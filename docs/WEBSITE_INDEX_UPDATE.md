# WEBSITE INDEX UPDATE

## Goal

Đồng bộ website với TOAN AAS Stable Revenue Bot V15.2.

## Files changed

- `index.html`
- `docs/WEBSITE_INDEX_AUDIT.md`
- `docs/WEBSITE_INDEX_UPDATE.md`
- `docs/STABLE_REVENUE_BOT_STATUS.md`

## Brand

- Old: `TOAN DAAS` in legacy/public positioning.
- New: `TOAN AAS - AI Automation System`.

## Sections updated

- Hero: Bot AI kiếm tiền và tự động hóa nội dung cho Facebook, TikTok, YouTube.
- AI Services: Chat AI, đọc voice, bóc băng audio, tách nền ảnh, tải video sạch, Video Script Lite.
- Video Factory: Content Pack cho Facebook, TikTok, YouTube.
- PayOS Xu: 6 gói đúng với `PAYMENT_PACKAGES`: 10k, 20k, 50k, 100k, 200k, 500k.
- Affiliate Workflow: lưu link, tạo script bằng `/film`, lên lịch, đăng thủ công, đo hiệu quả.
- Safety: không auto publish khi chưa duyệt, không spam, không deepfake không consent, affiliate minh bạch.
- Contact: giữ form POST `/lead`.

## CTA links

- Bot: `https://t.me/Httdhtoan`
- Nạp Xu: anchor `#pricing`, hướng người dùng về bot để dùng `/naptien`.
- Lead: form POST `/lead`.

## Manual checks

- Open `/landing`.
- Confirm `/` still returns JSON runtime summary.
- Check header brand is `TOAN AAS`.
- Check logo loads from `/LOGO.png`.
- Check CTA buttons.
- Submit lead form to `/lead`.
- Check mobile responsive layout.

## Safety

- PayOS code not changed.
- Billing code not changed.
- Webhook code not changed.
- Database schema not changed.
- Telegram handlers not changed.
