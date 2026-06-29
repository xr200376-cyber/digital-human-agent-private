from __future__ import annotations

import importlib
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.utils.files import ensure_dir, write_json


class VideoRemixError(RuntimeError):
    pass


@dataclass(frozen=True)
class VideoRemixRenderResult:
    outputs: list[Path]
    report_path: Path
    stdout_log: Path
    stderr_log: Path
    ffmpeg_path: str


@dataclass(frozen=True)
class SubtitleCue:
    text_file: Path
    start: float
    end: float


DEFAULT_SUBTITLE_STYLE = {
    "font_size": 58,
    "color": "#ffffff",
    "x": 0.5,
    "y": 0.68,
}

_SUBTITLE_PUNCTUATION_RE = re.compile(r"[，。！？、；：：“”‘’（）《》〈〉【】\[\]{}「」『』…—·,.!?;:\"'()<>`~@#$%^&*_+=|\\/\\-]")


FILTER_COMPLEX_SCRIPT_THRESHOLD = 6000


class LocalFFmpegVideoRemixEngine:
    def __init__(self, *, ffmpeg_path: str | None = None, timeout_seconds: int = 900):
        self.ffmpeg_path = _resolve_ffmpeg(ffmpeg_path)
        self.timeout_seconds = timeout_seconds
        self.subtitle_font_path = _resolve_subtitle_font()

    def render(
        self,
        *,
        main_video: Path,
        assets: list[Path],
        out_dir: Path,
        output_count: int,
        add_subtitles: bool = False,
        subtitle_text: str | None = None,
        subtitle_cues: list[SubtitleCue | tuple[Path, float, float]] | None = None,
        subtitle_style: dict[str, Any] | None = None,
        background_music: Path | None = None,
        background_music_volume: float = 0.18,
    ) -> VideoRemixRenderResult:
        if not self.ffmpeg_path:
            raise VideoRemixError("本地 ffmpeg 不可用，无法生成混剪视频。请先安装 ffmpeg 或在环境检查中配置 ffmpeg 路径。")
        if not main_video.exists() or not main_video.is_file():
            raise VideoRemixError("主视频文件不存在，无法生成混剪视频。")
        usable_assets = [path for path in assets if path.exists() and path.is_file()]
        if assets and not usable_assets:
            raise VideoRemixError("没有可用的混剪素材，无法生成混剪视频。")

        usable_background_music = background_music if background_music and background_music.exists() and background_music.is_file() else None
        if background_music and not usable_background_music:
            raise VideoRemixError("选择的背景音乐不存在，请重新选择。")

        if not usable_assets and not add_subtitles and not usable_background_music:
            raise VideoRemixError("Please choose at least one video operation: insert assets, add subtitles, or add background music.")

        outputs_dir = ensure_dir(out_dir / "outputs")
        work_dir = ensure_dir(out_dir / "work")
        stdout_log = out_dir / "ffmpeg_stdout.log"
        stderr_log = out_dir / "ffmpeg_stderr.log"
        stdout_log.write_text("", encoding="utf-8")
        stderr_log.write_text("", encoding="utf-8")
        main_video_duration = _probe_media_duration(main_video, ffmpeg_path=self.ffmpeg_path) or None
        if usable_assets and main_video_duration is None:
            raise VideoRemixError(
                "无法读取主视频时长，无法按前 8 秒和最后 3 秒生成画中画。"
                "请更换可识别的 MP4，或配置可用的 ffmpeg/ffprobe 后重试。"
            )
        normalized_subtitle_style = _normalize_subtitle_style(subtitle_style)

        outputs: list[Path] = []
        render_commands: list[list[str]] = []
        for index in range(output_count):
            output_path = outputs_dir / f"remix_{index + 1:03d}.mp4"
            rotated_assets = _rotate_assets(usable_assets, index)
            selected_assets = rotated_assets[: min(3, len(rotated_assets))]
            subtitle_file: Path | None = None
            output_subtitle_cues: list[SubtitleCue | tuple[Path, float, float]] | None = subtitle_cues
            if add_subtitles:
                subtitle_file = work_dir / f"subtitle_{index + 1:03d}.txt"
                raw_subtitle_text = subtitle_text or "数字人口播"
                subtitle_file.write_text(_wrap_subtitle_text(raw_subtitle_text), encoding="utf-8")
                if output_subtitle_cues is None:
                    output_subtitle_cues = _write_timed_subtitle_cues(
                        raw_subtitle_text,
                        work_dir=work_dir,
                        output_index=index + 1,
                        duration_seconds=main_video_duration,
                    )
            command = self._build_command(
                main_video=main_video,
                assets=selected_assets,
                output_path=output_path,
                variant_index=index,
                main_video_duration_seconds=main_video_duration,
                add_subtitles=add_subtitles,
                subtitle_text_file=subtitle_file,
                subtitle_cues=output_subtitle_cues,
                subtitle_style=normalized_subtitle_style,
                background_music=usable_background_music,
                background_music_volume=background_music_volume,
                filter_script_path=work_dir / f"filter_{index + 1:03d}.txt",
            )
            render_commands.append(command)
            self._run_command(command, stdout_log, stderr_log)
            if not output_path.exists() or output_path.stat().st_size == 0:
                raise VideoRemixError("本地 ffmpeg 已运行，但没有生成可用的混剪视频。")
            outputs.append(output_path)

        report_path = out_dir / "remix_report.json"
        write_json(
            report_path,
            {
                "status": "completed",
                "engine": "ffmpeg_local",
                "ffmpeg_path": self.ffmpeg_path,
                "main_video": str(main_video),
                "assets": [str(path) for path in usable_assets],
                "outputs": [str(path) for path in outputs],
                "output_count": output_count,
                "add_subtitles": add_subtitles,
                "subtitle_text": subtitle_text or "",
                "subtitle_style": normalized_subtitle_style,
                "background_music": str(usable_background_music) if usable_background_music else "",
                "background_music_volume": background_music_volume if usable_background_music else 0,
                "stdout_log": str(stdout_log),
                "stderr_log": str(stderr_log),
                "commands": render_commands,
                "strategy": {
                    "mode": "digital_human_head_tail_material_middle",
                    "timeline_policy": "前8秒保留口播数字人，最后3秒保留口播数字人，中间按上传顺序连续播放素材。",
                    "resolution": {"width": 1080, "height": 1920},
                    "max_assets_per_output": min(3, len(usable_assets)),
                    "head_seconds": 8.0,
                    "tail_seconds": 3.0,
                    "middle_window_seconds": max(0.0, main_video_duration - 11.0) if main_video_duration else None,
                    "background_music": bool(usable_background_music),
                },
            },
        )
        return VideoRemixRenderResult(
            outputs=outputs,
            report_path=report_path,
            stdout_log=stdout_log,
            stderr_log=stderr_log,
            ffmpeg_path=self.ffmpeg_path,
        )

    def _build_command(
        self,
        *,
        main_video: Path,
        assets: list[Path],
        output_path: Path,
        variant_index: int,
        main_video_duration_seconds: float | None = None,
        add_subtitles: bool = False,
        subtitle_text_file: Path | None = None,
        subtitle_cues: list[SubtitleCue | tuple[Path, float, float]] | None = None,
        subtitle_style: dict[str, Any] | None = None,
        background_music: Path | None = None,
        background_music_volume: float = 0.18,
        filter_script_path: Path | None = None,
    ) -> list[str]:
        input_args = ["-y", "-i", str(main_video)]
        for asset in assets:
            if _is_image(asset):
                input_args.extend(["-loop", "1", "-i", str(asset)])
            else:
                input_args.extend(["-stream_loop", "-1", "-i", str(asset)])
        background_music_index: int | None = None
        if background_music:
            background_music_index = len(assets) + 1
            input_args.extend(["-stream_loop", "-1", "-i", str(background_music)])

        filters: list[str] = [
            "[0:v]scale=1080:1920:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1[base0]"
        ]
        previous = "base0"
        overlay_slots = _middle_picture_in_picture_slots(
            len(assets),
            duration_seconds=main_video_duration_seconds,
            variant_index=variant_index,
        )
        for input_index, (_asset, slot) in enumerate(zip(assets, overlay_slots, strict=False), start=1):
            start, end = slot
            slot_seconds = max(0.0, end - start)
            filters.append(
                f"[{input_index}:v]scale=1080:1920:force_original_aspect_ratio=decrease,"
                f"pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1,"
                f"trim=duration={slot_seconds:.2f},setpts=PTS-STARTPTS+{start:.2f}/TB[cut{input_index}]"
            )
            filters.append(
                f"[{previous}][cut{input_index}]overlay=0:0:"
                f"enable='between(t,{start:.2f},{end:.2f})'[base{input_index}]"
            )
            previous = f"base{input_index}"
        if add_subtitles:
            font_option = ""
            if self.subtitle_font_path:
                font_option = f"fontfile='{_escape_drawtext_fontfile(self.subtitle_font_path)}':"
            style = _normalize_subtitle_style(subtitle_style)
            subtitle_position = (
                f"x=(w-text_w)*{style['x']:.3f}:"
                f"y=(h-text_h)*{style['y']:.3f}:"
                f"fontsize={style['font_size']}:line_spacing=10:"
                f"fontcolor={_drawtext_color(style['color'])}:"
                "borderw=4:bordercolor=0x2b2b2b:"
                "shadowx=2:shadowy=2:shadowcolor=0x000000@0.65"
            )
            cues = _normalize_subtitle_cues(subtitle_cues)
            if cues:
                for cue_index, cue in enumerate(cues, start=1):
                    label = f"vsub{cue_index}"
                    text_option = f"textfile='{_escape_drawtext_fontfile(cue.text_file)}'"
                    filters.append(
                        f"[{previous}]drawtext={font_option}{text_option}:{subtitle_position}:"
                        f"enable='between(t,{cue.start:.2f},{cue.end:.2f})'[{label}]"
                    )
                    previous = label
            else:
                text_option = "text='数字人口播'"
                if subtitle_text_file:
                    text_option = f"textfile='{_escape_drawtext_fontfile(subtitle_text_file)}'"
                filters.append(
                    f"[{previous}]drawtext={font_option}{text_option}:{subtitle_position}[vsub]"
                )
                previous = "vsub"
        filters.append(f"[{previous}]format=yuv420p[v]")
        audio_map = "0:a?"
        if background_music_index is not None:
            volume = min(max(background_music_volume, 0.0), 1.0)
            filters.append(
                f"[0:a]volume=1.0[a0];[{background_music_index}:a]volume={volume:.3f}[bgm];"
                "[a0][bgm]amix=inputs=2:duration=first:dropout_transition=2[a]"
            )
            audio_map = "[a]"

        filter_complex = ";".join(filters)
        filter_args = ["-filter_complex", filter_complex]
        if filter_script_path and len(filter_complex) > FILTER_COMPLEX_SCRIPT_THRESHOLD:
            ensure_dir(filter_script_path.parent)
            filter_script_path.write_text(filter_complex, encoding="utf-8")
            filter_args = ["-filter_complex_script", str(filter_script_path)]

        return [
            str(self.ffmpeg_path),
            *input_args,
            *filter_args,
            "-map",
            "[v]",
            "-map",
            audio_map,
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            "-shortest",
            str(output_path),
        ]

    def _run_command(self, command: list[str], stdout_log: Path, stderr_log: Path) -> None:
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise VideoRemixError("本地 ffmpeg 混剪超时，请减少素材数量或缩短主视频后重试。") from exc

        with stdout_log.open("a", encoding="utf-8") as stdout_file:
            stdout_file.write(result.stdout or "")
        with stderr_log.open("a", encoding="utf-8") as stderr_file:
            stderr_file.write(result.stderr or "")

        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip().splitlines()
            tail = detail[-1] if detail else f"exit {result.returncode}"
            raise VideoRemixError(f"本地 ffmpeg 混剪失败：{tail}")


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


