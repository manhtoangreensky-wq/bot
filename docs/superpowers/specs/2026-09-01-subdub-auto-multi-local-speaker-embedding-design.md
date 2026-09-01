# SubDub Auto Multi local speaker-embedding design

## Status

- Design class: architectural.
- Owner approval received in chat on 2026-09-01:
  `XÁC NHẬN TÍCH HỢP LOCAL SPEAKER-EMBEDDING ONNX CHỈ CHO SUBDUB AUTO MULTI VÀ FINAL ACOUSTIC RECOVERY CHÍNH JOB #B4CB6D5FE8; KHÔNG TẠO JOB MỚI; CHARGED_XU=0.`
- This document records the approved design for written review. It authorizes
  no implementation, provider call, database mutation, push, deploy, or live
  recovery until the Owner approves this written spec.

## Objective

Produce a real SubDub `subtitle_plus_dub|auto_multi_speaker` MP4 for the
existing job `b4cb6d5fe8a7bdfce507` / public `#B4CB6D5FE8` by identifying
speakers from the source audio with a local, hash-locked ONNX embedding model.
The final path must translate to English, use a distinct validated TTS voice
for every retained speaker, preserve source word timing, mix original audio at
40% and dubbed audio at 150%, deliver MP4 then receipt, and keep Owner charge
and wallet transaction deltas at zero.

The same acoustic backend becomes the only speaker-attribution authority for
future Auto Multi jobs. It does not change the already locked exact-two lane.

## Measured reason for the change

The provider cross-timeline approach is empirically invalid for the exact
fixture whose SHA-256 is
`83de97b744b931e544b569e6e750f8415545f226461bd2e36cfb49225898ad3e`:

- durable job identity is `subtitle_plus_dub|auto_multi_speaker`;
- primary sidecar has 32 cues and only two speaker labels;
- Gemini returned 147-149 valid word annotations and four to five labels;
- three bounded zero-duration Gemini annotations can be filtered safely;
- the first primary cue and Gemini word timeline differ by about 7.46 seconds;
- the first cue's only lexical token occurs six times and is not a unique join;
- primary-to-Gemini label voting was only 7-5 and therefore not authoritative;
- all three bounded same-job recovery corrections remained
  `failed_no_charge`, with no MP4, artifact, delivery, charge, or transaction.

Continuing to reduce timestamp, plurality, lexical, or crosswalk thresholds
would assign a voice by guess. This design removes cross-provider speaker
mapping from the active Auto Multi path instead of weakening fail-closed
behavior.

## Proven local acoustic evidence

The existing diagnostic workspace contains a WeSpeaker VoxCeleb ResNet34
runtime model and results produced from the exact fixture:

| Evidence | Measured value |
| --- | --- |
| Model file | `voxceleb_resnet34.onnx` |
| Model bytes | 26,534,127 |
| Model SHA-256 | `9fea6516d7ad6bf0a76c7689f5a49b65d330fad6dde96c91bb4435ffbfe056a1` |
| Source license | Apache-2.0 |
| VoxCeleb pretrained-weight license | CC-BY-4.0, per WeSpeaker `docs/pretrained.md` |
| Exact-fixture automatic cluster count | 5 |
| Speech runs | 23 |
| Embedding windows | 70 |

The repository already ships larger or comparable hash-locked ONNX assets,
and production already installs `numpy==2.4.6` and
`onnxruntime==1.29.0` from `requirements.lock`. No new package, ENV variable,
credential, network model download, GPU dependency, or service is required.

## Scope

### Allowed production files

- create `services/subdub_multi_speaker_embedding_onnx.py`;
- update `services/subdub_blackboxes/auto_multi_speaker.py` only at the
  Auto Multi prepare/diarization seam;
- update `bot.py` only for the optional Auto-Multi word-timeline seam,
  acoustic-backend dispatch, aggregate evidence propagation, and the final
  same-job recovery compare-and-set;
- add `assets/models/subdub_auto_multi/voxceleb_resnet34.onnx`;
- add `assets/models/subdub_auto_multi/WESPEAKER.LICENSE.APACHE-2.0`;
- add `assets/models/subdub_auto_multi/VOXCELEB.MODEL.LICENSE.CC-BY-4.0`;
- add `assets/models/subdub_auto_multi/THIRD_PARTY_NOTICES.md`;
- add focused tests and measured operational documentation.

### Protected and byte-locked production files

