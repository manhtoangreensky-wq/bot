# Anti-Overengineering & Minimal Code Footprint Reference

## Purpose
Guarantees minimal invasive code modification, zero unnecessary abstractions, early task termination upon success, and strict adherence to YAGNI.

## External Research & Adoption
- **Source**: PoLaR: Skip a Layer or Loop It (arXiv:2606.06574), Conformal Thinking (arXiv:2602.03814), LLM-as-a-Verifier (`llm-as-a-verifier.com`).
- **Retrieved At**: 2026-08-21.
- **What is Adopted**: Adaptive reasoning depth (skip simple layers, loop complex ones), empirical verification before claiming success, early stopping.
- **What is Not Adopted**: Speculative architecture layers or over-abstracted wrappers without real-world failure evidence.

## Core Rules
1. **Minimal Code Footprint**: Edit ONLY the necessary lines in the target function.
2. **YAGNI (You Aren't Gonna Need It)**: Do not write helper classes, future endpoints, or unrequested features.
3. **Early Stopping**: The moment empirical tests pass and acceptance criteria are satisfied, STOP, generate report, and do not make further unsolicited changes.
4. **No Opportunistic Refactoring**: Never rewrite working legacy code unless directly required by the user's task.
