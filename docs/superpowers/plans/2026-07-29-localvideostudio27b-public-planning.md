# Local Video Studio 27B Public Planning Implementation Plan

> For agentic workers: use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox syntax.

Goal: Add one feature-gated Vietnamese planning-only Local Video Studio entry under the existing Video Edit hub while preserving every existing product route and state.

Architecture: Keep services/local_video_studio_preview.py as the canonical 26I catalog/validator/pagination source. Add services/local_video_studio_public.py as a pure lvs27b adapter with separate session/backstack/TTL and text view model. Add one conditional keyboard row and one narrow callback adapter in bot.py; commit state only after a successful Telegram edit/reply.

Tech Stack: Python stdlib, existing python-telegram-bot primitives, pytest, canonical 26I JSON and fake Telegram objects.

---

## File structure and immutable boundaries

- Create: services/local_video_studio_public.py — public state machine, callback parser, readiness-safe view model, summary text and store helpers.
- Modify: bot.py — flag constant, conditional secondary action, import, narrow handler and lvs27b registration only.
- Create: tests/test_p1_localvideostudio27b_public_ui.py — focused contract and fake-transport tests.
- Create: the design doc in docs/superpowers/specs/.

Do not modify 27A service/tests, capability JSON, Product Video, SubDub, Frame Video, renderer, worker, provider adapters, DB, PayOS, wallet/Xu, Railway/VPS or Music/Suno.

## Task 1 — Baseline and design record

- [x] Confirm origin/main is 2622328872800abc08ec44372d49e05e8433618a and PR #589 delta is only bot.py plus its receipt-truth test.
- [x] Create the approved design doc and record the selected thin-adapter approach.
- [x] Run the existing 27A focused test and the PR #589 receipt-truth test before implementation; record timeout/failure honestly.

Commands:
  & $py -m pytest -q --noconftest tests/test_p1_localvideostudio27a_preview.py
  & $py -m pytest -q --noconftest tests/test_p0_subdub_production_receipt_truth.py

## Task 2 — Write failing 27B contract tests (RED)

Create tests/test_p1_localvideostudio27b_public_ui.py before production code. The first wished-for API assertions are:
  service = importlib.import_module('services.local_video_studio_public')
  assert service.CALLBACK_PREFIX == 'lvs27b'
  assert service.STATE_KEY == 'local_video_studio27b_public'
  assert service.new_session('session-a')['screen'] == 'goal'
  assert service.render_view(service.new_session('session-a'))['screen'] == 'goal'

Add tests for exact flag-off keyboard preservation and one flag-on lvs27b|open row, canonical index reuse without a second JSON, 11 local groups, 64-byte callbacks, all flow/back/pagination/summary behavior, and no duplicated capability IDs.

Add fake Query/Message objects that append edit, reply, commit, delete and answer to an event list. Assert edit-or-reply happens before commit/delete and callback answer is last. Assert both-send failure leaves state unchanged. Add static checks that the adapter imports no provider/worker/billing module and has no render/download/media-send path.

Run RED:
  & $py -m pytest -q --noconftest -p no:cacheprovider tests/test_p1_localvideostudio27b_public_ui.py
Expected: collection/import failure because the public adapter and integration do not exist yet.

## Task 3 — Implement the pure public adapter (GREEN)

Create services/local_video_studio_public.py with:
  CALLBACK_PREFIX = 'lvs27b'
  STATE_KEY = 'local_video_studio27b_public'
  SESSION_TTL_SECONDS = 1800
  PUBLIC_READINESS_STATES = ('CONTRACT_ONLY', 'LOCAL_PLANNING_READY', 'REQUIRES_RUNTIME', 'REQUIRES_PLANNED_SHOOT', 'NOT_SUPPORTED')

Import the canonical 27A service as catalog_source and alias its local/paid record tuples, QA IDs, load_capability_index, validate_capability_index, capability_coverage and paginate. Do not repeat capability IDs or read a second JSON path.

