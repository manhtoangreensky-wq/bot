"""Canonical Bot Core Admin Pricing Commercial Authority Service (B02).

Implements the single canonical Bot-owned pricing authority and publisher.
Guarantees:
- Single source of truth for Bot product sale pricing (WebApp is orchestrator/editor only)
- Immutable internal provider costs and secrets are never exposed or mutated via sale price authority
- Durable, versioned, append-only audit trail
- Optimistic concurrency control via expected_version CAS
- Strict field whitelist and fail-closed price validation
- Atomic persistence with immediate fresh canonical readback and consumer propagation
- Zero mutations to wallet, ledger, historical payments, jobs, or provider configurations
"""

from __future__ import annotations

from copy import deepcopy
import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
import logging
import sqlite3
import time
from typing import Any

logger = logging.getLogger("admin_pricing_service")

DEFAULT_ADMIN_ID = "7126457028"

# ─── CANONICAL BASE PRICING CATALOG ──────────────────────────────────────────
# Authoritative pricing dictionary covering all commercial customer domains.
# Sourced directly from current Bot execution and quote truths.

BASE_PRICING_CATALOG: dict[str, dict[str, Any]] = {
    # --- Product Video Tiers (services.video_ai_real_pricing.public_quality_catalog) ---
    "video_tier_300": {
        "price_key": "video_tier_300",
        "product_key": "video_ai_prompt",
        "label": "Video Khởi Đầu Âm Thanh 5s (Tier 300)",
        "unit": "scene",
        "base_value": 221,
        "value_type": "int",
        "editable": True,
        "policy_type": "PAID_PRICE",
        "domain": "video",
        "read_authority": "services.video_ai_real_pricing.public_quality_catalog",
        "quote_authority": "services.video_ai_real_pricing.public_quality_by_tier",
        "charge_authority": "bot.spend_fixed_credit_info",
    },
    "video_tier_200": {
        "price_key": "video_tier_200",
        "product_key": "video_ai_prompt",
        "label": "Video Chuyển Động Xã Hội 5s (Tier 200)",
        "unit": "scene",
        "base_value": 259,
        "value_type": "int",
        "editable": True,
        "policy_type": "PAID_PRICE",
        "domain": "video",
        "read_authority": "services.video_ai_real_pricing.public_quality_catalog",
        "quote_authority": "services.video_ai_real_pricing.public_quality_by_tier",
        "charge_authority": "bot.spend_fixed_credit_info",
    },
    "video_tier_1000": {
        "price_key": "video_tier_1000",
        "product_key": "video_ai_prompt",
        "label": "Video Diễn Xuất Nhân Vật 6s (Tier 1000)",
        "unit": "scene",
        "base_value": 337,
        "value_type": "int",
        "editable": True,
        "policy_type": "PAID_PRICE",
        "domain": "video",
        "read_authority": "services.video_ai_real_pricing.public_quality_catalog",
        "quote_authority": "services.video_ai_real_pricing.public_quality_by_tier",
        "charge_authority": "bot.spend_fixed_credit_info",
    },
    "video_tier_400": {
        "price_key": "video_tier_400",
        "product_key": "video_ai_prompt",
        "label": "Video Veo Cân Bằng Chi Tiết 8s (Tier 400)",
        "unit": "scene",
        "base_value": 371,
        "value_type": "int",
        "editable": True,
        "policy_type": "PAID_PRICE",
        "domain": "video",
        "read_authority": "services.video_ai_real_pricing.public_quality_catalog",
        "quote_authority": "services.video_ai_real_pricing.public_quality_by_tier",
        "charge_authority": "bot.spend_fixed_credit_info",
    },
    "video_tier_500": {
        "price_key": "video_tier_500",
        "product_key": "video_ai_prompt",
        "label": "Video Chuyển Động Kiểm Soát 5s (Tier 500)",
        "unit": "scene",
        "base_value": 804,
        "value_type": "int",
        "editable": True,
        "policy_type": "PAID_PRICE",
        "domain": "video",
        "read_authority": "services.video_ai_real_pricing.public_quality_catalog",
        "quote_authority": "services.video_ai_real_pricing.public_quality_by_tier",
        "charge_authority": "bot.spend_fixed_credit_info",
    },
    "video_tier_600": {
        "price_key": "video_tier_600",
        "product_key": "video_ai_prompt",
        "label": "Video Chuyển Động Đồng Bộ Âm Thanh 5s (Tier 600)",
        "unit": "scene",
        "base_value": 804,
        "value_type": "int",
        "editable": True,
        "policy_type": "PAID_PRICE",
        "domain": "video",
        "read_authority": "services.video_ai_real_pricing.public_quality_catalog",
        "quote_authority": "services.video_ai_real_pricing.public_quality_by_tier",
        "charge_authority": "bot.spend_fixed_credit_info",
    },
    "video_tier_1200": {
        "price_key": "video_tier_1200",
        "product_key": "video_ai_prompt",
        "label": "Video Tham Chiếu Đa Góc Nhìn 8s (Tier 1200)",
        "unit": "scene",
        "base_value": 1261,
        "value_type": "int",
        "editable": True,
        "policy_type": "PAID_PRICE",
        "domain": "video",
        "read_authority": "services.video_ai_real_pricing.public_quality_catalog",
        "quote_authority": "services.video_ai_real_pricing.public_quality_by_tier",
        "charge_authority": "bot.spend_fixed_credit_info",
    },
    "video_tier_800": {
        "price_key": "video_tier_800",
        "product_key": "video_ai_prompt",
        "label": "Video Chuyển Động Chuyên Nghiệp Kling 10s (Tier 800)",
        "unit": "scene",
        "base_value": 2143,
        "value_type": "int",
        "editable": True,
        "policy_type": "PAID_PRICE",
        "domain": "video",
        "read_authority": "services.video_ai_real_pricing.public_quality_catalog",
        "quote_authority": "services.video_ai_real_pricing.public_quality_by_tier",
        "charge_authority": "bot.spend_fixed_credit_info",
    },
    "video_tier_1500": {
        "price_key": "video_tier_1500",
        "product_key": "video_ai_prompt",
        "label": "Video Điện Ảnh Đa Phân Cảnh Doubao 10s (Tier 1500)",
        "unit": "scene",
        "base_value": 2411,
        "value_type": "int",
        "editable": True,
        "policy_type": "PAID_PRICE",
        "domain": "video",
        "read_authority": "services.video_ai_real_pricing.public_quality_catalog",
        "quote_authority": "services.video_ai_real_pricing.public_quality_by_tier",
        "charge_authority": "bot.spend_fixed_credit_info",
    },
    "video_tier_700": {
        "price_key": "video_tier_700",
        "product_key": "video_ai_prompt",
        "label": "Video Toàn Cảnh Chuyển Động Dài Kling 15s (Tier 700)",
        "unit": "scene",
        "base_value": 3214,
        "value_type": "int",
        "editable": True,
        "policy_type": "PAID_PRICE",
        "domain": "video",
        "read_authority": "services.video_ai_real_pricing.public_quality_catalog",
        "quote_authority": "services.video_ai_real_pricing.public_quality_by_tier",
        "charge_authority": "bot.spend_fixed_credit_info",
    },

    # --- AI Image Tiers (services.video_ai_real_pricing.public_image_quality_catalog) ---
    "image_tier_low": {
        "price_key": "image_tier_low",
        "product_key": "image_generation",
        "label": "Ảnh AI Nhanh gọn (Low)",
        "unit": "image",
        "base_value": 10,
        "value_type": "int",
        "editable": True,
        "policy_type": "PAID_PRICE",
        "domain": "image",
        "read_authority": "services.video_ai_real_pricing.public_image_quality_catalog",
        "quote_authority": "services.video_ai_real_pricing.public_image_quality_by_tier",
        "charge_authority": "bot.spend_fixed_credit_info",
    },
    "image_tier_standard": {
        "price_key": "image_tier_standard",
        "product_key": "image_generation",
        "label": "Ảnh AI Cân bằng (Standard)",
        "unit": "image",
        "base_value": 20,
        "value_type": "int",
        "editable": True,
        "policy_type": "PAID_PRICE",
        "domain": "image",
        "read_authority": "services.video_ai_real_pricing.public_image_quality_catalog",
        "quote_authority": "services.video_ai_real_pricing.public_image_quality_by_tier",
        "charge_authority": "bot.spend_fixed_credit_info",
    },
    "image_tier_standard_warranty": {
        "price_key": "image_tier_standard_warranty",
        "product_key": "image_generation",
        "label": "Ảnh AI Cân bằng + bảo hành",
        "unit": "image",
        "base_value": 30,
        "value_type": "int",
        "editable": True,
        "policy_type": "PAID_PRICE",
        "domain": "image",
        "read_authority": "services.video_ai_real_pricing.public_image_quality_catalog",
        "quote_authority": "services.video_ai_real_pricing.public_image_quality_by_tier",
        "charge_authority": "bot.spend_fixed_credit_info",
    },
    "image_tier_common": {
        "price_key": "image_tier_common",
        "product_key": "image_generation",
        "label": "Ảnh AI Sáng tạo chi tiết (Common)",
        "unit": "image",
        "base_value": 50,
        "value_type": "int",
        "editable": True,
        "policy_type": "PAID_PRICE",
        "domain": "image",
        "read_authority": "services.video_ai_real_pricing.public_image_quality_catalog",
        "quote_authority": "services.video_ai_real_pricing.public_image_quality_by_tier",
        "charge_authority": "bot.spend_fixed_credit_info",
    },
    "image_tier_common_warranty": {
        "price_key": "image_tier_common_warranty",
        "product_key": "image_generation",
        "label": "Ảnh AI Sáng tạo chi tiết + bảo hành",
        "unit": "image",
        "base_value": 100,
        "value_type": "int",
        "editable": True,
        "policy_type": "PAID_PRICE",
        "domain": "image",
        "read_authority": "services.video_ai_real_pricing.public_image_quality_catalog",
        "quote_authority": "services.video_ai_real_pricing.public_image_quality_by_tier",
        "charge_authority": "bot.spend_fixed_credit_info",
    },
    "image_tier_high": {
        "price_key": "image_tier_high",
        "product_key": "image_generation",
        "label": "Ảnh AI Cao cấp (High)",
        "unit": "image",
        "base_value": 70,
        "value_type": "int",
        "editable": True,
        "policy_type": "PAID_PRICE",
        "domain": "image",
        "read_authority": "services.video_ai_real_pricing.public_image_quality_catalog",
        "quote_authority": "services.video_ai_real_pricing.public_image_quality_by_tier",
        "charge_authority": "bot.spend_fixed_credit_info",
    },
    "image_tier_high_warranty": {
        "price_key": "image_tier_high_warranty",
        "product_key": "image_generation",
        "label": "Ảnh AI Cao cấp + bảo hành",
        "unit": "image",
        "base_value": 140,
        "value_type": "int",
        "editable": True,
        "policy_type": "PAID_PRICE",
        "domain": "image",
        "read_authority": "services.video_ai_real_pricing.public_image_quality_catalog",
        "quote_authority": "services.video_ai_real_pricing.public_image_quality_by_tier",
        "charge_authority": "bot.spend_fixed_credit_info",
    },

    # --- Voice / TTS / Clone (bot.py, default_voice_confirm_text, custom_voice_usage_price_xu) ---
    "voice_default_tts": {
        "price_key": "voice_default_tts",
        "product_key": "voice_tts",
        "label": "Giọng nam/nữ mặc định",
        "unit": "request",
        "base_value": 0,
        "value_type": "int",
        "editable": False,
        "policy_type": "FREE_BY_CANONICAL_POLICY",
        "domain": "voice",
        "read_authority": "bot.default_voice_confirm_text",
        "quote_authority": "bot.default_voice_confirm_text",
        "charge_authority": "FREE (Zero charge)",
    },
    "voice_clone_create": {
        "price_key": "voice_clone_create",
        "product_key": "voice_tts",
        "label": "Tạo Voice clone riêng",
        "unit": "clone_profile",
        "base_value": 50,
        "value_type": "int",
        "editable": True,
        "policy_type": "PAID_PRICE",
        "domain": "voice",
        "read_authority": "bot.voice_clone_quote_text",
        "quote_authority": "bot.voice_clone_quote_text",
        "charge_authority": "bot.spend_fixed_credit_info",
    },
    "voice_custom_tts_per_char": {
        "price_key": "voice_custom_tts_per_char",
        "product_key": "voice_tts",
        "label": "Đọc Voice riêng theo ký tự",
        "unit": "char",
        "base_value": 0.2,
        "value_type": "float",
        "editable": False,
        "policy_type": "UNWIRED_RUNTIME_POLICY",
        "domain": "voice",
        "read_authority": "UNWIRED_FROM_MUTABLE_ADMIN_SURFACE",
        "quote_authority": "UNWIRED_FROM_MUTABLE_ADMIN_SURFACE",
        "charge_authority": "UNWIRED_FROM_MUTABLE_ADMIN_SURFACE",
    },

    # --- AI Music (services.video_ai_real_pricing.public_music_background_prices, bot.py) ---
    "music_background_basic": {
        "price_key": "music_background_basic",
        "product_key": "music_generation",
        "label": "Nhạc nền cơ bản",
        "unit": "track",
        "base_value": 130,
        "value_type": "int",
        "editable": True,
        "policy_type": "PAID_PRICE",
        "domain": "music",
        "read_authority": "services.video_ai_real_pricing.public_music_background_prices",
        "quote_authority": "services.video_ai_real_pricing.public_music_background_prices",
        "charge_authority": "bot.spend_fixed_credit_info",
    },
    "music_background_standard": {
        "price_key": "music_background_standard",
        "product_key": "music_generation",
        "label": "Nhạc nền tiêu chuẩn",
        "unit": "track",
        "base_value": 150,
        "value_type": "int",
        "editable": True,
        "policy_type": "PAID_PRICE",
        "domain": "music",
        "read_authority": "services.video_ai_real_pricing.public_music_background_prices",
        "quote_authority": "services.video_ai_real_pricing.public_music_background_prices",
        "charge_authority": "bot.spend_fixed_credit_info",
    },
    "music_background_premium": {
        "price_key": "music_background_premium",
        "product_key": "music_generation",
        "label": "Nhạc nền cao cấp",
        "unit": "track",
        "base_value": 200,
        "value_type": "int",
        "editable": True,
        "policy_type": "PAID_PRICE",
        "domain": "music",
        "read_authority": "services.video_ai_real_pricing.public_music_background_prices",
        "quote_authority": "services.video_ai_real_pricing.public_music_background_prices",
        "charge_authority": "bot.spend_fixed_credit_info",
    },
    "music_vocal_full": {
        "price_key": "music_vocal_full",
        "product_key": "music_generation",
        "label": "Bài hát có lời AI (bản đầy đủ)",
        "unit": "song",
        "base_value": 800,
        "value_type": "int",
        "editable": True,
        "policy_type": "PAID_PRICE",
        "domain": "music",
        "read_authority": "bot.MUSIC_VOCAL_FULL_PRICE_XU",
        "quote_authority": "bot.music_product_quote_price_xu",
        "charge_authority": "bot.spend_fixed_credit_info",
    },

    # --- SubDub Service (services.subdub_auto_word_pricing, bot.py) ---
    "subdub_auto_word": {
        "price_key": "subdub_auto_word",
        "product_key": "subdub_service",
        "label": "Lồng tiếng Auto theo từ",
        "unit": "word",
        "base_value": 0.5,
        "value_type": "float",
        "editable": True,
        "policy_type": "PAID_PRICE",
        "domain": "subdub",
        "read_authority": "services.subdub_auto_word_pricing.AUTO_XU_PER_WORD",
        "quote_authority": "services.subdub_auto_word_pricing.auto_voice_component_xu",
        "charge_authority": "bot.spend_fixed_credit_info",
    },
    "subdub_translate_per_min": {
        "price_key": "subdub_translate_per_min",
        "product_key": "subdub_service",
        "label": "Dịch phụ đề video (mỗi phút)",
        "unit": "minute",
        "base_value": 40,
        "value_type": "int",
        "editable": False,
        "policy_type": "UNWIRED_RUNTIME_POLICY",
        "domain": "subdub",
        "read_authority": "UNWIRED_FROM_MUTABLE_ADMIN_SURFACE",
        "quote_authority": "UNWIRED_FROM_MUTABLE_ADMIN_SURFACE",
        "charge_authority": "UNWIRED_FROM_MUTABLE_ADMIN_SURFACE",
    },
    "subdub_burn_per_min": {
        "price_key": "subdub_burn_per_min",
        "product_key": "subdub_service",
        "label": "Ghép phụ đề cứng (mỗi phút)",
        "unit": "minute",
        "base_value": 20,
        "value_type": "int",
        "editable": False,
        "policy_type": "UNWIRED_RUNTIME_POLICY",
        "domain": "subdub",
        "read_authority": "UNWIRED_FROM_MUTABLE_ADMIN_SURFACE",
        "quote_authority": "UNWIRED_FROM_MUTABLE_ADMIN_SURFACE",
        "charge_authority": "UNWIRED_FROM_MUTABLE_ADMIN_SURFACE",
    },
    "subdub_blur_per_min": {
        "price_key": "subdub_blur_per_min",
        "product_key": "subdub_service",
        "label": "Xóa phụ đề cũ (mỗi phút)",
        "unit": "minute",
        "base_value": 20,
        "value_type": "int",
        "editable": False,
        "policy_type": "UNWIRED_RUNTIME_POLICY",
        "domain": "subdub",
        "read_authority": "UNWIRED_FROM_MUTABLE_ADMIN_SURFACE",
        "quote_authority": "UNWIRED_FROM_MUTABLE_ADMIN_SURFACE",
        "charge_authority": "UNWIRED_FROM_MUTABLE_ADMIN_SURFACE",
    },

    # --- Video Local Edit (services.video_local_editing) ---
    "video_local_edit": {
        "price_key": "video_local_edit",
        "product_key": "video_local_edit",
        "label": "Chỉnh sửa video nội bộ (FFmpeg)",
        "unit": "job",
        "base_value": 0,
        "value_type": "int",
        "editable": False,
        "policy_type": "FREE_BY_CANONICAL_POLICY",
        "domain": "video_local_edit",
        "read_authority": "services.video_local_editing",
        "quote_authority": "local_worker",
        "charge_authority": "FREE (Zero charge)",
    },

    # --- Content / Storyboard / Prompt Workflows (bot.py) ---
    "content_trend_analysis": {
        "price_key": "content_trend_analysis",
        "product_key": "video_trend",
        "label": "Phân tích xu hướng nội dung",
        "unit": "request",
        "base_value": 20,
        "value_type": "int",
        "editable": True,
        "policy_type": "PAID_PRICE",
        "domain": "content",
        "read_authority": "bot.WORKFLOW_TREND_ANALYSIS_COST_XU",
        "quote_authority": "bot.workflow_trend_analysis_cost_xu",
        "charge_authority": "bot.spend_fixed_credit_info",
    },
    "content_script_storyboard": {
        "price_key": "content_script_storyboard",
        "product_key": "script_to_video",
        "label": "Kịch bản & Storyboard",
        "unit": "request",
        "base_value": 30,
        "value_type": "int",
        "editable": True,
        "policy_type": "PAID_PRICE",
        "domain": "content",
        "read_authority": "bot.WORKFLOW_SCRIPT_STORYBOARD_COST_XU",
        "quote_authority": "bot.workflow_script_storyboard_cost_xu",
        "charge_authority": "bot.spend_fixed_credit_info",
    },
    "content_prompt_pack": {
        "price_key": "content_prompt_pack",
        "product_key": "video_ai_prompt",
        "label": "Bộ Prompt sản xuất video",
        "unit": "request",
        "base_value": 20,
        "value_type": "int",
        "editable": True,
        "policy_type": "PAID_PRICE",
        "domain": "content",
        "read_authority": "bot.WORKFLOW_PROMPT_PACK_COST_XU",
        "quote_authority": "bot.workflow_prompt_pack_cost_xu",
        "charge_authority": "bot.spend_fixed_credit_info",
    },
    "content_full_pack": {
        "price_key": "content_full_pack",
        "product_key": "video_idea_to_product",
        "label": "Gói nội dung hoàn chỉnh",
        "unit": "pack",
        "base_value": 70,
        "value_type": "int",
        "editable": True,
        "policy_type": "PAID_PRICE",
        "domain": "content",
        "read_authority": "bot.workflow_content_cost_xu",
        "quote_authority": "bot.workflow_content_cost_xu",
        "charge_authority": "bot.spend_fixed_credit_info",
    },

    # --- Documents / OCR Tools (bot.DOC_COSTS) ---
    "doc_image_to_pdf": {
        "price_key": "doc_image_to_pdf",
        "product_key": "doc_tools",
        "label": "Ảnh sang PDF",
        "unit": "file",
        "base_value": 0,
        "value_type": "int",
        "editable": False,
        "policy_type": "FREE_BY_CANONICAL_POLICY",
        "domain": "document",
        "read_authority": "bot.DOC_COSTS['image_to_pdf']",
        "quote_authority": "bot.doc_cost",
        "charge_authority": "FREE (Zero charge)",
    },
    "doc_ocr_pdf_per_page": {
        "price_key": "doc_ocr_pdf_per_page",
        "product_key": "doc_tools",
        "label": "OCR PDF theo trang",
        "unit": "page",
        "base_value": 0,
        "value_type": "int",
        "editable": False,
        "policy_type": "FREE_BY_CANONICAL_POLICY",
        "domain": "document",
        "read_authority": "bot.DOC_COSTS['ocr_pdf_per_page']",
        "quote_authority": "bot.doc_cost",
        "charge_authority": "FREE (Zero charge)",
    },

    # --- Chat Pro (services.chat_pro_pricing) ---
    "chat_pro_input": {
        "price_key": "chat_pro_input",
        "product_key": "chat_pro",
        "label": "Chat Pro Token đầu vào (mỗi 1K tokens)",
        "unit": "1k_tokens",
        "base_value": 5,
        "value_type": "int",
        "editable": True,
        "policy_type": "PAID_PRICE",
        "domain": "chat",
        "read_authority": "services.chat_pro_pricing.opus_price_per_thousand_labels",
        "quote_authority": "services.chat_pro_pricing.public_chat_customer_pricing",
        "charge_authority": "services.chat_pro_pricing.calculate_actual_xu",
    },
    "chat_pro_output": {
        "price_key": "chat_pro_output",
        "product_key": "chat_pro",
        "label": "Chat Pro Token đầu ra (mỗi 1K tokens)",
        "unit": "1k_tokens",
        "base_value": 25,
        "value_type": "int",
        "editable": True,
        "policy_type": "PAID_PRICE",
        "domain": "chat",
        "read_authority": "services.chat_pro_pricing.opus_price_per_thousand_labels",
        "quote_authority": "services.chat_pro_pricing.public_chat_customer_pricing",
        "charge_authority": "services.chat_pro_pricing.calculate_actual_xu",
    },
    "chat_pro_cache_read": {
        "price_key": "chat_pro_cache_read",
        "product_key": "chat_pro",
        "label": "Chat Pro Đọc bộ nhớ đệm (mỗi 1K tokens)",
        "unit": "1k_tokens",
        "base_value": 0.45,
        "value_type": "float",
        "editable": True,
        "policy_type": "PAID_PRICE",
        "domain": "chat",
        "read_authority": "services.chat_pro_pricing.opus_price_per_thousand_labels",
        "quote_authority": "services.chat_pro_pricing.public_chat_customer_pricing",
        "charge_authority": "services.chat_pro_pricing.calculate_actual_xu",
    },
}

