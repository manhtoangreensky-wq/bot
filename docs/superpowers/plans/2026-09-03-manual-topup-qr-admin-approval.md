# Manual Top-up QR and Admin Approval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Each checkbox is one bounded action with its own verification.

**Goal:** Restore one auditable manual top-up flow in which a customer selects an amount and QR payment method, receives the QR instructions, submits one bill, and Xu is credited only after an admin confirms the exact pending deposit.

**Architecture:** Keep the existing `pending_deposits` table as the durable approval queue. `USER_BILL_STATE` is only a short-lived customer draft; it never credits Xu. The customer path writes one `pending_admin_review` row after a bill/TXID is received, sends that row to the admin with deposit-scoped buttons, and the admin confirmation performs one SQLite transaction that credits the user and marks that same row `approved`.

**Tech Stack:** Python 3, `sqlite3` WAL, python-telegram-bot callbacks/messages, existing VietQR/static QR assets, pytest temporary databases.

**Spec:** `C:\Users\toann\Documents\Codex\2026-08-01\sua\work\payos-manual-topup\AGENTS.md` and the existing manual-payment history at commits `8a6ff00`, `3052e4a`, `ff9ffb5`, `2cd38bd`, `24284bd`, and `d2942c0`.

## Global Constraints

- Product scope is manual top-up through QR/bank bill review; do not change PayOS dynamic checkout or PayOS webhook behavior.
- Xu is added only after an admin confirmation callback or the equivalent admin command has atomically approved the exact pending deposit.
- A bill submission must leave `users.credits` and positive `credit_events` unchanged.
- Duplicate Telegram delivery of the same bill must not create a second active deposit.
- A duplicate admin approval must not add a second credit event or change the approved row again.
- Tests use temporary SQLite files; no real PayOS request, Telegram transfer, provider call, or production wallet mutation is allowed.
- Do not delete tables, migrate destructive data, change secrets/ENV, or touch SubDub, Product Video, WebApp, or the two locked SubDub files.

## Files and responsibilities

- `C:\Users\toann\Documents\Codex\2026-08-01\sua\work\payos-manual-topup\bot.py:18141-19030` — customer manual currency/amount/method menus, QR delivery, pending-deposit creation and admin notification.
- `C:\Users\toann\Documents\Codex\2026-08-01\sua\work\payos-manual-topup\bot.py:212804-213112` — `/naptien` and `/thucong` entry commands.
- `C:\Users\toann\Documents\Codex\2026-08-01\sua\work\payos-manual-topup\bot.py:43318-43680` — `manual|...` callback route, including amount, method, bill and admin approval buttons.
- `C:\Users\toann\Documents\Codex\2026-08-01\sua\work\payos-manual-topup\bot.py:226412-227620` — `/duyet`, `/tuchoi`, `/pending`, admin approval text and customer TXID intake.
- `C:\Users\toann\Documents\Codex\2026-08-01\sua\work\payos-manual-topup\bot.py:231864-232070` — customer bill-photo intake and admin notification.
- `C:\Users\toann\Documents\Codex\2026-08-01\sua\work\payos-manual-topup\tests\test_core.py:9761-10180` — existing manual-topup tests and temporary SQLite fixtures; add the focused regressions in this file.
- `C:\Users\toann\Documents\Codex\2026-08-01\sua\work\payos-manual-topup\tests\test_p0_17c3_payos_admin_risk_lock_review.py:1-460` — existing admin-risk/manual-deposit comparator; run it unchanged as a protected comparator.
- `C:\Users\toann\Documents\Codex\2026-08-01\sua\work\payos-manual-topup\TAI-LIEU\01-NGHIEP-VU-VAN-HANH.md` — measured current operational behavior; update only after tests have terminal output.
- `C:\Users\toann\Documents\Codex\2026-08-01\sua\work\payos-manual-topup\TAI-LIEU\02-CHUC-NANG-GOC-VA-HIEN-TAI.md` — original-versus-current function comparison; record the manual approval boundary here.

