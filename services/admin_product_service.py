"""Canonical Bot Core Admin Product Commercial Authority Service (B01.C1).

Implements the single canonical Bot-owned product configuration and commercial override authority.
Guarantees:
- Single source of truth for Bot product commercial metadata (WebApp is orchestrator/editor only)
- Dynamic discovery & adapter layer reading fresh technical contracts from canonical Bot authorities:
  * services.video_tail9.commercial_contract
  * services.video_uifreeze1.PUBLIC_EXECUTION_LOCKED_PRODUCTS
  * services.video_project_queue.product_video_engine_contract
  * services.video_ai_real_pricing (image and music catalogs)
  * services.subtitle_dub_product_pipeline (subdub shared core modes)
  * services.chat_pro_pricing (Claude Opus chat tariff)
  * bot.get_tts_provider_readiness (voice TTS)
- No second static technical capability catalog
- Customer product keys strictly separated from executor aliases:
  * script_image_video (customer) != script_to_video (executor alias)
  * video_idea (customer) != video_idea_to_product (executor alias)
- Invariant safety lock: commercial_enabled=True NEVER enables execution_enabled for deferred/locked products
- Durable, versioned, append-only audit trail with CAS optimistic concurrency
- Strict editable field whitelist (pricing, provider routing, credentials, wallet logic remain immutable)
- Zero mutations to wallet, ledger, historical payments, or provider configuration
"""

from __future__ import annotations

from copy import deepcopy
import datetime
import hashlib
import json
import logging
import sqlite3
import time
from typing import Any

logger = logging.getLogger("admin_product_service")

DEFAULT_ADMIN_ID = "7126457028"

# ─── CANONICAL CUSTOMER PRODUCT INVENTORY ─────────────────────────────────────

# ─── CANONICAL CUSTOMER PRODUCT DYNAMIC DISCOVERY ──────────────────────────────
# Technical inventory is dynamically resolved from live bot authorities.
# No static tuples act as technical authorities.

def discover_product_video_products() -> list[str]:
    """Dynamically discover Product Video canonical customer product keys from video authorities."""
    from services import video_tail9, video_uifreeze1
    sources = set(video_tail9.PRODUCT_ADAPTERS.keys()) | set(video_uifreeze1.CANONICAL_PRICING_PRODUCTS)
    frame_keys = set(getattr(video_uifreeze1, "FRAMEVIDEO_PRICING_PRODUCTS", ()))

    discovered = set()
    for raw_key in sources:
        if raw_key in frame_keys:
            continue
        canonical_key = resolve_canonical_product_key(raw_key)
        discovered.add(canonical_key)
    return sorted(discovered, key=lambda k: (PRODUCT_PRESENTATION_DEFAULTS.get(k, {}).get("sort_order", 100), k))


def discover_image_products() -> list[str]:
    """Dynamically discover Image canonical customer product keys from image authorities."""
    from services import video_ai_real_pricing
    if hasattr(video_ai_real_pricing, "public_image_quality_catalog"):
        return ["image_generation"]
    return []


def discover_voice_products() -> list[str]:
    """Dynamically discover Voice canonical customer product keys from voice authorities."""
    import bot
    res = []
    if hasattr(bot, "get_tts_provider_readiness"):
        res.append("voice_tts")
    if hasattr(bot, "get_minimax_voice_clone_readiness"):
        res.append("voice_clone")
    return res


def discover_music_products() -> list[str]:
    """Dynamically discover Music canonical customer product keys from music authorities."""
    from services import video_ai_real_pricing
    if hasattr(video_ai_real_pricing, "music_model_catalog"):
        return ["music_generation"]
    return []


def discover_subdub_products() -> list[str]:
    """Dynamically discover SubDub canonical customer product keys from subdub authorities."""
    from services import subtitle_dub_product_pipeline
    modes = getattr(subtitle_dub_product_pipeline, "SUBDUB_SHARED_CORE_MODES", set())
    if modes:
        return ["subdub_service"]
    return []


def discover_chat_products() -> list[str]:
    """Dynamically discover Chat Pro canonical customer product keys from chat authorities."""
    from services import chat_pro_pricing
    if hasattr(chat_pro_pricing, "CLAUDE_OPUS_MODEL"):
        return ["chat_pro"]
    return []


def discover_canonical_products() -> list[str]:
    """Discover, canonicalize, de-duplicate, and return all available canonical customer products."""
    discovered: list[str] = []
    seen: set[str] = set()
    for provider_func in (
        discover_product_video_products,
        discover_image_products,
        discover_voice_products,
        discover_music_products,
        discover_subdub_products,
        discover_chat_products,
    ):
        for raw_key in provider_func():
            canonical_key = resolve_canonical_product_key(raw_key)
            if canonical_key not in seen:
                seen.add(canonical_key)
                discovered.append(canonical_key)

    discovered.sort(key=lambda k: (PRODUCT_PRESENTATION_DEFAULTS.get(k, {}).get("sort_order", 999), k))
    return discovered


class _DynamicKeys(tuple):
    """Dynamic sequence of canonical keys reflecting discovered inventory."""
    def __contains__(self, item: object) -> bool:
        return resolve_canonical_product_key(str(item)) in discover_canonical_products()

    def __iter__(self):
        return iter(discover_canonical_products())

    def __len__(self) -> int:
        return len(discover_canonical_products())

    def __getitem__(self, idx):
        return discover_canonical_products()[idx]


class _DynamicVideoKeys(frozenset):
    """Dynamic set of product video keys reflecting discovered inventory."""
    def __contains__(self, item: object) -> bool:
        return resolve_canonical_product_key(str(item)) in discover_product_video_products()

    def __iter__(self):
        return iter(discover_product_video_products())

    def __len__(self) -> int:
        return len(discover_product_video_products())


