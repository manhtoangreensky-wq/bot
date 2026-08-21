# SubDub per-speaker automatic acoustic-register casting

## Goal

Add an explicit Auto voice option to the two SubDub lanes that synthesize
speech (`dub_only` and `subtitle_plus_dub`). Auto preserves diarized,
chunk-scoped speaker labels, estimates only the source audio's acoustic pitch
register as `low`, `high`, or `unknown`, assigns validated TTS voices
deterministically per speaker, and synthesizes each cue with that assignment.

Auto speaker recognition is a separate blackbox adapter. It must not replace,
copy, or modify the existing default/manual lane engine. The Auto adapter wraps
only the three dependencies already injected into the stable shared pipeline.
It owns an Auto-only preflight before delegation so post-text-preparation
confirmation can pause safely without entering the protected pipeline; ASR,
the already-existing translation path, scalar
TTS, timeline construction, audio QC, mux, artifact validation, delivery, and
charging continue to run through their current implementation.

Manual female, manual male, and saved/custom voice choices remain unchanged and
always override Auto.

This feature does not identify people and does not infer or claim anyone's
identity or personal gender. Acoustic register is only a local TTS-casting
signal; public copy must not describe it as proof of a person's gender.

## Delivery status and phase order

Tasks 1–3 are historical implementation phases. Task 3 is complete: canonical
cue IDs, chunk-scoped speaker metadata, exact sidecar identity, cache/checkpoint
preservation, and the approved duration-bounded delivery timeout are already in
the branch history.

The only approved order for the remaining work is:

1. Task 4: central exact-state predicate, pure bounded local acoustic-register
   classifier, and the isolated nonblocking Auto-blackbox preflight seam,
   without changing the default route and without assigning/annotating voices,
   installing resolve/synthesize wrappers, or delegating to the lane runner;
2. Task 5: provider-neutral stable per-speaker voice assignment and the
   Auto-only per-cue scalar-TTS wrapper, exact identity annotation, failure-slot
   normalization, and lane-runner delegation;
3. Task 6: Auto state/button and native 17-locale copy in both dubbing lanes;
4. Task 7: separate Auto pricing, after the language-safe word counter and
   estimate-to-exact-confirmation contract are proven;
5. Task 8: final protected verification.

UI work does not precede voice assignment, and pricing is last. A later phase
must not be used to weaken an earlier fail-closed contract.

Task 6 may add and directly test button/callback/dispatch code, but the
user-visible Auto route remains fail-closed and unreachable. Task 7 atomically
enables the button, exact-confirm callback, and dispatch only after the receipt
gate, pricing, and protected comparators pass. No intermediate release may
expose Auto with manual pricing or without resumable exact confirmation.

## Scope

Future implementation may touch only the established SubDub seams:

- `services/subdub_speaker_cast.py`: bounded classifier, label cap, validated
  provider-neutral voice pools, and deterministic assignment;
- create `services/subdub_blackboxes/auto_speaker.py`: the central exact-state
  predicate and Auto-only preflight/wrapper around the injected
  `prepare_subtitles`, `resolve_voice_id`, and `synthesize_segments`
  dependencies;
- `bot.py`: exact-pair Auto dispatch, bounded PCM extraction support, Auto
  state/reset/button in `dub_only` and `subtitle_plus_dub`, bounded exact
  confirmation receipt/resume handling, estimate/exact-confirmation
  integration, the existing one-shot charge path, and canonical copy
  consumption;
- `services/pricing_guide_content.py`: native Auto label/explanation/failure and
  pricing copy for all 17 registered locales;
- one focused language-safe billable-word counter module if the repository does
  not already provide a proven equivalent;
- focused tests with zero live provider calls.

The following stable engine files are protected and must remain byte-identical
through Tasks 4–8:

- `services/subdub_blackboxes/__init__.py`;
- `services/subdub_blackboxes/base.py`;
- `services/subdub_blackboxes/dub_only.py`;
- `services/subdub_blackboxes/subtitle_dub.py`;
- `services/subtitle_dub_product_pipeline.py`.

Protected behavior:

- manual voice modes and subtitle-only/translation-only lanes;
- provider order, adapters, live voice catalogs, ENV, credentials, and endpoints;
- Video Edit, Logo/Watermark, Video AI, Product Video, database, PayOS, wallet,
  deployment, and unrelated pricing/discount policies.

This document update authorizes no runtime or pricing implementation, provider
call, wallet mutation, ENV change, deployment, or claim about live provider
inventory.

## Stable shared-pipeline baseline and dispatch boundary

PR613 established the reusable lane blackbox in implementation commit
`00aff00871c61b4caefc2e165c1216cdbb2d7d63`, merged as
`61f17108b9482fa1f6fef0e1e12bf8d7f647bfb4`. At this document baseline,
`2e0453058c54e4169e80ffd356079e5960ee4674`, each protected service blob is
identical to both PR613 commits:

| Protected path | Git blob |
| --- | --- |
| `services/subdub_blackboxes/__init__.py` | `22f06a3dac77764ca702a9572d54220df4547673` |
| `services/subdub_blackboxes/base.py` | `6a87de96d0820a363ce8447be7fae51ec95bc679` |
| `services/subdub_blackboxes/dub_only.py` | `12f641b243a950e5a250105a30adffb27082233e` |
| `services/subdub_blackboxes/subtitle_dub.py` | `5531995d251dc1857d0f2a86ccf6ca75ed27b0cc` |
| `services/subtitle_dub_product_pipeline.py` | `24f8b45b8944b674e4d79b649e084916959bb2fe` |

