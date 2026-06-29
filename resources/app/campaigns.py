from __future__ import annotations

import csv
import io
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.audit import append_audit_event
from app.digital_humans import DigitalHumanStore
from app.pipeline import VideoPipeline
from app.schemas import (
    Campaign,
    CampaignItem,
    CampaignItemStatus,
    CampaignSourceType,
    CampaignStatus,
    CreateCampaignRequest,
    CreateVideoTaskRequest,
    TaskStatus,
)
from app.settings import Settings
from app.store import TaskStore
from app.utils.files import ensure_dir, read_json, write_json


class CampaignStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.projects_root = ensure_dir(settings.storage_dir / "projects")
        self.index_root = ensure_dir(settings.storage_dir / "campaigns")
        self.digital_humans = DigitalHumanStore(settings)

    def project_dir(self, project_id: str) -> Path:
        return ensure_dir(self.projects_root / project_id)

    def campaign_root(self, project_id: str) -> Path:
        return ensure_dir(self.project_dir(project_id) / "campaigns")

    def campaign_dir(self, project_id: str, campaign_id: str) -> Path:
        return ensure_dir(self.campaign_root(project_id) / campaign_id)

    def campaign_file(self, project_id: str, campaign_id: str) -> Path:
        return self.campaign_dir(project_id, campaign_id) / "campaign.json"

    def index_file(self, campaign_id: str) -> Path:
        return self.index_root / f"{campaign_id}.json"

    def create(self, project_id: str, request: CreateCampaignRequest) -> Campaign:
        profile = self.digital_humans.get(request.digital_human_id)
        if profile.project_id != project_id:
            raise ValueError(f"digital human {request.digital_human_id} does not belong to project {project_id}")
        self.digital_humans.get_voice_profile(request.digital_human_id, request.voice_profile_id)

        items = self._items_from_request(project_id, request)
        if not items:
            raise ValueError("campaign requires at least one topic, rewritten script, or CSV row")

        campaign = Campaign(
            project_id=project_id,
            name=request.name,
            digital_human_id=request.digital_human_id,
            voice_profile_id=request.voice_profile_id,
            role_model_id=request.role_model_id,
            platform=request.platform,
            duration_seconds=request.duration_seconds,
            render_profile=request.render_profile,
            video_template_id=request.video_template_id,
            export_jianying_draft=request.export_jianying_draft,
            script_review_required=request.script_review_required,
            items=items,
            metadata=request.metadata,
        )
        self.save(campaign)
        append_audit_event(
            self.settings.storage_dir,
            action="campaign.created",
            project_id=project_id,
            digital_human_id=request.digital_human_id,
            details={"campaign_id": campaign.campaign_id, "item_count": len(campaign.items)},
        )
        return campaign

    def save(self, campaign: Campaign) -> Campaign:
        campaign.updated_at = datetime.now(timezone.utc)
        payload = campaign.model_dump(mode="json")
        write_json(self.campaign_file(campaign.project_id, campaign.campaign_id), payload)
        write_json(self.index_file(campaign.campaign_id), payload)
        return campaign

    def get(self, campaign_id: str) -> Campaign:
        path = self.index_file(campaign_id)
        if not path.exists():
            raise KeyError(f"campaign not found: {campaign_id}")
        return Campaign.model_validate(read_json(path))

    async def run(
        self,
        campaign_id: str,
        *,
        retry_failed: bool,
        force: bool,
        task_store: TaskStore,
        pipeline: VideoPipeline,
    ) -> Campaign:
        campaign = self.get(campaign_id)
        profile = self.digital_humans.get(campaign.digital_human_id)
        campaign.status = CampaignStatus.running
        self.save(campaign)
        append_audit_event(
            self.settings.storage_dir,
            action="campaign.run_started",
            project_id=campaign.project_id,
            digital_human_id=campaign.digital_human_id,
            details={"campaign_id": campaign.campaign_id, "retry_failed": retry_failed, "force": force},
        )

        for item in campaign.items:
            if retry_failed and item.status != CampaignItemStatus.failed:
                continue
            if item.status == CampaignItemStatus.completed and item.task_id and not force:
                continue

            item.status = CampaignItemStatus.running
            item.error = None
            self.save(campaign)
            try:
                if force or not item.task_id:
                    task = task_store.create(self._task_request(campaign, item, profile.name))
                    item.task_id = task.task_id
                    self.save(campaign)
                else:
                    task = task_store.get(item.task_id)
                    if force:
                        task.request.force_render = True
                        task_store.save(task)

                task = await pipeline.run(task)
                if task.status == TaskStatus.completed:
                    item.status = CampaignItemStatus.completed
                    item.error = None
                    append_audit_event(
                        self.settings.storage_dir,
                        action="campaign.item_completed",
                        task_id=task.task_id,
                        project_id=campaign.project_id,
                        digital_human_id=campaign.digital_human_id,
                        details={"campaign_id": campaign.campaign_id, "item_id": item.item_id},
                    )
                else:
                    item.status = CampaignItemStatus.failed
                    item.error = task.error or f"task ended with status {task.status}"
                    append_audit_event(
                        self.settings.storage_dir,
                        action="campaign.item_failed",
                        task_id=task.task_id,
                        project_id=campaign.project_id,
                        digital_human_id=campaign.digital_human_id,
                        details={"campaign_id": campaign.campaign_id, "item_id": item.item_id, "error": item.error},
                    )
            except Exception as exc:
                item.status = CampaignItemStatus.failed
                item.error = str(exc)
            finally:
                self.save(campaign)

        statuses = [item.status for item in campaign.items]
        if statuses and all(status == CampaignItemStatus.completed for status in statuses):
            campaign.status = CampaignStatus.completed
        elif any(status == CampaignItemStatus.completed for status in statuses):
            campaign.status = CampaignStatus.partial_failed
        else:
            campaign.status = CampaignStatus.failed
        self.save(campaign)
        append_audit_event(
            self.settings.storage_dir,
            action="campaign.completed",
            project_id=campaign.project_id,
            digital_human_id=campaign.digital_human_id,
            details={"campaign_id": campaign.campaign_id, "status": campaign.status},
        )
        return campaign

    def task_rows(self, campaign_id: str, task_store: TaskStore) -> list[dict[str, Any]]:
        campaign = self.get(campaign_id)
        rows: list[dict[str, Any]] = []
        for item in campaign.items:
            task_payload: dict[str, Any] | None = None
            if item.task_id:
                try:
                    task = task_store.get(item.task_id)
                    task_payload = {
                        "task_id": task.task_id,
                        "status": task.status,
                        "error": task.error,
                        "artifacts": task.artifacts.model_dump(mode="json"),
                        "updated_at": task.updated_at.isoformat(),
                    }
                except KeyError:
                    task_payload = {"task_id": item.task_id, "status": "missing", "error": "task file missing", "artifacts": {}}
            rows.append(
                {
                    "campaign_id": campaign.campaign_id,
                    "item_id": item.item_id,
                    "source_type": item.source_type,
                    "topic": item.topic,
                    "status": item.status,
                    "error": item.error,
                    "task_id": item.task_id,
                    "artifacts": task_payload.get("artifacts", {}) if task_payload else {},
                    "task": task_payload,
                }
            )
        return rows

    def build_download_zip(self, campaign_id: str, task_store: TaskStore) -> Path:
        campaign = self.get(campaign_id)
        campaign_dir = self.campaign_dir(campaign.project_id, campaign.campaign_id)
        zip_path = campaign_dir / "campaign_results.zip"
        rows = self.task_rows(campaign_id, task_store)
        write_json(campaign_dir / "campaign_tasks.json", {"campaign_id": campaign_id, "tasks": rows})
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.write(self.campaign_file(campaign.project_id, campaign.campaign_id), "campaign.json")
            archive.write(campaign_dir / "campaign_tasks.json", "campaign_tasks.json")
            for item in campaign.items:
                if not item.task_id:
                    continue
                task_dir = task_store.task_dir(item.task_id)
                for path in sorted(task_dir.rglob("*")) if task_dir.exists() else []:
                    if not path.is_file() or path.name.endswith(".zip"):
                        continue
                    rel = path.relative_to(task_dir).as_posix()
                    archive.write(path, f"tasks/{item.task_id}/{rel}")
        return zip_path

    def _items_from_request(self, project_id: str, request: CreateCampaignRequest) -> list[CampaignItem]:
        items: list[CampaignItem] = []
        for topic in request.topics:
            clean = str(topic).strip()
            if clean:
                items.append(CampaignItem(source_type=CampaignSourceType.topic, topic=clean))

        scripts = list(request.rewritten_scripts)
        if request.rewrite_id and not scripts:
            scripts = self._rewritten_scripts_from_rewrite_id(project_id, request.rewrite_id)
        for script in scripts:
            topic = str(script.get("title") or script.get("hook") or script.get("script_id") or "Rewritten script").strip()
            fixed_script = "\n".join(
                str(script.get(key, "")).strip()
                for key in ("hook", "body", "cta")
                if str(script.get(key, "")).strip()
            )
            items.append(
                CampaignItem(
                    source_type=CampaignSourceType.rewritten_script,
                    topic=topic,
                    fixed_script=fixed_script or None,
                    source_script_id=str(script.get("script_id") or "") or None,
                    metadata={"script": script},
                )
            )

        for row in self._rows_from_csv(request.csv_text):
            topic = str(row.get("topic") or row.get("title") or row.get("script") or "").strip()
            if topic:
                fixed_script = str(row.get("script") or "").strip() or None
                items.append(
                    CampaignItem(
                        source_type=CampaignSourceType.csv,
                        topic=topic,
                        fixed_script=fixed_script,
                        metadata={"csv_row": row},
                    )
                )
        return items

    def _rewritten_scripts_from_rewrite_id(self, project_id: str, rewrite_id: str) -> list[dict[str, Any]]:
        root = self.project_dir(project_id) / "references"
        for path in sorted(root.glob(f"*/rewrites/{rewrite_id}/rewrite.json")) if root.exists() else []:
            data = read_json(path)
            return list(data.get("scripts", []))
        raise KeyError(f"rewrite not found in project {project_id}: {rewrite_id}")

    @staticmethod
    def _rows_from_csv(csv_text: str | None) -> list[dict[str, str]]:
        if not csv_text or not csv_text.strip():
            return []
        sample = csv_text.strip()
        stream = io.StringIO(sample)
        try:
            dialect = csv.Sniffer().sniff(sample[:1024])
        except csv.Error:
            dialect = csv.excel
        has_header = True
        try:
            has_header = csv.Sniffer().has_header(sample[:1024])
        except csv.Error:
            pass
        first_line = sample.splitlines()[0] if sample.splitlines() else ""
        header_tokens = {token.strip().lower() for token in next(csv.reader([first_line], dialect=dialect), [])}
        if header_tokens & {"topic", "title", "script"}:
            has_header = True
        if has_header:
            return [{str(k or "").strip(): str(v or "").strip() for k, v in row.items()} for row in csv.DictReader(stream, dialect=dialect)]
        rows = []
        for index, row in enumerate(csv.reader(stream, dialect=dialect), start=1):
            if not row:
                continue
            rows.append({"topic": str(row[0]).strip(), "row_index": str(index)})
        return rows

    @staticmethod
    def _task_request(campaign: Campaign, item: CampaignItem, brand_name: str) -> CreateVideoTaskRequest:
        return CreateVideoTaskRequest(
            brand_name=brand_name,
            persona="Synthetic digital human host",
            topic=item.topic,
            project_id=campaign.project_id,
            digital_human_id=campaign.digital_human_id,
            voice_profile_id=campaign.voice_profile_id,
            role_model_id=campaign.role_model_id,
            platform=campaign.platform,
            duration_seconds=campaign.duration_seconds,
            fixed_script=item.fixed_script,
            render_profile=campaign.render_profile,
            video_template_id=campaign.video_template_id,
            export_jianying_draft=campaign.export_jianying_draft,
            script_review_required=campaign.script_review_required,
            use_digital_human_pipeline=True,
            metadata={
                "campaign_id": campaign.campaign_id,
                "campaign_item_id": item.item_id,
                "campaign_source_type": item.source_type,
                "source_script_id": item.source_script_id,
                **item.metadata,
            },
        )
