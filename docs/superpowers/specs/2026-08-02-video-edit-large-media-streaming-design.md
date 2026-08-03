# Video Edit Large-Media Streaming Design

**Status:** Approved by the owner on 2026-08-02 with the explicit direction to follow the proven SubDub processing method while keeping SubDub code read-only.

## Purpose

Make every existing Video Edit lane accept and return videos according to the real capacity of the deployed Local Bot API and local FFmpeg worker, without an arbitrary public duration or megabyte ceiling. Production Telegram transport is already hosted at `tg.toanaas.vn`. The 60-second and 20-MiB marks select the short-media or VPS large-media lane; they never reject an otherwise processable file. The product must remain truthful: it must never promise literal unlimited processing, and it must reject a job before side effects only when transport, disk, workspace, timeout, or worker capacity cannot safely handle it.

This is a transport and resource-safety enhancement for Video Edit only. It does not change the Video Edit menu structure, edit semantics, pricing, provider policy, or database schema.

## Current evidence

The current Video Edit path cannot process large media safely even though `tg.toanaas.vn` is deployed:

- `services/video_local_validation.py` defaults input to 50 MiB, duration to 30 minutes, workspace to 1 GiB, and FFmpeg timeout to 600 seconds.
- `bot.py::inspect_video_editor_source` rejects the input limit before inspection and has a `download_as_bytearray()` fallback.
- `local_worker.py::telegram_json`, `telegram_download_file`, and `telegram_send_video_receipt` hard-code `https://api.telegram.org` instead of using the configured Local Bot API origin and shared-secret header.
- Worker input is written incrementally, but the transfer has a fixed 60-second read timeout and a fixed byte cap.
- Worker delivery reads the entire MP4, copies it into a multipart `bytearray`, and copies that body again before sending. Peak memory can exceed three times the artifact size.
- The worker tries `sendVideo` before `sendDocument`, even when the artifact is already known to require document delivery.
- A process heartbeat exists, but a long Video Edit download/render/upload does not renew durable liveness for the specific job.

The SubDub implementation is a read-only reference. Its Local Bot API URL policy, source classification, adaptive timeout, monotonic progress, and delivery receipt ideas are useful. Its byte-buffered intake, byte-buffered delivery, in-process claims, and provider-specific chunk pipeline must not be copied.

## Product contract

### User-visible behavior

- Remove fixed `50 MB` and fixed-duration claims from Video Edit copy when Local Bot API mode is active.
- Describe capability truthfully: the system checks the file and current processing capacity before accepting it.
- Do not display “unlimited”, “no limits”, or a maximum that the active transport cannot prove.
- Treat `duration <= 60 seconds AND size <= 20 MiB` as the short-media lane.
- Treat `duration > 60 seconds OR size > 20 MiB` as the VPS large-media lane through `tg.toanaas.vn` and `/localfile`.
- If size or duration is unknown, choose the large-media lane so the safe streaming path handles it.
- Exactly 60 seconds or exactly 20 MiB remains in the short-media lane.
- Crossing the routing threshold must never itself produce a “too large” or “too long” message.
- When capacity is insufficient, return a localized reason and the exact Back target for the current Video Edit screen. Do not create or submit a render job.
- Preserve all four primary Video Edit functions, their current subflows, `videoedit|` callback namespace, saved language, Back hierarchy, one-active-job behavior, progress panel, refresh behavior, idempotency, and delivery receipts.
- Large inputs may take longer to inspect, download, render, and upload. Status must report the real stage; it must not fabricate percentages.

### Technical capability policy

