---
name: local-video-viral-effects
description: Use when Codex must lập kế hoạch viral video effects từ footage có điều kiện quay, mask, tracking và rights rõ ràng.
---

# Lập kế hoạch mười viral video effects

Pack này là đặc tả clean-room planning-only cho mười effect; không phải
renderer, preset production, runtime registry hay public UI.

- [Viral effects contract](viral_effects.json): chọn `viral_effect.<id>` và đọc
  đủ source-shot, camera/plate/mask/tracking, continuity, beat, fallback, rights
  và fixture.
- [Rights contract](../local-video-filmmaking/rights_requirements.json): dùng
  đủ tám khai báo quyền trước khi lập kế hoạch.
- [Transition source 26D](../local-video-transition-motion/transition_audio.json):
  chỉ tham khảo cue/biên chuyển, không sao chép hành vi.
- [Design spec](../../../docs/superpowers/specs/2026-07-29-localvideostudio26f-viral-effects-design.md):
  xem boundary và acceptance.

## Quy trình

1. Xác định source shot, aspect ratio, duration và beat markers.
2. Đánh giá camera lock, clean plate, mask, tracking và continuity trước khi
   chọn effect.
3. Chọn đúng status; không gắn READY_FROM_ARBITRARY_FOOTAGE khi footage chưa
   đủ điều kiện.
4. Kiểm tra privacy, claim, brand, music, font, stock và AI disclosure rights.
5. Dùng local deterministic method như mapping tham khảo; execution_in_26f luôn
   false và optional AI method luôn LOCKED_DISABLED.
6. Nếu thiếu evidence, trả fallback và fail closed; không gọi renderer, model,
   dịch vụ trả phí, wallet hoặc Telegram.

Music/Suno luôn LOCKED_DISABLED. Không thu nạp audio, cover art, lyric hoặc
effect asset chưa xác minh. 26F không thêm nút hay callback vào sản phẩm cũ;
mọi UI/UX sản phẩm mới chỉ được làm trong task sản phẩm mới riêng.

Mọi record giữ planning_only=true, runtime_registered=false,
provider_executable=false, public_ui=false.
