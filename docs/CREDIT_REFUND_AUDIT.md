# CREDIT REFUND AUDIT

| Flow | Deduct before API? | Refund on error? | Risk | Fix |
|---|---|---|---|---|
| Chat AI | Yes for paid users | Partial/Need manual verification | If AI throws after deduct, current handler may not refund in every exception path. | Next task should wrap paid chat call with refund on exception. |
| Trial chat | No | Not needed | Trial quota can run out and should upsell. | Added topup buttons when free chat is exhausted. |
| Voice provider selection | No after this pass | Yes in provider flows | User could previously be blocked by premium cost before choosing cheap voice. | Fixed to require only minimum cheap voice cost before provider selection. |
| Voice premium | Yes at provider choice | Yes | Provider quota can fail. | Existing fallback/refund retained. |
| STT/audio | Yes | Yes | Need real Deepgram failure test. | Existing refund retained; missing Xu now shows topup buttons. |
| Image provider selection | No | Yes in provider flows | User could previously be blocked by premium cost before choosing cheap image. | Fixed to require only minimum cheap image cost before provider selection. |
| Image premium | Yes at provider choice | Yes | Provider quota can fail. | Existing fallback/refund retained. |
| Downloader | Yes | Yes in key failure branches | External downloader can block/private/link fail. | Existing refund retained; missing Xu now shows topup buttons. |
| Video/script/operator | Mixed | Need manual verification | Large internal workflows are not the current revenue-bot priority. | Keep gated; do not expand in this task. |

## Current changes

- Added shared topup keyboard for common insufficient-Xu paths.
- Applied to trial chat exhausted, paid chat insufficient, STT insufficient, voice minimum cost, download insufficient, and image minimum cost.
- Preserved `pkg|` callback format.
- Preserved `prov|` callback format.

## Remaining TODO

- Wrap paid Chat AI call with a focused refund-on-exception patch.
- Audit every operator/video command that deducts credits before expanding Video Script Lite.
- Add tests around insufficient credits response if Telegram objects are mocked.

