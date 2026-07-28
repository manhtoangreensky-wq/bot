# Local Video Studio 26G Local Capabilities Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bổ sung gap contracts local/free còn thiếu, delivery/accessibility
profiles và heavy-model inventory mà không cài model hoặc chạm sản phẩm cũ.

**Architecture:** Ba JSON tĩnh được `SKILL.md` định tuyến. G1 capability records
giữ namespace `local_capability.*`; delivery profiles và GPU inventory tách
schema để không trộn readiness. Focused test chỉ đọc JSON/Markdown bằng
stdlib, không import production.

**Tech Stack:** JSON UTF-8 deterministic, Markdown, Python stdlib/pytest;
FFmpeg/ffprobe và local tools chỉ metadata mapping.

---

## Task 1: Inventory and RED

- [x] Tạo worktree/branch từ main sau merge 26F.
- [x] Rà 30 G1 ID còn thiếu, partial capabilities, local tools và hardware;
  giữ `kinetic_typography` của 26D, không duplicate.
- [ ] Viết focused test exact tree/schema/IDs/locks.
- [ ] Chạy RED khi pack chưa tồn tại.

## Task 2: Local capability contract

- [ ] Tạo `local_capabilities.json` với đủ 30 IDs/order/count, refs, rights,
  local method và failure/validation.
- [ ] Ghi `inventory_snapshot` cho partial IDs để chống duplicate.
- [ ] Ghi tool policy, không cài dependency hoặc gọi package manager.

## Task 3: Delivery profiles

- [ ] Tạo 11 missing delivery/accessibility profiles.
- [ ] Giữ `subtitle_safe_area` và `mobile_legibility` inventory-only; không
  duplicate 26C/26D.
- [ ] Khóa flash/flicker, reduced-motion, mobile legibility và brand claims.

## Task 4: Heavy model inventory

- [ ] Tạo đủ 10 heavy model records với hardware/license evidence.
- [ ] Phân loại `DEFERRED`/`INSUFFICIENT_HARDWARE`; không tải model.

## Task 5: Verification and regression

- [ ] Chạy focused 26G và JSON/link/skill/static scans.
- [ ] Chạy regression 26C, 26D, 26E, 26F và test-module compile.
- [ ] Scope scan bằng `git status --short` và diff name; protected paths = 0.

## Task 6: Ship and handoff

- [ ] Review spec compliance và code quality.
- [ ] Commit, rebase latest main, push và mở PR 26G.
- [ ] Khi CLEAN/tests pass, merge commit tự động; ghi merge SHA/main SHA.
- [ ] Chỉ sau merge mới chuyển sang 26H; không deploy.
