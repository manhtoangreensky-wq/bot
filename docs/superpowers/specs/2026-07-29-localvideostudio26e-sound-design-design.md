# Local Video Studio 26E — Sound Design and Audio Post Pack

## Phạm vi và ranh giới

TASK 26E bổ sung một bộ hợp đồng âm thanh nguyên bản, tiếng Việt, dùng để lập
kế hoạch và kiểm tra tĩnh. Bộ này không phải audio renderer, FFmpeg filtergraph,
worker, runtime registry, callback, state machine, menu hay sản phẩm public.
Không sửa `bot.py`, Product Video, SubDub, renderer, worker, Railway, VPS,
PayOS, wallet/Xu, DB, webhook hoặc Music/Suno.

Nhánh duy nhất là `feat/p1-localvideostudio26e-sound-design`, tách từ merge
main của 26D tại `87c9febe853343e09a29de45ac24f7cf2a6225a5`. PR 26E sẽ được mở
nhưng không merge và không deploy trong task này.

## Mục tiêu đã duyệt

Pack phải mô tả đúng mười sound layer, mười bốn audio-post operation, chín
khai báo timeline theo scene, năm cấu hình loudness theo ngữ cảnh sử dụng và
mười kiểm tra audio QA. Mỗi capability có ID duy nhất trong group, mô tả rõ
đầu vào, timing, quyền, rủi ro, fallback và bằng chứng kiểm tra. Dialogue luôn
được ưu tiên hơn music hoặc sound effect.

Mọi capability record có các khóa bất biến; capability envelope giữ đúng bảy
field schema và không lặp các khóa này. Ba contract loudness/timeline/QA giữ
bốn khóa ở top-level:

```json
{
  "planning_only": true,
  "runtime_registered": false,
  "provider_executable": false,
  "public_ui": false
}
```

Readiness chỉ dùng `CONTRACT_ONLY`, `LOCAL_PLANNING_READY`, `REQUIRES_RUNTIME`
hoặc `NOT_SUPPORTED`; không dùng nhãn production-ready. `EXISTING_AND_VALID`
chỉ ghi nhận primitive/metadata hiện có, còn operation thiếu hoặc chưa đủ
semantics phải ghi `EXISTING_BUT_INCOMPLETE` hoặc `MISSING` trung thực.

## Clean-room và chống trùng hành vi

Nội dung được viết mới từ yêu cầu owner, inventory read-only của TOAN AAS và
kiến thức audio phổ quát. Không sao chép OpenMontage, Motion.so, Higgsfield,
tutorial hay source bên thứ ba. Namespace 26E là `sound_layer.*` và
`audio_post_operation.*`; các cue `impact`, `riser`, `whoosh` chỉ mô tả vai
trò layer. Khi cue gắn với biên chuyển, phải tham chiếu contract 26D
`transition_audio.json`, không chép lại timing/gain semantics của 26D.

Music/Suno giữ trạng thái `LOCKED_DISABLED`: không tạo, thu nạp hoặc phát hành
asset nhạc chưa được cấp quyền. Không có audio binary, URL, mã gọi mạng, lệnh
thu nạp asset hoặc khóa bí mật trong pack.

## Cấu trúc file được phép

```text
skills/video/local-video-sound-design/
├── SKILL.md
├── sound_layers.json
├── audio_post_operations.json
├── platform_loudness_profiles.json
├── sound_timeline_contract.json
└── audio_qa_contract.json

docs/superpowers/specs/2026-07-29-localvideostudio26e-sound-design-design.md
docs/superpowers/plans/2026-07-29-localvideostudio26e-sound-design.md
tests/test_p1_localvideostudio26e_sound_design.py
```

Không thêm runtime registry, Python module, preset production hoặc file tài sản
vào thư mục skill.

## Schema và ID chính xác

