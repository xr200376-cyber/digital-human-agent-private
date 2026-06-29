from __future__ import annotations

from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import httpx
from pydantic import BaseModel, Field

from app.utils.files import ensure_dir, read_json, write_json


LocalModelType = Literal["local_path", "ollama_or_local_service", "other"]


class LLMPlatformModel(BaseModel):
    id: str
    name: str = ""
    group: str = "Custom"
    enabled: bool = True


class LLMPlatformConfig(BaseModel):
    id: str
    name: str
    baseUrl: str = ""
    apiKey: str = ""
    enabled: bool = False
    models: list[LLMPlatformModel] = Field(default_factory=list)
    docsUrl: str = ""
    icon: str = ""


class LocalLLMModel(BaseModel):
    id: str = ""
    name: str
    path: str
    type: LocalModelType = "local_path"
    notes: str = ""
    enabled: bool = True


class LLMPlatformConfigDocument(BaseModel):
    activePlatformId: str = ""
    activeModelId: str = ""
    platforms: list[LLMPlatformConfig] = Field(default_factory=list)
    localModels: list[LocalLLMModel] = Field(default_factory=list)


def default_platforms() -> list[LLMPlatformConfig]:
    return [
        LLMPlatformConfig(
            id="openai",
            name="OpenAI",
            baseUrl="https://api.openai.com/v1",
            docsUrl="https://platform.openai.com/docs",
            icon="/provider-icons/openai.png",
            models=[
                LLMPlatformModel(id="gpt-4o-mini", name="GPT-4o mini", group="GPT-4o"),
                LLMPlatformModel(id="gpt-4o", name="GPT-4o", group="GPT-4o"),
            ],
        ),
        LLMPlatformConfig(
            id="o3",
            name="OpenAI O3",
            baseUrl="https://api.openai.com/v1",
            docsUrl="https://platform.openai.com/docs",
            icon="/provider-icons/openai.png",
            models=[
                LLMPlatformModel(id="o3", name="O3", group="Reasoning"),
            ],
        ),
        LLMPlatformConfig(
            id="ppio",
            name="PPIO",
            baseUrl="https://api.ppinfra.com/v3/openai",
            docsUrl="https://ppinfra.com",
            icon="/provider-icons/ppio.ico",
        ),
        LLMPlatformConfig(
            id="gemini",
            name="Gemini",
            baseUrl="https://generativelanguage.googleapis.com/v1beta/openai",
            docsUrl="https://ai.google.dev/gemini-api/docs/openai",
            icon="/provider-icons/gemini.svg",
            models=[
                LLMPlatformModel(id="gemini-1.5-flash", name="Gemini 1.5 Flash", group="Gemini 1.5"),
                LLMPlatformModel(id="gemini-1.5-pro", name="Gemini 1.5 Pro", group="Gemini 1.5"),
                LLMPlatformModel(id="gemini-2.0-flash", name="Gemini 2.0 Flash", group="Gemini 2.0"),
            ],
        ),
        LLMPlatformConfig(
            id="siliconflow",
            name="SiliconFlow",
            baseUrl="https://api.siliconflow.cn/v1",
            docsUrl="https://docs.siliconflow.cn",
            icon="/provider-icons/siliconflow.ico",
        ),
        LLMPlatformConfig(
            id="gitee_ai",
            name="Gitee AI",
            baseUrl="https://ai.gitee.com/v1",
            docsUrl="https://ai.gitee.com",
            icon="/provider-icons/gitee.ico",
        ),
        LLMPlatformConfig(
            id="github_models",
            name="GitHub Models",
            baseUrl="https://models.inference.ai.azure.com",
            docsUrl="https://docs.github.com/github-models",
            icon="/provider-icons/github.ico",
        ),
        LLMPlatformConfig(
            id="baidu_qianfan",
            name="百度千帆",
            baseUrl="https://qianfan.baidubce.com/v2",
            docsUrl="https://cloud.baidu.com/doc/WENXINWORKSHOP/index.html",
            icon="/provider-icons/baidu.ico",
            models=[
                LLMPlatformModel(id="ernie-4.0-turbo-8k", name="ERNIE 4.0 Turbo", group="ERNIE"),
                LLMPlatformModel(id="ernie-3.5-8k", name="ERNIE 3.5", group="ERNIE"),
            ],
        ),
        LLMPlatformConfig(
            id="doubao_ark",
            name="豆包/火山方舟",
            baseUrl="https://ark.cn-beijing.volces.com/api/v3",
            docsUrl="https://www.volcengine.com/docs/82379",
            icon="/provider-icons/volcengine.png",
            models=[
                LLMPlatformModel(id="doubao-seed-1-6-250615", name="Doubao Seed 1.6", group="Doubao"),
                LLMPlatformModel(id="doubao-1-5-pro-32k-250115", name="Doubao 1.5 Pro 32K", group="Doubao"),
            ],
        ),
        LLMPlatformConfig(
            id="aliyun_bailian",
            name="阿里百炼",
            baseUrl="https://dashscope.aliyuncs.com/compatible-mode/v1",
            docsUrl="https://help.aliyun.com/zh/model-studio/",
            icon="/provider-icons/aliyun.ico",
            models=[
                LLMPlatformModel(id="qwen-plus", name="Qwen Plus", group="Qwen"),
                LLMPlatformModel(id="qwen-turbo", name="Qwen Turbo", group="Qwen"),
                LLMPlatformModel(id="qwen-max", name="Qwen Max", group="Qwen"),
            ],
        ),
        LLMPlatformConfig(
            id="tencent_hunyuan",
            name="腾讯混元",
            baseUrl="https://api.hunyuan.cloud.tencent.com/v1",
            docsUrl="https://cloud.tencent.com/document/product/1729",
            icon="/provider-icons/tencent.ico",
            models=[
                LLMPlatformModel(id="hunyuan-turbos-latest", name="Hunyuan TurboS", group="Hunyuan"),
                LLMPlatformModel(id="hunyuan-lite", name="Hunyuan Lite", group="Hunyuan"),
            ],
        ),
        LLMPlatformConfig(
            id="zhipu_glm",
            name="智谱 GLM",
            baseUrl="https://open.bigmodel.cn/api/paas/v4",
            docsUrl="https://docs.bigmodel.cn",
            icon="/provider-icons/zhipu.png",
            models=[
                LLMPlatformModel(id="glm-4.5", name="GLM-4.5", group="GLM"),
                LLMPlatformModel(id="glm-4.5-air", name="GLM-4.5 Air", group="GLM"),
            ],
        ),
        LLMPlatformConfig(
            id="moonshot_kimi",
            name="Moonshot Kimi",
            baseUrl="https://api.moonshot.cn/v1",
            docsUrl="https://platform.moonshot.cn/docs",
            icon="/provider-icons/moonshot.ico",
            models=[
                LLMPlatformModel(id="moonshot-v1-8k", name="Moonshot v1 8K", group="Moonshot"),
                LLMPlatformModel(id="moonshot-v1-32k", name="Moonshot v1 32K", group="Moonshot"),
                LLMPlatformModel(id="moonshot-v1-128k", name="Moonshot v1 128K", group="Moonshot"),
            ],
        ),
        LLMPlatformConfig(
            id="deepseek",
            name="DeepSeek",
            baseUrl="https://api.deepseek.com",
            docsUrl="https://api-docs.deepseek.com",
            icon="/provider-icons/deepseek.ico",
            models=[
                LLMPlatformModel(id="deepseek-chat", name="DeepSeek Chat", group="DeepSeek"),
                LLMPlatformModel(id="deepseek-reasoner", name="DeepSeek Reasoner", group="DeepSeek"),
            ],
        ),
        LLMPlatformConfig(
            id="newapi_gateway",
            name="NewAPI / 自部署模型网关",
            baseUrl="http://127.0.0.1:3000/v1",
            docsUrl="https://github.com/QuantumNous/new-api",
            icon="/provider-icons/custom.svg",
            models=[
                LLMPlatformModel(id="deepseek-chat", name="DeepSeek Chat", group="DeepSeek"),
                LLMPlatformModel(id="qwen-plus", name="Qwen Plus", group="Qwen"),
                LLMPlatformModel(id="gpt-4o-mini", name="GPT-4o mini", group="OpenAI"),
            ],
        ),
        LLMPlatformConfig(
            id="custom",
            name="Custom",
            icon="/provider-icons/custom.svg",
        ),
    ]


