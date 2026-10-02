# Provider balance notifications — N4.35 handoff

`BASE_SHA=51e8c172f9a73e24ecb0e32418bdc48d25887f39`

## Contract

- Fixed reference: `100 USD credit = 100%`; notify only when a fresh, provider-verified balance is strictly `< 10 USD`. Exactly `10.00 USD` is not low.
- Key4U uses the official read-only `/v1/balance` endpoint with Bearer auth. ShopAIKey uses the official read-only `/usage` endpoint with its existing query-key contract.
- Missing credentials, bad schema, HTTP/transport errors, naive/stale/future timestamps, and invalid amounts are `UNKNOWN`; never coerce them to zero or alert on them.
- Disable redirects; keep credentials and raw response bodies out of returned values, user messages, and provider logs.
- Persist `PENDING` before Telegram send and `SENT` only after a valid message receipt. Ambiguous outcomes remain pending for manual reconciliation; do not blindly retry. Recovery above threshold rearms the next alert. Reminder cadence is six hours.
- Notification only: no automatic provider freeze, billing, wallet, or customer-message changes. Key4U polling honors the existing alert switch and credentials. ShopAIKey preserves its existing usage monitor/safety read and performs one separate fixed-balance notification read per monitor tick.

## Verification on the latest-main integration

- Current main advanced by SubDub PR #1285 while this branch was being verified. It was merged as an upstream parent only; the PR diff against latest main still contains no SubDub/Product Video/Voice/Music paths.
- Focused policy, notification, reader, actual monitor/startup seam, and protected quota regression command: `75 passed, 294 warnings in 11.10s` on the latest-main integration. HTTP was mocked with `httpx.MockTransport`, Telegram sends were `AsyncMock` only.
- Focused `py_compile` for the three service modules and five related test modules: exit `0` (8 files). Full `bot.py` compile is delegated to the required source-compile CI because the local 15 MB compile exceeded the bounded CPU window.
- `git diff --check HEAD`: exit `0`.
- Updated-PR source-compile and quality CI are required before merge.
- `PROVIDER_CALLS=0; TELEGRAM_SENDS=0; WALLET_MUTATIONS=0; PROD_DB_WRITES=0; DEPLOY=NO; RESTART=NO; RUNTIME_SHA=NOT_VERIFIED; LIVE_PASS=NOT_TESTED`.

## Remaining gates

- Require both updated-PR quality/tests and source-compile checks to succeed on the refreshed main-based branch.
- After merge, replay the focused suite on the merge SHA and check deployment records. Merge is not deploy or live verification; no real provider probe or Telegram notification is authorized by this test run.
