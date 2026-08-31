# Product Video: chức năng gốc và hiện tại

## Tài liệu giai đoạn trước

Nguồn đối chiếu:

1. `docs/superpowers/specs/2026-08-20-product-video-real-output-design.md`
2. `docs/reports/TOAN_AAS_2H_SYSTEM_AUDIT_20260616.md`
3. `docs/architecture/TOAN_AAS_GATE_CALLBACK_STATE_MAP_20260616.md`

## Đối chiếu

| Chức năng gốc | Hiện tại | Trạng thái |
|---|---|---|
| Video AI Prompt -> Add-on -> tier -> invoice -> confirm -> job | Tail hiện khóa 6 màn Add-on, Review, Quality, Invoice, Confirm, Status | Còn dùng, đã mở rộng |
| Video AI Prompt và Ảnh là hai lane riêng | Public product giữ `video_ai_real`; executor tách `video_ai_prompt` / `video_ai_image` | Còn dùng |
| Add-on giữ theo draft và materialize sau render | Tail/session giữ content, asset, add-on và owner snapshot | Còn dùng |
| Tier Video AI cũ tập trung 300/400 | Video AI Chân thật hiện có 10 tier: 200..1500 theo catalog | Tài liệu cũ không còn đủ |
| Frame dùng renderer riêng | Frame vẫn có 3 quality và pricing/engine riêng | Còn dùng, không được fallback Video AI |
| Long video public guard cũ | `multi_scene_film` có planner/Tail riêng; live output vẫn cần matrix mới | Dùng khác, live pending |

## Chỗ tài liệu cũ không còn đúng

- `docs/reports/TOAN_AAS_2H_SYSTEM_AUDIT_20260616.md:30,40` mô tả chủ yếu tier `300/400`; source hiện có 10 tier công khai cho Video AI Chân thật.
- `tests/test_p0_video_tail_confirm_logo_idea_backstack.py:56` đòi Logo/Summary trước Quality; Owner contract hiện tại là Add-on -> Review -> Quality -> Invoice -> Confirm -> Status.
- `docs/architecture/TOAN_AAS_GATE_CALLBACK_STATE_MAP_20260616.md:33` ghi `longvideo|start` planning-only; route hiện tại của `multi_scene_film` thuộc UIFLOW3/Tail và live output vẫn pending.
- Một số test cũ so tier theo thứ tự số; catalog hiện sắp theo giá/copy, vì vậy contract đúng là đủ đúng tập tier và đúng identity.

## Không có trong tài liệu cũ

- Lane tự nhập phải đi thẳng Tail sau khi provider-free planner dựng đủ cảnh.
- Asset gate fail-closed cho Frame/Storyboard/Self-shot và Video AI Ảnh.
- Service guard từ chối forged/unsupported tier trước state mutation.
- Durable parent snapshot để Back đúng owner sau bot restart.
- Full live matrix 9 lane + 10 tier với artifact/receipt/0 Xu.

## Rác hoặc bất nhất đã thấy

- 11 assertion baseline trong 2 test contract cũ đã fail y hệt trên `origin/main cd4acb8`; chưa sửa trong task này để tránh lan man.
- GitHub CLI local có token hết hiệu lực; chưa tạo label/Issue/Project thật. Tracker trong branch đang là nguồn tiến độ có thể đọc trên GitHub.

## Đối chiếu Public Landing — Motion 26/08/2026

Nguồn ban đầu đã tìm thấy: `index.html` tại base `5a4f942bc0b2e8820a96c5772ddb6372f1648604`; mẫu AI Suite Home/Login và NGOCTINCO chỉ là nguồn kỹ thuật chuyển động, không phải nguồn nội dung.

| Chức năng ban đầu | Hiện tại | Trạng thái |
|---|---|---|
| Hero giới thiệu và CTA Workspace/Telegram | Giữ nguyên URL/copy; semantic content luôn opacity `1`, chỉ settle `8px/360ms` một lần | ✅ Còn dùng |
| Các section nội dung hiện mặc định | Vẫn fail-open; chỉ section dưới fold nhận pending | ✅ Còn dùng |
| Form gửi JSON tới `/lead` | Không đổi endpoint, payload hoặc source authority | ✅ Còn dùng |
| Tablet/mobile/reduced-motion | Nội dung hiện ngay, không presentation motion | ✅ Đã khóa bằng test |
| Landing tĩnh không có parallax | Thêm parallax riêng `.workflow-preview`, desktop-only, tối đa `10px` | ⚠️ Mở rộng presentation |

Chỗ tài liệu cũ không còn đúng: dòng nói GitHub CLI hết hiệu lực đã lỗi thời; ngày 26/08/2026 `gh auth status` xác nhận tài khoản đăng nhập, issue Tester Landing là `#884`. Tài khoản hiện thiếu scope `read:project`, nên chưa gắn issue vào GitHub Projects; tracker issue vẫn là phiên Tester có ID/link.

## Đối chiếu SubDub tự động 2 giọng — 27/08/2026

Nguồn thiết kế trước: `docs/superpowers/plans/2026-08-14-subdub-per-speaker-auto-gender-cast.md`.

