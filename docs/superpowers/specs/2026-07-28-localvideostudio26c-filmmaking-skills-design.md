# Local Video Studio 26C — Original Filmmaking Skill Pack Design

## Decision and phase boundary

TASK 26C uses one repository-owned, clean-room skill pack. It is a planning
reference for Codex and is not a product feature, runtime registry, production
loader, renderer extension, provider route, or public user interface.

This specification is PHASE 26C-1. The only repository artifact produced in
this phase is this design document. The skill, JSON contracts, and focused test
belong to PHASE 26C-2 and require owner approval of this committed specification
before they are created.

The implementation branch is:

`feat/p1-localvideostudio26c-filmmaking-skills`

The read-only inventory baseline is `origin/main` at
`b66e7919abfcdb95c0475b7be5df28f29f3c1dcf`, fetched on 2026-07-28. Its
Product Video summary/back-stack change is upstream-owned and locked. PHASE
26C-1 and PHASE 26C-2 stay on this same branch and use one shared TASK 26C PR;
no second branch or PR is opened for the implementation phase.

Its approved implementation tree is exactly:

```text
skills/video/local-video-filmmaking/
├── SKILL.md
├── editing_grammar.json
├── framing_composition.json
├── pacing_storytelling.json
├── camera_movement.json
└── rights_requirements.json

tests/
└── test_p1_localvideostudio26c_filmmaking_skills.py
```

No file under `knowledge/video/` is added or changed. No Python runtime
registry, package initializer, service import, production loader registration,
Codex-home installation, provider adapter, callback, button, state, or
back-stack integration is part of TASK 26C.

## Source and isolation rules

The pack is original TOAN AAS material derived from:

1. the exact owner-supplied TASK 26C capability IDs and acceptance rules;
2. read-only inventory of the current TOAN AAS repository; and
3. general filmmaking knowledge expressed in new wording and new schemas.

OpenMontage source, OpenMontage skill text, third-party tutorial transcripts,
and third-party proprietary examples must not be copied or paraphrased closely.
Existing TOAN AAS files are referenced by path and symbol only; their prose or
implementation is not duplicated. The JSON files contain no executable code,
URLs, credentials, provider selection, shell commands, or production hooks.

Every capability record must contain these immutable guards:

```json
{
  "planning_only": true,
  "runtime_registered": false,
  "provider_executable": false,
  "public_ui": false
}
```

The guards are normative. A record with any different value is invalid.

## Architecture and data flow

`SKILL.md` is the sole human/agent entrypoint. It tells Codex which JSON file to
read for an editing, framing, pacing, camera, or rights question. It must keep
the body concise and load only the relevant JSON file for the current planning
request.

The four capability JSON files are static taxonomies. Each record explains the
creative intent, source prerequisites, non-use cases, continuity risks,
realization limits, fallback, and validation. Existing TOAN AAS mappings are
evidence links, not imports and not claims that the mapped runtime implements
the full filmmaking technique.

`rights_requirements.json` defines the eight declarations that every generated
plan must include. Rights metadata is a planning gate. Unknown, restricted, or
missing rights keep the output at planning-only status and must never be
interpreted as approval to render, publish, deliver, or spend.

The focused pytest contract reads Markdown and JSON directly with the standard
library. It does not import `bot`, `services.profile_router`, a renderer,
worker, provider, database module, or billing module.

```text
Owner request
    -> SKILL.md routing instruction
    -> one relevant capability JSON
    -> source/readiness validation
    -> rights declaration validation
    -> planning guidance only

No job, provider, wallet, output file, public menu, or delivery side effect
```

## Normative JSON schemas

### Capability-file envelope

Each of the four capability files has this exact top-level shape:

```json
{
  "schema_version": "1.0.0",
  "pack_id": "local-video-filmmaking",
  "group_id": "editing_grammar",
  "capability_count": 13,
  "capabilities": []
}
```

`group_id` and `capability_count` vary by file:

| File | `group_id` | Exact count |
| --- | --- | ---: |
| `editing_grammar.json` | `editing_grammar` | 13 |
| `framing_composition.json` | `framing_composition` | 20 |
| `pacing_storytelling.json` | `pacing_storytelling` | 11 |
| `camera_movement.json` | `camera_movement` | 14 |

