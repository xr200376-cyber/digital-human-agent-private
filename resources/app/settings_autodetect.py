from __future__ import annotations

import importlib.util
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

from app.cloud_providers import build_cloud_provider_configs
from app.desktop_settings import DesktopSettingsConfig


ModuleState = Literal["ready", "warning", "missing", "disabled"]
UrlChecker = Callable[[str], bool]


class ModuleStatus(BaseModel):
    key: str
    label: str
    status: ModuleState
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    recommended_action: str = ""


class SettingsAutoDetectResult(BaseModel):
    module_statuses: list[ModuleStatus]
    detected_values: dict[str, Any] = Field(default_factory=dict)
    recommended_actions: list[str] = Field(default_factory=list)


def run_settings_autodetect(
    config: DesktopSettingsConfig,
    *,
    repository_root: Path,
    url_checker: UrlChecker | None = None,
) -> SettingsAutoDetectResult:
    checker = url_checker or _default_url_checker
    detected: dict[str, Any] = {}
    statuses = [
        _detect_tts(config, checker, detected),
        _detect_pixelle(config, checker, detected),
        *_detect_cloud_providers(config),
        _detect_cloud_lipsync(config, checker, detected),
        _detect_omnihuman(config, checker, detected),
        _detect_tavus(config, checker, detected),
        _detect_baidu_xiling(config, checker, detected),
        _detect_hifly(config, checker, detected),
        _detect_wav2lip(config, repository_root),
        _detect_yywav2lip(config, repository_root),
        _detect_musetalk(config, repository_root),
        _detect_latentsync(config, repository_root),
        _detect_jianying(config, repository_root, detected),
        _detect_duix(config, checker, detected),
    ]
    actions = [status.recommended_action for status in statuses if status.status in {"warning", "missing"} and status.recommended_action]
    return SettingsAutoDetectResult(module_statuses=statuses, detected_values=detected, recommended_actions=actions)


def _detect_cloud_providers(config: DesktopSettingsConfig) -> list[ModuleStatus]:
    settings = _settings_from_desktop_config(config)
    statuses: list[ModuleStatus] = []
    labels = {
        "aliyun_bailian_cosyvoice": "阿里云百炼 CosyVoice 声音克隆",
        "aliyun_bailian_qwen_tts": "阿里云百炼 Qwen-TTS",
        "aliyun_bailian_minimax": "阿里云百炼 MiniMax 声音克隆",
        "elevenlabs": "ElevenLabs 声音克隆",
        "azure_tts_no_clone": "Azure TTS",
        "edge_tts_no_clone": "Edge TTS",
        "custom_http_tts": "自定义 HTTP TTS",
        "fal_latentsync": "fal.ai LatentSync",
        "fal_musetalk": "fal.ai MuseTalk",
        "self_hosted_lipsync": "自建口型同步服务",
        "baidu_xiling": "百度曦灵数字人",
        "hifly": "飞影 API 数字人",
        "did_optional": "D-ID 可选",
        "heygen_optional": "HeyGen 可选",
    }
    for provider in build_cloud_provider_configs(settings):
        if not provider.enabled:
            continue
        status: ModuleState = "ready" if provider.status == "green" else ("warning" if provider.status == "yellow" else "missing")
        statuses.append(
            ModuleStatus(
                key=provider.provider_id,
                label=labels.get(provider.provider_id, provider.provider_id),
                status=status,
                message=provider.message,
                details=provider.model_dump(mode="json"),
                recommended_action=_cloud_provider_action(provider.provider_id, provider.missing_items),
            )
        )
    return statuses


