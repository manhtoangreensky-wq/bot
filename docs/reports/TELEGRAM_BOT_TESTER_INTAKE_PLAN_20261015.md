# Telegram bot tester intake plan — 2026-10-15

## 1. Contract and immutable scope

This run handles only Telegram UI/callback defects: stale callback expiry,
wrong Back/Home ancestry, duplicate ACK, pending-state cleanup, missing
handler evidence and callback latency evidence. It must not change or register
Product Video, Video, Image, Music, Voice, SubDub, provider, worker, job,
pricing, wallet/Xu, PayOS, AutoPost, ENV/secrets or production data logic.

The supplied tester/PDF material is filtered before implementation. Legacy and
WebApp findings with no active Telegram producer/registered handler are recorded
as unmapped and are not copied into `bot.py`.

## 2. Ordered plan and acceptance gates

1. **READ:** identify the current producer and the exact registered handler for
   one callback family; inspect the current-main source, not a stale branch.
2. **CONTRACT:** open one narrow spec only when a side-effect-free exact-handler
   RED proves stale acceptance, wrong destination, duplicate ACK or an actual
   latency defect. Record protected-scope lock before editing.
3. **BUILD:** make the smallest UI/callback guard or destination correction;
   preserve every producer-backed valid value.
   A test-only entry may be added to `.github/workflows/ci-main.yml` so each
   locked callback defect remains a CI gate; workflow deploy behavior is frozen.
4. **REVIEW:** inspect the diff and reject any Product Video/SubDub/Voice/
   Music/Image/Video route or engine hunk, provider/worker/job/wallet change or
   generic router refactor.
5. **VERIFY:** run the focused registered-handler regression, compile changed
   tests, `git diff --check`, then the full-source compile/CI gates separately.
6. **REPORT:** update this plan, the audit checklist and the durable state with
   exact RED/GREEN output. A focused module alone never closes the whole goal.
7. **LEARN:** keep unresolved or unproven items explicitly open; do not promote
   a fixture result to a production/runtime claim.

## 3. Specs in this run

