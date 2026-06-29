from __future__ import annotations

import asyncio
import base64
import importlib
import json
import posixpath
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.adapters.base import AdapterError
from app.adapters.cloud_lipsync import PixVerseLipSyncAdapter, SyncSoLipSyncAdapter
from app.adapters.cloud_video_render import FalVideoRenderAdapter
from app.adapters.cloud_voice import AliyunBailianVoiceAdapter
from app.adapters.hifly import HiflyDigitalHumanAdapter, extract_hifly_id
from app.adapters.omnihuman import OmniHumanVideoAdapter
from app.adapters.object_storage import build_object_storage_adapter, source_voice_sample_key
from app.artifacts import write_artifact_manifest
from app.audit import append_audit_event
from app.digital_humans import DigitalHumanStore
from app.schemas import (
    CloudSourceVideoRenderRequest,
    CreateVoiceProfileRequest,
    HiflySourceVideoAvatarRequest,
    HiflySourceVideoGenerateRequest,
    HiflySourceVideoVoiceRequest,
    SourceVideoUploadRequest,
    SourceVideoVoiceProfileRequest,
    StepResult,
    TaskStatus,
    VideoTask,
    VoiceSourceType,
)
from app.settings import Settings
from app.store import TaskStore
from app.utils.files import ensure_dir, read_json, write_json, write_placeholder_binary, write_text


class SourceVideoWorkflowError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


