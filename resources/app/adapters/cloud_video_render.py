from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

import httpx

from app.adapters.base import AdapterError
from app.cloud_providers import FAL_LATENTSYNC_USD_PER_SECOND, FAL_MUSETALK_USD_PER_SECOND
from app.utils.files import ensure_dir, write_json, write_placeholder_binary, write_text


class BaseCloudVideoRenderAdapter:
    name = "cloud_video_render"

    async def render_lipsync(self, *, video_url: str, audio_url: str, out_dir: Path) -> Path:
        raise NotImplementedError

    async def get_job_status(self, *, job_id: str) -> dict[str, Any]:
        raise NotImplementedError

    async def download_result(self, *, result_url: str, output_path: Path) -> Path:
        raise NotImplementedError

    def estimate_cost(self, duration_seconds: int | float) -> float:
        raise NotImplementedError


class FalVideoRenderAdapter(BaseCloudVideoRenderAdapter):
    name = "fal"

    def __init__(
        self,
        *,
        provider_id: str = "fal_latentsync",
        dry_run: bool = True,
        enabled: bool = False,
        api_key: str | None = None,
        latentsync_model: str = "fal-ai/latentsync",
        musetalk_model: str = "fal-ai/musetalk",
        timeout_seconds: float = 1200.0,
    ):
        self.provider_id = provider_id
        self.dry_run = dry_run
        self.enabled = enabled
        self.api_key = api_key or os.getenv("FAL_API_KEY", "")
        self.latentsync_model = latentsync_model or os.getenv("FAL_LATENTSYNC_MODEL", "fal-ai/latentsync")
        self.musetalk_model = musetalk_model or os.getenv("FAL_MUSETALK_MODEL", "fal-ai/musetalk")
        self.timeout_seconds = timeout_seconds
        self.base_url = "https://fal.run"

    @property
    def model(self) -> str:
        return self.musetalk_model if self.provider_id == "fal_musetalk" else self.latentsync_model

    def available(self) -> bool:
        if self.dry_run:
            return True
        return bool(self.enabled and self.api_key and self.model)

    def readiness(self) -> dict[str, Any]:
        blocking_items: list[str] = []
        if not self.dry_run and not self.enabled:
            blocking_items.append("CLOUD_VIDEO_PROVIDER")
        if not self.dry_run and not self.api_key:
            blocking_items.append("FAL_API_KEY")
        if not self.model:
            blocking_items.append("FAL_LATENTSYNC_MODEL" if self.provider_id == "fal_latentsync" else "FAL_MUSETALK_MODEL")
        return {
            "provider": self.provider_id,
            "ready": not blocking_items or self.dry_run,
            "enabled": self.enabled,
            "dry_run": self.dry_run,
            "base_url": self.base_url,
            "model": self.model,
            "api_key_configured": bool(self.api_key),
            "blocking_items": blocking_items,
        }

    def require_available(self) -> None:
        if self.available():
            return
        blockers = "、".join(self.readiness()["blocking_items"])
        raise AdapterError(f"fal.ai 云端口型同步不可用：{blockers}")

    def estimate_cost(self, duration_seconds: int | float) -> float:
        seconds = max(0.0, float(duration_seconds))
        rate = FAL_MUSETALK_USD_PER_SECOND if self.provider_id == "fal_musetalk" else FAL_LATENTSYNC_USD_PER_SECOND
        return round(seconds * rate + 1e-9, 2)

    async def render_lipsync(self, *, video_url: str, audio_url: str, out_dir: Path) -> Path:
        ensure_dir(out_dir)
        output_path = out_dir / "lip_synced.mp4"
        response_log = out_dir / "fal_lipsync_response.json"
        http_log = out_dir / "fal_lipsync_http.log"

        if self.dry_run:
            request_log = write_json(
                out_dir / "fal_lipsync_request.json",
                {
                    "provider": self.provider_id,
                    "base_url": self.base_url,
                    "model": self.model,
                    "video_url": video_url,
                    "audio_url": audio_url,
                    "resolved_video_url": video_url,
                    "resolved_audio_url": audio_url,
                    "dry_run": self.dry_run,
                },
            )
            write_json(
                response_log,
                {
                    "status": "completed",
                    "provider": self.provider_id,
                    "output_url": str(output_path),
                    "request_log": str(request_log),
                    "dry_run": True,
                },
            )
            write_text(http_log, "dry-run: fal.ai call skipped; placeholder media generated.\n")
            return write_placeholder_binary(output_path, f"fal={self.provider_id};video={video_url};audio={audio_url}")

        self.require_available()
        resolved_video_url = await self._ensure_fal_accessible_url(value=video_url, out_dir=out_dir, kind="video")
        resolved_audio_url = await self._ensure_fal_accessible_url(value=audio_url, out_dir=out_dir, kind="audio")
        write_json(
            out_dir / "fal_lipsync_request.json",
            {
                "provider": self.provider_id,
                "base_url": self.base_url,
                "model": self.model,
                "video_url": video_url,
                "audio_url": audio_url,
                "resolved_video_url": resolved_video_url,
                "resolved_audio_url": resolved_audio_url,
                "dry_run": self.dry_run,
            },
        )

        try:
            data = await self._invoke_model(
                arguments={"video_url": resolved_video_url, "audio_url": resolved_audio_url},
                response_log=response_log,
            )
            result_url = _extract_result_url(data)
            if not result_url:
                raise AdapterError(f"fal.ai 响应缺少结果视频地址：{data}")
            return await self.download_result(result_url=result_url, output_path=output_path)
        except AdapterError:
            raise
        except Exception as exc:  # noqa: BLE001 - cloud failure should surface in task step.
            write_text(http_log, f"fal.ai 请求失败：{exc}\n")
            raise AdapterError(f"fal.ai 请求失败：{exc}") from exc

    async def _ensure_fal_accessible_url(self, *, value: str, out_dir: Path, kind: str) -> str:
        if _is_public_url(value):
            return str(value)
        path = Path(value)
        if not path.exists():
            raise AdapterError(f"fal.ai 云端渲染找不到本地{kind}文件：{value}")
        return await self.upload_file_to_url(file_path=path, out_dir=out_dir, kind=kind)

    async def upload_file_to_url(self, *, file_path: Path, out_dir: Path, kind: str) -> str:
        self.require_available()
        if not file_path.exists():
            raise AdapterError(f"fal.ai 上传失败，本地{kind}文件不存在：{file_path}")
        if file_path.stat().st_size <= 0:
            raise AdapterError(f"fal.ai 上传失败，本地{kind}文件为空：{file_path}")
        try:
            uploaded_url = await asyncio.to_thread(_fal_upload_file, file_path, self.api_key)
        except ModuleNotFoundError as exc:
            raise AdapterError("fal.ai 上传需要安装 fal-client：请运行 python -m pip install fal-client") from exc
        except Exception as exc:  # noqa: BLE001 - surface provider upload errors to task steps.
            raise AdapterError(f"fal.ai 上传{kind}文件失败：{exc}") from exc
        write_json(
            out_dir / f"fal_upload_{kind}.json",
            {
                "provider": self.provider_id,
                "kind": kind,
                "source_path": str(file_path),
                "uploaded_url": uploaded_url,
            },
        )
        return uploaded_url

    async def _invoke_model(self, *, arguments: dict[str, object], response_log: Path) -> dict[str, object]:
        async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True) as client:
            response = await client.post(
                f"{self.base_url}/{self.model}",
                headers={"Authorization": f"Key {self.api_key}"},
                json=arguments,
            )
            write_json(response_log, _safe_response_json(response))
            if response.status_code >= 400:
                raise AdapterError(f"fal.ai 请求失败：HTTP {response.status_code}")
            return response.json()

    async def _render_lipsync_without_upload(self, *, video_url: str, audio_url: str, out_dir: Path) -> Path:
        ensure_dir(out_dir)
        output_path = out_dir / "lip_synced.mp4"
        request_log = write_json(
            out_dir / "fal_lipsync_request.json",
            {
                "provider": self.provider_id,
                "base_url": self.base_url,
                "model": self.model,
                "video_url": video_url,
                "audio_url": audio_url,
                "dry_run": self.dry_run,
            },
        )
        response_log = out_dir / "fal_lipsync_response.json"
        http_log = out_dir / "fal_lipsync_http.log"

        if self.dry_run:
            write_json(
                response_log,
                {
                    "status": "completed",
                    "provider": self.provider_id,
                    "output_url": str(output_path),
                    "request_log": str(request_log),
                    "dry_run": True,
                },
            )
            write_text(http_log, "dry-run: fal.ai call skipped; placeholder media generated.\n")
            return write_placeholder_binary(output_path, f"fal={self.provider_id};video={video_url};audio={audio_url}")

        self.require_available()
        if not (_is_public_url(video_url) and _is_public_url(audio_url)):
            raise AdapterError("fal.ai 云端渲染需要公网可访问的 video_url 和 audio_url；本地文件请走自建服务或本地模型回退。")

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True) as client:
                response = await client.post(
                    f"{self.base_url}/{self.model}",
                    headers={"Authorization": f"Key {self.api_key}"},
                    json={"video_url": video_url, "audio_url": audio_url},
                )
                write_json(response_log, _safe_response_json(response))
                if response.status_code >= 400:
                    raise AdapterError(f"fal.ai 请求失败：HTTP {response.status_code}")
                data = response.json()
                result_url = _extract_result_url(data)
                if not result_url:
                    raise AdapterError(f"fal.ai 响应缺少结果视频地址：{data}")
                return await self.download_result(result_url=result_url, output_path=output_path)
        except AdapterError:
            raise
        except Exception as exc:  # noqa: BLE001 - cloud failure should surface in task step.
            write_text(http_log, f"fal.ai 请求失败：{exc}\n")
            raise AdapterError(f"fal.ai 请求失败：{exc}") from exc

    async def get_job_status(self, *, job_id: str) -> dict[str, Any]:
        if self.dry_run:
            return {"provider": self.provider_id, "job_id": job_id, "status": "completed", "dry_run": True}
        self.require_available()
        return {"provider": self.provider_id, "job_id": job_id, "status": "unknown", "message": "如使用 fal queue，请在此处映射状态接口。"}

    async def download_result(self, *, result_url: str, output_path: Path) -> Path:
        ensure_dir(output_path.parent)
        if self.dry_run:
            return write_placeholder_binary(output_path, f"fal-result={result_url}")
        self.require_available()
        async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True) as client:
            response = await client.get(result_url)
            response.raise_for_status()
            output_path.write_bytes(response.content)
        return output_path


def _is_public_url(value: str) -> bool:
    lowered = str(value or "").strip().lower()
    return lowered.startswith("https://") or lowered.startswith("http://")


def _fal_upload_file(file_path: Path, api_key: str) -> str:
    old_fal_key = os.environ.get("FAL_KEY")
    try:
        os.environ["FAL_KEY"] = api_key
        import fal_client

        return str(fal_client.upload_file(str(file_path), repository="cdn", fallback_repository=[]))
    finally:
        if old_fal_key is None:
            os.environ.pop("FAL_KEY", None)
        else:
            os.environ["FAL_KEY"] = old_fal_key


def _extract_result_url(data: dict[str, Any]) -> str:
    for key in ("video_url", "output_url", "download_url", "url"):
        value = data.get(key)
        if value:
            return str(value)
    output = data.get("output")
    if isinstance(output, dict):
        for key in ("video_url", "output_url", "download_url", "url"):
            value = output.get(key)
            if value:
                return str(value)
    return ""


def _safe_response_json(response: httpx.Response) -> dict[str, Any]:
    try:
        return response.json()
    except Exception:
        return {"status_code": response.status_code, "text": response.text[:2000]}
