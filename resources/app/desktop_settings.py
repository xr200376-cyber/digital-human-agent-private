from __future__ import annotations

import os
import importlib.util
import shutil
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urljoin

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.adapters.asr import FUNASR_PUNC_MODEL, PARAFORMER_ZH_LONG_AUDIO_MODEL
from app.cloud_providers import build_cloud_provider_configs
from app.settings import Settings, load_internal_provider_secrets
from app.utils.files import ensure_dir, read_json, write_json


RuntimeMode = Literal["dry-run", "compat", "standard", "final", "batch"]

SECRET_DESKTOP_SETTING_KEYS = {
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
}


class DesktopSettingsConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    selected_preset: str = "custom"
    tts_provider: str = "dryrun"
    digital_human_engine: str = "auto"
    editing_output: str = "mp4_only"
    runtime_mode: RuntimeMode = "final"
    storage_path: str = Field("storage", alias="STORAGE_DIR")
    python_path: str = Field("python", alias="PYTHON_PATH")

    tts_engine: str = Field("dryrun", alias="TTS_ENGINE")
    tts_base_url: str = Field("", alias="TTS_BASE_URL")
    tts_default_voice: str = Field("", alias="TTS_DEFAULT_VOICE")
    cosyvoice_url: str = Field("", alias="COSYVOICE_URL")
    gpt_sovits_url: str = Field("", alias="GPT_SOVITS_URL")

    pixelle_enabled: bool = Field(False, alias="PIXELLE_ENABLED")
    pixelle_base_url: str = Field("http://127.0.0.1:8000", alias="PIXELLE_BASE_URL")
    pixelle_script_endpoint: str = Field("/api/content/narration", alias="PIXELLE_SCRIPT_ENDPOINT")
    pixelle_video_endpoint: str = Field("/api/video/generate/sync", alias="PIXELLE_VIDEO_ENDPOINT")

    cloud_lipsync_enabled: bool = Field(False, alias="CLOUD_LIPSYNC_ENABLED")
    cloud_lipsync_provider: str = Field("syncso", alias="CLOUD_LIPSYNC_PROVIDER")
    syncso_base_url: str = Field("https://api.sync.so", alias="SYNCSO_BASE_URL")
    syncso_api_key: str = Field("", alias="SYNCSO_API_KEY")
    syncso_model: str = Field("lipsync-2", alias="SYNCSO_MODEL")
    syncso_generate_endpoint: str = Field("/v2/generate", alias="SYNCSO_GENERATE_ENDPOINT")
    syncso_timeout_seconds: int = Field(1200, alias="SYNCSO_TIMEOUT_SECONDS")
    syncso_poll_interval_seconds: float = Field(5.0, alias="SYNCSO_POLL_INTERVAL_SECONDS")
    pixverse_base_url: str = Field("https://superaiapi.top", alias="PIXVERSE_BASE_URL")
    pixverse_api_key: str = Field("", alias="PIXVERSE_API_KEY")
    pixverse_model: str = Field("pixverse-lipsync:stable", alias="PIXVERSE_MODEL")
    pixverse_generate_endpoint: str = Field("/v1/video/generations", alias="PIXVERSE_GENERATE_ENDPOINT")
    pixverse_task_endpoint_template: str = Field("/v1/video/tasks/{task_id}", alias="PIXVERSE_TASK_ENDPOINT_TEMPLATE")
    pixverse_timeout_seconds: int = Field(1200, alias="PIXVERSE_TIMEOUT_SECONDS")
    pixverse_poll_interval_seconds: float = Field(5.0, alias="PIXVERSE_POLL_INTERVAL_SECONDS")
    omnihuman_enabled: bool = Field(False, alias="OMNIHUMAN_ENABLED")
    omnihuman_access_key: str = Field("", alias="OMNIHUMAN_ACCESS_KEY")
    omnihuman_secret_key: str = Field("", alias="OMNIHUMAN_SECRET_KEY")
    omnihuman_endpoint: str = Field("https://visual.volcengineapi.com", alias="OMNIHUMAN_ENDPOINT")
    omnihuman_region: str = Field("cn-north-1", alias="OMNIHUMAN_REGION")
    omnihuman_service: str = Field("cv", alias="OMNIHUMAN_SERVICE")
    omnihuman_version: str = Field("2024-06-06", alias="OMNIHUMAN_VERSION")
    omnihuman_req_key: str = Field("jimeng_realman_avatar_picture_omni_v15", alias="OMNIHUMAN_REQ_KEY")
    omnihuman_output_resolution: int = Field(1080, alias="OMNIHUMAN_OUTPUT_RESOLUTION")
    omnihuman_prompt: str = Field("自然口播，面带微笑，保持人物身份一致。", alias="OMNIHUMAN_PROMPT")
    omnihuman_pe_fast_mode: bool = Field(False, alias="OMNIHUMAN_PE_FAST_MODE")
    omnihuman_timeout_seconds: int = Field(1200, alias="OMNIHUMAN_TIMEOUT_SECONDS")
    omnihuman_poll_interval_seconds: float = Field(5.0, alias="OMNIHUMAN_POLL_INTERVAL_SECONDS")
    tavus_enabled: bool = Field(False, alias="TAVUS_ENABLED")
    tavus_base_url: str = Field("https://tavusapi.com", alias="TAVUS_BASE_URL")
    tavus_api_key: str = Field("", alias="TAVUS_API_KEY")
    tavus_replica_id: str = Field("", alias="TAVUS_REPLICA_ID")
    tavus_video_endpoint: str = Field("/v2/videos", alias="TAVUS_VIDEO_ENDPOINT")
    tavus_timeout_seconds: int = Field(1800, alias="TAVUS_TIMEOUT_SECONDS")
    tavus_poll_interval_seconds: float = Field(8.0, alias="TAVUS_POLL_INTERVAL_SECONDS")
    baidu_xiling_enabled: bool = Field(False, alias="BAIDU_XILING_ENABLED")
    baidu_xiling_base_url: str = Field("https://open.xiling.baidu.com", alias="BAIDU_XILING_BASE_URL")
    baidu_xiling_app_id: str = Field("", alias="BAIDU_XILING_APP_ID")
    baidu_xiling_app_key: str = Field("", alias="BAIDU_XILING_APP_KEY")
    baidu_xiling_figure_id: str = Field("", alias="BAIDU_XILING_FIGURE_ID")
    baidu_xiling_tts_person: str = Field("", alias="BAIDU_XILING_TTS_PERSON")
    baidu_xiling_width: int = Field(1080, alias="BAIDU_XILING_WIDTH")
    baidu_xiling_height: int = Field(1920, alias="BAIDU_XILING_HEIGHT")
    baidu_xiling_transparent: bool = Field(False, alias="BAIDU_XILING_TRANSPARENT")
    baidu_xiling_timeout_seconds: int = Field(1200, alias="BAIDU_XILING_TIMEOUT_SECONDS")
    baidu_xiling_poll_interval_seconds: float = Field(5.0, alias="BAIDU_XILING_POLL_INTERVAL_SECONDS")
    hifly_enabled: bool = Field(False, alias="HIFLY_ENABLED")
    hifly_base_url: str = Field("https://hfw-api.hifly.cc", alias="HIFLY_BASE_URL")
    hifly_token: str = Field("", alias="HIFLY_TOKEN")
    hifly_required: bool = Field(False, alias="HIFLY_REQUIRED")
    hifly_poll_interval_seconds: float = Field(5.0, alias="HIFLY_POLL_INTERVAL_SECONDS")
    hifly_timeout_seconds: int = Field(1800, alias="HIFLY_TIMEOUT_SECONDS")
    video_parser_enabled: bool = Field(True, alias="VIDEO_PARSER_ENABLED")
    video_parser_engine: str = Field("douyin_downloader", alias="VIDEO_PARSER_ENGINE")
    video_parser_ytdlp_path: str = Field("", alias="VIDEO_PARSER_YTDLP_PATH")
    video_parser_douyin_downloader_root: str = Field(
        "third_party/douyin-downloader", alias="VIDEO_PARSER_DOUYIN_DOWNLOADER_ROOT"
    )
    video_parser_cloud_provider_order: str = Field(
        "aivo_proxy,tikhub,istero,evil0ctal", alias="VIDEO_PARSER_CLOUD_PROVIDER_ORDER"
    )
    aivo_parser_base_url: str = Field("", alias="AIVO_PARSER_BASE_URL")
    aivo_parser_endpoint: str = Field("/v1/video-parser/parse", alias="AIVO_PARSER_ENDPOINT")
    tikhub_base_url: str = Field("https://api.tikhub.io", alias="TIKHUB_BASE_URL")
    tikhub_douyin_endpoint: str = Field("/api/v1/hybrid/video_data", alias="TIKHUB_DOUYIN_ENDPOINT")
    istero_base_url: str = Field("", alias="ISTERO_BASE_URL")
    istero_douyin_endpoint: str = Field("/service/api/douyin-video-downloader", alias="ISTERO_DOUYIN_ENDPOINT")
    evil0ctal_douyin_api_base_url: str = Field("", alias="EVIL0CTAL_DOUYIN_API_BASE_URL")
    evil0ctal_douyin_api_endpoint: str = Field("/api/hybrid/video_data", alias="EVIL0CTAL_DOUYIN_API_ENDPOINT")
    video_parser_timeout_seconds: int = Field(120, alias="VIDEO_PARSER_TIMEOUT_SECONDS")
    video_parser_max_download_mb: int = Field(500, alias="VIDEO_PARSER_MAX_DOWNLOAD_MB")
    asr_engine: str = Field("funasr", alias="ASR_ENGINE")
    whisper_enabled: bool = Field(False, alias="WHISPER_ENABLED")
    funasr_enabled: bool = Field(True, alias="FUNASR_ENABLED")
    funasr_model: str = Field(PARAFORMER_ZH_LONG_AUDIO_MODEL, alias="FUNASR_MODEL")
    funasr_model_dir: str = Field("", alias="FUNASR_MODEL_DIR")
    funasr_device: str = Field("cpu", alias="FUNASR_DEVICE")
    funasr_vad_model: str = Field("fsmn-vad", alias="FUNASR_VAD_MODEL")
    funasr_punc_model: str = Field(FUNASR_PUNC_MODEL, alias="FUNASR_PUNC_MODEL")

    cloud_voice_provider: str = Field("edge_tts_no_clone", alias="CLOUD_VOICE_PROVIDER")
    cloud_video_provider: str = Field("local", alias="CLOUD_VIDEO_PROVIDER")
    dashscope_api_key: str = Field("", alias="DASHSCOPE_API_KEY")
    aliyun_bailian_region: str = Field("cn-beijing", alias="ALIYUN_BAILIAN_REGION")
    aliyun_voice_model: str = Field("cosyvoice-v1", alias="ALIYUN_VOICE_MODEL")
    elevenlabs_api_key: str = Field("", alias="ELEVENLABS_API_KEY")
    azure_speech_key: str = Field("", alias="AZURE_SPEECH_KEY")
    azure_speech_endpoint: str = Field("", alias="AZURE_SPEECH_ENDPOINT")
    custom_http_tts_base_url: str = Field("", alias="CUSTOM_HTTP_TTS_BASE_URL")
    custom_http_tts_api_key: str = Field("", alias="CUSTOM_HTTP_TTS_API_KEY")
    fal_api_key: str = Field("", alias="FAL_API_KEY")
    fal_latentsync_model: str = Field("fal-ai/latentsync", alias="FAL_LATENTSYNC_MODEL")
    fal_musetalk_model: str = Field("fal-ai/musetalk", alias="FAL_MUSETALK_MODEL")
    self_hosted_lipsync_base_url: str = Field("", alias="SELF_HOSTED_LIPSYNC_BASE_URL")
    self_hosted_lipsync_api_key: str = Field("", alias="SELF_HOSTED_LIPSYNC_API_KEY")

    wav2lip_enabled: bool = Field(False, alias="WAV2LIP_ENABLED")
    wav2lip_root: str = Field("third_party/Wav2Lip", alias="WAV2LIP_ROOT")
    wav2lip_checkpoint: str = Field("checkpoints/wav2lip.pth", alias="WAV2LIP_CHECKPOINT")

    yy_wav2lip_enabled: bool = Field(False, alias="YY_WAV2LIP_ENABLED")
    yy_wav2lip_checkpoint: str = Field("resource/checkpoints/yywav2lip.pth", alias="YY_WAV2LIP_CHECKPOINT")
    yy_wav2lip_role_model_dir: str = Field("", alias="YY_WAV2LIP_ROLE_MODEL_DIR")

    musetalk_enabled: bool = Field(False, alias="MUSETALK_ENABLED")
    musetalk_root: str = Field("third_party/MuseTalk", alias="MUSETALK_ROOT")
    musetalk_model_dir: str = Field("", alias="MUSETALK_MODEL_DIR")

    latentsync_enabled: bool = Field(False, alias="LATENTSYNC_ENABLED")
    latentsync_root: str = Field("third_party/LatentSync", alias="LATENTSYNC_ROOT")
    latentsync_checkpoint: str = Field("", alias="LATENTSYNC_CHECKPOINT")
    latentsync_unet_config: str = Field("", alias="LATENTSYNC_UNET_CONFIG")

    jianying_enabled: bool = Field(False, alias="JIANYING_ENABLED")
    jianying_draft_root: str = Field("", alias="JIANYING_DRAFT_ROOT")

    duix_enabled: bool = Field(False, alias="DUIX_ENABLED")
    duix_base_url: str = Field("http://127.0.0.1:8383", alias="DUIX_BASE_URL")
    object_storage_backend: str = Field("local", alias="OBJECT_STORAGE_BACKEND")
    object_storage_root: str = Field("storage/objects", alias="OBJECT_STORAGE_ROOT")
    object_storage_public_base_url: str = Field("", alias="OBJECT_STORAGE_PUBLIC_BASE_URL")
    object_storage_prefix: str = Field("aivo", alias="OBJECT_STORAGE_PREFIX")
    object_storage_endpoint: str = Field("", alias="OBJECT_STORAGE_ENDPOINT")
    object_storage_bucket: str = Field("", alias="OBJECT_STORAGE_BUCKET")
    object_storage_region: str = Field("", alias="OBJECT_STORAGE_REGION")
    object_storage_access_key_id: str = Field("", alias="OBJECT_STORAGE_ACCESS_KEY_ID")
    object_storage_secret_access_key: str = Field("", alias="OBJECT_STORAGE_SECRET_ACCESS_KEY")

    def as_env(self) -> str:
        lines = [f"RUNTIME_MODE={self.runtime_mode}"]
        skipped_keys = {"runtime_mode", "selected_preset", "tts_provider", "digital_human_engine", "editing_output"}
        for key, value in self.model_dump(by_alias=True).items():
            if key in skipped_keys:
                continue
            if key in SECRET_DESKTOP_SETTING_KEYS:
                continue
            if isinstance(value, bool):
                value = "true" if value else "false"
            lines.append(f"{key}={value}")
        return "\n".join(lines) + "\n"


class DesktopSettingsStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.path = settings.storage_dir / "desktop" / "desktop_settings.json"

    def default(self) -> DesktopSettingsConfig:
        return DesktopSettingsConfig(
            runtime_mode=("dry-run" if self.settings.dry_run else self.settings.runtime_mode),
            STORAGE_DIR=str(self.settings.storage_dir),
            TTS_ENGINE=self.settings.tts_engine,
            TTS_BASE_URL=self.settings.tts_base_url or "",
            TTS_DEFAULT_VOICE=self.settings.tts_default_voice or "",
            COSYVOICE_URL=self.settings.cosyvoice_url or "",
            GPT_SOVITS_URL=self.settings.gpt_sovits_url or "",
            PIXELLE_ENABLED=self.settings.pixelle_enabled,
            PIXELLE_BASE_URL=self.settings.pixelle_base_url,
            PIXELLE_SCRIPT_ENDPOINT=self.settings.pixelle_script_endpoint,
            PIXELLE_VIDEO_ENDPOINT=self.settings.pixelle_video_endpoint,
            CLOUD_LIPSYNC_ENABLED=self.settings.cloud_lipsync_enabled,
            CLOUD_LIPSYNC_PROVIDER=self.settings.cloud_lipsync_provider,
            SYNCSO_BASE_URL=self.settings.syncso_base_url,
            SYNCSO_API_KEY=self.settings.syncso_api_key or "",
            SYNCSO_MODEL=self.settings.syncso_model,
            SYNCSO_GENERATE_ENDPOINT=self.settings.syncso_generate_endpoint,
            SYNCSO_TIMEOUT_SECONDS=self.settings.syncso_timeout_seconds,
            SYNCSO_POLL_INTERVAL_SECONDS=self.settings.syncso_poll_interval_seconds,
            PIXVERSE_BASE_URL=self.settings.pixverse_base_url,
            PIXVERSE_API_KEY=self.settings.pixverse_api_key or "",
            PIXVERSE_MODEL=self.settings.pixverse_model,
            PIXVERSE_GENERATE_ENDPOINT=self.settings.pixverse_generate_endpoint,
            PIXVERSE_TASK_ENDPOINT_TEMPLATE=self.settings.pixverse_task_endpoint_template,
            PIXVERSE_TIMEOUT_SECONDS=self.settings.pixverse_timeout_seconds,
            PIXVERSE_POLL_INTERVAL_SECONDS=self.settings.pixverse_poll_interval_seconds,
            OMNIHUMAN_ENABLED=self.settings.omnihuman_enabled,
            OMNIHUMAN_ACCESS_KEY=self.settings.omnihuman_access_key or "",
            OMNIHUMAN_SECRET_KEY=self.settings.omnihuman_secret_key or "",
            OMNIHUMAN_ENDPOINT=self.settings.omnihuman_endpoint,
            OMNIHUMAN_REGION=self.settings.omnihuman_region,
            OMNIHUMAN_SERVICE=self.settings.omnihuman_service,
            OMNIHUMAN_VERSION=self.settings.omnihuman_version,
            OMNIHUMAN_REQ_KEY=self.settings.omnihuman_req_key,
            OMNIHUMAN_OUTPUT_RESOLUTION=self.settings.omnihuman_output_resolution,
            OMNIHUMAN_PROMPT=self.settings.omnihuman_prompt,
            OMNIHUMAN_PE_FAST_MODE=self.settings.omnihuman_pe_fast_mode,
            OMNIHUMAN_TIMEOUT_SECONDS=self.settings.omnihuman_timeout_seconds,
            OMNIHUMAN_POLL_INTERVAL_SECONDS=self.settings.omnihuman_poll_interval_seconds,
            TAVUS_ENABLED=self.settings.tavus_enabled,
            TAVUS_BASE_URL=self.settings.tavus_base_url,
            TAVUS_API_KEY=self.settings.tavus_api_key or "",
            TAVUS_REPLICA_ID=self.settings.tavus_replica_id or "",
            TAVUS_VIDEO_ENDPOINT=self.settings.tavus_video_endpoint,
            TAVUS_TIMEOUT_SECONDS=self.settings.tavus_timeout_seconds,
            TAVUS_POLL_INTERVAL_SECONDS=self.settings.tavus_poll_interval_seconds,
            BAIDU_XILING_ENABLED=self.settings.baidu_xiling_enabled,
            BAIDU_XILING_BASE_URL=self.settings.baidu_xiling_base_url,
            BAIDU_XILING_APP_ID=self.settings.baidu_xiling_app_id or "",
            BAIDU_XILING_APP_KEY=self.settings.baidu_xiling_app_key or "",
            BAIDU_XILING_FIGURE_ID=self.settings.baidu_xiling_figure_id or "",
            BAIDU_XILING_TTS_PERSON=self.settings.baidu_xiling_tts_person or "",
            BAIDU_XILING_WIDTH=self.settings.baidu_xiling_width,
            BAIDU_XILING_HEIGHT=self.settings.baidu_xiling_height,
            BAIDU_XILING_TRANSPARENT=self.settings.baidu_xiling_transparent,
            BAIDU_XILING_TIMEOUT_SECONDS=self.settings.baidu_xiling_timeout_seconds,
            BAIDU_XILING_POLL_INTERVAL_SECONDS=self.settings.baidu_xiling_poll_interval_seconds,
            HIFLY_ENABLED=self.settings.hifly_enabled,
            HIFLY_BASE_URL=self.settings.hifly_base_url,
            HIFLY_TOKEN=self.settings.hifly_token or "",
            HIFLY_REQUIRED=self.settings.hifly_required,
            HIFLY_POLL_INTERVAL_SECONDS=self.settings.hifly_poll_interval_seconds,
            HIFLY_TIMEOUT_SECONDS=self.settings.hifly_timeout_seconds,
            VIDEO_PARSER_ENABLED=self.settings.video_parser_enabled,
            VIDEO_PARSER_ENGINE=self.settings.video_parser_engine,
            VIDEO_PARSER_YTDLP_PATH=self.settings.video_parser_ytdlp_path or "",
            VIDEO_PARSER_DOUYIN_DOWNLOADER_ROOT=str(self.settings.video_parser_douyin_downloader_root or ""),
            VIDEO_PARSER_CLOUD_PROVIDER_ORDER=self.settings.video_parser_cloud_provider_order,
            AIVO_PARSER_BASE_URL=self.settings.aivo_parser_base_url or "",
            AIVO_PARSER_ENDPOINT=self.settings.aivo_parser_endpoint,
            TIKHUB_BASE_URL=self.settings.tikhub_base_url,
            TIKHUB_DOUYIN_ENDPOINT=self.settings.tikhub_douyin_endpoint,
            ISTERO_BASE_URL=self.settings.istero_base_url or "",
            ISTERO_DOUYIN_ENDPOINT=self.settings.istero_douyin_endpoint,
            EVIL0CTAL_DOUYIN_API_BASE_URL=self.settings.evil0ctal_douyin_api_base_url or "",
            EVIL0CTAL_DOUYIN_API_ENDPOINT=self.settings.evil0ctal_douyin_api_endpoint,
            VIDEO_PARSER_TIMEOUT_SECONDS=self.settings.video_parser_timeout_seconds,
            VIDEO_PARSER_MAX_DOWNLOAD_MB=self.settings.video_parser_max_download_mb,
            ASR_ENGINE=self.settings.asr_engine,
            WHISPER_ENABLED=self.settings.whisper_enabled,
            FUNASR_ENABLED=self.settings.funasr_enabled,
            FUNASR_MODEL=self.settings.funasr_model,
            FUNASR_MODEL_DIR=self.settings.funasr_model_dir or "",
            FUNASR_DEVICE=self.settings.funasr_device,
            FUNASR_VAD_MODEL=self.settings.funasr_vad_model,
            FUNASR_PUNC_MODEL=self.settings.funasr_punc_model,
            CLOUD_VOICE_PROVIDER=self.settings.cloud_voice_provider,
            CLOUD_VIDEO_PROVIDER=self.settings.cloud_video_provider,
            DASHSCOPE_API_KEY=self.settings.dashscope_api_key or "",
            ALIYUN_BAILIAN_REGION=self.settings.aliyun_bailian_region,
            ALIYUN_VOICE_MODEL=self.settings.aliyun_voice_model,
            ELEVENLABS_API_KEY=self.settings.elevenlabs_api_key or "",
            AZURE_SPEECH_KEY=self.settings.azure_speech_key or "",
            AZURE_SPEECH_ENDPOINT=self.settings.azure_speech_endpoint or "",
            CUSTOM_HTTP_TTS_BASE_URL=self.settings.custom_http_tts_base_url or "",
            CUSTOM_HTTP_TTS_API_KEY=self.settings.custom_http_tts_api_key or "",
            FAL_API_KEY=self.settings.fal_api_key or "",
            FAL_LATENTSYNC_MODEL=self.settings.fal_latentsync_model,
            FAL_MUSETALK_MODEL=self.settings.fal_musetalk_model,
            SELF_HOSTED_LIPSYNC_BASE_URL=self.settings.self_hosted_lipsync_base_url or "",
            SELF_HOSTED_LIPSYNC_API_KEY=self.settings.self_hosted_lipsync_api_key or "",
            WAV2LIP_ENABLED=self.settings.wav2lip_enabled,
            WAV2LIP_ROOT=str(self.settings.wav2lip_root),
            WAV2LIP_CHECKPOINT=str(self.settings.wav2lip_checkpoint),
            YY_WAV2LIP_ENABLED=self.settings.yy_wav2lip_enabled,
            YY_WAV2LIP_CHECKPOINT=str(self.settings.yy_wav2lip_checkpoint),
            YY_WAV2LIP_ROLE_MODEL_DIR=self.settings.yy_wav2lip_role_model_dir or "",
            MUSETALK_ENABLED=self.settings.musetalk_enabled,
            MUSETALK_ROOT=str(self.settings.musetalk_root),
            MUSETALK_MODEL_DIR=self.settings.musetalk_model_dir or "",
            LATENTSYNC_ENABLED=self.settings.latentsync_enabled,
            LATENTSYNC_ROOT=str(self.settings.latentsync_root),
            LATENTSYNC_CHECKPOINT=self.settings.latentsync_ckpt_path or "",
            LATENTSYNC_UNET_CONFIG=self.settings.latentsync_config_path or "",
            JIANYING_ENABLED=self.settings.jianying_enabled,
            JIANYING_DRAFT_ROOT=self.settings.jianying_draft_root or "",
            DUIX_ENABLED=self.settings.duix_enabled,
            DUIX_BASE_URL=self.settings.duix_base_url,
            OBJECT_STORAGE_BACKEND=self.settings.object_storage_backend,
            OBJECT_STORAGE_ROOT=str(self.settings.object_storage_root),
            OBJECT_STORAGE_PUBLIC_BASE_URL=self.settings.object_storage_public_base_url or "",
            OBJECT_STORAGE_PREFIX=self.settings.object_storage_prefix,
            OBJECT_STORAGE_ENDPOINT=self.settings.object_storage_endpoint or self.settings.s3_endpoint_url or "",
            OBJECT_STORAGE_BUCKET=self.settings.object_storage_bucket or self.settings.s3_bucket or "",
            OBJECT_STORAGE_REGION=self.settings.object_storage_region or "",
            OBJECT_STORAGE_ACCESS_KEY_ID=self.settings.object_storage_access_key_id or self.settings.s3_access_key_id or "",
            OBJECT_STORAGE_SECRET_ACCESS_KEY=self.settings.object_storage_secret_access_key or self.settings.s3_secret_access_key or "",
        )

    def load(self) -> DesktopSettingsConfig:
        if not self.path.exists():
            return self.default()
        data = read_json(self.path)
        if isinstance(data, dict):
            if data.get("runtime_mode") == "dry-run":
                data["runtime_mode"] = "final"
            if data.get("runtimeMode") == "dry-run":
                data["runtimeMode"] = "final"
            data["dryRun"] = False
            data["DRY_RUN"] = False
            hidden = load_internal_provider_secrets(self.settings.storage_dir)
            for key in SECRET_DESKTOP_SETTING_KEYS:
                if not data.get(key) and hidden.get(key):
                    data[key] = hidden[key]
        return DesktopSettingsConfig.model_validate(data)

    def save(self, config: DesktopSettingsConfig) -> DesktopSettingsConfig:
        ensure_dir(self.path.parent)
        config = self.with_preserved_secrets(config)
        write_json(self.path, config.model_dump(by_alias=True))
        return config

    def with_preserved_secrets(self, config: DesktopSettingsConfig) -> DesktopSettingsConfig:
        data = config.model_dump(by_alias=True)
        existing = read_json(self.path) if self.path.exists() else {}
        if not isinstance(existing, dict):
            existing = {}
        hidden = load_internal_provider_secrets(self.settings.storage_dir)
        for key in SECRET_DESKTOP_SETTING_KEYS:
            if not data.get(key) and hidden.get(key):
                data[key] = hidden[key]
            if not data.get(key) and existing.get(key):
                data[key] = existing[key]
        return DesktopSettingsConfig.model_validate(data)


