from abc import ABC, abstractmethod
import builtins
from contextlib import contextmanager, redirect_stderr, redirect_stdout
import importlib
import importlib.util
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

from app.adapters.base import AdapterError
from app.utils.files import ensure_dir, write_json

PARAFORMER_ZH_LONG_AUDIO_MODEL = "iic/speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-pytorch"
FUNASR_PUNC_MODEL = "ct-punc"


class BaseASRAdapter(ABC):
    name = "base"

    def __init__(self, *, dry_run: bool = True, enabled: bool = True):
        self.dry_run = dry_run
        self.enabled = enabled

    @abstractmethod
    def transcribe(self, *, audio_path: Path, out_dir: Path) -> Path:
        """Return transcript.json path."""

    def readiness(self) -> dict[str, Any]:
        blocking_items = [] if self.enabled else [f"{self.name.upper()}_ENABLED=false"]
        return {"engine": self.name, "ready": self.enabled, "blocking_items": blocking_items}


class DryRunASRAdapter(BaseASRAdapter):
    name = "dryrun"

    def __init__(self):
        super().__init__(dry_run=True, enabled=True)

    def transcribe(self, *, audio_path: Path, out_dir: Path) -> Path:
        ensure_dir(out_dir)
        return write_json(
            out_dir / "transcript.json",
            {
                "engine": self.name,
                "audio_path": str(audio_path),
                "language": "zh-CN",
                "duration_seconds": 45,
                "segments": [
                    {
                        "start": 0.0,
                        "end": 6.0,
                        "text": "开场用一个明确的问题抓住注意力。",
                        "confidence": 1.0,
                    },
                    {
                        "start": 6.0,
                        "end": 28.0,
                        "text": "中段用三点结构解释卖点、风险和解决方案。",
                        "confidence": 1.0,
                    },
                    {
                        "start": 28.0,
                        "end": 45.0,
                        "text": "结尾给出行动建议和发布平台适配提示。",
                        "confidence": 1.0,
                    },
                ],
            },
        )


class WhisperAdapter(BaseASRAdapter):
    name = "whisper"

    def __init__(self, *, dry_run: bool = True, enabled: bool = False):
        super().__init__(dry_run=dry_run, enabled=enabled and not dry_run)

    def transcribe(self, *, audio_path: Path, out_dir: Path) -> Path:
        raise AdapterError("WhisperAdapter is a Sprint 15 placeholder. Configure real Whisper before use.")


