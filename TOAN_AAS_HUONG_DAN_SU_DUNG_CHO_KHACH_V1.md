# TOAN AAS - HƯỚNG DẪN SỬ DỤNG CHO KHÁCH HÀNG

**Phiên bản:** V1 - Stable Revenue Tool Bot  
**Bot Telegram:** @toanaasbot  
**Mục tiêu:** Giúp khách tự tạo ý tưởng, kịch bản, prompt, caption, voice/media pack để tự đăng lên Facebook, TikTok, YouTube.  
**Lưu ý quan trọng:** Hiện tại TOAN AAS chưa tự đăng bài, chưa quản lý tài khoản mạng xã hội và chưa chạy quảng cáo hộ khách. Khách tự đăng nội dung của mình.

---

## 1. ĐỌC PHẦN NÀY TRƯỚC - TOAN AAS DÙNG ĐỂ LÀM GÌ?

TOAN AAS là một bot Telegram gom nhiều công cụ AI vào một quy trình dễ dùng. Thay vì bạn phải mở nhiều web khác nhau, tự nghĩ prompt, tự sửa caption, tự viết kịch bản, tự nghĩ hashtag, TOAN AAS giúp bạn đi theo từng bước:

1. Bạn nói mục tiêu hoặc chủ đề.
2. Bot tạo ý tưởng, kịch bản, storyboard, prompt cảnh, caption, hashtag, CTA.
3. Bạn kiểm tra và chỉnh lại theo sản phẩm/thương hiệu của mình.
4. Bạn tự dùng nội dung đó để tạo video/voice hoặc đăng lên nền tảng bạn muốn.
5. Sau khi đăng, bạn có thể nhập số liệu thủ công để bot gợi ý cải thiện.

Nói dễ hiểu: **TOAN AAS không chỉ trả lời một câu hỏi, mà giúp bạn đi theo quy trình tạo nội dung bán hàng/video từ đầu đến cuối.**

---

## 2. VÌ SAO KHÁCH NÊN DÙNG TOAN AAS THAY VÌ CÔNG CỤ MIỄN PHÍ TRÊN MẠNG?

Trên mạng có rất nhiều công cụ miễn phí: AI chat, tạo caption, tạo ảnh, tải video, tách nền, chuyển giọng nói, viết script. Nhưng đa số công cụ đó có 5 vấn đề:

1. **Mỗi nơi làm một việc riêng.** Bạn phải tự nhớ mở web nào, copy qua lại, sửa định dạng, ghép kết quả.
2. **Không có quy trình rõ ràng.** Công cụ miễn phí thường chỉ trả lời một phần, không chỉ bạn bước tiếp theo nên làm gì.
3. **Không tối ưu cho bán hàng/nội dung ngắn.** Kết quả thường chung chung, phải sửa nhiều mới dùng được cho TikTok/Facebook/YouTube.
4. **Không có tiếng Việt và ngữ cảnh Việt Nam tốt.** Nhiều nội dung nghe như dịch máy, thiếu tự nhiên.
5. **Không quản được chi phí.** Dùng nhiều AI khác nhau dễ tốn tiền lẻ, không biết cái nào đáng dùng.

TOAN AAS khác ở chỗ:

- Có quy trình từng bước: tạo ý tưởng -> script -> prompt cảnh -> caption -> hashtag -> CTA -> tối ưu.
- Dùng bằng Telegram, không cần cài nhiều app.
- Dùng Xu, dễ hiểu hơn token. Khách chỉ cần biết còn bao nhiêu Xu và lệnh này tốn bao nhiêu.
- Có hướng dẫn nạp Xu, ưu đãi, gift code.
- Có fallback QR thủ công nếu cổng tự động bận.
- Có module Video Factory Lite tập trung vào Facebook/TikTok/YouTube.
- Có thể dùng AI thường miễn phí theo giới hạn, còn tác vụ sâu hơn mới tính phí.
- Có hệ thống nội bộ để admin kiểm tra, backup, theo dõi provider và vận hành.

