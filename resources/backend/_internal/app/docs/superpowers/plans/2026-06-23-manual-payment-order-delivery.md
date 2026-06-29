# Manual Payment Order Delivery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a semi-automatic sales flow where customers submit manual WeChat payment evidence, admins confirm payment, and the system automatically issues licenses or credits.

**Architecture:** Extend the existing commercial control plane in `G:\app\commercial_center.py` with order and evidence records, while reusing current customer, license, credit, and audit logic. Add one public purchase page and one admin order section; keep future WeChat JSAPI/Native integration behind the same order fulfillment boundary.

**Tech Stack:** FastAPI, Pydantic, JSON-backed commercial store with optional Postgres mirror, vanilla HTML/CSS/JS admin/customer pages, pytest with FastAPI TestClient.

---

## File Structure

- Modify `G:\app\commercial_center.py`
  - Add order/evidence Pydantic models.
  - Add store methods for shop plans, order creation, evidence upload, admin order actions, and idempotent fulfillment.
  - Add public `/shop/*` routes and protected `/admin/api/orders/*` routes.
  - Add safe evidence download/display route for admins.
- Create `G:\app\static\commercial_shop.html`
  - Customer purchase page with package cards, contact fields, existing license field, payment note, evidence upload, and order status/result panel.
- Modify `G:\app\static\commercial_admin.html`
  - Add an “订单” tab and readable order table/actions.
  - Fetch `/admin/api/orders` with existing admin session.
- Create `G:\tests\test_manual_payment_orders.py`
  - Backend contract and fulfillment tests.
- Modify `G:\tests\test_agent_workbench_ui.py`
  - Static UI assertions for shop/admin order pages.

---

### Task 1: Add Shop Plans and Order Creation

**Files:**
- Modify: `G:\app\commercial_center.py`
- Create: `G:\tests\test_manual_payment_orders.py`

- [ ] **Step 1: Write failing tests for plan listing and creating a pending order**

Add this file:

```python
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app, get_settings
from app.settings import Settings


def _client(tmp_path: Path, *, admin_password: str = "xiongtuai123") -> TestClient:
    app.dependency_overrides.clear()
    app.dependency_overrides[get_settings] = lambda: Settings(
        dry_run=True,
        storage_dir=tmp_path,
        commercial_admin_password=admin_password,
    )
    return TestClient(app)


def _admin_login(client: TestClient) -> None:
    response = client.post("/admin/api/login", json={"username": "xiongtuai", "password": "xiongtuai123"})
    assert response.status_code == 200, response.text


def test_shop_plans_are_customer_readable(tmp_path: Path):
    with _client(tmp_path) as client:
        response = client.get("/shop/plans")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["currency"] == "CNY"
        product_ids = [item["product_id"] for item in body["plans"]]
        assert product_ids[:3] == ["trial", "monthly", "yearly"]
        monthly = next(item for item in body["plans"] if item["product_id"] == "monthly")
        assert monthly["credit_grant"] == 48000
        assert monthly["payment_method"] == "wechat_manual"
        assert "收款码" in body["payment_instructions"]


def test_customer_can_create_manual_payment_order(tmp_path: Path):
    with _client(tmp_path) as client:
        response = client.post(
            "/shop/orders",
            json={
                "product_id": "monthly",
                "contact_name": "张三",
                "wechat": "zhangsan_wx",
                "phone": "13800000000",
                "payment_note": "张三月付",
                "payment_time": "2026-06-23 10:30",
            },
        )
        assert response.status_code == 200, response.text
        order = response.json()["order"]
        assert order["order_no"].startswith("XT")
        assert order["status"] == "pending_review"
        assert order["product_type"] == "monthly"
        assert order["credit_grant"] == 48000
        assert order["amount_cents"] > 0
        assert "license_key" not in order

        lookup = client.get(f"/shop/orders/{order['order_no']}")
        assert lookup.status_code == 200, lookup.text
        assert lookup.json()["order"]["status_label"] == "待确认收款"

        _admin_login(client)
        admin_orders = client.get("/admin/api/orders")
        assert admin_orders.status_code == 200, admin_orders.text
        assert admin_orders.json()[0]["order_no"] == order["order_no"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest -q G:\tests\test_manual_payment_orders.py::test_shop_plans_are_customer_readable G:\tests\test_manual_payment_orders.py::test_customer_can_create_manual_payment_order
```

Expected: FAIL with missing `/shop/plans` and `/shop/orders` routes.

- [ ] **Step 3: Add models, default store data, plan config, and create-order store methods**

In `G:\app\commercial_center.py`, add these models near the existing request/record models:

```python
SHOP_PLANS = [
    {"product_id": "trial", "product_type": "trial", "name": "试用版", "amount_cents": 990, "credit_grant": 1300},
    {"product_id": "monthly", "product_type": "monthly", "name": "月付版", "amount_cents": 29800, "credit_grant": 48000},
    {"product_id": "yearly", "product_type": "yearly", "name": "年会员", "amount_cents": 298000, "credit_grant": 48000},
    {"product_id": "credit_48000", "product_type": "credit_pack", "name": "48000 积分充值包", "amount_cents": 29800, "credit_grant": 48000},
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
    order_no: str = Field(default_factory=lambda: f"XT{datetime.now(timezone.utc).strftime('%Y%m%d')}{uuid4().hex[:8].upper()}")
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
    operator_note: str = ""
    fulfillment_error: str = ""
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
    paid_at: str = ""
    fulfilled_at: str = ""
    rejected_at: str = ""
```

Update `_default_data()` so it includes order storage:

```python
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
```

Add these methods to `CommercialCenterStore`:

