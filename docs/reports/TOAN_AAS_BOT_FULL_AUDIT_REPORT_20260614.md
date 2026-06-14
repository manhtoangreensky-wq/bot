# TOAN AAS Bot Full Audit Report

Date: 2026-06-14
Audit mode: report-first, no runtime feature changes.
Repo head at audit start: `ec5146c Fix main menu layout and free tools callback`

## 1. Executive Summary

Overall status: PARTIAL. Core bot startup/tests are stable in local audit, the main menu callback layer is now covered by tests, and the latest code contains a handler-backed path from `/start` to `🎬 Tạo video AI`. However, public paid media/video should remain guarded until a live end-to-end video job passes: menu -> add-ons -> invoice -> confirm -> provider job -> poll/result -> Telegram delivery.

Safe for public users: PARTIAL. Menu, account, support, Free Hub, pricing display, notes/docs guards, and image/video guard messages are safe enough from the static/test audit. Paid media flows still need live smoke before wider traffic.

Public features that should stay OFF or guarded:
- Public AI video provider rendering until `/tool_test_shopaikey_video` and `/shopaikey_video_job <task_id>` pass on live.
- Frame-video render unless Local Worker is connected; Railway direct render should stay off.
- Unverified music/Suno/MiniMax/Auphonic endpoints.
- BYOK/deep provider flows unless explicitly configured and guarded.

Public features safe to keep ON if already enabled:
- Main menu navigation and guarded menus.
- Free Hub guarded/free tools.
- Public image only if current provider image smoke passes and refund guard is active.
- Support/contact and feedback ticket entry.

Biggest risks:
- P1: Live Telegram may still be serving an older Railway deploy if `🎬 Tạo video AI` does not open the video menu despite `ec5146c` registering and testing that route.
- P1: Video final pipeline exists in code, but a real end-to-end provider job/result delivery is not proven by this audit.
- P1/P2: ShopAIKey video status/content endpoints are blank in `.env.example`; if provider requires custom status/result URLs, async jobs may submit but fail to deliver output.
- P2: Many newer flows have guards/menu handlers, but some are intentionally not production-complete.

## 2. Recent Work Summary

Recent commits:
- `ec5146c Fix main menu layout and free tools callback`
- `9bef117 Fix growth checklist bridge and inventory readiness`
- `429ad20 Fix production website image asset paths`
- `1b9c856 Add TOAN AAS Free Tools Hub V1`
- `176b7e5 Complete universal video final pipeline`
- `acca316 Fix website logo and banner asset paths`
- `bfc9039 Add universal video finalization flow`
- `210834a Upgrade video prompt engine V10`
- `e40ff45 Replace website branding with official assets`
- `d2942c0 Fix manual top-up QR assets and bonus policy`

Recent change groups:
- Website/static: official logo/banner assets and production asset path fixes.
- Main menu/free hub: compact menu, Free Tools button handler, unknown callback guard.
- Support/CSKH: support reply/ticket handling, support menu split, auto-reply.
- Video: video prompt engine V10, universal finalization flow, final pipeline, provider status guards.
- Pricing: tiered media pricing, add-on confirmation, Xu/VND conversion.
- Provider: ShopAIKey status, video async job reporting, image fallback work.
- Payment/manual topup: QR asset work and policy text happened before the payment/top-up lock; current audit did not modify payment.
- Document/PDF and storage: notes/docs menus, storage quota policy, guarded document tools.
- Admin/checklist: growth checklist, operator bridge, runtime/status/admin command visibility.

Files changed in the last 10 commits included:
- `bot.py`
- `index.html`
- `.env.example`
- `free_tools_hub.py`
- `video_prompt_quality.py`
- `tests/test_core.py`
- `tests/test_free_tools_hub_v1.py`
- `tests/test_video_final_pipeline_v11.py`
- `tests/test_video_finalization_v12.py`
- `tests/test_growth_checklist_fix_v1.py`
- website/payment/static asset files

## 3. Test Commands Run

Pre-report checks from the latest completed task:
- `python -m py_compile bot.py`: PASS
- `python -m py_compile local_worker.py`: PASS
- `pytest -q`: PASS, `219 passed, 1 warning`
- `git diff --check`: PASS
- `git status --short`: clean before this report file

Final report checks:
- `python -m py_compile bot.py`: PASS using bundled Python runtime.
- `python -m py_compile local_worker.py`: PASS using bundled Python runtime.
- `pytest -q`: PASS, `219 passed, 1 warning in 38.92s`.
- First sandbox pytest attempt hit Windows temp/cache `PermissionError`; rerun outside sandbox passed.
- `git diff --check`: PASS.
- `git status --short`: report file only before commit.

