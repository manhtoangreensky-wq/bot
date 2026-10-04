# MAP: Product Video và kho Ý tưởng Video

Ngày: 05/10/2026. Source: `7bd5b2a86254e16631a9edb74bd40422635b227b`.
Stack: Python, Telegram handlers, SQLite, durable worker, FFmpeg.
Đây là bản đồ phạm vi Product Video, không phải bản đồ toàn hệ sinh thái.
Root: `C:/Users/toann/Documents/Codex/2026-06-25/start-new-codex-thread-p0-17b5-4/work/subdub-smart-receipt-paced-audio`.
Không delegate; nếu sau này Owner mở delegate, phải kèm toàn bộ bản đồ này.

## 1. Module và vai trò

| File | Vai trò |
|---|---|
| `services/video_idea_store.py` | Metadata kho, version và audit; không phải media executor |
| `services/video_idea_catalog.py` | Curated ideas, scene beats, preview/handoff |
| `services/video_idea_prompt.py` | Chọn/sửa prompt, preset detail, return contract |
| `services/video_idea_handoff.py` | Legacy parent session, route và asset context |
| `services/video_uiflow3.py` | Draft AI Prompt/Image, content lock và scene plan |
| `services/video_uiflow3_routeengine.py` | Approved draft sang immutable commercial project |
| `services/video_storyboard2.py` | Panel/images/scenes và storyboard manifest |
| `services/video_selfshot2.py` | Giữ subject, đổi scene/background |
| `services/video_selfshot3.py` | Cinematic one-take, layer rules và timeline |
| `services/video_tail9.py` | Add-on, Review, Quality, Invoice, Confirm, Status |
| `services/video_real_render_connector.py` | Capability/provider/model/output contract |
| `services/multiscene_video_pipeline.py` | Scene materialization và final composition |
| `services/web_product_video_worker_consumer.py` | Worker nhận Product Video contract |

## 2. Entry points

- `bot.py::VIDEO_PUBLIC_ROUTE_MATRIX`: public menu ownership/aliases.
- `bot.py::handle_video_idea_callback`: kho root và compatibility callbacks.
- `bot.py::handle_video_idea_prompt_callback`: namespace chọn prompt.
- `bot.py::video_idea_continue_to_exact_parent`: legacy product return.
- `bot.py::video_uiflow3_accept_idea_candidate`: kho về draft AI Prompt/Image.
- `bot.py::handle_storyboard_callback`: Storyboard riêng.
- `remote_worker.py`: worker entry; không chạy trong task lập plan.

## 3. Dùng chung từ 3 file trở lên

Đếm bằng `rg -l -F` trên `bot.py services tests -g '*.py'`; số là file chứa usage, không phải runtime callsite.

| Symbol | File sở hữu | Số file chứa usage |
|---|---|---|
| `video_idea_handoff.build_parent_handoff` | `services/video_idea_handoff.py` | 7 |
| `video_idea_prompt.select_prompt` | `services/video_idea_prompt.py` | 4 |
| `video_tail9.apply_content_contract` | `services/video_tail9.py` | 18 |
| `video_uiflow3.set_content_candidate` | `services/video_uiflow3.py` | 12 |

## 4. Luồng dữ liệu

Kho metadata -> chọn preset -> snapshot detail/prompt -> parent handoff -> product scene plan/locks -> shared Tail -> final confirm -> durable project/job -> worker -> provider artifact -> validated composition -> delivery.
Root kho không có parent: browse/detail/select target product; không standalone provider job.
Legacy và UIFLOW3 là hai đường vào hiện hữu; không ép tất cả lane qua một đường mới.

## 5. Điểm nhạy cảm

- Schema: `services/video_idea_store.py`, `services/video_project_queue.py`; không migration trong plan này.
- Auth/session: `bot.py`, `services/video_idea_handoff.py`; stale callback không được thay phiên mới.
- Tiền: pricing/settlement/wallet chỉ comparator mock hoặc isolated DB; không sửa quy tắc.
- Đồng bộ: selected prompt/detail phải khớp preview, scene manifest, invoice binding và worker payload.
- Provider: Reference ShopAIKey authority không được đổi thành Storyboard/Self-shot fallback.
- Khóa: Multi/Smart SubDub, `video_local_edit`, Long Video, AI Edit không thuộc remediation.
- `merged != deployed != LIVE`; map không chứng minh runtime success.