## Data matrix result

The required `ma-tran-du-lieu` scan was executed against this Python/SQLite repository and stopped without writing a matrix because no Drizzle schema, migration SQL, or `pb_schema.json` exists. Do not invent a table inventory. The authoritative schema source for this plan is the `CREATE TABLE IF NOT EXISTS pending_deposits`, `users`, `credit_events`, `payos_orders`, and `finance_invoices` code in `bot.py:init_db()`.

---

### Task 0: Capture baseline and lock the manual-only boundary

**Files:**
- Read: `bot.py:18141-19030`, `bot.py:212804-213112`, `bot.py:43318-43680`, `bot.py:226412-227620`, `bot.py:231864-232070`.
- Read: `tests/test_core.py:9761-10180` and `tests/test_p0_17c3_payos_admin_risk_lock_review.py`.
- Modify: none.

- [x] **Step 1: Run the current manual-topup baseline**

Run from the worktree:

```powershell
$py = 'C:\Users\toann\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $py -m pytest -q --noconftest -p no:cacheprovider --basetemp 'C:\Users\toann\AppData\Local\Temp\payos-manual-baseline' tests/test_core.py -k 'manual or topup or pending or duyet or tuchoi' tests/test_p0_17c3_payos_admin_risk_lock_review.py
```

Measured baseline on `origin/main=095b6c88aa98a42ebbb3fc6535d44d7222e29779`:
`32 passed, 6 failed, 290 deselected, 1 warning in 594.97s`. Failures were
`test_create_media_menu_and_quick_pending_guards`, two support-routing tests,
`test_image_ux_v8_manual_and_ai_edit_confirmation_guards`,
`test_manual_menu_bonus_text_no_zalopay_momo`, and
`test_foreign_topup_i18n_hides_bonus_promises_and_vi_has_domestic_notice`.
The four non-manual failures and the two manual-i18n failures are baseline
observations; no production DB or PayOS request was used.

- [x] **Step 2: Record the current route graph**

The route under test is exactly:

```text
/naptien -> manual|start|manual_custom|<uid>
-> manual|currency|VND|<uid>
-> manual|vndamount|50k|<uid>
-> manual|method|bank_acb|<uid>
-> one QR photo + manual|await_bill|<uid>
-> one customer photo bill
-> pending_deposits.status=pending_admin_review
-> admin manual|approve_expected|<deposit_id>
-> admin manual|confirm|<deposit_id>|<expected_xu>
-> pending_deposits.status=approved and one positive manual_deposit credit event
```

Measured: callback handler `CallbackQueryHandler(handle_manual_package_choice,
pattern=r"^manual\\|")` exists once; customer photo intake is owned by
`handle_photo`; admin buttons are deposit-scoped `approve_expected`,
`approve_custom`, `confirm`, and `reject`. The route graph above is present.

- [x] **Step 3: Commit no code**

Do not create a commit in this task. Task 0 is a read-only baseline.

---

### Task 1: Keep manual amount selection out of PayOS orders

**Files:**
- Modify: `bot.py:43318-43680`, only the `action == "start"` branch of `handle_manual_package_choice`.
- Test: `tests/test_core.py`, add one focused test beside the existing manual tests.

**Required behavior:** Selecting a manual package from either
`manual|start|<pkg>|<uid>` or `/thucong <pkg>` stores the selected
package/amount in `USER_BILL_STATE` and opens the manual currency/method path.
Neither entry point may call `create_order()` or insert a row into
`payos_orders`; manual deposit creation happens only after the customer submits
a bill/TXID.

- [x] **Step 1: Write the failing test**

