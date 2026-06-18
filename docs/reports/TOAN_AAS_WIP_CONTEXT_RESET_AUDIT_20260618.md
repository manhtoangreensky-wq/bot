# TOAN AAS WIP Context Reset Audit - 2026-06-18

## Audit Target

- Branch: `wip/save-before-codex-context-reset`
- Base: `origin/main` at `aaf88f1` (`Rebuild video flow state machine`)
- WIP commit: `dc13b43` (`WIP save before Codex context reset`)
- Audited range: `origin/main..HEAD`
- Patch artifact: `WIP_bot_diff.patch`

Important worktree note: the checkout was already dirty before this audit run: `M bot.py`, plus untracked audit/report files. Per the requested commands, the code review below is for the committed branch diff `origin/main..HEAD`; compile/pytest checks necessarily ran against the current checkout.

## Command Results

- `git branch --show-current`: `wip/save-before-codex-context-reset`
- `git log --oneline --decorate -5`: HEAD is `dc13b43`; base `aaf88f1` is directly below it.
- `git diff --stat origin/main..HEAD`: `bot.py | 711 +++++++++++++++++++++++++++++++++++++++++++++++++++--------------`, `563 insertions(+)`, `148 deletions(-)`.
- `git diff --name-only origin/main..HEAD`: `bot.py`
- `git diff origin/main..HEAD -- bot.py > WIP_bot_diff.patch`: completed.
- `git diff --check origin/main..HEAD`: PASS.
- `git status --short --untracked-files=no`: `M bot.py`

## 1. What Changed In `bot.py`

The committed WIP changes only `bot.py`.

- Adds `voice_profiles` schema columns: `consent_at`, `source_file_ref`, `preview_audio_ref`, `is_default`, `deleted_at`.
- Adds voice profile helpers for get/update/list/default/soft-delete.
- Reworks voice clone from direct upload to consent -> upload -> name -> quote -> confirm -> MiniMax upload/clone/TTS preview -> save.
- Adds Voice vault UI actions: select, listen, use, set default, rename, delete, save.
- Replaces the main voice/music tool grid with hub screens: voice hub, music hub, media.
- Adds no-voice/no-music/default-voice selections.
- Changes subtitle/dub pricing to new helper rules using 30-second extra blocks and a combo price.
- Updates some customer-facing voice/music wording.

## 2. What Is Completed

- Consent-first voice upload is present.
- Voice sample upload happens only after explicit consent.
- Voice profile rows are account-scoped and can be listed, renamed, soft-deleted, marked default, and selected.
- MiniMax voice profile preview path is wired behind readiness/public guards.
- Failed voice preview attempts try to refund charged Xu.
- Root Voice/Music UI now has a simpler customer-facing hub structure.
- `/test_all_video` is still defined and registered.
- Self-shot video upload-first flow exists in the audited tree, inherited from base.

## 3. What Is Incomplete

- No tests were added for the new voice vault, consent, billing, refund, retry, provider, or navigation behavior.
- New hub routing does not preserve exact caller/current video screen; `music_quick|root` hard-codes Back to `menu|main_video`.
- Several old direct music/voice actions are no longer visible from the root hub.
- Suno remains mostly planning/guarded from the customer flow; this WIP does not complete a public generation/job confirmation path.
- Subtitle/dub remains partial/public-gated; this WIP changes pricing but does not complete final muxed video output.
- `/test_all_video` was not hardened by this WIP.
- User-facing technical/provider wording remains in reachable flows.

## 4. Risky Changes

- **Voice billing/retry risk:** on failure the flow refunds but leaves `metadata["charged_xu"]`; retry uses `retry=True` and can skip charging, so a later successful retry may produce a saved voice after the original charge was refunded.
- **Duplicate confirmation risk:** charged metadata is not persisted before provider work begins; repeated confirm clicks can charge more than once.
- **Pricing regression:** subtitle/dub pricing no longer matches existing tests. Examples: 180-second subtitle now returns 360 Xu instead of expected 280 Xu; subtitle+dub combo changes expected 370 Xu to 350 Xu.
- **Navigation regression:** new hubs clear pending input and route back through a generic video menu, not the exact previous screen.
- **Visibility regression:** old direct buttons are hidden or removed from the top-level music UI.
- **DB/billing surface risk:** the WIP adds schema and wallet spend/refund calls in the new voice-clone path without regression coverage.

## 5. Deleted Or Hidden Buttons

Yes. The old direct Voice/Music grid was replaced by three root buttons.

Hidden/moved from the root:

