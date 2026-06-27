# P0.18A Voice + Subtitle + Dub Audit

Branch: `hotfix/p0-18a-voice-subtitle-dub-final-repair`
Base inspected: latest `origin/main` after B14.5 (`e9f8dbe` or newer)
Date: 2026-06-27

## Scope

This audit covers only voice, subtitle, translation, and dubbing entry points needed for P0.18A. B13 video render/stitch, B14.5 video order/backstack, PayOS/wallet/payment, Suno/music core, and web/app are out of scope and must not be changed.

## Current Voice Entry Points

- Public Studio am thanh uses `music_quick|...` callbacks and `voice_profiles` helpers:
  - `music_quick|showroom|voice_seed`
  - `music_quick|showroom|voice_custom`
  - `music_quick|showroom|voice_clone`
  - `music_quick|showroom|voice_profiles`
  - `music_quick|showroom|voice_profiles_page:<page>`
- B14.5 video add-ons voice screen:
  - `vproduct|b14_addon_voice`
  - `vproduct|b14_voice_source|none`
  - `vproduct|b14_voice_source|default_male`
  - `vproduct|b14_voice_source|default_female`
  - `vproduct|b14_voice_source|uploaded`
  - `vproduct|b14_voice_source|saved`
  - `vproduct|b14_voice_edit`
  - `vproduct|b14_voice_preview`
  - `vproduct|b14_voice_done`
  - `vproduct|b14_voice_volume`
  - `vproduct|b14_voice_volume_set|<percent>`
- Video dubbing voice screen:
  - `videodub|voice|default_female`
  - `videodub|voice|default_male`
  - `videodub|voice_saved`
  - `videodub|voice_library`
  - `videodub|voice_profile|<display_code>`
  - `videodub|voice_profile_page|<page>`
  - `videodub|voice_create`
  - `videodub|back_voice`

## Current Subtitle / Translate / Dub Entry Points

- Translation/subtitle/dubbing menu:
  - `videodub|start`
  - `videodub|start|video_addon`
  - `videodub|start|translation`
  - `videodub|type|subtitle_create`
  - `videodub|type|subtitle_translate`
  - `videodub|type|dub`
  - `videodub|type|subtitle_plus_dub`
  - `videodub|type|subtitle_file_translate`
  - `videodub|type|transcript`
- Source and link intake:
  - `videodub|source_upload`
  - `videodub|source_recent_subtitle`
  - `videodub|source_current_video`
  - `videodub|link_start`
  - `videodub|link_confirm`
  - `videodub|link_other`
  - `videodub|link_upload_direct`
  - `videodub|link_status|<id>`
- Language:
  - `videodub|language|Tiếng Việt`
  - `videodub|language|English`
  - `videodub|language|中文`
  - `videodub|language|日本語`
  - `videodub|language|한국어`
  - `videodub|language_custom`
  - `videodub|language_strategy|original`
  - `videodub|language_strategy|translate`
- Subtitle + dub combined:
  - `videodub|combo_translate`
  - `videodub|combo_dub_original`
  - `videodub|combo_dub_translated`
  - `videodub|combo_full_dub`
  - `videodub|combo_download_original_srt`
  - `videodub|combo_view_original_transcript`
  - `videodub|combo_download_final_video`
  - `videodub|combo_download_final_audio`
  - `videodub|combo_download_final_subtitle`
  - `videodub|combo_retry_mux`
  - `videodub|combo_redub_voice`
  - `videodub|combo_back_original`
  - `videodub|combo_back_subtitle_ready`
  - `videodub|combo_back_voice`
- Final/output:
  - `videodub|final`
  - `videodub|confirm_subtitle_create`
  - `videodub|confirm_subtitle_translate`
  - `videodub|confirm_dub`
  - `videodub|confirm_subtitle_plus_dub`
  - `videodub|output|srt`
  - `videodub|output|audio`
  - `videodub|output|video`
  - `videodub|output|video_subtitle`
  - `videodub|download_final_video`
  - `videodub|download_final_audio`
  - `videodub|download_final_subtitle`

These old callbacks must remain compatible.

## Current Provider Calls

- MiniMax/custom voice:
  - Settings and endpoints are defined in `bot.py` with `MINIMAX_*`, `SHOPAIKEY_*`, and `KEY4U_*`.
  - Clone/upload calls are in the voice studio section around the MiniMax/Key4U helpers.
  - Default voice helpers are `default_tts_voice_id()`, `default_tts_voice_map()`, and `get_tts_voice_id()`.
- TTS:
  - `video_dubbing_tts_bytes()` resolves default/custom voice and calls existing TTS providers.
  - `synthesize_dub_segment_chunks()` and subtitle+dub preview/full routes use TTS bytes.
