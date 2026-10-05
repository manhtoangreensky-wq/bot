# Product Video: tiến độ, checklist và điểm dừng

Đang đọc và áp dụng skill owner-governed-codex cho task này.

TASK_ID=PRODUCT_VIDEO_RESUME_PLAN_20261005
STATE=OWNER_APPROVED_PROVIDER_FREE_EXECUTION
MODE=APPROVED_PROVIDER_FREE_CONTROL_PLANE
BASE_SHA=7bd5b2a86254e16631a9edb74bd40422635b227b

## 0. Controller correction / Owner approval

- Owner đã duyệt tiếp tục provider-free execution theo S00-S11. PR #1360 vẫn là control-plane documentation; runtime/test remediation phải ở branch hẹp và chỉ sau RED chứng minh defect.
- Master AN4 final receipt `5983313383` đã tồn tại và `PASS` tại exact Bot/Worker SHA `7bd5b2a86254e16631a9edb74bd40422635b227b`: 106 SAFE_RUN files, 2007/2007 PASS, 17 system matrices PASS, unresolved defects=0, live/provider=0.
- Vì current `bot/main` vẫn đúng SHA trên, S01 Reference được coi là `EVIDENCE_RECONCILED_PASS_NO_RERUN_UNLESS_MATERIAL_DRIFT`. Không chạy chồng 2007 Reference tests.
- Execution thực tế còn lại: S00, S02-S11. Live/provider/deploy/merge vẫn cần authority riêng.

## 1. Quyết định Owner mới nhất

- **Ý tưởng Video là kho nội dung dùng chung, không phải sản phẩm bán/render độc lập.** Đóng yêu cầu nghiệm thu một sản phẩm standalone `video_idea`; không tạo live job riêng cho kho.
- Kho vẫn hoạt động. Prompt và chi tiết ý tưởng phải đi đúng vào sản phẩm khách đang làm, không chỉ đúng màn hình xem trước.
- Đóng standalone không đồng nghĩa đóng kiểm thử tích hợp kho: phần tích hợp vẫn cần bằng chứng qua từng lane.
- Lập plan, checklist, chia spec, cập nhật GitHub và gửi bản tóm tắt trong chat. Sau đó **dừng chờ Owner duyệt**.
- Không sửa runtime, merge, deploy/restart hoặc live test trong task lập plan.
- Không mở lại Multi/Smart SubDub, Local Edit, Long Video hay AI Edit.

## 2. Đã kiểm tra thực tế trong task này