class FunASRAdapter(BaseASRAdapter):
    name = "funasr"

    def __init__(
        self,
        *,
        dry_run: bool = True,
        enabled: bool = False,
        model: str = PARAFORMER_ZH_LONG_AUDIO_MODEL,
        model_dir: str | None = None,
        device: str = "cpu",
        vad_model: str = "fsmn-vad",
        punc_model: str = FUNASR_PUNC_MODEL,
    ):
        super().__init__(dry_run=dry_run, enabled=enabled and not dry_run)
        self.model = model or PARAFORMER_ZH_LONG_AUDIO_MODEL
        self.model_dir = model_dir or ""
        self.device = device or "cpu"
        self.vad_model = vad_model or ""
        self.punc_model = punc_model or ""

    def transcribe(self, *, audio_path: Path, out_dir: Path) -> Path:
        ensure_dir(out_dir)
        if self.dry_run:
            return DryRunASRAdapter().transcribe(audio_path=audio_path, out_dir=out_dir)
        readiness = self.readiness()
        if not readiness["ready"]:
            raise AdapterError("本地 FunASR 字幕模型不可用：" + "，".join(readiness["blocking_items"]))
        if not audio_path.exists() or audio_path.stat().st_size == 0:
            raise AdapterError("待识别音频不存在或为空，无法生成字幕。")

        if self.model_dir:
            ensure_dir(Path(self.model_dir))
            os.environ.setdefault("MODELSCOPE_CACHE", self.model_dir)
            os.environ.setdefault("HF_HOME", self.model_dir)
            os.environ.setdefault("FUNASR_CACHE_DIR", self.model_dir)

        _ensure_ffmpeg_on_path()
        try:
            from funasr import AutoModel  # type: ignore
        except Exception as exc:  # noqa: BLE001 - optional dependency.
            raise AdapterError("未安装 FunASR，请先安装 funasr 后再使用本地字幕识别。") from exc

        _ensure_funasr_runtime_compat()
        model_kwargs: dict[str, Any] = {
            "model": self.model,
            "device": self.device,
        }
        if self.vad_model:
            model_kwargs.update(
                {
                    "vad_model": self.vad_model,
                    "vad_kwargs": {"max_single_segment_time": 30000},
                }
            )
        if self.punc_model:
            model_kwargs["punc_model"] = self.punc_model
        try:
            audio_for_asr = _copy_audio_to_funasr_safe_temp(audio_path)
            with _suppress_funasr_console_output():
                try:
                    model = AutoModel(**model_kwargs)
                except NameError as exc:
                    if not _is_missing_load_seg_dict_error(exc):
                        raise
                    _ensure_funasr_runtime_compat()
                    model = AutoModel(**model_kwargs)
                try:
                    result = _generate_with_funasr(model, audio_for_asr)
                except NameError as exc:
                    if not _is_missing_load_seg_dict_error(exc):
                        raise
                    _ensure_funasr_runtime_compat()
                    result = _generate_with_funasr(model, audio_for_asr)
        except FileNotFoundError as exc:
            raise AdapterError(
                "FunASR 调用本机音频依赖失败：系统找不到必要文件。"
                "请确认 ffmpeg 可用，或安装/打包 imageio-ffmpeg 后重启后端。"
            ) from exc
        except Exception as exc:  # noqa: BLE001 - model/runtime errors should be surfaced clearly.
            raise AdapterError(f"FunASR 识别失败：{type(exc).__name__}: {exc}") from exc

        segments = _normalize_funasr_segments(result)
        if not segments:
            text = _extract_funasr_text(result)
            segments = [{"start": 0.0, "end": max(1.0, len(text) / 6.0), "text": text or "未识别到清晰语音", "confidence": 0.0}]
        return write_json(
            out_dir / "transcript.json",
            {
                "engine": self.name,
                "model": self.model,
                "audio_path": str(audio_path),
                "language": "auto",
                "segments": segments,
            },
        )

    def readiness(self) -> dict[str, Any]:
        blockers: list[str] = []
        if self.dry_run:
            return {
                "engine": self.name,
                "ready": True,
                "model": self.model,
                "device": self.device,
                "punc_model": self.punc_model,
                "blocking_items": [],
            }
        if not self.enabled:
            blockers.append("FUNASR_ENABLED=false")
        if not importlib.util.find_spec("funasr"):
            blockers.append("未安装 funasr")
        if self.model_dir:
            model_dir = Path(self.model_dir)
            try:
                repo_root = Path.cwd().resolve()
                if model_dir.resolve().is_relative_to(repo_root):
                    blockers.append("FUNASR_MODEL_DIR 不能放在项目仓库内，避免模型权重被误打包或提交")
            except OSError:
                blockers.append("FUNASR_MODEL_DIR 路径不可访问")
        return {
            "engine": self.name,
            "ready": not blockers,
            "model": self.model,
            "model_dir": self.model_dir,
            "device": self.device,
            "punc_model": self.punc_model,
            "blocking_items": blockers,
        }


def _generate_with_funasr(model: Any, audio_path: Path) -> Any:
    kwargs = {
        "input": str(audio_path),
        "cache": {},
        "language": "auto",
        "use_itn": True,
        "batch_size_s": 60,
        "merge_vad": True,
        "merge_length_s": 15,
        "sentence_timestamp": True,
    }
    try:
        return model.generate(**kwargs)
    except TypeError:
        kwargs.pop("sentence_timestamp", None)
        return model.generate(**kwargs)


