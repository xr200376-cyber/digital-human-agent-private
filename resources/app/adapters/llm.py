import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from app.adapters.base import AdapterError, minimal_script_payload
from app.schemas import CreateVideoTaskRequest
from app.utils.files import ensure_dir, write_json


@dataclass(frozen=True)
class LLMRewriteResult:
    rewritten_scripts_path: Path
    script_scores_path: Path
    rewrite_report_path: Path


class BaseLLMAdapter:
    name = "base"

    def __init__(self, *, dry_run: bool = True, enabled: bool = True):
        self.dry_run = dry_run
        self.enabled = enabled

    def readiness(self) -> dict[str, Any]:
        blocking_items = [] if self.enabled else [f"{self.name.upper()}_ENABLED=false"]
        return {"engine": self.name, "ready": self.enabled, "blocking_items": blocking_items}

    def rewrite_scripts(self, *, reference_analysis: dict[str, Any], request: dict[str, Any], out_dir: Path) -> LLMRewriteResult:
        raise NotImplementedError


class DryRunLLMAdapter(BaseLLMAdapter):
    name = "dryrun"

    def __init__(self):
        super().__init__(dry_run=True, enabled=True)

    def rewrite_scripts(self, *, reference_analysis: dict[str, Any], request: dict[str, Any], out_dir: Path) -> LLMRewriteResult:
        ensure_dir(out_dir)
        count = int(request.get("count") or 3)
        product = request.get("product_info") or {}
        product_name = product.get("name") or product.get("product_name") or "Product"
        benefit = product.get("benefit") or product.get("value") or "help customers make a better decision"
        tone = request.get("tone") or "practical"
        platform = request.get("platform") or "douyin"
        reference_script = reference_analysis.get("reference_script", {})
        style_summary = reference_analysis.get("style_summary", {})
        hook_seed = reference_script.get("hook") or "Ask a clear question"
        cta_seed = reference_script.get("cta") or "Invite the viewer to act"

        scripts = []
        scores = []
        for index in range(1, count + 1):
            script_id = f"script_{index:03d}"
            title = f"{product_name} rewrite {index}"
            hook = f"{hook_seed} - {product_name} version {index}"
            body = (
                f"Use a {tone} tone to explain why {product_name} can {benefit}. "
                f"Keep the reference rhythm, but replace all source wording with product-specific claims."
            )
            cta = f"{cta_seed} - ask the audience to try {product_name}."
            script = {
                "script_id": script_id,
                "title": title,
                "platform": platform,
                "tone": tone,
                "hook": hook,
                "body": body,
                "cta": cta,
                "segments": [
                    {"start": 0, "end": 5, "text": hook, "type": "hook"},
                    {"start": 5, "end": 35, "text": body, "type": "body"},
                    {"start": 35, "end": 45, "text": cta, "type": "cta"},
                ],
                "source_policy": "style/structure reference only; no exact wording copied",
            }
            scripts.append(script)
            scores.append(
                {
                    "script_id": script_id,
                    "score": max(80, 94 - index),
                    "platform_fit": platform,
                    "tone_fit": tone,
                    "risk_flags": [],
                }
            )

        rewritten_scripts_path = write_json(
            out_dir / "rewritten_scripts.json",
            {
                "reference_id": request.get("reference_id"),
                "project_id": request.get("project_id"),
                "scripts": scripts,
            },
        )
        script_scores_path = write_json(out_dir / "script_scores.json", {"scores": scores})
        rewrite_report_path = write_json(
            out_dir / "rewrite_report.json",
            {
                "engine": self.name,
                "count": count,
                "platform": platform,
                "tone": tone,
                "style_summary": style_summary,
                "policy": "dry-run rewrite generated from structured reference analysis only",
            },
        )
        return LLMRewriteResult(
            rewritten_scripts_path=rewritten_scripts_path,
            script_scores_path=script_scores_path,
            rewrite_report_path=rewrite_report_path,
        )


