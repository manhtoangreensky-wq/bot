# TOAN AAS Remaining Fix Queue - 2026-06-16

Audit base commit: `fcb8f5d`

Rule: fix oldest/highest-impact items first. Do not touch locked payment/top-up areas unless the task explicitly targets them.

## P0 - Critical Before Larger Launch

### P0.1 Verify deploy of video beta gate patch

Status: patched in code at `fcb8f5d`, live verification pending.

Why: previous live behavior showed Video AI remained blocked after successful provider output. Code now accepts output-confirmed smoke and runtime flags, but Railway/live bot must be checked.

Manual test:

1. `/runtime`
2. `/shopaikey_status`
3. `/video_public_status`
4. `/video_gate_status`
5. `/tool_test_shopaikey_video`
6. `/shopaikey_video_job <task_id>` until output sent/confirmed
7. `/video_beta_open tiers=300,400`
8. User flow: Video -> Video AI chân thật -> Prompt -> Add-ons -> tier 300/400 -> invoice -> confirm.

Do not open 200 unless explicitly testing marketing-loss mode with `allow_loss_200=true`.

### P0.2 Final video export path manual QA

Status: needs live QA.

Expected:

Prompt -> add-ons -> choose tier -> invoice -> confirm -> job -> provider/status -> output.

Rules:

- If provider not ready, show maintenance/upgrade guard.
- If a real action button says "confirm/export video", it must either run the ready path or be hidden behind a guard.
- Prompt-based AI video must not require local frame images.
- Local slideshow video may require 2+ images and worker readiness.

### P0.3 Back routing in video finalization

Status: code has `back_callback` support, manual QA needed.

Expected:

- Back from finalization returns to the exact previous branch where the user entered.
- Back from add-ons returns to finalization/package step, not a generic orphan menu.
- No "choose step to go back" placeholder for normal user paths.

### P0.4 Admin menu live error

Status: needs live QA after latest deploy.

User reported Admin button showed generic processing error. Static code shows `menu|admin` handler exists; likely live deploy/state issue or a subpage exception. Check logs if it still occurs.

Manual test:

1. `/start`
2. Tap Admin
3. Tap Provider, Freeze/Queue, Smoke Test, Finance
4. Confirm no generic error and no secret output.

## P1 - Important UX/Flow Stabilization

### P1.1 Storyboard + Prompt dien anh full manual chain

Expected chain:

Video -> Storyboard + Prompt điện ảnh -> Quảng cáo sản phẩm -> input "nước hoa nam cao cấp" -> Dùng mặc định -> 3 concepts -> select concept -> shot pack per scene -> image/video/Meta prompts -> back correctly.

Do not touch render video while fixing this flow.

### P1.2 Translation back routing and language continuity

Status: hub split exists, live QA pending.

Checks:

- Translation hub -> Language translation -> Text -> Back returns to Language translation.
- Translation hub -> Video translate/dub -> Back returns to Translation hub, not generic Video unless intentionally selected.
- English UI should not jump into Vietnamese except unsupported strings.

### P1.3 Free Tools first four flows

Status: freehub has suggestion/result states, but user reported thin flows.

Expected:

- 3 suggestions
- more suggestions
- custom input
- output/prompt
- copy/save/use next step
- no provider/no Xu

### P1.4 Support answer-first behavior

Expected:

- User asks "làm sao để nạp tiền" -> bot replies with top-up guidance immediately.
- Ticket/lead is saved if needed.
- Admin alert only when escalation threshold is met.

## P2 - Product Completeness / Guard Clarity

### P2.1 Image AI edit provider readiness wording

Status: guarded.

Keep menu structure locked. Improve only tool readiness text if a button still feels like it will render but actually cannot.

### P2.2 Local frame video worker readiness

Status: guarded.

Do not direct-render on Railway by default. Test only when Local Worker connected. Keep status clear in `/providers` and frame video status.

### P2.3 Storage add-on payment live path

Status: guarded.

Needs isolated test:

- add storage menu
- choose 10k/20k/50k/100k storage plan
- PayOS bridge creates order type `storage_addon`
- webhook applies storage add-on only

Do not alter top-up packages or PayOS webhook core.

### P2.4 Website/asset production verification

Status: likely patched earlier, live URL check required.

Check:

- `https://toanaas.vn/assets/logo.png`
- `https://toanaas.vn/assets/banner.png`
- `https://toanaas.vn`

## P3 - Documentation / Monitoring / Nice-to-Have

### P3.1 COMMAND_REGISTRY freshness

`docs/COMMAND_REGISTRY.md` is large and mostly current, but should be regenerated or patched after each new admin command set. Avoid treating it as the source of truth; source of truth is `bot.py` registration.

### P3.2 i18n coverage list

Create follow-up report for strings still Vietnamese-only in English/Chinese UI. Do not mass-rewrite during hotfixes.

### P3.3 Provider smoke dashboard

Admin status commands exist. A smaller dashboard could show:

- ShopAIKey chat/image/video/TTS
- Deepgram ASR
- translation
- Local Worker
- last error
- public gate

This is not urgent if `/providers`, `/shopaikey_status`, `/video_gate_status`, and `/video_public_status` are working.

## Explicitly Not In This Queue

- No PayOS core rewrite.
- No `/naptien` changes.
- No webhook signature changes.
- No top-up ratio changes.
- No DB destructive migration.
- No public long render.
- No 600+/premium video opening.
- No hidden direct Railway ffmpeg render.

