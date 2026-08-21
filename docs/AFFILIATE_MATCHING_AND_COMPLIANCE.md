# Affiliate Matching V2 & Paid-Ads Compliance Guard

## 1. Relevance Scoring Algorithm
- **Niche Match**: +40 points.
- **Topic Match**: +30 points.
- **Product Score**: +0..20 points.
- **Active Status**: +10 points.
- **Threshold**: Minimum score of 60. Sub-threshold returns `NO_AFFILIATE`.

## 2. Paid Ads Compliance Guard
- If `paid_ads_allowed == False` => Ads blocked.
- If `paid_ads_allowed == UNKNOWN` => **FAIL CLOSED** (`ADS_ELIGIBLE=NO`).
