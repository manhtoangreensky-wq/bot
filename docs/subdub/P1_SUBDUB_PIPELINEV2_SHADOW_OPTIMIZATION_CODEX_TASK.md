# P1.SUBDUB.PIPELINEV2 Shadow/Replay Optimization Task

> **For agentic workers:** Do not implement Phase 2 until the owner approves the
> Phase 1 design in `TOAN_AAS_SUBDUB_PIPELINEV2_SHARED_DAG_DESIGN_2026-07-28.md`.

**Goal:** Design and later implement a disabled/admin-only shared semantic DAG
that derives all four SubDub lanes from one source master and one translation
master without destabilizing the live V1 routes.

**Architecture:** Ingest, ASR/alignment and semantic normalization happen once.
Translation happens once per source/target/config fingerprint. Subtitle and dub
copies are independent derived artifacts that retain stable source and meaning
IDs. Every stage is persisted, idempotent and QC-gated; delivery receipt comes
before billing.

**Tech Stack:** Existing Python Telegram bot, existing SubDub executor and
FFmpeg adapters as read-only V1 references, JSON artifacts, existing engine
async persistence, legal fixtures/replay, and focused pytest tests. No new
microservice, queue, RabbitMQ or DB migration.

---

## Owner Locks

- V1 four-lane public path remains the production path.
- Public callbacks, callback data, menu/UI/UX and back routes are unchanged.
- Product Video, renderer/FFmpeg ownership, worker, PayOS, pricing, wallet/Xu,
  webhook and DB schema are unchanged.
- `provider_calls=0`, `wallet_mutations=0`, `customer_deliveries=0`,
  `production_traffic=0` during design and shadow/replay.
- Railway deploy is `NO`.
- No automatic paid retry, provider fallback, startup smoke or cron call.
- Status, health, public-open and recovery are read-only and create zero tasks.

## Current Phase And Stop Point

This task has completed the inventory/design-only phase when the linked design
document is present and the scope audit is clean. Stop at that point for owner
review. Do not create V2 runtime modules or connect a public callback in this
phase.

Authoritative design:

`docs/subdub/TOAN_AAS_SUBDUB_PIPELINEV2_SHARED_DAG_DESIGN_2026-07-28.md`

## Phase 0: Inventory Checklist

- [x] Map all four public lane callbacks and modes.
- [x] Map the common executor, blackbox ownership and final delivery boundary.
- [x] Map ingest, embedded subtitle/OCR/ASR resolution and absolute chunk timing.
- [x] Map translation, TTS, timeline audio, mux and MP4 validation.
- [x] Map workspace artifacts, asset records, manifest and persisted job state.
- [x] Map job key, dedupe, status recovery and late-delivery recovery.
- [x] Map current retry behavior and identify paid-submit uncertainty gaps.
- [x] Map status percentages and terminal state transitions.
- [x] Map delivery-before/after-charge behavior and identify the V2 change.
- [x] Map subtitle style/font/Unicode behavior and audio normalization settings.
- [x] Map current combo text behavior and the lack of separate subtitle/dub copies.
- [x] Map long-project part delivery and the missing one-final-MP4 concat step.

Evidence is recorded with file:line references in the authoritative design
document. The inventory is descriptive; it does not authorize V1 edits.

## Phase 1: Design Contracts

### Shared DAG

```text
ingest -> audio masters -> VAD -> ASR/alignment -> optional diarization
       -> source_semantic_master
       -> translation_master (lanes 2-4)
       -> subtitle_copy / dub_script
       -> TTS + M&E + mix / subtitle render
       -> one final mux
       -> QC -> delivery receipt -> charge once
```

### Required versioned artifacts

- `source_semantic_master.json`
- `translation_master.json`
- `subtitle_copy.json`
- `dub_script.json`
- `voice_cast.json`
- `stage_qc.json`
- `delivery_receipt.json`

Every artifact must include schema version, input/output fingerprints, stable
source IDs, retention class and a QC status. Provider metadata is referenced by
an admin-only pointer and is not part of public text or public fingerprints.

### Semantic invariants

- VAD identifies speech regions but preserves original absolute offsets.
- Chunk-local timestamps are converted to the original video timeline before a
  source master is written.
- Alignment truth is explicit: `word_aligned`, `segment_timed` or
  `alignment_unavailable`.
- Translated subtitle cues retain source cue start/end; only text and line
  breaks are adapted.
- One translation master feeds lanes 2, 3 and 4.
- Combo produces two different text artifacts with shared `meaning_id` values.
- Subtitle adaptation is profile-driven; Vietnamese Telegram starts at 42 CPL
  and two lines, while other scripts use their own profiles.
- Dubbing uses duration-aware candidates, semantic rewriting and measurement
  before any conservative timing adjustment.
- Owner fidelity profile synthesizes at 1.0, does not trim utterances and never
  overlaps the next cue. An unfit cue fails or waits for review.
- M&E separation cannot claim clean without artifact QC.
- Loudness target comes from a versioned audio profile, never one universal
  hard-coded target.