| Chức năng gốc | Hiện tại | Trạng thái |
|---|---|---|
| ASR Deepgram tạo cue và speaker label | Auto lane bắt buộc request diarization có speaker fields; fail-closed trước TTS nếu thiếu | ✅ Còn dùng |
| Deepgram model dùng chung từ `AgentDeepgram.REQUEST_PARAMS` | Default/manual giữ `nova-2`; auto diarized override call-scoped thành `nova-3-general` | ⚠️ Tách theo năng lực |
| Auto 2 giọng và multi dùng chung cast contract | Exact-two dùng local UVR + PANNs ONNX trên stereo PCM và tự vote từng speaker; raw-frame fallback bị loại; multi module vẫn byte-locked trên owner riêng | ⚠️ Cô lập exact-two, multi chưa LIVE PASS |
| Admin không trừ Xu | Receipt vẫn phải hiển thị đủ giá niêm yết; settlement admin `charged_xu=0` | ✅ Còn dùng |
| Âm lượng chọn bằng các nút phần trăm cố định | PR #896 thêm `10` preset là regression; hiện dùng hai layer cùng một hàng và nhập số gốc `0–100`, lồng `0–200` | ❌ Bỏ preset, giữ numeric |
| Mỗi kiểu giọng có bảng âm thanh riêng | Cả `2` lane và `6` kiểu giọng dùng chung một audio owner; test ma trận `12` case | ⚠️ Tài liệu cũ không còn đúng |
| TTS nối tiếp có thể đẩy cue sau và kéo dài video để giữ hết câu dịch | Exact 2-speaker đo đơn vị nói của câu gốc/câu dịch trên timestamp ASR, yêu cầu provider speed tối đa `1.8x`, đo duration TTS thật rồi `atempo`/pad riêng từng cue; start/end cue và duration nguồn bất biến | ❌ Bỏ drift tích lũy |
| Combo Auto tự gửi thêm SRT sau MP4 | SRT vẫn là artifact gắn phụ đề/QC và tải chủ động; success path chỉ tự gửi MP4 rồi receipt | ❌ Bỏ file delivery dư |

Chỗ tài liệu/code cũ không còn đúng: request diarization trước live job
`#EE4E7E69CD` kế thừa `model=nova-2`. Fixture Mandarin hai người có audio đo
được nhưng provider trả empty transcript. Source hiện override duy nhất
`bot.py:subdub_deepgram_request_params(require_diarization=True)` sang
`nova-3-general`; default route không đổi. LIVE output vẫn pending cho tới khi
có MP4 Telegram thật.

Chỗ UI cũ không còn đúng: ảnh/bảng preset `Gốc 20–100%` và `Lồng 80–200%` là
code thêm tại PR #896, không phải baseline được Owner khóa. Bằng chứng Git cho
thấy pre-#896 đã có callback nhập số; production rollback hiện chỉ xóa `32`
dòng preset/action và đổi `public_fixed_percentage_grid=True → False`. Các
numeric callback, pending state, mux, pricing, wallet và engine không đổi.

GitHub tester cloud readback ngày 28/08/2026: `gh label list --limit 60` trả đúng
`21` labels: `5` trạng thái, `4` mức độ, `3` loại và `9` mặc định; `gh issue
list --limit 10 --state all` trả 2 issues (`#884`, `#81`). Repo có 4 issue
templates tách Product Video/SubDub; chưa tạo SubDub issue mới trong correction
này. Case local dưới `KIEM-THU/` là nguồn chuẩn. `gh project list` chưa đọc được
vì token thiếu `read:project`; không tự chạy `gh auth refresh` và chưa tuyên bố có
Projects board khi chưa có readback.

## Đối chiếu Product Video provider/giá — 27/08/2026

Nguồn mới đã đối chiếu:

1. `config/product_video_price_route_map_20260827.json`
2. `docs/knowledge/PRODUCT_VIDEO_PRICE_ROUTE_MAP_20260827.md`
3. `https://api.shopaikey.com/pricing`
4. `https://key4u.vn/api/pricing_v3`
5. `https://api.key4u.vn/v1/models`

| Chức năng/tài liệu cũ | Hiện tại | Trạng thái |
|---|---|---|
| Key4U base `api.key4u.shop` | Dùng `api.key4u.vn`; `.shop` không còn là endpoint vận hành | Không còn đúng |
| Một generic JSON contract cho mọi video family | VEO dùng multipart; Kling và Hailuo dùng JSON/poll family riêng | Không còn đúng |
| Kling v3 đọc như giá mỗi lần tạo | Giá live tính theo giây; chi phí phải nhân đúng thời lượng cảnh | Không còn đúng |
| Tier 400 ưu tiên Key4U VEO | ShopAIKey VEO Fast `4.550 VND/2 cảnh` đứng trước Key4U `21.151 VND/2 cảnh` | Đã đổi route |
| Tier 800 có ShopAIKey Grok fallback | Chưa đủ artifact audio/pro-motion 10 giây nên không đủ điều kiện route | Bị loại khỏi route |
| Snapshot provider 11/08 quyết định runtime | Chỉ giữ làm lịch sử dựng giá khách; file map 27/08 quyết định runtime | Không còn đúng |

Giá khách hiện hành vẫn là `80`, `110`, `160`, `200`, `220`, `220`, `370`, `370`, `1.260`, `2.360` Xu/cảnh. Không được suy lại giá khách từ chi phí provider mới; mọi đổi giá hoặc thứ tự route phải sửa file map trước, có URL/timestamp bằng chứng rồi chạy comparator. LIVE vẫn pending cho tới khi từng lane/tier giao MP4 thật 2 cảnh có audio, add-on, receipt và `0 Xu`.

## Đối chiếu `NOT_START` và durable fallback — 27/08/2026

| Chức năng/tài liệu cũ | Hiện tại | Trạng thái |
|---|---|---|
| Không có final path thì báo renderer unavailable | Provider task còn `NOT_START` phải giữ pending/poll với nguyên nhân thật | Không còn đúng |
| `automatic_fallback_allowed=false` chặn mọi đường fallback | Vẫn chặn fallback ngầm; final confirm + exact quote + primary task thật được một Key4U fallback idempotent cho mỗi scene | Đã làm rõ |
| Worker claim/recovery có thể dùng generic retry count | Existing provider task chỉ poll; controlled fallback có khóa riêng; không resubmit primary và không chạm wallet | Đã khóa bằng test |

Bằng chứng là PV-L01 job `22`: hai ShopAIKey task thật, `0/2` clip, terminal `provider_not_start`, `charged_xu=0`. Source correction có focused `6 passed`, protected `51 passed`, `NEW_FAILURES=0`; LIVE output vẫn pending.

