# Simple Video Remix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the old `视频生产` page with a very simple `视频混剪` workflow: select or upload a main video, upload remix materials, choose 1/3/5 outputs, and create a clear remix task.

**Architecture:** Keep the digital-human production flow untouched. Add a small remix API that stores uploaded assets and creates a `video_remix_tasks` record with a clear "task created, render engine not connected" message, then replace the existing create-task UI with a minimal remix form that calls this API.

**Tech Stack:** FastAPI, Pydantic, local file storage under `storage_dir`, vanilla HTML/CSS/JavaScript, pytest `TestClient`.

---

## File Map

- Modify `G:\app\schemas.py`: add request/response schemas for video remix uploads and tasks.
- Modify `G:\app\main.py`: add `/video-remix/main-videos` and `/video-remix/tasks` endpoints, plus small upload helper functions.
- Modify `G:\app\static\studio.html`: rename nav/page and replace the create-video form with the simple remix form.
- Modify `G:\app\static\studio.js`: add remix state, main-video refresh, upload payload conversion, output count selection, and task creation.
- Modify `G:\tests\test_digital_human_studio_pages_14.py`: update page expectations from video production to video remix.
- Create `G:\tests\test_video_remix_workflow.py`: cover remix API validation and successful local task creation.
- Copy changed app files from `G:\app` to `G:\dist\desktop-cloud-providers-v2\win-unpacked\resources\app` before verifying the desktop runtime.

Current workspace note: `G:\app` is not a git repository, so commit steps are replaced by file-level verification.

---

### Task 1: Add Failing Tests For The Simple Remix Surface

**Files:**
- Modify: `G:\tests\test_digital_human_studio_pages_14.py`
- Create: `G:\tests\test_video_remix_workflow.py`

- [ ] **Step 1: Update the studio page test**

Replace the `create-task` labels in `test_studio_homepage_exposes_sprint_14_pages` and add a focused test that asserts the old script/task controls are gone from the remix page.

```python
def test_studio_homepage_exposes_sprint_14_pages(tmp_path: Path):
    with _client(tmp_path) as client:
        response = client.get("/")

    assert response.status_code == 200
    html = response.text

    primary_nav = {
        "dashboard": "工作台",
        "projects": "项目",
        "source-video-human": "数字人制作",
        "create-task": "视频混剪",
        "job-center": "任务与发布",
        "readiness": "环境检查",
    }
    for view, label in primary_nav.items():
        assert f'data-nav="{view}"' in html
        assert label in html

    expected_pages = {
        "dashboard": "工作台",
        "projects": "项目空间",
        "digital-humans": "数字人列表",
        "digital-human-detail": "数字人详情",
        "source-video-human": "源视频数字人",
        "voice-profiles": "声音档案",
        "create-task": "视频混剪",
        "task-detail": "任务详情",
        "results": "结果下载",
        "readiness": "环境检查",
    }
    for view, label in expected_pages.items():
        assert f'data-view="{view}"' in html
        assert label in html

    for forbidden_framework in ["react", "vue", "next.js", "angular", "svelte"]:
        assert forbidden_framework not in html.lower()


def test_video_remix_page_keeps_only_simple_controls(tmp_path: Path):
    with _client(tmp_path) as client:
        response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert "视频混剪" in html
    assert "remixMainVideoSelect" in html
    assert "remixMainVideoFile" in html
    assert "remixAssetFiles" in html
    assert "videoRemixGenerateBtn" in html
    assert "data-remix-count=\"1\"" in html
    assert "data-remix-count=\"3\"" in html
    assert "data-remix-count=\"5\"" in html
    assert "视频主题" not in html
    assert "需要脚本审核" not in html
    assert "templateInfoBox" not in html
    assert "generateScriptBtn" not in html
    assert "reviewBtn" not in html
```

- [ ] **Step 2: Add API workflow tests**

Create `G:\tests\test_video_remix_workflow.py`:

```python
import base64
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app, get_settings
from app.settings import Settings


def _client(tmp_path: Path) -> TestClient:
    app.dependency_overrides.clear()
    app.dependency_overrides[get_settings] = lambda: Settings(dry_run=True, storage_dir=tmp_path)
    return TestClient(app)


def _b64(payload: bytes) -> str:
    return base64.b64encode(payload).decode("ascii")


def test_video_remix_requires_main_video(tmp_path: Path):
    with _client(tmp_path) as client:
        response = client.post(
            "/video-remix/tasks",
            json={
                "project_id": "project_demo",
                "assets": [
                    {
                        "filename": "product.png",
                        "content_type": "image/png",
                        "content_base64": _b64(b"fake-image"),
                    }
                ],
                "output_count": 1,
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "请先选择或上传主视频。"


def test_video_remix_creates_local_task_record(tmp_path: Path):
    with _client(tmp_path) as client:
        response = client.post(
            "/video-remix/tasks",
            json={
                "project_id": "project_demo",
                "main_video": {
                    "filename": "main.mp4",
                    "content_type": "video/mp4",
                    "content_base64": _b64(b"fake-video"),
                },
                "assets": [
                    {
                        "filename": "product.png",
                        "content_type": "image/png",
                        "content_base64": _b64(b"fake-image"),
                    },
                    {
                        "filename": "case.mp4",
                        "content_type": "video/mp4",
                        "content_base64": _b64(b"fake-case-video"),
                    },
                ],
                "output_count": 3,
            },
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["remix_task_id"].startswith("remix_")
    assert body["status"] == "created"
    assert body["output_count"] == 3
    assert body["asset_count"] == 2
    assert body["message"] == "混剪任务已创建，混剪渲染引擎待接入。"

    task_dir = Path(body["task_dir"])
    assert (task_dir / "main" / "main.mp4").exists()
    assert (task_dir / "assets" / "product.png").exists()
    assert (task_dir / "assets" / "case.mp4").exists()
    assert (task_dir / "status.json").exists()
```

- [ ] **Step 3: Run tests and verify they fail**

Run:

```powershell
pytest -q G:\tests\test_digital_human_studio_pages_14.py G:\tests\test_video_remix_workflow.py
```

Expected: FAIL because the remix schemas, API endpoints, and UI IDs do not exist yet.

---

### Task 2: Add Remix API Schemas And Local Task Endpoint

**Files:**
- Modify: `G:\app\schemas.py`
- Modify: `G:\app\main.py`
- Test: `G:\tests\test_video_remix_workflow.py`

- [ ] **Step 1: Add schemas**

In `G:\app\schemas.py`, add these classes after `SourceVideoUploadRequest`:

```python
class VideoRemixAssetUpload(BaseModel):
    filename: str = "remix_asset"
    content_type: str = "application/octet-stream"
    content_base64: str


class VideoRemixTaskRequest(BaseModel):
    project_id: str = "project_demo"
    main_video_path: str | None = None
    main_video: VideoRemixAssetUpload | None = None
    assets: list[VideoRemixAssetUpload] = Field(default_factory=list, min_length=1, max_length=30)
    output_count: int = Field(1, ge=1, le=5)


class VideoRemixTaskResponse(BaseModel):
    remix_task_id: str
    status: str
    message: str
    task_dir: str
    main_video_path: str
    asset_count: int
    output_count: int
```

- [ ] **Step 2: Import schemas and uuid**

In `G:\app\main.py`, add `uuid4` and the new schemas:

```python
from uuid import uuid4
```

Add these names to the `from app.schemas import (...)` block:

```python
    VideoRemixAssetUpload,
    VideoRemixTaskRequest,
    VideoRemixTaskResponse,
```

- [ ] **Step 3: Add helper functions**

Add these helpers near `_safe_upload_filename`:

```python
def _decode_remix_upload(
    upload: VideoRemixAssetUpload,
    *,
    label: str,
    allowed_prefixes: tuple[str, ...],
) -> tuple[str, str, bytes]:
    content_type = (upload.content_type or "application/octet-stream").lower()
    if not any(content_type.startswith(prefix) for prefix in allowed_prefixes):
        allowed_text = "、".join(prefix.rstrip("/") for prefix in allowed_prefixes)
        raise HTTPException(status_code=400, detail=f"{label}只支持 {allowed_text} 文件。")
    try:
        file_bytes = base64.b64decode(upload.content_base64, validate=True)
    except Exception as exc:  # noqa: BLE001 - user upload payload can be malformed.
        raise HTTPException(status_code=400, detail=f"{label}文件内容不是有效的 base64。") from exc
    if not file_bytes:
        raise HTTPException(status_code=400, detail=f"{label}文件不能为空。")
    filename = _safe_upload_filename(upload.filename or label)
    return filename, content_type, file_bytes


def _write_remix_upload(
    root: Path,
    upload: VideoRemixAssetUpload,
    *,
    label: str,
    allowed_prefixes: tuple[str, ...],
) -> dict[str, str]:
    filename, content_type, file_bytes = _decode_remix_upload(
        upload,
        label=label,
        allowed_prefixes=allowed_prefixes,
    )
    path = root / filename
    path.write_bytes(file_bytes)
    return {"filename": filename, "content_type": content_type, "path": str(path)}
```

