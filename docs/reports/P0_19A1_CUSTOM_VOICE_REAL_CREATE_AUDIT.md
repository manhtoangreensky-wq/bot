# P0.19A.1 Custom Voice Real Create Flow Audit

Date: 2026-06-27
Branch: `hotfix/p0-19a1-custom-voice-real-create-flow`

## Scope

This audit covers only the custom voice create flow and the voice vault button layout.

Not touched:
- PayOS, wallet/payment rules, or Xu pricing constants.
- Video engine, render/stitch engine, worker W1-W5, or video flow router/backstack.
- Subtitle/dub pipeline.
- Suno/music core.
- `web/app/standalone`.

## Voice Vault Layout

The showroom voice vault now lists default voice shortcuts before custom voice creation:
- Row 1: `👨 Giọng nam`, `👩 Giọng nữ`.
- Row 2: `🧬 Tạo voice riêng`.

This keeps the custom voice button centered/full-width when no saved voices are present.

## Default Male/Female Source

Default voice ids continue to resolve through:
- `default_tts_voice_id("male")`
- `default_tts_voice_id("female")`
- `video_b14_voice_resolution(...)`
- `services/minimax_voice_adapter.resolve_provider_voice_id(...)`

These paths resolve provider-ready ids and do not send local profile ids to a provider.

## Saved Voice DB/Table/Fields

Saved/custom voices live in table `voice_profiles`.

Relevant fields:
- `id`: local profile id, never sent as provider voice id.
- `user_id`: owner.
- `provider`: selected provider/route, for example `shopaikey_minimax`, `key4u_minimax`, or `minimax_fake`.
- `provider_voice_id`: real provider voice id returned by provider or fake adapter in admin test mode.
- `display_name`: friendly user-facing voice name.
- `source_file_id` / `source_file_ref`: Telegram sample reference.
- `preview_audio_ref`: Telegram audio file id for demo, only when a real nonzero preview artifact was sent.
- `status`: `pending_confirm`, `pending_charge`, `ready`, or failure statuses.
- `metadata_json`: stores `source_type=custom_clone`, sample metadata, provider route, charge status, and activation timestamps.

Vault lookup uses:
- `voice_core_vault_lookup(...)`
- `minimax_voice_adapter.voice_vault_entry(...)`

Missing or local-only `provider_voice_id` entries are excluded from mapped provider lookup and cannot generate TTS.

## Uploaded Voice Source

The upload step uses the existing Telegram media path:
- callback `music_quick|showroom|voice_clone`
- callback `music_quick|showroom|voice_consent`
- pending action `voice_clone_upload`
- `handle_music_guided_pending_media(...)`
- `message_media_candidate(...)`
- `save_user_voice_profile(...)`

Accepted media remains voice/audio/document with audio MIME. The file is saved as a draft profile and does not call provider or charge Xu at upload time.

## Custom Voice Create Path

Public flow:
1. User taps `🧬 Tạo voice riêng`.
2. User confirms consent.
3. User uploads a clean voice/audio sample.
4. User sends the required sample confirmation sentence.
5. User enters a friendly display name.
6. User confirms the quoted create price.
7. `create_minimax_voice_profile_preview(...)` calls the configured MiniMax route.
8. Provider upload + clone must return a valid provider voice id.
9. `finalize_custom_voice_creation(...)` saves the provider voice id to `voice_profiles`.
10. Xu is charged only after provider success and vault save, and only for non-admin paid creations.

Provider routes:
- `shopaikey_minimax`: upload sample, clone voice, optional TTS demo.
- `key4u_minimax`: upload sample, clone voice, optional TTS demo.
- optional Fish/Eleven route names are still present but not changed by this repair.

## Provider Voice ID Mapping

The flow now validates `provider_voice_id` using:
- `minimax_voice_adapter.normalize_voice_id(...)`
- `minimax_voice_adapter.validate_provider_voice_id(...)`

The local `voice_profiles.id` is not used as the provider voice id.

If provider returns no usable id:
- profile is not marked ready,
- Xu is not charged,
- public reply stays clean and non-technical,
- user gets retry/default voice/vault/menu fallback buttons.

## Preview Path

Preview remains explicit and short:
- `voice_core_preview_policy(...)`
- `voice_preview_guard(...)`
- `cap_voice_preview_audio_bytes(...)`

Preview/demo audio is optional after clone success:
- If nonzero preview bytes exist, TOAN AAS caps and sends an audio demo, then stores `preview_audio_ref`.
- If preview TTS fails but clone returned a valid provider voice id, profile can still be saved as ready without claiming a demo exists.
- Preview never silently charges Xu.

## Charge Policy

The create profile price still uses:
- first successful custom voice: free,
- later successful custom voice: `VOICE_PROFILE_PRICE_XU` (default 50 Xu).

Charge timing:
- no charge on upload,
- no charge on naming,
- no charge on quote display,
- no charge if provider fails,
- no charge if provider id is missing,
- non-admin paid charge only after provider success and vault save,
- admin/owner fake test mode remains no-charge.

## Adapter

`services/minimax_voice_adapter.py` now includes:
- `CustomVoiceCreateResult`
- `create_custom_voice_from_sample(...)`

Fake mode:
- deterministic provider voice id,
- no provider call,
- useful for admin smoke tests.

Real mode:
- requires a callable provider adapter,
- refuses success when provider id is missing,
- sanitizes public errors.

## Admin Commands

Existing:
- `/tool_test_voice_gate`
- `/tool_test_minimax_adapter --fake`
- `/tool_test_voice_vault_lookup`
- `/tool_test_voice_default_tts --fake`
- `/tool_test_voice_preview_policy --fake`
- `/tool_test_custom_voice_flow --fake`

Added:
- `/tool_test_custom_voice_provider --fake`
- `/tool_test_custom_voice_provider --real --confirm-provider-cost`

Real provider command is explicit and gated because it can call provider resources. It does not charge TOAN AAS Xu.

## Fixed

- Voice vault layout is balanced with male/female defaults on the first row and custom voice centered below.
- Custom voice fake admin flow now creates a provider-mapped profile in the vault.
- Custom voice provider adapter rejects missing provider ids.
- Public custom voice create flow no longer treats missing preview audio as proof of success.
- Provider id is validated and saved before profile is marked ready.
- Failed provider id/clone cases do not charge.
- Admin fake tests remain no-charge and clearly say no provider call.
- Locked provider copy is clean and no longer exposes provider/API/raw diagnostics.

## Remains Locked

- Public custom voice real creation still depends on provider readiness, route configuration, and MiniMax clone permission.
- Real provider admin test requires `--real --confirm-provider-cost` and a replied audio sample.
- Optional provider routes outside MiniMax were not expanded in this repair.
- No live Telegram pass or deploy is claimed in this audit.