Unknown top-level keys are rejected so the contracts remain deterministic.

### Common capability record

Every capability record requires all fields below:

```json
{
  "id": "standard_cut",
  "display_name_vi": "Cắt tiêu chuẩn",
  "display_name_en": "Standard cut",
  "purpose": "Original concise planning guidance.",
  "when_to_use": ["At least one concrete condition."],
  "when_not_to_use": ["At least one concrete condition."],
  "source_shot_requirements": ["At least one measurable or observable requirement."],
  "continuity_risks": ["At least one specific risk."],
  "known_failure_conditions": ["At least one condition that prevents a truthful result."],
  "fallback_capability_id": null,
  "validation_checklist": ["At least one observable validation."],
  "existing_capability_mapping": [],
  "inventory_status": "EXISTING_BUT_INCOMPLETE",
  "source_dependency": "COMPATIBLE_FOOTAGE_REQUIRED",
  "planning_only": true,
  "runtime_registered": false,
  "provider_executable": false,
  "public_ui": false
}
```

Rules:

- `id` uses lowercase snake case and must be one of the exact IDs in this spec.
- The 58 capability IDs are unique across the whole pack.
- Text and list fields are non-empty and must state observable conditions,
  not promotional claims.
- `fallback_capability_id` is either `null` or another exact ID in the pack.
- A fallback never bypasses a missing source or rights gate.
- `source_dependency` is exactly one of:
  `COMPATIBLE_FOOTAGE_REQUIRED`, `PLANNED_SHOOT_RECOMMENDED`,
  `PLANNED_SHOOT_REQUIRED`, or `SIMULATION_LIMITED`.
- `inventory_status` uses the master inventory vocabulary:
  `EXISTING_AND_VALID`, `EXISTING_BUT_INCOMPLETE`, `MISSING`, `DUPLICATE`,
  `PAID_DISABLED`, `GPU_BLOCKED`, `LICENSE_BLOCKED`, or `NOT_APPLICABLE`.
  TASK 26C currently uses only the first three values.

Each item in `existing_capability_mapping` has this shape:

```json
{
  "path": "services/video_scene_transition_planner.py",
  "symbols": ["SUPPORTED_TRANSITIONS"],
  "support_layer": "planner",
  "relationship": "reference_only",
  "notes": "The existing symbol overlaps semantically but is not changed or invoked."
}
```

`support_layer` is one of `knowledge`, `prompt`, `planner`, `capability_catalog`,
`local_edit`, or `policy`. `symbols` is non-empty for a referenced code symbol
and may be empty for a static JSON or Markdown reference. `relationship` is
always `reference_only` in TASK 26C.

### Editing-specific fields

All 13 editing records additionally require:

```json
{
  "audio_boundary_behavior": {
    "incoming_audio": "Exact behavior before or at the picture boundary.",
    "outgoing_audio": "Exact behavior at or after the picture boundary.",
    "sync_rule": "How dialogue, action, ambience, and picture sync are preserved.",
    "fallback": "Safe boundary behavior when clean audio separation is unavailable."
  },
  "timing_guidance": {
    "frame_accuracy_required": true,
    "recommended_range_seconds": {"min": null, "max": null},
    "decision_rule": "Content-driven timing rule; never a universal promise."
  }
}
```

`recommended_range_seconds` may use `null` for either bound when a numeric
range would be misleading. `decision_rule` is always required. J-cuts and
L-cuts must describe picture/audio offset direction explicitly. Cut on action
must identify the action phase used as the boundary. Montage and parallel
editing must validate temporal and narrative clarity rather than merely
concatenating clips.

### Framing/composition-specific fields

All 20 framing records additionally require:

```json
{
  "composition_rules": ["Observable placement or balance rule."],
  "platform_reframing_notes": ["How crop, fit, and safe area can alter the composition."],
  "axis_or_gaze_checks": ["Applicable eyeline, screen-direction, or axis check; NOT_APPLICABLE when justified."]
}
```

The 180-degree and 30-degree rules are planning checks, not automatic camera
repair. Platform reframing must distinguish geometrical crop/fit from subject
tracking or generative background expansion.

### Pacing/storytelling-specific fields

All 11 pacing records additionally require:

```json
{
  "story_function": "The beat or audience-understanding goal.",
  "timing_guidance": {
    "measurement": "seconds, frames, words, shots, or beats",
    "decision_rule": "Content- and platform-aware pacing rule."
  },
  "information_risks": ["Overload, repetition, ambiguity, or unsupported claim risk."],
  "beat_prerequisites": ["Required script, transcript, action, or audio cue."]
}
```

`hook_first_three_seconds` may target the first three seconds but must not claim
that every video or platform guarantees retention. CTA guidance must reserve a
readable end-card interval and must not invent pricing, claims, or brand assets.

### Camera/movement-specific fields

All 14 camera records additionally require:

```json
{
  "capture_method": "EITHER_WITH_LIMITS",
  "realization_limits": ["Specific limits of captured footage or digital simulation."],
  "motion_continuity_checks": ["Direction, speed, entry/exit, horizon, or subject-lock check."],
  "simulation_disclosure": "How a simulated move is named without presenting it as captured camera motion."
}
```

`capture_method` is one of `CAPTURED_CAMERA_MOVE`, `DIGITAL_SIMULATION`, or
`EITHER_WITH_LIMITS`. No record may state that arbitrary footage can always be
converted into the requested motion. Digital push/pull, pan, truck, parallax,
orbit, whip, match-motion, and rack-focus simulations must declare crop,
resolution, depth, masking, motion-blur, or optical limitations as applicable.
`rack_focus_simulation` must never be described as a true optical focus pull.

### Rights-requirements schema

`rights_requirements.json` has this exact top-level shape:

```json
{
  "schema_version": "1.0.0",
  "pack_id": "local-video-filmmaking",
  "declaration_count": 8,
  "required_plan_key": "rights",
  "verification_values": ["VERIFIED", "NOT_APPLICABLE", "RESTRICTED", "UNKNOWN"],
  "unknown_or_restricted_action": "KEEP_PLANNING_ONLY_AND_BLOCK_EXECUTION",
  "declarations": []
}
```

Each declaration definition requires:

```json
{
  "id": "source_ownership",
  "required": true,
  "purpose": "Why the declaration is needed.",
  "accepted_evidence": ["Owner statement, license record, or another concrete reference."],
  "plan_fields": ["declared_value", "verification", "evidence", "restrictions", "notes"],
  "unknown_action": "KEEP_PLANNING_ONLY_AND_BLOCK_EXECUTION",
  "existing_capability_mapping": []
}
```

Every generated plan must contain all eight keys under `rights`. A value of
`UNKNOWN` is truthful and allowed for a draft plan, but it blocks any future
execution claim. `NOT_APPLICABLE` requires a reason in `notes`. No empty or
omitted declaration is treated as consent, ownership, or permission.
Unknown top-level keys and unknown declaration IDs are rejected.

## Exact capability IDs

### Editing grammar — 13

1. `standard_cut`
2. `jump_cut`
3. `j_cut`
4. `l_cut`
5. `cut_on_action`
6. `cross_cut`
7. `cutaway`
8. `montage`
9. `match_cut`
10. `smash_cut`
11. `insert_shot`
12. `reaction_cut`
13. `parallel_editing`

### Framing and composition — 20

1. `rule_of_thirds`
2. `central_composition`
3. `symmetry`
4. `intentional_imbalance`
5. `headroom`
6. `lead_room`
7. `negative_space`
8. `foreground_midground_background`
9. `frame_within_frame`
10. `depth_layers`
11. `subject_separation`
12. `eyeline`
13. `screen_direction`
14. `180_degree_rule`
15. `30_degree_rule`
16. `shot_size_progression`
17. `camera_height`
18. `lens_perspective_awareness`
19. `safe_area`
20. `platform_reframing`

### Pacing and visual storytelling — 11

1. `hook_first_three_seconds`
2. `shot_duration_rhythm`
3. `information_density`
4. `beat_mapping`
5. `visual_escalation`
6. `pattern_interrupt`
7. `setup_payoff`
8. `b_roll_motivation`
9. `continuity`
10. `emotional_arc`
11. `cta_end_card`

### Camera and movement — 14

1. `static`
2. `pan`
3. `tilt`
4. `push_in`
5. `pull_out`
6. `dolly`
7. `truck`
8. `orbit`
9. `crane`
10. `handheld`
11. `parallax`
12. `rack_focus_simulation`
13. `whip_motion`
14. `match_motion`