def validate_desktop_settings(config: DesktopSettingsConfig, *, repository_root: Path) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, status: str, message: str, *, required: bool = False) -> None:
        checks.append({"name": name, "status": status, "message": message, "required": required})

    add("real_runtime", "green", "正式运行模式已启用；不会使用演示转写模板。")
    if (
        config.runtime_mode in {"compat", "standard", "final"}
        and config.tts_engine.lower() in {"", "dryrun", "dry-run"}
        and not config.tavus_enabled
        and os.getenv("ALLOW_DRYRUN_TTS_IN_REAL_MODE", "").lower() not in {"1", "true", "yes", "on"}
    ):
        add(
            "TTS_ENGINE",
            "red",
            "当前仍使用占位声音，不是真实 TTS。请选择 Edge/阿里云/微软/CosyVoice，或显式设置 ALLOW_DRYRUN_TTS_IN_REAL_MODE=true。",
            required=True,
        )

    tts_engine = config.tts_engine.lower()
    _check_url(checks, "TTS_BASE_URL", config.tts_base_url, tts_engine in {"http", "generic_http"})
    _check_url(checks, "COSYVOICE_URL", config.cosyvoice_url or config.tts_base_url, tts_engine in {"cosyvoice", "cosyvoice_http"})
    _check_url(
        checks,
        "GPT_SOVITS_URL",
        config.gpt_sovits_url or config.tts_base_url,
        tts_engine in {"gpt-sovits", "gpt_sovits", "gpt_sovits_http", "gpt-sovits-http"},
    )
    _check_url(checks, "PIXELLE_BASE_URL", config.pixelle_base_url, config.pixelle_enabled, config.pixelle_script_endpoint)
    _check_cloud_lipsync(checks, config)
    _check_omnihuman(checks, config)
    _check_tavus(checks, config)
    _check_cloud_providers(checks, config)
    _check_video_parser(checks, config, repository_root=repository_root)
    _check_funasr_subtitles(checks, config)
    _check_object_storage(checks, config)
    _check_url(checks, "DUIX_BASE_URL", config.duix_base_url, config.duix_enabled)

    _check_path(checks, "WAV2LIP_ROOT", config.wav2lip_root, config.wav2lip_enabled, kind="dir")
    _check_path(checks, "WAV2LIP_CHECKPOINT", config.wav2lip_checkpoint, config.wav2lip_enabled, kind="file")
    _check_path(checks, "YY_WAV2LIP_CHECKPOINT", config.yy_wav2lip_checkpoint, config.yy_wav2lip_enabled, kind="file")
    _check_path(checks, "YY_WAV2LIP_ROLE_MODEL_DIR", config.yy_wav2lip_role_model_dir, config.yy_wav2lip_enabled, kind="dir")
    _check_path(checks, "MUSETALK_ROOT", config.musetalk_root, config.musetalk_enabled, kind="dir")
    _check_path(checks, "MUSETALK_MODEL_DIR", config.musetalk_model_dir, config.musetalk_enabled, kind="dir")
    _check_path(checks, "LATENTSYNC_ROOT", config.latentsync_root, config.latentsync_enabled, kind="dir")
    _check_path(checks, "LATENTSYNC_CHECKPOINT", config.latentsync_checkpoint, config.latentsync_enabled, kind="file")
    _check_path(checks, "LATENTSYNC_UNET_CONFIG", config.latentsync_unet_config, config.latentsync_enabled, kind="file")
    _check_path(checks, "JIANYING_DRAFT_ROOT", config.jianying_draft_root, config.jianying_enabled, kind="dir")

    weight_violations = _repo_model_weight_violations(repository_root)
    if weight_violations:
        add("repository_model_weight_policy", "red", "仓库源码目录中发现疑似模型权重或角色模型文件：" + ", ".join(weight_violations[:8]), required=True)
    else:
        add("repository_model_weight_policy", "green", "仓库源码目录中未发现模型权重、ONNX 或角色模型 pkl 文件。")

    overall = "green"
    if any(item["status"] == "red" for item in checks):
        overall = "red"
    elif any(item["status"] == "yellow" for item in checks):
        overall = "yellow"

    return {
        "overall_status": overall,
        "runtime_mode": config.runtime_mode,
        "dry_run_available": True,
        "checks": checks,
        "env_output": config.as_env(),
    }


