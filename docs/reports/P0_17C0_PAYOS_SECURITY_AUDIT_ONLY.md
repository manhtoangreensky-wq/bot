# P0.17C0 PayOS Security Audit Only

Audit date: 2026-06-26

Repository: `manhtoangreensky-wq/bot`

Branch: `hotfix/p0-17c0-payos-security-audit-only`

Base inspected: `origin/main` at `2d9dcf3` (`Merge pull request #55 from manhtoangreensky-wq/hotfix/p0-17b12-5-live-router-gate`)

Scope: audit only. No production payment behavior, PayOS webhook behavior, Xu credit/debit, wallet ledger, `/naptien`, pricing, DB migration, deploy, or LIVE PASS claim is included in this branch.

Status legend:

- `PATCHED` means the control already exists in the inspected codebase. It does not mean this audit branch patched runtime behavior.
- `PARTIAL` means some control exists but gaps remain.
- `MISSING` means no clear implementation was found.
- `UNKNOWN` means local static inspection could not prove the answer.

Suggested next-task classes:

- `C1`: payment/security hotfix branch before broad public use.
- `C2`: operational hardening/admin control branch.
- `C3`: tests/observability/reporting branch.
- `C4`: housekeeping/docs cleanup branch.

Important C1 finding: do not patch in this branch. The PayOS webhook verifies the signed `data` object before crediting, but it currently accepts the webhook as payable when `body.success` is true even if `data.status` is not explicitly `PAID`. Because `success` is outside the signed `data` object, the next hotfix should require `data.status == PAYOS_STATUS_PAID` before calling `process_payos_paid_order`. Suggested next branch: `hotfix/p0-17c1-payos-signature-idempotency`.

## 1. PayOS Webhook

Status: `PARTIAL`

Current file/function:

- `bot.py:143732` and `bot.py:143733`: FastAPI routes `POST /api/v1/billing/webhook/payos` and `POST /webhook/payos`.
- `bot.py:143734`: handler `webhook_payos`.
- `bot.py:143720`: `verify_payos_signature(data, received_sig)`.
- `bot.py:28334`: `process_payos_paid_order(order_code, amount_vnd)`.
- `bot.py:2556`: `payos_processed` table with `order_code` primary key.

Findings:

- Endpoint path: `POST /api/v1/billing/webhook/payos` and legacy `POST /webhook/payos`.
- Handler function name: `webhook_payos`.
- Signature/checksum before crediting Xu: yes. `webhook_payos` reads `body["data"]` and `body["signature"]`, requires `PAYOS_CHECKSUM_KEY`, calls `verify_payos_signature`, and only then calls `process_payos_paid_order`.
- Env secret used: `PAYOS_CHECKSUM_KEY`.
- Raw webhook data can credit Xu without verification: no, if `PAYOS_CHECKSUM_KEY` is configured. Missing checksum key returns HTTP 500 and invalid signature returns HTTP 400.
- Paid/pending/cancelled statuses: partial. `webhook_payos` ignores requests when neither `body.success` nor `data.status == "PAID"` is true. However, it does not require `data.status == "PAID"` if outer `body.success` is true. Internal order status checks reject already `PAID`, `EXPIRED`, and `CANCELLED` orders.
- Amount mismatch: rejected in `process_payos_paid_order` by comparing stored order amount to webhook amount before crediting.
- Duplicate webhook credit: blocked by both current order status (`already_paid`) and `payos_processed` order-code check inside `BEGIN IMMEDIATE`.
- Idempotency key: current idempotency is by internal `order_code`; `payment_link_id` is stored but not unique or used as the primary idempotency key; no transaction id key was found.
- Fake webhook test exists: partial. Tests cover invalid signature and missing checksum key (`tests/test_billing_bridge_storage_v2.py:10`, `tests/test_core.py:6483`). Tests also cover direct duplicate processing in `process_payos_paid_order` (`tests/test_core.py:5779`). No full valid-signed fake webhook replay/status/amount-mismatch integration test was found.

Risk:

- C1: A captured/replayed valid signed `data` object with non-PAID status could be unsafe if an attacker can influence the unsigned outer `success` field. This is mitigated by needing a valid PayOS HMAC but should still be fixed because money crediting should require signed `data.status == "PAID"`.
- Idempotency by internal `order_code` is strong for internal orders, but `paymentLinkId`/transaction id should also be recorded uniquely for forensics and defense in depth.
- Missing dedicated amount-mismatch and valid-signed fake webhook integration tests leaves regression risk.

Safe fix recommendation:

- In a separate C1 branch, require `data.get("status") == PAYOS_STATUS_PAID` before any call to `process_payos_paid_order`.
- Add unique/idempotent tracking for `paymentLinkId` and PayOS transaction id if PayOS provides it.
- Add read-only tests for invalid signature, missing checksum, non-PAID signed payload, amount mismatch, duplicate replay, and cancelled/expired internal order behavior.

Suggested next task: `C1`

## 2. Top-Up Order Creation

Status: `PARTIAL`

Current file/function:

- `bot.py:1090`: `PAYMENT_PACKAGES`.
- `bot.py:6833`: `create_order`.
- `bot.py:6990`: `generate_order_code`.
- `bot.py:31747`: `handle_package_choice` creates PayOS top-up orders from package callbacks.
- `bot.py:113297`: `cmd_naptien` opens the top-up flow.
- `bot.py:31978`: `handle_manual_package_choice`.
- `bot.py:8321`: `create_manual_pending_deposit`.
- `bot.py:126633`: `cmd_duyet` manual approval.
- `bot.py:127466`: `cmd_tuchoi` manual rejection.

Findings:

- PayOS auto top-up order creation: package callback flow in `handle_package_choice`, after `/naptien`/pricing menu selection.
- Max amount per auto order: partial. Fixed top-up packages are `10k`, `20k`, `50k`, `100k`, `200k`, `500k`, so the top-up menu caps normal package selection at 500,000 VND. This is not implemented as an explicit `MAX_AUTO_TOPUP_AMOUNT_VND` guard.
- Cooldown: missing. No per-user PayOS order creation cooldown was found.
- Rolling limits: missing. No per-user/day/week rolling order-creation or paid top-up limits were found for PayOS auto orders.
- User spam create orders: possible. A user can repeatedly click package callbacks and create many pending orders until TTL expiry; `expire_old_payos_orders` only expires old orders.
- Manual top-up exists: yes. `/thucong` and manual callbacks create pending manual deposit review flows.
- Manual top-up auto-credits: no. User bill/TXID/photo creates `pending_admin_review`; Xu is credited only through admin `/duyet` or admin confirm callback.

Risk:

- Order-spam risk can create noisy pending PayOS rows and PayOS checkout calls.
- Lack of explicit max/cooldown/rolling constants makes future pricing/package changes easier to accidentally expose without guardrails.

Safe fix recommendation:

- Add a separate C2/C3 branch with read-only tests first, then runtime controls: per-user pending-order cap, short cooldown, and rolling daily/monthly auto-order limits.
- Add explicit max auto top-up amount config separate from package display.
- Keep manual approval behavior unchanged unless a dedicated payment task authorizes changes.

Suggested next task: `C2`

## 3. Admin Controls

Status: `PARTIAL`

Current file/function:

- Registered commands in `bot.py:139598` through `bot.py:139950`.
- PayOS alert buttons in `bot.py:7286` and handler `handle_payos_alert_callback` at `bot.py:32252`.
- Global safe mode/payment freeze helpers at `bot.py:32946`, `bot.py:89146`, `bot.py:89183`, `bot.py:89247`, and `bot.py:89250`.
- Manual billing commands `cmd_pending`, `cmd_duyet`, `cmd_tuchoi` at `bot.py:127525`, `bot.py:126633`, and `bot.py:127466`.

Findings:

- Current admin PayOS commands/buttons:
  - `/checkpayos`, `/payos_status`, `/payos_verify`.
  - `/payos_debug_create`, `/payos_env_check`, `/payos_key_fingerprint`, `/payos_signature_debug`, `/payos_official_debug`, `/payos_confirm_webhook`.
  - `/payos_test_plan`, `/mark_payos_test`.
  - `/pending`, `/duyet`, `/tuchoi`, `/add`.
  - `/billing_bridge_status`, `/billing_bridge_test`, `/billing_retry_apply`.
  - `/freeze_payments`, `/unfreeze_payments`, `/emergency_lock`, `/emergency_unlock`, `/security_status`, `/risk_checklist`, `/dashboard`.
  - PayOS alert buttons: open manual top-up, test PayOS, mute alert, renewed/remind-later expiry actions.
