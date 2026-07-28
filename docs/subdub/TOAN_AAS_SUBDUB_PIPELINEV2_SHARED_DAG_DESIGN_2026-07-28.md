# TOAN AAS SubDub Pipeline V2 Shared DAG Design

Status: `OWNER_REVIEW_REQUIRED`

Date: 2026-07-28

Repository: `manhtoangreensky-wq/bot`

Supporting research:
`TOAN_AAS_SUBDUB_4LANE_OPTIMAL_PIPELINE_RESEARCH_2026-07-28.md`

Design base SHA: `0cefd4be1e53b4dcfe098265300fe89a266fa120`

Design branch: `hotfix/p0-subdub-real-product-gate-recovery`

## 1. Decision And Scope

Owner truth for this design phase:

- The four public V1 SubDub lanes are treated as `LIVE PASS`.
- V1 public callbacks, routing, UI/UX, renderer and worker ownership are frozen.
- This phase is inventory and design only.
- No provider call, customer delivery, production traffic, wallet mutation, deploy or merge is allowed.
- Phase 2 implementation must not start before owner approval of this document.

The V2 target is a disabled, admin-only shared DAG:

```text
one source ingest
-> one source semantic master
-> one translation master per target language
-> lane-specific derived artifacts
-> one validated final MP4
-> delivery receipt
-> charge once
```

Four lane contracts:

1. `source_subtitle`: source speech/subtitles -> source subtitle copy -> MP4.
2. `translated_subtitle`: source semantic master -> translation master -> subtitle copy -> MP4.
3. `translated_dub`: source semantic master -> translation master -> dub script -> TTS/mix -> MP4.
4. `translated_combo`: one translation master -> subtitle copy + dub copy -> one final render/mux -> MP4.

Hard locks for all V2 work:

- No public callback or visible UI/UX change.
- No Product Video change.
- No pricing, PayOS, wallet/Xu, webhook or DB schema change.
- No production renderer or worker ownership change.
- No startup smoke, cron provider call, automatic paid retry or automatic paid fallback.
- A status/readiness/refresh/recovery operation must create zero provider tasks.
- V1 remains the rollback path until all four V2 lanes pass approved canaries.

## 2. Phase 0 Inventory: Current V1

### 2.1 Public Entry And Lane Ownership

The four public choices are declared together in `bot.py:202315-202333`:

| Public lane | Mode | Callback evidence | Current lane wrapper | Default video output |
| --- | --- | --- | --- | --- |
| Tạo phụ đề tự động | `subtitle_create` | `bot.py:202322` | `subtitle_only` | `burn` |
| Dịch phụ đề video | `subtitle_translate` | `bot.py:202323` | `subtitle_only` | `burn` |
| Lồng tiếng video | `dub` | `bot.py:202326` | `dub_only` | `video` |
| Phụ đề + Lồng tiếng | `subtitle_plus_dub` | `bot.py:202327` | `subtitle_dub` | `video_subtitle` |

Mode ownership and default outputs are defined in
`services/subtitle_dub_product_pipeline.py:12-20` and
`services/subtitle_dub_product_pipeline.py:57-76`.
The lane boundary checks the mode before delegating in
`services/subdub_blackboxes/__init__.py:17-38` and
`services/subdub_blackboxes/base.py:120-147`.

The final confirmation buttons all converge on `videodub|final` in
`bot.py:204746-204817`. Upload and callback entry points are
`bot.py:216102` and `bot.py:217198`.

### 2.2 Shared V1 Execution Path

The public execution chain is:

```text
public callback
-> execute_video_dubbing_pipeline
-> acquire job + create workspace
-> _execute_video_dubbing_pipeline_core
-> run_subdub_lane_blackbox
-> subtitle_dub_product_pipeline.run_subdub_pipeline
-> process_subtitle_dub_job
-> validate artifact
-> Telegram delivery
-> persist terminal state
```

Evidence:

- Persisted wrapper and dedupe: `bot.py:215019-215083`.
- Core executor and input gate: `bot.py:213505-213690`.
- Lane dispatch: `bot.py:214051-214076`.
- Shared lane core: `services/subtitle_dub_product_pipeline.py:146-166`.
- Delivery: `bot.py:214530-214627`.
- Terminal persistence: `bot.py:214680-214910` and `bot.py:215128-215295`.

### 2.3 Current Stages By Lane

The canonical public stage lists are in `bot.py:206398-206443`.

#### Lane 1: source subtitle

```text
received_video
-> transcribing
-> auto_subtitle_ready
-> rendering_subtitle
-> checking_file
-> delivering
```

Evidence: `bot.py:206435-206441`.

The source resolver first accepts a supplied/embedded timed subtitle and
otherwise uses media ASR: `bot.py:212438-212540`. Source segments are converted
to SRT and rendered through the shared renderer: `bot.py:213283-213391` and
`bot.py:212543-212695`.

#### Lane 2: translated subtitle

```text
received_video
-> reading_source_captions
-> translating_subtitle
-> rendering_subtitle
-> checking_file
-> delivering
```

Evidence: `bot.py:206403-206410`.

Translation is one call per source cue and copies source cue timing back onto
the translated cue: `bot.py:212072-212120`. The preparation path validates cue
count, index, start and end equality before rendering: `bot.py:213397-213470`.

#### Lane 3: translated dubbing

```text
received_video
-> extracting_audio
-> transcribing
-> translating
-> choosing_voice
-> generating_voice
-> muxing_dub_video
-> checking_file
-> delivering
```

Evidence: `bot.py:206412-206421`.

TTS is awaited cue by cue in `bot.py:213057-213118`. The current timeline
builder delays each cue to its source start and trims it at the next cue
boundary in `bot.py:213120-213189`. Audio/video muxing and optional original
audio mixing are in `bot.py:212614-212679`.

#### Lane 4: translated subtitle + dubbing

```text
received_video
-> extracting_audio
-> transcribing
-> translating
-> subtitle_translation_ready
-> choosing_voice
-> generating_voice
-> muxing_subtitle_dub_video
-> checking_file
-> delivering
```

Evidence: `bot.py:206423-206433`.

The combo uses the same `output_segments` for subtitle output and TTS input:
`services/subtitle_dub_product_pipeline.py:219-245` and
`services/subtitle_dub_product_pipeline.py:274-334`. It renders subtitle and
dub audio together in one shared render call at
`services/subtitle_dub_product_pipeline.py:401-430`.

### 2.4 Source Acquisition, ASR And Timing

Current source priority is:

