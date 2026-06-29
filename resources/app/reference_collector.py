from __future__ import annotations

from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
import re
from typing import Callable
from urllib.parse import urlparse

import httpx

from app.schemas import CollectReferenceLinkRequest, ReferenceContentCapture
from app.settings import Settings
from app.utils.files import ensure_dir, write_json


FetchHtml = Callable[[str], tuple[str, str, str]]


class _PageMetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.title_parts: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "title":
            self._in_title = True
            return
        if tag.lower() != "meta":
            return
        data = {str(key).lower(): value or "" for key, value in attrs}
        key = (data.get("property") or data.get("name") or data.get("itemprop") or "").strip().lower()
        content = (data.get("content") or "").strip()
        if key and content and key not in self.meta:
            self.meta[key] = unescape(content)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title and data.strip():
            self.title_parts.append(data.strip())

    @property
    def title(self) -> str:
        return unescape(" ".join(self.title_parts).strip())


class ReferenceContentCollector:
    """Collect public reference-link metadata without bypassing platform access controls."""

    def __init__(self, settings: Settings, fetch_html: FetchHtml | None = None):
        self.settings = settings
        self.fetch_html = fetch_html

    def collect(self, project_id: str, request: CollectReferenceLinkRequest) -> ReferenceContentCapture:
        source_url = self._validate_url(request.url)
        platform = self.detect_platform(source_url)
        try:
            content_type, html_text, final_url = self.fetch_html(source_url) if self.fetch_html else self._fetch_html(source_url)
            capture = self._capture_from_html(
                project_id=project_id,
                source_url=source_url,
                final_url=final_url,
                platform=platform,
                content_type=content_type,
                html_text=html_text,
                request=request,
            )
        except Exception as exc:  # noqa: BLE001 - user-facing collection should not crash the workbench.
            capture = self._blocked_capture(project_id, source_url, platform, str(exc), request)
        return self._save(capture)

    def _fetch_html(self, url: str) -> tuple[str, str, str]:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
        }
        with httpx.Client(follow_redirects=True, timeout=12.0, headers=headers) as client:
            response = client.get(url)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        return content_type, response.text, str(response.url)

    @staticmethod
    def detect_platform(url: str) -> str:
        host = (urlparse(url).netloc or "").lower()
        if "douyin.com" in host or "iesdouyin.com" in host:
            return "douyin"
        if "xiaohongshu.com" in host or "xhslink.com" in host:
            return "xiaohongshu"
        if "kuaishou.com" in host or "chenzhongtech.com" in host:
            return "kuaishou"
        if "bilibili.com" in host or "b23.tv" in host:
            return "bilibili"
        if "weixin.qq.com" in host or "channels.weixin.qq.com" in host:
            return "shipinhao"
        return "generic_web"

    def _capture_from_html(
        self,
        *,
        project_id: str,
        source_url: str,
        final_url: str,
        platform: str,
        content_type: str,
        html_text: str,
        request: CollectReferenceLinkRequest,
    ) -> ReferenceContentCapture:
        parser = _PageMetadataParser()
        parser.feed(html_text or "")
        title = self._first_text(
            parser.meta.get("og:title"),
            parser.meta.get("twitter:title"),
            parser.title,
        )
        description = self._first_text(
            parser.meta.get("og:description"),
            parser.meta.get("description"),
            parser.meta.get("twitter:description"),
        )
        cover_url = self._first_text(
            parser.meta.get("og:image"),
            parser.meta.get("twitter:image"),
            parser.meta.get("image"),
        )
        video_url = self._first_text(
            parser.meta.get("og:video"),
            parser.meta.get("og:video:url"),
            parser.meta.get("og:video:secure_url"),
            parser.meta.get("twitter:player:stream"),
        )
        is_video_response = str(content_type).lower().startswith("video/")
        if not video_url and (self._looks_like_video_url(final_url) or is_video_response):
            video_url = final_url
        content_text = self._content_text(platform, title, description, source_url)
        script_seed = self._script_seed(title, description, request.metadata)
        downloadable = self._looks_like_video_url(video_url) or is_video_response
        status = "captured" if title or description or video_url else "blocked"
        message = (
            "平台链接已采集。"
            if status == "captured"
            else "平台限制，未能从公开页面提取可用文案。"
        )
        next_action = (
            "可以点击爆款文案或 AI生成继续生成口播脚本。"
            if status == "captured"
            else "请手动下载参考视频后上传，或复制平台文案到输入框。"
        )
        return ReferenceContentCapture(
            project_id=project_id,
            source_url=source_url,
            final_url=final_url,
            platform=platform,
            status=status,
            title=title,
            description=description,
            cover_url=cover_url,
            video_url=video_url,
            content_text=content_text,
            script_seed=script_seed,
            downloadable=downloadable,
            message=message,
            recommended_next_action=next_action,
            source_metadata={
                "source_url": source_url,
                "final_url": final_url,
                "platform": platform,
                "content_type": content_type,
                "collected_at": datetime.now(timezone.utc).isoformat(),
                "policy": "public metadata collection only; no login, captcha, paywall, DRM, or private content bypass",
            },
        )

    def _blocked_capture(
        self,
        project_id: str,
        source_url: str,
        platform: str,
        reason: str,
        request: CollectReferenceLinkRequest,
    ) -> ReferenceContentCapture:
        return ReferenceContentCapture(
            project_id=project_id,
            source_url=source_url,
            platform=platform,
            status="blocked",
            title="",
            description="",
            content_text=f"平台：{platform}\n来源链接：{source_url}\n采集失败：平台限制或网络不可访问。",
            script_seed=str(request.metadata.get("fallback_text") or "").strip(),
            downloadable=False,
            message=f"平台限制，无法自动采集该链接：{reason}",
            recommended_next_action="请手动下载参考视频后上传，或复制平台文案到输入框。",
            source_metadata={
                "source_url": source_url,
                "platform": platform,
                "error": reason,
                "collected_at": datetime.now(timezone.utc).isoformat(),
                "policy": "public metadata collection only; blocked platform access was not bypassed",
            },
        )

    def _save(self, capture: ReferenceContentCapture) -> ReferenceContentCapture:
        out_dir = ensure_dir(
            self.settings.storage_dir
            / "projects"
            / capture.project_id
            / "reference_collections"
            / capture.collection_id
        )
        path = out_dir / "collection.json"
        capture.collection_json = str(path)
        write_json(path, capture.model_dump(mode="json"))
        return capture

    @staticmethod
    def _validate_url(url: str) -> str:
        clean = str(url or "").strip()
        parsed = urlparse(clean)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("请输入 http 或 https 开头的平台链接。")
        return clean

    @staticmethod
    def _first_text(*values: str | None) -> str:
        for value in values:
            clean = re.sub(r"\s+", " ", str(value or "")).strip()
            if clean:
                return unescape(clean)
        return ""

    @staticmethod
    def _looks_like_video_url(url: str | None) -> bool:
        return bool(re.search(r"\.(mp4|mov|m4v|webm)(\?|#|$)", str(url or ""), re.IGNORECASE))

    @staticmethod
    def _content_text(platform: str, title: str, description: str, source_url: str) -> str:
        lines = [f"平台：{platform}", f"来源链接：{source_url}"]
        if title:
            lines.append(f"标题：{title}")
        if description:
            lines.append(f"文案：{description}")
        return "\n".join(lines)

    @staticmethod
    def _script_seed(title: str, description: str, metadata: dict[str, object]) -> str:
        fallback = str(metadata.get("fallback_text") or "").strip()
        text = "\n".join([item for item in [title, description, fallback] if item])
        return text[:3500]
