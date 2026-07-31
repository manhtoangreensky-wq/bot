# Video Edit Canonical Local Runtime Design

## Approval, decision, and scope

The owner assigned this task exclusive ownership of the Telegram product
`video_edit` / callback namespace `videoedit|`. The parallel Menu Video task has
released Video Edit route/engine ownership and will not modify its route,
callback, worker, state, or backstack.

The approved direction is a canonical local-first editor:

- every public button inside **Chỉnh sửa / Nâng cấp video** must perform a real,
  useful local operation or lead to a truthful capability explanation;
- no visible button may produce a dead end, fake success, generic red error, or
  route into another video product;
- provider/generative/paid execution remains closed until a separate owner gate;
- existing FFmpeg, validation, worker, idempotency, receipt, and delivery code is
  reused; no parallel editor engine is created;
- the task may change Video Edit internals, but must not change Product Video,
  SubDub, Frame Video, the top-level Video menu, shared product callbacks,
  Railway/VPS configuration, or another product's UI/UX.

CapCut is used only as lightweight workflow inspiration: group familiar tools
by Cut, Join, Frame, Transform, Audio, Color, Overlay, and Effects; show a short
review before execution; keep one button to one action. This Telegram product
does not copy an app timeline, keyframes, template/asset stores, cloud AI, or
desktop/mobile interaction patterns that cannot work truthfully in chat.

The implementation base is `origin/main` at
`74f27da2d1d6227080931b881b59d2c6d121b495`.

## Alternatives considered

1. **Canonical local editor with a Video Edit-specific confirmation path
   (selected).** Keep the existing public callbacks and engine, consolidate all
   editing operations into one workspace, and submit free local jobs directly
   to `video_editengine1`. This avoids shared-tail pricing contradictions and
   keeps other products isolated.
2. **Keep Video Edit on the shared `video_tail9` commercial tail.** This reuses
   more current UI but preserves the contradictory `0 Xu` versus mandatory
   positive quality-tier price and couples editor navigation to Product Video
   concerns. Rejected.
3. **Create one product/state/engine per editing tool.** This makes individual
   screens simple but duplicates upload, validation, job, receipt, and Back
   logic. Rejected because it would create callback and runtime drift.

## Existing foundation to preserve

The implementation must build on these current owners:

- `services/video_edit_state_machine.py`: canonical intake for `manual_edit`,
  `ai_edit`, and `quality_enhance`;
- `services/video_edit_capabilities.py`: truthful capability catalog;
- `services/video_local_editing.py`: FFmpeg command building and validated local
  manual/split execution;
- `services/video_editengine1.py`: persistent job/outbox/idempotency/receipt and
  post-delivery accounting contract;
- `local_worker.py::run_video_local_edit`: Telegram source acquisition, local
  execution, output validation, and media receipt;
- `bot.py::handle_video_editor_callback`: sole `videoedit|` callback owner;
- `services/local_video_studio_public.py`: independent `lvs27b` planning state,
  retained unchanged and outside this editor implementation.

The selected design does not introduce another Python runtime registry, another
worker job type, or another persistent product database.

## Public entry contract

The top-level Video menu remains byte-for-byte unchanged. Its existing
`videoedit|hub` entry opens the Video Edit hub. The hub retains the established
order and callbacks:

1. `✨ Chỉnh sửa & nâng cấp bằng AI` → `videoedit|ai`
2. `✂️ Chỉnh sửa thủ công` → `videoedit|manual`
3. `🧹 Nâng chất lượng video` → `videoedit|restore`
4. `❓ Hướng dẫn công cụ này` → `videoedit|guide`
5. existing optional secondary planning action
   `🧭 Lập kế hoạch dựng video` → `lvs27b|open`, retained as an independent
   preview/planning product and not connected to the editor by this task
6. Back → `menu|main_video`; Main menu → `menu|main`

No new top-level button is added. `/video_enhance` becomes a compatibility entry
to this same hub and no longer opens the obsolete five-button editor.

## Canonical user flows

### Manual editing

`Hub → Manual → Upload → Inspect once → Editor workspace → Operation screen →
Review → Confirm local edit → Job status → Valid MP4 delivery`

The workspace exposes only real local groups:

- **Cắt & chia đoạn:** trim edges, remove a middle interval, fixed-duration
  split, exact-count split, and custom ranges;