```python
def shop_plans(self) -> dict[str, Any]:
    return {
        "currency": "CNY",
        "payment_method": "wechat_manual",
        "payment_instructions": "请使用页面展示的微信收款码付款，付款后提交备注或截图，后台确认后自动发货。",
        "plans": [
            {**plan, "payment_method": "wechat_manual", "credits_seconds": plan["credit_grant"] // CREDIT_RATE_PER_SECOND}
            for plan in SHOP_PLANS
        ],
    }

def _shop_plan_by_id(self, product_id: str) -> dict[str, Any]:
    for plan in SHOP_PLANS:
        if plan["product_id"] == product_id:
            return dict(plan)
    raise HTTPException(status_code=400, detail="shop_product_not_found")

def create_shop_order(self, request: ShopOrderCreateRequest) -> dict[str, Any]:
    if not request.wechat.strip():
        raise HTTPException(status_code=400, detail="wechat_required")
    if not (request.payment_note.strip() or request.payment_time.strip()):
        raise HTTPException(status_code=400, detail="payment_evidence_required")
    plan = self._shop_plan_by_id(request.product_id.strip())
    data = self._load()
    record = ManualPaymentOrderRecord(
        contact_name=request.contact_name.strip() or request.wechat.strip(),
        wechat=request.wechat.strip(),
        phone=request.phone.strip(),
        existing_license_key_hash=_hash_secret(request.existing_license_key.strip()) if request.existing_license_key.strip() else "",
        product_type=plan["product_type"],
        product_id=plan["product_id"],
        product_name=plan["name"],
        amount_cents=int(plan["amount_cents"]),
        credit_grant=int(plan["credit_grant"]),
        payment_note=request.payment_note.strip(),
        payment_time=request.payment_time.strip(),
    )
    data.setdefault("orders", {})[record.order_id] = record.model_dump(mode="json")
    self._append_audit(data, "order.create", "order", record.order_id, after=self._public_order(data["orders"][record.order_id]))
    self._save(data)
    return {"order": self._public_order(data["orders"][record.order_id])}

def list_orders(self, status: str = "") -> list[dict[str, Any]]:
    rows = list(self._load().setdefault("orders", {}).values())
    if status:
        rows = [row for row in rows if row.get("status") == status]
    return [self._public_order(row, include_internal=True) for row in sorted(rows, key=lambda row: row.get("created_at", ""), reverse=True)]

def get_order_by_no(self, order_no: str) -> dict[str, Any]:
    data = self._load()
    for row in data.setdefault("orders", {}).values():
        if row.get("order_no") == order_no:
            return {"order": self._public_order(row)}
    raise HTTPException(status_code=404, detail="order_not_found")

def _public_order(self, row: dict[str, Any], *, include_internal: bool = False) -> dict[str, Any]:
    public = dict(row)
    public["status_label"] = ORDER_STATUS_LABELS.get(public.get("status", ""), public.get("status", ""))
    public.pop("existing_license_key_hash", None)
    if not include_internal:
        public.pop("fulfillment_error", None)
        public.pop("operator_note", None)
    return public
```

- [ ] **Step 4: Add public and admin order routes**

Add routes near the existing `/activate` and admin APIs:

```python
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
    _rate_limit(http_request, settings, bucket="shop_orders", per_minute=30)
    return store.create_shop_order(request)


@router.get("/shop/orders/{order_no}")
def get_shop_order(order_no: str, store: CommercialCenterStore = Depends(get_commercial_store)) -> dict[str, Any]:
    return store.get_order_by_no(order_no)


@router.get("/admin/api/orders", dependencies=[Depends(require_admin_access)])
def list_admin_orders(
    status: str = "",
    store: CommercialCenterStore = Depends(get_commercial_store),
) -> list[dict[str, Any]]:
    return store.list_orders(status=status)
```

- [ ] **Step 5: Run tests to verify Task 1 passes**

Run:

```powershell
python -m pytest -q G:\tests\test_manual_payment_orders.py::test_shop_plans_are_customer_readable G:\tests\test_manual_payment_orders.py::test_customer_can_create_manual_payment_order
```

Expected: 2 passed.

- [ ] **Step 6: Record checkpoint**

Run:

```powershell
git status --short
```

Expected in current workspace: this may print `fatal: not a git repository`. If git works, commit:

```powershell
git add G:\app\commercial_center.py G:\tests\test_manual_payment_orders.py
git commit -m "feat: add manual payment order creation"
```

If git is unavailable, continue and mention it in the task handoff notes.

---

### Task 2: Add Payment Evidence Upload and Safe Evidence Storage

**Files:**
- Modify: `G:\app\commercial_center.py`
- Modify: `G:\tests\test_manual_payment_orders.py`

- [ ] **Step 1: Write failing evidence upload tests**

Append to `G:\tests\test_manual_payment_orders.py`:

```python
def test_customer_can_upload_payment_evidence_image(tmp_path: Path):
    with _client(tmp_path) as client:
        created = client.post(
            "/shop/orders",
            json={"product_id": "trial", "wechat": "trial_wx", "payment_note": "trial pay"},
        ).json()["order"]

        response = client.post(
            f"/shop/orders/{created['order_no']}/evidence",
            data={"payment_note": "已付款，备注 trial_wx", "payment_time": "2026-06-23 11:00"},
            files={"file": ("pay.png", b"\x89PNG\r\n\x1a\nfake-image", "image/png")},
        )
        assert response.status_code == 200, response.text
        order = response.json()["order"]
        assert order["status"] == "pending_review"
        assert order["evidence_file_id"].startswith("ev_")

        _admin_login(client)
        admin_order = client.get("/admin/api/orders").json()[0]
        assert admin_order["evidence_file_id"] == order["evidence_file_id"]


def test_rejects_invalid_payment_evidence(tmp_path: Path):
    with _client(tmp_path) as client:
        created = client.post(
            "/shop/orders",
            json={"product_id": "trial", "wechat": "trial_wx", "payment_note": "trial pay"},
        ).json()["order"]

        response = client.post(
            f"/shop/orders/{created['order_no']}/evidence",
            files={"file": ("note.txt", b"not image", "text/plain")},
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "unsupported_evidence_file"
```

