# TOAN AAS Video 200 Experience Tier Policy

Date: 2026-06-20

## Purpose

The 200 Xu video tier is a starter/experience product. It lets customers try the default TOAN AAS video creation flow, see a real result, then upgrade naturally to 300 Xu or higher for more videos, better quality, longer output or paid add-ons.

## 200 Xu Policy

- Tier: Video Trải Nghiệm.
- Price: 200 Xu.
- Role: marketing starter / experience trial.
- Limit: 3 videos/day, 10 videos/week, 30 videos/month per account.
- Add-ons: paid add-ons are hidden and blocked.
- Extra duration/scenes: not sold on this tier.
- Provider/API: called only after final confirmation.
- Billing: Xu is deducted only after final confirmation.

## Included Free Assets

- Built-in prompt/script templates.
- Built-in/free asset libraries when available.
- Default package resources.
- Basic local/manual actions when technically eligible.

## Locked Paid Add-ons

The 200 Xu tier does not include:

- Paid extra duration or extra scenes.
- New AI music generation.
- Paid AI voice.
- Auto subtitle generation.
- Subtitle translation.
- Dubbing.
- Subtitle + dubbing.
- Quality/model upgrade.

If a stale callback tries to select a paid add-on on the 200 Xu tier, the bot blocks it before provider call and before Xu deduction, then upsells to 300 Xu or higher.

## Upsell Path

- 300 Xu: same base quality line as 200, but paid add-ons start here.
- 400/500/600/800: higher-quality ladder.
- 1000 Xu: professional public-controlled tier when provider/job gate is ready.
- 1500 Xu: future premium, still off.

## Manual Test Result

Planned verification:

- Select 200: paid add-ons hidden.
- Force old add-on callback on 200: blocked with upsell, no provider call, no Xu.
- 200 invoice: total remains 200 Xu.
- Select 300+: add-on pricing remains visible and itemized.
- 200 limit: 3/day, 10/week, 30/month.

## Not Touched

- PayOS.
- /naptien.
- Payment webhook.
- Trial bonus.
- Combo/package wallet.
- Provider execution core.
- Image edit flow.
