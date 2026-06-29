#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.digital_humans import DigitalHumanStore  # noqa: E402
from app.pipeline import VideoPipeline  # noqa: E402
from app.projects import ProjectStore  # noqa: E402
from app.schemas import (  # noqa: E402
    AvatarSourceType,
    AvatarStyleCard,
    CreateDigitalHumanRequest,
    CreateProjectRequest,
    CreateVideoTaskRequest,
    CreateVoiceProfileRequest,
    Platform,
    RenderProfileName,
    VoiceSourceType,
)
from app.settings import Settings  # noqa: E402
from app.store import TaskStore  # noqa: E402


def seed_trial_demo(
    *,
    storage_dir: str | Path = Path("storage"),
    project_id: str = "trial_demo",
    base_url: str = "http://127.0.0.1:8080",
) -> dict[str, object]:
    settings = Settings(dry_run=True, storage_dir=Path(storage_dir))
    project_store = ProjectStore(settings)
    digital_store = DigitalHumanStore(settings)
    task_store = TaskStore(settings)

    project = project_store.create(
        CreateProjectRequest(
            project_id=project_id,
            name="Aivo 试用演示",
            metadata={"source": "trial_seed", "purpose": "customer_demo"},
        )
    )
    profile = digital_store.create(
        project_id,
        CreateDigitalHumanRequest(
            name="试用合成主播",
            avatar_source_type=AvatarSourceType.generated,
            avatar_style=AvatarStyleCard(
                style="clean_studio",
                prompt="亲和、专业的合成 IP 主播，干净演播室光线",
                negative_prompt="真人、平台水印、受版权保护的角色",
                seed=2301,
            ),
            metadata={"source": "trial_seed"},
        ),
    )
    voice = digital_store.create_voice_profile(
        profile.digital_human_id,
        CreateVoiceProfileRequest(
            name="试用合成声音",
            voice_source_type=VoiceSourceType.synthetic,
            engine="dryrun",
            metadata={"source": "trial_seed"},
        ),
    )
    task = task_store.create(
        CreateVideoTaskRequest(
            brand_name="Aivo 试用演示",
            persona="合成数字人主播",
            topic="演示客户如何在本地创建一条 AI IP 口播短视频",
            project_id=project_id,
            digital_human_id=profile.digital_human_id,
            voice_profile_id=voice.voice_profile_id,
            platform=Platform.douyin,
            duration_seconds=30,
            render_profile=RenderProfileName.preview,
            video_template_id="clean_talking_head",
            script_review_required=False,
            export_jianying_draft=True,
            use_digital_human_pipeline=True,
            metadata={"source": "trial_seed"},
        )
    )
    completed = asyncio.run(VideoPipeline(settings, task_store).run(task))
    return {
        "project_id": project["project_id"],
        "digital_human_id": profile.digital_human_id,
        "voice_profile_id": voice.voice_profile_id,
        "task_id": completed.task_id,
        "task_status": completed.status.value,
        "studio_url": base_url.rstrip("/") + "/",
        "final_video": completed.artifacts.final_video,
        "jianying_draft": completed.artifacts.jianying_draft,
        "publish_package": completed.artifacts.publish_package,
        "download_urls": {
            "final_video": f"/tasks/{completed.task_id}/download/final-video",
            "jianying_draft": f"/tasks/{completed.task_id}/download/jianying-draft",
            "publish_package": f"/tasks/{completed.task_id}/download/publish-package",
            "quality_reports": f"/tasks/{completed.task_id}/download/quality-reports",
            "all_artifacts": f"/tasks/{completed.task_id}/artifacts.zip",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="创建本地 dry-run 试用演示项目。")
    parser.add_argument("--storage-dir", default="storage")
    parser.add_argument("--project-id", default="trial_demo")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    args = parser.parse_args()
    result = seed_trial_demo(storage_dir=args.storage_dir, project_id=args.project_id, base_url=args.base_url)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