- [ ] **Step 2: Run evidence tests to verify they fail**

Run:

```powershell
python -m pytest -q G:\tests\test_manual_payment_orders.py::test_customer_can_upload_payment_evidence_image G:\tests\test_manual_payment_orders.py::test_rejects_invalid_payment_evidence
```

Expected: FAIL because `/shop/orders/{order_no}/evidence` does not exist.

- [ ] **Step 3: Add evidence model and storage directory**

In `CommercialCenterStore.__init__`, add:

```python
self.evidence_dir = ensure_dir(self.root / "manual_payment_evidence")
```

Add model:

```python
class ManualPaymentEvidenceRecord(BaseModel):
    evidence_id: str = Field(default_factory=lambda: f"ev_{uuid4().hex[:12]}")
    order_id: str
    original_filename: str = ""
    stored_path: str
    content_type: str = ""
    size_bytes: int = 0
    created_at: str = Field(default_factory=_now)
```

- [ ] **Step 4: Implement evidence save method**

Add to `CommercialCenterStore`:

```python
def save_payment_evidence(
    self,
    *,
    order_no: str,
    payment_note: str,
    payment_time: str,
    original_filename: str,
    content_type: str,
    payload: bytes,
) -> dict[str, Any]:
    if payload and content_type not in {"image/png", "image/jpeg", "image/jpg", "image/webp"}:
        raise HTTPException(status_code=400, detail="unsupported_evidence_file")
    if len(payload) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="evidence_file_too_large")
    data = self._load()
    order = None
    for row in data.setdefault("orders", {}).values():
        if row.get("order_no") == order_no:
            order = row
            break
    if not order:
        raise HTTPException(status_code=404, detail="order_not_found")
    if not (payload or payment_note.strip() or payment_time.strip()):
        raise HTTPException(status_code=400, detail="payment_evidence_required")

    if payload:
        suffix = ".png" if content_type == "image/png" else ".jpg" if content_type in {"image/jpeg", "image/jpg"} else ".webp"
        evidence_id = f"ev_{uuid4().hex[:12]}"
        target = self.evidence_dir / f"{evidence_id}{suffix}"
        target.write_bytes(payload)
        record = ManualPaymentEvidenceRecord(
            evidence_id=evidence_id,
            order_id=order["order_id"],
            original_filename=original_filename,
            stored_path=str(target),
            content_type=content_type,
            size_bytes=len(payload),
        ).model_dump(mode="json")
        data.setdefault("manual_payment_evidence", {})[evidence_id] = record
        order["evidence_file_id"] = evidence_id

    if payment_note.strip():
        order["payment_note"] = payment_note.strip()
    if payment_time.strip():
        order["payment_time"] = payment_time.strip()
    order["updated_at"] = _now()
    self._append_audit(data, "order.evidence", "order", order["order_id"], after=self._public_order(order, include_internal=True))
    self._save(data)
    return {"order": self._public_order(order)}
```

- [ ] **Step 5: Add evidence upload route**

Add route:

```python
@router.post("/shop/orders/{order_no}/evidence")
async def upload_shop_order_evidence(
    order_no: str,
    payment_note: str = Form(""),
    payment_time: str = Form(""),
    file: UploadFile | None = File(None),
    store: CommercialCenterStore = Depends(get_commercial_store),
) -> dict[str, Any]:
    payload = b""
    filename = ""
    content_type = ""
    if file is not None:
        filename = file.filename or "payment-evidence"
        content_type = file.content_type or ""
        payload = await file.read()
        await file.close()
    return store.save_payment_evidence(
        order_no=order_no,
        payment_note=payment_note,
        payment_time=payment_time,
        original_filename=filename,
        content_type=content_type,
        payload=payload,
    )
```

- [ ] **Step 6: Run Task 2 tests**

Run:

```powershell
python -m pytest -q G:\tests\test_manual_payment_orders.py::test_customer_can_upload_payment_evidence_image G:\tests\test_manual_payment_orders.py::test_rejects_invalid_payment_evidence
```

Expected: 2 passed.

- [ ] **Step 7: Record checkpoint**

Run:

```powershell
git status --short
```

If git works:

```powershell
git add G:\app\commercial_center.py G:\tests\test_manual_payment_orders.py
git commit -m "feat: accept manual payment evidence"
```

---

### Task 3: Implement Admin Confirmation and Idempotent Fulfillment

**Files:**
- Modify: `G:\app\commercial_center.py`
- Modify: `G:\tests\test_manual_payment_orders.py`

- [ ] **Step 1: Write failing fulfillment tests**

Append to `G:\tests\test_manual_payment_orders.py`:

