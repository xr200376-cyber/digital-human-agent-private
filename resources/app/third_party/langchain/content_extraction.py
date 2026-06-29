"""
内容提取：从网页 URL 或视频文件中提取纯文本。

支持两种来源：
- URL：requests + BeautifulSoup 抓取正文
- 视频文件：moviepy 提取音轨 → SpeechRecognition（Google 免费 API）转写
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path


def extract_from_url(url: str) -> str:
    """用 requests + BeautifulSoup 抓取网页正文。"""
    import requests
    from bs4 import BeautifulSoup

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or "utf-8"

    soup = BeautifulSoup(resp.text, "lxml")

    # 移除 script / style / nav / footer
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    # 优先取 <article>，其次 <main>，再兜底整个 body
    main = soup.find("article") or soup.find("main") or soup.body
    text = (main or soup).get_text(separator="\n", strip=True)

    # 压缩连续空行
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines)


def extract_from_video(file_path: Path) -> str:
    """
    从视频文件提取音轨，用 Whisper 离线转写（支持中文，无需联网）。

    依赖：openai-whisper、ffmpeg（系统级）。
    首次运行会自动下载 Whisper small 模型（约 244MB）。
    """
    try:
        import whisper
    except ImportError as e:
        raise ImportError("请先安装 whisper：pip install openai-whisper") from e

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        ffmpeg = _resolve_ffmpeg_executable()
        result = subprocess.run(
            [ffmpeg, "-y", "-i", str(file_path), "-ac", "1", "-ar", "16000", tmp_path, "-loglevel", "error"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            message = f"ffmpeg 提取音频失败：{file_path}"
            if detail:
                message = f"{message}\n{detail}"
            raise ValueError(message)
        audio = _load_wav_for_whisper(Path(tmp_path))
        import opencc
        model = whisper.load_model("small")
        result = model.transcribe(audio, language="zh")
        text = result["text"].strip()
        return opencc.OpenCC("t2s").convert(text)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _resolve_ffmpeg_executable() -> str:
    configured = os.getenv("FFMPEG_PATH", "").strip()
    if configured:
        return configured

    found = shutil.which("ffmpeg")
    if found:
        return found

    try:
        import imageio_ffmpeg
    except ImportError as e:
        raise RuntimeError(
            "未找到 ffmpeg。请安装系统 ffmpeg，或安装 Python 依赖 imageio-ffmpeg。"
        ) from e

    return imageio_ffmpeg.get_ffmpeg_exe()


def _load_wav_for_whisper(file_path: Path):
    import numpy as np

    with wave.open(str(file_path), "rb") as wav:
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        frames = wav.readframes(wav.getnframes())

    if sample_width != 2:
        raise ValueError(f"Unsupported WAV sample width: {sample_width}")

    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    return audio


_DOUYIN_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) EdgiOS/121.0.2277.107 "
        "Version/17.0 Mobile/15E148 Safari/604.1"
    )
}


def _is_douyin_url(url: str) -> bool:
    return any(d in url for d in ("douyin.com", "iesdouyin.com"))


def _resolve_douyin_video_url(share_url: str) -> str:
    """从抖音分享链接解析出真实无水印视频下载地址。"""
    import json
    import re
    import requests

    # 跟随跳转拿到真实视频 ID
    resp = requests.get(share_url, headers=_DOUYIN_HEADERS, timeout=15, verify=False)
    video_id = resp.url.split("?")[0].rstrip("/").split("/")[-1]

    # 用 iesdouyin 接口获取视频信息
    page_url = f"https://www.iesdouyin.com/share/video/{video_id}"
    resp = requests.get(page_url, headers=_DOUYIN_HEADERS, timeout=15, verify=False)
    resp.raise_for_status()

    m = re.search(r"window\._ROUTER_DATA\s*=\s*(.*?)</script>", resp.text, re.DOTALL)
    if not m:
        raise ValueError("解析抖音页面失败，无法找到视频信息")

    data = json.loads(m.group(1).strip())
    loader = data["loaderData"]
    info = (
        loader.get("video_(id)/page") or loader.get("note_(id)/page")
    )
    if not info:
        raise ValueError("无法从抖音页面 JSON 中找到视频数据")

    video_url = info["videoInfoRes"]["item_list"][0]["video"]["play_addr"]["url_list"][0]
    return video_url.replace("playwm", "play")


def extract_from_douyin(share_text: str) -> str:
    """下载抖音视频并转写音频为文字。"""
    import re
    import requests

    m = re.search(r'https?://\S+', share_text)
    if not m:
        raise ValueError("分享文本中未找到链接")
    share_url = m.group(0).rstrip('.,;')

    video_url = _resolve_douyin_video_url(share_url)

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        resp = requests.get(video_url, headers=_DOUYIN_HEADERS, stream=True, timeout=60, verify=False)
        resp.raise_for_status()
        with open(tmp_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        return extract_from_video(Path(tmp_path))
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _extract_url(text: str) -> str | None:
    """从任意文本中提取第一个 http/https URL。"""
    import re
    m = re.search(r'https?://\S+', text)
    return m.group(0).rstrip('.,;') if m else None


def _extract_share_text(raw: str) -> str:
    """
    从抖音/微信等分享文本中提取有效内容（去掉邀请语、短链、乱码后缀）。
    示例输入：0.23 复制打开抖音，看看【唐旺仔的作品】程序员转型记 #程序员 https://v.douyin.com/xxx/ Hvs:/
    """
    import re
    # 移除短链及其后面的乱码
    text = re.sub(r'https?://\S+', '', raw)
    # 移除常见邀请语前缀
    text = re.sub(r'^[\d.]+\s*(复制打开抖音|复制链接|分享给你|看看)?[，,]?', '', text.strip())
    # 找最后一个中文字符位置，截断后面的乱码
    last_cn = max((i for i, c in enumerate(text) if '\u4e00' <= c <= '\u9fff'), default=-1)
    if last_cn >= 0:
        text = text[:last_cn + 1]
    return text.strip()


def extract_content(source: str) -> tuple[str, str]:
    """
    统一入口：自动判断 source 是 URL 还是本地视频文件。

    返回 (提取的文本, source_type)
    source_type 为 "url" 或 "video"。
    """
    stripped = source.strip()

    # 支持直接 URL 或抖音/微信等分享文本中内嵌 URL
    url = stripped if stripped.startswith(("http://", "https://")) else _extract_url(stripped)
    if url:
        # 抖音链接：下载视频 → 音频转写
        if _is_douyin_url(url):
            text = extract_from_douyin(stripped)
            return text, "video"
        text = extract_from_url(url)
        if text:
            return text, "url"
        raise ValueError(f"无法从该 URL 提取到文本内容，页面可能需要登录或使用了 JS 渲染：{url}")

    video_path = Path(stripped)
    if video_path.exists() and video_path.suffix.lower() in {
        ".mp4", ".mov", ".avi", ".mkv", ".flv", ".wmv", ".webm",
    }:
        text = extract_from_video(video_path)
        return text, "video"

    raise ValueError(
        f"无法识别来源：{source!r}。"
        "请提供 http/https URL 或本地视频文件路径（.mp4/.mov/.avi 等）。"
    )
