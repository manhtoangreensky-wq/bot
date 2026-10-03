# Smart Language Routing

## Current Contract

Deepgram's ASR wrapper accepts an optional explicit language. A concrete hint is
forwarded through the adapter and diagnostic request to `language`; the copied
request parameters omit `detect_language`, which otherwise takes precedence.
Default/empty/auto input keeps the previous request and old adapter call shape.
Shared request defaults are never mutated. Timeout and diarization are independent.

This change does not detect a language by itself, retry paid ASR, translate text,
change voices, change prices, retime audio or change the renderer. Automatic local
language detection is a separate Smart-only follow-up, not a claim of this patch.

## Regression Cases

Run `tests/test_p0_subdub_smart_language_hint_routing.py` with pytest. Its 13 cases
cover five explicit languages, three auto inputs, request-level timeout/diarization,
three ASR forwarding routes and compatibility with an old two-argument adapter.
The network client is replaced with a local recording client. No paid request runs.

Run `tests/test_p0_subdub_auto_asr_timeout_boundary.py` alongside it. Combined
measurement: 23 passed and 7 subtests passed. Expanded gate, fallback, receipt,
pricing and checkpoint comparison: 143 passed, 1 cached-artifact test skipped,
7 subtests passed. The skipped test requires separately supplied cached voice media.
