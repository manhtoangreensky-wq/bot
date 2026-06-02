# Campaign Report Export

## Commands

```text
/campaign_report
/campaign_report days=30
/campaign_report platform=tiktok
/campaign_report campaign_id=1
/campaign_report format=csv
/export_report format=txt
```

## Output

- Summary.
- Platform breakdown.
- Top posts.
- Rule-based recommendations.
- Next actions.

## Formats

- `txt`: human-readable campaign report.
- `csv`: rows for spreadsheet analysis.

## Columns For CSV

```text
post_id,platform,topic,post_url,views,likes,comments,shares,clicks,revenue,score,published_at
```

## Pricing

- Pricing Engine V2: 50 Xu per report export for normal users.
- Admin/VIP: free under current bot logic.
- No charge when there is no performance data.
- Refund if file export fails after Xu was charged.

## Boundaries

- Owner-scoped data only.
- No empty report file if user has no data.
- No social API calls.
- No auto publish.
