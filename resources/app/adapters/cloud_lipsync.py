import asyncio
from pathlib import Path
from urllib.parse import urljoin

import httpx

from app.adapters.base import AdapterError, LipSyncAdapter
from app.utils.files import ensure_dir, write_json, write_placeholder_binary, write_text


class SyncSoLipSyncAdapter(LipSyncAdapter):
    name = "syncso"

    def __init__(
        self,
        *,
        dry_run: bool = True,
        enabled: bool = False,
        base_url: str = "https://api.sync.so",
        api_key: str | None = None,
        model: str = "lipsync-2",
        generate_endpoint: str = "/v2/generate",
        timeout_seconds: float = 1200.0,
        poll_interval_seconds: float = 5.0,
    ):
        super().__init__(dry_run=dry_run)
        self.enabled = enabled
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or ""
        self.model = model
        self.generate_endpoint = generate_endpoint or "/v2/generate"
        self.timeout_seconds = timeout_seconds
        self.poll_interval_seconds = poll_interval_seconds

    @property
    def generate_url(self) -> str:
        if self.base_url.endswith("/v2") and self.generate_endpoint.startswith("/v2/"):
            return urljoin(self.base_url + "/", self.generate_endpoint.removeprefix("/v2/"))
        return urljoin(self.base_url + "/", self.generate_endpoint.lstrip("/"))

    def available(self) -> bool:
        if self.dry_run:
            return True
        return self.enabled and bool(self.base_url) and bool(self.api_key)

    def require_available(self) -> None:
        if self.available():
            return
        blockers = self.readiness()["blocking_items"]
        raise AdapterError("Sync.so 云端口型同步不可用：" + "；".join(blockers))

    def readiness(self) -> dict[str, object]:
        blocking_items: list[str] = []
        if not self.dry_run and not self.enabled:
            blocking_items.append("CLOUD_LIPSYNC_ENABLED")
        if not self.base_url:
            blocking_items.append("SYNCSO_BASE_URL")
        if not self.dry_run and not self.api_key:
            blocking_items.append("SYNCSO_API_KEY")
        if not self.model:
            blocking_items.append("SYNCSO_MODEL")
        return {
            "provider": "syncso",
            "ready": not blocking_items or self.dry_run,
            "enabled": self.enabled,
            "dry_run": self.dry_run,
            "base_url": self.base_url,
            "generate_endpoint": self.generate_endpoint,
            "model": self.model,
            "api_key_configured": bool(self.api_key),
            "blocking_items": blocking_items,
        }

    async def sync_lip(self, video_path: Path, audio_path: Path, out_dir: Path) -> Path:
        ensure_dir(out_dir)
        out_path = out_dir / "lip_synced.mp4"
        request_log = out_dir / "syncso_request.json"
        response_log = out_dir / "syncso_response.json"
        http_log = out_dir / "syncso_http.log"
        write_json(
            request_log,
            {
                "provider": "syncso",
                "base_url": self.base_url,
                "generate_endpoint": self.generate_endpoint,
                "model": self.model,
                "video_path": str(video_path),
                "audio_path": str(audio_path),
                "output_path": str(out_path),
                "dry_run": self.dry_run,
            },
        )

        if self.dry_run:
            write_json(
                response_log,
                {
                    "status": "COMPLETED",
                    "outputUrl": str(out_path),
                    "dry_run": True,
                    "provider": "syncso",
                },
            )
            write_text(http_log, "dry-run: Sync.so call skipped; placeholder media generated.\n")
            return write_placeholder_binary(out_path, f"syncso-video={video_path.name};audio={audio_path.name}")

        self.require_available()
        if not video_path.exists():
            raise AdapterError(f"Sync.so 输入视频不存在：{video_path}")
        if not audio_path.exists():
            raise AdapterError(f"Sync.so 输入音频不存在：{audio_path}")

        headers = {"x-api-key": self.api_key}
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True) as client:
                data = await self._create_generation(client, headers, video_path, audio_path)
                data = await self._wait_for_output(client, headers, data)
                write_json(response_log, data)
                output_url = self._extract_output_url(data)
                if not output_url:
                    raise AdapterError(f"Sync.so 返回结果里没有 outputUrl：{data}")
                response = await client.get(output_url, headers=headers)
                response.raise_for_status()
                out_path.write_bytes(response.content)
        except AdapterError:
            raise
        except Exception as exc:  # noqa: BLE001 - external API errors need to surface in task steps.
            write_text(http_log, f"Sync.so 请求失败：{exc}\n")
            raise AdapterError(f"Sync.so 请求失败：{exc}") from exc

        write_text(http_log, f"Sync.so completed: {out_path}\n")
        return out_path

    async def _create_generation(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        video_path: Path,
        audio_path: Path,
    ) -> dict[str, object]:
        with video_path.open("rb") as video_file, audio_path.open("rb") as audio_file:
            files = {
                "video": (video_path.name, video_file, "video/mp4"),
                "audio": (audio_path.name, audio_file, "audio/wav"),
            }
            response = await client.post(self.generate_url, headers=headers, data={"model": self.model}, files=files)
        response.raise_for_status()
        return response.json()

    async def _wait_for_output(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        data: dict[str, object],
    ) -> dict[str, object]:
        if self._extract_output_url(data):
            return data
        generation_id = data.get("id")
        if not generation_id:
            return data
        status_url = urljoin(self.generate_url.rstrip("/") + "/", str(generation_id))
        deadline = asyncio.get_running_loop().time() + self.timeout_seconds
        current = data
        while asyncio.get_running_loop().time() < deadline:
            status = str(current.get("status", "")).upper()
            if status in {"COMPLETED", "SUCCEEDED", "SUCCESS"} and self._extract_output_url(current):
                return current
            if status in {"FAILED", "REJECTED", "ERROR"}:
                raise AdapterError(f"Sync.so 任务失败：{current.get('error') or current}")
            await asyncio.sleep(self.poll_interval_seconds)
            response = await client.get(status_url, headers=headers)
            response.raise_for_status()
            current = response.json()
        raise AdapterError(f"Sync.so 任务超时：{generation_id}")

    @staticmethod
    def _extract_output_url(data: dict[str, object]) -> str:
        for key in ("outputUrl", "output_url", "videoUrl", "video_url", "downloadUrl", "download_url", "url"):
            value = data.get(key)
            if value:
                return str(value)
        output = data.get("output")
        if isinstance(output, dict):
            value = output.get("url") or output.get("outputUrl") or output.get("downloadUrl")
            if value:
                return str(value)
        return ""


