# TOAN AAS i18n Language Sync Audit

## 1. Summary

Supported languages in active public audit: `vi`, `en`.

Default language: `vi`.

User language storage: existing bot helpers such as `get_user_language`, `user_ui_lang`, `normalize_user_language`, and localized keyboard/text helpers.

Missing translation keys: no centralized JSON locale files exist yet. The codebase currently uses Python helper dictionaries plus localized functions. This is workable short-term but should be centralized later.

Hard-coded public texts: still present in many feature handlers because the bot is large. This pass only fixed high-visible menu labels and Storyboard planning flow text.

Mixed-language flows fixed in this pass:
- Main menu Vietnamese no longer shows `Voice / Nhạc`.
- Main menu Vietnamese no longer shows `Hub`; it now shows `Trung tâm`.
- Storyboard + Prompt điện ảnh has Vietnamese guided flow and English guard support for video AI safety message.

## 2. Main Menu vi/en

VI expected/checked:
- `🆓 Công cụ miễn phí`
- `👤 Tài khoản`
- `🖼 Tạo ảnh AI`
- `🎬 Tạo video AI`
- `📝 Ghi chú / Tài liệu`
- `🌐 Dịch thuật`
- `🎙 Giọng nói / Nhạc`
- `💰 Nạp Xu / Bảng giá`
- `📚 Hướng dẫn`
- `👨‍💼 Hỗ trợ`
- `💬 Góp ý / Báo lỗi`
- `🌐 Trung tâm`

EN expected/checked:
- `🆓 Free tools`
- `👤 My Account`
- `🖼 AI Image`
- `🎬 AI Video`
- `📝 Notes / Docs`
- `🌐 Translation`
- `🎙 Voice / Music`
- `💰 Top up / Pricing`
- `📚 Guide`
- `👨‍💼 Support`
- `💬 Feedback / Bug`
- `🌐 Hub`

Admin button remains admin-only.

## 3. Module Translation Coverage

| Module | vi | en | Missing | Mixed text | Status |
| ------ | -- | -- | ------- | ---------- | ------ |
| Main menu | yes | yes | zh/ja/ko full copy | fixed vi mixed labels | PASS |
| Free Hub | mostly | mostly | full locale extraction | minimal | PASS/GUARDED |
| Translation | mostly | partial | deeper subflow text | needs more smoke | WATCH |
| Image | mostly | partial | provider errors | unknown | WATCH |
| Video | mostly | partial | finalization deep flow | P1 finalization issue | WATCH |
| Storyboard + Prompt | yes | guard partial | non-vi detailed copy | no P1 found | PASS |
| Voice/Music | label fixed | partial | deep guards | some terms technical | WATCH |
| Documents/Storage | mostly | partial | storage/payment text | not audited deeply | WATCH |
| Billing/PayOS | do not touch | do not touch | not in scope | locked | LOCKED |
| Support/Feedback | mostly | partial | live smoke needed | not audited deeply | WATCH |

## 4. Hard-coded Text Found

| File | Function/Area | Text | Should be key | Severity |
| ---- | ------------- | ---- | ------------- | -------- |
| `bot.py` | `storyboard_pack_*` | Storyboard public text | future locale key | P3 |
| `bot.py` | Main menu keyboard | Labels | future locale key | P2 |
| `bot.py` | many handlers | Guard/error text | future locale key | P2 |

Decision: do not refactor all text into JSON in this pass because that would be a large rewrite and risky.

## 5. Mixed Language Bugs

| Flow | Steps | Expected | Actual before | Fix |
| ---- | ----- | -------- | ------------- | --- |
| Main menu VI | `/start` | Vietnamese public labels | `Voice / Nhạc`, `Hub` | Changed to `Giọng nói / Nhạc`, `Trung tâm` |
| Storyboard | Video -> Storyboard | Vietnamese guided flow | placeholder only | Rebuilt flow |
| Storyboard guard EN | AI video guard | English no-charge message | partial | Added English guard copy |

## 6. Fixed in This Task

- Main menu Vietnamese labels corrected.
- Storyboard planning flow now uses user-language helpers where practical.
- Storyboard guard has English fallback.
- Tests added for main menu vi/en label separation and Storyboard guard/back callbacks.

## 7. Remaining i18n Backlog

1. Extract high-traffic public labels into a centralized locale dictionary.
2. Add English smoke tests for Translation, Image, Video, Voice/Music, Notes/Documents.
3. Ensure provider prompts request output in user interface language except Translation target flows.
4. Ensure every `common.back` and `common.main_menu` button uses current interface language.
5. Build a missing-key scanner after locale extraction exists.

## 8. Next Languages Prepared

Planned fallback languages: `zh`, `ja`, `ko`, `th`, `id`, `fr`, `es`.

Current recommendation: keep these fallbacking to English unless a complete public-language pass is done.