- **Ghép & sắp xếp:** add up to nine additional clips and persist an explicit
  order;
- **Khung hình & kích thước:** crop or fit to 9:16, 16:9, 1:1, or 4:5 and keep,
  720p, or 1080p resolution;
- **Tốc độ & hướng:** supported speed values, rotation, and horizontal/vertical
  flip;
- **Âm thanh:** mute, master volume, and local loudness normalization when the
  FFmpeg filter is available; separately mixed dialogue/music/ambience/SFX is
  never claimed when source stems do not exist;
- **Ánh sáng & màu:** brightness and controlled color presets;
- **Chữ, logo & phụ đề:** timed text, bounded logo placement/opacity, and
  validated SRT burn-in;
- **Hiệu ứng local:** fade in/out, subtle vignette, and slow zoom when their
  required FFmpeg filters pass runtime preflight; crossfade appears only when at
  least two clips are present;
- **Thông tin video:** measured duration, dimensions, FPS, audio, format, and
  size;
- **Xem lại:** exact selected operations, output duration estimate, audio
  policy, and `0 Xu` truth before a single final confirmation.

### Local editing assistant

The existing `videoedit|ai` label remains for callback compatibility, but public
execution is local-first. The flow uploads and inspects a source, accepts a
Vietnamese editing intent, and produces deterministic suggestions restricted to
the local capability catalog. Selecting a suggestion pre-populates the same
manual edit plan and returns to the canonical workspace/review path.

If an intent requires generative transformation, subject tracking, background
generation, parallax synthesis, particles, or another provider-only feature,
the flow explains that it is not locally executable and offers relevant local
alternatives. It does not expose an invoice or a confirm button for the blocked
request and does not call a provider.

### Local quality enhancement

`videoedit|restore` uploads and inspects a source, then offers only filters whose
runtime preflight succeeds:

- controlled unsharp enhancement;
- light denoise with FFmpeg `hqdn3d` when available;
- brightness/contrast/color correction;
- honest geometric scaling labelled as resolution normalization, never “AI
  upscale”;
- optional master loudness normalization when source audio exists.

Deep deblur, stabilization, frame interpolation, face restoration, and AI
upscale remain hidden from actionable rows. A separate information row may list
them as unavailable without promising execution.

The selected quality operations become a normal local edit plan and use the
same confirmation/job/delivery path as Manual editing.

### Guide

The guide is fully Vietnamese and describes the actual supported operations,
source limits, confirmation, output validation, `0 Xu` policy, audio-stem truth,
and unavailable provider-only capabilities. Every guide Back returns to the
exact caller.

### Independent planning preview

The existing `lvs27b` planning product remains separate. This task does not add
an editor handoff button, copy planning capability IDs into Video Edit state, or
change its summary/actions. The owner will review optional flows separately and
authorize a future integration only if a preview is useful.

## Capability truth contract

An actionable public capability must satisfy all of the following:

- `enabled=true`;
- `execution_owner` is a local Video Edit owner;
- required FFmpeg/ffprobe/filter preflight passes where applicable;
- a plan field and worker execution branch exist;
- focused tests validate the plan and real output;
- failure returns a truthful no-job/no-charge response.

Provider-only capabilities are not actionable. Existing effect catalog entries
owned by `video_ai_edit_provider_guarded` are removed from public action rows or
shown only in an unavailable-information view. They are not silently relabelled
as local capabilities.

## Vietnamese-first copy

Saved UI language is authoritative for Video Edit. A narrow parent-return fix may
use `get_user_language(user_id)` when the existing `lvs27b` root returns to the
Video Edit hub; no other `lvs27b` behavior changes.

Vietnamese labels are defined for every public capability, operation, readiness
value, validation error, and status. Internal IDs such as `standard_cut` and
`LOCAL_PLANNING_READY` never appear in public text. English and other languages
may retain fallback behavior but are not expanded in this task.

## State model and isolation

The canonical state remains under `video_editor:<user_id>` with a bounded TTL.
It adds only editor-owned fields:

- `screen_id`: current canonical screen;
- `parent_callback`: exact immediate parent;
- `entry_parent_callback`: the exact Video Edit lane or compatibility entry;
- `suggested_operation_keys`: sanitized local-assistant suggestions;
- `local_effects`: selected local effect configuration;
- `audio_normalization`: selected local audio policy;
- `handled_callback_ids`: bounded idempotency list;
- existing source, metadata, manual plan, split/concat, revision, job, and
  receipt fields.

