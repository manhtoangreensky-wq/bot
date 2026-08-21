# Execution Efficiency & Single-Agent Workflow Reference

## Purpose
Establishes execution efficiency principles for all AI models, preventing token bloat, context fragmentation, and subagent orchestration overhead.

## External Research & Adoption
- **Source**: `github.com/blavkgokuvnn/single-agent-skills`, Terminal-Bench 2.1 Agent Benchmarks, ICML 2026 Research.
- **Retrieved At**: 2026-08-21.
- **What is Adopted**: Single-agent primary responsibility, eliminating cross-agent conversational ping-pong, focused linear debugging.
- **What is Not Adopted**: Absolute dogmatic ban on parallel research when workstreams are mathematically independent.

## Core Rules
1. **Primary Agent Accountability**: The primary agent owns the prompt, the code edits, the test execution, and the final delivery report.
2. **Subagent Exception Gate**: Never spawn subagents unless:
   - Workstreams are strictly orthogonal.
   - Shared mutable state is zero or minimal.
   - Expected token/speed benefit clearly exceeds the ~10,000 token orchestration overhead.
