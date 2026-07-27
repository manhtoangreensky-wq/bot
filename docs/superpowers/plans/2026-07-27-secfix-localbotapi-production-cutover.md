# SECfix and Local Bot API Production Cutover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the evidenced B1-B6 security gaps, deploy the newest `main` containing PR #539, and prove the production Telegram bot can receive and return a real file larger than 20 MB through `tg.toanaas.vn` without touching paid providers or unrelated workers.

**Architecture:** Keep Telegram transport policy in one small helper shared by normal media downloads and Telegram Business raw API calls. Bind B6 precheck tickets to the exact user, feature, action, and short lifetime before the executor may trust them. Keep the VPS Telegram Bot API behind TLS/Nginx and a shared-secret header, with the upstream bound to loopback only; Railway owns the production bot token and is cut over only after an explicit production checkpoint.

**Tech Stack:** Python 3.12, pytest, FFmpeg, python-telegram-bot, Railway CLI, Telegram Local Bot API, Nginx, Docker/systemd.

---

### Task 1: Establish the immutable baseline and scope

**Files:**
- Read: `AGENTS.md`
- Read: `bot.py`
- Read: `services/telegram_business_support.py`
- Read: `services/video_local_editing.py`
- Read: `requirements.txt`

- [ ] **Step 1: Record repository identity and dirty state**

Run:

```powershell
git status --short
git branch --show-current
git remote -v
git fetch origin --prune
git rev-parse origin/main
git merge-base --is-ancestor e383a36 origin/main
```

Expected: repository is `manhtoangreensky-wq/bot`; PR #539 merge commit is an ancestor; existing user changes are preserved.

- [ ] **Step 2: Record the pre-edit compiler result**

Run:

```powershell
python -m py_compile bot.py
```

Expected: report the actual exit state. A bounded timeout is recorded as `TIMEOUT`, never as `PASS`.

### Task 2: Enforce confidential transport for the Local Bot API

**Files:**
- Create: `services/telegram_transport.py`
- Modify: `bot.py`
- Modify: `services/telegram_business_support.py`
- Test: `tests/test_p0_secfix_local_api_transport.py`
- Test: `tests/test_infra_localbotapi_base_url.py`

- [ ] **Step 1: Write failing URL-policy tests**

Add cases that reject remote HTTP, URL user-info, query strings, fragments, unsupported schemes, and cloud-host suffix tricks while allowing HTTPS and loopback HTTP.

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
pytest --noconftest -q tests/test_p0_secfix_local_api_transport.py
```

Expected before implementation: malicious transport cases fail for the documented reason.

- [ ] **Step 3: Implement one shared URL classifier**

The helper must classify only exact Telegram Cloud hosts as cloud, permit `http://` only for `localhost`, `127.0.0.1`, or `::1`, require HTTPS for remote hosts, and reject credentials/query/fragment before any HTTP request is made.

- [ ] **Step 4: Verify GREEN and compatibility**

Run:

```powershell
pytest --noconftest -q tests/test_p0_secfix_local_api_transport.py tests/test_infra_localbotapi_base_url.py
```

Expected: all focused transport and existing Local Bot API tests pass.

### Task 3: Close B2 FFmpeg drawtext expression injection

**Files:**
- Modify: `services/video_local_editing.py`
- Test: `tests/test_p0_secfix_b2_ffmpeg_text_safety.py`

- [ ] **Step 1: Add a failing manual-editor regression test**

The test must feed text containing `%{eif:...}` into `_text_filter()` and assert the generated filter contains `expansion=none` while retaining ordinary Vietnamese text.

- [ ] **Step 2: Run the new case and verify RED**

Run:

```powershell
pytest --noconftest -q tests/test_p0_secfix_b2_ffmpeg_text_safety.py
```

Expected before implementation: the manual-editor assertion fails because `_text_filter()` omits `expansion=none`.

- [ ] **Step 3: Add the narrow FFmpeg control**

Append the repository's existing `DRAWTEXT_NO_EXPANSION` option to the manual-editor drawtext expression without changing layout, font, color, or timing behavior.

- [ ] **Step 4: Verify GREEN**

Run the same focused suite and require zero failures.

### Task 4: Bind B6 precheck tickets to their authorization context

**Files:**
- Modify: `bot.py`
- Test: `tests/test_p0_secfix_b6_engine_precheck.py`

- [ ] **Step 1: Add RED replay tests**

Add independent tests proving a ticket minted for one user, feature, or side-effecting action cannot authorize a different user, feature, or action. Add an expiry test using a deterministic clock.

- [ ] **Step 2: Verify the replay tests fail on current behavior**

Run:

```powershell
pytest --noconftest -q tests/test_p0_secfix_b6_engine_precheck.py
```

Expected before implementation: cross-context replay is accepted and the new assertions fail.

- [ ] **Step 3: Implement minimal binding and validation**

