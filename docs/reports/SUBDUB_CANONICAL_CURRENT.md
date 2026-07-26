# SubDub Canonical Current Runtime

Last verified: 2026-07-26

## Production Baseline

- Repository: `manhtoangreensky-wq/bot`
- Railway project/service: `selfless-abundance` / `bot`
- Canonical deployed merge: `55fde0c89f49b8957c29089ca753ecb413876ccb`
- Route-owner repair: PR `#523`, commit `d5cc92c078f629c868339b932c78d2fa79d8acd5`
- Historical comparison point requested by product owner: `7ab63f3` (PR #400 state)

Do not restore an old `bot.py` wholesale. Compare the exact function or route, write a focused regression, and change only the proven broken boundary.

## Locked UI And Routes

The current Telegram UI/UX is the product baseline. Do not redesign it in an engine or MP4 repair.

| Lane | Canonical mode |
| --- | --- |
| Auto subtitle from source audio | `subtitle_create` |
| Subtitle translation | `subtitle_translate` |
| Dubbing | `dub` |
| Subtitle and dubbing | `subtitle_plus_dub` |

Canonical owners in `bot.py`:

- Menu: `video_dubbing_menu_keyboard`
- Source: `video_dubbing_source_keyboard`
- Language: `video_dubbing_language_keyboard`
- Voice: `video_dubbing_voice_keyboard`
- Confirmation: `video_dubbing_confirm_keyboard`
- Back routing: `video_dubbing_back_route`
- Callback owner: `handle_video_dubbing_callback`
- Pending text owner: `handle_video_dubbing_pending_text`
- Final callback: `videodub|final`
- Pipeline executor: `execute_video_dubbing_pipeline`
- Core executor: `_execute_video_dubbing_pipeline_core`

`VIDEO_DUBBING_PENDING_TEXT_STEPS` and `subdub_text_input_owns_message` must remain defined before generic product text handlers. Removing them breaks pending SubDub input and can prevent all four lanes from reaching the canonical executor.

## MP4 And Terminal Contract

- A video lane is not successful without a valid real MP4 and a Telegram artifact `message_id`.
- The progress panel reaches 100 percent only after artifact delivery.
- Send one receipt only; refresh and retry must not send a second receipt.
- Do not use a generic or unrelated Telegram message ID as delivery evidence.
- Do not call a paid provider in automated tests.
- Do not claim LIVE MP4 PASS from mocks or static checks.

## Current Evidence

- GitHub Python 3.11 source compile gate passed for PR #523.
- Railway build `55fde0c` is deployed successfully.
- `/`, `/health`, and `/status` returned HTTP 200.
- Railway DB health returned OK.
- Telegram webhook belongs to the current Railway domain, with no pending updates or last error at verification time.
- Production no longer logs the missing `VIDEO_DUBBING_PENDING_TEXT_STEPS` `NameError` after deploy.
- Provider calls during repair: 0.
- Real media acceptance after this repair: not performed.
- LIVE MP4 PASS claimed: NO.

## Scope Lock

Do not touch Product Video, Music/Suno, PayOS, wallet/Xu, Storage, or the standalone webapp in a SubDub repair unless a separate explicit task authorizes it.

