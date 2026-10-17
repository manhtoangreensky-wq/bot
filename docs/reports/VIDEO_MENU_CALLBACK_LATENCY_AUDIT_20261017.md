# Video Menu Callback Latency Audit — 2026-10-17

## Contract

Mục tiêu của batch này là xử lý đúng nguyên nhân spinner/callback chậm ở các
điểm điều hướng của Menu Video. ACK Telegram được đưa lên trước các thao tác
đọc ngôn ngữ, lock, state, cleanup và render có thể chậm; không thay đổi
nghiệp vụ tạo video.

Được phép sửa: `bot.py`, regression test ACK-order, state và báo cáo này.

Đã khóa: route graph/back semantics đã hoàn thiện, Product Video/Video AI
engine, provider/router, worker/job executor, Voice, Music, Image, SubDub,
AutoPost, wallet/Xu/PayOS, ENV/secrets, database/data và deployment behavior.

## Ordered plan / checklist

1. **S1 — ACK seam:** DONE ở mức source/test. Đã ACK sớm cho root menu,
   Video AI entry/back, planner open/back, Product Video public entries,
   prompt library, video editor hub và long-video public entry; các nhánh
   nghiệp vụ/delegated vẫn giữ owner ACK của chúng.
2. **S2 — inventory:** DONE ở mức source. `services/video_uifreeze1.PUBLIC_MENU_ROWS`
   có 12 entry mặc định; khi planner bật có thêm `lvs27b|open`. Mỗi entry đã
   được đối chiếu với handler/ACK seam hoặc được giữ nguyên owner ACK.
3. **S3 — nested/back:** DONE ở mức source, CHƯA coi là live-complete. Chỉ
   thay đổi ACK điều hướng và chặn ACK lặp; không chuyển provider/job/wallet
   work vào fast path.
4. **S4 — protected scope:** DONE. Không sửa services/providers/worker hay
   engine semantics.
5. **S5 — verification/delivery:** OPEN cho tới khi full syntax/test có output
   terminal, rebase/push một PR duy nhất, CI xanh và (nếu được duyệt) exact-SHA
   deploy/health được xác minh.

## Code changes (minimal, UI/callback only)

- Root `menu|main`, `menu|main_video`, `menu|guide_video_ai`: ACK trước admin
  lookup, shared cleanup, language lookup và render; cờ nội bộ ngăn ACK lần hai.
- Video AI `vid3|entry|...` và `vid3|back`: ACK trước draft/state persistence
  và navigation render, sau các ownership/stale-token guard bắt buộc.
- Local Video Studio `lvs27b|open/back`: ACK trước transaction lock/state/render;
  marker theo `callback_query.id` bảo đảm một callback chỉ được trả lời một lần.
- Product Video public entries, prompt library, video editor hub và long-video
  public entry: ACK trước các local read/render bước đầu; delegated paths giữ
  nguyên owner ACK.

## Verification ledger

| Spec | Status | Evidence |
|---|---|---|
| S1 navigation ACK seams | SOURCE_VERIFIED | Focused source-order checks: `FOCUSED_PASS 9`; changed-function compile `13/13`; test module compile pass |
| S2 entry inventory | SOURCE_VERIFIED | 12 default + optional planner entry; handlers/ACK ownership reviewed |
| S3 nested/back | SOURCE_VERIFIED_NOT_LIVE_COMPLETE | No provider/job/wallet calls added to fast paths; live child timing still incomplete |
| S4 protected scope | SOURCE_VERIFIED | Changed files are `bot.py`, focused test, state, report; `DIFF_CHECK_PASS` |
| S5 delivery | OPEN | Full `bot.py` compile and pytest terminal results still pending; no PR/deploy claim |

## Terminal evidence captured

```text
FOCUSED_PASS 9
CHANGED_FUNCTION_COMPILE_PASS 13
TEST_COMPILE_PASS
DIFF_CHECK_PASS
```

The final working tree must still produce a terminal result for full
`py_compile bot.py` and the focused pytest invocation before delivery is
claimed. Static/source evidence is not a claim that every button is live-smooth.

## Delivery truth

`MERGED != DEPLOYED != LIVE`. Current runtime evidence remains the prior
checkpoint: PR #1409 is present on GitHub main/VPS; this callback-latency batch
has not been deployed. No provider call, wallet mutation, restart, merge or
deploy was made by this batch so far.

## Canonical status

```text
TASK=video-menu-callback-latency-20261017
BASE_SHA=origin/main (to be rebased before delivery)
HEAD_SHA=working tree
FILES_CHANGED=bot.py; tests/test_video_callback_ack_order.py; .agents/state/video-menu-callback-latency-20261017.yaml; docs/reports/VIDEO_MENU_CALLBACK_LATENCY_AUDIT_20261017.md
TESTS=focused 9/9; changed functions 13/13; test py_compile pass; diff check pass; full bot.py/pytest pending terminal output
BASELINE_FAILURES=none newly established
BRANCH_FAILURES=full compile/pytest not yet captured
NEW_FAILURES=none observed in focused checks
PROTECTED_COMPARATORS=source scope review; no provider/worker/wallet/engine files changed
PROVIDER_CALLS=false
WALLET_MUTATIONS=false
DEPLOY=not yet authorized/executed for this working tree
RUNTIME_SHA=prior checkpoint only; batch not live
LIVE_PASS=not claimed
BLOCKERS=full compile/pytest terminal evidence; one-PR CI/delivery; per-button live timing
```
