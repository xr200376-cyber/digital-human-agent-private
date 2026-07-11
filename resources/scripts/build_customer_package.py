from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any


SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "token",
    "secret",
    "password",
    "authorization",
    "access_key",
)
TEST_API_KEY_ALLOWLIST = {
    "DASHSCOPE_API_KEY",
    "HIFLY_TOKEN",
    "OBJECT_STORAGE_ACCESS_KEY_ID",
    "OBJECT_STORAGE_SECRET_ACCESS_KEY",
}
USER_PATH_KEYS = {
    "PYTHON_PATH",
    "pythonPath",
    "JIANYING_DRAFT_ROOT",
    "REFERENCE_FFMPEG_PATH",
}
GENERATED_STORAGE_DIRS = {
    "browser_profiles",
    "tasks",
    "video_remix_tasks",
    "cover_tasks",
    "references",
    "logs",
    "publish_queue",
    "jobs",
    "feedback",
    "objects",
}
PRESERVED_STORAGE_DIRS = {
    "preset_voice_assets",
}


def sanitize_desktop_settings(
    raw: dict[str, Any] | None,
    *,
    include_test_api_keys: bool = False,
) -> dict[str, Any]:
    raw = dict(raw or {})
    sanitized: dict[str, Any] = {}
    for key, value in raw.items():
        if key in USER_PATH_KEYS or (
            _is_sensitive_key(key)
            and not (include_test_api_keys and key in TEST_API_KEY_ALLOWLIST)
        ):
            sanitized[key] = ""
        else:
            sanitized[key] = value
    sanitized["runtime_mode"] = "final"
    sanitized["runtimeMode"] = "final"
    sanitized.pop("DRY_RUN", None)
    sanitized["dryRun"] = False
    sanitized["STORAGE_DIR"] = "storage"
    sanitized["storagePath"] = "storage"
    sanitized["PYTHON_PATH"] = ""
    sanitized["pythonPath"] = ""
    sanitized["tts_provider"] = "aliyun_bailian_cosyvoice"
    sanitized["digital_human_engine"] = "hifly"
    sanitized["editing_output"] = "mp4_only"
    sanitized["TTS_ENGINE"] = "cloud_clone"
    sanitized["CLOUD_VOICE_PROVIDER"] = "aliyun_bailian_cosyvoice"
    sanitized["CLOUD_VIDEO_PROVIDER"] = "hifly"
    sanitized["PIXELLE_ENABLED"] = False
    sanitized["JIANYING_ENABLED"] = False
    sanitized["HIFLY_ENABLED"] = True
    sanitized["HIFLY_REQUIRED"] = False
    return sanitized


def validate_delivery_tree(root: Path | str, *, allow_test_api_keys: bool = False) -> None:
    root = Path(root)
    backend_exe = root / "resources" / "backend" / "aivo_backend.exe"
    python_exe = root / "resources" / "python" / "python.exe"
    if not backend_exe.exists() and not python_exe.exists():
        raise ValueError("客户包缺少后端运行入口：需要 resources/backend/aivo_backend.exe 或 resources/python/python.exe")
    runtime_bin = root / "resources" / "storage" / "runtime_bin"
    for tool_name in ("ffmpeg.exe", "yt-dlp.exe"):
        if not (runtime_bin / tool_name).exists():
            raise ValueError(f"客户包缺少本地全流程工具：resources/storage/runtime_bin/{tool_name}")

    _validate_standalone_ytdlp(runtime_bin / "yt-dlp.exe")

    settings_path = root / "resources" / "storage" / "desktop" / "desktop_settings.json"
    if settings_path.exists():
        data = json.loads(settings_path.read_text(encoding="utf-8-sig"))
        leaked = _find_sensitive_values(
            data,
            allowed_keys=TEST_API_KEY_ALLOWLIST if allow_test_api_keys else set(),
        )
        if leaked:
            raise ValueError(f"客户包包含敏感配置：{', '.join(sorted(leaked))}")

    storage_root = root / "resources" / "storage"
    for name in GENERATED_STORAGE_DIRS:
        if (storage_root / name).exists():
            raise ValueError(f"客户包不应包含历史运行数据：resources/storage/{name}")
    for embedded_storage in (
        root / "resources" / "app" / "storage",
        root / "resources" / "backend" / "_internal" / "app" / "storage",
    ):
        if embedded_storage.exists():
            raise ValueError(f"客户包不应包含嵌入式运行数据：{embedded_storage.relative_to(root).as_posix()}")


