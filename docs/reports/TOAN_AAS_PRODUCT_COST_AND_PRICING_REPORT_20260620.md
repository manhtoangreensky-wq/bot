# TOAN AAS Product Cost Audit + Final Pricing Matrix V1

Date: 2026-06-17
Status: audit/report only, no runtime pricing change

## Executive Summary

This report audits the current TOAN AAS bot/app product surface before the planned 2026-06-20 public launch. It creates a draft pricing matrix and prompt-vault structure without changing live runtime prices, PayOS, top-up, webhook, wallet, package, trial or provider execution code.

Key decisions:

- `1 Xu = 100 VND`.
- Video 200 Xu remains a starter/experience product, not a profit baseline.
- Latest owner directive sets the 200 Xu tier limit to `3/day`, `10/week`, `30/month` per user.
- Video 300/400/500/600/800 form the normal paid ladder.
- Video 1000/1500 are future/Kling/Seedance/premium placeholders and should stay `KEEP_OFF` until real provider smoke and cost pass.
- Many provider costs are still `CONFIG_ESTIMATE`, not invoice-verified provider costs.
- Items without measured provider cost are marked `NEED_COST`, not PASS.

Files produced by this task:

- `config/pricing_matrix_draft.json`
- `docs/knowledge/TOAN_AAS_PROMPT_VAULT_SCHEMA.md`
- `data/prompt_vault/prompts.json`

## Source Audit

Reviewed local sources:

- `bot.py`
- `local_worker.py`
- `.env.example`
- `docs/COMMAND_REGISTRY.md`
- `docs/reports/TOAN_AAS_VIDEO_TIER_MATRIX_20260620.md`
- `docs/reports/TOAN_AAS_IMAGE_EDIT_AND_CHAT_AI_REPORT_20260620.md`
- `docs/reports/TOAN_AAS_SUBTITLE_DUB_PIPELINE_REPORT_20260620.md`

Runtime files not changed by this report:

- PayOS and `/naptien`
- webhook
- wallet/Xu/top-up history
- package/combo/monthly plan logic
- trial 200 Xu logic
- provider execution paths

## Product Inventory

