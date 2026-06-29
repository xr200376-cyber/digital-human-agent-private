from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.utils.files import ensure_dir


DOUYIN_UPLOAD_URL = "https://creator.douyin.com/creator-micro/content/upload"
DOUYIN_LOGIN_URL = "https://creator.douyin.com/"
DOUYIN_LOGIN_WAIT_TIMEOUT_MS = 300000
DOUYIN_UPLOAD_STUCK_TIMEOUT_SECONDS = 180
DOUYIN_PUBLISH_FIELDS_WAIT_TIMEOUT_MS = 60000


@dataclass(frozen=True)
class PlatformPublishBrowserConfig:
    platform: str
    label: str
    login_url: str
    upload_url: str
    upload_fallback_url: str
    file_input_selectors: tuple[str, ...]
    upload_button_selectors: tuple[str, ...]
    cover_file_input_selectors: tuple[str, ...]
    cover_button_selectors: tuple[str, ...]
    publish_field_selectors: tuple[str, ...]
    title_selectors: tuple[str, ...]
    description_selectors: tuple[str, ...]
    fallback_text_selectors: tuple[str, ...]
    publish_button_selectors: tuple[str, ...]


COMMON_FILE_INPUT_SELECTORS = (
    "input[type='file']",
    "input[accept*='video']",
    "input[accept*='mp4']",
)
COMMON_UPLOAD_BUTTON_SELECTORS = (
    "button:has-text('上传视频')",
    "[role='button']:has-text('上传视频')",
    "text=上传视频",
    "button:has-text('点击上传')",
    "[role='button']:has-text('点击上传')",
    "text=点击上传",
)
COMMON_COVER_FILE_INPUT_SELECTORS = (
    "input[type='file'][accept*='image']",
    "input[type='file'][accept*='png']",
    "input[type='file'][accept*='jpg']",
    "input[type='file'][accept*='jpeg']",
    "input[type='file'][accept*='webp']",
)
COMMON_COVER_BUTTON_SELECTORS = (
    "button:has-text('选择封面')",
    "[role='button']:has-text('选择封面')",
    "text=选择封面",
    "button:has-text('设置封面')",
    "[role='button']:has-text('设置封面')",
    "text=设置封面",
    "button:has-text('编辑封面')",
    "[role='button']:has-text('编辑封面')",
    "text=编辑封面",
    "button:has-text('上传封面')",
    "[role='button']:has-text('上传封面')",
    "text=上传封面",
    "button:has-text('更换封面')",
    "[role='button']:has-text('更换封面')",
    "text=更换封面",
    "button:has-text('自定义封面')",
    "[role='button']:has-text('自定义封面')",
    "text=自定义封面",
)
COMMON_TITLE_SELECTORS = (
    "input[placeholder*='标题']",
    "textarea[placeholder*='标题']",
    "[contenteditable='true'][aria-label*='标题']",
    "[contenteditable='true'][data-placeholder*='标题']",
)
COMMON_DESCRIPTION_SELECTORS = (
    "textarea[placeholder*='描述']",
    "textarea[placeholder*='作品描述']",
    "textarea[placeholder*='简介']",
    "textarea[placeholder*='正文']",
    "textarea[placeholder*='内容']",
    "[contenteditable='true'][aria-label*='描述']",
    "[contenteditable='true'][aria-label*='正文']",
    "[contenteditable='true'][data-placeholder*='描述']",
    "[contenteditable='true'][data-placeholder*='简介']",
    "[contenteditable='true'][data-placeholder*='正文']",
)
COMMON_FALLBACK_TEXT_SELECTORS = (
    "div[contenteditable='true']",
    "[contenteditable='true']",
)
COMMON_FIELD_WAIT_SELECTORS = COMMON_TITLE_SELECTORS + COMMON_DESCRIPTION_SELECTORS + COMMON_FALLBACK_TEXT_SELECTORS

