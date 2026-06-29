from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional
from urllib.parse import unquote, urlparse


class WorkflowStep(str, Enum):
    EXTRACTED     = "extracted"
    REWRITTEN     = "rewritten"
    CONFIRMED     = "confirmed"
    MODE_SELECTED = "mode_selected"  # 兼容旧会话；新流程不再使用模式选择
    AUDIO_DONE    = "audio_done"
    VIDEO_PENDING = "video_pending"
    VIDEO_DONE    = "video_done"
    VIDEO_FAILED  = "video_failed"


@dataclass
class WorkflowState:
    session_id:     str
    current_step:   WorkflowStep
    source:         str
    source_type:    str
    extracted_text: str
    rewritten_text: str = ""
    final_text:     str = ""
    audio_path:     Optional[str] = None
    avatar_image_path: Optional[str] = None
    video_url:      Optional[str] = None
    video_mode:     str = "avatar"
    video_status:   str = ""          # "", "queued", "processing", "succeed", "failed"
    video_error:    Optional[str] = None
    video_provider: str = "kling"     # "kling" | "baidu"
    baidu_task_id:  Optional[str] = None  # 百度云任务 ID，超时重试时直接接着轮询


@dataclass
class WorkflowSessionSummary:
    session_id: str
    current_step: str
    source_type: str
    text_preview: str
    video_mode: str
    video_url: Optional[str] = None
    updated_at: Optional[str] = None
    video_provider: str = "kling"


class InMemoryWorkflowStore:
    def __init__(self) -> None:
        self._store: dict[str, WorkflowState] = {}

    def __call__(self, session_id: str) -> WorkflowState:
        if session_id not in self._store:
            raise KeyError(session_id)
        return self._store[session_id]

    def create(self, state: WorkflowState) -> WorkflowState:
        self._store[state.session_id] = state
        return state

    def save(self, state: WorkflowState) -> WorkflowState:
        self._store[state.session_id] = state
        return state

    def list(self, limit: int = 50) -> list[WorkflowSessionSummary]:
        states = list(self._store.values())[-limit:]
        return [_summary_from_state(state) for state in reversed(states)]