## 4. Main Menu / UX Audit

Regular user layout in current code:
- Free Tools + Account
- Image + Video
- Notes/Documents + Voice/Music
- Topup/Pricing + Guide
- Support + Feedback
- Hub + Language

Admin layout:
- Same user layout plus one admin-only row.

Video entry status:
- `🎬 Tạo video AI` uses callback `menu|main_video`.
- `menu|main_video` is covered by `handle_menu_callback`.
- Static callback audit and tests confirm this button opens the video menu in the current code.

Important live note:
- If live Telegram still cannot open the video menu, the most likely causes are: Railway has not deployed `ec5146c`, the running process/webhook is old, or Telegram callback data is coming from an old inline keyboard still on screen. Retest with a fresh `/start` after deploy.

Broken/missing button status from static audit:
- Main menu: no missing callback handlers detected.
- Free Hub: no missing callback handlers detected.
- Video menu: no missing callback handlers detected.
- Image menu: no missing callback handlers detected.

## 5. Free Hub Audit

Status: guarded and navigable.

Covered menu callbacks:
- `freehub|prompt_meta_ai`
- `freehub|caption_hashtag`
- `freehub|content_ideas`
- `freehub|image_video_prompts`
- `freehub|docs_pdf`
- `freehub|notes_storage`
- `freehub|byok`
- `freehub|upload_postprocess`

Unknown Free Hub callbacks now return a friendly guard message instead of silently failing. Free Hub must remain free/no-Xu unless a later task explicitly adds paid actions with confirmation.

## 6. Image Module Audit

Status: partial production, provider-dependent.

Known stable/guarded pieces:
- Tiered image pricing is centralized.
- Warranty tiers are represented in pricing flows.
- Public image should only deduct after confirmation.
- Provider failure paths include user-friendly maintenance/refund messaging.

Risks:
- Provider model availability can change. `nano-banana` previously failed live as invalid/not found. Fallback configuration exists, but live image smoke must be checked after any ShopAIKey provider change.
- Some advanced image tools are guarded/planned rather than fully live.

Recommendation:
- Keep public image ON only if current `/tool_test_shopaikey_image <ratio>` passes and public fail/refund path remains tested.

## 7. Video Module Audit

Status: menu/callback layer fixed; final live rendering remains the highest-risk area.

Current code path:
- `/start` -> `🎬 Tạo video AI` -> `menu|main_video`
- Main video menu includes:
  - `🔥 Video theo trend`
  - `🎬 Video AI thật`
  - `🧩 Kịch bản -> Ảnh -> Video`
  - `🎞 Ghép ảnh thành video`
  - `🎭 Tự quay & đổi cảnh AI`
  - `🎥 Video mẫu >60 giây`
  - `💡 Ý tưởng video`
  - `🎥 Gợi ý chuyển động`
  - `🌐 Dịch/lồng tiếng video`
  - `🧰 Sửa/cắt video`

Handler status:
- `trendg|`: handler exists.
- `menu|video_ai_true`: handler exists through menu callback.
- `storyboard|`: handler exists.
- `menu|video_frame_intro`: handler exists through menu callback.
- `selfscene|`: handler exists.
- `longvideo|`: handler exists.
- `videoidea|`: handler exists.
- `motion|`: handler exists.
- `videodub|`: handler exists.
- `videoedit|`: handler exists.

Video AI true submenu:
- `promptvideo|start`: handler exists.
- `imagevideo|start`: handler exists.
- `videoref|start`: handler exists.
- `menu|hint_video_status`: handler exists.

Final pipeline:
- Universal video finalization code exists and test files are present.
- Expected pipeline: music/SFX -> subtitle/dub -> invoice -> confirm -> job -> render -> postprocess -> send result.
- Audit did not call paid/provider endpoints, so live final render is NOT proven here.

Primary issue to fix next if live still fails:
- Reproduce fresh `/start` -> `🎬 Tạo video AI`.
- If it does not open menu, this is deploy/runtime mismatch.
- If it opens menu but `Tạo video` inside a subflow does not reach final invoice/confirm, trace the specific callback into `handle_video_finalization_callback` and add a narrow test for that branch.
- If confirm submits but no output arrives, inspect ShopAIKey video job status/result endpoints and provider response shape.

## 8. Voice / Subtitle / Dubbing Audit

Status: guarded/partial.

Covered areas:
- ShopAIKey TTS admin smoke has been integrated historically.
- Video dubbing/subtitle callback routes exist.
- Newer tasks separated subtitle/dub modes to avoid jumping from subtitle into dubbing.

