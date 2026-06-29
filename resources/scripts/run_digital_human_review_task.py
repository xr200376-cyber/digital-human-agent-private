#!/usr/bin/env python3
from _smoke import approve_task, client, create_digital_human_task, require_artifact, run_task


def main() -> int:
    with client() as api:
        task_id = create_digital_human_task(api, render_profile="preview", review_required=True)
        waiting = run_task(api, task_id)
        if waiting["status"] != "waiting_for_review":
            raise SystemExit(waiting)
        approve_task(api, task_id)
        completed = run_task(api, task_id)
        if completed["status"] != "completed":
            raise SystemExit(completed)
        print(f"task_id={task_id}")
        print(f"voice_audio={require_artifact(api, task_id, 'voice.wav')}")
        print(f"final_video={require_artifact(api, task_id, 'final.mp4')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
