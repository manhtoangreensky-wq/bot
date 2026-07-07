# P0.19M.M4BASELINE SubDub Forensic Report

## 1. M4 Identity

- PR: #160, P0.19M.4 SubDub canonical working pipeline all modes fullframe back routing.
- Merge commit: `7dd2210af1f0df793d69c4563fe0a0393ad7bb12`.
- Head commit: `166a476ea51edb68de3dc5a5486feac1e9c4ae1d`.
- Branch: `origin/hotfix/p0-19m4-subdub-canonical-working-pipeline-all-modes-fullframe-back-routing`.
- Commit message: `Canonicalize SubDub pipeline rendering and routing`.
- Files changed by M4:
  - `bot.py`
  - `tests/test_p0_17b12_1_flow_ui_contract.py`
  - `tests/test_p0_19g_professional_subtitle_dub_overlay_voice_delivery.py`
  - `tests/test_p0_19k_complete_subdub_flows_hardsub_cover_voice_gender_entry_fix.py`
  - `tests/test_p0_19l_final_subdub_core_rewrite_from_working_combined_path.py`
  - `tests/test_p0_19m1_professional_subtitle_overlay_style_only.py`
  - `tests/test_p0_19m4_subdub_canonical_working_pipeline_all_modes_fullframe_back_routing.py`

M4 explicitly claims and tests one canonical SubDub core for all 3 modes. The M4 test file asserts:

- subtitle-only uses the canonical combined core and does not call TTS.
- dub-only uses the canonical combined core and does not burn subtitle bytes.
- subtitle+dub uses the canonical combined core with both subtitle bytes and TTS.
- old subtitle and dub routes are wrappers into the canonical core.
- no late public error after success.
- no failed-then-success terminal sequence.
- success requires a Telegram message id.
- full-frame output keeps aspect ratio without black canvas padding.
- back routing returns to the correct setup screen.

## 2. M4 Pipeline Map

M4 shared core is centered in `services/subtitle_dub_product_pipeline.py`:

- `subdub_mode_uses_shared_core(mode)` at line 44.
- `process_subtitle_dub_job(...)` at line 88.
- `run_subdub_pipeline(...)` at line 326.

M4 Telegram/product wrapper functions in `bot.py`:

- `subdub_pipeline_audit_payload()` at line 82216.
- `video_dubbing_receipt_text(...)` at line 157802.
- `subdub_progress_keyboard(...)` at line 158491.
- `send_subdub_fail_once(...)` at line 158603.
- `mark_subtitle_dub_pipeline_output_sent(...)` at line 158771.
- `send_public_subtitle_dub_final_outputs(...)` at line 160013.
- `video_dubbing_back_route(...)` at line 160160.
- `video_dubbing_render_video(...)` at line 160761.
- `video_dubbing_prepare_subtitles(...)` at line 161365.
- `_execute_video_dubbing_pipeline_core(...)` at line 161492.

Mode routing in M4:

- Subtitle-only: `VIDEO_SUBTITLE_MODE_TRANSLATE` enters `_execute_video_dubbing_pipeline_core`, which delegates to `subtitle_dub_product_pipeline.run_subdub_pipeline`. The core prepares subtitles, translates when requested, renders MP4 with subtitle bytes, and skips TTS.
- Dub-only: `VIDEO_SUBTITLE_MODE_DUB` enters the same wrapper and same `run_subdub_pipeline`. It prepares dialogue segments, calls TTS, builds dub timeline audio, calls `video_dubbing_render_video` with audio, and passes empty subtitle bytes.
- Subtitle+dub: `VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB` enters the same wrapper and same `run_subdub_pipeline`. It prepares/uses translated subtitle bytes, calls TTS, builds audio, then renders one MP4 with subtitle bytes plus dubbed audio.

M4 render/delivery:

- MP4 rendering is `video_dubbing_render_video(...)`.
- MP4 public delivery is `send_public_subtitle_dub_final_outputs(...)`.
- Terminal lock is `mark_subtitle_dub_pipeline_output_sent(...)`.
- Late public failure suppression is `send_subdub_fail_once(...)`.
- Receipt/result copy is `video_dubbing_receipt_text(...)`.
- Progress/status panel is mediated through `subdub_progress_keyboard(...)` and `services/product_progress_status.py`.

M4 file handling:

- Input is accepted in `video_dubbing_prepare_subtitles(...)` and `_execute_video_dubbing_pipeline_core(...)`.
- M4 already has `pipeline_duration_limit_seconds(...)`.
- M4 had basic duration/file checks but not the later expanded M4B/M5A large-media handling.
- M4's full-frame behavior is explicit: `subdub_video_fit_mode() == "cover"` and `SUBDUB_KEEP_ORIGINAL_RESOLUTION is True`; tests check no `pad=` black canvas.

## 3. Current Divergence From M4

