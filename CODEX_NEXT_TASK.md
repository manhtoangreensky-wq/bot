# NEXT TASK OPTIONS - STABLE REVENUE BOT ONLY

## Master Goal Source

- Current long-term source of truth: `docs/TOAN_AAS_MASTER_GOAL_PLAN_V4_4000_WORDS_CODEX_READY.md`.
- Treat the V4 master plan as the future target after the current bot reaches Stable Revenue/Sales Ready.
- Do not implement the future trend-to-video-to-publish pipeline in the public customer bot yet.
- Current work remains limited to making the Stable Revenue Bot reliable, sellable and easy to operate.

## Strategic Direction After Current Bot

TOAN AAS is following this model:

`AI Tools SaaS + Pay-as-you-go Credits + Automation Platform`

## Current Ops Safety Checkpoint

- Emergency lock, maintenance mode, payment freeze and tool freeze are part of the Stable Revenue Bot operations layer.
- After deploy, owner should test: `/emergency_status`, `/maintenance_on`, `/maintenance_off`, `/freeze_tools`, `/unfreeze_tools`, `/freeze_payments`, `/unfreeze_payments`, `/ops_plan`.
- Use `/emergency_lock <reason>` only for real incident drills or urgent safety lock. Only owner should run `/emergency_unlock`.
- Emergency mode must preserve DB, balances, payment history, ledger events and backups.

The current phase is not the large app/dashboard phase. Priority number one is to finish the existing Telegram bot so it runs reliably and starts generating real revenue.

### Current Phase - Bot Revenue Phase

Goals:

1. Telegram bot runs stably.
2. Service Xu top-up works reliably with manual QR first; PayOS dynamic checkout is debugged later.
3. User balances are managed by Telegram ID.
4. Trial 200 Xu can be claimed only once.
5. Only tools that pass smoke tests can be opened to customers.
6. Broken tools stay hidden/admin-only; customers must not use broken flows.
7. Provider failures must refund Xu when Xu was charged.
8. Legal terms, privacy policy and Xu service rules are present.
9. Website, landing page, guide and terms downloads are stable.
10. The bot starts producing real revenue.

### Locked Strategy

- Do not jump to app/dashboard while the bot is not stable.
- Do not open customer publishing before admin testing is complete.
- Do not open ads assistant before there is a clear workflow.
- Do not run the Big Plan while basic tools/API providers still fail.
- Do not make broad changes to parts already stable.

### Next Phase - Big Plan / TOAN AAS SaaS Platform

Only start this after the current bot is stable.

The TOAN AAS Big Plan becomes a SaaS platform with:

1. Web app / Dashboard:
   - Customer accounts.
   - Order history.
   - Xu service history.
   - Tool/project history.
   - File/media management.
   - Video/content project management.

2. SaaS Billing:
   - Monthly/subscription packages.
   - Pay-as-you-go with Xu service credits.
   - Invoices/bills.
   - Revenue dashboard.
   - API/provider cost reports.

3. AI Tool Hub:
   - AI chat/script.
   - Image tools.
   - STT/transcription.
   - Translation/dubbing.
   - TTS/voice.
   - Video script/storyboard.
   - Image-to-video prompt pack.
   - AI Story Video Factory.
   - Trend/content research.

4. Automation Platform:
   - Content creation workflows.
   - Trend -> idea -> script -> image -> voice -> video -> review.
   - Admin review.
   - Export/download.
   - Admin-only publish.
   - Customer publish only after safety is proven.

5. Content / Affiliate / Ads Expansion:
   - Affiliate content workflow.
   - Proper disclosure and lawful sources.
   - Ads assistant admin-first.
   - TikTok/YouTube/Facebook publish tested admin-only first.
   - No viral/revenue guarantees.

6. ERP / Ops / Device / Backend Expansion:
   - Operations dashboard.
   - Backup/health.
   - Provider monitor.
   - API cost monitor.
   - Automation jobs.
   - Internal operator panel.

### Core Principle

TOAN AAS starts with the revenue bot first, then expands into the larger SaaS platform.

- The current bot is the revenue MVP.
- The Big Plan is the later phase after the MVP is stable.
- If the bot is not stable, return to fixing the bot.
- If a tool has not passed, do not sell/open that tool.
- If PayOS is not stable, use manual QR.
- If publish/ads is not safe, keep it admin-only or disabled.
- If an API provider fails, replace the provider or hide the tool.

