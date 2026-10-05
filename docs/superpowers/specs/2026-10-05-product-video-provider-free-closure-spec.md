# Product Video: spec hẹp provider-free và kho ý tưởng

STATUS=PROPOSED_WAIT_OWNER_APPROVAL
TASK_ID=PRODUCT_VIDEO_RESUME_PLAN_20261005
BASE_SHA=7bd5b2a86254e16631a9edb74bd40422635b227b

## 1. Mục tiêu và giới hạn

Mục tiêu là giữ đúng nội dung khách chọn và hoàn thiện các product chưa đóng, bằng kiểm chứng hệ thống trước khi có live mới. Kho ý tưởng chỉ cung cấp nội dung; executor, quality, quote và job thuộc **sản phẩm đích**.

Quyền hiện tại: Owner đã duyệt thực thi provider-free S00-S11 với source/test remediation hẹp khi có RED. Approval này không cấp paid/provider calls, production mutation, deploy, merge hoặc live; PR #1360 vẫn là docs/state control plane.

Không hứa mọi input đều tạo được video đúng tuyệt đối. Input không hợp lệ, provider lỗi, thiếu asset bắt buộc hoặc output giả phải báo đúng lý do/no-charge; không báo `delivered` khi chưa có artifact giao thật. Trong provider-free test chỉ chứng minh contract và artifact local, không chứng minh provider sẽ làm đúng prompt.

## 2. Files và boundaries

Root tuyệt đối dùng trong mọi lệnh:

`C:/Users/toann/Documents/Codex/2026-06-25/start-new-codex-thread-p0-17b5-4/work/subdub-smart-receipt-paced-audio`.

Paths dưới đây là repo-relative, nối vào root trên. Không sửa cả `bot.py`; chỉ được xét các function hunks đã nêu và được gắn defect ID sau khi RED.

| Boundary | Source đã xác định | Điều phải giữ |
|---|---|---|
| Kho -> selected snapshot | `services/video_idea_store.py`, `video_idea_catalog.py`, `video_idea_prompt.py` | Nội dung, preset identity/version, safety và customer edits |
| Selected -> legacy parent | `services/video_idea_handoff.py`, `bot.py::video_idea_continue_to_exact_parent`, `video_idea_render_exact_parent` | Product/session/revision/route/assets |
| Selected -> UIFLOW3 | `bot.py::_video_uiflow3_catalog_candidate`, `_video_uiflow3_idea_handoff_matches`, `video_uiflow3_accept_idea_candidate`; `services/video_uiflow3.py::set_content_candidate` | Original intent, approved brief, content lock, owner/draft |
| Plan -> render request | `services/video_uiflow3_routeengine.py::compile_routeengine_handoff`, product compilers, `services/video_tail9.py::apply_content_contract` | Scene-indexed prompt và confirmed immutable snapshot |
| Product output | `services/video_selfshot2.py`, `video_selfshot3.py`, `video_storyboard2.py`, `video_real_render_connector.py`, `multiscene_video_pipeline.py` | Existing capability/output validation, không engine mới |

Protected: mọi SubDub/Multi/Smart code/test/model; Local Edit; Long/AI Edit execution; Voice TTS runtime; PayOS/wallet/payment; ENV/secrets; production DB/schema; deploy/systemd/workflow. Shared modules chỉ thay hunk trực tiếp defect Product Video; đổi signature/return shape dùng ở nhiều file phải có impact listing và Owner duyệt trước.

## 3. Phân loại kho, aliases và product