State transitions are pure and allow-listed. A callback cannot skip upload,
inspection, review, or final confirmation. Invalid, stale, duplicate, and
cross-user callbacks fail closed without resurrecting deleted state.

No Video Edit state is stored in Product Video, SubDub, Frame Video, `lvs27a`,
or `lvs27b` stores. No `lvs27b` data is copied into Video Edit state.

## Exact Back hierarchy

Back is rendered from explicit `parent_callback`, never inferred from a mutable
`step`. Required parent mappings include:

- hub → Video menu;
- lane upload → hub;
- workspace → exact Video Edit lane entry;
- cut submenu → workspace;
- trim input → cut submenu;
- split submenu → cut submenu;
- split input → split submenu;
- join submenu → workspace;
- concat intake/reorder → join submenu;
- audio submenu/custom input → workspace/audio submenu;
- effects submenu/detail → workspace/effects submenu;
- transform submenu/value choice → workspace/transform submenu;
- overlay submenu/text/logo/SRT input → workspace/overlay submenu;
- source information → exact invoking screen;
- review → workspace;
- confirmation → review;
- status → hub after submission.

Root Back exits only the `videoedit|` namespace. It never enters Product Video,
SubDub, Frame Video, or a shared guide unexpectedly.

## Legacy callback compatibility

Old Telegram messages remain safe. Compatibility maps are explicit:

- `videoedit|cut` → manual intake with Cut as the requested group;
- `resize`, `crop`, `ratio`, `vertical` → manual intake with Frame/ratio as the
  requested group;
- `compress`, `resolution` → manual intake with Resolution as the requested
  group;
- `color`, `preset`, `brightness` → manual intake with Light/color as the
  requested group;
- `text`, `logo`, `srt`, `subtitle` → manual intake with Overlay as the requested
  group;
- `volume`, `audio` → manual intake with Audio as the requested group;
- `sharpen` → quality-enhancement intake.

When no source exists, compatibility callbacks request upload and persist the
requested group. When a valid source exists, they open the exact group. They do
not build duplicate callback rows and do not display the obsolete editor.

Old generic `video_tail|` messages marked as Video Edit never re-enter the
commercial invoice path. They return to the canonical local Review/Status
screen before any balance, invoice, provider, or paid-submit check. A stale
Video Edit route marker with no source shows the upload recovery screen without
resurrecting deleted editor state or falling into Product Video.

That compatibility branch is restricted to an exact `owner == "video_edit"`
or persisted Video Edit route marker. It does not change routing, state, price,
or submission behavior for any other shared-tail owner.

## Local confirmation, job, and accounting

Video Edit uses a dedicated local confirmation view and does not enter the
shared commercial tail. The confirmation shows the source, operations, expected
duration/output count, audio policy, and `0 Xu`.

Final confirm performs exactly one atomic call to `video_editengine1.create_job`
with:

- `product_type=video_edit`;
- `job_type=video_local_edit`;
- `engine_route=local_worker_ffmpeg`;
- `price_xu=0` and `provider_call=false`;
- a stable idempotency key derived from user, edit session, plan, and local-free
  package identity.

`video_editengine1` accepts zero-priced jobs only for its own validated local
product path. It must not relax another product's invoice rules. The worker still
requires a validated source, bounded workspace, FFmpeg/ffprobe, valid MP4 output,
and Telegram delivery receipt. A zero-priced delivered job records `charged_xu=0`
without invoking wallet mutation. Failure records `failed_no_charge`.

Admission requires the filter snapshot to name the same non-empty worker ID and
the same normalized FFmpeg path as the executor heartbeat. Final receipts must
include a positive duration, dimensions, MP4 container identity, H.264 video,
hash/size, Telegram IDs, and exact free-charge truth. Missing or contradictory
evidence fails closed before success is persisted.

The shared `services/video_tail9.py` contract is not modified by this task.

## Error and transaction semantics

- UI state is committed only after the Telegram edit/reply succeeds.
- Video Edit uses its own state rollback guard; the shared Product Video
  failure guard is not made responsible for Video Edit state.
