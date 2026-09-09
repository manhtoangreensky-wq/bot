# SubDub customer one-confirm closeout — 2026-09-09

## Requirement

Every customer SubDub job has one final confirmation only. After that edge,
the system computes the exact price, checks the current Xu balance, claims the
durable receipt once and continues through TTS, mux and MP4 delivery. It must
not render `AUTO_EXACT_CONFIRMATION_REQUIRED` a second time.

## Source and tests

- Root cause: `_subdub_auto_post_prepare_gate()` limited the existing
  final-confirmation bypass to `_pipeline_is_admin`; customers were paused for
  a redundant second exact-price confirmation.
- Production delta: the bypass now uses `subdub_final_confirmed_state(state)`
  for both Admin and customer. Exact balance checks, receipt CAS, delivery-first
  settlement and Admin zero-Xu behavior are unchanged.
- TDD RED: customer received `AUTO_EXACT_CONFIRMATION_REQUIRED`.
- TDD GREEN: `1 passed in 4.88s`; result is `{continue: true}`, receipt becomes
  `consumed=true` / `claim_state=resuming`.
- Protected customer/Admin/Auto Multi/Auto 2 gate: `177 passed in 7.77s`.
- `python -m py_compile bot.py`: exit `0`.
- Diff/scope/secret checks: exit `0`; six scoped files.

## Git and runtime

- PR: `#1009`.
- Source commit: `8ee649bc3f21360ee8e4751574cd3834d2f31746`.
- Squash merge/runtime SHA: `92f2e41b10821dea231b50f0f1c93148529c5bb1`.
- Deploy run: `34366937616`, terminal `success`.
- VPS checkout: exact merge SHA; tracked tree clean.
- `toanaas-bot`, `toanaas-web`, `nginx` and Local Bot API: active.
- Health endpoint: `status=ok`.

## Runtime behavior probe

The deployed function was executed with a final-confirmed non-admin state and
an exact price that would previously require reconfirmation:

- result: `{continue: true}`;
- receipt: `consumed=true`, `claim_state=resuming`;
- persistence reason: `auto_exact_initial_confirmation_claimed`;
- `second_confirmation_returned=false`;
- provider calls, jobs, production DB writes and wallet mutations: `0` for the
  probe.

## Live downstream evidence

- Customer job `#599360B9AD` reached `delivered/100%` with Telegram MP4 message
  `28225`, charge status `charged`, amount `277 Xu`, and empty terminal error.
- That job ran before runtime `92f2e41b`; it proves the shared downstream
  acoustic/TTS/mux/delivery path, not a fresh end-to-end one-confirm execution
  on the new SHA.

## Fresh post-deploy one-confirm LIVE proof

- Runtime readback during the test was exactly
  `92f2e41b10821dea231b50f0f1c93148529c5bb1`; bot, web and nginx were active.
- Fresh customer job: public `#A866975622`, internal
  `a866975622647f768a73`, terminal alias `DUB-1A160D9A`.
- The same durable job moved from `running/transcribing/35%` to
  `running/generating_voice/65%` without returning to
  `awaiting_auto_exact_confirmation` and without another Owner/customer
  action.
- At `65%`, `subdub_final_confirmed=True`; the exact receipt was already
  `consumed=1`, `claim_state=resuming`, exact total was `240 Xu`, and charge
  status remained `not_charged`. This is the observable one-confirm boundary.
- Terminal result: `delivered/100%`, final MP4 validated, last error empty.
- MP4 evidence: `16,640,532` bytes, MIME `video/mp4`, duration `134.0s`,
  SHA-256
  `81d9e37af5c8266b64ea588bf388e7fdb402be3fff1e629c51e78d84e9d96393`.
- Acoustic/TTS evidence: `5` detected speakers, `5` distinct voices,
  `26/26` TTS segments generated, `0` dropped.
- Telegram evidence: video message `28234`, then receipt message `28235`;
  `receipt_send_state=sent`, `receipt_sent_once=1`, `success_sent_count=1`.
- Settlement happened only after delivery: `charged_xu=240`; the durable
  settlement reference has exactly one credit event, total delta `-240`, final
  balance `1958 Xu`.
- The closeout inspection itself was read-only: no retry, resubmit, second
  confirmation, provider call, DB write or wallet mutation was initiated by
  Codex.

## Closure boundary

- Source/CI/deploy/runtime one-confirm behavior: **PASS**.
- Shared customer downstream MP4 delivery: **PASS**.
- Fresh paid customer one-confirm job on runtime `92f2e41b`: **LIVE PASS**.
- Final MP4 validation and Telegram video + receipt delivery: **LIVE PASS**.
- Exactly-once post-delivery settlement: **LIVE PASS**.
- Do not rerun completed jobs, reset receipt markers, resend MP4, or charge
  again.
