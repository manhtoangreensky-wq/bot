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

## 4. Release gates still open

- Full `bot.py` compile emitted `COMPILE_START` but no completion marker during
  a bounded ~300s observation and was stopped with Ctrl+C; status is
  `NOT_VERIFIED` locally, not a syntax failure. Exact-head CI later verified
  `Compile Complete Bot Source` and `Python Compile Guard` successfully in run
  `38700321728`.
- The broader Admin child/Back regression runner did not return a completion
  marker in the bounded local observation window; it is `NOT_VERIFIED`, not a
  product failure or pass, and is not being repeated unchanged.
- Exact-head CI run `38700321728` completed SUCCESS. The source compile guard
  run `38700321747` also completed SUCCESS; all selected Admin/customer,
  stale-root, PayOS ACK and workflow-hygiene steps were green.
- Protected-scope comparator must show no route/engine/provider/worker delta.
- No provider call, wallet mutation, production DB write or real Telegram send.
- Merge, deploy, restart and live-client latency claims remain separate owner
  gates; focused fixture GREEN is not LIVE evidence.
