# Hướng Dẫn Xây Dựng Native Micro-Engine (Build-Your-Own-X)

Chuẩn mực xây dựng các engine xử lý cục bộ độc lập, nhẹ và bền bỉ trong TOAN AAS.

---

## 1. NATIVE FFPEG PIPELINE ENGINE

Thay vì sử dụng các thư viện bao bọc nặng nề, xây dựng bộ chuyển đổi câu lệnh FFmpeg trực tiếp:

```python
# Mẫu pipeline nối cảnh và chèn phụ đề / nhạc nền
ffmpeg_cmd = [
    "ffmpeg", "-y",
    "-i", video_input_path,
    "-i", audio_bgm_path,
    "-filter_complex",
    "[0:v]scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2[v];"
    "[1:a]volume=0.15[bgm];"
    "[0:a][bgm]amix=inputs=2:duration=first[a]",
    "-map", "[v]",
    "-map", "[a]",
    "-c:v", "libx264",
    "-preset", "veryfast",
    "-crf", "22",
    "-c:a", "aac",
    "-b:a", "192k",
    output_path,
]
```

---

## 2. EVENT-SOURCING STATE MACHINE NỘI BỘ

Mọi quy trình đa bước (Multi-scene, Long series, Video Storyboard) phải định nghĩa các trạng thái rời rạc và kiểm tra tính toàn vẹn:

1. `Entry` -> Thu thập ý tưởng & phong cách.
2. `Plan` -> Phân cảnh chi tiết, gán nhân vật, bối cảnh.
3. `Prompts` -> Tạo câu lệnh từng cảnh có liên kết ngữ nghĩa.
4. `Tail & Invoice` -> Chọn tỉ lệ, thời lượng, add-on và phát hành hóa đơn.
5. `Execution` -> Thực thi từng cảnh độc lập, kiểm tra artifact và ghép nối hoàn thiện.