- Production uses the single configured Local Bot API origin `https://tg.toanaas.vn` for both lanes. “Short-media Telegram lane” means the compact Telegram workflow on that configured origin; it does not mean switching the production bot back to Telegram Cloud.
- The public application-level input-byte and duration rejection limits default to disabled (`0`). Admission is based on transport capability, file metadata, current free disk, estimated workspace, adaptive deadline, and concurrency.
- Internal emergency caps remain configurable and fail closed. They are operational safety boundaries, not advertised product limits.
- A Cloud Bot API origin may exist only as a development/rollback configuration. If it is active, enforce its real download and delivery boundaries; never combine Cloud and Local origins for one production bot session.
- Keep one active Video Edit job per user and the existing global FFmpeg concurrency policy.
- Logo, subtitle, split-count, concat-count, codec/container, resolution, and safe-path constraints remain in force because they protect correctness rather than impose an arbitrary video-size ceiling.

## Chosen architecture

Use the same staged operating method as SubDub: Local Bot API intake, source classification, preflight, short/direct versus long/checkpointed execution, monotonic progress, delivery-once receipt evidence, and guarded cleanup. Implement those semantics through a Video Edit-specific file-backed streaming adapter while keeping the current Video Edit engine, local-worker job, outbox, charge policy, validation, and receipt contracts.

### Deterministic lane selection

Add one pure classifier whose result is persisted in existing Video Edit job detail, not a new table:

```text
short_media  = known_duration <= 60 seconds AND known_size <= 20 MiB
large_media  = NOT short_media
```

The classifier uses declared Telegram metadata for the initial choice and re-evaluates against the actual streamed byte count and FFprobe duration before FFmpeg. Re-evaluation may promote `short_media` to `large_media`; it must never demote a job after the large-safe path has started. Both lanes end in the same Video Edit engine, validation, status, and receipt flow.

This classifier selects transfer, timeout, and job policy; it does not create a second bot session. `tg.toanaas.vn` is the Telegram Local Bot API transport/storage origin. Unless a separately deployed Video Edit FFmpeg worker on that VPS is explicitly designed and approved, rendering remains on the existing Video Edit worker.

### SubDub alignment contract

Video Edit follows the same observable processing phases as SubDub:

1. classify the Telegram source and transport capability;
2. create a deterministic source/job fingerprint;
3. fetch through `tg.toanaas.vn` with bounded retries and classified errors;
4. perform real FFprobe preflight before editing;
5. run a direct whole-file path for short media;
6. run a durable long-media project path with checkpoints, adaptive timeout, and liveness for large media;
7. persist monotonic progress without inventing percentages;
8. validate the canonical MP4 before delivery;
9. choose video or document delivery before sending;
10. persist Telegram message/file receipt before terminal completion;
11. recover from a validated canonical artifact without rerendering or resending an ambiguous delivery;
12. clean workspace only after active-job, receipt, path, and liveness guards pass.

Alignment means identical safety and lifecycle semantics, not importing or modifying `subdub_*` modules. Video Edit must improve the known SubDub memory boundary by using file paths and bounded chunks instead of whole-file `bytes`, `bytearray`, or `BytesIO` payloads. It also keeps durable database job/outbox fencing rather than copying SubDub's in-process dictionary claims.

The long-media project planner may split work only when the selected Video Edit operation is segment-safe. Timeline-global operations such as concat ordering, transitions across boundaries, whole-track loudness analysis, or operations whose state crosses a cut run as one long checkpointed FFmpeg part with heartbeat renewal. Natural split/cut outputs and segment-local transforms may use stable part IDs and resume from validated parts. This prevents seams, audio drift, duplicate frames, and repeated delivery while preserving the SubDub recovery model.

### Rejected alternatives

1. **Raise the current ENV limits only.** This leaves hard-coded Cloud URLs, fixed timeouts, repeated downloads, whole-file RAM buffering, and ambiguous large-output fallback. It does not solve the problem.
2. **Copy the SubDub pipeline into Video Edit.** SubDub still buffers important paths and has provider-specific and in-process state that conflicts with Video Edit's durable job/outbox/receipt model.
3. **Introduce a persistent source cache and a separate inspection worker immediately.** This could eliminate the bot/worker double download, but it adds cache ownership, TTL, cleanup, and recovery complexity. It is deferred until file-backed streaming is proven in production.