Risks:
- ASR/translate/TTS/mux pipeline should be tested as separate admin smoke pieces before public charging.
- Provider timeout/Telegram send timeout false-fail cases have had hotfixes, but live large files can still expose timing issues.

Recommendation:
- Keep subtitle/dub add-ons in invoice preview, but only charge after final confirmation and only run when provider flags are enabled.

## 9. Music / SFX Audit

Status: mostly guarded.

Current expectation:
- Existing music/SFX menu can collect add-on preferences.
- Real AI music generation providers should remain OFF unless endpoint and model are live-tested.
- Upload/use-existing-audio flows are safer than AI music generation.

Risk:
- Do not hard-code guessed Suno/MiniMax/Musicful endpoints.

## 10. Document / PDF Audit

Status: menu restored/guarded.

Covered areas:
- Notes/Documents menu is separate from PDF/Word tools.
- PDF tools are submenu guarded.
- Merge PDF button can exist if handler exists; if not ready it should return maintenance text and no Xu deduction.

Risk:
- Album/multiple-file upload should not crash; recommend a manual test with several files after deploy.

## 11. Notes / Storage Audit

Status: policy appears aligned with the latest user decision.

Observed configuration:
- Free storage: `50MB`.
- Add-on block: `50MB`.
- Add-on price: `10k VND` per `50MB`.

Policy notes:
- Small text notes count by real text size.
- Attachments count by real file size.
- Temporary files should not count permanently if cleaned.

Risk:
- Need periodic cleanup verification for large media temp files.

## 12. Billing / PayOS / Packages Audit

Status: locked, not modified in this audit.

Observed conversion:
- `XU_TO_VND=100`
- 1 Xu = 100 VND
- 1,000 Xu = 100,000 VND

Payment/top-up lock:
- `/naptien`, PayOS QR, PayOS webhook, paid top-up, wallet balance, history, combo/package purchase, monthly package purchase, trial bonus, payment metadata, idempotency, and refund policy were not changed in this audit.

Recommendation:
- Continue treating payment/top-up as frozen unless a direct payment bug is reported.

## 13. Support / Ticket / CSKH Audit

Status: implemented/guarded.

Recent work includes:
- Support auto-reply before/alongside ticket creation.
- Ticket and lead support system.
- Separate support vs feedback flows.
- `support_auto_test` admin command exists.

Risk:
- Manual live test is still required: open support -> create ticket -> input "tôi cần tư vấn gói video" -> bot should reply immediately and create/store ticket.

## 14. Admin Audit

Status: admin commands are broadly registered and visible.

Important commands present in admin menus/registry include:
- `/runtime`
- `/data_status`
- `/providers`
- `/dashboard`
- `/stats`
- `/sales_ready`
- `/shopaikey_status`
- `/shopaikey_usage`
- `/shopaikey_video_job`
- `/free_hub_status`
- `/free_provider_status`
- `/video_price_test`
- `/support_auto_test`
- `/frame_video_status`

Risk:
- Admin menu is long; keep grouped but do not remove diagnostics.

## 15. Provider / Env Audit

ShopAIKey:
- Base URL is configured as `https://api.shopaikey.com/v1`.
- URL join helper exists to avoid `/v1/v1` style mistakes.
- Chat/TTS/image/video all have separate config areas.
- Usage endpoint is separate: `https://api.shopaikey.com/usage`.

Video-specific env risk:
- `.env.example` has `SHOPAIKEY_VIDEO_STATUS_ENDPOINT=` blank.
- `.env.example` has `SHOPAIKEY_VIDEO_CONTENT_ENDPOINT=` blank.
- If live provider needs non-default status/content endpoints, jobs may submit but fail during poll/result.

Operator bridge:
- `OPERATOR_API_ENABLED=false` by default.
- `PUBLIC_BASE_URL` and `OPERATOR_API_TOKEN` are internal bridge config, not a video or affiliate failure by themselves.

BYOK:
- Must not log raw keys.
- Should stay guarded.

## 16. Local Worker Audit

Status: safe by default, not proven live.

Expected safe defaults:
- Railway should not render heavy ffmpeg jobs directly unless explicitly enabled.
- Frame video should require Local Worker when configured.
- If worker is offline, bot should show maintenance/worker-unavailable and not deduct Xu.

Risk:
- Frame video output requires Local Worker live verification.
- Direct render on Railway is OOM risk and should stay off.

## 17. Website/Profile Static Audit

Status:
- Website logo/banner asset paths were fixed in recent commits.
- Production verification should use `https://www.toanaas.vn/assets/logo.png` and `https://www.toanaas.vn/assets/banner.png`, not only local 200 checks.

