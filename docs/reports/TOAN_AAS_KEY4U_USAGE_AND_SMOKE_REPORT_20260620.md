# TOAN AAS Key4U Usage And Smoke Report

Date: 2026-06-20

## Scope

This report covers Key4U admin-only smoke tooling and usage/status display. Public customer traffic remains OFF.

## Implemented

- `/key4u_status` shows config, smart routing, public/admin flags, endpoint readiness, smoke state, manual balance, and local usage summary.
- `/key4u_usage` queries configured usage/balance endpoints when present and falls back to safe `NEED_ENDPOINT` status when missing.
- `/key4u_set_manual_balance <usd>` stores admin-observed dashboard balance without calling provider APIs.
- Smoke events are recorded in `provider_usage_events` for local summaries.
- Key4U smoke commands are admin-only and no-Xu.

## Smoke Commands

| Command | State |
| --- | --- |
| `/tool_test_key4u_chat` | implemented, requires configured API key/model |
| `/tool_test_key4u_vision` | implemented, requires configured vision model |
| `/tool_test_key4u_image` | implemented as guarded image status/smoke path |
| `/tool_test_key4u_image_edit` | implemented, documented edit endpoints only |
| `/tool_test_key4u_video` | implemented async submit smoke |
| `/key4u_video_job` | implemented async job query |
| `/tool_test_key4u_tts` | safe `NEED_DOCS` unless endpoint/model configured |
| `/tool_test_key4u_stt` | safe `NEED_DOCS` unless endpoint/model configured |
| `/tool_test_key4u_suno` | safe `NEED_DOCS` unless endpoint/model configured |
| `/key4u_suno_job` | safe `NEED_DOCS` unless endpoint configured |
| `/tool_test_key4u_rerank` | safe `NEED_DOCS` unless endpoint/model configured |

## Live Test Status

Not executed in this code pass because no Key4U secret is stored in repo. Admin can run smoke tests after setting Railway ENV.

Expected safe states:

- Missing endpoint: `NEED_ENDPOINT` or `NEED_DOCS`.
- Missing model: sanitized fail with model/config hint.
- Provider failure: sanitized error class and short message only.

## Public Access

Blocked by default:

- `KEY4U_PUBLIC_ENABLED=false`
- `PROVIDER_FALLBACK_ENABLED=false`
- smoke commands require admin.

## Secret Logging

Confirmed design:

- No API key is displayed.
- `/key4u_usage` does not log raw key or full response.
- Smoke reports store status/model/latency/error class only.
