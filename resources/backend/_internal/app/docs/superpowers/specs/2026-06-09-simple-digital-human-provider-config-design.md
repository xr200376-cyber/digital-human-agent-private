# Simple Digital Human Provider Config

## Goal

Model settings should expose one simple digital-human provider configuration form:

- Platform
- API address
- API Key

Saving this form refreshes model detection, but it does not automatically change the selected digital-human model. The user still chooses the active model from the existing "digital human model" select and can run validation from that area.

## Behavior

- The provider configuration card replaces the Hifly-only card.
- The form maps the selected platform to existing desktop setting fields.
- A blank API Key keeps the saved key for that provider.
- After saving, the model catalog is refreshed so the upper model select can show the provider's detected status.
- Saving provider config must not call the model selection endpoint or force `digital_human_model`.
- The production page remains focused on upload video, script, choose human/voice, and render video.

## Scope

The UI remains intentionally minimal. Provider-specific advanced fields such as figure id, replica id, region, width, or polling settings are not shown in this card. If a provider still needs official required fields for a real paid call, the existing validation flow reports those blockers.
