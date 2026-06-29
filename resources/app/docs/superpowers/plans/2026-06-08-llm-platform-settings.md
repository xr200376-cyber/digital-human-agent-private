# LLM Platform Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the approved large model settings feature: OpenAI-compatible cloud platform configuration, local model registration, default model selection, downstream LLM wiring, and verification.

**Architecture:** Add a focused `app/llm_platforms.py` module for presets, persistence, safe secret serialization, platform checks, model refresh, and active model lookup. Expose it through FastAPI routes in `app/main.py`, wire selected cloud settings into `app/settings.py`, implement real OpenAI-compatible calls in `app/adapters/llm.py`, and add vanilla HTML/CSS/JS modal UI to `static/studio.*`.

**Tech Stack:** Python 3.11, FastAPI, Pydantic, httpx, pytest, vanilla HTML/CSS/JavaScript.

---

## File Structure

- Create `app/llm_platforms.py`
  - Owns Pydantic data models, built-in platform presets, local file persistence, safe API key serialization, model refresh, platform checks, local model CRUD, and active OpenAI-compatible config extraction.
- Modify `app/settings.py`
  - Reads `storage/desktop/llm_platforms.json` during desktop override application and maps the active enabled cloud platform/model into existing `openai_compatible_*` settings.
- Modify `app/adapters/llm.py`
  - Implements real OpenAI-compatible `/chat/completions` calls and rewrites scripts into the existing output files.
- Modify `app/main.py`
  - Adds `/llm/platforms`, `/llm/selection`, and `/llm/local-models` API routes.
  - Clears cached settings after LLM platform changes so downstream workflows see the active model.
- Modify `static/studio.html`
  - Adds `大模型设置` and `添加本地模型` buttons to the model center header.
  - Adds the large model modal and local model modal markup.
- Modify `static/studio.css`
  - Adds modal, platform sidebar, model row, switch, and responsive rules.
- Modify `static/studio.js`
  - Adds modal state, API calls, platform search, platform selection, safe key handling, model CRUD, selection, local model CRUD, and event bindings.
- Create `G:/tests/test_llm_platforms.py`
  - Covers store defaults, secret handling, selection, local models, platform check, model refresh, settings override, and adapter HTTP behavior.
- Modify or add frontend assertions in `G:/tests/test_model_center.py`
  - Confirms static UI exposes the new buttons, modal IDs, and JS endpoint calls.

Because `G:/app` is not a git repository in the current workspace, commit steps are written as conditional checks. If `git rev-parse --is-inside-work-tree` fails, record the failure in the handoff and continue without committing.

---

### Task 1: LLM Platform Store Tests And Core Module

**Files:**
- Create: `G:/tests/test_llm_platforms.py`
- Create: `G:/app/llm_platforms.py`

- [ ] **Step 1: Write failing store and secret tests**

Create `G:/tests/test_llm_platforms.py` with these initial tests:

```python
from pathlib import Path

from app.llm_platforms import (
    LLMPlatformConfig,
    LLMPlatformConfigDocument,
    LLMPlatformModel,
    LLMPlatformStore,
    LocalLLMModel,
)


def test_default_document_contains_presets_and_no_plaintext_keys(tmp_path: Path):
    store = LLMPlatformStore(tmp_path)

    safe = store.safe_document()

    platform_ids = {item["id"] for item in safe["platforms"]}
    assert {"openai", "o3", "gemini", "siliconflow", "github_models", "gitee_ai", "ppio", "custom"}.issubset(platform_ids)
    openai = next(item for item in safe["platforms"] if item["id"] == "openai")
    assert openai["baseUrl"] == "https://api.openai.com/v1"
    assert openai["hasApiKey"] is False
    assert "apiKey" not in openai


def test_save_preserves_existing_api_key_when_empty_key_is_submitted(tmp_path: Path):
    store = LLMPlatformStore(tmp_path)
    first = LLMPlatformConfigDocument(
        activePlatformId="openai",
        activeModelId="gpt-4o-mini",
        platforms=[
            LLMPlatformConfig(
                id="openai",
                name="OpenAI",
                baseUrl="https://api.openai.com/v1",
                apiKey="secret-one",
                enabled=True,
                models=[LLMPlatformModel(id="gpt-4o-mini", name="GPT-4o mini", group="GPT-4o", enabled=True)],
            )
        ],
        localModels=[],
    )
    store.save(first)

    replacement = first.model_copy(
        deep=True,
        update={
            "platforms": [
                first.platforms[0].model_copy(update={"apiKey": ""}),
            ]
        },
    )
    saved = store.save_preserving_secrets(replacement)

    assert saved.platforms[0].apiKey == "secret-one"
    safe = store.safe_document()
    openai = next(item for item in safe["platforms"] if item["id"] == "openai")
    assert openai["hasApiKey"] is True
    assert openai["apiKeyPreview"] == "secr...-one"
    assert "secret-one" not in str(safe)


def test_selection_and_local_model_crud_round_trip(tmp_path: Path):
    store = LLMPlatformStore(tmp_path)

    selected = store.set_selection("gemini", "gemini-2.0-flash")
    assert selected.activePlatformId == "gemini"
    assert selected.activeModelId == "gemini-2.0-flash"

    created = store.create_local_model(
        LocalLLMModel(
            id="",
            name="Local Ollama",
            path="http://127.0.0.1:11434/v1",
            type="ollama_or_local_service",
            notes="Local OpenAI-compatible service",
            enabled=True,
        )
    )
    assert created.id.startswith("local-")
    assert store.load().localModels[0].name == "Local Ollama"

    updated = store.update_local_model(created.id, created.model_copy(update={"name": "Local Ollama Updated"}))
    assert updated.name == "Local Ollama Updated"

    store.delete_local_model(created.id)
    assert store.load().localModels == []


def test_active_openai_config_requires_enabled_platform_model_key_and_base_url(tmp_path: Path):
    store = LLMPlatformStore(tmp_path)
    doc = LLMPlatformConfigDocument(
        activePlatformId="openai",
        activeModelId="gpt-4o-mini",
        platforms=[
            LLMPlatformConfig(
                id="openai",
                name="OpenAI",
                baseUrl="https://api.openai.com/v1/",
                apiKey="secret-one",
                enabled=True,
                models=[LLMPlatformModel(id="gpt-4o-mini", name="GPT-4o mini", group="GPT-4o", enabled=True)],
            )
        ],
        localModels=[],
    )
    store.save(doc)

    config = store.active_openai_config()

    assert config == {
        "enabled": True,
        "base_url": "https://api.openai.com/v1",
        "api_key": "secret-one",
        "model": "gpt-4o-mini",
        "platform_id": "openai",
        "missing_items": [],
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
pytest G:\tests\test_llm_platforms.py -q
```

Expected: fails with `ModuleNotFoundError: No module named 'app.llm_platforms'`.

- [ ] **Step 3: Implement `app/llm_platforms.py` core storage**

Create `G:/app/llm_platforms.py` with the following structure:

