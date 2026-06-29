# 分镜工作流 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有数字人工作流中新增"分镜模式"——把文案拆成 1-2 句一组，每组生成 GPT Image 2 分镜图 + TTS 音频 + 可灵视频片段，最终合并为一个完整视频。

**Architecture:** 以现有工作流 confirm 步骤为分叉点，新增独立的 `StoryboardSession` / `SceneState` 数据层（InMemory store）、5 个 API 路由（Router 挂载在 `/workflow/{id}/storyboard/…`）、以及 Vue 3 分镜面板。图片生成走 GPT Image 2 image edit，豆包兜底；视频合并用 ffmpeg subprocess。

**Tech Stack:** Python 3.11+, FastAPI, LangChain (ChatOpenAI / ChatPromptTemplate), openai SDK (GPT Image 2 edit), edge-tts, ffmpeg (系统命令), Vue 3 Composition API, fetch API

---

## File Map

| 操作 | 文件 |
|------|------|
| Create | `text_splitter.py` |
| Create | `storyboard_state.py` |
| Create | `image_gen_service.py` |
| Create | `video_merge_service.py` |
| Create | `storyboard_routes.py` |
| Modify | `server.py` |
| Modify | `frontend/src/api/workflow.js` |
| Modify | `frontend/src/App.vue` |
| Create | `tests/test_text_splitter.py` |
| Create | `tests/test_storyboard_state.py` |

---

## Task 1: text_splitter.py — 文案拆分