`sound_layers.json` dùng envelope `schema_version`, `pack_id`, `group_id`,
`capability_count`, `rights_contract_ref`, `music_suno_policy`,
`capabilities`. Group là `sound_layer`, count là 10, theo thứ tự:
`dialogue_or_narration`, `room_tone`, `ambience`, `foley`, `impact`, `riser`,
`whoosh`, `transition_accent`, `music_bed`, `silence`.

Mỗi layer giữ thứ tự field cố định: `id`, `qualified_id`, `display_name_vi`,
`purpose_vi`, `required_inputs`, `timing_guidance`, `level_guidance`,
`interaction_rules`, `rights_requirement_ids`, `avoid_when`, `failure_modes`,
`validation_checks`, `existing_capability_refs`, `inventory_status`,
`readiness`, bốn khóa bất biến.

`audio_post_operations.json` dùng cùng envelope, group `audio_post_operation`,
count 14, theo thứ tự: `dialogue_cleanup`, `noise_reduction`,
`high_pass_filter`, `de_essing`, `compression`, `limiting`, `normalization`,
`music_ducking`, `crossfade`, `fade_in_out`, `stereo_balance`,
`mono_compatibility`, `loudness_measurement`, `true_peak_check`. Record dùng
`required_inputs`, `parameter_contract`, `order_constraints`,
`intelligibility_policy`, `fallback`, `failure_modes`, `validation_checks`,
metadata references, inventory/readiness, rights và locks.

`platform_loudness_profiles.json` không dùng envelope capability. Nó khai báo
`short_form_social`, `long_form_video`, `spoken_word_video`, `podcast_stereo`,
`podcast_mono`; `universal_target_allowed` luôn false và mỗi profile bắt buộc
có cấu hình platform riêng, target LUFS-I, true-peak ceiling, kênh và ghi chú.

`sound_timeline_contract.json` khai báo đúng chín field scene:
`dialogue`, `ambience`, `foley`, `impact`, `riser`, `whoosh`, `music_cue`,
`ducking_envelope`, `silence_window`. Mỗi field có keys bắt buộc, quy tắc
validation và đủ rights IDs.

`audio_qa_contract.json` khai báo đúng mười check:
`audio_stream_present`, `decodable_duration`, `silence_ratio`, `clipping`,
`loudness`, `true_peak`, `dialogue_intelligibility`, `channel_layout`,
`mono_compatibility`, `timeline_alignment`. QA fail-closed: stream im lặng,
clipping hoặc thiếu evidence không bao giờ là success. FFmpeg/ffprobe chỉ là
mapping metadata; không được chạy trong 26E.

## Inventory mapping hiện có

References chỉ là path tương đối, tracked và `relationship=metadata_only`.
Mỗi reference có đúng thứ tự `path`, `symbols`, `support_layer`,
`relationship`, `notes_vi`; `path` tính từ repository root, dùng dấu `/` và
không chứa `..`. Python symbols phải là tên top-level; JSON reference dùng
qualified ID của contract nguồn.
Các primitive hiện hữu được trích dẫn có chọn lọc:

- `services/audio_postprocess.py`: `AudioBoostResult`, `boost_voice_audio`
  — voice boost/limiter, chưa đủ cleanup và đo lường.
- `services/frame_video_runtime.py`: `FrameVideoCommand`,
  `build_ffmpeg_command`, `probe_mp4` — metadata FFmpeg, không gọi.
- `services/video_local_validation.py`: `find_ffmpeg`, `find_ffprobe`,
  `probe_video_file`, `validate_mp4_output` — kiểm tra container/stream cơ bản.
- `services/video_postprocess_pipeline.py`: `VideoPostprocessPlan`,
  `VideoPostprocessResult`, `probe_duration`, `process_video_postprocess_plan`
  — mix metadata và target hiện hữu, chưa có platform profiles.
- `services/video_edit_capabilities.py`: `CAPABILITIES`, `capability`,
  `audio_source_truth` — catalog metadata.