CANONICAL_PRODUCT_KEYS = _DynamicKeys()
PRODUCT_VIDEO_KEYS = _DynamicVideoKeys()

# Canonical mapping from legacy/executor aliases to canonical customer product keys
CANONICAL_PRODUCT_ALIASES: dict[str, str] = {
    "script_to_video": "script_image_video",
    "video_idea_to_product": "video_idea",
    "video_edit": "video_local_edit",
    "long_video": "video_long",
    "trend_video": "video_trend",
    "prompt_video": "video_ai_prompt",
    "video_ai_real": "video_ai_prompt",
    "image_video": "video_ai_image",
    "video_video": "video_ai_video_reference",
    "selfshot_scene_change": "self_shot_scene_change",
    "selfshot_cinematic": "self_shot_cinematic_transform",
}

# Default commercial presentation metadata (editable by Owner via Admin API)
PRODUCT_PRESENTATION_DEFAULTS: dict[str, dict[str, Any]] = {
    "video_trend": {
        "display_name": "Video theo trend",
        "description": "Tạo video ngắn bắt trend mạng xã hội tự động",
        "product_group": "video",
        "public_visible": True,
        "commercial_enabled": True,
        "sort_order": 10,
    },
    "video_ai_prompt": {
        "display_name": "Video AI chân thật (từ Prompt)",
        "description": "Tạo video AI chân thật từ câu lệnh văn bản mô tả",
        "product_group": "video",
        "public_visible": True,
        "commercial_enabled": True,
        "sort_order": 20,
    },
    "video_ai_image": {
        "display_name": "Video AI từ Ảnh",
        "description": "Biến ảnh tĩnh thành chuyển động video chân thực",
        "product_group": "video",
        "public_visible": True,
        "commercial_enabled": True,
        "sort_order": 30,
    },
    "video_ai_video_reference": {
        "display_name": "Video AI tham khảo",
        "description": "Tái tạo hoặc biến đổi phong cách từ video mẫu",
        "product_group": "video",
        "public_visible": True,
        "commercial_enabled": True,
        "sort_order": 40,
    },
    "script_image_video": {
        "display_name": "Kịch bản → Video",
        "description": "Chuyển kịch bản hoàn chỉnh thành chuỗi cảnh video",
        "product_group": "video",
        "public_visible": True,
        "commercial_enabled": True,
        "sort_order": 50,
    },
    "storyboard_prompt": {
        "display_name": "Storyboard phân cảnh",
        "description": "Phác thảo và dựng từng phân cảnh với prompt trực quan",
        "product_group": "video",
        "public_visible": True,
        "commercial_enabled": True,
        "sort_order": 60,
    },
    "self_shot_scene_change": {
        "display_name": "Tự quay & Đổi cảnh AI",
        "description": "Giữ chủ thể người/sản phẩm và thay thế toàn bộ bối cảnh",
        "product_group": "video",
        "public_visible": True,
        "commercial_enabled": True,
        "sort_order": 80,
    },
    "self_shot_cinematic_transform": {
        "display_name": "Biến đổi điện ảnh một cú máy",
        "description": "Nâng cấp video tự quay thành chuẩn phim trường điện ảnh",
        "product_group": "video",
        "public_visible": True,
        "commercial_enabled": True,
        "sort_order": 90,
    },
    "multi_scene_film": {
        "display_name": "Video dài tập (Nhiều phân cảnh)",
        "description": "Sản xuất video nhiều tập có cốt truyện và nhân vật xuyên suốt",
        "product_group": "video",
        "public_visible": True,
        "commercial_enabled": True,
        "sort_order": 100,
    },
    "video_idea": {
        "display_name": "Phát triển ý tưởng video",
        "description": "Từ ý tưởng thô phát triển thành kế hoạch sản xuất video hoàn chỉnh",
        "product_group": "video",
        "public_visible": True,
        "commercial_enabled": True,
        "sort_order": 110,
    },
    "video_local_edit": {
        "display_name": "Chỉnh sửa / Nâng cấp video",
        "description": "Cắt ghép, nén, tối ưu và xử lý hậu kỳ video cục bộ qua FFmpeg",
        "product_group": "video",
        "public_visible": True,
        "commercial_enabled": True,
        "sort_order": 120,
    },
    "video_long": {
        "display_name": "Video dài chuyên sâu",
        "description": "Sản xuất video độ dài lớn với bố cục phân cảnh tự động",
        "product_group": "video",
        "public_visible": True,
        "commercial_enabled": True,
        "sort_order": 125,
    },
    "image_generation": {
        "display_name": "Tạo Ảnh AI Chuyên Nghiệp",
        "description": "Tạo hình ảnh AI độ phân giải cao từ văn bản mô tả",
        "product_group": "image",
        "public_visible": True,
        "commercial_enabled": True,
        "sort_order": 130,
    },
    "voice_tts": {
        "display_name": "Tạo Giọng Nói AI (Text to Speech)",
        "description": "Chuyển văn bản thành giọng đọc tự nhiên đa ngôn ngữ và cảm xúc",
        "product_group": "voice",
        "public_visible": True,
        "commercial_enabled": True,
        "sort_order": 140,
    },
    "voice_clone": {
        "display_name": "Clone Giọng Nói AI",
        "description": "Sao chép và mô phỏng giọng nói cá nhân từ mẫu âm thanh ngắn",
        "product_group": "voice",
        "public_visible": True,
        "commercial_enabled": True,
        "sort_order": 150,
    },
    "music_generation": {
        "display_name": "Tạo Nhạc & Bài Hát AI",
        "description": "Sáng tác ca khúc hoàn chỉnh và nhạc nền theo phong cách mong muốn",
        "product_group": "music",
        "public_visible": True,
        "commercial_enabled": True,
        "sort_order": 160,
    },
    "subdub_service": {
        "display_name": "Phụ Đề & Lồng Tiếng AI (SubDub)",
        "description": "Tạo phụ đề tự động, dịch thuật đa ngữ và lồng tiếng khớp khẩu hình",
        "product_group": "subdub",
        "public_visible": True,
        "commercial_enabled": True,
        "sort_order": 170,
    },
    "chat_pro": {
        "display_name": "Trợ Lý AI Đa Năng (Chat Pro)",
        "description": "Hội thoại thông minh, soạn thảo nội dung và hỗ trợ công việc 24/7",
        "product_group": "productivity",
        "public_visible": True,
        "commercial_enabled": True,
        "sort_order": 180,
    },
}


