import asyncio
from pathlib import Path
from uuid import uuid4

import httpx

from app.adapters.base import AvatarAdapter, VoiceAdapter
from app.schemas import CreateVideoTaskRequest
from app.utils.files import write_placeholder_binary


class DuixAdapter(VoiceAdapter, AvatarAdapter):
    name = "duix"

    def __init__(self, base_url: str, dry_run: bool = True, timeout_seconds: float = 300.0):
        super().__init__(dry_run=dry_run)
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def available(self) -> bool:
        return bool(self.base_url) and not self.dry_run

    async def synthesize_voice(self, script_json: Path, out_dir: Path) -> Path:
        out_path = out_dir / "voice.wav"
        if self.dry_run:
            return write_placeholder_binary(out_path, f"voice-from={script_json.name}")

        # Codex: connect to Duix voice clone/TTS endpoint after speaker model exists.
        raise NotImplementedError("Implement Duix TTS endpoint according to deployed Duix version")

    async def render_avatar(self, audio_path: Path, request: CreateVideoTaskRequest, out_dir: Path) -> Path:
        out_path = out_dir / "avatar.mp4"
        if self.dry_run:
            return write_placeholder_binary(out_path, f"avatar-video-from={audio_path.name}")

        task_code = uuid4().hex
        # Duix README documents /easy/submit and /easy/query. The exact file path/URL mapping
        # depends on deployment. Codex should normalize local paths into Duix-accessible URLs.
        payload = {
            "audio_url": str(audio_path),
            "video_url": request.metadata.get("duix_avatar_source_video", ""),
            "code": task_code,
            "chaofen": 0,
            "watermark_switch": 0,
            "pn": 1,
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            submit = await client.post(f"{self.base_url}/easy/submit", json=payload)
            submit.raise_for_status()
            for _ in range(120):
                await asyncio.sleep(2)
                query = await client.get(f"{self.base_url}/easy/query", params={"code": task_code})
                query.raise_for_status()
                data = query.json()
                if data.get("status") in {"completed", "success", 2, "2"}:
                    # Codex: inspect real response schema and download/copy result video.
                    result_url = data.get("video_url") or data.get("result") or data.get("data", {}).get("video_url")
                    if not result_url:
                        raise RuntimeError(f"Duix completed without result video URL: {data}")
                    video = await client.get(result_url) if str(result_url).startswith("http") else None
                    if video:
                        video.raise_for_status()
                        out_path.write_bytes(video.content)
                    else:
                        Path(result_url).replace(out_path)
                    return out_path
                if data.get("status") in {"failed", "error", -1, "-1"}:
                    raise RuntimeError(f"Duix render failed: {data}")
        raise TimeoutError("Duix render timeout")