```python
def test_admin_confirm_payment_fulfills_new_monthly_license(tmp_path: Path):
    with _client(tmp_path) as client:
        order = client.post(
            "/shop/orders",
            json={"product_id": "monthly", "wechat": "buyer_wx", "phone": "13900000000", "payment_note": "month"},
        ).json()["order"]
        _admin_login(client)

        response = client.post(f"/admin/api/orders/{order['order_id']}/confirm-payment", json={"note": "到账"})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["order"]["status"] == "fulfilled"
        assert body["delivery"]["license_key"].startswith("AIVO-")
        assert body["delivery"]["license"]["plan"] == "monthly"
        assert body["delivery"]["license"]["credit_balance"] == 48000

        duplicate = client.post(f"/admin/api/orders/{order['order_id']}/confirm-payment", json={"note": "重复确认"})
        assert duplicate.status_code == 200, duplicate.text
        assert duplicate.json()["delivery"]["license_key"] == body["delivery"]["license_key"]
        licenses = client.get("/admin/api/licenses").json()
        assert len(licenses) == 1
        assert licenses[0]["credit_balance"] == 48000


def test_admin_confirm_payment_recharges_existing_license(tmp_path: Path):
    with _client(tmp_path) as client:
        _admin_login(client)
        customer = client.post("/admin/api/customers", json={"name": "老客户", "wechat": "old_wx"}).json()
        created = client.post(
            "/admin/api/licenses",
            json={"customer_id": customer["customer_id"], "plan": "trial", "credit_grant": 1300},
        ).json()
        order = client.post(
            "/shop/orders",
            json={
                "product_id": "credit_48000",
                "wechat": "old_wx",
                "existing_license_key": created["license_key"],
                "payment_note": "充值",
            },
        ).json()["order"]

        fulfilled = client.post(f"/admin/api/orders/{order['order_id']}/confirm-payment", json={"note": "到账"})
        assert fulfilled.status_code == 200, fulfilled.text
        delivery = fulfilled.json()["delivery"]
        assert delivery["license"]["license_id"] == created["license"]["license_id"]
        assert delivery["license"]["credit_balance"] == 49300
        assert "license_key" not in delivery


def test_admin_can_reject_and_request_evidence(tmp_path: Path):
    with _client(tmp_path) as client:
        order = client.post(
            "/shop/orders",
            json={"product_id": "trial", "wechat": "bad_wx", "payment_note": "看不清"},
        ).json()["order"]
        _admin_login(client)

        needs = client.post(f"/admin/api/orders/{order['order_id']}/request-evidence", json={"note": "截图不清晰"})
        assert needs.status_code == 200, needs.text
        assert needs.json()["order"]["status"] == "needs_evidence"

        rejected = client.post(f"/admin/api/orders/{order['order_id']}/reject", json={"note": "未到账"})
        assert rejected.status_code == 200, rejected.text
        assert rejected.json()["order"]["status"] == "rejected"

        confirm = client.post(f"/admin/api/orders/{order['order_id']}/confirm-payment", json={"note": "误点"})
        assert confirm.status_code == 400
        assert confirm.json()["detail"] == "order_not_confirmable"
```

- [ ] **Step 2: Run fulfillment tests to verify they fail**

Run:

```powershell
python -m pytest -q G:\tests\test_manual_payment_orders.py::test_admin_confirm_payment_fulfills_new_monthly_license G:\tests\test_manual_payment_orders.py::test_admin_confirm_payment_recharges_existing_license G:\tests\test_manual_payment_orders.py::test_admin_can_reject_and_request_evidence
```

Expected: FAIL because admin order action routes do not exist.

- [ ] **Step 3: Add license lookup and customer reuse helpers**

Add to `CommercialCenterStore`:

```python
def _find_license_by_hash(self, data: dict[str, Any], key_hash: str) -> dict[str, Any] | None:
    if not key_hash:
        return None
    for license_record in data.setdefault("licenses", {}).values():
        if license_record.get("key_hash") == key_hash:
            return license_record
    return None

def _find_or_create_order_customer(self, data: dict[str, Any], order: dict[str, Any]) -> dict[str, Any]:
    for customer in data.setdefault("customers", {}).values():
        if order.get("wechat") and customer.get("wechat") == order.get("wechat"):
            return customer
    customer = CustomerRecord(
        name=order.get("contact_name") or order.get("wechat") or "微信客户",
        phone=order.get("phone", ""),
        wechat=order.get("wechat", ""),
        status="active" if order.get("product_type") != "trial" else "trial",
        notes=f"来自订单 {order.get('order_no')}",
    ).model_dump(mode="json")
    data["customers"][customer["customer_id"]] = customer
    self._append_audit(data, "customer.create", "customer", customer["customer_id"], after=customer)
    return customer
```

- [ ] **Step 4: Add fulfillment method**

Add to `CommercialCenterStore`:

```python
def confirm_order_payment(self, order_id: str, request: OrderAdminActionRequest) -> dict[str, Any]:
    data = self._load()
    order = data.setdefault("orders", {}).get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="order_not_found")
    if order.get("status") == "fulfilled":
        return {"order": self._public_order(order, include_internal=True), "delivery": order.get("delivery", {})}
    if order.get("status") in {"rejected", "cancelled"}:
        raise HTTPException(status_code=400, detail="order_not_confirmable")
    order["status"] = "paid"
    order["paid_at"] = order.get("paid_at") or _now()
    order["operator_note"] = request.note.strip()
    try:
        delivery = self._fulfill_order_locked(data, order)
        order["status"] = "fulfilled"
        order["fulfilled_at"] = order.get("fulfilled_at") or _now()
        order["fulfillment_error"] = ""
        order["delivery"] = delivery
    except HTTPException as exc:
        order["status"] = "fulfillment_failed"
        order["fulfillment_error"] = str(exc.detail)
        self._append_audit(data, "order.fulfillment_failed", "order", order_id, after=self._public_order(order, include_internal=True))
        self._save(data)
        raise
    except Exception as exc:
        order["status"] = "fulfillment_failed"
        order["fulfillment_error"] = str(exc)
    order["updated_at"] = _now()
    self._append_audit(data, "order.fulfill", "order", order_id, after=self._public_order(order, include_internal=True))
    self._save(data)
    return {"order": self._public_order(order, include_internal=True), "delivery": order.get("delivery", {})}

def _fulfill_order_locked(self, data: dict[str, Any], order: dict[str, Any]) -> dict[str, Any]:
    existing = self._find_license_by_hash(data, order.get("existing_license_key_hash", ""))
    if existing:
        before = self._public_license(existing, data=data)
        if order.get("product_type") == "credit_pack":
            grant = int(order.get("credit_grant") or 0)
            self._ensure_credit_fields(existing)
            existing["credit_balance"] = self._credit_int(existing, "credit_balance") + grant
            existing["credit_total_granted"] = self._credit_int(existing, "credit_total_granted") + grant
            existing["updated_at"] = _now()
            self._append_audit(data, "license.credit_adjust", "license", existing["license_id"], before=before, after=self._public_license(existing, data=data))
            return {"license": self._public_license(existing, data=data), "license_key_preview": existing.get("key_preview", "")}
        restored = self._restore_paid_license_in_data(data, existing, plan=order.get("product_type", "yearly"), credit_grant=int(order.get("credit_grant") or 0))
        return {"license": restored, "license_key_preview": existing.get("key_preview", "")}

    customer = self._find_or_create_order_customer(data, order)
    created = self._create_license_in_data(
        data,
        customer_id=customer["customer_id"],
        plan=order.get("product_type") or "monthly",
        credit_grant=int(order.get("credit_grant") or 0),
        note=f"订单 {order.get('order_no')} 自动发货",
    )
    order["customer_id"] = customer["customer_id"]
    order["license_id"] = created["license"]["license_id"]
    order["license_key_preview"] = created["license"]["key_preview"]
    return {"license": created["license"], "license_key": created["license_key"]}
```

