# SubDub Per-Speaker Automatic Voice Casting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give confirmed SubDub dubbing jobs a fail-closed Auto mode for at most 16 chunk-scoped speaker labels, using bounded acoustic-register classification, deterministic validated per-speaker voices, native UI in both dubbing lanes, and a separately priced 0.5-Xu-per-word Auto component charged through the existing one-shot SubDub path.

**Architecture:** Tasks 1–3 already established call-scoped diarization, canonical cue/sidecar identity, and bounded SubDub delivery. They are complete historical records and are not execution steps; implementation begins at Task 4. Auto speaker recognition is a separate adapter at `services/subdub_blackboxes/auto_speaker.py`, never a replacement or copy of the stable shared engine. Its central `is_auto_speaker_state(state)` predicate requires both exact keys and governs dispatch plus every Auto quote/confirmation/balance/invoice/spend/charge decision; partial or malformed pairs remain manual/default. `run_auto_speaker_blackbox` owns Auto preflight: it calls the injected bot-local prepare once with `require_auto_cast=True`, awaits an injected async `post_prepare_gate(prepared, state)`, and can return `AUTO_EXACT_CONFIRMATION_REQUIRED` before classifier or lane delegation. Task 4 stops strictly after the isolated gate/classifier result: it does not assign or annotate voices, install resolve/synthesize wrappers or their failure slot, or delegate to the lane runner. Task 5 adds those pieces; only then does a continue decision identity-join assignments by canonical `cue_id` plus exact timestamps into both `source_segments` and `output_segments` and call the same `subdub_blackboxes.run_subdub_lane_blackbox(..., runner=subtitle_dub_product_pipeline.run_subdub_pipeline, ...)` with an already-prepared closure plus wrapped resolve/synthesize dependencies. Every other state forwards `require_auto_cast=False` through the unchanged default/manual call. Task 6 wires exact-pair dispatch, failure mapping, state/UI/native copy. Task 7, still last, supplies durable text-preparation/exact-confirmation resume and the existing one-shot actual charge; Task 8 verifies the protected surface. Manual voice and scalar TTS remain the byte-stable compatibility path.

The first authorization in Task 7 is a text-preparation authorization, not an
ASR-only authorization. It permits ASR at most once when source cues are not
validly cached and the existing translation path at most once only when the
protected policy selects translated TTS text and no valid translation cache
exists. Exact count is over the final cue text in
`resolve_subdub_dub_audio_policy(...)["tts_segments"]`. Exact existing selected
text needs only the existing confirmation. Otherwise the runner persists the
nonterminal `awaiting_auto_exact_confirmation` receipt through the existing
SubDub snapshot/engine-job store, keeps the workspace, and permits zero
classifier/TTS/render/wallet work until the second exact confirmation.

**Tech Stack:** Python 3, asyncio, NumPy, FFmpeg/FFprobe, python-telegram-bot, pytest.

---

## File map

- Modify `services/subdub_speaker_cast.py`: add the 16-label cap, bounded PCM register estimation, provider-neutral voice-pool validation, and stable assignment to the existing sidecar identity/validation implementation.
- Create `services/subdub_blackboxes/auto_speaker.py`: define the central exact
  predicate, own Auto preflight and the async `post_prepare_gate`, wrap only the
  current injected `prepare_subtitles`, `resolve_voice_id`, and
  `synthesize_segments` dependencies, then delegate to the existing lane
  blackbox and shared pipeline.
- Modify `bot.py`: add bounded PCM-extraction support, the additive
  `_prepare_subtitles_for_blackbox(..., *, require_auto_cast=False)` seam,
  exact-pair Auto dispatch, Auto state/reset/UI in both dubbing lanes, bounded
  durable exact-confirmation receipt/CAS resume integration through the existing
  pipeline-job snapshot store, and canonical copy consumption
  while retaining the current default/manual call and one-shot charge order.
- Modify `services/pricing_guide_content.py`: add native Auto and Auto-pricing copy for every existing locale.
- Create `services/subdub_auto_word_pricing.py`: language-safe billable-word counting, exact Auto-component pricing, and pure estimate/actual confirmation inputs.
- Create `tests/test_p0_subdub_per_speaker_auto_gender_cast.py`: focused unit/integration tests with no real provider calls.
- Modify `tests/test_p0_i18n_video_subdub_native_contract.py`: 17-locale Auto-copy contract.

The following shared-engine files are protected and must remain byte-identical:

- `services/subdub_blackboxes/__init__.py`
- `services/subdub_blackboxes/base.py`
- `services/subdub_blackboxes/dub_only.py`
- `services/subdub_blackboxes/subtitle_dub.py`
- `services/subtitle_dub_product_pipeline.py`

Also protected are payment, wallet, PayOS, database/migrations, ENV/config credentials, Video Edit, Logo/Watermark, and provider adapter modules outside the existing `bot.py` seams. No live voice-catalog lookup is allowed.

### Stable PR613 engine evidence

PR613 implementation commit `00aff00871c61b4caefc2e165c1216cdbb2d7d63`
was merged as `61f17108b9482fa1f6fef0e1e12bf8d7f647bfb4`. At planning
baseline `2e0453058c54e4169e80ffd356079e5960ee4674`, all five protected
paths above are identical to both commits. Record and enforce these blobs:

```text
services/subdub_blackboxes/__init__.py       22f06a3dac77764ca702a9572d54220df4547673
services/subdub_blackboxes/base.py           6a87de96d0820a363ce8447be7fae51ec95bc679
services/subdub_blackboxes/dub_only.py       12f641b243a950e5a250105a30adffb27082233e
services/subdub_blackboxes/subtitle_dub.py   5531995d251dc1857d0f2a86ccf6ca75ed27b0cc
services/subtitle_dub_product_pipeline.py    24f8b45b8944b674e4d79b649e084916959bb2fe
```

The reusable chain remains:

```text
bot core -> existing lane blackbox
-> subtitle_dub_product_pipeline.run_subdub_pipeline
-> injected prepare/resolve/synthesize
-> existing timeline/QC/mux/delivery/charge
```

## Execution start

Tasks 1–3 below are **COMPLETE / HISTORICAL**. Their checked steps document
already-landed branch history and must not be executed or recommitted. Begin all
new implementation at Task 4.

This canonical architecture update is documentation-only. It authorizes no
Task 4–8 runtime edit, provider/catalog call, wallet mutation, ENV change,
deployment, or Telegram live action. The pricing values and confirmation/
charging contract in Task 7 are unchanged by this update.

### Task 1: Bound SubDub final-video delivery by validated duration — COMPLETE / HISTORICAL

**Status:** COMPLETE / HISTORICAL. Non-executable record; begin new work at Task 4.

**Files:**
- Modify: `tests/test_p0_subdub_live25_canonical_mp4_smoke.py`
- Modify: `bot.py:2232-2240`
- Modify: `bot.py:233961-234028`
- Modify: `bot.py:235904-236035`

- [x] **Step 1: Keep failing boundary and transport regression tests**

The pure boundary test requires:

```python
@pytest.mark.parametrize(("duration", "expected"), [
    (0, 5 * 60),
    (5 * 60 - 0.001, 5 * 60),
    (5 * 60, 15 * 60),
    (10 * 60 - 0.001, 15 * 60),
    (10 * 60, 25 * 60),
    (20 * 60 - 0.001, 25 * 60),
    (20 * 60, 30 * 60),
])
def test_subdub_delivery_timeout_uses_duration_buckets(duration, expected):
    assert bot.subdub_delivery_timeout_seconds_for_duration(duration) == expected
```

The integration test calls `send_public_subtitle_dub_final_outputs()` with a
validated 16-minute fixture and replaces the transport with a capture function:

```python
assert captured[0]["delivery_timeout_seconds"] == 25 * 60
assert bot.SUBDUB_LONG_VIDEO_DELIVERY_TIMEOUT_SECONDS == 30 * 60
```

A direct transport test calls `send_generated_video_bytes_for_delivery()` with
the 25-minute override and fake Telegram methods, then requires exact
`read_timeout=1500`, `write_timeout=1500`, `connect_timeout=30`, and
`pool_timeout=30`. The existing generic test requires its old configured
default and proves no 30-minute override leaks to other callers.

- [x] **Step 2: Run the one RED test**

Run:

```powershell
python -m pytest -q tests/test_p0_subdub_live25_canonical_mp4_smoke.py::test_subdub_final_video_delivery_uses_owner_approved_30_minute_timeout
```

Expected: FAIL because the duration helper and adaptive caller do not exist.

- [x] **Step 3: Add duration buckets without changing generic delivery**

Add beside the existing SubDub delivery constants:

```python
SUBDUB_LONG_VIDEO_DELIVERY_TIMEOUT_SECONDS = 30 * 60

def subdub_delivery_timeout_seconds_for_duration(duration_seconds: float) -> int:
    duration = max(0.0, float(duration_seconds or 0.0))
    if duration < 5 * 60:
        return 5 * 60
    if duration < 10 * 60:
        return 15 * 60
    if duration < 20 * 60:
        return 25 * 60
    return SUBDUB_LONG_VIDEO_DELIVERY_TIMEOUT_SECONDS
```

Extend the generic helper compatibly:

```python
async def send_generated_video_bytes_for_delivery(
    message,
    video_bytes: bytes,
    *,
    filename: str,
    caption: str,
    lang: str = "vi",
    preview_max_mb: int | None = None,
    document_max_mb: int | None = None,
    generated_max_mb: int | None = None,
    delivery_timeout_seconds: int | float | None = None,
) -> dict:
    requested_timeout = (
        SUBDUB_TELEGRAM_DELIVERY_TIMEOUT_SECONDS
        if delivery_timeout_seconds is None
        else delivery_timeout_seconds
    )
    delivery_timeout = float(max(60, min(30 * 60, int(requested_timeout))))
    connection_timeout = min(30.0, delivery_timeout)
```

After final MP4 validation, select the actual validated duration first and the
expected duration only as fallback. Pass the selected override only from
`_deliver_video_payload()` inside `send_public_subtitle_dub_final_outputs()`:

```python
delivery_duration_seconds = float(
    validation.get("actual_duration")
    or validation.get("duration")
    or expected_duration_seconds
    or 0.0
)
delivery_timeout_seconds=subdub_delivery_timeout_seconds_for_duration(
    delivery_duration_seconds
),
```

- [x] **Step 4: Run GREEN and the existing delivery selector**

Run:

```powershell
python -m pytest -q tests/test_p0_subdub_live25_canonical_mp4_smoke.py -k "generated_video_delivery or duration_buckets or adaptive_timeout"
```

Expected: boundary, caller, direct transport, and generic comparator tests PASS;
16 minutes gives read/write 1500, connect/pool remain 30, and the generic
default remains unchanged.

- [x] **Step 5: Commit the isolated timeout fix**

```powershell
git add -- bot.py tests/test_p0_subdub_live25_canonical_mp4_smoke.py
git commit -m "fix(subdub): allow 30 minute long-video delivery"
```

### Task 2: Add scoped Deepgram diarization and preserve word speakers — COMPLETE / HISTORICAL