PLATFORM_CONFIGS: dict[str, PlatformPublishBrowserConfig] = {
    "douyin": PlatformPublishBrowserConfig(
        platform="douyin",
        label="抖音",
        login_url=DOUYIN_LOGIN_URL,
        upload_url=DOUYIN_UPLOAD_URL,
        upload_fallback_url=DOUYIN_LOGIN_URL,
        file_input_selectors=COMMON_FILE_INPUT_SELECTORS,
        upload_button_selectors=COMMON_UPLOAD_BUTTON_SELECTORS,
        cover_file_input_selectors=COMMON_COVER_FILE_INPUT_SELECTORS,
        cover_button_selectors=COMMON_COVER_BUTTON_SELECTORS,
        publish_field_selectors=COMMON_FIELD_WAIT_SELECTORS,
        title_selectors=COMMON_TITLE_SELECTORS,
        description_selectors=COMMON_DESCRIPTION_SELECTORS,
        fallback_text_selectors=COMMON_FALLBACK_TEXT_SELECTORS,
        publish_button_selectors=(
            "button:has-text('发布')",
            "button:has-text('立即发布')",
            "button:has-text('定时发布')",
            "[role='button']:has-text('发布')",
        ),
    ),
    "xiaohongshu": PlatformPublishBrowserConfig(
        platform="xiaohongshu",
        label="小红书",
        login_url="https://creator.xiaohongshu.com/",
        upload_url="https://creator.xiaohongshu.com/publish/publish",
        upload_fallback_url="https://creator.xiaohongshu.com/",
        file_input_selectors=COMMON_FILE_INPUT_SELECTORS,
        upload_button_selectors=COMMON_UPLOAD_BUTTON_SELECTORS,
        cover_file_input_selectors=COMMON_COVER_FILE_INPUT_SELECTORS,
        cover_button_selectors=COMMON_COVER_BUTTON_SELECTORS,
        publish_field_selectors=COMMON_FIELD_WAIT_SELECTORS,
        title_selectors=COMMON_TITLE_SELECTORS,
        description_selectors=COMMON_DESCRIPTION_SELECTORS,
        fallback_text_selectors=COMMON_FALLBACK_TEXT_SELECTORS,
        publish_button_selectors=(
            "button:has-text('发布')",
            "button:has-text('立即发布')",
            "[role='button']:has-text('发布')",
        ),
    ),
    "shipinhao": PlatformPublishBrowserConfig(
        platform="shipinhao",
        label="视频号",
        login_url="https://channels.weixin.qq.com/platform",
        upload_url="https://channels.weixin.qq.com/platform/post/create",
        upload_fallback_url="https://channels.weixin.qq.com/platform",
        file_input_selectors=COMMON_FILE_INPUT_SELECTORS,
        upload_button_selectors=COMMON_UPLOAD_BUTTON_SELECTORS,
        cover_file_input_selectors=COMMON_COVER_FILE_INPUT_SELECTORS,
        cover_button_selectors=COMMON_COVER_BUTTON_SELECTORS,
        publish_field_selectors=COMMON_FIELD_WAIT_SELECTORS,
        title_selectors=COMMON_TITLE_SELECTORS,
        description_selectors=COMMON_DESCRIPTION_SELECTORS
        + (
            "textarea[placeholder*='动态']",
            "[contenteditable='true'][aria-label*='动态']",
            "[contenteditable='true'][data-placeholder*='动态']",
        ),
        fallback_text_selectors=COMMON_FALLBACK_TEXT_SELECTORS,
        publish_button_selectors=(
            "button:has-text('发表')",
            "button:has-text('发布')",
            "button:has-text('立即发表')",
            "button:has-text('立即发布')",
            "[role='button']:has-text('发表')",
            "[role='button']:has-text('发布')",
        ),
    ),
}
SUPPORTED_PLATFORM_LABELS = {
    "douyin": "抖音",
    "xiaohongshu": "小红书",
    "kuaishou": "快手",
    "shipinhao": "视频号",
    "tiktok": "TikTok",
}


class PublishBrowserAutomationError(RuntimeError):
    pass