Live job `23` bổ sung một bất nhất mới: route snapshot ghi provider chain đầy đủ, worker readiness cũng có ShopAIKey + Key4U, nhưng trường job-level `provider_order` chỉ còn ShopAIKey nên fallback list rỗng. Hiện tại policy phục hồi duy nhất Key4U từ readiness/capability cục bộ sau khi primary task đã stall và mọi gate xác nhận/quote/idempotency đạt; missing confirm hoặc quote lệch vẫn bị test chặn.

## Đối chiếu SubDub failure loop sau PR #904

| Chức năng gốc | Hiện tại | Trạng thái |
|---|---|---|
| Deepgram là nguồn duy nhất cho transcript + diarization Auto | Deepgram vẫn chạy trước; exact 2-speaker mới có fallback Key4U Whisper cue + Gemini Transcribe diarization khi Deepgram trả empty | ⚠️ Mở rộng có điều kiện |
| Key4U ASR dùng `api.key4u.shop/v1` | Runtime canonical dùng `api.key4u.vn/v1`; `.shop` lỗi TLS certificate và không được bypass verify | ⚠️ Tài liệu hostname cũ sai |
| Auto multi và Auto 2 giọng dùng cùng request diarization | Multi vẫn Deepgram-only và byte-locked; fallback mới không được forward khi `auto_speaker_lane=multi` | ✅ Cô lập theo Owner |
| Speaker labels đến từ provider, classifier chỉ đọc acoustic evidence theo label | Key4U cung cấp `18` cue timestamp; Gemini cung cấp `125` timed speaker words; mapping thời gian tạo đúng `2` labels trước classifier | ✅ Giữ nguyên trách nhiệm |

Chỗ tài liệu cũ không còn đúng: dòng khẳng định Deepgram là provider duy nhất
không còn đủ cho lane 2. Bằng chứng fixture hiện tại cho thấy Deepgram HTTP `200`
nhưng transcript/word/speaker đều `0`, trong khi Gemini Transcribe trả đúng `2`
speaker và `125` timed annotations. Đây không mở fallback cho multi/default/manual
và không thay classifier/cast/audio/pricing/wallet.

Bẫy đã khóa sau review: chỉ chấp nhận Key4U segments có `provider_timestamps=true`
và đầy đủ timestamp thật; fallback luôn ghim riêng `https://api.key4u.vn/v1`;
parser Gemini chỉ đọc `steps[].content[].annotations[]` có `type=word_info`;
video dài phải chunk (>5 phút ở Auto) dừng `AUTO_CAST_UNAVAILABLE` trước mọi
Key4U/Gemini fallback call.

### Đối chiếu retry Key4U transcript — 28/08/2026

| Chức năng cũ | Hiện tại | Trạng thái |
|---|---|---|
| Key4U fallback gọi đúng một lần rồi fail manual | Exact 2-speaker confirmed job được tối đa 2 attempts khi lần đầu empty/retryable | ⚠️ Sửa theo live evidence |
| Mọi lỗi Key4U đều có thể retry | HTTP 401 và response có segment nhưng thiếu timestamp provider dừng ngay | ✅ Fail-closed |
| Retry có thể áp cho multi/default/manual | Chỉ cờ exact two-speaker fallback mới vào owner này; multi/default/manual giữ zero fallback | ✅ Cô lập |

Chỗ tài liệu cũ không còn đúng: one-shot Key4U không đủ trước transient response
đã đo trên job `#00911B6FF0`. Diagnostic ngay sau đó chứng minh cùng
`whisper-1 verbose_json` trả `18` timed segments; do đó bounded retry nằm
trong fallback boundary, không phải thay classifier hoặc ép speaker.

Chỗ transport cũ cũng không còn đúng: multipart `data=list[tuple]` tạo sync
request stream và bị `httpx.AsyncClient` từ chối trước HTTP. Hiện form dùng
`dict`, giữ nguyên các field `model/response_format/
timestamp_granularities[]/language`; regression test dùng real MockTransport,
không giả adapter.

Live job `24` cho thấy connector policy đúng vẫn chưa đủ nếu server claim gate terminal hóa trước worker. Hiện claim transaction tính controlled-fallback eligibility trước ledger terminal decision và chỉ miễn đúng fallback Key4U đã xác nhận; `automatic_resubmit_allowed=false` vẫn chặn submit lại primary. Job/artifact/receipt LIVE vẫn pending.

### Đối chiếu acoustic cast karaoke sau job `#6DC569C0A6`

| Chức năng/tài liệu cũ | Hiện tại | Trạng thái |
|---|---|---|
| Hai speaker labels đồng nghĩa classifier đủ evidence | Job có `18` cue, đúng `2` labels nhưng raw full-mix whole-window pitch vẫn manual-required do backing music | ❌ Không còn đủ để PASS |
| Engine hai giọng phải byte-for-byte PR #842 mãi mãi | Raw-frame fallback đã bị review bác và xóa; exact-two dùng local UVR + PANNs ONNX trên stereo PCM, còn shared pitch/multi owner giữ nguyên | ⚠️ Authority exact-two được thay bằng evidence thật |
| Filter giọng #853 giúp nhận diện nam/nữ | Comparator trên fixture thật trả `high/high`; filter bị cấm ở lane 2 và chỉ còn là owner riêng của multi | ❌ Sai trên fixture acceptance |
| Nam/nữ được suy ra bằng cách ép hai label thành hai giới | Mỗi label tự vote male/female rồi map `male=low`, `female=high`; male/male, male/female, female/female đều được test; tie/weak fail-closed | ✅ Không forced pairing |

Chỗ tài liệu gốc không còn đúng: câu “exact Git blob PR #842 là toàn bộ engine
hiện tại” không còn đúng cho authority exact-two. Source correction gọi service
UVR + PANNs ONNX chỉ khi đúng lane hai speaker; không đổi
`subdub_speaker_cast.py`, `auto_multi_speaker.py`, PCM filter, provider,
pricing hay wallet.

