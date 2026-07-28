---
name: local-video-local-capabilities
description: Use when Codex must bổ sung capability video local/free còn thiếu sau inventory, kèm delivery profile hoặc hardware model audit.
---

# Lập kế hoạch capability video local/free

Pack này là metadata/contract planning-only; không phải runtime registry, renderer,
public UI, worker hay installer.

- [Local capabilities](local_capabilities.json): 32 gap IDs G1, inventory snapshot
  và tool policy.
- [Delivery profiles](platform_delivery_profiles.json): aspect, delivery,
  accessibility, safe-area, retention và brand contracts còn thiếu.
- [Heavy model inventory](heavy_gpu_inventory.json): hardware/license audit cho
  model nặng, không cài hoặc tạo asset.
- [Rights contract](../local-video-filmmaking/rights_requirements.json): tám
  khai báo quyền dùng chung.
- [Design spec](../../../docs/superpowers/specs/2026-07-29-localvideostudio26g-local-capabilities-design.md):
  boundary và acceptance.

Quy trình: inventory trước, giữ capability đúng, chỉ thêm ID MISSING, ghi
fallback/evidence, giữ partial capability trong snapshot và fail closed khi
rights/runtime/hardware thiếu. FFmpeg/ffprobe chỉ là metadata mapping; Piper,
Whisper, PySceneDetect, Remotion, GSAP và Playwright chưa được coi là executable.

Không tự tải model nhiều GB, không gọi Motion/Higgsfield/provider, không sửa
UI/UX sản phẩm cũ hoặc wiring production, không mutate wallet/Xu và không
deploy. Mọi record giữ planning_only=true, runtime_registered=false,
provider_executable=false, public_ui=false.
