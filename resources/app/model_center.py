from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from app.cloud_providers import build_cloud_provider_configs
from app.desktop_settings import DesktopSettingsConfig, validate_desktop_settings


ModelStatus = Literal["green", "yellow", "red", "disabled"]
QualityMode = Literal["dry-run", "preview", "compat", "standard", "final", "batch"]
DIGITAL_HUMAN_MODEL_IDS = {
    "hifly",
    "baidu_xiling",
    "aliyun_bailian_digital_human",
    "syncso",
    "pixverse_lipsync",
    "fal_musetalk",
    "fal_latentsync",
    "tavus",
    "omnihuman",
}


class ModelOption(BaseModel):
    model_id: str
    category: str
    label: str
    description: str
    status: ModelStatus = "disabled"
    missing_items: list[str] = []
    cost_note: str = ""
    requires_paid_call: bool = False
    recommended_for: list[str] = []


class ModelSelectionRequest(BaseModel):
    voice_model: str = "edge_tts_no_clone"
    digital_human_model: str = "syncso"
    script_model: str = "manual_script"
    export_model: str = "mp4_only"
    quality_mode: QualityMode = "preview"


class ModelPresetRequest(BaseModel):
    preset_id: str


VOICE_LABELS = {
    "edge_tts_no_clone": "Edge TTS 免费试听",
    "aliyun_bailian_cosyvoice": "阿里云百炼 CosyVoice",
    "aliyun_bailian_qwen_tts": "阿里云百炼 Qwen-TTS",
    "hifly_voice_clone": "飞影声音克隆",
    "custom_http_tts": "自定义 HTTP 声音服务",
}


PRESETS: dict[str, ModelSelectionRequest] = {
    "hifly_one_video": ModelSelectionRequest(
        voice_model="aliyun_bailian_cosyvoice",
        digital_human_model="hifly",
        script_model="manual_script",
        export_model="mp4_only",
        quality_mode="final",
    ),
    "cloud_quality": ModelSelectionRequest(
        voice_model="aliyun_bailian_cosyvoice",
        digital_human_model="fal_latentsync",
        script_model="pixelle_cloud",
        export_model="jianying_draft",
        quality_mode="final",
    ),
    "low_cost_preview": ModelSelectionRequest(
        voice_model="edge_tts_no_clone",
        digital_human_model="fal_musetalk",
        script_model="manual_script",
        export_model="mp4_only",
        quality_mode="preview",
    ),
    "syncso_lipsync": ModelSelectionRequest(
        voice_model="aliyun_bailian_cosyvoice",
        digital_human_model="syncso",
        script_model="pixelle_cloud",
        export_model="jianying_draft",
        quality_mode="compat",
    ),
}


def model_catalog(config: DesktopSettingsConfig) -> dict[str, Any]:
    voice_models = _voice_options(config)
    digital_human_models = _simple_digital_human_options(config)
    return {
        "categories": ["voice", "digital_human", "script", "export", "quality"],
        "voice_models": [item.model_dump(mode="json") for item in voice_models],
        "digital_human_models": [item.model_dump(mode="json") for item in digital_human_models],
        "script_models": [item.model_dump(mode="json") for item in _script_options(config)],
        "export_models": [item.model_dump(mode="json") for item in _export_options(config)],
        "quality_modes": [item.model_dump(mode="json") for item in _quality_options(config)],
        "presets": [
            {
                "preset_id": "hifly_one_video",
                "label": "飞影一体化",
                "description": "上传一个源视频，走飞影 API 创建形象、克隆声音并生成视频。",
            },
            {
                "preset_id": "cloud_quality",
                "label": "云端高质量",
                "description": "阿里云声音 + fal.ai LatentSync + Pixelle + 剪映草稿。",
            },
            {
                "preset_id": "low_cost_preview",
                "label": "低成本预览",
                "description": "Edge TTS + fal.ai MuseTalk，适合先看流程和样片。",
            },
            {
                "preset_id": "syncso_lipsync",
                "label": "Sync.so 口型同步",
                "description": "阿里云声音 + Sync.so 云端口型同步 + 剪映草稿。",
            },
        ],
        "selection": current_model_selection(config).model_dump(mode="json"),
    }