- `Tạo giọng đọc` / Create voice: moved into Voice hub.
- `Tạo nhạc AI` / AI Music: moved into Music hub.
- `Nhân bản giọng` / Voice profile: moved into Voice hub.
- `Kho nhạc`, `SFX`, `Media`, `Ghép nhạc`: moved/nested.

No longer visible in the new root/hubs:

- `STT / Transcribe`
- `Ghép voice` / Add voice to video
- Music prompt
- Music policy
- MiniMax status button from the visible clone keyboard, although its handler still exists.

This is also confirmed by pytest failure: `test_image_notes_voice_music_guided_flow_v1` expected the old direct `🎙 Tạo giọng đọc` label.

## 6. PayOS, Top-Up, DB, Payment Files Touched

- Changed files in committed range: only `bot.py`.
- PayOS files: not touched.
- `/naptien`: not touched.
- Webhook routes/payment webhook: not touched in the committed diff.
- Top-up/package files: not touched.
- DB destructive logic: not touched; no destructive migration was added.
- DB additive logic: touched via new `voice_profiles` columns and CRUD/default/soft-delete helpers.
- Wallet/payment behavior: touched indirectly through new `spend_fixed_credit_info` and `refund_charged_credit` calls in the voice-clone flow.

## 7. Whether `/test_all_video` Is Fixed

No. The WIP does not modify `cmd_test_all_video` or its registration path. The command exists and is registered, but the WIP does not add hardening or tests for the suspected old-schema crash path.

Verdict: **not fixed by this WIP**.

## 8. Whether Self-Shot Video Asks Upload First

Yes in the audited tree. The self-shot flow still asks the user to send/upload the self-shot video before transformation, with a plan-first alternative. This appears inherited from `origin/main`; the WIP diff does not materially change this flow.

Verdict: **yes, but not newly fixed by this WIP**.

## 9. Whether Music/Voice/Subtitle Flow Is Complete

No.

- Voice: partially implemented. Consent, upload, name, quote, provider preview, save/use/default/delete exist, but billing/retry/idempotency and tests are incomplete.
- Music: partially implemented. Hubs and no-music selection exist, but Suno/customer generation remains guarded/planning-heavy and some old direct actions are hidden.
- Subtitle/dub: not complete. Pricing changed, but public-gated subtitle/dub output remains partial and existing pricing tests fail.

Verdict: **not complete**.

## 10. User-Facing API/Provider/ENV/Raw Error Text

Yes, provider/technical wording remains.

- New or reachable customer text still mentions MiniMax and Suno.
- Existing reachable flows still include terms such as provider, public gate, smoke, and API in some places.
- `music_quick|voice_clone_guard` remains callable and can show Ready/Public/Smoke/Reason details without an admin check.
- New clone execution catches provider exceptions and sends a generic refund message, so raw provider error text is not sent in that specific failure path.
- Admin commands still intentionally expose provider/ENV/runtime details.

Verdict: **still contains provider/technical text**.

## 11. Tests Run

Literal requested `python` command:

- `python -m py_compile bot.py`: failed locally because `python` is not on PATH.
- `python -m py_compile local_worker.py`: failed locally because `python` is not on PATH.

Equivalent checks using bundled Codex Python:

- `C:\Users\toann\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m py_compile bot.py`: PASS.
- `C:\Users\toann\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m py_compile local_worker.py`: PASS.
- `C:\Users\toann\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest -q`: FAIL.

Pytest result:

- 311 passed.
- 5 failed.
- 26 errors.
- 3 warnings.

Direct WIP-related failures:

- `tests/test_core.py::test_image_notes_voice_music_guided_flow_v1`
- `tests/test_core.py::test_video_pricing_v2_subtitle_and_dubbing_prices`
- `tests/test_core.py::test_video_total_price_v2_is_itemized`
- `tests/test_core.py::test_video_order_builder_addon_total`
- `tests/test_video_final_pipeline_v11.py::test_video_total_price_and_invoice_include_music`

The 26 errors are local temp/cache permission errors around `C:\Users\toann\AppData\Local\Temp\pytest-of-toann` and `.pytest_cache`; pytest is available, so this is not `PYTEST_NOT_AVAILABLE_LOCAL`.

## 12. Safe To Continue

**NO.**

Do not continue feature work from this WIP as-is. The branch has real regressions in menu visibility and pricing, untested DB/billing/provider changes, and voice-clone charge/refund/retry risks. Also, the worktree is already dirty with `M bot.py`, so reconcile the current local state before any next implementation.

## 13. Safe To Merge Main

**NO.**

Do not merge this WIP into main. The committed diff fails tests, hides/removes expected buttons, changes pricing contracts, and introduces untested billing/provider behavior.