```python
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
            docsUrl="https://platform.openai.com/docs/api-reference",
            models=[
                LLMPlatformModel(id="gpt-4o-mini", name="GPT-4o mini", group="GPT-4o"),
                LLMPlatformModel(id="gpt-4o", name="GPT-4o", group="GPT-4o"),
            ],
        ),
        LLMPlatformConfig(id="o3", name="O3", baseUrl="https://api.openai.com/v1", models=[LLMPlatformModel(id="o3", name="O3", group="Reasoning")]),
        LLMPlatformConfig(id="ppio", name="PPIO 派欧云", baseUrl="https://api.ppinfra.com/v3/openai", models=[]),
        LLMPlatformConfig(
            id="gemini",
            name="Gemini",
            baseUrl="https://generativelanguage.googleapis.com/v1beta/openai",
            docsUrl="https://ai.google.dev/gemini-api/docs/openai",
            models=[
                LLMPlatformModel(id="gemini-1.5-flash", name="Gemini 1.5 Flash", group="Gemini 1.5"),
                LLMPlatformModel(id="gemini-1.5-pro", name="Gemini 1.5 Pro", group="Gemini 1.5"),
                LLMPlatformModel(id="gemini-2.0-flash", name="Gemini 2.0 Flash", group="Gemini 2.0"),
            ],
        ),
        LLMPlatformConfig(id="siliconflow", name="硅基流动", baseUrl="https://api.siliconflow.cn/v1", models=[]),
        LLMPlatformConfig(id="gitee_ai", name="Gitee AI", baseUrl="https://ai.gitee.com/v1", models=[]),
        LLMPlatformConfig(id="github_models", name="GitHub Models", baseUrl="https://models.inference.ai.azure.com", models=[]),
        LLMPlatformConfig(id="custom", name="自定义平台", baseUrl="", models=[]),
    ]


def _preview_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}...{value[-4:]}"


def _normalize_base_url(value: str) -> str:
    return (value or "").strip().rstrip("/")


class LLMPlatformStore:
    def __init__(self, storage_dir: Path):
        self.storage_dir = Path(storage_dir)
        self.path = self.storage_dir / "desktop" / "llm_platforms.json"

    def default(self) -> LLMPlatformConfigDocument:
        platforms = default_platforms()
        return LLMPlatformConfigDocument(
            activePlatformId=platforms[0].id if platforms else "",
            activeModelId=platforms[0].models[0].id if platforms and platforms[0].models else "",
            platforms=platforms,
            localModels=[],
        )

    def load(self) -> LLMPlatformConfigDocument:
        if not self.path.exists():
            return self.default()
        return self._merge_presets(LLMPlatformConfigDocument.model_validate(read_json(self.path)))

    def save(self, document: LLMPlatformConfigDocument) -> LLMPlatformConfigDocument:
        normalized = self._merge_presets(document)
        ensure_dir(self.path.parent)
        write_json(self.path, normalized.model_dump(mode="json"))
        return normalized

    def save_preserving_secrets(self, document: LLMPlatformConfigDocument) -> LLMPlatformConfigDocument:
        current_by_id = {item.id: item for item in self.load().platforms}
        platforms: list[LLMPlatformConfig] = []
        for platform in document.platforms:
            current = current_by_id.get(platform.id)
            if current and not platform.apiKey:
                platforms.append(platform.model_copy(update={"apiKey": current.apiKey}))
            else:
                platforms.append(platform)
        return self.save(document.model_copy(update={"platforms": platforms}))

    def safe_document(self) -> dict[str, Any]:
        document = self.load()
        return {
            "activePlatformId": document.activePlatformId,
            "activeModelId": document.activeModelId,
            "platforms": [self._safe_platform(item) for item in document.platforms],
            "localModels": [item.model_dump(mode="json") for item in document.localModels],
        }

    def set_selection(self, platform_id: str, model_id: str) -> LLMPlatformConfigDocument:
        document = self.load()
        if platform_id not in {item.id for item in document.platforms}:
            raise ValueError(f"unknown platform: {platform_id}")
        if not model_id:
            raise ValueError("active model id is required")
        return self.save(document.model_copy(update={"activePlatformId": platform_id, "activeModelId": model_id}))

    def create_local_model(self, model: LocalLLMModel) -> LocalLLMModel:
        document = self.load()
        created = model.model_copy(update={"id": model.id or f"local-{uuid4().hex[:12]}"})
        document.localModels.append(created)
        self.save(document)
        return created

    def update_local_model(self, model_id: str, model: LocalLLMModel) -> LocalLLMModel:
        document = self.load()
        for index, existing in enumerate(document.localModels):
            if existing.id == model_id:
                updated = model.model_copy(update={"id": model_id})
                document.localModels[index] = updated
                self.save(document)
                return updated
        raise ValueError(f"unknown local model: {model_id}")

    def delete_local_model(self, model_id: str) -> LLMPlatformConfigDocument:
        document = self.load()
        before = len(document.localModels)
        document.localModels = [item for item in document.localModels if item.id != model_id]
        if len(document.localModels) == before:
            raise ValueError(f"unknown local model: {model_id}")
        return self.save(document)

    def active_openai_config(self) -> dict[str, Any]:
        document = self.load()
        platform = next((item for item in document.platforms if item.id == document.activePlatformId), None)
        missing: list[str] = []
        if not platform:
            missing.append("activePlatformId")
            return {"enabled": False, "base_url": "", "api_key": "", "model": "", "platform_id": "", "missing_items": missing}
        model = next((item for item in platform.models if item.id == document.activeModelId), None)
        if not platform.enabled:
            missing.append("platform disabled")
        if not _normalize_base_url(platform.baseUrl):
            missing.append("baseUrl")
        if not platform.apiKey:
            missing.append("apiKey")
        if not model:
            missing.append("activeModelId")
        elif not model.enabled:
            missing.append("model disabled")
        return {
            "enabled": not missing,
            "base_url": _normalize_base_url(platform.baseUrl),
            "api_key": platform.apiKey,
            "model": document.activeModelId,
            "platform_id": platform.id,
            "missing_items": missing,
        }

    def _merge_presets(self, document: LLMPlatformConfigDocument) -> LLMPlatformConfigDocument:
        saved = {item.id: item for item in document.platforms}
        merged: list[LLMPlatformConfig] = []
        for preset in default_platforms():
            user = saved.pop(preset.id, None)
            if not user:
                merged.append(preset)
                continue
            model_ids = {item.id for item in user.models}
            models = user.models + [item for item in preset.models if item.id not in model_ids]
            merged.append(
                preset.model_copy(
                    update={
                        "baseUrl": user.baseUrl or preset.baseUrl,
                        "apiKey": user.apiKey,
                        "enabled": user.enabled,
                        "models": models,
                        "docsUrl": user.docsUrl or preset.docsUrl,
                    }
                )
            )
        merged.extend(saved.values())
        return document.model_copy(update={"platforms": merged})

    def _safe_platform(self, platform: LLMPlatformConfig) -> dict[str, Any]:
        data = platform.model_dump(mode="json", exclude={"apiKey"})
        data["hasApiKey"] = bool(platform.apiKey)
        data["apiKeyPreview"] = _preview_secret(platform.apiKey)
        return data
```

- [ ] **Step 4: Run store tests**

Run:

```powershell
pytest G:\tests\test_llm_platforms.py -q
```

Expected: all four tests pass.

- [ ] **Step 5: Commit or record no-git state**

Run:

```powershell
git rev-parse --is-inside-work-tree
```

Expected in this workspace: `fatal: not a git repository`. Record this in the task handoff. If it returns `true`, commit:

```powershell
git add G:\tests\test_llm_platforms.py G:\app\llm_platforms.py
git commit -m "feat: add llm platform store"
```

---

### Task 2: Platform Check And Model Refresh

**Files:**
- Modify: `G:/tests/test_llm_platforms.py`
- Modify: `G:/app/llm_platforms.py`

- [ ] **Step 1: Add failing tests for check and refresh**

Append to `G:/tests/test_llm_platforms.py`:

```python
import httpx


def test_check_platform_reports_missing_key_without_network(tmp_path: Path):
    store = LLMPlatformStore(tmp_path)

    result = store.check_platform("openai")

    assert result["status"] == "red"
    assert "apiKey" in result["missing_items"]


def test_refresh_models_merges_remote_models_and_preserves_manual_models(tmp_path: Path):
    store = LLMPlatformStore(tmp_path)
    doc = store.load()
    openai = next(item for item in doc.platforms if item.id == "openai")
    openai.apiKey = "secret-one"
    openai.enabled = True
    openai.models.append(LLMPlatformModel(id="manual-model", name="Manual Model", group="Manual", enabled=True))
    store.save(doc.model_copy(update={"activePlatformId": "openai", "activeModelId": "manual-model"}))

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/models"
        assert request.headers["authorization"] == "Bearer secret-one"
        return httpx.Response(200, json={"data": [{"id": "remote-model-a"}, {"id": "remote-model-b", "object": "model"}]})

    result = store.refresh_models("openai", client=httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.openai.com"))

    ids = {item["id"] for item in result["models"]}
    assert {"manual-model", "remote-model-a", "remote-model-b"}.issubset(ids)


def test_refresh_models_failure_keeps_existing_models(tmp_path: Path):
    store = LLMPlatformStore(tmp_path)
    doc = store.load()
    openai = next(item for item in doc.platforms if item.id == "openai")
    openai.apiKey = "secret-one"
    openai.enabled = True
    openai.models = [LLMPlatformModel(id="manual-model", name="Manual Model", group="Manual", enabled=True)]
    store.save(doc)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "down"})

    result = store.refresh_models("openai", client=httpx.Client(transport=httpx.MockTransport(handler)))

    assert result["status"] == "red"
    assert store.load().platforms[0].models[0].id == "manual-model"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
pytest G:\tests\test_llm_platforms.py::test_check_platform_reports_missing_key_without_network G:\tests\test_llm_platforms.py::test_refresh_models_merges_remote_models_and_preserves_manual_models G:\tests\test_llm_platforms.py::test_refresh_models_failure_keeps_existing_models -q
```

Expected: fail with missing `check_platform` and `refresh_models`.

- [ ] **Step 3: Implement check and refresh methods**

Add these methods to `LLMPlatformStore` in `G:/app/llm_platforms.py`:

```python
    def check_platform(self, platform_id: str, *, client: httpx.Client | None = None) -> dict[str, Any]:
        document = self.load()
        platform = self._platform_or_error(document, platform_id)
        missing = []
        if not platform.enabled:
            missing.append("platform disabled")
        if not _normalize_base_url(platform.baseUrl):
            missing.append("baseUrl")
        if not platform.apiKey:
            missing.append("apiKey")
        if missing:
            return {"status": "red", "message": "平台配置不完整。", "missing_items": missing}
        close_client = client is None
        http = client or httpx.Client(timeout=httpx.Timeout(8.0, connect=3.0), follow_redirects=True, trust_env=False)
        try:
            response = http.get(
                f"{_normalize_base_url(platform.baseUrl)}/models",
                headers={"Authorization": f"Bearer {platform.apiKey}"},
            )
            if response.status_code >= 400:
                return {"status": "red", "message": f"/models 返回 HTTP {response.status_code}", "missing_items": []}
            return {"status": "green", "message": "平台接口可访问。", "missing_items": []}
        except Exception as exc:  # noqa: BLE001 - reported to UI as readiness detail.
            return {"status": "red", "message": f"平台接口不可访问：{exc}", "missing_items": []}
        finally:
            if close_client:
                http.close()

    def refresh_models(self, platform_id: str, *, client: httpx.Client | None = None) -> dict[str, Any]:
        document = self.load()
        platform = self._platform_or_error(document, platform_id)
        check = self.check_platform(platform_id, client=client)
        if check["status"] == "red":
            return {"status": "red", "message": check["message"], "models": [item.model_dump(mode="json") for item in platform.models]}
        close_client = client is None
        http = client or httpx.Client(timeout=httpx.Timeout(12.0, connect=4.0), follow_redirects=True, trust_env=False)
        try:
            response = http.get(
                f"{_normalize_base_url(platform.baseUrl)}/models",
                headers={"Authorization": f"Bearer {platform.apiKey}"},
            )
            response.raise_for_status()
            payload = response.json()
            items = payload.get("data") if isinstance(payload, dict) else []
            if not isinstance(items, list):
                raise ValueError("/models response does not contain a data list")
            known = {item.id for item in platform.models}
            for item in items:
                if not isinstance(item, dict) or not item.get("id"):
                    continue
                model_id = str(item["id"])
                if model_id not in known:
                    platform.models.append(LLMPlatformModel(id=model_id, name=model_id, group="Remote", enabled=True))
                    known.add(model_id)
            self.save(document)
            return {"status": "green", "message": f"已刷新 {len(items)} 个远程模型。", "models": [item.model_dump(mode="json") for item in platform.models]}
        except Exception as exc:  # noqa: BLE001 - preserve manual models and return concrete status.
            return {"status": "red", "message": f"刷新模型失败：{exc}", "models": [item.model_dump(mode="json") for item in platform.models]}
        finally:
            if close_client:
                http.close()

    def _platform_or_error(self, document: LLMPlatformConfigDocument, platform_id: str) -> LLMPlatformConfig:
        platform = next((item for item in document.platforms if item.id == platform_id), None)
        if not platform:
            raise ValueError(f"unknown platform: {platform_id}")
        return platform
```

- [ ] **Step 4: Run refresh tests**

Run:

```powershell
pytest G:\tests\test_llm_platforms.py -q
```

Expected: all tests in `test_llm_platforms.py` pass.

- [ ] **Step 5: Commit or record no-git state**

Run:

```powershell
git rev-parse --is-inside-work-tree
```

Expected in this workspace: `fatal: not a git repository`. If git is available:

```powershell
git add G:\tests\test_llm_platforms.py G:\app\llm_platforms.py
git commit -m "feat: refresh llm platform models"
```

---

### Task 3: FastAPI LLM Platform Routes

**Files:**
- Modify: `G:/tests/test_llm_platforms.py`
- Modify: `G:/app/main.py`

- [ ] **Step 1: Add failing API tests**

Append to `G:/tests/test_llm_platforms.py`:

```python
from fastapi.testclient import TestClient

from app.main import app, get_settings
from app.settings import Settings


def _client(tmp_path: Path) -> TestClient:
    app.dependency_overrides.clear()
    app.dependency_overrides[get_settings] = lambda: Settings(storage_dir=tmp_path, dry_run=True)
    return TestClient(app)


def test_llm_platforms_api_saves_selection_and_hides_keys(tmp_path: Path):
    with _client(tmp_path) as client:
        initial = client.get("/llm/platforms")
        assert initial.status_code == 200, initial.text
        body = initial.json()
        openai = next(item for item in body["platforms"] if item["id"] == "openai")
        openai["apiKey"] = "secret-one"
        openai["enabled"] = True
        save = client.put(
            "/llm/platforms",
            json={
                "activePlatformId": "openai",
                "activeModelId": "gpt-4o-mini",
                "platforms": body["platforms"],
                "localModels": [],
            },
        )
        selected = client.put("/llm/selection", json={"platformId": "openai", "modelId": "gpt-4o-mini"})
        loaded = client.get("/llm/platforms")

    assert save.status_code == 200, save.text
    assert selected.status_code == 200, selected.text
    loaded_openai = next(item for item in loaded.json()["platforms"] if item["id"] == "openai")
    assert loaded_openai["hasApiKey"] is True
    assert "apiKey" not in loaded_openai
    assert "secret-one" not in str(loaded.json())
    assert loaded.json()["activePlatformId"] == "openai"
    assert loaded.json()["activeModelId"] == "gpt-4o-mini"


def test_llm_local_model_api_crud(tmp_path: Path):
    with _client(tmp_path) as client:
        created = client.post(
            "/llm/local-models",
            json={
                "id": "",
                "name": "Local Ollama",
                "path": "http://127.0.0.1:11434/v1",
                "type": "ollama_or_local_service",
                "notes": "local service",
                "enabled": True,
            },
        )
        model_id = created.json()["id"]
        updated = client.put(
            f"/llm/local-models/{model_id}",
            json={
                "id": model_id,
                "name": "Local Ollama Updated",
                "path": "http://127.0.0.1:11434/v1",
                "type": "ollama_or_local_service",
                "notes": "local service",
                "enabled": False,
            },
        )
        deleted = client.delete(f"/llm/local-models/{model_id}")

    assert created.status_code == 200, created.text
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "Local Ollama Updated"
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["localModels"] == []
```

- [ ] **Step 2: Run API tests to verify failure**

Run:

```powershell
pytest G:\tests\test_llm_platforms.py::test_llm_platforms_api_saves_selection_and_hides_keys G:\tests\test_llm_platforms.py::test_llm_local_model_api_crud -q
```

Expected: fail with `404 Not Found` for `/llm/platforms`.

- [ ] **Step 3: Implement route models and dependencies in `main.py`**

Add imports near existing imports:

```python
from app.llm_platforms import (
    LLMPlatformConfigDocument,
    LLMPlatformStore,
    LocalLLMModel,
)
```

Add request model near other local request models:

```python
class LLMSelectionRequest(BaseModel):
    platformId: str
    modelId: str
```

Add dependency:

```python
def get_llm_platform_store(settings: Settings = Depends(get_settings)) -> LLMPlatformStore:
    return LLMPlatformStore(settings.storage_dir)
```

Add routes after the existing `/models/*` routes:

```python
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
    saved = llm_store.save_preserving_secrets(request)
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
    created = llm_store.create_local_model(request)
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
```

- [ ] **Step 4: Run API tests**

Run:

```powershell
pytest G:\tests\test_llm_platforms.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit or record no-git state**

Run:

```powershell
git rev-parse --is-inside-work-tree
```

Expected in this workspace: `fatal: not a git repository`. If git is available:

```powershell
git add G:\tests\test_llm_platforms.py G:\app\main.py
git commit -m "feat: expose llm platform api"
```

---

### Task 4: Settings Override Uses Active Platform

**Files:**
- Modify: `G:/tests/test_llm_platforms.py`
- Modify: `G:/app/settings.py`

- [ ] **Step 1: Add failing settings override test**

Append to `G:/tests/test_llm_platforms.py`:

```python
from app.settings import apply_desktop_settings_overrides


def test_active_llm_platform_overrides_openai_compatible_settings(tmp_path: Path):
    store = LLMPlatformStore(tmp_path)
    doc = store.load()
    gemini = next(item for item in doc.platforms if item.id == "gemini")
    gemini.apiKey = "gemini-key"
    gemini.enabled = True
    store.save(doc.model_copy(update={"activePlatformId": "gemini", "activeModelId": "gemini-2.0-flash"}))

    settings = apply_desktop_settings_overrides(Settings(storage_dir=tmp_path, dry_run=False, llm_engine="dryrun"))

    assert settings.llm_engine == "openai_compatible"
    assert settings.openai_compatible_enabled is True
    assert settings.openai_compatible_base_url == "https://generativelanguage.googleapis.com/v1beta/openai"
    assert settings.openai_compatible_api_key == "gemini-key"
    assert settings.openai_compatible_model == "gemini-2.0-flash"
```

- [ ] **Step 2: Run test to verify failure**

Run:

```powershell
pytest G:\tests\test_llm_platforms.py::test_active_llm_platform_overrides_openai_compatible_settings -q
```

Expected: fails because `llm_engine` remains `dryrun`.

- [ ] **Step 3: Implement active LLM override**

In `G:/app/settings.py`, add import:

```python
from app.llm_platforms import LLMPlatformStore
```

Refactor the start of `apply_desktop_settings_overrides` so it no longer returns before checking `llm_platforms.json`. Replace the current early-return block:

```python
    path = settings.storage_dir / "desktop" / "desktop_settings.json"
    if not path.exists():
        return settings
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return settings
    updates: dict[str, Any] = {}
```

with:

```python
    path = settings.storage_dir / "desktop" / "desktop_settings.json"
    data: dict[str, Any] = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        except Exception:
            data = {}
    updates: dict[str, Any] = {}
```

Then add this block after the existing desktop settings mapping loop and before the final return:

```python
    llm_config = LLMPlatformStore(settings.storage_dir).active_openai_config()
    if llm_config["enabled"]:
        updates.update(
            {
                "llm_engine": "openai_compatible",
                "openai_compatible_enabled": True,
                "openai_compatible_base_url": llm_config["base_url"],
                "openai_compatible_api_key": llm_config["api_key"],
                "openai_compatible_model": llm_config["model"],
            }
        )
```

Keep the final return behavior at the end of the function:

```python
    if not updates:
        return settings
    return settings.model_copy(update=updates)
```

- [ ] **Step 4: Run settings override test**

Run:

```powershell
pytest G:\tests\test_llm_platforms.py::test_active_llm_platform_overrides_openai_compatible_settings -q
```

Expected: pass.

- [ ] **Step 5: Run existing model and rewrite tests**

Run:

```powershell
pytest G:\tests\test_model_center.py G:\tests\test_script_rewrite_batch_16.py -q
```

Expected: pass, confirming dry-run behavior remains intact.

- [ ] **Step 6: Commit or record no-git state**

Run:

```powershell
git rev-parse --is-inside-work-tree
```

Expected in this workspace: `fatal: not a git repository`. If git is available:

```powershell
git add G:\tests\test_llm_platforms.py G:\app\settings.py
git commit -m "feat: map active llm platform into settings"
```

---

### Task 5: OpenAI-Compatible Adapter HTTP Calls

**Files:**
- Modify: `G:/tests/test_llm_platforms.py`
- Modify: `G:/app/adapters/llm.py`

- [ ] **Step 1: Add failing adapter tests**

Append to `G:/tests/test_llm_platforms.py`:

```python
import json

from app.adapters.llm import OpenAICompatibleAdapter


