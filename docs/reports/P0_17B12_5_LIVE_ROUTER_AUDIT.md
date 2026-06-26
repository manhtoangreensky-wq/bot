# P0.17B12.5 Live Router Audit

Base: `43c4bede263cb5895c8cf12a5d2978c9639119bc`

Scope: Telegram router, public gates, and confirm-only product flow for Translation / Subtitle / Dubbing Studio.

No engine/provider work was added in this audit.

## A. Dịch phụ đề / video

- Visible live text observed: `TOAN AAS chưa thể dịch phụ đề lúc này. Hệ thống chưa xử lý file và chưa trừ Xu.`
- Menu entry callback: `videodub|type|subtitle_translate`
- Handler: `handle_video_dubbing_callback`
- Media handler: `handle_media_cache_only -> handle_video_dubbing_pending_upload`
- Language callback: `videodub|language|<target>`
- Confirm/export callback: `videodub|final`
- State keys: `pending_action=video_dubbing`, `mode=subtitle_translate`, `active_flow=subtitle_translate`, `step=source|await_video|language|confirm|processing`
- Old direct processing path: language callback could call `video_dubbing_translate_current_subtitle_to_output` in a branch with media, and upload path routed through preparation helpers before a final confirm screen in some states.
- Bypassed confirm: yes, in old live route after language/media state.
- Fixed route: upload only stores Telegram media ref, then asks language; language choice only stores `target_language` and shows confirm; only `videodub|final` may call `execute_video_dubbing_pipeline`.

## B. Lồng tiếng / Voice video

- Visible live text observed: `TOAN AAS chưa tạo được phụ đề từ file này...`
- Menu entry callback: `videodub|type|dub`
- Handler: `handle_video_dubbing_callback`
- Media handler: `handle_media_cache_only -> handle_video_dubbing_pending_upload`
- ASR/subtitle extraction callbacks: previous route reached `video_dubbing_create_dub_source_subtitle_then_next` and later `video_dubbing_prepare_subtitles`
- Voice callbacks: `videodub|voice|default_female`, `videodub|voice|default_male`, `videodub|voice_saved`, `videodub|voice_create`
- Confirm/export callback: `videodub|final`
- State keys: `mode=dub`, `active_flow=dub_audio`, `step=source|await_video|language|voice|voice_speed|confirm|processing`
- Old direct processing path: public user could enter the voice-video flow and upload media, causing ASR/subtitle extraction before the product was stable.
- Bypassed confirm: yes, public upload could trigger subtitle preparation/failure before final confirm.
- Fixed route: normal users are hard-gated by `PUBLIC_VOICE_VIDEO_ENABLED=false`; the guard sends no provider/ASR call and no Xu charge. Admin bypass keeps test access.

## C. Phụ đề + Lồng tiếng

- Visible live text observed: public upload tried ASR immediately and failed before confirm.
- Menu entry callback: `videodub|type|subtitle_plus_dub`
- Handler: `handle_video_dubbing_callback`
- Media handler: `handle_media_cache_only -> handle_video_dubbing_pending_upload`
- Language callbacks: `videodub|combo_translate`, `videodub|language|<target>`
- Voice callbacks: `videodub|combo_dub_original`, `videodub|combo_dub_translated`, `videodub|voice|...`
- Confirm/export callback: `videodub|combo_full_dub` for advanced combo path, `videodub|final` for unified final path
- State keys: `mode=subtitle_plus_dub`, `requested_mode=subtitle_plus_dub`, `active_flow=subtitle_plus_dub`, `step=waiting_media|original_subtitle_ready|choosing_translation_language|translated_subtitle_ready|choosing_voice|dub_confirmation`
- Old direct processing path: `handle_video_dubbing_pending_upload` called `subtitle_plus_dub_create_original_from_media` immediately when public media arrived.
- Bypassed confirm: yes, ASR/subtitle creation started on upload.
- Fixed route: normal users are hard-gated by `PUBLIC_SUBTITLE_DUB_ENABLED=false`; upload, language, voice, and combo callbacks return the clean public guard. Admin bypass keeps advanced flow available.

## D. Tạo phụ đề tự động

- Visible live text expected after B12.5: `Gửi video/audio cần tạo phụ đề. TOAN AAS chưa xử lý và chưa trừ Xu ở bước này.`
- Menu entry callback: `videodub|type|subtitle`
- Handler: `handle_video_dubbing_callback`
- Media handler: `handle_media_cache_only -> handle_video_dubbing_pending_upload`
- Confirm/export callback: `videodub|final`
- State keys: `mode=subtitle`, `active_flow=auto_subtitle`, `step=source|await_video|confirm|processing`
- Old editor/SRT path: public result/editor callbacks existed but were hidden from the main flow; advanced editor remains admin-only.
- Bypassed confirm: fixed in current route; upload stores media and shows `✅ Xuất video phụ đề`.
- Fixed route: no ASR runs on upload. ASR/subtitle/render only run after final confirm.

## Public Gates Added

- `PUBLIC_CUSTOM_VOICE_ENABLED=false`
- `PUBLIC_VOICE_VIDEO_ENABLED=false`
- `PUBLIC_SUBTITLE_DUB_ENABLED=false`

Admin bypass:

- `is_admin_user(user_id)` bypasses public gates.
- Admin entry state uses `entry_surface=admin_test_mode`.
- Admin-only status command: `/translation_voice_gate_status`.

## Hidden From Public Main Flow

- SRT/VTT/TXT upload button in public translate flow
- Voice video processing when public gate is closed
- Subtitle + dubbing processing when public gate is closed
- Custom voice / MiniMax voice clone public route
- Subtitle editor and line editing actions
- Preview/editor actions that open public manual editing

## Final Fixed Routes

- Auto subtitle: `type -> source/await_video -> upload stores ref -> confirm -> final processes`
- Translate subtitle/video: `type -> source/await_video -> upload stores ref -> language -> confirm -> final processes`
- Voice video public: `type/upload/callback -> clean guard -> no ASR/TTS/mux`
- Subtitle + dub public: `type/upload/callback -> clean guard -> no ASR/translate/TTS/mux`
- Admin voice/combo/custom voice: allowed through admin test mode.