### State and side-effect invariants

- Stage state is one of `PENDING`, `RUNNING`, `PASS`, `FAIL`, `WAITING_REVIEW`,
  `CANCELLED`.
- Idempotency key is `job_id + stage + segment_id_or_global + config_hash`.
- Poll/download/retrieve may retry an existing task; paid submit may not be
  retried automatically.
- An uncertain accepted request stays `WAITING_REVIEW`; it is never replaced.
- HTTP 200, task ID or URL without a validated artifact is not success.
- Missing MP4 is terminal failure and charge 0.
- `validate -> deliver -> persist receipt -> charge once -> report once`.

### Media contract

- Product input cap: 500 MiB.
- Product final Telegram output cap: 500 MiB.
- Transport capability is reported separately: cloud Bot API `getFile` limit
  versus local Bot API up to 2 GiB.
- Product duration cap: 3600 seconds.
- Long media may use chunks/parts internally but must return one concatenated,
  fully validated final MP4. Parts are not customer success outputs.
- FFmpeg commands use resolved executable paths and argument lists; no
  `shell=True`, hard-coded host path or `-shortest`.

## Phase 2: Isolated Implementation Plan (Approval Required)

The following files are a planned isolated module boundary. They are not created
in Phase 0/1.

### Task 1: V2 configuration and contracts

**Planned files:**

- Create: `services/subdub_v2/config.py`
- Create: `services/subdub_v2/contracts.py`
- Create: `services/subdub_v2/fingerprints.py`
- Test: `tests/test_p1_subdub_v2_contracts.py`

Implement the three disabled flags, schema versions, enums, deterministic JSON
serialization and SHA-256 fingerprints. The module must be import-safe and
must not import Telegram handlers, wallet code or providers at module import.

Acceptance:

- Invalid schema/state is rejected before a stage can be `PASS`.
- Fingerprints are stable across key order and exclude secret fields.
- All flags default to `0`.
- Importing the module makes zero network calls.

### Task 2: Source semantic master

**Planned files:**

- Create: `services/subdub_v2/source_master.py`
- Test: `tests/test_p1_subdub_v2_source_master.py`

Use existing source-resolution and long-media helpers as injected functions.
Build audio master, ASR input, speech regions, alignment truth and stable
segments. Reuse absolute offset behavior from
`services/subdub_long_media.py:270-304`; do not move or rewrite V1 code.

Acceptance:

- One fixture produces one source master reused by all four lane replays.
- VAD never changes absolute cue offsets.
- A segment-timed fixture cannot be reported as word-aligned.
- A missing timed source is labeled honestly.

### Task 3: Translation master and copies

**Planned files:**

- Create: `services/subdub_v2/translation_master.py`
- Create: `services/subdub_v2/copies.py`
- Test: `tests/test_p1_subdub_v2_translation_copies.py`

Inject a fixture translator. Build one semantic translation master, then derive
subtitle copy and dub script without a second translation call. Validate names,
numbers, glossary entries and stable IDs.

Acceptance:

- Lanes 2-4 share one translation artifact fingerprint.
- Subtitle and dub text may differ but share meaning IDs.
- A missing translation is `FAIL`, never source-text fake success.
- Subtitle timing equals source timing exactly.

### Task 4: Profile-driven subtitle and audio adaptation

**Planned files:**

- Create: `services/subdub_v2/profiles.py`
- Create: `services/subdub_v2/subtitle_adapter.py`
- Create: `services/subdub_v2/duration_fit.py`
- Test: `tests/test_p1_subdub_v2_profiles_and_fit.py`

Implement versioned subtitle profiles, real rendered-glyph QC hooks, duration
candidate selection and owner fidelity 1.0 speech fit. Candidate generation is
fixture-injected in shadow mode; no provider call is permitted.

Acceptance:

- Vietnamese profile enforces 42 CPL/two lines.
- CJK/Thai profiles are not forced through Vietnamese limits.
- TTS input speed and post-tempo are 1.0 in the owner profile.
- A long utterance is rewritten/recandidate-selected before any timing change.
- No overlap, truncation or silent dropped cue is accepted.

### Task 5: Stage artifact registry and safe recovery

**Planned files:**

- Create: `services/subdub_v2/artifacts.py`
- Create: `services/subdub_v2/replay.py`
- Test: `tests/test_p1_subdub_v2_idempotency_recovery.py`

Persist stage claims and artifacts through an approved existing JSON/result
store without a DB migration. The replay adapter must use only legal fixtures.

Acceptance:

- Duplicate confirm returns the prior stage claim.
- Poll/download retries the same stored task ID.
- Uncertain accepted submit becomes `WAITING_REVIEW`.
- Recovery never calls submit a second time.
- Status/health/public-open reads create zero tasks.

### Task 6: Combo QC, final media QC and receipt model

**Planned files:**

- Create: `services/subdub_v2/qc.py`
- Create: `services/subdub_v2/delivery.py`
- Test: `tests/test_p1_subdub_v2_qc_delivery.py`