def current_model_selection(config: DesktopSettingsConfig) -> ModelSelectionRequest:
    script_model = "pixelle_cloud" if config.pixelle_enabled else "manual_script"
    export_model = "jianying_draft" if config.jianying_enabled else "mp4_only"
    video_provider = (config.cloud_video_provider or "").strip().lower()
    cloud_lipsync_provider = config.cloud_lipsync_provider.lower()
    if config.cloud_lipsync_enabled and cloud_lipsync_provider == "syncso":
        digital_human_model = "syncso"
    elif config.cloud_lipsync_enabled and cloud_lipsync_provider in {"pixverse", "pixverse_lipsync"}:
        digital_human_model = "pixverse_lipsync"
    elif video_provider in DIGITAL_HUMAN_MODEL_IDS:
        digital_human_model = video_provider
    elif video_provider and video_provider != "local":
        digital_human_model = video_provider
    else:
        digital_human_model = "syncso"
    if digital_human_model == "local":
        digital_human_model = "syncso"
    quality = config.runtime_mode
    if quality in {"compat", "standard", "final", "batch"}:
        quality_mode = quality  # type: ignore[assignment]
    else:
        quality_mode = "preview"
    return ModelSelectionRequest(
        voice_model=config.cloud_voice_provider or "edge_tts_no_clone",
        digital_human_model=digital_human_model,
        script_model=script_model,
        export_model=export_model,
        quality_mode=quality_mode,
    )


def apply_model_selection(config: DesktopSettingsConfig, selection: ModelSelectionRequest) -> DesktopSettingsConfig:
    data = config.model_dump(by_alias=True)
    data.update(_voice_updates(selection.voice_model))
    data.update(_digital_human_updates(selection.digital_human_model))
    data.update(_script_updates(selection.script_model))
    data.update(_export_updates(selection.export_model))
    data.update(_quality_updates(selection.quality_mode))
    data["selected_preset"] = "custom"
    return DesktopSettingsConfig.model_validate(data)


def validate_model_selection(
    config: DesktopSettingsConfig,
    *,
    repository_root,
) -> dict[str, Any]:
    validation = validate_desktop_settings(config, repository_root=repository_root)
    checks = validation.get("checks", [])
    missing_items = [
        str(item.get("name") or item.get("message"))
        for item in checks
        if item.get("status") == "red"
    ]
    for provider in build_cloud_provider_configs(_settings_from_config(config)):
        if provider.enabled:
            missing_items.extend(provider.missing_items)
    if config.cloud_lipsync_enabled and config.cloud_lipsync_provider.lower() == "syncso":
        if not config.syncso_api_key:
            missing_items.append("SYNCSO_API_KEY")
        if not config.syncso_base_url:
            missing_items.append("SYNCSO_BASE_URL")
    if config.pixelle_enabled and not config.pixelle_base_url:
        missing_items.append("PIXELLE_BASE_URL")
    if config.jianying_enabled and not config.jianying_draft_root:
        missing_items.append("JIANYING_DRAFT_ROOT")
    if config.cloud_video_provider == "aliyun_bailian_digital_human" and not config.dashscope_api_key:
        missing_items.append("DASHSCOPE_API_KEY")
    missing_items = list(dict.fromkeys(missing_items))
    warnings = [
        str(item.get("message"))
        for item in checks
        if item.get("status") == "yellow"
    ]
    return {
        "overall_status": validation.get("overall_status", "red"),
        "missing_items": missing_items,
        "warnings": warnings,
        "selection": current_model_selection(config).model_dump(mode="json"),
        "checks": checks,
    }


def apply_model_preset(config: DesktopSettingsConfig, preset_id: str) -> DesktopSettingsConfig:
    if preset_id not in PRESETS:
        raise ValueError(f"unknown model preset: {preset_id}")
    selected = apply_model_selection(config, PRESETS[preset_id])
    data = selected.model_dump(by_alias=True)
    data["selected_preset"] = preset_id
    return DesktopSettingsConfig.model_validate(data)


