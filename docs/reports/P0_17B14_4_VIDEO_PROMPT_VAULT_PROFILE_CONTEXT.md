# P0.17B14.4 Video Prompt Vault + Profile Context Engine

## Scope

This patch adds a local product-brain layer above the existing B13/B14 video flow:

- Prompt Vault: local JSON packs for 12 video profiles plus shared shot/camera/transition/color/negative/postprocess blocks.
- Profile Context Engine: selects product domain, style, camera, motion, color, transition, negative prompt and add-on cues from the selected profile plus user idea/assets/creative controls.
- Cinematic Continuity Ledger: locks subject/product/location, entry/exit states, match-cut bridges, emotional arc and forbidden changes across scenes.
- Public planning UI: profile selection, creative controls, text storyboard/prompt pack, named package tiers, owner/admin test label and bypass.

## Flow Contract

The public flow remains the same product path:

1. User chooses video product.
2. User chooses one of 12 profiles or auto suggestion.
3. User enters idea and optionally sends assets.
4. Bot generates storyboard/prompt context as text only.
5. User chooses add-ons, aspect ratio, package tier and scene count.
6. Bot shows invoice.
7. Real file generation only starts after final confirm.
8. Worker/render/postprocess remains downstream and unchanged.

## What Changed

- Added `services/video_prompt_vault.py`.
- Added `services/video_profile_context_engine.py`.
- Added `services/video_cinematic_continuity.py`.
- Added `config/video_prompt_vault/` with 12 profile packs and shared blocks.
- Extended `services/video_storyboard_planner.py` to build prompt context and continuity-aware scene prompts.
- Updated `services/video_prompt_continuity.py` to preserve the B14.4 prompt chain format.
- Extended `services/video_project_queue.py` with non-destructive `creative_control_json`.
- Updated `bot.py` to expose profile/style/package planning screens and owner/admin test-mode bypass.

## Explicitly Not Changed

- No video render/stitch engine changes.
- No provider integration changes.
- No PayOS/wallet/payment runtime changes.
- No music/Suno engine changes.
- No custom voice provider changes.
- No web/app/standalone changes.

## Validation Added

- Vault has exactly 12 profile packs and shared blocks.
- Vault is local config/service code, not a giant dict in `bot.py`.
- Public profile screen has no create-test/preview/fake/provider wording.
- Domain selection works for UGC perfume, real estate apartment, food drink, fashion outfit and cinematic sci-fi.
- Creative controls override profile context and feed provider-ready scene prompts.
- Continuity ledger writes entry/exit/match-cut bridges.
- Public prompt text/pack stays text-only and does not expose provider internals.
- Owner/admin bypass public video gate and receive a clear no-Xu test label.
- Package tier 200 disables add-ons.
