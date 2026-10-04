# Product Video và kho ý tưởng: Implementation Plan

> Execution sau Owner duyệt: single agent dùng `superpowers:executing-plans`, từng task nhỏ với review checkpoint. Không spawn subagent; không bắt đầu runtime work trong task lập plan này.

**Goal:** Kho cung cấp đúng prompt/detail tới sản phẩm đích; đóng provider-free các Product Video còn thiếu bằng chứng mà không phá baseline ổn định.

**Architecture:** Tái sử dụng kho, hai parent handoff hiện hữu, compiler từng product, Tail và worker hiện có. Tạo regression tại boundary gây mất/sai; chỉ patch hunk tái hiện defect. Không engine/blackbox/framework mới.

**Tech Stack:** Python 3.11, pytest, mock transports, SQLite temp DB, FFmpeg/ffprobe local.

**Spec:** `docs/superpowers/specs/2026-10-05-product-video-provider-free-closure-spec.md`.

## Global Constraints

- `STATUS=PROPOSED_WAIT_OWNER_APPROVAL`; mọi S00-S11 dưới đây **NOT_RUN**.
- `REAL_PROVIDER_CALLS=0`; `PRODUCTION_JOB_CREATION=0`; `PRODUCTION_DB_MUTATION=0`; `WALLET_MUTATIONS=0`; `DEPLOY=0`; `PR_MERGE=0`.
- `video_idea=SHARED_LIBRARY`, standalone product acceptance closed; integration acceptance vẫn pending.
- Multi/Smart SubDub và Local Edit locked; Long Video/AI Edit deferred, không tự mở khi các spec khác PASS.
- Không biến dispatch expectations, test names, HTTP200 hoặc historical PASS thành kết quả mới.
- Execution units: một bước đọc/fixture/assertion/patch/rerun/review, khoảng 2-5 phút mỗi thao tác; test run dài ghi duration thật, không hứa suite hoàn tất trong 5 phút.
- Không sửa signature shared symbol trước impact listing và Owner duyệt phạm vi callers.
- `MAP.html` không cần tạo: plan Python provider-free không cần đồ thị JavaScript toàn repo; bản đồ source scoped đủ cho task.

## 1. Khởi tạo lệnh và bằng chứng

Mọi file ở các task dưới đây có đường dẫn tuyệt đối bằng cách nối vào `$R`:

```powershell
$R = 'C:\Users\toann\Documents\Codex\2026-06-25\start-new-codex-thread-p0-17b5-4\work\subdub-smart-receipt-paced-audio'
$ApprovedBase = '7bd5b2a86254e16631a9edb74bd40422635b227b'
Set-Location -LiteralPath $R
git rev-parse HEAD
git status --short --branch
```

Mong đợi lúc lập plan: base `7bd5b2a86254e16631a9edb74bd40422635b227b`. Khi thực thi phải rebind main thật và cập nhật `$ApprovedBase` sau authority review; drift ghi vào ledger, không auto-rebase/overwrite task khác.

Sau S00 tạo và chứng minh `tests/pv_provider_free_guard.py`, tất cả pytest dưới đây chạy với guard:

```powershell
function pvtest { & python -m pytest -p tests.pv_provider_free_guard @args }
```

Plugin là **test harness đề xuất**, hiện chưa tạo. Không chạy các lệnh `pvtest` cho tới khi guard canary/credential/temp-DB gates của S00 đạt. New test files dưới đây chỉ được tạo sau Owner duyệt, trước implementation. Không dùng `pytest tests/` hoặc wildcard live scripts để thay exact manifest.

## 2. Chu trình áp dụng cho mỗi spec sửa

1. Viết một test expected/actual với fixture độc lập, gán `DEFECT_ID` và product.
2. Chạy riêng test, giữ terminal/JUnit RED. Nếu không RED thì chỉ lưu evidence, không sửa code.
3. `rg -n` toàn callers của symbol; chọn đúng hunk allowed trong spec. Cần mở rộng phạm vi thì dừng xin duyệt.
4. Patch nhỏ nhất bằng `apply_patch`; không rename/refactor, không sửa fallback/provider khác.
5. Chạy focused GREEN, affected cluster rồi comparator baseline/branch.
6. Review diff, cập nhật `docs/product-video/PROGRESS.md` và PR bằng commit/hash/test evidence. Không thăng rollback anchor khi thiếu protected comparator.

