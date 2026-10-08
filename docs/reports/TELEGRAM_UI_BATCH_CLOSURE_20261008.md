# Telegram UI/callback batch — closure evidence, 08/10/2026

Status: PR #1410 MERGED and VPS delivery verified. This closes the delivered UI batch only; the whole-bot audit remains active with A3/A5/A6/A7 evidence gaps.

## Contract and source truth

- Delivered branch: `audit/telegram-small-flow-batch-20261007` (PR #1410). A separate local follow-up is on `audit/telegram-small-flow-followup-20261008`.
- Audit base: `93919f93d7207f252252f10f9c03d1e8a2d458f8`.
- Current main/runtime after delivery: `87bf32064473b02ee32aa6a6b63997ae3ef9b533`; `bot.py` blob `be492b669138370639318763ce4436411b7bcc8f`. PR #1409 (`d24716db…`) was deployed first; its provider router blob `578f6e103cb11997d497de86238b55aab4e3d9a5` remains unchanged by #1410.
- Owner's latest rule: finish one defect and its regression before proceeding; record difficult unresolved defects for Owner at task end.
- Scope: Telegram UI labels, emitted callback/navigation origin, Back/Home, draft cleanup, stale/ownership checks and verification/documentation. AutoPost WIP and stable processing engines are protected.

## Final review findings resolved sequentially

| Spec | Confirmed RED | Correction | Focused GREEN |
|---|---|---|---|
| S12.35.75 Prompt Copy | 3 behavioral assertions: misleading Meta label, missing copy help, lost result-list Back | Honest Copy label/manual instructions and library-item keyboard for copy/prompt_back | 1 method, 1.531s, actual registered handler/emitter |
| S12.35.76 Marketing | 7 assertions: 6 follow-ups and custom brief lost CSKH origin | Existing origin passed into two result renderer calls | 5 tests, 7.439s; CSKH and legacy Admin |
| S12.35.77 Memory search | 11 assertions: stale/expired/foreign/nonmember controls plus residual draft | Validate search-tagged View/Delete before read/cleanup; clear actor draft on valid result Back | 6 regression, 5.960s; saved-list/delete-picker/Start/Menu preserved |
| S12.35.78 Operator/System | 7 assertions: 6 descendants lost Operator plus invalid guide fallback | Closed origin carried across child/Details/Refresh/Back | 3 regression, 39.974s; legacy/public/stale coverage |

All focused failures were behavioral assertions, not setup errors. Fixtures did not submit paid providers, mutate wallets, write production DB, create jobs or send real Telegram messages. Destructive Memory confirmation was never dispatched.

## Protected source comparator

Compared baseline and current `bot.py` by hashing declaration text blocks bounded by top-level def/class/uppercase assignment markers. This is a text comparator, not an AST function count or runtime coverage claim.

- 23 changed blocks are UI/keyboard/origin renderers and two Admin UI mapping constants.
- 9,742 declaration blocks remain identical.
- `git diff --name-only` under services/providers/workers/engines/config and worker/requirements files returned no changes.
- Independent read-only diff review found the four defects above; no provider/wallet/product executor/AutoPost WIP change was found.

## Verification gates

- Changed-test compile: 23 files passed before the final test-only self-shot fixture adjustment; its unchanged two assertions then passed in 0.524s.
- State YAML: syntax issue from two misindented evidence fields corrected; parser passed at S12.35.79.
- Final bot compile: `python -B -S -m py_compile bot.py` exit 0 with `FINAL_BOT_PY_COMPILE_OK`; source blob `be492b669138370639318763ce4436411b7bcc8f`.
- Full safe UI gate: 41 CI-configured modules → `218 passed, 355 subtests passed in 589.44s (0:09:49)`. Linux workflow-hygiene tests remain a separate Ubuntu CI gate.
- Gate isolation: `--noconftest` avoids unrelated legacy autouse fixture importing bot runtime; assertions use source-extracted production handlers/registrations. Launcher output: `NO_BOT_RUNTIME_IMPORTED`.
- Previous broad attempts superseded after identifying whole-file AST extraction and unrelated autouse bot import; they are NOT_PASS and contribute no test-count claim.
- Protected comparator: `PROTECTED_SCOPE_COMPARATOR_PASS changed_ui_blocks=23 unchanged_declaration_blocks=9742`; file-scope assertions passed.
- Delivery: PR [#1410](https://github.com/manhtoangreensky-wq/bot/pull/1410) merged as `87bf32064473b02ee32aa6a6b63997ae3ef9b533`. Merge-SHA CI [#37723283055](https://github.com/manhtoangreensky-wq/bot/actions/runs/37723283055) succeeded. Exact-SHA bot-only deployment [#37727154776](https://github.com/manhtoangreensky-wq/bot/actions/runs/37727154776) succeeded with `DEPLOY_WORKERS=false` and `WORKER_RELEASE_ACTIVATION_SKIPPED=bot-only`.
- Live verification: VPS SHA and `bot.py` blob match #1410; router blob matches already-deployed #1409. `toanaas-bot.service`, `toanaas-web.service`, and `nginx.service` active/running, all `NRestarts=0`; loopback `/health` returned `status=ok`.
- The workflow's rollback retention pruned the older VPS backup directory `deploy-76f0454fbab5e467f9ca71a0135b6fd05d8d70c4-20261007124309`; the GitHub commit remains available for redeployment, but that server-side backup directory is gone.

## Difficult fault deferred to Owner: Account Back latency

The Owner reports 2–3s click-to-screen. Recent menu server dispatch samples are 306.038, 360.419, 424.794 and 512.953ms; guard phases 33.458–118.951ms and render-helper phases 89.179–101.572ms. Journal events were found outside the previously queried narrow windows.

These samples identify only the generic menu family and omit pre-handler wait and client delivery/render. No exact user timestamp is matched. One fresh public Telegram HTTPS request took 734ms; it was not a bot-method or warm-connection test. VPS load/RAM did not establish overload. No network/device/server cause or hardware purchase is supported.

Per Owner instruction, retain this as unresolved for synchronized click recordings and ingress/server timing. No claim that every button is smooth or the whole bot is error-free.

## Remaining whole-goal work

1. A3/A5 customer route families and safe dynamic terminals remain partial; Account → Gói của tôi → Account and the three Account referral read-only children are now covered by local S12.35.82–83 through the registered handler with inert fixtures. Continue with the next safe terminal.
2. A6 visual/client layout evidence remains unverified; source/keyboard review is not a claim about Telegram viewport rendering.
3. Account → Back 2–3s remains unresolved. S12.35.81 adds a local anonymous `account_root` route key to timing logs, but it is not deployed and has no new live sample. No latency cause is assigned.
4. The follow-up source/test/docs are local and unpushed. No further merge/deploy/restart is authorized by this delivery verification until the ordered follow-up review and final CI gate are complete.

Source ledger: `TELEGRAM_SMALL_FLOW_AUDIT_CHECKLIST_20261006.md`; registration evidence: `TELEGRAM_CALLBACK_HANDLER_EVIDENCE_20261006.md`; tester cases: `KIEM-THU/DANH-SACH-CASE.md`.
