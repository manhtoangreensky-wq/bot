# P0.18B Live Video UX Callback Audit

Branch: `hotfix/p0-18b-live-video-ux-callback-addon-repair`

Base: `origin/main` after P0.18A deploy, live build `1ace9dd`.

## Scope

This audit covers only the live video UX callback layer:

- `vproduct|...` B14/B18 video planner callbacks
- add-on summary/submenus and local back routes
- voice/subtitle/dub add-on planning state
- uploaded-video subtitle translation language callback
- admin-only dry-run command for the live button path

Not touched: PayOS, wallet/Xu ratio, B13 render/stitch internals, VPS W1-W5 worker internals, Suno/music provider core, web/app/standalone.

## Callback Matrix

| UI action | Callback |
| --- | --- |
| Mau sac | `vproduct|b14_creative_field|color_palette` then `vproduct|b14_creative_set|color_palette|...` |
| Cam xuc | `vproduct|b14_creative_field|emotion_tone` then `vproduct|b14_creative_set|emotion_tone|...` |
| Legacy mau sac compatibility | `vproduct|b14_creative_field|color_tone` maps to `color_palette` |
| Legacy cam xuc compatibility | `vproduct|b14_creative_field|mood` maps to `emotion_tone` |
| Xem storyboard/prompt | `vproduct|b14_creative_done` |
| Dung bo ngu canh / tiep tuc | `vproduct|storyboard_confirm` |
| Xem prompt anh | `vproduct|b14_prompt_image_text` |
| Xem prompt video | `vproduct|b14_prompt_video_text` |
| Xuat bo prompt | `vproduct|b14_export_pack` |
| Cau hinh add-ons | `vproduct|b14_addons` |
| Voice submenu | `vproduct|b14_addon_voice` |
| Voice: khong voice | `vproduct|b14_voice_source|none` |
| Voice: nu mac dinh | `vproduct|b14_voice_source|default_female` |
| Voice: nam mac dinh | `vproduct|b14_voice_source|default_male` |
| Voice da gui | `vproduct|b14_voice_source|uploaded` |
| Voice da luu | `vproduct|b14_voice_source|saved` / `vproduct|b14_voice_saved_pick|<id>` |
| Tao voice rieng legacy/fallback | `vproduct|b14_voice_source|custom` |
| Sua loi doc | `vproduct|b14_voice_edit` |
| Nghe thu ngan | `vproduct|b14_voice_preview` |
| Am luong giong | `vproduct|b14_voice_volume` / `vproduct|b14_voice_volume_set|...` |
| Xong voice | `vproduct|b14_voice_done` |
| Nhac nen submenu | `vproduct|b14_addon_music` |
| Nhac mac dinh | `vproduct|b14_music_source|default` |
| Kho nhac | `vproduct|b14_music_source|vault` |
| Kho SFX | `vproduct|b14_music_source|sfx_vault` |
| Media cua toi | `vproduct|b14_music_source|media` |
| Ghep/cat nhac rieng | `vproduct|b14_music_cut` |
| Am luong nhac | `vproduct|b14_music_volume` / `vproduct|b14_music_volume_set|...` |
| Xong nhac | `vproduct|b14_music_done` |
| Phu de submenu | `vproduct|b14_addon_subtitle` |
| Tat phu de | `vproduct|b14_subtitle_source|none` |
| Phu de theo loi doc | `vproduct|b14_subtitle_source|from_narration` |
| Dich phu de | `vproduct|b14_subtitle_translate` then `vproduct|b14_subtitle_lang|...` |
| Sua noi dung phu de | `vproduct|b14_subtitle_edit` |
| Xem thu SRT | `vproduct|b14_subtitle_preview` |
| Xong phu de | `vproduct|b14_subtitle_done` |
| Long tieng submenu | `vproduct|b14_addon_dub` |
| Tat long tieng | `vproduct|b14_dub_set|none` |
| Chon ngon ngu long tieng | `vproduct|b14_dub_lang|...` |
| Ngon ngu khac | `vproduct|b14_dub_other` |
| Xong long tieng | `vproduct|b14_dub_done` |
| Logo submenu | `vproduct|b14_addon_logo` / `vproduct|b14_logo_set|...` |
| SFX submenu | `vproduct|b14_addon_sfx` / `vproduct|b14_sfx_set|...` |

