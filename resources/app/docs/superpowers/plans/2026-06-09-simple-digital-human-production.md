# Simple Digital Human Production Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move Hifly API configuration out of digital human production and turn production into a three-step workflow.

**Architecture:** Reuse the existing desktop settings API for `HIFLY_*` credentials and the existing source-video/Hifly backend endpoints for rendering. Change only the studio HTML/JS/CSS and tests; backend provider endpoints remain available but are no longer exposed as production-page debug controls.

**Tech Stack:** FastAPI, Pydantic settings, static HTML/CSS/JavaScript, pytest, Node syntax check, in-app browser verification.

---

## File Structure

- Modify `G:\tests\test_hifly_digital_human_provider.py`: replace the old provider-card UI assertion with model-settings and simplified-production assertions.
- Modify `G:\tests\test_source_video_voice_clone_lipsync.py`: update source-video UI expectations to the three-step workflow.
- Modify `G:\app\static\studio.html`: remove the Hifly provider card from `source-video-human`, add a Hifly settings card in model settings, and replace source-video controls with three step panels.
- Modify `G:\app\static\studio.js`: add Hifly settings load/save/check handlers; remove production-page Hifly debug bindings; add Step 1/2/3 orchestration functions.
- Modify `G:\app\static\studio.css`: add compact workflow step styling if existing panel styles are not enough.
- Sync changed files to `G:\dist\desktop-cloud-providers-v2\win-unpacked\resources\app` and restart the desktop app.

`G:\app` is not a Git repository in this environment, so commit steps are replaced with status notes and verification output.

---

### Task 1: Lock UI Contract With Failing Tests

**Files:**
- Modify: `G:\tests\test_hifly_digital_human_provider.py`
- Modify: `G:\tests\test_source_video_voice_clone_lipsync.py`

- [ ] **Step 1: Replace the Hifly provider-card test**

Use assertions equivalent to:

```python
def test_hifly_configuration_lives_in_model_settings_not_production():
    html = Path("G:/app/static/studio.html").read_text(encoding="utf-8")
    js = Path("G:/app/static/studio.js").read_text(encoding="utf-8")

    assert "modelHiflyToken" in html
    assert "modelHiflyBaseUrl" in html
    assert "saveHiflyModelSettingsBtn" in html
    assert "checkHiflyModelSettingsBtn" in html
    assert "provider-card" not in _source_video_section(html)
    assert "hiflyVideoUrl" not in _source_video_section(html)
    assert "hiflyAudioUrl" not in _source_video_section(html)
    assert "hiflyCreateAvatarBtn" not in _source_video_section(html)
    assert "hiflyCreateVoiceBtn" not in _source_video_section(html)
    assert "hiflyOneClickBtn" not in _source_video_section(html)
    assert "modelHiflyToken" in js
    assert "saveHiflyModelSettings" in js
    assert "hiflyCreateAvatarBtn" not in js
```

- [ ] **Step 2: Add a helper that scopes assertions to the production section**

```python
def _source_video_section(html: str) -> str:
    start = html.index('data-view="source-video-human"')
    end = html.index('data-view="references"', start)
    return html[start:end]
```

- [ ] **Step 3: Update the production-page test**

Use assertions equivalent to:

```python
def test_studio_has_simple_three_step_source_video_ui():
    html = Path("G:/app/static/studio.html").read_text(encoding="utf-8")
    js = Path("G:/app/static/studio.js").read_text(encoding="utf-8")
    section = _source_video_section(html)

    assert "第一步" in section
    assert "上传视频创建形象和克隆声音" in section
    assert "第二步" in section
    assert "编写脚本" in section
    assert "第三步" in section
    assert "选择数字人形象和声音制作视频" in section
    assert "sourceVideoPrepareBtn" in section
    assert "sourceVideoSaveScriptBtn" in section
    assert "sourceVideoRenderBtn" in section
    assert "hiflyToken" not in section
    assert "hiflyVideoUrl" not in section
    assert "sourceVideoPrepareProfile" in js
    assert "saveSourceVideoScript" in js
```

- [ ] **Step 4: Run tests to verify RED**

Run:

```powershell
pytest G:\tests\test_hifly_digital_human_provider.py::test_hifly_configuration_lives_in_model_settings_not_production G:\tests\test_source_video_voice_clone_lipsync.py::test_studio_has_simple_three_step_source_video_ui -q
```

Expected: FAIL because the current UI still has the Hifly provider card and lacks the new model settings controls.

---

### Task 2: Add Hifly Configuration To Model Settings

**Files:**
- Modify: `G:\app\static\studio.html`
- Modify: `G:\app\static\studio.js`

- [ ] **Step 1: Add the model settings card**

In the model settings view, add controls:

```html
<section class="panel wide" id="hiflyModelSettingsCard">
  <h3>飞影 API 配置</h3>
  <p class="hint">飞影 Token 和 API 地址在这里配置；数字人制作页只负责上传视频、写脚本和生成视频。</p>
  <label class="checkline">
    <input type="checkbox" id="modelHiflyEnabled" />
    启用飞影 API 数字人
  </label>
  <div class="row">
    <label>
      API 地址
      <input id="modelHiflyBaseUrl" placeholder="https://hfw-api.hifly.cc" autocomplete="off" />
    </label>
    <label>
      API Token
      <input id="modelHiflyToken" type="password" placeholder="留空则保留已保存 Token" autocomplete="off" />
    </label>
  </div>
  <div class="actions compact">
    <button id="saveHiflyModelSettingsBtn" type="button">保存飞影配置</button>
    <button id="checkHiflyModelSettingsBtn" type="button">检查飞影配置</button>
  </div>
  <pre id="hiflyModelSettingsStatus" class="json-box compact-json">等待配置。</pre>
</section>
```

