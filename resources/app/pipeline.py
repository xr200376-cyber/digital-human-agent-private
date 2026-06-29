from datetime import datetime, timezone
from pathlib import Path

from app.adapters.duix import DuixAdapter
from app.adapters.jianying import JianyingDraftAdapter
from app.adapters.lipsync import LatentSyncAdapter, MuseTalkAdapter
from app.adapters.pixelle import PixelleAdapter
from app.schemas import LipSyncEngine, StepResult, TaskStatus, VideoTask
from app.script_generation import select_script_generator_adapter
from app.settings import Settings
from app.store import TaskStore
from app.utils.files import ensure_dir, write_text


class VideoPipeline:
    def __init__(self, settings: Settings, store: TaskStore):
        self.settings = settings
        self.store = store
        self.script_generator = select_script_generator_adapter(settings)
        self.pixelle = PixelleAdapter(settings.pixelle_base_url, dry_run=settings.dry_run)
        self.duix = DuixAdapter(settings.duix_base_url, dry_run=settings.dry_run)
        self.latentsync = LatentSyncAdapter(
            settings.latentsync_cli_path,
            dry_run=settings.dry_run,
            ckpt_path=settings.latentsync_ckpt_path,
            config_path=settings.latentsync_config_path,
        )
        self.musetalk = MuseTalkAdapter(
            settings.musetalk_cli_path,
            dry_run=settings.dry_run,
            model_dir=settings.musetalk_model_dir,
            version=settings.musetalk_version,
            ffmpeg_path=settings.musetalk_ffmpeg_path,
        )
        self.jianying = JianyingDraftAdapter(settings.jianying_draft_root, dry_run=settings.dry_run)

    async def run(self, task: VideoTask) -> VideoTask:
        if task.request.use_digital_human_pipeline or task.request.digital_human_id:
            from app.digital_human_pipeline import run_digital_human_pipeline

            return await run_digital_human_pipeline(self.settings, self.store, task)

        self.store.update_status(task, TaskStatus.running)
        task_dir = ensure_dir(self.store.task_dir(task.task_id))
        logs_path = task_dir / "pipeline.log"
        task.artifacts.logs = str(logs_path)
        try:
            script_json = await self._run_step(task, "generate_script", self.script_generator.generate_script(task.request, task_dir))
            task.artifacts.script_json = str(script_json)

            voice_audio = await self._run_step(task, "synthesize_voice", self.duix.synthesize_voice(script_json, task_dir))
            task.artifacts.voice_audio = str(voice_audio)

            avatar_video = await self._run_step(task, "render_avatar", self.duix.render_avatar(voice_audio, task.request, task_dir))
            task.artifacts.avatar_video = str(avatar_video)

            if task.request.lip_sync_engine == LipSyncEngine.musetalk:
                lip_adapter = self.musetalk
            elif task.request.lip_sync_engine == LipSyncEngine.latentsync:
                lip_adapter = self.latentsync
            else:
                lip_adapter = None

            if lip_adapter:
                lip_synced_video = await self._run_step(task, "sync_lip", lip_adapter.sync_lip(avatar_video, voice_audio, task_dir))
            else:
                lip_synced_video = avatar_video
            task.artifacts.lip_synced_video = str(lip_synced_video)

            final_video = await self._run_step(task, "assemble_video", self.pixelle.assemble_video(lip_synced_video, script_json, task_dir))
            task.artifacts.final_video = str(final_video)

            if task.request.export_jianying_draft:
                draft_dir = await self._run_step(task, "export_draft", self.jianying.export_draft(final_video, script_json, task_dir))
                task.artifacts.jianying_draft = str(draft_dir)

            write_text(logs_path, self._render_log(task))
            self.store.update_status(task, TaskStatus.completed)
            return self.store.save(task)
        except Exception as exc:
            task.error = str(exc)
            write_text(logs_path, self._render_log(task) + f"\nERROR: {exc}\n")
            self.store.update_status(task, TaskStatus.failed, error=str(exc))
            return self.store.save(task)

    async def _run_step(self, task: VideoTask, name: str, awaitable):
        step = StepResult(name=name, status="running", started_at=datetime.now(timezone.utc))
        task.steps.append(step)
        self.store.save(task)
        try:
            result = await awaitable
            step.status = "completed"
            step.finished_at = datetime.now(timezone.utc)
            if isinstance(result, Path):
                step.artifacts["path"] = str(result)
            step.message = "ok"
            self.store.save(task)
            return result
        except Exception as exc:
            step.status = "failed"
            step.finished_at = datetime.now(timezone.utc)
            step.message = str(exc)
            self.store.save(task)
            raise

    def _render_log(self, task: VideoTask) -> str:
        lines = [f"task_id={task.task_id}", f"status={task.status}"]
        for step in task.steps:
            lines.append(f"{step.name} {step.status} {step.started_at.isoformat()} -> {step.finished_at}")
            if step.message:
                lines.append(f"  message={step.message}")
            if step.artifacts:
                lines.append(f"  artifacts={step.artifacts}")
        return "\n".join(lines) + "\n"
