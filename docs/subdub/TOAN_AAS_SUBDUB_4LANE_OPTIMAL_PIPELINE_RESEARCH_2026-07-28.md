# TOAN AAS - NGHIEN CUU QUY TRINH TOI UU CHO 4 LANE SUBDUB

> Status: research reference for P1 SubDub Pipeline V2 shadow/replay.
>
> Normative contract: `TOAN_AAS_SUBDUB_PIPELINEV2_SHARED_DAG_DESIGN_2026-07-28.md`.
> When this research and the approved design differ, the approved design and
> Amendment A take precedence.
>
> Source SHA-256:
> `CF02803ED873EA9C8A5ABBD7DC35630150F4BF9CFAC762CE2497B2922E9C58A6`.

## Project Reconciliation

The research supports the approved Shared Semantic Master DAG. The following
project locks make its recommendations precise for the current phase:

1. V2 stays disabled and disconnected from public callbacks. V1 remains the
   production and rollback path.
2. Shadow/replay uses legal offline fixtures only: provider calls, wallet
   mutations, customer deliveries and production traffic all remain zero.
3. The owner fidelity dubbing profile keeps provider speed and post-tempo at
   exactly `1.0`. It does not use even a small time-stretch fallback. An
   utterance that does not fit becomes `WAITING_REVIEW` or `FAIL`.
4. No paid ASR, translation, TTS, separation or render submit is retried
   automatically. An uncertain submit becomes `ACCEPTANCE_UNKNOWN`; recovery
   may only inspect, poll a stored task ID or retrieve an existing artifact.
5. Translated subtitle cues retain the source cue timing exactly. Subtitle
   adaptation may condense text and choose line breaks, but cannot create a
   replacement translated timeline.
6. Combo derives `subtitle_copy` and `dub_script` from one translation master
   and reaches exactly one final compose/mux boundary.
7. The product limits remain 500 MiB input/output, 3,600 seconds, 12 sequential
   internal parts and one final customer MP4.
8. No microservice, queue, worker change, DB migration or production renderer
   change is part of this Phase 2 implementation.

## Conclusion

The recommended architecture is a **Shared Semantic Master DAG**:

```text
Input
-> Ingest/ffprobe
-> Audio master + ASR derivative
-> VAD preserving the original timeline
-> ASR
-> Forced alignment
-> Optional diarization
-> Source semantic master
   |-> Lane 1: source subtitle
   |-> Lane 2: translated subtitle
   |-> Lane 3: translated dubbing
   `-> Lane 4: translated subtitle + dubbing combo
