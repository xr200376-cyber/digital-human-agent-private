from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterable

from app.schemas import CloudCostEstimate, CloudProviderConfig, CloudProviderType
from app.settings import Settings


@dataclass(frozen=True)
class ProviderSpec:
    provider_id: str
    provider_type: CloudProviderType
    api_key_env_name: str = ""
    base_url: str = ""
    model: str = ""
    label: str = ""
    cost_estimate: str = ""
    optional: bool = False
    no_clone: bool = False


VOICE_PROVIDER_IDS = {
    "aliyun_bailian_cosyvoice",
    "aliyun_bailian_qwen_tts",
    "aliyun_bailian_minimax",
    "hifly_voice_clone",
    "elevenlabs",
    "azure_tts_no_clone",
    "edge_tts_no_clone",
    "custom_http_tts",
}

VIDEO_PROVIDER_IDS = {
    "fal_latentsync",
    "fal_musetalk",
    "pixverse_lipsync",
    "did_optional",
    "heygen_optional",
    "self_hosted_lipsync",
    "baidu_xiling",
    "hifly",
}

FAL_LATENTSYNC_USD_PER_SECOND = 0.005
FAL_MUSETALK_USD_PER_SECOND = 0.003
ALIYUN_VOICE_CLONE_SETUP_USD = 0.50
ALIYUN_VOICE_SYNTHESIS_USD_PER_1K_CHARS = 0.003
ELEVENLABS_SYNTHESIS_USD_PER_1K_CHARS = 0.015


def build_cloud_provider_configs(settings: Settings) -> list[CloudProviderConfig]:
    selected_voice = _provider_id(settings.cloud_voice_provider)
    selected_video = _provider_id(settings.cloud_video_provider)
    return [
        _to_config(spec, settings, selected_voice if spec.provider_type == CloudProviderType.voice else selected_video)
        for spec in _provider_specs(settings)
    ]


def provider_config_map(settings: Settings) -> dict[str, CloudProviderConfig]:
    return {config.provider_id: config for config in build_cloud_provider_configs(settings)}


def cloud_voice_provider_ready(settings: Settings, provider_id: str | None = None) -> bool:
    provider = _provider_id(provider_id or settings.cloud_voice_provider)
    config = provider_config_map(settings).get(provider)
    return bool(config and config.status == "green")


def cloud_video_provider_ready(settings: Settings, provider_id: str | None = None) -> bool:
    provider = _provider_id(provider_id or settings.cloud_video_provider)
    config = provider_config_map(settings).get(provider)
    return bool(config and config.status == "green")


def preferred_cloud_video_provider(render_profile: str, settings: Settings) -> str | None:
    selected = _provider_id(settings.cloud_video_provider)
    if selected in VIDEO_PROVIDER_IDS:
        return selected
    if render_profile == "preview":
        return "fal_musetalk"
    if render_profile == "final":
        return "fal_latentsync"
    return None


