# Landing Companion Responsive Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve the approved teal–sky landing's three product roles as an equal, readable companion set at tablet and mobile widths.

**Architecture:** Adjust only the public landing's responsive companion CSS and its static contract. At the tablet boundary the group becomes a single, equal-width stack rather than a 2+1 layout; every card continues to use the existing three role descriptions and translations. The list area is pinned to the card baseline on desktop without hardcoding content height.

**Tech Stack:** Static HTML/CSS/vanilla JavaScript landing, pytest static contracts.

---

### Task 1: Define the failing layout contract

**Files:**
- Modify: `tests/test_public_landing_teal_sky_rebalance_contracts.py`
- Verify: `index.html`

- [ ] **Step 1: Add a tablet contract**

```python
assert re.search(
    r"@media \(max-width: 840px\) \{\s*"
    r"\.companion-grid--three \{ grid-template-columns: minmax\(0, 1fr\); \}",
    LANDING,
)
assert ".companion-card--website { grid-column: 1 / -1; min-height: 0; }" not in LANDING
```

- [ ] **Step 2: Add an equal-card list baseline contract**

```python
assert ".companion-list { display: grid; gap: 10px; margin: auto 0 0; padding: 20px 0 0;" in LANDING
```

- [ ] **Step 3: Run the focused contract and verify RED**

Run: `python -m pytest -q tests/test_public_landing_teal_sky_rebalance_contracts.py`

Expected: it fails because the committed landing still uses a 2+1 tablet grid and non-pinned list margin.

### Task 2: Apply the minimal CSS correction

**Files:**
- Modify: `index.html`
- Test: `tests/test_public_landing_teal_sky_rebalance_contracts.py`

- [ ] **Step 1: Pin companion lists to a common card baseline**

Replace the companion list's top margin with `margin: auto 0 0` and add `padding: 20px 0 0`. Preserve the three existing list values, colours and locale bindings.

- [ ] **Step 2: Replace the 2+1 tablet grid with one column**

At `@media (max-width: 840px)`, make `.companion-grid--three` one column and remove the Website-only spanning/height exception. Retain the desktop three-column layout and the existing <=680px mobile rule.

- [ ] **Step 3: Run targeted tests and diff hygiene**

Run: `python -m pytest -q tests/test_public_landing_teal_sky_contracts.py tests/test_public_landing_teal_sky_rebalance_contracts.py` followed by `git diff --check`.

Expected: all tests pass and no Bot, PayOS, provider, payload, route or translation content change appears in the diff.

- [ ] **Step 4: Commit**

```bash
git add index.html tests/test_public_landing_teal_sky_rebalance_contracts.py docs/superpowers/plans/2026-07-27-landing-companion-responsive-polish.md
git commit -m "fix: align responsive landing companion cards"
```

### Task 3: Rendered quality gate

- [ ] **Step 1: Check visual responsive states**

Verify landing at 1440px, 768px and 390px. Confirm the product roles are three equal cards at desktop, a clear sequential stack at tablet/mobile, no content is horizontally clipped, and the actual Website/Workspace/Telegram routes still work.

## Self-review

- The landing remains a public entry surface; no Bot/runtime/PayOS/provider code is modified.
- All three locale tables and semantic role copy are left unchanged.
- Tablet no longer privileges Website visually over Workspace and Telegram.