def alignment_report(config: DesktopSettingsConfig, validation: dict[str, Any]) -> dict[str, Any]:
    red_items = [item["name"] for item in validation["checks"] if item["status"] == "red"]
    yellow_items = [item["name"] for item in validation["checks"] if item["status"] == "yellow"]
    missing_items = red_items + yellow_items
    return {
        "content_production_alignment": _alignment_status(
            config.pixelle_enabled and not any(name.startswith("PIXELLE") for name in red_items),
            "Pixelle HTTP 脚本/视频接口已配置。",
            "Pixelle 未启用或不可访问；当前仍可使用 dry-run 脚本生成。",
        ),
        "digital_human_alignment": _alignment_status(
            any(
                [
                    config.cloud_lipsync_enabled,
                    config.omnihuman_enabled,
                    config.tavus_enabled,
                    config.baidu_xiling_enabled or config.cloud_video_provider == "baidu_xiling",
                    config.hifly_enabled or config.cloud_video_provider == "hifly",
                    config.wav2lip_enabled,
                    config.yy_wav2lip_enabled,
                    config.musetalk_enabled,
                    config.latentsync_enabled,
                    config.duix_enabled,
                ]
            )
            and not any(
                name.startswith(("SYNCSO", "PIXVERSE", "CLOUD_LIPSYNC", "OMNIHUMAN", "TAVUS", "BAIDU_XILING", "HIFLY", "WAV2LIP", "YY_WAV2LIP", "MUSETALK", "LATENTSYNC", "DUIX"))
                for name in red_items
            ),
            "至少一个真实数字人/口型同步引擎已配置。",
            "真实数字人引擎需要本地模型文件或 HTTP 服务配置。",
        ),
        "jianying_alignment": _alignment_status(
            config.jianying_enabled and "JIANYING_DRAFT_ROOT" not in red_items,
            "剪映草稿导出目录已配置。",
            "剪映草稿导出需要有效的本地草稿目录。",
        ),
        "desktop_experience_alignment": _alignment_status(
            validation["overall_status"] != "red",
            "桌面设置可以保存、校验并导出 .env。",
            "桌面设置可用，但真实渲染前需要处理缺失项。",
        ),
        "missing_items": missing_items,
        "recommended_next_actions": _recommended_actions(config, missing_items),
    }


