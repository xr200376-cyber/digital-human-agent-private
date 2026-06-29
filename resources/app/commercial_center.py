from __future__ import annotations

import base64
from calendar import monthrange
import hashlib
import hmac
import json
import os
import shutil
import secrets
import string
import struct
import time
import zipfile
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, ClassVar
from uuid import uuid4

from fastapi import APIRouter, Cookie, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from app.settings import Settings, get_settings
from app.utils.files import ensure_dir, read_json, write_json


STATIC_DIR = Path(__file__).resolve().parent / "static"
ADMIN_SESSION_COOKIE = "aivo_admin_session"
PBKDF2_PREFIX = "pbkdf2_sha256"
_RATE_LIMITS: dict[tuple[str, str, str], list[float]] = {}
CREDIT_RATE_PER_SECOND = 15
PROVIDER_COST_PER_SECOND = 10
PAYMENT_EVIDENCE_CONTENT_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}
PAYMENT_EVIDENCE_MAX_BYTES = 5 * 1024 * 1024
PLAN_DEFAULT_CREDITS = {
    "trial": 1300,
    "monthly": 36_000,
    "monthly_premium": 36_000,
    "monthly_diamond": 200_000,
    "yearly": 200_000,
    "pro": 200_000,
}
SHOP_PLANS = [
    {"product_id": "trial", "product_type": "trial", "name": "试用版", "amount_cents": 990, "credit_grant": 1_300},
    {
        "product_id": "monthly_premium",
        "product_type": "monthly_premium",
        "name": "高级会员（月付）",
        "amount_cents": 18_800,
        "credit_grant": 36_000,
    },
    {
        "product_id": "monthly_diamond",
        "product_type": "monthly_diamond",
        "name": "钻石会员（月付）",
        "amount_cents": 98_800,
        "credit_grant": 200_000,
    },
]
ORDER_STATUS_LABELS = {
    "draft": "待提交",
    "pending_review": "待确认收款",
    "needs_evidence": "需补充凭证",
    "paid": "已确认收款",
    "fulfilled": "已发货",
    "fulfillment_failed": "发货失败",
    "rejected": "已驳回",
    "cancelled": "已取消",
}


def _is_production(settings: Settings) -> bool:
    return str(getattr(settings, "app_env", "") or "").strip().lower() in {"prod", "production", "server"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _add_one_month(value: datetime) -> datetime:
    month = value.month + 1
    year = value.year
    if month > 12:
        month = 1
        year += 1
    day = min(value.day, monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _default_credit_grant(plan: str) -> int:
    return PLAN_DEFAULT_CREDITS.get((plan or "").strip().lower(), 0)


def _credit_cycle_bounds(now_value: datetime | None = None) -> tuple[str, str]:
    start = (now_value or datetime.now(timezone.utc)).astimezone(timezone.utc)
    end = _add_one_month(start)
    return start.isoformat(), end.isoformat()


def _hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_admin_password(password: str, *, salt: str | None = None, iterations: int = 260_000) -> str:
    clean = password or ""
    salt_text = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", clean.encode("utf-8"), salt_text.encode("utf-8"), iterations)
    return f"{PBKDF2_PREFIX}${iterations}${salt_text}${digest.hex()}"


def _verify_password_hash(password: str, stored_hash: str) -> bool:
    try:
        prefix, iterations_text, salt, expected_hex = stored_hash.split("$", 3)
        iterations = int(iterations_text)
    except (ValueError, TypeError):
        return False
    if prefix != PBKDF2_PREFIX or iterations < 100_000:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations).hex()
    return hmac.compare_digest(digest, expected_hex)


def _hash_machine_code(value: str) -> str:
    return _hash_secret("machine:" + value.strip())


def _mask_key(value: str) -> str:
    clean = value.strip()
    if len(clean) <= 10:
        return clean[:2] + "***"
    return clean[:5] + "***" + clean[-5:]


def _new_license_key() -> str:
    alphabet = string.ascii_uppercase + string.digits
    groups = ["".join(secrets.choice(alphabet) for _ in range(5)) for _ in range(4)]
    return "AIVO-" + "-".join(groups)


def _parse_version(value: str | None) -> tuple[int, ...]:
    if not value:
        return (0,)
    parts: list[int] = []
    for piece in value.replace("-", ".").split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        if digits:
            parts.append(int(digits))
    return tuple(parts or [0])


def _safe_release_filename(filename: str) -> str:
    name = Path(filename or "release.bin").name.strip()
    name = "".join(ch if ch.isalnum() or ch in {".", "-", "_"} else "_" for ch in name)
    if not name:
        name = f"release_{uuid4().hex}.bin"
    return name[:160]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mask_url(value: str) -> str:
    if not value:
        return ""
    if "@" in value:
        left, right = value.rsplit("@", 1)
        return "***@" + right
    return value


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _rate_limit(request: Request, settings: Settings, *, bucket: str, per_minute: int) -> None:
    if per_minute <= 0:
        return
    now = time.monotonic()
    window_start = now - 60
    storage_key = str(getattr(settings, "storage_dir", ""))
    key = (storage_key, bucket, _client_ip(request))
    hits = [item for item in _RATE_LIMITS.get(key, []) if item >= window_start]
    if len(hits) >= per_minute:
        _RATE_LIMITS[key] = hits
        raise HTTPException(status_code=429, detail="too_many_requests")
    hits.append(now)
    _RATE_LIMITS[key] = hits


async def _read_limited_upload(file: UploadFile, limit: int) -> bytes:
    payload = await file.read(limit + 1)
    await file.close()
    if len(payload) > limit:
        raise HTTPException(status_code=400, detail="evidence_file_too_large")
    return payload


def _limit_text(value: str, max_length: int) -> str:
    return (value or "").strip()[:max_length]


def _valid_png(payload: bytes) -> bool:
    if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return False
    offset = 8
    seen_ihdr = False
    while offset + 12 <= len(payload):
        chunk_length = struct.unpack(">I", payload[offset : offset + 4])[0]
        chunk_type = payload[offset + 4 : offset + 8]
        data_start = offset + 8
        data_end = data_start + chunk_length
        crc_end = data_end + 4
        if crc_end > len(payload):
            return False
        chunk_data = payload[data_start:data_end]
        expected_crc = struct.unpack(">I", payload[data_end:crc_end])[0]
        actual_crc = zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF
        if expected_crc != actual_crc:
            return False
        if not seen_ihdr:
            if chunk_type != b"IHDR" or chunk_length != 13:
                return False
            seen_ihdr = True
        if chunk_type == b"IEND":
            return seen_ihdr and crc_end == len(payload)
        offset = crc_end
    return False


def _payment_evidence_suffix(content_type: str, payload: bytes) -> str:
    clean_content_type = (content_type or "").strip().lower()
    if clean_content_type == "image/png":
        if _valid_png(payload):
            return ".png"
    elif clean_content_type in {"image/jpeg", "image/jpg"}:
        if len(payload) > 4 and payload.startswith(b"\xff\xd8\xff"):
            return ".jpg"
    elif clean_content_type == "image/webp":
        if len(payload) > 16 and payload.startswith(b"RIFF") and payload[8:12] == b"WEBP":
            return ".webp"
    raise HTTPException(status_code=400, detail="unsupported_evidence_file")


class AdminLoginRequest(BaseModel):
    username: str
    password: str


class CustomerCreateRequest(BaseModel):
    name: str
    contact: str = ""
    phone: str = ""
    email: str = ""
    wechat: str = ""
    company: str = ""
    note: str = ""
    notes: str = ""
    status: str = "active"


class CustomerUpdateRequest(BaseModel):
    name: str | None = None
    contact: str | None = None
    phone: str | None = None
    email: str | None = None
    wechat: str | None = None
    company: str | None = None
    note: str | None = None
    notes: str | None = None
    status: str | None = None


class CustomerRecord(BaseModel):
    customer_id: str = Field(default_factory=lambda: f"cus_{uuid4().hex[:12]}")
    name: str
    contact: str = ""
    phone: str = ""
    email: str = ""
    wechat: str = ""
    company: str = ""
    note: str = ""
    notes: str = ""
    status: str = "active"
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)


class LicenseCreateRequest(BaseModel):
    customer_id: str
    plan: str = "yearly"
    seats: int = 1
    max_devices: int | None = None
    starts_at: str | None = None
    expires_at: str | None = None
    features: list[str] = Field(default_factory=lambda: ["digital_human", "video_remix", "publish"])
    feature_flags: list[str] | None = None
    usage_limit_seconds: int | None = None
    credit_grant: int | None = None
    note: str = ""
    notes: str = ""


class LicenseUpdateRequest(BaseModel):
    plan: str | None = None
    seats: int | None = None
    max_devices: int | None = None
    starts_at: str | None = None
    expires_at: str | None = None
    features: list[str] | None = None
    feature_flags: list[str] | None = None
    status: str | None = None
    usage_limit_seconds: int | None = None
    usage_used_seconds: int | None = None
    usage_locked_at: str | None = None
    usage_lock_reason: str | None = None
    credit_balance: int | None = None
    credit_grant_monthly: int | None = None
    credit_lock_reason: str | None = None
    note: str | None = None
    notes: str | None = None


class LicenseRecord(BaseModel):
    license_id: str = Field(default_factory=lambda: f"lic_{uuid4().hex[:12]}")
    customer_id: str
    key_hash: str
    key_preview: str
    plan: str = "yearly"
    seats: int = 1
    max_devices: int = 1
    status: str = "active"
    starts_at: str | None = None
    expires_at: str | None = None
    features: list[str] = Field(default_factory=list)
    feature_flags: list[str] = Field(default_factory=list)
    note: str = ""
    notes: str = ""
    usage_limit_seconds: int | None = None
    usage_used_seconds: int = 0
    usage_locked_at: str = ""
    usage_lock_reason: str = ""
    credit_rate_per_second: int = CREDIT_RATE_PER_SECOND
    credit_balance: int = 0
    credit_grant_monthly: int = 0
    credit_total_granted: int = 0
    credit_total_used: int = 0
    credit_total_refunded: int = 0
    credit_cycle_starts_at: str = ""
    credit_cycle_ends_at: str = ""
    credit_refreshed_at: str = ""
    credit_locked_at: str = ""
    credit_lock_reason: str = ""
    last_heartbeat_at: str = ""
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)


class LicenseCreateResponse(BaseModel):
    license: dict[str, Any]
    license_key: str


class ActivationRequest(BaseModel):
    license_key: str
    machine_id: str = ""
    machine_code: str = ""
    device_name: str = ""
    app_version: str = ""
    platform: str = "windows"

    def machine_code_value(self) -> str:
        return (self.machine_code or self.machine_id or "").strip()


class HeartbeatRequest(BaseModel):
    activation_token: str
    machine_id: str = ""
    machine_code: str = ""
    app_version: str = ""
    platform: str = "windows"

    def machine_code_value(self) -> str:
        return (self.machine_code or self.machine_id or "").strip()


class LicenseUsageClaimRequest(BaseModel):
    activation_token: str
    machine_id: str = ""
    machine_code: str = ""
    usage_seconds: int
    feature: str = ""
    context: dict[str, Any] = Field(default_factory=dict)

    def machine_code_value(self) -> str:
        return (self.machine_code or self.machine_id or "").strip()


class LicenseRestorePaidRequest(BaseModel):
    plan: str = "yearly"
    credit_grant: int | None = None


class CreditReserveRequest(BaseModel):
    activation_token: str
    machine_id: str = ""
    machine_code: str = ""
    provider: str = "hifly"
    feature: str = ""
    seconds: int
    task_id: str = ""
    context: dict[str, Any] = Field(default_factory=dict)

    def machine_code_value(self) -> str:
        return (self.machine_code or self.machine_id or "").strip()


class CreditCommitRequest(BaseModel):
    reservation_id: str
    task_id: str = ""
    actual_seconds: int | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class CreditRefundRequest(BaseModel):
    reservation_id: str
    reason: str = "provider_failed"
    context: dict[str, Any] = Field(default_factory=dict)


class CreditTransactionsRequest(BaseModel):
    activation_token: str
    machine_id: str = ""
    machine_code: str = ""
    limit: int = 20

    def machine_code_value(self) -> str:
        return (self.machine_code or self.machine_id or "").strip()


class AdminCreditAdjustRequest(BaseModel):
    delta_credits: int
    reason: str = ""
    note: str = ""


class ShopOrderCreateRequest(BaseModel):
    product_id: str
    contact_name: str = ""
    wechat: str
    phone: str = ""
    existing_license_key: str = ""
    payment_note: str = ""
    payment_time: str = ""


class OrderAdminActionRequest(BaseModel):
    note: str = ""


class ManualPaymentOrderRecord(BaseModel):
    order_id: str = Field(default_factory=lambda: f"ord_{uuid4().hex[:12]}")
    order_no: str = Field(
        default_factory=lambda: f"XT{datetime.now(timezone.utc).strftime('%Y%m%d')}{uuid4().hex[:8].upper()}"
    )
    customer_access_token: str = Field(default_factory=lambda: secrets.token_urlsafe(24))
    customer_id: str = ""
    license_id: str = ""
    license_key_preview: str = ""
    contact_name: str = ""
    wechat: str = ""
    phone: str = ""
    existing_license_key_hash: str = ""
    product_type: str
    product_id: str
    product_name: str
    amount_cents: int
    currency: str = "CNY"
    credit_grant: int
    status: str = "pending_review"
    payment_method: str = "wechat_manual"
    payment_note: str = ""
    payment_time: str = ""
    evidence_file_id: str = ""
    delivery: dict[str, Any] = Field(default_factory=dict)
    operator_note: str = ""
    fulfillment_error: str = ""
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
    paid_at: str = ""
    fulfilled_at: str = ""
    rejected_at: str = ""


class ManualPaymentEvidenceRecord(BaseModel):
    evidence_id: str = Field(default_factory=lambda: f"ev_{uuid4().hex[:12]}")
    order_id: str
    original_filename: str = ""
    stored_path: str
    content_type: str = ""
    size_bytes: int = 0
    created_at: str = Field(default_factory=_now)


