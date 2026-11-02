# Product Video S03: Tail18 fixture parity

Đang đọc và áp dụng skill owner-governed-codex cho task này.

Base: `054b08bee78bca45506645a39342b87495011d88`. Separate S03 scope from the approved plan. This changes tests, not the working shared Tail or Local Edit runtime.

## Narrow changes

File: `tests/test_p0_video_tailflow15_order_tier200_status_idea_parity.py`.

- Execute actual keyboard/invoice functions instead of extracted functions with missing/stubbed dependencies. Callback extraction handles real InlineKeyboardButton objects without eagerly evaluating a tuple fallback.
- Replace old Logo/Summary-first expectations with Add-on -> Review -> Quality. Completing Add-on does not implicitly approve Review. Keep prompt, revision, scene content and product identity across transitions.
- Verify actual Add-on/Review callbacks; the library remains an input to AI Real, not a standalone product.
- Legacy Video Edit owner uses the actual `video_editengine1.PRODUCT_TYPE`, not an invented fixture constant. Legacy incomplete Tail states migrate to Add-on, while a current-version state explicitly returning to Review preserves that return route.
- Tier200 is valid for one/two-scene AI Real and not Self-shot. Unknown9999 must not replace a valid package; do not falsely reject a currently valid tier200.
- Actual invoice breakdown: tier200 one scene259 Xu; tier300 two scenes442 subtotal,44 discount,398 total. Historical saved invoice migration retains its old snapshot rather than repricing it.
- Current manual Storyboard route uses `video_manual_lane_open_shared_tail` with `storyboard2_assets_done` origin; do not require an obsolete direct Logo call. Current Script/UIFlow/Self-shot bridges remain Add-on-first.
- Status checks execute current navigation keyboard and status-step renderer: missing output cannot show delivered; a valid output without delivery waits; complete artifact+delivery marks all steps complete. Current request/task labels and no-false-completion copy remain present.

## Evidence

- Original expanded audit: eight Tail15 failures, including missing fixture dependencies and obsolete flow/catalog/copy expectations.
- Revised Tail15 + Tail18 + manual-entry comparators with provider-free plugin: **37 passed in8.20s**, exit0, external socket attempts0.
- XML: `audit/safe-merge-20261102/s03-tail-full-comparators.xml`.
- During fixture correction, two intermediate failures identified the actual Video Edit alias and Tail18 migration semantics; one remaining fixture failure required a current-version state for the Review return. Neither justified a runtime change.

Verification inside isolated test environment:

```text
python -m pytest -q --noconftest -p tests.pv_provider_free_guard tests/test_p0_video_tailflow15_order_tier200_status_idea_parity.py tests/test_p0_video_tailflow18_locked_order.py tests/test_p0_product_video_manual_tail_matrix.py
```

Tester case: exercise actual Add-on/Review/branding/status keyboard functions offline, preserve the saved content/version, confirm product-specific valid/invalid tier and current invoice/default pricing. This does not prove real Telegram clicks, provider output, add-on presence in final media or live delivery.

## Protection and rollback

No edits to bot, services/providers/worker/config, ENV, wallet or locked Multi/SubDub. Runtime diff0. Revert only this test/CI/docs PR if needed; no production restart/deploy is required.

S04 wider regression qualification, S05 receipt reconciliation and S06-S10 live readiness/acceptance remain incomplete. Keep #1155/#1460 open and retain separate source-tested, deployed and live-accepted checkpoints.

```text
TASK=PRODUCT_VIDEO_S03_TAIL18_FIXTURE_PARITY
TESTS=37_PASS_WITH_TAIL18_AND_MANUAL_ENTRY_COMPARATORS
BRANCH_FAILURES=0_IN_DECLARED_S03_SCOPE
PROVIDER_CALLS=0
WALLET_MUTATIONS=0
ENV_MUTATIONS=0
DEPLOY=NO
LIVE_PASS=NOT_TESTED
```
