# TOAN AAS Key4U Provider Hub

Date: 2026-06-20

## Role

Key4U is a parallel provider hub for TOAN AAS. It is not the default production provider and does not replace ShopAIKey, OpenRouter, OpenAI, or Gemini.

- Primary provider remains: ShopAIKey where already live/pass.
- Key4U role: admin smoke, backup candidate, missing-capability research.
- WokuShop role: parked due higher cost until explicitly reopened.

## Runtime Safety

- `KEY4U_PUBLIC_ENABLED=false` by default.
- `KEY4U_ADMIN_SMOKE_ENABLED=true` allows owner/admin test commands only.
- `PROVIDER_FALLBACK_ENABLED=false` keeps automatic customer fallback closed.
- No Xu deduction in Key4U smoke commands.
- No API key, raw prompt, full provider response, token, or long output URL logging.

## Supported Capability Slots

| Capability | Key4U state | Notes |
| --- | --- | --- |
| Chat | admin smoke | OpenAI-compatible route when model is configured. |
| Vision | admin smoke | Requires configured vision model. |
| Image edit | admin smoke | Uses documented edit endpoints only. |
| Video create/query | admin smoke | Async job flow, public closed until smoke/cost gate. |
| TTS/STT/Suno/Rerank | need docs/config | Command stubs report `NEED_DOCS` instead of guessing endpoints. |

## Admin Commands

- `/key4u_status`
- `/key4u_usage`
- `/key4u_set_manual_balance <usd>`
- `/tool_test_key4u_chat [model]`
- `/tool_test_key4u_vision`
- `/tool_test_key4u_image`
- `/tool_test_key4u_image_edit [nano]`
- `/tool_test_key4u_video [model]`
- `/key4u_video_job <task_id>`
- `/tool_test_key4u_tts`
- `/tool_test_key4u_stt`
- `/tool_test_key4u_suno`
- `/key4u_suno_job <task_id>`
- `/tool_test_key4u_rerank`
- `/provider_matrix`

## Usage Reporting

Key4U usage can come from three places:

1. Remote usage endpoint if `KEY4U_USAGE_ENDPOINT` is configured.
2. Remote balance endpoint if `KEY4U_BALANCE_ENDPOINT` is configured.
3. Local smoke summary from `provider_usage_events`.

When Key4U has no documented usage endpoint, `/key4u_usage` reports `NEED_ENDPOINT` safely and still shows local smoke history plus optional admin-entered dashboard balance.

## Launch Rule

Key4U customer routing remains closed until:

1. Admin smoke passes for the exact capability.
2. Cost/margin is confirmed.
3. Public flag is explicitly enabled.
4. Auto-freeze/refund behavior is verified.
