# TOAN AAS Omnichannel Marketing Automation Architecture

```
CONTENT STRATEGY
      │
      ▼
CONTENT PLAN / CALENDAR
      │
      ├── Brand Profile Engine
      ├── Affiliate Matcher V2
      ├── Claims / Compliance Guard
      └── Platform Formatter
             │
             ▼
       PUBLISH PACKAGE
             │
    ┌────────┼─────────┬───────────┬──────────┐
 Telegram  Facebook  Instagram   YouTube    TikTok
    │         │          │           │          │
    └─────────┴──────────┴───────────┴──────────┘
                         │
                    PUBLISHED
                         │
                    METRICS LOOP
                         │
                  ADS ELIGIBILITY
                         │
                 ADS CONTROL PLANE
                  /       |                     Meta     TikTok    Google Ads
                         │
                 Owner Policy Gate
                         │
                  Optimize / Pause
```

## Core Invariants
1. **Single-Agent by Default**: Monolithic lifecycle governance without subagent sprawl.
2. **Fail-Closed Gateways**: Unknown affiliate ad policies block ad creation (`ADS_ELIGIBLE=NO`).
3. **Idempotency**: Deterministic keys prevent duplicate publishing during network retry or service restart.