### Đối chiếu sau Auto 2-speaker LIVE PASS — 28/08/2026

| Chức năng/tài liệu cũ | Hiện tại đo được | Trạng thái |
|---|---|---|
| MP4 đã giao một lần nghĩa là lane hai giọng đã xong | Chỉ khóa sau combo job `#3A3BEA618D` và standalone `#282347E26C` cùng giao MP4 thật + receipt, không file phụ, trên runtime `e819c1cd...` | ✅ Hai lane LIVE PASS |
| Ghép TTS nối tiếp để không mất chữ dịch | Mỗi cue đo source/target speech rate, provider speed tối đa `1.8x`, fit bằng `atempo`/pad trong chính cue; boundary và final duration nguồn bất biến | ❌ Cơ chế nối tiếp cũ bị bỏ |
| Combo Auto phải gửi thêm SRT | SRT `18` cue là artifact nội bộ/QC hoặc tải chủ động; automatic delivery là MP4 → receipt | ❌ File tự động dư bị bỏ |
| Có hai speaker thì buộc một nam, một nữ | Mỗi speaker vote độc lập; fixture live ra male/low `7/8` và female/high `8/10`, nhưng male–male/female–female vẫn hợp lệ nếu evidence đạt | ❌ Không forced pairing |
| Admin `0 Xu` nên dubbing price có thể bằng `0` | Combo vẫn niêm yết subtitle `61`, dubbing `75`, total `136`; standalone dubbing/total `77`; chỉ settlement là `charged_xu=0` | ❌ Không còn giá lồng tiếng giả 0 |
| Back/status và create-voice có thể tái dùng copy generic | Hai callback đúng nhưng nhãn live sai; PR `#922` đổi đúng `2` dòng, `5` UI/audio tests; deploy/runtime `2fd989e...` đã readback | ✅ Đã khóa runtime |

GitHub tester surface đo ngày 28/08/2026 vẫn có `21` labels, issue `#884` và
`#81`, `2` template SubDub, `3` case `SD-2S-01/SD-2S-02/SD-MS-01`; Projects
chưa đọc được vì token thiếu `read:project`. Không tự chạy `gh auth refresh`.

### Đối chiếu Auto multi-speaker source — 29/08/2026

| Chức năng/tài liệu cũ | Hiện tại đo được | Trạng thái |
|---|---|---|
| Auto multi không dùng cue-lock của Auto 2 | Marker multi dùng cùng speech-rate/per-cue fit/source-duration owner; manual/default vẫn không bật | ⚠️ Source PASS, chờ live |
| Combo multi tự gửi MP4 rồi SRT | Cả combo và standalone multi success chỉ tự gửi MP4 rồi receipt; SRT internal/explicit download | ⚠️ Source PASS, chờ live |
| Hai provider label đủ đại diện nhiều người nói | Acceptance fixture refined có `36` cue, đúng `3` label; sidecar `2` label bị loại underclustered | ❌ Tài liệu cũ không đủ |
| Một test English đủ chứng minh nhiều ngôn ngữ | Adapter giữ target/translate marker cho `vi`, `ja`, `en`, `ko`, `zh`; live representative vẫn chạy English | ⚠️ Mở rộng source contract |
| Multi có thể sửa classifier/cast lane 2 để dùng chung | Exact-two files/hashes giữ nguyên; multi chỉ dùng shared timing/delivery seam | ✅ Lane 2 vẫn khóa |

Source evidence: final focused `23 passed`; protected effective `82 passed` +
đúng `3` baseline failures, `NEW_FAILURES=0`; provider/wallet mutation `0`.
Chưa có deployed multi MP4 thì không được ghi `LIVE PASS`.

#### Đối chiếu failure live `#7C4BE502C0`

| Chức năng/tài liệu cũ | Hiện tại đo được | Trạng thái |
|---|---|---|
| Deepgram PASS nghĩa là diarization đủ cho Auto multi | Deepgram `listen/PASS` tạo sidecar `32` cue nhưng chỉ `2` label; multi terminal `AUTO_CAST_MANUAL_REQUIRED`, `0 Xu`, chưa TTS/mux/artifact | ❌ HTTP/provider PASS không phải multi PASS |
| Có thể tách label thiếu bằng cao độ | Pitch/register chỉ là thuộc tính giọng, không phải identity; cách này có thể bịa người khi một người đổi pitch hoặc có nhạc nền | ❌ Bị loại sau independent review |
| Fallback Key4U+Gemini chỉ tồn tại cho exact 2-speaker | Exact fallback vẫn khóa nguyên byte; multi có adapter re-diarization riêng sau final-confirm, không truyền speaker count và chỉ nhận `3–8` label | ⚠️ Mở rộng cô lập |
| Provider lặp word annotation không ảnh hưởng | Mọi word identity được canonicalize/dedup; conflict speaker trên cùng word/timestamp làm fail-closed trước overlap mapping | ✅ Cổng identity mới |
| Multi cast cần classifier pitch riêng | Multi tái dùng UVR+PANNs authority đã ship qua adapter `3–16` label, chung lock/budget nhưng không sửa exact-two files | ✅ Tái sử dụng engine khóa |
| Audio provider preprocessing có thể làm đồng bộ trên event loop | PCM streaming chunk `1 MiB`, conversion + JSON worker thread, một admission lock; concurrent job fail trước allocation/call | ❌ Cơ chế cũ không an toàn tải |

Bằng chứng hiện tại: protected matrix `135 passed + 14 subtests`; exact provider
baseline/branch cùng `49 passed`, `NEW_FAILURES=0`; changed-file compile/diff exit
`0`; review độc lập Critical `0`, Important `0`. Merge/deploy/runtime/combo MP4/
standalone MP4 vẫn là các cổng riêng.