```python
def test_manual_package_choice_does_not_create_payos_order(monkeypatch, tmp_path):
    db_path = tmp_path / "manual-entry.db"
    monkeypatch.setattr(bot, "DB_FILE", str(db_path))
    monkeypatch.setattr(bot, "USER_BILL_STATE", {})
    bot.init_db()

    class FakeQuery:
        data = "manual|start|50k|123"
        from_user = SimpleNamespace(id=123, first_name="Customer")
        message = SimpleNamespace(chat_id=123)
        async def answer(self, *args, **kwargs): pass
        async def edit_message_text(self, *args, **kwargs): pass

    asyncio.run(bot.handle_manual_package_choice(
        SimpleNamespace(callback_query=FakeQuery()),
        SimpleNamespace(args=[], bot=SimpleNamespace()),
    ))

    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM payos_orders").fetchone()[0] == 0
    finally:
        conn.close()
    assert bot.get_active_manual_bill_state(123)["pkg_key"] == "50k"
```

Also add this direct-command assertion to the same test file:

```python
def test_manual_command_does_not_create_payos_order(monkeypatch, tmp_path):
    db_path = tmp_path / "manual-command-entry.db"
    monkeypatch.setattr(bot, "DB_FILE", str(db_path))
    monkeypatch.setattr(bot, "USER_BILL_STATE", {})
    bot.init_db()
    replies = []

    async def reply_text(text, **_kwargs):
        replies.append(text)

    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=123, first_name="Customer"),
        message=SimpleNamespace(reply_text=reply_text),
    )
    asyncio.run(bot.cmd_thanhtoan_thucong(update, SimpleNamespace(args=["50k"])))
    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM payos_orders").fetchone()[0] == 0
    finally:
        conn.close()
    assert bot.get_active_manual_bill_state(123)["pkg_key"] == "50k"
    assert replies
```

- [x] **Step 2: Run the test to verify RED**

Run:

```powershell
$py = 'C:\Users\toann\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $py -m pytest -q --noconftest -p no:cacheprovider --basetemp 'C:\Users\toann\AppData\Local\Temp\payos-manual-entry-red' tests/test_core.py::test_manual_package_choice_does_not_create_payos_order tests/test_core.py::test_manual_command_does_not_create_payos_order
```

Expected: both tests fail because the current manual callback and `/thucong`
branches call `create_order()` for a manual package.

Measured RED: callback-only test `1 failed, 1 warning in 9.92s`; the temporary
database contained `1` `payos_orders` row. The direct `/thucong` test also
failed with `payos_orders=1` in the combined entry run.

- [x] **Step 3: Implement the smallest fix**

Remove only the manual-branch `create_order(...)` call and
`generate_order_code()` use in both `handle_manual_package_choice` and
`cmd_thanhtoan_thucong`. Preserve the selected package in
`set_manual_bill_state(...)`, set `currency="VND"`, `foreign_manual=False`, and
`step="select_method"`. Do not alter `handle_payos_package_callback` or any
PayOS webhook code.

- [x] **Step 4: Run the test to verify GREEN**

Expected: `2 passed`; both temporary `payos_orders` counts remain `0` and both
manual drafts contain `pkg_key="50k"`.

Measured GREEN: callback-only test `1 passed, 1 warning in 589.75s`. After the
direct-command regression, combined entry gate is `2 passed, 1 warning in
523.59s`; both temporary `payos_orders` counts are `0` and both drafts contain
`pkg_key=50k`.

- [x] **Step 5: Commit this bounded spec**

The code remains uncommitted until Tasks 2-5 are verified and the manual-only
change can be reviewed as one bounded correction.

```powershell
git add bot.py tests/test_core.py
git commit -m "fix(topup): keep manual package selection out of PayOS orders"
```

---

### Task 2: Make QR delivery carry the selected manual payment context

**Files:**
- Modify only if the RED identifies a defect: `bot.py:18460-18620` and `bot.py:18904-19025`.
- Test: `tests/test_core.py`, add or tighten the manual QR test.