Refactor tiny private helpers from existing `create_license()` and `restore_paid_license()` so the above can call:

```python
def _create_license_in_data(self, data: dict[str, Any], *, customer_id: str, plan: str, credit_grant: int, note: str) -> dict[str, Any]:
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
        note=note,
        notes=note,
    )
    data["licenses"][record.license_id] = record.model_dump(mode="json")
    public = self._public_license(data["licenses"][record.license_id], data=data)
    self._append_audit(data, "license.create", "license", record.license_id, after=public)
    return {"license": public, "license_key": raw_key}

def _restore_paid_license_in_data(self, data: dict[str, Any], license_record: dict[str, Any], *, plan: str, credit_grant: int) -> dict[str, Any]:
    before = self._public_license(license_record, data=data)
    cycle_starts_at, cycle_ends_at = _credit_cycle_bounds()
    license_record["plan"] = plan
    license_record["status"] = "active"
    license_record["usage_limit_seconds"] = None
    license_record["usage_locked_at"] = ""
    license_record["usage_lock_reason"] = ""
    self._ensure_credit_fields(license_record)
    license_record["credit_balance"] = credit_grant
    license_record["credit_grant_monthly"] = credit_grant
    license_record["credit_total_granted"] = self._credit_int(license_record, "credit_total_granted") + credit_grant
    license_record["credit_cycle_starts_at"] = cycle_starts_at
    license_record["credit_cycle_ends_at"] = cycle_ends_at
    license_record["credit_refreshed_at"] = cycle_starts_at
    license_record["credit_locked_at"] = ""
    license_record["credit_lock_reason"] = ""
    license_record["updated_at"] = _now()
    after = self._public_license(license_record, data=data)
    self._append_audit(data, "license.restore_paid", "license", license_record["license_id"], before=before, after=after)
    return after
```

Keep public `create_license()` and `restore_paid_license()` behavior unchanged by making them call these helpers and then `_save(data)`.

- [ ] **Step 5: Add admin order action methods and routes**

Add methods:

```python
def reject_order(self, order_id: str, request: OrderAdminActionRequest) -> dict[str, Any]:
    data = self._load()
    order = data.setdefault("orders", {}).get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="order_not_found")
    if order.get("status") == "fulfilled":
        raise HTTPException(status_code=400, detail="order_already_fulfilled")
    order["status"] = "rejected"
    order["operator_note"] = request.note.strip()
    order["rejected_at"] = _now()
    order["updated_at"] = _now()
    self._append_audit(data, "order.reject", "order", order_id, after=self._public_order(order, include_internal=True))
    self._save(data)
    return {"order": self._public_order(order, include_internal=True)}

def request_order_evidence(self, order_id: str, request: OrderAdminActionRequest) -> dict[str, Any]:
    data = self._load()
    order = data.setdefault("orders", {}).get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="order_not_found")
    if order.get("status") == "fulfilled":
        raise HTTPException(status_code=400, detail="order_already_fulfilled")
    order["status"] = "needs_evidence"
    order["operator_note"] = request.note.strip()
    order["updated_at"] = _now()
    self._append_audit(data, "order.request_evidence", "order", order_id, after=self._public_order(order, include_internal=True))
    self._save(data)
    return {"order": self._public_order(order, include_internal=True)}

def retry_order_fulfillment(self, order_id: str, request: OrderAdminActionRequest) -> dict[str, Any]:
    data = self._load()
    order = data.setdefault("orders", {}).get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="order_not_found")
    if order.get("status") != "fulfillment_failed":
        raise HTTPException(status_code=400, detail="order_not_retryable")
    order["status"] = "paid"
    self._save(data)
    return self.confirm_order_payment(order_id, request)
```

Add routes:

```python
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
```

- [ ] **Step 6: Run Task 3 tests**

Run:

```powershell
python -m pytest -q G:\tests\test_manual_payment_orders.py::test_admin_confirm_payment_fulfills_new_monthly_license G:\tests\test_manual_payment_orders.py::test_admin_confirm_payment_recharges_existing_license G:\tests\test_manual_payment_orders.py::test_admin_can_reject_and_request_evidence
```

Expected: 3 passed.

- [ ] **Step 7: Run credit regression tests**

Run:

```powershell
python -m pytest -q G:\tests\test_commercial_center.py G:\tests\test_commercial_client_license.py
```

Expected: all tests pass.