def test_openai_adapter_posts_chat_completion_and_writes_rewrite_files(tmp_path: Path):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["authorization"] = request.headers.get("authorization")
        captured["payload"] = json.loads(request.content.decode("utf-8"))
        content = {
            "scripts": [
                {
                    "script_id": "script_001",
                    "title": "Aivo Hook",
                    "platform": "douyin",
                    "tone": "confident",
                    "hook": "Start with a risk question.",
                    "body": "Explain the benefit clearly.",
                    "cta": "Ask viewers to try it.",
                    "segments": [],
                    "source_policy": "style/structure reference only",
                }
            ],
            "scores": [{"script_id": "script_001", "score": 91, "platform_fit": "douyin", "tone_fit": "confident", "risk_flags": []}],
        }
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(content)}}]})

    adapter = OpenAICompatibleAdapter(
        dry_run=False,
        enabled=True,
        base_url="https://api.example.test/v1/",
        api_key="secret-one",
        model="example-model",
        transport=httpx.MockTransport(handler),
    )

    result = adapter.rewrite_scripts(
        reference_analysis={"reference_script": {"hook": "risk"}, "style_summary": {"tone": "direct"}},
        request={"reference_id": "ref-1", "project_id": "project_demo", "count": 1, "platform": "douyin", "tone": "confident", "product_info": {"name": "Aivo"}},
        out_dir=tmp_path,
    )

    rewritten = json.loads(result.rewritten_scripts_path.read_text(encoding="utf-8"))
    scores = json.loads(result.script_scores_path.read_text(encoding="utf-8"))
    report = json.loads(result.rewrite_report_path.read_text(encoding="utf-8"))
    assert captured["path"] == "/v1/chat/completions"
    assert captured["authorization"] == "Bearer secret-one"
    assert captured["payload"]["model"] == "example-model"
    assert rewritten["scripts"][0]["script_id"] == "script_001"
    assert scores["scores"][0]["score"] == 91
    assert report["engine"] == "openai_compatible"


def test_openai_adapter_readiness_reports_missing_items():
    adapter = OpenAICompatibleAdapter(dry_run=False, enabled=True, base_url="", api_key="", model="")

    readiness = adapter.readiness()

    assert readiness["ready"] is False
    assert "OPENAI_COMPATIBLE_BASE_URL missing" in readiness["blocking_items"]
    assert "OPENAI_COMPATIBLE_API_KEY missing" in readiness["blocking_items"]
    assert "OPENAI_COMPATIBLE_MODEL missing" in readiness["blocking_items"]
```

- [ ] **Step 2: Run adapter tests to verify failure**

Run:

```powershell
pytest G:\tests\test_llm_platforms.py::test_openai_adapter_posts_chat_completion_and_writes_rewrite_files G:\tests\test_llm_platforms.py::test_openai_adapter_readiness_reports_missing_items -q
```

Expected: first test fails because `transport` is unsupported and `rewrite_scripts` raises `AdapterError`.

- [ ] **Step 3: Implement adapter HTTP behavior**

Modify `OpenAICompatibleAdapter` in `G:/app/adapters/llm.py`:

```python
import json

import httpx
```

Update constructor:

```python
    def __init__(
        self,
        *,
        dry_run: bool = True,
        enabled: bool = False,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str = "gpt-compatible",
        transport: httpx.BaseTransport | None = None,
    ):
        super().__init__(dry_run=dry_run, enabled=enabled and not dry_run)
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key or ""
        self.model = model or ""
        self.transport = transport
```

Update readiness:

```python
        if not self.model:
            blocking_items.append("OPENAI_COMPATIBLE_MODEL missing")
```

Replace `rewrite_scripts` with:

```python
    def rewrite_scripts(self, *, reference_analysis: dict[str, Any], request: dict[str, Any], out_dir: Path) -> LLMRewriteResult:
        readiness = self.readiness()
        if not readiness["ready"]:
            raise AdapterError("OpenAI-compatible LLM is not ready: " + ", ".join(readiness["blocking_items"]))
        ensure_dir(out_dir)
        payload = self._chat_payload(reference_analysis=reference_analysis, request=request)
        with httpx.Client(
            timeout=httpx.Timeout(60.0, connect=10.0),
            follow_redirects=True,
            trust_env=False,
            transport=self.transport,
        ) as client:
            response = client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        content = self._message_content(data)
        generated = self._parse_generation(content)
        scripts = generated["scripts"]
        scores = generated["scores"]
        rewritten_scripts_path = write_json(
            out_dir / "rewritten_scripts.json",
            {
                "reference_id": request.get("reference_id"),
                "project_id": request.get("project_id"),
                "scripts": scripts,
            },
        )
        script_scores_path = write_json(out_dir / "script_scores.json", {"scores": scores})
        rewrite_report_path = write_json(
            out_dir / "rewrite_report.json",
            {
                "engine": self.name,
                "model": self.model,
                "count": len(scripts),
                "platform": request.get("platform") or "douyin",
                "tone": request.get("tone") or "practical",
                "style_summary": reference_analysis.get("style_summary", {}),
                "policy": "OpenAI-compatible rewrite generated from structured reference analysis only",
            },
        )
        return LLMRewriteResult(
            rewritten_scripts_path=rewritten_scripts_path,
            script_scores_path=script_scores_path,
            rewrite_report_path=rewrite_report_path,
        )

    def _chat_payload(self, *, reference_analysis: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
        count = int(request.get("count") or 3)
        product_info = request.get("product_info") or {}
        system = (
            "You rewrite short video scripts using only the provided structure and style. "
            "Return strict JSON with keys scripts and scores. Do not copy source wording."
        )
        user = {
            "reference_analysis": reference_analysis,
            "product_info": product_info,
            "count": count,
            "platform": request.get("platform") or "douyin",
            "tone": request.get("tone") or "practical",
            "required_script_fields": ["script_id", "title", "platform", "tone", "hook", "body", "cta", "segments", "source_policy"],
        }
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            "temperature": 0.4,
        }

    def _message_content(self, data: dict[str, Any]) -> str:
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise AdapterError("OpenAI-compatible response missing choices")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise AdapterError("OpenAI-compatible response missing message content")
        return content

    def _parse_generation(self, content: str) -> dict[str, Any]:
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise AdapterError(f"OpenAI-compatible response was not JSON: {exc}") from exc
        scripts = data.get("scripts")
        scores = data.get("scores")
        if not isinstance(scripts, list) or not scripts:
            raise AdapterError("OpenAI-compatible response JSON missing scripts")
        if not isinstance(scores, list):
            scores = []
        return {"scripts": scripts, "scores": scores}
