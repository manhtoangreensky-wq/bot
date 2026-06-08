# Video Content Workflow References

Mục tiêu: lưu hướng phân tích video mẫu/reel đã học để phục vụ workflow tạo video sau này.

## Pipeline tham khảo

Trend discovery → hook/script → storyboard → image prompt → image generation → video generation → TTS/caption/music → CTA.

## Style nội dung

Các style cần hỗ trợ trong tương lai:

- AI tutorial.
- Affiliate opportunity.
- Ad hook.
- "Đừng click/docs" curiosity style.
- Screen-record walkthrough.
- Before/after.
- Faceless narration.
- UGC.
- Product demo.
- Cinematic AI.

## Future Workflow Output

Một workflow video đầy đủ cần tạo:

- 10 hook.
- 3 script: 15s / 30s / 60s.
- Storyboard từng cảnh.
- Prompt ảnh.
- Prompt video.
- Voice/TTS suggestion.
- Music suggestion.
- Caption/subtitle.
- CTA/affiliate/ad copy.

## Trend to Video Creative Workflow V1

Command admin-first: `/trend_video_flow <chủ đề>`.

Mục tiêu V1:

- Tạo plan/prompt/script để khách hoặc admin copy nhanh.
- Chưa gọi ShopAIKey image/video public nếu public image/video đang OFF.
- Không trừ Xu khi chỉ tạo hooks/script/storyboard/prompt.
- Không publish, không broadcast, không tự chạy ads.

Output nên chia thành các block ngắn:

1. 10 hook mở đầu.
2. Script 15s, 30s, 60s.
3. Storyboard theo scene.
4. Prompt tạo ảnh 9:16.
5. Prompt tạo video hoặc image-to-video.
6. Gợi ý TTS, nhạc/Suno, caption, hashtag, CTA.

Nút điều hướng chỉ gợi ý bước tiếp theo:

- Tạo prompt ảnh đẹp hơn.
- Tạo prompt video từ ảnh.
- Tạo voice/TTS.
- Tạo nhạc nền.
- Viết lại script.
- Tạo phiên bản ads để admin review.
- Lưu kế hoạch thủ công.

## Image Generation From Trend Workflow V1

Mục tiêu: nối prompt ảnh trong `/trend_video_flow` sang luồng tạo ảnh ShopAIKey có guard.

Nguyên tắc:

- Public image vẫn OFF mặc định qua `SHOPAIKEY_PUBLIC_IMAGE_ENABLED=false`.
- Public video không mở trong bước này.
- Khi workflow tạo xong, bot hỏi "Bạn muốn tạo ảnh từ prompt nào?".
- Scene 1/2/3 chỉ đi tiếp nếu public image ON hoặc admin dùng smoke command riêng.
- Public image ON thì vẫn phải đủ Xu, có job lock, hỏi xác nhận, rồi mới trừ Xu.
- Provider fail/no channel/timeout thì hoàn Xu theo `SHOPAIKEY_REFUND_ON_PROVIDER_FAIL=true`.
- Admin smoke command `/tool_test_workflow_image` không trừ Xu và không mở public.

DB tối giản:

- `trend_workflow_outputs` lưu `workflow_id`, scene, image prompt, video prompt, generated image URL nếu có.
- Không lưu API key.
- Không lưu raw provider response.
- Không lưu prompt quá dài.

## Admin-First Safety

- Publish/video automation là admin-first.
- Customer hiện nhận content/video pack để tự đăng.
- Không auto publish.
- Không chạy ads hộ khách.
- Không cam kết viral/doanh thu.
- Mọi output có yếu tố affiliate/ad cần disclosure và risk check.
- Public image/video generation vẫn OFF cho tới khi admin bật ENV, có billing, refund, queue và job lock.
- Prompt workflow không được gọi provider tạo ảnh/video thật nếu public OFF.

## Lưu ý dữ liệu

- Không lưu API key/token thật.
- Không lưu task_id/result_url cụ thể.
- Không lưu prompt dài nhạy cảm.
- Chỉ lưu pattern/workflow/backlog.
