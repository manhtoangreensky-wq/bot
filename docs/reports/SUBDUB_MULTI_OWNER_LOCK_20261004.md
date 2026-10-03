# Owner Acceptance And Lock: Multi / Smart Multi

Status: OWNER_ACCEPTED_WITH_KNOWN_LIMITATION_AND_LOCKED.
Date: 2026-10-04, Asia/Saigon.

## Owner Decision

Owner explicitly closed work on the Multi lane and requested a GitHub lock.
Owner acknowledged that initial male speech can still be dubbed with a female
voice, but accepted the current result as roughly 90% satisfactory and sufficient.
No further repair of that remaining issue is authorized by this closure.
The 90% figure is qualitative Owner feedback, not measured model accuracy.

## Accepted Runtime And Evidence

- Final runtime code PR: #1353, merged commit
  `ba198228c93af7306528eb589ba6f5e0e27458e4`.
- Selective rollback tag: `checkpoint/subdub-smart-pr1353-20261004`.
- Preserve gender checkpoint PR #1351 and identity/timing/source-fallback tags.
- Deploy run: https://github.com/manhtoangreensky-wq/bot/actions/runs/37142220831
  completed successfully. The final observed bot/helper SHA matches PR #1353.
- Offline post-TTS proof used six existing successful TTS artifacts, retained
  two dubbing voice IDs and one source-audio cue, and rendered an H264/AAC MP4
  passing full decode. Source fallback tempo1.0; shifted cue starts0.
- Output size8511457bytes; SHA256
  `1dfb6e58b6d4fd9838c037ded148cbd5a4a6d4804ac171f5282f2975b279fa13`.
- Output60.0s versus source media-format59.621016s retains the previously
  disclosed0.379s rounded-duration tail policy. No new renderer change is made.
- Final focused source-fallback suite106passed/8private skips; deployed
  smoke65passed/4private skips. The source-gender task's measured model parity
  is not a claim that every human source gender is correct.
- This agent's last verification was offline, not a new paid live submission.
  Owner acceptance is recorded separately from automated/live verification.
- Private source media, transcripts, audio and diagnostic payloads remain private.

## Lock Boundary

Auto Multi Speaker, Multi V2 and Smart Multi Voice remain enabled in their
existing runtime. This lock stops further engineering/testing/deployment work
on those lanes; it does not disable user-facing features or stop services.

No additional runtime fix, model/threshold/voice/timing adjustment, refactor,
replacement copy, replay/live test, provider request, job resubmission, wallet
mutation or Multi-specific deploy is authorized. Shared code must not change
locked Multi behavior indirectly. Other explicitly requested project work must
preserve these lanes.

`AGENTS.md` contains the durable Owner instruction. Reopening requires a new
explicit Owner instruction to reopen the locked lane and define a narrow task.
An automatic continuation or a still-known defect is not reopening authority.

## Publication And Recovery

This closure changes only `AGENTS.md` and this report. It introduces no runtime
change and requires no production deployment or restart. Keep the existing
runtime checkpoint, prior rollback tags, private evidence, stashes and unrelated
untracked work. Do not reset main or remove unrelated Owner changes.

If Owner later explicitly reopens a regression task, inspect the corresponding
PR checkpoint first and use a selective patch/revert within that approved scope.
Until then, record the known initial male/female mismatch without continuing work.