def resolve_canonical_product_key(product_key: str) -> str:
    """Resolve an incoming product key or alias to canonical customer product key."""
    clean = str(product_key or "").strip()
    return CANONICAL_PRODUCT_ALIASES.get(clean, clean)


def resolve_canonical_product_video_ratios(product_key: str, comm: dict[str, Any]) -> list[str] | str:
    """Dynamically resolve supported ratios from canonical authority.

    If canonical authority exposes supported ratios (in commercial_contract or video_tail9),
    use it directly. Otherwise, do NOT maintain a synthetic candidate list; report NOT_EXPOSED.
    """
    from services import video_tail9

    # 1. Direct commercial contract key if exposed
    if "supported_ratios" in comm and comm["supported_ratios"] is not None:
        return list(comm["supported_ratios"])

    # 2. Canonical ratio inventory function on video_tail9 if exposed
    if hasattr(video_tail9, "supported_ratios") and callable(getattr(video_tail9, "supported_ratios")):
        return list(video_tail9.supported_ratios(product_key))

    # 3. Canonical catalog/attribute on video_tail9 if exposed
    if hasattr(video_tail9, "PRODUCT_SUPPORTED_RATIOS"):
        cat = getattr(video_tail9, "PRODUCT_SUPPORTED_RATIOS")
        if isinstance(cat, dict) and product_key in cat:
            return list(cat[product_key])
        if isinstance(cat, (list, tuple, set, frozenset)):
            return list(cat)

    # 4. Only admission predicate exists and NO canonical ratio inventory is exposed
    return "NOT_EXPOSED"


