from __future__ import annotations

import importlib
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.adapters.asr import DryRunASRAdapter, FUNASR_PUNC_MODEL, FunASRAdapter, PARAFORMER_ZH_LONG_AUDIO_MODEL, WhisperAdapter
from app.adapters.base import AdapterError
from app.settings import Settings
from app.utils.files import ensure_dir, read_json, write_json, write_placeholder_binary, write_text
from app.video_remix import (
    SubtitleCue,
    _split_subtitle_sentences,
    _strip_subtitle_punctuation,
    _subtitle_speech_weight,
    _wrap_subtitle_text,
    _write_timed_subtitle_cues,
)


FIRST_SUBTITLE_START_GRACE_SECONDS = 1.0
MISSING_FIRST_SEGMENT_THRESHOLD_SECONDS = 0.75


@dataclass(frozen=True)
class SubtitleAlignmentResult:
    transcript_path: Path
    segments_path: Path
    cues: list[SubtitleCue | tuple[Path, float, float]]
    engine: str
    model: str
    status: str
    message: str


def align_video_subtitles(
    *,
    video_path: Path,
    out_dir: Path,
    settings: Settings,
    fallback_text: str = "",
) -> SubtitleAlignmentResult:
    ensure_dir(out_dir)
    audio_path = out_dir / "subtitle_audio.wav"
    _extract_audio_for_subtitles(video_path=video_path, audio_path=audio_path, settings=settings)
    adapter = _asr_adapter(settings)
    transcript_path = adapter.transcribe(audio_path=audio_path, out_dir=out_dir)
    transcript = read_json(transcript_path)
    segments = _clean_transcript_segments(transcript.get("segments", []))
    if not segments and fallback_text.strip():
        cues = _write_timed_subtitle_cues(
            fallback_text,
            work_dir=out_dir,
            output_index=1,
            duration_seconds=None,
        )
        segments = [
            {
                "start": cue.start,
                "end": cue.end,
                "text": cue.text_file.read_text(encoding="utf-8").replace("\n", ""),
                "confidence": 0.0,
            }
            for cue in cues
        ]
    else:
        segments = _ensure_first_fallback_segment(segments, fallback_text)
        cues = _write_cues_from_segments(segments, out_dir=out_dir)
    segments_path = write_json(
        out_dir / "subtitle_segments.json",
        {
            "engine": getattr(adapter, "name", settings.asr_engine),
            "model": getattr(adapter, "model", ""),
            "source_video": str(video_path),
            "source_audio": str(audio_path),
            "segments": segments,
        },
    )
    return SubtitleAlignmentResult(
        transcript_path=transcript_path,
        segments_path=segments_path,
        cues=cues,
        engine=getattr(adapter, "name", settings.asr_engine),
        model=getattr(adapter, "model", ""),
        status="completed",
        message="字幕时间轴已生成。",
    )


def _asr_adapter(settings: Settings):
    engine = (settings.asr_engine or "funasr").lower()
    if engine == "whisper":
        return WhisperAdapter(dry_run=settings.dry_run, enabled=settings.whisper_enabled)
    if engine in {"funasr", "sensevoice", "sensevoice_small"}:
        return FunASRAdapter(
            dry_run=settings.dry_run,
            enabled=settings.funasr_enabled,
            model=getattr(settings, "funasr_model", PARAFORMER_ZH_LONG_AUDIO_MODEL),
            model_dir=getattr(settings, "funasr_model_dir", None),
            device=getattr(settings, "funasr_device", "cpu"),
            vad_model=getattr(settings, "funasr_vad_model", "fsmn-vad"),
            punc_model=getattr(settings, "funasr_punc_model", FUNASR_PUNC_MODEL),
        )
    return DryRunASRAdapter()


