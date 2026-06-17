# TOAN AAS Key4U/Kling Duration Investigation

Date: 2026-06-17

## Scope

This report checks why short video jobs may return around 6 seconds while TOAN AAS pricing/UI describes one scene as 8 seconds. It focuses only on video duration behavior and admin debug readiness. It does not change public pricing, PayOS, top-up, wallet balance, or customer billing.

## Findings

### 1. TOAN AAS order/pricing assumes 8 seconds

The current video order builder uses `VIDEO_ORDER_DEFAULT_BASE_SECONDS = 8`. The price table text also describes each short-video tier as `1 cảnh / 8 giây`.

This means the customer-facing plan is currently built around 8 seconds per base scene.

### 2. Current ShopAIKey custom Veo payload does not enforce duration

The existing ShopAIKey custom video submit route uses `/v1/video/generations` and sends:

- `model`
- `prompt`
- `metadata.aspect_ratio`
- `metadata.enhance_prompt`
- `metadata.enable_upsample`

It does not send `seconds`, `duration`, or `duration_seconds` for Veo models.

The ShopAIKey custom Veo/Grok docs show:

- Veo request fields: `model`, `prompt`, `metadata.images`, `metadata.enhance_prompt`, `metadata.aspect_ratio`, `metadata.enable_upsample`
- Grok request fields include `metadata.duration`

So for the current Veo custom endpoint, TOAN AAS is not currently proving/enforcing 8 seconds at submit time. If a provider returns 6 seconds, it is likely provider/model default behavior or prompt/model interpretation, not a hard-coded TOAN AAS `seconds=6` field in the custom Veo payload.

### 3. ShopAIKey OpenAI-compatible video endpoint supports `seconds`

ShopAIKey docs also include an OpenAI-compatible `POST /v1/videos` endpoint with multipart fields:

- `model`
- `prompt`
- `seconds`
- `input_reference`

Example uses `seconds=8`, and the response includes `"seconds": "8"`.

This is the cleanest documented route for enforcing duration, but the current TOAN AAS video flow is not using this route for the custom Veo/Grok public flow.

### 4. Current Key4U video wrapper does not enforce duration

The current Key4U provider wrapper sends:

- `model`
- `prompt`
- `aspect_ratio`
- `enhance_prompt`
- `enable_upsample`

It does not send `seconds`, `duration`, or `duration_seconds`.

The admin smoke default prompt also contains the phrase `6-second ...`, so a Key4U smoke returning 6 seconds can be caused by both provider default behavior and the smoke prompt wording.

### 5. Do not sell extra seconds yet for 1000/1200/1500

Until TOAN AAS runs a real admin smoke proving that the provider accepts duration and returns the requested duration, do not sell per-second add-ons for 1000/1200/1500. Keep any extra-duration pricing as planning/report-only.

## Commands Added

### `/video_debug_tier_payload <tier> [seconds]`

Admin-only. No provider call. No Xu deduction.

Shows:

- tier/price
- order base seconds
- requested debug seconds
- ShopAIKey payload keys
- ShopAIKey metadata keys
- Key4U payload keys
- whether either payload currently includes `seconds/duration`

### `/video_test_tier_duration <tier> <seconds> [CONFIRM]`

Admin-only. Safe dry-run. No provider call. No Xu deduction.

Even with `CONFIRM`, the command does not submit a job while the current payload has no duration field. This avoids burning provider credit on a test that cannot prove duration.

## Recommendation

1. Keep current public video tiers focused on base short-video creation.
2. Do not advertise/sell exact extra seconds for premium tiers until one of these is implemented and smoke-tested:
   - Switch a duration-specific smoke path to ShopAIKey `POST /v1/videos` with `seconds=8/10`.
   - Add a documented duration field for the Key4U/Kling endpoint after Key4U docs or support confirms the accepted parameter.
3. Update the public price table only after the provider returns a task/result proving the requested duration.

## Not Touched

- PayOS
- `/naptien`
- payment webhook
- wallet/Xu balance
- public billing deduction/refund core
- ShopAIKey stable video submit/poll behavior
- Key4U public gate
- database destructive migration
