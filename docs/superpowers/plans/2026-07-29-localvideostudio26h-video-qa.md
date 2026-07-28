# Local Video Studio 26H Video QA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bổ sung contract QA video local fail-closed với đúng 19 validation và
không thay đổi bất kỳ runtime/UI production nào.

**Architecture:** Một JSON tĩnh là source of truth, được `SKILL.md` định tuyến.
Focused test chỉ đọc JSON/Markdown/helper symbols bằng Python stdlib; mọi
FFmpeg/ffprobe mapping là metadata-only và mọi fixture là ephemeral.

**Tech Stack:** JSON UTF-8 deterministic, Markdown, Python stdlib/pytest,
FFmpeg/ffprobe metadata references.

---

## Task 1: Inventory and RED

- [x] Tạo worktree/branch 26H từ main sau merge 26G.
- [x] Inventory 19 validation, no-fake cases và collision với 26D/26E/26G.
- [x] Viết focused test exact schema/IDs/locks và chạy RED khi pack chưa tồn tại.

## Task 2: QA contract and skill

- [x] Tạo `video_qa_contract.json` với 19 IDs/order/count và fail-closed rules.
- [x] Map helper/reference hiện hữu bằng `metadata_only`, không import runtime.
- [x] Link rights, audio QA/loudness, delivery profiles và kinetic typography.
- [x] Tạo `SKILL.md` với relative links và exact operating procedure.

## Task 3: Legal local fixtures and no-fake-success

- [x] Khóa tám fixture recipes là ephemeral-only, không commit binary/customer media; chỉ fixture temp được phép gọi local tools.
- [x] Khóa bảy no-fake-success trường hợp và render-promise evidence.
- [x] Giữ Music/Suno, provider, runtime và public UI disabled.

## Task 4: Verification

- [x] Chạy focused 26H, deterministic JSON, link/reference/static scans.
- [x] Chạy regression 26C–26G và test-module compile.
- [x] Chạy `git diff --check`, status/scope và secret/placeholder scan.

## Task 5: Ship and continue

- [ ] Review spec compliance và code quality.
- [ ] Commit, rebase latest main, push và mở PR 26H.
- [ ] Khi PR CLEAN và tests pass, merge bằng merge commit, ghi merge/main SHA.
- [ ] Chỉ sau merge mới tạo worktree/branch 26I; không deploy.