def _resolve_subtitle_font() -> Path | None:
    candidates: list[Path] = []
    windir = os.environ.get("WINDIR")
    if windir:
        fonts_dir = Path(windir) / "Fonts"
        candidates.extend(
            [
                fonts_dir / "msyh.ttc",
                fonts_dir / "simhei.ttf",
                fonts_dir / "simsun.ttc",
                fonts_dir / "Deng.ttf",
            ]
        )
    candidates.extend(
        [
            Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
            Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
            Path("/System/Library/Fonts/PingFang.ttc"),
        ]
    )
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _rotate_assets(assets: list[Path], offset: int) -> list[Path]:
    if not assets:
        return []
    amount = offset % len(assets)
    return assets[amount:] + assets[:amount]


def _middle_picture_in_picture_slots(
    asset_count: int,
    *,
    duration_seconds: float | None,
    variant_index: int = 0,
    head_seconds: float = 8.0,
    tail_seconds: float = 3.0,
) -> list[tuple[float, float]]:
    """Split the material section into continuous sequential slots.

    Product rule: keep the first 8 seconds and last 3 seconds as the
    digital-human talking segment, then play uploaded materials back-to-back
    in the middle window.
    """
    if asset_count <= 0:
        return []
    if duration_seconds is not None and duration_seconds <= head_seconds + tail_seconds:
        return []
    if duration_seconds is None:
        return []

    middle_start = head_seconds
    middle_end = duration_seconds - tail_seconds
    slot_seconds = (middle_end - middle_start) / asset_count
    return [
        (middle_start + index * slot_seconds, middle_start + (index + 1) * slot_seconds)
        for index in range(asset_count)
    ]


