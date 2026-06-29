import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from app.adapters.base import AdapterError, minimal_script_payload
from app.adapters.avatar_render import DryRunAvatarRenderAdapter
from app.adapters.baidu_xiling import BaiduXilingVideoAdapter
from app.adapters.cloud_lipsync import PixVerseLipSyncAdapter, SyncSoLipSyncAdapter
from app.adapters.cloud_video_render import FalVideoRenderAdapter
from app.adapters.cloud_voice import AliyunBailianVoiceAdapter
from app.adapters.jianying import JianyingDraftAdapter
from app.adapters.lipsync import LatentSyncAdapter, MuseTalkAdapter
from app.adapters.omnihuman import OmniHumanVideoAdapter
from app.adapters.tavus import TavusVideoAdapter
from app.adapters.tts import BaseTTSAdapter, DryRunTTSAdapter, EdgeTTSAdapter, HTTPTTSAdapter
from app.adapters.wav2lip import Wav2LipAdapter
from app.adapters.yy_wav2lip import YYWav2LipAdapter
from app.artifacts import write_artifact_manifest
from app.audit import append_audit_event
from app.cloud_providers import preferred_cloud_video_provider
from app.digital_humans import DigitalHumanStore
from app.render_profiles import get_render_profile
from app.schemas import DigitalHumanRoleModel, LipSyncEngine, RoleModelStatus, StepResult, TaskStatus, VideoTask
from app.script_generation import select_script_generator_adapter
from app.settings import Settings
from app.store import TaskStore
from app.utils.files import ensure_dir, read_json, write_json, write_placeholder_binary, write_text
from app.video_templates import TemplateAssemblyEngine, get_video_template


DIGITAL_HUMAN_PLAN = [
    "load_project_context",
    "load_digital_human_profile",
    "generate_or_load_avatar_image",
    "generate_script",
    "review_script",
    "synthesize_voice",
    "render_avatar_base_video",
    "enhance_lip_sync",
    "run_render_stability_check",
    "run_digital_human_quality_check",
    "assemble_final_video",
    "export_jianying_draft",
    "build_publish_handoff",
    "write_audit",
]