def _alignment_status(ready: bool, ready_message: str, fallback_message: str) -> dict[str, str]:
    return {"status": "green" if ready else "yellow", "message": ready_message if ready else fallback_message}


def _recommended_actions(config: DesktopSettingsConfig, missing_items: list[str]) -> list[str]:
    actions = []
    if any(item.startswith("DASHSCOPE") or item.startswith("ALIYUN") or item.startswith("aliyun_bailian") or item == "CLOUD_VOICE_PROVIDER" for item in missing_items):
        actions.append("如需中文声音克隆，推荐选择阿里云百炼 CosyVoice，并填写 DASHSCOPE_API_KEY、ALIYUN_BAILIAN_REGION 和 ALIYUN_VOICE_MODEL。")
    if any(item.startswith("FAL") or item.startswith("fal_") or item == "CLOUD_VIDEO_PROVIDER" for item in missing_items):
        actions.append("如需云端口型同步，预览选 fal.ai MuseTalk，最终质量选 fal.ai LatentSync，并填写 FAL_API_KEY。")
    if any(item.startswith("SELF_HOSTED_LIPSYNC") or item == "self_hosted_lipsync" for item in missing_items):
        actions.append("如走自建口型同步服务，请填写 SELF_HOSTED_LIPSYNC_BASE_URL；API Key 是否必填由你的服务决定。")
    if any(item.startswith("SYNCSO") or item.startswith("CLOUD_LIPSYNC") for item in missing_items):
        actions.append("配置 Sync.so 云端口型同步：填写 SYNCSO_API_KEY，并确认 SYNCSO_BASE_URL 指向 https://api.sync.so。")
    if any(item.startswith("OMNIHUMAN") for item in missing_items):
        actions.append("配置火山/BytePlus OmniHuman1.5：填写 Access Key、Secret Key，并确认 endpoint、Region、req_key 与账号所在站点一致。")
    if any(item.startswith("TAVUS") for item in missing_items):
        actions.append("配置 Tavus 自定义 Replica：填写 Tavus API Key 和已完成训练的 Replica ID。")
    if any(item.startswith("BAIDU_XILING") or item == "baidu_xiling" for item in missing_items):
        actions.append("配置百度曦灵数字人：在百度智能云曦灵开放平台获取 AppID、AppKey，并填写可用的 figureId/发音人 ID。")
    if any(item.startswith("HIFLY") or item == "hifly" for item in missing_items):
        actions.append("配置飞影 API：填写 HIFLY_TOKEN，并为源视频和音频准备公网可访问 URL 或后续接入文件上传/对象存储。")
    if any(item.startswith("OBJECT_STORAGE") for item in missing_items):
        actions.append("配置对象存储自动上传：选择阿里云 OSS 或腾讯云 COS，填写 Bucket、Endpoint/Region、Access Key 和公网访问域名，用于自动上传 clean_voice_sample.wav。")
    if "PIXELLE_BASE_URL" in missing_items:
        actions.append("启动 Pixelle 后端，并确认 PIXELLE_BASE_URL、脚本接口和视频接口。")
    if any(item.startswith("WAV2LIP") or item.startswith("YY_WAV2LIP") for item in missing_items):
        actions.append("把 Wav2Lip/YYWav2Lip 模型放在仓库外部，并设置角色模型目录。")
    if any(item.startswith("MUSETALK") or item.startswith("LATENTSYNC") for item in missing_items):
        actions.append("配置 MuseTalk 或 LatentSync 源码目录、模型目录、checkpoint 和配置文件。")
    if "JIANYING_DRAFT_ROOT" in missing_items:
        actions.append("把 JIANYING_DRAFT_ROOT 设置为 Windows 剪映/CapCut 草稿项目目录。")
    actions.append("如参考视频解析失败，请检查 ffmpeg、抖音专用解析器和 FunASR/Paraformer 模型。")
    if not actions:
        actions.append("运行一次标准渲染任务，并在交付前检查质量报告。")
    return actions


def _check_cloud_providers(checks: list[dict[str, Any]], config: DesktopSettingsConfig) -> None:
    settings = Settings(
        dry_run=False,
        runtime_mode=config.runtime_mode,
        cloud_voice_provider=config.cloud_voice_provider,
        cloud_video_provider=config.cloud_video_provider,
        dashscope_api_key=config.dashscope_api_key or None,
        aliyun_bailian_region=config.aliyun_bailian_region,
        aliyun_voice_model=config.aliyun_voice_model,
        elevenlabs_api_key=config.elevenlabs_api_key or None,
        azure_speech_key=config.azure_speech_key or None,
        azure_speech_endpoint=config.azure_speech_endpoint or None,
        custom_http_tts_base_url=config.custom_http_tts_base_url or None,
        custom_http_tts_api_key=config.custom_http_tts_api_key or None,
        fal_api_key=config.fal_api_key or None,
        fal_latentsync_model=config.fal_latentsync_model,
        fal_musetalk_model=config.fal_musetalk_model,
        self_hosted_lipsync_base_url=config.self_hosted_lipsync_base_url or None,
        self_hosted_lipsync_api_key=config.self_hosted_lipsync_api_key or None,
        baidu_xiling_enabled=config.baidu_xiling_enabled,
        baidu_xiling_base_url=config.baidu_xiling_base_url,
        baidu_xiling_app_id=config.baidu_xiling_app_id or None,
        baidu_xiling_app_key=config.baidu_xiling_app_key or None,
        baidu_xiling_figure_id=config.baidu_xiling_figure_id or None,
        baidu_xiling_tts_person=config.baidu_xiling_tts_person or None,
        baidu_xiling_width=config.baidu_xiling_width,
        baidu_xiling_height=config.baidu_xiling_height,
        baidu_xiling_transparent=config.baidu_xiling_transparent,
        baidu_xiling_timeout_seconds=config.baidu_xiling_timeout_seconds,
        baidu_xiling_poll_interval_seconds=config.baidu_xiling_poll_interval_seconds,
        hifly_enabled=config.hifly_enabled,
        hifly_base_url=config.hifly_base_url,
        hifly_token=config.hifly_token or None,
        hifly_required=config.hifly_required,
        hifly_poll_interval_seconds=config.hifly_poll_interval_seconds,
        hifly_timeout_seconds=config.hifly_timeout_seconds,
    )
    labels = {
        "aliyun_bailian_cosyvoice": "阿里云百炼 CosyVoice 声音克隆",
        "aliyun_bailian_qwen_tts": "阿里云百炼 Qwen-TTS",
        "aliyun_bailian_minimax": "阿里云百炼 MiniMax 声音克隆",
        "elevenlabs": "ElevenLabs 声音克隆",
        "azure_tts_no_clone": "Azure TTS",
        "edge_tts_no_clone": "Edge TTS",
        "custom_http_tts": "自定义 HTTP TTS",
        "fal_latentsync": "fal.ai LatentSync 云端渲染",
        "fal_musetalk": "fal.ai MuseTalk 云端预览",
        "did_optional": "D-ID 可选",
        "heygen_optional": "HeyGen 可选",
        "self_hosted_lipsync": "自建口型同步服务",
        "baidu_xiling": "百度曦灵数字人",
        "hifly": "飞影 API 数字人",
    }
    for provider in build_cloud_provider_configs(settings):
        if not provider.enabled:
            continue
        checks.append(
            {
                "name": provider.provider_id,
                "status": provider.status,
                "message": f"{labels.get(provider.provider_id, provider.provider_id)}：{provider.message}",
                "required": provider.required,
            }
        )
        if provider.base_url and provider.status != "red":
            _check_url(checks, f"{provider.provider_id}_BASE_URL", provider.base_url, provider.enabled)


