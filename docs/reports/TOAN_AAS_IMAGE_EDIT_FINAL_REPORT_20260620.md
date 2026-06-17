# TOAN AAS Image Edit Final Report - 2026-06-20

## Flow

User sends/selects an image -> chooses edit type -> enters edit request or chooses suggestions -> confirms price -> provider job -> real edited image -> friendly fail/refund if needed.

## Readiness

`get_image_edit_provider_readiness()` now exposes:

- provider/model/endpoint
- endpoint configured
- API key configured
- public enabled
- admin smoke status
- last smoke time
- missing env
- safe user message
- admin debug reason

## Admin Commands

- `/image_edit_status`
- `/tool_test_image_edit`
- `/tool_test_openai_image_edit`
- `/tool_test_gemini_image_edit`
- `/tool_test_shopaikey_image_edit`
- `/image_edit_public_open`
- `/image_edit_public_close`

## Public Gate

Public image edit only opens when a real provider path is ready and smoke has passed. The bot must not fake an edited image.
