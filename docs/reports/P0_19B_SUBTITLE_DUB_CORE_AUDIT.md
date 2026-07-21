# P0.19B Subtitle Dub Core Audit

Branch: `hotfix/p0-19b-subtitle-dub-core-final-repair`

Base: latest `origin/main` at `5e7cb74a1461c9dc6c2979b7e9d164ebc26e3808` or newer.

Scope: subtitle generation, SRT validation, timestamp-preserving SRT translation, dubbing audio artifact creation, audio combine, optional video mux, partial result on mux failure, uploaded-video public guard, and admin fake smokes.

## Generated Video Subtitle Source

- Generated-video subtitle source is storyboard/narration text from the B14 video session draft.
- Core helper: `services/subtitle_dub_pipeline.py::build_transcript_from_storyboard()`.
- SRT helper: `services/subtitle_dub_pipeline.py::generate_srt_from_transcript()`.
- Video product addon state stores subtitle settings in the B14 addon plan and keeps provider work until confirmed worker execution.

## Uploaded Video Subtitle Source

- Uploaded video/audio source remains the `videodub|...` flow state:
  - `source_file_id`
  - `video_file_id`
  - `source_file_name`
  - `source_mime_type`
  - `media_kind`
- Public uploaded-video subtitle/dub stays guarded before confirm.
- Guard probe command: `/tool_test_uploaded_video_subtitle_guard --fake`.
- Handler path: `bot.py::cmd_tool_test_uploaded_video_subtitle_guard()`.

## ASR/STT Path

- Live uploaded media path is `bot.py::video_dubbing_prepare_subtitles()`.
- Media download path is `bot.py::video_dubbing_download_source()`.
- ASR/STT call path is `bot.py::video_dubbing_resolve_source_script()` -> `bot.py::video_dubbing_transcribe_bytes()`.
- Readiness path is `bot.py::get_asr_adapter_readiness()` and `providers/asr_provider.py`.
- Public users are blocked before ASR if the feature is not public-ready or not confirmed.

## Translate Path

- Core fake/admin SRT path is `services/subtitle_dub_pipeline.py::translate_srt_preserve_timestamps()`.
- Live segment translation path is `bot.py::translate_subtitle_segments()`.
- Segment translation calls `bot.py::translate_subtitle_text()` only after the flow reaches the confirmed/processing path.
- Timestamp validation is enforced by `services/subtitle_dub_pipeline.py::validate_srt()`.

## Dub Path

- Core helper path:
  - `services/subtitle_dub_pipeline.py::synthesize_dub_audio()`
  - `services/subtitle_dub_pipeline.py::combine_dub_audio()`
  - `services/subtitle_dub_pipeline.py::run_dub_pipeline()`
- Live TTS path is `bot.py::synthesize_dub_segment_chunks()` -> `bot.py::video_dubbing_tts_bytes()`.
- Dub success requires a non-empty audio artifact.
- Fake/admin smokes use `p0_18a_fake_tts()` and do not call paid providers.

## Mux Path

- Core helper path is `services/subtitle_dub_pipeline.py::mux_subtitle_or_dub_video()`.
- Live mux/render path is `bot.py::video_dubbing_render_video()` and `services/dubbing_pipeline.py::mux_final_video()` for retry/final video operations.
- Final dubbed-video success requires a non-empty MP4 artifact.
- If mux fails but audio or SRT exists, `services/subtitle_dub_pipeline.py::partial_result_on_mux_fail()` returns a partial result instead of fake MP4 success.

## Existing Callbacks And Commands

- Existing subtitle/dub callbacks:
  - `videodub|start|...`
  - `videodub|studio|...`
  - `videodub|type|subtitle_create`
  - `videodub|type|subtitle_translate`
  - `videodub|type|video_dub`
  - `videodub|type|subtitle_plus_dub`
  - `videodub|source_upload`
  - `videodub|language|...`
  - `videodub|voice|...`
  - `videodub|final`
  - `videodub|retry_mux`
- Existing generated-video addon callbacks:
  - `vproduct|b14_addon_subtitle`
  - `vproduct|b14_subtitle_original`
  - `vproduct|b14_subtitle_translate`
  - `vproduct|b14_subtitle_lang|...`
  - `vproduct|b14_addon_dub`
  - `vproduct|b14_dub_lang|...`
- P0.19B admin smoke commands:
  - `/tool_test_subtitle_from_storyboard --fake`
  - `/tool_test_subtitle_srt_validate --fake`
  - `/tool_test_translate_srt --fake`
  - `/tool_test_subtitle_dub_pipeline --fake-files`
  - `/tool_test_subtitle_dub_mux_failure --fake-files`
  - `/tool_test_uploaded_video_subtitle_guard --fake`

## Broken Or Dead Callbacks

- No new public callbacks were added in P0.19B.
- P0.19B did not reopen deprecated translation-video factory callbacks.
- `videodub|language|...` is intentionally a draft/confirm transition for uploaded video translation; it must not translate before final confirm.
- `vfinal|subtitle`, `vfinal|dub`, `vfinal|combo`, and `vfinal|translate_sub` remain compatibility-only or disallowed where prior tests expect the newer `videodub|start|video_addon` route.

## Locked Public Features

- Public uploaded-video subtitle/dub remains locked unless readiness and final confirmation allow processing.
- Public copy must not expose provider, API, endpoint, FFmpeg, mux, adapter, traceback, token, or raw diagnostic text.
- Public guard copy says TOAN AAS has not processed the file and has not charged Xu.
- Admin fake smokes can validate local logic without provider calls and without Xu charge.

## Safe Admin Test Path

1. `/tool_test_subtitle_from_storyboard --fake`
2. `/tool_test_subtitle_srt_validate --fake`
3. `/tool_test_translate_srt --fake`
4. `/tool_test_subtitle_dub_pipeline --fake-files`
5. `/tool_test_subtitle_dub_mux_failure --fake-files`
6. `/tool_test_uploaded_video_subtitle_guard --fake`

Expected safety:

- Provider call: no for fake smokes.
- Charge: no for fake smokes.
- LIVE PASS: not claimed.
- Deploy: not part of this branch.

## Not Touched

- PayOS/wallet/payment code: not changed.
- B13 render/stitch engine: not changed.
- VPS worker W1-W5: not changed.
- Voice custom provider core: not changed.
- Suno/music core: not changed.
- Web/app/standalone: not changed.