def _check_video_parser(checks: list[dict[str, Any]], config: DesktopSettingsConfig, *, repository_root: Path) -> None:
    if not config.video_parser_enabled:
        checks.append(
            {
                "name": "VIDEO_PARSER_ENABLED",
                "status": "yellow",
                "message": "本地视频解析服务已关闭；公开视频链接只能读取公开元数据，无法自动下载转写。",
                "required": False,
            }
        )
        return

    engine = (config.video_parser_engine or "").lower().strip()
    if engine in {"douyin_downloader", "douyin-downloader", "jiji262"}:
        root = Path(config.video_parser_douyin_downloader_root or "third_party/douyin-downloader")
        candidates = [
            root if root.is_absolute() else repository_root / root,
            repository_root / "third_party" / "douyin-downloader",
            repository_root.parent / "third_party" / "douyin-downloader",
        ]
        resolved_root = next((candidate.resolve() for candidate in candidates if (candidate / "run.py").exists()), None)
        missing_modules = [
            module
            for module in ["aiohttp", "aiofiles", "aiosqlite", "rich", "yaml", "dateutil", "gmssl", "imageio_ffmpeg"]
            if importlib.util.find_spec(module) is None
        ]
        if not resolved_root:
            checks.append(
                {
                    "name": "VIDEO_PARSER_DOUYIN_DOWNLOADER_ROOT",
                    "status": "yellow",
                    "message": "已切换为抖音专用解析器，但未找到 third_party/douyin-downloader/run.py；请确认客户包已包含该开源解析器。",
                    "required": False,
                }
            )
            return
        if missing_modules:
            checks.append(
                {
                    "name": "VIDEO_PARSER_DOUYIN_DOWNLOADER_DEPS",
                    "status": "yellow",
                    "message": f"抖音专用解析器已安装，但缺少 Python 依赖：{', '.join(missing_modules)}。",
                    "required": False,
                }
            )
            return
        checks.append(
            {
                "name": "VIDEO_PARSER_ENGINE",
                "status": "green",
                "message": f"本地视频解析服务可用：抖音专用解析器 {resolved_root}",
                "required": False,
            }
        )
        _check_cloud_video_parsers(checks, config, repository_root=repository_root)
        return

    if engine not in {"yt_dlp", "yt-dlp"}:
        checks.append(
            {
                "name": "VIDEO_PARSER_ENGINE",
                "status": "yellow",
                "message": f"当前解析引擎不是 yt-dlp：{config.video_parser_engine}",
                "required": False,
            }
        )
        return

    configured_path = (config.video_parser_ytdlp_path or "").strip()
    if configured_path:
        path = Path(configured_path)
        if path.exists() and path.is_file():
            checks.append(
                {
                    "name": "VIDEO_PARSER_YTDLP_PATH",
                    "status": "green",
                    "message": f"本地视频解析服务可用：{configured_path}",
                    "required": False,
                }
            )
        else:
            checks.append(
                {
                    "name": "VIDEO_PARSER_YTDLP_PATH",
                    "status": "yellow",
                    "message": "已开启本地视频解析服务，但指定的 yt-dlp 路径不存在；请安装 yt-dlp 或清空路径使用系统 PATH。",
                    "required": False,
                }
            )
        return

    packaged = _packaged_ytdlp_for_settings_check(config, repository_root=repository_root)
    found = str(packaged) if packaged else (shutil.which("yt-dlp") or shutil.which("yt-dlp.exe"))
    checks.append(
        {
            "name": "VIDEO_PARSER_ENGINE",
            "status": "green" if found else "yellow",
            "message": "本地视频解析服务可用。" if found else "已开启本地视频解析服务，但当前环境未找到 yt-dlp；请安装依赖或使用本地上传视频。",
            "required": False,
        }
    )


    if found:
        checks[-1]["message"] = f"本地视频解析服务可用：{found}"


    _check_cloud_video_parsers(checks, config, repository_root=repository_root)


def _check_cloud_video_parsers(checks: list[dict[str, Any]], config: DesktopSettingsConfig) -> None:
    enabled: list[str] = []
    if config.aivo_parser_base_url.strip():
        enabled.append("Aivo 内部解析服务")
    if config.tikhub_base_url.strip() and os.environ.get("TIKHUB_API_KEY", "").strip():
        enabled.append("TikHub 服务端候选")
    if config.istero_base_url.strip() and os.environ.get("ISTERO_API_KEY", "").strip():
        enabled.append("起零数据服务端候选")
    if config.evil0ctal_douyin_api_base_url.strip():
        enabled.append("自建 Douyin/TikTok API")
    checks.append(
        {
            "name": "VIDEO_PARSER_CLOUD_PROVIDERS",
            "status": "green" if enabled else "yellow",
            "message": (
                f"解析候选已配置：{', '.join(enabled)}。API Key 由内部服务端或后台环境变量管理，不在客户设置页展示。"
                if enabled
                else "未配置内部/第三方解析服务；抖音受限链接会引导客户使用官方客户端下载后自动接收。"
            ),
            "required": False,
        }
    )


def _check_cloud_video_parsers(
    checks: list[dict[str, Any]],
    config: DesktopSettingsConfig,
    *,
    repository_root: Path,
) -> None:
    storage_dir = Path(config.storage_path or "storage")
    if not storage_dir.is_absolute():
        storage_dir = repository_root / storage_dir
    hidden = load_internal_provider_secrets(storage_dir)

    enabled: list[str] = []
    if config.aivo_parser_base_url.strip() or str(hidden.get("AIVO_PARSER_BASE_URL") or "").strip():
        enabled.append("Aivo 内部解析服务")
    if config.tikhub_base_url.strip() and (
        os.environ.get("TIKHUB_API_KEY", "").strip() or str(hidden.get("TIKHUB_API_KEY") or "").strip()
    ):
        enabled.append("TikHub 服务端候选")
    if config.istero_base_url.strip() and (
        os.environ.get("ISTERO_API_KEY", "").strip() or str(hidden.get("ISTERO_API_KEY") or "").strip()
    ):
        enabled.append("起零数据服务端候选")
    if config.evil0ctal_douyin_api_base_url.strip() or str(hidden.get("EVIL0CTAL_DOUYIN_API_BASE_URL") or "").strip():
        enabled.append("自建 Douyin/TikTok API")

    checks.append(
        {
            "name": "VIDEO_PARSER_CLOUD_PROVIDERS",
            "status": "green" if enabled else "yellow",
            "message": (
                f"解析候选已配置：{', '.join(enabled)}。API Key 只由内部服务端或后台私有配置管理，不在客户设置页展示。"
                if enabled
                else "未配置内部/第三方解析服务；抖音受限链接会引导客户使用官方客户端下载后自动接收。"
            ),
            "required": False,
        }
    )


def _packaged_ytdlp_for_settings_check(config: DesktopSettingsConfig, *, repository_root: Path) -> Path | None:
    candidates: list[Path] = []
    storage_from_env = os.environ.get("STORAGE_DIR", "").strip()
    if storage_from_env:
        candidates.extend(_runtime_tool_candidates(Path(storage_from_env)))
    if config.storage_path:
        storage_path = Path(config.storage_path)
        if storage_path.is_absolute():
            candidates.extend(_runtime_tool_candidates(storage_path))
        else:
            candidates.extend(_runtime_tool_candidates(repository_root.parent / storage_path))
            candidates.extend(_runtime_tool_candidates(repository_root / storage_path))
    candidates.extend(
        [
            repository_root / "storage" / "runtime_bin" / "yt-dlp.exe",
            repository_root / "storage" / "runtime_bin" / "yt-dlp",
            repository_root.parent / "storage" / "runtime_bin" / "yt-dlp.exe",
            repository_root.parent / "storage" / "runtime_bin" / "yt-dlp",
        ]
    )
    candidates.extend(_runtime_tool_candidates(Path.cwd() / "storage"))
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if candidate.exists() and candidate.is_file():
            return resolved
    return None


def _runtime_tool_candidates(storage_root: Path) -> list[Path]:
    return [
        storage_root / "runtime_bin" / "yt-dlp.exe",
        storage_root / "runtime_bin" / "yt-dlp",
    ]


