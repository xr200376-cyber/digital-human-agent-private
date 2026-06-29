from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from app.desktop_settings import DesktopSettingsConfig


PresetId = Literal["dryrun_trial", "yuanyue_compat", "high_quality", "batch_production", "custom"]
PRESET_IDS: tuple[PresetId, ...] = ("dryrun_trial", "yuanyue_compat", "high_quality", "batch_production", "custom")


class SettingsPreset(BaseModel):
    preset_id: PresetId
    label: str
    description: str
    config: DesktopSettingsConfig
    recommended_actions: list[str] = []


def get_settings_preset(
    preset_id: PresetId | str,
    *,
    current_config: DesktopSettingsConfig | None = None,
    detected_values: dict[str, Any] | None = None,
) -> SettingsPreset:
    if preset_id not in PRESET_IDS:
        raise ValueError(f"unknown settings preset: {preset_id}")
    detected = detected_values or {}
    base = current_config or DesktopSettingsConfig()

    if preset_id == "dryrun_trial":
        return SettingsPreset(
            preset_id="dryrun_trial",
            label="基础真实流程",
            description="使用本机可用能力和已配置云服务运行真实流程。",
            config=DesktopSettingsConfig(
                selected_preset="dryrun_trial",
                tts_provider="edge",
                digital_human_engine="syncso",
                editing_output="mp4_only",
                runtime_mode="final",
                STORAGE_DIR=base.storage_path,
                PYTHON_PATH=base.python_path,
                TTS_ENGINE="edge",
                CLOUD_VOICE_PROVIDER="edge_tts_no_clone",
                CLOUD_VIDEO_PROVIDER="local",
                TTS_BASE_URL=base.tts_base_url,
                TTS_DEFAULT_VOICE=base.tts_default_voice,
                COSYVOICE_URL=base.cosyvoice_url,
                GPT_SOVITS_URL=base.gpt_sovits_url,
                PIXELLE_ENABLED=False,
                PIXELLE_BASE_URL=base.pixelle_base_url,
                PIXELLE_SCRIPT_ENDPOINT=base.pixelle_script_endpoint,
                PIXELLE_VIDEO_ENDPOINT=base.pixelle_video_endpoint,
                CLOUD_LIPSYNC_ENABLED=False,
                CLOUD_LIPSYNC_PROVIDER=base.cloud_lipsync_provider,
                SYNCSO_BASE_URL=base.syncso_base_url,
                SYNCSO_API_KEY=base.syncso_api_key,
                SYNCSO_MODEL=base.syncso_model,
                SYNCSO_GENERATE_ENDPOINT=base.syncso_generate_endpoint,
                SYNCSO_TIMEOUT_SECONDS=base.syncso_timeout_seconds,
                SYNCSO_POLL_INTERVAL_SECONDS=base.syncso_poll_interval_seconds,
                WAV2LIP_ENABLED=False,
                WAV2LIP_ROOT=base.wav2lip_root,
                WAV2LIP_CHECKPOINT=base.wav2lip_checkpoint,
                YY_WAV2LIP_ENABLED=False,
                YY_WAV2LIP_CHECKPOINT=base.yy_wav2lip_checkpoint,
                YY_WAV2LIP_ROLE_MODEL_DIR=base.yy_wav2lip_role_model_dir,
                MUSETALK_ENABLED=False,
                MUSETALK_ROOT=base.musetalk_root,
                MUSETALK_MODEL_DIR=base.musetalk_model_dir,
                LATENTSYNC_ENABLED=False,
                LATENTSYNC_ROOT=base.latentsync_root,
                LATENTSYNC_CHECKPOINT=base.latentsync_checkpoint,
                LATENTSYNC_UNET_CONFIG=base.latentsync_unet_config,
                JIANYING_ENABLED=False,
                JIANYING_DRAFT_ROOT=base.jianying_draft_root,
                DUIX_ENABLED=False,
                DUIX_BASE_URL=base.duix_base_url,
            ),
            recommended_actions=["直接打开工作台运行真实流程；如需云端数字人，请先填写对应 API Key。"],
        )

    if preset_id == "yuanyue_compat":
        tts_engine = "edge" if detected.get("edge_tts_available", True) else "cloud_clone"
        return SettingsPreset(
            preset_id="yuanyue_compat",
            label="对齐元岳/AivoClaw路线",
            description="优先启用 Pixelle 云端、Sync.so 云端口型同步和剪映草稿。",
            config=_merge_config(
                base,
                selected_preset="yuanyue_compat",
                tts_provider=tts_engine,
                digital_human_engine="syncso",
                editing_output="jianying_auto",
                runtime_mode="compat",
                TTS_ENGINE=tts_engine,
                CLOUD_VOICE_PROVIDER="aliyun_bailian_cosyvoice",
                CLOUD_VIDEO_PROVIDER="fal_musetalk",
                PIXELLE_ENABLED=True,
                PIXELLE_BASE_URL=detected.get("pixelle_base_url") or _cloud_url_or_empty(base.pixelle_base_url),
                CLOUD_LIPSYNC_ENABLED=True,
                CLOUD_LIPSYNC_PROVIDER="syncso",
                SYNCSO_BASE_URL=detected.get("syncso_base_url", base.syncso_base_url),
                WAV2LIP_ENABLED=False,
                YY_WAV2LIP_ENABLED=False,
                MUSETALK_ENABLED=False,
                LATENTSYNC_ENABLED=False,
                JIANYING_ENABLED=True,
                JIANYING_DRAFT_ROOT=detected.get("jianying_draft_root", base.jianying_draft_root),
                DUIX_ENABLED=False,
            ),
            recommended_actions=["填写 Sync.so API Key，并把 PIXELLE_BASE_URL 设置为 Pixelle 云端地址；本地 YYWav2Lip 不再作为默认要求。"],
        )

    if preset_id == "high_quality":
        tts_engine = "cosyvoice_http" if detected.get("cosyvoice_url") else ("edge" if detected.get("edge_tts_available", True) else "cloud_clone")
        duix_url = detected.get("duix_base_url", base.duix_base_url)
        return SettingsPreset(
            preset_id="high_quality",
            label="高质量数字人",
            description="优先使用 CosyVoice、MuseTalk、LatentSync，Duix 只在 HTTP 可用时启用。",
            config=_merge_config(
                base,
                selected_preset="high_quality",
                tts_provider=tts_engine,
                digital_human_engine="latentsync",
                editing_output="jianying_auto",
                runtime_mode="final",
                TTS_ENGINE=tts_engine,
                CLOUD_VOICE_PROVIDER="aliyun_bailian_cosyvoice",
                CLOUD_VIDEO_PROVIDER="fal_latentsync",
                COSYVOICE_URL=detected.get("cosyvoice_url", base.cosyvoice_url),
                TTS_BASE_URL=detected.get("cosyvoice_url", base.tts_base_url),
                MUSETALK_ENABLED=True,
                LATENTSYNC_ENABLED=True,
                CLOUD_LIPSYNC_ENABLED=False,
                WAV2LIP_ENABLED=False,
                YY_WAV2LIP_ENABLED=False,
                JIANYING_ENABLED=True,
                JIANYING_DRAFT_ROOT=detected.get("jianying_draft_root", base.jianying_draft_root),
                DUIX_ENABLED=bool(detected.get("duix_base_url")),
                DUIX_BASE_URL=duix_url,
            ),
            recommended_actions=["准备 MuseTalk / LatentSync 模型和真实 TTS，再运行 final 质量任务。"],
        )

    if preset_id == "batch_production":
        return SettingsPreset(
            preset_id="batch_production",
            label="批量生产",
            description="偏向速度和稳定性：快速 TTS、MuseTalk/Wav2Lip，关闭重型最终渲染引擎。",
            config=_merge_config(
                base,
                selected_preset="batch_production",
                tts_provider="aliyun_tts",
                digital_human_engine="musetalk",
                editing_output="jianying_auto",
                runtime_mode="batch",
                TTS_ENGINE="cloud_clone",
                CLOUD_VOICE_PROVIDER="aliyun_bailian_cosyvoice",
                CLOUD_VIDEO_PROVIDER="fal_musetalk",
                TTS_BASE_URL=detected.get("tts_base_url", base.tts_base_url),
                MUSETALK_ENABLED=True,
                CLOUD_LIPSYNC_ENABLED=False,
                WAV2LIP_ENABLED=True,
                YY_WAV2LIP_ENABLED=False,
                LATENTSYNC_ENABLED=False,
                DUIX_ENABLED=False,
                JIANYING_ENABLED=True,
                JIANYING_DRAFT_ROOT=detected.get("jianying_draft_root", base.jianying_draft_root),
            ),
            recommended_actions=["先用 10 条批量基准任务验证稳定性，再放大生产。"],
        )

    return SettingsPreset(
        preset_id="custom",
        label="自定义",
        description="保留当前手动配置。",
        config=_merge_config(base, selected_preset="custom"),
        recommended_actions=["按需展开高级设置，或选择一个推荐使用目标。"],
    )


def _merge_config(base: DesktopSettingsConfig, **updates: Any) -> DesktopSettingsConfig:
    data = base.model_dump(by_alias=True)
    data.update(updates)
    return DesktopSettingsConfig.model_validate(data)


def _cloud_url_or_empty(value: str) -> str:
    lowered = value.lower().strip()
    if lowered.startswith("http://127.0.0.1") or lowered.startswith("http://localhost"):
        return ""
    return value
