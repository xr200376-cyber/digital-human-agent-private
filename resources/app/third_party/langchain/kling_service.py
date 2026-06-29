"""
可灵 AI 视频生成服务。

支持数字人口播：
  人物图 + 音频 → 数字人对嘴视频（generate_avatar_video）

鉴权：JWT HS256，每次请求前动态签发（有效期 30 分钟）。

环境变量：
  KLING_ACCESS_KEY_ID       可灵 Access Key ID
  KLING_ACCESS_KEY_SECRET   可灵 Access Key Secret
"""

from __future__ import annotations

import base64
import os
import sys
import time
from pathlib import Path

import jwt
import requests

_DEFAULT_BASE_URL = "https://api.klingai.com"
_SINGAPORE_BASE_URL = "https://api-singapore.klingai.com"


class KlingAPIError(RuntimeError):
    """可灵远端接口返回的非 2xx 错误。"""

    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code


# ── 鉴权 ──────────────────────────────────────────────────────────────────

def _get_credentials() -> tuple[str, str]:
    ak = os.getenv("KLING_ACCESS_KEY_ID", "").strip()
    sk = os.getenv("KLING_ACCESS_KEY_SECRET", "").strip()
    if not ak or not sk:
        raise EnvironmentError(
            "请在 .env 中设置 KLING_ACCESS_KEY_ID 和 KLING_ACCESS_KEY_SECRET"
        )
    return ak, sk


def _base_url() -> str:
    """读取可灵 API 基础地址，默认使用全局网关。"""
    return os.getenv("KLING_API_BASE_URL", _DEFAULT_BASE_URL).strip().rstrip("/")


def _make_jwt(ak: str, sk: str) -> str:
    """签发 JWT，有效期 30 分钟。"""
    now = int(time.time())
    payload = {"iss": ak, "exp": now + 1800, "nbf": now - 5}
    token = jwt.encode(
        payload,
        sk,
        algorithm="HS256",
        headers={"alg": "HS256", "typ": "JWT"},
    )
    if os.getenv("KLING_PRINT_JWT", "").strip() == "1":
        print(f"[Kling JWT] {token}", file=sys.stderr)
    return token


def _auth_headers(ak: str, sk: str) -> dict:
    """构建带 JWT 鉴权的请求头。"""
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {_make_jwt(ak, sk)}",
    }


def _debug_enabled() -> bool:
    return os.getenv("KLING_DEBUG_HTTP", "").strip() == "1"


def _mask_header(value: str) -> str:
    if len(value) <= 24:
        return value
    return f"{value[:18]}...{value[-8:]}"


def _extract_api_error(resp: requests.Response, base_url: str) -> str:
    """把可灵返回的错误正文提炼成可读信息。"""
    if 300 <= resp.status_code < 400:
        location = resp.headers.get("Location", "")
        if location:
            return (
                f"HTTP {resp.status_code}: 可灵 API 返回重定向，"
                f"Location={location}。请把 KLING_API_BASE_URL 配成最终网关地址，"
                "避免 Authorization 在跳转中丢失。"
            )
        return f"HTTP {resp.status_code}: 可灵 API 返回了重定向响应。"

    try:
        payload = resp.json()
    except ValueError:
        text = resp.text.strip() or resp.reason or "未知错误"
        return f"HTTP {resp.status_code}: {text}"

    code = payload.get("code")
    message = str(payload.get("message") or resp.reason or "未知错误").strip()
    request_id = payload.get("request_id")

    parts = [f"HTTP {resp.status_code}"]
    if code is not None:
        parts.append(f"code={code}")
    if request_id:
        parts.append(f"request_id={request_id}")
    summary = ", ".join(parts)

    hints: list[str] = []
    lowered = message.lower()
    if "access key not found" in lowered and "api-singapore" in base_url:
        hints.append(
            "当前 AK 在新加坡网关未找到，可优先改用 https://api.klingai.com "
            "或在 .env 中显式设置 KLING_API_BASE_URL。"
        )
    elif "auth failed" in lowered:
        hints.append("请确认 Access Key ID / Secret Key 是否为同一组、且已开通对应 API 权限。")

    detail = f"{summary}: {message}"
    if hints:
        detail = f"{detail} {' '.join(hints)}"
    return detail


def _should_retry_on_global(base_url: str, resp: requests.Response) -> bool:
    """默认新加坡网关返回 access key not found 时，自动回退到全局网关重试。"""
    configured = os.getenv("KLING_API_BASE_URL", "").strip()
    if configured and configured.rstrip("/") != _SINGAPORE_BASE_URL:
        return False
    if base_url != _SINGAPORE_BASE_URL:
        return False
    try:
        payload = resp.json()
    except ValueError:
        return False
    message = str(payload.get("message") or "").lower()
    return resp.status_code == 401 and "access key not found" in message


