# P0.SUBDUB.LONGMEDIA32 Limit And Failure Matrix

Branch base: `9628961572a18af5cb0174563598237f527b77ae`

Authoritative SubDub behavior baseline: PR #606, merge `94ad8a97d128cfcbbd3439ec602c5c2f9fbde225`, head `c16f931`. LONGMEDIA32 does not restore PR #400 wholesale and does not shorten the PR #606 dub/combo speech timeline.

Scope: the four SubDub video lanes only. Product Video, Frame Video, Video Edit,
PayOS, wallet internals, DB schema, webhook, provider selection, and public UI are
out of scope.

## Current Limits

| Path | Symbol / line on base | Current value | Stage / lanes | Classification | Symptom | Required action |
| --- | --- | --- | --- | --- | --- | --- |
| `bot.py` | `SUBDUB_MAX_INPUT_MB` 2110-2113 | 300 MB with Local Bot API; 50 MB otherwise | Intake, all lanes | `REPLACE_WITH_CAPABILITY_CHECK` | Legal local/source override is incorrectly reduced to the Telegram transport cap | Keep a bounded 500 MB processing safety ceiling, but choose the effective limit by intake method |
| `bot.py` | `SUBDUB_TELEGRAM_CLOUD_DOWNLOAD_LIMIT_MB` 2144 | 20 MB | Cloud Bot API download, all lanes | `KEEP_EXTERNAL_HARD_LIMIT` | Cloud `getFile` rejects larger media | Keep and report as transport-only; do not present it as an E2E pipeline limit |
| `bot.py` | `SUBDUB_TELEGRAM_DOWNLOAD_LIMIT_MB` 2150-2159 | cloud <=20 MB; local default 300 MB | Telegram download, all lanes | `KEEP_EXTERNAL_HARD_LIMIT` | Direct download can fail before the pipeline | Keep transport-derived limit; Local Bot API may use the explicit 500 MB product ceiling |
| `bot.py` | `subdub_input_limit_mb` 208997 | minimum of processing and Telegram limits | Every intake method | `REPLACE_WITH_CAPABILITY_CHECK` | Local path and injected legal fixture above 20 MB fail even though Telegram is not used | Accept an intake method and apply transport limits only to `bot_api_direct` |
| `bot.py` | `video_dubbing_save_input_for_pipeline` 210161 | buffers full input and rejects through `subdub_input_limit_mb` | Save input, all lanes | `REPLACE_WITH_CAPABILITY_CHECK` | Supported local input is rejected as `video_too_large` | Use method-specific admission, preserve a bounded memory/resource ceiling, and persist original fingerprint |
| `bot.py` | `subdub_validate_saved_input_for_pipeline` 207920 | repeats `subdub_input_limit_mb` | Post-save validation, all lanes | `REPLACE_WITH_CAPABILITY_CHECK` | A successfully saved legal input can be rejected a second time | Validate against the same recorded intake capability |
| `bot.py` | `PIPELINE_MAX_DURATION_SECONDS_*` 2114-2115 | 300 s | Generic pipeline and old combo guard | `NOT_RELEVANT` globally | Changing it would affect other products | Leave global constants unchanged |
| `bot.py` | `SUBDUB_MAX_DURATION_SECONDS` 2116 | default 300 s | Full SubDub duration gate | `REMOVE` | Media above 300 s enters a different multi-delivery path | Replace with the explicit one-hour SubDub processing capability; never treat 60 s as a rejection boundary |
| `bot.py` | `SUBDUB_PREVIEW_DURATION_SECONDS` 2117 | 30 s | Preview/chunk decision | `KEEP_RESOURCE_SAFETY` | None; it is not a rejection | Keep preview-only semantics; introduce a direct-ASR capability threshold separately |
| `bot.py` | `SUBDUB_LONG_CHUNK_SECONDS` 2118 | 10-30 s | ASR audio chunks | `KEEP_RESOURCE_SAFETY` | Current ranges have no overlap, stable IDs, or checkpoints | Keep bounded chunks; add overlap ownership, deduplication, stable IDs, and restart checkpoints |
| `bot.py` | `SUBDUB_LONG_PROJECT_MAX_PARTS` / `...DURATION...` 2129-2133 | 12 parts / 3600 s | Long project | `REPLACE_WITH_CHUNKING` | Video is split and each part is delivered separately | Process one full video; chunk audio/provider work only; compose one final MP4 |
| `services/subdub_long_media.py` | `build_long_project_plan` 61 | 300 s parts by caller | Long project | `REPLACE_WITH_CHUNKING` | Violates one-complete-artifact contract | Retire it from the public execution path |
| `services/subdub_long_media.py` | `process_long_project_parts` 552 | delivers each part independently | Long project | `REMOVE` | Partial deliveries and per-part charging are possible | Do not call it from the four public lanes |
| `bot.py` | `subtitle_plus_dub_exceeds_limits` 203459 | Telegram-size limit + generic 300 s limit | Combo pre-processing | `REMOVE` | Combo can fail before canonical probe/chunking | Route through the same canonical SubDub preflight as all other lanes |
| `bot.py` | `video_dubbing_download_source` 212849 | one-hour duration check; transport-size check; 180 s x3 download | Telegram intake | `KEEP_EXTERNAL_HARD_LIMIT` / `KEEP_RESOURCE_SAFETY` | Cloud oversized files and transient download errors | Keep external size check and bounded retries; label one hour as explicit product capability, not a 60 s gate |
| `bot.py` | `subdub_probe_video_bytes` 212215 | 30 s; limited stream fields | Probe, all lanes | `REPLACE_WITH_CAPABILITY_CHECK` | Unfamiliar codecs, VFR, start time, audio layouts, and timebase are invisible | Return canonical stream/container/timestamp metadata and a normalization decision |
| `bot.py` | `video_dubbing_extract_audio` 213169 | fixed 120 s FFmpeg timeout | Audio extraction, all ASR lanes | `REPLACE_WITH_CAPABILITY_CHECK` | Long inputs can time out despite progressing normally | Derive bounded timeout from measured duration |
| `bot.py` | `openai_compatible_asr_transcribe` 62262 | 60 s per request | ASR provider | `KEEP_RESOURCE_SAFETY` | Whole long audio can time out | Keep per-request bound and feed deterministic short audio chunks |
| `bot.py` | `translate_subtitle_text` 126937 | bounded per segment | Translation lanes | `KEEP_RESOURCE_SAFETY` | None when segment mapping is preserved | Keep provider policy unchanged; checkpoint stable segment identity |
| `bot.py` | `synthesize_dub_segment_chunks` 214966 | one synchronous request per cue; no durable checkpoint | Dub/combo TTS | `REPLACE_WITH_CHUNKING` | Restart can replay completed or acceptance-unknown TTS | Add cue artifacts/checkpoints; actual product uses one submit at most and no automatic paid retry |
| `bot.py` | `subdub_plan_dub_timeline` 215075 | may extend beyond source | Dub/combo timeline | `KEEP_PR606_BEHAVIOR` | A source-bounded rewrite would drop or overlap speech | Preserve every cue sequentially; use conservative fit first, then extend within the one-hour product capability |
| `bot.py` | `build_dub_timeline_audio` 215188 | `concat`, `apad`, `atrim`, `-t` to the planned PR #606 timeline | Dub/combo audio | `KEEP_PR606_BEHAVIOR` | A partial or source-only target can truncate the final cues | Keep every cue, no overlap and no dropped cue; pad/trim only to the complete planned timeline |
| `bot.py` | `video_dubbing_render_video` 214171 | fixed 300 s timeout; `-t render_duration`; no `-shortest`; `amix duration=longest` | Final compose, all lanes | `REPLACE_WITH_CAPABILITY_CHECK` | Long render can time out | Derive timeout; use measured source duration for subtitle lanes and the complete PR #606 timeline for dub/combo; retain source frames with `tpad` when speech extends; keep `-shortest` absent |
| `bot.py` | `subdub_compress_video_bytes` 212437 | fixed 300 s timeout | Delivery compression | `REPLACE_WITH_CAPABILITY_CHECK` | Long output compression can time out | Derive timeout from measured duration and revalidate duration |
| `bot.py` | Telegram output limits 2134-2139 | Cloud video 45 MB/document 49 MB; Local Bot API product ceiling 500 MB | Delivery, all lanes | `KEEP_EXTERNAL_HARD_LIMIT` | Large valid MP4 may need compression/document delivery | Keep Cloud limits; allow one validated Local Bot API MP4 up to 500 MB; never claim 2 GB E2E without a separate real infrastructure proof |
| `bot.py` | `PIPELINE_JOB_LOCK_TTL_SECONDS` 2190 and SubDub cleanup 209488/209942 | 30 minutes | Registry/workspace | `REPLACE_WITH_CAPABILITY_CHECK` | A legitimate long job can lose its workspace before completion | Use a SubDub lease/retention window derived from the one-hour processing capability plus heartbeat |
| `bot.py` | terminal panel and receipt 208695/208874 | durable terminal helpers exist | Status/report, all lanes | `KEEP_RESOURCE_SAFETY` | Old or interrupted jobs can retain the initial 5% card; combo report lacks canonical details | Keep exactly-once locks; force terminal replacement when edit fails; use one report builder for all lanes |
| `local_worker.py` | `telegram_download_file` 339 default 20 MB | Local Video Studio/other worker paths | `NOT_RELEVANT` | None in the current SubDub owner path | Do not change worker/global contract in LONGMEDIA32 |