**Required behavior:** After `manual|method|bank_acb|<uid>` the bot sends one QR photo/caption containing the selected VND amount, expected Xu, account, and transfer content. QR delivery is an asset/URL display operation; it must not call PayOS checkout and must not create a deposit row. If the QR asset is unavailable, show a no-charge error and leave the draft at `select_method`.

- [x] **Step 1: Write the failing test**

```python
def test_manual_method_qr_preserves_amount_and_does_not_create_deposit(monkeypatch, tmp_path):
    qr_path = tmp_path / "bank.jpg"
    qr_path.write_bytes(b"qr")
    monkeypatch.setattr(bot, "MANUAL_BANK_QR_PATH", str(qr_path))
    monkeypatch.setattr(bot, "USER_BILL_STATE", {})
    bot.set_manual_bill_state(123, order_code="MANUAL", pkg_key="50k", amount=50000,
                              amount_vnd=50000, base_xu=500, expected_xu=500,
                              xu=500, method="bank_acb", currency="VND")

    class FakeBot:
        photos = []
        async def send_photo(self, **kwargs): self.photos.append(kwargs)
    context = SimpleNamespace(bot=FakeBot())
    assert asyncio.run(bot.send_manual_method_qr(context, 123, 123, "bank_acb")) is True
    assert len(context.bot.photos) == 1
    assert "50.000" in context.bot.photos[0]["caption"]
    assert "500" in context.bot.photos[0]["caption"]
```

- [x] **Step 2: Run RED**

Run:

```powershell
$py = 'C:\Users\toann\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $py -m pytest -q --noconftest -p no:cacheprovider --basetemp 'C:\Users\toann\AppData\Local\Temp\payos-manual-qr-red' tests/test_core.py::test_manual_method_qr_preserves_amount_and_does_not_create_deposit
```

Expected: a terminal result. A failure must identify the exact caption/QR boundary that loses amount or Xu; a pass is recorded as characterization and requires no production edit.

- [x] **Step 3: Implement only the failing boundary**

Keep `_send_manual_payment_qr_to_chat()` as the single QR sender. Do not add a second sender, PayOS call, or automatic bill creation. The caption must be generated from `get_active_manual_bill_state(uid)` and the existing `manual_payment_method_text(...)`.

- [x] **Step 4: Run GREEN**

Expected: `1 passed`, exactly one `send_photo` call, zero `pending_deposits` rows.

Measured GREEN/characterization: `2 passed, 1 warning in 8.11s` including the
missing-asset guard; one QR photo contained `50.000` and `500 Xu`, and no
deposit row was created.

- [x] **Step 5: Commit if code changed**

```powershell
git add bot.py tests/test_core.py
git commit -m "test(topup): lock manual QR amount and payment context"
```

---

### Task 3: Persist one bill submission without credit and deduplicate the same file

**Files:**
- Modify: `bot.py:18700-18800` (`create_manual_pending_deposit`) and, only if required, `bot.py:231864-231930` (`handle_photo`).
- Test: `tests/test_core.py:9998-10035` area.

**Required behavior:** A customer photo with an active manual draft creates exactly one `pending_deposits` row with `status="pending_admin_review"`, `method`, amount, expected Xu, `file_id`, and `file_unique_id`. It must not call `add_credit`, update `users.credits`, or add a positive `credit_events` row. Re-delivery of the same `file_unique_id` must return the first deposit and create no second active row. Existing TXID dedupe remains intact.

- [x] **Step 1: Write the failing duplicate-photo test**

