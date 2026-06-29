from __future__ import annotations

import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.audit import append_audit_event
from app.schemas import (
    CreatePublishQueueItemRequest,
    PatchPublishQueueItemRequest,
    PlatformPublishPackage,
    PublishQueueItem,
    PublishStatus,
    TaskStatus,
)
from app.settings import Settings
from app.store import TaskStore
from app.utils.files import ensure_dir, read_json, write_json


SUPPORTED_PUBLISH_PLATFORMS = ("douyin", "xiaohongshu", "kuaishou", "shipinhao", "tiktok")


class PublishConsoleStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.root = ensure_dir(settings.storage_dir / "publish_queue")

    def queue_dir(self, queue_id: str) -> Path:
        return ensure_dir(self.root / queue_id)

    def queue_file(self, queue_id: str) -> Path:
        return self.queue_dir(queue_id) / "publish_queue_item.json"

    def create_from_task(
        self,
        task_id: str,
        request: CreatePublishQueueItemRequest,
        task_store: TaskStore,
    ) -> PublishQueueItem:
        platform = self._normalize_platform(request.platform)
        task = task_store.get(task_id)
        if task.status != TaskStatus.completed:
            raise ValueError(f"task must be completed before publish handoff: {task_id}")
        task_dir = task_store.task_dir(task_id)
        platform_package = self._platform_package(platform, task_dir)
        platform_package = self._apply_request_overrides(platform, platform_package, request)
        item = PublishQueueItem(
            task_id=task_id,
            project_id=task.request.project_id,
            digital_human_id=task.request.digital_human_id,
            platform=platform,
            status=request.status or PublishStatus.ready,
            scheduled_at=request.scheduled_at,
            reviewer_note=request.reviewer_note,
            platform_package=platform_package,
            artifacts={
                "final_video": task.artifacts.final_video,
                "cover_image": task.artifacts.cover_image,
                "publish_package": task.artifacts.publish_package,
                "template_report": task.artifacts.template_report,
                "jianying_draft": task.artifacts.jianying_draft,
            },
            metadata=request.metadata,
        )
        self.save(item)
        append_audit_event(
            self.settings.storage_dir,
            action="publish.queue_created",
            task_id=task.task_id,
            project_id=task.request.project_id,
            digital_human_id=task.request.digital_human_id,
            details={"queue_id": item.queue_id, "platform": platform},
        )
        return item

    def save(self, item: PublishQueueItem) -> PublishQueueItem:
        item.updated_at = datetime.now(timezone.utc)
        payload = item.model_dump(mode="json")
        write_json(self.queue_file(item.queue_id), payload)
        write_json(self.queue_dir(item.queue_id) / "platform_package.json", item.platform_package.model_dump(mode="json"))
        write_json(
            self.queue_dir(item.queue_id) / "publish_checklist.json",
            {"queue_id": item.queue_id, "platform": item.platform, "items": item.platform_package.publish_checklist},
        )
        return item

    def get(self, queue_id: str) -> PublishQueueItem:
        path = self.queue_file(queue_id)
        if not path.exists():
            raise KeyError(f"publish queue item not found: {queue_id}")
        return PublishQueueItem.model_validate(read_json(path))

    def list(self) -> list[PublishQueueItem]:
        return [PublishQueueItem.model_validate(read_json(path)) for path in sorted(self.root.glob("*/publish_queue_item.json"))]

    def patch(self, queue_id: str, request: PatchPublishQueueItemRequest) -> PublishQueueItem:
        item = self.get(queue_id)
        if request.status is not None:
            item.status = request.status
            if request.status == PublishStatus.published and not item.reviewed_at:
                item.reviewed_at = datetime.now(timezone.utc).isoformat()
        if request.scheduled_at is not None:
            item.scheduled_at = request.scheduled_at
        if request.reviewer_note is not None:
            item.reviewer_note = request.reviewer_note
        if request.external_url is not None:
            item.external_url = request.external_url
        if request.failure_reason is not None:
            item.failure_reason = request.failure_reason
        if request.metadata is not None:
            item.metadata.update(request.metadata)
        self.save(item)
        append_audit_event(
            self.settings.storage_dir,
            action="publish.status_updated",
            task_id=item.task_id,
            project_id=item.project_id,
            digital_human_id=item.digital_human_id,
            details={"queue_id": item.queue_id, "status": item.status},
        )
        return item

    def board(self) -> dict[str, list[dict[str, Any]]]:
        columns: dict[str, list[dict[str, Any]]] = {status.value: [] for status in PublishStatus}
        for item in self.list():
            columns[item.status.value].append(self._summary(item))
        return columns

    def calendar(self) -> list[dict[str, Any]]:
        rows = []
        for item in self.list():
            if not item.scheduled_at:
                continue
            rows.append({**self._summary(item), "date": item.scheduled_at[:10], "scheduled_at": item.scheduled_at})
        return sorted(rows, key=lambda row: row.get("scheduled_at") or "")

    def build_handoff_zip(self, queue_id: str, task_store: TaskStore) -> Path:
        item = self.get(queue_id)
        queue_dir = self.queue_dir(queue_id)
        task_dir = task_store.task_dir(item.task_id)
        zip_path = queue_dir / "handoff.zip"
        self.save(item)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.write(queue_dir / "publish_queue_item.json", "publish_queue_item.json")
            archive.write(queue_dir / "platform_package.json", "platform_package.json")
            archive.write(queue_dir / "publish_checklist.json", "publish_checklist.json")
            for source_name, target_name in [
                ("final.mp4", "assets/final.mp4"),
                ("cover.png", "assets/cover.png"),
                ("publish_package.json", "publish_package.json"),
                ("template_report.json", "template_report.json"),
                ("digital_human_quality_report.json", "quality_reports/digital_human_quality_report.json"),
                ("render_stability_report.json", "quality_reports/render_stability_report.json"),
            ]:
                path = task_dir / source_name
                if path.exists() and path.is_file():
                    archive.write(path, target_name)
        return zip_path

    def _platform_package(self, platform: str, task_dir: Path) -> PlatformPublishPackage:
        script = read_json(task_dir / "script.json") if (task_dir / "script.json").exists() else {}
        template_report = read_json(task_dir / "template_report.json") if (task_dir / "template_report.json").exists() else {}
        publish_package = read_json(task_dir / "publish_package.json") if (task_dir / "publish_package.json").exists() else {}
        title = self._title(script, template_report)
        hook = self._hook(script)
        description = self._description(platform, script, publish_package)
        hashtags = self._hashtags(platform, script)
        cover_text = str(template_report.get("cover", {}).get("title") or title)[:32]
        return PlatformPublishPackage(
            platform=platform,
            title=title,
            description=description,
            hashtags=hashtags,
            cover_text=cover_text,
            publish_checklist=self._checklist(platform),
            platform_fields=self._platform_fields(platform, title, hook, description, hashtags),
        )

    @classmethod
    def _apply_request_overrides(
        cls,
        platform: str,
        package: PlatformPublishPackage,
        request: CreatePublishQueueItemRequest,
    ) -> PlatformPublishPackage:
        title = str(request.title or "").strip()
        description = str(request.description or "").strip()
        cover_text = str(request.cover_text or "").strip()
        hashtags = cls._clean_hashtags(request.hashtags)
        if title:
            package.title = title
        if description:
            package.description = description
        if hashtags:
            package.hashtags = hashtags
        if cover_text:
            package.cover_text = cover_text[:32]
        package.platform_fields = cls._platform_fields(
            platform,
            package.title,
            package.title,
            package.description,
            package.hashtags,
        )
        return package

    @staticmethod
    def _clean_hashtags(values: list[str] | None) -> list[str]:
        if not values:
            return []
        cleaned: list[str] = []
        for value in values:
            text = str(value or "").strip().strip("#,，、.。;； ")
            if text and text not in cleaned:
                cleaned.append(text)
        return cleaned[:8]

    @staticmethod
    def _normalize_platform(platform: str) -> str:
        value = (platform or "douyin").strip().lower()
        aliases = {"wechat_channels": "shipinhao", "video_account": "shipinhao"}
        value = aliases.get(value, value)
        if value not in SUPPORTED_PUBLISH_PLATFORMS:
            raise ValueError(f"unsupported publish platform: {platform}")
        return value

    @staticmethod
    def _title(script: dict[str, Any], template_report: dict[str, Any]) -> str:
        raw = str(script.get("title") or script.get("hook") or template_report.get("cover", {}).get("title") or "Digital human short video")
        return raw.replace("\n", " ").strip()[:48] or "Digital human short video"

    @staticmethod
    def _hook(script: dict[str, Any]) -> str:
        segments = script.get("segments") or []
        if segments:
            return str(segments[0].get("text") or "").strip()
        return str(script.get("hook") or script.get("body") or "").strip()

    @staticmethod
    def _description(platform: str, script: dict[str, Any], publish_package: dict[str, Any]) -> str:
        body = str(script.get("body") or "").strip()
        cta = str(script.get("cta") or "").strip()
        base = "\n".join(part for part in [body[:180], cta] if part)
        if platform == "xiaohongshu":
            return base or "A structured note for manual Xiaohongshu publishing."
        if platform == "tiktok":
            return base or "Manual TikTok handoff package."
        return base or f"Manual {platform} publish handoff for task {publish_package.get('task_id', '')}."

    @staticmethod
    def _hashtags(platform: str, script: dict[str, Any]) -> list[str]:
        topic_words = [
            word.strip("#,.;:!?，。！？")
            for word in str(script.get("hook") or script.get("title") or "digital human").split()
            if word.strip("#,.;:!?，。！？")
        ]
        defaults = {
            "douyin": ["AI数字人", "口播短视频", "商业增长"],
            "xiaohongshu": ["AI工具", "数字人", "内容生产"],
            "kuaishou": ["数字人口播", "短视频运营", "实用干货"],
            "shipinhao": ["视频号运营", "数字人", "知识分享"],
            "tiktok": ["AIVideo", "DigitalHuman", "ShortVideo"],
        }
        return list(dict.fromkeys([*topic_words[:2], *defaults.get(platform, [])]))[:8]

    @staticmethod
    def _checklist(platform: str) -> list[str]:
        common = [
            "Review final.mp4 manually before upload.",
            "Confirm cover text does not obscure faces or subtitles.",
            "Confirm title, description, and hashtags match platform rules.",
            "Upload manually with an authorized account.",
            "Record external URL or failure reason after manual action.",
        ]
        platform_specific = {
            "douyin": "Check Douyin title length and commercial claim wording.",
            "xiaohongshu": "Check Xiaohongshu note style, hashtags, and sensitive claims.",
            "kuaishou": "Check Kuaishou caption readability and local compliance.",
            "shipinhao": "Check Shipinhao account category and video description.",
            "tiktok": "Check TikTok music, disclosure, and region-specific policy.",
        }
        return [platform_specific.get(platform, "Check platform-specific publishing rules."), *common]

    @staticmethod
    def _platform_fields(platform: str, title: str, hook: str, description: str, hashtags: list[str]) -> dict[str, Any]:
        base = {"manual_publish_only": True, "auto_login": False}
        if platform == "douyin":
            return {**base, "douyin_title": title[:30], "douyin_hashtag_count": len(hashtags)}
        if platform == "xiaohongshu":
            return {**base, "xiaohongshu_note_style": True, "xiaohongshu_title": title[:20]}
        if platform == "kuaishou":
            return {**base, "kuaishou_caption": description[:80], "kuaishou_cover_title": title[:24]}
        if platform == "shipinhao":
            return {**base, "shipinhao_description": description[:120], "wechat_channels_alias": True}
        if platform == "tiktok":
            return {**base, "tiktok_caption": f"{hook[:80]} {' '.join('#' + tag for tag in hashtags[:4])}".strip()}
        return base

    @staticmethod
    def _summary(item: PublishQueueItem) -> dict[str, Any]:
        return {
            "queue_id": item.queue_id,
            "task_id": item.task_id,
            "project_id": item.project_id,
            "digital_human_id": item.digital_human_id,
            "platform": item.platform,
            "status": item.status,
            "title": item.platform_package.title,
            "scheduled_at": item.scheduled_at,
            "external_url": item.external_url,
            "failure_reason": item.failure_reason,
            "updated_at": item.updated_at.isoformat(),
        }