def _voice_options(config: DesktopSettingsConfig) -> list[ModelOption]:
    settings_like = _settings_from_config(config)
    options: list[ModelOption] = []
    for provider in build_cloud_provider_configs(settings_like):
        if provider.provider_type != "voice":
            continue
        if provider.provider_id not in {"edge_tts_no_clone", "aliyun_bailian_cosyvoice", "aliyun_bailian_qwen_tts", "hifly_voice_clone", "custom_http_tts"}:
            continue
        options.append(
            ModelOption(
                model_id=provider.provider_id,
                category="voice",
                label=VOICE_LABELS.get(provider.provider_id, provider.provider_id),
                description=provider.message,
                status=_status(provider.status),
                missing_items=provider.missing_items,
                cost_note=provider.cost_estimate,
                requires_paid_call=provider.provider_id != "edge_tts_no_clone",
                recommended_for=["声音克隆", "口播配音"] if provider.provider_id != "edge_tts_no_clone" else ["免费试听", "快速预览"],
            )
        )
    return options


def _digital_human_options(config: DesktopSettingsConfig) -> list[ModelOption]:
    settings_like = _settings_from_config(config)
    cloud = {item.provider_id: item for item in build_cloud_provider_configs(settings_like)}
    sync_missing = []
    if not config.syncso_api_key:
        sync_missing.append("SYNCSO_API_KEY")
    pixverse_missing = []
    if not config.pixverse_api_key:
        pixverse_missing.append("PIXVERSE_API_KEY")
    if not config.pixverse_base_url:
        pixverse_missing.append("PIXVERSE_BASE_URL")
    return [
        ModelOption(
            model_id="hifly",
            category="digital_human",
            label="飞影 API 一体化数字人",
            description="上传源视频后由飞影创建形象、克隆声音并生成视频。",
            status=_status(cloud.get("hifly").status if cloud.get("hifly") else "disabled"),
            missing_items=cloud.get("hifly").missing_items if cloud.get("hifly") else ["HIFLY_TOKEN"],
            cost_note="按飞影账号额度计费。",
            requires_paid_call=True,
            recommended_for=["一键源视频数字人", "中国用户优先"],
        ),
        ModelOption(
            model_id="baidu_xiling",
            category="digital_human",
            label="百度曦灵数字人",
            description="适合已有百度曦灵 figureId 的视频合成。",
            status=_status(cloud.get("baidu_xiling").status if cloud.get("baidu_xiling") else "disabled"),
            missing_items=cloud.get("baidu_xiling").missing_items if cloud.get("baidu_xiling") else ["BAIDU_XILING_APP_ID", "BAIDU_XILING_APP_KEY", "BAIDU_XILING_FIGURE_ID"],
            cost_note="按百度智能云/曦灵实际账单计费。",
            requires_paid_call=True,
            recommended_for=["企业数字人", "百度账号体系"],
        ),
        ModelOption(
            model_id="syncso",
            category="digital_human",
            label="Sync.so 云端口型同步",
            description="使用已有形象视频 + 新声音进行云端口型同步。",
            status="green" if config.cloud_lipsync_enabled and not sync_missing else ("red" if config.cloud_lipsync_enabled else "disabled"),
            missing_items=sync_missing if config.cloud_lipsync_enabled else [],
            cost_note="按 Sync.so 账号用量计费。",
            requires_paid_call=True,
            recommended_for=["口型同步", "替代本地模型"],
        ),
        ModelOption(
            model_id="pixverse_lipsync",
            category="digital_human",
            label="PixVerse Lipsync",
            description="使用 PixVerse lipsync 模型，把形象视频和新声音合成为口型同步视频。",
            status=_configured_status(
                bool((config.cloud_lipsync_enabled and config.cloud_lipsync_provider == "pixverse") or config.pixverse_api_key),
                pixverse_missing,
            ),
            missing_items=pixverse_missing if (config.cloud_lipsync_enabled and config.cloud_lipsync_provider == "pixverse") or config.pixverse_api_key else [],
            cost_note="按 PixVerse/SuperAIAPI 账号用量计费。",
            requires_paid_call=True,
            recommended_for=["口型同步", "PixVerse 模型"],
        ),
        ModelOption(
            model_id="fal_musetalk",
            category="digital_human",
            label="fal.ai MuseTalk 预览",
            description="云端快速口型同步，适合预览和低成本测试。",
            status=_status(cloud.get("fal_musetalk").status if cloud.get("fal_musetalk") else "disabled"),
            missing_items=cloud.get("fal_musetalk").missing_items if cloud.get("fal_musetalk") else ["FAL_API_KEY"],
            cost_note="约 $0.003/秒，以 fal.ai 实际账单为准。",
            requires_paid_call=True,
            recommended_for=["快速预览"],
        ),
        ModelOption(
            model_id="fal_latentsync",
            category="digital_human",
            label="fal.ai LatentSync 高质量",
            description="云端高质量口型同步，适合最终成片。",
            status=_status(cloud.get("fal_latentsync").status if cloud.get("fal_latentsync") else "disabled"),
            missing_items=cloud.get("fal_latentsync").missing_items if cloud.get("fal_latentsync") else ["FAL_API_KEY"],
            cost_note="约 $0.005/秒，以 fal.ai 实际账单为准。",
            requires_paid_call=True,
            recommended_for=["最终成片"],
        ),
    ]


