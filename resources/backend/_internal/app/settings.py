import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.llm_platforms import LLMPlatformStore


INTERNAL_PROVIDER_SECRET_KEYS = {
    "DASHSCOPE_API_KEY",
    "ELEVENLABS_API_KEY",
    "AZURE_SPEECH_KEY",
    "CUSTOM_HTTP_TTS_API_KEY",
    "FAL_API_KEY",
    "SELF_HOSTED_LIPSYNC_API_KEY",
    "SYNCSO_API_KEY",
    "PIXVERSE_API_KEY",
    "OMNIHUMAN_ACCESS_KEY",
    "OMNIHUMAN_SECRET_KEY",
    "TAVUS_API_KEY",
    "BAIDU_XILING_APP_ID",
    "BAIDU_XILING_APP_KEY",
    "HIFLY_TOKEN",
    "OBJECT_STORAGE_ACCESS_KEY_ID",
    "OBJECT_STORAGE_SECRET_ACCESS_KEY",
    "S3_ACCESS_KEY_ID",
    "S3_SECRET_ACCESS_KEY",
    "OPENAI_COMPATIBLE_API_KEY",
    "AIVO_PARSER_BASE_URL",
    "AIVO_PARSER_ENDPOINT",
    "AIVO_PARSER_TOKEN",
    "TIKHUB_BASE_URL",
    "TIKHUB_API_KEY",
    "TIKHUB_DOUYIN_ENDPOINT",
    "ISTERO_BASE_URL",
    "ISTERO_API_KEY",
    "ISTERO_DOUYIN_ENDPOINT",
    "EVIL0CTAL_DOUYIN_API_BASE_URL",
    "EVIL0CTAL_DOUYIN_API_ENDPOINT",
}


