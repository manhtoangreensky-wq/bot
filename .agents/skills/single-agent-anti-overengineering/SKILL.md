---
name: single-agent-anti-overengineering
description: Deferred skill providing specialized guidance for complex refactoring, test-time verification, durable task state runbooks, and strict anti-overengineering constraints across all AI models.
license: Apache-2.0
metadata:
  version: v2.0
  author: TOAN AAS Core Team
---

# Single-Agent & Anti-Overengineering Specialized Skill (Deferred)

This skill provides specialized deep execution rules for complex tasks, architectural audits, and long-running workflows across all AI models.

---

## 1. SINGLE-AGENT HARNESS PRINCIPLES

1. **Monolithic Responsibility**: The single primary agent manages the entire task lifecycle. Do not break small tasks into multiple subagents.
2. **Subagent Exception Criteria**: Spawning a subagent requires explicit justification:
   - Workstreams must be 100% independent.
   - Zero shared mutable files.
   - Expected token gain must exceed 10,000 tokens.

---

## 2. STATEM DURABLE RUNBOOK INTEGRATION

For complex tasks (>3 files or high risk), maintain a durable task state at `.agents/state/<task_id>.yaml`.

- **Prohibited in State Files**:
  - No secrets, tokens, or private keys.
  - No Chain-of-Thought or reasoning monologues.
  - No raw multi-megabyte log dumps.
- **Allowed in State Files**:
  - Resumable phase, allowed files, protected files, acceptance criteria, test commands, and concise empirical output.

---

## 3. EMPIRICAL VERIFICATION (LLM AS A VERIFIER)

- **Verification Hierarchy**:
  1. Static compilation (`python -m py_compile <file>`).
  2. Targeted unit tests (`pytest <test_file> -v`).
  3. Integration & Contract tests (`pytest tests/ -k <feature>`).
- **Forbidden Claims**: Never output `PASS` or `ALL TESTS PASSED` without attaching the exact terminal output from the test execution.

---

## 4. EARLY STOPPING & YAGNI

- **Early Stopping**: Stop editing code immediately after all test assertions pass.
- **No Opportunistic Refactoring**: Do not polish, rename, or re-architect adjacent files outside the declared task scope.
