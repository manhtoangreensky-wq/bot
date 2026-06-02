# TOAN AAS Head Brain Operating System

Date: 2026-06-02

## Purpose

This is the operating contract for the TOAN AAS head brain: admin gives an objective in Telegram, the AI commander reads the control pack, creates or claims safe work, hands tasks to AI/tool workers, stops at review gates, then records publish and money results.

The current system is not a fully autonomous social posting bot. It is an approval-gated control system. This is intentional.

## Control Hierarchy

1. Admin Telegram: gives goals, approves publish, handles secrets, money and final judgment.
2. AI Commander: ChatGPT/Codex/Claude/n8n layer that reads the run card and calls whitelisted commands or APIs.
3. Tool Worker: creates script, voice, image, raw video, edit, subtitle or final video from the worker pack.
4. Publisher: posts manually or through official APIs only after review/approval.
5. Growth Analyst: records views, clicks, orders, revenue and recommends scale/fix/pause.

## Main Telegram Commands

- `/head_brain platform=tiktok days=30 limit=8`
- `/head_run platform=tiktok topic="..." execute=0`
- `/operator_contract platform=tiktok`
- `/goal_audit platform=tiktok`
- `/operator_launch topic="..." platform=tiktok limit=3 build=1`
- `/worker_intake claim=1 include_prompt=1`
- `/review_video job=<JOB_ID> send=1`
- `/approve_publish job=<JOB_ID> queue=1 mode=manual`
- `/publisher_handoff queue=<QUEUE_ID>`
- `/performance_add job=<JOB_ID> type=click value=...`
- `/affiliate_decisions days=30`

## Main API Packs

All operator APIs require `OPERATOR_API_TOKEN`.

- `GET /api/operator/head-brain`
- `POST /api/operator/head-run`
- `GET /api/operator/control-contract`
- `GET /api/operator/goal-audit`
- `POST /api/operator/launch`
- `GET /api/operator/worker-intake`
- `GET /api/operator/jobs/<JOB_ID>/worker-pack`
- `POST /api/operator/tasks/<TASK_ID>/complete`
- `GET /api/operator/jobs/<JOB_ID>/review-video`
- `POST /api/operator/jobs/<JOB_ID>/approve`
- `GET /api/operator/publish/<QUEUE_ID>/handoff`
- `POST /api/operator/publish/<QUEUE_ID>/complete`
- `POST /api/operator/performance`
- `GET /api/operator/affiliate-decisions`

## Standard Loop

1. Admin sends a topic or money objective in Telegram.
2. AI commander reads `/head_brain` or `GET /api/operator/head-brain`.
3. If setup is missing, run bootstrap or ask admin for missing ENV/channel/link.
4. Create job batch with `/operator_launch` or `/make_video`.
5. Worker claims tasks with `/worker_intake` or task API.
6. Worker returns real outputs by task complete/upload.
7. Admin/AI runs `/review_video`.
8. Admin approves with `/approve_publish`.
9. Publisher posts manually or through an official `api_ready` adapter.
10. Result URL and performance are recorded.
11. AI reads affiliate decisions and creates the next scale/fix batch.

## Platform Rules

Primary platforms:

- Facebook
- TikTok
- YouTube

Secondary platforms:

- Instagram
- Threads
- Website
- OnlyFans or paid fan platform, manual-only unless there is an official, compliant, reviewed adapter

OnlyFans and adult-oriented workflows require:

- fictional/self-created AI characters or real people with explicit consent only
- 18+ age/legal compliance
- manual review before publishing
- no impersonation, deepfake, or non-consensual likeness
- no hidden automation that bypasses platform terms

## Affiliate Rules

- Always keep affiliate disclosure where required.
- Never promise guaranteed income, approval, loan/card acceptance or fixed discounts.
- Use all relevant links for one product family when useful, but keep the post readable.
- Track source placement: caption, comment, bio, story, page post or manual DM.
- Scale only after real data: views, clicks, orders, revenue, cost.

## Current Safe State

- `auto_publish` default is off.
- Publish queue and review gate exist.
- Official auto publish is limited; unsupported platforms return manual handoff.
- Head brain and control contract already exist in `bot.py`.
- Real end-to-end automation still needs live verification with actual worker output and platform adapters.

## Next Implementation Priority

1. Live Telegram test: `/head_brain`, `/operator_launch`, `/worker_intake`, `/review_video`.
2. Add or connect one real video generation worker.
3. Add one official publishing adapter at a time, starting with the safest platform/account.
4. Keep OnlyFans manual until a compliant official workflow is confirmed.
5. Use performance tracking before scaling spend or output volume.
