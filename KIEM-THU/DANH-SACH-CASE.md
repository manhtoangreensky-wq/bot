# Danh sách case Product Video và Public Landing

Nguồn gốc duy nhất cho acceptance live. Sửa case tại file này trước khi tạo/sửa Issue.

## Product Video Strategy V2 — correction gate đang mở

| ID | Mục đích | Flow khóa | PASS bắt buộc |
|---|---|---|---|
| `PV2-S04G1` | Đóng live RED job #26 trước matrix | Video AI chân thật manual -> Add-on -> Review -> tier 400 -> Invoice -> Confirm -> Status | strict Add-on chỉ `transitions`; `partial_addons=0`; MP4 2 cảnh 9:16/16s; receipt; report sau MP4; 0 Xu; callback trùng không gửi lại |

Runbook duy nhất: `KIEM-THU/runbooks/PV2-SPEC04G1-addon-report-rerun.md`.
Case correction này không thay thế representative phức tạp `PV2-R02`.

## 8 representative rows — lane phức tạp nhất mỗi product

Tất cả dùng tier `400` / `80 Xu/cảnh`; 7 row dùng 2 cảnh, riêng Kịch bản ->
Video dùng đúng 5 cảnh. Manual/direct-input không phải representative.

| ID | Product / lane khóa | Kịch bản khóa | Add-on khóa | PASS bắt buộc |
|---|---|---|---|---|
| `PV2-R01` | Video theo trend / `vtrend|video_upload` | Phân tích clip remote-work thành trend ly tái sử dụng: mở xe cà phê điện -> phục vụ sinh viên | phụ đề nguồn + chuyển cảnh | 2 cảnh, đúng trend owner, MP4/receipt/report/0 Xu |
| `PV2-R02` | Video AI chân thật / `vid3|mode|image_video` | Giữ đồng hồ mặt xanh nhất quán từ bàn lắp ráp -> hero shot nền tối | lồng tiếng mặc định + phụ đề nguồn | 2 ảnh map đúng cảnh, 2 clip, MP4/receipt/report/0 Xu |
| `PV2-R03` | Kịch bản -> Video / `vproduct|script_upload` | File 5 cảnh trà sen Tây Hồ: hái, tách gạo, ướp, pha, mời khách | voice + phụ đề + nhạc | giữ nguyên script, đúng 5 cảnh, MP4/receipt/report/0 Xu |
| `PV2-R04` | Ghép ảnh thành video / `framevideo|source|ai` | Tạo 2 ảnh ví da nâu nhất quán: khâu tại bàn -> ảnh thành phẩm | chữ + chuyển cảnh | 2 source-image tasks, Frame engine, MP4/receipt/report/0 Xu |
| `PV2-R05A` | Tự quay & đổi cảnh AI / `vproduct|selfshot_product|scene_change` | Giữ người thật và động tác gõ máy; đổi văn phòng thành rooftop cafe | âm thanh gốc + watermark | đúng source SHA `784FBE5B...`, 2 cảnh, identity/audio/receipt/report/0 Xu |
| `PV2-R05B` | Tự quay & biến đổi điện ảnh / `vproduct|selfshot_product|cinematic` | Giữ diễn xuất review; đổi trang phục, ánh sáng và thế giới từ studio sang neon cinema | âm thanh gốc + cinematic effects | đúng source SHA `3A53DA94...`, one-take contract, artifact/receipt/report/0 Xu |
| `PV2-R06` | Storyboard / `vstory|ai` | Robot trắng-xanh gieo hạt trên mái -> đứng cạnh mầm phát sáng lúc bình minh | phụ đề nguồn + chuyển cảnh | 2 source-image tasks/map, MP4/receipt/report/0 Xu |
| `PV2-R08` | Ý tưởng video / `videoidea|explore` | Phát triển ý tưởng xe cà phê điện: tới cổng trường -> barista phục vụ sinh viên | phụ đề nguồn | handoff đúng product, 2 cảnh, MP4/receipt/report/0 Xu |

## 9 quality-only rows — phân cho route tương thích

Tier `400` đã được 8 representative rows bao phủ. Mỗi row dưới đây dùng đúng 1
cảnh, không tạo job tier `400` riêng và không dồn quality coverage vào AI Real.

