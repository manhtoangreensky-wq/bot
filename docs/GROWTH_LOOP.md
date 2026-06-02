# GROWTH LOOP

## Purpose

Convert manual performance metrics into simple actions for one-person affiliate operations.

## Command

```text
/growth_loop
/growth_loop days=30 platform=tiktok
/growth_ai
```

For admin, the existing operator growth loop remains the default. To force the manual post loop as admin:

```text
/growth_loop manual=1
```

## Rule-Based Recommendations

`/growth_loop` uses deterministic rules:

- `SCALE`: revenue and clicks exist.
- `FIX CTA`: views are good but clicks are weak.
- `FIX HOOK`: views are too low.
- `ADD OFFER`: engagement exists but revenue is missing.
- `PAUSE OR REWRITE`: not enough signal to scale.

## AI Growth Coach

`/growth_ai` is the paid deep-analysis layer.

- Cost: 30 Xu for normal users.
- Admin/VIP: free under current bot logic.
- Data source: the same manual publish/performance tables.
- Output: hook/caption/CTA variants, scale/fix/pause list, 7-day plan.
- Refund: yes if AI fails after charging.

## Stored Data

Table: `growth_recommendations`

- `published_post_id`
- `campaign_id`
- `recommendation_type`
- `score`
- `title`
- `reason`
- `action`
- `status`

## Boundaries

- No automatic posting.
- No automatic ad spend.
- No external API execution.
- Recommendations are decision support only.
- `/growth_ai` calls only existing Gemini/OpenAI text providers.
