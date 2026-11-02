# Product Video: explicit identity versus generic scene-plan inference

Đang đọc và áp dụng skill owner-governed-codex cho task này.

## Owner-approved scope

Owner explicitly approved exactly two Storyboard classification conditions on 2026-11-03, with tests only/offline verification and no deployment or live calls:

- `bot.py::video_b14_invoice_for_session`.
- `bot.py::video_b14_prepare_project_for_invoice`.

No symbol rename, parameter/return-shape change, new engine/helper, price table, provider route, wallet, ENV or SubDub edit is included. Shared functions have broad consumers: pre-edit `git grep -n -E 'video_b14_invoice_for_session\(|video_b14_prepare_project_for_invoice\(' -- bot.py services tests` measured63 matching lines in20 tracked files. Eighteen matches are in bot.py; remaining uses are tests. This is not evidence that all possible dynamic callers are enumerated.

## Reproduction and root cause

In the provider-free PV10 chain, explicit `video_trend` passed invoice/project preparation with a generic `b14_storyboard_plan`. The saved asset pack unexpectedly became `storyboard_prompt` / `storyboard_scene_image_video_engine` / `image_to_video`; its invoice still named `video_trend`. Render subsequently stopped before provider submission with `storyboard_panel_image_missing_no_charge`.

Both classification conditions previously treated any nonempty `b14_storyboard_plan` as Storyboard authority even if the session already identified a different product. At tier800 the same condition also selected the Storyboard-specific1714 Xu unit instead of the existing generic2143 Xu unit. This is classification correction, not a price-policy change.

This proves the legacy B14 source path defect offline. It does not establish that a new production Telegram job encountered the same path; modern RouteEngine can take a different ingress path.

## Minimal correction

Keep explicit normalized Storyboard product IDs authoritative. Otherwise use legacy flow-kind/plan inference only when neither session nor draft supplies a nonempty product_id. An explicit non-Storyboard product cannot be overwritten by a stale Storyboard marker or a generic scene plan.

Both predicates change identically. No other body of either function is changed. Legacy Storyboard sessions without an explicit product keep their previous inference behavior.

## Acceptance tests

`tests/test_p0_product_video_explicit_product_storyboard_plan.py` uses real invoice/project functions and an isolated in-memory queue DB. Telegram session storage alone is replaced with fixture state; no confirm, job, outbox or provider action is performed.

- Explicit Trend and AI Prompt, with and without a conflicting flow-kind marker: preserve product/adapter and existing generic tier800 price2143.
- Explicit and legacy unlabelled Storyboard: preserve accepted tier8001714 unit/3086 two-scene total and Key4U/kling-v3 binding.
- Every project preparation leaves job/outbox counts0.
- Correct RED after fixture field-name repair:4 failed,3 passed in9.67s on unchanged runtime, all four show1714 instead of2143. No source fix was applied before this RED.
- GREEN/comparators on Python3.11: **58 passed,1 existing import-deprecation warning in21.40s**, exit0; external socket attempts0.
- Wider current catalog/engine/Tail/manual/native-I2V/Storyboard regression including new tests: **393 passed,1 existing warning in36.64s**, exit0; external socket attempts0. XML `runtime-identity-wide-regression-py311.xml`.
- `scripts/check_bot_source_compile.py` on Python3.11: compile(source) and AST PASS; `python -m py_compile bot.py local_worker.py`: exit0.
- Python3.12 patched-source runs did not reach terminal and were stopped, not counted as PASS. Python3.11 testing used a separate local dependency directory; no application requirements or production packages were changed.
- The original PV10 Trend chain no longer stops for missing Storyboard panels. Its next blocker is `weekly_provider_spend_policy_incomplete` in the outdated fixture; keep that gate intact. The entire PV10 suite is still incomplete, not relabeled GREEN.

## Comparators and delivery gates

Run new regression together with Storyboard dual-tier, actual Tail invoice/keyboard checks, native-I2V/engine contracts and the accepted catalog/manual-entry matrix under provider-free guards. Full source compile and exact-head CI are mandatory. Preserve existing Storyboard cross-tier/model rejection.

The wider PV10 suite also has historical mock/input/renderer assumptions and is not automatically GREEN after this fix. Record remaining failures individually; do not patch unrelated runtime paths or relabel mocked media as a real live product.

S01 source-test checkpoint is PR #1462 / `33dca4befea912facd0cd5bc6ee72e593172f675`, both PR CI41490636426 and post-merge CI41492734156 SUCCESS. S02/S03 have separate PRs #1463/#1464; neither runtime deployment nor live acceptance follows from those PRs.

This runtime patch is not authorized for deployment/restart/live under the narrow approval. Keep deployed runtime and live-accepted checkpoint unchanged. If it regresses, revert only these two condition changes and their regression PR, preserving unrelated accepted lanes.

```text
TASK=PRODUCT_VIDEO_EXPLICIT_PRODUCT_IDENTITY
SOURCE_SCOPE=BOT_TWO_STORYBOARD_PREDICATES_ONLY
RED=4_FAIL_3_PASS
GREEN=58_PASS_TARGETED_AND_393_PASS_WIDE_PYTHON311
PROVIDER_CALLS=0
PRODUCTION_JOBS_CREATED=0
WALLET_MUTATIONS=0
ENV_MUTATIONS=0
DEPLOY=NO
LIVE_PASS=NOT_TESTED
```