```text
explicit subtitle artifact
-> subtitle text file
-> embedded subtitle stream
-> optional visual hardsub OCR
-> ASR
```

Evidence:

- Explicit/session subtitle: `bot.py:213305-213350`.
- Embedded subtitle extraction: `bot.py:211400-211418`.
- Embedded/OCR/ASR resolver: `bot.py:212438-212540`.
- Media ASR: `bot.py:212138-212436`.

For long ASR input, V1 uses 10-30 second chunks and maps chunk-local timestamps
onto the original absolute timeline:

- Chunk plan: `bot.py:207585-207637`.
- Chunk execution: `bot.py:212219-212308`.
- Absolute offset conversion:
  `services/subdub_long_media.py:270-304`.
- Global sort and final duration:
  `services/subdub_long_media.py:459-477`.

This absolute-offset behavior is correct and should be reused by V2.

Alignment truth is not currently a versioned artifact. V1 may use provider
segments or estimated transcript distribution and exposes that distinction as
`subtitle_timing_source` in `bot.py:212408-212435`, but it does not enforce the
V2 enum `word_aligned | segment_timed | alignment_unavailable`.

### 2.5 Repeated Work

V1 shares Python code, but not a durable cross-lane semantic artifact.

- Every new lane job enters `video_dubbing_prepare_subtitles` again at
  `bot.py:213283-213504`.
- Source subtitle and translated subtitle references are stored in
  `USER_PENDING` and expire with the session TTL at `bot.py:201643-201662`.
- Translation cache matching is bound to the current state, target language and
  source subtitle hash at `bot.py:201664-201688`.
- The compatibility pipeline at `bot.py:212697-212793` also performs its own
  ASR, translation and TTS chain.
- Long projects process each part through the lane pipeline in sequence at
  `services/subdub_long_media.py:481-563`.

Therefore, the same source sent through multiple lanes can repeat ASR and lanes
2-4 can repeat translation. There is no content-addressed, versioned source
master reused across independent jobs.

### 2.6 Current Artifacts And Persistence

The V1 workspace shape is declared at `bot.py:213523-213530`:

```text
source
audio
subtitles[]
translated_subtitles[]
dub_audio
final_mp4
```

Current storage layers:

- Session text artifacts in `USER_PENDING`: `bot.py:201649-201662`.
- Per-job temporary workspace: `bot.py:208451-208458`.
- Binary artifact writer: `bot.py:208556-208567`.
- Workspace manifest: `bot.py:215090-215127`.
- Subtitle/translation/dub asset records: `bot.py:214441-214529`.
- Engine async snapshot: `bot.py:208218-208268` and
  `bot.py:214703-214910`.
- Successful workspaces are cleaned in `bot.py:215318-215320`.

Gaps for V2:

- No schema version per stage artifact.
- No input/output fingerprint per stage.
- No stable `source_id`/`meaning_id` across all four lanes.
- No durable stage-level idempotency claim.
- Provider metadata and product artifacts are mixed in large job payloads.
- A successful workspace can be removed before it is useful for replay.

### 2.7 Job Identity, Recovery And Retry

Job identity:

- Job key includes user, chat, source and active flow:
  `bot.py:207780-207785`.
- A local job ID is generated and the job is acquired once:
  `bot.py:208112-208176`.
- Duplicate in-memory running/terminal jobs are not resubmitted:
  `bot.py:208115-208125`.

Recovery:

- Updates are persisted through the existing engine async store:
  `bot.py:208178-208268`.
- Status lookup prefers persisted terminal truth over memory after restart:
  `bot.py:8060-8124`.
- A late wrapper exception can recover an already delivered result:
  `bot.py:215297-215315`.

Current limitation: `persist_subtitle_dub_pipeline_job_snapshot` synthesizes a
job-level provider task ID (`subdub:<job_id>`) at `bot.py:208239`. It is not a
stage-specific paid provider task registry, so restart cannot safely resume an
uncertain ASR/translation/TTS submit from the exact stored task ID.

Current retry behavior:

| Operation | V1 behavior | Evidence |
| --- | --- | --- |
| Telegram download | Up to configured retries with backoff | `bot.py:211295-211339` |
| ASR long chunks | Sequential chunk processing | `bot.py:212219-212308` |
| Translation | One call per cue; missing result marks incomplete | `bot.py:212082-212120` |
| TTS | One awaited call per cue; no stage claim | `bot.py:213073-213115` |
| Delivery | Original payload, then optional local compression | `bot.py:211060-211077` |
| Duplicate final delivery | Delivery lock and output-sent guard | `bot.py:207056-207084`, `bot.py:214535-214558` |

V1 does not provide the full V2 guarantee that a restart can only poll/retrieve
an already accepted provider task and can never create a replacement paid task.

### 2.8 Status And Terminal Truth

The public stage percentages are declared in `bot.py:206120-206148`. Terminal
state and completed-step calculation are in `bot.py:206201-206233`.

The public panel is rendered from canonical product progress at
`bot.py:206553-206573`. Terminal delivery is persisted before later panel or
metadata updates at `bot.py:214617-214627`, which is the correct terminal
boundary to preserve.

### 2.9 Current Delivery And Billing Order

V1 validates the generated MP4 before delivery at `bot.py:214281-214294` and
again at the delivery boundary in `bot.py:210976-210998`.

However, V1 currently calculates and charges at `bot.py:214413-214428`, then
delivers at `bot.py:214560-214627`. Delivery failure triggers refunds at
`bot.py:214628-214679`.

This is not the requested V2 order. V2 must use:

```text
validate
-> deliver
-> persist delivery receipt
-> claim charge idempotency key
-> charge once
-> emit final report once
```

### 2.10 Subtitle, Unicode And Audio Profiles

V1 subtitle style presets are in `bot.py:209528-209617`. Cue wrapping supports
42 characters per line and two lines at `bot.py:211864-211882`. The canonical
cue helper preserves NFC text and stable cue IDs in
`services/subdub_canonical_cues.py:61-125`; translated cue wrapping and stable
timing are in `services/subdub_canonical_cues.py:374-445`.

V1 also resolves a real font and blocks missing glyph coverage before render:
`bot.py:210221-210230` and `bot.py:212590-212607`.

The subtitle settings are still renderer-oriented presets, not versioned
language/platform readability profiles containing CPL, CPS, duration and gap
rules.

Audio normalization currently uses one configured loudness target with default
`-16 LUFS`: `bot.py:2176-2183` and `bot.py:213191-213230`. It is not selected
from a versioned delivery profile. Original-audio preservation is explicit in
the render mix at `bot.py:212627-212655` and must remain driven by the user's
existing V1 choice.