- `services/subdub_speaker_cast.py`;
- `services/subdub_two_speaker_asr_fallback.py`;
- `services/subdub_two_speaker_gender_onnx.py`;
- `services/subdub_blackboxes/auto_speaker.py`;
- `services/subdub_blackboxes/dub_only.py`;
- `services/subdub_blackboxes/subtitle_dub.py`;
- `services/subtitle_dub_product_pipeline.py`;
- PayOS, `/naptien`, wallet, payment, trial, top-up, onboarding, PWA,
  Product Video, WebApp, and unrelated provider modules.

Before and after implementation, these two exact-two hashes must remain:

- `services/subdub_speaker_cast.py`:
  `de93620f3f038b5759a53e696c5c85d3553fcee758686df56c70e6b11bac145b`;
- `services/subdub_two_speaker_asr_fallback.py`:
  `94748def11c38d76952192a996fa42231d75b39d4d9ecd3407ff671d92e1177e`.

## Alternatives considered

### 1. Recommended: same-timeline local acoustic diarization

Use one word-timed ASR result for text and time, extract local speaker
embeddings from those exact intervals, cluster locally, and construct speaker
turns from the same word records. This avoids every cross-provider temporal
join and matches the Owner's requirement to recognize multiple voices
automatically.

### 2. Rejected: continue Gemini-to-primary timestamp mapping

The exact fixture has already disproved the assumption that both providers
share a usable timeline. More retries return slightly different label counts
and timing. Lower thresholds would hide, not fix, the mismatch.

### 3. Rejected: manual voice choice or forced speaker count

Manual selection is not Auto Multi. Supplying a speaker-count hint, copying
primary labels, alternating voices, or forcing gender pairs would fabricate
speaker evidence and is prohibited.

## Authoritative end-to-end flow

```text
existing exact job and exact source bytes
-> source media preflight and normalized audio
-> one confirmed word-timed ASR result
-> validate and canonicalize every word record
-> build bounded acoustic speech units from the same word timeline
-> local NumPy Kaldi-compatible fbank
-> hash-locked WeSpeaker ONNX embedding per speech unit
-> deterministic 3-8 speaker spectral clustering
-> assign every word to exactly one stable acoustic cluster
-> group adjacent same-cluster words into canonical source cues
-> existing translation path to English on those exact cue times
-> existing local register classifier per acoustic speaker
-> existing deterministic distinct-voice assignment
-> existing per-cue scalar TTS
-> existing cue-locked timeline/QC/mux
-> validate real MP4
-> Telegram MP4
-> receipt
-> no Owner charge and no wallet transaction
```

Gemini speaker annotations, primary-ASR speaker labels, lexical matching, and
provider-to-provider timestamp mapping are not accepted as speaker authority in
this path. Existing provider speaker fields may be retained only in private
diagnostics for comparison; they cannot affect cluster selection or voice
assignment.

## Word-timed ASR authority

Auto Multi requires an ordered word timeline from the existing confirmed ASR
provider call. Each word record must contain:

- nonempty text or punctuated text;
- finite `start` and `end` seconds;
- `0 <= start < end`;
- nondecreasing start time;
- source-media bounds;
- a stable sequential word index.

Provider speaker labels are explicitly ignored. Estimated transcript
distribution, visual OCR cue timing, subtitle-only text without word timing,
and cross-provider word joins fail closed for acoustic diarization.

The bot seam is additive and defaults off. A new optional
`require_auto_multi_word_timeline=False` argument may be passed through the
current resolve/transcribe functions. Only exact
`auto_speaker_lane == "multi"` passes `True`; all other lanes retain their
literal current behavior. The returned word list stays invocation-local or in
the existing bounded workspace checkpoint. It is never stored in public job
copy, logs, receipts, wallet state, or provider-usage public fields.

On final same-job recovery, a valid exact-source checkpoint may be reused. If
it is absent or hash-mismatched, the existing Owner-confirmed provider gate may
perform one word-timed ASR call on the same source. It may not create a new job,
upload, confirmation, or provider diarization request.

## Acoustic speech-unit construction

The local module receives mono signed-16-bit PCM at 16 kHz plus the validated
word timeline. It constructs units without changing output word times:

1. Start a new unit after a silence gap greater than 350 ms.
2. Start a new unit before adding a word that would make the unit longer than
   2.5 seconds.
3. Preserve every word exactly once and in order.
4. A unit shorter than 500 ms is zero-padded for feature extraction only; it
   must not borrow neighboring source audio that could contain another voice.