def _check_funasr_subtitles(checks: list[dict[str, Any]], config: DesktopSettingsConfig) -> None:
    engine = (config.asr_engine or "").lower().strip()
    real_mode = True
    if engine not in {"funasr", "paraformer", "sensevoice", "sensevoice_small"}:
        checks.append(
            {
                "name": "ASR_ENGINE",
                "status": "yellow",
                "message": "字幕对齐当前没有使用本地 FunASR/Paraformer；混剪字幕会退回估算时间，可能和说话节奏不一致。",
                "required": False,
            }
        )
        return

    checks.append(
        {
            "name": "ASR_ENGINE",
            "status": "green",
            "message": "字幕对齐默认使用 FunASR Paraformer 中文长音频版。",
            "required": real_mode,
        }
    )
    if not config.funasr_enabled:
        checks.append(
            {
                "name": "FUNASR_ENABLED",
                "status": "red" if real_mode else "yellow",
                "message": "FUNASR_ENABLED 未开启；真实混剪字幕无法使用 Paraformer 对齐。",
                "required": real_mode,
            }
        )
    else:
        checks.append({"name": "FUNASR_ENABLED", "status": "green", "message": "FunASR 字幕识别已开启。", "required": real_mode})

    if config.funasr_model != PARAFORMER_ZH_LONG_AUDIO_MODEL:
        checks.append(
            {
                "name": "FUNASR_MODEL",
                "status": "yellow",
                "message": f"当前模型不是默认 Paraformer 中文长音频版：{config.funasr_model}",
                "required": False,
            }
        )
    else:
        checks.append({"name": "FUNASR_MODEL", "status": "green", "message": "默认模型为 Paraformer 中文长音频版。", "required": real_mode})

    if not config.funasr_punc_model:
        checks.append(
            {
                "name": "FUNASR_PUNC_MODEL",
                "status": "yellow",
                "message": "未配置 FunASR 标点/断句模型；字幕可能变成一整段，无法一句一条对齐。",
                "required": False,
            }
        )
    else:
        checks.append({"name": "FUNASR_PUNC_MODEL", "status": "green", "message": f"断句模型：{config.funasr_punc_model}", "required": real_mode})

    if importlib.util.find_spec("funasr"):
        checks.append({"name": "FUNASR_PACKAGE", "status": "green", "message": "本机已安装 funasr。", "required": real_mode})
    else:
        checks.append(
            {
                "name": "FUNASR_PACKAGE",
                "status": "red" if real_mode else "yellow",
                "message": "本机未安装 funasr；首次使用真实字幕对齐前需要安装 funasr/modelscope。",
                "required": real_mode,
            }
        )

    model_dir_value = (config.funasr_model_dir or "").strip()
    if not model_dir_value:
        checks.append(
            {
                "name": "FUNASR_MODEL_DIR",
                "status": "yellow",
                "message": "未指定模型缓存目录；FunASR 会使用系统默认缓存，不建议和应用仓库混在一起。",
                "required": False,
            }
        )
        return

    model_dir = Path(model_dir_value)
    try:
        cwd = Path.cwd().resolve()
        if model_dir.resolve().is_relative_to(cwd):
            checks.append(
                {
                    "name": "FUNASR_MODEL_DIR",
                    "status": "red",
                    "message": "模型缓存目录不能放在应用仓库内，避免权重被误打包或提交。",
                    "required": True,
                }
            )
            return
    except OSError:
        checks.append({"name": "FUNASR_MODEL_DIR", "status": "red", "message": "模型缓存目录路径不可访问。", "required": True})
        return

    checks.append(
        {
            "name": "FUNASR_MODEL_DIR",
            "status": "green" if model_dir.exists() else "yellow",
            "message": f"模型缓存目录：{model_dir}" if model_dir.exists() else f"模型缓存目录尚未创建，首次安装时会使用：{model_dir}",
            "required": real_mode,
        }
    )


def _check_object_storage(checks: list[dict[str, Any]], config: DesktopSettingsConfig) -> None:
    backend = (config.object_storage_backend or "local").lower().strip()
    if backend in {"", "local", "none", "disabled"}:
        checks.append(
            {
                "name": "OBJECT_STORAGE_BACKEND",
                "status": "yellow",
                "message": "对象存储未启用；源视频声音克隆时需要手动填写公网声音 URL。",
                "required": False,
            }
        )
        return

    checks.append({"name": "OBJECT_STORAGE_BACKEND", "status": "green", "message": f"对象存储方案：{backend}", "required": True})
    if not config.object_storage_public_base_url.startswith(("http://", "https://")):
        checks.append({"name": "OBJECT_STORAGE_PUBLIC_BASE_URL", "status": "red", "message": "对象存储公网访问地址必须是 http(s) URL。", "required": True})
    else:
        checks.append({"name": "OBJECT_STORAGE_PUBLIC_BASE_URL", "status": "green", "message": "对象存储公网访问地址已配置。", "required": True})

    if backend in {"public_copy", "local_public", "public"}:
        root = Path(config.object_storage_root or "storage/objects")
        checks.append(
            {
                "name": "OBJECT_STORAGE_ROOT",
                "status": "green" if root.parent.exists() else "yellow",
                "message": f"公开同步目录：{root}。请确保该目录会同步到公网域名。",
                "required": True,
            }
        )
        return

    if backend in {"aliyun_oss", "oss", "aliyun"}:
        required = [
            ("OBJECT_STORAGE_ENDPOINT", config.object_storage_endpoint),
            ("OBJECT_STORAGE_BUCKET", config.object_storage_bucket),
            ("OBJECT_STORAGE_ACCESS_KEY_ID", config.object_storage_access_key_id),
            ("OBJECT_STORAGE_SECRET_ACCESS_KEY", config.object_storage_secret_access_key),
        ]
    elif backend in {"tencent_cos", "cos", "tencent"}:
        required = [
            ("OBJECT_STORAGE_REGION", config.object_storage_region),
            ("OBJECT_STORAGE_BUCKET", config.object_storage_bucket),
            ("OBJECT_STORAGE_ACCESS_KEY_ID", config.object_storage_access_key_id),
            ("OBJECT_STORAGE_SECRET_ACCESS_KEY", config.object_storage_secret_access_key),
        ]
    else:
        checks.append({"name": "OBJECT_STORAGE_BACKEND", "status": "red", "message": f"暂不支持的对象存储方案：{config.object_storage_backend}", "required": True})
        return

    for name, value in required:
        checks.append(
            {
                "name": name,
                "status": "green" if value else "red",
                "message": f"{name} 已配置。" if value else f"{name} 未配置，无法自动上传声音样本。",
                "required": True,
            }
        )


def _check_cloud_lipsync(checks: list[dict[str, Any]], config: DesktopSettingsConfig) -> None:
    if not config.cloud_lipsync_enabled:
        checks.append(
            {
                "name": "CLOUD_LIPSYNC_ENABLED",
                "status": "yellow",
                "message": "云端口型同步未启用；如需 Sync.so，请在简单选择里选择 Sync.so 云端口型同步。",
                "required": False,
            }
        )
        return
    provider = config.cloud_lipsync_provider.lower().strip()
    if provider == "pixverse":
        if not config.pixverse_base_url:
            checks.append({"name": "PIXVERSE_BASE_URL", "status": "red", "message": "已启用 PixVerse，但服务地址为空。", "required": True})
        else:
            try:
                with httpx.Client(timeout=httpx.Timeout(1.0, connect=0.4), follow_redirects=True, trust_env=False) as client:
                    response = client.get(config.pixverse_base_url)
                status = "green" if response.status_code < 500 else "red"
                checks.append({"name": "PIXVERSE_BASE_URL", "status": status, "message": f"访问 {config.pixverse_base_url} 返回状态码 {response.status_code}。", "required": True})
            except Exception as exc:  # noqa: BLE001 - validation reports the concrete blocker.
                checks.append({"name": "PIXVERSE_BASE_URL", "status": "red", "message": f"PixVerse 服务地址不可访问：{config.pixverse_base_url}；{exc}", "required": True})
        if not config.pixverse_api_key:
            checks.append({"name": "PIXVERSE_API_KEY", "status": "red", "message": "已启用 PixVerse，但没有填写 API Key。", "required": True})
        else:
            checks.append({"name": "PIXVERSE_API_KEY", "status": "green", "message": "PixVerse API Key 已配置；校验结果不会显示密钥内容。", "required": True})
        if not config.pixverse_model:
            checks.append({"name": "PIXVERSE_MODEL", "status": "red", "message": "已启用 PixVerse，但模型名为空。", "required": True})
        else:
            checks.append({"name": "PIXVERSE_MODEL", "status": "green", "message": f"PixVerse 模型：{config.pixverse_model}", "required": True})
        return
    if provider != "syncso":
        checks.append(
            {
                "name": "CLOUD_LIPSYNC_PROVIDER",
                "status": "red",
                "message": f"暂不支持的云端口型同步服务：{config.cloud_lipsync_provider}",
                "required": True,
            }
        )
        return
    if not config.syncso_base_url:
        checks.append({"name": "SYNCSO_BASE_URL", "status": "red", "message": "已启用 Sync.so，但服务地址为空。", "required": True})
    else:
        try:
            with httpx.Client(timeout=httpx.Timeout(1.0, connect=0.4), follow_redirects=True, trust_env=False) as client:
                response = client.get(config.syncso_base_url)
            status = "green" if response.status_code < 500 else "red"
            checks.append({"name": "SYNCSO_BASE_URL", "status": status, "message": f"访问 {config.syncso_base_url} 返回状态码 {response.status_code}。", "required": True})
        except Exception as exc:  # noqa: BLE001 - validation reports the concrete blocker.
            checks.append({"name": "SYNCSO_BASE_URL", "status": "red", "message": f"Sync.so 服务地址不可访问：{config.syncso_base_url}；{exc}", "required": True})
    if not config.syncso_api_key:
        checks.append({"name": "SYNCSO_API_KEY", "status": "red", "message": "已启用 Sync.so，但没有填写 API Key。", "required": True})
    else:
        checks.append({"name": "SYNCSO_API_KEY", "status": "green", "message": "Sync.so API Key 已配置；校验结果不会显示密钥内容。", "required": True})
    if not config.syncso_model:
        checks.append({"name": "SYNCSO_MODEL", "status": "red", "message": "已启用 Sync.so，但模型名为空。", "required": True})
    else:
        checks.append({"name": "SYNCSO_MODEL", "status": "green", "message": f"Sync.so 模型：{config.syncso_model}", "required": True})


