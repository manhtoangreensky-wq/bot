# TOAN AAS Subtitle/Dub Pipeline Report - 2026-06-20

## Pipeline

Upload media -> ASR -> subtitle -> optional translate -> TTS -> worker mux/burn if ready -> output.

If worker mux/burn is not ready, admin smoke can return SRT/audio separately. The bot must not claim a merged video was produced.

## Commands

- `/subtitle_dub_status`
- `/tool_test_asr`
- `/tool_test_video_subtitle`
- `/tool_test_subtitle_generate`
- `/tool_test_subtitle_translate`
- `/tool_test_video_dub`
- `/tool_test_minimax_dub`
- `/tool_test_subtitle_plus_dub`
- `/subtitle_public_open`
- `/subtitle_translate_public_open`
- `/dub_public_open`
- `/subtitle_dub_public_open`
- `/dub_public_close`

## Gates

Each public mode requires:

- feature flag ON
- public flag ON
- required provider present
- admin smoke PASS

No public mode charges Xu before final confirmation.