```

- [ ] **Step 4: Run adapter tests**

Run:

```powershell
pytest G:\tests\test_llm_platforms.py::test_openai_adapter_posts_chat_completion_and_writes_rewrite_files G:\tests\test_llm_platforms.py::test_openai_adapter_readiness_reports_missing_items -q
```

Expected: pass.

- [ ] **Step 5: Run script rewrite regression tests**

Run:

```powershell
pytest G:\tests\test_script_rewrite_batch_16.py -q
```

Expected: pass.

- [ ] **Step 6: Commit or record no-git state**

Run:

```powershell
git rev-parse --is-inside-work-tree
```

Expected in this workspace: `fatal: not a git repository`. If git is available:

```powershell
git add G:\tests\test_llm_platforms.py G:\app\adapters\llm.py
git commit -m "feat: implement openai compatible llm adapter"
```

---

### Task 6: Frontend Markup And Static Assertions

**Files:**
- Modify: `G:/tests/test_model_center.py`
- Modify: `G:/app/static/studio.html`

- [ ] **Step 1: Add failing frontend exposure assertions**

Modify `test_studio_exposes_model_center_ui` in `G:/tests/test_model_center.py` by adding:

```python
    assert "openLlmSettingsBtn" in html
    assert "addLocalLlmModelBtn" in html
    assert "llmSettingsModal" in html
    assert "localLlmModelModal" in html
    assert "llmPlatformSearch" in html
    assert "llmModelList" in html
```

- [ ] **Step 2: Run frontend assertion test to verify failure**

Run:

```powershell
pytest G:\tests\test_model_center.py::test_studio_exposes_model_center_ui -q
```

Expected: fails because the new IDs are absent.

- [ ] **Step 3: Add model center buttons**

In `G:/app/static/studio.html`, replace the model center page header:

```html
<div class="page-head">
  <h2>模型选择</h2>
  <button id="refreshModelsBtn" type="button">刷新模型</button>
</div>
```

with:

```html
<div class="page-head">
  <h2>模型选择</h2>
  <div class="actions compact page-actions">
    <button id="refreshModelsBtn" type="button">刷新模型</button>
    <button id="openLlmSettingsBtn" type="button">大模型设置</button>
    <button id="addLocalLlmModelBtn" type="button">添加本地模型</button>
  </div>
</div>
```

- [ ] **Step 4: Add modal markup before `</main>` or before the final log/status section**

Add this markup near the end of `G:/app/static/studio.html`, after the view stack sections and before the global log section if present:

```html
<div id="llmSettingsModal" class="modal-shell hidden" role="dialog" aria-modal="true" aria-labelledby="llmSettingsTitle">
  <div class="modal-panel llm-modal-panel">
    <div class="modal-head">
      <h3 id="llmSettingsTitle">大模型设置</h3>
      <button id="closeLlmSettingsBtn" type="button" class="ghost-button">关闭</button>
    </div>
    <div class="llm-settings-layout">
      <aside class="llm-platform-sidebar">
        <input id="llmPlatformSearch" placeholder="搜索模型平台" autocomplete="off" />
        <div id="llmPlatformList" class="llm-platform-list"></div>
      </aside>
      <section class="llm-platform-detail">
        <div class="llm-detail-head">
          <div>
            <strong id="llmPlatformName">选择平台</strong>
            <span id="llmPlatformStatus" class="muted-inline">未启用</span>
          </div>
          <label class="switchline">
            <input id="llmPlatformEnabled" type="checkbox" />
            启用平台
          </label>
        </div>
        <label>
          API 密钥
          <div class="input-action-row">
            <input id="llmApiKey" type="password" placeholder="已配置时留空表示保留旧密钥" autocomplete="off" />
            <button id="checkLlmPlatformBtn" type="button">检查</button>
          </div>
          <span id="llmApiKeyStatus" class="field-hint">未配置</span>
        </label>
        <label>
          API 地址
          <input id="llmBaseUrl" placeholder="https://api.example.com/v1" autocomplete="off" />
        </label>
        <div class="llm-model-toolbar">
          <strong>模型</strong>
          <div class="actions compact">
            <button id="refreshLlmModelsBtn" type="button">刷新模型</button>
            <button id="addLlmModelBtn" type="button">添加模型</button>
            <button id="saveLlmPlatformsBtn" type="button">保存</button>
          </div>
        </div>
        <div id="llmModelList" class="llm-model-list empty">请选择模型平台</div>
        <pre id="llmSettingsStatus" class="json-box">等待配置大模型平台。</pre>
      </section>
    </div>
  </div>
</div>

<div id="localLlmModelModal" class="modal-shell hidden" role="dialog" aria-modal="true" aria-labelledby="localLlmModelTitle">
  <div class="modal-panel local-model-panel">
    <div class="modal-head">
      <h3 id="localLlmModelTitle">添加本地模型</h3>
      <button id="closeLocalLlmModelBtn" type="button" class="ghost-button">关闭</button>
    </div>
    <label>
      模型名称
      <input id="localLlmName" placeholder="例如 本地 Ollama Qwen" autocomplete="off" />
    </label>
    <label>
      模型路径或地址
      <input id="localLlmPath" placeholder="例如 D:\models\qwen 或 http://127.0.0.1:11434/v1" autocomplete="off" />
    </label>
    <label>
      模型类型
      <select id="localLlmType">
        <option value="local_path">本地路径</option>
        <option value="ollama_or_local_service">Ollama/本地服务</option>
        <option value="other">其他</option>
      </select>
    </label>
    <label>
      备注
      <textarea id="localLlmNotes" rows="3"></textarea>
    </label>
    <label class="checkline">
      <input id="localLlmEnabled" type="checkbox" checked />
      启用本地模型
    </label>
    <div class="actions compact">
      <button id="saveLocalLlmModelBtn" type="button">保存本地模型</button>
    </div>
    <div id="localLlmModelList" class="list-box empty">暂无本地模型</div>
  </div>
</div>
```

- [ ] **Step 5: Run frontend assertion test**

Run:

```powershell
pytest G:\tests\test_model_center.py::test_studio_exposes_model_center_ui -q
```

Expected: pass.

- [ ] **Step 6: Commit or record no-git state**

Run:

```powershell
git rev-parse --is-inside-work-tree
```

Expected in this workspace: `fatal: not a git repository`. If git is available:

```powershell
git add G:\tests\test_model_center.py G:\app\static\studio.html
git commit -m "feat: add llm settings modal markup"
```

---

### Task 7: Frontend Styling And JavaScript Behavior

**Files:**
- Modify: `G:/tests/test_model_center.py`
- Modify: `G:/app/static/studio.css`
- Modify: `G:/app/static/studio.js`

- [ ] **Step 1: Add static JS/CSS assertions**

Extend `test_studio_exposes_model_center_ui` in `G:/tests/test_model_center.py`:

```python
    css = Path("G:/app/static/studio.css").read_text(encoding="utf-8")
    assert "/llm/platforms" in js
    assert "/llm/selection" in js
    assert "/llm/local-models" in js
    assert "renderLlmPlatformList" in js
    assert "renderLlmModelList" in js
    assert "modal-shell" in css
    assert "llm-settings-layout" in css
```

- [ ] **Step 2: Run static assertion test to verify failure**

Run:

```powershell
pytest G:\tests\test_model_center.py::test_studio_exposes_model_center_ui -q
```

Expected: fails because JS and CSS additions are absent.

- [ ] **Step 3: Add CSS rules**

Append to `G:/app/static/studio.css` before the `@media` block:

```css
.page-actions {
  min-width: min(520px, 100%);
}

.modal-shell {
  position: fixed;
  inset: 0;
  z-index: 50;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(15, 23, 42, 0.58);
  padding: 20px;
}

.modal-shell.hidden {
  display: none;
}

.modal-panel {
  width: min(980px, 100%);
  max-height: calc(100vh - 40px);
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel);
  box-shadow: 0 24px 70px rgba(15, 23, 42, 0.28);
}