Store normalized `feature`, integer `user_id`, normalized `action`, issue time, and expiration in the precheck ticket. The executor may use `allowed_prechecked` only after constant, exact comparisons and expiry validation; otherwise it must run the real gate and fail closed.

- [ ] **Step 4: Verify GREEN and existing engine behavior**

Run the B6 focused suite plus all existing executor/gate tests. No provider, wallet, Telegram, or network call is permitted.

### Task 5: Complete B4 dependency evidence without false claims

**Files:**
- Modify only if reproducible: `requirements.txt`
- Create only if the repository build is validated with it: `requirements.lock`
- Modify only with a validated lock: `Dockerfile`

- [ ] **Step 1: Audit the exact dependency set**

Run:

```powershell
python -m pip install pip-audit
python -m pip_audit -r requirements.txt
```

Expected: direct pins are enumerated and any advisory is recorded with package/version/fix availability. Do not claim clean when an upstream package has no fixed release.

- [ ] **Step 2: Generate and validate a lock only if deterministic**

Use the repository-supported resolver for Linux/Python 3.12, build the Docker image or install the lock in an isolated environment, and run import/tests. If platform-correct resolution cannot be proved, do not ship a misleading Windows-derived lock.

### Task 6: Verify and ship the code cluster

**Files:**
- Review: all changed files from Tasks 2-5

- [ ] **Step 1: Inspect final scope**

Run:

```powershell
git diff --check
git diff --stat
git diff -- bot.py services tests requirements.txt Dockerfile
```

Expected: no PayOS, wallet, `/naptien`, payment webhook, destructive DB, Product Video worker, or provider-routing edits.

- [ ] **Step 2: Run focused and repository checks**

Run:

```powershell
python -m py_compile services/telegram_transport.py services/telegram_business_support.py services/video_local_editing.py local_worker.py
pytest --noconftest -q tests/test_p0_secfix_local_api_transport.py tests/test_p0_secfix_b2_ffmpeg_text_safety.py tests/test_p0_secfix_b6_engine_precheck.py
python -m py_compile bot.py
pytest -q
git diff --check
git status --short
```

Expected: every fresh result is reported exactly; timeout or environment-blocked checks remain explicit unknowns.

- [ ] **Step 3: Commit, push, create one PR, and wait for CI**

Commit the coherent security cluster only after the required checks pass or any pre-existing bounded limitation is documented. Rebase on current `origin/main`, push, open one PR, and merge only after review and CI.

### Task 7: Production VPS and Railway cutover

**Files:**
- Read/execute: operator scripts under the task workspace only; do not commit secrets.

- [ ] **Step 1: Reverify VPS invariants without secrets**

Confirm DNS, TLS hostname/expiry, matching SSH host fingerprint, key-only SSH, fail2ban, loopback-only port 8081, Nginx shared-secret denial, log redaction, container privilege controls, cleanup timer, active-file guard, 120-minute retention, disk guard, and service health.

- [ ] **Step 2: Require the explicit production checkpoint**

The required approval text is:

```text
APPROVE PRODUCTION BOT CLOUD logOut + Railway Local API cutover + production upload test
```

Do not ask the user to paste `TELEGRAM_TOKEN`, `api_hash`, or shared-secret into chat. Consume the existing Railway bot token and existing VPS API credentials through non-echoing, in-memory pipes.

- [ ] **Step 3: Cut over with rollback captured first**

Record current Railway deployment/config presence and Local API health, prepare rollback commands, call Telegram Cloud `logOut` for the production bot once, set Railway `TELEGRAM_API_BASE_URL=https://tg.toanaas.vn`, shared-secret header variables, 500 MB intake/output limits, and one-hour processing timeout, then redeploy newest `main`.

- [ ] **Step 4: Prove real Telegram transfer**

Send a small control and the 74,838,369-byte MP4 through the production bot without selecting a paid provider. Verify Local Bot API `getFile`, Railway download, the allowed free/local processing path, returned artifact size/container/duration, Telegram delivery, no Xu deduction, and no token in logs.

- [ ] **Step 5: Roll back on failed health or delivery**

If production stops receiving updates or cannot return the artifact, restore the captured Railway variables/deployment and document Telegram's cloud re-login timing constraint. Do not touch Product Video worker or unrelated modules.

### Task 8: Final evidence report

**Files:**
- Create: `outputs/SECURITY_VPS_PRODUCTION_CUTOVER_REPORT.md`

- [ ] **Step 1: Separate all status dimensions**

Report code commit/PR/merge, Railway deployed SHA, VPS service state, production bot identity, small-file result, 74.8 MB result, 500 MB/one-hour configured limits, rollback result, and `LOCAL BOT API PRODUCTION PASS` separately.

- [ ] **Step 2: Apply strict PASS wording**

Set `LOCAL BOT API PRODUCTION PASS = YES` only after production Telegram evidence exists. Keep `SUBDUB MP4 LIVE PASS = NO` because no paid-live provider test is authorized.
