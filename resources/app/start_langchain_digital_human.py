from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
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
    stdout_path = log_dir / "backend.out.log"
    stderr_path = log_dir / "backend.err.log"

    if is_backend_ready():
        print(f"后端已在运行，正在打开数字人软件：{BASE_URL}/")
        webbrowser.open(f"{BASE_URL}/")
        return 0

    print(f"正在启动数字人工作流后端：{BASE_URL}")
    with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open(
        "w", encoding="utf-8"
    ) as stderr:
        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", PORT],
            cwd=APP_DIR,
            env=env,
            stdout=stdout,
            stderr=stderr,
            creationflags=creationflags,
            start_new_session=os.name != "nt",
        )
        try:
            wait_for_backend(process)
            print(f"正在打开数字人软件：{BASE_URL}/")
            webbrowser.open(f"{BASE_URL}/")
            print("后端已在后台运行，可以关闭此窗口。")
            print(f"日志：{stdout_path}")
            return 0
        except Exception:
            if process.poll() is None:
                process.terminate()
            raise


def is_backend_ready() -> bool:
    try:
        with urllib.request.urlopen(f"{BASE_URL}/health", timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def ensure_dependencies() -> None:
    try:
        import fastapi  # noqa: F401
        import imageio_ffmpeg  # noqa: F401
        import langchain_openai  # noqa: F401
        import uvicorn  # noqa: F401

        return
    except Exception:
        pass

    print("首次运行：正在安装 Python 依赖，请稍等...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", *load_dependencies()])


def load_dependencies() -> list[str]:
    pyproject_path = APP_DIR / "pyproject.toml"
    text = pyproject_path.read_text(encoding="utf-8")
    try:
        import tomllib

        return tomllib.loads(text)["project"]["dependencies"]
    except Exception:
        match = re.search(r"(?ms)^dependencies\s*=\s*\[(.*?)\]", text)
        if not match:
            raise RuntimeError(f"无法读取依赖列表：{pyproject_path}")
        return [
            line.strip().strip(",").strip('"')
            for line in match.group(1).splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]


def ensure_env_file() -> None:
    env_path = APP_DIR / ".env"
    if not env_path.exists():
        shutil.copyfile(APP_DIR / ".env.example", env_path)
        print(f"已创建默认配置文件：{env_path}")

    text = env_path.read_text(encoding="utf-8")
    if re.search(r"(?m)^MOONSHOT_API_KEY=\s*$", text):
        print(f"提示：MOONSHOT_API_KEY 为空，软件会先打开；使用 AI 改写前请编辑：{env_path}")


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
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("已停止。")
        raise SystemExit(0)
    except Exception as exc:
        print(str(exc))
        input("按回车退出")
        raise SystemExit(1)
