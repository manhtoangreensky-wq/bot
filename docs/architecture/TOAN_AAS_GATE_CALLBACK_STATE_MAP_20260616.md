# TOAN AAS Gate / Callback / State Map - 2026-06-16

Audit base commit: `fcb8f5d`

This map is a static audit of `bot.py`. It is not a runtime smoke result.

## Callback Registry

| Module | Button label | Callback | Handler found | Parent | Back target | Status | Note |
|---|---|---|---:|---|---|---|---|
| Main | Công cụ miễn phí | `freehub|main` | yes | main | `menu|main` | READY_PUBLIC | Content-only tools; no provider charge. |
| Main | Tài khoản | `menu|main_profile` | yes | main | `menu|main` | READY_PUBLIC | Account/member/referral surface. |
| Main | Tạo ảnh AI | `menu|main_image` | yes | main | `menu|main` | READY_PUBLIC | Image menu recently locked to 4 main buttons. |
| Main | Tạo video AI | `menu|main_video` | yes | main | `menu|main` | READY_PUBLIC | Video menu is large; execution gated downstream. |
| Main | Ghi chú / Tài liệu | `menu|main_memory` | yes | main | `menu|main` | READY_PUBLIC | Notes/docs/storage hub. |
| Main | Dịch thuật | `menu|translate` | yes | main | `menu|main` | READY_PUBLIC | Translation hub split into language and video branches. |
| Main | Giọng nói / Nhạc | `menu|main_music` | yes | main | `menu|main` | READY_PUBLIC | Voice/music menu with provider guards. |
| Main | Nạp Xu / Bảng giá | `pricing|main` | yes | main | `menu|main` | STABLE_LOCKED | Payment/top-up area locked. |
| Main | Hỗ trợ | `menu|support` | yes | main | `menu|main` | READY_PUBLIC | Opens support/ticket surface. |
| Main | Góp ý / Báo lỗi | `feedback|start` | yes | main | `menu|main` | READY_PUBLIC | Feedback schema migration previously stabilized. |
| Main | Admin | `menu|admin` | yes | main | `menu|main` | READY_ADMIN_ONLY | Must stay admin-only. |
| Image | Tạo ảnh nhanh | `create_media|quick_image` | yes | image | `menu|main_image` / flow back | READY_PUBLIC | Suggestion -> prompt -> ratio -> tier -> confirm. |
| Image | Tạo prompt từ ảnh | `menu|image_prompt_start` | yes | image | `menu|main_image` | READY_PUBLIC | Uses `imgtool|prompt_*` states after entry. |
| Image | Chỉnh sửa AI | `imgtool|edit_ai_start` | yes | image | `menu|main_image` | GUARDED | Provider edit guarded; can produce prompt/flow guard. |
| Image | Chỉnh sửa ảnh | `menu|image_edit_start` | yes | image | `menu|main_image` | READY_PUBLIC | Local edit/crop/resize submenu. |
| Image edit submenu | Preset/local edit | `imgtool|editor_*` | yes | image edit | submenu/image | READY_PUBLIC | Uses recent image or waits for image. |
| Image edit submenu | AI upscale/aspect | `imgtool|resize_task|ai_*` | yes | image edit | submenu | GUARDED | AI upscale/aspect guarded if not ready. |
| Video menu | Video theo trend | `trendg|start` | yes | video | `menu|main_video` | READY_PUBLIC | Planning/prompt flow. |
| Video menu | Video AI chân thật | `menu|video_ai_true` | yes | video | `menu|main_video` | GUARDED | Submenu to prompt/image/reference to video. |
| Video menu | Kịch bản -> Ảnh -> Video | `storyboard|start` | yes | video | `menu|main_video` | GUARDED | Image/video provider paths gated. |
| Video menu | Ghép ảnh thành video | `menu|video_frame_intro` -> `framevideo|start` | yes | video | `menu|main_video` | GUARDED | Requires Local Worker/ffmpeg guard. |
| Video menu | Tự quay & đổi cảnh AI | `selfscene|start` | yes | video | `menu|main_video` | PLANNING_ONLY/GUARDED | Leads to plan/finalization. |
| Video menu | Phim AI nhiều cảnh | `longvideo|start` | yes | video | `menu|main_video` | PLANNING_ONLY | Should not render long jobs publicly. |
| Video menu | Storyboard + Prompt điện ảnh | `storypack|start` | yes | video | `menu|main_video` | GUARDED | Needs manual flow QA; no placeholder accepted. |
| Video menu | Video mẫu / Kênh mẫu | `videoref|hub` | yes | video | `menu|main_video` | GUARDED | Reference learning/channel pack path. |
| Video menu | Ý tưởng video | `videoidea|start` | yes | video | `menu|main_video` | READY_PUBLIC | Planning-only ideas. |
| Video menu | Prompt / Chuyển động | `motion|start` | yes | video | `menu|main_video` | READY_PUBLIC | Planning-only motion prompt. |
| Video menu | Dịch/Lồng tiếng video | `videodub|start` | yes | video | `menu|main_video` | GUARDED | Also accessible from Translation hub. |
| Video menu | Chỉnh sửa video local | `videoedit|menu` | yes | video | `menu|main_video` | GUARDED | Requires Local Worker for real output. |
| Real AI video | Prompt -> Video AI | `promptvideo|start` | yes | video AI | `menu|video_ai_true` | GUARDED | Final render depends on video gate. |
| Real AI video | Ảnh -> Video AI | `imagevideo|start` | yes | video AI | `menu|video_ai_true` | GUARDED | Requires image and provider gate. |
| Real AI video | Video mẫu -> Video AI | `videoref|start` | yes | video AI | `menu|video_ai_true` | GUARDED | Reference provider path guarded. |
| Finalization | Add-ons | `vfinal|music`, `vfinal|voice`, `vfinal|subtitle`, `vfinal|combo` | yes | finalization | `vfinal|menu` | READY_PUBLIC/GUARDED | No provider until invoice/confirm. |
| Finalization | Choose package | `vfinal|tier` / `vfinal|tier|*` | yes | finalization | `vfinal|menu` | GUARDED | Tier status controls whether package can proceed. |
| Finalization | Confirm export | `vfinal|export_ai` | yes | finalization | `vfinal|tier` / back callback | GUARDED | Must route to provider only if public/admin ready. |
| Finalization | Local export | `vfinal|export_local` | yes | finalization | `vfinal|review` | GUARDED | Requires >=2 photos and Local Worker readiness. |
| Finalization | Copy prompt | `vfinal|copy_prompt` | yes | finalization | current | READY_PUBLIC | Safe fallback when video not ready. |
| Translation | Language hub | `menu|translation_language_hub` | yes | translate | `menu|translate` | READY_PUBLIC | Parent language branch. |
| Translation | Video dub hub | `menu|translation_video_dub_menu` | yes | translate | `menu|translate` | GUARDED | Should not route back to generic video menu unless user chooses video. |
| Translation | Target language | `tr_target|...` | yes | translate | `tr_pick|...` | READY_PUBLIC | Registered as `tr_*`. |
| Translation | Pair start/swap | `menu|translation_pair_*` | yes | translate | language hub | READY_PUBLIC | Uses translation session. |
| Support | Support start | `support|start` | yes | support | `menu|main` | READY_PUBLIC | Public support menu. |
| Support | Create ticket | `support|ticket` / `ticket|cat|*` | yes | support | support menu | READY_PUBLIC | Must reply with ticket code after user input. |
| Support | Ticket of mine | `ticket|mine` | yes | support | support menu | READY_PUBLIC | User ticket list. |
| Admin | Provider status | `menu|admin_provider_status` | yes | admin | `menu|admin_provider` | READY_ADMIN_ONLY | No secrets. |
| Admin | Freeze/queue | `menu|freeze_queue*` | yes | admin | `menu|admin` | READY_ADMIN_ONLY | Shows freeze/queue commands. |
| Storage | Add storage | `menu|memory_storage_addon` / `storage|*` | yes | memory | `menu|main_memory` | GUARDED | Uses storage add-on order path. |
| Docs | PDF/Word tools | `menu|main_docs`, `docflow|*` | yes | memory/docs | `menu|main_memory` | READY_PUBLIC/GUARDED | Local tools may guard if engine missing. |

