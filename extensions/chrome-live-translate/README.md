# TOAN AAS Live Translate & Dub — Chrome/Edge Extension MV3

Hệ thống dịch và lồng tiếng thời gian thực (Real-time Speech Recognition, Live Translation & AI Dubbing) trên mọi trang web (Facebook Reels, YouTube, Douyin, Twitter/X, Coursera, v.v.).

---

## 1. Cấu trúc thư mục

```text
extensions/chrome-live-translate/
├── manifest.json       # Khai báo Manifest V3 (tabCapture, offscreen, content_scripts)
├── background.js      # Service worker điều phối phiên và tabCapture streamId
├── offscreen.html     # Worker offscreen giữ AudioContext
├── offscreen.js       # Bắt audio tab, resample 16kHz PCM, Audio Ducking & TTS playback
├── content.js         # Inject floating draggable widget [文 VI] góc phải trên cùng
├── content.css        # Giao diện glassmorphism hiện đại cho phụ đề và widget
├── popup.html         # Menu điều khiển nhanh trên thanh công cụ trình duyệt
├── popup.js           # Xử lý sự kiện Bắt đầu / Dừng dịch
└── README.md          # Tài liệu hướng dẫn
```

---

## 2. Hướng dẫn cài đặt vào Chrome / Edge

1. Mở trình duyệt Google Chrome hoặc Microsoft Edge.
2. Truy cập: `chrome://extensions/` (hoặc `edge://extensions/`).
3. Bật công tắc **Developer mode** (Chế độ dành cho nhà phát triển) ở góc trên bên phải.
4. Bấm vào nút **Load unpacked** (Tải tiện ích đã giải nén).
5. Chọn thư mục:
   `d:\TOANAAS\wt_realtime_translate\extensions\chrome-live-translate`
6. Tiện ích `TOAN AAS Live Translate & Dub` sẽ xuất hiện ngay trên thanh công cụ.

---

## 3. Cách sử dụng

1. Mở bất kỳ tab nào có video (Facebook, YouTube, Douyin, TikTok, Podcast).
2. Bấm vào biểu tượng extension trên thanh công cụ:
   - Chọn chế độ dịch: `Lồng tiếng + Phụ đề song ngữ` hoặc `Chỉ phụ đề dịch`.
   - Chọn ngôn ngữ: `Tiếng Việt`.
   - Chọn giọng: `Nam Minh` hoặc `Hoài My`.
3. Bấm **▶ Bắt đầu dịch tab này**.
4. Widget nổi màu đen bóng mờ sẽ xuất hiện ở góc trên bên phải màn hình:
   - Phụ đề gốc và phụ đề dịch tự động hiển thị từng câu theo thời gian thực.
   - Khi có giọng dịch (TTS), âm lượng video gốc tự động giảm xuống 25% (Audio Ducking) để giọng dịch nổi rõ, sau đó tự động tăng lại 100%.
   - Bạn có thể kéo thả widget đến bất kỳ vị trí nào trên màn hình.
   - Bấm `💾 SRT` để tải toàn bộ phụ đề của buổi xem về máy tính.
