from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, HttpUrl


class Platform(str, Enum):
    douyin = "douyin"
    xiaohongshu = "xiaohongshu"
    kuaishou = "kuaishou"
    shipinhao = "shipinhao"
    wechat_channels = "wechat_channels"
    tiktok = "tiktok"
    youtube_shorts = "youtube_shorts"


class AvatarMode(str, Enum):
    none = "none"
    offline = "offline"
    realtime = "realtime"


class LipSyncEngine(str, Enum):
    none = "none"
    musetalk = "musetalk"
    latentsync = "latentsync"
    syncso = "syncso"
    wav2lip = "wav2lip"
    yywav2lip = "yywav2lip"


class RenderProfileName(str, Enum):
    preview = "preview"
    standard = "standard"
    final = "final"
    batch = "batch"
    compat = "compat"


class VoiceSourceType(str, Enum):
    synthetic = "synthetic"
    uploaded_sample = "uploaded_sample"
    preset_voice = "preset_voice"
    cloud_voice = "cloud_voice"
    cloud_clone = "cloud_clone"
    source_video_audio = "source_video_audio"


class AvatarSourceType(str, Enum):
    generated = "generated"
    uploaded_reference = "uploaded_reference"
    preset_avatar = "preset_avatar"


class RoleModelEngineType(str, Enum):
    wav2lip = "wav2lip"
    yywav2lip = "yywav2lip"
    duix = "duix"
    liveportrait = "liveportrait"


class RoleModelStatus(str, Enum):
    pending = "pending"
    ready = "ready"
    failed = "failed"


class ReferenceVideoStatus(str, Enum):
    created = "created"
    analyzed = "analyzed"
    failed = "failed"


class ScriptRewriteStatus(str, Enum):
    generated = "generated"
    failed = "failed"


class CampaignStatus(str, Enum):
    created = "created"
    running = "running"
    completed = "completed"
    partial_failed = "partial_failed"
    failed = "failed"


class CampaignItemStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class CampaignSourceType(str, Enum):
    topic = "topic"
    rewritten_script = "rewritten_script"
    csv = "csv"


class PublishStatus(str, Enum):
    draft = "draft"
    ready = "ready"
    scheduled = "scheduled"
    published = "published"
    failed = "failed"


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class JobKind(str, Enum):
    render_task = "render_task"
    campaign_run = "campaign_run"


class FeedbackCategory(str, Enum):
    trial = "trial"
    usability = "usability"
    output_quality = "output_quality"
    performance = "performance"
    bug = "bug"
    feature_request = "feature_request"
    other = "other"


class VideoTemplateResolution(BaseModel):
    width: int = 1080
    height: int = 1920


class VideoTemplate(BaseModel):
    template_id: str
    name: str
    description: str = ""
    resolution: dict[str, int] = Field(default_factory=lambda: {"width": 1080, "height": 1920})
    subtitle_style: dict[str, Any] = Field(default_factory=dict)
    title_style: dict[str, Any] = Field(default_factory=dict)
    bgm: dict[str, Any] = Field(default_factory=dict)
    intro: dict[str, Any] = Field(default_factory=dict)
    outro: dict[str, Any] = Field(default_factory=dict)
    safe_area: dict[str, Any] = Field(default_factory=dict)
    cover_text: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskStatus(str, Enum):
    created = "created"
    running = "running"
    waiting_for_review = "waiting_for_review"
    completed = "completed"
    failed = "failed"


