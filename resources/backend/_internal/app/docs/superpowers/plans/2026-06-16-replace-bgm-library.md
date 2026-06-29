# Replace BGM Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the old built-in BGM options with the five user-supplied MP3 files.

**Architecture:** The BGM library is manifest-driven through `app/static/bgm/bgm_manifest.json`; `/bgm/library` reads the manifest and checks file availability. No frontend behavior changes are needed because the dropdown already loads this endpoint.

**Tech Stack:** FastAPI static file endpoints, JSON manifest, pytest, vanilla JS frontend.

---

### Task 1: Update BGM Expectations

**Files:**
- Modify: `G:\tests\test_video_remix_workflow.py`

- [ ] **Step 1: Write the failing test**

Assert `/bgm/library` returns exactly the new five track IDs and titles, and update the remix request to use `maybach-march`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest -q G:\tests\test_video_remix_workflow.py::test_bgm_library_lists_bundled_tracks G:\tests\test_video_remix_workflow.py::test_video_remix_mixes_selected_background_music`

Expected: FAIL because the manifest still contains the old `carefree` library.

- [ ] **Step 3: Replace assets and manifest**

Copy the five supplied MP3 files into `G:\app\static\bgm` using ASCII filenames and rewrite the manifest with the new tracks only.

- [ ] **Step 4: Run focused tests**

Run the same pytest command again.

Expected: PASS.

### Task 2: Sync Runtime And Verify

**Files:**
- Modify: `G:\dist\desktop-cloud-providers-v2\win-unpacked\resources\app\static\bgm\*`

- [ ] **Step 1: Sync BGM folder**

Mirror `G:\app\static\bgm` to the packaged runtime.

- [ ] **Step 2: Restart backend**

Restart the desktop backend on port 8080.

- [ ] **Step 3: Verify served manifest**

Run: `Invoke-RestMethod http://127.0.0.1:8080/bgm/library`

Expected: exactly the five new tracks with `available: true`.