```python
def test_duplicate_manual_bill_file_is_idempotent_without_credit(monkeypatch, tmp_path):
    db_path = tmp_path / "manual-duplicate-photo.db"
    _create_manual_deposit_test_db(db_path)
    monkeypatch.setattr(bot, "DB_FILE", str(db_path))
    state = {"currency": "VND", "method": "bank_acb", "amount": 50000,
             "amount_vnd": 50000, "base_xu": 500, "bonus_xu": 0,
             "expected_xu": 500, "xu": 500, "foreign_manual": False}
    user = SimpleNamespace(id=123, first_name="Customer")
    first = bot.create_manual_pending_deposit(user, state, file_id="bill-1", file_unique_id="same-photo")
    second = bot.create_manual_pending_deposit(user, state, file_id="bill-1", file_unique_id="same-photo")
    assert first["ok"] is True
    assert second["ok"] is False
    assert second["reason"] == "duplicate_file_unique_id"
    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM pending_deposits").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM credit_events WHERE delta>0").fetchone()[0] == 0
    finally:
        conn.close()
```

- [x] **Step 2: Run RED**

Expected: FAIL because the current duplicate guard checks `tx_hash` but not `file_unique_id`.

Measured RED: `1 failed in 8.06s`; the second submission returned `ok=true`.

- [x] **Step 3: Implement the smallest database guard**

Before the `INSERT INTO pending_deposits`, query `file_unique_id` only when it is non-empty and match rows whose status is not `rejected`. Return the existing deposit id with reason `duplicate_file_unique_id`; do not call `add_credit`. Do not change the schema or add a destructive migration.

- [x] **Step 4: Run GREEN and existing bill test**

Run:

```powershell
$py = 'C:\Users\toann\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $py -m pytest -q --noconftest -p no:cacheprovider --basetemp 'C:\Users\toann\AppData\Local\Temp\payos-manual-bill-green' tests/test_core.py::test_duplicate_manual_bill_file_is_idempotent_without_credit tests/test_core.py::test_manual_bill_upload_creates_pending_review_without_credit
```

Expected: `2 passed`; row status is `pending_admin_review`, positive credit events are `0`.

Measured GREEN: `2 passed, 1 warning in 7.21s`; one row remained
`pending_admin_review`, positive credit events were `0`, and duplicate reason was
`duplicate_file_unique_id`.

- [x] **Step 5: Commit**

```powershell
git add bot.py tests/test_core.py
git commit -m "fix(topup): deduplicate repeated manual bill files"
```

---

### Task 4: Make admin approval atomic, deposit-scoped, and one-time

**Files:**
- Modify: `bot.py:226412-227388` (`cmd_duyet`) and `bot.py:43318-43415` (approval callback) only if a RED exposes a race or amount mismatch.
- Test: `tests/test_core.py:10036-10180` and `tests/test_p0_17c3_payos_admin_risk_lock_review.py` comparator.

**Required behavior:** The first admin button only displays a confirmation and leaves the pending row, user credits, and positive `credit_events` unchanged. The second confirmation re-reads the same `deposit_id`, verifies the row is still `pending`/`pending_admin_review`, and in one `BEGIN IMMEDIATE` transaction updates that row to `approved`, stores `approved_xu`, `approved_by`, `approved_at`, and adds exactly one `manual_deposit` credit event. A second click, a concurrent admin, or a forged amount must not add credit.

- [x] **Step 1: Write the failing concurrent/idempotency test**

```python
def test_manual_approval_is_one_time_and_deposit_scoped(monkeypatch, tmp_path):
    db_path = tmp_path / "manual-approval-once.db"
    monkeypatch.setattr(bot, "DB_FILE", str(db_path))
    bot.init_db()
    bot.get_user(123)
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO pending_deposits(user_id,status,xu,expected_xu,amount_vnd,method,submitted_at) VALUES('123','pending_admin_review',500,500,50000,'bank_acb','2026-09-03 10:00:00')")
    conn.commit(); conn.close()
    monkeypatch.setattr(bot, "is_admin_user", lambda uid: uid == 999)
    replies = []
    sent = []

    async def reply_text(text, **_kwargs):
        replies.append(text)

    class FakeBot:
        async def send_message(self, **kwargs):
            sent.append(kwargs)

    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=999),
        message=SimpleNamespace(reply_text=reply_text),
    )
    context = SimpleNamespace(args=["1", "500"], bot=FakeBot())
    asyncio.run(bot.cmd_duyet(update, context))
    asyncio.run(bot.cmd_duyet(update, context))
    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute("SELECT credits FROM users WHERE user_id='123'").fetchone()[0] == 500
        assert conn.execute("SELECT COUNT(*) FROM credit_events WHERE event_type='manual_deposit' AND ref_id='1'").fetchone()[0] == 1
        assert conn.execute("SELECT status,approved_xu FROM pending_deposits WHERE id=1").fetchone() == ('approved', 500)
    finally:
        conn.close()
    assert len(sent) >= 1
    assert replies
```