- `video_idea` là public library entry. Giữ nút browse kho, categories, presets, edit và back; không xoá data hoặc receipt lịch sử.
- Không có invoice/submit/render riêng dưới product `video_idea` chỉ vì khách xem/chọn kho. Chọn nội dung phải có product đích hợp lệ, hoặc quay về chọn product trước commercial Tail.
- `video_idea_to_product` và các alias nội bộ hiện tồn tại phải được audit theo callsite; không xoá hàng loạt. Alias chuyển nội dung tới product thật không phải sản phẩm độc lập.
- `video_ai_real` có entry AI Prompt/Image; không nhân đôi thành sản phẩm thứ ba. `video_reference` compatibility không được mặc nhiên đồng nhất với `video_ai_video_reference` có source-guided contract riêng.
- Product đích không nằm trong scope hiện hành (Long/AI Edit/Local Edit locked) không được mở execution qua kho.
- Nếu product có idea entry: entry phải hoạt động đúng. Nếu chưa có entry, ghi coverage gap cụ thể, đề xuất hunk riêng để Owner duyệt; không giấu gap và không tự thêm UI/route trái source contract.
- `frame_video_local` giữ baseline; không ép nhận Scene3 idea lane khi source/test hiện loại trừ.

## 4. Contract nội dung phải truy vết

Fixture đưa sentinel riêng vào từng trường để biết mất nội dung tại boundary nào. Giữ original snapshot riêng với compiled prompt; compiler có thể chuẩn hoá/provider-format nhưng không âm thầm xoá yêu cầu đã chấp nhận.

| Nhóm | Trường hiện có cần đối chiếu |
|---|---|
| Định danh | `preset_key`, `idea_id`, `idea_preset_id`, `idea_preset_version`, selected prompt ID/revision |
| Kịch bản | `title`, `description`, `hook`, `objective`, `scene_arc`, `idea_scene_content`, scene_index |
| Prompt | `system_guidance`, `user_prompt_template`, `image_prompt_seed`, `video_prompt_seed`, `idea_selected_prompt`, `selected_prompt_text`, negative constraints |
| Hình | `style`, `visual_plan`, selected/recommended profile, ratio, subject/locations/references |
| Tiếng | `audio_plan`, `voice_plan`, `music_plan`; chỉ planning, không tự bật paid add-on |
| Khuyến nghị | recommended scene count/duration/aspect ratio/product/profile, platform fit, variation axes |
| An toàn | `content_safety_note`, identity/relationship locks; không thực thi instruction trong preset thành quyền hệ thống |
| Owner context | parent product/flow/owner user/chat/draft/session/revision; source video/panel asset identity |

Precedence: **product source/identity/capability/safety locks -> customer-approved edits/selection -> full preset snapshot -> optional recommendations**. Product/source locks là giới hạn không được override; nội dung conflict phải trả về màn hình review với thông tin cụ thể, không tự thay mặt khách chọn ý khác.

Khuyến nghị scene count/ratio/profile không được ghi đè lựa chọn khách đã chốt. Template placeholder chỉ dùng schema đã có; biến không resolve phải hiện lỗi planning cho khách sửa, không gửi raw placeholder hoặc bí mật vào provider. Số liệu/brand/dialogue khách nhập phải còn trong original snapshot và field có nghĩa ở compiled request.

## 5. Audit targets đã thấy từ source, chưa phải bug đã tái hiện

| ID | Quan sát source | Cần chứng minh |
|---|---|---|
| A01 | `video_uifreeze1` và Tail/bridge vẫn có commercial/compatibility keys `video_idea` | Key có còn submit độc lập từ public path không, hay chỉ compatibility |
| A02 | `_PRESET_CONTENT_FIELDS` trong prompt là subset của store; `content_safety_note` không có trong tuple đã đọc | Safety/detail còn ở snapshot/consumer khác không; có mất ở final payload không |
| A03 | Candidate builder có phần direction/continuity chung; một số field được lưu nhưng chưa thấy dùng tại prompt builder | `system_guidance`, template, visual/audio plans có tới compiler/planner đúng nghĩa không |
| A04 | Legacy selected prompt giới hạn 20.000 ký tự; UIFLOW3 content intent có giới hạn 12.000 | Boundary input dài có silent loss không; original snapshot có giữ không |
| A05 | UIFLOW3 handoff lưu session revision nhưng match function đã đọc chủ yếu xét product/draft/user/chat | Callback cũ sau đổi revision có được chấp nhận nhầm không; guard ngoài có chặn không |
| A06 | Một số test legacy dùng continuation cũ khác registry hiện tại | Stale test expectation hay product defect; không sửa production chỉ để chiều test cũ |
| A07 | Connector Storyboard hiện chứa Key4U và ShopAIKey model sets mới hơn issue body lịch sử | Invoice/worker/provider request cùng authority không; không quay lại Fal/old pin bằng tên test |
| A08 | Kho có compatibility parent keys nhưng không thể suy ra đủ hỗ trợ tất cả canonical products | Map public entry -> parent -> final canonical executor bằng test hành vi |

