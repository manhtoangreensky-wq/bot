# UIFLOW3 Video UI Restore Design

Date: 2026-08-11
Status: Owner approved

## Scope

Restore and finish the existing Product Video UI without rebuilding it from scratch. Video AI Real is the reference implementation. Product-specific intake remains distinct; only interaction rules and the commercial tail are shared selectively.

Protected surfaces:

- Do not change Video Edit.
- Do not change or re-route Frame Images to Video.
- Do not send Telegram commands, callbacks, media, or provider requests.
- Do not deploy, mutate ENV/credentials, wallets, or payment state.

## Canonical Interaction Rules

1. A single-choice button advances immediately to the next logical screen.
2. Multi-choice screens keep check marks and expose one complete Vietnamese `Hoàn tất ...` action.
3. Ordinary keyboards use at most two buttons per row.
4. A five-item suggestion page is the deliberate exception: row one is exactly `1 2 3 4 5`; row two is `Đổi 5 gợi ý` and `Tự nhập nội dung`; row three is exact Back and Menu Video.
5. Suggestions are profile-specific, display full guidance, and a selected suggestion is compiled into the complete prompt before advancing.
6. The full current prompt is visible and directly editable. It is never shortened or replaced with a summary.
7. Logo image and watermark text each require the full nine-position chooser. The selected position is visible in Branding, Review, Invoice, and Status.
8. Quality is a separate screen after final review/branding and before invoice.
9. Public quality copy contains only Vietnamese customer-facing names, icons, seconds, image capability, use case, Xu per scene, and total Xu. Provider, adapter, and model names remain internal.
10. Final confirm creates exactly one real job. A real `job_id` opens the canonical status panel; no job opens a terminal `FAIL - Chua tao duoc tac vu` panel with the retained invoice and zero charge. No fake progress is allowed.
11. Back and stale callbacks stay within the exact opened product. Missing ownership returns Menu Video and never defaults to Video AI Real.

## Product Structure

- Video AI Real keeps `Prompt -> Video` and `Image -> Video` as the first product choice.
- `32 loai noi dung` and `Y tuong video` remain peer choices.
- Each other video product retains its own intake, required assets, prompts, and scene rules.
- Shared tail: prompt review, optional audio/add-ons, logo/watermark, quality, invoice, confirm, real status.
- Trend Video follows its own trend catalog and later uses the same commercial tail.

## Internal Quality Catalog

The public list is ordered from lower to higher cost and capability. Equivalent providers are grouped internally, with the cheapest verified route first and the highest verified equivalent cost used as the sale baseline. Sale price is baseline cost times three, rounded to tens using Owner's remainder rule.

Verified sources on 2026-08-11:

- ShopAIKey model catalog: Grok video at USD 0.400 per generation, Veo 3.1 Fast at USD 0.700, Veo 3.1 Pro at USD 3.500; displayed conversion 1 USD = 3,250 VND.
- Key4U model catalog: PixVerse USD 0.041, Grok Imagine Video USD 0.060, Veo 3.1 Fast USD 0.576, Veo 3.1 USD 0.768, Kling variants with 3-15 second modes, Hailuo 2.3 USD 3.200, Vidu Q3 Mix USD 6.250, Seedance 1.0 Pro USD 22.500.

Models with incomplete duration or billing-unit evidence may be retained as internal fallback candidates but must not create a public duration claim until verified. Draft estimates are not canonical prices.

## Acceptance Contract

- Five suggestion buttons render on one row and selection auto-advances.
- No public Grok, Veo, Kling, provider, adapter, or model text appears in the quality flow.
- Trial wording and trial-only restrictions are removed from the lowest normal package.
- All nine public quality tiers have an icon and complete customer information.
- Branding shows and persists nine-position placement for both logo and watermark.
- No-job confirmation is visibly terminal FAIL, not processing.
- Product ownership defaults are removed; stale state returns Menu Video.
- Protected flows have no tracked edits.
