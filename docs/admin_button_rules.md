# TOAN AAS Admin Button Rules

## Scope

P0.14 only cleans admin UX, back routing, Provider Management copy, command descriptions, and safe diagnostics.

Do not use this document as approval to change PayOS, `/naptien`, wallet ledger, pricing, public product flow, provider secrets, deployment, or DB migrations.

## Admin Screen Format

Every admin section should use:

1. Title.
2. Purpose: one short sentence.
3. Safe note: no secret, no Xu change, no provider call unless confirmed.
4. Important commands with descriptions.
5. Quick buttons.
6. Back/Admin/Menu chinh row.

## Button Layout

- Max 2 columns except long full-width action.
- Dangerous actions require confirm screen.
- Provider paid real test requires explicit confirm.
- Freeze/unfreeze requires confirm.
- Refund/manual wallet action requires confirm.

Default rows:

- Row 1: primary actions.
- Row 2: status/report actions.
- Row 3: freeze/test/refresh if relevant.
- Last row: `[⬅️ Quay lại] [🏠 Menu chính]` or `[⚙️ Admin] [🏠 Menu chính]`.

## Callback Naming

Use scoped callbacks:

- `admin:<section>:<action>[:id]`
- `provider:<provider>:<action>`
- `job:<feature>:<action>:<job_id>`

Existing Telegram menu callbacks may continue using `menu|<action>` when routed through `ADMIN_MENU_PAGE_HANDLERS`.

Do not add ambiguous callbacks like `back`, `menu`, `test`, or `status` without scope.

## Command Descriptions

### Provider

- `/providers` — open Provider Management and read configured/frozen/smoke state.
- `/provider_status` — read provider/audio/video status.
- `/shopaikey_usage` — refresh ShopAIKey usage, no API key shown.
- `/provider_freeze <provider> <reason>` — freeze one faulty provider route.
- `/provider_unfreeze <provider>` — reopen provider after smoke PASS.
- `/smoke_test_provider <provider> --confirm-paid` — chưa có lệnh này; use provider-specific smoke commands.

### Music/Suno

- `/music_engine_status` — chưa có lệnh này; use `/music_provider_status`.
- `/music_suno_jobs` — list recent Suno jobs.
- `/music_suno_job <MUS-id>` — inspect one Suno job.
- `/music_suno_poll <MUS-id>` — poll provider and download audio if available.
- `/music_suno_admin_test --confirm-paid` — submit real Suno admin-only test; can spend provider credit.

### Video

- `/video_engine_status` — chưa có lệnh này; use `/video_provider_status`.
- `/video_multiscene_engine_status` — read multiscene readiness.
- `/video_multiscene_job <job_id>` — inspect multiscene progress by parent id.
- `/video_multiscene_poll <job_id>` — poll scenes and stitch only when all files are valid.
- `/tool_test_video_multiscene basic 3 --confirm-paid` — real 3-scene admin test.
- `/shopaikey_video_job_status <job_id>` — diagnostic status route.
- `/shopaikey_video_content_probe <job_id> --confirm-paid` — chưa có lệnh này.

### Bill/Xu

- `/add_xu <telegram_id> <amount>` — chưa có lệnh này; current command is `/add <telegram_id> <amount>`.
- `/deduct_xu <telegram_id> <amount>` — chưa có lệnh này; current command is `/deduct <telegram_id> <amount>` and needs confirm policy.
- `/set_plan <telegram_id> <plan_code>` — chưa có lệnh này.
- `/add_membership <telegram_id> <tier> <days>` — chưa có lệnh này.
- `/grant_combo <telegram_id> <combo_code>` — grant combo if enabled.

### Finance

- `/finance_dashboard` — finance overview.
- `/revenue_report [YYYY-MM|YYYY]` — revenue report.
- `/expense_report [YYYY-MM|YYYY]` — expense report.
- `/profit_report [YYYY-MM|YYYY]` — profit/loss report.
- `/expense_add <amount_vnd> <category> <vendor> <note>` — add an expense.
- `/finance_export YYYY-MM` or `/finance_export YYYY` — export report.

### Freeze/Queue

- `/maintenance_status` — maintenance status.
- `/freeze_status` — freeze status.
- `/freeze_video <reason>` — freeze public video.
- `/unfreeze_video` — unfreeze video after checks.
- `/queue_status` — job queue state.
- `/job_status <job_id>` — one job status.
- `/refund_job <job_id>` — manual refund; confirm required.
- `/clear_job_lock <job_id>` — clear stuck job lock; confirm required.
- `/freeze_tools <reason>` — freeze tools.
- `/unfreeze_tools` — unfreeze tools.