## Components

### 1. Telegram endpoint policy

Extend `services/telegram_transport.py` only with dependency-free builders and classifiers:

- normalize and validate the Cloud or Local Bot API root;
- build Bot API method, Cloud file, and Local `/localfile` URLs;
- map the Local Bot API absolute file path to the reverse-proxy path without traversal;
- emit the shared-secret header only for the configured Local Bot API origin;
- reject redirects and unsafe origins before credentials leave the process;
- classify errors without including token-bearing URLs or secrets.

The module remains policy-only and performs no network or filesystem I/O.

### 2. Video Edit media transfer

Create `services/video_edit_media_transport.py` with two file-backed operations.

`download_file_to_path(...)`:

- calls `getFile` on the configured endpoint;
- uses the current compact Video Edit path for proven short media and the Local `/localfile` file-backed path for large or unknown media; both use the single configured `tg.toanaas.vn` Bot API origin in production;
- writes chunks to a sibling `.partial` file;
- checks declared size, running byte count, deadline, cancellation, free disk, and workspace budget;
- updates SHA-256 and progress incrementally;
- atomically renames only after a non-empty complete transfer;
- removes the partial file after every terminal failure;
- may retry only before a complete local artifact exists, with bounded backoff and the same `file_id`.

`send_artifact_from_path(...)`:

- reads the artifact through bounded chunks and constructs multipart data as a stream with a known `Content-Length`;
- selects `sendVideo` only for a compatible artifact below the configured preview threshold;
- selects `sendDocument` immediately for a known large artifact;
- never performs a second send after a timeout, connection loss, server-side failure, or any other outcome that may have accepted the first upload;
- permits `sendVideo` to `sendDocument` fallback only after a deterministic client rejection proving no delivery occurred;
- returns the existing receipt identity: `message_id`, `file_id`, delivery method, byte count, and artifact SHA-256.

The adapter accepts injected HTTP, clock, disk, and progress dependencies so focused tests never need Telegram or large allocations.

### 3. Bot-side Video Edit inspection

Update only the Video Edit inspection path in `bot.py`:

- use the file-backed downloader instead of `telegram_local_media_fetch()` or `download_as_bytearray()`;
- classify the upload using the exact 60-second/20-MiB rule before transfer and promote unknown or newly oversized media to the large-safe lane;
- stream into the inspection temporary directory, probe with the existing `video_local_validation` functions, and clean the directory on exit;
- use Telegram-declared size for early resource admission, then enforce actual streamed size;
- retain SHA-256, duration, stream, codec, and resolution evidence from the actual downloaded file;
- preserve the current concurrency/state guards so an inspection failure cannot overwrite a newer user action;
- return localized transport/resource reasons without creating a render job.

The first implementation intentionally retains the bot/worker double download. Removing it requires a separate durable cache design and is not part of this phase.

### 4. Local worker input and output

Update only Video Edit paths in `local_worker.py`:

- build endpoint config from the same environment names used by the bot;
- honor the persisted lane hint but revalidate it from the downloaded file before FFmpeg;
- replace `_local1_download_asset` transport with `download_file_to_path` for source, concat, logo, and subtitle assets;
- replace `telegram_send_video_receipt` use in `run_video_local_edit` with `send_artifact_from_path`;
- preserve the current manual/split engine, FFmpeg commands, MP4 validation, artifact order, charge policy, job type, and receipt schema;
- keep any explicitly configured rollback/development Cloud origin bounded to Cloud capability and never dynamically switch the production bot between Cloud and Local origins;
- never call a provider, Product Video worker, SubDub code, wallet, Xu, PayOS, or a new database table.

Unrelated `local_worker.py` routes retain their current behavior.

### 5. Resource admission and adaptive deadlines

