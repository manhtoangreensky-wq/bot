# TOAN AAS Beta Launch Checklist

## Before Selling

- [ ] Website `/` loads the TOAN AAS landing page.
- [ ] `/health` returns OK and does not expose secrets.
- [ ] `/providers` shows configured/missing only, no secret values.
- [ ] `/backup_db` runs successfully.
- [ ] New users receive 200 Xu trial credit.
- [ ] `/film` Basic costs 200 Xu.
- [ ] `/pricing` or `/banggia` shows the current pricing.
- [ ] `/promo BETA50` works for a test user.
- [ ] `/naptien` creates a PayOS QR/checkout URL.
- [ ] Real PayOS payment 10k without promo is understood or tested.
- [ ] Real PayOS payment 10k with BETA50 is tested.
- [ ] Duplicate webhook/checkpayos does not double-credit base Xu or promo Xu.
- [ ] `/mark_payos_test pass ...` has been run only after manual verification.
- [ ] `/sales_ready` shows SALES READY or gives a clear remaining blocker.

## First Beta Customers

Target: 3–10 users only.

Best early customer types:

- Affiliate sellers.
- Online shop owners.
- Facebook/TikTok content creators.
- YouTube Shorts creators.
- People who need script/caption/content packs quickly.

## Beta Offer

- New user trial: 200 Xu.
- Promo code: BETA50 for +50% Xu on deposit while active.
- Suggested first paid packages: 50k or 100k.
- Keep the public base price high; use promo to create a clear discount feeling.

## First Sales Message

```text
Mình đang mở beta TOAN AAS — bot AI tạo script/caption/content pack cho Facebook, TikTok, YouTube, có nạp Xu bằng PayOS. Tài khoản mới có 200 Xu trải nghiệm, nhập BETA50 sẽ được +50% Xu khi nạp nếu mã còn hiệu lực. Bạn muốn test không?
```

## Guided First-User Flow

1. Send the user the bot link.
2. User runs `/start`.
3. User checks `/profile` and sees 200 Xu trial.
4. User runs `/film <chủ đề>` to try one Video Script Basic.
5. User enters `/promo BETA50`.
6. User runs `/naptien` and chooses 50k or 100k.
7. Admin watches `/dashboard`.
8. Ask for feedback after the first generated output.

## Do Not Promise

- Do not promise guaranteed revenue.
- Do not say the bot auto-earns money.
- Do not claim auto publish unless the feature has been explicitly built and approved.
- Do not encourage spam.
- Do not ask users for their API keys or payment secrets.

## Beta KPI

- 3–10 beta users.
- At least 3 successful deposits.
- At least 10 `/film` runs.
- At least 3 `/growth_ai` or performance-analysis runs.
- Zero duplicate payment credits.
- At least 5 useful feedback notes.