def estimate_cloud_cost(
    *,
    videos_per_month: int,
    average_duration_seconds: int,
    average_chinese_chars_per_video: int,
    voice_provider: str,
    video_provider: str,
) -> CloudCostEstimate:
    videos = max(0, int(videos_per_month))
    duration = max(0, int(average_duration_seconds))
    chars = max(0, int(average_chinese_chars_per_video))
    voice = _provider_id(voice_provider)
    video = _provider_id(video_provider)
    warnings: list[str] = []

    voice_clone_setup_cost = 0.0
    voice_synthesis_cost = 0.0
    if voice.startswith("aliyun_bailian_"):
        voice_clone_setup_cost = ALIYUN_VOICE_CLONE_SETUP_USD
        voice_synthesis_cost = (videos * chars / 1000.0) * ALIYUN_VOICE_SYNTHESIS_USD_PER_1K_CHARS
        warnings.append("阿里云百炼费用为工程估算，请以下单页面和账单为准。")
    elif voice == "elevenlabs":
        voice_clone_setup_cost = 1.0
        voice_synthesis_cost = (videos * chars / 1000.0) * ELEVENLABS_SYNTHESIS_USD_PER_1K_CHARS
        warnings.append("ElevenLabs 国际化效果好，但中文和克隆成本通常不是最低。")
    elif voice == "hifly_voice_clone":
        warnings.append("飞影声音克隆按飞影/Hifly API 额度计费，本地只做配置检查，不估算固定单价。")
    elif voice in {"azure_tts_no_clone", "edge_tts_no_clone"}:
        warnings.append("当前声音方案不是正式声音克隆，只适合作为稳定 TTS 或试用方案。")
    elif voice == "custom_http_tts":
        warnings.append("自定义 HTTP TTS 费用由你的服务决定，这里按 0 估算。")

    video_render_cost = 0.0
    if video == "fal_latentsync":
        video_render_cost = videos * duration * FAL_LATENTSYNC_USD_PER_SECOND
    elif video == "fal_musetalk":
        video_render_cost = videos * duration * FAL_MUSETALK_USD_PER_SECOND
        warnings.append("fal.ai MuseTalk 更适合低成本预览，最终质量建议使用 LatentSync。")
    elif video == "self_hosted_lipsync":
        warnings.append("自建模型服务按云主机/GPU 成本计费，本估算不含机器成本。")
    elif video == "baidu_xiling":
        warnings.append("百度曦灵按百度智能云/曦灵账号账单计费；当前只做接入状态，不在本地估算具体单价。")
    elif video == "hifly":
        warnings.append("飞影数字人按飞影/Hifly API 额度计费；本地只检查配置，不估算具体单价。")
    elif video in {"did_optional", "heygen_optional"}:
        video_render_cost = videos * duration * 0.02
        warnings.append("D-ID/HeyGen 是一站式可选方案，通常成本高于 fal.ai 或自建服务。")

    voice_synthesis_cost = _money(voice_synthesis_cost)
    video_render_cost = _money(video_render_cost)
    voice_clone_setup_cost = _money(voice_clone_setup_cost if videos > 0 else 0.0)
    total = _money(voice_clone_setup_cost + voice_synthesis_cost + video_render_cost)
    return CloudCostEstimate(
        voice_clone_setup_cost=voice_clone_setup_cost,
        voice_synthesis_cost=voice_synthesis_cost,
        video_render_cost=video_render_cost,
        estimated_monthly_total=total,
        warnings=list(dict.fromkeys(warnings)),
        inputs={
            "videos_per_month": videos,
            "average_duration_seconds": duration,
            "average_chinese_chars_per_video": chars,
            "voice_provider": voice,
            "video_provider": video,
        },
    )


