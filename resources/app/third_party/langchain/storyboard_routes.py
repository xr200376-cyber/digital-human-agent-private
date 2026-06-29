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
from image_gen_service import generate_illustration_prompt, generate_storyboard_image
from tts_service import text_to_speech
from kling_service import generate_avatar_video
from video_merge_service import download_and_merge

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


def _scene_to_info(scene: SceneState) -> SceneInfo:
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
    lock = storyboard_store.get_lock(session_id)
    sb = storyboard_store.get(session_id)
    scene = sb.scenes[scene_index]

    # ── Step 1: Generate illustration prompt + storyboard image ──
    try:
        with lock:
            scene.image_status = "processing"
            storyboard_store.save(sb)

        prompt = generate_illustration_prompt(scene.text, llm)
        with lock:
            scene.illustration_prompt = prompt
            storyboard_store.save(sb)

        image_path = generated_dir / f"{session_id}_scene_{scene_index}.png"
        generate_storyboard_image(
            Path(sb.reference_image_path),
            prompt,
            image_path,
        )
        with lock:
            scene.image_path = str(image_path)
            scene.image_status = "succeed"
            storyboard_store.save(sb)
    except Exception as e:
        with lock:
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
        with lock:
            scene.audio_status = "processing"
            storyboard_store.save(sb)

        audio_path = generated_dir / f"{session_id}_scene_{scene_index}.mp3"
        text_to_speech(scene.text, audio_path)
        with lock:
            scene.audio_path = str(audio_path)
            scene.audio_status = "succeed"
            storyboard_store.save(sb)
    except Exception as e:
        with lock:
            scene.audio_status = "failed"
            scene.audio_error = str(e)
            scene.video_status = "failed"
            scene.video_error = "音频生成失败，跳过视频步骤"
            storyboard_store.save(sb)
        return

    # ── Step 3: Kling Avatar video ────────────────────────────────
    try:
        with lock:
            scene.video_status = "processing"
            storyboard_store.save(sb)

        video_url = generate_avatar_video(
            Path(scene.image_path),
            Path(scene.audio_path),
        )
        with lock:
            scene.video_url = video_url
            scene.video_status = "succeed"
            storyboard_store.save(sb)
    except Exception as e:
        with lock:
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
    lock = storyboard_store.get_lock(session_id)
    with lock:
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

    with lock:
        sb = storyboard_store.get(session_id)
        all_done = all(s.video_status == "succeed" for s in sb.scenes)
        sb.status = "done" if all_done else "failed"
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
    try:
        sb = create_storyboard(store, session_id, state.avatar_image_path, texts)
    except KeyError:
        raise HTTPException(status_code=409, detail=f"分镜会话已存在：{session_id}，请使用 /status 查看当前状态。")

    scenes_info = [_scene_to_info(s) for s in sb.scenes]
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
    llm = request.app.state.router_llm
    generated_dir: Path = request.app.state.generated_dir
    storyboard_store: InMemoryStoryboardStore = request.app.state.storyboard_store

    lock = storyboard_store.get_lock(session_id)
    with lock:
        sb = _get_storyboard(request, session_id)
        if sb.status == "processing":
            return {"session_id": session_id, "status": "processing", "message": "已在处理中"}

        # Reset non-succeed scenes so they get retried
        for scene in sb.scenes:
            if scene.video_status != "succeed":
                scene.image_status = "pending"
                scene.image_error = None
                scene.audio_status = "pending"
                scene.audio_error = None
                scene.video_status = "pending"
                scene.video_error = None
        sb.status = "processing"
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

    succeed_count = sum(1 for s in sb.scenes if s.video_status == "succeed")
    failed_count = sum(1 for s in sb.scenes if s.video_status == "failed")

    return StoryboardStatusResponse(
        session_id=session_id,
        status=sb.status,
        scene_count=len(sb.scenes),
        succeed_count=succeed_count,
        failed_count=failed_count,
        scenes=[_scene_to_info(s) for s in sb.scenes],
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

    scene = sb.scenes[scene_index]
    if scene.video_status == "processing" or scene.image_status == "processing":
        raise HTTPException(
            status_code=409,
            detail=f"Scene {scene_index} 正在生成中，请等待当前任务完成再重试。",
        )

    storyboard_store: InMemoryStoryboardStore = request.app.state.storyboard_store
    lock = storyboard_store.get_lock(session_id)
    with lock:
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
    generated_dir: Path = request.app.state.generated_dir
    storyboard_store: InMemoryStoryboardStore = request.app.state.storyboard_store
    lock = storyboard_store.get_lock(session_id)

    with lock:
        sb = _get_storyboard(request, session_id)
        not_ready = [s.index for s in sb.scenes if s.video_status != "succeed"]
        if not_ready:
            raise HTTPException(
                status_code=409,
                detail=f"以下 scene 尚未完成，无法合并：{not_ready}",
            )
        if sb.merged_video_url or sb.status in ("merging", "done"):
            if sb.merged_video_url:
                return MergeResponse(session_id=session_id, merged_video_url=sb.merged_video_url)
            raise HTTPException(status_code=409, detail="视频合并正在进行中，请稍后再试")
        # Set sentinel to prevent a concurrent request from also starting the merge
        sb.status = "merging"
        storyboard_store.save(sb)
        video_urls = [s.video_url for s in sb.scenes]

    try:
        merged_path = download_and_merge(video_urls, session_id, generated_dir)
    except Exception as e:
        with lock:
            sb = storyboard_store.get(session_id)
            sb.status = "failed"
            storyboard_store.save(sb)
        raise HTTPException(status_code=500, detail=f"视频合并失败：{e}") from e

    with lock:
        sb = storyboard_store.get(session_id)
        sb.merged_video_path = str(merged_path)
        sb.merged_video_url = f"/generated/{merged_path.name}"
        sb.status = "done"
        storyboard_store.save(sb)

    return MergeResponse(session_id=session_id, merged_video_url=sb.merged_video_url)
