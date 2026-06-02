# COST CONTROL - TOAN AAS

Date: 2026-06-02

## Principles

- A feature that calls a paid provider must charge Xu or be clearly limited by trial/free quota.
- If a paid feature fails after Xu was charged, the bot must refund.
- Admin/VIP bypass should not create refund records because no Xu is charged.
- Provider failures should alert admin without logging API keys.
- Before public launch, admin should test each provider with a low-risk account.

## Current paid/external providers

| Provider | Feature | User cost in Xu | Refund on fail? | Risk |
|---|---|---:|---:|---|
| Gemini/OpenAI | Chat AI, `/film`, `/growth_ai` | Dynamic, `/film` 200+, `/growth_ai` 120 | YES for paid command failures | Token/quota cost. |
| Deepgram | STT/audio transcription | Dynamic per existing code | YES where charged flow supports refund | Audio length/quota. |
| Fish Audio | HD TTS | Provider choice per existing code | YES where charged flow supports refund/fallback | Character/voice cost. |
| RemoveBG/Cutout | Background removal | Provider choice per existing code | YES where charged flow supports refund/fallback | Image/quota cost. |
| Cobalt/RapidAPI | Downloader | Dynamic per existing code | YES where charged flow supports refund | Public endpoint instability/API quota. |
| PayOS | Billing/checkout | No user Xu cost | N/A | Signature/channel mismatch and real payment test required. |

## Current configured limits

| Item | Value |
|---|---:|
| Trial credits | 150 Xu |
| Free chat daily | 20 messages/day |
| `/film` | 200 Xu basic; 500 Xu pro; 1,200 Xu series |
| `/growth_ai` | 120 Xu |
| `/campaign_report` | 50 Xu |
| `/chat_pro` | from 20 Xu; deep from 50 Xu; cap 200 Xu |
| Audio/STT | from 80 Xu, MB-based |
| Downloader/video | from 100 Xu, MB-based |
| Popular upsell packages | 50k / 100k / 200k |

## Before public launch

1. Run `/providers` and resolve missing critical providers.
2. Run `/sales_ready`.
3. Run `/payos_test_plan` and complete one real 10k PayOS payment.
4. Test insufficient-Xu upsell.
5. Test refund paths for Chat Pro, AI, STT, TTS, image, and downloader errors.
6. Run `/dashboard` and verify revenue/usage counters.
7. Keep `auto_publish` disabled.

## Cost review cadence

- Daily during beta: inspect `/dashboard`, `/costs`, and provider dashboards.
- Weekly: compare Xu revenue against provider spend.
- Before enabling a new paid provider: define user Xu cost, free/trial limit, and refund behavior.
