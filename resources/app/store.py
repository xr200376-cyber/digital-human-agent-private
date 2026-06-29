from datetime import datetime, timezone
from pathlib import Path

from app.schemas import CreateVideoTaskRequest, TaskStatus, VideoTask
from app.settings import Settings
from app.utils.files import ensure_dir, read_json, write_json, write_text


PROCESS_STARTED_AT = datetime.now(timezone.utc)
ORPHANED_RUNNING_TASK_ERROR = "本地后端重启中断了数字人生成任务。请重新点击生成数字人视频。"


class TaskStore:
    """File-backed task store for MVP.

    Replace with PostgreSQL when the product moves beyond local MVP.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.root = ensure_dir(settings.storage_dir / "tasks")

    def task_dir(self, task_id: str) -> Path:
        return ensure_dir(self.root / task_id)

    def task_file(self, task_id: str) -> Path:
        return self.task_dir(task_id) / "task.json"

    def create(self, request: CreateVideoTaskRequest) -> VideoTask:
        task = VideoTask(request=request)
        ensure_dir(self.task_dir(task.task_id))
        self.save(task)
        return task

    def get(self, task_id: str) -> VideoTask:
        path = self.task_file(task_id)
        if not path.exists():
            raise KeyError(f"task not found: {task_id}")
        return self.reconcile_running_task(VideoTask.model_validate(read_json(path)))

    def list_tasks(self) -> list[VideoTask]:
        tasks: list[VideoTask] = []
        for path in sorted(self.root.glob("*/task.json")):
            try:
                tasks.append(VideoTask.model_validate(read_json(path)))
            except Exception:
                continue
        return tasks

    def running_tasks(self, *, exclude_task_id: str | None = None) -> list[VideoTask]:
        return [
            checked
            for task in self.list_tasks()
            if (checked := self.reconcile_running_task(task)).status == TaskStatus.running
            and checked.task_id != exclude_task_id
        ]

    def save(self, task: VideoTask) -> VideoTask:
        task.updated_at = datetime.now(timezone.utc)
        write_json(self.task_file(task.task_id), task.model_dump(mode="json"))
        return task

    def update_status(self, task: VideoTask, status: TaskStatus, error: str | None = None) -> VideoTask:
        task.status = status
        task.error = error
        return self.save(task)

    def reconcile_running_task(self, task: VideoTask) -> VideoTask:
        if task.status != TaskStatus.running:
            return task
        error = self._pipeline_error(task)
        if error:
            return self.update_status(task, TaskStatus.failed, error=error)
        orphaned_error = self._orphaned_running_task_error(task)
        if orphaned_error:
            self._write_reconciliation_error_log(task, orphaned_error)
            return self.update_status(task, TaskStatus.failed, error=orphaned_error)
        return task

    def _orphaned_running_task_error(self, task: VideoTask) -> str | None:
        if self._final_artifact_exists(task):
            return None
        updated_at = task.updated_at
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        if updated_at >= PROCESS_STARTED_AT:
            return None
        return ORPHANED_RUNNING_TASK_ERROR

    def _final_artifact_exists(self, task: VideoTask) -> bool:
        final_video = task.artifacts.final_video
        if not final_video:
            return False
        candidates = [Path(final_video)]
        if not candidates[0].is_absolute():
            candidates.append(self.settings.storage_dir.parent / candidates[0])
        return any(path.exists() and path.stat().st_size > 0 for path in candidates)

    def _write_reconciliation_error_log(self, task: VideoTask, error: str) -> None:
        log_path = Path(task.artifacts.logs) if task.artifacts.logs else self.task_dir(task.task_id) / "pipeline.log"
        if not log_path.is_absolute():
            log_path = self.settings.storage_dir.parent / log_path
        content = ""
        if log_path.exists():
            try:
                content = log_path.read_text(encoding="utf-8", errors="ignore").rstrip()
            except OSError:
                content = ""
        suffix = f"ERROR: {error}"
        write_text(log_path, f"{content}\n{suffix}\n" if content else f"{suffix}\n")

    def _pipeline_error(self, task: VideoTask) -> str | None:
        for path in self._pipeline_log_candidates(task):
            if not path.exists():
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            marker = "ERROR:"
            if marker not in content:
                continue
            error = content.rsplit(marker, 1)[-1].strip()
            return error[-1200:] if error else "任务日志已记录失败，但未写入任务状态。"
        return None

    def _pipeline_log_candidates(self, task: VideoTask) -> list[Path]:
        candidates: list[Path] = []
        if task.artifacts.logs:
            log_path = Path(task.artifacts.logs)
            candidates.append(log_path)
            if not log_path.is_absolute():
                candidates.append(self.settings.storage_dir.parent / log_path)
        candidates.append(self.task_dir(task.task_id) / "pipeline.log")
        unique: list[Path] = []
        for candidate in candidates:
            if candidate not in unique:
                unique.append(candidate)
        return unique