def _preview_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}...{value[-4:]}"


def _normalize_base_url(value: str) -> str:
    return value.strip().rstrip("/")


class LLMPlatformStore:
    def __init__(self, storage_dir: Path):
        self.storage_dir = Path(storage_dir)
        self.path = self.storage_dir / "desktop" / "llm_platforms.json"

    def default(self) -> LLMPlatformConfigDocument:
        platforms = default_platforms()
        active_platform = platforms[0] if platforms else None
        active_model = active_platform.models[0] if active_platform and active_platform.models else None
        return LLMPlatformConfigDocument(
            activePlatformId=active_platform.id if active_platform else "",
            activeModelId=active_model.id if active_model else "",
            platforms=platforms,
            localModels=[],
        )

    def load(self) -> LLMPlatformConfigDocument:
        if not self.path.exists():
            return self.default()
        document = LLMPlatformConfigDocument.model_validate(read_json(self.path))
        return self._merge_presets(document)

    def save(self, document: LLMPlatformConfigDocument) -> LLMPlatformConfigDocument:
        normalized = self._normalize_enabled_models(
            self._normalize_enabled_platforms(self._normalize_active_selection(self._merge_presets(document)))
        )
        ensure_dir(self.path.parent)
        write_json(self.path, normalized.model_dump(mode="json"))
        return normalized

    def save_preserving_secrets(self, document: LLMPlatformConfigDocument) -> LLMPlatformConfigDocument:
        existing_keys = {platform.id: platform.apiKey for platform in self.load().platforms}
        platforms = []
        for platform in document.platforms:
            api_key = platform.apiKey
            if api_key == "" and existing_keys.get(platform.id):
                api_key = existing_keys[platform.id]
            platforms.append(platform.model_copy(update={"apiKey": api_key}))
        return self.save(document.model_copy(update={"platforms": platforms}))

    def safe_document(self) -> dict:
        document = self.load()
        return {
            "activePlatformId": document.activePlatformId,
            "activeModelId": document.activeModelId,
            "platforms": [self._safe_platform(platform) for platform in document.platforms],
            "localModels": [model.model_dump(mode="json") for model in document.localModels],
        }

    def set_selection(self, platform_id: str, model_id: str) -> LLMPlatformConfigDocument:
        document = self.load()
        platform = next((platform for platform in document.platforms if platform.id == platform_id), None)
        if platform is None:
            raise ValueError(f"Unknown LLM platform: {platform_id}")
        if not model_id:
            raise ValueError("Model id is required")
        model = next((model for model in platform.models if model.id == model_id), None)
        if model is None:
            raise ValueError(f"Unknown LLM model: {model_id}")
        return self.save(document.model_copy(update={"activePlatformId": platform_id, "activeModelId": model_id}))

    def create_local_model(self, model: LocalLLMModel) -> LocalLLMModel:
        document = self.load()
        created = model
        if created.id and any(existing.id == created.id for existing in document.localModels):
            raise ValueError(f"Duplicate local LLM model id: {created.id}")
        if not created.id:
            created = created.model_copy(update={"id": f"local-{uuid4().hex[:8]}"})
        self.save(document.model_copy(update={"localModels": [*document.localModels, created]}))
        return created

    def update_local_model(self, model_id: str, model: LocalLLMModel) -> LocalLLMModel:
        document = self.load()
        updated = model.model_copy(update={"id": model_id})
        local_models = []
        found = False
        for existing in document.localModels:
            if existing.id == model_id:
                local_models.append(updated)
                found = True
            else:
                local_models.append(existing)
        if not found:
            raise ValueError(f"Unknown local LLM model: {model_id}")
        self.save(document.model_copy(update={"localModels": local_models}))
        return updated

    def delete_local_model(self, model_id: str) -> LLMPlatformConfigDocument:
        document = self.load()
        local_models = [model for model in document.localModels if model.id != model_id]
        if len(local_models) == len(document.localModels):
            raise ValueError(f"Unknown local LLM model: {model_id}")
        return self.save(document.model_copy(update={"localModels": local_models}))

    def active_openai_config(self) -> dict:
        document = self.load()
        platform = next((item for item in document.platforms if item.id == document.activePlatformId), None)
        model = None
        if platform:
            model = next((item for item in platform.models if item.id == document.activeModelId), None)

        missing_items = []
        base_url = _normalize_base_url(platform.baseUrl) if platform else ""
        api_key = platform.apiKey if platform else ""

        if platform is None:
            missing_items.append("platform")
        else:
            if not platform.enabled:
                missing_items.append("platform_enabled")
            if not base_url:
                missing_items.append("base_url")
            if not api_key:
                missing_items.append("api_key")
            if model is None:
                missing_items.append("model")
            elif not model.enabled:
                missing_items.append("model_enabled")

        return {
            "enabled": not missing_items,
            "base_url": base_url,
            "api_key": api_key,
            "model": document.activeModelId,
            "platform_id": document.activePlatformId,
            "missing_items": missing_items,
        }

    def _platform_or_error(self, platform_id: str) -> LLMPlatformConfig:
        document = self.load()
        platform = next((item for item in document.platforms if item.id == platform_id), None)
        if platform is None:
            raise ValueError(f"unknown platform: {platform_id}")
        return platform

    def check_platform(self, platform_id: str, *, client: httpx.Client | None = None) -> dict[str, Any]:
        platform = self._platform_or_error(platform_id)
        missing_items = self._missing_api_settings(platform)
        if missing_items:
            return {
                "status": "red",
                "platformId": platform.id,
                "missing_items": missing_items,
                "message": "Missing required API settings.",
            }

        url = f"{_normalize_base_url(platform.baseUrl)}/models"
        headers = {"Authorization": f"Bearer {platform.apiKey.strip()}"}
        try:
            if client is not None:
                response = client.get(url, headers=headers)
            else:
                with httpx.Client(timeout=10) as local_client:
                    response = local_client.get(url, headers=headers)
        except (httpx.InvalidURL, httpx.HTTPError) as exc:
            return {
                "status": "red",
                "platformId": platform.id,
                "message": f"Platform check failed: {exc}",
            }

        if response.status_code >= 400:
            return {
                "status": "red",
                "platformId": platform.id,
                "message": f"Platform check failed: HTTP {response.status_code}",
            }
        return {
            "status": "green",
            "platformId": platform.id,
            "message": "Platform is reachable.",
        }

    def refresh_models(self, platform_id: str, *, client: httpx.Client | None = None) -> dict[str, Any]:
        document = self.load()
        platform = next((item for item in document.platforms if item.id == platform_id), None)
        if platform is None:
            raise ValueError(f"unknown platform: {platform_id}")

        missing_items = self._missing_api_settings(platform)
        if missing_items:
            return {
                "status": "red",
                "platformId": platform.id,
                "missing_items": missing_items,
                "models": [model.model_dump(mode="json") for model in platform.models],
                "message": "Missing required API settings.",
            }

        url = f"{_normalize_base_url(platform.baseUrl)}/models"
        headers = {"Authorization": f"Bearer {platform.apiKey.strip()}"}
        try:
            if client is not None:
                response = client.get(url, headers=headers)
            else:
                with httpx.Client(timeout=10) as local_client:
                    response = local_client.get(url, headers=headers)
            if response.status_code >= 400:
                return {
                    "status": "red",
                    "platformId": platform.id,
                    "models": [model.model_dump(mode="json") for model in platform.models],
                    "message": f"Model refresh failed: HTTP {response.status_code}",
                }
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("model response is not a JSON object")
            if "data" not in payload:
                raise ValueError("model response missing data")
            data = payload["data"]
            if not isinstance(data, list):
                raise ValueError("model response data is not a list")
        except (httpx.InvalidURL, httpx.HTTPError, ValueError) as exc:
            return {
                "status": "red",
                "platformId": platform.id,
                "models": [model.model_dump(mode="json") for model in platform.models],
                "message": f"Model refresh failed: {exc}",
            }

        existing_ids = {model.id for model in platform.models}
        remote_models = []
        for item in data:
            if not isinstance(item, dict):
                continue
            model_id = item.get("id")
            if not model_id or model_id in existing_ids:
                continue
            remote_models.append(LLMPlatformModel(id=str(model_id), name=str(model_id), group="Remote", enabled=True))
            existing_ids.add(model_id)

        updated_platform = platform.model_copy(update={"models": [*platform.models, *remote_models]})
        updated_platforms = [updated_platform if item.id == platform.id else item for item in document.platforms]
        saved = self.save(document.model_copy(update={"platforms": updated_platforms}))
        updated = next(item for item in saved.platforms if item.id == platform.id)
        return {
            "status": "green",
            "platformId": platform.id,
            "models": [model.model_dump(mode="json") for model in updated.models],
            "message": f"Refreshed {len(remote_models)} remote models.",
        }

    def _merge_presets(self, document: LLMPlatformConfigDocument) -> LLMPlatformConfigDocument:
        saved_by_id = {platform.id: platform for platform in document.platforms}
        merged_platforms = []

        for preset in default_platforms():
            saved = saved_by_id.get(preset.id)
            if saved is None:
                merged_platforms.append(preset)
                continue

            saved_model_ids = {model.id for model in saved.models}
            missing_preset_models = [model for model in preset.models if model.id not in saved_model_ids]
            icon = saved.icon or preset.icon
            if preset.id != "custom" and preset.icon:
                icon = preset.icon
            name = saved.name or preset.name
            if preset.id != "custom":
                name = preset.name
            merged_platforms.append(
                preset.model_copy(
                    update={
                        "name": name,
                        "baseUrl": saved.baseUrl,
                        "apiKey": saved.apiKey,
                        "enabled": saved.enabled,
                        "docsUrl": saved.docsUrl or preset.docsUrl,
                        "icon": icon,
                        "models": [*saved.models, *missing_preset_models],
                    }
                )
            )

        preset_ids = {platform.id for platform in merged_platforms}
        merged_platforms.extend(platform for platform in document.platforms if platform.id not in preset_ids)
        return document.model_copy(update={"platforms": merged_platforms})

    def _normalize_active_selection(self, document: LLMPlatformConfigDocument) -> LLMPlatformConfigDocument:
        platform = next((item for item in document.platforms if item.id == document.activePlatformId), None)
        if platform is None:
            return document.model_copy(update={"activeModelId": ""})
        active_model = next(
            (model for model in platform.models if model.id == document.activeModelId),
            None,
        )
        if active_model is not None:
            return document
        fallback = next((model for model in platform.models if model.enabled), None)
        if fallback is None and platform.models:
            fallback = platform.models[0]
        return document.model_copy(update={"activeModelId": fallback.id if fallback else ""})

    def _normalize_enabled_platforms(self, document: LLMPlatformConfigDocument) -> LLMPlatformConfigDocument:
        active_platform_id = document.activePlatformId
        if active_platform_id and not any(platform.id == active_platform_id for platform in document.platforms):
            active_platform_id = ""
        if not active_platform_id:
            enabled_platform = next((platform for platform in document.platforms if platform.enabled), None)
            active_platform_id = enabled_platform.id if enabled_platform else ""
        platforms = [
            platform.model_copy(update={"enabled": bool(active_platform_id and platform.id == active_platform_id)})
            for platform in document.platforms
        ]
        return document.model_copy(update={"activePlatformId": active_platform_id, "platforms": platforms})

    def _normalize_enabled_models(self, document: LLMPlatformConfigDocument) -> LLMPlatformConfigDocument:
        platforms = []
        for platform in document.platforms:
            models = [
                model.model_copy(
                    update={"enabled": bool(platform.id == document.activePlatformId and model.id == document.activeModelId)}
                )
                for model in platform.models
            ]
            platforms.append(platform.model_copy(update={"models": models}))
        return document.model_copy(update={"platforms": platforms})

    def _safe_platform(self, platform: LLMPlatformConfig) -> dict:
        data = platform.model_dump(mode="json", exclude={"apiKey"})
        data["hasApiKey"] = bool(platform.apiKey)
        data["apiKeyPreview"] = _preview_secret(platform.apiKey)
        return data

    def _missing_api_settings(self, platform: LLMPlatformConfig) -> list[str]:
        missing_items = []
        if not _normalize_base_url(platform.baseUrl):
            missing_items.append("baseUrl")
        if not platform.apiKey.strip():
            missing_items.append("apiKey")
        return missing_items
