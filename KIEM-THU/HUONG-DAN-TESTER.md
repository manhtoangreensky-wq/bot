# Hướng dẫn tester Product Video

Strategy V2 có đúng 8 representative rows và 9 quality-only rows. Tier `400`
được representative rows bao phủ; không tạo quality-only job thứ mười.

1. Chọn đúng case `PV2-*` trong `DANH-SACH-CASE.md`; không tự đổi scenario giữa chừng.
2. Representative phải dùng lane phức tạp không-manual. Manual/direct-input chỉ
   kiểm tra source contract đi thẳng Add-on, không dùng làm paid representative.
3. Ghi baseline project/job/outbox/provider-usage/transaction/credit-event trước
   khi bấm Xác nhận cuối.
4. Đi qua đúng Add-on -> Review -> Chất lượng -> Hóa đơn -> Xác nhận -> Trạng thái.
5. Chỉ bấm Xác nhận cuối một lần; thử callback lặp chỉ khi case yêu cầu idempotency.
6. Chờ job terminal. Queued/processing/HTTP 200 không phải PASS.
7. Tải MP4, đo hash, bytes, codec, kích thước, duration, scene coverage và audio.
8. Đối chiếu Add-on requested/materialized/applied với video thật; `missing` phải rỗng.
9. Ghi video delivery message ID, file ID, file_unique_id, `charged_xu`, transaction
   delta và credit-event delta.
10. Sau MP4, kiểm tra đúng một báo cáo kinh doanh được gửi sau receipt + settlement;
    ghi `delivery_report_message_id` và `delivery_report_sent=true`.
11. Callback completion trùng không được gửi lại MP4, settlement hoặc report.
12. FAIL ở bước nào thì mở lại đúng spec/case đó; không chuyển sang case tiếp theo.

Lỗi cũ cần canh: literal `\\n`, status nằm ngang, video mất audio, back nhảy sản
phẩm, tier bị đổi, thiếu scene, Add-on bị drop/tự bật từ profile, duplicate
job/delivery/report, report gửi trước settlement hoặc lộ thông tin kỹ thuật.

13. Với output `9:16`, không chỉ kiểm tra stream width/height. Mở video và xác nhận hình thật phủ kín canvas, không có hai dải đen trên/dưới hoặc trái/phải do `pad`; cảnh ngang phải được crop-to-fill, không co nhỏ giữa khung.
14. Ở mọi nút Chất lượng, bấm một lần phải chuyển sang Hóa đơn; `Xác nhận tạo video` phải chuyển sang Xác nhận; `Bắt đầu tạo video` phải luôn chuyển sang Trạng thái kể cả provider/worker chưa sẵn sàng. Đứng nguyên màn là FAIL callback.
15. Add-on PASS cần đồng thời: project plan ghi requested, worker materialization có artifact, manifest `addon_application.requested/applied` có đúng tên và video thật thể hiện add-on. Có SRT bên cạnh nhưng `subtitle_path=null` vẫn là FAIL.
16. Customer report chỉ được chứa thông tin kinh doanh: sản phẩm, chất lượng,
    cảnh/thời lượng/tỉ lệ, giá video, Add-on miễn phí/có phí/đã áp dụng, phí Add-on,
    tổng hóa đơn, Xu thực trả và trạng thái giao. Có provider, worker, job/task ID,
    SHA, manifest, JSON, engine route hoặc mã lỗi nội bộ là FAIL.
17. Không test `multi_scene_film`, `video_long`, `video_local_edit` hoặc
    `videoedit|ai` trong chu kỳ V2 hiện tại. Local Edit là baseline đã khóa.

## Cách test Public Landing Motion

1. Dùng đúng sáu case `ML-01..ML-06`; tải mới trang trước mỗi case.
2. Cuộn từ đầu tới cuối rồi quay lại; mỗi section chỉ được reveal một lần, không flash hoặc mắc kẹt mờ.
3. Desktop rê chuột tới bốn góc preview; độ lệch không quá `10px`. Tablet/mobile không được parallax.
4. Bật giảm chuyển động của hệ điều hành; nội dung, CTA và form phải hiện ngay.
5. PASS chỉ khi JSON có `failures=[]`, CLS/long task/overflow/pending/runtime error đều `0` ở cả hai lượt.
6. FAIL thì cập nhật issue `#884` và mở lại đúng `MOTION-LANDING-TOANAAS-001`; không sửa Bot/lead/Telegram/PayOS.

