# NEXT TASK OPTIONS - STABLE REVENUE BOT ONLY

## Master Goal Source

- Current long-term source of truth: `docs/TOAN_AAS_MASTER_GOAL_PLAN_V4_4000_WORDS_CODEX_READY.md`.
- Treat the V4 master plan as the future target after the current bot reaches Stable Revenue/Sales Ready.
- Do not implement the future trend-to-video-to-publish pipeline in the public customer bot yet.
- Current work remains limited to making the Stable Revenue Bot reliable, sellable and easy to operate.

Chưa quay lại kế hoạch lớn TOAN AAS.
Chưa làm app ngoài.
Chưa làm dashboard web.
Chưa làm ERP/Device Ops/SaaS.
Chưa mở customer affiliate vault, auto publish hoặc ads management.

## Current Priority

1. Deploy latest Stable Revenue Bot foundation hotfix.
2. Test `/huongdan` only shows/downloads Word guide, no Markdown and no numbered buttons.
3. Test `/start` as admin and normal user.
4. Test `/promo FIRST30` works without manual seeding after deploy.
5. Test `/naptien` chọn 50k and verify first-package Launch Bonus +30 Xu after paid/manual approval flow.
6. Test trial lock: same Telegram ID never receives 200 trial Xu twice, even if `users` row is recreated while `trial_grants` remains.
7. Test `ADMIN_IDS` with secondary admin for `/providers`, `/sales_ready`, `/backup_db`, `/promo_list`, `/gift_list`, `/duyet`.
8. Do not start big plan yet.

## Next After Foundation Passes

- Add Image Tool Center MVP.
- Add basic image tools.
- Add OpenAI image flags.
- Add image-to-video prompt pack.
- Do not build Image Tool Center until guide, trial, promo, admin and payment foundation pass.

Manual sequence:

```text
/backup_db
/providers
/payos_debug_create
/promo_seed_policy
/promo FIRST30
/naptien
# choose 50k or higher and pay real QR only after checkout URL works
/checkpayos <order_code>   # only if webhook has not credited yet
/mark_payos_test pass order=<order_code> note="FIRST30 OK"
/sales_ready
```

Expected for 50k + FIRST30:

- Base Xu: 500
- Launch Bonus: 30 if this is the user's first 50k package purchase
- Promo bonus: 150
- Total Xu added: 680
- Duplicate webhook/checkpayos must not add base or bonus again.

Expected for 100k first purchase:

- Base Xu: 1,000
- Launch Bonus: 50 if first 100k package purchase
- Total without promo: 1,050

## Customer Scope Now

- AI daily tools.
- Video Script / Prompt Pack with `/film`.
- STT/audio, voice/TTS, image utilities, downloader if provider works.
- PayOS QR dynamic and manual QR fallback.
- Customer self-posting only.

## Backlog Later

- Affiliate vault.
- Auto publish.
- Ads assistant.
- Claude Ads Safety Checker for future admin-first Ads module.
- Customer social account connection.
- Risk keyword checker.
- Compliance checker.
- Paid service package for publish/ads management.
- TOAN AAS Admin Trend-to-Video-to-Publish Pipeline:
  - Admin Trend Finder.
  - Admin Trend Scoring.
  - Admin AI Video Builder.
  - Admin Voice Builder.
  - Admin Review Gate.
  - Admin Publish Queue.
  - Admin Performance Tracker.
- GitHub Copilot dev workflow.
- Legal Docs Lite with OpenLaw/OpenLaws.
- Legal templates for service contracts and warranty documents.

## Future Ads Rule - Admin First

- Claude Ads Safety Checker belongs to future TOAN AAS Lab/admin sandbox, not the current customer bot.
- Possible future commands: `/ads_check`, `/ads_rewrite`, `/ads_score`, `/ads_pack`, `/ads_risk_report`.
- Future flow: generate script/caption/CTA -> Claude safety check -> risk level `SAFE`/`NEEDS_REWRITE`/`HIGH_RISK` -> safer rewrite -> admin review -> admin approve.
- Customer ads automation remains OFF by default.
- No automatic ad launch, no password collection, no payment card collection, and no approval/revenue guarantee.
- Customer-facing ads service can open later only if admin approves pricing, workflow, approval gate and responsibility rules.

## Future Publish Rule - Admin First

- Publish workflow belongs to TOAN AAS Lab/admin sandbox, not the current customer bot.
- Build and test publishing with admin-owned pages/accounts/channels first.
- Required future flags stay OFF by default: `publish_workflow`, `customer_publish`, `auto_publish`, `ads_assistant`.
- `admin_publish` is admin/internal only and requires explicit approval before live testing.
- No customer social account connection, no customer auto publish, no customer ads management in the current bot.
- If customer publish opens later, it must be a separate paid feature with account permission, approval gate, audit log, failure handling and admin disable switch.
- Future pipeline stages: `trend_scan -> trend_score -> angle_select -> script_generate -> scene_prompt_generate -> video_generate_task -> voice_generate -> assemble_or_export -> platform_output_generate -> risk_check -> admin_review -> admin_approve -> publish_queue -> publish_execute -> performance_track -> growth_ai_feedback`.

Codex không tự làm task tiếp theo.
