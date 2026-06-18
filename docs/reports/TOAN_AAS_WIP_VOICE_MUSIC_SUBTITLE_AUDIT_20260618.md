# TOAN AAS WIP Voice/Music/Subtitle Audit - 2026-06-18

## Target

- Branch: `wip/save-before-codex-context-reset`
- Base main: `origin/main` at `aaf88f1` (`Rebuild video flow state machine`)
- WIP commit audited: `dc13b43` (`WIP save before Codex context reset`)
- Audited range: `origin/main..HEAD`
- WIP patch: `WIP_bot_diff.patch`

Note: this checkout has an uncommitted `bot.py` delta beyond `dc13b43`. The audit below is for the committed WIP diff `origin/main..HEAD`; safety checks run against the current checkout.

## Required Git Context

- `git branch --show-current`: `wip/save-before-codex-context-reset`
- `git log --oneline --decorate -5`: `dc13b43` on top of `aaf88f1`
- `git diff --stat origin/main..HEAD`: `bot.py | 711 +++++++++++++++++++++++++++++++++++++++++++++++++++--------------`, `563 insertions(+)`, `148 deletions(-)`
- `git diff --name-only origin/main..HEAD`: `bot.py`
- `git diff origin/main..HEAD -- bot.py > WIP_bot_diff.patch`: completed

## 1. What WIP Commit `dc13b43` Changed

- Expanded `voice_profiles` with consent timestamp, source/preview references, default flag, and soft-delete timestamp.
- Added account-scoped Voice vault helpers and callbacks: list/select/listen/use/default/rename/delete/save.
- Reworked voice clone into consent -> upload voice/audio -> ask display name -> quote -> MiniMax upload/clone/TTS preview -> save.
- Split the main voice/music menu into two hubs: `Tạo giọng nói / Kho voice` and `Tạo nhạc / Kho nhạc / SFX`, plus media.
- Added no-voice/no-music and default male/female voice choices.
- Added subtitle/dub price helpers with named modes and 30-second extra blocks.
- Changed public-facing text around voice/music billing and readiness.

## 2. Completed Parts Of Voice/Music/Subtitle V2

- Voice menu split is present.
- `Kho voice của bạn` exists.
- `Tạo giọng mới` includes consent, upload, display-name prompt, fixed preview text, listen-preview, save, and set-default actions.
- Default male/female voices are labeled as free and stored as free selections.
- Music/SFX/media callbacks exist and open screens.
- Subtitle/dub helper modes exist: `subtitle`, `translate_subtitle`, `dubbing`, `subtitle_plus_dubbing`.
- Subtitle/dub pricing helper uses <=60-second base price and 30-second extra blocks.

## 3. Incomplete Parts

- Voice billing/retry/idempotency is unsafe.
- The new voice profile path has no dedicated tests.
- `use for current video` is only a generic guided-result update and is not fully wired into every video order flow.
- Suno has guarded/planning UX but no complete customer submit/poll/output flow.
- Music navigation did not fully preserve caller origin in the committed WIP.
- Subtitle/dub pricing broke existing order/invoice tests.
- `/test_all_video` was not fixed in the committed WIP.
- Public copy cleanup is incomplete.

## 4. PayOS, `/naptien`, Webhook, Wallet, Top-Up, DB Destructive, Secrets

- PayOS files: not touched.
- `/naptien`: not touched.
- Payment webhook: not touched.
- Top-up/package files: not touched.
- DB destructive logic: not touched.
- Provider secrets: no secret values added.
- Additive DB logic: touched through `voice_profiles`.
- Wallet/Xu behavior: touched by new `spend_fixed_credit_info` and `refund_charged_credit` calls in voice clone.

## 5. Deleted Or Hidden Buttons

Yes. The committed WIP hid or moved several buttons instead of preserving all tools in the new hierarchy.