def _is_image(path: Path) -> bool:
    return path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def _escape_drawtext(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("%", "\\%")
        .replace("\n", " ")
        .strip()
    )


def _strip_subtitle_punctuation(text: str) -> str:
    cleaned = _SUBTITLE_PUNCTUATION_RE.sub("", text or "")
    return " ".join(cleaned.split()).strip()


def _normalize_subtitle_style(style: dict[str, Any] | None) -> dict[str, Any]:
    style = style or {}
    try:
        font_size = int(style.get("font_size", DEFAULT_SUBTITLE_STYLE["font_size"]))
    except (TypeError, ValueError):
        font_size = int(DEFAULT_SUBTITLE_STYLE["font_size"])
    font_size = min(max(font_size, 20), 96)

    color = str(style.get("color", DEFAULT_SUBTITLE_STYLE["color"]) or DEFAULT_SUBTITLE_STYLE["color"]).strip()
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        color = str(DEFAULT_SUBTITLE_STYLE["color"])

    def _ratio(name: str) -> float:
        try:
            value = float(style.get(name, DEFAULT_SUBTITLE_STYLE[name]))
        except (TypeError, ValueError):
            value = float(DEFAULT_SUBTITLE_STYLE[name])
        return min(max(value, 0.0), 1.0)

    return {
        "font_size": font_size,
        "color": color.lower(),
        "x": _ratio("x"),
        "y": _ratio("y"),
    }


