# Animated Video Engine Implementation Plan

> For agentic workers: implement this plan task by task with TDD and keep the locked Video UI regression suite unchanged.

**Goal:** Connect the existing Animated Video product contract to a truthful local single-scene and multi-scene MP4 engine without changing the public flow.

**Architecture:** Add one UI-free animated engine adapter that validates an approved scene graph, renders each approved image/character asset with deterministic motion through an opt-in continuous-motion path in the existing Frame Video FFmpeg runtime, composes scenes with the existing multiscene pipeline, and finalizes delivery/receipt/charge/report exactly once. Extend the shared route contract only for Animated Video single_scene and multi_scene when default-OFF flags are explicitly enabled; shared runtime defaults remain unchanged.

**Tech Stack:** Python dataclasses, existing shared VideoEngineRequest contract, existing frame_video_runtime, existing multiscene_video_pipeline, local FFmpeg/ffprobe, pytest fixtures.

---

### Task 1: Lock the 29H contract and default-off route

**Files:**
- Create: `services/animated_video_engine.py`
- Modify: `services/video_engine_contract.py`
- Test: `tests/test_p0_videomenu29h_animated_video_engine.py`

- [ ] Write tests for default-off flags, supported modes, exact route metadata, required approved asset/rights fields, and rejection of unsupported claims.
- [ ] Run the focused tests and confirm they fail because the adapter and route do not exist.
- [ ] Implement immutable scene/plan/request dataclasses and the route/readiness functions. The route must remain disconnected when flags are absent, and must never select a provider automatically.
- [ ] Run the focused contract tests and confirm they pass.

### Task 2: Render one and many approved scenes locally

**Files:**
- Modify: `services/animated_video_engine.py`
- Modify: `services/frame_video_runtime.py`
- Modify: `services/multiscene_video_pipeline.py`
- Test: `tests/test_p0_videomenu29h_animated_video_engine.py`

- [ ] Add RED tests for one-scene and multi-scene local renders, ordered scene identity, character/style continuity, real motion evidence, full decode, and no render when a required asset or rights receipt is missing.
- [ ] Implement local rendering by passing one approved image/character asset per scene to `frame_video_runtime.build_ffmpeg_command` with opt-in continuous still-image motion, then compose the resulting clips through `multiscene_video_pipeline.finalize_multiscene_scene_clips`.
- [ ] Apply approved audio, caption, logo and watermark assets. Keep nine-position logo/watermark values independent, use an explicit local font file for drawtext, and fail closed instead of copying the unmodified master when muxing fails.
- [ ] Persist scene manifests, transition plan, prompt/style hashes, asset fingerprints, output profile, and validation evidence under the job workspace.
- [ ] Run the focused real-FFmpeg tests and confirm one-scene and multi-scene MP4s decode successfully.

### Task 3: Add exactly-once finalization and safety counters

**Files:**
- Modify: `services/animated_video_engine.py`
- Test: `tests/test_p0_videomenu29h_animated_video_engine.py`

- [ ] Write RED tests for duplicate dispatch/finalization, failed scenes, production delivery callbacks, wallet mutation, and zero provider calls.
- [ ] Implement an in-memory testable ledger with durable evidence writes, idempotency by approved plan plus asset fingerprints, fail-closed delivery/receipt/charge/report boundaries, and admin zero-charge behavior.
- [ ] Run focused tests and verify duplicate submit/delivery/receipt/report and wallet/provider counters remain zero where required.

### Task 4: Regression and ship gate

**Files:**
- No UI files; only the 29H adapter, shared contract/runtime/compositor changes, focused test, and this plan may be in the PR.

- [ ] Run focused 29H, legacy animated/profile tests, 29B-29F regressions, exact locked 144 UI tests, py_compile, git diff --check, secret/private-path scan, and forbidden-scope scan.
- [ ] Verify the 0cefd4b locked milestone and 29F merge are ancestors, then push one commit and open PR 29H.
- [ ] Merge only after head/file/clean checks, using a merge commit; record the merge SHA and parent count.

**Out of scope:** UI/UX, callbacks, Back/back-stack, status/pricing, bot.py, worker/VPS/Railway, provider/Telegram, DB schema, Video Edit, Human/AI, Summary, and Podcast.
