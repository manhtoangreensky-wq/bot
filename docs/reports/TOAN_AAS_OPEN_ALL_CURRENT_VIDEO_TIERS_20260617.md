# TOAN AAS Open All Current Video Tiers 2026-06-17

## Scope

Open the current public Video AI short-video tiers:

- 200 Xu - Video Trai Nghiem
- 300 Xu - Video Co Ban
- 400 Xu - Video Pho Thong
- 500 Xu - Video Nang Cao
- 600 Xu - Video Ban Hang
- 800 Xu - Video Cao Cap
- 1000 Xu - Video Chuyen Nghiep

Keep future/high-risk products closed:

- 1500 Xu future premium tier
- long video
- multi episode
- Kling public
- Seedance public
- image-to-video
- video-to-video
- Key4U public video

## Root Cause

The 500/600/800/1000 tiers were present or needed in the UI, but `get_video_tier_status()` depended on `video_billing_public_gate().allowed_tiers`.
That gate built `allowed_tiers` from cost/margin checks, so a cost warning or unknown provider cost could make a visible tier look closed with a message like "billing/cost gate".

## Gate Change

The public video gate now separates:

- billing safety: confirm before deduct, refund policy, job lock, concurrency and duration caps
- cost review: admin reporting only

For current launch tiers 200/300/400/500/600/800/1000, cost warnings no longer block the customer confirmation path.

## Opened Tiers

- 200: public starter tier, keeps existing starter limits
- 300: public
- 400: public
- 500: public
- 600: public
- 800: public
- 1000: public

## Still Closed

- 1500: coming soon, no confirm, no provider call
- long video and multi episode: off/coming soon
- Kling and Seedance public: off/coming soon
- Key4U public video: off; Key4U remains admin smoke/fallback candidate only

## Safety Retained

- User confirmation before provider call and Xu deduction
- User job lock to prevent duplicate submits
- Refund/no-charge path on provider failure
- ShopAIKey provider smoke gate
- Auto-freeze policy remains in the existing video safety layer
- 200 Xu starter tier keeps existing day/week/month limits
- 500/600/800/1000 have no daily tier limit in this phase, as requested

## Commands

- `/video_tier_status`
- `/video_public_status`
- `/video_open_all_current_tiers`
- `/video_close_high_tiers`
- `/video_open_high_tiers` kept for compatibility

## Manual Test Checklist

- `/runtime`
- `/video_tier_status`
- `/video_public_status`
- Choose 500/600/800/1000 and verify the confirmation screen appears without billing/cost gate text
- Choose 1500 and verify coming-soon guard
- Confirm 300/400 regression flow still reaches invoice/confirm/job path

## Not Touched

- PayOS
- `/naptien`
- payment webhook
- paid top-up Xu
- trial 200 Xu bonus
- combo/package wallet
- DB destructive operations
- ShopAIKey provider core
- Key4U public video
- image/translation/document/PDF flows
