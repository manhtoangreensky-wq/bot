# TASK 3D — Video Product Logic, Prompt Engine and Storyboard Workflow Audit

Date: 2026-06-20

Branch: `hotfix/task3d-video-product-prompt-engine-flow`

Scope: Task 3D video menu, product contracts, prompt planning, package selection, provider diagnostics, billing boundary and navigation.

Protected scope: Task 1, Task 2 and PayOS internals were not modified.

## 1. Audit conclusion

The video area now has one explicit product registry and one compact seven-row public menu. Each of the 13 buttons resolves to a registered product with a purpose, accepted input, output, free/paid boundary, prompt template, execution route, next steps, back steps, parent-menu route, guard message and admin status fields.

The implementation deliberately preserves working render/edit flows. It adds a Task 3D product-intro adapter in front of them and only replaces the parts that were inconsistent: menu routing, missing product contracts, free prompt planning, storyboard/multishot generation, public package exposure, provider diagnostics, charge timing and return navigation.

## 2. Findings before implementation

| Finding | Risk | Resolution |
|---|---|---|
| Video menu mixed direct callbacks and unrelated flow entry points | Buttons did not share a product contract; navigation and cost messaging varied | Rebuilt the menu from `VIDEO_PRODUCT_REGISTRY` and `VIDEO_MENU_ROWS` |
| Higher 500–1500 Xu tiers could appear in customer UI from legacy runtime gates | Customer could select an unverified product outside the requested 200/300/400 boundary | Public UI/status now exposes exactly low/basic/common = 200/300/400; higher tiers remain internal/admin history only |
| Free planning and paid rendering were not represented by one boundary | A free tool could look like a paid render step | Planning produces a provider-agnostic bundle with `provider_call_required=false`, no job and no Xu deduction |
| Prompt-vault work existed only as draft/reference material | No runtime status/search/import/export contract | Added a licensed local seed vault and admin commands; no website scraping |
| ShopAIKey video flow deducted wallet/package before provider acceptance and compensated on failure | Temporary charge/refund cycle violated the requested charge boundary | Paid video now creates an internal awaiting-acceptance job, submits, and deducts only after provider returns an accepted task id |
| Product roots and legacy roots did not have one machine-auditable parent route | Back could drift to a different menu after future changes | Every product declares `parent_menu_callback=menu|main_video`; all 13 adapters and five preserved legacy roots are tested |

## 3. Final public menu

| Row | Left | Right |
|---:|---|---|
| 1 | Video theo trend | Ý tưởng video |
| 2 | Storyboard + Prompt | Prompt / Chuyển động |
| 3 | Video AI chân thật | Kịch bản → Ảnh → Video |
| 4 | Ảnh → Video | Ghép ảnh thành video |
| 5 | Tự quay & đổi cảnh AI | Phim AI nhiều cảnh |
| 6 | Video mẫu / Kênh mẫu | Nhạc / Voice / SFX |
| 7 | Chỉnh sửa video local | Menu chính |

Every product callback has the form `vproduct|open|<product_id>`. The final main-menu button remains `menu|main`.

## 4. Product contract matrix

