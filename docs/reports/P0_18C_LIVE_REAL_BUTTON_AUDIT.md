# P0.18C Live Video Real Button Audit

Branch: `hotfix/p0-18c-live-video-real-button-repair`

Base: `origin/main` after P0.18B, `5e7cb74`.

## Scope

This audit covers only the public/live video planner button path:

- storyboard prompt video preview
- logo add-on source/position/back flow
- voice narration text edit
- voice/music manual volume input
- scene count and invoice discount
- queue/status detail after confirm
- admin-only no-charge regression command

Not touched: PayOS, wallet/Xu ratio, payment webhook, B13 render/stitch internals, W1-W5 worker internals, Suno/music provider core, web/app/standalone.

## Callback Matrix

| Live button | Callback / state |
| --- | --- |
| Xem prompt video | `vproduct|b14_prompt_video_text` |
| Xuat bo prompt | `vproduct|b14_export_pack` |
| Xem prompt anh | `vproduct|b14_prompt_image_text` |
| Cau hinh add-ons | `vproduct|b14_addons` |
| Tiep tuc tao video | `vproduct|storyboard_confirm` |
| Quay lai storyboard | `vproduct|b14_creative_done` / `vproduct|b14_storyboard_screen` |
| Logo menu | `vproduct|b14_addon_logo` |
| Logo da gui | `vproduct|b14_logo_source|uploaded` |
| Gui logo moi | `vproduct|b14_logo_upload` then state `b14_logo_upload_wait` |
| Logo position buttons | `vproduct|b14_logo_position|top_left|top_right|bottom_left|bottom_right` |
| Xong logo | `vproduct|b14_logo_done` |
| Voice menu | `vproduct|b14_addon_voice` |
| Sua loi doc | `vproduct|b14_voice_edit` then state `waiting_video_narration_text` |
| Am luong giong | `vproduct|b14_voice_volume` then state `waiting_voice_volume_percent` |
| Music menu | `vproduct|b14_addon_music` |
| Am luong nhac | `vproduct|b14_music_volume` then state `waiting_music_volume_percent` |
| Scene count 1/3/5/10/20 | `vproduct|b14_scene_count|<count>` |
| Nhap so khac | `vproduct|b14_scene_custom` then state `waiting_scene_count` |
| Hoa don | `vproduct|b14_invoice_screen` |
| Kiem tra trang thai | `vproduct|b14_job_status` |

## Root Causes

- Prompt video root cause: the live button used the generic prompt text renderer, which can generate an oversized Telegram edit payload and did not expose a compact per-scene fallback screen. Missing storyboard cases were rebuilt, but the UI still had no safe compact output.
- Logo root cause: source and position were mixed under `b14_logo_set`; choosing a position also enabled logo, so the UI felt like it forced position before logo source.
- Voice text root cause: the edit state was named `b14_voice_edit` and the prompt was too short; production users could not tell they were in a text input state for narration used by voice/subtitle.
- Volume root cause: voice/music volume opened fixed button menus only. There was no primary manual input state for arbitrary percent values.
- Scene count root cause: custom scene count reused `b14_scene_custom` and silently clamped values; it did not explain stable 1-5 scene guidance or guard unsupported multi-scene public charging clearly.
- Status root cause: the status screen was a confirmation receipt, not a real status view. It lacked stage/progress/addons/queue/no-charge fields.

## Session Keys

- `draft.b14_storyboard_plan`
- `draft.prompt_bundle`
- `draft.b14_addon_plan`
- `draft.b14_scene_count`
- `draft.b14_quality_xu`
- `draft.b14_invoice`
- `draft.b14_queue_job`
- `draft.b14_queue_job_id`
- `draft.b14_project_id`
- `draft.provider_called`
- `draft.xu_charged`
- `current_step`

## Back Routes

- Prompt video back returns storyboard via `vproduct|b14_creative_done`.
- Logo back returns add-ons via `vproduct|b14_addons`.
- Voice volume back returns voice via `vproduct|b14_addon_voice`.
- Music volume back returns music via `vproduct|b14_addon_music`.
- Scene custom back returns scene count via `vproduct|b14_scene_count_screen`.
- Status invoice back uses `vproduct|b14_invoice_screen`.

## Regression Coverage

- `test_prompt_video_button_no_generic_error`
- `test_prompt_video_rebuilds_from_storyboard`
- `test_prompt_video_missing_session_recovery`
- `test_prompt_video_back_to_storyboard`
- `test_logo_sent_selects_source_before_position`
- `test_logo_position_without_logo_saves_position_and_guides`
- `test_logo_upload_sets_waiting_state`
- `test_logo_done_returns_addons`
- `test_logo_back_returns_addons`
- `test_voice_edit_text_sets_waiting_state`
- `test_voice_edit_text_saves_narration`
- `test_voice_edit_text_returns_voice_menu`
- `test_voice_narration_used_by_subtitle`
- `test_voice_default_does_not_skip_narration`
- `test_voice_volume_asks_manual_input`
- `test_voice_volume_accepts_percent`
- `test_voice_volume_rejects_invalid`
- `test_music_volume_asks_manual_input`
- `test_music_volume_accepts_percent`
- `test_music_volume_rejects_invalid`
- `test_volume_back_routes_correctly`
- `test_scene_count_preserves_storyboard`
- `test_scene_count_extends_storyboard`
- `test_custom_scene_count_waits_for_input`
- `test_custom_scene_count_validates_range`
- `test_unsupported_multiscene_guard_no_charge`
- `test_video_discount_1_to_4_scenes_20_percent`
- `test_video_discount_5_to_9_scenes_25_percent`
- `test_video_discount_10_to_19_scenes_30_percent`
- `test_invoice_shows_discount_amount`
- `test_owner_admin_no_charge_still_applies`
- `test_video_status_shows_job_stage_progress`
- `test_video_status_shows_addons`
- `test_video_status_no_fake_success`
- `test_video_status_queued_worker_message`
- `test_video_status_owner_no_charge`
- `test_tool_test_live_video_buttons_regression_admin_only`
- `test_tool_test_live_video_buttons_regression_no_charge`
- `test_tool_test_live_video_buttons_regression_covers_prompt_logo_voice_volume_discount_status`
