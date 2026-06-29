# LLM Platform Settings Design

Date: 2026-06-08

## Summary

Add a model settings experience for cloud and local LLM configuration. Cloud platforms use one OpenAI-compatible integration path: users choose a platform preset, enter an API key and API base URL, refresh or add models, and set the default model for downstream LLM work. A separate "Add local model" action registers local models without requiring this phase to implement local inference.

## Goals

- Provide a screenshot-style "Large Model Settings" modal with a searchable platform list on the left and platform configuration on the right.
- Support OpenAI-compatible cloud platforms through API key, base URL, model list, enabled state, and default model selection.
- Include platform presets for OpenAI, O3, Gemini, SiliconFlow, GitHub Models, Gitee AI, PPIO, and a custom platform option.
- Let users refresh models from a platform when `/models` is available, while preserving manually entered models when refresh fails.
- Add a separate local model button and modal for registering local model names, paths, types, notes, and enabled state.
- Route real LLM calls through the selected platform and selected model when configured.
- Avoid returning API keys in plaintext from read APIs.

## Non-Goals

- Do not build native provider-specific SDK integrations in this phase.
- Do not implement local inference engines in this phase.
- Do not require every platform to support model refresh; manual model entry remains valid.
- Do not add a new landing page or replace the existing model center page.

## Existing Context

The repository has a Python FastAPI backend and a static frontend under `static/studio.*`. Current LLM support is represented by `adapters/llm.py`, where `OpenAICompatibleAdapter` and `LocalModelAdapter` are placeholders. Existing model center APIs live in `main.py` around `/models/catalog`, `/models/selection`, and `/models/readiness`. Desktop settings are stored through `desktop_settings.py` and `storage/desktop/desktop_settings.json`.

`G:\app` is not currently a git repository, so the design document can be written but cannot be committed from this workspace.

## UI Design

### Entry Points

The existing model page toolbar gets two actions:

- `大模型设置`: opens the cloud LLM platform settings modal.
- `添加本地模型`: opens the local model registration modal.

### Large Model Settings Modal

The modal follows the selected screenshot-style layout:

- Header: `大模型设置`, close action, and save action when needed.
- Left column: platform search input and platform list.
- Right column: selected platform details, API credentials, API base URL, and model groups.

The platform list contains presets:

- OpenAI
- O3
- PPIO 派欧云
- Gemini
- 硅基流动
- Gitee AI
- GitHub Models
- 自定义平台

Each platform preset supplies a display name, a provider id, a default OpenAI-compatible base URL when known, and default model groups. Users can override the base URL.

### Platform Fields

Each platform detail panel includes:

- Enabled switch.
- API key password input.
- API key configured status.
- Check button.
- API base URL input.
- Model documentation/help links when useful.
- Refresh models button.
- Add model button.
- Grouped model list.

Each model row includes:

- Model display name.
- Model id.
- Enabled switch.
- Set as default action.
- Edit/settings action.
- Delete action.

### Local Model Modal

The local model modal includes:

- Model name.
- Model path or endpoint.
- Model type: `local_path`, `ollama_or_local_service`, or `other`.
- Notes.
- Enabled switch.

This phase stores and displays local model entries. Local inference execution remains future work. `ollama_or_local_service` entries may later be bridged into the OpenAI-compatible adapter if the user supplies a compatible base URL.

## Data Model

Store LLM platform configuration separately from the large desktop settings object:

Path:

```text
storage/desktop/llm_platforms.json
```

Shape:

```json
{
  "activePlatformId": "openai",
  "activeModelId": "gpt-4o-mini",
  "platforms": [
    {
      "id": "openai",
      "name": "OpenAI",
      "baseUrl": "https://api.openai.com/v1",
      "apiKey": "stored-secret",
      "enabled": true,
      "models": [
        {
          "id": "gpt-4o-mini",
          "name": "GPT-4o mini",
          "group": "GPT-4o",
          "enabled": true
        }
      ]
    }
  ],
  "localModels": [
    {
      "id": "local-wav2lip",
      "name": "Local Wav2Lip",
      "path": "D:\\models\\wav2lip",
      "type": "local_path",
      "notes": "",
      "enabled": true
    }
  ]
}
```

Read responses must replace `apiKey` with safe metadata:

```json
{
  "hasApiKey": true,
  "apiKeyPreview": "sk-...abcd"
}
```