- [ ] **Step 4: Add endpoints**

Add these endpoints near the existing task endpoints in `G:\app\main.py`:

```python
@app.get("/video-remix/main-videos")
def list_video_remix_main_videos(
    project_id: str | None = None,
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    tasks_root = settings.storage_dir / "tasks"
    videos: list[dict[str, str]] = []
    if not tasks_root.exists():
        return {"videos": videos}
    for task_json in sorted(tasks_root.glob("*/task.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            task_data = read_json(task_json)
        except Exception:
            continue
        request_data = task_data.get("request") if isinstance(task_data.get("request"), dict) else {}
        if project_id and request_data.get("project_id") not in {project_id, None}:
            continue
        artifacts = task_data.get("artifacts") if isinstance(task_data.get("artifacts"), dict) else {}
        for artifact_key in ("final_video", "lip_synced_video", "avatar_video", "avatar_base_video"):
            path = _safe_storage_file(settings, str(artifacts.get(artifact_key)) if artifacts.get(artifact_key) else None)
            if path:
                task_id = task_json.parent.name
                videos.append(
                    {
                        "id": task_id,
                        "label": f"{request_data.get('topic') or '数字人视频'} ({task_id})",
                        "path": str(path),
                        "artifact": artifact_key,
                    }
                )
                break
    return {"videos": videos[:50]}


@app.post("/video-remix/tasks", response_model=VideoRemixTaskResponse)
def create_video_remix_task(
    request: VideoRemixTaskRequest,
    settings: Settings = Depends(get_settings),
) -> VideoRemixTaskResponse:
    if not request.main_video_path and request.main_video is None:
        raise HTTPException(status_code=400, detail="请先选择或上传主视频。")
    if not request.assets:
        raise HTTPException(status_code=400, detail="请先上传至少一个混剪素材。")

    remix_task_id = "remix_" + uuid4().hex
    task_dir = ensure_dir(settings.storage_dir / "video_remix_tasks" / remix_task_id)
    main_dir = ensure_dir(task_dir / "main")
    assets_dir = ensure_dir(task_dir / "assets")

    if request.main_video is not None:
        main_record = _write_remix_upload(
            main_dir,
            request.main_video,
            label="主视频",
            allowed_prefixes=("video/",),
        )
    else:
        selected = _safe_storage_file(settings, request.main_video_path)
        if selected is None:
            raise HTTPException(status_code=400, detail="选择的主视频不可用，请重新选择或上传。")
        main_record = {
            "filename": selected.name,
            "content_type": mimetypes.guess_type(selected.name)[0] or "video/mp4",
            "path": str(selected),
        }

    asset_records = [
        _write_remix_upload(
            assets_dir,
            asset,
            label="混剪素材",
            allowed_prefixes=("image/", "video/"),
        )
        for asset in request.assets
    ]
    message = "混剪任务已创建，混剪渲染引擎待接入。"
    status_payload = {
        "remix_task_id": remix_task_id,
        "status": "created",
        "message": message,
        "project_id": request.project_id,
        "main_video": main_record,
        "assets": asset_records,
        "output_count": request.output_count,
        "defaults": {
            "aspect_ratio": "9:16",
            "subtitles": "reuse_or_asr",
            "music": "default_light_music",
            "intro_outro": True,
            "quality": "stable_default",
            "format": "mp4",
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    write_json(task_dir / "request.json", request.model_dump(mode="json"))
    write_json(task_dir / "status.json", status_payload)
    append_audit_event(
        settings.storage_dir,
        action="video_remix.task_created",
        project_id=request.project_id,
        details={"remix_task_id": remix_task_id, "asset_count": len(asset_records), "output_count": request.output_count},
    )
    return VideoRemixTaskResponse(
        remix_task_id=remix_task_id,
        status="created",
        message=message,
        task_dir=str(task_dir),
        main_video_path=main_record["path"],
        asset_count=len(asset_records),
        output_count=request.output_count,
    )
```

- [ ] **Step 5: Run API tests**

Run:

```powershell
pytest -q G:\tests\test_video_remix_workflow.py
```

Expected: PASS.

---

### Task 3: Replace The Old Video Production UI With Simple Remix UI

**Files:**
- Modify: `G:\app\static\studio.html`
- Modify: `G:\app\static\studio.js`
- Test: `G:\tests\test_digital_human_studio_pages_14.py`

- [ ] **Step 1: Update HTML nav and page**

In `G:\app\static\studio.html`, change the nav label:

```html
<button class="nav-item" type="button" data-nav="create-task">视频混剪</button>
```

Replace the entire `<section class="view" data-view="create-task">...</section>` with:

```html
<section class="view" data-view="create-task">
  <div class="page-head">
    <h2>视频混剪</h2>
    <button id="videoRemixGenerateBtn" type="button">一键生成混剪视频</button>
  </div>
  <section class="panel">
    <h3>主视频</h3>
    <div class="row">
      <label>
        选择已生成数字人视频
        <select id="remixMainVideoSelect"></select>
      </label>
      <label>
        上传本地视频
        <input id="remixMainVideoFile" type="file" accept="video/*" />
      </label>
    </div>
    <div class="actions compact">
      <button id="refreshRemixMainVideosBtn" type="button">刷新主视频</button>
    </div>
  </section>
  <section class="panel">
    <h3>混剪素材</h3>
    <label>
      上传图片/视频素材
      <input id="remixAssetFiles" type="file" accept="image/*,video/*" multiple />
    </label>
  </section>
  <section class="panel">
    <h3>生成数量</h3>
    <div class="actions compact">
      <button type="button" data-remix-count="1">生成 1 条</button>
      <button type="button" data-remix-count="3">生成 3 条</button>
      <button type="button" data-remix-count="5">生成 5 条</button>
    </div>
  </section>
  <section class="panel wide">
    <h3>混剪状态</h3>
    <pre id="videoRemixStatusBox" class="json-box">选择主视频并上传素材后，点击一键生成混剪视频。</pre>
  </section>
</section>
```

Update the script cache buster at the bottom:

```html
<script src="/studio.js?v=20260611-video-remix"></script>
```

- [ ] **Step 2: Add remix state**

In `G:\app\static\studio.js`, extend the `state` object:

```javascript
  remixMainVideos: [],
  remixOutputCount: 1,
```

- [ ] **Step 3: Add remix helper functions**

Add these functions near the existing upload helpers:

```javascript
function setVideoRemixCount(count) {
  state.remixOutputCount = Number(count) || 1;
  for (const button of document.querySelectorAll("[data-remix-count]")) {
    button.classList.toggle("active", button.dataset.remixCount === String(state.remixOutputCount));
  }
  writeJson("videoRemixStatusBox", {
    status: "ready",
    output_count: state.remixOutputCount,
  });
}

async function refreshVideoRemixMainVideos() {
  const projectId = state.projectId || value("projectId") || "project_demo";
  const body = await api(`/video-remix/main-videos?project_id=${encodeURIComponent(projectId)}`);
  state.remixMainVideos = body.videos || [];
  fillSelect($("remixMainVideoSelect"), state.remixMainVideos, "path", "label", "选择已生成数字人视频");
  writeJson("videoRemixStatusBox", {
    status: "loaded",
    videos: state.remixMainVideos.length,
  });
}

async function fileUploadPayload(file) {
  return {
    filename: file.name || "upload.bin",
    content_type: file.type || "application/octet-stream",
    content_base64: await readFileAsBase64(file),
  };
}

async function createVideoRemixTask() {
  requireProject();
  const generateButton = $("videoRemixGenerateBtn");
  const selectedPath = value("remixMainVideoSelect");
  const mainFileInput = $("remixMainVideoFile");
  const mainFile = mainFileInput && mainFileInput.files ? mainFileInput.files[0] : null;
  const assetInput = $("remixAssetFiles");
  const assetFiles = assetInput && assetInput.files ? Array.from(assetInput.files) : [];

  if (!selectedPath && !mainFile) throw new Error("请先选择或上传主视频。");
  if (!assetFiles.length) throw new Error("请先上传至少一个混剪素材。");

  if (generateButton) generateButton.disabled = true;
  try {
    const payload = {
      project_id: state.projectId || value("projectId") || "project_demo",
      main_video_path: mainFile ? "" : selectedPath,
      main_video: mainFile ? await fileUploadPayload(mainFile) : null,
      assets: [],
      output_count: state.remixOutputCount || 1,
    };
    for (const file of assetFiles) {
      payload.assets.push(await fileUploadPayload(file));
    }
    const body = await api("/video-remix/tasks", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    writeJson("videoRemixStatusBox", body);
    log(`混剪任务已创建：${body.remix_task_id}`, "ok");
  } finally {
    if (generateButton) generateButton.disabled = false;
  }
}
```

- [ ] **Step 4: Wire navigation and buttons**

In `switchView`, replace the create-task refresh:

```javascript
  if (viewName === "create-task") safeRun(refreshVideoRemixMainVideos);
```

In `bind()`, replace the old create-task/video-template bindings with:

```javascript
  $("refreshRemixMainVideosBtn").onclick = () => safeRun(refreshVideoRemixMainVideos);
  $("videoRemixGenerateBtn").onclick = () => safeRun(createVideoRemixTask);
  for (const button of document.querySelectorAll("[data-remix-count]")) {
    button.onclick = () => setVideoRemixCount(button.dataset.remixCount);
  }
```

Keep `generateScriptQuickBtn`, `renderQuickBtn`, `generateScriptBtn`, `renderBtn`, and `reviewBtn` bindings guarded with null checks if those elements are no longer present:

```javascript
  if ($("generateScriptBtn")) $("generateScriptBtn").onclick = () => safeRun(generateScript);
  if ($("generateScriptQuickBtn")) $("generateScriptQuickBtn").onclick = () => safeRun(generateScript);
  if ($("renderBtn")) $("renderBtn").onclick = () => safeRun(renderVideo);
  if ($("generateFinalBtn")) $("generateFinalBtn").onclick = () => safeRun(renderVideo);
  if ($("renderQuickBtn")) $("renderQuickBtn").onclick = () => safeRun(renderVideo);
  if ($("reviewBtn")) $("reviewBtn").onclick = () => safeRun(reviewScript);
```

- [ ] **Step 5: Run UI tests and syntax check**

Run:

```powershell
pytest -q G:\tests\test_digital_human_studio_pages_14.py
node --check G:\app\static\studio.js
```

Expected: both pass.

---

### Task 4: Verify End-To-End Locally And Sync Packaged Runtime

**Files:**
- Copy changed files from `G:\app` to `G:\dist\desktop-cloud-providers-v2\win-unpacked\resources\app`
- Verify served app at `http://127.0.0.1:8080/`

- [ ] **Step 1: Run focused test suite**

Run:

```powershell
pytest -q G:\tests\test_video_remix_workflow.py G:\tests\test_digital_human_studio_pages_14.py
node --check G:\app\static\studio.js
python -m compileall G:\app\main.py G:\app\schemas.py
```

Expected: all tests pass and compileall reports successful compilation.

- [ ] **Step 2: Copy source changes into packaged app**

Run:

```powershell
Copy-Item -Path G:\app\main.py -Destination G:\dist\desktop-cloud-providers-v2\win-unpacked\resources\app\main.py -Force
Copy-Item -Path G:\app\schemas.py -Destination G:\dist\desktop-cloud-providers-v2\win-unpacked\resources\app\schemas.py -Force
Copy-Item -Path G:\app\static\studio.html -Destination G:\dist\desktop-cloud-providers-v2\win-unpacked\resources\app\static\studio.html -Force
Copy-Item -Path G:\app\static\studio.js -Destination G:\dist\desktop-cloud-providers-v2\win-unpacked\resources\app\static\studio.js -Force
```

Expected: no output and exit code 0.

- [ ] **Step 3: Restart the packaged backend**

Run:

```powershell
$proc = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*uvicorn*app.main*8080*' }
foreach ($item in $proc) { Stop-Process -Id $item.ProcessId -Force }
Start-Process -FilePath powershell.exe -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','G:\dist\desktop-cloud-providers-v2\win-unpacked\resources\storage\desktop\start_cloud_backend.ps1' -WindowStyle Hidden
```

Expected: backend restarts on port 8080.

- [ ] **Step 4: Verify served desktop content**

Run:

```powershell
$html = (Invoke-WebRequest http://127.0.0.1:8080/).Content
$js = (Invoke-WebRequest 'http://127.0.0.1:8080/studio.js?v=20260611-video-remix').Content
$health = Invoke-RestMethod http://127.0.0.1:8080/health
$html.Contains('视频混剪')
$html.Contains('remixMainVideoFile')
$html.Contains('视频生产')
$js.Contains('createVideoRemixTask')
$health.status
```

Expected:

```text
True
True
False
True
ok
```

- [ ] **Step 5: Verify API validation without paid calls**

Run:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8080/video-remix/tasks -ContentType 'application/json' -Body '{"project_id":"project_demo","assets":[{"filename":"a.png","content_type":"image/png","content_base64":"ZmFrZQ=="}],"output_count":1}'
```

Expected: HTTP 400 with detail `请先选择或上传主视频。`

---

## Self-Review

- Spec coverage: The plan renames the nav, removes old script/theme/template controls, adds main video selection/upload, asset upload, 1/3/5 output count, and one-click task creation.
- Error handling: API and UI both reject missing main video and missing remix assets with the specified Chinese messages.
- Scope control: The first implementation creates a clear remix task record and does not fake a finished MP4 while the remix render engine is not connected.
- Runtime coverage: The plan includes copying files into the packaged desktop app and verifying the served cache-busted JavaScript.