**Status:** COMPLETE / HISTORICAL. Non-executable record; begin new work at Task 4.

**Files:**
- Create: `tests/test_p0_subdub_per_speaker_auto_gender_cast.py`
- Modify: `bot.py:39990-40330`
- Modify: `bot.py:64100-64650`
- Modify: `bot.py:237217-237690`

- [x] **Step 1: Write RED fixtures for scoped request and response parsing**

Add fixtures containing two words with a speaker change:

```python
DEEPGRAM_TWO_SPEAKERS = {
    "results": {"channels": [{"alternatives": [{"words": [
        {"word": "hello", "start": 0.0, "end": 0.4,
         "speaker": 0, "speaker_confidence": 0.91},
        {"word": "there", "start": 0.5, "end": 0.9,
         "speaker": 1, "speaker_confidence": 0.88},
    ]}]}]}
}

def test_deepgram_speaker_fields_survive_and_split_on_change():
    words = bot.deepgram_word_items(DEEPGRAM_TWO_SPEAKERS)
    segments = bot.deepgram_segments_from_response(DEEPGRAM_TWO_SPEAKERS)
    assert words[0]["speaker"] == 0
    assert words[0]["speaker_confidence"] == pytest.approx(0.91)
    assert [item["speaker"] for item in segments] == [0, 1]

def test_auto_diarization_request_is_call_scoped(monkeypatch):
    before = dict(bot.AgentDeepgram.REQUEST_PARAMS)
    params = bot.subdub_deepgram_request_params(require_diarization=True)
    assert params["diarize_model"] == "latest"
    assert params["utterances"] == "true"
    assert "diarize" not in params
    assert bot.AgentDeepgram.REQUEST_PARAMS == before
```

- [x] **Step 2: Run RED**

Run the two node IDs. Expected: missing speaker fields/helper.

- [x] **Step 3: Implement immutable request options and speaker parsing**

Use a copied request dict:

```python
def subdub_deepgram_request_params(*, require_diarization: bool = False) -> dict[str, str]:
    params = {str(key): str(value) for key, value in AgentDeepgram.REQUEST_PARAMS.items()}
    if require_diarization:
        params.pop("diarize", None)
        params["diarize_model"] = "latest"
        params["utterances"] = "true"
    return params
```

`AgentDeepgram.diagnostic()`, `deepgram_asr_adapter()`, `asr_transcribe_audio()`, `transcribe_media_to_segments()`, and `_transcribe_long_chunk()` receive an optional `require_diarization=False` keyword. In the final architecture, only a confirmed call guarded by `auto_speaker.is_auto_speaker_state(state)` sets it true; either key alone remains false. When true, force the configured Deepgram route and return `AUTO_CAST_UNAVAILABLE` if no Deepgram route or no word has a valid `speaker`.

Extend each parsed word with:

```python
"speaker": int(raw["speaker"]) if raw.get("speaker") is not None else None,
"speaker_confidence": max(0.0, min(1.0, float(raw.get("speaker_confidence") or 0.0))),
```

Split the segment builder when `speaker` changes and copy both fields to each segment.

- [x] **Step 4: Run GREEN plus existing adapter/order tests**

Run the new two tests and the exact relevant tests in:

```powershell
python -m pytest -q tests/test_p0_real_engine_output_adapters.py tests/test_p0_17b3_asr_smoke_routing_fix.py -k "deepgram or provider_order"
```

- [x] **Step 5: Commit**

```powershell
git add -- bot.py tests/test_p0_subdub_per_speaker_auto_gender_cast.py
git commit -m "feat(subdub): preserve scoped speaker diarization"
```

### Task 3: Preserve canonical speaker metadata and sidecar identity — COMPLETE / HISTORICAL

**Status:** COMPLETE / HISTORICAL at the current branch history. Preserve this task and its tests as the canonical non-executable Task 3 record; begin new implementation at Task 4.

**Files:**
- Create: `services/subdub_speaker_cast.py`
- Modify: `services/subdub_long_media.py:306-720`
- Modify: `bot.py:225243-225330`
- Modify: `bot.py:236998-237210`
- Modify: `bot.py:238921-239165`
- Test: `tests/test_p0_subdub_per_speaker_auto_gender_cast.py`

- [x] **Step 1: Write RED sidecar/checkpoint/cache tests**

Tests require stable chunk-scoped speaker IDs, cue IDs, hashes, and exact timeline matching:

```python
def test_sidecar_requires_media_subtitle_and_timeline_identity():
    cues = [{"cue_id": "cue-1", "start": 0.0, "end": 1.0,
             "speaker_id": "chunk_00:speaker_0", "speaker_confidence": 0.9}]
    sidecar = speaker_cast.build_sidecar(cues, media_sha256="a" * 64,
                                         subtitle_sha256="b" * 64)
    assert speaker_cast.sidecar_matches(
        sidecar, cues, media_sha256="a" * 64, subtitle_sha256="b" * 64
    )
    assert not speaker_cast.sidecar_matches(
        sidecar, [{**cues[0], "end": 1.1}],
        media_sha256="a" * 64, subtitle_sha256="b" * 64
    )

def test_cached_srt_without_matching_sidecar_raises_before_paid_work():
    cues = [{"cue_id": "cue-1", "start": 0.0, "end": 1.0}]
    with pytest.raises(speaker_cast.AutoCastUnavailable):
        speaker_cast.require_matching_sidecar(
            {}, cues, media_sha256="a" * 64, subtitle_sha256="b" * 64
        )
```

The integration version monkeypatches ASR, translation, and TTS with counters,
calls `video_dubbing_prepare_subtitles()` in Auto mode with the same invalid
sidecar, and asserts all three counters remain zero.

- [x] **Step 2: Run RED**

Expected: module/functions absent and cache guard absent.

- [x] **Step 3: Implement the pure sidecar contract**

Create `services/subdub_speaker_cast.py` with these public functions:

```python
def normalized_speaker_key(chunk_index: int, speaker: int) -> str:
    return f"chunk_{max(0, int(chunk_index)):02d}:speaker_{max(0, int(speaker))}"

def cue_timeline_signature(cues: list[dict]) -> str:
    rows = [
        f"{item.get('cue_id')}:{round(float(item.get('start') or 0) * 1000)}:"
        f"{round(float(item.get('end') or 0) * 1000)}"
        for item in cues
    ]
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()

def build_sidecar(cues: list[dict], *, media_sha256: str, subtitle_sha256: str) -> dict:
    entries = [{
        "cue_id": str(item.get("cue_id") or ""),
        "start_ms": round(float(item.get("start") or 0) * 1000),
        "end_ms": round(float(item.get("end") or 0) * 1000),
        "speaker_id": str(item.get("speaker_id") or ""),
        "speaker_confidence": max(0.0, min(1.0, float(item.get("speaker_confidence") or 0))),
    } for item in cues]
    return {
        "version": 1,
        "media_sha256": str(media_sha256),
        "subtitle_sha256": str(subtitle_sha256),
        "timeline_signature": cue_timeline_signature(cues),
        "cues": entries,
    }
```

`sidecar_matches()` validates version, both hashes, cue count, and timeline signature. `join_sidecar()` joins only by stable `cue_id` and validates matching timestamps before copying `speaker_id` and `speaker_confidence`.

Add the fail-closed wrapper:

```python
class AutoCastUnavailable(RuntimeError):
    pass

def require_matching_sidecar(
    sidecar: dict,
    cues: list[dict],
    *,
    media_sha256: str,
    subtitle_sha256: str,
) -> list[dict]:
    if not sidecar_matches(
        sidecar,
        cues,
        media_sha256=media_sha256,
        subtitle_sha256=subtitle_sha256,
    ):
        raise AutoCastUnavailable("AUTO_CAST_UNAVAILABLE")
    return join_sidecar(sidecar, cues)
```

Use `services/subdub_canonical_cues.canonicalize_segments()` to establish cue IDs. Preserve `cue_id`, `speaker`, `speaker_confidence`, `speaker_id`, `chunk_index`, `voice_register`, and `tts_voice_id` in long-media offsets/checkpoints, QC, retiming, and translation outputs.

Persist the bounded sidecar as JSON inside the existing job workspace. Store only its path/hash in job state. For existing/uploaded/embedded/cached SRT, missing or mismatched identity raises `RuntimeError("AUTO_CAST_UNAVAILABLE")` before translation/TTS; manual mode follows current behavior.

- [x] **Step 4: Run GREEN and long-media/canonical-cue selectors**

Run the new tests and focused selectors from:

```powershell
python -m pytest -q tests/test_p0_subdub_longmedia32_duration_size_status_report.py tests/test_p0_subdub_long_media_no_speech_recovery.py tests/test_p0_subdub_live5_subtitle_combo_canonical_cue_restore.py -k "checkpoint or timing or cue"
```

- [x] **Step 5: Commit**

```powershell
git add -- services/subdub_speaker_cast.py services/subdub_long_media.py bot.py tests/test_p0_subdub_per_speaker_auto_gender_cast.py
git commit -m "feat(subdub): retain speaker cue sidecars"
```

### Task 4: Add the pure classifier and isolated Auto classifier seam

**Files:**
- Modify: `services/subdub_speaker_cast.py`
- Create: `services/subdub_blackboxes/auto_speaker.py`
- Test: `tests/test_p0_subdub_per_speaker_auto_gender_cast.py`

- [ ] **Step 1: Write RED synthetic-PCM tests**

Start with a table-driven pure predicate test for
`auto_speaker.is_auto_speaker_state(state)`. Only
`voice_kind="auto_speaker_gender"` together with
`voice_selection_mode="auto_speaker"` returns true. Empty/default,
manual/saved/custom, either key alone, stale receipt fields, and every malformed
cross-pair return false. Later Tasks 6–7 must import this helper rather than
restate the expression.

Add tests that generate 16 kHz mono `s16le` fixtures for 120 Hz, 155 Hz,
170 Hz, 185 Hz, 220 Hz, noise, overlap, and silence. Require
`low, low, unknown, high, high` for the tones; noisy, overlapping, silent,
insufficient, unstable, and timed-out inputs raise
`AutoCastManualRequired("AUTO_CAST_MANUAL_REQUIRED")`.

Add whole-job cap tests with canonical labels `chunk_00:speaker_0` through
`chunk_15:speaker_0`, then prove `chunk_16:speaker_0` is rejected before the
PCM reader is called. Assert exactly 3.0 voiced seconds/speaker, 48.0 sampled
seconds/job, 8,000 samples/read, 1 MiB transient buffers, and one exact
30.0-second classifier wall deadline. Capture the caller's monotonic start and
the `deadline_monotonic` passed into `classify_speaker_registers()`; require
`deadline_monotonic - start == pytest.approx(30.0)`. Advance the fake clock to
the boundary in a later speaker/read and prove the whole call fails closed
before TTS rather than receiving a fresh per-speaker timeout. Assert no result,
sidecar, checkpoint, or log contains raw PCM or embeddings.