The save API treats an empty or omitted API key as "keep the existing secret" and only overwrites the stored key when a non-empty new value is provided.

## Backend API Design

Add LLM platform APIs:

- `GET /llm/platforms`: returns preset platforms merged with saved user configuration, local models, and active selection.
- `PUT /llm/platforms`: saves platform configuration and local model data while preserving existing API keys when no replacement is provided.
- `POST /llm/platforms/{platform_id}/check`: checks whether the platform can be reached with the supplied or stored base URL and API key.
- `POST /llm/platforms/{platform_id}/models/refresh`: calls an OpenAI-compatible `/models` endpoint and merges discovered models into the platform model list.
- `PUT /llm/selection`: sets the active platform and active model.
- `POST /llm/local-models`: creates a local model entry.
- `PUT /llm/local-models/{model_id}`: updates a local model entry.
- `DELETE /llm/local-models/{model_id}`: deletes a local model entry.

Responses should include clear status and missing item messages, especially when an API key, base URL, active platform, or active model is missing.

## OpenAI-Compatible Integration

Update `OpenAICompatibleAdapter` so it can use the active LLM platform configuration.

Request behavior:

- Normalize base URLs by trimming trailing slashes.
- For chat calls, post to `{baseUrl}/chat/completions`.
- For model refresh, get `{baseUrl}/models`.
- Send `Authorization: Bearer <apiKey>`.
- Include the active model id in `model`.
- Use the existing dry-run policy: when the app is in dry-run mode, configuration management still works, but real external calls do not run unless explicitly enabled by the surrounding workflow.

The adapter should not contain provider-specific branches beyond base URL normalization and shared OpenAI-compatible request handling.

## Error Handling

The UI and API should distinguish:

- Missing API key.
- Missing base URL.
- No active model selected.
- Platform disabled.
- Network or timeout error.
- Unsupported response shape from `/models`.
- Chat completion response missing expected content.

Refreshing models must not delete existing manual models on failure.

## Security

This phase follows the existing desktop configuration storage style. API keys are stored locally under `storage/desktop/llm_platforms.json`, but read APIs must not return plaintext keys. Later hardening can move secrets into Windows Credential Manager or add encryption.

Frontend behavior:

- Show "已配置" when a key exists.
- Let the user enter a new key to replace the stored key.
- Treat an empty key field on save as "preserve existing key".

## Testing And Acceptance

Backend tests:

- `GET /llm/platforms` returns presets and safe key metadata when no config file exists.
- Saving a new key stores it, while reading the config does not return plaintext.
- Saving with an empty key preserves the previous key.
- `PUT /llm/selection` sets active platform and active model.
- Local model create, update, and delete work.
- The OpenAI-compatible adapter builds `{baseUrl}/chat/completions` and sets `Authorization`.
- Model refresh merges models returned by `/models`.
- Model refresh failure preserves existing manual models.

Frontend acceptance:

- `大模型设置` opens the left/right modal.
- Platform search filters the left list.
- Selecting a platform updates the right panel without closing the modal.
- API key fields never reveal plaintext saved keys.
- Check, refresh models, add model, enable model, set default, and delete model provide clear feedback.
- `添加本地模型` opens the local model modal and saving adds an entry to the local model list.
- The modal remains usable without text overlap on desktop and narrower windows.

Integration acceptance:

- A saved active platform/model is used by downstream LLM workflows.
- Missing key/model/platform configuration produces explicit readiness errors.
- Dry-run mode allows configuration management but avoids accidental external calls.
- A mock OpenAI-compatible HTTP service proves `/models` and `/chat/completions` integration.

## Implementation Notes

Suggested modules:

- `llm_platforms.py`: Pydantic models, presets, safe serialization, persistence, and selection logic.
- `adapters/llm.py`: real OpenAI-compatible HTTP calls using active platform configuration.
- `main.py`: LLM platform API routes.
- `static/studio.html`: toolbar buttons and modal markup.
- `static/studio.css`: modal layout and responsive styling.
- `static/studio.js`: state management, API calls, modal interactions, model list rendering.

## Open Questions

- Exact default model lists may change over time and should be treated as editable presets rather than hard-coded truth.
- Whether to later use OS-level credential storage is outside this phase.
- Whether local Ollama or llama.cpp should be executed locally or treated as an OpenAI-compatible local service is future work.