- `services/video_scene3_flow.py`: `AUDIO_POST_ADDONS`,
  `POST_ADDON_DEFAULTS`, `configure_audio_volume`, `finalize_audio_planning`,
  `initialize_scene_artifacts`, `preconfirm_audio_side_effects` — planning
  hooks hiện hữu, không đăng ký thêm.
- `services/multiscene_video_pipeline.py` và `services/video_local_editing.py`
  — timing/edit metadata, không thay pipeline.

Các operation noise reduction, high-pass, de-essing, compression, loudness và
true-peak chưa có runtime hoàn chỉnh; phải ghi thiếu/incomplete, không claim
executable. Mức loudness `-16` hiện có chỉ là default cũ, không được dùng như
một target universal.

Inventory/readiness đã khóa:

| Nhóm | `EXISTING_AND_VALID` | `EXISTING_BUT_INCOMPLETE` | `MISSING` |
|---|---|---|---|
| Layer | `dialogue_or_narration` | `impact`, `riser`, `whoosh`, `transition_accent`, `music_bed`, `silence` | `room_tone`, `ambience`, `foley` |
| Operation | `limiting`, `fade_in_out` | `normalization`, `music_ducking`, `crossfade`, `mono_compatibility` | `dialogue_cleanup`, `noise_reduction`, `high_pass_filter`, `de_essing`, `compression`, `stereo_balance`, `loudness_measurement`, `true_peak_check` |

Layer taxonomy hoàn toàn thiếu dùng `CONTRACT_ONLY`; cue có contract planning
hoặc primitive an toàn dùng `LOCAL_PLANNING_READY`; operation còn thiếu phép
xử lý/đo dùng `REQUIRES_RUNTIME`. Readiness không phải trạng thái production.

Collision được tách namespace và nguồn canonical:

| 26E | Contract 26D |
|---|---|
| `sound_layer.impact` | `transition_audio.impact` |
| `sound_layer.riser` | `transition_audio.riser` |
| `sound_layer.whoosh` | `transition_audio.whoosh` |
| `sound_layer.silence` | `transition_audio.silence_cut` |
| `audio_post_operation.music_ducking` | `transition_audio.music_duck` |
| `sound_layer.transition_accent` | catalog của `transition_audio.json` |

26E chịu trách nhiệm vai trò layer, scene placement và QA. Timing/gain/ducking
tại biên chuyển vẫn thuộc 26D; không reference cue bằng ID không namespace.

## Quyền, timeline và no-fake-success

Mọi capability tham chiếu đúng
`../local-video-filmmaking/rights_requirements.json` và đủ tám ID:
`source_ownership`, `license`, `brand_restrictions`, `face_person_consent`,
`music_rights`, `font_rights`, `stock_attribution`,
`ai_generated_asset_disclosure_metadata`. Giá trị quyền `UNKNOWN` hoặc
`RESTRICTED` giữ kế hoạch và chặn thực thi. Timeline phải phân biệt silence có
chủ đích với stream bị mất tiếng. Dialogue intelligibility phải được kiểm tra
trước music ducking. QA cần bằng chứng waveform/ffprobe/loudness tương ứng;
HTTP, task ID, đường dẫn rỗng hoặc file im lặng không phải bằng chứng.

## Verification và acceptance

Focused test phải kiểm tra đúng file/count/order/uniqueness/schema, rights
linkage, locks, tiếng Việt, metadata references, links, deterministic UTF-8,
không asset/mã thu nạp/secret và fail-closed QA. Chạy focused 26E, regression
26C và cả hai test 26D, JSON parse, relative-link check, quick skill validation,
compile test modules, `git diff --check` và scan secret/placeholder/binary.

Counters phải giữ: provider calls 0, paid generations 0, wallet mutations 0,
Telegram deliveries 0, bundled/downloaded audio NO. UI/UX, Product Video,
SubDub, renderer/audio runtime, worker, VPS và Railway đều NO CHANGE. Lỗi
contrast tại `/video-studio/story-video-plan` không thuộc phạm vi 26E và được
ghi nhận cho task UI riêng sau khi các gate 26A–26I/27A cho phép.