class PublishBrowserAutomation:
    def __init__(self) -> None:
        self.settings: Any | None = None
        self.sessions: dict[str, dict[str, Any]] = {}

    def configure(self, settings: Any) -> "PublishBrowserAutomation":
        self.settings = settings
        return self

    def open_login(self, platform: str) -> dict[str, object]:
        config = self._platform_config(platform)
        try:
            page, session = self._open_or_create_session(f"account_{config.platform}", config.platform)
            page.goto(config.login_url, wait_until="domcontentloaded", timeout=30000)
            session.update({"status": "needs_login", "page_url": page.url})
            return self._payload(
                queue_id="",
                platform=config.platform,
                status="needs_login",
                message=f"已打开{config.label}账号页面，请在浏览器中完成登录。",
                action_required="login",
                browser_opened=True,
                page_url=page.url,
            )
        except PublishBrowserAutomationError:
            raise
        except Exception as exc:  # pragma: no cover - depends on local browser runtime
            raise PublishBrowserAutomationError(f"打开{config.label}登录页失败：{exc}") from exc

    def start(self, item: Any, final_video_path: Path) -> dict[str, object]:
        config = self._platform_config(item.platform)
        if not final_video_path.exists():
            raise PublishBrowserAutomationError("未找到可发布的成片 MP4，请先完成视频生成。")

        existing = self.sessions.get(item.queue_id)
        if existing:
            if self._session_is_closed(existing):
                self._discard_session(item.queue_id)
                existing = None
            else:
                self._fail_stale_upload_session(existing)
        if existing and existing.get("status") in {"uploading", "filling", "awaiting_final_confirmation"}:
            return self._resume_existing_session_payload(item, existing)

        try:
            page, session = self._open_or_create_session(item.queue_id, config.platform)
            self._set_session_status(session, "uploading", final_video_path=str(final_video_path))
            self._goto_upload_page(page, config)
            if not self._upload_video_file(page, config, final_video_path):
                self._set_session_status(session, "needs_login", page_url=page.url)
                return self._payload(
                    queue_id=item.queue_id,
                    platform=config.platform,
                    status="needs_login",
                    message=(
                        f"未检测到{config.label}上传入口。请先在打开的浏览器中登录或处理验证码，"
                        "登录完成后再点击一次手动发布。登录态会保存在本机。"
                    ),
                    action_required="login",
                    browser_opened=True,
                    page_url=page.url,
                )

            self._set_session_status(session, "filling", page_url=page.url)
            self._wait_for_publish_fields(page, config)
            self._fill_publish_fields(page, item, config)
            self._upload_cover_image(page, item, config)
            self._set_session_status(session, "awaiting_final_confirmation", page_url=page.url)
            return self._payload(
                queue_id=item.queue_id,
                platform=config.platform,
                status="awaiting_final_confirmation",
                message=f"已上传视频并填写{config.label}发布信息，请在浏览器中检查内容后确认发布。",
                action_required="confirm_final",
                browser_opened=True,
                upload_url=config.upload_url,
                page_url=page.url,
                final_video_path=str(final_video_path),
            )
        except PublishBrowserAutomationError:
            raise
        except Exception as exc:  # pragma: no cover - depends on platform page/runtime
            raise PublishBrowserAutomationError(f"{config.label}自动发布失败：{exc}") from exc

    def status(self, item: Any) -> dict[str, object]:
        session = self.sessions.get(item.queue_id)
        if session:
            self._fail_stale_upload_session(session)
            if session.get("status") != "failed" and self._session_is_closed(session):
                self._discard_session(item.queue_id)
                platform = self._normalize_platform(item.platform)
                return self._payload(
                    queue_id=item.queue_id,
                    platform=platform,
                    status="not_started",
                    message="发布浏览器已经关闭。可以重新点击手动发布打开。",
                    action_required="start",
                    browser_opened=False,
                )
            status = str(session.get("status") or "not_started")
            platform = self._normalize_platform(str(session.get("platform") or item.platform))
            return self._payload(
                queue_id=item.queue_id,
                platform=platform,
                status=status,
                message=str(session.get("error_message") or self._status_message(status, platform)),
                action_required=self._action_for_status(status),
                browser_opened=bool(session.get("browser_opened", True)),
                page_url=session.get("page_url"),
                final_video_path=session.get("final_video_path"),
            )
        stored = item.metadata.get("browser_publish") if getattr(item, "metadata", None) else None
        if isinstance(stored, dict) and stored:
            return stored
        platform = self._normalize_platform(item.platform)
        return self._payload(
            queue_id=item.queue_id,
            platform=platform,
            status="not_started",
            message="尚未启动自动发布。",
            action_required="start",
        )

    def confirm_final(self, item: Any) -> dict[str, object]:
        config = self._platform_config(item.platform)
        session = self.sessions.get(item.queue_id)
        if not session:
            raise PublishBrowserAutomationError("浏览器发布会话已失效，请重新启动自动发布。")
        page = session.get("page")
        if page is None:
            raise PublishBrowserAutomationError("浏览器页面不可用，请重新启动自动发布。")
        try:
            clicked = self._click_publish_button(page, config)
            if not clicked:
                raise PublishBrowserAutomationError(f"未找到{config.label}发布按钮，请在浏览器中手动确认。")
            session.update({"status": "published", "page_url": page.url})
            return self._payload(
                queue_id=item.queue_id,
                platform=config.platform,
                status="published",
                message=f"已点击{config.label}最终发布按钮，请在平台页面确认发布结果。",
                action_required="none",
                browser_opened=True,
                page_url=page.url,
                external_url=page.url,
            )
        except PublishBrowserAutomationError:
            raise
        except Exception as exc:  # pragma: no cover - depends on platform page/runtime
            raise PublishBrowserAutomationError(f"确认发布失败：{exc}") from exc

    def _open_or_create_session(self, queue_id: str, platform: str) -> tuple[Any, dict[str, Any]]:
        session = self.sessions.get(queue_id)
        if session and session.get("page") is not None and not self._session_is_closed(session):
            self._bring_page_to_front(session.get("page"))
            return session["page"], session
        if session:
            self._discard_session(queue_id)

        sync_playwright = self._sync_playwright()
        playwright = sync_playwright().start()
        profile_dir = ensure_dir(self._profile_root() / platform)
        last_error: Exception | None = None
        for channel in ("msedge", "chrome", None):
            try:
                launch_kwargs: dict[str, Any] = {
                    "user_data_dir": str(profile_dir),
                    "headless": False,
                    "accept_downloads": True,
                    "args": ["--disable-blink-features=AutomationControlled"],
                }
                if channel:
                    launch_kwargs["channel"] = channel
                context = playwright.chromium.launch_persistent_context(**launch_kwargs)
                page = context.pages[0] if context.pages else context.new_page()
                session = {
                    "platform": platform,
                    "playwright": playwright,
                    "context": context,
                    "page": page,
                    "status": "not_started",
                    "status_updated_at": datetime.now(timezone.utc),
                    "browser_opened": True,
                }
                self.sessions[queue_id] = session
                return page, session
            except Exception as exc:  # pragma: no cover - depends on installed browsers
                last_error = exc
        try:
            playwright.stop()
        except Exception:
            pass
        raise PublishBrowserAutomationError(f"无法打开本机浏览器：{last_error}")

    def _resume_existing_session_payload(self, item: Any, session: dict[str, Any]) -> dict[str, object]:
        page = session.get("page")
        self._bring_page_to_front(page)
        status = str(session.get("status") or "not_started")
        platform = self._normalize_platform(str(session.get("platform") or item.platform))
        return self._payload(
            queue_id=item.queue_id,
            platform=platform,
            status=status,
            message=(
                "当前发布浏览器已经打开，已尝试切回该窗口。"
                "如果你已经关闭窗口，请刷新状态后重新点击手动发布。"
            ),
            action_required=self._action_for_status(status),
            browser_opened=True,
            page_url=session.get("page_url") or getattr(page, "url", None),
            final_video_path=session.get("final_video_path"),
        )

    def _discard_session(self, queue_id: str) -> None:
        session = self.sessions.pop(queue_id, None)
        if session:
            self._close_session_resources(session)

    @staticmethod
    def _session_is_closed(session: dict[str, Any]) -> bool:
        page = session.get("page")
        if page is None:
            return True
        try:
            is_closed = getattr(page, "is_closed", None)
            if callable(is_closed) and is_closed():
                return True
        except Exception:
            return True
        context = session.get("context")
        if context is not None:
            try:
                pages = getattr(context, "pages", None)
                if isinstance(pages, list) and not pages:
                    return True
            except Exception:
                return True
        return False

    @staticmethod
    def _bring_page_to_front(page: Any) -> None:
        if page is None:
            return
        try:
            page.bring_to_front()
        except Exception:
            pass

    def _sync_playwright(self) -> Any:
        try:
            from playwright.sync_api import sync_playwright

            return sync_playwright
        except Exception as exc:  # pragma: no cover - only when dependency missing
            raise PublishBrowserAutomationError(
                "Playwright 未安装，无法启动浏览器自动化。请先安装 playwright 并执行 playwright install chromium。"
            ) from exc

    def _profile_root(self) -> Path:
        if self.settings is None:
            raise PublishBrowserAutomationError("发布自动化尚未初始化。")
        return ensure_dir(Path(self.settings.storage_dir) / "browser_profiles")

    @staticmethod
    def _goto_upload_page(page: Any, config: PlatformPublishBrowserConfig) -> None:
        try:
            page.goto(config.upload_url, wait_until="domcontentloaded", timeout=30000)
        except Exception:
            if config.upload_fallback_url == config.upload_url:
                raise
            page.goto(config.upload_fallback_url, wait_until="domcontentloaded", timeout=30000)

    @staticmethod
    def _upload_video_file(page: Any, config: PlatformPublishBrowserConfig, final_video_path: Path) -> bool:
        if PublishBrowserAutomation._set_file_input_by_selector(page, config.file_input_selectors, final_video_path):
            return True
        file_input = PublishBrowserAutomation._file_input(page, config.file_input_selectors)
        if file_input is not None:
            return PublishBrowserAutomation._set_file_input(file_input, final_video_path)
        return PublishBrowserAutomation._choose_file_via_button(page, config.upload_button_selectors, final_video_path)

    @staticmethod
    def _upload_cover_image(page: Any, item: Any, config: PlatformPublishBrowserConfig) -> bool:
        cover_path = PublishBrowserAutomation._cover_image_path(item)
        if cover_path is None:
            return False
        if PublishBrowserAutomation._set_file_input_by_selector(page, config.cover_file_input_selectors, cover_path):
            return True
        file_input = PublishBrowserAutomation._file_input(page, config.cover_file_input_selectors)
        if file_input is not None and PublishBrowserAutomation._set_file_input(file_input, cover_path):
            return True
        return PublishBrowserAutomation._choose_file_via_button(page, config.cover_button_selectors, cover_path)

    @staticmethod
    def _cover_image_path(item: Any) -> Path | None:
        candidates: list[object] = []
        artifacts = getattr(item, "artifacts", None)
        if isinstance(artifacts, dict):
            candidates.append(artifacts.get("cover_image"))
        metadata = getattr(item, "metadata", None)
        if isinstance(metadata, dict):
            candidates.append(metadata.get("cover_image_path"))
        for raw_path in candidates:
            cover_path = PublishBrowserAutomation._existing_file_path(raw_path)
            if cover_path is not None:
                return cover_path
        return None

    @staticmethod
    def _existing_file_path(raw_path: object) -> Path | None:
        if not raw_path:
            return None
        cover_path = Path(str(raw_path))
        if not cover_path.is_absolute():
            cover_path = Path.cwd() / cover_path
        return cover_path if cover_path.exists() and cover_path.is_file() else None

    @staticmethod
    def _file_input(page: Any, selectors: tuple[str, ...]) -> Any | None:
        for scope in PublishBrowserAutomation._page_scopes(page):
            for selector in selectors:
                try:
                    locator = scope.locator(selector)
                    if locator.count() > 0:
                        target = locator.first
                        if hasattr(target, "set_input_files"):
                            return target
                except Exception:
                    continue
        return None

    @staticmethod
    def _set_file_input_by_selector(page: Any, selectors: tuple[str, ...], path: Path) -> bool:
        for scope in PublishBrowserAutomation._page_scopes(page):
            setter = getattr(scope, "set_input_files", None)
            if setter is None:
                continue
            for selector in selectors:
                try:
                    setter(selector, str(path), timeout=10000)
                    return True
                except TypeError:
                    try:
                        setter(selector, str(path))
                        return True
                    except Exception:
                        continue
                except Exception:
                    continue
        return False

    @staticmethod
    def _set_file_input(file_input: Any, path: Path) -> bool:
        try:
            file_input.set_input_files(str(path), timeout=10000)
            return True
        except TypeError:
            try:
                file_input.set_input_files(str(path))
                return True
            except Exception:
                return False
        except Exception:
            return False

    @staticmethod
    def _choose_file_via_button(page: Any, selectors: tuple[str, ...], path: Path) -> bool:
        expect_file_chooser = getattr(page, "expect_file_chooser", None)
        if expect_file_chooser is None:
            return False
        for scope in PublishBrowserAutomation._page_scopes(page):
            for selector in selectors:
                try:
                    locator = scope.locator(selector)
                    if locator.count() <= 0:
                        continue
                    with page.expect_file_chooser(timeout=5000) as file_chooser_info:
                        locator.first.click(timeout=3000)
                    file_chooser = file_chooser_info.value
                    file_chooser.set_files(str(path))
                    return True
                except Exception:
                    continue
        return False

    @staticmethod
    def _wait_for_file_input_after_login(
        page: Any,
        session: dict[str, Any],
        config: PlatformPublishBrowserConfig,
    ) -> Any | None:
        try:
            file_input = page.wait_for_selector(
                ", ".join(config.file_input_selectors),
                state="attached",
                timeout=DOUYIN_LOGIN_WAIT_TIMEOUT_MS,
            )
            session.update(
                {
                    "status": "uploading",
                    "status_updated_at": datetime.now(timezone.utc),
                    "page_url": getattr(page, "url", None),
                }
            )
            return file_input or PublishBrowserAutomation._file_input(page, config.file_input_selectors)
        except Exception:
            return PublishBrowserAutomation._file_input(page, config.file_input_selectors)

    @staticmethod
    def _set_session_status(session: dict[str, Any], status: str, **extra: object) -> None:
        session.update(
            {
                "status": status,
                "status_updated_at": datetime.now(timezone.utc),
                "browser_opened": True,
                **extra,
            }
        )
        if status != "failed":
            session.pop("error_message", None)

    def _fail_stale_upload_session(self, session: dict[str, Any]) -> bool:
        if session.get("status") != "uploading":
            return False
        updated_at = session.get("status_updated_at")
        if not isinstance(updated_at, datetime):
            return False
        if datetime.now(timezone.utc) - updated_at < timedelta(seconds=DOUYIN_UPLOAD_STUCK_TIMEOUT_SECONDS):
            return False
        platform = self._normalize_platform(str(session.get("platform") or "douyin"))
        label = SUPPORTED_PLATFORM_LABELS.get(platform, platform)
        self._close_session_resources(session)
        session.update(
            {
                "status": "failed",
                "status_updated_at": datetime.now(timezone.utc),
                "browser_opened": False,
                "error_message": (
                    f"{label}上传超过 3 分钟没有进入填写步骤，已停止本次发布会话。"
                    "请确认浏览器登录和网络后重新点击自动发布。"
                ),
            }
        )
        return True

    @staticmethod
    def _close_session_resources(session: dict[str, Any]) -> None:
        for key, method in (("context", "close"), ("playwright", "stop")):
            resource = session.get(key)
            if resource is None:
                continue
            try:
                getattr(resource, method)()
            except Exception:
                pass

    @staticmethod
    def _fill_publish_fields(page: Any, item: Any, config: PlatformPublishBrowserConfig) -> None:
        package = item.platform_package
        title = str(package.title or "")[:30]
        tags = " ".join(f"#{tag}" for tag in package.hashtags[:6])
        description = "\n".join(part for part in [package.description, tags] if str(part or "").strip()).strip()
        combined_description = "\n".join(
            part for part in [title, package.description, tags] if str(part or "").strip()
        ).strip()
        title_filled = PublishBrowserAutomation._try_fill_any(page, list(config.title_selectors), title)
        description_filled = PublishBrowserAutomation._try_fill_any(page, list(config.description_selectors), description)
        if not title_filled and not description_filled:
            PublishBrowserAutomation._try_fill_any(page, list(config.fallback_text_selectors), combined_description)
        elif not description_filled:
            PublishBrowserAutomation._try_fill_any(page, list(config.fallback_text_selectors), description)

    @staticmethod
    def _wait_for_publish_fields(page: Any, config: PlatformPublishBrowserConfig) -> None:
        selector = ", ".join(config.publish_field_selectors)
        for scope in PublishBrowserAutomation._page_scopes(page):
            try:
                scope.wait_for_selector(selector, state="attached", timeout=DOUYIN_PUBLISH_FIELDS_WAIT_TIMEOUT_MS)
                return
            except Exception:
                continue

    @staticmethod
    def _try_fill_any(page: Any, selectors: list[str], text: str) -> bool:
        for selector in selectors:
            if PublishBrowserAutomation._try_fill(page, selector, text):
                return True
        return False

    @staticmethod
    def _try_fill(page: Any, selector: str, text: str) -> bool:
        if not text:
            return False
        for scope in PublishBrowserAutomation._page_scopes(page):
            try:
                locator = scope.locator(selector)
                if locator.count() <= 0:
                    continue
                target = locator.first
                try:
                    target.fill(text, timeout=2500)
                except Exception:
                    target.click(timeout=2500)
                    target.press("Control+A", timeout=2500)
                    target.type(text, timeout=5000)
                return True
            except Exception:
                if PublishBrowserAutomation._try_dom_fill(scope, selector, text):
                    return True
                continue
        return False

    @staticmethod
    def _try_dom_fill(scope: Any, selector: str, text: str) -> bool:
        evaluate = getattr(scope, "evaluate", None)
        if evaluate is None:
            return False
        try:
            return bool(
                evaluate(
                    """({ selector, text }) => {
                        const el = document.querySelector(selector);
                        if (!el) return false;
                        if ('value' in el) {
                            el.value = text;
                        } else {
                            el.textContent = text;
                        }
                        el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: text }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        return true;
                    }""",
                    {"selector": selector, "text": text},
                )
            )
        except Exception:
            return False

    @staticmethod
    def _click_publish_button(page: Any, config: PlatformPublishBrowserConfig) -> bool:
        for scope in PublishBrowserAutomation._page_scopes(page):
            for selector in config.publish_button_selectors:
                try:
                    locator = scope.locator(selector)
                    if locator.count() <= 0:
                        continue
                    locator.first.click(timeout=3000)
                    return True
                except Exception:
                    continue
        return False

    @staticmethod
    def _page_scopes(page: Any) -> list[Any]:
        scopes: list[Any] = []
        seen: set[int] = set()

        def add_scope(scope: Any) -> None:
            if scope is None:
                return
            marker = id(scope)
            if marker in seen:
                return
            seen.add(marker)
            scopes.append(scope)

        add_scope(page)
        try:
            raw_frames = getattr(page, "frames", [])
            frames = raw_frames() if callable(raw_frames) else raw_frames
        except Exception:
            frames = []
        for frame in frames or []:
            add_scope(frame)
        return scopes

    @staticmethod
    def _normalize_platform(platform: str) -> str:
        value = (platform or "douyin").strip().lower()
        return {"wechat_channels": "shipinhao", "video_account": "shipinhao"}.get(value, value)

    @classmethod
    def _platform_config(cls, platform: str) -> PlatformPublishBrowserConfig:
        value = cls._normalize_platform(platform)
        config = PLATFORM_CONFIGS.get(value)
        if config is None:
            label = SUPPORTED_PLATFORM_LABELS.get(value, value)
            raise PublishBrowserAutomationError(f"{label}浏览器自动发布待接入，当前支持抖音、小红书、视频号。")
        return config

    @staticmethod
    def _payload(
        *,
        queue_id: str,
        platform: str,
        status: str,
        message: str,
        action_required: str,
        browser_opened: bool = False,
        **extra: object,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "queue_id": queue_id,
            "platform": platform,
            "status": status,
            "status_label": PublishBrowserAutomation._status_label(status),
            "message": message,
            "action_required": action_required,
            "browser_opened": browser_opened,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        payload.update({key: value for key, value in extra.items() if value is not None})
        return payload

    @staticmethod
    def _status_label(status: str) -> str:
        return {
            "not_started": "未开始",
            "needs_login": "需登录",
            "uploading": "上传中",
            "filling": "填写中",
            "awaiting_final_confirmation": "待最终确认",
            "published": "已发布",
            "failed": "失败",
        }.get(status, status)

    @staticmethod
    def _status_message(status: str, platform: str = "douyin") -> str:
        label = SUPPORTED_PLATFORM_LABELS.get(platform, platform)
        return {
            "not_started": "尚未启动自动发布。",
            "needs_login": f"请在打开的浏览器中完成{label}登录。",
            "uploading": "正在上传视频，请勿重复点击。",
            "filling": "正在填写标题、简介和话题。",
            "awaiting_final_confirmation": "请检查浏览器中的发布内容，然后确认发布。",
            "published": "已执行发布确认，请查看平台结果。",
            "failed": "自动发布失败，请查看错误提示。",
        }.get(status, "自动发布状态已更新。")

    @staticmethod
    def _action_for_status(status: str) -> str:
        return {
            "not_started": "start",
            "needs_login": "login",
            "uploading": "wait",
            "filling": "wait",
            "awaiting_final_confirmation": "confirm_final",
            "published": "none",
            "failed": "start",
        }.get(status, "start")
