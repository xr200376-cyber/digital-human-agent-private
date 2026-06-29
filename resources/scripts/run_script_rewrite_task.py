#!/usr/bin/env python3
from pathlib import Path

from _smoke import client


def _raise_for_status(response) -> None:
    if response.status_code >= 400:
        raise SystemExit(f"HTTP {response.status_code}: {response.text}")


def main() -> int:
    runtime_inputs = Path("storage") / "rewrite_inputs"
    runtime_inputs.mkdir(parents=True, exist_ok=True)
    source_video = runtime_inputs / "rewrite_reference.placeholder.mp4"
    source_video.write_bytes(b"SPRINT_16_REWRITE_REFERENCE_PLACEHOLDER")

    with client() as api:
        created = api.post(
            "/projects/project_demo/references",
            json={"title": "Sprint 16 Rewrite Reference", "source_path": str(source_video)},
        )
        _raise_for_status(created)
        reference_id = created.json()["reference_id"]

        analyzed = api.post(f"/references/{reference_id}/analyze")
        _raise_for_status(analyzed)

        rewritten = api.post(
            f"/references/{reference_id}/rewrite",
            json={
                "reference_id": reference_id,
                "project_id": "project_demo",
                "product_info": {"name": "Aivo Studio", "benefit": "batch digital human script production"},
                "count": 3,
                "platform": "douyin",
                "tone": "practical",
            },
        )
        _raise_for_status(rewritten)
        body = rewritten.json()
        if len(body["scripts"]) != 3:
            raise SystemExit(body)

        listing = api.get(f"/references/{reference_id}/rewrites")
        _raise_for_status(listing)
        print(f"reference_id={reference_id}")
        print(f"rewrite_id={body['rewrite_id']}")
        print(f"script_count={len(body['scripts'])}")
        print(f"rewritten_scripts={body['rewritten_scripts_json']}")
        print(f"script_scores={body['script_scores_json']}")
        print(f"rewrite_report={body['rewrite_report_json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
