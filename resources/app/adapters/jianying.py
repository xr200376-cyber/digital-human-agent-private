import importlib
import json
from pathlib import Path
from typing import Any

from app import vendor
from app.adapters.base import AdapterError, DraftExportAdapter
from app.utils.files import ensure_dir, read_json, write_json


class JianyingDraftAdapter(DraftExportAdapter):
    name = "jianying_draft"

    def __init__(self, draft_root: str | None, dry_run: bool = True):
        super().__init__(dry_run=dry_run)
        self.draft_root = Path(draft_root) if draft_root else None

    def available(self) -> bool:
        return not self.dry_run and vendor.vendor_project_path("pyjianyingdraft") is not None

    def _load_draft_module(self):
        try:
            vendor.add_vendor_to_syspath("pyjianyingdraft", required=True)
            return importlib.import_module("pyJianYingDraft")
        except FileNotFoundError as exc:
            raise AdapterError(f"pyjianyingdraft vendored source is missing: {exc}") from exc
        except Exception as exc:
            raise AdapterError(
                "Failed to import pyJianYingDraft from vendored source. "
                "Install third_party/pyJianYingDraft/requirements.txt dependencies before real export. "
                f"Original error: {exc}"
            ) from exc

    @staticmethod
    def _format_seconds(value: float) -> str:
        return f"{max(0.0, value):g}s"

    @staticmethod
    def _read_segments(script_json: Path) -> list[dict[str, Any]]:
        data = json.loads(script_json.read_text(encoding="utf-8"))
        raw_segments = data.get("segments") or []
        segments: list[dict[str, Any]] = []
        for index, item in enumerate(raw_segments):
            text = str(item.get("text") or item.get("content") or "").strip()
            if not text:
                continue
            start = float(item.get("start", index * 3))
            end = float(item.get("end", start + 3))
            if end <= start:
                end = start + 3
            segments.append({"start": start, "end": end, "text": text})

        if segments:
            return segments

        fallback_text = str(data.get("body") or data.get("hook") or data.get("title") or "").strip()
        if fallback_text:
            return [{"start": 0.0, "end": 5.0, "text": fallback_text}]
        return [{"start": 0.0, "end": 5.0, "text": "AI IP talking video"}]

    @staticmethod
    def _template_payload(template_report: Path | None) -> dict[str, Any]:
        if template_report and template_report.exists():
            data = read_json(template_report)
            return {
                "template_id": data.get("template_id"),
                "template_name": data.get("template_name"),
                "resolution": data.get("resolution"),
                "subtitle_style": data.get("subtitle_style", {}),
                "title_style": data.get("title_style", {}),
                "bgm": data.get("bgm", {}),
                "intro": data.get("intro", {}),
                "outro": data.get("outro", {}),
                "safe_area": data.get("safe_area", {}),
                "cover_text": data.get("cover_text", {}),
                "template_report": str(template_report),
            }
        return {
            "template_id": "clean_talking_head",
            "template_name": "干净口播",
            "resolution": {"width": 1080, "height": 1920},
            "subtitle_style": {},
            "title_style": {},
            "bgm": {},
            "intro": {},
            "outro": {},
            "safe_area": {},
            "cover_text": {},
            "template_report": None,
        }

    @staticmethod
    def _template_tracks(template: dict[str, Any]) -> list[str]:
        tracks = ["video", "subtitles", "title", "cover"]
        if template.get("bgm", {}).get("enabled"):
            tracks.append("bgm")
        if template.get("intro", {}).get("enabled"):
            tracks.append("intro")
        if template.get("outro", {}).get("enabled"):
            tracks.append("outro")
        return tracks

    async def export_draft(
        self,
        final_video: Path,
        script_json: Path,
        out_dir: Path,
        *,
        template_report: Path | None = None,
    ) -> Path:
        template = self._template_payload(template_report)
        template_tracks = self._template_tracks(template)
        if self.dry_run:
            draft_dir = ensure_dir(out_dir / "jianying_draft")
            write_json(
                draft_dir / "draft_meta_info.json",
                {
                    "mock": True,
                    "source_video": str(final_video),
                    "script": str(script_json),
                    "template": template,
                    "template_tracks": template_tracks,
                    "note": "Replace with pyJianYingDraft project file generation.",
                },
            )
            return draft_dir

        draft = self._load_draft_module()
        if not final_video.exists():
            raise AdapterError(f"Final video not found for Jianying draft export: {final_video}")
        if not script_json.exists():
            raise AdapterError(f"Script JSON not found for Jianying draft export: {script_json}")

        draft_parent = ensure_dir(self.draft_root or out_dir)
        draft_name = "jianying_draft"
        segments = self._read_segments(script_json)
        total_duration = max(segment["end"] for segment in segments)

        try:
            draft_folder = draft.DraftFolder(str(draft_parent))
            script = draft_folder.create_draft(
                draft_name,
                1080,
                1920,
                fps=30,
                allow_replace=True,
            )
            script.add_track(draft.TrackType.video).add_track(draft.TrackType.text)
            video_range = draft.trange("0s", self._format_seconds(total_duration))
            script.add_segment(draft.VideoSegment(str(final_video), video_range))

            text_clip = draft.ClipSettings(transform_y=-0.75)
            if template_report and template_report.exists():
                title_text = template.get("template_name") or "Digital Human Video"
                title_range = draft.trange("0s", self._format_seconds(min(3.0, total_duration)))
                script.add_segment(
                    draft.TextSegment(
                        title_text,
                        title_range,
                        clip_settings=draft.ClipSettings(transform_y=0.72),
                    )
                )
            for segment in segments:
                text_range = draft.trange(
                    self._format_seconds(segment["start"]),
                    self._format_seconds(segment["end"] - segment["start"]),
                )
                script.add_segment(
                    draft.TextSegment(
                        segment["text"],
                        text_range,
                        clip_settings=text_clip,
                    )
                )
            script.save()
        except AdapterError:
            raise
        except Exception as exc:
            raise AdapterError(f"pyJianYingDraft export failed: {exc}") from exc

        return draft_parent / draft_name
