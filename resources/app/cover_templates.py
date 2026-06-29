from __future__ import annotations

import importlib
import math
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.utils.files import ensure_dir, write_json


class CoverGenerationError(RuntimeError):
    pass


@dataclass(frozen=True)
class CoverGenerationResult:
    cover_image: Path
    report_path: Path
    first_frame: Path
    template_id: str


COVER_TEMPLATES: list[dict[str, Any]] = [
    {
        "template_id": "yellow_title_top",
        "name": "黄字顶部标题",
        "description": "参考用户封面图：人物背景上方大黄字黑描边。",
        "accent": "#ffe100",
        "accent_2": "#111111",
        "text_color": "#ffe100",
        "shadow": "#050505",
        "position": "top",
        "preview": "标题在顶部",
        "preview_image": "/static/cover-templates/yellow-title-top.png",
    },
    {
        "template_id": "yellow_title_middle",
        "name": "黄字中部标题",
        "description": "参考用户封面图：人物背景中下部大黄字黑描边。",
        "accent": "#ffe100",
        "accent_2": "#111111",
        "text_color": "#ffe100",
        "shadow": "#050505",
        "position": "middle",
        "preview": "标题在中下部",
        "preview_image": "/static/cover-templates/yellow-title-middle.png",
    },
]


def list_cover_templates() -> list[dict[str, Any]]:
    return COVER_TEMPLATES


def get_cover_template(template_id: str | None) -> dict[str, Any]:
    resolved_id = template_id or COVER_TEMPLATES[0]["template_id"]
    for template in COVER_TEMPLATES:
        if template["template_id"] == resolved_id:
            return template
    allowed = ", ".join(template["template_id"] for template in COVER_TEMPLATES)
    raise CoverGenerationError(f"未知封面模板：{resolved_id}，可选：{allowed}")


