# Telegram Callback Handler Evidence Inventory — 06/10/2026

Source baseline: `0929d61ade4b8f0d60b803b62417763e90acce9e`. Production deployment of this SHA was verified separately; the table inventories source registrations, not live execution of every route.

## Measured source inventory

- 87 direct add_handler(CallbackQueryHandler(...)) calls; 85 distinct callback function expressions.
- 83 registrations have literal regex patterns; guard/observer and any dynamic-pattern entries are listed explicitly.
- 87 CallbackQueryHandler constructor calls in source blocks containing that constructor. Comments/string descriptions are excluded by AST inspection.
- Registration line numbers come from AST call locations in bot.py. Conditional registration eligibility and per-user runtime behavior are not inferred.
- Test filenames below are candidates found by exact handler-name references. A filename match does not prove registration, execution, permission, Back, expiry, idempotency or latency correctness.
- Current CI #1381 passed 35 Admin route regressions and 99 deployment-hygiene tests. Their scope is narrower than this entire inventory.

## Per-registration ledger

Fresh Admin Ticket continuation (S12.35.304): the six emitted admin action
controls (`reply`, `ask`, `suggest`, `note`, `assign`, `lead`) dispatch through
the exact `handle_ticket_callback` registration in
`tests/test_admin_ticket_stale_actions_emitted.py`. Focused pytest checks
language/ticket SELECT scheduling, stale alerts, valid actions, public denial,
one ACK, and disappearing-assign recovery. Adjacent Lead-repeat tests remain
green. This is fixture-level scheduling and selected action evidence; it does
not establish live Ticket latency or coverage of every Admin terminal.

S12.35.307 also dispatches the actual emitted `📎 Xem file đính kèm` callback
through that registration. Fixture document/photo sends verify both reads use
the async thread seam and ACK precedes the fake send; stale ticket, non-admin,
retry and cleanup cases remain covered. A later no-I/O selector-based unittest
recheck passed all 7 cases, including concurrent duplicate suppression; its
selector rejects file-descriptor registration. Ubuntu CI remains pending. No
real file send, production ticket read, or client-latency claim is made.
S12.35.308 verifies the actual “🎧 Ticket admin” button from the Admin Support
keyboard: the authorized exact route renders the unchanged Ticket hub with one
ACK and no unnecessary SQLite language lookup. Existing public-denial behavior
and all other action paths remain covered; this removes only a source-level
pre-ACK DB risk and does not establish a measured live delay.
S12.35.309 follows the same emitted Admin Support → Ticket hub path to
“Ticket mới”; valid Admin list callbacks preserve one ACK, kind/offset and list
payload while skipping the unused locale SELECT. The full hub fixture keeps
malformed and public-denial behavior green. Neither spec is live-latency proof.
S12.35.310 likewise covers emitted Stats, Templates, Search-by-User and
Search-Ticket controls. Exact valid Admin callback shapes preserve report/prompt,
ACK, pending and Back/Home behavior without the unused locale SELECT; malformed,
legacy and public denial remain covered. This is source-level evidence only,
not live-latency proof.

### S12.35.230 — Fresh callback timing aggregate and menu-phase boundary

- Source-order detail: the `menu|main` handler awaits callback ACK before language lookup, pending cleanup, keyboard construction and Telegram edit. Those post-ACK phases may delay the visible screen, but no live phase sample currently establishes that they are slow.

- The Owner-approved 24-hour strict-host aggregate queried `callback_dispatch_timing`. At 2026-10-10 18:13:58 +07, `journalctl` exited 0 with empty stderr; matching events=0, malformed matching lines=0, aggregate status valid. No event or raw line was emitted.
- Source inspection confirms `handle_menu_callback` also emits a separate `callback_latency` phase record for exact `menu|main` and `menu|main_video`, including pre-ACK, ACK, language, cleanup, build, render and total handler milliseconds. Eight source-extracted assertions in `tests/test_menu_video_callback_timing.py` were invoked directly with an immediate no-I/O driver and passed on 2026-10-10; bundled Python lacks pytest, so this is not a standard pytest/CI pass.
- The separately Owner-approved 24-hour phase aggregate was rerun after discarding an initial over-escaped local parser attempt. Parser sanity was checked against a representative route line before the corrected read-only query. At about 18:41 +07, `journalctl` exited 0 with empty stderr; matching events=0, malformed matching lines=0, aggregate status valid; no route/role groups or raw lines were emitted. A fresh Owner-approved strict-host recheck at 20:38:38 +07 also exited 0 with empty stderr and 0 matching/malformed events; no phase values were available.
- Both valid empty windows do not prove that no click reached the bot, do not resolve Account → Back's reported 2–3s, and cannot attribute delay to bot, Telegram, network, device or client rendering. A7 remains partial pending a click-correlated sample/client observation. No code/runtime change, raw-log disclosure, service mutation, deploy, or restart.

### S12.35.231 — Current-main literal callback-assignment registration pre-screen

- Text pre-screen of `origin/main` `5c38bd31c20f26f815e2f05b6419f4dd64afbba9`: 83 valid literal `CallbackQueryHandler` patterns; 3,139 static `callback_data` assignments; 1,300 unique literal values; 494 dynamic-template assignments. Audit HEAD `b2a45cf72c8d11b838ce67101c6385128106e856`: 83 patterns; 3,120 static assignments; 1,306 unique literals; 495 dynamic templates. No unmatched unique literal remained after resolving `"|".join(...)` as a delimiter and `callback_data = ""` as a local default.
- This is a source-text pre-screen, not an AST/widget-emission inventory or route dispatch. It does not cover computed/positional values, conditional registration eligibility, dynamic templates, handler semantics, or callback terminal behavior. A5 remains partial; an attempted whole-file AST scan exceeded the local time budget and was interrupted. No product/source edit or runtime side effect.

| Handler / source | Pattern / group | Candidate test references | Evidence / remaining gate |
|---|---|---|---|
| `callback_latency_observer` — bot.py:139159 | `<no pattern>`; group `observer_group` | `test_callback_dispatch_timing.py` | PARTIAL: installed after all direct callback registrations and wraps every registered `CallbackQueryHandler`; focused suite rerun 2026-10-09 (`Ran 5 tests in 7.780s — OK`). Fresh seven-day live census: 10 events, all `menu` / `handle_menu_callback`, max 529.393 ms, none above 1 s; no non-menu family or ReplyKeyboard timing sample. This is not an all-button or client-render latency pass. |
| `dispatch_throttle_callback_guard` — bot.py:272499 | `<no pattern>`; group `-11` | `test_callback_dispatch_timing.py`; `test_p0_secfix_b5_dispatch_throttle.py`; `tests.test_admin_queue_confirm_back_origin` | PARTIAL: S12.35.12 executes the actual source-extracted allow path before registered Queue `menu|` controls in inert fixtures; throttle-denial/retry timing and live Application dispatch are not covered here. |
| `safe_mode_callback_guard` — bot.py:272501 | `<no pattern>`; group `-10` | `test_callback_dispatch_timing.py`; `test_p0_video_ai_real_pilot_ui.py`; `tests.test_admin_queue_confirm_back_origin` | PARTIAL: S12.35.12 traverses the actual guard with normal and tool/maintenance-freeze fixtures before registered Queue confirmation/guide callbacks. Emergency/payment/provider-specific blocked paths and live dispatch remain unverified. |
| `video_public_callback_dedupe_guard` — bot.py:272502 | `<no pattern>`; group `-9` | `test_callback_dispatch_timing.py`; `test_p0_video_route5_full_callback_image_ai_backstack.py`; `test_video_public_callback_dedupe_guard.py` | PARTIAL: S12.35.225 executes the extracted registered guard before the actual `vprofile` registration boundary: replaying the same Telegram query ID is stopped and acknowledged once; a distinct query ID passes. This is exact-update replay protection only, not proof of idempotency for separate rapid taps or of the protected Video handler's action. No product route body, job, provider or wallet was invoked. |
| `handle_music_quick_callback` — bot.py:172696; registration bot.py:274369 | <code>r"^(music_quick&#124;sfx_quick&#124;media_quick)\|"</code>; group `0` | S12.35.64/.93 dispatch emitted Audio Studio root/Voice Hub controls through the registered handler; Voice Hub Back returns to Audio Studio and Home to Main. S12.35.88 directly runs 19 in-memory Voice TTS settings Back/pending assertions through the registered handler. S12.35.314 adds 15 registered Music suggestion Back/pending-state fixtures across showroom/Video Add-on contexts; its pytest module is selected in final safe-navigation CI. | Partial verified UI/settings only; consolidated CI and Telegram-client rendering remain pending; TTS/STT/generation/provider and remaining dynamic terminals are not proven |
| `handle_product_progress_callback` — current main bot.py:12427 / registration 275133 | `^progress\\|status\\|`; group `0` | `test_admin_root_menu_callback_single_ack.py` (CI-selected); `test_p0_23a_unified_product_progress_status_panel.py`; `test_p0_23b_safe_auto_refresh_restore_music_engine.py` (+9 candidates) | PARTIAL: S12.35.374 dispatches the emitted `video_ai_real` update button twice through the registered handler with a matching in-memory job; each click ACKs once and renders the actual progress panel. S12.35.375 reproduces missing and foreign video jobs generating a synthetic 5% panel; a video-only UI guard now shows localized unavailable/retry copy with Back/Home and does not register refresh. Both use inert reads/refresh and fail-on-call delivery/reprocess seams. SubDub rehydrate/redelivery/receipt, Music delivery, Frame Video receipt DB, live refresh, production job state and Telegram remain unverified. Current main `381c71bb…`; no engine file or SubDub/Music branch changed. |
| `handle_media_preview_callback` — bot.py:273596 | `^(play_sfx\|play_music\|select_sfx\|select_music\|open_sfx_source\|open_music_source\|license_sfx\|license_music)\\|(?:[0-9a-f]{32}\\|)?\d+$`; group `0` | `test_media_preview_callback_snapshot.py` | PARTIAL on current branch: S12.35.352's exact-main `bot.py` literal scan found no unmatched static callback; dynamic `play_{kind}`, `select_{kind}`, and `license_{kind}` prefixes resolve to this pattern once type/token/index suffixes are present. Existing 19-case fixture run exercised Music/SFX and License route/stale snapshot cases through the registered handler. S12.35.353 adds direct emitted SFX Select+Play route verification with exact snapshot and a fake preview helper; this new case ran separately and is already selected by CI. No engine/provider or real Telegram send. Live client delivery/latency remains unverified. |
| `handle_pixabay_media_callback` — bot.py:273597 | `^(play_media\|select_media)\\|(?:[0-9a-f]{32}\\|)?\d+$`; group `0` | `test_media_preview_callback_snapshot.py` | PARTIAL on current branch: S12.35.352's exact-main literal scan found no unmatched static callback; `play_media|`/`select_media|` are dynamic prefixes whose registered pattern requires the optional snapshot token and numeric item index. The existing 19-case fixture run dispatched emitted Pixabay Select/Preview controls with their tokens; stale snapshot/context and wrong-owner/expiry cases fail closed. No real Telegram/provider delivery; live user experience remains unverified. |
| `handle_image_story_callback` — bot.py:274423 | <code>r"^(image_story_aspect\|.+|image_story_render_hint)$"</code>; group `0` | `tests.test_admin_root_menu_callback_single_ack` | PARTIAL: the pre-existing aspect callbacks are registered, acknowledge the chosen ratio, and reply that a future pack will use it, but `cmd_image_story` still builds at fixed 9:16; no selected-aspect application is claimed. The mismatch between the callback's promise and the prompt pack remains unresolved because Owner excluded output-affecting S12.35.106; dependent cleanup S12.35.108 was dropped. Only the independent `image_story_render_hint` route is retained as local test-only evidence (S12.35.107); prior aspect/expiry test results are historical and were run against reverted code. No real rendering/provider call or Telegram-client visual test; Image engine behavior remains unverified and protected. |
| `handle_local_video_studio_preview_callback` — current main bot.py:70830 / registration 275137 | `^lvs27a\\|`; group `0` | `test_admin_root_menu_callback_single_ack.py` (CI-selected); `test_p1_localvideostudio27a_preview.py` | PARTIAL: S12.35.376 emits the admin command's actual Local Video Studio Preview keyboard, matches `open|create` against the exact registered callback handler, then dispatches the emitted Back, Home, Close and stale Back. It verifies one ACK per callback, stale replay alert/no state recreation, and non-admin denial before edit. The preview capability index is local and read-only; no provider, job or product-video render runs. Live client rendering/latency remains unverified. |
| `handle_local_video_studio_public_callback` — current main bot.py:71207 / registration 275138 | `^lvs27b\\|`; group `0` | `test_admin_root_menu_callback_single_ack.py` (CI-selected); `test_p0_18k_video_menu_flow_standardization_routing_matrix.py`; `test_p1_localvideostudio27b_public_ui.py` | PARTIAL: S12.35.377 dispatches emitted `lvs27b|open` + Back through the exact registration; .378 verifies emitted persist idempotency through it; .380 dispatches emitted `plans` → saved-plan `view` → `library` Back with one ACK each and owner/chat-scoped fixture reads. Uses only local planner code and a shared in-memory SQLite fixture; no production DB, provider, job, render, wallet, or engine action. Edit/delete/expiry/repeat paths and Telegram-client rendering/latency remain unverified. |

S12.35.354 addendum for `handle_media_preview_callback`: the current SFX License
button was emitted by the media-preview keyboard and dispatched through this
registered handler with the exact snapshot token/index. The focused fixture
asserted one ACK and the fake license-helper arguments; output was
`SFX_LICENSE_REGISTERED_ROUTE_OK: exact emitted token/index, one ACK, fake license
helper only` (exit 0). No media/provider/Telegram/engine action was run. This
does not verify downstream licensing or client-visible latency.

S12.35.355 addendum for `handle_pixabay_media_callback`: the current production
Pixabay keyboard's Select and View buttons were emitted and dispatched through
the registered handler with their exact snapshot/index. The fixture asserted
one ACK per action, selected item content and the fake preview-helper arguments.
Output: `CURRENT_PIXABAY_SELECT_PLAY_REGISTERED_ROUTE_OK: exact emitted
callback/token/index, one ACK each, fake preview sink` (exit 0). No actual media,
search provider, job, Telegram API, or product engine action was run; downstream
delivery and live-client latency remain unverified.

S12.35.356 addendum for `handle_music_quick_callback`: the Pixabay keyboard's
Find-more button emits `music_quick|media` and dispatches to the registered
handler. The focused fixture verified one ACK and the Media Library guide with
its quick keyboard while setting the search/provider seam fail-fast; no provider
was called. Output: `PIXABAY_FIND_MORE_REGISTERED_ROUTE_OK: emitted callback,
one ACK, inert guide/keyboard, provider untouched` (exit 0). This does not verify
external search or actual media delivery.

