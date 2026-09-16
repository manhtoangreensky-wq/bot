# SubDub Auto Multi V2 Selected Segments Fix Plan

> **For agentic workers:** Execute inline in one agent. Do not delegate. Follow RED → GREEN → regression in order.

**Goal:** Preserve/reconstruct the already-prepared source/translated segment lists at the post-prepare boundary so Auto Multi V2 can pass exact-price admission and reach its first TTS checkpoint without re-running a provider.

**Architecture:** Keep V1 and Auto 2 immutable. Repair only the shared post-prepare input normalization used by Auto V2, using existing subtitle parsers and source-cue retiming. Persist bounded failure stage/code so any later failure is diagnosable without raw exception or provider payload.

**Tech Stack:** Python 3.12, pytest, existing SubDub product pipeline.

**Spec:** Runtime `c974dfbb2e363c1b3bc8689680b49419ad028069`; failed V2 job `756e0bbb01efee51383c`; sidecar evidence `67` cues, `3` speakers, `629` words; no TTS checkpoint or MP4.

## Global constraints

- Failure evidence came from runtime `c974dfbb2e363c1b3bc8689680b49419ad028069`;
  the fix branch was rebased without conflict onto
  `origin/main=351b824233e5bdd959632b749eaf7a649fac1d13` before final verification.
- Modify only `bot.py`, focused V2 tests, and this plan unless a RED proves another file owns the defect.
- Do not edit `auto_multi_speaker.py` V1, `auto_speaker.py` Auto 2, provider adapters, TTS artifact validator, timing mixer, mux, delivery, pricing, wallet or PayOS.
- Provider calls, Telegram sends, production DB writes, wallet mutations and deploy are `0/NO` during local RED/GREEN.
- Never hardcode job id, filename, SHA, `67`, `68`, or one fixture into production behavior.

## SPEC-01 — Prove the lost field

- [x] Add a provider-free fixture with valid source segments/cue identities and a translated SRT, but an empty `output_segments` list at the post-prepare boundary.
- [x] Assert the current policy produces `tts_segments=[]` and `selected_text=""` before repair.
- [x] Assert `_subdub_auto_post_prepare_gate()` fails generically before repair.
- [x] Run only the focused test. Measured RED: `1 failed` at the expected
  `AUTO_CAST_MANUAL_REQUIRED` continuation assertion.

## SPEC-02 — Minimal prepared-data recovery

- [-] Do not reconstruct missing `source_segments`: the live evidence and RED
  prove source segments survived, so expanding this path has no authority.
- [x] If translated output is selected, `output_segments` is empty and `output_subtitle` is valid, parse it, retime to source cues and preserve cue/speaker metadata using existing helpers.
- [x] Re-run the policy after normalization and update the original `prepared`
  object used by V2 downstream.
- [x] Fail closed if subtitle parsing, cue count, cue identity, timing or selected text is still invalid.
- [x] Do not call ASR, translation, TTS or any external provider during recovery.

Measured GREEN after the final rebase: focused vertical and generalization
matrix `7 passed`, including
exact translated text, downstream V2 cue-assignment/policy use, and
truncated/extra/blank translated SRT rejection.

## SPEC-03 — Bounded provenance (not expanded in this product fix)

- [-] No new persistence behavior: selected-segment recovery removes this
  failure before terminalization; adding a second behavior without a new RED
  would violate locked-focus scope.
- [x] No raw exception, provider payload, transcript or secret was added.
- [x] Public maintenance copy remains unchanged.

## SPEC-04 — Generalization and regression

- [x] Existing V2 suite protects source selection; focused matrix covers the
  translated missing-segment boundary.
- [x] Test `3`, `5`, and `8` speaker-shaped fixtures with `3`, `25`, `67`, and
  `70` cues.
- [x] Run Auto Multi V2 routing/contract/checkpoint/artifact suites after the
  final rebase: `74 passed`.
- [x] Run protected V1 Multi + customer + Auto 2 batch after the final rebase:
  `88 passed, 241 deselected`.
- [x] Compile `bot.py`, `local_worker.py`, V1/V2/Auto2 blackboxes: exit `0`.
- [x] Run `git diff --check` and secret scan: exit `0`, matches `0` after
  removing the final documentation whitespace.

Pre-final-rebase full-suite comparison on the reviewed tree:

- Branch run stopped at `--maxfail=12`: `12 failed, 90 passed`; no SubDub
  targeted failure appeared before the stop.
- The exact same `12` node IDs on clean base
  `0e41d39bc0837caf25dced329142c59b302e6c09` failed identically.
- Baseline-equivalent failures are `4` missing `SUBDUB_MULTI_FIXTURE_PATH`
  resource gates, `1` missing local `onnxruntime` resource gate, and `7` stale
  `tests/test_core.py` branding/menu/ShopAIKey assertions.
- `BASELINE_FAILURES=12`, `BRANCH_FAILURES=12`, `NEW_FAILURES=0`.

## SPEC-05 — Ship and live gate

- [x] Review the complete diff. Independent re-review found no Critical or
  Important issue and returned `READY_TO_MERGE=YES`; its only Minor base-SHA
  note was corrected in this plan.
- [ ] Commit/push/PR/merge/deploy only after all local gates pass.
- [ ] Confirm VPS runtime SHA equals merge SHA.
- [ ] Run one separately Owner-authorized V2 live job; no retry/rearm of job `756e0bbb01efee51383c`.
- [ ] PASS requires validated MP4 + Telegram video + one receipt + settlement only after delivery.
- [ ] V2 remains canary-routed until multiple supported videos pass; no global cutover from this single fix.

## LIVE-02 — Production shape correction after job `4B6751D819`

- [x] Runtime `ce6dafb96e22676783894c39da76c19d3818a219` received a new V2 job.
- [x] The job completed acoustic preparation with `69` cues, `3` speakers,
  `630` words and stable local acoustic evidence.
- [x] The job stopped as `failed_no_charge` with no exact-selection cache,
  TTS checkpoint, TTS artifact, mux, delivery or Xu charge.
- [x] Provider-free RED reproduced the remaining live shape: the outer state
  selected V2, the prepared inner state omitted that route marker, and a
  truthy-but-stale `output_segments` list masked the valid translated SRT.
- [x] Minimal correction: merge the outer route authority into prepared state
  and canonicalize V2 translated segments from the existing SRT even when the
  stale list is non-empty. V1, Auto 2, provider, TTS, mux, delivery and wallet
  code remain untouched.
- [x] Focused live-shape RED: `1 failed` with
  `AUTO_CAST_MANUAL_REQUIRED`; GREEN: `1 passed` for `69` cues / `3` speakers.
- [x] Complete post-prepare matrix after correction: `8 passed`.
- [x] V2 routing/contract/checkpoint/artifact regression: `75 passed`.
- [x] Protected V1 Multi + customer exact + Auto 2 comparator:
  `88 passed, 241 deselected`.
- [x] Compile `bot.py`, `local_worker.py` and V1/V2/Auto 2 blackboxes: exit `0`.
- [x] Exact production diff reviewed: `bot.py` is `+14/-2`; protected blackbox,
  pipeline and provider diffs are `0`.
- [ ] Push one follow-up PR and deploy once.
- [ ] A new live V2 job must produce validated MP4, Telegram delivery and one
  receipt before the task can be closed.

## LIVE-03 — Separate Auto 2 success from Multi V2 failure

- [x] Job `25F60D45442567B955ED` proved Auto 2 remains healthy: terminal
  `delivered`, MP4 validated/delivered, Telegram video message `28597`, one
  success receipt and `0` Xu for the admin run.
- [x] Job `6D35C7BCEF0A50058E42` proved the failing video is a different blackbox:
  `181s`, `69` acoustic cues, `3` speakers, `629` words, then
  `AUTO_CAST_MANUAL_REQUIRED` after translation and before TTS.
- [x] V1 delivered comparator `DUB-15E52AA8` had an exact `26 -> 26` cue
  bijection, exact cache, `26/26` TTS artifacts, MP4 delivery and receipt.
- [x] Add bounded Multi-only provenance for prepare bijection and gate
  selection. Persist counts/status only; never persist transcript text.
- [x] Provenance RED: `2 failed` because counters were absent. GREEN:
  `2 passed`; complete focused file: `10 passed`.
- [x] V2 regression: `77 passed`; protected V1/customer/Auto 2 comparator:
  `88 passed, 241 deselected`; compile: exit `0`.
- [ ] Deploy provenance once, then use exactly one new Multi V2 job to identify
  the failing predicate and apply the final minimal behavioral correction.