def _request_json(
    method: str,
    path: str,
    *,
    json_body: dict | None = None,
    timeout: int = 30,
) -> requests.Response:
    """
    发送带鉴权的 JSON 请求。

    - 默认走全局网关 `api.klingai.com`
    - 若默认新加坡网关无法识别 Access Key，则自动回退到全局网关重试一次
    - 禁止自动跟随重定向，避免 Authorization 头在跨主机跳转时被 requests 丢弃
    """
    ak, sk = _get_credentials()
    headers = _auth_headers(ak, sk)
    base_url = _base_url()

    for _ in range(2):
        url = f"{base_url}{path}"
        if _debug_enabled():
            auth_value = headers.get("Authorization", "")
            print(
                "[Kling HTTP Request] "
                f"method={method} url={url} "
                f"has_authorization={bool(auth_value)} "
                f"authorization={_mask_header(auth_value)}",
                file=sys.stderr,
            )
        resp = requests.request(
            method,
            url,
            headers=headers,
            json=json_body,
            timeout=timeout,
            allow_redirects=False,
        )
        if _debug_enabled():
            print(
                "[Kling HTTP Response] "
                f"status={resp.status_code} body={resp.text[:500]}",
                file=sys.stderr,
            )
        if resp.ok:
            return resp
        if _should_retry_on_global(base_url, resp):
            base_url = _DEFAULT_BASE_URL
            continue
        raise KlingAPIError(_extract_api_error(resp, base_url), resp.status_code)

    raise RuntimeError("可灵 API 请求失败：已超过最大重试次数。")


def _poll_avatar_task(task_id: str, timeout: int = 300) -> str:
    """
    轮询 Avatar 任务，直到完成或超时。

    Avatar 接口返回结构与通用视频接口不同：
      data.task_status
      data.task_result.videos[0].url
    """
    deadline = time.time() + timeout

    while time.time() < deadline:
        resp = _request_json("GET", f"/v1/videos/avatar/image2video/{task_id}", timeout=30)
        data = resp.json().get("data", {})
        if not isinstance(data, dict):
            raise RuntimeError(f"Avatar API 响应格式异常：{resp.text}")

        status = data.get("task_status", "")
        if status == "succeed":
            videos = data.get("task_result", {}).get("videos", [])
            if videos and isinstance(videos[0], dict) and videos[0].get("url"):
                return videos[0]["url"]
            raise RuntimeError(f"Avatar 任务完成但无视频 URL：{resp.text}")
        if status in ("failed", "cancelled"):
            raise RuntimeError(f"Avatar 任务 {task_id} 失败，状态：{status}")

        time.sleep(5)

    raise TimeoutError(f"Avatar 轮询超时（{timeout}s），task_id={task_id}")


def _file_to_base64(path: Path) -> str:
    """读取本地文件并转为 Base64 字符串。"""
    return base64.b64encode(path.read_bytes()).decode("utf-8")


def generate_avatar_video(
    image_path: Path,
    audio_path: Path,
    prompt: str | None = None,
    mode: str = "std",
    timeout: int = 300,
) -> str:
    """
    上传人物图和音频至可灵，生成数字人口播视频。

    返回可访问的视频 URL。
    """
    if not image_path.exists():
        raise FileNotFoundError(f"人物图不存在：{image_path}")
    if not audio_path.exists():
        raise FileNotFoundError(f"音频文件不存在：{audio_path}")

    payload = {
        "image": _file_to_base64(image_path),
        "sound_file": _file_to_base64(audio_path),
        "mode": mode,
    }
    if prompt:
        payload["prompt"] = prompt

    task_resp = _request_json(
        "POST",
        "/v1/videos/avatar/image2video",
        json_body=payload,
        timeout=30,
    )
    task_id = task_resp.json().get("data", {}).get("task_id", "")
    if not task_id:
        raise RuntimeError(f"Avatar 任务提交失败：{task_resp.text}")

    return _poll_avatar_task(task_id, timeout=timeout)


def query_avatar_task(task_id: str) -> dict:
    """
    单次查询 Avatar 任务状态，不轮询。

    返回字典：
      status: "succeed" | "failed" | "cancelled" | "processing" | "queued"
      video_url: str（仅 succeed 时有值）
    """
    resp = _request_json("GET", f"/v1/videos/avatar/image2video/{task_id}", timeout=30)
    data = resp.json().get("data", {})
    if not isinstance(data, dict):
        raise RuntimeError(f"Avatar API 响应格式异常：{resp.text}")

    status = data.get("task_status", "")
    video_url = ""
    if status == "succeed":
        videos = data.get("task_result", {}).get("videos", [])
        if videos and isinstance(videos[0], dict):
            video_url = videos[0].get("url", "")
    return {"status": status, "video_url": video_url}