Mỗi Axx chỉ chuyển thành DEFECT khi có expected/actual + failing test/fixture tại exact SHA. Không tăng giới hạn, thêm route hoặc đổi provider trước khi đo đúng boundary lỗi.

## 6. Specs S00-S11

### S00: Authority và kiểm thử cách ly

Input: exact main/head, latest #1155 receipts, local dirty list, test file inventory. Output: manifest phân loại mỗi file vào SAFE_RUN / LIVE_OR_NETWORK / OUT_OF_SCOPE / OBSOLETE_WITH_PROOF; fixture hashes; command environment.

Test harness không đọc production `.env`/DB, không import worker main loop. Bắt outbound DNS/connect trước collection, mock HTTP/provider/Telegram, chỉ asset local; mọi attempt ngoài explicit loopback là test failure. Trước chạy suite phải chứng minh một external DNS/connect bị guard chặn. Subprocess chỉ được FFmpeg/ffprobe trên local paths đã review, không URL/network helper. Không sửa production ENV.

File test plugin đề xuất sau duyệt: `tests/pv_provider_free_guard.py`; plugin phải audit collection-time import, report blocked attempts, zero real calls và temp-DB isolation. Giữ nguyên `tests/conftest.py`, không cài dependency/model mới. Guard không đủ chứng minh offline thì dừng, không chạy test unsafe.

Acceptance: full classification, unknown=0; guard canary PASS; no production paths/credential use; no conflict task. Số test được đo khi chạy, không cố ép thành số lịch sử.

### S01: Reference master audit đã có final receipt

Final master receipt `5983313383` đã PASS tại Bot/Worker SHA `7bd5b2a8...`: 106 SAFE_RUN files / 2007 tests PASS, 17 matrices PASS, defects=0. S00 chỉ rebind current main và audit drift; nếu exact authority không material đổi thì không làm lại 2.007 tests và không chạy chồng Reference.

Contract không đổi: `shopaikey_video / veo3.1-fast / image_to_video / video_reference_guided_i2v`, không Fal/Key4U commercial fallback, không ambiguous resubmit. Artifact download/security/worker SHA/recovery/no-charge được kiểm chứng offline tại cần thiết, không submit thật.

Acceptance: ledger ghi `REFERENCE_PROVIDER_FREE_MASTER_CLOSURE=PASS`, `LIVE=DEFERRED_BY_OWNER`; chỉ mở source remediation Reference nếu S00 chứng minh material drift hoặc test RED mới thuộc Reference.

### S02: Đóng standalone product Idea, giữ kho

Audit `video_uifreeze1`, public route matrix, Tail adapter, bridge và Strategy V2. Chỉ chỉnh authoritative inventory/checklist để Idea không còn standalone product requirement; public routing chỉ sửa nếu test chứng minh direct paid path còn reachable. Không xoá key compatibility/data/historical jobs, không đổi giá các sản phẩm.

Test: root browse/select/back/stale callbacks tạo `0` jobs/outbox/provider/charge; handoff xác định product thật trước Quality/Invoice/Confirm. Deferred targets vẫn deferred. Acceptance đóng **standalone scope**, không đánh dấu integration PASS từ quyết định phân loại.