### 2.11 Current MP4 QC And Long-Video Gap

V1 MP4 validation checks bytes, MP4 structure, streams and duration coverage in
`bot.py:210732-210793`. It does not prove lane semantics, translated text
quality, subtitle readability on rendered pixels, speech completeness, voice
overlap, original-audio selection or combo consistency.

V1 long-project policy already supports 12 x 300-second parts and a 3600-second
ceiling: `services/subdub_long_media.py:30-73`. It processes and delivers parts
one by one: `services/subdub_long_media.py:481-563`. It does not concatenate
those parts into one final customer MP4.

Current input limits are transport-aware but default to 300 MB on the local Bot
API path: `bot.py:2097-2105`. The effective input cap is the minimum of product
and transport limits: `bot.py:207566-207572`.

## 3. Phase 1 Design: Shared Semantic Master DAG

### 3.1 DAG

```text
S0 request_contract
  -> S1 ingest_probe
  -> S2 audio_master + asr_input
  -> S3 speech_regions (VAD, absolute offsets)
  -> S4 ASR + alignment truth
  -> S5 optional diarization
  -> S6 source_semantic_master
       |-> L1 source subtitle adaptation -> subtitle QC -> render
       |-> T1 translation_master(target, glossary, context)
            |-> L2 subtitle_copy -> subtitle QC -> render
            |-> L3 dub_script -> voice_cast -> duration fit -> TTS -> M&E/mix -> mux
            |-> L4 subtitle_copy + dub_script -> consistency QC -> one render/mux
  -> final media QC
  -> delivery
  -> delivery_receipt
  -> charge once
  -> final report once
```

No downstream node may call ASR again when a valid source master exists. No
lane 2-4 node may call translation again when a valid translation master for
the same source, target, glossary and policy exists.

### 3.2 Stable Identity

Identifiers:

- `source_id`: SHA-256 of canonical media identity.
- `speech_region_id`: deterministic from source ID and absolute region bounds.
- `segment_id`: deterministic from source ID, source index, absolute start/end
  and normalized source text.
- `meaning_id`: deterministic from translation master ID and `segment_id`.
- `derived_id`: deterministic from upstream meaning/source IDs and profile
  fingerprint.
- `artifact_id`: `<schema_name>:<schema_version>:<output_fingerprint>`.

Rules:

- Every downstream record retains `source_id` and `segment_id`.
- Translation records add exactly one `meaning_id` per `segment_id`.
- Subtitle and dub copies share `meaning_id` but may have different text.
- A translated subtitle cue keeps the canonical source start/end unchanged.
- If a future adaptation must merge source units, it stores `source_ids[]` and
  must not silently replace the canonical source timeline. V2 initial rollout
  does not merge translated cues.

### 3.3 Fingerprints

All fingerprints use SHA-256 over deterministic UTF-8 JSON with sorted keys.
Secrets, tokens, signed URLs and raw provider responses are excluded.

```text
source_fingerprint = sha256(
  media_bytes_sha256 + duration_ms + stream_manifest + rotation
)

stage_input_fingerprint = sha256(
  upstream_output_fingerprints + stage_name + schema_version
  + config_fingerprint + runtime_sha
)

config_fingerprint = sha256(
  source_language + target_language + glossary_version
  + subtitle_profile_version + audio_profile_version
  + voice_policy_version + alignment_policy_version
)

stage_output_fingerprint = sha256(
  canonical_artifact_without_admin_metadata
)
```

An artifact can be reused only when schema name/version, input fingerprint,
config fingerprint and QC `PASS` all match.

### 3.4 Artifact State Machine

Allowed stage states:

```text
PENDING
RUNNING
PASS
FAIL
WAITING_REVIEW
CANCELLED
```

`PASS` requires all of the following:

- The expected artifact exists and has non-zero bytes where applicable.
- JSON validates against the declared schema version.
- Its output fingerprint matches the stored fingerprint.
- Every blocking QC check passes.
- A provider HTTP 200, task ID, file ID or output URL alone is never sufficient.

Stage idempotency key:

```text
sha256(job_id + stage_name + segment_id_or_global + config_fingerprint)
```

The stage registry must atomically claim this key before a paid submit. A second
confirm returns the existing stage/job. It never creates a second provider
task.

Phase 2 must persist the registry inside the existing engine async JSON/result
storage or another already approved artifact store. It must not add a DB schema
migration. Public routing remains disconnected from this registry.

## 4. Versioned JSON Contracts

All seven contracts start at schema version `1.0.0`. Additive compatible fields
increment the minor version; renamed/removed fields or changed invariants
increment the major version.

### 4.1 `source_semantic_master.json`

```json
{
  "schema_name": "source_semantic_master",
  "schema_version": "1.0.0",
  "artifact_id": "source_semantic_master:1.0.0:<sha256>",
  "job_id": "<internal-job-id>",
  "source_id": "src_<sha256>",
  "source_fingerprint": "<sha256>",
  "request_contract_fingerprint": "<sha256>",
  "media": {
    "container": "mp4",
    "duration_ms": 0,
    "width": 0,
    "height": 0,
    "frame_rate": "0/1",
    "rotation": 0,
    "video_stream_present": true,
    "audio_streams": [],
    "embedded_subtitle_streams": [],
    "input_size_bytes": 0
  },
  "source_selection": {
    "selected": "user_timed_subtitle|embedded_subtitle|validated_visual_ocr|asr",
    "reason": "<safe-enum>",
    "timed_source_validated": true
  },
  "alignment_truth": "word_aligned|segment_timed|alignment_unavailable",
  "speech_regions": [
    {
      "speech_region_id": "region_0001_<sha256>",
      "local_start_ms": 0,
      "local_end_ms": 0,
      "original_start_ms": 0,
      "original_end_ms": 0
    }
  ],
  "segments": [
    {
      "segment_id": "seg_0001_<sha256>",
      "source_index": 1,
      "start_ms": 0,
      "end_ms": 0,
      "speaker_id": "speaker_01",
      "source_text_raw": "",
      "source_text_normalized": "",
      "words": [],
      "confidence": 0.0,
      "pause_before_ms": 0,
      "pause_after_ms": 0,
      "proper_nouns": [],
      "numbers": [],
      "emotion": "neutral"
    }
  ],
  "qc_summary": {
    "status": "PASS",
    "blocking_failures": [],
    "warnings": []
  },
  "admin_provenance_ref": "admin_provider_metadata:<sha256>",
  "created_at": "<utc-iso8601>",
  "retention_class": "subdub_semantic_72h"
}
```

