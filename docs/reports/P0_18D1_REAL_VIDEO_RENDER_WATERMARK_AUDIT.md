# P0.18D.1 Real Video Render Route + Watermark Default Off Audit

Scope: video render route metadata, fake/test-pattern isolation, final status wording, and B14 logo/watermark default state.

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
- B14 worker queue does not yet expose a real renderer adapter inside `remote_worker.py`; the reserved hook is `render_real_video`.
- If the real route is unavailable, normal flow fails cleanly with `real_video_renderer_unavailable`; no charge/no fake MP4.

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
- Changed `local_worker.py` normal video job behavior from fake renderer to unavailable/failed unless explicit test pattern.
- Updated B14 status/delivery copy so only `render_mode=real` can say real video is completed.
- Reworked B14 logo/watermark menu into text input + six-position confirm flow.
