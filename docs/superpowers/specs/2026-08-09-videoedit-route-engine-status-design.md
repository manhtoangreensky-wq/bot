# Video Edit Canonical Route/Engine Status Design

## Goal

Make Video Edit's cut, image-logo, and text-watermark actions reach the same
validated local FFmpeg worker path, with progress shown inside the submitted
job's own Telegram panel instead of a detached status menu.

## Owner decision and scope

The UI/UX route cleanup is already merged separately in `main` (merge
`a0565e1`). This engine branch starts from that merge and owns only the
`videoedit|` route-to-worker connection and job-bound progress presentation.
The top-level Video product, SubDub, Frame Video, planning, providers, PayOS,
wallet/Xu, onboarding/PWA, deployment configuration, and database migrations
are out of scope.

## Route contract

`handle_video_editor_callback()` remains the sole public callback owner.
Every route keeps an explicit immediate parent:

```text
workspace -> cut -> trim/split input -> review -> confirmation
workspace -> branding -> logo input/options -> review -> confirmation
workspace -> branding -> watermark input/options -> review -> confirmation
```

The text handler may mutate only the owned pending editor state. A stale,
malformed, or cross-product callback fails closed without changing state. Logo
and watermark remain separate plan fields and assets; neither is routed through
the brightness/color lane.

## Execution and artifact contract

The explicit confirmation edge creates exactly one idempotent zero-priced
`video_local_edit` job through `services/video_editengine1.py`. The existing
`local_worker.py` and `services/video_local_editing.py` executors remain the
only media engine. The worker must validate each output and the final MP4
(bytes, MP4/H.264 container evidence, dimensions, duration, full decode, hash,
and Telegram delivery receipt) before displaying completion. Failures remain
no-charge and use the existing safe public copy.

## Job-bound progress panel

Immediately after a job is created, the submitted message is rendered with
the existing Video Edit-specific six-stage renderer and an exact
`videoedit|status|<job_id>` refresh callback. The panel is bound to that job
ID and message ID; it never resolves “latest” while being refreshed. A
read-only refresh may select/format persisted state but cannot create, requeue,
resubmit, deliver, charge, or mutate the job.

Worker stage updates are reflected in that same panel when a safe status-panel
refresh mechanism is available. Missing or contradictory terminal receipt
evidence renders delivery-uncertain, not complete. No generic Product Video
progress type is reused because its semantics differ.

## Verification

Tests are test-first and provider-free:

1. Public callback/text route tests for cut, logo, and watermark, including
   exact Back targets and no brightness fall-through.
2. Submit tests proving one canonical job, job-bound initial panel, and
   idempotent exact-job refresh with no side effects.
3. Worker/receipt tests proving real plan fields reach the existing executor
   and invalid artifacts never become success.
4. Existing local FFmpeg/ffprobe media suites for trim, logo, watermark, split,
   and final delivery remain the artifact evidence.

No Telegram live result is claimed until an approved deployment and manual
QA are performed separately.
