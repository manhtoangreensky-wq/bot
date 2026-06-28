# P0.18D.1 Safety Fix + Watermark Default Off Audit

Scope: video render route metadata, fake/test-pattern isolation, final status wording, and B14 logo/watermark default state.

## Ship Status

CODE PASS / SAFETY FIX PASS / REAL RENDER ROUTE CONNECTED / FAKE PRODUCT OUTPUT BLOCKED / WATERMARK DEFAULT OFF / DEPLOY PENDING / LIVE QA NOT STARTED

This PR is a safety fix plus real-provider route reconnection. It does not claim live readiness because deploy and Telegram admin product QA have not started.

## Test Pattern Source

- `remote_worker.py::render_fake_video` creates a local color MP4 from FFmpeg `color=...`; it is now allowed only for explicit admin test-pattern jobs.
- `remote_worker.py::render_admin_video_delivery` creates local FFmpeg `testsrc` video; it is now labeled as `render_mode=admin_test_pattern` and used only by `/tool_test_video_delivery_worker --no-charge`.
- `local_worker.py::video_project_fake_scene_renderer` remains a test helper but normal `video_render` no longer uses it unless job metadata explicitly says `render_mode=admin_test_pattern`.
- `tools/smoke_multiscene_blackbox.py --fake-renderer --no-charge` remains an explicit smoke-only fake-renderer path.

## Why Normal Video Used Fake

- P0.18D connected worker delivery first. The B14 confirmed project path marked owner/admin jobs with `admin_video_delivery=True`, so `remote_worker.py --admin-video` claimed the job and rendered `testsrc`.
- `local_worker.py::run_video_render_job` also used `video_project_fake_scene_renderer` when `LOCAL_VIDEO_FAKE_RENDERER_ENABLED` was enabled.
- Status/delivery copy did not distinguish real render from delivery test pattern, so a test MP4 could look like completed video output.

## Final Confirm Metadata

- B14 normal confirm now stores:
  - `render_mode=real`
  - `test_pattern=false`
  - `fake_renderer_allowed=false`
  - `real_renderer_required=true`
- Owner/admin no-charge remains no-charge, but normal owner/admin video confirm is still `render_mode=real`; it cannot use test pattern as success.

## Admin-Video Worker Route

- `/tool_test_video_delivery_worker --no-charge` creates an explicit `admin_test_pattern` job.
- The command copy says this is a technical file-delivery test, not real rendered video and not LIVE PASS.
- `remote_worker.py --admin-video` can render test pattern only when all safety flags are present: admin-only, no-charge, provider-call false, public-user false, and `render_mode=admin_test_pattern`.

## B13/Render/Stitch Availability

- Existing B13 legacy provider route remains in `bot.py::run_multiscene_video_job`.
- B14 worker queue now calls `services/video_real_render_connector.py` through `remote_worker.py::render_real_video` and `local_worker.py::video_project_real_scene_renderer`.
- If provider config is missing, normal flow fails cleanly with provider-specific diagnostics such as `shopaikey_video_config_missing` / `key4u_video_config_missing`; no charge/no fake MP4.

## Real Renderer

- connected: YES, to the existing ShopAIKey/Key4U submit-poll-download routes when their ENV/config is present
- current behavior without provider config: safe failed/no-charge diagnostic, not fake output
- product fake output blocked: YES
- next required task: deploy/admin Telegram QA for 1-scene and 3-scene real product render; then harden add-on mux for voice/music/subtitle assets that require provider-ready artifacts

## Watermark Default State

- `video_b14_default_addon_plan` defaults:
  - `logo_enabled=false`
  - `logo_source=none`
  - `logo_text=""`
  - `logo_position=bottom_right` as inactive preference only
- Add-on summary, invoice, and status show `Logo: Tắt` by default.

## Logo/Watermark UX Fix

- B14 add-on logo/watermark is now text-only:
  - enter text
  - choose one of 6 screen positions
  - confirm
  - return to add-ons
- Default TOAN AAS watermark and uploaded image logo are no longer shown in this add-on screen.
- Image/logo assets remain outside this add-on flow.

## Exact Fix

- Added render mode metadata and validation in `services/remote_worker_api.py`.
- Split `remote_worker.py` test-pattern path from normal real-render path.
- Connected `remote_worker.py::render_real_video` and `local_worker.py::video_project_real_scene_renderer` to `services/video_real_render_connector.py`.
- The connector reads original prompt, scene cards, aspect ratio, provider order, and add-on plan from the worker job payload.
- The connector submits scenes to existing provider routes, polls/downloads MP4 outputs, normalizes duration, stitches scenes, and returns one final MP4 only.
- Changed `local_worker.py` normal video job behavior from fake renderer to real-provider connector unless explicit test pattern.
- Updated B14 status/delivery copy so only `render_mode=real` can say real video is completed.
- Reworked B14 logo/watermark menu into text input + six-position confirm flow.
- Sanitized legacy sessions so old `uploaded/default_watermark` logo state does not reappear in the add-on menu.
- Added FFmpeg text overlay support for confirmed logo/watermark text in the blackbox mux path.

## P0.18D.1 Done

1. Chặn fake/testsrc/color bars khỏi normal product video flow.
2. Admin test pattern vẫn chạy cho smoke/canary, có nhãn rõ.
3. Normal/admin product video đi qua real-provider connector; nếu provider config/gọi provider fail thì fail sạch/no-charge.
4. Watermark/logo add-on chuyển sang flow chữ, 6 vị trí, xác nhận.
5. Default watermark tắt và session cũ bị sanitize.
6. Job payload giữ `original_user_prompt`, `cleaned_user_prompt`, scene cards, provider order, aspect ratio, package, add-on plan.
7. Scene prompts mềm hơn, giữ ý người dùng, không tự thêm logo/watermark/text nếu user không yêu cầu.

## P0.18D.1 Not Done

1. Chưa deploy PR #82.
2. Chưa chạy Telegram admin product 1 cảnh ra video AI thật trên live ENV.
3. Chưa chạy Telegram admin product 3 cảnh ra final MP4 thật trên live ENV.
4. Chưa mở public video.
5. Voice/music/subtitle add-on vẫn cần provider-ready artifact; nếu thiếu thì fail sạch, không fake final success.

## Manual QA After Deploy

1. `/tool_test_video_delivery_worker --no-charge`
   - Có thể ra video test pattern.
   - Phải nói rõ không phải video thật.
2. Admin tạo video product bình thường:
   - Không được ra video sọc màu.
   - Nếu provider config thiếu hoặc provider fail, báo chưa sẵn sàng/no-charge.
   - Không claim success.
3. Public product video:
   - Chưa mở.
   - Không fake output.
   - Không trừ Xu trước provider thật.

## Next Required Task

P0.18E Real Provider Renderer Live QA + Add-on Hardening

Goal:

- deploy PR #82 only after approval.
- verify runtime commit.
- admin product 1 cảnh ra video thật.
- admin product 3 cảnh stitch thành final MP4 thật.
- verify logo chữ default off and confirmed overlay position.
- harden voice/music/subtitle add-on provider artifact mux without fake success.
