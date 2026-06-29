# Replace BGM Library Design

## Goal

Replace the built-in background music choices with the five MP3 files supplied by the user.

## Behavior

The background music dropdown should show only:

- 迈巴赫进行曲
- 时尚动感
- 大气震撼
- 野马进行曲
- 欢快音频1

The previous bundled tracks are removed from the manifest and no longer appear in `/bgm/library`.

## Implementation

- Copy the supplied MP3 files into `app/static/bgm/` with ASCII filenames.
- Rewrite `app/static/bgm/bgm_manifest.json` so the five new tracks are the only available tracks.
- Update tests that depend on the old track IDs.
- Sync the same `static/bgm` folder into the packaged desktop runtime.

## Verification

- `/bgm/library` returns exactly the five new tracks and marks them available.
- Video remix can use one of the new track IDs.
- The running desktop service on port 8080 serves the new manifest.
