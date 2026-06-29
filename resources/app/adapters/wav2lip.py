import asyncio
import os
import sys
from pathlib import Path
from typing import Any

from app.adapters.base import AdapterError, LipSyncAdapter
from app.utils.files import ensure_dir, write_placeholder_binary, write_text


def _env_with_pythonpath(source_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(source_root) if not existing else str(source_root) + os.pathsep + existing
    return env


def _decode(stdout: bytes, stderr: bytes) -> str:
    text = stderr.decode(errors="ignore").strip() or stdout.decode(errors="ignore").strip()
    return text or "no process output"


class Wav2LipAdapter(LipSyncAdapter):
    name = "wav2lip"

    def __init__(
        self,
        *,
        source_root: str | Path = Path("third_party/Wav2Lip"),
        checkpoint_path: str | Path = Path("checkpoints/wav2lip.pth"),
        python_executable: str | None = None,
        timeout_seconds: float = 600.0,
        dry_run: bool = True,
        enabled: bool = True,
    ):
        super().__init__(dry_run=dry_run)
        self.source_root = Path(source_root)
        self.checkpoint_path = Path(checkpoint_path)
        self.python_executable = python_executable or sys.executable
        self.timeout_seconds = timeout_seconds
        self.enabled = enabled

    def _inference_script(self) -> Path:
        root_script = self.source_root / "inference.py"
        scripts_script = self.source_root / "scripts" / "inference.py"
        return root_script if root_script.exists() else scripts_script

    def readiness(self) -> dict[str, Any]:
        script = self._inference_script()
        blocking_items: list[str] = []
        if not self.enabled:
            blocking_items.append("WAV2LIP_ENABLED=false")
        if not self.source_root.exists():
            blocking_items.append(f"WAV2LIP source missing: {self.source_root}")
        if not script.exists():
            blocking_items.append(f"Wav2Lip inference script missing: {script}")
        if not self.checkpoint_path.exists():
            blocking_items.append(f"WAV2LIP_CHECKPOINT missing: {self.checkpoint_path}")
        return {
            "engine": self.name,
            "enabled": self.enabled,
            "ready": not blocking_items,
            "source": {"path": str(self.source_root), "exists": self.source_root.exists()},
            "inference_script": {"path": str(script), "exists": script.exists()},
            "checkpoint": {"path": str(self.checkpoint_path), "exists": self.checkpoint_path.exists()},
            "blocking_items": blocking_items,
        }

    def available(self) -> bool:
        return self.dry_run or bool(self.readiness()["ready"])

    def _command(self, video_path: Path, audio_path: Path, out_path: Path) -> list[str]:
        script = self._inference_script()
        return [
            self.python_executable,
            str(script),
            "--checkpoint_path",
            str(self.checkpoint_path),
            "--face",
            str(video_path),
            "--audio",
            str(audio_path),
            "--outfile",
            str(out_path),
        ]

    async def sync_lip(self, video_path: Path, audio_path: Path, out_dir: Path) -> Path:
        ensure_dir(out_dir)
        out_path = out_dir / "lip_synced.mp4"
        stdout_log = out_dir / "wav2lip_stdout.log"
        stderr_log = out_dir / "wav2lip_stderr.log"
        if self.dry_run:
            write_text(stdout_log, "dry-run wav2lip\n")
            write_text(stderr_log, "")
            return write_placeholder_binary(out_path, f"wav2lip-video={video_path.name};audio={audio_path.name}")

        readiness = self.readiness()
        if not readiness["ready"]:
            write_text(stdout_log, "")
            write_text(stderr_log, "\n".join(readiness["blocking_items"]))
            raise AdapterError("Wav2Lip unavailable: " + "; ".join(readiness["blocking_items"]))

        cmd = self._command(video_path, audio_path, out_path)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self.source_root),
            env=_env_with_pythonpath(self.source_root),
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout_seconds)
        write_text(stdout_log, stdout.decode(errors="ignore"))
        write_text(stderr_log, stderr.decode(errors="ignore"))
        if proc.returncode != 0:
            raise AdapterError(f"Wav2Lip failed: {_decode(stdout, stderr)}")
        if not out_path.exists():
            raise AdapterError("Wav2Lip finished but expected lip_synced.mp4 was not created")
        return out_path
