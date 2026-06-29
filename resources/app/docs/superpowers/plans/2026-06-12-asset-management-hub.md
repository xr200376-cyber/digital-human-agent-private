# Asset Management Hub Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the user-facing project page with an asset-management hub for cloning avatar, cloning voice, and rewriting scripts.

**Architecture:** Keep the existing default project plumbing intact for API compatibility, but hide project creation/selection from the user. Add three card-style entry points that navigate to existing feature views, and restyle the voice page into a simple create/history layout matching the provided reference.

**Tech Stack:** FastAPI static HTML, vanilla JavaScript, CSS, pytest, node syntax check.

---

### Task 1: Tests

**Files:**
- Modify: `G:\tests\test_digital_human_studio_pages_14.py`
- Modify: `G:\tests\test_chinese_consumer_localization.py`

- [ ] Add assertions that the old project page labels are gone.
- [ ] Add assertions for `资产管理`, `克隆形象`, `克隆声音`, `文案改写`, and card jump targets.
- [ ] Add assertions that the voice page uses `创建声音` and `历史声音`.
- [ ] Run the focused tests and confirm they fail before implementation.

### Task 2: Static UI

**Files:**
- Modify: `G:\app\static\studio.html`
- Modify: `G:\app\static\studio.css`

- [ ] Rename the `项目` nav item to `资产管理`.
- [ ] Replace the old `projects` view with a three-card asset hub.
- [ ] Preserve hidden `projectName`, `projectId`, and `projectSelect` controls so existing JavaScript keeps a default project.
- [ ] Restyle the voice page into a left create panel and right history panel.
- [ ] Bump `studio.css` and `studio.js` cache versions.

### Task 3: Navigation

**Files:**
- Modify: `G:\app\static\studio.js`

- [ ] Make asset hub cards navigate with `data-go` using the existing click binding.
- [ ] Ensure `projects` no longer refreshes a visible project list.
- [ ] Keep initialization setting `project_demo`.

### Task 4: Verification and Desktop Sync

**Files:**
- Copy changed app files into `G:\dist\desktop-cloud-providers-v2\win-unpacked\resources\app`

- [ ] Run focused pytest files.
- [ ] Run `node --check G:\app\static\studio.js`.
- [ ] Run `python -m compileall G:\app\main.py`.
- [ ] Restart desktop backend.
- [ ] Verify served HTML contains the new asset hub and no `项目空间`.