Implement new_session(session_id, now=None), session_store_key(user_id, chat_id, session_id), new_store(), session_is_fresh(), normalize_session(), callback_data(), parse_callback(), apply_callback(), commit_callback_id() and render_view(). State fields are version, session_id, created_at, updated_at, screen, history, goal, record_id, selected_ids, catalog_page, detail_page and processed_callback_ids.

Allow only open, goal, catalog, detail, select, safety, summary, save, back and close. Enforce current-screen and selected-capability prerequisites; reject malformed/stale/deleted state without mutating input. Use record/index tokens for detail callbacks so every button is at most 64 UTF-8 bytes. Back from goal returns exit_parent=True; inner Back pops exactly one history entry.

Render Vietnamese text with the mandatory no-render wording, selected IDs, mapped readiness, rights/safety, sequence, blockers and next manual step. Catalog exposes only LOCAL_RECORD_IDS; detail uses shared paginate; save returns text only. Sanitize paths/provider/debug/secret-like metadata.

Run narrow service tests after each implementation slice; pure-service tests must pass before bot integration.

## Task 4 — Minimal bot adapter and flag-gated button

In bot.py add LOCAL_VIDEO_STUDIO_PUBLIC_ENABLED = env_flag('LOCAL_VIDEO_STUDIO_PUBLIC_ENABLED', '0'). Keep all existing video-edit rows unchanged when false; append only [( '🧭 Lập kế hoạch dựng video', 'lvs27b|open' )] when true.

Import the public service, map its rows with existing Telegram button primitives, and register CallbackQueryHandler(handle_local_video_studio_public_callback, pattern=r'^lvs27b\|'). The handler allows normal/admin users, remains behind the existing global dispatch/safe-mode callback guards, rejects disabled/stale/malformed callbacks truthfully, and stores separate state keyed by user/chat/session. The accepted base has no repository-wide banned-user predicate or account-status field, so 27B must not invent a second authorization system.

Use this transaction order: compute candidate → edit current message or approved reply/bot fallback → commit/delete session → answer callback. Root Back renders the existing Video Edit hub and deletes the public session only after successful delivery. No runtime, provider, worker, invoice, status or media API is reachable.

## Task 5 — Focused fake-transport verification

Run the complete 27B test file and exercise fake Telegram transport for flag ON/OFF, normal/admin/unauthorized access, two session keys, TTL expiry, duplicate callback IDs, edit failure/reply fallback and double failure. Confirm callback-owner matrix has no collision; the only intentional parent boundary is root Back to videoedit|hub.

Commands:
  & $py -m pytest -q --noconftest -p no:cacheprovider tests/test_p1_localvideostudio27b_public_ui.py
  & $py -m py_compile services/local_video_studio_public.py tests/test_p1_localvideostudio27b_public_ui.py

## Task 6 — Required regression and static gates

Run focused 27A, all 26C–26I, callback-owner, Product Video UI-freeze, relevant Video Edit UI and tests/test_p0_subdub_production_receipt_truth.py. Run tokenize and narrow AST/source checks for bot.py, git diff --check, secret/private-path scans and changed-file boundary checks. Full bot.py bytecode compile may time out like baseline; report its actual exit code and duration, never treat timeout as pass.

## Task 7 — Review, commits, push and stop gate

Request independent review of the design/implementation diff, fix critical/important findings and rerun gates. Make two narrow commits:
  git add docs/superpowers/specs docs/superpowers/plans
  git commit -m 'docs: design gated public Local Video Studio planning flow'
  git add services/local_video_studio_public.py tests/test_p1_localvideostudio27b_public_ui.py bot.py
  git commit -m 'feat: add fail-closed lvs27b public planning adapter'

Fetch/recheck origin/main before push. Push feat/p1-localvideostudio27b-public-ui, open PR titled P1.LOCALVIDEOSTUDIO27B: add gated public planning UI, collect CI evidence, and stop. Do not merge, deploy, alter Railway ENV or run production Telegram smoke.
