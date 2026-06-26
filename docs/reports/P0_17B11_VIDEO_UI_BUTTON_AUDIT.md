# P0.17B11 Video UI Button Audit

Scope: Video UI/UX cleanup only. No product engine, provider, payment, pricing, voice, music, image menu, ASR/subtitle/dubbing, DB, or web/app changes.

Files touched:

- `bot.py`
- `tests/test_p0_17b11_video_ui_ux_cleanup.py`
- `tests/test_task3d_video_product_prompt_engine.py`
- `tests/test_task3d7_video_lock_dedupe_public_guards.py`
- `docs/reports/P0_17B11_VIDEO_UI_BUTTON_AUDIT.md`

## Main Video Menu

| Button label | Callback | Current behavior before P0.17B11 | Fixed behavior | Work/guard status |
| --- | --- | --- | --- | --- |
| 🔥 Video theo trend | `vproduct\|open\|video_trend` | Opens trend planning screen. | Preserved. Opens planning screen with safe no-charge copy. | Works, no Xu before confirm. |
| 🧠 Ý tưởng video | `vproduct\|open\|video_idea` | Opens idea planning screen. Number choices could wrap 2+2+1. | Preserved. Numeric suggestions use compact row for 1-5. | Works, no Xu before confirm. |
| 🎬 Storyboard + Prompt | `vproduct\|open\|storyboard_prompt` | Opens storyboard/prompt planning screen. | Preserved. Number-only prompt selectors use compact numeric layout where applicable. | Works, no Xu before confirm. |
| 📚 Kho prompt video | `vpromptlib\|start` | Opens prompt library. | Preserved. Stays in Video menu with clean no-charge prompt-only copy. | Works, no Xu before confirm. |
| 🎬 Video AI chân thật | `vproduct\|open\|video_ai_real` | Opens guided prompt planning. | Preserved. Back remains Video menu. | Works, no Xu before confirm. |
| 🧩 Kịch bản → Video | `vproduct\|open\|script_image_video` | Opens script-to-video planning. | Preserved. Back remains Video menu. | Works, no Xu before confirm. |
| 🎞 Ghép ảnh thành video | `vproduct\|open\|frame_video_local` | Opens unified image slideshow/merge flow. | Preserved from locked image-to-video flow. Back remains Video menu. | Works/guarded by existing flow, no Xu before final confirm. |
| 🎥 Tự quay & đổi cảnh AI | `vproduct\|open\|self_shot_scene_change` | Opens self-shot scene planning. | Preserved. Back remains Video menu. | Works as planning/guard, no Xu before confirm. |
| 🎬 Phim AI nhiều cảnh | `vproduct\|open\|multi_scene_film` | Opens multiscene planning. Previously on lonely row. | Preserved and paired with downloader in Row 5. | Works/guarded by existing finalization, no Xu before confirm. |
| 📥 Tải video từ link | `vdownload\|start` | Opens link downloader utility. Previously on lonely row. | Preserved and paired with multiscene in Row 5. Public-disabled copy says the tool is being prepared and no Xu is charged. | Guarded by `VIDEO_DOWNLOADER_PUBLIC_ENABLED=false`, no Xu charge. |
| 🛠 Chỉnh sửa video local | `vproduct\|open\|video_local_edit` | Intro buttons routed through one legacy callback and could surface a generic red error in some paths. | Intro buttons route to explicit `videoedit` handlers: upload, cut, resize, compress. Missing video asks for upload; compress has clean guard when not ready. | Works/guarded, no provider call, no Xu charge. |
| 🏠 Menu chính | `menu\|main` | Returns to main menu. | Preserved. | Works. |

## Hidden Public Entries

| Button label | Status |
| --- | --- |
| 🖼 Ảnh → Video | Hidden as duplicate. Unified product remains `🎞 Ghép ảnh thành video`. |
| 🎵 Nhạc / Voice / SFX | Hidden from public Video main menu. |
| 📥 Video mẫu / Kênh mẫu | Hidden from public Video main menu. |
| 🎥 Prompt / Chuyển động | Hidden from public Video main menu. |

## Local Edit Buttons

| Button label | Callback | Fixed behavior |
| --- | --- | --- |
| 📎 Gửi video | `videoedit\|upload` | Asks user to upload a video first; after upload returns to local edit menu. |
| ✂️ Cắt video | `videoedit\|cut` | If no video is available, asks user to upload first. With video, continues to the existing ratio/crop selection. |
| 📐 Đổi tỉ lệ | `videoedit\|resize` | If no video is available, asks user to upload first. With video, continues to the existing ratio/crop selection. |
| 🗜 Nén video | `videoedit\|compress` | If no video is available, asks user to upload first. With video, shows clean prepared/guard copy and returns to Video menu or main menu. |

Clean guard copy:

`Chỉnh sửa video local đang được chuẩn bị. TOAN AAS chưa xử lý và chưa trừ Xu. Anh/chị có thể quay lại menu video hoặc thử công cụ khác trước.`

## Layout Audit

- Main Video menu now has 6 rows, 2 buttons per row.
- `🎬 Phim AI nhiều cảnh` and `📥 Tải video từ link` are paired in Row 5.
- Number-only choices use compact rows:
  - 1-5 numbers: one row.
  - 6 numbers: 3 + 3.
  - 7-8 numbers: 4 + 4.

## Safety

- PayOS/wallet/payment: not touched.
- Pricing: not touched.
- Music/Suno: not touched.
- Voice/TTS/custom voice: not touched.
- ASR/subtitle/dubbing: not touched.
- Image menu: not touched.
- Video engine/provider core: not touched.
- DB schema/destructive migration: not touched.
- Web/app/standalone: not touched.
