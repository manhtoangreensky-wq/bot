# Video & Media Factory Roadmap

## Mục tiêu

Video & Media Factory là trung tâm tạo nội dung/video đa hướng của TOAN AAS. Giai đoạn hiện tại chỉ tạo content pack, script, storyboard, prompt ảnh/video, voice-over text, caption, hashtag và CTA để khách tự kiểm tra, tự dựng và tự đăng.

## Quy trình chính

1. Trend và ý tưởng:
   - Gợi ý trend TikTok, YouTube, Facebook.
   - Gợi ý hook, tiêu đề, góc nội dung và format video.
   - Chỉ dùng nguồn hợp lệ, không crawler/reup nội dung có bản quyền.

2. Tư liệu hợp lệ:
   - Gợi ý từ khóa tìm ảnh/thông tin.
   - Tạo danh sách cảnh/ảnh cần dùng.
   - Tạo prompt ảnh chân thật.
   - Người dùng chịu trách nhiệm đảm bảo quyền sử dụng tư liệu.

3. Dịch và biên tập:
   - Hỗ trợ định hướng dịch/biên tập nội dung nước ngoài khi nguồn hợp lệ.
   - Ưu tiên nguồn tự sở hữu, public domain, Creative Commons phù hợp hoặc có giấy phép.
   - Không dùng để trích dịch/reup truyện, phim, video, ảnh có bản quyền khi chưa được phép.

4. Video pack:
   - Script/storyboard.
   - Prompt ảnh/video.
   - Voice-over text.
   - Caption, hashtag, CTA.
   - Gợi ý thumbnail và checklist rủi ro.

5. Duyệt nội dung:
   - Bot tạo bản nháp.
   - Khách/admin kiểm tra trước khi dùng.
   - Nếu bản đầu chưa đúng yêu cầu, có thể tạo lại 1 lần theo chính sách gói.
   - Sau khi khách duyệt/tải xuống, chỉnh sửa lớn có thể tính thêm Xu dịch vụ.

6. Tải xuống và tự đăng:
   - Khách tự tải/tự dùng nội dung để dựng hoặc đăng.
   - TOAN AAS không cam kết viral, view, duyệt quảng cáo hoặc doanh thu.

## Admin-Only Publish Backlog

Publish lên TikTok, YouTube, Facebook là backlog admin-only. Không mở cho khách trong giai đoạn Stable Revenue Bot.

Feature flags phải tắt mặc định:

- `admin_publish = 0`
- `customer_publish = 0`
- `auto_publish = 0`
- `youtube_publish_admin = 0`
- `tiktok_publish_admin = 0`
- `facebook_publish_admin = 0`

Khi làm sau:

1. Admin kết nối tài khoản admin-owned hoặc tài khoản được ủy quyền rõ ràng.
2. Bot tạo draft.
3. Risk checker chạy trước.
4. Admin duyệt.
5. Chỉ sau khi duyệt mới đưa vào publish queue.
6. Ghi audit log cho mọi hành động publish.
7. Không tự retry vô hạn.
8. Customer publish vẫn OFF cho đến khi admin mở riêng bằng task mới.

## Guardrails

- Không bypass watermark, DRM hoặc Content ID.
- Không deepfake mặt/giọng người thật khi chưa có quyền.
- Không thu mật khẩu tài khoản mạng xã hội.
- Không thu thông tin thẻ thanh toán.
- Không auto publish nếu chưa có approval gate.
- Không quảng cáo rằng hệ thống có thể đảm bảo doanh thu hoặc lượt xem.

## Commands Hiện Tại

- `/media_factory` — xem trung tâm Video & Media.
- `/media_factory <chủ đề>` — tạo pack trend/script/ảnh/video/caption.
- `/video_factory_flow` — xem quy trình trend → ảnh → dịch → video → duyệt.
- `/trend_ai <chủ đề>` — gợi ý trend/content angle.
- `/image_prompt <chủ đề>` — tạo prompt ảnh chân thật.
- `/image_to_video_pack <chủ đề>` — tạo prompt video từ ảnh.
- `/content_policy` — quy định nội dung/bản quyền.

## Roadmap Sau

- Dịch/lồng tiếng chuyên sâu.
- Source rights checklist.
- AI Story Video Factory an toàn.
- Motion prompt library.
- Admin review queue.
- Admin publish sandbox.
- Performance tracking đưa về Growth AI.
