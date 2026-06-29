"""
Moonshot / Kimi 共享配置。

仅保留数字人工作流所需的最小能力：
- 读取 `.env`
- 构建一个 OpenAI 兼容的 Kimi 客户端，供文本改写复用
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI


def project_root() -> Path:
    return Path(__file__).resolve().parent


def load_env() -> None:
    """从项目根目录加载 `.env`。"""
    env_path = project_root() / ".env"
    load_dotenv(env_path)

    key = (os.getenv("MOONSHOT_API_KEY") or "").strip()
    if key:
        os.environ["MOONSHOT_API_KEY"] = key


def build_moonshot_llm() -> ChatOpenAI | None:
    """构建工作流使用的 Kimi 客户端。"""
    key = (os.getenv("MOONSHOT_API_KEY") or "").strip()
    if not key:
        return None
    return ChatOpenAI(
        base_url="https://api.moonshot.cn/v1",
        api_key=key,
        model=os.getenv("MOONSHOT_MODEL", "kimi-k2.5"),
        temperature=float(os.getenv("MOONSHOT_TEMPERATURE", "1")),
    )