S12.35.357 addendum for `handle_music_quick_callback`: the production Media
Library keyboard emits Back as `music_quick|showroom|music_hub`; dispatch through
the registered route returns the fixture Audio Studio hub and ACKs once. Pending
clear and render seams are fake; provider/search is fail-fast and remains
untouched. Output: `MEDIA_LIBRARY_BACK_REGISTERED_ROUTE_OK: emitted callback,
one ACK, Audio Studio hub, provider untouched` (exit 0). No client latency or
downstream audio/media processing is established.
| `handle_product_video_public_confirm_callback` — bot.py:273601 | `^vproduct\\|b14_confirm$`; group `0` | `test_p0_product_video_pv09_full_button_flow_matrix_truth.py`; `test_p0_product_video_pv10_deterministic_all_product_e2e.py` (+14 candidates) | NOT PROVEN: candidate references are not executed route evidence |
| `handle_product_video_public_confirm_callback` — bot.py:273602 | `^vproduct\\|b14_confirm\\|[a-f0-9]{12}$`; group `0` | `test_p0_product_video_pv09_full_button_flow_matrix_truth.py`; `test_p0_product_video_pv10_deterministic_all_product_e2e.py` (+14 candidates) | NOT PROVEN: candidate references are not executed route evidence |
| `handle_video_tail_callback` — bot.py:273603 | `^video_tail\\|`; group `0` | `test_p0_product_video_full_menu_tail_to_status_matrix.py`; `test_p0_product_video_manual_tail_matrix.py` (+25 candidates) | NOT PROVEN: candidate references are not executed route evidence |
| `handle_video_uiflow3_callback` — bot.py:273604 | `^vid3\\|`; group `0` | `test_p0_18k_video_menu_flow_standardization_routing_matrix.py`; `test_p0_product_scene_plan_callback_ack.py` (+13 candidates) | NOT PROVEN: candidate references are not executed route evidence |
| `handle_video_trend2_callback` — bot.py:273605 | `^vtrend\\|`; group `0` | `test_p0_video_final_uiux_canonical_product_flows.py`; `test_p0_video_realistic_restore1_last_green_lock.py` (+4 candidates) | NOT PROVEN: candidate references are not executed route evidence |
| `handle_storyboard2_callback` — bot.py:273606 | `^vstory\\|`; group `0` | `test_p0_video_final_uiux_canonical_product_flows.py`; `test_p0_video_realistic_restore1_last_green_lock.py` (+4 candidates) | NOT PROVEN: candidate references are not executed route evidence |
| `handle_video_product_callback` — bot.py:273607 | `^vproduct\\|(?!b14_confirm(?:\\|\|$))`; group `0` | `test_p0_17b11_video_ui_ux_cleanup.py`; `test_p0_17b14_2_video_live_flow_repair.py` (+49 candidates) | NOT PROVEN: candidate references are not executed route evidence |
| `handle_video_prompt_library_callback` — bot.py:273608 | `^vpromptlib\\|`; group `0` | `test_p0_17b11_video_ui_ux_cleanup.py`; `test_p0_17b7_1_video_menu_cleanup.py` (+6 candidates) | NOT PROVEN: candidate references are not executed route evidence |
| `handle_architecture_profile_callback` — bot.py:273609 | `^archprofile\\|`; group `0` | `test_p0_profile_arch1_architecture_interior_realestate_studio.py`; `test_p0_video_realistic_restore1_last_green_lock.py` (+1 candidates) | NOT PROVEN: candidate references are not executed route evidence |
| `handle_video_profile_studio_callback` — bot.py:273610 | `^vprofile\\|`; group `0` | `test_p0_17b11_video_ui_ux_cleanup.py`; `test_p0_18f_video_menu_route_audit_fix_only.py` (+32 candidates) | NOT PROVEN: candidate references are not executed route evidence |
| `handle_video_trend2_legacy_callback` — bot.py:273611 | `^trendg\\|`; group `0` | `test_core.py`; `test_p0_video_realistic_restore1_last_green_lock.py` (+1 candidates) | NOT PROVEN: candidate references are not executed route evidence |
| `handle_video_trend2_legacy_callback` — bot.py:273612 | `^tvflow\\|`; group `0` | `test_core.py`; `test_p0_video_realistic_restore1_last_green_lock.py` (+1 candidates) | NOT PROVEN: candidate references are not executed route evidence |
| `handle_creative_motion_callback` — bot.py:273613 | `^motion\\|`; group `0` | `test_core.py`; `test_p0_video_realistic_restore1_last_green_lock.py` | NOT PROVEN: candidate references are not executed route evidence |
| `handle_cinematic_ad_callback` — bot.py:273614 | `^adconcept\\|`; group `0` | `test_core.py`; `test_p0_video_realistic_restore1_last_green_lock.py` | NOT PROVEN: candidate references are not executed route evidence |
| `handle_prompt_video_callback` — bot.py:273615 | `^promptvideo\\|`; group `0` | `test_core.py`; `test_p0_video_realistic_restore1_last_green_lock.py` | NOT PROVEN: candidate references are not executed route evidence |
| `handle_image_video_callback` — bot.py:273616 | `^imagevideo\\|`; group `0` | `test_core.py`; `test_p0_video_realistic_restore1_last_green_lock.py` | NOT PROVEN: candidate references are not executed route evidence |
| `handle_video_reference_callback` — bot.py:273617 | `^videoref\\|`; group `0` | `test_core.py`; `test_p0_video_flow4_callback_route_recovery.py` (+3 candidates) | NOT PROVEN: candidate references are not executed route evidence |
| `handle_video_downloader_callback` — bot.py:273618 | `^vdownload\\|`; group `0` | `test_p0_17b11_video_ui_ux_cleanup.py`; `test_p0_18f_video_menu_route_audit_fix_only.py` (+7 candidates) | NOT PROVEN: candidate references are not executed route evidence |
| `handle_video_dubbing_callback` — bot.py:273619 | `^videodub\\|`; group `0` | `test_core.py`; `test_lock_audio_translation_public_guards_18s.py` (+56 candidates) | PARTIAL: offline ACK/permission/stale or valid branches were executed in S12.28; remaining emitted values, full Back/expiry/repeat paths and client/runtime timing stay open. |
| `handle_autopost_callback` — bot.py:273620 | `^autopost\\|`; group `0` | `test_p0_vps_autopost_startup_symbol.py` | NOT PROVEN: candidate references are not executed route evidence |
| `handle_marketing_callback` — bot.py:273621 | `^marketing\\|`; group `0` | `test_core.py`; `test_marketing_callback_single_ack.py` (+1 candidates) | PARTIAL: offline ACK/permission/stale or valid branches were executed in S12.28; remaining emitted values, full Back/expiry/repeat paths and client/runtime timing stay open. |
| `handle_self_scene_ai_callback` — bot.py:273622 | `^selfscene\\|`; group `0` | `test_core.py`; `test_p0_3_canonical_flow.py` (+4 candidates) | NOT PROVEN: candidate references are not executed route evidence |
| `handle_long_video_callback` — bot.py:273623 | `^longvideo\\|`; group `0` | `test_core.py`; `test_p0_18f_video_menu_route_audit_fix_only.py` (+10 candidates) | NOT PROVEN: candidate references are not executed route evidence |
| `handle_storyboard_pack_callback` — bot.py:273624 | `^storypack\\|`; group `0` | `test_core.py`; `test_p0_video_realistic_restore1_last_green_lock.py` (+4 candidates) | NOT PROVEN: candidate references are not executed route evidence |
| `handle_video_idea_admin_callback` — bot.py:273626 | `^viadm\\|`; group `0` | `test_p0_video_idea2_dynamic_presets_admin_script_intake.py`; `test_p0_video_trend2_weekly_catalog_full_flow_callback_recovery.py` | NOT PROVEN: candidate references are not executed route evidence |
| `handle_video_idea_prompt_callback` — bot.py:273627 | `^idea_video\\|`; group `0` | `test_p0_video_finalflow12_golden_tail.py`; `test_p0_video_ideaflow2_restore_catalog_direct_prompt_return.py` (+4 candidates) | NOT PROVEN: candidate references are not executed route evidence |
| `handle_video_idea_dynamic_callback` — bot.py:273628 | `^videa\\|`; group `0` | `test_p0_video_idea2_dynamic_presets_admin_script_intake.py`; `test_p0_video_idea3ux6_direct_edit_trend_routes.py` (+8 candidates) | NOT PROVEN: candidate references are not executed route evidence |
| `handle_video_idea_callback` — bot.py:273629 | `^videoidea\\|`; group `0` | `test_core.py`; `test_p0_18f_video_menu_route_audit_fix_only.py` (+12 candidates) | NOT PROVEN: candidate references are not executed route evidence |
| `handle_video_upload_callback` — bot.py:273630 | `^video_upload\\|`; group `0` | `test_core.py`; `test_p0_videoedit_legacy_compatibility.py` (+7 candidates) | NOT PROVEN: candidate references are not executed route evidence |
| `handle_video_editor_callback` — bot.py:273631 | `^videoedit\\|`; group `0` | `test_p0_17b11_video_ui_ux_cleanup.py`; `test_p0_18f_video_menu_route_audit_fix_only.py` (+32 candidates) | NOT PROVEN: candidate references are not executed route evidence |
| `handle_storyboard_callback` — bot.py:273632 | `^storyboard\\|`; group `0` | `test_core.py`; `test_p0_video_framevideo4_duration_pricing_callback_recovery.py` (+2 candidates) | NOT PROVEN: candidate references are not executed route evidence |
| `handle_video_finalization_callback` — bot.py:273633 | `^vfinal\\|`; group `0` | `test_core.py`; `test_logo_watermark_image_video_flow.py` (+11 candidates) | NOT PROVEN: candidate references are not executed route evidence |
| `handle_video_addon_callback` — bot.py:273634 | `^videoaddon\\|`; group `0` | `test_core.py`; `test_p0_10_live_qa_voice_music_subtitle_video_flow.py` (+8 candidates) | NOT PROVEN: candidate references are not executed route evidence |
| `handle_storyboard_image_callback` — bot.py:273635 | `^vstoryimg\\|`; group `0` | `test_p0_video_realistic_restore1_last_green_lock.py`; `test_p0_video_route6_storyboard_selfshot_idea_longvideo.py` (+1 candidates) | NOT PROVEN: candidate references are not executed route evidence |
| `handle_create_media_callback` — bot.py:273636 | `^create_media\\|`; group `0` | `test_core.py`; `test_logo_watermark_image_video_flow.py` (+6 candidates) | NOT PROVEN: candidate references are not executed route evidence |
| `handle_frame_video_callback` — bot.py:273637 | `^framevideo\\|`; group `0` | `test_core.py`; `test_p0_17b7_2_image_to_video_dedupe_flow.py` (+13 candidates) | NOT PROVEN: candidate references are not executed route evidence |
| `handle_suggest_music_callback` — bot.py:273638 | `^suggest_music\\|`; group `0` | `tests/test_suggest_music_callback_ui_route.py` | PARTIAL: S12.35.321 builds all five emitted style controls and dispatches each through the exact registered callback; each ACKs once and returns the matching static search phrase and `/music_library` instruction. Unknown style falls back to the safe static recommendation. No playback, provider, generation, DB, wallet or engine call is exercised. This closes only the named static UI route; music action paths and live/client latency remain unverified. |
| `handle_engine_async_job_callback` — bot.py:273639 | `^enginejob\\|`; group `0` | `test_p0_13_job_polling_provider_discovery.py`; `test_p0_16a3_music_cleanup_preview_quota.py` | NOT PROVEN: candidate references are not executed route evidence |
| `handle_shopaikey_public_callback` — bot.py:273640 | `^shopai\\|`; group `0` | `test_core.py`; `test_lock_audio_translation_public_guards_18s.py` (+10 candidates) | NOT PROVEN: candidate references are not executed route evidence |
| `handle_public_video_status_callback` — bot.py:273641 | `^video\\|status\\|`; group `0` | `test_p0_19i_final_subdub_voice_lock_direct_dub_shared_status.py`; `test_p0_video_realistic_restore1_last_green_lock.py` | NOT PROVEN: candidate references are not executed route evidence |
| `handle_shopaikey_video_job_callback` — bot.py:273642 | `^shopai_video_job\\|`; group `0` | `test_lock_audio_translation_public_guards_18s.py`; `test_task3d7_video_lock_dedupe_public_guards.py` | NOT PROVEN: candidate references are not executed route evidence |
| `handle_human_support_callback` — bot.py:273643 | `^support\\|`; group `0` | `test_core.py`; `test_p0_free1_refresh_free_tools_menu_existing_zero_cost_shortcuts.py` (+3 candidates); `test_profile_support_pending_origin.py`; `test_profile_support_read_back_origin.py` | PARTIAL: S12.35.129 reran 19 registered-handler Support pending/Back and Account/Ticket ancestry cases (`Ran 19 tests in 141.541s — OK`); .130 source-compared the five-row/eight-control Support root; .215–.216 execute emitted public informational controls plus Back/Home; .217 executes emitted public `support|ticket` to the general-support prompt and verifies actor-only pending cleanup/foreign-state preservation; .220 dispatches My Tickets from public and Account-origin Admin-contact, Auto-support and Premium pages, then verifies Back restores the exact Support child. A fresh 2026-10-10 run of Ticket ancestry + Support read-only Back/Home + Support pending/expiry modules passed 34 tests in 515.271s — OK. The separate `ticket|start` category picker remains intentionally off the public root per the 2026-10-09 delegated choice to preserve the one-step form. Other action paths, localized client rendering and runtime timing remain partial. |
| `handle_ticket_callback` — bot.py:273644 | `^ticket\\|`; group `0` | `test_admin_stale_ticket_detail_callback_single_ack.py`; `test_admin_stale_ticket_status_callback_single_ack.py`; `test_profile_ticket_ancestry.py`; `test_admin_ticket_stale_actions_emitted.py` (+19 candidates) | PARTIAL: S12.35.60 covers selected owned Account-origin list/detail/prompt paths and malformed/foreign controls with fixture reads; .218 dispatches public Support's emitted `ticket|mine|support` through the registered handler and verifies Support-root Back/Home; .219 fixes public My Tickets → owned detail Back losing its list parent; .220 fixes list Back returning to Support root instead of the emitting Support child or Ticket category menu, including Account-scoped child origins. Fresh 2026-10-10 run of the Ticket ancestry and Support Back/pending suites passed 34 tests in 515.271s — OK. S12.35.302 verifies all six emitted Admin Ticket actions at stale/valid/public-denied boundaries, plus disappearing-assign recovery; the correct recovery Back is `menu|admin_support` (fixture only, CI pending). Account-root and Feedback-result origins remain regression-checked. Other Admin/action-capable terminals and live/client timing remain open. |
| `handle_feedback_callback` — bot.py:273645 | `^feedback\\|`; group `0` | `test_core.py`; `test_feedback_callback_single_ack.py` (+3 candidates) | PARTIAL: existing focused tests cover single ACK, start/category/cancel destinations, and unsupported-action denial; S12.35.131 passes two concurrent copies of one Telegram message through the actual in-process idempotency wrapper decorating handle_message and reaches Feedback pending handling once (one classify/create/clear/reply/notify). S12.35.132 consumes only expired Feedback input, responds with dedicated expiry copy verified for all 17 supported locales and the category keyboard, and stops fall-through to later handlers. S12.35.133 rejects unknown Feedback categories before ACK or pending mutation and confirms all eight emitted categories are whitelisted. Distinct rapid message IDs, cross-process behavior, error/retry, other emitted values, localized client rendering and live timing remain open. |
| `handle_image_tools_callback` — bot.py:273646 | `^imgtool\\|`; group `0` | `test_admin_root_menu_callback_single_ack.py` (+ existing candidate references) | PARTIAL: S12.35.157 executes the actual `^imgtool\\|` registration for emitted `imgtool|prompt_need_image`, verifies the intake pending state, then dispatches emitted Back through registered Menu and confirms actor-only pending cleanup plus exact Image-hub restoration. S12.35.160 likewise dispatches the actual main-image hub's `imgtool|edit_ai_start` through the registration without a source image; emitted `menu|main_image` Back restores the exact hub and clears only the actor's `image_edit_wait_image`, preserving another user's state. Combined focused Image routes: 2 tests pass; full CI-listed root/menu module including S12.35.160: 44 tests in 50.612s — OK. No image was uploaded or processed. Other image actions/processing and live/client latency remain unverified. |
| `handle_storage_addon_callback` — bot.py:273647 | `^storage\\|`; group `0` | `test_storage_addon_pending_reset_on_start.py`; `test_storage_addon_navigation_callbacks.py` | PARTIAL: S12.35.58 exercises emitted custom-input → Back through the exact registration; S12.35.147 verifies expiry consumption through the source-extracted `handle_message` chain and localized no-charge notice for all supported languages. Payment confirmation/repeat and real Telegram-client timing remain untested. |
| `handle_memory_callback` — bot.py:273648 | `^memory\\|`; group `0` | `test_memory_empty_delete_state.py`; `test_memory_pending_reset_on_start.py`; `test_admin_root_menu_callback_single_ack.py` (+1 candidates) | PARTIAL: S12.35.57 executes empty-delete to verify stale pending clears; S12.35.62 dispatches the actual emitted empty-delete button through the registered handler and its Back through registered Menu to Notes/Docs; S12.35.65 verifies Saved Notes → owned detail → Back and Delete Cancel → same detail → Back; S12.35.66 verifies Delete-picker choice → confirmation → Cancel returns to that picker; S12.35.67 dispatches actual search text/results → detail → delete-confirm Cancel → Back to the exact result list, and stale/expired/foreign origins fail closed. Start/Menu regression also checks registration. Delete execution, other Memory expiry/repeat paths and live/client timing remain unverified. |
| `handle_translation_callback` — bot.py:273649 | `^tr_(target\|more\|pick\|transcribe)(\\|\|$)`; group `0` | `test_p0_i18n_root_flow_copy.py`; `tests.test_admin_root_menu_callback_single_ack` | PARTIAL: S12.35.110 dispatches emitted text/file picker `tr_more|<source>` and matching `tr_pick|<source>` Back; .111 verifies voice picker More/Back; .162 verifies text target; .286 covers file/voice target to inert pre-provider boundaries. S12.35.381 dispatches the actual emitted `tr_transcribe` button through the exact registration and fixes missing-media recovery to restore the existing action/Home keyboard; the fail-on-call transcription seam is untouched. Other media/input processing, provider execution, complete-handler coverage and client latency remain unverified. Current-main #1424 diff has no Translation callback hunk; this is not a live/runtime claim. |
| `handle_language_callback` — bot.py:273650 | `^(lang\\|(?:[a-z]{2}\|fil)\|lang_more\|back_lang\|lang_back)$`; group `0` | `test_free_tools_hub_v1.py`; `test_language_callback_single_ack.py`; `tests.test_admin_root_menu_callback_single_ack`; `test_profile_language_back_origin.py` | PARTIAL: S12.35.113 dispatches the actual public-root back_lang entry then the emitted lang_back through the exact registered handler and verifies the exact original main-menu callback set returns, one ACK each, and no preference/usage/broadcast write. S12.35.258 dispatches every locale emitted by the Account picker through this registration, verifies the callback-byte bound, one in-memory preference/usage update, one ACK and return to Account. Other language branches, expiry/repeat, persisted preference/broadcast behavior, and client/runtime timing remain open. |
| `handle_package_purchase_callback` — bot.py:273651 | `^pkgbuy\\|`; group `0` | `tests.test_pkgcombo_navigation_registered_callback.PackageComboNavigationTests.test_emitted_package_confirmation_dispatches_to_inert_purchase_seam` | PARTIAL: S12.35.255 builds the auto-checkout confirmation control from the actual package-detail route and dispatches its emitted `pkgbuy|confirm|…` callback through this exact registration. It ACKs once and delegates to an inert `start_package_purchase` seam with exact user/type/code/message arguments; no order, PayOS, DB, wallet, provider or real message runs. Manual/invalid branches and actual checkout completion remain untested. |
| `handle_pkgcombo_callback` — bot.py:273652 | `^pkgcombo:`; group `0` | `test_pkgcombo_navigation_registered_callback.py`; `test_p0_global_pricing_i18n_locale_expansion.py` | PARTIAL: S12.35.61 dispatches the emitted Image package group and Back. S12.35.188 adds registered-route-origin checks for Catalog, Account Pricing main, Account Catalog, and public/Account Total → Packages → exact parent round-trips; .253 verifies package callback byte limits and group/detail ancestry across all origin tokens. S12.35.255 dispatches the emitted confirmation-screen Back through this handler and restores the same group. Actual package order creation, PayOS and payment completion remain untested. |
| `handle_pricing_callback` — bot.py:273653 | `^pricing\\|`; group `0` | `test_profile_pricing_back_origin.py`; `test_core.py`; `test_free_tools_hub_v1.py` (+2 candidates) | PARTIAL: S12.30 covers Account Pricing/catalog/detail and Membership ancestry; S12.35.3 is merged/deployed and exercises emitted Top-up from main/offers/promo guide/Video/Image, all 14 locale-fallback Catalog keyboards, and Xu via the registered Pricing handler. S12.35.4 offline GREEN: focused `/pricing_xu` → Top-up → Back coverage passed; runtime source is superseded in S12.35.105 at `9835b432…`. Local S12.35.184–.187 verify public Voice/Guide/Catalog Member/Total parent routes. S12.35.188 verifies scoped package entries and Account/Total ancestry; after two stale expected callback values were aligned, the complete Pricing module passed `28 tests in 118.453s — OK` using a Windows fixture driver that rejects yielded I/O. Client visual QA, generated-document/payment terminals, remaining catalog actions and live/client latency remain open. |
| `handle_buy_plan_callback` — bot.py:273654 | `^buy_plan\\|`; group `0` | `test_profile_pricing_back_origin.AccountPricingOriginTests.test_public_stale_buy_plan_callback_is_safe_and_registered` | VERIFIED SAFE LEGACY FALLBACK: S12.35.256 confirms no current emitter; one stale public callback reaches this exact registration, ACKs once, renders current public package destinations, and does not call purchase. Admin checkout remains untested. |
| `handle_doc_tool_callback` — bot.py:273655 | `^docflow\\|`; group `0` | `test_core.py`; `test_doc_page_prompt_reset_on_start.py`; `test_doc_split_back_emitted_callback.py`; `test_doc_tool_callback_single_ack.py` | PARTIAL: S12.35.57 executes split-page prompt Back and parent Back through the exact registration. S12.35.134 dispatches an expired `save_document` Back through the same registration. S12.35.137 covers after-file Add-more and Remove-last. S12.35.159 reproduced confirmation Add-more clearing staged state and changed only its emitter to existing `docflow|send_more`; 7 focused fixture functions passed, including the separate after-file `reset_files` guard. S12.35.161 dispatches actual confirmation Back for active `split_pdf` and `save_document` through the registration; both origin keyboards, actor-only cleanup, unrelated-user state preservation, and single ACK passed (2 origin scenarios). S12.35.299 reproduces the valid `docflow|confirm` SQLite-backed language lookup before ACK and fixes only that branch to ACK once, then offload the lookup; the insufficient-file alert remains unchanged (4 focused no-I/O callback assertions passed). Full `tests/test_doc_split_back_emitted_callback.py` rerun passed all 8 test functions in 10.887s; full `bot.py` syntax gate remains open. Processing/send actions, other expiries/repeats, and client/runtime timing remain unverified. |
| `handle_internal_archive_callback` — bot.py:273656 | `^archive\\|`; group `0` | `test_internal_archive_metadata_reset_on_start.py`; `test_internal_archive_type_back_label.py`; `test_internal_archive_search_back_origin.py`; `test_admin_root_menu_callback_single_ack.py` (+3 candidates) | PARTIAL: S12.35.31 verifies type-screen Back; S12.35.59 covers Archive root → Notes; S12.35.138 dispatches actual root/department Search Back through the registered handler, including TTL-expired department context and live-state precedence, then dispatches emitted Search Home through the exact registered Menu handler and confirms actor-only pending cleanup (full root/menu module: 51 tests passed). S12.35.151 dispatches emitted `archive|view|id` through the registered route and verifies fixture detail rendering; malformed/missing/stale `view` and stale/malformed `file` selections fail closed with one ACK and no unrelated pending cleanup. S12.35.152 dispatches emitted `archive|file|id` through the same registered handler and verifies exact fixture ID/caption at a fake Telegram send boundary (6 focused Archive tests passed). The historical S12.35.207/.232 pre-ACK concern was fixed in S12.35.271: current handler ACKs before `asyncio.to_thread(get_internal_document, ...)`. S12.35.346 rechecks both emitted View and File controls through the registered handler; a no-yield fixture asserts ACK before both fake reads, renders the detail screen, and keeps the file send at a fake sink. No production document/file was accessed or sent. Live/client timing, remaining action values and repeat/error paths outside tested cases remain unverified. |
| `handle_aichat_callback` — bot.py:273657 | `^aichat\\|`; group `0` | `test_p0_aichat1b_free_tools_menu_cleanup.py`; `test_p0_aichat1_copilot_consent.py`; `tests.test_admin_root_menu_callback_single_ack` | PARTIAL: S12.35.112 dispatches emitted Free Tools `aichat|on` and consent Back; S12.35.150 verifies stale-consent denial and valid pending-consent grant with fixture state. S12.35.163 covers emitted Trace → active-status Back; S12.35.164 covers emitted Status → read-only status/Trace/Back/Home; S12.35.165 dispatches enabled-state Back to Free Tools root. Each tested callback ACKs once; read-only routes do not persist state. AI message/action/provider behavior, remaining branches and client timing remain unverified. |
| `handle_free_hub_callback` — bot.py:273658 | `^freehub\\|`; group `0` | `test_p0_i18n_free_hub_root_static.py`; `test_admin_tool_test_pending_reset.py`; `test_admin_root_menu_callback_single_ack.py` | PARTIAL: S12.35.15 exercises emitted Free Tools root and maintenance custom-input cleanup; .34 verifies the public-root Free Tools route; .68–.74 cover Prompt Library, utilities, translation, prompt-generator and upload Back; .259 dispatches the actual emitted `freehub|hook` control through this registration, checks `hook_script` suggestion entry, owner-scoped pending cleanup, and emitted Back/Home with inert fixtures, without entering Voice/SubDub engines. Other tool terminals and client behavior remain open; no paid provider action is claimed. |
| `handle_payos_risk_callback` — bot.py:273659 | `^payrisk\\|`; group `0` | `test_p0_17c3_payos_admin_risk_lock_review.py`; `test_payos_risk_callback_single_ack.py` | PARTIAL: S12.35.326 dispatches six obsolete/malformed action-payload cases through the exact registration and verifies one alert ACK with no render/action; emitted report/help, valid admin ACK and non-admin denial regressions also pass. Other valid actions, expiry/repeat paths and client/runtime timing remain open. |
| `handle_remote_worker_canary_callback` — bot.py:273660 | `^remote_worker_canary_(create\|status)(\\|\|$)`; group `0` | `test_p0_17w4_remote_worker_canary.py`; `test_remote_worker_canary_callback_single_ack.py` | PARTIAL: offline ACK/permission/stale or valid branches were executed in S12.28; remaining emitted values, full Back/expiry/repeat paths and client/runtime timing stay open. |
| `handle_remote_worker_prod_canary_callback` — bot.py:273661 | `^remote_worker_prod_canary_(create\|status)(\\|\|$)`; group `0` | `test_p0_17w5_remote_worker_admin_prod_canary.py`; `test_remote_worker_prod_canary_callback_single_ack.py` | PARTIAL: offline ACK/permission/stale or valid branches were executed in S12.28; remaining emitted values, full Back/expiry/repeat paths and client/runtime timing stay open. |
| `handle_knowledge_vault_callback` — bot.py:273662 | `^vault\\|`; group `0` | `test_p0_22a_knowledge_vault_prompt_media_extraction.py`; `tests.test_admin_root_menu_callback_single_ack` | PARTIAL: S12.35.128 verifies emitted Vault status matches the registered route and Home=`menu|main` reaches Menu with one ACK. S12.35.135 corrects Import/Search labels as command guides. S12.35.340 dispatches both guide callbacks with one ACK, correct copy and Vault keyboard. S12.35.341 fixes missing Back/Home on non-empty callback prompt/review lists; item actions remain and navigation reaches the expected parents with one ACK. S12.35.342 dispatches Video/Image/Audio categories to the matching read-only list arguments. S12.35.343 verifies admin-only `/vault_review` registration and Back/Home. S12.35.344 verifies `/kho_prompt` and `/vault_prompt` aliases for Admin/public, empty/non-empty results and role-valid exits. S12.35.348 dispatches the emitted Admin approve-item callback through the registered handler using a fake Vault; public replay cannot invoke approval. S12.35.349 dispatches emitted `vault|use|id` for Admin/public; visibility scopes are correct, one ACK each, escaped prompt text goes only to the fake reply sink. No real prompt was approved/used. Tests are inert fixtures; other Vault authorization/action terminals and live Telegram rendering/latency remain unverified. |
| `handle_admin_gopy_callback` — bot.py:273663 | `^admin_gopy\\|`; group `0` | `test_admin_feedback_button_route.py`; `test_admin_feedback_callback_admin_guard.py` | PARTIAL: S12.22 dispatches the emitted Support inbox control through its callback to the read-only command/result renderer and verifies empty/populated/filtered rendering plus Back/Home. No live inbox data or real message was accessed. |
| `handle_admin_help_callback` — bot.py:273664 | `^admin_help\\|`; group `0` | `test_admin_feedback_button_route.py`; `test_admin_help_callback_single_ack.py` (+4 candidates) | PARTIAL: S12.35.127 verifies registered route, one ACK + admin handbook render, all emitted module-guide Back paths, runtime guide labels and stale Support denial; S12.35.149 dispatches all eight Admin Handbook root sections and verifies label-to-section mapping, matching handbook text, plus Handbook/Admin/Home callbacks accepted by the registered Menu handler. The CI-listed module ran 6 tests in 2.840s. No operational Admin action; other handbook branches and live/client rendering remain open. |
| `handle_admin_growth_callback` — bot.py:273665 | `^admin_growth\\|`; group `0` | `tests.test_admin_module_child_back_origin.AdminGrowthNavigationTests` | PARTIAL: S12.35.109 dispatches emitted Growth root links and read-only Affiliates/Ideas/Calendar/Revenue & Click/Channels/Packages pages through the exact registered callback. S12.35.236 reran the five dynamic-trail/navigation/auth assertions using an immediate no-I/O driver (`Ran 5 tests in 33.561s — OK`); the ordinary Windows runner stalled and is not counted. Report/list/render seams were in-memory. Affiliate/publish/campaign writes, production reports/data, client visuals and real Telegram remain untested. |
| `handle_broadcast_lite_callback` — bot.py:273666 | `^broadcast_lite\\|`; group `0` | `test_broadcast_lite_back_pending_cleanup.py`; `test_p0_admin_broadcast2.py` | PARTIAL: S12.35.21 covers emitted read-only History/Schedule/Limits controls and immediate-parent Back. S12.35.195 replays the emitted controls through the actual registered handler, checks Back/Menu pending-owner release while retaining a temporary draft, and verifies nested Limits → Schedule Back (4 fixture tests in 0.801s). Delivery, schedule writes/toggles and AutoPost WIP remain excluded. |
| `handle_menu_callback` — bot.py:273667 | `^menu\\|`; group `0` | `test_admin_billing_guide_labels.py`; `test_admin_finance_action_renderers.py`; `test_admin_queue_confirm_back_origin.py`; `test_admin_menu_denied_callback_single_ack.py`; `test_admin_root_menu_callback_single_ack.py`; `test_admin_module_child_back_origin.py`; `test_menu_video_callback_timing.py` | PARTIAL: S12.35.8 dispatches all ten emitted `menu|admin_*` Admin-root entries to matching registered module roots and immediate Admin Back; the separate `admin_growth|main` route and Back are also verified. Fresh Admin/customer root-menu safe-flow rerun on 2026-10-10: 50 tests in 48.397s — OK, after a test-only immediate no-yield authorization-fixture correction. S12.35.315 dispatches public Translation → SubDub landing and verifies Back/Home without activating `videodub|` processing. S12.35.347 directly invokes eight current-source Video entry/Back assertions with a no-yield driver: emitted `menu|main_video`/`menu|main`, one ACK, Video/Main screens, draft preservation, render-error propagation and timing-phase labels; no Video tool, job or provider action. This is deterministic fixture evidence, not pytest/CI or live client timing. Other child/action terminals, stateful/payment/provider paths, expiry/repeat coverage and client/runtime timing remain partial or excluded. |
| `handle_provider_choice` — bot.py:273668 | `^prov\\|`; group `0` | `test_provider_choice_single_ack.py` | PARTIAL: offline ACK/permission/stale or valid branches were executed in S12.28; remaining emitted values, full Back/expiry/repeat paths and client/runtime timing stay open. |
| `handle_payos_alert_callback` — bot.py:273669 | `^payosalert\\|`; group `0` | `test_p0_14_admin_ux_provider_cleanup.py`; `test_p0_pricing_manual_callback_locale_regression.py` (+1 candidates) | PARTIAL: offline ACK/permission/stale or valid branches were executed in S12.28; remaining emitted values, full Back/expiry/repeat paths and client/runtime timing stay open. |
| `handle_manual_package_choice` — bot.py:273670 | `^manual\\|`; group `0` | `test_core.py`; `test_p0_17c3_payos_admin_risk_lock_review.py`; `test_profile_topup_back_origin.py`; `test_manual_package_callback_single_ack.py`; `test_manual_foreign_owner_callback_single_ack.py` | PARTIAL: S12.35.301 dispatches the emitted customer Top-up entry through the registered handler and verifies one ACK + manual menu. S12.35.399 reproduces the Admin approval-denial double ACK and fixes only ACK order: a non-admin gets exactly one alert without DB access; authorized Admin still ACKs before a fixture read-only lookup (`Ran 2 tests in 0.514s — OK`). S12.35.400 emits ten owner-bound controls from manual top-up and PayOS-recovery keyboards; pre-change audit HEAD yielded two ACKs for all ten foreign-owner clicks, while the current source returns one denial alert (`Ran 3 tests in 1.843s — OK` with the related manual-package suite). Real bill/payment/wallet actions, expiry/replay, Admin approval terminal, whole-handler coverage and live latency remain unverified. Consolidated CI and source compile are pending. |
| handle_package_choice — bot.py:273671 | ^(payos_pkg|pkg)\\|; group 0 | test_p0_17c2_payos_auto_topup_limits.py; test_p0_global_pricing_i18n_locale_expansion.py; test_package_choice_callback_ack_order.py | PARTIAL: S12.35.300 confirms ACK before expiry cleanup. S12.35.303 builds the actual `main_topup_keyboard()` and dispatches all six emitted PayOS amount callbacks through the registered production handler; each ACKs once before inert expiry cleanup and stops before package/payment logic. S12.35.319 reproduced the foreign-owner double ACK on the emitted/registered callback; owner-approved ACK-only fix now gives the foreign user one denial alert, the authorized owner one early ACK, and malformed-length data one normal ACK, with expiry cleanup retained after each ACK. Fresh focused regression rerun: 3 pytest cases passed in 2.46s and is included in CI's explicit safe-navigation selection. Fixture-only, no production DB/payment/order/provider/wallet effects. Payment/order/provider branches and client timing remain unverified; full source compile/consolidated CI and batch delivery are pending. |
| `handle_video_job_callback` — bot.py:273672 | `^job\\|`; group `0` | `test_video_job_callback_single_ack.py` | PARTIAL: offline ACK/permission/stale or valid branches were executed in S12.28; remaining emitted values, full Back/expiry/repeat paths and client/runtime timing stay open. |
| `handle_pipeline_callback` — bot.py:273673 | `^pipe\\|`; group `0` | `test_pipeline_callback_single_ack.py` | PARTIAL: offline ACK/permission/stale or valid branches were executed in S12.28; remaining emitted values, full Back/expiry/repeat paths and client/runtime timing stay open. |
| `handle_trend_callback` — bot.py:273674 | `^trend\\|`; group `0` | `test_trend_callback_single_ack.py` | PARTIAL: offline ACK/permission/stale or valid branches were executed in S12.28; remaining emitted values, full Back/expiry/repeat paths and client/runtime timing stay open. |
| `handle_creative_callback` — bot.py:273675 | `^creative\\|`; group `0` | `test_creative_callback_single_ack.py` | PARTIAL: offline ACK/permission/stale or valid branches were executed in S12.28; remaining emitted values, full Back/expiry/repeat paths and client/runtime timing stay open. |
| `handle_task_callback` — bot.py:273676 | `^task\\|`; group `0` | `test_production_task_callback_single_ack.py` | PARTIAL: offline ACK/permission/stale or valid branches were executed in S12.28; remaining emitted values, full Back/expiry/repeat paths and client/runtime timing stay open. |
| `handle_operator_menu_callback` — bot.py:273677 | `^opmenu\\|`; group `0` | `test_operator_menu_callback_single_ack.py` | PARTIAL: S12.35.238 reproduces and fixes the command-guide Back destination for controls emitted by all nine Operator categories; every emitted control matches the registered route, stays under Telegram's 64-byte limit, ACKs once, and returns to its exact category. S12.35.239 verifies the root “Dashboard” control identifies its guide destination; .240 clarifies “Approve publish” opens `/approve_publish` instructions; .241 says category children open command instructions; .242 clarifies “Mark published” opens `/mark_published` instructions; .243 clarifies Publisher run opens `/publisher_run` instructions; .244 clarifies Publisher status opens `/publisher_status` instructions; .245 clarifies Publish queue opens `/publish_queue` instructions; .246 clarifies Publisher handoff opens `/publisher_handoff` instructions; .247 clarifies Publish cockpit opens `/publish_cockpit` instructions; .248 clarifies Publish readiness opens `/publish_readiness` instructions. Thirteen focused callback tests pass with inert command/render seams. Actual Operator commands, schedules, publishing, wallet/API, production data, expiry/repeat cases, and client/runtime timing remain excluded. |

