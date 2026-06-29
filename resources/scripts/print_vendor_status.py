#!/usr/bin/env python3
import json
from pathlib import Path


def main() -> int:
    manifest = Path("third_party") / "THIRD_PARTY_MANIFEST.generated.json"
    if not manifest.exists():
        manifest = Path("third_party") / "THIRD_PARTY_MANIFEST.dry-run.json"
    if not manifest.exists():
        raise SystemExit("no third-party manifest found")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    for project in data.get("projects", []):
        print(f"{project.get('key')}: {project.get('status')} -> {project.get('target')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
