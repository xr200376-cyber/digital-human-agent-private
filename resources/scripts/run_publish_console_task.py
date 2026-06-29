#!/usr/bin/env python3
from pathlib import Path

from _smoke import _raise_for_status, client, create_digital_human_task, run_task


def main() -> int:
    with client() as api:
        task_id = create_digital_human_task(api, render_profile="preview", video_template_id="douyin_sales")
        result = run_task(api, task_id)
        if result["status"] != "completed":
            raise SystemExit(result)

        queued = api.post(
            f"/tasks/{task_id}/publish/queue",
            json={"platform": "douyin", "scheduled_at": "2026-06-08T09:30:00+08:00"},
        )
        _raise_for_status(queued)
        queue_id = queued.json()["queue_id"]

        updated = api.patch(f"/publish/queue/{queue_id}", json={"status": "scheduled"})
        _raise_for_status(updated)

        board = api.get("/publish/board")
        _raise_for_status(board)
        calendar = api.get("/publish/calendar")
        _raise_for_status(calendar)

        handoff = api.get(f"/publish/queue/{queue_id}/handoff.zip")
        _raise_for_status(handoff)
        zip_path = Path("storage") / "publish_console_handoff.zip"
        zip_path.write_bytes(handoff.content)

        print(f"task_id={task_id}")
        print(f"queue_id={queue_id}")
        print(f"status={updated.json()['status']}")
        print(f"calendar_items={len(calendar.json()['items'])}")
        print(f"handoff_zip={zip_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