class ActivationRecord(BaseModel):
    activation_id: str = Field(default_factory=lambda: f"act_{uuid4().hex[:12]}")
    license_id: str
    customer_id: str
    machine_id: str = ""
    machine_code_hash: str = ""
    device_name: str = ""
    activation_token: str
    app_version: str = ""
    platform: str = "windows"
    status: str = "active"
    activated_at: str = Field(default_factory=_now)
    last_seen_at: str = Field(default_factory=_now)


class ReleaseCreateRequest(BaseModel):
    version: str
    download_url: str
    channel: str = "stable"
    platform: str = "windows"
    release_notes: str = ""
    changelog: str = ""
    sha256: str = ""
    min_supported_version: str = ""
    force_update: bool = False
    status: str = "published"


class ReleaseRecord(BaseModel):
    release_id: str = Field(default_factory=lambda: f"rel_{uuid4().hex[:12]}")
    version: str
    download_url: str
    channel: str = "stable"
    platform: str = "windows"
    release_notes: str = ""
    changelog: str = ""
    sha256: str = ""
    size_bytes: int = 0
    min_supported_version: str = ""
    force_update: bool = False
    status: str = "published"
    created_at: str = Field(default_factory=_now)
    published_at: str = Field(default_factory=_now)


class ClientLogRequest(BaseModel):
    activation_token: str = ""
    machine_id: str = ""
    level: str = "info"
    event_type: str = "client_event"
    message: str
    app_version: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class BackupRecord(BaseModel):
    backup_id: str = Field(default_factory=lambda: f"bak_{uuid4().hex[:12]}")
    created_at: str = Field(default_factory=_now)
    status: str = "completed"
    backend: str = "file"
    filename: str = ""
    size_bytes: int = 0
    message: str = ""


