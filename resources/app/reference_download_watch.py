from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.reference_link_transcription import ReferenceLinkTranscriptionService
from app.schemas import (
    ReferenceDownloadWatchStartRequest,
    ReferenceDownloadWatchStatus,
    ReferenceLinkTranscriptionResult,
)
from app.settings import Settings
from app.utils.files import ensure_dir, read_json, write_json


VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}
TEMP_SUFFIXES = {".crdownload", ".tmp", ".download", ".part"}


class ReferenceDownloadWatchService:
    """Watch a user's download folder for an officially downloaded reference video."""

    def __init__(
        self,
        settings: Settings,
        transcription_service: ReferenceLinkTranscriptionService | None = None,
    ) -> None:
        self.settings = settings
        self.transcription_service = transcription_service or ReferenceLinkTranscriptionService(settings)
        self.root = ensure_dir(settings.storage_dir / "reference_download_watches")

    def start(self, project_id: str, request: ReferenceDownloadWatchStartRequest) -> ReferenceDownloadWatchStatus:
        download_dir = self._resolve_download_dir(request.download_dir)
        if not request.download_dir:
            ensure_dir(download_dir)
        if not download_dir.exists() or not download_dir.is_dir():
            raise FileNotFoundError(f"download directory not found: {download_dir}")
        now = time.time()
        watch_id = "dlwatch_" + uuid4().hex
        payload = {
            "watch_id": watch_id,
            "project_id": project_id,
            "status": "watching",
            "message": "已开始监听下载目录。请在抖音客户端点官方下载，下载完成后会自动导入转写。",
            "platform": request.platform or "douyin",
            "source_url": request.url or "",
            "download_dir": str(download_dir),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "started_at_epoch": now,
            "timeout_seconds": request.timeout_seconds,
            "asr_engine": request.asr_engine or "funasr",
            "force": request.force,
            "metadata": request.metadata,
            "candidate_path": "",
            "candidate_size": None,
            "result": None,
        }
        self._save(payload)
        return self._status(payload)

    def poll(self, project_id: str, watch_id: str) -> ReferenceDownloadWatchStatus:
        payload = self._load(watch_id)
        if payload.get("project_id") != project_id:
            raise KeyError(f"download watch not found: {watch_id}")
        if payload.get("status") == "completed":
            return self._status(payload)

        started_at = float(payload.get("started_at_epoch") or 0)
        timeout_seconds = int(payload.get("timeout_seconds") or 600)
        if time.time() - started_at > timeout_seconds:
            payload["status"] = "expired"
            payload["message"] = "监听已超时。请重新点击解析并在抖音客户端下载视频。"
            self._save(payload)
            return self._status(payload)

        candidate = self._find_candidate(Path(str(payload.get("download_dir") or "")), started_at)
        if not candidate:
            payload["status"] = "watching"
            payload["message"] = "正在等待抖音客户端下载视频。下载完成后会自动导入。"
            self._save(payload)
            return self._status(payload)

        size = candidate.stat().st_size
        if payload.get("candidate_path") != str(candidate) or payload.get("candidate_size") != size:
            payload["status"] = "stabilizing"
            payload["message"] = "已检测到新视频，正在等待文件写入完成。"
            payload["candidate_path"] = str(candidate)
            payload["candidate_size"] = size
            self._save(payload)
            return self._status(payload)

        result = self.transcription_service.transcribe_local_video(
            project_id,
            candidate,
            platform=str(payload.get("platform") or "douyin"),
            source_url=str(payload.get("source_url") or ""),
            asr_engine=str(payload.get("asr_engine") or "funasr"),
            force=bool(payload.get("force")),
            metadata={
                **(payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}),
                "download_watch_id": watch_id,
                "downloaded_path": str(candidate),
            },
        )
        payload["status"] = "completed" if result.status == "transcribed" else "failed"
        payload["message"] = result.message
        payload["result"] = result.model_dump(mode="json")
        payload["completed_at"] = datetime.now(timezone.utc).isoformat()
        self._save(payload)
        return self._status(payload)

    def _watch_file(self, watch_id: str) -> Path:
        safe_id = "".join(ch for ch in watch_id if ch.isalnum() or ch in {"_", "-"})
        return self.root / f"{safe_id}.json"

    def _save(self, payload: dict[str, object]) -> None:
        write_json(self._watch_file(str(payload["watch_id"])), payload)

    def _load(self, watch_id: str) -> dict[str, object]:
        path = self._watch_file(watch_id)
        if not path.exists():
            raise KeyError(f"download watch not found: {watch_id}")
        data = read_json(path)
        if not isinstance(data, dict):
            raise KeyError(f"download watch invalid: {watch_id}")
        return data

    @staticmethod
    def _resolve_download_dir(download_dir: str | None) -> Path:
        if download_dir:
            return Path(download_dir).expanduser()
        return Path.home() / "Downloads"

    @staticmethod
    def _find_candidate(download_dir: Path, started_at_epoch: float) -> Path | None:
        if not download_dir.exists() or not download_dir.is_dir():
            return None
        candidates: list[tuple[float, Path]] = []
        for path in download_dir.iterdir():
            if not path.is_file():
                continue
            suffix = path.suffix.lower()
            if suffix in TEMP_SUFFIXES or suffix not in VIDEO_SUFFIXES:
                continue
            stat = path.stat()
            if stat.st_size <= 0:
                continue
            if stat.st_mtime < started_at_epoch - 1.0:
                continue
            candidates.append((stat.st_mtime, path))
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

    @staticmethod
    def _status(payload: dict[str, object]) -> ReferenceDownloadWatchStatus:
        result_payload = payload.get("result")
        result = (
            ReferenceLinkTranscriptionResult.model_validate(result_payload)
            if isinstance(result_payload, dict)
            else None
        )
        return ReferenceDownloadWatchStatus(
            watch_id=str(payload.get("watch_id") or ""),
            status=str(payload.get("status") or "watching"),
            message=str(payload.get("message") or ""),
            platform=str(payload.get("platform") or "douyin"),
            source_url=str(payload.get("source_url") or ""),
            download_dir=str(payload.get("download_dir") or ""),
            candidate_path=str(payload.get("candidate_path") or ""),
            candidate_size=payload.get("candidate_size") if isinstance(payload.get("candidate_size"), int) else None,
            result=result,
        )