async def run_digital_human_pipeline(settings: Settings, store: TaskStore, task: VideoTask) -> VideoTask:
    task_dir = ensure_dir(store.task_dir(task.task_id))
    logs_path = task_dir / "pipeline.log"
    task.artifacts.logs = str(logs_path)
    store.update_status(task, TaskStatus.running)

    digital_store = DigitalHumanStore(settings)
    script_generator = select_script_generator_adapter(settings)
    template_engine = TemplateAssemblyEngine(dry_run=settings.dry_run)
    tts = _select_tts_adapter(settings)
    avatar_renderer = DryRunAvatarRenderAdapter()
    latentsync = LatentSyncAdapter(settings.latentsync_cli_path, dry_run=settings.dry_run)
    musetalk = MuseTalkAdapter(settings.musetalk_cli_path, dry_run=settings.dry_run)
    wav2lip = Wav2LipAdapter(
        source_root=settings.wav2lip_root,
        checkpoint_path=settings.wav2lip_checkpoint,
        python_executable=settings.wav2lip_python,
        timeout_seconds=settings.wav2lip_timeout_seconds,
        dry_run=settings.dry_run,
        enabled=settings.wav2lip_enabled,
    )
    yywav2lip = YYWav2LipAdapter(
        source_root=settings.wav2lip_root,
        checkpoint_path=settings.yy_wav2lip_checkpoint,
        role_model_dir=settings.yy_wav2lip_role_model_dir,
        python_executable=settings.wav2lip_python,
        timeout_seconds=settings.yy_wav2lip_timeout_seconds,
        dry_run=settings.dry_run,
        enabled=settings.yy_wav2lip_enabled,
    )
    if settings.cloud_lipsync_provider.lower() in {"pixverse", "pixverse_lipsync"}:
        syncso = PixVerseLipSyncAdapter(
            dry_run=settings.dry_run,
            enabled=settings.cloud_lipsync_enabled,
            base_url=settings.pixverse_base_url,
            api_key=settings.pixverse_api_key,
            model=settings.pixverse_model,
            generate_endpoint=settings.pixverse_generate_endpoint,
            task_endpoint_template=settings.pixverse_task_endpoint_template,
            timeout_seconds=settings.pixverse_timeout_seconds,
            poll_interval_seconds=settings.pixverse_poll_interval_seconds,
        )
    else:
        syncso = SyncSoLipSyncAdapter(
            dry_run=settings.dry_run,
            enabled=settings.cloud_lipsync_enabled and settings.cloud_lipsync_provider.lower() == "syncso",
            base_url=settings.syncso_base_url,
            api_key=settings.syncso_api_key,
            model=settings.syncso_model,
            generate_endpoint=settings.syncso_generate_endpoint,
            timeout_seconds=settings.syncso_timeout_seconds,
            poll_interval_seconds=settings.syncso_poll_interval_seconds,
        )
    fal_video = FalVideoRenderAdapter(
        dry_run=settings.dry_run,
        enabled=settings.cloud_video_provider in {"fal_latentsync", "fal_musetalk"},
        provider_id=preferred_cloud_video_provider(_render_profile_value(task), settings) or settings.cloud_video_provider,
        api_key=settings.fal_api_key,
        latentsync_model=settings.fal_latentsync_model,
        musetalk_model=settings.fal_musetalk_model,
        timeout_seconds=settings.syncso_timeout_seconds,
    )
    omnihuman = OmniHumanVideoAdapter(
        dry_run=settings.dry_run,
        enabled=settings.omnihuman_enabled,
        access_key=settings.omnihuman_access_key,
        secret_key=settings.omnihuman_secret_key,
        endpoint=settings.omnihuman_endpoint,
        region=settings.omnihuman_region,
        service=settings.omnihuman_service,
        version=settings.omnihuman_version,
        req_key=settings.omnihuman_req_key,
        output_resolution=settings.omnihuman_output_resolution,
        prompt=settings.omnihuman_prompt,
        pe_fast_mode=settings.omnihuman_pe_fast_mode,
        timeout_seconds=settings.omnihuman_timeout_seconds,
        poll_interval_seconds=settings.omnihuman_poll_interval_seconds,
    )
    tavus = TavusVideoAdapter(
        dry_run=settings.dry_run,
        enabled=settings.tavus_enabled,
        base_url=settings.tavus_base_url,
        api_key=settings.tavus_api_key,
        replica_id=settings.tavus_replica_id,
        video_endpoint=settings.tavus_video_endpoint,
        timeout_seconds=settings.tavus_timeout_seconds,
        poll_interval_seconds=settings.tavus_poll_interval_seconds,
    )
    baidu_xiling = BaiduXilingVideoAdapter(
        dry_run=settings.dry_run,
        enabled=settings.baidu_xiling_enabled or settings.cloud_video_provider == "baidu_xiling",
        base_url=settings.baidu_xiling_base_url,
        app_id=settings.baidu_xiling_app_id,
        app_key=settings.baidu_xiling_app_key,
        figure_id=settings.baidu_xiling_figure_id,
        tts_person=settings.baidu_xiling_tts_person,
        width=settings.baidu_xiling_width,
        height=settings.baidu_xiling_height,
        transparent=settings.baidu_xiling_transparent,
        timeout_seconds=settings.baidu_xiling_timeout_seconds,
        poll_interval_seconds=settings.baidu_xiling_poll_interval_seconds,
    )
    jianying = JianyingDraftAdapter(settings.jianying_draft_root, dry_run=settings.dry_run)
    log_lines = [
        f"task_id={task.task_id}",
        "pipeline=digital_human_13e",
        f"retry_from={task.request.retry_from}",
    ]

    try:
        if not task.request.digital_human_id:
            raise ValueError("digital_human_id is required for digital human pipeline")
        if not task.request.voice_profile_id:
            raise ValueError("voice_profile_id is required for digital human pipeline")

        profile = digital_store.get(task.request.digital_human_id)
        voice = digital_store.get_voice_profile_for_project(profile.project_id, task.request.voice_profile_id)
        render_profile = get_render_profile(task.request.render_profile)
        role_model = None
        if render_profile.name == "compat":
            if not task.request.role_model_id:
                raise ValueError("role_model_id is required for compat render_profile")
            role_model = digital_store.get_role_model(profile.digital_human_id, task.request.role_model_id)
            if role_model.status != RoleModelStatus.ready and not settings.dry_run:
                raise ValueError(f"role model is not ready: {role_model.role_model_id}")

        append_audit_event(
            settings.storage_dir,
            action="render_job.started",
            task_id=task.task_id,
            project_id=profile.project_id,
            digital_human_id=profile.digital_human_id,
            details={"render_profile": render_profile.name},
        )

        project_context = await _step(
            store,
            task,
            "load_project_context",
            _write_project_context(task_dir, profile.project_id, task),
            log_lines,
        )
        task.artifacts.project_context = str(project_context)

        profile_path = await _step(
            store,
            task,
            "load_digital_human_profile",
            _write_profile(task_dir, profile),
            log_lines,
        )
        task.artifacts.digital_human_profile = str(profile_path)

        avatar_image = await _step(
            store,
            task,
            "generate_or_load_avatar_image",
            _avatar_image(task_dir, profile),
            log_lines,
        )
        task.artifacts.avatar_image = str(avatar_image)

        script_json = await _maybe_run(
            store,
            task,
            "generate_script",
            task_dir / "script.json",
            lambda: _generate_script_or_manual_fallback(script_generator, task.request, task_dir),
            log_lines,
        )
        _apply_voice_controls_to_script(task, script_json)
        task.artifacts.script_json = str(script_json)

        subtitles = await _step(store, task, "write_subtitles", _write_subtitles(task_dir, script_json), log_lines)
        task.artifacts.subtitles_srt = str(subtitles)
        script_quality = await _step(
            store,
            task,
            "run_script_quality_check",
            _write_script_quality_report(task_dir, script_json),
            log_lines,
        )
        task.artifacts.script_quality_report = str(script_quality)

        if task.request.script_review_required and not task.request.metadata.get("script_approved"):
            task.status = TaskStatus.waiting_for_review
            write_artifact_manifest(task_dir)
            task.artifacts.artifact_manifest = str(task_dir / "artifact_manifest.json")
            write_text(logs_path, "\n".join(log_lines) + "\nwaiting_for_review=true\n")
            return store.save(task)

        if _use_tavus_full_video(settings, task):
            tavus_video = await _maybe_tavus_full_video(
                store,
                task,
                task_dir,
                tavus,
                script_json,
                profile,
                voice,
                log_lines,
            )
            tavus_reports = _write_tavus_pipeline_reports(task_dir, task, profile, voice, tavus_video, tavus)
            task.artifacts.voice_segments = str(tavus_reports["voice_segments"])
            task.artifacts.voice_metadata = str(tavus_reports["voice_metadata"])
            task.artifacts.audio_quality_report = str(tavus_reports["audio_quality_report"])
            task.artifacts.avatar_base_video = str(tavus_video)
            task.artifacts.avatar_video = str(tavus_video)
            task.artifacts.avatar_render_metadata = str(tavus_reports["avatar_render_metadata"])
            task.artifacts.avatar_render_report = str(tavus_reports["avatar_render_report"])
            task.artifacts.lip_synced_video = str(tavus_video)
            task.artifacts.lip_sync_report = str(tavus_reports["lip_sync_report"])
            lip_synced = tavus_video
            append_audit_event(
                settings.storage_dir,
                action="voice.synthesized",
                task_id=task.task_id,
                project_id=profile.project_id,
                digital_human_id=profile.digital_human_id,
                details={"voice_profile_id": voice.voice_profile_id, "engine": "tavus_replica"},
            )
            append_audit_event(
                settings.storage_dir,
                action="avatar.rendered",
                task_id=task.task_id,
                project_id=profile.project_id,
                digital_human_id=profile.digital_human_id,
                details={"engine": "tavus_replica", "replica_id": _tavus_replica_id(task, tavus)},
            )
            append_audit_event(
                settings.storage_dir,
                action="lip_sync.completed",
                task_id=task.task_id,
                project_id=profile.project_id,
                digital_human_id=profile.digital_human_id,
                details=read_json(task_dir / "lip_sync_report.json"),
            )
        else:
            tts_result = await _maybe_tts(store, task, task_dir, script_json, voice, tts, log_lines, settings=settings)
            task.artifacts.voice_audio = str(tts_result.audio_path)
            task.artifacts.voice_segments = str(tts_result.segments_path)
            task.artifacts.voice_metadata = str(tts_result.metadata_path)
            audio_quality = await _step(
                store,
                task,
                "run_audio_quality_check",
                _write_audio_quality_report(task_dir, tts_result.audio_path),
                log_lines,
            )
            task.artifacts.audio_quality_report = str(audio_quality)
            append_audit_event(
                settings.storage_dir,
                action="voice.synthesized",
                task_id=task.task_id,
                project_id=profile.project_id,
                digital_human_id=profile.digital_human_id,
                details={"voice_profile_id": voice.voice_profile_id},
            )

            if render_profile.name == "compat" and role_model:
                avatar_result = await _maybe_role_model_avatar_render(
                    store,
                    task,
                    task_dir,
                    role_model,
                    render_profile.name,
                    _avatar_fallback_used(render_profile.avatar_engines),
                    log_lines,
                    dry_run=settings.dry_run,
                )
            elif selected_avatar_video := _selected_avatar_video(profile):
                avatar_result = await _maybe_uploaded_avatar_video(
                    store,
                    task,
                    task_dir,
                    selected_avatar_video,
                    render_profile.name,
                    log_lines,
                )
            else:
                avatar_result = await _maybe_avatar_render(
                    store,
                    task,
                    task_dir,
                    avatar_renderer,
                    avatar_image,
                    tts_result.audio_path,
                    render_profile.name,
                    _avatar_fallback_used(render_profile.avatar_engines),
                    log_lines,
                    duration_seconds=task.request.duration_seconds if not settings.dry_run else 3,
                )
            task.artifacts.avatar_base_video = str(avatar_result.video_path)
            task.artifacts.avatar_video = str(avatar_result.video_path)
            task.artifacts.avatar_render_metadata = str(avatar_result.metadata_path)
            task.artifacts.avatar_render_report = str(avatar_result.report_path)
            append_audit_event(
                settings.storage_dir,
                action="avatar.rendered",
                task_id=task.task_id,
                project_id=profile.project_id,
                digital_human_id=profile.digital_human_id,
                details={"engine": avatar_result.engine_used},
            )

            lip_synced = await _maybe_lip_sync(
                store,
                task,
                task_dir,
                avatar_result.video_path,
                tts_result.audio_path,
                render_profile.lip_sync_engines,
                latentsync,
                musetalk,
                wav2lip,
                yywav2lip,
                syncso,
                fal_video,
                baidu_xiling,
                omnihuman,
                role_model,
                profile,
                voice,
                script_json,
                log_lines,
            )
            task.artifacts.lip_synced_video = str(lip_synced)
            append_audit_event(
                settings.storage_dir,
                action="lip_sync.completed",
                task_id=task.task_id,
                project_id=profile.project_id,
                digital_human_id=profile.digital_human_id,
                details=read_json(task_dir / "lip_sync_report.json"),
            )

        video_template = get_video_template(task.request.video_template_id)
        template_result = await _maybe_template_assemble(
            store,
            task,
            task_dir,
            "assemble_final_video",
            lip_synced,
            script_json,
            video_template,
            template_engine,
            log_lines,
        )
        final_video = template_result.final_video
        task.artifacts.final_video = str(template_result.final_video)
        task.artifacts.cover_image = str(template_result.cover_image)
        task.artifacts.template_report = str(template_result.template_report)
        append_audit_event(
            settings.storage_dir,
            action="video_template.applied",
            task_id=task.task_id,
            project_id=profile.project_id,
            digital_human_id=profile.digital_human_id,
            details={
                "video_template_id": video_template.template_id,
                "final_video": str(template_result.final_video),
                "cover_image": str(template_result.cover_image),
                "template_report": str(template_result.template_report),
            },
        )

        render_job = await _step(
            store,
            task,
            "write_render_job",
            _write_render_job(task_dir, task, render_profile.name, video_template.template_id),
            log_lines,
        )
        task.artifacts.render_job = str(render_job)
        render_report = await _step(
            store,
            task,
            "run_render_stability_check",
            _write_render_stability_report(task_dir, render_profile.name, video_template.template_id),
            log_lines,
        )
        task.artifacts.render_stability_report = str(render_report)
        append_audit_event(
            settings.storage_dir,
            action="render.stability_report_generated",
            task_id=task.task_id,
            project_id=profile.project_id,
            digital_human_id=profile.digital_human_id,
        )

        quality_report = await _step(
            store,
            task,
            "run_digital_human_quality_check",
            _write_digital_human_quality_report(task_dir, profile, voice, render_profile.name, video_template.template_id),
            log_lines,
        )
        task.artifacts.digital_human_quality_report = str(quality_report)

        if task.request.export_jianying_draft:
            try:
                draft = await _maybe_run(
                    store,
                    task,
                    "export_jianying_draft",
                    task_dir / "jianying_draft",
                    lambda: jianying.export_draft(final_video, script_json, task_dir, template_report=template_result.template_report),
                    log_lines,
                    directory=True,
                )
                task.artifacts.jianying_draft = str(draft)
            except Exception as exc:
                if task.request.strict_jianying:
                    raise
                log_lines.append(f"export_jianying_draft warning={exc}")

        publish_package = await _step(
            store,
            task,
            "build_publish_handoff",
            _write_publish_package(task_dir, task, profile, voice, render_profile.name, video_template.template_id),
            log_lines,
        )
        task.artifacts.publish_package = str(publish_package)

        append_audit_event(
            settings.storage_dir,
            action="digital_human.video_completed",
            task_id=task.task_id,
            project_id=profile.project_id,
            digital_human_id=profile.digital_human_id,
            details={"final_video": str(final_video)},
        )
        append_audit_event(
            settings.storage_dir,
            action="render_job.succeeded",
            task_id=task.task_id,
            project_id=profile.project_id,
            digital_human_id=profile.digital_human_id,
        )

        manifest = write_artifact_manifest(task_dir)
        task.artifacts.artifact_manifest = str(manifest)
        write_text(logs_path, "\n".join(log_lines) + "\n")
        store.update_status(task, TaskStatus.completed)
        return store.save(task)
    except Exception as exc:
        task.error = str(exc)
        write_text(logs_path, "\n".join(log_lines) + f"\nERROR: {exc}\n")
        store.update_status(task, TaskStatus.failed, error=str(exc))
        append_audit_event(settings.storage_dir, action="render_job.failed", task_id=task.task_id, details={"error": str(exc)})
        return store.save(task)