The reusable chain is:

```text
bot core
-> subdub_blackboxes.run_subdub_lane_blackbox
-> subtitle_dub_product_pipeline.run_subdub_pipeline
-> injected prepare/resolve/synthesize dependencies
-> existing timeline/QC/mux/artifact/delivery/charge behavior
```

The repository has one Auto predicate. It is exact, not truthy or partial, and
lives in the Auto module:

```python
def is_auto_speaker_state(state: Mapping[str, object] | None) -> bool:
    current = state or {}
    return (
        current.get("voice_kind") == "auto_speaker_gender"
        and current.get("voice_selection_mode") == "auto_speaker"
    )

is_auto_speaker = auto_speaker.is_auto_speaker_state(state)
```

Only that exact pair dispatches to
`services.subdub_blackboxes.auto_speaker.run_auto_speaker_blackbox`. Every
other state—including either key by itself, stale/malformed combinations,
manual female/male, saved/custom, and the default state—must retain the literal
existing call:

```python
product_result = await subdub_blackboxes.run_subdub_lane_blackbox(
    lane_mode=mode,
    runner=subtitle_dub_product_pipeline.run_subdub_pipeline,
    # the current payload and injected dependencies remain unchanged
)
```

Every Auto-only decision must call this same predicate: dispatch, quote,
confirmation, read-only balance guard, invoice construction, actual spend
amount, and the final one-shot charge. No caller may reproduce a one-key or
truthy variant. Either key alone and every malformed cross-pair use the current
manual/default route, quote, confirmation behavior, invoice, and charge amount.

The Auto module owns preflight before making that same lane call; it is not a
second pipeline. The following is the Task-5-complete adapter contract. Task 4
ends after the isolated gate/classifier result and must not assign or annotate a
voice, install resolve/synthesize failure behavior, or delegate to the lane
runner. Task 5 extends that proven seam into the complete adapter described
below. `run_auto_speaker_blackbox` first verifies the exact predicate,
calls the injected current prepare dependency once as
`prepare_subtitles(state, require_auto_cast=True)`, and awaits an injected async
`post_prepare_gate(prepared, state)`. Only a continue decision may reach local
classification and assignment. The wrapper then passes the same lane mode,
runner, payload, and all non-Auto dependencies to `run_subdub_lane_blackbox` and
substitutes only the three existing injected callables:

1. `prepare_subtitles`: after preflight, classification, assignment, and both
   exact identity joins, pass a closure that returns the already prepared and
   annotated structure. The lane/shared pipeline still invokes its normal
   prepare dependency, but this closure performs no ASR, translation, cache
   rewrite, or provider call.
2. `resolve_voice_id`: validate the Auto cue assignments and return the first
   assigned cue's validated private `tts_voice_id` only as the compatibility
   scalar required by the shared pipeline's current nonempty guard. It must not
   invent a provider ID or perform a live catalog lookup.
3. `synthesize_segments`: validate every cue has a nonempty validated private
   `tts_voice_id` before the first TTS call, then invoke the existing injected
   scalar synthesizer sequentially once per cue with that cue's ID. It preserves
   cue count, order, timestamps, and the result shape consumed by the unchanged
   shared timeline/QC path.

The gate is an Auto-only support callback, not a fourth protected-pipeline
dependency. If it returns a structured pause, the wrapper returns that result
before PCM extraction, classifier execution, lane-runner delegation, TTS,
render, invoice spend, or charge. The wrapper also catches
`AutoCastUnavailable` and `AutoCastManualRequired` raised during preflight or
inside either Auto dependency wrapper while the lane runner is executing; the
exceptions do not fall through to a generic protected-pipeline failure.

Beginning only in Task 5, because the protected pipeline may normalize a
dependency exception into a generic result, the Auto resolve/synthesize
wrappers also record only these two
validation exceptions in an invocation-local failure slot before re-raising.
After delegation returns or raises, `run_auto_speaker_blackbox` checks that slot
before accepting any generic result and emits the canonical manual-required
result when set. This is not global state, does not parse generic copy, and does
not intercept unrelated provider/render/mux/charge/delivery failures.

The Auto wrapper must use the already-landed current seams. It must not copy old
`bot.py` code, revert later wrapper/report evolution, or fork ASR/TTS/mux/
delivery logic from PR613.

The one required bot-local prepare seam change is additive and defaults closed:

```python
async def _prepare_subtitles_for_blackbox(
    service_state: dict,
    *,
    require_auto_cast: bool = False,
) -> dict:
    prepared = await video_dubbing_prepare_subtitles(
        context,
        service_state,
        uid,
        allow_confirmed_product=confirmed_product,
        require_auto_cast=bool(require_auto_cast),
        **prepare_kwargs,
    )
```

The protected/default shared pipeline continues to invoke
`prepare_subtitles(state)` with the keyword omitted, so default/manual and every
partial or malformed Auto pair forward `False`. Only the exact Auto pair enters
the wrapper, which calls the injected prepare once with `True` per handler
invocation. Single-invocation tests capture `[True]`; pause/resume tests capture
one `True` per invocation but exactly one mocked ASR total because resume is
cache-only. Default/manual/partial/malformed cases capture `[False]` and never
enter Auto preflight.