- [ ] **Step 8: Record checkpoint**

Run:

```powershell
git status --short
```

If git works:

```powershell
git add G:\app\commercial_center.py G:\tests\test_manual_payment_orders.py
git commit -m "feat: fulfill manual payment orders"
```

---

### Task 4: Add Customer Shop Page and Admin Order UI

**Files:**
- Create: `G:\app\static\commercial_shop.html`
- Modify: `G:\app\static\commercial_admin.html`
- Modify: `G:\tests\test_agent_workbench_ui.py`

- [ ] **Step 1: Write failing static UI tests**

Append to `G:\tests\test_agent_workbench_ui.py`:

```python
def test_commercial_shop_page_exposes_manual_payment_flow():
    shop = Path("G:/app/static/commercial_shop.html").read_text(encoding="utf-8")

    for expected in [
        "<title>雄图IP智能体 自助购买</title>",
        "选择套餐",
        "微信收款码",
        "提交付款信息",
        "/shop/plans",
        "/shop/orders",
        "/evidence",
        "授权码",
        "积分余额",
    ]:
        assert expected in shop


def test_commercial_admin_exposes_order_management_tab():
    admin = Path("G:/app/static/commercial_admin.html").read_text(encoding="utf-8")

    for expected in [
        'data-tab="orders"',
        'id="tab-orders"',
        'id="ordersBody"',
        "/admin/api/orders",
        "confirm-payment",
        "request-evidence",
        "retry-fulfillment",
        "确认收款并发货",
        "待确认收款",
    ]:
        assert expected in admin
```

- [ ] **Step 2: Run static tests to verify they fail**

Run:

```powershell
python -m pytest -q G:\tests\test_agent_workbench_ui.py::test_commercial_shop_page_exposes_manual_payment_flow G:\tests\test_agent_workbench_ui.py::test_commercial_admin_exposes_order_management_tab
```

Expected: FAIL because `commercial_shop.html` and admin order UI do not exist yet.

- [ ] **Step 3: Create customer purchase page**

Create `G:\app\static\commercial_shop.html` with this structure:

```html
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>雄图IP智能体 自助购买</title>
  <style>
    body { margin: 0; font-family: "Microsoft YaHei", Arial, sans-serif; background: #f6f8fb; color: #0f172a; }
    header { padding: 28px 36px; background: #102a54; color: #fff; }
    main { max-width: 1120px; margin: 24px auto; padding: 0 20px 40px; display: grid; grid-template-columns: 1.1fr .9fr; gap: 18px; }
    .panel { background: #fff; border: 1px solid #d8e0ec; border-radius: 8px; padding: 18px; }
    .plans { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
    .plan { border: 1px solid #d8e0ec; border-radius: 8px; padding: 14px; cursor: pointer; }
    .plan.active { border-color: #168577; background: #e9f7f4; }
    label { display: block; margin: 12px 0 6px; font-weight: 700; }
    input, textarea { width: 100%; box-sizing: border-box; border: 1px solid #cbd5e1; border-radius: 6px; padding: 10px; font: inherit; }
    button { border: 0; border-radius: 6px; padding: 11px 16px; font-weight: 700; background: #168577; color: #fff; cursor: pointer; }
    button.secondary { background: #2d8cff; }
    .qr { min-height: 180px; display: grid; place-items: center; border: 1px dashed #a8b3c7; border-radius: 8px; color: #64748b; }
    .result { white-space: pre-wrap; background: #0f172a; color: #e5f6ff; border-radius: 8px; padding: 12px; min-height: 120px; }
    @media (max-width: 860px) { main { grid-template-columns: 1fr; } .plans { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <header>
    <h1>雄图IP智能体 自助购买</h1>
    <p>选择套餐后微信付款，提交付款信息，后台确认后自动发授权码或充值积分。</p>
  </header>
  <main>
    <section class="panel">
      <h2>选择套餐</h2>
      <div id="plans" class="plans"></div>
      <label>联系人</label>
      <input id="contactName" placeholder="例如：张三" />
      <label>微信号</label>
      <input id="wechat" placeholder="用于核对付款和售后联系" />
      <label>手机号</label>
      <input id="phone" placeholder="可选" />
      <label>已有授权码</label>
      <input id="existingLicenseKey" placeholder="续费或充值时填写；新购可不填" />
      <label>付款备注</label>
      <input id="paymentNote" placeholder="建议填写微信付款备注或转账昵称" />
      <label>付款时间</label>
      <input id="paymentTime" placeholder="例如：2026-06-23 10:30" />
      <button id="createOrder">提交付款信息</button>
    </section>
    <aside class="panel">
      <h2>微信收款码</h2>
      <div class="qr" id="qrBox">请把你的微信收款码图片放到后续配置位</div>
      <p id="payAmount">请选择套餐</p>
      <label>付款截图</label>
      <input id="evidenceFile" type="file" accept="image/png,image/jpeg,image/webp" />
      <button id="uploadEvidence" class="secondary">上传付款截图</button>
      <h2>订单状态</h2>
      <div id="result" class="result">等待提交订单。</div>
    </aside>
  </main>
  <script>
    const $ = (id) => document.getElementById(id);
    const money = (cents) => `¥${(Number(cents || 0) / 100).toFixed(2)}`;
    let plans = [];
    let selected = "";
    let currentOrder = null;
    async function api(path, options = {}) {
      const headers = options.body instanceof FormData ? {} : { "Content-Type": "application/json" };
      const res = await fetch(path, { ...options, headers: { ...headers, ...(options.headers || {}) } });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || res.statusText);
      return data;
    }
    function renderPlans() {
      $("plans").innerHTML = plans.map((plan) => `
        <div class="plan ${plan.product_id === selected ? "active" : ""}" data-plan="${plan.product_id}">
          <strong>${plan.name}</strong>
          <p>${money(plan.amount_cents)} / ${plan.credit_grant} 积分</p>
        </div>
      `).join("");
      document.querySelectorAll("[data-plan]").forEach((item) => item.onclick = () => {
        selected = item.dataset.plan;
        const plan = plans.find((row) => row.product_id === selected);
        $("payAmount").textContent = `应付金额：${money(plan.amount_cents)}，付款后请提交备注或截图。`;
        renderPlans();
      });
    }
    function renderOrder(order) {
      currentOrder = order;
      const lines = [`订单号：${order.order_no}`, `状态：${order.status_label}`, `套餐：${order.product_name}`];
      if (order.delivery?.license_key) lines.push(`授权码：${order.delivery.license_key}`);
      if (order.delivery?.license?.credits) lines.push(`积分余额：${order.delivery.license.credits.balance}`);
      $("result").textContent = lines.join("\n");
    }
    $("createOrder").onclick = async () => {
      const data = await api("/shop/orders", {
        method: "POST",
        body: JSON.stringify({
          product_id: selected,
          contact_name: $("contactName").value.trim(),
          wechat: $("wechat").value.trim(),
          phone: $("phone").value.trim(),
          existing_license_key: $("existingLicenseKey").value.trim(),
          payment_note: $("paymentNote").value.trim(),
          payment_time: $("paymentTime").value.trim(),
        }),
      });
      renderOrder(data.order);
    };
    $("uploadEvidence").onclick = async () => {
      if (!currentOrder) throw new Error("请先提交订单");
      const form = new FormData();
      form.append("payment_note", $("paymentNote").value.trim());
      form.append("payment_time", $("paymentTime").value.trim());
      if ($("evidenceFile").files[0]) form.append("file", $("evidenceFile").files[0]);
      const data = await api(`/shop/orders/${currentOrder.order_no}/evidence`, { method: "POST", body: form });
      renderOrder(data.order);
    };
    async function boot() {
      const data = await api("/shop/plans");
      plans = data.plans;
      selected = plans[0]?.product_id || "";
      renderPlans();
    }
    boot().catch((error) => $("result").textContent = error.message);
  </script>
</body>
</html>
```

