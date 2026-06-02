# Telegram Group Security Audit

Date: 2026-06-02
Scope: `bot.py`, operator/brain command paths, worker/n8n runbook surface.

## Summary

TOAN AAS must not automatically change Telegram group identity or member/admin permissions. Group title, group photo, group description, group permissions, and admin/member rights remain manual admin actions inside Telegram.

## Dangerous API Scan

The codebase was scanned for these Telegram group management APIs:

- `set_chat_title`
- `set_chat_photo`
- `set_chat_description`
- `delete_chat_photo`
- `set_chat_permissions`
- `promote_chat_member`
- `restrict_chat_member`
- `ChatAdministratorRights`

Result: no executable Telegram group management call was found. The method names now only appear in a security denylist and documentation so operator/AI requests can be blocked explicitly.

## Hardened Paths

- `/brain <natural language>`: blocks requests that ask to rename a group, change group photo/description, change permissions, promote admins, or restrict members.
- `/api/operator/command/run`: blocks the same natural-language group management requests before execution.
- Operator worker spec: includes a rule that Claude/n8n/tool workers must not call or simulate Telegram group management.

## Non-Goals

- No PayOS code changed.
- No billing/xu code changed.
- No database schema changed.
- No Telegram group management command was added.
- No environment variable was added.

## Operational Rule

Do not grant the bot `Change group info` or broad admin/member-management permissions. If a group setting must change, the human admin should do it manually in Telegram.
