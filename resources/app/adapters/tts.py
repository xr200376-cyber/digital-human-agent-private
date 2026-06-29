from dataclasses import dataclass
import importlib
from pathlib import Path
import shutil
import subprocess
from typing import Any

from app.schemas import VoiceProfile
from app.utils.files import read_json, write_json, write_placeholder_binary


@dataclass(frozen=True)
class TTSResult:
    audio_path: Path
    segments_path: Path
    metadata_path: Path


class BaseTTSAdapter:
    name = "base"

    async def synthesize(self, *, script_json: Path, voice_profile: VoiceProfile, out_dir: Path) -> TTSResult:
        raise NotImplementedError


class DryRunTTSAdapter(BaseTTSAdapter):
    name = "dryrun"

    async def synthesize(self, *, script_json: Path, voice_profile: VoiceProfile, out_dir: Path) -> TTSResult:
        data = read_json(script_json)
        options = _voice_options(data)
        audio_path = write_placeholder_binary(out_dir / "voice.wav", f"tts={voice_profile.voice_profile_id}")
        segments_path = write_json(
            out_dir / "voice_segments.json",
            {
                "voice_profile_id": voice_profile.voice_profile_id,
                "voice_style": options["voice_style"],
                "speech_rate": options["speech_rate"],
                "segments": [{"start": 0, "end": 3, "text": "dry-run synthetic voice"}],
            },
        )
        metadata_path = write_json(
            out_dir / "voice_metadata.json",
            {
                "engine": self.name,
                "voice_profile_id": voice_profile.voice_profile_id,
                "voice_source_type": voice_profile.voice_source_type,
                "script_json": str(script_json),
                "voice_style": options["voice_style"],
                "speech_rate": options["speech_rate"],
                "readable": False,
                "reason": "dry-run placeholder audio; real TTS engine not configured",
            },
        )
        return TTSResult(audio_path=audio_path, segments_path=segments_path, metadata_path=metadata_path)


