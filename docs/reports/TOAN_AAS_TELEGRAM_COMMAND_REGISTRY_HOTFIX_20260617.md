# TOAN AAS Telegram Command Registry Hotfix - 2026-06-17

## Scope

P0 hotfix for Telegram command registration and live admin command visibility.

This change adds real `CommandHandler` registration for commands that were already expected by admin workflows but were missing on live Telegram.

## Commands Added

Video tier/status:
- `/video_tier_matrix`
- `/video_test_tier_200`
- `/video_test_tier_300`
- `/video_test_tier_400`
- `/video_test_tier_500`
- `/video_test_tier_600`
- `/video_test_tier_800`
- `/video_test_tier_1000`
- `/video_test_tier_1200`
- `/video_test_tier_1500`
- `/video_test_all_tiers`

Video job diagnostics:
- `/video_recent_jobs`
- `/video_failed_jobs`
- `/video_error_report`

Safe system checks:
- `/test_all_safe`
- `/test_all_video`
- `/test_all_provider`
- `/test_all_system`

## Behavior

- All new commands are admin-only.
- Tier test commands are safe dry-runs: no provider call, no Xu deduction, no PayOS/payment changes.
- Recent/failed job commands show sanitized job IDs and short provider messages only.
- 1000/1200/1500 tiers are included in video billing/public gate status instead of being silently excluded by the allowlist gate.
- High tiers use `PUBLIC_WITH_PROVIDER_GUARD` when public tier config is open but provider execution is not ready, instead of vague `GUARDED`/coming-soon wording.

## Registry Updates

- `/providers` now advertises the new command registry and tier-safe-test commands.
- `docs/COMMAND_REGISTRY.md` includes the new commands and handlers.
- Tests verify command handler registration and documentation entries.

## Not Touched

- PayOS
- `/naptien`
- PayOS webhook
- Wallet/Xu balance logic
- Combo/package/monthly purchase logic
- Trial bonus
- ShopAIKey provider call behavior
- Key4U provider call behavior
- Public video execution/provider submit path
- Database destructive migration

## Live Test Checklist

After deploy, admin should test:

1. `/runtime`
2. `/data_status`
3. `/providers`
4. `/video_tier_matrix`
5. `/video_test_tier_200`
6. `/video_test_tier_300`
7. `/video_test_tier_400`
8. `/video_test_tier_500`
9. `/video_test_tier_600`
10. `/video_test_tier_800`
11. `/video_test_tier_1000`
12. `/video_test_tier_1200`
13. `/video_test_tier_1500`
14. `/video_test_all_tiers`
15. `/video_recent_jobs`
16. `/video_failed_jobs`
17. `/video_error_report`
18. `/test_all_safe`
19. `/test_all_video`
20. `/test_all_provider`
21. `/test_all_system`

