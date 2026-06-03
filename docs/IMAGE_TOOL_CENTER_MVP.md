# Image Tool Center MVP

## Scope

TOAN AAS is a practical AI tool center inside Telegram. The current customer-facing scope is stable revenue tooling: daily AI tools, Video & Media Factory, Xu billing, PayOS/manual fallback, promo/gift flows, and customer self-posting.

## Video & Media Factory

Video & Media Factory includes:

- Script and storyboard packs.
- Realistic image prompt packs.
- Image-to-video prompt packs.
- Captions, hashtags and CTA.
- Manual content packs for Facebook, TikTok and YouTube Shorts.

The bot does not auto-publish for public customers. Customers receive content/video packs and post them themselves.

## Why Not Only ChatGPT/OpenAI Image

ChatGPT/OpenAI image generation and editing are useful but can cost more and should not be enabled blindly. TOAN AAS keeps cheaper prompt-pack tools available first, so customers can get high-quality prompts without burning paid image API quota.

OpenAI image generation and editing stay OFF by default until admin explicitly enables the provider flags.

## Customer Commands

- `/image_tools` - show available image tools.
- `/image_prompt <topic>` - generate a realistic 6-prompt image pack.
- `/image_to_video_pack <topic>` - generate a video prompt pack from a topic.
- Reply to an image with `/image_to_video_pack` - generate a video prompt pack from the replied image context.
- `/ai_image <description>` - generate an AI image only when OpenAI image generation is enabled.
- Reply to an image with `/ai_image_edit <instruction>` - edit an image only when OpenAI image edit is enabled.

## Pricing

- `/image_prompt`: 80 Xu.
- `/image_to_video_pack`: 120 Xu.
- `/ai_image`: 300 Xu, only when provider is enabled.
- `/ai_image_edit`: 350 Xu, only when provider is enabled.

If OpenAI image generation or edit is disabled, the bot does not charge Xu and suggests `/image_prompt` first.

## Feature Flags

- `image_tools = 1`
- `image_prompt_factory = 1`
- `image_to_video_prompt = 1`
- `image_openai_generation = 0`
- `image_openai_edit = 0`

## Safety Rules

- No customer auto publish.
- No customer social account connection.
- No ad launch automation.
- No OpenAI image API call while its feature flag is OFF.
- No secrets are shown in `/providers`.
