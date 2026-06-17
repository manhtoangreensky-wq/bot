# TOAN AAS - Key4U First Smoke Stabilization Report - 2026-06-17

## Scope

Key4U remains an admin-smoke backup provider only. This fix does not replace or degrade ShopAIKey, OpenRouter, OpenAI, Gemini, PayOS, top-up, wallet, billing, package, or public provider routing.

## Changes

- Added non-empty default smoke models:
  - Chat: `qwen-plus`
  - Vision: `gemini-2.5-flash`
- Added fallback model lists:
  - Chat: `qwen-plus,qwen-turbo,deepseek-chat,gemini-2.5-flash`
  - Vision: `gemini-2.5-flash,gemini-2.5-flash-all,gpt-4o-mini,qwen-vl-max`
  - Video: optional `KEY4U_VIDEO_FALLBACK_MODELS`
- Added limited fallback behavior for admin smoke commands:
  - Chat and vision try primary plus at most two fallbacks.
  - Video tries primary plus at most one fallback.
  - If admin passes a model in the command, only that model is tested.
- Improved smoke output:
  - `models_tried`
  - `fallback_used`
  - HTTP status
  - selected model
  - sanitized provider message
- Fixed video job polling to use `GET /v1/video/query?id=<task_id>`.
- Rejected placeholder task IDs locally before provider calls.
- Raised video create timeout to 60 seconds and kept timeout diagnostics non-empty.
- Added provider-safe video create payload fields:
  - `aspect_ratio=16:9`
  - `enhance_prompt=true`
  - `enable_upsample=false`
- Image/vision smoke now can reuse the latest admin image sent within 10 minutes; if no image exists, it returns a clear instruction and does not call the provider.

## Public Safety

- `KEY4U_PUBLIC_ENABLED=false` remains the default.
- Key4U is not public routing in this task.
- WokuShop remains parked.
- ShopAIKey remains primary/stable.
- No API key, prompt, raw response, payment token, or secret is logged or shown.

## Admin Commands Affected

- `/key4u_status`
- `/key4u_usage`
- `/tool_test_key4u_chat`
- `/tool_test_key4u_vision`
- `/tool_test_key4u_image_edit`
- `/tool_test_key4u_video`
- `/key4u_video_job`

## Remaining Before Public Parallel Use

- Run live admin smoke for chat, vision, image edit, video create, and video query.
- Confirm Key4U model names against real provider responses.
- Keep Key4U public routing OFF until repeated live smoke passes.
- Only after stability is proven, enable controlled fallback between ShopAIKey and Key4U by product capability.