Invariants:

- `start_ms`/`end_ms` are absolute offsets in the original video.
- VAD never compacts silence or creates a shortened timeline.
- `word_aligned` is legal only when word timing artifacts exist and pass QC.
- Segments are monotonic and non-negative; overlap is explicit, not hidden.

### 4.2 `translation_master.json`

```json
{
  "schema_name": "translation_master",
  "schema_version": "1.0.0",
  "artifact_id": "translation_master:1.0.0:<sha256>",
  "source_master_artifact_id": "source_semantic_master:1.0.0:<sha256>",
  "source_id": "src_<sha256>",
  "source_language": "auto",
  "target_language": "vi",
  "translation_policy_version": "semantic_translation_v1",
  "glossary_version": "none|<version>",
  "context_fingerprint": "<sha256>",
  "entries": [
    {
      "segment_id": "seg_0001_<sha256>",
      "meaning_id": "meaning_0001_<sha256>",
      "source_text": "",
      "semantic_translation": "",
      "proper_noun_checks": [],
      "number_checks": [],
      "glossary_checks": [],
      "translation_status": "PASS"
    }
  ],
  "qc_summary": {
    "status": "PASS",
    "missing_segment_ids": [],
    "extra_segment_ids": [],
    "name_failures": [],
    "number_failures": [],
    "glossary_failures": []
  },
  "admin_provenance_ref": "admin_provider_metadata:<sha256>",
  "input_fingerprint": "<sha256>",
  "output_fingerprint": "<sha256>"
}
```

This artifact contains semantic translation, not display line breaks and not a
final spoken script. There is exactly one valid translation master for a given
source/config fingerprint.

### 4.3 `subtitle_copy.json`

```json
{
  "schema_name": "subtitle_copy",
  "schema_version": "1.0.0",
  "artifact_id": "subtitle_copy:1.0.0:<sha256>",
  "source_master_artifact_id": "source_semantic_master:1.0.0:<sha256>",
  "translation_master_artifact_id": "translation_master:1.0.0:<sha256>|none",
  "subtitle_profile": "vi_telegram_general_v1",
  "cues": [
    {
      "derived_id": "subtitle_0001_<sha256>",
      "segment_id": "seg_0001_<sha256>",
      "meaning_id": "meaning_0001_<sha256>|source_meaning",
      "start_ms": 0,
      "end_ms": 0,
      "subtitle_text": "",
      "lines": [],
      "cpl": [],
      "cps": 0.0,
      "adaptation": "source_copy|translated_condense"
    }
  ],
  "outputs": {
    "srt_artifact_id": "artifact:<sha256>",
    "vtt_artifact_id": "artifact:<sha256>",
    "ass_artifact_id": "artifact:<sha256>|none"
  },
  "qc_summary": {
    "status": "PASS",
    "timeline_equal_to_source": true,
    "max_lines_pass": true,
    "cpl_pass": true,
    "cps_pass": true,
    "unicode_pass": true,
    "rendered_glyph_pass": true
  },
  "input_fingerprint": "<sha256>",
  "output_fingerprint": "<sha256>"
}
```

Translated subtitle timing is copied exactly from source cues. Adaptation may
shorten text and choose line breaks, but cannot invent a new translated
timeline.

### 4.4 `dub_script.json`

```json
{
  "schema_name": "dub_script",
  "schema_version": "1.0.0",
  "artifact_id": "dub_script:1.0.0:<sha256>",
  "source_master_artifact_id": "source_semantic_master:1.0.0:<sha256>",
  "translation_master_artifact_id": "translation_master:1.0.0:<sha256>",
  "duration_fit_profile": "owner_fidelity_1x_v1",
  "entries": [
    {
      "derived_id": "dub_0001_<sha256>",
      "segment_id": "seg_0001_<sha256>",
      "meaning_id": "meaning_0001_<sha256>",
      "speaker_id": "speaker_01",
      "window_start_ms": 0,
      "window_end_ms": 0,
      "candidate_ids": [],
      "selected_candidate_id": "candidate_<sha256>",
      "spoken_text": "",
      "predicted_duration_ms": 0,
      "measured_duration_ms": 0,
      "provider_speech_rate": 1.0,
      "post_tempo": 1.0,
      "fit_strategy": "candidate_select|semantic_rewrite|pass",
      "complete_utterance_required": true,
      "overlap_allowed": false,
      "emotion": "neutral",
      "pause_after_ms": 0
    }
  ],
  "qc_summary": {
    "status": "PASS",
    "all_segments_generated": true,
    "all_utterances_complete": true,
    "overlap_count": 0,
    "truncated_count": 0,
    "speed_1x_count": 0,
    "meaning_consistency_pass": true
  },
  "input_fingerprint": "<sha256>",
  "output_fingerprint": "<sha256>"
}
```

Owner fidelity profile rules:

- Provider speech rate is exactly `1.0`.
- Post-tempo is exactly `1.0`.
- Candidate selection and semantic rewrite are attempted before synthesis is
  accepted.
- A cue that still does not fit becomes `WAITING_REVIEW` or `FAIL`; it is never
  clipped and never mixed on top of the next cue.
- The previous utterance must finish before the next utterance starts.

### 4.5 `voice_cast.json`

```json
{
  "schema_name": "voice_cast",
  "schema_version": "1.0.0",
  "artifact_id": "voice_cast:1.0.0:<sha256>",
  "voice_policy_version": "subdub_voice_cast_v1",
  "diarization": {
    "required": false,
    "status": "not_requested|PASS|alignment_unavailable",
    "reason": "single_speaker|multi_speaker|owner_selected"
  },
  "casts": [
    {
      "speaker_id": "speaker_01",
      "voice_alias": "<public-safe-alias>",
      "voice_gender": "female|male|neutral",
      "voice_language": "vi",
      "admin_provider_voice_ref": "admin_voice:<sha256>"
    }
  ],
  "me_policy": {
    "source": "provided_me|embedded_me|separation_fallback|voiceover_ducking",
    "artifact_id": "artifact:<sha256>|none",
    "qc_required": true
  },
  "input_fingerprint": "<sha256>",
  "output_fingerprint": "<sha256>"
}
```

Diarization is optional and disabled for an eligible single-speaker job unless
the owner explicitly requests it. Source separation cannot be called clean M&E
without artifact QC.

### 4.6 `stage_qc.json`

