from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.adapters.video_parser import LocalVideoParserAdapter, VideoParserResult
from app.reference_collector import ReferenceContentCollector
from app.reference_videos import ReferenceVideoStore
from app.schemas import (
    AnalyzeReferenceVideoRequest,
    CollectReferenceLinkRequest,
    CreateReferenceVideoRequest,
    ReferenceContentCapture,
    ReferenceLinkTranscriptionResult,
    TranscribeReferenceLinkRequest,
)
from app.settings import Settings
from app.utils.files import ensure_dir, write_json


MAX_REFERENCE_VIDEO_DOWNLOAD_BYTES = 300 * 1024 * 1024


class ReferenceLinkTranscriptionService:
    """Turn a public video link into reference-video ASR when the video file is actually reachable."""

    def __init__(
        self,
        settings: Settings,
        collector: ReferenceContentCollector | None = None,
        reference_store: ReferenceVideoStore | None = None,
    ):
        self.settings = settings
        self.collector = collector or ReferenceContentCollector(settings)
        self.reference_store = reference_store or ReferenceVideoStore(settings)

    def transcribe(self, project_id: str, request: TranscribeReferenceLinkRequest) -> ReferenceLinkTranscriptionResult:
        try:
            capture = self.collector.collect(
                project_id,
                CollectReferenceLinkRequest(
                    url=request.url,
                    metadata={
                        **request.metadata,
                        "fallback_text": request.metadata.get("fallback_text", ""),
                        "source": "reference_link_transcription",
                    },
                ),
            )
        except ValueError:
            return ReferenceLinkTranscriptionResult(
                status="blocked",
                message="没有检测到 http 或 https 视频链接，当前内容像平台口令或普通文字，不能直接读取视频声音。",
                platform="generic_web",
                source_url=str(request.url or ""),
                recommended_next_action="请复制分享面板里的完整网页链接，或先把视频下载到本地后上传。",
            )
        if not capture.video_url or not capture.downloadable:
            parser_result = self._parse_with_local_engine(capture)
            if parser_result.downloadable and parser_result.video_url:
                capture = self._capture_from_parser_result(capture, parser_result)
            else:
                message = self._unreachable_video_message(capture, parser_result)
                return self._blocked(
                    capture,
                    message,
                    "请手动下载参考视频后上传，系统会用 FunASR / Paraformer 转写成文案。",
                )

        try:
            video_path = self._materialize_video(capture, project_id)
            reference = self.reference_store.create(
                project_id,
                CreateReferenceVideoRequest(
                    title=capture.title or "平台参考视频",
                    source_path=str(video_path),
                    metadata={
                        "source": "platform_reference_link",
                        "source_url": capture.source_url,
                        "final_url": capture.final_url,
                        "platform": capture.platform,
                        "collection_id": capture.collection_id,
                        "video_url": capture.video_url,
                    },
                ),
            )
            analyzed = self.reference_store.analyze(
                reference.reference_id,
                AnalyzeReferenceVideoRequest(asr_engine=request.asr_engine or "funasr", force=request.force),
            )
            analysis = self.reference_store.analysis_payload(analyzed.reference_id)
            transcript_text = self._transcript_text(analysis)
            reference_script_text = self._reference_script_text(analysis)
            transcription_blocker = self._real_transcription_blocker(analysis, transcript_text)
            if transcription_blocker:
                return ReferenceLinkTranscriptionResult(
                    status="blocked",
                    message=transcription_blocker,
                    platform=capture.platform,
                    source_url=capture.source_url,
                    final_url=capture.final_url,
                    collection_id=capture.collection_id,
                    reference_id=analyzed.reference_id,
                    stored_video_path=str(video_path),
                    transcript_text="",
                    reference_script_text="",
                    recommended_next_action="请关闭演示模式，确认 ffmpeg 和 FunASR / Paraformer 可用后重试；如果平台限制解析，请先手动下载视频再上传。",
                    collection=capture,
                    analysis=analysis,
                )
            return ReferenceLinkTranscriptionResult(
                status="transcribed",
                message="视频声音已通过 FunASR / Paraformer 转写成文案。",
                platform=capture.platform,
                source_url=capture.source_url,
                final_url=capture.final_url,
                collection_id=capture.collection_id,
                reference_id=analyzed.reference_id,
                stored_video_path=str(video_path),
                transcript_text=transcript_text,
                reference_script_text=reference_script_text,
                recommended_next_action="已填入识别内容和脚本文案，可继续 AI 改写或生成数字人视频。",
                collection=capture,
                analysis=analysis,
            )
        except Exception as exc:  # noqa: BLE001 - workbench should show a clear blocker instead of a 500.
            return self._blocked(
                capture,
                f"链接视频转写失败：{type(exc).__name__}: {exc}",
                "请手动下载参考视频后上传，或检查 FunASR / ffmpeg 配置后重试。",
            )

    def transcribe_local_video(
        self,
        project_id: str,
        video_path: Path,
        *,
        platform: str = "local_download",
        source_url: str = "",
        asr_engine: str | None = "funasr",
        force: bool = False,
        metadata: dict[str, object] | None = None,
    ) -> ReferenceLinkTranscriptionResult:
        local_path = Path(video_path)
        capture = ReferenceContentCapture(
            project_id=project_id,
            source_url=source_url or str(local_path),
            final_url=source_url or str(local_path),
            platform=platform or "local_download",
            status="captured",
            title=local_path.stem,
            video_url=str(local_path),
            downloadable=True,
            message="已从本机下载目录接收视频，正在转写声音。",
            recommended_next_action="下载目录视频已接收，可继续生成脚本文案。",
            source_metadata={"source": "download_watch", **(metadata or {})},
        )
        try:
            if not local_path.exists() or not local_path.is_file():
                raise FileNotFoundError(f"downloaded reference video not found: {local_path}")
            reference = self.reference_store.create(
                project_id,
                CreateReferenceVideoRequest(
                    title=local_path.stem or "下载目录参考视频",
                    source_path=str(local_path),
                    metadata={
                        "source": "download_watch",
                        "source_url": source_url or str(local_path),
                        "platform": capture.platform,
                        "video_url": str(local_path),
                        **(metadata or {}),
                    },
                ),
            )
            analyzed = self.reference_store.analyze(
                reference.reference_id,
                AnalyzeReferenceVideoRequest(asr_engine=asr_engine or "funasr", force=force),
            )
            analysis = self.reference_store.analysis_payload(analyzed.reference_id)
            transcript_text = self._transcript_text(analysis)
            reference_script_text = self._reference_script_text(analysis)
            transcription_blocker = self._real_transcription_blocker(analysis, transcript_text)
            if transcription_blocker:
                return ReferenceLinkTranscriptionResult(
                    status="blocked",
                    message=transcription_blocker,
                    platform=capture.platform,
                    source_url=capture.source_url,
                    final_url=capture.final_url,
                    collection_id=capture.collection_id,
                    reference_id=analyzed.reference_id,
                    stored_video_path=str(local_path),
                    transcript_text="",
                    reference_script_text="",
                    recommended_next_action="请确认 ffmpeg 和 FunASR / Paraformer 可用后重试，或换一个已下载完成的视频文件。",
                    collection=capture,
                    analysis=analysis,
                )
            return ReferenceLinkTranscriptionResult(
                status="transcribed",
                message="下载目录视频声音已通过 FunASR / Paraformer 转写成文案。",
                platform=capture.platform,
                source_url=capture.source_url,
                final_url=capture.final_url,
                collection_id=capture.collection_id,
                reference_id=analyzed.reference_id,
                stored_video_path=str(local_path),
                transcript_text=transcript_text,
                reference_script_text=reference_script_text,
                recommended_next_action="已填入识别内容和脚本文案，可继续 AI 改写或生成数字人视频。",
                collection=capture,
                analysis=analysis,
            )
        except Exception as exc:  # noqa: BLE001 - keep customer UI on a readable blocker.
            return self._blocked(
                capture,
                f"下载目录视频转写失败：{type(exc).__name__}: {exc}",
                "请确认视频已经下载完成，或重新在抖音客户端点官方下载。",
            )

    def _download_remote_video(self, capture: ReferenceContentCapture, project_id: str) -> Path:
        url = capture.video_url
        out_dir = ensure_dir(
            self.settings.storage_dir / "projects" / project_id / "reference_collections" / capture.collection_id
        )
        target = out_dir / f"source_video{self._video_extension(url)}"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
            ),
            "Accept": "video/*,*/*;q=0.8",
        }
        downloaded = 0
        with httpx.Client(follow_redirects=True, timeout=60.0, headers=headers) as client:
            with client.stream("GET", url) as response:
                response.raise_for_status()
                content_type = response.headers.get("content-type", "")
                if content_type and not content_type.lower().startswith(("video/", "application/octet-stream")):
                    raise RuntimeError(f"远程地址不是视频文件：{content_type}")
                with target.open("wb") as file:
                    for chunk in response.iter_bytes():
                        if not chunk:
                            continue
                        downloaded += len(chunk)
                        if downloaded > MAX_REFERENCE_VIDEO_DOWNLOAD_BYTES:
                            raise RuntimeError("参考视频超过 300MB，已停止下载")
                        file.write(chunk)
        if not target.exists() or target.stat().st_size == 0:
            raise RuntimeError("远程视频下载为空")
        return target

    def _materialize_video(self, capture: ReferenceContentCapture, project_id: str) -> Path:
        local_path = self._parser_stored_video_path(capture)
        if local_path:
            return local_path
        return self._download_remote_video(capture, project_id)

    @staticmethod
    def _parser_stored_video_path(capture: ReferenceContentCapture) -> Path | None:
        source_metadata = capture.source_metadata if isinstance(capture.source_metadata, dict) else {}
        candidates = [
            source_metadata.get("stored_video_path"),
            source_metadata.get("parser_stored_video_path"),
            capture.video_url,
        ]
        for value in candidates:
            text = str(value or "").strip()
            if not text or text.startswith(("http://", "https://")):
                continue
            path = Path(text)
            if path.exists() and path.is_file() and path.stat().st_size > 0:
                return path
        return None

    @staticmethod
    def _video_extension(url: str) -> str:
        suffix = Path(urlparse(url).path).suffix.lower()
        if suffix in {".mp4", ".mov", ".m4v", ".webm"}:
            return suffix
        return ".mp4"

    def _parse_with_local_engine(self, capture: ReferenceContentCapture) -> VideoParserResult:
        adapter = LocalVideoParserAdapter(
            enabled=self.settings.video_parser_enabled,
            ytdlp_path=self.settings.video_parser_ytdlp_path,
            douyin_downloader_root=self.settings.video_parser_douyin_downloader_root,
            download_dir=(
                self.settings.storage_dir
                / "projects"
                / capture.project_id
                / "reference_collections"
                / capture.collection_id
                / "douyin_downloader"
            ),
            timeout_seconds=self.settings.video_parser_timeout_seconds,
            max_download_mb=self.settings.video_parser_max_download_mb,
            engine=self.settings.video_parser_engine,
            python_executable=self.settings.python_path,
            cloud_provider_order=self.settings.video_parser_cloud_provider_order,
            aivo_parser_base_url=self.settings.aivo_parser_base_url,
            aivo_parser_endpoint=self.settings.aivo_parser_endpoint,
            aivo_parser_token=self.settings.aivo_parser_token,
            tikhub_base_url=self.settings.tikhub_base_url,
            tikhub_api_key=self.settings.tikhub_api_key,
            tikhub_endpoint=self.settings.tikhub_douyin_endpoint,
            istero_base_url=self.settings.istero_base_url,
            istero_api_key=self.settings.istero_api_key,
            istero_endpoint=self.settings.istero_douyin_endpoint,
            evil0ctal_base_url=self.settings.evil0ctal_douyin_api_base_url,
            evil0ctal_endpoint=self.settings.evil0ctal_douyin_api_endpoint,
        )
        return adapter.parse(capture.source_url, platform=capture.platform)

    @classmethod
    def _unreachable_video_message(
        cls,
        capture: ReferenceContentCapture,
        parser_result: VideoParserResult,
    ) -> str:
        if cls._short_link_landed_on_platform_home(capture):
            return (
                "无法直接读取视频声音。这个抖音短链没有跳转到具体作品页，"
                "可能是链接失效、复制不完整、需要登录验证，或平台临时限制访问。"
            )
        return f"无法直接读取视频声音。{parser_result.message}"

    @staticmethod
    def _short_link_landed_on_platform_home(capture: ReferenceContentCapture) -> bool:
        if capture.platform != "douyin":
            return False
        final = urlparse(capture.final_url or "")
        source = urlparse(capture.source_url or "")
        final_host = final.netloc.lower()
        source_host = source.netloc.lower()
        final_path = (final.path or "/").rstrip("/") or "/"
        return source_host == "v.douyin.com" and final_host.endswith("douyin.com") and final_path == "/"

    def _capture_from_parser_result(
        self,
        capture: ReferenceContentCapture,
        parser_result: VideoParserResult,
    ) -> ReferenceContentCapture:
        capture.status = "captured"
        capture.final_url = parser_result.final_url or capture.final_url or capture.source_url
        capture.title = parser_result.title or capture.title
        capture.description = parser_result.description or capture.description
        capture.cover_url = parser_result.thumbnail_url or capture.cover_url
        capture.video_url = parser_result.video_url
        capture.downloadable = True
        capture.message = parser_result.message or "本地视频解析成功。"
        capture.recommended_next_action = "已拿到视频文件，将继续抽音频并转写文案。"
        capture.source_metadata = {
            **capture.source_metadata,
            **parser_result.source_metadata,
            "parser_engine": parser_result.engine,
            "parser_status": parser_result.status,
            "parser_message": parser_result.message,
            "stored_video_path": parser_result.stored_video_path or "",
        }
        lines = [f"平台：{capture.platform}", f"来源链接：{capture.source_url}"]
        if capture.title:
            lines.append(f"标题：{capture.title}")
        if capture.description:
            lines.append(f"文案：{capture.description}")
        capture.content_text = "\n".join(lines)
        capture.script_seed = "\n".join(
            item for item in [capture.title, capture.description] if item
        ).strip()
        if capture.collection_json:
            write_json(Path(capture.collection_json), capture.model_dump(mode="json"))
        return capture

    @staticmethod
    def _transcript_text(analysis: dict[str, object]) -> str:
        transcript = analysis.get("transcript") if isinstance(analysis, dict) else {}
        if not isinstance(transcript, dict):
            return ""
        segments = transcript.get("segments") or []
        if not isinstance(segments, list):
            return ""
        lines = [str(item.get("text") or "").strip() for item in segments if isinstance(item, dict)]
        return "\n".join([line for line in lines if line]).strip()

    @staticmethod
    def _reference_script_text(analysis: dict[str, object]) -> str:
        script = analysis.get("reference_script") if isinstance(analysis, dict) else {}
        if not isinstance(script, dict):
            return ""
        parts: list[str] = []
        hook = str(script.get("hook") or "").strip()
        if hook:
            parts.append(hook)
        body_points = script.get("body_points") or []
        if isinstance(body_points, list):
            parts.extend(str(item).strip() for item in body_points if str(item).strip())
        cta = str(script.get("cta") or "").strip()
        if cta:
            parts.append(cta)
        return "\n".join(parts).strip()

    @staticmethod
    def _real_transcription_blocker(analysis: dict[str, object], transcript_text: str) -> str:
        if not transcript_text:
            return "没有拿到真实语音转写稿：FunASR / Paraformer 没有返回可用文本，已拒绝用参考文案或模板覆盖脚本。"
        transcript = analysis.get("transcript") if isinstance(analysis, dict) else {}
        if isinstance(transcript, dict):
            engine = str(transcript.get("engine") or "").strip().lower()
            if engine in {"dryrun", "dry-run", "demo", "placeholder"}:
                return "当前得到的是演示转写模板，不是真实语音转写。请关闭演示模式，并确认 FunASR / Paraformer 模型可用。"
        reference = analysis.get("reference") if isinstance(analysis, dict) else {}
        report = reference.get("analysis_report") if isinstance(reference, dict) else {}
        audio_report = report.get("audio") if isinstance(report, dict) else {}
        audio_status = str(audio_report.get("status") or "").strip().lower() if isinstance(audio_report, dict) else ""
        if audio_status.startswith("dry_run") or "placeholder" in audio_status:
            return "视频音频没有真实抽取成功，不能把演示转写写入脚本。请检查 ffmpeg 和 FunASR / Paraformer 配置后重试。"
        return ""

    @staticmethod
    def _blocked(
        capture: ReferenceContentCapture,
        message: str,
        recommended_next_action: str,
    ) -> ReferenceLinkTranscriptionResult:
        return ReferenceLinkTranscriptionResult(
            status="blocked",
            message=message,
            platform=capture.platform,
            source_url=capture.source_url,
            final_url=capture.final_url,
            collection_id=capture.collection_id,
            recommended_next_action=recommended_next_action,
            collection=capture,
        )