## Executable text-preparation pause and durable resume

Task 4 creates the injected async `post_prepare_gate` seam with a fixture-only
continue implementation; it imports no pricing logic. Task 7, last, supplies
the real exact-confirmation gate. The first authorization is explicitly a
**text-preparation authorization**, not an ASR-only authorization. It permits:

- at most one ASR call when no valid source subtitle/ASR cache exists; and
- at most one call through the existing translation path, but only when
  `resolve_subdub_dub_audio_policy(state, prepared)` selects translated text for
  TTS and no valid translation cache exists for the exact source text and target
  language.

It permits zero classifier, voice assignment, TTS, render, spend, refund,
delivery, or other wallet mutation. Exact billing is counted over the final cue
text in the policy-selected `tts_segments`, not over whichever source/output
list happens to be convenient. When that exact selected text already exists
before provider preparation—source cues for a source-text selection, or a valid
cached translation for a translated-text selection—the quote is exact and the
existing confirmation is the only confirmation. An existing source subtitle
alone is not exact when policy selects a still-missing translation.

The executable sequence is:

```text
first handler invocation
-> exact Auto predicate
-> prepare(require_auto_cast=True)
-> text preparation: matching cache, otherwise ASR at most once and existing
   translation at most once only when the selected TTS text requires it
-> resolve_subdub_dub_audio_policy(...)["tts_segments"]
-> exact count over the final policy-selected TTS cue text
-> post_prepare_gate(prepared, state)
-> either continue, or return AUTO_EXACT_CONFIRMATION_REQUIRED

second exact-confirm handler invocation, when required
-> exact Auto predicate
-> rehydrate the same durable job/workspace
-> cache-only prepare(require_auto_cast=True) from matching source subtitle,
   selected translated text when applicable, and sidecar
-> validate confirmed receipt in post_prepare_gate
-> classify/assign/identity-join
-> lane runner with already-prepared closure
-> protected shared pipeline/TTS/render/actual one-shot charge
```

When the exact selected-text count was unknown at the first quote or differs
from it, the gate performs the existing read-only balance guard and returns this
bounded control result:

```python
{
    "ok": False,
    "status": "AUTO_EXACT_CONFIRMATION_REQUIRED",
    "resume_required": True,
    "receipt": {
        "version": AUTO_EXACT_RECEIPT_VERSION,
        "quote_version": auto_quote_version,
        "internal_job_id": internal_job_id,
        "job_key_sha256": job_key_sha256,
        "session_nonce": session_nonce,
        "owner_user_id": owner_user_id,
        "chat_id": chat_id,
        "mode": mode,
        "source_sha256": source_sha256,
        "media_sha256": media_sha256,
        "subtitle_sha256": subtitle_sha256,
        "selected_tts_text_sha256": selected_tts_text_sha256,
        "translated_selected_text_sha256": translated_selected_text_sha256,
        "sidecar_sha256": sidecar_sha256,
        "timeline_signature": timeline_signature,
        "actual_billable_words": actual_words,
        "actual_auto_xu": actual_auto_xu,
        "actual_subtitle_xu": actual_subtitle_xu,
        "actual_total_xu": actual_total_xu,
        "expires_at": expires_at,
        "consumed": False,
        "claim_state": "unconsumed",
    },
}
```

The authoritative pause is the durable nonterminal job state
`awaiting_auto_exact_confirmation`. The bounded receipt and existing workspace
reference are persisted through
`persist_subtitle_dub_pipeline_job_snapshot(...)`, which already delegates to
`save_engine_async_job(...)`; no DB schema is added. `USER_PENDING` may mirror
display state, but it is never receipt, claim, resume, or ownership authority.
The durable receipt binds the exact job/session nonce, owner/chat and mode,
source/media/subtitle/selected-text hashes, the translated-selected-text hash
when translation is selected, timeline and sidecar hashes, exact count, Auto
and unchanged subtitle components, total, receipt/quote versions, expiry, and
consumed/claim state. It stores no prepared segment list, classification, cast,
PCM, provider payload, credential, or wallet state. The callback contains only
the bounded public job token and opaque session nonce, never any hash, count,
total, path, or provider value.

`_execute_video_dubbing_pipeline_core` must intercept
`AUTO_EXACT_CONFIRMATION_REQUIRED` immediately after the Auto blackbox returns
and before its generic `if not product_result.get("ok")` failure normalizer.
`execute_video_dubbing_pipeline` must then intercept the same control result
before manifest/update defaults map `ok=False` to `failed_no_charge`. It keeps
`terminal_state` empty, persists `status`, `lifecycle_state`, `current_stage`,
and `progress_stage` as `awaiting_auto_exact_confirmation`, keeps the workspace,
and renders the exact-confirm/cancel panel. Both
`awaiting_auto_exact_confirmation` and
`resuming_auto_exact_confirmation` are nonterminal active states in acquisition,
dedupe, lifecycle, and `SUBDUB_WORKSPACE_ACTIVE_STATUSES`; neither may be
cleaned or pruned as an unknown/failed job.