def _provider_specs(settings: Settings) -> Iterable[ProviderSpec]:
    aliyun_base = f"https://dashscope.aliyuncs.com/{settings.aliyun_bailian_region}".rstrip("/")
    fal_base = "https://fal.run"
    yield ProviderSpec(
        "aliyun_bailian_cosyvoice",
        CloudProviderType.voice,
        api_key_env_name="DASHSCOPE_API_KEY",
        base_url=aliyun_base,
        model=settings.aliyun_voice_model or "cosyvoice-v1",
        label="阿里云百炼 CosyVoice",
        cost_estimate="中文声音克隆推荐，按克隆建档和合成量计费",
    )
    yield ProviderSpec(
        "aliyun_bailian_qwen_tts",
        CloudProviderType.voice,
        api_key_env_name="DASHSCOPE_API_KEY",
        base_url=aliyun_base,
        model=settings.aliyun_voice_model or "qwen-tts",
        label="阿里云百炼 Qwen-TTS",
        cost_estimate="中文 TTS/克隆候选，按实际模型账单为准",
    )
    yield ProviderSpec(
        "aliyun_bailian_minimax",
        CloudProviderType.voice,
        api_key_env_name="DASHSCOPE_API_KEY",
        base_url=aliyun_base,
        model=settings.aliyun_voice_model or "minimax-voice",
        label="阿里云百炼 MiniMax",
        cost_estimate="中文声音克隆候选，适合试不同音色",
    )
    yield ProviderSpec(
        "hifly_voice_clone",
        CloudProviderType.voice,
        api_key_env_name="HIFLY_TOKEN",
        base_url=settings.hifly_base_url or "https://hfw-api.hifly.cc",
        model="hifly-voice-clone",
        label="飞影声音克隆",
        cost_estimate="使用飞影 API 从源视频声音样本克隆音色，适合飞影一体化数字人路线。",
    )
    yield ProviderSpec(
        "elevenlabs",
        CloudProviderType.voice,
        api_key_env_name="ELEVENLABS_API_KEY",
        base_url="https://api.elevenlabs.io",
        model="eleven_multilingual_v2",
        label="ElevenLabs",
        cost_estimate="国际化声音效果好，成本通常高于国内方案",
    )
    yield ProviderSpec(
        "azure_tts_no_clone",
        CloudProviderType.voice,
        api_key_env_name="AZURE_SPEECH_KEY",
        base_url=settings.azure_speech_endpoint or "",
        model="azure-neural-tts",
        label="Azure TTS",
        cost_estimate="稳定 TTS，不作为首选声音克隆",
        no_clone=True,
    )
    yield ProviderSpec(
        "edge_tts_no_clone",
        CloudProviderType.voice,
        api_key_env_name="",
        base_url="",
        model="edge-tts",
        label="Edge TTS",
        cost_estimate="免费试用，非正式声音克隆",
        no_clone=True,
    )
    yield ProviderSpec(
        "custom_http_tts",
        CloudProviderType.voice,
        api_key_env_name="CUSTOM_HTTP_TTS_API_KEY",
        base_url=settings.custom_http_tts_base_url or "",
        model="custom-http",
        label="自定义 HTTP TTS",
        cost_estimate="费用由自建或第三方服务决定",
    )
    yield ProviderSpec(
        "fal_latentsync",
        CloudProviderType.video,
        api_key_env_name="FAL_API_KEY",
        base_url=fal_base,
        model=settings.fal_latentsync_model or "fal-ai/latentsync",
        label="fal.ai LatentSync",
        cost_estimate="$0.005/秒，60 秒约 $0.30，适合最终质量",
    )
    yield ProviderSpec(
        "fal_musetalk",
        CloudProviderType.video,
        api_key_env_name="FAL_API_KEY",
        base_url=fal_base,
        model=settings.fal_musetalk_model or "fal-ai/musetalk",
        label="fal.ai MuseTalk",
        cost_estimate="$0.003/秒，适合低成本预览",
    )
    yield ProviderSpec(
        "pixverse_lipsync",
        CloudProviderType.video,
        api_key_env_name="PIXVERSE_API_KEY",
        base_url=settings.pixverse_base_url or "https://superaiapi.top",
        model=settings.pixverse_model or "pixverse-lipsync:stable",
        label="PixVerse Lipsync",
        cost_estimate="按 PixVerse/SuperAIAPI 账号用量计费，适合云端口型同步。",
    )
    yield ProviderSpec(
        "did_optional",
        CloudProviderType.video,
        api_key_env_name="DID_API_KEY",
        base_url="https://api.d-id.com",
        model="did-talks",
        label="D-ID 可选",
        cost_estimate="一站式方案，成本通常较高",
        optional=True,
    )
    yield ProviderSpec(
        "heygen_optional",
        CloudProviderType.video,
        api_key_env_name="HEYGEN_API_KEY",
        base_url="https://api.heygen.com",
        model="heygen-video",
        label="HeyGen 可选",
        cost_estimate="一站式方案，成本通常较高",
        optional=True,
    )
    yield ProviderSpec(
        "self_hosted_lipsync",
        CloudProviderType.video,
        api_key_env_name="SELF_HOSTED_LIPSYNC_API_KEY",
        base_url=settings.self_hosted_lipsync_base_url or "",
        model="self-hosted",
        label="自建口型同步服务",
        cost_estimate="长期最低成本，取决于你的 GPU/服务器",
    )
    yield ProviderSpec(
        "baidu_xiling",
        CloudProviderType.video,
        api_key_env_name="BAIDU_XILING_APP_KEY",
        base_url=settings.baidu_xiling_base_url or "https://open.xiling.baidu.com",
        model=settings.baidu_xiling_figure_id or "figure-required",
        label="百度曦灵数字人",
        cost_estimate="按百度智能云/曦灵实际账单计费，需开通应用并配置 AppID、AppKey、figureId。",
    )
    yield ProviderSpec(
        "hifly",
        CloudProviderType.video,
        api_key_env_name="HIFLY_TOKEN",
        base_url=settings.hifly_base_url or "https://hfw-api.hifly.cc",
        model="hifly-api-v2",
        label="飞影 API 数字人",
        cost_estimate="上传一个源视频即可创建形象、克隆声音并生成数字人视频，按飞影 API 额度计费。",
    )