### Rights declarations — 8

1. `source_ownership`
2. `license`
3. `brand_restrictions`
4. `face_person_consent`
5. `music_rights`
6. `font_rights`
7. `stock_attribution`
8. `ai_generated_asset_disclosure_metadata`

## Existing TOAN AAS capability mapping

The inventory distinguishes explicit reusable support from partial semantic
building blocks. `EXISTING_AND_VALID` does not mean the full technique is
locally executable; it means the repository already models the named concept
at a knowledge, prompt, planner, catalog, or local-edit layer. Every mapping in
the future JSON remains `reference_only`.

### Editing mapping

| ID | Inventory | Existing reference and relationship |
| --- | --- | --- |
| `standard_cut` | `EXISTING_BUT_INCOMPLETE` | `services/video_edit_capabilities.py` trim/concat catalog and `services/video_local_editing.py` primitives; no canonical filmmaking contract. |
| `jump_cut` | `EXISTING_AND_VALID` | `knowledge/video/manual_editing.json` names clean talking-head jump cuts as a production pattern. |
| `j_cut` | `EXISTING_BUT_INCOMPLETE` | `services/video_scene_transition_planner.py` supports sound bridges; no typed picture/audio offset contract. |
| `l_cut` | `EXISTING_BUT_INCOMPLETE` | `services/video_cinematic_continuity.py` models an audio bridge tail; no typed L-cut boundary. |
| `cut_on_action` | `EXISTING_AND_VALID` | `services/video_scene_transition_planner.py::SUPPORTED_TRANSITIONS` explicitly includes cut on action. |
| `cross_cut` | `MISSING` | No relevant editorial cross-cut contract found. |
| `cutaway` | `EXISTING_AND_VALID` | `config/video_prompt_vault/profiles/news.json` and `product_review.json` contain reusable cutaway shot templates. |
| `montage` | `EXISTING_BUT_INCOMPLETE` | Local concat/reorder exists, but selection rhythm and narrative compression are not modeled. |
| `match_cut` | `EXISTING_AND_VALID` | `services/video_scene_transition_planner.py::SUPPORTED_TRANSITIONS` explicitly includes match cut. |
| `smash_cut` | `EXISTING_BUT_INCOMPLETE` | Hard-cut vocabulary exists in `services/video_product_profiles.py`; contrast/impact semantics are absent. |
| `insert_shot` | `EXISTING_BUT_INCOMPLETE` | Detail-insert vocabulary exists in `data/prompt_vault/camera_moves.json`; no canonical insert-shot contract. |
| `reaction_cut` | `EXISTING_AND_VALID` | `config/video_prompt_vault/profiles/ugc_affiliate.json` contains a reaction shot template. |
| `parallel_editing` | `MISSING` | Parallel runtime dispatch is unrelated; no editorial parallel-editing contract found. |

### Framing/composition mapping

| ID | Inventory | Existing reference and relationship |
| --- | --- | --- |
| `rule_of_thirds` | `MISSING` | No relevant reusable rule found. |
| `central_composition` | `EXISTING_BUT_INCOMPLETE` | Centered prompt templates exist in `config/video_prompt_vault/profiles/educational.json`. |
| `symmetry` | `EXISTING_BUT_INCOMPLETE` | Architecture prompt vocabulary exists in `services/architecture_prompt_builder.py`; no general contract. |
| `intentional_imbalance` | `EXISTING_BUT_INCOMPLETE` | Asymmetric architecture vocabulary exists; no general intentional-imbalance contract. |
| `headroom` | `MISSING` | No relevant reusable rule found. |
| `lead_room` | `MISSING` | No relevant reusable rule found. |
| `negative_space` | `EXISTING_AND_VALID` | `video_prompt_quality.py` contains an explicit negative-space composition rule. |
| `foreground_midground_background` | `EXISTING_BUT_INCOMPLETE` | Foreground wipe/cover concepts exist; no three-plane composition schema. |
| `frame_within_frame` | `MISSING` | No relevant reusable rule found. |
| `depth_layers` | `EXISTING_BUT_INCOMPLETE` | Depth/parallax vocabulary exists in `video_prompt_quality.py`; no layer contract. |
| `subject_separation` | `EXISTING_BUT_INCOMPLETE` | Clear-subject/clean-background guidance exists in `data/prompt_vault/video_styles.json`. |
| `eyeline` | `EXISTING_BUT_INCOMPLETE` | Gaze-direction preservation exists in `knowledge/video/ai_edit_vfx.json`; no eyeline contract. |
| `screen_direction` | `EXISTING_BUT_INCOMPLETE` | `services/video_scene_continuity.py` validates motion direction; no screen-axis field. |
| `180_degree_rule` | `MISSING` | No relevant reusable axis rule found. |
| `30_degree_rule` | `MISSING` | No relevant reusable angle-change rule found. |
| `shot_size_progression` | `EXISTING_BUT_INCOMPLETE` | `services/video_idea_catalog.py` contains wide/medium/close sequencing guidance. |
| `camera_height` | `EXISTING_BUT_INCOMPLETE` | Eye-level and low-angle vocabulary exists, but no typed height model. |
| `lens_perspective_awareness` | `EXISTING_BUT_INCOMPLETE` | Lensing and natural-perspective guidance exists in `video_prompt_quality.py`; no validation contract. |
| `safe_area` | `EXISTING_AND_VALID` | `data/prompt_vault/platform_rules.json` models platform safe-zone constraints. |
| `platform_reframing` | `EXISTING_AND_VALID` | `services/video_local_editing.py` supports geometric crop/fit and platform rules; no claim of subject tracking. |