## S12.35.232 — Pre-ACK SQLite source triage

- A bounded lexical pass covered 87 top-level callback-handler bodies. The explicit DB/execute/fetch/network/sleep token pass found `get_internal_document` in Archive; a broader generic getter pass flagged 20 handlers for manual triage, not 20 confirmed slow paths.
- Manual safe-flow inspection confirmed synchronous SQLite reads before callback ACK in Internal Archive `view`/`file`, Ticket callback entry (`get_user_language`) and selected Ticket detail/result actions (`get_support_ticket`), plus Document tool `main`/`back` language lookup. Archive/Ticket stale or missing-record alerts currently depend on lookup before ACK; those UX paths remain unchanged.
- Account → Back emits `menu|main_profile`. Its registered Menu handler ACKs before language lookup and profile content rendering. The profile screen then performs synchronous account/package reads after ACK; no current event sample isolates that screen-render work. The two valid 24-hour aggregate windows were empty, so none of these source candidates is proven to explain the Owner's reported 2–3s.
- Limits: lexical/source inspection only; helper timing, SQLite lock/wait duration, Telegram edit/client rendering, exact click correlation, and reply-keyboard latency are unmeasured. No code or runtime changed. Keep A7 partial and do not assign cause to bot, Telegram, network, or device.

## Next verification order

Current narrow evidence: S12.25 exercises SS2/SS3 intro source controls from real service rows through the registered `handle_video_product_callback`, its failure guard, the real Hub builder and `safe_edit_or_send`. It reproduces missing acknowledgement in both stale-product recovery branches; the minimal fix precedes render with one best-effort ACK. Active product/session data remains unchanged, including when ACK times out. Other Product Video callbacks are not covered by this fixture and remain unproven here.

### S12.35.271 — Archive callback response-order follow-up

This local UI-audit WIP supersedes the earlier S12.35.207/.232 Archive pre-ACK note for the specific emitted `archive|view|<id>` and `archive|file|<id>` actions: the actual registered handler now answers before `get_internal_document` and runs that read with `asyncio.to_thread`. Missing/stale records render an error with Archive-root/Home recovery controls after the early ACK; malformed IDs retain an alert. The CI-listed Archive source-extracted module passed 21 fixture tests, including the new RED/GREEN ordering check, valid detail, fake file-send boundary, expiry and navigation. This is branch-local source/test evidence only: no production file/DB/send occurred, no live latency was measured, `bot.py` full-file compile remains NOT_VERIFIED, and main/VPS were not updated by this audit. All other rows remain at their recorded evidence scope.

### S12.35.272 — Feedback callback response-order follow-up

This local WIP moves `user_ui_lang(uid)` after callback/category validation and the single ACK for supported Feedback `start`, `cancel`, and category routes. Unsupported actions/categories still alert before any language lookup or pending mutation. Eight focused source-extracted registered-handler fixtures passed through the immediate no-I/O driver; the new ACK-before-language assertion was observed RED before the move. The module is pytest-style and is selected by the workflow's pytest step; no consolidated CI or live latency is claimed. This is source ordering evidence for the Feedback menu only, not an all-button or client-render latency result.

### S12.35.273 — Document Tools Back response-order follow-up

The emitted `docflow|back|main_docs` callback now ACKs before the potentially synchronous language lookup, then returns to the Documents parent and clears only the current user's pending draft. The Confirm action retains its existing lookup/ACK and minimum-file validation order. The new registered-handler regression was RED on original source (`language_lookup_after_ack=[False]`); after the narrow change all three focused Document Tools tests passed with the immediate no-I/O driver. The test module compiled; local pytest is unavailable, so this is not a CI result. No document/file, production data, provider, wallet, or live Telegram operation was used.

### A7 — Account-root aggregate recheck — 2026-10-11 01:52 +07

One Owner-approved strict-host 24-hour aggregate completed with journalctl and aggregation exit 0 and no stderr; it matched zero `callback_dispatch_timing` events on `route_key=account_root`. Count/average/maximum are unavailable for all four timing fields because the window was empty. It does not explain or disprove the reported 2–3 second Back, identify the delay source, or close all-button latency. No raw logs were returned and no runtime change occurred.

### A7 — Account-root aggregate recheck — 2026-10-11 05:31 +07

A second, separately Owner-approved strict-host 24-hour aggregate completed with `SSH_EXIT=0`, `JOURNALCTL_EXIT=0`, `JOURNALCTL_STDERR_BYTES=0`, and `AGGREGATE_EXIT=0`. It matched zero `callback_dispatch_timing` events for `route_key=account_root`; `guard_ms`, `handler_ms`, `render_helper_ms`, and `dispatch_ms` each had count 0, with average/maximum unavailable. No raw log records were returned. This still cannot correlate the reported 2–3 second Account → Back delay or identify bot, Telegram, network, device, or client-render cause. A7 remains open; no runtime change occurred.

### A7 — Account → Back route classification — 2026-10-11 05:47 +07

Source confirms the prior `account_root` query classified only `menu|main_profile` (opening Account). Account → Back emits `menu|main`, classified `main_home`; the 05:31 aggregate therefore did not sample the reported Back click. In the local Menu handler, the callback ACK is sent before language lookup, pending cleanup, keyboard construction, and Telegram edit; the pre-ACK admin check is an in-memory `OWNER_IDS`/`ADMIN_IDS` set lookup. No synchronous DB/network operation before ACK was found. The focused emitted Account keyboard → registered Menu handler → Home → Package child Back to Account fixture passed (`Ran 1 test in 1.995s — OK`) with an immediate no-I/O driver. A standard full-module rerun produced no result after its first test started for >120 seconds and was interrupted (`NOT_VERIFIED`, not a product failure). This identifies the correct live route but does not resolve post-ACK render/network/client delay; A7 stays open.

### S12.35.274 — Ticket-input Back response-order follow-up

The exact `ticket|start` Back emitted by the production Ticket-input keyboard now receives its single ACK before `get_user_language`; the existing Ticket-menu render remains unchanged. Only that exact callback moved; all other Ticket validations and data reads retain their previous order. The registered-route regression was RED on original source (language lookup observed ACK count `0`) and passed after the narrow change with an immediate no-I/O runner. Its CI-listed test file compiled; a broader local run did not complete within the bounded 30-second window, so no module/CI pass is claimed. No production Ticket, Telegram, or service state was touched.

Update: the subsequent CI-listed `AdminTicketReplyOriginPaginationTest` fixture run passed all five methods, including the S12.35.274 callback; this supersedes the earlier incomplete local run. This remains fixture verification, not remote CI or live latency.

### S12.35.275 — Customer Ticket preview response-order follow-up

The real `public_support_ticket_list_keyboard` emits `ticket|pv|<id>` and the exact registered `^ticket\|` handler now validates a well-formed ID/origin, ACKs before both the synchronous language lookup and the ticket read, then offloads the read-only `get_support_ticket` call through `asyncio.to_thread`. Valid preview still renders the existing detail and controls. A stale/missing ticket now edits the screen to a concise not-found state with a valid My Tickets/Ticket return and Home, since the callback has already been acknowledged; malformed IDs retain the alert. RED first caught ticket lookup at ACK count zero, then caught language lookup still at zero; both boundaries are asserted. The CI-listed fixture class passed five tests, the two new preview checks passed, and stale/malformed compatibility checks passed under the immediate no-I/O driver. Test files compiled. This proves source-fixture ordering and recovery only; no production Ticket read, live timing, full compile, remote CI, or deployment occurred.

### S12.35.276 — Customer Ticket summary Back response-order follow-up

The emitted `ticket|summary|<id>|profile_result|feedback_result` Back now ACKs once before the language lookup, then offloads the read-only ticket lookup through `asyncio.to_thread`; a present ticket still renders its existing summary and View-ticket control. RED was reproduced on source (`language_ack_counts=[1, 0]`). If the row is missing, the already-ACKed callback renders a Ticket-menu/Home recovery screen instead of attempting a late alert. `AdminTicketReplyOriginPaginationTest` ran 7 tests in 82.822s — OK with the immediate no-I/O fixture runner, including success, stale recovery, single ACK/order, and existing Ticket navigation cases. Test-file `py_compile` exited 0 and `git diff --check` exited 0. Full `bot.py` compile produced no output for over two minutes and was interrupted (`NOT_VERIFIED`, not a syntax failure). No production Ticket read, Telegram send, provider, wallet, merge, deploy, or restart occurred.

### S12.35.277 — Customer Ticket Reply prompt response-order follow-up

The actual Ticket detail keyboard's emitted `ticket|reply_user|<id>` now ACKs once before language lookup, then performs only the read-only ticket lookup through `asyncio.to_thread`. On success, the existing reply prompt is rendered with actor-owned `awaiting_ticket_reply` pending state and Back to the same Ticket detail; no reply text was submitted. On a stale row, it renders Ticket-menu/Home after ACK without creating pending state. RED: the language seam observed ACK count `0`; a first GREEN attempt also exposed a duplicate ACK in the shared path, which the final tests assert absent. The full CI-listed Ticket fixture class ran 9 tests in 104.359s — OK; test-file `py_compile` and `git diff --check` exited 0. Attach/Done and live/runtime latency remain untested; no production data or external side effect occurred.

### S12.35.278 — Customer Ticket Attach prompt response-order follow-up

The actual Ticket detail keyboard's emitted `ticket|attach|<id>` now ACKs once before language lookup, then performs only the read-only Ticket lookup through `asyncio.to_thread`. Success preserves the attachment prompt, actor-owned `awaiting_attachment` state, and emitted Back-to-detail/Home controls; no file upload occurred. A stale ticket renders Ticket-menu/Home after ACK without creating pending state. RED: language lookup observed ACK count `0`. The complete CI-listed Ticket fixture class ran 11 tests in 129.764s — OK; test-file `py_compile` and `git diff --check` exited 0. Reply and prior Ticket routes remained green; Done is intentionally untouched for a separate state-changing-action review. No live timing or production data access occurred.

### S12.35.279 — Customer Ticket Done response-order follow-up

The emitted `ticket|done|<id>` control now ACKs once before language lookup; its read-only Ticket lookup runs via `asyncio.to_thread`. The existing status update remains unchanged and is called exactly once only after a fixture row exists; a stale row gets Ticket-menu/Home after ACK and triggers no update. RED: the language seam saw ACK count `0`. The full CI-listed Ticket fixture class ran 13 tests in 146.806s — OK, including unchanged Done success controls, stale recovery, and all earlier Ticket navigation/read/prompt cases. Test-file `py_compile` and `git diff --check` exited 0. The status-update function remains synchronous after ACK, so screen-edit time is not proven; no production Ticket data was read or mutated, and no live latency claim is made.

1. Separate negative-group guards/final timing observer from business routes; they do not make an unmatched business callback functional.
2. For remaining Admin actions, exercise an emitted control through its registered handler, then verify result/error, pending state, Back/Home and authorization with inert fixtures.
3. Continue customer route families and dynamic values, retaining ownership and product/mode context; stable engines and AutoPost WIP are protected.
4. For stale/repeated/expired controls, assert no resubmit, charge, provider or production-data mutation.
5. After route evidence is complete, use anonymous live timing distribution plus owner-timed menu samples to finish latency diagnosis. The historical 16:57 two-route sample is not whole-bot smoothness evidence.
6. Rows without route evidence remain incomplete. Do not close the goal from counts or name-based candidate matches.

## S12.17 current-branch update — 06/10/2026

