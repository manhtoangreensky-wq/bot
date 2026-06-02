# WEBSITE INDEX UPDATE

## Goal

Đồng bộ website với TOAN AAS Stable Revenue Bot V15.2.

## Files changed

- `index.html`
- `banner.png`
- `bot.py` - safe `/banner.png` FileResponse route only
- `docs/WEBSITE_INDEX_AUDIT.md`
- `docs/WEBSITE_INDEX_UPDATE.md`
- `docs/STABLE_REVENUE_BOT_STATUS.md`

## Brand

- Old: legacy DAAS spelling in public positioning.
- New: `TOAN AAS - AI Automation System`.

## Sections updated

- Hero: Bot AI tạo nội dung, Video Script Lite và công cụ AI hằng ngày cho Facebook, TikTok, YouTube.
- AI Services: Chat AI, đọc voice, bóc băng audio, tách nền ảnh, tải video sạch, Video Script Lite.
- Video Factory: Content Pack cho Facebook, TikTok, YouTube.
- PayOS Xu: 6 gói đúng với `PAYMENT_PACKAGES`: 10k, 20k, 50k, 100k, 200k, 500k.
- Content Pack self-post workflow: tạo nội dung/video pack, dán link trực tiếp nếu cần, tự đăng và tự theo dõi hiệu quả.
- Safety: chưa tự đăng bài, chưa quản lý tài khoản mạng xã hội, chưa vận hành quảng cáo thay khách, không spam, không deepfake không consent.
- Contact: giữ form POST `/lead`.
- Banner: added repository-root `banner.png` immediately after hero with responsive `object-fit: contain`.
- Root route: `/` now serves `index.html` directly; JSON runtime summary moved to `/status`.

## CTA links

- Bot: `https://t.me/toanaasbot`
- Nạp Xu: anchor `#pricing`, hướng người dùng mở bot và dùng `/naptien`.
- Lead: form POST `/lead`.

## Static assets

- `/LOGO.png`: dedicated route, unchanged.
- `/banner.png`: dedicated route serving only `banner.png`; no catch-all route added.
- `og:image`: `/banner.png`.
- `/health`: JSON health endpoint kept unchanged.

## Manual checks

- Open `/landing`.
- Confirm `/` serves the TOAN AAS landing page.
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
- Telegram handlers changed only to guard internal/operator/publish commands from non-admin users.