### Pacing/storytelling mapping

| ID | Inventory | Existing reference and relationship |
| --- | --- | --- |
| `hook_first_three_seconds` | `EXISTING_AND_VALID` | `data/prompt_vault/prompts.json` and `video_prompt_quality.py` explicitly model a 0–3 second hook. |
| `shot_duration_rhythm` | `EXISTING_AND_VALID` | `services/video_product_profiles.py` and `video_prompt_quality.py` contain per-shot duration policies. |
| `information_density` | `EXISTING_BUT_INCOMPLETE` | One-concept-per-scene guidance exists; no density validation model. |
| `beat_mapping` | `EXISTING_BUT_INCOMPLETE` | Transition-beat and sound-cue vocabulary exists in current knowledge files; no typed beat map. |
| `visual_escalation` | `EXISTING_AND_VALID` | Cinematic-trailer profiles and `services/video_cinematic_continuity.py` model escalation arcs. |
| `pattern_interrupt` | `EXISTING_AND_VALID` | `video_prompt_quality.py` explicitly models pattern interruption for early attention. |
| `setup_payoff` | `EXISTING_AND_VALID` | `knowledge/video/prompt_patterns/curated_defaults.json` contains setup/payoff scene roles. |
| `b_roll_motivation` | `EXISTING_AND_VALID` | `knowledge/video/manual_editing.json` requires context-motivated B-roll. |
| `continuity` | `EXISTING_AND_VALID` | `services/video_scene_continuity.py` provides structured continuity validation. |
| `emotional_arc` | `EXISTING_AND_VALID` | `services/video_cinematic_continuity.py` defines and produces emotional arcs. |
| `cta_end_card` | `EXISTING_AND_VALID` | `data/prompt_vault/cta_templates.json` and `video_prompt_quality.py` reserve a clean CTA end frame. |

### Camera/movement mapping

| ID | Inventory | Existing reference and relationship |
| --- | --- | --- |
| `static` | `EXISTING_AND_VALID` | `config/video_prompt_vault/shared/camera_motion.json` includes locked-off/static guidance. |
| `pan` | `EXISTING_AND_VALID` | `video_prompt_quality.py` normalizes pan direction; the transition planner supports camera-pan continuation. |
| `tilt` | `EXISTING_BUT_INCOMPLETE` | Tilt prompt vocabulary exists, but not in a shared typed motion contract. |
| `push_in` | `EXISTING_AND_VALID` | `video_prompt_quality.py` contains an explicit push-in rule. |
| `pull_out` | `EXISTING_AND_VALID` | `video_prompt_quality.py` contains an explicit slow pull-out rule. |
| `dolly` | `EXISTING_AND_VALID` | Shared camera-motion configuration and prompt normalization model dolly movement. |
| `truck` | `EXISTING_BUT_INCOMPLETE` | Lateral tracking vocabulary exists in `data/prompt_vault/camera_moves.json`; no truck alias/contract. |
| `orbit` | `EXISTING_AND_VALID` | `video_prompt_quality.py` contains orbit guidance. |
| `crane` | `EXISTING_AND_VALID` | `services/architecture_scene_planner.py` contains planned crane moves. |
| `handheld` | `EXISTING_AND_VALID` | Shared camera-motion configuration and prompt normalization model handheld movement. |
| `parallax` | `EXISTING_AND_VALID` | `services/video_edit_capabilities.py` and `video_prompt_quality.py` explicitly name parallax; execution remains separately gated. |
| `rack_focus_simulation` | `MISSING` | No reusable rack-focus simulation contract found. |
| `whip_motion` | `EXISTING_BUT_INCOMPLETE` | `services/video_scene_transition_planner.py` supports the narrower whip-pan concept. |
| `match_motion` | `EXISTING_BUT_INCOMPLETE` | The transition planner uses the alias `motion match`; no canonical requested ID or realization limits. |

