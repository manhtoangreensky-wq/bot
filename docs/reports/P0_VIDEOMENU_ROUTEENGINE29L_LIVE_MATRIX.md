# P0 Video Menu Route/Engine 29L Matrix

Baseline main: `94ad8a97d128cfcbbd3439ec602c5c2f9fbde225`

Locked Video UI milestone: `0cefd4b`

Canonical evidence: `docs/reports/P0_VIDEOMENU_ROUTEENGINE29L_LIVE_MATRIX.json`

## Production Truth

29B through 29K now provide a shared contract and default-OFF local engines for Product Video, Frame Video, Animated Video, owner-footage Human/AI Video, grounded Summary Video, and Podcast Video. Their accepted legal fixtures create and fully decode real local MP4 files for one-scene and multi-scene modes.

That is not production LIVE evidence. No 29L Railway or VPS deployment was authorized, no production Telegram job was created, and no real or paid provider was called. The last approved Product Video worker evidence belongs to SHA `2622328872800abc08ec44372d49e05e8433618a`; the current merged bot runtime is `94ad8a97d128cfcbbd3439ec602c5c2f9fbde225`. Current Product Video worker SHA and heartbeat were not read after 29K, so dispatch remains blocked by `worker_current_runtime_unverified`.

`ALL VIDEO MENU ROUTES LIVE PASS=NO`

## Product Matrix

| Product | Engine head / merge | Modes | Offline artifact proof | Production state |
|---|---|---|---|---|
| Product Video | `5673e20`, `b7be4ca`, `7b5f1a1` / `0a67763`, `3344ce1`, `8e54a08` | one and many scenes | 34 + 30 + 60 accepted cases; real local MP4; same-task recovery | default OFF; no current worker/deploy/live receipt |
| Frame Video | `dbec053` / `5ba9a2d` | one and many frames/scenes | 21 accepted cases; local FFmpeg MP4 | default OFF; no current worker/deploy/live receipt |
| Animated Video | `c4120e5` / `8f7c3e3` | one and many scenes | 12 accepted cases; deterministic moving MP4 | default OFF; no current worker/deploy/live receipt |
| Human/AI Video | `a66ebd5` / `f7975d7` | one and many owner-footage scenes | 11 accepted cases; source-lineage MP4 | default OFF; unsupported generation stays blocked |
| Summary Video | `97814e6` / `86401d2` | one and many grounded scenes | 15 accepted cases; source-mapped MP4 | default OFF; no production intake/deploy/live receipt |
| Podcast Video | `a580ae1` / `a757df6` | one and many visual podcast scenes | 24 accepted cases; source-audio-preserving MP4 | default OFF; runtime entrypoint and production finalizer missing |

Shared evidence on the 29K merged tree:

- accepted 29B-29K engine suite: `245 passed`;
- focused Podcast Video: `24 passed`;
- locked Video UI branch and clean main: `144 passed` and `144 passed`;
- FFmpeg security/output matrix: `102 passed`;
- snapshot updates: `0`;
- Video UI files changed: `0`;
- real provider calls: `0`;
- paid provider calls: `0`;
- production Telegram deliveries: `0`;
- wallet mutations: `0`.

29L final verification on latest main `94ad8a9` adds `7 passed` focused matrix cases and `252 passed` for the accepted 29B-29L engine/matrix suite. The exact locked Video UI comparator remains `144 passed` on both branch and clean main.

### Product Video

The one-scene route freezes the approved prompt, product/profile identity, references, scene duration, ratio, audio/add-ons, and branding before one fixture submit. The multi-scene route freezes ordered scene prompts and continuity, submits once per required scene in legal fixtures, polls the same accepted task, reuses completed scenes, refuses `ACCEPTANCE_UNKNOWN` resubmission, composes once, and validates the final MP4. Production provider flags remain OFF.

### Frame Video

