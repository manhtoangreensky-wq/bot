# TOAN AAS Key4U Cost And Product Matrix

Date: 2026-06-20

## Status

Draft cost matrix only. It is not imported by runtime and does not change prices.

## Product Mapping

| Product area | Primary today | Key4U role | Public state |
| --- | --- | --- | --- |
| Chat AI | existing router/OpenRouter/OpenAI/Gemini paths | backup/admin smoke | OFF |
| Vision chat | existing guarded flow | backup if vision model configured | OFF |
| AI image edit | existing guarded flow | candidate provider for real edit | OFF until smoke/cost pass |
| Video AI | ShopAIKey controlled video path | backup async video candidate | OFF until smoke/cost pass |
| TTS/STT/Suno/Rerank | existing providers/local guards | `NEED_DOCS` placeholders | OFF |

## Cost Policy

- Do not use Key4U publicly without exact provider cost.
- Do not sell unknown endpoints as customer-ready.
- Keep WokuShop parked due higher cost.
- Keep 200 Xu video as marketing starter per current product policy, not a profit tier.

## Required Before Public Use

1. Run admin smoke.
2. Record real cost/usage from dashboard or API.
3. Set manual balance if no usage API exists.
4. Update pricing matrix.
5. Open only the specific capability that passed.