def _simple_digital_human_options(config: DesktopSettingsConfig) -> list[ModelOption]:
    hifly_missing = _missing_items(
        ("HIFLY_TOKEN", config.hifly_token),
        ("HIFLY_BASE_URL", config.hifly_base_url),
    )
    baidu_missing = _missing_items(
        ("BAIDU_XILING_APP_KEY", config.baidu_xiling_app_key),
        ("BAIDU_XILING_BASE_URL", config.baidu_xiling_base_url),
    )
    syncso_missing = _missing_items(
        ("SYNCSO_API_KEY", config.syncso_api_key),
        ("SYNCSO_BASE_URL", config.syncso_base_url),
    )
    pixverse_missing = _missing_items(
        ("PIXVERSE_API_KEY", config.pixverse_api_key),
        ("PIXVERSE_BASE_URL", config.pixverse_base_url),
    )
    aliyun_bailian_missing = _missing_items(("DASHSCOPE_API_KEY", config.dashscope_api_key))
    fal_missing = _missing_items(("FAL_API_KEY", config.fal_api_key))
    tavus_missing = _missing_items(
        ("TAVUS_API_KEY", config.tavus_api_key),
        ("TAVUS_BASE_URL", config.tavus_base_url),
    )
    omnihuman_missing = _missing_items(
        ("OMNIHUMAN_ACCESS_KEY", config.omnihuman_access_key),
        ("OMNIHUMAN_ENDPOINT", config.omnihuman_endpoint),
    )

    return [
        ModelOption(
            model_id="hifly",
            category="digital_human",
            label="飞影 API 一体化数字人",
            description="上传源视频后由飞影创建形象、克隆声音并生成视频。",
            status=_configured_status(bool(config.hifly_enabled or config.cloud_video_provider == "hifly" or config.hifly_token), hifly_missing),
            missing_items=hifly_missing,
            cost_note="按飞影账号额度计费。",
            requires_paid_call=True,
            recommended_for=["一键源视频数字人", "中国用户优先"],
        ),
        ModelOption(
            model_id="baidu_xiling",
            category="digital_human",
            label="百度曦灵数字人",
            description="使用百度曦灵视频合成能力。",
            status=_configured_status(bool(config.baidu_xiling_enabled or config.cloud_video_provider == "baidu_xiling" or config.baidu_xiling_app_key), baidu_missing),
            missing_items=baidu_missing if config.baidu_xiling_enabled or config.cloud_video_provider == "baidu_xiling" or config.baidu_xiling_app_key else [],
            cost_note="按百度智能云/曦灵实际账单计费。",
            requires_paid_call=True,
            recommended_for=["企业数字人", "百度账号体系"],
        ),
        ModelOption(
            model_id="aliyun_bailian_digital_human",
            category="digital_human",
            label="阿里百炼数字人",
            description="阿里云百炼/DashScope 数字人路线入口；已保留模型选择和 Key 校验，真实成片接口确认后接入适配器。",
            status=_configured_status(
                bool(config.cloud_video_provider == "aliyun_bailian_digital_human" or config.dashscope_api_key),
                aliyun_bailian_missing,
            ),
            missing_items=aliyun_bailian_missing if config.cloud_video_provider == "aliyun_bailian_digital_human" or config.dashscope_api_key else [],
            cost_note="按阿里云百炼/DashScope 实际账单计费。",
            requires_paid_call=True,
            recommended_for=["阿里云生态", "待接入数字人成片"],
        ),
        ModelOption(
            model_id="syncso",
            category="digital_human",
            label="Sync.so 云端口型同步",
            description="使用已有形象视频和新声音进行云端口型同步。",
            status=_configured_status(bool(config.cloud_lipsync_enabled or config.syncso_api_key), syncso_missing),
            missing_items=syncso_missing if config.cloud_lipsync_enabled or config.syncso_api_key else [],
            cost_note="按 Sync.so 账号用量计费。",
            requires_paid_call=True,
            recommended_for=["口型同步", "替代本地模型"],
        ),
        ModelOption(
            model_id="fal_musetalk",
            category="digital_human",
            label="fal.ai MuseTalk 预览",
            description="云端快速口型同步，适合预览和低成本测试。",
            status=_configured_status(bool(config.cloud_video_provider == "fal_musetalk" or config.fal_api_key), fal_missing),
            missing_items=fal_missing if config.cloud_video_provider == "fal_musetalk" or config.fal_api_key else [],
            cost_note="约 $0.003/秒，以 fal.ai 实际账单为准。",
            requires_paid_call=True,
            recommended_for=["快速预览"],
        ),
        ModelOption(
            model_id="fal_latentsync",
            category="digital_human",
            label="fal.ai LatentSync 高质量",
            description="云端高质量口型同步，适合最终成片。",
            status=_configured_status(bool(config.cloud_video_provider == "fal_latentsync" or config.fal_api_key), fal_missing),
            missing_items=fal_missing if config.cloud_video_provider == "fal_latentsync" or config.fal_api_key else [],
            cost_note="约 $0.005/秒，以 fal.ai 实际账单为准。",
            requires_paid_call=True,
            recommended_for=["最终成片"],
        ),
        ModelOption(
            model_id="tavus",
            category="digital_human",
            label="Tavus 云端数字人",
            description="使用 Tavus Replica 生成数字人口播视频。",
            status=_configured_status(bool(config.tavus_enabled or config.cloud_video_provider == "tavus" or config.tavus_api_key), tavus_missing),
            missing_items=tavus_missing if config.tavus_enabled or config.cloud_video_provider == "tavus" or config.tavus_api_key else [],
            cost_note="按 Tavus 账号用量计费。",
            requires_paid_call=True,
            recommended_for=["海外数字人", "已有 Replica"],
        ),
        ModelOption(
            model_id="omnihuman",
            category="digital_human",
            label="火山 OmniHuman 数字人",
            description="使用火山/豆包生态的 OmniHuman 图片数字人生成能力。",
            status=_configured_status(bool(config.omnihuman_enabled or config.cloud_video_provider == "omnihuman" or config.omnihuman_access_key), omnihuman_missing),
            missing_items=omnihuman_missing if config.omnihuman_enabled or config.cloud_video_provider == "omnihuman" or config.omnihuman_access_key else [],
            cost_note="按火山引擎实际账单计费。",
            requires_paid_call=True,
            recommended_for=["图片数字人", "豆包/火山生态"],
        ),
        ModelOption(
            model_id="pixverse_lipsync",
            category="digital_human",
            label="PixVerse Lipsync",
            description="使用 PixVerse lipsync 模型，把形象视频和新声音合成为口型同步视频。",
            status=_configured_status(
                bool((config.cloud_lipsync_enabled and config.cloud_lipsync_provider == "pixverse") or config.pixverse_api_key),
                pixverse_missing,
            ),
            missing_items=pixverse_missing if (config.cloud_lipsync_enabled and config.cloud_lipsync_provider == "pixverse") or config.pixverse_api_key else [],
            cost_note="按 PixVerse/SuperAIAPI 账号用量计费。",
            requires_paid_call=True,
            recommended_for=["口型同步", "PixVerse 模型"],
        ),
    ]


