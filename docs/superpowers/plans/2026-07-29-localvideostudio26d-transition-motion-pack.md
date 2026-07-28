# Local Video Studio 26D Transition/Motion Implementation Plan

**Goal:** Thêm một pack planning-only nguyên bản gồm 20 transition, 12
motion-design principles, 10 kinetic typography contracts và mapping kỹ thuật
cục bộ trung thực.

**Architecture:** Một `SKILL.md` định tuyến tới bốn JSON tĩnh. Một focused test
đọc trực tiếp Markdown/JSON, kiểm tra schema, semantics, namespace, quyền,
accessibility và hard locks. Không import hoặc sửa production.

## Phạm vi file

Chỉ tạo tám file đã liệt kê trong đặc tả 26D. Giữ nguyên toàn bộ file 26C và
mọi file production.

## Trình tự

1. Viết focused test với ID, schema, namespace và lock chính xác.
2. Chạy focused test, yêu cầu RED vì skill directory chưa tồn tại.
3. Viết `SKILL.md` ngắn gọn, tiếng Việt, link đúng bốn contract và spec.
4. Viết `transition_grammar.json` với 20 records và chín semantics bắt buộc.
5. Viết `motion_design_principles.json` với 12 records có restraint.
6. Viết `kinetic_typography.json` với 10 records có accessibility đầy đủ.
7. Viết mapping 42 capability theo đúng bảy technology ID và inventory thực.
8. Chạy focused 26D, regression 26C, quick validation và kiểm tra tĩnh.
9. Review requirements/scope rồi review chất lượng nội dung.
10. Commit, push, mở một PR 26D; không merge/deploy và không bắt đầu 26E.

## Lệnh xác minh trọng yếu

```powershell
python -m pytest -q tests/test_p1_localvideostudio26d_transition_motion_pack.py
python -m pytest -q tests/test_p1_localvideostudio26c_filmmaking_skills.py
python -m py_compile tests/test_p1_localvideostudio26d_transition_motion_pack.py
git diff --check
git status --short
```

Nếu baseline compile `bot.py` timeout, ghi `TIMEOUT`; không sửa hoặc tuyên bố
PASS. Test không gọi provider, renderer, Motion, Higgsfield, wallet hoặc UI.