- [ ] **Step 2: Add JS settings helpers**

Add functions that call `GET /settings/desktop`, `PUT /settings/desktop`, and `POST /integrations/hifly/validate?live=true`.

- [ ] **Step 3: Bind controls**

Bind `saveHiflyModelSettingsBtn` and `checkHiflyModelSettingsBtn`. Call the load helper from `refreshModelCenter()`.

- [ ] **Step 4: Run GREEN check for Task 2 tests**

Run the Task 1 targeted tests. Expected remaining failures only relate to the production page.

---

### Task 3: Replace Production Page With Three-Step Workflow

**Files:**
- Modify: `G:\app\static\studio.html`
- Modify: `G:\app\static\studio.js`
- Modify: `G:\app\static\studio.css`

- [ ] **Step 1: Replace the source-video section markup**

The source-video section should show:

- Step 1: project, human name, source video upload, paid confirmation, `sourceVideoPrepareBtn`.
- Step 2: `sourceVideoScript`, `sourceVideoSaveScriptBtn`.
- Step 3: `sourceVideoHumanSelect`, `sourceVideoVoiceSelect`, `sourceVideoRenderQuality`, `sourceVideoRenderBtn`.
- Progress and output preview sections.

- [ ] **Step 2: Add Step 1 orchestrator**

Implement `sourceVideoPrepareProfile()`:

```javascript
async function sourceVideoPrepareProfile() {
  state.projectId = value("sourceVideoProject") || state.projectId || "project_demo";
  if ($("sourceVideoProject")) $("sourceVideoProject").value = state.projectId;
  let digitalHumanId = value("sourceVideoHumanSelect") || state.digitalHumanId;
  if (!digitalHumanId) {
    const created = await api(`/projects/${encodeURIComponent(state.projectId)}/digital-humans`, {
      method: "POST",
      body: JSON.stringify({
        name: value("sourceVideoHumanName") || "源视频数字人",
        avatar_source_type: "uploaded_reference",
      }),
    });
    digitalHumanId = created.digital_human_id;
    state.digitalHumanId = digitalHumanId;
  }
  await refreshSourceVideoHumans();
  if ($("sourceVideoHumanSelect")) $("sourceVideoHumanSelect").value = digitalHumanId;
  await uploadSourceVideo();
  await extractSourceVideoVoice();
  await createSourceVideoVoiceProfile();
  await refreshSourceVideoVoices();
  writeJson("sourceVideoProgressBox", { status: "ready", digital_human_id: state.digitalHumanId, voice_profile_id: state.voiceProfileId });
}
```

- [ ] **Step 3: Add source-video voice selector**

Implement `refreshSourceVideoVoices()` and `selectedSourceVideoVoiceId()` using existing `/digital-humans/{id}/voice-profiles`.

- [ ] **Step 4: Add Step 2 script saver**

Implement `saveSourceVideoScript()` that validates script text and stores it in `state.sourceVideoScript`.

- [ ] **Step 5: Revise Step 3 render**

Update `createSourceVideoTask()` to use `selectedSourceVideoVoiceId()` and the saved/current script. Keep `renderSourceVideoTask()` as the primary render action.

- [ ] **Step 6: Remove old Hifly debug bindings**

Delete bindings and functions for the removed production buttons.

- [ ] **Step 7: Run targeted tests**

Run:

```powershell
pytest G:\tests\test_hifly_digital_human_provider.py::test_hifly_configuration_lives_in_model_settings_not_production G:\tests\test_source_video_voice_clone_lipsync.py::test_studio_has_simple_three_step_source_video_ui -q
node --check G:\app\static\studio.js
```

Expected: PASS.

---

### Task 4: Regression And Desktop Verification

**Files:**
- Modify generated desktop runtime copy under `G:\dist\desktop-cloud-providers-v2\win-unpacked\resources\app`

- [ ] **Step 1: Run focused backend/UI tests**

Run:

```powershell
pytest G:\tests\test_hifly_digital_human_provider.py G:\tests\test_source_video_voice_clone_lipsync.py G:\tests\test_model_center.py -q
```

Expected: PASS.

- [ ] **Step 2: Run full verification**

Run:

```powershell
pytest -q
node --check G:\app\static\studio.js
python -m compileall G:\app G:\tests
```

Expected: all pass.

- [ ] **Step 3: Sync desktop runtime**

Copy changed app files to:

```text
G:\dist\desktop-cloud-providers-v2\win-unpacked\resources\app
```

Restart the desktop app if needed and confirm `/health` on `http://127.0.0.1:8080`.

- [ ] **Step 4: Browser verification**

Use the in-app browser to open `http://127.0.0.1:8080/`, navigate to Model Settings and Digital Human Production, and verify:

- Model settings shows Hifly API configuration.
- Production page shows exactly the three-step flow.
- Production page does not show Hifly token/public URL/debug buttons.
- Browser console has no app errors.

---

## Self-Review

- Spec coverage: model settings owns Hifly configuration, production page is three-step, real-mode URL handling remains backend-owned, tests and browser verification are covered.
- Placeholder scan: no TBD/TODO placeholders.
- Type consistency: IDs used in tests, HTML, and JS are consistent: `modelHiflyToken`, `modelHiflyBaseUrl`, `sourceVideoPrepareBtn`, `sourceVideoSaveScriptBtn`, `sourceVideoVoiceSelect`.
