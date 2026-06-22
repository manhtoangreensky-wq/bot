# TOAN AAS Flow Freeze Rules

Marker: `FREEZE_UI_FLOW_RULES_LOCKED_2026_06_23`

## Scope

UI/flow is frozen for the current public release branch. This document is a regression anchor for tests and future hotfix reviews.

## Rules

1. UI/flow frozen

   - Do not change public menu order, button labels, callback order, invoice order, tier order, or price display unless the owner explicitly asks for that exact change.
   - Do not change image or video public flow while fixing engine readiness, docs, tests, or admin-only observability.

2. Back route rule

   - A back button must return to the immediate previous public decision point.
   - Video invoice/export back routes must return to the video finalization/tier/scene flow, not to a stale prompt or unrelated menu.
   - Image logo/watermark back routes must return to the matching prompt, logo, ratio, or tier step without skipping required choices.

3. Public copy rule

   - Public guard copy must be clean, user-safe, and non-technical.
   - Public maintenance copy must say that the system is under maintenance/upgrading, that TOAN AAS has not processed the request, and that no Xu was charged.
   - Public copy must not expose internal provider names, task/job identifiers, API terms, tokens, keys, or debug state.

4. No interface changes without explicit instruction

   - Admin-only readiness/status commands may be added or standardized without changing public UI/flow.
   - Provider readiness, roadmap docs, and regression tests must not alter public menu, button, price, or invoice behavior.
   - Any future UI/flow change needs a direct owner instruction and a dedicated regression test update in the same commit.