Add async responsiveness and cancellation tests around the wrapper. A heartbeat
coroutine must continue advancing while a controlled synchronous classifier
runs through an invocation-local `asyncio.to_thread`/executor boundary. Compute
the remaining whole-job deadline and protect the worker Task from the initial
wait with `await asyncio.wait_for(asyncio.shield(worker), remaining_seconds)`;
a naked initial `await worker` is forbidden because
coroutine cancellation can mark the Task cancelled while its OS thread keeps
running. On timeout or task cancellation, require a cooperative stop signal,
the still-live worker's termination before PCM deletion, no orphan
worker/artifact, and zero lane-runner/TTS/render/charge calls. Include a control
that fails when shielding is added only after the initial naked await. Capture
the same caller-owned absolute deadline inside the worker and require checks
before/after seek and read plus during bounded analysis loops.

Use this exact confidence boundary:

```python
assert speaker_cast.pitch_register(154.9, confidence=0.75) == "low"
assert speaker_cast.pitch_register(185.0, confidence=0.75) == "high"
assert speaker_cast.pitch_register(120.0, confidence=0.7499) == "unknown"
```

Add an isolated Auto-blackbox preflight test with injected fakes.
`run_auto_speaker_preflight` must call the injected prepare fake exactly once as
`prepare_subtitles(state, require_auto_cast=True)`, then await an injected async
`post_prepare_gate(prepared, state)`. A structured gate pause must be returned
unchanged before PCM extraction, classifier, lane runner, TTS, mux, delivery,
or wallet counters. A continue decision validates canonical sidecar/cues,
enforces the 16-label cap, and runs bounded classification off the event loop,
then returns only an invocation-local preflight/classification result for Task 5
to consume. Task 4 must prove zero pool assignment, identity annotation,
resolve/synthesize wrapper or failure-slot behavior, and zero lane-runner calls.
The test must not import, patch, or change the default lane modules or shared
product pipeline.

- [ ] **Step 2: Run RED**

Run:

```powershell
python -m pytest -q tests/test_p0_subdub_per_speaker_auto_gender_cast.py -k "exact_state or register or pcm or speaker_limit or manual_required or event_loop or cancellation or preflight_gate"
```

Expected: FAIL because the central predicate, classifier, whole-job cap,
manual-required error, nonblocking worker boundary, and separate Auto preflight
wrapper do not exist yet; no provider fixture is called.

- [ ] **Step 3: Implement bounded streaming reads and FFT autocorrelation**

Define the one repository-wide Auto predicate in
`services/subdub_blackboxes/auto_speaker.py`:

```python
def is_auto_speaker_state(state: Mapping[str, object] | None) -> bool:
    current = state or {}
    return (
        current.get("voice_kind") == "auto_speaker_gender"
        and current.get("voice_selection_mode") == "auto_speaker"
    )
```

Do not add any alternate one-key/truthy predicate in `bot.py` or the pricing
module. Add classifier constants:

```python
PCM_SAMPLE_RATE = 16_000
PCM_WINDOW_SAMPLES = 8_000
PCM_WINDOW_BYTES = PCM_WINDOW_SAMPLES * 2
MAX_AUTO_SPEAKER_LABELS = 16
MAX_SPEAKER_VOICED_SECONDS = 3.0
MAX_JOB_SAMPLE_SECONDS = 48.0
MAX_WORK_BUFFER_BYTES = 1_048_576
CLASSIFIER_WALL_TIMEOUT_SECONDS = 30.0
LOW_MAX_HZ = 155.0
HIGH_MIN_HZ = 185.0
MIN_REGISTER_CONFIDENCE = 0.75

class AutoCastManualRequired(RuntimeError):
    def __init__(self) -> None:
        super().__init__("AUTO_CAST_MANUAL_REQUIRED")

def pitch_register(median_hz: float, *, confidence: float) -> str:
    if float(confidence) < MIN_REGISTER_CONFIDENCE:
        return "unknown"
    if float(median_hz) <= LOW_MAX_HZ:
        return "low"
    if float(median_hz) >= HIGH_MIN_HZ:
        return "high"
    return "unknown"
```

Add `ordered_auto_speaker_labels(cues)` to retain first-cue order and raise on
the 17th distinct chunk-scoped label. Read raw `s16le` only with
`read(PCM_WINDOW_BYTES)`. Normalize one window, reject low RMS, compute bounded
autocorrelation, and aggregate a median without exceeding the 1 MiB budget.

Map `median_hz <= 155.0` to `low`, `median_hz >= 185.0` to `high`, and the open
interval to `unknown`. A classified result is usable only at confidence
`>= 0.75`. Ambiguous/noisy/overlapping/insufficient/unstable input, timeout,
resource overflow, or `unknown` raises `AutoCastManualRequired`; do not return a
female, male, dominant, or default fallback.

Expose `classify_speaker_registers(pcm_path: str,
ranges_by_speaker: dict[str, list[tuple[float, float]]], *,
deadline_monotonic: float, stop_requested: Callable[[], bool]) ->
dict[str, dict]`. Check the cooperative stop signal and `time.monotonic()` both
before and after every seek/read and within bounded normalization,
FFT/autocorrelation, peak-selection, and aggregation loops. Raise
`AutoCastManualRequired` when stop is requested or the deadline is reached. The
classifier receives one caller-owned absolute deadline for the whole job; it
must not add 30 seconds again inside a thread, per-speaker, or per-window loop.

Each in-memory result contains only `speaker_id`, `voice_register`,
`confidence`, `voiced_seconds`, `sample_count`, and `reason`. Persist no raw
PCM, embeddings, sample arrays, FFT/autocorrelation arrays, or NumPy values.

Create `services/subdub_blackboxes/auto_speaker.py` as an Auto-only adapter.
Task 4 exposes only `run_auto_speaker_preflight(...)`, accepting state, the
injected confirmed-diarized `prepare_subtitles`, async
`post_prepare_gate(prepared, state)`, PCM extraction callback, and classifier
inputs. It does not accept or call a lane runner, shared pipeline runner,
resolve-voice dependency, or synthesize dependency in this phase.

The wrapper owns Auto preflight before delegation. It verifies
`is_auto_speaker_state(state)`, calls the injected current confirmed-diarized
prepare exactly once as `prepare_subtitles(state, require_auto_cast=True)`, and
awaits `post_prepare_gate`. A structured gate pause is returned immediately.
Only a continue result may validate sidecar identity/the 16-label cap, extract
`-ac 1 -ar 16000 -f s16le` in the current temporary workspace, and classify.
It returns a bounded invocation-local preflight result and stops. Task 4 uses an
injected no-op/continue gate in fixtures; it performs no voice-pool validation,
assignment, segment annotation, resolve/synthesize wrapping, failure-slot
normalization, or lane-runner delegation. Task 5 alone adds those operations;
Task 7 supplies pricing and receipt behavior without changing this wrapper seam.

At the Auto wrapper's classifier boundary, use this exact ordering:

```python
classifier_started = time.monotonic()
classifier_deadline = (
    classifier_started + speaker_cast.CLASSIFIER_WALL_TIMEOUT_SECONDS
)
stop_event = threading.Event()
worker = asyncio.create_task(
    asyncio.to_thread(
        speaker_cast.classify_speaker_registers,
        pcm_path,
        ranges_by_speaker,
        deadline_monotonic=classifier_deadline,
        stop_requested=stop_event.is_set,
    )
)
remaining_seconds = max(0.0, classifier_deadline - time.monotonic())
classifications = await asyncio.wait_for(
    asyncio.shield(worker),
    remaining_seconds,
)
```

Await the invocation-local worker without blocking the event loop using
`await asyncio.wait_for(asyncio.shield(worker), remaining_seconds)` from the
initial wait; never await the Task naked. On the absolute deadline, set
`stop_event`, await the
still-live cooperatively terminating worker under `asyncio.shield`, then return
manual-required. On external `asyncio.CancelledError`, set the signal, await
termination and cleanup under shield, delete PCM only after the worker has
exited, then re-raise cancellation. Adding shield only after an initial naked
await is not compliant. The Auto wrapper is the sole PCM cleanup owner on
success, classifier failure, timeout, and cancellation; cleanup never races an
active reader.

Task 4 catches only preflight/classifier `AutoCastUnavailable` and
`AutoCastManualRequired` needed to return its isolated structured result. It
does not install dependency wrappers or a post-delegation failure slot because
there is no lane delegation in this phase.

The caller test captures both deadline values, asserts the exact 30.0-second
delta, keeps a heartbeat responsive, and proves timeout/cancellation cleanup
before any TTS mock is called. Do not wire `bot.py` in Task 4 and do not touch
any of the five protected shared-engine files.

- [ ] **Step 4: Run GREEN**

Run:

```powershell
python -m pytest -q tests/test_p0_subdub_per_speaker_auto_gender_cast.py -k "exact_state or register or pcm or speaker_limit or manual_required or event_loop or cancellation or preflight_gate"
```

Expected: PASS for the exact predicate, threshold/confidence boundaries, 16/17
labels, resource caps, event-loop responsiveness, cooperative cancellation,
initial-wait shielding, cleanup/non-persistence, and pause-before-classifier.
Assignment, annotation, resolve/synthesize/failure-slot, and lane-runner
counters remain zero; provider-call counter remains zero.

- [ ] **Step 5: Commit**

```powershell
git add -- services/subdub_speaker_cast.py services/subdub_blackboxes/auto_speaker.py tests/test_p0_subdub_per_speaker_auto_gender_cast.py
git commit -m "feat(subdub): classify bounded acoustic registers"
```

### Task 5: Assign provider-neutral stable voices and synthesize per cue

**Files:**
- Modify: `services/subdub_speaker_cast.py`
- Modify: `services/subdub_blackboxes/auto_speaker.py`
- Test: `tests/test_p0_subdub_per_speaker_auto_gender_cast.py`

- [ ] **Step 1: Write RED stable-pool and per-cue tests**

Use four first-occurrence-ordered speakers: two `low` and two `high`. Supply
validated local pools `low-a, low-b` and `high-a, high-b`. Require deterministic
mapping across retry/resume, different IDs for same-register speakers while the
pool allows, and unchanged mapping when input dict order changes. Require a
manual-required result for an empty, invalid, duplicate-only, wrong-register,
or too-small pool before any TTS call.

```python
first_cue_speaker_order = [
    "chunk_00:speaker_0", "chunk_00:speaker_1",
    "chunk_01:speaker_0", "chunk_01:speaker_1",
]
classifications = {
    first_cue_speaker_order[0]: {"voice_register": "low", "confidence": 0.90},
    first_cue_speaker_order[1]: {"voice_register": "low", "confidence": 0.88},
    first_cue_speaker_order[2]: {"voice_register": "high", "confidence": 0.91},
    first_cue_speaker_order[3]: {"voice_register": "high", "confidence": 0.89},
}
casts_a = speaker_cast.assign_stable_voices(
    classifications,
    speaker_order=first_cue_speaker_order,
    validated_pools={"low": ["low-a", "low-b"], "high": ["high-a", "high-b"]},
    assignment_seed="a" * 64,
)
casts_b = speaker_cast.assign_stable_voices(
    dict(reversed(list(classifications.items()))),
    speaker_order=first_cue_speaker_order,
    validated_pools={"high": ["high-b", "high-a"], "low": ["low-b", "low-a"]},
    assignment_seed="a" * 64,
)
assert casts_a == casts_b
assert len({casts_a["chunk_00:speaker_0"]["voice_id"],
            casts_a["chunk_00:speaker_1"]["voice_id"]}) == 2
```

