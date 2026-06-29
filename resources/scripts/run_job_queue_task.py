#!/usr/bin/env python3
from _smoke import _raise_for_status, client, create_digital_human_task


def main() -> int:
    with client() as api:
        task_id = create_digital_human_task(api, render_profile="preview")
        queued = api.post(f"/tasks/{task_id}/run-async", json={"max_retries": 1})
        _raise_for_status(queued)
        job_id = queued.json()["job_id"]

        run = api.post("/jobs/worker/run-next")
        _raise_for_status(run)
        job = run.json()
        if job["status"] != "succeeded":
            raise SystemExit(job)

        logs = api.get(f"/jobs/{job_id}/logs")
        _raise_for_status(logs)
        if "job succeeded" not in logs.text:
            raise SystemExit(logs.text)

        print(f"task_id={task_id}")
        print(f"job_id={job_id}")
        print(f"job_status={job['status']}")
        print(f"task_status={job['result']['task_status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
