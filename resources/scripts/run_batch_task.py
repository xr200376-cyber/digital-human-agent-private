#!/usr/bin/env python3
from _smoke import client, create_digital_human_task, run_task


def main() -> int:
    with client() as api:
        task_ids = [create_digital_human_task(api, render_profile="batch") for _ in range(2)]
        for task_id in task_ids:
            result = run_task(api, task_id)
            if result["status"] != "completed":
                raise SystemExit(result)
        print("batch_task_ids=" + ",".join(task_ids))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