- [x] **Step 2: Run RED**

Expected: FAIL if the current implementation can approve using a stale user-level lookup, credit twice, or ignore the deposit id.

Measured RED: fixture initially retained the automatic trial credit and produced
`700` instead of the intended `500`; the fixture was corrected to reset the user
credit baseline to `0`. This was a test-fixture failure, not a production
approval failure.

- [x] **Step 3: Implement the smallest atomic correction**

Keep the existing deposit-id lookup and `BEGIN IMMEDIATE`. Ensure the positive credit event uses `ref_id=str(pending_deposit_id)`, the `UPDATE pending_deposits` includes `WHERE id=? AND status IN ('pending','pending_admin_review')`, and a zero-row update rolls back without credit. Preserve the existing promotion/tier bookkeeping only after the base credit and row-status guard are valid.

- [x] **Step 4: Run GREEN and protected comparator**

```powershell
$py = 'C:\Users\toann\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $py -m pytest -q --noconftest -p no:cacheprovider --basetemp 'C:\Users\toann\AppData\Local\Temp\payos-manual-approval-green' tests/test_core.py::test_manual_approve_requires_second_confirmation tests/test_core.py::test_manual_approval_is_one_time_and_deposit_scoped tests/test_p0_17c3_payos_admin_risk_lock_review.py
```

Expected: all selected tests pass; first approval snapshot has no credit, final database has one credit event for the exact deposit id.

Measured GREEN: `47 passed, 1 warning in 29.34s`; approval remained deposit-
scoped, final credit was `500`, exactly one `manual_deposit` event referenced
deposit `1`, and the protected admin-risk comparator passed.

- [x] **Step 5: Preserve approval metadata after the atomic status CAS**

The status/approved fields are claimed once at the start of the same
`BEGIN IMMEDIATE` transaction so a zero-row CAS cannot credit Xu. The later
metadata write therefore targets only `WHERE id=? AND status='approved'` and
does not silently re-run the status transition. Regression
`test_manual_approval_keeps_post_approval_metadata` verifies the exact row
retains `payment_market='VN'`, `domestic_eligibility=1`, and
`successful_topup_ordinal=7` after approval.

Measured focused rerun after this correction: `48 passed, 2 warnings in
33.00s` including the four approval/reject/metadata tests and the protected
admin-risk comparator.

- [x] **Step 5: Commit**

```powershell
git add bot.py tests/test_core.py
git commit -m "fix(topup): make manual bill approval atomic and idempotent"
```

---

### Task 5: Verify rejection, queue visibility, and callback registration

**Files:**
- Modify only if a RED identifies a missing route: `bot.py:227389-227479`, `bot.py:43318-43680`, or Telegram handler registration near `bot.py:269730-269790`.
- Test: `tests/test_core.py` and `tests/test_p0_17c3_payos_admin_risk_lock_review.py`.

**Required behavior:** `/pending` and the admin photo notification identify the deposit id, expected Xu, method and user. `manual|reject|<deposit_id>` marks only that row rejected and sends a rejection notice; it never adds Xu. Customer history shows `pending_admin_review`, `approved`, or `rejected` from the same row. `CallbackQueryHandler(handle_manual_package_choice, pattern=r"^manual\|")` remains registered exactly once.

