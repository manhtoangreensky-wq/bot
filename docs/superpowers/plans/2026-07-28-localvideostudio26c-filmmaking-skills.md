# Local Video Studio 26C Filmmaking Skills Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one original Vietnamese, planning-only filmmaking skill pack with 58 capability contracts, eight rights declarations, and static semantic verification.

**Architecture:** `SKILL.md` routes Codex to five deterministic JSON contracts under one isolated repository skill directory. A single pytest module loads Markdown/JSON only, validates schemas and semantics, and never imports production code. Existing TOAN AAS paths are metadata references only; no runtime loader, public UI, renderer, provider, worker, or wallet integration is created.

**Tech Stack:** Markdown, UTF-8 JSON, Python 3.12 standard library, pytest, Git/GitHub CLI.

---

## Locked file map

**Create:**

- `skills/video/local-video-filmmaking/SKILL.md` — concise trigger and planning workflow.
- `skills/video/local-video-filmmaking/editing_grammar.json` — 13 editing contracts.
- `skills/video/local-video-filmmaking/framing_composition.json` — 20 framing contracts.
- `skills/video/local-video-filmmaking/pacing_storytelling.json` — 11 pacing contracts.
- `skills/video/local-video-filmmaking/camera_movement.json` — 14 camera contracts.
- `skills/video/local-video-filmmaking/rights_requirements.json` — eight rights declarations and plan linkage.
- `tests/test_p1_localvideostudio26c_filmmaking_skills.py` — pure-static schema and semantic contract.

**Retain unchanged:**

- `docs/superpowers/specs/2026-07-28-localvideostudio26c-filmmaking-skills-design.md`

**Do not modify:**

- `bot.py`, `knowledge/video/**`, `services/profile_router.py`, Product Video,
  SubDub, UI/callback/state/back-stack, renderer, worker, provider, Railway,
  VPS, PayOS, wallet/Xu, database, webhook, billing, or Music/Suno files.

## Owner addendum applied over the design schema

Every capability has these exact required fields:

```python
REQUIRED_FIELDS = {
    "id", "display_name_vi", "summary_vi", "category", "purpose",
    "use_when", "avoid_when", "required_inputs", "shot_requirements",
    "audio_behavior", "timing_guidance", "continuity_rules",
    "aspect_ratio_notes", "failure_modes", "fallbacks",
    "validation_checks", "existing_capability_refs", "inventory_status",
    "source_dependency", "readiness", "rights_requirement_ids",
    "planning_only", "runtime_registered", "provider_executable", "public_ui",
}
```

Allowed readiness is exactly:

```python
READINESS = {
    "CONTRACT_ONLY",
    "LOCAL_PLANNING_READY",
    "REQUIRES_RUNTIME",
    "REQUIRES_PLANNED_SHOOT",
    "NOT_SUPPORTED",
}
```

All human-facing content is original Vietnamese. Identifiers, enums, relative
repository paths, and code symbols remain canonical machine metadata.

### Task 1: Write the static contract test and prove RED

**Files:**

- Create: `tests/test_p1_localvideostudio26c_filmmaking_skills.py`
- Verify absent: `skills/video/local-video-filmmaking/`

- [ ] **Step 1: Define exact IDs, fields, locks, and loader**

Use immutable tuples for the 13/20/11/14 capability IDs and eight rights IDs.
Load files only with `Path.read_text(encoding="utf-8")` and `json.loads`.
Define `_validate_capability(record)` that rejects missing fields, empty
Vietnamese text, invalid readiness, changed locks, malformed references, or
missing rights linkage.

```python
LOCKS = {
    "planning_only": True,
    "runtime_registered": False,
    "provider_executable": False,
    "public_ui": False,
}

def _validate_capability(record: dict[str, object]) -> None:
    assert REQUIRED_FIELDS <= set(record)
    assert record["readiness"] in READINESS
    for key, expected in LOCKS.items():
        assert record[key] is expected
    assert tuple(record["rights_requirement_ids"]) == RIGHTS_IDS
```

- [ ] **Step 2: Add exact count, uniqueness, rights, format, and mutation tests**

The tests must prove:

- exact group ID tuples and counts 13/20/11/14;
- 58 globally unique capability IDs;
- eight rights IDs exactly once and linked by the planning contract;
- deep-copied mutation fails for a missing field, changed lock, unknown
  readiness, and empty Vietnamese value;
- JSON is UTF-8 without BOM and equals `json.dumps(payload,
  ensure_ascii=False, indent=2) + "\n"`;
- the test AST imports standard-library modules only and no production module;
- repository references are relative, tracked paths with `metadata_only`
  relationship and a string-list `symbols` declaration;
- no credential, provider-model, task-ID, private absolute path, callback,
  state, back-stack, or runtime-registration material is present.

- [ ] **Step 3: Add semantic assertions**

Use structured `audio_behavior` booleans to prove J-cut and L-cut are opposite:

```python
assert j_cut["audio_behavior"]["starts_before_picture_cut"] is True
assert j_cut["audio_behavior"]["continues_after_picture_cut"] is False
assert l_cut["audio_behavior"]["starts_before_picture_cut"] is False
assert l_cut["audio_behavior"]["continues_after_picture_cut"] is True
```

Also assert:

- `screen_direction.continuity_rules` names `180_degree_rule`;
- `platform_reframing` contains a non-universal crop warning;
- `rule_of_thirds` explicitly says it is guidance, not mandatory;
- true camera-move IDs use `REQUIRES_PLANNED_SHOOT` and
  `PLANNED_SHOOT_REQUIRED`;
- `rack_focus_simulation` says simulation and denies physical optical focus;
- references remain metadata only.

- [ ] **Step 4: Run focused test and verify RED**

Run:

```powershell
python -m pytest -q tests/test_p1_localvideostudio26c_filmmaking_skills.py
```

Expected: FAIL because the six approved skill files are absent. A collection
error, production import, or unrelated failure is not an acceptable RED.

### Task 2: Record the skill baseline pressure scenario

**Files:** None.

- [ ] **Step 1: Ask a context-limited subagent for a filmmaking plan without the skill**

Use a request combining J-cut/L-cut semantics, a rack-focus request from fixed
footage, vertical reframing, and unknown music/person rights. Do not disclose
the intended answer. Record whether the response omits rights declarations,
confuses J/L boundaries, or overclaims arbitrary-footage execution.

- [ ] **Step 2: Convert observed gaps into existing contract assertions**

Only strengthen the focused test when the baseline exposes a requirement not
already covered. Do not create the skill before RED is confirmed.

### Task 3: Scaffold and write concise `SKILL.md`

**Files:**

- Create: `skills/video/local-video-filmmaking/SKILL.md`

- [ ] **Step 1: Initialize the skill after RED**

Run the system `skill-creator` initializer for `local-video-filmmaking` under
`skills/video/`. Retain only the owner-approved `SKILL.md`; remove generated
optional metadata from the pending diff with `apply_patch` so the final skill
directory contains exactly six approved files.

- [ ] **Step 2: Replace the template with the original Vietnamese skill**

Use frontmatter containing only:

```yaml
---
name: local-video-filmmaking
description: Use when Codex must plan Vietnamese video editing grammar, framing, pacing, camera movement, or rights-aware filmmaking decisions from supplied footage and production constraints.
---
```

The body covers purpose, triggers, exclusions, required inputs, workflow,
stopping conditions, rights gate, no-fake-success, output contract, and the
distinction between `CONTRACT_ONLY`, local preview, and production readiness.
Link relatively to the five JSON files and to
`../../../docs/superpowers/specs/2026-07-28-localvideostudio26c-filmmaking-skills-design.md`.
Do not duplicate all JSON records.

### Task 4: Implement editing and rights contracts

**Files:**

- Create: `skills/video/local-video-filmmaking/editing_grammar.json`
- Create: `skills/video/local-video-filmmaking/rights_requirements.json`

- [ ] **Step 1: Write the 13 editing records in approved order**

Use exact IDs from the design spec. Every record uses the common field order
from the owner addendum, all Vietnamese human-facing content, all eight rights
links, and immutable locks. Preserve existing inventory classifications and
metadata-only references from the spec. Editing records include structured
picture/audio boundary booleans, frame-aware timing guidance, observable
failure modes, safe fallbacks, and validation checks.