### S03: Snapshot detail kho

Fixture đầy đủ mọi trường ở mục 4; custom edits, missing optional values, preset inactive/version changed, Unicode/quotes/newlines, text dài chạm giới hạn từng normalizer. Đo `source -> prepare -> select -> restore -> content lock`.

Nếu field mất: whitelist/copy hunk tại boundary gây mất, không đổi schema. Giữ original raw accepted payload; không dùng generic title thay detail. Version thay đổi sau confirm không mutate snapshot đang render. Limit vượt phải báo rõ trước confirm hoặc giữ đầy đủ original; không silent truncation nội dung khách đã duyệt.

Acceptance: snapshot equality/deep-copy độc lập cho accepted fields; no missing required sentinel; no shared mutable object; production catalog mutations=0.

### S04: Đúng prompt và scene semantics

Test chọn 5 options, refresh, edit, skip hợp lệ, Storyboard mandatory prompt; các scene counts hiện công khai `1,2,3,5,10,20`; ratios `9:16,16:9,1:1,4:5`. Không gọi LLM thật.

Compile theo selected/custom prompt và explicit scene arc; giữ hook đầu, mục tiêu cuối, ordering và distinct scene action. Template/system guidance là nội dung planning, không đổi permissions. Generic variation chỉ bổ trợ camera/style, không thay đổi ý chính. Replan không ghi đè scene `locked_by_user`.

Acceptance: selected prompt identity/revision đúng; accepted content tokens/constraints ở đúng field; đủ N scene/indices; không mất dialogue/brand/negative constraint; custom edit thắng generated default.

### S05: Parent handoff legacy và UIFLOW3

Test return/back/cancel/reopen/duplicate/stale/cross-user/cross-chat/cross-product/cross-draft, revision thay đổi và preset session mismatch; assets giữ file identity. Legacy và UIFLOW3 mỗi đường có case riêng. Session sai phải block/reset ở đúng parent, không restore nhầm phiên mới hoặc quay sang standalone executor.

Acceptance: đúng parent product+owner+session+revision, zero side effects trước confirm, asset/source IDs bất biến, stale callback không ghi lên active draft. Nếu sửa guard, chỉ hunk match/capture/accept gây lỗi; không redesign back-stack.

### S06: Tích hợp từng product consumer

Map và test riêng: Trend; AI Prompt; AI Image; Reference; Script; Storyboard; Self-shot Scene Change; Self-shot Cinematic. Mỗi row có public callback, legacy/UIFLOW3 parent key, final canonical product, applicable asset/source locks, selected prompt/detail và last mock provider payload. Alias không tính thêm product.

Acceptance theo row: preview -> approved snapshot -> per-scene manifest -> worker request đồng nhất nội dung có nghĩa; không bị title-only/generic substitution. Tail giữ `Add-on -> Review -> Quality -> Invoice -> Confirm -> Status`; source-first lane không bị chuyển thành text-only. Product không có entry phải là explicit coverage gap với remediation proposal, không bỏ qua.

### S07: Self-shot Scene Change / PV2-R05A

Source `services/video_selfshot2.py`, existing local analysis/continuity modules; fixture thật hiện có `PV-L05-self-shot-typing-source.mp4` phải hash-check khi lấy, không tạo fixture giả thay cho acceptance source. Synthetic fixture chỉ cho unit/contract được gắn nhãn rõ.

Prove source fingerprint/segment, selected subject, person/object/relationships preserve locks, background change và scene prompts, two-scene composition, full Tail. Inconclusive analysis không tự coi như pass; unsupported capability báo planning block/no-charge. Tách source lock failure khỏi provider transport failure.

Acceptance: input/source identity không đổi; expected locks nằm trong payload; offline output probe/decoding và continuity evidence đủ; historical 5-second live PASS không thay two-scene V2 evidence.

### S08: Self-shot Cinematic / PV2-R05B

