---
name: owner-governed-codex
description: Core governing operating kernel for all AI engineering tasks across the TOAN AAS ecosystem. Enforces strict single-agent lifecycle (READ -> CONTRACT -> BUILD -> REVIEW -> VERIFY -> REPORT -> LEARN), durable FSM state, empirical verification gates, Owner-approval gates, VPS-only deployment truth, and zero-loss semantic safety. Applies to ALL AI models without exception.
license: Apache-2.0
metadata:
  version: v2.0
  author: TOAN AAS Core Team
---

# TOAN AAS Owner-Governed Operating Kernel (V2)

Governing kernel for all software engineering work across the TOAN AAS repository and infrastructure. All AI models operate under this contract.

---

## 1. TRIGGER & SCOPE

- **Active Mandate**: At the beginning of EVERY technical task report, state:
  `Đang đọc và áp dụng skill owner-governed-codex cho task này.`
- **Applicability**: All repository code, configuration, database migrations, CI/CD pipelines, and infrastructure tasks.

---

## 2. AUTHORITY PRECEDENCE

1. **Owner Directives & Rules** (`AGENTS.md`, `AGENTS.override.md`, explicit chat instructions).
2. **Owner-Governed Kernel** (`owner-governed-codex`).
3. **Domain & Task Skills** (Loaded on demand / deferred).
4. **Model Default Heuristics**.

---

## 3. OPERATING CONTRACT & SAFETY GUARDRAILS

> [!CAUTION]
> **MANDATORY OWNER APPROVAL GATES**: An AI agent must NEVER automatically execute or claim without explicit Owner approval:
> 1. Production deployment (`DEPLOY`).
> 2. Environment / Secret / API Key modifications (`ENV/SECRETS`).
> 3. Deleting or dropping user/project data or tables (`DATA LOSS RISK`).
> 4. Paid external provider API calls (`PROVIDER_CALLS`).
> 5. Wallet, payment, or financial balance mutations (`WALLET_MUTATIONS`).
> 6. Promoting experimental lessons or candidate rules into global policy (`AUTO_PROMOTION=OFF`).

- **Truth Invariants**:
  - `MERGED != DEPLOYED != LIVE`.
  - `HTTP 200 != FINAL OUTPUT SUCCESS`.
  - `BUILD != PASS` (Do not claim PASS without empirical verification output).

---

## 4. FINITE STATE MACHINE (FSM) LIFECYCLE

All engineering tasks follow a deterministic 7-phase state machine:

```
READ  ──►  CONTRACT  ──►  BUILD  ──►  REVIEW  ──►  VERIFY  ──►  REPORT  [──►  LEARN]
```

1. **READ**: Inspect task requirements, repository context, open files, and relevant skills. Resolve source truth.
2. **CONTRACT**: Define explicit scope, allowed files, protected files, acceptance criteria, and test plan.
3. **BUILD**: Execute minimal code changes directly targeted at the problem (`MINIMAL_CODE_FOOTPRINT=ON`, `YAGNI=ON`).
4. **REVIEW**: Perform git diff review, check scope boundaries, verify no secrets or unintended edits.
5. **VERIFY**: Run automated test suites (`pytest`, `py_compile`, syntax/runtime checks) and capture empirical output.
6. **REPORT**: Deliver structured report using canonical report schema with verifiable evidence.
7. **LEARN** *(Optional)*: Log postmortem candidate lessons. Requires Owner approval to promote.

---

## 5. SINGLE-AGENT FOCUS & SUBAGENT EXCEPTION GATE

- **Default Execution**: `SINGLE_AGENT_DEFAULT=ON`. The primary agent manages the entire task lifecycle end-to-end to prevent context fragmentation and token overhead.
- **Subagent Exception Gate**: `SUBAGENT_AUTOSPAWN=OFF`. Subagents may ONLY be spawned when ALL 4 conditions are satisfied:
  1. `PARALLELIZABLE=YES`
  2. `WORKSTREAMS_INDEPENDENT=YES`
  3. `SHARED_MUTABLE_STATE_LOW=YES`
  4. `EXPECTED_BENEFIT_EXCEEDS_ORCHESTRATION_COST=YES`
- **Prohibited Subagent Spawns**: Linear debugging, small diffs, re-reading context, duplicate reviews, routine test execution.

---

## 6. ANTI-OVERENGINEERING & ADAPTIVE EFFORT

- **Anti-Overengineering Contract**:
  - `MINIMAL_CODE_FOOTPRINT=ON`: Modify only lines necessary to solve the issue.
  - `YAGNI=ON`: Do not build speculative features or unnecessary abstractions.
  - `EARLY_STOP=ON`: Once tests pass and acceptance is met, stop immediately.
  - `NO_OPPORTUNISTIC_REFACTOR=ON`: Do not refactor unrelated working code.
- **Adaptive Effort Classification**:
  - **TRIVIAL**: Direct minimal edit + quick verification (`py_compile`/targeted test).
  - **BOUNDED**: Contract + targeted unit tests + diff review.
  - **COMPLEX**: Full 7-phase lifecycle + optional durable runbook (`.agents/state/`).
  - **HIGH_RISK**: Full lifecycle + explicit rollback plan + Owner authorization gates.

---

## 7. CONTEXT & PROMPT CACHING HYGIENE

- **Prefix Stability**: Keep system policy and skill definitions static to maximize prompt cache hits.
- **Dynamic Last**: Place volatile task data (task id, diffs, tool output) at the end of context.
- **Deferred Discovery**: Load detailed reference manuals on-demand via `references/`, never inline large text into always-loaded headers.

---

## 8. PRODUCTION DEPLOYMENT TRUTH (VPS-ONLY)

- **Production Target**: Ubuntu VPS (`tg.toanaas.vn` / `/opt/toanaas/bot`).
- **Pipeline Truth**: `GitHub main` ──► `GitHub Actions (CI/CD)` ──► `tg.toanaas.vn (systemd services)`.
- **Obsolete Target**: Railway is deprecated for production; current runtime is 100% VPS-based.

---

## 9. CANONICAL REPORT SCHEMA

```markdown
TASK=
BASE_SHA=
HEAD_SHA=
FILES_CHANGED=
TESTS=
BASELINE_FAILURES=
BRANCH_FAILURES=
NEW_FAILURES=
PROTECTED_COMPARATORS=
PROVIDER_CALLS=
WALLET_MUTATIONS=
DEPLOY=
RUNTIME_SHA=
LIVE_PASS=
BLOCKERS=
```
