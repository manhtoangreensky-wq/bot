# Video Factory Plan

Do not implement new Video Factory logic in this documentation task.

Video Factory should start only after the Stable Revenue Bot is healthy.

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
- video brief
- scene manifest
- worker task list
- review packet
- publish packet
- performance report

## Not In First MVP

- No fully automatic paid video generation until API/tool reliability is proven.
- No fully automatic social posting without platform credentials and approval gate.
- No removal of manual review.