```json
{
  "schema_name": "stage_qc",
  "schema_version": "1.0.0",
  "artifact_id": "stage_qc:1.0.0:<sha256>",
  "job_id": "<internal-job-id>",
  "stage_name": "final_media_qc",
  "stage_state": "PASS",
  "input_fingerprint": "<sha256>",
  "output_fingerprint": "<sha256>",
  "checks": [
    {
      "check_id": "mp4_full_decode",
      "blocking": true,
      "status": "PASS",
      "metrics": {},
      "safe_reason": ""
    }
  ],
  "blocking_failures": [],
  "warnings": [],
  "readiness": {
    "artifact_exists": true,
    "schema_valid": true,
    "fingerprint_matches": true,
    "safe_for_next_stage": true
  },
  "admin_diagnostic_ref": "admin_qc:<sha256>",
  "created_at": "<utc-iso8601>"
}
```

Required final checks include MP4 container/streams, full decode, source-duration
coverage, subtitle rendered-glyph samples, subtitle timing/readability, dub
completeness/no overlap, loudness/true peak, original-audio policy and combo
meaning/name/number consistency.

### 4.7 `delivery_receipt.json`

```json
{
  "schema_name": "delivery_receipt",
  "schema_version": "1.0.0",
  "receipt_id": "delivery_<sha256>",
  "job_id": "<internal-job-id>",
  "lane": "source_subtitle|translated_subtitle|translated_dub|translated_combo",
  "final_artifact_id": "final_mp4:<sha256>",
  "final_artifact_fingerprint": "<sha256>",
  "final_size_bytes": 0,
  "final_duration_ms": 0,
  "final_qc_artifact_id": "stage_qc:1.0.0:<sha256>",
  "delivery_channel": "telegram",
  "delivery_message_id": "<persisted-message-id>",
  "delivered_at": "<utc-iso8601>",
  "delivery_status": "DELIVERED",
  "charge_eligibility": "ELIGIBLE",
  "charge_idempotency_key": "<sha256>",
  "charge_state": "NOT_CLAIMED|CLAIMED|CHARGED|RECONCILE",
  "public_report_state": "NOT_SENT|SENT",
  "input_fingerprint": "<sha256>",
  "output_fingerprint": "<sha256>"
}
```

The receipt is persisted before any wallet mutation. In shadow/replay,
`charge_eligibility` is forced to `INELIGIBLE_SHADOW` and wallet calls are
forbidden.

## 5. Semantic And Media Rules

### 5.1 Source Selection

Priority:

```text
validated user timed subtitle
-> validated embedded subtitle
-> validated visual OCR when explicitly eligible
-> ASR
```

An untimed text file cannot claim source timing. It must be aligned or marked
`alignment_unavailable`.

### 5.2 VAD And Chunking

- VAD creates speech regions only; it never removes silence from the canonical
  timeline.
- Every chunk stores local and original offsets.
- ASR chunk overlap, if introduced later, is deduplicated before source master
  creation.
- All segment timestamps are absolute before any lane derives an artifact.

### 5.3 Alignment Truth

Only these values are accepted:

- `word_aligned`: real word timing exists and passes monotonic/bounds QC.
- `segment_timed`: segment/cue timing exists, but no valid word alignment.
- `alignment_unavailable`: text exists without trustworthy timing.

No UI or report may call segment timing word-accurate.

### 5.4 Translation

- Translation uses scene/context windows while preserving stable segment IDs.
- Glossary, proper nouns, numbers, dates and units are checked before `PASS`.
- A missing translation is a blocking failure; copying source text is not a
  translated success.
- Back-translation is warning evidence only, never the sole pass criterion.
- Automatic paid provider fallback is forbidden.

### 5.5 Subtitle Adaptation

Profiles are versioned and configurable. Proposed Vietnamese Telegram profile:

```json
{
  "profile_id": "vi_telegram_general_v1",
  "language": "vi",
  "platform": "telegram",
  "max_lines": 2,
  "max_cpl": 42,
  "target_cps": 17,
  "warning_cps": 20,
  "hard_cps": 23,
  "min_duration_ms": 833,
  "max_duration_ms": 7000,
  "gap_frames": 2,
  "safe_width_ratio": 0.86,
  "unicode_normalization": "NFC",
  "rendered_glyph_qc": true
}
```

These numbers belong to this profile only. CJK, Thai, Arabic and other scripts
receive separate profiles. Encoding success alone is insufficient: V2 renders
sample frames through the actual ASS/libass font path and checks visible glyphs.

### 5.6 Dubbing And Duration Fit

V2 initial owner profile is strict 1.0 speed:

```text
semantic translation
-> generate duration-aware candidates
-> predict duration
-> choose best meaning-preserving candidate
-> rewrite if too long
-> synthesize at 1.0
-> measure actual duration
-> accept only if full utterance fits before next cue
```

No audio trim may remove spoken content. A completed utterance never overlaps
the next cue, and no new cue starts while the previous cue is still speaking.
If no candidate fits, the stage fails or waits for admin review; it does not
distort or overlap speech.

Character count is only a weak feature, not a duration contract.

### 5.7 M&E And Original Audio

Priority:

```text
owner-provided M&E
-> embedded M&E
-> source separation with QC
-> original track with voice-over ducking
```

Required M&E checks: vocal bleed, music damage, phasing, missing ambience and
pumping. The existing V1 user's keep/mute/mix choice is copied into the V2
request contract unchanged.

### 5.8 Audio Delivery Profiles

Loudness is chosen by versioned delivery profile, not one universal value:

| Profile | Integrated loudness | True peak | Use |
| --- | ---: | ---: | --- |
| `telegram_social_v1` | -16 LUFS | -1.0 dBTP | Telegram/social output |
| `streaming_dialogue_v1` | -18 LUFS | -1.0 dBTP | Dialogue-first streaming |
| `broadcast_ebu_v1` | -23 LUFS | -1.0 dBTP | Explicit broadcast request only |

Each profile also versions LRA, sample rate, codec and bitrate. Fixed final
outputs use measured two-pass loudness normalization when supported. A failed
measurement is not silently called normalized.

### 5.9 Combo Consistency

Combo derives two artifacts from one meaning master:

```text
translation_master entry
  -> subtitle_copy entry
  -> dub_script entry
```

They share `meaning_id`, names, numbers, speaker and scene. Text does not need
to be identical. QC blocks mismatched meaning, name, number, speaker or scene.
Changing only subtitle line breaks must never rerun TTS.

### 5.10 One Final MP4 For Long Video

Public SubDub V2 product limits:

- Maximum input size: 500 MiB.
- Maximum final output size delivered to Telegram: 500 MiB.
- Maximum source duration: 3600 seconds.
- Local Bot API transport may support 2 GiB, but the SubDub product cap remains
  500 MiB.
