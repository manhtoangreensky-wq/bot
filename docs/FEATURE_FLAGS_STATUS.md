# FEATURE FLAGS STATUS - TOAN AAS

Date: 2026-06-02
Source: `init_db()` defaults in `bot.py`.

| Flag | Enabled | Meaning | Sales impact |
|---|---:|---|---|
| `video_factory` | 0 | Large Video Factory features gated until foundation is stable. | Keeps MVP focused. |
| `youtube_output` | 0 | YouTube output generation gated. | Avoids over-expansion. |
| `affiliate_engine` | 0 | Advanced affiliate automation gated. | Keep manual/controlled first. |
| `device_ops` | 0 | Device Ops outside first 90 day production scope. | No device farm scope. |
| `auto_publish` | 0 | Auto publish disabled until explicit approval. | Critical safety gate. |
| `worker_queue` | 0 | Worker queue off until reviewed. | Avoids hidden background cost. |
| `dashboard` | 0 | Dashboard expansion gated. | Avoids web app expansion now. |
| `trial_upsell` | 1 | Missing-Xu upsell is allowed. | Helps revenue. |
| `payos_dynamic` | 1 | Dynamic QR billing enabled. | Core money flow. |
| `telegram_menu_v2` | 1 | Grouped Telegram menu enabled. | Better UX. |
| `website_rebrand` | 1 | TOAN AAS landing rebrand enabled. | Public brand ready. |

## Required guardrails

- Keep `auto_publish = 0` until admin explicitly approves a separate task.
- Head brain may create plans, jobs, worker tasks and review packets while `auto_publish = 0`; it must stop at publish handoff or manual approval.
- Keep `payos_dynamic = 1` only after PayOS ENV and real payment test pass.
- Keep `trial_upsell = 1` because it supports revenue without adding new provider risk.
- Do not add new feature flag schema in Step 8.
