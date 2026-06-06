# TOAN AAS Legal Risk Register

TOAN AAS current public bot is a Stable Revenue Tool Bot: AI tools, Video Factory Lite, service credits, PayOS/manual fallback, promo/gift, and customer self-post content packs.

This register defines legal guardrails before opening larger platform modules.

| Module | Status | Main risks | Rules before opening |
|---|---|---|---|
| Bot AI tools | Public V1 | Wrong output, unsafe advice, user misuse | User must review output; no guarantee of accuracy, revenue, virality, ad approval, or legal/financial result. |
| Xu service credits/payment | Public V1 | Misunderstood as money, e-money, digital asset, transfer value | Service credits only; no withdrawal, no transfer, no outside payment value, no user trading. |
| Image/video/voice tools | Public V1 / limited by provider readiness | Copyright, privacy, deepfake, consent, harmful edits | Reject risky requests; require user-owned or authorized content; no impersonation or harmful deepfake. |
| Music/audio/media tools | Public V1 / admin-test for rendering | Copyright, music license, attribution, commercial-use limits, artist imitation, voice clone misuse | Do not create artist/song clones; require license checks for Jamendo/Freesound/Pixabay/external media; rendering/AI music remains provider-ready/admin-tested before public use. |
| Downloader | Limited | Reup/copyright/bypass platform protection | Use only for user-owned/authorized content; public downloader provider may remain disabled for safety. |
| Affiliate content | Customer self-post only | Undisclosed commissions, exaggerated claims, prohibited goods | Require affiliate disclosure and truthful claims; no fake reviews or restricted products. |
| Admin publish | Future admin-first | Account permission, platform policy, accidental posting | Admin-owned/authorized accounts only; approval gate, audit log, risk check, failure handling. |
| Customer publish | OFF | Social account permissions, privacy, OAuth, unauthorized posting | OFF until legal/privacy/OAuth review, revoke flow, pricing, audit log, and explicit admin approval. |
| Ads assistant | OFF / future admin-first | Policy violations, ad disapproval, card/password risk, revenue claims | No auto ad launch; no passwords/cards; policy checker; admin approval; no revenue guarantee. |
| Dashboard/SaaS | Future | Data exposure, role access, operational risk | Role-based access, audit logs, privacy notices, secure data handling. |
| App riêng | Future | App store/privacy compliance, payment flow, user data | Separate privacy terms, secure auth, payment and data review before release. |
| Affiliate marketplace | Future | Product claims, commission disclosure, tracking data | Disclosure rules, product vetting, transparent tracking and opt-out where applicable. |
| ERP/Automation/Device Ops | Backlog | Operational damage, device access, automation mistakes | Sandbox first, admin-only, explicit scope, audit logs, no production device access without approval. |

## Standing Rules

- Customer publish: OFF until legal/privacy/OAuth approval.
- Ads automation: OFF until admin approval and policy checker.
- Social token storage: OFF until encryption, privacy terms, revoke flow, and audit logs exist.
- Downloader public use is limited to user-owned or authorized content.
- Affiliate content should include disclosure when a link/commission is involved.
- Service credits have no withdrawal, no transfer, and no outside payment value.
- No password collection.
- No payment card collection through the bot.
- No automatic publishing or ad launch without approval.

## Music, Audio, Media And Copyright Policy

1. TOAN AAS supports music prompts, background music search, sound effect search, public media search, and audio preparation for video workflows.
2. Users must not request or use music that imitates a copyrighted artist, singer, song, melody, beat, arrangement, vocal style, or music brand.
3. Users must not use TOAN AAS for unauthorized covers/remixes, voice cloning, copyright evasion, or reuploading content without usage rights.
4. Sources such as Jamendo, Freesound, Pixabay, or external libraries have item-specific licenses. Users are responsible for checking license terms, attribution requirements, commercial-use limits, and platform rules before posting.
5. TOAN AAS does not guarantee that every third-party music/media file is valid for every commercial purpose or platform.
6. AI music generation, audio/video enhancement, and music-to-video rendering may have separate Xu costs and are not unlimited services.
7. If a provider fails, lacks a configured key, or processing fails, the bot must not charge Xu, or must refund Xu if it already charged before the failure.
8. TOAN AAS may reject, block, or remove content that appears to violate copyright, imitate artists, or mislead viewers.
9. Users are legally responsible if they use music/media under the wrong license or violate third-party rights.