def _check_omnihuman(checks: list[dict[str, Any]], config: DesktopSettingsConfig) -> None:
    if not config.omnihuman_enabled:
        checks.append(
            {
                "name": "OMNIHUMAN_ENABLED",
                "status": "yellow",
                "message": "火山/BytePlus OmniHuman1.5 当前未启用；需要云端数字人渲染时再开启。",
                "required": False,
            }
        )
        return

    if not config.omnihuman_endpoint:
        checks.append({"name": "OMNIHUMAN_ENDPOINT", "status": "red", "message": "已启用 OmniHuman1.5，但服务地址为空。", "required": True})
    else:
        try:
            with httpx.Client(timeout=httpx.Timeout(1.0, connect=0.4), follow_redirects=True, trust_env=False) as client:
                response = client.get(config.omnihuman_endpoint)
            status = "green" if response.status_code < 500 else "red"
            checks.append(
                {
                    "name": "OMNIHUMAN_ENDPOINT",
                    "status": status,
                    "message": f"访问 {config.omnihuman_endpoint} 返回状态码 {response.status_code}。",
                    "required": True,
                }
            )
        except Exception as exc:  # noqa: BLE001 - validation reports the concrete blocker.
            checks.append(
                {
                    "name": "OMNIHUMAN_ENDPOINT",
                    "status": "red",
                    "message": f"OmniHuman1.5 服务地址不可访问：{config.omnihuman_endpoint}；{exc}",
                    "required": True,
                }
            )

    if not config.omnihuman_access_key:
        checks.append({"name": "OMNIHUMAN_ACCESS_KEY", "status": "red", "message": "已启用 OmniHuman1.5，但没有填写 Access Key。", "required": True})
    else:
        checks.append({"name": "OMNIHUMAN_ACCESS_KEY", "status": "green", "message": "OmniHuman1.5 Access Key 已配置；校验结果不会显示密钥内容。", "required": True})

    if not config.omnihuman_secret_key:
        checks.append({"name": "OMNIHUMAN_SECRET_KEY", "status": "red", "message": "已启用 OmniHuman1.5，但没有填写 Secret Key。", "required": True})
    else:
        checks.append({"name": "OMNIHUMAN_SECRET_KEY", "status": "green", "message": "OmniHuman1.5 Secret Key 已配置；校验结果不会显示密钥内容。", "required": True})

    if not config.omnihuman_req_key:
        checks.append({"name": "OMNIHUMAN_REQ_KEY", "status": "red", "message": "已启用 OmniHuman1.5，但 req_key 为空。", "required": True})
    else:
        checks.append({"name": "OMNIHUMAN_REQ_KEY", "status": "green", "message": f"OmniHuman1.5 req_key：{config.omnihuman_req_key}", "required": True})

    if not config.omnihuman_region:
        checks.append({"name": "OMNIHUMAN_REGION", "status": "red", "message": "已启用 OmniHuman1.5，但 Region 为空。", "required": True})
    else:
        checks.append({"name": "OMNIHUMAN_REGION", "status": "green", "message": f"OmniHuman1.5 Region：{config.omnihuman_region}", "required": True})


def _check_tavus(checks: list[dict[str, Any]], config: DesktopSettingsConfig) -> None:
    if not config.tavus_enabled:
        checks.append(
            {
                "name": "TAVUS_ENABLED",
                "status": "yellow",
                "message": "Tavus 云端数字人当前未启用；启用后可由 Tavus Replica 直接生成带声音和口型的视频。",
                "required": False,
            }
        )
        return
    if not config.tavus_base_url:
        checks.append({"name": "TAVUS_BASE_URL", "status": "red", "message": "已启用 Tavus，但服务地址为空。", "required": True})
        return
    if not config.tavus_api_key:
        checks.append({"name": "TAVUS_API_KEY", "status": "red", "message": "已启用 Tavus，但没有填写 API Key。", "required": True})
    else:
        checks.append({"name": "TAVUS_API_KEY", "status": "green", "message": "Tavus API Key 已配置；校验结果不会显示密钥内容。", "required": True})
    if not config.tavus_replica_id:
        checks.append({"name": "TAVUS_REPLICA_ID", "status": "red", "message": "已启用 Tavus，但没有填写 Replica ID。", "required": True})
    if not config.tavus_api_key:
        return
    try:
        replicas_url = urljoin(config.tavus_base_url.rstrip("/") + "/", "v2/replicas")
        with httpx.Client(timeout=httpx.Timeout(3.0, connect=1.0), follow_redirects=True, trust_env=False) as client:
            response = client.get(replicas_url, headers={"x-api-key": config.tavus_api_key})
        if response.status_code >= 500:
            checks.append({"name": "TAVUS_BASE_URL", "status": "red", "message": f"访问 Tavus 返回状态码 {response.status_code}。", "required": True})
            return
        data = response.json() if response.content else {}
        replicas = data.get("data") if isinstance(data, dict) else []
        replica_ids = {str(item.get("replica_id")) for item in replicas if isinstance(item, dict)}
        checks.append({"name": "TAVUS_BASE_URL", "status": "green", "message": f"Tavus 服务可访问，已读取 {len(replica_ids)} 个 Replica。", "required": True})
        if config.tavus_replica_id:
            if config.tavus_replica_id in replica_ids:
                checks.append({"name": "TAVUS_REPLICA_ID", "status": "green", "message": f"Tavus Replica 可用：{config.tavus_replica_id}", "required": True})
            else:
                checks.append({"name": "TAVUS_REPLICA_ID", "status": "yellow", "message": f"Tavus 可访问，但当前 Replica ID 未出现在列表中：{config.tavus_replica_id}", "required": True})
    except Exception as exc:  # noqa: BLE001 - validation reports the concrete blocker.
        checks.append({"name": "TAVUS_BASE_URL", "status": "red", "message": f"Tavus 服务不可访问：{config.tavus_base_url}；{exc}", "required": True})


def _check_url(checks: list[dict[str, Any]], name: str, value: str, enabled: bool, endpoint: str = "") -> None:
    if not enabled:
        checks.append({"name": name, "status": "yellow", "message": "当前模式不需要启用；如需真实能力，可在简单选择或高级设置中开启。", "required": False})
        return
    if not value:
        checks.append({"name": name, "status": "red", "message": "已启用，但服务地址为空。", "required": True})
        return
    url = urljoin(value.rstrip("/") + "/", endpoint.lstrip("/")) if endpoint else value
    try:
        with httpx.Client(timeout=httpx.Timeout(1.0, connect=0.4), follow_redirects=True, trust_env=False) as client:
            response = client.get(url)
        status = "green" if response.status_code < 500 else "red"
        checks.append({"name": name, "status": status, "message": f"访问 {url} 返回状态码 {response.status_code}。", "required": True})
    except Exception as exc:  # noqa: BLE001 - validation reports the concrete blocker.
        checks.append({"name": name, "status": "red", "message": f"服务地址不可访问：{url}；{exc}", "required": True})


def _check_path(checks: list[dict[str, Any]], name: str, value: str, enabled: bool, *, kind: Literal["file", "dir"]) -> None:
    if not enabled:
        checks.append({"name": name, "status": "yellow", "message": "当前模式不需要启用；如需真实能力，可在简单选择或高级设置中开启。", "required": False})
        return
    if not value:
        checks.append({"name": name, "status": "red", "message": "已启用，但本地路径为空。", "required": True})
        return
    path = Path(value)
    exists = path.is_file() if kind == "file" else path.is_dir()
    kind_label = "文件" if kind == "file" else "目录"
    checks.append(
        {
            "name": name,
            "status": "green" if exists else "red",
            "message": f"{kind_label}存在：{path}" if exists else f"{kind_label}不存在：{path}",
            "required": True,
        }
    )


def _repo_model_weight_violations(repository_root: Path) -> list[str]:
    suffixes = {".pth", ".pt", ".ckpt", ".safetensors", ".onnx", ".pkl"}
    excluded_dirs = {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "dist",
        "env",
        "node_modules",
        "storage",
        "venv",
    }
    violations: list[str] = []
    for dirpath, dirnames, filenames in os.walk(repository_root):
        dirnames[:] = [name for name in dirnames if name not in excluded_dirs]
        for filename in filenames:
            if Path(filename).suffix.lower() in suffixes:
                path = Path(dirpath) / filename
                violations.append(path.relative_to(repository_root).as_posix())
    return violations