The exact-confirm callback rehydrates the existing job with
`get_engine_async_job(...)`/the existing engine-job lookup, verifies owner,
chat, mode, job key/session nonce, and safe existing workspace, and restores the
in-memory registry only as a cache of that durable authority. A dedicated
per-job `asyncio.Lock` serializes confirm/cancel claims. Under that lock the
callback reloads the latest durable snapshot and performs compare-and-set from
unexpired `status="awaiting_auto_exact_confirmation"`,
`claim_state="unconsumed"`, `consumed=False`, and the expected receipt/quote
versions to `status="resuming_auto_exact_confirmation"`,
`claim_state="resuming"`, and `consumed=True`, with claim timestamps/token. It
persists that claim before releasing the lock or resuming work. Exactly one of
two concurrent callbacks can claim; the loser renders the durable current
status and performs no preparation or side effect.

Resume invokes the current prepare seam once again in cache-only mode. It may
accept only workspace artifacts whose source/media/subtitle/selected-text,
translated-selected-text when applicable, sidecar, and timeline hashes plus
actual count/components/total and receipt/quote versions all match the consumed
receipt. It makes zero new ASR and zero new translation calls. A missing, stale,
mismatched, or expired receipt/cache fails closed instead of retranscribing or
retranslating. After the gate continues, the lane prepare closure returns the
already prepared annotated structure, so delegation cannot perform another
prepare/provider call.

Cancel uses the same per-job lock and durable compare-and-set. It expires and
consumes an unclaimed receipt, terminalizes the job with the existing
`failed_no_charge`/cancel reason and `charge_status="not_charged"`, and only then
allows normal terminal workspace policy. Status refresh reads the durable job
and renders it without claiming or mutating anything; it cannot invoke prepare,
the gate, ASR, translation, classifier, TTS, render, balance, spend, refund, or
delivery. Two-invocation tests require at most one mocked ASR and at most one
mocked translation total according to policy, with zero of both on resume.
Classifier, TTS, render, spend, and delivery run exactly once and only after a
valid exact confirmation. No DB schema or wallet primitive is added.

## Approved duration-bounded delivery timeout addendum

The existing generated-video Telegram delivery call defaults to 180 seconds
and is capped at 300 seconds. A validated long SubDub MP4 can therefore reach
the 90% validation stage and still fail while Telegram is receiving the file.

For SubDub generated-video delivery only, the read/write delivery timeout is
selected from the validated final MP4 duration (falling back to the expected
duration only when validation metadata omits it):

- shorter than 5 minutes: 5 minutes (300 seconds);
- 5 minutes through shorter than 10 minutes: 15 minutes (900 seconds);
- 10 minutes through shorter than 20 minutes: 25 minutes (1,500 seconds);
- 20 minutes or longer: 30 minutes (1,800 seconds).

Exactly 20 minutes belongs to the final 30-minute bucket. Connection and pool
setup remain capped at 30 seconds. Unknown or zero duration uses the bounded
5-minute bucket. Rendering, FFmpeg stage deadlines, provider calls, retry
count, delivery deduplication, size limits, charging order, and every
non-SubDub delivery path remain unchanged. The timeout is bounded; jobs are not
allowed to run forever.

## User flow

Both `dub_only` and `subtitle_plus_dub` retain every existing manual voice
choice and add one localized Auto choice. Canonical Vietnamese UI text is:

`👥 Tự nhận giọng (tối đa 16)`

Every other registered locale uses a native equivalent plus native explanatory
and fail-closed/manual-choice copy. Non-English locales do not fall back to
English, and non-Vietnamese locales do not fall back to Vietnamese on this
surface.

Selecting Auto first clears `voice_kind`, `voice_selection_mode`, and every
stale manual/provider voice field, then assigns
`voice_kind="auto_speaker_gender"` and `voice_selection_mode="auto_speaker"`.
Selecting any manual, saved, or custom voice first clears `voice_kind`, the Auto
flag/mode, speaker sidecar reference, speaker assignments, and per-cue voice
IDs plus any exact receipt/confirmation fields, then assigns the chosen
manual/saved/custom `voice_kind` and its current manual mode fields. This
reset-before-assign ordering is mandatory in both directions, so a stale
`auto_speaker_gender` value cannot survive a manual selection. Back, retry,
resume, and lane transitions preserve only the currently selected mode and a
matching bounded receipt when deliberately paused. Manual behavior and manual
pricing remain unchanged.

No classification, TTS call, live catalog lookup, or wallet action occurs
before the existing explicit confirmation edge. If any Auto prerequisite is
unavailable, the job returns to manual voice selection with localized copy.
When Task 7 introduces a second exact confirmation for a previously unknown or
different post-text-preparation count, that later confirmation also occurs
before acoustic classification, TTS, render, or any wallet mutation.

## Processing design

### 1. Speaker attribution and whole-job cap

The existing scoped Deepgram diarization contract remains: only confirmed Auto
jobs request call-scoped diarization, no global request parameters or provider
order are mutated, no second ASR call is made, and speaker metadata is joined by
stable cue ID plus exact timestamps.

The exact Auto dispatch must reach that contract through the explicit keyword
path: the Auto prepare wrapper invokes the injected bot-local prepare exactly
once with `require_auto_cast=True`; the bot-local prepare forwards
`require_auto_cast=bool(require_auto_cast)` to
`video_dubbing_prepare_subtitles`. Omission or `False` preserves the current
non-diarized default/manual behavior. State values alone are not a substitute
for this keyword and must not trigger a second prepare or ASR attempt.

