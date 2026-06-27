# P0.17C2 PayOS Auto Top-up Limits + Lock State

Date: 2026-06-27
Branch: hotfix/p0-17c2-payos-auto-topup-limits
Base: origin/main at 7904c1d or newer after P0.17C1

## Scope

This branch adds guardrails to PayOS auto top-up order creation only. It does not change PayOS webhook crediting, Xu debit/credit ratio, wallet ledger logic, AI tool pricing, video/voice/music/image flows, deployment config, or web/app/standalone code.

## Status Matrix

### 1. Max 500,000 VND per auto PayOS order

- Status: PATCHED
- Current file/function: `bot.py` constants `PAYOS_AUTO_TOPUP_MAX_VND`; `payos_auto_topup_guard`; `handle_package_choice`
- Risk: Auto order creation through the Telegram PayOS package callback is blocked before user creation, order creation, or PayOS API call when amount is above 500,000 VND. Direct web/app billing paths were intentionally not changed in this branch.
- Safe fix recommendation: If another auto top-up entrypoint is added, route it through `payos_auto_topup_guard` before creating PayOS orders.
- Suggested next task: C3/C4

### 2. One auto order per user per 5 minutes

- Status: PATCHED
- Current file/function: `bot.py` `payos_auto_topup_last_created_at_conn`; `payos_auto_topup_guard`
- Risk: Cooldown checks recent auto-looking PayOS orders for the same user and blocks a second creation inside 5 minutes. Manual top-up orders are excluded by `order_type`/metadata.
- Safe fix recommendation: Keep all future auto top-up order creation tagged with `auto_topup=true` metadata.
- Suggested next task: C3

### 3. 3,000,000 VND per 60 minutes triggers 1-hour auto lock

- Status: PATCHED
- Current file/function: `bot.py` `payos_auto_topup_rolling_amounts_conn`; `create_payos_auto_topup_lock`; `active_payos_auto_topup_lock_conn`; table `payos_topup_locks`
- Risk: Rolling exposure includes pending and paid auto PayOS top-up orders. At or above 3,000,000 VND in 60 minutes, the next auto order is blocked and a 1-hour lock is recorded.
- Safe fix recommendation: C3 admin view/unlock should expose this lock state and event metadata.
- Suggested next task: C3

### 4. 9,000,000 VND per 12 hours triggers review lock

- Status: PATCHED
- Current file/function: `bot.py` `payos_auto_topup_guard`; `create_payos_auto_topup_lock`
- Risk: Review lock does not auto-expire and blocks future auto top-up attempts until an admin flow is added. This is intentional for C2.
- Safe fix recommendation: Add admin review/unlock controls in a separate C3 branch.
- Suggested next task: C3

### 5. 15,000,000 VND per 24 hours triggers review lock

- Status: PATCHED
- Current file/function: `bot.py` `payos_auto_topup_guard`; `create_payos_auto_topup_lock`
- Risk: Review lock is persistent. C2 does not implement admin risk dashboard or manual unlock UI.
- Safe fix recommendation: Add admin risk report and unlock action in C3.
- Suggested next task: C3

### 6. USD auto max 100 USD / USD manual-only status

- Status: PARTIAL
- Current file/function: `bot.py` `PAYOS_AUTO_TOPUP_MAX_USD`; `payos_auto_topup_guard`; `manual_topup_rules_text`
- Risk: Current `PAYMENT_PACKAGES` are VND only, so USD remains manual-only. The guard has a USD cap for future auto USD routing, but no USD auto order path exists in this branch.
- Safe fix recommendation: If USD auto PayOS is introduced later, add explicit tests that the USD entrypoint calls `payos_auto_topup_guard(..., currency="USD")` before order/API creation.
- Suggested next task: C4

### 7. Manual top-up large amount can proceed but must not auto-credit

- Status: PATCHED
- Current file/function: `bot.py` `manual_topup_rules_text`; `payos_manual_topup_order_metadata`; manual `create_order` calls in `handle_package_choice`, `handle_manual_package_choice`, and `cmd_thanhtoan_thucong`; existing `create_manual_pending_deposit`
- Risk: Manual pending deposits remain admin-review only and are not auto-credited. Manual PayOS-order placeholders are now tagged as `manual_topup` so they do not pollute PayOS auto rolling limits.
- Safe fix recommendation: Keep manual approval as a second-step admin confirmation and do not attach PayOS webhook auto-credit logic to manual deposits.
- Suggested next task: C3

### 8. Public top-up rules text

- Status: PATCHED
- Current file/function: `bot.py` `payos_auto_topup_rules_text`; `manual_topup_rules_text`; `manual_payment_menu_text`; `cmd_naptien`
- Risk: Users can now see auto PayOS limits and manual review expectations before choosing a top-up path.
- Safe fix recommendation: Add i18n variants only in a separate copy/localization task.
- Suggested next task: C4

### 9. Security event logging for limit blocks

- Status: PATCHED
- Current file/function: `bot.py` `record_payos_auto_topup_limit_event`; `create_payos_auto_topup_lock`; `payos_auto_topup_guard`
- Risk: C2 records limit events through the existing `record_anomaly` helper. It does not add a full admin risk dashboard.
- Safe fix recommendation: C3 should expose PayOS auto top-up lock and event history to admins.
- Suggested next task: C3

### 10. Admin controls for lock/review state

- Status: PARTIAL
- Current file/function: `bot.py` table/helper only: `payos_topup_locks`, `active_payos_auto_topup_lock`
- Risk: Auto/review locks are enforced, but C2 intentionally does not add full admin lock/unlock, cancel/delete, or risk report UI.
- Safe fix recommendation: Implement admin unlock/risk report in a dedicated C3 branch without changing webhook crediting.
- Suggested next task: C3

## Tests Added

- `tests/test_p0_17c2_payos_auto_topup_limits.py`
  - 500,000 VND max accepted and above-cap blocked before PayOS API/order/credit.
  - 5-minute cooldown blocks second auto order.
  - 3,000,000 VND/60m creates 1-hour lock and expires.
  - 9,000,000 VND/12h and 15,000,000 VND/24h create review locks.
  - Review lock does not auto-expire.
  - Manual large VND and USD top-up remain pending admin review and do not auto-credit.
  - Manual orders are excluded from auto rolling limits.
  - Security event is written for PayOS auto limit events.

## No-Touch Confirmation

- PayOS webhook behavior: unchanged
- Xu credit/debit and PayOS pricing ratio: unchanged
- Wallet ledger: unchanged
- `/naptien` behavior: only public rule text added; existing package choices remain
- Voice/TTS, subtitle/dubbing, video/multiscene, music/Suno, image/image-to-video: unchanged
- DB migration: non-destructive `CREATE TABLE IF NOT EXISTS`/indexes only for lock state
- Deployment: not performed
- LIVE PASS: not claimed