| Spec | Surface | Status | Evidence/next action |
|---|---|---|---|
| S12.35.477 | `menu|main` stale suffix | LOCKED GREEN | 2 focused tests OK; exact root unchanged |
| S12.35.478 | `menu|main_profile` stale suffix | LOCKED GREEN | 1 focused test OK |
| S12.35.479 | `menu|main_memory` suffix allowlist | LOCKED GREEN | exact root + `freehub` origin + stale case OK |
| S12.35.480 | `menu|main_video` stale suffix | LOCKED GREEN | 1 focused test OK; engine untouched |
| S12.35.481 | `menu|main_image` stale suffix | LOCKED GREEN | 1 focused test OK; engine untouched |
| S12.35.482 | `menu|main_guide` stale suffix | LOCKED GREEN | 1 focused test OK |
| S12.35.483 | `menu|main_music` stale suffix | LOCKED GREEN | 1 focused test OK; engine untouched |
| S12.35.484 | `menu|main_topup` stale origin | CLOSED AS ALREADY GUARDED | exact-main RED probe shows existing pre-ACK origin guard; speculative duplicate patch removed |
| S12.35.485 | `menu|translate` unknown suffix | LOCKED GREEN | producer-backed allowlist test OK; translation execution untouched |
| S12.35.486 | `menu|doc_tools` stale suffix | LOCKED GREEN | 1 focused test OK; document processing untouched |
| S12.35.487 | `menu|chat_pro` stale suffix | LOCKED GREEN | 1 focused test OK; chat provider/engine untouched |
| S12.35.488 | `menu|chat_free` stale suffix | LOCKED GREEN | 1 focused test OK; chat provider/engine untouched |
| S12.35.489 | `menu|admin` stale suffix | TARGETED GREEN | exact current-main RED, focused regression OK |
| S12.35.490 | `menu|finance` stale suffix | TARGETED GREEN | exact current-main RED, focused regression OK |
| S12.35.491 | `menu|billing` stale suffix | TARGETED GREEN | exact current-main RED, focused regression OK; wallet/payment logic untouched |
| S12.35.492 | `menu|main_docs` stale suffix | TARGETED GREEN | exact current-main RED, focused regression OK; document processing untouched |
| S12.35.493 | exact Admin submenu roots (11 producers) | TARGETED GREEN | matrix RED→GREEN (`Ran 1 test` with 11 subtests); child-origin maps remain unchanged |
| S12.35.494 | registered PayOS package ownership ACK | LOCKED GREEN | RED: unauthorized `payos_pkg|...` received normal ACK then alert; GREEN: producer/registration contract passes with alert-only denial; payment branches unchanged |
| S12.35.495 | registered manual package admin ownership ACK | LOCKED GREEN | RED: non-admin `manual|approve...` received normal ACK then denial alert; GREEN: admin gate precedes normal ACK; approval/payment branches unchanged |
| S12.35.496 | malformed provider-choice UID | DEFERRED BY PROTECTED SCOPE | `provider_keyboard()` emits `prov|voice/image|...|<uid>` and exact `^prov\\|` registration reaches `handle_provider_choice`; malformed UID reaches `int(uid_str)` before ACK. No patch is authorized in this UI-only batch because this is the protected Voice/Image provider-choice boundary. |
| S12.35.497 | Admin Ticket status callback out-of-range ID | LOCKED GREEN | exact registered `ticket|st|<id>|<status>` route reproduced an `OverflowError` before a safe alert when the decimal ID exceeded SQLite int64; bounded ASCII-decimal guard now returns one unsupported alert before lookup. |
| S12.35.498 | Admin Ticket list callback out-of-range offset | LOCKED GREEN | exact registered `ticket|al|<kind>|<offset>` route reproduced a SQLite-style `OverflowError` after a normal ACK; bounded int64 offset guard now returns one expired-button alert before list lookup. |
| S12.35.499 | Customer Ticket summary callback out-of-range ID | LOCKED GREEN | exact registered `ticket|summary|<id>|<origin>` route reproduced a SQLite-style `OverflowError` after ACK; bounded int64 ID guard now returns one unsupported alert before lookup. |
| S12.35.500 | Customer Ticket action ID overflow (`reply_user`/`attach`/`done`) | LOCKED GREEN | exact registered routes reproduced SQLite-style `OverflowError` after ACK; one shared bounded ID predicate now rejects all three before lookup/pending/action. |
| S12.35.501 | Internal Archive `view`/`file` out-of-range document ID | LOCKED GREEN | exact registered routes reproduced SQLite-style `OverflowError`; the bounded ASCII-decimal/int64 guard now returns one invalid-ID alert before lookup for both actions. Focused no-I/O runner: `RUN 6` / `ALL_OK`; changed test compile and diff check exit 0. |
| S12.35.502 | Knowledge Vault prompt/asset callback out-of-range ID | LOCKED GREEN | exact `^vault\\|` handler reproduced SQLite-style `OverflowError`; bounded ASCII-decimal/int64 admission now returns one alert before Vault for `use`/`approve_prompt`/`approve_asset`. Focused run: `VAULT_FOCUSED_RUN 2` / `ALL_OK`; test compile and diff check exit 0. |
| S12.35.503 | Document Tools `confirm` ACK ordering | LOCKED GREEN (CI) | exact registered `docflow|confirm` route now performs only in-memory admission before one ACK, then reads language and renders; regression locks ACK-before-language for a valid confirm and preserves one alert for too-few files. No file processing or charge path changed. |
| S12.35.505 | Admin Support/Broadcast Lite root stale suffixes | LOCKED GREEN (local) | `menu|admin_support` and `menu|admin_broadcast_lite` are emitted by Admin modules and registered through `handle_menu_callback`; exact current-main RED accepted either suffixed callback, cleared pending state and rendered a fallback screen. The exact-root guard now rejects both suffixes with one alert before cleanup/render; focused registered-handler matrix passes. |

### Continuation recheck — Admin Growth (no new implementation spec)

The current source was re-audited through the actual `^admin_growth\\|`
registration. An inert source-extracted runner reached 33 distinct emitted
callbacks, each with exactly one ACK and one render, and verified 11 malformed
trail cases fail closed before report/list reads. Three public-user cases were
denied without reads. The only two accepted callbacks not currently emitted
are the documented legacy unscoped `admin_growth|aff_add` and
`admin_growth|aff_import` guides. Result: `ADMIN_GROWTH_RECHECK=ALL_OK`; no
new RED, so no code/spec change is authorized. This is fixture evidence only,
not live Telegram latency evidence.

`menu|main_quick` and `menu|main_audio` were probed but have no current
literal producer that can justify a new guard; they remain `NOT_OPEN` rather
than receiving speculative code. `menu|autopost` remains out of this run as
WIP. `menu|billing` now has its own exact-root spec; no broad admin/finance
guard is introduced.

