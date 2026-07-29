# Local Video Studio 27B — Public Planning UI Design

## Approval and scope

This design implements the owner-approved P1_LOCALVIDEOSTUDIO27B_PUBLIC_UI_INTEGRATION_CODEX_TASK.md from accepted main 2622328872800abc08ec44372d49e05e8433618a.

The feature adds one additive, flag-gated secondary action under the existing 🛠️ Chỉnh sửa video screen:
- label: 🧭 Lập kế hoạch dựng video;
- callback namespace: lvs27b;
- flag: LOCAL_VIDEO_STUDIO_PUBLIC_ENABLED, default and invalid values OFF.

When the flag is OFF, existing keyboard rows, labels, order and callbacks are behaviorally unchanged. The lvs27a owner preview and its state remain untouched.

This flow is planning text only. It does not accept media, render, invoke a provider or worker, create invoice/status, deliver media, write a new database field, or mutate Xu/wallet state.

## Alternatives considered

1. Thin public adapter over the 27A pure service (selected): reuse the validated 26I index, record IDs, coverage and pagination while keeping a new lvs27b state machine and public view model. This minimizes duplication and keeps 27A stable.
2. Refactor 27A into a shared core first: rejected for this additive task because it enlarges the diff and risks changing the approved admin preview.
3. Copy 26C–26I catalog data: rejected because canonical IDs/JSON would drift.

## Architecture and data flow

services/local_video_studio_public.py is a pure adapter. It imports the 27A service's read-only index validator/loader, canonical record partitions, coverage and pagination. It defines only public navigation, safe readiness mapping, text and session semantics; it has no Telegram, provider, filesystem-write, subprocess, database, billing or renderer dependency.

bot.py has one feature-flag constant, one conditional row in the existing video-edit keyboard, one narrow lvs27b callback registration and one adapter handler. It never calls an editor/runtime route.

## Vietnamese public flow

Chỉnh sửa video → Lập kế hoạch dựng video → Mục tiêu → Capability catalog → Capability detail → Quyền và an toàn → Planning summary → Gửi bản tóm tắt dạng text vào chat hoặc Back.

Root Back from the goal screen returns to the exact existing videoedit|hub parent. Inner Back pops exactly one invoking parent: summary → safety → detail → catalog → goal. No callback jumps to Product Video, SubDub, Frame Video or another product.

Every root and summary view contains: Đây là công cụ lập kế hoạch dựng video. and Công cụ chưa tạo hoặc render video. Public text contains no private path, provider name, task ID, SHA, secret, render command or job ID.

## State and callback contract

Each public session has a short session_id and is stored under a key derived from user_id + chat_id + session_id. The store is separate from local_video_studio27a_preview. Sessions carry creation/update timestamps and expire after a bounded TTL. Missing, malformed, deleted or expired sessions fail closed without resurrection.

Entry uses lvs27b|open; subsequent callbacks carry the session ID and an allow-listed verb. Record/index tokens keep every UTF-8 callback within Telegram's 64-byte limit. Duplicate callback query IDs are recorded only after a successful edit/reply and then answer idempotently without a second transition.

The pure service applies callbacks to a deep copy. Telegram transaction order is: compute candidate → edit current message or approved reply/bot fallback → commit/delete session → answer callback. If edit and fallback both fail, no forward state is committed. Text-save sends only the planning summary as a normal chat message.

## Safety and readiness

The adapter first calls the 27A validator, preserving planning_only=true, runtime_registered=false, provider_executable=false and public_ui=false, 14 records, 251 unique IDs, 248 local IDs, 3 paid-disabled IDs, 19 QA IDs and zero counters. It never changes the index.

Internal readiness maps to the public-safe enum CONTRACT_ONLY, LOCAL_PLANNING_READY, REQUIRES_RUNTIME, REQUIRES_PLANNED_SHOOT or NOT_SUPPORTED. Paid records are not public catalog choices. Rights/safety derives from canonical rights and selected record metadata without exposing private locations.

## Verification design

Focused tests cover flag OFF/ON invariants, namespace/access isolation, all 11 groups and pagination clamps, exact Back hierarchy, per-session/TTL/stale/malformed/duplicate behavior, fake-transport transaction ordering, locks/readiness/index validation, no-render/provider/wallet/media paths and source boundaries. 27A, 26C–26I, callback-owner, Product Video UI-freeze, Video Edit UI and PR #589 SubDub receipt-truth tests remain regression gates.

## Immutable counters

Provider calls, paid generations, Motion/Higgsfield calls, wallet/Xu mutations, Telegram media deliveries, production deploys and Railway/VPS changes remain zero. No production token or Telegram production smoke is used.
