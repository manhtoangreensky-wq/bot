# P0.CATALOG.1 Provider Catalog Audit

Generated: 2026-07-06

Scope: planning/audit only. This document does not change runtime routes, live prices, wallet logic, provider calls, or database schema.

## Sources

### ShopAIKey

- https://shopaikey.com/models
- https://shopaikey.com/api-docs
- https://shopaikey.com/docs/veo-video

### Key4U

- https://docs.key4u.shop/api-36908536
- https://docs.key4u.shop/doc-2182560
- https://docs.key4u.shop/api-36908543
- https://docs.key4u.shop/api-36908545
- https://docs.key4u.shop/doc-2182561
- https://docs.key4u.shop/api-36908555
- https://docs.key4u.shop/api-36908556
- https://docs.key4u.shop/api-36908551
- https://key4u.shop/models

## Current TOAN AAS References Inspected

- `config/pricing_matrix_draft.json`
- `services/pricing_guide_content.py`
- `services/video_provider_router.py`
- `services/video_final_output.py`
- `providers/key4u_provider.py`
- `providers/video_generic_http_provider.py`

Current public-facing price references found:

| Family | Current ranges |
| --- | --- |
| Video | Bảng canonical hiện hành có 10 tier ID; giá bán và thời lượng lấy từ `services/video_ai_real_pricing.py`, tier ID không phải Xu. |
| Image | 50, 150-200, 300-400, 500-600 Xu |
| Music | separate product family; not changed |
| SubDub | separate product family; not changed |

Current provider routing reference:

- Default video provider chain is `shopaikey_video,key4u_video,toanaas_video,veo,kling,generic_http`.
- ShopAIKey and Key4U video adapters advertise `text_to_video`, `image_to_video`, `video_to_video`, `multi_scene_video`, and `scene_video`.
- Current charge policy copy says TOAN AAS shows an invoice before processing and only charges after confirmation and a valid result.

## ShopAIKey Video Audit

Official video contract from ShopAIKey docs:

- Base URL: `https://api.shopaikey.com`
- Submit: `POST /v1/video/generations`
- Status: `GET /v1/video/generations/{task_id}`
- Auth: `Authorization: Bearer <your-api-key>`
- Submit response: `data.task_id`
- Running status: `data.status` such as `queued` or `processing`
- Completion status: `data.status == SUCCESS`
- Result URL path: `data.result_url`
- Progress field: `data.progress`, shown as a string such as `50%`
- Failure status: `data.status == FAILURE`, with `data.fail_reason`

ShopAIKey supports text-to-video and image-to-video through the same video generation endpoint. Image-to-video uses `metadata.images`.

### ShopAIKey Video Models

| Model | Capability | Submit | Status | Result path | Cost confidence | Recommended tier | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `veo2-fast` | text-to-video, image-to-video | `/v1/video/generations` | `/v1/video/generations/{task_id}` | `data.result_url` | Low | Video Basic | Cost was not visible in static `/models` scrape; verify before runtime tier assignment. |
| `veo2` | text-to-video, image-to-video | same | same | same | Low | Video Standard | Use only after exact model cost is verified. |
| `veo2-pro` | text-to-video, image-to-video | same | same | same | Low | Video Pro | Higher tier candidate; cost verification required. |
| `veo3-fast` | text-to-video, image-to-video | same | same | same | Low | Video Basic / Standard | Docs show example request with `veo3-fast`. |
| `veo3` | text-to-video, image-to-video | same | same | same | Low | Video Standard | Cost verification required. |
| `veo3-pro` | text-to-video, image-to-video | same | same | same | Low | Video Pro | Cost verification required. |
| `veo3.1-fast` | text-to-video, image-to-video | same | same | same | Low | Video Basic / Standard | Current code defaults around `veo3.1-fast` in Key4U adapter; verify provider-specific availability. |
| `veo3.1` | text-to-video, image-to-video | same | same | same | Low | Video Pro | Cost verification required. |
| `veo3.1-pro` | text-to-video, image-to-video | same | same | same | Low | Video Ultra | Cost verification required. |
| `grok-video-3` | text-to-video, image-to-video, duration metadata | same | same | same | Low | Video Basic / creative alt | Docs show `metadata.duration`, `metadata.ratio`, and `metadata.resolution`. |

Risk notes:

- Do not use HTTP 200 as progress.
- Do not mark final success until `data.status == SUCCESS`, `data.result_url` exists, MP4 downloads, validates, and is delivered once.
- If provider status remains processing, keep polling; do not fallback to another paid provider without explicit confirmation.

## ShopAIKey Image Audit

The public model page exposes some image model costs directly, but it is paginated/client-heavy. The following are visible in the static scrape:

