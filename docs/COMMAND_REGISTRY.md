# COMMAND REGISTRY - TOAN AAS

Date: 2026-06-02
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

| Command | Handler | Protected? | In admin menu? | Notes |
|---|---|---:|---:|---|
| `/dashboard` | `cmd_dashboard` | YES | YES | Main admin dashboard. |
| `/admin` | `cmd_dashboard` | YES | YES | Alias for dashboard. |
| `/stats` | `cmd_stats` | YES | YES | Admin stats. |
| `/pending` | `cmd_pending` | YES | YES | Pending manual bills. |
| `/duyet` | `cmd_duyet` | YES | YES | Approve manual bill. |
| `/tuchoi` | `cmd_tuchoi` | YES | YES | Reject manual bill. |
| `/add` | `cmd_admin_add` | YES | YES | Add credit. |
| `/setvip` | `cmd_setvip` | YES | YES | VIP flag. |
| `/admin_gopy` | `cmd_admin_gopy` | YES | YES | View feedback. |
| `/backup_db` | `cmd_backup_db` | YES | YES | Sends DB file to admin if available. |
| `/providers` | `cmd_providers` | YES | YES | Provider key status, configured/missing only. |
| `/costs` | `cmd_costs` | YES | YES | Cost control and paid-provider risk summary. |
| `/sales_ready` | `cmd_sales_ready` | YES | YES | NOT READY/BETA READY readiness check; no auto SALES READY. |
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
| `/runtime` | `cmd_runtime` | YES | System menu | Runtime/webhook diagnostics. |
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
