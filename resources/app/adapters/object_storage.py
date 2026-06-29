from __future__ import annotations

import importlib
import posixpath
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

from app.adapters.base import AdapterError
from app.settings import Settings
from app.utils.files import ensure_dir, write_json


ALIYUN_SIGNED_URL_EXPIRES_SECONDS = 7 * 24 * 60 * 60


@dataclass(frozen=True)
class ObjectStorageUploadResult:
    provider: str
    key: str
    public_url: str
    local_copy_path: str | None = None
    report_path: str | None = None


class BaseObjectStorageAdapter(Protocol):
    provider: str

    def upload_file(self, *, file_path: Path, key: str, report_dir: Path, report_name: str) -> ObjectStorageUploadResult:
        ...


class LocalPublicCopyObjectStorageAdapter:
    provider = "public_copy"

    def __init__(self, *, root: Path, public_base_url: str) -> None:
        self.root = root
        self.public_base_url = public_base_url.rstrip("/")

    def upload_file(self, *, file_path: Path, key: str, report_dir: Path, report_name: str) -> ObjectStorageUploadResult:
        _require_file(file_path)
        if not self.public_base_url:
            raise AdapterError("对象存储未配置公网访问地址：请填写 OBJECT_STORAGE_PUBLIC_BASE_URL。")
        normalized_key = _normalize_key(key)
        target = ensure_dir(self.root / Path(normalized_key).parent) / Path(normalized_key).name
        shutil.copyfile(file_path, target)
        result = ObjectStorageUploadResult(
            provider=self.provider,
            key=normalized_key,
            public_url=_public_url(self.public_base_url, normalized_key),
            local_copy_path=str(target),
        )
        return _write_upload_report(report_dir, report_name, file_path, result)


class AliyunOSSObjectStorageAdapter:
    provider = "aliyun_oss"

    def __init__(
        self,
        *,
        endpoint: str,
        bucket: str,
        access_key_id: str,
        access_key_secret: str,
        public_base_url: str,
    ) -> None:
        self.endpoint = endpoint
        self.bucket = bucket
        self.access_key_id = access_key_id
        self.access_key_secret = access_key_secret
        self.public_base_url = public_base_url.rstrip("/")

    def upload_file(self, *, file_path: Path, key: str, report_dir: Path, report_name: str) -> ObjectStorageUploadResult:
        _require_file(file_path)
        _require_nonempty("OBJECT_STORAGE_ENDPOINT", self.endpoint)
        _require_nonempty("OBJECT_STORAGE_BUCKET", self.bucket)
        _require_nonempty("OBJECT_STORAGE_ACCESS_KEY_ID", self.access_key_id)
        _require_nonempty("OBJECT_STORAGE_SECRET_ACCESS_KEY", self.access_key_secret)
        _require_nonempty("OBJECT_STORAGE_PUBLIC_BASE_URL", self.public_base_url)
        try:
            oss2 = importlib.import_module("oss2")
        except ModuleNotFoundError as exc:
            raise AdapterError("阿里云 OSS 自动上传需要安装 oss2：python -m pip install oss2") from exc
        normalized_key = _normalize_key(key)
        auth = oss2.Auth(self.access_key_id, self.access_key_secret)
        bucket = oss2.Bucket(auth, self.endpoint, self.bucket)
        bucket.put_object_from_file(normalized_key, str(file_path))
        result = ObjectStorageUploadResult(
            provider=self.provider,
            key=normalized_key,
            public_url=bucket.sign_url("GET", normalized_key, ALIYUN_SIGNED_URL_EXPIRES_SECONDS),
        )
        return _write_upload_report(report_dir, report_name, file_path, result)