## Task S00: authority, isolation và safe manifest

**Read:** `AGENTS.md`, `docs/product-video/PROGRESS.md`, `docs/product-video/MAP.md`, spec, latest #1155, `tests/conftest.py` và `docs/reports/VIDEO_AI_VIDEO_REFERENCE_PROVIDER_FREE_TEST_MANIFEST_R16_09AN1E.md`.

**Create sau duyệt:** `tests/pv_provider_free_guard.py`, `tests/test_p0_product_video_provider_free_guard.py`, `docs/product-video/SAFE_TEST_MANIFEST.md`.

- [ ] JIT main/PR/latest receipt; xác định Reference master có final receipt chưa, tránh task chồng.
- [ ] Phân loại exact candidate tests theo source; fixture files SHA256; không dùng totals 707/106/2007 làm con số mới.
- [ ] Plugin chặn external DNS/socket/HTTP trước collection; credential real và production DB paths không được nạp; FFmpeg chỉ local paths.
- [ ] Canary test thử `socket.getaddrinfo('example.invalid',443)` và `socket.create_connection(('192.0.2.1',443))`: cả hai phải bị guard exception chặn trước transport. Có counter, không nuốt attempt.
- [ ] Tạo DB/cache/artifacts trong temp sandbox; assert không có path tới `/data` hoặc production checkout. Không sửa shared conftest.
- [ ] Verify: `python -m pytest -p tests.pv_provider_free_guard -q tests/test_p0_product_video_provider_free_guard.py`. Mong đợi zero failures; real network=0; guard intercept chứng minh được. Nếu guard chưa chạy được thì **STOP**, không chạy business suite.

## Task S01: reconcile Reference, không audit chồng

**Read:** tracker receipts `5982470946`, `5982823837`, `5983095178`, `5983137534`; `docs/reports/VIDEO_AI_VIDEO_REFERENCE_PROVIDER_FREE_TEST_MANIFEST_R16_09AN1E.md`; connector/consumer files ở spec.

- [ ] Thu final receipt mới nếu có và bind source/manifest/17 matrix proofs; nếu vẫn in-progress thì ghi ownership blocker, không takeover execution.
- [ ] Audit drift hiện có so với receipt, không tự redeploy target đã deploy.
- [ ] Chỉ chạy bổ sung những proof thiếu hoặc bị drift tại exact target, dưới safe manifest; không gọi ShopAIKey.
- [ ] Verify gap-sensitive cluster sau S00: `pvtest -q tests/test_web_product_video_acceptance.py tests/test_p0_web_product_video_settlement_service.py tests/test_p0_product_video_admin_free_admission.py tests/test_p0_product_video_pv10_deterministic_all_product_e2e.py`. Mong đợi zero new failures so với baseline; counts đo mới. Đây không thay full Reference manifest nếu closure đó chưa có.
- [ ] Cập nhật Reference status: historical technical PASS / newest audit result / LIVE_DEFERRED tách riêng.

## Task S02: Idea là kho, không product độc lập

**Read-only audit files:** `services/video_uifreeze1.py`, `services/video_tail9.py`, `services/video_uiflow3_routeengine.py`, `bot.py::VIDEO_PUBLIC_ROUTE_MATRIX`, kho root handlers; `KIEM-THU/PRODUCT-VIDEO-LIVE-STRATEGY-V2.md` và JSON.

**Test mới:** `tests/test_p0_product_video_idea_library_boundary.py`.

- [ ] Các root browse/detail/select/back/cancel/stale callback dùng mocks job/outbox/provider/wallet, assert call counts `0`.
- [ ] Chọn target thật mới đi commercial Tail; `video_idea` không là executor standalone. Deferred targets vẫn blocked; compatibility `video_idea_to_product` không xoá nếu đang phục vụ parent đích.
- [ ] Đối chiếu PV2-R08 và quality assignments; đóng standalone row, chuyển handoff thành integration checklist. Assignment cũ giữ history, chưa reassign/live.
- [ ] Runtime registry chỉ sửa nếu direct paid path còn reachable được RED chứng minh; patch hunk public boundary riêng, không đổi pricing rules.
- [ ] Verify: `pvtest -q tests/test_p0_product_video_idea_library_boundary.py tests/test_p0_video_ideaflow2_restore_catalog_direct_prompt_return.py`. Mong đợi no standalone side effects + embedded compatibility còn đúng; stale expectations phân loại bằng source, không làm mù integration tests.

