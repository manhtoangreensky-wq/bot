---
name: local-video-filmmaking
description: Use when Codex must plan Vietnamese video editing grammar, framing, pacing, camera movement, or rights-aware filmmaking decisions from supplied footage and production constraints.
---

# Lập kế hoạch dựng phim cục bộ

## Mục đích

Dùng bộ hợp đồng này để lập kế hoạch dựng phim bằng tiếng Việt, kiểm tra khả
năng của footage và nói rõ giới hạn trước khi đề xuất cắt dựng, bố cục, nhịp kể
hoặc chuyển động máy quay. Đây chỉ là tri thức lập kế hoạch; không phải chức
năng xử lý video hay bằng chứng sản xuất đã sẵn sàng.

## Khi sử dụng

- Cần chọn ngữ pháp cắt dựng, bố cục khung hình, nhịp kể hoặc chuyển động máy.
- Cần đánh giá footage hiện có có đủ góc máy, âm thanh và tính liên tục hay không.
- Cần lập shot list hoặc hướng dẫn quay bổ sung trước khi dựng.
- Cần khai báo quyền sở hữu, giấy phép, đồng thuận và nghĩa vụ công bố tài sản.

## Không sử dụng

- Không dùng để khẳng định footage bất kỳ luôn thực hiện được hiệu ứng dự kiến.
- Không dùng để gọi dịch vụ, kết xuất, giao file, xuất bản hoặc thanh toán.
- Không dùng thay bước xem trước cục bộ, kiểm tra đầu ra hoặc duyệt sản xuất.
- Không suy diễn quyền sử dụng khi thông tin thiếu, bị hạn chế hoặc chưa xác minh.

## Dữ liệu đầu vào bắt buộc

Thu thập mục tiêu video, nền tảng và tỷ lệ khung; danh sách footage kèm thời
lượng, góc máy, chuyển động, âm thanh; kịch bản hoặc thông điệp; nhịp mong muốn;
tài sản chữ, font, nhạc, stock, thương hiệu và người xuất hiện; cùng tám khai
báo trong [yêu cầu quyền](rights_requirements.json).

## Quy trình lập kế hoạch

1. Chọn đúng nhóm: [dựng phim](editing_grammar.json),
   [bố cục](framing_composition.json), [nhịp kể](pacing_storytelling.json) hoặc
   [chuyển động máy](camera_movement.json).
2. Đối chiếu `required_inputs`, `shot_requirements`, âm thanh, thời gian, tỷ lệ
   khung và quy tắc liên tục của capability được chọn.
3. Kiểm tra `readiness`. `LOCAL_PLANNING_READY` chỉ có nghĩa là đủ dữ liệu để
   lập kế hoạch; không có nghĩa là runtime, xem trước hay sản xuất đã sẵn sàng.
4. Điền đủ tám khai báo quyền. Giá trị chưa rõ hoặc bị hạn chế giữ kế hoạch ở
   trạng thái không thực thi.
5. Ghi rõ failure mode, fallback và validation check cho từng quyết định.
6. Trả về kế hoạch có căn cứ từ footage; không tạo job hoặc báo thành công giả.

## Điều kiện phải dừng

Dừng ở mức kế hoạch khi thiếu shot tương thích, thiếu âm thanh sạch, sai trục
hoặc hướng nhìn, không đủ độ phân giải để crop, chuyển động thật chưa được quay,
quyền chưa rõ, hoặc capability yêu cầu runtime chưa được kiểm chứng. Nêu đúng
blocker và đề xuất quay bổ sung hay fallback an toàn; không tự bỏ qua blocker.

## Cổng quyền và nguyên tắc không thành công giả

Mọi kế hoạch phải liên kết đủ tám quyền. `UNKNOWN` và `RESTRICTED` không phải
phê duyệt. Chỉ dùng `NOT_APPLICABLE` khi `notes` nêu rõ lý do không áp dụng.
Không coi hợp đồng JSON hợp lệ, ID tác vụ, đường dẫn rỗng hoặc mô tả ý tưởng là
video hoàn chỉnh. Không nâng `CONTRACT_ONLY` hay
`REQUIRES_PLANNED_SHOOT` thành trạng thái thực thi.

## Đầu ra mong đợi

Trả về capability ID, lý do chọn, readiness, yêu cầu footage, ranh giới âm
thanh/hình ảnh, hướng dẫn thời gian, liên tục, tỷ lệ khung, lỗi có thể gặp,
fallback, checklist xác minh và tám khai báo quyền. Phân biệt rõ:

- `CONTRACT PASS`: cấu trúc và nội dung lập kế hoạch đã qua kiểm tra tĩnh.
- Xem trước cục bộ: chỉ ghi nhận sau một task xem trước riêng có bằng chứng.
- Sẵn sàng production: không được suy ra từ pack này.

Chi tiết thiết kế và giới hạn phạm vi nằm trong
[đặc tả 26C](../../../docs/superpowers/specs/2026-07-28-localvideostudio26c-filmmaking-skills-design.md).
