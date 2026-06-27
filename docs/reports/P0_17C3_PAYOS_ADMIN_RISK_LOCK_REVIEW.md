# P0.17C3 PayOS Admin Risk Lock Review And Order Control

Date: 2026-06-27
Branch: hotfix/p0-17c3-payos-admin-risk-lock-review
Base: origin/main at f123e3a or newer after P0.17C2

## Scope

This branch adds admin-only PayOS/top-up risk review surfaces. It does not change PayOS signature/idempotency gates from C1, auto top-up limit math from C2, PayOS pricing ratio, Xu credit/debit, wallet ledger, `/naptien` public behavior, webhook route behavior, AI tool pricing, video, voice/TTS, subtitle/dubbing, music/Suno, image flows, web/app/standalone code, deployment config, or destructive DB migrations.

User clarification for this branch: C3 only implements admin screen/commands for risk management. Telegram webhook secret validation, DB backup/status commands, global HTML escaping sweeps, and IP/security-event capture are left for later tasks.

## Existing Surfaces Read

- C2 lock state: `bot.py` table `payos_topup_locks`; helpers `create_payos_auto_topup_lock`, `active_payos_auto_topup_lock_conn`, `payos_auto_topup_guard`.
- PayOS paid processing: `bot.py` `process_payos_paid_order`.
- Admin menu: `bot.py` `menu_text_admin`, `menu_nav_keyboard`, `ADMIN_MENU_PAGE_HANDLERS`, `handle_menu_callback`.
- Manual top-up review: `bot.py` `create_manual_pending_deposit`, `manual_pending_admin_text`, `handle_manual_package_choice`.
- Existing audit/security storage: `bot.py` `record_audit`, `record_audit_event`, `record_anomaly`, table `security_events`.

## Status Matrix

### 1. Admin PayOS risk menu

- Status: PATCHED
- Current file/function: `bot.py` `menu_nav_keyboard`; `menu_text_admin`; `ADMIN_MENU_PAGE_HANDLERS`; `payos_risk_menu_text`; `payos_risk_menu_keyboard`; `handle_payos_risk_callback`
- Risk: Before C3, admins had PayOS/top-up commands but no consolidated Vietnamese risk surface for C2 locks and suspicious orders.
- Safe fix recommendation: Keep this surface admin-only and avoid showing raw webhook payload, checksum, signature, or API secrets.
- Suggested next task: C4

### 2. Admin-only authorization

- Status: PATCHED
- Current file/function: `bot.py` `cmd_payos_risk`; `cmd_payos_risk_user`; `cmd_payos_risk_block`; `cmd_payos_risk_unblock`; `cmd_payos_risk_cancel`; `cmd_payos_risk_mark`; `handle_payos_risk_callback`
- Risk: Public users must not see lock metadata, risk reports, manual block controls, or order control actions.
- Safe fix recommendation: Keep every future `payrisk|...` callback behind `is_admin_user` before reading or mutating risk data.
- Suggested next task: C4

### 3. Review lock listing and unlock

- Status: PATCHED
- Current file/function: `bot.py` `payos_risk_active_locks`; `payos_risk_lock_list_text`; `payos_risk_lock_list_keyboard`; `payos_risk_unlock_user`; `payos_risk_resolve_lock`
- Risk: C2 review locks were persistent by design, so without C3 an admin could not inspect or resolve them cleanly from Telegram.
- Safe fix recommendation: Keep lock resolution non-destructive by recording `resolved_at`, `resolved_by`, and `resolved_note` instead of deleting lock rows.
- Suggested next task: C4

### 4. One-hour lock visibility

- Status: PATCHED
- Current file/function: `bot.py` `payos_risk_active_locks`; `payos_risk_lock_list_text`; `payos_risk_lock_list_keyboard`
- Risk: C2 one-hour locks existed but were hard to review; admins could not quickly see temporary lock reason, amount metadata summary, or expiry.
- Safe fix recommendation: Preserve automatic expiry behavior and only show active temporary locks.
- Suggested next task: C4

### 5. Manual admin block and unblock

- Status: PATCHED
- Current file/function: `bot.py` `payos_risk_manual_block_user`; `payos_risk_unlock_user`; `payos_auto_topup_lock_message`
- Risk: Admins needed a way to pause a user's auto top-up order creation during review without changing manual top-up review behavior or Xu ledger logic.
- Safe fix recommendation: Keep manual block scoped to auto top-up order creation. Do not attach it to service-wide access unless a separate account blocking model is approved.
- Suggested next task: C4

### 6. User risk detail and rolling sums

- Status: PATCHED
- Current file/function: `bot.py` `payos_risk_user_detail_text`; `payos_risk_user_detail_keyboard`; `payos_auto_topup_rolling_amounts_conn`; `payos_risk_recent_orders`; `payos_risk_manual_deposits`
- Risk: Admins needed a compact view of active locks, 60m/12h/24h exposure, recent PayOS orders, and manual pending deposits before deciding whether to unblock or cancel an order.
- Safe fix recommendation: Continue to summarize risk fields only. Do not expose raw webhook body, checksum, or API secret values in Telegram messages.
- Suggested next task: C4

### 7. Pending order cancel