- The baseline table above remains tied to source `0929d61a`; the current branch extends both media callback patterns to accept a 32-hex result token while retaining legacy tokenless syntax so old buttons can be caught and rejected by the handler.
- Local registered-handler evidence: `tests/test_media_preview_callback_snapshot.py` has 19 focused cases. The test harness uses the actual production result cache/keyboards/handler bodies and exact `CallbackQueryHandler` registration lines; only Telegram send/provider-facing helper calls are inert. Evidence covers valid Select and Preview dispatch with the emitted token, stale replacement-cache rejection, cross-user isolation, product-context mismatch, TTL expiry, tokenless legacy data, invalid index, callback length and current/stale selected-video License follow-up.
- RED: on baseline `0929d61a`, five targeted assertions failed: emitted music and Pixabay controls had no snapshot token; old music Select resolved to `Track B` after the cache was replaced; a showroom control still reached selection after switching to video add-on; old Pixabay Preview resolved to result B. These failures occurred after correcting the harness and were behavioral assertions, not setup errors.
- GREEN: current-branch `python -m unittest tests/test_media_preview_callback_snapshot.py` → `Ran 19 tests in 51.593s — OK`; valid Preview and License callbacks also reach their registered helper with the same result token. Provider calls, real Telegram sends, job creation, Xu mutations and production-data writes were zero.
- Delivery: PR [#1382](https://github.com/manhtoangreensky-wq/bot/pull/1382) merged as `979c0ee5d9cc3b51d23b5c6470a6d02947f69208`; both required PR checks and main-push CI passed. Bot-only deploy [#37486561839](https://github.com/manhtoangreensky-wq/bot/actions/runs/37486561839) succeeded. Read-only VPS verification confirmed the exact SHA, `toanaas-bot.service`, `toanaas-web.service`, and `nginx.service` active, `NRestarts=0`, and health `status=ok`. Manual Telegram/provider QA remains unclaimed.
- The 3 named handler references now have focused route evidence: media preview and Pixabay are PARTIAL; suggested music still has no executed route evidence. The overall bot audit remains open.

## S12.18 current-branch update — 06/10/2026

- A2 route evidence found an immediate-parent mismatch in the shared Admin package-order screen: the package entry rendered a Back control to `menu|finance`. The same screen is reachable from Finance, so the correction carries and validates the opening origin.
- `tests/test_admin_package_orders_back_origin.py` executes both origin callbacks through the registered menu handler; related Finance and Broadcast pending cleanup regressions remain green. CI invocation is included.
- Delivery: PR [#1383](https://github.com/manhtoangreensky-wq/bot/pull/1383) merged as `5c040c22f2cf07b9edaa9631c219dbf07c15a6ff`; required checks and main-push CI passed. Bot-only deploy [#37496473987](https://github.com/manhtoangreensky-wq/bot/actions/runs/37496473987) succeeded. Read-only VPS verification confirmed exact runtime SHA, all three services active, `NRestarts=0`, and health `status=ok`.

## S12.19 current-branch update — 06/10/2026

- A2 route evidence found two Security/DB child keyboards that returned to the Admin root instead of their immediate module parent; the two child screens also needed origin tokens when opened from each other. The focused test covers both production builders and registered menu dispatch; PR/merge/deploy are pending.
- Delivery: #1384 merged/deployed at `3557b97a59b19b267f07efe5558269ea6894f9ec`; 163 configured CI tests OK; deploy 37505100609 SUCCESS; exact SHA/tracked source/services verified, manual Telegram navigation NOT_TESTED.

## S12.20 current-branch update — 07/10/2026

- Seven Admin module entry routes lost their parent (Queue Status/Help, Sales Ready, Dashboard, Provider Status/Routes, Smoke Test). Actual emitted callbacks and registered menu dispatch reproduced the mismatches.
- A closed UI-origin branch preserves each allowed parent through Back and refresh; original report/queue/provider renderers and business controls stay in use. Legacy callbacks retain their original parent. Public/invalid contexts stop before cleanup/read/render.
- Corrected baseline fixture: 15 behavioral assertions fail, 0 setup errors. Focused 3 tests and adjacent regression command: 27 tests OK in 38.252s. Protected source comparator passes; #1385 is verified deployed at `406280d6`, main CI 166 configured tests OK, deploy 37508350342 SUCCESS, exact runtime SHA/tracked source/services verified. Manual Telegram QA NOT_TESTED.

## S12.21 current-branch update — 07/10/2026

- Three Queue-entered confirmation guides lost origin: Unfreeze tools, Freeze video and Refund job. Prompt Back/Cancel retain Queue; acknowledgement Back returns to the same confirmation prompt and then Queue. Legacy guide entries preserve their existing parent and command text.
- Baseline: 3 methods, 4 behavioral failures, no setup errors. Local adjacent run: 30 tests in 48.340s OK; final focused 4 tests in 12.724s OK, including actual throttle/safe-mode/video-dedupe guard traversal before the registered menu handler under normal and maintenance/tool/provider freeze fixtures.
- Confirmation text/builders, operation bodies, product engine sources and common guards are unchanged by the protected comparator. #1386 is verified deployed at `877aea89`, 170 configured main CI tests OK, deploy 37511737977 SUCCESS; exact SHA/source/services verified. Manual Telegram/client QA NOT_TESTED.

## CSKH UI evidence — S12.22

- Actual emitted Support → Góp ý admin control executes its exact registered handler and read-only command. Empty/populated/filtered result markup was missing (3 RED assertions); a 15-long-row reply had 6,937 visible characters and failed the Telegram message-limit assertion.
- Two renderer changes reuse unchanged navigation/chunk helpers. Four focused methods pass; adjacent run `35 tests in 63.974s — OK` includes prior feedback tests, actual Back/Home menu dispatch and full 15-row delivery with navigation on the final chunk. Full source scope comparator passes; final compile/CI/PR/deploy pending.

- S12.22 delivery: #1387 verified deployed at `8faa35eb93ac5a967d1f3f6eb097c735987ecf91`; main compile and 174 configured tests OK; deploy 37517206697 SUCCESS; SSH exact SHA/source/services verified. Manual Telegram/client QA NOT_TESTED.

## S12.23 — Ticket hub/read-only panel UI evidence

- Actual Support emitter → registered Ticket handler/keyboard lost parent. Stats/Templates shared the same unrelated Admin-root Back and did not validate origin.
- Final focused suite on baseline: 3 behavioral failures, 0 setup errors; business/pending regression passes. Final branch 4 methods OK; adjacent Ticket/inbox subset 24 tests in 36.372s OK. Module/panel/sibling Back, repeat, legacy, permission/origin rejection and callback bounds verified through registrations; data/report calls are inert.
- UI origin fields and read-panel keyboard arguments are the only handler changes. Data/status/reply/list/file, menu router and engines/services/providers/workers/config unchanged by source comparator. Compile/PR/CI/deploy pending.

- S12.23 delivery: #1388 deployed at `c0a05ce0910dab0242af593ae17b39be430c0d55`; PR/main checks and 178 configured CI tests OK; deploy 37521327174 SUCCESS; SSH exact SHA/tracked source/services verified. Manual Telegram/client QA NOT_TESTED.
- Remaining A1/A2 route matrix is still partial; continue S12.24 emitted-control/registered-handler evidence. A6 wording backlog records 3 stale Railway mentions across 2 rendered Admin UI functions, with no configuration changes. No whole-bot completion claim.

## S12.24.1 — Provider/Worker route label evidence

- Reproduction: the actual Provider/Worker module keyboard emitted `menu|admin_provider_routes|admin_provider_worker` on the label “🎬 Video job”. The registered `handle_menu_callback` validated that origin and rendered `admin_provider_routes_text`, headed “Route/Group Info”. The label did not describe the destination.
- RED: focused registered-handler regression failed on the observed label/destination mismatch.
- Fix: changed the single button label to “🧾 Route/Group Info”; callback, handler, route output, provider state and commands are unchanged.
- GREEN: Provider/Worker module tests `4 OK`; adjacent Billing guide tests `3 OK`; full `bot.py` and changed-test `py_compile` exit 0; `git diff --check` exit 0 (LF→CRLF warning only).
- Scope: one UI label plus one assertion in the existing registered-handler regression file; no provider call, secret, wallet, production data or Telegram message.
- Delivery: [PR #1389](https://github.com/manhtoangreensky-wq/bot/pull/1389) merged as `54ee434aab7c44b09af793bdb7dd9764976cf3bd`; both required CI checks SUCCESS. Exact-SHA bot-only deploy [37524980913](https://github.com/manhtoangreensky-wq/bot/actions/runs/37524980913) SUCCESS with workers disabled. Read-only SSH confirms exact runtime/source SHA, bot/web/nginx active, `NRestarts=0`, health `status=ok`. [PR delivery evidence](https://github.com/manhtoangreensky-wq/bot/pull/1389#issuecomment-6024706054).
- Manual Telegram/client QA remains NOT_TESTED. A1/A2 inventory remains open.

## S12.24.2 — Admin Package command-guide labels

- Reproduction: the registered Admin Package module emitted “Catalog gói”, “Cấp combo”, “Cấp tháng”, and “Gói của user”. The corresponding registered menu-handler destinations rendered command instructions for `/package_catalog`, `/grant_combo`, `/grant_monthly`, and `/user_packages`.
- RED: all four button-label expectations failed before the UI correction; no dispatch/setup error occurred.
- Fix: label them “Hướng dẫn xem catalog gói”, “Hướng dẫn cấp combo”, “Hướng dẫn cấp gói tháng”, and “Hướng dẫn xem gói của user”. Preserve callback payloads and package/order operations.
- GREEN: Admin module suite `5 OK`; adjacent Package Orders Back-origin suite `2 OK`; full `bot.py` and changed-test `py_compile` exit 0; `git diff --check` exit 0. Test traverses Admin → Packages → each emitted control → help page → emitted Back → Packages.
- No package grant, wallet/data mutation, provider call, production job or Telegram send.
- Delivery: [PR #1390](https://github.com/manhtoangreensky-wq/bot/pull/1390) merged as `1f1b035edb225f8fef6b475836c75f6c7b609a81`; both required CI checks SUCCESS. Exact-SHA bot-only deploy [37528116347](https://github.com/manhtoangreensky-wq/bot/actions/runs/37528116347) SUCCESS with workers disabled. Read-only SSH confirms exact runtime/source SHA, bot/web/nginx active, `NRestarts=0`, health `status=ok`. [PR delivery evidence](https://github.com/manhtoangreensky-wq/bot/pull/1390#issuecomment-6025092937).
- Manual Telegram/client QA remains NOT_TESTED; A1/A2 audit remains partial.

## S12.24.3 — Queue command-guide acknowledgement copy

- The three Queue confirmation prompts emit Freeze Video, Unfreeze Tool and Refund Job controls. Registered dispatch of each button only displayed the manual slash command; no operation was invoked. The old “✅ Xác nhận” CTA and “Đã xác nhận thao tác admin” result heading overstated what happened.
- RED: the new actual-emitter/registered-handler regression reproduced the ambiguous CTA in all three cases before the code change.
- Fix: the CTA now says “📋 Xem lệnh cần chạy” and the destination heading says “Hướng dẫn thao tác admin”. Callback values, command text, authorization, Back/Cancel routing and operation handlers are unchanged.
- GREEN: Queue confirmation suite `5 tests OK`; Admin module child Back suite `5 tests OK`; `git diff --check` exit 0. Local `pytest` is unavailable. Full `bot.py` compile produced no output for over 7 minutes and was interrupted; this is neither PASS nor a syntax failure. Required CI compile/test gates remain pending.
- No slash command, provider call, wallet/database mutation, job, production-data write or real Telegram send occurred. Manual Telegram/client QA NOT_TESTED.
- Delivery: pending PR, CI, merge and deploy.

## 2026-10-08 current-main reconciliation for A3/A5

The registration table above is a historical candidate inventory: a test filename reference alone is not route proof. The initial A3/A5 reconciliation was taken when GitHub main was `76f0454fbab5e467f9ca71a0135b6fd05d8d70c4`; compared with the local UI audit base `93919f93d7207f252252f10f9c03d1e8a2d458f8`, that snapshot's only intervening commit changed `services/remote_worker_api.py` and one Product Video worker-authority test, while the bot keyboard/handler source was unchanged. Current GitHub main and the VPS bot runtime have since advanced together to `ea516e37c1e482b5cb8708d5b7591cf93c1ecfcc` after PR #1410/#1411; current deployment/worker scope is reconciled in S12.35.84 and `TELEGRAM_UI_BATCH_CLOSURE_20261008.md`. The following evidence supersedes the old candidate-status text only for the named small-flow families:

| Handler family | Current emitted/registered route evidence | Remaining gate |
|---|---|---|
| handle_menu_callback | S12.35.34/.43/.44/.47/.51/.52/.54/.55/.59; emitted safe root, Guide, Account, Notes/Documents, Feedback, Billing, Finance, System and Admin Internal Archive controls were dispatched through the registered menu handler. S12.35.96's CI-listed focused case passes the Vietnamese public root row/route contract; S12.35.148 verifies actual public/Admin root keyboards across all 17 supported locales against registered callback patterns and byte limits. | Selected downstream screens only; dynamic controls, protected processing, translated copy semantics and Telegram-client visual/latency QA remain open or excluded. |

S12.35.97 additionally dispatches the actual emitted customer `menu|translate` root control, the emitted language-hub child, and its Back/Home through the registered `handle_menu_callback`. This verifies that navigation slice only; translation/session/provider terminals remain excluded.
| handle_free_hub_callback | S12.35.15 exercises emitted `freehub|main` and maintenance pending cleanup; .34 joins the public-root Free Tools link to its registered route; .68–.70 verify Prompt Library root/category/detail Back ancestry and exact result restoration; .71–.74 cover Utilities/Translation/Prompt/Upload prompt Back with owner-scoped pending cleanup; .98–.101 cover rate, QR, Avatar and Weather prompt/Back routes; .102 verifies Meta/Caption/Ideas suggestion Back; .103 verifies Notes/Docs → Memory → Back ancestry. S12.35.116 source-audits all 14 Free Tools root label/callback pairs against route branches; no mismatch found, without dispatching the action paths. | Other tool terminals remain unverified; exchange-rate/network, QR generation/input, Avatar generation, upload processing, Music/SubDub/Voice helpers, publish package and downloader execution were not run. No provider call or production mutation is claimed. |
| handle_pricing_callback | S12.35.3/.4/.47 cover emitted Top-up, account pricing/membership/catalog and Back ancestry through Pricing/Menu handlers; S12.35.143 reconciles the Vietnamese “Khuyến mãi / Thành viên” label; .144 maps all 16 Vietnamese catalog controls to registered destinations; .145 reviews market-dependent Pricing hub controls and selected origin regressions; .154 dispatches the public non-core-locale catalog Back through the registered handler for all 14 supported locales outside vi/en/zh. S12.35.166 additionally follows the actual public main-menu Bảng giá button (`pricing|main`) through the registered Pricing handler and its emitted `menu|main` Home through the registered Menu handler, restoring the exact main-menu callback set; .204 follows emitted Pricing Guide → Back to the exact hub and Home to Main for all 14 fallback locales. Pricing/Top-up tests ran 20 tests in 130.171s — OK. | Payment/top-up confirmation and live pricing source remain separate gates; action callbacks, remaining all-locale variants, and whole-catalog Telegram visual/latency QA remain open. The Owner's <1s screen report is not correlated to a server timing event and does not establish all-button latency. |
| handle_feedback_callback / handle_language_callback | S12.35.45/.46 cover selected emitted start/category/cancel/unsupported and supported/unsupported-language paths; S12.35.113 verifies the actual public-root Language entry → emitted picker Back → identical Main callback set through the registered handler without preference/usage/broadcast writes. S12.35.197 dispatches all eight actual emitted Feedback category callbacks through the registered pattern/extracted handler and verifies ACK, category pending owner, prompt, Back and Home. S12.35.205 runs transient retry via the actual registered non-command `MessageHandler`, decorated `handle_message`, and real idempotency decorator using fixture-only downstream seams. | No real feedback delivery or production language write; other message-handler branches, remaining action callbacks and user-visible latency remain partial. |
| handle_memory_callback / handle_doc_tool_callback | S12.35.15–19/.31/.43–45 cover pending ownership/expiry and Notes/Documents landing/back exits; S12.35.57 covers empty-delete stale-pending cleanup plus registered Document tool Back/page-prompt Back; S12.35.62 dispatches Memory empty-delete → Notes/Docs Back through registered Memory/Menu handlers; S12.35.65 dispatches Saved Notes list/detail/Cancel ancestry; S12.35.66 dispatches Delete-picker choice → confirmation → Cancel back to the same picker; S12.35.67 dispatches search results → detail → Cancel → Back to exact search results with stale/expired/foreign rejection; S12.35.123 rejects tokenless and stale Delete confirmations after cancel/reconfirm and accepts only the current per-user note/token/TTL using a fake DB. | Destructive behavior was exercised only against a fake in-memory DB; no production note/DB was accessed. Other note CRUD, search mutation, file upload/save, and PDF/Word processing terminals remain untested. |
| handle_internal_archive_callback | S12.35.31 verifies the type-screen Back destination with/without a pending preview file; S12.35.59 covers Archive root → Notes; S12.35.138 covers emitted Search → Back for root and department search, including TTL expiry and live per-user state precedence through the registered handler. Emitted Search Home then reaches the registered Menu handler and clears only that actor's draft. S12.35.151 exercises emitted result → registered `view`, verifies fixture detail output, and rejects malformed/missing/stale `view`/`file` IDs with one ACK and no unrelated pending cleanup. S12.35.152 follows the actual emitted `file` control to the registered handler and verifies a single fixture send payload. S12.35.167 follows the actual emitted preview Save button to the registered `archive|` handler; the fixture save happens once, ACKs once, clears pending, and a replay is rejected without a second save. S12.35.168 dispatches the actual emitted Change department and picker Back controls through the registered handler, restoring the exact preview and preserving fixture file/type state. S12.35.169 dispatches the actual emitted Edit control through the registered handler and verifies the metadata prompt plus owner pending state without submitting text. S12.35.170 dispatches the emitted discard-to-department control through the registered handler, removes only the actor's draft while preserving a second user's full pending snapshot, and returns to the matching department dashboard. S12.35.171–.177 dispatch the actual emitted Help, type picker/selection, quick-save, department Search, root/dept Back, and root Search controls through the registered Archive handler; exact parent controls and pending-state results are asserted using fixture-only state. S12.35.178 dispatches the actual emitted department Quick Save callback after TTL expiry; it ACKs once, returns to the exact root, clears only the expired actor's pending state, preserves another user's fresh state, and performs no document lookup. S12.35.179 dispatches the actual emitted “Hồ sơ gần đây” callback after TTL expiry; it returns to the exact root without recent/document lookup or send, clears only the expired actor, and preserves another user's fresh pending state. S12.35.180 dispatches the actual emitted “Chọn loại hồ sơ” control after TTL expiry; it returns to exact root, creates no choosing_type/awaiting_file state, and preserves another user's fresh pending state. | No production search or archive/customer document was read or written; Telegram delivery, remaining action values, repeat/error handling outside the tested IDs, and live/client timing/visual remain untested. |
| handle_storage_addon_callback | S12.35.58 dispatches the emitted custom-input Back through the exact registered `storage|` handler; the root keyboard Back matches the registered `menu|` route. | Payment confirmation/purchase, expiry/repeat and Telegram client timing remain untested. |
| handle_admin_gopy_callback | S12.22 exercises the emitted Support inbox control through the callback to a read-only command result; empty/populated/filtered rendering and Back/Home are covered. | No live inbox/customer data read or real message. |
| handle_ticket_callback / handle_marketing_callback | S12.34.1/.2 cover selected customer Ticket ownership/stale paths; S12.35.60 covers customer-owned list/detail/prompt Back and malformed/foreign rejection; S12.35.20/.22 cover Support-origin Marketing planner Back and legacy fallback; S12.35.90 exercises emitted admin reply-send and attachment-send callbacks through the registered handler with FakeBot; S12.35.94 verifies customer category-prompt Back; S12.35.95 traces the public direct general-support entry and records the Owner's decision to preserve that one-step path instead of exposing the separate category chooser. | No real Telegram delivery or production ticket write; payment/messaging terminals remain outside this navigation audit; content generation and publishing are not claimed. |
| handle_pkgcombo_callback | S12.35.61 dispatches the emitted Image package group and Back to the Packages keyboard; S12.35.139 traverses emitted monthly Image group → detail → Back; S12.35.140 traverses emitted Combo group → Combo detail → Back; S12.35.141 traverses package home → Notes → Back; S12.35.142 traverses package home → My Packages → Back. S12.35.191 verifies Account Pricing main, Account Total, and public Catalog Total origin tokens survive package group → detail → Back → group → home → exact Pricing parent. Each chain uses the exact registered `^pkgcombo:` handler and inert fixtures. | Other package routes and purchase/checkout/order/payment terminals are not claimed. |
| handle_broadcast_lite_callback | S12.35.21 dispatches emitted read-only History/Schedule/Limits controls and checks their immediate-parent Back. | Delivery, draft confirmation, schedule writes/toggles and AutoPost WIP are excluded. |
| AutoPost, translation, music/voice and media/product engine handlers | Intentionally not executed by this UI/navigation audit, consistent with the protected-scope contract. | NOT_TESTED / EXCLUDED, not pass. |

No new product-code behavior is asserted by this reconciliation. The audit's source-inventory and selected route evidence do not establish all-handler correctness or live Telegram UX; A3/A5 remain PARTIAL until remaining in-scope routes are dispatched or explicitly excluded and their evidence is current.

## Final batch closure recheck — 08/10/2026

- S12.35.75 extends actual FreeHub item Copy through the registered handler, preserving exact suggestion IDs/text and library Back; 3 RED assertions → focused GREEN.
- S12.35.76 extends Marketing's six follow-ups and custom-brief result to maintain CSKH ancestry; 7 RED assertions → 5 GREEN methods including legacy Admin.
- S12.35.77 extends Memory's token/TTL/result validation to search-tagged View/Delete before note reads or draft cleanup; 11 RED assertions → 6 GREEN regression, including unchanged saved-list/delete-picker and other-user draft preservation.
- S12.35.78 extends Operator→System origin through all six emitted static/provider children, details/refresh and Back; 7 RED assertions → 3 GREEN regression with legacy/public/invalid-origin checks.
- Current integrated safe UI gate: 41 configured modules, `218 passed, 355 subtests passed in 589.44s`; fixture-only and no imported runtime bot. Full current bot compile and asserted protected-source/file comparator passed.
- Current batch changes 23 text declaration blocks; 9,742 remain identical. No protected service/provider/worker/engine/config file changes. This is source-scope evidence, not all-terminal engine or live correctness.
- A7 remains Owner-deferred: server menu events 306.038–512.953ms are not matched click-to-screen evidence for the 2–3s Account report. No latency-cause/whole-bot claim. Detailed closure and delivery gates: `TELEGRAM_UI_BATCH_CLOSURE_20261008.md`.

## S12.35.287 — Translation voice target picker source/Back evidence

- The Translation voice menu now emits a compact source token (`language` or `media`) with its audio-picker callback. The received-audio action keyboard uses its own `actions` token. The registered `tr_` handler restores that exact originating screen from the target picker; More-page Back returns to the base target list, and Home routes to Main.
- If the recent audio cache expires, More-page Back still restores the base target list through a dedicated navigation callback; initial picker entry and target selection continue to require recent audio. A missing-audio warning returns the matching source-screen keyboard. Test-only runner and media seams were inert.
- Four focused registered-handler regressions passed in 3.352s, including the text/file More/Back regression after its immediate no-I/O fixture was switched from `asyncio.run` to the existing no-yield driver. This proves source routing and fail-closed runner boundary only; it does not measure Telegram rendering or live callback latency. Full `bot.py` compile and remote CI remain unverified; no deploy or runtime change occurred.

## S12.35.101 — Free Tools weather callback evidence

- The Utilities keyboard's emitted `freehub|util_weather` and `freehub|util_weather_input` controls were dispatched through the exact registered handler. The deterministic weather stub was called for Hà Nội, Đà Nẵng, and Hồ Chí Minh only for the overview; opening the input prompt made no additional call.
- The prompt's emitted Back returned to the same Utilities callback set and cleared only the current fixture user's pending state. Focused test: 1 test in 1.005s — OK; root/menu module: 28 tests in 28.245s — OK.
- No live weather API, network, production source, DB, provider, wallet, job, AutoPost, engine, or Telegram action. This closes route evidence only; it does not claim live client visual/latency validation or a production bug fix.

## S12.35.284 — Customer My Tickets callback responsiveness

- The actual public Support keyboard emits `ticket|mine|support`; the exact registered Ticket handler now ACKs that valid route before language lookup. It sends only the read-only `list_support_tickets(user_id=uid, limit=10)` call through `asyncio.to_thread`, then keeps the existing keyboard/text rendering on the event loop.
- RED first observed `language → ACK → list` and no offload. The focused ACK/offload and invalid-origin tests passed `2 tests in 32.119s — OK`; public list Back/Home and detail→list Back regressions passed `2 tests in 33.734s — OK`; the legacy unscoped `ticket|mine` case passed. After the category ACK fix, the combined six-case Ticket list/category regression passed `6 tests in 72.927s — OK`. Assertions preserve actor-only pending cleanup and fail-closed invalid origins. The test module is already included in safe-navigation CI.
- A broader `tests.test_customer_ticket_action_ack` invocation did not complete after more than 150 seconds in the Windows test harness and was interrupted; it remains NOT_VERIFIED, not a product failure. Fixture-only evidence: no production ticket read, client render timing, remote CI, full `bot.py` compile, merge or deploy is claimed. No Ticket mutation, Telegram send, provider, wallet, AutoPost, or protected engine behavior changed.

## S12.35.285 — Customer Ticket category prompt ACK order

- The actual emitted `ticket|cat|image_error` control reached language lookup before the shared ACK, then set the actor's pending category and rendered the prompt. After the test-only fixture was given the omitted `SUPPORT_CATEGORIES` and prompt-builder globals, RED reproduced the order `language → ACK → pending`.
- The minimal fix early-ACKs only exact supported category callbacks and prevents a duplicate shared ACK. Unsupported-category fallback and pending, prompt, Back/Home semantics are unchanged. The focused emitted-control/registered-handler test passed `1 test in 13.785s — OK`, including foreign pending preservation. The post-change combined six-case Ticket list/category regression passed `6 tests in 72.927s — OK`. The existing `asyncio.run` category navigation test stalled without progress and is NOT_VERIFIED.
- Fixture-only evidence; no production ticket state, real Telegram, client rendering latency, full source compile, remote CI, merge or deploy is claimed. No ticket creation, provider, wallet, AutoPost, or protected engine action.

## S12.35.256 — Legacy public `buy_plan|` callback fallback

- Current source inventory found `handle_buy_plan_callback` registered but no current pricing/package keyboard emitter for `buy_plan|`; it is a stale-control compatibility route.
- The exact registered handler was dispatched with a stale public callback. It ACKed once, rendered the existing public package list, and did not call the inert `start_plan_purchase` seam. The fixture also asserted the current package keyboard has no `buy_plan|` callback.
- Focused result: `Ran 1 test in 6.261s — OK`. The test is included in the already-configured Account Pricing Back CI step.
- Scope limit: admin purchase/checkout, financial state, provider, and live Telegram behavior were not exercised. No production source changed.

## S12.35.253 — Package detail origin callback byte limits

- RED: the Combo detail Large Order callback was 74 bytes; the all-origin matrix found a 65-byte Combo detail selector and Large Order result Back, plus a 66-byte Prompt/Workflow group Large Order callback.
- Package group/detail selectors and origin-bearing Large Order callbacks/Backs now use a one-character allowlisted origin suffix. Registered routes decode it before rendering; a one-character package code is not treated as an origin.
- Focused registered-handler test: `Ran 1 test in 3.042s — OK` across all nine origin tokens, all seven task groups plus Combo (63 group screens), and both monthly/Combo detail paths (18 cases). Every emitted Package home/group/detail callback and Large Order result Back is ≤64 bytes; group/detail Back controls restore identical screens. The Large Order action itself is not dispatched. Changed test-file compile and scoped diff check exited `0`.
- An additional legacy group/detail regression emitted its test name but no result for 60 seconds and was interrupted; it is NOT_VERIFIED in this Windows runner, not a product assertion failure. The focused route matrix is the current evidence for this spec.
- No order request, DB, wallet, provider, Telegram send, or engine action occurred. Full bot compile, consolidated CI, final main/runtime comparison, and live/client verification remain open; no merge/deploy/restart.

## A7 — Approved 24-hour menu callback phase aggregate — 2026-10-10 22:01 +07

- One Owner-approved read-only SSH query for `callback_latency` on exact `menu|main` and `menu|main_video` returned `JOURNALCTL_EXIT=0`, `AGGREGATE_EXIT=0`, `JOURNALCTL_STDERR_BYTES=0`, `MATCHING_EVENTS=0`, and `MALFORMED_MATCHING_LINES=0`. No route/role groups existed to aggregate; no raw journal lines were returned.
- The remote shell wrapper subsequently returned SSH exit 2 because its final `exit` argument retained a PowerShell CRLF (`0\r`). The command had already printed explicit successful journalctl and aggregate exit statuses. No second query was run.
- An empty sample cannot prove the buttons fast or correlate a tap, and cannot assign a reported 2–3s delay to bot, Telegram, network, device, or client rendering. No runtime changes were made; A7 remains open.

## S12.35.242 — “Mark published” guide label through registered route

- The emitted `cat_publish` button now reads `📘 Hướng dẫn đánh dấu đã đăng`. Its callback remains `opmenu|markpublished|cat_publish`; the registered handler returns the `/mark_published` command guide, ACKs once, and Back returns to `opmenu|cat_publish`.
- RED reproduced the mismatch with the old `✅ Mark published` label. GREEN: all seven `OperatorMenuCallbackSingleAckTests` passed in 3.045s using immediate no-I/O fixtures; test compile and scoped diff check passed. The test is already listed in Admin Route Regressions CI.
- No job, queue, publication, API, provider, wallet, production data, AutoPost worker, or product-engine operation was invoked. This is local UI evidence only; Telegram rendering, consolidated CI, and live latency remain pending.

## S12.35.243 — “Publisher run” guide label through registered route

- The emitted `cat_publish` button now reads `📘 Hướng dẫn chạy Publisher`. Callback remains `opmenu|publisherrun|cat_publish`; the registered handler returns `/publisher_run` instructions, ACKs once, and Back returns to `opmenu|cat_publish`.
- RED reproduced the mismatch with the old `▶️ Publisher run` label. GREEN: all eight `OperatorMenuCallbackSingleAckTests` passed in 3.350s with immediate no-I/O fixtures; test compile and scoped diff check passed. The test is included in Admin Route Regressions CI.
- No Publisher command/API, job, queue, provider, wallet, production data, AutoPost worker, or protected engine was invoked. This is local UI evidence only; Telegram rendering, consolidated CI, and live latency remain pending.

## S12.35.244 — “Publisher status” guide label through registered route

- The emitted `cat_publish` button now reads `📘 Hướng dẫn trạng thái Publisher`. Callback remains `opmenu|publisherstatus|cat_publish`; the registered handler returns `/publisher_status` instructions, ACKs once, and Back returns to `opmenu|cat_publish`.
- RED reproduced that the old label `📡 Publisher status` looked like a live status screen even though only a command/API guide was rendered. GREEN: all nine `OperatorMenuCallbackSingleAckTests` passed in 3.992s with immediate no-I/O fixtures; test compile and scoped diff check passed.
- No Publisher API/status lookup, job, queue, provider, wallet, production data, AutoPost worker, or protected engine was accessed. This is local UI evidence only; live UI, consolidated CI, and latency remain pending.

## S12.35.245 — “Publish queue” guide label through registered route

- The emitted `cat_publish` control now reads `📘 Hướng dẫn hàng đợi đăng bài`. Callback remains `opmenu|publishqueue|cat_publish`; the registered route returns `/publish_queue` command/API guidance, ACKs once, and Back returns to `opmenu|cat_publish`.
- RED reproduced that `📮 Publish queue` looked like a queue screen; GREEN: all ten `OperatorMenuCallbackSingleAckTests` passed in 4.838s with immediate no-I/O fixtures. Test compile and scoped diff check passed; the module is in Admin Route Regressions CI.
- No queue, API/provider, job, wallet, production data, AutoPost worker, or protected engine was accessed. UI runtime rendering and live latency remain unverified.

## S12.35.246 — “Publisher handoff” guide label through registered route

- The emitted `cat_publish` control now reads `📘 Hướng dẫn bàn giao Publisher`. Callback remains `opmenu|publisherhandoff|cat_publish`; the registered route returns `/publisher_handoff` instructions, ACKs once, and Back returns to `opmenu|cat_publish`.
- RED reproduced the mismatch with `🤖 Publisher handoff`. GREEN: all 11 `OperatorMenuCallbackSingleAckTests` passed in 5.299s with immediate no-I/O fixtures. Test compile and scoped diff check passed; the module is in Admin Route Regressions CI.
- No queue handoff, job, Publisher command/API, provider, wallet, production data, AutoPost worker, or protected engine was invoked. Live Telegram rendering/latency remain unverified.

## S12.35.247 — “Publish cockpit” guide label through registered route

- The emitted `cat_publish` control now reads `📘 Hướng dẫn bảng điều khiển đăng bài`. Callback remains `opmenu|publishcockpit|cat_publish`; handler returns `/publish_cockpit` instructions, ACKs once, and Back returns to `opmenu|cat_publish`.
- RED reproduced the mismatch with `🎛 Publish cockpit`. GREEN: all 12 `OperatorMenuCallbackSingleAckTests` passed in 5.216s using immediate no-I/O fixtures; test compile and scoped diff check passed.
- No publish data, queue, API/provider, wallet, production data, AutoPost worker, or protected engine was accessed. This is local UI evidence only; runtime rendering/latency remain unverified.

## S12.35.248 — “Publish readiness” guide label through registered route

- The emitted `cat_publish` control now reads `📘 Hướng dẫn kiểm tra điều kiện đăng`. Callback remains `opmenu|readiness|cat_publish`; the registered route returns `/publish_readiness` instructions, ACKs once, and Back returns to `opmenu|cat_publish`.
- RED reproduced the mismatch with `🧪 Publish readiness`; GREEN: all 13 `OperatorMenuCallbackSingleAckTests` passed in 5.694s with immediate no-I/O fixtures. Test compile and scoped diff check passed.
- No readiness check, channel change, API/provider call, wallet, production data, AutoPost worker, or protected engine was used. Live rendering/latency and consolidated CI remain unverified.

## S12.35.229 — Origin-aware callback snapshot reconciliation and A7 retry

- The copy-only regression expected older unscoped callbacks for Account and Ticket parents. Current emitted controls preserve origins: public Support children use `ticket|mine|<support-child>`, Account entry callbacks carry `main_profile`/`profile`, the Account language button emits `back_lang|profile`, and Ticket-category My Tickets emits `ticket|mine|ticket_menu`.
- Updated only the expected callback sets in `tests/test_p0_i18n_root_flow_copy.py`; no `bot.py` or handler change. The emitted public Support-child Back round-trip through the registered Ticket handler passed (`1 test — OK`), and all 29 source-only functions in the copy module passed via direct invocation. Added the test module to the existing small-navigation CI command. Local `pytest` and GitHub CI remain unrun for this change.
- The standard Account-pricing fixture invocation using `asyncio.run` stalled on Windows and was interrupted; that invocation is not counted. Targeted reruns through existing immediate/no-I/O fixture drivers passed the Account catalog/detail Back chain and pricing-origin Top-up Back (2 tests), Account language picker (6 tests), and Credit Guide Back (3 tests), with zero failures/errors. The fixtures use fake preference/payment controls; no real preference write or top-up/payment was initiated. Other Account paths and normal Windows test-runner behavior remain unverified.
- The first approved retry at 17:54 +07 used journalctl `--grep`, returned exit 1 with empty stderr, and was not counted because the reducer did not preserve stdout; systemd documents that no-match grep can also return 1 ([journalctl issue #32422](https://github.com/systemd/systemd/issues/32422)). A corrected full-stream read at 2026-10-10 18:04 +07 returned `JOURNALCTL_EXIT=0`, empty stderr, `EVENTS=0`, `MALFORMED_MATCHING_LINES=0`, SSH exit 0, and no route rows. This is a verified empty 24-hour window, not proof of fast/slow handling. The earlier full-stream empty window at 17:16 +07 remains historical corroboration.
- The manual Bảng giá observation was `<1 second`, but has no precise click timestamp or correlated server event. Account → Back remains a 2–3 second report without a matched event. This does not locate delay in bot handling, Telegram transport, network, device, or client rendering. A7 remains partial; no production source/service/data change, raw log disclosure, Telegram send, provider, wallet, deploy, or restart occurred.

## A7 — Corrected approved 24-hour callback timing aggregate — 2026-10-10 17:16:56 +07

- One read-only SSH query ran `journalctl -u toanaas-bot.service --since '24 hours ago' --no-pager -o cat`; the journal process returned exit code 0 and empty stderr. The reducer returned `EVENTS=0 malformed_matching_lines=0` for `callback_dispatch_timing`.
- The earlier unchecked `NO_EVENTS` attempt remains invalid; this rerun is the verified result for its own 24-hour window. There are no route/handler timing values to aggregate or correlate with the Owner's approximate Account → Back report (2–3 seconds, no exact click timestamp).
- No raw log lines, user IDs, callback values, or payloads were emitted. No production code/data/service change, Telegram send, provider call, wallet operation, deploy, restart, or hardware inference. A7 remains partial; the empty sample does not prove smoothness or assign a delay cause.

## S12.35.228 — Callback timing observer coverage review

- Source review: instrumentation is installed after direct callback registrations, wraps every registered `CallbackQueryHandler`, and adds a final observer handler. Its static route key only singles out exact Main and Account-root menu callbacks; other inline callbacks are observable by static prefix/handler, but not by individual dynamic button payload.
- Boundaries: guard/handler time and the shared edit helper are measured. ReplyKeyboard/MessageHandler routes, transport before the bot receives an update, and client-side screen rendering are not measured by this callback observer.
- The initial bundled-Python run stalled before the callback fixture: faulthandler located the wait in Windows Proactor self-pipe setup (`socket._fallback_socketpair`/`accept`) invoked by `asyncio.run`. The fixtures perform no I/O; replacing only the test driver with `_run_no_io` resolved that harness stall.
- Focused verification: `python.exe -B -S -m unittest tests.test_callback_dispatch_timing -v` — `Ran 5 tests in 16.056s — OK`. These are extracted-source/fixture tests, not live latency proof. No production logger or handler code changed.
- Conclusion: an exact Owner tap time plus a matching route event is needed to diagnose an inline callback; absence of events requires a separately authorized runtime/log-delivery check. ReplyKeyboard and end-to-end rendering need independent measurement. No hardware recommendation can be supported yet.

## S12.35.225 — Public Video exact callback replay boundary

- The extracted guard was exercised before the registered `vprofile` route: the first query ID reached an inert route seam, a replay of that same ID was stopped before route dispatch and acknowledged once, and a distinct ID passed. Focused result: `Ran 1 test in 0.424s — OK`; test-file `py_compile` and `git diff --check` exited 0.
- Fresh continuation recheck (2026-10-11): the exact replay-boundary case passed in a combined three-case focused run (`Ran 3 tests in 6.728s — OK`), alongside the expired Document and Support/Ticket text-routing cases.
- No production change was justified. This proves exact Telegram update replay suppression only—not idempotency of two separate rapid taps, product output, or live latency. The actual Video handler body, job/provider/wallet seams and protected engine were not invoked; GitHub CI remains pending.

## S12.35.226 — Fresh approved callback timing aggregate

- One Owner-approved, strict-host read-only SSH query covered the preceding 24 hours and filtered only `callback_dispatch_timing`; it returned grouped count/average/maximum only.
- The SSH wrapper returned exit code 0 and the reducer printed `NO_EVENTS`, but the command suppressed `journalctl` stderr and did not propagate its exit status through the pipe. This cannot be treated as a verified zero-event count. No raw journal lines, IDs, or payloads were returned.
- No reliable new route latency sample was obtained. This does not reproduce a slow bot dispatch, correlate the reported Account → Back 2–3s, prove an instrumentation fault, or identify Telegram/network/client cause. A7 remains partial; no code or runtime change is indicated.

## S12.35.227 — Admin Support Ticket hub and read-only panel Back

- The actual Admin Support → Ticket admin entry, Stats and Reply-template controls were dispatched through the registered Ticket handler; its parent Back was dispatched through Ticket/Menu handlers. Assertions cover the exact parent, nested/sibling/self navigation, one ACK, and public/invalid-origin fail-closed behavior before pending cleanup or report reads.
- The first test run stalled in the Windows `asyncio.run` fixture startup without reaching assertions. Its callbacks use immediate inert coroutines, so this test now uses a single-step no-I/O driver which raises if a coroutine yields. Retest: `Ran 4 tests in 8.074s — OK`; test-file `py_compile` exited 0; `git diff --check` exited 0 with LF→CRLF notices only.
- No route defect reproduced and no production code changed. Ticket business controls were only inventoried, not invoked; no real ticket/report data, reply, message, provider, wallet, AutoPost, protected engine, merge, deploy, or restart. Consolidated CI and whole-goal closeout remain pending.

## S12.35.222 — Account-origin Support form prompt Back/Home

- Contract: from Account → Support, open each emitted Ticket, Premium, Bot and Consult input form, then dispatch the prompt's actual Back and Home controls through the registered Support/Menu routes. Back must restore the exact immediate parent keyboard; Home must restore Main. Clear only the current actor's pending form and preserve another user's fixture state.
- The first attempt errored before any route assertion because the test fixture lacked a deterministic `time.perf_counter` for the Menu handler. Adding the same inert clock used by the adjacent public-form test fixed the harness; this was not a product failure.
- GREEN: all eight emitted callback cases (4 forms × Back/Home) passed with exact parent callback sets, Main rendering, one ACK per route, actor-only pending cleanup, preservation of the other user's state, and zero create/classify/notify calls: focused `Ran 1 test in 53.834s — OK`; complete `tests.test_profile_support_pending_origin` module `Ran 7 tests in 119.708s — OK`.
- Limits: offline fixtures only; no text submission, real ticket, production data, Telegram message, provider, wallet, AutoPost, protected engine, merge, deploy, or restart. This closes only Account-origin Support-prompt navigation evidence, not live UI rendering or latency; consolidated CI and A3/A5/A6/A7 remain open.

## S12.35.223 — Account Support information exact Back/Home

- The emitted Account Support root's Admin-contact, Auto-support, Premium, Bot and Consult information controls were dispatched through the registered Support route. Their emitted Back callbacks restored the exact root callback list; their Home controls reached Main through the registered Menu route. No URLs or form controls were activated.
- Focused five-page Back/Home matrix: `Ran 1 test in 48.305s — OK`. The complete `tests.test_profile_support_read_back_origin` module passed `Ran 8 tests in 123.354s — OK`.
- Harness/compatibility findings: the prior imported `asyncio.run()` fixture stalled on Windows, so this test module now uses its immediate no-I/O dispatcher and rejects any awaited I/O. The first completed full run exposed a stale Account Premium expectation after S12.35.221: `ticket|mine|premium` is correctly wrapped as `ticket|mine|profile_premium`, whose registered Ticket route returns to `support|premium|profile`. The test expectation was updated; no product mismatch or production edit was found. The focused compatibility assertion passed in `4.514s`.
- Limits: offline navigation fixtures only, not Telegram-client rendering/latency. No lead form, contact URL, user message, ticket mutation, production data, provider, wallet, AutoPost, protected engine, merge, deploy, or restart. Consolidated CI and global A3/A5/A6/A7 remain open.

## S12.35.224 — Account Support form expiry Back/Home

- Expired Ticket, Premium, Bot and Consult Account-origin pending forms were dispatched via the registered non-command text handler using an in-memory clock and inert message. Each stale input returned expiry copy; its actual Back control restored the exact immediate parent and Home returned to Main. Only actor 123's expired pending key was cleared; fresh pending state for user 999 remained unchanged; create/classify/notify seams were not called.
- Focused matrix: eight form × exit cases in `Ran 1 test in 44.463s — OK`. Full `tests.test_profile_support_pending_origin`: `Ran 8 tests in 197.600s — OK`.
- Initial test attempts exposed two fixture-only setup errors (fresh other-user state was created before advancing the shared clock; keyboard flattener expected a query rather than a Markup). Both were corrected; no product assertion failed and production source did not change.
- Limits: fixture-only pending state; no customer message processing, ticket creation, production data, provider, wallet, AutoPost, protected engine, merge, deploy, or restart. Live rendering/latency and consolidated CI remain open.


## S12.35.220 — My Tickets parent-origin evidence

- RED: emitted My Tickets controls from Admin-contact, Auto-support, and Premium lost their immediate parent. Through the registered Ticket handler, list Back returned to Support root in all three public paths and all three Account-origin paths. Ticket category menu also emitted unscoped `ticket|mine`, losing its category-menu parent.
- Fix: the three Support-child buttons and Ticket category-menu button now carry narrow origin tokens. Ticket origin wrapping/parser keeps public origins and composes Account-scoped `profile_<page>` origins; list Back returns to the exact parent. The existing root, Account, detail-list, and Feedback-result origin regressions remain intact.
- GREEN: Support-child registered/emitted-route regressions ran 2 tests in 22.035s — OK over all six public/Account paths; Ticket category → list → detail → list → category passed 1 test in 3.799s — OK; final combined 8-route regression ran 8 tests in 50.903s — OK. The test module is already in the safe-navigation CI workflow; consolidated CI is pending.
- Verification limits: focused source-extracted callbacks compiled/executed. Full `py_compile bot.py` produced no output for 60 seconds and was interrupted (NOT_VERIFIED); `git diff --check` exited 0 with only existing LF→CRLF notices. No production ticket/data, ticket mutation, reply, attachment, provider, wallet, AutoPost, product engine, real Telegram message, merge, deploy, or restart.

## S12.35.221 — Premium-form My Tickets origin evidence

- RED: following the emitted form control through the registered Ticket route failed for both entry contexts: public emitted `ticket|mine`; Account emitted `ticket|mine|profile`. The Premium parent was absent, so Back could not be exact.
- Root cause/fix: the Premium lead-input keyboard used `support_flow_back_keyboard` with a context-free Ticket callback. Added optional `ticket_origin`; only this Premium form sets `premium`, while default callers retain their existing callback. Account wrapping yields `profile_premium`.
- GREEN: `test_premium_form_my_tickets_back_restores_premium_page` plus public/Account Premium-parent regressions passed: `Ran 3 tests in 32.322s — OK`. A subsequent full `tests.test_profile_ticket_ancestry` run passed `18 tests in 171.092s — OK`, including this Premium-form route and existing Ticket ancestry regressions. The test module compiles and uses source-extracted production handlers dispatched via registered routes. CI already includes `tests/test_profile_ticket_ancestry.py` in its Account Owned Ticket Ancestry step.
- Verification limits: an earlier full-module run printed two progress dots without further progress and was interrupted; the later complete module rerun passed. Whole-file `py_compile bot.py` still had no output after 60 seconds and was interrupted, so it remains NOT_VERIFIED. `git diff --check` exited 0 with existing line-ending notices. Consolidated CI is pending.
- No Ticket state mutation, reply, attachment, notification, production data, Telegram action/latency test, provider, wallet, AutoPost, protected engine, merge, deploy, or restart. This evidence closes only the Premium-form callback ancestry defect; global callback/latency audit remains open.

## S12.35.217 — Account-origin Support form pending-context addendum

- The public Ticket prompt's Back/Home regression remains green as previously recorded. To resolve the adjacent Account-form verification gap, `test_all_four_form_emitters_persist_their_account_back_context` now dispatches the actual emitted Ticket, Premium, Bot and Consult controls through their registered handlers with an immediate no-I/O test driver.
- The fixture confirms each emitted prompt retains the expected Account-origin `back_to` and that no ticket/business seam is called: focused test `Ran 1 test in 22.184s — OK`. The prior `asyncio.run()` fixture runner stalled on Windows; the replacement explicitly fails if a route yields I/O. The full `tests.test_profile_support_pending_origin` module subsequently passed 6 tests in 71.052s — OK; consolidated CI remains pending.
- No input was submitted and no ticket was created. This verifies pending-context emission only, not prompt Back/Home for every form or live Telegram rendering/latency. No production data, provider, wallet, AutoPost, protected engine, merge, deploy, or restart.

## S12.35.213 — Document Confirm/Add more emitted callback evidence

- The actual after-file keyboard builder emitted docflow|confirm and docflow|send_more for the one-file PDF fixture. The source registration expression selected the registered handle_doc_tool_callback route for each emitted value.
- Confirm returned the expected minimum-file alert once and performed no rendering/processing. Add more ACKed once and returned the same tool's upload prompt. The two focused route assertions passed through an immediate no-I/O coroutine driver.
- This replaces the prior hard-coded callback-only evidence. No PDF/file processing, send, provider, wallet, production state, AutoPost, protected engine, or real Telegram action occurred. Remote CI and client UX remain pending.

## S12.35.205 — Feedback retry through the registered text dispatcher

`handle_message` was exercised through the actual registered non-command `MessageHandler`, actual idempotency decorator, and Feedback pending handler. A one-time fixture classifier failure preserved the pending Feedback marker and left the message eligible for retry; retry created one fixture ticket, cleared only that user's Feedback marker, and replied/notified once. The focused assertion printed `registered handle_message retry assertion: OK`. Unrelated pending owners were stubbed false and AutoPost `context.user_data` was empty. No production data, real Telegram message, provider, wallet, engine, AutoPost, merge, deploy, or restart was touched. Other message-handler branches remain unverified.

## A7 — Bảng giá follow-up, 2026-10-10 approximately 11:01 +07

The Owner reports the Bảng giá screen appeared immediately (`<1s`) after the latest tap. The exact click timestamp was not supplied, so no individual server timing event can be correlated. This is a single user-visible observation, not proof that every button is fast; it does not resolve Account → Back (reported at 2–3 seconds) or identify Telegram/network/client delay. No Pricing patch or runtime action was indicated.

## S12.35.206 — Feedback-created ticket View Current Back origin

- RED: the actual ticket-created keyboard's View Current control was unscoped (`ticket|pv|901`), so the registered ticket handler rendered detail without knowing that Feedback's receipt was its parent.
- Fix: only the Feedback success path scopes that keyboard with `feedback_result`. The registered `^ticket\|` handler accepts this origin on the customer detail/reply/attachment/done continuations and read-only summary; detail Back targets `ticket|summary|<id>|feedback_result`. The wrapper keeps My Tickets, Support and Home unscoped in this flow; Account/profile and legacy routes retain their established destinations.
- GREEN: emitted keyboard → registered ticket callback → View Current → Back → receipt printed `Feedback result -> View Current -> Back -> receipt: OK`; Reply/Attachment prompt Back chains returned through detail to the receipt without submitting content or files and printed `Feedback result -> View/Reply/Attach -> Back -> receipt: OK`; five profile/legacy regressions printed `5 ticket/profile-origin fixture regressions: OK`; three Profile-result/legacy regressions printed `3 Profile-result/legacy ticket-origin regressions: OK`; registered feedback retry still printed `registered handle_message retry assertion: OK`. Changed test files compiled and `git diff --check` exited 0.
- Limits: full `py_compile bot.py` produced no output for about 100s and was interrupted (NOT_VERIFIED); ordinary unittest runner stalled in the known Windows Proactor fixture path, so focused no-I/O methods were executed directly. Resolve/Done was not invoked. Consolidated CI/source compile remain open. No live ticket/customer action, provider, wallet, production data, protected engine, merge, deploy, or restart.

### S12.35.203 — `pkgcombo:large_order` immediate-parent route evidence

- RED: the actual emitted large-order callback from Account-origin Packages returned `pkgcombo:home` and dropped the Pricing origin. Extending the registered-handler matrix to seven emitting screens identified the same defect from Home, Notes, My Packages, Image group, Combo group, monthly detail and combo detail.
- Fix: each origin-bearing emitter now carries its existing allowlisted Pricing token. The registered `handle_pkgcombo_callback` Back builder returns to the exact emitting screen; legacy unscoped controls still resolve without a synthetic origin.
- GREEN: 14 combinations (7 screens × Account Pricing/public Catalog origins) passed through the registered package callback route. A follow-up Home → large-order → Back regression passed for English, Chinese, and fallback locales. Together with image-group, monthly-detail, combo-detail, Notes and My Packages Back regressions, the final focused run passed `7 tests in 34.619s — OK`. Every callback ACKed once; the fake order-request and render boundaries recorded no external side effect.
- Test limitations: the full module stalled in the existing Windows Proactor Pricing-fixture `asyncio.run` helper before completion and was interrupted. Full-bot `py_compile` produced no output for 60 seconds and was interrupted; extracted changed functions compiled and executed in the targeted route test. Final combined CI remains required.
- Scope: callback navigation only. No real order, purchase, payment, wallet, provider, DB/data write, Telegram send, protected product engine, AutoPost, merge, deploy or restart. This route fix does not establish end-to-end client latency or close A3/A5/A6/A7.

## S12.35.199 — Public Pricing document-download callback dispatch

- The actual Catalog emits `pricing|download_pricing` and `pricing|download_guide`; the registered Pricing handler maps them to localized markdown plus the real in-memory `send_generated_markdown_document` helper. The helper reaches `query.message.reply_document`.
- A focused registered-handler test using an inert reply sink passed: `Ran 1 test in 3.119s — OK`. It verifies one ACK and exact filename/caption/content for both downloads. The first attempt stalled because the new test reused the legacy `asyncio.run` fixture dispatch; an immediate no-I/O driver and correct nested Query fixture resolved the harness issue. Test-file `py_compile` and `git diff --check` exited `0` (LF→CRLF notices only). Consolidated CI remains pending; no actual Telegram document was sent.
- The strict-host seven-day callback aggregate at 2026-10-10 03:10 +07 contained 14 records: `menu` 11 (avg 350.520 ms, max 529.393 ms), `pricing` 3 (avg 377.814 ms, max 741.848 ms), zero above 1 second, no other prefix. Runtime SHA `381d335961bea01db60cda99f0dfe98e2b2d1760`, bot active, `NRestarts=0`. These are sparse server-dispatch timings, not click-correlated or client/network timings.

## S12.35.196 — Feedback message retry/idempotency evidence

- S12.35.205 supersedes the original scope: the same transient classification failure and retry now run through the actual registered non-command `MessageHandler`, decorated `handle_message` body, and source idempotency decorator. First failure leaves pending and dedupe eligibility intact; retry creates exactly one fixture ticket and one reply/notification, then clears pending. All unrelated pending handlers are false-returning fakes and context `user_data` is empty.
- Focused direct assertion printed `registered handle_message retry assertion: OK`; changed test modules `py_compile` and `git diff --check` exited 0. The feedback module is included in the safe-navigation pytest CI step; local pytest is unavailable, so no local pytest/CI pass is claimed. No real Telegram message or production side effect.

## S12.35.197 — Feedback category emitted-callback matrix

- The actual category keyboard emitted eight distinct whitelisted `feedback|cat|...` values. All eight matched the registered route pattern and reached the extracted production callback handler; each ACKed once, set only the corresponding fixture category, rendered its prompt, and emitted Back=`feedback|start` plus Home=`menu|main`.
- The focused direct assertion passed, and an in-memory wrong-callback mutation was rejected. The module is already wired into safe-navigation CI; local pytest is unavailable, so no pytest/CI pass is claimed. No real message, production data, or Telegram operation.

## S12.35.198 — Video entry latency recheck

- Existing phase telemetry already separates `menu|main_video`: handler 291.160ms, render 91.453ms, ACK 180.930ms, and matching dispatch 373.478ms in the 2026-10-09 sample. The seven-day sparse callback census had no dispatch above 1,000ms. No new route-key branch was retained because it would duplicate this evidence.
- This does not measure client/network end-to-end delay or prove all buttons smooth. The current Bảng giá `<1s` report is a single manual observation without correlated server timing; A7 remains partial.

## S12.35.192 — Document split Back and staged-state recheck

- The actual emitted page-prompt action, prompt Back, confirmation Add-more, parent Back, expiry, and actor/other-user state cases in `tests/test_doc_split_back_emitted_callback.py` were exercised against the registered `^docflow\\|` route. All eight test functions passed under a fixture-only immediate coroutine driver that refuses yielded I/O.
- The file is included in CI's `pytest --noconftest` navigation step. The local bundled Python does not contain pytest; the direct assertion run is not a pytest or CI result.
- No PDF/Word processing, file upload/save/send, production data, provider, wallet, AutoPost, protected engine, or Telegram action was invoked. Route/action coverage remains partial.

## S12.35.193 — SubDub/Voice child Back navigation recheck

- `tests.test_subdub_voice_child_back.SubDubVoiceChildBackTests` passed all 5 tests in 4.353s — OK through the exact source registration and fixture-only `USER_PENDING` state. The immediate coroutine driver rejects any yielded I/O.
- Verified Audio Mix layer Back, expired-child recovery, emitted voice-child Back to its Voice parent across modes/visibility, saved-voice pagination Back, and main Voice Back to Language preserving source/origin.
- No voice selection, media processing, job, provider, production state, wallet, or Telegram action was invoked. This is UI-navigation evidence only; engine behavior remains protected and outside this spec.

## S12.35.194 — Voice TTS settings prompt Back recheck

- 19 fixture cases passed: speed/volume prompt Back across three source kinds and two product contexts, parent Back for all six combinations, plus a stale Back preserving an unrelated pending action. The exact registered Music Quick handler and in-memory result/pending state were exercised; an immediate coroutine driver aborts on yielded I/O.
- Test `pytest.mark.parametrize` decorators were expanded by a one-shot in-memory shim because local Python lacks pytest. This is direct assertion evidence, not pytest/CI evidence. Generation, price-summary, and provider seams were explicitly forbidden.
- No voice output or production side effect occurred. This verifies only UI navigation/pending behavior; stable Voice/Music engines are not claimed as tested.

## S12.35.195 — Admin Broadcast Lite Back and read-only navigation

- The actual registered Broadcast Lite handler passed 4 focused tests in 0.801s: emitted History/Schedule/Limits navigation, their Back routes, nested Limits → Schedule Back, and Back/Menu pending-owner release with draft-content preservation.
- The first invocation failed before product assertions because Windows sandbox AppData temp denied SQLite open/cleanup; the same suite passed after redirecting only its temporary database directory into the worktree. That exact workspace temp directory was removed.
- No broadcast message, Telegram send, production DB, AutoPost, provider, wallet or engine action was run. This is fixture route/state evidence only.

## S12.35.191 — Package detail Back retains Account and Total-price ancestry

- RED: three emitted routes (Account Pricing main, Account Total, and public Catalog Total) carried their allowlisted origin through Package Home and Image group, but package detail Back emitted the unscoped `pkgcombo:group:image`. The failure was in the detail keyboard's origin allowlist, not the entry callback or registered handler.
- Fix: add those three existing navigation tokens to the detail Back preservation set. No package purchase action or pricing/checkout/engine logic changed.
- GREEN: the focused emitted-route test passed in `6.304s` across the three origin scenarios; the full package navigation module passed `15 tests in 52.225s — OK`. The Windows test driver rejects yielded I/O; payment/provider/Telegram boundaries are inert.
- Limits: fixture-only callback routing; no package purchase, payment, provider, wallet, production data, engine, AutoPost, merge, deploy or restart. Live/client latency remains separately unverified.

## Current continuation evidence — 2026-10-09

### S12.35.181 — Expired Internal Archive department Search

- The actual emitted `archive|search_dept|customers` callback was dispatched after fixture TTL expiry through the registered Archive handler. It ACKed once, returned the exact Archive-root controls without opening a prompt or issuing a search/lookup, cleared only the expired actor, and preserved another user's fresh pending state.
- Focused test: `1 test in 0.040s — OK`; full registered Archive module: `20 tests in 0.806s — OK`. On Windows, the ordinary Proactor invocation stalled before handler execution in `_fallback_socketpair`; the counted fixture run used an in-memory source index and an immediate coroutine driver that rejects yielded I/O.
- No production document/DB, search, provider, wallet, engine, AutoPost, Telegram send, merge, deploy, or restart.

### S12.35.182 — Public Audio Studio landing Back/Home

- The actual public-root Audio Studio callback `music_quick|showroom|root` reached the registered `handle_music_quick_callback` and rendered the Studio Audio landing keyboard. Its emitted Back and Home controls both reached the registered Menu handler and restored the exact main-menu callback list.
- Verification: the corrected combined focused rerun passed `2 tests in 2.790s — OK` with a synchronous coroutine driver that rejects any yielded I/O. The earlier ordinary Windows Proactor invocation stalled in `_fallback_socketpair` before handler execution and is not counted as a pass.
- Navigation-only evidence. No Voice/Music child flow, generation, provider, production data, wallet, Telegram send, AutoPost, merge, deploy, or restart. Live Telegram visual/latency and broader A3/A5 coverage remain open.

### S12.35.183 — Public Music Hub Back/Home

- The actual Audio Studio keyboard's emitted `music_quick|showroom|music_hub` reached the registered Music callback and rendered the Music Hub. Its emitted `music_quick|showroom|root` Back returned the Audio Studio controls; emitted `menu|main` Home reached the registered Menu handler and restored the public Main menu. Each callback ACKed once.
- Verification: the corrected combined focused rerun passed `2 tests in 2.790s — OK` with a synchronous coroutine driver that rejects any yielded I/O. No Music/Voice action child or generation boundary was entered.
- No product source, provider, production data, wallet, Telegram send, AutoPost, merge, deploy, or restart. This closes only the named navigation path; whole-handler and client/runtime visual/latency review remain partial.

### S12.35.184 — Public Pricing Voice Back returns through Catalog

- The public Pricing hub's emitted Catalog control was dispatched through the registered Pricing handler, followed by the emitted Voice pricing control. The Voice screen's emitted Back returned to the exact Catalog callback list; Catalog Back returned to the Pricing hub; the hub's emitted Main Home reached the registered Menu handler and restored Main.
- Focused test `test_public_voice_pricing_back_restores_catalog_then_pricing_hub` passed in `2.582s` using a corrected synchronous fixture driver that rejects any yielded I/O. An injected wrong-Back mutation (`pricing|main` instead of `pricing|catalog`) failed at the expected assertion. The complete Account Pricing regression then ran `17 tests in 89.763s — OK`; six callbacks in this route ACKed exactly once and Voice text came from an inert fixture.
- Navigation-only evidence. No Voice action/generation, provider, payment/top-up, wallet, production data, Telegram send, AutoPost, engine, merge, deploy, or restart. This does not measure Telegram-client latency or close A3/A5/A6/A7 globally.

### S12.35.185 — Public Pricing Guide Back returns to Pricing

- The emitted Catalog `pricing|guide` control reached the registered Pricing handler and rendered fixture guide text. Its emitted Back returned to the Pricing hub; the hub's emitted `menu|main` reached the registered Menu handler and rendered Main. The generated-pricing and generated-guide download controls were not dispatched.
- Focused test `test_public_pricing_guide_back_returns_to_pricing_hub` passed in `2.891s` with a synchronous fixture driver that rejects yielded I/O; the full Account Pricing module ran `18 tests in 121.573s — OK`. Injecting the wrong Back (`menu|main_guide`) failed at the intended `pricing|main` assertion. The first fixture attempt raised `NameError` for an unprovided `effective_public_base_url` seam; the offline fixture was corrected with an empty URL.
- No document generation/send, provider, payment, wallet, production data, Telegram send, AutoPost, product engine, merge, deploy, or restart. This is navigation evidence, not live/client latency QA.

## S12.35.172 — Internal Archive type-picker Back returns to its department

- The actual Archive root keyboard emitted the customer-department callback; its dashboard emitted `archive|types`; the actual type picker rendered the “Chọn loại hồ sơ — Hồ sơ khách hàng” prompt and emitted `archive|back_department` plus the fixture customer-profile type option.
- Dispatching that emitted Back through the exact registered Archive callback ACKed once, restored the same department dashboard callback list, and retained `step=department_dashboard` / `department=customers`. Focused unittest: `1 test in 2.535s — OK`.
- No type selection, lookup/recent query, production record/file/database access, Telegram send, provider, wallet, product engine, AutoPost, merge, deploy, or restart. This is fixture-only route evidence, not live client visual/latency validation.

## S12.35.173 — Internal Archive type selection Back returns to the type picker

- The actual department dashboard emitted `archive|types`; the type picker emitted `archive|type|customer_profile`. Dispatching the latter through the registered Archive handler rendered the upload prompt and set fixture pending state to `awaiting_file` with department `customers` and type `customer_profile`.
- The upload prompt's emitted `archive|types` Back ACKed once, restored the exact type-picker callback list and `choosing_type` state, and retained the selected draft type. Focused unittest: `1 test in 1.882s — OK`.
- No file upload/save, production Archive/DB record, Telegram send, provider, wallet, product engine, AutoPost, merge, deploy, or restart. Fixture-only UI-route evidence; no live client visual/latency claim.

## S12.35.174 — Internal Archive quick-save entry Back returns to its department

- The actual customers department keyboard emitted “📎 Lưu file vào nhóm này”; dispatching it through the registered Archive handler rendered the quick-save prompt, emitted `archive|back_department`, and set fixture state to `awaiting_file` / `customers` / `general`.
- Dispatching the prompt's emitted Back ACKed once and restored the exact original department callback list and `department_dashboard` state. Focused unittest: `1 test in 3.024s — OK`.
- No file upload/save, production Archive/DB record, Telegram send, provider, wallet, product engine, AutoPost, merge, deploy, or restart. Fixture-only route evidence; no live client visual/latency claim.

## S12.35.175 — Internal Archive department Search Back returns to its department

- The actual Archive department keyboard emitted “🔍 Tìm trong nhóm”; dispatching it through the registered handler rendered the department-specific prompt and emitted `archive|back_department|customers`.
- Dispatching that emitted Back ACKed once and restored the exact customers department callback list and `department_dashboard` state. Focused unittest: `1 test in 2.336s — OK`.
- Combined regression: the complete `tests.test_internal_archive_search_back_origin` module ran `15 tests in 102.177s — OK`, including S12.35.172–.175.
- No search term was entered, no document query or production Archive/database access occurred, and no Telegram send, provider, wallet, engine, AutoPost, merge, deploy, or restart was used. Fixture-only navigation evidence.

## S12.35.176 — Internal Archive department Back returns to Archive root

- The actual customer department keyboard emitted `archive|root`. Dispatch through the registered Archive handler ACKed once, rendered the Archive root and exact root callback list, and cleared only the fixture user's department pending state.
- Focused test was corrected after the first assertion expected `{}`; the actual getter returns `None` for cleared state. Rerun: `1 test in 21.640s — OK`. No production code change.
- Latest combined regression: the complete `tests.test_internal_archive_search_back_origin` module ran `16 tests in 45.381s — OK`, including S12.35.172–.177.
- No production Archive/DB/file action, Telegram send, provider, wallet, product engine, AutoPost, merge, deploy, or restart. Fixture-only navigation/state evidence.

## S12.35.177 — Internal Archive root Search is dispatched from its emitted button

- The root Search regression previously invoked `archive|search` directly. It now selects the actual visible “🔍 Tìm hồ sơ” button from `internal_archive_menu_keyboard`, verifies its callback matches the registered Archive route, and dispatches that emitted value. The prompt's emitted `archive|root` Back then restores the exact root callback list.
- Focused registered-handler unittest passed: `1 test in 2.197s — OK`; one ACK was observed for Search and Back. This closes a route-evidence gap only; no product mismatch or code change was indicated.
- The complete Archive route module then passed `16 tests in 45.381s — OK`, including the emitted Search entry and all S12.35.172–.177 cases.
- No search term/query, production DB, Telegram send, provider, wallet, engine, AutoPost, merge, deploy, or restart.

### Latest continuation — S12.35.171 Internal Archive Help → Back

- The actual Archive root → department → “Hướng dẫn lưu” controls and emitted Back were dispatched through the registered Archive handler. The help page used the real text helper; Back restored the exact customers-department keyboard and pending state. Focused unittest: `1 test in 1.964s — OK`.
- No Archive lookup/recent/send fake was called; no production record/file, Telegram, provider, wallet, protected engine, AutoPost, merge, deploy or restart. Other Archive action values and client/runtime latency remain partial.

## S12.35.134 — Expired Document Back route evidence

- RED reproduced on the exact registered `^docflow\\|` handler: expired `save_document` Back from the after-file menu routed to PDF Documents; the quota-error Back emitter also carried only the generic `docflow|back` origin.
- Start, after-file, confirmation, and quota-error Back controls now retain the allowlisted `main_memory`/`main_docs` parent. The registered handler trusts live pending state, then uses the encoded parent after TTL cleanup; old/invalid stale values keep the safe Documents fallback.
- Five source-extracted tests pass, including all three ordinary keyboard builders, the quota-only early-stop renderer with fake metadata, the real TTL getter, Notes/Docs destination, and split-page selection-preserving Back. No file contents, storage, DB, wallet, provider, product engine, AutoPost, or real Telegram action.
- Status remains PARTIAL for document processing/action terminals and Telegram-client timing; this is a local UX route fix pending the consolidated CI batch.

## S12.35.144 — Pricing catalog source reconciliation

All 16 Vietnamese controls emitted by `pricing_catalog_keyboard("vi")` were matched to the exact registered `^pricing\\|`, `^pkgcombo:`, or `^menu\\|` handler and corresponding branch: summary, voice, music, video, subtitle/dubbing, image, documents, free, member/promotions, guide, two generated-document actions, storage, package home, Pricing Back, and Main menu. No source mismatch was found. The Account Pricing/Back suite passed 13 tests in 89.627s, including total/catalog Back and membership ancestry. A separate static catalog assertion invocation was interrupted before assertions during CPU-bound full-bot import; it is not counted as passed. The two document-send actions were source-inspected only. This establishes source mapping, not dispatch of all 16 routes, generated-document delivery, pricing transactions, or Telegram-client rendering/latency.

## S12.35.145 — Pricing hub callback evidence

`pricing_main_keyboard` has four source branches. Vietnamese domestic offers emit `pricing|promotions`; non-domestic Vietnamese hides the offer and emits Top-up instead; English/Chinese use Pricing, Top-up, package home and Main; other-locale fallback also emits Guide, generated-document controls and Support. The Pricing renderer wraps Top-up with `pricing_main` context, and registered Pricing/Menu/Package handlers contain matching destinations. The selected origin-aware Top-up/Offers regressions are among the 13 passing `test_profile_pricing_back_origin` tests. Source-only review did not query real market state or dispatch all variants; no document was sent and no transaction, provider, wallet, customer data, engine, AutoPost, deploy, or restart path ran. No mismatch was found; locale rendering remains PARTIAL.

## S12.35.124 — Internal Archive change-group Back origin

- RED: the source-extracted production Archive handler opened the department picker from `archive|change_dept` but reused the root keyboard, exposing Search and Back-to-Notes (`menu|main_memory`) instead of Back-to-preview (`archive|preview`). The Search prompt's Back routes to Archive root, which clears the pending preview.
- GREEN: only the nested picker now omits Search and opts into preview-origin Back. Focused tests dispatch both the emitted Back and a newly selected department through the extracted handler; they verify the pending file is retained and the expected preview returns. Registered Menu callback tests dispatch Archive→Notes and the actual preview Home control, verifying only the current actor's pending draft clears and the expected destination renders. Final CI-style runs: Archive picker module 5 tests in 0.764s — OK; Menu routes 2 tests in 0.679s — OK. An initial unittest-discovery invocation ran 0 tests; the test harness was corrected to `unittest.TestCase`, so CI executes the assertions.
- Default Archive root Back/Search stay unchanged; no Search query, department selection, Save or file-send terminal was executed. No production Archive data/file, provider, wallet, job, protected engine, AutoPost, or Telegram side effect.

## S12.35.123 — Memory delete-confirmation replay guard

- Source RED: after Cancel, replaying the old emitted `memory|delete_yes` callback still reached the archive update. The original fixture failure showed `active != archived`; no setup failure occurred.
- Source GREEN: confirmation callbacks now carry a per-user pending token bound to the note and existing TTL. Invalid, missing, stale and expired confirmations fail closed; the valid one-time token is consumed before the original archive update.
- Evidence: the final registered-handler regression cancels, reopens confirmation for the same note, rejects a tokenless legacy callback and the stale token without DB/event calls, then accepts only the current token against a fake DB. Focused: 1 test/0.859s — OK; root/menu module: 39 tests/21.574s — OK; Memory pending-reset and empty-delete modules: 1 test/2.663s and 1 test/0.307s — OK.
- Limits: no production Memory record, DB, real Telegram, provider, wallet, job or engine was accessed. Full `bot.py` local compile remains NOT_VERIFIED due multi-minute no-output resource use; CI compile remains required. No workflow diff or delivery action.

## S12.35.103 — Free Tools Notes/Docs origin-aware Back

- The emitted Free Tools Notes/Docs button now carries its source origin into the registered `menu|` handler. The emitted Memory prompt Back returns to the Memory root, whose Back then returns to Free Tools; ordinary Main-origin Memory retains `menu|main`.
- Fresh `/start` and `/memory` command entry and Free Tools exit clear the temporary navigation origin. Focused registered-handler/command fixtures passed 2 tests; the complete root/menu module passed 30 tests.
- Only UI navigation and in-memory `context.user_data` were exercised. No note operation, document processing, production data, provider, wallet, job, AutoPost, product engine, or real Telegram delivery was invoked. This does not establish Telegram-client visuals/latency or whole-bot completion.

## S12.35.153 — Internal Archive emitted Recent button returns to its department

- `test_emitted_recent_button_renders_fixture_and_back_returns_to_department` follows the department dashboard's emitted `archive|recent` control through the registered handler, checks one ACK and fixture-only lookup/rendering, then dispatches the emitted `archive|back_department` and verifies the same department dashboard and pending origin are restored.
- Combined Archive Search/Recent/Detail/File/Back and adjacent Save tests: 9 passed in 11.715s; 2 standalone Preview ACK/navigation checks passed. Changed test modules compiled and `git diff --check` exited `0`.
- No production mismatch or code fix was indicated. No production document/data, real Telegram send, provider, wallet, engine, AutoPost, deploy, or restart. Live client timing remains unmeasured.

## S12.35.188 — Package Home retains its Pricing parent

- RED used the actual emitted Package/Combo controls from Account Pricing main and public Catalog Total. Both emitted `pkgcombo:home` without origin, so Back could not restore the exact parent.
- The Pricing UI wrapper now scopes those two package-home entry paths with allowlisted origin tokens; the registered Package handler maps Back back to Account Pricing main or Total price. Existing unscoped callbacks and package actions are unchanged.
- `tests.test_pkgcombo_navigation_registered_callback`: 14 tests in 39.241s — OK, including the Account → Catalog → Total → Packages → Total → Catalog → Account round-trip. After updating only the two stale expected callback values, the full Pricing module passed 28 tests in 118.453s — OK. On Windows, the test fixture used an immediate coroutine driver that fails on any yielded I/O.
- Fixture-only route dispatch. No purchase/detail, payment, provider, wallet, production data, Telegram, AutoPost, product engine, merge, deploy or restart. Local full-source compilation and CI remain outstanding.

## S12.35.189 — Ticket category prompt Back recheck

- `test_customer_ticket_category_prompt_back_restores_category_menu` passed in `0.492s`. The fixture route checked the emitted category, expected actor pending state, emitted `ticket|start` Back, one ACK per step, actor-only cleanup, and exact category-list restoration.
- The first test-selection command named the wrong unittest class and failed discovery; the corrected test selection passed. No product behavior mismatch was reproduced.
- Fixture only: no ticket delivery, production data, provider, wallet, AutoPost, engine, merge, deploy or restart. This is not live customer-message or Ticket-action coverage.

## A7 — Callback timing instrumentation source/fixture recheck

- Current source wraps every registered inline callback handler and records anonymous bounded route prefix plus guard, handler and shared render-helper time. `tests.test_callback_dispatch_timing` passed `5 tests in 8.245s — OK`.
- The observer cannot measure Telegram transport/client rendering after bot dispatch or ReplyKeyboard/message handlers. On 2026-10-10 the Owner again reported Bảng giá `<1s`; a strict-host aggregate over the preceding 15 minutes at about 02:01 +07 returned no callback timing event. Account → Back remains reported at 2–3s without a correlated server sample. Root cause and all-button smoothness remain unresolved; no speculative code change was made.

### A7 latest Pricing tap observation — 2026-10-10 approximately 03:21 +07

The Owner reports the Bảng giá screen appeared immediately (`<1s`). The available seven-day aggregate has three Pricing events (average `377.814 ms`, maximum `741.848 ms`), but cannot correlate one event to this tap. This supports no Pricing latency patch; it does not prove other routes or identify the source of the separate Account → Back delay. ReplyKeyboard and Telegram/client rendering remain unmeasured.

### S12.35.200 — Public Support root → Home round-trip

`test_customer_root_support_home_returns_to_main_menu` dispatched the emitted public-root Support control and its emitted Home control through the registered Menu handler. It rendered Support, restored Main, and acknowledged each callback once (`Ran 1 test in 0.287s — OK`) with an immediate fixture driver that rejects I/O. The default Windows Proactor runner stalled before completion; the targeted fixture rerun passed. No production change or Telegram send.

### S12.35.201 — Document Split confirmation “Add more”

The emitted `docflow|send_more` control reached the registered Document handler and returned to the upload prompt. The focused fixture assertion passed (`focused emitted document Add-more route: OK`), preserving the current user's staged files/options and another user's pending state, with one ACK. No actual file was uploaded or processed.

### S12.35.202 — Package group Back ancestry (navigation only)

The public Pricing Catalog and Account → Pricing → Catalog → Packages routes were dispatched through the registered Pricing handler. The emitted Image, Video, Music, Voice and SubDub group controls each opened only the package list screen; each Back returned to the exact origin-bearing Packages controls, and Packages Back restored the originating Catalog. In the Account-origin route, the final Catalog Back restored the Pricing hub. Both focused source-extracted matrices passed for all five groups. No package detail, purchase, wallet, provider or protected engine was entered.

## S12.35.190 — Exact Home/Back timing classification

- RED: exact `menu|main` was emitted by the registered menu fixture but was logged as `route_key=unclassified`, so it could not be isolated from unrelated `menu` controls.
- GREEN: the existing observer now classifies only exact `menu|main` as fixed `main_home`; exact Account entry remains `account_root`, and a payload with an added private/dynamic suffix remains `unclassified`. Full timing module passed `5 tests in 6.990s — OK`, including no-payload/no-user-ID assertions.
- The actual Account keyboard's emitted `menu|main` Home/Back was separately dispatched through the registered Menu handler and restored Main (`1 test in 0.722s — OK`). This validates route/destination only.
- Logging-only change. It does not affect the Menu handler, speed, or Telegram rendering; one correlated live Account Back event is still needed for root-cause attribution.

## A7 Account → Back post-tap recheck — 2026-10-09 12:42 +07

- The Owner reported a fresh Account → Back tap. Strict-host aggregate-only query of the preceding 15 minutes returned `callback_events=0` and `transport_telegram_warning_matches=0` for the checked timeout/network/Telegram error signatures; no server event is available to match to that tap.
- VPS readback at 12:45 +07 found `toanaas-bot.service` active/running, `NRestarts=0`, runtime HEAD `62566249d4d54f6047ab33ddffd1bf94c57d0e41`, `/health` `status=ok`, and the timing instrumentation marker present. No route-latency or cause inference is possible from an empty window. It does not prove the tap failed to reach Telegram or assign delay to bot, Telegram, network, or client rendering. The seven-day live sample remains menu-only; other callback families and ReplyKeyboard/message handlers are unmeasured. No raw logs/IDs/payloads or side effects.

## S12.35.209 — ReplyKeyboard Home routing and latency boundary

- `main_reply_keyboard()` emits `🏠 TOAN AAS MENU`. The actual registered non-command text route sends both Home labels to `cmd_start` before AutoPost's pending-content branch; the message idempotency wrapper uses an in-memory per-message lock/dedupe set. No route mismatch was found by source inspection.
- The existing callback timing observer wraps callback-query handlers only, not `MessageHandler`/`handle_message`, so it cannot measure ReplyKeyboard Home or the subsequent `/start` render.
- The original fixture runner stalled at `asyncio.run` on Windows. Its Home and ordinary-text fixture coroutines are immediate and must not yield I/O; replacing only this test helper with an immediate no-I/O driver made the assertions complete.
- Direct local assertion output: `ReplyKeyboard Home priority: 2 labels OK; ordinary AutoPost input preserved: OK`. Bundled Python test-file `py_compile` exited `0`; `python -m pytest ...` could not start because pytest is not installed in that runtime. The test was added to CI's safe-navigation pytest list; GitHub CI has not run for this change. This is not a pytest/CI pass.
- No production handler or AutoPost logic changed. Server timing for this MessageHandler path and live client rendering remain unmeasured; A7 remains partial.
- A read-only 24-hour production timing aggregate could not be retrieved: workspace SSH could not resolve the host, and the authenticated retry was rejected pending more explicit authorization for remote journal access. No production logs were read or returned.

## A7 — Approved 24-hour live callback timing aggregate — 2026-10-10 12:17:44 +07

- The Owner approved one SSH read-only query filtered to `callback_dispatch_timing`. The command returned aggregates only: count, average, maximum, and count over 1,000 ms by route prefix, route key, and handler.
- `menu` / `unclassified` / `handle_menu_callback`: 1 event, 478.802 ms average and maximum, 0 over 1s. `pricing` / `unclassified` / `handle_pricing_callback`: 3 events, 377.814 ms average, 741.848 ms maximum, 0 over 1s. No other prefix appeared in the 24-hour window.
- This did not reproduce a >1s callback handler dispatch. The menu event cannot be assigned to Account → Back because its route key is unclassified; the Pricing events are not click-correlated to the latest Bảng giá observation. Handler duration includes awaited work but does not isolate internal/API phases or measure client rendering/ingress network; ReplyKeyboard/MessageHandler remains outside the observer. No raw journal lines, IDs, or payloads were returned. No production source/service/data changed; no patch is justified. A7 remains partial.

## S12.35.102 — Free Tools suggestion-menu callback evidence

- The actual Free Tools root emits `freehub|meta`, `freehub|caption`, and `freehub|ideas`. Each was dispatched through the exact registered handler; each produced the expected local suggestion task, and its emitted Back returned to the root while preserving unrelated pending state.
- Initial fixture execution stopped on missing `normalize_free_hub_task_type`; the fixture was given an identity stub for these task names. Retest: focused method 1 test in 0.327s — OK; root/menu module 28 tests in 16.090s — OK. This was a test-fixture setup error, not a product failure.
- No suggestion selected or custom text entered; no provider, generation, network, DB, wallet, job, AutoPost, engine, or real Telegram action. Route evidence only; no live client QA claim.

## S12.35.119 — Current callback-evidence reconciliation (2026-10-08)

- The baseline inventory at the top of this file remains a historical registration snapshot. Its old `handle_language_callback`/`handle_menu_callback` candidate status is superseded for the explicitly tested public-root slices: S12.35.117 source-compares public Main label keys, callbacks, handler registrations, landing branches and conditional Admin entry with no mismatch; S12.35.118 dispatches all 17 current public Language-picker choices through the exact registered handler and verifies fixture-only update + Main render in the selected locale (focused 1 test/0.976s; root/menu module 38 tests/57.760s).
- Fresh runtime read at 2026-10-08 22:52 +07: GitHub main `f232deafaef5461e1de0494e750db16e26612b78`, VPS bot `9835b432464c4ccd94fe43690d41b6500c75eb7b`; VPS bot active/running, `NRestarts=0`, internal health `ok`. The one-commit main-only delta remains protected Product Video PR #1412; this UX audit did not deploy or restart it.
- Remaining handler rows marked PARTIAL/NOT PROVEN stay so where they refer to action-capable, payment/provider, AutoPost, protected product, untested dynamic, or client/runtime behavior. These two specs do not close A3/A5/A6/A7 as a whole.

## S12.35.101 — Free Tools weather callback evidence

- The Utilities keyboard's emitted `freehub|util_weather` and `freehub|util_weather_input` controls were dispatched through the exact registered handler. The deterministic weather stub was called for Hà Nội, Đà Nẵng, and Hồ Chí Minh only for the overview; opening the input prompt made no additional call.
- The prompt's emitted Back returned to the same Utilities callback set and cleared only the current fixture user's pending state. Focused test: 1 test in 1.005s — OK; root/menu module: 28 tests in 28.245s — OK.
- No live weather API, network, production source, DB, provider, wallet, job, AutoPost, engine, or Telegram action. This closes route evidence only; it does not claim live client visual/latency validation or a production bug fix.

## A7 / UI release-gate recheck — 2026-10-11 05:53 +07

- The previously approved strict-host `account_root` aggregate is already recorded above: at 05:31 +07 it had 0 events and valid journal/aggregator status. `account_root` is Account entry, not Account → Back; no duplicate query was run. The reported Back is `menu|main` / `main_home`; the separate approved 24-hour phase sample for `menu|main`/`menu|main_video` was also empty. This does not identify the 2–3s delay source.
- GitHub UI showed PR #1409 merged. Deploy workflow #492 succeeded at commit `381d335961bea01db60cda99f0dfe98e2b2d1760`; read-only SSH confirmed the VPS bot repo is on that exact SHA. PR commits #1410 (`87bf320`), #1411 (`ea516e3`), and #1415 (`4dc0c31`) are ancestors of the runtime. `toanaas-bot`, `toanaas-web`, and `nginx` were active/running; all reported `NRestarts=0`.
- Current GitHub `main` is `5c38bd31c20f26f815e2f05b6419f4dd64afbba9`. Runtime is its ancestor. The exact runtime-to-main diff is 7 files, 320 insertions / 19 deletions, all in Product Video provider/router/worker code and related tests (#1420). Because this task is UX/callback-only and those protected changes are not authorized in this release, no deploy was started.
- Required local `python -m py_compile bot.py` on the uncommitted audit worktree produced no result after 90 seconds and was interrupted; mark `NOT_VERIFIED`, not a compile failure. The worktree and pre-existing VPS untracked data/artifacts were left unchanged. The live timing cause and all-button client smoothness remain open.
- `git diff --check` exited 0 (with existing LF→CRLF warnings). The state YAML parser check is `NOT_VERIFIED`: bundled Python has no PyYAML and a temporary PyYAML install was denied by the sandbox; no project dependency was changed.

## S12.35.291 — Admin tax report selector Back origin — 2026-10-11

- RED: the `finance_tax_vat` page's actual `finance_tax_keyboard()` emitted the VAT report control. Its registered `menu|` handler rendered the report selector, whose emitted Back was `menu|finance`; dispatching that through the same registered handler returned Finance root instead of the immediate `finance_tax_vat` parent. After correcting a missing inert fixture name, the test failed on this exact destination mismatch (one assertion failure, no fixture errors).
- GREEN: `finance_tax_report_keyboard()` now emits Back as “Thuế / VAT / TNDN” → `menu|finance_tax_vat`. `tests.test_admin_overview_callback` passed 2 tests in 1.232s; adjacent `tests.test_admin_report_source_availability` passed 4 tests in 12.791s. The new case uses real source keyboard builders, `ADMIN_MENU_PAGE_HANDLERS`, `localized_menu_content`, and the exact registered `handle_menu_callback`; it asserts one ACK per route and public denial before report helper.
- `tests/test_admin_overview_callback.py` `py_compile` exited 0; `git diff --check` exited 0 with only pre-existing LF→CRLF warnings in unrelated tests. The module is already listed in `.github/workflows/ci-main.yml`; no workflow change.
- Scope: one Back label/callback row plus inert source-extracted test. No production report/database read, export, payment/wallet mutation, provider, job, Telegram send, AutoPost, or protected engine. Full bot compile, branch CI, batch release, and live UI performance remain pending.

## S12.35.292 — Admin Finance Audit Back origin — 2026-10-11

- Current-main source at `5c38bd31c20f26f815e2f05b6419f4dd64afbba9` emits `menu|finance_menu_audit` from the Tax/VAT/CIT keyboard. `ADMIN_MENU_PAGE_HANDLERS` rendered the Audit screen with generic Finance Back (`menu|finance`), so the actual emitted route returned one level too far. The standalone `/finance_menu_audit` command separately uses the generic Finance keyboard and remains unchanged.
- RED/GREEN: the emitted button and its emitted Back were dispatched through the exact registered `handle_menu_callback`. Baseline failed with actual `menu|finance` vs expected `menu|finance_tax_vat`; after changing only the inline menu mapping to `finance_tax_child_keyboard()`, the full `tests.test_admin_overview_callback` module passed 3 tests in 0.577s, including existing Overview and tax-report Back cases. One ACK per callback was asserted.
- Changed test py_compile exited 0; `git diff --check` exited 0 with existing line-ending warnings in unrelated files. Test module is already included in CI.
- No production report/audit query, database/config write, provider, wallet, job, real Telegram, AutoPost, or protected engine. Main is not changed by this local patch; one batch CI/release and separate delivery approval remain pending. Account Back latency remains uncorrelated to server timing.

## S12.35.293 — Admin tax read-only child Back matrix — 2026-10-11

- The actual `finance_tax_keyboard()` controls for Tax settings, VAT/CIT rate help, B2C/B2B policy, 100k scenario, Provider cost/FCT status, and Finance Audit were dispatched through the exact registered `handle_menu_callback`. All seven rendered the expected inert child screen; all seven emitted Back=`menu|finance_tax_vat`; dispatching each Back restored the tax module. One ACK was asserted for each parent, child, and Back callback.
- GREEN: `python.exe -S -m unittest -v tests.test_admin_overview_callback` returned `Ran 4 tests in 0.836s — OK`, including the new seven-child matrix and prior Admin Overview, Finance Audit, and tax-report navigation cases. Changed-test `py_compile` exited 0; `git diff --check` exited 0 with pre-existing LF→CRLF notices in unrelated tests.
- No additional route defect was reproduced; no `bot.py` product change was needed. Fixture only: no tax DB/config/report/export/provider/wallet operations, production data, job, AutoPost, protected engine, or real Telegram action. Live UI smoothness, Account → Back's reported 2–3 seconds, full-bot compilation, batch CI, and final delivery remain open.

## S12.35.294 — Admin CIT report shortcut Back origin — 2026-10-11

- The actual tax keyboard's emitted `menu|finance_cit_report` reached the registered Menu callback and shared report display fixture. Its emitted Back returned to `menu|finance_tax_vat`; parent, report and Back each ACK once.
- Focused case: `Ran 1 test in 0.258s — OK`. Full `python.exe -S -m unittest -v tests.test_admin_overview_callback`: `Ran 5 tests in 1.402s — OK`. Changed-test py_compile and git diff --check exited 0 (existing line-ending notices only).
- No product mismatch reproduced or bot.py change. Report data/calculations/exports, config/wallet/provider operations and real Telegram were not invoked. Whole-bot compilation, batch CI/delivery and Account Back latency remain open.

## S12.35.295/.296 — Batch verification and Ticket ID guard — 2026-10-11

- Initial run: 577 collected; `77 failed, 507 passed, 785 subtests passed in 1438.16s`. JUnit classified 66 Windows TEMP/Bash environment failure entries and the remaining UI fixture/contract cases; this initial run is not PASS.
- Broadcast TEMP fix: 4 tests/1.066s OK. Feedback missing presentation stub: 12 passed/7.13s. Package compact-token expectations retained complete Back assertions: two affected matrix methods passed/41.145s; catalog case passed. Seven previous ordinary UI failures reran GREEN (`7 passed, 79 deselected, 3 subtests passed in 62.78s`). Ubuntu workflow hygiene remains a required CI gate.
- New actual product defect: `ticket|pv` raised IndexError on candidate while main answered safely; superscript detail IDs raised ValueError and lost pending on both sources. Only the customer/admin detail ID predicates were changed to bounded ASCII decimal validation before lookup/cleanup.
- New matrix RED: 5 failures/4 errors. GREEN: 16 malformed-ID combinations and foreign recovery passed 2 tests/15.784s; full ancestry/reply-origin modules passed 41 tests/206.240s. Actor/foreign pending, ownership and semantic Back checks remain asserted. Full candidate compile exited 0 at bot blob `93ed446354e11947f52bee923a9f5a846c6ad6f1`.
- Text declaration comparator: 43 UI blocks changed, 2 UI helpers added, 0 removed; 5,347 protected-pattern blocks unchanged and no protected file changes. This is source evidence, not live product-output/client coverage. No production DB, wallet, paid provider, Telegram action, merge/deploy/restart occurred during these checks.

## S12.35.305 — Admin Ticket status callback read scheduling — 2026-10-11

- All three status buttons emitted by the actual Admin Ticket detail keyboard
  (`resolved`, `refund_pending`, `waiting_provider`) dispatch through the exact
  registered `ticket|` handler. Before the patch, both `get_user_language` and
  `get_support_ticket` performed SQLite SELECTs synchronously on the event loop;
  five new focused scheduling assertions reproduced the missing thread seam.
- The narrow patch adds only `st` to the existing Admin Ticket read-offload set
  and moves its ticket SELECT through `asyncio.to_thread`. A combined no-I/O
  pytest run returned 43 passed in 10.41s, covering the emitted status matrix,
  one ACK, public denial before ticket lookup, stale-ticket alert/no update,
  status update order, one refund warning on a transition, and list/Main controls.
- `tests/test_admin_stale_ticket_status_callback_single_ack.py` is now selected
  in the existing Small Navigation CI command; no deploy step changed.
- All three changed test modules passed `py_compile`; audit-state and workflow
  YAML parsed; `git diff --check` exited 0. Final combined `bot.py` compile and
  consolidated CI have not run yet.
- This prevents the SQLite reads from blocking the shared event loop; it is not
  evidence that client-visible spinner/render time is lower. No real ticket,
  database, admin/customer message, wallet/payment, provider or Telegram action
  occurred. A7, final combined CI, current-main/protected-source sync and the
  single batch release gate remain open.

## S12.35.306 — Admin confirmed reply Send read scheduling — 2026-10-11

- The actual token-bearing Send button emitted from the Admin reply preview
  dispatches through the registered `ticket|` handler. Before the fix, the
  handler synchronously read language and ticket from SQLite before the ACK.
  Five new preview-Send assertions reproduced the missing scheduling seam.
- The minimal source change adds only `send` to the existing Admin read-offload
  condition and schedules its ticket SELECT with `asyncio.to_thread`. Stale and
  tokenless previews still send nothing; valid previews ACK once before the
  fake customer send, keep the per-ticket in-flight lock, and remain retryable
  after a simulated delivery failure.
- Combined no-I/O pytest: `48 passed, 2 subtests passed in 19.23s`. A later
  selector-based standard-library unittest recheck returned `Ran 2 tests in
  0.855s — OK` for concurrent single-send/replacement-preview and failure/retry
  behavior. The test-only selector rejects file-descriptor registration; the
  Ubuntu CI selection still must run.
- No real Telegram message, production ticket/DB, provider, wallet/payment,
  AutoPost, protected engine, deploy or restart. This is event-loop protection,
  not measured client-latency improvement; A7 and final batch gates remain open.

## S12.35.311 — Admin Ticket detail skips unused language lookup — 2026-10-11

- RED: the actual filtered Admin Ticket list emitted valid detail callbacks;
  both the existing-ticket and stale-ticket Admin paths called the SQLite
  language getter after their early ACK even though these screens use fixed
  Vietnamese copy. The unauthorized path was already denied before the ticket
  read.
- The exact authorized detail branch now uses the existing Vietnamese default;
  the early ACK, offloaded ticket lookup, unchanged detail/stale recovery and
  list/Home controls are preserved. No other route's locale handling changed.
- GREEN: the valid detail, stale recovery, and unauthorized denial cases passed:
  `Ran 3 tests in 11.088s — OK`. The test-only inert coroutine runner avoids a
  Windows event-loop setup stall before these no-I/O fixture handlers. This is
  source-level handler evidence, not a live Telegram/client latency measurement.
- The test module is already selected in CI. Adjacent Ticket regression,
  whole-bot compile, consolidated CI, current-main/protected-source comparison
  and one-batch release remain open. Changed-test `py_compile` and
  `git diff --check` exited 0; the diff check showed an existing line-ending
  warning in an unrelated file. State YAML parsing is NOT_VERIFIED locally
  because PyYAML is unavailable; the existing CI step installs PyYAML and
  parses the file. A full local unittest run stalled at the next-page async
  case after two tests reported OK; it was interrupted and marked NOT_VERIFIED,
  not a failure or pass. CI must execute the full selected test module.
- No production ticket/database, admin/customer message, Telegram send,
  provider, wallet/payment, AutoPost, or protected engine was invoked.

### S12.35.311 local full-module verification refresh

- The initial module runner stalls inside Windows `asyncio` `_fallback_socketpair`
  while `asyncio.run` initializes, before dispatching the callback. `faulthandler`
  captured that exact stack in the preview/attach fixture.
- These test coroutines use only inert fake handlers and mocked `asyncio.to_thread`;
  no coroutine should yield external I/O. Replaced only their test-driver calls
  with `_run_inert`, which fails explicitly if a coroutine yields unexpectedly.
- Full `tests.test_support_ticket_reply_origin_pagination` now returns
  `Ran 19 tests in 63.943s — OK`; changed-test `py_compile` and `git diff --check`
  exit 0. This resolves the local verification stall without changing production
  code. Consolidated CI still must run its selected module.

## A7 — All-callback timing aggregate — 2026-10-11 18:26 +07

- The approved read-only 24-hour all-route aggregate returned four callback
  events across three groups. Only counts and timing statistics were returned;
  raw logs, IDs and payloads were not printed.
- `menu|main_video` (admin, n=1): render max 72.066ms; handler/dispatch max
  135.942ms. `menu|main` (admin, n=2): render average 2833.405ms / max
  5582.814ms; dispatch average 2909.028ms / max 5678.657ms. `account_root`
  (n=1) dispatched in 295.238ms.
- The Home outlier spent 5582.814ms in the awaited render/edit helper; its
  pre-ACK, language, cleanup and build phases were fast. The logs cannot
  distinguish Telegram API wait from VPS network or client rendering. Owner's
  latest Video → Back observation was <1s, but no exact timestamp was supplied
  to correlate it to this aggregate.
- No change was made to the shared render helper: a single server-side outlier
  is not a reproduced client-visible defect, and the helper is shared by
  protected routes. Other routes had no sample, so A7/all-button smoothness
  remains partial. No raw log, runtime/source change, send, provider, wallet,
  deploy or restart occurred.

## S12.35.317 — Memory delete confirmation concurrent replay

- The actual emitted delete confirmation callback was dispatched twice with
  distinct callback-query IDs, both suspended at the ACK await, through the
  matching registered pattern and extracted production handler. The fixture
  asserted one ACK per click, exactly one successful archive update/event, and
  one consumed-confirmation response.
- Focused result: `Ran 1 test in 0.812s — OK`; changed test-file `py_compile`
  exited 0. The deterministic scheduler is test-only and has no external I/O.
- No duplicate effect reproduced: pending confirmation is synchronously
  consumed before the next handler await. No production fix was warranted.
  The test remains inside the CI-selected root-menu module; consolidated CI,
  whole-bot compile and cross-process behavior are not established here.
- No production DB, Telegram send, provider, wallet, job, AutoPost or protected
  engine action occurred.

## S12.35.326 — PayOS Risk stale/invalid callback ACKs once

- Root cause: the registered admin callback ACKed before action/payload
  validation, then its unsupported-action fallback ACKed again. Obsolete
  actions and malformed required IDs therefore produced two answers.
- The exact registered `^payrisk\\|` route now validates the action and its
  required payload before the normal early ACK. Invalid values return the
  existing alert once; valid branches preserve their early ACK and non-admin
  denial. No risk action, payment, order, wallet, or provider behavior changed.
- RED/GREEN: four test methods ran through a direct bundled-Python
  no-I/O/no-yield driver (`Ran 4 tests in 0.505s — OK`), including all six
  malformed subcases, emitted report/help controls, and non-admin denial.
  Native `unittest`/`asyncio.run` stalled before its first async fixture
  completed under Windows Proactor and was interrupted; it is not counted as a
  pass. The test is selected in CI, which remains pending.
- Fixture-only: no production DB, risk mutation, payment, wallet, provider,
  Telegram send/callback, merge, deploy or restart. Whole-bot compilation and
  live behavior remain unverified.

## S12.35.320 — Admin Ticket input-prompt Back ancestry

- The Admin Ticket detail keyboard's actual Reply, Ask, and Note controls were
  each opened through the registered `ticket|` handler. Their emitted Back
  callback `ticket|av|41|new|0` was dispatched through that same handler and
  returned the matching ticket detail.
- The source-extracted fixture uses the actual `set_support_ticket_pending` and
  `clear_support_ticket_pending` helpers with in-memory `USER_PENDING`: each
  Back clears actor 501's prompt state and preserves user 999's unrelated state.
  ACK, detail read and render are asserted; update/send seams remain unused.
- Sixteen focused test-function cases passed via the bundled Python no-yield
  runner; test-file `py_compile` and `git diff --check` exited 0. This is direct
  fixture evidence, not a pytest/CI or live-latency pass. No product mismatch
  reproduced; no production source fix was needed. Full batch CI, whole-bot
  compile and global A3/A5/A7 closure remain pending.

## S12.35.327 — Admin Ticket stale status emitted-route confirmation

- `support_ticket_admin_keyboard()` emitted
  `ticket|st|987654321|resolved|new|0`; this exact value matched the registered
  `ticket|` handler and was dispatched with an inert stale-ticket lookup.
- One not-found alert was observed, with no status update or screen render.
  The malformed-status guard and existing Ticket hub ACK/render cases also pass.
- The same stale-status assertion passed against `git show HEAD:bot.py`, so no
  product defect was reproduced. The focused test was strengthened from a
  hard-coded abbreviated value to the actual emitted callback; no production
  source was changed.
- Three direct no-I/O assertions passed, along with focused test `py_compile`
  and `git diff --check`. CI/live latency remain unverified; no production
  ticket query, message, or Telegram action occurred.

### S12.35.328 — PayOS Risk report route supplement

The emitted `payrisk|report` control was dispatched through the exact registered
callback with report, audit, and render sinks replaced by inert fixture functions.
It ACKed once, rendered the supplied fixture report, recorded exactly one
fixture audit event, and exposed the expected refresh, Admin, and Main callbacks.
This closes only the read-only report UI plumbing slice; report-data accuracy,
other payment-risk actions, production behavior, and live/client rendering remain
unverified. No database, payment, wallet, provider, real Telegram, or production
data operation occurred.

### S12.35.329 — Legacy Language `lang_more` route supplement

The retained legacy `lang_more` callback was matched to the registered Language
handler and dispatched with inert language and render functions. It ACKed once
and rendered the canonical picker with the fixture's current locale choices,
`lang_back`, and `menu|main`; preference and usage sinks were not touched. The
fixture used a two-locale set and does not establish all-locale or persisted
preference behavior. A heavier composite-test import stalled before route entry;
the lean source-extracted fixture is the only counted evidence for this slice.

### S12.35.330 — Manual Top-up Back route supplement

The real manual-payment menu keyboard emits menu|main_topup for its Back-to-
Top-up control. That exact value was dispatched through the registered Menu
handler and returned the Top-up selector with the expected package and manual
entry controls, with one ACK. A direct no-I/O fixture and the existing Account
Top-up suite (5 tests, OK) found no route defect. Payment/order/provider paths
and Telegram-client latency were not exercised; no financial operation or
production source change occurred.

### S12.35.331 — ReplyKeyboard Home with Support pending input

The actual extracted handle_message Home branch was composed with the actual
cmd_start and Support pending-state helpers using inert non-Support cleanup and
render seams. With an awaiting_ticket_reply fixture, Home rendered Main before
the Support text handler, cleared only the actor's pending state, retained the
other user's pending entry, and preserved the actor's last-ticket return ID.
The no-yield fixture passed; no production/test patch or real Telegram action
occurred. This does not measure ReplyKeyboard delivery latency or close other
pending families.

### S12.35.333 — Feedback Home-to-Main registered-route supplement

The Feedback category keyboard's actual Home button emits `menu|main`, which
matches the registered Menu callback. Dispatching that value through the actual
`handle_menu_callback` with the production feedback cleanup and inert other
cleanup families rendered Main, ACKed once, removed the actor's Feedback pending
entry, and preserved an unrelated pending marker. The subsequent feedback text
handler returned false without replying. The focused direct fixture passed;
broader direct execution of the module did not complete and is not counted. No
production callback defect or `bot.py` change was found. Client rendering,
live timing, whole-batch CI and other pending families remain unverified.

### S12.35.335 — Memory expired delete-confirmation supplement

The production delete-confirm keyboard's emitted confirmation callback was
dispatched through the registered Memory handler after its in-memory pending
state exceeded the TTL. The handler ACKed once, displayed the existing expired
button message, removed only the actor's expired state, preserved another user's
state, and reached neither the note-read nor DB seam. The focused fixture passed;
no production defect or `bot.py` change was found. Other Memory stale/repeat
routes, live/client behavior and consolidated CI remain unverified.

### S12.35.334 — Feedback prompt Back-to-picker registered-route supplement

The actual Feedback category control was dispatched through its registered
handler, then the prompt's emitted `feedback|start` Back was dispatched through
that same registration. The category picker returned with one ACK; the actor's
old Feedback pending state was cleared, an unrelated user's state was preserved,
and the next ordinary text was not consumed by the abandoned form. The focused
direct fixture passed. No production defect or `bot.py` change was found; the
broader module and live/client behavior remain unverified.

### S12.35.336 — Expired Document confirm callback

The actual Document after-file keyboard's `docflow|confirm` value was dispatched
through the registered `^docflow\\|` handler after the actor's fixture pending
state expired. The handler ACKed once, returned the existing expired/no-charge
Document hub screen, removed only the actor's expired record, preserved a second
user's fresh state, and did not reach `run_doc_tool_state`. This is stale-control
navigation evidence only; document processing and live/client timing remain
unverified.

### S12.35.337 — Expired Document run callback

The actual Document confirmation keyboard's final `docflow|run` value was
dispatched through the registered `^docflow\\|` handler after the actor's
fixture pending state exceeded its TTL. It ACKed once, returned the existing
expired/no-charge hub recovery, removed only the actor's expired state, retained
another user's fresh pending entry, and did not reach `run_doc_tool_state`.
Document processing and live/client timing remain unverified.

### S12.35.338 — Expired Document file controls

The actual after-file keyboard's `docflow|send_more`, `docflow|pop`, and
`docflow|clear` values were each dispatched through the registered `^docflow\\|`
handler after the actor's fixture pending state expired. Each click ACKed once,
returned the existing expired/no-charge Document hub screen, removed only the
actor's stale state and preserved another user's fresh state. No file state was
mutated and no document processing occurred; live/client behavior remains
unverified.

### S12.35.339 — Active Document clear-list callback

The active after-file keyboard's `docflow|clear` button was dispatched through
the registered `^docflow\\|` handler. It ACKed once before locale lookup,
cleared only the current user's staged file IDs/count/options, preserved a
second user's pending state, and returned to the upload prompt. No document
processing, database, charge, provider or Telegram-send operation was invoked.
This fixture does not establish live rendering or client latency.

### S12.35.358 — Media Library Home callback

The production `media_library_quick_keyboard` emitted `menu|main`; the callback
matched the registered Menu handler and rendered the fake Main screen with one
ACK via the handler's actual `localized_menu_content` path. Output:
`MEDIA_LIBRARY_HOME_REGISTERED_ROUTE_OK: emitted menu|main, one ACK, Main
screen/keyboard, fixture-only cleanup` (exit 0). No production account/payment,
provider, job, Telegram-client or engine action was performed.

### S12.35.360 — Admin Provider/Worker handbook guide callbacks

All six testing-labelled buttons emitted by the Provider/Worker module keyboard
carry the contextual callback `admin_help|provider|admin_provider_worker`. Each
was dispatched through the exact registered `handle_admin_help_callback`, ACKed
once, rendered the static Provider/Worker guide and exposed Back to
`menu|admin_provider_worker` plus Home `menu|main`. The CI-selected
`test_admin_module_child_back_origin.py` fixture printed
`ADMIN_PROVIDER_WORKER_GUIDES_OK: 6 emitted controls -> registered help route,
one ACK, scoped Back/Home, no provider calls` (exit 0). No operational provider,
worker, TTS/ASR/SubDub or canary action ran; this is route evidence, not live UI or
operational-check evidence.

### S12.35.361 — Admin Support handbook guide callback

The actual Admin Support module keyboard emitted `📌 Hướng dẫn hỗ trợ` as
`admin_help|support|admin_support`. It matched the registered
`handle_admin_help_callback`, ACKed once, rendered the static Support guide, and
emitted Back to `menu|admin_support` plus Home `menu|main`. Focused fixture output:
`ADMIN_SUPPORT_GUIDE_REGISTERED_ROUTE_OK: exact emitted callback, one ACK,
Support Back/Home, no ticket/data action` (exit 0). No Ticket, customer-data or
notification action was invoked; live rendering/latency remains unverified.

### S12.35.362 — Admin module handbook footer matrix

For every key in the current `ADMIN_CONTROL_MODULES` registry, the fixture emitted
its module-footer `📘 Hướng dẫn` button and dispatched the exact contextual
callback through the registered `handle_admin_help_callback`. All guide routes
ACKed once, rendered the corresponding static handbook section, and exposed Back
to `menu|admin_<module>` plus Home `menu|main`. The CI-selected route fixture
printed `ADMIN_MODULE_GUIDE_MATRIX_OK: all emitted footer guides -> exact
registered handler, one ACK, scoped Back/Home` (exit 0). No operational checks,
providers, DB/customer reads, payment, engine or Telegram action was run.

### S12.35.363 — External callback-emitter source census

A read-only source search found 16 Python files under `services/` or `handlers/`
containing `callback_data` or `InlineKeyboardButton`. The five `handlers/*`
modules appear imported only by `handlers/__init__.py` in the source search; no
runtime reachability is claimed. Active service emitters found in `bot.py` map
to locked AutoPost, Product/Video, or SubDub/Music progress areas, except the
shared navigation helper already covered by S12.35.351. `workflow_graph_contract`
contains callback matching/validation but is not proof of an actual Telegram
keyboard. This is a grep census, not AST/runtime route evidence; protected and
opaque routes remain open and were not exercised.

### S12.35.364 — FreeHub empty publish-package guidance

The production Free Tools keyboard's `freehub|publish_package` callback was
dispatched through the exact registered `handle_free_hub_callback` with empty
pending state. The handler ACKed once, rendered localized prompt guidance with
the no-Xu copy, and preserved the hub keyboard. Result text/keyboard helpers were
fail-fast and not called; no AutoPost, provider, engine, wallet, social publish,
Telegram send or production-data operation was run. Output:
`FREEHUB_EMPTY_PACKAGE_GUIDE_OK: emitted callback -> registered route, one ACK,
actual copy/no-Xu, no publish helper, hub keyboard retained` (exit 0).

### S12.35.365 — FreeHub package result Back ancestry

The production `free_hub_result_keyboard` emitted `freehub|publish_package`; with
fixture result state, the exact registered FreeHub handler ACKed once and rendered
the package summary. Its emitted `freehub|prompt_back` was dispatched through the
same registration, ACKed once, and restored the same result content and exact
keyboard while preserving pending state. The result's emitted `freehub|main`
then returned to the fixture Free Tools root, cleared only the actor's pending
result, and preserved another user's pending record. The emitted `freehub|copy`
also remained on the same result and only added localized copy instructions.
Output: `FREEHUB_PACKAGE_BACKSTACK_OK: package Back restores result; Copy stays
on same result; Home clears actor only; ACK/state assertions pass` (exit 0). No generation, save/persist,
AutoPost, provider, payment, wallet, engine, data or Telegram-send action ran.

### S12.35.366 — Admin Queue refund guide callback

The actual Queue module screen emitted “Hướng dẫn hoàn Xu khi job lỗi” with
`admin_help|refund|admin_queue`. Dispatch through the registered
`handle_admin_help_callback` ACKed once, rendered the static refund instructions,
and exposed Back to `menu|admin_queue` plus Home `menu|main`. Output:
`ADMIN_QUEUE_REFUND_GUIDE_ROUTE_OK: emitted scoped callback -> registered help,
one ACK, Queue Back/Home, no job/refund` (exit 0). No job query, refund/payment,
wallet, provider, customer data or production Telegram action ran.

### S12.35.367 — Admin Provider/Worker Route Info Back/Home

The real Provider/Worker screen emitted `menu|admin_provider_routes|admin_provider_worker`.
Through the exact registered Menu handler it ACKed once, rendered fixture route
information, and emitted Back to `menu|admin_provider_worker` plus Home
`menu|main`. Output: `PROVIDER_ROUTE_INFO_BACK_HOME_OK: exact emitted callback,
one ACK, Back to Provider/Worker, Home, fake report only` (exit 0). No provider
or worker check or production report read ran.

### S12.35.368 — FreeHub translation input Back

The actual Free Tools keyboard emitted `freehub|open_translate`, which matched
the registered `handle_free_hub_callback`, ACKed once, and rendered the input
prompt with actor-scoped pending state. The prompt's emitted `freehub|main` Back
was dispatched through that same registration, ACKed once, returned to the hub,
and cleared only the actor's pending input; another user's state was preserved.
Output: `FREEHUB_TRANSLATION_PROMPT_REGISTERED_BACK_OK: emitted callback, exact
handler, one ACK each, actor-only pending cleanup` (exit 0). No user text,
translation, provider, production state or Telegram send was involved.

### S12.35.369 — FreeHub Docs immediate-parent Back

The production `free_hub_docs_keyboard` emitted `freehub|docs_split_merge` and
`freehub|docs_summary_guard`. Both exact registered callbacks rendered their
static guides and emitted Back=`freehub|docs`; dispatching Back previously
returned `menu_text_main_memory_i18n` / `main_memory_keyboard`, the wrong parent.
The narrow fix routes only `action == "docs"` back to the FreeHub PDF/Word tools
screen and preserves the legacy `action == "notes"` Memory destination. Both
Back paths now restore the original docs text/keyboard with HTML parsing and one
ACK per click.
Output: `FREEHUB_DOCS_BACK_ROUTE_GREEN: split/summary Back returns exact docs
keyboard; legacy notes destination preserved` (exit 0). No file, provider,
payment, production data or protected engine action ran.

### S12.35.370 — FreeHub Docs image/compress hint origin

The production FreeHub Docs keyboard's Image→PDF and Compress-PDF buttons
previously emitted generic `menu|hint_doc_*` routes; those Menu-handler hints
returned Back=`menu|main_docs`, not the originating FreeHub docs keyboard. The
narrow fix scopes only these two FreeHub emitters as `freehub|docs_image_to_pdf`
and `freehub|docs_compress_pdf`, reuses the localized hint text, and returns
Back=`freehub|docs`. Generic Main Docs hint routes remain untouched. Focused
registered-route fixture output: `FREEHUB_DOC_HINT_BACK_ROUTE_GREEN: image/compress
hint Back restores exact FreeHub Docs screen; generic docs routes unchanged`
(exit 0). It verifies both routes, HTML parsing and one ACK; no file/provider or
engine action ran. A protected comparator also dispatches generic
all five `main_docs_keyboard` `menu|hint_doc_*` controls and confirms each Back
remains `menu|main_docs` with the original keyboard. Existing FreeHub Docs
keyboard expectations in `test_core.py` and `test_free_tools_hub_v1.py` were
updated to scoped callback values; the generic emitter remains unchanged.

### S12.35.371 — Current-main inline-button callback expression census

Token-stream extraction followed by per-constructor AST parsing on exact local
`origin/main:bot.py` (`381c71bb9e52876eb35b15f5c417ca2cf833dc28`, 15,029,211 bytes)
returned 4,003 `InlineKeyboardButton` calls; 3,979 had callback data and 24 did
not. It parsed 914 non-literal expressions (names/calls/f-strings/conditionals/
subscripts), with zero per-call parse failures. Counts align with the earlier
S12.35.350 button inventory. This does not prove handler coverage/permissions or
dispatch correctness for dynamic values; no callbacks were executed and no
product/provider/AutoPost routes were touched.

### S12.35.372 — FreeHub legacy BYOK disabled fallback

The current Free Tools root keyboard does not emit `freehub|byok`, but the
registered handler still accepts older/stale callback buttons. With BYOK disabled,
the legacy route previously rendered generic support-setup copy in place of an
explicit unavailable/no-key warning. The narrow copy branch now says in both
Vietnamese and English that TOAN AAS is not accepting API keys and keys must not
be sent in chat. The registered-route fixture passed (1 test, exit 0), ACKed once,
cleared only the actor's temporary pending state, preserved another user's state,
and rendered the actual Free Tools root keyboard. It did not inspect or accept a
key or call a provider. Whole-source py_compile was interrupted after about six
minutes without an exit result and remains unverified; `git diff --check` exited
0 with existing LF-to-CRLF warnings. No production runtime, provider, wallet,
database or Telegram send was touched.

### S12.35.373 — FreeHub root Music/SFX shortcut ancestry

The exact Music/SFX button emitted from the actual Free Tools root previously
shared `freehub|lib_music` with the Prompt Library category button. Dispatching
that root shortcut through the registered FreeHub handler opened the Music/SFX
suggestions page, but its Back emitted `freehub|library`, the wrong parent; the
focused regression reproduced this RED. The fix gives only the root shortcut a
distinct `freehub|lib_music_root` callback, stores its parent (`freehub|main`)
in that user's temporary FreeHub state, and emits root-scoped More/Pick/item-Back
callbacks. Its Back label and destination now identify Free Tools; More and item
Back preserve the origin, and a stale root-scoped More returns to Free Tools.
Selecting a music prompt and choosing Copy also preserves the root-scoped item
Back callback.
The same Music category from the Prompt Library still emits `freehub|lib_music`
and returns to `freehub|library`. Latest registered-route fixture: 1 test in
0.805s — OK; related FreeHub regressions: 4 tests in 3.283s — OK. The test stubbed
the prompt library, so no prompt source, audio/music engine, provider, database,
wallet, Telegram or production state was accessed. Full-source compile and CI
remain release gates; no push/PR/merge/deploy/restart occurred.

The adjacent Aichat Back → Free Tools assertion also checks the updated root
callback set. Its first `asyncio.run` attempt stalled in the Windows fixture;
the dispatcher was changed to the existing no-yield runner (no production
behavior change). Final targeted Aichat-root + Music/SFX registered-route rerun:
2 tests in 1.062s — OK. No Chatbot behavior/state was altered.

### S12.35.378 — Local Video Studio public-planner persist callback

The actual planner summary emitter produced `lvs27b|<session>|persist`; the
callback matched the production `^lvs27b\\|` registration and dispatched through
`handle_local_video_studio_public_callback`. A test-local, shared-memory SQLite
database stored exactly one plan. Replaying the same Telegram callback ID was
ACK-only/no-edit; a distinct ID for the unchanged plan returned the saved view
without creating another row or incrementing its version. An unrelated
`video_edit_sentinel` in the same context remained unchanged. Output:
`test_local_video_public_plan_save_button_uses_registered_handler_idempotently`
ran 1 test in 0.132s — OK. No production DB, provider, wallet, job, video render,
Telegram API or engine operation was used. Other saved-plan list/view/edit/delete
routes and public client rendering/latency remain unverified.

S12.35.378 updates the `lvs27b` row above: the emitted persist control is now
verified through the exact registered handler using a shared in-memory SQLite
database. One plan row is created; the same callback ID is ACK-only, and a new
callback ID with unchanged plan content does not add a row or increment version.
The remaining local saved-plan list/view/edit/delete callbacks and actual client
rendering/latency remain unverified.

### S12.35.382 — `/profile` command-emitted Account callback round-trip

The registered `/profile` command emitted the production localized Account
keyboard. Its actual `menu|profile_packages` button matched the source's
registered `handle_menu_callback` route and dispatched with one ACK. The
fixture-only Packages screen emitted Back=`menu|main_profile` and Home=`menu|main`;
Back restored the same six-row command keyboard and Home returned to the fixture
Main screen. Targeted output: `Ran 1 test in 0.718s — OK`. No production account
or package data, payment, wallet, provider, AutoPost, or engine path was used.
Current main #1424 diff does not mention `cmd_profile`, `main_profile_keyboard`,
or the Account callback values; no latest-main runtime/deploy claim is made.

### S12.35.383 — Customer Ticket Done stale replay

The production Ticket-detail keyboard emitted the scoped Done callback and the
exact `^ticket\|` registered handler processed two separate query objects.
Before the fix, the second press after the fixture Ticket had become `resolved`
called `update_support_ticket(status="resolved")` a second time and rewrote the
close/update timestamp. The Done branch now skips only that redundant update for
an already `resolved`/`closed` owned Ticket; the same ACK, success text, pending
cleanup and Back/Home keyboard are preserved. Replays against both resolved and
closed fixture Tickets keep the update count at one. GREEN: duplicate replay,
existing Done Back ancestry, and emitted Done/ACK regression returned
`Ran 3 tests in 15.852s — OK`. Fixture-only; no production Ticket, notification,
provider, wallet, or Telegram operation. Main #1424 diff does not touch this
Ticket handler/keyboard; runtime behavior is not claimed.

### S12.35.379 — Current-main #1424 Owner-live callback (static only)

Read-only GitHub API reports `main=e2b48f215f30a088156a1e29c1f402170274dcf0`
(2026-10-12), one commit beyond local `origin/main` `381c71bb…`. The commit
modifies `bot.py` and provider/spend-guard, Key4U/ShopAI TTS, video provider,
video queue and public-chat services. Its bot patch adds an Owner live-accept
button, a dedicated handler, a `VIDEO_PUBLIC_CALLBACK_OWNER_PREFIXES` entry and
`video_route_expected_handler` mapping. The same patch has no explicit
`CallbackQueryHandler(handle_product_video_owner_live_accept_callback, ...)`
registration; the existing broad `^vproduct\|` handler is unchanged. Static
evidence leaves the actual dispatcher owner uncertain, so this is a possible
misroute, not a confirmed runtime defect.

The new handler validates a durable Owner receipt and may propagate to
`confirm_video_project_invoice` to authorize a paid live test. For that reason
this audit did not dispatch the callback, read a receipt, call a provider, touch
queue/wallet state, add a registration, or rebase the protected main delta. A
separate explicit Owner approval is required before wiring or exercising the
paid path. Keep this route `NOT_VERIFIED / OWNER_GATE`; it does not stop other
safe callback audits.

### S12.35.380 — Local Video Studio saved-plan list/detail/back

The audit-worktree planner summary keyboard emitted the saved-plan list callback; its list
emitted the current owner's saved-plan detail callback; Detail emitted `library`
Back. All three values matched the source's actual `CallbackQueryHandler`
registration and dispatched through its callback with one ACK each. A shared
in-memory SQLite fixture confirmed owner/chat-scoped rows, restored the same list
after Back, and retained exactly the three seed rows. Output:
`Ran 1 test in 0.145s — OK`. No production DB, plan mutation, provider, wallet,
job, render, Telegram API, or Product/Edit engine was used. The source was the
audit branch based on `381c71bb…`, not protected latest-main #1424 (`e2b48f2…`)
or live runtime; this result is not a latest-main/live claim.

### S12.35.384 — Customer Ticket Done concurrent callback

Two callbacks using the actual emitted scoped Done value were dispatched through
the exact registered `handle_ticket_callback`, with deterministic scheduling that
held both owner-scoped fixture reads at `new`. The pre-existing sequential replay
guard allowed two writes under this race, reproduced by a fixture SQLite trigger.
The narrow fix delegates only customer Done to
`resolve_support_ticket_once(ticket_id, user_id)`, a conditional owner-scoped SQL
UPDATE excluding `resolved`/`closed`, followed by an owned-row readback. The test
confirmed one transition total, one ACK for each callback, unchanged success
rendering and identical Ticket-detail Back navigation. Focused combined result:
`Ran 4 tests in 54.808s — OK`; changed test modules' bundled `py_compile` and
`git diff --check` exited 0. The fixture used shared in-memory SQLite only. No
production Ticket, notification, payment, wallet, provider, engine, AutoPost or
Telegram action occurred. Full `bot.py` compile and latest-main/live behavior
remain unverified; this evidence closes only the concurrent Done route slice.

### S12.35.385/.386 — Admin Ticket status validation and response order

The Admin Ticket detail keyboard emits three status values only:
`resolved`, `refund_pending`, and `waiting_provider`. A callback derived from its
actual resolved button but changed to `not_a_status` previously performed a
Ticket read and wrote the unsupported value; the handler now rejects unsupported
statuses before any read/update. All three emitted values still pass through the
exact registered `handle_ticket_callback`, update only the fixture, ACK once, and
preserve the existing refund warning. Six focused source-extracted checks passed;
the refund-notice replay regression ran `Ran 1 test in 0.304s — OK`.

The valid emitted status route also previously performed synchronous language and
Ticket reads before acknowledging the callback (`[('language', 0), ('ticket', 0)]`).
It now performs exactly one ACK before both reads. If the ticket is stale, it edits
to a localized not-found screen with Back to the original source/page and Main
Home; it does not attempt a second alert ACK or update. The same focused six checks
cover this order/recovery. Focused status test functions and existing refund replay
passed; the broad origin/page regression is recorded `NOT_VERIFIED` because it
stalled locally. Full `bot.py` compile currently has a no-result local process
pending, so no full-source or CI pass is claimed. Fixture-only; no production
Ticket, payment, wallet, provider, engine, AutoPost or Telegram action occurred.

### S12.35.404 — Product Video Owner live-accept callback registration

The current-main keyboard emitted `vproduct|owner_live_accept` or the same
callback with a 12-character lowercase-hex receipt token. The route map expected
`handle_product_video_owner_live_accept_callback`, but lifespan registered only
the generic Product Video route. RED: the exact dedicated route regression
failed because that registration was absent. The narrow fix registers the
existing handler with an anchored token pattern before the generic handler and
excludes this action from the generic pattern. GREEN: focused route/dedupe tests
passed (2 tests); source compile #38353329268 and full CI #38353329226 both
passed on exact commit `b3f91bb0e8b7a74fdc9d7255617624f384b2135b`, including the
Product Callback Replay Guard Boundary step. The handler can admit an
Owner-authorized paid Product Video test; no callback was dispatched and no
invoice, job, provider, wallet, or production data was touched. This closes only
the callback registration defect; PR #1426 is still OPEN/DRAFT and not deployed.

### S12.35.395 — Local Video Studio saved-plan navigation/CRUD fixture result

The actual Local Video Studio saved-plan `lvs27b` callback registration, entry,
list, detail, Back, edit, confirmed delete, owner/chat isolation, delete-failure
recovery, and optimistic-version fixtures returned without product assertions
failing. The original direct runner exited 1 during Windows temporary SQLite
cleanup, so it is not counted as a clean test PASS. A focused pytest retry stayed
silent for more than four minutes and was interrupted; record it as
NOT_VERIFIED. The four local SQLite-backed saved-plan tests have been selected
in the existing Linux Small Navigation CI step; that result is pending push/CI.
No video generation/render/provider, payment, wallet, production DB, Telegram,
or protected engine action was used.

### S12.35.400 — Manual top-up foreign-owner ACK count

Ten customer controls emitted by the real manual top-up and PayOS-recovery
keyboards were dispatched through the exact registered manual callback route
for a non-owner.
Before the narrow change, each produced an empty ACK followed by the existing
denial alert. Deferring the ACK until after the owner check leaves exactly one
denial alert. The regression asserts that no state/DB/payment/provider seam is
entered. Bundled-Python verification with the related manual-package suite:
`Ran 3 tests in 1.843s — OK`. CI selection now includes the new test; full-source
compile and consolidated CI remain pending.

### S12.35.395 — Local Video Studio saved-plan route recheck

The exact registered `^lvs27b\\|` handler pattern covers the emitted entry and
saved-plan actions. The registered entry/Back fixture passed its assertions,
including expired Back recovery. Four additional existing fixture bodies
dispatched list/view/edit/delete-confirm and failure/retry cases through the
source-extracted handler with owner/chat-scoped temporary SQLite data; all
assertion bodies returned without assertion failure. No ownership, Back, retry,
or stale-plan defect was reproduced. The direct runner exited non-zero only while
Windows attempted temporary SQLite cleanup; the exact temp directory was removed
after process exit. Bundled pytest is unavailable, so these results are not a
clean full-module or test-suite PASS. No product code, production DB, render,
provider, wallet, job, Telegram API, AutoPost, protected engine, merge, deploy,
or runtime was touched.

### S12.35.393 addendum — last-confirmed-main PayOS callback regression

The table's S12.35.319 single-ACK fix describes the audit branch, not the last-
confirmed main source (read-only SHA check 2026-10-12). Exact
`e2b48f215f30a088156a1e29c1f402170274dcf0:bot.py` extraction through the emitted
`payos_pkg|10k|123` control and registered handler reproduced
the pre-fix foreign-owner behavior: two ACKs (`ACK_COUNT=2`) and event order
`expire → ACK → ACK`. The audit-branch fixture invoked all five top-level
assertions successfully. This is source/test evidence only; latest VPS runtime,
final-main CI and delivery remain unverified. Do not repeat or claim the fix is
live before final exact-main reconciliation.

### S12.35.390 — Home clears Local Video Studio text-input ownership

`cmd_start` (also used by `/menu`) and the common `handle_menu_callback` cleanup
did not clear `_LOCAL_VIDEO_PLANNING_PENDING_KEY`, even though the next text
message handler consumes that marker as Local Video Studio brief input. The
emitted Home button from `main_video_keyboard()` is `menu|main` and matches the
registered `^menu\|` route. RED was reproduced through the actual command and
registered callback handler fixtures. The fix calls the existing
`_local_video_planning_clear_pending(context)` at both exit boundaries; only the
input-owner marker is removed, while saved planner session and Video Edit state
remain unchanged. Direct fixture output: `PASS (cmd_start, cmd_menu, emitted
Video-menu Home via registered Menu handler)`. No rendering/provider, Xu, DB,
Telegram, or protected engine work occurred. Full-source CI/compile and broader
A3/A5/A6/A7 acceptance remain open.

### S12.35.389 — PayOS foreign-owner denial locale

An actual package-choice button was dispatched through the exact registered
`handle_package_choice` handler with callback owner 123 and clicker 456. The
fixture configured different locales and proved RED: the handler looked up the
package owner's language, so the clicker's denial could be rendered in the
wrong language. The one-line branch change now looks up `query.from_user.id`.
All five focused package-choice assertions pass, including one denial alert and
the already-verified ACK-before-expiry order. No payment/order path or production
data was entered. The test is CI-selected; full bot compile and consolidated CI
remain release gates.

### S12.35.387 — Memory delete confirmation owner scope and replay

The emitted `memory|delete_yes|445|fixture-delete-token` control matched the
registered `^memory\\|` handler and was dispatched through the extracted
production handler. The fixture observed one owner-scoped archive update, one
ACK/event/success render, actor-only pending cleanup, and preservation of another
user's pending marker. Replaying the consumed callback ACKed once and returned
expired/invalid guidance without another update or event. The focused assertion
and existing expired-confirm assertion passed; test-file compilation and
`git diff --check` exited 0. The full Memory module stalled after its first dot
and is `NOT_VERIFIED`, not a product failure. No production note/DB, Telegram,
provider, wallet, AutoPost, or protected engine was touched; consolidated CI,
whole-source compile, remaining A3/A5/A6/A7, main/protected comparison and batch
delivery remain open.

### S12.35.388 — Memory search-origin delete Cancel pending cleanup

RED reproduced on the actual emitted cancel value
`memory|view|445|search|old-search`: after the search TTL expired, the registered
Memory handler returned to its root screen but left the matching fresh
`delete_confirm` state pending. The narrow fix stores the origin search token on
search-origin confirmations and clears only the pending action with matching
note ID and token on invalid/expired search context or missing result. It
preserves a newer confirmation with a different token. The emitted route fixture,
owner/replay confirmation regression, and expired-confirm regression passed
(`Ran 3 tests in 3.419s — OK`); test-file `py_compile` and `git diff --check`
exited 0. No production Memory data, provider, wallet, Telegram send, AutoPost,
or protected engine action occurred. Full module/source compile and consolidated
CI remain open; this closes only this stale search-cancel route.

### S12.35.391 — `/start` and `/menu` release Finance Compliance input

The `menu|main` callback already calls `clear_finance_compliance_pending`, but
`cmd_start` and `/menu` did not. An emitted/registered-menu comparison therefore
showed inconsistent Home exits: fixture state remained pending after
`/start`/`/menu`, and the next ordinary text could still be parsed as a
compliance-note update. A source-extracted command fixture reproduced RED. The
minimal change calls `clear_finance_compliance_pending(uid)` from `cmd_start`.
Direct fixture GREEN: `Home pending cleanup regressions: PASS (Video planner
/start, /menu, emitted callback; Finance Compliance actor-only /start and
/menu)`. Another user's marker is preserved; finance note persistence is never
called. No financial data, payment, wallet or production path was accessed.

### S12.35.385 — Admin Ticket status values fail closed

The actual Admin Ticket keyboard emits only `resolved`, `refund_pending`, and
`waiting_provider` status actions. A registered callback derived from the real
button but with its status replaced by `not_a_status` previously read the fixture
Ticket and wrote that unsupported status. The handler now rejects other values
with one unsupported-action alert before Ticket lookup/update/render. All three
actual emitted status callbacks still dispatch through the registered handler,
ACK once and apply their fixture status; the existing refund-only explanation is
unchanged. Focused Admin status fixtures: four checks passed; refund-notice replay
regression: `Ran 1 test in 0.563s — OK`. Bundled test-module `py_compile` and
`git diff --check` exited 0. The broader Admin origin/offset test stalled and was
interrupted (`NOT_VERIFIED`), so no full-module or CI claim is made. No production
Ticket, payment, wallet, provider, engine, AutoPost or Telegram action occurred.