def _to_config(spec: ProviderSpec, settings: Settings, selected_provider: str) -> CloudProviderConfig:
    enabled = spec.provider_id == selected_provider
    required = bool(enabled and not settings.dry_run and not spec.optional)
    missing: list[str] = []
    api_key = _api_key_value(settings, spec.api_key_env_name)
    if enabled and spec.api_key_env_name and not api_key and spec.provider_id != "self_hosted_lipsync":
        missing.append(spec.api_key_env_name)
    if enabled and spec.provider_id == "custom_http_tts" and not spec.base_url:
        missing.append("CUSTOM_HTTP_TTS_BASE_URL")
    if enabled and spec.provider_id == "self_hosted_lipsync" and not spec.base_url:
        missing.append("SELF_HOSTED_LIPSYNC_BASE_URL")
    if enabled and spec.provider_id == "azure_tts_no_clone" and not spec.base_url:
        missing.append("AZURE_SPEECH_ENDPOINT")
    if enabled and spec.provider_id == "baidu_xiling":
        if not settings.baidu_xiling_app_id:
            missing.append("BAIDU_XILING_APP_ID")
        if not settings.baidu_xiling_figure_id:
            missing.append("BAIDU_XILING_FIGURE_ID")
        if not spec.base_url:
            missing.append("BAIDU_XILING_BASE_URL")

    if not enabled:
        status = "disabled"
        message = "未选择"
    elif missing and required:
        status = "red"
        message = "缺少真实模式必需配置：" + "、".join(missing)
    elif missing:
        status = "yellow"
        message = "试用模式可继续运行；真实调用前需要配置：" + "、".join(missing)
    elif spec.no_clone:
        status = "green"
        message = "可用于 TTS，但不是正式声音克隆方案。"
    else:
        status = "green"
        message = "已选择，关键配置已填写。"

    return CloudProviderConfig(
        provider_id=spec.provider_id,
        provider_type=spec.provider_type,
        api_key_env_name=spec.api_key_env_name,
        base_url=spec.base_url,
        model=spec.model,
        enabled=enabled,
        required=required,
        cost_estimate=spec.cost_estimate,
        status=status,
        missing_items=missing,
        message=message,
    )


def _api_key_value(settings: Settings, env_name: str) -> str:
    if not env_name:
        return ""
    field_name = env_name.lower()
    value = getattr(settings, field_name, None)
    return str(value or os.getenv(env_name) or "").strip()


def _provider_id(value: str | None) -> str:
    return str(value or "").strip().lower()


def _money(value: float) -> float:
    return round(float(value) + 1e-9, 2)
