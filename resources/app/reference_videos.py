import shutil
import subprocess
import importlib
from datetime import datetime, timezone
from pathlib import Path

from app.adapters.asr import DryRunASRAdapter, FunASRAdapter, WhisperAdapter
from app.schemas import (
    AnalyzeReferenceVideoRequest,
    CreateReferenceVideoRequest,
    ReferenceVideo,
    ReferenceVideoStatus,
)
from app.settings import Settings
from app.utils.files import ensure_dir, read_json, write_json, write_placeholder_binary, write_text


class ReferenceVideoStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.projects_root = ensure_dir(settings.storage_dir / "projects")
        self.index_root = ensure_dir(settings.storage_dir / "references")

    def project_dir(self, project_id: str) -> Path:
        return ensure_dir(self.projects_root / project_id)

    def project_assets_dir(self, project_id: str) -> Path:
        return ensure_dir(self.project_dir(project_id) / "assets")

    def reference_root(self, project_id: str) -> Path:
        return ensure_dir(self.project_dir(project_id) / "references")

    def reference_dir(self, project_id: str, reference_id: str) -> Path:
        return ensure_dir(self.reference_root(project_id) / reference_id)

    def reference_file(self, project_id: str, reference_id: str) -> Path:
        return self.reference_dir(project_id, reference_id) / "reference.json"

    def index_file(self, reference_id: str) -> Path:
        return self.index_root / f"{reference_id}.json"

    def create(self, project_id: str, request: CreateReferenceVideoRequest) -> ReferenceVideo:
        stored_path, asset_id = self._store_or_select_video(project_id, request)
        reference = ReferenceVideo(
            project_id=project_id,
            title=request.title,
            asset_id=asset_id,
            original_source_path=request.source_path,
            stored_video_path=str(stored_path),
            metadata=request.metadata,
        )
        return self.save(reference)

    def save(self, reference: ReferenceVideo) -> ReferenceVideo:
        reference.updated_at = datetime.now(timezone.utc)
        payload = reference.model_dump(mode="json")
        write_json(self.reference_file(reference.project_id, reference.reference_id), payload)
        write_json(self.index_file(reference.reference_id), payload)
        return reference

    def get(self, reference_id: str) -> ReferenceVideo:
        path = self.index_file(reference_id)
        if not path.exists():
            raise KeyError(f"reference video not found: {reference_id}")
        return ReferenceVideo.model_validate(read_json(path))

    def list_for_project(self, project_id: str) -> list[ReferenceVideo]:
        root = self.reference_root(project_id)
        return [ReferenceVideo.model_validate(read_json(path)) for path in sorted(root.glob("*/reference.json"))]

    def analyze(self, reference_id: str, request: AnalyzeReferenceVideoRequest) -> ReferenceVideo:
        reference = self.get(reference_id)
        reference_dir = self.reference_dir(reference.project_id, reference.reference_id)
        try:
            video_path = Path(reference.stored_video_path)
            if not video_path.exists():
                raise FileNotFoundError(f"reference video missing: {video_path}")
            audio_path, audio_report = self._extract_audio(video_path, reference_dir, force=request.force)
            transcript_path = self._asr_adapter(request.asr_engine).transcribe(audio_path=audio_path, out_dir=reference_dir)
            reference_script_path = self._write_reference_script(reference_dir, transcript_path)
            shot_breakdown_path = self._write_shot_breakdown(reference_dir, reference, video_path)
            style_summary_path = self._write_style_summary(reference_dir, transcript_path, shot_breakdown_path)

            reference.extracted_audio_path = str(audio_path)
            reference.transcript_json = str(transcript_path)
            reference.reference_script_json = str(reference_script_path)
            reference.shot_breakdown_json = str(shot_breakdown_path)
            reference.style_summary_json = str(style_summary_path)
            reference.status = ReferenceVideoStatus.analyzed
            reference.analysis_report = {
                "audio": audio_report,
                "asr_engine": request.asr_engine or self.settings.asr_engine,
                "outputs": {
                    "transcript": str(transcript_path),
                    "reference_script": str(reference_script_path),
                    "shot_breakdown": str(shot_breakdown_path),
                    "style_summary": str(style_summary_path),
                },
            }
            return self.save(reference)
        except Exception as exc:
            reference.status = ReferenceVideoStatus.failed
            reference.analysis_report = {"error": str(exc)}
            self.save(reference)
            raise

    def analysis_payload(self, reference_id: str) -> dict[str, object]:
        reference = self.get(reference_id)
        if reference.status != ReferenceVideoStatus.analyzed:
            raise KeyError(f"reference analysis not ready: {reference_id}")
        return {
            "reference": reference.model_dump(mode="json"),
            "transcript": read_json(Path(reference.transcript_json)),
            "reference_script": read_json(Path(reference.reference_script_json)),
            "shot_breakdown": read_json(Path(reference.shot_breakdown_json)),
            "style_summary": read_json(Path(reference.style_summary_json)),
        }

    def _store_or_select_video(self, project_id: str, request: CreateReferenceVideoRequest) -> tuple[Path, str | None]:
        if request.source_path:
            source = Path(request.source_path)
            if not source.exists() or not source.is_file():
                raise FileNotFoundError(f"source reference video not found: {source}")
            asset_id = request.asset_id or f"reference_asset_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
            extension = source.suffix or ".mp4"
            target_dir = ensure_dir(self.project_assets_dir(project_id) / "reference_videos" / asset_id)
            target = target_dir / f"reference{extension}"
            shutil.copyfile(source, target)
            return target, asset_id

        if request.asset_id:
            asset = self._find_project_asset(project_id, request.asset_id)
            if asset:
                return asset, request.asset_id
            raise FileNotFoundError(f"project asset not found: {request.asset_id}")

        raise ValueError("source_path or asset_id is required")

    def _find_project_asset(self, project_id: str, asset_id: str) -> Path | None:
        root = self.project_assets_dir(project_id)
        candidate = Path(asset_id)
        if candidate.exists() and candidate.is_file():
            return candidate
        for path in sorted(root.rglob("*")) if root.exists() else []:
            if path.is_file() and (path.name == asset_id or path.stem == asset_id):
                return path
        return None

    def _extract_audio(self, video_path: Path, reference_dir: Path, *, force: bool) -> tuple[Path, dict[str, object]]:
        ensure_dir(reference_dir)
        audio_path = reference_dir / "reference_audio.wav"
        if audio_path.exists() and audio_path.stat().st_size > 0 and not force:
            return audio_path, {"status": "cached", "path": str(audio_path)}

        ffmpeg_path = _resolve_ffmpeg(self.settings.reference_ffmpeg_path)
        stdout_log = reference_dir / "ffmpeg_stdout.log"
        stderr_log = reference_dir / "ffmpeg_stderr.log"
        if ffmpeg_path:
            cmd = [
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
            try:
                completed = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
            except FileNotFoundError as exc:
                write_text(stdout_log, "")
                write_text(stderr_log, f"本地 ffmpeg 不可用，无法抽取参考视频音频：{exc}")
                if not self.settings.dry_run:
                    raise RuntimeError("本地 ffmpeg 不可用，无法从参考视频抽取音频。请安装 ffmpeg，或使用应用内置 imageio-ffmpeg。") from exc
                reason = "ffmpeg command not found; dry-run placeholder audio used"
                write_placeholder_binary(audio_path, f"reference-audio={video_path.name};reason={reason}")
                return audio_path, {"status": "dry_run_placeholder", "ffmpeg_path": ffmpeg_path, "reason": reason}
            write_text(stdout_log, completed.stdout)
            write_text(stderr_log, completed.stderr)
            if completed.returncode == 0 and audio_path.exists() and audio_path.stat().st_size > 0:
                return audio_path, {
                    "status": "ffmpeg_extracted",
                    "ffmpeg_path": ffmpeg_path,
                    "returncode": completed.returncode,
                    "path": str(audio_path),
                }
            if not self.settings.dry_run:
                raise RuntimeError(f"ffmpeg audio extraction failed: {completed.stderr or completed.stdout}")

        reason = "ffmpeg unavailable" if not ffmpeg_path else "ffmpeg failed; dry-run placeholder audio used"
        if not ffmpeg_path and not self.settings.dry_run:
            write_text(stdout_log, "")
            write_text(stderr_log, "本地 ffmpeg 不可用，无法抽取参考视频音频。")
            raise RuntimeError("本地 ffmpeg 不可用，无法从参考视频抽取音频。请安装 ffmpeg，或检查 imageio-ffmpeg 是否已随桌面版打包。")
        write_text(stdout_log, "" if not ffmpeg_path else stdout_log.read_text(encoding="utf-8"))
        if not stderr_log.exists():
            write_text(stderr_log, reason)
        write_placeholder_binary(audio_path, f"reference-audio={video_path.name};reason={reason}")
        return audio_path, {"status": "dry_run_placeholder", "ffmpeg_path": ffmpeg_path, "reason": reason}

    def _asr_adapter(self, requested_engine: str | None):
        engine = (requested_engine or self.settings.asr_engine or "dryrun").lower()
        if engine == "whisper":
            return WhisperAdapter(dry_run=self.settings.dry_run, enabled=self.settings.whisper_enabled)
        if engine == "funasr":
            return FunASRAdapter(
                dry_run=self.settings.dry_run,
                enabled=self.settings.funasr_enabled,
                model=self.settings.funasr_model,
                model_dir=self.settings.funasr_model_dir,
                device=self.settings.funasr_device,
                vad_model=self.settings.funasr_vad_model,
            )
        raise RuntimeError(f"不支持的本地语音识别引擎：{engine}。请使用 FunASR / Paraformer。")

    def _write_reference_script(self, reference_dir: Path, transcript_path: Path) -> Path:
        transcript = read_json(transcript_path)
        segments = transcript.get("segments", [])
        return write_json(
            reference_dir / "reference_script.json",
            {
                "source": "reference_video_analysis",
                "hook": segments[0]["text"] if segments else "Reference hook",
                "body_points": [segment["text"] for segment in segments[1:-1]] or ["Reference body structure"],
                "cta": segments[-1]["text"] if segments else "Reference call to action",
                "rewrite_guidance": {
                    "keep": ["opening rhythm", "three-part explanation", "clear final action"],
                    "avoid": ["copying exact wording", "using unlicensed media", "claiming source ownership"],
                },
            },
        )

    def _write_shot_breakdown(self, reference_dir: Path, reference: ReferenceVideo, video_path: Path) -> Path:
        return write_json(
            reference_dir / "shot_breakdown.json",
            {
                "reference_id": reference.reference_id,
                "video_path": str(video_path),
                "shots": [
                    {"index": 1, "start": 0.0, "end": 5.0, "type": "hook", "visual": "presenter close-up"},
                    {"index": 2, "start": 5.0, "end": 28.0, "type": "explanation", "visual": "talking head with captions"},
                    {"index": 3, "start": 28.0, "end": 45.0, "type": "cta", "visual": "direct-to-camera close"},
                ],
                "method": "dry-run heuristic shot breakdown",
            },
        )

    def _write_style_summary(self, reference_dir: Path, transcript_path: Path, shot_breakdown_path: Path) -> Path:
        transcript = read_json(transcript_path)
        shots = read_json(shot_breakdown_path).get("shots", [])
        return write_json(
            reference_dir / "style_summary.json",
            {
                "tone": "clear, direct, practical",
                "pacing": "fast hook, structured middle, concise ending",
                "caption_style": "short sentence subtitles",
                "visual_pattern": [shot["type"] for shot in shots],
                "script_length_segments": len(transcript.get("segments", [])),
                "reuse_policy": "use as structure/style reference only; do not copy exact media or wording",
            },
        )


def _resolve_ffmpeg(configured_path: str | None = None) -> str | None:
    if configured_path:
        candidate = Path(configured_path)
        if candidate.exists() and candidate.is_file():
            return str(candidate)
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg
    try:
        imageio_ffmpeg = importlib.import_module("imageio_ffmpeg")
        ffmpeg_path = str(imageio_ffmpeg.get_ffmpeg_exe())
        return ffmpeg_path if ffmpeg_path else None
    except Exception:  # noqa: BLE001 - optional desktop dependency.
        return None
