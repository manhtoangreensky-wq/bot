# Context & Prompt Cache Hygiene Reference

## Purpose
Maximizes prompt caching efficiency (90% cost discount on cache reads) and minimizes context bloat across all AI models.

## External Research & Adoption
- **Source**: OpenAI Builder's Guide to Frontier Models, Prompt Caching Architecture (ICML 2026).
- **Retrieved At**: 2026-08-21.
- **What is Adopted**: Deterministic prefix stability, deferred dynamic context, compact operational kernels.
- **What is Not Adopted**: Hardcoded vendor pricing or ephemeral token rate formulas in permanent system prompts.

## Core Rules
1. **Static First, Dynamic Last**: Static governance rules and skill definitions remain invariant at the top of context. Volatile parameters (file content, test logs, diffs) appear at the tail.
2. **Deferred Discovery**: Inactive skill bodies and extensive guides must be kept in `references/` and loaded only when triggered.
3. **No Dynamic SHA in Headers**: Never embed volatile commit SHAs, active incident logs, or temporary token counts into permanent SKILL.md headers.