class Settings(BaseSettings):
    app_env: str = "local"
    dry_run: bool = False
    runtime_mode: str = "final"
    storage_dir: Path = Path("storage")
    third_party_dir: Path = Path("third_party")
    vendor_mode: bool = False

    pixelle_base_url: str = "http://127.0.0.1:8000"
    pixelle_enabled: bool = False
    pixelle_script_endpoint: str = "/api/content/narration"
    pixelle_video_endpoint: str = "/api/video/generate/sync"
    cloud_lipsync_enabled: bool = False
    cloud_lipsync_provider: str = "syncso"
    syncso_base_url: str = "https://api.sync.so"
    syncso_api_key: str | None = None
    syncso_model: str = "lipsync-2"
    syncso_generate_endpoint: str = "/v2/generate"
    syncso_timeout_seconds: int = 1200
    syncso_poll_interval_seconds: float = 5.0
    pixverse_base_url: str = "https://superaiapi.top"
    pixverse_api_key: str | None = None
    pixverse_model: str = "pixverse-lipsync:stable"
    pixverse_generate_endpoint: str = "/v1/video/generations"
    pixverse_task_endpoint_template: str = "/v1/video/tasks/{task_id}"
    pixverse_timeout_seconds: int = 1200
    pixverse_poll_interval_seconds: float = 5.0
    omnihuman_enabled: bool = False
    omnihuman_access_key: str | None = None
    omnihuman_secret_key: str | None = None
    omnihuman_endpoint: str = "https://visual.volcengineapi.com"
    omnihuman_region: str = "cn-north-1"
    omnihuman_service: str = "cv"
    omnihuman_version: str = "2024-06-06"
    omnihuman_req_key: str = "jimeng_realman_avatar_picture_omni_v15"
    omnihuman_output_resolution: int = 1080
    omnihuman_prompt: str = "自然口播，面带微笑，保持人物身份一致。"
    omnihuman_pe_fast_mode: bool = False
    omnihuman_timeout_seconds: int = 1200
    omnihuman_poll_interval_seconds: float = 5.0
    tavus_enabled: bool = False
    tavus_base_url: str = "https://tavusapi.com"
    tavus_api_key: str | None = None
    tavus_replica_id: str | None = None
    tavus_video_endpoint: str = "/v2/videos"
    tavus_timeout_seconds: int = 1800
    tavus_poll_interval_seconds: float = 8.0
    baidu_xiling_enabled: bool = False
    baidu_xiling_base_url: str = "https://open.xiling.baidu.com"
    baidu_xiling_app_id: str | None = None
    baidu_xiling_app_key: str | None = None
    baidu_xiling_figure_id: str | None = None
    baidu_xiling_tts_person: str | None = None
    baidu_xiling_width: int = 1080
    baidu_xiling_height: int = 1920
    baidu_xiling_transparent: bool = False
    baidu_xiling_timeout_seconds: int = 1200
    baidu_xiling_poll_interval_seconds: float = 5.0
    hifly_enabled: bool = False
    hifly_base_url: str = "https://hfw-api.hifly.cc"
    hifly_token: str | None = None
    hifly_required: bool = False
    hifly_poll_interval_seconds: float = 5.0
    hifly_timeout_seconds: int = 1800
    cloud_voice_provider: str = "edge_tts_no_clone"
    cloud_video_provider: str = "local"
    dashscope_api_key: str | None = None
    aliyun_bailian_region: str = "cn-beijing"
    aliyun_voice_model: str = "cosyvoice-v1"
    elevenlabs_api_key: str | None = None
    azure_speech_key: str | None = None
    azure_speech_endpoint: str | None = None
    custom_http_tts_base_url: str | None = None
    custom_http_tts_api_key: str | None = None
    fal_api_key: str | None = None
    fal_latentsync_model: str = "fal-ai/latentsync"
    fal_musetalk_model: str = "fal-ai/musetalk"
    self_hosted_lipsync_base_url: str | None = None
    self_hosted_lipsync_api_key: str | None = None
    duix_base_url: str = "http://127.0.0.1:8383"
    duix_enabled: bool = False
    tts_engine: str = "dryrun"
    tts_base_url: str | None = None
    tts_default_voice: str | None = None
    cosyvoice_url: str | None = None
    gpt_sovits_url: str | None = None
    musetalk_enabled: bool = False
    musetalk_root: Path = Path("third_party/MuseTalk")
    musetalk_cli_path: str | None = None
    musetalk_model_dir: str | None = None
    musetalk_version: str = "v15"
    musetalk_ffmpeg_path: str | None = None
    latentsync_enabled: bool = False
    latentsync_root: Path = Path("third_party/LatentSync")
    latentsync_cli_path: str | None = None
    latentsync_ckpt_path: str | None = None
    latentsync_config_path: str | None = None
    jianying_enabled: bool = False
    jianying_draft_root: str | None = None
    wav2lip_enabled: bool = False
    wav2lip_root: Path = Path("third_party/Wav2Lip")
    wav2lip_python: str | None = None
    wav2lip_checkpoint: Path = Path("checkpoints/wav2lip.pth")
    wav2lip_timeout_seconds: int = 600
    yy_wav2lip_enabled: bool = False
    yy_wav2lip_checkpoint: Path = Path("resource/checkpoints/yywav2lip.pth")
    yy_wav2lip_role_model_dir: str | None = None
    yy_wav2lip_timeout_seconds: int = 600
    reference_ffmpeg_path: str | None = None
    video_parser_enabled: bool = True
    video_parser_engine: str = "douyin_downloader"
    video_parser_ytdlp_path: str | None = None
    video_parser_douyin_downloader_root: Path = Path("third_party/douyin-downloader")
    python_path: str | None = None
    video_parser_cloud_provider_order: str = "aivo_proxy,tikhub,istero,evil0ctal"
    aivo_parser_base_url: str | None = None
    aivo_parser_endpoint: str = "/v1/video-parser/parse"
    aivo_parser_token: str | None = None
    tikhub_base_url: str = "https://api.tikhub.io"
    tikhub_api_key: str | None = None
    tikhub_douyin_endpoint: str = "/api/v1/hybrid/video_data"
    istero_base_url: str | None = None
    istero_api_key: str | None = None
    istero_douyin_endpoint: str = "/service/api/douyin-video-downloader"
    evil0ctal_douyin_api_base_url: str | None = None
    evil0ctal_douyin_api_endpoint: str = "/api/hybrid/video_data"
    video_parser_timeout_seconds: int = 120
    video_parser_max_download_mb: int = 500
    asr_engine: str = "funasr"
    whisper_enabled: bool = False
    funasr_enabled: bool = True
    funasr_model: str = "iic/speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-pytorch"
    funasr_model_dir: str | None = None
    funasr_device: str = "cpu"
    funasr_vad_model: str = "fsmn-vad"
    funasr_punc_model: str = "ct-punc"
    preset_voice_assets_dir: Path | None = None
    llm_engine: str = "dryrun"
    openai_compatible_enabled: bool = False
    openai_compatible_base_url: str | None = None
    openai_compatible_api_key: str | None = None
    openai_compatible_model: str = "gpt-compatible"
    local_model_enabled: bool = False
    local_model_path: str | None = None
    job_queue_backend: str = "local"
    redis_url: str | None = None
    repository_backend: str = "file"
    database_url: str | None = None
    commercial_repository_backend: str = "file"
    commercial_database_url: str | None = None
    object_storage_backend: str = "local"
    object_storage_root: Path = Path("storage/objects")
    object_storage_public_base_url: str | None = None
    object_storage_prefix: str = "aivo"
    object_storage_endpoint: str | None = None
    object_storage_bucket: str | None = None
    object_storage_region: str | None = None
    object_storage_access_key_id: str | None = None
    object_storage_secret_access_key: str | None = None
    s3_endpoint_url: str | None = None
    s3_bucket: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    commercial_admin_username: str = "xiongtuai"
    commercial_admin_password: str = ""
    commercial_admin_password_hash: str = ""
    commercial_admin_session_secret: str = ""
    commercial_admin_session_ttl_seconds: int = 86400
    commercial_admin_cookie_secure: bool = True
    commercial_login_rate_limit_per_minute: int = 5
    commercial_api_rate_limit_per_minute: int = 60
    commercial_api_base_url: str = "https://api.xiongtuai.cc"
    commercial_release_public_base_url: str = ""
    commercial_backup_retention_days: int = 14
    commercial_license_required: bool = True
    commercial_offline_grace_seconds: int = 259200

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    settings = apply_desktop_settings_overrides(Settings())
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    settings.third_party_dir.mkdir(parents=True, exist_ok=True)
    settings.object_storage_root.mkdir(parents=True, exist_ok=True)
    return settings


