# P0.19B.1 Subtitle Dub Live Wiring Audit

## Scope

- Branch: `hotfix/p0-19b1-subtitle-dub-live-wiring-command-fix`
- Base: latest `origin/main` after P0.19B merge (`97bb699` or newer)
- Scope kept to subtitle/dub live wiring, admin command handlers, uploaded subtitle language routing, and smoke coverage.
- Not touched: PayOS, wallet/Xu/payment core, B13 render/stitch engine, VPS worker W1-W5, voice provider core, Suno/music core, web/app/standalone.

## Handlers

- `cmd_tool_test_subtitle_from_storyboard`
  - Admin-only fake SRT smoke.
  - Uses `admin_tool_test_has_flag()` so `--fake` works when registered through `MessageHandler`.
  - Output now reports transcript, real SRT artifact, timestamp validation, provider NO, and PASS/FAIL.
- `cmd_tool_test_subtitle_dub_mux_failure`
  - Admin-only fake-files mux failure smoke.
  - Uses `admin_tool_test_has_flag()` so `--fake-files` works when registered through `MessageHandler`.
  - Output now reports transcript/SRT PASS, dub audio PASS, mux MP4 FAIL as expected, partial audio/SRT availability, provider NO, and PASS/FAIL.
- `cmd_tool_test_uploaded_video_subtitle_guard`
  - Admin-only fake uploaded-video guard smoke.
  - Uses the uploaded translate language route helper to verify state preservation, language routing, confirm/lock gate, no provider before confirm, no charge before confirm, safe public copy, and PASS/FAIL.
- `cmd_tool_test_subtitle_dub_live_wiring`
  - New admin-only fake smoke.
  - Registered through `MessageHandler` because the command name is longer than the Telegram command-handler comfort limit.
  - Covers uploaded video state, language route, confirm/locked guard, storyboard SRT, mux failure partial result, no provider before confirm, no charge before confirm, command handler execution, safe public copy.

## Why Usage Happened

- Long admin commands were registered as `MessageHandler(filters.Regex(...))`, not `CommandHandler`.
- Telegram `context.args` is populated by `CommandHandler`; with `MessageHandler`, `context.args` can be empty even when the text contains `--fake` or `--fake-files`.
- The handlers checked only `context.args`, so valid live commands fell back to usage text.
- Fix: `admin_tool_test_args()` falls back to parsing `update.message.text` after the command token. The three existing long handlers and the new long handler use this parser.

## Uploaded Video Callback Path

- User picks subtitle translation from `videodub|type|subtitle_translate`.
- `set_video_dubbing_pending()` stores mode/process/source metadata.
- User sends video/audio/SRT/VTT/TXT.
- `handle_video_dubbing_pending_upload()` stores:
  - `source_file_id`
  - `video_file_id` for media uploads
  - `source_file_name`
  - `source_mime_type`
  - `media_kind`
  - `source_kind`
  - `video_message_id`
- If no target language exists, the flow opens language selection through `video_dubbing_create_original_subtitle_then_language()` without provider calls.
- Language callbacks are handled by `handle_video_dubbing_callback()` under `action == "language"`.

## Language Selection

- `videodub|language|<target>` now preserves the existing upload state.
- For uploaded media in public translate-subtitle mode, the callback routes through `video_dubbing_uploaded_translate_language_route()`.
- If the state is missing or expired, the recovery screen says:
  - `TOAN AAS chưa tìm thấy file cần xử lý. Anh/chị gửi lại video hoặc file phụ đề giúp em.`
- Recovery buttons:
  - send file again
  - back
  - main menu

## State Key Storing Upload

- Pending state key: `video_dubbing_pending:<user_id>` via `video_dubbing_pending_key()`.
- Upload references:
  - `source_file_id`
  - `video_file_id`
  - `source_file_ref`
  - `source_file_name`
  - `source_mime_type`
  - `source_kind`
  - `media_kind`
- Subtitle file source detection uses `video_dubbing_is_subtitle_text_source()` for `.srt`, `.vtt`, `.txt`, and subtitle/text MIME types.

## Confirm Gate

- Supported subtitle files (`SRT/VTT/TXT`) enter confirm gate and keep timestamps.
- Public uploaded video/audio translation uses a clear quality lock if ASR/translation readiness is missing before confirm.
- Locked message:
  - `Tính năng dịch phụ đề từ video tải lên đang tạm khóa để kiểm soát chất lượng. TOAN AAS chưa xử lý file và chưa trừ Xu. Anh/chị có thể gửi file SRT/VTT/TXT có sẵn để dịch phụ đề trước.`
- Confirmation screen title:
  - `🌐 Xác nhận dịch phụ đề`
- Confirmation screen includes:
  - file received
  - target language
  - translation form
  - no processing/no Xu at this step
- No ASR, translate, TTS, mux, provider, or charge call is made before final confirm.

## What Fixed

- Long admin command flags now execute instead of returning usage.
- Uploaded video subtitle language selection no longer drops to the generic dead message.
- Uploaded video state is preserved through language selection.
- Missing state now has a clear recovery path.
- Uploaded subtitle files can enter a confirm gate instead of being rejected by the public video-only copy.
- Public uploaded video/audio remains locked with clear quality-control copy if provider readiness is not sufficient.
- Admin smoke tests cover command execution, uploaded language route, storyboard SRT generation, mux-failure partial result, no provider before confirm, and no charge before confirm.

## Safe Admin Test Path

- `/tool_test_subtitle_from_storyboard --fake`
- `/tool_test_subtitle_dub_mux_failure --fake-files`
- `/tool_test_uploaded_video_subtitle_guard --fake`
- `/tool_test_subtitle_dub_live_wiring --fake`
- These paths are admin-only and do not call external providers or deduct Xu.
