# Local FFmpeg Video Remix Design

## Goal

Turn the existing video-remix task shell into a lightweight local ffmpeg renderer. It should generate usable MP4 outputs on the user's machine without calling cloud video APIs.

## Scope

- Use the selected/uploaded main video as the base.
- Use one uploaded image/video as a middle cutaway inside the digital-human talking video.
- Provide an option to add subtitles or render without subtitles.
- Generate `output_count` MP4 files under the remix task directory.
- Always run real local ffmpeg for this feature, regardless of the app-wide dry-run setting.
- Fail clearly if ffmpeg is unavailable or exits with an error.

## First-Version Editing Rules

- Target vertical short-video output: `1080x1920`, H.264 video, AAC audio.
- Each output is deterministic but varies asset order by output index.
- Main video occupies most of the timeline.
- Uploaded images/videos become one short full-frame middle insert while the main video's audio continues.
- Multiple outputs rotate the selected cutaway asset.
- Subtitle rendering is optional. When enabled, a simple bottom subtitle is burned into the MP4.
- No cloud calls, no AI scene understanding, no fake success path.

## Artifacts

Each remix task writes:

- `request.json`
- `status.json`
- `main/*`
- `assets/*`
- `outputs/remix_001.mp4`, etc.
- `remix_report.json`
- `ffmpeg_stdout.log`
- `ffmpeg_stderr.log`

## Verification

- Unit tests monkeypatch ffmpeg discovery and subprocess execution.
- API tests check that successful responses include completed outputs.
- API tests check that missing ffmpeg reports a clear error.
- Existing upload validation and filename-safety tests must continue to pass.