| Việc | Kết quả / giới hạn bằng chứng |
|---|---|
| Local Git HEAD | `7bd5b2a86254e16631a9edb74bd40422635b227b` |
| GitHub `bot/main` | Cùng SHA; đọc qua GitHub API ngày 05/10/2026 |
| PR đang mở trong repo bot | API trả `[]` trước khi tạo PR plan |
| Tracker hiện hành | [bot#1155](https://github.com/manhtoangreensky-wq/bot/issues/1155), vẫn OPEN |
| Source kho | Đã đọc `video_idea_store`, `video_idea_prompt`, `video_idea_handoff` và các đoạn catalog/consumer liên quan |
| Source consumer | Đã đọc đoạn UIFLOW3 capture/accept ý tưởng, `set_content_candidate`, local scene planner và bridge |
| Runtime VPS ngày 05/10 | **NOT_RECHECKED_IN_THIS_PLANNING_TASK**; không lấy local/GitHub SHA làm runtime truth |
| pytest / provider-free matrix mới | **NOT_RUN**; chưa thực thi kế hoạch |
| Kiểm tra tài liệu mới | PowerShell validator exit `0`: 5 files, 4 local links, 12 spec-plan pairs, 47 source/test paths, unresolved `0` |
| Provider / production job / ví / deploy | **0 / 0 / 0 / 0** trong task này |

Hai file untracked có sẵn `2026-10-03-smart-measured-failures-plan.md` và `2026-10-03-smart-measured-failures-spec.md` không thuộc task này, được giữ nguyên và không đưa vào PR.

## 3. Đối chiếu báo cáo cũ với GitHub mới

| Nguồn | Điều nguồn chứng minh | Không được suy ra |
|---|---|---|
| [R16.09AN3B receipt](https://github.com/manhtoangreensky-wq/bot/issues/1155#issuecomment-5982352702) | Báo cáo lịch sử target binding và safe suite 2.007 PASS trên 106 file | Không phải test được chạy lại hôm nay |
| [Review AN3B](https://github.com/manhtoangreensky-wq/bot/issues/1155#issuecomment-5982409618) | Target đã được đưa lên bằng transaction liên sản phẩm; không cần tự deploy lại | Không phải giấy phép deploy mới |
| [AN4 receipt](https://github.com/manhtoangreensky-wq/bot/issues/1155#issuecomment-5982470946) và [final review](https://github.com/manhtoangreensky-wq/bot/issues/1155#issuecomment-5982823837) | Reference được chấp nhận đóng kỹ thuật provider-free tại thời điểm receipt; live còn hoãn | Không đóng toàn bộ Goal Product Video |
| [Inventory mới](https://github.com/manhtoangreensky-wq/bot/issues/1155#issuecomment-5982970782) | Self-shot A/B, Storyboard còn V2 acceptance; standalone Idea live không bắt buộc | Không cần mở lại mọi lane lịch sử đã PASS |
| [Master audit sau inventory](https://github.com/manhtoangreensky-wq/bot/issues/1155#issuecomment-5983095178) và [START receipt](https://github.com/manhtoangreensky-wq/bot/issues/1155#issuecomment-5983137534) | Reference lại có đợt audit sâu hơn; receipt mới nhất đọc được là `IN_PROGRESS`, không có final receipt của đợt này | Không tự đánh dấu đợt master đã hoàn tất hoặc chạy chồng task |

Giữ nguyên receipt cũ. Không biến nội dung dispatch/expected PASS thành kết quả thực nghiệm.

## 4. Product, kho và baseline phải phân biệt

| Key / nhóm | Phân loại trong plan mới | Việc còn lại |
|---|---|---|
| `video_idea` | **OWNER_CLOSED_AS_STANDALONE_PRODUCT / SHARED_LIBRARY** | Xác minh prompt/detail handoff; không thêm job standalone |
| `video_trend` | Historical/V2 locked | Comparator tích hợp kho; sửa chỉ khi có defect mới được tái hiện |
| `video_ai_prompt`, `video_ai_image` | Sản phẩm; entry parent `video_ai_real` | Kiểm chứng kho qua UIFLOW3, prompt cuối và source-image binding |
| `video_ai_video_reference` | Sản phẩm Reference, không phải Self-shot | Reconcile master audit; bảo toàn source + contract ShopAIKey I2V; live deferred |
| `script_image_video` | Historical/V2 locked | Comparator exact script/detail; không viết lại engine |
| `self_shot_scene_change` | PV2-R05A chưa đóng V2 | Provider-free source/subject/prompt/2-scene/Tail closure |
| `self_shot_cinematic_transform` | PV2-R05B chưa đóng V2 | Provider-free one-take/timeline/layer-lock closure riêng |
| `storyboard_prompt` / `storyboard_to_video` | PV2-R06 chưa đóng | Panel-to-scene/prompt/I2V/concat, không padding giả |
| `frame_video_local` | Baseline riêng; không tự thêm idea lane | Giữ nguyên comparator/menu; không đồng nhất với AI Edit |
| `video_local_edit` | **LOCKED** | Không sửa |
| `multi_scene_film`, `video_long` | **DEFERRED / NOT_AUTHORIZED** | Chỉ backlog; không code/provider/deploy cho lane này |
| `videoedit|ai` | **DEFERRED / NOT_AUTHORIZED** | Không nhầm alias `video_edit` của Local Edit với AI Edit |
| Multi/Smart SubDub | **OWNER_LOCKED** | Không sửa, replay, live hoặc tác động qua shared SubDub |

Strategy V2 cũ còn `PV2-R08 video_idea=PENDING` và assignment quality cho Idea. Tài liệu này ghi override phân loại theo lệnh Owner mới; **chưa chỉnh JSON/registry/runtime hay tự gán assignment đó sang sản phẩm khác**. S02 sẽ đối chiếu và cập nhật tài liệu authoritative sau duyệt, không xoá lịch sử.

## 5. Checklist duyệt và thực thi

Các ô `[x]` dưới đây chỉ là phần lập kế hoạch đã làm. Ô `[ ]` là công việc chưa thực thi.

- [x] P00: xác định SHA, branch, tracker và preserved untracked files.
- [x] P01: đóng yêu cầu standalone Idea theo Owner; giữ integration closure tách riêng.
- [x] P02: đọc source thật, khoanh các boundary cần kiểm chứng; không tuyên bố runtime defect chưa được tái hiện.
- [x] P03: lập spec và plan có file, acceptance, lệnh kiểm chứng và rollback.
- [x] P04: Owner đã duyệt phạm vi thực thi provider-free; live/deploy/merge vẫn khóa riêng.
- [ ] S00: JIT authority, phân loại test, fixture isolation và chứng minh guard chặn outbound.
- [x] S01: final master receipt `5983313383` đã reconcile PASS; chỉ mở lại nếu S00 phát hiện material drift.
- [ ] S02: sửa ledger product/library; kiểm chứng kho không submit/quote/charge độc lập.
- [ ] S03: fixture đầy đủ các trường kho; giữ detail, version và snapshot qua normalizers.
- [ ] S04: selected/custom prompt, scene arc và nội dung bắt buộc đúng đến compiler; không fallback generic làm mất ý.
- [ ] S05: legacy/UIFLOW3 parent handoff; đúng product, owner, phiên, revision, assets; stale/back/cancel không side effect.
- [ ] S06: consumer từng lane; so sánh snapshot kho với scene manifest, provider payload mock và Tail.
- [ ] S07: Self-shot Scene Change, một product riêng, source/subject locks và artifact offline.
- [ ] S08: Self-shot Cinematic, một product riêng, one-take/timeline/layer locks.
- [ ] S09: Storyboard, một product riêng, panel identity và no-fake-padding.
- [ ] S10: full safe matrix, baseline/branch, order independence, protected comparators.
- [ ] S11: review PR sửa, cập nhật checkpoint được xác minh, báo Owner; merge/deploy/live vẫn có gate riêng.

Thứ tự: `P04 -> S00 -> S01 -> S02 -> S03 -> S04 -> S05 -> S06 -> S07 -> S08 -> S09 -> S10 -> S11`. S01 có overlap thì không chiếm quyền sửa Reference; có thể hoàn thiện tài liệu nhưng không chạy task runtime chồng.

## 6. Defect ledger và rollback ledger

**Chưa có runtime defect mới được xác nhận bằng replay/test trong task lập plan.** Các điểm nghi ngờ ở spec là audit targets, không phải danh sách bug đã chứng minh.

Mỗi defect sau duyệt phải có một hàng:

`DEFECT_ID | product | expected | observed | failing node/fixture | root cause | allowed hunks | fix commit | focused result | regression result | status`.

Mỗi checkpoint sau sửa phải có một hàng:

`product | fixed defect IDs | PR | head SHA | merged SHA | test receipt | deployed SHA/NO | live receipt/NOT_RUN | previous verified checkpoint | rollback scope`.

Không lấy số PR mới nhất làm rollback mặc định. Chỉ thăng checkpoint khi đúng product, đúng SHA và đủ test/comparator; nếu chưa deploy thì chỉ là source checkpoint. Không rollback toàn `main` để sửa một lane, vì có thể bỏ các bản sửa ví/Voice TTS/SubDub không liên quan. Production rollback phải có Owner duyệt riêng.

## 7. Hồ sơ duyệt

- [Bản đồ phạm vi](MAP.md).
- [Spec chi tiết](../superpowers/specs/2026-10-05-product-video-provider-free-closure-spec.md).
- [Plan từng bước và lệnh verify](../superpowers/plans/2026-10-05-product-video-provider-free-closure-plan.md).
- [State có thể tiếp tục](../../.agents/state/product-video-resume-plan-20261005.yaml).
- GitHub: PR plan documentation-only; tracker #1155 giữ OPEN. Không `Closes #1155`.

## 8. Receipt task lập plan

```text
TASK=PRODUCT_VIDEO_RESUME_PLAN_20261005
BASE_SHA=7bd5b2a86254e16631a9edb74bd40422635b227b
HEAD_SHA=SEE_PLANNING_PR_EXACT_HEAD
FILES_CHANGED=5 documentation/state files; runtime changes=0
TESTS=DOCUMENT_VALIDATOR exit 0: files=5, local_links=4, spec_plan_pairs=12, source_test_paths=47, unresolved=0; runtime pytest=NOT_RUN
BASELINE_FAILURES=NOT_RUN_PLANNING_ONLY
BRANCH_FAILURES=NOT_RUN_PLANNING_ONLY
NEW_FAILURES=UNKNOWN_RUNTIME_TESTS_NOT_RUN
PROTECTED_COMPARATORS=ZERO_DIFF_OUTSIDE_DECLARED_DOCUMENTATION
PROVIDER_CALLS=0
PRODUCTION_JOB_CREATION=0
WALLET_MUTATIONS=0
DEPLOY=NO
RUNTIME_SHA=NOT_RECHECKED_IN_THIS_PLANNING_TASK
LIVE_PASS=NOT_TESTED
BLOCKERS=NONE_FOR_PROVIDER_FREE_EXECUTION; LIVE_DEPLOY_MERGE_SEPARATELY_LOCKED
LESSON_CANDIDATE=NONE
NEXT_STATE=OWNER_APPROVED_PROVIDER_FREE_EXECUTION
STOP=YES
```
