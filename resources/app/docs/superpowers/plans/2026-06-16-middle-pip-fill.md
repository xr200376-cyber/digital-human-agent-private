# Middle Picture-In-Picture Fill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make picture-in-picture materials fill the entire middle section between the first 8 seconds and the final 3 seconds of the digital-human video.

**Architecture:** Keep `LocalFFmpegVideoRemixEngine` as the single local ffmpeg adapter. Add a small scheduling helper that receives selected assets and the main-video duration, then emits start/end slots for the overlay filters.

**Tech Stack:** Python 3.11, pytest, ffmpeg filter graph strings, FastAPI desktop runtime.

---

### Task 1: Lock The New Timing Rule With Tests

**Files:**
- Modify: `G:\tests\test_video_remix_workflow.py`

- [ ] **Step 1: Write failing tests**

Add tests that call `_build_command(..., main_video_duration_seconds=35.0)` and assert three materials split the middle window into `8.00-16.00`, `16.00-24.00`, and `24.00-32.00`; also assert one material covers `8.00-32.00`.

- [ ] **Step 2: Run focused tests**

Run: `python -m pytest -q G:\tests\test_video_remix_workflow.py::test_video_remix_places_materials_back_to_back G:\tests\test_video_remix_workflow.py::test_video_remix_single_material_fills_middle_window`

Expected: fail because the current implementation still starts at 6 seconds and uses fixed 2.5-second slots.

### Task 2: Implement Middle Fill Scheduling

**Files:**
- Modify: `G:\app\video_remix.py`

- [ ] **Step 1: Pass duration into command building**

Probe `main_video` duration once per output and pass it to `_build_command`.

- [ ] **Step 2: Add slot helper**

Add a helper that returns equal overlay slots for known durations longer than 11 seconds and safe fallback slots otherwise.

- [ ] **Step 3: Use slots in overlay filters**

Replace the fixed `6.0 + index` / `2.5` logic with the helper output.

- [ ] **Step 4: Update strategy report**

Record `head_seconds: 8.0`, `tail_seconds: 3.0`, and `mode: digital_human_with_middle_pip_fill`.

### Task 3: Verify And Sync

**Files:**
- Copy: `G:\app\video_remix.py` to `G:\dist\desktop-cloud-providers-v2\win-unpacked\resources\app\video_remix.py`

- [ ] **Step 1: Run focused and full remix tests**

Run: `python -m pytest -q G:\tests\test_video_remix_workflow.py`

Expected: all tests pass.

- [ ] **Step 2: Compile changed module**

Run: `python -m compileall G:\app\video_remix.py`

Expected: exit 0.

- [ ] **Step 3: Sync desktop runtime**

Copy the changed module into the packaged runtime and restart the 8080 backend.

- [ ] **Step 4: Verify runtime health**

Run: `Invoke-RestMethod http://127.0.0.1:8080/health`

Expected: `status` is `ok`.