class CommercialCenterStore:
    backend_name = "file"

    @classmethod
    def from_settings(cls, settings: Settings) -> "CommercialCenterStore":
        backend = str(getattr(settings, "commercial_repository_backend", "file") or "file").strip().lower()
        if backend in {"postgres", "postgresql"}:
            return PostgresCommercialCenterStore(settings)
        return cls(settings)

    def __init__(self, settings: Settings):
        self.settings = settings
        self.root = ensure_dir(settings.storage_dir / "commercial_center")
        self.data_path = self.root / "data.json"
        self.logs_path = self.root / "client_logs.jsonl"
        self.backups_path = self.root / "backups.json"
        self.backups_dir = ensure_dir(self.root / "backups")
        self.releases_dir = ensure_dir(self.root / "releases")
        self.evidence_dir = ensure_dir(self.root / "manual_payment_evidence")

    def _default_data(self) -> dict[str, Any]:
        return {
            "customers": {},
            "licenses": {},
            "activations": {},
            "releases": {},
            "audit_logs": [],
            "credit_transactions": {},
            "orders": {},
            "manual_payment_evidence": {},
        }

    def _load(self) -> dict[str, Any]:
        if not self.data_path.exists():
            return self._default_data()
        data = read_json(self.data_path)
        if not isinstance(data, dict):
            return self._default_data()
        default = self._default_data()
        for key, value in default.items():
            data.setdefault(key, value)
        return data

    def _save(self, data: dict[str, Any]) -> None:
        write_json(self.data_path, data)

    def readiness(self) -> dict[str, Any]:
        return {
            "backend": self.backend_name,
            "ready": True,
            "database_url_configured": False,
        }

    def health(self) -> dict[str, Any]:
        summary = self.summary()
        backups = self.list_backups()
        alerts: list[str] = []
        if not backups["items"]:
            alerts.append("no_backup")
        if not summary.get("latest_version"):
            alerts.append("no_release")
        recent_errors = summary.get("recent_errors") or []
        if recent_errors:
            alerts.append("recent_client_errors")
        return {
            "ok": True,
            "checked_at": _now(),
            "database": self.readiness(),
            "backups": {
                "latest": backups["items"][0] if backups["items"] else None,
                "count": backups["count"],
            },
            "releases": {
                "count": summary.get("releases", 0),
                "latest_version": summary.get("latest_version", ""),
            },
            "usage": {
                "customers": summary.get("customers", 0),
                "active_licenses": summary.get("active_licenses", 0),
                "online_devices": summary.get("online_devices", 0),
                "recent_errors": len(recent_errors),
            },
            "alerts": alerts,
        }

    def _load_backup_records(self) -> list[dict[str, Any]]:
        if not self.backups_path.exists():
            return []
        data = read_json(self.backups_path)
        return data if isinstance(data, list) else []

    def _save_backup_records(self, rows: list[dict[str, Any]]) -> None:
        write_json(self.backups_path, rows[-300:])

    def list_backups(self) -> dict[str, Any]:
        rows = sorted(self._load_backup_records(), key=lambda row: row.get("created_at", ""), reverse=True)
        return {"items": rows, "count": len(rows)}

    def run_backup(self) -> dict[str, Any]:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        filename = f"commercial_backup_{stamp}_{uuid4().hex[:8]}.zip"
        target = self.backups_dir / filename
        ensure_dir(target.parent)
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            if self.data_path.exists():
                archive.write(self.data_path, arcname="commercial_center/data.json")
            if self.logs_path.exists():
                archive.write(self.logs_path, arcname="commercial_center/client_logs.jsonl")
            archive.writestr(
                "manifest.json",
                json.dumps(
                    {
                        "created_at": _now(),
                        "backend": self.backend_name,
                        "contains": ["data.json", "client_logs.jsonl"],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            )
        record = BackupRecord(
            backend=self.backend_name,
            filename=filename,
            size_bytes=target.stat().st_size,
            status="completed",
        ).model_dump(mode="json")
        rows = self._load_backup_records()
        rows.append(record)
        self._save_backup_records(rows)
        self._prune_old_backups()
        return {"ok": True, "backup": record}

    def _prune_old_backups(self) -> None:
        retention_days = max(int(getattr(self.settings, "commercial_backup_retention_days", 14) or 14), 1)
        cutoff = time.time() - retention_days * 86400
        for path in self.backups_dir.glob("commercial_backup_*.zip"):
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink(missing_ok=True)
            except OSError:
                continue

    def summary(self) -> dict[str, Any]:
        data = self._load()
        customers = [item for item in data["customers"].values() if item.get("status") != "deleted"]
        licenses = [item for item in data["licenses"].values() if not item.get("deleted_with_customer")]
        activations = [item for item in data["activations"].values() if not item.get("deleted_with_customer")]
        releases = list(data["releases"].values())
        logs = self.list_logs(limit=50)
        latest_release = self.latest_release(channel="stable", platform="windows")
        return {
            "customers": len(customers),
            "active_customers": sum(1 for item in customers if item.get("status") in {"active", "trial"}),
            "licenses": len(licenses),
            "active_licenses": sum(1 for item in licenses if item.get("status") == "active"),
            "activations": len(activations),
            "online_devices": sum(1 for item in activations if item.get("status") == "active"),
            "releases": len(releases),
            "latest_release": latest_release,
            "latest_version": latest_release.get("version") if latest_release else "",
            "recent_logs": logs[:8],
            "recent_errors": [row for row in logs if str(row.get("level", "")).lower() in {"error", "fatal"}][:8],
        }

    def shop_plans(self) -> dict[str, Any]:
        return {
            "currency": "CNY",
            "payment_method": "wechat_manual",
            "payment_instructions": "请使用页面展示的微信收款码付款，付款后提交备注或截图，后台确认后发货。",
            "plans": [
                {
                    **plan,
                    "payment_method": "wechat_manual",
                    "currency": "CNY",
                    "credits_seconds": int(plan["credit_grant"]) // CREDIT_RATE_PER_SECOND,
                }
                for plan in SHOP_PLANS
            ],
        }

    def _shop_plan_by_id(self, product_id: str) -> dict[str, Any]:
        clean_product_id = (product_id or "").strip()
        for plan in SHOP_PLANS:
            if plan["product_id"] == clean_product_id:
                return dict(plan)
        raise HTTPException(status_code=400, detail="shop_product_not_found")

    def create_shop_order(self, request: ShopOrderCreateRequest) -> dict[str, Any]:
        wechat = _limit_text(request.wechat, 120)
        payment_note = _limit_text(request.payment_note, 500)
        payment_time = _limit_text(request.payment_time, 80)
        if not wechat:
            raise HTTPException(status_code=400, detail="wechat_required")
        if not (payment_note or payment_time):
            raise HTTPException(status_code=400, detail="payment_evidence_required")
        plan = self._shop_plan_by_id(request.product_id)
        existing_license_key = (request.existing_license_key or "").strip()
        data = self._load()
        order = ManualPaymentOrderRecord(
            contact_name=_limit_text(request.contact_name, 120) or wechat,
            wechat=wechat,
            phone=_limit_text(request.phone, 40),
            existing_license_key_hash=_hash_secret(existing_license_key) if existing_license_key else "",
            product_type=str(plan["product_type"]),
            product_id=str(plan["product_id"]),
            product_name=str(plan["name"]),
            amount_cents=int(plan["amount_cents"]),
            credit_grant=int(plan["credit_grant"]),
            payment_note=payment_note,
            payment_time=payment_time,
        )
        orders = data.setdefault("orders", {})
        orders[order.order_id] = order.model_dump(mode="json")
        self._append_audit(
            data,
            "order.create",
            "order",
            order.order_id,
            after=self._public_order(orders[order.order_id]),
            actor="customer",
        )
        self._save(data)
        return {"order": self._public_order(orders[order.order_id]), "access_token": order.customer_access_token}

    def list_orders(self, status: str = "") -> list[dict[str, Any]]:
        data = self._load()
        rows = list(data.setdefault("orders", {}).values())
        clean_status = (status or "").strip()
        if clean_status:
            rows = [row for row in rows if row.get("status") == clean_status]
        rows = sorted(rows, key=lambda row: row.get("created_at", ""), reverse=True)
        return [self._public_order(row, include_internal=True) for row in rows]

    def get_order_by_no(self, order_no: str, access_token: str = "") -> dict[str, Any]:
        clean_order_no = (order_no or "").strip()
        data = self._load()
        for row in data.setdefault("orders", {}).values():
            if row.get("order_no") == clean_order_no:
                include_delivery = bool(
                    access_token
                    and row.get("customer_access_token")
                    and hmac.compare_digest(str(access_token), str(row.get("customer_access_token")))
                )
                return {"order": self._public_order(row, include_delivery=include_delivery)}
        raise HTTPException(status_code=404, detail="order_not_found")

    def save_payment_evidence(
        self,
        *,
        order_no: str,
        access_token: str,
        payment_note: str,
        payment_time: str,
        original_filename: str,
        content_type: str,
        payload: bytes,
    ) -> dict[str, Any]:
        clean_note = _limit_text(payment_note, 500)
        clean_time = _limit_text(payment_time, 80)
        clean_content_type = (content_type or "").strip().lower()
        if len(payload) > PAYMENT_EVIDENCE_MAX_BYTES:
            raise HTTPException(status_code=400, detail="evidence_file_too_large")
        if not (payload or clean_note or clean_time):
            raise HTTPException(status_code=400, detail="payment_evidence_required")

        data = self._load()
        order = None
        for row in data.setdefault("orders", {}).values():
            if row.get("order_no") == (order_no or "").strip():
                order = row
                break
        if not order:
            raise HTTPException(status_code=404, detail="order_not_found")
        stored_token = str(order.get("customer_access_token") or "")
        if not stored_token or not access_token or not hmac.compare_digest(str(access_token), stored_token):
            raise HTTPException(status_code=403, detail="order_access_denied")
        if order.get("status") in {"fulfilled", "rejected", "cancelled"}:
            raise HTTPException(status_code=400, detail="order_not_editable")

        suffix = ""
        if payload:
            suffix = _payment_evidence_suffix(clean_content_type, payload)
        if payload:
            evidence_id = f"ev_{uuid4().hex[:12]}"
            target = self.evidence_dir / f"{evidence_id}{suffix}"
            target.write_bytes(payload)
            record = ManualPaymentEvidenceRecord(
                evidence_id=evidence_id,
                order_id=str(order.get("order_id") or ""),
                original_filename=Path(original_filename or "payment-evidence").name[:160],
                stored_path=str(target),
                content_type=clean_content_type,
                size_bytes=len(payload),
            ).model_dump(mode="json")
            data.setdefault("manual_payment_evidence", {})[evidence_id] = record
            order["evidence_file_id"] = evidence_id
        if clean_note:
            order["payment_note"] = clean_note
        if clean_time:
            order["payment_time"] = clean_time
        order["updated_at"] = _now()
        self._append_audit(
            data,
            "order.evidence",
            "order",
            str(order.get("order_id") or ""),
            after=self._public_order(order, include_internal=True),
            actor="customer",
        )
        self._save(data)
        return {"order": self._public_order(order)}

    def confirm_order_payment(self, order_id: str, request: OrderAdminActionRequest) -> dict[str, Any]:
        data = self._load()
        order = self._order_by_id(data, order_id)
        if order.get("status") == "fulfilled" and order.get("delivery"):
            return {"order": self._public_order(order, include_internal=True, include_delivery=True)}
        if order.get("status") in {"rejected", "cancelled"}:
            raise HTTPException(status_code=400, detail="order_not_confirmable")
        if order.get("status") not in {"pending_review", "needs_evidence", "paid", "fulfillment_failed"}:
            raise HTTPException(status_code=400, detail="order_not_confirmable")

        before = self._public_order(order, include_internal=True)
        now_value = _now()
        order["status"] = "paid"
        order["paid_at"] = order.get("paid_at") or now_value
        order["operator_note"] = _limit_text(request.note, 500)
        order["updated_at"] = now_value
        try:
            delivery = self._fulfill_order_locked(data, order)
        except HTTPException as exc:
            order["status"] = "fulfillment_failed"
            order["fulfillment_error"] = str(exc.detail)
            order["updated_at"] = _now()
            self._append_audit(
                data,
                "order.fulfillment_failed",
                "order",
                order["order_id"],
                before=before,
                after=self._public_order(order, include_internal=True),
            )
            self._save(data)
            raise
        order["status"] = "fulfilled"
        order["delivery"] = delivery
        order["license_id"] = delivery.get("license", {}).get("license_id", "")
        order["license_key_preview"] = delivery.get("license", {}).get("key_preview", "")
        order["fulfilled_at"] = order.get("fulfilled_at") or _now()
        order["fulfillment_error"] = ""
        order["updated_at"] = _now()
        self._append_audit(
            data,
            "order.confirm_payment",
            "order",
            order["order_id"],
            before=before,
            after=self._public_order(order, include_internal=True),
        )
        self._save(data)
        return {"order": self._public_order(order, include_internal=True, include_delivery=True)}

    def reject_order(self, order_id: str, request: OrderAdminActionRequest) -> dict[str, Any]:
        data = self._load()
        order = self._order_by_id(data, order_id)
        if order.get("status") == "fulfilled":
            raise HTTPException(status_code=400, detail="order_not_rejectable")
        before = self._public_order(order, include_internal=True)
        order["status"] = "rejected"
        order["operator_note"] = _limit_text(request.note, 500)
        order["rejected_at"] = order.get("rejected_at") or _now()
        order["updated_at"] = _now()
        self._append_audit(
            data,
            "order.reject",
            "order",
            order["order_id"],
            before=before,
            after=self._public_order(order, include_internal=True),
        )
        self._save(data)
        return {"order": self._public_order(order, include_internal=True)}

    def request_order_evidence(self, order_id: str, request: OrderAdminActionRequest) -> dict[str, Any]:
        data = self._load()
        order = self._order_by_id(data, order_id)
        if order.get("status") in {"fulfilled", "rejected", "cancelled"}:
            raise HTTPException(status_code=400, detail="order_not_editable")
        before = self._public_order(order, include_internal=True)
        order["status"] = "needs_evidence"
        order["operator_note"] = _limit_text(request.note, 500)
        order["updated_at"] = _now()
        self._append_audit(
            data,
            "order.request_evidence",
            "order",
            order["order_id"],
            before=before,
            after=self._public_order(order, include_internal=True),
        )
        self._save(data)
        return {"order": self._public_order(order, include_internal=True)}

    def retry_order_fulfillment(self, order_id: str, request: OrderAdminActionRequest) -> dict[str, Any]:
        data = self._load()
        order = self._order_by_id(data, order_id)
        if order.get("status") != "fulfillment_failed":
            raise HTTPException(status_code=400, detail="order_not_retryable")
        order["operator_note"] = _limit_text(request.note, 500)
        self._save(data)
        return self.confirm_order_payment(order_id, request)

    def _order_by_id(self, data: dict[str, Any], order_id: str) -> dict[str, Any]:
        order = data.setdefault("orders", {}).get(order_id)
        if not order:
            raise HTTPException(status_code=404, detail="order_not_found")
        return order

    def _find_license_by_hash(self, data: dict[str, Any], key_hash: str) -> dict[str, Any] | None:
        if not key_hash:
            return None
        for license_record in data.setdefault("licenses", {}).values():
            if license_record.get("key_hash") == key_hash:
                return license_record
        return None

    def _find_or_create_order_customer(self, data: dict[str, Any], order: dict[str, Any]) -> dict[str, Any]:
        customer_id = str(order.get("customer_id") or "")
        if customer_id and customer_id in data.setdefault("customers", {}):
            return data["customers"][customer_id]
        customer = CustomerRecord(
            name=str(order.get("contact_name") or order.get("wechat") or "微信客户"),
            phone=str(order.get("phone") or ""),
            wechat=str(order.get("wechat") or ""),
            status="trial" if order.get("product_type") == "trial" else "active",
            notes=f"订单 {order.get('order_no', '')} 自动创建",
        )
        data["customers"][customer.customer_id] = customer.model_dump(mode="json")
        order["customer_id"] = customer.customer_id
        self._append_audit(
            data,
            "customer.create",
            "customer",
            customer.customer_id,
            after=data["customers"][customer.customer_id],
            actor="system",
        )
        return data["customers"][customer.customer_id]

    def _create_license_in_data(
        self,
        data: dict[str, Any],
        *,
        customer_id: str,
        plan: str,
        credit_grant: int,
        notes: str,
    ) -> tuple[dict[str, Any], str]:
        raw_key = _new_license_key()
        cycle_starts_at, cycle_ends_at = _credit_cycle_bounds()
        record = LicenseRecord(
            customer_id=customer_id,
            key_hash=_hash_secret(raw_key),
            key_preview=_mask_key(raw_key),
            plan=plan,
            seats=1,
            max_devices=1,
            features=["digital_human", "video_remix", "publish"],
            feature_flags=["digital_human", "video_remix", "publish"],
            credit_balance=credit_grant,
            credit_grant_monthly=credit_grant,
            credit_total_granted=credit_grant,
            credit_cycle_starts_at=cycle_starts_at,
            credit_cycle_ends_at=cycle_ends_at,
            credit_refreshed_at=cycle_starts_at,
            notes=notes,
            note=notes,
        )
        data.setdefault("licenses", {})[record.license_id] = record.model_dump(mode="json")
        self._append_audit(
            data,
            "license.create",
            "license",
            record.license_id,
            after=self._public_license(data["licenses"][record.license_id], data=data),
            actor="system",
        )
        return data["licenses"][record.license_id], raw_key

    def _fulfill_order_locked(self, data: dict[str, Any], order: dict[str, Any]) -> dict[str, Any]:
        product_type = str(order.get("product_type") or "")
        credit_grant = max(int(order.get("credit_grant") or 0), 0)
        existing_license = self._find_license_by_hash(data, str(order.get("existing_license_key_hash") or ""))
        if existing_license:
            before = self._public_license(existing_license, data=data)
            self._ensure_credit_fields(existing_license)
            if product_type == "credit_pack":
                existing_license["credit_balance"] = self._credit_int(existing_license, "credit_balance") + credit_grant
                existing_license["credit_total_granted"] = self._credit_int(existing_license, "credit_total_granted") + credit_grant
            else:
                existing_license["plan"] = product_type or "yearly"
                existing_license["status"] = "active"
                existing_license["credit_balance"] = credit_grant
                existing_license["credit_grant_monthly"] = credit_grant
                existing_license["credit_total_granted"] = self._credit_int(existing_license, "credit_total_granted") + credit_grant
                existing_license["usage_limit_seconds"] = None
                existing_license["usage_locked_at"] = ""
                existing_license["usage_lock_reason"] = ""
            existing_license["credit_locked_at"] = ""
            existing_license["credit_lock_reason"] = ""
            existing_license["updated_at"] = _now()
            transaction_id = f"cr_{uuid4().hex[:12]}"
            data.setdefault("credit_transactions", {})[transaction_id] = {
                "transaction_id": transaction_id,
                "license_id": existing_license["license_id"],
                "customer_id": existing_license.get("customer_id", ""),
                "type": "manual_payment",
                "status": "committed",
                "order_id": order.get("order_id", ""),
                "order_no": order.get("order_no", ""),
                "delta_credits": credit_grant,
                "created_at": _now(),
                "updated_at": _now(),
            }
            after = self._public_license(existing_license, data=data)
            self._append_audit(
                data,
                "license.manual_payment_fulfill",
                "license",
                existing_license["license_id"],
                before=before,
                after={**after, "order_id": order.get("order_id", "")},
                actor="system",
            )
            order["customer_id"] = existing_license.get("customer_id", "")
            return {"type": "existing_license", "license": after}
        if order.get("existing_license_key_hash"):
            raise HTTPException(status_code=404, detail="existing_license_not_found")

        customer = self._find_or_create_order_customer(data, order)
        license_record, raw_key = self._create_license_in_data(
            data,
            customer_id=customer["customer_id"],
            plan=product_type if product_type != "credit_pack" else "yearly",
            credit_grant=credit_grant,
            notes=f"订单 {order.get('order_no', '')} 自动发货",
        )
        return {
            "type": "new_license",
            "license_key": raw_key,
            "license": self._public_license(license_record, data=data),
        }

    def _public_order(
        self,
        row: dict[str, Any],
        *,
        include_internal: bool = False,
        include_delivery: bool = False,
    ) -> dict[str, Any]:
        public = dict(row)
        public["status_label"] = ORDER_STATUS_LABELS.get(str(public.get("status") or ""), str(public.get("status") or ""))
        public.pop("customer_access_token", None)
        public.pop("existing_license_key_hash", None)
        public.pop("license_key", None)
        if not include_delivery:
            public.pop("delivery", None)
        if not include_internal:
            public.pop("operator_note", None)
            public.pop("fulfillment_error", None)
        return public

    def create_customer(self, request: CustomerCreateRequest) -> dict[str, Any]:
        data = self._load()
        payload = request.model_dump()
        payload["notes"] = payload.get("notes") or payload.get("note") or ""
        payload["note"] = payload["notes"]
        record = CustomerRecord(**payload)
        data["customers"][record.customer_id] = record.model_dump(mode="json")
        self._append_audit(data, "customer.create", "customer", record.customer_id, after=data["customers"][record.customer_id])
        self._save(data)
        return data["customers"][record.customer_id]

    def list_customers(self, q: str = "", status: str = "") -> list[dict[str, Any]]:
        rows = list(self._load()["customers"].values())
        query = q.strip().lower()
        if status != "deleted":
            rows = [row for row in rows if row.get("status") != "deleted"]
        if query:
            rows = [
                row
                for row in rows
                if query
                in " ".join(
                    str(row.get(key, ""))
                    for key in ("name", "contact", "phone", "email", "wechat", "company", "notes", "note")
                ).lower()
            ]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        return sorted(rows, key=lambda row: row.get("created_at", ""), reverse=True)

    def update_customer(self, customer_id: str, request: CustomerUpdateRequest) -> dict[str, Any]:
        data = self._load()
        customer = data["customers"].get(customer_id)
        if not customer or customer.get("status") == "deleted":
            raise HTTPException(status_code=404, detail="customer not found")
        before = dict(customer)
        for key, value in request.model_dump(exclude_unset=True).items():
            customer[key] = value
        if "notes" in customer and not customer.get("note"):
            customer["note"] = customer.get("notes", "")
        if "note" in customer and not customer.get("notes"):
            customer["notes"] = customer.get("note", "")
        customer["updated_at"] = _now()
        self._append_audit(data, "customer.update", "customer", customer_id, before=before, after=customer)
        self._save(data)
        return customer

    def delete_customer(self, customer_id: str) -> dict[str, Any]:
        data = self._load()
        customer = data["customers"].get(customer_id)
        if not customer or customer.get("status") == "deleted":
            raise HTTPException(status_code=404, detail="customer not found")
        now_value = _now()
        before = dict(customer)
        customer["status"] = "deleted"
        customer["deleted_at"] = now_value
        customer["updated_at"] = now_value

        disabled_license_ids: list[str] = []
        for license_record in data["licenses"].values():
            if license_record.get("customer_id") != customer_id:
                continue
            license_id = str(license_record.get("license_id") or "")
            disabled_license_ids.append(license_id)
            license_record["status"] = "disabled"
            license_record["deleted_with_customer"] = True
            license_record["disabled_reason"] = "customer_deleted"
            license_record["deleted_at"] = now_value
            license_record["updated_at"] = now_value

        disabled_activations = 0
        disabled_license_id_set = set(disabled_license_ids)
        for activation in data["activations"].values():
            if activation.get("customer_id") != customer_id and activation.get("license_id") not in disabled_license_id_set:
                continue
            if activation.get("status") != "disabled":
                disabled_activations += 1
            activation["status"] = "disabled"
            activation["deleted_with_customer"] = True
            activation["disabled_reason"] = "customer_deleted"
            activation["updated_at"] = now_value

        result = {
            "status": "deleted",
            "customer_id": customer_id,
            "disabled_licenses": len(disabled_license_ids),
            "disabled_activations": disabled_activations,
            "deleted_at": now_value,
        }
        self._append_audit(
            data,
            "customer.delete",
            "customer",
            customer_id,
            before=before,
            after={**result, "license_ids": disabled_license_ids},
        )
        self._save(data)
        return result

    def create_license(self, request: LicenseCreateRequest) -> LicenseCreateResponse:
        data = self._load()
        customer = data["customers"].get(request.customer_id)
        if not customer or customer.get("status") == "deleted":
            raise HTTPException(status_code=404, detail="customer not found")
        max_devices = request.max_devices if request.max_devices is not None else request.seats
        if max_devices < 1:
            raise HTTPException(status_code=400, detail="max_devices must be at least 1")
        feature_flags = request.feature_flags if request.feature_flags is not None else request.features
        usage_limit_seconds = request.usage_limit_seconds
        if usage_limit_seconds is not None and usage_limit_seconds < 1:
            raise HTTPException(status_code=400, detail="usage_limit_seconds must be at least 1")
        credit_grant = request.credit_grant if request.credit_grant is not None else _default_credit_grant(request.plan)
        if credit_grant < 0:
            raise HTTPException(status_code=400, detail="credit_grant must be at least 0")
        cycle_starts_at, cycle_ends_at = _credit_cycle_bounds()
        raw_key = _new_license_key()
        record = LicenseRecord(
            customer_id=request.customer_id,
            key_hash=_hash_secret(raw_key),
            key_preview=_mask_key(raw_key),
            plan=request.plan,
            seats=max_devices,
            max_devices=max_devices,
            starts_at=request.starts_at,
            expires_at=request.expires_at,
            features=feature_flags,
            feature_flags=feature_flags,
            usage_limit_seconds=usage_limit_seconds,
            credit_balance=credit_grant,
            credit_grant_monthly=credit_grant,
            credit_total_granted=credit_grant,
            credit_cycle_starts_at=cycle_starts_at,
            credit_cycle_ends_at=cycle_ends_at,
            credit_refreshed_at=cycle_starts_at,
            note=request.notes or request.note,
            notes=request.notes or request.note,
        )
        data["licenses"][record.license_id] = record.model_dump(mode="json")
        self._append_audit(
            data,
            "license.create",
            "license",
            record.license_id,
            after=self._public_license(data["licenses"][record.license_id], data=data),
        )
        self._save(data)
        return LicenseCreateResponse(license=self._public_license(data["licenses"][record.license_id]), license_key=raw_key)

    def list_licenses(self) -> list[dict[str, Any]]:
        data = self._load()
        rows = []
        for license_record in data["licenses"].values():
            if license_record.get("deleted_with_customer"):
                continue
            rows.append(self._public_license(license_record, data=data))
        return sorted(rows, key=lambda row: row.get("created_at", ""), reverse=True)

    def update_license(self, license_id: str, request: LicenseUpdateRequest) -> dict[str, Any]:
        data = self._load()
        license_record = data["licenses"].get(license_id)
        if not license_record:
            raise HTTPException(status_code=404, detail="license not found")
        updates = request.model_dump(exclude_unset=True)
        before = self._public_license(license_record, data=data)
        if "max_devices" in updates and updates["max_devices"] is not None:
            updates["seats"] = updates["max_devices"]
        if "seats" in updates and updates["seats"] is not None:
            if updates["seats"] < 1:
                raise HTTPException(status_code=400, detail="max_devices must be at least 1")
            updates["max_devices"] = updates["seats"]
        if "feature_flags" in updates and updates["feature_flags"] is not None:
            updates["features"] = updates["feature_flags"]
        if "features" in updates and updates["features"] is not None:
            updates["feature_flags"] = updates["features"]
        if "usage_limit_seconds" in updates and updates["usage_limit_seconds"] is not None:
            if updates["usage_limit_seconds"] < 1:
                raise HTTPException(status_code=400, detail="usage_limit_seconds must be at least 1")
        if "usage_used_seconds" in updates and updates["usage_used_seconds"] is not None:
            if updates["usage_used_seconds"] < 0:
                raise HTTPException(status_code=400, detail="usage_used_seconds must be at least 0")
        if "credit_balance" in updates and updates["credit_balance"] is not None:
            if updates["credit_balance"] < 0:
                raise HTTPException(status_code=400, detail="credit_balance must be at least 0")
        if "credit_grant_monthly" in updates and updates["credit_grant_monthly"] is not None:
            if updates["credit_grant_monthly"] < 0:
                raise HTTPException(status_code=400, detail="credit_grant_monthly must be at least 0")
        if "notes" in updates and updates["notes"] is not None:
            updates["note"] = updates["notes"]
        if "note" in updates and updates["note"] is not None:
            updates["notes"] = updates["note"]
        for key, value in updates.items():
            license_record[key] = value
        if updates.get("status") == "active" and not license_record.get("usage_lock_reason"):
            license_record["usage_locked_at"] = ""
        license_record["updated_at"] = _now()
        self._append_audit(
            data,
            "license.update",
            "license",
            license_id,
            before=before,
            after=self._public_license(license_record, data=data),
        )
        self._save(data)
        return self._public_license(license_record, data=data)

    def revoke_license(self, license_id: str) -> dict[str, Any]:
        data = self._load()
        license_record = data["licenses"].get(license_id)
        if not license_record:
            raise HTTPException(status_code=404, detail="license not found")
        before = self._public_license(license_record, data=data)
        license_record["status"] = "disabled"
        license_record["updated_at"] = _now()
        for activation in data["activations"].values():
            if activation.get("license_id") == license_id:
                activation["status"] = "disabled"
        self._append_audit(
            data,
            "license.disable",
            "license",
            license_id,
            before=before,
            after=self._public_license(license_record, data=data),
        )
        self._save(data)
        return self._public_license(license_record, data=data)

    def reset_license_devices(self, license_id: str) -> dict[str, Any]:
        data = self._load()
        license_record = data["licenses"].get(license_id)
        if not license_record:
            raise HTTPException(status_code=404, detail="license not found")
        before = self._public_license(license_record, data=data)
        reset_count = 0
        for activation in data["activations"].values():
            if activation.get("license_id") == license_id and activation.get("status") == "active":
                activation["status"] = "reset"
                activation["reset_at"] = _now()
                reset_count += 1
        license_record["updated_at"] = _now()
        after = self._public_license(license_record, data=data)
        self._append_audit(
            data,
            "license.reset_device",
            "license",
            license_id,
            before=before,
            after={**after, "reset_count": reset_count},
        )
        self._save(data)
        return after

    def restore_paid_license(self, license_id: str, request: LicenseRestorePaidRequest) -> dict[str, Any]:
        data = self._load()
        license_record = data["licenses"].get(license_id)
        if not license_record:
            raise HTTPException(status_code=404, detail="license not found")
        before = self._public_license(license_record, data=data)
        license_record["plan"] = (request.plan or "yearly").strip() or "yearly"
        license_record["status"] = "active"
        license_record["usage_limit_seconds"] = None
        license_record["usage_locked_at"] = ""
        license_record["usage_lock_reason"] = ""
        grant = request.credit_grant if request.credit_grant is not None else _default_credit_grant(license_record["plan"])
        if grant < 0:
            raise HTTPException(status_code=400, detail="credit_grant must be at least 0")
        cycle_starts_at, cycle_ends_at = _credit_cycle_bounds()
        self._ensure_credit_fields(license_record)
        license_record["credit_balance"] = grant
        license_record["credit_grant_monthly"] = grant
        license_record["credit_total_granted"] = self._credit_int(license_record, "credit_total_granted") + grant
        license_record["credit_cycle_starts_at"] = cycle_starts_at
        license_record["credit_cycle_ends_at"] = cycle_ends_at
        license_record["credit_refreshed_at"] = cycle_starts_at
        license_record["credit_locked_at"] = ""
        license_record["credit_lock_reason"] = ""
        license_record["updated_at"] = _now()
        after = self._public_license(license_record, data=data)
        self._append_audit(
            data,
            "license.restore_paid",
            "license",
            license_id,
            before=before,
            after=after,
        )
        self._save(data)
        return after

    def claim_usage(self, request: LicenseUsageClaimRequest) -> dict[str, Any]:
        usage_seconds = int(request.usage_seconds or 0)
        if usage_seconds < 1:
            raise HTTPException(status_code=400, detail="usage_seconds must be at least 1")
        reserve = self.reserve_credits(
            CreditReserveRequest(
                activation_token=request.activation_token,
                machine_id=request.machine_id,
                machine_code=request.machine_code,
                provider="legacy",
                feature=request.feature or "legacy_usage_claim",
                seconds=usage_seconds,
                context=request.context,
            )
        )
        committed = self.commit_credits(
            CreditCommitRequest(
                reservation_id=reserve["reservation_id"],
                actual_seconds=usage_seconds,
                context={"source": "legacy_usage_claim"},
            )
        )
        return {
            "ok": True,
            "allowed": True,
            "license_id": reserve.get("license_id", ""),
            "usage": {
                "limit_seconds": None,
                "used_seconds": None,
                "remaining_seconds": None,
                "locked": False,
            },
            "credits": committed.get("credits", reserve.get("credits", {})),
        }

    def reserve_credits(self, request: CreditReserveRequest) -> dict[str, Any]:
        data = self._load()
        data.setdefault("credit_transactions", {})
        activation, license_record, customer = self._validated_activation_for_credit(data, request)
        self._refresh_yearly_credit_cycle(data, license_record)
        self._ensure_credit_fields(license_record)
        seconds = int(request.seconds or 0)
        if seconds < 1:
            raise HTTPException(status_code=400, detail="seconds must be at least 1")
        credits_needed = self._credits_for_seconds(seconds)
        before = self._public_license(license_record, data=data)
        balance = self._credit_int(license_record, "credit_balance")
        if balance < credits_needed:
            self._handle_insufficient_credits(data, license_record, before=before)
            self._save(data)
            raise HTTPException(status_code=403, detail="license_credit_insufficient")

        reservation_id = f"cr_{uuid4().hex[:12]}"
        license_record["credit_balance"] = balance - credits_needed
        license_record["updated_at"] = _now()
        transaction = {
            "transaction_id": reservation_id,
            "license_id": license_record["license_id"],
            "customer_id": license_record["customer_id"],
            "activation_id": activation.get("activation_id", ""),
            "type": "reserve",
            "status": "reserved",
            "provider": (request.provider or "hifly").strip().lower(),
            "feature": request.feature,
            "seconds": seconds,
            "rate_per_second": CREDIT_RATE_PER_SECOND,
            "provider_cost_per_second": PROVIDER_COST_PER_SECOND,
            "credits_reserved": credits_needed,
            "credits_committed": 0,
            "credits_refunded": 0,
            "task_id": request.task_id,
            "context": self._sanitize_metadata(request.context),
            "created_at": _now(),
            "updated_at": _now(),
        }
        data["credit_transactions"][reservation_id] = transaction
        self._append_audit(
            data,
            "license.credit_reserved",
            "license",
            license_record["license_id"],
            before=before,
            after={**self._public_license(license_record, data=data), "transaction": transaction},
            actor="client",
        )
        self._save(data)
        return {
            "ok": True,
            "reservation_id": reservation_id,
            "license_id": license_record["license_id"],
            "customer_id": customer.get("customer_id", ""),
            "provider": transaction["provider"],
            "feature": request.feature,
            "seconds": seconds,
            "credits_reserved": credits_needed,
            "credit_rate_per_second": CREDIT_RATE_PER_SECOND,
            "provider_cost_credits": seconds * PROVIDER_COST_PER_SECOND,
            "credits": self._credit_snapshot(license_record),
        }

    def commit_credits(self, request: CreditCommitRequest) -> dict[str, Any]:
        data = self._load()
        transactions = data.setdefault("credit_transactions", {})
        transaction = transactions.get(request.reservation_id)
        if not transaction:
            raise HTTPException(status_code=404, detail="credit_reservation_not_found")
        if transaction.get("status") != "reserved":
            raise HTTPException(status_code=409, detail="credit_reservation_not_pending")
        license_record = data["licenses"].get(transaction.get("license_id"))
        if not license_record:
            raise HTTPException(status_code=404, detail="license not found")
        self._ensure_credit_fields(license_record)
        before = self._public_license(license_record, data=data)
        reserved = max(int(transaction.get("credits_reserved") or 0), 0)
        actual_seconds = request.actual_seconds if request.actual_seconds is not None else transaction.get("seconds")
        actual_seconds = max(int(actual_seconds or 0), 1)
        actual_credits = self._credits_for_seconds(actual_seconds)
        if actual_credits > reserved:
            extra = actual_credits - reserved
            balance = self._credit_int(license_record, "credit_balance")
            if balance < extra:
                self._handle_insufficient_credits(data, license_record, before=before)
                self._save(data)
                raise HTTPException(status_code=403, detail="license_credit_insufficient")
            license_record["credit_balance"] = balance - extra
        refunded = max(reserved - actual_credits, 0)
        if refunded:
            license_record["credit_balance"] = self._credit_int(license_record, "credit_balance") + refunded
            license_record["credit_total_refunded"] = self._credit_int(license_record, "credit_total_refunded") + refunded
        license_record["credit_total_used"] = self._credit_int(license_record, "credit_total_used") + actual_credits
        license_record["updated_at"] = _now()
        transaction.update(
            {
                "status": "committed",
                "type": "commit",
                "seconds": actual_seconds,
                "credits_committed": actual_credits,
                "credits_refunded": refunded,
                "task_id": request.task_id or transaction.get("task_id", ""),
                "commit_context": self._sanitize_metadata(request.context),
                "committed_at": _now(),
                "updated_at": _now(),
            }
        )
        if self._is_trial_license(license_record) and self._credit_int(license_record, "credit_balance") <= 0:
            self._lock_credit_license(data, license_record, before=before)
        self._append_audit(
            data,
            "license.credit_committed",
            "license",
            license_record["license_id"],
            before=before,
            after={**self._public_license(license_record, data=data), "transaction": transaction},
            actor="client",
        )
        self._save(data)
        return {
            "ok": True,
            "reservation_id": request.reservation_id,
            "license_id": license_record["license_id"],
            "credits_committed": actual_credits,
            "credits_refunded": refunded,
            "credits": self._credit_snapshot(license_record),
        }

    def refund_credits(self, request: CreditRefundRequest) -> dict[str, Any]:
        data = self._load()
        transactions = data.setdefault("credit_transactions", {})
        transaction = transactions.get(request.reservation_id)
        if not transaction:
            raise HTTPException(status_code=404, detail="credit_reservation_not_found")
        if transaction.get("status") != "reserved":
            raise HTTPException(status_code=409, detail="credit_reservation_not_pending")
        license_record = data["licenses"].get(transaction.get("license_id"))
        if not license_record:
            raise HTTPException(status_code=404, detail="license not found")
        self._ensure_credit_fields(license_record)
        before = self._public_license(license_record, data=data)
        refunded = max(int(transaction.get("credits_reserved") or 0), 0)
        license_record["credit_balance"] = self._credit_int(license_record, "credit_balance") + refunded
        license_record["credit_total_refunded"] = self._credit_int(license_record, "credit_total_refunded") + refunded
        license_record["updated_at"] = _now()
        transaction.update(
            {
                "status": "refunded",
                "type": "refund",
                "credits_refunded": refunded,
                "refund_reason": request.reason,
                "refund_context": self._sanitize_metadata(request.context),
                "refunded_at": _now(),
                "updated_at": _now(),
            }
        )
        self._append_audit(
            data,
            "license.credit_refunded",
            "license",
            license_record["license_id"],
            before=before,
            after={**self._public_license(license_record, data=data), "transaction": transaction},
            actor="client",
        )
        self._save(data)
        return {
            "ok": True,
            "reservation_id": request.reservation_id,
            "license_id": license_record["license_id"],
            "credits_refunded": refunded,
            "credits": self._credit_snapshot(license_record),
        }

    def adjust_license_credits(self, license_id: str, request: AdminCreditAdjustRequest) -> dict[str, Any]:
        data = self._load()
        data.setdefault("credit_transactions", {})
        license_record = data["licenses"].get(license_id)
        if not license_record:
            raise HTTPException(status_code=404, detail="license not found")
        self._ensure_credit_fields(license_record)
        delta = int(request.delta_credits or 0)
        if delta == 0:
            raise HTTPException(status_code=400, detail="delta_credits must not be 0")
        before = self._public_license(license_record, data=data)
        next_balance = self._credit_int(license_record, "credit_balance") + delta
        if next_balance < 0:
            raise HTTPException(status_code=400, detail="credit_balance_cannot_be_negative")
        license_record["credit_balance"] = next_balance
        if delta > 0:
            license_record["credit_total_granted"] = self._credit_int(license_record, "credit_total_granted") + delta
        else:
            license_record["credit_total_used"] = self._credit_int(license_record, "credit_total_used") + abs(delta)
        license_record["updated_at"] = _now()
        transaction_id = f"cr_{uuid4().hex[:12]}"
        transaction = {
            "transaction_id": transaction_id,
            "license_id": license_id,
            "customer_id": license_record.get("customer_id", ""),
            "type": "admin_adjust",
            "status": "committed",
            "delta_credits": delta,
            "reason": request.reason,
            "note": request.note,
            "created_at": _now(),
            "updated_at": _now(),
        }
        data["credit_transactions"][transaction_id] = transaction
        if license_record.get("status") == "disabled" and license_record.get("credit_lock_reason"):
            license_record["status"] = "active"
            license_record["credit_locked_at"] = ""
            license_record["credit_lock_reason"] = ""
        self._append_audit(
            data,
            "license.credit_adjust",
            "license",
            license_id,
            before=before,
            after={**self._public_license(license_record, data=data), "transaction": transaction},
        )
        self._save(data)
        return self._public_license(license_record, data=data)

    def refresh_license_credit_cycle(self, license_id: str) -> dict[str, Any]:
        data = self._load()
        license_record = data["licenses"].get(license_id)
        if not license_record:
            raise HTTPException(status_code=404, detail="license not found")
        before = self._public_license(license_record, data=data)
        refreshed = self._reset_credit_cycle(data, license_record, reason="admin_refresh")
        if not refreshed:
            self._save(data)
            return self._public_license(license_record, data=data)
        self._append_audit(
            data,
            "license.credit_cycle_refresh",
            "license",
            license_id,
            before=before,
            after=self._public_license(license_record, data=data),
        )
        self._save(data)
        return self._public_license(license_record, data=data)

    def list_credit_transactions(self, license_id: str, limit: int = 100) -> list[dict[str, Any]]:
        data = self._load()
        if license_id not in data["licenses"]:
            raise HTTPException(status_code=404, detail="license not found")
        rows = [
            row
            for row in data.get("credit_transactions", {}).values()
            if row.get("license_id") == license_id
        ]
        return sorted(rows, key=lambda row: row.get("created_at", ""), reverse=True)[: max(int(limit or 100), 1)]

    def customer_credit_overview(self, request: CreditTransactionsRequest) -> dict[str, Any]:
        data = self._load()
        activation = self._activation_by_token(data, request.activation_token)
        if not activation:
            raise HTTPException(status_code=401, detail="activation_token_invalid")
        machine_code = request.machine_code_value()
        if machine_code and not self._activation_matches_machine(activation, machine_code):
            raise HTTPException(status_code=403, detail="machine_mismatch")
        if activation.get("status") != "active":
            raise HTTPException(status_code=403, detail="activation_disabled")
        license_record = data["licenses"].get(activation.get("license_id", ""))
        if not license_record:
            raise HTTPException(status_code=404, detail="license not found")
        if str(license_record.get("status") or "") in {"disabled", "revoked", "refunded"}:
            raise HTTPException(status_code=403, detail="license_disabled")
        credits = dict(self._credit_snapshot(license_record))
        credits.pop("remaining_seconds", None)
        rows = [
            row
            for row in data.get("credit_transactions", {}).values()
            if row.get("license_id") == license_record.get("license_id")
        ]
        limit = max(min(int(request.limit or 20), 100), 1)
        return {
            "ok": True,
            "license_id": license_record.get("license_id", ""),
            "plan": license_record.get("plan", ""),
            "credits": credits,
            "transactions": sorted(rows, key=lambda row: row.get("created_at", ""), reverse=True)[:limit],
        }

    def activate(self, request: ActivationRequest) -> dict[str, Any]:
        data = self._load()
        key_hash = _hash_secret(request.license_key.strip())
        license_record = next(
            (item for item in data["licenses"].values() if item.get("key_hash") == key_hash),
            None,
        )
        if not license_record:
            raise HTTPException(status_code=401, detail="license_not_found")
        self._assert_license_usable(license_record)
        customer = data["customers"].get(license_record["customer_id"])
        if not customer or customer.get("status") not in {"active", "trial"}:
            raise HTTPException(status_code=403, detail="customer_disabled")

        machine_code = request.machine_code_value()
        if not machine_code:
            raise HTTPException(status_code=400, detail="machine_code_required")
        machine_hash = _hash_machine_code(machine_code)

        existing = self._find_activation(data, license_record["license_id"], machine_code)
        if existing:
            existing["status"] = "active"
            existing["machine_code_hash"] = existing.get("machine_code_hash") or machine_hash
            existing["device_name"] = request.device_name or existing.get("device_name", "")
            existing["app_version"] = request.app_version
            existing["platform"] = request.platform
            existing["last_seen_at"] = _now()
            license_record["last_heartbeat_at"] = existing["last_seen_at"]
            self._save(data)
            return self._activation_response(existing, license_record, customer, data=data)

        active_machines = {
            row.get("machine_code_hash") or _hash_machine_code(str(row.get("machine_id", "")))
            for row in data["activations"].values()
            if row.get("license_id") == license_record["license_id"] and row.get("status") == "active"
        }
        if len(active_machines) >= self._max_devices(license_record):
            raise HTTPException(status_code=403, detail="device_limit_reached")

        token = "act_" + secrets.token_urlsafe(32)
        activation = ActivationRecord(
            license_id=license_record["license_id"],
            customer_id=license_record["customer_id"],
            machine_code_hash=machine_hash,
            device_name=request.device_name,
            activation_token=token,
            app_version=request.app_version,
            platform=request.platform,
        )
        data["activations"][activation.activation_id] = activation.model_dump(mode="json")
        license_record["last_heartbeat_at"] = data["activations"][activation.activation_id]["last_seen_at"]
        self._append_audit(
            data,
            "activation.create",
            "license",
            license_record["license_id"],
            after=self._public_activation(data["activations"][activation.activation_id]),
            actor="client",
        )
        self._save(data)
        return self._activation_response(data["activations"][activation.activation_id], license_record, customer, data=data)

    def heartbeat(self, request: HeartbeatRequest) -> dict[str, Any]:
        data = self._load()
        activation = self._activation_by_token(data, request.activation_token)
        if not activation:
            raise HTTPException(status_code=401, detail="activation_token_invalid")
        machine_code = request.machine_code_value()
        if machine_code and not self._activation_matches_machine(activation, machine_code):
            raise HTTPException(status_code=403, detail="machine_mismatch")
        license_record = data["licenses"].get(activation["license_id"])
        if not license_record:
            raise HTTPException(status_code=404, detail="license not found")
        self._assert_license_usable(license_record)
        if activation.get("status") != "active":
            raise HTTPException(status_code=403, detail="activation_disabled")
        customer = data["customers"].get(activation["customer_id"], {})
        activation["app_version"] = request.app_version or activation.get("app_version", "")
        activation["platform"] = request.platform or activation.get("platform", "windows")
        activation["last_seen_at"] = _now()
        license_record["last_heartbeat_at"] = activation["last_seen_at"]
        self._save(data)
        return self._activation_response(activation, license_record, customer, current_version=request.app_version, data=data)

    def latest_release(self, channel: str = "stable", platform: str = "windows") -> dict[str, Any] | None:
        data = self._load()
        candidates = [
            item
            for item in data["releases"].values()
            if item.get("status") == "published"
            and item.get("channel", "stable") == channel
            and item.get("platform", "windows") == platform
        ]
        if not candidates:
            return None
        return sorted(candidates, key=lambda row: _parse_version(row.get("version")), reverse=True)[0]

    def update_check(self, channel: str, platform: str, current_version: str = "") -> dict[str, Any]:
        release = self.latest_release(channel=channel, platform=platform)
        if not release:
            return {
                "available": False,
                "force_update": False,
                "current_version": current_version,
                "latest_version": "",
                "message": "no published release",
                "release": None,
            }
        update_available = _parse_version(release.get("version")) > _parse_version(current_version)
        force_update = bool(release.get("force_update"))
        minimum = release.get("min_supported_version") or ""
        if minimum and _parse_version(current_version) < _parse_version(minimum):
            force_update = True
        return {
            "available": update_available,
            "force_update": force_update,
            "current_version": current_version,
            "latest_version": release.get("version"),
            "release": release,
        }

    def create_release(self, request: ReleaseCreateRequest) -> dict[str, Any]:
        data = self._load()
        payload = request.model_dump()
        payload["changelog"] = payload.get("changelog") or payload.get("release_notes") or ""
        payload["release_notes"] = payload.get("release_notes") or payload.get("changelog") or ""
        release = ReleaseRecord(**payload)
        data["releases"][release.release_id] = release.model_dump(mode="json")
        self._append_audit(
            data,
            "release.publish",
            "release",
            release.release_id,
            after=data["releases"][release.release_id],
        )
        self._save(data)
        return data["releases"][release.release_id]

    def list_releases(self) -> list[dict[str, Any]]:
        return sorted(self._load()["releases"].values(), key=lambda row: row.get("created_at", ""), reverse=True)

    def release_download_url(self, filename: str) -> str:
        base = (getattr(self.settings, "commercial_release_public_base_url", "") or "").rstrip("/")
        path = f"/downloads/{filename}"
        return f"{base}{path}" if base else path

    def release_file_path(self, filename: str) -> Path:
        safe = _safe_release_filename(filename)
        path = (self.releases_dir / safe).resolve()
        root = self.releases_dir.resolve()
        if root != path and root not in path.parents:
            raise HTTPException(status_code=400, detail="invalid_release_file")
        return path

    def create_uploaded_release(
        self,
        *,
        version: str,
        channel: str,
        platform: str,
        changelog: str,
        force_update: bool,
        source_path: Path,
        original_filename: str,
    ) -> dict[str, Any]:
        version_text = version.strip()
        if not version_text:
            raise HTTPException(status_code=400, detail="version_required")
        safe_name = _safe_release_filename(original_filename)
        suffix = Path(safe_name).suffix.lower()
        if suffix not in {".zip", ".exe", ".msi", ".7z"}:
            raise HTTPException(status_code=400, detail="unsupported_release_file")
        target_name = f"{version_text.replace('.', '_')}_{uuid4().hex[:8]}_{safe_name}"
        target = self.release_file_path(target_name)
        shutil.move(str(source_path), target)
        sha256 = _sha256_file(target)
        request = ReleaseCreateRequest(
            version=version_text,
            download_url=self.release_download_url(target.name),
            channel=channel or "stable",
            platform=platform or "windows",
            changelog=changelog or "",
            release_notes=changelog or "",
            sha256=sha256,
            force_update=force_update,
        )
        release = self.create_release(request)
        release["size_bytes"] = target.stat().st_size
        data = self._load()
        if release["release_id"] in data["releases"]:
            data["releases"][release["release_id"]]["size_bytes"] = release["size_bytes"]
            self._save(data)
        return release

    def append_log(self, request: ClientLogRequest) -> dict[str, Any]:
        data = self._load()
        activation = self._activation_by_token(data, request.activation_token) if request.activation_token else None
        machine_code = request.machine_id.strip()
        row = {
            "log_id": f"log_{uuid4().hex[:12]}",
            "created_at": _now(),
            "license_id": activation.get("license_id") if activation else "",
            "customer_id": activation.get("customer_id") if activation else "",
            "machine_code_hash": _hash_machine_code(machine_code) if machine_code else activation.get("machine_code_hash", "") if activation else "",
            "level": (request.level or "info").lower()[:20],
            "event_type": (request.event_type or "client_event")[:80],
            "message": request.message[:2000],
            "app_version": request.app_version,
            "metadata": self._sanitize_metadata(request.metadata),
        }
        ensure_dir(self.logs_path.parent)
        with self.logs_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        return {"status": "ok", "log_id": row["log_id"]}

    def list_logs(self, limit: int = 100) -> list[dict[str, Any]]:
        if not self.logs_path.exists():
            return []
        rows: list[dict[str, Any]] = []
        try:
            lines = self.logs_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            return []
        for line in lines[-max(limit, 1) :]:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                rows.append(item)
        return list(reversed(rows))

    def list_audit_logs(self, limit: int = 100) -> list[dict[str, Any]]:
        data = self._load()
        rows = data.get("audit_logs", [])
        if not isinstance(rows, list):
            return []
        return list(reversed(rows[-max(limit, 1) :]))

    def _activation_response(
        self,
        activation: dict[str, Any],
        license_record: dict[str, Any],
        customer: dict[str, Any],
        *,
        current_version: str = "",
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        public_license = self._public_license(license_record, data=data)
        public_activation = self._public_activation(activation)
        return {
            "ok": True,
            "valid": True,
            "license_id": license_record.get("license_id"),
            "customer_name": customer.get("name"),
            "plan": license_record.get("plan"),
            "expires_at": license_record.get("expires_at"),
            "features": self._feature_flags(license_record),
            "heartbeat_interval_seconds": 3600,
            "activation": {
                **public_activation,
                "activation_token": activation.get("activation_token"),
            },
            "license": public_license,
            "customer": {
                "customer_id": customer.get("customer_id"),
                "name": customer.get("name"),
                "phone": customer.get("phone", ""),
                "email": customer.get("email", ""),
                "wechat": customer.get("wechat", ""),
                "company": customer.get("company", ""),
                "status": customer.get("status", ""),
            },
            "update": self.update_check(
                channel="stable",
                platform=activation.get("platform", "windows"),
                current_version=current_version or activation.get("app_version", ""),
            ),
        }

    def _public_license(self, license_record: dict[str, Any], data: dict[str, Any] | None = None) -> dict[str, Any]:
        public = dict(license_record)
        public.pop("key_hash", None)
        public["max_devices"] = self._max_devices(license_record)
        public["seats"] = public["max_devices"]
        public["feature_flags"] = self._feature_flags(license_record)
        public["features"] = public["feature_flags"]
        public["notes"] = public.get("notes") or public.get("note") or ""
        public["note"] = public["notes"]
        public["usage_limit_seconds"] = self._usage_limit_seconds(license_record)
        public["usage_used_seconds"] = self._usage_used_seconds(license_record)
        public["usage_locked_at"] = str(license_record.get("usage_locked_at") or "")
        public["usage_lock_reason"] = str(license_record.get("usage_lock_reason") or "")
        public["usage"] = self._usage_snapshot(license_record)
        public["credit_rate_per_second"] = CREDIT_RATE_PER_SECOND
        public["credit_balance"] = self._credit_int(license_record, "credit_balance")
        public["credit_grant_monthly"] = self._credit_int(license_record, "credit_grant_monthly")
        public["credit_total_granted"] = self._credit_int(license_record, "credit_total_granted")
        public["credit_total_used"] = self._credit_int(license_record, "credit_total_used")
        public["credit_total_refunded"] = self._credit_int(license_record, "credit_total_refunded")
        public["credit_cycle_starts_at"] = str(license_record.get("credit_cycle_starts_at") or "")
        public["credit_cycle_ends_at"] = str(license_record.get("credit_cycle_ends_at") or "")
        public["credit_locked_at"] = str(license_record.get("credit_locked_at") or "")
        public["credit_lock_reason"] = str(license_record.get("credit_lock_reason") or "")
        public["credits"] = self._credit_snapshot(license_record)
        if data:
            activations = [
                row
                for row in data["activations"].values()
                if row.get("license_id") == license_record.get("license_id") and row.get("status") == "active"
            ]
            public["devices"] = [self._public_activation(row) for row in activations]
            public["bound_devices"] = len(
                {row.get("machine_code_hash") or _hash_machine_code(str(row.get("machine_id", ""))) for row in activations}
            )
            public["activated_devices"] = public["bound_devices"]
        return public

    def _assert_license_usable(self, license_record: dict[str, Any]) -> None:
        if str(license_record.get("credit_lock_reason") or ""):
            raise HTTPException(status_code=403, detail="license_credit_insufficient")
        if self._usage_lock_reason(license_record) == "trial_usage_limit_reached" or self._usage_limit_reached(license_record):
            raise HTTPException(status_code=403, detail="license_usage_limit_reached")
        status = license_record.get("status")
        if status in {"disabled", "revoked", "refunded"}:
            raise HTTPException(status_code=403, detail="license_disabled")
        if status == "expired":
            raise HTTPException(status_code=403, detail="license_expired")
        if status != "active":
            raise HTTPException(status_code=403, detail="license_disabled")
        expires_at = license_record.get("expires_at")
        if expires_at:
            try:
                expires = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            except ValueError:
                expires = None
            if expires and expires < datetime.now(timezone.utc):
                raise HTTPException(status_code=403, detail="license_expired")

    def _usage_limit_seconds(self, license_record: dict[str, Any]) -> int | None:
        value = license_record.get("usage_limit_seconds")
        if value in {None, ""}:
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    def _usage_used_seconds(self, license_record: dict[str, Any]) -> int:
        try:
            return max(int(license_record.get("usage_used_seconds") or 0), 0)
        except (TypeError, ValueError):
            return 0

    def _usage_lock_reason(self, license_record: dict[str, Any]) -> str:
        return str(license_record.get("usage_lock_reason") or "")

    def _usage_limit_reached(self, license_record: dict[str, Any]) -> bool:
        limit_seconds = self._usage_limit_seconds(license_record)
        return limit_seconds is not None and self._usage_used_seconds(license_record) >= limit_seconds

    def _usage_snapshot(self, license_record: dict[str, Any]) -> dict[str, Any]:
        limit_seconds = self._usage_limit_seconds(license_record)
        used_seconds = self._usage_used_seconds(license_record)
        remaining_seconds = None if limit_seconds is None else max(limit_seconds - used_seconds, 0)
        return {
            "limit_seconds": limit_seconds,
            "used_seconds": used_seconds,
            "remaining_seconds": remaining_seconds,
            "locked": bool(self._usage_lock_reason(license_record)) or (
                limit_seconds is not None and used_seconds >= limit_seconds
            ),
            "locked_at": str(license_record.get("usage_locked_at") or ""),
            "lock_reason": self._usage_lock_reason(license_record),
        }

    def _credit_int(self, license_record: dict[str, Any], key: str) -> int:
        try:
            return max(int(license_record.get(key) or 0), 0)
        except (TypeError, ValueError):
            return 0

    def _ensure_credit_fields(self, license_record: dict[str, Any]) -> None:
        grant = self._credit_int(license_record, "credit_grant_monthly") or _default_credit_grant(str(license_record.get("plan") or ""))
        if "credit_rate_per_second" not in license_record:
            license_record["credit_rate_per_second"] = CREDIT_RATE_PER_SECOND
        if "credit_balance" not in license_record:
            license_record["credit_balance"] = grant
        if "credit_grant_monthly" not in license_record:
            license_record["credit_grant_monthly"] = grant
        if "credit_total_granted" not in license_record:
            license_record["credit_total_granted"] = self._credit_int(license_record, "credit_balance")
        for key in ("credit_total_used", "credit_total_refunded"):
            license_record.setdefault(key, 0)
        cycle_starts_at = str(license_record.get("credit_cycle_starts_at") or "")
        cycle_ends_at = str(license_record.get("credit_cycle_ends_at") or "")
        if not cycle_starts_at or not cycle_ends_at:
            cycle_starts_at, cycle_ends_at = _credit_cycle_bounds()
            license_record["credit_cycle_starts_at"] = cycle_starts_at
            license_record["credit_cycle_ends_at"] = cycle_ends_at
        license_record.setdefault("credit_refreshed_at", cycle_starts_at)
        license_record.setdefault("credit_locked_at", "")
        license_record.setdefault("credit_lock_reason", "")

    def _credit_snapshot(self, license_record: dict[str, Any]) -> dict[str, Any]:
        self._ensure_credit_fields(license_record)
        balance = self._credit_int(license_record, "credit_balance")
        return {
            "balance": balance,
            "grant_monthly": self._credit_int(license_record, "credit_grant_monthly"),
            "rate_per_second": CREDIT_RATE_PER_SECOND,
            "provider_cost_per_second": PROVIDER_COST_PER_SECOND,
            "remaining_seconds": balance // CREDIT_RATE_PER_SECOND if CREDIT_RATE_PER_SECOND else 0,
            "total_granted": self._credit_int(license_record, "credit_total_granted"),
            "total_used": self._credit_int(license_record, "credit_total_used"),
            "total_refunded": self._credit_int(license_record, "credit_total_refunded"),
            "cycle_starts_at": str(license_record.get("credit_cycle_starts_at") or ""),
            "cycle_ends_at": str(license_record.get("credit_cycle_ends_at") or ""),
            "locked": bool(license_record.get("credit_lock_reason")),
            "locked_at": str(license_record.get("credit_locked_at") or ""),
            "lock_reason": str(license_record.get("credit_lock_reason") or ""),
        }

    def _credits_for_seconds(self, seconds: int) -> int:
        return max(int(seconds or 0), 1) * CREDIT_RATE_PER_SECOND

    def _is_trial_license(self, license_record: dict[str, Any]) -> bool:
        return str(license_record.get("plan") or "").strip().lower() == "trial"

    def _validated_activation_for_credit(
        self,
        data: dict[str, Any],
        request: CreditReserveRequest,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        activation = self._activation_by_token(data, request.activation_token)
        if not activation:
            raise HTTPException(status_code=401, detail="activation_token_invalid")
        machine_code = request.machine_code_value()
        if machine_code and not self._activation_matches_machine(activation, machine_code):
            raise HTTPException(status_code=403, detail="machine_mismatch")
        license_record = data["licenses"].get(activation["license_id"])
        if not license_record:
            raise HTTPException(status_code=404, detail="license not found")
        self._assert_license_usable(license_record)
        if activation.get("status") != "active":
            raise HTTPException(status_code=403, detail="activation_disabled")
        customer = data["customers"].get(activation["customer_id"], {})
        if customer and customer.get("status") not in {"active", "trial"}:
            raise HTTPException(status_code=403, detail="customer_disabled")
        return activation, license_record, customer

    def _handle_insufficient_credits(
        self,
        data: dict[str, Any],
        license_record: dict[str, Any],
        *,
        before: dict[str, Any],
    ) -> None:
        if self._is_trial_license(license_record):
            self._lock_credit_license(data, license_record, before=before)
        self._append_audit(
            data,
            "license.credit_insufficient",
            "license",
            license_record["license_id"],
            before=before,
            after=self._public_license(license_record, data=data),
            actor="client",
        )

    def _lock_credit_license(
        self,
        data: dict[str, Any],
        license_record: dict[str, Any],
        *,
        before: dict[str, Any] | None = None,
    ) -> None:
        if str(license_record.get("credit_lock_reason") or ""):
            return
        license_record["status"] = "disabled"
        license_record["credit_locked_at"] = _now()
        license_record["credit_lock_reason"] = "trial_credit_exhausted"
        license_record["updated_at"] = _now()
        self._append_audit(
            data,
            "license.credit_locked",
            "license",
            license_record["license_id"],
            before=before or self._public_license(license_record, data=data),
            after=self._public_license(license_record, data=data),
            actor="system",
        )

    def _refresh_yearly_credit_cycle(self, data: dict[str, Any], license_record: dict[str, Any]) -> bool:
        if str(license_record.get("plan") or "").strip().lower() != "yearly":
            self._ensure_credit_fields(license_record)
            return False
        self._ensure_credit_fields(license_record)
        cycle_end = _parse_iso_datetime(str(license_record.get("credit_cycle_ends_at") or ""))
        if not cycle_end or cycle_end > datetime.now(timezone.utc):
            return False
        return self._reset_credit_cycle(data, license_record, reason="yearly_monthly_refresh")

    def _reset_credit_cycle(self, data: dict[str, Any], license_record: dict[str, Any], *, reason: str) -> bool:
        self._ensure_credit_fields(license_record)
        grant = self._credit_int(license_record, "credit_grant_monthly") or _default_credit_grant(str(license_record.get("plan") or ""))
        if grant <= 0:
            return False
        before_balance = self._credit_int(license_record, "credit_balance")
        cycle_starts_at, cycle_ends_at = _credit_cycle_bounds()
        license_record["credit_balance"] = grant
        license_record["credit_total_granted"] = self._credit_int(license_record, "credit_total_granted") + grant
        license_record["credit_cycle_starts_at"] = cycle_starts_at
        license_record["credit_cycle_ends_at"] = cycle_ends_at
        license_record["credit_refreshed_at"] = cycle_starts_at
        license_record["updated_at"] = _now()
        transaction_id = f"cr_{uuid4().hex[:12]}"
        data.setdefault("credit_transactions", {})[transaction_id] = {
            "transaction_id": transaction_id,
            "license_id": license_record.get("license_id", ""),
            "customer_id": license_record.get("customer_id", ""),
            "type": "cycle_refresh",
            "status": "committed",
            "reason": reason,
            "previous_balance": before_balance,
            "credit_balance": grant,
            "delta_credits": grant,
            "created_at": _now(),
            "updated_at": _now(),
        }
        return True

    def _lock_usage_license(
        self,
        data: dict[str, Any],
        license_record: dict[str, Any],
        *,
        before: dict[str, Any] | None = None,
    ) -> None:
        if self._usage_lock_reason(license_record) == "trial_usage_limit_reached":
            return
        limit_seconds = self._usage_limit_seconds(license_record)
        if limit_seconds is not None:
            license_record["usage_used_seconds"] = min(max(self._usage_used_seconds(license_record), limit_seconds), limit_seconds)
        license_record["status"] = "disabled"
        license_record["usage_locked_at"] = _now()
        license_record["usage_lock_reason"] = "trial_usage_limit_reached"
        license_record["updated_at"] = _now()
        self._append_audit(
            data,
            "license.usage_locked",
            "license",
            license_record["license_id"],
            before=before or self._public_license(license_record, data=data),
            after=self._public_license(license_record, data=data),
            actor="system",
        )

    def _find_activation(self, data: dict[str, Any], license_id: str, machine_code: str) -> dict[str, Any] | None:
        for row in data["activations"].values():
            if row.get("license_id") == license_id and self._activation_matches_machine(row, machine_code):
                return row
        return None

    def _activation_by_token(self, data: dict[str, Any], token: str) -> dict[str, Any] | None:
        for row in data["activations"].values():
            if row.get("activation_token") == token:
                return row
        return None

    def _activation_matches_machine(self, activation: dict[str, Any], machine_code: str) -> bool:
        machine_hash = _hash_machine_code(machine_code)
        if activation.get("machine_code_hash"):
            return activation.get("machine_code_hash") == machine_hash
        return activation.get("machine_id") == machine_code

    def _public_activation(self, activation: dict[str, Any]) -> dict[str, Any]:
        machine_hash = activation.get("machine_code_hash")
        if not machine_hash and activation.get("machine_id"):
            machine_hash = _hash_machine_code(str(activation.get("machine_id")))
        return {
            "activation_id": activation.get("activation_id"),
            "machine_id": machine_hash[:16] if machine_hash else "",
            "machine_code_hash": machine_hash[:16] if machine_hash else "",
            "device_name": activation.get("device_name", ""),
            "status": activation.get("status", ""),
            "app_version": activation.get("app_version", ""),
            "platform": activation.get("platform", "windows"),
            "activated_at": activation.get("activated_at", ""),
            "last_seen_at": activation.get("last_seen_at", ""),
        }

    def _max_devices(self, license_record: dict[str, Any]) -> int:
        value = license_record.get("max_devices", license_record.get("seats", 1))
        try:
            return max(int(value), 1)
        except (TypeError, ValueError):
            return 1

    def _feature_flags(self, license_record: dict[str, Any]) -> list[str]:
        value = license_record.get("feature_flags")
        if value is None:
            value = license_record.get("features", [])
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if str(item).strip()]

    def _append_audit(
        self,
        data: dict[str, Any],
        action: str,
        target_type: str,
        target_id: str,
        *,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        actor: str = "admin",
    ) -> None:
        logs = data.setdefault("audit_logs", [])
        if not isinstance(logs, list):
            data["audit_logs"] = logs = []
        logs.append(
            {
                "audit_id": f"audit_{uuid4().hex[:12]}",
                "created_at": _now(),
                "actor": actor,
                "action": action,
                "target_type": target_type,
                "target_id": target_id,
                "before": before or {},
                "after": after or {},
            }
        )
        if len(logs) > 5000:
            del logs[:-5000]

    def _sanitize_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        blocked = {"password", "token", "secret", "api_key", "apikey", "authorization", "license_key"}
        clean: dict[str, Any] = {}
        for key, value in metadata.items():
            key_text = str(key)
            if key_text.lower() in blocked:
                clean[key_text] = "[redacted]"
            else:
                clean[key_text] = value
        return clean


class PostgresCommercialCenterStore(CommercialCenterStore):
    backend_name = "postgresql"
    tables: ClassVar[list[str]] = [
        "commercial_customers",
        "commercial_licenses",
        "commercial_activations",
        "commercial_releases",
        "commercial_orders",
        "commercial_manual_payment_evidence",
        "commercial_audit_logs",
        "commercial_client_logs",
        "commercial_backups",
    ]

    def __init__(self, settings: Settings):
        super().__init__(settings)
        self.database_url = getattr(settings, "commercial_database_url", None) or getattr(settings, "database_url", None)

    def readiness(self) -> dict[str, Any]:
        driver_available = self._driver_available()
        return {
            "backend": self.backend_name,
            "ready": bool(self.database_url and driver_available),
            "database_url_configured": bool(self.database_url),
            "driver_available": driver_available,
            "tables": list(self.tables),
        }

    def _driver_available(self) -> bool:
        try:
            import psycopg  # noqa: F401
        except Exception:
            return False
        return True

    def _connect(self):
        if not self.database_url:
            raise HTTPException(status_code=503, detail="commercial_database_url_missing")
        try:
            import psycopg
        except Exception as exc:
            raise HTTPException(status_code=503, detail="postgres_driver_missing") from exc
        return psycopg.connect(self.database_url)

    def _ensure_schema(self, conn) -> None:
        for table in self.tables:
            if table in {"commercial_audit_logs", "commercial_client_logs", "commercial_backups"}:
                id_column = "id"
            elif table == "commercial_customers":
                id_column = "customer_id"
            elif table == "commercial_licenses":
                id_column = "license_id"
            elif table == "commercial_activations":
                id_column = "activation_id"
            elif table == "commercial_releases":
                id_column = "release_id"
            elif table == "commercial_orders":
                id_column = "order_id"
            elif table == "commercial_manual_payment_evidence":
                id_column = "evidence_id"
            else:
                id_column = "id"
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {table} (
                    {id_column} TEXT PRIMARY KEY,
                    payload JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
        conn.commit()

    def _select_payloads(self, conn, table: str) -> list[dict[str, Any]]:
        cursor = conn.execute(f"SELECT payload FROM {table}")
        rows = []
        for row in cursor.fetchall():
            payload = row[0]
            if isinstance(payload, dict):
                rows.append(payload)
        return rows

    def _load(self) -> dict[str, Any]:
        with self._connect() as conn:
            self._ensure_schema(conn)
            data = self._default_data()
            data["customers"] = {row["customer_id"]: row for row in self._select_payloads(conn, "commercial_customers")}
            data["licenses"] = {row["license_id"]: row for row in self._select_payloads(conn, "commercial_licenses")}
            data["activations"] = {
                row["activation_id"]: row for row in self._select_payloads(conn, "commercial_activations")
            }
            data["releases"] = {row["release_id"]: row for row in self._select_payloads(conn, "commercial_releases")}
            data["orders"] = {row["order_id"]: row for row in self._select_payloads(conn, "commercial_orders")}
            data["manual_payment_evidence"] = {
                row["evidence_id"]: row for row in self._select_payloads(conn, "commercial_manual_payment_evidence")
            }
            data["audit_logs"] = self._select_payloads(conn, "commercial_audit_logs")
            return data

    def _upsert_payloads(self, conn, table: str, id_key: str, rows: list[dict[str, Any]]) -> None:
        from psycopg.types.json import Jsonb

        ids = [str(row.get(id_key) or row.get("audit_id") or row.get("log_id") or row.get("backup_id") or uuid4().hex) for row in rows]
        if ids:
            placeholders = ",".join(["%s"] * len(ids))
            conn.execute(f"DELETE FROM {table} WHERE {id_key} NOT IN ({placeholders})", ids)
        else:
            conn.execute(f"DELETE FROM {table}")
        for row, row_id in zip(rows, ids):
            conn.execute(
                f"""
                INSERT INTO {table} ({id_key}, payload, updated_at)
                VALUES (%s, %s, now())
                ON CONFLICT ({id_key}) DO UPDATE SET payload = EXCLUDED.payload, updated_at = now()
                """,
                (row_id, Jsonb(row)),
            )

    def _save(self, data: dict[str, Any]) -> None:
        with self._connect() as conn:
            self._ensure_schema(conn)
            self._upsert_payloads(conn, "commercial_customers", "customer_id", list(data["customers"].values()))
            self._upsert_payloads(conn, "commercial_licenses", "license_id", list(data["licenses"].values()))
            self._upsert_payloads(conn, "commercial_activations", "activation_id", list(data["activations"].values()))
            self._upsert_payloads(conn, "commercial_releases", "release_id", list(data["releases"].values()))
            self._upsert_payloads(conn, "commercial_orders", "order_id", list(data["orders"].values()))
            self._upsert_payloads(
                conn,
                "commercial_manual_payment_evidence",
                "evidence_id",
                list(data["manual_payment_evidence"].values()),
            )
            self._upsert_payloads(conn, "commercial_audit_logs", "id", list(data.get("audit_logs", [])))
            conn.commit()

    def _load_backup_records(self) -> list[dict[str, Any]]:
        if not self.readiness()["ready"]:
            return []
        with self._connect() as conn:
            self._ensure_schema(conn)
            return self._select_payloads(conn, "commercial_backups")

    def _save_backup_records(self, rows: list[dict[str, Any]]) -> None:
        if not self.readiness()["ready"]:
            return
        with self._connect() as conn:
            self._ensure_schema(conn)
            self._upsert_payloads(conn, "commercial_backups", "id", rows)
            conn.commit()

    def run_backup(self) -> dict[str, Any]:
        record = BackupRecord(
            backend=self.backend_name,
            filename="pg_dump_required_on_server",
            status="pending_external_dump",
            message="Run pg_dump -Fc on the server backup job for a complete PostgreSQL backup.",
        ).model_dump(mode="json")
        rows = self._load_backup_records()
        rows.append(record)
        self._save_backup_records(rows)
        return {"ok": True, "backup": record}


def get_commercial_store(settings: Settings = Depends(get_settings)) -> CommercialCenterStore:
    return CommercialCenterStore.from_settings(settings)


def _admin_session_secret(settings: Settings) -> bytes:
    username = getattr(settings, "commercial_admin_username", "admin") or "admin"
    configured = getattr(settings, "commercial_admin_session_secret", "") or ""
    password_hash = getattr(settings, "commercial_admin_password_hash", "") or ""
    legacy_password = getattr(settings, "commercial_admin_password", "") or ""
    material = configured or password_hash or legacy_password
    return hashlib.sha256(f"aivo-admin-session:{username}:{material}".encode("utf-8")).digest()


def _admin_password_configured(settings: Settings) -> bool:
    return bool((getattr(settings, "commercial_admin_password_hash", "") or "").strip()) or bool(
        (getattr(settings, "commercial_admin_password", "") or "").strip()
    )


def _verify_admin_password(settings: Settings, password: str) -> bool:
    password_hash = (getattr(settings, "commercial_admin_password_hash", "") or "").strip()
    if password_hash:
        return _verify_password_hash(password, password_hash)
    legacy_password = getattr(settings, "commercial_admin_password", "") or ""
    return bool(legacy_password) and hmac.compare_digest(password, legacy_password)


def _issue_admin_session(settings: Settings) -> tuple[str, int]:
    username = (getattr(settings, "commercial_admin_username", "admin") or "admin").strip()
    ttl = max(300, int(getattr(settings, "commercial_admin_session_ttl_seconds", 86400) or 86400))
    expires_at = int(time.time()) + ttl
    nonce = secrets.token_urlsafe(18)
    payload = f"{username}|{expires_at}|{nonce}"
    encoded = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")
    signature = hmac.new(_admin_session_secret(settings), encoded.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}", ttl


def _verify_admin_session(settings: Settings, token: str) -> bool:
    try:
        encoded, signature = token.split(".", 1)
    except ValueError:
        return False
    expected = hmac.new(_admin_session_secret(settings), encoded.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return False
    try:
        padded = encoded + "=" * (-len(encoded) % 4)
        payload = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        username, expires_at_text, _nonce = payload.split("|", 2)
        expires_at = int(expires_at_text)
    except Exception:
        return False
    expected_username = (getattr(settings, "commercial_admin_username", "admin") or "admin").strip()
    return bool(username) and hmac.compare_digest(username, expected_username) and expires_at >= int(time.time())


def require_admin_access(
    aivo_admin_session: str | None = Cookie(default=None, alias=ADMIN_SESSION_COOKIE),
    settings: Settings = Depends(get_settings),
) -> None:
    if not _admin_password_configured(settings) and not _is_production(settings):
        return
    if aivo_admin_session and _verify_admin_session(settings, aivo_admin_session):
        return
    raise HTTPException(status_code=401, detail="admin login required")


router = APIRouter()


@router.get("/admin", response_class=HTMLResponse)
def commercial_admin_home() -> HTMLResponse:
    return HTMLResponse((STATIC_DIR / "commercial_admin.html").read_text(encoding="utf-8"))


@router.post("/admin/api/login")
def commercial_admin_login(
    request: AdminLoginRequest,
    response: Response,
    http_request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _rate_limit(
        http_request,
        settings,
        bucket="admin_login",
        per_minute=int(getattr(settings, "commercial_login_rate_limit_per_minute", 5) or 5),
    )
    expected_username = (getattr(settings, "commercial_admin_username", "admin") or "admin").strip()
    username_ok = hmac.compare_digest(request.username.strip(), expected_username)
    password_ok = _verify_admin_password(settings, request.password)
    if not _admin_password_configured(settings) or not username_ok or not password_ok:
        raise HTTPException(status_code=401, detail="admin login failed")
    token, ttl = _issue_admin_session(settings)
    response.set_cookie(
        ADMIN_SESSION_COOKIE,
        token,
        max_age=ttl,
        httponly=True,
        secure=bool(getattr(settings, "commercial_admin_cookie_secure", True) and _is_production(settings)),
        samesite="lax",
        path="/",
    )
    return {"ok": True, "expires_in": ttl, "username": expected_username}


@router.post("/admin/api/logout")
def commercial_admin_logout(response: Response) -> dict[str, bool]:
    response.delete_cookie(ADMIN_SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/admin/api/me", dependencies=[Depends(require_admin_access)])
def commercial_admin_me(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    return {"ok": True, "username": getattr(settings, "commercial_admin_username", "admin") or "admin"}


@router.get("/activate", response_class=HTMLResponse)
def commercial_activation_home() -> HTMLResponse:
    return HTMLResponse((STATIC_DIR / "commercial_activate.html").read_text(encoding="utf-8"))


@router.get("/shop", response_class=HTMLResponse)
def commercial_shop_home() -> HTMLResponse:
    return HTMLResponse((STATIC_DIR / "commercial_shop.html").read_text(encoding="utf-8"))


@router.get("/shop/plans")
def shop_plans(store: CommercialCenterStore = Depends(get_commercial_store)) -> dict[str, Any]:
    return store.shop_plans()


@router.post("/shop/orders")
def create_shop_order(
    request: ShopOrderCreateRequest,
    http_request: Request,
    settings: Settings = Depends(get_settings),
    store: CommercialCenterStore = Depends(get_commercial_store),
) -> dict[str, Any]:
    _rate_limit(
        http_request,
        settings,
        bucket="shop_orders",
        per_minute=int(getattr(settings, "commercial_api_rate_limit_per_minute", 60) or 60),
    )
    return store.create_shop_order(request)


@router.get("/shop/orders/{order_no}")
def get_shop_order(
    order_no: str,
    access_token: str = "",
    store: CommercialCenterStore = Depends(get_commercial_store),
) -> dict[str, Any]:
    return store.get_order_by_no(order_no, access_token=access_token)


@router.post("/shop/orders/{order_no}/evidence")
async def upload_shop_order_evidence(
    order_no: str,
    http_request: Request,
    access_token: str = "",
    payment_note: str = Form(""),
    payment_time: str = Form(""),
    file: UploadFile | None = File(None),
    settings: Settings = Depends(get_settings),
    store: CommercialCenterStore = Depends(get_commercial_store),
) -> dict[str, Any]:
    _rate_limit(
        http_request,
        settings,
        bucket="shop_evidence",
        per_minute=int(getattr(settings, "commercial_api_rate_limit_per_minute", 60) or 60),
    )
    payload = b""
    filename = ""
    content_type = ""
    if file is not None:
        filename = file.filename or "payment-evidence"
        content_type = file.content_type or ""
        payload = await _read_limited_upload(file, PAYMENT_EVIDENCE_MAX_BYTES)
    return store.save_payment_evidence(
        order_no=order_no,
        access_token=access_token,
        payment_note=payment_note,
        payment_time=payment_time,
        original_filename=filename,
        content_type=content_type,
        payload=payload,
    )


@router.get("/admin/api/summary", dependencies=[Depends(require_admin_access)])
def commercial_summary(store: CommercialCenterStore = Depends(get_commercial_store)) -> dict[str, Any]:
    return store.summary()


@router.get("/admin/api/health", dependencies=[Depends(require_admin_access)])
def commercial_admin_health(store: CommercialCenterStore = Depends(get_commercial_store)) -> dict[str, Any]:
    return store.health()


@router.get("/admin/api/backups", dependencies=[Depends(require_admin_access)])
def commercial_list_backups(store: CommercialCenterStore = Depends(get_commercial_store)) -> dict[str, Any]:
    return store.list_backups()


@router.post("/admin/api/backups/run", dependencies=[Depends(require_admin_access)])
def commercial_run_backup(store: CommercialCenterStore = Depends(get_commercial_store)) -> dict[str, Any]:
    return store.run_backup()


@router.get("/admin/api/orders", dependencies=[Depends(require_admin_access)])
def list_admin_orders(
    status: str = "",
    store: CommercialCenterStore = Depends(get_commercial_store),
) -> list[dict[str, Any]]:
    return store.list_orders(status=status)


@router.post("/admin/api/orders/{order_id}/confirm-payment", dependencies=[Depends(require_admin_access)])
def confirm_admin_order_payment(
    order_id: str,
    request: OrderAdminActionRequest,
    store: CommercialCenterStore = Depends(get_commercial_store),
) -> dict[str, Any]:
    return store.confirm_order_payment(order_id, request)


@router.post("/admin/api/orders/{order_id}/reject", dependencies=[Depends(require_admin_access)])
def reject_admin_order(
    order_id: str,
    request: OrderAdminActionRequest,
    store: CommercialCenterStore = Depends(get_commercial_store),
) -> dict[str, Any]:
    return store.reject_order(order_id, request)


@router.post("/admin/api/orders/{order_id}/request-evidence", dependencies=[Depends(require_admin_access)])
def request_admin_order_evidence(
    order_id: str,
    request: OrderAdminActionRequest,
    store: CommercialCenterStore = Depends(get_commercial_store),
) -> dict[str, Any]:
    return store.request_order_evidence(order_id, request)


@router.post("/admin/api/orders/{order_id}/retry-fulfillment", dependencies=[Depends(require_admin_access)])
def retry_admin_order_fulfillment(
    order_id: str,
    request: OrderAdminActionRequest,
    store: CommercialCenterStore = Depends(get_commercial_store),
) -> dict[str, Any]:
    return store.retry_order_fulfillment(order_id, request)


@router.get("/admin/api/customers", dependencies=[Depends(require_admin_access)])
def list_customers(
    q: str = "",
    status: str = "",
    store: CommercialCenterStore = Depends(get_commercial_store),
) -> list[dict[str, Any]]:
    return store.list_customers(q=q, status=status)


@router.post("/admin/api/customers", dependencies=[Depends(require_admin_access)])
def create_customer(
    request: CustomerCreateRequest,
    store: CommercialCenterStore = Depends(get_commercial_store),
) -> dict[str, Any]:
    return store.create_customer(request)


@router.patch("/admin/api/customers/{customer_id}", dependencies=[Depends(require_admin_access)])
def update_customer(
    customer_id: str,
    request: CustomerUpdateRequest,
    store: CommercialCenterStore = Depends(get_commercial_store),
) -> dict[str, Any]:
    return store.update_customer(customer_id, request)


@router.delete("/admin/api/customers/{customer_id}", dependencies=[Depends(require_admin_access)])
def delete_customer(
    customer_id: str,
    store: CommercialCenterStore = Depends(get_commercial_store),
) -> dict[str, Any]:
    return store.delete_customer(customer_id)


@router.get("/admin/api/licenses", dependencies=[Depends(require_admin_access)])
def list_licenses(store: CommercialCenterStore = Depends(get_commercial_store)) -> list[dict[str, Any]]:
    return store.list_licenses()


@router.post("/admin/api/licenses", dependencies=[Depends(require_admin_access)])
def create_license(
    request: LicenseCreateRequest,
    store: CommercialCenterStore = Depends(get_commercial_store),
) -> LicenseCreateResponse:
    return store.create_license(request)


@router.patch("/admin/api/licenses/{license_id}", dependencies=[Depends(require_admin_access)])
def update_license(
    license_id: str,
    request: LicenseUpdateRequest,
    store: CommercialCenterStore = Depends(get_commercial_store),
) -> dict[str, Any]:
    return store.update_license(license_id, request)


@router.post("/admin/api/licenses/{license_id}/revoke", dependencies=[Depends(require_admin_access)])
def revoke_license(
    license_id: str,
    store: CommercialCenterStore = Depends(get_commercial_store),
) -> dict[str, Any]:
    return store.revoke_license(license_id)


@router.post("/admin/api/licenses/{license_id}/reset-device", dependencies=[Depends(require_admin_access)])
def reset_license_devices(
    license_id: str,
    store: CommercialCenterStore = Depends(get_commercial_store),
) -> dict[str, Any]:
    return store.reset_license_devices(license_id)


@router.post("/admin/api/licenses/{license_id}/restore-paid", dependencies=[Depends(require_admin_access)])
def restore_paid_license(
    license_id: str,
    request: LicenseRestorePaidRequest,
    store: CommercialCenterStore = Depends(get_commercial_store),
) -> dict[str, Any]:
    return store.restore_paid_license(license_id, request)


@router.post("/admin/api/licenses/{license_id}/credits/adjust", dependencies=[Depends(require_admin_access)])
def adjust_license_credits(
    license_id: str,
    request: AdminCreditAdjustRequest,
    store: CommercialCenterStore = Depends(get_commercial_store),
) -> dict[str, Any]:
    return store.adjust_license_credits(license_id, request)


@router.post("/admin/api/licenses/{license_id}/credits/refresh-cycle", dependencies=[Depends(require_admin_access)])
def refresh_license_credit_cycle(
    license_id: str,
    store: CommercialCenterStore = Depends(get_commercial_store),
) -> dict[str, Any]:
    return store.refresh_license_credit_cycle(license_id)


@router.get("/admin/api/licenses/{license_id}/credits/transactions", dependencies=[Depends(require_admin_access)])
def list_license_credit_transactions(
    license_id: str,
    limit: int = 100,
    store: CommercialCenterStore = Depends(get_commercial_store),
) -> list[dict[str, Any]]:
    return store.list_credit_transactions(license_id, limit=limit)


@router.get("/admin/api/releases", dependencies=[Depends(require_admin_access)])
def list_releases(store: CommercialCenterStore = Depends(get_commercial_store)) -> list[dict[str, Any]]:
    return store.list_releases()


@router.post("/admin/api/releases", dependencies=[Depends(require_admin_access)])
def create_release(
    request: ReleaseCreateRequest,
    store: CommercialCenterStore = Depends(get_commercial_store),
) -> dict[str, Any]:
    return store.create_release(request)


@router.post("/admin/api/releases/upload", dependencies=[Depends(require_admin_access)])
async def upload_release(
    version: str = Form(...),
    channel: str = Form("stable"),
    platform: str = Form("windows"),
    changelog: str = Form(""),
    force_update: bool = Form(False),
    file: UploadFile = File(...),
    store: CommercialCenterStore = Depends(get_commercial_store),
) -> dict[str, Any]:
    temp_path = store.releases_dir / f"upload_{uuid4().hex}.tmp"
    ensure_dir(temp_path.parent)
    try:
        with temp_path.open("wb") as handle:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
        if temp_path.stat().st_size <= 0:
            raise HTTPException(status_code=400, detail="empty_release_file")
        return store.create_uploaded_release(
            version=version,
            channel=channel,
            platform=platform,
            changelog=changelog,
            force_update=force_update,
            source_path=temp_path,
            original_filename=file.filename or "release.bin",
        )
    finally:
        await file.close()
        temp_path.unlink(missing_ok=True)


@router.get("/downloads/{release_file}")
def download_release_file(
    release_file: str,
    store: CommercialCenterStore = Depends(get_commercial_store),
) -> FileResponse:
    path = store.release_file_path(release_file)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="release_file_not_found")
    return FileResponse(path, filename=path.name, media_type="application/octet-stream")


@router.get("/admin/api/logs", dependencies=[Depends(require_admin_access)])
@router.get("/admin/api/client-logs", dependencies=[Depends(require_admin_access)])
def list_client_logs(
    limit: int = 100,
    store: CommercialCenterStore = Depends(get_commercial_store),
) -> list[dict[str, Any]]:
    return store.list_logs(limit=limit)


@router.get("/admin/api/audit-logs", dependencies=[Depends(require_admin_access)])
def list_audit_logs(
    limit: int = 100,
    store: CommercialCenterStore = Depends(get_commercial_store),
) -> list[dict[str, Any]]:
    return store.list_audit_logs(limit=limit)


@router.post("/activation/activate")
@router.post("/license/activate")
@router.post("/software/activate")
def activate_software(
    request: ActivationRequest,
    http_request: Request,
    settings: Settings = Depends(get_settings),
    store: CommercialCenterStore = Depends(get_commercial_store),
) -> dict[str, Any]:
    _rate_limit(
        http_request,
        settings,
        bucket="activation_activate",
        per_minute=int(getattr(settings, "commercial_api_rate_limit_per_minute", 60) or 60),
    )
    return store.activate(request)


@router.post("/activation/heartbeat")
@router.post("/license/heartbeat")
def software_heartbeat(
    request: HeartbeatRequest,
    http_request: Request,
    settings: Settings = Depends(get_settings),
    store: CommercialCenterStore = Depends(get_commercial_store),
) -> dict[str, Any]:
    _rate_limit(
        http_request,
        settings,
        bucket="activation_heartbeat",
        per_minute=int(getattr(settings, "commercial_api_rate_limit_per_minute", 60) or 60),
    )
    return store.heartbeat(request)


@router.post("/activation/usage/claim")
@router.post("/license/usage/claim")
def claim_license_usage(
    request: LicenseUsageClaimRequest,
    http_request: Request,
    settings: Settings = Depends(get_settings),
    store: CommercialCenterStore = Depends(get_commercial_store),
) -> dict[str, Any]:
    _rate_limit(
        http_request,
        settings,
        bucket="license_usage_claim",
        per_minute=int(getattr(settings, "commercial_api_rate_limit_per_minute", 60) or 60),
    )
    return store.claim_usage(request)


@router.post("/license/credits/reserve")
def reserve_license_credits(
    request: CreditReserveRequest,
    http_request: Request,
    settings: Settings = Depends(get_settings),
    store: CommercialCenterStore = Depends(get_commercial_store),
) -> dict[str, Any]:
    _rate_limit(
        http_request,
        settings,
        bucket="license_credit_reserve",
        per_minute=int(getattr(settings, "commercial_api_rate_limit_per_minute", 60) or 60),
    )
    return store.reserve_credits(request)


@router.post("/license/credits/commit")
def commit_license_credits(
    request: CreditCommitRequest,
    http_request: Request,
    settings: Settings = Depends(get_settings),
    store: CommercialCenterStore = Depends(get_commercial_store),
) -> dict[str, Any]:
    _rate_limit(
        http_request,
        settings,
        bucket="license_credit_commit",
        per_minute=int(getattr(settings, "commercial_api_rate_limit_per_minute", 60) or 60),
    )
    return store.commit_credits(request)


@router.post("/license/credits/refund")
def refund_license_credits(
    request: CreditRefundRequest,
    http_request: Request,
    settings: Settings = Depends(get_settings),
    store: CommercialCenterStore = Depends(get_commercial_store),
) -> dict[str, Any]:
    _rate_limit(
        http_request,
        settings,
        bucket="license_credit_refund",
        per_minute=int(getattr(settings, "commercial_api_rate_limit_per_minute", 60) or 60),
    )
    return store.refund_credits(request)


@router.post("/license/credits/transactions")
def customer_license_credit_transactions(
    request: CreditTransactionsRequest,
    http_request: Request,
    settings: Settings = Depends(get_settings),
    store: CommercialCenterStore = Depends(get_commercial_store),
) -> dict[str, Any]:
    _rate_limit(
        http_request,
        settings,
        bucket="license_credit_transactions",
        per_minute=int(getattr(settings, "commercial_api_rate_limit_per_minute", 60) or 60),
    )
    return store.customer_credit_overview(request)


@router.get("/updates/latest")
def latest_update(
    channel: str = "stable",
    platform: str = "windows",
    current_version: str = "",
    version: str = "",
    store: CommercialCenterStore = Depends(get_commercial_store),
) -> dict[str, Any]:
    return store.update_check(channel=channel, platform=platform, current_version=current_version or version)


@router.post("/logs/client")
@router.post("/client/logs")
def append_client_log(
    request: ClientLogRequest,
    http_request: Request,
    settings: Settings = Depends(get_settings),
    store: CommercialCenterStore = Depends(get_commercial_store),
) -> dict[str, Any]:
    _rate_limit(
        http_request,
        settings,
        bucket="client_logs",
        per_minute=int(getattr(settings, "commercial_api_rate_limit_per_minute", 60) or 60),
    )
    return store.append_log(request)
