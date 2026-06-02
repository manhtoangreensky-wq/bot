# TOAN AAS Master Goal Plan V4 - Codex Ready

This document is the Codex-ready backlog pointer for the TOAN AAS V4 master goal.

Current production priority remains the Stable Revenue Bot:

- AI daily tools.
- Video Factory Lite / content packs.
- PayOS and manual Xu top-up.
- Promo, gift, launch bonus.
- Customer self-posting only.

Do not implement future platform publishing, ads, affiliate vault, customer account connection, or social automation in the public customer bot until the Stable Revenue Bot is confirmed stable and admin explicitly approves the next phase.

## Future Admin-First Trend-to-Video-to-Publish Pipeline

Future workflow name:
TOAN AAS Admin Trend-to-Video-to-Publish Pipeline.

Long-term goal:
TOAN AAS will support an admin-first pipeline where Admin can find trends, generate AI video content, review the output and publish only after approval.

Workflow:
Trend Finder -> Trend Scoring -> Script/Context -> Scene Prompts -> AI Video Tasks -> Voice/TTS -> Captions/Hashtags/CTA -> Risk Check -> Admin Approval -> Publish Queue -> Platform Publish -> Performance Tracking -> Growth Feedback.

Original long-term workflow:
1. Admin clicks or runs Trend Finder.
2. Bot finds trending topics, products and content angles.
3. Bot scores trend potential.
4. Bot chooses or suggests the best trend.
5. Bot generates context, angle, audience, hook and script.
6. Bot generates video prompts and scenes automatically.
7. Bot generates AI video assets or video generation tasks.
8. Bot generates voice-over/TTS.
9. Bot combines or prepares video package.
10. Bot generates captions, hashtags, CTA and platform-specific outputs.
11. Bot sends the complete draft package to Admin.
12. Admin reviews.
13. Admin approves, rejects or requests rewrite.
14. Only after Admin approval can the system publish/post to social platforms.
15. After posting, bot stores published URL and performance data.
16. Performance feeds back into Growth AI and Trend Finder.

Current status:
This is a future/admin-first workflow. It must not be exposed to public customers in the current Stable Revenue Bot.

Customer-facing bot V1 only provides content/video packs for customers to self-post.

Current bot V1:
- Customers can use AI tools.
- Customers can create script, prompt, caption, storyboard and content pack.
- Customers self-post.
- No public auto publish.
- No public trend-to-post automation.
- No customer social account connection.
- No ads management for customers.

Future admin workflow modules:
- Admin Trend Finder.
- Admin Trend Scoring.
- Admin AI Video Builder.
- Admin Voice Builder.
- Admin Caption/Hashtag/CTA Generator.
- Admin Review Gate.
- Admin Approval Queue.
- Admin Publish Queue.
- Admin Platform Account Manager.
- Admin Publish Logs.
- Admin Performance Tracker.

Feature flags:
- `trend_finder = admin only`
- `ai_video_builder = admin only`
- `admin_publish = admin only`
- `customer_publish = off by default`
- `auto_publish = off by default`
- `ads_assistant = off by default`

Required safety:
- No automatic publishing without approval.
- Every generated video/post must go through approval gate.
- Every publish action must have audit log.
- Every platform account connection must be admin-owned or explicitly authorized.
- No password collection.
- No payment card collection.
- No customer publish access until admin manually enables it later.
- Failed publish must not retry endlessly.
- Risk checker must run before publish.

Pipeline stages:
1. `trend_scan`
2. `trend_score`
3. `angle_select`
4. `script_generate`
5. `scene_prompt_generate`
6. `video_generate_task`
7. `voice_generate`
8. `assemble_or_export`
9. `platform_output_generate`
10. `risk_check`
11. `admin_review`
12. `admin_approve`
13. `publish_queue`
14. `publish_execute`
15. `performance_track`
16. `growth_ai_feedback`

Admin-first rollout:
1. Build inside admin/internal interface.
2. Test only with admin-owned accounts/pages/channels.
3. Keep customer access disabled.
4. Require admin approval before every post.
5. Keep audit logs for every action.
6. Only open to customers later if admin approves and pricing/package is defined.

Ads:
Ads is optional and separate. Publishing organic video is the main future workflow. Ads Assistant may be added only if customers need it and TOAN AAS has clear rules, fees and permission model.

Important:
Keep affiliate vault, trend finder, publish workflow and video posting tools as admin/internal modules first. Do not expose these to customers in the current public bot. Only after admin tests successfully can admin decide whether to open it as a paid customer feature.
