# WEBSITE INDEX AUDIT

## Files scanned

- `bot.py`
- `index.html`
- `landing.html` - not present
- `templates/index.html` - not present
- `static/index.html` - not present
- `app/templates/index.html` - not present
- CSS/JS standalone files - not present

## Matched old branding

| File | Match | Used by route? | Action |
| --- | --- | --- | --- |
| `index.html` | Previous public landing content needed alignment with current TOAN AAS V15.2 bot | Yes, `/landing` serves this file | Replaced public landing text/UI |
| `README.md` | `TOAN AAS Bot` heading | No public landing route | Updated to match brand |
| `docs/*` | Some historical references may exist | No public landing route | Not changed unless status docs needed |

## Served route

- `/`: JSON runtime/health summary from `bot.py`, not the marketing landing page.
- `/landing`: `FileResponse(index.html)` from repository root.
- Static logo: `/LOGO.png` and `/logo.png`.
- Static banner: `/banner.png` serves only repository-root `banner.png`.

## Verification Before Banner

Checked on 2026-06-02 before adding banner:

- Live `/`: HTTP 200, `application/json`, returns runtime JSON.
- Live `/landing`: HTTP 200, `text/html`, contains `TOAN AAS - AI Automation System`.
- Live `/LOGO.png`: HTTP 200, `image/png`.
- Local `bot.py`: `/landing` uses `FileResponse(index.html)`.
- Local `bot.py`: `/LOGO.png` uses a dedicated safe route.
- No catch-all static route is used.

## Pricing Check

`index.html` pricing matches `PAYMENT_PACKAGES` in `bot.py`:

- `10k`: 10.000đ -> 100 Xu
- `20k`: 20.000đ -> 200 Xu
- `50k`: 50.000đ -> 500 Xu base, plus 30 Xu Launch Bonus on first 50k purchase
- `100k`: 100.000đ -> 1.000 Xu base, plus 50 Xu Launch Bonus on first 100k purchase
- `200k`: 200.000đ -> 2.000 Xu base, plus 150 Xu Launch Bonus on first 200k purchase
- `500k`: 500.000đ -> 5.000 Xu base, plus 500 Xu Launch Bonus on first 500k purchase

## Telegram CTA Check

- Website CTA uses `https://t.me/toanaasbot`.
- `BOT_USERNAME` default in `bot.py` and `.env.example` is `toanaasbot`.
- CTA copy now tells users to open Telegram bot and use `/naptien` to top up Xu.

## Decision

- File edited: `index.html`.
- Backend route edited only to add safe `/banner.png` FileResponse.
- Files not edited: PayOS, billing, database, Telegram handlers.
- Reason: banner is a repository-root image and needs an explicit safe asset route.
