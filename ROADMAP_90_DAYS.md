# TOAN AAS Roadmap 90 Days

## First 30 Days: Stable Revenue Bot + Early Revenue

Week 1:

- Keep `python -m py_compile bot.py` passing.
- Verify SQLite persistence on Railway.
- Add Railway Volume or backup plan.
- Add `/health`.
- Keep admin alert and `/runtime` diagnosis.
- Create foundation docs.

Week 2:

- Extract `app/core/config.py` safely.
- Extract `app/core/db.py` safely.
- Do not change PayOS flow.
- Do not change schema unless migration is explicit and tested.

Week 3:

- Test PayOS dynamic QR end to end.
- Prevent duplicate credit.
- Keep manual bill fallback.
- Add trial upsell only after payment tests pass.
- Add a basic admin dashboard only if it does not risk payment flow.

Week 4:

- Video Factory Lite:
  - `/film` or `/video_script`
  - outline
  - scene prompts
  - Facebook/TikTok/YouTube outputs
  - no render
  - no auto publish

## 60 Days: Video Factory MVP

- `video_projects`
- `video_episodes`
- `video_scenes`
- `platform_outputs`
- `affiliate_links`
- prompt quality gate
- manual review gate
- export JSON/Markdown
- manual performance tracking

## 90 Days: Light Dashboard + Device Ops Lite

- Light dashboard.
- Customer/project/task basics.
- Device Ops Lite only if there is a paying customer.
- Installation checklist.
- Maintenance/warranty checklist.
- n8n/Make connector only if needed.

## Explicitly Not Prioritized In First 90 Days

- HR.
- Tax.
- Travel platform.
- Dev Studio.
- Full auto-publish.
- Fully automatic paid video generation.