async def _generate_script_or_manual_fallback(script_generator, request, task_dir: Path) -> Path:
    try:
        return await script_generator.generate_script(request, task_dir)
    except AdapterError as exc:
        message = str(exc)
        if "real script generation is not configured" not in message:
            raise
        payload = minimal_script_payload(request)
        payload["source_policy"] = (
            "manual topic/script fallback; no cloud script generator configured. "
            "This is not an AI-generated script."
        )
        payload["llm"] = {
            "engine": getattr(script_generator, "name", "unconfigured"),
            "fallback_used": "manual_topic_or_fixed_script",
            "reason": message,
        }
        return write_json(task_dir / "script.json", payload)


def _apply_voice_controls_to_script(task: VideoTask, script_json: Path) -> None:
    metadata = task.request.metadata if isinstance(task.request.metadata, dict) else {}
    voice_style = _normalize_voice_style(metadata.get("voice_style", "natural"))
    speech_rate = _normalize_speech_rate(metadata.get("speech_rate", 1.0))
    try:
        payload = read_json(script_json)
    except Exception:
        return
    payload["voice_style"] = voice_style
    payload["speech_rate"] = speech_rate
    payload.setdefault("voice_options", {})
    if isinstance(payload["voice_options"], dict):
        payload["voice_options"].update({"voice_style": voice_style, "speech_rate": speech_rate})
    segments = payload.get("segments")
    if isinstance(segments, list):
        for segment in segments:
            if isinstance(segment, dict):
                segment.setdefault("voice_style", voice_style)
                segment.setdefault("speech_rate", speech_rate)
    write_json(script_json, payload)


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


async def _step(
    store: TaskStore,
    task: VideoTask,
    name: str,
    result: Path,
    log_lines: list[str],
) -> Path:
    started = datetime.now(timezone.utc)
    step = StepResult(name=name, status="completed", started_at=started, finished_at=datetime.now(timezone.utc), message="ok")
    step.artifacts["path"] = str(result)
    task.steps.append(step)
    log_lines.append(f"{name}=completed path={result}")
    store.save(task)
    return result