class MySQLWorkflowStore:
    def __init__(self) -> None:
        try:
            import pymysql
        except ImportError as e:
            raise RuntimeError("使用 MySQL 存储需要先安装 PyMySQL：uv add PyMySQL") from e

        self._pymysql = pymysql
        self.table_name = _mysql_table_name()
        self.conn_kwargs = _mysql_conn_kwargs()
        self._ensure_table()

    def __call__(self, session_id: str) -> WorkflowState:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT * FROM `{self.table_name}` WHERE session_id=%s LIMIT 1",
                    (session_id,),
                )
                row = cur.fetchone()
        if not row:
            raise KeyError(session_id)
        return _state_from_row(row)

    def create(self, state: WorkflowState) -> WorkflowState:
        self.save(state)
        return state

    def save(self, state: WorkflowState) -> WorkflowState:
        row = _state_to_row(state)
        columns = [
            "session_id",
            "current_step",
            "source",
            "source_type",
            "extracted_text",
            "rewritten_text",
            "final_text",
            "audio_path",
            "avatar_image_path",
            "video_url",
            "video_mode",
            "video_status",
            "video_error",
            "video_provider",
            "baidu_task_id",
        ]
        placeholders = ", ".join(["%s"] * len(columns))
        column_sql = ", ".join(f"`{c}`" for c in columns)
        update_sql = ", ".join(f"`{c}`=VALUES(`{c}`)" for c in columns if c != "session_id")
        values = tuple(row[c] for c in columns)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO `{self.table_name}` ({column_sql})
                    VALUES ({placeholders})
                    ON DUPLICATE KEY UPDATE {update_sql}
                    """,
                    values,
                )
        return state

    def list(self, limit: int = 50) -> list[WorkflowSessionSummary]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT
                      session_id,
                      current_step,
                      source_type,
                      extracted_text,
                      rewritten_text,
                      final_text,
                      video_mode,
                      video_url,
                      video_provider,
                      updated_at
                    FROM `{self.table_name}`
                    ORDER BY updated_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
                rows = cur.fetchall()
        return [_summary_from_row(row) for row in rows]

    def _connect(self):
        return self._pymysql.connect(
            **self.conn_kwargs,
            autocommit=True,
            charset="utf8mb4",
            cursorclass=self._pymysql.cursors.DictCursor,
        )

    def _ensure_table(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS `{self.table_name}` (
                      session_id VARCHAR(64) PRIMARY KEY,
                      current_step VARCHAR(32) NOT NULL,
                      source LONGTEXT NOT NULL,
                      source_type VARCHAR(32) NOT NULL,
                      extracted_text LONGTEXT NOT NULL,
                      rewritten_text LONGTEXT NOT NULL,
                      final_text LONGTEXT NOT NULL,
                      audio_path TEXT NULL,
                      avatar_image_path TEXT NULL,
                      video_url TEXT NULL,
                      video_mode VARCHAR(32) NOT NULL,
                      video_status VARCHAR(32) NOT NULL DEFAULT '',
                      video_error TEXT NULL,
                      video_provider VARCHAR(32) NOT NULL DEFAULT 'kling',
                      baidu_task_id VARCHAR(128) NULL,
                      created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                      updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                        ON UPDATE CURRENT_TIMESTAMP
                    ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                    """
                )
        self._ensure_columns()

    def _ensure_columns(self) -> None:
        """旧库升级：补齐异步视频状态字段。"""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SHOW COLUMNS FROM `{self.table_name}`")
                existing = {row["Field"] for row in cur.fetchall()}
                if "video_status" not in existing:
                    cur.execute(
                        f"ALTER TABLE `{self.table_name}` "
                        "ADD COLUMN `video_status` VARCHAR(32) NOT NULL DEFAULT ''"
                    )
                if "video_error" not in existing:
                    cur.execute(
                        f"ALTER TABLE `{self.table_name}` "
                        "ADD COLUMN `video_error` TEXT NULL"
                    )
                if "video_provider" not in existing:
                    cur.execute(
                        f"ALTER TABLE `{self.table_name}` "
                        "ADD COLUMN `video_provider` VARCHAR(32) NOT NULL DEFAULT 'kling'"
                    )
                if "baidu_task_id" not in existing:
                    cur.execute(
                        f"ALTER TABLE `{self.table_name}` "
                        "ADD COLUMN `baidu_task_id` VARCHAR(128) NULL"
                    )


def make_workflow_store() -> Callable[[str], WorkflowState]:
    backend = os.getenv("WORKFLOW_STORE_BACKEND", "").strip().lower()
    if backend == "mysql" or os.getenv("WORKFLOW_DATABASE_URL", "").strip():
        return MySQLWorkflowStore()
    return InMemoryWorkflowStore()


def create_workflow(
    store_fn: Callable,
    source: str,
    source_type: str,
    extracted_text: str,
) -> WorkflowState:
    session_id = str(uuid.uuid4())
    state = WorkflowState(
        session_id=session_id,
        current_step=WorkflowStep.EXTRACTED,
        source=source,
        source_type=source_type,
        extracted_text=extracted_text,
    )
    if hasattr(store_fn, "create"):
        return store_fn.create(state)  # type: ignore[attr-defined]
    store_fn._store[session_id] = state  # type: ignore[attr-defined]
    return state


def save_workflow(store_fn: Callable, state: WorkflowState) -> WorkflowState:
    if hasattr(store_fn, "save"):
        return store_fn.save(state)  # type: ignore[attr-defined]
    store_fn._store[state.session_id] = state  # type: ignore[attr-defined]
    return state


def list_workflows(store_fn: Callable, limit: int = 50) -> list[WorkflowSessionSummary]:
    if hasattr(store_fn, "list"):
        return store_fn.list(limit=limit)  # type: ignore[attr-defined]
    states = list(store_fn._store.values())[-limit:]  # type: ignore[attr-defined]
    return [_summary_from_state(state) for state in reversed(states)]