**Tác dụng thực tế cho khách:** tiết kiệm thời gian nghĩ nội dung, giảm lỗi prompt, có sẵn format để đăng, có CTA và hashtag, có hướng tối ưu sau khi đăng.

TOAN AAS không cam kết video nào cũng viral, không cam kết doanh thu chắc chắn. Công cụ giúp bạn tạo nội dung nhanh hơn và có quy trình hơn; kết quả còn phụ thuộc sản phẩm, thị trường, cách quay/dựng, tài khoản và cách đăng.

---

## 3. LUỒNG DÙNG NHANH NHẤT CHO NGƯỜI MỚI

Nếu bạn là người mới, cứ làm đúng 7 bước này:

1. Mở Telegram.
2. Tìm bot: **@toanaasbot**.
3. Bấm **START** hoặc gõ `/start`.
4. Gõ `/profile` để xem số Xu hiện có.
5. Gõ `/khuyenmai` để xem mã ưu đãi đang có.
6. Nếu muốn nạp Xu, gõ `/naptien` và chọn gói.
7. Nếu muốn tạo nội dung video, gõ `/film chủ đề của bạn`.

Ví dụ cực đơn giản:

```text
/film review máy xay sinh tố mini cho mẹ bỉm, đăng TikTok, giọng gần gũi, mục tiêu bán hàng
```

Sau đó bot sẽ tạo nội dung. Bạn đọc kết quả, sửa lại thông tin sản phẩm, copy caption/prompt/script để tự làm video hoặc tự đăng.

---

## 4. BẢNG CHỌN NHANH: MUỐN LÀM GÌ THÌ BẤM/GÕ GÌ?

| Bạn muốn làm gì? | Dùng lệnh/nút nào? | Sau đó làm gì tiếp? |
|---|---|---|
| Xem bot có gì | `/start` hoặc `/help` | Đọc menu, chọn nhóm công cụ |
| Xem số Xu | `/profile` | Nếu thiếu Xu thì nạp |
| Nạp Xu | `/naptien` | Chọn gói, quét QR, chờ cộng Xu hoặc gửi bill thủ công |
| Xem khuyến mãi | `/khuyenmai` | Chọn mã phù hợp, nhập `/promo MÃ` trước khi nạp |
| Nhập mã promo | `/promo FIRST30` | Sau đó vào `/naptien` chọn gói đủ điều kiện |
| Nhận mã quà tặng | `/gift THANK100` hoặc `/nhanqua SORRY100` | Gift public hợp lệ thì Xu cộng ngay; mã BETA cần admin cấp theo ID |
| Tạo kịch bản/prompt video | `/film <chủ đề>` | Lấy script, scene prompt, caption, hashtag, CTA |
| Phân tích/tối ưu nội dung | `/growth_ai` | Đưa hook/caption/số liệu để bot góp ý |
| Báo cáo hiệu quả thủ công | `/campaign_report` | Tổng hợp nội dung đã đăng, số liệu, bài học |
| Nhập số liệu bài đã đăng | `/performance_add` | Ghi view/like/comment/click/doanh thu nếu có |
| Xem báo cáo số liệu | `/performance_report` | Dùng để quyết định nội dung tiếp theo |
| Hỏi AI thường | Gõ câu hỏi trực tiếp | Dùng cho việc nhanh, ngắn |
| Hỏi AI chuyên sâu | Dùng lệnh Pro/Deep nếu menu có | Dùng khi cần phân tích dài, chiến lược, nội dung khó |

Nếu bạn không nhớ lệnh, gõ:

```text
/help
```

---

## 5. GIẢI THÍCH VỀ XU CHO KHÁCH DỄ HIỂU

Xu là số dư trong bot. Bạn dùng Xu để chạy công cụ.

- User mới nhận **200 Xu trải nghiệm**.
- 1 Xu tương đương định giá nội bộ khoảng **100đ**.
- Một số tác vụ thường miễn phí hoặc có giới hạn/ngày.
- Tác vụ tạo nội dung/video pack, phân tích sâu, xuất báo cáo sẽ tốn Xu.