## Cách test SubDub tự động

1. Chạy đúng thứ tự `SD-2S-01 -> SD-2S-02 -> SD-MS-01`; case trước chưa có
   artifact PASS thì cấm chạy case sau.
2. Hai case đầu chỉ upload file `2 giọng nam nữ.mp4` có SHA-256
   `85C8793D197CF2782BB554D46282E82A83BCB062A0483E412A0CA1DA668F9F51`;
   không dùng `Download.mp4` hoặc fixture lịch sử.
3. Chọn `Tự động 2 giọng`, mở `🎚 Âm thanh`. Màn chính phải chỉ có hai nút
   `Âm thanh gốc | Giọng lồng tiếng` cùng một hàng và Quay lại; không được có
   `Gốc xx%` hoặc `Lồng xx%`. Vào từng màn con để nhập gốc `40%`, lồng `150%`,
   quay lại kiểm tra hai giá trị còn nguyên, rồi confirm đúng một lần.
4. Status phải hiện từ saved input qua ASR/diarization, cast, TTS, mux và delivery;
   lỗi ở stage nào ghi đúng stage đó, không suy ra từ HTTP `200`.
5. Sidecar phải có đúng `2` speaker labels. Cast của từng label phải đến từ
   acoustic evidence độc lập; không chấp nhận forced male/female pairing.
6. Combo và standalone chỉ được tự gửi MP4 rồi receipt cuối. Không được tự gửi
   SRT, audio, sidecar hoặc document phụ; SRT chỉ dùng nội bộ để gắn phụ đề/QC
   hoặc khi người dùng chủ động bấm tải. Receipt phải đủ giá phụ đề, giá lồng
   tiếng, total và loại `Tự động 2 giọng`.
7. Nghe từng cue: giọng dịch phải bắt đầu/kết thúc trong đúng timestamp phụ đề
   gốc; cue sau không bị trễ vì cue trước dài. Evidence job phải có số cue đo,
   `speech_rate_max_drift_seconds=0` và duration MP4 bằng duration nguồn trong
   tolerance validator.
7. Mỗi MP4 đo hash/bytes/duration/dimensions/codecs và AAC loudness; nghe lại để
   xác nhận có tiếng và mức gốc/lồng đúng lựa chọn.
8. Admin phải `charged_xu=0`; credits, total_spent, transaction count và wallet
   event delta phải giữ nguyên.
9. `empty_transcript`, thiếu một speaker, speaker evidence không chắc hoặc mapping
   cue dưới ngưỡng đều là FAIL-closed. Không sửa test để ép thành hai label.
10. Chỉ sau hai case 2-speaker PASS và lock manifest đã ghi hash mới dùng
    `test nhiều giọng.mp4` SHA-256
    `83DE97B744B931E544B569E6E750F8415545F226461BD2E36CFB49225898AD3E`
    cho `SD-MS-01`. Chạy combo trước rồi standalone; mỗi flow chọn English,
    Auto multi, gốc `40%`, lồng `150%` và confirm đúng một lần.
11. Lặp lại contract audio UI trên giọng nữ mặc định, giọng nam mặc định, Kho
    voice, voice riêng, Auto 2 và Auto multi khi chạy case tương ứng; không chấp
    nhận một kiểu giọng mở bảng preset hoặc làm mất giá trị numeric.
12. Nếu Deepgram empty và Key4U lần đầu unusable, exact Auto 2 được gọi Key4U
    tối đa `2` lần. HTTP `401` hoặc segment không có timestamp provider phải
    dừng ngay; fallback exact này không được dùng cho Auto multi. Với Auto
    multi acoustic, Deepgram chỉ cung cấp strict word timeline, không request
    diarization; active wrapper không được gọi provider re-diarization/crosswalk
    hoặc truyền expected-speaker count. ASR words và VAD không được quyết định
    `k`; fixed-vocal windows phải khám phá speaker trước khi map words.