def apply_desktop_settings_overrides(settings: Settings) -> Settings:
    path = settings.storage_dir / "desktop" / "desktop_settings.json"
    data: dict[str, Any] = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8-sig"))
            if isinstance(loaded, dict):
                data = loaded
        except Exception:
            data = {}
    updates: dict[str, Any] = {}
    mapping: dict[str, tuple[str, type]] = {
        "runtime_mode": ("runtime_mode", str),
        "runtimeMode": ("runtime_mode", str),
        "TTS_ENGINE": ("tts_engine", str),
        "TTS_BASE_URL": ("tts_base_url", str),
        "TTS_DEFAULT_VOICE": ("tts_default_voice", str),
        "COSYVOICE_URL": ("cosyvoice_url", str),
        "GPT_SOVITS_URL": ("gpt_sovits_url", str),
        "PIXELLE_ENABLED": ("pixelle_enabled", bool),
        "PIXELLE_BASE_URL": ("pixelle_base_url", str),
        "PIXELLE_SCRIPT_ENDPOINT": ("pixelle_script_endpoint", str),
        "PIXELLE_VIDEO_ENDPOINT": ("pixelle_video_endpoint", str),
        "CLOUD_LIPSYNC_ENABLED": ("cloud_lipsync_enabled", bool),
        "CLOUD_LIPSYNC_PROVIDER": ("cloud_lipsync_provider", str),
        "SYNCSO_BASE_URL": ("syncso_base_url", str),
        "SYNCSO_API_KEY": ("syncso_api_key", str),
        "SYNCSO_MODEL": ("syncso_model", str),
        "SYNCSO_GENERATE_ENDPOINT": ("syncso_generate_endpoint", str),
        "SYNCSO_TIMEOUT_SECONDS": ("syncso_timeout_seconds", int),
        "SYNCSO_POLL_INTERVAL_SECONDS": ("syncso_poll_interval_seconds", float),
        "PIXVERSE_BASE_URL": ("pixverse_base_url", str),
        "PIXVERSE_API_KEY": ("pixverse_api_key", str),
        "PIXVERSE_MODEL": ("pixverse_model", str),
        "PIXVERSE_GENERATE_ENDPOINT": ("pixverse_generate_endpoint", str),
        "PIXVERSE_TASK_ENDPOINT_TEMPLATE": ("pixverse_task_endpoint_template", str),
        "PIXVERSE_TIMEOUT_SECONDS": ("pixverse_timeout_seconds", int),
        "PIXVERSE_POLL_INTERVAL_SECONDS": ("pixverse_poll_interval_seconds", float),
        "OMNIHUMAN_ENABLED": ("omnihuman_enabled", bool),
        "OMNIHUMAN_ACCESS_KEY": ("omnihuman_access_key", str),
        "OMNIHUMAN_SECRET_KEY": ("omnihuman_secret_key", str),
        "OMNIHUMAN_ENDPOINT": ("omnihuman_endpoint", str),
        "OMNIHUMAN_REGION": ("omnihuman_region", str),
        "OMNIHUMAN_SERVICE": ("omnihuman_service", str),
        "OMNIHUMAN_VERSION": ("omnihuman_version", str),
        "OMNIHUMAN_REQ_KEY": ("omnihuman_req_key", str),
        "OMNIHUMAN_OUTPUT_RESOLUTION": ("omnihuman_output_resolution", int),
        "OMNIHUMAN_PROMPT": ("omnihuman_prompt", str),
        "OMNIHUMAN_PE_FAST_MODE": ("omnihuman_pe_fast_mode", bool),
        "OMNIHUMAN_TIMEOUT_SECONDS": ("omnihuman_timeout_seconds", int),
        "OMNIHUMAN_POLL_INTERVAL_SECONDS": ("omnihuman_poll_interval_seconds", float),
        "TAVUS_ENABLED": ("tavus_enabled", bool),
        "TAVUS_BASE_URL": ("tavus_base_url", str),
        "TAVUS_API_KEY": ("tavus_api_key", str),
        "TAVUS_REPLICA_ID": ("tavus_replica_id", str),
        "TAVUS_VIDEO_ENDPOINT": ("tavus_video_endpoint", str),
        "TAVUS_TIMEOUT_SECONDS": ("tavus_timeout_seconds", int),
        "TAVUS_POLL_INTERVAL_SECONDS": ("tavus_poll_interval_seconds", float),
        "BAIDU_XILING_ENABLED": ("baidu_xiling_enabled", bool),
        "BAIDU_XILING_BASE_URL": ("baidu_xiling_base_url", str),
        "BAIDU_XILING_APP_ID": ("baidu_xiling_app_id", str),
        "BAIDU_XILING_APP_KEY": ("baidu_xiling_app_key", str),
        "BAIDU_XILING_FIGURE_ID": ("baidu_xiling_figure_id", str),
        "BAIDU_XILING_TTS_PERSON": ("baidu_xiling_tts_person", str),
        "BAIDU_XILING_WIDTH": ("baidu_xiling_width", int),
        "BAIDU_XILING_HEIGHT": ("baidu_xiling_height", int),
        "BAIDU_XILING_TRANSPARENT": ("baidu_xiling_transparent", bool),
        "BAIDU_XILING_TIMEOUT_SECONDS": ("baidu_xiling_timeout_seconds", int),
        "BAIDU_XILING_POLL_INTERVAL_SECONDS": ("baidu_xiling_poll_interval_seconds", float),
        "HIFLY_ENABLED": ("hifly_enabled", bool),
        "HIFLY_BASE_URL": ("hifly_base_url", str),
        "HIFLY_TOKEN": ("hifly_token", str),
        "HIFLY_REQUIRED": ("hifly_required", bool),
        "HIFLY_POLL_INTERVAL_SECONDS": ("hifly_poll_interval_seconds", float),
        "HIFLY_TIMEOUT_SECONDS": ("hifly_timeout_seconds", int),
        "VIDEO_PARSER_ENABLED": ("video_parser_enabled", bool),
        "VIDEO_PARSER_ENGINE": ("video_parser_engine", str),
        "VIDEO_PARSER_YTDLP_PATH": ("video_parser_ytdlp_path", str),
        "VIDEO_PARSER_DOUYIN_DOWNLOADER_ROOT": ("video_parser_douyin_downloader_root", Path),
        "PYTHON_PATH": ("python_path", str),
        "VIDEO_PARSER_CLOUD_PROVIDER_ORDER": ("video_parser_cloud_provider_order", str),
        "AIVO_PARSER_BASE_URL": ("aivo_parser_base_url", str),
        "AIVO_PARSER_ENDPOINT": ("aivo_parser_endpoint", str),
        "TIKHUB_BASE_URL": ("tikhub_base_url", str),
        "TIKHUB_DOUYIN_ENDPOINT": ("tikhub_douyin_endpoint", str),
        "ISTERO_BASE_URL": ("istero_base_url", str),
        "ISTERO_DOUYIN_ENDPOINT": ("istero_douyin_endpoint", str),
        "EVIL0CTAL_DOUYIN_API_BASE_URL": ("evil0ctal_douyin_api_base_url", str),
        "EVIL0CTAL_DOUYIN_API_ENDPOINT": ("evil0ctal_douyin_api_endpoint", str),
        "VIDEO_PARSER_TIMEOUT_SECONDS": ("video_parser_timeout_seconds", int),
        "VIDEO_PARSER_MAX_DOWNLOAD_MB": ("video_parser_max_download_mb", int),
        "ASR_ENGINE": ("asr_engine", str),
        "WHISPER_ENABLED": ("whisper_enabled", bool),
        "FUNASR_ENABLED": ("funasr_enabled", bool),
        "FUNASR_MODEL": ("funasr_model", str),
        "FUNASR_MODEL_DIR": ("funasr_model_dir", str),
        "FUNASR_DEVICE": ("funasr_device", str),
        "FUNASR_VAD_MODEL": ("funasr_vad_model", str),
        "FUNASR_PUNC_MODEL": ("funasr_punc_model", str),
        "CLOUD_VOICE_PROVIDER": ("cloud_voice_provider", str),
        "CLOUD_VIDEO_PROVIDER": ("cloud_video_provider", str),
        "DASHSCOPE_API_KEY": ("dashscope_api_key", str),
        "ALIYUN_BAILIAN_REGION": ("aliyun_bailian_region", str),
        "ALIYUN_VOICE_MODEL": ("aliyun_voice_model", str),
        "ELEVENLABS_API_KEY": ("elevenlabs_api_key", str),
        "AZURE_SPEECH_KEY": ("azure_speech_key", str),
        "AZURE_SPEECH_ENDPOINT": ("azure_speech_endpoint", str),
        "CUSTOM_HTTP_TTS_BASE_URL": ("custom_http_tts_base_url", str),
        "CUSTOM_HTTP_TTS_API_KEY": ("custom_http_tts_api_key", str),
        "FAL_API_KEY": ("fal_api_key", str),
        "FAL_LATENTSYNC_MODEL": ("fal_latentsync_model", str),
        "FAL_MUSETALK_MODEL": ("fal_musetalk_model", str),
        "SELF_HOSTED_LIPSYNC_BASE_URL": ("self_hosted_lipsync_base_url", str),
        "SELF_HOSTED_LIPSYNC_API_KEY": ("self_hosted_lipsync_api_key", str),
        "JIANYING_ENABLED": ("jianying_enabled", bool),
        "JIANYING_DRAFT_ROOT": ("jianying_draft_root", str),
        "OBJECT_STORAGE_BACKEND": ("object_storage_backend", str),
        "OBJECT_STORAGE_ROOT": ("object_storage_root", Path),
        "OBJECT_STORAGE_PUBLIC_BASE_URL": ("object_storage_public_base_url", str),
        "OBJECT_STORAGE_PREFIX": ("object_storage_prefix", str),
        "OBJECT_STORAGE_ENDPOINT": ("object_storage_endpoint", str),
        "OBJECT_STORAGE_BUCKET": ("object_storage_bucket", str),
        "OBJECT_STORAGE_REGION": ("object_storage_region", str),
        "OBJECT_STORAGE_ACCESS_KEY_ID": ("object_storage_access_key_id", str),
        "OBJECT_STORAGE_SECRET_ACCESS_KEY": ("object_storage_secret_access_key", str),
        "S3_ENDPOINT_URL": ("s3_endpoint_url", str),
        "S3_BUCKET": ("s3_bucket", str),
        "S3_ACCESS_KEY_ID": ("s3_access_key_id", str),
        "S3_SECRET_ACCESS_KEY": ("s3_secret_access_key", str),
        "COMMERCIAL_API_BASE_URL": ("commercial_api_base_url", str),
        "COMMERCIAL_LICENSE_REQUIRED": ("commercial_license_required", bool),
        "COMMERCIAL_OFFLINE_GRACE_SECONDS": ("commercial_offline_grace_seconds", int),
    }
    for key, (field, caster) in mapping.items():
        if key in data:
            updates[field] = _cast_desktop_setting(data[key], caster)
    if str(updates.get("runtime_mode", "")).lower() == "dry-run":
        updates["runtime_mode"] = "final"
    updates["dry_run"] = False
    effective_dry_run = False
    effective_storage_dir = Path(updates.get("storage_dir", settings.storage_dir))
    updates.update(_internal_provider_secret_updates(effective_storage_dir))
    llm_config = LLMPlatformStore(settings.storage_dir).active_openai_config()
    if not effective_dry_run and llm_config["enabled"]:
        updates.update(
            {
                "llm_engine": "openai_compatible",
                "openai_compatible_enabled": True,
                "openai_compatible_base_url": llm_config["base_url"],
                "openai_compatible_api_key": llm_config["api_key"],
                "openai_compatible_model": llm_config["model"],
            }
        )
    if not updates:
        return settings
    return settings.model_copy(update=updates)


