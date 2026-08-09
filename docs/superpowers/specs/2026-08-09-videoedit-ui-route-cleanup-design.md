# Video Edit UI Route Cleanup Design

## Outcome

Ship one UI/UX-only change before any Video Edit engine work. The public Telegram Video menu, Video Edit hub, active manual workspace, general Video guide, and local planning Back route must form one predictable graph with no cross-menu jump.

## Approved scope

- Keep the four Video Edit hub actions: goal-based edit, manual edit, quality enhancement, and editor-specific guide.
- Remove the standalone `videoedit|latest_status` button from both the idle Video Edit hub and the active manual workspace.
- In the two-column manual workspace, replace that detached status slot with an editor guide whose Back target is the exact workspace.
- Keep the old `latest_status` handler read-only for callbacks already present in old Telegram messages; do not expose it in new menus.
- When Local Video Studio planning is enabled, show `🧭 Lập kế hoạch dựng video` beside `📖 Hướng dẫn video` in the main Video menu. Keep it hidden when the feature flag is off.
- Render the main-menu button on its own row when Planning is visible.
- Make the general Video guide Back button return directly to `menu|main_video`; remove the competing Back-to-generic-guide action.
- Keep every editor-specific guide Back target tied to its exact caller (`hub`, `manual`, `ai`, `quality`, `audio`, or `effects`).
- Make root Back from Local Video Studio planning return to the main Video menu, not the Video Edit hub.

## Route graph

```text
Main Video
├─ Video Edit hub
│  ├─ Goal-based edit
│  ├─ Manual edit
│  │  └─ Active workspace (no standalone status button)
│  ├─ Quality enhancement
│  └─ Tool guide -> exact caller
├─ Planning (feature-gated) -> root Back -> Main Video
└─ Video guide -> Back -> Main Video
```

## Status behavior

This UI change removes only the detached status navigation. Real progress belongs inside each submitted edit job and will be implemented in the later route/engine branch from worker/job state. The UI branch must not invent progress, submit work, poll providers, run FFmpeg, create jobs, or charge Xu.

## Implementation boundaries

Allowed production files:

- `bot.py`
- `services/local_video_studio_public.py`
- `services/video_uifreeze1.py` only if the frozen menu declaration must change

Allowed supporting changes:

- Focused route/UI tests under `tests/`
- This spec and its implementation plan

Forbidden in this phase:

- `services/video_local_editing.py`, `local_worker.py`, provider adapters, payment/wallet/Xu, onboarding, PWA, database migrations, deploy configuration, or live media execution

## Failure and compatibility rules

- A disabled Planning feature answers with its existing safe alert and must not create a session.
- Old status callbacks remain safe and read-only, but no new keyboard advertises them.
- A failed Planning Back delivery must leave its session available for retry.
- Callback payloads stay within Telegram's 64-byte limit.
- No Back button may fall through to `menu|main_guide`, another product, or the generic main menu unless it is explicitly the Main menu button.

## Verification

1. Run focused RED tests and confirm failures describe only the old UI contract.
2. Apply the minimal production change.
3. Run focused GREEN tests plus affected menu, route-audit, editor navigation, and planning tests.
4. Run `python -m py_compile bot.py`, `git diff --check`, and inspect the changed-file scope.
5. After an approved deploy/runtime is available, perform Telegram QA on the real public callbacks. Do not label unit results as live results.