- Moved/nested: Create voice, AI Music, Voice profile, Music library, SFX, Media, Add music.
- Hidden from new root/hubs in the committed WIP: STT/Transcribe, Add voice to video, Music prompt, Music policy, MiniMax status.
- This is confirmed by the failing existing test expecting the old direct `🎙 Tạo giọng đọc` label.

## 6. Voice Menu Split

Yes. The split exists:

- `Tạo giọng nói / Kho voice`
- `Tạo nhạc / Kho nhạc / SFX`

The split is directionally correct, but the committed WIP needs restoration of hidden sub-tools and caller-aware Back routing.

## 7. `Kho voice của bạn`

Exists and is DB-backed. It lists account-scoped profiles and supports preview/use/default/rename/delete. It is not sufficiently covered by tests.

## 8. `Tạo giọng mới`

Mostly present:

- Consent: yes.
- Upload voice/audio: yes.
- Ask display name: yes.
- Fixed preview text: yes.
- Listen preview: yes.
- Save voice profile: yes.
- Set default: yes.

Incomplete/risky:

- Charge/refund/retry semantics are unsafe.
- Concurrent confirm clicks are not idempotent.
- Use-for-current-video needs stronger video-flow integration.

## 9. Default Male/Female Voices

Yes. They are labeled `Miễn phí` and set `voice_is_free=True`.

## 10. Suno Button

The Suno button opens guarded/planning screens. It does not yet provide a complete public customer generation flow. It should show a friendly readiness guard when unavailable and admin status should show sanitized missing config.

## 11. Music/SFX/Media Menu

The screens open, but the committed WIP has navigation weaknesses and hidden tools. Current uncommitted work already starts restoring some missing buttons.

## 12. Subtitle/Dub Four Modes

The helper modes exist:

- `Tạo phụ đề tự động`
- `Dịch phụ đề`
- `Lồng tiếng`
- `Phụ đề + Lồng tiếng`

The UI/order/invoice path still needs complete coverage to guarantee named labels everywhere.

## 13. Subtitle/Dub Pricing

The WIP helper implements:

- <=60 seconds base prices.
- >60 seconds extra 30-second blocks.

Prices:

- Subtitle: 120 Xu base, +60 Xu per extra 30s.
- Translate subtitle: 150 Xu base, +75 Xu per extra 30s.
- Dubbing: 250 Xu base, +125 Xu per extra 30s.
- Subtitle + dubbing: 350 Xu base, +175 Xu per extra 30s.

Existing tests were still expecting older pricing, so they fail until the tests/order contracts are updated to V5.

## 14. Paid Button Labels

Partially. Some labels include task names, but V5 still needs tests to ensure paid buttons are never icon+price only.

## 15. User-Facing API/Provider/ENV/Raw Errors

Cleanup is incomplete. Some reachable text still mentions provider/API/public gate/smoke. New clone failure output is friendly, but other user screens need sanitizing.

## 16. `/test_all_video`

Not fixed by committed WIP. The command exists and is registered, but the old-schema crash risk remains unless additive `shopaikey_jobs` column migration or defensive query handling is added.

## 17. Safe To Continue From WIP

Useful but **not safe as-is**. Continue only by fixing the identified issues on the WIP branch, preserving valid V2 work, and not merging to main until tests and reports are complete.

## Safety Checks Before Continuation

- Literal `python -m py_compile bot.py`: unavailable locally because `python` is not on PATH.
- Literal `python -m py_compile local_worker.py`: unavailable locally because `python` is not on PATH.
- Bundled Python `py_compile bot.py`: PASS.
- Bundled Python `py_compile local_worker.py`: PASS.
- Bundled Python `pytest -q`: FAIL, `311 passed`, `5 failed`, `26 errors`, `3 warnings`.
- `git diff --check origin/main..HEAD`: PASS.
- `git status --short --untracked-files=no`: `M bot.py`

`pytest` is available, so this is not `PYTEST_NOT_AVAILABLE_LOCAL`. The 5 failures confirm menu/pricing regressions; the 26 errors are local temp/cache permission errors.
