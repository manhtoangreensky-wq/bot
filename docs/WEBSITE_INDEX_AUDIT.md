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
| `README.md` | Legacy `TOAN DAAS Bot` heading | No public landing route | Not changed in this task |
| `docs/*` | Some historical references may exist | No public landing route | Not changed unless status docs needed |

## Served route

- `/`: JSON runtime/health summary from `bot.py`, not the marketing landing page.
- `/landing`: `FileResponse(index.html)` from repository root.
- Static logo: `/LOGO.png` and `/logo.png`.

## Decision

- File edited: `index.html`.
- Files not edited: `bot.py` route logic, PayOS, billing, database, Telegram handlers.
- Reason: landing HTML is a standalone file and does not require backend logic changes.