- [x] **Step 1: Write the failing rejection/route test**

```python
def test_manual_reject_is_deposit_scoped_and_no_charge(monkeypatch, tmp_path):
    db_path = tmp_path / "manual-reject.db"
    monkeypatch.setattr(bot, "DB_FILE", str(db_path))
    bot.init_db()
    bot.get_user(123)
    conn = sqlite3.connect(db_path)
    conn.executemany(
        "INSERT INTO pending_deposits(user_id,status,xu,expected_xu,amount_vnd,method,submitted_at) VALUES(?,?,?,?,?,?,?)",
        [("123", "pending_admin_review", 500, 500, 50000, "bank_acb", "2026-09-03 10:00:00"),
         ("123", "pending_admin_review", 1000, 1000, 100000, "bank_acb", "2026-09-03 10:01:00")],
    )
    conn.commit(); conn.close()
    monkeypatch.setattr(bot, "is_admin_user", lambda uid: uid == 999)
    replies = []
    sent = []

    async def reply_text(text, **_kwargs):
        replies.append(text)

    class FakeBot:
        async def send_message(self, **kwargs):
            sent.append(kwargs)

    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=999),
        message=SimpleNamespace(reply_text=reply_text),
    )
    context = SimpleNamespace(args=["1"], bot=FakeBot())
    asyncio.run(bot.cmd_tuchoi(update, context))

    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute("SELECT status FROM pending_deposits WHERE id=1").fetchone()[0] == "rejected"
        assert conn.execute("SELECT status FROM pending_deposits WHERE id=2").fetchone()[0] == "pending_admin_review"
        assert conn.execute("SELECT credits FROM users WHERE user_id='123'").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM credit_events WHERE delta>0").fetchone()[0] == 0
    finally:
        conn.close()
    assert sent and replies
```

Use literal database assertions for `status`, `credits`, and `credit_events`; do not assert only on mock calls.

- [x] **Step 2: Run RED, then fix only the failing route**

Run:

```powershell
$py = 'C:\Users\toann\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $py -m pytest -q --noconftest -p no:cacheprovider --basetemp 'C:\Users\toann\AppData\Local\Temp\payos-manual-reject-red' tests/test_core.py::test_manual_reject_is_deposit_scoped_and_no_charge
```

Expected before the fix: FAIL only when the exact deposit-scoped status or zero-credit invariant is broken. After the minimal route fix: one rejected row, one still-pending row, zero credit delta. Do not add a new admin command because the existing callback route already covers rejection.

Measured: the route test is green on current code; the earlier failure was only
the automatic trial event in the test fixture, corrected by narrowing the
assertion to `manual_deposit`.

- [x] **Step 3: Run the focused route matrix**

```powershell
$py = 'C:\Users\toann\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $py -m pytest -q --noconftest -p no:cacheprovider --basetemp 'C:\Users\toann\AppData\Local\Temp\payos-manual-routes' tests/test_core.py -k 'manual or topup or pending or duyet or tuchoi'
```

Expected: zero new failures; any pre-existing failure must be named and compared against the baseline from Task 0.

Measured route matrix before the metadata correction: `25 passed, 6 failed, 253
deselected, 1 warning in 21.10s`. The six failures are exactly the Task 0
baseline failures (`test_create_media_menu_and_quick_pending_guards`, the two
support-routing assertions, `test_image_ux_v8_manual_and_ai_edit_confirmation_guards`,
and two existing manual/international copy assertions); `NEW_FAILURES=0`.

Final manual-only rerun after the metadata correction: `18 passed, 268
deselected, 2 warnings in 13.07s`. The selected cases cover manual package
entry, QR delivery, bill persistence, duplicate file/TXID, approval,
metadata, rejection, and foreign-manual guards. The protected PayOS auto-topup
comparator (excluding its unrelated static scope/copy check) measured
`18 passed, 1 failed, 1 deselected in 45.80s`; the sole failure is the
pre-existing English/manual menu copy assertion, not a manual payment logic
regression.

