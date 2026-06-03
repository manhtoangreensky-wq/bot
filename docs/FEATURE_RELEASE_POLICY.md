# Feature Release Policy

TOAN AAS uses an admin-first release gate for every new, risky or API-cost feature.

## Release Stages

- `PLANNED`: planned only, not usable by customers.
- `ADMIN_ONLY`: admin/owner can test; not public.
- `BETA_PRIVATE`: limited private users approved by admin.
- `PUBLIC_READY`: opened to customers after tests, pricing and safety checks.
- `DISABLED`: turned off because provider, cost, quota or policy risk is not ready.

## Default Rule

New features must not default to public. The default is `ADMIN_ONLY` or `DISABLED`.

This applies to:

- AI image generation.
- AI image editing.
- Real video generation.
- Trend live/realtime search.
- Downloader providers.
- RemoveBG/Cutout provider changes.
- Auto publish.
- Customer publish.
- Ads assistant.
- Any payment/provider flow with money or credits.

## Feature Flags

Current default flags:

- `ENABLE_OPENAI_IMAGE=0`
- `ENABLE_OPENAI_IMAGE_EDIT=0`
- `ENABLE_REAL_VIDEO=0`
- `ENABLE_TREND_LIVE=0`
- `ENABLE_DOWNLOADER_PUBLIC=0`
- `ENABLE_REMOVE_BG_PUBLIC=0`
- `ENABLE_AUTO_PUBLISH=0`
- `ENABLE_CUSTOMER_PUBLISH=0`
- `ENABLE_ADS_ASSISTANT=0`
- `ADMIN_TEST_OPENAI_IMAGE=1`
- `ADMIN_TEST_OPENAI_IMAGE_EDIT=1`
- `ADMIN_TEST_REAL_VIDEO=0`
- `ADMIN_TEST_TREND_LIVE=0`

## Public Opening Checklist

Before setting any feature to `PUBLIC_READY`:

1. Admin smoke test passes at least three times.
2. Provider cost and quota are understood.
3. Customer price in Xu is defined.
4. No-charge/refund behavior on provider failure is implemented.
5. Rate limit and file limits are defined where relevant.
6. `/providers`, `/tool_status` and `/sales_ready` show correct status.
7. Customer instructions are present.
8. Admin explicitly approves opening the feature.

## Commands

- `/feature_status`: show current release stage/config/test/public state.
- `/feature_set FEATURE STATUS`: owner-only, records a release stage override.

Changing a stage does not create API keys, does not enable missing env vars and does not bypass smoke testing.

## Current Customer Rule

Customers can use prompt/content tools that are stable. Expensive or risky provider tools stay admin-first until proven safe.
