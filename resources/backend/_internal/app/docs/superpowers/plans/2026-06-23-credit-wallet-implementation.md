# Credit Wallet Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current trial seconds model with a server-side credit wallet tied to license plans, charging 15 credits per generated second for Hifly/Flying-Shadow cloud usage.

**Architecture:** Keep the existing commercial center as the source of truth for customers, licenses, activations, and audit logs. Add credit fields and a transaction ledger to license records, expose reserve/commit/refund/admin-adjust APIs, and make desktop cloud calls reserve credits before hitting paid providers.

**Tech Stack:** FastAPI, Pydantic, file-backed commercial repository, vanilla HTML/CSS/JS admin page, pytest, existing desktop `CommercialLicenseClient`.

---

## File Structure

- Modify `G:\app\commercial_center.py`
  - Add credit constants, request models, license fields, transaction ledger helpers, credit APIs, yearly refresh, and backward-compatible `/license/usage/claim`.
- Modify `G:\app\commercial_client.py`
  - Add `reserve_credits`, `commit_credits`, and `refund_credits` methods.
- Modify `G:\app\main.py`
  - Replace direct seconds-claim calls with credit reserve/commit/refund helpers around paid cloud operations.
- Modify `G:\app\static\commercial_admin.html`
  - Replace “体验用量（秒）” with “赠送积分”, show balance and monthly usage, add adjust/refresh/detail controls.
- Modify `G:\tests\test_commercial_center.py`
  - Cover plan default credits, credit reserve/commit/refund, insufficient balance, yearly non-rollover refresh, and admin adjust.
- Modify `G:\tests\test_commercial_client_license.py`
  - Cover desktop credit API payloads.
- Modify `G:\tests\test_desktop_commercial_license_api.py`
  - Cover cloud-call helper behavior on reserve success, insufficient credits, and refund on provider failure.
- Modify `G:\tests\test_agent_workbench_ui.py`
  - Cover admin UI copy and controls.
- Sync changed runtime files into `G:\dist\desktop-cloud-providers-v2\win-unpacked\resources\app` after tests pass.

Current workspace note: `G:\app` is not a git repository. Use verification checkpoints after each task and skip git commit commands in this workspace. Suggested commit messages are included only for mirrored git checkouts.

---

### Task 1: License Credit Wallet Defaults

**Files:**
- Modify: `G:\tests\test_commercial_center.py`
- Modify: `G:\app\commercial_center.py`

- [ ] **Step 1: Write failing tests for plan default credits**

Append these tests after `test_trial_usage_claim_locks_license_and_paid_restore_reopens_it` in `G:\tests\test_commercial_center.py`:

```python
def test_license_plans_seed_default_credit_wallets(tmp_path: Path):
    with _client(tmp_path) as client:
        customer = client.post("/admin/api/customers", json={"name": "Credit Plans"})
        customer_id = customer.json()["customer_id"]

        cases = [
            ("trial", 1300),
            ("monthly", 48000),
            ("yearly", 48000),
        ]
        for plan, expected_credits in cases:
            created = client.post(
                "/admin/api/licenses",
                json={"customer_id": customer_id, "plan": plan, "max_devices": 1},
            )
            assert created.status_code == 200, created.text
            license_body = created.json()["license"]
            assert license_body["plan"] == plan
            assert license_body["credit_balance"] == expected_credits
            assert license_body["credit_granted_total"] == expected_credits
            assert license_body["credit_used_total"] == 0
            assert license_body["credit_plan_allowance"] == expected_credits
            assert license_body["credit_unit_price_hifly_per_second"] == 15
            assert license_body["credit_unlimited"] is False


def test_license_creation_allows_manual_credit_grant(tmp_path: Path):
    with _client(tmp_path) as client:
        customer = client.post("/admin/api/customers", json={"name": "Manual Credit"})
        created = client.post(
            "/admin/api/licenses",
            json={
                "customer_id": customer.json()["customer_id"],
                "plan": "custom",
                "max_devices": 1,
                "credit_grant": 2500,
            },
        )
        assert created.status_code == 200, created.text
        license_body = created.json()["license"]
        assert license_body["credit_balance"] == 2500
        assert license_body["credit_granted_total"] == 2500
        assert license_body["credit_plan_allowance"] == 2500
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest -q G:\tests\test_commercial_center.py::test_license_plans_seed_default_credit_wallets G:\tests\test_commercial_center.py::test_license_creation_allows_manual_credit_grant
```

Expected: both tests fail because `credit_balance` and `credit_grant` do not exist.

- [ ] **Step 3: Add constants and Pydantic fields**

In `G:\app\commercial_center.py`, near `_RATE_LIMITS`, add:

```python
PLAN_CREDIT_ALLOWANCES = {
    "trial": 1300,
    "monthly": 48000,
    "yearly": 48000,
}
HIFLY_CREDIT_PRICE_PER_SECOND = 15
```

In `LicenseCreateRequest`, add:

```python
    credit_grant: int | None = None
    credit_unlimited: bool = False
```

In `LicenseUpdateRequest`, add:

```python
    credit_balance: int | None = None
    credit_granted_total: int | None = None
    credit_used_total: int | None = None
    credit_plan_allowance: int | None = None
    credit_unit_price_hifly_per_second: int | None = None
    credit_unlimited: bool | None = None
    credit_period_started_at: str | None = None
    credit_period_ends_at: str | None = None
    credit_last_refreshed_at: str | None = None
```

In `LicenseRecord`, add:

```python
    credit_balance: int = 0
    credit_granted_total: int = 0
    credit_used_total: int = 0
    credit_plan_allowance: int = 0
    credit_unit_price_hifly_per_second: int = HIFLY_CREDIT_PRICE_PER_SECOND
    credit_period_started_at: str = ""
    credit_period_ends_at: str = ""
    credit_last_refreshed_at: str = ""
    credit_unlimited: bool = False
```

- [ ] **Step 4: Add credit helper methods**

Inside `CommercialCenterStore`, before `create_license`, add:

```python
    def _default_credit_grant(self, plan: str, requested: int | None) -> int:
        if requested is not None:
            if requested < 0:
                raise HTTPException(status_code=400, detail="credit_grant must be at least 0")
            return int(requested)
        return int(PLAN_CREDIT_ALLOWANCES.get((plan or "").strip(), 0))

    def _ensure_credit_fields(self, license_record: dict[str, Any]) -> dict[str, Any]:
        plan = str(license_record.get("plan") or "").strip()
        default_allowance = int(PLAN_CREDIT_ALLOWANCES.get(plan, 0))
        if "credit_balance" not in license_record:
            legacy_used_seconds = self._usage_used_seconds(license_record)
            legacy_cost = legacy_used_seconds * HIFLY_CREDIT_PRICE_PER_SECOND
            seeded = max(default_allowance - legacy_cost, 0)
            license_record["credit_balance"] = seeded
            license_record["credit_granted_total"] = default_allowance
            license_record["credit_used_total"] = min(legacy_cost, default_allowance)
            license_record["credit_plan_allowance"] = default_allowance
        license_record["credit_unit_price_hifly_per_second"] = int(
            license_record.get("credit_unit_price_hifly_per_second") or HIFLY_CREDIT_PRICE_PER_SECOND
        )
        license_record["credit_unlimited"] = bool(license_record.get("credit_unlimited", False))
        license_record["credit_period_started_at"] = str(license_record.get("credit_period_started_at") or "")
        license_record["credit_period_ends_at"] = str(license_record.get("credit_period_ends_at") or "")
        license_record["credit_last_refreshed_at"] = str(license_record.get("credit_last_refreshed_at") or "")
        return license_record
```

- [ ] **Step 5: Seed credit fields during license creation**

In `create_license`, after `feature_flags` is calculated, add:

```python
        credit_grant = self._default_credit_grant(request.plan, request.credit_grant)
        credit_period_started_at = _now() if request.plan == "yearly" else ""
        credit_period_ends_at = _next_credit_period_end(credit_period_started_at) if request.plan == "yearly" else ""
```

Add this helper near `_parse_version`:

```python
def _next_credit_period_end(started_at: str) -> str:
    if not started_at:
        return ""
    started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    month = started.month + 1
    year = started.year
    if month > 12:
        month = 1
        year += 1
    return started.replace(year=year, month=month).isoformat()
```

Add these arguments to `LicenseRecord(...)` in `create_license`:

```python
            credit_balance=credit_grant,
            credit_granted_total=credit_grant,
            credit_used_total=0,
            credit_plan_allowance=credit_grant,
            credit_unit_price_hifly_per_second=HIFLY_CREDIT_PRICE_PER_SECOND,
            credit_period_started_at=credit_period_started_at,
            credit_period_ends_at=credit_period_ends_at,
            credit_last_refreshed_at=credit_period_started_at,
            credit_unlimited=request.credit_unlimited,
```

- [ ] **Step 6: Expose credit fields publicly**

At the start of `_public_license`, after `public = dict(license_record)`, add:

```python
        self._ensure_credit_fields(public)
```

Then add these public fields before the `if data:` block:

```python
        public["credit_balance"] = int(public.get("credit_balance") or 0)
        public["credit_granted_total"] = int(public.get("credit_granted_total") or 0)
        public["credit_used_total"] = int(public.get("credit_used_total") or 0)
        public["credit_plan_allowance"] = int(public.get("credit_plan_allowance") or 0)
        public["credit_unit_price_hifly_per_second"] = int(
            public.get("credit_unit_price_hifly_per_second") or HIFLY_CREDIT_PRICE_PER_SECOND
        )
        public["credit_unlimited"] = bool(public.get("credit_unlimited", False))
```

- [ ] **Step 7: Run tests to verify Task 1 passes**

Run:

```powershell
python -m pytest -q G:\tests\test_commercial_center.py::test_license_plans_seed_default_credit_wallets G:\tests\test_commercial_center.py::test_license_creation_allows_manual_credit_grant
```

Expected: both tests pass.

- [ ] **Step 8: Verification checkpoint**

Run:

```powershell
python -m compileall G:\app\commercial_center.py
```

Expected: exit code 0.

Suggested commit if using git: `feat: seed license credit wallet defaults`.

---

### Task 2: Credit Reservation, Commit, Refund, And Ledger

**Files:**
- Modify: `G:\tests\test_commercial_center.py`
- Modify: `G:\app\commercial_center.py`

- [ ] **Step 1: Write failing credit flow tests**

Append these tests to `G:\tests\test_commercial_center.py`:

```python
def _create_credit_license(client: TestClient, *, plan: str = "trial", credit_grant: int | None = None) -> tuple[str, str, str]:
    customer = client.post("/admin/api/customers", json={"name": f"Credit {plan}"})
    payload = {"customer_id": customer.json()["customer_id"], "plan": plan, "max_devices": 1}
    if credit_grant is not None:
        payload["credit_grant"] = credit_grant
    created = client.post("/admin/api/licenses", json=payload)
    license_key = created.json()["license_key"]
    license_id = created.json()["license"]["license_id"]
    activated = client.post("/activation/activate", json={"license_key": license_key, "machine_code": "credit-machine"})
    token = activated.json()["activation"]["activation_token"]
    return license_key, license_id, token


def test_credit_reserve_commit_and_refund_flow(tmp_path: Path):
    with _client(tmp_path) as client:
        _, license_id, token = _create_credit_license(client, credit_grant=1300)

        reserve = client.post(
            "/license/credits/reserve",
            json={
                "activation_token": token,
                "machine_code": "credit-machine",
                "provider": "hifly",
                "feature": "hifly_video",
                "seconds": 10,
                "task_id": "task_credit_1",
            },
        )
        assert reserve.status_code == 200, reserve.text
        reservation_id = reserve.json()["reservation_id"]
        assert reserve.json()["cost_credits"] == 150
        assert reserve.json()["balance_after"] == 1150

        commit = client.post(
            "/license/credits/commit",
            json={"reservation_id": reservation_id, "task_id": "task_credit_1", "actual_seconds": 10},
        )
        assert commit.status_code == 200, commit.text
        assert commit.json()["consumed"] is True
        assert commit.json()["balance_after"] == 1150

        reserve_2 = client.post(
            "/license/credits/reserve",
            json={
                "activation_token": token,
                "machine_code": "credit-machine",
                "provider": "hifly",
                "feature": "hifly_video",
                "seconds": 5,
                "task_id": "task_credit_2",
            },
        )
        refund = client.post(
            "/license/credits/refund",
            json={"reservation_id": reserve_2.json()["reservation_id"], "task_id": "task_credit_2", "reason": "provider_failed"},
        )
        assert refund.status_code == 200, refund.text
        assert refund.json()["refunded"] is True
        assert refund.json()["balance_after"] == 1150

        licenses = client.get("/admin/api/licenses").json()
        license_body = next(item for item in licenses if item["license_id"] == license_id)
        assert license_body["credit_balance"] == 1150
        assert license_body["credit_used_total"] == 150


def test_credit_reserve_blocks_when_balance_is_insufficient(tmp_path: Path):
    with _client(tmp_path) as client:
        _, _, token = _create_credit_license(client, credit_grant=100)
        reserve = client.post(
            "/license/credits/reserve",
            json={
                "activation_token": token,
                "machine_code": "credit-machine",
                "provider": "hifly",
                "feature": "hifly_video",
                "seconds": 10,
                "task_id": "task_too_expensive",
            },
        )
        assert reserve.status_code == 403
        assert reserve.json()["detail"] == "license_credit_insufficient"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest -q G:\tests\test_commercial_center.py::test_credit_reserve_commit_and_refund_flow G:\tests\test_commercial_center.py::test_credit_reserve_blocks_when_balance_is_insufficient
```

