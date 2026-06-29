# Simple Desktop Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Simplify the desktop sidebar and model page wording so the main workflow has fewer, clearer entry points.

**Architecture:** Keep existing view sections and API behavior intact. Change only the visible sidebar labels, model page labels, and JS active-nav grouping so internal workflow views still work but no longer appear as top-level navigation.

**Tech Stack:** Static HTML/CSS/JavaScript served by FastAPI, pytest static assertions, desktop unpacked resource sync.

---

### Task 1: Add Static UI Regression Tests

**Files:**
- Modify: `G:/tests/test_model_center.py`

- [ ] **Step 1: Write failing tests**

Add assertions that the sidebar contains only the primary labels and does not expose intermediate page labels. Add assertions that model-center is presented as "模型设置" with simplified action labels.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest G:\tests\test_model_center.py::test_studio_exposes_model_center_ui -q`

Expected: FAIL because the old sidebar still includes intermediate labels and the model page still says "模型选择", "大模型设置", and "添加本地模型".

### Task 2: Simplify Sidebar and Model Page Markup

**Files:**
- Modify: `G:/app/static/studio.html`

- [ ] **Step 1: Replace sidebar nav buttons**

Keep only these top-level buttons: 工作台, 模型设置, 项目, 数字人制作, 视频生产, 任务与发布, 环境检查.

- [ ] **Step 2: Rename model page actions**

Change model-center heading to "模型设置"; change actions to "刷新", "配置云模型", and "本地模型".

- [ ] **Step 3: Run static UI test**

Run: `pytest G:\tests\test_model_center.py::test_studio_exposes_model_center_ui -q`

Expected: PASS.

### Task 3: Preserve Active Sidebar Grouping

**Files:**
- Modify: `G:/app/static/studio.js`
- Modify: `G:/tests/test_model_center.py`

- [ ] **Step 1: Add JS grouping assertions**

Assert the JS includes a `navGroupFor` function and maps internal pages to the simplified primary nav groups.

- [ ] **Step 2: Implement grouping**

Use `navGroupFor(viewName)` inside `switchView()` so internal pages highlight their parent sidebar item.

- [ ] **Step 3: Run tests**

Run: `pytest G:\tests\test_model_center.py -q`

Expected: PASS.

### Task 4: Verify and Sync Desktop Package

**Files:**
- Copy updated static files from `G:/app/static` to `G:/dist/desktop-cloud-providers-v2/win-unpacked/resources/app/static`

- [ ] **Step 1: Run verification**

Run:

```powershell
pytest G:\tests\test_model_center.py -q
node --check G:\app\static\studio.js
```

- [ ] **Step 2: Sync desktop resources**

Copy `studio.html`, `studio.css`, and `studio.js` to the unpacked desktop app resource folder.

- [ ] **Step 3: Restart and verify desktop URL**

Restart the desktop app/backend, then check `http://127.0.0.1:8080/` contains the simplified labels and no hidden intermediate labels in the sidebar.