#### Đối chiếu failure live `#22B138532B` — 30/08/2026

| Chức năng/tài liệu cũ | Hiện tại đo được | Trạng thái |
|---|---|---|
| File ID mới tự động tạo toàn bộ phiên Auto mới | Fresh file identity đã đổi nhưng `5` field private `auto_exact_*` vẫn sống trong pending dict | ❌ Tài liệu cũ sai |
| Có `auto_exact_resume=true` luôn nghĩa là genuine resume | Chỉ đúng khi tiếp tục cùng nguồn; upload nguồn mới phải xóa resume authority trước khi merge fields | ⚠️ Đã sửa source boundary |
| Receipt cũ hoặc provider PASS đủ để bỏ qua re-diarization | Job mới Deepgram PASS/`32` cue nhưng chỉ `2` label; vẫn phải chứng minh `3–8` label cho multi | ❌ Không phải multi PASS |
| Có thể xóa toàn bộ voice state khi đổi nguồn | Correction chỉ xóa `5` private fields; giữ `auto_speaker_lane=multi`, voice mode và âm gốc/lồng `40/150` | ✅ Phạm vi tối thiểu |
| Fix boundary có thể thay đổi resume thật | Comparator genuine resume vẫn không gọi re-diarization; `3` focused tests PASS | ✅ Resume thật được bảo vệ |

Bằng chứng correction: RED `1 failed in 5.60s`; focused GREEN `1 passed in
520.48s`; multi protected `53 passed`; exact-two/audio `82 passed`; exact-two
hashes `2/2` nguyên vẹn; branch/baseline cùng đúng `3` failure ID nên
`NEW_FAILURES=0`; compile/YAML/diff/scope/secret exit `0`; provider/wallet `0`.
Tester surface local có `4` templates và `3` SubDub cases. Docs/Strategy V2 có
`8 passed` + đúng `1` baseline fixture-hash failure tái hiện trên clean HEAD.
Chưa deploy và chưa có MP4 mới nên trạng thái vẫn là source-local ready.

#### Đối chiếu failure live `#DB4FFFD7F6` — 30/08/2026

| Chức năng/tài liệu cũ | Hiện tại đo được | Trạng thái |
|---|---|---|
| `AUTO_CAST_MANUAL_REQUIRED` nghĩa là direct multi provider chưa được gọi | Durable job/manifest cũ làm rơi attempted/provider/status/http/detail/counts; direct outcome của job `#DB4FFFD7F6` vì thế là `UNKNOWN` | ❌ Không được suy từ field thiếu |
| Telegram progress timeout là root failure | Journal chỉ có best-effort progress warning; terminal authority là cast manual-required sau sidecar `32` cue/`2` label | ❌ UI warning không phải root |
| Terminal generic đủ để điều tra provider | Correction giữ đúng `8` field bounded ở manifest + durable terminal và loại `api_key`, raw response, credentials/provider payload | ⚠️ Source diagnostics ready |
| Có diagnostics mới nghĩa là output đã được sửa | Provider request/retry/mapping/TTS/mux không đổi; combo vẫn chưa có MP4 và standalone chưa được chạy | ❌ Chỉ là evidence seam |
| Có thể dùng lại lệnh live cũ để rerun | Authorization tạo job `#DB4FFFD7F6` đã được dùng; job mới cần Owner action-time confirmation mới sau deploy | ✅ Chốt side effect |

Evidence live: runtime `aaf3a9c6...`, fixture `9,869,032` bytes/SHA
`83DE97B...`, Confirm `1`, engine jobs `319 -> 320`, duplicate `0`, TTS/mux/
artifact/delivery `0`, transactions/provider-usage `0/0`, credit events `11`,
wallet `200/0`. Sidecar `5,425` bytes/SHA `08D5CC60...` có `32` cue và `2`
label. Evidence source hiện tại: RED `2 failed in 7.43s`; functional durable
GREEN `2 passed in 9.46s`; direct adapter `3 passed in 7.10s`; exact provider
detail RED `1 failed in 7.19s` -> GREEN `2 passed in 5.85s`; hai file focused
conditional manifest RED `1 passed + 1 failed in 6.55s` -> GREEN `2 passed in
562.59s`; cuối `58 passed in 6.87s`; exact-two/audio `86 passed in 8.92s`; Task7
branch/clean cùng đúng `6 passed + 7` failure IDs, `NEW_FAILURES=0`; compile
exit `0`; source provider calls/wallet mutations `0/0`. Multi vẫn chưa LIVE PASS.

## Đối chiếu Product Video flow/artifact sau job 25 — 28/08/2026

| Chức năng/tài liệu cũ | Hiện tại | Trạng thái |
|---|---|---|
| Canvas `9:16` đồng nghĩa hình thật phủ kín dọc | Job `25` có stream `540x960` nhưng nội dung ngang bị pad đen, hình co nhỏ | Không còn đủ để PASS |
| Add-on bật trong UI sẽ tự tới renderer | Job `25` có `subtitle_requested=1` và SRT nhưng legacy plan làm manifest rơi subtitle | Không còn đúng |
| Callback ACK là bước bắt buộc trước logic | Telegram timeout/502 làm 10 tier và Confirm đứng nguyên màn | Đã sửa thành best-effort |
| Ý tưởng video có executor `video_idea_to_product` độc lập | Executor phải alias về owner `video_idea` để tạo Invoice/Confirm/Status Tail | Đã khóa contract |
| Kho trend chỉ có Google Trends và TikTok reference | Backend có bốn nhóm public metadata Media/Facebook/YouTube/TikTok, refresh 7 ngày | Đã mở rộng không đổi UI |
| Trend chọn tỉ lệ rồi đi thẳng sang nhân vật | Cả `4` lane Trend phải qua content source, profile/preset, content choice và Preview trước entity flow | Flow cũ đã phục hồi |
| Telegram document có thể luôn dùng `get_file/download_to_drive` | Local Bot API có file path/transport riêng; Trend phải dùng shared bounded byte downloader như các Video lane ổn định | Direct path gây `InvalidToken`, đã sửa source |

