#!/usr/bin/env python3
from pathlib import Path

from _smoke import client


def _raise_for_status(response) -> None:
    if response.status_code >= 400:
        raise SystemExit(f"HTTP {response.status_code}: {response.text}")


def main() -> int:
    runtime_inputs = Path("storage") / "reference_inputs"
    runtime_inputs.mkdir(parents=True, exist_ok=True)
    source_video = runtime_inputs / "reference.placeholder.mp4"
    source_video.write_bytes(b"SPRINT_15_REFERENCE_VIDEO_PLACEHOLDER")

    with client() as api:
        created = api.post(
            "/projects/project_demo/references",
            json={
                "title": "Sprint 15 Reference Video",
                "source_path": str(source_video),
                "metadata": {"mode": "dry-run"},
            },
        )
        _raise_for_status(created)
        reference_id = created.json()["reference_id"]

        analyzed = api.post(f"/references/{reference_id}/analyze")
        _raise_for_status(analyzed)
        if analyzed.json()["status"] != "analyzed":
            raise SystemExit(analyzed.json())

        analysis = api.get(f"/references/{reference_id}/analysis")
        _raise_for_status(analysis)
        payload = analysis.json()
        print(f"reference_id={reference_id}")
        print(f"transcript={payload['reference']['transcript_json']}")
        print(f"reference_script={payload['reference']['reference_script_json']}")
        print(f"shot_breakdown={payload['reference']['shot_breakdown_json']}")
        print(f"style_summary={payload['reference']['style_summary_json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