- Cloud Bot API and local Bot API transport limits are reported separately from
  the product limit.

Long video execution:

1. Probe the complete source once.
2. Create one absolute-timeline source semantic master.
3. Process bounded chunks/parts while retaining absolute source IDs.
4. Produce per-part media artifacts with matching codecs and dimensions.
5. QC every part.
6. Concatenate parts locally in source order.
7. Validate one final MP4 with ffprobe, full decode and source-duration check.
8. If over 500 MiB, run one deterministic local compression profile, then
   validate again.
9. If still over 500 MiB or invalid, fail honestly with zero charge.
10. Deliver only the one final MP4; internal parts are never customer success.

FFmpeg commands are argument lists with a resolved executable path. V2 must not
use `shell=True`, hard-coded host paths, `-shortest`, or string-concatenated
commands.

## 6. Safe Retry And Recovery Contract

### 6.1 Automatically Retryable

- Read an already persisted local artifact.
- Poll a stored provider task ID.
- Download/retrieve the result for a stored task ID.
- Telegram download when the request is known not to be a paid submit.
- Telegram delivery of the same validated artifact under one delivery claim.
- Local validation and deterministic local render after persisted inputs exist.

### 6.2 Never Automatically Retryable

- Submit ASR, translation, TTS, separation or any paid provider task.
- Submit a replacement after an uncertain timeout/connection close.
- Switch to a paid fallback provider.
- Create a provider task from status, health, public-open, refresh or recovery.

### 6.3 Uncertain Submit

If the client cannot prove whether a paid request was accepted:

```text
stage = WAITING_REVIEW
provider submit claim remains locked
no replacement submit
admin diagnostic only
new submit requires explicit owner/customer confirmation
```

### 6.4 Recovery

On restart:

1. Load the stage registry by idempotency key.
2. If an output artifact is fingerprint-valid and QC passed, reuse it.
3. If a stored provider task ID exists, poll/retrieve only that task.
4. If a submit was claimed but task acceptance is uncertain, wait for review.
5. Never create a replacement task.
6. Continue local downstream stages only from validated artifacts.

## 7. Delivery-First Billing

Required sequence:

```text
final artifact exists
-> schema/artifact QC PASS
-> MP4 full decode PASS
-> Telegram delivery returns a real message ID
-> delivery_receipt.json atomically persisted
-> charge claim acquired once
-> wallet charged once
-> final report emitted once
-> public panel terminalized once
```

Failure rules:

- Missing/invalid MP4: terminal failure, charge 0.
- Delivery failed: charge 0; retry only the same validated artifact.
- Receipt persistence failed: charge 0 and `WAITING_REVIEW`.
- Charge failed after delivery: `DELIVERED_UNCHARGED_RECONCILE`; do not redeliver
  and do not create provider work.
- Final report/full-green state requires delivery receipt and successful charge
  resolution (or explicit zero-price policy), never only an MP4 path.

Shadow/replay always stops before delivery and forces wallet mutation count to
zero.

## 8. Privacy, Retention And Public Leakage

Default proposed retention:

| Artifact class | Retention | Content |
| --- | --- | --- |
| Raw source, audio master, ASR input, part MP4s | 24 hours | Customer media |
| Semantic/translation/subtitle/dub artifacts | 72 hours | Customer text/timing |
| Admin provider/task metadata | 30 days | Masked admin-only diagnostics |
| QC summary without raw text/media | 30 days | Metrics and safe reasons |
| Delivery receipt | 90 days | Artifact hash, Telegram message ID, charge state |
| Legal generated fixtures | Repository lifetime | No customer data |

Rules:

- Shadow/replay uses generated legal fixtures or owner-approved redacted/copied
  artifacts only.
- Public messages never include provider, base URL, model, endpoint, task ID,
  signed URL or raw debug.
- Provider metadata lives behind an admin-only reference and is excluded from
  public artifacts/fingerprints.
- Deletion must honor active idempotency, retrieval and delivery references.

## 9. Shadow And Replay Evaluation

All flags remain off until separate approval:

```text
SUBDUB_PIPELINE_V2_ENABLED=0
SUBDUB_PIPELINE_V2_PUBLIC_ALLOWED=0
SUBDUB_PIPELINE_V2_SHADOW_REPLAY=0
```

Replay inputs:

- Generated legal fixtures.
- Owner-approved, copied/redacted test artifacts.
- No customer production traffic.
- No provider call.

Compare V1 and V2 on:

- Source timing coverage and alignment truth.
- Subtitle CPL/CPS/line breaks/rendered glyphs.
- Translation glossary/name/number integrity.
- Dub predicted vs measured duration, 1.0 speed, completeness and overlap count.
- Combo meaning/name/number/speaker/scene consistency.
- Final MP4 streams, duration, full decode and size.

Acceptance counters:

```text
provider_calls = 0
wallet_mutations = 0
customer_deliveries = 0
production_traffic = 0
```

## 10. Focused Test Contract For Phase 2

Phase 2 tests must prove:

1. One source semantic master is reused by all four lanes.
2. One translation master is reused by lanes 2-4.
3. Combo creates different subtitle/dub text artifacts with shared meaning IDs.
4. VAD preserves absolute original offsets.
5. Alignment truth is explicit and cannot overclaim word alignment.
6. Vietnamese profile supports 42 CPL and two lines.
7. Subtitle/audio profiles are configurable and versioned.
8. Diarization is optional for an eligible single-speaker job.
9. Glossary, names, numbers, dates and units are validated.
10. Provider TTS speed and post-tempo remain 1.0 in owner fidelity profile.
11. Every TTS utterance completes and overlap count is zero.
12. Duration fit selects/re-writes candidates before any timing adjustment.
13. M&E separation cannot claim clean without artifact QC.
14. Loudness target comes from the selected profile.
15. Stage idempotency blocks duplicate submits.
16. Poll/download can retry an existing task.
17. Recovery cannot submit a replacement provider task.
18. Status/health/public-open create zero provider tasks.
19. HTTP 200/task ID/output URL cannot create a `PASS` without validated output.
20. Missing final MP4 is terminal failure and zero charge.
21. Delivery receipt is persisted before one charge claim.
22. A 3600-second project produces one final concatenated MP4.
23. Input and final Telegram output are capped at 500 MiB.
24. Shadow/replay makes zero provider calls, wallet mutations and deliveries.
25. Public callback snapshots remain unchanged.
26. Product Video, renderer ownership, worker ownership and DB schema remain
    untouched.