| Nhóm | Sản phẩm | Public status | Có tốn API? | Provider | Cost unit | Cost estimate | Current price | Recommended price | Margin status | Note |
| ---- | -------- | ------------- | ----------- | -------- | --------- | ------------: | ------------: | ----------------: | ------------- | ---- |
| Free / Planning | Prompt Meta AI | ON/free | No provider required | Local/LLM planning | request | 0/NEED_COST if LLM used | 0 | 0 | GREEN/NEED_COST | Keep free to upsell paid render |
| Free / Planning | Caption/Hashtag | ON/free | Optional LLM | Local/LLM | request | NEED_COST | 0 | 0 | NEED_COST | Good free entry |
| Free / Planning | Ý tưởng content | ON/free | Optional LLM | Local/LLM | request | NEED_COST | 0 | 0 | NEED_COST | Keep free/light |
| Free / Planning | Prompt ảnh/video | ON/free | Optional LLM | Local/LLM | request | NEED_COST | 0 | 0 | NEED_COST | Should feed paid image/video |
| Free / Planning | Storyboard | ON/planning | Optional LLM | Local/LLM | request | NEED_COST | 0/low | 0-30 | NEED_COST | Paid only if using expensive model |
| Free / Planning | Trend planning | ON/content-only | Optional LLM/search | Local/LLM | request | NEED_COST | 0/70 content pack | 0-70 | NEED_COST | Live internet trend should stay guarded |
| Chat AI | Chat text normal | ON if chat provider ready | Yes | OpenRouter/ShopAIKey/OpenAI/Gemini | request/tokens | NEED_COST | 5 Xu | 5-10 Xu | NEED_COST | Needs token usage reporting |
| Chat AI | Chat pro/deep | ON if provider ready | Yes | configured model | request/tokens | NEED_COST | 10-20+ Xu | 10-30 Xu | NEED_COST | Deep model must be priced by token |
| Chat AI | Chat hiểu ảnh | Guarded unless vision ready | Yes | vision provider | image request | NEED_COST | missing | 20-80 Xu | NEED_COST | Do not open without smoke/cost |
| Chat AI | TOAN AAS support AI | Should be free/cheap | Yes/KB | chat provider/knowledge | request | NEED_COST | 0 | 0-5 Xu | GREEN/NEED_COST | Sales/support tool |
| Image | Tạo ảnh AI low | Public if provider gate pass | Yes | ShopAIKey image | job | 25 Xu config | 50 Xu | 50 Xu | YELLOW | Starter image |
| Image | Tạo ảnh AI standard | Public if provider gate pass | Yes | ShopAIKey image | job | 150 Xu config | 200 Xu | 200-300 Xu | RED/YELLOW | Needs provider invoice |
| Image | Ảnh standard + warranty | Public if provider gate pass | Yes | ShopAIKey image | job + 1 retry | 150 Xu config, retry risk | 300 Xu | 250-300 Xu | YELLOW | If 250 chosen, margin tighter |
| Image | Ảnh high | Public if provider gate pass | Yes | ShopAIKey image | job | 250 Xu config | 400 Xu | 400 Xu | RED/YELLOW | Needs real provider cost |
| Image | Ảnh high + warranty | Public if provider gate pass | Yes | ShopAIKey image | job + 1 retry | 250 Xu config, retry risk | 600 Xu | 500-600 Xu | YELLOW | If 500 chosen, margin tighter |
| Image | Chỉnh sửa ảnh AI | Guarded | Yes | OpenAI/Gemini/ShopAIKey edit | job | NEED_COST | 350 Xu legacy | NEED_COST | NEED_COST | Must smoke real output before public |
| Image | Crop/resize/text/logo local | ON/free/low | No | Local | file | low overhead | 0 | 0-10 Xu | GREEN | Avoid provider calls |
| Video AI | 200 | Controlled beta | Yes | ShopAIKey VEO path | job | 150 Xu config | 200 Xu | 200 Xu | MARKETING_LOSS | 3/day, 10/week, 30/month |
| Video AI | 300 | Public beta if provider gate pass | Yes | same base line as 200 | job | 150 Xu config | 300 Xu | 300 Xu | YELLOW | Upsell after 200 |
| Video AI | 400 | Public beta if gate pass | Yes | ShopAIKey VEO path | job | 200 Xu config | 400 Xu | 400 Xu | YELLOW | Better prompt/style |
| Video AI | 500 | Gate required | Yes | ShopAIKey VEO path | job | 250 Xu config | 500 Xu | 500 Xu | YELLOW | Advanced tier |
| Video AI | 600 | Gate required | Yes | ShopAIKey VEO path | job | 300 Xu config | 600 Xu | 600 Xu | YELLOW | Main business tier |
| Video AI | 800 | Gate required | Yes | ShopAIKey VEO path | job | 400 Xu config | 800 Xu | 800 Xu | YELLOW | High tier |
| Video AI | 1000/1500 | KEEP_OFF | Yes | future provider | job | NEED_COST | 1000/1500 | KEEP_OFF | NEED_COST | Kling/Seedance future |
| Video AI | video dài/nhiều tập | KEEP_OFF | Yes | future provider/queue | duration/job | NEED_COST | missing | KEEP_OFF | NEED_COST | Needs load/cost/smoke |
| Video AI | frame video local | Guarded by worker | No provider | Local Worker/FFmpeg | render | low overhead | 50/100/150 Xu | 50/100/150 Xu | GREEN | Requires worker, not Railway direct render |
| Voice/Audio | TTS | Admin/pass if provider ready | Yes | ShopAIKey/Eleven/Fish/Edge fallback | chars/min | NEED_COST | 50 + blocks legacy | NEED_COST | NEED_COST | Need per-char/min cost |
| Voice/Audio | STT | Guarded | Yes | Deepgram/ASR provider | minute | NEED_COST | missing | NEED_COST | NEED_COST | Required for subtitle/dub |
| Voice/Audio | Music/SFX library | Guarded/library | Usually no provider | local/library | item | 0/low | 0/10 Xu | 0-10 Xu | GREEN | Library assets only |
| Voice/Audio | AI music | KEEP_OFF | Yes | music provider | 30s | NEED_COST | 300 Xu config | KEEP_OFF | NEED_COST | No public without smoke |
| Subtitle/Dub | Tạo phụ đề | Guarded | Yes | ASR | minute | NEED_COST | 20 Xu/min | NEED_COST | NEED_COST | Need ASR smoke/cost |
| Subtitle/Dub | Dịch phụ đề | Guarded | Yes | ASR + translation | minute | NEED_COST | 40 Xu/min | NEED_COST | NEED_COST | Need translation cost |
| Subtitle/Dub | Lồng tiếng | Guarded | Yes | ASR + TTS + mux | minute | NEED_COST | 100 Xu/min | NEED_COST | NEED_COST | Needs TTS/mux smoke |
| Subtitle/Dub | Phụ đề + lồng tiếng | Guarded | Yes | full pipeline | minute | NEED_COST | 120-150 Xu/min | NEED_COST | NEED_COST | Keep guarded until full pass |
| Documents/Storage | PDF/document tools | ON/free local | No/optional OCR | local/OCR | file | low/NEED_COST | 0 | 0 | GREEN/NEED_COST | OCR separate |
| Documents/Storage | Storage free | ON | No | Railway volume | MB/month | platform cost | 50MB free | 50MB free | GREEN | Text and files count real size |
| Documents/Storage | Storage add-on | Needs PayOS bridge | No provider | storage | 50MB/month | platform cost | 10k/50MB | 10k/50MB | GREEN | Payment flow separate |
| Support/Admin/Web | Ticket/support | ON | Optional LLM | DB/LLM | ticket/request | low/NEED_COST | 0 | 0 | GREEN/NEED_COST | Support should answer first, ticket behind |
| Support/Admin/Web | App assistant | Work in progress | Optional LLM | web app/LLM | request | NEED_COST | TBD | TBD | NEED_COST | Separate app audit needed |
| Support/Admin/Web | Affiliate/campaign/ERP | Internal/backlog | Optional | internal | module | NEED_COST | TBD | TBD | NEED_COST | Do not sell until productized |

