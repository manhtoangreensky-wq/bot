# Human/AI Video Engine Implementation Plan

> For agentic workers: implement this plan task by task with TDD and keep the locked Video UI regression suite unchanged.

**Goal:** Connect the locked SelfShot2 and SelfShot3 planning contracts to a truthful, default-OFF Human/AI Video engine for owner-supplied footage without claiming unavailable avatar, face/voice cloning, lip-sync, or generative video capabilities.

**Architecture:** Freeze the approved SelfShot snapshot, source-video fingerprint, subject/relationship locks, scene prompts, and rights/consent receipts into an immutable engine plan. The local lane may only trim, normalize, compose, caption, brand, and preserve approved source footage through the existing FFmpeg and multiscene runtime. Generative transformation requests remain explicit blockers until an independently approved provider capability exists. Extend the shared route contract only for Human/AI `single_scene` and `multi_scene` when default-OFF flags are enabled.

**Tech Stack:** Python dataclasses, existing `video_selfshot2`/`video_selfshot3` planning contracts, shared `VideoEngineRequest`, existing `multiscene_video_pipeline`, local FFmpeg/ffprobe, pytest legal fixtures.

---

### Task 1: Lock route truth, rights, consent, and mode boundaries

**Files:**
- Create: `services/human_ai_video_engine.py`
- Modify: `services/video_engine_contract.py`
- Test: `tests/test_p0_videomenu29i_human_ai_video_engine.py`

- [ ] Write tests for default-OFF flags, exact route metadata, SelfShot2/SelfShot3 snapshot mapping, one/many scene rules, and unsupported generation claims.
- [ ] Run the focused test and observe RED before production code exists.
- [ ] Require source ownership, person consent, face/identity consent, conditional voice consent, and conditional brand rights. Never infer consent from a file path or provider response.
- [ ] Keep provider submit, automatic retry, and automatic fallback unavailable.

### Task 2: Render legal owner footage for one and many scenes

**Files:**
- Create: `services/human_ai_video_engine.py`
- Test: `tests/test_p0_videomenu29i_human_ai_video_engine.py`

- [ ] Add RED tests using locally generated MP4 fixtures with motion and audio.
- [ ] Materialize only the source segments selected by the locked scene plan; verify source fingerprints before rendering.
- [ ] Normalize and compose clips through `multiscene_video_pipeline`, preserving scene order, source audio, approved subtitle, logo, and watermark selections.
- [ ] Persist scene prompts, source lineage, consent receipts, subject locks, output profile, and full-decode evidence under the job workspace.
- [ ] Validate MP4 container/streams, complete scene coverage, motion, non-silent promised audio, source-lineage identity preservation, and no missing scene.

### Task 3: Exactly-once boundaries and truthful blockers

**Files:**
- Modify: `services/human_ai_video_engine.py`
- Test: `tests/test_p0_videomenu29i_human_ai_video_engine.py`

- [ ] Add RED tests for duplicate dispatch/finalization, missing source segments, fingerprint mismatch, production delivery callback, and wallet mutation.
- [ ] Finalize delivery, receipt, zero-charge admin record, and terminal report exactly once.
- [ ] Report avatar generation, AI presenter generation, direct video-to-video transformation, lip-sync, face clone, and voice clone as capability blockers; never emit a fake MP4 success for them.

### Task 4: Regression and ship gate

**Files:**
- No UI files; only the 29I adapter, shared contract, focused test, and this plan may change.

- [ ] Run focused 29I, 29B-29H engine regressions, exact locked 144 UI tests, changed-module `py_compile`, `git diff --check`, secret/private-path scan, and forbidden-scope scan.
- [ ] Verify latest main ancestry, push one commit, open the 29I PR, inspect exact scope and CI, then merge with a merge commit.

**Out of scope:** UI/UX, callbacks, Back/back-stack, status/pricing, `bot.py`, worker/VPS/Railway, paid provider, production Telegram, DB schema, Video Edit, Summary, and Podcast.
