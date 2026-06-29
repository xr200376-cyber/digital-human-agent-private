#!/usr/bin/env python3
from _smoke import client, create_digital_human_task, require_artifact, run_task


def main() -> int:
    with client() as api:
        task_id = create_digital_human_task(api, render_profile="final")
        run_task(api, task_id)
        retry = api.post(f"/tasks/{task_id}/render/retry", json={"retry_from": "lip_sync"})
        if retry.status_code >= 400 or retry.json()["status"] != "completed":
            raise SystemExit(retry.text)
        print(f"render_stability_report={require_artifact(api, task_id, 'render_stability_report.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
