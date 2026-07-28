# Local Video Studio 26E Sound Design Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tạo bộ hợp đồng sound-design/audio-post planning-only, nguyên bản,
đủ 10 layer, 14 operation, 9 timeline fields, 5 loudness profiles và 10 QA
checks mà không sửa runtime hay UI.

**Architecture:** Năm JSON tĩnh được `SKILL.md` định tuyến và liên kết tới
rights contract 26C cùng design spec. Focused test chỉ đọc JSON/Markdown bằng
stdlib, kiểm tra schema, nội dung tiếng Việt, references, locks và no-fake-
success; không import production module để thực thi.

**Tech Stack:** JSON UTF-8 deterministic, Markdown, Python stdlib/pytest cho
contract tests, Git worktree/branch.

---

## File map

- Create `skills/video/local-video-sound-design/SKILL.md`: hướng dẫn chọn đúng
  contract, giới hạn planning-only, rights và fail-closed.
- Create `skills/video/local-video-sound-design/sound_layers.json`: 10 layer
  records, group `sound_layer`.
- Create `skills/video/local-video-sound-design/audio_post_operations.json`:
  14 operation records, group `audio_post_operation`.
- Create `skills/video/local-video-sound-design/platform_loudness_profiles.json`:
  5 cấu hình platform, không universal target.
- Create `skills/video/local-video-sound-design/sound_timeline_contract.json`:
  9 scene declarations và rights gate.
- Create `skills/video/local-video-sound-design/audio_qa_contract.json`: 10
  fail-closed checks và mapping FFmpeg/ffprobe metadata.
- Create/update `docs/superpowers/specs/2026-07-29-localvideostudio26e-sound-design-design.md`:
  spec đã duyệt ở task này.
- Create/update `docs/superpowers/plans/2026-07-29-localvideostudio26e-sound-design.md`:
  kế hoạch này.
- Keep `tests/test_p1_localvideostudio26e_sound_design.py` test-first; chỉ sửa
  nếu phát hiện lỗi kiểm tra, không nới lỏng yêu cầu.

## Task 1: Baseline and RED

- [x] Kiểm tra branch/worktree, baseline `87c9febe853343e09a29de45ac24f7cf2a6225a5`.
- [x] Viết test trước.
- [x] Chạy:
  `python -m pytest --noconftest -q tests/test_p1_localvideostudio26e_sound_design.py`.
- [x] Kết quả mong đợi đã xác nhận: thiếu sáu file pack, `1 failed, 2 passed,
  9 skipped`.

## Task 2: Static contracts (GREEN)

- [ ] Tạo thư mục đúng tree và `SKILL.md` với frontmatter chỉ có `name` và
  `description`; link cả năm JSON, rights contract và spec bằng path tương đối.
- [ ] Tạo `sound_layers.json` với envelope exact, 10 ID theo thứ tự, metadata
  references hợp lệ, inventory status trung thực và bốn locks.
- [ ] Tạo `audio_post_operations.json` với envelope exact, 14 ID theo thứ tự,
  `dialogue_priority=true` cho mọi operation, order/fallback/failure/validation
  rõ ràng và bốn locks.
- [ ] Tạo `platform_loudness_profiles.json` với năm profile khác nhau, target
  LUFS-I và true-peak ceiling theo profile, `universal_target_allowed=false`.
- [ ] Tạo `sound_timeline_contract.json` với đúng chín declaration fields,
  required keys, validation rules và rights IDs.
- [ ] Tạo `audio_qa_contract.json` với đúng mười checks, evidence bắt buộc,
  fail-closed cho silent/clipped/missing evidence, allowed tools chỉ ffmpeg/
  ffprobe và `execution_in_26e_allowed=false`.

## Task 3: GREEN and static validation

- [ ] Chạy focused 26E test; nếu fail, sửa contract content chứ không sửa test
  để làm yếu yêu cầu.
- [ ] Chạy JSON parse + deterministic formatter check cho năm JSON.
- [ ] Chạy relative-link/tracked-reference/symbol validation qua focused test.
- [ ] Chạy `python -m py_compile tests/test_p1_localvideostudio26e_sound_design.py`.
- [ ] Chạy `git diff --check` và scan binary, URL, secret, network/download
  code, runtime registration, UI/callback/state/backstack.

## Task 4: Regression and scope review

- [ ] Chạy `tests/test_p1_localvideostudio26c_filmmaking_skills.py`.
- [ ] Chạy cả `tests/test_p1_localvideostudio26d_transition_motion_pack.py` và
  `tests/test_p1_localvideostudio26d_transition_audio.py`.
- [ ] Kiểm tra `git diff --name-only` chỉ chứa test 26E, spec/plan và sáu file
  skill; không có bot/UI/renderer/worker/provider/billing.
- [ ] Ghi rõ baseline `bot.py py_compile TIMEOUT` nếu lặp lại timeout; không
  đổi `bot.py`.

## Task 5: Review, commit, PR

- [ ] Đọc lại spec và từng ID/field, thực hiện spec-compliance review.
- [ ] Thực hiện code-quality review độc lập, xử lý mọi finding quan trọng.
- [ ] Commit một commit 26E có message mô tả pack; push đúng branch.
- [ ] Mở một PR 26E, để OPEN, không merge, không deploy, không bắt đầu 26F.
- [ ] Báo exact Head SHA, PR URL/number, tests và toàn bộ hard-lock counters.