13. Fixture karaoke có nhạc nền: kiểm evidence cast, không chỉ nhìn hai label.
    Kết quả khóa local là speaker 0 `male/low`, vote `7/8`, dominance `0.875`,
    evidence `21s`; speaker 1 `female/high`, vote `8/10`, dominance `0.800`,
    evidence `27s`. Tổng unique evidence `48s`, classifier provider calls `0`.
    Filter cũ từng trả sai `high/high`; raw-frame fallback đã bị cấm. Nếu log
    chỉ có label mà không có gender/register/dominance/evidence time, hoặc dùng
    “một nam + một nữ” không qua vote độc lập, FAIL.
14. Với Auto multi, range chung là `3–8` speaker có speech support. Fixture
    `83DE97B7...` phải ghi raw acoustic `5` nhưng effective speech speakers `4`.
    Raw label `0` không có overlap word support và targeted ASR trên vocal/gốc
    đều empty nên không được tạo voice. Terminal proof phải ghi
    `auto_detected_speaker_count == auto_distinct_voice_count` và
    `auto_multi_attribution_verified=true`; mỗi cue có đúng một speaker, tập
    speaker của cue bằng tập acoustic, mỗi label giữ một voice ID ổn định trong
    toàn video. Không chấp nhận bịa/gộp label, ép giới tính, bỏ speaker khỏi TTS
    hoặc dùng lại một voice cho hai label. Raw/effective counts phải tách riêng.
    Bắt buộc chạy thêm ma trận không-fixture: raw count `4..8`, noise/phi-lời ở
    cả label đầu, giữa, cuối hoặc nhiều label; rồi full-chain cho từng effective
    count `3..8`. Không được có nhánh theo SHA/job/duration/raw label/k cụ thể.
15. Auto multi dùng cùng cue-lock đã chứng minh: từng start/end nguồn bất biến,
    cue sau không đợi cue trước, final duration bằng nguồn. Cả combo và
    standalone chỉ tự giao MP4 rồi receipt; SRT/audio/document tự động phải là
    `0`. Receipt có loại Auto multi, speaker/voice count, giá niêm yết và total;
    admin `charged_xu=0`, wallet/event delta `0`.
16. Canh regression local acoustic: malformed/duplicate/non-monotonic word
    authority phải FAIL; provider speaker label bị bỏ qua; mọi retained cluster
    phải có support và tổng embedding windows không vượt cap `1,000`. Speaker
    high-bound `>8`, busy lock, PCM sai shape, timeout hoặc cancellation phải
    dừng trước TTS/mux và giữ `charged_xu=0`.
17. Trước LIVE chạy `SD-MS-L01`: strict word timeline phải giữ nguyên index,
    start/end của mọi retained word; coverage count bằng word count và không word
    nào xuất hiện trong hai cue. Zero-duration/malformed item không được tạo cue.
18. Chạy `SD-MS-L02` bằng exact fixture offline và model thật. Phải đo raw `5`
    clusters, `178` embedding views `[9,18,26,25,11]`; effective `4` speech
    speakers từ raw labels `[1,2,3,4]`, raw label 0 overlap support `0`; word
    coverage không mất. Model-byte mutation hoặc missing notice phải fail trước
    inference. Đây không phải LIVE PASS và không gọi provider.
19. Chạy `SD-MS-L03/L04`: legacy/provider sidecar phải force-fresh; chỉ bundle
    acoustic cùng source, strict timeline, model hash và algorithm version mới
    được resume, với ASR-call delta `0`. Không đọc raw embedding/PCM trong state.
20. `SD-MS-L05` giữ bằng chứng lịch sử: model preflight đã hoàn tất trước CAS và
    chính job chuyển `3/2 -> 4/3` đúng một winner. Marker hiện đã consumed; command
    cũ, attempt mới không được cấp quyền và concurrent loser đều phải no-op.
