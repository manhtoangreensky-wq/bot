# COMMAND REGISTRY - TOAN AAS

Date: 2026-06-12
Source: `bot.py` local audit after Step 11
Registered Telegram commands: 224
Registered callback groups: 9

## User Commands

| Command | Handler | In `/menu`? | Notes |
|---|---|---:|---|
| `/start` | `cmd_start` | YES | Creates/loads user, handles referral payload, shows onboarding funnel. |
| `/menu` | `cmd_menu` | YES | Reuses `/start` menu flow. |
| `/help` | `cmd_help` | YES | Quick command guide for user/admin. |
| `/commands` | `cmd_help` | YES | Alias for `/help`. |
| `/profile` | `cmd_profile` | YES | Balance, VIP, referral status. |
| `/naptien` | `cmd_naptien` | YES | PayOS package selection. |
| `/pricing` | `cmd_pricing` | YES | User-facing Pricing Engine V2 table. |
| `/banggia` | `cmd_pricing` | YES | Vietnamese alias for `/pricing`. |
| `/chat_pro` | `cmd_chat_pro` | YES | Paid Pro/Deep chat with upfront Xu price. |
| `/models` | `cmd_models` | YES | User-facing AI tier/model status. |
| `/ai_models` | `cmd_models` | YES | Alias for `/models`. |
| `/thucong` | `cmd_thanhtoan_thucong` | YES | Manual bill fallback. |
| `/beta_offer` | `cmd_beta_offer` | YES | Shows beta packages and customer workflow. |
| `/goi_beta` | `cmd_beta_offer` | YES | Vietnamese alias for `/beta_offer`. |
| `/promo` | `cmd_promo` | YES | Saves one promo code for the next PayOS order; no stacking and no pre-payment credit. |
| `/magiamgia` | `cmd_promo` | YES | Vietnamese alias for `/promo`. |
| `/gift` | `cmd_gift` | YES | Redeems gift/reward Xu codes immediately when valid. |
| `/nhanqua` | `cmd_gift` | YES | Vietnamese alias for `/gift`. |
| `/khuyenmai` | `cmd_promo_guide` | YES | Shows Promotion Policy V2.1 and recommended code order. |
| `/uudai` | `cmd_promo_guide` | YES | Alias for `/khuyenmai`. |
| `/promos` | `cmd_promo_guide` | YES | Alias for `/khuyenmai`. |
| `/ref` | `cmd_ref` | YES | Referral link and stats. |
| `/invite` | `cmd_invite` | YES | Alias to referral flow. |
| `/gopy` | `cmd_gopy` | YES | User feedback. |
| `/support` | `cmd_support` | YES | Opens the unified support/ticket category menu. |
| `/tickets` | `cmd_tickets` | YES | Lists only the current user's support tickets. |
| `/ticket_status` | `cmd_tickets` | YES | Alias for the current user's ticket list. |
| `/memory` | `cmd_memory` | YES | Opens Notes/Documents storage policy and memory command guide. |
| `/memory_plan` | `cmd_memory_plan` | YES | Shows 50MB free storage policy and +50MB/month add-on pricing. |
| `/memory_status` | `cmd_memory_status` | YES | Shows user's text/file/total storage usage. |
| `/note` | `cmd_note` | YES | Saves a text note when memory is public/admin-enabled and quota allows. |
| `/remind` | `cmd_remind` | YES | Creates a reminder; text counts toward storage quota. |
| `/doc_tools` | `cmd_doc_tools` | YES | Opens Document/PDF tools from the Notes/Documents menu. |
| `/pdf_to_word` | `cmd_pdf_to_word` | YES | Reply to a PDF and convert text PDF to Word when local engine is available. |
| `/image_to_pdf` | `cmd_image_to_pdf` | YES | Reply to an image and create PDF using local engine. |
| `/pdf_to_images` | `cmd_pdf_to_images` | YES | Reply to a PDF and export pages to image(s) when PyMuPDF is available. |
| `/compress_pdf` | `cmd_compress_pdf` | YES | Reply to a PDF and compress locally when engine is available. |
| `/split_pdf` | `cmd_split_pdf` | YES | Reply to a PDF and split selected pages. |
| `/merge_pdf` | `cmd_merge_pdf` | YES | Planned/admin-tested merge workflow; does not charge Xu while unavailable. |