Expected: both tests fail with 404 for missing credit endpoints.

- [ ] **Step 3: Extend empty data shape**

In `CommercialCenterStore._empty`, change the return shape to include `credit_transactions`:

```python
        return {"customers": {}, "licenses": {}, "activations": {}, "releases": {}, "audit_logs": [], "credit_transactions": {}}
```

In `_load`, after reading data, ensure missing legacy data gets the key:

```python
        data.setdefault("credit_transactions", {})
```

- [ ] **Step 4: Add request models**

In `G:\app\commercial_center.py`, after `LicenseUsageClaimRequest`, add:

```python
class CreditReserveRequest(BaseModel):
    activation_token: str
    machine_id: str = ""
    machine_code: str = ""
    provider: str = "hifly"
    feature: str = "hifly_video"
    seconds: int
    task_id: str = ""
    context: dict[str, Any] = Field(default_factory=dict)

    def machine_code_value(self) -> str:
        return (self.machine_code or self.machine_id or "").strip()


class CreditCommitRequest(BaseModel):
    reservation_id: str
    task_id: str = ""
    actual_seconds: int | None = None


class CreditRefundRequest(BaseModel):
    reservation_id: str
    task_id: str = ""
    reason: str = ""
```

- [ ] **Step 5: Add transaction helpers**

Inside `CommercialCenterStore`, before `claim_usage`, add:

```python
    def _credit_cost(self, license_record: dict[str, Any], seconds: int, provider: str) -> int:
        clean_seconds = max(int(seconds or 0), 1)
        if provider == "hifly":
            price = int(license_record.get("credit_unit_price_hifly_per_second") or HIFLY_CREDIT_PRICE_PER_SECOND)
        else:
            price = HIFLY_CREDIT_PRICE_PER_SECOND
        return clean_seconds * price

    def _credit_txn(
        self,
        data: dict[str, Any],
        *,
        license_record: dict[str, Any],
        activation: dict[str, Any] | None,
        txn_type: str,
        amount: int,
        feature: str = "",
        seconds: int = 0,
        provider: str = "",
        task_id: str = "",
        status: str = "completed",
        note: str = "",
        context: dict[str, Any] | None = None,
        reservation_id: str = "",
    ) -> dict[str, Any]:
        txn_id = reservation_id or f"ctxn_{uuid4().hex[:16]}"
        row = {
            "credit_txn_id": txn_id,
            "license_id": license_record.get("license_id", ""),
            "customer_id": license_record.get("customer_id", ""),
            "activation_id": activation.get("activation_id", "") if activation else "",
            "type": txn_type,
            "amount": int(amount),
            "balance_after": int(license_record.get("credit_balance") or 0),
            "feature": feature,
            "seconds": int(seconds or 0),
            "provider": provider,
            "task_id": task_id,
            "status": status,
            "note": note,
            "context": context or {},
            "created_at": _now(),
        }
        data.setdefault("credit_transactions", {})[txn_id] = row
        return row
```

- [ ] **Step 6: Add reserve/commit/refund methods**

Inside `CommercialCenterStore`, add:

```python
    def reserve_credits(self, request: CreditReserveRequest) -> dict[str, Any]:
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
        self._ensure_credit_fields(license_record)
        self._refresh_yearly_credit_period_if_needed(data, license_record)
        seconds = max(int(request.seconds or 0), 1)
        cost = self._credit_cost(license_record, seconds, request.provider)
        if not license_record.get("credit_unlimited"):
            balance = int(license_record.get("credit_balance") or 0)
            if balance < cost:
                raise HTTPException(status_code=403, detail="license_credit_insufficient")
            license_record["credit_balance"] = balance - cost
        txn = self._credit_txn(
            data,
            license_record=license_record,
            activation=activation,
            txn_type="reserve",
            amount=-cost,
            feature=request.feature,
            seconds=seconds,
            provider=request.provider,
            task_id=request.task_id,
            status="reserved",
            context=request.context,
        )
        license_record["updated_at"] = _now()
        self._save(data)
        return {
            "reserved": True,
            "reservation_id": txn["credit_txn_id"],
            "cost_credits": cost,
            "balance_after": int(license_record.get("credit_balance") or 0),
            "credit_unlimited": bool(license_record.get("credit_unlimited", False)),
        }

    def commit_credits(self, request: CreditCommitRequest) -> dict[str, Any]:
        data = self._load()
        txn = data.setdefault("credit_transactions", {}).get(request.reservation_id)
        if not txn:
            raise HTTPException(status_code=404, detail="credit_reservation_not_found")
        if txn.get("status") == "consumed":
            return {"consumed": True, "reservation_id": request.reservation_id, "balance_after": txn.get("balance_after", 0)}
        if txn.get("status") != "reserved":
            raise HTTPException(status_code=409, detail="credit_reservation_not_reserved")
        license_record = data["licenses"].get(txn["license_id"])
        if not license_record:
            raise HTTPException(status_code=404, detail="license not found")
        self._ensure_credit_fields(license_record)
        txn["status"] = "consumed"
        txn["type"] = "consume"
        txn["task_id"] = request.task_id or txn.get("task_id", "")
        if request.actual_seconds is not None:
            txn["actual_seconds"] = max(int(request.actual_seconds), 0)
        license_record["credit_used_total"] = int(license_record.get("credit_used_total") or 0) + abs(int(txn.get("amount") or 0))
        license_record["updated_at"] = _now()
        txn["balance_after"] = int(license_record.get("credit_balance") or 0)
        self._save(data)
        return {
            "consumed": True,
            "reservation_id": request.reservation_id,
            "final_cost_credits": abs(int(txn.get("amount") or 0)),
            "balance_after": int(license_record.get("credit_balance") or 0),
        }

    def refund_credits(self, request: CreditRefundRequest) -> dict[str, Any]:
        data = self._load()
        txn = data.setdefault("credit_transactions", {}).get(request.reservation_id)
        if not txn:
            raise HTTPException(status_code=404, detail="credit_reservation_not_found")
        if txn.get("status") == "refunded":
            return {"refunded": True, "reservation_id": request.reservation_id, "balance_after": txn.get("balance_after", 0)}
        if txn.get("status") != "reserved":
            raise HTTPException(status_code=409, detail="credit_reservation_not_reserved")
        license_record = data["licenses"].get(txn["license_id"])
        if not license_record:
            raise HTTPException(status_code=404, detail="license not found")
        self._ensure_credit_fields(license_record)
        refund_amount = abs(int(txn.get("amount") or 0))
        if not license_record.get("credit_unlimited"):
            license_record["credit_balance"] = int(license_record.get("credit_balance") or 0) + refund_amount
        txn["status"] = "refunded"
        txn["type"] = "refund"
        txn["task_id"] = request.task_id or txn.get("task_id", "")
        txn["note"] = request.reason
        txn["balance_after"] = int(license_record.get("credit_balance") or 0)
        license_record["updated_at"] = _now()
        self._save(data)
        return {
            "refunded": True,
            "reservation_id": request.reservation_id,
            "refund_credits": refund_amount,
            "balance_after": int(license_record.get("credit_balance") or 0),
        }
```

