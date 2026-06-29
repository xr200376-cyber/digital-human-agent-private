#!/usr/bin/env python3
from _smoke import client


def main() -> int:
    with client() as api:
        created = api.post(
            "/tasks",
            json={"brand_name": "Dry Brand", "persona": "Host", "topic": "Dry run topic"},
        )
        if created.status_code >= 400:
            raise SystemExit(created.text)
        task_id = created.json()["task_id"]
        result = api.post(f"/tasks/{task_id}/run")
        if result.status_code >= 400 or result.json()["status"] != "completed":
            raise SystemExit(result.text)
        print(f"task_id={task_id}")
        print(f"final_video={result.json()['artifacts']['final_video']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
