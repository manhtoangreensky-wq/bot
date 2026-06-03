# TOAN AAS Operation Risk Plan

Status: current emergency operations checklist for the Telegram bot revenue phase.

## Purpose

TOAN AAS must protect user balance, payment history, database records, and operational evidence during abnormal situations. Emergency mode is a soft lock. It does not delete data, reset balances, rotate keys, or remove files.

## Emergency Lock Principles

- Do not DROP TABLE.
- Do not delete DB, users, payment records, backups, or ledger events.
- Do not reset credits.
- Do not rotate Telegram token or API keys from bot code.
- Do not pause/delete Railway service from bot code.
- Lock processing first, preserve data, then let owner inspect.

## Runtime Flags

Stored in `system_flags`:

- `emergency_lock`
- `maintenance_mode`
- `payment_freeze`
- `tool_freeze`
- `provider_freeze`
- `safe_mode_reason`
- `last_emergency_at`

Security/anomaly events are stored in `security_events`.

## Telegram Commands

- `/emergency_lock <reason>`: owner-only, freezes payments, tools, providers.
- `/emergency_unlock`: owner-only.
- `/emergency_status`: admin/owner.
- `/maintenance_on <reason>` and `/maintenance_off`: admin/owner.
- `/freeze_payments <reason>` and `/unfreeze_payments`: admin/owner.
- `/freeze_tools <reason>` and `/unfreeze_tools`: admin/owner.
- `/ops_plan`: admin/owner.
- `/backup_db`: owner/admin backup command.

## Risk Groups

1. Admin account risk.
2. Telegram bot token/session risk.
3. Railway/GitHub access risk.
4. PayOS, Xu, DB, and ledger risk.
5. Provider/API risk.
6. Customer abuse/fraud risk.
7. One-person operation risk.
8. Emergency recovery.

## Admin Account Risk

Signals:

- Unknown account tries admin commands repeatedly.
- Admin actions happen at unusual volume.
- Unexpected approval/credit operations.

Actions:

1. Run `/emergency_lock <reason>` if account compromise is suspected.
2. Run `/backup_db`.
3. Check Telegram active sessions.
4. Rotate Telegram bot token if needed.
5. Review GitHub/Railway access logs.

## Telegram Bot Risk

Signals:

- Bot replies from wrong brand/service.
- Webhook points to wrong deployment.
- Unknown service shares the same bot token.

Actions:

1. Run `/telegram_status`.
2. Run `/telegram_takeover`.
3. If still abnormal, pause old service manually in Railway.
4. Rotate bot token in BotFather and update Railway ENV.

## Railway / GitHub Risk

Signals:

- Unexpected deploy.
- Unknown commit.
- ENV changed without owner action.
- DB volume missing or changed.

Actions:

1. Pause Railway service manually if needed.
2. Check Railway Project/Workspace members.
3. Check GitHub repo Settings -> Collaborators / Manage access.
4. Rotate tokens/API keys if exposed.
5. Restore DB only after preserving current DB backup.

## PayOS / Xu / DB Risk

Signals:

- Duplicate credits.
- Amount mismatch.
- Negative balance.
- Unknown large credit adjustment.
- DB write errors.

Actions:

1. `/freeze_payments <reason>`.
2. `/backup_db`.
3. Inspect PayOS orders, pending deposits, credit events.
4. Do not delete ledger rows.
5. Correct with explicit admin audit note only after verifying evidence.

## Provider / API Risk

Signals:

- Provider error spike.
- 429/quota exhausted.
- API response malformed.

Actions:

1. `/freeze_tools <reason>` if customer experience is affected.
2. Run `/providers`.
3. Run `/tool_audit`.
4. Smoke test provider commands.
5. Do not open failed tools to customers.

Provider quota or PayOS signature errors alone should not auto emergency-lock the whole bot. Freeze tools/payment and debug first.

## Customer / Fraud Risk

Signals:

- Many bills in short time.
- Same order or amount repeatedly submitted.
- User tries internal/admin commands.
- High-speed paid tool calls.

Actions:

1. Keep evidence in logs/database.
2. Freeze specific flow if needed.
3. Do not delete user or bill history.
4. Escalate to owner for large adjustments.

## One-Person Operation Risk

Current owner should prepare:

- Owner Telegram ID in `OWNER_IDS`.
- Backup admin in `ADMIN_IDS` only when needed.
- GitHub collaborator access.
- Railway member/invite.
- PayOS/provider team or sub-account where available.

Scaling checkpoints:

- 20-50 paying users: add backup admin.
- 100+ paying users: split support, billing, technical roles.
- 500+ users: dashboard and alerting.
- 1000+ users: SOP, shifts, incident process.

## Emergency Checklist

1. Run `/emergency_lock <reason>`.
2. Run `/emergency_status`.
3. Run `/backup_db`.
4. Check Telegram sessions and BotFather token.
5. Check Railway deploy/ENV/volume.
6. Check GitHub commits/collaborators.
7. Check PayOS/provider dashboard.
8. Document what happened.
9. Only owner runs `/emergency_unlock` after verification.

## If Admin Telegram Is Hacked Or Lost

1. Pause Railway service manually.
2. Rotate bot token in BotFather.
3. Remove compromised Telegram ID from Railway `ADMIN_IDS` / `OWNER_IDS`.
4. Redeploy.
5. Restore DB only if current DB is damaged.

## If Bot Token Is Exposed

1. Revoke/rotate token in BotFather.
2. Update Railway ENV.
3. Restart deploy.
4. Run `/telegram_status`.
5. Run `/backup_db`.

## If Railway/GitHub Access Is Suspicious

1. Pause Railway service.
2. Remove unknown members.
3. Rotate deploy/API tokens.
4. Check recent commits.
5. Backup DB before any restore.

## Data Preservation Rule

Every emergency action must preserve:

- User balances.
- Payment records.
- Credit events.
- Pending bills.
- Provider logs.
- Audit/security events.
- Backups.

The goal is recovery and evidence preservation, not deletion.
