from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

from app.adapters.base import AdapterError
from app.utils.files import ensure_dir, write_json, write_placeholder_binary, write_text


HIFLY_DEFAULT_BASE_URL = "https://hfw-api.hifly.cc"

HIFLY_ENDPOINTS = {
    "avatar_create": "/api/v2/hifly/avatar/create_by_video",
    "avatar_list": "/api/v2/hifly/avatar/list",
    "avatar_task": "/api/v2/hifly/avatar/task",
    "voice_create": "/api/v2/hifly/voice/create",
    "voice_task": "/api/v2/hifly/voice/task",
    "video_audio": "/api/v2/hifly/video/create_by_audio",
    "video_tts": "/api/v2/hifly/video/create_by_tts",
    "video_task": "/api/v2/hifly/video/task",
}


class HiflyDigitalHumanAdapter:
    name = "hifly"

    def __init__(
        self,
        *,
        dry_run: bool = True,
        enabled: bool = False,
        base_url: str = HIFLY_DEFAULT_BASE_URL,
        token: str | None = None,
        required: bool = False,
        poll_interval_seconds: float = 5.0,
        timeout_seconds: float = 1800.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.dry_run = dry_run
        self.enabled = enabled
        self.base_url = (base_url or HIFLY_DEFAULT_BASE_URL).rstrip("/")
        self.token = token or ""
        self.required = required
        self.poll_interval_seconds = float(poll_interval_seconds or 5.0)
        self.timeout_seconds = float(timeout_seconds or 1800.0)
        self.transport = transport

    def endpoint(self, key: str) -> str:
        if key not in HIFLY_ENDPOINTS:
            raise KeyError(f"unknown Hifly endpoint: {key}")
        return f"{self.base_url}{HIFLY_ENDPOINTS[key]}"

    def validate_config(self) -> dict[str, Any]:
        blockers: list[str] = []
        if not self.dry_run and not self.enabled:
            blockers.append("HIFLY_ENABLED")
        if not self.dry_run and not self.token:
            blockers.append("HIFLY_TOKEN")
        if not self.base_url:
            blockers.append("HIFLY_BASE_URL")
        return {
            "provider": self.name,
            "ready": not blockers or self.dry_run,
            "enabled": self.enabled,
            "dry_run": self.dry_run,
            "base_url": self.base_url,
            "token_configured": bool(self.token),
            "blocking_items": blockers,
        }

    def require_available(self) -> None:
        readiness = self.validate_config()
        if readiness["ready"]:
            return
        raise AdapterError("Hifly is not available: " + ", ".join(readiness["blocking_items"]))

    async def probe_token(self) -> dict[str, Any]:
        readiness = self.validate_config()
        report: dict[str, Any] = {
            **readiness,
            "paid_call": False,
            "live_auth_checked": False,
            "auth_result": "skipped",
            "http_status": None,
            "body_excerpt": "",
        }
        if self.dry_run:
            report["auth_result"] = "dry-run: skipped live Hifly token check"
            return report
        if readiness["blocking_items"]:
            report["ready"] = False
            report["auth_result"] = "skipped: local Hifly config is incomplete"
            return report

        try:
            async with httpx.AsyncClient(
                timeout=min(self.timeout_seconds, 30.0),
                follow_redirects=True,
                transport=self.transport,
            ) as client:
                response = await client.get(
                    self.endpoint("avatar_list"),
                    headers=self._headers(),
                    params={"page": 1, "size": 1, "kind": 2},
                )
            data = _safe_response_json(response)
            body_excerpt = str(data)[:800]
            blockers = list(readiness["blocking_items"])
            if response.status_code in {401, 403}:
                blockers.append("HIFLY_TOKEN_UNAUTHORIZED")
                ready = False
                auth_result = "failed: Hifly rejected the token"
            elif response.status_code >= 400:
                blockers.append(f"HIFLY_TOKEN_PROBE_HTTP_{response.status_code}")
                ready = False
                auth_result = "failed: Hifly token probe returned an HTTP error"
            else:
                ready = True
                auth_result = "ok: Hifly token accepted by read-only probe"
            report.update(
                {
                    "ready": ready,
                    "live_auth_checked": True,
                    "auth_result": auth_result,
                    "http_status": response.status_code,
                    "body_excerpt": body_excerpt,
                    "blocking_items": blockers,
                }
            )
            return report
        except httpx.HTTPError as exc:
            report.update(
                {
                    "ready": False,
                    "live_auth_checked": True,
                    "auth_result": "failed: Hifly token probe request failed",
                    "blocking_items": [*readiness["blocking_items"], "HIFLY_TOKEN_PROBE_REQUEST_FAILED"],
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            return report

    async def create_avatar_by_video(
        self,
        *,
        video_url: str,
        title: str,
        out_dir: Path | None = None,
        confirm_paid_call: bool = False,
    ) -> dict[str, Any]:
        self._require_paid_confirmation(confirm_paid_call)
        payload = {"video_url": video_url, "title": title}
        return await self._post_json(
            endpoint_key="avatar_create",
            payload=payload,
            out_dir=out_dir,
            request_name="hifly_avatar_request.json",
            response_name="hifly_avatar_response.json",
            dry_run_response={
                "code": 0,
                "success": True,
                "data": {
                    "task_id": "dryrun_hifly_avatar_task",
                    "status": "done",
                    "avatar_id": "dryrun_hifly_avatar",
                },
            },
        )

    async def get_avatar_task(self, task_id: str) -> dict[str, Any]:
        return await self._get_json("avatar_task", {"task_id": task_id})

    async def create_voice(
        self,
        *,
        audio_url: str,
        title: str,
        voice_type: str | int = "clone",
        out_dir: Path | None = None,
        confirm_paid_call: bool = False,
    ) -> dict[str, Any]:
        self._require_paid_confirmation(confirm_paid_call)
        payload = {"audio_url": audio_url, "title": title, "voice_type": _normalize_voice_type(voice_type)}
        return await self._post_json(
            endpoint_key="voice_create",
            payload=payload,
            out_dir=out_dir,
            request_name="hifly_voice_request.json",
            response_name="hifly_voice_response.json",
            dry_run_response={
                "code": 0,
                "success": True,
                "data": {
                    "task_id": "dryrun_hifly_voice_task",
                    "status": "done",
                    "voice_id": "dryrun_hifly_voice",
                },
            },
        )

    async def get_voice_task(self, task_id: str) -> dict[str, Any]:
        return await self._get_json("voice_task", {"task_id": task_id})

    async def create_video_by_tts(
        self,
        *,
        text: str,
        avatar: str,
        voice: str,
        title: str,
        aigc_flag: int = 2,
        out_dir: Path | None = None,
        confirm_paid_call: bool = False,
    ) -> dict[str, Any]:
        self._require_paid_confirmation(confirm_paid_call)
        payload = {"text": text, "avatar": avatar, "voice": voice, "title": title, "aigc_flag": aigc_flag}
        return await self._post_json(
            endpoint_key="video_tts",
            payload=payload,
            out_dir=out_dir,
            request_name="hifly_video_request.json",
            response_name="hifly_video_response.json",
            dry_run_response={
                "code": 0,
                "success": True,
                "data": {
                    "task_id": "dryrun_hifly_video_task",
                    "status": "done",
                    "video_url": "dryrun://hifly/final.mp4",
                },
            },
        )

    async def create_video_by_audio(
        self,
        *,
        audio_url: str,
        avatar: str,
        title: str,
        aigc_flag: int = 2,
        out_dir: Path | None = None,
        confirm_paid_call: bool = False,
    ) -> dict[str, Any]:
        self._require_paid_confirmation(confirm_paid_call)
        payload = {"audio_url": audio_url, "avatar": avatar, "title": title, "aigc_flag": aigc_flag}
        return await self._post_json(
            endpoint_key="video_audio",
            payload=payload,
            out_dir=out_dir,
            request_name="hifly_video_request.json",
            response_name="hifly_video_response.json",
            dry_run_response={
                "code": 0,
                "success": True,
                "data": {
                    "task_id": "dryrun_hifly_video_task",
                    "status": "done",
                    "video_url": "dryrun://hifly/final.mp4",
                },
            },
        )

    async def get_video_task(self, task_id: str) -> dict[str, Any]:
        return await self._get_json("video_task", {"task_id": task_id})

    async def download_result(self, result_url: str, output_path: Path) -> Path:
        ensure_dir(output_path.parent)
        if self.dry_run or result_url.startswith("dryrun://"):
            return write_placeholder_binary(output_path, f"hifly-result={result_url}")
        self.require_available()
        async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True, transport=self.transport) as client:
            response = await client.get(result_url, headers=self._headers())
            response.raise_for_status()
            output_path.write_bytes(response.content)
        return output_path

    async def wait_for_task(self, task_id: str, task_type: str) -> dict[str, Any]:
        if self.dry_run:
            return {"code": 0, "success": True, "data": {"task_id": task_id, "status": "done"}}
        deadline = asyncio.get_running_loop().time() + self.timeout_seconds
        last: dict[str, Any] = {}
        while asyncio.get_running_loop().time() < deadline:
            if task_type == "avatar":
                data = await self.get_avatar_task(task_id)
            elif task_type == "voice":
                data = await self.get_voice_task(task_id)
            elif task_type == "video":
                data = await self.get_video_task(task_id)
            else:
                raise AdapterError(f"unknown Hifly task type: {task_type}")
            last = data
            status = _extract_status(data)
            if status in {"failed", "fail", "error"}:
                raise AdapterError(f"Hifly {task_type} task failed: {data}")
            if status in {"done", "success", "completed"} or _task_has_result(data, task_type):
                return data
            await asyncio.sleep(self.poll_interval_seconds)
        raise AdapterError(f"Hifly {task_type} task timed out: {task_id}; last={last}")

    async def _post_json(
        self,
        *,
        endpoint_key: str,
        payload: dict[str, Any],
        out_dir: Path | None,
        request_name: str,
        response_name: str,
        dry_run_response: dict[str, Any],
    ) -> dict[str, Any]:
        if out_dir:
            ensure_dir(out_dir)
            write_json(out_dir / request_name, {"provider": self.name, "endpoint": self.endpoint(endpoint_key), "payload": payload, "dry_run": self.dry_run})
        if self.dry_run:
            response = dry_run_response
            if out_dir:
                write_json(out_dir / response_name, response)
                write_text(out_dir / "hifly_http.log", "dry-run: Hifly call skipped.\n")
            return response
        self.require_available()
        async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True, transport=self.transport) as client:
            response = await client.post(self.endpoint(endpoint_key), headers=self._headers(), json=payload)
            data = _safe_response_json(response)
            if out_dir:
                write_json(out_dir / response_name, data)
            if response.status_code >= 400 or not _is_success(data):
                raise AdapterError(f"Hifly {endpoint_key} failed: HTTP {response.status_code}; {data}")
            return data

    async def _get_json(self, endpoint_key: str, params: dict[str, Any]) -> dict[str, Any]:
        if self.dry_run:
            return {"code": 0, "success": True, "data": {"task_id": params.get("task_id"), "status": "done"}}
        self.require_available()
        async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True, transport=self.transport) as client:
            response = await client.get(self.endpoint(endpoint_key), headers=self._headers(), params=params)
            data = _safe_response_json(response)
            if response.status_code >= 400 or not _is_success(data):
                raise AdapterError(f"Hifly {endpoint_key} failed: HTTP {response.status_code}; {data}")
            return data

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    def _require_paid_confirmation(self, confirm_paid_call: bool) -> None:
        if not self.dry_run and not confirm_paid_call:
            raise AdapterError("confirm_paid_call=true required before Hifly credit-consuming API call")


