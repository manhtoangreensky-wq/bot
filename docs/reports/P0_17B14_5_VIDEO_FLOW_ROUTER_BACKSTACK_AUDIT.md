# P0.17B14.5 Video Flow Router + Backstack Audit

Branch: `hotfix/p0-17b14-5-video-flow-router-backstack-legacy-restore`

Base: latest `origin/main` after PR #64 (`0dba8cc`).

## Scope

Fixed only the live B14 video product flow/router layer:

- Callback routing for `vproduct|...`
- Public copy and menu continuity for the B14 planning flow
- Backstack rendering for B14 screens
- Legacy voice/music/add-on selection screens inside the video planner
- Final confirm status/ETA screen after queueing
- Admin-only dry-run diagnostics

Not touched:

- B13 multiscene render/stitch engine
- PayOS, wallet, Xu pricing ratios, C1/C2/C3 payment logic
- Suno/music provider core
- Custom voice clone core
- Web/app/standalone

## Broken Live Paths Found

Screenshots and source audit showed these broken paths:

- `vproduct|asset_skip_confirm` asked for an idea but left `current_step` at `b14_creative_controls`, so user text fell through to generic chat.
- `vproduct|back` used `task3d_render_step`, but that renderer did not know B14 screens, so Back could jump to old generic intro screens.
- `vproduct|ideas` used generic product suggestions instead of selected profile suggestions.
- `vproduct|b14_addon_voice` and `vproduct|b14_addon_music` were one-shot choice popups; applying default voice/music immediately returned to add-ons and lost the old flow feeling.
- `vproduct|b14_scene_count` could be pressed before package selection and returned to storyboard instead of forcing package -> scene count -> invoice.
- `vproduct|b14_confirm` cleared the session immediately, so the user had no job status/ETA button after confirmation.
- Public copy still exposed technical wording such as provider/FFmpeg/QC/profile ids in key B14 screens.

## Canonical Public Flow

Canonical flow after B14.5:

1. Select video profile
2. Enter idea or choose profile-based suggestion
3. Asset intake with skip warning
4. Creative controls
5. Storyboard/prompt text planning
6. Add-ons: voice, music/SFX, subtitle, logo
7. Aspect ratio
8. Package/quality
9. Scene count
10. Invoice
11. Final confirm
12. Queue status with ETA
13. Final MP4 sent by worker

No file generation, provider call, or Xu charge happens before final confirm.

## Callback Matrix

| Step | Callback(s) | Fixed behavior |
| --- | --- | --- |
| Profile select | `vproduct|b14_profile|...`, `vproduct|b14_profiles` | Saves selected profile and shows idea/assets/creative choices. |
| Profile back | `vproduct|b14_profile_back` | Returns to selected profile summary if chosen, otherwise profile selection. |
| Ideas | `vproduct|ideas`, `vproduct|ideas_refresh`, `vproduct|b14_idea_select|n` | Uses selected profile suggestions; selected idea goes to asset intake. |
| Manual idea | `vproduct|input_text` | Sets `current_step=collect_input` and saves text through pending-text handler. |
| Asset intake | `vproduct|asset_intro`, `asset_wait`, `asset_done` | Keeps user in asset flow; Back returns to profile summary. |
| Asset skip | `vproduct|asset_skip`, `asset_skip_confirm` | Shows warning; continue saves skipped assets. If idea missing, moves to real text-input state. |
| Creative | `vproduct|b14_creative_screen`, `b14_creative_field`, `b14_creative_done` | Friendly controls; done builds storyboard. |
| Storyboard | `vproduct|storyboard_confirm`, `b14_prompt_image_text`, `b14_prompt_video_text`, `b14_export_pack` | Text-only planning; no file generation. |
| Voice | `vproduct|b14_addon_voice`, `b14_voice_source`, `b14_voice_edit`, `b14_voice_done` | Dedicated voice screen, narration saved from storyboard or user text. |
| Music/SFX | `vproduct|b14_addon_music`, `b14_music_source`, `b14_music_cut`, `b14_music_done` | Dedicated music screen with default/vault/uploaded/saved choices. |
| Add-ons done | `vproduct|b14_addon_done` | Goes to aspect ratio. |
| Aspect | `vproduct|b14_aspect|...` | Goes to package/quality. |
| Package | `vproduct|b14_quality|...` | Goes to scene count. |
| Scene count | `vproduct|b14_scene_count|...`, `b14_scene_custom` | If package missing, forces package screen. Otherwise builds invoice. |
| Confirm | `vproduct|b14_confirm` | Confirms invoice once and shows job status/ETA, preserving session status. |
| Status | `vproduct|b14_job_status`, `b14_invoice_screen` | Lets user check status or review invoice after confirm. |

## Backstack Matrix

`task3d_render_step` now knows B14 screens:

- `profile_select`
- `intro` with B14 profile selected
- `asset_intake`
- `idea_suggestions` with B14 profile selected
- `b14_creative_controls`
- `storyboard_preview`
- `b14_addons`
- `b14_voice`
- `b14_music`
- `b14_aspect`
- `b14_quality`
- `b14_scene_count`
- `b14_invoice`
- `b14_queue_status`

This prevents old `vproduct|back` from falling into generic Task3D intro/result screens.

## Legacy UX Restored

- Default male/female voice remains a first-class choice.
- Voice flow displays narration text derived from storyboard and lets admin/user edit narration before confirm.
- Preview voice is locked to after full video confirmation; it does not create test files in public.
- Music flow restores default music, vault, SFX vault, uploaded, and saved choices.
- Add-ons return to a summary screen instead of jumping randomly.
- Scene count keeps the old price-per-scene model and happens after package selection.

## Admin Diagnostics

Added admin-only hidden commands:

- `/tool_test_video_flow_router`
- `/tool_test_video_backstack`
- `/tool_test_video_live_dry_run`
- `/tool_test_video_job_status`

They do not call the real renderer/provider and do not deduct Xu.

## Public Copy Guard

The main B14 public screens now avoid exposing internal terms such as provider, FFmpeg, callback, queue lease, local worker, prompt context engine, and continuity ledger. Prompt text export remains available as planning text, not a file-generation path.
