from __future__ import annotations

import asyncio
import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

from app.adapters.base import AdapterError
from app.utils.files import ensure_dir, write_json, write_placeholder_binary, write_text


XILING_DEFAULT_BASE_URL = "https://open.xiling.baidu.com"
XILING_SUBMIT_ENDPOINT = "/api/digitalhuman/open/v1/video/submit"
XILING_TASK_ENDPOINT = "/api/digitalhuman/open/v1/video/task"


def build_xiling_authorization(*, app_id: str, app_key: str, expire_time: str | None = None) -> str:
    expires = expire_time or (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    signature = hmac.new(app_key.encode("utf-8"), f"{app_id}{expires}".encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{app_id}/{signature}/{expires}"


class BaiduXilingVideoAdapter:
    name = "baidu_xiling"

    def __init__(
        self,
        *,
        dry_run: bool = True,
        enabled: bool = False,
        base_url: str = XILING_DEFAULT_BASE_URL,
        app_id: str | None = None,
        app_key: str | None = None,
        figure_id: str | None = None,
        tts_person: str | None = None,
        width: int = 1080,
        height: int = 1920,
        transparent: bool = False,
        timeout_seconds: float = 1200.0,
        poll_interval_seconds: float = 5.0,
    ) -> None:
        self.dry_run = dry_run
        self.enabled = enabled
        self.base_url = (base_url or XILING_DEFAULT_BASE_URL).rstrip("/")
        self.app_id = app_id or ""
        self.app_key = app_key or ""
        self.figure_id = figure_id or ""
        self.tts_person = tts_person or ""
        self.width = int(width or 1080)
        self.height = int(height or 1920)
        self.transparent = bool(transparent)
        self.timeout_seconds = float(timeout_seconds or 1200.0)
        self.poll_interval_seconds = float(poll_interval_seconds or 5.0)

    def available(self) -> bool:
        if self.dry_run:
            return True
        return bool(self.enabled and self.app_id and self.app_key and self.figure_id)

    def readiness(self) -> dict[str, Any]:
        blocking_items: list[str] = []
        if not self.dry_run and not self.enabled:
            blocking_items.append("BAIDU_XILING_ENABLED")
        if not self.dry_run and not self.app_id:
            blocking_items.append("BAIDU_XILING_APP_ID")
        if not self.dry_run and not self.app_key:
            blocking_items.append("BAIDU_XILING_APP_KEY")
        if not self.dry_run and not self.figure_id:
            blocking_items.append("BAIDU_XILING_FIGURE_ID")
        return {
            "provider": self.name,
            "ready": not blocking_items or self.dry_run,
            "enabled": self.enabled,
            "dry_run": self.dry_run,
            "base_url": self.base_url,
            "figure_id_configured": bool(self.figure_id),
            "tts_person_configured": bool(self.tts_person),
            "app_id_configured": bool(self.app_id),
            "app_key_configured": bool(self.app_key),
            "blocking_items": blocking_items,
        }

    def require_available(self) -> None:
        if self.available():
            return
        blockers = ", ".join(str(item) for item in self.readiness()["blocking_items"])
        raise AdapterError(f"Baidu Xiling is not available: {blockers}")

    async def generate_video(
        self,
        *,
        text: str,
        audio_url: str = "",
        out_dir: Path,
        request_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Path:
        ensure_dir(out_dir)
        output_path = out_dir / "lip_synced.mp4"
        request_log = out_dir / "baidu_xiling_request.json"
        response_log = out_dir / "baidu_xiling_response.json"
        http_log = out_dir / "baidu_xiling_http.log"
        payload = self._build_submit_payload(text=text, audio_url=audio_url, request_id=request_id, metadata=metadata or {})
        write_json(
            request_log,
            {
                "provider": self.name,
                "base_url": self.base_url,
                "submit_endpoint": XILING_SUBMIT_ENDPOINT,
                "task_endpoint": XILING_TASK_ENDPOINT,
                "payload": payload,
                "dry_run": self.dry_run,
            },
        )

        if self.dry_run:
            write_json(
                response_log,
                {
                    "code": 0,
                    "success": True,
                    "result": {
                        "taskId": "dryrun-xiling-task",
                        "status": "SUCCESS",
                        "videoUrl": str(output_path),
                    },
                    "dry_run": True,
                },
            )
            write_text(http_log, "dry-run: Baidu Xiling call skipped; placeholder media generated.\n")
            return write_placeholder_binary(output_path, f"baidu-xiling;figure={self.figure_id};audio={audio_url}")

        self.require_available()
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True) as client:
                submit_data = await self._submit(client, payload)
                task_id = _extract_task_id(submit_data)
                if not task_id:
                    raise AdapterError(f"Baidu Xiling response missing taskId: {submit_data}")
                result = await self._poll_until_done(client, task_id=task_id)
                write_json(response_log, result)
                result_url = _extract_video_url(result)
                if not result_url:
                    raise AdapterError(f"Baidu Xiling response missing videoUrl: {result}")
                return await self.download_result(result_url=result_url, output_path=output_path)
        except AdapterError:
            raise
        except Exception as exc:  # noqa: BLE001 - cloud failures must be captured in task logs.
            write_text(http_log, f"Baidu Xiling request failed: {exc}\n")
            raise AdapterError(f"Baidu Xiling request failed: {exc}") from exc

    async def _submit(self, client: httpx.AsyncClient, payload: dict[str, Any]) -> dict[str, Any]:
        response = await client.post(
            f"{self.base_url}{XILING_SUBMIT_ENDPOINT}",
            headers=self._headers(),
            json=payload,
        )
        data = _safe_response_json(response)
        if response.status_code >= 400 or not _xiling_success(data):
            raise AdapterError(f"Baidu Xiling submit failed: HTTP {response.status_code}; {data}")
        return data

    async def _poll_until_done(self, client: httpx.AsyncClient, *, task_id: str) -> dict[str, Any]:
        deadline = asyncio.get_running_loop().time() + self.timeout_seconds
        last_data: dict[str, Any] = {}
        while asyncio.get_running_loop().time() < deadline:
            data = await self.get_job_status(client=client, job_id=task_id)
            last_data = data
            result = _result(data)
            status = str(result.get("status") or "").upper()
            if status == "SUCCESS":
                return data
            if status == "FAILED":
                raise AdapterError(f"Baidu Xiling task failed: {data}")
            await asyncio.sleep(self.poll_interval_seconds)
        raise AdapterError(f"Baidu Xiling task timed out: {task_id}; last={last_data}")

    async def get_job_status(self, *, job_id: str, client: httpx.AsyncClient | None = None) -> dict[str, Any]:
        if self.dry_run:
            return {"code": 0, "success": True, "result": {"taskId": job_id, "status": "SUCCESS", "videoUrl": "dryrun"}}
        self.require_available()
        close_client = client is None
        if client is None:
            client = httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True)
        try:
            response = await client.get(
                f"{self.base_url}{XILING_TASK_ENDPOINT}",
                headers=self._headers(),
                params={"taskId": job_id, "requestId": uuid4().hex},
            )
            data = _safe_response_json(response)
            if response.status_code >= 400 or not _xiling_success(data):
                raise AdapterError(f"Baidu Xiling status failed: HTTP {response.status_code}; {data}")
            return data
        finally:
            if close_client:
                await client.aclose()

    async def download_result(self, *, result_url: str, output_path: Path) -> Path:
        ensure_dir(output_path.parent)
        if self.dry_run:
            return write_placeholder_binary(output_path, f"baidu-xiling-result={result_url}")
        async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True) as client:
            response = await client.get(result_url)
            response.raise_for_status()
            output_path.write_bytes(response.content)
        return output_path

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": build_xiling_authorization(app_id=self.app_id, app_key=self.app_key),
            "Content-Type": "application/json;charset=utf-8",
        }

    def _build_submit_payload(
        self,
        *,
        text: str,
        audio_url: str,
        request_id: str | None,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        drive_type = "VOICE" if audio_url else "TEXT"
        payload: dict[str, Any] = {
            "requestId": request_id or uuid4().hex,
            "figureId": str(metadata.get("baidu_xiling_figure_id") or self.figure_id),
            "driveType": drive_type,
            "videoParams": {
                "width": int(metadata.get("baidu_xiling_width") or self.width),
                "height": int(metadata.get("baidu_xiling_height") or self.height),
                "transparent": bool(metadata.get("baidu_xiling_transparent", self.transparent)),
            },
            "subtitleParams": {
                "enabled": bool(metadata.get("baidu_xiling_subtitles", False)),
                "subtitlePolicy": str(metadata.get("baidu_xiling_subtitle_policy") or "SRT"),
            },
            "autoAnimoji": bool(metadata.get("baidu_xiling_auto_animoji", False)),
        }
        if drive_type == "VOICE":
            payload["inputAudioUrl"] = audio_url
        else:
            if not text:
                raise AdapterError("Baidu Xiling TEXT mode requires text")
            payload["text"] = text
            tts_person = str(metadata.get("baidu_xiling_tts_person") or self.tts_person or "")
            payload["ttsParams"] = {
                "speed": str(metadata.get("baidu_xiling_speed") or "5"),
                "pitch": str(metadata.get("baidu_xiling_pitch") or "5"),
                "volume": str(metadata.get("baidu_xiling_volume") or "5"),
            }
            if tts_person:
                payload["ttsParams"]["person"] = tts_person
        background_url = metadata.get("baidu_xiling_background_image_url")
        callback_url = metadata.get("baidu_xiling_callback_url")
        if background_url:
            payload["backgroundImageUrl"] = str(background_url)
        if callback_url:
            payload["callbackUrl"] = str(callback_url)
        dh_params = metadata.get("baidu_xiling_dh_params")
        if isinstance(dh_params, dict):
            payload["dhParams"] = dh_params
        play_control = metadata.get("baidu_xiling_play_control_params")
        if isinstance(play_control, dict):
            payload["playControlParams"] = play_control
        return payload


def _result(data: dict[str, Any]) -> dict[str, Any]:
    value = data.get("result")
    return value if isinstance(value, dict) else {}


def _extract_task_id(data: dict[str, Any]) -> str:
    return str(_result(data).get("taskId") or data.get("taskId") or "")


def _extract_video_url(data: dict[str, Any]) -> str:
    result = _result(data)
    return str(result.get("videoUrl") or result.get("video_url") or data.get("videoUrl") or data.get("video_url") or "")


def _xiling_success(data: dict[str, Any]) -> bool:
    return bool(data.get("success") is True or data.get("code") == 0)


def _safe_response_json(response: httpx.Response) -> dict[str, Any]:
    try:
        return response.json()
    except Exception:
        return {"status_code": response.status_code, "text": response.text[:2000]}
