#!/usr/bin/env python3
from _smoke import _raise_for_status, client, create_digital_human_task


def main() -> int:
    with client() as api:
        task_id = create_digital_human_task(api, render_profile="preview")
        queued = api.post(f"/tasks/{task_id}/run-async", json={"max_retries": 1})
        _raise_for_status(queued)
        job_id = queued.json()["job_id"]

        result = api.post("/jobs/worker/run-next")
        _raise_for_status(result)
        if result.json()["status"] != "succeeded":
            raise SystemExit(result.json())
        print(f"async_smoke_task_id={task_id}")
        print(f"async_smoke_job_id={job_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
