"""
数字人内容工作流的本地 HTTP 接口。

职责：
- 内容提取
- AI 改写
- 用户确认文本
- TTS 生成语音
- 上传数字人参考图
- 调用可灵生成数字人口播视频
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from moonshot_service import build_moonshot_llm, load_env
from workflow_state import (
    WorkflowStep,
    create_workflow,
    list_workflows,
    make_workflow_store,
    save_workflow,
)
from storyboard_state import make_storyboard_store
from storyboard_routes import router as storyboard_router

# 本地文件存储目录
_BASE_DIR = Path(__file__).resolve().parent
UPLOADS_DIR = _BASE_DIR / "uploads"
GENERATED_DIR = _BASE_DIR / "generated"
FRONTEND_DIST_DIR = _BASE_DIR / "frontend" / "dist"
UPLOADS_DIR.mkdir(exist_ok=True)
GENERATED_DIR.mkdir(exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时只初始化工作流所需的环境与共享 LLM。
    load_env()
    app.state.router_llm = build_moonshot_llm()
    app.state.workflow_store = make_workflow_store()
    app.state.storyboard_store = make_storyboard_store()
    app.state.generated_dir = GENERATED_DIR
    yield


app = FastAPI(title="数字人内容工作流", lifespan=lifespan)

_origins = [o.strip() for o in os.getenv("CORS_ALLOW_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(storyboard_router)


@app.get("/health")
def health():
    return {"status": "ok"}

class WorkflowStartRequest(BaseModel):
    source: str = Field(default="", description="网页 URL 或已上传视频文件的服务器路径")
    raw_text: str = Field(default="", description="手动输入的原始文本，可直接进入确认流程")


class WorkflowStartResponse(BaseModel):
    session_id: str
    source_type: str
    extracted_text: str


class RewriteStyleInfo(BaseModel):
    style_id: str
    display_name: str


class RewriteRequest(BaseModel):
    style_id: str = Field(default="news", description="改写风格 ID，见 GET /rewrite-styles")


class RewriteResponse(BaseModel):
    session_id: str
    rewritten_text: str


class ConfirmRequest(BaseModel):
    final_text: str = Field(..., min_length=1, description="用户最终确认（或修改）的文本")


class ConfirmResponse(BaseModel):
    session_id: str
    final_text: str


class AudioResponse(BaseModel):
    session_id: str
    audio_url: str


class AvatarImageResponse(BaseModel):
    session_id: str
    file_path: str
    image_url: str


class VideoResponse(BaseModel):
    session_id: str
    video_status: str
    video_url: str | None = None
    video_error: str | None = None


class VideoRequest(BaseModel):
    mode: str = Field(
        default="avatar",
        description="生成模式：仅支持 avatar（数字人口播）",
        pattern="^avatar$",
    )
    provider: str = Field(
        default="kling",
        description="数字人服务商：kling（可灵）或 baidu（百度云晓灵）",
        pattern="^(kling|baidu)$",
    )


class VideoPatchRequest(BaseModel):
    video_url: str = Field(default="", description="直接写入视频 URL（与 task_id 二选一）")
    task_id: str   = Field(default="", description="任务 ID，服务端按 provider 查询结果后写入")
    provider: str  = Field(default="", description="覆盖 state.video_provider，kling 或 baidu")


class WorkflowStatusResponse(BaseModel):
    session_id: str
    current_step: str
    source_type: str
    extracted_text: str
    rewritten_text: str
    final_text: str
    audio_url: str | None
    avatar_image_ready: bool
    avatar_image_url: str | None
    video_url: str | None
    video_mode: str
    video_status: str
    video_error: str | None = None
    video_provider: str = "kling"


class WorkflowSessionInfo(BaseModel):
    session_id: str
    current_step: str
    source_type: str
    text_preview: str
    video_mode: str
    video_url: str | None = None
    updated_at: str | None = None
    video_provider: str = "kling"


def _get_state(request: Request, session_id: str):
    """从 store 取状态，找不到抛 404。"""
    try:
        return request.app.state.workflow_store(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"工作流会话不存在：{session_id}")


def _avatar_image_url(state) -> str | None:
    if not state.avatar_image_path:
        return None
    return f"/uploads/{Path(state.avatar_image_path).name}"


def _video_status(state) -> str:
    if state.video_status:
        return state.video_status
    return "succeed" if state.video_url else ""


def _run_avatar_video_job(store_fn, session_id: str) -> None:
    """后台生成数字人口播视频，并把结果写回工作流存储。"""
    from kling_service import generate_avatar_video

    try:
        state = store_fn(session_id)
        state.video_status = "processing"
        state.video_error = None
        state.video_mode = "avatar"
        state.current_step = WorkflowStep.VIDEO_PENDING
        save_workflow(store_fn, state)

        image_path = Path(state.avatar_image_path or "")
        audio_path = Path(state.audio_path or "")
        prompt = os.getenv("KLING_AVATAR_PROMPT", "").strip() or None
        mode   = os.getenv("KLING_AVATAR_MODE", "std").strip() or "std"
        video_url = generate_avatar_video(image_path, audio_path, prompt=prompt, mode=mode)

        state = store_fn(session_id)
        state.video_url = video_url
        state.video_status = "succeed"
        state.video_error = None
        state.video_mode = "avatar"
        state.current_step = WorkflowStep.VIDEO_DONE
        save_workflow(store_fn, state)
    except Exception as e:
        try:
            state = store_fn(session_id)
            state.video_status = "failed"
            state.video_error = str(e)
            state.video_mode = "avatar"
            state.current_step = WorkflowStep.VIDEO_FAILED
            save_workflow(store_fn, state)
        except Exception:
            pass


def _run_baidu_avatar_video_job(store_fn, session_id: str) -> None:
    """
    后台调用百度云数字人生成口播视频，将结果写回工作流存储。

    重试逻辑：
    - 若 state.baidu_task_id 已存在（上次超时），跳过提交直接接着轮询，不重复扣费。
    - 若没有 task_id（首次或文本/音频已更换），重新上传 COS + 提交任务。
    """
    from baidu_dh_service import poll_task, submit_job, verify_image
    from cos_service import upload_file

    _POLL_TIMEOUT = 1800  # 30 分钟，覆盖较长音频场景

    try:
        state = store_fn(session_id)
        state.video_status = "processing"
        state.video_error = None
        state.video_provider = "baidu"
        state.video_mode = "avatar"
        state.current_step = WorkflowStep.VIDEO_PENDING
        save_workflow(store_fn, state)

        task_id = state.baidu_task_id

        if not task_id:
            # ── 首次提交：上传 COS → 校验图片 → 提交任务 ──
            image_path = Path(state.avatar_image_path or "")
            audio_path = Path(state.audio_path or "")

            image_url = upload_file(
                image_path,
                f"digital-human/{session_id}/avatar{image_path.suffix}",
            )
            audio_url = upload_file(
                audio_path,
                f"digital-human/{session_id}/audio{audio_path.suffix}",
            )

            verify_image(image_url)
            task_id = submit_job(image_url, audio_url)

            # 持久化 task_id，超时后重试可直接接着轮询
            state = store_fn(session_id)
            state.baidu_task_id = task_id
            save_workflow(store_fn, state)

        # ── 轮询结果 ──
        video_url = poll_task(task_id, timeout=_POLL_TIMEOUT)

        state = store_fn(session_id)
        state.video_url = video_url
        state.video_status = "succeed"
        state.video_error = None
        state.baidu_task_id = None   # 任务完成后清空
        state.video_provider = "baidu"
        state.video_mode = "avatar"
        state.current_step = WorkflowStep.VIDEO_DONE
        save_workflow(store_fn, state)
    except Exception as e:
        try:
            state = store_fn(session_id)
            state.video_status = "failed"
            state.video_error = str(e)
            state.video_provider = "baidu"
            state.video_mode = "avatar"
            state.current_step = WorkflowStep.VIDEO_FAILED
            # baidu_task_id 保留，下次重试可接着轮询
            save_workflow(store_fn, state)
        except Exception:
            pass


@app.get("/workflow/sessions", response_model=list[WorkflowSessionInfo], tags=["workflow"])
def workflow_sessions(request: Request, limit: int = 50):
    """列出最近的工作流会话，供前端选择并恢复。"""
    safe_limit = min(max(limit, 1), 200)
    return list_workflows(request.app.state.workflow_store, limit=safe_limit)


@app.post("/workflow/start", response_model=WorkflowStartResponse, tags=["workflow"])
def workflow_start(body: WorkflowStartRequest, request: Request):
    """步骤 1：提交 URL / 视频路径 / 手动文本，初始化工作流并返回 session_id。"""
    from content_extraction import extract_content

    raw_text = body.raw_text.strip()
    source = body.source.strip()

    if raw_text:
        text = raw_text
        source_type = "text"
        state_source = raw_text
    else:
        if not source:
            raise HTTPException(status_code=422, detail="source 或 raw_text 至少提供一个。")
        try:
            text, source_type = extract_content(source)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"内容提取失败：{e}") from e
        state_source = source

    state = create_workflow(
        request.app.state.workflow_store,
        source=state_source,
        source_type=source_type,
        extracted_text=text,
    )
    return WorkflowStartResponse(
        session_id=state.session_id,
        source_type=state.source_type,
        extracted_text=state.extracted_text,
    )


@app.post("/workflow/upload", tags=["workflow"])
async def workflow_upload(file: UploadFile = File(...)):
    """上传视频文件到 uploads/ 目录，返回服务器文件路径，供 /workflow/start 使用。"""
    dest = UPLOADS_DIR / file.filename
    content = await file.read()
    dest.write_bytes(content)
    return {"file_path": str(dest)}


@app.get("/rewrite-styles", response_model=list[RewriteStyleInfo], tags=["workflow"])
def list_rewrite_styles():
    """查询可用改写风格。"""
    from text_rewrite import BUILTIN_REWRITE_STYLES

    return [
        RewriteStyleInfo(style_id=s.style_id, display_name=s.display_name)
        for s in BUILTIN_REWRITE_STYLES
    ]


@app.post("/workflow/{session_id}/rewrite", response_model=RewriteResponse, tags=["workflow"])
def workflow_rewrite(session_id: str, body: RewriteRequest, request: Request):
    """步骤 2：改写提取到的文本，返回改写结果。"""
    from text_rewrite import rewrite_text

    state = _get_state(request, session_id)
    if state.current_step == WorkflowStep.VIDEO_DONE:
        raise HTTPException(status_code=409, detail="工作流已完成，无法重新改写。")

    llm = request.app.state.router_llm
    if llm is None:
        raise HTTPException(
            status_code=503,
            detail="未配置 MOONSHOT_API_KEY。请在 .env 中填写后重启，再使用 AI 改写。",
        )
    try:
        rewritten = rewrite_text(state.extracted_text, body.style_id, llm)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"改写失败：{e}") from e

    state.rewritten_text = rewritten
    state.final_text = ""
    state.audio_path = None
    state.video_url = None
    state.video_status = ""
    state.video_error = None
    state.video_mode = "avatar"
    state.baidu_task_id = None
    state.current_step = WorkflowStep.REWRITTEN
    save_workflow(request.app.state.workflow_store, state)
    return RewriteResponse(session_id=session_id, rewritten_text=rewritten)


@app.post("/workflow/{session_id}/confirm", response_model=ConfirmResponse, tags=["workflow"])
def workflow_confirm(session_id: str, body: ConfirmRequest, request: Request):
    """步骤 3：用户确认或修改文本，存入 final_text。"""
    state = _get_state(request, session_id)
    state.final_text = body.final_text.strip()
    state.audio_path = None
    state.video_url = None
    state.video_status = ""
    state.video_error = None
    state.video_mode = "avatar"
    state.baidu_task_id = None
    state.current_step = WorkflowStep.CONFIRMED
    save_workflow(request.app.state.workflow_store, state)
    return ConfirmResponse(session_id=session_id, final_text=state.final_text)


@app.post("/workflow/{session_id}/audio", response_model=AudioResponse, tags=["workflow"])
def workflow_audio(session_id: str, request: Request):
    """步骤 4a：根据 final_text 生成 Edge TTS 音频，返回音频文件 URL。"""
    from tts_service import text_to_speech

    state = _get_state(request, session_id)
    if not state.final_text:
        raise HTTPException(status_code=409, detail="请先确认文本（POST /workflow/{id}/confirm）。")

    output_path = GENERATED_DIR / f"{session_id}.mp3"
    try:
        text_to_speech(state.final_text, output_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS 生成失败：{e}") from e

    state.audio_path = str(output_path)
    state.video_url = None
    state.video_status = ""
    state.video_error = None
    state.video_mode = "avatar"
    state.current_step = WorkflowStep.AUDIO_DONE
    save_workflow(request.app.state.workflow_store, state)

    audio_url = f"/generated/{session_id}.mp3"
    return AudioResponse(session_id=session_id, audio_url=audio_url)


@app.post("/workflow/{session_id}/avatar-image", response_model=AvatarImageResponse, tags=["workflow"])
async def workflow_avatar_image(session_id: str, request: Request, file: UploadFile = File(...)):
    """上传数字人参考图，供 Avatar image2video 接口使用。"""
    state = _get_state(request, session_id)
    if not state.final_text:
        raise HTTPException(status_code=409, detail="请先确认文本（POST /workflow/{id}/confirm）。")
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=422, detail="请上传图片文件（PNG/JPG/JPEG/WebP）。")

    suffix = Path(file.filename or "").suffix.lower() or ".png"
    if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise HTTPException(status_code=422, detail="头像图片仅支持 PNG/JPG/JPEG/WebP。")

    dest = UPLOADS_DIR / f"{session_id}_avatar{suffix}"
    content = await file.read()
    dest.write_bytes(content)

    state.avatar_image_path = str(dest)
    state.video_url = None
    state.video_status = ""
    state.video_error = None
    state.video_mode = "avatar"
    save_workflow(request.app.state.workflow_store, state)
    return AvatarImageResponse(session_id=session_id, file_path=str(dest), image_url=_avatar_image_url(state) or "")


@app.post("/workflow/{session_id}/video", response_model=VideoResponse, tags=["workflow"])
def workflow_video(
    session_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    body: VideoRequest | None = None,
):
    """
    步骤 5：异步生成数字人口播视频。

    必须先调用 /audio 和 /avatar-image，用人物图 + 音频驱动数字人口播。
    接口会快速返回 queued/processing，前端通过 /status 轮询最终 video_url。
    """
    state = _get_state(request, session_id)
    if body and body.mode != "avatar":
        raise HTTPException(status_code=422, detail="当前只支持数字人口播。")
    if state.video_url:
        return VideoResponse(
            session_id=session_id,
            video_status="succeed",
            video_url=state.video_url,
        )
    if _video_status(state) in {"queued", "processing"}:
        return VideoResponse(
            session_id=session_id,
            video_status=_video_status(state),
            video_url=state.video_url,
            video_error=state.video_error,
        )
    if not state.final_text:
        raise HTTPException(status_code=409, detail="请先确认文本（POST /workflow/{id}/confirm）。")
    if not state.audio_path:
        raise HTTPException(status_code=409, detail="请先生成音频（POST /workflow/{id}/audio）。")
    if not state.avatar_image_path:
        raise HTTPException(status_code=409, detail="请先上传数字人图片（POST /workflow/{id}/avatar-image）。")

    audio_path = Path(state.audio_path)
    if not audio_path.exists():
        raise HTTPException(status_code=500, detail=f"音频文件不存在：{audio_path}")
    image_path = Path(state.avatar_image_path)
    if not image_path.exists():
        raise HTTPException(status_code=500, detail=f"数字人图片不存在：{image_path}")

    provider = (body.provider if body else None) or "kling"
    state.video_mode = "avatar"
    state.video_provider = provider
    state.video_status = "queued"
    state.video_error = None
    state.video_url = None
    state.current_step = WorkflowStep.VIDEO_PENDING
    save_workflow(request.app.state.workflow_store, state)

    if provider == "baidu":
        background_tasks.add_task(_run_baidu_avatar_video_job, request.app.state.workflow_store, session_id)
    else:
        background_tasks.add_task(_run_avatar_video_job, request.app.state.workflow_store, session_id)

    return VideoResponse(session_id=session_id, video_status="queued")


@app.post("/workflow/{session_id}/video-patch", response_model=VideoResponse, tags=["workflow"])
def workflow_video_patch(session_id: str, body: VideoPatchRequest, request: Request):
    """
    手动补录视频结果。适用于：轮询超时但任务已在云端完成的情况（可灵 / 百度云）。

    - 传 video_url：直接写入指定 URL。
    - 传 task_id：后端按 video_provider 查询对应平台任务状态，成功则写入 videoUrl。
    - 两者都传时 video_url 优先。
    """
    state = _get_state(request, session_id)

    video_url = body.video_url.strip()

    if not video_url and body.task_id.strip():
        task_id = body.task_id.strip()
        provider = (body.provider.strip() or state.video_provider or "kling").lower()

        if provider == "baidu":
            from baidu_dh_service import BaiduDHAPIError, _get, _QUERY_PATH
            try:
                data = _get(_QUERY_PATH, {"taskId": task_id})
            except BaiduDHAPIError as e:
                raise HTTPException(status_code=502, detail=f"查询百度任务失败：{e}") from e
            result = data.get("result") or {}
            status = result.get("status", "")
            if status == "SUCCESS":
                video_url = result.get("videoUrl", "")
            elif status == "FAILED":
                raise HTTPException(
                    status_code=422,
                    detail=f"百度任务已失败 code={result.get('failedCode')}: {result.get('failedMessage')}",
                )
            else:
                raise HTTPException(
                    status_code=409,
                    detail=f"百度任务尚未完成，当前状态：{status}，请稍后再试。",
                )
        else:  # kling
            from kling_service import KlingAPIError, query_avatar_task
            try:
                result = query_avatar_task(task_id)
            except KlingAPIError as e:
                raise HTTPException(status_code=502, detail=f"查询可灵任务失败：{e}") from e
            status = result.get("status", "")
            if status == "succeed":
                video_url = result.get("video_url", "")
            elif status in ("failed", "cancelled"):
                raise HTTPException(status_code=422, detail=f"可灵任务已失败，状态：{status}")
            else:
                raise HTTPException(
                    status_code=409,
                    detail=f"可灵任务尚未完成，当前状态：{status}，请稍后再试。",
                )

    if not video_url:
        raise HTTPException(status_code=422, detail="请提供 video_url 或 task_id。")

    state.video_url = video_url
    state.video_status = "succeed"
    state.video_error = None
    state.baidu_task_id = None
    state.current_step = WorkflowStep.VIDEO_DONE
    save_workflow(request.app.state.workflow_store, state)
    return VideoResponse(session_id=session_id, video_status="succeed", video_url=video_url)


@app.get("/workflow/{session_id}/status", response_model=WorkflowStatusResponse, tags=["workflow"])
def workflow_status(session_id: str, request: Request):
    """查询工作流整体状态。"""
    state = _get_state(request, session_id)
    return WorkflowStatusResponse(
        session_id=state.session_id,
        current_step=state.current_step.value,
        source_type=state.source_type,
        extracted_text=state.extracted_text,
        rewritten_text=state.rewritten_text,
        final_text=state.final_text,
        audio_url=f"/generated/{session_id}.mp3" if state.audio_path else None,
        avatar_image_ready=bool(state.avatar_image_path),
        avatar_image_url=_avatar_image_url(state),
        video_url=state.video_url,
        video_mode=state.video_mode or "avatar",
        video_status=_video_status(state),
        video_error=state.video_error,
        video_provider=state.video_provider or "kling",
    )


# 挂载静态文件目录，让前端可以直接访问生成的音视频
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")
app.mount("/generated", StaticFiles(directory=str(GENERATED_DIR)), name="generated")
if FRONTEND_DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST_DIR), html=True), name="frontend")