Bằng chứng hiện tại: job `25` đã delivery message `27576` và `0 Xu`, nhưng PV-L01 vẫn FAIL do letterbox + subtitle drop. Source correction có focused `45 passed`, quality/manual `39 passed`, Trend/scene `52 passed`, full output `24 passed`, compile `0`; UI lock `14/14` function bytes. Phải rerun live exact case sau deploy mới được đổi trạng thái thành PASS.

Bằng chứng phục hồi Trend ngày 29/08/2026: exact RED `4 failed, 1 passed` ->
GREEN `5 passed`; `5` selector hợp đồng lịch sử và `3` transition runtime đưa
file restore lên `8 passed`. So sánh bảy file là
branch `119 passed + 2` failure Script baseline và clean main `117 passed + 3`;
`NEW_FAILURES=0`. Tail/quality/UI protected `59 passed`. PR #928 đã deploy exact
runtime `fe25cc05...` qua run `33237168072`; bot + owner worker cùng SHA và
heartbeat generation mới hợp lệ. Chưa có artifact full-flow mới nên Trend vẫn
chưa được đánh dấu LIVE PASS.
Post-rebase exact main `da817b65...`: `186 passed + 2` failure Script baseline;
compile exit `0`. Artifact thật vẫn là cổng riêng.

## Đối chiếu Tail chọn chất lượng — 28/08/2026

| Chức năng/tài liệu cũ | Hiện tại | Trạng thái |
|---|---|---|
| Callback chất lượng có thể clamp số bất kỳ về `200..1500` | Chỉ nhận exact tier có trong catalog hiện hành của đúng product; callback giả/stale fail-closed | Không còn đúng |
| Snapshot kế hoạch trước Tail luôn đủ cho RouteEngine | Chọn tier có thời lượng khác cần execution snapshot mới, hash mới và cùng một authority cho RouteEngine/storyboard/invoice/guard | Đã sửa |
| Product ngoài AI Real luôn dùng duration mặc định planning | Planning UI vẫn giữ mặc định; execution snapshot và session dùng duration của tier đã chọn | Đã làm rõ |
| Canonical Storyboard owner là `video_storyboard` | Public/UI/Tail dùng `storyboard_prompt`; RouteEngine giữ alias cũ và nhận thêm canonical alias | Tài liệu tên cũ không còn đủ |
| Hiện lại danh mục sau exception nghĩa là tier rẻ nhảy sang tier đắt | Live log chứng minh callback vẫn là `select|400`; catalog chỉ là recovery screen, chưa có Invoice/job/provider/wallet mutation | Cách đọc cũ sai |

Bằng chứng source: `130 passed` acceptance, `25 passed` RouteEngine, `17 passed`
quality matrix, `14/14` UI hashes, `NEW_FAILURES=0`, compile/diff exit `0`.
Merge/deploy/runtime và live traversal vẫn là các cổng riêng.

## Đối chiếu Strategy V2 và báo cáo sau delivery — 28/08/2026

| Tài liệu/cách làm cũ | Strategy V2 hiện tại | Trạng thái |
|---|---|---|
| Live mọi lane, lấy manual lane ngắn làm mẫu | Chỉ live 1 lane phức tạp nhất mỗi product; manual/direct-input là source-contract coverage | Không còn đúng |
| Video AI Chân thật chạy riêng đủ 10 tier, mỗi tier 2 cảnh | Tier `400` được 8 representative rows bao phủ; 9 tier còn lại phân cho product tương thích và dùng 1 cảnh | Không còn đúng |
| Video tự quay là 1 product | Có 2 product/engine độc lập: đổi cảnh và biến đổi điện ảnh; cả hai có representative row | Không còn đúng |
| Video dài tập và Chỉnh sửa Video nằm trong matrix hiện tại | Long Video bị loại; Local Edit đã khóa; AI Edit hoãn cùng Long Video | Không còn đúng |
| MP4 Telegram là terminal customer outcome duy nhất | Sau MP4 receipt + settlement còn đúng 1 business report, có message-id durable và dedupe | Đã mở rộng |
| Add-on state có thể rebuild từ profile defaults | Strict `product-video-addons-v1` từ Tail phải giữ nguyên tới worker; profile không được tự bật voice/music/subtitle | Không còn đúng |

Số đo hiện tại: 8 representative rows, 9 quality-only rows, 17 final jobs,
28 scene renders, 4 source-image tasks và tối đa 32 external create calls. Nguồn
đối chiếu là `KIEM-THU/product-video-live-strategy-v2.json`; case tester phải lấy
từ `KIEM-THU/DANH-SACH-CASE.md`, không lấy từ ma trận PV-L01..PV-L09 lịch sử.

Chỗ tài liệu gốc không còn đúng quan trọng nhất: một lane đã LIVE PASS phải khóa
route/test/artifact; sản phẩm sau chỉ nối adapter vào engine đã chứng minh. Không
được sửa product đã PASS để làm product mới chạy. `merged != deployed != LIVE`, và
MP4 hợp lệ vẫn chưa đủ nếu Add-on truth, report receipt hoặc zero-wallet evidence
còn thiếu.

## Đối chiếu PV2-R01 job #28 và provider authority theo cảnh - 29/08/2026