## AI Tools

| Feature | Trigger | Cost | Refund? | Notes |
|---|---|---:|---:|---|
| Chat AI | Plain text message | Dynamic/free trial | YES | Gemini/OpenAI fallback path, paid exception refunds. |
| Chat Pro | `/chat_pro` | 20-200 Xu | YES | Gemini/OpenAI router, Claude/Grok planned only. |
| Voice/TTS | `Đọc voice: nội dung` or routed text | Provider choice | YES | Paid Fish Audio, fallback Edge TTS. |
| STT/audio | Voice/mp3/m4a message | Dynamic | YES | Deepgram flow. |
| Background removal | Photo message | Provider choice | YES | RemoveBG/Cutout provider choice/fallback. |
| Downloader | TikTok/YouTube/Facebook URL | Dynamic | YES | Existing downloader route. |

## Video Customer Commands

| Command | Handler | In `/menu`? | Notes |
|---|---|---:|---|
| `/film` | `cmd_film` | YES | Video Script Lite, no render, no auto publish. |
| `/video_script` | `cmd_film` | YES | Alias for `/film`. |
| `/growth_ai` | `cmd_growth_ai` | YES | AI Growth Coach, 120 Xu for normal users. |
| `/campaign_report` | `cmd_campaign_report` | YES | TXT/CSV campaign report export. |
| `/export_report` | `cmd_campaign_report` | YES | Alias for campaign report export. |

## Internal Affiliate/Publish Backlog Commands

These handlers remain in code for admin/internal testing but are blocked for normal users.

| Command | Handler | Public? | Notes |
|---|---|---:|---|
| `/addlink` | `cmd_addlink` | NO | Internal affiliate vault/storage. |
| `/links` | `cmd_links` | NO | Internal affiliate link listing. |
| `/campaign` | `cmd_campaign` | NO | Internal campaign setup. |
| `/campaign_new` | `cmd_campaign_new` | NO | Internal campaign helper. |
| `/campaigns` | `cmd_campaigns` | NO | Internal campaign listing. |
| `/addcal` | `cmd_addcal` | NO | Internal content calendar. |
| `/calendar` | `cmd_calendar` | NO | Internal calendar listing. |
| `/calendar_plan` | `cmd_calendar_plan` | NO | Internal calendar planning. |
| `/publish_done` | `cmd_publish_done` | NO | Internal manual publish record. |
| `/performance_add` | `cmd_performance_add` | NO | Internal manual metrics input. |
| `/performance_report` | `cmd_performance_report` | NO | Internal manual performance rollup. |
| `/posts` | `cmd_posts` | NO | Internal published post list. |
| `/growth_loop` | `cmd_growth_loop` | NO | Internal rule-based growth loop. |

## Admin Commands

Admin menu groups in `bot.py` should show a short purpose and example syntax for high-risk commands, especially Xu, bill, package wallet, provider, freeze, queue, and refund commands. Do not show secrets or raw provider responses in admin menus.