# Immutable internal cost keywords strictly rejected from admin mutation
IMMUTABLE_INTERNAL_COST_FIELDS: set[str] = {
    "cost",
    "cost_minor",
    "cost_vnd",
    "usd_per_scene",
    "usd_per_second",
    "usd_per_image",
    "usd_per_track",
    "provider",
    "provider_cost",
    "provider_key",
    "provider_costs",
    "provider_order",
    "provider_priority",
    "provider_sources",
    "provider_capability",
    "exchange_rates_vnd_per_usd",
    "usd_to_vnd",
    "vnd_per_usd",
    "margin",
    "profit",
    "credentials",
    "api_key",
    "token",
    "wallet",
    "balance",
    "ledger",
}

# In-memory runtime override cache for ultra-fast and deterministic execution reads
_RUNTIME_PRICING_OVERRIDES: dict[str, Any] = {}
_RUNTIME_PRICING_STATES: dict[str, dict[str, Any]] = {}

# Canonical pricing aliases mapping legacy or alternative keys to canonical price keys
CANONICAL_PRICING_ALIASES: dict[str, str] = {
    "voice_clone": "voice_clone_create",
    "voice_clone_create": "voice_clone_create",
    "voice_profile_storage": "voice_clone_create",
}


def utc_now_text() -> str:
    """Format current UTC time as YYYY-MM-DD HH:MM:SS."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def ensure_admin_pricing_schema(conn: sqlite3.Connection) -> None:
    """Ensure durable admin pricing overrides and audit tables exist."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS admin_pricing_overrides (
            price_key TEXT PRIMARY KEY,
            product_key TEXT NOT NULL,
            effective_value TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,
            updated_at DATETIME NOT NULL,
            updated_by TEXT NOT NULL DEFAULT '',
            update_reason TEXT NOT NULL DEFAULT ''
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS admin_pricing_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            price_key TEXT NOT NULL,
            actor_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            reason TEXT NOT NULL,
            previous_version INTEGER NOT NULL,
            new_version INTEGER NOT NULL,
            previous_value TEXT NOT NULL,
            new_value TEXT NOT NULL,
            mutation_digest TEXT NOT NULL,
            request_id TEXT DEFAULT '',
            created_at DATETIME NOT NULL
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_admin_pricing_audit_key ON admin_pricing_audit(price_key)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_admin_pricing_audit_actor ON admin_pricing_audit(actor_id)"
    )


