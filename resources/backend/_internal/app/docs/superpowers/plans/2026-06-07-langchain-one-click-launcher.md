# Langchain One-Click Launcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Windows one-click launcher for the downloaded `MaLunan/langchain` digital-human workflow.

**Architecture:** Serve `frontend/dist` from the FastAPI backend as a static fallback, then use a Python launcher to check dependencies, prepare `.env`, start uvicorn, wait for `/health`, and open the browser. A `.bat` wrapper gives users a simple double-click entry point.

**Tech Stack:** FastAPI, StaticFiles, PowerShell, Windows batch, pytest.

---

### Task 1: Serve Built Frontend

**Files:**
- Modify: `third_party/langchain/tests/test_server.py`
- Modify: `third_party/langchain/server.py`

- [ ] **Step 1: Write the failing test**

Add this test to `third_party/langchain/tests/test_server.py`:

```python
def test_root_serves_built_frontend():
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "数字人内容生成" in response.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_server.py::test_root_serves_built_frontend -q`

Expected: `404 Not Found`, because `server.py` does not currently serve the built frontend.

- [ ] **Step 3: Write minimal implementation**

In `third_party/langchain/server.py`, define `FRONTEND_DIST_DIR = _BASE_DIR / "frontend" / "dist"` near the existing storage directories. At the bottom of the file, after API/static media mounts, add:

```python
if FRONTEND_DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST_DIR), html=True), name="frontend")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_server.py::test_root_serves_built_frontend -q`

Expected: one passing test.

### Task 2: Add One-Click Launchers

**Files:**
- Create: `start_langchain_digital_human.py`
- Create: `start_langchain_digital_human.bat`

- [ ] **Step 1: Write launcher smoke check**

Run this before creating the files:

```powershell
Test-Path .\start_langchain_digital_human.py
Test-Path .\start_langchain_digital_human.bat
```

Expected: both commands print `False`.

- [ ] **Step 2: Create the Python launcher**

Create `start_langchain_digital_human.py` with:

```python
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
import tomllib
import urllib.request
import webbrowser
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
APP_DIR = ROOT_DIR / "third_party" / "langchain"
PORT = os.getenv("LANGCHAIN_DIGITAL_HUMAN_PORT", "8000")
BASE_URL = f"http://127.0.0.1:{PORT}"

def main() -> int:
    if not (APP_DIR / "server.py").exists():
        print(f"找不到下载项目：{APP_DIR}")
        return 1
    os.chdir(APP_DIR)
    ensure_dependencies()
    ensure_env_file()
    env = os.environ.copy()
    env["WORKFLOW_STORE_BACKEND"] = "memory"
    env["WORKFLOW_DATABASE_URL"] = ""
    log_dir = APP_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    stdout = (log_dir / "backend.out.log").open("w", encoding="utf-8")
    stderr = (log_dir / "backend.err.log").open("w", encoding="utf-8")
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", PORT],
        cwd=APP_DIR,
        env=env,
        stdout=stdout,
        stderr=stderr,
    )
    try:
        wait_for_backend(process)
        print(f"正在打开数字人软件：{BASE_URL}/")
        webbrowser.open(f"{BASE_URL}/")
        print("后端正在运行。按 Ctrl+C 可停止服务。")
        return process.wait()
    finally:
        process.terminate()
        stdout.close()
        stderr.close()

def ensure_dependencies() -> None:
    try:
        import fastapi  # noqa: F401
        import langchain_openai  # noqa: F401
        import uvicorn  # noqa: F401
        return
    except Exception:
        pass
    deps = tomllib.loads((APP_DIR / "pyproject.toml").read_text(encoding="utf-8"))["project"]["dependencies"]
    subprocess.check_call([sys.executable, "-m", "pip", "install", *deps])

def ensure_env_file() -> None:
    env_path = APP_DIR / ".env"
    if not env_path.exists():
        shutil.copyfile(APP_DIR / ".env.example", env_path)
    text = env_path.read_text(encoding="utf-8")
    if re.search(r"(?m)^MOONSHOT_API_KEY=\s*$", text):
        print(f"请先填写 Moonshot Key：{env_path}")
        if os.name == "nt":
            subprocess.run(["notepad.exe", str(env_path)], check=False)
        text = env_path.read_text(encoding="utf-8")
        if re.search(r"(?m)^MOONSHOT_API_KEY=\s*$", text):
            raise RuntimeError("MOONSHOT_API_KEY 仍为空，已取消启动。")

def wait_for_backend(process: subprocess.Popen) -> None:
    for _ in range(45):
        if process.poll() is not None:
            raise RuntimeError(f"后端进程已退出，退出码：{process.returncode}")
        try:
            with urllib.request.urlopen(f"{BASE_URL}/health", timeout=2) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(1)
    raise RuntimeError("45 秒内未等到后端启动成功。")

if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Create the batch wrapper**

Create `start_langchain_digital_human.bat` with:

```bat
@echo off
setlocal
cd /d "%~dp0"
python "%~dp0start_langchain_digital_human.py"
if errorlevel 1 (
  echo.
  echo 启动失败，请查看上面的错误信息。
  pause
)
```

- [ ] **Step 4: Verify launcher files exist**

Run:

```powershell
Test-Path .\start_langchain_digital_human.py
Test-Path .\start_langchain_digital_human.bat
```

Expected: both commands print `True`.

### Task 3: Verify Locally

**Files:**
- No edits.

- [ ] **Step 1: Run server tests**

Run: `python -m pytest tests/test_server.py -q`

Expected: both server tests pass.

- [ ] **Step 2: Compile changed backend**

Run: `python -m compileall server.py`

Expected: command exits with code `0`.

- [ ] **Step 3: Smoke test HTTP responses**

Start uvicorn in the downloaded project, query `http://127.0.0.1:8000/health` and `http://127.0.0.1:8000/`, then stop the process.

Expected: `/health` returns status `200` with JSON, and `/` returns HTML containing `数字人内容生成`.