- [ ] **Step 4: Add admin order tab markup and JS**

In `G:\app\static\commercial_admin.html`:

Add a tab button beside existing customer/license/release buttons:

```html
<button class="tab" data-tab="orders">订单</button>
```

Add tab page:

```html
<div id="tab-orders" class="tab-page" hidden>
  <h3>收款订单</h3>
  <label>订单状态</label>
  <select id="orderStatusFilter">
    <option value="">全部订单</option>
    <option value="pending_review">待确认收款</option>
    <option value="needs_evidence">需补充凭证</option>
    <option value="fulfilled">已发货</option>
    <option value="fulfillment_failed">发货失败</option>
    <option value="rejected">已驳回</option>
  </select>
  <div class="actions"><button id="refreshOrders" class="ghost">刷新订单</button></div>
</div>
```

Add a panel in the main section:

```html
<div class="panel">
  <div class="panel-head">
    <h2>订单管理</h2>
    <small>人工确认收款后自动发授权码或充值积分</small>
  </div>
  <div class="table-wrap">
    <table>
      <thead><tr><th>订单</th><th>客户</th><th>套餐</th><th>金额</th><th>状态</th><th>凭证</th><th>操作</th></tr></thead>
      <tbody id="ordersBody"></tbody>
    </table>
  </div>
</div>
```

Update script state and refresh:

```javascript
const state = { customers: [], licenses: [], releases: [], logs: [], audit: [], backups: [], orders: [], health: null };
```

In `refreshAll()`, include:

```javascript
api(`/admin/api/orders?status=${encodeURIComponent($("orderStatusFilter")?.value || "")}`)
```

Assign:

```javascript
state.orders = orders;
renderOrders();
```

Add renderer/actions:

```javascript
function renderOrders() {
  $("ordersBody").innerHTML = state.orders.map((order) => `
    <tr>
      <td><strong>${text(order.order_no)}</strong><br><small>${text(order.created_at)}</small></td>
      <td>${text(order.contact_name || order.wechat)}<br><small>${text(order.phone || order.wechat)}</small></td>
      <td>${text(order.product_name)}<br><small>${Number(order.credit_grant || 0)} 积分</small></td>
      <td>¥${(Number(order.amount_cents || 0) / 100).toFixed(2)}</td>
      <td>${text(order.status_label || order.status)}</td>
      <td>${order.evidence_file_id ? "已上传" : text(order.payment_note || "-")}</td>
      <td><div class="actions" style="margin-top:0">
        ${order.status === "pending_review" || order.status === "needs_evidence" ? `<button data-order-confirm="${text(order.order_id)}">确认收款并发货</button>` : ""}
        ${order.status === "pending_review" ? `<button class="ghost" data-order-evidence="${text(order.order_id)}">要求补凭证</button>` : ""}
        ${order.status === "fulfillment_failed" ? `<button class="warning" data-order-retry="${text(order.order_id)}">重试发货</button>` : ""}
        ${order.status !== "fulfilled" && order.status !== "rejected" ? `<button class="danger" data-order-reject="${text(order.order_id)}">驳回</button>` : ""}
      </div></td>
    </tr>
  `).join("") || `<tr><td colspan="7"><div class="empty">暂无订单</div></td></tr>`;
  document.querySelectorAll("[data-order-confirm]").forEach((button) => button.onclick = () => confirmOrder(button.dataset.orderConfirm));
  document.querySelectorAll("[data-order-evidence]").forEach((button) => button.onclick = () => requestOrderEvidence(button.dataset.orderEvidence));
  document.querySelectorAll("[data-order-retry]").forEach((button) => button.onclick = () => retryOrder(button.dataset.orderRetry));
  document.querySelectorAll("[data-order-reject]").forEach((button) => button.onclick = () => rejectOrder(button.dataset.orderReject));
}

async function confirmOrder(id) {
  const note = prompt("确认已收到客户付款？填写备注：", "已确认到账");
  if (note === null) return;
  await api(`/admin/api/orders/${id}/confirm-payment`, { method: "POST", body: JSON.stringify({ note }) });
  await refreshAll();
}

async function requestOrderEvidence(id) {
  const note = prompt("请填写要求补充凭证的原因：", "付款截图不清晰，请补充");
  if (note === null) return;
  await api(`/admin/api/orders/${id}/request-evidence`, { method: "POST", body: JSON.stringify({ note }) });
  await refreshAll();
}

async function retryOrder(id) {
  await api(`/admin/api/orders/${id}/retry-fulfillment`, { method: "POST", body: JSON.stringify({ note: "后台重试发货" }) });
  await refreshAll();
}

async function rejectOrder(id) {
  const note = prompt("请填写驳回原因：", "未查到付款");
  if (note === null) return;
  await api(`/admin/api/orders/${id}/reject`, { method: "POST", body: JSON.stringify({ note }) });
  await refreshAll();
}

$("refreshOrders").onclick = refreshAll;
$("orderStatusFilter").onchange = refreshAll;
```