Known caution:
- If apex `https://toanaas.vn` DNS or asset routing differs from `www.toanaas.vn`, verify both. Do not claim website fixed from local-only tests.

## 18. Callback Registry Audit

Static callback audit result:

| Menu | Callback count | Missing handlers | Row layout |
| --- | ---: | --- | --- |
| main_regular | 11 | none | 2,2,2,2,2,2 |
| main_admin | 12 | none | 2,2,2,2,2,2,1 |
| free_hub | 9 | none | 2,2,2,2,1 |
| image_menu | 10 | none | 2,2,2,2,2 |
| video_menu | 12 | none | 2,2,2,2,2,2 |
| video_ai_true | 6 | none | 2,2,2 |
| support | 7 | none | 2,2,2,1 |
| feedback | 9 | none | 2,2,2,2,1 |
| account | 10 | none | 2,2,2,2,2 |
| notes_docs | 11 | none | 2,2,2,2,1,2 |
| pdf_word_tools | 8 | none | 2,2,2,2 |
| music_voice | 12 | none | 2,2,2,2,2,2 |
| pricing | 4 | none | 2,2 |

Representative callback table:

| Callback | Label | Module | Handler exists | Status | Note |
| --- | --- | --- | --- | --- | --- |
| `menu|main_video` | Tạo video AI | main/video | yes | PASS | Fresh `/start` should open video menu. |
| `menu|video_ai_true` | Video AI thật | video | yes | PASS | Opens AI video submenu. |
| `promptvideo|start` | Prompt -> Video | video | yes | PASS/GUARDED | Must lead into final pipeline. |
| `imagevideo|start` | Ảnh -> Video | video | yes | PASS/GUARDED | Provider/video public flags still matter. |
| `videoref|start` | Video mẫu -> Video AI | video | yes | PASS/GUARDED | Should remain guarded if provider missing. |
| `trendg|start` | Video theo trend | video | yes | PASS/GUARDED | Content planning first. |
| `storyboard|start` | Kịch bản -> Ảnh -> Video | video | yes | PASS/GUARDED | Media render needs provider/worker. |
| `freehub|prompt_meta_ai` | Prompt Meta AI | Free Hub | yes | PASS | Free/guarded. |
| `support|human` | Human support | support | yes | PASS | Needs live ticket reply smoke. |
| `feedback|start` | Góp ý/Báo lỗi | feedback | yes | PASS | Ticket/feedback separated. |

No missing handler was detected in the audited menu builders. This does not prove every deep flow is complete; it proves the menu callback layer is not orphaned.

## 19. State Machine Audit

Reviewed state groups:
- Image prompt/ratio/tier/confirm.
- Video project/finalization/add-on states.
- Frame-video image collection.
- Support pending input/ticket.
- BYOK key input.
- Document upload.
- Notes/storage.

Findings:
- Current code has many explicit pending states and callback handlers.
- The highest state-risk areas are multi-step video flows and uploaded media flows, because several branches can converge into finalization.
- `/start`, menu buttons, and back buttons should clear or redirect pending state; this is partly covered by tests but still needs live flow-by-flow QA.

Risk:
- P2: Some deep flows may return guard text rather than a full workflow. This is acceptable if public billing is not triggered.
- P1: Any paid flow that reaches confirmation but does not create/send a result must refund/clear lock; this requires live smoke for video.

## 20. Pricing / Xu Conversion Audit

Confirmed:
- `XU_TO_VND=100`.
- 1 Xu = 100 VND.
- 1,000 Xu = 100,000 VND.
- Storage policy: 50MB free + 10k VND per additional 50MB.

Media pricing:
- Image/video pricing is tiered/centralized in current code.
- Video low pricing was previously adjusted to 200 Xu as product entry tier.
- Invoice/final confirmation is required before paid media should deduct Xu.

Do not change:
- Top-up packages.
- PayOS conversion.
- Trial 200 Xu.
- Combo/monthly purchase logic.

## 21. No-charge / Refund Risk Audit

Strong guarantees observed:
- Free Hub actions are no-Xu.
- Menu navigation, support, feedback, pricing, and status commands do not deduct Xu.
- Provider-disabled/maintenance messages generally say no API/no Xu.
- Image/video public failure paths include refund/rollback messaging.

Risk areas:
- Video provider submit may deduct after confirmation; if status/result fails later, refund and job lock clearing must be live-tested.
- Telegram send failure after provider success can create false failure messages; previous hotfixes addressed some TTS/image cases, but video large-file delivery still needs live verification.
- Local Worker offline must not deduct for frame video.

## 22. Open Issues Backlog

