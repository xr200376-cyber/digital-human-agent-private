#!/usr/bin/env python3
from pathlib import Path

from _smoke import client, require_artifact, run_task


def _raise_for_status(response) -> None:
    if response.status_code >= 400:
        raise SystemExit(f"HTTP {response.status_code}: {response.text}")


def main() -> int:
    runtime_inputs = Path("storage") / "compat_inputs"
    runtime_inputs.mkdir(parents=True, exist_ok=True)
    pkl_path = runtime_inputs / "model_9.placeholder.pkl"
    video_path = runtime_inputs / "idle.placeholder.mp4"
    pkl_path.write_bytes(b"SPRINT_13F_PLACEHOLDER_PKL_PRESENCE_ONLY")
    video_path.write_bytes(b"SPRINT_13F_PLACEHOLDER_VIDEO_PRESENCE_ONLY")

    with client() as api:
        human = api.post(
            "/projects/project_demo/digital-humans",
            json={
                "name": "Sprint 13F Compat Host",
                "avatar_source_type": "generated",
                "avatar_style": {"style": "compat", "prompt": "role model compatibility host"},
            },
        )
        _raise_for_status(human)
        digital_human_id = human.json()["digital_human_id"]

        voice = api.post(
            f"/digital-humans/{digital_human_id}/voice-profiles",
            json={"name": "Compat Dry Run Voice", "voice_source_type": "synthetic", "engine": "dryrun"},
        )
        _raise_for_status(voice)
        voice_profile_id = voice.json()["voice_profile_id"]

        role = api.post(
            f"/digital-humans/{digital_human_id}/role-models",
            json={
                "source_video_asset_id": str(video_path),
                "idle_video_asset_id": str(video_path),
                "action_video_asset_id": str(video_path),
                "pkl_model_path": str(pkl_path),
                "engine_type": "yywav2lip",
            },
        )
        _raise_for_status(role)
        role_model_id = role.json()["role_model_id"]

        validate = api.post(f"/digital-humans/{digital_human_id}/role-models/{role_model_id}/validate")
        _raise_for_status(validate)
        if validate.json()["status"] != "ready":
            raise SystemExit(validate.json())

        task = api.post(
            "/projects/project_demo/digital-human-tasks",
            json={
                "digital_human_id": digital_human_id,
                "voice_profile_id": voice_profile_id,
                "role_model_id": role_model_id,
                "topic": "Sprint 13F compatibility dry-run",
                "render_profile": "compat",
                "script_review_required": False,
                "export_jianying_draft": True,
            },
        )
        _raise_for_status(task)
        task_id = task.json()["task_id"]

        result = run_task(api, task_id)
        if result["status"] != "completed":
            raise SystemExit(result)

        lip_synced = require_artifact(api, task_id, "lip_synced.mp4")
        final_video = require_artifact(api, task_id, "final.mp4")
        print(f"task_id={task_id}")
        print(f"role_model_id={role_model_id}")
        print(f"lip_synced={lip_synced}")
        print(f"final_video={final_video}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