async def _maybe_run(
    store: TaskStore,
    task: VideoTask,
    name: str,
    expected: Path,
    awaitable_factory: Callable[[], Awaitable[Path]],
    log_lines: list[str],
    *,
    directory: bool = False,
) -> Path:
    if _valid(expected, directory=directory) and not task.request.force_render:
        log_lines.append(f"{name}=skipped existing={expected}")
        return expected
    started = datetime.now(timezone.utc)
    step = StepResult(name=name, status="running", started_at=started)
    task.steps.append(step)
    store.save(task)
    try:
        result = await awaitable_factory()
        step.status = "completed"
        step.finished_at = datetime.now(timezone.utc)
        step.message = "ok"
        step.artifacts["path"] = str(result)
        log_lines.append(f"{name}=completed path={result}")
        store.save(task)
        return result
    except Exception as exc:
        step.status = "failed"
        step.finished_at = datetime.now(timezone.utc)
        step.message = str(exc)
        store.save(task)
        raise


async def _maybe_template_assemble(
    store: TaskStore,
    task: VideoTask,
    task_dir: Path,
    name: str,
    lip_synced: Path,
    script_json: Path,
    video_template,
    template_engine: TemplateAssemblyEngine,
    log_lines: list[str],
):
    expected_final = task_dir / "final.mp4"
    expected_cover = task_dir / "cover.png"
    expected_report = task_dir / "template_report.json"
    if all(_valid(path) for path in (expected_final, expected_cover, expected_report)) and not task.request.force_render:
        log_lines.append(f"{name}=skipped existing={expected_final} template={video_template.template_id}")
        return type(
            "TemplateAssemblyCachedResult",
            (),
            {
                "final_video": expected_final,
                "cover_image": expected_cover,
                "template_report": expected_report,
                "template_id": video_template.template_id,
                "ffmpeg_used": False,
            },
        )()

    started = datetime.now(timezone.utc)
    step = StepResult(name=name, status="running", started_at=started)
    task.steps.append(step)
    store.save(task)
    try:
        result = template_engine.assemble(
            source_video=lip_synced,
            script_json=script_json,
            template=video_template,
            out_dir=task_dir,
        )
        step.status = "completed"
        step.finished_at = datetime.now(timezone.utc)
        step.message = f"template={video_template.template_id}"
        step.artifacts["final_video"] = str(result.final_video)
        step.artifacts["cover_image"] = str(result.cover_image)
        step.artifacts["template_report"] = str(result.template_report)
        log_lines.append(f"{name}=completed path={result.final_video} template={video_template.template_id}")
        store.save(task)
        return result
    except Exception as exc:
        step.status = "failed"
        step.finished_at = datetime.now(timezone.utc)
        step.message = str(exc)
        store.save(task)
        raise


async def _maybe_tts(
    store: TaskStore,
    task: VideoTask,
    task_dir: Path,
    script_json: Path,
    voice,
    tts: BaseTTSAdapter,
    log_lines: list[str],
    *,
    settings: Settings | None = None,
):
    expected = task_dir / "voice.wav"
    if _valid(expected) and not task.request.force_render:
        log_lines.append(f"synthesize_voice=skipped existing={expected}")
        return type(
            "TTSCachedResult",
            (),
            {
                "audio_path": expected,
                "segments_path": task_dir / "voice_segments.json",
                "metadata_path": task_dir / "voice_metadata.json",
            },
        )()
    step = StepResult(name="synthesize_voice", status="running", started_at=datetime.now(timezone.utc))
    task.steps.append(step)
    store.save(task)
    if settings and str(getattr(voice, "voice_source_type", "")).endswith("cloud_clone"):
        tts = _select_tts_adapter(settings, voice)
    result = await tts.synthesize(script_json=script_json, voice_profile=voice, out_dir=task_dir)
    step.status = "completed"
    step.finished_at = datetime.now(timezone.utc)
    step.message = "ok"
    step.artifacts["path"] = str(result.audio_path)
    log_lines.append(f"synthesize_voice=completed path={result.audio_path}")
    store.save(task)
    return result


async def _maybe_avatar_render(
    store: TaskStore,
    task: VideoTask,
    task_dir: Path,
    renderer: DryRunAvatarRenderAdapter,
    avatar_image: Path,
    voice_audio: Path,
    render_profile: str,
    fallback_used: list[str],
    log_lines: list[str],
    *,
    duration_seconds: int | None = None,
):
    expected = task_dir / "avatar_base.mp4"
    if _valid(expected) and not task.request.force_render:
        log_lines.append(f"render_avatar_base_video=skipped existing={expected}")
        return type(
            "AvatarCachedResult",
            (),
            {
                "video_path": expected,
                "metadata_path": task_dir / "avatar_render_metadata.json",
                "report_path": task_dir / "avatar_render_report.json",
                "engine_used": "static",
                "fallback_used": fallback_used,
            },
        )()
    step = StepResult(name="render_avatar_base_video", status="running", started_at=datetime.now(timezone.utc))
    task.steps.append(step)
    store.save(task)
    result = await renderer.render_base_video(
        avatar_image_path=avatar_image,
        voice_audio_path=voice_audio,
        output_path=expected,
        render_profile=render_profile,
        options={"fallback_used": fallback_used, "duration_seconds": duration_seconds or task.request.duration_seconds},
        task_dir=task_dir,
    )
    step.status = "completed"
    step.finished_at = datetime.now(timezone.utc)
    step.message = "ok"
    step.artifacts["path"] = str(result.video_path)
    log_lines.append(f"render_avatar_base_video=completed path={result.video_path}")
    store.save(task)
    return result


async def _maybe_role_model_avatar_render(
    store: TaskStore,
    task: VideoTask,
    task_dir: Path,
    role_model: DigitalHumanRoleModel,
    render_profile: str,
    fallback_used: list[str],
    log_lines: list[str],
    *,
    dry_run: bool,
):
    expected = task_dir / "avatar_base.mp4"
    metadata_path = task_dir / "avatar_render_metadata.json"
    report_path = task_dir / "avatar_render_report.json"
    if _valid(expected) and not task.request.force_render:
        log_lines.append(f"render_avatar_base_video=skipped existing={expected}")
        return type(
            "RoleModelCachedResult",
            (),
            {
                "video_path": expected,
                "metadata_path": metadata_path,
                "report_path": report_path,
                "engine_used": "role_model",
                "fallback_used": fallback_used,
            },
        )()

    step = StepResult(name="render_avatar_base_video", status="running", started_at=datetime.now(timezone.utc))
    task.steps.append(step)
    store.save(task)
    source_video = _role_model_video(role_model)
    if source_video and source_video.exists():
        shutil.copyfile(source_video, expected)
    elif dry_run:
        write_placeholder_binary(expected, f"role-model={role_model.role_model_id}")
    else:
        raise ValueError(f"role model video asset missing for {role_model.role_model_id}")

    write_json(
        metadata_path,
        {
            "engine": "role_model",
            "role_model_id": role_model.role_model_id,
            "engine_type": role_model.engine_type,
            "source_video": str(source_video) if source_video else None,
            "pkl_model_path": role_model.pkl_model_path,
            "render_profile": render_profile,
        },
    )
    write_json(
        report_path,
        {
            "status": "completed",
            "engine_used": "role_model",
            "role_model_id": role_model.role_model_id,
            "fallback_used": fallback_used,
            "readable": False,
            "warnings": ["role model compatibility dry-run media may not be ffprobe-readable"],
        },
    )
    step.status = "completed"
    step.finished_at = datetime.now(timezone.utc)
    step.message = "ok"
    step.artifacts["path"] = str(expected)
    log_lines.append(f"render_avatar_base_video=completed role_model={role_model.role_model_id} path={expected}")
    store.save(task)
    return type(
        "RoleModelRenderResult",
        (),
        {
            "video_path": expected,
            "metadata_path": metadata_path,
            "report_path": report_path,
            "engine_used": "role_model",
            "fallback_used": fallback_used,
        },
    )()


