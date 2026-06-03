# TOAN AAS Legal Risk Register

TOAN AAS current public bot is a Stable Revenue Tool Bot: AI tools, Video Factory Lite, service credits, PayOS/manual fallback, promo/gift, and customer self-post content packs.

This register defines legal guardrails before opening larger platform modules.

| Module | Status | Main risks | Rules before opening |
|---|---|---|---|
| Bot AI tools | Public V1 | Wrong output, unsafe advice, user misuse | User must review output; no guarantee of accuracy, revenue, virality, ad approval, or legal/financial result. |
| Xu service credits/payment | Public V1 | Misunderstood as money, e-money, digital asset, transfer value | Service credits only; no withdrawal, no transfer, no outside payment value, no user trading. |
| Image/video/voice tools | Public V1 / limited by provider readiness | Copyright, privacy, deepfake, consent, harmful edits | Reject risky requests; require user-owned or authorized content; no impersonation or harmful deepfake. |
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
