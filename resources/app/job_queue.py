from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from app.audit import append_audit_event
from app.campaigns import CampaignStore
from app.pipeline import VideoPipeline
from app.schemas import CampaignStatus, JobKind, JobRecord, JobStatus, TaskStatus
from app.settings import Settings
from app.store import TaskStore
from app.utils.files import ensure_dir, read_json, write_json


class JobQueue(Protocol):
    def enqueue(
        self,
        *,
        kind: JobKind,
        payload: dict[str, Any],
        max_retries: int = 0,
        parent_job_id: str | None = None,
        attempt: int = 1,
        metadata: dict[str, Any] | None = None,
    ) -> JobRecord:
        ...

    def get(self, job_id: str) -> JobRecord:
        ...

    def list(self, *, status: JobStatus | None = None) -> list[JobRecord]:
        ...

    async def run_next(self) -> JobRecord:
        ...

    async def run_job(self, job_id: str) -> JobRecord:
        ...

    def retry(self, job_id: str) -> JobRecord:
        ...

    def cancel(self, job_id: str) -> JobRecord:
        ...


class LocalJobQueue:
    """File-backed job queue for local MVP and dry-run workflows."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.root = ensure_dir(settings.storage_dir / "jobs")

    def job_dir(self, job_id: str) -> Path:
        return ensure_dir(self.root / job_id)

    def job_file(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "job.json"

    def log_file(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "job.log"

    def enqueue(
        self,
        *,
        kind: JobKind,
        payload: dict[str, Any],
        max_retries: int = 0,
        parent_job_id: str | None = None,
        attempt: int = 1,
        metadata: dict[str, Any] | None = None,
    ) -> JobRecord:
        job = JobRecord(
            kind=kind,
            payload=payload,
            max_retries=max_retries,
            parent_job_id=parent_job_id,
            attempt=attempt,
            metadata=metadata or {},
        )
        job.logs_path = str(self.log_file(job.job_id))
        self.save(job)
        self._append_log(job.job_id, f"job queued kind={job.kind.value} payload={json.dumps(payload, ensure_ascii=False)}")
        append_audit_event(
            self.settings.storage_dir,
            action="job.queued",
            task_id=payload.get("task_id"),
            project_id=payload.get("project_id"),
            digital_human_id=payload.get("digital_human_id"),
            details={"job_id": job.job_id, "kind": job.kind.value, "parent_job_id": parent_job_id},
        )
        return job

    def save(self, job: JobRecord) -> JobRecord:
        job.updated_at = datetime.now(timezone.utc)
        write_json(self.job_file(job.job_id), job.model_dump(mode="json"))
        return job

    def get(self, job_id: str) -> JobRecord:
        path = self.job_file(job_id)
        if not path.exists():
            raise KeyError(f"job not found: {job_id}")
        return JobRecord.model_validate(read_json(path))

    def list(self, *, status: JobStatus | None = None) -> list[JobRecord]:
        rows: list[JobRecord] = []
        for path in sorted(self.root.glob("*/job.json")):
            try:
                job = JobRecord.model_validate(read_json(path))
            except (ValueError, TypeError, json.JSONDecodeError):
                continue
            if status is None or job.status == status:
                rows.append(job)
        return sorted(rows, key=lambda item: item.created_at, reverse=True)

    def cancel(self, job_id: str) -> JobRecord:
        job = self.get(job_id)
        if job.status == JobStatus.succeeded:
            raise ValueError(f"cannot cancel succeeded job: {job_id}")
        if job.status != JobStatus.cancelled:
            job.status = JobStatus.cancelled
            job.finished_at = datetime.now(timezone.utc)
            self._append_log(job.job_id, "job cancelled")
            self.save(job)
            append_audit_event(
                self.settings.storage_dir,
                action="job.cancelled",
                task_id=job.payload.get("task_id"),
                project_id=job.payload.get("project_id"),
                digital_human_id=job.payload.get("digital_human_id"),
                details={"job_id": job.job_id, "kind": job.kind.value},
            )
        return job

    def retry(self, job_id: str) -> JobRecord:
        job = self.get(job_id)
        if job.status == JobStatus.running:
            raise ValueError(f"cannot retry running job: {job_id}")
        retry_job = self.enqueue(
            kind=job.kind,
            payload=job.payload,
            max_retries=job.max_retries,
            parent_job_id=job.job_id,
            attempt=job.attempt + 1,
            metadata={**job.metadata, "retry_of": job.job_id},
        )
        self._append_log(job.job_id, f"retry queued job_id={retry_job.job_id}")
        append_audit_event(
            self.settings.storage_dir,
            action="job.retry_queued",
            task_id=job.payload.get("task_id"),
            project_id=job.payload.get("project_id"),
            digital_human_id=job.payload.get("digital_human_id"),
            details={"job_id": job.job_id, "retry_job_id": retry_job.job_id},
        )
        return retry_job

    async def run_next(self) -> JobRecord:
        queued = sorted(self.list(status=JobStatus.queued), key=lambda item: item.created_at)
        if not queued:
            raise KeyError("no queued jobs")
        return await self.run_job(queued[0].job_id)

    async def run_job(self, job_id: str) -> JobRecord:
        job = self.get(job_id)
        if job.status == JobStatus.cancelled:
            return job
        if job.status != JobStatus.queued:
            raise ValueError(f"job is not queued: {job_id} status={job.status.value}")

        job.status = JobStatus.running
        job.started_at = datetime.now(timezone.utc)
        job.error = None
        self._append_log(job.job_id, "job running")
        self.save(job)
        append_audit_event(
            self.settings.storage_dir,
            action="job.running",
            task_id=job.payload.get("task_id"),
            project_id=job.payload.get("project_id"),
            digital_human_id=job.payload.get("digital_human_id"),
            details={"job_id": job.job_id, "kind": job.kind.value},
        )

        try:
            if job.kind == JobKind.render_task:
                result = await self._run_render_task(job)
            elif job.kind == JobKind.campaign_run:
                result = await self._run_campaign(job)
            else:
                raise ValueError(f"unsupported job kind: {job.kind}")
            job.result = result
            job.status = JobStatus.succeeded
            job.finished_at = datetime.now(timezone.utc)
            self._append_log(job.job_id, f"job succeeded result={json.dumps(result, ensure_ascii=False)}")
            self.save(job)
            append_audit_event(
                self.settings.storage_dir,
                action="job.succeeded",
                task_id=job.payload.get("task_id"),
                project_id=job.payload.get("project_id"),
                digital_human_id=job.payload.get("digital_human_id"),
                details={"job_id": job.job_id, "kind": job.kind.value},
            )
            return job
        except Exception as exc:
            job.status = JobStatus.failed
            job.error = str(exc)
            job.finished_at = datetime.now(timezone.utc)
            self._append_log(job.job_id, f"job failed error={exc}")
            self.save(job)
            append_audit_event(
                self.settings.storage_dir,
                action="job.failed",
                task_id=job.payload.get("task_id"),
                project_id=job.payload.get("project_id"),
                digital_human_id=job.payload.get("digital_human_id"),
                details={"job_id": job.job_id, "kind": job.kind.value, "error": str(exc)},
            )
            return job

    async def _run_render_task(self, job: JobRecord) -> dict[str, Any]:
        task_id = str(job.payload.get("task_id") or "")
        if not task_id:
            raise ValueError("render_task job requires task_id")
        task_store = TaskStore(self.settings)
        pipeline = VideoPipeline(self.settings, task_store)
        task = task_store.get(task_id)
        task = await pipeline.run(task)
        if task.status == TaskStatus.failed:
            raise RuntimeError(task.error or f"task failed: {task.task_id}")
        return {
            "task_id": task.task_id,
            "task_status": _value(task.status),
            "artifacts": task.artifacts.model_dump(mode="json"),
        }

    async def _run_campaign(self, job: JobRecord) -> dict[str, Any]:
        campaign_id = str(job.payload.get("campaign_id") or "")
        if not campaign_id:
            raise ValueError("campaign_run job requires campaign_id")
        task_store = TaskStore(self.settings)
        pipeline = VideoPipeline(self.settings, task_store)
        campaign_store = CampaignStore(self.settings)
        campaign = await campaign_store.run(
            campaign_id,
            retry_failed=bool(job.payload.get("retry_failed", False)),
            force=bool(job.payload.get("force", False)),
            task_store=task_store,
            pipeline=pipeline,
        )
        if campaign.status == CampaignStatus.failed:
            raise RuntimeError(f"campaign failed: {campaign.campaign_id}")
        return {
            "campaign_id": campaign.campaign_id,
            "campaign_status": _value(campaign.status),
            "task_ids": [item.task_id for item in campaign.items if item.task_id],
        }

    def _append_log(self, job_id: str, line: str) -> None:
        log_path = self.log_file(job_id)
        ensure_dir(log_path.parent)
        timestamp = datetime.now(timezone.utc).isoformat()
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"[{timestamp}] {line}\n")


class RedisRQJobQueue:
    """Scaffold for a future Redis/RQ backend.

    The local file queue remains the default. This placeholder keeps the
    interface explicit without adding Redis/RQ as a mandatory dependency.
    """

    def __init__(self, settings: Settings):
        self.settings = settings

    def readiness(self) -> dict[str, Any]:
        return {
            "backend": "redis_rq",
            "ready": False,
            "redis_url_configured": bool(self.settings.redis_url),
            "message": "Redis/RQ backend scaffold only; use LocalJobQueue for Sprint 21.",
        }


def _value(value: Any) -> Any:
    return getattr(value, "value", value)