## Provider Cost Findings

| Provider | Found data | Status | Notes |
|---|---|---|---|
| ShopAIKey chat | manual smoke pass from previous work | NEED_COST | Need token/model pricing or usage export by model |
| ShopAIKey image | config provider cost 25/150/250 Xu | CONFIG_ESTIMATE | Need real per-image charge by model/ratio |
| ShopAIKey video | config provider cost 150/150/200/250/300/400 Xu | CONFIG_ESTIMATE | Need invoice/usage by video job/model |
| ShopAIKey TTS | manual smoke pass | NEED_COST | Need per-character/minute cost |
| Key4U | not integrated in this task | NEED_COST | Next provider task can add smoke/status |
| WokuShop | parked due higher cost | NEED_COST/KEEP_OFF | Do not integrate unless approved |
| Gemini | key/config may exist | NEED_COST | Need model-specific pricing |
| OpenAI | image edit path exists if enabled | NEED_COST | Need image edit pricing by model |
| OpenRouter | text provider | NEED_COST | Need token usage/cost table |
| Deepgram | STT candidate | NEED_COST | Need minute pricing |
| Fish/ElevenLabs/Edge TTS | voice path exists/fallback | NEED_COST | Edge local/free-ish, paid providers need cost |
| Local Worker/FFmpeg | local processing | LOW_OVERHEAD | Must include CPU/storage/queue overhead and avoid Railway direct OOM |

## Video Tier Matrix