## FFmpeg Duration Policy

- `-shortest`: absent from the current SubDub compose scope and must stay absent.
- `-t`: permitted only for a measured extraction chunk, the measured source
  duration on subtitle-only lanes, or the complete planned PR #606 output
  duration on dub/combo. It must never use a partial TTS duration.
- `atrim` / `apad`: align audio to the canonical final timeline: measured
  source duration for subtitle-only lanes, complete sequential speech timeline
  for dub/combo.
- `amix`: `duration=longest` is safe only after its inputs are aligned to that
  same canonical final timeline.
- `concat`: valid for sequential cue audio, not for concatenating separately
  delivered video products.

## Read-Only Failure Evidence

The owner supplied four production support references. They are intentionally
not copied into this repository. No job was replayed, resubmitted, redelivered,
or mutated.

| Evidence alias | Observable evidence | First failing stage / confidence |
| --- | --- | --- |
| J1 | A roughly 1:36 translated-subtitle request returned media around 1:23 while visible source-language hard subtitles remained; the report claimed translated subtitle success | Transformed-artifact identity is not proven. Medium confidence from screenshot only |
| J2 | A submitted video retained the initial 5% status panel | Durable progress/terminal reconciliation failure. High confidence for the public symptom; internal cause unavailable |
| J3 | A roughly 1:33 request showed a 100% panel, proving long intake can reach terminal state in at least one path | No failure root cause proven from the supplied image |
| J4 | Combo source was roughly 1:33; returned media was shown as roughly 0:02 and 0:09, followed by generic `Kết quả đã gửi phía trên.` | The generic combo receipt differs from the other lanes. High confidence for the report symptom; no truncation root cause is asserted without the exact artifact and FFmpeg command |

Unavailable sources: production DB rows, Railway runtime logs containing the
four jobs, provider task records, final artifact hashes, and exact FFmpeg
commands are not present in the clean worktree. No root cause beyond screenshot
evidence is asserted without those sources.
