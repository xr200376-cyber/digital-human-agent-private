from __future__ import annotations

import csv
import json
from pathlib import Path

from app.audit import append_audit_event
from app.schemas import FeedbackRecord, FeedbackRequest
from app.settings import Settings
from app.utils.files import ensure_dir


class FeedbackStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.root = ensure_dir(settings.storage_dir / "feedback")
        self.jsonl_path = self.root / "feedback.jsonl"
        self.csv_path = self.root / "feedback_export.csv"

    def create(self, request: FeedbackRequest) -> FeedbackRecord:
        record = FeedbackRecord(**request.model_dump())
        ensure_dir(self.jsonl_path.parent)
        with self.jsonl_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.model_dump(mode="json"), ensure_ascii=False) + "\n")
        append_audit_event(
            self.settings.storage_dir,
            action="feedback.submitted",
            details={"feedback_id": record.feedback_id, "rating": record.rating, "category": record.category},
        )
        return record

    def list(self) -> list[FeedbackRecord]:
        if not self.jsonl_path.exists():
            return []
        rows: list[FeedbackRecord] = []
        for line in self.jsonl_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rows.append(FeedbackRecord.model_validate(json.loads(line)))
            except (json.JSONDecodeError, ValueError):
                continue
        return rows

    def export_csv(self) -> Path:
        rows = self.list()
        fieldnames = ["feedback_id", "created_at", "rating", "category", "message", "contact"]
        ensure_dir(self.csv_path.parent)
        with self.csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        "feedback_id": row.feedback_id,
                        "created_at": row.created_at.isoformat(),
                        "rating": row.rating,
                        "category": row.category.value if hasattr(row.category, "value") else row.category,
                        "message": row.message,
                        "contact": row.contact or "",
                    }
                )
        return self.csv_path