| Gói | Giá Xu | Giá VND | Loại | Model/provider | Chất lượng | Thời lượng mặc định | Tối đa | Ratio | Add-on | Limit | Cost estimate | Margin | Public |
| --- | -----: | ------: | ---- | -------------- | ---------- | ------------------- | ------ | ----- | ------ | ----- | ------------: | ------ | ------ |
| Video Trải Nghiệm | 200 | 20.000 | gói mồi | current ShopAIKey VEO path | cơ bản/trải nghiệm | current provider default | short only | 9:16 ưu tiên | add-on guarded | 3/day, 10/week, 30/month | 150 Xu config | MARKETING_LOSS | controlled beta |
| Video Cơ Bản | 300 | 30.000 | upsell | same base model as 200 | cơ bản ổn định | current provider default | short only | 9:16/16:9 if provider supports | add-on optional | normal job lock | 150 Xu config | YELLOW | beta if gate pass |
| Video Phổ Thông | 400 | 40.000 | normal | ShopAIKey VEO path | tốt hơn 300 | current provider default | short only | 9:16/16:9 | add-on optional | normal job lock | 200 Xu config | YELLOW | beta if gate pass |
| Video Nâng Cao | 500 | 50.000 | advanced | ShopAIKey VEO path | prompt/style/camera tốt hơn | current provider default | short only | 9:16/16:9 | add-on optional | can limit/day | 250 Xu config | YELLOW | gate required |
| Video Bán Hàng | 600 | 60.000 | business | ShopAIKey VEO path | CTA/prompt enhancer | current provider default | short only | 9:16/16:9 | voice/subtitle recommended | can limit/day | 300 Xu config | YELLOW | gate required |
| Video Cao Cấp | 800 | 80.000 | high | ShopAIKey VEO path | tốt nhất nhóm hiện tại | current provider default | short only | 9:16/16:9 | voice/subtitle/music recommended | can limit/day | 400 Xu config | YELLOW | gate required |
| Video Kling/Seedance | 1000 | 100.000 | future | Kling/Seedance future | TBD | TBD | TBD | TBD | TBD | off | NEED_COST | KEEP_OFF | no job |
| Video Premium Future | 1500 | 150.000 | future premium | premium future | TBD | TBD | TBD | TBD | TBD | off | NEED_COST | KEEP_OFF | no job |

## Duration Pricing

Current recommendation: do not sell public extra seconds until provider duration billing is verified.

| Base tier | Base seconds | Extra seconds allowed | Extra cost per second | Max seconds public | Note |
| --------- | -----------: | --------------------: | --------------------: | -----------------: | ---- |
| 200 | provider default | no | NEED_COST | provider default | Keep short; marketing tier |
| 300 | provider default | no | NEED_COST | provider default | Same base line as 200 |
| 400 | provider default | not yet | NEED_COST | provider default | Add +2s only after duration cost is known |
| 500 | provider default | not yet | NEED_COST | provider default | Add +2-4s only after duration cost is known |
| 600 | provider default | not yet | NEED_COST | provider default | Main sales tier, protect margin |
| 800 | provider default | not yet | NEED_COST | provider default | Can support longer only if provider pricing confirms |
| 1000/1500 | unknown | no | NEED_COST | no public | Future provider |

If provider later exposes duration pricing:

`extra_price_xu = ceil((provider_extra_cost_xu_per_second + platform_cost_xu + risk_buffer_xu) / target_cost_ratio)`

## Add-on Pricing Matrix

