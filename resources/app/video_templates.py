from __future__ import annotations

import base64
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.schemas import VideoTemplate
from app.utils.files import ensure_dir, read_json, write_json, write_placeholder_binary


@dataclass(frozen=True)
class TemplateAssemblyResult:
    final_video: Path
    cover_image: Path
    template_report: Path
    template_id: str
    ffmpeg_used: bool


_COVER_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/ax"
    "k6H0AAAAASUVORK5CYII="
)


BUILT_IN_VIDEO_TEMPLATES: dict[str, VideoTemplate] = {
    "clean_talking_head": VideoTemplate(
        template_id="clean_talking_head",
        name="干净口播",
        description="简洁竖屏口播版式，字幕清晰，适合通用数字人视频。",
        resolution={"width": 1080, "height": 1920},
        subtitle_style={
            "position": "lower_third",
            "font_size": 54,
            "font_weight": "bold",
            "text_color": "#FFFFFF",
            "stroke_color": "#111827",
            "stroke_width": 6,
            "max_lines": 2,
        },
        title_style={
            "position": "top_safe",
            "font_size": 66,
            "font_weight": "bold",
            "text_color": "#111827",
            "background_color": "#F8FAFC",
        },
        bgm={"enabled": False, "asset_id": None, "volume": 0.0},
        intro={"enabled": False, "duration_seconds": 0},
        outro={"enabled": False, "duration_seconds": 0},
        safe_area={"top": 140, "bottom": 220, "left": 72, "right": 72},
        cover_text={"mode": "title", "max_chars": 28, "position": "center"},
        metadata={"platform_fit": ["douyin", "tiktok", "youtube_shorts"]},
    ),
    "xiaohongshu_knowledge": VideoTemplate(
        template_id="xiaohongshu_knowledge",
        name="小红书知识分享",
        description="知识笔记风格，突出标题、干净字幕和轻量 BGM 占位。",
        resolution={"width": 1080, "height": 1920},
        subtitle_style={
            "position": "lower_third",
            "font_size": 48,
            "font_weight": "semibold",
            "text_color": "#1F2937",
            "background_color": "#FFF7ED",
            "stroke_width": 0,
            "max_lines": 2,
        },
        title_style={
            "position": "top_card",
            "font_size": 62,
            "font_weight": "bold",
            "text_color": "#111827",
            "background_color": "#FFFFFF",
        },
        bgm={"enabled": True, "asset_id": "local_optional_bgm", "volume": 0.18},
        intro={"enabled": True, "duration_seconds": 1.0, "style": "title_flash"},
        outro={"enabled": True, "duration_seconds": 1.0, "style": "summary_cta"},
        safe_area={"top": 180, "bottom": 260, "left": 64, "right": 64},
        cover_text={"mode": "title_plus_hook", "max_chars": 34, "position": "center"},
        metadata={"platform_fit": ["xiaohongshu"]},
    ),
    "douyin_sales": VideoTemplate(
        template_id="douyin_sales",
        name="抖音销售口播",
        description="节奏更快的销售口播模板，顶部大标题和强引导结尾。",
        resolution={"width": 1080, "height": 1920},
        subtitle_style={
            "position": "bottom_safe",
            "font_size": 58,
            "font_weight": "bold",
            "text_color": "#FFFFFF",
            "stroke_color": "#000000",
            "stroke_width": 8,
            "max_lines": 2,
        },
        title_style={
            "position": "top_safe",
            "font_size": 72,
            "font_weight": "heavy",
            "text_color": "#FFFFFF",
            "background_color": "#DC2626",
        },
        bgm={"enabled": True, "asset_id": "local_optional_sales_bgm", "volume": 0.22},
        intro={"enabled": True, "duration_seconds": 0.6, "style": "hook_pop"},
        outro={"enabled": True, "duration_seconds": 1.2, "style": "cta_card"},
        safe_area={"top": 150, "bottom": 250, "left": 56, "right": 56},
        cover_text={"mode": "sales_title", "max_chars": 24, "position": "center"},
        metadata={"platform_fit": ["douyin", "tiktok"]},
    ),
    "corporate_explainer": VideoTemplate(
        template_id="corporate_explainer",
        name="企业讲解",
        description="克制清晰的讲解风格，适合品牌、培训和内部知识视频。",
        resolution={"width": 1080, "height": 1920},
        subtitle_style={
            "position": "lower_third",
            "font_size": 46,
            "font_weight": "medium",
            "text_color": "#0F172A",
            "background_color": "#E2E8F0",
            "stroke_width": 0,
            "max_lines": 2,
        },
        title_style={
            "position": "top_safe",
            "font_size": 56,
            "font_weight": "bold",
            "text_color": "#0F172A",
            "background_color": "#F8FAFC",
        },
        bgm={"enabled": False, "asset_id": None, "volume": 0.0},
        intro={"enabled": True, "duration_seconds": 1.0, "style": "brand_title"},
        outro={"enabled": True, "duration_seconds": 1.0, "style": "brand_summary"},
        safe_area={"top": 160, "bottom": 230, "left": 80, "right": 80},
        cover_text={"mode": "business_title", "max_chars": 30, "position": "center"},
        metadata={"platform_fit": ["wechat_channels", "youtube_shorts"]},
    ),
}


