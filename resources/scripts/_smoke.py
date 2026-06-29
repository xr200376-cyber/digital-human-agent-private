from __future__ import annotations

import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", message="Using `httpx` with `starlette.testclient` is deprecated.*")

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import app, get_settings  # noqa: E402
from app.settings import Settings, get_settings as cached_get_settings  # noqa: E402


def client(*, dry_run: bool = True) -> TestClient:
    app.dependency_overrides.clear()
    cached_get_settings.cache_clear()
    if dry_run:
        app.dependency_overrides[get_settings] = lambda: Settings(
            dry_run=True,
            runtime_mode="dry-run",
            storage_dir=Path("storage"),
        )
    return TestClient(app)


def create_digital_human_task(
    api: TestClient,
    *,
    project_id: str = "project_demo",
    render_profile: str = "preview",
    video_template_id: str = "clean_talking_head",
    review_required: bool = False,
) -> str:
    human = api.post(
        f"/projects/{project_id}/digital-humans",
        json={
            "name": "Sprint 13E Synthetic Host",
            "avatar_source_type": "generated",
            "avatar_style": {"style": "studio", "prompt": "synthetic host"},
        },
    )
    _raise_for_status(human)
    digital_human_id = human.json()["digital_human_id"]

    voice = api.post(
        f"/digital-humans/{digital_human_id}/voice-profiles",
        json={"name": "Dry Run Voice", "voice_source_type": "synthetic", "engine": "dryrun"},
    )
    _raise_for_status(voice)
    voice_profile_id = voice.json()["voice_profile_id"]

    task = api.post(
        f"/projects/{project_id}/digital-human-tasks",
        json={
            "digital_human_id": digital_human_id,
            "voice_profile_id": voice_profile_id,
            "topic": "Why customers care about risk before price",
            "platform": "douyin",
            "duration_seconds": 45,
            "render_profile": render_profile,
            "video_template_id": video_template_id,
            "script_review_required": review_required,
            "export_jianying_draft": True,
        },
    )
    _raise_for_status(task)
    return task.json()["task_id"]


def run_task(api: TestClient, task_id: str) -> dict:
    response = api.post(f"/tasks/{task_id}/run")
    _raise_for_status(response)
    return response.json()


def approve_task(api: TestClient, task_id: str) -> dict:
    response = api.post(f"/tasks/{task_id}/review/approve", json={"reviewer_id": "smoke"})
    _raise_for_status(response)
    return response.json()


def require_artifact(api: TestClient, task_id: str, filename: str) -> Path:
    artifacts = api.get(f"/tasks/{task_id}/artifacts")
    _raise_for_status(artifacts)
    for item in artifacts.json()["items"]:
        path = Path(item["path"])
        if path.name == filename and path.exists() and path.stat().st_size > 0:
            return path
    raise SystemExit(f"missing artifact {filename} for task {task_id}")


def _raise_for_status(response) -> None:
    if response.status_code >= 400:
        raise SystemExit(f"HTTP {response.status_code}: {response.text}")
