"""
百度云数字人视频生成服务（晓灵平台）。

鉴权格式：
  Authorization: {AppId}/{HMAC-SHA256(AppKey, AppId+ExpireTime)}/{ExpireTime}

接口：
  submit  POST /api/digitalhuman/open/v1/video/image/submit
  query   GET  /api/digitalhuman/open/v1/video/image/task
  verify  POST /api/digitalhuman/open/v1/video/image/verify

环境变量：
  BAIDU_DH_APP_ID       晓灵平台应用 ID
  BAIDU_DH_APP_KEY      晓灵平台应用密钥
  BAIDU_DH_API_BASE_URL API 基础地址（默认 https://open.xiling.baidu.com）
  SERVER_BASE_URL       本服务对外可访问的基础 URL，百度云用此地址下载音频/图片
                        例如 http://your-server.com:8000
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import os
import time
import uuid

import requests

_DEFAULT_BASE_URL = "https://open.xiling.baidu.com"
_SUBMIT_PATH = "/api/digitalhuman/open/v1/video/image/submit"
_QUERY_PATH  = "/api/digitalhuman/open/v1/video/image/task"
_VERIFY_PATH = "/api/digitalhuman/open/v1/video/image/verify"


class BaiduDHAPIError(RuntimeError):
    """百度数字人接口错误。"""

    def __init__(self, message: str, code: int = 0):
        super().__init__(message)
        self.code = code


# ── 凭证与鉴权 ──────────────────────────────────────────────────────────────


def _get_credentials() -> tuple[str, str]:
    app_id  = os.getenv("BAIDU_DH_APP_ID", "").strip()
    app_key = os.getenv("BAIDU_DH_APP_KEY", "").strip()
    if not app_id or not app_key:
        raise EnvironmentError(
            "请在 .env 中设置 BAIDU_DH_APP_ID 和 BAIDU_DH_APP_KEY"
        )
    return app_id, app_key


def _base_url() -> str:
    return os.getenv("BAIDU_DH_API_BASE_URL", _DEFAULT_BASE_URL).strip().rstrip("/")


def _make_authorization(app_id: str, app_key: str, hours: int = 1) -> str:
    """
    生成鉴权字符串：{AppId}/{Signature}/{ExpireTime}

    Signature = HMAC-SHA256(AppKey, AppId + ExpireTime)  (hex)
    ExpireTime = ISO 8601 带时区偏移，例如 2025-05-27T10:15:30.123456+00:00
    """
    expire_time = (
        datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=hours)
    ).isoformat()
    signature = hmac.new(
        app_key.encode("utf-8"),
        (app_id + expire_time).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{app_id}/{signature}/{expire_time}"


# ── HTTP 辅助 ────────────────────────────────────────────────────────────────


def _parse_response(resp: requests.Response) -> dict:
    try:
        data = resp.json()
    except ValueError:
        raise BaiduDHAPIError(f"HTTP {resp.status_code}: {resp.text[:300]}")

    if not resp.ok or data.get("code", 0) != 0:
        code = data.get("code", resp.status_code)
        msg_obj = data.get("message", {})
        msg = (
            msg_obj.get("global", str(msg_obj))
            if isinstance(msg_obj, dict)
            else str(msg_obj)
        )
        raise BaiduDHAPIError(f"百度数字人接口错误 code={code}: {msg}", code=code)

    return data


def _post(path: str, payload: dict) -> dict:
    app_id, app_key = _get_credentials()
    url = f"{_base_url()}{path}"
    headers = {
        "Content-Type": "application/json;charset=utf-8",
        "Authorization": _make_authorization(app_id, app_key),
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    return _parse_response(resp)


def _get(path: str, params: dict) -> dict:
    app_id, app_key = _get_credentials()
    url = f"{_base_url()}{path}"
    headers = {
        "Authorization": _make_authorization(app_id, app_key),
    }
    resp = requests.get(url, headers=headers, params=params, timeout=30)
    return _parse_response(resp)


# ── 业务接口 ─────────────────────────────────────────────────────────────────


def verify_image(image_url: str) -> None:
    """
    校验人像图片是否符合数字人合成要求。
    不符合时抛出 BaiduDHAPIError（含错误码和描述）。
    """
    _post(_VERIFY_PATH, {
        "requestId": str(uuid.uuid4()),
        "inputImageUrl": image_url,
    })


def submit_job(image_url: str, audio_url: str) -> str:
    """提交图像 + 音频驱动的数字人视频生成任务，返回 taskId。"""
    data = _post(_SUBMIT_PATH, {
        "requestId": str(uuid.uuid4()),
        "driveType": "VOICE",
        "inputImageUrl": image_url,
        "inputAudioUrl": audio_url,
    })
    task_id = (data.get("result") or {}).get("taskId", "")
    if not task_id:
        raise BaiduDHAPIError(f"百度数字人未返回 taskId：{data}")
    return task_id


def poll_task(task_id: str, timeout: int = 300) -> str:
    """
    轮询任务状态直到成功或失败。
    成功返回视频 URL，失败抛出 BaiduDHAPIError。
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = _get(_QUERY_PATH, {"taskId": task_id})
        result = data.get("result") or {}
        status = result.get("status", "")

        if status == "SUCCESS":
            video_url = result.get("videoUrl", "")
            if not video_url:
                raise BaiduDHAPIError("百度数字人任务完成但未返回视频 URL")
            return video_url

        if status == "FAILED":
            failed_msg  = result.get("failedMessage", "未知错误")
            failed_code = result.get("failedCode", 0)
            raise BaiduDHAPIError(
                f"百度数字人任务失败 code={failed_code}: {failed_msg}",
                code=failed_code,
            )

        # SUBMIT / GENERATING — 等待后重试
        time.sleep(5)

    raise TimeoutError(f"百度数字人任务轮询超时（{timeout}s），task_id={task_id}")


def generate_avatar_video(
    image_url: str,
    audio_url: str,
    timeout: int = 300,
) -> str:
    """
    提交百度云数字人视频生成任务，同步等待完成，返回视频 URL。

    :param image_url:  人物图的公开可访问 URL（PNG/JPG/JPEG，≤3 MB）
    :param audio_url:  音频文件的公开可访问 URL（MP3/WAV/WMA/M4A，≤2 G，≥2 s）
    :param timeout:    最长等待秒数（默认 300 秒）
    """
    task_id = submit_job(image_url, audio_url)
    return poll_task(task_id, timeout=timeout)