Add semantic combo checks, M&E checks, profile loudness checks, full-decode MP4
checks, 500 MiB/3600-second checks and delivery receipt ordering. Delivery is a
fixture sink in shadow mode.

Acceptance:

- A structurally valid but semantically invalid MP4 is not `PASS`.
- A missing final MP4 yields zero charge eligibility.
- Receipt is persisted before the charge claim is even eligible.
- Shadow delivery and wallet counters remain zero.

### Task 7: Four-lane replay harness

**Planned files:**

- Create: `services/subdub_v2/harness.py`
- Create: `tests/fixtures/subdub_v2/` legal fixtures only
- Test: `tests/test_p1_subdub_v2_replay_harness.py`

Replay one fixture through all four lane derivations and compare against V1
artifacts without calling a provider or Telegram. Keep the harness disconnected
from public callbacks.

Acceptance:

- `source_master_builds == 1`.
- `translation_master_builds == 1` for lanes 2-4.
- `provider_calls == 0`.
- `wallet_mutations == 0`.
- `deliveries == 0`.
- `new_failures_introduced == 0` against the clean base command.

## Phase 3: Review And Rollout (Separate Approval)

```text
design approval
-> shadow contract PASS
-> legal replay PASS
-> admin preview
-> owner-approved canary: source subtitle
-> owner-approved canary: translated subtitle
-> owner-approved canary: translated dub
-> owner-approved canary: combo
-> 5% -> 25% -> 50% -> 100%
```

Every rollout step has a stop condition if any lane loses validated MP4,
semantic QC, delivery receipt or billing truth. Rollback is:

```text
SUBDUB_PIPELINE_V2_PUBLIC_ALLOWED=0
```

V1 stays public and available throughout.

## Final Design-Phase Report

```text
TASK: P1.SUBDUB.PIPELINEV2
Design approved: NO - owner review required
Current stages mapped: YES
Duplicated work: YES - documented, not changed
Schemas: DESIGNED - 7 versioned contracts
Subtitle profiles: DESIGNED - configurable, Vietnamese 42 CPL / 2 lines
Translation master: DESIGNED - one per source/target/config fingerprint
Dub adaptation: DESIGNED - separate dub_script, strict 1.0 owner profile
Combo consistency: DESIGNED - shared meaning IDs, two derived text artifacts
Retry/idempotency: DESIGNED - no automatic paid replacement submit
Delivery/billing: DESIGNED - validate -> deliver -> receipt -> charge once

Focused tests: NOT RUN - design-only phase, no runtime code changed
Common tests branch/main: NOT RUN - design-only phase
New failures: NOT APPLICABLE - no runtime diff
Provider calls: 0
Wallet mutations: 0
Customer deliveries: 0

Public callbacks changed: NO
UI/UX changed: NO
Product Video changed: NO
Renderer changed: NO
Worker changed: NO
DB schema changed: NO
Railway deployed: NO

SHADOW CONTRACT PASS: NOT RUN - pending Phase 2 approval
REPLAY PASS: NOT RUN - pending Phase 2 approval
ADMIN PREVIEW PASS: NO
PUBLIC CANARY: NO
V2 LIVE PASS: NO
V1 STILL AVAILABLE: YES
Blockers: owner approval of Phase 1 design
```

Stop here. Do not implement, merge or deploy until the owner approves the
design and explicitly opens Phase 2.

## Approved Amendment A (2026-07-29)

Owner approved Phase 2 with these mandatory additions. The authoritative
details and invariants are in section 13 of the design document.

- [x] Safe UTF-8 TTS transport chunking with ordered text hashes and per-fragment claims.
- [x] Long-video resource budget: 500 MiB input/output, 3600 seconds, 12 parts,
  sequential execution and bounded workspace/audio/cue resources.
- [x] Explicit lineage across all seven schemas.
- [x] Three-level idempotency: request, stage/artifact and side-effect/transport.
- [x] First-class `ACCEPTANCE_UNKNOWN` with no replacement submit.
- [x] Quantitative V1/V2 replay metrics and blocking thresholds.
- [x] Privacy, retention and scope isolation rules.
- [x] Default-off V2 flags and one-step V1 rollback.
- [x] Exactly one final combo compose/mux boundary.

The amendment must be committed as one design-only commit before Phase 2 code.

## Phase 2 Execution Gate (Now Approved)

Implement only disabled shadow/replay modules and offline legal fixtures. Keep
the following side-effect counters at zero:

```text
provider_calls = 0
wallet_mutations = 0
customer_deliveries = 0
production_traffic = 0
```

No production callback imports the V2 package. No module import may call a
provider, Telegram, worker, wallet or database. The offline harness must use
injected fixture adapters and deterministic bytes.

Required Phase 2 report:

```text
SHADOW CONTRACT PASS=YES
REPLAY PASS=YES
provider calls=0
wallet mutations=0
V1 STILL AVAILABLE=YES
V2 LIVE PASS=NO
```