class EdgeTTSAdapter(BaseTTSAdapter):
    name = "edge"

    def __init__(self, default_voice: str | None = None):
        self.default_voice = default_voice or "zh-CN-XiaoxiaoNeural"

    async def synthesize(self, *, script_json: Path, voice_profile: VoiceProfile, out_dir: Path) -> TTSResult:
        data = read_json(script_json)
        text, segments = _script_text_and_segments(data)
        options = _voice_options(data)
        edge_rate = _edge_rate(options["speech_rate"])
        voice_name = _voice_name(voice_profile, self.default_voice)
        audio_path = out_dir / "voice.wav"
        temp_audio = out_dir / "voice_edge_source.mp3"

        try:
            edge_tts = importlib.import_module("edge_tts")
        except ImportError as exc:
            raise RuntimeError("Edge TTS 未安装。请先安装 edge-tts，或在桌面设置里选择其他真实 TTS。") from exc

        communicator = edge_tts.Communicate(text, voice_name, rate=edge_rate)
        edge_error: str | None = None
        try:
            await communicator.save(str(temp_audio))
            conversion = self._convert_to_wav(temp_audio, audio_path)
        except Exception as exc:
            edge_error = f"{type(exc).__name__}: {exc}"
            conversion = _synthesize_with_windows_sapi(text, audio_path)
            conversion["edge_error"] = edge_error
        if not audio_path.exists() or audio_path.stat().st_size == 0:
            if temp_audio.exists():
                shutil.copyfile(temp_audio, audio_path)
                conversion = {
                    "converted": False,
                    "ffmpeg_used": False,
                    "edge_error": edge_error,
                    "reason": "Edge TTS produced audio, but WAV conversion output was empty; copied source bytes to voice.wav.",
                }
            else:
                raise RuntimeError(f"Edge TTS 生成失败，Windows 备用语音也没有生成音频：{edge_error}")
        try:
            temp_audio.unlink()
        except OSError:
            pass

        segments_path = write_json(
            out_dir / "voice_segments.json",
            {
                "voice_profile_id": voice_profile.voice_profile_id,
                "engine": self.name,
                "voice_name": voice_name,
                "voice_style": options["voice_style"],
                "speech_rate": options["speech_rate"],
                "edge_rate": edge_rate,
                "segments": segments,
            },
        )
        metadata_path = write_json(
            out_dir / "voice_metadata.json",
            {
                "engine": self.name,
                "voice_profile_id": voice_profile.voice_profile_id,
                "voice_source_type": voice_profile.voice_source_type,
                "voice_name": voice_name,
                "script_json": str(script_json),
                "voice_style": options["voice_style"],
                "speech_rate": options["speech_rate"],
                "edge_rate": edge_rate,
                "readable": audio_path.exists() and audio_path.stat().st_size > 0 and bool(conversion.get("converted", False)),
                "conversion": conversion,
            },
        )
        return TTSResult(audio_path=audio_path, segments_path=segments_path, metadata_path=metadata_path)

    def _convert_to_wav(self, source_path: Path, output_path: Path) -> dict[str, Any]:
        stdout_path = output_path.parent / "tts_ffmpeg_stdout.log"
        stderr_path = output_path.parent / "tts_ffmpeg_stderr.log"
        ffmpeg = _find_ffmpeg()
        if not ffmpeg:
            shutil.copyfile(source_path, output_path)
            stdout_path.write_text("", encoding="utf-8")
            stderr_path.write_text("ffmpeg unavailable; Edge TTS source audio copied to voice.wav\n", encoding="utf-8")
            return {
                "converted": False,
                "ffmpeg_used": False,
                "stdout_log": str(stdout_path),
                "stderr_log": str(stderr_path),
                "reason": "ffmpeg unavailable; voice.wav may contain Edge TTS source audio bytes.",
            }

        command = [
            str(ffmpeg),
            "-y",
            "-i",
            str(source_path),
            "-ac",
            "1",
            "-ar",
            "16000",
            str(output_path),
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
        stdout_path.write_text(result.stdout, encoding="utf-8")
        stderr_path.write_text(result.stderr, encoding="utf-8")
        if result.returncode != 0:
            shutil.copyfile(source_path, output_path)
            return {
                "converted": False,
                "ffmpeg_used": True,
                "stdout_log": str(stdout_path),
                "stderr_log": str(stderr_path),
                "reason": f"ffmpeg conversion failed with exit code {result.returncode}; copied source audio bytes.",
            }
        return {
            "converted": True,
            "ffmpeg_used": True,
            "stdout_log": str(stdout_path),
            "stderr_log": str(stderr_path),
        }


class HTTPTTSAdapter(BaseTTSAdapter):
    name = "http"

    def __init__(self, base_url: str, timeout_seconds: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    async def synthesize(self, *, script_json: Path, voice_profile: VoiceProfile, out_dir: Path) -> TTSResult:
        raise NotImplementedError("Configure a CosyVoice/IndexTTS/GPT-SoVITS compatible HTTP endpoint first.")


def _script_text_and_segments(data: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    raw_segments = data.get("segments") or []
    segments: list[dict[str, Any]] = []
    if isinstance(raw_segments, list):
        for index, segment in enumerate(raw_segments):
            if not isinstance(segment, dict):
                continue
            text = str(segment.get("text") or "").strip()
            if not text:
                continue
            segments.append(
                {
                    "start": segment.get("start", index * 3),
                    "end": segment.get("end", (index + 1) * 3),
                    "text": text,
                }
            )
    text_parts = [str(segment["text"]).strip() for segment in segments if str(segment.get("text", "")).strip()]
    if not text_parts:
        for key in ("hook", "body", "cta", "title"):
            value = str(data.get(key) or "").strip()
            if value:
                text_parts.append(value)
        if text_parts:
            segments = [{"start": 0, "end": max(3, len(" ".join(text_parts)) // 12), "text": " ".join(text_parts)}]
    text = "\n".join(text_parts).strip() or "你好，欢迎使用 Aivo 数字人口播工作台。"
    return text, segments or [{"start": 0, "end": 3, "text": text}]


def _voice_options(data: dict[str, Any] | None) -> dict[str, Any]:
    data = data if isinstance(data, dict) else {}
    nested = data.get("voice_options") if isinstance(data.get("voice_options"), dict) else {}
    voice_style = _normalize_voice_style(data.get("voice_style") or nested.get("voice_style"))
    speech_rate = _normalize_speech_rate(data.get("speech_rate") or nested.get("speech_rate"))
    return {"voice_style": voice_style, "speech_rate": speech_rate}


def _normalize_voice_style(value: Any) -> str:
    raw = str(value or "natural").strip().lower()
    return {
        "自然": "natural",
        "natural": "natural",
        "热情": "warm",
        "warm": "warm",
        "enthusiastic": "warm",
        "沉稳": "calm",
        "calm": "calm",
        "steady": "calm",
    }.get(raw, "natural")


def _normalize_speech_rate(value: Any) -> float:
    try:
        rate = float(value)
    except (TypeError, ValueError):
        return 1.0
    return round(max(0.5, min(2.0, rate)), 2)


def _edge_rate(speech_rate: float) -> str:
    percent = int(round((_normalize_speech_rate(speech_rate) - 1.0) * 100))
    return f"{percent:+d}%"


def _voice_name(voice_profile: VoiceProfile, default_voice: str) -> str:
    metadata = voice_profile.metadata if isinstance(voice_profile.metadata, dict) else {}
    return str(
        metadata.get("edge_voice")
        or metadata.get("voice_name")
        or metadata.get("voice_id")
        or metadata.get("speaker")
        or default_voice
    )


def _find_ffmpeg() -> str | None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return ffmpeg
    try:
        imageio_ffmpeg = importlib.import_module("imageio_ffmpeg")
        return str(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        return None


def _synthesize_with_windows_sapi(text: str, output_path: Path) -> dict[str, Any]:
    stdout_path = output_path.parent / "tts_sapi_stdout.log"
    stderr_path = output_path.parent / "tts_sapi_stderr.log"
    text_path = output_path.parent / "tts_sapi_text.txt"
    powershell = shutil.which("powershell") or shutil.which("powershell.exe")
    if not powershell:
        return {
            "converted": False,
            "ffmpeg_used": False,
            "fallback_engine": "windows_sapi",
            "stdout_log": str(stdout_path),
            "stderr_log": str(stderr_path),
            "reason": "PowerShell not found; Windows SAPI fallback unavailable.",
        }

    spoken_text = _sapi_safe_text(text)
    result = _run_windows_sapi(powershell, spoken_text, text_path, output_path, stdout_path, stderr_path)
    readable = result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 1024
    retried_with_default = False
    if not readable and spoken_text != _DEFAULT_SAPI_TEXT:
        retried_with_default = True
        result = _run_windows_sapi(powershell, _DEFAULT_SAPI_TEXT, text_path, output_path, stdout_path, stderr_path)
        readable = result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 1024
    return {
        "converted": readable,
        "ffmpeg_used": False,
        "fallback_engine": "windows_sapi",
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
        "retried_with_default_text": retried_with_default,
        "reason": None if readable else f"Windows SAPI fallback failed or produced an empty WAV; exit code {result.returncode}.",
    }


def _run_windows_sapi(
    powershell: str,
    text: str,
    text_path: Path,
    output_path: Path,
    stdout_path: Path,
    stderr_path: Path,
):
    text_path.write_text(text, encoding="utf-8")
    script = (
        "Add-Type -AssemblyName System.Speech; "
        f"$text = Get-Content -LiteralPath {_ps_quote(str(text_path))} -Raw -Encoding UTF8; "
        "$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$speaker.SetOutputToWaveFile({_ps_quote(str(output_path))}); "
        "$speaker.Speak($text); "
        "$speaker.Dispose();"
    )
    result = subprocess.run(
        [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    stdout_path.write_text(result.stdout, encoding="utf-8")
    stderr_path.write_text(result.stderr, encoding="utf-8")
    return result


_DEFAULT_SAPI_TEXT = "你好，这是 Aivo 数字人口播工作台的备用语音测试。"


def _sapi_safe_text(text: str) -> str:
    stripped = " ".join(str(text or "").split())
    meaningful = [char for char in stripped if char.isalnum() or "\u4e00" <= char <= "\u9fff"]
    if len(meaningful) < 2:
        return _DEFAULT_SAPI_TEXT
    return stripped


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
