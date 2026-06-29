#!/usr/bin/env python3
from __future__ import annotations

import argparse
import zipfile
from datetime import datetime, timezone
from pathlib import Path

EXCLUDED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "dist",
    "node_modules",
    "storage",
    "third_party",
}
EXCLUDED_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".mp4",
    ".wav",
    ".mp3",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".pth",
    ".pt",
    ".ckpt",
    ".safetensors",
    ".onnx",
    ".pkl",
    ".zip",
}
INCLUDED_ROOT_FILES = {
    "AGENTS.md",
    "KNOWN_LIMITATIONS.md",
    "README.md",
    "THIRD_PARTY_MANIFEST.yml",
    "TRIAL_QUICKSTART.md",
    "TRIAL_README.md",
    "pyproject.toml",
    "start_trial.bat",
    "start_trial.ps1",
    "start_trial.sh",
}
INCLUDED_DIRS = {"app", "desktop", "docs", "scripts", "tools"}


def build_trial_package(
    *,
    root: Path | str = Path("."),
    output_dir: Path | str = Path("dist"),
    package_name: str = "AivoDigitalHuman_trial",
) -> str:
    root = Path(root).resolve()
    output_dir = Path(output_dir)
    if not output_dir.is_absolute():
        output_dir = root / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    zip_path = output_dir / f"{package_name}.zip"
    if zip_path.exists():
        zip_path.unlink()

    manifest = {
        "package": package_name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "policy": {
            "dry_run_ready": True,
            "duix_source_included": False,
            "model_weights_included": False,
            "generated_media_included": False,
            "third_party_source_included": False,
        },
    }
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("trial_manifest.json", _json_dump(manifest))
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(root)
            if _should_exclude(relative):
                continue
            if not _should_include(relative):
                continue
            archive.write(path, relative.as_posix())
    return str(zip_path)


def _should_include(relative: Path) -> bool:
    if len(relative.parts) == 1:
        return relative.name in INCLUDED_ROOT_FILES
    return relative.parts[0] in INCLUDED_DIRS


def _should_exclude(relative: Path) -> bool:
    parts = set(relative.parts)
    if parts & EXCLUDED_DIRS:
        return True
    if relative.suffix.lower() in EXCLUDED_SUFFIXES:
        return True
    if relative.name.startswith("."):
        return True
    return False


def _json_dump(data: dict[str, object]) -> str:
    import json

    return json.dumps(data, ensure_ascii=False, indent=2)


def main() -> int:
    parser = argparse.ArgumentParser(description="构建本地客户试用包 zip。")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--output-dir", default="dist")
    parser.add_argument("--package-name", default="AivoDigitalHuman_trial")
    args = parser.parse_args()
    zip_path = build_trial_package(root=Path(args.root), output_dir=Path(args.output_dir), package_name=args.package_name)
    print(f"trial_package={zip_path}")
    print(f"试用包已生成：{zip_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
