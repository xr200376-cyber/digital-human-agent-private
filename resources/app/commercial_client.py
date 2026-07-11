from __future__ import annotations

import hashlib
import json
import os
import platform
import socket
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib import error, parse, request

from app.utils.files import ensure_dir


DEFAULT_COMMERCIAL_API_BASE = "https://api.digitalhumanagent.example.com"
DEFAULT_OFFLINE_GRACE_SECONDS = 3 * 24 * 60 * 60


class CommercialLicenseError(Exception):
    """Base exception for desktop license client failures."""


class CommercialLicenseHttpError(CommercialLicenseError):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


RequestJson = Callable[[str, str, dict[str, Any] | None], dict[str, Any]]


class CommercialLicenseClient:
    def __init__(
        self,
        *,
        storage_dir: Path,
        api_base_url: str = DEFAULT_COMMERCIAL_API_BASE,
        request_json: RequestJson | None = None,
        machine_code_provider: Callable[[], str] | None = None,
        device_name_provider: Callable[[], str] | None = None,
        now: Callable[[], datetime] | None = None,
        offline_grace_seconds: int = DEFAULT_OFFLINE_GRACE_SECONDS,
    ):
        self.storage_dir = Path(storage_dir)
        self.api_base_url = api_base_url.rstrip("/")
        self.request_json = request_json or _urllib_request_json
        self.machine_code_provider = machine_code_provider or default_machine_code
        self.device_name_provider = device_name_provider or default_device_name
        self.now = now or _utc_now
        self.offline_grace = timedelta(seconds=offline_grace_seconds)
        self.state_dir = ensure_dir(self.storage_dir / "desktop" / "commercial")
        self.state_path = self.state_dir / "activation_state.json"

    def activate(self, license_key: str, *, app_version: str = "", device_name: str = "") -> dict[str, Any]:
        clean_key = license_key.strip()
        if not clean_key:
            raise CommercialLicenseError("license_key_required")
        machine_code = self.machine_code_provider()
        payload = {
            "license_key": clean_key,
            "machine_code": machine_code,
            "device_name": device_name.strip() or self.device_name_provider(),
            "app_version": app_version,
            "platform": "windows",
        }
        response = self.request_json("POST", self._url("/activation/activate"), payload)
        state = self._state_from_activation_response(response, payload)
        self._write_state(state)
        return self._allowed_status(state, status="active", update=response.get("update", {}))

    def status(self, *, app_version: str = "") -> dict[str, Any]:
        state = self._read_state()
        token = str(state.get("activation_token") or "")
        if not token:
            return {
                "activated": False,
                "allowed": False,
                "status": "not_activated",
                "message": "请先输入授权码激活软件。",
            }
        payload = {
            "activation_token": token,
            "machine_code": self.machine_code_provider(),
            "app_version": app_version,
            "platform": "windows",
        }
        try:
            response = self.request_json("POST", self._url("/activation/heartbeat"), payload)
        except CommercialLicenseHttpError as exc:
            state["last_error"] = exc.detail
            state["last_checked_at"] = _iso(self.now())
            self._write_state(state)
            return self._blocked_status(state, status=exc.detail, message=_customer_message(exc.detail))
        except Exception as exc:
            last_success = _parse_datetime(str(state.get("last_success_at") or ""))
            if last_success and self.now() - last_success <= self.offline_grace:
                return self._allowed_status(
                    state,
                    status="offline_grace",
                    message="暂时无法连接授权服务器，已进入离线宽限期。",
                    error=str(exc),
                )
            return self._blocked_status(
                state,
                status="offline_expired",
                message="离线宽限期已过，请联网后重新校验授权。",
                error=str(exc),
            )

        updated_state = self._state_from_activation_response(response, payload, existing_state=state)
        self._write_state(updated_state)
        return self._allowed_status(updated_state, status="active", update=response.get("update", {}))

    def check_update(self, *, current_version: str, channel: str = "stable", platform_name: str = "windows") -> dict[str, Any]:
        query = parse.urlencode({"version": current_version, "channel": channel, "platform": platform_name})
        return self.request_json("GET", self._url(f"/updates/latest?{query}"), None)

    def claim_usage(self, *, usage_seconds: int, feature: str = "", context: dict[str, Any] | None = None) -> dict[str, Any]:
        state = self._read_state()
        token = str(state.get("activation_token") or "")
        if not token:
            raise CommercialLicenseError("activation_token_missing")
        payload = {
            "activation_token": token,
            "machine_code": self.machine_code_provider(),
            "usage_seconds": max(int(usage_seconds or 0), 0),
            "feature": feature,
            "context": context or {},
        }
        return self.request_json("POST", self._url("/license/usage/claim"), payload)

    def reserve_credits(
        self,
        *,
        seconds: int,
        provider: str = "hifly",
        feature: str = "",
        task_id: str = "",
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        state = self._read_state()
        token = str(state.get("activation_token") or "")
        if not token:
            raise CommercialLicenseError("activation_token_missing")
        payload = {
            "activation_token": token,
            "machine_code": self.machine_code_provider(),
            "seconds": max(int(seconds or 0), 1),
            "provider": provider,
            "feature": feature,
            "task_id": task_id,
            "context": context or {},
        }
        return self.request_json("POST", self._url("/license/credits/reserve"), payload)

    def commit_credits(
        self,
        *,
        reservation_id: str,
        task_id: str = "",
        actual_seconds: int | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "reservation_id": reservation_id,
            "task_id": task_id,
            "context": context or {},
        }
        if actual_seconds is not None:
            payload["actual_seconds"] = max(int(actual_seconds or 0), 1)
        return self.request_json("POST", self._url("/license/credits/commit"), payload)

    def refund_credits(
        self,
        *,
        reservation_id: str,
        reason: str = "provider_failed",
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "reservation_id": reservation_id,
            "reason": reason,
            "context": context or {},
        }
        return self.request_json("POST", self._url("/license/credits/refund"), payload)

    def credit_overview(self, *, limit: int = 20) -> dict[str, Any]:
        state = self._read_state()
        token = str(state.get("activation_token") or "")
        if not token:
            raise CommercialLicenseError("activation_token_missing")
        payload = {
            "activation_token": token,
            "machine_code": self.machine_code_provider(),
            "limit": max(min(int(limit or 20), 100), 1),
        }
        response = self.request_json("POST", self._url("/license/credits/transactions"), payload)
        credits = _credits_from_response(response)
        if credits:
            state["credits"] = credits
            state["last_checked_at"] = _iso(self.now())
            self._write_state(state)
        return response

    def send_client_log(
        self,
        *,
        level: str,
        event_type: str,
        message: str,
        app_version: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        state = self._read_state()
        payload = {
            "activation_token": str(state.get("activation_token") or ""),
            "machine_id": self.machine_code_provider(),
            "level": level,
            "event_type": event_type,
            "message": message,
            "app_version": app_version,
            "metadata": metadata or {},
        }
        return self.request_json("POST", self._url("/logs/client"), payload)

    def clear_activation(self) -> None:
        if self.state_path.exists():
            self.state_path.unlink()

    def _state_from_activation_response(
        self,
        response: dict[str, Any],
        payload: dict[str, Any],
        *,
        existing_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        activation = response.get("activation") if isinstance(response.get("activation"), dict) else {}
        token = activation.get("activation_token") or response.get("activation_token")
        if not token and existing_state:
            token = existing_state.get("activation_token")
        if not token:
            raise CommercialLicenseError("activation_token_missing")
        now_text = _iso(self.now())
        credits = _credits_from_response(response)
        return {
            "activation_token": token,
            "license_id": response.get("license_id") or response.get("license", {}).get("license_id", ""),
            "customer_name": response.get("customer_name", ""),
            "plan": response.get("plan", ""),
            "expires_at": response.get("expires_at", ""),
            "features": response.get("features", []),
            "credits": credits,
            "heartbeat_interval_seconds": response.get("heartbeat_interval_seconds", 3600),
            "device_name": payload.get("device_name", existing_state.get("device_name", "") if existing_state else ""),
            "app_version": payload.get("app_version", ""),
            "machine_code_hash": _hash_machine_code(str(payload.get("machine_code") or "")),
            "api_base_url": self.api_base_url,
            "activated_at": existing_state.get("activated_at", now_text) if existing_state else now_text,
            "last_success_at": now_text,
            "last_checked_at": now_text,
            "last_error": "",
        }

    def _allowed_status(self, state: dict[str, Any], *, status: str, message: str = "", error: str = "", update: dict | None = None) -> dict[str, Any]:
        return {
            "activated": True,
            "allowed": True,
            "status": status,
            "message": message or "授权校验通过。",
            "customer_name": state.get("customer_name", ""),
            "license_id": state.get("license_id", ""),
            "plan": state.get("plan", ""),
            "expires_at": state.get("expires_at", ""),
            "features": state.get("features", []),
            "credits": state.get("credits", {}),
            "last_success_at": state.get("last_success_at", ""),
            "update": update or {},
            "error": error,
        }

    def _blocked_status(self, state: dict[str, Any], *, status: str, message: str, error: str = "") -> dict[str, Any]:
        return {
            "activated": bool(state.get("activation_token")),
            "allowed": False,
            "status": status,
            "message": message,
            "customer_name": state.get("customer_name", ""),
            "license_id": state.get("license_id", ""),
            "plan": state.get("plan", ""),
            "expires_at": state.get("expires_at", ""),
            "features": state.get("features", []),
            "credits": state.get("credits", {}),
            "error": error,
        }

    def _read_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {}
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    def _write_state(self, state: dict[str, Any]) -> None:
        self.state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    def _url(self, path: str) -> str:
        return self.api_base_url + path


def _credits_from_response(response: dict[str, Any]) -> dict[str, Any]:
    license_body = response.get("license") if isinstance(response.get("license"), dict) else {}
    credits = response.get("credits") if isinstance(response.get("credits"), dict) else license_body.get("credits")
    if not isinstance(credits, dict):
        return {}
    allowed_keys = {
        "balance",
        "grant_monthly",
        "rate_per_second",
        "provider_cost_per_second",
        "total_granted",
        "total_used",
        "total_refunded",
        "cycle_starts_at",
        "cycle_ends_at",
        "locked",
        "locked_at",
        "lock_reason",
    }
    return {key: value for key, value in credits.items() if key in allowed_keys}


def default_device_name() -> str:
    return socket.gethostname() or platform.node() or "Windows PC"


def default_machine_code() -> str:
    parts = [
        str(uuid.getnode()),
        platform.node(),
        os.environ.get("COMPUTERNAME", ""),
        os.environ.get("USERNAME", ""),
    ]
    raw = "|".join(piece for piece in parts if piece)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _hash_machine_code(value: str) -> str:
    return hashlib.sha256(("machine:" + value.strip()).encode("utf-8")).hexdigest()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _customer_message(status: str) -> str:
    messages = {
        "activation_token_invalid": "授权已失效，请重新激活。",
        "machine_mismatch": "当前设备与授权绑定设备不一致，请联系管理员重置设备。",
        "license_disabled": "授权已被停用，请联系管理员。",
        "license_expired": "授权已过期，请续费后继续使用。",
        "device_limit_reached": "授权设备数量已达上限，请联系管理员处理。",
        "license_usage_limit_reached": "体验时长已用完，请购买正式版后继续使用。",
        "license_usage_limit_insufficient": "本次生成超过剩余体验时长，请购买正式版后继续使用。",
        "license_credit_insufficient": "可用积分不足，请充值或购买正式版后继续使用。",
    }
    return messages.get(status, "授权校验失败，请联系管理员。")


def _urllib_request_json(method: str, url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = request.Request(url, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=15) as response:
            body = response.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.reason
        try:
            body = exc.read().decode("utf-8")
            parsed = json.loads(body)
            detail = str(parsed.get("detail") or detail)
        except Exception:
            pass
        raise CommercialLicenseHttpError(exc.code, detail) from exc
    if not body:
        return {}
    parsed = json.loads(body)
    if not isinstance(parsed, dict):
        raise CommercialLicenseError("invalid_json_response")
    return parsed