class TencentCOSObjectStorageAdapter:
    provider = "tencent_cos"

    def __init__(
        self,
        *,
        region: str,
        bucket: str,
        secret_id: str,
        secret_key: str,
        public_base_url: str,
    ) -> None:
        self.region = region
        self.bucket = bucket
        self.secret_id = secret_id
        self.secret_key = secret_key
        self.public_base_url = public_base_url.rstrip("/")

    def upload_file(self, *, file_path: Path, key: str, report_dir: Path, report_name: str) -> ObjectStorageUploadResult:
        _require_file(file_path)
        _require_nonempty("OBJECT_STORAGE_REGION", self.region)
        _require_nonempty("OBJECT_STORAGE_BUCKET", self.bucket)
        _require_nonempty("OBJECT_STORAGE_ACCESS_KEY_ID", self.secret_id)
        _require_nonempty("OBJECT_STORAGE_SECRET_ACCESS_KEY", self.secret_key)
        _require_nonempty("OBJECT_STORAGE_PUBLIC_BASE_URL", self.public_base_url)
        try:
            cos_config = importlib.import_module("qcloud_cos").CosConfig
            cos_client = importlib.import_module("qcloud_cos").CosS3Client
        except ModuleNotFoundError as exc:
            raise AdapterError("腾讯云 COS 自动上传需要安装 cos-python-sdk-v5：python -m pip install cos-python-sdk-v5") from exc
        normalized_key = _normalize_key(key)
        config = cos_config(Region=self.region, SecretId=self.secret_id, SecretKey=self.secret_key, Scheme="https")
        client = cos_client(config)
        client.upload_file(Bucket=self.bucket, LocalFilePath=str(file_path), Key=normalized_key)
        result = ObjectStorageUploadResult(
            provider=self.provider,
            key=normalized_key,
            public_url=_public_url(self.public_base_url, normalized_key),
        )
        return _write_upload_report(report_dir, report_name, file_path, result)


class DisabledObjectStorageAdapter:
    provider = "disabled"

    def upload_file(self, *, file_path: Path, key: str, report_dir: Path, report_name: str) -> ObjectStorageUploadResult:
        raise AdapterError(
            "未配置对象存储自动上传。请在桌面设置中配置阿里云 OSS/腾讯云 COS，"
            "或手动把 clean_voice_sample.wav 上传后填写公网声音 URL。"
        )


def build_object_storage_adapter(settings: Settings) -> BaseObjectStorageAdapter:
    backend = (settings.object_storage_backend or "local").lower().strip()
    public_base_url = settings.object_storage_public_base_url or ""
    endpoint = settings.object_storage_endpoint or settings.s3_endpoint_url or ""
    bucket = settings.object_storage_bucket or settings.s3_bucket or ""
    access_key_id = settings.object_storage_access_key_id or settings.s3_access_key_id or ""
    secret_access_key = settings.object_storage_secret_access_key or settings.s3_secret_access_key or ""
    if backend in {"public_copy", "local_public", "public"}:
        return LocalPublicCopyObjectStorageAdapter(root=settings.object_storage_root, public_base_url=public_base_url)
    if backend in {"aliyun_oss", "oss", "aliyun"}:
        return AliyunOSSObjectStorageAdapter(
            endpoint=endpoint,
            bucket=bucket,
            access_key_id=access_key_id,
            access_key_secret=secret_access_key,
            public_base_url=public_base_url,
        )
    if backend in {"tencent_cos", "cos", "tencent"}:
        return TencentCOSObjectStorageAdapter(
            region=settings.object_storage_region or "",
            bucket=bucket,
            secret_id=access_key_id,
            secret_key=secret_access_key,
            public_base_url=public_base_url,
        )
    return DisabledObjectStorageAdapter()


def source_voice_sample_key(settings: Settings, *, project_id: str, digital_human_id: str) -> str:
    prefix = (settings.object_storage_prefix or "aivo").strip().strip("/")
    return posixpath.join(prefix, "projects", project_id, "digital_humans", digital_human_id, "source_video", "clean_voice_sample.wav")


def _write_upload_report(
    report_dir: Path,
    report_name: str,
    file_path: Path,
    result: ObjectStorageUploadResult,
) -> ObjectStorageUploadResult:
    ensure_dir(report_dir)
    report_path = write_json(
        report_dir / report_name,
        {
            "provider": result.provider,
            "source_path": str(file_path),
            "key": result.key,
            "public_url": result.public_url,
            "local_copy_path": result.local_copy_path,
        },
    )
    return ObjectStorageUploadResult(
        provider=result.provider,
        key=result.key,
        public_url=result.public_url,
        local_copy_path=result.local_copy_path,
        report_path=str(report_path),
    )


def _require_file(path: Path) -> None:
    if not path.exists():
        raise AdapterError(f"待上传文件不存在：{path}")
    if not path.is_file() or path.stat().st_size <= 0:
        raise AdapterError(f"待上传文件为空或不可读：{path}")


def _require_nonempty(name: str, value: str) -> None:
    if not str(value or "").strip():
        raise AdapterError(f"{name} 未配置，无法自动上传声音样本。")


def _normalize_key(value: str) -> str:
    parts = [part for part in str(value).replace("\\", "/").split("/") if part and part != "."]
    return "/".join(parts)


def _public_url(base_url: str, key: str) -> str:
    encoded = "/".join(quote(part, safe="") for part in _normalize_key(key).split("/"))
    return f"{base_url.rstrip('/')}/{encoded}"
