# TOAN AAS Product Workflow

Mục tiêu: lưu nguyên tắc sản phẩm để giữ hướng phát triển ổn định, tránh sửa lan man phần đã pass.

## Ưu tiên hiện tại

TOAN AAS ưu tiên bot Telegram hiện tại tạo doanh thu trước app/platform lớn.

Bot V1 tập trung:

- AI tools dùng hằng ngày.
- Nạp Xu và quản lý số dư.
- Content/video pack để khách tự đăng.
- Provider smoke test admin-first.
- Billing/refund/maintenance guard trước khi mở public tool.

## Phần không sửa lung tung

Không sửa khi task không yêu cầu trực tiếp:

- PayOS, `/naptien`, PayOS webhook, auto cộng Xu.
- `/start`, `/language`, menu i18n.
- Local Worker, ffmpeg, ComfyUI.
- PDF/document tools đã pass.
- Manual bill safety flow.
- Pricing/member tier policy đã khóa.

## Public Feature Rule

Một feature public phải có đủ:

- Billing rõ ràng bằng Xu.
- Xác nhận trước khi trừ Xu.
- Refund nếu provider fail.
- Maintenance/freeze guard.
- Queue/job lock nếu tác vụ lâu.
- UX chờ chuyên nghiệp.
- Không lộ key, token, prompt/response dài hoặc raw provider error.

## Trial Bonus

- Trial 200 Xu chỉ chống spam cho free one-time trial.
- Không áp dụng anti-spam trial vào paid top-up.
- Paid top-up vẫn nhận Xu/gói/khuyến mãi trả phí theo logic hiện tại.
- Không sửa PayOS webhook hoặc paid top-up bonus nếu task không yêu cầu.

## Backlog Thanh Toán / Pháp Lý

Sau khi provider ổn mới xử lý:

- Thanh toán quốc tế.
- Tài khoản nhận USD.
- USDT/crypto nếu có rule pháp lý rõ.
- Tax/accounting automation.
- Invoice/export mở rộng.

## Provider Redundancy Backlog

Provider redundancy là phase sau:

- ShopAIKey
- Key4U
- WokuShop
- OpenRouter/OpenAI/Gemini fallback matrix

Không tự thay default provider khi chưa có test và chỉ đạo.

## Nguyên tắc khóa phần đã pass

- Phần nào live PASS thì khóa lại.
- Chỉ sửa đúng phần task yêu cầu.
- Không refactor callback/menu/state đã ổn.
- Không xóa command/tool/flow.
- Không DROP TABLE, không xóa DB.