## Registered Callback Groups

`bot.py` registers the following customer/admin callback groups:

- `music_quick|`, `sfx_quick|`, `media_quick|`
- `play_sfx|`, `play_music|`, `select_sfx|`, `select_music|`
- `image_story_*`
- `trendg|`, `tvflow|`
- `motion|`
- `adconcept|`
- `promptvideo|`
- `imagevideo|`
- `videoref|`
- `videodub|`
- `marketing|`
- `selfscene|`
- `longvideo|`
- `storypack|`
- `videoidea|`
- `video_upload|`
- `videoedit|`
- `storyboard|`
- `vfinal|`
- `videoaddon|`
- `create_media|`
- `framevideo|`
- `suggest_music|`
- `shopai|`
- `shopai_video_job|`
- `support|`
- `ticket|`
- `feedback|`
- `imgtool|`
- `storage|`
- `memory|`
- `tr_*`
- `lang|`
- `pkgbuy|`
- `pricing|`
- `buy_plan|`
- `docflow|`
- `archive|`
- `freehub|`
- `menu|`
- `prov|`
- `payosalert|`
- `manual|`
- `payos_pkg|`, `pkg|`
- `job|`
- `pipe|`
- `trend|`
- `creative|`
- `task|`
- `opmenu|`

## State Registry

