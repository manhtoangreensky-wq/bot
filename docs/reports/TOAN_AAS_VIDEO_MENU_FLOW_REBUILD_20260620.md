# TOAN AAS Video Menu Flow Rebuild - 2026-06-20

## Scope

Rebuilt the video add-on/pricing confirmation path around a shared `video_order` object so screens update one order instead of recalculating price independently.

## Done

- Added `video_order` builder with tier, base price, free items, paid add-ons, total Xu, VND estimate and screen stack.
- Moved video AI invoice text to read from `video_order`.
- Prevented invalid member discount from reducing a paid video invoice to `0 Xu`.
- Kept 200 Xu as the starter tier and locked all paid add-ons for it.
- Kept 300 Xu and higher eligible for paid add-ons.
- Marked 1000/1500 future tiers as not billable in the order builder.
- Updated add-on/back stack so voice/language screens return to the add-on menu before returning to tier selection.
- Reworded customer-facing video add-on screens to avoid raw `provider` / `API` language.
- Added tests for order totals, 200 add-on lock, 300 add-ons, invoice copy, stack behavior and coming-soon tiers.

## Not touched

- PayOS
- `/naptien`
- Payment webhook
- Paid top-up logic
- Wallet/Xu balance reset
- Combo/package purchase logic
- Local Worker render implementation
- ShopAIKey provider submit/query implementation

