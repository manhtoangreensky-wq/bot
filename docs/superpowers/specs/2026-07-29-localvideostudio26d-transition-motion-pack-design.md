# Local Video Studio 26D — Transition and Motion-Design Pack

## Phạm vi và quyết định

TASK 26D tạo một skill pack nguyên bản, chỉ dùng để lập kế hoạch bằng tiếng
Việt. Pack không phải renderer, preset production, runtime registry, callback,
state machine, menu hoặc sản phẩm public. Không file production hiện hữu nào
được sửa.

Nhánh duy nhất:

`feat/p1-localvideostudio26d-transition-motion-pack`

Baseline đã fetch là `origin/main` tại
`89ff8ea547103f7434ef677b63cb3970c90ed845`. Đây là merge commit của PR #569
và chứa cả đặc tả 26C `7f77c5ea87c6459c16184edb004615d6d11d12e1`
lẫn implementation 26C `da4c8b8e2f9e24233ff5b232dfb17f08c42c8a95`.

Tree 26D được phép tạo:

```text
skills/video/local-video-transition-motion/
├── SKILL.md
├── transition_grammar.json
├── motion_design_principles.json
├── kinetic_typography.json
└── local_implementation_mapping.json

docs/superpowers/specs/
└── 2026-07-29-localvideostudio26d-transition-motion-pack-design.md

docs/superpowers/plans/
└── 2026-07-29-localvideostudio26d-transition-motion-pack.md

tests/
└── test_p1_localvideostudio26d_transition_motion_pack.py
```

Không sửa `bot.py`, UI, nút, callback, state, backstack, Product Video,
SubDub, renderer, worker, provider, Railway, VPS, PayOS, wallet/Xu, DB,
webhook, billing hoặc Music/Suno. Không bắt đầu 26E.

## Nguồn và clean-room

Nội dung được viết mới từ ID và yêu cầu do owner cung cấp, inventory chỉ đọc
của TOAN AAS, kiến thức dựng/motion phổ quát và quy tắc motion-kit của
workspace. Không sao chép OpenMontage, Motion.so, Higgsfield, transcript hướng
dẫn hoặc source của bên thứ ba.

Mọi record giữ bốn khóa bất biến:

```json
{
  "planning_only": true,
  "runtime_registered": false,
  "provider_executable": false,
  "public_ui": false
}
```

Readiness của pack chỉ có `CONTRACT_ONLY`, `LOCAL_PLANNING_READY`,
`REQUIRES_RUNTIME`, `REQUIRES_PLANNED_SHOOT` hoặc `NOT_SUPPORTED`. Không trạng
thái nào đồng nghĩa local preview pass, production ready hoặc public.

## Kiến trúc tĩnh

`SKILL.md` định tuyến yêu cầu sang đúng một hoặc nhiều JSON. Ba file capability
lưu ngữ pháp chuyển cảnh, nguyên lý motion và kinetic typography.
`local_implementation_mapping.json` ghi mapping kỹ thuật nhưng không import,
khởi tạo hay gọi công nghệ nào. Focused test chỉ đọc Markdown/JSON bằng Python
standard library.

```text
Yêu cầu lập kế hoạch
  -> chọn capability theo group
  -> kiểm tra footage/quyền/accessibility
  -> kiểm tra continuity, duration, failure và fallback
  -> đọc mapping kỹ thuật như metadata
  -> trả kế hoạch planning-only

Không job -> không render -> không provider -> không wallet -> không UI
```

Quyền dùng tài sản không được lặp schema. Pack liên kết read-only tới
`../local-video-filmmaking/rights_requirements.json` và yêu cầu đủ tám ID đã
khóa trong 26C.

## Namespace và chống trùng hành vi

Owner bắt buộc `mask_reveal` ở cả transition và kinetic typography. Đây là hai
hành vi khác nhau: một cái nối shot A/B, một cái hé lộ glyph/dòng chữ. Vì vậy
khóa duy nhất là cặp `(group_id, id)` và mỗi record có `qualified_id`:

- `transition.mask_reveal`
- `kinetic_typography.mask_reveal`

`match_motion` đã tồn tại trong 26C ở phạm vi camera/movement. Bản 26D chỉ mô
tả ranh giới nối hai shot và dùng `qualified_id=transition.match_motion`.
Không sao chép hay thay thế capability 26C.

## Envelope và ID chính xác

Ba file capability có envelope:

```json
{
  "schema_version": "1.0.0",
  "pack_id": "local-video-transition-motion",
  "group_id": "transition",
  "capability_count": 20,
  "rights_contract_ref": "../local-video-filmmaking/rights_requirements.json",
  "capabilities": []
}
```

### Transition — 20

`hard_cut`, `cross_dissolve`, `dip_to_black`, `dip_to_white`, `slide`, `push`,
`whip_pan`, `speed_ramp`, `match_motion`, `match_shape`, `match_color`,
`object_wipe`, `foreground_occlusion`, `zoom`, `light_flash`, `blur`, `glitch`,
`mask_reveal`, `split_screen`, `parallax_transition`.