| Add-on | Applies to | Provider/worker | Cost basis | Recommended price | Public status |
| ------ | ---------- | --------------- | ---------- | ----------------: | ------------- |
| Prompt enhancer | video/image planning | LLM/local | request/tokens | 0-20 Xu | ON/free or low |
| Viết kịch bản bán hàng | video | LLM/local | request/tokens | 30 Xu | ON/planning |
| Storyboard nhiều cảnh | video | LLM/local | request/tokens | 30-70 Xu | ON/planning |
| Tạo voice/TTS | video/audio | TTS provider | chars/min | NEED_COST | guarded |
| Thêm nhạc nền library | video | local/library | file | 0 Xu | if assets ready |
| SFX library | video | local/library | item | 10 Xu/item | if assets ready |
| Tạo nhạc AI | video/audio | music provider | 30s | 300 Xu config | KEEP_OFF until smoke |
| Tạo phụ đề | video | ASR | minute | 20 Xu/min config | guarded until smoke |
| Dịch phụ đề | video | ASR + translation | minute | 40 Xu/min config | guarded until smoke |
| Lồng tiếng | video | ASR + TTS + mux | minute | 100 Xu/min config | guarded until smoke |
| Phụ đề + lồng tiếng | video | full pipeline | minute | 120-150 Xu/min config | guarded until smoke |
| Burn subtitle | video | Local Worker/FFmpeg | render | NEED_COST/low | requires worker |
| Mux audio | video | Local Worker/FFmpeg | render | NEED_COST/low | requires worker |
| Lưu media | all | storage | MB/month | 10k/50MB | ON if PayOS/storage bridge ready |
| Nâng chất lượng ảnh | image | AI provider/local | job | NEED_COST | guarded |
| Chỉnh sửa ảnh AI | image | image edit provider | job | 350 Xu legacy/NEED_COST | guarded |
| Dùng ảnh đã chỉnh làm video | image-to-video | video provider | job | video tier price | guarded by video gate |

## Subtitle / Dub Pricing Per Minute

| Mode | 0-1 phút | 1-3 phút | 3-5 phút | 5+ phút | Provider | Public |
| ---- | -------: | -------: | -------: | ------: | -------- | ------ |
| Tạo phụ đề | 20 Xu min | 20 Xu/phút | 20 Xu/phút | NEED_COST | ASR | guarded |
| Dịch phụ đề | 40 Xu min | 40 Xu/phút | 40 Xu/phút | NEED_COST | ASR + translation | guarded |
| Lồng tiếng | 100 Xu min | 100 Xu/phút | 100 Xu/phút | NEED_COST | ASR + TTS | guarded |
| Phụ đề + lồng tiếng | 120 Xu min | 120 Xu/phút | 120 Xu/phút | NEED_COST | ASR + TTS + worker | guarded |
| Dịch phụ đề + lồng tiếng | 150 Xu min | 150 Xu/phút | 150 Xu/phút | NEED_COST | full pipeline | guarded |
| Burn subtitle vào video | NEED_COST | NEED_COST | NEED_COST | NEED_COST | Local Worker/FFmpeg | guarded |
| Xuất video hoàn chỉnh | NEED_COST | NEED_COST | NEED_COST | NEED_COST | Local Worker/FFmpeg/provider | guarded |

Required before public open:

- ASR smoke PASS.
- Translation smoke PASS.
- TTS smoke PASS.
- Mux/burn-in worker smoke PASS.
- Cost by minute confirmed.

## Image Pricing

| Image tool | Cost basis | Current price | Recommended price | Note |
| ---------- | ---------- | ------------: | ----------------: | ---- |
| Tạo ảnh AI tiết kiệm | provider image job | 50 Xu | 50 Xu | Starter/test; no warranty |
| Tạo ảnh AI tiêu chuẩn | provider image job | 200 Xu | 200-300 Xu | Current config provider cost 150 Xu makes 200 tight |
| Tiêu chuẩn + bảo hành | job + 1 retry risk | 300 Xu | 250-300 Xu | Owner previously wanted 250; cost needs invoice before lowering |
| Chất lượng cao | provider image job | 400 Xu | 400 Xu | Needs model/ratio cost |
| Cao + bảo hành | job + 1 retry risk | 600 Xu | 500-600 Xu | Owner previously wanted 500; cost needs invoice before lowering |
| Chỉnh sửa ảnh AI | edit provider job | 350 Xu legacy | NEED_COST | Public guarded until real output smoke |
| Nâng chất lượng AI | provider/local | missing | NEED_COST | Guarded |
| Xóa vật thể/đổi nền/màu | edit provider | missing | NEED_COST | Guarded |
| Crop/resize/thêm chữ/logo local | local CPU | 0 | 0-10 Xu | Low-risk utility |

