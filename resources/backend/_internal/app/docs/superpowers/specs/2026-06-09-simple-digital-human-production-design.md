# Simple Digital Human Production Design

## Goal

Make the digital human production page a simple three-step workflow. Provider API configuration, including Hifly token and base URL checks, belongs in the model settings area. The production page should not ask users to understand provider credentials, public media URLs, or low-level API calls.

## Current Problem

The `source-video-human` page currently mixes two responsibilities:

- Provider configuration and diagnostics: HIFLY token, public source video URL, public audio URL, token test, create avatar, create voice, generate video, one-click Hifly.
- Production workflow: upload a source video, create a voice profile, write a script, create/render a task, preview/download output.

This creates repeated controls and makes the page look like an API console instead of a digital human creation tool.

## Chosen Approach

Use approach A: move Hifly configuration to model settings and keep the production page as a three-step guided flow.

## Model Settings

The model settings page owns provider configuration.

- The digital human model selector keeps `Hifly API one-video digital human` as a selectable provider.
- Hifly credentials are configured in model settings, not on the production page:
  - `HIFLY_TOKEN`
  - `HIFLY_BASE_URL`
  - optional readiness/test action
- Provider status and missing items are surfaced there, such as missing token, disabled provider, or unavailable storage for real-mode media upload.

## Digital Human Production Page

The production page is organized into three visible steps.

### Step 1: Upload Video, Create Avatar And Clone Voice

Inputs:

- Project, defaulting to the current project.
- Digital human name.
- Source video file upload.
- Paid-call confirmation checkbox when the selected provider may charge.

Primary action:

- `Upload video and create avatar/voice`

Behavior:

- Upload the source video.
- Create or select a digital human record.
- Extract the source audio.
- Create the voice profile from the source video audio.
- When Hifly is the selected digital human model, run the Hifly avatar and voice flow through the configured provider settings.

No Hifly token, public source video URL, public audio URL, or provider debug buttons are shown here.

### Step 2: Write Script

Inputs:

- Script text.

Primary action:

- `Save script`

Behavior:

- Store the script in page state for the render step.
- Later script model generation can plug into this step, but it is not required for this change.

### Step 3: Select Avatar And Voice, Generate Video

Inputs:

- Digital human selector.
- Voice profile selector.
- Render quality selector.
- Paid-call confirmation checkbox, reused if needed.

Primary action:

- `Generate digital human video`

Behavior:

- Create a digital human task using the selected human, selected voice, and Step 2 script.
- Render through the selected provider path.
- Show progress, output preview, and downloads.

## Real-Mode Media URL Handling

The production page must not expose public media URL fields. Real Hifly calls still require reachable media URLs, so backend behavior should be:

- If object storage/upload publishing is configured, use it to obtain public video/audio URLs.
- If it is not configured, block the paid real call with a clear message telling the user to configure provider/storage in model settings.
- Dry-run mode remains usable without public URLs.

## UI Removal

Remove from the production page:

- Hifly provider card.
- `hiflyToken`
- `hiflyTitle`
- `hiflyVideoUrl`
- `hiflyAudioUrl`
- `hiflyTestTokenBtn`
- `hiflyCreateAvatarBtn`
- `hiflyCreateVoiceBtn`
- `hiflyGenerateBtn`
- `hiflyOneClickBtn`

Keep or replace with simplified step controls:

- `sourceVideoProject`
- digital human name input for Step 1
- `sourceVideoFile`
- `sourceVideoScript`
- `sourceVideoHumanSelect`
- voice profile selector for Step 3
- `sourceVideoRenderQuality`
- `sourceVideoConfirmPaid`
- `sourceVideoProgressBox`
- output audio/video/download controls

## JavaScript Behavior

Add or revise functions around the three business actions:

- Step 1 orchestrator: create/select human, upload source video, extract voice, create voice profile. For Hifly, delegate to existing Hifly backend endpoints without exposing provider fields.
- Step 2 action: validate and persist script text in state.
- Step 3 action: create/render the task using selected human and voice.

Remove UI bindings for the removed Hifly debug buttons. Existing backend endpoints can remain available for tests or advanced integrations, but they are no longer part of this page.

## Error Handling

Messages should speak in user workflow terms:

- Missing video: ask the user to upload a source video.
- Missing script: ask the user to write a script.
- Missing provider config: point to model settings.
- Paid call not confirmed: ask the user to tick the confirmation checkbox.
- Real Hifly media not publishable: ask the user to configure public storage/provider settings.

Avoid raw provider wording on the production page unless needed for support diagnostics.

## Testing

Update tests to assert:

- The production page has the three step labels and primary actions.
- Hifly credential/public URL fields are not present in production HTML.
- Removed Hifly debug buttons are not bound in production JS.
- Model settings/catalog still exposes Hifly as a digital human model option.
- The existing Hifly backend provider tests continue to pass.
- Full Python test suite, JS syntax check, compileall, and browser verification pass before completion.

## Out Of Scope

- Replacing Hifly backend endpoints.
- Building script generation in Step 2.
- Adding a new storage provider implementation beyond using existing object storage capability and clear blocking messages.
- Changing unrelated dashboard/navigation pages.
