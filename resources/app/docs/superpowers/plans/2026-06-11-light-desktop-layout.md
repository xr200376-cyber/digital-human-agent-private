# Light Desktop Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep Aivo's current light theme while changing the studio UI into a simpler desktop-app layout modeled after the provided AivoClaw reference.

**Architecture:** This is a static frontend layout change. `studio.html` supplies semantic layout wrappers while preserving existing element IDs, `studio.css` owns the visual shell and responsive behavior, and tests assert the intended structure.

**Tech Stack:** FastAPI static HTML, vanilla JavaScript, CSS, pytest with FastAPI TestClient.

---

### Task 1: Layout Regression Tests

**Files:**
- Modify: `G:\tests\test_digital_human_studio_pages_14.py`

- [ ] **Step 1: Add the failing layout test**

Add a test that fetches `/` and asserts these structural markers:

```python
def test_studio_uses_light_desktop_layout(tmp_path: Path):
    with _client(tmp_path) as client:
        response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert 'class="app-shell"' in html
    assert 'class="app-sidebar"' in html
    assert 'class="app-content"' in html
    assert 'class="production-layout"' in html
    assert 'class="production-main"' in html
    assert 'class="production-aside"' in html
    assert "/studio.js?v=20260611-light-desktop-layout" in html
```

- [ ] **Step 2: Verify the test fails**

Run:

```powershell
python -m pytest -q G:\tests\test_digital_human_studio_pages_14.py::test_studio_uses_light_desktop_layout
```

Expected: FAIL because the new wrapper classes are not present yet.

### Task 2: HTML Structure

**Files:**
- Modify: `G:\app\static\studio.html`

- [ ] **Step 1: Add desktop shell classes without changing IDs**

Change the top-level structure so `<main class="shell">` becomes `<main class="shell app-shell">`, sidebar becomes `class="sidebar app-sidebar"`, and view stack becomes `class="view-stack app-content"`.

- [ ] **Step 2: Group production pages into two-column regions**

For `source-video-human` and `create-task`, wrap existing panels into:

```html
<div class="production-layout">
  <div class="production-main">...</div>
  <aside class="production-aside">...</aside>
</div>
```

Move workflow inputs into `production-main`; move preview/status/output panels into `production-aside`.

- [ ] **Step 3: Update cache buster**

Change the script URL to:

```html
<script src="/studio.js?v=20260611-light-desktop-layout"></script>
```

### Task 3: CSS Desktop Layout

**Files:**
- Modify: `G:\app\static\studio.css`

- [ ] **Step 1: Change shell sizing**

Make the app fill the desktop window, with a compact top bar and `92px + 1fr` body grid.

- [ ] **Step 2: Restyle sidebar**

Make the sidebar full-height, narrow, icon-label-like, and still light themed. Preserve active teal state.

- [ ] **Step 3: Add production layout CSS**

Add `.production-layout`, `.production-main`, and `.production-aside` grid rules. The production pages should use a narrower left workflow column and a larger right preview/status column like the reference product.

- [ ] **Step 4: Responsive fallback**

At `max-width: 960px`, collapse app shell and production layouts to one column.

### Task 4: Runtime Sync And Verification

**Files:**
- Copy to: `G:\dist\desktop-cloud-providers-v2\win-unpacked\resources\app\static\studio.html`
- Copy to: `G:\dist\desktop-cloud-providers-v2\win-unpacked\resources\app\static\studio.css`
- Copy to: `G:\dist\desktop-cloud-providers-v2\win-unpacked\resources\app\static\studio.js`

- [ ] **Step 1: Run tests**

```powershell
python -m pytest -q G:\tests\test_digital_human_studio_pages_14.py G:\tests\test_video_remix_workflow.py
node --check G:\app\static\studio.js
```

- [ ] **Step 2: Sync runtime files**

Copy the modified static files to the packaged runtime app folder.

- [ ] **Step 3: Verify served app**

Fetch `http://127.0.0.1:8080/` and assert it contains the new classes and script version.

- [ ] **Step 4: Browser visual check**

Open the running app in the in-app browser, inspect `数字人制作` and `视频混剪`, and confirm the reference-style structure is visible.
