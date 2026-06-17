# TOAN AAS Friendly Message Audit 2026-06-20

Date: 2026-06-17

## User-facing principles

- No API keys, tokens, signatures or raw provider response.
- No traceback or stack trace.
- No raw env flag such as `ENABLE_OPENAI_IMAGE_EDIT=0` in public user flows.
- No fake success. If provider is missing, say the feature is being maintained/upgraded.
- No Xu deduction before final confirmation.

## Standard messages

Image processing:

> TOAN AAS đang xử lý ảnh của quý khách. Vui lòng chờ trong giây lát, hệ thống sẽ gửi kết quả ngay khi hoàn tất.

Video processing:

> TOAN AAS đang xuất video cho quý khách. Quá trình này có thể mất vài phút tùy độ phức tạp. Bot sẽ tự động gửi kết quả khi hoàn tất.

Subtitle/dub:

> TOAN AAS đang xử lý âm thanh và phụ đề cho video. Vui lòng giữ nguyên cuộc trò chuyện, kết quả sẽ được gửi lại sau khi hoàn tất.

Provider unavailable:

> Tính năng này đang được bảo trì/nâng cấp để đảm bảo chất lượng. TOAN AAS chưa trừ Xu của quý khách. Vui lòng thử lại sau hoặc chọn tính năng khác.

Insufficient Xu:

> Số dư Xu của quý khách chưa đủ để sử dụng gói này. Vui lòng nạp thêm Xu hoặc chọn gói thấp hơn.

Queue busy:

> Hệ thống đang có nhiều yêu cầu xử lý. Quý khách vui lòng chờ trong giây lát, TOAN AAS sẽ tự động tiếp tục khi đến lượt.

## Admin exception

Admin/status commands may show sanitized provider, model, smoke status, feature flag and reason. They must not expose secrets.
