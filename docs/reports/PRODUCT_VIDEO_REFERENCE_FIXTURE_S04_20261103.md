# S04: reference lifecycle fixtures under the current paid-create boundary

Đang đọc và áp dụng skill owner-governed-codex cho task này.

## Scope and source checkpoint

Base: `44b5fc87a45b496ca7a2f75c2b0243eaed6016d0` (merged test/CI checkpoint #1463). Only the reference-wire test file, its guarded CI selection and this report change. No bot/service/provider/worker/config/spend-guard/wallet/ENV code changes.

S04 remains a wider incomplete qualification task, not a claim that the entire manifest or live goal is complete.

## Measured defect in the old fixture

The full provider-free manifest stopped at `test_active_task_reference_preservation_and_poll_only_recovery`: expected running, received blocked_no_charge. The fixture attempted an initial provider create with a dummy API token and no current durable spend/confirm authority. A patched HTTP response cannot authorize a paid create. The production guard correctly rejected that attempt before HTTP.

The correction does not mock or disable the spend guard. It removes the unsupported implicit paid create from lifecycle setup and tests recovery of a previously accepted task instead.

## Contract changes in tests only

| Old expectation | Current acceptance assertion |
|---|---|
| Fake submit HTTP permits initial create | Materialize a real local reference using the production serializer, then supply an existing task in fixture metadata |
| Pending task retains image | Two poll-only GET calls retain the same single reference; recovered request keeps the persisted keyframe and must report provider_poll_called |
| Terminal success deletes references | One GET returns success; materialization is an explicit fixture boundary; production router removes image and metadata |
| Terminal failure deletes references | One GET returns failure; production router removes the pre-existing reference |
| A fake timeout creates an ambiguous paid submit without authority | New create is blocked before HTTP with charged_xu0; pre-existing reference is not discarded |
| Unresolved reference may remain forever | Actual storage service preserves it before expiry and removes it after expiry |

All existing model-family, HTTPS/private-address and Self-shot wire assertions remain. The new unauthorized-create negative and bounded-TTL case replace an invalid old claim that a caller lacking spend authority can reach an ambiguous transport outcome. These tests do **not** prove an authorized live ambiguous-submit integration path; that is an explicit evidence limit, not a renamed PASS.

The setup does not insert a production job/task, mint production confirmation or write a production reference. Everything uses pytest temp paths and dummy task IDs, with the provider-free plugin blocking outbound transport. HTTP in these fixtures is mocked GET-only; no real provider polling or create occurs.

## Verification and tester case

- Baseline failure: blocked initial create in the old wire fixture, after399 prior manifest tests passed. The manifest run stopped; no full-manifest success is claimed.
- Three corrected active/success/failure lifecycle tests:3 passed,8 deselected in8.16s.
- Full wire suite plus reference transport/security and native Self-shot I2V comparators:46 passed,1 existing Starlette import warning in12.30s, external socket attempts0.
- Final reviewed assertions require exactly one GET for each terminal case, preventing a vacuous all-GET assertion on zero requests. Rerun:46 passed,1 existing warning in10.86s, external socket attempts0.
- Exact new CI selection (full wire plus the existing catalog/engine step):166 passed in15.07s, exit0, external socket attempts0. XML `s04-reference-exact-ci-selection.xml`.

Verify with isolated local storage and test credentials, never production ENV:

```text
python -m pytest -q --noconftest -p tests.pv_provider_free_guard tests/test_p0_product_video_shopaikey_veo_i2v_reference_wire_r13_1.py tests/test_p0_product_video_provider_reference_transport_r13_1.py tests/test_p0_product_video_selfshot_native_i2v_r13.py
```

Tester case `PV-REFERENCE-S04-01`: pending/recovered tasks keep one reference, terminal cases remove it with exactly one GET, unauthorized create never reaches HTTP, unresolved file survives only to TTL. Missing sidecar/invalid HTTPS/model-family checks remain fail-closed. This is source/fixture acceptance only, not actual Telegram output/delivery.

## Rollback and remaining work

Rollback is limited to this test/CI/docs patch. No production restart/deploy is needed. Keep source-tested, deployed and live-accepted anchors separate. #1155/#1460 stay open.

PV10 deterministic E2E still has obsolete execution-lock and paid-create fixture assumptions; the broad manifest has not completed. No spend policy/reset/cap or production data is changed to make it pass. The separately approved two-predicate runtime patch stays in draft PR #1465.

```text
TASK=PRODUCT_VIDEO_S04_REFERENCE_LIFECYCLE_FIXTURES
PROTECTED_COMPARATORS=RUNTIME_DIFF_0;REFERENCE_TRANSPORT_SECURITY;NATIVE_SELFSHOT_I2V
PROVIDER_CALLS=0
PRODUCTION_JOBS_CREATED=0
WALLET_MUTATIONS=0
ENV_MUTATIONS=0
DEPLOY=NO
LIVE_PASS=NOT_TESTED
```