def resolve_canonical_technical_contract(product_key: str) -> dict[str, Any]:
    """Dynamically resolve technical capability fields from authoritative Bot source modules.

    Never reads from a static duplicated catalog. Always queries live contracts:
    - Product Video: services.video_tail9, services.video_uifreeze1, services.video_project_queue
    - Image: services.video_ai_real_pricing.public_image_quality_catalog
    - Music: services.video_ai_real_pricing.music_model_catalog
    - Voice: bot.get_tts_provider_readiness, bot.get_minimax_voice_clone_readiness
    - SubDub: services.subtitle_dub_product_pipeline, providers.subtitle_dub_pipeline
    - Chat: services.chat_pro_pricing
    """
    clean_key = resolve_canonical_product_key(product_key)
    discovered = discover_canonical_products()
    if clean_key not in discovered:
        raise KeyError(f"Unrecognized canonical product key: {product_key}")

    defaults = deepcopy(PRODUCT_PRESENTATION_DEFAULTS.get(clean_key, {}))

    if clean_key in discover_product_video_products():
        from services import video_tail9, video_uifreeze1, video_project_queue

        comm = video_tail9.commercial_contract(clean_key)
        engine_contract = video_project_queue.product_video_engine_contract(clean_key)
        is_locked = clean_key in video_uifreeze1.PUBLIC_EXECUTION_LOCKED_PRODUCTS

        supported_tiers = list(comm.get("supported_quality_tiers") or ())
        supported_ratios = resolve_canonical_product_video_ratios(clean_key, comm)

        execution_enabled = False if is_locked else bool(comm.get("execution_enabled", False))
        execution_blocker = str(comm.get("execution_blocker") or (f"{clean_key}_deferred" if is_locked else ""))

        req_cap = str(engine_contract.get("required_capability") or comm.get("required_capability") or "")

        return {
            "product_key": clean_key,
            "product_group": defaults.get("product_group", "video"),
            "display_name": defaults.get("display_name", clean_key),
            "description": defaults.get("description", ""),
            "public_visible": defaults.get("public_visible", True),
            "commercial_enabled": defaults.get("commercial_enabled", True),
            "sort_order": defaults.get("sort_order", 100),
            "execution_enabled": execution_enabled,
            "execution_blocker": execution_blocker,
            "supported_tiers": supported_tiers,
            "supported_quality_tiers": supported_tiers,
            "supported_ratios": supported_ratios,
            "required_capability": req_cap,
            "provider_capability": req_cap,
            "modality": str(comm.get("required_capability") or req_cap),
            "executor_product_type": str(comm.get("executor_product_type") or ""),
            "engine_route": str(comm.get("engine_route") or ""),
            "flow_owner": str(comm.get("flow_owner") or ""),
            "worker_owner": str(comm.get("worker_owner") or "product_video"),
            "minimum_scene_count": int(comm.get("minimum_scene_count") or 1),
            "maximum_scene_count": int(comm.get("maximum_scene_count") or 20),
            "supports_single_scene": bool(comm.get("supports_single_scene", True)),
            "source_authority": "services.video_tail9.commercial_contract",
        }

    elif clean_key == "image_generation":
        from services import video_ai_real_pricing

        try:
            image_catalog = video_ai_real_pricing.public_image_quality_catalog()
            supported_tiers = [item["tier_key"] for item in image_catalog]
            execution_enabled = bool(supported_tiers)
            execution_blocker = ""
        except Exception:
            supported_tiers = []
            execution_enabled = False
            execution_blocker = "image_authority_unavailable"

        return {
            "product_key": clean_key,
            "product_group": defaults.get("product_group", "image"),
            "display_name": defaults.get("display_name", "Tạo Ảnh AI Chuyên Nghiệp"),
            "description": defaults.get("description", "Tạo hình ảnh AI độ phân giải cao từ văn bản mô tả"),
            "public_visible": defaults.get("public_visible", True),
            "commercial_enabled": defaults.get("commercial_enabled", True),
            "sort_order": defaults.get("sort_order", 130),
            "execution_enabled": execution_enabled,
            "execution_blocker": execution_blocker,
            "supported_tiers": supported_tiers,
            "supported_quality_tiers": supported_tiers,
            "supported_ratios": "NOT_EXPOSED",
            "required_capability": "NOT_EXPOSED",
            "provider_capability": "NOT_EXPOSED",
            "modality": "NOT_EXPOSED",
            "executor_product_type": "NOT_EXPOSED",
            "engine_route": "NOT_EXPOSED",
            "flow_owner": "NOT_EXPOSED",
            "worker_owner": "NOT_EXPOSED",
            "source_authority": "services.video_ai_real_pricing.public_image_quality_catalog",
        }

    elif clean_key == "voice_tts":
        import bot

        try:
            tts_info = bot.get_tts_provider_readiness(public=True)
            ready = bool(tts_info.get("public_ready", False) or tts_info.get("ready", False))
            supported_tiers = list(tts_info.get("supported_voices", []))
            blocker = str(tts_info.get("reason", "")) if not ready else ""
        except Exception:
            supported_tiers = []
            ready = False
            blocker = "tts_authority_unavailable"

        return {
            "product_key": clean_key,
            "product_group": defaults.get("product_group", "voice"),
            "display_name": defaults.get("display_name", "Tạo Giọng Nói AI (Text to Speech)"),
            "description": defaults.get("description", "Chuyển văn bản thành giọng đọc tự nhiên đa ngôn ngữ và cảm xúc"),
            "public_visible": defaults.get("public_visible", True),
            "commercial_enabled": defaults.get("commercial_enabled", True),
            "sort_order": defaults.get("sort_order", 140),
            "execution_enabled": ready,
            "execution_blocker": blocker,
            "supported_tiers": supported_tiers,
            "supported_quality_tiers": supported_tiers,
            "supported_ratios": "NOT_EXPOSED",
            "required_capability": "NOT_EXPOSED",
            "provider_capability": "NOT_EXPOSED",
            "modality": "NOT_EXPOSED",
            "executor_product_type": "NOT_EXPOSED",
            "engine_route": "NOT_EXPOSED",
            "flow_owner": "NOT_EXPOSED",
            "worker_owner": "NOT_EXPOSED",
            "source_authority": "bot.get_tts_provider_readiness",
        }

    elif clean_key == "voice_clone":
        import bot

        try:
            clone_info = bot.get_minimax_voice_clone_readiness()
            ready = bool(clone_info.get("public_enabled", False))
            blocker = str(clone_info.get("reason", "")) if not ready else ""
        except Exception:
            ready = False
            blocker = "voice_clone_authority_unavailable"

        return {
            "product_key": clean_key,
            "product_group": defaults.get("product_group", "voice"),
            "display_name": defaults.get("display_name", "Clone Giọng Nói AI"),
            "description": defaults.get("description", "Sao chép và mô phỏng giọng nói cá nhân từ mẫu âm thanh ngắn"),
            "public_visible": defaults.get("public_visible", True),
            "commercial_enabled": defaults.get("commercial_enabled", True),
            "sort_order": defaults.get("sort_order", 150),
            "execution_enabled": ready,
            "execution_blocker": blocker,
            "supported_tiers": [],
            "supported_quality_tiers": [],
            "supported_ratios": "NOT_EXPOSED",
            "required_capability": "NOT_EXPOSED",
            "provider_capability": "NOT_EXPOSED",
            "modality": "NOT_EXPOSED",
            "executor_product_type": "NOT_EXPOSED",
            "engine_route": "NOT_EXPOSED",
            "flow_owner": "NOT_EXPOSED",
            "worker_owner": "NOT_EXPOSED",
            "source_authority": "bot.get_minimax_voice_clone_readiness",
        }

    elif clean_key == "music_generation":
        from services import video_ai_real_pricing

        try:
            music_catalog = video_ai_real_pricing.music_model_catalog()
            supported_tiers = [item["key"] for item in music_catalog]
            execution_enabled = bool(supported_tiers)
            execution_blocker = ""
        except Exception:
            supported_tiers = []
            execution_enabled = False
            execution_blocker = "music_authority_unavailable"

        return {
            "product_key": clean_key,
            "product_group": defaults.get("product_group", "music"),
            "display_name": defaults.get("display_name", "Tạo Nhạc & Bài Hát AI"),
            "description": defaults.get("description", "Sáng tác ca khúc hoàn chỉnh và nhạc nền theo phong cách mong muốn"),
            "public_visible": defaults.get("public_visible", True),
            "commercial_enabled": defaults.get("commercial_enabled", True),
            "sort_order": defaults.get("sort_order", 160),
            "execution_enabled": execution_enabled,
            "execution_blocker": execution_blocker,
            "supported_tiers": supported_tiers,
            "supported_quality_tiers": supported_tiers,
            "supported_ratios": "NOT_EXPOSED",
            "required_capability": "NOT_EXPOSED",
            "provider_capability": "NOT_EXPOSED",
            "modality": "NOT_EXPOSED",
            "executor_product_type": "NOT_EXPOSED",
            "engine_route": "NOT_EXPOSED",
            "flow_owner": "NOT_EXPOSED",
            "worker_owner": "NOT_EXPOSED",
            "source_authority": "services.video_ai_real_pricing.music_model_catalog",
        }

    elif clean_key == "subdub_service":
        from services import subtitle_dub_product_pipeline

        try:
            from providers import subtitle_dub_pipeline
            readiness = subtitle_dub_pipeline.readiness()
            ready = bool(readiness.get("public_enabled", False) or readiness.get("ready", False))
            blocker = str(readiness.get("reason", "")) if not ready else ""
        except Exception:
            ready = False
            blocker = "subdub_pipeline_unavailable"

        try:
            supported_tiers = sorted(list(subtitle_dub_product_pipeline.SUBDUB_SHARED_CORE_MODES))
        except Exception:
            supported_tiers = []

        return {
            "product_key": clean_key,
            "product_group": defaults.get("product_group", "subdub"),
            "display_name": defaults.get("display_name", "Phụ Đề & Lồng Tiếng AI (SubDub)"),
            "description": defaults.get("description", "Tạo phụ đề tự động, dịch thuật đa ngữ và lồng tiếng khớp khẩu hình"),
            "public_visible": defaults.get("public_visible", True),
            "commercial_enabled": defaults.get("commercial_enabled", True),
            "sort_order": defaults.get("sort_order", 170),
            "execution_enabled": ready,
            "execution_blocker": blocker,
            "supported_tiers": supported_tiers,
            "supported_quality_tiers": supported_tiers,
            "supported_ratios": "NOT_EXPOSED",
            "required_capability": "NOT_EXPOSED",
            "provider_capability": "NOT_EXPOSED",
            "modality": "NOT_EXPOSED",
            "executor_product_type": "NOT_EXPOSED",
            "engine_route": "NOT_EXPOSED",
            "flow_owner": "NOT_EXPOSED",
            "worker_owner": "NOT_EXPOSED",
            "source_authority": "services.subtitle_dub_product_pipeline.SUBDUB_SHARED_CORE_MODES",
        }

    elif clean_key == "chat_pro":
        from services import chat_pro_pricing

        try:
            model = chat_pro_pricing.CLAUDE_OPUS_MODEL
            supported_tiers = [model]
        except Exception:
            supported_tiers = []

        return {
            "product_key": clean_key,
            "product_group": defaults.get("product_group", "productivity"),
            "display_name": defaults.get("display_name", "Trợ Lý AI Đa Năng (Chat Pro)"),
            "description": defaults.get("description", "Hội thoại thông minh, soạn thảo nội dung và hỗ trợ công việc 24/7"),
            "public_visible": defaults.get("public_visible", True),
            "commercial_enabled": defaults.get("commercial_enabled", True),
            "sort_order": defaults.get("sort_order", 180),
            "execution_enabled": False,
            "execution_blocker": "chat_pro_readiness_authority_unproven",
            "supported_tiers": supported_tiers,
            "supported_quality_tiers": supported_tiers,
            "supported_ratios": "NOT_EXPOSED",
            "required_capability": "NOT_EXPOSED",
            "provider_capability": "NOT_EXPOSED",
            "modality": "NOT_EXPOSED",
            "executor_product_type": "NOT_EXPOSED",
            "engine_route": "NOT_EXPOSED",
            "flow_owner": "NOT_EXPOSED",
            "worker_owner": "NOT_EXPOSED",
            "source_authority": "services.chat_pro_pricing.CLAUDE_OPUS_MODEL",
        }

    raise KeyError(f"Unhandled canonical product: {clean_key}")


