# TOAN AAS Suno Music Integration Report - 2026-06-20

## Current Route

Suno music is routed through the Key4U provider adapter when configured:

- `KEY4U_SUNO_CREATE_ENDPOINT`
- `KEY4U_SUNO_QUERY_ENDPOINT`
- `KEY4U_DEFAULT_MUSIC_MODEL` or `KEY4U_SUNO_MODEL`

## Admin Smoke

- `/tool_test_suno_music`
- `/tool_test_key4u_suno`
- `/suno_job <task_id>`
- `/key4u_suno_job <task_id>`

Placeholder task ids are rejected locally and do not call the provider.

## Public Gate

- `SUNO_PUBLIC_ENABLED=false` by default.
- `/suno_public_open` requires readiness and smoke PASS/PASS_SUBMITTED.
- Gói video 200 Xu cannot buy Suno paid add-ons.

## Customer Failure Message

If Suno is not ready, customers see a friendly maintenance/upgrade message. No provider call and no Xu deduction happen.