| Product id | Purpose/input | Free output and paid boundary | Execution route | Root back route |
|---|---|---|---|---|
| `video_trend` | Topic/product/niche → trend angle | Idea, hook, script and prompt pack are free; no provider | Prompt engine only | `menu|main_video` |
| `video_idea` | Topic/product/platform → ideas | Idea pack is free; no provider | Prompt engine only | `menu|main_video` |
| `storyboard_prompt` | Topic/story/product/reference | 6/9/12/16-panel table, image/video prompts and export are free; optional one-shot render uses 200/300/400 after confirmation | Prompt engine; paid one-shot through existing finalization/ShopAIKey route | `menu|main_video` |
| `motion_prompt` | Image/scene description | Camera, subject motion and transition prompt are free | Prompt engine only | `menu|main_video` |
| `video_ai_real` | Text prompt and optional image | Prompt improvement/plan is free; real render is 200/300/400 after confirmation | Existing ShopAIKey public execution route | `menu|main_video` |
| `script_image_video` | Topic/script/product | Script, shot list, image prompts and video prompts are free; one-shot render uses 200/300/400 | Prompt engine, then existing finalization route | `menu|main_video` |
| `image_to_video` | One to four images and scene direction | Motion prompt is free; render is 200/300/400 | Existing ShopAIKey image-to-video/finalization route | `menu|main_video` |
| `frame_video_local` | Images | Existing local pricing/confirmation remains authoritative | Preserved Local Worker/FFmpeg flow; no AI video provider | `menu|main_video` |
| `self_shot_scene_change` | User image/video | Scene plan is free; only 300/400 are allowed for guarded render | Preserved self-scene flow/provider guards | `menu|main_video` |
| `multi_scene_film` | Story/product/script | Scene plan and prompt pack are free; 200 is rejected because it is one short shot only; 300/400 allowed | Existing long/multiscene execution remains guarded | `menu|main_video` |
| `video_reference` | Link/video/manual style | Original style brief is free and rights-safe | Preserved reference-analysis flow; no automatic copying/re-upload | `menu|main_video` |
| `audio_addons` | Current video session | Default plan can be free; optional audio uses Task 1 readiness/pricing | Preserved Task 1-facing audio hub; Task 1 internals unchanged | `menu|main_video` |
| `video_local_edit` | Video | Existing local edit policy remains authoritative | Preserved Local Worker/FFmpeg edit flow | `menu|main_video` |

## 5. Standard product flow

The shared Task 3D planning path is:

1. Open product contract and cost boundary.
2. Collect text or media once and retain the media file id in `VideoSession`.
3. Choose platform/purpose.
4. Choose aspect ratio.
5. Choose storyboard panel count where applicable.
6. Choose style.
7. Choose free output type where applicable.
8. Build and validate the free prompt bundle.
9. View/export prompt pack without a provider call or Xu deduction.
10. If rendering is supported, enter the existing finalization flow, choose 200/300/400, review and confirm.
11. Create an internal pending job, submit to the configured provider, and deduct only after provider acceptance.

`Back` inside the adapter pops one recorded step and preserves topic, product, style, platform, prompt bundle and source-media references. At product intro, Back returns to `menu|main_video`, the menu containing that product button. Result child screens (image/video prompt view, prompt-pack export and finalization) return directly through `vproduct|result`, so they go back to the result menu that contains their launch buttons instead of accidentally popping to style/output.

## 6. Prompt engine and storyboard contract

`VideoPromptRequest` includes product, topic, platform, aspect ratio, duration, package, objective, style, tone, language, scene/shot count, reference style, source-media reference, provider target and safety flags.

`VideoPromptBundle` includes bundle metadata, summary, hook, script, scene table, shot table, storyboard panels, image prompts, video prompts, global negative prompt, continuity bible, render plan and export metadata.

Each shot contains at least:

- shot number, scene purpose, subject, action and environment;
- composition, camera angle, camera movement and lens;
- lighting, time of day, mood, style and color palette;
- dialogue/voice-over, on-screen text and sound direction;
- duration and aspect ratio;
- transition in/out and continuity notes;
- image prompt, video prompt and negative prompt.

Storyboard supports 6, 9, 12 and 16 panels. Multishot render planning groups two sequential shots per batch; an odd final shot remains a one-shot final batch. Manual QA with “mèo cam mập trong công viên, phong cách hoạt hình 3D dễ thương” produced a valid 9-shot bundle and five batches sized 2/2/2/2/1.

## 7. Package and billing boundary

| Package | Public | Intended use | Preview | Paid add-ons | Result |
|---|---:|---|---|---|---|
| 200 Xu | Yes | One short/default shot | Not required | None | Can reach final confirmation and provider submission without preview/add-on dependency |
| 300 Xu | Yes | Standard render | Existing final review | Guarded by existing finalization | Available only after explicit selection/confirmation |
| 400 Xu | Yes | Higher public render | Existing final review | Guarded by existing finalization | Available only after explicit selection/confirmation |
| 500+ / 600+ / premium | No | Internal/admin/history until verified | N/A | N/A | Hidden and rejected by public tier status even if stale legacy flags are enabled |

The 200 Xu package is explicitly invalid for `multi_scene_film` and any request that requires paid add-ons. The UI offers 300/400 as the upgrade path. Free/default planning still works for all prompt products.

