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

`menu|main_quick` and `menu|main_audio` were probed but have no current
literal producer that can justify a new guard; they remain `NOT_OPEN` rather
than receiving speculative code. `menu|autopost` remains out of this run as
WIP. `menu|billing` now has its own exact-root spec; no broad admin/finance
guard is introduced.

## 4. Release gates still open

- Full `bot.py` compile emitted `COMPILE_START` but no completion marker during
  a bounded ~270s observation and was stopped with Ctrl+C; status is
  `NOT_VERIFIED`, not a syntax failure. Exact-head CI must still return an
  actual exit marker.
- The broader Admin child/Back regression runner did not return a completion
  marker in the bounded local observation window; it is `NOT_VERIFIED`, not a
  product failure or pass, and is not being repeated unchanged.
- Protected-scope comparator must show no route/engine/provider/worker delta.
- No provider call, wallet mutation, production DB write or real Telegram send.
- Merge, deploy, restart and live-client latency claims remain separate owner
  gates; focused fixture GREEN is not LIVE evidence.