- Admin can unlock/lock user: missing for per-user lock/unlock. Global emergency/payment/tool/provider freeze exists.
- Admin can cancel/delete top-up order: partial. Manual pending bills can be rejected with `/tuchoi`; PayOS orders are cancelled internally on create failure/freeze. No dedicated admin command to cancel/delete a PayOS top-up order was found.
- Admin can block user from service: missing. No per-user service block command/table was found in the audited payment/security surface.
- Admin can view risk report: partial. `/security_status`, `/risk_checklist`, `/dashboard`, and billing/dashboard summaries exist, but no dedicated PayOS risk report with webhook/IP/idempotency/top-up-limit signals was found.

Risk:

- Operators can freeze all payments but cannot isolate a single suspicious user without broader service impact.
- Lack of order cancel/delete tooling can force manual DB intervention if a pending/fraudulent order needs operational cleanup.

Safe fix recommendation:

- Add per-user risk controls in a C2 branch: lock/unlock user, service block, PayOS order cancel, and audit log entries.
- Add a PayOS risk report in C3: recent invalid signatures, amount mismatches, duplicate webhooks, pending-order spam, and manual approval anomalies.

Suggested next task: `C2`

## 4. Telegram Webhook Security

Status: `PARTIAL`

Current file/function:

- `bot.py:915`: `TELEGRAM_WEBHOOK_SECRET`.
- `bot.py:917`: `TELEGRAM_WEBHOOK_PATH`.
- `bot.py:1008`: `set_telegram_webhook_takeover`.
- `bot.py:140613`: `telegram_webhook`.
- `bot.py:139067`: `run_polling_guarded`.

Findings:

- Webhook set with `secret_token`: yes, but only if `TELEGRAM_WEBHOOK_SECRET` is configured.
- FastAPI checks `X-Telegram-Bot-Api-Secret-Token`: yes, but only if `TELEGRAM_WEBHOOK_SECRET` is configured. Header name is read as `x-telegram-bot-api-secret-token`.
- Missing/bad token rejected: yes when `TELEGRAM_WEBHOOK_SECRET` exists; missing/bad token is not rejected when the secret is unset.
- Local polling/dev still works: yes. `TELEGRAM_UPDATE_MODE` supports `webhook` or `polling`, and polling path exists.
- Additional obscurity: default Telegram webhook path includes a SHA-256 prefix from `TELEGRAM_TOKEN` when token exists. This is not a replacement for header verification.

Risk:

- If production runs webhook mode without `TELEGRAM_WEBHOOK_SECRET`, anyone who knows the path can post synthetic Telegram updates.

Safe fix recommendation:

- In C1/C2, require `TELEGRAM_WEBHOOK_SECRET` when `TELEGRAM_UPDATE_MODE=webhook` in Railway/production, while preserving explicit local polling/dev mode.
- Add a static test that production webhook mode fails startup or health readiness if webhook secret is missing.

Suggested next task: `C1`

## 5. DB And Backup

Status: `PARTIAL`

Current file/function:

- `bot.py:1228`: `DATA_PERSISTENCE_MODE`.
- `bot.py:1232`: `DB_PATH = _env("DB_PATH", _env("DB_FILE", "toandaas_system.db"))`.
- `bot.py:1238`: `DB_BACKUP_DIR`.
- `bot.py:2198`: `data_persistence_status_payload`.
- `bot.py:59826`: `cmd_data_status`.
- `bot.py:129495`: `cmd_backup_db`.
- Registered `/data_status` and `/backup_db` at `bot.py:139187` and `bot.py:139198`.
- `.gitignore` excludes `.env`, SQLite files, and `backups/`.

Findings:

- Current SQLite DB path: default `toandaas_system.db`, overridable by `DB_PATH` or `DB_FILE`.
- DB path persistent or ephemeral: partial. Default relative `toandaas_system.db` is ephemeral-risky on Railway/container storage. `/data/toandaas_system.db` is treated as persistent candidate when configured.
- `/db_status` exists: missing. `/data_status` exists and covers DB path, volume, backup, counts, migration guard, and data-loss risk.
- `/backup_db_now` exists: missing. `/backup_db` exists.
- Backup admin-only: yes. `/backup_db` requires admin; during emergency lock, only owner can run it.
- Backup files excluded from git: yes. `.gitignore` excludes `backups/`, `*.sqlite`, `*.sqlite3`, and `toandaas_system.db`.

Risk:

- Default DB path is not safe for production persistence if Railway Volume is not configured.
- Operators may expect `/db_status` or `/backup_db_now` from docs/tasks, but actual commands are `/data_status` and `/backup_db`.

Safe fix recommendation:

- In C2, add aliases `/db_status -> /data_status` and `/backup_db_now -> /backup_db` if desired, without changing backup semantics.
- Before any payment-flow changes, verify Railway Volume with `DB_PATH=/data/toandaas_system.db` and `DB_BACKUP_DIR=/data/backups`.

Suggested next task: `C2`

## 6. HTML Escaping

Status: `PARTIAL`

Current file/function:

- PayOS/admin/top-up HTML messages across `bot.py`.
- Manual payment text at `bot.py:7664`, manual pending admin/user text at `bot.py:8391` and `bot.py:8436`.
- Admin pending list at `bot.py:127525`.
- Dashboard at `bot.py:129331`.
- PayOS webhook notifications at `bot.py:143785` through `bot.py:143948`.

Findings:

- Many PayOS/admin/security fields are escaped with `html.escape`, including PayOS webhook target URLs, PayOS key fingerprints, package labels, promo codes, manual deposit `tx_hash`, transfer content, and many admin IDs.
- User-controlled values not consistently wrapped:
  - `bot.py:127542`: `/pending` renders stored `username` (`r[2]`) directly in an HTML message.
  - `bot.py:127542`: `/pending` also renders `order_code` (`r[4]`) in plain text, not escaped. Today this is generated/internal in most flows, but it should still be escaped.
  - `bot.py:129415`: `/dashboard` renders top-user `username` directly in an HTML message.
  - `bot.py:143936` and `bot.py:143940`: PayOS success admin notification renders `target_id` and `order_code` without `html.escape`. These are expected to be numeric/internal, but consistency should be improved.
- `target_id`, `username`, `note`, `amount input`, `order text`, and transaction data were checked in the audited PayOS/admin/top-up surfaces. The clearest user-controlled gap is stored username in admin lists.

Risk:

- Admin-only HTML injection/display breakage risk from malicious Telegram names or stored fields.
- Low direct public impact, but admin views are operationally sensitive during payment review.

Safe fix recommendation:

- In C3, add a static escaping test for PayOS/admin/top-up HTML paths.
- Escape all stored usernames, order text, note fields, and transaction data before HTML rendering.

Suggested next task: `C3`

## 7. Secret Management

Status: `PARTIAL`

Current file/function:

- `bot.py:215`: `mask_secret`.
- `bot.py:223`: `_log_secret_values`.
- `bot.py:276`: `sanitize_log_text`.
- `bot.py:376`: `TELEGRAM_TOKEN` from env.
- `bot.py:452`: `OPENAI_API_KEY` from env.
- `bot.py:458`: `SHOPAIKEY_API_KEY` from env.
- `bot.py:480`: `KEY4U_API_KEY` from env.
- `bot.py:844`: `MINIMAX_API_KEY` from env.
- `bot.py:858` through `bot.py:860`: PayOS keys from env.
- `.gitignore`.

Findings:

- Hardcoded `TELEGRAM_TOKEN`: no hardcoded token found in runtime `bot.py`; it loads `TELEGRAM_TOKEN` or `BOT_TOKEN` from environment. `token tele.txt` exists but contains no Telegram-token-shaped value in this audit.
- Hardcoded `PAYOS_CLIENT_ID`/`PAYOS_API_KEY`/`PAYOS_CHECKSUM_KEY`: no hardcoded runtime values found; all load from env.
- Hardcoded MiniMax/OpenAI/ShopAIKey secrets: no hardcoded runtime values found; all load from env. Test files contain dummy values such as `test-key`, `configured`, or `sk-key4u-secret-123456789` for masking tests.
- Secret-like repo files: `mã dự phòng payos-backupcode.txt` is non-empty and appears secret-like by filename/content length. This should be removed/rotated outside this audit branch if it contains real recovery material.
- `.env` in `.gitignore`: yes. `.gitignore` excludes `.env` and `*.env`.
- Logs do not print full secrets: partial. Known secret values are masked by `sanitize_log_text`, PayOS key admin commands show fingerprints/lengths only, and local worker prints only whether a token is configured. Some provider calls necessarily place tokens in HTTP headers/URLs internally, but no direct full-secret logging was found in the audited payment/admin paths.

Risk:

- Secret-like plaintext backup-code file in repo is a high operational risk if real.
- Log sanitizer only masks values known to the running process; historical logs or unknown secret files are still a risk.

Safe fix recommendation:

- In C1/C4, verify whether `mã dự phòng payos-backupcode.txt` contains real recovery codes. If real, rotate/revoke outside code, remove from repo history through a dedicated secret-removal process, and add denylist scanning.
- Keep runtime secrets environment-only and keep PayOS fingerprint commands masked.

Suggested next task: `C1`

## 8. IP And Security Events

Status: `PARTIAL`

Current file/function:

- `bot.py:3237`: `security_events` table.
- `bot.py:32972`: `latest_security_event`.
- `bot.py:32992`: `record_anomaly`.
- `bot.py:143744`: PayOS webhook records an anomaly only when blocked by emergency/payment freeze.
- `bot.py:90006`: trial status text notes Telegram `/start` has no user IP.

Findings:

- PayOS webhook records request IP/user-agent: missing. `webhook_payos` does not read `request.client.host`, `X-Forwarded-For`, or `User-Agent`.
- Security event table/helper exists: yes. `security_events` and `record_anomaly` exist.
- IP blocking exists: missing for PayOS/webhook risk. Trial bonus has IP hash concepts for web/HTTP/WebApp claims, but no general IP blocklist/rate limit for PayOS webhook was found.
- Telegram messages expose user IP: no. Telegram bot updates do not expose user IP; code text explicitly notes Telegram `/start` has no user IP and IP hash only applies when a web/HTTP/WebApp claim safely provides it.

Risk:

- Invalid-signature or suspicious PayOS webhook activity lacks IP/user-agent forensics.
- No IP block/rate-limit path for repeated fake webhook attempts.

Safe fix recommendation:

- In C3, add safe request metadata capture for PayOS webhook security events: timestamp, route, remote IP from trusted proxy headers, user-agent, signature status, order code if present, and reason. Do not expose IPs to public users.
- In C2/C3, add alert thresholds for repeated invalid signatures by IP/user-agent and a reversible admin blocklist if needed.

Suggested next task: `C3`

## No-Touch Confirmation

Behavior changed: `NO`

Not touched:

- PayOS credit/debit: `NO`
- Wallet ledger: `NO`
- `/naptien`: `NO`
- Payment webhook behavior: `NO`
- Pricing: `NO`
- Voice/TTS: `NO`
- Subtitle/dubbing: `NO`
- Video/multiscene: `NO`
- Music/Suno: `NO`
- Image/image-to-video: `NO`
- DB migration: `NO`
- Web/app/standalone: `NO`

Recommended follow-up branches:

- `hotfix/p0-17c1-payos-signature-idempotency`: require signed `data.status == PAID`, add paymentLinkId/transaction-id idempotency and webhook replay tests.
- `hotfix/p0-17c2-topup-limits-admin-controls`: add top-up cooldowns, rolling limits, per-user lock/block, PayOS order cancel controls.
- `hotfix/p0-17c3-payment-observability-static-tests`: add escaping tests, webhook security event metadata, PayOS risk report, fake webhook test matrix.
- `hotfix/p0-17c4-secret-file-cleanup`: verify/rotate/remove secret-like plaintext files and add repo secret scanning.
