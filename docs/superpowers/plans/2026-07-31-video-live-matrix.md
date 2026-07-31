# Video Live Matrix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate the accepted ROUTEENGINE29 evidence into one machine-readable and one human-readable matrix without changing any Video UI or claiming production LIVE PASS without a deployment and Telegram artifact receipt.

**Architecture:** A versioned JSON document records immutable route/engine SHAs, accepted local fixture evidence, rollback flags, worker truth, production counters, and live blockers for every owned Video product. A Markdown report explains the same split between local MP4 proof and missing production evidence. A focused pytest contract validates the documents against the real default-OFF engine flags and rejects fake live fields.

**Tech Stack:** JSON, Markdown, Python pathlib/json, pytest, existing Video engine modules and shared route contract.

---

### Task 1: Define the fail-closed matrix contract

**Files:**
- Create: `tests/test_p0_videomenu29l_consolidated_live_matrix.py`
- Create: `docs/reports/P0_VIDEOMENU_ROUTEENGINE29L_LIVE_MATRIX.json`

- [x] Write focused tests that require exactly the six ROUTEENGINE29-owned products and explicitly release Video Edit to its separate owner.
- [x] Run the focused test before the JSON exists and record the expected missing-artifact RED.
- [x] Add the smallest JSON evidence document that satisfies the schema without inventing deployment, worker, provider, delivery, or live-smoke evidence.
- [x] Run focused tests GREEN.

### Task 2: Publish the human-readable truth report

**Files:**
- Create: `docs/reports/P0_VIDEOMENU_ROUTEENGINE29L_LIVE_MATRIX.md`
- Test: `tests/test_p0_videomenu29l_consolidated_live_matrix.py`

- [x] Describe route and engine lineage, supported one/multi-scene modes, prompt/flow preservation, offline MP4 evidence, rollback controls, and exact production blockers per product.
- [x] Keep live MP4 metrics, deployment IDs, Telegram jobs, delivery receipts, and reports unset until an authorized live run supplies them.
- [x] State `ALL VIDEO MENU ROUTES LIVE PASS=NO` while current worker/runtime and production delivery evidence are unverified.
- [x] State `VIDEO EDIT ROUTE/ENGINE RELEASED=YES` and make no Video Edit implementation claim.

### Task 3: Regression and ship gate

**Files:**
- No production, UI, callback, Back, status, worker, DB, provider, Video Edit, or SubDub files may change.

- [x] Run focused 29L, accepted 29B-29L regressions, exact locked 144 UI tests on branch and clean main, JSON parse, `git diff --check`, secret/private-path scan, and forbidden-scope scan.
- [ ] Push one commit, open the 29L PR, inspect exact scope and CI, then merge with a merge commit.

**Out of scope:** Railway/VPS deployment, Telegram action, real or paid provider calls, public flag enablement, worker restart, wallet mutation, UI/UX, menu/callback/back-stack/status changes, Video Edit ownership, and any claim of production LIVE PASS.
