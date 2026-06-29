from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx

from app.adapters.base import AdapterError
from app.utils.files import ensure_dir, write_json, write_placeholder_binary, write_text


SUBMIT_ACTION = "JimengRealmanAvatarPictureOmniV15SubmitTask"
RESULT_ACTION = "JimengRealmanAvatarPictureOmniV15GetResult"


@dataclass(frozen=True)
class OmniHumanRequest:
    image_url: str
    audio_url: str
    prompt: str
    task_id: str | None = None


class OmniHumanVideoAdapter:
    name = "omnihuman"

    def __init__(
        self,
        *,
        dry_run: bool = True,
        enabled: bool = False,
        access_key: str | None = None,
        secret_key: str | None = None,
        endpoint: str = "https://visual.volcengineapi.com",
        region: str = "cn-north-1",
        service: str = "cv",
        version: str = "2024-06-06",
        req_key: str = "jimeng_realman_avatar_picture_omni_v15",
        output_resolution: int = 1080,
        prompt: str = "自然口播，面带微笑，保持人物身份一致。",
        pe_fast_mode: bool = False,
        timeout_seconds: float = 1200.0,
        poll_interval_seconds: float = 5.0,
    ):
        self.dry_run = dry_run
        self.enabled = enabled
        self.access_key = access_key or ""
        self.secret_key = secret_key or ""
        self.endpoint = endpoint.rstrip("/")
        self.region = region or "cn-north-1"
        self.service = service or "cv"
        self.version = version or "2024-06-06"
        self.req_key = req_key or "jimeng_realman_avatar_picture_omni_v15"
        self.output_resolution = output_resolution
        self.prompt = prompt
        self.pe_fast_mode = pe_fast_mode
        self.timeout_seconds = timeout_seconds
        self.poll_interval_seconds = poll_interval_seconds

    def readiness(self) -> dict[str, object]:
        blocking_items: list[str] = []
        if not self.dry_run and not self.enabled:
            blocking_items.append("OMNIHUMAN_ENABLED")
        if not self.endpoint:
            blocking_items.append("OMNIHUMAN_ENDPOINT")
        if not self.dry_run and not self.access_key:
            blocking_items.append("OMNIHUMAN_ACCESS_KEY")
        if not self.dry_run and not self.secret_key:
            blocking_items.append("OMNIHUMAN_SECRET_KEY")
        return {
            "provider": "volcengine_omnihuman",
            "ready": not blocking_items or self.dry_run,
            "enabled": self.enabled,
            "dry_run": self.dry_run,
            "endpoint": self.endpoint,
            "region": self.region,
            "service": self.service,
            "version": self.version,
            "req_key": self.req_key,
            "access_key_configured": bool(self.access_key),
            "secret_key_configured": bool(self.secret_key),
            "blocking_items": blocking_items,
        }

    async def generate_video(
        self,
        *,
        image_url: str,
        audio_url: str,
        prompt: str | None,
        out_dir: Path,
        output_name: str = "omnihuman_video.mp4",
    ) -> Path:
        ensure_dir(out_dir)
        output_path = out_dir / output_name
        request_log = out_dir / "omnihuman_request.json"
        response_log = out_dir / "omnihuman_response.json"
        http_log = out_dir / "omnihuman_http.log"
        request_prompt = prompt or self.prompt
        request_payload = {
            "provider": "volcengine_omnihuman",
            "endpoint": self.endpoint,
            "version": self.version,
            "req_key": self.req_key,
            "image_url": image_url,
            "audio_url": audio_url,
            "prompt": request_prompt,
            "output_resolution": self.output_resolution,
            "pe_fast_mode": self.pe_fast_mode,
            "dry_run": self.dry_run,
        }
        write_json(request_log, request_payload)

        if self.dry_run:
            write_json(response_log, {"status": "done", "dry_run": True, "video_url": str(output_path)})
            write_text(http_log, "dry-run: OmniHuman call skipped; placeholder media generated.\n")
            return write_placeholder_binary(output_path, f"omnihuman-image={image_url};audio={audio_url}")

        self._require_available()
        if not _is_public_url(image_url):
            raise AdapterError("OmniHuman 需要公网可访问头像 URL：请在数字人或任务 metadata 中填写 omnihuman_image_url。")
        if not _is_public_url(audio_url):
            raise AdapterError("OmniHuman 需要公网可访问音频 URL：请在声音档案或任务 metadata 中填写 omnihuman_audio_url。")

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True) as client:
                submit_data = await self._post_action(
                    client,
                    SUBMIT_ACTION,
                    {
                        "req_key": self.req_key,
                        "image_url": image_url,
                        "audio_url": audio_url,
                        "prompt": request_prompt,
                        "output_resolution": self.output_resolution,
                        "pe_fast_mode": self.pe_fast_mode,
                    },
                )
                task_id = self._extract_task_id(submit_data)
                result_data = await self._wait_for_result(client, task_id)
                write_json(response_log, {"submit": submit_data, "result": result_data})
                video_url = self._extract_video_url(result_data)
                if not video_url:
                    raise AdapterError(f"OmniHuman 返回结果里没有 video_url：{result_data}")
                response = await client.get(video_url)
                response.raise_for_status()
                output_path.write_bytes(response.content)
        except AdapterError:
            raise
        except Exception as exc:  # noqa: BLE001 - external API errors need to surface in task steps.
            write_text(http_log, f"OmniHuman 请求失败：{exc}\n")
            raise AdapterError(f"OmniHuman 请求失败：{exc}") from exc

        write_text(http_log, f"OmniHuman completed: {output_path}\n")
        return output_path

    def _require_available(self) -> None:
        blockers = self.readiness()["blocking_items"]
        if blockers:
            raise AdapterError("OmniHuman 不可用：" + "，".join(str(item) for item in blockers))

    async def _post_action(self, client: httpx.AsyncClient, action: str, payload: dict[str, object]) -> dict[str, object]:
        params = {"Action": action, "Version": self.version}
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers = self._signed_headers("POST", "/", params, body)
        response = await client.post(self.endpoint, params=params, headers=headers, content=body)
        response.raise_for_status()
        data = response.json()
        if not self._is_success(data):
            raise AdapterError(f"OmniHuman API 返回失败：{data}")
        return data

    async def _wait_for_result(self, client: httpx.AsyncClient, task_id: str) -> dict[str, object]:
        deadline = asyncio.get_running_loop().time() + self.timeout_seconds
        current: dict[str, object] = {}
        while asyncio.get_running_loop().time() < deadline:
            current = await self._post_action(
                client,
                RESULT_ACTION,
                {"req_key": self.req_key, "task_id": task_id},
            )
            status = self._extract_status(current)
            if status in {"done", "success", "succeeded", "completed", "finish"} and self._extract_video_url(current):
                return current
            if status in {"failed", "fail", "error", "rejected"}:
                raise AdapterError(f"OmniHuman 任务失败：{current}")
            await asyncio.sleep(self.poll_interval_seconds)
        raise AdapterError(f"OmniHuman 任务超时：{task_id}")

    def _signed_headers(self, method: str, canonical_uri: str, params: dict[str, str], body: bytes) -> dict[str, str]:
        parsed = urlparse(self.endpoint)
        host = parsed.netloc
        now = datetime.now(timezone.utc)
        x_date = now.strftime("%Y%m%dT%H%M%SZ")
        short_date = now.strftime("%Y%m%d")
        payload_hash = hashlib.sha256(body).hexdigest()
        query = "&".join(f"{quote(key, safe='')}={quote(str(params[key]), safe='')}" for key in sorted(params))
        canonical_headers = (
            "content-type:application/json\n"
            f"host:{host}\n"
            f"x-content-sha256:{payload_hash}\n"
            f"x-date:{x_date}\n"
        )
        signed_headers = "content-type;host;x-content-sha256;x-date"
        canonical_request = "\n".join([method.upper(), canonical_uri, query, canonical_headers, signed_headers, payload_hash])
        credential_scope = f"{short_date}/{self.region}/{self.service}/request"
        string_to_sign = "\n".join(
            [
                "HMAC-SHA256",
                x_date,
                credential_scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            ]
        )
        signing_key = _hmac(_hmac(_hmac(_hmac(self.secret_key.encode("utf-8"), short_date), self.region), self.service), "request")
        signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
        authorization = (
            "HMAC-SHA256 "
            f"Credential={self.access_key}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, "
            f"Signature={signature}"
        )
        return {
            "Authorization": authorization,
            "Content-Type": "application/json",
            "Host": host,
            "X-Content-Sha256": payload_hash,
            "X-Date": x_date,
        }

    @staticmethod
    def _is_success(data: dict[str, object]) -> bool:
        code = data.get("code", data.get("status"))
        if code in (0, 10000, "0", "10000", None):
            return True
        return False

    @staticmethod
    def _extract_task_id(data: dict[str, object]) -> str:
        for container in _response_containers(data):
            if isinstance(container, dict):
                for key in ("task_id", "taskId", "id"):
                    value = container.get(key)
                    if value:
                        return str(value)
        raise AdapterError(f"OmniHuman 提交结果里没有 task_id：{data}")

    @staticmethod
    def _extract_status(data: dict[str, object]) -> str:
        for container in _response_containers(data):
            if isinstance(container, dict):
                value = container.get("status") or container.get("state")
                if value:
                    return str(value).lower()
        return ""

    @staticmethod
    def _extract_video_url(data: dict[str, object]) -> str:
        for container in _response_containers(data):
            if isinstance(container, dict):
                for key in ("video_url", "videoUrl", "url", "download_url", "downloadUrl"):
                    value = container.get(key)
                    if value:
                        return str(value)
                video = container.get("video")
                if isinstance(video, dict):
                    value = video.get("url") or video.get("video_url")
                    if value:
                        return str(value)
        return ""


def _response_containers(data: dict[str, object]) -> list[dict[str, object]]:
    containers: list[dict[str, object]] = []

    def add(container: object) -> None:
        if not isinstance(container, dict):
            return
        for key in ("data", "Data", "result", "Result"):
            nested = container.get(key)
            if isinstance(nested, dict):
                add(nested)
        containers.append(container)

    add(data)
    return containers


def _hmac(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


def _is_public_url(value: str) -> bool:
    parsed = urlparse(value or "")
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
