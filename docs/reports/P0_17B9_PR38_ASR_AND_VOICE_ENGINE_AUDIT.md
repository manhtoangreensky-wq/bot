# P0.17B9 PR38 ASR + Voice/TTS Engine Audit

Date: 2026-06-26

Branch: `hotfix/p0-17b9-pr38-asr-voice-engine`

Base: latest `main` after PR #48, merge commit `221ee7f763915c3702616667b64770d04c81e84d`

PR38 reference audited: `c4fa82079636d68bb9c0cd5ff2d6018be2a7513e` (`Merge pull request #38 from hotfix/p0-17b4-studio-routing-separation`)

## Scope Lock

Changed only subtitle/dub/voice engine stability surfaces:

- `bot.py` ASR failure recovery, dialogue-text fallback, TTS readiness, TTS failure copy/keyboard.
- Smoke tools for subtitle ASR, standalone TTS, subtitle-file dubbing.
- B9 tests and small fixtures.

Not touched:

- PayOS, wallet, payment, pricing.
- Music/Suno.
- Image menu, video menu, image-to-video, multiscene.
- Custom voice clone internals.
- Web/app/standalone.

## PR38 ASR Path

The restored path remains:

1. Telegram media/file is downloaded through `video_dubbing_download_source`.
2. Video media goes through `video_dubbing_extract_audio` before ASR.
3. Audio bytes go to `video_dubbing_transcribe_bytes`.
4. Empty ASR output is rejected by `video_dubbing_prepare_subtitles` with `subtitle_segments_empty`.
5. Non-empty segments are normalized into SRT/VTT/TXT via `video_dubbing_srt_from_segments` and `video_dubbing_subtitle_output_items`.

B9 keeps that route and adds a clean user recovery when the real ASR provider is unavailable or returns no segments:

- Retry media.
- Send existing SRT/VTT/TXT.
- Enter dialogue text.
- Back.
- Main menu.

The new dialogue-text fallback creates timed subtitle segments from text, stores `subtitle_ref` and `source_subtitle_ref`, and routes to the exact selected tool:

- Auto subtitle -> output selection.
- Translate subtitle -> language selection.
- Voice/dub -> language or voice step.
- Subtitle + dub -> original subtitle ready screen.

This fallback does not charge Xu and does not fake ASR.

## Voice/TTS Engine

Added `get_tts_provider_readiness(public=False)` with the required contract:

- `ready`
- `provider`
- `model`
- `supported_voices`
- `default_female_voice_id`
- `default_male_voice_id`
- `reason`

The readiness checks real routes without exposing secrets:

- Key4U MiniMax TTS.
- ShopAIKey MiniMax TTS.
- Direct MiniMax TTS.
- ShopAIKey `/audio/speech`.
- Edge TTS fallback.

`_product_engine_readiness("voice_tts")` now consumes this contract, so voice gate decisions are based on actual TTS routes instead of scattered MiniMax-only checks. If Edge/default TTS is available, missing MiniMax env no longer blocks the whole voice engine.

Public failure copy is now fixed:

`TOAN AAS chưa tạo được giọng đọc lúc này. Hệ thống chưa trừ Xu. Anh/chị có thể thử lại hoặc đổi giọng khác.`

Provider-not-called guard copy is now fixed:

`Giọng đọc AI đang được chuẩn bị. TOAN AAS chưa gọi provider và chưa trừ Xu. Anh/chị có thể thử lại sau hoặc dùng công cụ khác trước.`

Failure keyboard includes:

- Retry.
- Change voice.
- Edit content.
- Back.
- Main menu.

## Smoke Policy

B9 smoke scripts do not report fake PASS:

- If a real provider output exists, status is `PASS`.
- If provider is missing, blocked, or network access is unavailable, status is `CLEAN_GUARD`.
- `CLEAN_GUARD` is a safe no-charge result, not a live/provider pass.
- Paid provider calls require `--confirm-paid`.

## Local Smoke Results

Command:

`python tools/smoke_subtitle_pipeline.py --input tests/fixtures/short_clear_voice.mp4 --no-charge`

Result:

- `status`: `CLEAN_GUARD`
- `reason`: `asr_adapter_missing`
- `asr_called`: `false`
- `segments`: `0`
- `no_charge`: `true`

Command:

`python tools/smoke_tts_pipeline.py --text "Xin chào, đây là kiểm tra giọng đọc TOAN AAS." --voice default_female --preview --no-charge`

Result:

- `status`: `CLEAN_GUARD`
- `provider`: `edge_tts`
- `reason`: local sandbox denied network access to `speech.platform.bing.com:443`
- `output_audio_exists`: `false`
- `no_charge`: `true`

Command:

`python tools/smoke_subtitle_dub_pipeline.py --subtitle tests/fixtures/sample_vi.srt --voice default_female --preview --no-charge`

Result:

- `status`: `CLEAN_GUARD`
- `provider`: `edge_tts`
- `segments`: `3`
- `reason`: `tts_unavailable:Edge TTS=FAIL`
- `output_audio_exists`: `false`
- `no_charge`: `true`

Local smoke therefore proves clean no-charge guards and no fake output. It does not prove live ASR/TTS provider success in this sandbox because ASR credentials are absent and Edge network access is blocked.

## Tests Added

- `tests/test_p0_17b9_pr38_asr_voice_engine.py`
- `tests/fixtures/sample_vi.srt`
- `tools/smoke_tts_pipeline.py`
- `tools/smoke_subtitle_dub_pipeline.py`

Key assertions:

- TTS readiness contract has real default female/male IDs.
- Voice engine gate uses the TTS readiness contract.
- Required public TTS guard/failure copy is present.
- ASR failure keyboard includes dialogue-text fallback.
- Dialogue text creates stored timed subtitle refs and routes by selected tool.
- Subtitle-file dubbing preview receives segment texts, not raw whole SRT.
- Subtitle smoke no longer contains fake ASR stubs.

## LIVE PASS

LIVE PASS claimed: NO.

Manual Telegram QA and deploy were not run in this task.