def _script_options(config: DesktopSettingsConfig) -> list[ModelOption]:
    return [
        ModelOption(
            model_id="manual_script",
            category="script",
            label="手动输入脚本",
            description="不调用脚本模型，用户直接输入文案。",
            status="green",
            recommended_for=["最快开始", "低成本"],
        ),
        ModelOption(
            model_id="pixelle_cloud",
            category="script",
            label="Pixelle 云端脚本",
            description="调用 Pixelle 后端生成短视频脚本。",
            status="green" if config.pixelle_enabled and config.pixelle_base_url else ("disabled" if not config.pixelle_enabled else "red"),
            missing_items=[] if config.pixelle_base_url else ["PIXELLE_BASE_URL"],
            requires_paid_call=True,
            recommended_for=["批量脚本", "内容生产"],
        ),
    ]


def _export_options(config: DesktopSettingsConfig) -> list[ModelOption]:
    return [
        ModelOption(
            model_id="mp4_only",
            category="export",
            label="只导出 MP4",
            description="生成最终视频文件，不创建剪映草稿。",
            status="green",
            recommended_for=["最快交付"],
        ),
        ModelOption(
            model_id="jianying_draft",
            category="export",
            label="剪映草稿",
            description="导出可编辑剪映草稿，便于人工二次剪辑。",
            status="green" if config.jianying_enabled and config.jianying_draft_root else ("disabled" if not config.jianying_enabled else "yellow"),
            missing_items=[] if config.jianying_draft_root else ["JIANYING_DRAFT_ROOT"],
            recommended_for=["人工精剪", "团队交接"],
        ),
    ]