### Rights mapping

| Declaration | Inventory | Existing reference and relationship |
| --- | --- | --- |
| `source_ownership` | `EXISTING_BUT_INCOMPLETE` | `services/knowledge_vault.py` has reusable rights status, but video plans do not require this declaration. |
| `license` | `EXISTING_BUT_INCOMPLETE` | Knowledge Vault and prompt seed records carry license information; no 26C plan gate exists. |
| `brand_restrictions` | `EXISTING_BUT_INCOMPLETE` | Brand/logo integrity rules exist in prompt and media-classification files; no structured declaration. |
| `face_person_consent` | `EXISTING_BUT_INCOMPLETE` | Consent and real-person review guidance exists; no per-plan declaration. |
| `music_rights` | `EXISTING_BUT_INCOMPLETE` | Legal policy exists; no music-specific plan metadata contract. Music/Suno stays locked. |
| `font_rights` | `MISSING` | No structured font-rights field found. |
| `stock_attribution` | `EXISTING_BUT_INCOMPLETE` | Attribution obligations exist in legal documentation; no structured plan field. |
| `ai_generated_asset_disclosure_metadata` | `MISSING` | No structured disclosure metadata field found. |

Inventory totals for the 58 filmmaking IDs are 26 `EXISTING_AND_VALID`,
23 `EXISTING_BUT_INCOMPLETE`, and 9 `MISSING`. These totals classify current
repository evidence, not production readiness.

## Readiness semantics

TASK 26C uses the master readiness terms without inflating them:

| State | Meaning for this pack |
| --- | --- |
| `NOT_INSTALLED` | Approved skill/JSON file is absent. This is the 26C-1 state. |
| `INSTALLED` | Files exist and parse, but focused contract verification has not passed. |
| `CONTRACT_PASS` | All focused static contracts pass against the committed files. |
| `LOCAL_DEMO_PASS` | Not applicable to a planning-only knowledge pack. |
| `PAID_SMOKE_REQUIRED` | Forbidden for TASK 26C; no paid capability is exercised. |
| `PRODUCTION_READY` | Forbidden inference; the pack has no runtime integration. |
| `PUBLIC` | Forbidden; no public UI or loader registration exists. |

`inventory_status` and readiness are independent. An
`EXISTING_AND_VALID` mapping can still have only planning-contract readiness.
A `CONTRACT_PASS` result proves schema and content completeness, not that any
camera move or edit can be executed on arbitrary footage.

## Rights and consent gate

Every plan created with the skill must emit a `rights` object containing the
eight exact declaration IDs. Each declaration has `declared_value`,
`verification`, `evidence`, `restrictions`, and `notes`.

Rules:

1. `UNKNOWN` is not approval.
2. `RESTRICTED` preserves the restriction and blocks incompatible execution.
3. `NOT_APPLICABLE` requires a reason.
4. Source ownership and license are separate declarations.
5. Consent is required per recognizable person when relevant; generic project
   access does not imply face/person consent.
6. Music/Suno is locked. The pack neither generates nor downloads music.
7. Font use requires a system, open, commercial, or owner-supplied license
   record appropriate to the intended use.
8. Stock attribution is retained when a license requires it.
9. AI-generated asset metadata records what was generated, the disclosed
   status, and any owner/platform disclosure restriction; it never certifies
   legal compliance automatically.