Speaker labels are chunk-scoped (for example `chunk_03:speaker_1`). They are not
cross-chunk person identities. Auto accepts at most 16 distinct chunk-scoped
speaker labels across the whole job, regardless of how many ASR chunks exist.
The first 16 are ordered by first cue occurrence. Discovery of a 17th distinct
label fails closed with `AUTO_CAST_MANUAL_REQUIRED` before classification or
TTS and asks the user to choose a manual voice. The system does not merge labels,
guess identity, drop a speaker, or claim an exact unique-person count.

Missing, stale, or mismatched sidecars continue to return
`AUTO_CAST_UNAVAILABLE` before translation/TTS. Missing speaker metadata after a
confirmed ASR call never triggers a second provider call or fabricated mapping.

### 2. Bounded local acoustic classification

The classifier reads a temporary FFmpeg artifact in exactly 16 kHz, mono,
signed 16-bit little-endian (`s16le`) PCM. It uses bounded 0.5-second reads,
exactly 8,000 samples or 16,000 bytes per full read, and never loads the whole
artifact into memory.

Task 4 implements the classifier as pure, fixture-driven logic in
`services/subdub_speaker_cast.py` and creates the bounded classifier seam in
`services/subdub_blackboxes/auto_speaker.py`. The seam wraps the injected
confirmed-diarized `prepare_subtitles` dependency; it does not edit or bypass
the default/manual blackbox or `services/subtitle_dub_product_pipeline.py`.
Task 4 does not wire the bot dispatch yet, so the default runtime route remains
unchanged while the isolated Auto wrapper is proven. Task 4 ends with an
invocation-local preflight/classification result. It does not validate a voice
pool, assign or annotate a voice, install Auto resolve/synthesize wrappers or
their failure slot, accept/delegate to the lane runner, or expose the complete
runtime adapter. Its entry is `run_auto_speaker_preflight(...)`. Task 5 adds
`run_auto_speaker_blackbox(...)` and all later behavior.

The internal result contract is:

```text
speaker_id
voice_register = low | high | unknown
confidence = 0.0 .. 1.0
voiced_seconds
sample_count
reason
```

Pitch thresholds are inclusive at the classified edges: median fundamental
frequency `<= 155 Hz` is `low`, `>= 165 Hz` is `high`, and values strictly
between 155 Hz and 165 Hz are `unknown`. A `low` or `high` result is usable only
when confidence is `>= 0.75`; otherwise it is `unknown`.

Resource boundaries apply to the whole job:

- at most 16 distinct chunk-scoped speaker labels;
- at most 3.0 voiced seconds sampled per speaker;
- at most 48.0 sampled seconds across the job;
- at most 0.5 seconds/8,000 samples per PCM read;
- at most 1 MiB of transient working buffers.

The classifier has one exact whole-job wall timeout:
`CLASSIFIER_WALL_TIMEOUT_SECONDS = 30.0`. The caller computes one absolute
monotonic deadline at classifier entry and passes that same deadline through
every speaker/read operation. Reaching the deadline before or during any seek,
read, or analysis fails closed before TTS; the timeout is not reset per speaker
or per PCM window.

The classifier remains synchronous and fixture-testable, but the async Auto
wrapper runs each invocation behind its own `asyncio.to_thread` or equivalent
executor boundary. It never executes PCM seek/read or pitch analysis on the
Telegram event-loop thread. The wrapper computes the absolute 30.0-second
deadline before starting the worker and passes that same value into it; entering
a thread does not reset or extend the deadline. From the initial wait onward,
the wrapper must compute the remaining whole-job time and use
`await asyncio.wait_for(asyncio.shield(worker), remaining_seconds)`. It must
never directly await the Task in a way that lets cancellation mark that Task
cancelled while its OS thread continues running.

The synchronous implementation accepts a cooperative stop signal and checks
both that signal and `time.monotonic() >= deadline_monotonic` before and after
every seek/read and inside bounded short-frame YIN, full-rate refinement, FFT
competing-pitch, and aggregation loops. The FFT overlap gate requires a stable
competing pitch across at least two short frames. On
timeout, task cancellation, or wrapper failure, the wrapper signals stop and
awaits the still-live worker's cooperative termination under cancellation
shielding before it deletes the PCM artifact. The initial protected wait and
the cleanup wait are both required; adding `shield` only after a naked initial
await is insufficient. Cleanup never races an active reader and leaves no
orphan worker or PCM file. A worker that observes timeout/stop fails closed and
cannot publish a partial classification.

Ambiguous pitch, noise, music, overlap, insufficient voiced material, unstable
estimates, resource overflow, or classification timeout returns
`AUTO_CAST_MANUAL_REQUIRED`. Auto never guesses and never substitutes a female,
male, default, or dominant-register fallback.

PCM stays in the existing temporary job workspace. The Auto wrapper is its sole
cleanup owner and removes it only after the cooperative classifier worker has
terminated on success, failure, timeout, or cancellation. Raw PCM, embeddings,
YIN/FFT working arrays, and sample values are never persisted in job state,
sidecars, checkpoints, logs, diagnostics, or public output. Only bounded scalar
classification results may be retained.