def _settings_from_desktop_config(config: DesktopSettingsConfig):
    from app.settings import Settings

    return Settings(
        dry_run=config.runtime_mode == "dry-run",
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


def _cloud_provider_action(provider_id: str, missing_items: list[str]) -> str:
    if not missing_items:
        return "当前云端供应商关键配置已填写。"
    if provider_id.startswith("aliyun_bailian"):
        return "填写 DASHSCOPE_API_KEY；如需固定区域和模型，请设置 ALIYUN_BAILIAN_REGION、ALIYUN_VOICE_MODEL。"
    if provider_id.startswith("fal_"):
        return "填写 FAL_API_KEY；预览建议 fal.ai MuseTalk，最终质量建议 fal.ai LatentSync。"
    if provider_id == "self_hosted_lipsync":
        return "填写 SELF_HOSTED_LIPSYNC_BASE_URL，并确认服务能读取公开视频和音频 URL。"
    if provider_id == "baidu_xiling":
        return "填写百度曦灵 AppID、AppKey 和 figureId；需要在百度智能云曦灵开放平台先开通应用。"
    if provider_id == "hifly":
        return "填写 HIFLY_TOKEN；真实调用前还需要公网 source video/audio URL 或 Hifly 文件上传机制。"
    return "补齐缺失的云端服务配置后再进入真实模式。"


def _detect_tts(config: DesktopSettingsConfig, checker: UrlChecker, detected: dict[str, Any]) -> ModuleStatus:
    edge_available = importlib.util.find_spec("edge_tts") is not None
    detected["edge_tts_available"] = edge_available
    engine = config.tts_engine.lower()
    cosy_url = config.cosyvoice_url or ("http://127.0.0.1:50000" if engine in {"cosyvoice", "cosyvoice_http"} else "")
    gpt_url = config.gpt_sovits_url or ("http://127.0.0.1:9880" if engine in {"gpt-sovits", "gpt_sovits", "gpt_sovits_http", "gpt-sovits-http"} else "")
    generic_url = config.tts_base_url or ""
    cosy_ready = bool(cosy_url and checker(cosy_url))
    gpt_ready = bool(gpt_url and checker(gpt_url))
    generic_ready = bool(generic_url and engine in {"http", "generic_http"} and checker(generic_url))
    azure_ready = _has_any_env("AZURE_SPEECH_KEY", "AZURE_TTS_KEY") and _has_any_env("AZURE_SPEECH_REGION", "AZURE_REGION")
    aliyun_ready = _has_any_env("ALIYUN_ACCESS_KEY_ID") and _has_any_env("ALIYUN_ACCESS_KEY_SECRET")
    if cosy_ready:
        detected["cosyvoice_url"] = cosy_url
    if gpt_ready:
        detected["gpt_sovits_url"] = gpt_url
    if generic_ready:
        detected["tts_base_url"] = generic_url

    providers = {
        "edge_tts": edge_available,
        "cosyvoice_http": cosy_ready,
        "gpt_sovits_http": gpt_ready,
        "generic_http": generic_ready,
        "azure_tts": azure_ready,
        "aliyun_tts": aliyun_ready,
    }
    if config.tts_engine.lower() in {"", "dryrun", "dry-run"}:
        return ModuleStatus(
            key="tts",
            label="语音合成",
            status="warning",
            message="当前仍使用占位声音，不是真实 TTS。",
            details=providers,
            recommended_action="最快方式是选择 Edge TTS，或配置阿里云/微软/CosyVoice/GPT-SoVITS。",
        )
    if any(providers.values()):
        ready_names = [name for name, ready in providers.items() if ready]
        return ModuleStatus(
            key="tts",
            label="语音合成",
            status="ready",
            message="已检测到真实 TTS 可用：" + "、".join(ready_names),
            details=providers,
            recommended_action="选择一个真实声音方案，避免真实模式继续使用占位声音。",
        )
    if config.tts_engine.lower() in {"", "dryrun", "dry-run"}:
        return ModuleStatus(
            key="tts",
            label="语音合成",
            status="warning",
            message="当前仍使用占位声音，不是真实 TTS。",
            details=providers,
            recommended_action="最快方式是安装 edge-tts，或配置阿里云/微软/CosyVoice/GPT-SoVITS。",
        )
    return ModuleStatus(
        key="tts",
        label="语音合成",
        status="missing",
        message=f"已选择 {config.tts_engine}，但没有检测到可用服务或凭据。",
        details=providers,
        recommended_action="检查 TTS URL、云服务凭据或切回 dry-run 试用。",
    )


def _detect_pixelle(config: DesktopSettingsConfig, checker: UrlChecker, detected: dict[str, Any]) -> ModuleStatus:
    if not config.pixelle_enabled:
        return ModuleStatus(
            key="pixelle",
            label="Pixelle",
            status="disabled",
            message="Pixelle 当前未启用。",
            details={"base_url": config.pixelle_base_url},
            recommended_action="启用 Pixelle HTTP 后端后再进行自动检测。",
        )
    candidates = [config.pixelle_base_url, "http://127.0.0.1:8000"]
    ready_url = next((url for url in candidates if url and checker(url)), "")
    if ready_url:
        detected["pixelle_base_url"] = ready_url
        return ModuleStatus(
            key="pixelle",
            label="Pixelle",
            status="ready",
            message=f"Pixelle 后端可访问：{ready_url}",
            details={"base_url": ready_url},
            recommended_action="可以启用真实脚本/视频后端。",
        )
    return ModuleStatus(
        key="pixelle",
        label="Pixelle",
        status="missing" if config.pixelle_enabled else "disabled",
        message="未检测到 Pixelle HTTP 后端。" if config.pixelle_enabled else "Pixelle 当前未启用。",
        details={"base_url": config.pixelle_base_url},
        recommended_action="启动 Pixelle 后端，或继续使用本地 dry-run/shim。",
    )


def _detect_cloud_lipsync(config: DesktopSettingsConfig, checker: UrlChecker, detected: dict[str, Any]) -> ModuleStatus:
    provider = config.cloud_lipsync_provider.lower().strip() or "syncso"
    base_url = config.syncso_base_url or "https://api.sync.so"
    api_key_configured = bool(config.syncso_api_key)
    if not config.cloud_lipsync_enabled:
        return ModuleStatus(
            key="cloud_lipsync",
            label="Sync.so 云端口型同步",
            status="disabled",
            message="云端口型同步当前未启用。",
            details={"provider": "syncso", "base_url": base_url, "api_key_configured": api_key_configured},
            recommended_action="如果要替代本地 YYWav2Lip，可选择 Sync.so 云端口型同步并填写 API Key。",
        )
    if provider != "syncso":
        return ModuleStatus(
            key="cloud_lipsync",
            label="云端口型同步",
            status="missing" if config.cloud_lipsync_enabled else "disabled",
            message=f"暂不支持的云端口型同步服务：{config.cloud_lipsync_provider}",
            details={"provider": config.cloud_lipsync_provider},
            recommended_action="当前建议选择 Sync.so 云端口型同步。",
        )
    base_url = config.syncso_base_url or "https://api.sync.so"
    reachable = checker(base_url)
    api_key_configured = bool(config.syncso_api_key)
    if config.cloud_lipsync_enabled and api_key_configured and reachable:
        detected["syncso_base_url"] = base_url
        return ModuleStatus(
            key="cloud_lipsync",
            label="Sync.so 云端口型同步",
            status="ready",
            message=f"Sync.so 云端服务已配置：{base_url}",
            details={
                "provider": "syncso",
                "base_url": base_url,
                "api_key_configured": True,
                "model": config.syncso_model,
                "generate_endpoint": config.syncso_generate_endpoint,
            },
            recommended_action="可以使用 Sync.so 进行云端口型同步；请确认上传素材符合你的授权和平台合规要求。",
        )
    if config.cloud_lipsync_enabled:
        missing = []
        if not api_key_configured:
            missing.append("SYNCSO_API_KEY")
        if not reachable:
            missing.append("SYNCSO_BASE_URL")
        return ModuleStatus(
            key="cloud_lipsync",
            label="Sync.so 云端口型同步",
            status="missing",
            message="Sync.so 云端口型同步未就绪：" + "、".join(missing),
            details={
                "provider": "syncso",
                "base_url": base_url,
                "api_key_configured": api_key_configured,
                "base_url_reachable": reachable,
                "model": config.syncso_model,
            },
            recommended_action="填写 Sync.so API Key，并确认网络能访问 https://api.sync.so。",
        )
    return ModuleStatus(
        key="cloud_lipsync",
        label="Sync.so 云端口型同步",
        status="disabled",
        message="云端口型同步当前未启用。",
        details={"provider": "syncso", "base_url": base_url, "api_key_configured": api_key_configured},
        recommended_action="如果要替代本地 YYWav2Lip，可选择 Sync.so 云端口型同步并填写 API Key。",
    )


def _detect_omnihuman(config: DesktopSettingsConfig, checker: UrlChecker, detected: dict[str, Any]) -> ModuleStatus:
    endpoint = config.omnihuman_endpoint or "https://visual.volcengineapi.com"
    access_key_configured = bool(config.omnihuman_access_key)
    secret_key_configured = bool(config.omnihuman_secret_key)
    if not config.omnihuman_enabled:
        return ModuleStatus(
            key="omnihuman_cloud",
            label="火山 OmniHuman1.5",
            status="disabled",
            message="火山/BytePlus OmniHuman1.5 当前未启用。",
            details={"endpoint": endpoint, "access_key_configured": access_key_configured, "secret_key_configured": secret_key_configured},
            recommended_action="如果要使用火山/BytePlus OmniHuman1.5，请启用 OMNIHUMAN_ENABLED 并填写 AK/SK。",
        )
    reachable = checker(endpoint)
    if config.omnihuman_enabled and access_key_configured and secret_key_configured and reachable:
        detected["omnihuman_endpoint"] = endpoint
        return ModuleStatus(
            key="omnihuman_cloud",
            label="火山 OmniHuman1.5",
            status="ready",
            message=f"火山 OmniHuman1.5 已配置：{endpoint}",
            details={
                "endpoint": endpoint,
                "region": config.omnihuman_region,
                "version": config.omnihuman_version,
                "req_key": config.omnihuman_req_key,
                "access_key_configured": True,
                "secret_key_configured": True,
            },
            recommended_action="任务需要提供公网可访问的 omnihuman_image_url 和 omnihuman_audio_url。",
        )
    if config.omnihuman_enabled:
        missing = []
        if not access_key_configured:
            missing.append("OMNIHUMAN_ACCESS_KEY")
        if not secret_key_configured:
            missing.append("OMNIHUMAN_SECRET_KEY")
        if not reachable:
            missing.append("OMNIHUMAN_ENDPOINT")
        return ModuleStatus(
            key="omnihuman_cloud",
            label="火山 OmniHuman1.5",
            status="missing",
            message="火山 OmniHuman1.5 未就绪：" + "、".join(missing),
            details={
                "endpoint": endpoint,
                "base_url_reachable": reachable,
                "access_key_configured": access_key_configured,
                "secret_key_configured": secret_key_configured,
            },
            recommended_action="填写火山 Access Key/Secret Key，并确认网络能访问 https://visual.volcengineapi.com。",
        )
    return ModuleStatus(
        key="omnihuman_cloud",
        label="火山 OmniHuman1.5",
        status="disabled",
        message="火山 OmniHuman1.5 当前未启用。",
        details={"endpoint": endpoint, "access_key_configured": access_key_configured, "secret_key_configured": secret_key_configured},
        recommended_action="如果要用火山 OmniHuman1.5 云端数字人，请启用 OMNIHUMAN_ENABLED 并填写 AK/SK。",
    )


def _detect_tavus(config: DesktopSettingsConfig, checker: UrlChecker, detected: dict[str, Any]) -> ModuleStatus:
    base_url = config.tavus_base_url or "https://tavusapi.com"
    api_key_configured = bool(config.tavus_api_key)
    replica_configured = bool(config.tavus_replica_id)
    if not config.tavus_enabled:
        return ModuleStatus(
            key="tavus_cloud",
            label="Tavus 自定义 Replica",
            status="disabled",
            message="Tavus 云端数字人当前未启用。",
            details={"base_url": base_url, "api_key_configured": api_key_configured, "replica_id": config.tavus_replica_id},
            recommended_action="如果要让 Tavus 负责声音、口型和视频，请启用 TAVUS_ENABLED 并填写 Replica ID。",
        )
    reachable = checker(base_url)
    if config.tavus_enabled and api_key_configured and replica_configured and reachable:
        detected["tavus_base_url"] = base_url
        detected["tavus_replica_id"] = config.tavus_replica_id
        return ModuleStatus(
            key="tavus_cloud",
            label="Tavus 自定义 Replica",
            status="ready",
            message=f"Tavus 云端数字人已配置：{config.tavus_replica_id}",
            details={"base_url": base_url, "api_key_configured": True, "replica_id": config.tavus_replica_id},
            recommended_action="可以用 Tavus Replica 直接生成带声音和口型的完整数字人视频。",
        )
    missing = []
    if not api_key_configured:
        missing.append("TAVUS_API_KEY")
    if not replica_configured:
        missing.append("TAVUS_REPLICA_ID")
    if not reachable:
        missing.append("TAVUS_BASE_URL")
    return ModuleStatus(
        key="tavus_cloud",
        label="Tavus 自定义 Replica",
        status="missing",
        message="Tavus 云端数字人未就绪：" + "、".join(missing),
        details={"base_url": base_url, "api_key_configured": api_key_configured, "replica_id": config.tavus_replica_id},
        recommended_action="填写 Tavus API Key 和已完成训练的 Replica ID。",
    )


def _detect_baidu_xiling(config: DesktopSettingsConfig, checker: UrlChecker, detected: dict[str, Any]) -> ModuleStatus:
    base_url = config.baidu_xiling_base_url or "https://open.xiling.baidu.com"
    app_id_configured = bool(config.baidu_xiling_app_id)
    app_key_configured = bool(config.baidu_xiling_app_key)
    figure_configured = bool(config.baidu_xiling_figure_id)
    enabled = config.baidu_xiling_enabled or config.cloud_video_provider == "baidu_xiling"
    if not enabled:
        return ModuleStatus(
            key="baidu_xiling",
            label="百度曦灵数字人",
            status="disabled",
            message="百度曦灵当前未启用。",
            details={
                "base_url": base_url,
                "app_id_configured": app_id_configured,
                "app_key_configured": app_key_configured,
                "figure_id_configured": figure_configured,
            },
            recommended_action="如果要使用百度曦灵生成数字人视频，请启用 BAIDU_XILING_ENABLED 并选择 CLOUD_VIDEO_PROVIDER=baidu_xiling。",
        )
    reachable = checker(base_url)
    if app_id_configured and app_key_configured and figure_configured and reachable:
        detected["baidu_xiling_base_url"] = base_url
        detected["baidu_xiling_figure_id"] = config.baidu_xiling_figure_id
        return ModuleStatus(
            key="baidu_xiling",
            label="百度曦灵数字人",
            status="ready",
            message=f"百度曦灵已配置：figureId={config.baidu_xiling_figure_id}",
            details={
                "base_url": base_url,
                "app_id_configured": True,
                "app_key_configured": True,
                "figure_id_configured": True,
                "tts_person_configured": bool(config.baidu_xiling_tts_person),
            },
            recommended_action="可以选择百度曦灵作为云端数字人视频引擎；付费生成前请确认账号额度和素材授权。",
        )
    missing = []
    if not app_id_configured:
        missing.append("BAIDU_XILING_APP_ID")
    if not app_key_configured:
        missing.append("BAIDU_XILING_APP_KEY")
    if not figure_configured:
        missing.append("BAIDU_XILING_FIGURE_ID")
    if not reachable:
        missing.append("BAIDU_XILING_BASE_URL")
    return ModuleStatus(
        key="baidu_xiling",
        label="百度曦灵数字人",
        status="missing",
        message="百度曦灵未就绪：" + "、".join(missing),
        details={
            "base_url": base_url,
            "base_url_reachable": reachable,
            "app_id_configured": app_id_configured,
            "app_key_configured": app_key_configured,
            "figure_id_configured": figure_configured,
            "tts_person_configured": bool(config.baidu_xiling_tts_person),
        },
        recommended_action="在百度智能云曦灵开放平台开通应用后，填写 AppID、AppKey、figureId 和可选发音人 ID。",
    )


def _detect_hifly(config: DesktopSettingsConfig, checker: UrlChecker, detected: dict[str, Any]) -> ModuleStatus:
    base_url = config.hifly_base_url or "https://hfw-api.hifly.cc"
    token_configured = bool(config.hifly_token)
    enabled = config.hifly_enabled or config.cloud_video_provider == "hifly"
    if not enabled:
        return ModuleStatus(
            key="hifly",
            label="飞影 API 数字人",
            status="disabled",
            message="飞影 API 当前未启用。",
            details={"base_url": base_url, "token_configured": token_configured},
            recommended_action="如需上传源视频直接制作数字人，请启用 HIFLY_ENABLED 或选择 CLOUD_VIDEO_PROVIDER=hifly。",
        )
    reachable = checker(base_url)
    if token_configured and reachable:
        detected["hifly_base_url"] = base_url
        return ModuleStatus(
            key="hifly",
            label="飞影 API 数字人",
            status="ready",
            message="飞影 API 已配置；真实生成前还需要公网 video_url/audio_url。",
            details={"base_url": base_url, "token_configured": True, "base_url_reachable": True},
            recommended_action="上传源视频后填写公网源视频 URL 和声音 URL，再勾选确认消耗额度。",
        )
    missing = []
    if not token_configured:
        missing.append("HIFLY_TOKEN")
    if not reachable:
        missing.append("HIFLY_BASE_URL")
    return ModuleStatus(
        key="hifly",
        label="飞影 API 数字人",
        status="missing",
        message="飞影 API 未就绪：" + "、".join(missing),
        details={"base_url": base_url, "token_configured": token_configured, "base_url_reachable": reachable},
        recommended_action="填写 HIFLY_TOKEN，并确认 HIFLY_BASE_URL 可访问；真实调用前准备公网素材 URL 或接入文件上传。",
    )


def _detect_wav2lip(config: DesktopSettingsConfig, repository_root: Path) -> ModuleStatus:
    checkpoint = _resolve_path(config.wav2lip_checkpoint, repository_root)
    root = _resolve_path(config.wav2lip_root, repository_root)
    ready = checkpoint.is_file()
    return ModuleStatus(
        key="wav2lip",
        label="Wav2Lip",
        status="ready" if ready else ("missing" if config.wav2lip_enabled else "disabled"),
        message=f"已找到 Wav2Lip checkpoint：{checkpoint}" if ready else f"未找到 Wav2Lip checkpoint：{checkpoint}",
        details={"root": str(root), "checkpoint": str(checkpoint), "root_exists": root.is_dir(), "checkpoint_exists": ready},
        recommended_action="把 wav2lip.pth 放在仓库外部模型目录，并在高级设置里填写路径。",
    )


def _detect_yywav2lip(config: DesktopSettingsConfig, repository_root: Path) -> ModuleStatus:
    checkpoint = _resolve_path(config.yy_wav2lip_checkpoint, repository_root)
    role_dir = _resolve_path(config.yy_wav2lip_role_model_dir, repository_root) if config.yy_wav2lip_role_model_dir else None
    ready = checkpoint.is_file() and bool(role_dir and role_dir.is_dir())
    if ready:
        message = "已找到 YYWav2Lip checkpoint 和角色模型目录。"
    else:
        message = "未找到 YYWav2Lip checkpoint 或角色模型目录。"
    return ModuleStatus(
        key="yywav2lip",
        label="YYWav2Lip",
        status="ready" if ready else ("missing" if config.yy_wav2lip_enabled else "disabled"),
        message=message,
        details={
            "checkpoint": str(checkpoint),
            "checkpoint_exists": checkpoint.is_file(),
            "role_model_dir": str(role_dir) if role_dir else "",
            "role_model_dir_exists": bool(role_dir and role_dir.is_dir()),
        },
        recommended_action="配置 yywav2lip.pth 和 model_9.pkl/model_10.pkl 所在角色模型目录，文件不要放进仓库。",
    )


def _detect_musetalk(config: DesktopSettingsConfig, repository_root: Path) -> ModuleStatus:
    model_dir = _resolve_path(config.musetalk_model_dir, repository_root) if config.musetalk_model_dir else None
    root = _resolve_path(config.musetalk_root, repository_root)
    ready = bool(model_dir and model_dir.is_dir())
    return ModuleStatus(
        key="musetalk",
        label="MuseTalk",
        status="ready" if ready else ("missing" if config.musetalk_enabled else "disabled"),
        message=f"已找到 MuseTalk 模型目录：{model_dir}" if ready else "未找到 MuseTalk 模型目录。",
        details={"root": str(root), "root_exists": root.is_dir(), "model_dir": str(model_dir) if model_dir else "", "model_dir_exists": ready},
        recommended_action="按模型配置文档填写 MUSETALK_MODEL_DIR，模型权重保留在仓库外。",
    )


def _detect_latentsync(config: DesktopSettingsConfig, repository_root: Path) -> ModuleStatus:
    checkpoint = _resolve_path(config.latentsync_checkpoint, repository_root) if config.latentsync_checkpoint else None
    unet_config = _resolve_path(config.latentsync_unet_config, repository_root) if config.latentsync_unet_config else None
    root = _resolve_path(config.latentsync_root, repository_root)
    ready = bool(checkpoint and checkpoint.is_file() and unet_config and unet_config.is_file())
    return ModuleStatus(
        key="latentsync",
        label="LatentSync",
        status="ready" if ready else ("missing" if config.latentsync_enabled else "disabled"),
        message="已找到 LatentSync checkpoint 和 UNet 配置。" if ready else "未找到 LatentSync checkpoint 或 UNet 配置。",
        details={
            "root": str(root),
            "root_exists": root.is_dir(),
            "checkpoint": str(checkpoint) if checkpoint else "",
            "checkpoint_exists": bool(checkpoint and checkpoint.is_file()),
            "unet_config": str(unet_config) if unet_config else "",
            "unet_config_exists": bool(unet_config and unet_config.is_file()),
        },
        recommended_action="按模型配置文档填写 LATENTSYNC_CHECKPOINT 和 LATENTSYNC_UNET_CONFIG。",
    )


def _detect_jianying(config: DesktopSettingsConfig, repository_root: Path, detected: dict[str, Any]) -> ModuleStatus:
    candidates: list[Path] = []
    if config.jianying_draft_root:
        candidates.append(_resolve_path(config.jianying_draft_root, repository_root))
    candidates.extend(_common_jianying_paths())
    ready_path = next((path for path in candidates if path.is_dir() and os.access(path, os.W_OK)), None)
    if ready_path:
        detected["jianying_draft_root"] = str(ready_path)
        return ModuleStatus(
            key="jianying",
            label="剪映草稿",
            status="ready",
            message=f"已找到可写剪映/CapCut 草稿目录：{ready_path}",
            details={"draft_root": str(ready_path), "candidates": [str(path) for path in candidates]},
            recommended_action="可以启用剪映草稿导出。",
        )
    return ModuleStatus(
        key="jianying",
        label="剪映草稿",
        status="missing" if config.jianying_enabled else "disabled",
        message="未检测到可写剪映/CapCut 草稿目录。",
        details={"draft_root": config.jianying_draft_root, "candidates": [str(path) for path in candidates]},
        recommended_action="打开剪映/CapCut 创建一次草稿，或手动填写 JIANYING_DRAFT_ROOT。",
    )


def _detect_duix(config: DesktopSettingsConfig, checker: UrlChecker, detected: dict[str, Any]) -> ModuleStatus:
    if not config.duix_enabled:
        return ModuleStatus(
            key="duix",
            label="Duix HTTP",
            status="disabled",
            message="Duix 当前未启用。",
            details={"base_url": config.duix_base_url, "policy": "HTTP only; do not vendor Duix source."},
            recommended_action="如需 Duix，请先启动外部 HTTP 服务并确认商业授权；不要复制 Duix 源码。",
        )
    candidates = [config.duix_base_url, "http://127.0.0.1:8088"]
    ready_url = next((url for url in candidates if url and checker(url)), "")
    if ready_url:
        detected["duix_base_url"] = ready_url
        return ModuleStatus(
            key="duix",
            label="Duix HTTP",
            status="ready",
            message=f"Duix HTTP 服务可访问：{ready_url}",
            details={"base_url": ready_url, "policy": "HTTP only; do not vendor Duix source."},
            recommended_action="可以在 final 模式中启用 Duix HTTP。",
        )
    return ModuleStatus(
        key="duix",
        label="Duix HTTP",
        status="missing" if config.duix_enabled else "disabled",
        message="未检测到 Duix HTTP 服务。" if config.duix_enabled else "Duix 当前未启用。",
        details={"base_url": config.duix_base_url, "policy": "HTTP only; do not vendor Duix source."},
        recommended_action="如需 Duix，先启动外部 HTTP 服务并确认商业授权；不要复制 Duix 源码。",
    )


def _default_url_checker(url: str) -> bool:
    if not url:
        return False
    try:
        with httpx.Client(timeout=httpx.Timeout(1.0, connect=0.4), follow_redirects=True, trust_env=False) as client:
            response = client.get(url)
        return response.status_code < 500
    except Exception:  # noqa: BLE001 - detection must not crash the settings wizard.
        return False


def _resolve_path(value: str | os.PathLike[str], repository_root: Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else repository_root / path


def _common_jianying_paths() -> list[Path]:
    local = os.getenv("LOCALAPPDATA", "")
    appdata = os.getenv("APPDATA", "")
    userprofile = os.getenv("USERPROFILE", "")
    roots = [
        Path(local) / "JianyingPro" / "User Data" / "Projects" if local else None,
        Path(local) / "CapCut" / "User Data" / "Projects" if local else None,
        Path(appdata) / "JianyingPro" / "User Data" / "Projects" if appdata else None,
        Path(userprofile) / "Documents" / "JianyingPro Drafts" if userprofile else None,
        Path(userprofile) / "Documents" / "CapCut Drafts" if userprofile else None,
    ]
    return [path for path in roots if path is not None]


def _has_any_env(*names: str) -> bool:
    return any(bool(os.getenv(name)) for name in names)
