# Durable Run State & FSM State Machine Reference

## Purpose
Defines the schema and transition rules for durable task state tracking (`.agents/state/<task_id>.yaml`) based on StateM principles.

## External Research & Adoption
- **Source**: StateM Architecture (`https://henryqin1997.github.io/statem/`).
- **Retrieved At**: 2026-08-21.
- **What is Adopted**: Moving procedural state out of LLM volatile context into human-readable, resumable YAML runbooks; Gated transitions.
- **What is Not Adopted**: External heavy binary runtime dependencies; custom CLI requirements when native Python scripts suffice.

## State Schema Specification (`.agents/state/<task_id>.yaml`)
```yaml
version: "2.0"
task_id: "TASK-20260821-001"
repository: "manhtoangreensky-wq/bot"
branch: "fix/feature-branch"
base_sha: "c7ac969"
head_sha: "c7ac969"
phase: "VERIFY" # Options: READ, CONTRACT, BUILD, REVIEW, VERIFY, REPORT, LEARN
goal: "Clear 1-line statement of task goal"
scope:
  allowed_files:
    - "services/module.py"
  protected_files:
    - "config/payment.json"
acceptance:
  - "Criterion 1"
tests:
  - "pytest tests/test_module.py"
evidence:
  - "37 passed in 12s"
decisions:
  - "Decision notes"
blockers: []
owner_gates:
  deploy_approved: false
  provider_approved: false
  wallet_approved: false
next_action: "Execute REPORT phase"
updated_at: "2026-08-21T14:40:00Z"
```

## Transition Gates
- `READ -> CONTRACT`: Source and requirements resolved.
- `CONTRACT -> BUILD`: Allowed files, protected files, acceptance declared.
- `BUILD -> REVIEW`: Implementation complete within allowed files.
- `REVIEW -> VERIFY`: Diff inspected, zero unauthorized files.
- `VERIFY -> REPORT`: Test suite executed with empirical pass/fail output.
- `REPORT -> LEARN`: Postmortem documented (optional).