def build_customer_package(
    *,
    source: Path | str,
    output_dir: Path | str,
    backend_dir: Path | str | None = None,
    ffmpeg_exe: Path | str | None = None,
    ytdlp_exe: Path | str | None = None,
    include_test_api_keys: bool = False,
    product: str = "数字人智能体",
) -> Path:
    source = Path(source).resolve()
    output_dir = Path(output_dir).resolve()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    package_dir = output_dir / f"{product}_交付包_{timestamp}"
    app_dir = package_dir / product
    cleanup_old_delivery_packages(output_dir, product)
    if package_dir.exists():
        _remove_tree(package_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    shutil.copytree(source, app_dir, ignore=_copy_ignore)
    _remove_embedded_storage(app_dir)
    _reset_storage(app_dir, source, include_test_api_keys=include_test_api_keys)
    if backend_dir:
        _copy_backend(Path(backend_dir), app_dir)
        _remove_embedded_storage(app_dir)
    resolved_ffmpeg = Path(ffmpeg_exe) if ffmpeg_exe else _source_runtime_tool(source, "ffmpeg.exe")
    resolved_ytdlp = Path(ytdlp_exe) if ytdlp_exe else _source_runtime_tool(source, "yt-dlp.exe")
    if resolved_ffmpeg:
        _copy_ffmpeg(resolved_ffmpeg, app_dir)
    if resolved_ytdlp:
        _copy_ytdlp(resolved_ytdlp, app_dir)
    _write_launch_files(app_dir, product)
    validate_delivery_tree(app_dir, allow_test_api_keys=include_test_api_keys)

    portable_zip = package_dir / f"{product}_便携版_{timestamp}.zip"
    _zip_dir(app_dir, portable_zip)
    installer_zip = _build_scripted_installer(package_dir, portable_zip, product, timestamp)
    manifest = {
        "product": product,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": str(source),
        "portable_zip": str(portable_zip),
        "installer_zip": str(installer_zip),
        "backend_included": bool(backend_dir),
        "ffmpeg_included": bool(resolved_ffmpeg),
        "ytdlp_included": bool(resolved_ytdlp),
        "secrets_included": bool(include_test_api_keys),
        "test_api_keys_included": bool(include_test_api_keys),
    }
    (package_dir / "打包清单.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return package_dir


def cleanup_old_delivery_packages(output_dir: Path | str, product: str = "数字人智能体") -> list[Path]:
    output_dir = Path(output_dir).resolve()
    if not output_dir.exists():
        return []
    deleted: list[Path] = []
    pattern = f"{product}_交付包_*"
    for old_package in sorted(output_dir.glob(pattern)):
        if not old_package.is_dir():
            continue
        resolved = old_package.resolve()
        if resolved.parent != output_dir:
            raise ValueError(f"拒绝删除输出目录外的旧交付包：{resolved}")
        _remove_tree(resolved)
        deleted.append(resolved)
    return deleted


def _copy_ignore(dir_path: str, names: list[str]) -> set[str]:
    ignored: set[str] = set()
    current = Path(dir_path)
    for name in names:
        if name in {"browser_profiles", "__pycache__"}:
            ignored.add(name)
        if current.name == "storage" and name in GENERATED_STORAGE_DIRS:
            ignored.add(name)
        if name.endswith((".pyc", ".pyo")):
            ignored.add(name)
    return ignored


def _reset_storage(app_dir: Path, source: Path, *, include_test_api_keys: bool = False) -> None:
    storage = app_dir / "resources" / "storage"
    if storage.exists():
        _remove_tree(storage)
    desktop = storage / "desktop"
    desktop.mkdir(parents=True, exist_ok=True)
    source_settings = source / "resources" / "storage" / "desktop" / "desktop_settings.json"
    raw: dict[str, Any] = {}
    if source_settings.exists():
        raw = json.loads(source_settings.read_text(encoding="utf-8-sig"))
    (desktop / "desktop_settings.json").write_text(
        json.dumps(
            sanitize_desktop_settings(raw, include_test_api_keys=include_test_api_keys),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    for name in PRESERVED_STORAGE_DIRS:
        source_dir = source / "resources" / "storage" / name
        if source_dir.exists():
            shutil.copytree(source_dir, storage / name)


def _copy_backend(backend_dir: Path, app_dir: Path) -> None:
    destination = app_dir / "resources" / "backend"
    if destination.exists():
        _remove_tree(destination)
    shutil.copytree(backend_dir, destination)


def _remove_embedded_storage(app_dir: Path) -> None:
    for storage in (
        app_dir / "resources" / "app" / "storage",
        app_dir / "resources" / "backend" / "_internal" / "app" / "storage",
    ):
        if storage.exists():
            _remove_tree(storage)


def _remove_tree(path: Path) -> None:
    def _clear_readonly(func, target, _exc_info):
        os.chmod(target, stat.S_IWRITE)
        func(target)

    shutil.rmtree(path, onerror=_clear_readonly)


def _copy_ffmpeg(ffmpeg_exe: Path, app_dir: Path) -> None:
    runtime_bin = app_dir / "resources" / "storage" / "runtime_bin"
    runtime_bin.mkdir(parents=True, exist_ok=True)
    target = runtime_bin / "ffmpeg.exe"
    shutil.copy2(ffmpeg_exe, target)
    (runtime_bin / "ffmpeg.cmd").write_text('@echo off\r\n"%~dp0ffmpeg.exe" %*\r\n', encoding="utf-8")


def _source_runtime_tool(source: Path, tool_name: str) -> Path | None:
    candidate = source / "resources" / "storage" / "runtime_bin" / tool_name
    if candidate.exists():
        return candidate
    return None


def _copy_ytdlp(ytdlp_exe: Path, app_dir: Path) -> None:
    _validate_standalone_ytdlp(ytdlp_exe)
    runtime_bin = app_dir / "resources" / "storage" / "runtime_bin"
    runtime_bin.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ytdlp_exe, runtime_bin / "yt-dlp.exe")


def _validate_standalone_ytdlp(ytdlp_exe: Path) -> None:
    if not ytdlp_exe.exists():
        raise ValueError(f"yt-dlp.exe missing: {ytdlp_exe}")
    # The pip-generated Windows console launcher is about 100 KB and depends on
    # the developer machine's Python/site-packages. Customer portable packages
    # need the official standalone executable, which is much larger.
    if ytdlp_exe.stat().st_size < 1_000_000:
        raise ValueError(
            "yt-dlp.exe is not standalone. Use the official GitHub release executable, "
            "not the small Python Scripts launcher."
        )


def _write_launch_files(app_dir: Path, product: str) -> None:
    exe_name = "Aivo 数字人口播工作台.exe"
    (app_dir / f"启动{product}.bat").write_text(f'@echo off\r\nstart "" "%~dp0{exe_name}"\r\n', encoding="gbk", errors="ignore")
    (app_dir / "使用说明.txt").write_text(
        f"{product}\n\n1. 双击 {exe_name} 启动。\n2. 首次启动会自动拉起本地后端，请等待 10-30 秒。\n3. 如果看到后端启动失败页面，请把页面上的日志路径发给技术支持。\n",
        encoding="utf-8",
    )


def _build_scripted_installer(package_dir: Path, portable_zip: Path, product: str, timestamp: str) -> Path:
    installer_dir = package_dir / f"{product}_安装包_{timestamp}"
    installer_dir.mkdir(parents=True, exist_ok=True)
    payload = installer_dir / "payload.zip"
    shutil.copy2(portable_zip, payload)
    # Windows PowerShell 5 treats UTF-8 without BOM as the local ANSI code page.
    # The installer contains Chinese text, so write a BOM to keep parsing stable.
    (installer_dir / "install.ps1").write_text(_install_script(product), encoding="utf-8-sig")
    (installer_dir / "安装.cmd").write_text(
        '@echo off\r\npowershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"\r\npause\r\n',
        encoding="gbk",
        errors="ignore",
    )
    (installer_dir / "安装说明.txt").write_text("双击 安装.cmd 完成安装。安装后桌面会生成快捷方式。\n", encoding="utf-8")
    installer_zip = package_dir / f"{product}_安装包_{timestamp}.zip"
    _zip_dir(installer_dir, installer_zip)
    return installer_zip


def _install_script(product: str) -> str:
    return f"""$ErrorActionPreference = 'Stop'
$product = '{product}'
$zip = Join-Path $PSScriptRoot 'payload.zip'
if (!(Test-Path $zip)) {{ throw '未找到 payload.zip，请保持安装包文件完整。' }}
$programs = Join-Path $env:LOCALAPPDATA 'Programs'
$installDir = Join-Path $programs $product
$preserveRoot = Join-Path ([System.IO.Path]::GetTempPath()) ($product + '_install_preserve')
$oldCommercialDir = Join-Path $installDir 'resources\storage\desktop\commercial'
$oldSettingsFile = Join-Path $installDir 'resources\storage\desktop\desktop_settings.json'
New-Item -ItemType Directory -Path $programs -Force | Out-Null
Get-CimInstance Win32_Process | Where-Object {{
  ($_.ExecutablePath -and $_.ExecutablePath.StartsWith($installDir, [System.StringComparison]::OrdinalIgnoreCase)) -or
  ($_.Name -eq 'aivo_backend.exe') -or
  ($_.CommandLine -like '*uvicorn*app.main*--port 8080*') -or
  ($_.CommandLine -like '*uvicorn*app.main*--port*8080*') -or
  ($_.CommandLine -like '*aivo_backend.exe*--port*8080*')
}} | ForEach-Object {{
  Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}}
Start-Sleep -Seconds 1
if (Test-Path $preserveRoot) {{
  Remove-Item -LiteralPath $preserveRoot -Recurse -Force -ErrorAction SilentlyContinue
}}
New-Item -ItemType Directory -Path $preserveRoot -Force | Out-Null
if (Test-Path $oldCommercialDir) {{
  Copy-Item -LiteralPath $oldCommercialDir -Destination (Join-Path $preserveRoot 'commercial') -Recurse -Force
}}
if (Test-Path $oldSettingsFile) {{
  Copy-Item -LiteralPath $oldSettingsFile -Destination (Join-Path $preserveRoot 'desktop_settings.json') -Force
}}
$backupPattern = $product + '_backup_*'
Get-ChildItem -LiteralPath $programs -Directory -Filter $backupPattern -ErrorAction SilentlyContinue | ForEach-Object {{
  Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
}}
if (Test-Path $installDir) {{
  Remove-Item -LiteralPath $installDir -Recurse -Force
}}
$driveName = [System.IO.Path]::GetPathRoot($programs).Substring(0, 1)
$drive = Get-PSDrive -Name $driveName
$requiredBytes = [int64]((Get-Item -LiteralPath $zip).Length * 3)
if ($requiredBytes -lt 3221225472) {{
  $requiredBytes = 3221225472
}}
if ($drive.Free -lt $requiredBytes) {{
  $freeGb = [math]::Round($drive.Free / 1GB, 2)
  $needGb = [math]::Round($requiredBytes / 1GB, 2)
  throw "磁盘空间不足：当前 $driveName 盘剩余 $freeGb GB，至少需要 $needGb GB。请清理空间后重新安装。"
}}
Expand-Archive -LiteralPath $zip -DestinationPath $programs -Force
$newDesktopDir = Join-Path $installDir 'resources\storage\desktop'
New-Item -ItemType Directory -Path $newDesktopDir -Force | Out-Null
$preservedCommercialDir = Join-Path $preserveRoot 'commercial'
$preservedSettingsFile = Join-Path $preserveRoot 'desktop_settings.json'
if (Test-Path $preservedCommercialDir) {{
  $newCommercialDir = Join-Path $newDesktopDir 'commercial'
  if (Test-Path $newCommercialDir) {{
    Remove-Item -LiteralPath $newCommercialDir -Recurse -Force
  }}
  Copy-Item -LiteralPath $preservedCommercialDir -Destination $newCommercialDir -Recurse -Force
}}
if (Test-Path $preservedSettingsFile) {{
  Copy-Item -LiteralPath $preservedSettingsFile -Destination (Join-Path $newDesktopDir 'desktop_settings.json') -Force
}}
Remove-Item -LiteralPath $preserveRoot -Recurse -Force -ErrorAction SilentlyContinue
$exe = Join-Path $installDir 'Aivo 数字人口播工作台.exe'
if (!(Test-Path $exe)) {{ throw '安装失败：未找到主程序。' }}
$desktop = [Environment]::GetFolderPath('Desktop')
$shortcutPath = Join-Path $desktop ($product + '.lnk')
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $exe
$shortcut.WorkingDirectory = $installDir
$shortcut.Description = $product
$shortcut.Save()
Write-Host "安装完成：$installDir"
Write-Host "桌面快捷方式：$shortcutPath"
"""


def _zip_dir(source_dir: Path, zip_path: Path) -> None:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(source_dir.parent).as_posix())


def _find_sensitive_values(data: Any, prefix: str = "", *, allowed_keys: set[str] | None = None) -> set[str]:
    allowed_keys = allowed_keys or set()
    leaked: set[str] = set()
    if isinstance(data, dict):
        for key, value in data.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if _is_sensitive_key(str(key)) and key not in allowed_keys and value not in ("", None, False):
                leaked.add(path)
            leaked.update(_find_sensitive_values(value, path, allowed_keys=allowed_keys))
    elif isinstance(data, list):
        for index, item in enumerate(data):
            leaked.update(_find_sensitive_values(item, f"{prefix}[{index}]", allowed_keys=allowed_keys))
    return leaked


def _is_sensitive_key(key: str) -> bool:
    lower = key.lower()
    return any(part in lower for part in SENSITIVE_KEY_PARTS)


def main() -> int:
    parser = argparse.ArgumentParser(description="构建可交付客户桌面包")
    parser.add_argument("--source", default=r"G:\dist\desktop-cloud-providers-v2\win-unpacked")
    parser.add_argument("--output-dir", default=str(Path.home() / "Desktop"))
    parser.add_argument("--backend-dir", default="")
    parser.add_argument("--ffmpeg-exe", default="")
    parser.add_argument("--ytdlp-exe", default="")
    parser.add_argument(
        "--include-test-api-keys",
        action="store_true",
        help="include allowlisted test API keys for customer trial packages",
    )
    parser.add_argument("--product", default="数字人智能体")
    args = parser.parse_args()
    package_dir = build_customer_package(
        source=args.source,
        output_dir=args.output_dir,
        backend_dir=args.backend_dir or None,
        ffmpeg_exe=args.ffmpeg_exe or None,
        ytdlp_exe=args.ytdlp_exe or None,
        product=args.product,
        include_test_api_keys=args.include_test_api_keys,
    )
    print(f"customer_package={package_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
