# Smart Terminal Handoff

Only the standalone Smart failure-result and exact-confirmation boundary changes.
Legacy/manual boundaries, pricing formulas, settlement, speaker models, speech
timing, renderer and shared lifecycle maps are unchanged.

On failure, the same job/user's last known progress stage is carried into its
diagnostic snapshot. A different job/user or an already delivered record cannot
provide this proof. A positive existing output-validation result AND a nonempty
existing final artifact can preserve validation-stage progress and artifact proof.
Failure remains failure: no delivery/success is fabricated and no charge occurs.
Error stage is retained separately from the last truthful processing stage.

Smart voice-count and translation-review evidence is retained from the blackbox
result. Unknown counts are not inferred from a filename or button. On a Smart
exact-confirmation pause, the authoritative gate result's state is merged with
entry context without confirming a receipt or changing the price.

Tests extract the actual boundary code. Unit artifact files test metadata handoff,
not media decoding; media validity is tested separately in the cached MP4 suite.
Controls include early/no-artifact failures, foreign job/user, delivered snapshots,
unchanged legacy failure/pause and the actual public progress renderer. The original
boundary produced 3 failed and 6 passed cases before the patch. An added stage
coherence test caught one further failure before publication.

Completed Smart snapshots now preserve bounded generic cast/count metadata in
both the core final-job save and outer pipeline update. This fixes metadata loss
for Smart results without strict multi attribution/geometry proof. The strict
proof helper and its requirements remain unchanged; generic metadata never adds
strict verified flags. Unproven whole-source attribution is explicitly marked
and cannot persist a fabricated one-speaker count. Source cue IDs/reasons and
actual dubbing voice count remain available after workspace cleanup. Fields are
allowlisted and bounded; financial, provider, credential and output-validation
fields are not copied. Tests execute the actual metadata unpacks in both final
consumers and include invalid/unverified casts and legacy controls.