| ID | Tier | Product / lane khóa | Kịch bản khóa | PASS bắt buộc |
|---|---:|---|---|---|
| `PV2-Q200` | 200 | Ghép ảnh / uploaded image | Animate ảnh hero đồng hồ mặt xanh với camera move nhẹ | exact tier, 1 cảnh, artifact/receipt/report/0 Xu |
| `PV2-Q300` | 300 | Trend / latest catalog | Trend sân vườn năng lượng mặt trời kết thúc khi đèn bật | exact tier + audio, artifact/receipt/report/0 Xu |
| `PV2-Q500` | 500 | Trend / search | Gấp diều giấy sáng màu và reveal diều bay trên đê | exact tier, artifact/receipt/report/0 Xu |
| `PV2-Q600` | 600 | Ý tưởng video / explore | Xếp bộ trà gốm và rót trà bên cửa sổ mưa, âm thanh đồng bộ | exact tier + audio, artifact/receipt/report/0 Xu |
| `PV2-Q700` | 700 | Tự quay & đổi cảnh AI | Giữ người gõ máy qua chuyển đổi liên tục văn phòng -> rooftop hoàng hôn | exact tier + source audio, artifact/receipt/report/0 Xu |
| `PV2-Q800` | 800 | Tự quay & biến đổi điện ảnh | Biến review liên tục thành phòng lab nước hoa cao cấp | exact tier + audio, artifact/receipt/report/0 Xu |
| `PV2-Q1000` | 1000 | Video AI chân thật / prompt video | Vũ công khởi động trước gương rồi xoay dưới đèn sân khấu | exact tier, artifact/receipt/report/0 Xu |
| `PV2-Q1200` | 1200 | Video AI chân thật / image video | Từ ảnh đồng hồ bàn lắp ráp tạo camera move đa góc nhất quán | exact tier + source identity, artifact/receipt/report/0 Xu |
| `PV2-Q1500` | 1500 | Video AI chân thật / prompt video | Ga tàu mưa đêm, hai người gặp nhau dưới đồng hồ lớn | exact tier, artifact/receipt/report/0 Xu |

## Product/lane bị khóa hoặc hoãn

- `multi_scene_film` và `video_long`: loại khỏi chu kỳ. Không code, test provider,
  submit, deploy hoặc suy diễn PASS cho tới lệnh Owner mở Long Video.
- `video_local_edit`: sản phẩm đã khóa. Không sửa code/test/UI/route và không dùng
  làm quality probe.
- `videoedit|ai`: hoãn cùng Long Video.

## Bằng chứng bắt buộc cho mỗi paid row

- Case/scenario hoặc fixture hash riêng; không tái sử dụng idempotency key.
- REQUEST_ID, project, job và outbox đúng một lần.
- Scene outputs theo scene count khóa; final MP4 hash/bytes/codec/dimensions/duration.
- Audio stream + loudness khi row yêu cầu audio.
- Add-on requested/materialized/applied và `missing=[]`.
- Telegram video delivery message ID/file ID/file_unique_id.
- Customer report gửi sau receipt + settlement; lưu `delivery_report_message_id`
  và `delivery_report_sent=true`; không lộ provider/worker/job/SHA/manifest/JSON.
- `charged_xu=0`, transaction và credit-event count/max-ID delta 0.
- Duplicate callback không tạo job, delivery, settlement hoặc report thứ hai.

Canh lỗi riêng `PV2-R01`: provider-deferred job phải tôn trọng `next_poll_at`,
không tăng claim attempts trong cửa sổ chờ. Controlled fallback đã khóa scene 1
không được lan sang scene 2; scene index, scene marker và Key4U candidate phải cùng
khớp trước submit. ShopAIKey task identity cũ không được đổi nhãn thành Key4U task.

## Public Landing Motion

| ID | Viewport/chế độ | PASS bắt buộc |
|---|---|---|
| ML-01 | `1440×900`, normal | Hero semantic opacity `1` từ 10ms; settle ≤`8px/360ms`; reveal once; parallax ≤`10px`; CLS/long task/overflow/error `0` |
| ML-02 | `768×900`, normal | Presentation motion `0`; nội dung/CTA/form đủ; overflow/error `0` |
| ML-03 | `390×667`, normal | Presentation motion `0`; nội dung/CTA/form đủ; overflow/error `0` |
| ML-04 | `360×640`, normal | Presentation motion `0`; nội dung/CTA/form đủ; overflow/error `0` |
| ML-05 | `1440×900`, reduced | Animation/parallax `0`; nội dung hiện; pending/error `0` |
| ML-06 | `390×667`, reduced | Animation/parallax `0`; nội dung hiện; pending/error `0` |