Chưa quay lại kế hoạch lớn TOAN AAS.
Chưa làm app ngoài.
Chưa làm dashboard web.
Chưa làm ERP/Device Ops/SaaS.
Chưa mở customer affiliate vault, auto publish hoặc ads management.

## Current Priority

0. Test VIP/member/referral policy:
   - `/vip_policy`
   - `/member`
   - `/referral`
   - `/ref_stats`
   - `/profile`
   - `/pricing`
   - `/mode`
   - `/my_promos`
   - `/birthday`
   - `/set_birthday DD-MM`
   - `/start ref_<admin_or_test_user_id>` with a secondary new Telegram user if available
   - Approve that user's first bill with `/duyet <USER_ID> <Xu>` and confirm referral reward is based on base Xu only
   - Confirm tier keys/badges: `newbie`, `silver`, `gold`, `platinum`, `diamond`, `vip`
   - `/set_vip <USER_ID> platinum`
   - `/set_vip <USER_ID> vip`
   - `/clear_vip <USER_ID>`
   - `/grant_tier_promo <USER_ID> platinum`
   - `/birthday_gift_check <USER_ID>`
   - `/birthday_gift_grant <USER_ID>`
   - `/ref_admin <USER_ID>`
   - `/report_today` must include referral, tier promo and birthday gift summary
0. Test admin reporting and persistent modes:
   - `/admin_dashboard`
   - `/report_today`
   - `/report_week`
   - `/report_month`
   - `/report_ai_today`
   - `/report_chart_week`
   - `/mode`
   - `/chat_pro_on`, send one normal chat message, then `/chat_pro_off`
   - `/chat_deep_on`, send one normal chat message, then `/chat_deep_off`
0.1. Test final provider diagnostics:
   - `/report_ai_today` and `/report_ai_week`: must show offline fallback if Gemini/OpenAI quota fails.
   - `/tool_test_translate`, then `/tool_status`: Translation should show PASS after DeepL pass.
   - Send voice/audio, then run `/tool_test_stt` within 2 minutes without reply.
   - Reply voice/audio with `/tool_test_stt_debug`.
   - Reply image with `/tool_test_image_debug`.
   - `/payos_key_fingerprint`.
   - `/payos_official_debug`.
   - `/payos_debug_create`.
0.2. Test Trend/Image/Video status after the media audit patch:
   - `/feature_status`
   - `/trend_status`
   - `/trend_ai mỹ phẩm cho dân văn phòng`
   - `/trend_research mỹ phẩm cho dân văn phòng`
   - `/trend_live mỹ phẩm cho dân văn phòng` must report provider missing, no fake live data.
   - `/image_tools`
   - `/image_prompt máy hút bụi mini`
   - `/image_to_video_pack máy hút bụi mini`
   - `/ai_image ảnh sản phẩm máy hút bụi mini` must not charge if disabled.
   - `/video_provider_status`
   - `/media_factory chủ shop nhỏ dùng AI`
   - `/source_help`
   - `/dubbing_help`
   - `/story_video_factory truyện cổ tích tự sáng tác`
   - `/story_motion_prompt cô gái đi trong rừng cổ tích`
   - `/sales_ready`
   - `/tool_status`
   - `/providers`
1. Test `/legal` and the Legal button in `/start`.
2. Test `/terms`, `/privacy`, `/dieukhoan_xu`, `/refund_policy`, `/content_policy`, `/affiliate_policy`, `/ads_policy`.
3. Test website `/`, `/landing`, `/LOGO.png`, `/banner.png` and the legal footer.
4. Test `/media_factory`.
5. Test `/video_factory_flow`.
6. Test `/providers` and confirm PayOS still reports NEED DEBUG if checkout remains invalid.
7. Test `/sales_ready`.
8. Test image tools and tool audit commands.
9. Fix PayOS separately if checkout remains invalid.
10. Do not open customer publish or ads.
11. Do not collect social passwords/cards.
12. Keep legal gates before big plan modules.
13. Do not start big plan yet.

## Next After Foundation Passes

- Only enable OpenAI image generation/edit flags after admin explicitly confirms provider cost and test budget.
- Keep customer publishing, affiliate vault and ads automation hidden/internal.
- Do not build the big TOAN AAS platform plan until the current bot is Sales Ready.

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