def list_video_templates() -> list[VideoTemplate]:
    return list(BUILT_IN_VIDEO_TEMPLATES.values())


def get_video_template(template_id: str | None) -> VideoTemplate:
    resolved_id = template_id or "clean_talking_head"
    try:
        return BUILT_IN_VIDEO_TEMPLATES[resolved_id]
    except KeyError as exc:
        allowed = ", ".join(sorted(BUILT_IN_VIDEO_TEMPLATES))
        raise ValueError(f"unknown video_template_id: {resolved_id}; allowed: {allowed}") from exc


class TemplateAssemblyEngine:
    def __init__(self, *, dry_run: bool = True, ffmpeg_path: str | None = None, timeout_seconds: int = 300):
        self.dry_run = dry_run
        self.ffmpeg_path = ffmpeg_path or shutil.which("ffmpeg")
        self.timeout_seconds = timeout_seconds

    def assemble(
        self,
        *,
        source_video: Path,
        script_json: Path,
        template: VideoTemplate,
        out_dir: Path,
    ) -> TemplateAssemblyResult:
        ensure_dir(out_dir)
        final_video = out_dir / "final.mp4"
        cover_image = out_dir / "cover.png"
        report_path = out_dir / "template_report.json"
        stdout_path = out_dir / "template_ffmpeg_stdout.log"
        stderr_path = out_dir / "template_ffmpeg_stderr.log"

        ffmpeg_used = False
        ffmpeg_status: dict[str, Any] = {
            "available": bool(self.ffmpeg_path),
            "used": False,
            "stdout_log": str(stdout_path),
            "stderr_log": str(stderr_path),
        }

        if self.dry_run:
            write_placeholder_binary(final_video, f"template={template.template_id};source={source_video}")
            stdout_path.write_text("", encoding="utf-8")
            stderr_path.write_text("dry-run: ffmpeg not invoked\n", encoding="utf-8")
        elif self.ffmpeg_path:
            ffmpeg_used = self._run_ffmpeg(source_video, final_video, template, stdout_path, stderr_path)
            ffmpeg_status["used"] = ffmpeg_used
        elif source_video.exists():
            shutil.copyfile(source_video, final_video)
            stdout_path.write_text("", encoding="utf-8")
            stderr_path.write_text("ffmpeg unavailable; copied source video\n", encoding="utf-8")
        else:
            raise FileNotFoundError(f"source video not found: {source_video}")

        cover_image.write_bytes(_COVER_PNG_BYTES)
        script = read_json(script_json)
        segments = script.get("segments") or []
        title = str(script.get("title") or script.get("hook") or "Digital human video")
        hook = str(segments[0].get("text") if segments else script.get("body") or title)
        final_readable = (not self.dry_run) and final_video.exists() and final_video.stat().st_size > 0
        warnings = ["dry-run media may not be ffprobe-readable"] if self.dry_run else []
        if (not self.dry_run) and (not ffmpeg_used) and source_video.exists():
            warnings.append("ffmpeg unavailable; copied source video without template transforms")
        report = {
            "template_id": template.template_id,
            "template_name": template.name,
            "description": template.description,
            "resolution": template.resolution,
            "subtitle_style": template.subtitle_style,
            "title_style": template.title_style,
            "bgm": template.bgm,
            "intro": template.intro,
            "outro": template.outro,
            "safe_area": template.safe_area,
            "cover_text": template.cover_text,
            "cover": {
                "path": str(cover_image),
                "title": title[: template.cover_text.get("max_chars", 28)],
                "hook": hook[: template.cover_text.get("max_chars", 28)],
            },
            "source_video": str(source_video),
            "script_json": str(script_json),
            "final_video": str(final_video),
            "ffmpeg": ffmpeg_status,
            "readable": final_readable,
            "warnings": warnings,
        }
        write_json(report_path, report)
        return TemplateAssemblyResult(
            final_video=final_video,
            cover_image=cover_image,
            template_report=report_path,
            template_id=template.template_id,
            ffmpeg_used=ffmpeg_used,
        )

    def _run_ffmpeg(
        self,
        source_video: Path,
        final_video: Path,
        template: VideoTemplate,
        stdout_path: Path,
        stderr_path: Path,
    ) -> bool:
        width = template.resolution.get("width", 1080)
        height = template.resolution.get("height", 1920)
        command = [
            str(self.ffmpeg_path),
            "-y",
            "-i",
            str(source_video),
            "-vf",
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(final_video),
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=self.timeout_seconds, check=False)
        stdout_path.write_text(result.stdout, encoding="utf-8")
        stderr_path.write_text(result.stderr, encoding="utf-8")
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg template assembly failed with exit code {result.returncode}")
        return True