| Chức năng/tài liệu cũ | Hiện tại đo được | Trạng thái |
|---|---|---|
| Root `provider_task_ids/provider_status` đủ đại diện job nhiều cảnh | Job `28` root chỉ đếm `1` task và mất authority, nhưng `scene_tasks` + hai map durable giữ đúng `2` task, một cho mỗi cảnh, cùng authority `IN_PROGRESS` | Không còn đúng |
| `failed_no_charge` luôn thắng mọi provider snapshot | Chỉ explicit exhaustion/cancellation/delivery thắng; marker failed stale được scene task đang chạy sửa về polling khi root vẫn yêu cầu pending | Đã làm rõ fail-closed |
| Worker hết generic retry thì cần submit job mới | Claim boundary CAS-requeue chính job cũ với `recovery_existing_tasks_only`; submit/resubmit/fallback đều bị ép false | Không còn đúng |
| Provider nhận task hoặc HTTP 200 là video PASS | Hai task job `28` được nhận và pollable nhưng chưa có scene artifact/final MP4/receipt, nên vẫn LIVE RED | Không còn đủ để PASS |

Bằng chứng production: runtime `42cbf929...`, request `VID-20260829-D78AA3`,
project/job/outbox `32/28/27`, `attempts=5/max=3`, hai scene authority
`IN_PROGRESS`, outbox `terminal_failed`, delivery attempts `0`, charged Xu `0`.
Source correction có focused/recovery `7 passed`, protected `68 passed + 5` exact baseline
deselected, broad impact branch/clean cùng đúng `34` historical failures,
`NEW_FAILURES=0`; compile/diff/docs/state/secret sạch. Recovery preflight RED
chứng minh claim scan từng có thể hồi sinh job #27 explicit exhaustion; shared
terminal-reason guard hiện giữ #27 terminal, giữ #28 poll-only, và `4` selector
recovery hiện hữu PASS mà không thêm provider submit route.

Chỗ tài liệu cũ không còn đúng cần nhớ: một summary root có thể là dữ liệu trình
bày đã collapsed, không phải authority cho multiscene. Trước khi terminal hóa phải
đọc task identity, actual status source và clip validity của từng scene; ngược lại,
không được dùng scene status cũ để hồi sinh job đã cancelled, delivered hoặc có
terminal reason explicit. `PV2-R01` chưa LIVE PASS cho tới khi chính hai task cũ
được materialize thành MP4/receipt/report đạt đủ acceptance.

## Đối chiếu recovery budget và authority repair - 30/08/2026

| Chức năng/tài liệu cũ | Hiện tại đo được | Trạng thái |
|---|---|---|
| Hết `3` recovery luôn đồng nghĩa provider task đã hết hiệu lực | Job #28 dùng đủ `3/3` trên logic root-only cũ nhưng hai task-scene vẫn authority `IN_PROGRESS`, map đủ `2/2` và `provider_task_alive=true` | Không còn đúng |
| Sửa lỗi bằng cách tăng max recovery chung | Max thường vẫn là `3`; chỉ một authority-repair có marker durable, đủ scene authority và toàn bộ cancel/terminal/delivery/wallet guard | Không được làm theo cách cũ |
| Authority repair có thể mở fallback/provider submit | Repair chỉ poll hai task cũ; `provider_submit_allowed`, `automatic_resubmit_allowed`, `automatic_fallback_allowed` đều false | Đã khóa fail-closed |

Bằng chứng source hiện tại: one-shot RED `1 failed in 8.41s` -> GREEN `1 passed
in 5.74s`; protected `242 passed` và final strategy-inclusive `251 passed`, cùng
một warning dependency; compile/diff-check exit `0`. PR/deploy/live của correction vẫn là cổng riêng, nên `PV2-R01` còn
`IN PROGRESS` và không được ghi `LOCKED_LIVE_PASS` sớm.

## Đối chiếu root status và scene authority trong terminal classifier - 30/08/2026

| Chức năng/tài liệu cũ | Hiện tại đo được | Trạng thái |
|---|---|---|
| Chỉ hỏi scene authority khi root `continue_polling=true` | Job #28 có root false nhưng hai scene authority `IN_PROGRESS` và `provider_task_alive=true`; root là summary stale | Không còn đúng |
| Authority repair đã dùng thì không thể phân biệt lỗi classifier kế tiếp | Có đúng một classifier-repair marker cho payload authority-repair-used + worker-failed + pending; marker thứ hai bị chặn | Đã khóa bounded |
| `provider_in_progress` trên root failed luôn là terminal | Explicit exhaustion vẫn terminal trước; pending chỉ được giữ khi helper scene authority chứng minh task thật còn sống | Đã sửa theo authority |

Source evidence: RED `1 failed in 6.27s`, focused GREEN `4 passed in 4.65s`,
protected `252 passed` và một warning dependency. Không có provider submit, job mới
hay wallet mutation; live artifact/receipt/report vẫn chưa đạt.

## Đối chiếu summary rank và current task authority - 30/08/2026

| Chức năng/tài liệu cũ | Hiện tại đo được | Trạng thái |
|---|---|---|
| Rank `failed=4` luôn mạnh hơn `running=3` | Chỉ đúng trong cùng cấp authority; job #28 summary failed là historical, còn task-bearing `actual_provider_payload_status=IN_PROGRESS` là current authority | Không còn đúng |
| `scene_status_by_index` có thể ghi đè scene task đã map | Summary chỉ bổ sung scene chưa có task candidate; task đã map phải theo current provider payload | Đã sửa |
| Requeue thành công nghĩa là worker đã nhận job | Job #28 recovery count tăng lên `5`, nhưng attempts vẫn `5` và lock rỗng, chứng minh claim-scan terminal hóa trước CAS | Không còn đủ |

Bằng chứng source: claim integration RED `1 failed in 5.92s` -> GREEN `1 passed
in 5.14s`; focused `25 passed`; protected `252 passed` và một warning dependency.
Không có recovery marker, provider submit, job mới hay wallet mutation được thêm.

## Đối chiếu task identity và status authority source - 30/08/2026

