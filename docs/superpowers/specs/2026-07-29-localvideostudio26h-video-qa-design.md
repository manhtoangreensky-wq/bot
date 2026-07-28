# Local Video Studio 26H — Video QA and No-Fake-Success

## Phạm vi

26H tạo một contract QA video cục bộ, tái sử dụng được và fail-closed. Pack
chỉ mô tả evidence, pass/fail semantics, fixture hợp pháp và mapping tới helper
hiện hữu; không sửa validator, renderer, worker, bot, UI, callback, state hay
backstack production. Không provider, model, dịch vụ trả phí, ví/Xu, Telegram
hoặc deploy nào được gọi.

Branch: `feat/p1-localvideostudio26h-video-qa`, base sau merge 26G là
`4a2385dc90f0c55c90ad4145e558c23ba944ab68`.

## Inventory delta

Có đủ primitive hiện hữu cho bảy validation: file tồn tại, minimum bytes,
container, video stream, duration, dimensions và audio stream khi promise yêu
cầu. Frame rate đã được probe nhưng chưa được gate. Loudness/true peak đã có
contract 26E nhưng chưa có executor. Safe-area/readability/aspect/name/size và
render-promise có primitive hoặc metadata nhưng chưa thành một QA contract
đầy đủ. Black-frame, frozen-frame và visual duplicated-scene detection chưa có
executor; `duplicate_scene_result_prevented` của provider không phải visual QA.

26H không sao chép semantics đã có:

- loudness và true peak tham chiếu 26E;
- subtitle safe-area, delivery/aspect/accessibility tham chiếu 26G;
- subtitle readability tham chiếu kinetic typography 26D;
- rights dùng đủ tám declaration của 26C;
- helper Python production chỉ là `metadata_only`, không import hoặc gọi.

## File tree được phép

```text
skills/video/local-video-video-qa/
├── SKILL.md
└── video_qa_contract.json

docs/superpowers/specs/2026-07-29-localvideostudio26h-video-qa-design.md
docs/superpowers/plans/2026-07-29-localvideostudio26h-video-qa.md
tests/test_p1_localvideostudio26h_video_qa.py
```

Không có Python registry, production loader, binary media, customer media,
model, network client hoặc provider route.

## Contract shape

`video_qa_contract.json` có `group_id=video_qa`,
`contract_id=video_qa_no_fake_success` và đúng 19 checks theo thứ tự master
task. Mỗi check có ID/qualified ID, mô tả tiếng Việt, evidence, pass/failure
rule, severity, outcome, local-method mapping, failure modes, validation,
metadata references, rights, inventory/readiness và bốn planning locks.

Exact IDs:

```text
file_exists
file_size_minimum
container_valid
video_stream_exists
duration_positive
dimensions_valid
frame_rate_valid
audio_stream_when_promised
audio_loudness_valid
true_peak_valid
black_frame_detection
frozen_frame_detection
duplicated_scene_warning
subtitle_safe_area
subtitle_readability
aspect_ratio
delivery_filename
output_size
render_promise_verification
```

Mọi blocking check và mọi evidence bắt buộc đều fail-closed. Visual duplicated
scene là warning yêu cầu human review vì intentional hold/repeat có thể hợp lệ;
thiếu evidence để chạy check này vẫn không được claim QA hoàn tất.

## No-fake-success

Bảy trường hợp luôn bị từ chối: HTTP 200 đơn lẻ, task ID đơn lẻ, output path
rỗng, file zero byte, chỉ SRT khi promise MP4, audio-only khi promise MP4 và
MP4 hỏng. File path hoặc metadata không thay cho artifact đã probe. Success chỉ
có sau khi toàn bộ blocking checks có evidence phù hợp render promise.

## FFmpeg/ffprobe và fixtures

FFmpeg/ffprobe chỉ được ghi mapping metadata cho container/stream, LUFS/true
peak, blackdetect, freezedetect và frame sampling. `execution_in_26h_allowed`
luôn false vì 26H không đăng ký runtime. Fixture matrix chỉ dùng nguồn lavfi
hoặc metadata/file giả lập trong temp directory khi focused test cần; không
commit binary và không dùng customer media.

## Acceptance

Focused tests phải kiểm tra exact tree, exact 19 IDs/count/order, no-fake list,
fail-closed rules, references/symbols, 26C/26D/26E/26G linkage, Music/Suno
lock, ephemeral fixture policy, relative links, deterministic UTF-8 JSON, no
binary/network/secret/runtime code và four planning locks. Regression 26C–26G,
`git diff --check`, scope scan và secret/placeholder scan phải pass trước PR.

Provider/Motion/Higgsfield/paid calls, wallet/Xu mutations, Telegram delivery,
asset acquisition và deployments giữ 0/NO. Product Video, SubDub, renderer,
worker, VPS, Railway và UI/UX sản phẩm cũ không thay đổi.
