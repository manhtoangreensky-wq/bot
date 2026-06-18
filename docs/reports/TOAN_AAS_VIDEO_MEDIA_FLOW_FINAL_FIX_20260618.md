# TOAN AAS Video Media Flow Final Fix - 2026-06-18

## WIP Audit Result

- Branch audited: `wip/save-before-codex-context-reset`.
- Base main: `origin/main` at `aaf88f1`.
- WIP commit audited: `dc13b43`.
- Committed WIP diff touched only `bot.py`.
- Audit report created: `docs/reports/TOAN_AAS_WIP_VOICE_MUSIC_SUBTITLE_AUDIT_20260618.md`.
- Result: WIP was useful but not safe to merge as-is. It was safe to continue on the WIP branch only.

## Reused From V2

- Voice vault schema/helpers and account-scoped voice profile actions.
- Voice clone consent/upload/name/preview/save/default flow.
- Split Voice and Music hubs.
- Music/SFX/media menu structure.
- Subtitle/dub base price helper and 30-second block model.
- Video finalization state and invoice/order infrastructure.

## Fixed After Audit

- Self-shot video flow now asks for source video first, stores file ID in `video_session.draft.input_video_file_id`, records duration status, then asks subject to preserve.
- Self-shot finalization/back navigation now returns to `selfscene|plan` instead of resetting to main video.
- Storyboard payload now includes `storyboard_visual_canon`.
- Each storyboard scene prompt uses the visual canon and carries `retry_scope=retry_scene_only`.
- Free planning screen now appears before tier selection.
- Paid subtitle/dub add-ons now appear only after an eligible tier/package path.
- Subtitle/dub buttons now use named task labels, not icon + Xu only.
- Legacy combo invoice now shows one selected add-on line with exact combo price.
- Suno missing-readiness path now shows a friendly user guard without public provider detail.
- User-facing text touched in these flows was cleaned away from API/provider/ENV/raw-error wording.
- `/test_all_video` old-schema crash risk is covered by additive `shopaikey_jobs` column migration and tests.

## Self-Shot Flow Result

- Entry asks upload/source video first.
- Upload and recent-video paths sync source file ID, duration, filename, MIME type and file size to the video session draft.
- Next screen asks object to keep stable.
- Direction/change-scene selection happens after the object step for real uploaded videos.
- Music/voice/subtitle finalization no longer resets the self-shot plan route.

## Storyboard Image Consistency Result

- Added `storyboard_visual_canon` fields:
  `main_subject`, `product`, `brand_style`, `color_palette`, `location_style`, `lighting`, `camera_style`, `character_consistency`, `product_consistency`, `forbidden_elements`.
- Image and video prompts include the canon text.
- Scene negative prompts include canon forbidden elements.
- Scene retry scope is per scene, not whole-flow reset.

## Trend / Idea / Realistic Distinction

- Trend flow remains trend direction -> platform/hook/script/CTA/storyboard suggestion -> finalization.
- Idea flow now explicitly describes 10 ideas across sales, review, education, viral, affiliate, CSKH and automation, then routes to storyboard or realistic video.
- Realistic video flow remains prompt/content first, then ratio/style/add-ons/tier/invoice/confirm/provider.
- Tests pin that these flows are distinct and do not call processing before confirmation.

## Music / SFX Status

- Music finalization menu includes Kho nhạc, Kho SFX, Media của tôi, Tạo nhạc AI Suno, Không thêm nhạc, Back and Menu chính.
- Existing caller-origin navigation helpers are preserved.
- Menu actions do not reset the current video flow.

## Suno Status

- Suno button has a handler.
- If Suno is not public-ready, users see a friendly resource-readiness guard and no Xu charge message.
- Admin readiness still keeps sanitized reason/status fields.

## Voice / Kho Voice Status

- Voice menu includes Không thêm giọng, Kho voice của bạn, Tạo giọng mới, Giọng nữ mặc định - Miễn phí and Giọng nam mặc định - Miễn phí.
- Create-new-voice path keeps consent, upload, name, fixed preview text, audio preview, save profile and set default.
- Default voices remain free planning selections and do not create a paid dubbing line.

## MiniMax Status

- MiniMax voice profile work remains behind readiness/confirmation.
- No public MiniMax secret/config detail is shown in the touched user-facing flows.
- Billing/retry/idempotency remains an area for owner review before opening broadly.

## Subtitle / Dub Status

- Menu shows four named modes:
  1. Tạo phụ đề tự động
  2. Dịch phụ đề
  3. Lồng tiếng
  4. Phụ đề + lồng tiếng
- Translated combo is preserved internally as a compatibility alias, but no longer shown as a fifth public mode in the V5 paid menu.
- Invoice shows selected add-on name and exact price.

## Pricing Formula

- `calculate_subtitle_dub_price(mode, duration_seconds)` supports:
  - `subtitle`: 120 Xu for <=60s, +60 Xu per extra 30s block.
  - `translate_subtitle`: 150 Xu for <=60s, +75 Xu per extra 30s block.
  - `dubbing`: 250 Xu for <=60s, +125 Xu per extra 30s block.
  - `subtitle_plus_dubbing`: 350 Xu for <=60s, +175 Xu per extra 30s block.
- Combo at 24s/60s is 350 Xu.
- Combo at 180s is 1050 Xu.

## User Copy Cleanup

- Touched public flows avoid `API`, `provider`, `ENV`, `HTTP`, raw traceback, and old "Bot chưa gọi API" copy.
- Replacement copy uses friendly no-processing/no-Xu language and final-confirmation language.
- Admin-only diagnostics may still show sanitized provider/config status.

## Tests

- Literal `python -m py_compile bot.py`: not run because `python` is not on PATH locally.
- Literal `python -m py_compile local_worker.py`: not run because `python` is not on PATH locally.
- Literal `python -m pytest -q`: not run because `python` is not on PATH locally.
- Bundled Python `py_compile bot.py`: PASS.
- Bundled Python `py_compile local_worker.py`: PASS.
- Bundled Python `pytest -q`: PASS, `385 passed`, `1 warning`.
- Targeted V5 contract tests: PASS, `44 passed`, `213 deselected`, `1 warning`.
- `git diff --check`: PASS.
- `git status --short --untracked-files=no`: tracked modifications only before commit.

## Remaining Blockers

- Owner review is still required before merging to main.
- Literal `python` command is unavailable on this Windows PATH; checks were run with the bundled Codex Python runtime.
- MiniMax/Suno public generation should remain guarded until owner verifies production config and billing.
- PayOS, `/naptien`, webhook, wallet, top-up and DB destructive logic were not touched.

## Safe To Continue / Merge

- Safe to continue on WIP branch: YES.
- Safe to push WIP branch for owner review: YES.
- Safe to merge main directly: NO.