10. Missing or unresolved rights keep the result planning-only and must not
    create a provider call, render, delivery, publication, or wallet action.

## Failure and fallback behavior

The skill must prefer a truthful non-executable plan over a fabricated success:

- Missing source-shot requirements produce a named blocker and a safe fallback,
  not a claim that the technique is ready.
- Incompatible angles, axis, eyeline, motion direction, frame rate, resolution,
  audio separation, or duration are recorded as failure conditions.
- Planned camera motion that was not captured is labeled as unavailable or as
  a limited digital simulation; the distinction is never hidden.
- J/L cuts fall back to a clean standard audio boundary when separate clean
  dialogue/ambience timing cannot be established.
- Match, movement, and continuity techniques fall back to a standard cut or
  static framing when their visual correspondence cannot be validated.
- Rights uncertainty blocks execution even when the creative plan is valid.
- A fallback cannot enable a provider, paid service, public UI, renderer, or
  production route.

## Focused test plan for PHASE 26C-2

The approved test file is:

`tests/test_p1_localvideostudio26c_filmmaking_skills.py`

The implementation must follow RED–GREEN–REFACTOR:

1. Add the focused test before the skill files and run it. The expected RED
   reason is that the approved skill files do not exist.
2. Validate the exact six approved skill files and reject unexpected runtime
   files, Python modules, package initializers, scripts, credentials, or URLs.
3. Parse all five JSON files with `json.loads` and validate exact top-level
   keys, `schema_version`, `pack_id`, group IDs, and declared counts.
4. Assert exact ID sets: 13 editing, 20 framing, 11 pacing, 14 camera, and 8
   rights declarations.
5. Assert 58 globally unique capability IDs and eight unique rights IDs.
6. Assert all common text/list fields are non-empty and all fallback IDs either
   resolve to another exact capability or are `null`.
7. Assert every capability has exactly `planning_only=true`,
   `runtime_registered=false`, `provider_executable=false`, and
   `public_ui=false`.
8. Assert every editing record contains the complete audio-boundary, timing,
   continuity-risk, and validation structures.
9. Assert every camera record contains capture method, realization limits,
   motion-continuity checks, and simulation disclosure. Search for and reject
   universal arbitrary-footage claims.
10. Assert every existing mapping uses a tracked repository path, a permitted
    support layer, and `relationship=reference_only`.
11. Assert rights declarations are exact, required, evidence-aware, and use
    `KEEP_PLANNING_ONLY_AND_BLOCK_EXECUTION` for unknown or restricted status.
12. Validate `SKILL.md` frontmatter contains only `name` and `description`, the
    description is trigger-focused, and the body routes to the five JSON files
    without production instructions.
13. Run the same focused test again for GREEN, then run the existing knowledge
    catalog validation to prove the fixed six-store loader remains unchanged.
14. Run `py_compile` only for the changed Python test module. Run
    `python -m py_compile bot.py` as a baseline/reporting check without changing
    `bot.py`; a clean-main timeout must be reported as `TIMEOUT`, not `PASS`.
15. Run `git diff --check`, a changed-file secret scan, and a diff-scope check.
    The implementation diff is limited to this spec, the six approved skill
    files, and the one focused test. If an existing full-suite scope guard
    rejects these owner-approved paths, stop and request owner approval before
    changing that guard.

The focused test performs no media generation, external network request,
provider selection, wallet access, delivery, deployment, or production import.

## Acceptance and locked scope

PHASE 26C-1 is accepted when this spec is committed on the approved branch and
the owner reviews it. PHASE 26C-2 must not begin before that review.

PHASE 26C-2 is accepted only when:

- all exact IDs and schemas above are implemented with original text;
- the focused contract passes;
- existing mappings remain references rather than duplicated behavior;
- `knowledge/video/` and `services/profile_router.py` remain unchanged;
- `bot.py`, Product Video summary/backstack, Product Video, SubDub, menus,
  buttons, callback/state/back-stack behavior, renderers, workers, providers,
  Railway, VPS, PayOS, wallet/Xu, database, webhooks, billing, and Music/Suno
  remain unchanged;
- Provider calls, Motion calls, Higgsfield calls, paid generations, wallet/Xu
  mutations, and production deploys all remain zero; and
- no readiness above `CONTRACT_PASS` is claimed.
