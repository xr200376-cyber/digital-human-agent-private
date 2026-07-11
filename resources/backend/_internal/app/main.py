import base64
import html
import json
import mimetypes
import posixpath
import re
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel

from app.artifacts import artifact_items, build_artifacts_zip, write_artifact_manifest
from app.audit import append_audit_event
from app.adapters.base import AdapterError
from app.adapters.cloud_voice import AliyunBailianVoiceAdapter
from app.adapters.object_storage import build_object_storage_adapter
from app.adapters.wav2lip import Wav2LipAdapter
from app.adapters.yy_wav2lip import YYWav2LipAdapter
from app.adapters.cloud_lipsync import PixVerseLipSyncAdapter, SyncSoLipSyncAdapter
from app.adapters.baidu_xiling import BaiduXilingVideoAdapter
from app.adapters.hifly import HiflyDigitalHumanAdapter
from app.adapters.omnihuman import OmniHumanVideoAdapter
from app.adapters.publish_browser import PublishBrowserAutomation, PublishBrowserAutomationError
from app.adapters.tavus import TavusVideoAdapter
from app.adapters.video_parser import LocalVideoParserAdapter, VideoParserResult
from app.cloud_providers import build_cloud_provider_configs, estimate_cloud_cost
from app.commercial_client import CommercialLicenseClient, CommercialLicenseError, CommercialLicenseHttpError
from app.commercial_center import router as commercial_router
from app.cover_templates import (
    CoverGenerationError,
    generate_cover_from_video,
    get_cover_template,
    list_cover_templates,
)
from app.campaigns import CampaignStore
from app.digital_human_pipeline import DIGITAL_HUMAN_PLAN, _select_tts_adapter
from app.digital_humans import DigitalHumanStore
from app.desktop_settings import (
    DesktopSettingsConfig,
    DesktopSettingsStore,
    SECRET_DESKTOP_SETTING_KEYS,
    alignment_report,
    validate_desktop_settings,
)
from app.feedback import FeedbackStore
from app.job_queue import LocalJobQueue
from app.llm_platforms import (
    LLMPlatformConfigDocument,
    LLMPlatformStore,
    LocalLLMModel,
)
from app.model_center import (
    ModelPresetRequest,
    ModelSelectionRequest,
    apply_model_preset,
    apply_model_selection,
    current_model_selection,
    model_catalog,
    validate_model_selection,
)
from app.object_storage import LocalObjectStorage, S3ObjectStorage
from app.pipeline import VideoPipeline
from app.project_packages import import_project_package, export_project_package
from app.publish_console import PublishConsoleStore
from app.quality_center import QualityCenter
from app.reference_videos import ReferenceVideoStore
from app.reference_collector import ReferenceContentCollector
from app.reference_download_watch import ReferenceDownloadWatchService
from app.reference_link_transcription import ReferenceLinkTranscriptionService
from app.repositories import FileRepositoryBundle, PostgresRepositoryBundle
from app.script_rewrites import ScriptRewriteStore
from app.script_generation import select_script_generator_adapter
from app.schemas import (
    AnalyzeReferenceVideoRequest,
    BenchmarkReport,
    Campaign,
    CampaignRunRequest,
    CoverGenerateRequest,
    CoverGenerateResponse,
    CreateDigitalHumanRequest,
    CreateCampaignRequest,
    CreatePublishQueueItemRequest,
    CreateProjectRequest,
    CreateReferenceVideoRequest,
    CreateVideoTaskRequest,
    CreateVoiceProfileRequest,
    DigitalHumanProfile,
    DigitalHumanTaskRequest,
    DigitalHumanTaskResponse,
    EnqueueJobRequest,
    FeedbackRecord,
    FeedbackRequest,
    AvatarGenerationRequest,
    AvatarSelectRequest,
    CloudSourceVideoRenderRequest,
    CollectReferenceLinkRequest,
    HiflySourceVideoAvatarRequest,
    HiflySourceVideoGenerateRequest,
    HiflySourceVideoVoiceRequest,
    AvatarSourceType,
    JobKind,
    JobRecord,
    JobStatus,
    PatchDigitalHumanRequest,
    PatchPublishQueueItemRequest,
    CreateRoleModelRequest,
    DigitalHumanRoleModel,
    ReferenceVideo,
    ReferenceContentCapture,
    ReferenceDownloadWatchStartRequest,
    ReferenceDownloadWatchStatus,
    ReferenceLinkTranscriptionResult,
    RenderRetryRequest,
    ReviewApprovalRequest,
    RewriteScriptRequest,
    ScriptRewrite,
    PublishQueueItem,
    PublishStatus,
    ProjectImportRequest,
    QualityDashboard,
    QualityMetricSummary,
    TaskStatus,
    TaskResponse,
    RunBenchmarkRequest,
    SourceVideoUploadRequest,
    SourceVideoVoiceProfileRequest,
    TranscribeReferenceLinkRequest,
    VideoRemixAssetUpload,
    VideoRemixTaskRequest,
    VideoRemixTaskResponse,
    VoiceSourceType,
    VoiceProfile,
    VoiceTestRequest,
)
from app.settings import Settings, get_settings
from app.settings_autodetect import SettingsAutoDetectResult, run_settings_autodetect
from app.settings_presets import get_settings_preset
from app.source_video_workflow import SourceVideoWorkflow, SourceVideoWorkflowError
from app.store import TaskStore
from app.subtitle_alignment import align_video_subtitles
from app.projects import ProjectStore
from app.utils.files import ensure_dir, read_json, write_json, write_placeholder_binary
from app.video_remix import LocalFFmpegVideoRemixEngine, VideoRemixError
from app.video_templates import get_video_template, list_video_templates

app = FastAPI(title="数字人智能体 API", version="0.1.0", docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(commercial_router)
STATIC_DIR = Path(__file__).resolve().parent / "static"
DEFAULT_PRESET_VOICE_SOURCE_DIR = Path("D:/Backup/xwechat_files/wxid_rm27hl739b7222_616c/msg/file/2026-06")
DEFAULT_PRESET_VOICE_ASSETS = (
    {"preset_id": "news_female", "name": "新闻女声", "filename": "新闻女声(1).mp3"},
    {"preset_id": "magnetic_male", "name": "磁性男声", "filename": "磁性男声(1).mp3"},
    {"preset_id": "gentle_female", "name": "温柔女声", "filename": "温柔女声.mp3"},
    {"preset_id": "professional_female_narrator", "name": "专业解说女", "filename": "专业解说女.mp3"},
    {"preset_id": "lively_male_narrator", "name": "生动解说男", "filename": "生动解说男.mp3"},
)
SENSITIVE_ERROR_KEYS = {"apikey", "api_key", "token", "secret", "password", "authorization"}
PUBLISH_BROWSER_AUTOMATION = PublishBrowserAutomation()


def _redact_sensitive_values(value: object) -> object:
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text.lower() in SENSITIVE_ERROR_KEYS:
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = _redact_sensitive_values(item)
        return redacted
    if isinstance(value, list):
        return [_redact_sensitive_values(item) for item in value]
    return value


def _redact_sensitive_text(value: object, *, limit: int = 1200) -> str:
    text = str(value)
    text = re.sub(r"https?://\S+", "[已隐藏链接]", text)
    text = re.sub(
        r"(?i)(api[_-]?key|token|secret|authorization|password)\s*[:=]\s*[^,\s}\]]+",
        r"\1=[已隐藏]",
        text,
    )
    if len(text) > limit:
        return text[:limit] + "..."
    return text


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=jsonable_encoder({"detail": _redact_sensitive_values(exc.errors())}),
    )


class ApplySimpleSettingsPresetRequest(BaseModel):
    preset_id: str
    auto_detect: bool = True


class PersonalDigitalHumanUploadRequest(BaseModel):
    name: str = "客户个人数字人"
    source_type: str = "uploaded_reference"
    filename: str = "personal_avatar.png"
    content_type: str = "image/png"
    content_base64: str
    tavus_replica_id: str = ""


class LLMSelectionRequest(BaseModel):
    platformId: str
    modelId: str


class DesktopLicenseActivateRequest(BaseModel):
    license_key: str
    app_version: str = ""
    device_name: str = ""


class InlineSourceVideoScriptRequest(BaseModel):
    topic: str
    project_id: str | None = None
    platform: str = "douyin"
    duration_seconds: int | None = None
    target_char_count: int | None = None
    style: str = "口播成交型"
    language: str = "zh-CN"
    current_script: str = ""
    mode: str = "generate"
    confirm_paid_call: bool = False


class InlineSourceVideoScriptResponse(BaseModel):
    status: str
    script_text: str
    script_json: dict[str, object]
    engine: str
    model: str | None = None
    fallback_used: bool = False


class InlineSourceVideoTagRequest(BaseModel):
    topic: str
    script_text: str
    project_id: str | None = None
    platform: str = "douyin"
    language: str = "zh-CN"
    confirm_paid_call: bool = False


class InlineSourceVideoTagResponse(BaseModel):
    status: str
    title: str
    tags: list[str]
    keywords: list[str]
    engine: str
    model: str | None = None
    fallback_used: bool = False


def get_store(settings: Settings = Depends(get_settings)) -> TaskStore:
    return TaskStore(settings)


def get_pipeline(settings: Settings = Depends(get_settings), store: TaskStore = Depends(get_store)) -> VideoPipeline:
    return VideoPipeline(settings, store)


def get_job_queue(settings: Settings = Depends(get_settings)) -> LocalJobQueue:
    return LocalJobQueue(settings)


def get_feedback_store(settings: Settings = Depends(get_settings)) -> FeedbackStore:
    return FeedbackStore(settings)


def get_quality_center(
    settings: Settings = Depends(get_settings),
    store: TaskStore = Depends(get_store),
    pipeline: VideoPipeline = Depends(get_pipeline),
) -> QualityCenter:
    return QualityCenter(settings, store, pipeline)


def get_digital_human_store(settings: Settings = Depends(get_settings)) -> DigitalHumanStore:
    return DigitalHumanStore(settings)


def get_project_store(settings: Settings = Depends(get_settings)) -> ProjectStore:
    return ProjectStore(settings)


def get_desktop_license_client(settings: Settings = Depends(get_settings)) -> CommercialLicenseClient:
    return CommercialLicenseClient(
        storage_dir=settings.storage_dir,
        api_base_url=settings.commercial_api_base_url,
        offline_grace_seconds=settings.commercial_offline_grace_seconds,
    )


def _claim_commercial_usage_or_raise(
    settings: Settings,
    license_client: CommercialLicenseClient,
    *,
    usage_seconds: int,
    feature: str,
    context: dict[str, object] | None = None,
) -> dict[str, object]:
    if not settings.commercial_license_required:
        return {"ok": True, "allowed": True, "skipped": True}
    seconds = max(int(usage_seconds or 0), 1)
    try:
        reserve = license_client.reserve_credits(
            seconds=seconds,
            provider=str((context or {}).get("provider") or feature.split(":", 1)[0] or "hifly"),
            feature=feature,
            context=context or {},
        )
        response = license_client.commit_credits(
            reservation_id=str(reserve.get("reservation_id") or ""),
            actual_seconds=seconds,
            context={"source": "desktop_cloud_call", **(context or {})},
        )
    except CommercialLicenseHttpError as exc:
        messages = {
            "license_usage_limit_reached": "体验时长已用完，请购买正式版后继续使用。",
            "license_usage_limit_insufficient": "本次生成超过剩余体验时长，请购买正式版后继续使用。",
            "license_credit_insufficient": "可用积分不足，请充值或购买正式版后继续使用。",
            "activation_token_invalid": "授权已失效，请重新激活。",
            "license_disabled": "授权已停用，请联系管理员。",
            "license_expired": "授权已过期，请续费后继续使用。",
        }
        raise HTTPException(status_code=exc.status_code, detail=messages.get(exc.detail, exc.detail)) from exc
    except CommercialLicenseError as exc:
        raise HTTPException(status_code=403, detail=f"授权校验失败：{exc}") from exc
    if response.get("allowed") is False:
        raise HTTPException(status_code=403, detail="可用积分不足，请充值或购买正式版后继续使用。")
    return response


def _reserve_commercial_credits_or_raise(
    settings: Settings,
    license_client: CommercialLicenseClient,
    *,
    usage_seconds: int,
    provider: str,
    feature: str,
    context: dict[str, object] | None = None,
) -> dict[str, object]:
    if not settings.commercial_license_required:
        return {"ok": True, "skipped": True}
    try:
        return license_client.reserve_credits(
            seconds=max(int(usage_seconds or 0), 1),
            provider=provider,
            feature=feature,
            context=context or {},
        )
    except CommercialLicenseHttpError as exc:
        messages = {
            "license_credit_insufficient": "可用积分不足，请充值或购买正式版后继续使用。",
            "activation_token_invalid": "授权已失效，请重新激活。",
            "license_disabled": "授权已停用，请联系管理员。",
            "license_expired": "授权已过期，请续费后继续使用。",
        }
        raise HTTPException(status_code=exc.status_code, detail=messages.get(exc.detail, exc.detail)) from exc
    except CommercialLicenseError as exc:
        raise HTTPException(status_code=403, detail=f"授权校验失败：{exc}") from exc


def _commit_commercial_credits_best_effort(
    license_client: CommercialLicenseClient,
    reservation: dict[str, object],
    *,
    actual_seconds: int | None = None,
    context: dict[str, object] | None = None,
) -> None:
    reservation_id = str(reservation.get("reservation_id") or "")
    if not reservation_id:
        return
    try:
        license_client.commit_credits(
            reservation_id=reservation_id,
            actual_seconds=actual_seconds,
            context=context or {},
        )
    except CommercialLicenseError:
        return


def _commit_commercial_credits_on_cloud_failure(
    license_client: CommercialLicenseClient,
    reservation: dict[str, object],
    *,
    actual_seconds: int | None = None,
    reason: str,
    context: dict[str, object] | None = None,
) -> None:
    failure_context = {"failure_reason": reason, **(context or {})}
    _commit_commercial_credits_best_effort(
        license_client,
        reservation,
        actual_seconds=actual_seconds,
        context=failure_context,
    )


