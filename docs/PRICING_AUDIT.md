# PRICING AUDIT - TOAN AAS

Date: 2026-06-02
Scope: Phase 1 Step 10, Pricing Engine V2.

## Current constants

| Constant | Current value | Used by |
|---|---:|---|
| `PRICING_MARKUP_MULTIPLIER` | 3 | Admin pricing docs and strategy. |
| `FILM_SCRIPT_COST` | 200 Xu | `/film` basic floor and help text. |
| `GROWTH_AI_COST` | 120 Xu | `/growth_ai`. |
| `CAMPAIGN_REPORT_COST` | 50 Xu | `/campaign_report`, `/export_report`. |
| `VIDEO_BASIC_COST` | 200 Xu | `/film` basic. |
| `VIDEO_PRO_COST` | 500 Xu | `/film tier=pro`. |
| `VIDEO_SERIES_COST` | 1,200 Xu | `/film tier=series`. |
| `AUDIO_MIN_COST` | 80 Xu | STT/audio MB pricing. |
| `VIDEO_DOWNLOAD_MIN_COST` | 100 Xu | Downloader MB pricing. |
| `IMAGE_REMOVE_BG_BASE_COST` | 80 Xu | Economy background removal. |
| `IMAGE_REMOVE_BG_PREMIUM_COST` | 150 Xu | Premium background removal. |
| `VOICE_BASE_COST` | 50 Xu | Economy voice/TTS. |

## Hardcoded costs

| Location | Current cost | Risk |
|---|---:|---|
| `/film` | Calculated by `calculate_film_cost()` | Low; supports basic/pro/series and extra episodes/scenes. |
| `/growth_ai` | `GROWTH_AI_COST` | Low; no data means no charge, AI error refunds. |
| `/campaign_report` | `CAMPAIGN_REPORT_COST` | Medium; report export now charges after data exists and refunds on export error. |
| Provider choice voice/image | `VOICE_FREE_COST`, `IMAGE_FREE_COST`, dynamic premium cost | Medium; labels still say economy/premium but pricing is now higher. |

## MB-based tools

| Tool | Current pricing | Needs MB pricing? |
|---|---|---:|
| STT/audio | `calculate_audio_cost(size_bytes)` | YES, implemented. |
| Downloader/video | `calculate_video_download_cost(size_bytes)` | YES, implemented. |
| Image background removal | Base/premium fixed pricing | Future per-MB option can be added if provider cost requires it. |
| Voice/TTS | `calculate_voice_cost()` by character blocks | Character-based, not MB-based. |

## Recommendations

1. Keep default prices high and use percentage promotions instead of lowering base prices.
2. Run PayOS real test before selling paid report/export features.
3. Review real provider dashboards weekly and adjust constants only after data.