def _state_to_row(state: WorkflowState) -> dict[str, str | None]:
    return {
        "session_id": state.session_id,
        "current_step": state.current_step.value,
        "source": state.source,
        "source_type": state.source_type,
        "extracted_text": state.extracted_text,
        "rewritten_text": state.rewritten_text,
        "final_text": state.final_text,
        "audio_path": state.audio_path,
        "avatar_image_path": state.avatar_image_path,
        "video_url": state.video_url,
        "video_mode": state.video_mode,
        "video_status": state.video_status,
        "video_error": state.video_error,
        "video_provider": state.video_provider,
        "baidu_task_id": state.baidu_task_id,
    }


def _state_from_row(row: dict) -> WorkflowState:
    return WorkflowState(
        session_id=row["session_id"],
        current_step=WorkflowStep(row["current_step"]),
        source=row["source"],
        source_type=row["source_type"],
        extracted_text=row["extracted_text"],
        rewritten_text=row.get("rewritten_text") or "",
        final_text=row.get("final_text") or "",
        audio_path=row.get("audio_path"),
        avatar_image_path=row.get("avatar_image_path"),
        video_url=row.get("video_url"),
        video_mode=row.get("video_mode") or "avatar",
        video_status=row.get("video_status") or ("succeed" if row.get("video_url") else ""),
        video_error=row.get("video_error"),
        video_provider=row.get("video_provider") or "kling",
        baidu_task_id=row.get("baidu_task_id") or None,
    )


def _summary_from_state(state: WorkflowState) -> WorkflowSessionSummary:
    return WorkflowSessionSummary(
        session_id=state.session_id,
        current_step=state.current_step.value,
        source_type=state.source_type,
        text_preview=_text_preview(state.final_text or state.rewritten_text or state.extracted_text),
        video_mode=state.video_mode,
        video_url=state.video_url,
        video_provider=state.video_provider,
    )


def _summary_from_row(row: dict) -> WorkflowSessionSummary:
    updated_at = row.get("updated_at")
    return WorkflowSessionSummary(
        session_id=row["session_id"],
        current_step=row["current_step"],
        source_type=row["source_type"],
        text_preview=_text_preview(
            row.get("final_text") or row.get("rewritten_text") or row.get("extracted_text") or ""
        ),
        video_mode=row.get("video_mode") or "",
        video_url=row.get("video_url"),
        updated_at=updated_at.isoformat(sep=" ") if hasattr(updated_at, "isoformat") else updated_at,
        video_provider=row.get("video_provider") or "kling",
    )


def _text_preview(text: str, limit: int = 48) -> str:
    normalized = " ".join((text or "").split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit]}..."


def _mysql_table_name() -> str:
    table_name = os.getenv("WORKFLOW_MYSQL_TABLE", "workflow_sessions").strip()
    if not re.fullmatch(r"[A-Za-z0-9_]+", table_name):
        raise ValueError("WORKFLOW_MYSQL_TABLE 只能包含字母、数字和下划线。")
    return table_name


def _mysql_conn_kwargs() -> dict:
    url = os.getenv("WORKFLOW_DATABASE_URL", "").strip()
    if url:
        parsed = urlparse(url)
        if parsed.scheme not in {"mysql", "mysql+pymysql"}:
            raise ValueError("WORKFLOW_DATABASE_URL 仅支持 mysql:// 或 mysql+pymysql://。")
        return {
            "host": parsed.hostname or "127.0.0.1",
            "port": parsed.port or 3306,
            "user": unquote(parsed.username or ""),
            "password": unquote(parsed.password or ""),
            "database": (parsed.path or "").lstrip("/"),
        }

    return {
        "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("MYSQL_USER", "root"),
        "password": os.getenv("MYSQL_PASSWORD", ""),
        "database": os.getenv("MYSQL_DATABASE", "digital_human_workflow"),
    }