Current `origin/main` after M6AF differs from M4 in SubDub-relevant runtime mainly in:

- `bot.py`
- `services/product_progress_status.py`

`services/subtitle_dub_product_pipeline.py` is not changed from M4 in the current M4-to-main direct diff, which means the canonical shared service core is still structurally present. The regressions are more likely in the bot wrapper, input/save/duration/status/delivery/render/style code around that core.

Important post-M4 SubDub commits and branches:

- `da2a13d` / PR #204 M4B: long video duration gate.
- `20f284c` / PR #211 M5A: large Telegram media input save.
- `995c2e1` / PR #214 M5C: mode route and female voice state diagnostics.
- `56f863d` / PR #215 M6A: one terminal public outcome late error duplicate fix.
- `81c6de4` / PR #218 M6R: runtime terminal outcome path.
- `2094020` / PR #221 M6S: job registry partial audio debug lifecycle.
- `1dc772c` / PR #225 M6T: final video-only delivery, no public audio fallback.
- `f10c1e9` / PR #228 M6U: input save failed terminalization/debug/progress.
- `6309f03` / PR #231 M6V/19N: final report, female voice, audio mix.
- `a958de4` / PR #234 M6W: emergency rollback pipeline/font/volume UI.
- `1157624` / PR #239 M6X: public fallback/style/dub speed.
- `011d6b6` / PR #241 M6Y: revert M6X.
- `4dcecf6` / PR #242 M6Z: voice/subtitle/status/audio/report.
- `6c300a4` / PR #245 M6AB: suppress late fail and extra copy after video success.
- `277f0ab` / PR #248: stale subtitle cache fix.
- `61e8d39` / PR #252: ambiguous video upload media transcription restore.
- `bb3947a`, `6b6518c`, `05ff62e`: M6AE subtitle polish and dub known-good restore.
- `c235228`, `30e5584`: M6AF subtitle style and dub fallback.
- `751e96a` / PR #177 M7 and follow-up rollback: risky lifecycle rewrite.
- `9d38a36`, `5886789`: M8/M8R baseline/rollback attempts.

High-risk divergence from M4 in current `bot.py`:

- `subdub_caption_chunks(...)` and `subdub_split_srt_blocks_for_ass(...)` were introduced after M4 and alter ASS cue timing/splitting before render.
- `subdub_render_with_known_good_dub_fallback(...)` was introduced after M4 and wraps render for dub modes.
- `_execute_video_dubbing_pipeline_core(...)` now includes duration gates, many progress/status mutations, audio mix injection, and the M6AF dub fallback wrapper before render.
- `video_dubbing_prepare_subtitles(...)` now has translated subtitle cache reference handling. This looks useful and should be preserved only if it does not bypass the M4 prepare path.
- `send_public_subtitle_dub_final_outputs(...)` now has no-auto-SRT-after-MP4 suppression. This is a safe later fix and should be preserved.
- `handle_video_dubbing_callback(...)` now includes audio mix controls and progress/receipt terminalization. These are product features the user wants to keep, but they must call into the M4 shared core without changing the render/prepare semantics.
- `services/product_progress_status.py` has many later progress panel changes. The SubDub stage label changed from `Tạo giọng lồng tiếng` to `Tạo phụ đề / Tạo giọng lồng tiếng`, and later logic introduced special SubDub terminal handling. These changes should be preserved only where they do not alter job outcome or fire public failures.

## 4. Regression Suspects After M4

Most likely unsafe changes to drop or isolate from restore:

- M6AF cue splitting and ASS segmentation:
  - `subdub_caption_chunks(...)`
  - `subdub_split_srt_blocks_for_ass(...)`
  - call to `subdub_split_srt_blocks_for_ass(...)` inside `subdub_generate_ass_from_srt(...)`

- M6AF dub fallback wrapper:
  - `subdub_render_with_known_good_dub_fallback(...)`
  - replacement of direct `video_dubbing_render_video(*args, **kwargs)` inside `_execute_video_dubbing_pipeline_core(...)`

- Broad duration/input rewrites if they run before M4 prepare/render:
  - `subdub_duration_gate_payload_for_saved_input(...)`
  - duration gate failure before `video_dubbing_prepare_subtitles(...)`
  - input save changes that classify valid Telegram video as unsupported or too large before core can run

- Public fallback logic if it fires before delivery is actually known:
  - fallback SRT/audio public send before final MP4 decision
  - fail copy sent while render/delivery can still succeed

## 5. Safe Later Fixes To Preserve

Preserve only when implemented as wrappers around M4, not replacements of M4 prepare/render/core:

- No late public fail after MP4 delivery:
  - `send_subdub_fail_once(...)` should suppress after terminal success.
  - public generic X/fail must not fire after final delivery.

