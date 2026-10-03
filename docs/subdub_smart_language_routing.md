# Smart Language Routing

## Current Contract

Deepgram's ASR wrapper accepts an optional explicit language. A concrete hint is
forwarded through the adapter and diagnostic request to `language`; the copied
request parameters omit `detect_language`, which otherwise takes precedence.
Default/empty/auto input keeps the previous request and old adapter call shape.
Shared request defaults are never mutated. Timeout and diarization are independent.

This change does not detect a language by itself, retry paid ASR, translate text,
change voices, change prices, retime audio or change the renderer. Automatic local
language detection is a separate Smart-only module described below.

## Regression Cases

Run `tests/test_p0_subdub_smart_language_hint_routing.py` with pytest. Its 13 cases
cover five explicit languages, three auto inputs, request-level timeout/diarization,
three ASR forwarding routes and compatibility with an old two-argument adapter.
The network client is replaced with a local recording client. No paid request runs.

Run `tests/test_p0_subdub_auto_asr_timeout_boundary.py` alongside it. Combined
measurement: 23 passed and 7 subtests passed. Expanded gate, fallback, receipt,
pricing and checkpoint comparison: 143 passed, 1 cached-artifact test skipped,
7 subtests passed. The skipped test requires separately supplied cached voice media.

## Optional Local Hint

Explicit confirmed Smart word-timeline ASR with source language `auto` may run
the separate `services/subdub_smart_language.py` helper before its existing ASR
request. All other lanes and known-language inputs bypass this helper. It samples
up to three 30-second windows of unfiltered audio. Speech VAD is deliberately not
used for this probe: measured singing samples lost language evidence after VAD.
At least two supported-language samples must agree with confidence >=0.90 and
no competing high-confidence language. A single sample requires duration >=8s
and confidence >=0.98. These are conservative routing thresholds, not accuracy
guarantees or claims about all videos/languages.

The local subprocess uses CPU int8 and two threads with a 60-second timeout.
Missing/corrupt model, unavailable dependency, timeout, low confidence, conflicting
languages or decoding failures return `auto`; they must not fail the product job.
No customer media is uploaded by this helper. No paid retry is introduced.

Install public hash-locked weights explicitly with the module's `--install-model`
command before acceptance. `MODEL_DIR` is fixed in the module, not a new ENV key.
Customer jobs use `local_files_only=True`. Existing dependency versions remain
unchanged; newly added packages are covered by `requirements.lock` hashes.

Offline actual-helper measurement: Chinese cached source returned `zh` from
three samples in 15.844s; Spanish returned `es` in 12.718s, with two confident
samples and a third below the threshold. These results prove hint selection on
those inputs, not end-to-end translation correctness or Telegram delivery.

New test surface: `tests/test_p0_subdub_smart_local_language.py` covers policy,
silence/invalid input, missing/corrupt model, timeout, optional failure, known
language and non-Smart route controls. Full MP4 and live acceptance remain separate.

Acceptance measurements for the local-hint patch: 165 offline regression tests
and 7 subtests passed; a separate cached MP4/tail/voice suite passed 38 tests.
Workflow hygiene passed 39 tests. All 78 existing dependency pins were preserved.
A clean isolated Ubuntu venv installed the complete hash lock and `pip check`
reported no broken requirements. The same helper on Ubuntu returned `zh` and
`es` on the two cached sources. None of these checks called paid providers.

Before enabling the helper on a release, run `python services/subdub_smart_language.py
--install-model` explicitly in that checkout. The command verifies every public
weight/config file; an incomplete install keeps customer jobs on ordinary auto
ASR. Run the offline local-language suite and actual helper smoke before recording
a release checkpoint. Do not report a model-ready release as live MP4 acceptance.
