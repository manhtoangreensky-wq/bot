# TOAN AAS Key4U Provider Integration

Date: 2026-06-17

## Scope

Key4U is added as an optional backup provider for admin smoke tests only.
It does not replace ShopAIKey, OpenRouter, OpenAI, Gemini, or any public
customer provider route.

## Provider Roles

- ShopAIKey: primary media/provider route already used by TOAN AAS guards.
- Key4U: backup candidate and admin-only smoke test provider.
- WokuShop: parked due higher cost; do not call while parked.

## Environment

```env
KEY4U_ENABLED=false
KEY4U_API_KEY=
KEY4U_BASE_URL=https://api.key4u.shop
KEY4U_OPENAI_BASE_URL=https://api.key4u.shop/v1
KEY4U_CHAT_ENDPOINT=/v1/chat/completions
KEY4U_IMAGE_EDIT_ENDPOINT=/v1/images/edits
KEY4U_NANO_BANANA_EDIT_ENDPOINT=/fal-ai/nano-banana/edit
KEY4U_VIDEO_CREATE_ENDPOINT=/v1/video/create
KEY4U_VIDEO_QUERY_ENDPOINT=/v1/video/query
KEY4U_CHAT_MODEL=
KEY4U_VISION_MODEL=
KEY4U_IMAGE_EDIT_MODEL=grok-imagine-image-pro
KEY4U_NANO_BANANA_EDIT_MODEL=nano-banana
KEY4U_VIDEO_MODEL=veo3.1-fast
KEY4U_VIDEO_FALLBACK_MODELS=veo3.1-fast,pixverse-video,viduq3,kling-video,minimax-video,doubao-seedance
KEY4U_PUBLIC_ENABLED=false
KEY4U_ADMIN_SMOKE_ENABLED=true
PROVIDER_ROUTER_ENABLED=true
PROVIDER_FALLBACK_ENABLED=false
PROVIDER_FALLBACK_ORDER=shopaikey,key4u
WOKU_ENABLED=false
WOKU_PUBLIC_ENABLED=false
WOKU_ADMIN_SMOKE_ENABLED=false
WOKU_REASON=cost_high_parked
```

## Admin Commands

- `/key4u_status`
- `/tool_test_key4u_chat [model]`
- `/tool_test_key4u_vision`
- `/tool_test_key4u_image`
- `/tool_test_key4u_image_edit [nano]`
- `/tool_test_key4u_video [model]`
- `/tool_test_key4u_video_model <model>`
- `/tool_test_key4u_video_all` (lists candidates only; no batch submit)
- `/key4u_video_job <task_id>`
- `/provider_matrix`

## Safety Rules

- Admin-only.
- No Xu deduction.
- No public routing by default.
- No API key, prompt, raw provider response, or output URL logging beyond
  sanitized admin smoke metadata.
- Image generation is not guessed in V1; use documented edit endpoints only
  until a verified generation endpoint is confirmed.
- WokuShop remains parked and must not be called while cost is higher.

## Status Display

`/providers` and `/provider_matrix` show Key4U as a backup provider and WokuShop
as parked. Fallback remains OFF until admin explicitly opens it after smoke
tests and cost checks.
