from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.repositories import FileRepositoryBundle
from app.settings import Settings
from app.utils.files import ensure_dir, read_json, write_json

EXCLUDED_SUFFIXES = (".pth", ".pt", ".ckpt", ".safetensors", ".onnx", ".pkl")
EXCLUDED_ROOTS = ("third_party",)


class ProjectPackageService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.repositories = FileRepositoryBundle(settings)
        self.package_root = ensure_dir(settings.storage_dir / "project_packages")

    def export_project(self, project_id: str) -> dict[str, Any]:
        project = self.repositories.projects.get(project_id)
        tasks = self.repositories.tasks.list_by_project(project_id)
        publish_items = self.repositories.publish.list_by_project(project_id)
        events = self.repositories.audit.list_events(project_id=project_id)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        export_dir = ensure_dir(self.package_root / project_id / timestamp)
        package_path = export_dir / "project_export.zip"
        manifest = {
            "project_id": project_id,
            "project": project,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "repository_backend": "file",
            "object_storage_backend": self.settings.object_storage_backend,
            "task_ids": [task.task_id for task in tasks],
            "publish_queue_ids": [item.queue_id for item in publish_items],
            "counts": {
                "tasks": len(tasks),
                "publish_queue": len(publish_items),
                "audit_events": len(events),
            },
        }

        with zipfile.ZipFile(package_path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            self._add_tree(
                archive,
                self.settings.storage_dir / "projects" / project_id,
                Path("projects") / project_id,
            )
            for task in tasks:
                self._add_tree(
                    archive,
                    self.settings.storage_dir / "tasks" / task.task_id,
                    Path("tasks") / task.task_id,
                )
            for item in publish_items:
                self._add_tree(
                    archive,
                    self.settings.storage_dir / "publish_queue" / item.queue_id,
                    Path("publish_queue") / item.queue_id,
                )
            if events:
                archive.writestr(
                    "audit/events.jsonl",
                    "\n".join(json.dumps(event, ensure_ascii=False) for event in events) + "\n",
                )

        return {
            "project_id": project_id,
            "package_path": str(package_path),
            "manifest": manifest,
        }

    def import_project(self, package_path: Path, project_id: str | None = None) -> dict[str, Any]:
        package_path = Path(package_path)
        if not package_path.exists() or not package_path.is_file():
            raise FileNotFoundError(f"project package not found: {package_path}")
        imported_files = 0
        with zipfile.ZipFile(package_path) as archive:
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            source_project_id = str(manifest.get("project_id") or "")
            if not source_project_id:
                raise ValueError("package manifest missing project_id")
            target_project_id = project_id or source_project_id
            for member in archive.infolist():
                if member.is_dir() or member.filename == "manifest.json":
                    continue
                target = self._target_path_for_member(
                    member.filename,
                    source_project_id=source_project_id,
                    target_project_id=target_project_id,
                )
                if target is None:
                    continue
                ensure_dir(target.parent)
                payload = archive.read(member)
                if target.suffix.lower() == ".json":
                    payload = self._rewrite_project_json(payload, source_project_id, target_project_id)
                target.write_bytes(payload)
                imported_files += 1
        return {
            "project_id": target_project_id,
            "source_project_id": source_project_id,
            "package_path": str(package_path),
            "imported_files": imported_files,
        }

    def _add_tree(self, archive: zipfile.ZipFile, source_root: Path, archive_root: Path) -> None:
        if not source_root.exists():
            return
        for path in sorted(source_root.rglob("*")):
            if not path.is_file() or self._excluded(path):
                continue
            relative = path.relative_to(source_root)
            archive_name = (archive_root / relative).as_posix()
            if self._unsafe_archive_name(archive_name):
                continue
            archive.write(path, archive_name)

    @staticmethod
    def _excluded(path: Path) -> bool:
        suffix = path.suffix.lower()
        if suffix in EXCLUDED_SUFFIXES:
            return True
        parts = {part.lower() for part in path.parts}
        if any(root.lower() in parts for root in EXCLUDED_ROOTS):
            return True
        if path.name.lower().endswith(".zip"):
            return True
        return False

    def _target_path_for_member(
        self,
        name: str,
        *,
        source_project_id: str,
        target_project_id: str,
    ) -> Path | None:
        if self._unsafe_archive_name(name):
            return None
        parts = Path(name).parts
        if len(parts) >= 2 and parts[0] == "projects" and parts[1] == source_project_id:
            return self.settings.storage_dir / "projects" / target_project_id / Path(*parts[2:])
        if parts and parts[0] in {"tasks", "publish_queue"}:
            return self.settings.storage_dir / Path(*parts)
        if parts and parts[0] == "audit":
            return self.settings.storage_dir / "audit" / f"imported_{target_project_id}_{Path(name).name}"
        return None

    @staticmethod
    def _unsafe_archive_name(name: str) -> bool:
        path = Path(name)
        return path.is_absolute() or ".." in path.parts or any(part in EXCLUDED_ROOTS for part in path.parts)

    @staticmethod
    def _rewrite_project_json(payload: bytes, source_project_id: str, target_project_id: str) -> bytes:
        try:
            data = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return payload

        def rewrite(value: Any) -> Any:
            if isinstance(value, dict):
                return {key: rewrite(item) for key, item in value.items()}
            if isinstance(value, list):
                return [rewrite(item) for item in value]
            if value == source_project_id:
                return target_project_id
            return value

        return json.dumps(rewrite(data), ensure_ascii=False, indent=2).encode("utf-8")


def export_project_package(settings: Settings, project_id: str) -> dict[str, Any]:
    return ProjectPackageService(settings).export_project(project_id)


def import_project_package(settings: Settings, package_path: Path, project_id: str | None = None) -> dict[str, Any]:
    result = ProjectPackageService(settings).import_project(package_path, project_id=project_id)
    project_file = settings.storage_dir / "projects" / result["project_id"] / "project.json"
    if project_file.exists():
        project = read_json(project_file)
        project["project_id"] = result["project_id"]
        write_json(project_file, project)
    return result
