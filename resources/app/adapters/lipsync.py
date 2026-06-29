import asyncio
import os
import shutil
import sys
from pathlib import Path

from app import vendor
from app.adapters.base import AdapterError, LipSyncAdapter
from app.utils.files import ensure_dir, write_placeholder_binary


def _with_pythonpath(source_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(source_root) if not existing else str(source_root) + os.pathsep + existing
    return env


def _require_file(path: Path, *, label: str, env_var: str) -> Path:
    if not path.exists():
        raise AdapterError(f"{label} not found at {path}. Download/configure it and set {env_var}.")
    return path


def _decode_output(stdout: bytes, stderr: bytes) -> str:
    text = stderr.decode(errors="ignore").strip() or stdout.decode(errors="ignore").strip()
    return text or "no process output"


def _yaml_quote(value: Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


class LatentSyncAdapter(LipSyncAdapter):
    name = "latentsync"

    def __init__(
        self,
        cli_path: str | None,
        dry_run: bool = True,
        timeout_seconds: float = 900.0,
        ckpt_path: str | None = None,
        config_path: str | None = None,
        inference_steps: int = 20,
        guidance_scale: float = 1.5,
        enable_deepcache: bool = False,
    ):
        super().__init__(dry_run=dry_run)
        self.cli_path = cli_path
        self.timeout_seconds = timeout_seconds
        self.ckpt_path = Path(ckpt_path) if ckpt_path else None
        self.config_path = Path(config_path) if config_path else None
        self.inference_steps = inference_steps
        self.guidance_scale = guidance_scale
        self.enable_deepcache = enable_deepcache

    def available(self) -> bool:
        if self.dry_run:
            return False
        if self.cli_path and Path(self.cli_path).exists():
            return True
        return vendor.vendor_project_path("latentsync") is not None

    def _source_root(self) -> Path:
        if self.cli_path:
            cli = Path(self.cli_path).resolve()
            if cli.exists():
                return cli.parent.parent if cli.parent.name == "scripts" else cli.parent
        root = vendor.vendor_project_path("latentsync", required=True)
        assert root is not None
        return root

    def _command(self, video_path: Path, audio_path: Path, out_path: Path, out_dir: Path) -> tuple[list[str], Path]:
        source_root = self._source_root()
        script_path = source_root / "scripts" / "inference.py"
        _require_file(script_path, label="LatentSync inference script", env_var="LATENTSYNC_SOURCE_DIR")

        config_path = self.config_path or source_root / "configs" / "unet" / "stage2_512.yaml"
        ckpt_path = self.ckpt_path or source_root / "checkpoints" / "latentsync_unet.pt"
        _require_file(config_path, label="LatentSync UNet config", env_var="LATENTSYNC_CONFIG_PATH")
        _require_file(ckpt_path, label="LatentSync checkpoint", env_var="LATENTSYNC_CKPT_PATH")

        cmd = [
            sys.executable,
            "-m",
            "scripts.inference",
            "--unet_config_path",
            str(config_path),
            "--inference_ckpt_path",
            str(ckpt_path),
            "--inference_steps",
            str(self.inference_steps),
            "--guidance_scale",
            str(self.guidance_scale),
            "--video_path",
            str(video_path),
            "--audio_path",
            str(audio_path),
            "--video_out_path",
            str(out_path),
            "--temp_dir",
            str(out_dir / "latentsync_temp"),
        ]
        if self.enable_deepcache:
            cmd.append("--enable_deepcache")
        return cmd, source_root

    async def sync_lip(self, video_path: Path, audio_path: Path, out_dir: Path) -> Path:
        ensure_dir(out_dir)
        out_path = out_dir / "lip_synced.mp4"
        if self.dry_run:
            return write_placeholder_binary(out_path, f"latentsync-video={video_path.name};audio={audio_path.name}")
        self.require_available()
        cmd, source_root = self._command(video_path, audio_path, out_path, out_dir)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(source_root),
            env=_with_pythonpath(source_root),
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout_seconds)
        if proc.returncode != 0:
            raise AdapterError(f"LatentSync failed: {_decode_output(stdout, stderr)}")
        if not out_path.exists():
            raise AdapterError("LatentSync finished but expected output file was not created")
        return out_path


class MuseTalkAdapter(LipSyncAdapter):
    name = "musetalk"

    def __init__(
        self,
        cli_path: str | None,
        dry_run: bool = True,
        timeout_seconds: float = 600.0,
        model_dir: str | None = None,
        version: str = "v15",
        ffmpeg_path: str | None = None,
    ):
        super().__init__(dry_run=dry_run)
        self.cli_path = cli_path
        self.timeout_seconds = timeout_seconds
        self.model_dir = Path(model_dir) if model_dir else None
        self.version = self._normalize_version(version)
        self.ffmpeg_path = ffmpeg_path

    def available(self) -> bool:
        if self.dry_run:
            return False
        if self.cli_path and Path(self.cli_path).exists():
            return True
        return vendor.vendor_project_path("musetalk") is not None

    @staticmethod
    def _normalize_version(version: str) -> str:
        normalized = version.lower().replace(".", "")
        return "v15" if normalized in {"v15", "v150"} else "v1"

    def _source_root(self) -> Path:
        if self.cli_path:
            cli = Path(self.cli_path).resolve()
            if cli.exists():
                return cli.parent.parent if cli.parent.name == "scripts" else cli.parent
        root = vendor.vendor_project_path("musetalk", required=True)
        assert root is not None
        return root

    def _model_dir(self, source_root: Path) -> Path:
        if self.model_dir:
            return self.model_dir
        folder = "musetalkV15" if self.version == "v15" else "musetalk"
        return source_root / "models" / folder

    def _write_inference_config(self, video_path: Path, audio_path: Path, out_dir: Path) -> Path:
        config_path = out_dir / "musetalk_inference.yaml"
        config_text = "\n".join(
            [
                "task_0:",
                f" video_path: {_yaml_quote(video_path)}",
                f" audio_path: {_yaml_quote(audio_path)}",
                ' result_name: "lip_synced.mp4"',
                "",
            ]
        )
        config_path.write_text(config_text, encoding="utf-8")
        return config_path

    def _command(self, video_path: Path, audio_path: Path, out_dir: Path) -> tuple[list[str], Path, Path]:
        source_root = self._source_root()
        script_path = source_root / "scripts" / "inference.py"
        _require_file(script_path, label="MuseTalk inference script", env_var="MUSETALK_SOURCE_DIR")

        model_dir = self._model_dir(source_root)
        unet_model_path = model_dir / ("unet.pth" if self.version == "v15" else "pytorch_model.bin")
        unet_config = model_dir / "musetalk.json"
        _require_file(unet_model_path, label="MuseTalk UNet weights", env_var="MUSETALK_MODEL_DIR")
        _require_file(unet_config, label="MuseTalk UNet config", env_var="MUSETALK_MODEL_DIR")

        config_path = self._write_inference_config(video_path, audio_path, out_dir)
        cmd = [
            sys.executable,
            "-m",
            "scripts.inference",
            "--inference_config",
            str(config_path),
            "--result_dir",
            str(out_dir),
            "--unet_model_path",
            str(unet_model_path),
            "--unet_config",
            str(unet_config),
            "--version",
            self.version,
        ]
        if self.ffmpeg_path:
            cmd.extend(["--ffmpeg_path", self.ffmpeg_path])
        expected_output = out_dir / self.version / "lip_synced.mp4"
        return cmd, source_root, expected_output

    async def sync_lip(self, video_path: Path, audio_path: Path, out_dir: Path) -> Path:
        ensure_dir(out_dir)
        out_path = out_dir / "lip_synced.mp4"
        if self.dry_run:
            return write_placeholder_binary(out_path, f"musetalk-video={video_path.name};audio={audio_path.name}")
        self.require_available()
        cmd, source_root, expected_output = self._command(video_path, audio_path, out_dir)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(source_root),
            env=_with_pythonpath(source_root),
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout_seconds)
        if proc.returncode != 0:
            raise AdapterError(f"MuseTalk failed: {_decode_output(stdout, stderr)}")
        if expected_output.exists() and expected_output != out_path:
            if out_path.exists():
                out_path.unlink()
            shutil.move(str(expected_output), str(out_path))
        if not out_path.exists():
            raise AdapterError("MuseTalk finished but expected output file was not created")
        return out_path