class SourceVideoWorkflow:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.digital_store = DigitalHumanStore(settings)
        self.ffmpeg_path = _find_ffmpeg(settings.reference_ffmpeg_path)
        self.ffprobe_path = _sibling_ffprobe(self.ffmpeg_path) or shutil.which("ffprobe")

    def source_dir(self, digital_human_id: str) -> Path:
        profile = self.digital_store.get(digital_human_id)
        return ensure_dir(
            self.settings.storage_dir
            / "projects"
            / profile.project_id
            / "digital_humans"
            / digital_human_id
            / "source_video"
        )

    def source_video_path(self, digital_human_id: str) -> Path:
        return self.source_dir(digital_human_id) / "source_video.mp4"

    def hifly_adapter(self) -> HiflyDigitalHumanAdapter:
        return HiflyDigitalHumanAdapter(
            dry_run=self.settings.dry_run,
            enabled=self.settings.hifly_enabled or self.settings.cloud_video_provider == "hifly",
            base_url=self.settings.hifly_base_url,
            token=self.settings.hifly_token,
            required=self.settings.hifly_required,
            poll_interval_seconds=self.settings.hifly_poll_interval_seconds,
            timeout_seconds=self.settings.hifly_timeout_seconds,
        )

    def upload_source_video(self, digital_human_id: str, request: SourceVideoUploadRequest) -> dict[str, Any]:
        profile = self.digital_store.get(digital_human_id)
        source_dir = self.source_dir(digital_human_id)
        source_path = source_dir / "source_video.mp4"
        try:
            payload = base64.b64decode(request.content_base64, validate=True)
        except Exception as exc:  # noqa: BLE001 - API should report the invalid payload.
            raise SourceVideoWorkflowError(f"source_video.mp4 base64 解码失败：{exc}") from exc
        source_path.write_bytes(payload)
        report = self.validate_source_video(digital_human_id)

        metadata = dict(profile.metadata or {})
        metadata["source_video"] = {
            "source_video_path": str(source_path),
            "report_path": str(source_dir / "source_video_report.json"),
            "filename": request.filename,
            "content_type": request.content_type,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        profile.metadata = metadata
        profile.selected_avatar_asset = str(source_path)
        self.digital_store.save(profile)
        append_audit_event(
            self.settings.storage_dir,
            action="source_video.uploaded",
            project_id=profile.project_id,
            digital_human_id=digital_human_id,
            details={"source_video_path": str(source_path), "warnings": report.get("warnings", [])},
        )
        return {"digital_human_id": digital_human_id, "source_video_path": str(source_path), "report": report}

    async def create_hifly_avatar(self, digital_human_id: str, request: HiflySourceVideoAvatarRequest) -> dict[str, Any]:
        profile = self.digital_store.get(digital_human_id)
        out_dir = ensure_dir(self.source_dir(digital_human_id) / "hifly")
        video_url = self._hifly_video_url(digital_human_id, request.video_url, request.metadata)
        adapter = self.hifly_adapter()
        try:
            response = await adapter.create_avatar_by_video(
                video_url=video_url,
                title=request.title,
                out_dir=out_dir,
                confirm_paid_call=request.confirm_paid_call,
            )
        except AdapterError as exc:
            raise SourceVideoWorkflowError(str(exc), status_code=402 if "confirm_paid_call" in str(exc) else 400) from exc
        avatar_task_id = extract_hifly_id(response, "task_id", "taskId", "id")
        task_response = await adapter.wait_for_task(avatar_task_id, "avatar") if avatar_task_id else response
        avatar_id = extract_hifly_id(task_response, "avatar_id", "avatarId", "avatar") or extract_hifly_id(response, "avatar_id", "avatarId", "avatar")
        metadata = dict(profile.metadata or {})
        metadata["hifly_avatar"] = {
            "avatar_task_id": avatar_task_id,
            "avatar_id": avatar_id,
            "status": extract_hifly_id(task_response, "status", "state") or "done",
            "video_url": video_url,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        profile.metadata = metadata
        self.digital_store.save(profile)
        append_audit_event(
            self.settings.storage_dir,
            action="hifly.avatar.created",
            project_id=profile.project_id,
            digital_human_id=digital_human_id,
            details={"avatar_task_id": avatar_task_id, "avatar_id": avatar_id},
        )
        return {"digital_human_id": digital_human_id, "avatar_task_id": avatar_task_id, "avatar_id": avatar_id, "status": metadata["hifly_avatar"]["status"], "response": response}

    async def create_hifly_voice(self, digital_human_id: str, request: HiflySourceVideoVoiceRequest) -> dict[str, Any]:
        profile = self.digital_store.get(digital_human_id)
        out_dir = ensure_dir(self.source_dir(digital_human_id) / "hifly")
        self.extract_voice(digital_human_id)
        audio_url = self._hifly_audio_url(digital_human_id, request.audio_url, request.metadata)
        adapter = self.hifly_adapter()
        try:
            response = await adapter.create_voice(
                audio_url=audio_url,
                title=request.title,
                voice_type=request.voice_type,
                out_dir=out_dir,
                confirm_paid_call=request.confirm_paid_call,
            )
        except AdapterError as exc:
            raise SourceVideoWorkflowError(str(exc), status_code=402 if "confirm_paid_call" in str(exc) else 400) from exc
        voice_task_id = extract_hifly_id(response, "task_id", "taskId", "id")
        task_response = await adapter.wait_for_task(voice_task_id, "voice") if voice_task_id else response
        voice_id = extract_hifly_id(task_response, "voice_id", "voiceId", "voice") or extract_hifly_id(response, "voice_id", "voiceId", "voice")
        metadata = dict(profile.metadata or {})
        metadata["hifly_voice"] = {
            "voice_task_id": voice_task_id,
            "voice_id": voice_id,
            "status": extract_hifly_id(task_response, "status", "state") or "done",
            "audio_url": audio_url,
            "voice_type": request.voice_type,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        profile.metadata = metadata
        self.digital_store.save(profile)
        append_audit_event(
            self.settings.storage_dir,
            action="hifly.voice.created",
            project_id=profile.project_id,
            digital_human_id=digital_human_id,
            details={"voice_task_id": voice_task_id, "voice_id": voice_id},
        )
        return {"digital_human_id": digital_human_id, "voice_task_id": voice_task_id, "voice_id": voice_id, "status": metadata["hifly_voice"]["status"], "response": response}

    async def generate_hifly_from_source_video(
        self,
        store: TaskStore,
        task: VideoTask,
        request: HiflySourceVideoGenerateRequest,
    ) -> VideoTask:
        task_dir = ensure_dir(store.task_dir(task.task_id))
        logs_path = task_dir / "pipeline.log"
        task.artifacts.logs = str(logs_path)
        log_lines = [f"task_id={task.task_id}", "pipeline=hifly_source_video_digital_human"]
        store.update_status(task, TaskStatus.running)
        try:
            digital_human_id = task.request.digital_human_id
            if not digital_human_id:
                raise SourceVideoWorkflowError("digital_human_id is required")
            profile = self.digital_store.get(digital_human_id)
            source_report = self.validate_source_video(digital_human_id)
            write_json(task_dir / "source_video_report.json", source_report)
            log_lines.append("视频检测=completed")
            adapter = self.hifly_adapter()
            video_url = self._hifly_video_url(digital_human_id, request.video_url, request.metadata)
            script_json = _write_source_video_script(task_dir, task)
            task.artifacts.script_json = str(script_json)
            log_lines.append("写入脚本=completed")

            avatar_response = await adapter.create_avatar_by_video(
                video_url=video_url,
                title=request.title,
                out_dir=task_dir,
                confirm_paid_call=request.confirm_paid_call,
            )
            avatar_task_id = extract_hifly_id(avatar_response, "task_id", "taskId", "id")
            avatar_task = await adapter.wait_for_task(avatar_task_id, "avatar") if avatar_task_id else avatar_response
            avatar_id = extract_hifly_id(avatar_task, "avatar_id", "avatarId", "avatar") or extract_hifly_id(avatar_response, "avatar_id", "avatarId", "avatar")
            log_lines.append("创建数字人=completed")

            voice_task_id = None
            voice_id = None
            audio_url = ""
            hifly_mode = "hifly_clone_tts"
            if task.request.voice_profile_id:
                voice = self.digital_store.get_voice_profile_for_project(profile.project_id, task.request.voice_profile_id)
                tts_result = await self._synthesize_new_voice(task_dir, script_json, voice)
                task.artifacts.voice_audio = str(tts_result["voice"])
                task.artifacts.voice_segments = str(tts_result["segments"])
                task.artifacts.voice_metadata = str(tts_result["metadata"])
                task.artifacts.audio_quality_report = str(tts_result["quality"])
                audio_url = self._hifly_generated_audio_url(task_dir, task.task_id, Path(tts_result["voice"]), request.metadata)
                hifly_mode = "selected_voice_audio"
                log_lines.append("合成选中声音=completed")
                video_response = await adapter.create_video_by_audio(
                    audio_url=audio_url,
                    avatar=avatar_id,
                    title=request.title,
                    aigc_flag=request.aigc_flag,
                    out_dir=task_dir,
                    confirm_paid_call=request.confirm_paid_call,
                )
            else:
                self.extract_voice(digital_human_id)
                log_lines.append("提取声音=completed")
                audio_url = self._hifly_audio_url(digital_human_id, request.audio_url, request.metadata)
                voice_response = await adapter.create_voice(
                    audio_url=audio_url,
                    title=request.title,
                    voice_type=request.voice_type,
                    out_dir=task_dir,
                    confirm_paid_call=request.confirm_paid_call,
                )
                voice_task_id = extract_hifly_id(voice_response, "task_id", "taskId", "id")
                voice_task = await adapter.wait_for_task(voice_task_id, "voice") if voice_task_id else voice_response
                voice_id = extract_hifly_id(voice_task, "voice_id", "voiceId", "voice") or extract_hifly_id(voice_response, "voice_id", "voiceId", "voice")
                log_lines.append("克隆声音=completed")
                video_response = await adapter.create_video_by_tts(
                    text=request.text,
                    avatar=avatar_id,
                    voice=voice_id,
                    title=request.title,
                    aigc_flag=request.aigc_flag,
                    out_dir=task_dir,
                    confirm_paid_call=request.confirm_paid_call,
                )
            video_task_id = extract_hifly_id(video_response, "task_id", "taskId", "id")
            video_task = await adapter.wait_for_task(video_task_id, "video") if video_task_id else video_response
            result_url = extract_hifly_id(video_task, "video_url", "videoUrl", "video_Url", "result_url", "url") or extract_hifly_id(video_response, "video_url", "videoUrl", "video_Url", "result_url", "url")
            final_video = await adapter.download_result(result_url or "dryrun://hifly/final.mp4", task_dir / "final.mp4")
            task.artifacts.final_video = str(final_video)
            task.artifacts.artifact_manifest = str(write_artifact_manifest(task_dir))
            provider_report = write_json(
                task_dir / "provider_report.json",
                {
                    "provider": "hifly",
                    "avatar_task_id": avatar_task_id,
                    "avatar_id": avatar_id,
                    "voice_task_id": voice_task_id,
                    "voice_id": voice_id,
                    "voice_profile_id": task.request.voice_profile_id,
                    "video_task_id": video_task_id,
                    "mode": hifly_mode,
                    "status": "completed",
                    "warnings": _hifly_warnings(self.settings.dry_run, video_url, audio_url),
                    "cost_note": "Hifly/飞影 API 可能消耗额度；真实调用仅在 confirm_paid_call=true 时执行。",
                    "result_url": result_url,
                    "dry_run": self.settings.dry_run,
                },
            )
            log_lines.append("生成视频=completed")
            task.request.metadata["hifly"] = {"avatar_id": avatar_id, "voice_id": voice_id, "provider_report": str(provider_report)}
            append_audit_event(
                self.settings.storage_dir,
                action="hifly.video.generated",
                task_id=task.task_id,
                project_id=profile.project_id,
                digital_human_id=digital_human_id,
                details={"video_task_id": video_task_id, "final_video": str(final_video)},
            )
            write_text(logs_path, "\n".join(log_lines) + "\n")
            store.update_status(task, TaskStatus.completed)
            return store.save(task)
        except Exception as exc:
            write_json(
                task_dir / "provider_report.json",
                {
                    "provider": "hifly",
                    "status": "failed",
                    "warnings": [],
                    "cost_note": "Hifly/飞影 API 真实调用需要 confirm_paid_call=true。",
                    "error": str(exc),
                },
            )
            task.error = str(exc)
            write_text(logs_path, "\n".join(log_lines) + f"\nERROR: {exc}\n")
            store.update_status(task, TaskStatus.failed, error=str(exc))
            return store.save(task)

    def validate_source_video(self, digital_human_id: str) -> dict[str, Any]:
        source_path = self.source_video_path(digital_human_id)
        source_dir = source_path.parent
        checks = {
            "file_exists": source_path.exists(),
            "non_zero_size": source_path.exists() and source_path.stat().st_size > 0,
        }
        warnings: list[str] = []
        blockers: list[str] = []
        if not checks["file_exists"]:
            blockers.append("source_video.mp4 missing")
        if source_path.exists() and not checks["non_zero_size"]:
            blockers.append("source_video.mp4 is empty")

        probe = _probe_media(source_path, self.ffprobe_path, dry_run=self.settings.dry_run)
        checks.update(
            {
                "ffprobe_available": bool(self.ffprobe_path),
                "ffprobe_readable": probe["readable"],
                "has_video_stream": probe["has_video_stream"],
                "has_audio_stream": probe["has_audio_stream"],
            }
        )
        if not probe["has_video_stream"]:
            blockers.append("source video has no video stream")
        if not probe["has_audio_stream"]:
            warnings.append("source video has no audio stream; voice clone sample cannot be created until audio is provided")
            if not self.settings.dry_run:
                blockers.append("source video has no audio stream")
        duration = float(probe.get("duration_seconds") or 0)
        width = int(probe.get("width") or 0)
        height = int(probe.get("height") or 0)
        if duration and duration < 10:
            warnings.append("source video duration is shorter than 10 seconds")
        if width and height and min(width, height) < 720:
            warnings.append("source video resolution is lower than 720p")
        if not probe["readable"] and self.ffprobe_path and not self.settings.dry_run:
            blockers.append("source video is not readable by ffprobe")

        report = {
            "digital_human_id": digital_human_id,
            "source_video_path": str(source_path),
            "checks": checks,
            "media": {
                "duration_seconds": duration,
                "width": width,
                "height": height,
                "has_video_stream": probe["has_video_stream"],
                "has_audio_stream": probe["has_audio_stream"],
            },
            "warnings": warnings,
            "blockers": blockers,
            "dry_run": self.settings.dry_run,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        write_json(source_dir / "source_video_report.json", report)
        return report

    def extract_voice(self, digital_human_id: str) -> dict[str, Any]:
        source_path = self.source_video_path(digital_human_id)
        source_dir = source_path.parent
        report = self.validate_source_video(digital_human_id)
        if report["blockers"] and not self.settings.dry_run:
            raise SourceVideoWorkflowError("源视频不可用于真实声音提取：" + "；".join(report["blockers"]))
        if not source_path.exists():
            raise SourceVideoWorkflowError("source_video.mp4 missing")

        source_audio = source_dir / "source_audio.wav"
        clean_sample = source_dir / "clean_voice_sample.wav"
        source_stdout = source_dir / "source_audio_ffmpeg_stdout.log"
        source_stderr = source_dir / "source_audio_ffmpeg_stderr.log"
        sample_stdout = source_dir / "clean_voice_sample_ffmpeg_stdout.log"
        sample_stderr = source_dir / "clean_voice_sample_ffmpeg_stderr.log"

        if self.settings.dry_run:
            write_placeholder_binary(source_audio, f"source_audio={digital_human_id}")
            write_placeholder_binary(clean_sample, f"clean_voice_sample={digital_human_id};first_20_seconds")
            source_stdout.write_text("", encoding="utf-8")
            source_stderr.write_text("dry-run: ffmpeg not invoked\n", encoding="utf-8")
            sample_stdout.write_text("", encoding="utf-8")
            sample_stderr.write_text("dry-run: ffmpeg not invoked\n", encoding="utf-8")
            ffmpeg_used = False
        else:
            if not self.ffmpeg_path:
                raise SourceVideoWorkflowError("ffmpeg unavailable; real mode cannot extract source video audio")
            _run_command(
                [
                    self.ffmpeg_path,
                    "-y",
                    "-i",
                    str(source_path),
                    "-vn",
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    str(source_audio),
                ],
                source_stdout,
                source_stderr,
            )
            _run_command(
                [
                    self.ffmpeg_path,
                    "-y",
                    "-i",
                    str(source_audio),
                    "-t",
                    "20",
                    "-af",
                    "loudnorm",
                    str(clean_sample),
                ],
                sample_stdout,
                sample_stderr,
            )
            ffmpeg_used = True

        audio_report = {
            "source_video_path": str(source_path),
            "source_audio_path": str(source_audio),
            "ffmpeg_available": bool(self.ffmpeg_path),
            "ffmpeg_used": ffmpeg_used,
            "dry_run": self.settings.dry_run,
            "warnings": [] if ffmpeg_used else ["dry-run placeholder audio; not a real voice clone sample"],
        }
        sample_report = {
            "source_audio_path": str(source_audio),
            "clean_voice_sample_path": str(clean_sample),
            "strategy": "first_20_seconds",
            "future_hooks": ["vad", "denoise", "manual_trim"],
            "ffmpeg_used": ffmpeg_used,
            "dry_run": self.settings.dry_run,
        }
        write_json(source_dir / "source_audio_report.json", audio_report)
        write_json(source_dir / "voice_sample_report.json", sample_report)
        return {
            "digital_human_id": digital_human_id,
            "source_audio_path": str(source_audio),
            "clean_voice_sample_path": str(clean_sample),
            "source_audio_report": audio_report,
            "voice_sample_report": sample_report,
        }

    async def create_voice_profile(
        self,
        digital_human_id: str,
        request: SourceVideoVoiceProfileRequest,
    ):
        profile = self.digital_store.get(digital_human_id)
        source_dir = self.source_dir(digital_human_id)
        if not self.settings.dry_run and not request.confirm_paid_call:
            raise SourceVideoWorkflowError("confirm_paid_call=true required before Aliyun Bailian voice clone", status_code=402)
        if not self.settings.dry_run and not self.settings.dashscope_api_key:
            raise SourceVideoWorkflowError("DASHSCOPE_API_KEY missing")
        clean_sample = source_dir / "clean_voice_sample.wav"
        if not clean_sample.exists():
            self.extract_voice(digital_human_id)

        adapter = AliyunBailianVoiceAdapter(
            provider_id=request.provider,
            dry_run=self.settings.dry_run,
            api_key=self.settings.dashscope_api_key,
            region=self.settings.aliyun_bailian_region,
            model=self.settings.aliyun_voice_model,
        )
        clone_dir = ensure_dir(source_dir / "voice_clone")
        sample_audio_url = request.source_audio_url
        object_storage_upload = None
        if not self.settings.dry_run and not sample_audio_url:
            try:
                upload_result = build_object_storage_adapter(self.settings).upload_file(
                    file_path=clean_sample,
                    key=source_voice_sample_key(
                        self.settings,
                        project_id=profile.project_id,
                        digital_human_id=digital_human_id,
                    ),
                    report_dir=clone_dir,
                    report_name="clean_voice_sample_upload.json",
                )
                sample_audio_url = upload_result.public_url
                object_storage_upload = {
                    "provider": upload_result.provider,
                    "key": upload_result.key,
                    "public_url": upload_result.public_url,
                    "local_copy_path": upload_result.local_copy_path,
                    "report_path": upload_result.report_path,
                }
            except AdapterError as exc:
                raise SourceVideoWorkflowError(str(exc)) from exc
        try:
            clone_response = await adapter.create_voice_clone(
                sample_audio_path=clean_sample,
                sample_audio_url=sample_audio_url,
                voice_name=request.name,
                out_dir=clone_dir,
            )
        except AdapterError as exc:
            raise SourceVideoWorkflowError(str(exc)) from exc
        provider_voice_id = str(clone_response.get("voice_id"))

        voice = self.digital_store.create_voice_profile(
            digital_human_id,
            CreateVoiceProfileRequest(
                name=request.name,
                voice_source_type=VoiceSourceType.source_video_audio,
                engine=request.provider,
                sample_asset_id=str(clean_sample),
                metadata={
                    **request.metadata,
                    "source": "source_video_audio",
                    "source_video_path": str(self.source_video_path(digital_human_id)),
                    "clean_voice_sample_path": str(clean_sample),
                    "sample_audio_url": sample_audio_url,
                    "object_storage_upload": object_storage_upload,
                    "provider": request.provider,
                    "provider_voice_id": provider_voice_id,
                    "cloud_voice_id": provider_voice_id,
                    "voice_id": provider_voice_id,
                    "clone_response_path": str(clone_dir / "aliyun_voice_clone_response.json"),
                },
            ),
        )
        append_audit_event(
            self.settings.storage_dir,
            action="voice_profile.created",
            project_id=profile.project_id,
            digital_human_id=digital_human_id,
            details={"voice_profile_id": voice.voice_profile_id, "source": "source_video_audio"},
        )
        return voice

    async def render_task_from_source_video(
        self,
        store: TaskStore,
        task: VideoTask,
        request: CloudSourceVideoRenderRequest,
    ) -> VideoTask:
        task_dir = ensure_dir(store.task_dir(task.task_id))
        logs_path = task_dir / "pipeline.log"
        task.artifacts.logs = str(logs_path)
        log_lines = [f"task_id={task.task_id}", "pipeline=source_video_voice_clone_lipsync"]
        store.update_status(task, TaskStatus.running)

        try:
            if not task.request.digital_human_id:
                raise SourceVideoWorkflowError("digital_human_id is required")
            if not task.request.voice_profile_id:
                raise SourceVideoWorkflowError("voice_profile_id is required")
            profile = self.digital_store.get(task.request.digital_human_id)
            voice = self.digital_store.get_voice_profile_for_project(profile.project_id, task.request.voice_profile_id)

            selected_provider = self._selected_video_provider()
            cloud_lipsync_provider = self.settings.cloud_lipsync_provider.lower()
            syncso_selected = self.settings.cloud_lipsync_enabled and cloud_lipsync_provider == "syncso"
            pixverse_selected = self.settings.cloud_lipsync_enabled and cloud_lipsync_provider in {"pixverse", "pixverse_lipsync"}
            if not self.settings.dry_run and not request.confirm_paid_call:
                raise SourceVideoWorkflowError("confirm_paid_call=true required before cloud source-video render")
            if not self.settings.dry_run and selected_provider == "omnihuman":
                if not self.settings.omnihuman_access_key or not self.settings.omnihuman_secret_key:
                    raise SourceVideoWorkflowError("OMNIHUMAN_ACCESS_KEY/OMNIHUMAN_SECRET_KEY missing")
            elif not self.settings.dry_run and syncso_selected:
                if not self.settings.syncso_api_key:
                    raise SourceVideoWorkflowError("SYNCSO_API_KEY missing")
            elif not self.settings.dry_run and pixverse_selected:
                if not self.settings.pixverse_api_key:
                    raise SourceVideoWorkflowError("PIXVERSE_API_KEY missing")
            elif not self.settings.dry_run and not self.settings.fal_api_key:
                raise SourceVideoWorkflowError("FAL_API_KEY missing")
            if not self.settings.dry_run and not self.settings.dashscope_api_key:
                raise SourceVideoWorkflowError("DASHSCOPE_API_KEY missing")

            source_report = await self._task_step(store, task, "视频检测", lambda: self._copy_source_report(task_dir, profile.digital_human_id), log_lines)
            await self._task_step(store, task, "提取声音", lambda: self._ensure_source_audio(profile.digital_human_id, task_dir), log_lines)
            script_json = await self._task_step(store, task, "写入脚本", lambda: _write_source_video_script(task_dir, task), log_lines)
            tts_result = await self._synthesize_new_voice(task_dir, script_json, voice)
            task.artifacts.voice_audio = str(tts_result["voice"])
            task.artifacts.voice_segments = str(tts_result["segments"])
            task.artifacts.voice_metadata = str(tts_result["metadata"])
            task.artifacts.audio_quality_report = str(tts_result["quality"])
            task.artifacts.script_json = str(script_json)

            normalized = await self._task_step(
                store,
                task,
                "视频时长处理",
                lambda: self._prepare_avatar_video(task_dir, profile.digital_human_id, task, source_report),
                log_lines,
            )
            task.artifacts.avatar_base_video = str(normalized)
            task.artifacts.avatar_video = str(normalized)

            lip_synced = await self._render_lipsync(task_dir, normalized, Path(task.artifacts.voice_audio), task, profile, voice, request)
            task.artifacts.lip_synced_video = str(lip_synced)
            final_video = await self._assemble_final(task_dir, lip_synced, script_json)
            task.artifacts.final_video = str(final_video)
            manifest = write_artifact_manifest(task_dir)
            task.artifacts.artifact_manifest = str(manifest)

            append_audit_event(
                self.settings.storage_dir,
                action="source_video.cloud_render.completed",
                task_id=task.task_id,
                project_id=profile.project_id,
                digital_human_id=profile.digital_human_id,
                details={"render_quality": request.render_quality, "final_video": str(final_video)},
            )
            write_text(logs_path, "\n".join(log_lines) + "\n")
            store.update_status(task, TaskStatus.completed)
            return store.save(task)
        except Exception as exc:
            task.error = str(exc)
            write_text(logs_path, "\n".join(log_lines) + f"\nERROR: {exc}\n")
            store.update_status(task, TaskStatus.failed, error=str(exc))
            return store.save(task)

    async def _task_step(self, store: TaskStore, task: VideoTask, name: str, fn, log_lines: list[str]) -> Any:
        step = StepResult(name=name, status="running", started_at=datetime.now(timezone.utc))
        task.steps.append(step)
        store.save(task)
        try:
            result = fn()
            if asyncio.iscoroutine(result):
                result = await result
            step.status = "completed"
            step.finished_at = datetime.now(timezone.utc)
            step.message = "ok"
            if isinstance(result, Path):
                step.artifacts["path"] = str(result)
            log_lines.append(f"{name}=completed")
            store.save(task)
            return result
        except Exception as exc:
            step.status = "failed"
            step.finished_at = datetime.now(timezone.utc)
            step.message = str(exc)
            store.save(task)
            raise

    def _copy_source_report(self, task_dir: Path, digital_human_id: str) -> dict[str, Any]:
        report = self.validate_source_video(digital_human_id)
        write_json(task_dir / "source_video_report.json", report)
        return report

    def _ensure_source_audio(self, digital_human_id: str, task_dir: Path) -> Path:
        source_dir = self.source_dir(digital_human_id)
        if not (source_dir / "clean_voice_sample.wav").exists():
            self.extract_voice(digital_human_id)
        for name in ["source_audio.wav", "source_audio_report.json", "clean_voice_sample.wav", "voice_sample_report.json"]:
            src = source_dir / name
            if src.exists():
                dst = task_dir / name
                if src.is_file():
                    shutil.copyfile(src, dst)
        return task_dir / "clean_voice_sample.wav"

    async def _synthesize_new_voice(self, task_dir: Path, script_json: Path, voice) -> dict[str, Path]:
        text = _script_text(script_json)
        metadata = voice.metadata if isinstance(voice.metadata, dict) else {}
        voice_id = str(metadata.get("provider_voice_id") or metadata.get("cloud_voice_id") or metadata.get("voice_id") or voice.voice_profile_id)
        adapter = AliyunBailianVoiceAdapter(
            provider_id=str(voice.engine or self.settings.cloud_voice_provider),
            dry_run=self.settings.dry_run,
            api_key=self.settings.dashscope_api_key,
            region=self.settings.aliyun_bailian_region,
            model=self.settings.aliyun_voice_model,
        )
        result = await adapter.synthesize_with_cloned_voice(text=text, voice_id=voice_id, out_dir=task_dir, script_json=script_json, voice_profile=voice)
        quality = write_json(
            task_dir / "audio_quality_report.json",
            {
                "status": "completed",
                "file_exists": result.audio_path.exists(),
                "size_bytes": result.audio_path.stat().st_size if result.audio_path.exists() else 0,
                "readable_by_ffprobe": False,
                "duration_seconds": None,
                "warnings": ["dry-run placeholder audio; original source video audio was not used as final audio"],
            },
        )
        return {"voice": result.audio_path, "segments": result.segments_path, "metadata": result.metadata_path, "quality": quality}
    def _prepare_avatar_video(self, task_dir: Path, digital_human_id: str, task: VideoTask, source_report: dict[str, Any]) -> Path:
        source_video = self.source_video_path(digital_human_id)
        muted = task_dir / "avatar_source_muted.mp4"
        normalized = task_dir / "avatar_base_normalized.mp4"
        stdout_path = task_dir / "avatar_stdout.log"
        stderr_path = task_dir / "avatar_stderr.log"
        metadata = task.request.metadata or {}
        source_duration = float(metadata.get("source_video_duration_seconds") or source_report.get("media", {}).get("duration_seconds") or 3)
        voice_duration = float(metadata.get("voice_duration_seconds") or max(3, len(_script_text(task_dir / "script.json")) / 12))
        if source_duration < voice_duration:
            action = "loop"
        elif source_duration > voice_duration:
            action = "trim"
        else:
            action = "copy"

        if self.settings.dry_run:
            write_placeholder_binary(muted, f"muted_source={source_video}")
            write_placeholder_binary(normalized, f"normalized_source={source_video};action={action};voice_duration={voice_duration}")
            stdout_path.write_text("", encoding="utf-8")
            stderr_path.write_text("dry-run: ffmpeg not invoked\n", encoding="utf-8")
            ffmpeg_used = False
        else:
            if not self.ffmpeg_path:
                raise SourceVideoWorkflowError("ffmpeg unavailable; real mode cannot prepare avatar video")
            _run_command([self.ffmpeg_path, "-y", "-i", str(source_video), "-an", "-c:v", "copy", str(muted)], stdout_path, stderr_path)
            if action == "loop":
                command = [self.ffmpeg_path, "-y", "-stream_loop", "-1", "-i", str(muted), "-t", str(voice_duration), "-c:v", "libx264", "-pix_fmt", "yuv420p", str(normalized)]
            elif action == "trim":
                command = [self.ffmpeg_path, "-y", "-i", str(muted), "-t", str(voice_duration), "-c:v", "libx264", "-pix_fmt", "yuv420p", str(normalized)]
            else:
                command = [self.ffmpeg_path, "-y", "-i", str(muted), "-c:v", "copy", str(normalized)]
            _run_command(command, stdout_path, stderr_path)
            ffmpeg_used = True

        write_json(
            task_dir / "avatar_duration_normalization_report.json",
            {
                "source_video": str(source_video),
                "muted_video": str(muted),
                "output": str(normalized),
                "source_duration_seconds": source_duration,
                "voice_duration_seconds": voice_duration,
                "action": action,
                "ffmpeg_used": ffmpeg_used,
                "original_audio_removed": True,
            },
        )
        return normalized
    def _selected_video_provider(self) -> str:
        provider = (self.settings.cloud_video_provider or "").strip().lower()
        if provider in {"volcengine_omnihuman", "volc_omnihuman"}:
            return "omnihuman"
        return provider

    async def _render_lipsync(
        self,
        task_dir: Path,
        avatar_video: Path,
        voice_audio: Path,
        task: VideoTask,
        profile,
        voice,
        request: CloudSourceVideoRenderRequest,
    ) -> Path:
        if self._selected_video_provider() == "omnihuman":
            return await self._render_omnihuman(task_dir, avatar_video, voice_audio, task, profile, voice, request)

        if self.settings.cloud_lipsync_enabled and self.settings.cloud_lipsync_provider.lower() == "syncso":
            provider_id = "syncso"
            adapter = SyncSoLipSyncAdapter(
                dry_run=self.settings.dry_run,
                enabled=True,
                base_url=self.settings.syncso_base_url,
                api_key=self.settings.syncso_api_key,
                model=self.settings.syncso_model,
                generate_endpoint=self.settings.syncso_generate_endpoint,
                timeout_seconds=self.settings.syncso_timeout_seconds,
                poll_interval_seconds=self.settings.syncso_poll_interval_seconds,
            )
            try:
                output = await adapter.sync_lip(avatar_video, voice_audio, task_dir)
                write_json(
                    task_dir / "cloud_video_render_report.json",
                    {
                        "provider": provider_id,
                        "render_quality": request.render_quality,
                        "video_input": str(avatar_video),
                        "audio_input": str(voice_audio),
                        "output": str(output),
                        "paid_call_confirmed": request.confirm_paid_call,
                        "dry_run": self.settings.dry_run,
                        "status": "completed",
                    },
                )
                write_json(
                    task_dir / "lip_sync_report.json",
                    {
                        "status": "completed",
                        "engine_used": provider_id,
                        "source_video": str(avatar_video),
                        "voice_audio": str(voice_audio),
                        "output": str(output),
                    },
                )
                return output
            except AdapterError as exc:
                write_json(
                    task_dir / "cloud_video_render_report.json",
                    {"provider": provider_id, "status": "failed", "error": str(exc), "dry_run": self.settings.dry_run},
                )
                raise

        if self.settings.cloud_lipsync_enabled and self.settings.cloud_lipsync_provider.lower() in {"pixverse", "pixverse_lipsync"}:
            provider_id = "pixverse_lipsync"
            adapter = PixVerseLipSyncAdapter(
                dry_run=self.settings.dry_run,
                enabled=True,
                base_url=self.settings.pixverse_base_url,
                api_key=self.settings.pixverse_api_key,
                model=self.settings.pixverse_model,
                generate_endpoint=self.settings.pixverse_generate_endpoint,
                task_endpoint_template=self.settings.pixverse_task_endpoint_template,
                timeout_seconds=self.settings.pixverse_timeout_seconds,
                poll_interval_seconds=self.settings.pixverse_poll_interval_seconds,
            )
            try:
                video_url, audio_url = self._pixverse_public_urls(task_dir, task, profile, voice, avatar_video, voice_audio)
                output = await adapter.sync_lip(avatar_video, voice_audio, task_dir, video_url=video_url, audio_url=audio_url)
                write_json(
                    task_dir / "cloud_video_render_report.json",
                    {
                        "provider": provider_id,
                        "render_quality": request.render_quality,
                        "video_input": video_url,
                        "audio_input": audio_url,
                        "output": str(output),
                        "paid_call_confirmed": request.confirm_paid_call,
                        "dry_run": self.settings.dry_run,
                        "status": "completed",
                    },
                )
                write_json(
                    task_dir / "lip_sync_report.json",
                    {
                        "status": "completed",
                        "engine_used": provider_id,
                        "source_video": str(avatar_video),
                        "voice_audio": str(voice_audio),
                        "output": str(output),
                    },
                )
                return output
            except (AdapterError, SourceVideoWorkflowError) as exc:
                write_json(
                    task_dir / "cloud_video_render_report.json",
                    {"provider": provider_id, "status": "failed", "error": str(exc), "dry_run": self.settings.dry_run},
                )
                raise

        provider_id = "fal_musetalk" if request.render_quality == "preview" else "fal_latentsync"
        adapter = FalVideoRenderAdapter(
            provider_id=provider_id,
            dry_run=self.settings.dry_run,
            enabled=True,
            api_key=self.settings.fal_api_key,
            latentsync_model=self.settings.fal_latentsync_model,
            musetalk_model=self.settings.fal_musetalk_model,
        )
        try:
            output = await adapter.render_lipsync(video_url=str(avatar_video), audio_url=str(voice_audio), out_dir=task_dir)
            write_json(
                task_dir / "cloud_video_render_report.json",
                {
                    "provider": provider_id,
                    "render_quality": request.render_quality,
                    "video_input": str(avatar_video),
                    "audio_input": str(voice_audio),
                    "output": str(output),
                    "paid_call_confirmed": request.confirm_paid_call,
                    "dry_run": self.settings.dry_run,
                    "status": "completed",
                },
            )
            write_json(
                task_dir / "lip_sync_report.json",
                {
                    "status": "completed",
                    "engine_used": provider_id,
                    "source_video": str(avatar_video),
                    "voice_audio": str(voice_audio),
                    "output": str(output),
                },
            )
            return output
        except AdapterError as exc:
            write_json(
                task_dir / "cloud_video_render_report.json",
                {"provider": provider_id, "status": "failed", "error": str(exc), "dry_run": self.settings.dry_run},
            )
            raise

    async def _render_omnihuman(
        self,
        task_dir: Path,
        avatar_video: Path,
        voice_audio: Path,
        task: VideoTask,
        profile,
        voice,
        request: CloudSourceVideoRenderRequest,
    ) -> Path:
        provider_id = "omnihuman"
        adapter = OmniHumanVideoAdapter(
            dry_run=self.settings.dry_run,
            enabled=self.settings.omnihuman_enabled or self._selected_video_provider() == "omnihuman",
            access_key=self.settings.omnihuman_access_key,
            secret_key=self.settings.omnihuman_secret_key,
            endpoint=self.settings.omnihuman_endpoint,
            region=self.settings.omnihuman_region,
            service=self.settings.omnihuman_service,
            version=self.settings.omnihuman_version,
            req_key=self.settings.omnihuman_req_key,
            output_resolution=self.settings.omnihuman_output_resolution,
            prompt=self.settings.omnihuman_prompt,
            pe_fast_mode=self.settings.omnihuman_pe_fast_mode,
            timeout_seconds=self.settings.omnihuman_timeout_seconds,
            poll_interval_seconds=self.settings.omnihuman_poll_interval_seconds,
        )
        try:
            image_url, audio_url = self._omnihuman_public_urls(task_dir, task, profile, voice, voice_audio)
            metadata = task.request.metadata if isinstance(task.request.metadata, dict) else {}
            output = await adapter.generate_video(
                image_url=image_url,
                audio_url=audio_url,
                prompt=str(metadata.get("omnihuman_prompt") or self.settings.omnihuman_prompt),
                out_dir=task_dir,
            )
            lip_synced = task_dir / "lip_synced.mp4"
            if output != lip_synced:
                shutil.copyfile(output, lip_synced)
            write_json(
                task_dir / "cloud_video_render_report.json",
                {
                    "provider": provider_id,
                    "render_quality": request.render_quality,
                    "image_input": image_url,
                    "audio_input": audio_url,
                    "avatar_video_reference": str(avatar_video),
                    "output": str(lip_synced),
                    "paid_call_confirmed": request.confirm_paid_call,
                    "dry_run": self.settings.dry_run,
                    "status": "completed",
                },
            )
            write_json(
                task_dir / "lip_sync_report.json",
                {
                    "status": "completed",
                    "engine_used": provider_id,
                    "source_video": str(avatar_video),
                    "voice_audio": str(voice_audio),
                    "output": str(lip_synced),
                },
            )
            return lip_synced
        except (AdapterError, SourceVideoWorkflowError) as exc:
            write_json(
                task_dir / "cloud_video_render_report.json",
                {"provider": provider_id, "status": "failed", "error": str(exc), "dry_run": self.settings.dry_run},
            )
            raise

    def _omnihuman_public_urls(self, task_dir: Path, task: VideoTask, profile, voice, voice_audio: Path) -> tuple[str, str]:
        task_meta = task.request.metadata if isinstance(task.request.metadata, dict) else {}
        profile_meta = profile.metadata if isinstance(profile.metadata, dict) else {}
        voice_meta = voice.metadata if isinstance(voice.metadata, dict) else {}
        source_meta = profile_meta.get("source_video") if isinstance(profile_meta.get("source_video"), dict) else {}
        image_url = (
            task_meta.get("omnihuman_image_url")
            or task_meta.get("avatar_image_url")
            or task_meta.get("image_url")
            or profile_meta.get("omnihuman_image_url")
            or profile_meta.get("avatar_image_url")
            or source_meta.get("omnihuman_image_url")
            or source_meta.get("avatar_image_url")
        )
        audio_url = (
            task_meta.get("omnihuman_audio_url")
            or task_meta.get("voice_audio_url")
            or task_meta.get("cloud_audio_url")
            or task_meta.get("audio_url")
            or voice_meta.get("omnihuman_audio_url")
            or voice_meta.get("voice_audio_url")
            or voice_meta.get("cloud_audio_url")
            or voice_meta.get("audio_url")
        )
        uploads: dict[str, Any] = {}
        if not image_url:
            image_path = self._extract_omnihuman_avatar_image(task_dir, profile.digital_human_id)
            image_upload = self._upload_omnihuman_input(
                task_dir,
                task.task_id,
                image_path,
                "omnihuman_avatar_frame.jpg",
                "omnihuman_avatar_frame_upload.json",
            )
            image_url = image_upload.public_url
            uploads["image"] = {"provider": image_upload.provider, "key": image_upload.key, "public_url": image_upload.public_url}
        if not audio_url:
            audio_upload = self._upload_omnihuman_input(
                task_dir,
                task.task_id,
                voice_audio,
                "omnihuman_voice.wav",
                "omnihuman_audio_upload.json",
            )
            audio_url = audio_upload.public_url
            uploads["audio"] = {"provider": audio_upload.provider, "key": audio_upload.key, "public_url": audio_upload.public_url}
        write_json(task_dir / "omnihuman_input_urls.json", {"image_url": image_url, "audio_url": audio_url, "auto_uploads": uploads})
        return str(image_url), str(audio_url)

    def _pixverse_public_urls(self, task_dir: Path, task: VideoTask, profile, voice, avatar_video: Path, voice_audio: Path) -> tuple[str, str]:
        task_meta = task.request.metadata if isinstance(task.request.metadata, dict) else {}
        profile_meta = profile.metadata if isinstance(profile.metadata, dict) else {}
        voice_meta = voice.metadata if isinstance(voice.metadata, dict) else {}
        video_url = (
            task_meta.get("pixverse_video_url")
            or task_meta.get("cloud_video_url")
            or task_meta.get("video_url")
            or profile_meta.get("pixverse_video_url")
            or profile_meta.get("cloud_video_url")
            or profile_meta.get("video_url")
        )
        audio_url = (
            task_meta.get("pixverse_audio_url")
            or task_meta.get("cloud_audio_url")
            or task_meta.get("audio_url")
            or voice_meta.get("pixverse_audio_url")
            or voice_meta.get("cloud_audio_url")
            or voice_meta.get("audio_url")
        )
        uploads: dict[str, Any] = {}
        if not video_url:
            video_upload = self._upload_omnihuman_input(
                task_dir,
                task.task_id,
                avatar_video,
                "pixverse_avatar_video.mp4",
                "pixverse_avatar_video_upload.json",
            )
            video_url = video_upload.public_url
            uploads["video"] = {"provider": video_upload.provider, "key": video_upload.key, "public_url": video_upload.public_url}
        if not audio_url:
            audio_upload = self._upload_omnihuman_input(
                task_dir,
                task.task_id,
                voice_audio,
                "pixverse_voice.wav",
                "pixverse_audio_upload.json",
            )
            audio_url = audio_upload.public_url
            uploads["audio"] = {"provider": audio_upload.provider, "key": audio_upload.key, "public_url": audio_upload.public_url}
        write_json(task_dir / "pixverse_input_urls.json", {"video_url": video_url, "audio_url": audio_url, "auto_uploads": uploads})
        return str(video_url), str(audio_url)

    def _extract_omnihuman_avatar_image(self, task_dir: Path, digital_human_id: str) -> Path:
        output = task_dir / "omnihuman_avatar_frame.jpg"
        if self.settings.dry_run:
            return write_placeholder_binary(output, f"omnihuman-frame={digital_human_id}")
        if not self.ffmpeg_path:
            raise SourceVideoWorkflowError("OmniHuman 需要从源视频截取一张形象图片，但当前 ffmpeg 不可用。")
        stdout_path = task_dir / "omnihuman_frame_stdout.log"
        stderr_path = task_dir / "omnihuman_frame_stderr.log"
        _run_command(
            [self.ffmpeg_path, "-y", "-i", str(self.source_video_path(digital_human_id)), "-frames:v", "1", "-q:v", "2", str(output)],
            stdout_path,
            stderr_path,
        )
        if not output.exists() or output.stat().st_size <= 0:
            raise SourceVideoWorkflowError("OmniHuman 源视频头像图截取失败，请换一个可读取的视频或手动填写 omnihuman_image_url。")
        return output

    def _upload_omnihuman_input(self, task_dir: Path, task_id: str, file_path: Path, filename: str, report_name: str):
        key = _task_object_storage_key(self.settings, task_id=task_id, filename=filename)
        try:
            return build_object_storage_adapter(self.settings).upload_file(
                file_path=file_path,
                key=key,
                report_dir=task_dir,
                report_name=report_name,
            )
        except AdapterError as exc:
            raise SourceVideoWorkflowError(
                "OmniHuman 需要公网可访问的图片和音频 URL；请配置 OSS/COS 自动上传，或在任务 metadata 中填写 "
                "omnihuman_image_url / omnihuman_audio_url。"
            ) from exc

    def _auto_upload_hifly_video_url(self, digital_human_id: str) -> str:
        profile = self.digital_store.get(digital_human_id)
        source_path = self.source_video_path(digital_human_id)
        if not source_path.exists() or source_path.stat().st_size <= 0:
            raise SourceVideoWorkflowError("请先上传源视频，再生成飞影数字人视频。")
        report_dir = ensure_dir(self.source_dir(digital_human_id) / "hifly")
        try:
            upload_result = build_object_storage_adapter(self.settings).upload_file(
                file_path=source_path,
                key=_source_video_object_storage_key(
                    self.settings,
                    project_id=profile.project_id,
                    digital_human_id=digital_human_id,
                    filename="source_video.mp4",
                ),
                report_dir=report_dir,
                report_name="source_video_upload.json",
            )
        except AdapterError as exc:
            raise SourceVideoWorkflowError(
                "飞影真实模式需要公网可访问的视频 URL；本地源视频自动上传失败。"
                "请在桌面版设置里配置阿里云 OSS/腾讯云 COS，或手动填写 source_video_url。"
            ) from exc
        self._save_source_video_public_url(
            profile,
            {
                "public_url": upload_result.public_url,
                "video_url": upload_result.public_url,
                "source_video_url": upload_result.public_url,
                "object_storage_video_upload": _upload_metadata(upload_result),
            },
        )
        return upload_result.public_url

    def _auto_upload_hifly_audio_url(self, digital_human_id: str) -> str:
        profile = self.digital_store.get(digital_human_id)
        clean_sample = self.source_dir(digital_human_id) / "clean_voice_sample.wav"
        if not clean_sample.exists() or clean_sample.stat().st_size <= 0:
            self.extract_voice(digital_human_id)
        if not clean_sample.exists() or clean_sample.stat().st_size <= 0:
            raise SourceVideoWorkflowError("请先从源视频提取有效声音样本，再调用飞影生成视频。")
        report_dir = ensure_dir(self.source_dir(digital_human_id) / "hifly")
        try:
            upload_result = build_object_storage_adapter(self.settings).upload_file(
                file_path=clean_sample,
                key=source_voice_sample_key(
                    self.settings,
                    project_id=profile.project_id,
                    digital_human_id=digital_human_id,
                ),
                report_dir=report_dir,
                report_name="clean_voice_sample_upload.json",
            )
        except AdapterError as exc:
            raise SourceVideoWorkflowError(
                "飞影真实模式需要公网可访问的声音 URL；本地声音样本自动上传失败。"
                "请在桌面版设置里配置阿里云 OSS/腾讯云 COS，或手动填写 source_audio_url。"
            ) from exc
        self._save_source_video_public_url(
            profile,
            {
                "public_audio_url": upload_result.public_url,
                "audio_url": upload_result.public_url,
                "source_audio_url": upload_result.public_url,
                "object_storage_audio_upload": _upload_metadata(upload_result),
            },
        )
        return upload_result.public_url

    def _hifly_generated_audio_url(self, task_dir: Path, task_id: str, audio_path: Path, metadata: dict[str, Any]) -> str:
        values = [
            metadata.get("generated_audio_url") if isinstance(metadata, dict) else None,
            metadata.get("voice_audio_url") if isinstance(metadata, dict) else None,
            metadata.get("hifly_generated_audio_url") if isinstance(metadata, dict) else None,
        ]
        for value in values:
            if value:
                return str(value)
        if self.settings.dry_run:
            return str(audio_path)
        try:
            upload_result = build_object_storage_adapter(self.settings).upload_file(
                file_path=audio_path,
                key=_task_object_storage_key(self.settings, task_id=task_id, filename="hifly_voice.wav"),
                report_dir=task_dir,
                report_name="hifly_voice_upload.json",
            )
        except AdapterError as exc:
            raise SourceVideoWorkflowError(
                "飞影音频驱动模式需要公网可访问的成片声音 URL；请配置 OSS/COS 自动上传，"
                "或在任务 metadata 中填写 voice_audio_url。"
            ) from exc
        return upload_result.public_url

    def _save_source_video_public_url(self, profile, updates: dict[str, Any]) -> None:
        metadata = dict(profile.metadata or {})
        source_meta = dict(metadata.get("source_video") or {})
        source_meta.update(updates)
        source_meta["updated_at"] = datetime.now(timezone.utc).isoformat()
        metadata["source_video"] = source_meta
        profile.metadata = metadata
        self.digital_store.save(profile)

    async def _assemble_final(self, task_dir: Path, lip_synced: Path, script_json: Path) -> Path:
        final_video = task_dir / "final.mp4"
        try:
            if self.settings.dry_run:
                write_placeholder_binary(final_video, f"source_video_final={lip_synced}")
            elif self.ffmpeg_path:
                shutil.copyfile(lip_synced, final_video)
            else:
                shutil.copyfile(lip_synced, final_video)
            write_json(
                task_dir / "final_assembly_report.json",
                {"status": "completed", "source": str(lip_synced), "final_video": str(final_video), "script_json": str(script_json)},
            )
        except Exception as exc:  # noqa: BLE001 - final fallback policy is required.
            shutil.copyfile(lip_synced, final_video)
            write_json(
                task_dir / "final_assembly_report.json",
                {"status": "warning", "source": str(lip_synced), "final_video": str(final_video), "warning": str(exc), "fallback_used": True},
            )
        return final_video

    def _hifly_video_url(self, digital_human_id: str, explicit_url: str | None, metadata: dict[str, Any]) -> str:
        profile = self.digital_store.get(digital_human_id)
        values = [
            explicit_url,
            metadata.get("video_url") if isinstance(metadata, dict) else None,
            metadata.get("source_video_url") if isinstance(metadata, dict) else None,
            metadata.get("hifly_video_url") if isinstance(metadata, dict) else None,
        ]
        source_meta = (profile.metadata or {}).get("source_video")
        if isinstance(source_meta, dict):
            values.extend([source_meta.get("public_url"), source_meta.get("video_url"), source_meta.get("source_video_url")])
        for value in values:
            if value:
                return str(value)
        if self.settings.dry_run:
            return str(self.source_video_path(digital_human_id))
        return self._auto_upload_hifly_video_url(digital_human_id)

    def _hifly_audio_url(self, digital_human_id: str, explicit_url: str | None, metadata: dict[str, Any]) -> str:
        profile = self.digital_store.get(digital_human_id)
        values = [
            explicit_url,
            metadata.get("audio_url") if isinstance(metadata, dict) else None,
            metadata.get("source_audio_url") if isinstance(metadata, dict) else None,
            metadata.get("hifly_audio_url") if isinstance(metadata, dict) else None,
        ]
        source_meta = (profile.metadata or {}).get("source_video")
        if isinstance(source_meta, dict):
            values.extend([source_meta.get("public_audio_url"), source_meta.get("audio_url"), source_meta.get("source_audio_url")])
        for value in values:
            if value:
                return str(value)
        if self.settings.dry_run:
            return str(self.source_dir(digital_human_id) / "clean_voice_sample.wav")
        return self._auto_upload_hifly_audio_url(digital_human_id)


def _write_source_video_script(task_dir: Path, task: VideoTask) -> Path:
    text = task.request.fixed_script or task.request.topic
    duration = max(3, min(task.request.duration_seconds, max(3, len(text) // 5)))
    metadata = task.request.metadata if isinstance(task.request.metadata, dict) else {}
    voice_style = _normalize_voice_style(metadata.get("voice_style", "natural"))
    speech_rate = _normalize_speech_rate(metadata.get("speech_rate", 1.0))
    return write_json(
        task_dir / "script.json",
        {
            "title": task.request.topic,
            "body": text,
            "voice_style": voice_style,
            "speech_rate": speech_rate,
            "voice_options": {"voice_style": voice_style, "speech_rate": speech_rate},
            "segments": [{"start": 0, "end": duration, "text": text, "voice_style": voice_style, "speech_rate": speech_rate}],
            "source": "source_video_voice_clone_lipsync",
            "policy": "original source video audio is only a clone sample; final voice.wav is newly synthesized",
        },
    )


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
    return round(max(0.5, min(2.0, rate)), 1)


def _script_text(script_json: Path) -> str:
    data = read_json(script_json)
    segments = data.get("segments") or []
    if segments:
        return "\n".join(str(item.get("text", "")).strip() for item in segments if item.get("text"))
    return str(data.get("body") or data.get("title") or "")


def _task_object_storage_key(settings: Settings, *, task_id: str, filename: str) -> str:
    prefix = (settings.object_storage_prefix or "aivo").strip().strip("/")
    parts = ["tasks", task_id, filename]
    if prefix:
        parts.insert(0, prefix)
    return posixpath.join(*parts)


def _source_video_object_storage_key(settings: Settings, *, project_id: str, digital_human_id: str, filename: str) -> str:
    prefix = (settings.object_storage_prefix or "aivo").strip().strip("/")
    parts = ["projects", project_id, "digital_humans", digital_human_id, "source_video", filename]
    if prefix:
        parts.insert(0, prefix)
    return posixpath.join(*parts)


def _upload_metadata(upload_result) -> dict[str, Any]:
    return {
        "provider": upload_result.provider,
        "key": upload_result.key,
        "public_url": upload_result.public_url,
        "local_copy_path": upload_result.local_copy_path,
        "report_path": upload_result.report_path,
    }


def _hifly_warnings(dry_run: bool, video_url: str, audio_url: str) -> list[str]:
    warnings: list[str] = []
    if dry_run:
        warnings.append("dry-run placeholder video; no Hifly credits consumed")
    if not str(video_url).startswith(("http://", "https://")):
        warnings.append("video_url is not a public HTTP URL; real Hifly calls require reachable media")
    if not str(audio_url).startswith(("http://", "https://")):
        warnings.append("audio_url is not a public HTTP URL; real Hifly calls require reachable media")
    return warnings


def _probe_media(path: Path, ffprobe_path: str | None, *, dry_run: bool) -> dict[str, Any]:
    fallback = _dry_run_probe(path)
    if not path.exists():
        return {**fallback, "readable": False, "has_video_stream": False, "has_audio_stream": False}
    if not ffprobe_path:
        return fallback
    try:
        result = subprocess.run(
            [
                ffprobe_path,
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if result.returncode != 0:
            return fallback if dry_run else {**fallback, "readable": False}
        data = json.loads(result.stdout or "{}")
        streams = data.get("streams") or []
        video_stream = next((item for item in streams if item.get("codec_type") == "video"), {})
        audio_stream = next((item for item in streams if item.get("codec_type") == "audio"), {})
        duration = data.get("format", {}).get("duration") or video_stream.get("duration") or audio_stream.get("duration") or 0
        return {
            "readable": True,
            "has_video_stream": bool(video_stream),
            "has_audio_stream": bool(audio_stream),
            "duration_seconds": float(duration or 0),
            "width": int(video_stream.get("width") or 0),
            "height": int(video_stream.get("height") or 0),
        }
    except Exception:
        return fallback if dry_run else {**fallback, "readable": False}


def _dry_run_probe(path: Path) -> dict[str, Any]:
    marker = ""
    if path.exists():
        marker = path.read_bytes()[:512].decode("utf-8", errors="ignore").upper()
    return {
        "readable": False,
        "has_video_stream": "NO_VIDEO" not in marker,
        "has_audio_stream": "NO_AUDIO" not in marker,
        "duration_seconds": 5.0 if "SHORT" in marker else 12.0,
        "width": 640 if "LOWRES" in marker else 1080,
        "height": 360 if "LOWRES" in marker else 1920,
    }


def _run_command(command: list[str], stdout_path: Path, stderr_path: Path) -> None:
    ensure_dir(stdout_path.parent)
    result = subprocess.run(command, capture_output=True, text=True, timeout=600, check=False)
    stdout_path.write_text(result.stdout, encoding="utf-8")
    stderr_path.write_text(result.stderr, encoding="utf-8")
    if result.returncode != 0:
        raise SourceVideoWorkflowError(f"command failed with exit code {result.returncode}: {' '.join(command)}")


def _find_ffmpeg(configured_path: str | None = None) -> str | None:
    if configured_path:
        return configured_path
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg
    imageio_ffmpeg = _imageio_ffmpeg_path()
    if imageio_ffmpeg:
        return imageio_ffmpeg
    for candidate in _bundled_ffmpeg_candidates():
        if candidate.exists():
            return str(candidate)
    return None


def _imageio_ffmpeg_path() -> str | None:
    try:
        imageio_ffmpeg = importlib.import_module("imageio_ffmpeg")
        ffmpeg_path = str(imageio_ffmpeg.get_ffmpeg_exe())
        return ffmpeg_path if ffmpeg_path else None
    except Exception:
        return None


def _bundled_ffmpeg_candidates() -> list[Path]:
    module_dir = Path(__file__).resolve().parent
    roots = [
        module_dir,
        *module_dir.parents,
    ]
    candidates: list[Path] = []
    for root in roots:
        candidates.extend(
            [
                root / "extraResources" / "ffmpeg" / "ffmpeg.exe",
                root / "resources" / "extraResources" / "ffmpeg" / "ffmpeg.exe",
                root / "ffmpeg" / "ffmpeg.exe",
            ]
        )
    return candidates


def _sibling_ffprobe(ffmpeg_path: str | None) -> str | None:
    if not ffmpeg_path:
        return None
    ffmpeg = Path(ffmpeg_path)
    candidate = ffmpeg.with_name("ffprobe.exe" if ffmpeg.suffix.lower() == ".exe" else "ffprobe")
    return str(candidate) if candidate.exists() else None
