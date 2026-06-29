# Middle Picture-In-Picture Fill Design

## Goal

Adjust local video remix picture-in-picture timing so the digital-human main video remains visible at the beginning and end, while uploaded picture-in-picture materials fill the entire middle section.

## Timing Rule

- The main digital-human video remains the base layer for the full output.
- The first 8 seconds show only the digital human.
- The final 3 seconds show only the digital human.
- The middle window starts at `8.0` seconds and ends at `video_duration - 3.0` seconds.
- If one material is selected, it covers the whole middle window.
- If multiple materials are selected, each material receives an equal share of the middle window.
- If the video duration is unknown or not longer than 11 seconds, keep the existing safe fallback using a short middle insert schedule so rendering still works.

## Implementation

`LocalFFmpegVideoRemixEngine` should compute picture-in-picture overlay slots from the probed main-video duration and pass those slots into the ffmpeg filter graph. Existing image/video input handling, subtitles, background music, and output format stay unchanged.

## Verification

- Unit tests assert a 35-second main video with three materials produces overlays at `8.00-16.00`, `16.00-24.00`, and `24.00-32.00`.
- Unit tests assert a single material covers `8.00-32.00`.
- Existing remix, subtitle, and background music tests remain green.
