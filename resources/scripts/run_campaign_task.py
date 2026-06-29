#!/usr/bin/env python3
from pathlib import Path

from _smoke import _raise_for_status, client


def main() -> int:
    with client() as api:
        human = api.post(
            "/projects/project_demo/digital-humans",
            json={"name": "Campaign Smoke Host", "avatar_source_type": "generated"},
        )
        _raise_for_status(human)
        digital_human_id = human.json()["digital_human_id"]

        voice = api.post(
            f"/digital-humans/{digital_human_id}/voice-profiles",
            json={"name": "Campaign Smoke Voice", "voice_source_type": "synthetic"},
        )
        _raise_for_status(voice)
        voice_profile_id = voice.json()["voice_profile_id"]

        campaign = api.post(
            "/projects/project_demo/campaigns",
            json={
                "name": "Campaign smoke",
                "digital_human_id": digital_human_id,
                "voice_profile_id": voice_profile_id,
                "topics": ["Campaign smoke topic one", "Campaign smoke topic two"],
                "render_profile": "batch",
                "video_template_id": "clean_talking_head",
            },
        )
        _raise_for_status(campaign)
        campaign_id = campaign.json()["campaign_id"]

        run = api.post(f"/campaigns/{campaign_id}/run")
        _raise_for_status(run)
        if run.json()["status"] != "completed":
            raise SystemExit(run.json())

        tasks = api.get(f"/campaigns/{campaign_id}/tasks")
        _raise_for_status(tasks)
        rows = tasks.json()["tasks"]
        if len(rows) != 2 or {row["status"] for row in rows} != {"completed"}:
            raise SystemExit(tasks.json())

        zip_response = api.get(f"/campaigns/{campaign_id}/download.zip")
        _raise_for_status(zip_response)
        zip_path = Path("storage") / "campaign_smoke_results.zip"
        zip_path.write_bytes(zip_response.content)

        print(f"campaign_id={campaign_id}")
        print("task_ids=" + ",".join(row["task_id"] for row in rows))
        print(f"download_zip={zip_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
