# ShopAIKey Provider Docs / Backlog

Mục tiêu: lưu tóm tắt định hướng tích hợp ShopAIKey để không phải giữ dài trong ChatGPT memory. Đây là backlog kỹ thuật, không mở public nếu chưa có lệnh admin.

## Nguyên tắc hiện tại

- Public image/video vẫn OFF mặc định.
- Admin smoke test không trừ Xu.
- Không log API key, token, prompt đầy đủ, response đầy đủ hoặc URL nhạy cảm.
- Không thay OpenRouter/OpenAI/Gemini làm provider mặc định nếu chưa có task riêng.
- Không mở customer image/video khi chưa có billing, refund, maintenance guard và queue.

## OpenAI-Compatible Format

Các nhóm API cần phân loại và test riêng:

- Chat completions: text/chat/script/prompt brain.
- Responses API: backlog nếu ShopAIKey hỗ trợ rõ.
- Images: chỉ dùng khi model/group có channel hợp lệ.
- Videos: admin-only smoke test trước, public OFF.
- Embeddings: backlog cho search/memory/rag.
- Audio: TTS/STT nếu endpoint ổn.
- Rerank: backlog cho search/ranking.
- Moderation: backlog cho risk checker.
- Realtime: backlog, chưa đưa vào bot V1.
- Models: admin-only model list/status check.

## Anthropic Format

Backlog kiểm tra nếu ShopAIKey hoặc provider khác hỗ trợ Anthropic-compatible:

- `messages`
- `count_tokens`
- vision input
- tool use
- stream
- system prompt handling

Không gửi dữ liệu khách thật cho smoke test nếu chưa có rule bảo mật.

## Google GenAI SDK Format

Backlog kiểm tra nếu provider hỗ trợ Google GenAI-compatible:

- models
- `generateContent`
- `streamGenerateContent`
- embeddings
- vision input
- tool/function calling

Luồng này chỉ dùng admin-first cho đến khi có billing và policy rõ.

## Custom Media

Các endpoint custom cần giữ tách biệt với OpenAI-compatible endpoint:

- Veo/Grok video: admin-only submit/status polling.
- Nano Banana image: admin-only smoke test, public chỉ mở bằng ENV.
- OpenAI/Google/MiniMax TTS: test từng endpoint riêng, không gom nhầm.
- Suno music: backlog, không public nếu chưa có license/cost guard.

## Seller API

Seller API là backlog/sensitive:

- Không tích hợp nếu chưa có yêu cầu trực tiếp.
- Không lưu token/key seller thật trong docs.
- Không gọi seller API từ customer flow.
- Cần có security review trước khi kết nối.

## Ghi chú vận hành

- Khi provider lỗi/no channel/quota/timeout: ghi event đã sanitize, trả message mềm cho user.
- Nếu public billing đã trừ Xu mà provider fail: hoàn Xu theo refund policy.
- Admin xem trạng thái qua `/shopaikey_status`, `/providers`, `/maintenance_status`.