def _copy_audio_to_funasr_safe_temp(audio_path: Path) -> Path:
    """Copy audio to an ASCII temp path because some Windows ASR stacks reject CJK paths."""

    temp_root = Path(tempfile.mkdtemp(prefix="aivo_funasr_"))
    safe_audio = temp_root / "input.wav"
    shutil.copyfile(audio_path, safe_audio)
    return safe_audio


@contextmanager
def _suppress_funasr_console_output():
    """Prevent FunASR/tqdm progress writes from breaking hidden Windows desktop backends."""

    try:
        with open(os.devnull, "w", encoding="utf-8") as sink:
            with redirect_stdout(sink), redirect_stderr(sink):
                yield
    except OSError:
        yield


def _is_missing_load_seg_dict_error(exc: BaseException) -> bool:
    return isinstance(exc, NameError) and "load_seg_dict" in str(exc)


def _ensure_funasr_runtime_compat() -> None:
    setattr(builtins, "load_seg_dict", _funasr_load_seg_dict)
    for module_name in (
        "funasr.models.paraformer.model",
        "funasr.models.bicif_paraformer.model",
        "funasr.models.contextual_paraformer.model",
        "funasr.models.seaco_paraformer.model",
    ):
        try:
            module = importlib.import_module(module_name)
        except Exception:  # noqa: BLE001 - optional FunASR submodule may be unavailable.
            continue
        if not hasattr(module, "load_seg_dict"):
            setattr(module, "load_seg_dict", _funasr_load_seg_dict)
        for value in vars(module).values():
            if hasattr(value, "__globals__") and "load_seg_dict" not in value.__globals__:
                value.__globals__["load_seg_dict"] = _funasr_load_seg_dict
            if isinstance(value, type) and hasattr(value, "generate_hotwords_list"):
                _patch_funasr_hotword_method(value)
            for method_name in ("generate", "inference", "inference_export"):
                method = getattr(value, method_name, None)
                globals_dict = getattr(method, "__globals__", None)
                if globals_dict is not None and "load_seg_dict" not in globals_dict:
                    globals_dict["load_seg_dict"] = _funasr_load_seg_dict


def _patch_funasr_hotword_method(model_class: type) -> None:
    if getattr(model_class, "_aivo_hotword_compat_patched", False):
        return
    original = getattr(model_class, "generate_hotwords_list", None)
    if not callable(original):
        return

    def generate_hotwords_list_compat(self: Any, hotword_list_or_file: Any, tokenizer: Any = None, frontend: Any = None) -> Any:
        if hotword_list_or_file is None:
            return None
        if isinstance(hotword_list_or_file, str) and not hotword_list_or_file.strip():
            return None
        try:
            return original(self, hotword_list_or_file, tokenizer=tokenizer, frontend=frontend)
        except NameError as exc:
            if "load_seg_dict" not in str(exc):
                raise
            globals_dict = getattr(original, "__globals__", None)
            if globals_dict is None:
                raise
            globals_dict["load_seg_dict"] = _funasr_load_seg_dict
            return original(self, hotword_list_or_file, tokenizer=tokenizer, frontend=frontend)

    setattr(model_class, "_aivo_original_generate_hotwords_list", original)
    setattr(model_class, "generate_hotwords_list", generate_hotwords_list_compat)
    setattr(model_class, "_aivo_hotword_compat_patched", True)


def _funasr_load_seg_dict(seg_dict_file: str) -> dict[str, str]:
    seg_dict: dict[str, str] = {}
    with open(seg_dict_file, "r", encoding="utf8") as file:
        for line in file:
            parts = line.strip().split()
            if not parts:
                continue
            seg_dict[parts[0]] = " ".join(parts[1:])
    return seg_dict


