import hashlib
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.utils.files import ensure_dir, write_json


EXCLUDED_PREFIXES = ("third_party/",)
EXCLUDED_SUFFIXES = (
    ".ckpt",
    ".pth",
    ".pt",
    ".safetensors",
    ".onnx",
    ".gguf",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_items(task_dir: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for path in sorted(task_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(task_dir).as_posix()
        if _excluded(rel):
            continue
        items.append(
            {
                "name": path.name,
                "path": str(path),
                "relative_path": rel,
                "exists": path.exists(),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "validation_status": "ok" if path.stat().st_size > 0 else "warning",
                "validation_warnings": [] if path.stat().st_size > 0 else ["empty file"],
            }
        )
    return items


def write_artifact_manifest(task_dir: Path) -> Path:
    return write_json(
        task_dir / "artifact_manifest.json",
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "items": artifact_items(task_dir),
        },
    )


def build_artifacts_zip(task_dir: Path) -> Path:
    manifest_path = write_artifact_manifest(task_dir)
    zip_path = task_dir / "artifacts.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for item in artifact_items(task_dir):
            path = Path(item["path"])
            rel = item["relative_path"]
            if path == zip_path or path.name == "artifacts.zip" or _excluded(rel):
                continue
            archive.write(path, rel)
        if manifest_path.exists() and "artifact_manifest.json" not in archive.namelist():
            archive.write(manifest_path, "artifact_manifest.json")
    return zip_path


def _excluded(relative_path: str) -> bool:
    lowered = relative_path.lower()
    return lowered.startswith(EXCLUDED_PREFIXES) or lowered.endswith(EXCLUDED_SUFFIXES)
