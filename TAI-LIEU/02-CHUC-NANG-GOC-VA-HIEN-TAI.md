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

GitHub tester cloud readback ngày 28/08/2026 có `21` labels: `5` trạng thái,
`4` mức độ, `3` loại và `9` mặc định. Issue list hiện có tracker `#884` và
`#81`; chưa tạo SubDub issue mới trong correction này. Hai template SubDub và
case local dưới `KIEM-THU/` là nguồn chuẩn. GitHub Projects chưa đọc được vì
token thiếu scope `read:project`; không tự chạy `gh auth refresh`.

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
`subdub_speaker_cast.py`, `auto_multi_speaker.py`, PCM filter, provider, UI,
pricing hay wallet. Chưa deploy/chưa có MP4 thật thì vẫn ghi `LIVE pending`.

## Đối chiếu Product Video flow/artifact sau job 25 — 28/08/2026

| Chức năng/tài liệu cũ | Hiện tại | Trạng thái |
|---|---|---|
| Canvas `9:16` đồng nghĩa hình thật phủ kín dọc | Job `25` có stream `540x960` nhưng nội dung ngang bị pad đen, hình co nhỏ | Không còn đủ để PASS |
| Add-on bật trong UI sẽ tự tới renderer | Job `25` có `subtitle_requested=1` và SRT nhưng legacy plan làm manifest rơi subtitle | Không còn đúng |
| Callback ACK là bước bắt buộc trước logic | Telegram timeout/502 làm 10 tier và Confirm đứng nguyên màn | Đã sửa thành best-effort |
| Ý tưởng video có executor `video_idea_to_product` độc lập | Executor phải alias về owner `video_idea` để tạo Invoice/Confirm/Status Tail | Đã khóa contract |
| Kho trend chỉ có Google Trends và TikTok reference | Backend có bốn nhóm public metadata Media/Facebook/YouTube/TikTok, refresh 7 ngày | Đã mở rộng không đổi UI |

Bằng chứng hiện tại: job `25` đã delivery message `27576` và `0 Xu`, nhưng PV-L01 vẫn FAIL do letterbox + subtitle drop. Source correction có focused `45 passed`, quality/manual `39 passed`, Trend/scene `52 passed`, full output `24 passed`, compile `0`; UI lock `14/14` function bytes. Phải rerun live exact case sau deploy mới được đổi trạng thái thành PASS.

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
