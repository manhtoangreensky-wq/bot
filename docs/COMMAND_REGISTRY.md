# COMMAND REGISTRY - TOAN AAS

Date: 2026-06-02
Source: `bot.py` local audit after Step 10
Registered Telegram commands: 203
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
| `/thucong` | `cmd_thanhtoan_thucong` | YES | Manual bill fallback. |
| `/beta_offer` | `cmd_beta_offer` | YES | Shows beta packages and customer workflow. |
| `/goi_beta` | `cmd_beta_offer` | YES | Vietnamese alias for `/beta_offer`. |
| `/ref` | `cmd_ref` | YES | Referral link and stats. |
| `/invite` | `cmd_invite` | YES | Alias to referral flow. |
| `/gopy` | `cmd_gopy` | YES | User feedback. |

## AI Tools

| Feature | Trigger | Cost | Refund? | Notes |
|---|---|---:|---:|---|
| Chat AI | Plain text message | Dynamic/free trial | YES | Gemini/OpenAI fallback path, paid exception refunds. |
| Voice/TTS | `Đọc voice: nội dung` or routed text | Provider choice | YES | Paid Fish Audio, fallback Edge TTS. |
| STT/audio | Voice/mp3/m4a message | Dynamic | YES | Deepgram flow. |
| Background removal | Photo message | Provider choice | YES | RemoveBG/Cutout provider choice/fallback. |
| Downloader | TikTok/YouTube/Facebook URL | Dynamic | YES | Existing downloader route. |

## Video/Affiliate Commands

| Command | Handler | In `/menu`? | Notes |
|---|---|---:|---|
| `/film` | `cmd_film` | YES | Video Script Lite, no render, no auto publish. |
| `/video_script` | `cmd_film` | YES | Alias for `/film`. |
| `/addlink` | `cmd_addlink` | YES | Store affiliate URL for current user. |
| `/links` | `cmd_links` | YES | List active affiliate links. |
| `/campaign` | `cmd_campaign` | YES | User-facing campaign entry. |
| `/campaign_new` | `cmd_campaign_new` | YES | Campaign creation helper. |
| `/campaigns` | `cmd_campaigns` | YES | Campaign listing. |
| `/addcal` | `cmd_addcal` | YES | Add manual content calendar item. |
| `/calendar` | `cmd_calendar` | YES | View calendar. |
| `/calendar_plan` | `cmd_calendar_plan` | Admin/Menu | Internal calendar planning. |
| `/publish_done` | `cmd_publish_done` | YES | Manual record of published post. |
| `/performance_add` | `cmd_performance_add` | YES | Manual metrics input. |
| `/performance_report` | `cmd_performance_report` | YES | Manual performance rollup. |
| `/growth_ai` | `cmd_growth_ai` | YES | AI Growth Coach, 120 Xu for normal users. |
| `/campaign_report` | `cmd_campaign_report` | YES | TXT/CSV campaign report export. |
| `/export_report` | `cmd_campaign_report` | YES | Alias for campaign report export. |
| `/posts` | `cmd_posts` | YES | Recent published posts. |
| `/growth_loop` | `cmd_growth_loop` | YES | User rule-based growth loop, admin can request manual mode. |

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
