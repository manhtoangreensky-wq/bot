# Local Video Studio 26F Viral Effects Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tạo mười viral-effect contracts nguyên bản, planning-only, nêu rõ
điều kiện footage, phương pháp local deterministic tham khảo, fallback và
trạng thái readiness mà không tạo runtime hay UI cũ.

**Architecture:** Một `SKILL.md` định tuyến tới `viral_effects.json`. JSON có
envelope và namespace `viral_effect.*`; mỗi record chứa toàn bộ source-shot,
mask/tracking, rights, validation và fixture semantics để không cần registry
Python. Focused tests đọc JSON/Markdown bằng stdlib và không import production.

**Tech Stack:** JSON UTF-8 deterministic, Markdown, Python stdlib/pytest,
FFmpeg/SVG/CSS chỉ metadata mapping, Git worktree/branch.

---

## Task 1: Inventory and RED

- [x] Xác nhận main base `908fd3c42ebfe87650bcb6221b789268a70b9d5c` và worktree
  riêng.
- [x] Search toàn repo theo mười ID và effect-specific keywords; phân loại
  hiện có/incomplete/missing.
- [ ] Tạo focused test với exact IDs, schema, locks và effect minimums.
- [ ] Chạy focused test khi pack chưa tồn tại; phải thấy RED đúng nguyên nhân.

## Task 2: Design documentation and skill routing

- [ ] Tạo `SKILL.md` frontmatter chỉ có `name`/`description` và link JSON,
  rights contract, 26D transition source và design spec.
- [ ] Ghi rõ UI/UX cũ không đổi; 26F không public UI, không runtime registry,
  không provider/AI execution và không asset.

## Task 3: Ten effect contracts

- [ ] Tạo envelope `viral_effects.json` với đúng 10 IDs/order/count.
- [ ] Mỗi record có đủ 19 nhóm semantics theo spec và bốn locks.
- [ ] Khóa effect-specific keys cho phone, segmentation, clone, morph,
  disappear, message, music, product và phone-drop.
- [ ] Ghi status truth rule và fallback không biến blocker thành success.

## Task 4: GREEN and static checks

- [ ] Chạy focused 26F; sửa contract, không làm yếu test.
- [ ] Parse JSON, kiểm tra deterministic two-space UTF-8/no BOM và relative links.
- [ ] Chạy quick skill validation, test-module compile, `git diff --check`,
  binary/network/secret/placeholder scan.

## Task 5: Regression and scope

- [ ] Chạy regression 26C, cả hai test 26D và focused 26E.
- [ ] Dùng `git status --short` cùng `git diff --name-only` để bảo đảm không
  có bot/UI/renderer/worker/provider/billing changes.
- [ ] Xác nhận counters provider/paid/wallet/Telegram/asset đều zero/NO.

## Task 6: Commit, PR, merge and handoff

- [ ] Spec-compliance và code-quality review độc lập.
- [ ] Commit một commit 26F, push branch và mở một PR.
- [ ] Khi PR CLEAN và tests pass, merge bằng merge commit; ghi merge SHA/main SHA.
- [ ] Chỉ sau merge mới chuyển inventory-first sang 26G; không deploy.
