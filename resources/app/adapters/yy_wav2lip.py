from pathlib import Path
from typing import Any

from app.adapters.wav2lip import Wav2LipAdapter
from app.utils.files import write_json, write_text


class YYWav2LipAdapter(Wav2LipAdapter):
    name = "yywav2lip"

    def __init__(
        self,
        *,
        source_root: str | Path = Path("third_party/Wav2Lip"),
        checkpoint_path: str | Path = Path("resource/checkpoints/yywav2lip.pth"),
        role_model_dir: str | Path | None = None,
        python_executable: str | None = None,
        timeout_seconds: float = 600.0,
        dry_run: bool = True,
        enabled: bool = True,
    ):
        super().__init__(
            source_root=source_root,
            checkpoint_path=checkpoint_path,
            python_executable=python_executable,
            timeout_seconds=timeout_seconds,
            dry_run=dry_run,
            enabled=enabled,
        )
        self.role_model_dir = Path(role_model_dir) if role_model_dir else None

    def readiness(self, role_model_path: str | Path | None = None) -> dict[str, Any]:
        payload = super().readiness()
        payload["engine"] = self.name
        blocking_items = list(payload["blocking_items"])
        if not self.enabled:
            blocking_items = [item for item in blocking_items if item != "WAV2LIP_ENABLED=false"]
            blocking_items.insert(0, "YY_WAV2LIP_ENABLED=false")
        if not self.checkpoint_path.exists():
            blocking_items = [
                item for item in blocking_items if not item.startswith("WAV2LIP_CHECKPOINT missing:")
            ]
            blocking_items.append(f"YY_WAV2LIP_CHECKPOINT missing: {self.checkpoint_path}")
        if role_model_path:
            model = Path(role_model_path)
            if not model.exists():
                blocking_items.append(f"YY_WAV2LIP role model pkl missing: {model}")
        elif self.role_model_dir and not self.role_model_dir.exists():
            blocking_items.append(f"YY_WAV2LIP_ROLE_MODEL_DIR missing: {self.role_model_dir}")
        payload["ready"] = not blocking_items
        payload["checkpoint"] = {"path": str(self.checkpoint_path), "exists": self.checkpoint_path.exists()}
        payload["role_model_dir"] = {
            "path": str(self.role_model_dir) if self.role_model_dir else None,
            "exists": self.role_model_dir.exists() if self.role_model_dir else None,
        }
        payload["role_model"] = {
            "path": str(role_model_path) if role_model_path else None,
            "exists": Path(role_model_path).exists() if role_model_path else None,
        }
        payload["blocking_items"] = blocking_items
        return payload

    async def sync_lip(
        self,
        video_path: Path,
        audio_path: Path,
        out_dir: Path,
        *,
        role_model_path: str | Path | None = None,
    ) -> Path:
        write_json(
            out_dir / "yywav2lip_request.json",
            {
                "face_video": str(video_path),
                "audio_file": str(audio_path),
                "checkpoint": str(self.checkpoint_path),
                "role_model_path": str(role_model_path) if role_model_path else None,
            },
        )
        if self.dry_run:
            write_text(out_dir / "wav2lip_stdout.log", "dry-run yywav2lip\n")
            write_text(out_dir / "wav2lip_stderr.log", "")
            return await super().sync_lip(video_path, audio_path, out_dir)
        return await super().sync_lip(video_path, audio_path, out_dir)