## Task S03: snapshot đầy đủ, không rơi detail

**Allowed candidate hunks:** `services/video_idea_prompt.py::_preset_content`, `hydrate_parent_state`; `services/video_idea_handoff.py::build_parent_handoff`, `normalize_parent_handoff`, `apply_parent_handoff`; store/catalog chỉ fixture read, không schema/data edit.

**Test mới:** `tests/test_p0_product_video_idea_snapshot_fidelity.py`.

- [ ] Fixture từ `video_idea_store.PRESET_FIELDS`, sentinel riêng mỗi field; list JSON được parse structured; version và full raw customer text được giữ.
- [ ] Snapshot prepare/select/restore bằng deep equality và object independence. Cases: preset inactive/change-version, empty optional, newline/Unicode, text 11999/12000/12001 và 19999/20000/20001 chars.
- [ ] Đo location loss trước patch; test required sentinel/safety note không được mất, accepted long text không silent truncate.
- [ ] RED hunk whitelist/copy nếu cần, không thêm DB column, không tự tăng giới hạn chung.
- [ ] Verify: `pvtest -q tests/test_p0_product_video_idea_snapshot_fidelity.py tests/test_p0_video_ideaprompt1_restore_prompt_selection_return_owner.py tests/test_p0_video_ideaflow2_restore_catalog_direct_prompt_return.py`. Mong đợi snapshot intact và baseline comparator không mới fail.

## Task S04: prompt đúng nội dung và đúng N scene

**Allowed candidate hunks:** `services/video_idea_prompt.py::build_prompt_candidates`, `select_prompt`, `set_custom_prompt`, `_preset_scene_content`; `services/video_idea_catalog.py::semantic_beats_for_idea`; local scene planner hunk chỉ nếu loss xảy ra ở consumer.

**Test mới:** `tests/test_p0_product_video_idea_prompt_semantics.py`.

- [ ] Dùng ít nhất hai preset nội dung khác nhau từ curated fixture và một custom script; không hardcode production sample video.
- [ ] Parametrize N=`1,2,3,5,10,20`, ratios=`9:16,16:9,1:1,4:5`, chọn/refresh/edit/skip; Storyboard skip phải reject theo contract.
- [ ] Assert title/description/hook/objective/scene_arc/templates/seeds/safety tới planning có nghĩa; không chỉ test prompt nonempty. Locked custom scene không bị replan ghi đè.
- [ ] System guidance/template không trở thành quyền gọi API; unresolved placeholder phải có planning error rõ trước confirm.
- [ ] Verify: `pvtest -q tests/test_p0_product_video_idea_prompt_semantics.py tests/test_p0_video_scene3ux4_reference_only_idea_hub.py tests/test_p0_product_video_pv03_script_idea_prompt_truth.py`. Mong đợi exact content coverage, N scene/indices đúng, no generic replacement.

Ví dụ assertion contract cho fixture three-act trong file test mới:

```python
# prepared is the actual prepare_prompt_selection output for a full preset.
assert prepared['idea_preset_content']['preset_key'] == preset['preset_key']
assert len(prepared['idea_scene_content']) == 3
selected = video_idea_prompt.select_prompt(prepared, 2)
assert selected['selected_prompt_text'] == selected['idea_selected_prompt']
assert preset['hook'] in selected['selected_prompt_text']
assert preset['objective'] in selected['selected_prompt_text']
assert selected['selected_prompt_revision'] == parent_revision
```

Các field template/audio/safety cần asserts thêm ở consumer đúng chức năng; không ép toàn bộ metadata thành một chuỗi provider prompt.

## Task S05: đúng parent/owner/revision, không restore nhầm

**Allowed hunks:** `services/video_idea_handoff.py::parent_session_matches`; `bot.py::_video_uiflow3_idea_handoff_matches`, `_video_uiflow3_capture_idea_handoff`, `video_uiflow3_accept_idea_candidate`, `video_idea_continue_to_exact_parent`.

**Test mới:** `tests/test_p0_product_video_idea_parent_scope.py`.