Frame Video retains exact frame fingerprints and order, per-frame duration, fit/crop, deterministic motion, transitions, text, audio, logo, and watermark. It is local-only and does not pretend pan/zoom is new generative content. Both one-frame and multi-frame fixtures produce real MP4 files and verify full frame coverage.

### Animated Video

Animated Video freezes character, prop, palette, lighting, style, rights receipts, and scene continuity. It renders deterministic local motion from approved assets and composes all required scenes. It does not silently choose a cloud provider or label a static storyboard as completed animation.

### Human/AI Video

The implemented lane is owner-supplied footage processing. Source ownership and applicable person, face, voice, and brand consents are immutable inputs. Source segments, identity locks, scene prompts, audio, captions, and branding are preserved. Avatar generation, cloning, lip-sync, and direct generative transformation remain truthful blockers until an approved capability exists.

### Summary Video

Every summary unit must map to source evidence and every scene maps to grounded claims. Extraction failure, unsupported extraction, missing evidence, or an ungrounded claim stops rendering. The admin source map remains part of the artifact evidence; no fabricated summary is allowed.

### Podcast Video

Podcast Video treats the selected speech stream as the canonical timeline. Transcript IDs, timing, speaker truth, visual scene coverage, captions, waveform, rights-approved assets, and branding are frozen. Source speech is muxed once and decoded source/output audio content is compared. Production remains blocked by `podcast_runtime_entrypoint_missing` and `podcast_production_finalizer_missing`.

## Prompt And Flow Fidelity

All six engines consume an approved immutable snapshot rather than rebuilding customer choices. The snapshot preserves original prompt, profile, facts and forbidden claims, source/reference fingerprints, ordered scenes, start/action/end state, camera and motion, duration and ratio, audio/voice/add-ons, logo/watermark, explicit provider policy, idempotency key, runtime SHA, and expected worker SHA.

One-scene execution permits one complete semantic action with a finished camera move. Multi-scene execution preserves scene order and continuity, validates every required scene, refuses to drop a failed scene, normalizes media only where needed, composes once, validates full decode, and requires exactly-once delivery, receipt, charge, and report boundaries.

Trend, 32-content, idea, script, and storyboard selections remain profiles and approved-plan inputs to the correct engine. 29L adds no menu, callback, state, Back, status panel, or new public flow.

## Rollback

Every owned engine has an engine-enable flag and a public-allow flag that default to OFF. Product Video also has explicit real-provider flags that default to OFF. Local-only products expose no cloud provider path. Automatic retry, auto-resubmit, and automatic fallback remain OFF. Podcast additionally requires an explicit runtime-registration flag.

Safe rollback is therefore configuration-only: leave or return engine/public/provider/runtime flags to OFF. Status and health reads must never submit, charge, deliver, or mutate a wallet.

`VIDEO EDIT ROUTE/ENGINE RELEASED=YES`

Video Edit is owned by the dedicated Video Edit task. 29L neither changes nor claims its route, engine, worker, tests, or live result.

## Remaining Live Gates

Before any product may be marked production LIVE:

1. Re-run queue safety and prove eligible pending, running, stale claimable, and unknown accepted provider tasks are all zero.
2. Read the actual worker SHA and heartbeat against the exact approved runtime SHA; do not restart on a non-empty queue.
3. Deploy only an owner-approved SHA and keep public/provider flags OFF until each product lane is tested.
4. For a paid lane, report product, provider, model, estimated cost, expected submit count, and fallback policy, then receive separate approval.
5. Run one product at a time through the locked confirmation flow and record deployment ID, job ID, mode, provider calls, MP4 bytes, duration, codec, resolution, delivery, receipt, report, duplicate/stuck counters, wallet mutation, and admin charge.
6. Claim LIVE only after the actual Telegram MP4 is accepted and the receipt/report are persisted exactly once.

Until those gates are supplied, all production MP4 metric fields remain unset and no LIVE PASS is claimed.
