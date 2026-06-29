"""
文本改写：调用 Kimi 将原始文本改写成不同风格，语义保持一致。
"""

from __future__ import annotations

from dataclasses import dataclass

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI


@dataclass(frozen=True)
class RewriteStyle:
    style_id: str
    display_name: str
    system_prompt: str


BUILTIN_REWRITE_STYLES: tuple[RewriteStyle, ...] = (
    RewriteStyle(
        style_id="professional",
        display_name="专业严谨",
        system_prompt=(
            "你是一位专业编辑，请将用户提供的文本改写为语言严谨、逻辑清晰、措辞专业的正式风格。"
            "保留原文核心信息和表达意图，不要增加或删减关键内容。"
            "直接输出改写后的文本，不要解释或添加任何前缀。"
        ),
    ),
    RewriteStyle(
        style_id="casual",
        display_name="轻松口语",
        system_prompt=(
            "你是一位擅长口语化写作的编辑，请将用户提供的文本改写成轻松自然、贴近日常对话的风格。"
            "保留原文的核心信息，语气亲切，避免过于书面化的表达。"
            "直接输出改写后的文本，不要解释或添加任何前缀。"
        ),
    ),
    RewriteStyle(
        style_id="news",
        display_name="新闻播报",
        system_prompt=(
            "你是一位专业新闻播音员，请将用户提供的文本改写为适合新闻播报的风格："
            "语言简洁凝练、客观中立、节奏感强，适合数字人朗读播报。"
            "保留原文核心事实，用短句，避免复杂从句。"
            "直接输出改写后的文本，不要解释或添加任何前缀。"
        ),
    ),
)

_STYLES_BY_ID: dict[str, RewriteStyle] = {s.style_id: s for s in BUILTIN_REWRITE_STYLES}


def get_style(style_id: str) -> RewriteStyle:
    """按 style_id 查找，找不到抛 ValueError。"""
    if style_id not in _STYLES_BY_ID:
        valid = ", ".join(_STYLES_BY_ID)
        raise ValueError(f"未知改写风格：{style_id!r}，可用值：{valid}")
    return _STYLES_BY_ID[style_id]


def build_rewrite_chain(llm: ChatOpenAI, style: RewriteStyle) -> Runnable:
    """构建改写 chain：system prompt 注入风格指令，human 消息带原文。"""
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", style.system_prompt),
            ("human", "请改写以下文本：\n\n{original_text}"),
        ]
    )
    return prompt | llm | StrOutputParser()


def rewrite_text(original_text: str, style_id: str, llm: ChatOpenAI) -> str:
    """
    对外接口：传入原文和风格 ID，返回改写后的文本。

    llm 由调用方传入（通常复用 app.state 中的共享实例）。
    """
    style = get_style(style_id)
    chain = build_rewrite_chain(llm, style)
    return chain.invoke({"original_text": original_text})
