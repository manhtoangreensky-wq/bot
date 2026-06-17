# TOAN AAS Final Launch Fix Before 2026-06-20

Date: 2026-06-17

## Scope

P0 launch hardening for AI image edit, Chat AI vision status, TOAN AAS assistant knowledge, video tier policy, subtitle/dub gates and friendly user messages.

## Runtime changes

- Added status commands for image edit, Chat AI, TOAN AAS AI, video tiers and subtitle/dub readiness.
- Added image edit public open/close commands with owner-only smoke gate.
- Added image edit smoke aliases and guarded Gemini/ShopAIKey edit smoke commands.
- Added subtitle/dub public open/close commands with owner-only provider/test gate.
- Updated video tiers to 200/300/400/500/600/800 launch tiers and 1000/1500 coming soon.
- Updated 200 Xu starter limits to 3/day, 10/week and 30/month.

## Public launch posture

Open only when provider, smoke and cost gates pass. No feature is marked public merely because a menu exists.

## Kept guarded

- Gemini/ShopAIKey image edit real output path: guarded until wired and smoke-tested.
- 1000/1500 video tiers: coming soon, no public job.
- Long AI video, multi-episode, Kling/Seedance: coming soon.
- Full subtitle+dub modes: open only per mode after provider/test gate.

## Not touched

PayOS, /naptien, webhook, paid top-up Xu, trial bonus, combo/package wallet, storage add-on, DB destructive paths, web app production, stable document/PDF core.
