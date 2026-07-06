# P0.CATALOG.1 Product Tier Recommendation

Generated: 2026-07-06

Scope: product planning only. No runtime menu, provider route, pricing, wallet, PayOS, or database behavior is changed by this document.

## Pricing Formula

Use this rule before enabling any paid provider tier:

```text
public_price_xu >= provider_cost_xu * margin_multiplier + system_overhead_xu
```

Recommended defaults:

- Normal public tier: `margin_multiplier = 2.5`
- Premium/high-risk provider tier: `margin_multiplier = 3.0`
- System overhead: `30-80 Xu` for short image/video products, higher for multi-scene or postprocess-heavy jobs
- Keep margin target under the existing policy in `config/pricing_matrix_draft.json`.

Do not finalize 1000 / 1200 / 1500 Xu Kling tiers until exact Key4U model cost is verified.

## Proposed Image Products

| Public product | Current price reference | Proposed price | Hidden provider/model | Input | Output | Confidence | Notes |
| --- | ---: | ---: | --- | --- | --- | --- | --- |
| Tạo ảnh nhanh | 50 Xu | 50-100 Xu | ShopAIKey `grok-imagine-image` if quality passes | text | image | Medium | Visible provider cost is about 6.76 Xu/generation; keep as starter/basic. |
| Tạo ảnh chất lượng cao | 150-400 Xu | 200-400 Xu | ShopAIKey `qwen-image-max-2025-12-30` or verified image model | text | image | Medium | Visible provider cost is about 16.25 Xu/generation for qwen-image-max. |
| Sửa ảnh / thay nền | 350 Xu reference | 300-600 Xu | Nano Banana / Gemini / Flux only after verification | image + instruction | image | Low | Needs exact edit endpoint and cost. |
| Ảnh theo mẫu | 300-600 Xu | 400-600 Xu | reference-image capable model after verification | image/reference + text | image | Low | Must validate reference support before public opening. |

Public copy must hide provider names. Admin/debug can show provider/model/cost confidence.

## Proposed Video Products

| Public product | Current price reference | Proposed price | Hidden provider/model | Input | Output | Risk | Notes |
| --- | ---: | ---: | --- | --- | --- | --- | --- |
| Video nhanh | 200-300 Xu | keep 200/300 Xu | ShopAIKey `veo3-fast`, `veo3.1-fast`, or `grok-video-3` after cost verification | prompt | MP4 | Medium | Entry tier. Must not call provider if cost cannot fit margin. |
| Video từ ảnh | 300-600 Xu | 400-800 Xu | ShopAIKey Veo/Grok with `metadata.images` | image + prompt | MP4 | Medium | Good fit for product/photo-driven video. |
| Video chất lượng cao | 600-1000 Xu | 800-1000 Xu | ShopAIKey Pro model after cost verification | prompt/image | MP4 | High | Do not enable until exact cost and delivery reliability pass. |
| Video cao cấp Kling | 1000-1500 Xu | 1000/1200/1500 Xu draft only | Key4U Kling after exact verification | prompt/image/reference | MP4 | High | Use Key4U only after exact endpoint, result URL, and cost are known. |
| Video hiệu ứng | 1000-1500 Xu | draft only | Key4U `/kling/v1/videos/effects` | video/image + effect | MP4 | High | Requires exact request fields and result URL. |
| Kéo dài video | 1000-1500 Xu | draft only | Key4U `/kling/v1/videos/video-extend` | video | MP4 | High | Must avoid duplicate paid submits. |

## Product Family Matrix

