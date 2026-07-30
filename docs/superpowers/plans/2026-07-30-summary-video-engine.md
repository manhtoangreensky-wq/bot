# Summary Video Engine Implementation Plan

> For agentic workers: implement this plan task by task with TDD and keep the locked Video UI regression suite unchanged.

**Goal:** Connect Summary Video to a truthful, grounded, default-OFF local MP4 engine without changing the public flow or inventing claims when source extraction is unavailable.

**Architecture:** Freeze one allowed source (`video`, `audio`, `document`, `text`, or `link`), its fingerprint, an extraction artifact, grounded summary units, an ordered scene map, and approved visual/audio assets. The local lane supports direct text extraction and externally completed extraction artifacts; it never pretends to perform unavailable ASR, OCR, document parsing, or network fetches. Every extractive summary claim must be traceable to source units before any frame is rendered. Approved scene assets are rendered through the existing Frame Video FFmpeg runtime and composed with the existing multiscene pipeline.

**Tech Stack:** Python dataclasses, shared `VideoEngineRequest`, existing `frame_video_runtime`, existing `multiscene_video_pipeline`, local FFmpeg/ffprobe, pytest legal fixtures.

---

### Task 1: Lock source, extraction, and grounding truth

**Files:**
- Create: `services/summary_video_engine.py`
- Modify: `services/video_engine_contract.py`
- Test: `tests/test_p0_videomenu29j_summary_video_engine.py`

- [x] Write tests for the exact five locked source types, default-OFF flags, route metadata, source fingerprints, extraction status, and fail-closed unsupported extraction.
- [x] Run the focused test and observe RED before production code exists.
- [x] Require every summary unit to reference valid source units and every local extractive claim to occur in its referenced source text.
- [x] Persist source locators: timestamps for audio/video, pages for documents, ranges/paragraphs for text, and canonical URL/section for links.

### Task 2: Render one and many grounded summary scenes

**Files:**
- Create: `services/summary_video_engine.py`
- Test: `tests/test_p0_videomenu29j_summary_video_engine.py`

- [x] Add RED tests for real single-scene and multi-scene MP4s, ordered claims, full source-map coverage, motion, full decode, and approved audio/branding.
- [x] Render only approved visual assets and preserve prompt, claim, evidence IDs, asset fingerprints, and scene order in per-scene manifests.
- [x] Compose through `multiscene_video_pipeline`; apply approved subtitles, logo, watermark, and audio without provider calls.
- [x] Persist an admin-only source map that links each final scene and claim back to exact source references.

### Task 3: Exactly-once finalization and truthful failure

**Files:**
- Modify: `services/summary_video_engine.py`
- Test: `tests/test_p0_videomenu29j_summary_video_engine.py`

- [x] Add RED tests for extraction failure, ungrounded claims, missing scene assets, duplicate dispatch/finalization, production delivery callback, and wallet mutation.
- [x] Finalize delivery, receipt, zero-charge admin record, and terminal report exactly once.
- [x] Keep provider calls, paid calls, automatic retry/fallback, production Telegram, and wallet mutation at zero.

### Task 4: Regression and ship gate

**Files:**
- No UI files; only the 29J adapter, shared contract, focused test, and this plan may change.

- [x] Run focused 29J, 29B-29I engine regressions, FFmpeg security/output matrix, exact locked 144 UI tests, changed-module `py_compile`, `git diff --check`, secret/private-path scan, and forbidden-scope scan.
- [ ] Push one commit, open the 29J PR, inspect exact scope and CI, then merge with a merge commit.

**Out of scope:** UI/UX, callbacks, Back/back-stack, status/pricing, `bot.py`, worker/VPS/Railway, paid provider, production Telegram, DB schema, Video Edit, SubDub, Human/AI, and Podcast.