## Chat AI / Bot AI Pricing

| Tool | Cost unit | Current price | Recommended price | Note |
| ---- | --------- | ------------: | ----------------: | ---- |
| Chat text normal | request/tokens | 5 Xu | 5-10 Xu | Need token cost logging |
| Chat pro | request/tokens | 10 Xu | 10-20 Xu | Depends model |
| Chat deep | request/tokens | 20 Xu base | 20-50 Xu | Cap and per-MB already configured |
| Chat image understanding | image request | missing | 20-80 Xu | Keep guarded until vision smoke/cost |
| TOAN AAS support AI | support/sales | 0 | 0-5 Xu | Should answer first, ticket second |
| Prompt helper/vault search | local/KB | 0 | 0 | Free to upsell paid products |

## Prompt Vault Strategy

Created draft files:

- `docs/knowledge/TOAN_AAS_PROMPT_VAULT_SCHEMA.md`
- `data/prompt_vault/prompts.json`

The vault includes starter prompts for:

- video sales
- video cinematic
- video affiliate
- product review/UGC
- image ads
- image product
- caption/hashtag
- livestream
- translation/dub
- support pricing explanation

Runtime loading is intentionally not enabled in this task. A separate implementation should add:

- indexing/search
- language filtering
- user state/back-routing
- safety filtering
- admin update path

## NEED_COST Items

- Real ShopAIKey per-video cost by tier/model/duration.
- Real ShopAIKey image cost by model/ratio and retry.
- OpenAI/Gemini/ShopAIKey image edit actual cost.
- Key4U backup provider cost.
- Deepgram/ASR minute cost.
- TTS per character/minute cost for ShopAIKey/Fish/ElevenLabs.
- Full subtitle+dub pipeline cost per minute.
- Music AI provider cost.
- Long video / multi-scene cost.
- App assistant LLM cost.

## KEEP_OFF Items

- Video 1000/1500 Kling/Seedance/premium future.
- Long render/video nhiều tập until provider + queue + load test pass.
- Video-to-video until smoke/cost pass.
- AI music public until provider smoke/cost pass.
- Full dub/burn-in output if ASR/TTS/worker smoke has not passed.
- OCR if provider cost is unknown.

## Proposed Sales Flow

Recommended video sales flow:

1. User enters need/product/platform.
2. Bot/app gives free prompt/storyboard suggestions.
3. Bot/app asks goal:
   - test thử
   - tạo tiếp cơ bản
   - bán hàng
   - quảng cáo tốt hơn
   - cao cấp
4. Bot/app recommends tier:
   - test thử -> 200 Xu
   - tạo tiếp cơ bản -> 300 Xu
   - bán hàng thường -> 400/500 Xu
   - bán hàng chính -> 600 Xu
   - cần đẹp hơn -> 800 Xu
   - premium/Kling/Seedance -> coming soon
5. Bot/app suggests add-ons:
   - voice
   - subtitle
   - dub
   - music/SFX
6. Bot/app shows mini invoice:
   - video tier
   - add-ons
   - total Xu
   - equivalent VND
7. User confirms.
8. System creates job and status path.

## Admin Read-Only Commands Proposed

These commands should be read-only if implemented later:

- `/pricing_status`
- `/product_cost_report`
- `/video_pricing_status`
- `/addon_pricing_status`
- `/prompt_vault_status`

No runtime implementation was added in this task.

## Decisions

- 200 remains experience package and marketing starter.
- 300 remains same base model line as 200 and is the first upsell.
- 400/500/600/800 become the quality ladder.
- 1000/1500 stay coming soon.
- Provider-cost and usage logging must improve before calling any tier “profit-safe”.

## Not Changed

- Runtime prices: not changed by this task.
- PayOS: not touched.
- `/naptien`: not touched.
- webhook: not touched.
- trial 200 Xu: not touched.
- wallet/package/combo/monthly plan: not touched.
- provider execution paths: not touched.
- DB destructive behavior: not touched.
