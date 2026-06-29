from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from app.digital_humans import DigitalHumanStore
from app.projects import ProjectStore
from app.publish_console import PublishConsoleStore
from app.schemas import DigitalHumanProfile, PublishQueueItem, VideoTask, VoiceProfile
from app.settings import Settings
from app.store import TaskStore
from app.utils.files import ensure_dir, read_json, write_json


@runtime_checkable
class ProjectRepository(Protocol):
    def list(self) -> list[dict[str, Any]]:
        ...

    def get(self, project_id: str) -> dict[str, Any]:
        ...

    def save(self, project: dict[str, Any]) -> dict[str, Any]:
        ...


@runtime_checkable
class AssetRepository(Protocol):
    def list_assets(self, project_id: str) -> list[dict[str, Any]]:
        ...

    def asset_root(self, project_id: str) -> Path:
        ...


@runtime_checkable
class TaskRepository(Protocol):
    def get(self, task_id: str) -> VideoTask:
        ...

    def save(self, task: VideoTask) -> VideoTask:
        ...

    def list_by_project(self, project_id: str) -> list[VideoTask]:
        ...


@runtime_checkable
class DigitalHumanRepository(Protocol):
    def get(self, digital_human_id: str) -> DigitalHumanProfile:
        ...

    def list_by_project(self, project_id: str) -> list[DigitalHumanProfile]:
        ...


@runtime_checkable
class VoiceRepository(Protocol):
    def get(self, digital_human_id: str, voice_profile_id: str) -> VoiceProfile:
        ...

    def list_by_digital_human(self, digital_human_id: str) -> list[VoiceProfile]:
        ...


@runtime_checkable
class PublishRepository(Protocol):
    def get(self, queue_id: str) -> PublishQueueItem:
        ...

    def list_by_project(self, project_id: str) -> list[PublishQueueItem]:
        ...


@runtime_checkable
class AuditRepository(Protocol):
    def list_events(
        self,
        *,
        project_id: str | None = None,
        task_id: str | None = None,
    ) -> list[dict[str, Any]]:
        ...


class FileProjectRepository:
    def __init__(self, settings: Settings):
        self.store = ProjectStore(settings)

    def list(self) -> list[dict[str, Any]]:
        return self.store.list()

    def get(self, project_id: str) -> dict[str, Any]:
        path = self.store.project_file(project_id)
        if not path.exists():
            raise KeyError(f"project not found: {project_id}")
        return read_json(path)

    def save(self, project: dict[str, Any]) -> dict[str, Any]:
        project_id = str(project.get("project_id") or "")
        if not project_id:
            raise ValueError("project_id is required")
        write_json(self.store.project_file(project_id), project)
        return project


class FileAssetRepository:
    def __init__(self, settings: Settings):
        self.root = ensure_dir(settings.storage_dir / "projects")

    def asset_root(self, project_id: str) -> Path:
        return ensure_dir(self.root / project_id / "assets")

    def list_assets(self, project_id: str) -> list[dict[str, Any]]:
        root = self.asset_root(project_id)
        assets: list[dict[str, Any]] = []
        for path in sorted(root.rglob("*")) if root.exists() else []:
            if path.is_file():
                assets.append(
                    {
                        "project_id": project_id,
                        "path": str(path),
                        "relative_path": path.relative_to(root).as_posix(),
                        "size_bytes": path.stat().st_size,
                    }
                )
        return assets


class FileTaskRepository:
    def __init__(self, settings: Settings):
        self.store = TaskStore(settings)

    def get(self, task_id: str) -> VideoTask:
        return self.store.get(task_id)

    def save(self, task: VideoTask) -> VideoTask:
        return self.store.save(task)

    def list_by_project(self, project_id: str) -> list[VideoTask]:
        tasks: list[VideoTask] = []
        for path in sorted(self.store.root.glob("*/task.json")) if self.store.root.exists() else []:
            task = VideoTask.model_validate(read_json(path))
            if task.request.project_id == project_id:
                tasks.append(task)
        return tasks


class FileDigitalHumanRepository:
    def __init__(self, settings: Settings):
        self.store = DigitalHumanStore(settings)

    def get(self, digital_human_id: str) -> DigitalHumanProfile:
        return self.store.get(digital_human_id)

    def list_by_project(self, project_id: str) -> list[DigitalHumanProfile]:
        return self.store.list_for_project(project_id)


class FileVoiceRepository:
    def __init__(self, settings: Settings):
        self.store = DigitalHumanStore(settings)

    def get(self, digital_human_id: str, voice_profile_id: str) -> VoiceProfile:
        return self.store.get_voice_profile(digital_human_id, voice_profile_id)

    def list_by_digital_human(self, digital_human_id: str) -> list[VoiceProfile]:
        return self.store.list_voice_profiles(digital_human_id)


class FilePublishRepository:
    def __init__(self, settings: Settings):
        self.store = PublishConsoleStore(settings)

    def get(self, queue_id: str) -> PublishQueueItem:
        return self.store.get(queue_id)

    def list_by_project(self, project_id: str) -> list[PublishQueueItem]:
        return [item for item in self.store.list() if item.project_id == project_id]


class FileAuditRepository:
    def __init__(self, settings: Settings):
        self.storage_dir = settings.storage_dir
        self.path = self.storage_dir / "audit" / "events.jsonl"

    def list_events(
        self,
        *,
        project_id: str | None = None,
        task_id: str | None = None,
    ) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        if not self.path.exists():
            return events
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if project_id is not None and event.get("project_id") != project_id:
                continue
            if task_id is not None and event.get("task_id") != task_id:
                continue
            events.append(event)
        return events


class FileRepositoryBundle:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.projects: ProjectRepository = FileProjectRepository(settings)
        self.assets: AssetRepository = FileAssetRepository(settings)
        self.tasks: TaskRepository = FileTaskRepository(settings)
        self.digital_humans: DigitalHumanRepository = FileDigitalHumanRepository(settings)
        self.voices: VoiceRepository = FileVoiceRepository(settings)
        self.publish: PublishRepository = FilePublishRepository(settings)
        self.audit: AuditRepository = FileAuditRepository(settings)

    def readiness(self) -> dict[str, object]:
        return {
            "backend": "file",
            "ready": True,
            "storage_dir": str(self.settings.storage_dir),
            "paths": {
                "projects": str(self.settings.storage_dir / "projects"),
                "tasks": str(self.settings.storage_dir / "tasks"),
                "digital_humans": str(self.settings.storage_dir / "digital_humans"),
                "publish_queue": str(self.settings.storage_dir / "publish_queue"),
                "audit": str(self.settings.storage_dir / "audit" / "events.jsonl"),
            },
        }


class PostgresRepositoryBundle:
    """PostgreSQL repository scaffold for the production migration path."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.database_url = settings.database_url

    def readiness(self) -> dict[str, object]:
        return {
            "backend": "postgresql",
            "ready": False,
            "database_url_configured": bool(self.database_url),
            "message": "PostgreSQL repository scaffold only; file repositories remain the default.",
        }
