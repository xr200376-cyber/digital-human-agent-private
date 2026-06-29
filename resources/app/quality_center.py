from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

from app.audit import append_audit_event
from app.digital_humans import DigitalHumanStore
from app.pipeline import VideoPipeline
from app.projects import ProjectStore
from app.schemas import (
    BenchmarkReport,
    BenchmarkScenarioResult,
    CreateDigitalHumanRequest,
    CreateProjectRequest,
    CreateVideoTaskRequest,
    CreateVoiceProfileRequest,
    QualityDashboard,
    QualityMetricSummary,
    RunBenchmarkRequest,
    TaskStatus,
    VideoTask,
)
from app.settings import Settings
from app.store import TaskStore
from app.utils.files import ensure_dir, read_json, write_json


REPORT_NAMES = [
    "script_quality_report.json",
    "audio_quality_report.json",
    "avatar_render_report.json",
    "lip_sync_report.json",
    "render_stability_report.json",
    "digital_human_quality_report.json",
    "template_report.json",
]


class QualityCenter:
    def __init__(self, settings: Settings, store: TaskStore, pipeline: VideoPipeline):
        self.settings = settings
        self.store = store
        self.pipeline = pipeline

    def task_summary(self, task_id: str) -> QualityMetricSummary:
        task = self.store.get(task_id)
        return summarize_task(task, self.store.task_dir(task_id), self.settings.storage_dir)

    def dashboard(self) -> QualityDashboard:
        summaries = [
            summarize_task(task, self.store.task_dir(task.task_id), self.settings.storage_dir)
            for task in self._list_tasks()
        ]
        return build_dashboard(summaries)

    async def run_benchmark(self, request: RunBenchmarkRequest) -> BenchmarkReport:
        benchmark_id = "bench_" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        started = datetime.now(timezone.utc)
        project_id, digital_human_id, voice_profile_id = self._resolve_benchmark_profile(request, benchmark_id)
        scenarios: list[BenchmarkScenarioResult] = []
        for scenario, duration, count in [
            ("30s_task", 30, 1),
            ("60s_task", 60, 1),
            ("batch_10_task", 30, 10),
        ]:
            scenarios.append(
                await self._run_scenario(
                    benchmark_id=benchmark_id,
                    scenario=scenario,
                    project_id=project_id,
                    digital_human_id=digital_human_id,
                    voice_profile_id=voice_profile_id,
                    duration_seconds=duration,
                    count=count,
                    request=request,
                )
            )
        report = BenchmarkReport(
            benchmark_id=benchmark_id,
            status="completed" if all(row.failed_count == 0 for row in scenarios) else "partial_failed",
            started_at=started,
            finished_at=datetime.now(timezone.utc),
            scenarios=scenarios,
            dashboard=build_dashboard([summary for scenario in scenarios for summary in scenario.summaries]),
            download_url=f"/quality/benchmarks/{benchmark_id}/download.json",
        )
        report_path = self.benchmark_report_path(benchmark_id)
        report.report_path = str(report_path)
        write_json(report_path, report.model_dump(mode="json"))
        append_audit_event(
            self.settings.storage_dir,
            action="quality.benchmark_run",
            project_id=project_id,
            digital_human_id=digital_human_id,
            details={
                "benchmark_id": benchmark_id,
                "status": report.status,
                "scenario_count": len(scenarios),
                "task_count": sum(len(row.task_ids) for row in scenarios),
            },
        )
        return report

    def benchmark_report_path(self, benchmark_id: str) -> Path:
        return ensure_dir(self.settings.storage_dir / "quality" / "benchmarks" / benchmark_id) / "benchmark_report.json"

    def _list_tasks(self) -> list[VideoTask]:
        tasks: list[VideoTask] = []
        for path in sorted(self.store.root.glob("*/task.json")):
            try:
                tasks.append(VideoTask.model_validate(read_json(path)))
            except (ValueError, TypeError, json.JSONDecodeError):
                continue
        return sorted(tasks, key=lambda task: task.updated_at, reverse=True)

    def _resolve_benchmark_profile(
        self, request: RunBenchmarkRequest, benchmark_id: str
    ) -> tuple[str, str, str]:
        digital_store = DigitalHumanStore(self.settings)
        project_store = ProjectStore(self.settings)
        if request.digital_human_id:
            profile = digital_store.get(request.digital_human_id)
            voices = digital_store.list_voice_profiles(profile.digital_human_id)
            voice_profile_id = request.voice_profile_id or profile.voice_profile_id or (voices[0].voice_profile_id if voices else None)
            if not voice_profile_id:
                voice = digital_store.create_voice_profile(
                    profile.digital_human_id,
                    CreateVoiceProfileRequest(name="Benchmark Voice", voice_source_type="synthetic", engine="dryrun"),
                )
                voice_profile_id = voice.voice_profile_id
            return profile.project_id, profile.digital_human_id, voice_profile_id

        project_id = request.project_id or f"quality_benchmark_{benchmark_id}"
        project_store.create(
            CreateProjectRequest(
                project_id=project_id,
                name="Quality Benchmark Project",
                metadata={"benchmark_id": benchmark_id, "source": "quality_center"},
            )
        )
        profile = digital_store.create(
            project_id,
            CreateDigitalHumanRequest(
                name="Quality Benchmark Host",
                avatar_source_type="generated",
                metadata={"benchmark_id": benchmark_id},
            ),
        )
        voice = digital_store.create_voice_profile(
            profile.digital_human_id,
            CreateVoiceProfileRequest(
                name="Quality Benchmark Voice",
                voice_source_type="synthetic",
                engine="dryrun",
                metadata={"benchmark_id": benchmark_id},
            ),
        )
        return project_id, profile.digital_human_id, voice.voice_profile_id

    async def _run_scenario(
        self,
        *,
        benchmark_id: str,
        scenario: str,
        project_id: str,
        digital_human_id: str,
        voice_profile_id: str,
        duration_seconds: int,
        count: int,
        request: RunBenchmarkRequest,
    ) -> BenchmarkScenarioResult:
        started = perf_counter()
        task_ids: list[str] = []
        summaries: list[QualityMetricSummary] = []
        for index in range(count):
            task_request = CreateVideoTaskRequest(
                brand_name="Quality Benchmark Host",
                persona="Synthetic digital human benchmark host",
                topic=f"{scenario} benchmark topic {index + 1}",
                project_id=project_id,
                digital_human_id=digital_human_id,
                voice_profile_id=voice_profile_id,
                platform="douyin",
                duration_seconds=duration_seconds,
                export_jianying_draft=True,
                render_profile=request.render_profile,
                video_template_id=request.video_template_id,
                use_digital_human_pipeline=True,
                script_review_required=False,
                metadata={
                    **request.metadata,
                    "benchmark_id": benchmark_id,
                    "benchmark_scenario": scenario,
                    "benchmark_index": index + 1,
                },
            )
            task = self.store.create(task_request)
            task_ids.append(task.task_id)
            task = await self.pipeline.run(task)
            summaries.append(summarize_task(task, self.store.task_dir(task.task_id), self.settings.storage_dir))
        return BenchmarkScenarioResult(
            scenario=scenario,
            target_duration_seconds=duration_seconds,
            requested_task_count=count,
            completed_count=sum(1 for summary in summaries if summary.status == TaskStatus.completed.value),
            failed_count=sum(1 for summary in summaries if summary.status == TaskStatus.failed.value),
            task_ids=task_ids,
            summaries=summaries,
            render_time_seconds=round(perf_counter() - started, 3),
        )