### 5.1. Gói nạp cơ bản

| Gói | Tiền | Xu gốc | Ghi chú |
|---|---:|---:|---|
| Dùng thử | 10.000đ | 100 Xu | thử hệ thống |
| Nhỏ | 20.000đ | 200 Xu | thử thêm |
| Trung | 50.000đ | 500 Xu | bắt đầu dùng nghiêm túc |
| Tiêu chuẩn | 100.000đ | 1.000 Xu | dùng ổn định |
| Nâng cao | 200.000đ | 2.000 Xu | dùng nhiều |
| Doanh nghiệp | 500.000đ | 5.000 Xu | dùng nhiều nhất hiện tại |

### 5.2. Launch Bonus lần đầu mua từng gói

| Gói | Xu gốc | Launch Bonus lần đầu | Tổng lần đầu | Mua lại |
|---|---:|---:|---:|---:|
| 10k | 100 | 0 | 100 | 100 |
| 20k | 200 | 0 | 200 | 200 |
| 50k | 500 | +30 | 530 | 500 |
| 100k | 1.000 | +50 | 1.050 | 1.000 |
| 200k | 2.000 | +150 | 2.150 | 2.000 |
| 500k | 5.000 | +500 | 5.500 | 5.000 |

Gói 10k và 20k chỉ dùng thử, không có Launch Bonus. Launch Bonus bắt đầu từ gói 50k trở lên.
Launch Bonus áp dụng 1 lần cho mỗi tài khoản ở từng gói 50k/100k/200k/500k.
Các lần mua lại cùng gói chỉ nhận Xu gốc.

---

## 6. CÁCH NẠP XU - CHỈ TỪNG BƯỚC

### 6.1. Nạp bằng PayOS QR động

Làm như sau:

1. Gõ `/naptien`.
2. Bot hiện bảng gói nạp.
3. Nếu có mã ưu đãi, nhập mã trước. Ví dụ:

```text
/promo FIRST30
```

4. Gõ lại `/naptien` nếu cần.
5. Bấm gói muốn nạp, ví dụ **50.000đ**.
6. Bot tạo link/QR thanh toán.
7. Bạn mở app ngân hàng, quét QR hoặc bấm link thanh toán.
8. Thanh toán đúng số tiền.
9. Chờ hệ thống cộng Xu tự động.
10. Gõ `/profile` để kiểm tra số dư.

### 6.2. Nếu cổng tự động bận

Nếu bot báo cổng QR tự động đang bận, bot sẽ gửi QR thủ công.

Bạn làm như sau:

1. Quét QR thủ công.
2. Chuyển đúng số tiền.
3. Nội dung chuyển khoản phải có dạng:

```text
AAS <ID Telegram> <Mã đơn>
```

4. Chụp bill.
5. Gửi bill ngay trong chat với bot.
6. Chờ admin kiểm tra và cộng Xu.

### 6.3. Lưu ý khi nạp

- Không tự sửa nội dung chuyển khoản.
- Không chuyển thiếu tiền.
- Không dùng chung một bill cho nhiều đơn.
- Nếu đã nhập promo, phải chọn gói đủ điều kiện từ 50k trở lên.
- Mỗi đơn chỉ dùng 1 promo, không cộng dồn nhiều mã.

---

## 7. CÁCH DÙNG MÃ ƯU ĐÃI VÀ GIFT CODE

### 7.1. Promo code nạp tiền

Promo là mã ưu đãi chỉ cộng thêm Xu sau khi thanh toán thành công. Promo không giảm số tiền phải chuyển.

Ví dụ:

```text
/promo FIRST30
```

Sau đó nạp từ 50k trở lên.

Các mã thường dùng:

| Mã | Ý nghĩa | Điều kiện |
|---|---|---|
| FIRST30 | Nạp lần đầu từ 50k: +30% Xu | nên dùng trước |
| SECOND15 | Nạp lần 2 từ 50k: +15% Xu | dùng sau FIRST30 |
| MONTHLY20 | Ưu đãi tháng từ 100k: +20% Xu | khi nạp lớn hơn |
| WEEKLY10 | Ưu đãi tuần từ 50k: +10% Xu | dùng theo chương trình |
| DAILY5 | Ưu đãi ngày từ 50k: +5% Xu | ưu đãi nhỏ |
| BETA50 | Mã beta giới hạn | không phải lúc nào cũng có |

### 7.2. Gift code

Gift code là mã tặng Xu trực tiếp. Với mã public hợp lệ, Xu cộng ngay, không cần nạp tiền.

Riêng mã có tiền tố BETA là mã test/sự kiện đặc biệt. User thường không tự nhận BETA nếu admin chưa cấp cho đúng ID Telegram.

Ví dụ:

```text
/gift THANK100
```

hoặc:

```text
/nhanqua SORRY100
```

Nếu admin/hỗ trợ yêu cầu, gõ `/myid` để lấy ID Telegram rồi gửi cho admin. Admin cấp mã BETA bằng ID đó; sau khi cấp, hệ thống mới cộng Xu.

Các mã BETA như BETA5, BETA10, BETA20, BETA100, BETA200, BETA500, BETA1000 chỉ dùng trong chương trình test/sự kiện đặc biệt. Mã có thể hết lượt hoặc mỗi người chỉ dùng một lần.

---

## 8. QUY TRÌNH 1 - TẠO VIDEO REVIEW SẢN PHẨM ĐỂ TỰ ĐĂNG

Đây là quy trình quan trọng nhất cho khách.

### 8.1. Bạn cần chuẩn bị gì?

Trước khi gõ lệnh, chuẩn bị 5 thông tin:

1. Sản phẩm là gì?
2. Ai là người mua?
3. Đăng ở đâu: TikTok, Facebook Reels, YouTube Shorts?
4. Muốn giọng văn thế nào: gần gũi, chuyên gia, hài hước, sang trọng?
5. Có link sản phẩm không? Nếu có thì dán trực tiếp vào prompt.

### 8.2. Lệnh mẫu cực dễ

```text
/film topic="review máy xay sinh tố mini cho mẹ bỉm" platform="tiktok" tone="gần gũi, dễ hiểu" goal="bán hàng" link="https://link-san-pham-neu-co"
```

Nếu bạn không thích dùng dấu ngoặc, có thể gõ tự nhiên:

```text
/film review máy xay sinh tố mini cho mẹ bỉm, đăng TikTok, giọng gần gũi, mục tiêu bán hàng, có CTA mua hàng cuối video
```

### 8.3. Bot sẽ trả về những gì?

Thông thường bạn sẽ nhận được các phần:

1. **Ý tưởng video:** video nói về góc nào.
2. **Hook 3 giây đầu:** câu mở đầu để giữ người xem.
3. **Kịch bản nói:** nội dung voice hoặc lời thoại.
4. **Storyboard:** chia cảnh 1, 2, 3, 4...
5. **Scene prompt:** prompt để tạo cảnh/video/ảnh AI.
6. **Caption:** nội dung đăng bài.
7. **Hashtag:** hashtag gợi ý.
8. **CTA:** câu kêu gọi hành động.

### 8.4. Làm gì tiếp sau khi bot trả kết quả?

Làm theo thứ tự này:

1. Đọc phần Hook, xem có đủ cuốn không.
2. Đọc kịch bản, sửa lại tên sản phẩm, giá, ưu đãi nếu cần.
3. Copy từng scene prompt để tạo hình/video AI bằng công cụ bạn có.
4. Copy phần kịch bản để tạo voice nếu cần.
5. Ghép video, voice, caption/subtitle trong CapCut hoặc công cụ dựng video.
6. Copy caption và hashtag.
7. Tự đăng lên TikTok/Facebook/YouTube.
8. Sau 24-48 giờ, lưu lại view/like/comment/click.
9. Dùng `/growth_ai` hoặc `/performance_add` để bot gợi ý tối ưu.

