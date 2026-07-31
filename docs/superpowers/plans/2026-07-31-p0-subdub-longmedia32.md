# P0.SUBDUB.LONGMEDIA32 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve PR #606 and the passing four-lane short SubDub path while producing one complete, validated MP4 for supported long, large, and unfamiliar media with truthful progress and one canonical final report.

**Architecture:** Keep the existing public callbacks and canonical SubDub runner. Add provider-neutral media preflight and deterministic stage artifacts, apply Telegram's 20 MiB limit only to cloud Bot API transport, use whole-file ASR through its measured capability and checkpointed audio chunks above it, and validate against the canonical final timeline. Subtitle-only lanes retain source duration; dub/combo preserve PR #606's complete sequential speech and may extend source frames within the one-hour product capability. Existing delivery and receipt idempotency remain authoritative.

**Tech Stack:** Python, python-telegram-bot, FFmpeg/FFprobe, SQLite's existing `system_settings` persistence, pytest.

---

### Task 1: Lock Short Baseline And Write LONGMEDIA32 RED Tests

**Files:**
- Create: `tests/test_p0_subdub_longmedia32_duration_size_status_report.py`
- Modify: `docs/reports/P0_SUBDUB_LONGMEDIA32_LIMIT_MATRIX.md`

- [ ] Run the protected Restore400, international, terminal receipt, Local Bot API, and four-lane short selectors on clean latest main and record exact results.
- [ ] Add RED tests proving 59 seconds stays direct, 61/90/180/300 seconds use deterministic chunks, and one hour is accepted without public video-part delivery.
- [ ] Add RED tests proving cloud Bot API keeps its 20 MiB intake and 45/49 MiB delivery limits while local Bot API, local path, and legal byte fixtures use the bounded 500 MiB processing/delivery ceiling.
- [ ] Add RED tests for unfamiliar probe metadata, duration-derived timeouts, PR #606 full-speech TTS/mux, transformed subtitle identity, monotonic terminal 100%, and one report shape for all four lanes.
- [ ] Run only the new nodes and confirm each fails for the missing LONGMEDIA32 contract, not import or fixture errors.

### Task 2: Canonical Media Preflight And Normalization

**Files:**
- Create: `services/subdub_media_preflight.py`
- Modify: `bot.py`
- Test: `tests/test_p0_subdub_longmedia32_duration_size_status_report.py`

- [ ] Implement a pure FFprobe JSON parser that records container, codecs, pixel format, frame-rate truth, rotation, start time, timebase, audio streams/sample rate/layout, duration, dimensions, and normalization reasons.
- [ ] Implement operation-specific timeout derivation from measured duration with bounded floors and ceilings.
- [ ] Implement an injected FFmpeg normalization command that resets timestamps, preserves display orientation/full duration/content dimensions, pads odd dimensions by at most one pixel, and emits H.264/yuv420p plus AAC only when required.
- [ ] Make `subdub_probe_video_bytes` use the canonical parser and run normalization once after intake when the preflight requires it.
- [ ] Validate normalized duration, display geometry, and decodability before any ASR or render stage.

### Task 3: Capability-Based Intake And Deterministic ASR Chunks

**Files:**
- Modify: `bot.py`
- Modify: `services/subdub_long_media.py`
- Test: `tests/test_p0_subdub_longmedia32_duration_size_status_report.py`

- [ ] Replace `subdub_input_limit_mb()` call sites with an intake-method contract: cloud direct download 20 MiB, Local Bot API/local path/legal fixture 500 MiB, all bounded before buffering.
- [ ] Set the explicit SubDub product duration capability to one hour and remove the public multi-part delivery branch from the four-lane execution path.
- [ ] Keep direct ASR through 60 seconds; above 60 seconds build stable source-hash chunk IDs with bounded overlap and global timestamp ownership.
- [ ] Persist per-chunk extraction/ASR state and artifact hashes in the existing workspace; reuse completed chunks after restart and never auto-resubmit `ACCEPTANCE_UNKNOWN`.
- [ ] Deduplicate overlap by stable normalized text/timestamp ownership and prove no duplicate or missing cues at boundaries.

