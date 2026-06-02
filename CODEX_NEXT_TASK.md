# NEXT TASK OPTIONS - STABLE REVENUE BOT ONLY

Chưa quay lại kế hoạch lớn TOAN AAS.
Chưa làm app ngoài.
Chưa làm dashboard web.
Chưa làm ERP/Device Ops/SaaS.

## Current priority

Run the real PayOS payment test with Promotion Policy V2.1 before selling beta.

Manual sequence:

- MVP done: `/promo_seed_policy`, `/promo <code>`, `/khuyenmai`, admin list/create/disable, percent bonus on PayOS paid order.
- `BETA50` is limited/internal only; public first top-up offer is `FIRST30`.
- Không đổi bảng giá gốc.
- Không đụng PayOS packages nếu chưa cần.

```text
/backup_db
/providers
/promo_seed_policy
/promo FIRST30
/naptien
# choose 20k or higher and pay real QR
/checkpayos <order_code>   # only if webhook has not credited yet
/mark_payos_test pass order=<order_code> note="FIRST30 OK"
/sales_ready
```

Expected for 20k + FIRST30:

- Base Xu: 200
- Promo bonus: 60
- Total Xu added: 260
- Duplicate webhook/checkpayos must not add base or bonus again.

## Option A - Run real PayOS 10k test manually

- Test without promo if needed.
- Test with `/promo FIRST30`.
- Confirm dashboard and user balance.
- Mark pass only after manual verification.

## Option B - First customer beta launch

- Open beta for 3-10 users.
- Offer: 200 Xu trial + FIRST30 for first top-up while active.
- Watch `/dashboard`, `/performance_report`, `/sales_ready`.

## Option C - Sales copy/posts

- Write Facebook/Zalo/TikTok launch posts.
- Write direct-message closing scripts.
- Write onboarding messages for first beta customers.

## Option D - Video Script template packs

- Improve `/film` output by niche.
- Add templates for affiliate, product review, story, education, local service.
- No render.

## Option E - AI Caption Variant Generator

- Generate 5 hook/caption/CTA variants from winning posts.
- Use `/growth_ai` and `/performance_report` data when available.
- No auto publish.

## Option F - Trial top-up migration for old users

If admin wants to top up users who already received 150 Xu to 200 Xu:

- Write a safe one-time migration.
- Only top up users with old trial credit event.
- Add exactly 50 Xu once.
- Record clear credit event.
- Admin approval required before running.

## Option G - Extract config.py safely

- Separate ENV/constants.
- Do not change behavior.

## Option H - Extract db.py safely

- Separate DB helpers.
- Do not change schema.

## Future Backlog

- GitHub Copilot dev workflow
- Legal Docs Lite with OpenLaw/OpenLaws
- Legal templates for service contracts and warranty documents

Codex không tự làm task tiếp theo.