Add Video Edit-specific policy helpers to `services/video_local_validation.py` or a new focused `services/video_edit_resource_policy.py` if the validation module would become mixed-purpose.

Admission uses:

- sum of declared input/asset bytes;
- current free bytes at the actual workspace volume;
- a fixed free-space reserve;
- an operation-aware scratch/output multiplier for manual, concat, split, overlay, and transcode plans;
- one active user job and global FFmpeg concurrency;
- transport mode and its hard protocol capability;
- an adaptive transfer/render deadline derived from size, duration, resolution, output count, and operation class;
- an internal configurable maximum deadline and emergency byte cap.

Known insufficient capacity fails before job creation. Unknown metadata may proceed only under the streaming byte guard and must fail cleanly before FFmpeg if the real file exceeds current capacity.

The public Video Edit limits view reports capability categories and current acceptance logic, not internal emergency values as a permanent product promise.

### 6. Durable job liveness

Use the existing Video Edit job/outbox records; do not alter the schema.

- Start a per-job liveness context after the worker claims a Video Edit job.
- During download, render, validation, and upload, renew existing job/outbox lease fields and persist the real stage at a bounded interval.
- Liveness updates must be monotonic and must not replace an already terminal job.
- Stop renewal before writing the terminal receipt.
- A stale worker cannot overwrite a newer terminal state or produce a second delivery.
- Recovery may reuse a validated canonical output only when the existing receipt state proves it was not already delivered. It must never blindly rerender or resend an ambiguous delivery.

### 7. Long-media project checkpoints

Add Video Edit-owned checkpoint helpers; do not import the SubDub implementation.

- Derive a stable project key from user ID, source SHA-256, canonical edit-plan hash, state revision, and output index.
- Persist the current stage, validated part identities, canonical artifact identity, delivery cursor, and last liveness time inside existing job/outbox detail fields or worker workspace manifests; do not add a table.
- A validated part is reusable only when its source hash, plan hash, expected time range, output hash, and FFprobe evidence all match.
- A plan classifier explicitly marks an operation `segment_safe` or `whole_timeline_required`.
- `segment_safe` plans may resume deterministic parts and assemble them once.
- `whole_timeline_required` plans retain one stable part/checkpoint and restart only when no canonical output or ambiguous delivery evidence exists.
- Checkpoints never authorize a new Telegram send. The delivery cursor and durable receipts remain the delivery source of truth.

## Data flow

1. The user uploads a Video Edit source.
2. The bot validates ownership, extension, declared metadata, and current resource admission.
3. The bot classifies the source as `short_media` only when both duration and size are known and within 60 seconds/20 MiB; otherwise it selects `large_media`.
4. The bot transfers from the single configured Bot API origin, using Local `/localfile` streaming for the large-media lane, hashes and probes the inspection file, and then saves only the existing canonical Video Edit metadata/state.
5. The user configures any existing manual, split, goal-based, or quality operation and confirms.
6. Existing idempotency creates at most one Video Edit job/outbox record.
7. The worker claims the job and starts per-job liveness.
8. The worker streams all Telegram assets into the job workspace and verifies size/hash/metadata, promoting the lane when actual evidence crosses a routing threshold.
9. The existing local FFmpeg engine renders and validates MP4 outputs.
10. The worker streams each artifact to Telegram, choosing document delivery before upload when required.
11. Each accepted artifact persists its message/file receipt before the next artifact begins.
12. The job becomes 100% complete only after every expected receipt is durable; cleanup runs with the existing delivery-ambiguity rules.

## Failure behavior

- Unsafe URL, redirect, missing proxy secret, forbidden response, Cloud-size violation, resource shortage, timeout, partial download, invalid media, stale lease, and invalid receipt have distinct internal reason codes.
- Public messages are localized and concise and never expose paths, tokens, headers, raw network exceptions, or infrastructure limits as a promise.
- Download failure removes `.partial` data and creates no render side effect.
- FFmpeg failure produces no delivery and preserves truthful failed status.
- Deterministic Telegram rejection may end as `delivery_rejected`.
- Ambiguous Telegram response ends as `delivery_unknown`; it is not automatically resent.
- Partial multi-artifact delivery retains every durable receipt and never restarts from artifact one.