def _extract_audio_for_subtitles(*, video_path: Path, audio_path: Path, settings: Settings) -> None:
    if audio_path.exists() and audio_path.stat().st_size > 0:
        return
    ffmpeg_path = _resolve_ffmpeg(settings.reference_ffmpeg_path)
    stdout_log = audio_path.with_name("subtitle_ffmpeg_stdout.log")
    stderr_log = audio_path.with_name("subtitle_ffmpeg_stderr.log")
    if not ffmpeg_path:
        if settings.dry_run:
            write_placeholder_binary(audio_path, f"subtitle-audio={video_path.name};reason=ffmpeg unavailable")
            write_text(stderr_log, "ffmpeg unavailable; dry-run placeholder audio used.")
            return
        raise AdapterError("本地 ffmpeg 不可用，无法从视频提取音频生成字幕。")
    command = [
        ffmpeg_path,
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        str(audio_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
    write_text(stdout_log, completed.stdout or "")
    write_text(stderr_log, completed.stderr or "")
    if completed.returncode != 0 or not audio_path.exists() or audio_path.stat().st_size == 0:
        if settings.dry_run:
            write_placeholder_binary(audio_path, f"subtitle-audio={video_path.name};reason=ffmpeg failed")
            return
        detail = (completed.stderr or completed.stdout or "").strip().splitlines()
        tail = detail[-1] if detail else f"exit {completed.returncode}"
        raise AdapterError(f"提取字幕音频失败：{tail}")


def _resolve_ffmpeg(configured_path: str | None) -> str | None:
    if configured_path:
        candidate = Path(configured_path)
        if candidate.exists() and candidate.is_file():
            return str(candidate)
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg
    try:
        imageio_ffmpeg = importlib.import_module("imageio_ffmpeg")
        return str(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:  # noqa: BLE001 - optional dependency.
        return None


def _clean_transcript_segments(raw_segments: Any) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    if not isinstance(raw_segments, list):
        return segments
    for item in raw_segments:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        try:
            start = float(item.get("start", 0.0) or 0.0)
            end = float(item.get("end", 0.0) or 0.0)
        except (TypeError, ValueError):
            continue
        if end <= start:
            end = start + max(0.6, len(text) / 6.0)
        segments.append(
            {
                "start": round(max(0.0, start), 3),
                "end": round(max(start + 0.1, end), 3),
                "text": text,
                "confidence": float(item.get("confidence", 1.0) or 1.0),
            }
        )
    return sorted(segments, key=lambda segment: (segment["start"], segment["end"]))


def _write_cues_from_segments(segments: list[dict[str, Any]], *, out_dir: Path) -> list[SubtitleCue]:
    cues: list[SubtitleCue] = []
    for index, segment in enumerate(segments, start=1):
        cue_file = out_dir / f"subtitle_asr_{index:03d}.txt"
        cue_file.write_text(_wrap_subtitle_text(str(segment["text"])), encoding="utf-8")
        start = float(segment["start"])
        if index == 1 and 0.0 < start <= FIRST_SUBTITLE_START_GRACE_SECONDS:
            start = 0.0
        cues.append(SubtitleCue(text_file=cue_file, start=start, end=float(segment["end"])))
    return cues


def _ensure_first_fallback_segment(segments: list[dict[str, Any]], fallback_text: str) -> list[dict[str, Any]]:
    if not segments or not fallback_text.strip():
        return segments
    first_segment_start = float(segments[0].get("start", 0.0) or 0.0)
    if first_segment_start < MISSING_FIRST_SEGMENT_THRESHOLD_SECONDS:
        return segments

    fallback_sentences = _split_subtitle_sentences(fallback_text, max_clause_chars=18)
    if not fallback_sentences:
        return segments
    first_fallback = fallback_sentences[0].strip()
    normalized_fallback = _strip_subtitle_punctuation(first_fallback)
    if not normalized_fallback:
        return segments

    leading_asr = _strip_subtitle_punctuation("".join(str(segment.get("text", "")) for segment in segments[:2]))
    prefix_length = min(8, len(normalized_fallback))
    if normalized_fallback[:prefix_length] and normalized_fallback[:prefix_length] in leading_asr:
        return segments

    estimated_duration = max(0.8, _subtitle_speech_weight(first_fallback) / 7.0 + 0.2)
    insert_end = round(min(first_segment_start, estimated_duration), 3)
    if insert_end <= 0:
        return segments

    inserted = {
        "start": 0.0,
        "end": insert_end,
        "text": first_fallback,
        "confidence": 0.0,
        "source": "fallback_first_sentence",
    }
    return [inserted, *segments]