### 8.5. Mẫu câu nếu bạn không biết viết chủ đề

Copy một trong các mẫu này:

```text
/film tạo video 30 giây giới thiệu sản phẩm [tên sản phẩm], khách hàng là [ai], đăng TikTok, giọng gần gũi, mục tiêu kéo inbox
```

```text
/film tạo video review thật tự nhiên cho [tên sản phẩm], nêu 3 lợi ích chính, không nói quá đà, có CTA cuối video
```

```text
/film tạo video so sánh trước và sau khi dùng [tên sản phẩm], nhưng tránh cam kết tuyệt đối, đăng Facebook Reels
```

---

## 9. QUY TRÌNH 2 - TẠO 3 VIDEO MỖI NGÀY CHO MỘT SẢN PHẨM

Nếu bạn muốn làm đều nội dung mỗi ngày, làm như sau:

### Buổi sáng

1. Chọn 1 sản phẩm hoặc 1 chủ đề.
2. Gõ:

```text
/film cho tôi 3 ý tưởng video ngắn về [sản phẩm/chủ đề], mỗi video 30 giây, đăng TikTok, mục tiêu kéo tương tác và inbox
```

3. Chọn 1 ý tưởng dễ làm nhất.
4. Nếu muốn bot viết chi tiết hơn, gõ tiếp:

```text
Viết chi tiết video số 1 thành kịch bản, storyboard, prompt cảnh, caption và hashtag
```

### Buổi trưa

1. Dùng script để quay hoặc tạo video.
2. Tạo voice nếu cần.
3. Ghép video và subtitle.

### Buổi tối

1. Đăng video.
2. Ghi lại link bài đăng.
3. Hôm sau nhập số liệu vào bot để tối ưu.

---

## 10. QUY TRÌNH 3 - TỐI ƯU BÀI ĐÃ ĐĂNG

Sau khi đăng bài, đừng đoán mò. Hãy lấy số liệu rồi hỏi bot.

### 10.1. Bạn cần ghi lại

- Link bài đăng.
- Nền tảng: TikTok/Facebook/YouTube.
- Lượt xem.
- Lượt thích.
- Bình luận.
- Chia sẻ.
- Click link hoặc inbox nếu có.
- Doanh thu nếu có.

### 10.2. Nhập số liệu thủ công

Nếu bot có lệnh `/performance_add`, dùng dạng:

```text
/performance_add platform=tiktok views=1200 likes=80 comments=6 shares=3 clicks=12 revenue=0 note="video review máy xay mini"
```

Nếu không nhớ cú pháp, gõ `/help` hoặc nhập tự nhiên:

```text
Tôi đăng TikTok video review máy xay mini, được 1200 view, 80 like, 6 comment, 3 share, 12 click. Hãy phân tích giúp tôi.
```

### 10.3. Dùng Growth AI

Gõ:

```text
/growth_ai
```

hoặc hỏi tự nhiên:

```text
Dựa trên số liệu này, hãy cho tôi biết video yếu ở hook, nội dung, CTA hay sản phẩm. Gợi ý 3 video tiếp theo.
```

Bot sẽ giúp bạn:

- Sửa hook.
- Đổi góc nội dung.
- Viết CTA mạnh hơn.
- Chọn ý tưởng video tiếp theo.
- Gợi ý caption/hashtag mới.

---

## 11. QUY TRÌNH 4 - TẠO CAPTION, HASHTAG, CTA RIÊNG

Nếu bạn đã có video rồi, chỉ cần caption:

```text
Viết cho tôi 5 caption TikTok cho video review [sản phẩm], giọng tự nhiên, không nói quá đà, có CTA cuối bài
```

Nếu muốn hashtag:

```text
Tạo hashtag cho video [chủ đề], chia thành nhóm hashtag rộng, hashtag ngách, hashtag thương hiệu
```

