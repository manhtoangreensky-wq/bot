# Smart Speech Identity Recovery

Only explicit Smart uses this retry when whole-vocal acoustic views are unstable.
The stable primary and strict multi defaults remain unchanged. The hook requires
`minimum_speakers=1` and original-source register mode, the existing Smart call
contract; it does not change a shared signature or cosine/confidence threshold.

Reuse the already separated vocal stem once, extract speech-conditioned windows
with the existing engine, and classify original-source register. Base, shifted
and aggregate spectral views independently select a count1-8. They must agree;
the existing constrained partition must meet all three agreement gates and the
unchanged0.98cosine gate. No filename, job hash or forced two-speaker count exists.
Word mapping uses original timestamps and covers each word exactly once. Return
the generic Smart classification contract, not fabricated strict-multi proof.

Identity register votes use the existing strong-confidence and two-thirds vote
dominance constants. Isolated opposite-register windows cannot split one person.
Supported opposite-register speech retains the existing constrained partition;
evenly divided evidence cannot authorize a guessed voice. No legacy default is
changed. Tests cover 1/2/3/5/8 identities, same-register people, isolated outliers,
ties, disagreeing/bad views and strict controls. Optional local source evidence
is not published with the repository.

Acceptance checklist for offline review:
- Speaker counts follow the signal, not filenames or a fixed two-speaker count.
- Each word is covered once at its original timestamp.
- Same-register identities retain distinct cast entries.
- Ambiguous register evidence cannot silently become confident dubbing.
- Strict lanes never invoke this retry; one vocal extraction is reused.

Unstable recovery errors are recognized by Smart's existing degrade boundary;
invalid/corrupt model/data and other lanes remain fail closed. Source selection
is governed by the fitting-TTS policy: attribution uncertainty alone cannot
discard TTS. MP4, speed, tail, pricing, ASR/TTS providers, models and dependencies
are not changed by this recovery patch. No paid request is used by tests.

## Supported Identity Retry

Only failed Smart speech recovery enters the supported-window retry for view,
register ambiguity or register-evidence failures. Primary stable/strict lanes
and a successful prior speech result bypass it. All runtime edits remain in this
helper. The reliable subset still must pass the unchanged0.98cosine gate and
cover at least the existing0.95agreement fraction, with unchanged speech support.
The three views select and agree on the count before register samples are
selected. The register subset cannot recount two people as one. Supported
register windows use the existing constrained partition for that same count.
Their centroid projection must agree at0.95; labels are then mapped back to all
windows and every original word, without timestamp shifts or text removal.
Too many unstable views, unsupported identities, ties, invalid inputs or unstable
projection still cannot fabricate multiple speakers. Approximate recovery is not
strict attribution/geometry proof or a guarantee that every boundary is correct.

Offline acceptance includes1/2/3/5/8 stable identities,2/3/5/8 partial-view cases,
same-register identities, partial register ambiguity, corrupt inputs, missing
speaker support, actual normalized source word coverage and distinct cast routes.
No video filename, job ID, forced count, dependency or model change is used.

Measured verification for this retry:62 focused tests passed, including local
real ONNX word mapping; wider regressions261 passed/1 unsupplied archival fixture
skip. Workflow hygiene39 passed, Python3.11 compile/diff checks passed. Cached
same-source original and normalized Ubuntu candidate probes retained70/70 words
and distinct low/high cast routes. Fresh live ASR word timing was not retained
after workspace cleanup, so cached response evidence is not represented as a
reproduction of every fresh word boundary or paid LIVE acceptance. Diagnostic
timing variants with unstable centroid projection remain rejected, not forced.
