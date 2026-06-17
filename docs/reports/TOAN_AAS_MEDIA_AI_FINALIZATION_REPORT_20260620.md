# TOAN AAS Media AI Finalization Report - 2026-06-20

## Scope

This pass standardizes Media AI readiness for:

- AI image edit
- Suno music
- MiniMax Voice
- ASR/subtitle/dubbing pipeline

## Rule

Every provider-backed feature must pass:

provider readiness -> admin smoke -> public gate -> pricing -> confirm -> job -> real output -> friendly failure.

No API key, raw token, raw provider response, fake task id, or fake output is exposed.

## Public Gate

- Video 200 Xu keeps all paid add-ons locked.
- Suno/MiniMax/subtitle/dubbing are only allowed from 300 Xu+ or as standalone products with explicit pricing confirmation.
- Missing provider docs/config returns NEED_DOCS/NOT_CONFIGURED for admin and a friendly maintenance message for customers.

## Commands Added/Aligned

- `/image_edit_status`
- `/suno_status`
- `/minimax_status`
- `/subtitle_dub_status`
- `/tool_test_suno_music`
- `/tool_test_minimax_tts`
- `/tool_test_minimax_voice_clone`
- `/tool_test_subtitle_generate`
- `/tool_test_subtitle_translate`
- `/tool_test_minimax_dub`
- `/suno_public_open`, `/suno_public_close`
- `/voice_public_open`, `/voice_public_close`
- `/subtitle_translate_public_open`
- `/subtitle_dub_public_open`

## Data

Added `voice_profiles` table for future consented/user-scoped voice profiles.

## Not Touched

PayOS, `/naptien`, webhook, wallet/Xu top-up logic, combo/monthly package purchase logic, trial bonus, ShopAIKey stable paths.
