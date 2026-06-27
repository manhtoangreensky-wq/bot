# P0.17B14.2 Video Live Flow Repair

Base: main after B14/PR #59.

Scope: live Telegram video product flow only. No new profiles, no B13 multiscene engine/stitch rewrite, no PayOS/wallet/payment, no music/Suno core, no custom voice clone provider, no web/app/standalone changes.

## Live Router Audit

Entry points audited:

- `vproduct|open|...` opens the video product menu.
- `vproduct|input_text`, `vproduct|ideas`, `vproduct|sample`, and `vproduct|trend_select` collect the idea.
- `vproduct|asset_*` handles B14 asset intake.
- `vproduct|result`, `vproduct|prompt_image`, `vproduct|prompt_video`, and `vproduct|export_*` are prompt-pack/export tools.
- `vproduct|render` and `vproduct|prompt_video_create` previously routed into the older video finalization path.
- `/internal/video_worker/poll` and `/internal/video_worker/job_update` already exist for `video_jobs`.

Findings:

- Asset recommendation existed but was too soft and did not show the exact product warning before planning.
- Public "Dùng để tạo video" could route through old finalization screens, causing repeated aspect/package/scene prompts.
- Storyboard/prompt pack screens were mixing planner/export and paid creation.
- Add-on choices were available in other video finalization paths, but B14 project flow did not expose voice/music volume in a clean JSON-only plan before invoice.
- Storyboard planner generated generic placeholders such as product/reference wording and generic one-action text.

## Canonical Public Flow

Canonical public flow after this repair:

1. Choose video type/profile or enter idea.
2. Asset/reference intake, with clear recommendation to send character, product, object, setting, logo, storyboard, voice, or music assets.
3. Storyboard + prompt preview as text only.
4. Add-on configuration as `addon_plan_json` only.
5. Aspect ratio once.
6. Package/quality once: 200/300/400/500/600/800/1000/1200/1500 Xu.
7. Scene count once: 1/3/5/10/20/custom, capped by public max scene env for non-admin users.
8. Final invoice/confirm.

No provider/render/Xu before final confirm.

## Duplicate Screens Removed

Duplicate screens removed in the live repair:

- Storyboard panel remains planner/export only.
- `Dùng để tạo video` now transfers the current storyboard/prompt context into the B14.2 canonical flow instead of restarting the old finalization path.
- `Tạo video từ prompt` now creates a B14.2 storyboard preview instead of opening the old package finalization path.
- Aspect ratio, package, scene count, and invoice are each asked once in the canonical path.
- "Chọn đầu ra miễn phí" remains part of prompt export only, not paid video creation.

## Asset-First Repair

Public copy now says:

> Muốn video sát ý hơn, anh/chị nên gửi ảnh nhân vật, sản phẩm, đồ vật, bối cảnh, logo hoặc ảnh storyboard mẫu. Nếu bỏ qua, TOAN AAS sẽ tự dựng bằng text prompt nên độ giống nhân vật/sản phẩm có thể thấp hơn.

Skip behavior:

- If no assets are provided, the bot shows the skip warning before continuing.
- `asset_pack.skipped_by_user = true` is stored when the user confirms skipping.
- Asset upload only updates the plan. It does not render, call a provider, or charge Xu.

## Add-On UX

The public B14.2 add-on plan exposes:

- Voice source and voice volume: 70/80/90/100/110/120%.
- Music source and music volume: 5/10/15/20/30%.
- SFX none/default.
- Subtitle none/from narration/uploaded.
- Logo none/uploaded and logo corner position.

The selected plan is stored in `addon_plan_json`. No TTS/music/subtitle/FFmpeg runs before final confirm.

For the 200 Xu package, invoice disables add-ons and shows:

> Gói trải nghiệm chỉ tạo video gốc. Giọng đọc, nhạc, phụ đề và logo sẽ tắt trong hóa đơn này.

## Storyboard Brain Repair

The planner now:

- Extracts concrete subject/product/setting from the idea and assets.
- Avoids forbidden generic placeholders in final scene prompts.
- Creates scene cards with role, duration, narration, visual goal, subject action, camera motion, composition, background, transitions, music, subtitle, logo, provider prompt, negative prompt, and quality score.
- Scores subject, action, camera, continuity, and add-on readiness.
- Repairs weak scenes before showing the preview.

## Public Render And Worker Gate

Public behavior:

- If public multiscene is disabled: show the internal-test guard before invoice/confirm.
- If project worker is not configured or not connected: show worker-not-ready copy before charging.
- If enabled and worker-ready: final confirm deducts Xu and creates `video_project` + `video_job`.

Admin behavior:

- Admin bypasses public feature gates for testing.
- Admin fake renderer outputs explicitly say: `ADMIN TEST MODE — fake renderer. Video này chỉ kiểm tra pipeline ghép cảnh, không phải render AI thật.`

## Not Touched

- PayOS, wallet, `/naptien`, payment webhook.
- Music/Suno core.
- Custom voice clone provider.
- B13 multiscene render/stitch engine.
- Video main menu.
- Web/app/standalone.
