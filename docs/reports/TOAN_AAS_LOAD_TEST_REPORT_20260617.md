# TOAN AAS Load Test Report

Date: 2026-06-17
Status: harness prepared; production load test not executed without explicit dry-run deployment window

## 1. Environment

Target repo/worktree audited:

- Bot service: FastAPI + Telegram bot in `bot.py`
- Existing public health endpoint: `GET /health`
- Added lightweight endpoints:
  - `GET /api/v1/health`
  - `GET /api/v1/metrics-lite`
- DB mode: SQLite by current bot configuration, expected Railway persistent volume when deployed with `/data`.
- Production destructive tests: not run.

Required dry-run flags before load testing real deployment:

```text
LOAD_TEST_MODE=true
BOT_DRY_RUN_SEND=true
PROVIDER_DRY_RUN=true
PAYOS_DRY_RUN=true
DISABLE_REAL_TELEGRAM_SEND=true
LOAD_TEST_USER_PREFIX=loadtest_
```

## 2. Test Tools

Prepared k6 scripts:

- `loadtests/k6_app.js`
- `loadtests/k6_bot_webhook.js`
- `loadtests/k6_mixed.js`

The scripts send:

- `X-Load-Test-Mode: true`
- `X-Dry-Run: true`

## 3. App API Results

Not executed against production in this pass because the live service was not confirmed to have all dry-run flags enabled.

| Stage | RPS | p50 | p95 | p99 | Error % | CPU | RAM | Notes |
|---|---:|---:|---:|---:|---:|---|---|---|
| Baseline | 5 | not run | not run | not run | not run | not sampled | not sampled | Harness ready |
| Light | 10 | not run | not run | not run | not run | not sampled | not sampled | Run after dry-run deploy |
| Medium | 25 | not run | not run | not run | not run | not sampled | not sampled | Watch SQLite locks |
| High | 50 | not run | not run | not run | not run | not sampled | not sampled | Likely needs DB/worker separation if write-heavy |
| Stress | 100 | not run | not run | not run | not run | not sampled | not sampled | Do not run on production without window |

## 4. Bot Webhook Results

Synthetic webhook script is ready but not executed against production. It generates `/start`, text, and callback updates with `loadtest_` users.

| Stage | Updates/sec | p50 | p95 | p99 | Error % | DB lock | Notes |
|---|---:|---:|---:|---:|---:|---:|---|
| Baseline | 5 | not run | not run | not run | not run | not sampled | Requires dry-run Telegram send |
| Light | 10 | not run | not run | not run | not run | not sampled | Safe only with `BOT_DRY_RUN_SEND=true` |
| Medium | 25 | not run | not run | not run | not run | not sampled | Watch SQLite write contention |
| High | 50 | not run | not run | not run | not run | not sampled | Queue/DB likely bottleneck |

## 5. Mixed Workload

`loadtests/k6_mixed.js` combines:

- 55% app read endpoints
- 35% bot webhook synthetic updates
- 10% light write dry-run feedback

Do not run mixed workload until dry-run flags are active and admin confirms no real Telegram/provider/PayOS execution.

## 6. Bottleneck Risks

Likely bottlenecks before measured run:

- SQLite write locks under concurrent callbacks/jobs.
- Telegram send latency if dry-run is not enabled.
- Provider latency/cost if provider dry-run is not enforced.
- Local Worker/FFmpeg should not run inside Railway web process for heavy jobs.
- Video/image queues should be tested separately with provider mock.

## 7. Estimated User Capacity Model

Use this formula after actual sustainable RPS is measured:

`active_users_supported = sustainable_rps * 60 / avg_requests_per_user_per_minute`

Assumptions:

| User type | Avg requests/user/min | Notes |
|---|---:|---|
| Casual app users | 1-3 | Browsing dashboard/pricing/help |
| Active bot users | 3-8 | Menu/callback/text interactions |
| Heavy creator users | 8-20 | Prompt + image/video job + poll/status |
| Admin/internal users | 2-10 | Status/report commands |

## 8. Scale Recommendation

| Mức tải | RPS | Active users ước lượng | Cấu hình đề xuất |
| ------- | --: | ---------------------: | ---------------- |
| Level 1 | 5-10 | 50-150 | 1 Railway service, SQLite WAL can be acceptable if write volume is low |
| Level 2 | 25-50 | 300-600 | Increase Railway CPU/RAM, separate worker, monitor DB locks |
| Level 3 | 50-100 | 600-1200 | Move to PostgreSQL, add Redis/queue, split bot/web/worker |
| Level 4 | 100+ | 1200+ | Horizontal web instances, dedicated queue workers, CDN/static, cache |

## 9. Next Actions

1. Deploy dry-run env flags to staging or a short production maintenance window.
2. Run:

```bash
k6 run -e BASE_URL=https://app.toanaas.vn -e READ_ONLY=true loadtests/k6_app.js
k6 run -e BASE_URL=https://app.toanaas.vn -e TELEGRAM_WEBHOOK_PATH=/webhook/telegram/<secret> loadtests/k6_bot_webhook.js
k6 run -e BASE_URL=https://app.toanaas.vn -e TELEGRAM_WEBHOOK_PATH=/webhook/telegram/<secret> loadtests/k6_mixed.js
```

3. Record p50/p95/p99/error rate and Railway CPU/RAM.
4. If SQLite lock appears above 25-50 RPS, plan PostgreSQL migration before public scale.
5. Do not run real provider-heavy image/video jobs in load test.

## 10. Safety Confirmation

Not touched:

- PayOS real payment
- `/naptien`
- webhook payment logic
- Telegram real send bulk
- ShopAIKey/OpenAI/Gemini provider calls
- Xu production billing
- DB destructive paths
