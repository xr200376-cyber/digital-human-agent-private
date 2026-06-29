# LLM Provider Icons And Presets Design

## Goal

Make the cloud model platform list feel complete and recognizable by adding common China-facing OpenAI-compatible providers and showing each provider's official icon in the platform list.

## Provider Presets

Add these default platforms:

- 百度千帆
- 豆包/火山方舟
- 阿里百炼
- 腾讯混元
- 智谱 GLM
- Moonshot Kimi
- DeepSeek

Existing platforms remain: OpenAI, OpenAI O3, PPIO, Gemini, SiliconFlow, Gitee AI, GitHub Models, and Custom.

## API Shape

Each platform still uses the same OpenAI-compatible flow: API key, base URL, model ID, and optional model refresh. Defaults are only starting values; users can edit the API address and add model IDs manually.

## Icons

Provider icons are stored as local static files under `/provider-icons/`. The backend includes an `icon` path on each platform record. The frontend renders the icon before the platform name in the left platform list and in the detail header.

## Desktop Sync

After source verification, copy updated backend/static files and icon assets to `G:/dist/desktop-cloud-providers-v2/win-unpacked/resources/app`, then restart the desktop app/backend and verify `http://127.0.0.1:8080/llm/platforms`.
