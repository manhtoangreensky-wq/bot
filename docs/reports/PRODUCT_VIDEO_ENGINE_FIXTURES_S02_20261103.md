# Product Video S02: engine fixture contract parity

Đang đọc và áp dụng skill owner-governed-codex cho task này.

Base: `054b08bee78bca45506645a39342b87495011d88`. This is the separate S02 scope from the approved plan; S01 is PR #1462.

## Changes

Only `tests/test_p0_video_real_engine_output_matrix.py` changes executable assertions:

- Both Self-shot expected routes now match controlled-keyframe I2V; their separate executor identities are preserved.
- Storyboard positive Key4U fixture uses accepted `kling-v3` with the I2V endpoint. The old unproved model/generic endpoint remains an explicit rejection assertion, not a silent replacement in runtime.
- Confirm kickoff is tested for both approved Storyboard bindings: tier400/ShopAIKey/veo3.1-fast and tier800/Key4U/kling-v3. Both require8s per scene, two scene tasks and16s total. Expected quote fixtures use668 and3086 Xu, respectively; no production price or wallet mutation.
- Worker fixture checks only resolver calls made for the current product. Storyboard's pinned model path must not call the generic resolver; the actual payload must retain its provider/model/capability. Other products require exactly one matching current resolver call.
- Worker fixtures now use supported tiers and retain Script minimum5 scenes.

## Evidence

- Earlier five-suite audit measured four current engine failures (five on the unchanged original fixture version). This PR changes fixtures, not production behavior.
- Engine matrix: **32 passed in3.40s**, exit0; no external socket attempts.
- Engine matrix + native Self-shot I2V + Storyboard dual-tier comparators, with `tests.pv_provider_free_guard`: **82 passed,1 warning in15.94s**, exit0, external socket attempts0.
- Warning is the existing `python_multipart` import deprecation in the unchanged Storyboard test, not a new runtime failure.
- XML: `audit/safe-merge-20261102/s02-engine-matrix.xml`, `s02-engine-comparators.xml`.

Verify under isolated test environment:

```text
python -m pytest -q --noconftest -p tests.pv_provider_free_guard tests/test_p0_video_real_engine_output_matrix.py tests/test_p0_product_video_selfshot_native_i2v_r13.py tests/test_p0_storyboard_dual_tier_routing.py
```

Tester acceptance: exact Self-shot route/capability/executor identity, Storyboard two-tier positive and unproved-model negative, actual worker payload checked per product rather than stale captured calls. No provider request or real delivery is involved.

## Limits and rollback

No runtime, provider, config, worker, wallet, ENV, deployed checkout or locked SubDub changes. Tail15 draft remains separate. Local/CI evidence is not MP4/Telegram live acceptance. #1155/#1460 remain open.

Revert only this test/CI/documentation PR if required. Keep runtime checkpoint and live acceptance checkpoint separate; no deploy/restart is needed for fixture corrections. Exact-head CI, PR and merge evidence are recorded after terminal results.

```text
TASK=PRODUCT_VIDEO_S02_ENGINE_FIXTURE_PARITY
TESTS=32_PASS_ENGINE;82_PASS_WITH_NATIVE_I2V_AND_STORYBOARD_COMPARATORS
BRANCH_FAILURES=0_IN_DECLARED_S02_SCOPE
PROVIDER_CALLS=0
WALLET_MUTATIONS=0
ENV_MUTATIONS=0
DEPLOY=NO
LIVE_PASS=NOT_TESTED
```