def _quality_options(config: DesktopSettingsConfig) -> list[ModelOption]:
    return [
        ModelOption(model_id="preview", category="quality", label="预览模式", description="偏速度和低成本。", status="green"),
        ModelOption(model_id="compat", category="quality", label="兼容模式", description="适合 Sync.so/Wav2Lip 路线。", status="green"),
        ModelOption(model_id="final", category="quality", label="最终质量", description="偏真实成片质量。", status="green"),
        ModelOption(model_id="batch", category="quality", label="批量生产", description="偏稳定和吞吐。", status="green"),
    ]


def _voice_updates(model_id: str) -> dict[str, Any]:
    if model_id == "edge_tts_no_clone":
        return {"TTS_ENGINE": "edge", "CLOUD_VOICE_PROVIDER": "edge_tts_no_clone"}
    if model_id in {"aliyun_bailian_cosyvoice", "aliyun_bailian_qwen_tts"}:
        return {"TTS_ENGINE": "cloud_clone", "CLOUD_VOICE_PROVIDER": model_id}
    if model_id == "hifly_voice_clone":
        return {"TTS_ENGINE": "hifly_voice_clone", "CLOUD_VOICE_PROVIDER": "hifly_voice_clone"}
    if model_id == "custom_http_tts":
        return {"TTS_ENGINE": "http", "CLOUD_VOICE_PROVIDER": "custom_http_tts"}
    raise ValueError(f"unknown voice model: {model_id}")