| State key | Module | Set by | Consumed by | Cleared by | Risk | Status |
|---|---|---|---|---|---|---|
| `image_ai_edit_state` | Image AI edit | Implemented under image menu pending actions like `image_edit_*`; no literal key found | image edit callback/text/media handlers | image pending clear | Naming mismatch vs task text can confuse audits | READY via `image_menu_pending` |
| `image_edit_state` | Local/AI image tools | `set_image_menu_pending(...)` | `handle_image_tools_callback`, pending text/image handlers | `clear_image_menu_pending` | Many substeps; live QA back routing needed | READY_PUBLIC/GUARDED |
| `video_storyboard_state` | Storyboard image/video | `set_storyboard_state` | `handle_storyboard_callback`, `handle_storyboard_pending_text` | `clear_storyboard_state` | Requires project restore for persisted actions | GUARDED |
| `video_prompt_state` | Video prompt/finalization | developing video state + `video_finalization_state` | prompt/video/finalization callbacks | clear finalization/developing state | Multiple sources feed finalization; must keep back callback correct | GUARDED |
| `video_export_state` | Final video export | `set_video_finalization_state` | `handle_video_finalization_callback` | clear media creator/finalization | Most sensitive user-facing gate | GUARDED |
| `video_beta_state` | Public beta gate | system settings/runtime flags | status/open/close commands and tier checks | `/video_beta_close` / admin settings | Depends on live runtime, provider smoke | GUARDED |
| `translation_session_state` | Translation | `set_translation_session` | translation callback/text routing | `clear_translation_session` | Language continuity/back route must be QA'd | READY_PUBLIC |
| `support_ticket_state` | Support/tickets | `set_support_ticket_pending` | support/ticket callbacks and text handler | `clear_support_ticket_pending` | Must answer user before/with ticket creation | READY_PUBLIC |
| `billing_promo_state` | Promo/payment | `user_promo_state` table + promo helpers | PayOS order attach | clear after attach/redeem/expiry | Payment locked; audit only | STABLE_LOCKED |
| `manual_topup_state` | Manual top-up | `set_manual_bill_state` | manual callback/payment bill handler | after submission/cancel | Payment locked; do not edit casually | STABLE_LOCKED |
| `storage_upload_state` | Notes/docs storage | storage add-on pending + doc/memory states | storage callback/doc handlers | clear storage addon pending | PayOS extension must remain isolated | GUARDED |
| `free_hub` | Free tools | `set_free_hub_pending` | freehub callback and text handler | clear pending | Should remain content-only | READY_PUBLIC |
| `frame_video` | Frame video | `set_frame_video_state` | frame video callback/render | `clear_frame_video_state` | OOM risk if direct render enabled; worker preferred | GUARDED |
| `manual_approval_state` | Admin manual top-up | `set_manual_approval_state` | admin approval callback/commands | approval complete/cancel | Payment locked | STABLE_LOCKED |

## Gate Rules Summary

### Image

- Public image requires public image flag/provider guard.
- Pricing/tier confirmation occurs before deduct.
- Provider failure refunds or avoids charge.
- Warranty tiers keep separate retry counts.

### Video

- Planning/storyboard/prompt flows are content-only until finalization.
- Prompt-based AI video should require prompt + tier + video public/provider gate, not local image count.
- Local frame video requires images + worker/ffmpeg gate.
- 200 Xu beta is off unless admin explicitly sets marketing-loss override.
- 600+ and premium remain off.

### Translation

- Short text translation/session setup is public.
- Voice/audio/video translate/dub paths are guarded by ASR/TTS/provider readiness and must show confirm before cost.

### Support

- Support should produce immediate user-facing guidance and ticket/lead when needed.
- Ticket admin remains admin-only.

### Storage

- 50MB free policy + add-on plans are separate from top-up packages.
- Storage add-on payment must use existing PayOS bridge and should not mutate top-up logic.

