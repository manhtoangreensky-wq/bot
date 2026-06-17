# TOAN AAS Friendly User Message Audit

Date: 2026-06-20

## Principle

User-facing errors should explain what happens next without exposing provider internals.

## Provider Messages

- Public users see maintenance/busy/not-ready style messages.
- Admin sees model, status, HTTP code, safe error class, and short sanitized message.
- API keys, full prompts, full responses, and long output URLs are not shown.

## Key4U Status

- Missing docs: `NEED_DOCS`.
- Missing usage endpoint: `NEED_ENDPOINT`.
- Missing model: safe config message.
- Provider error: sanitized error class.

## Not Changed

No payment/top-up wording was changed by this Key4U pass.