Source `services/video_selfshot3.py`, `video_selfshotflow4.py`. Giữ one-take: identity/motion gốc, layer rules, transformation stages và timeline; không áp engine đổi-background của S07 sang lane này. Test stages empty/out of order/overlap/source mismatch và locked wardrobe/person/objects.

Acceptance: contiguous ordered timeline, correct preserve/replace/effect layers, no arbitrary scene cuts, prompt chứa approved transformation; full Tail and artifact offline. Stage không hỗ trợ phải giải thích/block trước submit, không tạo kết quả placeholder.

### S09: Storyboard / PV2-R06

Source `services/video_storyboard2.py`, planner, current connector và concat validator. Test panel count/order/duplicate/missing/corrupt, mapping scene-to-image, first/end image requirements, scene-specific motion prompt, required capability/provider/model/quote binding.

Fixture offline có hai clip phân biệt, đúng current native duration contract; concat theo thứ tự, final ffprobe/decode/representative frames và audio stream. Không `tpad`/cloned trailing hold để bù output ngắn; scene ngắn/invalid phải reject đúng, không fake PASS. Không hồi phục Fal hay áp pin Key4U-only từ issue body cũ trái current approved authority.

Acceptance: 2 scene identity distinct, sum duration theo tolerance source hiện có, no fake padding, panel và prompt payload đúng, zero real provider calls.

### S10: Safe matrix và protected regressions

Dimensions: product/entry, root-vs-embedded, selection/custom/refresh/skip/back, scene count/ratio, assets, quality, confirm duplicate/stale, output success/failure/recovery. Chia semantic fixture để đo coverage, không Cartesian vô ích. Quality buttons hiện có `200,300,400,500,600,700,800,1000,1200,1500`: chọn được và đúng supported capability/quote, không phải giấy phép live từng tier.

Run baseline và branch cùng environment/manifest; forward/reverse sensitive clusters; account pass/fail/skip/xfailed/xpassed/collection errors riêng. Không xoá/skip valid failure để xanh; obsolete expectation có proof và Owner review. So sánh original locked paths/function hashes; any new protected behavior failure stops source change.

Acceptance: unresolved measured defects=0 hoặc blocker thật được báo; no new regressions; no unknown classification; evidence node/JUnit/hash/diff rõ. Không claim provider perceptual correctness từ mock payload hay ffprobe.

### S11: PR evidence, checkpoint và gate kế tiếp

Mỗi defect một sửa hẹp; shared contract tests trước lane-specific edits. PR đang làm cập nhật done/pending/blocked, exact SHA, RED/GREEN, original comparator và rollback scope. Không PR runtime ôm Long/SubDub/Voice TTS.

Checkpoint chỉ thăng khi review+tests được xác minh cho product đó. PR chưa merge là candidate, merge chưa deploy là source checkpoint, deploy chưa live là runtime checkpoint. Không dùng PR plan này làm runtime rollback anchor.

Acceptance: Owner đọc được cùng nội dung ở GitHub và chat; checklist đúng bằng chứng. Dừng ở review. Merge/deploy/live require instruction mới, không dùng allowance lịch sử.

## 7. Definition of done và stop

**Planning/control-plane DONE**: docs/spec/checklist nhất quán, Owner đã duyệt provider-free execution; PR #1360 vẫn chỉ docs/state.

**Provider-free phase DONE**: S00 + S02-S11 đủ traceability/matrices, zero unresolved measured defects, actual local artifact evidence; S01 Reference giữ closed trừ material drift. Không đánh dấu live Goal hoàn tất.

**Product live DONE tương lai**: Owner mở live riêng, exact runtime binding, job/provider/artifact/delivery/no-charge evidence và content/continuity inspection thật. Hiện live bị hoãn.

Stop ngay khi scope drift cần sửa lane locked, production data/ENV/wallet, test muốn outbound, evidence không đúng SHA, source task overlap hoặc protected comparator mới fail. Báo defect hẹp, không sửa lan sang phần đang ổn.
