import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.utils.files import ensure_dir


def append_audit_event(
    storage_dir: Path,
    *,
    action: str,
    task_id: str | None = None,
    project_id: str | None = None,
    digital_human_id: str | None = None,
    actor: str = "system",
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "actor": actor,
        "task_id": task_id,
        "project_id": project_id,
        "digital_human_id": digital_human_id,
        "details": details or {},
    }
    global_path = ensure_dir(storage_dir / "audit") / "events.jsonl"
    _append_jsonl(global_path, event)
    if task_id:
        task_path = ensure_dir(storage_dir / "tasks" / task_id) / "audit_events.jsonl"
        _append_jsonl(task_path, event)
    return event


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
