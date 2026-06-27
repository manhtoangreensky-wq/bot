# P0.17W1 Remote Local Worker API Bridge

## Scope

This branch keeps the Telegram bot, webhook ownership, PayOS, wallet/Xu, DB, admin controls, and `video_jobs` authority on Railway. The VPS is only a remote worker for heavy local/video processing.

## Current `video_jobs` Table And Helpers

`services/video_project_queue.py` owns the SQLite-backed video project state machine and queue. It creates:

- `video_projects` for confirmed user video projects.
- `video_scenes` for storyboard/scene rows.
- `video_jobs` for `video_render` work.

Existing helpers already support:

- `confirm_video_project_invoice(...)`: marks a project confirmed and queues a render job after product confirmation.
- `claim_next_video_job(...)`: atomically moves one queued job to `processing`, records `locked_by`, `locked_at`, lease expiry, and increments attempts.
- `hydrate_video_job_payload(...)`: attaches project and scenes to a claimed job.
- `complete_video_job(...)`: marks the job and project completed.
- `fail_video_job(...)`: retries retryable jobs until `max_attempts`, then marks failed.

W1 adds progress columns (`progress_percent`, `progress_message`), a heartbeat helper, and confirmed-project filtering so workers only claim jobs from confirmed projects.

## Current `local_worker.py` Behavior

`local_worker.py` is the legacy local/Windows worker. It polls Railway internal endpoints:

- `GET /internal/worker/poll`
- `GET /internal/video_worker/poll`
- `POST /internal/worker/job_update`
- `POST /internal/video_worker/job_update`

That flow remains for backward compatibility. It is not the VPS contract.

## Why VPS Cannot Read Railway SQLite

Railway owns the SQLite file and any persistent volume path. A VPS worker cannot safely or reliably mount/read that file. Letting a VPS open the DB would break the deployment boundary, risk corruption, and grant the VPS authority over data it must not own.

The VPS must therefore call authenticated Railway HTTP endpoints using `LOCAL_WORKER_TOKEN`.

## New Worker API Endpoints

All new endpoints are under `/api/v1/worker/*` and require:

```text
Authorization: Bearer <LOCAL_WORKER_TOKEN>
```

Endpoints:

- `POST /api/v1/worker/claim`: claims one confirmed queued video job and returns a sanitized payload.
- `POST /api/v1/worker/heartbeat`: verifies job ownership and extends the lease while saving progress.
- `POST /api/v1/worker/complete`: verifies ownership, accepts JSON or multipart MP4 upload, validates uploaded bytes, marks job/project completed, and guards duplicate completion.
- `POST /api/v1/worker/fail`: verifies ownership, records a safe error, retries if allowed, or marks failed.
- `GET /api/v1/worker/assets/{asset_id}`: token-protected placeholder asset download route.

## `LOCAL_WORKER_TOKEN` Behavior

The W1 API uses Bearer-only token auth via `services/worker_auth.py`.

- Missing Bearer token returns `401`.
- Wrong Bearer token returns `403`.
- Missing server-side `LOCAL_WORKER_TOKEN` returns `503`.
- Token comparison uses `hmac.compare_digest`.
- Logs record endpoint, IP, user-agent, time, and reason only.
- Logs never record the provided or expected token.

`/runtime` exposes only booleans:

- `worker_api_enabled`
- `local_worker_token_configured`
- `remote_worker_mode_supported`

## Security Boundary

The VPS worker can:

- Claim confirmed queued video jobs.
- Download authorized worker assets.
- Upload result artifacts.
- Report heartbeat/failure.

The VPS worker cannot:

- Own Telegram webhook updates.
- Access PayOS authority.
- Credit/debit Xu.
- Modify wallet/top-up/payment state.
- Read Railway SQLite directly.
- Access admin/operator endpoints with `LOCAL_WORKER_TOKEN`.

## Result Upload Strategy

`POST /api/v1/worker/complete` supports:

- Multipart upload with `metadata` JSON and `file`.
- JSON completion for already-uploaded/result-URL strategies.

Multipart uploads are stored under `WORKER_RESULT_UPLOAD_DIR` (default `files/worker_results`). Uploaded file bytes must be nonzero. Duplicate complete calls by the same worker return `duplicate: true` and do not re-complete/re-send.

Railway remains responsible for final delivery to Telegram users when the Telegram app is available.

## Retry And Failure Behavior

`POST /api/v1/worker/fail` stores only `safe_error` text. If `retryable=true` and attempts are still below `max_attempts`, the job returns to `queued`. Once attempts reach `max_attempts`, the job and project are marked failed.

No traceback, provider secret, token, or raw debug payload is sent to public users.

## Remote Worker Script

`remote_worker.py` is the VPS-side HTTP worker loop. It uses:

- `BOT_API_URL`
- `LOCAL_WORKER_TOKEN`
- `WORKER_ID`
- `WORKER_POLL_INTERVAL_SECONDS`
- `WORKER_CONCURRENCY`
- `WORKER_TMP_DIR`
- `FFMPEG_MAX_CONCURRENT`

It claims jobs, heartbeats, processes fake admin-test jobs when enabled, uploads completion, reports safe failure, and cleans temporary work directories. It does not import `sqlite3` or call `db_connect`.

## Not Touched

- PayOS
- `/naptien`
- payment webhook
- wallet ledger
- top-up logic
- destructive DB migrations
- music/Suno core
- custom voice provider
- standalone web/app
- Telegram webhook ownership
- B13 render/stitch engine rewrite

## Deployment

This branch does not deploy. No LIVE PASS is claimed. After merge, VPS setup can run the checked-in `remote_worker.py` with a systemd service using the Railway `BOT_API_URL` and `LOCAL_WORKER_TOKEN`.
