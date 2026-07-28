---
name: local-video-sound-design
description: Use when Codex must lập kế hoạch sound design, audio post hoặc kiểm tra audio cho video cục bộ bằng tiếng Việt.
---

# Lập kế hoạch sound design và audio post cục bộ

Đây là hợp đồng clean-room planning-only; không đăng ký runtime, không thay
renderer và không chứng minh audio đã hoàn thành.

- [Sound layers](sound_layers.json): vai trò dialogue, room tone, ambience,
  Foley, transition accent, music bed và silence.
- [Audio post operations](audio_post_operations.json): cleanup, lọc, dynamics,
  ducking, fades, balance và đo lường.
- [Platform loudness profiles](platform_loudness_profiles.json): cấu hình theo
  đích; không dùng một target universal.
- [Sound timeline](sound_timeline_contract.json): chín khai báo theo scene.
- [Audio QA](audio_qa_contract.json): evidence và no-fake-success.
- [Transition audio 26D](../local-video-transition-motion/transition_audio.json):
  nguồn canonical cho cue biên chuyển; 26E không chép semantics.

Quy trình: xác nhận đủ tám khai báo trong
[rights contract](../local-video-filmmaking/rights_requirements.json), chọn đúng
qualified ID, ghi timebase/marker/profile/ducking, rồi kiểm tra stream,
duration, silence, clipping, LUFS-I, true peak, kênh, mono và alignment.
Thiếu quyền, runtime, marker hoặc QA thì giữ planning-only và fail closed.

Music/Suno luôn LOCKED_DISABLED; chỉ dùng asset do chủ sở hữu cung cấp và đã
xác minh quyền. Pack không kèm audio asset hoặc lệnh thu nạp. Mọi reference chỉ
là metadata read-only; FFmpeg/ffprobe không chạy trong 26E. Dialogue luôn ưu
tiên hơn music/effect.

Xem [design spec](../../../docs/superpowers/specs/2026-07-29-localvideostudio26e-sound-design-design.md)
và [implementation plan](../../../docs/superpowers/plans/2026-07-29-localvideostudio26e-sound-design.md).