Paid video billing sequence:

`final confirm → internal job awaiting provider → provider submit → accepted task id → wallet/package deduction → poll/fetch result`

Provider rejection before task acceptance records `provider_rejected_not_charged`; no wallet/package deduction occurs. Image billing was not changed.

## 8. Provider route and diagnostics

Public video execution remains wired to the existing ShopAIKey implementation. The status function derives submit/fetch URLs from the configured `SHOPAIKEY_VIDEO_URL`, matching the existing create and fetch code. It does not guess a replacement endpoint. Key4U remains an audited admin/alternative route and exposes its configured create/query final URLs through safe URL joining; it is not falsely reported as the selected public provider.

Admin-only commands:

- `/video_provider_status`
- `/video_provider_curl`
- `/tool_test_video_200`
- `/tool_test_video_submit` (safe diagnostic alias)
- `/tool_test_video_fetch` (safe diagnostic alias)

Status includes selected provider, base URL, submit/fetch endpoint, final URLs, enabled flags, smoke status, cost gate, last job id and a sanitized last error. cURL examples mask tokens. Missing configuration is shown as `missing endpoint`; no diagnostic command reports PASS without a task/file result. `/tool_test_video_200` is intentionally dry-run only and does not call the provider or deduct Xu.

No live paid provider request was executed during this task.

## 9. Prompt vault

The local seed contains 15 requested categories: product ad, affiliate, UGC, cinematic, cute character, horror, action, transformation, image-to-video motion, storyboard 9/12 panel, Seedance multishot, YouTube Shorts, TikTok hook and Facebook ad video.

Every record contains id, category, product, platform, style, language, prompt, negative prompt, variables, source, license note, quality score and enabled state. Runtime operations support status, refresh, keyword search, validated JSON add/import and secret-free export. Refresh is local-only; it does not scrape websites or fetch unlicensed prompt collections.

## 10. Preserved flows and protected scope

The following working roots were adapted, not rewritten:

- image slideshow/local frame video;
- self-shot/scene-change AI;
- reference video/channel analysis;
- music/voice/SFX hub;
- local video editor.

Their original internal handlers, pricing and worker/provider safeguards remain in place. Automated checks confirm their root keyboards return to `menu|main_video`.

No Task 1, Task 2 or PayOS implementation file was edited. The only provider file change adds Key4U status URL fields; it does not change submit/fetch execution.

## 11. Verification

- Registry audit: valid; 13 products; zero missing fields; zero missing/unknown menu products; zero wrong parent routes.
- Prompt bundle validation: valid; all required shot fields and safety/continuity checks pass.
- Manual storyboard QA: 9 shots; five 2-shot batches with final one-shot remainder.
- Prompt vault: 15 enabled seed categories; schema valid.
- Provider status: ShopAIKey selected; configured submit/fetch route derived from existing runtime; Key4U alternative route visible to admin only.
- Python compile: `bot.py`, `video_product_system.py`, `providers/key4u_provider.py`, `local_worker.py`.
- Automated suite: **918 passed**, one third-party Starlette deprecation warning; zero failures.
- `git diff --check`: clean (line-ending warnings only on Windows checkout).

## 12. Deferred/guarded work

- Higher tiers remain hidden until provider cost and output reliability are verified.
- No live paid smoke test was run; deployment/live QA must use a controlled admin test budget.
- Multi-scene automatic assembly remains on existing guarded routes; Task 3D adds planning/batching without pretending the provider completed a long-film job.
- Task 1 audio behavior remains governed by Task 1 readiness and should be evolved in its own task.

## 13. Task 3E recommendations

1. Run a controlled admin-only live 200 Xu provider test in staging and store submit/fetch evidence with secrets removed.
2. Add provider-webhook support if ShopAIKey/Key4U documentation guarantees signed callbacks; retain polling fallback.
3. Add persisted prompt-bundle/project records when schema migration is approved, instead of session-only drafts.
4. Open any higher package only after measured provider cost, success rate, duration and output-quality gates pass.
5. Add Telegram integration tests against a test bot for callback expiry, document export and Back navigation; current tests use deterministic handlers/markup without sending production messages.