Evidence nguồn: `D:/TOANAAS/TOAN_AAS_WEB_APP/evidence/motion-landing-toanaas-001/r1/candidate-io-green-run-1/` và `candidate-io-green-run-2/`. GitHub Tester tracker: `manhtoangreensky-wq/bot#884`.

## SubDub — thứ tự acceptance khóa

Fixture hai giọng cho cả hai case đầu: `C:/Users/toann/Downloads/test sub/2 giọng nam nữ.mp4`,
`4,284,017` bytes, SHA-256 `85C8793D197CF2782BB554D46282E82A83BCB062A0483E412A0CA1DA668F9F51`.

Fixture nhiều giọng cho case cuối: `C:/Users/toann/Downloads/test sub/test nhiều giọng.mp4`,
SHA-256 `83DE97B744B931E544B569E6E750F8415545F226461BD2E36CFB49225898AD3E`.

| ID | Lane | Thiết lập khóa | PASS bắt buộc | Canh lỗi cũ |
|---|---|---|---|---|
| SD-2S-01 | Phụ đề + Lồng tiếng | English; Tự động 2 giọng; numeric UI chỉ 2 layer cùng hàng; nhập gốc 40%, lồng 150%; không preset | Chỉ tự gửi MP4 rồi receipt; SRT/audio/sidecar nội bộ; mọi cue dịch/TTS giữ start-end gốc, đo source/target rate + duration thật, drift 0; đúng 2 labels; speaker 0 male/low, speaker 1 female/high từ UVR+PANNs vote độc lập; giá phụ đề + lồng tiếng + total; admin 0 Xu; wallet delta 0 | `empty_transcript`; Key4U first response unavailable; httpx sync-stream/AsyncClient; cue sau bị đẩy bởi audio trước; video bị kéo dài; auto SRT dư; backing music làm whole-window cast manual; filter cũ trả sai high/high; raw-frame fallback bị cấm; model/hash/license/onnxruntime thiếu; FAIL nếu >2 Key4U attempts; preset grid quay lại |
| SD-2S-02 | Lồng tiếng video | Cùng fixture; Tự động 2 giọng; cùng numeric UI; gốc 40%, lồng 150%; không preset | MP4 + receipt; đúng 2 labels/cast; dubbing list price >0; admin 0 Xu; wallet delta 0 | Lane combo PASS nhưng standalone hồi quy; audio UI khác combo |
| SD-MS-01 | Phụ đề + Lồng tiếng / Tự động nhiều giọng — same-job continuation `#B4CB6D5FE8` | Chỉ fixture SHA `83DE97B...`; English; numeric gốc 40%, lồng 150%; không gửi lại recovery command đã consumed; chỉ fresh Owner authorization sau exact runtime; không upload/Confirm/job mới | Chính job giao MP4 → receipt, file phụ 0; fixed-vocal acoustic `3–8` speaker thật; số voice ID riêng = số speaker; không invented/merged label hoặc forced gender; mọi word/cue giữ start-end gốc, drift 0 và duration nguồn; giá >0 nhưng admin 0 Xu; job/transaction/wallet delta 0 | FAIL nếu active path gọi provider crosswalk/re-diarization hoặc nhận expected speaker count; ASR/VAD quyết định `k`; strict word timeline thiếu/sai; legacy sidecar được resume; model/hash/license/CPU provider sai; command cũ/lần hai; raw PCM/embedding/centroid/provider payload bị persist; SRT tự gửi; voice ID dùng lại; cue sau trễ; exact-two comparator/hash đổi |

### SubDub Auto multi — source/resource cases trước LIVE

