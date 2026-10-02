# Smart-Only Bounded Audio And Subtitle Tails

## Owner Contract

Continue only the post-TTS failure on job `bbdd0c9918d018db4c4d`.
Owner explicitly allowed extending a cue's audio and subtitle tail by at most
2 seconds into an empty gap. Keep its source start, all later cue starts,
the complete text, assigned voice, and source video duration unchanged.
Do not increase a compression limit, shift subsequent speech, or truncate words.

Base: `f294f4f846aa07cc7cf0489622c589e01cfe866f`.
Production observed before this patch: `b0bf521423e16b6953edea7cb09480fac1ff4dde`.

## Reproduced Failure

The job's five TTS entries were all `SUCCEEDED`. Cue 5 contained 5.142938 seconds
of cached audio in its 39.920-41.940 source window. Its fit ratio was 2.546,
exceeding Smart's existing 2.5 limit. The failure was post-TTS, despite the
terminal progress metadata displaying 5 percent. Owner was charged 0 Xu.

With the new helper disabled, the exact cached artifacts reproduce
`duration_aware_fit_exceeds_hard_cap` before the renderer is called.

## Narrow Runtime Changes

- `services/subdub_smart_timing.py`: bounded extension from measured audio;
  stops at any next speech, preserved original speech, earlier overlapping
  speaker, or video end. Supports seconds/millisecond cue representations.
  Stores the original end so repeated evaluation cannot accumulate extensions.
- The same helper validates source SRT start/end before changing only the end
  timestamp. It retains subtitle text and timing settings; mismatches fail closed.
- `services/subdub_blackboxes/auto_smart_multivoice.py`: apply after TTS coverage
  and identity checks, before existing fit gates. Copy render cues, preserve
  source cues, burn and return the same retimed SRT. Without any extension,
  the original output-segment precedence remains unchanged.
- `services/subtitle_dub_product_pipeline.py`: the corresponding branch is
  explicitly limited to `auto_smart_multivoice` with duration-aware chunks.
  Ordinary Multi and two-voice lanes do not enter it.
- `tests/test_p0_subdub_smart_tail_extension.py`: 16 tests including old-failure
  control, actual cached MP4 replay, no-overlap boundaries, video-end limit,
  repeat safety, preserved source objects, and unchanged legacy lanes.

Unchanged by this patch: `bot.py`, ASR, translation, acoustic models,
speaker assignment, strict Multi V2, provider clients, checkpoint submission,
wallet/payment logic, ENV, and secrets. Existing thresholds 1.8, 2.5, 5.0
and 30 percent are not changed.

## Real Cached MP4 Evidence

Every input MP3 is checked against its recorded SHA256. The cached TTS callback
rejects any requested voice change and makes no external calls. Production
timeline, ASS and mux functions are loaded without starting the bot. FFmpeg
and FFprobe perform the real rendering, stream checks and full decode.

| Cue | Original Start/End | Rendered Start/End |
| --- | --- | --- |
| 1 | 13.505 / 15.045 | 13.505 / 15.085188 |
| 2 | 21.265 / 21.765 | 21.265 / 22.061656 |
| 3 | 24.945 / 28.005 | 24.945 / 28.797 |
| 4 | 30.080 / 38.980 | 30.080 / 38.980 |
| 5 | 39.920 / 41.940 | 39.920 / 43.940 |

Output: 7,764,732 bytes, H264 video + AAC audio, exactly 59.600 seconds.
All 5 complete cue texts and the existing single fallback voice are retained.
Shifted cue starts: 0. Video extension: 0.000 seconds. Full decode: exit 0.
Cue 5 fit after extension: 1.2793378109452749, not 2.546.

The locally retained artifact is `artifacts/subdub-bbdd0c9918-replay/`
`verified-tail-output/smart_complete.mp4` under the parent task directory.
It is an offline replay, not a new Telegram delivery or a paid live test.

## Verification And Baseline Limits

- Python 3.11 compile guard for `bot.py`, all three changed runtime files,
  and the new test file: exit 0. `git diff --check`: exit 0.
- Deployment workflow hygiene: `Ran 39 tests in 5.784s`, `OK`. The first local
  attempt lacked Bash coreutils on PATH; supplying the already installed Git
  coreutils to only the test process resolved all four environment failures.
- Core Smart, timing, checkpoint, orchestrator, compression and new tail tests:
  `183 passed, 1 skipped, 3 deselected in 35.04s`.
- The skipped case requires a different old 25-cue cached artifact not supplied.
- The three excluded cases require full bot bootstrap or compare to an obsolete
  historical frozen-file SHA. They were run in the broader baseline comparison.
- Broader baseline with both changed modules loaded from unchanged HEAD:
  `194 passed, 11 failed, 1 skipped in 55.37s`.
- Final broad branch run, including all 16 new tail tests:
  `210 passed, 11 failed, 1 skipped in 64.66s`; identical failing test identities
  to the baseline. New failures: 0.

These are scoped tests, not a claim that the entire repository test suite passes.
Existing wider failures are kept out of this fix rather than editing working
runtime paths to satisfy an incomplete local bootstrap.

## Translation Acceptance Is Still Open

Cue 5's cached translated text equals its source text:
`nie yung menyu nie yung menyu nai`. Other ASR source strings also contain
phonetic text. Successful nonempty translation/TTS does not prove semantic
translation accuracy. This patch preserves all text and does not certify it
as a correct Vietnamese translation. No ASR/provider/model change is justified
by the post-TTS timing evidence alone.

Fresh end-to-end acceptance must check the original-language transcription,
complete translation, natural speech/subtitle pacing, receipt counts and final
Telegram MP4. Previous bounded paid-job grants were consumed; no new paid job
or resubmission is performed by this patch.

## Operational Boundaries

PROVIDER_CALLS=0
WALLET_MUTATIONS=0
ENV_OR_SECRETS_CHANGED=0
LIVE_PASS=NOT_TESTED

Before restart, read-only SQLite showed only old active-status records. Their
latest update preceded the running bot's 19:37:16 +07 startup, including the
previously interrupted job `2a2ad303023b1c26d6b6`. Those records were not edited
or resumed. Check again immediately before deploying a pinned merge SHA.

Rollback scope: revert only this patch's three runtime files on a new branch,
retain the earlier receipt/pacing/fallback fixes, and deploy through the normal
workflow. Do not roll back `main` or restore unrelated bot/provider code.

Candidate lesson: cached render proof must include subtitle end timestamps and
all occupied speech intervals, not just successful TTS counts. This is local
task evidence, not a promoted global rule.