### Task 4: PR #606 Full-Speech TTS And One Final Compose

**Files:**
- Modify: `bot.py`
- Modify: `services/subtitle_dub_product_pipeline.py`
- Test: `tests/test_p0_subdub_longmedia32_duration_size_status_report.py`
- Test: `tests/test_p0_subdub_live10_tts_checkpoint_resume.py`

- [ ] Restore a canonical TTS cue checkpoint contract with stable cue IDs, hashes, one accepted request per cue, and same-runtime lease protection.
- [ ] Preserve the PR #606 sequential timeline planner: prefer conservative tempo adjustment, never overlap or drop a sentence, and extend the final timeline when required.
- [ ] Keep subtitle-only outputs at measured source duration and dub/combo outputs at the complete planned speech duration, bounded by the one-hour product capability.
- [ ] Force final `apad`, `atrim`, `amix`, and `-t` values to the canonical final timeline; never use `-shortest` or trim the video to a partial TTS track.
- [ ] Compose combo once from the translated subtitle artifact and the complete dubbed audio timeline.

### Task 5: Artifact Identity, Progress, And Canonical Report

**Files:**
- Modify: `bot.py`
- Test: `tests/test_p0_subdub_longmedia32_duration_size_status_report.py`

- [ ] Record source, subtitle, final MP4, and delivered artifact SHA-256 fingerprints without exposing private paths or provider metadata publicly.
- [ ] Reject translated-subtitle success when the translated SRT is absent, target language is unproven, source/output paths are identical, or the transformed MP4 is not validated.
- [ ] Keep existing delivery receipt locks and terminal panel replacement; enforce durable monotonic progress and terminal 100% after confirmed delivery.
- [ ] Expand `video_dubbing_receipt_text` into the one shared report for all four lanes: lane, source/target language, input/output duration, cue/TTS/audio metrics, file validation, Xu truth, and safe support code.
- [ ] Prove duplicate callback/restart cannot duplicate media, report, mux, provider submit, or wallet mutation.

### Task 6: Boundary, Unfamiliar, Recovery, And Isolation Gates

**Files:**
- Create/modify only focused SubDub tests and legal generated fixtures.

- [ ] Run 59/61/90-second, 3/5-minute, just-under/over-20-MiB, and approximately-75-MiB contracts with provider and wallet fakes.
- [ ] Run VFR, rotation, non-zero timestamp, mono/44.1 kHz/multiple-audio, MOV/MKV/WebM, odd timebase, no-audio, and locally supported HEVC fixtures.
- [ ] Prove full decode, canonical-duration tolerance, geometry/orientation, subtitle pixel evidence, audio activity, TTS cue coverage, and final MP4 identity.
- [ ] Run restart checkpoints at ASR, TTS, pre-mux, and delivery/report boundaries.
- [ ] Run all current SubDub, Local Bot API, Product Video, Frame Video, Video Edit, and callback-owner isolation selectors; compare every failure with the exact clean-main command.

### Task 7: Static Review And One PR

**Files:**
- All changed files from Tasks 1-6 only.

- [ ] Run changed-module/test `py_compile`, `bot.py` tokenize/narrow AST, `git diff --check`, callback collision, secret, private-path, and forbidden-scope scans.
- [ ] Confirm real provider calls, paid calls, wallet mutations, production Telegram deliveries, Railway deploys, and VPS changes are all zero.
- [ ] Review diff against the task and limit matrix, then commit and push the one branch.
- [ ] Open exactly one PR titled `P0.SUBDUB.LONGMEDIA32: support long media and truthful terminal output`.
- [ ] Stop without merge, deploy, live provider smoke, Telegram delivery, or production job replay.