.llm-modal-panel {
  width: min(980px, 100%);
}

.local-model-panel {
  width: min(560px, 100%);
  overflow: auto;
  padding-bottom: 14px;
}

.modal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid var(--line);
  padding: 14px 16px;
}

.ghost-button {
  border-color: var(--line);
  background: #fff;
  color: var(--text);
}

.llm-settings-layout {
  display: grid;
  grid-template-columns: 230px minmax(0, 1fr);
  min-height: 560px;
  max-height: calc(100vh - 110px);
}

.llm-platform-sidebar {
  border-right: 1px solid var(--line);
  background: #f8fafc;
  padding: 12px;
  overflow: auto;
}

.llm-platform-list,
.llm-model-list {
  display: grid;
  gap: 8px;
}

.llm-platform-item,
.llm-model-row {
  display: grid;
  gap: 4px;
  width: 100%;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: #fff;
  padding: 9px 10px;
  color: var(--text);
  text-align: left;
}

.llm-platform-item.active,
.llm-platform-item:hover,
.llm-model-row.active {
  border-color: var(--accent);
  background: #e9f5f2;
}

.llm-platform-detail {
  overflow: auto;
  padding: 16px;
}

.llm-detail-head,
.input-action-row,
.llm-model-toolbar,
.model-row-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.input-action-row {
  align-items: stretch;
}

.input-action-row button {
  width: 88px;
  flex: 0 0 auto;
}

.field-hint,
.muted-inline {
  display: block;
  margin-top: 4px;
  color: var(--muted);
  font-size: 12px;
}

.switchline {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  color: var(--text);
}

.switchline input {
  width: 18px;
  height: 18px;
  margin: 0;
}

.llm-model-group {
  border: 1px solid var(--line);
  border-radius: 6px;
  overflow: hidden;
}

.llm-model-group-title {
  background: #f8fafc;
  border-bottom: 1px solid var(--line);
  padding: 9px 10px;
  font-weight: 700;
}

.llm-model-row {
  border-width: 0 0 1px;
  border-radius: 0;
}

.llm-model-row:last-child {
  border-bottom: 0;
}
```

Add to the existing `@media (max-width: 960px)` block:

```css
  .llm-settings-layout {
    grid-template-columns: 1fr;
  }

  .llm-platform-sidebar {
    border-right: 0;
    border-bottom: 1px solid var(--line);
  }

  .llm-detail-head,
  .llm-model-toolbar,
  .input-action-row {
    align-items: stretch;
    flex-direction: column;
  }

  .input-action-row button {
    width: 100%;
  }
```

- [ ] **Step 4: Add JavaScript state and functions**

In `G:/app/static/studio.js`, add fields to `state`:

```javascript
  llmPlatforms: null,
  selectedLlmPlatformId: "",
```

Add these functions after `renderModelStatus` or after existing model center functions:

```javascript
function showModal(id, show = true) {
  const modal = $(id);
  if (modal) modal.classList.toggle("hidden", !show);
}

function selectedLlmPlatform() {
  if (!state.llmPlatforms) return null;
  return (state.llmPlatforms.platforms || []).find((item) => item.id === state.selectedLlmPlatformId) || null;
}

async function loadLlmPlatforms() {
  state.llmPlatforms = await api("/llm/platforms");
  state.selectedLlmPlatformId = state.selectedLlmPlatformId || state.llmPlatforms.activePlatformId || (state.llmPlatforms.platforms[0] && state.llmPlatforms.platforms[0].id) || "";
  renderLlmPlatformList();
  renderLlmPlatformDetail();
}

async function openLlmSettings() {
  showModal("llmSettingsModal", true);
  await loadLlmPlatforms();
}

function renderLlmPlatformList() {
  const box = $("llmPlatformList");
  if (!box || !state.llmPlatforms) return;
  const query = value("llmPlatformSearch").toLowerCase();
  box.innerHTML = "";
  for (const platform of state.llmPlatforms.platforms || []) {
    if (query && !`${platform.name} ${platform.id}`.toLowerCase().includes(query)) continue;
    const item = document.createElement("button");
    item.type = "button";
    item.className = `llm-platform-item${platform.id === state.selectedLlmPlatformId ? " active" : ""}`;
    item.innerHTML = `<strong></strong><span></span>`;
    item.querySelector("strong").textContent = platform.name;
    item.querySelector("span").textContent = platform.hasApiKey ? "已配置 API Key" : "未配置 API Key";
    item.onclick = () => {
      state.selectedLlmPlatformId = platform.id;
      renderLlmPlatformList();
      renderLlmPlatformDetail();
    };
    box.appendChild(item);
  }
}

function renderLlmPlatformDetail() {
  const platform = selectedLlmPlatform();
  if (!platform) return;
  write("llmPlatformName", platform.name);
  write("llmPlatformStatus", platform.enabled ? "已启用" : "未启用");
  $("llmPlatformEnabled").checked = Boolean(platform.enabled);
  $("llmApiKey").value = "";
  $("llmBaseUrl").value = platform.baseUrl || "";
  write("llmApiKeyStatus", platform.hasApiKey ? `已配置 ${platform.apiKeyPreview || ""}` : "未配置");
  renderLlmModelList(platform);
}

function updateSelectedLlmPlatformFromInputs() {
  const platform = selectedLlmPlatform();
  if (!platform) return null;
  platform.enabled = $("llmPlatformEnabled").checked;
  platform.baseUrl = value("llmBaseUrl");
  const key = value("llmApiKey");
  if (key) platform.apiKey = key;
  return platform;
}

function renderLlmModelList(platform) {
  const box = $("llmModelList");
  if (!box) return;
  const models = platform.models || [];
  box.innerHTML = "";
  if (!models.length) {
    box.className = "llm-model-list empty";
    box.textContent = "暂无模型，可点击添加模型或刷新模型。";
    return;
  }
  box.className = "llm-model-list";
  const groups = new Map();
  for (const model of models) {
    const group = model.group || "Custom";
    if (!groups.has(group)) groups.set(group, []);
    groups.get(group).push(model);
  }
  for (const [group, rows] of groups.entries()) {
    const section = document.createElement("section");
    section.className = "llm-model-group";
    const title = document.createElement("div");
    title.className = "llm-model-group-title";
    title.textContent = group;
    section.appendChild(title);
    for (const model of rows) {
      const row = document.createElement("div");
      row.className = `llm-model-row${state.llmPlatforms.activePlatformId === platform.id && state.llmPlatforms.activeModelId === model.id ? " active" : ""}`;
      const label = document.createElement("div");
      label.innerHTML = `<strong></strong><span class="field-hint"></span>`;
      label.querySelector("strong").textContent = model.name || model.id;
      label.querySelector("span").textContent = model.id;
      const actions = document.createElement("div");
      actions.className = "model-row-actions";
      const toggle = document.createElement("button");
      toggle.type = "button";
      toggle.textContent = model.enabled ? "停用" : "启用";
      toggle.onclick = () => {
        model.enabled = !model.enabled;
        renderLlmModelList(platform);
      };
      const select = document.createElement("button");
      select.type = "button";
      select.textContent = state.llmPlatforms.activePlatformId === platform.id && state.llmPlatforms.activeModelId === model.id ? "默认模型" : "设为默认";
      select.onclick = () => safeRun(() => selectLlmModel(platform.id, model.id));
      const remove = document.createElement("button");
      remove.type = "button";
      remove.textContent = "删除";
      remove.onclick = () => {
        platform.models = platform.models.filter((item) => item.id !== model.id);
        renderLlmModelList(platform);
      };
      actions.append(toggle, select, remove);
      row.append(label, actions);
      section.appendChild(row);
    }
    box.appendChild(section);
  }
}