```

Four independent pipelines would duplicate ASR/alignment and make cross-lane
consistency harder. One video should produce one source master; lanes 2-4
should consume one `translation_master` for the same target/config.

## Corrections To Earlier Approaches

1. VAD identifies speech regions; it never removes silence or compacts the
   canonical timeline.
2. Subtitle limits are selected from a versioned language/platform profile,
   not one global constant.
3. Loudness comes from a delivery profile. `-23 LUFS` is an explicit broadcast
   target, not a universal target.
4. Provider submit is never an automatic retry. Poll and retrieval can reuse a
   stored task ID.
5. Combo produces two text artifacts from one meaning master:
   `subtitle_copy` for reading and `dub_script` for natural duration-aware
   speech.

## Architecture Options

| Option | Advantages | Disadvantages | Decision |
| --- | --- | --- | --- |
| Independent lane pipelines | Fast initial implementation | Repeated ASR/translation, drift | Reject |
| Provider end-to-end | Less local code | Lock-in, weak QC/cost control | Manual only |
| Microservices + queue | Scalable | Operationally complex | Long-term only |
| Shared DAG + durable artifacts | Reuse, traceability, QC | Requires contracts | Recommended |

## Shared Preflight

### S0 - Request Contract

Persist:

```text
job_id
lane
source/target language
subtitle profile
audio delivery profile
voice policy
glossary version
explicit confirmation receipt
runtime SHA
```

### S1 - Ingest

Validate:

```text
checksum
container
duration
video/audio/subtitle streams
frame rate
rotation
full-decode policy
```

Source-text priority:

```text
validated owner timed subtitle
-> valid embedded subtitle
-> explicitly eligible visual OCR
-> ASR
```

### S2 - Audio

Keep two artifacts:

```text
audio_master.wav      # quality source for mix/master
asr_input.wav         # provider-specific ASR derivative
```

A mono 16 kHz ASR derivative must not become the final mix source.

### S3 - VAD

Create `speech_regions.json` with local and original offsets. Do not physically
remove silence from the canonical source.

### S4 - ASR/Alignment

Alignment truth is explicit:

```text
word_aligned
segment_timed
alignment_unavailable
```

### S5 - Diarization

Diarization is required only when multi-speaker voice casting needs it. Low
confidence uses a narrator policy or review; it must not guess identity.

### S6 - Source Semantic Master

Each segment carries:

```text
segment_id, start, end, speaker_id
source_text_raw, source_text_normalized
word timestamps, confidence
pause_before/after
proper nouns, numbers
emotion/emphasis hints
```

## Lane 1 - Source Subtitle

```text
source master
-> semantic segmentation
-> source-locked timing
-> language/platform profile
-> QC
-> SRT/VTT/ASS
-> optional final MP4
```

Cue decisions use semantic boundaries, shot/cut, speaker changes, readability,
duration and gap repair. The initial Vietnamese profile is:

```text
max_lines = 2
max_characters_per_line = 42
minimum_event_duration = 5/6 second
maximum_event_duration = 7 seconds
```

CPS has target, warning and hard limits. It is not one system-wide constant.

Subtitle QC covers:

```text
overlap and monotonic timing
duration
CPS/CPL
semantic line breaks
safe area
speech coverage
low-confidence flags
real rendered glyphs
```

## Lane 2 - Translated Subtitle

Do not translate isolated cues without context:

```text
source master
-> scene/context batches
-> faithful translation master
-> glossary/name/number QC
-> subtitle condensation
-> profile line breaking
-> source-locked cue timing
-> subtitle QC
```

The two phases are distinct:

1. Semantic translation preserves meaning, terminology and tone.
2. Subtitle adaptation condenses and line-breaks for the existing cue window.

QC covers untranslated or unexpectedly unchanged text, glossary violations,
proper nouns, numbers/dates/units, missing/extra segments, semantic coverage
and target-language CPS/CPL.

## Lane 3 - Translated Dubbing

```text
source master
-> translation master
-> dub-script adaptation
-> voice casting
-> duration prediction
-> sequential TTS per segment/transport fragment
-> duration fit
-> M&E policy
-> mix/master
-> one mux
-> AV QC
```

Dub-script adaptation balances meaning, natural speech, emphasis/emotion,
pause structure, target duration and visible-mouth priority.

Owner-profile duration fit:

1. Generate duration-aware candidates.
2. Predict duration.
3. Select the best meaning-preserving candidate.
4. Rewrite when needed.
5. Synthesize at speed `1.0`.
6. Measure real output duration.
7. Accept only a complete utterance that ends within its source window.

There is no clipping, aggressive speed-up or overlap fallback.

M&E priority:

```text
owner-provided M&E
-> embedded M&E
-> source separation with artifact QC
-> original track with voice-over ducking
```

Source separation is never called clean without QC for vocal bleed, music
damage, phasing, missing ambience and pumping.

Mix/master includes gain staging, sidechain ducking, ambience preservation,
crossfades, limiter, measured loudness normalization and true-peak checks from
the selected delivery profile.

## Lane 4 - Combo

```text
source master
-> one translation master
   |-> subtitle_copy
   `-> dub_script
-> sequential TTS and mix
-> one subtitle artifact
-> exactly one final compose/mux
-> combo semantic QC
```

Do not translate twice, use subtitle copy directly as the dub script, or render
two complete videos and merge them afterward.

Combo QC verifies meaning, names, numbers, terms, speaker mapping and timing.
Subtitle and spoken wording may differ, but their stable meaning IDs and intent
must agree.

## State, Artifact And Retry

Stage states:

```text
PENDING
RUNNING
PASS
FAIL
WAITING_REVIEW
CANCELLED
```

Every stage records input/output fingerprints, configuration, runtime SHA,
safe error category, timestamps and an admin-only provider reference when one
exists.

Three idempotency levels protect:

```text
request/job
stage/artifact
side-effect/transport
```

Automatic operations are limited to persisted artifact reads and safe
poll/retrieval of an existing task. Paid submit is never automatic. Uncertain
acceptance becomes `ACCEPTANCE_UNKNOWN` and blocks replacement submit.

## Delivery And Billing

The production contract is:

```text
validated final output
-> ffprobe/full decode
-> real Telegram delivery accepted
-> persist delivery receipt
-> charge exactly once
-> final report exactly once
```

No MP4 means truthful terminal failure and zero charge. HTTP 200, a task ID or
an output URL is not success by itself. Shadow/replay stops before customer
delivery and makes zero wallet mutations.

## Safe Upgrade Path

The live V1 lanes are not refactored directly:

```text
V2 shadow/replay with zero provider calls
-> admin preview
-> one owner-approved canary per lane
-> 5% -> 25% -> 50% -> 100%
```

V1 remains available until V2 passes every approved lane and rollout gate.

## Final Formula

```text
ONE SOURCE MASTER
ONE TRANSLATION MASTER
TWO COMBO COPIES
STAGE ARTIFACTS
EXPLICIT PROVIDERS
NO AUTOMATIC PAID RESUBMIT
CONFIGURABLE QC PROFILES
ONE FINAL COMPOSE
DELIVERY-FIRST BILLING
```
