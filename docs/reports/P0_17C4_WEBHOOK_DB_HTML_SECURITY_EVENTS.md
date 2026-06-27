# P0.17C4 Webhook Secret + DB Backup Status + HTML Escape + Security Events

Date: 2026-06-27

Scope: security hardening around Telegram webhook ingress, admin DB backup/status, admin HTML escaping, and security-event visibility.

Non-goals: no PayOS C1 signature/idempotency rewrite, no C2 auto top-up limit rewrite, no C3 admin risk logic rewrite, no Xu credit/debit change, no wallet ledger change, no `/naptien` behavior change, no video/voice/music/image/web/app change, no DB destructive migration, no deploy, no LIVE PASS.

## Summary

Status: PATCHED

Current files/functions:
- `bot.py`: `telegram_webhook`, `set_telegram_webhook_takeover`, `runtime_health`
- `bot.py`: `safe_html`, `record_security_event`, `request_security_context`, `recent_security_events`
- `bot.py`: `create_db_backup_now`, `db_status_admin_text`, `backup_db_result_text`, `security_log_text`
- `bot.py`: `cmd_db_status`, `cmd_backup_db`, `cmd_security_log`, admin menu callbacks/buttons
- `tests/test_p0_17c4_webhook_db_html_security_events.py`

Risk addressed:
- Public Telegram webhook endpoint could receive unauthenticated update-shaped POSTs if webhook secret was configured at Telegram but not checked server-side.
- Admin DB status/backup needed safer operational controls with masked paths and no DB contents/balances.
- Admin/security/backup surfaces needed consistent HTML escaping for user/admin-controlled values.
- Sensitive webhook/admin actions needed structured IP/user-agent/security event records without logging secrets or raw payloads.

Safe fix recommendation:
- Keep `TELEGRAM_WEBHOOK_SECRET` configured in production and rotate it like other secrets.
- Keep `DB_BACKUP_DIR` outside public/static paths and on persistent storage.
- Review `/security_log` and `/db_status` after deploy before declaring production readiness.

Suggested next task: C4 deploy/QA only after owner approval. No further C1/C2/C3 core change is required by this task.

## Telegram Webhook Secret

Status: PATCHED

Current file/function:
- `bot.py`: `TELEGRAM_WEBHOOK_SECRET`
- `bot.py`: `set_telegram_webhook_takeover`
- `bot.py`: `telegram_webhook`
- `bot.py`: `runtime_health`

Behavior:
- If `TELEGRAM_WEBHOOK_SECRET` is configured, `setWebhook` sends `secret_token`.
- If `TELEGRAM_WEBHOOK_SECRET` is configured, FastAPI checks `X-Telegram-Bot-Api-Secret-Token` before processing the update.
- Missing or bad token returns `401` and records a security event.
- The token value is never logged.
- If `TELEGRAM_WEBHOOK_SECRET` is not configured, previous local/dev behavior is preserved.
- `/runtime` now exposes `telegram_webhook_secret_configured` and `telegram_webhook_secret_enforced`.

Risk:
- Before this hardening, a server-side check could be absent even if Telegram supported `secret_token`.

Safe fix recommendation:
- Production should set a strong random `TELEGRAM_WEBHOOK_SECRET`.
- Rotate if exposed.

Suggested next task: deployment QA, not a code hotfix.

## DB Status And Backup

Status: PATCHED

Current file/function:
- `bot.py`: `create_db_backup_now`
- `bot.py`: `db_status_admin_payload`
- `bot.py`: `db_status_admin_text`
- `bot.py`: `cmd_db_status`
- `bot.py`: `cmd_backup_db`
- `bot.py`: `secret_file_risk_check`

Behavior:
- Admin command/button added: `/db_status`, `🗄 DB trạng thái`.
- Admin command/button added: `/backup_db_now`, `💾 Sao lưu DB`.
- `/backup_db` remains available and now uses the same safer backup helper.
- Backup filename format: `toanaas_system_YYYYMMDD_HHMMSS.sqlite3`.
- Backup directory uses `DB_BACKUP_DIR`.
- Retention uses `DB_BACKUP_KEEP_LAST`, default `10`.
- Backup helper rejects public/static backup directories.
- DB status masks paths and does not show DB contents, balances, raw secrets, or full private paths.
- Secret-like file risk check reports masked filenames for `.env`, token/key/secret-like files, public DB backups, and backup-like DB files in repo root.

Risk:
- Backups must stay out of public/static paths and must not be committed.

Safe fix recommendation:
- Set `DB_BACKUP_DIR=/data/backups` or another private persistent path in production.
- Keep backup files excluded from git.

Suggested next task: deployment QA and a manual backup restore drill in a separate ops branch if needed.

## HTML Safety

Status: PATCHED

Current file/function:
- `bot.py`: `safe_html`
- `bot.py`: `db_status_admin_text`
- `bot.py`: `backup_db_result_text`
- `bot.py`: `security_log_text`
- `bot.py`: `cmd_security_status`