def load_internal_provider_secrets(storage_dir: Path) -> dict[str, Any]:
    """Load server-side/provider secrets that must not be exposed in desktop settings."""
    path = storage_dir / "desktop" / "internal_provider_secrets.json"
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    if not isinstance(loaded, dict):
        return {}
    return {str(key): value for key, value in loaded.items() if str(key) in INTERNAL_PROVIDER_SECRET_KEYS}


def _internal_provider_secret_updates(storage_dir: Path) -> dict[str, Any]:
    data = load_internal_provider_secrets(storage_dir)
    if not data:
        return {}
    mapping: dict[str, tuple[str, type]] = {
        "DASHSCOPE_API_KEY": ("dashscope_api_key", str),
        "ELEVENLABS_API_KEY": ("elevenlabs_api_key", str),
        "AZURE_SPEECH_KEY": ("azure_speech_key", str),
        "CUSTOM_HTTP_TTS_API_KEY": ("custom_http_tts_api_key", str),
        "FAL_API_KEY": ("fal_api_key", str),
        "SELF_HOSTED_LIPSYNC_API_KEY": ("self_hosted_lipsync_api_key", str),
        "SYNCSO_API_KEY": ("syncso_api_key", str),
        "PIXVERSE_API_KEY": ("pixverse_api_key", str),
        "OMNIHUMAN_ACCESS_KEY": ("omnihuman_access_key", str),
        "OMNIHUMAN_SECRET_KEY": ("omnihuman_secret_key", str),
        "TAVUS_API_KEY": ("tavus_api_key", str),
        "BAIDU_XILING_APP_ID": ("baidu_xiling_app_id", str),
        "BAIDU_XILING_APP_KEY": ("baidu_xiling_app_key", str),
        "HIFLY_TOKEN": ("hifly_token", str),
        "OBJECT_STORAGE_ACCESS_KEY_ID": ("object_storage_access_key_id", str),
        "OBJECT_STORAGE_SECRET_ACCESS_KEY": ("object_storage_secret_access_key", str),
        "S3_ACCESS_KEY_ID": ("s3_access_key_id", str),
        "S3_SECRET_ACCESS_KEY": ("s3_secret_access_key", str),
        "OPENAI_COMPATIBLE_API_KEY": ("openai_compatible_api_key", str),
        "AIVO_PARSER_BASE_URL": ("aivo_parser_base_url", str),
        "AIVO_PARSER_ENDPOINT": ("aivo_parser_endpoint", str),
        "AIVO_PARSER_TOKEN": ("aivo_parser_token", str),
        "TIKHUB_BASE_URL": ("tikhub_base_url", str),
        "TIKHUB_API_KEY": ("tikhub_api_key", str),
        "TIKHUB_DOUYIN_ENDPOINT": ("tikhub_douyin_endpoint", str),
        "ISTERO_BASE_URL": ("istero_base_url", str),
        "ISTERO_API_KEY": ("istero_api_key", str),
        "ISTERO_DOUYIN_ENDPOINT": ("istero_douyin_endpoint", str),
        "EVIL0CTAL_DOUYIN_API_BASE_URL": ("evil0ctal_douyin_api_base_url", str),
        "EVIL0CTAL_DOUYIN_API_ENDPOINT": ("evil0ctal_douyin_api_endpoint", str),
    }
    updates: dict[str, Any] = {}
    for key, value in data.items():
        if key in mapping:
            field, caster = mapping[key]
            updates[field] = _cast_desktop_setting(value, caster)
    return updates


def _cast_desktop_setting(value: Any, caster: type) -> Any:
    if caster is bool:
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)
    if caster is int:
        return int(value)
    if caster is float:
        return float(value)
    if caster is str:
        return "" if value is None else str(value)
    if caster is Path:
        return Path(value)
    return value