21. Sau exact-SHA deploy, chỉ tiếp tục LIVE khi Owner gửi fresh action-time
    authorization cho chính job `b4cb6d5fe8a7bdfce507`. Không gửi lại command
    recovery cũ, không upload, không Confirm và không tạo job mới. Sau đó chỉ đọc
    durable job/workspace/journal tới terminal. Không có MP4 thật rồi receipt thì
    ghi FAIL/BLOCKED, không ghi PASS.
22. Nếu durable job vẫn ghi `wespeaker-resnet34-spectral-v1` và cả hai one-shot
    marker cũ đã true, không reset/xóa marker và không gửi command cũ. Trước live
    phải deploy rồi test `scripts/recover_subdub_fixed_vocal_v2.py`: preflight v2
    exact model/CPU trước DB; cùng attempt `4/3`; một marker v2; duplicate và mọi
    mismatch no-op. Chỉ chạy script thật sau fresh Owner authorization.
23. Final evidence phải có model/algorithm, speaker/unit/window/cluster counts,
    distinct voice count, per-speaker cue counts, source/translated cue count,
    drift counters, original `40`/dub `150`, MP4 metrics, hai Telegram message ID,
    `charged_xu=0`, root-job/transaction/wallet/credit/provider-usage deltas `0`.
24. Với context-repair same-job, kiểm bốn `_pipeline_*` field tới classifier/TTS/
    mux. `job_key` chứa `file_unique_id` dùng idempotency; nó không download được.
    Runner chỉ được gọi Telegram bằng full `file_id` lưu riêng, nonempty và khác
    unique ID. Size `9,869,032`, MIME `video/mp4` và SHA fixture phải khớp trước
    ghi file/CAS. Sai hash, unique ID lệch, full ID thiếu/mâu thuẫn/sai type,
    duplicate marker hoặc CAS loser phải dừng, không command cũ/job mới/overwrite.
25. Exact Auto Multi phải tách nguồn theo mục đích: ASR/render dùng normalized
    video, speaker embedding dùng original hash-locked audio. FAIL nếu PCM acoustic
    lấy normalized copy đã resample; exact original fixture phải giữ raw `k=5`
    và tính effective speech count từ word-overlap support. Lane
    khác và Auto 2-speaker giữ nguyên saved-source priority.
26. Kiểm timeout Auto Multi bằng duration PCM thật, không theo tên/codec/fixture:
    `1s` và `75s` dùng floor `300s`, `133.37542s` dùng `534s`, direct limit
    `300s` dùng cap `1200s`. Chạy timing-only regression `145` words; provider
    có thể lệch timestamp nhưng vẫn phải giữ coverage, raw `k=5` và effective
    speech count ổn định cho fixture, đủ
    cue→speaker. Nếu timeout phải thấy `acoustic_runtime_timeout`; nếu engine
    fail `fixed_vocal_*` phải giữ đúng mã đó, không chấp nhận
    `acoustic_failure_unknown`.
27. Kiểm duration nguồn acoustic tách khỏi speech timeline. Với fixture, lời
    cuối kết thúc `126.505s` nhưng original media dài `133.37542s`; command
    extract phải dùng full media duration. FAIL nếu PCM dừng ở cue cuối, kể cả
    khi đúng original file. Chạy comparator non-Multi để chắc lane khác không bị
    probe/đổi duration.
28. Kiểm marker lane qua pending state: sau ASR/persist subtitle, state vẫn phải
    có `voice_kind`, `voice_selection_mode` và `auto_speaker_lane=multi`. Nếu
    thiếu lane marker, extractor sẽ âm thầm rơi về normalized source; coi là
    FAIL dù các `_pipeline_*` field còn đủ.
29. Kiểm speech support: raw cluster chỉ có centroid-assigned word nhưng không có
    dominant-overlap word-unit không được tính là người nói. Phải giữ raw cluster
    audit, drop nó khỏi effective voice set, remap các word không mất, và fail nếu
    sau lọc còn dưới 3 speaker. Fixture D: raw `5`, effective `4`, 145/145 words.