Responsiveness tests keep an event-loop heartbeat advancing while a controlled
classifier worker runs. Cancellation tests interrupt the awaiting handler,
prove the stop signal is observed, wait for worker exit, then prove PCM cleanup
and zero classifier/TTS/render/charge continuation.

### 3. Provider-neutral stable voice assignment

Task 5 consumes Task 4's confident `low`/`high` results. It does not name a
provider in the assignment interface. Before TTS, the existing configured voice
inventory is normalized into validated `low` and `high` pools. Validation is
local and makes no live catalog call during a job.

Assignment rules are deterministic and stable across retry/resume:

- sort chunk-scoped speaker labels by first cue occurrence;
- choose from the matching validated register pool using a stable hash of the
  job/canonical sidecar identity and speaker label;
- same-register speakers receive different validated voice IDs while that pool
  still has unused IDs;
- once a pool cannot satisfy the distinct assignment contract, Auto fails
  closed with `AUTO_CAST_MANUAL_REQUIRED` before any TTS call;
- an `unknown`, low-confidence, missing, invalid, or duplicate-only pool also
  requires manual selection.

The mapping contains only stable speaker label, `low|high`, and a validated
private voice reference. Public output masks voice IDs. The implementation must
not change provider order or ENV, must not query a live voice catalog during a
job, and must never state that all configured/provider voices are currently
live.

After assignment, the Auto prepare wrapper identity-joins speaker and cast data
by the tuple of canonical `cue_id` plus exact `start` and `end` timestamps. It
must require and annotate both `prepared["source_segments"]` and
`prepared["output_segments"]`; it must not join by position, text, speaker
order, or approximate time. A missing list, missing cue ID, missing timestamp,
duplicate identity, absent assignment, or any identity/timestamp mismatch fails
closed before TTS. Each list retains its own existing cue order and exact
timestamps after annotation.

This dual annotation is required because the protected
`resolve_subdub_dub_audio_policy` selects `source_segments` for the `dub_only`
source path and selects translated `output_segments` for the
`subtitle_plus_dub` translated path. The policy and shared pipeline remain
byte-identical; the Auto wrapper guarantees that whichever list they select has
a validated private `tts_voice_id` on every selected cue.

### 4. Per-cue synthesis

Every Auto cue in both prepared segment lists receives the resolved private
voice ID for its stable chunk-scoped speaker label during the wrapped prepare
step. Before any TTS, the Auto `resolve_voice_id` wrapper validates the exact
list selected by `resolve_subdub_dub_audio_policy` and returns its first cue's
validated private ID only to satisfy the shared pipeline's existing nonempty
scalar guard. That compatibility value is a real assigned ID, not a fabricated
default and not a claim that one voice applies to the job.

The Auto `synthesize_segments` wrapper receives the exact list selected by
`resolve_subdub_dub_audio_policy` and revalidates that full list, so a
missing/invalid `tts_voice_id` fails with `AUTO_CAST_MANUAL_REQUIRED` before any
TTS call. It then calls the already-injected scalar synthesizer sequentially
with one cue at a time and `voice_id=cue["tts_voice_id"]`, accumulating the
returned chunks in original cue order and preserving their existing timing.
Provider aggregation is deterministic: preserve the ordered cue chunks; return
the one nonempty internal provider label when all nonempty labels are equal,
return the internal generic label `mixed` when distinct nonempty labels occur,
and return an empty label when none is present. Provider labels and the `mixed`
marker remain internal and never appear in public copy.
No parallel or combined provider schema is introduced. Cue count, order,
timestamps, translation, timeline construction, audio QC, muxing, artifact
validation, delivery, and charging order remain unchanged.

All non-Auto states continue through the current single scalar call and never
enter this wrapper. No manual cue, default state, or partially matching Auto
state consumes a per-cue assignment.

Provider-specific multi-speaker endpoints and undocumented combined-audio
schemas remain out of scope. No provider endpoint or provider order changes.

## Separate pricing and confirmation contract (Task 7, last)

Pricing is implemented only after Tasks 4–6 pass and after two prerequisites
are explicitly proven by tests: a language-safe billable-word counter and an
estimate-to-exact-confirmation gate that does not invent a wallet primitive.

The pricing caller must use
`auto_speaker.is_auto_speaker_state(state)` for the quote, confirmation gate,
read-only balance guard, invoice, selected spend amount, and final one-shot
charge. The Auto formula is unreachable for partial/malformed pairs. Those
states keep the existing manual/default price and charge path, even if one Auto
key or stale Auto receipt field is present.

The canonical Auto component is `0.5 Xu` per billable word. Manual modes retain
their existing prices. For Auto only, apply one volume discount to the Auto
component: 10% for at least 1,000 words, 20% for at least 10,000 words, and 0%
below 1,000 words. The 10,000-word tier replaces, rather than stacks with, the
10% tier.

Calculate with exact decimal arithmetic, then ceil the discounted Auto component
to whole Xu. For `subtitle_plus_dub`, add that ceiled Auto component to the
existing subtitle component; do not discount or round the combined total as a
single component. The unrelated 100-unit discount rule must not be reused.

