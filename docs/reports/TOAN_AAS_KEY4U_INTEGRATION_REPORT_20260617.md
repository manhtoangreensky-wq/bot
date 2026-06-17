# TOAN AAS Key4U Integration Report

Date: 2026-06-17

## Done

- Added Key4U provider adapter for admin smoke tests.
- Added central provider router metadata for ShopAIKey primary, Key4U backup,
  and WokuShop parked.
- Added admin-only Key4U smoke commands.
- Added Key4U to provider registry, `/providers`, and `/provider_matrix`.
- Added `.env.example` entries for Key4U, router, fallback, and Woku parked
  flags.
- Added tests for config masking, no-Xu smoke command contract, router order,
  Woku parked behavior, and Video 200 beta daily limit.

## Commands Added

- `/key4u_status`
- `/tool_test_key4u_chat`
- `/tool_test_key4u_vision`
- `/tool_test_key4u_image`
- `/tool_test_key4u_image_edit`
- `/tool_test_key4u_video`
- `/key4u_video_job`

## Public Access

Public Key4U access remains OFF:

- `KEY4U_PUBLIC_ENABLED=false`
- `PROVIDER_FALLBACK_ENABLED=false`

Admin smoke tests do not deduct Xu.

## WokuShop

WokuShop is intentionally parked:

- `WOKU_ENABLED=false`
- `WOKU_PUBLIC_ENABLED=false`
- `WOKU_ADMIN_SMOKE_ENABLED=false`
- `WOKU_REASON=cost_high_parked`

## Not Touched

- PayOS
- `/naptien`
- webhook
- paid top-up logic
- trial bonus logic
- wallet/package/combo logic
- public image/video billing core
- DB destructive migration paths

## Live Test Notes

1. Set `KEY4U_ENABLED=true` and `KEY4U_API_KEY`.
2. Set model ENV values for the specific smoke test.
3. Run `/key4u_status`.
4. Run one smoke command at a time.
5. Keep `KEY4U_PUBLIC_ENABLED=false` until smoke, cost, and fallback policy are
   explicitly approved.
