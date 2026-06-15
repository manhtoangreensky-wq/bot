# TOAN AAS UX / Language / Flow / Tool Audit

## 1. Executive Summary

Overall status: guarded public bot with many planning flows ready and paid/provider flows behind confirmation or safety guards.

Public safe: yes for audited changes in this pass. No provider render, PayOS, Xu deduction, DB destructive migration, or webhook logic was changed.

Critical risks: video finalization still has a P1 UX issue reported live: some buttons in the final video screen back-route too far and the local export option is hidden when the customer expects a guarded/exportable route. This is queued as the next focused hotfix.

Biggest fixed issues in this pass:
- Storyboard + Prompt điện ảnh no longer stops at placeholder text.
- Storyboard now has template selection, topic input, quick setup, 3 concepts, detailed scene pack, image prompts, video prompts, Meta AI prompts, save guard, and video AI guard.
- Main menu Vietnamese labels now use "Giọng nói / Nhạc" and "Trung tâm" instead of mixed "Voice / Nhạc" and "Hub".
- Free Hub cleanup from the previous task removed video-reference-only routes and moved prompt flow to 3 prompt choices plus guards.

Still blocked:
- Public real Video AI render/export needs the finalization/back-routing hotfix.
- Some provider-dependent tools remain guarded until provider and worker readiness are verified.

## 2. Vietnamese Language Audit

Labels fixed:
- `🎙 Voice / Nhạc` -> `🎙 Giọng nói / Nhạc`
- `🌐 Hub` -> `🌐 Trung tâm`
- Storyboard flow text changed from placeholder to Vietnamese guided planning copy.

English terms kept:
AI, bot, video, TikTok, Facebook, YouTube, Telegram, API, provider, prompt, Meta AI, PayOS, Xu, QR, PDF, SFX.

Terms to change later:
- Some admin/status screens still use technical English. This is acceptable for admin but should be reviewed before wider public exposure.

Public text issues:
- Video finalization guard text is understandable, but the export/back route must be fixed so the user sees an actionable route instead of feeling blocked.

## 3. Main Menu Audit

VI public menu checked:
- Công cụ miễn phí, Tài khoản, Tạo ảnh AI, Tạo video AI, Ghi chú / Tài liệu, Dịch thuật, Giọng nói / Nhạc, Nạp Xu / Bảng giá, Hướng dẫn, Hỗ trợ, Góp ý / Báo lỗi, Trung tâm.

EN public menu checked:
- Free tools, My Account, AI Image, AI Video, Notes / Docs, Translation, Voice / Music, Top up / Pricing, Guide, Support, Feedback / Bug, Hub.

Admin button remains admin-only.

## 4. Callback Audit

Focused callbacks checked in this pass:

| Label | Callback | Module | Handler | Result | Issue |
| ----- | -------- | ------ | ------- | ------ | ----- |
| Storyboard + Prompt điện ảnh | `storypack|start` | Video | `handle_storyboard_pack_callback` | PASS | Rebuilt guided flow |
| Quảng cáo sản phẩm | `storypack|template|product_ad` | Storyboard | same | PASS | Sets topic state |
| Dùng mặc định | `storypack|generate_concepts` | Storyboard | same | PASS | Shows 3 concepts |
| Dùng bản 1/2/3 | `storypack|concept|n` | Storyboard | same | PASS | Shows detail pack |
| Prompt ảnh từng cảnh | `storypack|image_prompts` | Storyboard | same | PASS | Guarded prompt-only |
| Prompt video từng cảnh | `storypack|video_prompts` | Storyboard | same | PASS | Guarded prompt-only |
| Prompt Meta AI | `storypack|meta_ai_prompt` | Storyboard | same | PASS | No Meta API call |
| Tạo video AI từ prompt | `storypack|create_video_ai` | Storyboard | same | GUARD | No provider call, no Xu |

Full public callback matrix remains large and should be refreshed after the next video finalization hotfix.

## 5. Back Routing Audit

Fixed/verified in this pass:
- Storyboard entry -> Video menu via `menu|main_video`.
- Storyboard template topic -> template entry.
- Quick setup -> topic.
- Concepts -> topic/brief.
- Storyboard detail -> concepts.
- Prompt image/video/Meta -> storyboard detail.
- Video AI guard -> storyboard detail.

Known remaining issue:
- Video finalization screen back routing reported live jumps too far. Queued as P1 focused fix.

## 6. Free Tools Audit

Status from previous committed cleanup:
- Free Hub no longer exposes "Prompt theo video mẫu" or "Hồ sơ kênh".
- Prompt library is under "Kho prompt mẫu".
- Prompt output provides 3 options, regenerate, edit, save, copy, and guarded AI video route.
- No Xu deduction and no provider call.

## 7. Translation Audit

Translation hub was restored before this audit:
- Language translation and video translate/dub are separated.
- Video translate/dub back route preserves origin.
- Further i18n consistency is documented in the i18n report.

## 8. Image Audit

No image provider/render logic changed in this pass.

Current expected state:
- Prompt/image planning should not charge Xu.
- Real image generation remains guarded by tier, confirmation, provider checks, refund/warranty logic.

## 9. Video Audit

