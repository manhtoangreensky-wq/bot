# TOAN AAS Subtitle/Dub Pipeline Report 2026-06-20

Date: 2026-06-17

## Pipeline

Input video -> ASR -> subtitle SRT/VTT -> translation if selected -> TTS if selected -> mux/burn-in if worker is ready -> output file.

## Modes

- Tạo phụ đề: requires ASR and subtitle smoke.
- Dịch phụ đề: requires ASR, translation provider and subtitle smoke.
- Lồng tiếng: requires ASR, TTS provider and dub smoke.
- Phụ đề + lồng tiếng: requires the full selected provider path and subtitle+dub smoke.

## Commands

- `/subtitle_dub_status`
- `/subtitle_status`
- `/tool_test_asr`
- `/tool_test_translate`
- `/tool_test_tts_for_dub`
- `/tool_test_video_subtitle`
- `/tool_test_video_dub`
- `/tool_test_subtitle_plus_dub`
- `/video_dub_public_open`
- `/video_dub_public_close`

## Public gate

`/video_dub_public_open` is owner-only and opens only modes with provider readiness and smoke PASS. It does not call providers or deduct Xu. Missing modes stay guarded.

## Worker rule

Mux/burn-in depends on Local Worker/FFmpeg readiness. If mux is not ready, the system must return separate subtitle/audio outputs or keep the mode guarded, not silently fail.