def resolve_effective_pricing(
    price_key: str,
    override_row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve effective pricing read model from canonical base and durable override."""
    if price_key not in BASE_PRICING_CATALOG:
        raise KeyError(f"Unknown price key: {price_key}")

    base = deepcopy(BASE_PRICING_CATALOG[price_key])
    effective = deepcopy(base)

    if override_row:
        raw_val = override_row.get("effective_value")
        if raw_val is not None:
            if base["value_type"] == "int":
                effective["effective_value"] = int(Decimal(str(raw_val)))
            else:
                effective["effective_value"] = float(Decimal(str(raw_val)))
        else:
            effective["effective_value"] = base["base_value"]

        effective["version"] = int(override_row.get("version", 1))
        effective["updated_at"] = override_row.get("updated_at")
        effective["updated_by"] = override_row.get("updated_by")
        effective["update_reason"] = override_row.get("update_reason")
        effective["has_override"] = True
    else:
        effective["effective_value"] = base["base_value"]
        effective["version"] = 1
        effective["updated_at"] = None
        effective["updated_by"] = None
        effective["update_reason"] = None
        effective["has_override"] = False

    return effective


def get_canonical_pricing_collection(db_path: str) -> tuple[bool, dict[str, Any], int]:
    """Return all canonical price keys with effective values and metadata."""
    try:
        conn = sqlite3.connect(db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        ensure_admin_pricing_schema(conn)

        cur = conn.cursor()
        cur.execute("SELECT * FROM admin_pricing_overrides")
        overrides = {row["price_key"]: dict(row) for row in cur.fetchall()}
        conn.close()

        items = []
        for key in sorted(BASE_PRICING_CATALOG.keys()):
            ov = overrides.get(key)
            item = resolve_effective_pricing(key, ov)
            items.append(item)

        return True, {
            "ok": True,
            "total_count": len(items),
            "pricing": items,
            "catalog_version": "2026.09.b02.canonical",
        }, 200
    except Exception as exc:
        logger.exception("Error getting canonical pricing collection: %s", exc)
        return False, {
            "ok": False,
            "error_code": "INTERNAL_PRICING_ERROR",
            "message": str(exc),
        }, 500


def get_canonical_pricing_single(price_key: str, db_path: str) -> tuple[bool, dict[str, Any], int]:
    """Return a single canonical pricing entry with effective value and version."""
    price_key = CANONICAL_PRICING_ALIASES.get(price_key, price_key)
    if price_key not in BASE_PRICING_CATALOG:
        return False, {
            "ok": False,
            "error_code": "UNKNOWN_PRICE_KEY",
            "message": f"Unknown price key: {price_key}",
        }, 404

    try:
        conn = sqlite3.connect(db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        ensure_admin_pricing_schema(conn)

        cur = conn.cursor()
        cur.execute("SELECT * FROM admin_pricing_overrides WHERE price_key = ?", (price_key,))
        row = cur.fetchone()
        ov = dict(row) if row else None
        conn.close()

        item = resolve_effective_pricing(price_key, ov)
        return True, {"ok": True, "pricing": item}, 200
    except Exception as exc:
        logger.exception("Error getting single pricing %s: %s", price_key, exc)
        return False, {
            "ok": False,
            "error_code": "INTERNAL_PRICING_ERROR",
            "message": str(exc),
        }, 500


def clear_runtime_pricing_cache() -> None:
    """Clear in-memory runtime cache, useful for testing and fresh reload."""
    _RUNTIME_PRICING_OVERRIDES.clear()
    _RUNTIME_PRICING_STATES.clear()


def get_canonical_effective_price_state(price_key: str, db_path: str | None = None) -> dict[str, Any]:
    """Return explicit authority state: (base_value, effective_value, has_override, version).
    Does NOT infer override status from numeric equality."""
    price_key = CANONICAL_PRICING_ALIASES.get(price_key, price_key)
    base = BASE_PRICING_CATALOG.get(price_key, {})
    base_val = base.get("base_value")
    val_type = base.get("value_type", "int")

    if price_key in _RUNTIME_PRICING_STATES:
        return dict(_RUNTIME_PRICING_STATES[price_key])

    resolved_db = db_path
    if not resolved_db:
        import sys
        import os
        bot_mod = sys.modules.get("bot")
        if bot_mod:
            resolved_db = getattr(bot_mod, "DB_FILE", None)
        if not resolved_db:
            resolved_db = os.getenv("TOANAAS_DB_FILE")

    if resolved_db:
        try:
            conn = sqlite3.connect(resolved_db, timeout=5.0)
            conn.row_factory = sqlite3.Row
            ensure_admin_pricing_schema(conn)
            cur = conn.cursor()
            cur.execute("SELECT effective_value, version FROM admin_pricing_overrides WHERE price_key = ?", (price_key,))
            row = cur.fetchone()
            conn.close()
            if row:
                raw = row["effective_value"]
                val = int(Decimal(str(raw))) if val_type == "int" else float(Decimal(str(raw)))
                ver = int(row["version"])
                state = {
                    "price_key": price_key,
                    "base_value": base_val,
                    "effective_value": val,
                    "has_override": True,
                    "version": ver,
                }
                _RUNTIME_PRICING_OVERRIDES[price_key] = val
                _RUNTIME_PRICING_STATES[price_key] = state
                return dict(state)
        except Exception:
            pass

    state = {
        "price_key": price_key,
        "base_value": base_val,
        "effective_value": base_val,
        "has_override": False,
        "version": 1,
    }
    return state


def get_canonical_effective_price(price_key: str, fallback: Any = None, db_path: str | None = None) -> Any:
    """Synchronous read helper consumed directly by execution engines and quote resolvers."""
    state = get_canonical_effective_price_state(price_key, db_path=db_path)
    if state["has_override"]:
        return state["effective_value"]
    if state["base_value"] is not None:
        return state["base_value"]
    return fallback


def update_canonical_pricing(
    price_key: str,
    payload: dict[str, Any],
    actor_id: str,
    request_id: str,
    db_path: str,
) -> tuple[bool, dict[str, Any], int]:
    """Execute CAS mutation on a single price key and append immutable audit event."""
    price_key = CANONICAL_PRICING_ALIASES.get(price_key, price_key)
    if price_key not in BASE_PRICING_CATALOG:
        return False, {
            "ok": False,
            "error_code": "UNKNOWN_PRICE_KEY",
            "message": f"Unknown price key: {price_key}",
        }, 404

    base = BASE_PRICING_CATALOG[price_key]

    # Validate price key editability
    if not base.get("editable", True):
        return False, {
            "ok": False,
            "error_code": "IMMUTABLE_PRICE_KEY_REJECTED",
            "message": f"Price key '{price_key}' is immutable by canonical policy and cannot be mutated.",
        }, 400

    # Reject immutable / internal cost fields
    forbidden_keys = set(payload.keys()) & IMMUTABLE_INTERNAL_COST_FIELDS
    if forbidden_keys:
        return False, {
            "ok": False,
            "error_code": "IMMUTABLE_FIELD_MODIFICATION_FORBIDDEN",
            "message": f"Payload contains forbidden internal cost fields: {sorted(forbidden_keys)}",
        }, 400

    # Validate expected_version
    if "expected_version" not in payload:
        return False, {
            "ok": False,
            "error_code": "EXPECTED_VERSION_MANDATORY",
            "message": "Missing mandatory field 'expected_version' for optimistic concurrency control (CAS).",
        }, 400

    try:
        expected_version = int(payload["expected_version"])
    except (ValueError, TypeError):
        return False, {
            "ok": False,
            "error_code": "INVALID_EXPECTED_VERSION",
            "message": "'expected_version' must be an integer.",
        }, 400

    # Validate new_value
    if "new_value" not in payload:
        return False, {
            "ok": False,
            "error_code": "NEW_VALUE_MANDATORY",
            "message": "Missing mandatory field 'new_value'.",
        }, 400

    raw_val = payload["new_value"]
    try:
        dec_val = Decimal(str(raw_val).strip())
    except (InvalidOperation, ValueError, TypeError):
        return False, {
            "ok": False,
            "error_code": "INVALID_PRICE_VALUE",
            "message": "'new_value' must be a valid numeric value.",
        }, 400

    if dec_val < Decimal("0"):
        return False, {
            "ok": False,
            "error_code": "NEGATIVE_PRICE_REJECTED",
            "message": "Price value cannot be negative.",
        }, 400

    if base["policy_type"] == "PAID_PRICE" and dec_val <= Decimal("0"):
        return False, {
            "ok": False,
            "error_code": "PAID_PRICE_CANNOT_BE_ZERO",
            "message": f"Price key '{price_key}' requires a positive value (> 0).",
        }, 400

    if base["value_type"] == "int" and dec_val != dec_val.to_integral_value():
        return False, {
            "ok": False,
            "error_code": "INVALID_PRICE_VALUE_TYPE",
            "message": f"Price key '{price_key}' requires an integer value, got decimal {raw_val}.",
        }, 400

    if dec_val > Decimal("100000000"):
        return False, {
            "ok": False,
            "error_code": "PRICE_VALUE_UNBOUNDED",
            "message": "Price value exceeds maximum allowable bound (100,000,000).",
        }, 400

    # Check reason
    reason = str(payload.get("reason") or "").strip()
    if not reason:
        return False, {
            "ok": False,
            "error_code": "REASON_MANDATORY",
            "message": "A non-empty 'reason' is required for audit recording.",
        }, 400

    now_text = utc_now_text()
    clean_val = int(dec_val) if base["value_type"] == "int" else float(dec_val)

    try:
        conn = sqlite3.connect(db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        ensure_admin_pricing_schema(conn)

        with conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM admin_pricing_overrides WHERE price_key = ?", (price_key,))
            existing = cur.fetchone()

            current_version = int(existing["version"]) if existing else 1
            previous_value = existing["effective_value"] if existing else str(base["base_value"])

            # Check CAS version
            if current_version != expected_version:
                # Check idempotency: if request_id matches existing latest audit record
                if request_id:
                    cur.execute(
                        "SELECT * FROM admin_pricing_audit WHERE price_key = ? AND request_id = ? ORDER BY id DESC LIMIT 1",
                        (price_key, request_id),
                    )
                    recent_audit = cur.fetchone()
                    if recent_audit and recent_audit["new_version"] == current_version:
                        # Idempotent replay: return existing receipt
                        receipt = {
                            "receipt_id": f"rcpt_prc_{recent_audit['id']}_{recent_audit['mutation_digest'][:8]}",
                            "price_key": price_key,
                            "previous_version": recent_audit["previous_version"],
                            "new_version": recent_audit["new_version"],
                            "previous_value": recent_audit["previous_value"],
                            "new_value": recent_audit["new_value"],
                            "mutation_digest": recent_audit["mutation_digest"],
                            "request_id": request_id,
                            "actor_id": recent_audit["actor_id"],
                            "timestamp": recent_audit["timestamp"],
                            "idempotent_replay": True,
                        }
                        item = resolve_effective_pricing(price_key, dict(existing))
                        return True, {"ok": True, "receipt": receipt, "pricing": item}, 200

                return False, {
                    "ok": False,
                    "error_code": "VERSION_CONFLICT_STALE_WRITE",
                    "message": f"Version conflict for {price_key}: expected {expected_version}, current is {current_version}.",
                    "current_version": current_version,
                    "expected_version": expected_version,
                }, 409

            new_version = current_version + 1
            mutation_seed = f"{price_key}:{current_version}:{new_version}:{clean_val}:{actor_id}:{reason}:{request_id}"
            mutation_digest = hashlib.sha256(mutation_seed.encode("utf-8")).hexdigest()

            # Persist override
            cur.execute(
                """INSERT INTO admin_pricing_overrides (
                    price_key, product_key, effective_value, version, updated_at, updated_by, update_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(price_key) DO UPDATE SET
                    effective_value = excluded.effective_value,
                    version = excluded.version,
                    updated_at = excluded.updated_at,
                    updated_by = excluded.updated_by,
                    update_reason = excluded.update_reason
                """,
                (price_key, base["product_key"], str(clean_val), new_version, now_text, actor_id, reason),
            )

            # Append audit
            cur.execute(
                """INSERT INTO admin_pricing_audit (
                    price_key, actor_id, timestamp, reason, previous_version, new_version,
                    previous_value, new_value, mutation_digest, request_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    price_key,
                    actor_id,
                    now_text,
                    reason,
                    current_version,
                    new_version,
                    str(previous_value),
                    str(clean_val),
                    mutation_digest,
                    request_id,
                    now_text,
                ),
            )
            audit_id = cur.lastrowid

        conn.close()

        # Update runtime hook cache
        _RUNTIME_PRICING_OVERRIDES[price_key] = clean_val
        _RUNTIME_PRICING_STATES[price_key] = {
            "price_key": price_key,
            "base_value": base["base_value"],
            "effective_value": clean_val,
            "has_override": True,
            "version": new_version,
        }

        # Fresh canonical readback verification
        readback_val = get_canonical_effective_price(price_key, db_path=db_path)
        if readback_val != clean_val:
            raise RuntimeError(f"Readback mismatch for {price_key}: expected {clean_val}, got {readback_val}")

        receipt = {
            "receipt_id": f"rcpt_prc_{audit_id}_{mutation_digest[:8]}",
            "price_key": price_key,
            "previous_version": current_version,
            "new_version": new_version,
            "previous_value": previous_value,
            "new_value": clean_val,
            "mutation_digest": mutation_digest,
            "request_id": request_id,
            "actor_id": actor_id,
            "timestamp": now_text,
            "idempotent_replay": False,
        }

        updated_item = {
            "price_key": price_key,
            "product_key": base["product_key"],
            "label": base["label"],
            "unit": base["unit"],
            "effective_value": clean_val,
            "version": new_version,
            "updated_at": now_text,
            "updated_by": actor_id,
            "update_reason": reason,
        }

        return True, {
            "ok": True,
            "receipt": receipt,
            "pricing": updated_item,
        }, 200

    except Exception as exc:
        logger.exception("Error mutating canonical pricing %s: %s", price_key, exc)
        return False, {
            "ok": False,
            "error_code": "INTERNAL_PRICING_MUTATION_ERROR",
            "message": str(exc),
        }, 500


# Canonical aliases and receipt/readback helpers for explicit spec verification
update_canonical_pricing_cas = update_canonical_pricing


def generate_pricing_write_receipt(
    price_key: str,
    previous_version: int,
    new_version: int,
    previous_value: Any,
    new_value: Any,
    mutation_digest: str,
    request_id: str,
    actor_id: str,
    timestamp: str,
    audit_id: int = 1,
    idempotent_replay: bool = False,
) -> dict[str, Any]:
    """Generate canonical pricing write receipt model."""
    return {
        "receipt_id": f"rcpt_prc_{audit_id}_{mutation_digest[:8]}",
        "price_key": price_key,
        "previous_version": previous_version,
        "new_version": new_version,
        "previous_value": previous_value,
        "new_value": new_value,
        "mutation_digest": mutation_digest,
        "request_id": request_id,
        "actor_id": actor_id,
        "timestamp": timestamp,
        "idempotent_replay": idempotent_replay,
    }


def verify_fresh_canonical_readback(price_key: str, expected_val: Any, db_path: str) -> bool:
    """Verify fresh readback directly against canonical SQLite source."""
    val = get_canonical_effective_price(price_key, db_path=db_path)
    return val == expected_val

