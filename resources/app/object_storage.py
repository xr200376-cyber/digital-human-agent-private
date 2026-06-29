from __future__ import annotations

import shutil
from pathlib import Path
from typing import Protocol, runtime_checkable

from app.utils.files import ensure_dir


@runtime_checkable
class ObjectStorage(Protocol):
    def put_file(self, key: str, source: Path) -> Path:
        ...

    def get_file(self, key: str) -> Path:
        ...

    def exists(self, key: str) -> bool:
        ...

    def list_keys(self, prefix: str = "") -> list[str]:
        ...

    def readiness(self) -> dict[str, object]:
        ...


class LocalObjectStorage:
    """Local filesystem object storage used by the default MVP runtime."""

    def __init__(self, root: Path):
        self.root = ensure_dir(root)

    def put_file(self, key: str, source: Path) -> Path:
        source = Path(source)
        if not source.exists() or not source.is_file():
            raise FileNotFoundError(f"object source file not found: {source}")
        target = self._path_for_key(key)
        ensure_dir(target.parent)
        shutil.copy2(source, target)
        return target

    def get_file(self, key: str) -> Path:
        path = self._path_for_key(key)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"object not found: {key}")
        return path

    def exists(self, key: str) -> bool:
        return self._path_for_key(key).is_file()

    def list_keys(self, prefix: str = "") -> list[str]:
        prefix = self._normalize_key(prefix) if prefix else ""
        keys: list[str] = []
        for path in sorted(self.root.rglob("*")) if self.root.exists() else []:
            if path.is_file():
                key = path.relative_to(self.root).as_posix()
                if not prefix or key.startswith(prefix.rstrip("/") + "/") or key == prefix:
                    keys.append(key)
        return keys

    def readiness(self) -> dict[str, object]:
        return {
            "backend": "local",
            "ready": self.root.exists() and self.root.is_dir(),
            "root": str(self.root),
        }

    def _path_for_key(self, key: str) -> Path:
        return self.root / self._normalize_key(key)

    @staticmethod
    def _normalize_key(key: str) -> str:
        raw = str(key).replace("\\", "/").strip("/")
        if not raw:
            raise ValueError("object key cannot be empty")
        path = Path(raw)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"unsafe object key: {key}")
        return raw


class S3ObjectStorage:
    """S3/MinIO scaffold.

    This intentionally avoids a hard dependency on boto3 until deployment wiring
    is chosen. Readiness reports the configured target without claiming support.
    """

    def __init__(self, bucket: str | None, endpoint_url: str | None = None):
        self.bucket = bucket
        self.endpoint_url = endpoint_url

    def put_file(self, key: str, source: Path) -> Path:
        raise NotImplementedError("S3 object storage scaffold is not enabled in local mode")

    def get_file(self, key: str) -> Path:
        raise NotImplementedError("S3 object storage scaffold is not enabled in local mode")

    def exists(self, key: str) -> bool:
        return False

    def list_keys(self, prefix: str = "") -> list[str]:
        return []

    def readiness(self) -> dict[str, object]:
        return {
            "backend": "s3",
            "ready": False,
            "bucket": self.bucket,
            "endpoint_url": self.endpoint_url,
            "message": "S3/MinIO scaffold only; configure an implementation before enabling production mode.",
        }
