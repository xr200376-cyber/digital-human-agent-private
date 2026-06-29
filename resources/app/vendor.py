"""Helpers for optional vendored third-party source trees.

The project can run in two modes:
1. adapter mode: call external tools through HTTP/CLI/Docker services;
2. vendored-source mode: copy approved open-source repositories into ./third_party
   and let adapters resolve CLI scripts or Python packages from there.

This module intentionally does not import third-party code at module import time.
Adapters should call these helpers lazily so dry-run and test environments stay light.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from app.settings import get_settings


@dataclass(frozen=True)
class VendorProject:
    key: str
    dirname: str
    env_var: str
    license_name: str


VENDOR_PROJECTS: dict[str, VendorProject] = {
    "pixelle-video": VendorProject("pixelle-video", "Pixelle-Video", "PIXELLE_SOURCE_DIR", "Apache-2.0"),
    "pyjianyingdraft": VendorProject("pyjianyingdraft", "pyJianYingDraft", "PYJIANYINGDRAFT_SOURCE_DIR", "Apache-2.0"),
    "latentsync": VendorProject("latentsync", "LatentSync", "LATENTSYNC_SOURCE_DIR", "Apache-2.0"),
    "musetalk": VendorProject("musetalk", "MuseTalk", "MUSETALK_SOURCE_DIR", "MIT"),
    "langgraph": VendorProject("langgraph", "langgraph", "LANGGRAPH_SOURCE_DIR", "MIT"),
    "mcp": VendorProject("mcp", "modelcontextprotocol", "MCP_SOURCE_DIR", "MIT/Apache-2.0 transition"),
    "duix-avatar": VendorProject("duix-avatar", "Duix-Avatar", "DUIX_SOURCE_DIR", "DUIX.COM Community License"),
}


def third_party_root() -> Path:
    settings = get_settings()
    return Path(os.getenv("THIRD_PARTY_ROOT", str(settings.third_party_dir))).resolve()


def vendor_project_path(project_key: str, *, required: bool = False) -> Path | None:
    """Return the vendored source path for a project, or None if missing.

    `project_key` must be one of VENDOR_PROJECTS. Environment variables such as
    PIXELLE_SOURCE_DIR can override the default third_party/<dirname> location.
    """

    if project_key not in VENDOR_PROJECTS:
        raise KeyError(f"Unknown vendor project: {project_key}")
    project = VENDOR_PROJECTS[project_key]
    configured = os.getenv(project.env_var)
    path = Path(configured).expanduser().resolve() if configured else third_party_root() / project.dirname
    if path.exists():
        return path
    if required:
        raise FileNotFoundError(
            f"Vendored source for {project_key!r} not found at {path}. "
            f"Run scripts/vendor_sources.py or set {project.env_var}."
        )
    return None


def add_vendor_to_syspath(project_key: str, subdir: str | None = None, *, required: bool = False) -> Path | None:
    """Add a vendored project or subdirectory to sys.path lazily.

    Returns the path that was added, or None if the source tree is not available.
    """

    root = vendor_project_path(project_key, required=required)
    if root is None:
        return None
    path = root / subdir if subdir else root
    if required and not path.exists():
        raise FileNotFoundError(f"Expected vendored path does not exist: {path}")
    if path.exists() and str(path) not in sys.path:
        sys.path.insert(0, str(path))
    return path if path.exists() else None