- [x] **Step 4: Commit only if route code changed**

```powershell
git add bot.py tests/test_core.py
git commit -m "test(topup): lock manual queue approval and rejection routes"
```

---

### Task 6: Documentation, full verification, and handoff for deployment approval

**Files:**
- Modify: `TAI-LIEU/01-NGHIEP-VU-VAN-HANH.md`, `TAI-LIEU/02-CHUC-NANG-GOC-VA-HIEN-TAI.md`, and `KIEM-THU/DANH-SACH-CASE.md` only with measured evidence from Tasks 0-5.
- Read: `.github/workflows/deploy-vps.yml` to report the actual deploy path; do not run it in this task without explicit deployment approval.

- [x] **Step 1: Run complete local verification**

```powershell
$py = 'C:\Users\toann\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $py -m py_compile bot.py local_worker.py
& $py -m pytest -q --noconftest -p no:cacheprovider --basetemp 'C:\Users\toann\AppData\Local\Temp\payos-manual-final' tests/test_core.py -k 'manual or topup or pending or duyet or tuchoi' tests/test_p0_17c3_payos_admin_risk_lock_review.py tests/test_p0_17c2_payos_auto_topup_limits.py
git diff --check
git status --short
```

Expected: compile exit `0`; pytest output with exact counts and no new failures versus Task 0; diff-check exit `0`; only the declared manual-topup files changed.

Measured compile: `py_compile bot.py local_worker.py` exited `0`.
Measured `git diff --check`: exit `0`.

- [x] **Step 2: Update measured documentation**

Document this exact customer/admin contract:

```text
Customer: select VND amount -> select bank QR -> receive one QR/instruction -> submit one bill.
Database before approval: one pending_deposits row with pending_admin_review; no positive credit event.
Admin: inspect bank statement -> press approve_expected or approve_custom -> press confirm once.
Database after approval: same deposit id approved, approved_xu recorded, one manual_deposit credit event.
Reject: same deposit id rejected, zero Xu delta.
```

Every numeric test result must be copied from terminal output; do not write estimates.

- [x] **Step 3: Review scope and secrets**

Run:

```powershell
git diff --name-only origin/main...HEAD
git diff --check origin/main...HEAD
rg -n -i 'PAYOS_API_KEY|PAYOS_CHECKSUM_KEY|TELEGRAM_TOKEN|BEGIN .*PRIVATE KEY|ghp_|github_pat_' bot.py tests TAI-LIEU KIEM-THU
```

Expected: no secret values; no SubDub/Product Video/WebApp files; no destructive SQL.

- [x] **Step 4: Stop before push/deploy and request Owner approval**

Report the exact local HEAD, test counts, baseline/new failures, changed files, and the fact that no PayOS gateway call or production wallet mutation was executed. Push/PR/merge/deploy is a separate Owner-approved step.

---

## Acceptance checklist

- [x] Manual package selection creates no `payos_orders` row.
- [x] Selected amount/method appears in one QR message and the draft remains no-charge.
- [x] One bill submission creates one `pending_admin_review` deposit and zero positive credit events.
- [x] Duplicate bill photo/TXID is rejected without a second active deposit.
- [x] First admin approval click performs no credit.
- [x] Second admin confirmation credits exactly once and marks the exact deposit approved.
- [x] Rejection is deposit-scoped and adds zero Xu.
- [x] Existing PayOS dynamic checkout/webhook tests remain unchanged; protected comparator has no new logic failure.
- [x] Compile, focused pytest, diff-check, scope and secret scans have terminal evidence.
- [x] No LIVE PASS or deployment claim is made before explicit deployment and Telegram/manual verification.
