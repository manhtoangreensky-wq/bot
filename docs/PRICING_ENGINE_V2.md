# TOAN AAS Pricing Engine V2

Date: 2026-06-02

## Strategy

Default prices must be high enough to pay for:

- API cost.
- Server cost.
- Processing retries.
- Refund/error buffer.
- Customer support.
- Product development.
- Profit.

## Formula

```text
Retail price = internal cost x 3
```

`PRICING_MARKUP_MULTIPLIER = 3`

## Default prices

| Feature | Price |
|---|---:|
| `/film` Basic | 200 Xu |
| `/film tier=pro` | 500 Xu |
| `/film tier=series` | 1,200 Xu |
| `/growth_ai` | 120 Xu |
| `/campaign_report` | 50 Xu |
| Chat short | from 5 Xu |
| Chat long/heavy | 15-30 Xu |
| Voice/TTS | from 50 Xu + length |
| Audio/STT | from 80 Xu |
| Background removal | 80-150 Xu |
| Downloader/video processing | from 100 Xu |

## MB-based pricing

| Feature | Base | Per MB | Minimum |
|---|---:|---:|---:|
| Audio/STT | 30 Xu | 20 Xu | 80 Xu |
| Downloader/video | 50 Xu | 15 Xu | 100 Xu |

## Film pricing

| Film input | Price |
|---|---:|
| Basic, 1 episode, 5 scenes | 200 Xu |
| `episodes=3 scenes=5` | 400 Xu |
| `episodes=1 scenes=10` | 300 Xu |
| `tier=pro` | 500 Xu |
| `tier=series` | 1,200 Xu |

## Promotion strategy

- Do not lower the base price table.
- Use discount percentages.
- Use bonus Xu.
- Use beta discounts.
- Do not sell below cost.

## Beta note

During beta, admin can run a promotion, but the public price table should stay high so customers understand the normal value.
