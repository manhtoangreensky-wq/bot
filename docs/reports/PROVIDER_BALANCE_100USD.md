# Provider balance notifications — source/test handoff

Fixed reference is 100 USD credit per provider. Notify strictly below 10 USD using unrounded Decimal values. Invalid, stale or missing balance is UNKNOWN, not zero.

Official read-only endpoints are Key4U /v1/balance (Bearer) and ShopAIKey /usage (apiKey query). The new reader returns sanitized balance only, disables redirects and redacts the ShopAIKey query credential in HTTPX INFO logs.

Existing monitor now includes Key4U and sends ShopAIKey alerts through the same notification policy. Producer freeze/billing functions are unchanged. Notification snapshots use separate system_settings keys. ShopAIKey retains the legacy usage request for its existing safeguards plus one notification read; do not remove the legacy path without a separate protected change.

Delivery writes PENDING before sending and SENT only after message_id. Unknown send/receipt persistence failures remain pending for reconciliation, never blind resend. Same-process asyncio locks serialize per-provider ticks. This is single bot-process protection, not a distributed lease. Default reminder is six hours; verified recovery above threshold rearms notification.

## Verification

- 51 focused policy/reader/notification/actual-source integration tests passed.
- 23 existing quota regression tests passed after correcting a scope guard that confused unchanged diff context with payment edits.
- py_compile bot.py and new modules passed; git diff --check passed.
- AST protected comparison uses immutable base 0ec38f1587fbe4f2126bf6975345de63f3da9130, not moving HEAD.
- Only notification entry, monitor and startup functions changed; unrelated producers unchanged.

## Pending acceptance

Not deployed; no real Telegram notification sent. Successful manual read-only provider probes do not establish deployed notification success. Ambiguous delivery has no automatic reconciliation UI yet. Do not claim whole-goal completion.
