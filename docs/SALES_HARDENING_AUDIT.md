# SALES HARDENING AUDIT

Date: 2026-06-02
Scope: TOAN AAS Phase 1 Step 9.

## Public routes

| Route | Public? | Returns | Risk | Action |
|---|---:|---|---|---|
| `/` | YES | Landing page | Low | Keep public. |
| `/landing` | YES | Landing page | Low | Keep public. |
| `/health` | YES | Compact health JSON and config booleans | Low | Keep public, no secrets. |
| `/status` | YES | Compact status, build, health and landing links | Low | Hardened to remove webhook/runtime details. |
| `/runtime` | NO | Runtime/webhook diagnostics | Medium if public | Protected by `OPERATOR_API_TOKEN`. |
| `/banner.png` | YES | Public banner asset | Low | Keep public. |
| `/LOGO.png` | YES | Public logo asset | Low | Keep public. |

## Admin commands

| Command | Exists? | Protected? | Notes |
|---|---:|---:|---|
| `/providers` | YES | YES | Shows configured/missing only. |
| `/sales_ready` | YES | YES | Reads PayOS real test setting and returns NOT READY/BETA READY/SALES READY. |
| `/costs` | YES | YES | Cost risk summary, no provider values. |
| `/payos_test_plan` | YES | YES | Manual 10k test checklist. |
| `/mark_payos_test` | YES | YES | Stores PASS/FAIL/NOT_TESTED in `system_settings`; does not alter payments. |
| `/dashboard` | YES | YES | Admin revenue dashboard. |
| `/backup_db` | YES | YES | Sends DB file to admin. |

## Sales blockers

1. Real PayOS 10k payment test must be completed and marked with `/mark_payos_test pass ...`.
2. Railway DB persistence/backup must be verified before onboarding multiple users.
3. Beta should remain manual-posting only; no auto publish or social APIs.

## Result

- `/health` remains public.
- `/status` is public but compact.
- `/runtime` is no longer public debug surface.
- Sales readiness can move from BETA READY to SALES READY only after admin marks PayOS real test PASS.
