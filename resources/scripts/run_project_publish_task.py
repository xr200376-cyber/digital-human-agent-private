#!/usr/bin/env python3
from _smoke import client, create_digital_human_task, require_artifact, run_task


def main() -> int:
    with client() as api:
        task_id = create_digital_human_task(api, render_profile="preview")
        run_task(api, task_id)
        print(f"publish_package={require_artifact(api, task_id, 'publish_package.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
