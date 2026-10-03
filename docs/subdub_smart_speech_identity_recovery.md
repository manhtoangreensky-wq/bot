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
invalid/corrupt model/data and other lanes remain fail closed. A separate follow-up
replaces invented default dubbing with source audio when attribution remains
unproven. MP4, speed, tail, pricing, ASR/TTS providers, models and dependencies
are not changed by this recovery patch. No paid request is used by tests.