Feed cues `speaker_0, speaker_1, speaker_0` through the Auto wrapper with an
injected fake scalar synthesizer. The prepared fixture must contain both
`source_segments` and translated `output_segments`; shuffle the assignment rows
relative to the cue rows so a positional join cannot pass. Require the wrapped
prepare result to identity-join each assignment by the exact tuple
`(cue_id, start, end)` and annotate every cue in both lists with its private
`tts_voice_id`, without changing either list's cue count, order, or timestamps.
Missing either list, a missing/duplicate identity, or any exact timestamp
mismatch must fail before TTS.

Route the fixture through both protected policy branches. For `dub_only`,
require the wrappers to validate the exact `source_segments` list selected by
`resolve_subdub_dub_audio_policy`; for translated `subtitle_plus_dub`, require
the exact selected `output_segments` list. The wrapped `resolve_voice_id`
returns the first cue's validated assigned ID from that selected list only as
the shared pipeline's compatibility scalar. The wrapped
`synthesize_segments` revalidates the entire selected cue list, then calls the
fake scalar synthesizer once per cue in exact order with that cue's assigned
ID. Assert unchanged selected-list cue count/order/timestamps and masked
diagnostics.

Add pure aggregation fixtures for the per-cue scalar result shape. Flatten
returned audio chunks first by cue order and then by each scalar result's chunk
order. If every nonempty provider label is identical, the internal aggregate
provider is that label; if two or more distinct nonempty labels occur, it is the
generic internal value `mixed`; if no label exists, it is empty. Require exactly
one successful scalar result per cue and fail closed on a missing/extra result.
Neither individual provider labels nor `mixed` may enter public copy.

For a missing, empty, or non-pool `tts_voice_id`, require
`AUTO_CAST_MANUAL_REQUIRED` before the fake scalar synthesizer's first call.
Monkeypatch every live voice-catalog function to raise if invoked and snapshot
provider order/ENV before and after. Real provider calls remain zero.

- [ ] **Step 2: Run RED**

```powershell
python -m pytest -q tests/test_p0_subdub_per_speaker_auto_gender_cast.py -k "stable_voice or voice_pool or per_cue or provider_aggregation or catalog"
```

Expected: FAIL because pool validation/assignment and the three complete Auto
dependency wrappers are absent. Catalog-call and real-provider counters remain
zero.

- [ ] **Step 3: Implement provider-neutral pool validation and stable assignment**

Keep provider names outside the assignment API. Normalize configured inventory
before the job into `low` and `high` candidates, validating syntax, declared
register, uniqueness, enabled/configured state, and the existing local adapter
contract. Do not query a live catalog during the job and do not claim every
provider voice is live.

```python
def assign_stable_voices(
    classifications: dict[str, dict],
    *,
    speaker_order: list[str],
    validated_pools: dict[str, list[str]],
    assignment_seed: str,
) -> dict[str, dict]:
    result: dict[str, dict] = {}
    used: dict[str, set[str]] = {"low": set(), "high": set()}
    for speaker_id in speaker_order:
        item = classifications.get(speaker_id) or {}
        register = str(item.get("voice_register") or "unknown")
        confidence = float(item.get("confidence") or 0.0)
        if register not in used or confidence < MIN_REGISTER_CONFIDENCE:
            raise AutoCastManualRequired()
        pool = sorted(set(validated_pools.get(register) or []))
        available = [voice_id for voice_id in pool if voice_id not in used[register]]
        if not available:
            raise AutoCastManualRequired()
        digest = hashlib.sha256(
            f"{assignment_seed}:{speaker_id}:{register}".encode("utf-8")
        ).digest()
        voice_id = available[int.from_bytes(digest[:8], "big") % len(available)]
        used[register].add(voice_id)
        result[speaker_id] = {
            "speaker_id": speaker_id,
            "voice_register": register,
            "voice_id": voice_id,
        }
    return result
```

Use the canonical sidecar SHA-256 as `assignment_seed` so retry/resume yields
the same result. Preserve first-cue speaker order when building
`classifications`; do not sort speakers lexically. If distinct same-register
voices cannot be allocated, return `AUTO_CAST_MANUAL_REQUIRED` before TTS.
Task 5 now extends Task 4's isolated classifier result into the complete Auto
adapter. Add the public `run_auto_speaker_blackbox(...)` entry point here; it
calls the already-proven `run_auto_speaker_preflight(...)` and only after a
continue result installs the Task 5 behavior. Extend only the Auto module's
wrapped prepare dependency: consume Task
4's classification, assign the validated pools, build an identity map keyed by the
exact canonical tuple `(cue_id, start, end)`, and annotate both
`prepared["source_segments"]` and `prepared["output_segments"]`. Both lists are
required for Auto. Join neither by position nor by text, and fail closed before
TTS if either list, identity component, assignment, or exact timestamp match is
missing or duplicated. Preserve each list's existing cue order and timing. Do
not add fields or branches to `services/subtitle_dub_product_pipeline.py`.

- [ ] **Step 4: Consume the validated assignment per cue**

Annotate every Auto cue before TTS and reject any missing assignment:

```python
cast = casts.get(str(segment.get("speaker_id") or ""))
if not cast:
    raise speaker_cast.AutoCastManualRequired()
annotated = {
    **segment,
    "voice_register": cast["voice_register"],
    "tts_voice_id": cast["voice_id"],
}
```

Implement the other two wrappers only in
`services/subdub_blackboxes/auto_speaker.py`:

- wrapped `resolve_voice_id` validates every prepared Auto cue against the
  completed assignment in the exact segment list selected by
  `resolve_subdub_dub_audio_policy`, then returns that list's first cue's real
  validated `tts_voice_id` solely for the current shared pipeline nonempty
  scalar guard; it never invents a provider ID and never queries a live catalog;
- wrapped `synthesize_segments` revalidates every cue and all private IDs in
  that exact selected list before any call, then invokes the injected existing scalar
  `synthesize_segments` sequentially with `[cue]` and
  `voice_id=cue["tts_voice_id"]`. Forward the unchanged speech/language kwargs,
  require one successful ordered result per cue, flatten chunks in cue/result
  order, and combine provider metadata deterministically in the result shape
  the shared pipeline already consumes. All nonempty labels equal returns that
  internal label, distinct labels return internal `mixed`, and no labels return
  empty; never silently choose first/last and never expose a provider label in
  public output.

Do not modify `synthesize_dub_segment_chunks()`, any default/manual module, or
`services/subtitle_dub_product_pipeline.py`. The shared pipeline may pass the
compatibility scalar to the Auto synth wrapper, but that wrapper must use each
cue's validated private ID for the actual scalar call. Preserve cue count,
order, start/end timing, provider order, endpoint, ENV, adapter modules,
timeline, QC, mux, delivery, and charging.

Only in Task 5, after assignment and both exact identity joins succeed, define
the async prepare closure that returns the already prepared annotated structure
and delegate once to the injected `run_subdub_lane_blackbox` with the existing
shared runner. The protected lane/shared pipeline may call that closure, but it
cannot cause another prepare, cache rewrite, ASR, translation, or provider call.

Task 5 also installs the invocation-local resolve/synthesize failure slot. Each
wrapper records only `AutoCastUnavailable` or `AutoCastManualRequired` before
re-raising. After lane delegation returns or raises, the Auto adapter checks
that slot before accepting a generic normalized result and emits the canonical
manual-required result when present. It must not use global state, parse public
copy, or intercept unrelated provider/render/mux/charge/delivery failures or
external cancellation. No part of this assignment/annotation/wrapper/failure-
slot/delegation behavior may be backported into Task 4.

- [ ] **Step 5: Run GREEN and protected TTS comparators**

```powershell
python -m pytest -q tests/test_p0_subdub_per_speaker_auto_gender_cast.py -k "stable_voice or voice_pool or per_cue or provider_aggregation or catalog"
python -m pytest -q tests/test_p0_subdub_tts_audio_truth_sequential.py tests/test_p0_subdub_live14_blackbox_lane_language_contract.py tests/test_p0_19i_final_subdub_voice_lock_direct_dub_shared_status.py
```

- [ ] **Step 6: Commit**

```powershell
git add -- services/subdub_speaker_cast.py services/subdub_blackboxes/auto_speaker.py tests/test_p0_subdub_per_speaker_auto_gender_cast.py
git commit -m "feat(subdub): assign stable voices per speaker cue"
```

### Task 6: Wire exact-pair Auto dispatch, state/button, and native copy

**Files:**
- Modify: `bot.py:225653-225870`
- Modify: `bot.py:227775-228110`
- Modify: `bot.py:243130-244400`
- Modify: `services/pricing_guide_content.py:2040-2248`
- Modify: `tests/test_p0_i18n_video_subdub_native_contract.py`
- Test: `tests/test_p0_subdub_per_speaker_auto_gender_cast.py`

- [ ] **Step 1: Write RED two-lane state and callback tests**

For both `VIDEO_SUBTITLE_MODE_DUB` (`dub_only`) and
`VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB`, require one callback
`videodub|voice|auto_speaker_gender`, `voice_kind="auto_speaker_gender"`, and
`voice_selection_mode="auto_speaker"`. Assert manual buttons, callbacks,
labels, route results, and scalar voice behavior are unchanged.

Exercise Auto-after-manual and manual-after-Auto through the real callback/state
helpers, including back, retry, and resume. Require opposing state to clear in
both directions. Tests must capture the state immediately after reset and before
assignment: `voice_kind` and `voice_selection_mode` are absent at that point.
Only then may the callback assign the newly chosen Auto or manual/saved/custom
mode, proving stale `voice_kind="auto_speaker_gender"` cannot survive:

```python
SUBDUB_MANUAL_VOICE_FIELDS = frozenset({
    "voice_style", "voice_id", "selected_voice_gender", "requested_gender",
    "provider_voice_id", "selected_tts_voice_id", "resolved_voice_id",
    "resolved_gender", "_subdub_voice_resolution",
})
SUBDUB_AUTO_VOICE_FIELDS = frozenset({
    "voice_selection_mode", "speaker_sidecar_path", "speaker_sidecar_sha256",
    "speaker_classifications", "speaker_casts", "per_cue_voice_assignments",
    "auto_exact_receipt_version", "auto_exact_media_sha256",
    "auto_exact_subtitle_sha256", "auto_exact_sidecar_sha256",
    "auto_exact_timeline_signature", "auto_exact_actual_billable_words",
    "auto_exact_actual_total_xu", "auto_exact_receipt_confirmed",
})
```

Structured classifier/cast/prepared data stays out of `USER_PENDING`.
`USER_PENDING` may retain canonical mode and bounded UI mirror fields during a
deliberate confirmation pause, but it is never receipt, ownership, expiry,
claim, or resume authority. Task 7 persists the authoritative bounded receipt
only in the existing durable SubDub job snapshot/engine-job store. Missing
durable authority fails closed even if a mirror remains in memory. An Auto
preflight or assignment/synthesis validation failure clears the mirror fields
and returns the same lane's voice screen with native manual-choice copy.
Downstream provider/render/mux/charge/delivery failures keep their existing
handling.