def summarize_task(task: VideoTask, task_dir: Path, storage_dir: Path) -> QualityMetricSummary:
    reports = _load_reports(task, task_dir)
    report_paths = _report_paths(task, task_dir)
    audio_report = reports.get("audio_quality_report", {})
    render_report = reports.get("render_stability_report", {})
    template_report = reports.get("template_report", {})
    actual_duration = _first_number(
        audio_report.get("duration_seconds"),
        template_report.get("duration_seconds"),
        render_report.get("duration_seconds"),
    )
    if actual_duration is None:
        duration_delta = 0.0
        duration_reason = "actual duration unavailable; dry-run media may be a placeholder"
    else:
        duration_delta = abs(float(task.request.duration_seconds) - actual_duration)
        duration_reason = None
    return QualityMetricSummary(
        task_id=task.task_id,
        status=_value(task.status),
        project_id=task.request.project_id,
        digital_human_id=task.request.digital_human_id,
        topic=task.request.topic,
        platform=_value(task.request.platform),
        requested_duration_seconds=task.request.duration_seconds,
        script_score=_script_score(reports.get("script_quality_report", {})),
        audio_readable=bool(audio_report.get("readable_by_ffprobe") or audio_report.get("readable")),
        video_readable=bool(render_report.get("final_video_readable") or template_report.get("readable")),
        duration_delta_seconds=round(duration_delta, 3),
        duration_delta_reason=duration_reason,
        render_time_seconds=_step_seconds(task),
        fallback_used=_fallback_used(reports),
        failure_reason=_failure_reason(task),
        retry_count=_retry_count(task, storage_dir),
        reports=report_paths,
        artifacts={key: value for key, value in task.artifacts.model_dump().items() if value},
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def build_dashboard(summaries: list[QualityMetricSummary]) -> QualityDashboard:
    fallback_counter: Counter[str] = Counter()
    failure_counter: Counter[str] = Counter()
    for summary in summaries:
        fallback_counter.update(summary.fallback_used)
        if summary.failure_reason:
            failure_counter.update([summary.failure_reason])
    return QualityDashboard(
        task_count=len(summaries),
        completed_count=sum(1 for summary in summaries if summary.status == TaskStatus.completed.value),
        failed_count=sum(1 for summary in summaries if summary.status == TaskStatus.failed.value),
        average_script_score=_average([summary.script_score for summary in summaries]),
        audio_readable_rate=_rate([summary.audio_readable for summary in summaries]),
        video_readable_rate=_rate([summary.video_readable for summary in summaries]),
        average_render_time_seconds=_average([summary.render_time_seconds for summary in summaries]),
        fallback_usage=dict(sorted(fallback_counter.items())),
        failure_reasons=dict(failure_counter.most_common()),
        recent_tasks=summaries[:10],
    )


def _load_reports(task: VideoTask, task_dir: Path) -> dict[str, dict[str, Any]]:
    loaded: dict[str, dict[str, Any]] = {}
    for name, path in _report_paths(task, task_dir).items():
        try:
            loaded[name] = read_json(Path(path))
        except (FileNotFoundError, ValueError, TypeError, json.JSONDecodeError):
            loaded[name] = {}
    return loaded


def _report_paths(task: VideoTask, task_dir: Path) -> dict[str, str]:
    paths: dict[str, str] = {}
    artifact_values = task.artifacts.model_dump()
    for filename in REPORT_NAMES:
        key = filename.removesuffix(".json")
        path = Path(artifact_values.get(key) or task_dir / filename)
        if path.exists() and path.is_file():
            paths[key] = str(path)
    return paths


def _script_score(report: dict[str, Any]) -> float:
    if not report:
        return 0.0
    explicit = _first_number(report.get("score"), report.get("script_score"))
    if explicit is not None:
        return max(0.0, min(100.0, explicit))
    score = 100.0
    if report.get("readable") is False:
        score -= 40.0
    score -= 10.0 * len(report.get("warnings") or [])
    score -= 5.0 * len(report.get("suggestions") or [])
    if report.get("status") not in {None, "completed", "ok"}:
        score -= 20.0
    return max(0.0, min(100.0, score))


def _fallback_used(reports: dict[str, dict[str, Any]]) -> list[str]:
    seen: list[str] = []
    for key in ["avatar_render_report", "lip_sync_report", "render_stability_report"]:
        value = reports.get(key, {}).get("fallback_used")
        if isinstance(value, list):
            for item in value:
                if str(item) not in seen:
                    seen.append(str(item))
    return seen


def _failure_reason(task: VideoTask) -> str | None:
    if task.error:
        return task.error
    for step in task.steps:
        if step.status == "failed":
            return step.message or step.name
    return None


def _retry_count(task: VideoTask, storage_dir: Path) -> int:
    audit_path = storage_dir / "tasks" / task.task_id / "audit_events.jsonl"
    if not audit_path.exists():
        return 0
    count = 0
    with audit_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("action") == "render.retry_requested":
                count += 1
    return count


def _step_seconds(task: VideoTask) -> float:
    total = 0.0
    for step in task.steps:
        if step.finished_at is None:
            continue
        total += max(0.0, (step.finished_at - step.started_at).total_seconds())
    return round(total, 3)


def _first_number(*values: Any) -> float | None:
    for value in values:
        if isinstance(value, (int, float)):
            return float(value)
    return None


def _average(values: list[float]) -> float:
    return round(sum(values) / len(values), 3) if values else 0.0


def _rate(values: list[bool]) -> float:
    return round(sum(1 for value in values if value) / len(values), 3) if values else 0.0


def _value(value: Any) -> Any:
    return getattr(value, "value", value)
