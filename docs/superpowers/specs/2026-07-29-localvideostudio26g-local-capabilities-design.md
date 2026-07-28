# Local Video Studio 26G — Additional Local/Free Capabilities

## Phạm vi

26G bổ sung các contract/skill local-free còn thiếu sau inventory, không sửa
implementation hiện hữu và không tạo route trả phí. Pack chỉ là planning,
metadata và readiness; không đăng ký runtime, không public UI, không thêm nút
vào sản phẩm cũ. Quyền xây UI/UX mới chỉ áp dụng cho task sản phẩm mới riêng;
26G không chứa UI.

Branch: `feat/p1-localvideostudio26g-local-capabilities`, base sau merge 26F là
`9d8f1ae2eb3bc16f8fce896b00d56096f6be9bf1`.

## Inventory delta và nguyên tắc không trùng

G1 tìm thấy 30 ID chưa có contract có cấu trúc: tám planning, sáu clip/edit,
bốn documentary/archive, ba screen-demo, bốn talking-head/subtitle và năm
animated-explainer. `kinetic_typography` đã là contract 26D; `reframing`,
`subtitle_safe_area` và `mobile_legibility` có metadata/contract partial ở
26C/26D. Các capability đã có chỉ ghi trong `inventory_snapshot`, không tạo
bản trùng.

FFmpeg/ffprobe có trên workstation. Piper, PySceneDetect, Whisper/WhisperX,
Remotion, GSAP và Playwright chưa được chứng minh là local executable trong
inventory này; không tự cài. SVG/Canvas chỉ là specification mapping.

## File tree được phép

```text
skills/video/local-video-local-capabilities/
├── SKILL.md
├── local_capabilities.json
├── platform_delivery_profiles.json
└── heavy_gpu_inventory.json

docs/superpowers/specs/2026-07-29-localvideostudio26g-local-capabilities-design.md
docs/superpowers/plans/2026-07-29-localvideostudio26g-local-capabilities.md
tests/test_p1_localvideostudio26g_local_capabilities.py
```

Không có Python registry, model, binary, asset bundled, downloader, provider
route hoặc production loader.

## Contract 1 — local capabilities

`local_capabilities.json` có envelope `schema_version`, `pack_id`, `group_id`,
`capability_count`, `capabilities`, `inventory_snapshot`, `local_tool_policy`
và bốn locks. Group `local_capability` có 30 record theo thứ tự G1 sau khi
loại `kinetic_typography` đã có ở 26D.

Mỗi record có `id`, display/purpose tiếng Việt, `inventory_status`, `readiness`,
`local_method`, `required_inputs`, `failure_modes`, `validation_checks`,
`existing_capability_refs`, `rights_requirement_ids` và bốn locks. Readiness
chỉ là `CONTRACT_ONLY`, `LOCAL_PLANNING_READY`, `REQUIRES_RUNTIME` hoặc
`NOT_SUPPORTED`; không claim production.

`inventory_snapshot` ghi các capability partial đã giữ nguyên và lý do không
duplicate. `local_tool_policy` ghi status của FFmpeg/ffprobe và các dependency
được phép nhưng chưa cài; không gọi package manager.

## Contract 2 — delivery/accessibility profiles

`platform_delivery_profiles.json` khai báo các profile thiếu:
`platform_delivery_profiles`, `9_16_short_form`, `16_9_long_form`,
`1_1_social`, `4_5_feed`, `thumbnail_keyframe_selection`, `hook_scoring`,
`retention_checkpoints`, `brand_consistency`, `accessibility`,
`flash_flicker_safety`. `subtitle_safe_area`, `mobile_legibility` chỉ nằm trong
inventory snapshot với status `EXISTING_BUT_INCOMPLETE` và reference 26C/26D.

Mỗi profile có aspect/delivery rules, mobile/readability/accessibility checks,
fallback và readiness. Flash/flicker safety luôn fail-closed; reduced-motion
không được bỏ qua.

## Contract 3 — heavy/GPU inventory

`heavy_gpu_inventory.json` ghi đủ WAN, Hunyuan, CogVideo, LTX local, Stable
Diffusion, Real-ESRGAN, CodeFormer, GFPGAN, SadTalker và Wav2Lip cùng GPU
model, VRAM, RAM, disk free, CUDA/driver evidence, estimated size/runtime,
license và classification `SUPPORTED`, `INSUFFICIENT_HARDWARE`, `DEFERRED` hoặc
`LICENSE_BLOCKED`.

Workstation hiện là NVIDIA Quadro P1000 4096 MiB, RAM khoảng 31.8 GiB, driver
555.99; `nvidia-smi` không cung cấp CUDA runtime field đáng tin trong audit.
Không tải multi-gigabyte model nếu chưa có owner approval; classification của
mọi model nặng là `DEFERRED` hoặc `INSUFFICIENT_HARDWARE`.

## Rights và no-fake-success

Mọi capability liên kết tám rights ID của
`../local-video-filmmaking/rights_requirements.json`. UNKNOWN/RESTRICTED giữ
planning-only và block. Local method chỉ mapping metadata; HTTP, package install,
model generation, task ID hoặc output path không phải evidence thành công.

## Acceptance

Focused 26G phải kiểm tra exact IDs/count/order, no-duplicate snapshot, tool
status, profile fields, heavy-model classifications, rights/locks, relative
links, deterministic UTF-8 JSON và không asset/network/secret code. Chạy
regression 26C/26D/26E/26F, quick skill validation, compile test, `git diff
--check` và protected-scope scan.

Giữ provider calls, paid generations, Motion/Higgsfield calls, wallet/Xu,
Telegram deliveries, downloads và deployments ở 0/NO. Không merge task kế tiếp
cho tới khi 26G đã được merge và report.