def _ensure_ffmpeg_on_path() -> str | None:
    if shutil.which("ffmpeg"):
        return shutil.which("ffmpeg")
    try:
        imageio_ffmpeg = importlib.import_module("imageio_ffmpeg")
        ffmpeg_path = Path(str(imageio_ffmpeg.get_ffmpeg_exe()))
    except Exception:  # noqa: BLE001 - optional dependency.
        return None
    if not ffmpeg_path.exists():
        return None
    ffmpeg_dir = _ensure_ffmpeg_shim(ffmpeg_path)
    current_path = os.environ.get("PATH", "")
    path_parts = [part for part in current_path.split(os.pathsep) if part]
    if not any(Path(part).resolve() == Path(ffmpeg_dir).resolve() for part in path_parts if Path(part).exists()):
        os.environ["PATH"] = ffmpeg_dir + os.pathsep + current_path
    return str(ffmpeg_path)


def _ensure_ffmpeg_shim(ffmpeg_path: Path) -> str:
    if ffmpeg_path.name.lower() in {"ffmpeg.exe", "ffmpeg"}:
        return str(ffmpeg_path.parent)
    shim_root = Path(os.environ.get("AIVO_RUNTIME_BIN_DIR", Path.cwd() / "storage" / "runtime_bin"))
    ensure_dir(shim_root)
    shim_path = shim_root / "ffmpeg.cmd"
    content = f'@echo off\r\n"{ffmpeg_path}" %*\r\n'
    if not shim_path.exists() or shim_path.read_text(encoding="utf-8", errors="ignore") != content:
        shim_path.write_text(content, encoding="utf-8")
    return str(shim_root)


def _normalize_funasr_segments(result: Any) -> list[dict[str, Any]]:
    payloads = result if isinstance(result, list) else [result]
    segments: list[dict[str, Any]] = []
    cursor = 0.0
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        for key in ("sentence_info", "sentences", "segments"):
            items = payload.get(key)
            if isinstance(items, list):
                for item in items:
                    segment = _normalize_funasr_segment(item)
                    if segment:
                        segments.append(segment)
        if segments:
            continue
        timestamp_segments = _segments_from_timestamp_payload(payload, cursor)
        if timestamp_segments:
            segments.extend(timestamp_segments)
            cursor = segments[-1]["end"]
    return _dedupe_and_sort_segments(segments)


def _normalize_funasr_segment(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    text = str(item.get("text") or item.get("sentence") or "").strip()
    if not text:
        return None
    start = _timestamp_to_seconds(item.get("start", item.get("begin", item.get("start_time"))))
    end = _timestamp_to_seconds(item.get("end", item.get("finish", item.get("end_time"))))
    if end <= start:
        end = start + max(0.6, len(text) / 6.0)
    return {
        "start": round(start, 3),
        "end": round(end, 3),
        "text": text,
        "confidence": float(item.get("confidence", item.get("score", 1.0)) or 1.0),
    }


def _segments_from_timestamp_payload(payload: dict[str, Any], cursor: float) -> list[dict[str, Any]]:
    text = str(payload.get("text") or "").strip()
    timestamps = payload.get("timestamp")
    if not text or not isinstance(timestamps, list) or not timestamps:
        return []
    start = cursor
    end = cursor
    first = timestamps[0]
    last = timestamps[-1]
    if isinstance(first, (list, tuple)) and first:
        start = _timestamp_to_seconds(first[0])
    if isinstance(last, (list, tuple)) and len(last) >= 2:
        end = _timestamp_to_seconds(last[1])
    if end <= start:
        end = start + max(0.6, len(text) / 6.0)
    return [{"start": round(start, 3), "end": round(end, 3), "text": text, "confidence": 1.0}]


def _timestamp_to_seconds(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number > 1000:
        return number / 1000.0
    return number


def _dedupe_and_sort_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    seen: set[tuple[float, float, str]] = set()
    for segment in sorted(segments, key=lambda item: (float(item["start"]), float(item["end"]))):
        key = (float(segment["start"]), float(segment["end"]), str(segment["text"]))
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(segment)
    return cleaned


def _extract_funasr_text(result: Any) -> str:
    payloads = result if isinstance(result, list) else [result]
    texts: list[str] = []
    for payload in payloads:
        if isinstance(payload, dict) and payload.get("text"):
            texts.append(str(payload["text"]).strip())
    return " ".join(text for text in texts if text)