def _estimate_cloud_usage_seconds(text: str, *, fallback_seconds: int = 3) -> int:
    compact = re.sub(r"\s+", "", text or "")
    if not compact:
        return max(int(fallback_seconds), 1)
    return max((len(compact) + 3) // 4, 1)


def get_file_repositories(settings: Settings = Depends(get_settings)) -> FileRepositoryBundle:
    return FileRepositoryBundle(settings)


def get_local_object_storage(settings: Settings = Depends(get_settings)) -> LocalObjectStorage:
    return LocalObjectStorage(settings.object_storage_root)


def get_reference_video_store(settings: Settings = Depends(get_settings)) -> ReferenceVideoStore:
    return ReferenceVideoStore(settings)


def get_reference_content_collector(settings: Settings = Depends(get_settings)) -> ReferenceContentCollector:
    return ReferenceContentCollector(settings)


def get_reference_link_transcription_service(
    settings: Settings = Depends(get_settings),
    collector: ReferenceContentCollector = Depends(get_reference_content_collector),
    reference_store: ReferenceVideoStore = Depends(get_reference_video_store),
) -> ReferenceLinkTranscriptionService:
    return ReferenceLinkTranscriptionService(settings, collector=collector, reference_store=reference_store)


def get_script_rewrite_store(settings: Settings = Depends(get_settings)) -> ScriptRewriteStore:
    return ScriptRewriteStore(settings)


def get_campaign_store(settings: Settings = Depends(get_settings)) -> CampaignStore:
    return CampaignStore(settings)


def get_publish_console_store(settings: Settings = Depends(get_settings)) -> PublishConsoleStore:
    return PublishConsoleStore(settings)


def get_publish_browser_automation(settings: Settings = Depends(get_settings)) -> PublishBrowserAutomation:
    return PUBLISH_BROWSER_AUTOMATION.configure(settings)


def get_desktop_settings_store(settings: Settings = Depends(get_settings)) -> DesktopSettingsStore:
    return DesktopSettingsStore(settings)


def get_llm_platform_store(settings: Settings = Depends(get_settings)) -> LLMPlatformStore:
    return LLMPlatformStore(settings.storage_dir)


def get_source_video_workflow(settings: Settings = Depends(get_settings)) -> SourceVideoWorkflow:
    return SourceVideoWorkflow(settings)


def _wav2lip_adapter(settings: Settings) -> Wav2LipAdapter:
    return Wav2LipAdapter(
        source_root=settings.wav2lip_root,
        checkpoint_path=settings.wav2lip_checkpoint,
        python_executable=settings.wav2lip_python,
        timeout_seconds=settings.wav2lip_timeout_seconds,
        dry_run=settings.dry_run,
        enabled=settings.wav2lip_enabled,
    )


def _yywav2lip_adapter(settings: Settings) -> YYWav2LipAdapter:
    return YYWav2LipAdapter(
        source_root=settings.wav2lip_root,
        checkpoint_path=settings.yy_wav2lip_checkpoint,
        role_model_dir=settings.yy_wav2lip_role_model_dir,
        python_executable=settings.wav2lip_python,
        timeout_seconds=settings.yy_wav2lip_timeout_seconds,
        dry_run=settings.dry_run,
        enabled=settings.yy_wav2lip_enabled,
    )


def _syncso_adapter(settings: Settings) -> SyncSoLipSyncAdapter:
    return SyncSoLipSyncAdapter(
        dry_run=settings.dry_run,
        enabled=settings.cloud_lipsync_enabled and settings.cloud_lipsync_provider.lower() == "syncso",
        base_url=settings.syncso_base_url,
        api_key=settings.syncso_api_key,
        model=settings.syncso_model,
        generate_endpoint=settings.syncso_generate_endpoint,
        timeout_seconds=settings.syncso_timeout_seconds,
        poll_interval_seconds=settings.syncso_poll_interval_seconds,
    )


def _cloud_lipsync_adapter(settings: Settings):
    provider = settings.cloud_lipsync_provider.lower()
    if provider in {"pixverse", "pixverse_lipsync"}:
        return PixVerseLipSyncAdapter(
            dry_run=settings.dry_run,
            enabled=settings.cloud_lipsync_enabled,
            base_url=settings.pixverse_base_url,
            api_key=settings.pixverse_api_key,
            model=settings.pixverse_model,
            generate_endpoint=settings.pixverse_generate_endpoint,
            task_endpoint_template=settings.pixverse_task_endpoint_template,
            timeout_seconds=settings.pixverse_timeout_seconds,
            poll_interval_seconds=settings.pixverse_poll_interval_seconds,
        )
    return _syncso_adapter(settings)


def _omnihuman_adapter(settings: Settings) -> OmniHumanVideoAdapter:
    return OmniHumanVideoAdapter(
        dry_run=settings.dry_run,
        enabled=settings.omnihuman_enabled,
        access_key=settings.omnihuman_access_key,
        secret_key=settings.omnihuman_secret_key,
        endpoint=settings.omnihuman_endpoint,
        region=settings.omnihuman_region,
        service=settings.omnihuman_service,
        version=settings.omnihuman_version,
        req_key=settings.omnihuman_req_key,
        output_resolution=settings.omnihuman_output_resolution,
        prompt=settings.omnihuman_prompt,
        pe_fast_mode=settings.omnihuman_pe_fast_mode,
        timeout_seconds=settings.omnihuman_timeout_seconds,
        poll_interval_seconds=settings.omnihuman_poll_interval_seconds,
    )


def _tavus_adapter(settings: Settings) -> TavusVideoAdapter:
    return TavusVideoAdapter(
        dry_run=settings.dry_run,
        enabled=settings.tavus_enabled,
        base_url=settings.tavus_base_url,
        api_key=settings.tavus_api_key,
        replica_id=settings.tavus_replica_id,
        video_endpoint=settings.tavus_video_endpoint,
        timeout_seconds=settings.tavus_timeout_seconds,
        poll_interval_seconds=settings.tavus_poll_interval_seconds,
    )


def _baidu_xiling_adapter(settings: Settings) -> BaiduXilingVideoAdapter:
    return BaiduXilingVideoAdapter(
        dry_run=settings.dry_run,
        enabled=settings.baidu_xiling_enabled or settings.cloud_video_provider == "baidu_xiling",
        base_url=settings.baidu_xiling_base_url,
        app_id=settings.baidu_xiling_app_id,
        app_key=settings.baidu_xiling_app_key,
        figure_id=settings.baidu_xiling_figure_id,
        tts_person=settings.baidu_xiling_tts_person,
        width=settings.baidu_xiling_width,
        height=settings.baidu_xiling_height,
        transparent=settings.baidu_xiling_transparent,
        timeout_seconds=settings.baidu_xiling_timeout_seconds,
        poll_interval_seconds=settings.baidu_xiling_poll_interval_seconds,
    )


def _hifly_adapter(settings: Settings) -> HiflyDigitalHumanAdapter:
    return HiflyDigitalHumanAdapter(
        dry_run=settings.dry_run,
        enabled=settings.hifly_enabled or settings.cloud_video_provider == "hifly",
        base_url=settings.hifly_base_url,
        token=settings.hifly_token,
        required=settings.hifly_required,
        poll_interval_seconds=settings.hifly_poll_interval_seconds,
        timeout_seconds=settings.hifly_timeout_seconds,
    )


@app.get("/health")
def health(settings: Settings = Depends(get_settings)) -> dict[str, object]:
    return {
        "status": "ok",
        "dry_run": False,
        "runtime_mode": settings.runtime_mode,
        "aivo_desktop_backend": True,
    }


@app.get("/desktop/license/status")
def desktop_license_status(
    version: str = "",
    settings: Settings = Depends(get_settings),
    license_client: CommercialLicenseClient = Depends(get_desktop_license_client),
) -> dict[str, object]:
    if not settings.commercial_license_required:
        return {
            "activated": True,
            "allowed": True,
            "status": "license_not_required",
            "message": "当前版本未启用商业授权校验。",
            "features": ["digital_human", "video_remix", "publish"],
            "update": {},
        }
    return license_client.status(app_version=version)


@app.post("/desktop/license/activate")
def desktop_license_activate(
    request: DesktopLicenseActivateRequest,
    license_client: CommercialLicenseClient = Depends(get_desktop_license_client),
) -> dict[str, object]:
    try:
        return license_client.activate(
            request.license_key.strip(),
            app_version=request.app_version,
            device_name=request.device_name,
        )
    except CommercialLicenseError as exc:
        status_code = int(getattr(exc, "status_code", 400) or 400)
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@app.post("/desktop/license/deactivate")
def desktop_license_deactivate(
    license_client: CommercialLicenseClient = Depends(get_desktop_license_client),
) -> dict[str, object]:
    license_client.clear_activation()
    return {"ok": True, "message": "已清除本机授权。"}


@app.get("/desktop/license/credits")
def desktop_license_credits(
    limit: int = Query(20, ge=1, le=100),
    license_client: CommercialLicenseClient = Depends(get_desktop_license_client),
) -> dict[str, object]:
    try:
        return license_client.credit_overview(limit=limit)
    except CommercialLicenseError as exc:
        status_code = int(getattr(exc, "status_code", 400) or 400)
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@app.get("/desktop/update/check")
def desktop_update_check(
    version: str = Query("0.0.0"),
    channel: str = Query("stable"),
    platform: str = Query("windows"),
    license_client: CommercialLicenseClient = Depends(get_desktop_license_client),
) -> dict[str, object]:
    try:
        return license_client.check_update(current_version=version, channel=channel, platform_name=platform)
    except CommercialLicenseError as exc:
        status_code = int(getattr(exc, "status_code", 400) or 400)
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@app.get("/settings/desktop")
def get_desktop_settings(
    desktop_settings_store: DesktopSettingsStore = Depends(get_desktop_settings_store),
) -> dict[str, object]:
    config = desktop_settings_store.load()
    return _desktop_settings_public_body(config)


@app.put("/settings/desktop")
def put_desktop_settings(
    request: DesktopSettingsConfig,
    desktop_settings_store: DesktopSettingsStore = Depends(get_desktop_settings_store),
) -> dict[str, object]:
    config = desktop_settings_store.save(request)
    _clear_settings_cache()
    return _desktop_settings_public_body(config)


def _desktop_settings_public_body(config: DesktopSettingsConfig) -> dict[str, object]:
    body = config.model_dump(by_alias=True)
    for key in SECRET_DESKTOP_SETTING_KEYS:
        if key in body:
            body[key] = ""
    body["env_output"] = config.as_env()
    return body


def _repository_root() -> Path:
    return Path(__file__).resolve().parent


@app.post("/settings/desktop/validate")
def validate_desktop_settings_endpoint(
    request: DesktopSettingsConfig | None = None,
    desktop_settings_store: DesktopSettingsStore = Depends(get_desktop_settings_store),
) -> dict[str, object]:
    config = desktop_settings_store.with_preserved_secrets(request) if request else desktop_settings_store.load()
    return validate_desktop_settings(config, repository_root=_repository_root())


@app.get("/settings/alignment-report")
def desktop_settings_alignment_report(
    desktop_settings_store: DesktopSettingsStore = Depends(get_desktop_settings_store),
) -> dict[str, object]:
    config = desktop_settings_store.load()
    validation = validate_desktop_settings(config, repository_root=_repository_root())
    return alignment_report(config, validation)


@app.get("/settings/cloud-providers")
def cloud_provider_settings(settings: Settings = Depends(get_settings)) -> dict[str, object]:
    configs = [item.model_dump(mode="json") for item in build_cloud_provider_configs(settings)]
    return {
        "voice_providers": [item for item in configs if item["provider_type"] == "voice"],
        "video_providers": [item for item in configs if item["provider_type"] == "video"],
        "selected_voice_provider": settings.cloud_voice_provider,
        "selected_video_provider": settings.cloud_video_provider,
    }


@app.get("/models/catalog")
def get_models_catalog(
    desktop_settings_store: DesktopSettingsStore = Depends(get_desktop_settings_store),
) -> dict[str, object]:
    return model_catalog(desktop_settings_store.load())


@app.get("/models/selection")
def get_models_selection(
    desktop_settings_store: DesktopSettingsStore = Depends(get_desktop_settings_store),
) -> dict[str, object]:
    config = desktop_settings_store.load()
    return {
        "selection": current_model_selection(config).model_dump(mode="json"),
        "config_summary": _current_config_summary(config),
    }


@app.put("/models/selection")
def put_models_selection(
    request: ModelSelectionRequest,
    desktop_settings_store: DesktopSettingsStore = Depends(get_desktop_settings_store),
) -> dict[str, object]:
    try:
        config = apply_model_selection(desktop_settings_store.load(), request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    config = desktop_settings_store.save(config)
    _clear_settings_cache()
    return {
        "selection": current_model_selection(config).model_dump(mode="json"),
        "config_summary": _current_config_summary(config),
    }


@app.post("/models/selection/validate")
def validate_models_selection(
    request: ModelSelectionRequest | None = None,
    desktop_settings_store: DesktopSettingsStore = Depends(get_desktop_settings_store),
) -> dict[str, object]:
    try:
        config = apply_model_selection(desktop_settings_store.load(), request) if request else desktop_settings_store.load()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return validate_model_selection(config, repository_root=_repository_root())


@app.get("/models/readiness")
def get_models_readiness(
    desktop_settings_store: DesktopSettingsStore = Depends(get_desktop_settings_store),
) -> dict[str, object]:
    config = desktop_settings_store.load()
    return validate_model_selection(config, repository_root=_repository_root())


@app.post("/models/presets/apply")
def apply_models_preset(
    request: ModelPresetRequest,
    desktop_settings_store: DesktopSettingsStore = Depends(get_desktop_settings_store),
) -> dict[str, object]:
    try:
        config = apply_model_preset(desktop_settings_store.load(), request.preset_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    config = desktop_settings_store.save(config)
    _clear_settings_cache()
    return {
        "selection": current_model_selection(config).model_dump(mode="json"),
        "config_summary": _current_config_summary(config),
    }


def _clear_settings_cache() -> None:
    cache_clear = getattr(get_settings, "cache_clear", None)
    if callable(cache_clear):
        cache_clear()


@app.get("/llm/platforms")
def get_llm_platforms(
    llm_store: LLMPlatformStore = Depends(get_llm_platform_store),
) -> dict[str, object]:
    return llm_store.safe_document()


@app.put("/llm/platforms")
def put_llm_platforms(
    request: LLMPlatformConfigDocument,
    llm_store: LLMPlatformStore = Depends(get_llm_platform_store),
) -> dict[str, object]:
    llm_store.save_preserving_secrets(request)
    _clear_settings_cache()
    return llm_store.safe_document()


@app.post("/llm/platforms/{platform_id}/check")
def check_llm_platform(
    platform_id: str,
    llm_store: LLMPlatformStore = Depends(get_llm_platform_store),
) -> dict[str, object]:
    try:
        return llm_store.check_platform(platform_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/llm/platforms/{platform_id}/models/refresh")
def refresh_llm_platform_models(
    platform_id: str,
    llm_store: LLMPlatformStore = Depends(get_llm_platform_store),
) -> dict[str, object]:
    try:
        result = llm_store.refresh_models(platform_id)
        _clear_settings_cache()
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.put("/llm/selection")
def put_llm_selection(
    request: LLMSelectionRequest,
    llm_store: LLMPlatformStore = Depends(get_llm_platform_store),
) -> dict[str, object]:
    try:
        llm_store.set_selection(request.platformId, request.modelId)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _clear_settings_cache()
    return llm_store.safe_document()


@app.post("/llm/local-models")
def create_llm_local_model(
    request: LocalLLMModel,
    llm_store: LLMPlatformStore = Depends(get_llm_platform_store),
) -> dict[str, object]:
    try:
        created = llm_store.create_local_model(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _clear_settings_cache()
    return created.model_dump(mode="json")


@app.put("/llm/local-models/{model_id}")
def update_llm_local_model(
    model_id: str,
    request: LocalLLMModel,
    llm_store: LLMPlatformStore = Depends(get_llm_platform_store),
) -> dict[str, object]:
    try:
        updated = llm_store.update_local_model(model_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _clear_settings_cache()
    return updated.model_dump(mode="json")


@app.delete("/llm/local-models/{model_id}")
def delete_llm_local_model(
    model_id: str,
    llm_store: LLMPlatformStore = Depends(get_llm_platform_store),
) -> dict[str, object]:
    try:
        llm_store.delete_local_model(model_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _clear_settings_cache()
    return llm_store.safe_document()


@app.post("/integrations/hifly/validate")
async def validate_hifly_provider(live: bool = False, settings: Settings = Depends(get_settings)) -> dict[str, object]:
    adapter = _hifly_adapter(settings)
    if live:
        return await adapter.probe_token()
    return adapter.validate_config()


@app.get("/settings/cloud-cost-estimate")
def cloud_cost_estimate(
    videos_per_month: int = 30,
    average_duration_seconds: int = 60,
    average_chinese_chars_per_video: int = 500,
    voice_provider: str = "aliyun_bailian_cosyvoice",
    video_provider: str = "fal_latentsync",
) -> dict[str, object]:
    return estimate_cloud_cost(
        videos_per_month=videos_per_month,
        average_duration_seconds=average_duration_seconds,
        average_chinese_chars_per_video=average_chinese_chars_per_video,
        voice_provider=voice_provider,
        video_provider=video_provider,
    ).model_dump(mode="json")


@app.post("/source-video/script/generate", response_model=InlineSourceVideoScriptResponse)
async def generate_inline_source_video_script(
    request: InlineSourceVideoScriptRequest,
    settings: Settings = Depends(get_settings),
) -> InlineSourceVideoScriptResponse:
    mode = _normalize_inline_script_mode(request.mode)
    topic = request.topic.strip()
    current_script = request.current_script.strip()
    if mode == "translate":
        if not current_script:
            raise HTTPException(status_code=400, detail="请先填写需要翻译的脚本文案。")
        topic = current_script[:120]
    if mode in {"rewrite", "legal"} and current_script and not topic:
        topic = current_script[:120]
    if not topic and not current_script:
        raise HTTPException(status_code=400, detail="请先填写主题或产品资料。")
    if not settings.dry_run and not request.confirm_paid_call:
        raise HTTPException(status_code=402, detail="云端大模型生成文案可能消耗额度，请确认后再生成。")

    script_generator = select_script_generator_adapter(settings)
    out_dir = ensure_dir(settings.storage_dir / "desktop" / "inline_scripts" / uuid4().hex)
    target_char_count = _normalize_inline_target_char_count(request.target_char_count)
    if mode == "translate":
        target_char_count = None
    language = _normalize_inline_language(request.language)
    if mode == "rewrite" and target_char_count is None and current_script:
        target_char_count = max(20, min(2000, _visible_text_length(current_script)))
    duration_seconds = request.duration_seconds
    if duration_seconds is None:
        duration_seconds = max(10, min(180, round((target_char_count or 180) / 4)))
    duration_seconds = max(10, min(180, int(duration_seconds or 45)))
    length_unit = f"{_inline_language_name(language)} visible characters"
    if mode == "translate":
        length_rule = "Translate the full current_script. Keep the meaning complete and do not expand or summarize."
    else:
        length_rule = (
            f"Target length: about {target_char_count} {length_unit}. "
            f"Do not exceed {max(target_char_count, int(target_char_count * 1.35))} visible characters."
            if target_char_count
            else "Keep the spoken script concise for short-video delivery."
        )
    task_request = CreateVideoTaskRequest(
        brand_name=topic[:80],
        persona="中文短视频数字人口播主播",
        topic=topic,
        project_id=request.project_id or "project_demo",
        platform=request.platform,
        duration_seconds=duration_seconds,
        fixed_script=None,
        export_jianying_draft=False,
        render_profile="final",
        use_digital_human_pipeline=False,
        metadata={
            "source": "source_video_workbench_inline_ai",
            "mode": mode,
            "style": request.style,
            "current_script": current_script[:4000],
            "language": language,
            "language_requirements": _inline_language_requirements(language),
            "target_char_count": target_char_count,
            "length_rule": length_rule,
            "requirements": [
                "必须围绕用户输入主题生成，不要改写成 Aivo 软件介绍",
                "适合数字人口播，中文，直接可朗读",
                "包含客户痛点、核心卖点、信任理由和行动引导",
                "不要编造具体价格、认证、库存、销量等无法确认的事实",
            ],
            "requirements": _inline_script_requirements(mode, language),
        },
    )
    try:
        script_path = await script_generator.generate_script(task_request, out_dir)
        script_json = read_json(script_path)
    except AdapterError as exc:
        raise HTTPException(status_code=503, detail=_redact_sensitive_text(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - user needs a clear UI failure.
        raise HTTPException(status_code=503, detail=_redact_sensitive_text(exc)) from exc

    raw_script_text = _inline_script_text(script_json, mode=mode)
    script_text = _fit_inline_script_to_target(raw_script_text, target_char_count)
    if not script_text:
        raise HTTPException(status_code=503, detail="云端模型没有返回可用脚本文案。")
    if mode == "translate":
        script_json["title"] = ""
        script_json["hook"] = ""
        script_json["body"] = script_text
        script_json["cta"] = ""
        script_json["segments"] = [{"start": 0, "end": duration_seconds, "text": script_text, "type": "body"}]
        script_json["translation_only"] = True
        write_json(script_path, script_json)
    elif target_char_count:
        script_json["target_char_count"] = target_char_count
        script_json["script_text_trimmed_to_target"] = script_text != raw_script_text
        script_json["segments"] = [{"start": 0, "end": duration_seconds, "text": script_text, "type": "body"}]
        write_json(script_path, script_json)
    llm_meta = script_json.get("llm") if isinstance(script_json.get("llm"), dict) else {}
    return InlineSourceVideoScriptResponse(
        status="generated",
        script_text=script_text,
        script_json=script_json,
        engine=str(llm_meta.get("engine") or getattr(script_generator, "name", "script_generator")),
        model=str(llm_meta.get("model") or "") or None,
        fallback_used=False,
    )


def _inline_script_text(script_json: dict[str, object], *, mode: str = "generate") -> str:
    if mode == "translate":
        return _inline_translation_script_text(script_json)

    segments = script_json.get("segments")
    if isinstance(segments, list) and segments:
        texts = []
        for segment in segments:
            if isinstance(segment, dict):
                text = str(segment.get("text") or "").strip()
                if text and text not in texts:
                    texts.append(text)
        if texts:
            return "\n".join(texts)

    texts = []
    for key in ("hook", "body", "cta"):
        text = str(script_json.get(key) or "").strip()
        if text and text not in texts:
            texts.append(text)
    return "\n".join(texts).strip()


def _inline_translation_script_text(script_json: dict[str, object]) -> str:
    for key in ("body", "translated_text", "translation", "script_text"):
        text = str(script_json.get(key) or "").strip()
        if text:
            return _clean_inline_translation_text(text)

    segments = script_json.get("segments")
    if isinstance(segments, list) and segments:
        body_texts = []
        fallback_texts = []
        for segment in segments:
            if not isinstance(segment, dict):
                continue
            text = str(segment.get("text") or "").strip()
            if not text:
                continue
            segment_type = str(segment.get("type") or "").strip().lower()
            if segment_type in {"body", "translation", "translated_text"}:
                body_texts.append(text)
            elif not segment_type:
                fallback_texts.append(text)
        selected = body_texts or fallback_texts
        if selected:
            return _clean_inline_translation_text("\n".join(dict.fromkeys(selected)))

    return ""


def _clean_inline_translation_text(text: str) -> str:
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^```(?:\w+)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    cleaned = re.sub(r"^(?:翻译结果|译文|translation|translated script)\s*[:：]\s*", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def _normalize_inline_target_char_count(value: int | None) -> int | None:
    if value is None:
        return None
    try:
        count = int(value)
    except (TypeError, ValueError):
        return None
    return max(20, min(2000, count))


def _normalize_inline_script_mode(value: str | None) -> str:
    normalized = (value or "generate").strip().lower().replace("-", "_")
    if normalized in {"rewrite", "legal", "translate"}:
        return normalized
    return "generate"


def _normalize_inline_language(value: str | None) -> str:
    normalized = (value or "zh-CN").strip().lower().replace("_", "-")
    if normalized in {"en", "en-us", "english"}:
        return "en-US"
    if normalized in {"es", "es-es", "spanish"}:
        return "es-ES"
    if normalized in {"ar", "ar-sa", "arabic"}:
        return "ar-SA"
    if normalized in {"pt", "pt-br", "portuguese"}:
        return "pt-BR"
    return "zh-CN"


def _inline_language_name(language: str) -> str:
    return {
        "en-US": "English",
        "es-ES": "Spanish",
        "ar-SA": "Arabic",
        "pt-BR": "Portuguese",
        "zh-CN": "Simplified Chinese Mandarin",
    }.get(language, "Simplified Chinese Mandarin")


def _inline_script_requirements(mode: str, language: str) -> list[str]:
    base = [
        "Use the exact user topic and do not turn the script into Aivo software promotion.",
        "Write for spoken digital-human short video delivery.",
        "Keep the output directly readable as a short-video script.",
        "Do not invent prices, certifications, inventory, sales volume, or unverifiable claims.",
    ]
    if mode == "rewrite":
        return [
            "Rewrite the current_script: change only selected words, phrases, and sentence rhythm.",
            "Keep the topic and core content unchanged, including product facts, audience, selling points, and call to action.",
            "Keep the rewritten script close to the original visible character count; do not expand it into a longer script.",
            "Do not change the theme, add new claims, or remove the original message structure.",
            *_inline_language_requirements(language),
            *base,
        ]
    if mode == "legal":
        return [
            "Compliance rewrite: use the AI model to avoid risk words, banned terms, absolute claims, exaggerated promises, and platform-sensitive wording.",
            "Keep the marketing meaning but make the wording safer and more conservative.",
            "Do not add medical, financial, certification, price, inventory, or sales-volume claims unless present in the source.",
            *_inline_language_requirements(language),
            *base,
        ]
    if mode == "translate":
        target_language = _inline_language_name(language)
        return [
            f"Translate current_script into natural {target_language}.",
            "Preserve the original meaning, facts, audience, selling points, tone, and call to action.",
            "Do not rewrite, polish, expand, summarize, add headings, labels, hooks, selling points, CTA, explanations, comments, or new claims.",
            "Return only the translated script content.",
            f"Output language must be natural {target_language}.",
        ]
    return [
        "Generate a new spoken short-video script from the user topic and reference material.",
        "Include customer pain point, core selling point, trust reason, and call to action.",
        *_inline_language_requirements(language),
        *base,
    ]


def _inline_language_requirements(language: str) -> list[str]:
    if language == "en-US":
        return [
            "Output language must be natural English.",
            "Write for spoken digital-human short video delivery.",
            "Use the exact user topic and do not turn the script into Aivo software promotion.",
            "Include customer pain point, core selling point, trust reason, and call to action.",
            "Do not invent prices, certifications, inventory, sales volume, or unverifiable claims.",
        ]
    if language == "es-ES":
        return [
            "Output language must be natural Spanish.",
            "Write for spoken digital-human short video delivery.",
            "Use the exact user topic and do not turn the script into Aivo software promotion.",
            "Include customer pain point, core selling point, trust reason, and call to action.",
            "Do not invent prices, certifications, inventory, sales volume, or unverifiable claims.",
        ]
    if language == "ar-SA":
        return [
            "Output language must be natural Arabic.",
            "Write for spoken digital-human short video delivery.",
            "Use the exact user topic and do not turn the script into Aivo software promotion.",
            "Include customer pain point, core selling point, trust reason, and call to action.",
            "Do not invent prices, certifications, inventory, sales volume, or unverifiable claims.",
        ]
    if language == "pt-BR":
        return [
            "Output language must be natural Portuguese.",
            "Write for spoken digital-human short video delivery.",
            "Use the exact user topic and do not turn the script into Aivo software promotion.",
            "Include customer pain point, core selling point, trust reason, and call to action.",
            "Do not invent prices, certifications, inventory, sales volume, or unverifiable claims.",
        ]
    return [
        "Output language must be Simplified Chinese Mandarin.",
        "Write for spoken digital-human short video delivery.",
        "Use the exact user topic and do not turn the script into Aivo software promotion.",
        "Include customer pain point, core selling point, trust reason, and call to action.",
        "Do not invent prices, certifications, inventory, sales volume, or unverifiable claims.",
    ]


def _visible_text_length(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def _truncate_visible_text(text: str, limit: int) -> str:
    chars: list[str] = []
    visible_count = 0
    previous_space = False
    for char in (text or "").strip():
        if char.isspace():
            if chars and not previous_space:
                chars.append(" ")
            previous_space = True
            continue
        if visible_count >= limit:
            break
        chars.append(char)
        visible_count += 1
        previous_space = False
    result = "".join(chars).strip()
    if result and result[-1] not in "。！？!?.,，；;":
        result += "。"
    return result


def _fit_inline_script_to_target(text: str, target_char_count: int | None) -> str:
    text = (text or "").strip()
    if not text or not target_char_count:
        return text
    max_chars = max(target_char_count, int(target_char_count * 1.35))
    if _visible_text_length(text) <= max_chars:
        return text

    sentences = [item.strip() for item in re.findall(r"[^。！？!?；;\n]+[。！？!?；;]?", text) if item.strip()]
    if not sentences:
        return _truncate_visible_text(text, max_chars)

    selected: list[str] = []
    for sentence in sentences:
        candidate = "\n".join([*selected, sentence]).strip()
        if _visible_text_length(candidate) <= max_chars:
            selected.append(sentence)
            continue
        if selected:
            break
        return _truncate_visible_text(sentence, max_chars)
    return "\n".join(selected).strip() or _truncate_visible_text(text, max_chars)


@app.post("/source-video/tags/generate", response_model=InlineSourceVideoTagResponse)
async def generate_inline_source_video_tags(
    request: InlineSourceVideoTagRequest,
    settings: Settings = Depends(get_settings),
) -> InlineSourceVideoTagResponse:
    topic = request.topic.strip()
    script_text = request.script_text.strip()
    if not topic and not script_text:
        raise HTTPException(status_code=400, detail="请先填写主题或脚本文案。")
    if not settings.dry_run and not request.confirm_paid_call:
        raise HTTPException(status_code=402, detail="云端大模型生成标题标签可能消耗额度，请确认后再生成。")

    adapter = select_script_generator_adapter(settings)
    generator = getattr(adapter, "generate_title_tags", None)
    if not callable(generator):
        raise HTTPException(status_code=503, detail="当前脚本生成模型暂不支持标题标签生成，请启用 OpenAI 兼容大模型。")

    out_dir = ensure_dir(settings.storage_dir / "desktop" / "inline_tags" / uuid4().hex)
    language = _normalize_inline_language(request.language)
    try:
        result_path = await generator(
            {
                "topic": topic or script_text[:60],
                "script_text": script_text,
                "project_id": request.project_id or "project_demo",
                "platform": request.platform,
                "language": language,
                "language_requirements": _inline_language_requirements(language),
                "source": "source_video_workbench_tag_ai",
            },
            out_dir,
        )
        result = read_json(result_path)
    except AdapterError as exc:
        raise HTTPException(status_code=503, detail=_redact_sensitive_text(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - keep UI failures readable.
        raise HTTPException(status_code=503, detail=_redact_sensitive_text(exc)) from exc

    title = str(result.get("title") or topic or "短视频标题").strip()
    tags = _clean_inline_text_list(result.get("tags")) or _clean_inline_text_list([topic, "短视频"])
    keywords = _clean_inline_text_list(result.get("keywords")) or tags
    llm_meta = result.get("llm") if isinstance(result.get("llm"), dict) else {}
    return InlineSourceVideoTagResponse(
        status="generated",
        title=title,
        tags=tags[:8],
        keywords=keywords[:10],
        engine=str(llm_meta.get("engine") or getattr(adapter, "name", "script_generator")),
        model=str(llm_meta.get("model") or "") or None,
        fallback_used=False,
    )


def _clean_inline_text_list(value: object) -> list[str]:
    if isinstance(value, str):
        items = re.split(r"[,，、\n]+", value)
    elif isinstance(value, list):
        items = value
    else:
        items = []
    cleaned: list[str] = []
    for item in items:
        text = str(item or "").strip().lstrip("#").strip()
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned


@app.get("/settings/simple")
def get_simple_settings(
    desktop_settings_store: DesktopSettingsStore = Depends(get_desktop_settings_store),
) -> dict[str, object]:
    repository_root = _repository_root()
    config = desktop_settings_store.load()
    detection = run_settings_autodetect(config, repository_root=repository_root)
    return _simple_settings_response(config, detection)


@app.post("/settings/simple/apply-preset")
def apply_simple_settings_preset(
    request: ApplySimpleSettingsPresetRequest,
    desktop_settings_store: DesktopSettingsStore = Depends(get_desktop_settings_store),
) -> dict[str, object]:
    repository_root = _repository_root()
    current = desktop_settings_store.load()
    detection = run_settings_autodetect(current, repository_root=repository_root) if request.auto_detect else None
    try:
        preset = get_settings_preset(
            request.preset_id,
            current_config=current,
            detected_values=detection.detected_values if detection else {},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    config = desktop_settings_store.save(preset.config)
    _clear_settings_cache()
    detection = run_settings_autodetect(config, repository_root=repository_root)
    body = _simple_settings_response(config, detection)
    body["recommended_actions"] = list(dict.fromkeys([*preset.recommended_actions, *body["recommended_actions"]]))
    return body


@app.post("/settings/simple/autodetect")
def autodetect_simple_settings(
    desktop_settings_store: DesktopSettingsStore = Depends(get_desktop_settings_store),
) -> dict[str, object]:
    config = desktop_settings_store.load()
    detection = run_settings_autodetect(config, repository_root=_repository_root())
    return detection.model_dump(mode="json")


@app.post("/settings/simple/validate")
def validate_simple_settings(
    request: DesktopSettingsConfig | None = None,
    desktop_settings_store: DesktopSettingsStore = Depends(get_desktop_settings_store),
) -> dict[str, object]:
    repository_root = _repository_root()
    config = desktop_settings_store.with_preserved_secrets(request) if request else desktop_settings_store.load()
    validation = validate_desktop_settings(config, repository_root=repository_root)
    detection = run_settings_autodetect(config, repository_root=repository_root)
    red_checks = [item for item in validation["checks"] if item["status"] == "red"]
    yellow_checks = [item for item in validation["checks"] if item["status"] == "yellow"]
    return {
        **validation,
        "module_statuses": [status.model_dump(mode="json") for status in detection.module_statuses],
        "blocking_items": [item["message"] for item in red_checks],
        "warnings": [item["message"] for item in yellow_checks],
        "recommended_actions": _simple_recommended_actions(config, detection),
    }


@app.post("/settings/simple/copy-env")
def copy_simple_settings_env(
    request: DesktopSettingsConfig | None = None,
    desktop_settings_store: DesktopSettingsStore = Depends(get_desktop_settings_store),
) -> PlainTextResponse:
    config = desktop_settings_store.with_preserved_secrets(request) if request else desktop_settings_store.load()
    return PlainTextResponse(config.as_env(), media_type="text/plain")


@app.get("/settings/simple/alignment-report")
def simple_settings_alignment_report(
    desktop_settings_store: DesktopSettingsStore = Depends(get_desktop_settings_store),
) -> dict[str, object]:
    repository_root = _repository_root()
    config = desktop_settings_store.load()
    validation = validate_desktop_settings(config, repository_root=repository_root)
    detection = run_settings_autodetect(config, repository_root=repository_root)
    statuses = {status.key: status for status in detection.module_statuses}
    red_checks = [item["message"] for item in validation["checks"] if item["status"] == "red"]
    warnings = [item["message"] for item in validation["checks"] if item["status"] == "yellow"]
    return {
        "digital_human_alignment_score": _status_score(statuses, ["cloud_lipsync", "omnihuman_cloud", "tavus_cloud", "baidu_xiling", "wav2lip", "yywav2lip", "musetalk", "latentsync", "duix"]),
        "content_production_alignment_score": _status_score(statuses, ["pixelle"]),
        "jianying_alignment_score": _status_score(statuses, ["jianying"]),
        "desktop_experience_alignment_score": 100 if validation["overall_status"] == "green" else (65 if validation["overall_status"] == "yellow" else 35),
        "blocking_items": red_checks,
        "warnings": warnings,
        "recommended_next_actions": _simple_recommended_actions(config, detection),
        "module_statuses": [status.model_dump(mode="json") for status in detection.module_statuses],
    }


def _simple_settings_response(config: DesktopSettingsConfig, detection: SettingsAutoDetectResult) -> dict[str, object]:
    advanced_config = config.model_dump(by_alias=True)
    for key in SECRET_DESKTOP_SETTING_KEYS:
        if key in advanced_config:
            advanced_config[key] = ""
    return {
        "selected_preset": config.selected_preset,
        "current_config_summary": _current_config_summary(config),
        "module_statuses": [status.model_dump(mode="json") for status in detection.module_statuses],
        "recommended_actions": _simple_recommended_actions(config, detection),
        "advanced_config": advanced_config,
        "env_output": config.as_env(),
    }


def _current_config_summary(config: DesktopSettingsConfig) -> dict[str, object]:
    enabled_modules = []
    for enabled, label in [
        (config.pixelle_enabled, "Pixelle"),
        (config.cloud_lipsync_enabled, "Sync.so 云端口型同步"),
        (config.baidu_xiling_enabled or config.cloud_video_provider == "baidu_xiling", "百度曦灵数字人"),
        (config.wav2lip_enabled, "Wav2Lip"),
        (config.yy_wav2lip_enabled, "YYWav2Lip"),
        (config.musetalk_enabled, "MuseTalk"),
        (config.latentsync_enabled, "LatentSync"),
        (config.jianying_enabled, "剪映草稿"),
        (config.duix_enabled, "Duix HTTP"),
    ]:
        if enabled:
            enabled_modules.append(label)
    return {
        "runtime_mode": config.runtime_mode,
        "tts_provider": config.tts_provider or config.tts_engine,
        "tts_engine": config.tts_engine,
        "cloud_voice_provider": config.cloud_voice_provider,
        "cloud_video_provider": config.cloud_video_provider,
        "digital_human_engine": config.digital_human_engine,
        "editing_output": config.editing_output,
        "enabled_modules": enabled_modules,
    }


def _simple_recommended_actions(config: DesktopSettingsConfig, detection: SettingsAutoDetectResult) -> list[str]:
    actions = list(detection.recommended_actions)
    if config.runtime_mode in {"compat", "standard", "final"} and config.tts_engine.lower() in {"", "dryrun", "dry-run"}:
        actions.insert(0, "当前仍使用占位声音，不是真实 TTS。请选择 Edge/阿里云/微软/CosyVoice。")
    if config.selected_preset == "dryrun_trial":
        actions.insert(0, "无需配置，可以体验完整流程，但生成的是占位媒体。")
    return list(dict.fromkeys(actions))


def _status_score(statuses: dict[str, object], keys: list[str]) -> int:
    values = [getattr(statuses[key], "status", "disabled") for key in keys if key in statuses]
    if not values:
        return 0
    if any(value == "ready" for value in values):
        return 100
    if any(value == "warning" for value in values):
        return 65
    if any(value == "missing" for value in values):
        return 35
    return 20


@app.get("/video-templates")
def video_templates() -> dict[str, object]:
    return {"templates": [template.model_dump(mode="json") for template in list_video_templates()]}


@app.get("/video-templates/{template_id}")
def video_template_detail(template_id: str) -> dict[str, object]:
    try:
        return get_video_template(template_id).model_dump(mode="json")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/cover/templates")
def cover_templates() -> dict[str, object]:
    return {"templates": list_cover_templates()}


@app.get("/cover/preview")
def cover_preview(
    path: str,
    download: bool = False,
    settings: Settings = Depends(get_settings),
) -> FileResponse:
    cover_path = _safe_storage_file(settings, path)
    if not cover_path:
        raise HTTPException(status_code=404, detail="封面文件不存在，请先生成封面。")
    filename = cover_path.name if download else None
    media_type = "application/json" if cover_path.suffix.lower() == ".json" else "image/png"
    return FileResponse(cover_path, media_type=media_type, filename=filename)


@app.post("/cover/generate", response_model=CoverGenerateResponse)
def generate_cover(
    request: CoverGenerateRequest,
    settings: Settings = Depends(get_settings),
    store: TaskStore = Depends(get_store),
) -> CoverGenerateResponse:
    if not request.task_id and not request.video_path and not request.video:
        raise HTTPException(status_code=400, detail="请先生成或选择一个成片视频。")

    cover_task_id = "cover_" + uuid4().hex
    out_dir = ensure_dir(settings.storage_dir / "cover_tasks" / cover_task_id)
    upload_dir = ensure_dir(out_dir / "upload")
    if request.video:
        video_path = _write_remix_upload(request.video, upload_dir, allowed_prefixes=("video/",))
    elif request.video_path:
        video_path = _safe_storage_file(settings, request.video_path)
        if not video_path:
            raise HTTPException(status_code=400, detail="选择的视频不可用，请重新选择或上传。")
    else:
        task = _get_task_or_404(str(request.task_id), store)
        video_path = Path(task.artifacts.final_video or store.task_dir(str(request.task_id)) / "final.mp4")
        if not video_path.exists():
            raise HTTPException(status_code=400, detail="任务成片视频不存在，请先生成视频。")

    try:
        template = get_cover_template(request.template_id)
        result = generate_cover_from_video(
            video_path=video_path,
            out_dir=out_dir,
            template=template,
            keyword_text=request.keyword_text,
            ffmpeg_path=settings.reference_ffmpeg_path,
        )
    except CoverGenerationError as exc:
        append_audit_event(
            settings.storage_dir,
            action="cover.generation_failed",
            project_id=request.project_id,
            details={"error": str(exc), "template_id": request.template_id},
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    cover_url = f"/cover/preview?path={quote(str(result.cover_image), safe='')}"
    report_url = f"/cover/preview?path={quote(str(result.report_path), safe='')}&download=1"
    append_audit_event(
        settings.storage_dir,
        action="cover.generated",
        project_id=request.project_id,
        details={
            "template_id": result.template_id,
            "keyword_text": request.keyword_text,
            "cover_path": str(result.cover_image),
            "source_video": str(video_path),
        },
    )
    return CoverGenerateResponse(
        status="completed",
        message="封面已生成，可预览或下载。",
        template_id=result.template_id,
        template_name=str(template["name"]),
        keyword_text=request.keyword_text,
        cover_path=str(result.cover_image),
        cover_url=cover_url,
        report_path=str(result.report_path),
        report_url=report_url,
    )


@app.get("/", response_class=HTMLResponse)
def studio_home() -> HTMLResponse:
    return HTMLResponse((STATIC_DIR / "studio.html").read_text(encoding="utf-8"))


@app.get("/studio.css")
def studio_css() -> FileResponse:
    return FileResponse(STATIC_DIR / "studio.css", media_type="text/css")


@app.get("/studio.js")
def studio_js() -> FileResponse:
    return FileResponse(STATIC_DIR / "studio.js", media_type="application/javascript")


@app.get("/provider-icons/{filename}")
def provider_icon(filename: str) -> FileResponse:
    if "/" in filename or "\\" in filename or filename.startswith("."):
        raise HTTPException(status_code=404, detail="Provider icon not found")
    path = STATIC_DIR / "provider-icons" / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Provider icon not found")
    return FileResponse(path)


@app.get("/static/cover-templates/{filename}")
def cover_template_image(filename: str) -> FileResponse:
    if "/" in filename or "\\" in filename or filename.startswith("."):
        raise HTTPException(status_code=404, detail="Cover template image not found")
    path = STATIC_DIR / "cover-templates" / filename
    if not path.exists() or not path.is_file() or path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise HTTPException(status_code=404, detail="Cover template image not found")
    media_type = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    if path.suffix.lower() == ".webp":
        media_type = "image/webp"
    return FileResponse(path, media_type=media_type)


def _bgm_tracks() -> list[dict[str, object]]:
    manifest_path = STATIC_DIR / "bgm" / "bgm_manifest.json"
    try:
        manifest = read_json(manifest_path)
    except Exception:  # noqa: BLE001 - optional bundled assets.
        return []
    tracks: list[dict[str, object]] = []
    for item in manifest.get("tracks", []):
        if not isinstance(item, dict):
            continue
        filename = str(item.get("filename") or "")
        if not filename or "/" in filename or "\\" in filename or filename.startswith("."):
            continue
        path = STATIC_DIR / "bgm" / filename
        track = dict(item)
        track["available"] = path.exists() and path.is_file()
        track["size_bytes"] = path.stat().st_size if path.exists() and path.is_file() else 0
        tracks.append(track)
    return tracks


def _bgm_track(track_id: str | None) -> dict[str, object] | None:
    if not track_id:
        return None
    for track in _bgm_tracks():
        if track.get("id") == track_id:
            return track
    return None


def _bgm_track_path(track: dict[str, object] | None) -> Path | None:
    if not track:
        return None
    filename = str(track.get("filename") or "")
    if not filename or "/" in filename or "\\" in filename or filename.startswith("."):
        return None
    root = (STATIC_DIR / "bgm").resolve()
    candidate = (root / filename).resolve()
    if root != candidate.parent:
        return None
    return candidate if candidate.exists() and candidate.is_file() else None


@app.get("/bgm/library")
def bgm_library() -> dict[str, object]:
    return {"tracks": _bgm_tracks()}


@app.get("/bgm/{filename}")
def bgm_file(filename: str) -> FileResponse:
    track = next((item for item in _bgm_tracks() if item.get("filename") == filename), None)
    path = _bgm_track_path(track)
    if not path:
        raise HTTPException(status_code=404, detail="Background music not found")
    return FileResponse(path, media_type="audio/mpeg")


@app.get("/readiness")
def readiness(settings: Settings = Depends(get_settings)) -> dict[str, object]:
    wav2lip_status = _wav2lip_adapter(settings).readiness()
    yywav2lip_status = _yywav2lip_adapter(settings).readiness()
    syncso_status = _syncso_adapter(settings).readiness()
    cloud_lipsync_status = _cloud_lipsync_adapter(settings).readiness()
    omnihuman_status = _omnihuman_adapter(settings).readiness()
    tavus_status = _tavus_adapter(settings).readiness()
    baidu_xiling_status = _baidu_xiling_adapter(settings).readiness()
    hifly_status = _hifly_adapter(settings).validate_config()
    compatibility_blocking_items = [
        item
        for item in [*wav2lip_status["blocking_items"], *yywav2lip_status["blocking_items"]]
        if "CHECKPOINT" in item or "role model" in item
    ]
    return {
        "status": "ok",
        "dry_run": settings.dry_run,
        "avatar_selected": "task scoped",
        "voice_profile_selected": "task scoped",
        "voice_engine_ready": True,
        "avatar_render_engine_ready": True,
        "lip_sync_engine_ready": True,
        "final_assembly_ready": True,
        "jianying_ready": settings.dry_run or bool(settings.jianying_draft_root),
        "model_assets_status": "dry-run placeholders; real checkpoints are external",
        "wav2lip": wav2lip_status,
        "yywav2lip": yywav2lip_status,
        "cloud_lipsync": cloud_lipsync_status,
        "syncso_cloud": syncso_status,
        "pixverse_cloud": cloud_lipsync_status if cloud_lipsync_status.get("provider") == "pixverse" else _cloud_lipsync_adapter(settings.model_copy(update={"cloud_lipsync_provider": "pixverse"})).readiness(),
        "omnihuman_cloud": omnihuman_status,
        "tavus_cloud": tavus_status,
        "baidu_xiling_cloud": baidu_xiling_status,
        "hifly_cloud": hifly_status,
        "compatibility_blocking_items": compatibility_blocking_items,
        "warnings": [] if settings.dry_run else ["real model readiness depends on local checkpoints"],
        "blocking_items": [],
    }


@app.get("/storage/readiness")
def storage_readiness(
    settings: Settings = Depends(get_settings),
    repositories: FileRepositoryBundle = Depends(get_file_repositories),
    object_storage: LocalObjectStorage = Depends(get_local_object_storage),
) -> dict[str, object]:
    return {
        "mode": "local" if settings.repository_backend == "file" else settings.repository_backend,
        "repositories": repositories.readiness(),
        "postgres": PostgresRepositoryBundle(settings).readiness(),
        "object_storage": object_storage.readiness(),
        "s3": S3ObjectStorage(bucket=settings.s3_bucket, endpoint_url=settings.s3_endpoint_url).readiness(),
    }


@app.post("/feedback", response_model=FeedbackRecord)
def submit_feedback(
    request: FeedbackRequest,
    feedback_store: FeedbackStore = Depends(get_feedback_store),
) -> FeedbackRecord:
    return feedback_store.create(request)


@app.get("/feedback")
def list_feedback(feedback_store: FeedbackStore = Depends(get_feedback_store)) -> dict[str, object]:
    return {"items": [item.model_dump(mode="json") for item in feedback_store.list()]}


@app.get("/feedback/export.csv")
def export_feedback_csv(feedback_store: FeedbackStore = Depends(get_feedback_store)) -> FileResponse:
    path = feedback_store.export_csv()
    return FileResponse(path, filename="trial_feedback.csv", media_type="text/csv")


@app.get("/integrations/probes")
def integration_probes(settings: Settings = Depends(get_settings)) -> dict[str, object]:
    wav2lip_status = _wav2lip_adapter(settings).readiness()
    yywav2lip_status = _yywav2lip_adapter(settings).readiness()
    syncso_status = _syncso_adapter(settings).readiness()
    cloud_lipsync_status = _cloud_lipsync_adapter(settings).readiness()
    omnihuman_status = _omnihuman_adapter(settings).readiness()
    tavus_status = _tavus_adapter(settings).readiness()
    baidu_xiling_status = _baidu_xiling_adapter(settings).readiness()
    hifly_status = _hifly_adapter(settings).validate_config()
    cloud_configs = [item.model_dump(mode="json") for item in build_cloud_provider_configs(settings)]
    cloud_voice = {item["provider_id"]: item for item in cloud_configs if item["provider_type"] == "voice"}
    cloud_video = {item["provider_id"]: item for item in cloud_configs if item["provider_type"] == "video"}
    return {
        "pixelle_http": {
            "ready": bool(settings.pixelle_enabled and settings.pixelle_base_url),
            "enabled": settings.pixelle_enabled,
            "base_url": settings.pixelle_base_url,
            "script_endpoint": settings.pixelle_script_endpoint,
            "video_endpoint": settings.pixelle_video_endpoint,
        },
        "tts_engine_ready": {"ready": bool(settings.dry_run or settings.tts_engine), "engine": settings.tts_engine},
        "avatar_render_engine_ready": {"ready": True, "engine": "static"},
        "lip_sync_engine_ready": {"ready": True, "engines": ["hifly", "tavus", "baidu_xiling", "omnihuman", "syncso", "latentsync", "musetalk", "yywav2lip", "wav2lip", "none"]},
        "final_assembly_ready": {"ready": True, "engine": "video_template_ffmpeg_dryrun"},
        "jianying_ready": {"ready": settings.dry_run or bool(settings.jianying_draft_root)},
        "duix_http": {"ready": False, "policy": "HTTP only; source vendoring requires explicit approval"},
        "wav2lip_source": wav2lip_status["source"],
        "wav2lip_checkpoint": wav2lip_status["checkpoint"],
        "yywav2lip_checkpoint": yywav2lip_status["checkpoint"],
        "yywav2lip_role_model": yywav2lip_status["role_model_dir"],
        "cloud_lipsync": cloud_lipsync_status,
        "syncso_cloud": syncso_status,
        "pixverse_cloud": cloud_lipsync_status if cloud_lipsync_status.get("provider") == "pixverse" else _cloud_lipsync_adapter(settings.model_copy(update={"cloud_lipsync_provider": "pixverse"})).readiness(),
        "cloud_voice_providers": cloud_voice,
        "cloud_video_providers": cloud_video,
        "omnihuman_cloud": omnihuman_status,
        "tavus_cloud": tavus_status,
        "baidu_xiling_cloud": baidu_xiling_status,
        "hifly_cloud": hifly_status,
        "role_model_ready": {
            "ready": bool(settings.dry_run),
            "policy": "project role models are validated per digital human",
        },
    }


@app.post("/tasks", response_model=TaskResponse)
def create_task(request: CreateVideoTaskRequest, store: TaskStore = Depends(get_store)) -> TaskResponse:
    task = store.create(request)
    return TaskResponse(task_id=task.task_id, status=task.status, artifacts=task.artifacts, error=task.error)


@app.get("/tasks/running")
def list_running_tasks(store: TaskStore = Depends(get_store)) -> dict[str, object]:
    tasks = store.running_tasks()
    return {
        "tasks": [
            {
                "task_id": task.task_id,
                "status": task.status.value,
                "project_id": task.request.project_id,
                "topic": task.request.topic,
            }
            for task in tasks
        ]
    }


@app.get("/video-remix/main-videos")
def list_video_remix_main_videos(
    project_id: str | None = None,
    settings: Settings = Depends(get_settings),
) -> dict[str, list[dict[str, str]]]:
    artifact_names = ["final_video"]
    artifact_labels = {
        "final_video": "最终成片",
    }
    items: list[dict[str, str]] = []
    for task_json in sorted((settings.storage_dir / "tasks").glob("*/task.json"), reverse=True):
        if len(items) >= 50:
            break
        try:
            task_payload = read_json(task_json)
        except Exception:
            continue
        request_payload = task_payload.get("request") if isinstance(task_payload.get("request"), dict) else {}
        task_project_id = request_payload.get("project_id")
        if project_id and task_project_id != project_id:
            continue
        artifacts = task_payload.get("artifacts") if isinstance(task_payload.get("artifacts"), dict) else {}
        task_id = str(task_payload.get("task_id") or task_json.parent.name)
        script_text = _task_script_text_for_remix(task_payload)
        for artifact in artifact_names:
            path = _safe_storage_file(settings, artifacts.get(artifact))
            if not path:
                continue
            script_preview = script_text[:80] + ("..." if len(script_text) > 80 else "")
            items.append(
                {
                    "id": f"{task_id}:{artifact}",
                    "label": f"{task_id} / {artifact}",
                    "display_name": f"成片视频 {len(items) + 1}",
                    "kind_label": artifact_labels.get(artifact, "成片视频"),
                    "script_text": script_text,
                    "script_preview": script_preview,
                    "path": str(path),
                    "preview_url": f"/video-remix/main-video-preview?path={quote(str(path), safe='')}",
                    "artifact": artifact,
                }
            )
            break
    return {"videos": items}


def _task_script_text_for_remix(task_payload: dict[str, object]) -> str:
    request_payload = task_payload.get("request") if isinstance(task_payload.get("request"), dict) else {}
    for key in ("fixed_script", "topic"):
        value = request_payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _find_remix_script_text_for_video(settings: Settings, video_path: Path) -> str:
    try:
        target = video_path.resolve()
    except OSError:
        target = video_path
    for task_json in sorted((settings.storage_dir / "tasks").glob("*/task.json"), reverse=True):
        try:
            task_payload = read_json(task_json)
        except Exception:
            continue
        artifacts = task_payload.get("artifacts") if isinstance(task_payload.get("artifacts"), dict) else {}
        final_video = _safe_storage_file(settings, artifacts.get("final_video"))
        if not final_video:
            continue
        try:
            final_video_resolved = final_video.resolve()
        except OSError:
            final_video_resolved = final_video
        if final_video_resolved == target:
            return _task_script_text_for_remix(task_payload)
    return ""


def _video_remix_output_url(path: Path) -> str:
    return f"/video-remix/output-preview?path={quote(str(path), safe='')}"


def _subtitle_alignment_payload(result: object | None) -> dict[str, object] | None:
    if result is None:
        return None
    return {
        "status": getattr(result, "status", ""),
        "engine": getattr(result, "engine", ""),
        "model": getattr(result, "model", ""),
        "message": getattr(result, "message", ""),
        "transcript_path": str(getattr(result, "transcript_path", "")),
        "segments_path": str(getattr(result, "segments_path", "")),
    }


@app.get("/video-remix/main-video-preview")
def preview_video_remix_main_video(
    path: str,
    settings: Settings = Depends(get_settings),
) -> FileResponse:
    video_path = _safe_storage_file(settings, path)
    if not video_path:
        raise HTTPException(status_code=404, detail="选择的口播主视频不可用，请重新选择或上传。")
    return FileResponse(video_path, media_type="video/mp4")


@app.get("/video-remix/output-preview")
def preview_video_remix_output(
    path: str,
    download: bool = False,
    settings: Settings = Depends(get_settings),
) -> FileResponse:
    video_path = _safe_storage_file(settings, path)
    if not video_path:
        raise HTTPException(status_code=404, detail="混剪结果视频不可用，请重新生成。")
    filename = video_path.name if download else None
    return FileResponse(video_path, media_type="video/mp4", filename=filename)


@app.post("/video-remix/tasks", response_model=VideoRemixTaskResponse)
def create_video_remix_task(
    request: VideoRemixTaskRequest,
    settings: Settings = Depends(get_settings),
) -> VideoRemixTaskResponse:
    if not request.main_video_path and not request.main_video:
        raise HTTPException(status_code=400, detail="请先选择或上传口播主视频。")
    if not request.assets and not request.add_subtitles and not request.add_background_music:
        raise HTTPException(status_code=400, detail="请先上传至少一个产品图或素材视频。")

    remix_task_id = "remix_" + uuid4().hex
    task_dir = ensure_dir(settings.storage_dir / "video_remix_tasks" / remix_task_id)
    main_dir = ensure_dir(task_dir / "main")
    assets_dir = ensure_dir(task_dir / "assets")

    if request.main_video:
        main_video_path = _write_remix_upload(request.main_video, main_dir, allowed_prefixes=("video/",))
    else:
        main_video_path = _safe_storage_file(settings, request.main_video_path)
        if not main_video_path:
            raise HTTPException(status_code=400, detail="选择的口播主视频不可用，请重新选择或上传。")

    asset_paths = [
        _write_remix_upload(asset, assets_dir, allowed_prefixes=("image/", "video/"))
        for asset in request.assets
    ]
    background_music_track = _bgm_track(request.background_music_id) if request.add_background_music else None
    background_music_path = _bgm_track_path(background_music_track) if background_music_track else None
    if request.add_background_music and not background_music_path:
        raise HTTPException(status_code=400, detail="请选择可用的背景音乐。")
    created_at = datetime.now(timezone.utc).isoformat()
    request_payload = request.model_dump(mode="json")
    write_json(task_dir / "request.json", request_payload)
    resolved_subtitle_text = (request.subtitle_text or "").strip()
    if request.add_subtitles and not resolved_subtitle_text and not request.main_video:
        resolved_subtitle_text = _find_remix_script_text_for_video(settings, main_video_path)

    subtitle_alignment = None
    try:
        if request.add_subtitles and request.use_smart_subtitles:
            subtitle_alignment = align_video_subtitles(
                video_path=main_video_path,
                out_dir=ensure_dir(task_dir / "work"),
                settings=settings,
                fallback_text=resolved_subtitle_text,
            )
        render_result = LocalFFmpegVideoRemixEngine(ffmpeg_path=settings.reference_ffmpeg_path).render(
            main_video=main_video_path,
            assets=asset_paths,
            out_dir=task_dir,
            output_count=request.output_count,
            add_subtitles=request.add_subtitles,
            subtitle_text=resolved_subtitle_text,
            subtitle_cues=subtitle_alignment.cues if subtitle_alignment else None,
            subtitle_style=request.subtitle_style.model_dump(mode="json"),
            background_music=background_music_path,
            background_music_volume=request.background_music_volume,
        )
    except (VideoRemixError, AdapterError) as exc:
        failed_payload = {
            "remix_task_id": remix_task_id,
            "status": "failed",
            "message": str(exc),
            "project_id": request.project_id,
            "main_video": str(main_video_path),
            "assets": [str(path) for path in asset_paths],
            "output_count": request.output_count,
            "add_subtitles": request.add_subtitles,
            "use_smart_subtitles": request.use_smart_subtitles,
            "subtitle_text": resolved_subtitle_text,
            "subtitle_style": request.subtitle_style.model_dump(mode="json"),
            "subtitle_alignment": _subtitle_alignment_payload(subtitle_alignment),
            "add_background_music": request.add_background_music,
            "background_music_id": request.background_music_id,
            "background_music_title": background_music_track.get("title_cn") if background_music_track else None,
            "background_music_volume": request.background_music_volume,
            "defaults": {
                "render_engine": "ffmpeg_local",
                "create_placeholder_output": False,
            },
            "created_at": created_at,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        write_json(task_dir / "status.json", failed_payload)
        append_audit_event(
            settings.storage_dir,
            action="video_remix.task_failed",
            project_id=request.project_id,
            details={"remix_task_id": remix_task_id, "error": str(exc)},
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    output_urls = [_video_remix_output_url(path) for path in render_result.outputs]
    message = f"本地混剪已生成 {len(render_result.outputs)} 条视频。"
    status_payload = {
        "remix_task_id": remix_task_id,
        "status": "completed",
        "message": message,
        "project_id": request.project_id,
        "main_video": str(main_video_path),
        "assets": [str(path) for path in asset_paths],
        "output_count": request.output_count,
        "outputs": [str(path) for path in render_result.outputs],
        "output_urls": output_urls,
        "report_path": str(render_result.report_path),
        "add_subtitles": request.add_subtitles,
        "use_smart_subtitles": request.use_smart_subtitles,
        "subtitle_text": resolved_subtitle_text,
        "subtitle_style": request.subtitle_style.model_dump(mode="json"),
        "subtitle_alignment": _subtitle_alignment_payload(subtitle_alignment),
        "add_background_music": request.add_background_music,
        "background_music_id": request.background_music_id,
        "background_music_title": background_music_track.get("title_cn") if background_music_track else None,
        "background_music_volume": request.background_music_volume,
        "defaults": {
            "render_engine": "ffmpeg_local",
            "create_placeholder_output": False,
        },
        "created_at": created_at,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    write_json(task_dir / "status.json", status_payload)
    append_audit_event(
        settings.storage_dir,
        action="video_remix.task_completed",
        project_id=request.project_id,
        details={
            "remix_task_id": remix_task_id,
            "asset_count": len(asset_paths),
            "output_count": request.output_count,
            "outputs": [str(path) for path in render_result.outputs],
        },
    )
    return VideoRemixTaskResponse(
        remix_task_id=remix_task_id,
        status="completed",
        message=message,
        task_dir=str(task_dir),
        main_video_path=str(main_video_path),
        asset_count=len(asset_paths),
        output_count=request.output_count,
        outputs=[str(path) for path in render_result.outputs],
        output_urls=output_urls,
        report_path=str(render_result.report_path),
        add_subtitles=request.add_subtitles,
        use_smart_subtitles=request.use_smart_subtitles,
        subtitle_text=resolved_subtitle_text,
        subtitle_style=request.subtitle_style,
        add_background_music=request.add_background_music,
        background_music_id=request.background_music_id,
        background_music_title=background_music_track.get("title_cn") if background_music_track else None,
        background_music_volume=request.background_music_volume,
    )


@app.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: str, store: TaskStore = Depends(get_store)) -> TaskResponse:
    try:
        task = store.get(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return TaskResponse(task_id=task.task_id, status=task.status, artifacts=task.artifacts, error=task.error)


@app.post("/tasks/{task_id}/run", response_model=TaskResponse)
async def run_task(
    task_id: str,
    store: TaskStore = Depends(get_store),
    pipeline: VideoPipeline = Depends(get_pipeline),
) -> TaskResponse:
    try:
        task = store.get(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    task = await pipeline.run(task)
    return TaskResponse(task_id=task.task_id, status=task.status, artifacts=task.artifacts, error=task.error)


@app.post("/tasks/{task_id}/run-async", response_model=JobRecord)
def enqueue_task_run(
    task_id: str,
    request: EnqueueJobRequest | None = None,
    store: TaskStore = Depends(get_store),
    job_queue: LocalJobQueue = Depends(get_job_queue),
) -> JobRecord:
    run_request = request or EnqueueJobRequest()
    try:
        task = store.get(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return job_queue.enqueue(
        kind=JobKind.render_task,
        payload={
            "task_id": task.task_id,
            "project_id": task.request.project_id,
            "digital_human_id": task.request.digital_human_id,
        },
        max_retries=run_request.max_retries,
        metadata=run_request.metadata,
    )


@app.get("/tasks/{task_id}/artifacts")
def get_artifacts(task_id: str, store: TaskStore = Depends(get_store)) -> dict[str, object]:
    try:
        task = store.get(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    task_dir = store.task_dir(task_id)
    if task_dir.exists():
        manifest = write_artifact_manifest(task_dir)
        task.artifacts.artifact_manifest = str(manifest)
        store.save(task)
    payload = task.artifacts.model_dump()
    payload["items"] = artifact_items(task_dir)
    return payload


@app.get("/tasks/{task_id}/artifacts.zip")
def get_artifacts_zip(task_id: str, store: TaskStore = Depends(get_store)) -> FileResponse:
    try:
        store.get(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    zip_path = build_artifacts_zip(store.task_dir(task_id))
    return FileResponse(zip_path, filename=f"{task_id}_artifacts.zip", media_type="application/zip")


@app.get("/tasks/{task_id}/progress")
def task_progress(task_id: str, store: TaskStore = Depends(get_store)) -> dict[str, object]:
    try:
        task = store.get(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "task_id": task.task_id,
        "status": task.status,
        "error": task.error,
        "steps": [step.model_dump(mode="json") for step in task.steps],
        "artifacts": task.artifacts.model_dump(),
        "updated_at": task.updated_at.isoformat(),
    }


@app.get("/tasks/{task_id}/logs", response_class=PlainTextResponse)
def task_logs(task_id: str, store: TaskStore = Depends(get_store)) -> PlainTextResponse:
    try:
        task = store.get(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    log_path = Path(task.artifacts.logs or store.task_dir(task_id) / "pipeline.log")
    if not log_path.is_absolute():
        log_path = store.settings.storage_dir.parent / log_path
    fallback = store.task_dir(task_id) / "pipeline.log"
    if not log_path.exists() and fallback.exists():
        log_path = fallback
    if not log_path.exists():
        raise HTTPException(status_code=404, detail="task log not generated yet")
    return PlainTextResponse(log_path.read_text(encoding="utf-8"), media_type="text/plain")


@app.get("/tasks/{task_id}/script")
def task_script(task_id: str, store: TaskStore = Depends(get_store)) -> dict[str, object]:
    try:
        task = store.get(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    script_path = Path(task.artifacts.script_json or store.task_dir(task_id) / "script.json")
    if not script_path.exists():
        raise HTTPException(status_code=404, detail="script not generated yet")
    subtitles_path = Path(task.artifacts.subtitles_srt or store.task_dir(task_id) / "subtitles.srt")
    return {
        "task_id": task_id,
        "script_json": read_json(script_path),
        "subtitles": subtitles_path.read_text(encoding="utf-8") if subtitles_path.exists() else "",
    }


@app.get("/tasks/{task_id}/download/final-video")
def download_final_video(task_id: str, store: TaskStore = Depends(get_store)) -> FileResponse:
    task = _get_task_or_404(task_id, store)
    path = Path(task.artifacts.final_video or store.task_dir(task_id) / "final.mp4")
    return _file_response_or_404(path, filename="final.mp4", media_type="video/mp4")


@app.get("/tasks/{task_id}/download/voice")
def download_task_voice(task_id: str, store: TaskStore = Depends(get_store)) -> FileResponse:
    task = _get_task_or_404(task_id, store)
    path = Path(task.artifacts.voice_audio or store.task_dir(task_id) / "voice.wav")
    return _file_response_or_404(path, filename="voice.wav", media_type="audio/wav")


@app.get("/tasks/{task_id}/download/jianying-draft")
def download_jianying_draft(task_id: str, store: TaskStore = Depends(get_store)) -> FileResponse:
    task = _get_task_or_404(task_id, store)
    draft_dir = Path(task.artifacts.jianying_draft or store.task_dir(task_id) / "jianying_draft")
    if not draft_dir.exists() or not draft_dir.is_dir():
        raise HTTPException(status_code=404, detail="jianying draft not generated yet")
    zip_path = store.task_dir(task_id) / "jianying_draft.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(draft_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(draft_dir).as_posix())
    return FileResponse(zip_path, filename=f"{task_id}_jianying_draft.zip", media_type="application/zip")


@app.get("/tasks/{task_id}/download/publish-package")
def download_publish_package(task_id: str, store: TaskStore = Depends(get_store)) -> dict[str, object]:
    task = _get_task_or_404(task_id, store)
    path = Path(task.artifacts.publish_package or store.task_dir(task_id) / "publish_package.json")
    if not path.exists():
        raise HTTPException(status_code=404, detail="publish package not generated yet")
    return read_json(path)


@app.get("/tasks/{task_id}/download/quality-reports")
def download_quality_reports(task_id: str, store: TaskStore = Depends(get_store)) -> FileResponse:
    task = _get_task_or_404(task_id, store)
    task_dir = store.task_dir(task.task_id)
    report_names = [
        "script_quality_report.json",
        "audio_quality_report.json",
        "avatar_render_report.json",
        "lip_sync_report.json",
        "render_stability_report.json",
        "digital_human_quality_report.json",
        "template_report.json",
    ]
    available = [task_dir / name for name in report_names if (task_dir / name).exists()]
    if not available:
        raise HTTPException(status_code=404, detail="quality reports not generated yet")
    zip_path = task_dir / "quality_reports.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in available:
            archive.write(path, path.name)
    return FileResponse(zip_path, filename=f"{task_id}_quality_reports.zip", media_type="application/zip")


@app.get("/tasks/{task_id}/quality-summary", response_model=QualityMetricSummary)
def task_quality_summary(
    task_id: str,
    quality_center: QualityCenter = Depends(get_quality_center),
) -> QualityMetricSummary:
    try:
        return quality_center.task_summary(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/quality/dashboard", response_model=QualityDashboard)
def quality_dashboard(quality_center: QualityCenter = Depends(get_quality_center)) -> QualityDashboard:
    return quality_center.dashboard()


@app.post("/quality/benchmarks/run", response_model=BenchmarkReport)
async def run_quality_benchmark(
    request: RunBenchmarkRequest | None = None,
    quality_center: QualityCenter = Depends(get_quality_center),
) -> BenchmarkReport:
    return await quality_center.run_benchmark(request or RunBenchmarkRequest())


@app.get("/quality/benchmarks/{benchmark_id}", response_model=BenchmarkReport)
def get_quality_benchmark(
    benchmark_id: str,
    quality_center: QualityCenter = Depends(get_quality_center),
) -> BenchmarkReport:
    path = quality_center.benchmark_report_path(benchmark_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"benchmark report not found: {benchmark_id}")
    return BenchmarkReport.model_validate(read_json(path))


@app.get("/quality/benchmarks/{benchmark_id}/download.json")
def download_quality_benchmark_report(
    benchmark_id: str,
    quality_center: QualityCenter = Depends(get_quality_center),
) -> FileResponse:
    path = quality_center.benchmark_report_path(benchmark_id)
    return _file_response_or_404(path, filename=f"{benchmark_id}_benchmark_report.json", media_type="application/json")


@app.get("/jobs")
def list_jobs(
    status: JobStatus | None = None,
    job_queue: LocalJobQueue = Depends(get_job_queue),
) -> dict[str, object]:
    return {"jobs": [job.model_dump(mode="json") for job in job_queue.list(status=status)]}


@app.post("/jobs/worker/run-next", response_model=JobRecord)
async def run_next_job(job_queue: LocalJobQueue = Depends(get_job_queue)) -> JobRecord:
    try:
        return await job_queue.run_next()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/jobs/{job_id}", response_model=JobRecord)
def get_job(job_id: str, job_queue: LocalJobQueue = Depends(get_job_queue)) -> JobRecord:
    try:
        return job_queue.get(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/jobs/{job_id}/logs", response_class=PlainTextResponse)
def get_job_logs(job_id: str, job_queue: LocalJobQueue = Depends(get_job_queue)) -> PlainTextResponse:
    try:
        job = job_queue.get(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    log_path = Path(job.logs_path or job_queue.log_file(job_id))
    text = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    return PlainTextResponse(text)


@app.post("/jobs/{job_id}/retry", response_model=JobRecord)
def retry_job(job_id: str, job_queue: LocalJobQueue = Depends(get_job_queue)) -> JobRecord:
    try:
        return job_queue.retry(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/jobs/{job_id}/cancel", response_model=JobRecord)
def cancel_job(job_id: str, job_queue: LocalJobQueue = Depends(get_job_queue)) -> JobRecord:
    try:
        return job_queue.cancel(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/tasks/{task_id}/publish/queue", response_model=PublishQueueItem)
def create_publish_queue_item(
    task_id: str,
    request: CreatePublishQueueItemRequest,
    publish_store: PublishConsoleStore = Depends(get_publish_console_store),
    store: TaskStore = Depends(get_store),
) -> PublishQueueItem:
    try:
        return publish_store.create_from_task(task_id, request, store)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/publish/queue")
def list_publish_queue(publish_store: PublishConsoleStore = Depends(get_publish_console_store)) -> dict[str, object]:
    return {"items": [item.model_dump(mode="json") for item in publish_store.list()]}


@app.get("/publish/board")
def publish_board(publish_store: PublishConsoleStore = Depends(get_publish_console_store)) -> dict[str, object]:
    return {"columns": publish_store.board()}


@app.get("/publish/calendar")
def publish_calendar(publish_store: PublishConsoleStore = Depends(get_publish_console_store)) -> dict[str, object]:
    return {"items": publish_store.calendar()}


@app.get("/publish/queue/{queue_id}", response_model=PublishQueueItem)
def get_publish_queue_item(
    queue_id: str,
    publish_store: PublishConsoleStore = Depends(get_publish_console_store),
) -> PublishQueueItem:
    try:
        return publish_store.get(queue_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/publish/accounts/{platform}/open-login")
def open_publish_account_login(
    platform: str,
    automation: PublishBrowserAutomation = Depends(get_publish_browser_automation),
) -> dict[str, object]:
    try:
        _require_publish_automation_supported(platform)
        return automation.open_login(platform)
    except (ValueError, PublishBrowserAutomationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/publish/queue/{queue_id}/automation/start")
def start_publish_automation(
    queue_id: str,
    publish_store: PublishConsoleStore = Depends(get_publish_console_store),
    store: TaskStore = Depends(get_store),
    automation: PublishBrowserAutomation = Depends(get_publish_browser_automation),
) -> dict[str, object]:
    try:
        item = publish_store.get(queue_id)
        _require_publish_automation_supported(item.platform)
        final_video_path = _publish_final_video_path(item, store)
        result = automation.start(item, final_video_path)
        item = _save_publish_automation_result(publish_store, item, result)
        append_audit_event(
            publish_store.settings.storage_dir,
            action="publish.browser_automation_started",
            task_id=item.task_id,
            project_id=item.project_id,
            digital_human_id=item.digital_human_id,
            details={"queue_id": queue_id, "platform": item.platform, "status": result.get("status")},
        )
        return item.metadata["browser_publish"]
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, PublishBrowserAutomationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/publish/queue/{queue_id}/automation")
def get_publish_automation_status(
    queue_id: str,
    publish_store: PublishConsoleStore = Depends(get_publish_console_store),
    automation: PublishBrowserAutomation = Depends(get_publish_browser_automation),
) -> dict[str, object]:
    try:
        item = publish_store.get(queue_id)
        return automation.status(item)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/publish/queue/{queue_id}/automation/confirm-final")
def confirm_publish_automation_final(
    queue_id: str,
    publish_store: PublishConsoleStore = Depends(get_publish_console_store),
    automation: PublishBrowserAutomation = Depends(get_publish_browser_automation),
) -> dict[str, object]:
    try:
        item = publish_store.get(queue_id)
        _require_publish_automation_supported(item.platform)
        result = automation.confirm_final(item)
        item = _save_publish_automation_result(publish_store, item, result)
        append_audit_event(
            publish_store.settings.storage_dir,
            action="publish.browser_automation_confirmed",
            task_id=item.task_id,
            project_id=item.project_id,
            digital_human_id=item.digital_human_id,
            details={"queue_id": queue_id, "platform": item.platform, "status": result.get("status")},
        )
        return item.metadata["browser_publish"]
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PublishBrowserAutomationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch("/publish/queue/{queue_id}", response_model=PublishQueueItem)
def patch_publish_queue_item(
    queue_id: str,
    request: PatchPublishQueueItemRequest,
    publish_store: PublishConsoleStore = Depends(get_publish_console_store),
) -> PublishQueueItem:
    try:
        return publish_store.patch(queue_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/publish/queue/{queue_id}/handoff.zip")
def download_publish_handoff_zip(
    queue_id: str,
    publish_store: PublishConsoleStore = Depends(get_publish_console_store),
    store: TaskStore = Depends(get_store),
) -> FileResponse:
    try:
        zip_path = publish_store.build_handoff_zip(queue_id, store)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(zip_path, filename=f"{queue_id}_handoff.zip", media_type="application/zip")


def _publish_final_video_path(item: PublishQueueItem, store: TaskStore) -> Path:
    task_dir = store.task_dir(item.task_id)
    candidates: list[Path] = []
    artifact_path = (item.artifacts or {}).get("final_video")
    if artifact_path:
        candidates.append(Path(str(artifact_path)))
    candidates.append(task_dir / "final.mp4")
    for path in candidates:
        if not path.is_absolute():
            path = Path.cwd() / path
        if path.exists() and path.is_file():
            return path
    raise ValueError("未找到可发布的成片 MP4，请先完成视频生成。")


def _require_publish_automation_supported(platform: str) -> None:
    value = (platform or "douyin").strip().lower()
    value = {"wechat_channels": "shipinhao", "video_account": "shipinhao"}.get(value, value)
    if value not in {"douyin", "xiaohongshu", "shipinhao"}:
        labels = {
            "xiaohongshu": "小红书",
            "kuaishou": "快手",
            "shipinhao": "视频号",
            "tiktok": "TikTok",
        }
        raise ValueError(f"{labels.get(value, value)}浏览器自动发布待接入，当前支持抖音、小红书、视频号。")


def _save_publish_automation_result(
    publish_store: PublishConsoleStore,
    item: PublishQueueItem,
    result: dict[str, object],
) -> PublishQueueItem:
    item.metadata["browser_publish"] = result
    status = str(result.get("status") or "")
    if status == "published":
        item.status = PublishStatus.published
        item.reviewed_at = item.reviewed_at or datetime.now(timezone.utc).isoformat()
        external_url = result.get("external_url")
        if external_url:
            item.external_url = str(external_url)
    elif status == "failed":
        item.status = PublishStatus.failed
        item.failure_reason = str(result.get("message") or "浏览器自动发布失败")
    elif status == "awaiting_final_confirmation":
        item.handoff_policy = "browser_assisted_requires_user_confirmation"
    publish_store.save(item)
    return item


@app.post("/projects")
def create_project(
    request: CreateProjectRequest,
    settings: Settings = Depends(get_settings),
    project_store: ProjectStore = Depends(get_project_store),
) -> dict[str, object]:
    project = project_store.create(request)
    append_audit_event(
        settings.storage_dir,
        action="project.created",
        project_id=request.project_id,
        details={"name": request.name},
    )
    return project


@app.get("/projects")
def list_projects(project_store: ProjectStore = Depends(get_project_store)) -> dict[str, object]:
    return {"projects": project_store.list()}


@app.post("/projects/{project_id}/export")
def export_project(
    project_id: str,
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    try:
        return export_project_package(settings, project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/projects/import")
def import_project(
    request: ProjectImportRequest,
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    try:
        return import_project_package(settings, Path(request.package_path), project_id=request.project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/projects/{project_id}/campaigns", response_model=Campaign)
def create_campaign(
    project_id: str,
    request: CreateCampaignRequest,
    campaign_store: CampaignStore = Depends(get_campaign_store),
) -> Campaign:
    try:
        return campaign_store.create(project_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/campaigns/{campaign_id}", response_model=Campaign)
def get_campaign(
    campaign_id: str,
    campaign_store: CampaignStore = Depends(get_campaign_store),
) -> Campaign:
    try:
        return campaign_store.get(campaign_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/campaigns/{campaign_id}/run", response_model=Campaign)
async def run_campaign(
    campaign_id: str,
    request: CampaignRunRequest | None = None,
    campaign_store: CampaignStore = Depends(get_campaign_store),
    store: TaskStore = Depends(get_store),
    pipeline: VideoPipeline = Depends(get_pipeline),
) -> Campaign:
    run_request = request or CampaignRunRequest()
    try:
        return await campaign_store.run(
            campaign_id,
            retry_failed=run_request.retry_failed,
            force=run_request.force,
            task_store=store,
            pipeline=pipeline,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/campaigns/{campaign_id}/run-async", response_model=JobRecord)
def enqueue_campaign_run(
    campaign_id: str,
    request: EnqueueJobRequest | None = None,
    campaign_store: CampaignStore = Depends(get_campaign_store),
    job_queue: LocalJobQueue = Depends(get_job_queue),
) -> JobRecord:
    run_request = request or EnqueueJobRequest()
    try:
        campaign = campaign_store.get(campaign_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return job_queue.enqueue(
        kind=JobKind.campaign_run,
        payload={
            "campaign_id": campaign.campaign_id,
            "project_id": campaign.project_id,
            "digital_human_id": campaign.digital_human_id,
            "retry_failed": run_request.retry_failed,
            "force": run_request.force,
        },
        max_retries=run_request.max_retries,
        metadata=run_request.metadata,
    )


@app.get("/campaigns/{campaign_id}/tasks")
def get_campaign_tasks(
    campaign_id: str,
    campaign_store: CampaignStore = Depends(get_campaign_store),
    store: TaskStore = Depends(get_store),
) -> dict[str, object]:
    try:
        campaign = campaign_store.get(campaign_id)
        return {"campaign_id": campaign_id, "status": campaign.status, "tasks": campaign_store.task_rows(campaign_id, store)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/campaigns/{campaign_id}/download.zip")
def download_campaign_zip(
    campaign_id: str,
    campaign_store: CampaignStore = Depends(get_campaign_store),
    store: TaskStore = Depends(get_store),
) -> FileResponse:
    try:
        zip_path = campaign_store.build_download_zip(campaign_id, store)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(zip_path, filename=f"{campaign_id}_results.zip", media_type="application/zip")


@app.post("/projects/{project_id}/references", response_model=ReferenceVideo)
def create_reference_video(
    project_id: str,
    request: CreateReferenceVideoRequest,
    settings: Settings = Depends(get_settings),
    reference_store: ReferenceVideoStore = Depends(get_reference_video_store),
) -> ReferenceVideo:
    try:
        reference = reference_store.create(project_id, request)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    append_audit_event(
        settings.storage_dir,
        action="reference.created",
        project_id=project_id,
        details={"reference_id": reference.reference_id, "asset_id": reference.asset_id},
    )
    return reference


@app.get("/projects/{project_id}/references", response_model=list[ReferenceVideo])
def list_reference_videos(
    project_id: str,
    reference_store: ReferenceVideoStore = Depends(get_reference_video_store),
) -> list[ReferenceVideo]:
    return reference_store.list_for_project(project_id)


@app.post("/projects/{project_id}/reference-links/collect", response_model=ReferenceContentCapture)
def collect_project_reference_link(
    project_id: str,
    request: CollectReferenceLinkRequest,
    settings: Settings = Depends(get_settings),
    collector: ReferenceContentCollector = Depends(get_reference_content_collector),
) -> ReferenceContentCapture:
    try:
        capture = collector.collect(project_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    append_audit_event(
        settings.storage_dir,
        action="reference_link.collected",
        project_id=project_id,
        details={
            "collection_id": capture.collection_id,
            "platform": capture.platform,
            "status": capture.status,
            "source_url": capture.source_url,
        },
    )
    return capture


@app.post("/projects/{project_id}/reference-links/parse", response_model=VideoParserResult)
def parse_project_reference_link(
    project_id: str,
    request: CollectReferenceLinkRequest,
    settings: Settings = Depends(get_settings),
) -> VideoParserResult:
    platform = ReferenceContentCollector.detect_platform(request.url)
    adapter = LocalVideoParserAdapter(
        enabled=settings.video_parser_enabled,
        ytdlp_path=settings.video_parser_ytdlp_path,
        douyin_downloader_root=settings.video_parser_douyin_downloader_root,
        download_dir=settings.storage_dir / "projects" / project_id / "reference_collections" / "_link_parse",
        timeout_seconds=settings.video_parser_timeout_seconds,
        max_download_mb=settings.video_parser_max_download_mb,
        engine=settings.video_parser_engine,
        python_executable=settings.python_path,
        cloud_provider_order=settings.video_parser_cloud_provider_order,
        aivo_parser_base_url=settings.aivo_parser_base_url,
        aivo_parser_endpoint=settings.aivo_parser_endpoint,
        aivo_parser_token=settings.aivo_parser_token,
        tikhub_base_url=settings.tikhub_base_url,
        tikhub_api_key=settings.tikhub_api_key,
        tikhub_endpoint=settings.tikhub_douyin_endpoint,
        istero_base_url=settings.istero_base_url,
        istero_api_key=settings.istero_api_key,
        istero_endpoint=settings.istero_douyin_endpoint,
        evil0ctal_base_url=settings.evil0ctal_douyin_api_base_url,
        evil0ctal_endpoint=settings.evil0ctal_douyin_api_endpoint,
    )
    result = adapter.parse(request.url, platform=platform)
    append_audit_event(
        settings.storage_dir,
        action="reference_link.parsed",
        project_id=project_id,
        details={
            "platform": result.platform,
            "status": result.status,
            "engine": result.engine,
            "source_url": result.source_url,
            "downloadable": result.downloadable,
        },
    )
    return result


@app.post("/projects/{project_id}/reference-links/transcribe", response_model=ReferenceLinkTranscriptionResult)
def transcribe_project_reference_link(
    project_id: str,
    request: TranscribeReferenceLinkRequest,
    settings: Settings = Depends(get_settings),
    service: ReferenceLinkTranscriptionService = Depends(get_reference_link_transcription_service),
) -> ReferenceLinkTranscriptionResult:
    result = service.transcribe(project_id, request)
    append_audit_event(
        settings.storage_dir,
        action="reference_link.transcribed",
        project_id=project_id,
        details={
            "collection_id": result.collection_id,
            "reference_id": result.reference_id,
            "platform": result.platform,
            "status": result.status,
            "source_url": result.source_url,
        },
    )
    return result


@app.post("/projects/{project_id}/reference-links/download-watch/start", response_model=ReferenceDownloadWatchStatus)
def start_project_reference_download_watch(
    project_id: str,
    request: ReferenceDownloadWatchStartRequest,
    settings: Settings = Depends(get_settings),
    service: ReferenceLinkTranscriptionService = Depends(get_reference_link_transcription_service),
) -> ReferenceDownloadWatchStatus:
    watcher = ReferenceDownloadWatchService(settings, transcription_service=service)
    try:
        result = watcher.start(project_id, request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=f"下载目录不可用：{exc}") from exc
    append_audit_event(
        settings.storage_dir,
        action="reference_link.download_watch_started",
        project_id=project_id,
        details={
            "watch_id": result.watch_id,
            "platform": result.platform,
            "source_url": result.source_url,
            "download_dir": result.download_dir,
        },
    )
    return result


@app.get(
    "/projects/{project_id}/reference-links/download-watch/{watch_id}",
    response_model=ReferenceDownloadWatchStatus,
)
def get_project_reference_download_watch(
    project_id: str,
    watch_id: str,
    settings: Settings = Depends(get_settings),
    service: ReferenceLinkTranscriptionService = Depends(get_reference_link_transcription_service),
) -> ReferenceDownloadWatchStatus:
    watcher = ReferenceDownloadWatchService(settings, transcription_service=service)
    try:
        result = watcher.poll(project_id, watch_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    append_audit_event(
        settings.storage_dir,
        action="reference_link.download_watch_polled",
        project_id=project_id,
        details={
            "watch_id": result.watch_id,
            "platform": result.platform,
            "status": result.status,
            "candidate_path": result.candidate_path,
            "reference_id": result.result.reference_id if result.result else None,
        },
    )
    return result


@app.post("/references/{reference_id}/analyze", response_model=ReferenceVideo)
def analyze_reference_video(
    reference_id: str,
    request: AnalyzeReferenceVideoRequest | None = None,
    settings: Settings = Depends(get_settings),
    reference_store: ReferenceVideoStore = Depends(get_reference_video_store),
) -> ReferenceVideo:
    try:
        reference = reference_store.analyze(reference_id, request or AnalyzeReferenceVideoRequest())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    append_audit_event(
        settings.storage_dir,
        action="reference.analyzed",
        project_id=reference.project_id,
        details={"reference_id": reference.reference_id, "status": reference.status},
    )
    return reference


@app.get("/references/{reference_id}/analysis")
def get_reference_analysis(
    reference_id: str,
    reference_store: ReferenceVideoStore = Depends(get_reference_video_store),
) -> dict[str, object]:
    try:
        return reference_store.analysis_payload(reference_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/references/{reference_id}/rewrite")
def rewrite_reference_scripts(
    reference_id: str,
    request: RewriteScriptRequest,
    settings: Settings = Depends(get_settings),
    rewrite_store: ScriptRewriteStore = Depends(get_script_rewrite_store),
) -> dict[str, object]:
    if request.reference_id != reference_id:
        raise HTTPException(status_code=400, detail="request.reference_id must match path reference_id")
    try:
        rewrite = rewrite_store.rewrite(reference_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AdapterError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    append_audit_event(
        settings.storage_dir,
        action="reference.rewritten",
        project_id=rewrite.project_id,
        details={"reference_id": reference_id, "rewrite_id": rewrite.rewrite_id, "count": len(rewrite.scripts)},
    )
    return _rewrite_response(rewrite)


@app.get("/references/{reference_id}/rewrites")
def list_reference_rewrites(
    reference_id: str,
    rewrite_store: ScriptRewriteStore = Depends(get_script_rewrite_store),
) -> dict[str, object]:
    try:
        rewrites = rewrite_store.list_for_reference(reference_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"reference_id": reference_id, "rewrites": [_rewrite_response(rewrite) for rewrite in rewrites]}


@app.post("/projects/{project_id}/digital-humans", response_model=DigitalHumanProfile)
def create_digital_human(
    project_id: str,
    request: CreateDigitalHumanRequest,
    settings: Settings = Depends(get_settings),
    digital_store: DigitalHumanStore = Depends(get_digital_human_store),
) -> DigitalHumanProfile:
    profile = digital_store.create(project_id, request)
    append_audit_event(
        settings.storage_dir,
        action="digital_human.created",
        project_id=project_id,
        digital_human_id=profile.digital_human_id,
    )
    return profile


@app.post("/projects/{project_id}/digital-humans/upload", response_model=DigitalHumanProfile)
def upload_personal_digital_human(
    project_id: str,
    request: PersonalDigitalHumanUploadRequest,
    settings: Settings = Depends(get_settings),
    digital_store: DigitalHumanStore = Depends(get_digital_human_store),
) -> DigitalHumanProfile:
    source_type = request.source_type
    if source_type not in {"uploaded_reference", "preset_avatar"}:
        raise HTTPException(status_code=400, detail="source_type must be uploaded_reference or preset_avatar")
    content_type = (request.content_type or "").lower()
    if not (content_type.startswith("image/") or content_type.startswith("video/")):
        raise HTTPException(status_code=400, detail="avatar file must be an image or video file")
    try:
        file_bytes = base64.b64decode(request.content_base64, validate=True)
    except Exception as exc:  # noqa: BLE001 - malformed user upload payload.
        raise HTTPException(status_code=400, detail="content_base64 is not valid base64") from exc
    if not file_bytes:
        raise HTTPException(status_code=400, detail="uploaded avatar file is empty")

    profile = digital_store.create(
        project_id,
        CreateDigitalHumanRequest(
            name=request.name.strip() or "客户个人数字人",
            avatar_source_type=source_type,
            metadata={
                "source_tracking": {
                    "avatar_source_type": source_type,
                    "upload_policy": "stored in project assets; uploaded to selected cloud renderer only during rendering",
                    "original_filename": request.filename or "",
                    "content_type": content_type,
                },
                "tavus_replica_id": request.tavus_replica_id.strip(),
            },
        ),
    )
    safe_name = _safe_upload_filename(request.filename or "personal_avatar")
    asset_dir = ensure_dir(settings.storage_dir / "projects" / project_id / "assets" / "digital_humans" / profile.digital_human_id)
    asset_path = asset_dir / safe_name
    asset_path.write_bytes(file_bytes)
    write_json(
        asset_dir / "asset_metadata.json",
        {
            "digital_human_id": profile.digital_human_id,
            "project_id": project_id,
            "name": profile.name,
            "stored_path": str(asset_path),
            "original_filename": request.filename or "",
            "content_type": content_type,
            "avatar_source_type": source_type,
            "tavus_replica_id": request.tavus_replica_id.strip(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "policy": "customer-uploaded personal digital human asset; cloud upload occurs only when a cloud render provider is selected",
        },
    )
    profile.selected_avatar_asset = str(asset_path)
    profile.metadata["selected_avatar_asset"] = str(asset_path)
    profile.metadata["source_tracking"]["stored_path"] = str(asset_path)
    digital_store.save(profile)
    append_audit_event(
        settings.storage_dir,
        action="digital_human.uploaded",
        project_id=project_id,
        digital_human_id=profile.digital_human_id,
        details={"path": str(asset_path), "content_type": content_type, "tavus_replica_configured": bool(request.tavus_replica_id.strip())},
    )
    return profile


@app.get("/projects/{project_id}/digital-humans", response_model=list[DigitalHumanProfile])
def list_digital_humans(
    project_id: str,
    digital_store: DigitalHumanStore = Depends(get_digital_human_store),
) -> list[DigitalHumanProfile]:
    return [profile for profile in digital_store.list_for_project(project_id) if not _is_system_preset_voice_library(profile)]


@app.get("/projects/{project_id}/voice-profiles")
def list_project_voice_profiles(
    project_id: str,
    visible_assets_only: bool = Query(False),
    settings: Settings = Depends(get_settings),
    digital_store: DigitalHumanStore = Depends(get_digital_human_store),
) -> list[dict[str, object]]:
    _ensure_project_preset_voice_profiles(settings, digital_store, project_id)
    return digital_store.list_voice_profiles_for_project(
        project_id,
        visible_asset_owners_only=visible_assets_only,
    )


@app.get("/digital-humans/{digital_human_id}", response_model=DigitalHumanProfile)
def get_digital_human(
    digital_human_id: str,
    digital_store: DigitalHumanStore = Depends(get_digital_human_store),
) -> DigitalHumanProfile:
    try:
        return digital_store.get(digital_human_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/digital-humans/{digital_human_id}")
def delete_digital_human(
    digital_human_id: str,
    settings: Settings = Depends(get_settings),
    digital_store: DigitalHumanStore = Depends(get_digital_human_store),
) -> dict[str, object]:
    try:
        profile = digital_store.delete_digital_human(digital_human_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    append_audit_event(
        settings.storage_dir,
        action="digital_human.deleted",
        project_id=profile.project_id,
        digital_human_id=digital_human_id,
        details={"name": profile.name},
    )
    return {"deleted": True, "digital_human_id": digital_human_id, "project_id": profile.project_id}


@app.get("/digital-humans/{digital_human_id}/asset-preview")
def get_digital_human_asset_preview(
    digital_human_id: str,
    voice_profile_id: str | None = None,
    settings: Settings = Depends(get_settings),
    digital_store: DigitalHumanStore = Depends(get_digital_human_store),
) -> dict[str, object]:
    try:
        profile = digital_store.get(digital_human_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    voices = digital_store.list_voice_profiles_for_project(profile.project_id)
    selected_voice_id = voice_profile_id or profile.voice_profile_id or (str(voices[-1]["voice_profile_id"]) if voices else "")
    avatar_path = _selected_preview_asset_path(settings, profile)
    voice_path = _selected_voice_preview_path(settings, digital_store, profile, selected_voice_id)
    return {
        "digital_human_id": digital_human_id,
        "name": profile.name,
        "avatar_url": _preview_url(f"/digital-humans/{digital_human_id}/asset-preview/avatar", avatar_path),
        "avatar_media_type": _preview_media_kind(avatar_path),
        "avatar_filename": avatar_path.name if avatar_path else "",
        "voice_profile_id": selected_voice_id,
        "voice_sample_url": _preview_url(
            f"/digital-humans/{digital_human_id}/asset-preview/voice-sample?voice_profile_id={selected_voice_id}",
            voice_path,
            separator="&",
        )
        if selected_voice_id
        else _preview_url(f"/digital-humans/{digital_human_id}/asset-preview/voice-sample", voice_path),
        "voice_sample_filename": voice_path.name if voice_path else "",
        "voices": voices,
    }


@app.get("/digital-humans/{digital_human_id}/asset-preview/avatar")
def get_digital_human_asset_preview_avatar(
    digital_human_id: str,
    settings: Settings = Depends(get_settings),
    digital_store: DigitalHumanStore = Depends(get_digital_human_store),
) -> FileResponse:
    try:
        profile = digital_store.get(digital_human_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    path = _selected_preview_asset_path(settings, profile)
    if not path:
        raise HTTPException(status_code=404, detail="avatar preview not found")
    return _file_response_or_404(path, filename=path.name, media_type=_guess_media_type(path))


@app.get("/digital-humans/{digital_human_id}/asset-preview/voice-sample")
def get_digital_human_asset_preview_voice_sample(
    digital_human_id: str,
    voice_profile_id: str | None = None,
    settings: Settings = Depends(get_settings),
    digital_store: DigitalHumanStore = Depends(get_digital_human_store),
) -> FileResponse:
    try:
        profile = digital_store.get(digital_human_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    selected_voice_id = voice_profile_id or profile.voice_profile_id or ""
    path = _selected_voice_preview_path(settings, digital_store, profile, selected_voice_id)
    if not path:
        raise HTTPException(status_code=404, detail="voice sample preview not found")
    return _file_response_or_404(path, filename=path.name, media_type=_guess_media_type(path))


@app.patch("/digital-humans/{digital_human_id}", response_model=DigitalHumanProfile)
def patch_digital_human(
    digital_human_id: str,
    request: PatchDigitalHumanRequest,
    settings: Settings = Depends(get_settings),
    digital_store: DigitalHumanStore = Depends(get_digital_human_store),
) -> DigitalHumanProfile:
    try:
        profile = digital_store.patch(digital_human_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    append_audit_event(
        settings.storage_dir,
        action="digital_human.updated",
        project_id=profile.project_id,
        digital_human_id=profile.digital_human_id,
    )
    return profile


@app.get("/digital-humans/{digital_human_id}/readiness")
def digital_human_readiness(
    digital_human_id: str,
    digital_store: DigitalHumanStore = Depends(get_digital_human_store),
) -> dict[str, object]:
    try:
        return digital_store.readiness(digital_human_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/digital-humans/{digital_human_id}/role-models", response_model=DigitalHumanRoleModel)
def create_role_model(
    digital_human_id: str,
    request: CreateRoleModelRequest,
    settings: Settings = Depends(get_settings),
    digital_store: DigitalHumanStore = Depends(get_digital_human_store),
) -> DigitalHumanRoleModel:
    try:
        role_model = digital_store.create_role_model(digital_human_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    append_audit_event(
        settings.storage_dir,
        action="role_model.created",
        project_id=role_model.project_id,
        digital_human_id=digital_human_id,
        details={"role_model_id": role_model.role_model_id, "engine_type": role_model.engine_type},
    )
    return role_model


@app.get("/digital-humans/{digital_human_id}/role-models", response_model=list[DigitalHumanRoleModel])
def list_role_models(
    digital_human_id: str,
    digital_store: DigitalHumanStore = Depends(get_digital_human_store),
) -> list[DigitalHumanRoleModel]:
    try:
        return digital_store.list_role_models(digital_human_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/digital-humans/{digital_human_id}/role-models/{role_model_id}", response_model=DigitalHumanRoleModel)
def get_role_model(
    digital_human_id: str,
    role_model_id: str,
    digital_store: DigitalHumanStore = Depends(get_digital_human_store),
) -> DigitalHumanRoleModel:
    try:
        return digital_store.get_role_model(digital_human_id, role_model_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/digital-humans/{digital_human_id}/role-models/{role_model_id}/validate", response_model=DigitalHumanRoleModel)
def validate_role_model(
    digital_human_id: str,
    role_model_id: str,
    settings: Settings = Depends(get_settings),
    digital_store: DigitalHumanStore = Depends(get_digital_human_store),
) -> DigitalHumanRoleModel:
    try:
        role_model = digital_store.validate_role_model(digital_human_id, role_model_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    append_audit_event(
        settings.storage_dir,
        action="role_model.validated",
        project_id=role_model.project_id,
        digital_human_id=digital_human_id,
        details={
            "role_model_id": role_model.role_model_id,
            "status": role_model.status,
            "blocking_items": role_model.validation_report.get("blocking_items", []),
        },
    )
    return role_model


@app.post("/digital-humans/{digital_human_id}/avatar/generate")
def generate_avatar(
    digital_human_id: str,
    request: AvatarGenerationRequest,
    settings: Settings = Depends(get_settings),
    digital_store: DigitalHumanStore = Depends(get_digital_human_store),
) -> dict[str, object]:
    try:
        profile = digital_store.get(digital_human_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    generation_id = "avatar_gen_" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    root = ensure_dir(digital_store.digital_human_dir(profile.project_id, digital_human_id) / "avatar_generations")
    generation_dir = ensure_dir(root / generation_id)
    images = []
    for index in range(request.count):
        asset_id = f"{generation_id}_{index + 1}"
        path = generation_dir / f"{asset_id}.svg"
        path.write_text(
            _avatar_svg(
                title=profile.name,
                prompt=request.prompt,
                style=request.style,
                seed=request.seed,
                index=index + 1,
            ),
            encoding="utf-8",
        )
        images.append(
            {
                "asset_id": asset_id,
                "path": str(path),
                "url": f"/digital-humans/{digital_human_id}/avatar/assets/{asset_id}",
            }
        )
    record = {
        "generation_id": generation_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "prompt": request.prompt,
        "negative_prompt": request.negative_prompt,
        "style": request.style,
        "seed": request.seed,
        "images": images,
    }
    write_json(generation_dir / "generation.json", record)
    append_audit_event(
        settings.storage_dir,
        action="avatar.generated",
        project_id=profile.project_id,
        digital_human_id=digital_human_id,
        details={"generation_id": generation_id, "image_count": len(images)},
    )
    return record


@app.get("/digital-humans/{digital_human_id}/avatar/generations")
def list_avatar_generations(
    digital_human_id: str,
    digital_store: DigitalHumanStore = Depends(get_digital_human_store),
) -> dict[str, object]:
    try:
        profile = digital_store.get(digital_human_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    root = digital_store.digital_human_dir(profile.project_id, digital_human_id) / "avatar_generations"
    generations = []
    for path in sorted(root.glob("*/generation.json"), reverse=True) if root.exists() else []:
        generations.append(read_json(path))
    return {"digital_human_id": digital_human_id, "generations": generations}


@app.get("/digital-humans/{digital_human_id}/avatar/assets/{asset_id}")
def get_avatar_asset(
    digital_human_id: str,
    asset_id: str,
    digital_store: DigitalHumanStore = Depends(get_digital_human_store),
) -> FileResponse:
    path = _find_avatar_asset(digital_store, digital_human_id, asset_id)
    return FileResponse(path, media_type="image/svg+xml")


@app.post("/digital-humans/{digital_human_id}/avatar/select")
def select_avatar(
    digital_human_id: str,
    request: AvatarSelectRequest,
    settings: Settings = Depends(get_settings),
    digital_store: DigitalHumanStore = Depends(get_digital_human_store),
) -> dict[str, object]:
    path = _find_avatar_asset(digital_store, digital_human_id, request.asset_id)
    profile = digital_store.get(digital_human_id)
    profile.selected_avatar_asset = str(path)
    digital_store.save(profile)
    append_audit_event(
        settings.storage_dir,
        action="avatar.selected",
        project_id=profile.project_id,
        digital_human_id=digital_human_id,
        details={"asset_id": request.asset_id, "path": str(path)},
    )
    return profile.model_dump(mode="json")


@app.post("/digital-humans/{digital_human_id}/voice-profiles")
def create_voice_profile(
    digital_human_id: str,
    request: CreateVoiceProfileRequest,
    settings: Settings = Depends(get_settings),
    digital_store: DigitalHumanStore = Depends(get_digital_human_store),
) -> dict[str, object]:
    sample_upload = _decode_voice_sample_upload(request)
    try:
        voice = digital_store.create_voice_profile(digital_human_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if sample_upload:
        filename, content_type, file_bytes = sample_upload
        sample_dir = ensure_dir(
            digital_store.voice_profile_dir(voice.project_id, digital_human_id)
            / voice.voice_profile_id
            / "sample"
        )
        sample_path = sample_dir / filename
        sample_path.write_bytes(file_bytes)
        voice.sample_asset_id = str(sample_path)
        voice.voice_source_type = VoiceSourceType.uploaded_sample
        if voice.engine in {"", "dryrun", "dry-run"}:
            voice.engine = "local_sample"
        metadata = dict(voice.metadata or {})
        metadata.update(
            {
                "sample_audio_path": str(sample_path),
                "sample_audio_filename": filename,
                "sample_audio_content_type": content_type,
                "sample_audio_uploaded_at": datetime.now(timezone.utc).isoformat(),
                "source": "uploaded_sample",
            }
        )
        voice.metadata = metadata
        digital_store.save_voice_profile(voice)
    append_audit_event(
        settings.storage_dir,
        action="voice_profile.created",
        project_id=voice.project_id,
        digital_human_id=digital_human_id,
        details={"voice_profile_id": voice.voice_profile_id},
    )
    return voice.model_dump(mode="json")


@app.get("/digital-humans/{digital_human_id}/voice-profiles")
def list_voice_profiles(
    digital_human_id: str,
    digital_store: DigitalHumanStore = Depends(get_digital_human_store),
) -> list[dict[str, object]]:
    try:
        return [voice.model_dump(mode="json") for voice in digital_store.list_voice_profiles(digital_human_id)]
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/digital-humans/{digital_human_id}/voice-profiles/{voice_profile_id}")
def delete_voice_profile(
    digital_human_id: str,
    voice_profile_id: str,
    settings: Settings = Depends(get_settings),
    digital_store: DigitalHumanStore = Depends(get_digital_human_store),
) -> dict[str, object]:
    try:
        voice = digital_store.delete_voice_profile(digital_human_id, voice_profile_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    append_audit_event(
        settings.storage_dir,
        action="voice_profile.deleted",
        project_id=voice.project_id,
        digital_human_id=digital_human_id,
        details={"voice_profile_id": voice_profile_id, "name": voice.name},
    )
    return {
        "deleted": True,
        "digital_human_id": digital_human_id,
        "voice_profile_id": voice_profile_id,
        "project_id": voice.project_id,
    }


@app.post("/digital-humans/{digital_human_id}/voice-profiles/{voice_profile_id}/test")
async def test_voice_profile(
    digital_human_id: str,
    voice_profile_id: str,
    request: VoiceTestRequest,
    settings: Settings = Depends(get_settings),
    digital_store: DigitalHumanStore = Depends(get_digital_human_store),
    license_client: CommercialLicenseClient = Depends(get_desktop_license_client),
) -> dict[str, object]:
    try:
        voice = _get_voice_profile_for_route(digital_store, digital_human_id, voice_profile_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    out_dir = ensure_dir(
        digital_store.digital_human_dir(voice.project_id, digital_human_id)
        / "voice_profiles"
        / voice_profile_id
        / "tests"
    )
    audio_path = out_dir / "voice_test.wav"
    metadata_path = out_dir / "voice_test_metadata.json"
    language = request.language if request.language in {"zh-CN", "en-US"} else "zh-CN"
    voice_style = _normalize_voice_style(request.voice_style)
    speech_rate = _normalize_speech_rate(request.speech_rate)
    if _cached_voice_test_matches(audio_path, metadata_path, request.text, language, voice_style, speech_rate):
        return {
            "voice_profile_id": voice_profile_id,
            "audio_path": str(audio_path),
            "metadata_path": str(metadata_path),
            "audio_url": _voice_test_audio_url(digital_human_id, voice_profile_id, audio_path),
            "cached": True,
            "message": "已播放本地克隆试听缓存，没有重新调用云端。",
        }
    if _voice_profile_uses_sample_preview(voice) and not request.allow_sample_fallback:
        voice = await _ensure_voice_profile_cloud_clone(
            settings,
            digital_store,
            digital_human_id,
            voice,
            out_dir,
            confirm_paid_call=request.confirm_paid_call,
        )
    if _voice_profile_uses_sample_preview(voice):
        sample_audio = _voice_profile_sample_audio_path(settings, voice)
        if not request.allow_sample_fallback:
            raise HTTPException(
                status_code=400,
                detail="当前音色不支持单独生成脚本语音；请点击播放原始样本试听音色，或直接生成数字人视频。",
            )
        if not sample_audio:
            raise HTTPException(status_code=404, detail="这个声音没有可播放的本地样本，请重新上传音频或重新创建声音。")
        return {
            "voice_profile_id": voice_profile_id,
            "audio_path": str(sample_audio),
            "metadata_path": None,
            "audio_url": _voice_sample_audio_url(digital_human_id, voice_profile_id, sample_audio),
            "cached": True,
            "fallback_to_sample": True,
            "message": "当前声音平台暂不支持生成新文本试听，已播放原始样本。",
        }
    script_path = write_json(
        out_dir / "voice_test_script.json",
        {
            "title": "voice test",
            "language": language,
            "voice_style": voice_style,
            "speech_rate": speech_rate,
            "segments": [{"start": 0, "end": 3, "text": request.text}],
            "body": request.text,
        },
    )
    tts = _select_tts_adapter(settings, voice)
    if not settings.dry_run and getattr(tts, "name", "") in {"aliyun_bailian", "cloud_voice"} and not request.confirm_paid_call:
        raise HTTPException(
            status_code=402,
            detail="请先勾选“确认云端声音试听”，云端声音试听可能消耗服务额度。",
        )
    try:
        tts_result = await tts.synthesize(script_json=script_path, voice_profile=voice, out_dir=out_dir)
    except AdapterError as exc:
        retry_error: AdapterError | None = exc
        if _voice_preview_error_should_reclone(exc, voice):
            try:
                voice = await _ensure_voice_profile_cloud_clone(
                    settings,
                    digital_store,
                    digital_human_id,
                    voice,
                    out_dir,
                    confirm_paid_call=request.confirm_paid_call,
                    force=True,
                )
                tts = _select_tts_adapter(settings, voice)
                tts_result = await tts.synthesize(script_json=script_path, voice_profile=voice, out_dir=out_dir)
                retry_error = None
            except AdapterError as reclone_exc:
                retry_error = reclone_exc
        if retry_error is not None:
            exc = retry_error
            error_detail = _redact_sensitive_text(exc)
            failed_message = "\u4e91\u7aef\u58f0\u97f3\u8bd5\u542c\u5931\u8d25\uff0c\u8bf7\u91cd\u65b0\u514b\u9686\u58f0\u97f3\u6216\u6362\u4e00\u6761\u5386\u53f2\u58f0\u97f3\u540e\u518d\u8bd5\u3002"
            write_json(
                out_dir / "voice_test_error.json",
                {
                    "voice_profile_id": voice_profile_id,
                    "digital_human_id": digital_human_id,
                    "engine": getattr(tts, "name", voice.engine),
                    "voice_source_type": voice.voice_source_type,
                    "message": failed_message,
                    "provider_error": error_detail,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            raise HTTPException(
                status_code=502,
                detail=f"{failed_message}\u4e91\u7aef\u539f\u56e0\uff1a{error_detail}",
            ) from exc
    shutil.copyfile(tts_result.audio_path, audio_path)
    source_metadata = read_json(tts_result.metadata_path) if tts_result.metadata_path.exists() else {}
    metadata_path = write_json(
        out_dir / "voice_test_metadata.json",
        {
            "voice_profile_id": voice_profile_id,
            "text": request.text,
            "language": language,
            "voice_style": voice_style,
            "speech_rate": speech_rate,
            "engine": source_metadata.get("engine", getattr(tts, "name", voice.engine)),
            "voice_source_type": voice.voice_source_type,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "readable": source_metadata.get("readable", audio_path.exists() and audio_path.stat().st_size > 0),
            "source_metadata": source_metadata,
        },
    )
    append_audit_event(
        settings.storage_dir,
        action="voice.synthesized",
        project_id=voice.project_id,
        digital_human_id=digital_human_id,
        details={"voice_profile_id": voice_profile_id, "mode": "test", "voice_style": voice_style, "speech_rate": speech_rate},
    )
    return {
        "voice_profile_id": voice_profile_id,
        "audio_path": str(audio_path),
        "metadata_path": str(metadata_path),
        "audio_url": _voice_test_audio_url(digital_human_id, voice_profile_id, audio_path),
        "cached": False,
        "fallback_to_sample": False,
        "message": "克隆试听已生成并缓存到本地。",
    }


@app.get("/digital-humans/{digital_human_id}/voice-profiles/{voice_profile_id}/sample-audio")
def get_voice_sample_audio(
    digital_human_id: str,
    voice_profile_id: str,
    settings: Settings = Depends(get_settings),
    digital_store: DigitalHumanStore = Depends(get_digital_human_store),
) -> FileResponse:
    try:
        voice = _get_voice_profile_for_route(digital_store, digital_human_id, voice_profile_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    path = _voice_profile_sample_audio_path(settings, voice)
    if not path:
        raise HTTPException(status_code=404, detail="没有找到这个声音的本地原始样本。")
    return _file_response_or_404(path, filename=path.name, media_type=_guess_media_type(path))


@app.get("/digital-humans/{digital_human_id}/voice-profiles/{voice_profile_id}/test-audio/voice_test.wav")
def get_voice_test_audio(
    digital_human_id: str,
    voice_profile_id: str,
    digital_store: DigitalHumanStore = Depends(get_digital_human_store),
) -> FileResponse:
    try:
        voice = _get_voice_profile_for_route(digital_store, digital_human_id, voice_profile_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    path = (
        digital_store.digital_human_dir(voice.project_id, digital_human_id)
        / "voice_profiles"
        / voice_profile_id
        / "tests"
        / "voice_test.wav"
    )
    return _file_response_or_404(path, filename="voice_test.wav", media_type="audio/wav")


@app.post("/digital-humans/{digital_human_id}/source-video/upload")
def upload_digital_human_source_video(
    digital_human_id: str,
    request: SourceVideoUploadRequest,
    workflow: SourceVideoWorkflow = Depends(get_source_video_workflow),
) -> dict[str, object]:
    try:
        return workflow.upload_source_video(digital_human_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SourceVideoWorkflowError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.post("/digital-humans/{digital_human_id}/source-video/extract-voice")
def extract_digital_human_source_video_voice(
    digital_human_id: str,
    workflow: SourceVideoWorkflow = Depends(get_source_video_workflow),
) -> dict[str, object]:
    try:
        return workflow.extract_voice(digital_human_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SourceVideoWorkflowError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.post("/digital-humans/{digital_human_id}/source-video/create-voice-profile")
async def create_source_video_voice_profile(
    digital_human_id: str,
    request: SourceVideoVoiceProfileRequest,
    settings: Settings = Depends(get_settings),
    workflow: SourceVideoWorkflow = Depends(get_source_video_workflow),
    license_client: CommercialLicenseClient = Depends(get_desktop_license_client),
) -> dict[str, object]:
    try:
        voice = await workflow.create_voice_profile(digital_human_id, request)
        return voice.model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SourceVideoWorkflowError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.post("/digital-humans/{digital_human_id}/source-video/hifly/create-avatar")
async def create_hifly_source_video_avatar(
    digital_human_id: str,
    request: HiflySourceVideoAvatarRequest,
    settings: Settings = Depends(get_settings),
    workflow: SourceVideoWorkflow = Depends(get_source_video_workflow),
    license_client: CommercialLicenseClient = Depends(get_desktop_license_client),
) -> dict[str, object]:
    try:
        result = await workflow.create_hifly_avatar(digital_human_id, request)
        return result
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SourceVideoWorkflowError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.post("/digital-humans/{digital_human_id}/source-video/hifly/create-voice")
async def create_hifly_source_video_voice(
    digital_human_id: str,
    request: HiflySourceVideoVoiceRequest,
    settings: Settings = Depends(get_settings),
    workflow: SourceVideoWorkflow = Depends(get_source_video_workflow),
    license_client: CommercialLicenseClient = Depends(get_desktop_license_client),
) -> dict[str, object]:
    try:
        result = await workflow.create_hifly_voice(digital_human_id, request)
        return result
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SourceVideoWorkflowError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.post("/digital-humans/{digital_human_id}/source-video/hifly/generate", response_model=TaskResponse)
async def generate_hifly_source_video(
    digital_human_id: str,
    request: HiflySourceVideoGenerateRequest,
    settings: Settings = Depends(get_settings),
    store: TaskStore = Depends(get_store),
    digital_store: DigitalHumanStore = Depends(get_digital_human_store),
    workflow: SourceVideoWorkflow = Depends(get_source_video_workflow),
    license_client: CommercialLicenseClient = Depends(get_desktop_license_client),
) -> TaskResponse:
    try:
        profile = digital_store.get(digital_human_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    credit_reservation: dict[str, object] = {}
    estimated_seconds = _estimate_cloud_usage_seconds(request.text, fallback_seconds=10)
    if not settings.dry_run and request.confirm_paid_call:
        credit_reservation = _reserve_commercial_credits_or_raise(
            settings,
            license_client,
            usage_seconds=estimated_seconds,
            provider="hifly",
            feature="hifly_video",
            context={"digital_human_id": digital_human_id, "title": request.title},
        )
    task = store.create(
        CreateVideoTaskRequest(
            brand_name=profile.name,
            persona="Hifly source-video digital human",
            topic=request.title,
            project_id=profile.project_id,
            digital_human_id=digital_human_id,
            voice_profile_id=request.voice_profile_id,
            fixed_script=request.text,
            export_jianying_draft=False,
            render_profile="final",
            use_digital_human_pipeline=False,
            metadata={"hifly_workflow": True, **request.metadata},
        )
    )
    try:
        task = await workflow.generate_hifly_from_source_video(store, task, request)
    except Exception:
        _commit_commercial_credits_on_cloud_failure(
            license_client,
            credit_reservation,
            actual_seconds=estimated_seconds,
            reason="hifly_video_failed",
            context={"digital_human_id": digital_human_id, "title": request.title},
        )
        raise
    _commit_commercial_credits_best_effort(
        license_client,
        credit_reservation,
        actual_seconds=estimated_seconds,
        context={"digital_human_id": digital_human_id, "title": request.title},
    )
    return TaskResponse(task_id=task.task_id, status=task.status, artifacts=task.artifacts, error=task.error)


@app.post("/projects/{project_id}/digital-human-tasks", response_model=DigitalHumanTaskResponse)
def create_digital_human_task(
    project_id: str,
    request: DigitalHumanTaskRequest,
    settings: Settings = Depends(get_settings),
    store: TaskStore = Depends(get_store),
    digital_store: DigitalHumanStore = Depends(get_digital_human_store),
) -> DigitalHumanTaskResponse:
    try:
        profile = digital_store.get(request.digital_human_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"digital human not found: {request.digital_human_id}") from exc
    if profile.project_id != project_id:
        raise HTTPException(status_code=404, detail=f"digital human not found in project: {project_id}")
    try:
        voice = digital_store.get_voice_profile_for_project(project_id, request.voice_profile_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"voice profile not found: {request.voice_profile_id}") from exc

    task_request = CreateVideoTaskRequest(
        brand_name=profile.name,
        persona="Synthetic digital human host",
        topic=request.topic,
        project_id=project_id,
        digital_human_id=profile.digital_human_id,
        voice_profile_id=voice.voice_profile_id,
        role_model_id=request.role_model_id,
        platform=request.platform,
        duration_seconds=request.duration_seconds,
        export_jianying_draft=request.export_jianying_draft,
        render_profile=request.render_profile,
        force_render=request.force_render,
        avatar_engine_preference=request.avatar_engine_preference,
        lip_sync_engine_preference=request.lip_sync_engine_preference,
        video_template_id=request.video_template_id,
        use_project_context=request.use_project_context,
        use_digital_human_pipeline=True,
        fixed_script=request.fixed_script,
        script_review_required=request.script_review_required,
        metadata=request.metadata,
    )
    task = store.create(task_request)
    append_audit_event(
        settings.storage_dir,
        action="digital_human.task_created",
        task_id=task.task_id,
        project_id=project_id,
        digital_human_id=profile.digital_human_id,
        details={
            "voice_profile_id": voice.voice_profile_id,
            "render_profile": request.render_profile,
            "video_template_id": request.video_template_id,
        },
    )
    return DigitalHumanTaskResponse(task_id=task.task_id, plan=DIGITAL_HUMAN_PLAN, initial_status=task.status)


@app.post("/tasks/{task_id}/review/approve", response_model=TaskResponse)
def approve_script(
    task_id: str,
    request: ReviewApprovalRequest,
    settings: Settings = Depends(get_settings),
    store: TaskStore = Depends(get_store),
) -> TaskResponse:
    try:
        task = store.get(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    task.request.metadata["script_approved"] = True
    task.request.metadata["reviewer_id"] = request.reviewer_id
    task.request.metadata["review_note"] = request.review_note
    task.status = TaskStatus.created
    task = store.save(task)
    append_audit_event(
        settings.storage_dir,
        action="script.approved",
        task_id=task.task_id,
        project_id=task.request.project_id,
        digital_human_id=task.request.digital_human_id,
        actor=request.reviewer_id,
    )
    return TaskResponse(task_id=task.task_id, status=task.status, artifacts=task.artifacts, error=task.error)


@app.post("/tasks/{task_id}/render/retry", response_model=TaskResponse)
async def retry_render(
    task_id: str,
    request: RenderRetryRequest,
    settings: Settings = Depends(get_settings),
    store: TaskStore = Depends(get_store),
    pipeline: VideoPipeline = Depends(get_pipeline),
) -> TaskResponse:
    try:
        task = store.get(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    task.request.retry_from = request.retry_from
    task.request.force_render = False
    _invalidate_downstream(store.task_dir(task_id), request.retry_from)
    append_audit_event(
        settings.storage_dir,
        action="render.retry_requested",
        task_id=task.task_id,
        project_id=task.request.project_id,
        digital_human_id=task.request.digital_human_id,
        details={"retry_from": request.retry_from},
    )
    task = store.save(task)
    task = await pipeline.run(task)
    return TaskResponse(task_id=task.task_id, status=task.status, artifacts=task.artifacts, error=task.error)


@app.post("/tasks/{task_id}/cloud-source-video-render", response_model=TaskResponse)
async def cloud_source_video_render(
    task_id: str,
    request: CloudSourceVideoRenderRequest | None = None,
    settings: Settings = Depends(get_settings),
    store: TaskStore = Depends(get_store),
    workflow: SourceVideoWorkflow = Depends(get_source_video_workflow),
    license_client: CommercialLicenseClient = Depends(get_desktop_license_client),
) -> TaskResponse:
    try:
        task = store.get(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if task.status == TaskStatus.running:
        raise HTTPException(status_code=409, detail="当前数字人生成任务正在运行，请等待完成后再操作。")
    running_tasks = store.running_tasks(exclude_task_id=task_id)
    if running_tasks:
        raise HTTPException(
            status_code=409,
            detail=f"已有数字人生成任务正在运行，请等待当前任务完成后再提交。任务ID：{running_tasks[0].task_id}",
        )
    render_request = request or CloudSourceVideoRenderRequest()
    credit_reservation: dict[str, object] = {}
    estimated_seconds = 0
    if not settings.dry_run and render_request.confirm_paid_call:
        task_text = str(getattr(task.request, "fixed_script", "") or getattr(task.request, "topic", "") or "")
        estimated_seconds = _estimate_cloud_usage_seconds(task_text, fallback_seconds=10)
        credit_reservation = _reserve_commercial_credits_or_raise(
            settings,
            license_client,
            usage_seconds=estimated_seconds,
            provider=settings.cloud_video_provider,
            feature=f"cloud_video_render:{settings.cloud_video_provider}",
            context={"task_id": task_id, "digital_human_id": task.request.digital_human_id or ""},
        )
    try:
        task = await workflow.render_task_from_source_video(store, task, render_request)
    except Exception:
        _commit_commercial_credits_on_cloud_failure(
            license_client,
            credit_reservation,
            actual_seconds=estimated_seconds or None,
            reason="cloud_video_render_failed",
            context={"task_id": task_id, "digital_human_id": task.request.digital_human_id or ""},
        )
        raise
    _commit_commercial_credits_best_effort(
        license_client,
        credit_reservation,
        actual_seconds=estimated_seconds or None,
        context={"task_id": task_id, "digital_human_id": task.request.digital_human_id or ""},
    )
    return TaskResponse(task_id=task.task_id, status=task.status, artifacts=task.artifacts, error=task.error)


@app.get("/tasks/{task_id}/source-video-report")
def get_source_video_task_report(task_id: str, store: TaskStore = Depends(get_store)) -> dict[str, object]:
    task = _get_task_or_404(task_id, store)
    task_dir = store.task_dir(task.task_id)
    reports: dict[str, object] = {"task_id": task_id}
    for name in [
        "source_video_report.json",
        "source_audio_report.json",
        "voice_sample_report.json",
        "avatar_duration_normalization_report.json",
        "cloud_video_render_report.json",
        "provider_report.json",
        "final_assembly_report.json",
    ]:
        path = task_dir / name
        if path.exists():
            reports[name.replace(".json", "")] = read_json(path)
    return reports


def _invalidate_downstream(task_dir, retry_from: str) -> None:
    stages = {
        "voice": [
            "voice.wav",
            "voice_segments.json",
            "voice_metadata.json",
            "audio_quality_report.json",
            "avatar_base.mp4",
            "avatar_render_metadata.json",
            "avatar_render_report.json",
            "lip_synced.mp4",
            "lip_sync_report.json",
            "final.mp4",
            "cover.png",
            "template_report.json",
            "template_ffmpeg_stdout.log",
            "template_ffmpeg_stderr.log",
            "render_stability_report.json",
            "digital_human_quality_report.json",
            "publish_package.json",
        ],
        "avatar": [
            "avatar_base.mp4",
            "avatar_render_metadata.json",
            "avatar_render_report.json",
            "lip_synced.mp4",
            "lip_sync_report.json",
            "final.mp4",
            "cover.png",
            "template_report.json",
            "template_ffmpeg_stdout.log",
            "template_ffmpeg_stderr.log",
            "render_stability_report.json",
            "digital_human_quality_report.json",
            "publish_package.json",
        ],
        "lip_sync": [
            "lip_synced.mp4",
            "lip_sync_report.json",
            "final.mp4",
            "cover.png",
            "template_report.json",
            "template_ffmpeg_stdout.log",
            "template_ffmpeg_stderr.log",
            "render_stability_report.json",
            "digital_human_quality_report.json",
            "publish_package.json",
        ],
        "assemble": [
            "final.mp4",
            "cover.png",
            "template_report.json",
            "template_ffmpeg_stdout.log",
            "template_ffmpeg_stderr.log",
            "render_stability_report.json",
            "digital_human_quality_report.json",
            "publish_package.json",
        ],
    }
    for name in stages.get(retry_from, stages["lip_sync"]):
        path = task_dir / name
        if path.is_dir():
            for child in sorted(path.rglob("*"), reverse=True):
                if child.is_file():
                    child.unlink()
                elif child.is_dir():
                    child.rmdir()
            path.rmdir()
        elif path.exists():
            path.unlink()


def _get_task_or_404(task_id: str, store: TaskStore):
    try:
        return store.get(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _file_response_or_404(path: Path, *, filename: str, media_type: str) -> FileResponse:
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"file not found: {filename}")
    return FileResponse(path, filename=filename, media_type=media_type)


def _safe_storage_file(settings: Settings, path_value: str | None) -> Path | None:
    if not path_value:
        return None
    raw_path = Path(str(path_value))
    candidates = [raw_path]
    if not raw_path.is_absolute():
        candidates.append(settings.storage_dir / raw_path)
        candidates.append(settings.storage_dir.parent / raw_path)
    storage_root = settings.storage_dir.resolve()
    for path in candidates:
        if not path.exists() or not path.is_file():
            continue
        try:
            resolved = path.resolve()
            resolved.relative_to(storage_root)
        except ValueError:
            continue
        return resolved
    return None


def _voice_test_audio_url(digital_human_id: str, voice_profile_id: str, audio_path: Path) -> str:
    return (
        f"/digital-humans/{digital_human_id}/voice-profiles/{voice_profile_id}/test-audio/voice_test.wav"
        f"?v={audio_path.stat().st_mtime_ns}"
    )


def _voice_sample_audio_url(digital_human_id: str, voice_profile_id: str, audio_path: Path) -> str:
    return (
        f"/digital-humans/{digital_human_id}/voice-profiles/{voice_profile_id}/sample-audio"
        f"?v={audio_path.stat().st_mtime_ns}"
    )


def _get_voice_profile_for_route(
    digital_store: DigitalHumanStore,
    digital_human_id: str,
    voice_profile_id: str,
) -> VoiceProfile:
    profile = digital_store.get(digital_human_id)
    try:
        return digital_store.get_voice_profile(digital_human_id, voice_profile_id)
    except KeyError:
        return digital_store.get_voice_profile_for_project(profile.project_id, voice_profile_id)


def _voice_profile_cloud_voice_id(voice: VoiceProfile) -> str:
    metadata = voice.metadata if isinstance(voice.metadata, dict) else {}
    return str(
        metadata.get("cloud_voice_id")
        or metadata.get("provider_voice_id")
        or metadata.get("voice_id")
        or ""
    ).strip()


def _voice_preview_error_should_reclone(exc: AdapterError, voice: VoiceProfile) -> bool:
    message = str(exc).lower()
    if "empty audio" not in message and "missing audio" not in message:
        return False
    voice_engine = str(voice.engine or "").lower().strip()
    metadata = voice.metadata if isinstance(voice.metadata, dict) else {}
    provider = str(metadata.get("provider") or "").lower().strip()
    return _voice_profile_cloud_voice_id(voice) != "" and (
        voice_engine.startswith("aliyun_bailian") or provider.startswith("aliyun_bailian")
    )


def _voice_profile_can_auto_clone(voice: VoiceProfile) -> bool:
    voice_source = str(getattr(voice.voice_source_type, "value", voice.voice_source_type) or "").lower()
    return (
        voice_source.endswith("preset_voice")
        or voice_source.endswith("uploaded_sample")
        or voice_source.endswith("source_video_audio")
    )


def _voice_clone_sample_key(settings: Settings, voice: VoiceProfile, sample_audio: Path) -> str:
    prefix = (settings.object_storage_prefix or "aivo").strip().strip("/")
    return posixpath.join(
        prefix,
        "projects",
        voice.project_id,
        "voice_profiles",
        voice.voice_profile_id,
        sample_audio.name,
    )


async def _ensure_voice_profile_cloud_clone(
    settings: Settings,
    digital_store: DigitalHumanStore,
    digital_human_id: str,
    voice: VoiceProfile,
    out_dir: Path,
    *,
    confirm_paid_call: bool,
    force: bool = False,
) -> VoiceProfile:
    if _voice_profile_cloud_voice_id(voice) and not force:
        return voice
    if not _voice_profile_can_auto_clone(voice):
        return voice
    if not settings.dry_run and not confirm_paid_call:
        raise HTTPException(
            status_code=402,
            detail="请先确认云端声音试听，首次使用该音色需要克隆声音并可能消耗服务额度。",
        )
    if not settings.dry_run and not settings.dashscope_api_key:
        raise HTTPException(status_code=400, detail="DASHSCOPE_API_KEY 未配置，无法克隆该声音。")

    sample_audio = _voice_profile_sample_audio_path(settings, voice)
    if not sample_audio:
        raise HTTPException(status_code=404, detail="没有找到这个声音的本地样本，无法克隆声音。")

    metadata = dict(voice.metadata or {})
    sample_audio_url = str(metadata.get("sample_audio_url") or "").strip() or None
    object_storage_upload = metadata.get("object_storage_upload")
    clone_dir = ensure_dir(out_dir / "voice_clone")
    if not settings.dry_run and not sample_audio_url:
        try:
            upload_result = build_object_storage_adapter(settings).upload_file(
                file_path=sample_audio,
                key=_voice_clone_sample_key(settings, voice, sample_audio),
                report_dir=clone_dir,
                report_name="voice_sample_upload.json",
            )
        except AdapterError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"声音克隆需要可公网访问的样本音频，请先配置阿里云 OSS/腾讯云 COS：{_redact_sensitive_text(exc)}",
            ) from exc
        sample_audio_url = upload_result.public_url
        object_storage_upload = {
            "provider": upload_result.provider,
            "key": upload_result.key,
            "public_url": upload_result.public_url,
            "local_copy_path": upload_result.local_copy_path,
            "report_path": upload_result.report_path,
        }

    provider = (settings.cloud_voice_provider or "aliyun_bailian_cosyvoice").lower().strip()
    if not provider.startswith("aliyun_bailian"):
        provider = "aliyun_bailian_cosyvoice"
    adapter = AliyunBailianVoiceAdapter(
        provider_id=provider,
        dry_run=settings.dry_run,
        api_key=settings.dashscope_api_key,
        region=settings.aliyun_bailian_region,
        model=settings.aliyun_voice_model,
    )
    try:
        clone_response = await adapter.create_voice_clone(
            sample_audio_path=sample_audio,
            sample_audio_url=sample_audio_url,
            voice_name=voice.name,
            out_dir=clone_dir,
        )
    except AdapterError as exc:
        raise HTTPException(status_code=502, detail=f"声音克隆失败：{_redact_sensitive_text(exc)}") from exc

    provider_voice_id = str(clone_response.get("voice_id") or "").strip()
    if not provider_voice_id:
        raise HTTPException(status_code=502, detail="声音克隆失败：云端没有返回 voice_id。")

    metadata.update(
        {
            "provider": provider,
            "provider_voice_id": provider_voice_id,
            "cloud_voice_id": provider_voice_id,
            "voice_id": provider_voice_id,
            "sample_audio_url": sample_audio_url,
            "object_storage_upload": object_storage_upload,
            "clone_response_path": str(clone_dir / "aliyun_voice_clone_response.json"),
            "clone_created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    voice.engine = provider
    voice.metadata = metadata
    digital_store.save_voice_profile(voice)
    append_audit_event(
        settings.storage_dir,
        action="voice_profile.updated",
        project_id=voice.project_id,
        digital_human_id=voice.digital_human_id,
        details={
            "voice_profile_id": voice.voice_profile_id,
            "mode": "auto_clone_for_script_preview",
            "route_digital_human_id": digital_human_id,
        },
    )
    return voice


def _cached_voice_test_matches(
    audio_path: Path,
    metadata_path: Path,
    text: str,
    language: str = "zh-CN",
    voice_style: str = "natural",
    speech_rate: float = 1.0,
) -> bool:
    if not audio_path.exists() or not audio_path.is_file() or audio_path.stat().st_size <= 0:
        return False
    if not metadata_path.exists():
        return False
    try:
        metadata = read_json(metadata_path)
    except Exception:
        return False
    if metadata.get("text") != text:
        return False
    if metadata.get("language", "zh-CN") != language:
        return False
    if _normalize_voice_style(str(metadata.get("voice_style", "natural"))) != voice_style:
        return False
    if _normalize_speech_rate(metadata.get("speech_rate", 1.0)) != speech_rate:
        return False
    if metadata.get("readable") is False:
        return False
    return True


def _normalize_voice_style(value: object) -> str:
    raw = str(value or "natural").strip().lower()
    mapping = {
        "自然": "natural",
        "natural": "natural",
        "热情": "warm",
        "warm": "warm",
        "enthusiastic": "warm",
        "沉稳": "calm",
        "calm": "calm",
        "steady": "calm",
    }
    return mapping.get(raw, "natural")


def _normalize_speech_rate(value: object) -> float:
    try:
        rate = float(value)
    except (TypeError, ValueError):
        return 1.0
    return round(max(0.5, min(2.0, rate)), 1)


def _ensure_project_preset_voice_profiles(
    settings: Settings,
    digital_store: DigitalHumanStore,
    project_id: str,
) -> None:
    profile = _ensure_preset_voice_library_profile(digital_store, project_id)
    existing_by_preset_id: dict[str, VoiceProfile] = {}
    for voice in digital_store.list_voice_profiles(profile.digital_human_id):
        metadata = voice.metadata if isinstance(voice.metadata, dict) else {}
        preset_id = str(metadata.get("preset_voice_id") or "")
        if preset_id:
            existing_by_preset_id[preset_id] = voice

    for preset in DEFAULT_PRESET_VOICE_ASSETS:
        preset_id = str(preset["preset_id"])
        source_path = _find_preset_voice_source(settings, str(preset["filename"]))
        stored_path = _stored_preset_voice_path(settings, project_id, preset_id, str(preset["filename"]))
        if source_path and not stored_path.exists():
            ensure_dir(stored_path.parent)
            shutil.copy2(source_path, stored_path)
        if not stored_path.exists():
            continue
        existing = existing_by_preset_id.get(preset_id)
        if existing:
            metadata = dict(existing.metadata or {})
            if metadata.get("sample_audio_path") != str(stored_path) or existing.sample_asset_id != str(stored_path):
                metadata.update(
                    {
                        "sample_audio_path": str(stored_path),
                        "sample_audio_filename": stored_path.name,
                        "sample_audio_content_type": _guess_media_type(stored_path),
                    }
                )
                existing.sample_asset_id = str(stored_path)
                existing.metadata = metadata
                digital_store.save_voice_profile(existing)
            continue
        voice = VoiceProfile(
            voice_profile_id=f"voice_preset_{preset_id}",
            digital_human_id=profile.digital_human_id,
            project_id=project_id,
            name=str(preset["name"]),
            voice_source_type=VoiceSourceType.preset_voice,
            engine="local_sample",
            sample_asset_id=str(stored_path),
            metadata={
                "source": "default_preset_voice_asset",
                "preset_voice_id": preset_id,
                "sample_audio_path": str(stored_path),
                "sample_audio_filename": stored_path.name,
                "sample_audio_content_type": _guess_media_type(stored_path),
                "customer_visible": True,
            },
        )
        digital_store.save_voice_profile(voice)


def _ensure_preset_voice_library_profile(digital_store: DigitalHumanStore, project_id: str) -> DigitalHumanProfile:
    for profile in digital_store.list_for_project(project_id):
        if _is_system_preset_voice_library(profile):
            return profile
    profile = DigitalHumanProfile(
        digital_human_id=_preset_voice_library_id(project_id),
        project_id=project_id,
        name="系统预设声音库",
        avatar_source_type=AvatarSourceType.preset_avatar,
        metadata={"system_role": "preset_voice_library", "hidden_from_human_picker": True},
    )
    return digital_store.save(profile)


def _is_system_preset_voice_library(profile: DigitalHumanProfile) -> bool:
    metadata = profile.metadata if isinstance(profile.metadata, dict) else {}
    return metadata.get("system_role") == "preset_voice_library"


def _preset_voice_library_id(project_id: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", project_id).strip("_").lower() or "project"
    return f"dh_preset_voice_library_{slug[:40]}"


def _stored_preset_voice_path(settings: Settings, project_id: str, preset_id: str, filename: str) -> Path:
    return settings.storage_dir / "projects" / project_id / "preset_voice_assets" / preset_id / _safe_upload_filename(filename)


def _find_preset_voice_source(settings: Settings, filename: str) -> Path | None:
    search_dirs = [
        settings.preset_voice_assets_dir,
        settings.storage_dir / "preset_voice_assets",
        STATIC_DIR.parent / "preset_voice_assets",
        DEFAULT_PRESET_VOICE_SOURCE_DIR,
    ]
    for directory in search_dirs:
        if not directory:
            continue
        path = Path(directory) / filename
        if path.exists() and path.is_file():
            return path
    return None


def _voice_profile_sample_audio_path(settings: Settings, voice: VoiceProfile) -> Path | None:
    metadata = voice.metadata or {}
    candidates = [
        voice.sample_asset_id,
        metadata.get("sample_audio_path"),
        metadata.get("clean_voice_sample_path"),
        metadata.get("source_audio_path"),
        settings.storage_dir
        / "projects"
        / voice.project_id
        / "digital_humans"
        / voice.digital_human_id
        / "source_video"
        / "clean_voice_sample.wav",
        settings.storage_dir
        / "projects"
        / voice.project_id
        / "digital_humans"
        / voice.digital_human_id
        / "source_video"
        / "source_audio.wav",
    ]
    object_storage_upload = metadata.get("object_storage_upload")
    if isinstance(object_storage_upload, dict):
        candidates.append(object_storage_upload.get("local_copy_path"))
    source_video = metadata.get("source_video")
    if isinstance(source_video, dict):
        candidates.extend(
            [
                source_video.get("clean_voice_sample_path"),
                source_video.get("source_audio_path"),
            ]
        )
    for candidate in candidates:
        path = _safe_storage_file(settings, str(candidate) if candidate else None)
        if path:
            return path
    return None


def _decode_voice_sample_upload(request: CreateVoiceProfileRequest) -> tuple[str, str, bytes] | None:
    if not request.sample_audio_base64:
        return None
    filename = _safe_upload_filename(request.sample_audio_filename or "voice_sample.wav")
    content_type = (request.sample_audio_content_type or "application/octet-stream").lower()
    suffix = Path(filename).suffix.lower()
    allowed_suffixes = {".wav", ".mp3", ".m4a", ".aac", ".ogg", ".flac"}
    if not content_type.startswith("audio/") and suffix not in allowed_suffixes:
        raise HTTPException(status_code=400, detail="声音样本必须是 WAV、MP3、M4A、AAC、OGG 或 FLAC 音频文件。")
    try:
        file_bytes = base64.b64decode(request.sample_audio_base64, validate=True)
    except Exception as exc:  # noqa: BLE001 - malformed user upload payload.
        raise HTTPException(status_code=400, detail="声音样本内容不是有效的 base64。") from exc
    if not file_bytes:
        raise HTTPException(status_code=400, detail="声音样本不能为空。")
    if len(file_bytes) > 100 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="声音样本不能超过 100MB。")
    return filename, content_type, file_bytes


def _voice_profile_uses_sample_preview(voice: VoiceProfile) -> bool:
    voice_source = str(getattr(voice.voice_source_type, "value", voice.voice_source_type) or "").lower()
    voice_engine = str(voice.engine or "").lower().strip()
    metadata = voice.metadata if isinstance(voice.metadata, dict) else {}
    provider = str(metadata.get("provider") or "").lower().strip()
    cloud_voice_id = _voice_profile_cloud_voice_id(voice)
    if voice_source.endswith("uploaded_sample") or voice_source.endswith("preset_voice"):
        return not (
            cloud_voice_id and (voice_engine.startswith("aliyun_bailian") or provider.startswith("aliyun_bailian"))
        )
    if voice_source.endswith("source_video_audio") and not (
        voice_engine.startswith("aliyun_bailian") or provider.startswith("aliyun_bailian")
    ):
        return True
    return False


def _decode_remix_upload(upload: VideoRemixAssetUpload, *, allowed_prefixes: tuple[str, ...]) -> bytes:
    content_type = (upload.content_type or "").lower()
    if not any(content_type.startswith(prefix) for prefix in allowed_prefixes):
        allowed = " or ".join(allowed_prefixes)
        raise HTTPException(status_code=400, detail=f"上传文件类型必须是 {allowed}")
    try:
        file_bytes = base64.b64decode(upload.content_base64, validate=True)
    except Exception as exc:  # noqa: BLE001 - malformed user upload payload.
        raise HTTPException(status_code=400, detail="文件内容不是有效的 base64。") from exc
    if not file_bytes:
        raise HTTPException(status_code=400, detail="上传文件不能为空。")
    return file_bytes


def _write_remix_upload(upload: VideoRemixAssetUpload, target_dir: Path, *, allowed_prefixes: tuple[str, ...]) -> Path:
    file_bytes = _decode_remix_upload(upload, allowed_prefixes=allowed_prefixes)
    target_path = ensure_dir(target_dir) / _safe_upload_filename(upload.filename or "remix_asset")
    target_path.write_bytes(file_bytes)
    return target_path


def _selected_preview_asset_path(settings: Settings, profile: DigitalHumanProfile) -> Path | None:
    metadata = profile.metadata or {}
    source_tracking = metadata.get("source_tracking") if isinstance(metadata.get("source_tracking"), dict) else {}
    source_video = metadata.get("source_video") if isinstance(metadata.get("source_video"), dict) else {}
    candidates = [
        profile.selected_avatar_asset,
        metadata.get("selected_avatar_asset"),
        source_tracking.get("stored_path"),
        source_video.get("source_video_path"),
    ]
    for candidate in candidates:
        path = _safe_storage_file(settings, str(candidate) if candidate else None)
        if path:
            return path
    return None


def _selected_voice_preview_path(
    settings: Settings,
    digital_store: DigitalHumanStore,
    profile: DigitalHumanProfile,
    voice_profile_id: str | None,
) -> Path | None:
    if voice_profile_id:
        path = _voice_profile_preview_path(settings, digital_store, profile.project_id, voice_profile_id)
        if path:
            return path
    source_sample = _safe_storage_file(
        settings,
        str(
            digital_store.digital_human_dir(profile.project_id, profile.digital_human_id)
            / "source_video"
            / "clean_voice_sample.wav"
        ),
    )
    if source_sample:
        return source_sample
    return None


def _voice_profile_preview_path(
    settings: Settings,
    digital_store: DigitalHumanStore,
    project_id: str,
    voice_profile_id: str,
) -> Path | None:
    try:
        voice = digital_store.get_voice_profile_for_project(project_id, voice_profile_id)
    except KeyError:
        return None
    for candidate in [
        voice.sample_asset_id,
        (voice.metadata or {}).get("sample_audio_path"),
        (voice.metadata or {}).get("clean_voice_sample_path"),
    ]:
        path = _safe_storage_file(settings, str(candidate) if candidate else None)
        if path:
            return path
    test_audio = _safe_storage_file(
        settings,
        str(
            digital_store.digital_human_dir(voice.project_id, voice.digital_human_id)
            / "voice_profiles"
            / voice.voice_profile_id
            / "tests"
            / "voice_test.wav"
        ),
    )
    if test_audio:
        return test_audio
    return None


def _guess_media_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".wav":
        return "audio/wav"
    if suffix == ".mp4":
        return "video/mp4"
    if suffix == ".svg":
        return "image/svg+xml"
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def _preview_media_kind(path: Path | None) -> str:
    if not path:
        return ""
    media_type = _guess_media_type(path)
    if media_type.startswith("image/"):
        return "image"
    if media_type.startswith("video/"):
        return "video"
    if media_type.startswith("audio/"):
        return "audio"
    return ""


def _preview_url(base_path: str, path: Path | None, *, separator: str = "?") -> str:
    if not path:
        return ""
    return f"{base_path}{separator}v={path.stat().st_mtime_ns}"


def _rewrite_response(rewrite: ScriptRewrite) -> dict[str, object]:
    payload = rewrite.model_dump(mode="json")
    payload["scripts"] = rewrite.scripts
    return payload


def _find_avatar_asset(digital_store: DigitalHumanStore, digital_human_id: str, asset_id: str) -> Path:
    try:
        profile = digital_store.get(digital_human_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    root = digital_store.digital_human_dir(profile.project_id, digital_human_id) / "avatar_generations"
    matches = list(root.glob(f"*/{asset_id}.svg")) if root.exists() else []
    if not matches:
        raise HTTPException(status_code=404, detail=f"avatar asset not found: {asset_id}")
    return matches[0]


def _safe_upload_filename(filename: str) -> str:
    name = Path(filename).name.strip() or "personal_avatar"
    safe = "".join(char if char.isalnum() or char in {".", "-", "_"} else "_" for char in name)
    safe = safe.strip("._") or "personal_avatar"
    return safe[:120]


def _avatar_svg(*, title: str, prompt: str, style: str, seed: int | None, index: int) -> str:
    safe_title = html.escape(title)
    safe_prompt = html.escape(prompt[:80])
    safe_style = html.escape(style)
    safe_seed = html.escape(str(seed if seed is not None else "auto"))
    colors = [("#255E6F", "#F5D061"), ("#6C5CE7", "#00CEC9"), ("#2D3436", "#FAB1A0"), ("#0984E3", "#FDCB6E")]
    bg, accent = colors[(index - 1) % len(colors)]
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">
  <rect width="512" height="512" fill="{bg}"/>
  <circle cx="256" cy="210" r="112" fill="{accent}"/>
  <circle cx="218" cy="194" r="12" fill="#111827"/>
  <circle cx="294" cy="194" r="12" fill="#111827"/>
  <path d="M214 250 Q256 286 302 250" stroke="#111827" stroke-width="14" fill="none" stroke-linecap="round"/>
  <rect x="128" y="335" width="256" height="92" rx="24" fill="#ffffff" opacity="0.92"/>
  <text x="256" y="372" text-anchor="middle" font-size="24" font-family="Arial" fill="#111827">{safe_title}</text>
  <text x="256" y="402" text-anchor="middle" font-size="16" font-family="Arial" fill="#374151">{safe_style} / seed {safe_seed}</text>
  <text x="256" y="474" text-anchor="middle" font-size="14" font-family="Arial" fill="#ffffff">{safe_prompt}</text>
</svg>"""
