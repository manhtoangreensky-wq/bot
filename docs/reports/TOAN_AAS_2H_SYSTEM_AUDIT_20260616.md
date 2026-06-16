# TOAN AAS 2H System Audit - 2026-06-16

Audit base commit: `fcb8f5d` (`Open video beta gate after VEO output`)

Scope: read-only system audit, gate map, hidden feature check, and remaining fix queue. No public flags were opened during this audit. No provider was called. No Xu was deducted.

## Locked Areas

These areas must stay locked unless a task explicitly targets them:

- PayOS dynamic QR, PayOS webhook, webhook signature/auth, return/cancel URLs.
- `/naptien`, paid top-up Xu logic, manual top-up approval logic that is already passing.
- Wallet balance, user Xu balance, payment/top-up/transaction history.
- Combo/package purchase, monthly package purchase, trial bonus 200 Xu.
- DB destructive actions, DROP TABLE, reset, user/payment/top-up/job/history deletion.
- Provider secrets, API keys, tokens, raw webhook payloads.

## Executive Summary

The codebase is currently very broad but structurally organized around registered command handlers and callback prefixes. Main customer surfaces have real callback handlers: `menu|`, `freehub|`, `imgtool|`, `vfinal|`, `videoaddon|`, `trendg|`, `storyboard|`, `tr_*`, `support|`, `ticket|`, `pricing|`, `storage|`, `memory|`, and admin/provider/freeze callbacks.

The main remaining risk is not missing registration; it is mismatch between live runtime flags, provider smoke state, and user-facing wording. Video AI beta gate was patched in commit `fcb8f5d`; the next critical step is live verification after deploy, not another broad code rewrite.

## High-Signal Findings

### 1. Video Beta Gate: Patched, Needs Live Verification

Status: `GUARDED`

Commit `fcb8f5d` changed video beta opening logic so a confirmed ShopAIKey video output can satisfy the smoke gate, and runtime system settings can enable public beta tiers 300/400 while keeping 200 off unless explicitly allowed. This addresses the previous code-side blocker where video could stay blocked despite a successful output.

Remaining live checks:

- `/video_public_status`
- `/video_gate_status`
- `/shopaikey_status`
- `/tool_test_shopaikey_video`
- `/shopaikey_video_job <task_id>` until output confirmed
- `/video_beta_open tiers=300,400`
- User path: Video -> Video AI chan that -> Prompt -> Add-ons -> tier 300/400 -> invoice -> confirm -> job.

### 2. Video Finalization: Core Pipeline Exists

Status: `GUARDED`

The finalization module has a shared path:

- add-ons menu
- music/voice/subtitle choices
- tier/package choice
- confirm/not-ready guard
- local render guard
- AI video readiness gate
- copy/save fallback

Important: prompt-based Video AI should not require local slideshow images. Code now differentiates local frame readiness from prompt export readiness. Live test should verify no old deployment is still returning the stale "need images" path for prompt-based AI export.

### 3. Main Menu and Major Callback Registration Are Present

Status: `READY_PUBLIC` for menu navigation, `GUARDED` for paid/provider features.

Main menu exposes:

- Free tools
- Account
- AI Image
- AI Video
- Notes / Docs
- Translation
- Voice / Music
- Top-up / Pricing
- Guide
- Support
- Feedback
- Hub
- Admin for admin users

All major callback groups are registered in `bot.py`.

### 4. Image Menu Structure Is Recently Locked

Status: `READY_PUBLIC` for menu/prompt flow; `GUARDED` for provider render.

Commit `7ee3c51` restored the requested image structure:

- Quick image
- Prompt from image
- AI edit
- Edit image

Local edit tools are under the edit submenu, while AI edit is a separate top-level image flow. Do not re-expand the image menu unless a later task explicitly asks.

### 5. Translation Hub Is Present and Split Correctly

Status: `READY_PUBLIC` for text/session setup; `GUARDED` for paid/provider voice/video parts.

Translation is a hub with:

- Language translation
- Video translate/dubbing

The language branch has text, voice/audio, two-way, conversation, document, transcript, and auto-translate controls. The video branch is separate. Back routing still needs live manual QA because the user reported earlier cross-routing between video and translation menus.

### 6. Support / Ticket Has Real Pending State

Status: `READY_PUBLIC`

Support has callback handlers and pending state. The correct product standard is:

- Reply immediately to common user questions.
- Save ticket/lead where needed.
- Alert/admin-escalate only when required.

Ticket storage alone is not enough; future support fixes should preserve "answer first, ticket second".

### 7. Storage Add-on Has Payment Bridge Code

Status: `GUARDED`

Storage add-on tables and PayOS order type handling exist. Since payment/top-up is locked, any future storage payment work must be isolated to storage add-on order creation and must not alter PayOS core/webhook behavior except through existing extension points.

## Gate Matrix

| Feature | Visibility | Callback | State | Back | Provider | Worker | Billing | Output | Language | Final |
|---|---|---|---|---|---|---|---|---|---|---|
| Main menu | Public | `menu|main` | none | main | n/a | n/a | no | menu | i18n vi/en/zh | READY_PUBLIC |
| Cong cu mien phi | Public | `freehub|main` | `free_hub` pending | mostly local | n/a | n/a | no | prompt/content | vi/en partial | READY_PUBLIC |
| Uu dai/promo | Public | commands/callbacks | promo pending DB | pricing/top-up | n/a | n/a | PayOS-linked | promo guide | vi-focused | STABLE_LOCKED |
| Nap Xu / Bang gia | Public | `pricing|`, `payos_pkg|`, `manual|` | payment/manual states | pricing/top-up | PayOS/manual | n/a | yes | payment/order | vi-focused | STABLE_LOCKED |
| Dich thuat | Public | `menu|translate`, `tr_*` | translation session | hub-aware | translate/STT/TTS guarded | n/a | guarded | text/audio/doc | vi/en/zh partial | READY_PUBLIC |
| Dich/Long tieng video | Public menu | `videodub|`, `vfinal|` | video dub/finalization | video/translation branch | ASR/TTS guarded | worker for mux | confirm gate | subtitle/dub plan or output | vi/en partial | GUARDED |
| Tao anh nhanh | Public when image flag ON | `create_media|quick_image` | quick image state | step-aware | ShopAIKey image | n/a | confirm before deduct | image | vi/en/zh partial | READY_PUBLIC |
| Chinh sua AI | Public menu | `imgtool|edit_ai_start` | image edit state | image menu | image edit provider guarded | n/a | confirm/guard | edited image or prompt | vi/en partial | GUARDED |
| Chinh sua anh | Public | `menu|image_edit_start`, `imgtool|editor_*` | image editor state | image submenu | n/a/local | local processing | no or guarded | edited/resized image | vi/en partial | READY_PUBLIC |
| Nang chat luong AI | Public menu guarded | `imgtool|editor_upscale` / AI upscale guard | image state | image submenu | guarded | local fallback | no/guarded | enhanced image or guard | vi/en partial | GUARDED |
| Video theo trend | Public planning | `trendg|`, `tvflow|` | trend/video flow state | video branch | no provider until final | n/a | content free/guarded | plan/prompt | vi primary | READY_PUBLIC for planning |
| Storyboard + Prompt dien anh | Public planning | `storypack|start` | storyboard pack state | video branch | no provider until image/video action | n/a | no until render | concepts/shot pack | vi primary | GUARDED |
| Kich ban -> Anh -> Video | Public guarded | `storyboard|` | storyboard state | storyboard project | image/video providers guarded | frame worker for local | confirm before image/video | storyboard/images/video plan | vi primary | GUARDED |
| Video AI chan that Beta | Admin/public gated | `menu|video_ai_true`, `promptvideo|`, `vfinal|` | video finalization | finalization back callback | ShopAIKey video | n/a | final invoice/confirm | job/video | vi/en/zh partial | GUARDED |
| Video beta 200 | Admin-openable only with loss override | `vfinal|tier|low` | video finalization | finalization | ShopAIKey video | n/a | confirm | job/video | vi/en | KEEP_OFF by default |
| Video beta 300 | Public after safe gate | `vfinal|tier|basic` | video finalization | finalization | ShopAIKey video | n/a | confirm | job/video | vi/en | GUARDED |
| Video beta 400 | Public after safe gate | `vfinal|tier|common` | video finalization | finalization | ShopAIKey video | n/a | confirm | job/video | vi/en | GUARDED |
| Video 600+ | Hidden/blocked | `vfinal|tier|standard` and above | video finalization | finalization | not public | n/a | blocked | guard | vi/en | KEEP_OFF |
| Ghép anh local | Public guarded | `framevideo|`, `vfinal|export_local` | frame video state | video branch | n/a | Local Worker/ffmpeg | confirm/refund | local mp4 | vi/en | GUARDED |
| Image-to-video | Public menu guarded | `imagevideo|start` | image/video state | video AI branch | provider guarded | n/a | confirm | video job or guard | vi/en | GUARDED |
| Video-to-video | Hidden/planned | reference/video branch | reference state | video AI branch | provider not confirmed | n/a | blocked | guard | vi/en | KEEP_OFF |
| Voice/Music | Public | music/media callbacks | music pending | menu branch | library/TTS guarded | n/a | guarded | audio/prompt | vi/en | READY_PUBLIC/GUARDED |
| Ghi chu/Tai lieu | Public | `memory|`, `docflow|`, `menu|main_memory` | memory/doc states | mixed | n/a | local docs | free/quota | note/file/doc | vi/en | READY_PUBLIC |
| Storage addon | Public menu guarded | `storage|`, `menu|memory_storage_addon` | storage addon pending | memory menu | n/a | n/a | PayOS order type | storage grant after payment | vi | GUARDED |
| Ho tro | Public | `support|`, `ticket|` | support ticket pending | support menu | n/a | n/a | no | reply/ticket | vi/en partial | READY_PUBLIC |
| Gop y/Bao loi | Public | `feedback|` | feedback pending | main | n/a | n/a | no | feedback row | vi | READY_PUBLIC |
| Admin | Admin only | `menu|admin`, admin commands | admin-specific states | admin menu | providers via smoke | worker status | no direct unless admin finance | status/actions | vi | READY_ADMIN_ONLY |
| Provider status | Admin only | commands and `menu|admin_provider` | tool test snapshots | admin | no secrets | n/a | no | status | vi | READY_ADMIN_ONLY |
| Local Worker | Admin/public guarded | local commands/frame callbacks | worker/job states | admin/video | n/a | Local Worker | no/guarded | status/job | vi | GUARDED |

