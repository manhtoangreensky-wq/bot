# Product Video: S01 catalog/callback contract reconciliation

Đang đọc và áp dụng skill owner-governed-codex cho task này.

## Scope and checkpoint

- Owner approved the staged plan on 2026-11-03 and reiterated narrow scope.
- Base: `054b08bee78bca45506645a39342b87495011d88` (PR #1461).
- This first PR changes only three catalog test modules, their CI step and evidence/docs.
- Two previously dirty test modules (engine matrix and Tail15) remain outside this commit. S02/S03 will review them separately.
- No changes to bot, runtime services, providers, worker, configuration, wallet, ENV or locked Multi/Smart SubDub.

## Confirmed corrections

| Historical test expectation | Accepted source contract | Coverage retained |
|---|---|---|
| Storyboard has ten generic tiers | Exactly 400/800; tier800 8s /1714 Xu | Positive tiers and explicit rejection of the other eight |
| Both Self-shot products use direct V2V | Source video -> controlled keyframes -> I2V, tiers500/600/700/800 | Separate source-video/route/modality assertions for each product; reject six unsupported tiers |
| Film and Local Edit are execution-disabled | Film enabled after #1455; Local Edit operational/protected | Two separately parametrized enabled cases; video_long remains explicitly blocked |
| Tier400 price80 Xu and old menu order | Existing approved price-map:371 Xu and ascending current price order | Exact default-price/catalog/quote assertions; production prices unchanged |
| Local Edit exact snapshot lacks fallback_capabilities | Current empty tuple is part of the contract | Exact protected-route snapshot and100 capability/ratio/count combinations retained |

`video_idea` remains a legacy compatibility-adapter test, not a standalone live product or authorization to create library jobs.

## Callback fixture defect

The three callbacks completed on a fresh diagnostic run (3 passed /19 deselected,12.71s); the previous hang was not reproduced. Do not claim a production hang was fixed.

Two negative tests nevertheless swallowed arbitrary exceptions and could pass without proving the intended rejection. The revised fixture:

- executes the decorated production callback;
- uses the emitted keyboard callback for the supported tier;
- isolates only runtime preflight, storage/session/invoice and Telegram rendering boundaries;
- rejects unexpected DB access, snapshots every save and imposes a5s async wait bound;
- inspects the exception caught by the production guard, requiring exactly `ValueError("quality_tier_not_supported")` for invalid tiers;
- verifies a supported tier really persists package500, two scenes and the fixture invoice1608 Xu, then renders invoice exactly once;
- keeps invalid tiers unset and renders quality recovery. Unrelated errors can no longer satisfy the negative assertions.

This checks callback selection/persistence, not provider readiness, production pricing or real Telegram delivery. Invoice generation is an explicit isolated fixture boundary.

## Evidence

- Baseline three-suite selected run:18 failed,101 passed,3 callback fixtures deselected; XML `audit/safe-merge-20261102/catalog-adapters-baseline.xml`.
- Full revised three-suite inventory:122 cases, same count as the original inventory. Two obsolete Self-shot V2V cases are replaced by two I2V cases; two obsolete disabled Film/Local cases are replaced by two enabled cases. No deselection is required.
- Full three-suite plus accepted148-case regression: **270 passed in14.67s**, exit0, external socket attempts0; XML `s01-catalog-and-regression.xml`.
- Compilation of the three changed test modules: exit0.
- CI-plugin-equivalent full selection: **122 passed in9.64s**, exit0, external socket attempts0; XML `s01-ci-plugin-equivalent.xml`.
- Full local bot source compile started but has not produced terminal output; it is not counted as PASS. Unchanged full source compilation remains a required exact-head CI gate.
- CI now runs the three full suites with `tests.pv_provider_free_guard`, an offline Telegram placeholder and isolated runner-temp storage. No provider secrets or production paths are passed.
- Exact-head CI/merge receipts will be added after terminal verification. Local tests do not prove CI or live.

Reproduction from the audit workspace root:

```powershell
& 'C:\Users\toann\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' audit\safe-merge-20261102\run_offline_checks.py work\pv-catalog-tail-contract-tests -q --noconftest -p tests.pv_provider_free_guard tests/test_p0_video_uifreeze1_menu_pricing_public_freeze.py tests/test_p0_product_video_pv04_capability_quality_catalog_truth.py tests/test_p0_product_video_pv08_product_adapters_product_specific_quality.py
```

CI-equivalent pytest selection, from the repo root with the isolated test environment declared in CI:

```text
python -m pytest -q --noconftest -p tests.pv_provider_free_guard tests/test_p0_video_uifreeze1_menu_pricing_public_freeze.py tests/test_p0_product_video_pv04_capability_quality_catalog_truth.py tests/test_p0_product_video_pv08_product_adapters_product_specific_quality.py
```

## Remaining work and rollback

- S02 engine fixtures, S03 old Tail15 fixtures, S04 wider provider-free qualification and S05 current live receipt matrix remain incomplete.
- No real MP4 generation/delivery claim is made. #1155/#1460 remain open.
- Rollback scope for this PR is test/CI/docs only. Runtime checkpoint `804e23dad74dce0dfcaf3f472f1d2231a86931ba` is unchanged; do not deploy/restart for this PR.
- Record source-tested, deployed and live-accepted checkpoints separately. Newest PR number is not automatically the runtime rollback anchor.

```text
TASK=PRODUCT_VIDEO_S01_CATALOG_CALLBACK_CONTRACTS
BASE_SHA=054b08bee78bca45506645a39342b87495011d88
TESTS=270_PASS_FULL_SELECTION_NO_DESELECTION
BASELINE_FAILURES=18_IN_SELECTED_CATALOG_SCOPE
BRANCH_FAILURES=0_IN_FULL_CATALOG_PLUS_148_REGRESSION
PROTECTED_COMPARATORS=RUNTIME_DIFF_0
PROVIDER_CALLS=0
WALLET_MUTATIONS=0
ENV_MUTATIONS=0
PRODUCTION_JOBS_CREATED=0
DEPLOY=NO
LIVE_PASS=NOT_TESTED
BLOCKERS=REMAINING_S02_TO_S10_EVIDENCE
```