async def _maybe_uploaded_avatar_video(
    store: TaskStore,
    task: VideoTask,
    task_dir: Path,
    source_video: Path,
    render_profile: str,
    log_lines: list[str],
):
    expected = task_dir / "avatar_base.mp4"
    metadata_path = task_dir / "avatar_render_metadata.json"
    report_path = task_dir / "avatar_render_report.json"
    if _valid(expected) and not task.request.force_render:
        log_lines.append(f"render_avatar_base_video=skipped existing={expected}")
        return type(
            "UploadedAvatarCachedResult",
            (),
            {
                "video_path": expected,
                "metadata_path": metadata_path,
                "report_path": report_path,
                "engine_used": "uploaded_avatar_video",
                "fallback_used": [],
            },
        )()

    step = StepResult(name="render_avatar_base_video", status="running", started_at=datetime.now(timezone.utc))
    task.steps.append(step)
    store.save(task)
    shutil.copyfile(source_video, expected)
    write_json(
        metadata_path,
        {
            "engine": "uploaded_avatar_video",
            "source_video": str(source_video),
            "render_profile": render_profile,
            "policy": "customer-uploaded video is used as the digital human base video",
        },
    )
    write_json(
        report_path,
        {
            "status": "completed",
            "engine_used": "uploaded_avatar_video",
            "source_video": str(source_video),
            "readable": expected.exists() and expected.stat().st_size > 0,
            "fallback_used": [],
            "warnings": [],
        },
    )
    step.status = "completed"
    step.finished_at = datetime.now(timezone.utc)
    step.message = "ok"
    step.artifacts["path"] = str(expected)
    log_lines.append(f"render_avatar_base_video=completed uploaded_video={source_video} path={expected}")
    store.save(task)
    return type(
        "UploadedAvatarVideoResult",
        (),
        {
            "video_path": expected,
            "metadata_path": metadata_path,
            "report_path": report_path,
            "engine_used": "uploaded_avatar_video",
            "fallback_used": [],
        },
    )()


def _use_tavus_full_video(settings: Settings, task: VideoTask) -> bool:
    provider = str(task.request.metadata.get("video_provider") or task.request.metadata.get("digital_human_provider") or "").lower()
    return bool(not settings.dry_run and (settings.tavus_enabled or provider == "tavus"))


def _tavus_replica_id(task: VideoTask, tavus: TavusVideoAdapter) -> str:
    return str(task.request.metadata.get("tavus_replica_id") or tavus.replica_id or "")


async def _maybe_tavus_full_video(
    store: TaskStore,
    task: VideoTask,
    task_dir: Path,
    tavus: TavusVideoAdapter,
    script_json: Path,
    profile,
    voice,
    log_lines: list[str],
) -> Path:
    expected = task_dir / "tavus_video.mp4"
    replica_id = _tavus_replica_id(task, tavus)
    return await _maybe_run(
        store,
        task,
        "generate_tavus_video",
        expected,
        lambda: tavus.generate_video(
            script_json,
            task_dir,
            replica_id=replica_id,
            video_name=f"Aivo-{task.task_id}",
            metadata={
                "task_id": task.task_id,
                "project_id": profile.project_id,
                "digital_human_id": profile.digital_human_id,
                "voice_profile_id": voice.voice_profile_id,
            },
        ),
        log_lines,
    )