class CreateVideoTaskRequest(BaseModel):
    # brand_name/persona keep the legacy contract alive. Digital-human task APIs fill them in.
    brand_name: str = Field("Synthetic IP", min_length=1)
    persona: str = Field("Synthetic digital human host", min_length=1)
    topic: str = Field(..., min_length=1)
    project_id: str | None = None
    digital_human_id: str | None = None
    voice_profile_id: str | None = None
    role_model_id: str | None = None
    platform: Platform = Platform.douyin
    duration_seconds: int = Field(45, ge=10, le=180)
    reference_video_url: HttpUrl | None = None
    fixed_script: str | None = None
    avatar_mode: AvatarMode = AvatarMode.offline
    lip_sync_engine: LipSyncEngine = LipSyncEngine.latentsync
    export_jianying_draft: bool = True
    render_profile: RenderProfileName = RenderProfileName.preview
    retry_from: str | None = None
    force_render: bool = False
    avatar_engine_preference: str | None = None
    lip_sync_engine_preference: str | None = None
    video_template_id: str = "clean_talking_head"
    use_project_context: bool = True
    use_digital_human_pipeline: bool = False
    script_review_required: bool = False
    strict_jianying: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArtifactSet(BaseModel):
    project_context: str | None = None
    digital_human_profile: str | None = None
    avatar_image: str | None = None
    script_json: str | None = None
    subtitles_srt: str | None = None
    script_quality_report: str | None = None
    voice_audio: str | None = None
    voice_segments: str | None = None
    voice_metadata: str | None = None
    audio_quality_report: str | None = None
    avatar_base_video: str | None = None
    avatar_render_metadata: str | None = None
    avatar_render_report: str | None = None
    avatar_video: str | None = None
    lip_synced_video: str | None = None
    lip_sync_report: str | None = None
    final_video: str | None = None
    cover_image: str | None = None
    template_report: str | None = None
    render_job: str | None = None
    render_stability_report: str | None = None
    digital_human_quality_report: str | None = None
    jianying_draft: str | None = None
    publish_package: str | None = None
    artifact_manifest: str | None = None
    logs: str | None = None


class StepResult(BaseModel):
    name: str
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    message: str | None = None
    artifacts: dict[str, str] = Field(default_factory=dict)


class VideoTask(BaseModel):
    task_id: str = Field(default_factory=lambda: uuid4().hex)
    status: TaskStatus = TaskStatus.created
    request: CreateVideoTaskRequest
    artifacts: ArtifactSet = Field(default_factory=ArtifactSet)
    steps: list[StepResult] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    error: str | None = None

    @property
    def task_dir(self) -> Path:
        return Path("storage") / "tasks" / self.task_id


class TaskResponse(BaseModel):
    task_id: str
    status: TaskStatus
    artifacts: ArtifactSet
    error: str | None = None


class AvatarStyleCard(BaseModel):
    style: str = "studio"
    prompt: str = "synthetic IP digital human avatar"
    negative_prompt: str = "real person, copyrighted character, watermark"
    seed: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DigitalHumanProfile(BaseModel):
    digital_human_id: str = Field(default_factory=lambda: "dh_" + uuid4().hex)
    project_id: str
    name: str
    avatar_source_type: AvatarSourceType = AvatarSourceType.generated
    avatar_style: AvatarStyleCard = Field(default_factory=AvatarStyleCard)
    selected_avatar_asset: str | None = None
    voice_profile_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class VoiceProfile(BaseModel):
    voice_profile_id: str = Field(default_factory=lambda: "voice_" + uuid4().hex)
    digital_human_id: str
    project_id: str
    name: str
    voice_source_type: VoiceSourceType = VoiceSourceType.synthetic
    engine: str = "dryrun"
    sample_asset_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CloudProviderType(str, Enum):
    voice = "voice"
    video = "video"


class CloudProviderConfig(BaseModel):
    provider_id: str
    provider_type: CloudProviderType
    api_key_env_name: str = ""
    base_url: str = ""
    model: str = ""
    enabled: bool = False
    required: bool = False
    cost_estimate: str = ""
    status: str = "disabled"
    missing_items: list[str] = Field(default_factory=list)
    message: str = ""


class CloudCostEstimate(BaseModel):
    voice_clone_setup_cost: float = 0.0
    voice_synthesis_cost: float = 0.0
    video_render_cost: float = 0.0
    estimated_monthly_total: float = 0.0
    currency: str = "USD"
    warnings: list[str] = Field(default_factory=list)
    inputs: dict[str, Any] = Field(default_factory=dict)