5. A unit with no finite audio energy or fewer than the minimum fbank frames
   after padding fails closed.

The unit's original first-word start, last-word end, and ordered words remain
the text/timing authority. Padding never changes subtitle, TTS, or mux timing.

Bounds:

- source duration at most the current Auto Multi limit of 300 seconds;
- at most `speaker_cast.MAX_SIDECAR_CUES` word-derived acoustic units;
- at least six units before requesting three or more clusters;
- one in-process acoustic-classifier lock;
- one CPU thread per ONNX session;
- 300-second wall deadline with cooperative cancellation;
- no unbounded arrays, raw-payload persistence, or network access.

## Feature frontend and model validation

The module implements the WeSpeaker runtime frontend using NumPy only:

- 16 kHz mono PCM;
- input scaled by `2^15`, matching WeSpeaker inference;
- 25 ms Hamming analysis window;
- 10 ms frame shift;
- 80 mel bins;
- zero dither;
- per-unit cepstral mean normalization without variance normalization;
- ONNX input `feats` with a batch dimension;
- output `embs`, normalized to unit L2 length.

No Torch or Torchaudio dependency is added. A checked-in golden frontend
fixture derived once from the Apache-licensed WeSpeaker reference must prove
NumPy fbank parity within a documented numeric tolerance. The expected values
are static test data, not calculated by the implementation under test.

Before the first inference, the module must verify:

- model file exists and is nonempty;
- model SHA-256 exactly matches
  `9fea6516d7ad6bf0a76c7689f5a49b65d330fad6dde96c91bb4435ffbfe056a1`;
- all three notice/license files exist and are nonempty;
- ONNX input and output names/types/ranks match the expected WeSpeaker runtime
  contract;
- only `CPUExecutionProvider` is selected;
- every output embedding is finite, nonzero, and has one consistent dimension.

Any failure raises the existing Auto-Multi manual-required exception before
translation, TTS, mux, delivery, charge, or wallet mutation.

## Deterministic spectral clustering

Clustering is implemented with NumPy and the bounded algorithm used by the
existing WeSpeaker diagnostic, without SciPy or Scikit-learn:

1. L2-normalize unit embeddings.
2. Build cosine similarity as `0.5 * (1 + E @ E.T)`.
3. Apply symmetric nearest-neighbor pruning with bounded matrix size.
4. Construct the unnormalized graph Laplacian.
5. Run `numpy.linalg.eigh`.
6. Select `k` from the largest eigengap within the inclusive range 3-8,
   subject to available-unit and minimum-cluster-support bounds.
7. Cluster the selected eigenvectors with deterministic farthest-first
   centroid initialization and a bounded iteration count.
8. Canonicalize cluster labels by earliest source-word time so reruns do not
   reorder public speaker IDs.

The result is accepted only when:

- `3 <= k <= 8`;
- every unit has exactly one cluster;
- every cluster contains at least two independent units;
- every cluster contains at least 800 ms of original, non-padding speech;
- every embedding, eigenvalue, centroid, and distance is finite;
- no cluster is empty;
- convergence completes within the fixed iteration bound;
- two deterministic window views (base and half-frame-shifted frontend) select
  the same `k` and assign every unit consistently after canonical label
  normalization.

If either view disagrees, Auto Multi fails closed. No majority override,
expected-speaker hint, alternating labels, or minimum-three fabrication is
allowed.

## Word, cue, sidecar, and translation contracts

Each word inherits its unit's acoustic cluster. Adjacent words with the same
cluster are grouped into source cues. A cluster change always creates a cue
boundary. Output cue timing is the first word's original start and final word's
original end.

Acceptance requires:

- word count before and after clustering is identical;
- ordered word identity/text coverage is 100%;
- every source word appears in exactly one cue;
- cue starts are nondecreasing and each cue has `end > start`;
- no cue contains two acoustic clusters;
- retained speaker count equals selected `k`;
- every selected cluster appears in at least one cue;
- source and translated cue counts match;
- cue-index, start, and end mismatch counts are all zero after translation;
- sidecar cue count and timeline signature match the source cues exactly.

The sidecar stores bounded acoustic authority only:

- canonical cue ID/start/end;
- canonical `speaker_id` and numeric speaker label;
- bounded assignment confidence;
- model SHA-256;
- selected `k`;
- unit/window counts and sorted cluster-size aggregates;
- stability-pass boolean and algorithm version.