| Chức năng/tài liệu cũ | Hiện tại đo được | Trạng thái |
|---|---|---|
| Cùng task ID thì status có rank số lớn hơn luôn thắng | Job #28 có historical event/root `FAILURE` cùng task ID nhưng per-scene current là `IN_PROGRESS`; identity bằng nhau, authority source khác nhau | Không còn đúng |
| Root canonical summary là current authority | Root summary có thể collapsed/stale; chỉ per-scene provider payload hiện tại hoặc completion có result thật là trusted sticky | Không còn đúng |
| Sticky running làm current FAILURE không terminal được | Current per-scene FAILURE cũng là trusted và vẫn thay running; chỉ historical event/root bị chặn | Đã khóa comparator |

Full production-shape RED `1 failed in 5.31s` -> GREEN `1 passed in 5.67s`;
focused `27 passed`; protected `252 passed` và một warning dependency. Correction
không thêm provider call, recovery marker, job hay wallet mutation.

## Đối chiếu giá khách và provider budget fallback - 30/08/2026

| Chức năng/tài liệu cũ | Hiện tại đo được | Trạng thái |
|---|---|---|
| Exact quote yêu cầu cả provider budget bằng giá khách | Chỉ ba trường customer quote phải bằng `144`; internal budget tier 400 là `212 Xu` để bao phủ Key4U `21.150,72 VND` | Không còn đúng |
| Fallback đắt hơn phải tăng giá khách | Owner giữ exact price và hấp thụ âm biên `6.750,72 VND`; customer charge không đổi | Không được tăng giá |
| Primary terminal cần tạo job mới | Dùng cùng job #28, fallback một lần/cảnh, idempotency riêng; primary không resubmit | Đã có blackbox/shared route |

RED `1 failed in 5.84s` -> GREEN `5 passed in 5.63s`; protected fallback/Key4U/
price/claim `88 passed in 9.34s`. Debug/recover/background source, quote mismatch,
missing confirm, delivered/charged và fallback count >=1 vẫn fail-closed.

## Đối chiếu truyền cost vào fallback router - 30/08/2026

| Chức năng/tài liệu cũ | Hiện tại đo được | Trạng thái |
|---|---|---|
| Có budget `212` là router tự biết cost Key4U | Router không suy đoán cost; request phải truyền riêng `fallback_provider_cost_xu=212` | Đã bổ sung boundary |
| Thiếu cost có thể bỏ qua vì candidate đã prevalidated | Live tier 400 phải chứng minh cả budget và cost; prevalidated không thay thế số đo đã khóa | Không được bỏ qua |

RED `1 failed in 8.29s` -> GREEN `1 passed in 5.56s`; protected fallback/Key4U
`19 passed in 6.76s`; compile/diff `0`. Production chỉ thêm một metadata field.

| Chức năng/tài liệu cũ | Hiện tại đo được | Trạng thái |
|---|---|---|
| Tính đúng cost context đồng nghĩa submit path tự enforce | Single-candidate Key4U trước guard vẫn submit khi cost `213>212` | Không còn đúng |
| Cost guard chỉ cần ở bước chuyển provider | Public fallback source phải chạy controlled policy trước mọi adapter submit, kể cả chain chỉ có Key4U | Đã bổ sung fail-closed |

Over-budget RED: Key4U `submit_calls=1`; GREEN chặn trước call. Within-budget
`212==212` vẫn gọi đúng một lần. Count-before-submit `0` cho phép attempt
hiện tại, `1` chặn retry. Spend safety `12 passed`, affected total
`49 passed`, compile/diff `0`.

## Đối chiếu claim state và worker payload - 30/08/2026

| Chức năng/tài liệu cũ | Hiện tại đo được | Trạng thái |
|---|---|---|
| Preclaim ghi result_json là worker tự nhận đủ | Worker payload builder chỉ copy route/default fields; job #28 mất quote `144`, budget/cost `212`, fallback scene và idempotency | Không còn đúng |
| Project Invoice đủ để dựng lại controlled fallback | Invoice lưu giá khách nhưng không mang live controlled authority; dựng lại thành `400/0/0` và chặn fallback | Không được tái dựng |
| Có thể truyền toàn bộ result_json sang worker | Chỉ allowlist controlled context khi recovery + terminal suppression + Key4U candidate cùng đúng | Đã cô lập |

Live RED attempts `6->8`, provider HTTP/usage `0`, wallet `200/0`.
Direct claim/hydrate `2 passed`, worker-to-scene `1 passed`; expanded branch
`97 passed + 4 failures` và clean cùng 4, focused branch `61 passed + 2` và
clean cùng 2, `NEW_FAILURES=0`.

## Đối chiếu SubDub Auto multi terminal-empty recovery — 31/08/2026

| Chức năng/tài liệu cũ | Hiện tại đo được | Trạng thái |
|---|---|---|
| Một terminal HTTP 200 rỗng rồi retry một lần là đủ | Recovery production nhận liên tiếp `2` response HTTP `200 completed` rỗng; probe kế tiếp cùng file/config trả `152` annotations, `149` word và `5` speaker | Không còn đúng |
| Recovery admin có thể dùng command message làm progress target | Command message không edit được; cùng recovery đã tạo `6` panel riêng thay vì cập nhật một panel | Không còn đúng |
| Same-job recovery chỉ có một attempt trong mọi trường hợp | Có đúng một correction thứ hai, chỉ cho Gemini HTTP `200` rỗng + `AUTO_CAST_MANUAL_REQUIRED` + no-charge/no-output; attempt tiếp theo vẫn bị chặn | Đã cô lập fail-closed |

Source evidence: RED `3 failed in 609.21s`; exact GREEN `3 passed in 6.56s`;
direct `36 passed`; protected `68 passed`; compile `0`. Đây chưa phải LIVE PASS:
MP4/receipt vẫn phải được đo sau deploy trên chính job `211844aa34788db33757`.

Pre-merge review bổ sung explicit safety + raw annotation authority: missing field,
artifact/message evidence hoặc nonempty rejected annotations đều không được correction.
RED `17 failed, 8 passed in 8.64s`; GREEN `25 passed in 563.13s`; expanded
`126 passed in 9.39s`.
