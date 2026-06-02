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

1. PayOS dynamic QR debug.
2. AAS payment content.
3. Manual fallback correct Xu.
4. Backup DB send file.
5. Sales readiness.
6. Then real payment test.
7. Do not start big plan yet.

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
- Launch Bonus: 30 if first 50k package purchase
- Promo bonus: 150
- Total Xu added: 680 if Launch Bonus applies; 650 if the user already used 50k Launch Bonus
- Duplicate webhook/checkpayos must not add base or bonus again.

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
- Customer social account connection.
- Risk keyword checker.
- Compliance checker.
- Paid service package for publish/ads management.
- GitHub Copilot dev workflow.
- Legal Docs Lite with OpenLaw/OpenLaws.
- Legal templates for service contracts and warranty documents.

## Future Publish Rule - Admin First

- Publish workflow belongs to TOAN AAS Lab/admin sandbox, not the current customer bot.
- Build and test publishing with admin-owned pages/accounts/channels first.
- Required future flags stay OFF by default: `publish_workflow`, `customer_publish`, `auto_publish`, `ads_assistant`.
- `admin_publish` is admin/internal only and requires explicit approval before live testing.
- No customer social account connection, no customer auto publish, no customer ads management in the current bot.
- If customer publish opens later, it must be a separate paid feature with account permission, approval gate, audit log, failure handling and admin disable switch.

Codex không tự làm task tiếp theo.
