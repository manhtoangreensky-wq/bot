# Video Factory Plan

Do not implement new Video Factory logic in this documentation task.

Video Factory should start only after the Stable Revenue Bot is healthy.

Module name: Multi-Platform AI Video & Affiliate Factory.

Primary platforms:

- Facebook
- TikTok
- YouTube

Secondary platforms:

- Instagram
- Threads
- OnlyFans or paid fan platform only when legal, consent-based, and manually reviewed
- Website/Landing

## MVP Tables

The MVP should use:

- `campaigns`
- `affiliate_links`
- `social_channels`
- `production_jobs`
- `production_tasks`
- `production_assets`
- `production_manifests`
- `creative_variants`
- `publish_queue`
- `performance_events`
- `tool_events`
- `reference_videos`

Several of these tables already exist in current `bot.py`; the next step is safe migration/audit, not duplicate creation.

## Future Commands

- `/film_series`
- `/film_review`
- `/film_approve`
- `/film_rewrite`
- `/reference_analyze`
- `/video_work_orders`
- `/worker_intake`
- `/publish_queue`
- `/performance_add`

Many of these commands already exist in the current code and must be reviewed before further expansion.

## Workflow

topic
-> character bible
-> episode manifest
-> scene prompts
-> quality gate
-> production_tasks
-> worker render
-> review
-> approve
-> publish queue
-> performance tracking

## Head Brain Control

The Video Factory is controlled through the head-brain layer, not by isolated commands.

Recommended control sequence:

1. `/head_brain platform=tiktok days=30 limit=8`
2. `/operator_launch topic="<topic>" platform=tiktok limit=3 build=1`
3. `/worker_intake claim=1 include_prompt=1`
4. `/review_video job=<JOB_ID> send=1`
5. `/approve_publish job=<JOB_ID> queue=1 mode=manual`
6. `/publisher_handoff queue=<QUEUE_ID>` or official adapter if `api_ready`
7. `/performance_add job=<JOB_ID> type=click value=<N>`
8. `/affiliate_decisions days=30`

See `docs/HEAD_BRAIN_OPERATING_SYSTEM.md` for the command/API contract.

## Policy

- Do not copy a reference video directly.
- Learn structure, pacing, hook, proof, and CTA only.
- Use original characters, prompts, and scripts.
- Keep affiliate disclosure when required.
- Do not impersonate real people.
- Do not auto-publish without admin approval.

## MVP Output

The MVP should produce:

- campaign plan
- affiliate product match
- outline
- episode list
- image prompt
- video prompt
- voice line
- caption
- CTA
- affiliate disclosure
- platform-specific output
- video brief
- scene manifest
- worker task list
- review packet
- publish packet
- performance report

Export formats:

- JSON
- Markdown

Future commands:

- `/film`
- `/video_script`
- `/scene_prompt`
- `/film_review`
- `/film_approve`
- `/export_video_pack`

## Not In First MVP

- No fully automatic paid video generation until API/tool reliability is proven.
- No fully automatic social posting without platform credentials and approval gate.
- No removal of manual review.
