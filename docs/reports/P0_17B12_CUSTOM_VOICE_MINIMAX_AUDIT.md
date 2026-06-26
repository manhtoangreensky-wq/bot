# P0.17B12 Custom Voice MiniMax Audit

Branch: `hotfix/p0-17b12-final-product-flow-fix`

Scope:
- Custom voice runtime selection for subtitle/dubbing TTS.
- MiniMax/user voice ID fallback.
- Voice guard keyboards.
- Blackbox dubbing/mux module.

Not touched:
- PayOS, wallet, payment, pricing.
- Music/Suno.
- Image menu, video main menu, image-to-video, multiscene.
- Web/app/standalone.
- Destructive DB migrations.

## Findings

- Default voice generation already produced real MP3 output and remains locked.
- Custom voice clone/provider readiness is guarded before provider calls; fake ready profiles are not created by the new blackbox helper.
- The practical runtime issue was voice selection for dubbing: TTS could receive `default_female`, `saved_voice`, or an empty marker instead of a provider `voice_id`.
- `services/dubbing_pipeline.get_user_voice_id()` now resolves a real active default `voice_profiles.provider_voice_id` when no valid explicit provider voice is supplied, and safely falls back to configured default voice IDs when the profile table is missing or empty.
- `bot.py` now resolves the voice ID before segment TTS in the dub pipeline through `resolve_video_dub_tts_voice_id()`.

## Blackbox Engine

- Added `services/dubbing_pipeline.py`.
- It has no Telegram imports and does not charge Xu.
- `mux_final_video()` validates input files, uses `subprocess.run()` with list args, never uses `shell=True`, replaces audio by default, burns subtitles only when requested, and verifies output MP4 bytes.
- `process_dubbing_pipeline()` writes intermediate audio/subtitle/video files inside a caller workspace and returns a structured result instead of sending Telegram messages.
- `cleanup_workspace()` removes only files inside the given workspace.

## Voice UX

- Voice clone/provider guard keyboard is now two-column:
  - `🎙 Dùng giọng nữ mặc định | 🎙 Dùng giọng nam mặc định`
  - `🔁 Thử lại sau | ⬅️ Kho voice`
  - `🏠 Menu chính`
- Failed voice profile keyboard is now two-column:
  - `🔁 Tạo/nghe thử lại | ✏️ Đổi tên`
  - `🗑 Xóa | ⬅️ Kho voice`
  - `🏠 Menu chính`

## Remaining Operational Notes

- Smoke scripts clean-guard instead of claiming pass when fixture media, fixture TTS audio, or FFmpeg are missing.
- No deploy or live pass was claimed in this change.