class PixVerseLipSyncAdapter(LipSyncAdapter):
    name = "pixverse"

    def __init__(
        self,
        *,
        dry_run: bool = True,
        enabled: bool = False,
        base_url: str = "https://superaiapi.top",
        api_key: str | None = None,
        model: str = "pixverse-lipsync:stable",
        generate_endpoint: str = "/v1/video/generations",
        task_endpoint_template: str = "/v1/video/tasks/{task_id}",
        timeout_seconds: float = 1200.0,
        poll_interval_seconds: float = 5.0,
    ):
        super().__init__(dry_run=dry_run)
        self.enabled = enabled
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or ""
        self.model = model or "pixverse-lipsync:stable"
        self.generate_endpoint = generate_endpoint or "/v1/video/generations"
        self.task_endpoint_template = task_endpoint_template or "/v1/video/tasks/{task_id}"
        self.timeout_seconds = timeout_seconds
        self.poll_interval_seconds = poll_interval_seconds

    @property
    def generate_url(self) -> str:
        return urljoin(self.base_url + "/", self.generate_endpoint.lstrip("/"))

    def task_url(self, task_id: str) -> str:
        endpoint = self.task_endpoint_template.replace("{task_id}", str(task_id))
        return urljoin(self.base_url + "/", endpoint.lstrip("/"))

    def available(self) -> bool:
        if self.dry_run:
            return True
        return self.enabled and bool(self.base_url) and bool(self.api_key)

    def require_available(self) -> None:
        if self.available():
            return
        blockers = self.readiness()["blocking_items"]
        raise AdapterError("PixVerse Lipsync cloud provider unavailable: " + ", ".join(blockers))

    def readiness(self) -> dict[str, object]:
        blocking_items: list[str] = []
        if not self.dry_run and not self.enabled:
            blocking_items.append("CLOUD_LIPSYNC_ENABLED")
        if not self.base_url:
            blocking_items.append("PIXVERSE_BASE_URL")
        if not self.dry_run and not self.api_key:
            blocking_items.append("PIXVERSE_API_KEY")
        if not self.model:
            blocking_items.append("PIXVERSE_MODEL")
        return {
            "provider": "pixverse",
            "ready": not blocking_items or self.dry_run,
            "enabled": self.enabled,
            "dry_run": self.dry_run,
            "base_url": self.base_url,
            "generate_endpoint": self.generate_endpoint,
            "task_endpoint_template": self.task_endpoint_template,
            "model": self.model,
            "api_key_configured": bool(self.api_key),
            "blocking_items": blocking_items,
        }

    async def sync_lip(
        self,
        video_path: Path,
        audio_path: Path,
        out_dir: Path,
        *,
        video_url: str | None = None,
        audio_url: str | None = None,
    ) -> Path:
        ensure_dir(out_dir)
        out_path = out_dir / "lip_synced.mp4"
        request_log = out_dir / "pixverse_request.json"
        response_log = out_dir / "pixverse_response.json"
        http_log = out_dir / "pixverse_http.log"
        write_json(
            request_log,
            {
                "provider": "pixverse",
                "base_url": self.base_url,
                "generate_endpoint": self.generate_endpoint,
                "task_endpoint_template": self.task_endpoint_template,
                "model": self.model,
                "video_path": str(video_path),
                "audio_path": str(audio_path),
                "video_url_configured": bool(video_url),
                "audio_url_configured": bool(audio_url),
                "output_path": str(out_path),
                "dry_run": self.dry_run,
            },
        )

        if self.dry_run:
            write_json(
                response_log,
                {
                    "status": "completed",
                    "video_url": str(out_path),
                    "dry_run": True,
                    "provider": "pixverse",
                },
            )
            write_text(http_log, "dry-run: PixVerse call skipped; placeholder media generated.\n")
            return write_placeholder_binary(out_path, f"pixverse-video={video_path.name};audio={audio_path.name}")

        self.require_available()
        if not video_url or not audio_url:
            raise AdapterError("PixVerse Lipsync requires public video_url and audio_url. Configure OSS/COS auto upload first.")

        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {"model": self.model, "video_url": video_url, "audio_url": audio_url}
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True) as client:
                data = await self._create_generation(client, headers, payload)
                data = await self._wait_for_output(client, headers, data)
                write_json(response_log, data)
                output_url = self._extract_output_url(data)
                if not output_url:
                    raise AdapterError(f"PixVerse response missing video url: {data}")
                response = await client.get(output_url, headers=headers)
                response.raise_for_status()
                out_path.write_bytes(response.content)
        except AdapterError:
            raise
        except Exception as exc:  # noqa: BLE001 - external API errors must be surfaced to task logs.
            write_text(http_log, f"PixVerse request failed: {exc}\n")
            raise AdapterError(f"PixVerse request failed: {exc}") from exc

        write_text(http_log, f"PixVerse completed: {out_path}\n")
        return out_path

    async def _create_generation(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        payload: dict[str, str],
    ) -> dict[str, object]:
        response = await client.post(self.generate_url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()

    async def _wait_for_output(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        data: dict[str, object],
    ) -> dict[str, object]:
        if self._extract_output_url(data):
            return data
        task_id = self._extract_task_id(data)
        if not task_id:
            return data
        deadline = asyncio.get_running_loop().time() + self.timeout_seconds
        current = data
        while asyncio.get_running_loop().time() < deadline:
            status = str(current.get("status") or current.get("state") or "").upper()
            if status in {"COMPLETED", "SUCCEEDED", "SUCCESS", "DONE"} and self._extract_output_url(current):
                return current
            if status in {"FAILED", "REJECTED", "ERROR", "CANCELED", "CANCELLED"}:
                raise AdapterError(f"PixVerse task failed: {current.get('error') or current}")
            await asyncio.sleep(self.poll_interval_seconds)
            response = await client.get(self.task_url(task_id), headers=headers)
            response.raise_for_status()
            current = response.json()
        raise AdapterError(f"PixVerse task timed out: {task_id}")

    @staticmethod
    def _extract_task_id(data: dict[str, object]) -> str:
        for container in _response_containers(data):
            for key in ("task_id", "taskId", "id"):
                value = container.get(key)
                if value:
                    return str(value)
        return ""

    @staticmethod
    def _extract_output_url(data: dict[str, object]) -> str:
        for container in _response_containers(data):
            for key in ("video_url", "videoUrl", "output_url", "outputUrl", "download_url", "downloadUrl", "url"):
                value = container.get(key)
                if value:
                    return str(value)
            output = container.get("output")
            if isinstance(output, dict):
                for key in ("video_url", "videoUrl", "url", "downloadUrl", "outputUrl"):
                    value = output.get(key)
                    if value:
                        return str(value)
            if isinstance(output, list):
                for item in output:
                    if isinstance(item, dict):
                        value = item.get("url") or item.get("video_url") or item.get("videoUrl")
                        if value:
                            return str(value)
                    elif isinstance(item, str) and item.startswith(("http://", "https://")):
                        return item
        return ""


def _response_containers(data: dict[str, object]) -> list[dict[str, object]]:
    containers: list[dict[str, object]] = []

    def visit(value: object) -> None:
        if isinstance(value, dict):
            containers.append(value)
            for key in ("data", "result", "response", "task", "output"):
                child = value.get(key)
                if isinstance(child, dict):
                    visit(child)
                elif isinstance(child, list):
                    for item in child:
                        visit(item)

    visit(data)
    return containers