class DigitalHumanRoleModel(BaseModel):
    role_model_id: str = Field(default_factory=lambda: "role_" + uuid4().hex)
    digital_human_id: str
    project_id: str
    source_video_asset_id: str | None = None
    idle_video_asset_id: str | None = None
    action_video_asset_id: str | None = None
    pkl_model_path: str | None = None
    engine_type: RoleModelEngineType = RoleModelEngineType.yywav2lip
    status: RoleModelStatus = RoleModelStatus.pending
    validation_report: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ReferenceVideo(BaseModel):
    reference_id: str = Field(default_factory=lambda: "ref_" + uuid4().hex)
    project_id: str
    title: str = "Reference video"
    asset_id: str | None = None
    original_source_path: str | None = None
    stored_video_path: str
    status: ReferenceVideoStatus = ReferenceVideoStatus.created
    extracted_audio_path: str | None = None
    transcript_json: str | None = None
    reference_script_json: str | None = None
    shot_breakdown_json: str | None = None
    style_summary_json: str | None = None
    analysis_report: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ScriptTemplate(BaseModel):
    template_id: str = Field(default_factory=lambda: "tpl_" + uuid4().hex)
    reference_id: str
    project_id: str
    name: str = "Reference-derived script template"
    platform: Platform = Platform.douyin
    tone: str = "practical"
    hook_pattern: str = "question hook"
    body_structure: list[str] = Field(default_factory=list)
    cta_pattern: str = "clear action"
    source_summary: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RewriteScriptRequest(BaseModel):
    reference_id: str
    project_id: str
    product_info: dict[str, Any] = Field(default_factory=dict)
    count: int = Field(3, ge=1, le=20)
    platform: Platform = Platform.douyin
    tone: str = "practical"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScriptRewrite(BaseModel):
    rewrite_id: str = Field(default_factory=lambda: "rewrite_" + uuid4().hex)
    reference_id: str
    project_id: str
    request: RewriteScriptRequest
    template: ScriptTemplate
    status: ScriptRewriteStatus = ScriptRewriteStatus.generated
    rewritten_scripts_json: str
    script_scores_json: str
    rewrite_report_json: str
    scripts: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CampaignItem(BaseModel):
    item_id: str = Field(default_factory=lambda: "camp_item_" + uuid4().hex)
    source_type: CampaignSourceType = CampaignSourceType.topic
    topic: str
    fixed_script: str | None = None
    source_script_id: str | None = None
    task_id: str | None = None
    status: CampaignItemStatus = CampaignItemStatus.pending
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Campaign(BaseModel):
    campaign_id: str = Field(default_factory=lambda: "camp_" + uuid4().hex)
    project_id: str
    name: str
    digital_human_id: str
    voice_profile_id: str
    role_model_id: str | None = None
    platform: Platform = Platform.douyin
    duration_seconds: int = Field(45, ge=10, le=180)
    render_profile: RenderProfileName = RenderProfileName.batch
    video_template_id: str = "clean_talking_head"
    export_jianying_draft: bool = True
    script_review_required: bool = False
    status: CampaignStatus = CampaignStatus.created
    items: list[CampaignItem] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CreateCampaignRequest(BaseModel):
    name: str = Field("Batch campaign", min_length=1)
    digital_human_id: str
    voice_profile_id: str
    role_model_id: str | None = None
    topics: list[str] = Field(default_factory=list)
    rewritten_scripts: list[dict[str, Any]] = Field(default_factory=list)
    rewrite_id: str | None = None
    csv_text: str | None = None
    platform: Platform = Platform.douyin
    duration_seconds: int = Field(45, ge=10, le=180)
    render_profile: RenderProfileName = RenderProfileName.batch
    video_template_id: str = "clean_talking_head"
    export_jianying_draft: bool = True
    script_review_required: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class CampaignRunRequest(BaseModel):
    retry_failed: bool = False
    force: bool = False


class PlatformPublishPackage(BaseModel):
    platform: str
    title: str
    description: str
    hashtags: list[str] = Field(default_factory=list)
    cover_text: str
    publish_checklist: list[str] = Field(default_factory=list)
    platform_fields: dict[str, Any] = Field(default_factory=dict)


