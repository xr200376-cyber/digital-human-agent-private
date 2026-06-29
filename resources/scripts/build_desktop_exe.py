#!/usr/bin/env python3
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = ROOT / "dist" / "AivoDigitalHuman"
ZIP_PATH = ROOT / "dist" / "AivoDigitalHuman_windows.zip"


def main() -> int:
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "AivoDigitalHuman.spec"]
    subprocess.run(cmd, cwd=ROOT, check=True)
    exe = DIST_DIR / "AivoDigitalHuman.exe"
    if not exe.exists():
        raise SystemExit(f"missing exe: {exe}")

    storage = DIST_DIR / "storage"
    if storage.exists():
        shutil.rmtree(storage)
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    shutil.make_archive(str(ZIP_PATH.with_suffix("")), "zip", DIST_DIR)
    print(f"exe={exe}")
    print(f"zip={ZIP_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
