# Product Video: Storyboard Tail Duration, 2026-11-10

TASK=PV-S04R01
OWNER_SCOPE=NARROW_STORYBOARD_BRANCH_AND_OFFLINE_TESTS
BASE_SHA=e2905a42308a641f99de77daa6ea2b12ef7a2271
STATUS=OFFLINE_REGRESSION_PASSED_PUBLICATION_GATES_PENDING
DEPLOY=NO
LIVE=NOT_TESTED

## Runtime Contract And Exact Change

The Storyboard planner and approved dual-tier routing contract both use8s
per scene for tiers400 and800. Generic tier800 for AI Prompt, Trend and
Script remains10s. Product eligibility, routes, prices and invoice rules
are not changed by this correction.

The real `video_uiflow3_apply_tail_quality_contract` helper previously read
generic tier duration and wrote10s into the Storyboard800 execution snapshot.
The Storyboard-only branch now uses existing
`video_storyboard2.SCENE_SECONDS`. All other products continue using generic
quality seconds. No function signature, return shape, caller, renderer,
provider, wallet/ENV/DB or Multi/Smart/Local Edit code was changed.

The regression fixture had also drifted: it expected Storyboard500/5s to
succeed although that product supports only400/800. The invalid500 coverage
is retained as a rejection case rather than accepted or silently removed.

## Measured RED -> GREEN

Existing stale positive tuple:1 failed in1.41s with
`quality_tier_not_supported`. After fixture correction and new independent
literal duration controls:33 passed/1 failed in3.83s. The only failure was
Storyboard800 `10 == 8`. After the narrowly approved runtime fix, the exact
same combined selection completed **34 passed in4.97s**, exit0:

```text
tests/test_p0_product_video_tail_quality_integrity.py                  24 cases
tests/test_p0_video_uifreeze1_menu_pricing_public_freeze.py             7 cases
tests/test_p0_video_tailflow18_locked_order.py                         3 cases
TRANSPORT_GUARD_CANARY=PASS
OUTBOUND_TRANSPORT_ATTEMPTS=0
BOT_MODULE_IMPORTED=False
```

The checks exercise the real extracted helper, real planning snapshots,
hash/legacy snapshot persistence and routeengine handoff. Expectations are
literal8/10, not derived from the implementation constant. Eight unsupported
Storyboard tiers must reject without mutating planning or selected Tail
inputs. Generic800 controls guard against a global duration change.

No original assertion or valid non-Storyboard case was removed. The quality
integrity file is added to the existing provider-free CI contract selection;
runner credential/network/storage guards remain unchanged. A green older
main CI did not cover this previously omitted regression file.

## Original Versus Current Evidence

The original current planner contract at
`services/video_storyboard2.py::SCENE_SECONDS` and dual-tier acceptance in
`tests/test_p0_storyboard_dual_tier_routing.py` remain authoritative. Only the
old positive tier500 fixture was stale. This report does not declare the
historical implementation or all customer jobs correct/incorrect.

Source lookup found two Bot callers:commercial Tail guard and invoice
preparation. Those callers are unchanged. Text search does not establish
absence of dynamic callers, so regression scope is reported explicitly.

## Tester Handoff And Remaining Gates

Tracker:#1155; master:#1457. Case index:
`KIEM-THU/DANH-SACH-CASE.md::PV-STORYBOARD-TAIL-DURATION-01`.
Run the24-case quality file with the existing isolated provider-free CI
fixture setup; include the named7+3 comparators for the34-case local scope.
No live/provider request is necessary to reproduce this snapshot defect.

Full Bot source compile and exact-head CI are separate publication gates.
The local Python3.12 full-source compile did not return a terminal result
within this review and was stopped; it is NOT counted PASS. The testfile
py_compile passed. Publish as a draft candidate for the existing Python3.11
exact-head full compile/CI gate; no merge/deploy readiness before that succeeds.
This report's local34-case result is not a full repository pytest PASS, a
provider result, real MP4 render, Telegram delivery or completion of S04.
Current deployed checkout last read804e23da is distinct from this branch;
no deploy/restart/live was authorized by this narrow Owner approval.

Rollback must distinguish source candidate from deployed and live checkpoints.
If this patch regresses after a later authorized deployment, revert only its
Storyboard helper hunk/associated tests as appropriate; never reset unrelated
accepted work or replace existing protected Multi/Smart rollback tags.