class PublishQueueItem(BaseModel):
    queue_id: str = Field(default_factory=lambda: "pub_" + uuid4().hex)
    task_id: str
    project_id: str | None = None
    digital_human_id: str | None = None
    platform: str = "douyin"
    status: PublishStatus = PublishStatus.draft
    scheduled_at: str | None = None
    reviewed_at: str | None = None
    reviewer_note: str | None = None
    external_url: str | None = None
    failure_reason: str | None = None
    platform_package: PlatformPublishPackage
    handoff_policy: str = "manual_only_no_auto_login"
    artifacts: dict[str, str | None] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CreatePublishQueueItemRequest(BaseModel):
    platform: str = "douyin"
    status: PublishStatus | None = None
    scheduled_at: str | None = None
    reviewer_note: str | None = None
    title: str | None = None
    description: str | None = None
    hashtags: list[str] | None = None
    cover_text: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PatchPublishQueueItemRequest(BaseModel):
    status: PublishStatus | None = None
    scheduled_at: str | None = None
    reviewer_note: str | None = None
    external_url: str | None = None
    failure_reason: str | None = None
    metadata: dict[str, Any] | None = None


class EnqueueJobRequest(BaseModel):
    max_retries: int = Field(0, ge=0, le=10)
    retry_failed: bool = False
    force: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class JobRecord(BaseModel):
    job_id: str = Field(default_factory=lambda: "job_" + uuid4().hex)
    kind: JobKind
    status: JobStatus = JobStatus.queued
    payload: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    attempt: int = 1
    max_retries: int = 0
    parent_job_id: str | None = None
    logs_path: str | None = None
    worker: str = "local"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    finished_at: datetime | None = None


class FeedbackRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    category: FeedbackCategory = FeedbackCategory.trial
    message: str = Field(..., min_length=1, max_length=4000)
    contact: str | None = None


class FeedbackRecord(FeedbackRequest):
    feedback_id: str = Field(default_factory=lambda: "fb_" + uuid4().hex)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class QualityMetricSummary(BaseModel):
    task_id: str
    status: str
    project_id: str | None = None
    digital_human_id: str | None = None
    topic: str | None = None
    platform: str | None = None
    requested_duration_seconds: int | None = None
    script_score: float = 0.0
    audio_readable: bool = False
    video_readable: bool = False
    duration_delta_seconds: float = 0.0
    duration_delta_reason: str | None = None
    render_time_seconds: float = 0.0
    fallback_used: list[str] = Field(default_factory=list)
    failure_reason: str | None = None
    retry_count: int = 0
    reports: dict[str, str] = Field(default_factory=dict)
    artifacts: dict[str, str | None] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class QualityDashboard(BaseModel):
    task_count: int = 0
    completed_count: int = 0
    failed_count: int = 0
    average_script_score: float = 0.0
    audio_readable_rate: float = 0.0
    video_readable_rate: float = 0.0
    average_render_time_seconds: float = 0.0
    fallback_usage: dict[str, int] = Field(default_factory=dict)
    failure_reasons: dict[str, int] = Field(default_factory=dict)
    recent_tasks: list[QualityMetricSummary] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RunBenchmarkRequest(BaseModel):
    project_id: str | None = None
    digital_human_id: str | None = None
    voice_profile_id: str | None = None
    render_profile: RenderProfileName = RenderProfileName.preview
    video_template_id: str = "clean_talking_head"
    metadata: dict[str, Any] = Field(default_factory=dict)


class BenchmarkScenarioResult(BaseModel):
    scenario: str
    target_duration_seconds: int | None = None
    requested_task_count: int = 0
    completed_count: int = 0
    failed_count: int = 0
    task_ids: list[str] = Field(default_factory=list)
    summaries: list[QualityMetricSummary] = Field(default_factory=list)
    render_time_seconds: float = 0.0


class BenchmarkReport(BaseModel):
    benchmark_id: str = Field(default_factory=lambda: "bench_" + uuid4().hex)
    status: str = "completed"
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    scenarios: list[BenchmarkScenarioResult] = Field(default_factory=list)
    dashboard: QualityDashboard = Field(default_factory=QualityDashboard)
    report_path: str | None = None
    download_url: str | None = None


class CreateDigitalHumanRequest(BaseModel):
    name: str = Field(..., min_length=1)
    avatar_source_type: AvatarSourceType = AvatarSourceType.generated
    avatar_style: AvatarStyleCard = Field(default_factory=AvatarStyleCard)
    selected_avatar_asset: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreateProjectRequest(BaseModel):
    project_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectImportRequest(BaseModel):
    package_path: str = Field(..., min_length=1)
    project_id: str | None = None


