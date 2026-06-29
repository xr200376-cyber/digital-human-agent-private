import asyncio
import json
from pathlib import Path
from urllib.parse import urljoin

import httpx

from app.adapters.base import AdapterError
from app.utils.files import ensure_dir, write_json, write_placeholder_binary, write_text


class TavusVideoAdapter:
    name = "tavus"

    def __init__(
        self,
        *,
        dry_run: bool = True,
        enabled: bool = False,
        base_url: str = "https://tavusapi.com",
        api_key: str | None = None,
        replica_id: str | None = None,
        video_endpoint: str = "/v2/videos",
        timeout_seconds: float = 1800.0,
        poll_interval_seconds: float = 8.0,
    ) -> None:
        self.dry_run = dry_run
        self.enabled = enabled
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or ""
        self.replica_id = replica_id or ""
        self.video_endpoint = video_endpoint or "/v2/videos"
        self.timeout_seconds = timeout_seconds
        self.poll_interval_seconds = poll_interval_seconds

    @property
    def videos_url(self) -> str:
        return self._url(self.video_endpoint)

    def available(self) -> bool:
        if self.dry_run:
            return True
        return self.enabled and bool(self.base_url) and bool(self.api_key) and bool(self.replica_id)

    def readiness(self) -> dict[str, object]:
        blockers: list[str] = []
        if not self.dry_run and not self.enabled:
            blockers.append("TAVUS_ENABLED")
        if not self.base_url:
            blockers.append("TAVUS_BASE_URL")
        if not self.dry_run and not self.api_key:
            blockers.append("TAVUS_API_KEY")
        if not self.dry_run and not self.replica_id:
            blockers.append("TAVUS_REPLICA_ID")
        return {
            "provider": "tavus",
            "ready": not blockers or self.dry_run,
            "enabled": self.enabled,
            "dry_run": self.dry_run,
            "base_url": self.base_url,
            "video_endpoint": self.video_endpoint,
            "replica_id": self.replica_id,
            "api_key_configured": bool(self.api_key),
            "blocking_items": blockers,
        }

    def require_available(self) -> None:
        if self.available():
            return
        raise AdapterError("Tavus 云端数字人不可用：" + "；".join(self.readiness()["blocking_items"]))

    async def list_replicas(self) -> list[dict[str, object]]:
        self.require_available()
        headers = self._headers()
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            response = await client.get(self._url("/v2/replicas"), headers=headers)
            response.raise_for_status()
            data = response.json()
        replicas = data.get("data") if isinstance(data, dict) else data
        return list(replicas or [])

    async def generate_video(
        self,
        script_json: Path,
        out_dir: Path,
        *,
        replica_id: str | None = None,
        video_name: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> Path:
        ensure_dir(out_dir)
        out_path = out_dir / "tavus_video.mp4"
        request_path = out_dir / "tavus_request.json"
        response_path = out_dir / "tavus_response.json"
        http_log = out_dir / "tavus_http.log"
        resolved_replica_id = replica_id or self.replica_id
        script = self._script_text(script_json)
        payload = {
            "replica_id": resolved_replica_id,
            "script": script,
            "video_name": video_name or f"Aivo-{out_dir.name}",
        }
        write_json(
            request_path,
            {
                "provider": "tavus",
                "base_url": self.base_url,
                "video_endpoint": self.video_endpoint,
                "replica_id": resolved_replica_id,
                "payload": payload,
                "local_metadata": metadata or {},
                "script_json": str(script_json),
                "output_path": str(out_path),
                "dry_run": self.dry_run,
            },
        )

        if self.dry_run:
            write_json(
                response_path,
                {
                    "status": "ready",
                    "video_id": "dry-run",
                    "download_url": str(out_path),
                    "provider": "tavus",
                    "dry_run": True,
                },
            )
            write_text(http_log, "dry-run: Tavus call skipped; placeholder media generated.\n")
            return write_placeholder_binary(out_path, f"tavus-replica={resolved_replica_id};script={script[:80]}")

        self.require_available()
        if not resolved_replica_id:
            raise AdapterError("Tavus 需要 TAVUS_REPLICA_ID 或任务 metadata.tavus_replica_id")

        headers = self._headers()
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True) as client:
                response = await client.post(self.videos_url, headers=headers, json=payload)
                if response.status_code >= 400:
                    write_json(response_path, self._response_snapshot(response))
                    write_text(http_log, f"Tavus request failed: HTTP {response.status_code}\n")
                response.raise_for_status()
                data = response.json()
                data = await self._wait_for_video(client, headers, data)
                write_json(response_path, data)
                download_url = self._extract_download_url(data)
                if not download_url:
                    raise AdapterError(f"Tavus 返回结果没有可下载视频地址：{data}")
                download = await client.get(download_url, headers=headers)
                download.raise_for_status()
                out_path.write_bytes(download.content)
        except AdapterError:
            raise
        except Exception as exc:  # noqa: BLE001 - external API failures must be visible in task logs.
            write_text(http_log, f"Tavus 请求失败：{exc}\n")
            raise AdapterError(f"Tavus 请求失败：{exc}") from exc
        write_text(http_log, f"Tavus completed: {out_path}\n")
        return out_path

    async def _wait_for_video(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        data: dict[str, object],
    ) -> dict[str, object]:
        if self._extract_download_url(data):
            return data
        video_id = data.get("video_id") or data.get("id")
        if not video_id:
            return data
        status_url = self._url(f"/v2/videos/{video_id}")
        deadline = asyncio.get_running_loop().time() + self.timeout_seconds
        current = data
        while asyncio.get_running_loop().time() < deadline:
            status = str(current.get("status", "")).lower()
            if status in {"ready", "completed", "succeeded", "success"} and self._extract_download_url(current):
                return current
            if status in {"failed", "error", "rejected"}:
                raise AdapterError(f"Tavus 视频生成失败：{current.get('error') or current}")
            await asyncio.sleep(self.poll_interval_seconds)
            response = await client.get(status_url, headers=headers)
            response.raise_for_status()
            current = response.json()
        raise AdapterError(f"Tavus 视频生成超时：{video_id}")

    def _headers(self) -> dict[str, str]:
        return {"x-api-key": self.api_key}

    @staticmethod
    def _response_snapshot(response: httpx.Response) -> dict[str, object]:
        try:
            body: object = response.json()
        except ValueError:
            body = response.text[:4000]
        return {
            "status_code": response.status_code,
            "reason_phrase": response.reason_phrase,
            "body": body,
        }

    def _url(self, endpoint: str) -> str:
        if endpoint.startswith("http://") or endpoint.startswith("https://"):
            return endpoint
        return urljoin(self.base_url + "/", endpoint.lstrip("/"))

    @staticmethod
    def _script_text(script_json: Path) -> str:
        data = json.loads(script_json.read_text(encoding="utf-8"))
        segments = data.get("segments") or []
        texts = [str(segment.get("text", "")).strip() for segment in segments if segment.get("text")]
        text = "\n".join(texts) or str(data.get("body") or data.get("hook") or "").strip()
        if not text:
            raise AdapterError(f"Tavus 需要可朗读脚本文本：{script_json}")
        return text

    @staticmethod
    def _extract_download_url(data: dict[str, object]) -> str:
        for key in ("download_url", "downloadUrl", "video_url", "videoUrl", "mp4_url", "mp4Url", "file_url", "fileUrl"):
            value = data.get(key)
            if value:
                return str(value)
        output = data.get("output")
        if isinstance(output, dict):
            value = output.get("download_url") or output.get("video_url") or output.get("mp4_url") or output.get("file_url")
            if value:
                return str(value)
        return ""
