# Local Video Studio 27A — Owner Preview Design

## Owner approval and boundary

Owner đã duyệt 27A sau khi 26I hoàn tất và yêu cầu tiếp tục tự động. 27A là
một sản phẩm preview mới, vì vậy được có UI/flow riêng nhưng tuyệt đối không sửa
UI/UX, callback, state hoặc backstack của Product Video, SubDub, Chỉnh sửa video
hay bất kỳ sản phẩm cũ nào.

Entry duy nhất là lệnh ẩn `/local_video_studio_preview` cho owner/admin đã cấu
hình. Sản phẩm không xuất hiện trong public menu hoặc Admin Center hiện tại.

## Inventory decision

Ba phương án đã được cân nhắc:

1. **Command-only Telegram preview (chọn):** namespace, state và Back riêng;
   kiểm được đúng hành vi Telegram mà không sửa menu cũ.
2. Thêm nút vào Admin Center: dễ tìm hơn nhưng làm thay đổi UI cũ, nên loại.
3. Local CLI/web preview: cô lập tốt nhưng không kiểm được callback/state/Back
   Telegram, nên loại.

Tái sử dụng ngôn ngữ tương tác hiện có: nội dung ngắn, nút tối đa hai cột,
phản hồi ngay khi nhấn và nút Back luôn trở về đúng màn hình cha. Không thêm
animation/media nặng; Telegram callback acknowledgement là feedback chính.

## Architecture

### Pure preview service

Tạo `services/local_video_studio_preview.py` làm source-of-truth 27A:

- đọc `skills/video/local-video-codex-index/capability_index.json` read-only;
- định nghĩa callback namespace `lvs27a` và state key
  `local_video_studio27a_preview`;
- quản lý session, lựa chọn, navigation history và exact route matrix;
- dựng view model gồm text và rows button, không phụ thuộc Telegram runtime;
- không import provider, worker, billing, wallet, database hoặc renderer;
- không ghi file, không gọi mạng, không chạy subprocess và không tạo job.

`bot.py` chỉ là adapter hẹp: import service, mở preview bằng command admin,
chuyển view model thành `InlineKeyboardMarkup`, xử lý callback exact prefix và
giữ session trong `context.user_data`.

### State contract

Mỗi user có đúng một state riêng dưới key 27A:

```text
version: 27A
screen: home | flow screen | catalog screen | safety screen | complete
history: ordered parent screens
mode: create | edit | catalog | safety | empty
selections: create/edit choices only
catalog_page: non-negative integer
pack_id: selected capability record or empty
pack_page: non-negative integer
```

`Back` pop đúng một phần tử history. `Home` đưa về home và xóa history nhưng
không đi sang menu sản phẩm khác. `Close` xóa riêng state 27A và đóng keyboard.
Không dùng `USER_PENDING`, Product Video session, SubDub state hoặc global
backstack.

## Vietnamese preview flows

### Home

- `🎬 Tạo video mới` → bước mục tiêu tạo mới;
- `🎞 Chỉnh footage có sẵn` → bước mục tiêu chỉnh sửa;
- `🧰 Kho capability` → danh sách 11 pack local/free;
- `🛡 QA & khóa an toàn` → 19 QA checks và ba paid-provider locks;
- `✖️ Đóng preview` → kết thúc preview, không về public menu.

### Tạo video mới

Quy trình exact:

```text
Mục tiêu → Định dạng → Phong cách → Âm thanh → Xem lại → QA → Hoàn tất
```

Lựa chọn chỉ lập kế hoạch. Âm thanh cho phép owner-supplied/licensed, sound
design local hoặc silence; không có lựa chọn Suno/generation. Màn hoàn tất phải
ghi rõ không tạo MP4, không chạy provider và không trừ Xu.

### Chỉnh footage có sẵn

Quy trình exact:

```text
Mục tiêu chỉnh → Nguồn/quyền → Định dạng giao → Xem lại → QA → Hoàn tất
```

Đây là flow preview bên ngoài menu Chỉnh sửa video. Không nhận upload, không
gọi edit engine và không gắn nút vào sản phẩm cũ trong 27A.

### Capability catalog

Hiển thị 11 record local/planning: OpenMontage và 26C–26H. Danh sách pack và
qualified IDs được phân trang để callback dưới 64 bytes. Tất cả 248 local IDs
phải xem được qua catalog. Ba paid-provider IDs chỉ xuất hiện ở safety screen
với trạng thái disabled; tổng coverage vẫn là 251 IDs từ 26I.

### QA and locks

Hiển thị đủ 19 ID 26H, readiness thật và counters bằng 0. Motion, Higgsfield và
Suno luôn disabled; nút không được tạo paid smoke, generation, download hoặc
credential flow.

## Callback contract

Tất cả callback có dạng `lvs27a|verb|value|page` và tối đa 64 bytes. Verbs được
allowlist: `open`, `pick`, `catalog`, `pack`, `qa`, `back`, `home`, `close`.
Mỗi nút có đúng một route/action. Callback sai namespace, verb, value hoặc page
fail closed, hiện alert và không đổi state/message.

Callback command và callback handler đều phải qua `is_admin_user`. User không
có quyền không được tạo state và không được xem nội dung preview.

## Failure and truth behavior

- Index thiếu/sai schema: hiển thị lỗi local rõ ràng và đường về home/close;
- session thiếu/stale: khởi tạo home an toàn rồi xử lý allowlisted action;
- page ngoài range: clamp về page hợp lệ, không crash;
- edit Telegram thất bại không được báo capability/render thành công;
- completion chỉ là `PREVIEW_COMPLETE`, không phải render/production success.

## Tests and acceptance

Focused 27A tests phải chứng minh:

- command hidden/admin-only và callback namespace riêng;
- state key, route matrix và backstack không giao với sản phẩm khác;
- create/edit flow order exact và mọi Back về đúng cha;
- mọi button callback allowlisted, ≤64 bytes và không cross-product route;
- 14 records/251 IDs từ index được catalog/safety cover, gồm 248 local IDs;
- 19 QA IDs và paid locks exact;
- no provider/network/subprocess/file-write/job/wallet/deploy code;
- `bot.py` chỉ có import, hai handlers và registrations 27A hẹp;
- Product Video/SubDub/menu/router/renderer/worker files không đổi;
- local preview render mọi screen/page không exception;
- focused 26C–26I regression không có failure mới.

## Immutable counters

```text
provider calls = 0
Motion calls = 0
Higgsfield generation calls = 0
paid generations = 0
wallet/Xu mutations = 0
Telegram deliveries = 0
background jobs = 0
production deploys = 0
VPS updates = 0
```

27A không deploy. Public integration chỉ thuộc task 27B sau khi callback matrix,
state-flow, backstack, focused navigation, local preview, QA và no-cross-product
tests đều PASS.