S12.35.494 changes only the ACK order in `handle_package_choice`: malformed
 callbacks keep one normal ACK, an unauthorized owner token gets one alert ACK,
 and an authorized owner gets one early normal ACK before the existing payment
 flow. No order, wallet, PayOS request, price or provider branch changes.

S12.35.495 applies the same ACK-only contract to `handle_manual_package_choice`:
malformed controls receive one normal ACK, non-admin approval actions receive
one denial alert, and authorized admin actions receive one normal ACK before
the existing read/approval branch.

S12.35.496 is a follow-up item only. Reopening it requires explicit Owner
permission for a narrow malformed-UID guard at the protected provider-choice
boundary; no permission is inferred from this UI audit.

S12.35.497 changes only the Admin Ticket status callback's ID validation. Valid
SQLite-range IDs keep the existing lookup, status update, and Back rendering;
out-of-range or malformed values are rejected before any ticket lookup. No
ticket data, wallet, payment, provider, job, product engine or AutoPost path is
changed.

S12.35.500 applies the shared Ticket ID admission check only to the three
customer action callbacks `reply_user`, `attach` and `done`. Valid IDs retain
their existing reply/attachment/resolve and Back behavior; malformed or
out-of-range IDs stop before lookup and pending/action changes. No ticket data,
wallet, payment, provider, job, product engine or AutoPost path is changed.

S12.35.499 changes only the Customer Ticket summary callback's ID admission.
Valid SQLite-range IDs and both existing result origins retain the current
summary screen and Back controls; malformed or out-of-range IDs are rejected
before the ticket getter. No ticket data, wallet, payment, provider, job,
product engine or AutoPost path is changed.

S12.35.498 changes only the Admin Ticket list offset admission check. Valid
SQLite-range offsets retain the existing list and pagination behavior; malformed
or out-of-range offsets return the existing expired-button alert before any
ticket list read. No ticket data, wallet, payment, provider, job, product
engine or AutoPost path is changed.

S12.35.503 changes only the ordering at the Document Tools callback boundary.
`docflow|confirm` checks its already-loaded pending state and minimum-file
condition before acknowledging exactly once; valid confirmation ACKs before the
language lookup/render path, while the too-few-files alert remains the sole ACK.
Document processing, file delivery, charging, wallet, provider, engine and
AutoPost paths are unchanged.

S12.35.505 changes only the exact-root label map used by the existing stale
`menu|` guard. `menu|admin_support` and `menu|admin_broadcast_lite` remain valid
producer-backed roots and continue to render their existing Admin pages; only
suffixed/stale variants are rejected before pending cleanup or rendering. No
Ticket/Broadcast data or action, wallet, provider, job, product engine or
AutoPost path changes.

## 4. Release-gate result and remaining evidence

- Full `bot.py` compile was not counted locally because the bounded Windows
  observation emitted no completion marker; this is `NOT_VERIFIED`, not a
  syntax failure. The exact-head Ubuntu source-compile run `38758593047`
  completed SUCCESS and verified the source compile/tokenize guards.
- The broader Admin child/Back regression runner did not return a completion
  marker in the bounded local observation window; it is `NOT_VERIFIED`, not a
  product failure or pass, and is not being repeated unchanged.
- PR #1432 is merged: head `44156d7a7952cb27e698c0be4cbe6c3daf47fcc7`, merge
  commit `55abb1d0701a2e6f7e399d6583a2ad2b91687afc`. Exact-head full
  hygiene/regression CI `38758593472` and source-compile CI `38758593047` are
  SUCCESS; selected stale-root, Admin/customer, ACK and workflow gates are
  green.
- The one approved bot-only deploy `38761999018` is SUCCESS with
  `deploy_workers=false`. Read-only VPS verification reports BOT_SHA
  `55abb1d0701a2e6f7e399d6583a2ad2b91687afc`, all three services active,
  `NRestarts=0`, and `/health` status `ok`.
- Protected-scope review remains clean: no Product/Edit/Image/Video/SubDub/
  Voice/Music route or engine, provider, worker, AutoPost, wallet/PayOS,
  ENV/secret or production-data change was introduced. Provider calls, wallet
  mutations, production DB writes and real Telegram sends are all `0`.
- Remaining gate is A7 only: Account → Back has no exact anonymous server event
  correlated to the Owner's click timestamp. Therefore client/network cause,
  device diagnosis and “all buttons are smooth” are not claimed; no hardware or
  latency patch is justified without that evidence.