Required branch/main comparison after implementation:

```text
new failures introduced = 0
provider calls = 0
wallet mutations = 0
```

## 11. Readiness, Rollout And Rollback

Design review gate:

- This document approved by owner.
- No Phase 2 implementation before approval.

Shadow contract pass requires all schema/idempotency tests and zero side-effect
counters. Replay pass requires approved artifacts and the comparison report.

Rollout requires separate approval at each step:

```text
admin preview
-> one owner-approved canary per lane
-> 5%
-> 25%
-> 50%
-> 100%
```

Rollback:

```text
SUBDUB_PIPELINE_V2_PUBLIC_ALLOWED=0
```

V1 remains available until all four V2 lanes have sustained approved live pass.
No rollout step may remove or rewrite V1.

## 12. Review Decisions Requested

Owner approval is requested for these design choices:

1. Shared source master and one translation master per target/config.
2. Separate subtitle and dub copy artifacts with shared meaning IDs.
3. Strict owner fidelity profile: provider speed 1.0, post-tempo 1.0, no trim,
   no overlap; fail/review when speech does not fit.
4. Public SubDub caps: 500 MiB input, 500 MiB final output, 3600 seconds.
5. One final MP4 for long projects; no successful customer part delivery.
6. Versioned subtitle/audio profiles and real rendered-glyph QC.
7. Stage-level idempotency with no automatic paid resubmit/fallback.
8. Delivery receipt before charge.
9. Proposed retention table.
10. Phase 2 remains isolated and disconnected from public callbacks.

No implementation, deployment or production smoke is authorized by this
document.

## 13. Design Amendment A (2026-07-29)

This amendment is a contract-only change requested after the first design gate.
It is intentionally committed separately before any V2 runtime module is
implemented.

### 13.1 Safe TTS Transport Chunking

Semantic cue boundaries and transport payload boundaries are different things.
V2 may split one long `dub_script` utterance only to satisfy a transport limit;
it may not create a new subtitle cue, change the source window or claim that a
transport fragment is a separate semantic sentence.

The transport chunk contract is:

```json
{
  "segment_id": "seg_0001_<sha256>",
  "transport_group_id": "ttsgrp_<sha256>",
  "transport_sequence": 1,
  "transport_total": 2,
  "text_utf8_sha256": "<sha256>",
  "text_start_codepoint": 0,
  "text_end_codepoint": 3800,
  "max_payload_bytes": 65536,
  "provider_speed": 1.0,
  "idempotency_key": "<sha256>"
}
```

Rules:

- Default transport limits are 4,000 Unicode code points and 64 KiB UTF-8
  bytes per request; a provider-specific adapter may lower them, never raise
  them without a versioned profile.
- Split only at punctuation/word boundaries. A boundary that would cut a
  grapheme, combining sequence, markup tag or word is invalid.
- Every fragment carries the same `segment_id`, ordered sequence and complete
  text hash. Reassembly must prove that the ordered text hash equals the source
  dub-script text hash.
- Transport fragments are synthesized sequentially. Their audio is concatenated
  only after every fragment has a valid artifact and measured duration.
- A fragment may not start a new source cue and may not extend the cue window.
  If fragment timing cannot fit while preserving the complete utterance, the
  segment is `WAITING_REVIEW` or `FAIL`; it is never clipped or overlapped.
- Each fragment has its own stage idempotency claim. A timeout after a submit
  remains `ACCEPTANCE_UNKNOWN`; it is not submitted again automatically.
- Offline replay uses a fixture transport adapter that records calls and returns
  deterministic audio bytes. It never reaches a provider.

### 13.2 Long-Video Resource Budget

The 500 MiB/3600-second product contract is also a resource contract. V2 uses
bounded sequential work so one job cannot exhaust the bot host:

| Resource | V2 limit | Failure |
| --- | ---: | --- |
| Input media | 500 MiB | `RESOURCE_LIMIT_EXCEEDED` |
| Final Telegram MP4 | 500 MiB | `RESOURCE_LIMIT_EXCEEDED` |
| Source duration | 3,600 seconds | `RESOURCE_LIMIT_EXCEEDED` |
| Internal parts | 12 | `RESOURCE_LIMIT_EXCEEDED` |
| Target part duration | 300 seconds | deterministic planner |
| Concurrent parts | 1 | no parallel memory spikes |
| In-flight decoded audio | 256 MiB | `RESOURCE_LIMIT_EXCEEDED` |
| Workspace budget | `min(3 * input_bytes + 512 MiB, 4 GiB)` | `RESOURCE_LIMIT_EXCEEDED` |
| Semantic cue count | 6,000 | `RESOURCE_LIMIT_EXCEEDED` |
| Subtitle artifact | 8 MiB | `RESOURCE_LIMIT_EXCEEDED` |

The budget is evaluated after ingest/probe and before a paid stage. Per-part
artifacts are fingerprinted, QCed and released before the next part starts.
Only the final concatenated MP4 is a customer output. Part files are never
individually marked delivered or charged.

### 13.3 Seven-Schema Lineage

Every one of the seven contracts now carries explicit lineage fields:

```text
lineage_id
parent_artifact_ids[]
root_source_id
source_segment_ids[]
derived_meaning_ids[]
upstream_fingerprints[]
lineage_fingerprint
```

The permitted lineage graph is:

```text
source_semantic_master
  -> translation_master
       -> subtitle_copy
       -> dub_script
            -> voice_cast
            -> stage_qc
                 -> delivery_receipt
```

`source_semantic_master` may have no semantic parent but must have an ingest
request fingerprint. `translation_master` must point to exactly one source
master. `subtitle_copy` and `dub_script` must point to the same source master
and, for translated lanes, the same translation master. `voice_cast` points to
the dub script and its speaker set. `stage_qc` points to the artifact it checks.
`delivery_receipt` points to the final MP4 and final QC artifact. A missing or
cross-user parent makes the artifact invalid.

Lineage is immutable after `PASS`. A new profile, source, target, voice policy
or runtime SHA creates a new derived artifact rather than mutating an old one.

### 13.4 Three-Level Idempotency

V2 uses three independent idempotency levels; passing one level does not waive
the others.

| Level | Key | Protects |
| --- | --- | --- |
| Request/job | `scope + source_fingerprint + request_config_fingerprint` | duplicate confirmation/new job |
| Stage/artifact | `job_id + stage + upstream_fingerprint + config_fingerprint + segment_or_global` | duplicate computation and artifact writes |
| Side effect/transport | `provider_alias + transport_group_or_delivery + sequence + artifact_fingerprint` | provider submit, retrieval, Telegram delivery and charge claim |