## Backstack Matrix

| From screen | Back callback | Expected destination |
| --- | --- | --- |
| Storyboard/prompt | `vproduct|b14_creative_screen` | Creative controls |
| Add-ons summary | `vproduct|b14_creative_done` | Storyboard/prompt |
| Voice submenu | `vproduct|b14_addons` | Add-ons summary |
| Music submenu | `vproduct|b14_addons` | Add-ons summary |
| Subtitle submenu | `vproduct|b14_addons` | Add-ons summary |
| Dub submenu | `vproduct|b14_addons` | Add-ons summary |
| Logo submenu | `vproduct|b14_addons` | Add-ons summary |
| SFX submenu | `vproduct|b14_addons` | Add-ons summary |

Menu chinh remains only `menu|main`.

## Broken Live Causes

1. Emotion/color overlap:
   - Old emotion callback used `mood`.
   - Old values were English production descriptors like `reflective emotional mood` or profile goals, which read like style/pacing rather than viewer feeling.
   - Fix: primary state keys are `creative.color_palette` and `creative.emotion_tone`; legacy `color_tone`/`mood` map into those keys only for compatibility.

2. Storyboard/prompt generic error:
   - The storyboard actions relied on a valid B14 session and could fall through to the generic expired/generic error path if the live message carried an old/missing session.
   - Fix: storyboard/prompt actions rebuild from current idea/profile when data is missing, and missing sessions get a recovery screen instead of a generic error.

3. Add-on back routes:
   - Some add-on choices returned directly to summary without a real submenu/done path.
   - Fix: Voice/Music/Subtitle/Dub keep dedicated screens; Back from each submenu returns to add-ons summary; Add-ons Back returns storyboard/prompt.

4. Voice add-on:
   - Default voice existed but needed to stay in the voice submenu after apply and save narration from storyboard.
   - Custom voice legacy action needed a clear quality-lock fallback instead of a dead placeholder.

5. Subtitle add-on:
   - Generated-video subtitle translation is planning only before final confirm and must not show uploaded-video provider guard copy.
   - Fix: `b14_subtitle_translate` opens language selection; language selection updates `addon_plan` and returns to the subtitle submenu.

6. Uploaded-video subtitle translation:
   - `videodub|language|...` still had a live branch that called translation immediately when media was present.
   - Fix: language selection now moves to confirm/guard planning; provider work waits for `videodub|final`.

## Regression Coverage

- `test_creative_color_and_emotion_are_distinct`
- `test_emotion_does_not_write_color_palette`
- `test_color_does_not_write_emotion_tone`
- `test_emotion_output_vietnamese_friendly`
- `test_fast_style_does_not_duplicate_color_emotion`
- `test_storyboard_prompt_from_creative_no_error`
- `test_storyboard_builds_if_missing`
- `test_storyboard_missing_session_recover`
- `test_storyboard_buttons_have_handlers`
- `test_storyboard_back_returns_creative`
- `test_addons_back_to_storyboard`
- `test_voice_back_to_addons`
- `test_music_back_to_addons`
- `test_subtitle_back_to_addons`
- `test_dub_back_to_addons`
- `test_logo_back_to_addons`
- `test_sfx_back_to_addons`
- `test_video_voice_default_female_applies_and_returns`
- `test_video_voice_default_male_applies_and_returns`
- `test_video_voice_custom_not_ready_has_fallback`
- `test_video_subtitle_translate_language_applies`
- `test_uploaded_video_subtitle_language_no_false_ready`
- `test_dub_language_applies_to_addon_plan`
- `test_tool_test_live_video_ux_regression_no_charge`
