# TOAN AAS Product Context Separation Hotfix - 2026-06-18

Branch: `hotfix/product-context-separation-voice-music-translation`

## 1. What Changed In `bot.py`

- Added product context primitives: `showroom` and `video_addon`.
- Added callback/context helpers: `product_context_callback`, `infer_product_context_from_callback`, `parse_product_context_callback`, `enter_product_context`, `current_product_context`.
- Split `/start` tools into independent Studio entry points:
  - Voice Studio
  - Music Studio
  - Translation / Subtitle / Dubbing Studio
- Enforced `product_context=showroom` for `/start` Voice/Music/Translation entry points and translation menu callbacks.
- Enforced `product_context=video_addon` for video finalization/add-on callbacks.
- Reworked Voice/Music keyboards so showroom and video add-on render different controls.
- Reworked saved voice profile actions so showroom can preview/read/download/manage, while video add-on can select a saved voice for the current video draft.
- Reworked music/SFX/media selection labels and routing so video add-on updates the current video draft, while showroom remains standalone.
- Reworked subtitle/dub add-on menu pricing to use 60-second started blocks after the first 60 seconds.
- Added context-specific copy that avoids exposing raw provider/API/ENV wording on the new product surfaces.

## 2. What Is Completed

- `product_context=showroom/video_addon` is implemented and enforced for Voice/Music/Translation surfaces.
- Showroom no longer requires a video session or invoice.
- Showroom hides video-only controls such as "Không thêm giọng", "Không thêm nhạc", "Chọn cho video", and "Quay lại video".
- Video add-on keeps the current video draft/order while selecting free voice/music/media options.
- Video add-on keeps no-voice/no-music/free-stock choices separate from paid generation/clone/dubbing choices.
- Translation Studio restored existing language/video-dub branches, so features were not deleted while still entering showroom context.
- Regression tests prove context separation.

## 3. What Is Incomplete

- No known blocker remains for this hotfix.
- Global legacy/admin diagnostics still contain technical words like API/provider/ENV where they are intentionally diagnostic; the new Voice/Music/Translation product surfaces tested in this hotfix do not leak those terms.

## 4. Risky Changes

- Medium risk: `bot.py` callback routing changed in a broad Voice/Music/Translation area.
- Mitigation: added dedicated context separation tests and ran the full test suite.
- No payment/top-up/PayOS/webhook/wallet logic was modified.
- No destructive DB logic was modified.

## 5. Deleted Or Hidden Buttons

- No product feature was intentionally deleted.
- The old combined `/start` button `Giọng nói / Nhạc` was replaced by separate Studio buttons.
- Showroom intentionally hides video-only buttons:
  - `Không thêm giọng`
  - `Không thêm nhạc`
  - `Chọn cho video`
  - `Dùng cho video hiện tại`
  - `Quay lại video`
- Video add-on still shows the relevant no-add/free-choice buttons inside the video flow.

## 6. PayOS / Top-Up / DB / Payment Files Touched

- PayOS files touched: NO
- `/naptien` touched: NO
- Webhook touched: NO
- Wallet/top-up/payment touched: NO
- DB destructive logic touched: NO
- Changed files are limited to `bot.py`, tests, and this report.

## 7. `/test_all_video`

Status: YES, verified.

The existing regression `test_test_all_video_does_not_crash` passed in the full pytest run.

## 8. Self-Shot Video Upload First

Status: YES, verified.

Existing self-shot tests, including the upload-first guard, passed in the full pytest run.

## 9. Music / Voice / Subtitle Flow Completeness

Status: YES for context separation.

- Showroom creates/handles standalone Studio actions.
- Video add-on preserves source file/video file ID, package/tier, duration, object/direction, invoice/source payload, and selected add-ons.
- Paid provider work remains guarded behind later confirmation.

## 10. User-Facing Technical Text

New product surfaces checked by tests do not contain raw `API`, `provider`, `ENV`, `HTTP`, `traceback`, or `raw error` wording.

Legacy/admin diagnostics outside this hotfix still contain technical terms by design and were not globally rewritten.

## 11. Tests Run

- `py -m py_compile bot.py`: `PY_LAUNCHER_NOT_AVAILABLE_LOCAL`
- Bundled Python `python -m py_compile bot.py`: PASS
- Bundled Python `python -m py_compile local_worker.py`: PASS
- Bundled Python `python -m pytest -q -p no:cacheprovider --basetemp <workspace-temp>`: PASS, `395 passed, 1 warning`
- `git diff --check`: PASS

## 12. Safe To Continue

YES.

## 13. Safe To Merge Main

YES, after normal review. Main was not pushed or merged by this task.