Nếu muốn CTA:

```text
Viết 10 câu CTA ngắn để kéo inbox cho sản phẩm [tên sản phẩm], không gây phản cảm
```

---

## 12. QUY TRÌNH 5 - BÓC BĂNG ÂM THANH/VIDEO

Dùng khi bạn có video/audio và muốn lấy chữ ra để viết lại nội dung.

Cách làm:

1. Gửi file audio/video vào bot nếu menu hỗ trợ.
2. Chọn công cụ **Bóc Băng AI / STT** nếu có nút.
3. Chờ bot chuyển thành văn bản.
4. Copy văn bản đó để:
   - tóm tắt,
   - viết lại kịch bản,
   - tạo caption,
   - biến thành video mới.

Mẫu yêu cầu sau khi có transcript:

```text
Tóm tắt đoạn này thành 5 ý chính, rồi viết lại thành script TikTok 30 giây
```

---

## 13. QUY TRÌNH 6 - TẠO VOICE-OFF / GIỌNG ĐỌC

Dùng khi bạn có script và muốn tạo giọng đọc.

Cách làm cơ bản:

1. Tạo script bằng `/film` hoặc tự viết.
2. Kiểm tra script không quá dài.
3. Chọn công cụ voice/TTS trong menu nếu có.
4. Dán script vào.
5. Chọn giọng nếu bot có lựa chọn.
6. Tải file audio về.
7. Ghép audio vào video.

Mẹo:

- Script 30 giây nên khoảng 70-90 từ tiếng Việt.
- Câu ngắn, dễ nghe.
- Đừng dùng quá nhiều dấu chấm phẩy.
- Đọc lại bằng mắt trước khi tạo voice.

---

## 14. QUY TRÌNH 7 - XỬ LÝ ẢNH / TÁCH NỀN / PROMPT HÌNH ẢNH

Dùng khi bạn cần ảnh sản phẩm, ảnh minh họa, thumbnail hoặc hình nền.

Cách làm:

1. Gửi ảnh vào bot nếu công cụ hỗ trợ.
2. Chọn tách nền/xử lý ảnh nếu có nút.
3. Nếu cần prompt hình ảnh, hỏi bot:

```text
Viết prompt tạo ảnh thumbnail TikTok cho sản phẩm [tên sản phẩm], nền sáng, bố cục rõ, có khoảng trống để thêm chữ
```

4. Dùng prompt đó ở công cụ tạo ảnh AI.
5. Kiểm tra ảnh không vi phạm bản quyền, không dùng người thật khi chưa có quyền.

---

## 15. QUY TRÌNH 8 - DÙNG CHAT AI THƯỜNG VÀ CHAT CHUYÊN SÂU

### 15.1. Chat thường

Dùng cho câu hỏi nhanh:

```text
Viết giúp tôi caption bán hàng cho sản phẩm này
```

```text
Cho tôi 10 ý tưởng video về spa tại nhà
```

Chat thường phù hợp với việc nhanh, ngắn, không quá phức tạp.

### 15.2. Chat Pro/Deep

Dùng khi bạn cần suy nghĩ sâu hơn:

- Lập kế hoạch bán hàng.
- Phân tích thị trường.
- Soạn chiến lược nội dung 30 ngày.
- Viết kịch bản dài.
- Sửa nội dung theo nhiều tiêu chí.
- Tối ưu phễu bán hàng.

Ví dụ:

```text
Hãy lập kế hoạch nội dung 14 ngày cho sản phẩm [tên sản phẩm], mỗi ngày 2 video TikTok, chia theo mục tiêu nhận diện, niềm tin, chuyển đổi
```

---

## 16. CHECKLIST TRƯỚC KHI ĐĂNG VIDEO

Trước khi đăng, tự kiểm tra:

- Video có hook trong 3 giây đầu chưa?
- Người xem có hiểu sản phẩm giải quyết vấn đề gì không?
- Có nói quá đà hoặc cam kết tuyệt đối không?
- Có CTA chưa?
- Caption có rõ lợi ích không?
- Hashtag có liên quan không?
- Âm thanh có nghe rõ không?
- Chữ/subtitle có dễ đọc không?
- Có dùng hình/giọng người thật khi chưa có quyền không?
- Có vi phạm chính sách nền tảng không?

Nếu chưa chắc, hỏi bot:

```text
Kiểm tra giúp tôi nội dung này có điểm nào dễ bị nền tảng hạn chế hoặc người xem hiểu sai không?
```

---

## 17. NHỮNG CÂU LỆNH MẪU COPY DÙNG NGAY

### 17.1. Tạo video bán hàng

```text
/film tạo video 30 giây bán [sản phẩm], khách hàng là [nhóm khách], đăng TikTok, giọng gần gũi, có hook mạnh, có CTA inbox
```

### 17.2. Tạo video giáo dục

```text
/film tạo video giáo dục 45 giây về [chủ đề], giải thích dễ hiểu như nói với người mới, đăng Facebook Reels
```

### 17.3. Tạo video review

```text
/film review [sản phẩm], nêu vấn đề trước khi dùng, trải nghiệm khi dùng, lợi ích chính, điểm cần lưu ý, CTA cuối video
```

### 17.4. Tạo caption

```text
Viết 5 caption cho video về [chủ đề], giọng tự nhiên, không quá quảng cáo, có CTA nhẹ
```

### 17.5. Tối ưu hook

```text
Cho tôi 20 hook 3 giây đầu cho video về [sản phẩm/chủ đề], ưu tiên tò mò nhưng không giật tít quá đà
```

### 17.6. Phân tích bài đã đăng

```text
Video của tôi có 3000 view, 120 like, 8 comment, 5 share, 15 click nhưng chưa có đơn. Hãy phân tích lý do và gợi ý 5 video tiếp theo
```

---

## 18. LỖI THƯỜNG GẶP VÀ CÁCH XỬ LÝ

### 18.1. Bot báo thiếu Xu

Làm như sau:

1. Gõ `/profile` xem còn bao nhiêu Xu.
2. Gõ `/naptien` để nạp thêm.
3. Nếu có mã ưu đãi, nhập `/promo MÃ` trước khi chọn gói.

### 18.2. Không thấy Xu cộng sau khi chuyển khoản

1. Kiểm tra bạn chuyển đúng số tiền chưa.
2. Kiểm tra nội dung chuyển khoản có đúng dạng AAS chưa.
3. Nếu là QR thủ công, gửi ảnh bill vào bot.
4. Chờ admin duyệt.

### 18.3. Kết quả video quá chung chung

Hãy bổ sung thêm:

- tên sản phẩm,
- nhóm khách hàng,
- nền tảng đăng,
- thời lượng video,
- giọng văn,
- mục tiêu,
- điểm khác biệt của sản phẩm.

Mẫu sửa:

```text
Viết lại cụ thể hơn cho khách nữ 25-35 tuổi, dùng giọng thân thiện, không quá quảng cáo, video 30 giây
```

### 18.4. Caption nghe giả hoặc quá AI

Gõ:

```text
Viết lại caption này tự nhiên hơn, giống người bán hàng thật nói, bớt văn mẫu, không dùng từ quá bóng bẩy
```

### 18.5. Không biết nên đăng nền tảng nào

Hỏi bot:

```text
Với sản phẩm [tên sản phẩm], nên ưu tiên TikTok, Facebook hay YouTube Shorts? Hãy giải thích theo khách hàng mục tiêu
```

---

## 19. NHỮNG GÌ TOAN AAS HIỆN CHƯA LÀM CHO KHÁCH

Để khách không hiểu nhầm, cần nói rõ:

- TOAN AAS hiện chưa tự đăng bài cho khách.
- TOAN AAS hiện chưa kết nối tài khoản Facebook/TikTok/YouTube của khách.
- TOAN AAS hiện chưa chạy quảng cáo hộ khách.
- TOAN AAS hiện chưa nhận thẻ thanh toán hoặc mật khẩu của khách.
- TOAN AAS hiện chưa cam kết doanh thu.
- Kho affiliate/link sản phẩm là phần admin/internal hoặc kế hoạch lớn sau này, chưa public cho khách.

Khách hiện tại nhận được: **nội dung, script, prompt, caption, hashtag, CTA, hướng tối ưu để tự đăng.**

---

## 20. QUY TRÌNH TƯƠNG LAI CHO ADMIN - KHÔNG PHẢI CHO KHÁCH V1

Sau này, khi admin test ổn, TOAN AAS có thể có pipeline:

```text
Trend Finder
→ chọn trend
→ tạo ngữ cảnh/kịch bản
→ tạo prompt cảnh
→ tạo video AI
→ tạo voice
→ tạo caption/hashtag/CTA
→ risk check
→ gửi admin duyệt
→ admin duyệt
→ đưa vào publish queue
→ post MXH
→ lưu URL
→ theo dõi hiệu quả
→ đưa dữ liệu về Growth AI
```

Nhưng hiện tại quy trình này chỉ là **admin-first/internal test**. Khách chưa dùng phần tự đăng/publish tự động.

---

## 21. KỊCH BẢN HƯỚNG DẪN KHÁCH LẦN ĐẦU - NHÂN VIÊN CÓ THỂ COPY GỬI

Chào bạn, đây là cách dùng TOAN AAS đơn giản nhất:

1. Vào Telegram tìm **@toanaasbot**.
2. Bấm **START**.
3. Gõ `/profile` để xem Xu trải nghiệm.
4. Muốn tạo video thì gõ:

```text
/film chủ đề bạn muốn làm video
```

Ví dụ:

```text
/film review máy lọc không khí mini cho phòng ngủ, đăng TikTok, giọng gần gũi, video 30 giây
```

5. Bot sẽ tạo kịch bản, prompt cảnh, caption, hashtag.
6. Bạn đọc lại, sửa thông tin sản phẩm nếu cần.
7. Bạn tự dùng nội dung đó để làm video và đăng lên nền tảng của mình.
8. Nếu cần nạp thêm Xu, gõ `/naptien`.
9. Nếu có mã ưu đãi, gõ `/promo MÃ` trước khi nạp.

Lưu ý: Bot hỗ trợ tạo nội dung/video pack để bạn tự đăng, chưa tự đăng bài hoặc chạy quảng cáo hộ bạn.

---

## 22. TÓM TẮT 1 TRANG CHO KHÁCH

**TOAN AAS dùng để làm gì?**  
Tạo ý tưởng, script, prompt cảnh, caption, hashtag, CTA, voice/media hỗ trợ làm nội dung ngắn.

**Dùng thế nào?**  
Mở @toanaasbot -> `/start` -> `/profile` -> `/film chủ đề` -> lấy kết quả -> tự đăng.

**Nạp tiền thế nào?**  
`/khuyenmai` -> `/promo MÃ` nếu có -> `/naptien` -> chọn gói -> quét QR.

**Khách có cần biết prompt không?**  
Không cần giỏi prompt. Cứ nói mục tiêu rõ ràng, bot sẽ giúp viết lại.

**Có tự đăng bài không?**  
Chưa. Khách tự đăng. Phần đăng tự động là kế hoạch admin/internal sau này.

**Có chạy quảng cáo không?**  
Chưa. TOAN AAS hiện không nhận tài khoản, mật khẩu hoặc thẻ thanh toán của khách.

**Tại sao nên dùng?**  
Vì bot gom quy trình tạo nội dung vào một nơi, dễ dùng bằng Telegram, có tiếng Việt, có Xu rõ ràng, có kịch bản/caption/prompt/CTA theo nền tảng, giúp tiết kiệm thời gian hơn so với tự dùng nhiều công cụ rời rạc.
