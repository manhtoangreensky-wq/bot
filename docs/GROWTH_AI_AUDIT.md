# GROWTH AI AUDIT

Date: 2026-06-02
Scope: TOAN AAS Phase 1 Step 7

## Compile

- `py_compile`: PASS before implementation.
- `py_compile`: PASS after implementation.
- `pytest -q`: PASS, 13 tests.
- Import test: PASS, `cmd_growth_ai` and `cmd_campaign_report` exist.
- Local route smoke: PASS for `/`, `/landing`, `/health`, `/banner.png`.

## Existing Data Tables

| Table | Exists? | Used for |
|---|---:|---|
| `published_posts` | YES | Manual published post records from `/publish_done`. |
| `manual_performance_events` | YES | Manual metrics from `/performance_add`. |
| `growth_recommendations` | YES | Rule-based and AI growth recommendations. |
| `campaigns` | YES | Campaign metadata and owner scope. |
| `content_calendar` | YES | Manual calendar slots. |
| `video_script_jobs` | YES | `/film` output/jobs. |
| `affiliate_links` | YES | User affiliate products/links. |

## Existing Commands

| Command | Exists? | Notes |
|---|---:|---|
| `/performance_report` | YES | Manual aggregate report. |
| `/growth_loop` | YES | Rule-based/manual loop for users, operator loop for admin. |
| `/posts` | YES | Recent manual posts. |
| `/dashboard` | YES | Admin dashboard. |
| `/film` | YES | Video Script Lite. |
| `/campaign` | YES | User-facing campaign entry. |

## AI Provider

- Gemini: YES through `AgentGemini.chat`.
- OpenAI fallback: YES through `AgentGemini.chat`.
- Current helper: sync `AgentGemini.chat(prompt, text, uid, is_json=False)`.

## Credits

- Spend helper: `spend_fixed_credit`.
- Refund helper: `refund_charged_credit`.
- Insufficient credits helper: `reply_insufficient_credits` with top-up keyboard.
- Admin/VIP behavior: `/growth_ai` follows `/film` pattern: admin/VIP cost 0.

## Recommendation

- Safe to add `/growth_ai`: YES, uses existing manual metrics and AI text provider only.
- Safe to add `/campaign_report`: YES, reads owner-scoped data and exports local temp files.
- Commands registered after implementation: `/growth_ai`, `/campaign_report`, `/export_report`.
- Risks:
  1. AI provider quota/network errors; mitigation: refund Xu after charge.
  2. Low/no manual data; mitigation: no charge and show onboarding steps.
  3. Live Telegram file-send still needs manual smoke test after Railway deploy.