| ID | Bằng chứng phải chạy | PASS bắt buộc |
|---|---|---|
| `SD-MS-L01` | Strict word timeline | Deepgram nondiarized word list nonempty; runtime malformed/zero-duration/duplicate bị reject; resource sanitation ghi đúng `48` upstream zero-duration rows đã drop; mọi retained word giữ index/start/end và được cue coverage đúng `1` lần |
| `SD-MS-L02` | Real fixed-vocal acoustic fixture | Model `26,534,127` bytes/SHA `9FEA6516...056A1`, CPU-only; UVR vocal fixed windows give `5` speakers, `50` words, `23` units, `178` embedding views, clusters `[9,18,26,25,11]`, coverage `[3,2,4,11,3]`, cosine min `0.990487`; call `139.76s < 300s` |
| `SD-MS-L03` | Legacy sidecar force-fresh | Provider/crosswalk/underclustered sidecar hoặc bundle thiếu acoustic model/algorithm/media/timeline authority không được reuse và không được chuyển thẳng sang TTS |
| `SD-MS-L04` | Valid acoustic resume | Bundle acoustic đầy đủ, cùng source/timeline/model/algorithm được reuse với ASR call delta `0`; cue/voice/timing authority không đổi |
| `SD-MS-L05` | Final same-job CAS | Chỉ internal `b4cb6d5fe8a7bdfce507`, exact SHA/English/40/150/no-output/no-charge; attempt `3/2 -> 4/3` đúng một winner; attempt `5`, duplicate và concurrent loser đều no-op |

Mỗi MP4 phải đo SHA-256/bytes/duration/dimensions/codec và AAC loudness; job id
hoặc HTTP 200 không được tính PASS. Sửa case tại file này trước khi tạo/sửa
GitHub Issue.

Canh lỗi bổ sung cho `SD-MS-01` sau live 31/08/2026: recovery của cùng job chỉ
được có `1` progress message và edit message đó qua mọi stage; `2` terminal HTTP
`200 completed` rỗng phải đi tới attempt thứ `3`, nhưng không được có attempt thứ
`4`; correction chỉ thắng CAS đúng `1` lần, engine job count không tăng và
`charged_xu` luôn bằng `0`. Missing safety field, bất kỳ artifact/delivery path hoặc
message ID, hay response có nonzero raw `word_info` dù parser reject đều phải chặn
correction.

Legacy-only comparator: nếu failure xảy ra trước khi hai raw fields được deploy,
ordinary command vẫn phải bị chặn. Override chỉ PASS khi có literal
`--confirm-observability-gap`, cả hai fields cùng thiếu, mọi safety field explicit,
marker chưa dùng; partial raw evidence hoặc lần override thứ hai phải FAIL.
Literal legacy trên first recovery với raw evidence complete hoặc partial cũng phải
FAIL, không được chuyển thành ordinary recovery.
Parser evidence comparator: raw count may be stored only as an aggregate. Never
persist annotation text, speaker labels, timestamps, raw response or key. A `151`
raw / `5` canonical-label response with one singleton may filter exactly `1` weak
word only when weak total ≤`2` words and ≤`2%`, leaving `3–8` strong labels. Mapper
must still cover every cue; a cue whose only evidence is the filtered label must
FAIL. Two strong labels remain `speaker_count_out_of_range`; missing fields,
unbounded weak fraction and conflicting identity require distinct rejection.

Fixed-vocal comparator 02/09/2026 supersedes word/VAD-region speaker-count
authority for the active Auto Multi path. Speaker count is `3–8`, selected before
ASR word mapping from fixed vocal windows without hint. Four energy percentile
views must agree on `k`; the `47.5/50` core partition must match exactly after
numeric-label alignment. Model mutation/missing notice, `k>8`, unstable views,
missing word/speaker coverage, legacy sidecar or wrong-lane dispatch must fail
before TTS/mux/charge. Offline `k=5` is required for `SD-MS-L02`, but production
code must not contain a fixture hash branch or hard-coded expected `k`.

Comparator UI bổ sung: `2` lane × `6` kiểu giọng (nữ mặc định, nam mặc định,
Kho voice, voice riêng, Auto 2, Auto multi) phải cùng callback
`videodub|audio_mix`, cùng ba callback màn chính và cùng numeric range.

Comparator cast bổ sung: exact fixture phải ghi `speaker_0=male/low`, vote
`7/8`, dominance `0.875`, evidence `21s`; `speaker_1=female/high`, vote `8/10`,
dominance `0.800`, evidence `27s`. Tổng evidence unique không vượt `48s` và
provider calls cho classifier bằng `0`. Một code path chỉ PASS nam/nữ nhưng
fail male/male hoặc female/female là forced pairing và phải FAIL case.