Add a no-op yearly refresh helper now; Task 3 will complete it:

```python
    def _refresh_yearly_credit_period_if_needed(self, data: dict[str, Any], license_record: dict[str, Any]) -> None:
        self._ensure_credit_fields(license_record)
```

- [ ] **Step 7: Add FastAPI routes**

Near the existing `/license/usage/claim` route in `G:\app\commercial_center.py`, add:

```python
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
    store: CommercialCenterStore = Depends(get_commercial_store),
) -> dict[str, Any]:
    return store.commit_credits(request)


@router.post("/license/credits/refund")
def refund_license_credits(
    request: CreditRefundRequest,
    store: CommercialCenterStore = Depends(get_commercial_store),
) -> dict[str, Any]:
    return store.refund_credits(request)
```

- [ ] **Step 8: Update compatibility `/license/usage/claim`**

In `claim_usage`, replace direct seconds counting with a reserve and commit:

```python
        reserve = self.reserve_credits(
            CreditReserveRequest(
                activation_token=request.activation_token,
                machine_code=request.machine_code,
                machine_id=request.machine_id,
                provider="hifly",
                feature=request.feature or "legacy_usage_claim",
                seconds=request.usage_seconds,
                task_id=str(request.context.get("task_id", "")) if isinstance(request.context, dict) else "",
                context=request.context,
            )
        )
        self.commit_credits(CreditCommitRequest(reservation_id=reserve["reservation_id"], task_id=reserve.get("task_id", "")))
```

Return a compatibility response:

```python
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
            "credits": reserve,
        }
```

The `reserve_credits` response must include `"license_id": license_record.get("license_id")` so this compatibility endpoint can return the license id without reloading or guessing.

- [ ] **Step 9: Run tests to verify Task 2 passes**

Run:

```powershell
python -m pytest -q G:\tests\test_commercial_center.py::test_credit_reserve_commit_and_refund_flow G:\tests\test_commercial_center.py::test_credit_reserve_blocks_when_balance_is_insufficient G:\tests\test_commercial_center.py::test_trial_usage_claim_locks_license_and_paid_restore_reopens_it
```

Expected: all tests pass. If the old trial usage lock test is intentionally superseded by credits, update it to assert `license_credit_insufficient` behavior through the credit API instead of seconds lock.

- [ ] **Step 10: Verification checkpoint**

Run:

```powershell
python -m compileall G:\app\commercial_center.py
```

Expected: exit code 0.

Suggested commit if using git: `feat: add credit reserve commit refund ledger`.

---

### Task 3: Yearly Monthly Refresh And Admin Credit Adjustments

**Files:**
- Modify: `G:\tests\test_commercial_center.py`
- Modify: `G:\app\commercial_center.py`

- [ ] **Step 1: Write failing tests for yearly non-rollover and admin adjustment**

Append these tests to `G:\tests\test_commercial_center.py`:

```python
def test_yearly_credit_refresh_resets_balance_without_rollover(tmp_path: Path):
    with _client(tmp_path) as client:
        customer = client.post("/admin/api/customers", json={"name": "Yearly Refresh"})
        created = client.post(
            "/admin/api/licenses",
            json={"customer_id": customer.json()["customer_id"], "plan": "yearly", "max_devices": 1},
        )
        license_id = created.json()["license"]["license_id"]

        patched = client.patch(
            f"/admin/api/licenses/{license_id}",
            json={
                "credit_balance": 100,
                "credit_used_total": 47900,
                "credit_period_started_at": "2026-05-01T00:00:00+00:00",
                "credit_period_ends_at": "2026-06-01T00:00:00+00:00",
            },
        )
        assert patched.status_code == 200, patched.text

        refreshed = client.post(f"/admin/api/licenses/{license_id}/credits/refresh-period")
        assert refreshed.status_code == 200, refreshed.text
        body = refreshed.json()
        assert body["credit_balance"] == 48000
        assert body["credit_granted_total"] == 96000
        assert body["credit_plan_allowance"] == 48000
        assert body["credit_used_total"] == 47900


def test_admin_can_adjust_license_credits_with_audit_log(tmp_path: Path):
    with _client(tmp_path) as client:
        customer = client.post("/admin/api/customers", json={"name": "Adjust Credit"})
        created = client.post(
            "/admin/api/licenses",
            json={"customer_id": customer.json()["customer_id"], "plan": "trial", "max_devices": 1},
        )
        license_id = created.json()["license"]["license_id"]

        add = client.post(
            f"/admin/api/licenses/{license_id}/credits/adjust",
            json={"amount": 200, "note": "manual top-up"},
        )
        assert add.status_code == 200, add.text
        assert add.json()["credit_balance"] == 1500

        deduct = client.post(
            f"/admin/api/licenses/{license_id}/credits/adjust",
            json={"amount": -300, "note": "manual correction"},
        )
        assert deduct.status_code == 200, deduct.text
        assert deduct.json()["credit_balance"] == 1200

        audit = client.get("/admin/api/audit-logs").json()
        actions = [row["action"] for row in audit]
        assert "license.credit_adjust" in actions
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest -q G:\tests\test_commercial_center.py::test_yearly_credit_refresh_resets_balance_without_rollover G:\tests\test_commercial_center.py::test_admin_can_adjust_license_credits_with_audit_log
```

Expected: both tests fail because admin credit routes do not exist.

- [ ] **Step 3: Add admin request models**

In `G:\app\commercial_center.py`, after `CreditRefundRequest`, add:

```python
class CreditAdjustRequest(BaseModel):
    amount: int
    note: str = ""


class CreditRefreshRequest(BaseModel):
    note: str = "manual refresh"
```

- [ ] **Step 4: Implement adjust and refresh methods**

Inside `CommercialCenterStore`, add:

```python
    def adjust_credits(self, license_id: str, request: CreditAdjustRequest) -> dict[str, Any]:
        data = self._load()
        license_record = data["licenses"].get(license_id)
        if not license_record:
            raise HTTPException(status_code=404, detail="license not found")
        self._ensure_credit_fields(license_record)
        before = self._public_license(license_record, data=data)
        amount = int(request.amount)
        new_balance = int(license_record.get("credit_balance") or 0) + amount
        if new_balance < 0:
            raise HTTPException(status_code=400, detail="credit_balance_cannot_be_negative")
        license_record["credit_balance"] = new_balance
        if amount > 0:
            license_record["credit_granted_total"] = int(license_record.get("credit_granted_total") or 0) + amount
        else:
            license_record["credit_used_total"] = int(license_record.get("credit_used_total") or 0) + abs(amount)
        license_record["updated_at"] = _now()
        self._credit_txn(
            data,
            license_record=license_record,
            activation=None,
            txn_type="adjust",
            amount=amount,
            note=request.note,
            status="completed",
        )
        after = self._public_license(license_record, data=data)
        self._append_audit(data, "license.credit_adjust", "license", license_id, before=before, after=after)
        self._save(data)
        return after

    def refresh_credit_period(self, license_id: str, request: CreditRefreshRequest | None = None) -> dict[str, Any]:
        data = self._load()
        license_record = data["licenses"].get(license_id)
        if not license_record:
            raise HTTPException(status_code=404, detail="license not found")
        self._ensure_credit_fields(license_record)
        before = self._public_license(license_record, data=data)
        allowance = int(license_record.get("credit_plan_allowance") or PLAN_CREDIT_ALLOWANCES.get(license_record.get("plan"), 0) or 0)
        now_text = _now()
        license_record["credit_balance"] = allowance
        license_record["credit_granted_total"] = int(license_record.get("credit_granted_total") or 0) + allowance
        license_record["credit_period_started_at"] = now_text
        license_record["credit_period_ends_at"] = _next_credit_period_end(now_text)
        license_record["credit_last_refreshed_at"] = now_text
        license_record["updated_at"] = now_text
        self._credit_txn(
            data,
            license_record=license_record,
            activation=None,
            txn_type="monthly_refresh",
            amount=allowance,
            note=(request.note if request else "manual refresh"),
            status="completed",
        )
        after = self._public_license(license_record, data=data)
        self._append_audit(data, "license.credit_refresh", "license", license_id, before=before, after=after)
        self._save(data)
        return after
```

- [ ] **Step 5: Complete automatic yearly refresh helper**

Replace `_refresh_yearly_credit_period_if_needed` with:

```python
    def _refresh_yearly_credit_period_if_needed(self, data: dict[str, Any], license_record: dict[str, Any]) -> None:
        self._ensure_credit_fields(license_record)
        if license_record.get("plan") != "yearly":
            return
        ends_at = str(license_record.get("credit_period_ends_at") or "")
        if not ends_at:
            now_text = _now()
            license_record["credit_period_started_at"] = now_text
            license_record["credit_period_ends_at"] = _next_credit_period_end(now_text)
            license_record["credit_last_refreshed_at"] = now_text
            return
        try:
            expires = datetime.fromisoformat(ends_at.replace("Z", "+00:00"))
        except ValueError:
            return
        if expires <= datetime.now(timezone.utc):
            allowance = int(license_record.get("credit_plan_allowance") or PLAN_CREDIT_ALLOWANCES["yearly"])
            now_text = _now()
            license_record["credit_balance"] = allowance
            license_record["credit_granted_total"] = int(license_record.get("credit_granted_total") or 0) + allowance
            license_record["credit_period_started_at"] = now_text
            license_record["credit_period_ends_at"] = _next_credit_period_end(now_text)
            license_record["credit_last_refreshed_at"] = now_text
            license_record["updated_at"] = now_text
            self._credit_txn(
                data,
                license_record=license_record,
                activation=None,
                txn_type="monthly_refresh",
                amount=allowance,
                note="automatic yearly monthly allowance refresh",
                status="completed",
            )
```

- [ ] **Step 6: Add admin routes**

Near `restore_paid_license`, add:

```python
@router.post("/admin/api/licenses/{license_id}/credits/adjust", dependencies=[Depends(require_admin_access)])
def adjust_license_credits(
    license_id: str,
    request: CreditAdjustRequest,
    store: CommercialCenterStore = Depends(get_commercial_store),
) -> dict[str, Any]:
    return store.adjust_credits(license_id, request)


@router.post("/admin/api/licenses/{license_id}/credits/refresh-period", dependencies=[Depends(require_admin_access)])
def refresh_license_credit_period(
    license_id: str,
    request: CreditRefreshRequest = CreditRefreshRequest(),
    store: CommercialCenterStore = Depends(get_commercial_store),
) -> dict[str, Any]:
    return store.refresh_credit_period(license_id, request)
```

- [ ] **Step 7: Run tests to verify Task 3 passes**

Run:

```powershell
python -m pytest -q G:\tests\test_commercial_center.py::test_yearly_credit_refresh_resets_balance_without_rollover G:\tests\test_commercial_center.py::test_admin_can_adjust_license_credits_with_audit_log
```

Expected: both tests pass.

- [ ] **Step 8: Verification checkpoint**

Run:

```powershell
python -m compileall G:\app\commercial_center.py
```

Expected: exit code 0.

Suggested commit if using git: `feat: add yearly credit refresh and admin adjustment`.

---

### Task 4: Desktop Credit Client And Paid Cloud Call Wrapping

**Files:**
- Modify: `G:\tests\test_commercial_client_license.py`
- Modify: `G:\tests\test_desktop_commercial_license_api.py`
- Modify: `G:\app\commercial_client.py`
- Modify: `G:\app\main.py`

- [ ] **Step 1: Write failing client method tests**

In `G:\tests\test_commercial_client_license.py`, extend `FakeCommercialApi.__call__` with these responses:

```python
        if url.endswith("/license/credits/reserve"):
            return {
                "reserved": True,
                "reservation_id": "ctxn_demo",
                "cost_credits": 150,
                "balance_after": 1150,
            }
        if url.endswith("/license/credits/commit"):
            return {
                "consumed": True,
                "reservation_id": payload["reservation_id"],
                "final_cost_credits": 150,
                "balance_after": 1150,
            }
        if url.endswith("/license/credits/refund"):
            return {
                "refunded": True,
                "reservation_id": payload["reservation_id"],
                "refund_credits": 150,
                "balance_after": 1300,
            }
```

Append this test:

```python
def test_credit_reserve_commit_and_refund_client_payloads(tmp_path: Path):
    fake_api = FakeCommercialApi()
    client = _client(tmp_path, fake_api)
    client.activate("AIVO-SECRET-LICENSE-KEY", app_version="1.0.0")
    fake_api.calls.clear()

    reserve = client.reserve_credits(provider="hifly", feature="hifly_video", seconds=10, task_id="task_001")
    commit = client.commit_credits(reserve["reservation_id"], task_id="task_001", actual_seconds=10)
    refund = client.refund_credits(reserve["reservation_id"], task_id="task_001", reason="provider_failed")

    assert reserve["reservation_id"] == "ctxn_demo"
    assert commit["consumed"] is True
    assert refund["refunded"] is True
    assert fake_api.calls[0][1] == "https://api.example.test/license/credits/reserve"
    assert fake_api.calls[0][2]["activation_token"] == "act_token_demo"
    assert fake_api.calls[0][2]["machine_code"] == "machine-001"
    assert fake_api.calls[0][2]["seconds"] == 10
    assert fake_api.calls[1][1] == "https://api.example.test/license/credits/commit"
    assert fake_api.calls[2][1] == "https://api.example.test/license/credits/refund"
```

- [ ] **Step 2: Run client test to verify it fails**

Run:

```powershell
python -m pytest -q G:\tests\test_commercial_client_license.py::test_credit_reserve_commit_and_refund_client_payloads
```

Expected: fail with missing `reserve_credits`.

- [ ] **Step 3: Add client methods**

In `G:\app\commercial_client.py`, after `claim_usage`, add:

```python
    def reserve_credits(
        self,
        *,
        provider: str,
        feature: str,
        seconds: int,
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
            "provider": provider,
            "feature": feature,
            "seconds": max(int(seconds or 0), 1),
            "task_id": task_id,
            "context": context or {},
        }
        return self.request_json("POST", self._url("/license/credits/reserve"), payload)

    def commit_credits(self, reservation_id: str, *, task_id: str = "", actual_seconds: int | None = None) -> dict[str, Any]:
        payload = {"reservation_id": reservation_id, "task_id": task_id, "actual_seconds": actual_seconds}
        return self.request_json("POST", self._url("/license/credits/commit"), payload)

    def refund_credits(self, reservation_id: str, *, task_id: str = "", reason: str = "") -> dict[str, Any]:
        payload = {"reservation_id": reservation_id, "task_id": task_id, "reason": reason}
        return self.request_json("POST", self._url("/license/credits/refund"), payload)
```

- [ ] **Step 4: Run client test to verify it passes**

Run:

```powershell
python -m pytest -q G:\tests\test_commercial_client_license.py::test_credit_reserve_commit_and_refund_client_payloads
```

Expected: pass.

- [ ] **Step 5: Write failing main helper tests**

In `G:\tests\test_desktop_commercial_license_api.py`, extend `FakeDesktopLicenseClient` with:

```python
        self.reserved: list[dict] = []
        self.committed: list[dict] = []
        self.refunded: list[dict] = []
        self.reserve_error: Exception | None = None
```

Add methods:

```python
    def reserve_credits(self, *, provider: str, feature: str, seconds: int, task_id: str = "", context: dict | None = None) -> dict:
        self.reserved.append({"provider": provider, "feature": feature, "seconds": seconds, "task_id": task_id, "context": context or {}})
        if self.reserve_error:
            raise self.reserve_error
        return {"reserved": True, "reservation_id": "ctxn_test", "cost_credits": seconds * 15, "balance_after": 1000}

    def commit_credits(self, reservation_id: str, *, task_id: str = "", actual_seconds: int | None = None) -> dict:
        self.committed.append({"reservation_id": reservation_id, "task_id": task_id, "actual_seconds": actual_seconds})
        return {"consumed": True, "reservation_id": reservation_id}

    def refund_credits(self, reservation_id: str, *, task_id: str = "", reason: str = "") -> dict:
        self.refunded.append({"reservation_id": reservation_id, "task_id": task_id, "reason": reason})
        return {"refunded": True, "reservation_id": reservation_id}
```

Append tests:

```python
def test_credit_reserve_helper_blocks_on_insufficient_credits(tmp_path: Path):
    fake = FakeDesktopLicenseClient()
    fake.reserve_error = CommercialLicenseHttpError(403, "license_credit_insufficient")
    settings = Settings(storage_dir=tmp_path, commercial_license_required=True)

    with pytest.raises(HTTPException) as exc:
        main._reserve_commercial_credits_or_raise(
            settings,
            fake,
            provider="hifly",
            feature="hifly_video",
            seconds=10,
            task_id="task_1",
            context={},
        )

    assert exc.value.status_code == 403
    assert "积分不足" in str(exc.value.detail)


def test_credit_commit_and_refund_helpers_call_client(tmp_path: Path):
    fake = FakeDesktopLicenseClient()
    settings = Settings(storage_dir=tmp_path, commercial_license_required=True)

    reservation = main._reserve_commercial_credits_or_raise(
        settings,
        fake,
        provider="hifly",
        feature="hifly_video",
        seconds=10,
        task_id="task_1",
        context={},
    )
    main._commit_commercial_credits(settings, fake, reservation, task_id="task_1", actual_seconds=10)
    main._refund_commercial_credits(settings, fake, reservation, task_id="task_1", reason="provider_failed")

    assert fake.reserved[0]["seconds"] == 10
    assert fake.committed[0]["reservation_id"] == "ctxn_test"
    assert fake.refunded[0]["reason"] == "provider_failed"
```

- [ ] **Step 6: Run main helper tests to verify they fail**

Run:

```powershell
python -m pytest -q G:\tests\test_desktop_commercial_license_api.py::test_credit_reserve_helper_blocks_on_insufficient_credits G:\tests\test_desktop_commercial_license_api.py::test_credit_commit_and_refund_helpers_call_client
```

Expected: fail with missing helper functions.

- [ ] **Step 7: Add main helper functions**

In `G:\app\main.py`, near `_claim_commercial_usage_or_raise`, add:

