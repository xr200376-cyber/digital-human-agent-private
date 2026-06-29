from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field


Runner = Callable[..., subprocess.CompletedProcess[str]]


class VideoParserResult(BaseModel):
    status: str = "blocked"
    engine: str = "yt_dlp"
    platform: str = "generic_web"
    source_url: str = ""
    final_url: str = ""
    title: str = ""
    description: str = ""
    duration_seconds: float | None = None
    thumbnail_url: str = ""
    video_url: str = ""
    stored_video_path: str | None = None
    downloadable: bool = False
    message: str = ""
    source_metadata: dict[str, Any] = Field(default_factory=dict)


class LocalVideoParserAdapter:
    """Resolve public video links into direct media URLs without logging in or bypassing access controls."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        ytdlp_path: str | None = None,
        douyin_downloader_root: str | Path | None = None,
        download_dir: str | Path | None = None,
        timeout_seconds: int = 120,
        max_download_mb: int = 500,
        runner: Runner | None = None,
        browser_cookie_sources: tuple[str, ...] = ("edge", "chrome"),
        engine: str = "douyin_downloader",
        python_executable: str | Path | None = None,
        cloud_provider_order: str | list[str] | tuple[str, ...] | None = None,
        aivo_parser_base_url: str | None = None,
        aivo_parser_endpoint: str | None = None,
        aivo_parser_token: str | None = None,
        tikhub_base_url: str | None = None,
        tikhub_api_key: str | None = None,
        tikhub_endpoint: str | None = None,
        istero_base_url: str | None = None,
        istero_api_key: str | None = None,
        istero_endpoint: str | None = None,
        evil0ctal_base_url: str | None = None,
        evil0ctal_endpoint: str | None = None,
        http_client: Any | None = None,
    ) -> None:
        self.enabled = enabled
        self.ytdlp_path = ytdlp_path or ""
        self.douyin_downloader_root = (
            Path(douyin_downloader_root) if douyin_downloader_root else Path("third_party/douyin-downloader")
        )
        self.download_dir = Path(download_dir) if download_dir else None
        self.timeout_seconds = timeout_seconds
        self.max_download_mb = max_download_mb
        self.runner = runner or subprocess.run
        self.browser_cookie_sources = tuple(source for source in browser_cookie_sources if source)
        self.engine = (engine or "douyin_downloader").strip().lower()
        self.python_executable = str(python_executable or os.getenv("PYTHON_PATH") or "").strip()
        self.cloud_provider_order = self._normalize_provider_order(
            cloud_provider_order
            or os.getenv("VIDEO_PARSER_CLOUD_PROVIDER_ORDER")
            or "aivo_proxy,tikhub,istero,evil0ctal"
        )
        self.aivo_parser_base_url = self._clean_base_url(
            aivo_parser_base_url or os.getenv("AIVO_PARSER_BASE_URL") or ""
        )
        self.aivo_parser_endpoint = str(
            aivo_parser_endpoint or os.getenv("AIVO_PARSER_ENDPOINT") or "/v1/video-parser/parse"
        ).strip()
        self.aivo_parser_token = str(aivo_parser_token or os.getenv("AIVO_PARSER_TOKEN") or "").strip()
        self.tikhub_base_url = self._clean_base_url(tikhub_base_url or os.getenv("TIKHUB_BASE_URL") or "https://api.tikhub.io")
        self.tikhub_api_key = str(tikhub_api_key or os.getenv("TIKHUB_API_KEY") or "").strip()
        self.tikhub_endpoint = str(
            tikhub_endpoint or os.getenv("TIKHUB_DOUYIN_ENDPOINT") or "/api/v1/hybrid/video_data"
        ).strip()
        self.istero_base_url = self._clean_base_url(istero_base_url or os.getenv("ISTERO_BASE_URL") or "")
        self.istero_api_key = str(istero_api_key or os.getenv("ISTERO_API_KEY") or "").strip()
        self.istero_endpoint = str(
            istero_endpoint or os.getenv("ISTERO_DOUYIN_ENDPOINT") or "/service/api/douyin-video-downloader"
        ).strip()
        self.evil0ctal_base_url = self._clean_base_url(
            evil0ctal_base_url or os.getenv("EVIL0CTAL_DOUYIN_API_BASE_URL") or ""
        )
        self.evil0ctal_endpoint = str(
            evil0ctal_endpoint or os.getenv("EVIL0CTAL_DOUYIN_API_ENDPOINT") or "/api/hybrid/video_data"
        ).strip()
        self.http_client = http_client

    def parse(self, url: str, platform: str = "generic_web") -> VideoParserResult:
        source_url = str(url or "").strip()
        if not self._valid_url(source_url):
            return self._result(
                status="blocked",
                platform=platform,
                source_url=source_url,
                message="没有检测到有效的视频链接，请粘贴 http 或 https 开头的完整链接。",
            )
        if self._looks_like_video_url(source_url):
            return self._result(
                status="parsed",
                engine="direct_url",
                platform=platform,
                source_url=source_url,
                final_url=source_url,
                video_url=source_url,
                downloadable=True,
                message="检测到可直接下载的视频链接。",
            )
        if not self.enabled:
            return self._result(
                status="disabled",
                platform=platform,
                source_url=source_url,
                message="本地视频解析服务未启用，请在桌面设置中开启。",
            )

        if platform == "douyin" and self.engine in {"douyin_downloader", "douyin-downloader", "jiji262"}:
            local_result = self._parse_with_douyin_downloader(source_url, platform)
            if local_result.downloadable and local_result.video_url:
                return local_result
            cloud_result = self._parse_with_cloud_providers(source_url, platform, previous_result=local_result)
            if cloud_result.status != "unavailable":
                return cloud_result
            return local_result

        executable = self._resolve_ytdlp()
        if not executable:
            return self._result(
                status="unavailable",
                platform=platform,
                source_url=source_url,
                message="本地视频解析引擎未安装：请安装 yt-dlp 后重试，或先下载视频再上传。",
            )

        command = self._ytdlp_command(executable, source_url)
        try:
            completed = self.runner(
                command,
                capture_output=True,
                text=True,
                timeout=max(10, self.timeout_seconds),
                check=False,
                encoding="utf-8",
                errors="replace",
            )
        except subprocess.TimeoutExpired:
            return self._result(
                status="blocked",
                platform=platform,
                source_url=source_url,
                message="本地视频解析超时，请稍后重试或先下载视频再上传。",
                source_metadata={"parser_engine": "yt_dlp", "command": self._safe_command(command)},
            )
        except Exception as exc:  # noqa: BLE001 - user-facing parser should not crash the workbench.
            return self._result(
                status="blocked",
                platform=platform,
                source_url=source_url,
                message=f"本地视频解析失败：{type(exc).__name__}: {exc}",
                source_metadata={"parser_engine": "yt_dlp", "command": self._safe_command(command)},
            )

        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            if self._should_retry_with_browser_cookies(detail):
                cookie_result = self._parse_with_browser_cookies(executable, source_url, platform)
                if cookie_result.downloadable and cookie_result.video_url:
                    return cookie_result
            return self._result(
                status="blocked",
                platform=platform,
                source_url=source_url,
                message=self._blocked_message(detail),
                source_metadata={
                    "parser_engine": "yt_dlp",
                    "returncode": completed.returncode,
                    "stderr": detail[:1000],
                    "command": self._safe_command(command),
                },
            )

        return self._from_ytdlp_json(source_url, platform, completed.stdout)

    def _parse_with_cloud_providers(
        self,
        source_url: str,
        platform: str,
        *,
        previous_result: VideoParserResult | None = None,
    ) -> VideoParserResult:
        attempts: list[dict[str, Any]] = []
        enabled_providers = 0
        actionable_result: VideoParserResult | None = None
        for provider in self.cloud_provider_order:
            config = self._cloud_provider_config(provider)
            if not config:
                attempts.append({"provider": provider, "status": "skipped", "reason": "not_configured"})
                continue
            enabled_providers += 1
            result = self._parse_with_cloud_provider(source_url, platform, config)
            attempts.append(
                {
                    "provider": provider,
                    "status": result.status,
                    "downloadable": result.downloadable,
                    "message": result.message,
                    "http_status": result.source_metadata.get("http_status"),
                }
            )
            if actionable_result is None and self._is_actionable_cloud_failure(result):
                actionable_result = result
            if result.downloadable and result.video_url:
                result.source_metadata = {
                    **result.source_metadata,
                    "parser_attempts": attempts,
                    "local_parser_status": previous_result.status if previous_result else "",
                    "local_parser_message": previous_result.message if previous_result else "",
                }
                return result

        if enabled_providers == 0:
            return self._result(
                status="unavailable",
                engine="cloud_parser",
                platform=platform,
                source_url=source_url,
                message="未配置第三方解析服务；系统会提示客户从官方客户端保存视频后自动接收。",
                source_metadata={"parser_engine": "cloud_parser", "parser_attempts": attempts},
            )
        if actionable_result is not None:
            actionable_result.source_metadata = {
                **actionable_result.source_metadata,
                "parser_attempts": attempts,
                "local_parser_status": previous_result.status if previous_result else "",
                "local_parser_message": previous_result.message if previous_result else "",
            }
            return actionable_result
        return self._result(
            status="blocked",
            engine="cloud_parser",
            platform=platform,
            source_url=source_url,
            message="本地解析和第三方解析服务都没有拿到可用视频流。请在官方客户端保存视频，或换一个公开视频链接。",
            source_metadata={
                "parser_engine": "cloud_parser",
                "parser_attempts": attempts,
                "local_parser_status": previous_result.status if previous_result else "",
                "local_parser_message": previous_result.message if previous_result else "",
            },
        )

    def _parse_with_cloud_provider(
        self,
        source_url: str,
        platform: str,
        config: dict[str, Any],
    ) -> VideoParserResult:
        provider = str(config["provider"])
        endpoint = str(config["endpoint"])
        base_url = str(config["base_url"])
        url = base_url + endpoint if endpoint.startswith("/") else f"{base_url}/{endpoint}"
        headers = dict(config.get("headers") or {})
        params = {"url": source_url, **dict(config.get("params") or {})}
        try:
            payload = self._cloud_get_json(url, params=params, headers=headers)
        except httpx.TimeoutException:
            return self._result(
                status="blocked",
                engine=provider,
                platform=platform,
                source_url=source_url,
                message=f"{self._cloud_provider_label(provider)}解析超时，请稍后重试或改用客户端下载。",
                source_metadata={"parser_engine": provider, "endpoint": self._safe_url(url)},
            )
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code if exc.response is not None else 0
            return self._result(
                status="blocked",
                engine=provider,
                platform=platform,
                source_url=source_url,
                message=self._cloud_http_error_message(provider, status_code),
                source_metadata={
                    "parser_engine": provider,
                    "endpoint": self._safe_url(url),
                    "http_status": status_code,
                },
            )
        except Exception as exc:  # noqa: BLE001 - external parser errors must stay readable.
            return self._result(
                status="blocked",
                engine=provider,
                platform=platform,
                source_url=source_url,
                message=f"{self._cloud_provider_label(provider)}解析失败：{type(exc).__name__}: {exc}",
                source_metadata={"parser_engine": provider, "endpoint": self._safe_url(url)},
            )

        result = self._from_cloud_payload(source_url, platform, provider, payload)
        result.source_metadata = {
            **result.source_metadata,
            "endpoint": self._safe_url(url),
            "payload_keys": sorted(payload.keys())[:20] if isinstance(payload, dict) else [],
        }
        return result

    def _cloud_get_json(self, url: str, *, params: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        client = self.http_client
        if client is not None:
            response = client.get(url, params=params, headers=headers, timeout=max(10, self.timeout_seconds))
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, dict) else {"data": data}

        with httpx.Client(timeout=max(10, self.timeout_seconds), follow_redirects=True) as live_client:
            response = live_client.get(url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, dict) else {"data": data}

    def _cloud_provider_config(self, provider: str) -> dict[str, Any] | None:
        normalized = provider.lower().strip().replace("-", "_")
        if normalized in {"aivo_proxy", "aivo", "internal"}:
            if not self.aivo_parser_base_url:
                return None
            headers = {"Accept": "application/json"}
            if self.aivo_parser_token:
                headers["Authorization"] = f"Bearer {self.aivo_parser_token}"
            return {
                "provider": "aivo_proxy",
                "base_url": self.aivo_parser_base_url,
                "endpoint": self.aivo_parser_endpoint,
                "headers": headers,
                "params": {},
            }
        if normalized == "tikhub":
            if not self.tikhub_base_url or not self.tikhub_api_key:
                return None
            return {
                "provider": "tikhub",
                "base_url": self.tikhub_base_url,
                "endpoint": self.tikhub_endpoint,
                "headers": {
                    "Authorization": f"Bearer {self.tikhub_api_key}",
                    "Accept": "application/json",
                },
                "params": {"minimal": "false"},
            }
        if normalized == "istero":
            if not self.istero_base_url:
                return None
            headers = {"Accept": "application/json"}
            if self.istero_api_key:
                headers["Authorization"] = f"Bearer {self.istero_api_key}"
                headers["X-API-Key"] = self.istero_api_key
            return {
                "provider": "istero",
                "base_url": self.istero_base_url,
                "endpoint": self.istero_endpoint,
                "headers": headers,
                "params": {},
            }
        if normalized in {"evil0ctal", "douyin_tiktok_download_api", "self_hosted"}:
            if not self.evil0ctal_base_url:
                return None
            return {
                "provider": "evil0ctal",
                "base_url": self.evil0ctal_base_url,
                "endpoint": self.evil0ctal_endpoint,
                "headers": {"Accept": "application/json"},
                "params": {"minimal": "false"},
            }
        return None

    def _from_cloud_payload(
        self,
        source_url: str,
        platform: str,
        provider: str,
        payload: dict[str, Any],
    ) -> VideoParserResult:
        video_url = self._find_video_url(payload)
        title = self._find_first_text(payload, {"title", "desc", "description", "caption"}) or ""
        description = self._find_first_text(payload, {"description", "desc", "caption", "text"}) or ""
        thumbnail_url = self._find_first_url_by_keys(payload, {"cover", "thumbnail", "poster", "origin_cover"}) or ""
        duration_seconds = self._duration(
            self._find_first_value(payload, {"duration", "duration_seconds", "video_duration"})
        )
        final_url = self._find_first_url_by_keys(payload, {"share_url", "webpage_url", "aweme_url", "url"}) or source_url
        if not video_url:
            return self._result(
                status="blocked",
                engine=provider,
                platform=platform,
                source_url=source_url,
                final_url=final_url,
                title=title,
                description=description,
                duration_seconds=duration_seconds,
                thumbnail_url=thumbnail_url,
                message=f"{self._cloud_provider_label(provider)}没有返回可用视频流，可能该内容受平台限制。",
                source_metadata={"parser_engine": provider},
            )
        return self._result(
            status="parsed",
            engine=provider,
            platform=platform,
            source_url=source_url,
            final_url=final_url,
            title=title,
            description=description,
            duration_seconds=duration_seconds,
            thumbnail_url=thumbnail_url,
            video_url=video_url,
            downloadable=True,
            message=f"{self._cloud_provider_label(provider)}解析成功，已拿到可用视频流。",
            source_metadata={"parser_engine": provider},
        )

    def _parse_with_douyin_downloader(self, source_url: str, platform: str) -> VideoParserResult:
        root = self._resolve_douyin_downloader_root()
        run_py = root / "run.py"
        if not run_py.exists():
            return self._result(
                status="unavailable",
                engine="douyin_downloader",
                platform=platform,
                source_url=source_url,
                message="抖音专用解析器未安装：缺少 third_party/douyin-downloader/run.py，请先随客户版一起打包。",
                source_metadata={"parser_engine": "douyin_downloader", "root": str(root)},
            )

        python_command = self._resolve_python_command()
        if not python_command:
            return self._result(
                status="unavailable",
                engine="douyin_downloader",
                platform=platform,
                source_url=source_url,
                message="抖音专用解析器需要本机可用的 Python。请在桌面设置里配置 PYTHON_PATH，或安装 Python 后重试；也可以先从客户端保存视频后本地上传。",
                source_metadata={"parser_engine": "douyin_downloader", "root": str(root)},
            )

        download_dir = self.download_dir or Path("storage") / "reference_collections" / "douyin_downloader"
        download_dir.mkdir(parents=True, exist_ok=True)
        config_path = download_dir / "douyin_downloader_config.yml"
        self._write_douyin_downloader_config(config_path, download_dir)
        before = self._media_files(download_dir)
        command = [
            *python_command,
            str(run_py),
            "-c",
            str(config_path),
            "-u",
            source_url,
            "-p",
            str(download_dir),
            "-t",
            "1",
            "--show-warnings",
        ]
        env = os.environ.copy()
        env.setdefault("PYTHONUTF8", "1")
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env.setdefault("TERM", "dumb")
        try:
            completed = self.runner(
                command,
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=max(30, self.timeout_seconds),
                check=False,
                encoding="utf-8",
                errors="replace",
                env=env,
            )
        except subprocess.TimeoutExpired:
            return self._result(
                status="blocked",
                engine="douyin_downloader",
                platform=platform,
                source_url=source_url,
                message="抖音专用解析器超时：平台可能风控、网络慢或链接需要登录验证，请手动下载视频后上传。",
                source_metadata={"parser_engine": "douyin_downloader", "command": self._safe_command(command)},
            )
        except Exception as exc:  # noqa: BLE001 - parser should surface clear blockers.
            return self._result(
                status="blocked",
                engine="douyin_downloader",
                platform=platform,
                source_url=source_url,
                message=f"抖音专用解析器调用失败：{type(exc).__name__}: {exc}",
                source_metadata={"parser_engine": "douyin_downloader", "command": self._safe_command(command)},
            )

        after = self._media_files(download_dir)
        new_files = [path for path in after if path not in before]
        video_path = self._pick_video_file(new_files) or self._pick_video_file(after)
        if completed.returncode == 0 and video_path and video_path.exists():
            return self._result(
                status="parsed",
                engine="douyin_downloader",
                platform=platform,
                source_url=source_url,
                final_url=source_url,
                video_url=str(video_path),
                stored_video_path=str(video_path),
                downloadable=True,
                message="抖音专用解析器已下载公开视频文件，接下来会抽取音频并转写文案。",
                source_metadata={
                    "parser_engine": "douyin_downloader",
                    "download_dir": str(download_dir),
                    "stdout": (completed.stdout or "")[-1200:],
                    "stderr": (completed.stderr or "")[-1200:],
                },
            )

        output = "\n".join(
            item for item in [(completed.stdout or "").strip(), (completed.stderr or "").strip()] if item
        )
        return self._result(
            status="blocked",
            engine="douyin_downloader",
            platform=platform,
            source_url=source_url,
            message=self._douyin_downloader_blocked_message(output),
            source_metadata={
                "parser_engine": "douyin_downloader",
                "returncode": completed.returncode,
                "download_dir": str(download_dir),
                "stdout": (completed.stdout or "")[-1200:],
                "stderr": (completed.stderr or "")[-1200:],
                "command": self._safe_command(command),
            },
        )

    def _parse_with_browser_cookies(self, executable: str, source_url: str, platform: str) -> VideoParserResult:
        attempts: list[dict[str, object]] = []
        for cookie_source in self.browser_cookie_sources:
            command = self._ytdlp_command(executable, source_url, cookie_source=cookie_source)
            try:
                completed = self.runner(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=max(10, self.timeout_seconds),
                    check=False,
                    encoding="utf-8",
                    errors="replace",
                )
            except subprocess.TimeoutExpired:
                attempts.append({"cookie_source": cookie_source, "status": "timeout"})
                continue
            except Exception as exc:  # noqa: BLE001 - browser cookie retry must not crash the workbench.
                attempts.append({"cookie_source": cookie_source, "status": "error", "error": str(exc)[:300]})
                continue
            if completed.returncode == 0:
                result = self._from_ytdlp_json(source_url, platform, completed.stdout)
                result.source_metadata = {
                    **result.source_metadata,
                    "cookie_retry": True,
                    "cookie_source": cookie_source,
                }
                if result.message:
                    result.message = f"{result.message}（已使用本机{self._browser_label(cookie_source)}登录态）"
                return result
            attempts.append(
                {
                    "cookie_source": cookie_source,
                    "status": "failed",
                    "stderr": (completed.stderr or completed.stdout or "").strip()[:500],
                }
            )
        return self._result(
            status="blocked",
            platform=platform,
            source_url=source_url,
            message="平台限制：已尝试读取本机浏览器登录态，但仍未拿到可下载视频。请在抖音客户端点官方下载，或手动下载后上传。",
            source_metadata={"parser_engine": "yt_dlp", "cookie_retry": True, "cookie_attempts": attempts},
        )

    @staticmethod
    def _ytdlp_command(executable: str, source_url: str, *, cookie_source: str | None = None) -> list[str]:
        command = [
            executable,
            "--dump-single-json",
            "--no-playlist",
            "--no-warnings",
            "--format",
            "best[ext=mp4]/best",
        ]
        if cookie_source:
            command.extend(["--cookies-from-browser", cookie_source])
        command.append(source_url)
        return command

    def _from_ytdlp_json(self, source_url: str, platform: str, stdout: str) -> VideoParserResult:
        try:
            payload = json.loads(stdout or "{}")
        except json.JSONDecodeError as exc:
            return self._result(
                status="blocked",
                platform=platform,
                source_url=source_url,
                message=f"本地视频解析失败：解析结果不是有效 JSON：{exc}",
                source_metadata={"parser_engine": "yt_dlp"},
            )
        if not isinstance(payload, dict):
            return self._result(
                status="blocked",
                platform=platform,
                source_url=source_url,
                message="本地视频解析失败：解析结果格式不正确。",
                source_metadata={"parser_engine": "yt_dlp"},
            )

        entry = self._first_video_entry(payload)
        video_url = self._best_video_url(entry)
        if not video_url:
            return self._result(
                status="blocked",
                platform=platform,
                source_url=source_url,
                final_url=str(entry.get("webpage_url") or entry.get("original_url") or ""),
                title=str(entry.get("title") or ""),
                description=str(entry.get("description") or ""),
                duration_seconds=self._duration(entry.get("duration")),
                thumbnail_url=str(entry.get("thumbnail") or ""),
                message="平台限制或解析结果中没有可下载视频文件，请手动下载视频后上传。",
                source_metadata={"parser_engine": "yt_dlp", "extractor": entry.get("extractor_key") or ""},
            )

        return self._result(
            status="parsed",
            engine="yt_dlp",
            platform=platform,
            source_url=source_url,
            final_url=str(entry.get("webpage_url") or entry.get("original_url") or source_url),
            title=str(entry.get("title") or ""),
            description=str(entry.get("description") or ""),
            duration_seconds=self._duration(entry.get("duration")),
            thumbnail_url=str(entry.get("thumbnail") or ""),
            video_url=video_url,
            downloadable=True,
            message="本地视频解析成功，已拿到可下载视频地址。",
            source_metadata={
                "parser_engine": "yt_dlp",
                "extractor": entry.get("extractor_key") or entry.get("extractor") or "",
                "format_id": entry.get("format_id") or "",
            },
        )

    def _resolve_ytdlp(self) -> str:
        if self.ytdlp_path:
            return self.ytdlp_path
        for candidate in self._packaged_ytdlp_candidates():
            if candidate.exists():
                return str(candidate.resolve())
        return shutil.which("yt-dlp") or shutil.which("yt-dlp.exe") or ""

    @staticmethod
    def _packaged_ytdlp_candidates() -> list[Path]:
        storage_dir = Path(os.environ.get("STORAGE_DIR") or "storage")
        runtime_bin = storage_dir / "runtime_bin"
        candidates = [
            runtime_bin / "yt-dlp.exe",
            runtime_bin / "yt-dlp",
            Path.cwd() / "storage" / "runtime_bin" / "yt-dlp.exe",
            Path.cwd() / "storage" / "runtime_bin" / "yt-dlp",
        ]
        seen: set[Path] = set()
        unique: list[Path] = []
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved not in seen:
                seen.add(resolved)
                unique.append(candidate)
        return unique

    @staticmethod
    def _first_video_entry(payload: dict[str, Any]) -> dict[str, Any]:
        entries = payload.get("entries")
        if isinstance(entries, list):
            for item in entries:
                if isinstance(item, dict):
                    return item
        return payload

    @classmethod
    def _best_video_url(cls, payload: dict[str, Any]) -> str:
        direct_url = str(payload.get("url") or "")
        if direct_url:
            return direct_url
        requested_formats = payload.get("requested_formats")
        if isinstance(requested_formats, list):
            for item in requested_formats:
                if isinstance(item, dict) and str(item.get("vcodec") or "none") != "none":
                    url = str(item.get("url") or "")
                    if url:
                        return url
        formats = payload.get("formats")
        if isinstance(formats, list):
            for item in reversed(formats):
                if not isinstance(item, dict):
                    continue
                url = str(item.get("url") or "")
                if url and str(item.get("vcodec") or "none") != "none":
                    return url
        return ""

    @staticmethod
    def _duration(value: object) -> float | None:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _valid_url(url: str) -> bool:
        parsed = urlparse(url)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    @staticmethod
    def _looks_like_video_url(url: str) -> bool:
        return bool(re.search(r"\.(mp4|mov|m4v|webm|m3u8)(\?|#|$)", url, re.IGNORECASE))

    @staticmethod
    def _normalize_provider_order(value: str | list[str] | tuple[str, ...]) -> tuple[str, ...]:
        if isinstance(value, str):
            items = re.split(r"[,;\s]+", value)
        else:
            items = [str(item) for item in value]
        normalized = []
        seen = set()
        for item in items:
            provider = item.strip().lower().replace("-", "_")
            if provider and provider not in seen:
                seen.add(provider)
                normalized.append(provider)
        return tuple(normalized)

    @staticmethod
    def _clean_base_url(value: str | None) -> str:
        return str(value or "").strip().rstrip("/")

    @classmethod
    def _find_video_url(cls, payload: Any) -> str:
        candidates = []
        for path, value in cls._walk_json(payload):
            url = cls._coerce_url(value)
            if not url:
                continue
            score = cls._score_video_url_candidate(path, url)
            if score > 0:
                candidates.append((score, len(path), url))
        if not candidates:
            return ""
        candidates.sort(key=lambda item: (item[0], -item[1]), reverse=True)
        return candidates[0][2]

    @classmethod
    def _score_video_url_candidate(cls, path: tuple[str, ...], url: str) -> int:
        joined_path = "_".join(path).lower()
        url_lower = url.lower()
        score = 0
        video_tokens = {
            "video",
            "video_url",
            "play_addr",
            "download_addr",
            "download_url",
            "wmplay",
            "nwmplay",
            "nwm_video_url",
            "no_watermark",
            "origin_video",
            "bit_rate",
        }
        for token in video_tokens:
            if token in joined_path:
                score += 50
        if any(token in joined_path for token in {"play", "download", "url_list", "urls"}):
            score += 15
        if cls._looks_like_video_url(url):
            score += 40
        if any(token in url_lower for token in {"/video/", "mime_type=video", "mime=video"}):
            score += 20
        if re.search(r"\.(mp3|m4a|aac|wav|flac|ogg)(\?|#|$)", url_lower):
            score -= 120
        if any(token in joined_path for token in {"music", "audio", "sound", "song"}):
            score -= 100
        if any(token in joined_path for token in {"cover", "avatar", "image", "thumb", "poster"}):
            score -= 100
        if joined_path.endswith("share_url") or joined_path.endswith("webpage_url"):
            score -= 50
        return score

    @classmethod
    def _find_first_text(cls, payload: Any, keys: set[str]) -> str | None:
        value = cls._find_first_value(payload, keys)
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @classmethod
    def _find_first_url_by_keys(cls, payload: Any, keys: set[str]) -> str:
        normalized_keys = {key.lower() for key in keys}
        for path, value in cls._walk_json(payload):
            key = path[-1].lower() if path else ""
            if key not in normalized_keys:
                continue
            url = cls._coerce_url(value)
            if url:
                return url
        return ""

    @classmethod
    def _find_first_value(cls, payload: Any, keys: set[str]) -> Any:
        normalized_keys = {key.lower() for key in keys}
        for path, value in cls._walk_json(payload):
            if path and path[-1].lower() in normalized_keys and not isinstance(value, (dict, list)):
                return value
        return None

    @classmethod
    def _find_first_url_by_path_hints(cls, payload: Any, *, include: set[str], exclude: set[str]) -> str:
        for path, value in cls._walk_json(payload):
            joined_path = "_".join(path).lower()
            if not any(token in joined_path for token in include):
                continue
            if any(token in joined_path for token in exclude):
                continue
            url = cls._coerce_url(value)
            if url:
                return url
        return ""

    @classmethod
    def _coerce_url(cls, value: Any) -> str:
        if isinstance(value, str):
            text = value.strip()
            if text.startswith("http"):
                return text
            return ""
        if isinstance(value, list):
            for item in value:
                url = cls._coerce_url(item)
                if url:
                    return url
        if isinstance(value, dict):
            for key in ("url", "uri", "src"):
                url = cls._coerce_url(value.get(key))
                if url:
                    return url
            for key in ("url_list", "urls", "list"):
                url = cls._coerce_url(value.get(key))
                if url:
                    return url
        return ""

    @classmethod
    def _walk_json(cls, payload: Any, path: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], Any]]:
        items: list[tuple[tuple[str, ...], Any]] = [(path, payload)]
        if isinstance(payload, dict):
            for key, value in payload.items():
                items.extend(cls._walk_json(value, (*path, str(key))))
        elif isinstance(payload, list):
            for index, value in enumerate(payload):
                items.extend(cls._walk_json(value, (*path, str(index))))
        return items

    @staticmethod
    def _safe_url(url: str) -> str:
        parsed = urlparse(url)
        if not parsed.query:
            return url
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}?<query>"

    @staticmethod
    def _is_actionable_cloud_failure(result: VideoParserResult) -> bool:
        if result.status != "blocked" or result.downloadable:
            return False
        status = result.source_metadata.get("http_status")
        if status in {401, 402, 403, 429}:
            return True
        message = result.message
        return any(keyword in message for keyword in ("额度", "套餐", "权限", "限流", "HTTP 401", "HTTP 402", "HTTP 403", "HTTP 429"))

    def _cloud_http_error_message(self, provider: str, status_code: int) -> str:
        label = self._cloud_provider_label(provider)
        if status_code in {401, 403}:
            return f"{label}账号权限不可用（HTTP {status_code}），请检查 API Key 或服务权限；也可以点击“接收客户端下载”从官方客户端保存视频。"
        if status_code == 402:
            return f"{label}额度不足或套餐不可用（HTTP 402），请充值或开通解析服务；也可以点击“接收客户端下载”从官方客户端保存视频。"
        if status_code == 429:
            return f"{label}请求过于频繁被限流（HTTP 429），请稍后重试；也可以点击“接收客户端下载”。"
        if status_code:
            return f"{label}解析失败（HTTP {status_code}），请检查解析服务状态；也可以点击“接收客户端下载”。"
        return f"{label}解析失败，请检查解析服务状态；也可以点击“接收客户端下载”。"

    @staticmethod
    def _cloud_provider_label(provider: str) -> str:
        labels = {
            "aivo_proxy": "Aivo 内部解析服务",
            "tikhub": "TikHub 第三方解析服务",
            "istero": "起零数据第三方解析服务",
            "evil0ctal": "自建 Douyin/TikTok 解析服务",
            "cloud_parser": "第三方解析服务",
        }
        return labels.get(provider, provider)

    def _resolve_douyin_downloader_root(self) -> Path:
        candidates = [
            self.douyin_downloader_root,
            Path.cwd() / "third_party" / "douyin-downloader",
            Path.cwd().parent / "third_party" / "douyin-downloader",
        ]
        for candidate in candidates:
            resolved = candidate.resolve()
            if (resolved / "run.py").exists():
                return resolved
        return self.douyin_downloader_root.resolve()

    def _resolve_python_command(self) -> list[str] | None:
        configured = self._python_command_from_value(self.python_executable)
        if configured:
            return configured

        if self._looks_like_real_python(sys.executable):
            return [sys.executable]

        for name in ("python", "python3"):
            resolved = shutil.which(name)
            if self._looks_like_real_python(resolved):
                return [str(resolved)]

        py_launcher = shutil.which("py")
        if self._looks_like_py_launcher(py_launcher):
            return [str(py_launcher), "-3"]
        return None

    def _python_command_from_value(self, value: str | Path | None) -> list[str] | None:
        raw = str(value or "").strip().strip('"')
        if not raw:
            return None
        path = Path(raw)
        if path.exists() and self._looks_like_real_python(str(path)):
            return [str(path)]
        resolved = shutil.which(raw)
        if self._looks_like_real_python(resolved):
            return [str(resolved)]
        if self._looks_like_py_launcher(resolved):
            return [str(resolved), "-3"]
        if self._looks_like_py_launcher(raw):
            return [raw, "-3"]
        return None

    @staticmethod
    def _looks_like_real_python(value: str | Path | None) -> bool:
        if not value:
            return False
        lowered = str(value).lower()
        if "windowsapps" in lowered:
            return False
        name = Path(str(value)).name.lower()
        return name in {"python", "python.exe", "python3", "python3.exe"} or (
            name.startswith("python") and name.endswith(".exe")
        )

    @staticmethod
    def _looks_like_py_launcher(value: str | Path | None) -> bool:
        if not value:
            return False
        lowered = str(value).lower()
        if "windowsapps" in lowered:
            return False
        return Path(str(value)).name.lower() in {"py", "py.exe"}

    @staticmethod
    def _media_files(root: Path) -> set[Path]:
        suffixes = {".mp4", ".mov", ".m4v", ".webm"}
        if not root.exists():
            return set()
        files: set[Path] = set()
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in suffixes:
                try:
                    if path.stat().st_size > 0:
                        files.add(path.resolve())
                except OSError:
                    continue
        return files

    @staticmethod
    def _pick_video_file(paths: set[Path] | list[Path]) -> Path | None:
        candidates = [path for path in paths if path.suffix.lower() in {".mp4", ".mov", ".m4v", ".webm"}]
        if not candidates:
            return None
        return max(candidates, key=lambda item: (item.stat().st_mtime, item.stat().st_size))

    def _write_douyin_downloader_config(self, config_path: Path, download_dir: Path) -> None:
        cookies = self._load_douyin_cookies()
        cookie_lines = "\n".join(f"  {key}: {json.dumps(value, ensure_ascii=False)}" for key, value in cookies.items())
        config = f"""link: []
