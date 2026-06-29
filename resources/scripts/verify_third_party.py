#!/usr/bin/env python3
"""Verify vendored third-party source trees have the minimum license metadata."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

CONDITIONAL_KEYS = {"duix-avatar"}


def main() -> int:
    root = Path(os.getenv("THIRD_PARTY_ROOT", "third_party"))
    manifest_path = root / "THIRD_PARTY_MANIFEST.generated.json"
    if not manifest_path.exists():
        print(f"No generated third-party manifest found at {manifest_path}. Run scripts/vendor_sources.py first.")
        return 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    for project in manifest.get("projects", []):
        key = project.get("key")
        target = Path(project.get("target", ""))
        license_files = [Path(p) for p in project.get("license_files", [])]
        if not target.exists():
            errors.append(f"Missing source directory for {key}: {target}")
        if not license_files or not any(p.exists() for p in license_files):
            errors.append(f"Missing preserved license/notice file for {key}")
        if key in CONDITIONAL_KEYS and os.getenv("ALLOW_DUIX_COMMUNITY_LICENSE") != "1":
            errors.append(f"{key} has a conditional community license; set ALLOW_DUIX_COMMUNITY_LICENSE=1 only after approval.")
    if errors:
        print("Third-party verification failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Third-party source verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
