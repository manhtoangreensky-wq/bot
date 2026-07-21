# P0.17B14 Video Flow Contract Audit

Date: 2026-06-27

Scope: B14 profile brain, asset-first storyboard, prompt continuity, B13 render handoff, and FFmpeg postprocess.

Non-goals: no PayOS/wallet/payment changes, no render provider rewrite, no B13 stitch rewrite, no music/Suno core changes, no public preview/test generation.

## Shared 8-Step Flow

All 12 profiles use the same product flow:

1. Planning / idea, free: create draft project, return text-only packaged suggestions.
2. Asset/image preparation: store reference assets only.
3. Optimize video prompt: build StoryBible, scene cards, continuity prompts as text.
4. Add-on configuration: store add-on plan only.
5. Quality/package gate: select package; 200 Xu disables add-ons for that invoice.
6. Scene count / scale: choose scene count; public max can be guarded by env.
7. Final invoice and confirm: show one final bill; no provider, no Xu, no file before confirm.
8. Background rendering and delivery: after confirm only, render video, create add-ons, postprocess, send one final MP4.

Public users must see no "tao thu", "xem thu", "render thu", "demo generation", "preview render", provider/API/FFmpeg/debug text, or admin test tools.

Admin-only slash tests remain hidden from public keyboards and must be treated as ADMIN TEST MODE.

## Profile Audit

### storytelling

- Menu label: Video kể chuyện
- Script formula: 3-act Hook -> rising action/conflict -> twist/resolution/open ending
- Required/optional assets: idea/story; optional character, background, style, voice, music, logo
- 3 scenes: hook, conflict, ending
- 5 scenes: hook, setup, conflict, proof, ending
- Add-on defaults: emotional voice, soft/intense/soft music, readable captions, subtle logo
- Shared flow: yes
- Public "tao thu" button: no
- Render before confirm: no
- Add-ons postprocess after final MP4: yes

### product_review

- Menu label: Video review sản phẩm / affiliate
- Script formula: AIDA/PAS
- Required/optional assets: product/offer; optional product/object refs, logo, brand color, music, voice
- 3 scenes: pain point, product reveal, benefit/CTA
- 5 scenes: hook, problem, reveal, proof, CTA
- Add-on defaults: energetic voice, upbeat low music, punchy captions, ending logo
- Shared flow: yes
- Public "tao thu" button: no
- Render before confirm: no
- Add-ons postprocess after final MP4: yes

### news

- Menu label: Video tin tức
- Script formula: 5W1H
- Required/optional assets: news text/topic; optional article text, background/news image, style, logo
- 3 scenes: headline, key facts, impact
- 5 scenes: headline, who/what, where/when, why/how, impact
- Add-on defaults: neutral anchor voice, light news music, clean lower-third, factual policy
- Shared flow: yes
- Public "tao thu" button: no
- Render before confirm: no
- Add-ons postprocess after final MP4: yes

### philosophy_quotes

- Menu label: Video triết lý / đạo lý / quotes
- Script formula: quote hook -> pause -> explanation -> emotional ending
- Required/optional assets: quote/message; optional background/style/voice/music/logo
- 3 scenes: quote hook, pause/reflection, meaning
- 5 scenes: visual hook, quote, reflection, explanation, ending
- Add-on defaults: slow reflective voice, lofi/ambient, elegant captions, subtle/no logo
- Shared flow: yes
- Public "tao thu" button: no
- Render before confirm: no
- Add-ons postprocess after final MP4: yes

### educational

- Menu label: Video kiến thức
- Script formula: ELI5
- Required/optional assets: topic/question; optional style/background/logo/voice/music
- 3 scenes: concept hook, explanation, summary
- 5 scenes: question, definition, example, process, summary
- Add-on defaults: teacher voice, low lofi/corporate music, bullet captions, small logo
- Shared flow: yes
- Public "tao thu" button: no
- Render before confirm: no
- Add-ons postprocess after final MP4: yes

### history

- Menu label: Video lịch sử
- Script formula: context -> event -> turning point -> consequence -> lesson
- Required/optional assets: historical topic/facts; optional background/style/logo/voice/music
- 3 scenes: context, turning point, consequence
- 5 scenes: context, figure/event, turning point, result, lesson
- Add-on defaults: epic narration, solemn music, classic lower-third, strict fact policy
- Shared flow: yes
- Public "tao thu" button: no
- Render before confirm: no
- Add-ons postprocess after final MP4: yes

### ugc_affiliate

- Menu label: Video Affiliate / UGC bán hàng
- Script formula: Problem -> Solution -> Personal experience -> CTA
- Required/optional assets: product info/image; optional product/person/existing video/logo/music
- 3 scenes: relatable pain, product use, result/CTA
- 5 scenes: hook, problem, reveal, proof, CTA
- Add-on defaults: excited UGC voice, viral music at low volume, popup captions, transition SFX cue
- Shared flow: yes
- Public "tao thu" button: no
- Render before confirm: no
- Add-ons postprocess after final MP4: yes

### real_estate_fpv

- Menu label: Video bất động sản / địa điểm / FPV tour
- Script formula: Location -> specs -> experience -> value -> contact/CTA
- Required/optional assets: location/property description; optional background/property/map/logo/music
- 3 scenes: exterior, walkthrough, value/contact
- 5 scenes: location, exterior, interior, amenities, contact
- Add-on defaults: calm narrator, luxury lounge music, minimal lower-third, spec overlays after postprocess
- Shared flow: yes
- Public "tao thu" button: no
- Render before confirm: no
- Add-ons postprocess after final MP4: yes

### fashion_lookbook