def extract_hifly_id(data: dict[str, Any], *names: str) -> str:
    values = [_payload(data), data]
    for payload in values:
        for name in names:
            value = payload.get(name)
            if value:
                return str(value)
    return ""


def _payload(data: dict[str, Any]) -> dict[str, Any]:
    for key in ("data", "result"):
        value = data.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _extract_status(data: dict[str, Any]) -> str:
    return str(extract_hifly_id(data, "status", "state") or "processing").lower()


def _task_has_result(data: dict[str, Any], task_type: str) -> bool:
    if task_type == "avatar":
        return bool(extract_hifly_id(data, "avatar_id", "avatarId", "avatar"))
    if task_type == "voice":
        return bool(extract_hifly_id(data, "voice_id", "voiceId", "voice"))
    if task_type == "video":
        return bool(extract_hifly_id(data, "video_url", "videoUrl", "video_Url", "result_url", "url"))
    return False


def _normalize_voice_type(value: str | int) -> int:
    if isinstance(value, int):
        return value
    text = str(value or "").strip().lower()
    if not text or text == "clone":
        return 8
    try:
        return int(text)
    except ValueError:
        return 8


def _is_success(data: dict[str, Any]) -> bool:
    if data.get("success") is True:
        return True
    code = data.get("code")
    return code in {0, "0", 200, "200"} or (code is None and bool(data))


def _safe_response_json(response: httpx.Response) -> dict[str, Any]:
    try:
        return response.json()
    except Exception:
        return {"status_code": response.status_code, "text": response.text[:2000], "request_id": uuid4().hex}