def generate_cover_from_video(
    *,
    video_path: Path,
    out_dir: Path,
    template: dict[str, Any],
    keyword_text: str,
    ffmpeg_path: str | None = None,
) -> CoverGenerationResult:
    if not video_path.exists() or not video_path.is_file():
        raise CoverGenerationError("视频文件不存在，无法生成封面。")
    resolved_ffmpeg = _resolve_ffmpeg(ffmpeg_path)
    if not resolved_ffmpeg:
        raise CoverGenerationError("本地 ffmpeg 不可用，无法从视频首帧生成封面。")

    ensure_dir(out_dir)
    frame_path = out_dir / "cover_first_frame.png"
    cover_path = out_dir / "cover.png"
    report_path = out_dir / "cover_report.json"
    stdout_log = out_dir / "cover_ffmpeg_stdout.log"
    stderr_log = out_dir / "cover_ffmpeg_stderr.log"

    command = [
        str(resolved_ffmpeg),
        "-y",
        "-i",
        str(video_path),
        "-vf",
        "select=eq(n\\,0),scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
        "-frames:v",
        "1",
        str(frame_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
    stdout_log.write_text(result.stdout or "", encoding="utf-8")
    stderr_log.write_text(result.stderr or "", encoding="utf-8")
    if result.returncode != 0 or not frame_path.exists() or frame_path.stat().st_size == 0:
        tail = (result.stderr or result.stdout or f"exit {result.returncode}").strip().splitlines()
        raise CoverGenerationError(f"首帧提取失败：{tail[-1] if tail else '未知错误'}")

    _compose_cover(first_frame=frame_path, output_path=cover_path, template=template, keyword_text=keyword_text)
    write_json(
        report_path,
        {
            "status": "completed",
            "template_id": template["template_id"],
            "template_name": template["name"],
            "keyword_text": keyword_text,
            "source_video": str(video_path),
            "first_frame": str(frame_path),
            "cover_image": str(cover_path),
            "ffmpeg_path": str(resolved_ffmpeg),
            "ffmpeg_stdout": str(stdout_log),
            "ffmpeg_stderr": str(stderr_log),
            "source_policy": "first_frame_plus_keyword_text",
        },
    )
    return CoverGenerationResult(
        cover_image=cover_path,
        report_path=report_path,
        first_frame=frame_path,
        template_id=str(template["template_id"]),
    )


def _compose_cover(*, first_frame: Path, output_path: Path, template: dict[str, Any], keyword_text: str) -> None:
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageOps
    except Exception as exc:  # noqa: BLE001 - optional runtime dependency.
        raise CoverGenerationError("Pillow 不可用，无法合成封面文字。") from exc

    image = Image.open(first_frame).convert("RGB")
    canvas = ImageOps.fit(image, (1080, 1920), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    accent = _hex_to_rgb(template["accent"])
    accent_2 = _hex_to_rgb(template["accent_2"])
    text_color = _hex_to_rgb(template["text_color"])
    shadow = _hex_to_rgb(template["shadow"])

    _draw_template_frame(draw, template, accent, accent_2)

    keyword = _normalize_keyword(keyword_text)
    title_font = _font(132)
    lines = _wrap_keyword(keyword, max_chars=7, max_lines=2)
    block = _text_block(lines, title_font)
    x = max(40, math.floor((1080 - block[0]) / 2))
    y = _template_y(template["position"], block[1])
    text_y = y
    for line in lines:
        line_width = max(1, title_font.getbbox(line)[2] - title_font.getbbox(line)[0])
        line_x = max(32, math.floor((1080 - line_width) / 2))
        draw.text(
            (line_x + 4, text_y + 6),
            line,
            font=title_font,
            fill=(0, 0, 0, 210),
            stroke_width=9,
            stroke_fill=(*shadow, 255),
        )
        draw.text(
            (line_x, text_y),
            line,
            font=title_font,
            fill=(*text_color, 255),
            stroke_width=8,
            stroke_fill=(*shadow, 255),
        )
        text_y += 142

    canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")
    canvas.save(output_path, "PNG")


def _draw_template_frame(draw: Any, template: dict[str, Any], accent: tuple[int, int, int], accent_2: tuple[int, int, int]) -> None:
    position = str(template.get("position") or "top")
    if position == "top":
        draw.rectangle((0, 0, 1080, 560), fill=(0, 0, 0, 54))
        return
    draw.rectangle((0, 860, 1080, 1420), fill=(0, 0, 0, 42))


def _template_y(position: str, block_height: int) -> int:
    if position == "top":
        return 150
    if position == "middle":
        return 1000
    if position == "bottom":
        return max(1220, 1560 - block_height)
    return max(700, math.floor((1920 - block_height) / 2))


def _wrap_keyword(text: str, *, max_chars: int, max_lines: int) -> list[str]:
    compact = _normalize_keyword(text)
    if len(compact) <= max_chars:
        return [compact]
    lines = [compact[index : index + max_chars] for index in range(0, len(compact), max_chars)]
    return lines[:max_lines]


def _normalize_keyword(text: str) -> str:
    compact = " ".join(str(text or "").replace("\n", " ").split()).strip(" ，。,.")
    return compact[:24] or "数字人口播"


def _text_block(lines: list[str], font: Any) -> tuple[int, int]:
    widths = []
    for line in lines:
        bbox = font.getbbox(line)
        widths.append(max(1, bbox[2] - bbox[0]))
    return max(widths) if widths else 1, max(1, len(lines) * 142)


def _font(size: int) -> Any:
    from PIL import ImageFont

    candidates = [
        Path("C:/Windows/Fonts/msyhbd.ttc"),
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    text = value.strip().lstrip("#")
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)


def _resolve_ffmpeg(configured_path: str | None = None) -> str | None:
    if configured_path:
        candidate = Path(configured_path)
        return str(candidate) if candidate.exists() and candidate.is_file() else None
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg
    try:
        imageio_ffmpeg = importlib.import_module("imageio_ffmpeg")
        ffmpeg_path = str(imageio_ffmpeg.get_ffmpeg_exe())
        return ffmpeg_path if ffmpeg_path else None
    except Exception:  # noqa: BLE001 - optional dependency.
        return None