Add a dispatch matrix around the real bot-core seam. Only this exact pair may
call `services.subdub_blackboxes.auto_speaker`:

```python
auto_speaker.is_auto_speaker_state(state)
```

This helper, defined in Task 4, is the only allowed predicate. Do not duplicate
the two comparisons in `bot.py`.

Test default/empty, every manual/saved/custom mode, either Auto key alone, and
both malformed cross-pairs. Each non-exact case must call the existing
`subdub_blackboxes.run_subdub_lane_blackbox` exactly once with runner identity
`subtitle_dub_product_pipeline.run_subdub_pipeline`, the original injected
dependency identities, and no call to the Auto module. The exact pair calls the
Auto module once; its spy must receive that same lane runner, pipeline runner,
payload, and dependencies. Add a source comparator requiring the literal
existing call and runner expression to remain in `_execute_video_dubbing_pipeline_core`.

Complement the dispatch/source spy with a behavior comparator that executes the
injected bot-local prepare seam. Capture the value forwarded into
`video_dubbing_prepare_subtitles`: the exact Auto pair must call prepare once and
capture exactly `[True]`; every default/manual/partial/malformed case must call
prepare once through the unchanged path and capture exactly `[False]`, whether
the keyword was omitted at the caller or explicitly false. No matrix case may
perform a second prepare or ASR call. Observing dispatch identity alone is not
sufficient evidence for this flag contract.

Add failure-mapping fixtures for exceptions raised during owned preflight and
from the Auto resolve/synthesize wrappers while the lane runner is executing.
The Auto wrapper catches only `AutoCastUnavailable` and
`AutoCastManualRequired` and returns:

```python
{
    "ok": False,
    "status": "AUTO_CAST_MANUAL_REQUIRED",
    "reason": safe_internal_reason,
    "lane_mode": lane_mode,
    "public_copy_key": "voice_auto_manual_required",
}
```

The bot clears bounded Auto receipt/classification/cast/per-cue fields and
re-renders the native voice screen for the same lane. Test both lanes and prove
no TTS call. Include a fake protected runner that swallows/relabels the Auto
dependency exception; the invocation-local failure slot must still override its
generic result with the canonical same-lane result. `AUTO_EXACT_CONFIRMATION_REQUIRED`
is a resumable control result, not this failure. User cancellation and
insufficient balance retain their own safe outcomes; external `CancelledError`
cleans up then re-raises; unrelated provider/TTS/render/mux/charge/delivery
failures retain existing handlers and refund behavior.

- [ ] **Step 2: Run RED**

```powershell
python -m pytest -q tests/test_p0_subdub_per_speaker_auto_gender_cast.py -k "auto_button or activation_closed or voice_state or both_lanes or manual_mode or exact_pair or default_blackbox or manual_failure_mapping"
```

Expected: FAIL because the callback, bidirectional state contract, and exact-pair
Auto dispatch are absent.

- [ ] **Step 3: Implement one bidirectional reset helper and both UI entries**

Add and use this helper on Auto selection, manual/saved/custom selection,
back-to-voice, retry, resume, and redub:

```python
def reset_subdub_voice_selection(state: dict, *, selecting_auto: bool) -> dict:
    blocked = SUBDUB_MANUAL_VOICE_FIELDS if selecting_auto else SUBDUB_AUTO_VOICE_FIELDS
    cleaned = {key: value for key, value in dict(state or {}).items() if key not in blocked}
    cleaned.pop("voice_kind", None)
    cleaned.pop("voice_selection_mode", None)
    return cleaned
```

The helper is reset-only. Every selection handler must call it first and assign
the new mode second:

```python
state = reset_subdub_voice_selection(state, selecting_auto=selecting_auto)
if selecting_auto:
    state["voice_kind"] = "auto_speaker_gender"
    state["voice_selection_mode"] = "auto_speaker"
else:
    state["voice_kind"] = chosen_voice_kind
    state["voice_selection_mode"] = chosen_manual_mode
```

`chosen_voice_kind` and `chosen_manual_mode` come from the existing
manual/saved/custom callback path; do not introduce new manual identifiers.
Use the same reset-before-assign ordering on back-to-voice, retry, resume, and
redub restoration. Tests must cover both directions and each restoration edge.

Build the Auto button in the shared voice-keyboard builder for both dubbing
lanes and test it through direct seams. Do not add it to
subtitle-only/translation-only screens. Task 6 must leave the user-visible
button/callback/dispatch activation fail-closed and unreachable; Task 7
atomically enables that route only after pricing, exact receipt pause/resume,
and protected comparators pass. This is code sequencing, not an ENV flag. Auto
work still starts only after the existing confirmation edge.

Make the current bot-local prepare seam additive and default-closed:

```python
async def _prepare_subtitles_for_blackbox(
    service_state: dict,
    *,
    require_auto_cast: bool = False,
) -> dict:
    # existing arguments stay unchanged
    return await video_dubbing_prepare_subtitles(
        # existing positional/keyword arguments stay unchanged
        require_auto_cast=bool(require_auto_cast),
    )
```

The default/manual lane call continues to omit this keyword and therefore
forwards `False`. Only the exact-pair Auto wrapper invokes the injected helper
once with `require_auto_cast=True`; state values alone must not enable
diarization or trigger another prepare/ASR attempt.

Import `services.subdub_blackboxes.auto_speaker` without editing the package
`__init__.py`. At the current product-result call site, call
`auto_speaker.is_auto_speaker_state(state)`. For true only, call
`auto_speaker.run_auto_speaker_blackbox(...)` and inject:

```text
run_lane_blackbox = subdub_blackboxes.run_subdub_lane_blackbox
runner = subtitle_dub_product_pipeline.run_subdub_pipeline
prepare_subtitles = _prepare_subtitles_for_blackbox
resolve_voice_id = _resolve_voice_id_for_blackbox
synthesize_segments = _synthesize_dub_segments_for_blackbox
post_prepare_gate = _subdub_auto_post_prepare_gate
```

Pass every other current payload/dependency unchanged. The Auto module wraps
only those last three dependencies and delegates to the injected lane blackbox
and runner. Add the smallest bounded PCM-extraction helper in `bot.py` and pass
it as an Auto-only support callback to `run_auto_speaker_blackbox`; it uses the
current
temporary workspace and existing bounded FFmpeg stage runner. This support
callback is not a fourth shared-pipeline dependency replacement: only
`prepare_subtitles`, `resolve_voice_id`, and `synthesize_segments` are
substituted in the payload sent to `run_subdub_lane_blackbox`.

Through Task 6, `_subdub_auto_post_prepare_gate` is a local continue-only seam
used by focused fixtures while activation remains unreachable. Task 7 replaces
its behavior with the exact receipt gate and performs the atomic user-route
activation; Task 4–6 code must not import or calculate pricing.

In the `else` branch, preserve the literal existing source call:

```python
product_result = await subdub_blackboxes.run_subdub_lane_blackbox(
    lane_mode=mode,
    runner=subtitle_dub_product_pipeline.run_subdub_pipeline,
    # existing payload and dependency arguments, unchanged
)
```

Do not extract this default call into the Auto module or a new generic helper.
Do not copy PR613-era `bot.py`; preserve all later wrapper, render-debug, report,
timeline/QC, mux, delivery, and charging evolution already present at HEAD.

- [ ] **Step 4: Add exact native 17-locale copy**

Append `voice_auto_speaker`, `voice_auto_explanation`, and
`voice_auto_manual_required` to `_PUBLIC_SUBDUB_DEEP_KEYS`. Add the following
exact native tuple `(label, explanation, manual_required)` for every locale:

```python
AUTO_COPY = {
    "vi": ("👥 Tự nhận giọng (tối đa 16)", "Ghép giọng theo đặc điểm âm thanh cho tối đa 16 nhãn người nói; không xác định danh tính hay giới tính cá nhân.", "Không thể ghép giọng tự động một cách an toàn. Vui lòng chọn giọng thủ công."),
    "en": ("👥 Auto voice matching (up to 16)", "Matches voices from acoustic traits for up to 16 speaker labels; it does not identify people or personal gender.", "Auto could not match voices safely. Please choose a voice manually."),
    "zh": ("👥 自动匹配声音（最多 16 个）", "根据声学特征为最多 16 个说话人标签匹配声音；不识别身份或个人性别。", "无法安全地自动匹配声音。请选择手动声音。"),
    "es": ("👥 Asignación automática de voces (máx. 16)", "Asigna voces por rasgos acústicos a un máximo de 16 etiquetas de hablante; no identifica personas ni su género personal.", "No se pudieron asignar las voces automáticamente de forma segura. Elige una voz manualmente."),
    "pt": ("👥 Atribuição automática de vozes (máx. 16)", "Associa vozes por características acústicas a até 16 rótulos de falante; não identifica pessoas nem gênero pessoal.", "Não foi possível associar as vozes automaticamente com segurança. Escolha uma voz manualmente."),
    "fr": ("👥 Attribution automatique des voix (16 max.)", "Associe des voix selon des caractéristiques acoustiques pour 16 étiquettes de locuteur au maximum, sans identifier une personne ni son genre.", "L’attribution automatique n’a pas pu être faite de façon sûre. Choisissez une voix manuellement."),
    "de": ("👥 Automatische Stimmenzuordnung (max. 16)", "Ordnet bis zu 16 Sprecherlabels anhand akustischer Merkmale Stimmen zu; Personen oder persönliches Geschlecht werden nicht erkannt.", "Die Stimmen konnten nicht sicher automatisch zugeordnet werden. Bitte wählen Sie eine Stimme manuell."),
    "ja": ("👥 音声を自動割り当て（最大 16）", "音響的な特徴から最大 16 個の話者ラベルに音声を割り当てます。人物の特定や個人の性別判定は行いません。", "安全に自動割り当てできませんでした。音声を手動で選択してください。"),
    "ko": ("👥 음성 자동 배정(최대 16)", "음향 특성으로 최대 16개 화자 라벨에 음성을 배정하며, 사람의 신원이나 개인 성별을 식별하지 않습니다.", "음성을 안전하게 자동 배정하지 못했습니다. 음성을 직접 선택해 주세요."),
    "hi": ("👥 आवाज़ों का अपने-आप मिलान (अधिकतम 16)", "ध्वनिक गुणों से अधिकतम 16 वक्ता लेबलों के लिए आवाज़ मिलाता है; यह व्यक्ति की पहचान या निजी लिंग निर्धारित नहीं करता।", "आवाज़ों का सुरक्षित स्वचालित मिलान नहीं हो सका। कृपया आवाज़ मैन्युअल रूप से चुनें।"),
    "ar": ("👥 تعيين تلقائي للأصوات (حتى 16)", "يطابق الأصوات حسب الخصائص الصوتية لما يصل إلى 16 تسمية متحدث، ولا يحدد هوية الأشخاص أو جنسهم الشخصي.", "تعذر تعيين الأصوات تلقائياً بأمان. يرجى اختيار صوت يدوياً."),
    "ru": ("👥 Автоподбор голосов (до 16)", "Подбирает голоса по акустическим признакам максимум для 16 меток говорящих; не определяет личность или личный гендер.", "Безопасно подобрать голоса автоматически не удалось. Выберите голос вручную."),
    "tr": ("👥 Otomatik ses eşleme (en fazla 16)", "Akustik özelliklere göre en fazla 16 konuşmacı etiketine ses eşler; kişi kimliği veya kişisel cinsiyet belirlemez.", "Sesler güvenli biçimde otomatik eşlenemedi. Lütfen sesi elle seçin."),
    "th": ("👥 จับคู่เสียงอัตโนมัติ (สูงสุด 16)", "จับคู่เสียงจากลักษณะทางเสียงให้ป้ายผู้พูดได้สูงสุด 16 ป้าย โดยไม่ระบุตัวบุคคลหรือเพศส่วนบุคคล", "ไม่สามารถจับคู่เสียงอัตโนมัติได้อย่างปลอดภัย โปรดเลือกเสียงด้วยตนเอง"),
    "fil": ("👥 Awtomatikong pagtutugma ng boses (hanggang 16)", "Itinutugma ang boses ayon sa katangiang akustiko para sa hanggang 16 label ng tagapagsalita; hindi nito kinikilala ang tao o personal na kasarian.", "Hindi ligtas na naitugma nang awtomatiko ang mga boses. Pumili ng boses nang manu-mano."),
    "it": ("👥 Assegnazione automatica delle voci (max 16)", "Abbina le voci in base a caratteristiche acustiche per un massimo di 16 etichette di parlante; non identifica persone né il genere personale.", "Non è stato possibile abbinare automaticamente le voci in modo sicuro. Scegli una voce manualmente."),
    "id": ("👥 Pencocokan suara otomatis (maks. 16)", "Mencocokkan suara dari ciri akustik untuk maksimal 16 label pembicara; tidak mengidentifikasi orang atau gender pribadi.", "Suara tidak dapat dicocokkan secara otomatis dengan aman. Silakan pilih suara secara manual."),
}
```

