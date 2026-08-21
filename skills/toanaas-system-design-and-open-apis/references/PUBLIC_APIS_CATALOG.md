# Danh Mục Tuyển Chọn Public APIs Mở Cho TOAN AAS

Tổng hợp các API công khai, miễn phí và ổn định có thể tích hợp vào `free_tools_hub.py`, `media_provider_router.py` và các module tiện ích mở rộng của bot.

---

## 1. MEDIA, VIDEO & HÌNH ẢNH

| Tên API | Mô tả | Xác thực | Giới hạn / Ghi chú | Điểm tích hợp đề xuất |
| :--- | :--- | :---: | :--- | :--- |
| **Unsplash API** | Tìm kiếm và tải ảnh độ phân giải cao miễn phí | API Key (Free) | 50 req/hour | Tạo ảnh nền, tài nguyên storyboard |
| **Pexels API** | Kho video ngắn và ảnh stock chất lượng cao | API Key (Free) | 200 req/hour | Video B-roll, cảnh chuyển tiếp |
| **Pixabay API** | Kho media miễn phí (ảnh, video, nhạc, SFX) | API Key (Free) | 100 req/min | Thư viện âm thanh, nhạc nền video |
| **QR Code Generator API** | Tạo mã QR nhanh cho link thanh toán/website | Không | Không giới hạn | Tiện ích bot tạo mã QR |
| **RoboHash API** | Tạo avatar AI độc đáo từ chuỗi text/ID | Không | Không giới hạn | Avatar nhân vật AI mặc định |

---

## 2. NGÔN NGỮ, DỊCH THUẬT & NLP

| Tên API | Mô tả | Xác thực | Giới hạn / Ghi chú | Điểm tích hợp đề xuất |
| :--- | :--- | :---: | :--- | :--- |
| **LibreTranslate API** | Dịch thuật mã nguồn mở đa ngôn ngữ | Không / Key | Miễn phí theo instance | Dịch phụ đề, dịch prompt |
| **MyMemory Translation** | Bộ nhớ dịch thuật dịch nhanh 50+ ngôn ngữ | Không | 1000 từ/ngày (Free) | Fallback dịch thuật kịch bản |
| **LanguageTool API** | Kiểm tra ngữ pháp và chính tả tiếng Việt / Anh | Không / Key | 20 req/min | Kiểm tra lời thoại, kịch bản |
| **Datamuse API** | Tra cứu từ đồng nghĩa, vần điệu, liên tưởng | Không | 100.000 req/day | Gợi ý từ khóa viết kịch bản AI |

---

## 3. TÀI CHÍNH, TỶ GIÁ & DỮ LIỆU THỰC TẾ

| Tên API | Mô tả | Xác thực | Giới hạn / Ghi chú | Điểm tích hợp đề xuất |
| :--- | :--- | :---: | :--- | :--- |
| **ExchangeRate-API** | Tra cứu tỷ giá ngoại tệ USD/VND thời gian thực | API Key (Free) | 1.500 req/month | Bảng quy đổi Xu quốc tế |
| **CoinGecko API** | Dữ liệu giá tiền mã hóa và thị trường | Không | 10-30 req/min | Tiện ích tra cứu thị trường crypto |
| **Open-Meteo API** | Dự báo thời tiết chi tiết theo tọa độ GPS | Không | Không giới hạn phi thương mại | Tiện ích thời tiết đời sống |
| **REST Countries API** | Tra cứu thông tin quốc gia, múi giờ, tiền tệ | Không | Không giới hạn | Định dạng thanh toán đa quốc gia |

---

## 4. TIỆN ÍCH LẬP TRÌNH & HỆ THỐNG (DEV TOOLS)

| Tên API | Mô tả | Xác thực | Giới hạn / Ghi chú | Điểm tích hợp đề xuất |
| :--- | :--- | :---: | :--- | :--- |
| **GitHub REST API** | Truy vấn repo, commit, release, action runs | Token (Free) | 5.000 req/hour | Kiểm tra phiên bản bot, runtime SHA |
| **IP-API / ipify** | Tra cứu IP công khai và định vị địa lý | Không | 45 req/min | Kiểm tra kết nối mạng VPS/Railway |
| **HTTPBin / Cloudflare Trace** | Kiểm tra request headers, timing và proxy | Không | Không giới hạn | Chẩn đoán mạng và đường truyền bot |
