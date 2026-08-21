# Social Platform Capability & Authorization Matrix

| Platform | Mode | Required API / Product | Capability State |
| :--- | :--- | :--- | :--- |
| **Telegram** | Bot Admin | Telegram Bot API | `READY` |
| **Facebook Pages** | Page Post | Meta Pages API | `READY` / `NEEDS_OAUTH` |
| **Instagram Pro** | Business Publish | Instagram Graph API | `READY` / `NEEDS_OAUTH` |
| **YouTube** | Video Upload | YouTube Data API v3 | `NEEDS_OAUTH` |
| **TikTok** | Direct Post | TikTok Content Posting API | `NEEDS_APP_REVIEW` |

## Security & Isolation
- All OAuth tokens and refresh tokens are encrypted at rest with server-side keys.
- Plaintext secrets are never displayed in customer UI or logged.