- [ ] **Step 2: Write the eight rights declarations**

The root planning contract lists all eight IDs and the action
`KEEP_PLANNING_ONLY_AND_BLOCK_EXECUTION` for unknown/restricted rights. Each
declaration is Vietnamese, required, evidence-aware, and contains no legal
success claim. Music/Suno stays locked.

### Task 5: Implement framing, pacing, and camera contracts

**Files:**

- Create: `skills/video/local-video-filmmaking/framing_composition.json`
- Create: `skills/video/local-video-filmmaking/pacing_storytelling.json`
- Create: `skills/video/local-video-filmmaking/camera_movement.json`

- [ ] **Step 1: Write 20 framing records**

Keep rule of thirds optional, link screen direction to the 180-degree rule,
separate safe-area checks from universally safe crop claims, and distinguish
geometric reframing from subject tracking or generated background expansion.

- [ ] **Step 2: Write 11 pacing records**

Keep the first-three-seconds hook non-guaranteed, make pacing content-aware,
require motivated B-roll, preserve setup/payoff and continuity, and forbid
invented CTA claims.

- [ ] **Step 3: Write 14 camera records**

Mark true moves as planned-shoot requirements. State crop, resolution, depth,
masking, motion-blur, and optical limits where applicable. Rack-focus
simulation must never claim a physical optical focus pull.

### Task 6: Verify GREEN and refine only contract defects

**Files:**

- Modify only when required: the six skill files and focused test.

- [ ] **Step 1: Run focused tests**

```powershell
python -m pytest -q tests/test_p1_localvideostudio26c_filmmaking_skills.py
```

Expected: PASS with zero failures and no production imports.

- [ ] **Step 2: Validate the skill folder**

Run the system `skill-creator` `quick_validate.py` against
`skills/video/local-video-filmmaking`. If it requires optional agent metadata,
report that mismatch rather than adding an unapproved file.

- [ ] **Step 3: Forward-test the completed skill**

Give a fresh context-limited subagent the same realistic planning request and
the skill path. Verify the result declares all rights, distinguishes J/L cuts,
stops on unavailable optical focus, and does not claim runtime/public success.

### Task 7: Run bounded common verification

**Files:** None unless a genuine 26C contract defect is found.

- [ ] **Step 1: Compile only the changed Python test**

```powershell
python -m py_compile tests/test_p1_localvideostudio26c_filmmaking_skills.py
```

- [ ] **Step 2: Run relevant static knowledge and pure planning tests**

Run the existing six-store knowledge validation test and selected storyboard,
continuity, or transition tests only after confirming they do not import
`bot.py` indefinitely. If a relevant suite times out, run the identical command
on clean `origin/main` and report branch/main outcomes honestly.

- [ ] **Step 3: Run repository hygiene**

Run `git diff --check`, deterministic JSON comparison, relative-link checks,
placeholder/secret/private-path scan, exact changed-file scope check, and
tracked-worktree status. Do not use `.pytest_cache/lastfailed`.

### Task 8: Review, commit, push, and open the one PR

**Files:** All approved 26C files above; no locked file.

- [ ] **Step 1: Review the complete diff against owner requirements**

Confirm exact totals, locks, rights linkage, readiness enum, Vietnamese
completeness, clean-room wording, and zero production wiring. Confirm the
design spec commit remains in history.

- [ ] **Step 2: Create one logical implementation commit**

```powershell
git add docs/superpowers/plans/2026-07-28-localvideostudio26c-filmmaking-skills.md skills/video/local-video-filmmaking tests/test_p1_localvideostudio26c_filmmaking_skills.py
git commit -m "feat: add Vietnamese filmmaking skill contracts"
```

- [ ] **Step 3: Push and open one PR without merging**

Push the current branch and create a PR titled exactly:

`P1.LOCALVIDEOSTUDIO26C: add original Vietnamese filmmaking skill contracts`

The PR targets `main`, contains both spec and implementation commits, and is
left open. Do not deploy and do not begin TASK 26D.
