# Local Video Studio 26I Codex Capability Index Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tạo một index duy nhất cho OpenMontage, 26C–26H và provider locks mà
không duplicate implementation hoặc nâng readiness sai evidence.

**Architecture:** Một JSON deterministic chứa 14 record nhóm và qualified IDs;
`SKILL.md` chỉ định cách đọc readiness/source-of-truth. Focused test so index
trực tiếp với JSON nguồn bằng Python stdlib.

**Tech Stack:** JSON UTF-8 deterministic, Markdown, Python stdlib/pytest, local
Git metadata read-only.

---

## Task 1: Inventory and RED

- [x] Tạo worktree/branch 26I từ main sau correction 26H.
- [x] Audit OpenMontage path/pin, repository groups và provider presence/locks.
- [x] Viết focused test exact schema/records/IDs/readiness và chạy RED.

## Task 2: Capability index

- [x] Tạo `capability_index.json` với 14 records và 251 qualified IDs unique.
- [x] Ghi exact location/status/local-cloud/free-paid/tools/shoot/confirmation/test/readiness.
- [x] Khóa Motion/Higgsfield paid-disabled, Suno locked, mọi production flag false.

## Task 3: Index skill and documentation

- [x] Tạo `SKILL.md` với relative links tới 26C–26H và exact lookup procedure.
- [x] Ghi readiness definitions và nguyên tắc installed không phải production-ready.
- [x] Không copy OpenMontage source hoặc skill content vào bot repo.

## Task 4: Verification

- [x] Chạy focused 26I, skill/link/source/deterministic/static checks.
- [x] Chạy regression 26C–26H và compile changed test module.
- [x] Chạy `git diff --check`, status/scope và secret/placeholder scan.

## Task 5: Ship

- [x] Review spec compliance và code quality.
- [ ] Commit, rebase latest main, push và mở PR 26I.
- [ ] Khi PR CLEAN và tests pass, merge bằng merge commit; ghi merge/main SHA.
- [ ] Không deploy hoặc bắt đầu 27A trong 26I.
