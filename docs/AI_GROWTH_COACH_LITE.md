# AI Growth Coach Lite

## Purpose

Use admin/internal manual data from `/publish_done` and `/performance_add` so AI can suggest what to scale, fix, pause, and remix.

Normal customers do not use publish tracking in the current bot. They receive content packs through `/film`, self-post manually, and can request `/growth_ai` when enough data is supplied manually.

## Command

```text
/growth_ai
/growth_ai days=30
/growth_ai platform=tiktok
/growth_ai campaign_id=1 goal="tăng affiliate"
```

## Pricing

- Pricing Engine V2: 120 Xu per AI analysis.
- Admin/VIP: free under current bot logic.
- No charge when there is no performance data.
- Refund if AI fails after credits were charged.

## Output

- Tổng quan.
- Bài nên scale.
- Bài nên fix.
- Bài nên pause.
- Kế hoạch 7 ngày tới.
- Cảnh báo an toàn.

## Data Source

- `published_posts`
- `manual_performance_events`
- `campaigns`
- `affiliate_links`

## Safety

- No auto publish.
- No Facebook/TikTok/YouTube API calls.
- No browser automation.
- No guaranteed revenue claims.
- No spam recommendations.
- Affiliate disclosure is required.