- [ ] Fixture legacy và UIFLOW3 riêng, hai users/chats, hai product/draft/revisions, source/panel IDs phân biệt.
- [ ] Assert valid return tới đúng owner, duplicate idempotent, cancel/back không mutate, stale revision không ghi active draft.
- [ ] Kiểm guard bên ngoài match function trước thêm guard trùng; patch chỗ gây RED duy nhất.
- [ ] Verify: `pvtest -q tests/test_p0_product_video_idea_parent_scope.py tests/test_p0_video_ideaprompt1_restore_prompt_selection_return_owner.py tests/test_p0_video_idea3_product_lane_scene3_integration.py`. Mong đợi cross-scope rejects/no side effects; valid source preserved.

## Task S06: consumer từng product tới final mock request

**Allowed candidate hunks:** `bot.py::_video_uiflow3_catalog_candidate`, `video_idea_render_exact_parent`; `services/video_uiflow3.py::set_content_candidate`, `_scene_plan_vault_actions`, `suggest_scene_plan_from_vault`; `services/video_uiflow3_routeengine.py::compile_routeengine_handoff`; product-specific compiler được liệt kê trong spec. Shared Tail chỉ loss hunk có impact proof.

**Test mới:** `tests/test_p0_product_video_idea_consumer_payload.py`.

- [ ] Lập exact map 8 canonical product rows của spec S06; source-first lanes phải giữ source/image/panel; missing entry thành coverage gap cụ thể.
- [ ] Capture approved content -> scene manifests -> bridge/worker -> mock wire payload. Assert each field có consumer đúng nghĩa; không cast mọi planning metadata vào prompt text.
- [ ] Với Trend/Script/AI lịch sử ổn, chạy comparator trước; không sửa executor nếu loss không xảy ra ở đó.
- [ ] Verify: `pvtest -q tests/test_p0_product_video_idea_consumer_payload.py tests/test_p0_video_uiflow3_routeengine_bridge.py tests/test_p0_product_video_manual_tail_matrix.py tests/test_p0_product_video_full_menu_tail_to_status_matrix.py`. Mong đợi parent canonical product đúng, payload fidelity, Tail order và zero charge trước delivered mock evidence.

## Task S07: Self-shot Scene Change

**Allowed source:** defect hunk trong `services/video_selfshot2.py`, `video_selfshot_local_analysis.py`, `video_selfshot_continuity_validator.py`; person/object/relationship validators chỉ test trước, sửa threshold/model phải xin spec riêng.

**Tests có sẵn:** `tests/test_p0_product_video_selfshot_native_i2v_r13.py`, `test_p0_selfshot2_continuity_evidence_contract.py`, `test_p0_selfshot2_local_vision_validator_integration.py`, `test_p0_selfshot2_local_vision_cumulative_acceptance.py`, `test_p0_selfshot2_duration_contract.py`.

- [ ] Hash source fixture, subject/segment IDs, expected identity/relationship locks và current native route; bỏ old Fal tests chỉ khi có proof obsolete.
- [ ] Check idea/detail vào từng scene prompt, preserve subject nhưng đổi background, no generic subject replacement.
- [ ] Render/concat local synthetic clips có nhãn offline; ffprobe streams/duration, decode và frame identity; không gọi provider. Validator inconclusive không PASS giả.
- [ ] Verify: `pvtest -q tests/test_p0_product_video_selfshot_native_i2v_r13.py tests/test_p0_selfshot2_continuity_evidence_contract.py tests/test_p0_selfshot2_duration_contract.py tests/test_p0_selfshot2_local_vision_validator_integration.py`. Mong đợi no new failures, traceable preserve evidence; các fixture/model thiếu là blocker, không tải model tự động.

## Task S08: Self-shot Cinematic

**Allowed source:** defect hunk trong `services/video_selfshot3.py::build_timeline`, `compile_prompt`, `preflight`; `services/video_selfshotflow4.py` product-only handoff hunk nếu RED.

- [ ] Test one-take timeline, ordered stages, layer preserve/replace, locked source motion/face/objects, conflicts và missing stages.
- [ ] Capture transformed prompt/manifest, no switch sang Scene Change route, source fingerprint nguyên vẹn.
- [ ] Verify: `pvtest -q tests/test_p0_video_selfshot3_one_take_cinematic_transformation.py tests/test_p0_video_selfshotflow4_complete_contract.py tests/test_p0_video_selfshotflow4_canonical_routes.py tests/test_p0_product_video_selfshot_native_i2v_r13.py`. Mong đợi correct one-take/layer contracts, no new regression S07.

