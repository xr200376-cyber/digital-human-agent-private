#!/usr/bin/env python3
from _smoke import client, create_digital_human_task, require_artifact, run_task


def main() -> int:
    with client() as api:
        task_id = create_digital_human_task(api, render_profile="preview")
        result = run_task(api, task_id)
        if result["status"] != "completed":
            raise SystemExit(result)
        final_video = require_artifact(api, task_id, "final.mp4")
        manifest = require_artifact(api, task_id, "artifact_manifest.json")
        print(f"task_id={task_id}")
        print(f"final_video={final_video}")
        print(f"artifact_manifest={manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
