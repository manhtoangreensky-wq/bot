# TOAN AAS Public Landing Teal–Sky Rebalance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `www.toanaas.vn` a balanced teal–sky public companion that leads visitors into Workspace without changing Bot, payment, webhook or lead authority.

**Architecture:** Keep the static single-file landing, locale selector and `/lead` contract. Consolidate the visual system in its inline token block, preserve information architecture, and change only presentation/copy that is reviewed in all three locales.

**Tech Stack:** Semantic HTML, CSS, vanilla JavaScript, pytest static contracts.

---

### Task 1: Add failing contracts for shared token and layout boundaries

**Files:**
- Create: `tests/test_public_landing_teal_sky_rebalance_contracts.py`
- Test: `tests/test_public_landing_teal_sky_contracts.py`

- [ ] **Step 1: Write a red semantic-token test**

```python
def test_landing_uses_contrast_safe_teal_sky_roles() -> None:
    for token in (
        "--teal-action: #0f766e;",
        "--teal-brand: #14b8a6;",
        "--sky-context: #0284c7;",
        "--canvas: #f4fbfc;",
        "--ink: #083344;",
    ):
        assert token in LANDING
```

- [ ] **Step 2: Write a red responsive geometry test**

```python
def test_header_and_hero_do_not_force_an_overwide_desktop_composition() -> None:
    assert "grid-template-columns: minmax(0, 1.08fr) minmax(0, .92fr);" in LANDING
    assert "minmax(0, 420px)" not in LANDING
    assert "overflow-x: clip;" in LANDING
```

- [ ] **Step 3: Run the red test**

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
python -m pytest -q --noconftest tests/test_public_landing_teal_sky_rebalance_contracts.py
```

Expected: failure only because the new semantic names and grid have not been
implemented.

### Task 2: Rebalance the public layout without changing authority

**Files:**
- Modify: `index.html`
- Modify: `tests/test_public_landing_teal_sky_rebalance_contracts.py`

- [ ] **Step 1: Define final roles once**

```css
:root {
  --teal-action: #0f766e;
  --teal-brand: #14b8a6;
  --sky-context: #0284c7;
  --canvas: #f4fbfc;
  --surface: #ffffff;
  --ink: #083344;
  --line: #d7ecef;
  --muted: #486b75;
}
```

- [ ] **Step 2: Normalize header and hero rails**

```css
.container { width: min(1240px, calc(100% - 48px)); margin-inline: auto; }
.hero-grid {
  grid-template-columns: minmax(0, 1.08fr) minmax(0, .92fr);
  gap: clamp(28px, 4vw, 56px);
}
```

At tablet widths collapse before a minimum column can clip. Do not add stock
photos, fake metrics, carousels, decorative hero pills or unverifiable claims.

- [ ] **Step 3: Preserve real routes and lead payload**

Do not change the Workspace URL, Telegram URL, `POST /lead` JSON body, form
method/native validation, canonical topic values, legal/download routes or
`landing-clean-clear-v2` source.

- [ ] **Step 4: Verify and commit**

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
python -m pytest -q --noconftest tests/test_public_landing_teal_sky_contracts.py tests/test_public_landing_teal_sky_rebalance_contracts.py
git add index.html tests/test_public_landing_teal_sky_contracts.py tests/test_public_landing_teal_sky_rebalance_contracts.py
git commit -m "feat: rebalance public teal sky landing"
```

### Task 3: Check localized clarity and responsive experience

**Files:**
- Modify: `docs/public/2026-07-27-teal-sky-rebalance-design.md`

- [ ] **Step 1: Assert every changed label remains three-localed**

```python
for key in ("hero.title", "hero.workspace", "workflow.title", "companion.title", "lead.submit"):
    assert LANDING.count(f'"{key}":') == 3
```

- [ ] **Step 2: Smoke test at 375px and desktop**

Verify menu toggle/Escape focus, Workspace and Telegram links, form native
validation and no horizontal overflow. Do not submit a lead or invoke
Telegram, PayOS or provider actions.

- [ ] **Step 3: Run final checks and commit the ledger**

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
python -m pytest -q --noconftest tests/test_public_landing_teal_sky_contracts.py tests/test_public_landing_teal_sky_rebalance_contracts.py
git diff --check
```

Record the before/after visual checks in the design document, request review,
then open a Landing-only PR.
