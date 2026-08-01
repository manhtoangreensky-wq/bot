# Video Edit Latest Status Design

## Approval and scope

The owner requested that the useful video status/progress presentation also be
available inside **Chỉnh sửa / Nâng cấp video**. The owner previously granted
this task full authority over Video Edit and directed it to continue until the
editor is genuinely useful. The selected design keeps status inside the
`videoedit|` namespace and does not change the top-level Video menu, Product
Video, SubDub, Frame Video, Local Video Studio planning, provider routing,
workers, accounting, deployment, or production configuration.

This is a read-only navigation addition. Opening or refreshing status must not
create a job, call a provider or worker, upload or deliver media, generate paid
content, or mutate Xu/wallet state.

## Alternatives considered

1. **Latest-status entry plus the existing per-job progress panel (selected).**
   Add one secondary action to the Video Edit hub. It opens the requesting
   user's latest canonical Video Edit job and reuses the existing truthful
   six-step renderer. This makes status recoverable after the original Telegram
   message is lost without adding another status implementation.
2. **Per-job panel only.** The current job receipt already includes six steps,
   but users cannot reliably reopen it from the hub. This does not fully satisfy
   the usability request.
3. **Full job-history browser.** This could be useful later but adds pagination,
   retention, privacy, and stale-message behavior that the current request does
   not need. It is rejected as unnecessary scope.

## Public UX

The Video Edit hub retains its four established primary actions, labels, order,
and callbacks:

1. `✨ Chỉnh sửa theo mục tiêu` → `videoedit|ai`
2. `✂️ Chỉnh sửa thủ công` → `videoedit|manual`
3. `🧹 Nâng chất lượng video` → `videoedit|restore`
4. `❓ Hướng dẫn công cụ này` → `videoedit|guide`

A new single-button secondary row appears after those actions:

- `📊 Trạng thái chỉnh sửa` → `videoedit|latest_status`

The existing optional `🧭 Lập kế hoạch dựng video` row remains conditional and
independent. The hub Back and Main-menu row remains last. No status button is
added to the top-level Video menu, and the new button appears exactly once.

When the user has a Video Edit job, the entry opens the existing
`video_editor_job_status_text()` view for the newest owned
`video_local_edit` worker job. The view keeps:

- public processing code;
- truthful public status;
- confirmed price/Xu truth;
- six Video Edit-specific progress steps;
- bounded part progress for split delivery where available;
- delivery, no-charge, or delivery-uncertain receipt truth;
- `🔄 Cập nhật trạng thái` for the exact job;
- Back to `videoedit|hub`.

When no owned job exists, the bot shows a Vietnamese empty state explaining
that no Video Edit task has been submitted yet. It provides Back to Video Edit
and Main menu only. It does not redirect into upload, create editor state, or
open another product.

## Data and truth contract

The latest-job lookup is a dedicated read-only helper with all of these
constraints:

- exact `user_id` equality with the requesting Telegram user;
- exact `job_type == video_editengine1.WORKER_JOB_TYPE`;
- newest row by descending numeric worker-job ID;
- a limit of one row;
- the same public row shape used by `get_local_worker_job()`;
- database connection closed on success and failure.

An admin/owner pressing the hub entry still sees only their own latest job.
Admin status access to an explicitly supplied job ID remains unchanged, but the
new hub entry never becomes a cross-user job browser.

The progress panel remains Video Edit-specific. It may reuse presentation
patterns such as `✅`, `⏳`, `⬜`, and `⚠️`, but it must not read Product Video
session/provider progress or call Product Video status helpers. The six stages
remain:

1. Nhận video
2. Kiểm tra cấu hình
3. Chuẩn bị file
4. Chỉnh sửa video
5. Kiểm tra MP4
6. Gửi kết quả

A completed/delivered display still requires canonical Video Edit receipt
evidence: terminal canonical status, created receipt, Telegram delivery IDs,
positive output size, output hash, and successful ffprobe evidence. Missing or
contradictory evidence must not render a false success. The UI does not invent
a percentage when the worker supplies only stage-level progress.

## Callback, state, and Back behavior

`handle_video_editor_callback()` remains the sole owner of `videoedit|`.
`videoedit|latest_status` is a stateless read route:

- it does not clear or create Product Video state;
- it does not alter the canonical Video Edit pending session;
- it cannot skip upload, review, confirmation, or execution;
- it cannot accept a job ID supplied by the user;
- duplicate clicks only repeat the same read and render;
- Back returns directly to `videoedit|hub`;
- refresh continues to target the exact rendered job ID, so a newer job cannot
  silently replace the job while the user is inspecting it.

Malformed or stale explicit `videoedit|status|<id>` callbacks retain their
current fail-closed ownership check. No callback in this design routes to
`vproduct|`, `subdub|`, `framevideo|`, `lvs27a|`, `lvs27b|`, or a shared
commercial tail.

The existing `videoedit|status|<id>` refresh and legacy
`videoedit|ai_status|<id>` refresh are also explicitly read-only/stateless.
They must remain usable after the hub has cleared the pending editor session.
Both continue to require an exact owned job (or the existing explicit admin
authorization for an exact ID); neither may create or restore editor state.

## Error handling and privacy

- A missing table or database read failure is logged with sanitized context and
  returns a generic Vietnamese unavailable message; raw SQL, paths, Telegram
  IDs, secrets, or exception text are not exposed.
- A missing job is a normal empty state, not an error.
- A job belonging to another user is indistinguishable from no owned job.
- Invalid job fields fall back to the existing bounded public status renderer.
- Status rendering never reads Telegram message bodies or stored source media.
- The route performs no retry, requeue, delivery, billing, or cleanup action.

## Tests and verification

Tests are added before production code and must first fail for the missing
behavior. Focused coverage includes:

- hub retains all four primary actions and adds exactly one secondary status
  row in the correct position;
- optional Local Video Studio planning row remains independent and the final
  Back row remains last;
- no top-level Video-menu status entry is added;
- latest lookup returns only the newest owned Video Edit job;
- Product Video, SubDub, Frame Video, AI-edit legacy jobs, and another user's
  jobs are excluded;
- admin/owner hub entry does not expose another user's job;
- no-job and database-failure views are Vietnamese, bounded, and correctly
  back-routed;
- active, failed-no-charge, delivery-uncertain, delivered, and split-part
  progress render truthfully;
- refresh targets the exact job and performs no mutation;
- callback-owner collision and cross-product-route counts remain zero;
- provider/worker calls, created jobs, paid generations, wallet mutations, and
  Telegram media deliveries remain zero for status navigation tests.

The new focused tests are followed by all accepted Video Edit route/state,
engine/worker/job-safety, real-media, legacy compatibility, Product Video,
SubDub, Local Video Studio, callback-owner, and cross-product regression gates,
plus changed-file compile, `bot.py` tokenize/narrow AST, scope checks,
`git diff --check`, and secret/private-path scans.

## Expected files

The implementation is limited to:

- `bot.py`: the Video Edit hub row, read-only latest-job helper, callback route,
  and empty/error copy;
- focused Video Edit tests;
- this design and its implementation plan.

No database schema, service contract, worker, provider, wallet, deployment,
Railway/VPS, webhook, Product Video, SubDub, Frame Video, or Local Video Studio
source file is changed for this feature.

## Completion criteria

The status addition is complete only when the user can open the newest owned
Video Edit job from the Video Edit hub, see truthful six-step progress, refresh
that exact job, return to the exact hub, and receive a useful empty state when
no job exists. All isolation and zero-side-effect assertions must pass, and all
existing Video Edit actions must remain usable and unchanged.
