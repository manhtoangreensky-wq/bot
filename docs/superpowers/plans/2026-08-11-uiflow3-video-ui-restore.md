# UIFLOW3 Video UI Restore Implementation Plan

Date: 2026-08-11
Status: Owner approved for build and merge; no deploy/live

1. Update the side-effect-free video pricing catalog with verified provider evidence, public metadata, fallback ordering, and Owner rounding.
2. Replace the four-item Video AI Real quality map with the nine canonical public tiers and remove provider/model names from public copy.
3. Restore the one-row five-number suggestion interaction, automatic single-choice advance, exact Back/Menu routing, complete prompt display, and nine-position branding summary.
4. Remove trial wording/restrictions from the lowest normal video package and make no-job status explicitly terminal FAIL.
5. Remove implicit Video AI Real ownership defaults in the shared product flow; missing/stale ownership returns Menu Video.
6. Review changed callbacks and protected-file boundaries statically.
7. Run only the focused owner-restore selector, Python compile for changed modules, and `git diff --check`; do not run broad suites.
8. Commit, push, create and merge the UI PR, then freeze UI. Do not deploy.
9. After Video UI is complete, research the image model/tool catalog and image prices using the same evidence and pricing rules.
10. Start a separate Route Engine/VPS plan only after UI merge is terminal.
