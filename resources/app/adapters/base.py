from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from app.schemas import CreateVideoTaskRequest


class AdapterError(RuntimeError):
    pass


class BaseAdapter(ABC):
    name: str = "base"

    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run

    @abstractmethod
    def available(self) -> bool:
        """Return True when the real external tool is configured and callable."""

    def require_available(self) -> None:
        if not self.available():
            raise AdapterError(f"{self.name} adapter is not available")


class ScriptGeneratorAdapter(BaseAdapter):
    @abstractmethod
    async def generate_script(self, request: CreateVideoTaskRequest, out_dir: Path) -> Path:
        """Return path to script.json."""


class VoiceAdapter(BaseAdapter):
    @abstractmethod
    async def synthesize_voice(self, script_json: Path, out_dir: Path) -> Path:
        """Return path to voice audio."""


class AvatarAdapter(BaseAdapter):
    @abstractmethod
    async def render_avatar(self, audio_path: Path, request: CreateVideoTaskRequest, out_dir: Path) -> Path:
        """Return path to avatar video."""


class LipSyncAdapter(BaseAdapter):
    @abstractmethod
    async def sync_lip(self, video_path: Path, audio_path: Path, out_dir: Path) -> Path:
        """Return path to lip-synced video."""


class VideoAssemblyAdapter(BaseAdapter):
    @abstractmethod
    async def assemble_video(self, video_path: Path, script_json: Path, out_dir: Path) -> Path:
        """Return path to final mp4."""


class DraftExportAdapter(BaseAdapter):
    @abstractmethod
    async def export_draft(
        self,
        final_video: Path,
        script_json: Path,
        out_dir: Path,
        *,
        template_report: Path | None = None,
    ) -> Path:
        """Return path to editable draft directory."""


def minimal_script_payload(request: CreateVideoTaskRequest) -> dict[str, Any]:
    hook = f"{request.brand_name}：{request.topic}"
    body = request.fixed_script or (
        f"大家好，我是{request.persona}。今天用 {request.duration_seconds} 秒讲清楚：{request.topic}。"
        "先说结论，再给三个可执行建议，最后提醒大家收藏并行动。"
    )
    return {
        "brand_name": request.brand_name,
        "persona": request.persona,
        "platform": request.platform,
        "duration_seconds": request.duration_seconds,
        "hook": hook,
        "body": body,
        "cta": "关注我，下一条继续拆解更实用的方法。",
        "segments": [
            {"start": 0, "end": 5, "text": hook, "type": "hook"},
            {"start": 5, "end": max(8, request.duration_seconds - 5), "text": body, "type": "body"},
            {"start": max(8, request.duration_seconds - 5), "end": request.duration_seconds, "text": "关注收藏，马上用起来。", "type": "cta"},
        ],
    }
