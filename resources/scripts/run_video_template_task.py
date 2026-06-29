#!/usr/bin/env python3
from _smoke import client, create_digital_human_task, require_artifact, run_task


def main() -> int:
    with client() as api:
        task_id = create_digital_human_task(
            api,
            render_profile="preview",
            video_template_id="douyin_sales",
        )
        result = run_task(api, task_id)
        if result["status"] != "completed":
            raise SystemExit(result)

        final_video = require_artifact(api, task_id, "final.mp4")
        cover_image = require_artifact(api, task_id, "cover.png")
        template_report = require_artifact(api, task_id, "template_report.json")
        print(f"task_id={task_id}")
        print(f"final_video={final_video}")
        print(f"cover_image={cover_image}")
        print(f"template_report={template_report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