Behavior:
- Added centralized `safe_html(text)`.
- New C4 admin DB/security/backup surfaces use `safe_html` for dynamic text.
- Existing high-risk PayOS/admin risk surfaces already used `html.escape` in most places; C4 avoids introducing unsafe HTML on new surfaces.

Risk:
- Telegram `parse_mode="HTML"` can render malformed or injected content if user-controlled strings are not escaped.

Safe fix recommendation:
- Prefer `safe_html` for new admin/security/payment strings.
- Continue replacing raw `html.escape(str(...))` gradually only when touching nearby code.

Suggested next task: optional C5 static lint for all `parse_mode="HTML"` surfaces.

## Security Events And IP/User-Agent

Status: PATCHED

Current file/function:
- `bot.py`: `request_security_context`
- `bot.py`: `record_security_event`
- `bot.py`: `recent_security_events`
- `bot.py`: `record_payos_webhook_security_event`
- `bot.py`: `cmd_security_log`
- `bot.py`: `payos_risk_manual_block_user`
- `bot.py`: `payos_risk_unlock_user`
- `bot.py`: `payos_risk_cancel_order`
- `bot.py`: `payos_risk_mark_order_suspicious`

Behavior:
- Security events include endpoint, request client IP, user-agent, action, user id, order code, and payment id where available.
- PayOS webhook rejection/security events now include request IP/user-agent metadata.
- Telegram webhook secret failures record request IP/user-agent metadata.
- Admin risk actions now record security events after successful actions.
- Admin command/button added: `/security_log`, `🛡 Nhật ký bảo mật`.
- Telegram messages do not expose user IP. IP/user-agent is only available for HTTP webhook/API requests and is shown only as admin security-event metadata.

Risk:
- Client IP is taken from the ASGI request client and not trusted forwarding headers.
- No raw payload, checksum, token, or secret is stored in these event details.

Safe fix recommendation:
- If running behind a trusted proxy and true client IP is required later, add an explicit trusted-proxy parser in a separate hotfix.

Suggested next task: optional C5 trusted-proxy IP normalization, if production ingress requires it.

## Admin Menu

Status: PATCHED

Current file/function:
- `bot.py`: `menu_nav_keyboard`
- `bot.py`: `menu_text_admin`
- `bot.py`: `menu_text_system`
- `bot.py`: `handle_menu_callback`
- `bot.py`: `ADMIN_MENU_PAGE_HANDLERS`

Behavior:
- Added admin menu buttons:
  - `🗄 DB trạng thái`
  - `💾 Sao lưu DB`
  - `🛡 Nhật ký bảo mật`
- Kept Finance + Freeze/Queue row.
- Kept C3 PayOS risk admin tools.

Risk:
- Admin-only controls must remain behind `is_admin_user`.

Safe fix recommendation:
- Verify buttons from a non-admin Telegram account after deployment.

Suggested next task: deployment QA only.

## Runtime

Status: PATCHED

Current file/function:
- `bot.py`: `runtime_health`

Runtime flags added:
- `telegram_webhook_secret_configured`
- `telegram_webhook_secret_enforced`
- `db_backup_enabled`
- `last_db_backup_at`
- `security_event_logging_enabled`

Public version:
- Preserved `PUBLIC_VERSION = "v1.0 Beta"`.

## Tests

Status: PATCHED

Current file/function:
- `tests/test_p0_17c4_webhook_db_html_security_events.py`
- Updated static guard allowlists in C1/C2/C3 and audio/video guard tests.

Covered:
- Telegram webhook secret missing/bad token rejection.
- Valid Telegram webhook secret acceptance.
- Local/dev no-secret behavior preserved.
- `setWebhook` includes `secret_token`.
- Runtime flags exposed.
- DB backup filename, retention, status text, masked paths.
- Admin-only DB status/backup commands and security-event logging.
- Secret-like backup risk detection with masked filenames.
- HTML escaping on C4 admin/security surfaces.
- Admin menu buttons and command registrations.

## Not Touched

- PayOS credit/debit: NOT TOUCHED
- Wallet ledger: NOT TOUCHED
- `/naptien`: NOT TOUCHED
- PayOS pricing ratio: NOT TOUCHED
- PayOS C1 signature/idempotency core: NOT TOUCHED
- PayOS C2 auto top-up limit core: NOT TOUCHED
- PayOS C3 admin risk core behavior: NOT TOUCHED, only security-event visibility added after successful actions
- Voice/TTS: NOT TOUCHED
- Subtitle/dubbing: NOT TOUCHED
- Video/multiscene: NOT TOUCHED
- Music/Suno: NOT TOUCHED
- Image/image-to-video: NOT TOUCHED
- DB destructive migration: NOT TOUCHED
- Web/app/standalone: NOT TOUCHED
- Deploy: NOT DONE
- LIVE PASS: NOT CLAIMED