- No auto SRT/audio after MP4:
  - `send_public_subtitle_dub_final_outputs(...)` may keep `srt_auto_send_suppressed` and `auto_srt_after_video_prevented`.
  - for public video/dub outputs, internal audio/SRT artifacts must not be sent after MP4.

- Clean status/receipt:
  - `mark_subtitle_dub_pipeline_output_sent(...)` should terminalize at delivered/100% after Telegram message id.
  - receipt should show result, duration, cost/charged line, but must not drive pipeline state backwards.

- Back routing:
  - `video_dubbing_back_route(...)` can preserve exact previous-screen behavior if compatible with M4.

- International subtitle cache:
  - `translated_subtitle_ref` fix should be preserved if it only avoids stale cache and still flows through M4 `video_dubbing_prepare_subtitles(...)`.

- Audio split controls:
  - Keep original/dub volume controls only as state passed into render.
  - Do not let audio mix UI decide success/failure or replace M4 render path.

## 6. Unsafe Later Changes To Drop

Do not keep in the first restore task:

- new style/cue splitting work from M6AF.
- new dub fallback wrapper from M6AF.
- broad M7/M8 lifecycle rewrites.
- any public fallback that sends SRT/audio instead of waiting for MP4 outcome in video modes.
- input save or file-size branches that fail valid short Telegram videos before `video_dubbing_prepare_subtitles(...)`.
- any receipt/status code that can send failure after delivery or before render is terminal.

## 7. Restore Strategy

Recommended restore base: M4 merge commit `7dd2210af1f0df793d69c4563fe0a0393ad7bb12`, not PR238 and not M6W/M6AF.

Recommended method:

1. Restore M4 canonical runtime functions into current main:
   - `video_dubbing_prepare_subtitles(...)`
   - `video_dubbing_render_video(...)`
   - `_execute_video_dubbing_pipeline_core(...)`
   - `subdub_generate_ass_from_srt(...)`
   - `subdub_ass_wrap_text(...)`
   - `subdub_cover_filter(...)`
   - any helper directly required by those functions

2. Keep the existing service core:
   - `services/subtitle_dub_product_pipeline.py` is already aligned with the M4 shared-core model and should not be rewritten.

3. Re-apply safe fixes as thin wrappers:
   - no late fail after MP4.
   - no auto SRT/audio after MP4.
   - status/receipt 100% after valid Telegram delivery.
   - back routing where it does not change core pipeline.
   - translated subtitle cache reference if it only fixes stale cache.
   - audio split state, passed through render kwargs only.

4. Drop risky changes in first restore:
   - M6AF cue splitting.
   - M6AF dub fallback wrapper.
   - style-only changes beyond M4.
   - any fallback that changes success/failure semantics.

5. Test restore using M4 assertions plus later safety assertions:
   - subtitle-only sends MP4.
   - dub-only sends MP4 or fails cleanly without breaking subtitle-only.
   - subtitle+dub calls same core.
   - no SRT/audio public fallback after MP4.
   - no late fail after MP4.
   - translated cache remains fresh.
   - audio mix state is preserved but does not gate success.

## 8. M4 Test Attempt

Attempted command in M4 read-only worktree:

```text
python -m pytest -q tests/test_p0_19m4_subdub_canonical_working_pipeline_all_modes_fullframe_back_routing.py
```

Result:

- Timed out after 180 seconds with no failure output.
- Several Python child processes remained and were stopped.
- This is treated as an environment/test-hang blocker, not proof that M4 runtime fails.
- The M4 test source itself is still strong evidence of the intended all-mode canonical core contract.

## 9. Exact Next Task Draft: P0.19M.M4RESTORE

Task objective:

Restore current SubDub runtime to M4 canonical shared pipeline for subtitle-only, dub-only, and subtitle+dub, while preserving only safe later wrapper fixes.

Allowed runtime files:

- `bot.py`
- SubDub tests only
- `services/product_progress_status.py` only if needed for status display, not pipeline success/failure

Do not touch:

- Music/Suno
- Product Video
- Voice standalone
- PayOS/wallet
- Pricing/Finance
- DB migrations
- Telegram webhook
- provider core
- worker global logic

Must preserve:

- no late fail after MP4
- no public SRT/audio fallback after MP4
- clean status/receipt
- back routing
- international subtitle cache if compatible
- split original/dub audio volume state if compatible

Must drop:

- M6AF cue splitting
- M6AF known-good dub fallback wrapper
- style-only changes that alter prepare/render pipeline
- lifecycle rewrites that fail before M4 prepare/render on valid Telegram video

Primary live success criteria:

- `Dịch phụ đề / video` produces MP4 again.
- `Lồng tiếng video` uses the same M4 shared core and either produces MP4 or fails cleanly without breaking subtitle-only.
- `Phụ đề + Lồng tiếng` uses the same M4 shared core.
- No public fail copy after MP4.
- No auto SRT/audio after MP4.