class OpenAICompatibleAdapter(BaseLLMAdapter):
    name = "openai_compatible"
    _topic_edge_punctuation = " \t\r\n，。！？、；：,.!?;:\"'“”‘’（）()[]【】《》"
    _template_placeholder_pattern = re.compile(r"(\[[^\]\n]{1,30}\]|【[^】\n]{1,30}】|\{\{[^}\n]{1,40}\}\})")

    def __init__(
        self,
        *,
        dry_run: bool = True,
        enabled: bool = False,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str = "gpt-compatible",
        transport: httpx.BaseTransport | None = None,
    ):
        super().__init__(dry_run=dry_run, enabled=enabled and not dry_run)
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key or ""
        self.model = model or ""
        self.transport = transport

    def readiness(self) -> dict[str, Any]:
        blocking_items: list[str] = []
        if not self.enabled:
            blocking_items.append("OPENAI_COMPATIBLE_ENABLED=false")
        if not self.base_url:
            blocking_items.append("OPENAI_COMPATIBLE_BASE_URL missing")
        if not self.api_key:
            blocking_items.append("OPENAI_COMPATIBLE_API_KEY missing")
        if not self.model:
            blocking_items.append("OPENAI_COMPATIBLE_MODEL missing")
        return {
            "engine": self.name,
            "ready": not blocking_items,
            "base_url": self.base_url,
            "model": self.model,
            "blocking_items": blocking_items,
        }

    def rewrite_scripts(self, *, reference_analysis: dict[str, Any], request: dict[str, Any], out_dir: Path) -> LLMRewriteResult:
        readiness = self.readiness()
        if not readiness["ready"]:
            raise AdapterError("OpenAI-compatible LLM is not ready: " + ", ".join(readiness["blocking_items"]))
        ensure_dir(out_dir)
        payload = self._chat_payload(reference_analysis=reference_analysis, request=request)
        try:
            with httpx.Client(
                timeout=httpx.Timeout(60.0, connect=10.0),
                follow_redirects=True,
                trust_env=False,
                transport=self.transport,
            ) as client:
                response = client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        except (httpx.InvalidURL, httpx.HTTPError) as exc:
            raise AdapterError(f"OpenAI-compatible request failed: {exc}") from exc
        except ValueError as exc:
            raise AdapterError(f"OpenAI-compatible response JSON parse failed: {exc}") from exc
        if not isinstance(data, dict):
            raise AdapterError("OpenAI-compatible response was not a JSON object")
        content = self._message_content(data)
        generated = self._parse_generation(content)
        scripts = generated["scripts"]
        scores = generated["scores"]
        rewritten_scripts_path = write_json(
            out_dir / "rewritten_scripts.json",
            {
                "reference_id": request.get("reference_id"),
                "project_id": request.get("project_id"),
                "scripts": scripts,
            },
        )
        script_scores_path = write_json(out_dir / "script_scores.json", {"scores": scores})
        rewrite_report_path = write_json(
            out_dir / "rewrite_report.json",
            {
                "engine": self.name,
                "model": self.model,
                "count": len(scripts),
                "platform": request.get("platform") or "douyin",
                "tone": request.get("tone") or "practical",
                "style_summary": reference_analysis.get("style_summary", {}),
                "policy": "OpenAI-compatible rewrite generated from structured reference analysis only",
            },
        )
        return LLMRewriteResult(
            rewritten_scripts_path=rewritten_scripts_path,
            script_scores_path=script_scores_path,
            rewrite_report_path=rewrite_report_path,
        )

    async def generate_script(self, request: CreateVideoTaskRequest, out_dir: Path) -> Path:
        readiness = self.readiness()
        if not readiness["ready"]:
            raise AdapterError("OpenAI-compatible LLM is not ready: " + ", ".join(readiness["blocking_items"]))
        ensure_dir(out_dir)
        payload = self._script_chat_payload(request)
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(60.0, connect=10.0),
                follow_redirects=True,
                trust_env=False,
                transport=self.transport,
            ) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        except (httpx.InvalidURL, httpx.HTTPError) as exc:
            raise AdapterError(f"OpenAI-compatible script request failed: {exc}") from exc
        except ValueError as exc:
            raise AdapterError(f"OpenAI-compatible script response JSON parse failed: {exc}") from exc
        if not isinstance(data, dict):
            raise AdapterError("OpenAI-compatible script response was not a JSON object")
        content = self._message_content(data)
        script = self._parse_script_generation(content, request)
        return write_json(out_dir / "script.json", script)

    async def generate_title_tags(self, request: dict[str, Any], out_dir: Path) -> Path:
        readiness = self.readiness()
        if not readiness["ready"]:
            raise AdapterError("OpenAI-compatible LLM is not ready: " + ", ".join(readiness["blocking_items"]))
        ensure_dir(out_dir)
        payload = self._title_tags_chat_payload(request)
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(60.0, connect=10.0),
                follow_redirects=True,
                trust_env=False,
                transport=self.transport,
            ) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        except (httpx.InvalidURL, httpx.HTTPError) as exc:
            raise AdapterError(f"OpenAI-compatible title/tag request failed: {exc}") from exc
        except ValueError as exc:
            raise AdapterError(f"OpenAI-compatible title/tag response JSON parse failed: {exc}") from exc
        if not isinstance(data, dict):
            raise AdapterError("OpenAI-compatible title/tag response was not a JSON object")
        content = self._message_content(data)
        result = self._parse_title_tags_generation(content)
        result["llm"] = {"engine": self.name, "model": self.model, "base_url": self.base_url}
        return write_json(out_dir / "title_tags.json", result)

    def _chat_payload(self, *, reference_analysis: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
        count = int(request.get("count") or 3)
        product_info = request.get("product_info") or {}
        system = (
            "You rewrite short video scripts using only the provided structure and style. "
            "Return strict JSON with keys scripts and scores. Do not copy source wording."
        )
        user = {
            "reference_analysis": reference_analysis,
            "product_info": product_info,
            "count": count,
            "platform": request.get("platform") or "douyin",
            "tone": request.get("tone") or "practical",
            "required_script_fields": [
                "script_id",
                "title",
                "platform",
                "tone",
                "hook",
                "body",
                "cta",
                "segments",
                "source_policy",
            ],
        }
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            "temperature": 0.4,
        }

    def _script_chat_payload(self, request: CreateVideoTaskRequest) -> dict[str, Any]:
        target_char_count = None
        length_rule = None
        output_language = "zh-CN"
        language_requirements: list[str] = []
        if isinstance(request.metadata, dict):
            target_char_count = request.metadata.get("target_char_count")
            length_rule = request.metadata.get("length_rule")
            output_language = str(request.metadata.get("language") or "zh-CN")
            raw_language_requirements = request.metadata.get("language_requirements")
            if isinstance(raw_language_requirements, list):
                language_requirements = [str(item) for item in raw_language_requirements if str(item).strip()]
            inline_mode = str(request.metadata.get("mode") or "").strip().lower()
            current_script = str(request.metadata.get("current_script") or "").strip()
        else:
            inline_mode = ""
            current_script = ""
        if inline_mode == "translate":
            system = (
                "You are a strict translation engine. Translate only the provided text_to_translate. "
                "Return strict JSON only. Do not wrap the JSON in markdown. "
                "Required keys: title, hook, body, cta, segments. "
                "Put the complete translation in body and one body segment. "
                "Title, hook and cta must be empty. Hook and CTA must be empty. "
                "Do not rewrite, polish, expand, summarize, add labels, add explanations, add selling points, or add new claims."
            )
            user = {
                "text_to_translate": current_script or request.topic,
                "output_language": output_language,
                "language_rules": language_requirements,
                "required_json_shape": {
                    "title": "",
                    "hook": "",
                    "body": "translated script only",
                    "cta": "",
                    "segments": [{"start": 0, "end": request.duration_seconds, "text": "translated script only", "type": "body"}],
                },
                "forbidden_behaviors": [
                    "rewrite",
                    "expand",
                    "summarize",
                    "add hooks",
                    "add CTA",
                    "add selling points",
                    "add commentary",
                ],
            }
            return {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
                ],
                "temperature": 0.1,
            }
        planner_language = "English" if output_language == "en-US" else "Chinese"
        system = (
            f"You are a {planner_language} short-video script planner for synthetic digital-human talking-head videos. "
            "Return strict JSON only. Do not wrap the JSON in markdown. "
            "Required keys: title, hook, body, cta, segments. "
            "segments must be a list of objects with start, end, text, and type. "
            "Use the exact user topic in the title, hook, or body. "
            "Do not use placeholders such as [主题], [痛点场景], [相关动作], [产品], {{variable}}, or template labels. "
            "Do not invent prices, sales volume, certifications, customer counts, delivery promises, or unverifiable claims."
        )
        user = {
            "brand_name": request.brand_name,
            "persona": request.persona,
            "topic": request.topic,
            "must_include_topic": request.topic,
            "platform": request.platform.value if hasattr(request.platform, "value") else str(request.platform),
            "duration_seconds": request.duration_seconds,
            "target_char_count": target_char_count,
            "length_rule": length_rule,
            "fixed_script": request.fixed_script,
            "project_id": request.project_id,
            "digital_human_id": request.digital_human_id,
            "voice_profile_id": request.voice_profile_id,
            "render_profile": request.render_profile.value if hasattr(request.render_profile, "value") else str(request.render_profile),
            "video_template_id": request.video_template_id,
            "structured_context": request.metadata,
            "output_language": output_language,
            "language_rules": language_requirements,
            "forbidden_placeholders": ["[主题]", "[痛点场景]", "[相关动作]", "[产品]", "[行业]", "{{variable}}"],
            "script_rules": [
                "必须围绕 topic/must_include_topic 写，不要生成泛泛的软件介绍。",
                "每个 segment 的 text 都应是可直接朗读的中文口播句子。",
                "如果信息不足，用稳妥表达引导用户咨询，不要编造事实。",
            ],
            "policy": "Use structured context only. Do not claim facts not present in the request.",
        }
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            "temperature": 0.45,
        }

    def _title_tags_chat_payload(self, request: dict[str, Any]) -> dict[str, Any]:
        output_language = str(request.get("language") or "zh-CN")
        is_english = output_language == "en-US"
        system = (
            f"You generate {'English' if is_english else 'Chinese'} short-video publishing metadata. "
            "Return strict JSON only with keys: title, tags, keywords. "
            "Do not wrap JSON in markdown. Do not invent prices, certifications, sales volume, or guarantees."
        )
        user = {
            "topic": request.get("topic") or "",
            "script_text": request.get("script_text") or "",
            "platform": request.get("platform") or "douyin",
            "output_language": output_language,
            "language_requirements": request.get("language_requirements") or [],
            "strict_output_rule": "Use English only for title, tags, and keywords." if is_english else "Use Simplified Chinese for title, tags, and keywords.",
            "requirements": [
                "Use the same subject and selling points as script_text.",
                "title should be natural Chinese and no more than 24 Chinese characters when possible.",
                "tags should be 5 to 8 short Chinese tags without #.",
                "keywords should be 5 to 10 Chinese keywords, one concept per item.",
                "Avoid generic tags like AI口播 unless the script is actually about AI tools.",
            ],
        }
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            "temperature": 0.35,
        }

    def _message_content(self, data: dict[str, Any]) -> str:
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise AdapterError("OpenAI-compatible response missing choices")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise AdapterError("OpenAI-compatible response missing message content")
        return content

    def _parse_generation(self, content: str) -> dict[str, Any]:
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise AdapterError(f"OpenAI-compatible response was not JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise AdapterError("OpenAI-compatible response JSON missing scripts")
        scripts = data.get("scripts")
        scores = data.get("scores")
        if not isinstance(scripts, list) or not scripts:
            raise AdapterError("OpenAI-compatible response JSON missing scripts")
        if not all(isinstance(script, dict) for script in scripts):
            raise AdapterError("OpenAI-compatible response JSON missing scripts")
        required_script_fields = [
            "script_id",
            "title",
            "platform",
            "tone",
            "hook",
            "body",
            "cta",
            "segments",
            "source_policy",
        ]
        for script in scripts:
            for field in required_script_fields:
                if field not in script:
                    raise AdapterError(f"OpenAI-compatible response script missing required script field: {field}")
            if not isinstance(script["segments"], list):
                raise AdapterError("OpenAI-compatible response script segments must be a list")
        if not isinstance(scores, list):
            scores = []
        return {"scripts": scripts, "scores": scores}

    def _parse_script_generation(self, content: str, request: CreateVideoTaskRequest) -> dict[str, Any]:
        try:
            data = json.loads(self._strip_json_fence(content))
        except json.JSONDecodeError as exc:
            raise AdapterError(f"OpenAI-compatible script response was not JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise AdapterError("OpenAI-compatible script response JSON must be an object")
        if isinstance(data.get("script"), dict):
            data = data["script"]
        elif isinstance(data.get("scripts"), list) and data["scripts"] and isinstance(data["scripts"][0], dict):
            data = data["scripts"][0]

        is_inline_translate = (
            isinstance(request.metadata, dict)
            and request.metadata.get("source") == "source_video_workbench_inline_ai"
            and str(request.metadata.get("mode") or "").strip().lower() == "translate"
        )
        if is_inline_translate:
            body = str(data.get("body") or data.get("translated_text") or data.get("translation") or data.get("script_text") or "").strip()
            fallback_segments = (
                [{"start": 0, "end": request.duration_seconds, "text": body, "type": "body"}]
                if body
                else []
            )
            segments = self._normalize_script_segments(data.get("segments"), fallback_segments, request.duration_seconds)
            body_segments = [
                segment
                for segment in segments
                if str(segment.get("type") or "").strip().lower() in {"body", "translation", "translated_text"}
            ]
            if body_segments:
                segments = body_segments
            if not body and segments:
                body = "\n".join(str(segment.get("text") or "").strip() for segment in segments if str(segment.get("text") or "").strip())
            if not body:
                raise AdapterError("OpenAI-compatible translation response missing translated body")
            if not segments:
                segments = [{"start": 0.0, "end": float(request.duration_seconds), "text": body, "type": "body"}]
            fallback = {}
        else:
            fallback = minimal_script_payload(request)
            segments = self._normalize_script_segments(data.get("segments"), fallback["segments"], request.duration_seconds)
        script = {
            "brand_name": request.brand_name,
            "persona": request.persona,
            "platform": request.platform.value if hasattr(request.platform, "value") else str(request.platform),
            "duration_seconds": request.duration_seconds,
            "title": "" if is_inline_translate else str(data.get("title") or fallback["hook"]).strip(),
            "hook": "" if is_inline_translate else str(data.get("hook") or fallback["hook"]).strip(),
            "body": body if is_inline_translate else str(data.get("body") or request.fixed_script or fallback["body"]).strip(),
            "cta": "" if is_inline_translate else str(data.get("cta") or fallback["cta"]).strip(),
            "segments": segments,
            "source_policy": str(
                data.get("source_policy")
                or (
                    "translated from inline source script only"
                    if is_inline_translate
                    else "generated from structured task and project context; no raw uploaded files copied"
                )
            ),
            "source_context": {
                "project_id": request.project_id,
                "digital_human_id": request.digital_human_id,
                "metadata_keys": sorted(request.metadata.keys()),
            },
            "llm": {
                "engine": self.name,
                "model": self.model,
                "base_url": self.base_url,
            },
        }
        if not is_inline_translate:
            script = self._repair_inline_topic_anchor(script, request)
        self._validate_script_text(script, request)
        return script

    def _parse_title_tags_generation(self, content: str) -> dict[str, Any]:
        try:
            data = json.loads(self._strip_json_fence(content))
        except json.JSONDecodeError as exc:
            raise AdapterError(f"OpenAI-compatible title/tag response was not JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise AdapterError("OpenAI-compatible title/tag response JSON must be an object")
        title = str(data.get("title") or "").strip()
        tags = self._normalize_string_list(data.get("tags"))
        keywords = self._normalize_string_list(data.get("keywords"))
        if not title:
            raise AdapterError("OpenAI-compatible title/tag response missing title")
        if not tags:
            raise AdapterError("OpenAI-compatible title/tag response missing tags")
        if not keywords:
            raise AdapterError("OpenAI-compatible title/tag response missing keywords")
        return {"title": title, "tags": tags[:8], "keywords": keywords[:10]}

    @staticmethod
    def _normalize_string_list(value: Any) -> list[str]:
        if isinstance(value, str):
            candidates = re.split(r"[,，、\n]+", value)
        elif isinstance(value, list):
            candidates = value
        else:
            candidates = []
        normalized: list[str] = []
        for item in candidates:
            text = str(item or "").strip().lstrip("#").strip()
            if text and text not in normalized:
                normalized.append(text)
        return normalized

    def _combined_script_text(self, script: dict[str, Any]) -> str:
        texts = [
            str(script.get("title") or ""),
            str(script.get("hook") or ""),
            str(script.get("body") or ""),
            str(script.get("cta") or ""),
        ]
        for segment in script.get("segments") or []:
            if isinstance(segment, dict):
                texts.append(str(segment.get("text") or ""))
        return "\n".join(texts)

    def _topic_variants(self, topic: str) -> list[str]:
        original = str(topic or "").strip()
        stripped = original.strip(self._topic_edge_punctuation).strip()
        compact = re.sub(r"\s+", "", stripped)
        variants: list[str] = []
        for candidate in [original, stripped, compact]:
            if candidate and candidate not in variants:
                variants.append(candidate)
        return variants

    def _script_contains_topic(self, script: dict[str, Any], topic: str) -> bool:
        combined = self._combined_script_text(script)
        compact_combined = re.sub(r"\s+", "", combined)
        return any(variant in combined or variant in compact_combined for variant in self._topic_variants(topic))

    def _repair_inline_topic_anchor(self, script: dict[str, Any], request: CreateVideoTaskRequest) -> dict[str, Any]:
        if request.metadata.get("source") != "source_video_workbench_inline_ai":
            return script
        if str(request.metadata.get("mode") or "").strip().lower() == "translate":
            return script
        topic = str(request.topic or "").strip()
        if not topic or self._script_contains_topic(script, topic):
            return script

        fallback = minimal_script_payload(request)
        repaired = dict(script)
        repaired["title"] = f"{topic}口播文案"
        repaired["hook"] = str(fallback["hook"])
        repaired["body"] = str(fallback["body"])
        repaired["cta"] = str(fallback["cta"])
        repaired["segments"] = fallback["segments"]
        repaired["source_policy"] = (
            str(script.get("source_policy") or "generated from OpenAI-compatible model")
            + "; cloud response omitted the exact requested topic, so the inline workbench repaired the script with the requested topic"
        )
        llm = dict(repaired.get("llm") or {})
        llm["topic_anchor_repaired"] = True
        repaired["llm"] = llm
        return repaired

    def _validate_script_text(self, script: dict[str, Any], request: CreateVideoTaskRequest) -> None:
        combined = self._combined_script_text(script)
        match = self._template_placeholder_pattern.search(combined)
        if match:
            raise AdapterError(f"OpenAI-compatible script response contains template placeholders: {match.group(1)}")
        if request.metadata.get("source") == "source_video_workbench_inline_ai":
            if str(request.metadata.get("mode") or "").strip().lower() == "translate":
                return
            topic = str(request.topic or "").strip()
            if topic and not self._script_contains_topic(script, topic):
                raise AdapterError("OpenAI-compatible script response did not include the requested topic")

    def _normalize_script_segments(
        self,
        raw_segments: Any,
        fallback_segments: list[dict[str, Any]],
        duration_seconds: int,
    ) -> list[dict[str, Any]]:
        if not isinstance(raw_segments, list) or not raw_segments:
            raw_segments = fallback_segments
        segments: list[dict[str, Any]] = []
        for index, segment in enumerate(raw_segments):
            if not isinstance(segment, dict):
                continue
            try:
                start = float(segment.get("start", 0 if not segments else segments[-1]["end"]))
                end = float(segment.get("end", min(duration_seconds, start + 5)))
            except (TypeError, ValueError):
                start = float(segments[-1]["end"] if segments else 0)
                end = min(float(duration_seconds), start + 5)
            if end <= start:
                end = min(float(duration_seconds), start + 5)
            text = str(segment.get("text") or "").strip()
            if not text:
                continue
            segments.append(
                {
                    "start": round(max(0.0, start), 3),
                    "end": round(max(start + 0.5, end), 3),
                    "text": text,
                    "type": str(segment.get("type") or f"segment_{index + 1}"),
                }
            )
        if segments:
            return segments
        return fallback_segments

    @staticmethod
    def _strip_json_fence(content: str) -> str:
        text = content.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines:
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        return text


class LocalModelAdapter(BaseLLMAdapter):
    name = "local_model"

    def __init__(self, *, dry_run: bool = True, enabled: bool = False, model_path: str | None = None):
        super().__init__(dry_run=dry_run, enabled=enabled and not dry_run)
        self.model_path = model_path

    def readiness(self) -> dict[str, Any]:
        blocking_items: list[str] = []
        if not self.enabled:
            blocking_items.append("LOCAL_MODEL_ENABLED=false")
        if not self.model_path:
            blocking_items.append("LOCAL_MODEL_PATH missing")
        return {"engine": self.name, "ready": not blocking_items, "model_path": self.model_path, "blocking_items": blocking_items}

    def rewrite_scripts(self, *, reference_analysis: dict[str, Any], request: dict[str, Any], out_dir: Path) -> LLMRewriteResult:
        raise AdapterError("LocalModelAdapter is a Sprint 16 placeholder. Configure local inference later.")
