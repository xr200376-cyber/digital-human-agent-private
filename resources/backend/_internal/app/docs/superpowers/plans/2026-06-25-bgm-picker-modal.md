# BGM Picker Modal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the compact BGM dropdown flow with a customer-friendly modal picker, import the user-provided WeChat BGM tracks, and preserve adjustable background-music volume.

**Architecture:** Keep the existing `/bgm/library` and `/bgm/{filename}` backend API. Update the manifest and static assets so the backend naturally exposes the new tracks. Add modal-only UI behavior in `studio.html`, `studio.css`, and `studio.js`; final export continues using the existing `/source-video/finalize` payload with `background_music_id` plus `background_music_volume`.

**Tech Stack:** FastAPI static file serving, vanilla HTML/CSS/JavaScript, Node syntax check, Python compile/test commands.

---

### Task 1: Backend Manifest And Volume Payload Tests

**Files:**
- Modify: `G:\tests\test_bgm_library.py`

- [ ] **Step 1: Write failing tests**

Add tests that assert `/bgm/library` returns the new imported BGM names and that the remix/finalize schema still accepts a `background_music_volume` value.

- [ ] **Step 2: Run tests to verify RED**

Run: `python -m pytest -q G:\tests\test_bgm_library.py`

Expected before implementation: at least one assertion fails because the manifest still contains only the old tracks.

- [ ] **Step 3: Import BGM and update manifest**

Copy the 19 WeChat MP3 files into `G:\app\static\bgm` with stable filenames and rewrite `G:\app\static\bgm\bgm_manifest.json` in UTF-8.

- [ ] **Step 4: Run tests to verify GREEN**

Run: `python -m pytest -q G:\tests\test_bgm_library.py`

Expected after implementation: tests pass.

### Task 2: BGM Modal UI

**Files:**
- Modify: `G:\app\static\studio.html`
- Modify: `G:\app\static\studio.css`
- Modify: `G:\app\static\studio.js`

- [ ] **Step 1: Preserve the hidden select for compatibility**

Keep `#sourceVideoBgmSelect` in the DOM so existing payload code can continue to read the selected track id, but hide it from the customer-facing card.

- [ ] **Step 2: Add visible modal entry and volume control**

Add a “选择配乐” button, current BGM display, and a volume slider labeled “配乐音量”. The slider should map 0-100% to `background_music_volume` 0-1.

- [ ] **Step 3: Add modal markup**

Add a modal that lists all available tracks, with each row showing title, mood/size if available, “试听”, and “选择”.

- [ ] **Step 4: Implement modal behavior**

Add JS functions for opening/closing the modal, rendering rows, selecting a track, previewing the selected row, updating the hidden select, and refreshing the visible current selection.

- [ ] **Step 5: Update final export payload**

Change `sourceVideoBgmPayload()` so it uses the slider value instead of the fixed `0.18`.

### Task 3: Runtime And Delivery Sync

**Files/Folders:**
- Source: `G:\app`
- Runtime: `G:\dist\desktop-cloud-providers-v2\win-unpacked\resources\app`
- Packaged backend: `G:\dist\desktop-cloud-providers-v2\win-unpacked\resources\backend\_internal\app`
- Customer package: `G:\release\customer_package_20260625\...\`

- [ ] **Step 1: Sync static files and BGM assets**

Copy changed `studio.html`, `studio.css`, `studio.js`, and `static\bgm` into runtime, backend internal app, and expanded customer package when those folders exist.

- [ ] **Step 2: Rebuild customer zips**

Rebuild the portable and installer zip files that contain the expanded customer package.

- [ ] **Step 3: Verify**

Run:

```powershell
python -m pytest -q G:\tests\test_bgm_library.py
node --check G:\app\static\studio.js
python -m compileall G:\app\main.py
Invoke-RestMethod http://127.0.0.1:8080/bgm/library
```

Expected: tests pass, JS syntax is valid, Python compiles, and `/bgm/library` returns the imported tracks.