def _write_tavus_pipeline_reports(task_dir: Path, task: VideoTask, profile, voice, tavus_video: Path, tavus: TavusVideoAdapter) -> dict[str, Path]:
    replica_id = _tavus_replica_id(task, tavus)
    voice_segments = write_json(
        task_dir / "voice_segments.json",
        {
            "engine": "tavus_replica",
            "audio_source": "tavus_cloud",
            "segments": [],
            "note": "Tavus custom replica generated speech inside the cloud video; no local voice.wav is required.",
        },
    )
    voice_metadata = write_json(
        task_dir / "voice_metadata.json",
        {
            "engine": "tavus_replica",
            "voice_source_type": voice.voice_source_type,
            "voice_profile_id": voice.voice_profile_id,
            "audio_source": "tavus_cloud",
            "replica_id": replica_id,
            "local_voice_audio": None,
            "readable": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    audio_quality_report = write_json(
        task_dir / "audio_quality_report.json",
        {
            "status": "completed",
            "engine": "tavus_replica",
            "audio_readable": True,
            "audio_source": "tavus_cloud_video",
            "local_voice_audio_required": False,
            "warnings": [],
        },
    )
    avatar_render_metadata = write_json(
        task_dir / "avatar_render_metadata.json",
        {
            "engine": "tavus_replica",
            "replica_id": replica_id,
            "digital_human_id": profile.digital_human_id,
            "output": str(tavus_video),
            "render_profile": task.request.render_profile,
        },
    )
    avatar_render_report = write_json(
        task_dir / "avatar_render_report.json",
        {
            "status": "completed",
            "engine_used": "tavus_replica",
            "replica_id": replica_id,
            "readable": tavus_video.exists() and tavus_video.stat().st_size > 0,
            "fallback_used": [],
            "warnings": [],
        },
    )
    lip_sync_report = write_json(
        task_dir / "lip_sync_report.json",
        {
            "status": "completed",
            "engine_used": "tavus",
            "source_video": str(tavus_video),
            "voice_audio": "tavus_cloud",
            "output": str(tavus_video),
            "replica_id": replica_id,
            "fallback_used": [],
        },
    )
    return {
        "voice_segments": voice_segments,
        "voice_metadata": voice_metadata,
        "audio_quality_report": audio_quality_report,
        "avatar_render_metadata": avatar_render_metadata,
        "avatar_render_report": avatar_render_report,
        "lip_sync_report": lip_sync_report,
    }


async def _maybe_lip_sync(
    store: TaskStore,
    task: VideoTask,
    task_dir: Path,
    avatar_video: Path,
    voice_audio: Path,
    engines: tuple[str, ...],
    latentsync: LatentSyncAdapter,
    musetalk: MuseTalkAdapter,
    wav2lip: Wav2LipAdapter,
    yywav2lip: YYWav2LipAdapter,
    syncso: SyncSoLipSyncAdapter,
    fal_video: FalVideoRenderAdapter,
    baidu_xiling: BaiduXilingVideoAdapter,
    omnihuman: OmniHumanVideoAdapter,
    role_model: DigitalHumanRoleModel | None,
    profile,
    voice,
    script_json: Path,
    log_lines: list[str],
) -> Path:
    expected = task_dir / "lip_synced.mp4"
    if _valid(expected) and not task.request.force_render:
        log_lines.append(f"enhance_lip_sync=skipped existing={expected}")
        return expected

    chosen = task.request.lip_sync_engine_preference or _choose_lip_sync_engine(
        engines,
        role_model,
        syncso,
        omnihuman,
        fal_video,
        baidu_xiling,
        render_profile=_render_profile_value(task),
        has_public_urls=_has_public_lipsync_urls(task, profile, voice),
    )
    if chosen == LipSyncEngine.latentsync or chosen == "latentsync":
        result = await _maybe_run(
            store,
            task,
            "enhance_lip_sync",
            expected,
            lambda: latentsync.sync_lip(avatar_video, voice_audio, task_dir),
            log_lines,
        )
    elif chosen == LipSyncEngine.musetalk or chosen == "musetalk":
        result = await _maybe_run(
            store,
            task,
            "enhance_lip_sync",
            expected,
            lambda: musetalk.sync_lip(avatar_video, voice_audio, task_dir),
            log_lines,
        )
    elif chosen == LipSyncEngine.yywav2lip or chosen == "yywav2lip":
        result = await _maybe_run(
            store,
            task,
            "enhance_lip_sync",
            expected,
            lambda: yywav2lip.sync_lip(
                avatar_video,
                voice_audio,
                task_dir,
                role_model_path=role_model.pkl_model_path if role_model else None,
            ),
            log_lines,
        )
    elif chosen == LipSyncEngine.wav2lip or chosen == "wav2lip":
        result = await _maybe_run(
            store,
            task,
            "enhance_lip_sync",
            expected,
            lambda: wav2lip.sync_lip(avatar_video, voice_audio, task_dir),
            log_lines,
        )
    elif chosen in {"syncso", "pixverse", "pixverse_lipsync", "cloud_lipsync", "cloud-sync"}:
        if chosen in {"pixverse", "pixverse_lipsync"} or getattr(syncso, "name", "") == "pixverse":
            video_url, audio_url = _fal_public_urls(task, profile, voice, avatar_video, voice_audio)
            result = await _maybe_run(
                store,
                task,
                "enhance_lip_sync",
                expected,
                lambda: syncso.sync_lip(avatar_video, voice_audio, task_dir, video_url=video_url, audio_url=audio_url),
                log_lines,
            )
        else:
            result = await _maybe_run(
                store,
                task,
                "enhance_lip_sync",
                expected,
                lambda: syncso.sync_lip(avatar_video, voice_audio, task_dir),
                log_lines,
            )
    elif chosen in {"fal_latentsync", "fal_musetalk"}:
        video_url, audio_url = _fal_public_urls(task, profile, voice, avatar_video, voice_audio)
        fal_video.provider_id = str(chosen)
        result = await _maybe_run(
            store,
            task,
            "enhance_lip_sync",
            expected,
            lambda: fal_video.render_lipsync(video_url=video_url, audio_url=audio_url, out_dir=task_dir),
            log_lines,
        )
    elif chosen == "baidu_xiling":
        task_meta = task.request.metadata if isinstance(task.request.metadata, dict) else {}
        audio_url = str(task_meta.get("baidu_xiling_audio_url") or task_meta.get("cloud_audio_url") or "")
        script_text = _script_text(script_json, fallback=task.request.fixed_script or task.request.topic)
        result = await _maybe_run(
            store,
            task,
            "enhance_lip_sync",
            expected,
            lambda: baidu_xiling.generate_video(
                text=script_text,
                audio_url=audio_url,
                out_dir=task_dir,
                metadata=task_meta,
            ),
            log_lines,
        )
    elif chosen in {"omnihuman", "volcengine_omnihuman", "volc_omnihuman"}:
        image_url, audio_url = _omnihuman_public_urls(task, profile, voice)
        omnihuman_output = await _maybe_run(
            store,
            task,
            "enhance_lip_sync",
            task_dir / "omnihuman_video.mp4",
            lambda: omnihuman.generate_video(
                image_url=image_url,
                audio_url=audio_url,
                prompt=str(task.request.metadata.get("omnihuman_prompt") or settings_prompt(omnihuman)),
                out_dir=task_dir,
            ),
            log_lines,
        )
        shutil.copyfile(omnihuman_output, expected)
        result = expected
    else:
        shutil.copyfile(avatar_video, expected)
        result = await _step(store, task, "enhance_lip_sync", expected, log_lines)

    write_json(
        task_dir / "lip_sync_report.json",
        {
            "status": "completed",
            "engine_used": str(chosen),
            "fallback_used": [],
            "source_video": str(avatar_video),
            "voice_audio": str(voice_audio),
            "output": str(result),
            "role_model_id": role_model.role_model_id if role_model else None,
            "pkl_model_path": role_model.pkl_model_path if role_model else None,
        },
    )
    task.artifacts.lip_sync_report = str(task_dir / "lip_sync_report.json")
    return result


def _choose_lip_sync_engine(
    engines: tuple[str, ...],
    role_model: DigitalHumanRoleModel | None,
    syncso: SyncSoLipSyncAdapter | None = None,
    omnihuman: OmniHumanVideoAdapter | None = None,
    fal_video: FalVideoRenderAdapter | None = None,
    baidu_xiling: BaiduXilingVideoAdapter | None = None,
    *,
    render_profile: str = "preview",
    has_public_urls: bool = False,
) -> str:
    if omnihuman and omnihuman.enabled:
        return "omnihuman"
    if baidu_xiling and baidu_xiling.enabled and (baidu_xiling.dry_run or baidu_xiling.available()):
        return "baidu_xiling"
    if fal_video and fal_video.enabled and (fal_video.dry_run or fal_video.available()):
        if render_profile == "preview" and fal_video.provider_id in {"fal_musetalk", "fal_latentsync"}:
            return "fal_musetalk" if fal_video.provider_id == "fal_musetalk" else fal_video.provider_id
        if render_profile == "final" and fal_video.provider_id in {"fal_latentsync", "fal_musetalk"}:
            return "fal_latentsync" if fal_video.provider_id == "fal_latentsync" else fal_video.provider_id
        if fal_video.provider_id in {"fal_latentsync", "fal_musetalk"}:
            return fal_video.provider_id
    if syncso and syncso.enabled:
        return "pixverse_lipsync" if getattr(syncso, "name", "") == "pixverse" else "syncso"
    if role_model and role_model.engine_type.value in {"yywav2lip", "wav2lip"} and role_model.engine_type.value in engines:
        return role_model.engine_type.value
    return next((engine for engine in engines if engine != "none"), "none")


def _select_tts_adapter(settings: Settings, voice_profile=None) -> BaseTTSAdapter:
    engine = (settings.tts_engine or "").lower().strip()
    voice_source = str(getattr(voice_profile, "voice_source_type", "") or "").lower()
    voice_engine = str(getattr(voice_profile, "engine", "") or "").lower().strip()
    metadata = getattr(voice_profile, "metadata", {}) if voice_profile is not None else {}
    if not isinstance(metadata, dict):
        metadata = {}
    voice_provider = str(metadata.get("provider") or "").lower().strip()
    cloud_voice_id = metadata.get("cloud_voice_id") or metadata.get("provider_voice_id") or metadata.get("voice_id")
    if voice_engine.startswith("aliyun_bailian") or voice_provider.startswith("aliyun_bailian"):
        return _select_cloud_voice_adapter(settings, provider_id=voice_engine or voice_provider)
    if voice_source.endswith("source_video_audio") and cloud_voice_id and (settings.cloud_voice_provider or "").lower().startswith("aliyun_bailian"):
        return _select_cloud_voice_adapter(settings)
    if voice_source.endswith("cloud_clone") or engine in {"cloud_clone", "aliyun_tts", "aliyun_bailian_cosyvoice", "aliyun_bailian_qwen_tts", "aliyun_bailian_minimax"}:
        return _select_cloud_voice_adapter(settings)
    if settings.dry_run or engine in {"", "dryrun", "dry-run"}:
        return DryRunTTSAdapter()
    if engine in {"edge", "edge_tts", "edge-tts"}:
        return EdgeTTSAdapter(default_voice=settings.tts_default_voice)
    if engine in {"http", "generic_http"} and settings.tts_base_url:
        return HTTPTTSAdapter(settings.tts_base_url)
    if engine in {"cosyvoice", "cosyvoice_http"} and (settings.cosyvoice_url or settings.tts_base_url):
        return HTTPTTSAdapter(settings.cosyvoice_url or settings.tts_base_url or "")
    if engine in {"gpt-sovits", "gpt_sovits", "gpt_sovits_http", "gpt-sovits-http"} and (settings.gpt_sovits_url or settings.tts_base_url):
        return HTTPTTSAdapter(settings.gpt_sovits_url or settings.tts_base_url or "")
    raise ValueError(f"真实模式需要可用 TTS，当前 TTS_ENGINE={settings.tts_engine!r} 未配置。")


def _select_cloud_voice_adapter(settings: Settings, provider_id: str | None = None) -> BaseTTSAdapter:
    provider = (provider_id or settings.cloud_voice_provider or "").lower().strip()
    if provider.startswith("aliyun_bailian"):
        return AliyunBailianVoiceAdapter(
            provider_id=provider,
            dry_run=settings.dry_run,
            api_key=settings.dashscope_api_key,
            region=settings.aliyun_bailian_region,
            model=settings.aliyun_voice_model,
        )
    if settings.dry_run:
        return DryRunTTSAdapter()
    if provider == "edge_tts_no_clone":
        return EdgeTTSAdapter(default_voice=settings.tts_default_voice)
    if provider == "custom_http_tts" and settings.custom_http_tts_base_url:
        return HTTPTTSAdapter(settings.custom_http_tts_base_url)
    raise ValueError(f"当前云端声音服务 {settings.cloud_voice_provider!r} 还没有真实适配器，请选择阿里云百炼或自定义 HTTP TTS。")


def settings_prompt(omnihuman: OmniHumanVideoAdapter) -> str:
    return omnihuman.prompt


def _render_profile_value(task: VideoTask) -> str:
    value = task.request.render_profile
    return value.value if hasattr(value, "value") else str(value)


def _has_public_lipsync_urls(task: VideoTask, profile, voice) -> bool:
    video_url, audio_url = _cloud_lipsync_urls(task, profile, voice)
    return _is_public_url(video_url) and _is_public_url(audio_url)


def _fal_public_urls(task: VideoTask, profile, voice, avatar_video: Path, voice_audio: Path) -> tuple[str, str]:
    video_url, audio_url = _cloud_lipsync_urls(task, profile, voice)
    if not video_url:
        video_url = str(avatar_video)
    if not audio_url:
        audio_url = str(voice_audio)
    return str(video_url), str(audio_url)


def _cloud_lipsync_urls(task: VideoTask, profile, voice) -> tuple[str, str]:
    task_meta = task.request.metadata if isinstance(task.request.metadata, dict) else {}
    profile_meta = profile.metadata if isinstance(profile.metadata, dict) else {}
    voice_meta = voice.metadata if isinstance(voice.metadata, dict) else {}
    video_url = (
        task_meta.get("fal_video_url")
        or task_meta.get("cloud_video_url")
        or task_meta.get("video_url")
        or profile_meta.get("fal_video_url")
        or profile_meta.get("cloud_video_url")
        or profile_meta.get("video_url")
    )
    audio_url = (
        task_meta.get("fal_audio_url")
        or task_meta.get("cloud_audio_url")
        or task_meta.get("audio_url")
        or voice_meta.get("fal_audio_url")
        or voice_meta.get("cloud_audio_url")
        or voice_meta.get("audio_url")
    )
    return str(video_url or ""), str(audio_url or "")


def _script_text(script_json: Path, *, fallback: str = "") -> str:
    try:
        payload = read_json(script_json)
    except Exception:
        return fallback
    if isinstance(payload, dict):
        for key in ("body", "text", "script", "content"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        segments = payload.get("segments")
        if isinstance(segments, list):
            parts = [str(item.get("text") or "").strip() for item in segments if isinstance(item, dict)]
            text = " ".join(part for part in parts if part)
            if text:
                return text
    return fallback


def _is_public_url(value: str) -> bool:
    lowered = str(value or "").strip().lower()
    return lowered.startswith("https://") or lowered.startswith("http://")


def _omnihuman_public_urls(task: VideoTask, profile, voice) -> tuple[str, str]:
    task_meta = task.request.metadata if isinstance(task.request.metadata, dict) else {}
    profile_meta = profile.metadata if isinstance(profile.metadata, dict) else {}
    voice_meta = voice.metadata if isinstance(voice.metadata, dict) else {}
    image_url = (
        task_meta.get("omnihuman_image_url")
        or task_meta.get("avatar_image_url")
        or profile_meta.get("omnihuman_image_url")
        or profile_meta.get("avatar_image_url")
    )
    audio_url = (
        task_meta.get("omnihuman_audio_url")
        or task_meta.get("voice_audio_url")
        or voice_meta.get("omnihuman_audio_url")
        or voice_meta.get("voice_audio_url")
    )
    if not image_url:
        raise ValueError("OmniHuman 需要公网头像 URL：请在数字人或任务 metadata 中填写 omnihuman_image_url。")
    if not audio_url:
        raise ValueError("OmniHuman 需要公网音频 URL：请在声音档案或任务 metadata 中填写 omnihuman_audio_url。")
    return str(image_url), str(audio_url)


def _role_model_video(role_model: DigitalHumanRoleModel) -> Path | None:
    for value in (role_model.action_video_asset_id, role_model.idle_video_asset_id, role_model.source_video_asset_id):
        if value:
            return Path(value)
    return None


def _valid(path: Path, *, directory: bool = False) -> bool:
    if directory:
        return path.exists() and path.is_dir() and any(path.iterdir())
    return path.exists() and path.is_file() and path.stat().st_size > 0


def _write_project_context(task_dir: Path, project_id: str, task: VideoTask) -> Path:
    return write_json(
        task_dir / "project_context.json",
        {
            "project_id": project_id,
            "topic": task.request.topic,
            "use_project_context": task.request.use_project_context,
            "metadata": task.request.metadata.get("project_context", {}),
            "source_policy": "safe structured context only",
        },
    )


def _write_profile(task_dir: Path, profile) -> Path:
    return write_json(task_dir / "digital_human_profile.json", profile.model_dump(mode="json"))


def _avatar_image(task_dir: Path, profile) -> Path:
    path = task_dir / "avatar_image.png"
    if profile.selected_avatar_asset:
        selected = Path(profile.selected_avatar_asset)
        if selected.exists() and not _is_video_file(selected):
            shutil.copyfile(selected, path)
            return path
    return write_placeholder_binary(path, f"avatar={profile.digital_human_id};source={profile.avatar_source_type}")


def _selected_avatar_video(profile) -> Path | None:
    selected_asset = getattr(profile, "selected_avatar_asset", None)
    if not selected_asset:
        return None
    selected = Path(selected_asset)
    if selected.exists() and _is_video_file(selected):
        return selected
    return None


def _is_video_file(path: Path) -> bool:
    return path.suffix.lower() in {".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv"}


def _write_subtitles(task_dir: Path, script_json: Path) -> Path:
    data = read_json(script_json)
    segments = data.get("segments") or [{"start": 0, "end": 3, "text": data.get("body", "")}]
    lines: list[str] = []
    for index, segment in enumerate(segments, start=1):
        lines.append(str(index))
        lines.append(f"{_srt_time(float(segment.get('start', 0)))} --> {_srt_time(float(segment.get('end', 3)))}")
        lines.append(str(segment.get("text", "")).strip() or "Synthetic IP talking point")
        lines.append("")
    return write_text(task_dir / "subtitles.srt", "\n".join(lines))


def _srt_time(seconds: float) -> str:
    millis = int(max(0.0, seconds) * 1000)
    hours, remainder = divmod(millis, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, ms = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{ms:03}"


def _write_script_quality_report(task_dir: Path, script_json: Path) -> Path:
    data = read_json(script_json)
    text = json.dumps(data, ensure_ascii=False)
    return write_json(
        task_dir / "script_quality_report.json",
        {
            "status": "completed",
            "readable": True,
            "character_count": len(text),
            "warnings": [],
            "suggestions": [],
        },
    )


def _write_audio_quality_report(task_dir: Path, audio: Path) -> Path:
    return write_json(
        task_dir / "audio_quality_report.json",
        {
            "status": "completed" if _valid(audio) else "warning",
            "file_exists": audio.exists(),
            "size_bytes": audio.stat().st_size if audio.exists() else 0,
            "readable_by_ffprobe": False,
            "duration_seconds": None,
            "warnings": ["ffprobe not required for dry-run placeholder audio"],
        },
    )


def _avatar_fallback_used(engines: tuple[str, ...]) -> list[str]:
    if "static" not in engines:
        return list(engines)
    return list(engines[: engines.index("static")])


def _write_render_job(task_dir: Path, task: VideoTask, render_profile: str, video_template_id: str) -> Path:
    return write_json(
        task_dir / "render_job.json",
        {
            "render_job_id": "render_" + task.task_id,
            "task_id": task.task_id,
            "render_profile": render_profile,
            "video_template_id": video_template_id,
            "status": "succeeded",
            "attempt": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )


def _write_render_stability_report(task_dir: Path, render_profile: str, video_template_id: str) -> Path:
    final_video = task_dir / "final.mp4"
    avatar_report = read_json(task_dir / "avatar_render_report.json") if (task_dir / "avatar_render_report.json").exists() else {}
    lip_report = read_json(task_dir / "lip_sync_report.json") if (task_dir / "lip_sync_report.json").exists() else {}
    template_report = read_json(task_dir / "template_report.json") if (task_dir / "template_report.json").exists() else {}
    return write_json(
        task_dir / "render_stability_report.json",
        {
            "overall_status": "completed",
            "render_profile": render_profile,
            "video_template_id": video_template_id,
            "avatar_engine_used": avatar_report.get("engine_used"),
            "lip_sync_engine_used": lip_report.get("engine_used"),
            "template_resolution": template_report.get("resolution"),
            "final_video_readable": bool(template_report.get("readable")) or (final_video.exists() and final_video.stat().st_size > 0),
            "final_video_size_bytes": final_video.stat().st_size if final_video.exists() else 0,
            "risk_flags": [],
            "warnings": template_report.get("warnings") or [],
            "suggestions": [],
        },
    )


def _write_digital_human_quality_report(task_dir: Path, profile, voice, render_profile: str, video_template_id: str) -> Path:
    return write_json(
        task_dir / "digital_human_quality_report.json",
        {
            "digital_human_id": profile.digital_human_id,
            "avatar_source_type": profile.avatar_source_type,
            "voice_source_type": voice.voice_source_type,
            "voice_profile_id": voice.voice_profile_id,
            "render_profile": render_profile,
            "video_template_id": video_template_id,
            "overall_grade": "dry-run",
            "face_stability_check": "skipped",
            "mouth_quality_check": "skipped",
            "subtitle_alignment_check": "generated",
            "suggestions": [],
        },
    )


def _write_publish_package(task_dir: Path, task: VideoTask, profile, voice, render_profile: str, video_template_id: str) -> Path:
    return write_json(
        task_dir / "publish_package.json",
        {
            "task_id": task.task_id,
            "project_id": profile.project_id,
            "digital_human_id": profile.digital_human_id,
            "voice_profile_id": voice.voice_profile_id,
            "render_profile": render_profile,
            "video_template_id": video_template_id,
            "platform": task.request.platform,
            "final_video": str(task_dir / "final.mp4"),
            "cover_image": str(task_dir / "cover.png"),
            "template_report": str(task_dir / "template_report.json"),
            "quality_reports": {
                "render_stability_report": str(task_dir / "render_stability_report.json"),
                "digital_human_quality_report": str(task_dir / "digital_human_quality_report.json"),
            },
            "handoff_policy": "manual publish handoff; no automatic platform login",
        },
    )