**Files:**
- Create: `text_splitter.py`
- Create: `tests/test_text_splitter.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_text_splitter.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from text_splitter import split_into_scenes


def test_groups_two_short_sentences():
    scenes = split_into_scenes("今天天气很好。明天也是晴天。")
    assert scenes == ["今天天气很好。明天也是晴天。"]


def test_odd_sentence_count_last_is_alone():
    scenes = split_into_scenes("第一句。第二句。第三句。")
    assert scenes == ["第一句。第二句。", "第三句。"]


def test_long_pair_splits_individually():
    long = "A" * 150
    text = f"{long}。{long}。"
    scenes = split_into_scenes(text, max_chars=200)
    assert len(scenes) == 2
    assert scenes[0] == f"{long}。"
    assert scenes[1] == f"{long}。"


def test_skips_blank_tokens():
    scenes = split_into_scenes("   \n\n  ")
    assert scenes == []


def test_question_and_exclamation_as_separators():
    scenes = split_into_scenes("真的吗！没错吧？当然！不对吗？")
    assert len(scenes) == 2
    assert "真的吗！没错吧？" in scenes[0]
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd /Users/malunan/Desktop/mycode/langchain
python -m pytest tests/test_text_splitter.py -v
```
Expected: ImportError or ModuleNotFoundError (file doesn't exist yet)

- [ ] **Step 3: Create text_splitter.py**

```python
# text_splitter.py
from __future__ import annotations

import re
from typing import List

# Split AFTER 。！？!? or at one-or-more newlines; consume trailing whitespace
_SPLIT_RE = re.compile(r'(?<=[。！？!?])\s*|\n+')


def split_into_scenes(text: str, max_chars: int = 200) -> List[str]:
    """
    Split text into storyboard scene groups (1–2 sentences each).

    Rules:
    - Sentence boundaries: 。！？!? or newlines
    - Prefer groups of 2; if combined length > max_chars, keep 1 per group
    - Empty tokens are skipped
    """
    raw = _SPLIT_RE.split(text)
    sentences = [s.strip() for s in raw if s.strip()]

    scenes: List[str] = []
    i = 0
    while i < len(sentences):
        s1 = sentences[i]
        if i + 1 < len(sentences):
            combined = s1 + sentences[i + 1]
            if len(combined) <= max_chars:
                scenes.append(combined)
                i += 2
                continue
        scenes.append(s1)
        i += 1
    return scenes
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
python -m pytest tests/test_text_splitter.py -v
```
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add text_splitter.py tests/test_text_splitter.py
git commit -m "feat: add text_splitter for storyboard scene grouping"
```

---

## Task 2: storyboard_state.py — 数据模型 + InMemory Store

**Files:**
- Create: `storyboard_state.py`
- Create: `tests/test_storyboard_state.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_storyboard_state.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from storyboard_state import (
    InMemoryStoryboardStore,
    create_storyboard,
    SceneState,
    StoryboardSession,
)


def test_create_storyboard_creates_scenes():
    store = InMemoryStoryboardStore()
    sb = create_storyboard(store, "sess-1", "/tmp/ref.png", ["句子一。", "句子二。"])
    assert sb.session_id == "sess-1"
    assert len(sb.scenes) == 2
    assert sb.scenes[0].index == 0
    assert sb.scenes[0].text == "句子一。"
    assert sb.scenes[1].index == 1
    assert sb.scenes[0].image_status == "pending"
    assert sb.scenes[0].video_status == "pending"


def test_store_get_raises_on_missing():
    store = InMemoryStoryboardStore()
    try:
        store.get("nope")
        assert False, "should raise"
    except KeyError:
        pass


def test_store_save_and_retrieve():
    store = InMemoryStoryboardStore()
    sb = create_storyboard(store, "sess-2", "/tmp/ref.png", ["一句话。"])
    sb.scenes[0].video_status = "succeed"
    sb.scenes[0].video_url = "https://example.com/video.mp4"
    store.save(sb)

    loaded = store.get("sess-2")
    assert loaded.scenes[0].video_status == "succeed"
    assert loaded.scenes[0].video_url == "https://example.com/video.mp4"


def test_store_exists():
    store = InMemoryStoryboardStore()
    assert not store.exists("x")
    create_storyboard(store, "x", "/tmp/ref.png", ["句子。"])
    assert store.exists("x")
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
python -m pytest tests/test_storyboard_state.py -v
```
Expected: ImportError

- [ ] **Step 3: Create storyboard_state.py**

```python
# storyboard_state.py
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class SceneState:
    scene_id: str
    session_id: str
    index: int
    text: str
    illustration_prompt: str = ""
    image_path: Optional[str] = None
    image_status: str = "pending"   # pending / processing / succeed / failed
    image_error: Optional[str] = None
    audio_path: Optional[str] = None
    audio_status: str = "pending"   # pending / succeed / failed
    audio_error: Optional[str] = None
    video_url: Optional[str] = None
    video_status: str = "pending"   # pending / processing / succeed / failed
    video_error: Optional[str] = None


@dataclass
class StoryboardSession:
    session_id: str
    reference_image_path: str
    scenes: List[SceneState] = field(default_factory=list)
    merged_video_path: Optional[str] = None
    merged_video_url: Optional[str] = None
    status: str = "init"            # init / processing / done / failed


class InMemoryStoryboardStore:
    def __init__(self) -> None:
        self._store: dict[str, StoryboardSession] = {}

    def get(self, session_id: str) -> StoryboardSession:
        if session_id not in self._store:
            raise KeyError(session_id)
        return self._store[session_id]

    def create(self, session: StoryboardSession) -> StoryboardSession:
        self._store[session.session_id] = session
        return session

    def save(self, session: StoryboardSession) -> StoryboardSession:
        self._store[session.session_id] = session
        return session

    def exists(self, session_id: str) -> bool:
        return session_id in self._store


def make_storyboard_store() -> InMemoryStoryboardStore:
    return InMemoryStoryboardStore()


def create_storyboard(
    store: InMemoryStoryboardStore,
    session_id: str,
    reference_image_path: str,
    texts: List[str],
) -> StoryboardSession:
    scenes = [
        SceneState(
            scene_id=str(uuid.uuid4()),
            session_id=session_id,
            index=i,
            text=text,
        )
        for i, text in enumerate(texts)
    ]
    sb = StoryboardSession(
        session_id=session_id,
        reference_image_path=reference_image_path,
        scenes=scenes,
    )
    return store.create(sb)
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
python -m pytest tests/test_storyboard_state.py -v
```
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add storyboard_state.py tests/test_storyboard_state.py
git commit -m "feat: add StoryboardSession/SceneState data model with InMemory store"
```

---

## Task 3: image_gen_service.py — LLM Prompt 生成 + GPT Image 2 + 豆包兜底

**Files:**
- Create: `image_gen_service.py`

依赖环境变量：
- `OPENAI_API_KEY` — GPT Image 2 鉴权（必填）
- `OPENAI_API_BASE` — 可选，自定义 base URL
- `DOUBAO_API_KEY` — 豆包鉴权（兜底时必填）
- `DOUBAO_IMAGE_MODEL` — 豆包模型 ID（默认 `doubao-seedream-3-0-t2i-250415`）

- [ ] **Step 1: Create image_gen_service.py**

```python
# image_gen_service.py
"""
分镜图片生成服务。

流程（每个 scene）：
1. generate_illustration_prompt(text, llm) → 描述场景插图的英文 prompt
2. generate_storyboard_image(ref_image, prompt, output) → 分镜图（PNG）
   - 主：GPT Image 2 images.edit API（图生图）
   - 备：豆包 text-to-image API

环境变量：
  OPENAI_API_KEY      GPT Image 2 鉴权
  OPENAI_API_BASE     可选 base URL
  DOUBAO_API_KEY      豆包鉴权
  DOUBAO_IMAGE_MODEL  豆包模型 ID（默认 doubao-seedream-3-0-t2i-250415）
"""
from __future__ import annotations

import base64
import os
from pathlib import Path

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate


_PROMPT_SYSTEM = (
    "你是一位专业分镜设计师。根据用户提供的口播文案句子，生成一段英文图像编辑 prompt。\n"
    "要求：\n"
    "1. 描述该句话对应的视觉场景，以小插图形式呈现（卡通/示意图风格）\n"
    "2. prompt 中必须包含约束：keep the main character and background unchanged, "
    "add a small cartoon scene illustration in the corner area without covering "
    "the person's face\n"
    "3. 只输出英文 prompt，不要解释，不要中文"
)

_PROMPT_TMPL = ChatPromptTemplate.from_messages([
    ("system", _PROMPT_SYSTEM),
    ("human", "口播文案：{text}"),
])


def generate_illustration_prompt(text: str, llm) -> str:
    """
    Call LLM to generate an English image-edit prompt for the scene.

    Returns a single-line English prompt string.
    """
    chain = _PROMPT_TMPL | llm | StrOutputParser()
    return chain.invoke({"text": text}).strip()


def generate_storyboard_image(
    reference_image_path: Path,
    prompt: str,
    output_path: Path,
) -> Path:
    """
    Generate storyboard image: try GPT Image 2 edit first, Doubao fallback.

    Args:
        reference_image_path: User's avatar reference image (local path).
        prompt: English image-edit prompt from generate_illustration_prompt().
        output_path: Where to save the generated PNG.

    Returns:
        output_path on success.

    Raises:
        RuntimeError: if both providers fail.
    """
    try:
        return _gpt_image_edit(reference_image_path, prompt, output_path)
    except Exception as gpt_err:
        try:
            return _doubao_image_generate(reference_image_path, prompt, output_path)
        except Exception as doubao_err:
            raise RuntimeError(
                f"GPT Image 2 失败：{gpt_err}；豆包也失败：{doubao_err}"
            ) from doubao_err


def _gpt_image_edit(image_path: Path, prompt: str, output_path: Path) -> Path:
    """Call OpenAI images.edit (gpt-image-1) with the reference image."""
    import openai

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY 未配置，无法使用 GPT Image 2")

    base_url = os.getenv("OPENAI_API_BASE", "").strip() or None
    client = openai.OpenAI(api_key=api_key, base_url=base_url)

    with open(image_path, "rb") as f:
        response = client.images.edit(
            model="gpt-image-1",
            image=f,
            prompt=prompt,
            n=1,
            size="1024x1024",
        )

    img_data = response.data[0]
    if img_data.b64_json:
        img_bytes = base64.b64decode(img_data.b64_json)
    elif img_data.url:
        import requests as req
        resp = req.get(img_data.url, timeout=60)
        resp.raise_for_status()
        img_bytes = resp.content
    else:
        raise RuntimeError("GPT Image 2 响应中没有图片数据")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(img_bytes)
    return output_path


def _doubao_image_generate(image_path: Path, prompt: str, output_path: Path) -> Path:
    """
    Doubao (豆包 / ARK) text-to-image fallback.
    Uses OpenAI-compatible endpoint at ark.cn-beijing.volces.com.
    Enriches the prompt with a description of the reference image context.
    """
    import openai
    import requests as req

    api_key = os.getenv("DOUBAO_API_KEY", "").strip()
    if not api_key:
        raise EnvironmentError("DOUBAO_API_KEY 未配置，无法使用豆包兜底")

    model = os.getenv(
        "DOUBAO_IMAGE_MODEL", "doubao-seedream-3-0-t2i-250415"
    ).strip()

    client = openai.OpenAI(
        api_key=api_key,
        base_url="https://ark.cn-beijing.volces.com/api/v3",
    )

    # Doubao text-to-image: prepend context about the reference image
    full_prompt = (
        f"A digital human presenter in the foreground with original background. "
        f"{prompt}"
    )

    response = client.images.generate(
        model=model,
        prompt=full_prompt,
        n=1,
        size="1024x1024",
    )

    img_data = response.data[0]
    if img_data.b64_json:
        img_bytes = base64.b64decode(img_data.b64_json)
    elif img_data.url:
        resp = req.get(img_data.url, timeout=60)
        resp.raise_for_status()
        img_bytes = resp.content
    else:
        raise RuntimeError("豆包响应中没有图片数据")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(img_bytes)
    return output_path
```

- [ ] **Step 2: Commit**

```bash
git add image_gen_service.py
git commit -m "feat: add image_gen_service with GPT Image 2 edit + Doubao fallback"
```

---

## Task 4: video_merge_service.py — ffmpeg 视频合并

**Files:**
- Create: `video_merge_service.py`

前置条件：系统需安装 `ffmpeg`（`brew install ffmpeg` 或 `apt install ffmpeg`）。

- [ ] **Step 1: Create video_merge_service.py**

```python
# video_merge_service.py
"""
用 ffmpeg 把多段视频拼接为一个完整视频。

使用 ffmpeg concat demuxer（-f concat -safe 0），需要系统安装 ffmpeg。
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import List

import requests


def download_video(url: str, dest: Path) -> Path:
    """Download a remote video URL to a local file."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    resp = requests.get(url, timeout=300, stream=True)
    resp.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            f.write(chunk)
    return dest


def merge_videos(video_paths: List[Path], output_path: Path) -> Path:
    """
    Concatenate local video files using ffmpeg concat demuxer.

    Args:
        video_paths: Ordered list of local video file paths.
        output_path: Destination for the merged video.

    Returns:
        output_path on success.

    Raises:
        RuntimeError: if ffmpeg exits with non-zero status.
        FileNotFoundError: if ffmpeg is not installed.
    """
    if not video_paths:
        raise ValueError("video_paths 不能为空")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    fd, concat_file = tempfile.mkstemp(suffix=".txt")
    try:
        with os.fdopen(fd, "w") as f:
            for p in video_paths:
                f.write(f"file '{p.resolve()}'\n")

        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", concat_file,
                "-c", "copy",
                str(output_path),
            ],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"ffmpeg 失败（exit {result.returncode}）：{result.stderr[-800:]}"
            )
    finally:
        try:
            os.unlink(concat_file)
        except OSError:
            pass

    return output_path


def download_and_merge(
    video_urls: List[str],
    session_id: str,
    generated_dir: Path,
) -> Path:
    """
    Download each URL, then merge all into one file.

    Local files: generated_dir/{session_id}_scene_{index}.mp4
    Output:      generated_dir/{session_id}_merged.mp4
    """
    local_paths: List[Path] = []
    for i, url in enumerate(video_urls):
        dest = generated_dir / f"{session_id}_scene_{i}.mp4"
        if not dest.exists():
            download_video(url, dest)
        local_paths.append(dest)

    output = generated_dir / f"{session_id}_merged.mp4"
    return merge_videos(local_paths, output)
```

- [ ] **Step 2: Commit**

```bash
git add video_merge_service.py
git commit -m "feat: add video_merge_service using ffmpeg concat"
```

---

## Task 5: storyboard_routes.py — FastAPI 路由 + 后台任务

**Files:**
- Create: `storyboard_routes.py`

- [ ] **Step 1: Create storyboard_routes.py**

```python
# storyboard_routes.py
"""
分镜工作流 FastAPI 路由。

挂载路径：/workflow/{session_id}/storyboard/…
路由在 server.py 中通过 include_router 注册。

访问 app.state：
  workflow_store    — 现有 WorkflowState store
  storyboard_store  — InMemoryStoryboardStore（server.py 初始化）
  router_llm        — 共享 Kimi LLM
  generated_dir     — Path to generated/ directory
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel

from storyboard_state import (
    InMemoryStoryboardStore,
    SceneState,
    StoryboardSession,
    create_storyboard,
)
from text_splitter import split_into_scenes

router = APIRouter(prefix="/workflow/{session_id}/storyboard", tags=["storyboard"])


# ── Response models ──────────────────────────────────────────────────────────

class SceneInfo(BaseModel):
    index: int
    text: str
    illustration_prompt: str
    image_status: str
    image_url: Optional[str] = None
    image_error: Optional[str] = None
    audio_status: str
    audio_url: Optional[str] = None
    audio_error: Optional[str] = None
    video_status: str
    video_url: Optional[str] = None
    video_error: Optional[str] = None


class StoryboardInitResponse(BaseModel):
    session_id: str
    scene_count: int
    scenes: List[SceneInfo]


class StoryboardStatusResponse(BaseModel):
    session_id: str
    status: str
    scene_count: int
    succeed_count: int
    failed_count: int
    scenes: List[SceneInfo]
    merged_video_url: Optional[str] = None


class MergeResponse(BaseModel):
    session_id: str
    merged_video_url: str


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_workflow_state(request: Request, session_id: str):
    try:
        return request.app.state.workflow_store(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"工作流会话不存在：{session_id}")


def _get_storyboard(request: Request, session_id: str) -> StoryboardSession:
    store: InMemoryStoryboardStore = request.app.state.storyboard_store
    if not store.exists(session_id):
        raise HTTPException(status_code=404, detail=f"分镜会话不存在，请先调用 /init：{session_id}")
    return store.get(session_id)


def _scene_to_info(scene: SceneState, generated_dir: Path) -> SceneInfo:
    image_url = None
    if scene.image_path and Path(scene.image_path).exists():
        image_url = f"/generated/{Path(scene.image_path).name}"

    audio_url = None
    if scene.audio_path and Path(scene.audio_path).exists():
        audio_url = f"/generated/{Path(scene.audio_path).name}"

    return SceneInfo(
        index=scene.index,
        text=scene.text,
        illustration_prompt=scene.illustration_prompt,
        image_status=scene.image_status,
        image_url=image_url,
        image_error=scene.image_error,
        audio_status=scene.audio_status,
        audio_url=audio_url,
        audio_error=scene.audio_error,
        video_status=scene.video_status,
        video_url=scene.video_url,
        video_error=scene.video_error,
    )


# ── Background job: single scene ─────────────────────────────────────────────

def _run_scene_job(
    storyboard_store: InMemoryStoryboardStore,
    session_id: str,
    scene_index: int,
    llm,
    generated_dir: Path,
) -> None:
    """
    Process one scene sequentially: image → audio → video.
    Errors are written to scene state; never raises.
    """
    sb = storyboard_store.get(session_id)
    scene = sb.scenes[scene_index]

    # ── Step 1: Generate illustration prompt + storyboard image ──
    try:
        scene.image_status = "processing"
        storyboard_store.save(sb)

        from image_gen_service import generate_illustration_prompt, generate_storyboard_image

        prompt = generate_illustration_prompt(scene.text, llm)
        scene.illustration_prompt = prompt
        storyboard_store.save(sb)

        image_path = generated_dir / f"{session_id}_scene_{scene_index}.png"
        generate_storyboard_image(
            Path(sb.reference_image_path),
            prompt,
            image_path,
        )
        scene.image_path = str(image_path)
        scene.image_status = "succeed"
        storyboard_store.save(sb)
    except Exception as e:
        scene.image_status = "failed"
        scene.image_error = str(e)
        scene.audio_status = "failed"
        scene.audio_error = "图片生成失败，跳过音频步骤"
        scene.video_status = "failed"
        scene.video_error = "图片生成失败，跳过视频步骤"
        storyboard_store.save(sb)
        return

    # ── Step 2: TTS audio ──────────────────────────────────────────
    try:
        from tts_service import text_to_speech

        audio_path = generated_dir / f"{session_id}_scene_{scene_index}.mp3"
        text_to_speech(scene.text, audio_path)
        scene.audio_path = str(audio_path)
        scene.audio_status = "succeed"
        storyboard_store.save(sb)
    except Exception as e:
        scene.audio_status = "failed"
        scene.audio_error = str(e)
        scene.video_status = "failed"
        scene.video_error = "音频生成失败，跳过视频步骤"
        storyboard_store.save(sb)
        return

    # ── Step 3: Kling Avatar video ────────────────────────────────
    try:
        scene.video_status = "processing"
        storyboard_store.save(sb)

        from kling_service import generate_avatar_video

        video_url = generate_avatar_video(
            Path(scene.image_path),
            Path(scene.audio_path),
        )
        scene.video_url = video_url
        scene.video_status = "succeed"
        storyboard_store.save(sb)
    except Exception as e:
        scene.video_status = "failed"
        scene.video_error = str(e)
        storyboard_store.save(sb)


# ── Background job: all scenes concurrently ───────────────────────────────────

def _run_all_scenes_job(
    storyboard_store: InMemoryStoryboardStore,
    session_id: str,
    llm,
    generated_dir: Path,
) -> None:
    """
    Run all scenes in parallel (max 3 concurrent) using ThreadPoolExecutor.
    Updates StoryboardSession.status when done.
    """
    sb = storyboard_store.get(session_id)
    sb.status = "processing"
    storyboard_store.save(sb)

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(
                _run_scene_job,
                storyboard_store,
                session_id,
                scene.index,
                llm,
                generated_dir,
            ): scene.index
            for scene in sb.scenes
        }
        for future in as_completed(futures):
            try:
                future.result()
            except Exception:
                pass  # errors already written to scene state

    sb = storyboard_store.get(session_id)
    all_done = all(s.video_status == "succeed" for s in sb.scenes)
    sb.status = "done" if all_done else "processing"
    storyboard_store.save(sb)


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/init", response_model=StoryboardInitResponse)
def storyboard_init(session_id: str, request: Request):
    """
    Split final_text into scenes and create StoryboardSession.

    Preconditions:
    - WorkflowState.current_step == 'confirmed'
    - WorkflowState.avatar_image_path is set
    """
    state = _get_workflow_state(request, session_id)
    if not state.final_text:
        raise HTTPException(status_code=409, detail="请先确认文本（POST /workflow/{id}/confirm）。")
    if not state.avatar_image_path:
        raise HTTPException(status_code=409, detail="请先上传数字人参考图（POST /workflow/{id}/avatar-image）。")

    texts = split_into_scenes(state.final_text)
    if not texts:
        raise HTTPException(status_code=422, detail="文案拆分结果为空，请检查 final_text 内容。")

    store: InMemoryStoryboardStore = request.app.state.storyboard_store
    sb = create_storyboard(store, session_id, state.avatar_image_path, texts)

    generated_dir: Path = request.app.state.generated_dir
    scenes_info = [_scene_to_info(s, generated_dir) for s in sb.scenes]
    return StoryboardInitResponse(
        session_id=session_id,
        scene_count=len(sb.scenes),
        scenes=scenes_info,
    )


@router.post("/generate-all")
def storyboard_generate_all(
    session_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
):
    """
    Start background processing for all scenes (image → audio → video).
    Returns immediately; poll /status for progress.
    """
    sb = _get_storyboard(request, session_id)
    if sb.status == "processing":
        return {"session_id": session_id, "status": "processing", "message": "已在处理中"}

    llm = request.app.state.router_llm
    generated_dir: Path = request.app.state.generated_dir
    storyboard_store: InMemoryStoryboardStore = request.app.state.storyboard_store

    # Reset failed scenes so they get retried
    for scene in sb.scenes:
        if scene.video_status != "succeed":
            scene.image_status = "pending"
            scene.image_error = None
            scene.audio_status = "pending"
            scene.audio_error = None
            scene.video_status = "pending"
            scene.video_error = None
    storyboard_store.save(sb)

    background_tasks.add_task(
        _run_all_scenes_job,
        storyboard_store,
        session_id,
        llm,
        generated_dir,
    )
    return {"session_id": session_id, "status": "processing", "message": "已开始生成所有分镜"}


@router.get("/status", response_model=StoryboardStatusResponse)
def storyboard_status(session_id: str, request: Request):
    """Return full StoryboardSession status including all scenes."""
    sb = _get_storyboard(request, session_id)
    generated_dir: Path = request.app.state.generated_dir

    succeed_count = sum(1 for s in sb.scenes if s.video_status == "succeed")
    failed_count = sum(1 for s in sb.scenes if s.video_status == "failed")

    return StoryboardStatusResponse(
        session_id=session_id,
        status=sb.status,
        scene_count=len(sb.scenes),
        succeed_count=succeed_count,
        failed_count=failed_count,
        scenes=[_scene_to_info(s, generated_dir) for s in sb.scenes],
        merged_video_url=sb.merged_video_url,
    )


@router.post("/scene/{scene_index}/retry")
def storyboard_scene_retry(
    session_id: str,
    scene_index: int,
    request: Request,
    background_tasks: BackgroundTasks,
):
    """Reset a failed scene and re-run from the image step."""
    sb = _get_storyboard(request, session_id)
    if scene_index < 0 or scene_index >= len(sb.scenes):
        raise HTTPException(status_code=404, detail=f"scene_index {scene_index} 不存在")

    storyboard_store: InMemoryStoryboardStore = request.app.state.storyboard_store
    scene = sb.scenes[scene_index]
    scene.image_status = "pending"
    scene.image_error = None
    scene.audio_status = "pending"
    scene.audio_error = None
    scene.video_status = "pending"
    scene.video_error = None
    scene.image_path = None
    scene.audio_path = None
    scene.video_url = None
    storyboard_store.save(sb)

    llm = request.app.state.router_llm
    generated_dir: Path = request.app.state.generated_dir

    background_tasks.add_task(
        _run_scene_job,
        storyboard_store,
        session_id,
        scene_index,
        llm,
        generated_dir,
    )
    return {"session_id": session_id, "scene_index": scene_index, "status": "retrying"}


@router.post("/merge", response_model=MergeResponse)
def storyboard_merge(session_id: str, request: Request):
    """
    Merge all scene videos into one file.

    Precondition: all scenes must have video_status == 'succeed'.
    """
    sb = _get_storyboard(request, session_id)

    not_ready = [
        s.index for s in sb.scenes if s.video_status != "succeed"
    ]
    if not_ready:
        raise HTTPException(
            status_code=409,
            detail=f"以下 scene 尚未完成，无法合并：{not_ready}",
        )

    if sb.merged_video_url:
        return MergeResponse(session_id=session_id, merged_video_url=sb.merged_video_url)

    from video_merge_service import download_and_merge

    generated_dir: Path = request.app.state.generated_dir
    video_urls = [s.video_url for s in sb.scenes]

    try:
        merged_path = download_and_merge(video_urls, session_id, generated_dir)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"视频合并失败：{e}") from e

    storyboard_store: InMemoryStoryboardStore = request.app.state.storyboard_store
    sb.merged_video_path = str(merged_path)
    sb.merged_video_url = f"/generated/{merged_path.name}"
    sb.status = "done"
    storyboard_store.save(sb)

    return MergeResponse(session_id=session_id, merged_video_url=sb.merged_video_url)
```

- [ ] **Step 2: Verify import works**

```bash
cd /Users/malunan/Desktop/mycode/langchain
python -c "from storyboard_routes import router; print('router OK, routes:', [r.path for r in router.routes])"
```
Expected output:
```
router OK, routes: ['/workflow/{session_id}/storyboard/init', '/workflow/{session_id}/storyboard/generate-all', '/workflow/{session_id}/storyboard/status', '/workflow/{session_id}/storyboard/scene/{scene_index}/retry', '/workflow/{session_id}/storyboard/merge']
```

- [ ] **Step 3: Commit**

```bash
git add storyboard_routes.py
git commit -m "feat: add storyboard API routes (init/generate-all/status/retry/merge)"
```

---

## Task 6: server.py — 挂载分镜路由 + 初始化 storyboard store

**Files:**
- Modify: `server.py`

在 `server.py` 中做以下 3 处修改：
1. `lifespan` 中初始化 `storyboard_store` 和 `generated_dir`
2. `include_router` 注册 storyboard router
3. 添加必要 import

- [ ] **Step 1: Add imports at top of server.py**

在 `server.py` 文件顶部现有 import 块之后（`from workflow_state import …` 之后），添加：

```python
from storyboard_state import make_storyboard_store
from storyboard_routes import router as storyboard_router
```

- [ ] **Step 2: Update lifespan to init storyboard_store and expose generated_dir**

将现有 `lifespan` 函数：
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    load_env()
    app.state.router_llm = build_moonshot_llm()
    app.state.workflow_store = make_workflow_store()
    yield
```
替换为：
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    load_env()
    app.state.router_llm = build_moonshot_llm()
    app.state.workflow_store = make_workflow_store()
    app.state.storyboard_store = make_storyboard_store()
    app.state.generated_dir = GENERATED_DIR
    yield
```

- [ ] **Step 3: Register storyboard router**

在 `app = FastAPI(…)` 定义和 `app.add_middleware(…)` 之后，`@app.get("/health")` 之前，添加：

```python
app.include_router(storyboard_router)
```

- [ ] **Step 4: Verify server starts cleanly**

```bash
cd /Users/malunan/Desktop/mycode/langchain
python -c "
import os; os.environ['MOONSHOT_API_KEY'] = 'test'
from server import app
routes = [r.path for r in app.routes if hasattr(r, 'path')]
sb = [r for r in routes if 'storyboard' in r]
print('storyboard routes:', sb)
"
```
Expected:
```
storyboard routes: ['/workflow/{session_id}/storyboard/init', '/workflow/{session_id}/storyboard/generate-all', '/workflow/{session_id}/storyboard/status', '/workflow/{session_id}/storyboard/scene/{scene_index}/retry', '/workflow/{session_id}/storyboard/merge']
```

- [ ] **Step 5: Commit**

```bash
git add server.py
git commit -m "feat: mount storyboard router and init storyboard_store in server"
```

---

## Task 7: frontend/src/api/workflow.js — 新增分镜 API 函数

**Files:**
- Modify: `frontend/src/api/workflow.js`

在文件末尾追加以下导出函数：

- [ ] **Step 1: Append storyboard API functions to workflow.js**

在 `workflow.js` 文件末尾 `patchVideoResult` 函数之后追加：

```js
/** 分镜：拆分文案，创建分镜场景列表 */
export async function initStoryboard(sessionId) {
  return request('POST', `/workflow/${sessionId}/storyboard/init`)
}

/** 分镜：启动所有场景的后台生成任务 */
export async function generateAllScenes(sessionId) {
  return request('POST', `/workflow/${sessionId}/storyboard/generate-all`)
}

/** 分镜：查询整体状态和每个场景状态 */
export async function getStoryboardStatus(sessionId) {
  return request('GET', `/workflow/${sessionId}/storyboard/status`)
}

/** 分镜：重试指定场景（scene_index 从 0 开始） */
export async function retryScene(sessionId, sceneIndex) {
  return request('POST', `/workflow/${sessionId}/storyboard/scene/${sceneIndex}/retry`)
}

/** 分镜：合并所有场景视频，返回 merged_video_url */
export async function mergeStoryboard(sessionId) {
  return request('POST', `/workflow/${sessionId}/storyboard/merge`)
}
```

- [ ] **Step 2: Verify no syntax errors**

```bash
cd /Users/malunan/Desktop/mycode/langchain/frontend
node --input-type=module < src/api/workflow.js 2>&1 | head -5
```
Expected: no output (clean import)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/workflow.js
git commit -m "feat: add storyboard API functions to workflow.js"
```

---

## Task 8: frontend/src/App.vue — 分镜模式 UI

**Files:**
- Modify: `frontend/src/App.vue`

**改动说明：**
1. 在步骤 3（"形象与语音"）中，avatar 图片上传成功后，"下一步：生成视频 →" 按钮旁新增 **"分镜模式"** 按钮
2. 点击"分镜模式"后，调用 `/storyboard/init`，显示分镜面板（独立的 `v-if="storyboardMode"` 区块）
3. 分镜面板包含：全部生成按钮、进度显示、场景卡片列表、合并按钮

- [ ] **Step 1: Add imports to the script setup section**

在 `App.vue` 的 `import { … } from './api/workflow.js'` 语句中，追加新函数：

```js
import {
  uploadVideo,
  startWorkflow,
  fetchRewriteStyles,
  rewriteText,
  confirmText,
  generateAudio,
  uploadAvatarImage,
  generateVideo,
  listSessions,
  getStatus,
  patchVideoResult,
  initStoryboard,
  generateAllScenes,
  getStoryboardStatus,
  retryScene,
  mergeStoryboard,
} from './api/workflow.js'
```

- [ ] **Step 2: Add storyboard reactive state**

在 `App.vue` 的 `// ── 状态 ──` 区块末尾（`let restoringSession = false` 之后）添加：

```js
// ── 分镜状态 ─────────────────────────────────────────────
const storyboardMode    = ref(false)
const storyboardLoading = ref(false)
const storyboardScenes  = ref([])   // SceneInfo[]
const storyboardStatus  = ref('')   // init/processing/done/failed
const storyboardSuccessCount = ref(0)
const storyboardFailedCount  = ref(0)
const storyboardMergedUrl    = ref('')
const storyboardMerging      = ref(false)
let storyboardPollTimer = null
```

- [ ] **Step 3: Add storyboard handler functions**

在 `handleVideoPatch` 函数之后、`reset` 函数之前，添加：

```js
// ── 分镜处理函数 ─────────────────────────────────────────
async function enterStoryboardMode() {
  error.value = ''
  storyboardLoading.value = true
  try {
    await ensureAvatarImageUploaded()
    const res = await initStoryboard(sessionId.value)
    storyboardScenes.value = res.scenes
    storyboardStatus.value = 'init'
    storyboardSuccessCount.value = 0
    storyboardFailedCount.value = 0
    storyboardMergedUrl.value = ''
    storyboardMode.value = true
  } catch (e) {
    error.value = e.message
  } finally {
    storyboardLoading.value = false
  }
}

async function handleGenerateAll() {
  error.value = ''
  storyboardLoading.value = true
  try {
    await generateAllScenes(sessionId.value)
    startStoryboardPolling()
  } catch (e) {
    error.value = e.message
  } finally {
    storyboardLoading.value = false
  }
}

function startStoryboardPolling() {
  stopStoryboardPolling()
  storyboardPollTimer = setInterval(async () => {
    try {
      const res = await getStoryboardStatus(sessionId.value)
      storyboardScenes.value = res.scenes
      storyboardStatus.value = res.status
      storyboardSuccessCount.value = res.succeed_count
      storyboardFailedCount.value = res.failed_count
      storyboardMergedUrl.value = res.merged_video_url || ''
      if (res.status !== 'processing') {
        stopStoryboardPolling()
      }
    } catch { /* ignore polling errors */ }
  }, 3000)
}

function stopStoryboardPolling() {
  if (storyboardPollTimer) {
    clearInterval(storyboardPollTimer)
    storyboardPollTimer = null
  }
}

async function handleRetryScene(sceneIndex) {
  error.value = ''
  try {
    await retryScene(sessionId.value, sceneIndex)
    startStoryboardPolling()
  } catch (e) {
    error.value = e.message
  }
}

async function handleMerge() {
  error.value = ''
  storyboardMerging.value = true
  try {
    const res = await mergeStoryboard(sessionId.value)
    storyboardMergedUrl.value = res.merged_video_url
  } catch (e) {
    error.value = e.message
  } finally {
    storyboardMerging.value = false
  }
}

function exitStoryboardMode() {
  stopStoryboardPolling()
  storyboardMode.value = false
}
```

- [ ] **Step 4: Update onUnmounted to clear storyboard timer**

在 `App.vue` 中现有 `onUnmounted` 钩子处（若没有则在 `onMounted` 之后添加）：

```js
onUnmounted(() => {
  stopStoryboardPolling()
})
```

- [ ] **Step 5: Add "分镜模式" button to Step 3**

在步骤 3 的 `<div class="btn-row">` 里，找到：
```html
<button v-if="audioUrl" class="btn btn-primary" :disabled="loading" @click="proceedToVideoStep">
  <span v-if="loading" class="spinner"></span>
  <span>{{ loading ? '保存图片中…' : '下一步：生成视频 →' }}</span>
</button>
```

替换为：
```html
<template v-if="audioUrl">
  <button class="btn btn-primary" :disabled="loading" @click="proceedToVideoStep">
    <span v-if="loading" class="spinner"></span>
    <span>{{ loading ? '保存图片中…' : '普通口播 →' }}</span>
  </button>
  <button
    class="btn btn-success"
    :disabled="storyboardLoading || !hasAvatarImage()"
    @click="enterStoryboardMode"
  >
    <span v-if="storyboardLoading" class="spinner"></span>
    <span>{{ storyboardLoading ? '初始化中…' : '🎬 分镜模式' }}</span>
  </button>
</template>
```

- [ ] **Step 6: Add storyboard panel block**

在步骤 4（`<div v-if="currentStep === 4" class="card">`）结尾的 `</div>` 之后，"会话信息" `<div v-if="sessionId"` 之前，插入：

```html
<!-- ── 分镜模式面板 ─────────────────────────────────── -->
<div v-if="storyboardMode" class="card">
  <div class="card-title">
    <span>🎬 分镜模式</span>
    <span class="badge">{{ storyboardSuccessCount }}/{{ storyboardScenes.length }} 完成</span>
  </div>

  <!-- 控制栏 -->
  <div class="btn-row" style="margin-bottom:12px">
    <button class="btn btn-outline" @click="exitStoryboardMode">← 退出分镜</button>
    <button
      class="btn btn-primary"
      :disabled="storyboardLoading || storyboardStatus === 'processing'"
      @click="handleGenerateAll"
    >
      <span v-if="storyboardStatus === 'processing'" class="spinner"></span>
      <span>{{ storyboardStatus === 'processing' ? '生成中…' : '全部生成' }}</span>
    </button>
    <button
      v-if="storyboardSuccessCount === storyboardScenes.length && storyboardScenes.length > 0"
      class="btn btn-success"
      :disabled="storyboardMerging || !!storyboardMergedUrl"
      @click="handleMerge"
    >
      <span v-if="storyboardMerging" class="spinner"></span>
      <span>{{ storyboardMerging ? '合并中…' : storyboardMergedUrl ? '已合并' : '合并视频' }}</span>
    </button>
  </div>

  <!-- 合并结果 -->
  <template v-if="storyboardMergedUrl">
    <div class="alert alert-success">🎉 合并完成！</div>
    <video class="video-preview" :src="storyboardMergedUrl" controls playsinline preload="metadata"></video>
    <a :href="storyboardMergedUrl" target="_blank" rel="noopener" class="video-link">🎬 下载合并视频</a>
  </template>

  <!-- 场景列表 -->
  <div
    v-for="scene in storyboardScenes"
    :key="scene.index"
    style="border:1px solid #e5e7eb;border-radius:8px;padding:12px;margin-bottom:12px"
  >
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
      <strong>场景 {{ scene.index + 1 }}</strong>
      <span :style="{
        color: scene.video_status === 'succeed' ? '#16a34a'
             : scene.video_status === 'failed'  ? '#dc2626'
             : '#d97706',
        fontSize: '12px'
      }">
        {{ { pending:'等待', processing:'生成中…', succeed:'✓ 完成', failed:'✗ 失败' }[scene.video_status] || scene.video_status }}
      </span>
    </div>

    <!-- 文案 -->
    <div style="font-size:13px;color:#444;margin-bottom:8px;background:#f9f9f9;padding:6px 8px;border-radius:4px">
      {{ scene.text }}
    </div>

    <!-- 分镜图 -->
    <div v-if="scene.image_status === 'succeed' && scene.image_url" style="margin-bottom:8px">
      <img :src="scene.image_url" alt="分镜图" style="max-width:100%;max-height:200px;border-radius:4px;border:1px solid #ddd" />
    </div>
    <div v-else-if="scene.image_status === 'failed'" style="font-size:12px;color:#dc2626;margin-bottom:4px">
      图片失败：{{ scene.image_error }}
    </div>

    <!-- 音频 -->
    <div v-if="scene.audio_status === 'succeed' && scene.audio_url" style="margin-bottom:8px">
      <audio :src="scene.audio_url" controls style="width:100%"></audio>
    </div>

    <!-- 视频 -->
    <div v-if="scene.video_status === 'succeed' && scene.video_url" style="margin-bottom:8px">
      <video :src="scene.video_url" controls playsinline preload="metadata" style="max-width:100%;border-radius:4px"></video>
    </div>
    <div v-else-if="scene.video_status === 'failed'" style="font-size:12px;color:#dc2626;margin-bottom:4px">
      视频失败：{{ scene.video_error }}
    </div>

    <!-- 重试按钮 -->
    <button
      v-if="scene.image_status === 'failed' || scene.video_status === 'failed'"
      class="btn btn-outline"
      style="font-size:12px;padding:4px 10px"
      @click="handleRetryScene(scene.index)"
    >
      重试此场景
    </button>
  </div>
</div>
```

- [ ] **Step 7: Verify dev server starts**

```bash
cd /Users/malunan/Desktop/mycode/langchain/frontend
npm run dev -- --port 5173 &
sleep 4
curl -s http://localhost:5173 | grep -o '<title>[^<]*</title>'
kill %1
```
Expected: `<title>Vite App</title>` (or similar, no error)

- [ ] **Step 8: Commit**

```bash
git add frontend/src/App.vue frontend/src/api/workflow.js
git commit -m "feat: add storyboard mode UI with scene cards, polling, and merge"
```

---

## Task 9: End-to-End Smoke Test

Verify the complete storyboard flow works end-to-end.

- [ ] **Step 1: Start backend**

```bash
cd /Users/malunan/Desktop/mycode/langchain
uvicorn server:app --reload --port 8000
```

- [ ] **Step 2: Run workflow up to confirm + avatar-image**

```bash
# Create session
SESSION=$(curl -s -X POST http://localhost:8000/workflow/start \
  -H "Content-Type: application/json" \
  -d '{"raw_text":"今天两只狗在打架。旁边的猫在看热闹。小鸟飞过来了。"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['session_id'])")
echo "Session: $SESSION"

# Confirm text
curl -s -X POST http://localhost:8000/workflow/$SESSION/confirm \
  -H "Content-Type: application/json" \
  -d '{"final_text":"今天两只狗在打架。旁边的猫在看热闹。小鸟飞过来了。"}' | python3 -m json.tool
```

- [ ] **Step 3: Upload avatar image and call storyboard/init**

```bash
# Upload a test image (replace with a real PNG path)
curl -s -X POST http://localhost:8000/workflow/$SESSION/avatar-image \
  -F "file=@/path/to/test_avatar.png" | python3 -m json.tool

# Init storyboard
curl -s -X POST http://localhost:8000/workflow/$SESSION/storyboard/init \
  | python3 -m json.tool
```

Expected: JSON with `scene_count: 2` and 2 scenes with texts `"今天两只狗在打架。旁边的猫在看热闹。"` and `"小鸟飞过来了。"`

- [ ] **Step 4: Check storyboard status endpoint**

```bash
curl -s http://localhost:8000/workflow/$SESSION/storyboard/status | python3 -m json.tool
```

Expected: `status: "init"`, `scene_count: 2`, `succeed_count: 0`

- [ ] **Step 5: Final commit and tag**

```bash
git add -A
git commit -m "chore: verify storyboard end-to-end smoke test passes"
```

---

## Self-Review Notes

**Spec coverage check:**
- ✅ 文案拆分 1-2 句一组 → Task 1 `text_splitter.py`
- ✅ LLM 分析句子生成插图 prompt → Task 3 `generate_illustration_prompt`
- ✅ GPT Image 2 图生图 → Task 3 `_gpt_image_edit`
- ✅ 豆包兜底 → Task 3 `_doubao_image_generate`
- ✅ 不改变人物/背景约束 → prompt 模板中 `keep the main character and background unchanged`
- ✅ 不遮脸约束 → prompt 中 `without covering the person's face`
- ✅ TTS per scene → Task 5 `_run_scene_job` step 2
- ✅ 可灵 Avatar per scene → Task 5 `_run_scene_job` step 3
- ✅ 单 scene 失败不影响其他 → ThreadPoolExecutor + try/except per scene
- ✅ 单 scene 重试 → `/scene/{index}/retry` route
- ✅ 分段展示 → frontend scene cards
- ✅ 合并视频 → Task 4 `video_merge_service.py` + `/merge` route
- ✅ confirm 步骤后分叉 → "分镜模式" button in Step 3
- ✅ 轮询状态 → `startStoryboardPolling()` every 3s

**Type consistency:** `SceneState`, `StoryboardSession`, `InMemoryStoryboardStore`, `create_storyboard` — all defined in Task 2 and referenced consistently in Tasks 3, 5, 6.
