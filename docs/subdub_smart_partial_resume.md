# Partial Smart Translation Resume

The existing exact-quote resume serializer retained only scalar values, so the
new approved missing-translation cue-ID list disappeared at confirmation pause.
This patch changes only that Smart-specific field: preserve a copied, bounded,
unique list of nonempty string IDs. Malformed values are not render authority.
All other resume fields and non-Smart behavior remain unchanged. No quote hash,
price formula, confirmation, claims, persistence schema or wallet logic changes.

RED actual serializer:3 failed/5 passed. Tests round-trip through JSON, keep the
original list independent, reject invalid shapes/duplicate/oversized IDs and retain
the existing non-Smart handling. This prevents a previously marked untranslated
cue from returning to target-language TTS after pause; the exact source-cue render
helper remains separately verified in PR1323.