- Menu label: Video thời trang / lookbook
- Script formula: short keyword hook -> style keyword -> highlight -> CTA
- Required/optional assets: fashion item/style; optional model/clothing/style/music/logo
- 3 scenes: outfit hook, detail close-up, full look/CTA
- 5 scenes: brand hook, look 1, detail, look 2, CTA
- Add-on defaults: usually no voice, beat music, short keyword flashes, logo at final pose
- Shared flow: yes
- Public "tao thu" button: no
- Render before confirm: no
- Add-ons postprocess after final MP4: yes

### food_asmr

- Menu label: Video ẩm thực / ASMR
- Script formula: sensory hook -> texture -> taste -> craving/CTA
- Required/optional assets: dish/drink or food image; optional logo/music/SFX
- 3 scenes: food hook, texture close-up, taste/CTA
- 5 scenes: hook, prep, sizzle/pour, bite, craving
- Add-on defaults: ASMR/reviewer voice, low cozy music, tasty popup captions, SFX cues only if assets exist
- Shared flow: yes
- Public "tao thu" button: no
- Render before confirm: no
- Add-ons postprocess after final MP4: yes

### lofi_audio_visualizer

- Menu label: Video nhạc chill / lofi / audio visualizer
- Script formula: mood -> optional lyric hook -> loop
- Required/optional assets: mood/music/lyrics/audio; optional style, character, background
- 3 scenes: mood, variation/lyric hook, seamless return
- 5 scenes: intro, verse, hook, bridge, loop return
- Add-on defaults: no voice by default, lofi music, karaoke captions if lyrics, loop extension postprocess only
- Shared flow: yes
- Public "tao thu" button: no
- Render before confirm: no
- Add-ons postprocess after final MP4: yes

### cinematic_trailer

- Menu label: Phim ngắn AI / cinematic trailer
- Script formula: setup -> incident -> escalation -> climax glimpse -> title/CTA
- Required/optional assets: film idea/story; optional characters, locations, style, voice, music, logo/title card
- 3 scenes: world, conflict, climax/title
- 5 scenes: world, character, incident, escalation, title
- Add-on defaults: deep trailer voice, epic music, minimal cinematic subtitles, letterbox/color-grade postprocess policy
- Shared flow: yes
- Public "tao thu" button: no
- Render before confirm: no
- Add-ons postprocess after final MP4: yes

## Public Copy Audit

- Text-only storyboard preview: allowed.
- Text-only prompt preview: allowed.
- Invoice/bill preview: allowed.
- Asset/add-on summary: allowed.
- Provider render preview: forbidden.
- TTS/music/subtitle/FFmpeg before confirm: forbidden.
- Admin slash tests: hidden from public keyboards.

## State Machine / Worker Queue Audit

### video_projects

- Added persistent SQLite project state for the shared 8-step video flow.
- Statuses: draft_planning, draft_assets, draft_prompt, draft_addons, draft_quality, draft_scene_count, draft_invoice, queued_for_worker, processing, completed, failed, cancelled.
- Stores profile_id, topic, ratio, selected suggestion JSON, asset pack JSON, story bible JSON, scene cards JSON, prompt text, add-on plan JSON, quality tier, scene count, invoice JSON, estimated Xu, confirmation flags, final video info, and timestamps.
- All 12 profiles use this same table and state sequence; profile-specific behavior is limited to script formula, scene roles, style, and add-on defaults.

### video_scenes

- Added persistent scene rows keyed by project_id and scene_index.
- Stores role, script/subtitle line, image/video prompt, reference asset IDs, output paths, and scene_status.
- Scene statuses: pending, gen_audio, gen_image, gen_video, postprocess, done, failed.

### video_jobs

- Existing `video_jobs` table was adapted non-destructively instead of recreated because the repo already used it for operator/campaign jobs.
- Added queue fields for project_id, user_id, job_type, priority, attempts, max_attempts, locked_by, locked_at, lease_expires_at, last_error, result_json, started_at, completed_at, and updated_at.
- New render rows use `job_type='video_render'`; older campaign rows remain untouched.
- Added one-active-render-job guard by unique partial index on project_id/job_type while status is queued or processing.

### Bot responsibilities

- Bot creates/updates video_projects during draft planning.
- Bot stores storyboard/scene cards into video_projects/video_scenes.
- Bot confirms invoice only from draft_invoice.
- Bot can call the existing wallet deduction policy at final confirm.
- Bot sets project status to queued_for_worker and inserts one queued video_jobs row.
- Bot returns immediately; it does not render, call providers, call FFmpeg, TTS, music, subtitle, or public preview/test render before final confirm.

### Worker responsibilities

- local_worker.py now has a separate video project queue poll path: `/internal/video_worker/poll`.
- Poll claims one `video_jobs` row atomically from queued to processing with a lease.
- Stale processing jobs with expired leases are requeued when attempts remain.
- Completed jobs are marked completed and are not claimed again.
- Failure retries until max_attempts, then marks both job and project failed.
- Worker delivery updates the project/job through `/internal/video_worker/job_update`.

### Explicit queue constraints

- SQLite queue first: yes.
- Celery: no.
- Redis/RQ: no.
- FastAPI BackgroundTasks for render: no.
- Telegram webhook long render blocking: no.
- Non-destructive migration: yes.
- Public render before invoice confirm: no.

## Conclusion

All 12 profiles share one pipeline:

VideoProductProfile -> VideoAssetPack -> StoryBible -> SceneCard -> continuity prompts -> video_projects/video_scenes -> confirmed video_jobs queue -> B13 renderer -> FFmpeg postprocess -> final MP4.

The profile changes only planning/storyboard/prompt defaults. Rendering, stitching, billing confirmation, and final delivery remain shared.