- Successful callback order is render → commit/delete state → answer callback.
- Final confirmation uses an idempotency key and a callback claim; retries return
  the existing job/status and cannot create a second job.
- Invalid media keeps the intake active with a Vietnamese corrective message.
- Failed inspection or FFmpeg execution creates no success receipt and no wallet
  mutation.
- Delivery uncertainty does not trigger a second send.
- A valid success requires output existence, MP4 validation, ffprobe evidence,
  output hash/size, Telegram message ID, and Telegram file ID.
- No exception falls through to an unrelated product or generic public error.

## Files and ownership boundaries

Expected modifications are limited to:

- `bot.py`: Video Edit callback/rendering only, plus at most the narrow saved-
  language correction when the existing `lvs27b` root returns to the hub;
- `services/video_edit_state_machine.py`: explicit navigation transitions;
- `services/video_edit_capabilities.py`: truthful local capability exposure;
- `services/video_local_editing.py`: bounded local filters/plan fields;
- `services/video_editengine1.py`: validated zero-price local contract;
- `local_worker.py`: execution of newly specified local plan fields;
- focused Video Edit/27B tests and local fixture helpers.

The task must not modify Product Video engines/contracts/tests, SubDub, Frame
Video, shared menu order/labels, Railway environment, VPS, provider adapters,
PayOS, DB schemas outside `video_editengine1`, wallet logic, webhook ownership,
Music/Suno, Motion, or Higgsfield.

## Test and verification design

Tests are written before each behavior change and must visibly fail for the
expected missing behavior before implementation.

### Pure contract tests

- exact hub labels/order/callbacks and optional 27B row;
- every visible callback has exactly one owner and handler;
- legacy callback mapping and no duplicate keyboard rows;
- explicit parent map for every screen and exact Back matrix;
- Vietnamese saved-language authority;
- state/session isolation, stale/malformed/duplicate callbacks, and required-step
  enforcement;
- capability truth: every actionable item has a local owner and plan mapping;
- no provider-only item appears as actionable;
- local-free job preflight accepts `price_xu=0` only for Video Edit;
- provider, wallet, other-product route, and production side-effect scans.

### Real local media tests

A generated short MP4 fixture with video and sine-wave audio, a second clip, a
small logo, timed text, and a valid SRT are processed with the discovered local
FFmpeg/ffprobe binaries. Focused tests validate:

- trim and remove-middle/split outputs;
- concat and reorder duration/order;
- crop/fit/resolution;
- speed, rotation, flip;
- volume, mute, and available loudness normalization;
- brightness, color, sharpen, available denoise;
- text, logo, SRT;
- available local effects and conditional crossfade;
- final MP4 format, dimensions, duration tolerance, audio policy, hash, and size;
- failed commands leave no final artifact or fake receipt.

Runtime-filter-dependent buttons are shown only when the same preflight used by
tests passes.

### Adapter and regression tests

- fake Telegram flow from `/start` → Video menu → hub → every lane;
- existing 27B flow remains isolated and its root Back returns to the Vietnamese
  Video Edit hub without creating editor state;
- final confirm idempotency and status truth;
- `video_editengine1` worker/receipt suite;
- callback-owner collision and cross-product route suite;
- Product Video UI freeze and engine contract regressions;
- SubDub receipt-truth regressions;
- 27A/27B isolation regressions;
- `py_compile`, `bot.py` tokenize/narrow AST, JSON/secret/private-path scans,
  `git diff --check`.

Production media smoke, deployment, provider calls, wallet mutation, and
Railway/VPS changes are not part of implementation verification unless the owner
opens a separate deployment gate.

## Completion criteria

The task is complete only when:

1. every visible Video Edit button performs a verified local action or truthful
   capability explanation;
2. all listed local operations produce valid media in focused tests;
3. every Back returns to its exact invoking parent;
4. all public Video Edit copy is Vietnamese-first and contains no raw IDs;
5. the independent planning preview remains unchanged and creates no editor
   state;
6. no provider-only feature is falsely actionable;
7. duplicate/stale/failure cases are safe and idempotent;
8. zero-price local jobs deliver truthfully without wallet mutation;
9. callback collisions and cross-product routes are zero;
10. relevant regressions, compile, static checks, and diff checks pass;
11. Product Video, SubDub, Frame Video, provider/worker production configuration,
    Railway, VPS, wallet, and webhook behavior remain unchanged.