- [ ] **Step 5: Run static UI tests**

Run:

```powershell
python -m pytest -q G:\tests\test_agent_workbench_ui.py::test_commercial_shop_page_exposes_manual_payment_flow G:\tests\test_agent_workbench_ui.py::test_commercial_admin_exposes_order_management_tab
```

Expected: 2 passed.

- [ ] **Step 6: Run JS syntax check for any touched JS file**

The customer/admin pages use inline JS, so also run the existing app JS check:

```powershell
node --check G:\app\static\studio.js
```

Expected: no output and exit code 0.

- [ ] **Step 7: Record checkpoint**

Run:

```powershell
git status --short
```

If git works:

```powershell
git add G:\app\static\commercial_shop.html G:\app\static\commercial_admin.html G:\tests\test_agent_workbench_ui.py
git commit -m "feat: add manual payment order UI"
```

---

### Task 5: Full Verification and Runtime Sync

**Files:**
- Sync to: `G:\dist\desktop-cloud-providers-v2\win-unpacked\resources\app`

- [ ] **Step 1: Run focused backend and UI tests**

Run:

```powershell
python -m pytest -q G:\tests\test_manual_payment_orders.py G:\tests\test_commercial_center.py G:\tests\test_agent_workbench_ui.py
```

Expected: all selected tests pass.

- [ ] **Step 2: Compile Python**

Run:

```powershell
python -m compileall G:\app\commercial_center.py G:\app\main.py
```

Expected: both files compile successfully.

- [ ] **Step 3: Sync changed files to desktop runtime**

Run these PowerShell copy commands:

```powershell
$runtime = "G:\dist\desktop-cloud-providers-v2\win-unpacked\resources\app"
Copy-Item -LiteralPath "G:\app\commercial_center.py" -Destination "$runtime\commercial_center.py" -Force
Copy-Item -LiteralPath "G:\app\static\commercial_admin.html" -Destination "$runtime\static\commercial_admin.html" -Force
Copy-Item -LiteralPath "G:\app\static\commercial_shop.html" -Destination "$runtime\static\commercial_shop.html" -Force
```

Expected: commands complete with no errors.

- [ ] **Step 4: Restart local backend on 8080**

Use the repo’s existing launcher process pattern. First check current Python processes:

```powershell
Get-Process python -ErrorAction SilentlyContinue | Select-Object Id,ProcessName,Path
```

Then stop only the known local backend process if it is serving the desktop app. Start the app using the same command currently used by this project. Confirm:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/health
```

Expected JSON includes:

```json
{"status":"ok","dry_run":false,"runtime_mode":"final","aivo_desktop_backend":true}
```

- [ ] **Step 5: Browser smoke checks**

Open these URLs in the browser:

```text
http://127.0.0.1:8080/shop
http://127.0.0.1:8080/admin
```

Verify:

- `/shop` shows package cards and can create a pending order.
- `/admin` has an “订单” tab.
- Admin can confirm the pending order.
- Customer order lookup shows a delivered license key after confirmation.

- [ ] **Step 6: Final regression command**

Run:

```powershell
python -m pytest -q G:\tests\test_manual_payment_orders.py G:\tests\test_commercial_center.py G:\tests\test_commercial_client_license.py G:\tests\test_agent_workbench_ui.py
node --check G:\app\static\studio.js
python -m compileall G:\app\commercial_center.py G:\app\main.py
```

Expected: pytest passes, node check passes, compileall passes.

---

## Self-Review

- Spec coverage:
  - Customer self-serve purchase: Task 1 and Task 4.
  - Manual evidence submission: Task 2 and Task 4.
  - Admin confirmation/reject/evidence/retry: Task 3 and Task 4.
  - Automatic license and credit delivery: Task 3.
  - Idempotent no-double-credit behavior: Task 3.
  - Audit trail: Task 1, Task 2, Task 3.
  - Future WeChat API compatibility: preserved by `orders` model and `confirm_order_payment` / `_fulfill_order_locked` boundary.
- Placeholder scan:
  - No unresolved placeholder markers.
  - No unbounded “handle errors” instruction; each error path names exact status and detail.
- Type consistency:
  - `product_id`, `product_type`, `credit_grant`, `order_no`, `order_id`, `payment_note`, and `payment_time` match the design document.
  - Admin routes all accept `OrderAdminActionRequest`.
  - Public routes return `{"order": ...}` consistently.