def _digital_human_updates(model_id: str) -> dict[str, Any]:
    base = {
        "HIFLY_ENABLED": False,
        "BAIDU_XILING_ENABLED": False,
        "TAVUS_ENABLED": False,
        "OMNIHUMAN_ENABLED": False,
        "CLOUD_LIPSYNC_ENABLED": False,
    }
    if model_id == "hifly":
        return {**base, "digital_human_engine": "hifly", "CLOUD_VIDEO_PROVIDER": "hifly", "HIFLY_ENABLED": True}
    if model_id == "baidu_xiling":
        return {**base, "digital_human_engine": "baidu_xiling", "CLOUD_VIDEO_PROVIDER": "baidu_xiling", "BAIDU_XILING_ENABLED": True}
    if model_id == "aliyun_bailian_digital_human":
        return {**base, "digital_human_engine": "aliyun_bailian_digital_human", "CLOUD_VIDEO_PROVIDER": "aliyun_bailian_digital_human"}
    if model_id == "syncso":
        return {**base, "digital_human_engine": "syncso", "CLOUD_VIDEO_PROVIDER": "fal_musetalk", "CLOUD_LIPSYNC_ENABLED": True, "CLOUD_LIPSYNC_PROVIDER": "syncso"}
    if model_id == "pixverse_lipsync":
        return {
            **base,
            "digital_human_engine": "pixverse_lipsync",
            "CLOUD_VIDEO_PROVIDER": "fal_musetalk",
            "CLOUD_LIPSYNC_ENABLED": True,
            "CLOUD_LIPSYNC_PROVIDER": "pixverse",
            "PIXVERSE_BASE_URL": "https://superaiapi.top",
            "PIXVERSE_MODEL": "pixverse-lipsync:stable",
            "PIXVERSE_GENERATE_ENDPOINT": "/v1/video/generations",
            "PIXVERSE_TASK_ENDPOINT_TEMPLATE": "/v1/video/tasks/{task_id}",
        }
    if model_id in {"fal_musetalk", "fal_latentsync"}:
        return {**base, "digital_human_engine": model_id, "CLOUD_VIDEO_PROVIDER": model_id}
    if model_id == "tavus":
        return {**base, "digital_human_engine": "tavus", "CLOUD_VIDEO_PROVIDER": "tavus", "TAVUS_ENABLED": True}
    if model_id == "omnihuman":
        return {**base, "digital_human_engine": "omnihuman", "CLOUD_VIDEO_PROVIDER": "omnihuman", "OMNIHUMAN_ENABLED": True}
    raise ValueError(f"unknown digital human model: {model_id}")


def _script_updates(model_id: str) -> dict[str, Any]:
    if model_id == "manual_script":
        return {"PIXELLE_ENABLED": False}
    if model_id == "pixelle_cloud":
        return {"PIXELLE_ENABLED": True}
    raise ValueError(f"unknown script model: {model_id}")


def _export_updates(model_id: str) -> dict[str, Any]:
    if model_id == "mp4_only":
        return {"editing_output": "mp4_only", "JIANYING_ENABLED": False}
    if model_id == "jianying_draft":
        return {"editing_output": "jianying_auto", "JIANYING_ENABLED": True}
    raise ValueError(f"unknown export model: {model_id}")


def _quality_updates(mode: QualityMode) -> dict[str, Any]:
    runtime_mode = "standard" if mode in {"preview", "dry-run"} else mode
    return {"runtime_mode": runtime_mode}


def _status(value: str) -> ModelStatus:
    if value in {"green", "yellow", "red", "disabled"}:
        return value  # type: ignore[return-value]
    return "disabled"


def _missing_items(*items: tuple[str, object]) -> list[str]:
    return [name for name, value in items if not str(value or "").strip()]


def _configured_status(configured: bool, missing_items: list[str]) -> ModelStatus:
    if not configured:
        return "disabled"
    return "red" if missing_items else "green"


def _settings_from_config(config: DesktopSettingsConfig):
    from app.settings import Settings

    return Settings(
        dry_run=False,
        cloud_voice_provider=config.cloud_voice_provider,
        cloud_video_provider=config.cloud_video_provider,
        dashscope_api_key=config.dashscope_api_key,
        fal_api_key=config.fal_api_key,
        hifly_token=config.hifly_token,
        hifly_base_url=config.hifly_base_url,
        baidu_xiling_app_id=config.baidu_xiling_app_id,
        baidu_xiling_app_key=config.baidu_xiling_app_key,
        baidu_xiling_figure_id=config.baidu_xiling_figure_id,
        baidu_xiling_base_url=config.baidu_xiling_base_url,
        custom_http_tts_base_url=config.custom_http_tts_base_url,
        custom_http_tts_api_key=config.custom_http_tts_api_key,
        azure_speech_key=config.azure_speech_key,
        azure_speech_endpoint=config.azure_speech_endpoint,
        aliyun_bailian_region=config.aliyun_bailian_region,
        aliyun_voice_model=config.aliyun_voice_model,
        self_hosted_lipsync_base_url=config.self_hosted_lipsync_base_url,
        self_hosted_lipsync_api_key=config.self_hosted_lipsync_api_key,
        syncso_api_key=config.syncso_api_key,
        syncso_base_url=config.syncso_base_url,
        syncso_model=config.syncso_model,
        pixverse_api_key=config.pixverse_api_key,
        pixverse_base_url=config.pixverse_base_url,
        pixverse_model=config.pixverse_model,
    )