Store all three values explicitly in each locale tuple; do not implement
runtime fallback or reuse English/Vietnamese strings. Callback/state tokens stay
canonical English identifiers.

- [ ] **Step 5: Run GREEN and manual/i18n comparators**

```powershell
python -m pytest -q tests/test_p0_subdub_per_speaker_auto_gender_cast.py -k "auto_button or activation_closed or voice_state or both_lanes or manual_mode or exact_pair or default_blackbox or manual_failure_mapping"
python -m pytest -q tests/test_p0_i18n_video_subdub_native_contract.py tests/test_p0_i18n_deep_locale_no_fallback.py tests/test_p0_19m5c_subdub_mode_route_female_voice_state_fix.py
python -m pytest -q tests/test_p0_subdub_live14_blackbox_lane_language_contract.py
```

- [ ] **Step 6: Commit**

```powershell
git add -- bot.py services/pricing_guide_content.py tests/test_p0_i18n_video_subdub_native_contract.py tests/test_p0_subdub_per_speaker_auto_gender_cast.py
git commit -m "feat(subdub): add native 16-speaker Auto selection"
```

### Task 7: Add isolated Auto word pricing, exact confirmation, and one-shot actual charge

This task is last and separate. Its public contract is 0.5 Xu per billable word
for Auto only: 10% off at 1,000 words and 20% off at 10,000 words. Manual prices
remain unchanged; the 20% tier replaces rather than stacks with the 10% tier.
Do not enable this task until Tasks 4–6 pass. Do not add a wallet primitive or
move the existing SubDub charge before successful render/validation.

**Files:**
- Create: `services/subdub_auto_word_pricing.py`
- Modify: `bot.py:225595-225635`
- Modify: `bot.py:228220-228250`
- Modify: `services/pricing_guide_content.py`
- Create: `tests/test_p0_subdub_auto_word_pricing.py`
- Test: `tests/test_p0_subdub_per_speaker_auto_gender_cast.py`

- [ ] **Step 1: Prove a language-safe counter before touching invoice code**

Write table-driven fixtures for Vietnamese, English, Chinese, Japanese, Thai,
Korean, Hindi, Arabic, and mixed punctuation. Use NFKC normalization. Count
contiguous letter/number runs as one word for spaced scripts; count each
Han/Kana/Hangul base character and each Thai base-plus-combining-mark cluster as
one deterministic billable unit. Ignore whitespace, punctuation, symbols, and
emoji. The same function must count any estimate text and the final canonical
cue text that will be synthesized.

Implement only this pure function first:

```python
@pytest.mark.parametrize(("text", "expected"), [
    ("Xin chào thế giới", 4),
    ("Hello, world!", 2),
    ("你好世界", 4),
    ("こんにちは世界", 7),
    ("สวัสดีโลก", 7),
    ("안녕하세요 세계", 7),
    ("नमस्ते दुनिया", 2),
    ("مرحبا بالعالم", 2),
    ("Hello，世界!", 3),
])
def test_billable_word_contract(text, expected):
    assert count_billable_words(text) == expected
```

Then implement the production function:

```python
import unicodedata

UNSPACED_RANGES = (
    (0x3400, 0x4DBF), (0x4E00, 0x9FFF),
    (0x3040, 0x30FF), (0x31F0, 0x31FF),
    (0x0E00, 0x0E7F), (0xAC00, 0xD7AF),
)

def _unspaced_base(char: str) -> bool:
    codepoint = ord(char)
    return any(start <= codepoint <= end for start, end in UNSPACED_RANGES)

def count_billable_words(text: str) -> int:
    count = 0
    in_spaced_word = False
    for char in unicodedata.normalize("NFKC", str(text or "")):
        category = unicodedata.category(char)
        if category.startswith("M"):
            continue
        if _unspaced_base(char) and category[0] in {"L", "N"}:
            count += 1
            in_spaced_word = False
        elif category[0] in {"L", "N"}:
            if not in_spaced_word:
                count += 1
            in_spaced_word = True
        else:
            in_spaced_word = False
    return count
```

Run:

```powershell
python -m pytest -q tests/test_p0_subdub_auto_word_pricing.py -k "billable_word"
```

Expected after the pure implementation: all multilingual fixtures PASS. Stop
Task 7 if estimate and actual paths cannot call this exact counter.

- [ ] **Step 2: Write RED exact-price boundary tests**

Require these exact results:

```python
assert auto_voice_component_xu(1) == 1
assert auto_voice_component_xu(999) == 500
assert auto_voice_component_xu(1_000) == 450
assert auto_voice_component_xu(9_999) == 4_500
assert auto_voice_component_xu(10_000) == 4_000
assert auto_voice_component_xu(10_001) == 4_001
```

Assert Auto `dub_only` total equals only the Auto component. Assert Auto
`subtitle_plus_dub` total equals the existing subtitle component plus the
already-ceiled Auto component. Manual female/male/saved/custom invoice snapshots
must remain byte-for-byte unchanged. Add a monkeypatch that makes the unrelated
100-unit discount helper raise if Auto pricing calls it.

Add a state matrix around quote, confirmation, read-only balance guard, invoice,
selected spend amount, and final one-shot charge. Every decision must call
`auto_speaker.is_auto_speaker_state(state)`. Only both exact keys use the Auto
component; either key alone, stale receipt fields, and malformed cross-pairs use
the unchanged manual/default price and charge amount and never enter the Auto
exact-confirmation gate.

- [ ] **Step 3: Implement the pure Decimal formula**

```python
from decimal import Decimal, ROUND_CEILING

AUTO_XU_PER_WORD = Decimal("0.5")

def auto_volume_discount_percent(words: int) -> int:
    safe_words = max(0, int(words or 0))
    if safe_words >= 10_000:
        return 20
    if safe_words >= 1_000:
        return 10
    return 0

def auto_voice_component_xu(words: int) -> int:
    safe_words = max(0, int(words or 0))
    discount = Decimal(100 - auto_volume_discount_percent(safe_words)) / Decimal(100)
    amount = Decimal(safe_words) * AUTO_XU_PER_WORD * discount
    return int(amount.to_integral_value(rounding=ROUND_CEILING))
```

Never use `float`, never apply both tiers, and never pass this component through
`finance_volume_discount_percent`, `video_only_price_discount_percent`, or an
unrelated 100-unit comparator. In `video_dubbing_invoice_breakdown()`, branch
only when the central exact predicate returns true:

```python
if auto_speaker.is_auto_speaker_state(state):
    auto_xu = auto_voice_component_xu(billable_words)
    voice_xu = auto_xu
    total_xu = existing_subtitle_component_xu + auto_xu
```

For `dub_only`, `existing_subtitle_component_xu` is zero. For
`subtitle_plus_dub`, obtain it from the current subtitle branch without changing
its rate, counter, discount, or ceiling.

- [ ] **Step 4: Prove estimate-to-exact-confirmation gates before enabling Auto pricing**

There are two quote paths and neither mutates the wallet:

1. If the exact text already exists for the list that
   `resolve_subdub_dub_audio_policy(state, prepared)["tts_segments"]` will
   select, count only that final cue text with `count_billable_words()`, quote
   the exact Auto component, and use the existing confirmation once. This is a
   source-subtitle cache when policy selects source text, or a valid translation
   cache for the exact source/target pair when policy selects translated text.
   An existing source subtitle does not make the quote exact when the selected
   translation is absent. For `subtitle_plus_dub`, the exact total remains the
   unchanged existing subtitle component plus the exact Auto component.
2. Otherwise the first confirmation is a **text-preparation authorization**,
   not an ASR-only authorization. It authorizes ASR at most once only when a
   valid source subtitle/ASR cache is absent. It additionally authorizes at most
   one call through the existing translation path only when the protected
   policy selects translated TTS text and no valid translation cache exists for
   the exact source text and target language. It authorizes zero acoustic
   classification, voice assignment, TTS, render, delivery, spend, refund, or
   any other wallet mutation. After preparation, call the protected policy,
   count the final text of exactly its selected `tts_segments`, and recompute
   the exact Auto component/total inside `_subdub_auto_post_prepare_gate`.
   Perform the current read-only balance guard, then return
   `AUTO_EXACT_CONFIRMATION_REQUIRED` before PCM extraction, classifier, lane
   runner, TTS, render, or debit whenever the selected-text count was unknown at
   the quote or differs from it.

Implement only a pure decision helper in the pricing module:

```python
def auto_exact_confirmation_state(
    *,
    quoted_words: int | None,
    actual_words: int,
    exact_known_at_quote: bool,
) -> dict[str, int | bool | None]:
    quoted = None if quoted_words is None else max(0, int(quoted_words))
    actual = max(0, int(actual_words or 0))
    return {
        "quoted_billable_words": quoted,
        "actual_billable_words": actual,
        "quoted_auto_xu": (
            None if quoted is None else auto_voice_component_xu(quoted)
        ),
        "actual_auto_xu": auto_voice_component_xu(actual),
        "exact_confirmation_required": (
            not exact_known_at_quote or quoted is None or quoted != actual
        ),
    }
```

