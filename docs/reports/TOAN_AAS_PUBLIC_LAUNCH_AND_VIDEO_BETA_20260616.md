# TOAN AAS Public Launch + Video Beta Report

## 1. Current Public Status

- Free tools: ON by menu/handler guard.
- Translation: stable locked / ON.
- Image generation: controlled by image provider flags and existing billing guard.
- Image AI edit: guarded by provider readiness and confirmation.
- Video planning/storyboard/trend content: public planning layer, no provider call and no Xu charge.
- Video AI beta: controlled by `/video_beta_open`, `/video_beta_close`, `/video_public_open_safe`.

## 2. Tools Opened Public

- Planning-only video flows can remain public because they generate prompt/script/storyboard only.
- Public video beta can open only for low/basic/common tiers after smoke and cost gates pass.
- Public beta tiers map to 200 / 300 / 400 Xu from the centralized video tier price table.

## 3. Tools Guarded

- Frame video remains guarded by Local Worker + ffmpeg smoke status.
- Video AI realistic render remains guarded by ShopAIKey video smoke output, billing safety, job lock, and cost ratio.
- Image AI edit remains guarded by provider readiness and final confirmation.

## 4. Tools Kept Off

- Video 600+ / standard / high.
- Premium video.
- Long render.
- Image-to-video until separate smoke pass.
- Video-to-video/self-scene until separate smoke pass.
- Subtitle+dub public render until separate smoke pass.
- Auto publish and ads assistant.

## 5. Video Status

- Planning: ON by `VIDEO_PLANNING_PUBLIC_ENABLED`.
- Storyboard: ON by `VIDEO_STORYBOARD_PUBLIC_ENABLED`.
- Trend: ON by `VIDEO_TREND_CONTENT_PUBLIC_ENABLED`.
- Frame video: ON only if `FRAME_VIDEO_PUBLIC_ENABLED` and worker/ffmpeg smoke pass.
- Video AI beta: ON only if `/video_beta_open` or `/video_public_open_safe` passes.
- 200: low tier.
- 300: basic tier.
- 400: common tier.
- 600+: OFF.
- Premium: OFF.
- Long render: OFF.

## 6. Cost / Margin

- Cost gate uses `check_video_margin(tier)`.
- Safe if provider cost ratio is at or below `VIDEO_PUBLIC_MAX_COST_RATIO` default `0.5`.
- Warning window is between safe ratio and `VIDEO_PUBLIC_WARN_COST_RATIO` default `0.6`.
- Blocked if provider cost ratio is above the hard ratio or provider cost is unknown.
- Blocked tiers stay visible only in admin status, not as public purchase buttons.

## 7. Smoke Tests

- Frame video: run `/tool_test_frame_video`.
- VEO submit: run `/tool_test_shopaikey_video`.
- VEO status: run `/shopaikey_video_job <task_id>`.
- Telegram output: require completed provider result and Telegram output sent.

## 8. Safety

- Confirm: required by `SHOPAIKEY_REQUIRE_CONFIRM_BEFORE_DEDUCT` and `VIDEO_PUBLIC_REQUIRE_CONFIRM`.
- Job lock: required by `SHOPAIKEY_PUBLIC_JOB_LOCK_ENABLED`, `SHOPAIKEY_VIDEO_JOB_LOCK_ENABLED`, and `VIDEO_PUBLIC_REQUIRE_JOB_LOCK`.
- Refund: required by `SHOPAIKEY_REFUND_ON_PROVIDER_FAIL`.
- Auto freeze: exposed by `VIDEO_PUBLIC_AUTO_FREEZE_ON_ERROR`.
- Low credit: keep using ShopAIKey usage monitor/admin alert.

## 9. Manual Test Results

Run in order after deploy:

1. `/runtime`
2. `/providers`
3. `/system_public_status`
4. `/video_public_status`
5. `/video_gate_status`
6. `/video_cost_status`
7. `/shopaikey_usage`
8. `/tool_test_shopaikey_video`
9. `/shopaikey_video_job <task_id>`
10. `/video_beta_open 200,300,400` only after VEO output passes.

## 10. Final Recommendation

Open planning/storyboard immediately. Open frame video only after Local Worker smoke passes. Open Video AI beta 200/300/400 only after ShopAIKey video smoke completes with a real output and cost gate passes. Keep 600+, premium, long render, image-to-video and video-to-video OFF until separate smoke tests pass.