| ID | Severity | Module | Issue | Reproduce | Root Cause | Recommendation | Priority |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AUD-P1-001 | P1 | Video menu/live deploy | User reports `Tạo video` still cannot open normal video flow | Fresh `/start` -> `🎬 Tạo video AI` | Likely Railway still running older deploy, old Telegram keyboard, or a deeper final-pipeline callback not covered by main menu test | First verify live commit/runtime. If commit is old, redeploy. If menu opens but subflow fails, trace exact callback. | 1 |
| AUD-P1-002 | P1 | Video final pipeline | Real end-to-end video render not proven by audit | Prompt/Image/Reference -> add-ons -> invoice -> confirm | Provider async status/result may not match expected shape | Run admin smoke and public guarded test with video public OFF/ON as appropriate; add narrow regression tests for failing callback. | 2 |
| AUD-P1-003 | P1 | Provider video | ShopAIKey video status/content endpoints blank in example env | Submit video job then poll | Provider may require custom endpoints/result shape | Confirm live API docs/result; set env; keep public video OFF until job returns result URL/video. | 3 |
| AUD-P2-004 | P2 | Frame video | Local Worker render not proven live | Storyboard/images -> frame video | Worker may be offline; direct Railway render should stay off | Keep guard; verify worker poll/output before opening. | 4 |
| AUD-P2-005 | P2 | Support | Auto reply/ticket needs live test | Support -> create ticket -> input question | Static audit cannot prove Telegram input handling live | Manual test and inspect ticket storage/admin alert. | 5 |
| AUD-P2-006 | P2 | Image provider | Image model availability can change | `/tool_test_shopaikey_image 9:16` | ShopAIKey model/channel availability unstable | Keep fallback env and smoke test after provider changes. | 6 |
| AUD-P2-007 | P2 | Music/SFX | AI music endpoints not fully verified | Music/SFX -> AI generation | Provider endpoints planned/guarded | Keep public disabled/guarded until smoke pass. | 7 |
| AUD-P2-008 | P2 | Docs/upload | Album/multiple file upload not fully proven | Send multiple docs/photos | Telegram media groups can stress state handling | Manual test; never crash, ask user to send one by one. | 8 |
| AUD-P3-009 | P3 | Website | Apex vs www asset verification may differ | Curl `toanaas.vn` and `www.toanaas.vn` assets | DNS/static host routing | Verify production URLs after deploy. | 9 |
| AUD-P3-010 | P3 | UX/layout | Some submenus still have uneven rows or guard-only buttons | Navigate deep submenus | Many features are staged | Polish after P1/P2 video/support issues. | 10 |

## 23. Recommended Next 5 Fixes

1. Verify live deploy/runtime for `ec5146c`; test fresh `/start` -> `🎬 Tạo video AI`. If live commit is old, redeploy before touching code.
2. Reproduce the exact dead video button path inside the current live bot and add one narrow regression test for that exact callback.
3. Run admin video provider smoke: submit job, poll status, confirm result URL/video delivery. Keep public video OFF until this passes.
4. If provider job submits but output does not arrive, fix only the ShopAIKey video status/result mapping through the shared video service.
5. Live-test support input auto reply/ticket and document upload guards after video is stable.

## 24. Do Not Touch List

Stable/locked areas:
- PayOS dynamic QR.
- `/naptien`.
- Payment webhook.
- Paid top-up Xu logic.
- Manual top-up logic if currently passing.
- Wallet/user Xu balance.
- Payment/top-up/transaction history.
- Combo/package purchase logic.
- Monthly package purchase logic.
- Trial bonus 200 Xu.
- Payment metadata and webhook idempotency.
- Refund/charge policy unless fixing a direct confirmed bug.
- Railway persistent DB/backup unless data-status bug appears.
- Provider keys/tokens.
- Destructive DB migrations.

## 25. Final Recommendation

What to fix next:
- Do not start another large feature. Fix the exact live video entry/final-pipeline issue first.
- Treat `🎬 Tạo video AI` as two layers:
  1. Menu open layer: fixed/tested in current code.
  2. Final paid render layer: still needs live end-to-end verification.

What to keep frozen:
- Payment/top-up.
- DB destructive work.
- Public video rendering until provider job/result delivery is confirmed.
- Local ffmpeg/frame video on Railway.

What can be public:
- Main menu navigation.
- Free Hub guarded tools.
- Support/contact/ticket if live input test passes.
- Public image only while current provider smoke/refund path passes.

What should remain admin-only:
- ShopAIKey video smoke.
- Provider usage/status commands.
- Frame video worker diagnostics.
- Unverified music/voice/video provider tests.