class _DynamicCatalog(dict):
    """Dynamic catalog mapping that resolves technical contracts fresh on access.

    Prevents stale import-time snapshotting of live technical truth.
    """
    def __getitem__(self, key: str) -> dict[str, Any]:
        return resolve_canonical_technical_contract(key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return resolve_canonical_technical_contract(key)
        except KeyError:
            return default

    def __contains__(self, key: object) -> bool:
        try:
            return resolve_canonical_product_key(str(key)) in discover_canonical_products()
        except Exception:
            return False

    def keys(self):
        return discover_canonical_products()

    def values(self):
        return [resolve_canonical_technical_contract(k) for k in discover_canonical_products()]

    def items(self):
        return [(k, resolve_canonical_technical_contract(k)) for k in discover_canonical_products()]

    def __len__(self) -> int:
        return len(discover_canonical_products())

    def __iter__(self):
        return iter(discover_canonical_products())


def get_canonical_base_products() -> dict[str, dict[str, Any]]:
    """Return dictionary of all canonical products resolved dynamically from technical authorities."""
    catalog: dict[str, dict[str, Any]] = {}
    for key in discover_canonical_products():
        catalog[key] = resolve_canonical_technical_contract(key)
    return catalog


# Dynamic backward-compatibility mapping for existing callers and test suites
BASE_PRODUCTS: dict[str, dict[str, Any]] = _DynamicCatalog()

# ─── WHITELIST & IMMUTABLE GUARDS ─────────────────────────────────────────────

EDITABLE_FIELD_WHITELIST: set[str] = {
    "display_name",
    "description",
    "product_group",
    "public_visible",
    "commercial_enabled",
    "sort_order",
}

IMMUTABLE_FIELD_KEYWORDS: set[str] = {
    "pricing",
    "price",
    "sale_price",
    "unit_xu",
    "xu",
    "cost",
    "provider",
    "provider_capability",
    "model",
    "routing",
    "credentials",
    "execution_enabled",
    "execution_blocker",
    "supported_tiers",
    "supported_quality_tiers",
    "supported_ratios",
    "wallet",
    "ledger",
    "balance",
}


def utc_now_text() -> str:
    """Format current UTC time as YYYY-MM-DD HH:MM:SS."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def ensure_admin_product_schema(conn: sqlite3.Connection) -> None:
    """Ensure the durable admin product overrides and audit tables exist.

    Additive-only migration: does not alter existing tables.
    Safe to invoke repeatedly across process startups and test setups.
    """
    conn.execute(
        """CREATE TABLE IF NOT EXISTS admin_product_overrides (
            product_key TEXT PRIMARY KEY,
            display_name TEXT,
            description TEXT,
            product_group TEXT,
            public_visible INTEGER NOT NULL DEFAULT 1,
            commercial_enabled INTEGER NOT NULL DEFAULT 1,
            sort_order INTEGER NOT NULL DEFAULT 100,
            version INTEGER NOT NULL DEFAULT 1,
            updated_at DATETIME NOT NULL,
            updated_by TEXT NOT NULL DEFAULT '',
            update_reason TEXT NOT NULL DEFAULT ''
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_admin_product_overrides_group ON admin_product_overrides(product_group)"
    )

    conn.execute(
        """CREATE TABLE IF NOT EXISTS admin_product_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_key TEXT NOT NULL,
            actor_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            reason TEXT NOT NULL,
            previous_version INTEGER NOT NULL,
            new_version INTEGER NOT NULL,
            before_json TEXT NOT NULL,
            after_json TEXT NOT NULL,
            accepted_changes_json TEXT NOT NULL,
            request_id TEXT DEFAULT '',
            created_at DATETIME NOT NULL
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_admin_product_audit_key ON admin_product_audit(product_key)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_admin_product_audit_actor ON admin_product_audit(actor_id)"
    )


def resolve_effective_product(
    product_key: str,
    override_row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve effective product read model from canonical source contract and durable override.

    Formula:
    CANONICAL BOT PRODUCT CONTRACT + VALID DURABLE COMMERCIAL OVERRIDE = EFFECTIVE PRODUCT READ MODEL

    Guarantees:
    - Fails closed on unknown product
    - Hard execution safety lock is immutable: commercial_enabled=True NEVER enables execution_enabled
    - Technical fields are always fresh from canonical authorities (supported_tiers, supported_ratios, modality, etc.)
    - Version is 1 (base default) or override version
    """
    canonical_key = resolve_canonical_product_key(product_key)
    if canonical_key not in discover_canonical_products():
        raise KeyError(f"Unknown product key: {product_key}")

    base = resolve_canonical_technical_contract(canonical_key)
    effective = deepcopy(base)

    if override_row:
        if "display_name" in override_row and override_row["display_name"] is not None:
            effective["display_name"] = str(override_row["display_name"]).strip()
        if "description" in override_row and override_row["description"] is not None:
            effective["description"] = str(override_row["description"]).strip()
        if "product_group" in override_row and override_row["product_group"] is not None:
            effective["product_group"] = str(override_row["product_group"]).strip()
        if "public_visible" in override_row and override_row["public_visible"] is not None:
            effective["public_visible"] = bool(override_row["public_visible"])
        if "commercial_enabled" in override_row and override_row["commercial_enabled"] is not None:
            effective["commercial_enabled"] = bool(override_row["commercial_enabled"])
        if "sort_order" in override_row and override_row["sort_order"] is not None:
            effective["sort_order"] = int(override_row["sort_order"])
        effective["version"] = int(override_row.get("version", 1))
        effective["updated_at"] = override_row.get("updated_at")
        effective["updated_by"] = override_row.get("updated_by")
    else:
        effective["version"] = 1
        effective["updated_at"] = None
        effective["updated_by"] = None

    # CRITICAL INVARIANT: Hard execution safety lock
    # A commercial toggle must never override an execution safety lock.
    if not base.get("execution_enabled", False):
        effective["execution_enabled"] = False
    effective["execution_blocker"] = base.get("execution_blocker", "")

    # Ensure technical fields are always pure canonical reflection
    effective["supported_tiers"] = base.get("supported_tiers", [])
    effective["supported_quality_tiers"] = base.get("supported_quality_tiers", [])
    effective["supported_ratios"] = base.get("supported_ratios", "NOT_EXPOSED")
    effective["provider_capability"] = base.get("provider_capability", "NOT_EXPOSED")
    effective["required_capability"] = base.get("required_capability", "NOT_EXPOSED")
    effective["modality"] = base.get("modality", "NOT_EXPOSED")
    effective["executor_product_type"] = base.get("executor_product_type", "NOT_EXPOSED")
    effective["engine_route"] = base.get("engine_route", "NOT_EXPOSED")
    effective["flow_owner"] = base.get("flow_owner", "NOT_EXPOSED")
    effective["worker_owner"] = base.get("worker_owner", "NOT_EXPOSED")
    effective["source_authority"] = base.get("source_authority", "")

    effective["has_override"] = override_row is not None
    return effective


def get_canonical_product_collection(
    db_path: str,
) -> tuple[bool, dict[str, Any], int]:
    """Retrieve full collection of canonical products with effective overrides.

    Returns:
        (ok, response_dict, http_status)
    """
    try:
        conn = sqlite3.connect(db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        ensure_admin_product_schema(conn)

        c = conn.cursor()
        c.execute("SELECT * FROM admin_product_overrides")
        override_rows = {row["product_key"]: dict(row) for row in c.fetchall()}
        conn.close()
    except Exception as exc:
        logger.error(f"Error querying admin_product_overrides: {exc}")
        override_rows = {}

    products = []
    for key in discover_canonical_products():
        override = override_rows.get(key)
        effective = resolve_effective_product(key, override)
        products.append(effective)

    # Sort by sort_order ascending, then product_key
    products.sort(key=lambda p: (p.get("sort_order", 100), p.get("product_key", "")))

    return (
        True,
        {
            "ok": True,
            "count": len(products),
            "products": products,
        },
        200,
    )


def get_canonical_product_single(
    product_key: str,
    db_path: str,
) -> tuple[bool, dict[str, Any], int]:
    """Retrieve single canonical product with base values and effective override.

    Returns:
        (ok, response_dict, http_status)
    """
    clean_key = resolve_canonical_product_key(product_key)
    if clean_key not in discover_canonical_products():
        return (
            False,
            {
                "ok": False,
                "error_code": "PRODUCT_NOT_FOUND",
                "message": f"Product '{product_key}' is not recognized in canonical Bot catalog",
            },
            404,
        )

    try:
        conn = sqlite3.connect(db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        ensure_admin_product_schema(conn)

        c = conn.cursor()
        c.execute("SELECT * FROM admin_product_overrides WHERE product_key = ?", (clean_key,))
        row = c.fetchone()
        override_row = dict(row) if row else None
        conn.close()
    except Exception as exc:
        logger.error(f"Error querying single product override: {exc}")
        override_row = None

    effective = resolve_effective_product(clean_key, override_row)
    base = resolve_canonical_technical_contract(clean_key)

    return (
        True,
        {
            "ok": True,
            "product_key": clean_key,
            "base": base,
            "effective": effective,
            "version": effective["version"],
            "has_override": override_row is not None,
        },
        200,
    )


def update_canonical_product(
    product_key: str,
    expected_version: int,
    changes: dict[str, Any],
    reason: str,
    actor_id: str = "",
    request_id: str = "",
    db_path: str = "",
) -> tuple[bool, dict[str, Any], int]:
    """Atomically mutate product commercial metadata with CAS versioning and audit record.

    Validates:
    1. Product key existence (fails closed)
    2. Editable whitelist validation (rejects pricing, providers, execution locks)
    3. Type and range validation
    4. Expected version CAS check (rejects stale writes with 409 Conflict)
    5. Atomic transaction: write override + append audit record
    6. Returns write receipt and deterministic canonical readback verification

    Returns:
        (ok, response_dict, http_status)
    """
    clean_key = resolve_canonical_product_key(product_key)
    if clean_key not in discover_canonical_products():
        return (
            False,
            {
                "ok": False,
                "error_code": "PRODUCT_NOT_FOUND",
                "message": f"Cannot update unrecognized product '{product_key}'",
            },
            404,
        )

    clean_reason = str(reason or "").strip()
    if not clean_reason:
        return (
            False,
            {
                "ok": False,
                "error_code": "MISSING_REASON",
                "message": "Mutation reason is required and cannot be blank",
            },
            400,
        )

    if not isinstance(expected_version, int) or expected_version < 1:
        return (
            False,
            {
                "ok": False,
                "error_code": "INVALID_EXPECTED_VERSION",
                "message": "expected_version must be a positive integer >= 1",
            },
            400,
        )

    if not isinstance(changes, dict) or not changes:
        return (
            False,
            {
                "ok": False,
                "error_code": "EMPTY_CHANGES",
                "message": "changes dictionary must not be empty",
            },
            400,
        )

    # 1. Guard against immutable fields
    for field_name in changes.keys():
        lower_field = str(field_name).strip().lower()
        if lower_field in IMMUTABLE_FIELD_KEYWORDS or any(
            token in lower_field for token in ("price", "pricing", "cost", "provider", "routing", "secret", "token", "balance")
        ):
            return (
                False,
                {
                    "ok": False,
                    "error_code": "IMMUTABLE_FIELD_MODIFICATION_FORBIDDEN",
                    "message": f"Field '{field_name}' is immutable in B01. Pricing, routing, and provider logic cannot be modified via Product API.",
                },
                400,
            )
        if field_name not in EDITABLE_FIELD_WHITELIST:
            return (
                False,
                {
                    "ok": False,
                    "error_code": "UNKNOWN_OR_DISALLOWED_FIELD",
                    "message": f"Field '{field_name}' is not in editable whitelist: {sorted(EDITABLE_FIELD_WHITELIST)}",
                },
                400,
            )

    # 2. Validate types and bounds
    accepted_changes: dict[str, Any] = {}
    if "display_name" in changes:
        val = str(changes["display_name"]).strip()
        if not val or len(val) > 100:
            return False, {"ok": False, "error_code": "INVALID_DISPLAY_NAME", "message": "display_name must be non-empty and <= 100 chars"}, 400
        accepted_changes["display_name"] = val

    if "description" in changes:
        val = str(changes["description"]).strip()
        if len(val) > 1000:
            return False, {"ok": False, "error_code": "INVALID_DESCRIPTION", "message": "description must be <= 1000 chars"}, 400
        accepted_changes["description"] = val

    if "product_group" in changes:
        val = str(changes["product_group"]).strip().lower()
        if not val or len(val) > 50:
            return False, {"ok": False, "error_code": "INVALID_PRODUCT_GROUP", "message": "product_group must be non-empty and <= 50 chars"}, 400
        accepted_changes["product_group"] = val

    if "public_visible" in changes:
        accepted_changes["public_visible"] = bool(changes["public_visible"])

    if "commercial_enabled" in changes:
        accepted_changes["commercial_enabled"] = bool(changes["commercial_enabled"])

    if "sort_order" in changes:
        try:
            so = int(changes["sort_order"])
            if so < 0 or so > 10000:
                raise ValueError()
            accepted_changes["sort_order"] = so
        except Exception:
            return False, {"ok": False, "error_code": "INVALID_SORT_ORDER", "message": "sort_order must be an integer between 0 and 10000"}, 400

    clean_actor = str(actor_id or DEFAULT_ADMIN_ID).strip()
    now_ts = utc_now_text()

    # 3. Execute atomic transaction with CAS check
    try:
        conn = sqlite3.connect(db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        ensure_admin_product_schema(conn)

        conn_conflict = False
        with conn:
            c = conn.cursor()
            c.execute("SELECT * FROM admin_product_overrides WHERE product_key = ?", (clean_key,))
            existing_row = c.fetchone()
            current_version = int(existing_row["version"]) if existing_row else 1

            if current_version != expected_version:
                conn_conflict = True
            else:
                new_version = current_version + 1
                before_override = dict(existing_row) if existing_row else None
                before_effective = resolve_effective_product(clean_key, before_override)

                merged_override = {
                    "display_name": accepted_changes.get("display_name", before_effective["display_name"]),
                    "description": accepted_changes.get("description", before_effective["description"]),
                    "product_group": accepted_changes.get("product_group", before_effective["product_group"]),
                    "public_visible": int(accepted_changes.get("public_visible", before_effective["public_visible"])),
                    "commercial_enabled": int(accepted_changes.get("commercial_enabled", before_effective["commercial_enabled"])),
                    "sort_order": int(accepted_changes.get("sort_order", before_effective["sort_order"])),
                    "version": new_version,
                    "updated_at": now_ts,
                    "updated_by": clean_actor,
                    "update_reason": clean_reason,
                }

                c.execute(
                    """INSERT INTO admin_product_overrides (
                        product_key, display_name, description, product_group,
                        public_visible, commercial_enabled, sort_order,
                        version, updated_at, updated_by, update_reason
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(product_key) DO UPDATE SET
                        display_name = excluded.display_name,
                        description = excluded.description,
                        product_group = excluded.product_group,
                        public_visible = excluded.public_visible,
                        commercial_enabled = excluded.commercial_enabled,
                        sort_order = excluded.sort_order,
                        version = excluded.version,
                        updated_at = excluded.updated_at,
                        updated_by = excluded.updated_by,
                        update_reason = excluded.update_reason
                    """,
                    (
                        clean_key,
                        merged_override["display_name"],
                        merged_override["description"],
                        merged_override["product_group"],
                        merged_override["public_visible"],
                        merged_override["commercial_enabled"],
                        merged_override["sort_order"],
                        new_version,
                        now_ts,
                        clean_actor,
                        clean_reason,
                    ),
                )

                after_effective = resolve_effective_product(clean_key, merged_override)

                # Append audit record
                c.execute(
                    """INSERT INTO admin_product_audit (
                        product_key, actor_id, timestamp, reason,
                        previous_version, new_version,
                        before_json, after_json, accepted_changes_json,
                        request_id, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        clean_key,
                        clean_actor,
                        now_ts,
                        clean_reason,
                        current_version,
                        new_version,
                        json.dumps(before_effective, sort_keys=True, ensure_ascii=False),
                        json.dumps(after_effective, sort_keys=True, ensure_ascii=False),
                        json.dumps(accepted_changes, sort_keys=True, ensure_ascii=False),
                        str(request_id or "").strip(),
                        now_ts,
                    ),
                )

        conn.close()

        if conn_conflict:
            return (
                False,
                {
                    "ok": False,
                    "error_code": "VERSION_CONFLICT_STALE_WRITE",
                    "message": f"Stale write rejected: expected_version={expected_version} but current_version={current_version}",
                    "current_version": current_version,
                    "expected_version": expected_version,
                },
                409,
            )

        # 4. Perform deterministic readback verification
        _, readback_res, _ = get_canonical_product_single(clean_key, db_path)
        readback_effective = readback_res.get("effective", {})

        # Verify readback matches committed update
        readback_match = True
        for k, v in accepted_changes.items():
            if readback_effective.get(k) != v:
                readback_match = False
                break
        if readback_effective.get("version") != new_version:
            readback_match = False

        # Generate write receipt
        mutation_digest = hashlib.sha256(
            json.dumps(accepted_changes, sort_keys=True).encode("utf-8")
        ).hexdigest()

        write_receipt = {
            "receipt_id": f"rcpt-prod-{clean_key}-v{new_version}-{int(time.time())}",
            "product_key": clean_key,
            "version": new_version,
            "timestamp": now_ts,
            "actor_id": clean_actor,
            "reason": clean_reason,
            "mutation_digest": mutation_digest,
        }

        return (
            True,
            {
                "ok": True,
                "product_key": clean_key,
                "previous_version": current_version,
                "new_version": new_version,
                "accepted_changes": accepted_changes,
                "write_receipt": write_receipt,
                "effective_product": readback_effective,
                "readback_match": readback_match,
            },
            200,
        )

    except Exception as exc:
        logger.error(f"Error updating canonical product {clean_key}: {exc}")
        return (
            False,
            {
                "ok": False,
                "error_code": "PRODUCT_UPDATE_FAILED",
                "message": f"Failed to persist product update: {exc}",
            },
            500,
        )
