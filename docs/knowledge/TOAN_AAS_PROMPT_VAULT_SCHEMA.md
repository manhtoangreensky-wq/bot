# TOAN AAS Prompt Vault Schema

Date: 2026-06-17

Purpose: define a shared prompt vault that bot/app assistants can use to recommend content, image, video, caption, translation, support and pricing workflows without hard-coding one-off prompts in callbacks.

## Storage

Draft data file:

- `data/prompt_vault/prompts.json`

This is a draft knowledge file only. Runtime code must not import it until a separate implementation task approves loading, indexing and i18n behavior.

## Prompt Object

```json
{
  "id": "video_sales_001",
  "category": "video",
  "sub_category": "sales",
  "title": "Kịch bản video bán hàng 30s",
  "use_case": "Tạo video TikTok bán sản phẩm",
  "language": "vi",
  "prompt": "...",
  "variables": ["product_name", "target_customer", "tone", "duration"],
  "recommended_tier": 400,
  "addons": ["voice", "subtitle"],
  "tags": ["tiktok", "affiliate", "sales"],
  "public": true,
  "requires_paid_render": false,
  "next_steps": ["choose_video_tier", "add_voice", "add_subtitle"]
}
```

## Required Fields

| Field | Type | Notes |
|---|---|---|
| `id` | string | Stable unique ID. |
| `category` | string | `video`, `image`, `caption`, `chatbot`, `translation`, `support`, `pricing`. |
| `sub_category` | string | Sales, cinematic, affiliate, product, etc. |
| `title` | string | Short UI-safe title. |
| `use_case` | string | When to use this prompt. |
| `language` | string | `vi`, `en`, `zh`, etc. |
| `prompt` | string | User-facing prompt template; no secrets. |
| `variables` | array | Variables bot/app should ask from user. |
| `recommended_tier` | number/null | Suggested Xu tier when a paid render is requested. |
| `addons` | array | Suggested add-ons such as voice/subtitle/music. |
| `tags` | array | Search/filter tags. |
| `public` | boolean | Safe to show to customers. |
| `requires_paid_render` | boolean | `false` for planning-only prompts. |
| `next_steps` | array | Buttons/flows to suggest next. |

## Categories

- `video.sales`: TikTok/Reels/product ads.
- `video.cinematic`: cinematic scenes, filmic ads, emotional story.
- `video.affiliate`: affiliate/TikTok Shop scripts.
- `video.product_review`: review, before/after, UGC.
- `image.ad`: product ad image prompts.
- `image.product`: product/studio/lifestyle prompts.
- `caption.hashtag`: captions and hashtag packs.
- `livestream`: live sales hooks and scripts.
- `chatbot.support`: CSKH replies and support escalation.
- `translation.dub`: subtitle, dub and localization prompts.
- `pricing.explanation`: package/tier explanation templates.

## Recommendation Rules

- If user asks for a quick test, recommend Nhanh gọn (`tier_id=200`) at 200 Xu for each 5-second scene.
- Recommend by public quality, duration and current sale price; never present tier IDs as Xu prices.
- For multi-scene Video orders, state the canonical discount: 2–5 scenes 10%, 6–10 scenes 15%, 11–20 scenes 20%; one scene has no discount and add-ons are separate.
- If user wants sales/ads or cinematic quality, recommend the closest ready public package by its current catalog description, never by the old numeric price ladder.
- Always suggest voice/subtitle/music as optional add-ons after a paid video tier is chosen.
- Do not claim provider readiness unless `/tool_public_status`, `/video_gate_status` or relevant smoke status says ready.

## Safety

- Do not store API keys, task IDs, private URLs or raw provider responses.
- Do not store customer personal data in prompt templates.
- Keep prompts reusable and variable-driven.
- Runtime loading must include language filtering and back-routing metadata before public use.