| product_family | public_product_name | current_price_xu | proposed_price_xu | provider | provider_model | endpoint | expected_cost | gross_margin_estimate | quality_level | duration | input_type | output_type | risk_level | implementation_status | notes |
| --- | --- | ---: | ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| image_generate | Tạo ảnh nhanh | 50 | 50-100 | ShopAIKey | `grok-imagine-image` | image/OpenAI compatible | 676 VND visible | Good if priced >=50 Xu | basic | n/a | text | image | medium | planning | Verify visual quality before public routing. |
| image_generate | Tạo ảnh chất lượng cao | 200-400 | 200-400 | ShopAIKey | `qwen-image-max-2025-12-30` | image/OpenAI compatible | 1,625 VND visible | Good if priced >=150 Xu | pro | n/a | text | image | medium | planning | Fits current 200/300/400 tiers. |
| image_edit | Sửa ảnh / thay nền | 350 | 300-600 | ShopAIKey | Nano Banana/Gemini/Flux candidate | NEED_ENDPOINT | NEED_COST | Unknown | pro/edit | n/a | image + text | image | high | blocked_by_cost | Do not implement until endpoint/cost verified. |
| image_reference | Ảnh theo mẫu | 300-600 | 400-600 | ShopAIKey | reference-capable candidate | NEED_ENDPOINT | NEED_COST | Unknown | pro/reference | n/a | image/reference | image | high | blocked_by_cost | Need reference consistency tests. |
| video_text_to_video | Video nhanh | 200/300 | keep current if margin passes | ShopAIKey | `veo3-fast` / `veo3.1-fast` / `grok-video-3` | `/v1/video/generations` | NEED_COST | Unknown | starter | short | prompt | MP4 | high | blocked_by_cost | Provider contract known, price unknown. |
| video_image_to_video | Video từ ảnh | 300-600 | 400-800 | ShopAIKey | Veo/Grok image-to-video | `/v1/video/generations` | NEED_COST | Unknown | standard | short | image + prompt | MP4 | high | blocked_by_cost | Uses `metadata.images`. |
| video_reference_image | Video chất lượng cao | 800/1000 | 800-1000 | ShopAIKey | `veo3.1` / `veo3.1-pro` | `/v1/video/generations` | NEED_COST | Unknown | pro | short | prompt/image | MP4 | high | blocked_by_cost | Verify cost and provider availability. |
| video_high_end_kling | Video cao cấp Kling | 1000/1200/1500 | draft only | Key4U | `kling-v2-5-*` candidates | `/kling/v1/videos/text2video` | NEED_COST | Unknown | ultra | short | prompt | MP4 | high | docs_only | Exact model list/cost/result URL required. |
| video_effects | Video hiệu ứng | 1000/1200/1500 | draft only | Key4U | Kling effects | `/kling/v1/videos/effects` | NEED_COST | Unknown | ultra/effect | short | image/video + effect | MP4 | high | docs_only | Do not expose until mocked tests pass. |
| video_extend | Kéo dài video | 1000/1200/1500 | draft only | Key4U | Kling extension | `/kling/v1/videos/video-extend` | NEED_COST | Unknown | ultra/extend | extension | video | MP4 | high | docs_only | Must use idempotency and recovery. |

## Draft Public Menu Copy

Do not implement this menu in runtime yet.

### Image

- Tạo ảnh nhanh - tạo ảnh cơ bản từ mô tả ngắn.
- Tạo ảnh chất lượng cao - ảnh nhiều chi tiết hơn cho sản phẩm/quảng cáo.
- Sửa ảnh / thay nền - chỉnh ảnh theo yêu cầu.
- Ảnh theo mẫu - tạo ảnh bám ảnh tham khảo.

### Video

- Video nhanh - tạo video ngắn từ ý tưởng.
- Video từ ảnh - dùng ảnh sẵn có để tạo video.
- Video chất lượng cao - video ngắn chất lượng cao hơn.
- Video cao cấp Kling - video premium sau khi provider/cost đã xác minh.
- Video hiệu ứng - thêm hiệu ứng hoặc chuyển động đặc biệt.
- Kéo dài video - mở rộng video đã có.

Public copy rules:

- Do not show provider/API/model names to public users.
- Always show invoice before paid processing.
- If no deliverable artifact exists, do not charge.
- If external provider may take longer, say it may take a few minutes; do not show technical/provider words.

## Required Build Rules For Future Implementation

1. No paid submit without a kill switch and idempotency key.
2. Persist `provider_task_id` before any retry.
3. No paid fallback unless the user explicitly confirms the fallback spend.
4. Recovery command and raw status command must exist before public opening.
5. Raw provider MP4/image delivery must be possible before postprocess.
6. Charge only after validated artifact delivery.
7. Every provider route must have mocked submit/status/result tests.
8. Premium tiers must stay disabled until exact cost and result URL parsing are verified.

## Next Implementation Task

Recommended next task: `P0.CATALOG.2 Provider Catalog Admin Dry Run`.

Goal: add admin-only dry-run commands that list configured catalog entries, validate required ENV names, and run mocked parser tests without submitting paid provider jobs.
