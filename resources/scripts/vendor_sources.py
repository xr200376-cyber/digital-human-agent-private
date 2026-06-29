#!/usr/bin/env python3
"""Vendor approved open-source project source trees into ./third_party.

This script is intended to be run by a developer or Codex on a machine with Git
and internet access. It clones approved upstream repositories, removes VCS/cache/
model/data artifacts, copies source into third_party/<project>, and records a
manifest with commit hashes and license files.

Examples:
  python scripts/vendor_sources.py --projects pixelle-video pyjianyingdraft latentsync musetalk
  python scripts/vendor_sources.py --include-frameworks
  python scripts/vendor_sources.py --include-conditional --projects duix-avatar
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class RepoSpec:
    key: str
    url: str
    target_dirname: str
    license_name: str
    status: str
    default: bool
    conditional: bool = False
    optional_framework: bool = False
    ref: str | None = None
    exclude_patterns: tuple[str, ...] = ()


COMMON_EXCLUDES = (
    ".git",
    ".github/workflows",
    "__pycache__",
    "*.pyc",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "dist",
    "build",
    "*.egg-info",
    "outputs",
    "output",
    "results",
    "result",
    "runs",
    "logs",
    "tmp",
    "temp",
    "cache",
    ".cache",
    "*.mp4",
    "*.mov",
    "*.avi",
    "*.mkv",
    "*.wav",
    "*.mp3",
    "*.flac",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.webp",
    "*.gif",
    "*.zip",
    "*.7z",
    "*.tar",
    "*.tar.gz",
    "*.rar",
)

MODEL_AND_DATA_EXCLUDES = (
    "checkpoints",
    "checkpoint",
    "weights",
    "weight",
    "models",
    "pretrained",
    "pretrained_models",
    "modelscope",
    "huggingface",
    "hf_cache",
    "*.ckpt",
    "*.pth",
    "*.pt",
    "*.safetensors",
    "*.onnx",
    "*.engine",
    "*.bin",
    "*.pkl",
    "*.pickle",
    "*.npy",
    "*.npz",
    "datasets",
    "dataset",
    "testdata",
    "test_data",
    "demo_data",
    "sample_data",
    "samples",
)

REPOS: dict[str, RepoSpec] = {
    "pixelle-video": RepoSpec(
        key="pixelle-video",
        url="https://github.com/AIDC-AI/Pixelle-Video.git",
        target_dirname="Pixelle-Video",
        license_name="Apache-2.0",
        status="approved_to_vendor",
        default=True,
        exclude_patterns=COMMON_EXCLUDES + MODEL_AND_DATA_EXCLUDES,
    ),
    "pyjianyingdraft": RepoSpec(
        key="pyjianyingdraft",
        url="https://github.com/GuanYixuan/pyJianYingDraft.git",
        target_dirname="pyJianYingDraft",
        license_name="Apache-2.0",
        status="approved_to_vendor",
        default=True,
        exclude_patterns=COMMON_EXCLUDES + ("readme_assets",),
    ),
    "latentsync": RepoSpec(
        key="latentsync",
        url="https://github.com/bytedance/LatentSync.git",
        target_dirname="LatentSync",
        license_name="Apache-2.0 code; model weights separate",
        status="approved_to_vendor_source_only",
        default=True,
        exclude_patterns=COMMON_EXCLUDES + MODEL_AND_DATA_EXCLUDES,
    ),
    "musetalk": RepoSpec(
        key="musetalk",
        url="https://github.com/TMElyralab/MuseTalk.git",
        target_dirname="MuseTalk",
        license_name="MIT code; testdata non-commercial only",
        status="approved_to_vendor_source_only",
        default=True,
        exclude_patterns=COMMON_EXCLUDES + MODEL_AND_DATA_EXCLUDES + ("testdata", "data/audio", "data/video"),
    ),
    "langgraph": RepoSpec(
        key="langgraph",
        url="https://github.com/langchain-ai/langgraph.git",
        target_dirname="langgraph",
        license_name="MIT",
        status="optional_dependency_preferred",
        default=False,
        optional_framework=True,
        exclude_patterns=COMMON_EXCLUDES + MODEL_AND_DATA_EXCLUDES,
    ),
    "mcp": RepoSpec(
        key="mcp",
        url="https://github.com/modelcontextprotocol/modelcontextprotocol.git",
        target_dirname="modelcontextprotocol",
        license_name="MIT/Apache-2.0 transition; docs may be CC-BY-4.0",
        status="optional_dependency_preferred",
        default=False,
        optional_framework=True,
        exclude_patterns=COMMON_EXCLUDES + MODEL_AND_DATA_EXCLUDES,
    ),
    "duix-avatar": RepoSpec(
        key="duix-avatar",
        url="https://github.com/duixcom/Duix-Avatar.git",
        target_dirname="Duix-Avatar",
        license_name="DUIX.COM Community License",
        status="conditional_vendor_only",
        default=False,
        conditional=True,
        exclude_patterns=COMMON_EXCLUDES + MODEL_AND_DATA_EXCLUDES,
    ),
}


def run(cmd: list[str], cwd: Path | None = None) -> str:
    proc = subprocess.run(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")
    return proc.stdout.strip()


def github_repo_slug(repo_url: str) -> tuple[str, str]:
    parsed = urlparse(repo_url)
    if parsed.netloc.lower() != "github.com":
        raise ValueError(f"Archive fallback only supports GitHub repositories: {repo_url}")
    parts = parsed.path.strip("/").split("/")
    if len(parts) < 2:
        raise ValueError(f"Cannot parse GitHub owner/repo from URL: {repo_url}")
    owner = parts[0]
    repo = parts[1]
    if repo.endswith(".git"):
        repo = repo[:-4]
    return owner, repo


def download_github_archive(spec: RepoSpec, archive_dst: Path) -> str:
    owner, repo = github_repo_slug(spec.url)
    ref = spec.ref or "HEAD"
    archive_url = f"https://api.github.com/repos/{owner}/{repo}/zipball/{ref}"
    request = Request(archive_url, headers={"User-Agent": "aivo-source-vendor/1.0"})
    with urlopen(request, timeout=120) as response, archive_dst.open("wb") as output:
        shutil.copyfileobj(response, output)
    return ref


def _assert_safe_zip_member(member_name: str) -> None:
    member_path = Path(member_name)
    if member_path.is_absolute() or ".." in member_path.parts:
        raise ValueError(f"Unsafe path in downloaded archive: {member_name}")


def extract_github_archive(archive_path: Path, extract_dir: Path) -> Path:
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.namelist():
            _assert_safe_zip_member(member)
        archive.extractall(extract_dir)
    roots = [path for path in extract_dir.iterdir() if path.is_dir()]
    if len(roots) != 1:
        raise RuntimeError(f"Expected one top-level directory in archive, found {len(roots)}")
    return roots[0]


def archive_commit_hint(repo_dir: Path, fallback: str) -> str:
    candidate = repo_dir.name.rsplit("-", 1)[-1]
    if len(candidate) >= 7 and all(ch in "0123456789abcdefABCDEF" for ch in candidate):
        return candidate
    return fallback


def should_exclude(rel_path: Path, patterns: Iterable[str]) -> bool:
    rel = rel_path.as_posix()
    name = rel_path.name
    for pattern in patterns:
        if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(name, pattern):
            return True
        # Directory pattern should also exclude nested contents.
        if rel == pattern or rel.startswith(pattern.rstrip("/") + "/"):
            return True
    return False


def copy_filtered(src: Path, dst: Path, patterns: Iterable[str]) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.rglob("*"):
        rel = item.relative_to(src)
        if should_exclude(rel, patterns):
            if item.is_dir():
                # rglob will still see children, each child is excluded by prefix.
                pass
            continue
        target = dst / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)


def find_license_files(repo_dir: Path) -> list[Path]:
    candidates: list[Path] = []
    for path in repo_dir.iterdir():
        if path.is_file() and path.name.lower().startswith(("license", "notice", "copying", "authors")):
            candidates.append(path)
    return candidates


def clone_and_vendor(spec: RepoSpec, root: Path, *, keep_git: bool, force: bool, dry_run: bool) -> dict[str, str]:
    target = root / spec.target_dirname
    license_target = root / "_licenses" / spec.target_dirname

    print(f"\n==> Vendoring {spec.key}: {spec.url}")
    if dry_run:
        return {
            "key": spec.key,
            "url": spec.url,
            "target": str(target),
            "license": spec.license_name,
            "status": "dry-run",
        }
    if target.exists() and not force:
        raise FileExistsError(f"Target already exists: {target}. Use --force to replace it.")

    with tempfile.TemporaryDirectory(prefix=f"vendor-{spec.key}-") as tmp_str:
        tmp = Path(tmp_str)
        clone_dir = tmp / spec.target_dirname
        source = "git"
        if shutil.which("git"):
            cmd = ["git", "clone", "--depth", "1"]
            if spec.ref:
                cmd += ["--branch", spec.ref]
            cmd += [spec.url, str(clone_dir)]
            run(cmd)
            commit = run(["git", "rev-parse", "HEAD"], cwd=clone_dir)
        else:
            source = "github-zipball"
            archive_path = tmp / f"{spec.target_dirname}.zip"
            commit = download_github_archive(spec, archive_path)
            clone_dir = extract_github_archive(archive_path, tmp / "archive")
            commit = archive_commit_hint(clone_dir, commit)

        patterns = spec.exclude_patterns
        if not keep_git:
            patterns = tuple(patterns) + (".git",)

        if target.exists():
            shutil.rmtree(target)
        copy_filtered(clone_dir, target, patterns)

        license_files = find_license_files(clone_dir)
        if license_target.exists():
            shutil.rmtree(license_target)
        license_target.mkdir(parents=True, exist_ok=True)
        for lic in license_files:
            shutil.copy2(lic, license_target / lic.name)
        if not license_files:
            print(f"WARNING: no root license/notice file found for {spec.key}; inspect manually.", file=sys.stderr)

        return {
            "key": spec.key,
            "url": spec.url,
            "target": str(target),
            "commit": commit,
            "source": source,
            "license": spec.license_name,
            "license_files": [str(license_target / lic.name) for lic in license_files],
            "status": spec.status,
        }


def select_projects(args: argparse.Namespace) -> list[RepoSpec]:
    if args.projects:
        keys = args.projects
    else:
        keys = [k for k, spec in REPOS.items() if spec.default]
        if args.include_frameworks:
            keys += [k for k, spec in REPOS.items() if spec.optional_framework]
    unknown = [k for k in keys if k not in REPOS]
    if unknown:
        raise KeyError(f"Unknown project(s): {unknown}. Known: {sorted(REPOS)}")
    specs = [REPOS[k] for k in keys]
    blocked = [s.key for s in specs if s.conditional and not args.include_conditional]
    if blocked:
        raise PermissionError(
            "Conditional-license project(s) requested without --include-conditional: "
            + ", ".join(blocked)
            + ". Review license terms first."
        )
    return specs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="third_party", help="Target third_party root directory")
    parser.add_argument("--projects", nargs="*", help="Project keys to vendor. Defaults to approved core projects.")
    parser.add_argument("--include-frameworks", action="store_true", help="Also vendor optional framework source: langgraph and MCP spec/docs.")
    parser.add_argument("--include-conditional", action="store_true", help="Allow conditional-license projects such as Duix-Avatar.")
    parser.add_argument("--keep-git", action="store_true", help="Keep .git directories in vendored copies.")
    parser.add_argument("--force", action="store_true", help="Replace existing target directories.")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without cloning/copying.")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    (root / "_licenses").mkdir(parents=True, exist_ok=True)

    specs = select_projects(args)
    manifest: dict[str, object] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root": str(root),
        "projects": [],
    }
    for spec in specs:
        result = clone_and_vendor(spec, root, keep_git=args.keep_git, force=args.force, dry_run=args.dry_run)
        manifest["projects"].append(result)

    manifest_name = "THIRD_PARTY_MANIFEST.dry-run.json" if args.dry_run else "THIRD_PARTY_MANIFEST.generated.json"
    manifest_path = root / manifest_name
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
