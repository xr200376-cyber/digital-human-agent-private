"""
TTS 服务：使用微软 Edge TTS（免费，无需 API Key）生成中文语音。

依赖：edge-tts>=6.1.0
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path


async def _tts_edge_async(text: str, voice: str, output_path: Path) -> None:
    """异步调用 edge-tts 生成音频文件。"""
    try:
        import edge_tts
    except ImportError as e:
        raise ImportError("请先安装 edge-tts：pip install edge-tts") from e

    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(output_path))


def text_to_speech(
    text: str,
    output_path: Path,
    voice: str | None = None,
) -> Path:
    """
    将文本转换为 MP3 语音文件。

    voice 默认从环境变量 TTS_VOICE 读取，未设置则用 zh-CN-XiaoxiaoNeural。
    返回写入成功的 output_path。
    """
    if voice is None:
        voice = os.getenv("TTS_VOICE", "zh-CN-XiaoxiaoNeural")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    asyncio.run(_tts_edge_async(text, voice, output_path))
    return output_path