The decision helper calculates no subtitle charge and touches no wallet. The
caller combines `actual_auto_xu` with the unchanged existing subtitle component
only for `subtitle_plus_dub`; `dub_only` uses `actual_auto_xu` alone.

Implement the real async `post_prepare_gate(prepared, state)` in `bot.py` and
inject it through the Task 4 seam. It first rechecks
`auto_speaker.is_auto_speaker_state(state)`. When exact confirmation is needed,
return only this bounded control result:

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

Persist the authoritative pause as durable, nonterminal
`awaiting_auto_exact_confirmation` through the existing
`persist_subtitle_dub_pipeline_job_snapshot(job_key, job, ...)` seam, which
already calls `save_engine_async_job(...)`. Do not add a DB schema/table/column.
The snapshot keeps the existing workspace reference and only the bounded
hash/scalar receipt above plus claim timestamps/token as state changes. It does
not persist prepared segments, classifier/cast data, PCM, provider payloads,
credentials, or wallet state. `USER_PENDING` may mirror mode/panel fields but
is never owner, receipt, expiry, claim, or resume authority. The exact-confirm
callback contains only the bounded public job token and opaque session nonce;
it carries no hash, count, total, path, or provider value.

Add explicit control interception at both current failure-normalization seams:

1. In `_execute_video_dubbing_pipeline_core`, inspect `product_result` for
   `AUTO_EXACT_CONFIRMATION_REQUIRED` immediately after the Auto blackbox call
   and before the generic `if not product_result.get("ok")` branch. Return the
   structured control result without `_failed_product_result`.
2. In `execute_video_dubbing_pipeline`, inspect that result before manifest and
   update defaults derive `failed`/`failed_no_charge` from `ok=False`. Persist
   `status`, `lifecycle_state`, `current_stage`, and `progress_stage` as
   `awaiting_auto_exact_confirmation`, leave `terminal_state` empty, keep the
   workspace, and render the exact-confirm/cancel panel. Never write the generic
   failure debug snapshot for this control state.

Add `awaiting_auto_exact_confirmation` and
`resuming_auto_exact_confirmation` to the active acquisition/dedupe and
workspace-lifecycle contract, including `SUBDUB_WORKSPACE_ACTIVE_STATUSES`.
They are nonterminal and must prevent prune/cleanup; neither belongs in terminal
sets. Status refresh resolves the durable engine-job snapshot and only renders
the current state.

The exact-confirm callback starts a second handler invocation by rehydrating the
same job via `get_engine_async_job(...)`/the existing engine-job lookup. Validate
owner, chat, mode, job key/session nonce, safe existing workspace, expiry, and
all receipt identities before placing a copy in
`SUBTITLE_DUB_PIPELINE_JOBS`. That in-memory dict is a cache, never authority.

Create one dedicated per-job `asyncio.Lock` registry for exact-confirm/cancel
claims. Under that lock, reload the latest durable snapshot and compare-and-set
only the expected receipt/quote versions from:

```text
status=awaiting_auto_exact_confirmation
claim_state=unconsumed
consumed=false
expires_at > now
```

to:

```text
status=resuming_auto_exact_confirmation
claim_state=resuming
consumed=true
claimed_at=<now>
claim_token=<bounded opaque token>
```

Persist the claim before releasing the lock or resuming work. Two concurrent
callbacks therefore yield one winner; the loser reads/renders the durable
current state and makes no prepare/provider/classifier/TTS/render/wallet call.
This is a logical compare-and-set over the existing JSON job snapshot under the
dedicated lock, not a new database or wallet primitive.

The winner calls the current prepare seam once with `require_auto_cast=True` in
cache-only resume mode. It may rehydrate only workspace artifacts whose
source/media/subtitle/selected-TTS-text hash, translated-selected-text hash when
applicable, timeline/sidecar hashes, exact count/components/total, receipt and
quote versions all match. It makes zero new ASR calls and zero new translation
calls. Missing, stale, mismatched, or expired receipt/cache fails closed instead
of retranscribing or retranslating. Only after cached prepare and receipt
validation may the gate continue; Task 5's wrapper then classifies/assigns and
delegates with the already-prepared closure, so the protected pipeline cannot
perform another preparation/provider call.

Cancel uses the same per-job lock and durable compare-and-set. It changes an
unclaimed receipt to expired/consumed, persists a terminal no-charge job using
the existing `failed_no_charge` terminal contract plus a cancellation reason and
`charge_status="not_charged"`, and only then permits normal terminal workspace
cleanup. Missing/stale/expired callbacks fail closed and never recreate a job or
workspace.

Write event-order tests with mocked ASR, existing translation, classifier, TTS,
render, balance read, `spend_fixed_credit_info`, delivery, and
`refund_charged_credit`:

- exact existing source-selected text: exact policy-selected quote → one
  confirmation → read-only balance guard → classifier/TTS/render success → one
  actual charge → delivery; ASR and translation counters remain zero;
- exact existing valid translated-selected text: exact policy-selected quote →
  one confirmation and the same downstream order; ASR and translation counters
  remain zero;
- existing source subtitle but missing selected translation: estimate/formula →
  text-preparation authorization → zero ASR and exactly one existing translation
  call → exact selected-text count/total → read-only guard → durable
  `awaiting_auto_exact_confirmation`; lane runner, classifier, TTS, render, and
  wallet counters remain zero;
- no valid source cache with source text selected: text-preparation authorization
  → exactly one ASR and zero translation → exact selected-text count/total →
  durable pause; all later-work counters remain zero;
- no valid source cache with translated text selected: text-preparation
  authorization → exactly one ASR then at most one existing translation call →
  exact selected-text count/total → durable pause; all later-work counters
  remain zero;
- count every case over exactly the final
  `resolve_subdub_dub_audio_policy(...)["tts_segments"]` cue text; source/output
  text not selected by policy must not affect the count;
- outer-runner interception persists `awaiting_auto_exact_confirmation` with an
  empty terminal state before either generic failure branch, keeps the workspace,
  and places awaiting/resuming in the active-workspace lifecycle;
- second handler after an in-process pause: exact-confirm callback → dedicated
  per-job lock → one durable compare-and-set claim → cached prepare with zero new
  ASR and zero new translation → receipt validation → classifier/TTS/render once
  → one actual charge → delivery;
- restart resume: clear in-memory `USER_PENDING` and pipeline-job caches, load the
  existing engine-job snapshot/workspace, claim it, then complete with zero new
  ASR/translation; no replacement job/workspace is created;
- two concurrent duplicate callbacks: exactly one claim reaches cached prepare;
  the loser is a read-only no-op. Sequential duplicate, stale job/session nonce,
  missing receipt, mismatched hash/version, and expired receipt also fail closed
  with zero provider/classifier/TTS/render/spend/refund/delivery calls;
- cancel while awaiting: atomically expire/consume the durable receipt,
  terminalize `failed_no_charge` with charged Xu zero, and allow cleanup only
  after terminalization; a later confirm cannot resume;
- post-preparation cancel or insufficient exact balance: stop before
  classifier/TTS/render, call neither `spend_fixed_credit_info` nor
  `refund_charged_credit`, and retain only the ASR/translation calls actually
  authorized by the selected-text policy;
- actual words lower than, equal to, or higher than the estimate: require the
  second confirmation whenever exact words were unknown at the first quote,
  even if component rounding happens to produce the same Xu amount;
- status refresh reads only the durable snapshot and performs no claim, prepare,
  gate, ASR, translation, classifier, TTS, render, balance, spend, refund, or
  delivery call; it cannot confirm or resume a receipt;
- successful render followed by insufficient one-shot charge: send no output
  and preserve the current no-deduction behavior;
- delivery exception, empty delivery, and partial delivery: render succeeds,
  `spend_fixed_credit_info` is called exactly once for the actual total before
  delivery, then the existing `refund_charged_credit` branch runs in its current
  order.

Retry and resume must not duplicate ASR, translation, classifier, TTS, render,
confirmation, charge, or refund. Do not add pre-render debit logic; do not modify
`spend_fixed_credit_info`, `refund_charged_credit`, wallet primitives, PayOS,
payment schema, or database schema. If these tests cannot pass, do not enable
Auto pricing and do not alter manual pricing.

After all Task 7 focused tests and protected comparators pass, atomically enable
the already-built Auto button, exact callback, and dispatch route in both lanes.
No user-reachable intermediate Task 6 route is allowed. This activation is code
within the same Task 7 change, not deployment or an ENV/config toggle.

- [ ] **Step 5: Run GREEN and protected pricing comparators**

```powershell
python -m pytest -q tests/test_p0_subdub_auto_word_pricing.py
python -m pytest -q tests/test_p0_subdub_per_speaker_auto_gender_cast.py -k "central_predicate or pricing or text_preparation or durable_receipt or concurrent_claim or restart_resume or stale_receipt or expired_receipt or cancel_receipt or pause_resume or cached_prepare or exact_confirmation or one_shot_charge or status_read_only or manual_mode or partial_pair"
python -m pytest -q tests/test_p0_pricing1_sync_voice_subtitle_dub_video_pricing_tables_invoices_checkout_only.py tests/test_p0_19b4_video_only_subtitle_translate_dub_flow_reset_pricing.py
```

- [ ] **Step 6: Commit the isolated pricing phase**

```powershell
git add -- services/subdub_auto_word_pricing.py bot.py services/pricing_guide_content.py tests/test_p0_subdub_auto_word_pricing.py tests/test_p0_subdub_per_speaker_auto_gender_cast.py
git commit -m "feat(subdub): charge exact Auto voice price after render"
```

### Task 8: Final review and protected verification

**Files:**
- Review every changed file from Tasks 4–7 against implementation diff base
  `2e0453058c54e4169e80ffd356079e5960ee4674`.
- The complete allowed diff is exactly:
  - `services/subdub_speaker_cast.py`
  - `services/subdub_blackboxes/auto_speaker.py`
  - `services/subdub_auto_word_pricing.py`
  - `services/pricing_guide_content.py`
  - `bot.py`
  - `tests/test_p0_subdub_per_speaker_auto_gender_cast.py`
  - `tests/test_p0_subdub_auto_word_pricing.py`
  - `tests/test_p0_i18n_video_subdub_native_contract.py`
  - `docs/superpowers/specs/2026-08-14-subdub-per-speaker-auto-gender-cast-design.md`
  - `docs/superpowers/plans/2026-08-14-subdub-per-speaker-auto-gender-cast.md`
- The five recorded PR613-compatible shared-engine paths are protected, not
  allowed changes.

- [ ] **Step 1: Inspect exact scope and stale claims**