| Command | Handler | Protected? | In admin menu? | Notes |
|---|---|---:|---:|---|
| `/dashboard` | `cmd_dashboard` | YES | YES | Main admin dashboard. |
| `/admin` | `cmd_dashboard` | YES | YES | Alias for dashboard. |
| `/stats` | `cmd_stats` | YES | YES | Admin stats. |
| `/pending` | `cmd_pending` | YES | YES | Pending manual bills. |
| `/duyet` | `cmd_duyet` | YES | YES | Approve manual bill. |
| `/fx_price_test` | `cmd_fx_price_test` | YES | YES | Preview USD/CNY fixed-rate conversion; creates no payment and credits no Xu. |
| `/tuchoi` | `cmd_tuchoi` | YES | YES | Reject manual bill. |
| `/add` | `cmd_admin_add` | YES | YES | Add credit. |
| `/setvip` | `cmd_setvip` | YES | YES | Set member tier: silver/gold/platinum/diamond/vip only. |
| `/settier` | `cmd_set_vip` | YES | YES | Set member tier with the current tier policy. |
| `/set_member_tier` | `cmd_set_vip` | YES | YES | Alias for `/settier`. |
| `/profile_user` | `cmd_profile_user` | YES | YES | Admin user profile lookup. |
| `/ledger_user` | `cmd_ledger_user` | YES | YES | Admin Xu ledger lookup. |
| `/member_user` | `cmd_member_user` | YES | YES | Admin member tier/benefit lookup. |
| `/admin_gopy` | `cmd_admin_gopy` | YES | YES | View feedback. |
| `/backup_db` | `cmd_backup_db` | YES | YES | Sends DB file to admin if available. |
| `/providers` | `cmd_providers` | YES | YES | Provider key status, configured/missing only. |
| `/costs` | `cmd_costs` | YES | YES | Cost control and paid-provider risk summary. |
| `/sales_ready` | `cmd_sales_ready` | YES | YES | NOT READY/BETA READY readiness check; no auto SALES READY. |
| `/system_public_status` | `cmd_system_public_status` | YES | YES | Public tool surface summary; no secrets and no provider calls. |
| `/tool_public_status` | `cmd_tool_public_status` | YES | YES | Alias-style public tool surface summary for launch checks. |
| `/image_edit_status` | `cmd_image_edit_status` | YES | YES | Image edit provider readiness matrix; never shows keys and does not fake output. |
| `/tool_test_image_edit` | `cmd_tool_test_ai_image_edit` | YES | YES | Alias for the real OpenAI image edit smoke test; requires replying to an image. |
| `/tool_test_gemini_image_edit` | `cmd_tool_test_gemini_image_edit` | YES | YES | Guarded Gemini image-edit readiness check; no fake image and no Xu charge. |
| `/tool_test_shopaikey_image_edit` | `cmd_tool_test_shopaikey_image_edit` | YES | YES | Guarded ShopAIKey image-edit readiness check; no fake image and no Xu charge. |
| `/image_edit_public_open` | `cmd_image_edit_public_open` | YES | YES | Owner-only gate; opens image edit public only after real provider readiness and smoke PASS. |
| `/image_edit_public_close` | `cmd_image_edit_public_close` | YES | YES | Owner-only gate; returns image edit to admin-only. |
| `/chat_ai_status` | `cmd_chat_ai_status` | YES | YES | Text/vision Chat AI readiness and image-analysis provider status. |
| `/toanaas_ai_status` | `cmd_toanaas_ai_status` | YES | YES | TOAN AAS assistant knowledge-base and AI provider readiness. |
| `/video_public_status` | `cmd_video_public_status` | YES | YES | Video public flags, provider smoke, worker readiness, tier status and blocked tiers. |
| `/video_gate_status` | `cmd_video_gate_status` | YES | YES | Video gate matrix for planning, frame video, Video AI, image/video-to-video and long render. |
| `/video_tier_status` | `cmd_video_tier_status` | YES | YES | Video 200/300/400/500/600/800 tier status plus 1000/1500 coming-soon guard. |
| `/video_cost_status` | `cmd_video_cost_status` | YES | YES | Video 200/300/400/500/600/800 cost ratio and margin status; no payment changes. |
| `/video_beta_limits` | `cmd_video_beta_limits` | YES | YES | Current public video beta limits, confirm/job-lock policy and duration caps. |
| `/video_beta_open` | `cmd_video_beta_open` | YES | YES | Opens only eligible 200/300/400/500/600/800 Video AI tiers after smoke and cost gates pass. |
| `/video_beta_close` | `cmd_video_beta_close` | YES | YES | Closes Video AI public beta without touching planning/storyboard or payment logic. |
| `/video_open_high_tiers` | `cmd_video_open_high_tiers` | YES | YES | Opens controlled 500/600/800 Video AI tiers after provider smoke/cost override; keeps 1000/1500/long/premium OFF. |
| `/video_close_high_tiers` | `cmd_video_close_high_tiers` | YES | YES | Closes only 500/600/800 tiers and leaves lower beta tiers unchanged. |
| `/video_smoke_tier_500` | `cmd_video_smoke_tier_500` | YES | YES | Admin-only/no-Xu smoke path for the 500 Xu tier; delegates to ShopAIKey video smoke. |
| `/video_smoke_tier_600` | `cmd_video_smoke_tier_600` | YES | YES | Admin-only/no-Xu smoke path for the 600 Xu sales tier; delegates to ShopAIKey video smoke. |
| `/video_smoke_tier_800` | `cmd_video_smoke_tier_800` | YES | YES | Admin-only/no-Xu smoke path for the 800 Xu high tier; delegates to ShopAIKey video smoke. |
| `/runtime` | `cmd_runtime` | YES | YES | Runtime/webhook diagnostics. |
| `/data_status` | `cmd_data_status` | YES | YES | Persistent DB/backup/volume status. |
| `/storage_status` | `cmd_storage_status` | YES | YES | Admin read-only storage policy and aggregate usage; no secrets. |
| `/storage_user` | `cmd_storage_user` | YES | YES | Admin read-only storage usage for one user. |
| `/cleanup_temp_files` | `cmd_cleanup_temp_files` | YES | YES | Admin cleanup policy/status placeholder; does not delete files directly. |
| `/local_worker_status` | `cmd_local_status` | YES | YES | Alias for Local Worker/Frame Video readiness; hides tokens/secrets. |
| `/payos_test_plan` | `cmd_payos_test_plan` | YES | YES | Real PayOS 10k manual test checklist. |
| `/promo_seed_policy` | `cmd_promo_seed_policy` | YES | YES | Seeds Promotion Policy V2.1 codes: FIRST30, SECOND15, WEEKLY10, MONTHLY20, DAILY5, BETA50. |
| `/promo_seed_beta` | `cmd_promo_seed_beta` | YES | YES | Compatibility alias for `/promo_seed_policy`. |
| `/promo_list` | `cmd_promo_list` | YES | YES | Lists recent promo codes and usage. |
| `/promo_create` | `cmd_promo_create` | YES | YES | Creates a new promo code without overwriting existing codes. |
| `/promo_disable` | `cmd_promo_disable` | YES | YES | Disables a promo code without deleting data. |
| `/gift_create` | `cmd_gift_create` | YES | YES | Creates an immediate Xu gift/reward code. |
| `/gift_seed_beta` | `cmd_gift_seed_beta` | YES | YES | Seeds default beta gift codes BETA5 through BETA1000. |
| `/gift_list` | `cmd_gift_list` | YES | YES | Lists gift/reward codes and usage. |
| `/gift_disable` | `cmd_gift_disable` | YES | YES | Disables a gift/reward code without deleting data. |
| `/mark_payos_test` | `cmd_mark_payos_test` | YES | YES | Admin records PayOS real test PASS/FAIL/NOT_TESTED; does not alter payments. |
| `/pricing_admin` | `cmd_pricing_admin` | YES | YES | Admin-only formula/constants for Pricing Engine V2. |
| `/pricing_audit` | `cmd_pricing_audit` | YES | YES | Admin-only V6 feature/price/source/guard audit; no secrets or raw provider responses. |
| `/banggia` | `cmd_pricing` | YES | YES | Public/admin price menu entry shown in admin menu for quick access. |
| `/package_catalog` | `cmd_package_catalog` | YES | YES | Lists admin-grantable combo/monthly package catalog. |
| `/grant_combo` | `cmd_grant_combo` | YES | YES | Admin grants a combo package; does not add Xu or rank/top-up points. |
| `/grant_monthly` | `cmd_grant_monthly` | YES | YES | Admin grants a monthly package with expiry; does not add Xu or rank/top-up points. |
| `/user_packages` | `cmd_user_packages` | YES | YES | Shows a user's active/revoked package wallet and remaining item slots. |
| `/adjust_package` | `cmd_adjust_package` | YES | YES | Admin adjusts package item quantities without changing Xu balance. |
| `/revoke_package` | `cmd_revoke_package` | YES | YES | Admin revokes a package while preserving history. |
| `/finance_dashboard` | `cmd_finance_dashboard` | YES | YES | Internal revenue/expense/profit dashboard for today, month, and year. |
| `/revenue_report` | `cmd_revenue_report` | YES | YES | Internal cash revenue report by month or year; accepts `YYYY-MM` or `YYYY`. |
| `/expense_report` | `cmd_expense_report` | YES | YES | Internal expense report by month or year. |
| `/profit_report` | `cmd_profit_report` | YES | YES | Internal profit/loss estimate by month or year, including annual totals. |
| `/expense_add` | `cmd_expense_add` | YES | YES | Add operating expense manually; no payment/Xu logic changes. |
| `/expense_add_pre` | `cmd_expense_add_pre` | YES | YES | Add pre-establishment expense for internal management reporting. |
| `/expense_edit` | `cmd_expense_edit` | YES | YES | Correct an expense field without deleting history. |
| `/expense_delete` | `cmd_expense_delete` | YES | YES | Soft-delete an expense with a reason; does not DROP or delete DB data. |
| `/finance_export` | `cmd_finance_export` | YES | YES | Export finance revenue, expense, and usage CSV files for a month or year. |
| `/tax_status` | `cmd_tax_status` | YES | YES | Show the current-month internal tax estimate using admin-configured rates. |
| `/tax_report` | `cmd_tax_report` | YES | YES | Show an internal tax-prep estimate for `YYYY-MM` or `YYYY`; not an official filing. |
| `/tax_export` | `cmd_tax_export` | YES | YES | Export five accounting-prep CSV files for a month or year, including empty headers. |
| `/tax_config` | `cmd_tax_config` | YES | YES | View or update manual tax assumptions; no tax law is hard-coded. |
| `/internal_docs` | `cmd_internal_docs` | YES | YES | Open the admin-only internal business archive by department. |
| `/search_internal_doc` | `cmd_search_internal_doc` | YES | YES | Search internal archive metadata; never exposes provider secrets. |
| `/ticket_admin` | `cmd_ticket_admin` | YES | YES | Opens CSKH/Ticket administration with new, high-priority, refund, search and statistics views. |
| `/ticket_overdue` | `cmd_ticket_overdue` | YES | YES | Lists new/reviewing/refund tickets older than 24h and provider waits older than 72h. |
| `/support_persona_test <message>` | `cmd_support_persona_test` | YES | YES | Preview the deterministic CSKH classification, escalation decision and safe reply without creating a ticket or changing Xu. |
| `/support_auto_test <message>` | `cmd_support_auto_test` | YES | YES | Preview Support Auto Reply V3.1 category, priority, ticket decision, admin alert and reply without creating a ticket. |
| `/shopaikey_status` | `cmd_shopaikey_status` | YES | YES | ShopAIKey admin status, usage and smoke-test snapshots. |
| `/shopaikey_status_debug` | `cmd_shopaikey_status_debug` | YES | YES | Sanitized component snapshots for diagnosing status rendering; never shows secrets. |
| `/shopaikey_usage` | `cmd_shopaikey_usage` | YES | YES | ShopAIKey usage monitor, no key leakage. |
| `/shopaikey_video_job` | `cmd_shopaikey_video_job` | YES | YES | Query ShopAIKey video job status. |
| `/tool_test_shopaikey` | `cmd_tool_test_shopaikey` | YES | YES | Admin chat smoke test. |
| `/tool_test_shopaikey_image` | `cmd_tool_test_shopaikey_image` | YES | YES | Admin image smoke test. |
| `/tool_test_shopaikey_video` | `cmd_tool_test_shopaikey_video` | YES | YES | Admin video smoke test. |
| `/tool_test_shopaikey_tts` | `cmd_tool_test_shopaikey_tts` | YES | YES | Admin TTS smoke test. |
| `/key4u_status` | `cmd_key4u_status` | YES | YES | Key4U parallel provider hub status, smoke snapshots, usage endpoint state, and masked key. |
| `/key4u_usage` | `cmd_key4u_usage` | YES | YES | Key4U usage dashboard: remote endpoint status, manual/dashboard balance, local usage events, warnings; no key leakage. |
| `/key4u_set_manual_balance` | `cmd_key4u_set_manual_balance` | YES | YES | Store admin-observed Key4U dashboard balance for reporting when remote balance endpoint is unknown. |
| `/tool_test_key4u_chat` | `cmd_tool_test_key4u_chat` | YES | YES | Key4U chat smoke test; no Xu charge and no prompt/response logging. |
| `/tool_test_key4u_vision` | `cmd_tool_test_key4u_vision` | YES | YES | Reply to an image to test Key4U vision model; no Xu charge. |
| `/tool_test_key4u_image` | `cmd_tool_test_key4u_image` | YES | YES | Guarded Key4U image generation placeholder until endpoint docs are verified. |
| `/tool_test_key4u_image_edit` | `cmd_tool_test_key4u_image_edit` | YES | YES | Reply to an image to smoke test Key4U image edit/nano-banana edit. |
| `/tool_test_key4u_video` | `cmd_tool_test_key4u_video` | YES | YES | Key4U video create smoke test; submits admin-only job if provider accepts. |
| `/tool_test_key4u_video_model` | `cmd_tool_test_key4u_video_model` | YES | YES | Key4U video create smoke test for one explicit model; no Xu charge and no public routing. |
| `/tool_test_key4u_video_all` | `cmd_tool_test_key4u_video_all` | YES | YES | Lists configured Key4U video model candidates without submitting expensive batch jobs. |
| `/key4u_video_job` | `cmd_key4u_video_job` | YES | YES | Query Key4U video job status by provider task id. |
| `/tool_test_key4u_tts` | `cmd_tool_test_key4u_tts` | YES | YES | Key4U TTS smoke test; returns NEED_DOCS unless endpoint/model are configured; no Xu charge. |
| `/tool_test_key4u_stt` | `cmd_tool_test_key4u_stt` | YES | YES | Reply to audio to test Key4U STT if endpoint/model are configured; no Xu charge. |
| `/tool_test_key4u_suno` | `cmd_tool_test_key4u_suno` | YES | YES | Key4U Suno/music smoke test; guarded by explicit endpoint/model docs; no Xu charge. |
| `/key4u_suno_job` | `cmd_key4u_suno_job` | YES | YES | Query Key4U Suno/music job status by provider task id. |
| `/tool_test_key4u_rerank` | `cmd_tool_test_key4u_rerank` | YES | YES | Key4U rerank smoke test if endpoint/model are configured; no prompt/response logging. |
| `/tool_test_asr` | `cmd_tool_test_asr` | YES | YES | Reply a short audio/video file to smoke test Deepgram ASR with no Xu charge. |
| `/tool_test_translate [text] [lang]` | `cmd_tool_test_translate` | YES | YES | Smoke test translation routing/fallback with a short text. |
| `/tool_test_tts_for_dub` | `cmd_tool_test_tts` | YES | YES | Alias for TTS smoke when verifying dubbing readiness. |
| `/subtitle_dub_status` | `cmd_subtitle_dub_status` | YES | YES | Subtitle/dub pipeline readiness: ASR, translation, TTS, mux and public mode gates. |
| `/subtitle_status` | `cmd_subtitle_dub_status` | YES | YES | Alias for subtitle/dub readiness status. |
| `/tool_test_video_subtitle` | `cmd_tool_test_video_subtitle` | YES | YES | Reply a short video to test ASR to SRT; admin-only and no Xu charge. |
| `/tool_test_video_dub [text]` | `cmd_tool_test_video_dub` | YES | YES | Test dubbing TTS output from replied media or short text; mux remains capability-guarded. |
| `/tool_test_subtitle_plus_dub` | `cmd_tool_test_subtitle_plus_dub` | YES | YES | Reply a short video to test ASR, subtitle, and TTS outputs without charging Xu. |
| `/video_dub_public_open` | `cmd_video_dub_public_open` | YES | YES | Owner-only gate; opens subtitle/dub modes only after provider readiness and smoke PASS. |
| `/video_dub_public_close` | `cmd_video_dub_public_close` | YES | YES | Owner-only gate; closes selected subtitle/dub public modes. |
| `/clear_frame_video_error` | `cmd_clear_frame_video_error` | YES | YES | Clear only the stored frame-video last-error display; does not alter jobs or Xu. |
| `/video_price_test <seconds> <type> <tier> <addon>` | `cmd_video_price_test` | YES | YES | Preview itemized video, subtitle, dubbing, total Xu, and VND pricing without creating a job or charging Xu. |
| `/maintenance_status` | `cmd_maintenance_status` | YES | YES | Maintenance/freeze status overview. |
| `/maintenance_on` | `cmd_maintenance_on` | YES | YES | Enable maintenance mode. |
| `/maintenance_off` | `cmd_maintenance_off` | YES | YES | Disable maintenance mode. |
| `/freeze_tools` | `cmd_freeze_tools` | YES | YES | Freeze tool usage. |
| `/unfreeze_tools` | `cmd_unfreeze_tools` | YES | YES | Unfreeze tool usage. |
| `/provider_freeze` | `cmd_provider_freeze` | YES | YES | Freeze a provider by name/reason. |
| `/provider_unfreeze` | `cmd_provider_unfreeze` | YES | YES | Unfreeze a provider by name. |
| `/freeze_status` | `cmd_freeze_status` | YES | YES | ShopAIKey video freeze, credit, error-window and queue overview. |
| `/freeze_video` | `cmd_freeze_video` | YES | YES | Manually freeze public ShopAIKey video only; does not touch image. |
| `/unfreeze_video` | `cmd_unfreeze_video` | YES | YES | Manually unfreeze public ShopAIKey video guard; public flags still apply. |
| `/queue_status` | `cmd_queue_status` | YES | YES | ShopAIKey video queue counts and stale cleanup status. |
| `/job_status` | `cmd_job_status` | YES | YES | Sanitized ShopAIKey job status by internal job id. |
| `/refund_job` | `cmd_refund_job` | YES | YES | Idempotent manual refund for a ShopAIKey job if Xu was deducted. |
| `/clear_job_lock` | `cmd_clear_job_lock` | YES | YES | Clear stuck public video active jobs for a user, refunding deducted Xu when possible. |
| `/checkpayos` | `cmd_checkpayos` | YES | System menu | PayOS order check. |
| `/telegram_status` | `cmd_telegram_status` | YES | System menu | Telegram update mode. |
| `/telegram_takeover` | `cmd_telegram_takeover` | YES | System menu | Reclaim Telegram webhook/polling. |
| `/customer_surface` | `cmd_customer_surface` | YES | Hidden | Checks public surface leakage. |

