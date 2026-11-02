# Product Video catalog and Tail test reconciliation

## Scope and authority

- Base: `2e622359ec73125fc0aa99b72a3d2be3d567a776`.
- Tracker: [#1155](https://github.com/manhtoangreensky-wq/bot/issues/1155).
- Owner requested an ordered completion plan, safe merges, and live acceptance for missing Video lanes.
- This patch changes regression tests, CI selection, and handover documentation only.
- Runtime modules, provider routes, pricing configuration, workers, wallet/payment, and locked Multi/Smart lanes have no diff.

## Measured baseline

The existing complete catalog and menu-to-status suites returned:

```text
19 failed, 125 passed
BLOCKED_EXTERNAL_SOCKET_ATTEMPTS=0
```

Failures were outdated test expectations after accepted product changes:

1. Eight Storyboard cases still expected all ten quality tiers. The current
   dual-tier contract from PR #1445 permits only 400 and 800.
2. Ten Long Series quality cases still expected `multi_scene_film_under_upgrade`
   during confirmation after PR #1455 enabled `multi_scene_film`.
3. One menu-to-status case still asserted that Long Series was disabled and
   skipped its confirmation/status assertions.

These are test/contract mismatches on the base. They are not evidence that a
new production job failed or that every other product works live.

## Changes

- Preserve all ten Storyboard test inputs. Two supported tiers must reach
  invoice/confirmation; eight unsupported tiers must fail before mutating the
  input selection, invoice identity, or confirmation state.
- Use the Storyboard offer when preparing the test invoice. Protect the
  product-specific tier 800 contract: 8 seconds and 1714 Xu per scene.
- Require enabled Long Series to confirm once and reject duplicate creation.
- Run the existing menu-to-status confirmation/delivery-receipt contract for
  Long Series instead of its obsolete early-return branch.
- Preserve `video_long` execution lock explicitly and add a real
  `confirm_once` rejection assertion after an invoice is prepared.
- Add the two complete suites and Tail18 ordering suite to the quality CI.
- Label the legacy Idea adapter tests as contract-only. They do not reopen
  Owner-closed standalone Idea live acceptance.

## Verification

Run from the repository root with dependencies installed:

```powershell
python -m pytest -q --noconftest tests/test_p0_product_video_all_quality_tiers_multi_product_matrix.py tests/test_p0_product_video_full_menu_tail_to_status_matrix.py tests/test_p0_video_tailflow18_locked_order.py
```

Branch result under the local audit harness, with external sockets blocked:

```text
148 passed in 8.19s
BLOCKED_EXTERNAL_SOCKET_ATTEMPTS=0
EXIT_CODE=0
```

The two original files retain all 144 cases, and Tail18 retains its 3 cases.
One new `video_long` confirmation-lock case makes 148 total. No failure was
hidden by a skip, deselection, or removed case. The 19 obsolete expectations
were replaced by current product behavior checks.

## Acceptance limits and rollback

- This is source/contract acceptance, not live acceptance.
- Fresh PR CI must succeed before merge; compile guards remain required.
- No deployment or restart is necessary for this test/documentation-only patch.
- Revert this PR's test/workflow/documentation changes to roll back; do not
  roll back the runtime product contracts to match obsolete tests.
- The full Video goal remains incomplete: genuine Telegram ingress, missing
  lane/tier output receipts, paid readiness gates, `video_long`, and generative
  V2V are tracked separately in #1155/#1460.

```text
RUNTIME_SOURCE_CHANGES=0
REAL_PROVIDER_CALLS=0
PRODUCTION_JOBS_CREATED=0
PRODUCTION_DB_MUTATIONS=0
WALLET_MUTATIONS=0
ENV_MUTATIONS=0
DEPLOY=NO
LIVE_PASS=NOT_TESTED
```
