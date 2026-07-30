# Podcast Video Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect Podcast Video to a truthful, default-OFF local engine that preserves approved speech audio and renders real single-scene or multi-scene MP4s without changing the locked public flow.

**Architecture:** Freeze an approved audio/video source fingerprint, an explicit source-audio stream index, completed transcript provenance, bounded speaker truth, ordered scene-to-transcript coverage, visual asset fingerprints, captions, waveform policy, branding, and output profile. Decode that selected speech stream to canonical PCM, render approved visuals through the existing Frame Video runtime, compose through the existing multiscene pipeline, mux the canonical speech once, and compare decoded source/output audio content before success. Local code never invents ASR, diarization, active-speaker accuracy, music, provider generation, retry, or fallback.

**Production truth:** The engine and local legal fixture harness exist behind default-OFF flags. Production remains `ENGINE_MISSING` until a separate runtime entrypoint is registered, and production finalization remains blocked by `podcast_production_finalizer_missing` because worker and durable DB changes are outside 29K. Only the explicit fixture mode may self-register the local harness and use the in-memory admin-zero-charge fixture finalizer.

**Tech Stack:** Python dataclasses, shared `VideoEngineRequest`, existing `frame_video_runtime`, existing `multiscene_video_pipeline`, local FFmpeg/ffprobe, pytest legal WAV/PNG/MP4 fixtures.

---

### Task 1: Freeze source, transcript, and speaker truth

**Files:**
- Create: `services/podcast_video_engine.py`
- Modify: `services/video_engine_contract.py`
- Test: `tests/test_p0_videomenu29k_podcast_video_engine.py`

- [x] Write failing tests for exact audio/video input types, default-OFF flags, source fingerprints, real stream probing, completed transcript provenance, segment timing, and fail-closed missing speech audio.
- [x] Allow absent diarization only for a declared one-speaker transcript.
- [x] Require completed diarization, bounded confidence, speaker IDs, and explicit active-speaker QC before a speaker layout may claim active-speaker accuracy.
- [x] Preserve source rights and every transcript segment in the immutable approved plan.

### Task 2: Render single-scene and multi-scene visual podcasts

**Files:**
- Create: `services/podcast_video_engine.py`
- Test: `tests/test_p0_videomenu29k_podcast_video_engine.py`

- [x] Add failing tests for one-scene and three-scene real MP4s, complete ordered scene coverage, selected-stream PCM/content evidence, transcript SRT timing, optional waveform, and strict full decode.
- [x] Require scene ranges to cover the source timeline without gaps, overlaps, dropped transcript segments, or duplicated transcript segments.
- [x] Render only rights-approved visual assets and preserve prompt, speaker, transcript, timing, asset fingerprint, and scene order in evidence manifests.
- [x] Mux the canonicalized approved source speech once; never synthesize music or replace speech audio.

### Task 3: Branding, QA, and exactly-once finalization

**Files:**
- Modify: `services/podcast_video_engine.py`
- Test: `tests/test_p0_videomenu29k_podcast_video_engine.py`

- [x] Add failing tests for independent logo/watermark positions, audio continuity, caption timing, waveform evidence, duplicate dispatch/render/finalization, production callback rejection, and wallet mutation rejection.
- [x] Validate container, video/audio streams, duration tolerance, strict full decode, compositor scene coverage, transcript coverage, unclipped speech, pixel-region branding evidence, and source/output speech-content evidence before fixture delivery.
- [x] Finalize fixture delivery, receipt, zero-charge admin record, and terminal report exactly once in the explicitly in-memory fixture ledger; make no production durability claim.
- [x] Keep provider calls, paid calls, automatic retry/fallback, production Telegram, music generation, and wallet mutation at zero.

### Task 4: Regression and ship gate

**Files:**
- No UI files; only the 29K engine, shared contract, focused test, and this plan may change.

- [x] Run focused 29K, accepted 29B-29J regressions, exact locked 144 UI tests on clean main and branch, FFmpeg security/output matrix, changed-module `py_compile`, `git diff --check`, secret/private-path scan, and forbidden-scope scan.
- [ ] Push one commit, open the 29K PR, inspect exact scope and CI, then merge with a merge commit.

**Out of scope:** UI/UX, callbacks, Back/back-stack, status/pricing, `bot.py`, worker/VPS/Railway, production runtime registration, durable production finalization, paid provider, ASR, automatic diarization, Music/Suno, production Telegram, DB schema, Video Edit, SubDub, Summary Video, and highlight extraction absent an explicit approved clip plan.
