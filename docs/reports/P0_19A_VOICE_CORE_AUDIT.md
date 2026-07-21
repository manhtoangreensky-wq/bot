# P0.19A Voice Core Audit

Base: `origin/main` at `5e7cb74`
Branch: `hotfix/p0-19a-voice-core-final-repair`
Deploy status: not deployed
LIVE PASS claimed: NO

## Default Male/Female Source

- Default female resolves through `default_tts_voice_id("female")`, backed by `DEFAULT_TTS_FEMALE_VOICE` / `MINIMAX_DEFAULT_FEMALE_VOICE_ID`, with fallback key `female-shaonv`.
- Default male resolves through `default_tts_voice_id("male")`, backed by `DEFAULT_TTS_MALE_VOICE` / `MINIMAX_DEFAULT_MALE_VOICE_ID`, with fallback key `male-qn-qingse`.
- `video_b14_voice_resolution()` passes these values into `services/minimax_voice_adapter.resolve_provider_voice_id()`.
- Default TTS output still uses the existing no-charge default/free route and validates real nonzero audio bytes before success.

## Saved Voice DB/Table/Fields

Saved/custom voice profiles are stored in `voice_profiles`.

Key fields:

- `id`: local profile id. This must never be sent as provider voice id.
- `user_id`: owner.
- `provider`: provider route label.
- `provider_voice_id`: real provider voice id required for saved/uploaded TTS.
- `display_name`: friendly name shown in menus.
- `source_file_id`, `source_file_ref`: Telegram/source upload reference.
- `preview_audio_ref`: optional preview/demo audio reference.
- `status`: `active`, `ready`, or `saved` can generate TTS.
- `metadata_json`: sanitized metadata for clone/activation flow.
- `deleted_at`: soft-delete marker.

Saved/generated audio artifacts are stored in `voice_assets`.

Key fields:

- `voice_asset_id`, `source_feature`, `product_context`, `voice_kind`.
- `duration_seconds`, `output_bytes`, `file_ref`, `file_id`, `local_path`.
- `status`, `linked_video_session_id`, `metadata_json`.

## Uploaded Voice Source

- Uploaded voice starts from Telegram audio/voice through `save_user_voice_profile()`.
- Upload source is recorded in `source_file_id` / `source_file_ref`.
- Uploaded voice is usable for TTS only after the provider clone/create path stores a real `provider_voice_id` and marks status ready/active/saved.
- `video_b14_uploaded_voice_profiles()` filters uploaded profiles with source refs and final-ready provider ids.

## Provider Voice ID Mapping

- `services/minimax_voice_adapter.resolve_provider_voice_id()` is the core resolver for default, saved, uploaded, and direct provider voice keys.
- Saved/uploaded voice resolution requires `provider_voice_id`.
- Saved/uploaded voice resolution rejects an empty provider id and rejects a provider id that is only the same as the local profile `id`.
- `send_paid_saved_voice_tts_result()` continues to pass `profile["provider_voice_id"]` into `execute_engine("voice_saved_tts", ...)`.
- `synthesize_text_to_audio()` normalizes provider voice ids, rejects missing/placeholder values, calls the TTS function with the provider id, writes output, and validates a nonzero audio file before returning success.

## Custom Voice Create Path

- Public/custom clone UI path: `music_quick|...|voice_clone` and clone step callbacks.
- Clone execution path: `create_minimax_voice_profile_preview()` -> `execute_engine("voice_clone", ...)` -> provider route attempts.
- Readiness source: `get_minimax_voice_clone_readiness()`.
- P0.19A adds `custom_voice_core_state()` so callers can clearly model ready vs locked.
- Locked state has safe fallback copy and default male/female or saved voice fallback; it does not claim success and does not charge.

## Preview Path

- Voice preview policy uses `voice_core_preview_policy()` and `services/minimax_voice_adapter.voice_preview_policy()`.
- Silent preview is blocked: preview must be explicit.
- Preview is short: capped by `voice_preview_seconds()` with adapter max seconds clamp.
- Preview is no-charge: public copy says no silent Xu charge.
- Provider gate path: `provider_gate.evaluate_provider_gate(context=PREVIEW_CONFIRMED, ...)`.

## Voice-Related Callbacks/Commands

Video B14 voice add-on callbacks:

- `vproduct|b14_voice_source|none`
- `vproduct|b14_voice_source|default_female`
- `vproduct|b14_voice_source|default_male`
- `vproduct|b14_voice_source|uploaded`
- `vproduct|b14_voice_source|saved`
- `vproduct|b14_voice_source|custom`
- `vproduct|b14_voice_saved_pick|<profile_id>`
- `vproduct|b14_voice_edit`
- `vproduct|b14_voice_preview`
- `vproduct|b14_voice_done`
- `vproduct|b14_voice_volume`
- `vproduct|b14_voice_volume_set|<percent>`

Voice showroom / vault / TTS callbacks:

- `music_quick|<context>|voice_hub`
- `music_quick|<context>|voice_tts_text`
- `music_quick|<context>|voice_tts_guard`
- `music_quick|<context>|voice_tts_default_female`
- `music_quick|<context>|voice_tts_default_male`
- `music_quick|<context>|voice_tts_default_neutral`
- `music_quick|<context>|voice_profiles`
- `music_quick|<context>|voice_profile_select_code:<code>`
- `music_quick|<context>|voice_profile_read:<profile_id>`
- `music_quick|showroom|voice_profile_generate:<profile_id>`
- `music_quick|showroom|voice_profile_edit_text:<profile_id>`
- `music_quick|<context>|voice_profile_rename:<profile_id>`
- `music_quick|<context>|voice_profile_delete:<profile_id>`
- `music_quick|<context>|voice_profile_default:<profile_id>`
- `music_quick|<context>|voice_clone`
- `music_quick|<context>|voice_clone_upload`
- `music_quick|<context>|voice_clone_sample_confirm:<profile_id>`
- `music_quick|<context>|voice_clone_name:<profile_id>`
- `music_quick|<context>|voice_clone_confirm:<profile_id>`
- `music_quick|<context>|voice_clone_confirmed:<profile_id>`
- `music_quick|<context>|voice_clone_retry:<profile_id>`
- `music_quick|<context>|voice_clone_full:<profile_id>`
- `music_quick|<context>|voice_clone_guard`

Video final/add-on voice callbacks:

- `vfinal|voice_vault`
- `vfinal|voice_default|female`
- `vfinal|voice_default|male`
- `vfinal|voice`

Subtitle/dub voice callbacks:

- `videodub|voice|default_female`
- `videodub|voice|default_male`
- `videodub|voice_library`
- `videodub|voice_saved`
- `videodub|voice_create`
- `videodub|voice_profile|<code>`
- `videodub|voice_profile_page|<page>`
- `videodub|back_voice`

Admin voice commands:

- `/tool_test_voice_gate`
- `/tool_test_minimax_adapter --fake`
- `/tool_test_voice_vault_lookup`
- `/tool_test_voice_default_tts --fake`
- `/tool_test_voice_preview_policy --fake`
- `/tool_test_custom_voice_flow --fake`
- Existing broader voice commands remain: `/tool_test_minimax_tts`, `/tool_test_voice_tts`, `/tool_test_voice_tts_product`, `/tool_test_minimax_voice_clone`, `/tool_test_voice_clone`, `/voice_engine_status`, `/voice_asset_status`, `/voice_asset_detail`, `/voice_curl_audit`.

## Fixed

- Default female/male mapping is test-covered through the adapter and bot resolver.
- Saved/uploaded profiles require real `provider_voice_id`; missing provider ids show clean no-charge errors.
- Local profile id is not accepted as the provider id for saved/uploaded profiles.
- Saved voice lists use friendly display names.
- Preview policy is explicit, short, and no-charge; silent preview is blocked.
- Admin fake smoke commands cover gate, adapter, vault lookup, default TTS, preview policy, and custom voice state.
- Audio success requires a real nonzero output artifact.
- Public copy avoids provider/API/raw traceback details.

## Remains Locked

- Public custom voice creation remains guarded unless `get_minimax_voice_clone_readiness()` reports the clone path ready and public enabled.
- Real provider clone/TTS calls are not run by the new P0.19A fake smoke commands.
- LIVE PASS is not claimed because no deploy and no Telegram manual QA were requested or performed.

## Not Touched

- PayOS, wallet/Xu/payment flows.
- B13 render/stitch engine.
- VPS worker W1-W5.
- Subtitle/dub pipeline internals.
- Suno/music core.
- Web/app/standalone.
