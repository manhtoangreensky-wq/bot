# PROVIDER SECURITY AUDIT - TOAN AAS

Date: 2026-06-02

## Compile

- `py_compile`: PASS before provider command implementation.
- `py_compile`: PASS after provider command implementation.

## Env keys detected in code

| ENV | Purpose | Exposed in response/log? | Risk |
|---|---|---:|---|
| `TELEGRAM_TOKEN` / `BOT_TOKEN` | Telegram bot runtime | NO raw token found in health/provider outputs | High if leaked; regenerate if screenshot/log exposed it. |
| `ADMIN_ID` | Admin command gate | Visible only as config concept | Low. |
| `PUBLIC_BASE_URL` | Public Railway URL | Public by design | Low. |
| `GEMINI_API_KEY` | AI provider | NO | Medium provider cost risk. |
| `OPENAI_API_KEY` | AI fallback | NO | Medium provider cost risk. |
| `DEEPGRAM_API_KEY` | STT | NO | Medium audio quota risk. |
| `FISH_AUDIO_KEY` | TTS | NO | Medium character/quota risk. |
| `REMOVEBG_API_KEY` | Image background removal | NO | Medium image quota risk. |
| `CUTOUT_API_KEY` | Image fallback | NO | Medium image quota risk. |
| `PAYOS_CLIENT_ID` | PayOS checkout | NO raw value in provider commands | High money-flow risk if mismatched. |
| `PAYOS_API_KEY` | PayOS checkout | NO | High money-flow risk if leaked. |
| `PAYOS_CHECKSUM_KEY` | PayOS signature/webhook | NO | Critical if leaked/mismatched. |
| `RAPIDAPI_KEY` | Downloader fallback | NO | Medium quota risk. |
| `RAPIDAPI_HOST` | Downloader fallback host | NO | Low. |
| `COBALT_API_URL` | Downloader endpoint | URL status only in `/providers`; public URL may appear in `/runtime` as disabled flag only | Low/medium availability risk. |
| `COBALT_API_KEY` | Downloader auth | NO | Medium quota/auth risk. |
| `LEAD_WEBHOOK_SECRET` | Lead form protection | NO | Low/medium. |
| `OPERATOR_API_TOKEN` | Operator API bridge | NO raw token; examples use placeholder | High if leaked. |
| `AFFILIATE_POSTBACK_TOKEN` | Affiliate postback protection | NO raw token; examples use placeholder | Medium. |
| `TELEGRAM_WEBHOOK_SECRET` | Telegram webhook secret token | NO raw secret | Medium. |

## Public routes

| Route | Shows provider status? | Shows secret? | Notes |
|---|---:|---:|---|
| `/` | NO | NO | Serves landing page. |
| `/landing` | NO | NO | Serves landing page. |
| `/health` | Boolean config only | NO | Uses provider booleans, no raw keys. |
| `/runtime` | Runtime/webhook diagnostics | NO raw keys | Public route shows public URL and webhook path, not token/checksum/API key. |
| `/webhook/payos` | NO | NO | Webhook verification path untouched in Step 8. |
| `/lead` | NO | NO | Header secret is compared, not printed. |

## Admin commands

| Command | Shows provider status? | Shows secret? | Notes |
|---|---:|---:|---|
| `/providers` | YES | NO | Admin-only, configured/missing only. |
| `/costs` | YES, high-level | NO | Admin-only cost risk view. |
| `/sales_ready` | YES, readiness only | NO | Admin-only, never auto-marks SALES READY. |
| `/payos_test_plan` | NO | NO | Admin-only checklist. |
| `/runtime` | Runtime diagnostics | NO raw keys | Admin-only Telegram command. |
| `/dashboard` | Revenue/user counters | NO | Admin-only. |

## Provider usage

| Provider | Used for | Fallback | Cost risk |
|---|---|---|---|
| Gemini | AI chat/script/growth | OpenAI or template path where implemented | Token/quota. |
| OpenAI | AI fallback | Existing non-AI/template errors if both missing | Token/quota. |
| Deepgram | STT | Clear missing-key error | Audio quota. |
| Fish Audio | HD TTS | Edge TTS fallback | Character/voice quota. |
| RemoveBG | Background removal | Cutout if configured | Image quota. |
| Cutout | Background removal fallback | Missing-provider error | Image quota. |
| Cobalt | Downloader | RapidAPI/manual fallback where implemented | Availability/quota. |
| RapidAPI | Downloader fallback | Manual error/fallback where implemented | Quota. |
| PayOS | Dynamic QR and webhook credit | Manual bill fallback | Signature/channel mismatch. |

## Current risks

1. PayOS must pass a real 10k payment test before public sale.
2. `/runtime` is public and diagnostic-heavy; it does not expose secrets, but should not be treated as a private admin report.
3. Public Cobalt default can be unstable; self-hosted `COBALT_API_URL` is recommended.
4. Provider quotas can create cost spikes if public demand grows before pricing/rate limits are reviewed.

## Required fixes

1. Complete `/payos_test_plan` with a real 10k payment.
2. Review provider dashboards after beta usage.
3. Keep all provider values in Railway ENV only.
4. Regenerate any key that was exposed through screenshots or logs.
