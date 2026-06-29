#!/usr/bin/env python3
from pathlib import Path

from _smoke import _raise_for_status, client, create_digital_human_task, run_task


def main() -> int:
    project_id = "project_export_demo"
    imported_project_id = "project_export_demo_imported"
    with client() as api:
        created_project = api.post(
            "/projects",
            json={"project_id": project_id, "name": "Project Export Demo"},
        )
        _raise_for_status(created_project)
        task_id = create_digital_human_task(api, project_id=project_id, render_profile="preview")
        result = run_task(api, task_id)
        if result["status"] != "completed":
            raise SystemExit(result)

        queued = api.post(f"/tasks/{task_id}/publish/queue", json={"platform": "douyin"})
        _raise_for_status(queued)

        exported = api.post(f"/projects/{project_id}/export")
        _raise_for_status(exported)
        package_path = Path(exported.json()["package_path"])
        if not package_path.exists():
            raise SystemExit(f"missing export package: {package_path}")

        imported = api.post(
            "/projects/import",
            json={"package_path": str(package_path), "project_id": imported_project_id},
        )
        _raise_for_status(imported)

        projects = api.get("/projects")
        _raise_for_status(projects)
        project_ids = {project["project_id"] for project in projects.json()["projects"]}
        if imported_project_id not in project_ids:
            raise SystemExit(f"imported project not listed: {imported_project_id}")

        readiness = api.get("/storage/readiness")
        _raise_for_status(readiness)
        if readiness.json()["repositories"]["backend"] != "file":
            raise SystemExit(readiness.json())

        print(f"task_id={task_id}")
        print(f"export_package={package_path}")
        print(f"imported_project_id={imported_project_id}")
        print(f"imported_files={imported.json()['imported_files']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
