# TOAN AAS Engine Roadmap: Voice, Music, Subtitle, Video

Date: 2026-06-23

Scope: audit and roadmap only. No public UI/flow, menu, button, price, PayOS, wallet, or provider-internal behavior is changed by this report.

Readiness labels:

- `configured`: code path, settings, table, or adapter foundation exists.
- `smoke pass`: an admin smoke result proves the route works end to end.
- `public ready`: configured plus required smoke pass plus safe public cost/guard behavior.
- `guarded`: public request must stop behind clean no-charge copy until readiness is proven.

Important rule: this report does not claim `public ready` for any route unless a real smoke pass is already recorded.

## Video Tier Audit

All video tiers must route to the final invoice/export confirmation when enabled, or to a clean no-charge guard when not ready.

| Tier | Code tier | Current route | Readiness | Public stance |
| --- | --- | --- | --- | --- |
| 200 Xu | `low` | ShopAIKey primary with Key4U/Kling fallback path; final invoice/export route is present. | Configured; smoke pass required before public-ready claim. | Invoice/export or clean guard. |
| 300 Xu | `basic` | ShopAIKey primary with Key4U/Kling fallback path; final invoice/export route is present. | Configured; smoke pass required before public-ready claim. | Invoice/export or clean guard. |
| 400 Xu | `common` | ShopAIKey primary with Key4U/Kling fallback path; final invoice/export route is present. | Configured; smoke pass required before public-ready claim. | Invoice/export or clean guard. |
| 500 Xu | `advanced` | ShopAIKey primary with Key4U/Kling fallback path; final invoice/export route is present. | Configured; admin paid smoke required. | Guarded unless smoke has passed. |
| 600 Xu | `standard` | ShopAIKey primary with Key4U/Kling fallback path; final invoice/export route is present. | Configured; admin paid smoke required. | Guarded unless smoke has passed. |
| 800 Xu | `high` | ShopAIKey primary with Key4U/Kling fallback path; final invoice/export route is present. | Configured; admin paid smoke required. | Guarded unless smoke has passed. |
| 1000 Xu | `future_1000` | Key4U/Kling high-tier route; final invoice/export or clean guard. | Configured foundation; public smoke not proven here. | Guarded. |
| 1200 Xu | `future_1200` | Key4U/Kling high-tier route; final invoice/export or clean guard. | Configured foundation; public smoke not proven here. | Guarded. |
| 1500 Xu | `future_1500` | Key4U/Kling high-tier route; final invoice/export or clean guard. | Configured foundation; public smoke not proven here. | Guarded. |

## MiniMax Voice

Current route:

- MiniMax TTS readiness is exposed through `get_minimax_voice_readiness()`.
- MiniMax voice clone readiness is exposed through `get_minimax_voice_clone_readiness()`.
- Admin-only status command: `/voice_engine_status`.

Readiness:

- `configured`: adapter/readiness foundation exists for TTS and clone.
- `smoke pass`: requires recorded admin smoke for TTS and clone where clone is public-facing.
- `public ready`: only when public flags and required smoke pass are both true.
- `guarded`: any missing key, route, or smoke pass keeps public voice/clone guarded.

Needs admin paid smoke:

- MiniMax TTS sample output.
- MiniMax clone upload/clone/TTS output.

## Suno Music

Current route:

- Suno submit/fetch/download readiness is exposed through `get_suno_music_readiness()`.
- Preferred provider and fallback status are summarized by `/music_engine_status`.

Readiness:

- `configured`: Suno submit/fetch adapter foundation exists.
- `smoke pass`: submit plus fetch plus downloadable full result must pass.
- `public ready`: only when cost gate, public flag, submit smoke, fetch smoke, and full-result download smoke are all proven.
- `guarded`: missing full result, missing smoke, or missing cost gate keeps public music generation guarded.

Needs admin paid smoke:

- Suno submit.
- Suno fetch/poll.
- Full-result download/preview.

## Subtitle, Translate, Dub

Current route:

- ASR, translation, TTS/dub, FFmpeg mux, subtitle burn readiness are summarized by `get_subtitle_dub_readiness()`.
- Admin-only status command: `/subtitle_engine_status`.

Readiness:

- `configured`: ASR, translation, TTS/dub, local worker/FFmpeg, and subtitle burn foundations exist.
- `smoke pass`: each mode needs its own smoke result: subtitle create, subtitle translate, dub, subtitle plus dub.
- `public ready`: only the modes with public flag plus required smoke pass can be called public ready.
- `guarded`: missing ASR/translation/TTS/local worker smoke keeps the affected mode guarded.

Needs admin paid smoke:

- Video subtitle creation.
- Subtitle translation.
- Video dub.
- Subtitle plus dub.

## Multi-Scene 120s Architecture

Foundation:

- Parent/child scene architecture exists for multi-scene video jobs.
- Scene-level render results can be stitched after successful child jobs.
- Public readiness depends on scene count, per-scene provider route, local stitch readiness, quota, and delivery limits.

Readiness:

- `configured`: multi-scene plan, child jobs, stitch flow, and status payload foundation exist.
- `smoke pass`: needs admin smoke for the exact target scene count and final stitched output.
- `public ready`: only after 20-scene/120s stitch smoke and delivery smoke pass.
- `guarded`: if target scene count or stitching is not proven, use clean no-charge guard.

## Long Video 2h Architecture

Foundation:

- Long-video project tables and scene tables exist.
- Project-level planning can split a long output into scene/chunk records.
- Final public delivery needs chunk render, stitch/merge, progress resume, quota control, and Telegram-safe delivery packaging.

Readiness:

- `configured`: project and scene table foundation exists.
- `smoke pass`: not claimed here.
- `public ready`: not claimed here.
- `guarded`: keep long video public entry guarded until chunk render, stitch, quota, resume, and delivery smoke pass.

## Risk, Cost, Quota, Telegram Limit

- Provider cost risk: video, music, voice clone, and dub routes can consume paid provider quota. Admin smoke must be deliberate and recorded.
- Xu risk: public guarded routes must not deduct Xu before a proven invoice/export path or clean guard.
- Quota risk: high video tiers, multi-scene, and long video need per-user and global caps before wider release.
- Telegram limit risk: large video outputs can exceed upload/file-size limits. Long outputs need chunked delivery or external delivery policy before public release.
- Retry risk: polling/fetch jobs need idempotency so retries do not duplicate paid provider calls or double charge Xu.
- Copy risk: public maintenance copy must stay non-technical and must not expose provider names, task/job IDs, API terms, keys, tokens, or debug state.

## Public Ready, Admin Smoke, Guarded

Public ready:

- No new route is marked public ready by this report.
- Existing public enabled flows may continue only where current code already gates them with invoice/export or clean guard behavior.

Needs admin paid smoke:

- MiniMax TTS.
- MiniMax voice clone.
- Suno submit/fetch/full-result download.
- Video tiers 500/600/800.
- Video tiers 1000/1200/1500 before public exposure.
- Subtitle create, translate, dub, subtitle plus dub.
- Multi-scene 120s stitched output.
- Long video chunk render/stitch/delivery.

Must stay guarded:

- Any route missing configured provider settings.
- Any route missing required smoke pass.
- Any high-cost route without quota caps.
- Any long or multi-scene route without Telegram-safe delivery proof.
- Any public route that would expose technical/provider details instead of clean maintenance copy.