## Hidden Active Feature Audit

| Feature | Active? | Menu entrypoint? | Should show? | Status | Fix |
|---|---:|---:|---:|---|---|
| Free Hub prompt library | yes | yes | yes | READY_PUBLIC | Keep as content-only upsell path. |
| Video beta commands | yes | admin command only | admin yes, public no until gate | GUARDED | Verify deploy of `fcb8f5d`; do not open 200 without explicit override. |
| Storage addon PayOS order type | yes | yes | yes | GUARDED | Test isolated storage purchase only; no PayOS core edits. |
| Internal finance archive | yes | admin only | admin yes | READY_ADMIN_ONLY | Keep hidden from users. |
| Long AI story video | yes/planning | video menu | yes as planning/guard | PLANNING_ONLY | Do not present as render-ready. |
| Image-to-video | yes/guarded | video AI menu | yes with guard | GUARDED | Only enable provider path after smoke. |
| Video-to-video/reference | yes/guarded | reference menu | yes as planning/guard | GUARDED | Keep provider execution guarded. |
| Local frame video | yes/guarded | video menu | yes | GUARDED | Requires Local Worker; no direct Railway render by default. |
| Translation video dub | yes/guarded | translation + video menus | yes | GUARDED | Verify back target stays in current branch. |
| Admin provider smoke tools | yes | admin/smoke menu | admin only | READY_ADMIN_ONLY | Keep no-Xu and no-secret logging. |

## Manual QA Checklist After Deploy

1. `/runtime`
2. `/data_status`
3. `/providers`
4. `/shopaikey_status`
5. `/video_public_status`
6. `/video_gate_status`
7. `/start`
8. Main menu -> Admin, verify no generic error.
9. Main menu -> Video -> Video AI chân thật -> Prompt -> add-ons -> tier -> confirm.
10. Main menu -> Video -> Video theo trend -> generate prompt -> finalization -> no image requirement for prompt-based export.
11. Main menu -> Translation -> Language branch -> Back.
12. Main menu -> Translation -> Video dub branch -> Back.
13. Main menu -> Image -> Quick image -> suggestions -> ratio -> tier -> confirm.
14. Main menu -> Support -> create ticket -> type message -> immediate reply + ticket code.

## Audit Conclusion

No further broad refactor should happen before live QA. The next work should be small, targeted fixes based on the remaining queue. The highest risk area is video public execution path after deploy because it depends on runtime flags and provider smoke state, not only code.

