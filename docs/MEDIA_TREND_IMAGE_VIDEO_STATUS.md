# TOAN AAS Media, Trend, Image, Video Status

Current phase: Stable Revenue Bot. This document records what can be shown to customers now and what must remain admin-only/backlog.

## Ready For Customers

These tools are content-only or prompt-only and do not call expensive media generation providers:

- `/trend_ai <topic>`: AI-suggested trend angles. Not live/realtime data.
- `/trend_research <topic>`: manual trend research checklist.
- `/image_tools`: customer-facing image tool menu.
- `/image_prompt <topic>`: realistic image prompt pack.
- `/image_to_video_pack <topic>`: image-to-video prompt pack.
- `/film <topic>` or `/video_script <topic>`: video script/content pack.
- `/media_factory <topic>`: script, storyboard, image prompt, video prompt, caption, hashtag, CTA.
- `/video_factory_flow`: explains the current safe workflow.
- `/source_help`: lawful source guidance.
- `/dubbing_help`: lawful dubbing/voice-over guidance.
- `/story_video_factory <topic>`: story video workflow prompt plan.
- `/story_motion_prompt <scene>`: motion prompt only.

## Disabled Or Admin-First

These features must not be sold as public working tools yet:

- `/trend_live <topic>`: disabled/provider missing. It must not fake "latest" trend data.
- `/ai_image <prompt>`: disabled unless `ENABLE_OPENAI_IMAGE=1` and admin release gate allows testing.
- `/ai_image_edit <instruction>`: disabled unless `ENABLE_OPENAI_IMAGE_EDIT=1` and admin release gate allows testing.
- Real video generation: disabled/planned; provider not selected.
- Customer publishing: off.
- Auto publish: off.
- Ads assistant: off.
- Downloader public use: off unless self-hosted provider is tested.

## Provider Notes

- Configured does not mean working.
- A provider becomes ready only after admin smoke tests pass and the tool has price/refund/rate-limit rules.
- Trend Live requires a future search/trend provider such as Google Trends unofficial, SerpAPI, DataForSEO, Tavily, Brave Search, YouTube Data API, or another approved source.
- AI Image requires OpenAI image provider testing and cost control.
- Real video generation requires a separate provider decision and admin-first cost/quota testing.
- Cobalt public API is not for customer production. Use self-hosted Cobalt or an approved provider.

## Copyright And Source Rules

Allowed sources:

- Customer-owned media.
- Self-created script, image, voice and video.
- Public domain materials.
- Licensed media.
- Materials with explicit permission.

Not allowed:

- Reuploading content without permission.
- Bypassing watermark, DRM, Content ID or platform protection.
- Cloning a real person's voice/image without permission.
- Making guaranteed revenue, medical, financial or legal claims without review.

## Admin Test Commands

- `/feature_status`
- `/feature_set FEATURE STATUS` owner-only
- `/providers`
- `/tool_status`
- `/tool_audit`
- `/tool_test_ai_image`
- `/tool_test_ai_image_edit`
- `/tool_test_image`
- `/tool_test_downloader`
- `/video_provider_status`
- `/trend_status`

## Current Rule

Customer-facing bot V1 provides content/video packs for customers to self-post. Trend live, real AI image/video generation, publishing and ads stay admin-first until explicitly approved.