It does not store embeddings, raw PCM, provider payloads, API keys, endpoints,
raw transcript JSON, or personal identity claims.

## Register and distinct-voice assignment

After acoustic clustering, the existing Auto Multi register classifier runs on
ranges grouped by the new acoustic speaker IDs. The existing deterministic
voice allocator then assigns one validated private voice ID per retained
speaker.

Before the first TTS call:

- every cue has an acoustic speaker ID;
- every speaker has `low` or `high` register evidence accepted by the existing
  classifier;
- every speaker has one nonempty voice ID from the validated pool;
- distinct voice-ID count equals retained acoustic speaker count;
- the same speaker always maps to the same voice;
- different speakers never share a voice;
- no provider ID or voice ID is exposed in public copy.

The existing per-cue scalar TTS, translation, timeline, audio QC, mux,
artifact validation, delivery, and receipt code remains shared and unchanged.

## Final acoustic recovery for `#B4CB6D5FE8`

The existing durable job is the only recovery target. A fourth and final
compare-and-set claim is allowed only when all conditions are simultaneously
true:

- internal ID is exactly `b4cb6d5fe8a7bdfce507`;
- public code is exactly `B4CB6D5FE8`;
- job suffix is exactly `subtitle_plus_dub|auto_multi_speaker`;
- owner/chat match the command caller;
- exact source SHA-256 matches the approved fixture;
- target is exactly English;
- original volume is 40 and dubbed volume is 150;
- status and terminal state are both `failed_no_charge`;
- `charged_xu == 0` and `charge_status == "not_charged"`;
- no output, delivery, artifact, validation, or MP4 field is present/true;
- attempts are exactly 3 and correction count is exactly 2;
- the prior crosswalk marker is true;
- `auto_multi_acoustic_recovery_used` is absent/false;
- model and notice preflight passes before the CAS.

The successful CAS sets attempt 4, final acoustic correction count 3,
`auto_multi_acoustic_recovery_used=true`, and the acoustic backend/version. It
persists before work resumes. No fifth claim is possible under any command or
flag. A concurrent or duplicate command loses the CAS and performs no ASR,
translation, embedding, TTS, mux, delivery, or wallet action.

The root durable job count must remain unchanged. The recovery cannot create a
new engine job, job key, public code, workspace, upload, Telegram file,
confirmation, price, invoice, transaction, or wallet event.

## Charging and provider policy

- Owner authorization applies only to the same approved job and final acoustic
  recovery.
- Local embedding/clustering has no provider call and no provider usage event.
- The recovery may use the existing paid ASR, translation, and TTS providers
  needed to finish the same job under the already approved exact settings.
- No provider speaker-diarization request is made by the acoustic path.
- Public price remains nonzero and measurable.
- Owner `charged_xu` remains zero before, during, and after delivery.
- Transactions, wallet balance, and credit-event deltas remain zero.
- PayOS and wallet code are byte-protected and unmodified.

## Failure handling

All failures before validated delivery terminalize the same job as
`failed_no_charge` with no public provider/model/path/debug leak. Admin-only
durable diagnostics may include bounded codes and aggregates such as:

- `ACOUSTIC_MODEL_MISSING`;
- `ACOUSTIC_MODEL_HASH_MISMATCH`;
- `ACOUSTIC_NOTICE_MISSING`;
- `ACOUSTIC_WORD_TIMELINE_REQUIRED`;
- `ACOUSTIC_FEATURE_INVALID`;
- `ACOUSTIC_EMBEDDING_INVALID`;
- `ACOUSTIC_CLUSTER_COUNT_OUT_OF_RANGE`;
- `ACOUSTIC_CLUSTER_UNSUPPORTED`;
- `ACOUSTIC_CLUSTER_UNSTABLE`;
- `ACOUSTIC_WORD_COVERAGE_FAILED`;
- `ACOUSTIC_VOICE_DISTINCTNESS_FAILED`;
- `ACOUSTIC_TIMEOUT`;
- `ACOUSTIC_CANCELLED`.

No failure may fall back to Gemini timestamp mapping, primary speaker labels,
manual voice selection, fake pending, fake success, or a second job.

## TDD and verification gates

Implementation begins with failing tests. At minimum, tests must prove:

### Model and frontend

