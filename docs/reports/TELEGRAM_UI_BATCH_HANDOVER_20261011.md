# Telegram UI/callback — batch continuation 11/10/2026

Status: this handover is a historical pre-delivery snapshot. The batch was
later delivered once through PR #1432 and bot-only deploy run #38761999018;
whole-goal status remains ACTIVE only because A7 client-correlation evidence is
still missing.

## Current operating checkpoint

- Read-only GitHub/VPS check: both revisions are
  `5c38bd31c20f26f815e2f05b6419f4dd64afbba9`; bot/web/nginx are active/running,
  `NRestarts=0`. The earlier protected #1420 deployment hold is cleared.
- Candidate branch: `audit/telegram-ui-closure-20261011`, based on
  verified main `5c38bd31c20f26f815e2f05b6419f4dd64afbba9` after one clean
  sync/rebase. Original audit checkpoint was `b2a45cf72c8d11b838ce67101c6385128106e856`.
- Current candidate bot blob:
  `280e1ab01fbb1ba055451c598af4bed5df1f2f37` (post-sync).
- Scope: emitted callback destinations, Back/Home context, pending expiry,
  callback acknowledgement and display/read scheduling. Processing engines,
  provider/worker, wallet/payment and AutoPost implementation are protected.

## Previous behavior and candidate correction

| UI path | Confirmed previous behavior | Candidate behavior / evidence ledger |
|---|---|---|
| Tax report and Finance Audit Back | Skipped Tax/VAT/CIT and returned to Finance root | Immediate tax parent; S12.35.291–.294 |
| Catalog/Account Packages and Large Order | Lost the opening Catalog/Account/detail context | Origin retained across group/detail/Back; compact detail tokens preserve the 64-byte callback limit; .187/.203/.253 |
| Support My Tickets and Feedback receipt | Selected child/result Back lost its opening page | Exact Support/Account/result/list ancestry; .206/.219–.224 |
| Translation voice picker | Missing parent Back; expiry interfered with More/Back | Bounded Language/Media/action/command origin and recovery; .287 |
| Read/display callback acknowledgement | Selected language/SQLite work ran before ACK | Selected Ticket/Archive/Feedback/Document routes ACK before their read/display work; .271–.285 |
| Expired Document/Support input | Could fall through to generic chat | Expired input is consumed and returns to its recovery menu; .210/.212 |
| Ticket detail malformed ID | Missing ID raised IndexError; Unicode ID raised ValueError after pending cleanup | Validate bounded ASCII decimal ID before lookup/cleanup; .296 |

These changes are candidate behavior until the batch delivery is verified.
The full per-spec RED/GREEN history is in the
[checklist](TELEGRAM_SMALL_FLOW_AUDIT_CHECKLIST_20261006.md) and
[registered-handler evidence](TELEGRAM_CALLBACK_HANDLER_EVIDENCE_20261006.md).

## Verification and release gates

- The initial 64-file run collected 577 items: `77 failed, 507 passed,
  785 subtests passed in 1438.16s`. This run is not a PASS. Failure entries
  include sandbox TEMP/Bash errors and source-fixture expectations; their
  sequential classification is in S12.35.295.
- Broadcast: 4 tests/1.066s OK with usable fixture TEMP. Feedback: 12 tests
  passed/7.13s after one missing inert presentation stub was supplied.
- Package compact-token expectation corrections retain semantic Back checks;
  the two affected matrix methods passed 2 tests/41.145s.
- Ticket malformed-ID and foreign recovery checks passed 2 tests/15.784s;
  full Ticket ancestry/reply-origin regression passed 41 tests/206.240s.
- Source text comparison: 43 UI declaration blocks changed, 2 UI helpers
  added, 0 blocks removed; 5,352 protected-pattern blocks unchanged against
  current main and no
  protected file changes. These are text-block counts, not runtime coverage.
- CI now explicitly selects 64 test files; local UI selection is 63 files.
  Linux workflow hygiene remains mandatory on Ubuntu CI before merge.
- Pre-sync candidate full `py_compile bot.py` plus changed ancestry/package
  tests completed with exit 0 at blob `93ed4463…`. The failed-only UI rerun
  returned `7 passed, 79 deselected, 3 subtests passed in 62.78s`, exit 0;
  Package subtest matrices were verified separately as recorded above.
  One final sync/rebase is complete; post-sync Ticket validation passed
  2 tests/12.872s. Full post-sync compile completed with exit 0. Remote CI and one batch
  merge/deploy are pending.

## Tester handoff and difficult residual cases

Use the UI cases in [DANH-SACH-CASE.md](../../KIEM-THU/DANH-SACH-CASE.md)
and the existing `.github/ISSUE_TEMPLATE/05-telegram-ui-callback.yml`.
Record the exact path, expected/actual parent, HH:MM:SS +07, spinner duration
and screen duration. The fixture cases can run without a production action.

- Account → Back remains Owner-reported 2–3s without a matched server event.
  A7 stays deferred/open; no network/device/VPS purchase diagnosis is supported.
- Telegram client wrapping/visual QA and all-button smoothness remain unverified.
- The Image Story aspect/prompt mismatch (.106) remains excluded by Owner.
  The aspect experiment and dependent .108 are absent from this batch.

`MERGED != DEPLOYED != LIVE`. A local test or active service does not establish
client smoothness or product-output success.

## Superseding delivery readback — 15/10/2026

- PR [#1432](https://github.com/manhtoangreensky-wq/bot/pull/1432) is merged:
  head `44156d7a7952cb27e698c0be4cbe6c3daf47fcc7`, merge commit
  `55abb1d0701a2e6f7e399d6583a2ad2b91687afc`.
- Exact-head CI `38758593472` (full hygiene/regression) and
  `38758593047` (source compile) are `SUCCESS`. Deploy
  [`38761999018`](https://github.com/manhtoangreensky-wq/bot/actions/runs/38761999018)
  is `SUCCESS` with `deploy_workers=false` and target SHA
  `55abb1d0701a2e6f7e399d6583a2ad2b91687afc`.
- VPS readback: bot SHA equals target, bot/web/nginx are `active`,
  `NRestarts=0`, and `/health` is `ok`. The protected product/provider/worker,
  wallet/PayOS and AutoPost scope was not changed by this UI batch.
- The delivered callback fixes are locked; no second code patch is opened merely
  to polish a passing route. A7 remains partial because Account → Back has no
  exact click-correlated anonymous event. Do not infer network/device/VPS cause
  or all-button smoothness from the current server samples.

### Superseding handover — 16/10/2026

The continuation is delivered and runtime-verified: PR #1434 merged at
`3d17231cdfbffecdf999b3398c189bb83f36558e`; workflow `38784324561` succeeded
with `deploy_workers=false`; VPS SHA/services/health match. S12.35.505 is
closed as live evidence. Keep A7 explicitly deferred and do not reopen the
already-verified callback code without a new RED and Owner scope decision.
