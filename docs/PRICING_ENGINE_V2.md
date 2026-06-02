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
| Normal chat | fair-use / existing normal chat flow |
| `/chat_pro` Pro | from 20 Xu |
| `/chat_pro tier=deep` | from 50 Xu |
| Long Chat Pro content | +20 Xu / content unit, capped at 200 Xu |
| Voice/TTS | from 50 Xu + length |
| Audio/STT | from 80 Xu |
| Background removal | 80-150 Xu |
| Downloader/video processing | from 100 Xu |

## MB-based pricing

| Feature | Base | Per MB | Minimum |
|---|---:|---:|---:|
| Audio/STT | 30 Xu | 20 Xu | 80 Xu |
| Downloader/video | 50 Xu | 15 Xu | 100 Xu |

## Chat Pro pricing

| Input | Price |
|---|---:|
| Short Pro request | 20 Xu |
| Short Deep/high-model request | 50 Xu |
| Each extra content unit | +20 Xu |
| Maximum per request | 200 Xu |

## Film pricing

| Film input | Price |
|---|---:|
| Basic, 1 episode, 5 scenes | 200 Xu |
| `episodes=3 scenes=5` | 400 Xu |
| `episodes=1 scenes=10` | 300 Xu |
| `tier=pro` | 500 Xu |
| `tier=series` | 1,200 Xu |

## Trial Strategy

New user trial = 200 Xu.

Reason:

- `/film` Basic = 200 Xu.
- User mới cần đủ Xu để trải nghiệm tính năng video cốt lõi.
- Sau khi thấy giá trị, user được hướng dẫn `/naptien` để nạp thêm.
- Áp dụng cho user mới sau deploy; user cũ không tự động được bù nếu chưa có migration riêng.

## Top-up packages

| Package | Base Xu | Launch Bonus | First purchase total | Repeat purchase total |
|---|---:|---:|---:|---:|
| 10k | 100 | 0 | 100 | 100 |
| 20k | 200 | 0 | 200 | 200 |
| 100k | 1,000 | +50 | 1,050 | 1,000 |
| 200k | 2,000 | +150 | 2,150 | 2,000 |
| 500k | 5,000 | +500 | 5,500 | 5,000 |

## Promotion strategy

- Do not lower the base price table.
- Use discount percentages.
- Use bonus Xu.
- Use beta discounts.
- Do not sell below cost.
- One order can use only one promo code.
- Launch Bonus is separate from promo code and can coexist with one eligible promo.

Example: 500k first purchase with FIRST30:

- Base Xu: 5,000
- Launch Bonus first 500k package: +500
- FIRST30: +30% Xu
- Current customer-facing total: 7,000 Xu

Actual eligibility depends on promo code status and whether the user has already used Launch Bonus for that package.

## Beta note

During beta, admin can run a promotion, but the public price table should stay high so customers understand the normal value.