async function saveLlmPlatforms() {
  updateSelectedLlmPlatformFromInputs();
  const body = await api("/llm/platforms", {
    method: "PUT",
    body: JSON.stringify(state.llmPlatforms),
  });
  state.llmPlatforms = body;
  renderLlmPlatformList();
  renderLlmPlatformDetail();
  writeJson("llmSettingsStatus", { status: "saved", activePlatformId: body.activePlatformId, activeModelId: body.activeModelId });
  log("大模型平台配置已保存。", "ok");
}

async function checkLlmPlatform() {
  updateSelectedLlmPlatformFromInputs();
  await saveLlmPlatforms();
  const platform = selectedLlmPlatform();
  const body = await api(`/llm/platforms/${encodeURIComponent(platform.id)}/check`, { method: "POST", body: "{}" });
  writeJson("llmSettingsStatus", body);
}

async function refreshLlmModels() {
  updateSelectedLlmPlatformFromInputs();
  await saveLlmPlatforms();
  const platform = selectedLlmPlatform();
  const body = await api(`/llm/platforms/${encodeURIComponent(platform.id)}/models/refresh`, { method: "POST", body: "{}" });
  writeJson("llmSettingsStatus", body);
  await loadLlmPlatforms();
}

function addLlmModel() {
  const platform = updateSelectedLlmPlatformFromInputs();
  if (!platform) throw new Error("请先选择平台。");
  const modelId = window.prompt("请输入模型 ID，例如 gpt-4o-mini");
  if (!modelId) return;
  platform.models = platform.models || [];
  platform.models.push({ id: modelId.trim(), name: modelId.trim(), group: "Manual", enabled: true });
  renderLlmModelList(platform);
}

async function selectLlmModel(platformId, modelId) {
  updateSelectedLlmPlatformFromInputs();
  await saveLlmPlatforms();
  const body = await api("/llm/selection", {
    method: "PUT",
    body: JSON.stringify({ platformId, modelId }),
  });
  state.llmPlatforms = body;
  renderLlmPlatformList();
  renderLlmPlatformDetail();
  log(`已设置默认大模型：${platformId}/${modelId}`, "ok");
}

async function openLocalLlmModelModal() {
  showModal("localLlmModelModal", true);
  if (!state.llmPlatforms) await loadLlmPlatforms();
  renderLocalLlmModelList();
}

function renderLocalLlmModelList() {
  const rows = (state.llmPlatforms && state.llmPlatforms.localModels) || [];
  renderRows("localLlmModelList", rows, "id", "name", "暂无本地模型", () => {});
}

async function saveLocalLlmModel() {
  const payload = {
    id: "",
    name: value("localLlmName"),
    path: value("localLlmPath"),
    type: value("localLlmType") || "local_path",
    notes: value("localLlmNotes"),
    enabled: $("localLlmEnabled").checked,
  };
  if (!payload.name || !payload.path) throw new Error("请填写本地模型名称和路径。");
  const created = await api("/llm/local-models", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  await loadLlmPlatforms();
  renderLocalLlmModelList();
  writeJson("llmSettingsStatus", { localModelCreated: created });
  log(`本地模型已添加：${created.name}`, "ok");
}
```

- [ ] **Step 5: Add event bindings**

In `bind()` in `G:/app/static/studio.js`, add:

```javascript
  bindClick("openLlmSettingsBtn", openLlmSettings);
  bindClick("addLocalLlmModelBtn", openLocalLlmModelModal);
  bindClick("closeLlmSettingsBtn", () => showModal("llmSettingsModal", false));
  bindClick("closeLocalLlmModelBtn", () => showModal("localLlmModelModal", false));
  bindClick("saveLlmPlatformsBtn", saveLlmPlatforms);
  bindClick("checkLlmPlatformBtn", checkLlmPlatform);
  bindClick("refreshLlmModelsBtn", refreshLlmModels);
  bindClick("addLlmModelBtn", addLlmModel);
  bindClick("saveLocalLlmModelBtn", saveLocalLlmModel);
  const platformSearch = $("llmPlatformSearch");
  if (platformSearch) platformSearch.oninput = renderLlmPlatformList;
```

- [ ] **Step 6: Run static assertion test**

Run:

```powershell
pytest G:\tests\test_model_center.py::test_studio_exposes_model_center_ui -q
```

Expected: pass.

- [ ] **Step 7: Run frontend-adjacent tests**

Run:

```powershell
pytest G:\tests\test_model_center.py G:\tests\test_digital_human_studio_pages_14.py -q
```

Expected: pass.

- [ ] **Step 8: Commit or record no-git state**

Run:

```powershell
git rev-parse --is-inside-work-tree
```

Expected in this workspace: `fatal: not a git repository`. If git is available:

```powershell
git add G:\tests\test_model_center.py G:\app\static\studio.css G:\app\static\studio.js
git commit -m "feat: wire llm settings frontend"
```

---

### Task 8: End-To-End Verification

**Files:**
- No required source edits unless verification exposes a defect.

- [ ] **Step 1: Run focused backend tests**

Run:

```powershell
pytest G:\tests\test_llm_platforms.py G:\tests\test_model_center.py G:\tests\test_script_rewrite_batch_16.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run full existing test suite**

Run:

```powershell
pytest -q
```

Expected: all tests pass. If unrelated historical tests fail, capture the failing test names and the first failure message.

- [ ] **Step 3: Compile Python files**

Run:

```powershell
python -m compileall G:\app G:\tests
```

Expected: command exits `0`.

- [ ] **Step 4: Start or reuse local app server**

Run:

```powershell
Start-Process -FilePath python -ArgumentList @('-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000') -WorkingDirectory 'G:\' -WindowStyle Hidden
```

Expected: server starts at `http://127.0.0.1:8000`.

- [ ] **Step 5: Probe LLM platform API manually**

Run:

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/llm/platforms' -Method GET | ConvertTo-Json -Depth 8
```

Expected: JSON includes `platforms`, `localModels`, `activePlatformId`, `activeModelId`, and no plaintext `apiKey`.

- [ ] **Step 6: Verify browser UI**

Open:

```text
http://127.0.0.1:8000/
```

Manual checks:

- Navigate to `模型选择`.
- Click `大模型设置`.
- Confirm the left platform list appears.
- Search for `Gemini` and confirm the list filters.
- Select `Gemini`, confirm API key and API address fields appear.
- Add a manual model and set it as default.
- Click `保存`, then close and reopen the modal; confirm the platform/model selection persists.
- Click `添加本地模型`, save a local model, and confirm it appears in the local model list.

- [ ] **Step 7: Record verification evidence**

Record:

- Focused pytest command and result.
- Full pytest command and result.
- Compile command and result.
- Manual browser checks completed.
- Whether git was unavailable or a commit was created.

Do not mark the goal complete until every item in the design spec has evidence from tests, command output, rendered UI behavior, or manual browser verification.