Mỗi transition bắt buộc định nghĩa: shot đầu vào tương thích, hướng chuyển động,
khoảng thời lượng, easing, motion blur, mask/tracking, audio accent, fallback,
failure conditions và validation. `hard_cut` có duration bằng 0; mọi transition
khác phải có khoảng hữu hạn với min không âm và max không nhỏ hơn min.

### Motion-design principles — 12

`timing_and_spacing`, `easing`, `anticipation`, `follow_through`, `overlap`,
`squash_and_stretch`, `arcs`, `staging`, `secondary_action`, `exaggeration`,
`appeal`, `motion_hierarchy`.

Mỗi principle phải nêu ứng dụng, restraint, giới hạn footage, accessibility,
reduced-motion, fallback và validation. Không principle nào được hứa biến
footage bất kỳ thành animation tự nhiên.

### Kinetic typography — 10

`word_emphasis`, `line_build`, `type_reveal`, `mask_reveal`,
`tracking_animation`, `scale_punch`, `rotation_accent`, `highlight_box`,
`subtitle_to_title_promotion`, `beat_synced_type`.

Mỗi record bắt buộc có cấu trúc riêng cho readability, safe area, mật độ ký tự
tối đa, contrast, mobile legibility, no-flashing, reduced-motion, timing,
fallback, failure và validation. Pack cấm flashing; không dựa vào màu đơn độc
để truyền nghĩa.

## Mapping kỹ thuật cục bộ

Mapping dùng đúng bảy technology ID:

`remotion`, `gsap`, `hyperframes`, `ffmpeg`, `svg`, `canvas`,
`css_transforms`.

Inventory tại baseline:

- FFmpeg/ffprobe hiện diện và repo có primitive fade/dissolve/slide/zoom.
- Không tìm thấy dependency/runtime Remotion, GSAP hoặc HyperFrames trong repo.
- SVG, Canvas và CSS transforms là target mô tả; không có runtime 26D được
  đăng ký.

Mỗi capability scoped phải có một mapping. Technology vắng mặt vẫn được ghi
`NOT_INSTALLED` và không được nâng readiness. Quan hệ luôn `metadata_only`.
Không cài dependency và không sửa renderer.

## Inventory semantics

Mỗi record dùng vocabulary:

`EXISTING_AND_VALID`, `EXISTING_BUT_INCOMPLETE`, `MISSING`, `DUPLICATE`,
`PAID_DISABLED`, `GPU_BLOCKED`, `LICENSE_BLOCKED`, `NOT_APPLICABLE`.

`EXISTING_AND_VALID` chỉ nói repository đã có primitive hoặc metadata phù hợp,
không nói capability production đã hoàn chỉnh. Mapping tới file Python/JSON
hiện hữu là đường dẫn relative, tracked và `metadata_only`; focused test không
import file đó.

## Cổng quyền, accessibility và no-fake-success

Mọi capability liên kết đủ tám rights ID của 26C. `UNKNOWN` hoặc `RESTRICTED`
giữ planning-only và chặn thực thi. `NOT_APPLICABLE` phải có lý do.

Mỗi capability phải có reduced-motion behavior. Kinetic typography cấm flash,
giữ chữ trong safe area theo profile đích, giới hạn mật độ bằng rule có thể đo,
kiểm tra contrast trên frame đại diện và ưu tiên khả năng đọc trên mobile.

Không coi JSON hợp lệ, mapping kỹ thuật, tên preset, task ID hay đường dẫn file
là bằng chứng video đã được tạo. Fallback không được bỏ qua footage, quyền,
accessibility hoặc QA blocker.

## Focused test plan

1. Kiểm tra đúng năm file skill, không có runtime file.
2. Kiểm tra đúng ID/thứ tự/count 20/12/10 và unique theo group.
3. Chỉ cho phép collision base ID `mask_reveal`; mọi `qualified_id` phải unique.
4. Kiểm tra exact field order, tiếng Việt không rỗng và bốn khóa planning.
5. Kiểm tra transition có đủ chín nhóm semantics do owner yêu cầu.
6. Kiểm tra duration, hard-cut zero, easing, blur, mask/tracking và fallback.
7. Kiểm tra principles có restraint/footage limits/reduced-motion.
8. Kiểm tra toàn bộ kinetic records có sáu guard readability/accessibility.
9. Kiểm tra 42 mapping scoped, bảy technology ID và trạng thái cài đặt trung
   thực; không executable mapping.
10. Kiểm tra rights linkage dùng đúng tám ID 26C.
11. Kiểm tra reference relative/tracked/metadata-only và symbol Python hợp lệ.
12. Kiểm tra JSON UTF-8, không BOM, format hai dấu cách và Markdown link hợp lệ.
13. Quét secret, URL, provider task, callback/state/backstack/runtime wiring.
14. Chạy focused 26D, regression 26C, compile test module và `git diff --check`.

## Acceptance

26D đạt khi contract/tests pass, PR 26D được mở và để nguyên OPEN; không merge,
không deploy, không bắt đầu 26E. Provider/Motion/Higgsfield/paid generations,
wallet mutations, Telegram deliveries, production deploy và VPS updates đều 0.
UI/UX, Product Video, SubDub, renderer và worker đều không đổi.