Changed:
- Storyboard + Prompt điện ảnh now works as planning flow.

Not changed:
- Real Video AI provider render.
- Local worker/ffmpeg render core.
- Video final pipeline billing/deduction.

P1 remaining:
- Restore/repair video finalization export and exact back routing without deleting working routes.

## 10. Storyboard / Prompt Audit

Fixed:
- Entry now opens template selection.
- User topic is captured by state.
- Quick defaults allow fast flow without many questions.
- Bot generates 3 storyboard directions.
- User can regenerate concepts.
- Selecting a concept creates a detailed scene pack with required fields.
- Separate views exist for image prompts, video prompts, and Meta AI prompts.
- Create Video AI is guarded with no provider call and no Xu deduction.

## 11. Voice / Music Audit

Only public menu label/back-label language was touched:
- Vietnamese label now says "Giọng nói / Nhạc".

Provider/TTS/music logic was not changed.

## 12. Document / Storage Audit

Not changed in this pass.

Known policy from previous tasks:
- Notes/documents storage uses quota policy.
- Temporary files should not count as long-term quota after cleanup.

## 13. Billing / PayOS Audit

Not changed.

Lock honored:
- `/naptien`, PayOS dynamic QR, webhook, paid top-up logic, wallet balance, package/combo/monthly plan, trial bonus were not touched.

## 14. Support / Feedback Audit

Not changed in this pass.

Backlog:
- Continue verifying "user asks -> bot answers immediately -> ticket stored if needed" after video finalization hotfix.

## 15. Admin Audit

Not changed in this pass.

Admin-only button remains hidden from normal user menu according to tests.

## 16. Tool Readiness Matrix

| Group | Tool | Public status | Admin status | Real usable? | Fee? | Issue | Recommendation |
| ---- | ---- | ------------- | ------------ | ------------ | ---- | ----- | -------------- |
| Free tools | Prompt Meta/Caption/Ideas/Prompt pack | READY_PUBLIC | READY_PUBLIC | Planning only | Free | No provider render | Keep |
| Video | Storyboard + Prompt điện ảnh | PLANNING_ONLY | READY_PUBLIC | Text/plan ready | Free | No render by design | Keep |
| Video | Real Video AI | GUARDED | Admin smoke | Not public-ready | Paid later | Finalization/back route P1 | Fix next |
| Video | Local frame video | NEED_LOCAL_WORKER | Admin/worker dependent | Depends worker | Paid/free by flow | OOM guard exists | Keep worker required |
| Image | Public image | READY_PUBLIC where ENV on | Admin smoke | Provider-dependent | Paid | Provider fallback configured earlier | Monitor |
| Translation | Text/voice/video hub | GUARDED/PLANNING | Mixed | Depends provider | Mixed | Needs full i18n review | Continue audit |
| Voice/Music | TTS/music/SFX | GUARDED | Admin smoke | Provider-dependent | Mixed | No endpoint guessing | Keep guarded |
| Documents | PDF/local tools | READY/GUARDED | READY | Local tools only | Mostly free | Large files need quota | Keep |
| Storage | Notes/documents quota | READY/GUARDED | READY | Yes | Storage addon | Payment bridge separate | Do not mix with Xu |
| Billing | PayOS/top-up | READY_PUBLIC | READY | Yes | Payment | Locked | Do not touch |
| Support | Support/ticket | NEED_SMOKE | Admin | Basic | Free | Auto reply should be verified | Audit later |

## 17. Fixed in This Task

- Storyboard prompt workflow rebuilt.
- Storyboard state and text input added.
- 3 concept generation and regeneration added.
- Scene pack includes camera, motion, lighting, prompt image, prompt video, negative prompt, caption/voice/music/SFX.
- Prompt image/video/Meta views added.
- Create video AI guard added.
- Main menu Vietnamese labels cleaned.
- Tests added for storyboard workflow and i18n labels.

## 18. Remaining Issues Backlog

| ID | Severity | Module | Issue | Status | Recommendation |
| -- | -------- | ------ | ----- | ------ | -------------- |
| UX-P1-001 | P1 | Video finalization | Export/back routing wrong; user cannot complete normal video export | Open | Focused hotfix next |
| UX-P1-002 | P1 | Video finalization | Do not delete export buttons; guard or route correctly | Open | Restore actionable path |
| UX-P2-001 | P2 | i18n | Some modules still have hard-coded public Vietnamese/English | Open | Continue converting high-traffic screens |
| UX-P2-002 | P2 | Support | Verify auto reply + ticket creation live | Open | Smoke after video fix |
| UX-P2-003 | P2 | Translation | Verify English mode across all submenus | Open | Continue i18n audit |

## 19. Recommended Next 5 Fixes

1. Fix video finalization export and exact back routing.
2. Add focused tests for video finalization back matrix.
3. Smoke support auto reply/ticket flow.
4. Expand i18n tests for Translation/Image/Video submenus.
5. Refresh public callback matrix report after video hotfix.

## 20. Do Not Touch List

PayOS, `/naptien`, payment webhook, paid top-up Xu, trial 200 Xu, combo/package wallet, DB destructive operations, users/payments/topups/jobs/history deletion, provider render core, Local Worker core.