```powershell
git status --short
git diff --name-status 2e0453058c54e4169e80ffd356079e5960ee4674..HEAD
git diff --check 2e0453058c54e4169e80ffd356079e5960ee4674..HEAD
$allowed = @(
  'services/subdub_speaker_cast.py',
  'services/subdub_blackboxes/auto_speaker.py',
  'services/subdub_auto_word_pricing.py',
  'services/pricing_guide_content.py',
  'bot.py',
  'tests/test_p0_subdub_per_speaker_auto_gender_cast.py',
  'tests/test_p0_subdub_auto_word_pricing.py',
  'tests/test_p0_i18n_video_subdub_native_contract.py',
  'docs/superpowers/specs/2026-08-14-subdub-per-speaker-auto-gender-cast-design.md',
  'docs/superpowers/plans/2026-08-14-subdub-per-speaker-auto-gender-cast.md'
)
$changed = @(
  git diff --name-only 2e0453058c54e4169e80ffd356079e5960ee4674..HEAD
  git diff --name-only
  git diff --cached --name-only
  git ls-files --others --exclude-standard
) | Sort-Object -Unique
$unexpected = @($changed | Where-Object { $_ -notin $allowed })
if ($unexpected.Count) { throw "unexpected changed paths: $($unexpected -join ', ')" }
rg -n "is_auto_speaker_state|post_prepare_gate|AUTO_EXACT_CONFIRMATION_REQUIRED|awaiting_auto_exact_confirmation|resuming_auto_exact_confirmation|persist_subtitle_dub_pipeline_job_snapshot|save_engine_async_job|AUTO_CAST_MANUAL_REQUIRED|run_auto_speaker|run_subdub_lane_blackbox|runner=subtitle_dub_product_pipeline.run_subdub_pipeline" bot.py services/subdub_blackboxes/auto_speaker.py tests/test_p0_subdub_per_speaker_auto_gender_cast.py tests/test_p0_subdub_auto_word_pricing.py
rg -n "MAX_AUTO_SPEAKER_LABELS|MAX_SPEAKER_VOICED_SECONDS|MAX_JOB_SAMPLE_SECONDS|CLASSIFIER_WALL_TIMEOUT_SECONDS|MIN_REGISTER_CONFIDENCE|AUTO_XU_PER_WORD|auto_exact_confirmation_state" services bot.py tests
```

Expected: the diff contains only declared Task 4–7 files plus the two canonical
planning documents explicitly listed above; `git diff --check` exits 0; every
new contract marker is present and superseded classifier, resource-cap,
fallback, assignment-order, and pricing comparators are absent from the changed
scope.
Confirm no provider adapter/order, ENV, credential, DB, PayOS, wallet primitive,
Video Edit, Logo/Watermark, or unrelated product file changed.

- [ ] **Step 2: Enforce protected blobs and the default behavior comparator**

Run the exact blob comparator against the PR613 implementation and planning
baseline:

```powershell
$protected = @(
  'services/subdub_blackboxes/__init__.py',
  'services/subdub_blackboxes/base.py',
  'services/subdub_blackboxes/dub_only.py',
  'services/subdub_blackboxes/subtitle_dub.py',
  'services/subtitle_dub_product_pipeline.py'
)
$expected = @{
  'services/subdub_blackboxes/__init__.py' = '22f06a3dac77764ca702a9572d54220df4547673'
  'services/subdub_blackboxes/base.py' = '6a87de96d0820a363ce8447be7fae51ec95bc679'
  'services/subdub_blackboxes/dub_only.py' = '12f641b243a950e5a250105a30adffb27082233e'
  'services/subdub_blackboxes/subtitle_dub.py' = '5531995d251dc1857d0f2a86ccf6ca75ed27b0cc'
  'services/subtitle_dub_product_pipeline.py' = '24f8b45b8944b674e4d79b649e084916959bb2fe'
}
foreach ($path in $protected) {
  $headBlob = git rev-parse "HEAD`:$path"
  $workingBlob = git hash-object -- $path
  if ($headBlob -ne $expected[$path]) { throw "protected HEAD blob changed: $path" }
  if ($workingBlob -ne $expected[$path]) { throw "protected working blob changed: $path" }
}
git diff --quiet -- $protected
if ($LASTEXITCODE -ne 0) { throw 'unstaged protected diff detected' }
git diff --cached --quiet -- $protected
if ($LASTEXITCODE -ne 0) { throw 'staged protected diff detected' }
git diff --quiet 00aff00871c61b4caefc2e165c1216cdbb2d7d63 HEAD -- $protected
if ($LASTEXITCODE -ne 0) { throw 'protected PR613 engine diff detected' }
git diff --quiet 2e0453058c54e4169e80ffd356079e5960ee4674 HEAD -- $protected
if ($LASTEXITCODE -ne 0) { throw 'protected planning-baseline diff detected' }
```

Then run the focused behavior comparator. It must cover exact Auto dispatch,
central-predicate reuse across all financial decisions, the exact `[True]`
versus `[False]` prepare-flag captures, all non-Auto/partial-pair cases,
text-preparation authorization, durable pause/two-invocation and restart cached
resume, concurrent durable claim, stale/missing/expired/cancel behavior,
event-loop responsiveness and cancellation cleanup from the initial shielded
worker await, original runner/dependency identities, dual exact
identity-joins into `source_segments` and `output_segments`, exact
policy-selected-list validation, the canonical same-lane failure mapping, the
real compatibility scalar, full prevalidation, deterministic provider
aggregation, and sequential per-cue calls:

```powershell
python -m pytest -q tests/test_p0_subdub_per_speaker_auto_gender_cast.py -k "central_predicate or exact_pair or prepare_flag or text_preparation or durable_receipt or concurrent_claim or restart_resume or stale_receipt or expired_receipt or cancel_receipt or pause_resume or cached_prepare or event_loop or cancellation or default_blackbox or identity_join or selected_list or manual_failure_mapping or compatibility_scalar or provider_aggregation or sequential_per_cue"
python -m pytest -q tests/test_p0_subdub_live14_blackbox_lane_language_contract.py
```

Expected: Auto is used only for the exact pair. Every other state makes exactly
the current lane-blackbox call with
`runner=subtitle_dub_product_pipeline.run_subdub_pipeline`; no default module or
shared pipeline behavior changes. The exact pair prepares once with `True`;
every non-exact state prepares once with `False`. Both prepared segment lists
are identity-joined by exact canonical identity, and whichever list the
protected policy selects is completely validated before TTS. A pending exact
confirmation never enters the lane runner. The outer runner persists the
nonterminal durable receipt before generic failure mapping, awaiting/resuming
protect the workspace, and resume uses cached prepare data with zero new ASR and
zero new translation.

### Current Owner verification gate

The Owner authorizes only the named focused SubDub tests below, the changed
module compile/AST checks, protected blob checks, and static diff/scope scans.
Full `python -m pytest -q` and unrelated
`python -m py_compile local_worker.py` are intentionally `NOT_RUN`. Record exact
commands, exit codes, and counts for every focused check; report baseline and
branch failures separately. This evidence can support focused local TEST PASS
only. It must not be reported as full-repository regression PASS, deployment,
provider readiness, or LIVE PASS. Any paid provider smoke, Telegram live QA,
deployment, ENV change, or wallet mutation requires separate current Owner
approval.

- [ ] **Step 3: Run the focused feature suite**

```powershell
python -m pytest -q tests/test_p0_subdub_per_speaker_auto_gender_cast.py tests/test_p0_subdub_auto_word_pricing.py tests/test_p0_subdub_live25_canonical_mp4_smoke.py tests/test_p0_i18n_video_subdub_native_contract.py
```

- [ ] **Step 4: Run surrounding SubDub comparators**

```powershell
python -m pytest -q tests/test_p0_subdub_tts_audio_truth_sequential.py tests/test_p0_subdub_live14_blackbox_lane_language_contract.py tests/test_p0_subdub_long_media_no_speech_recovery.py tests/test_p0_subdub_live10_tts_checkpoint_resume.py tests/test_p0_19i_final_subdub_voice_lock_direct_dub_shared_status.py tests/test_p0_pricing1_sync_voice_subtitle_dub_video_pricing_tables_invoices_checkout_only.py tests/test_p0_19b4_video_only_subtitle_translate_dub_flow_reset_pricing.py
```

- [ ] **Step 5: Compile changed modules proportionately**

```powershell
python -m py_compile services/subdub_speaker_cast.py services/subdub_blackboxes/auto_speaker.py services/subdub_auto_word_pricing.py services/pricing_guide_content.py
```

Run `python -m py_compile bot.py` once with the established 60-second boundary.
If it times out, report `BOT_PY_COMPILE=TIMEOUT_AFTER_60S`, verify no process
remains, and run an AST parse of the changed `bot.py` source as the truthful
secondary check; never relabel a timeout as PASS.

- [ ] **Step 6: Review failure gates and report**

Confirm with mocks that the 17th label, classifier ambiguity/noise/insufficient
data/exact 30.0-second whole-job timeout, confidence below 0.75, invalid or
exhausted voice pool, and missing per-cue assignment all return manual choice
before TTS. Confirm the caller passes one absolute classifier deadline, provider
calls are zero in preflight failures, the event loop remains responsive,
cancellation starts with `wait_for(shield(worker), remaining)`, waits for
cooperative worker exit before PCM deletion, raw
PCM/embeddings are absent from persistence, and no live catalog lookup or
all-voices-live claim exists.

Confirm Task 4 ends after gate/classification with zero assignment, annotation,
resolve/synthesize failure slot, or lane delegation; Task 5 alone adds those
steps. Confirm the Auto wrapper calls current confirmed diarized prepare before
the gate, authorizes ASR at most once and translation at most once only for
missing policy-selected translated text, counts exactly the selected TTS cues,
pauses durably before classifier/lane delegation, and resumes from matching
cached workspace artifacts with zero new ASR/translation. Confirm the
already-prepared closure prevents a second prepare/provider call, the first
validated assigned per-cue voice is used
only for the shared scalar guard, all cues are prevalidated before TTS, chunks
remain ordered, and provider aggregation returns same/`mixed`/empty internally.
Confirm no ASR, TTS, timeline, QC, mux, delivery, or charge implementation was
copied into the Auto module.

Confirm only the central exact predicate controls dispatch and every Auto
financial decision. Confirm structured manual-required mapping clears bounded
Auto computed fields and returns both lanes to their own native voice screen,
while downstream provider/render/mux/charge/delivery failures retain current
handling.

Confirm Task 7 remains after Tasks 4–6 and proves the exact quote/second-confirm
durable receipt gates, outer-runner control interception, per-job lock/CAS,
restart resume and stale/missing/expired/cancel behavior, zero wallet mutation
on cancel/insufficient balance, one
post-render `spend_fixed_credit_info` actual charge, and the unchanged
delivery-failure `refund_charged_credit` ordering. Confirm Task 6 stayed
user-unreachable until atomic Task 7 activation. No wallet helper or
charge-order change is allowed.

- [ ] **Step 7: Commit test-only final adjustments if needed**

```powershell
git add -- tests/test_p0_subdub_per_speaker_auto_gender_cast.py tests/test_p0_subdub_auto_word_pricing.py tests/test_p0_i18n_video_subdub_native_contract.py
git commit -m "test(subdub): verify fail-closed Auto voice flow"
```

Skip this commit when no test-only adjustment is needed. No push, PR, merge,
deploy, provider smoke, Telegram live action, ENV change, credential change, or
direct wallet/payment mutation is authorized by this plan.
