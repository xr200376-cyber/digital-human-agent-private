from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.schemas import CreateProjectRequest
from app.settings import Settings
from app.utils.files import ensure_dir, read_json, write_json


class ProjectStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.root = ensure_dir(settings.storage_dir / "projects")

    def project_dir(self, project_id: str) -> Path:
        return ensure_dir(self.root / project_id)

    def project_file(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "project.json"

    def create(self, request: CreateProjectRequest) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        path = self.project_file(request.project_id)
        if path.exists():
            data = read_json(path)
            data["name"] = request.name
            data["metadata"] = request.metadata
            data["updated_at"] = now
        else:
            data = {
                "project_id": request.project_id,
                "name": request.name,
                "metadata": request.metadata,
                "created_at": now,
                "updated_at": now,
            }
        write_json(path, data)
        return data

    def list(self) -> list[dict[str, Any]]:
        projects: list[dict[str, Any]] = []
        for path in sorted(self.root.glob("*/project.json")):
            projects.append(read_json(path))
        for directory in sorted(self.root.iterdir()) if self.root.exists() else []:
            if directory.is_dir() and not (directory / "project.json").exists():
                projects.append(
                    {
                        "project_id": directory.name,
                        "name": directory.name,
                        "metadata": {},
                        "created_at": None,
                        "updated_at": None,
                    }
                )
        return projects