class PatchDigitalHumanRequest(BaseModel):
    name: str | None = None
    avatar_source_type: AvatarSourceType | None = None
    avatar_style: AvatarStyleCard | None = None
    selected_avatar_asset: str | None = None
    voice_profile_id: str | None = None
    metadata: dict[str, Any] | None = None


class CreateVoiceProfileRequest(BaseModel):
    name: str = Field(..., min_length=1)
    voice_source_type: VoiceSourceType = VoiceSourceType.synthetic
    engine: str = "dryrun"
    sample_asset_id: str | None = None
    sample_audio_filename: str | None = None
    sample_audio_content_type: str | None = None
    sample_audio_base64: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreateRoleModelRequest(BaseModel):
    source_video_asset_id: str | None = None
    idle_video_asset_id: str | None = None
    action_video_asset_id: str | None = None
    pkl_model_path: str | None = None
    engine_type: RoleModelEngineType = RoleModelEngineType.yywav2lip
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreateReferenceVideoRequest(BaseModel):
    title: str = Field("Reference video", min_length=1)
    asset_id: str | None = None
    source_path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CollectReferenceLinkRequest(BaseModel):
    url: str = Field(..., min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReferenceContentCapture(BaseModel):
    collection_id: str = Field(default_factory=lambda: "refcol_" + uuid4().hex)
    project_id: str
    source_url: str
    final_url: str | None = None
    platform: str = "generic_web"
    status: str = "captured"
    title: str = ""
    description: str = ""
    cover_url: str = ""
    video_url: str = ""
    content_text: str = ""
    script_seed: str = ""
    downloadable: bool = False
    message: str = ""
    recommended_next_action: str = ""
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    collection_json: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TranscribeReferenceLinkRequest(BaseModel):
    url: str = Field(..., min_length=1)
    asr_engine: str | None = "funasr"
    force: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReferenceDownloadWatchStartRequest(BaseModel):
    url: str = ""
    platform: str = "douyin"
    download_dir: str | None = None
    asr_engine: str | None = "funasr"
    force: bool = False
    timeout_seconds: int = Field(600, ge=30, le=3600)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReferenceLinkTranscriptionResult(BaseModel):
    status: str = "blocked"
    message: str = ""
    platform: str = "generic_web"
    source_url: str = ""
    final_url: str | None = None
    collection_id: str | None = None
    reference_id: str | None = None
    stored_video_path: str | None = None
    transcript_text: str = ""
    reference_script_text: str = ""
    recommended_next_action: str = ""
    collection: ReferenceContentCapture | None = None
    analysis: dict[str, Any] = Field(default_factory=dict)


class ReferenceDownloadWatchStatus(BaseModel):
    watch_id: str
    status: str = "watching"
    message: str = ""
    platform: str = "douyin"
    source_url: str = ""
    download_dir: str = ""
    candidate_path: str = ""
    candidate_size: int | None = None
    result: ReferenceLinkTranscriptionResult | None = None


class AnalyzeReferenceVideoRequest(BaseModel):
    asr_engine: str | None = None
    force: bool = False


class DigitalHumanTaskRequest(BaseModel):
    digital_human_id: str
    voice_profile_id: str
    role_model_id: str | None = None
    topic: str = Field(..., min_length=1)
    fixed_script: str | None = None
    platform: Platform = Platform.douyin
    duration_seconds: int = Field(45, ge=10, le=180)
    render_profile: RenderProfileName = RenderProfileName.preview
    script_review_required: bool = False
    export_jianying_draft: bool = True
    use_project_context: bool = True
    force_render: bool = False
    avatar_engine_preference: str | None = None
    lip_sync_engine_preference: str | None = None
    video_template_id: str = "clean_talking_head"
    metadata: dict[str, Any] = Field(default_factory=dict)


class DigitalHumanTaskResponse(BaseModel):
    task_id: str
    plan: list[str]
    initial_status: TaskStatus


class ReviewApprovalRequest(BaseModel):
    reviewer_id: str = "system"
    review_note: str | None = None


class RenderRetryRequest(BaseModel):
    retry_from: str = "lip_sync"
    force_render: bool = True


class AvatarGenerationRequest(BaseModel):
    prompt: str = "synthetic IP digital human avatar"
    negative_prompt: str = "real person, watermark, copyrighted character"
    style: str = "studio"
    seed: int | None = None
    count: int = Field(2, ge=1, le=4)


class AvatarSelectRequest(BaseModel):
    asset_id: str


class VoiceTestRequest(BaseModel):
    text: str = Field("This is a voice test.", min_length=1)
    language: str = "zh-CN"
    voice_style: str = "natural"
    speech_rate: float = Field(1.0, ge=0.5, le=2.0)
    confirm_paid_call: bool = False
    allow_sample_fallback: bool = False


class SourceVideoUploadRequest(BaseModel):
    filename: str = "source_video.mp4"
    content_type: str = "video/mp4"
    content_base64: str


class VideoRemixAssetUpload(BaseModel):
    filename: str = "remix_asset"
    content_type: str = "application/octet-stream"
    content_base64: str


class VideoRemixSubtitleStyle(BaseModel):
    font_size: int = Field(58, ge=20, le=96)
    color: str = Field("#ffffff", pattern=r"^#[0-9a-fA-F]{6}$")
    x: float = Field(0.5, ge=0.0, le=1.0)
    y: float = Field(0.68, ge=0.0, le=1.0)


class VideoRemixTaskRequest(BaseModel):
    project_id: str = "project_demo"
    main_video_path: str | None = None
    main_video: VideoRemixAssetUpload | None = None
    assets: list[VideoRemixAssetUpload] = Field(default_factory=list, max_length=30)
    output_count: int = Field(1, ge=1, le=5)
    add_subtitles: bool = False
    use_smart_subtitles: bool = True
    subtitle_text: str | None = Field(None, max_length=2000)
    subtitle_style: VideoRemixSubtitleStyle = Field(default_factory=VideoRemixSubtitleStyle)
    add_background_music: bool = False
    background_music_id: str | None = Field(None, max_length=80)
    background_music_volume: float = Field(0.18, ge=0.0, le=1.0)


class VideoRemixTaskResponse(BaseModel):
    remix_task_id: str
    status: str
    message: str
    task_dir: str
    main_video_path: str
    asset_count: int
    output_count: int
    outputs: list[str] = Field(default_factory=list)
    output_urls: list[str] = Field(default_factory=list)
    report_path: str | None = None
    add_subtitles: bool = False
    use_smart_subtitles: bool = True
    subtitle_text: str | None = None
    subtitle_style: VideoRemixSubtitleStyle = Field(default_factory=VideoRemixSubtitleStyle)
    add_background_music: bool = False
    background_music_id: str | None = None
    background_music_title: str | None = None
    background_music_volume: float = 0.18


class CoverGenerateRequest(BaseModel):
    project_id: str = "project_demo"
    task_id: str | None = None
    video_path: str | None = None
    video: VideoRemixAssetUpload | None = None
    template_id: str = "yellow_title_top"
    keyword_text: str = Field("数字人口播", max_length=80)


class CoverGenerateResponse(BaseModel):
    status: str
    message: str
    template_id: str
    template_name: str
    keyword_text: str
    cover_path: str
    cover_url: str
    report_path: str
    report_url: str


class SourceVideoVoiceProfileRequest(BaseModel):
    name: str = Field("源视频克隆音色", min_length=1)
    confirm_paid_call: bool = False
    provider: str = "aliyun_bailian_cosyvoice"
    source_audio_url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CloudSourceVideoRenderRequest(BaseModel):
    render_quality: str = "preview"
    confirm_paid_call: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class HiflySourceVideoAvatarRequest(BaseModel):
    title: str = Field("飞影源视频数字人", min_length=1)
    video_url: str | None = None
    confirm_paid_call: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class HiflySourceVideoVoiceRequest(BaseModel):
    title: str = Field("飞影克隆声音", min_length=1)
    audio_url: str | None = None
    voice_type: str = "clone"
    confirm_paid_call: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class HiflySourceVideoGenerateRequest(BaseModel):
    title: str = Field("飞影数字人视频", min_length=1)
    text: str = Field(..., min_length=1)
    voice_profile_id: str | None = None
    video_url: str | None = None
    audio_url: str | None = None
    voice_type: str = "clone"
    aigc_flag: int = Field(2, ge=0, le=2)
    confirm_paid_call: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
