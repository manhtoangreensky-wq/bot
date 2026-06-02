# Database Foundation

## Current Database

The current system uses SQLite.

SQLite is acceptable for the current small revenue bot, but public scale should eventually move to PostgreSQL or add stronger write coordination.

## Current Rule

- Do not drop old tables.
- Do not rename old columns without a migration.
- Do not change old data types without a migration.
- Add new tables/columns idempotently.
- Test migrations on a temporary SQLite database first.

## Proposed Future Schema

### Core

- `organizations`
- `users`
- `roles`
- `permissions`
- `customers`
- `contacts`
- `projects`
- `tasks`
- `jobs`
- `job_runs`
- `approvals`
- `audit_logs`
- `files`
- `notes`
- `messages`

### Revenue

- `invoices`
- `payments`
- `credit_events`
- `payos_orders`

### Video Factory

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

### Device Ops

- `devices`
- `installation_jobs`
- `maintenance_tasks`
- `warranties`
- `technicians`

## Current Reality

Several Video Factory tables already exist in `bot.py`. Treat them as existing foundation, not as proof that the full automated system is production-ready.

## Next Migration Task

Before adding more tables:

1. Inspect current `init_db()`.
2. List existing tables and columns.
3. Identify missing columns only.
4. Add migration helpers that are safe to run multiple times.
5. Add tests using temporary SQLite.