path: {json.dumps(str(download_dir), ensure_ascii=False)}
music: false
cover: false
avatar: false
json: true
folderstyle: true
filename_template: "{{date}}_{{title}}_{{id}}"
folder_template: "{{date}}_{{title}}_{{id}}"
author_dir: "nickname"
download_pinned: false
mode:
  - post
number:
  post: 1
  like: 0
  allmix: 0
  mix: 0
  music: 0
  collect: 0
  collectmix: 0
increase:
  post: false
  like: false
  allmix: false
  mix: false
  music: false
thread: 1
retry_times: 2
proxy: ""
database: false
database_path: {json.dumps(str(download_dir / "dy_downloader.db"), ensure_ascii=False)}
progress:
  quiet_logs: true
browser_fallback:
  enabled: false
  headless: true
  max_scrolls: 1
  idle_rounds: 1
  wait_timeout_seconds: 10
transcript:
  enabled: false
comments:
  enabled: false
live:
  max_duration_seconds: 0
cookies:
{cookie_lines}
"""
        config_path.write_text(config, encoding="utf-8")

    def _load_douyin_cookies(self) -> dict[str, str]:
        keys = ["msToken", "ttwid", "odin_tt", "passport_csrf_token", "sid_guard"]
        defaults = {key: "" for key in keys}
        config_path = self._resolve_douyin_downloader_root() / "config.yml"
        if not config_path.exists():
            return defaults
        try:
            import yaml  # type: ignore

            payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except Exception:
            return defaults
        raw_cookies = payload.get("cookies") if isinstance(payload, dict) else {}
        if not isinstance(raw_cookies, dict):
            return defaults
        return {key: str(raw_cookies.get(key) or "") for key in keys}

    @staticmethod
    def _douyin_downloader_blocked_message(detail: str) -> str:
        lowered = detail.lower()
        if any(token in lowered for token in ["anti-bot", "cookie", "cookies", "captcha", "csrf", "empty 200"]):
            return "抖音专用解析器已调用，但平台返回风控或需要有效 Cookie。请在抖音客户端官方下载视频后上传，或在解析器 config.yml 中配置本人账号 Cookie 后重试。"
        return "抖音专用解析器未拿到可下载视频文件。可能是链接失效、平台限制、需要登录验证，或该内容不允许公开下载；请手动下载视频后上传。"

    @staticmethod
    def _safe_command(command: list[str]) -> list[str]:
        return [item if not item.startswith("http") else "<source_url>" for item in command]

    @staticmethod
    def _should_retry_with_browser_cookies(detail: str) -> bool:
        lowered = detail.lower()
        return any(keyword in lowered for keyword in ["login", "cookie", "captcha", "forbidden", "private"])

    @staticmethod
    def _browser_label(cookie_source: str) -> str:
        labels = {"edge": "Edge", "chrome": "Chrome", "chromium": "Chromium"}
        return labels.get(cookie_source, cookie_source)

    @staticmethod
    def _blocked_message(detail: str) -> str:
        if any(keyword in detail.lower() for keyword in ["login", "cookie", "captcha", "forbidden", "private"]):
            return "平台限制：该链接可能需要登录、验证码或权限访问，请手动下载视频后上传。"
        return "本地视频解析失败：未拿到可下载视频文件，请手动下载视频后上传。"

    @staticmethod
    def _result(**kwargs: Any) -> VideoParserResult:
        payload = {"engine": "yt_dlp", **kwargs}
        return VideoParserResult(**payload)
