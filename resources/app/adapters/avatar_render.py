from dataclasses import dataclass
import base64
import importlib
from pathlib import Path
import shutil
import subprocess
from typing import Any

from app.utils.files import write_json, write_placeholder_binary


@dataclass(frozen=True)
class AvatarRenderResult:
    video_path: Path
    metadata_path: Path
    report_path: Path
    engine_used: str
    fallback_used: list[str]


class BaseAvatarRenderAdapter:
    name = "base"

    async def render_base_video(
        self,
        *,
        avatar_image_path: Path,
        voice_audio_path: Path,
        output_path: Path,
        render_profile: str,
        options: dict,
        task_dir: Path,
    ) -> AvatarRenderResult:
        raise NotImplementedError


class DryRunAvatarRenderAdapter(BaseAvatarRenderAdapter):
    name = "static"

    async def render_base_video(
        self,
        *,
        avatar_image_path: Path,
        voice_audio_path: Path,
        output_path: Path,
        render_profile: str,
        options: dict,
        task_dir: Path,
    ) -> AvatarRenderResult:
        fallback_used = list(options.get("fallback_used", []))
        duration_seconds = _safe_duration(options.get("duration_seconds") or options.get("target_duration_seconds") or 45)
        ffmpeg_status = _render_static_video_with_ffmpeg(
            avatar_image_path=avatar_image_path,
            output_path=output_path,
            duration_seconds=duration_seconds,
            task_dir=task_dir,
        )
        if not ffmpeg_status.get("readable") and (not output_path.exists() or output_path.stat().st_size == 0):
            write_placeholder_binary(output_path, f"avatar-base={avatar_image_path.name};voice={voice_audio_path.name}")

        metadata_path = write_json(
            task_dir / "avatar_render_metadata.json",
            {
                "engine": self.name,
                "render_profile": render_profile,
                "avatar_image_path": str(avatar_image_path),
                "voice_audio_path": str(voice_audio_path),
                "output_path": str(output_path),
                "duration_seconds": duration_seconds,
                "ffmpeg": ffmpeg_status,
            },
        )
        warnings = []
        if ffmpeg_status.get("readable"):
            warnings.append("static avatar base video generated; real facial motion renderer not configured")
        else:
            warnings.append("placeholder video; ffmpeg static MP4 generation unavailable or failed")
            if ffmpeg_status.get("reason"):
                warnings.append(str(ffmpeg_status["reason"]))
        report_path = write_json(
            task_dir / "avatar_render_report.json",
            {
                "status": "completed",
                "engine_used": self.name,
                "fallback_used": fallback_used,
                "readable": bool(ffmpeg_status.get("readable")),
                "duration_seconds": duration_seconds,
                "ffmpeg": ffmpeg_status,
                "warnings": warnings,
            },
        )
        return AvatarRenderResult(
            video_path=output_path,
            metadata_path=metadata_path,
            report_path=report_path,
            engine_used=self.name,
            fallback_used=fallback_used,
        )


class LivePortraitAvatarRenderAdapter(BaseAvatarRenderAdapter):
    name = "liveportrait"


class SadTalkerAvatarRenderAdapter(BaseAvatarRenderAdapter):
    name = "sadtalker"


class DuixHTTPAvatarRenderAdapter(BaseAvatarRenderAdapter):
    name = "duix_http"


def _render_static_video_with_ffmpeg(
    *,
    avatar_image_path: Path,
    output_path: Path,
    duration_seconds: int,
    task_dir: Path,
) -> dict[str, Any]:
    stdout_path = task_dir / "avatar_stdout.log"
    stderr_path = task_dir / "avatar_stderr.log"
    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        stdout_path.write_text("", encoding="utf-8")
        stderr_path.write_text("ffmpeg unavailable; static avatar MP4 not generated\n", encoding="utf-8")
        return {
            "available": False,
            "used": False,
            "readable": False,
            "duration_seconds": duration_seconds,
            "stdout_log": str(stdout_path),
            "stderr_log": str(stderr_path),
            "reason": "ffmpeg unavailable",
        }

    frame_path = _prepare_static_frame(avatar_image_path, task_dir)
    command = [
        str(ffmpeg),
        "-y",
        "-loop",
        "1",
        "-i",
        str(frame_path),
        "-t",
        str(duration_seconds),
        "-r",
        "25",
        "-vf",
        "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-tune",
        "stillimage",
        "-pix_fmt",
        "yuv420p",
        str(output_path),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
    except Exception as exc:
        stdout_path.write_text("", encoding="utf-8")
        stderr_path.write_text(str(exc), encoding="utf-8")
        return {
            "available": True,
            "used": True,
            "readable": False,
            "duration_seconds": duration_seconds,
            "stdout_log": str(stdout_path),
            "stderr_log": str(stderr_path),
            "reason": str(exc),
        }
    stdout_path.write_text(result.stdout, encoding="utf-8")
    stderr_path.write_text(result.stderr, encoding="utf-8")
    readable = result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0
    return {
        "available": True,
        "used": True,
        "readable": readable,
        "duration_seconds": duration_seconds,
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
        "reason": None if readable else f"ffmpeg exited with code {result.returncode}",
    }


def _prepare_static_frame(avatar_image_path: Path, task_dir: Path) -> Path:
    frame_path = task_dir / "avatar_static_frame.png"
    try:
        Image = importlib.import_module("PIL.Image")
        ImageDraw = importlib.import_module("PIL.ImageDraw")
        image = None
        if avatar_image_path.exists():
            try:
                image = Image.open(avatar_image_path).convert("RGB")
            except Exception:
                image = None
        canvas = Image.new("RGB", (1080, 1920), color=(245, 247, 250))
        if image is not None:
            image.thumbnail((920, 1320))
            x = (1080 - image.width) // 2
            y = max(160, (1920 - image.height) // 2)
            canvas.paste(image, (x, y))
        else:
            _draw_fallback_avatar(canvas, ImageDraw)
        canvas.save(frame_path)
        return frame_path
    except Exception:
        frame_path.write_bytes(_FALLBACK_PNG_BYTES)
        return frame_path


def _draw_fallback_avatar(canvas, ImageDraw) -> None:
    draw = ImageDraw.Draw(canvas)
    draw.ellipse((300, 260, 780, 740), fill=(32, 129, 226), outline=(15, 23, 42), width=8)
    draw.rectangle((250, 760, 830, 1360), fill=(20, 184, 166), outline=(15, 23, 42), width=8)
    draw.ellipse((425, 430, 455, 460), fill=(15, 23, 42))
    draw.ellipse((625, 430, 655, 460), fill=(15, 23, 42))
    draw.arc((450, 500, 630, 620), 0, 180, fill=(15, 23, 42), width=8)


def _safe_duration(value: Any) -> int:
    try:
        return max(1, min(180, int(float(value))))
    except (TypeError, ValueError):
        return 45


def _find_ffmpeg() -> str | None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return ffmpeg
    try:
        imageio_ffmpeg = importlib.import_module("imageio_ffmpeg")
        return str(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        return None


_FALLBACK_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/ax"
    "k6H0AAAAASUVORK5CYII="
)