When the final policy-selected TTS cue text is already available, the first
quote uses its exact language-safe count and can be confirmed once. This may be
source cues or a valid cached translation, depending on
`resolve_subdub_dub_audio_policy`; a source subtitle does not make a missing
selected translation exact. When the selected text is not exact at quote time,
the first confirmation authorizes only text preparation and the displayed
formula estimate: ASR at most once if source cues are not validly cached, plus
the existing translation path at most once only if policy selects translated
TTS text and no valid translation cache exists. After text preparation and
before classifier, lane delegation, TTS, render, or wallet mutation, the system
counts exactly the final `tts_segments` selected by that policy, recomputes the
exact Auto component and exact total, and the injected `post_prepare_gate`
performs a read-only guard against the user's current Xu balance. It returns
`AUTO_EXACT_CONFIRMATION_REQUIRED` and the durable bounded receipt whenever the
exact selected-text count was unknown at the quote or differs from it. Resume
must claim the durable receipt and matching workspace cache before work
continues, with zero second ASR or translation calls.

Cancellation at the second confirmation or an insufficient exact balance stops
the job before TTS/render and performs no wallet mutation; authorized ASR and,
only when selected translated text required it, translation provider cost may
already have occurred. `dub_only` uses the exact Auto component alone.
`subtitle_plus_dub` uses the existing subtitle component plus the exact Auto
component. The existing subtitle component, rate, counter, discount, and
rounding remain unchanged.

After exact confirmation, the existing SubDub path renders and validates the
artifact, then calls `spend_fixed_credit_info` exactly once for the actual total
before delivery. It preserves the existing delivery attempt followed by
`refund_charged_credit` on delivery exception, empty delivery, or partial
delivery. There is no pre-render debit, new wallet primitive, or charge-order
change. If the one-shot charge reports insufficient balance after render, the
existing behavior remains: no output is sent and no Xu is deducted.

Counter semantics must be deterministic for whitespace-delimited languages and
languages without spaces, with fixtures for Vietnamese, English, Chinese,
Japanese, Thai, and mixed punctuation. If those semantics, the exact
confirmation gate, or the existing one-shot charge order cannot be proven,
Task 7 remains blocked and existing manual pricing remains untouched.

## Failure policy

- Manual modes are behaviorally and financially identical to current production.
- The Auto wrapper catches `AutoCastUnavailable` and
  `AutoCastManualRequired` from its owned preflight and from Auto dependency
  wrappers during lane delegation, then returns one canonical structured
  result with `status="AUTO_CAST_MANUAL_REQUIRED"`, the safe internal reason,
  `lane_mode`, and `public_copy_key="voice_auto_manual_required"`. It exposes no
  provider, voice ID, receipt value, endpoint, or debug array.
- The bot consumes that structured result, clears bounded Auto receipts,
  classifications, casts, and per-cue assignments, and re-renders the native
  voice screen for the same `dub_only` or `subtitle_plus_dub` lane. It does not
  route the exception through a generic protected-pipeline failure and does not
  jump to another lane or the main menu.
- `AUTO_EXACT_CONFIRMATION_REQUIRED` is a resumable control result. The outer
  runner maps it to durable nonterminal
  `awaiting_auto_exact_confirmation` before generic failure normalization and
  preserves its workspace plus bounded receipt; it is never rendered as manual
  failure. User cancel atomically expires/consumes the receipt and terminalizes
  no-charge. Exact insufficient balance stops before classifier/TTS/render with
  the existing safe balance response and zero wallet mutation.
- External `asyncio.CancelledError` signals and awaits classifier cleanup, then
  re-raises. It is not converted to a manual-choice result. Unrelated
  provider/TTS/render/mux/charge/delivery failures retain their current handler
  and refund behavior.
- The 17th chunk-scoped label, `unknown`, confidence below 0.75, noise,
  insufficient material, timeout, invalid voice pool, pool exhaustion, or a
  missing cue assignment all require manual selection; Auto never guesses.
- Provider, TTS, mux, and delivery failures keep existing no-fake-success and
  no-charge/refund behavior.
- Status refresh is read-only over the durable job and cannot claim/resume a
  receipt or rerun prepare, ASR, translation, classification, catalog lookup,
  TTS, quote confirmation, balance guard, rendering, delivery, or charging.
- No raw PCM, embeddings, provider IDs, model names, endpoints, confidence
  internals, or debug arrays appear in public copy.

## Verification

All automated checks use fixtures/mocks and make zero real provider calls.

1. Existing Task 1–3 sidecar, cache/checkpoint, scoped diarization, and timeout
   focused tests remain green.
2. Whole-job label tests accept 16 chunk-scoped labels and fail the 17th before
   classification/TTS with `AUTO_CAST_MANUAL_REQUIRED`.
3. Synthetic `s16le` fixtures prove `<=155 Hz` low, `>=165 Hz` high, the open
   interval between them unknown, and confidence `>=0.75` for usable results.
4. Noise, overlap, silence, insufficient material, instability, and the exact
   30.0-second classifier wall timeout all require manual selection without a
   female/default fallback. Tests prove one absolute deadline crosses the
   invocation-local thread boundary and is checked before/after I/O and during
   analysis loops.
5. Event-loop heartbeat and cancellation tests prove classifier work never
   blocks Telegram, the worker Task is protected from cancellation from its
   initial await, cooperative stop terminates the OS-thread work before PCM
   deletion, and no worker or raw artifact is orphaned. A control test proves
   adding `shield` only after a naked initial await is rejected.
