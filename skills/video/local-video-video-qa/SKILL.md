---
name: local-video-video-qa
description: Use when Codex must lập kế hoạch kiểm định video local, render promise và no-fake-success bằng evidence rõ ràng.
---

# Kiểm định video local và no-fake-success

Pack clean-room này là contract planning-only; không phải renderer, runtime
registry, production validator hoặc public UI.

- [Video QA contract](video_qa_contract.json): đọc đúng 19 check, evidence,
  pass/fail, fixture và render-promise policy.
- [Rights contract](../local-video-filmmaking/rights_requirements.json): dùng
  đủ tám declaration trước khi chấp nhận artifact.
- [Audio QA 26E](../local-video-sound-design/audio_qa_contract.json) và
  [loudness profiles](../local-video-sound-design/platform_loudness_profiles.json):
  là source of truth cho loudness/true peak.
- [Delivery profiles 26G](../local-video-local-capabilities/platform_delivery_profiles.json):
  là source of truth cho aspect, delivery và accessibility.
- [Kinetic typography 26D](../local-video-transition-motion/kinetic_typography.json):
  là source of truth cho safe-area/readability của chữ.
- [Design spec](../../../docs/superpowers/specs/2026-07-29-localvideostudio26h-video-qa-design.md):
  xem inventory, boundary và acceptance.

## Quy trình

1. Nhận render promise: loại artifact, duration, dimensions, frame rate, audio,
   aspect, tên và output-size policy.
2. Thu evidence file/container/stream bằng helper và FFmpeg/ffprobe đã có; không
   xem HTTP 200, task ID hoặc output path là thành công.
3. Chạy logic theo thứ tự 19 check; thiếu evidence của blocking check thì
   FAIL_CLOSED.
4. Đối chiếu loudness/true peak với 26E, subtitle/delivery với 26D/26G và rights
   với 26C; không sao chép semantics.
5. Duplicated-scene chỉ tạo warning yêu cầu review để không loại intentional
   hold/repeat; thiếu evidence vẫn không được claim QA hoàn tất.
6. Fixture chỉ tạo trong temp directory từ nguồn local hợp pháp; không commit
   binary hoặc customer media.

Music/Suno luôn LOCKED_DISABLED. Không gọi provider, model, ví/Xu, Telegram,
renderer, worker hoặc deployment. Không thêm UI, nút hoặc route vào sản phẩm cũ.

Mọi record giữ planning_only=true, runtime_registered=false,
provider_executable=false, public_ui=false.
