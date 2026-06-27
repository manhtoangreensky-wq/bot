# P0.18D Video Output Delivery Audit

Scope: video output delivery, processing status copy, watermark/logo menu, scene-count policy, and admin-only delivery worker test.

Out of scope and intentionally untouched: PayOS, wallet/Xu ratio, voice/subtitle/dub engines, music/Suno, web/app.

Findings:

- Public video status still used technical words such as worker and queue in the main status card.
- The video worker bridge had canary/admin-canary modes, but no dedicated owner/admin no-charge video delivery mode for normal `video_render` jobs.
- Admin/owner video projects did not carry a clear no-charge/admin-delivery marker for a remote worker to claim safely without opening public jobs.
- Logo UI previously mixed default watermark, uploaded image logo, and position in one add-on screen.
- Scene buttons were derived from an environment max, so 10/20 could disappear or be clamped before invoice. Scene 20 also did not receive the 30% scene discount.
- Status refresh already read the latest job row by id; wording needed cleanup so users see “hệ thống” and final output readiness, not worker internals.

P0.18D fixes:

- Added `remote_worker.py --admin-video` for owner/admin no-charge video delivery jobs only.
- Added remote worker API support for `admin_video_only` with an admin/no-charge/public-false safety filter.
- Added an admin-only `/tool_test_video_delivery_worker --no-charge` command that creates a normal `video_render` delivery test job.
- Admin video completion now requires a real non-empty MP4 upload/path and cannot pass without output.
- Restored logo/watermark as a text add-on flow: enter text, choose position, confirm, then return to add-ons. Image logo assets are handled outside this add-on screen.
- Scene buttons now always show 1/3/5/10/20, with public confirmation still guarded before any processing or charge if the output path is not ready.
- Scene 20 now receives the same 30% scene-count discount as 10-19.
- Public status copy now uses friendly system wording and avoids worker/queue/provider/API/FFmpeg/lease/traceback terms.

Validation notes:

- This is not a live Telegram pass. Manual Telegram button QA is still required before claiming LIVE PASS.
- Deploy is not included in this task.