def _drawtext_color(color: str) -> str:
    normalized = _normalize_subtitle_style({"color": color})["color"]
    return "0x" + normalized.lstrip("#")


def _split_subtitle_sentences(text: str, max_clause_chars: int = 14) -> list[str]:
    compact = " ".join((text or "").split())
    if not compact:
        return []

    sentence_parts = [part for part in re.findall(r".+?[。！？!?]+|.+$", compact) if part.strip()]
    cues: list[str] = []
    for part in sentence_parts:
        part = part.strip()
        if len(part) <= max_clause_chars:
            cues.append(part)
            continue
        clause_parts = [clause for clause in re.findall(r".+?[，、；,;]+|.+$", part) if clause.strip()]
        for clause in clause_parts:
            cleaned = clause.strip()
            if not cleaned:
                continue
            cues.extend(_split_plain_subtitle_clause(cleaned, max_clause_chars))
    return cues or [compact]


def _split_plain_subtitle_clause(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    return [text[index : index + max_chars] for index in range(0, len(text), max_chars)]


def _write_timed_subtitle_cues(
    text: str,
    *,
    work_dir: Path,
    output_index: int,
    duration_seconds: float | None,
) -> list[SubtitleCue]:
    sentences = _split_subtitle_sentences(text)
    if not sentences:
        sentences = ["数字人口播"]
    cue_weights = [_subtitle_speech_weight(sentence) for sentence in sentences]
    estimated_duration = _estimate_subtitle_spoken_duration(cue_weights)
    usable_duration = estimated_duration
    if duration_seconds and duration_seconds > 0:
        usable_duration = min(duration_seconds, estimated_duration)
    cues: list[SubtitleCue] = []
    cursor = 0.0
    total_weight = sum(cue_weights) or float(len(sentences))
    for sentence_index, sentence in enumerate(sentences, start=1):
        weight = cue_weights[sentence_index - 1] or 1.0
        cue_duration = max(0.45, usable_duration * weight / total_weight)
        start = cursor
        end = min(usable_duration, start + cue_duration)
        if sentence_index == len(sentences):
            end = usable_duration
        cue_file = work_dir / f"subtitle_{output_index:03d}_{sentence_index:03d}.txt"
        cue_file.write_text(_single_line_subtitle_text(sentence), encoding="utf-8")
        cues.append(SubtitleCue(text_file=cue_file, start=start, end=end))
        cursor = end
    return cues


def _subtitle_speech_weight(text: str) -> float:
    weight = 0.0
    for char in text:
        if char.isspace() or char in "，。！？、；,.!?;：:":
            continue
        weight += 0.5 if char.isascii() else 1.0
    return max(weight, 1.0)


def _estimate_subtitle_spoken_duration(weights: list[float], *, chars_per_second: float = 7.0) -> float:
    total_weight = sum(weights) or 1.0
    return max(0.6 * len(weights), total_weight / chars_per_second + 0.35)


def _normalize_subtitle_cues(cues: list[SubtitleCue | tuple[Path, float, float]] | None) -> list[SubtitleCue]:
    normalized: list[SubtitleCue] = []
    for cue in cues or []:
        if isinstance(cue, SubtitleCue):
            normalized.append(cue)
        else:
            text_file, start, end = cue
            normalized.append(SubtitleCue(text_file=text_file, start=float(start), end=float(end)))
    return normalized


def _wrap_subtitle_text(text: str, max_chars: int = 14) -> str:
    compact = _strip_subtitle_punctuation(text)
    if len(compact) <= max_chars:
        return compact
    punctuation = "，。！？、；,.!?; "
    lines: list[str] = []
    remaining = compact
    while len(remaining) > max_chars:
        window = remaining[: max_chars + 1]
        min_break = max(6, max_chars // 2)
        break_points = [
            index + 1
            for index, char in enumerate(window)
            if char in punctuation and index + 1 >= min_break
        ]
        cut = break_points[-1] if break_points else max_chars
        lines.append(remaining[:cut].strip())
        remaining = remaining[cut:].lstrip()
    if remaining.strip():
        lines.append(remaining.strip())
    return "\n".join(lines)


def _single_line_subtitle_text(text: str) -> str:
    return _strip_subtitle_punctuation(text)


def _subtitle_y_offset(line_count: int) -> int:
    return 260 + min(max(line_count, 1), 5) * 100


def _subtitle_line_count(path: Path | None) -> int:
    if not path or not path.exists():
        return 1
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return 1
    return max(1, len(lines))


_FFMPEG_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")


def _probe_media_duration(path: Path, *, ffmpeg_path: str | None = None) -> float | None:
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        try:
            result = subprocess.run(
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(path),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            result = None
        if result and result.returncode == 0:
            try:
                duration = float((result.stdout or "").strip())
            except ValueError:
                duration = 0.0
            if duration > 0:
                return duration

    ffmpeg = ffmpeg_path or _resolve_ffmpeg()
    if not ffmpeg:
        return None
    try:
        result = subprocess.run(
            [str(ffmpeg), "-hide_banner", "-i", str(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return _parse_ffmpeg_duration((result.stderr or "") + "\n" + (result.stdout or ""))


def _parse_ffmpeg_duration(output: str) -> float | None:
    match = _FFMPEG_DURATION_RE.search(output or "")
    if not match:
        return None
    hours = int(match.group(1))
    minutes = int(match.group(2))
    seconds = float(match.group(3))
    duration = hours * 3600 + minutes * 60 + seconds
    return duration if duration > 0 else None


def _escape_drawtext_fontfile(path: Path) -> str:
    return str(path).replace("\\", "/").replace(":", "\\:")