## Security and privacy invariants

- The bot token may appear only in validated request paths and never in logs, exceptions, DB fields, status text, or test snapshots.
- The Local Bot API shared secret is sent only to its exact configured HTTPS origin.
- Redirects are disabled for credential-bearing media requests.
- Every destination and artifact path must remain inside the expected Video Edit workspace and may not be a symlink.
- Only the current user's Telegram file IDs and Video Edit state/job/receipt are used.
- No Product Video, Frame Video, SubDub, wallet, Xu, PayOS, provider, or schema behavior changes.

## Test contract

### Pure and focused tests

- exact Cloud/Local URL and secret-header classification;
- absolute Local Bot API path to `/localfile` mapping and traversal rejection;
- token/secret redaction for every failure class;
- chunked download writes incrementally, hashes correctly, atomically renames, and deletes partials;
- a synthetic large stream never enters a single `bytes`/`bytearray` proportional to file size;
- known-size and unknown-size disk admission;
- operation-aware workspace estimate and internal emergency cap;
- adaptive timeout ordering for short/small versus long/large inputs;
- exact boundary cases at 60 seconds and 20 MiB, either-threshold promotion, and unknown-metadata promotion;
- single-origin production behavior and bounded rollback/development Cloud configuration;
- stable source/job fingerprint and canonical plan hash;
- segment-safe versus whole-timeline planner classification;
- validated-part resume, mismatched-part rejection, and canonical-artifact recovery;
- SubDub lifecycle parity without importing, editing, or calling any `subdub_*` module;
- deterministic direct `sendDocument` selection for large output;
- streaming multipart length and receipt parsing;
- timeout/5xx ambiguity never causes a second send;
- per-job lease renewal, stale-writer fencing, and terminal-state protection;
- one-active-job, callback ownership, cross-route isolation, and submit idempotency.

### Existing regression gates

- all focused Video Edit route, state, manual, split, overlay/logo/watermark, status, receipt, worker, and callback suites;
- clean-main versus branch comparator with zero new failures and zero unexpected node delta;
- changed-module compile and static scope audit;
- no changed `subdub_*`, Product Video, Frame Video, wallet, PayOS, provider, or schema file.

### Real-media verification

- Use local deterministic fixtures first: small control, long-duration low-bitrate MP4, and a sparse/streamed large-body transport fixture that does not require proportional RAM.
- Exercise download, FFprobe, one real manual edit, MP4 validation, document delivery selection, receipt persistence, and cleanup.
- After merge/deploy, perform one owner-authorized Telegram test through `tg.toanaas.vn` with no provider and no Xu/wallet side effect. Record declared size, streamed size, SHA-256, duration, peak process memory, delivery method, message/file receipt, and cleanup result.
- Do not claim large-media production PASS unless the deployed SHA and Telegram receipt are both proven.

## Rollout and rollback

- Land this as a separate Video Edit PR after the pending callback-context PR is terminal.
- Keep Local Bot API activation environment-driven. Production remains on `tg.toanaas.vn`; Cloud is a bounded rollback/development configuration, not per-file routing.
- Deploy only after focused, comparator, compile, spec, and code-quality review pass.
- If live liveness, download, or delivery fails, disable the Video Edit large-media capability flag and preserve the existing small-file path while retaining all job/receipt evidence. Do not retry an ambiguous delivery.

## Explicit non-goals

- No task history.
- No persistent cross-job source cache in this phase.
- No provider-based editing.
- No SubDub modification or code copy.
- No Product Video or Frame Video change.
- No wallet, Xu, PayOS, or database-schema change.
- No promise that every theoretically sized Telegram file can be processed regardless of current machine resources.