- Status: PATCHED
- Current file/function: `bot.py` `payos_risk_cancel_order`; `payos_risk_order_row_conn`; `payos_risk_order_processed_conn`
- Risk: Admins needed to cancel an uncredited suspicious auto top-up order. C3 marks eligible pending/created/unpaid orders as `CANCELLED` and records audit metadata. Paid or already credited orders are rejected.
- Safe fix recommendation: Keep cancellation limited to uncredited PayOS auto top-up orders. Do not cancel wallet ledger entries from this surface.
- Suggested next task: C4

### 8. Cancelled order later webhook no-credit

- Status: PATCHED
- Current file/function: `bot.py` `payos_risk_cancel_order`; existing `process_payos_paid_order`
- Risk: A later PayOS paid webhook for an admin-cancelled order must not credit Xu. C3 uses the existing `PAYOS_STATUS_CANCELLED` state so the existing C1/C2 status gate rejects later credit.
- Safe fix recommendation: Keep the `process_payos_paid_order` cancelled/expired rejection intact.
- Suggested next task: C4

### 9. Suspicious mark

- Status: PATCHED
- Current file/function: `bot.py` `payos_risk_mark_order_suspicious`
- Risk: Admins needed a non-money annotation for orders that should be reviewed. C3 writes metadata only and does not credit, debit, approve, or cancel by itself.
- Safe fix recommendation: Use this as a triage marker only; any future automated actions should be a separate reviewed hotfix.
- Suggested next task: C4

### 10. Risk report

- Status: PATCHED
- Current file/function: `bot.py` `payos_risk_report_payload`; `payos_risk_report_text`; `payos_risk_report_keyboard`
- Risk: Admins needed a read-only view of active review locks, active one-hour locks, suspicious/cancelled-by-admin orders, existing invalid webhook/security event counts, and top users by PayOS auto top-up exposure.
- Safe fix recommendation: If export is needed later, add a separate admin-only export that redacts raw payload/checksum/signature/secrets.
- Suggested next task: C4

### 11. Manual top-up review copy

- Status: PATCHED
- Current file/function: `bot.py` `manual_pending_admin_text`
- Risk: Manual top-up already waited for admin approval; the admin message needed an explicit warning that manual deposits are not auto-credited and should only be approved after money is verified.
- Safe fix recommendation: Keep manual approval as a human action and do not route manual pending deposits through PayOS webhook auto-credit.
- Suggested next task: C4

### 12. Audit logs for admin risk actions

- Status: PATCHED
- Current file/function: `bot.py` `record_audit`; `record_audit_event`; C3 actions `manual_block_auto_topup`, `resolve_auto_topup_lock`, `cancel_payos_order`, `mark_payos_order_suspicious`, `view_risk_report`
- Risk: Admin lock/order actions need traceability without leaking raw payment secrets.
- Safe fix recommendation: Keep audit details concise and avoid logging full webhook payloads or secrets.
- Suggested next task: C4

### 13. Telegram webhook secret

- Status: MISSING
- Current file/function: Not changed in C3
- Risk: This branch intentionally does not implement `secret_token` setup or `X-Telegram-Bot-Api-Secret-Token` validation.
- Safe fix recommendation: Implement in a separate branch dedicated to Telegram webhook security.
- Suggested next task: C4

### 14. DB backup/status

- Status: MISSING
- Current file/function: Not changed in C3
- Risk: This branch intentionally does not add `/db_status`, `/backup_db_now`, backup storage policy, or `.gitignore` updates.
- Safe fix recommendation: Implement admin-only backup/status commands in a separate DB ops branch.
- Suggested next task: C4

### 15. HTML escaping sweep

- Status: PARTIAL
- Current file/function: C3 new PayOS risk messages use `html.escape`; no global sweep was performed.
- Risk: Existing non-C3 PayOS/admin/top-up HTML messages may still need a broader escaping audit.
- Safe fix recommendation: Run a dedicated static audit/fix branch for HTML escaping across PayOS/admin/security/top-up messages.
- Suggested next task: C4

### 16. IP/security event capture

- Status: PARTIAL
- Current file/function: C3 reads existing `security_events` counts and writes admin audit events only; no new request IP/user-agent capture was added.
- Risk: Existing PayOS webhook request IP/user-agent forensic coverage remains outside C3 scope. Telegram messages do not expose user IP.
- Safe fix recommendation: Add request IP/user-agent capture and IP block policy in a separate security-event branch.
- Suggested next task: C4

## Test Coverage

- `tests/test_p0_17c3_payos_admin_risk_lock_review.py`
- Covered: admin menu visibility, public hidden checks, lock list, one-hour locks, user risk detail, rolling sums, manual block/unblock, pending order cancel, cancelled later webhook no-credit, suspicious mark, risk report, manual top-up warning, audit logs, no raw secret/payload exposure in C3 messages, command/callback registration, and static file guard.

## Not Touched

- PayOS signature/idempotency logic from C1
- PayOS auto top-up limit thresholds and cooldown from C2
- PayOS pricing ratio and package pricing
- Xu credit/debit logic and wallet ledger
- `/naptien` public behavior
- PayOS webhook route behavior
- Voice/TTS, subtitle/dubbing, video/multiscene, music/Suno, image/image-to-video
- Web/app/standalone
- DB destructive migrations
- Deployment and LIVE PASS
