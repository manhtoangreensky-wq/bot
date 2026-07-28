---
name: local-video-codex-index
description: Use when Codex must tra cứu capability video đã cài, contract nguồn, cost class và readiness thực tế trước khi lập kế hoạch.
---

# Tra cứu capability Local Video Studio

Index này chỉ điều hướng tới source-of-truth; không chứa hoặc thay thế
implementation.

- [Capability index](capability_index.json): tra `capability_id`, qualified IDs,
  location, cost, required tools, confirmation và readiness.
- [Filmmaking 26C](../local-video-filmmaking/SKILL.md)
- [Transition/motion 26D](../local-video-transition-motion/SKILL.md)
- [Sound design 26E](../local-video-sound-design/SKILL.md)
- [Viral effects 26F](../local-video-viral-effects/SKILL.md)
- [Local/free capabilities 26G](../local-video-local-capabilities/SKILL.md)
- [Video QA 26H](../local-video-video-qa/SKILL.md)
- [Design spec](../../../docs/superpowers/specs/2026-07-29-localvideostudio26i-codex-index-design.md)

## Quy trình

1. Tìm record theo `capability_id` hoặc qualified capability ID.
2. Đọc `highest_readiness`; tuyệt đối không suy diễn `INSTALLED` thành
   `PRODUCTION_READY`, hoặc contract pass thành local demo.
3. Mở đúng `source_files`; không copy, fork hoặc tạo implementation trùng.
4. Kiểm tra local/cloud, free/paid, required tools, planned shoot và explicit
   confirmation trước khi đề xuất hành động.
5. `test_command` là evidence command, không phải quyền tự động chạy; giá trị
   `SKIP_PAID_SMOKE` phải giữ nguyên và không được thực thi.
6. Với OpenMontage, đọc `CODEX.md`, `AGENT_GUIDE.md` và `PROJECT_CONTEXT.md`
   tại external path trước pipeline; không nhập source vào bot repo.
7. Với Motion/Higgsfield/Suno, giữ paid-disabled/locked; không gọi generation,
   không dùng credit và không tự fallback.

Mọi record giữ planning_only=true, runtime_registered=false,
provider_executable=false, public_ui=false. Index không thêm UI/nút/route vào
sản phẩm cũ và không cho phép deploy.
