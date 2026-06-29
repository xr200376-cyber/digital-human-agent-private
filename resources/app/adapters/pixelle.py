import json
from pathlib import Path
from urllib.parse import urljoin

import httpx

from app.adapters.base import AdapterError, ScriptGeneratorAdapter, VideoAssemblyAdapter, minimal_script_payload
from app.schemas import CreateVideoTaskRequest
from app.utils.files import write_json, write_placeholder_binary


class PixelleAdapter(ScriptGeneratorAdapter, VideoAssemblyAdapter):
    name = "pixelle"

    def __init__(
        self,
        base_url: str,
        dry_run: bool = True,
        timeout_seconds: float = 120.0,
        script_endpoint: str = "/api/content/narration",
        video_endpoint: str = "/api/video/generate/sync",
    ):
        super().__init__(dry_run=dry_run)
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.script_endpoint = script_endpoint or "/api/content/narration"
        self.video_endpoint = video_endpoint or "/api/video/generate/sync"

    def available(self) -> bool:
        return bool(self.base_url) and not self.dry_run

    @staticmethod
    def _scene_count(request: CreateVideoTaskRequest) -> int:
        return max(1, min(20, round(request.duration_seconds / 15) or 1))

    @staticmethod
    def _script_source_text(request: CreateVideoTaskRequest) -> str:
        return request.fixed_script or "\n".join(
            [
                f"Brand: {request.brand_name}",
                f"Persona: {request.persona}",
                f"Topic: {request.topic}",
                f"Platform: {request.platform}",
            ]
        )

    def _payload_from_narrations(self, request: CreateVideoTaskRequest, narrations: list[str]) -> dict:
        payload = minimal_script_payload(request)
        duration = max(1, request.duration_seconds)
        scene_duration = duration / len(narrations)
        segments = []
        for index, narration in enumerate(narrations):
            start = round(index * scene_duration, 3)
            end = duration if index == len(narrations) - 1 else round((index + 1) * scene_duration, 3)
            segments.append({"start": start, "end": end, "text": narration, "type": "pixelle_narration"})
        payload["body"] = "\n".join(narrations)
        payload["segments"] = segments
        payload["pixelle"] = {"mode": "http", "route": self.script_endpoint}
        return payload

    async def generate_script(self, request: CreateVideoTaskRequest, out_dir: Path) -> Path:
        out_path = out_dir / "script.json"
        if self.dry_run:
            return write_json(out_path, minimal_script_payload(request))

        payload = {
            "text": self._script_source_text(request),
            "n_scenes": self._scene_count(request),
            "min_words": 5,
            "max_words": 30,
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(self._url(self.script_endpoint), json=payload)
            response.raise_for_status()
            data = response.json()
        narrations = data.get("narrations")
        if not isinstance(narrations, list) or not narrations:
            raise AdapterError(f"Pixelle narration response did not include narrations: {data}")
        return write_json(out_path, self._payload_from_narrations(request, [str(item) for item in narrations]))

    @staticmethod
    def _text_from_script(script_json: Path) -> tuple[str, int, str | None]:
        data = json.loads(script_json.read_text(encoding="utf-8"))
        segments = data.get("segments") or []
        texts = [str(segment.get("text", "")).strip() for segment in segments if segment.get("text")]
        text = "\n".join(texts) or str(data.get("body") or data.get("hook") or "").strip()
        if not text:
            raise AdapterError(f"Script JSON has no usable text for Pixelle video generation: {script_json}")
        title = str(data.get("hook") or data.get("title") or "").strip() or None
        return text, max(1, len(texts)), title

    async def _download_video_result(self, client: httpx.AsyncClient, result_url: str, out_path: Path) -> None:
        if result_url.startswith("http://") or result_url.startswith("https://"):
            download_url = result_url
        elif result_url.startswith("/"):
            download_url = urljoin(self.base_url + "/", result_url.lstrip("/"))
        else:
            local_path = Path(result_url)
            if local_path.exists():
                out_path.write_bytes(local_path.read_bytes())
                return
            download_url = urljoin(self.base_url + "/", result_url)
        video_response = await client.get(download_url)
        video_response.raise_for_status()
        out_path.write_bytes(video_response.content)

    async def assemble_video(self, video_path: Path, script_json: Path, out_dir: Path) -> Path:
        out_path = out_dir / "final.mp4"
        if self.dry_run:
            return write_placeholder_binary(out_path, f"final-video-from={video_path.name};script={script_json.name}")

        text, n_scenes, title = self._text_from_script(script_json)
        payload = {
            "text": text,
            "mode": "fixed",
            "title": title,
            "n_scenes": n_scenes,
            "frame_template": "1080x1920/video_default.html",
            "template_params": {
                "source_video_path": str(video_path),
            },
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(self._url(self.video_endpoint), json=payload)
            response.raise_for_status()
            data = response.json()
            result_url = data.get("video_url") or data.get("video_path") or data.get("file_path")
            if not result_url:
                raise AdapterError(f"Pixelle video response did not include a video URL/path: {data}")
            await self._download_video_result(client, str(result_url), out_path)
        return out_path

    def _url(self, endpoint: str) -> str:
        if endpoint.startswith("http://") or endpoint.startswith("https://"):
            return endpoint
        return urljoin(self.base_url + "/", endpoint.lstrip("/"))
