# Local Video Studio 26F — Ten Viral Effect Specifications

## Phạm vi đã duyệt

26F tạo một pack đặc tả viral-effect nguyên bản, tiếng Việt, planning-only.
Pack không sửa UI/UX của Product Video, SubDub hoặc sản phẩm cũ; cũng không
thêm public menu, callback, state, backstack, renderer, worker hay provider
route. Quyền xây UI/UX mới chỉ áp dụng khi có task sản phẩm mới riêng và không
được mở rộng vào 26F. Trong 26F, không có public UI và không có prototype
runtime vì inventory không tìm thấy preset system local an toàn cho mười hiệu
ứng.

Nhánh duy nhất: `feat/p1-localvideostudio26f-viral-effects`, tách từ main sau
merge 26E tại `908fd3c42ebfe87650bcb6221b789268a70b9d5c`. PR 26F sẽ được mở,
owner workflow cho phép tự merge sau khi mọi gate pass; không deploy và không
bắt đầu 26G cho tới khi report 26F hoàn tất.

## Nguồn và inventory

Inventory read-only tìm thấy transition/motion, filmmaking và sound-design
contracts hiện hữu, nhưng không thấy `phone_magic`, `colour_fill`,
`clone_throw`, `outfit_morph`, `clone_thief`, `music_scroll`, `product_popup`
hoặc `phone_drop` dưới dạng effect contract. Các từ `disappear` và
`text_message` chỉ xuất hiện trong metadata/storyboard cũ, không đủ camera,
plate, mask, tracking, rights và validation semantics; không tái sử dụng như
capability hoàn chỉnh.

Không có local preset registry được inventory chứng minh cho các hiệu ứng này.
FFmpeg, SVG/CSS và metadata của 26C–26E chỉ là mapping tham khảo. Không cài
model/GPU lớn, không gọi AI, không dùng Motion/Higgsfield và không tạo asset.

## Cấu trúc file

```text
skills/video/local-video-viral-effects/
├── SKILL.md
└── viral_effects.json

docs/superpowers/specs/2026-07-29-localvideostudio26f-viral-effects-design.md
docs/superpowers/plans/2026-07-29-localvideostudio26f-viral-effects.md
tests/test_p1_localvideostudio26f_viral_effects.py
```

Không thêm Python registry, preset production, binary, customer media, UI
component hoặc asset bundled vào thư mục skill.

## ID và schema

`viral_effects.json` có envelope theo thứ tự:
`schema_version`, `pack_id`, `group_id`, `capability_count`,
`rights_contract_ref`, `music_suno_policy`, `ai_assist_policy`,
`capabilities`. Group là `viral_effect`, count là 10, theo đúng thứ tự:

`phone_magic`, `colour_fill`, `clone_throw`, `outfit_morph`, `clone_thief`,
`disappear`, `text_message`, `music_scroll`, `product_popup`, `phone_drop`.

Mỗi record định nghĩa: display name, creative intent, source-shot setup, camera
lock, clean plate, mask, tracking, pose/hand/object continuity, aspect ratios,
duration, beat markers, local deterministic method, optional AI method disabled,
fallback, known failures, validation và fixture specification. Record có
`status` thuộc đúng một trong:

`READY_FROM_ARBITRARY_FOOTAGE`, `REQUIRES_PLANNED_SHOOT`,
`REQUIRES_MASK_TRACK`, `PROTOTYPE_ONLY`, `BLOCKED`.

Mọi record cũng có `inventory_status`, `readiness`, đủ tám rights ID và bốn
planning locks:

```json
{
  "planning_only": true,
  "runtime_registered": false,
  "provider_executable": false,
  "public_ui": false
}
```

Không effect nào được gắn `READY_FROM_ARBITRARY_FOOTAGE` khi thiếu camera,
plate, mask hoặc tracking. `optional_ai_assisted_method.enabled` luôn false;
AI method chỉ là mô tả bị khóa, không phải đường chạy.

## Effect-specific contract

- `phone_magic`: phone/screen tracking, screen replacement, perspective corner
  pin, glow/reflection và hand occlusion.
- `colour_fill`: subject/object segmentation, animated reveal, edge feather,
  spill prevention và color-accessibility.
- `clone_throw`: locked/solved camera, clean plate, nhiều pass, trajectory,
  occlusion order và shadow consistency.
- `outfit_morph`: matched pose/framing, segmentation, transition mask,
  body/cloth edge continuity; fallback match cut.
- `clone_thief`: multi-pass compositing, object handoff, clean plate, layer
  order và object mask/tracking.
- `disappear`: clean plate, subject mask, optional particles/smoke/light,
  shadow removal và background continuity.
- `text_message`: message UI recreation, privacy redaction, typing/reveal,
  notification sound policy và platform-neutral/brand-rights gate.
- `music_scroll`: waveform/beat map, scroll direction, cover-art rights,
  lyric display blocked without rights và no unlicensed song extraction.
- `product_popup`: product cutout, shadow, pricing/claim validation,
  callout labels, brand safe area và CTA timing.
- `phone_drop`: motion tracking, impact point, screen transition, object
  continuity, optional camera shake và hard-cut fallback.

## Rights, safety và no-fake-success

Mọi record liên kết `../local-video-filmmaking/rights_requirements.json` và
đủ `source_ownership`, `license`, `brand_restrictions`, `face_person_consent`,
`music_rights`, `font_rights`, `stock_attribution`,
`ai_generated_asset_disclosure_metadata`. UNKNOWN/RESTRICTED giữ planning-only
và block execution. Music/Suno `LOCKED_DISABLED`; không lyric, cover art,
notification sound hay effect asset nào được coi là hợp lệ nếu quyền chưa xác
minh.

Validation phải fail-closed khi thiếu plate, marker, mask, tracking, rights,
privacy redaction, claim evidence hoặc fixture evidence. JSON, effect name,
task ID, output path hoặc HTTP response không phải bằng chứng effect đã chạy.

## Verification và acceptance

Focused tests kiểm tra exact IDs/count/order, schema/field order, status enum,
effect-specific keys, rights linkage, local-only mapping, AI/Music locks,
reduced-motion/accessibility, no asset/network code, relative links và
deterministic UTF-8 JSON. Chạy focused 26F, regression 26C/26D/26E, JSON parse,
quick skill validation, compile test, `git diff --check` và scope scan.

Counters giữ nguyên: provider calls 0, paid generations 0, Motion calls 0,
Higgsfield calls 0, wallet/Xu mutations 0, Telegram deliveries 0, bundled or
downloaded assets NO. UI/UX sản phẩm cũ, Product Video, SubDub, renderer,
worker, VPS, Railway và billing không đổi.
