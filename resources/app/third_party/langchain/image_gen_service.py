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

    if not image_path.exists():
        raise FileNotFoundError(f"参考图不存在：{image_path}")

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
    if img_data.b64_json is not None:
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


def _doubao_image_generate(_image_path: Path, prompt: str, output_path: Path) -> Path:
    """
    Doubao (豆包 / ARK) text-to-image fallback.
    Uses OpenAI-compatible endpoint at ark.cn-beijing.volces.com.
    Enriches the prompt with a description of the reference image context.
    """
    import logging
    import openai
    import requests as req

    logging.warning("豆包兜底使用 text-to-image，参考图 %s 未被使用", _image_path)

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
    if img_data.b64_json is not None:
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
