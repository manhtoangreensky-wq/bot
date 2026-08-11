# Video Planning Assistant MVP Design

## Approval

Owner approved the Product Architect recommendation on 2026-08-11: the public planning entry is a feature named `🧭 Lên kế hoạch chỉnh sửa`, with a small saved-plan library inside it. It is not a Video Edit engine, not a Product Video flow, and not a standalone project-management product.

## Product promise

The feature turns a user's editing intention into a structured, plain-Vietnamese plan that can be saved and reopened. It does not accept media or execute edits.

The public distinction is fixed:

- Product Video creates new video content.
- Video Edit executes changes against real media.
- Video Planning prepares an editing plan before execution.

## Public flow

```text
Menu Video
→ 🧭 Lên kế hoạch chỉnh sửa
→ Mục tiêu
→ Mô tả mong muốn bằng tiếng Việt
→ Nền tảng và tỷ lệ
→ Thời lượng video nguồn
→ Thời lượng thành phẩm
→ Tài nguyên đang có
→ Ưu tiên (nhịp, sản phẩm, ánh sáng, âm thanh, nhận diện)
→ Hạng mục được trợ lý đề xuất và người dùng xác nhận
→ Quyền và lưu ý
→ Bản kế hoạch
→ Lưu kế hoạch / Gửi kế hoạch vào chat / Kế hoạch của tôi
```

Single-choice screens advance immediately. Multi-choice screens remain on the same screen until the user presses `Tiếp tục`. Back always returns to the exact preceding screen. Root Back is labelled `⬅️ Menu Video` because that is the real parent route.

## Structured plan

Every plan contains:

```text
plan_id
plan_schema_version
title
goal
editing_brief
platform_ratio
source_duration
target_duration
available_assets[]
priorities[]
selected_operations[]
ordered_steps[]
rights_notes[]
created_at
updated_at
```

The public report uses user language only. It must not expose capability IDs, readiness enums, provider names, paths, task/job IDs, FFmpeg commands, SHAs, secrets, or internal execution terms.

The assistant is a deterministic local adviser for this MVP. It translates guided priorities and safe keywords from the user's brief into proposed operations, then asks the user to confirm them. It does not call an AI/provider. It preserves time ranges and segment instructions supplied by the user, but it never invents timestamps or claims to have analyzed media. If the user did not provide exact keep/remove ranges, the plan says that the best segment must be selected during execution.

Example output:

```text
Cắt đoạn thừa → tăng nhịp → chỉnh khung 9:16 → thêm watermark → cân âm lượng
```

If the user enters `Bỏ 00:00–00:08; giữ sản phẩm 00:08–00:28`, those instructions are kept in the ordered plan. Without that input, the planner may recommend `Chọn và giữ đoạn sản phẩm rõ nhất`, but may not create fake seconds.

## Saved-plan library

The library is a supporting screen inside the assistant. It provides only:

- create/save;
- list;
- open;
- update by saving the reopened plan;
- delete after confirmation.

Storage is a dedicated lightweight SQLite table owned by the planning feature. Ownership is enforced by `user_id` and `chat_id`; updates use an optimistic version and delete is a soft delete. Only normalized plan business data and a public summary snapshot are stored. Telegram screen/history/callback state is never written to the table. Plans never create Product Video projects, Video Edit jobs, invoices, receipts, outbox records, or wallet mutations.

## YAGNI exclusions

The MVP intentionally excludes:

- media upload or media analysis;
- timeline editing;
- provider, worker, FFmpeg, job, invoice, status, delivery or charging;
- Product Video Production Bible, prompts, scenes, quality packages or render submission;
- Video Edit handoff until a separate task proves a real supported mapping;
- version history, duplication, collaboration, share links, PDF/DOCX export;
- cost estimation and AI-generated recommendations.

## Compatibility and safety

- Keep callback namespace `lvs27b`, `PREVIEW_VERSION=27B`, the four approved goals and the existing feature flag. Use a separate integer `plan_schema_version` for durable plan payload evolution. Preserve the old capability adapter as legacy internal evidence; the public bot imports the new pure `video_planning_assistant` service under the existing adapter alias so only one `lvs27b` handler remains registered.
- Keep the capability index internal and read-only; public screens use curated Vietnamese operation labels.
- Keep ordinary session transaction ordering: compute → deliver → commit → answer.
- For the explicit `Lưu kế hoạch` action, durable idempotent persistence must succeed before public copy may say `Đã lưu`. If the Telegram confirmation cannot be delivered, the already-saved plan remains owner-scoped and a retry resolves to the same plan instead of creating a duplicate.
- Duplicate callbacks must not create duplicate plans or duplicate chat summaries.
- Feature OFF permits only Back/Close for an already open session.
- Provider calls and wallet mutations remain exactly zero.
