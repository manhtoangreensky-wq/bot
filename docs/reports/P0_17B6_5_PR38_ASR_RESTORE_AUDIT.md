# P0.17B6.5 PR38 ASR Restore Audit

Base: `origin/main` after PR #46, commit `089d47410e6625fb5cd1cff9dded6784e89c1474`.

Known working reference: PR #38 merge commit `c4fa82079636d68bb9c0cd5ff2d6018be2a7513e`.

Branch: `hotfix/p0-17b6-5-pr38-asr-engine-restore`.

Deploy: NO. LIVE PASS claimed: NO.

## PR38 ASR Path Restored

PR38 working media-to-subtitle path:

1. `handle_video_dubbing_pending_upload`
2. `video_dubbing_prepare_subtitles`
3. `video_dubbing_download_source`
4. `video_dubbing_resolve_source_script`
5. `transcribe_media_to_segments`
6. `video_dubbing_extract_audio` for video
7. `video_dubbing_transcribe_bytes` / `asr_transcribe_audio`
8. `video_dubbing_srt_from_segments`

Current restored files/functions:

- `bot.py:132804` restores Telegram bytearray-first download in `video_dubbing_download_source`, matching PR38 behavior before falling back to temp file download.
- `bot.py:133277` keeps media routing in `video_dubbing_resolve_source_script` and now passes `file_name` plus `media_kind` into `transcribe_media_to_segments`.
- `bot.py:133887` keeps `video_dubbing_prepare_subtitles` as the shared source-subtitle engine, requires non-empty timestamped segments, stores both `subtitle_ref` and `source_subtitle_ref`, and clears stale refs on new upload.
- `bot.py:134750` adds the missing "Lồng tiếng / Voice video" media path: upload media -> create original subtitle by ASR -> ask language/voice/speed/confirm as appropriate.
- `bot.py:135152` routes current 6-tool Studio upload actions into the restored engine by button-selected mode, not by generic video/audio auto pipeline.

## Root Cause

Observed live failure:

- `🎬 Phụ đề + Lồng tiếng` and `🌐 Dịch phụ đề / video` reached "TOAN AAS đang tạo phụ đề gốc từ video/audio..." then failed with the public subtitle failure copy.

Confirmed causes:

- Current download path preferred `download_to_drive`; PR38 used `download_as_bytearray`. Restored bytearray-first behavior reduces Telegram file/temp path drift.
- `video_dubbing_resolve_source_script` dropped `source_file_name` and `media_kind` when calling `transcribe_media_to_segments`. Telegram files with `application/octet-stream` could be rejected as unsupported even when the file was `.mp4` or audio.
- New uploads could retain stale `subtitle_ref` from a previous pending state. New upload handling now clears `subtitle_ref`, `source_subtitle_ref`, and `translated_subtitle_ref`.
- `Lồng tiếng / Voice video` could skip original subtitle creation and jump directly to language selection. It now creates a real source subtitle first.

## Current UI Proof

The public 6-tool Studio UI is unchanged. The upload handler branches by the selected tool:

- `Tạo phụ đề tự động`: upload -> ASR source subtitle -> output screen with SRT/VTT/TXT.
- `Dịch phụ đề / video`: upload -> ASR source subtitle -> language prompt -> translation output only after translated subtitle exists.
- `Lồng tiếng / Voice video`: upload -> ASR source subtitle -> language prompt -> voice -> speed -> confirm.
- `Phụ đề + Lồng tiếng`: upload -> ASR source subtitle -> original subtitle ready screen -> translate/voice steps.
- `Transcript / Bóc lời`: upload -> ASR source subtitle -> TXT output default.
- `Dịch file phụ đề`: subtitle file only, no video/audio hijack.

## Output/Charging Policy

- No Xu is charged during upload, ASR, language selection, subtitle preview, or source subtitle creation.
- Final charge remains inside confirmed execution path after output validation.
- Public ASR failure copy remains friendly and has no provider/API/env/ffmpeg/internal terms.
- Subtitle success requires non-empty segments before SRT/VTT/TXT can be treated as ready.

## Tests Added/Updated

Added:

- `tests/test_p0_17b6_5_pr38_asr_restore.py`
  - PR38 bytearray download before ASR.
  - Video extract audio before ASR, including `application/octet-stream` + `.mp4`.
  - Subtitle + dub media upload calls restored ASR path.
  - Subtitle translate media upload calls restored ASR path.
  - Auto subtitle media upload calls restored ASR path and exposes SRT/VTT/TXT.
  - Dub media upload calls restored ASR path before language.
  - Non-empty segments required.
  - Transcript uses ASR and defaults to TXT.
  - No charge before final confirm.
  - Public failure copy has no provider terms.

Updated:

- `tests/test_p0_3_translation_canonical_flow.py`
- `tests/test_task2_3_public_ui_lock_translation.py`

Added local smoke:

- `tools/smoke_subtitle_pipeline.py`
- `tests/fixtures/short_clear_voice.mp4`

Smoke command:

```bash
python tools/smoke_subtitle_pipeline.py --input tests/fixtures/short_clear_voice.mp4 --no-charge
```

Result in this branch: PASS with Telegram download, audio extract, ASR call, segments, SRT/VTT/TXT, and no charge.

## Validation Run

- `py_compile bot.py`: PASS
- `py_compile local_worker.py`: PASS
- `py_compile providers/key4u_provider.py`: PASS
- Targeted pytest: PASS, `22 passed`
- Smoke subtitle pipeline: PASS
- Full `pytest -q`: PASS, `1765 passed, 1 warning`
- `git diff --check`: PASS
- `git status --short --untracked-files=no`: tracked changes only in scoped files before commit

## Not Touched

- PayOS: not touched.
- wallet/payment/topup: not touched.
- music/Suno: not touched.
- custom voice clone: not touched.
- multiscene: not touched.
- pricing/image pricing: not touched.
- web/app/standalone: not touched.
- deploy/runtime: not touched.