## Operator Commands

| Group | Commands | Protected? | Notes |
|---|---|---:|---|
| Operator core | `/operator`, `/operator_menu`, `/operator_contract`, `/operator_status`, `/operator_dashboard`, `/operator_audit`, `/operator_smoke` | YES | Internal admin/operator surface. |
| Autopilot | `/brain`, `/autopilot`, `/operator_loop`, `/operator_launch`, `/operator_auto`, `/operator_build` | YES | No customer exposure. |
| Head brain launch | `/tao_video`, `/boss_video`, `/head_brain`, `/head_run`, `/operator_contract`, `/goal_audit` | YES | Admin gives a simple topic/platform order; bot creates gated video jobs/tasks and returns worker/review/publish handoff. |
| Missions | `/mission_add`, `/missions`, `/mission_claim`, `/mission_prompt`, `/mission_run`, `/mission_workorders`, `/mission_complete` | YES | Internal work order flow. |
| Workers | `/worker_next`, `/worker_intake`, `/worker_autorun`, `/worker_pack`, `/operator_worker_spec` | YES | Internal worker handoff. |
| Film factory internal | `/film_blueprint`, `/film_series`, `/film_review`, `/film_rewrite`, `/film_approve`, `/film_project_pack`, `/scene_pack`, `/storyboard_crop`, `/compose_video` | YES | No render API added in Step 6. |
| Reference/remix | `/reference_pack`, `/reference_videos`, `/reference_add`, `/reference_analyze`, `/reference_build`, `/reference_scan`, `/viral_remix` | YES | Reference video workflow. |
| Publish/review internal | `/publish_pack`, `/review_gate`, `/queue_publish`, `/approve_publish`, `/approve_ready`, `/publish_queue`, `/publish_cockpit`, `/publisher_handoff`, `/publisher_run`, `/publisher_auto_check`, `/publisher_auto` | YES | Still gated; no social API auto-publish added. |
| Assets/jobs/tasks | `/asset_add`, `/assets`, `/asset_send`, `/review_video`, `/job_report`, `/job_context`, `/job_ready`, `/task_plan`, `/tasks`, `/next_task`, `/task_prompt`, `/task_handoff`, `/task_set`, `/output_acceptance` | YES | Internal production ops. |
| Affiliate/revenue internal | `/affiliate_add`, `/affiliate_seed`, `/affiliate_import`, `/affiliates`, `/affiliate_profile`, `/affiliate_match`, `/affiliate_ideas`, `/affiliate_related`, `/affiliate_bundle`, `/affiliate_report`, `/affiliate_decisions`, `/affiliate_scale`, `/money_pack`, `/affiliate_cockpit`, `/revenue_destinations`, `/tracking_report`, `/postback_setup`, `/scale_plan`, `/scale_execute`, `/growth` | YES | Admin/operator expansion surface. |
| Channel/platform | `/channel_add`, `/channels`, `/channel_router`, `/channel_publish_set`, `/publish_readiness`, `/publisher_status`, `/publisher_capabilities`, `/platform_adapters` | YES | Capability/status only. |

## Callback Registry

| Pattern | Handler | Status |
|---|---|---|
| `menu|` | `handle_menu_callback` | Active, unchanged. |
| `ticket|` | `handle_ticket_callback` | Active; public ticket creation/lookup and admin-only ticket actions. |
| `prov|` | `handle_provider_choice` | Active, unchanged. |
| `pkg|` | `handle_package_choice` | Active, unchanged. |
| `job|` | `handle_video_job_callback` | Active, unchanged. |
| `pipe|` | `handle_pipeline_callback` | Active, unchanged. |
| `trend|` | `handle_trend_callback` | Active, unchanged. |
| `creative|` | `handle_creative_callback` | Active, unchanged. |
| `task|` | `handle_task_callback` | Active, unchanged. |
| `opmenu|` | `handle_operator_menu_callback` | Active, unchanged. |

## Missing Registration

| Function | Handler registered? | Action |
|---|---:|---|
| `cmd_publish_done_manual` | NO | Internal helper called by `cmd_publish_done`; no handler needed. |
| `cmd_performance_add_manual` | NO | Internal helper called by `cmd_performance_add`; no handler needed. |
| `cmd_growth_loop_manual` | NO | Internal helper called by `cmd_growth_loop`; no handler needed. |