- missing model, wrong model hash, and missing notices fail closed;
- model input/output schema mismatch fails closed;
- NumPy fbank matches the independent golden fixture;
- NaN, Inf, zero-norm, wrong-dimensional, or inconsistent embeddings fail;
- ONNX session is CPU-only, single-threaded, lazy, and lock-bounded;
- timeout and cancellation release the lock and create no partial sidecar.

### Word timeline and units

- malformed, estimated, unordered, duplicated, overlapping-invalid, or
  out-of-media word records fail;
- every valid word appears in exactly one unit and final cue;
- long speech is split only at word boundaries;
- short units use zero padding without timing mutation or neighboring audio;
- word/cue coverage and start/end drift are exactly zero.

### Clustering

- deterministic fixtures select 3, 5, and 8 clusters correctly;
- fewer than 3 or more than 8 clusters fail;
- empty/tiny/unsupported clusters fail;
- input permutation cannot change canonical speaker identity order;
- the two stability views must agree;
- no expected-speaker hint or provider label affects the result;
- the exact measured fixture selects five speakers in an offline resource gate.

### Voice and pipeline

- retained speaker count equals distinct validated voice count;
- every cue is synthesized once with its own speaker's voice;
- translation preserves cue count and times;
- original 40% and dubbed 150% reach the existing mux call;
- real MP4 validation is required before success;
- delivery order is MP4 then receipt only;
- status/refresh is read-only;
- no SRT, audio, document, or duplicate video companion is sent automatically.

### Recovery and safety

- exact job/source/owner/chat/language/volume conditions are required;
- final acoustic CAS wins exactly once;
- attempt 5 is blocked;
- root job count does not increase;
- no new upload, confirm, provider diarization, transaction, wallet, or charge;
- failed recovery remains `failed_no_charge`;
- exact-two files retain their locked hashes;
- manual/default and every non-multi product route are unchanged.

Required final local gates include focused acoustic tests, existing Auto Multi
parser/blackbox/recovery tests, exact-two protected tests, direct-impact
SubDub tests, `py_compile` of every changed Python file plus `bot.py` and
`local_worker.py`, `git diff --check`, model/license/hash validation, scope and
secret scans, and an independent diff review with Critical 0 / Important 0.

## Deployment and live acceptance

`MERGED`, `DEPLOYED`, and `LIVE` remain separate evidence states.

After squash merge and successful exact-SHA deploy:

1. verify VPS checkout equals the merge SHA and tracked diff is zero;
2. verify bot/web/nginx active and health JSON `status=ok`;
3. verify runtime model bytes, SHA, notices, NumPy, ONNX Runtime, CPU provider,
   and frontend/model smoke before recovery;
4. snapshot root-job, wallet, transaction, credit, provider-usage, and job
   durable state;
5. claim the final same-job acoustic recovery exactly once;
6. stop all Browser clicks and observe read-only to terminal;
7. reject any state that creates another root job or changes Owner charge.

LIVE PASS requires all of the following measured evidence:

- same internal job and public code;
- no new root job;
- final MP4 exists and is delivered;
- MP4 bytes and SHA-256;
- MP4 container, video/audio codecs, dimensions, duration, stream counts,
  frame rate, sample rate, channels, and loudness;
- selected acoustic speaker count between 3 and 8;
- exact fixture expected result: five retained acoustic speakers unless the
  final independent stability gate safely rejects the fixture;
- distinct validated voice-ID count equals retained speaker count;
- every source and translated word/cue covered exactly once;
- source/translated cue counts match;
- cue start/end drift counts are zero;
- final duration agrees with source within the existing validated tolerance;
- English translation evidence;
- original audio 40% and dubbed audio 150% evidence;
- nonzero public price;
- Owner `charged_xu=0`;
- wallet/transaction/credit deltas zero;
- Telegram video message ID and receipt message ID;
- public delivery sequence MP4 then receipt, with no automatic companion file;
- no duplicate success or error after delivery.

If any item is missing, indirect, ambiguous, or inconsistent, the job is not
LIVE PASS and the goal remains incomplete.

## Rollback

Rollback is source-only and fail-closed:

- disable acoustic dispatch by reverting the isolated Auto Multi integration;
- retain the durable failed job and its no-charge history;
- do not revive Gemini/primary cross-timeline mapping as success authority;
- do not delete source data, job state, model evidence, wallet state, or
  operational records;
- do not create a replacement job automatically.

The model asset and notices may remain packaged after a source rollback, but
an unused model cannot be reported as an active feature or LIVE PASS.
