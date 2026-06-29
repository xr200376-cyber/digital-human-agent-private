"""
腾讯云 COS 文件上传服务。

上传本地文件到 COS Bucket，返回预签名临时 URL，供百度云等第三方平台下载。
Bucket 无需设为公开读，URL 默认 2 小时有效。

环境变量：
  COS_SECRET_ID    腾讯云 SecretId
  COS_SECRET_KEY   腾讯云 SecretKey
  COS_BUCKET       存储桶名称，例如 dev-mln-1300628430
  COS_REGION       地域，例如 ap-beijing
"""

from __future__ import annotations

import os
from pathlib import Path


def _get_client():
    try:
        from qcloud_cos import CosConfig, CosS3Client
    except ImportError as e:
        raise RuntimeError(
            "使用腾讯云 COS 需要先安装 SDK：uv sync"
        ) from e

    secret_id  = os.getenv("COS_SECRET_ID", "").strip()
    secret_key = os.getenv("COS_SECRET_KEY", "").strip()
    region     = os.getenv("COS_REGION", "").strip()
    if not (secret_id and secret_key and region):
        raise EnvironmentError(
            "请在 .env 中设置 COS_SECRET_ID / COS_SECRET_KEY / COS_REGION"
        )
    config = CosConfig(Region=region, SecretId=secret_id, SecretKey=secret_key)
    return CosS3Client(config)


def _bucket() -> str:
    bucket = os.getenv("COS_BUCKET", "").strip()
    if not bucket:
        raise EnvironmentError("请在 .env 中设置 COS_BUCKET")
    return bucket


def upload_file(local_path: Path, key: str, signed_expiry: int = 7200) -> str:
    """
    上传本地文件到 COS，返回带签名的临时访问 URL（预签名 URL）。

    Bucket 无需设为公开，URL 在 signed_expiry 秒内有效（默认 2 小时）。
    百度云会在提交任务后立即下载文件，2 小时内足够完成生成。

    :param local_path:    本地文件路径
    :param key:           COS 对象键，例如 digital-human/session-id/audio.mp3
    :param signed_expiry: URL 有效期（秒），默认 7200（2 小时）
    :returns:             带签名的临时 URL
    """
    if not local_path.exists():
        raise FileNotFoundError(f"文件不存在：{local_path}")

    client = _get_client()
    bucket = _bucket()

    client.upload_file(
        Bucket=bucket,
        Key=key,
        LocalFilePath=str(local_path),
    )

    # 生成预签名临时下载 URL，Bucket 无需公开读
    url = client.get_presigned_download_url(
        Bucket=bucket,
        Key=key,
        Expired=signed_expiry,
    )
    return url
