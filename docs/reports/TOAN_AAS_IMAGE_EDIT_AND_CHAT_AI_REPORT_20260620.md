# TOAN AAS Image Edit and Chat AI Report 2026-06-20

Date: 2026-06-17

## Image edit readiness

The bot now exposes `get_image_edit_provider_readiness()` and `/image_edit_status`.

Provider posture:

- OpenAI image edit: real execution path exists through `images.edit` when env/key/feature gate are enabled and admin smoke passes.
- Gemini image edit: visible in readiness matrix but guarded because the real output path is not wired in this build.
- ShopAIKey image edit: visible in readiness matrix but guarded because the real edit-output path is not wired in this build.

## Public open rule

`/image_edit_public_open` is owner-only and opens public only when a real provider is ready and smoke status is PASS. `/image_edit_public_close` returns the feature to admin-only.

## Admin smoke commands

- `/tool_test_image_edit`: alias for the existing real OpenAI image edit smoke test.
- `/tool_test_ai_image_edit`: existing command, kept for backward compatibility.
- `/tool_test_gemini_image_edit`: guarded status command, no fake output.
- `/tool_test_shopaikey_image_edit`: guarded status command, no fake output.

## Chat AI vision

`/chat_ai_status` reports text chat readiness and vision provider readiness. Vision is considered ready only when a configured provider can process image input.

## User-facing rule

If image edit or vision provider is missing, users see a maintenance/upgrade message. Admin status commands keep the technical reason without exposing secrets.
