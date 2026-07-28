---
name: local-video-transition-motion
description: Use when Codex must plan Vietnamese video transitions, restrained motion design, or accessible kinetic typography from supplied footage and timing constraints.
---

# Lập kế hoạch chuyển cảnh và motion cục bộ

## Mục đích

Bộ skill này biến yêu cầu chuyển cảnh, nguyên lý chuyển động và chữ động thành
một kế hoạch có thể kiểm tra. Đây là hợp đồng clean-room, planning-only; không
phải bộ lọc FFmpeg, renderer, preset production hay bằng chứng video đã xong.

## Chọn đúng nhóm

- [Ngữ pháp chuyển cảnh](transition_grammar.json): nối hai shot đã có, continuity,
  duration, easing, blur, mask/tracking và audio accent.
- [Nguyên lý motion](motion_design_principles.json): timing, staging và mức độ
  chuyển động; luôn ghi giới hạn khi áp dụng lên footage thật.
- [Kinetic typography](kinetic_typography.json): chữ nhấn, reveal và beat-sync;
  ưu tiên đọc được trên mobile, safe area và reduced motion.
- [Âm thanh tại biên chuyển](transition_audio.json): tám cue âm thanh planning-only;
  kiểm tra timing, gain, ducking và quyền, không chứa asset hoặc lệnh tải.
- [Mapping kỹ thuật](local_implementation_mapping.json): metadata về công cụ
  cục bộ, không phải lệnh cài đặt hoặc lệnh chạy.

## Dữ liệu và quy trình bắt buộc

1. Ghi mục tiêu, nền tảng, tỷ lệ, fps, shot trước/sau, hướng chuyển động, điểm
   cắt, âm thanh, font và quyền tài sản.
2. Chọn đúng `qualified_id`; `transition.mask_reveal` là nối shot còn
   `kinetic_typography.mask_reveal` là hé lộ chữ, không tráo hành vi.
3. Đối chiếu mọi điều kiện đầu vào, duration, easing, blur, mask/tracking,
   accessibility và continuity của record.
4. Đọc mapping như tham khảo. Công cụ `NOT_INSTALLED` hoặc
   `SPECIFICATION_ONLY` không được nâng readiness.
5. Liên kết đủ tám khai báo quyền từ
   [rights contract](../local-video-filmmaking/rights_requirements.json). Quyền
   `UNKNOWN`/`RESTRICTED` giữ kế hoạch ở planning-only.
6. Trả failure condition, fallback và validation checklist cụ thể; không báo
   thành công vì có JSON, task ID hay tên preset.

## Accessibility và reduced motion

Kinetic typography phải giữ chữ trong safe area của profile đích, giới hạn mật
độ ký tự có thể đo, kiểm tra tương phản trên frame đại diện và thử ở kích thước
mobile. `flashing_allowed` luôn là `false`; không truyền nghĩa chỉ bằng màu.
Mỗi record phải có biến thể giảm chuyển động (giữ tĩnh, opacity hoặc cắt đơn
giản) và phải ghi rõ khi nhịp/blur cần rút gọn.

## Điều kiện dừng

Dừng ở mức kế hoạch khi shot không tương thích, thiếu clean plate/mask/tracking,
sai hướng hoặc trục, thiếu dư ảnh để crop, chữ vượt mật độ, audio accent chưa
được cấp quyền, runtime chưa có, hoặc rights chưa xác minh. Fallback không được
bỏ qua blocker. Không gọi Motion, Higgsfield, provider, renderer, worker,
Telegram hay wallet.

Chi tiết schema và phạm vi nằm trong
[đặc tả 26D](../../../docs/superpowers/specs/2026-07-29-localvideostudio26d-transition-motion-pack-design.md).