| Model | Capability | Endpoint family | Cost visible | Recommended product |
| --- | --- | --- | --- | --- |
| `grok-imagine-image` | text-to-image / image generation | OpenAI-compatible image endpoint | `$0.2080` per generation / `676 VND` | Image Basic or Image Pro depending quality |
| `qwen-image-max-2025-12-30` | image generation | OpenAI-compatible image endpoint | `$0.5000` per generation / `1,625 VND` | Image Pro |
| `gpt-image-1.5` | image generation | OpenAI-compatible image endpoint | input/output token pricing, no fixed per-image total | Image Pro / edit after token budget verification |

Requested model families not confirmed in the static scrape:

- Nano Banana / `nano-banana-2` / `nano-banana-pro`
- Gemini image models
- Flux models including `flux-1.1-pro` and `flux.1-kontext-pro`

These should remain `NEED_COST_VERIFICATION` until the provider dashboard, model API, or a source page exposes exact cost and endpoint.

## Key4U Video Audit

Key4U docs are Apidog-generated pages. The loaded HTML confirms these endpoint names and page titles, but many request/response tables are embedded in the app payload and should be verified before runtime implementation.

Unified video endpoints observed:

- Base URL shown in docs snippets: `https://api.key4u.shop`
- Create video: `/v1/video/create`
- Query video: `/v1/video/query`
- Current repo defaults:
  - `KEY4U_VIDEO_CREATE_ENDPOINT=/v1/video/create`
  - `KEY4U_VIDEO_QUERY_ENDPOINT=/v1/video/query`
  - default model `veo3.1-fast`

Kling endpoints observed in docs:

- `/kling/v1/videos/text2video`
- `/kling/v1/videos/image2video`
- `/kling/v1/videos/video-extend`
- `/kling/v1/videos/effects`
- `/kling/v1/videos/multi-image2video`

Result fields requiring exact verification:

- `task_id` appears in docs snippets.
- Some docs snippets show `task_status`.
- Result/download fields such as `download_url` and `resource_without_watermark` must be verified against exact endpoint examples before wiring premium tiers.

### Key4U Candidate Models / Products

| Provider area | Endpoint | Candidate models | Cost confidence | Recommended use |
| --- | --- | --- | --- | --- |
| Unified video | `/v1/video/create` + `/v1/video/query` | `veo3.1-fast` from current repo default | Low | Fallback for normal video only after ShopAIKey is unavailable or unhealthy |
| Kling text-to-video | `/kling/v1/videos/text2video` | `kling-v2-5-turbo`, `kling-v2-5-pro`, `kling-v2-1` if visible/available | Low | High-quality route candidates after exact API/cost verification |
| Kling image-to-video | `/kling/v1/videos/image2video` | same Kling family | Low | Premium image-to-video |
| Kling video extension | `/kling/v1/videos/video-extend` | same Kling family | Low | Kéo dài video |
| Kling effects | `/kling/v1/videos/effects` | same Kling family | Low | Video hiệu ứng |
| Kling multi-image reference | `/kling/v1/videos/multi-image2video` | same Kling family | Low | Reference-heavy route candidate; public price comes from the canonical catalog |

Key4U should not be used as the first provider while ShopAIKey is configured and has usable balance. Use Key4U as fallback only, and do not perform paid fallback without explicit confirmation.

## Cost Confidence Summary

| Area | Endpoint confidence | Cost confidence | Reason |
| --- | --- | --- | --- |
| ShopAIKey video | High | Low | Official video endpoint/result contract is clear; per-model video prices were not visible in static model scrape. |
| ShopAIKey image visible models | Medium | High for visible rows | `grok-imagine-image` and `qwen-image-max-2025-12-30` costs are visible on `/models`. |
| ShopAIKey image requested families | Low | Low | Nano Banana/Gemini/Flux requested by task were not confirmed in static scrape. |
| Key4U unified video | Medium | Low | Endpoint names match docs and current repo defaults; exact response/cost must be verified. |
| Key4U Kling | Medium | Low | Endpoint names are visible; exact model availability/prices must be verified. |

## Safety Rules Before Implementation

Every paid provider submit must have:

- kill switch
- idempotency key
- provider task id persisted before retry
- no duplicate paid submit
- no paid fallback without explicit confirmation
- recovery command
- raw status command
- raw artifact delivery before postprocess

Every async provider must have:

- submit parser
- status parser
- result URL parser
- raw response persistence
- artifact download validator
- duplicate delivery lock
- charge after delivery only

Every new tier must have:

- mocked submit/status/result tests
- no live paid test requirement
- admin dry-run mode
- provider spend debug

## Implementation Recommendation

Runtime Video pricing is now owned by `services/video_ai_real_pricing.py`. Provider readiness still requires the existing guarded route checks; this audit must not override that source.