Each claim has an atomic state:

```text
UNCLAIMED -> CLAIMED -> COMPLETED
                    \-> ACCEPTANCE_UNKNOWN
                    \-> FAILED
```

`CLAIMED` has an owner, lease and timestamp. Lease expiry permits inspection
or polling, not an automatic paid replacement submit. `COMPLETED` returns the
existing artifact/receipt. A second confirmation at any level returns the
existing job and cannot mutate wallet state twice.

### 13.5 `ACCEPTANCE_UNKNOWN`

`ACCEPTANCE_UNKNOWN` is a first-class state, not a generic failure. It is used
when a side-effect request may have reached a provider or Telegram but the
client lacks a definitive acceptance/result boundary.

Required fields:

```text
acceptance_state = ACCEPTANCE_UNKNOWN
side_effect_claim_id
request_fingerprint
provider_task_id_present = true|false
last_safe_operation = poll|retrieve|inspect|none
replacement_submit_allowed = false
admin_review_required = true
charge_eligible = false
```

Allowed actions are read-only inspection, polling a stored task ID, retrieving
an already-created artifact and admin review. Public status remains honest and
non-technical. No refresh, restart, recovery or health route may create a
replacement provider task. A new paid submit requires a new explicit confirm
and a new request fingerprint.

### 13.6 Quantitative V1/V2 Replay Metrics

The replay harness writes a machine-readable `replay_metrics.json` for each
fixture and an aggregate report. The following metrics and thresholds are the
acceptance contract:

| Metric | Definition | Required threshold |
| --- | --- | ---: |
| `source_master_reuse_rate` | lanes using one valid source master / 4 | 1.0 |
| `translation_master_reuse_rate` | lanes 2-4 using one valid translation master / 3 | 1.0 |
| `duplicate_stage_submit_count` | repeated stage claims that created work | 0 |
| `duplicate_side_effect_count` | repeated transport/delivery/charge effects | 0 |
| `subtitle_timing_exact_rate` | translated cues with identical source bounds | 1.0 |
| `translation_coverage_rate` | source segments with valid translated meaning | 1.0 |
| `glossary_name_number_error_rate` | failed glossary/name/number checks / checked | 0.0 |
| `dub_complete_utterance_rate` | complete measured utterances / expected | 1.0 |
| `dub_overlap_count` | utterance overlaps on the absolute timeline | 0 |
| `dub_truncation_count` | utterances clipped or dropped | 0 |
| `dub_speed_deviation_max` | absolute deviation from profile speed 1.0 | 0.0 |
| `combo_consistency_rate` | shared meaning/name/number/speaker checks passed | 1.0 |
| `mp4_valid_rate` | final artifacts passing structural/full-decode QC | 1.0 |
| `duration_delta_p95_ms` | p95 absolute source/final duration delta | <= 350 |
| `provider_calls` | fixture run external provider calls | 0 |
| `wallet_mutations` | fixture run credit mutations | 0 |
| `customer_deliveries` | fixture run external deliveries | 0 |
| `new_failures_introduced` | same-command V2 failures minus clean-base failures | 0 |

V1 and V2 are compared on these measurements, not on byte equality or a green
progress panel. A fixture fails replay if any blocking threshold is missed.

### 13.7 Privacy, Retention And User Isolation

All artifact keys and stage claims include an immutable `scope_id` derived from
the authenticated owner and product context. Raw Telegram user/chat IDs are
never used as public artifact names and are never shared across scopes.

Isolation rules:

- A source fingerprint may be reused only inside the same `scope_id`, or from a
  repository legal fixture explicitly marked `fixture_scope`.
- A matching media hash from another user never grants access to that user's
  semantic, translation, voice or delivery artifact.
- Every artifact read checks scope, product and lineage before returning bytes.
- Admin diagnostics expose masked identifiers only; public responses expose no
  provider/task/debug values.
- Logs store event type, scope hash and safe reason, not raw media or full
  customer text.

Retention defaults are now enforceable contracts: raw media/audio/parts 24h,
semantic/translation/copy artifacts 72h, admin provider metadata 30d, QC
summaries 30d and delivery receipts 90d. Deletion is blocked while a valid
retrieval/delivery claim is active, then removes bytes and leaves only the
minimum non-sensitive audit tombstone.

### 13.8 Default-Off Flags And V1 Rollback

The V2 config contract is:

```text
SUBDUB_PIPELINE_V2_ENABLED=0
SUBDUB_PIPELINE_V2_PUBLIC_ALLOWED=0
SUBDUB_PIPELINE_V2_SHADOW_REPLAY=0
SUBDUB_PIPELINE_V2_ADMIN_PREVIEW=0
```

Any missing, malformed or false flag selects V1/disabled behavior. No module
import changes a flag, registers a callback or starts a background task.

Rollback is a single operational action:

```text
SUBDUB_PIPELINE_V2_PUBLIC_ALLOWED=0
```

V1 remains available even if a V2 artifact, replay or admin preview fails. V2
cannot remove, overwrite or migrate V1 jobs, artifacts or callback routes.

### 13.9 One Final Combo Compose/Mux

Combo has one and only one final compose boundary:

```text
source_video
 + subtitle_copy (one selected SRT/ASS artifact)
 + mixed_dub_audio (one timeline artifact)
 + original_audio_policy
 -> compose/mux exactly once
 -> final_mp4
 -> final_media_qc
```

The combo must not render a subtitle video and a dubbed video separately and
then merge the two MP4s. It must not feed the subtitle copy back through
translation or TTS. Subtitle and dub copies are assembled from the same
translation master and passed to one compose stage. For long media, internal
parts may be composed and QCed, then concatenated once in source order; the
concatenated file is the only final MP4 and the only delivery candidate.

The compose stage records both input artifact IDs, the original-audio policy,
the output fingerprint and one `stage_qc` result. A structurally valid file
without both requested combo layers is `FAIL`, never partial success.

## 14. Amendment Acceptance Gate

Before Phase 2 code is accepted, the branch must show:

```text
design amendment commit: present and separate
safe TTS transport chunking: specified and fixture-tested
long-video resource limits: specified and fixture-tested
seven-schema lineage: specified and fixture-tested
three-level idempotency: specified and fixture-tested
ACCEPTANCE_UNKNOWN: specified and fixture-tested
quantitative replay metrics: specified and fixture-tested
privacy/retention/user isolation: specified and fixture-tested
default-off flags/V1 rollback: specified and fixture-tested
one final combo compose/mux: specified and fixture-tested
```
