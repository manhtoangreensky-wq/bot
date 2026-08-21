# Ads Control Plane & Autonomy Levels (L0..L5)

## Autonomy Levels
- **L0**: No Ads.
- **L1**: Read-only Analytics & Recommendations.
- **L2**: Generate Ad Plan & Draft.
- **L3 (Default)**: Create paused external ad resources with Owner consent.
- **L4**: Owner explicitly authorizes spend per campaign.
- **L5**: Autonomous budget optimization within Owner Budget Envelope.

## Agent Security Boundary
- AI agents cannot make raw API calls with provider tokens.
- All requests flow through policy validation, budget checks, and audit logging.