```python
def _reserve_commercial_credits_or_raise(
    settings: Settings,
    license_client: CommercialLicenseClient,
    *,
    provider: str,
    feature: str,
    seconds: int,
    task_id: str = "",
    context: dict[str, object] | None = None,
) -> dict[str, object]:
    if not settings.commercial_license_required:
        return {"reserved": False, "skipped": True}
    try:
        return license_client.reserve_credits(
            provider=provider,
            feature=feature,
            seconds=max(int(seconds or 0), 1),
            task_id=task_id,
            context=context or {},
        )
    except CommercialLicenseHttpError as exc:
        messages = {
            "license_credit_insufficient": "积分不足，请续费或联系管理员充值。",
            "activation_token_invalid": "授权已失效，请重新激活。",
            "license_disabled": "授权已停用，请联系管理员。",
            "license_expired": "授权已过期，请续费后继续使用。",
        }
        raise HTTPException(status_code=exc.status_code, detail=messages.get(exc.detail, exc.detail)) from exc
    except CommercialLicenseError as exc:
        raise HTTPException(status_code=403, detail=f"授权校验失败：{exc}") from exc


def _commit_commercial_credits(
    settings: Settings,
    license_client: CommercialLicenseClient,
    reservation: dict[str, object],
    *,
    task_id: str = "",
    actual_seconds: int | None = None,
) -> None:
    if not settings.commercial_license_required or reservation.get("skipped"):
        return
    reservation_id = str(reservation.get("reservation_id") or "")
    if reservation_id:
        license_client.commit_credits(reservation_id, task_id=task_id, actual_seconds=actual_seconds)


def _refund_commercial_credits(
    settings: Settings,
    license_client: CommercialLicenseClient,
    reservation: dict[str, object],
    *,
    task_id: str = "",
    reason: str = "",
) -> None:
    if not settings.commercial_license_required or reservation.get("skipped"):
        return
    reservation_id = str(reservation.get("reservation_id") or "")
    if reservation_id:
        license_client.refund_credits(reservation_id, task_id=task_id, reason=reason)
```

- [ ] **Step 8: Replace paid cloud call wrapping**

In `test_voice_profile`, replace the current `_claim_commercial_usage_or_raise` before cloud TTS with:

```python
    voice_reservation: dict[str, object] = {}
    if not settings.dry_run and getattr(tts, "name", "") in {"aliyun_bailian", "cloud_voice"}:
        voice_seconds = _estimate_cloud_usage_seconds(request.text)
        voice_reservation = _reserve_commercial_credits_or_raise(
            settings,
            license_client,
            provider="aliyun",
            feature="aliyun_voice_preview",
            seconds=voice_seconds,
            context={"digital_human_id": digital_human_id, "voice_profile_id": voice_profile_id},
        )
```

Wrap the synthesize call:

```python
    try:
        tts_result = await tts.synthesize(script_json=script_path, voice_profile=voice, out_dir=out_dir)
        _commit_commercial_credits(
            settings,
            license_client,
            voice_reservation,
            task_id=f"voice_test:{digital_human_id}:{voice_profile_id}",
            actual_seconds=_estimate_cloud_usage_seconds(request.text),
        )
    except AdapterError as exc:
        _refund_commercial_credits(
            settings,
            license_client,
            voice_reservation,
            task_id=f"voice_test:{digital_human_id}:{voice_profile_id}",
            reason=str(exc),
        )
        ...
```

Keep the existing error-report body after the refund call.

For Hifly avatar, voice, and video routes:

- Reserve before calling `workflow.create_hifly_avatar`, `workflow.create_hifly_voice`, or `workflow.generate_hifly_from_source_video`.
- Commit when the call returns a successful response or a completed task.
- Refund when an exception is raised or a returned task has `TaskStatus.failed`.

Use this pattern in `generate_hifly_source_video`:

```python
    reservation: dict[str, object] = {}
    if not settings.dry_run and request.confirm_paid_call:
        estimated_seconds = _estimate_cloud_usage_seconds(request.text, fallback_seconds=10)
        reservation = _reserve_commercial_credits_or_raise(
            settings,
            license_client,
            provider="hifly",
            feature="hifly_video",
            seconds=estimated_seconds,
            context={"digital_human_id": digital_human_id, "title": request.title},
        )
    task = store.create(...)
    task = await workflow.generate_hifly_from_source_video(store, task, request)
    if task.status == TaskStatus.failed:
        _refund_commercial_credits(settings, license_client, reservation, task_id=task.task_id, reason=task.error or "hifly_failed")
    else:
        _commit_commercial_credits(settings, license_client, reservation, task_id=task.task_id, actual_seconds=estimated_seconds)
```

- [ ] **Step 9: Run Task 4 tests**

Run:

```powershell
python -m pytest -q G:\tests\test_commercial_client_license.py::test_credit_reserve_commit_and_refund_client_payloads G:\tests\test_desktop_commercial_license_api.py::test_credit_reserve_helper_blocks_on_insufficient_credits G:\tests\test_desktop_commercial_license_api.py::test_credit_commit_and_refund_helpers_call_client
```

Expected: all tests pass.

- [ ] **Step 10: Verification checkpoint**

Run:

```powershell
python -m compileall G:\app\commercial_client.py G:\app\main.py
```

Expected: exit code 0.

Suggested commit if using git: `feat: gate paid cloud calls with credit reservations`.

---

### Task 5: Admin UI Credit Wallet Controls

**Files:**
- Modify: `G:\tests\test_agent_workbench_ui.py`
- Modify: `G:\app\static\commercial_admin.html`

- [ ] **Step 1: Replace UI test for seconds with credits**

In `G:\tests\test_agent_workbench_ui.py`, replace `test_commercial_admin_exposes_trial_usage_and_paid_restore_controls` with:

```python
def test_commercial_admin_exposes_credit_wallet_controls():
    commercial_admin = Path("G:/app/static/commercial_admin.html").read_text(encoding="utf-8")

    assert "赠送积分" in commercial_admin
    assert "剩余积分" in commercial_admin
    assert "本月已用" in commercial_admin
    assert "credit_balance" in commercial_admin
    assert "credit_grant" in commercial_admin
    assert "credits/adjust" in commercial_admin
    assert "credits/refresh-period" in commercial_admin
    assert "体验用量（秒）" not in commercial_admin
```

- [ ] **Step 2: Run UI test to verify it fails**

Run:

```powershell
python -m pytest -q G:\tests\test_agent_workbench_ui.py::test_commercial_admin_exposes_credit_wallet_controls
```

Expected: fail because the page still contains “体验用量（秒）” and lacks credit controls.

- [ ] **Step 3: Update create-license form**

In `G:\app\static\commercial_admin.html`, remove the old usage-seconds form control:

```html
<label>体验用量（秒）</label>
<input id="licenseUsageLimitSeconds" type="number" min="1" placeholder="试用版默认30秒；正式版留空不限时" />
```

and add the credit grant form control in its place:

```html
<label>赠送积分</label>
<input id="licenseCreditGrant" type="number" min="0" value="48000" placeholder="试用版1300；月付/年会员48000" />
```

Add this script near the `createLicense` handler:

```javascript
    const planCredits = { trial: 1300, monthly: 48000, yearly: 48000, lifetime: 0, custom: 0 };
    $("licensePlan").addEventListener("change", () => {
      $("licenseCreditGrant").value = String(planCredits[$("licensePlan").value] ?? 0);
    });
```

Change the payload code to:

```javascript
      const creditGrant = Number($("licenseCreditGrant").value || 0);
      if (creditGrant > 0) payload.credit_grant = creditGrant;
```

