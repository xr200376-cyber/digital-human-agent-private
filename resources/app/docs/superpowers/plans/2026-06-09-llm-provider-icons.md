# LLM Provider Icons And Presets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add common OpenAI-compatible cloud providers and render official provider icons in the LLM platform selector.

**Architecture:** Extend `LLMPlatformConfig` with an `icon` static path, add new default provider presets in `llm_platforms.py`, and update `studio.js/css/html` to render icons. Keep the existing API-key/base-URL/model-selection flow unchanged.

**Tech Stack:** FastAPI/Pydantic, static HTML/CSS/JavaScript, pytest, local desktop resource sync.

---

### Task 1: Provider Preset Tests

**Files:**
- Modify: `G:/tests/test_llm_platforms.py`

- [ ] Add a failing test that default safe document includes Baidu Qianfan, Doubao Ark, Aliyun Bailian, Tencent Hunyuan, Zhipu, Moonshot, and DeepSeek.
- [ ] Assert each new platform has a non-empty `/provider-icons/` icon path and the expected OpenAI-compatible base URL.
- [ ] Run `pytest G:\tests\test_llm_platforms.py::test_default_document_contains_presets_and_no_plaintext_keys -q` and confirm failure.

### Task 2: Backend Presets

**Files:**
- Modify: `G:/app/llm_platforms.py`

- [ ] Add `icon: str = ""` to `LLMPlatformConfig`.
- [ ] Add icon paths and provider presets to `default_platforms()`.
- [ ] Update preset merging so existing saved platforms receive default icons when their icon is missing.
- [ ] Run the provider preset test and confirm it passes.

### Task 3: Frontend Icon Rendering

**Files:**
- Modify: `G:/app/static/studio.html`
- Modify: `G:/app/static/studio.js`
- Modify: `G:/app/static/studio.css`
- Modify: `G:/tests/test_model_center.py`

- [ ] Add a failing static test for `llm-platform-icon` markup/style and JS rendering.
- [ ] Render provider icon images in the platform list and detail header.
- [ ] Style icons as small square official-logo chips.
- [ ] Run `pytest G:\tests\test_model_center.py -q` and `node --check G:\app\static\studio.js`.

### Task 4: Icon Assets And Desktop Verification

**Files:**
- Create: `G:/app/static/provider-icons/*`
- Copy to: `G:/dist/desktop-cloud-providers-v2/win-unpacked/resources/app/static/provider-icons/*`

- [ ] Download provider icons from official provider domains.
- [ ] Verify icon files exist.
- [ ] Run full tests: `pytest -q`, `python -m compileall G:\app G:\tests`.
- [ ] Sync files to desktop package, restart desktop app/backend, and verify `http://127.0.0.1:8080/llm/platforms` includes the new providers and icon paths.
