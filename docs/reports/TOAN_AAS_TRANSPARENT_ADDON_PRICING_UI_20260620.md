# TOAN AAS Transparent Add-on Pricing UI

Date: 2026-06-20

## Goal

Make video/image pricing transparent before final confirmation. A base package has its own price. Only items displayed with `+` add extra Xu. Built-in libraries and basic local/manual actions remain free within technical limits.

## Video Base Rule

- Short Video AI base package: 1 scene / 8 seconds.
- Extra seconds and extra scenes are quoted before confirmation for eligible tiers.
- Requests over 60 seconds route to the long-video flow.
- Provider is called only after final confirmation.

## Public Video Tier Pricing

- 200 Xu: experience tier, no paid add-ons, 3/day, 10/week, 30/month.
- 300 Xu: basic paid tier, same base quality line as 200, paid add-ons start here.
- 400 Xu: standard public tier.
- 500 Xu: advanced public-controlled tier.
- 600 Xu: business/main revenue public-controlled tier.
- 800 Xu: high public-controlled tier.
- 1000 Xu: professional public-controlled tier.
- 1500 Xu: future premium/off.

## Add-on Pricing

Under 60 seconds:

- Auto subtitles: +120 Xu.
- Translate subtitles: +150 Xu.
- Translate + burn subtitles: +220 Xu.
- Dubbing default voice: +250 Xu.
- Translate + dubbing default voice: +350 Xu.
- Advanced voice: +100 Xu.
- Voice transform: +150 Xu.
- Premium preset voice: +200 Xu.
- Voice clone create: +600 Xu.
- Reuse voice clone: +100 Xu.
- Suno music: +300 Xu.
- Suno variation: +150 Xu.
- AI lyrics: +80 Xu.
- Cut/loop music: +50 Xu.
- AI SFX: +80 Xu.

Long media extra block after 60 seconds:

- Auto subtitles: +80 Xu / 60s block.
- Translate subtitles: +100 Xu / 60s block.
- Subtitle full pipeline: +150 Xu / 60s block.
- Dubbing: +200 Xu / 60s block.
- Translate + dubbing: +250 Xu / 60s block.

## Free Included Items

- Stock music library when available.
- Built-in prompt/script templates.
- Subtitle from existing script/text if no heavy provider call.
- Basic manual/local actions within technical limits.
- Save to media vault within storage quota.

## Admin Checks Added

- `/pricing_status`
- `/video_pricing_status`
- `/addon_pricing_status`
- `/image_pricing_status`
- `/pricing_preview`
- `/pricing_validate`
- `/video_quote_test`
- `/subtitle_quote_test`
- `/dub_quote_test`
- `/music_quote_test`
- `/video_kling_status`

## Not Touched

- PayOS.
- /naptien.
- Payment webhook.
- Wallet/Xu top-up logic.
- Trial bonus.
- Combo/package wallet.