- STT/ASR:
  - `video_dubbing_transcribe_bytes()` is the central video/audio transcript route.
  - `video_dubbing_prepare_subtitles()` and helper flows use ASR to produce segments/SRT.
- Translation:
  - `video_dubbing_translate_current_subtitle_to_output()` translates current SRT/transcript and preserves timing.
- FFmpeg mux:
  - `services/dubbing_pipeline.py` already has `mux_final_video()`, `render_subtitled_video()`, `mux_dubbed_video()`, `process_final_video_product()`, and `process_dubbing_pipeline()`.
  - It returns `audio_fallback` when mux fails but dubbed audio exists.

## Current DB Fields / Tables

- `voice_profiles`:
  - `id`, `user_id`, `provider`, `provider_voice_id`, `display_name`, `consent_status`, `source_file_id`, `source_file_ref`, `preview_audio_ref`, `status`, `is_default`, timestamps, `deleted_at`, `metadata_json`.
- `voice_assets`:
  - `voice_asset_id`, `user_id`, `source_feature`, `product_context`, `voice_kind`, `text_hash`, `duration_seconds`, `output_bytes`, `file_ref`, `file_id`, `local_path`, `status`, `linked_video_session_id`, timestamps.
- B14.5 video queue:
  - `video_projects.addon_plan_json` stores the selected add-ons.
  - `video_jobs` stores confirmed worker jobs and is claimed by `services.video_project_queue`.
- Runtime pending state:
  - `USER_PENDING["video_dubbing:<user_id>"]` stores subtitle/dub state, including `voice_id`, `voice_kind`, `voice_profile_id`, `target_language`, `subtitle_ref`, `translated_subtitle_ref`, final artifact refs, and current step.

## Broken / Weak Points Found

- Provider call rules are spread across UI handlers and engine wrappers; there is no single provider/no-charge gate for voice, subtitle, translate, and dub.
- B14.5 video add-ons voice stores `voice_source` but does not consistently store a resolved `voice_provider_voice_id`.
- B14.5 video add-ons do not have a first-class `dub_enabled` / `dub_target_language` plan entry, so invoice/status cannot show lồng tiếng clearly.
- `vproduct|b14_voice_source|saved` currently selects the generic source and does not list saved voices by friendly name.
- `vproduct|b14_voice_source|uploaded` can be selected even if no uploaded/created voice has a provider voice id ready.
- Narration exists via `video_b14_narration_from_storyboard()`, but empty/manual/storyboard source status is not explicit enough for validation and tests.
- `vproduct|b14_voice_preview` is safe because it does not call providers, but there is no reusable preview policy guard.
- Subtitle helpers exist in `bot.py`, but P0.18A needs a pure service layer for storyboard/narration to transcript/SRT, SRT validation, translation timestamp preservation, and mux partial-result behavior.
- Public-safe copy is inconsistent in older guard/admin messages. Public P0.18A copy must avoid provider/API/endpoint/MiniMax/FFmpeg/mux/worker terminology.

## Safe To Reuse

- B14.5 video flow order and callbacks: profile -> idea/assets -> creative -> storyboard -> add-ons -> aspect -> package -> scene count -> invoice -> confirm -> status.
- `video_b14_narration_from_storyboard()` as the base narration source, with additional source validation.
- `default_tts_voice_id()` and `get_tts_voice_id()` for default male/female voice ids.
- `voice_profile_can_generate_tts()`, `user_voice_profile_rows()`, `user_voice_profile_by_display_code()`, and `list_saved_voice_profiles_for_tts()` for saved voice readiness.
- `services/dubbing_pipeline.py` FFmpeg mux and partial fallback behavior.
- Existing `videodub|...` public/admin callback set and B12.5 public lock behavior.

## Must Be Repaired In P0.18A

- Add central `services/provider_gate.py` with public/admin contexts and safe public messages.
- Add `services/minimax_voice_adapter.py` to normalize voice id, reject missing provider ids, synthesize to a real non-empty audio artifact through injected/real TTS functions, and return safe errors.
- Add `services/subtitle_dub_pipeline.py` with pure transcript/SRT/translation/dub artifact utilities.
- Extend B14.5 `addon_plan` with voice provider id, saved/uploaded voice profile fields, subtitle target language, and dub plan fields.
- Update B14.5 voice add-on menu labels and callback handling without changing the B14.5 flow order/backstack.
- Ensure B14.5 invoice/status surfaces voice/subtitle/dub plan but still only queues provider work after final confirm.
- Add admin smoke commands for voice gate, adapter, voice vault lookup, subtitle from storyboard, full subtitle+dub fake files, and mux failure fake files.

## Not Touched By Audit

- PayOS/wallet/payment/Xu ratio.
- B13 render/stitch engine.
- Suno/music core.
- Web/app/standalone.
- DB destructive migration.