Remove all references to `licenseUsageLimitSeconds`.

- [ ] **Step 4: Update license table**

Change the license table header to:

```html
<thead><tr><th>授权码</th><th>客户</th><th>套餐</th><th>设备</th><th>积分</th><th>到期</th><th>状态</th><th>操作</th></tr></thead>
```

Replace `usageText(l)` with:

```javascript
    function creditText(l) {
      if (l.credit_unlimited) return "不限积分";
      const balance = Number(l.credit_balance || 0);
      const used = Number(l.credit_used_total || 0);
      const allowance = Number(l.credit_plan_allowance || 0);
      return `剩余积分：${balance}<br><small>本月已用：${used} / 额度：${allowance}</small>`;
    }
```

Change the table body cell from:

```javascript
<td>${usageText(l)}</td>
```

to:

```javascript
<td>${creditText(l)}</td>
```

- [ ] **Step 5: Add admin action buttons and handlers**

Inside the license action buttons, add:

```javascript
<button class="ghost" data-credit-add="${text(l.license_id)}">加积分</button>
<button class="warning" data-credit-refresh="${text(l.license_id)}">刷新本月</button>
```

After render listeners, add:

```javascript
      document.querySelectorAll("[data-credit-add]").forEach((button) => button.addEventListener("click", () => adjustCredits(button.dataset.creditAdd)));
      document.querySelectorAll("[data-credit-refresh]").forEach((button) => button.addEventListener("click", () => refreshCredits(button.dataset.creditRefresh)));
```

Add functions:

```javascript
    async function adjustCredits(id) {
      const amountText = prompt("请输入要调整的积分，正数为加积分，负数为扣积分。", "1000");
      if (amountText === null) return;
      const amount = Number(amountText);
      if (!Number.isFinite(amount) || amount === 0) {
        notice("请输入非零数字积分。", true);
        return;
      }
      await api(`/admin/api/licenses/${id}/credits/adjust`, {
        method: "POST",
        body: JSON.stringify({ amount, note: "后台手动调整" }),
      });
      await refreshAll();
    }

    async function refreshCredits(id) {
      if (!confirm("确定将这条年会员授权刷新为本月48000积分吗？未用完积分不会结转。")) return;
      await api(`/admin/api/licenses/${id}/credits/refresh-period`, {
        method: "POST",
        body: JSON.stringify({ note: "后台手动刷新本月积分" }),
      });
      await refreshAll();
    }
```

- [ ] **Step 6: Run UI test to verify Task 5 passes**

Run:

```powershell
python -m pytest -q G:\tests\test_agent_workbench_ui.py::test_commercial_admin_exposes_credit_wallet_controls
```

Expected: pass.

- [ ] **Step 7: Browser/runtime check**

Run:

```powershell
$html=(Invoke-WebRequest http://127.0.0.1:8080/admin -UseBasicParsing).Content
[pscustomobject]@{
  HasCreditGrant=$html.Contains('赠送积分')
  HasCreditBalance=$html.Contains('剩余积分')
  HasOldSeconds=$html.Contains('体验用量（秒）')
} | ConvertTo-Json
```

Expected before runtime sync: it may still show old content if runtime has not been copied. Final sync is Task 6.

Suggested commit if using git: `feat: expose credit wallet controls in admin UI`.

---

### Task 6: Full Verification And Desktop Runtime Sync

**Files:**
- Copy changed files from `G:\app` to `G:\dist\desktop-cloud-providers-v2\win-unpacked\resources\app`

- [ ] **Step 1: Run commercial backend tests**

Run:

```powershell
python -m pytest -q G:\tests\test_commercial_center.py G:\tests\test_commercial_client_license.py G:\tests\test_desktop_commercial_license_api.py
```

Expected: all tests pass.

- [ ] **Step 2: Run admin UI static test**

Run:

```powershell
python -m pytest -q G:\tests\test_agent_workbench_ui.py::test_commercial_admin_exposes_credit_wallet_controls
```

Expected: pass.

- [ ] **Step 3: Compile changed Python files**

Run:

```powershell
python -m compileall G:\app\commercial_center.py G:\app\commercial_client.py G:\app\main.py
```

Expected: exit code 0.

- [ ] **Step 4: Sync desktop runtime**

Run:

```powershell
$target='G:\dist\desktop-cloud-providers-v2\win-unpacked\resources\app'
Copy-Item G:\app\commercial_center.py (Join-Path $target 'commercial_center.py') -Force
Copy-Item G:\app\commercial_client.py (Join-Path $target 'commercial_client.py') -Force
Copy-Item G:\app\main.py (Join-Path $target 'main.py') -Force
Copy-Item G:\app\static\commercial_admin.html (Join-Path $target 'static\commercial_admin.html') -Force
```

Expected: no errors.

- [ ] **Step 5: Restart local 8080 backend**

Run:

```powershell
$pidToStop=(Get-NetTCPConnection -LocalPort 8080 -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty OwningProcess)
if($pidToStop){ Stop-Process -Id $pidToStop -Force; Start-Sleep -Seconds 1 }
Start-Process -FilePath powershell.exe -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','G:\dist\desktop-cloud-providers-v2\win-unpacked\resources\storage\desktop\start_cloud_backend.ps1' -WindowStyle Hidden
Start-Sleep -Seconds 3
Get-NetTCPConnection -LocalPort 8080 -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,State,OwningProcess
```

Expected: one `Listen` row on `127.0.0.1:8080`.

- [ ] **Step 6: Verify running service**

Run:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/health | ConvertTo-Json -Depth 4
$html=(Invoke-WebRequest http://127.0.0.1:8080/admin -UseBasicParsing).Content
[pscustomobject]@{
  HasCreditGrant=$html.Contains('赠送积分')
  HasCreditBalance=$html.Contains('剩余积分')
  HasOldSeconds=$html.Contains('体验用量（秒）')
} | ConvertTo-Json
```

Expected:

```json
{
  "status": "ok",
  "dry_run": false,
  "runtime_mode": "final",
  "aivo_desktop_backend": true
}
```

and:

```json
{
  "HasCreditGrant": true,
  "HasCreditBalance": true,
  "HasOldSeconds": false
}
```

- [ ] **Step 7: Record non-git checkpoint**

Because `G:\app` is not a git repository, record the changed file list in the final response:

```text
G:\app\commercial_center.py
G:\app\commercial_client.py
G:\app\main.py
G:\app\static\commercial_admin.html
G:\tests\test_commercial_center.py
G:\tests\test_commercial_client_license.py
G:\tests\test_desktop_commercial_license_api.py
G:\tests\test_agent_workbench_ui.py
```

Suggested commit if using git: `feat: deliver license credit wallet`.