## Task S09: Storyboard

**Allowed source:** defect hunk trong `services/video_storyboard2.py::apply_middle_contract`, `compile_video_prompts`, `build_manifest`, `preflight`; current connector/duration validator hunk nếu proven defect, không đổi model defaults/authority mù.

- [ ] Check distinct panels -> exact scene indices -> approved motion prompt -> current provider/capability request.
- [ ] Offline 2 clips khác nội dung, concat thứ tự đúng, no cloned-hold/tpad; short/corrupt/missing output rejected no-charge.
- [ ] Binding invoice/asset pack/worker/provider thống nhất, selected model không bị default thay. Provider downtime không sửa bằng fallback trái approved route.
- [ ] Verify: `pvtest -q tests/test_p0_product_video_storyboard_key4u_veo_route_r15_7.py tests/test_p0_storyboard_normalization_quality_remediation_r15_2.py tests/test_p0_r4_storyboard_declared_coverage_scene_identity.py tests/test_p0_video_storyboard_entity_creative_middle.py`. Mong đợi no fake padding, scene identity, approved prompt và binding; legacy expectation khác phải classification, không weaken validation.

## Task S10: toàn bộ safe matrix và chống hồi quy

**Manifest:** exact SAFE_RUN tại `docs/product-video/SAFE_TEST_MANIFEST.md` sau S00, gồm new regression files khi được tạo. Không include SubDub/Voice TTS model replay.

- [ ] Cover scope dimensions ở spec S10 và quality catalog supported states; không tạo live assignments cho kho.
- [ ] Chạy baseline/branch cùng test/environment, sensitive forward/reverse; JUnit collected/passed/failed/skipped/xfailed/xpassed/errors tách rõ.
- [ ] Kiểm exact protected paths không đổi; nếu shared bot hunk thì diff function-level ngoài allowlist phải zero.
- [ ] Verify compile sau code sửa: `python scripts/check_bot_source_compile.py`; `python -m py_compile bot.py` và mỗi Python file changed.
- [ ] Verify safe system cluster: `pvtest -q tests/test_p0_product_video_manual_tail_matrix.py tests/test_p0_product_video_full_menu_tail_to_status_matrix.py tests/test_p0_product_video_pv10_deterministic_all_product_e2e.py tests/test_deploy_vps_workflow_hygiene.py tests/test_p0_product_video_worker_deploy_lock.py`.
- [ ] Execute full exact current SAFE_RUN bằng list manifest dưới guard, không deselect valid failure. Mong đợi zero new regressions/unclassified tests; còn failure phải ledger/blocker, không claim clean.

## Task S11: checkpoint, báo cáo và dừng

**Files:** `docs/product-video/PROGRESS.md`, narrow defect reports và PR conversation; không sửa global AGENTS/skills để tự promote lesson.

- [ ] Review mỗi changed file/hunk -> defect -> spec -> test; secret/privacy gate; preserve untracked work.
- [ ] Publish defect ledger, exact base/head/merge/runtime SHAs riêng; trạng thái implement/test/deploy/live không gộp.
- [ ] Cập nhật verified rollback checkpoint sau từng product sửa đạt đủ comparator. PR mới nhất chưa đủ evidence không thay anchor cũ.
- [ ] Merge/deploy/live approval tách riêng, không chạy tự động trong provider-free review-only scope.
- [ ] Verify: `git diff --check` và `git diff --name-status "$ApprovedBase...HEAD"`; `gh pr view --json state,isDraft,headRefOid,files` từ branch có PR hiện hành. Mong đợi đúng allowlist, OPEN/chờ review, không production mutation.
- [ ] Gửi cùng checklist summary trong chat và GitHub. `NEXT_STATE=WAIT_OWNER_DECISION`; không tự mở Long/AI Edit.

## 3. Nghiệm thu plan trước khi chạy

- [x] Source paths/symbols chính đã đọc, không viết plan bằng tên lane suy đoán.
- [x] Phân loại Idea library/active/deferred/locked tách rõ.
- [x] Audit targets không bị gọi là confirmed bugs.
- [x] Mỗi task có files, assertions, verify command và stop gate.
- [x] Live/provider/deploy không được cấp bởi plan.
- [ ] Owner duyệt plan/spec S00-S11.

**STOP tại đây. Không chạy các task trên trước Owner duyệt.**