6. Tests prove 3 seconds/speaker, 48 seconds/job, 8,000 samples/read, and 1 MiB
   work-buffer limits; no raw PCM or embeddings are persisted.
7. Task-4 boundary tests prove the isolated seam stops after gate/classification:
   no pool assignment, identity annotation, resolve/synthesize wrapper or
   failure slot, and no lane-runner call exists until Task 5.
8. Stable assignment is deterministic across retry/resume and gives
   same-register speakers different IDs while the validated pool allows.
9. Invalid or insufficient pools fail before TTS; no live catalog call,
   provider-order mutation, ENV mutation, or universal-live-voice claim occurs.
10. The central predicate matrix proves only both exact keys enable Auto across
   dispatch, quote, confirmation, read-only balance guard, invoice, selected
   spend amount, and final charge. Partial/malformed pairs preserve exact
   manual/default behavior and pricing.
11. Prepare-seam fixtures capture exactly `[True]` for each exact Auto handler
    invocation and exactly `[False]` for default/manual and every partial or
    malformed pair. The lane runner receives an already-prepared closure and
    cannot cause a second prepare, ASR, or translation call.
12. Text-preparation authorization fixtures cover source-selected and
    translated-selected policy branches: ASR runs at most once only without a
    valid source cache; the existing translation path runs at most once only
    when translated TTS text is selected without a valid translation cache;
    exact existing selected text needs one confirmation. Exact count uses only
    the final policy-selected TTS cue text, while classifier/TTS/render/wallet
    counters remain zero until any required second confirmation.
13. Two-handler pause/resume fixtures prove
    `AUTO_EXACT_CONFIRMATION_REQUIRED` returns before classifier/lane runner,
    the outer runner persists `awaiting_auto_exact_confirmation` through the
    existing snapshot/engine-job store before generic failure handling, keeps
    the workspace active, and resume uses matching cache with zero new ASR and
    zero new translation.
14. Concurrent duplicate callbacks prove one dedicated per-job lock and one
    durable compare-and-set claim. Restart rehydrates the same job/workspace;
    stale, missing, mismatched, expired, duplicate, cancel, insufficient-balance,
    and read-only status cases perform no second provider/classifier/TTS/render/
    spend/refund/delivery work. Cancel expires/consumes the receipt and
    terminalizes no-charge.
15. Auto-wrapper fixtures prove identity-join by canonical `cue_id` plus exact
    timestamps into both `source_segments` and `output_segments`, fail closed on
    either missing list or missing/mismatched identity, and prove complete
    assigned cues on both the `dub_only` source policy path and
    `subtitle_plus_dub` translated-output path.
16. Auto-wrapper fixtures prove the real first-assigned compatibility scalar,
    full-list validation before TTS, sequential one-cue scalar calls, exact cue
    order/timing, and deterministic provider aggregation: same, `mixed`, or
    empty. No provider label appears in public copy.
17. Auto state/button exists in both `dub_only` and `subtitle_plus_dub`, opposing
    state clears in both directions, and all 17 locales contain native copy.
18. Preflight and delegated Auto exceptions map to the canonical structured
    manual-required result; both lanes clear bounded Auto computed fields and
    re-render their own native voice screen before any TTS continuation.
19. Pricing tests preserve 0.5 Xu/word Auto-only, 0/10/20% thresholds, component
    ceiling before addition, unchanged manual pricing, and no 100-unit rule.
20. Language-safe estimate and actual counters share semantics. Exact-upfront
    policy-selected text needs one confirmation; unknown/different
    post-preparation actuals pause after a read-only balance guard and resume
    from a claimed durable receipt before classifier/TTS. Success uses one post-render
    `spend_fixed_credit_info` actual charge and retains the existing
    delivery-failure refund order.
21. Protected blob/hash checks keep the five stable shared-engine files at
    their recorded PR613-compatible blobs, and focused comparators prove
    non-Auto states keep the original runner/dependency identities.
22. Protected diffs show no provider adapter/order, wallet primitive, PayOS,
    DB, ENV, credential, unrelated product, or deployment change, and
    `git diff --check` passes.

Under the current explicit Owner verification gate, only the named focused
SubDub tests, changed-module compile/AST checks, protected blob checks, and
diff/scope checks are authorized. Full `pytest -q` and unrelated
`python -m py_compile local_worker.py` are intentionally `NOT_RUN`. Reports must
not claim full-repository regression PASS from the focused evidence.

## Provider references retained from Tasks 1–3

- Key4U Speech Synthesis: `https://docs.key4u.vn/api-41690934`
- Key4U Speech Synthesis Copy: `https://docs.key4u.vn/api-41690935`
- ShopAIKey TTS guide: `https://shopaikey.com/docs/tts`
- ShopAIKey OpenAPI TTS schema: `https://shopaikey.com/api-docs#tag/tts`
- Deepgram speaker diarization: `https://developers.deepgram.com/docs/diarization`
- Deepgram utterances: `https://developers.deepgram.com/docs/utterances`
- Deepgram pre-recorded API: `https://developers.deepgram.com/reference/speech-to-text/listen-pre-recorded`
- Google Gemini TTS guide: `https://ai.google.dev/gemini-api/docs/speech-generation`

No deploy, VPS update, paid provider smoke, Telegram live action, ENV change,
pricing implementation, or wallet mutation is authorized by this document-only
canonicalization gate.
