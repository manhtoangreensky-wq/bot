"""Product Video provider catalog and tier/model routing.

This module is deliberately provider-call free. It resolves which provider
model should be used for a confirmed Product Video job and describes the
payload contract the worker must obey before it submits anything.
"""

from __future__ import annotations

import json
import os
import urllib.parse
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG_PATH = ROOT_DIR / "config" / "video_provider_catalog.json"
DEFAULT_ROUTING_PATH = ROOT_DIR / "config" / "product_video_model_routing.json"
DEFAULT_PROVIDER_CHAIN = ["shopaikey_video", "key4u_video", "toanaas_video", "veo", "kling", "generic_http"]
PROVIDER_ENV_PREFIX = {
    "shopaikey_video": "SHOPAIKEY_VIDEO",
    "key4u_video": "KEY4U_VIDEO",
    "toanaas_video": "VIDEO_TOANAAS",
    "veo": "VIDEO_VEO",
    "kling": "VIDEO_KLING",
    "generic_http": "VIDEO_GENERIC_HTTP",
}
MODEL_UNKNOWN = "CONFIG_MODEL_UNKNOWN"
CONTRACT_MISSING = "provider_contract_missing_no_charge"
KEY4U_EXCLUSIVE_ENDPOINT_MISSING = "key4u_model_requires_exclusive_interface_no_endpoint"
KEY4U_MODEL_CONTRACT_MISSING = "key4u_model_contract_missing_no_charge"
KEY4U_COST_ROUTING_OVERRIDE_WARNING = "COST_ROUTING_OVERRIDE_KEY4U_PRIMARY"
PUBLIC_LOW_TIER_KEY4U_WARNING = "PUBLIC_LOW_TIER_PRIMARY_PROVIDER_NOT_COST_OPTIMAL"

_URL_PREFIXES = ("http://", "https://")
_MEDIA_INPUT_FIELDS = ("storyboard", "image_paths", "source_video_path")
_TIER_COST_ORDER = {
    "low": 1,
    "basic": 2,
    "common": 3,
    "standard": 4,
    "long": 5,
    "advanced": 5,
    "high": 6,
    "future_1000": 7,
    "future_1200": 8,
    "future_1500": 9,
}
_KEY4U_EXCLUSIVE_ENDPOINT_ENVS = {
    "kling": (
        "KEY4U_KLING_VIDEO_ENDPOINT",
        "KEY4U_KLING_ENDPOINT",
        "KEY4U_KELING_VIDEO_ENDPOINT",
        "KEY4U_KLING_VIDEO_SUBMIT_URL",
        "KEY4U_KELING_VIDEO_SUBMIT_URL",
    ),
    "keling": (
        "KEY4U_KELING_VIDEO_ENDPOINT",
        "KEY4U_KLING_VIDEO_ENDPOINT",
        "KEY4U_KELING_VIDEO_SUBMIT_URL",
        "KEY4U_KLING_VIDEO_SUBMIT_URL",
    ),
    "minimax_hailuo": (
        "KEY4U_HAILUO_VIDEO_ENDPOINT",
        "KEY4U_MINIMAX_HAILUO_VIDEO_ENDPOINT",
        "KEY4U_MINIMAX_VIDEO_ENDPOINT",
        "KEY4U_HAILUO_VIDEO_SUBMIT_URL",
    ),
    "google_veo": (
        "KEY4U_VEO_VIDEO_ENDPOINT",
        "KEY4U_GOOGLE_VEO_VIDEO_ENDPOINT",
        "KEY4U_VEO_VIDEO_SUBMIT_URL",
    ),
}
_KEY4U_EXCLUSIVE_POLL_ENVS = {
    "kling": ("KEY4U_KLING_VIDEO_POLL_URL", "KEY4U_KLING_POLL_URL", "KEY4U_KELING_VIDEO_POLL_URL"),
    "keling": ("KEY4U_KELING_VIDEO_POLL_URL", "KEY4U_KLING_VIDEO_POLL_URL"),
    "minimax_hailuo": ("KEY4U_HAILUO_VIDEO_POLL_URL", "KEY4U_MINIMAX_HAILUO_VIDEO_POLL_URL", "KEY4U_MINIMAX_VIDEO_POLL_URL"),
    "google_veo": ("KEY4U_VEO_VIDEO_POLL_URL", "KEY4U_GOOGLE_VEO_VIDEO_POLL_URL"),
}
_KEY4U_GENERIC_ENDPOINT_ENVS = (
    "KEY4U_VIDEO_ENDPOINT",
    "KEY4U_VIDEO_SUBMIT_URL",
)
_KEY4U_GENERIC_POLL_ENVS = (
    "KEY4U_VIDEO_POLL_ENDPOINT",
    "KEY4U_VIDEO_POLL_URL",
)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return {}
    return data if isinstance(data, dict) else {}


def load_video_provider_catalog(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    return _load_json(Path(path) if path else DEFAULT_CATALOG_PATH)


def load_product_video_model_routing(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    return _load_json(Path(path) if path else DEFAULT_ROUTING_PATH)


def split_provider_chain(value: Any) -> list[str]:
    aliases = {
        "shopaikey": "shopaikey_video",
        "shopai": "shopaikey_video",
        "key4u": "key4u_video",
        "k4u": "key4u_video",
        "toanaas": "toanaas_video",
        "generic": "generic_http",
    }
    if isinstance(value, (list, tuple)):
        raw_items = [str(item or "") for item in value]
    else:
        raw_items = str(value or "").replace(">", ",").replace("|", ",").split(",")
    result: list[str] = []
    for raw in raw_items:
        token = aliases.get(raw.strip().lower(), raw.strip().lower())
        if token and token not in result:
            result.append(token)
    return result


def effective_provider_chain(env: dict[str, str] | os._Environ[str] | None = None, routing: dict[str, Any] | None = None) -> list[str]:
    data = env or os.environ
    raw = data.get("VIDEO_PROVIDER_CHAIN") if hasattr(data, "get") else ""
    if raw:
        return split_provider_chain(raw)
    route = routing or load_product_video_model_routing()
    return split_provider_chain(route.get("default_provider_chain") or DEFAULT_PROVIDER_CHAIN)


def normalize_tier(value: Any, routing: dict[str, Any] | None = None) -> str:
    route = routing or load_product_video_model_routing()
    aliases = {str(k).strip().lower(): str(v).strip().lower() for k, v in (route.get("tier_aliases") or {}).items()}
    token = str(value or "").strip().lower()
    return aliases.get(token, token or "basic") or "basic"


def provider_model_config(provider: str, model: str, catalog: dict[str, Any] | None = None) -> dict[str, Any]:
    cat = catalog or load_video_provider_catalog()
    providers = cat.get("providers") if isinstance(cat.get("providers"), dict) else {}
    provider_cfg = providers.get(str(provider or "").strip().lower()) if isinstance(providers, dict) else {}
    models = provider_cfg.get("models") if isinstance(provider_cfg, dict) else {}
    cfg = models.get(str(model or "").strip()) if isinstance(models, dict) else {}
    if not isinstance(cfg, dict):
        return {}
    result = dict(cfg)
    result["provider"] = str(provider or "").strip().lower()
    result["model"] = str(model or "").strip()
    return result


def payload_adapter_contract(adapter_name: str, catalog: dict[str, Any] | None = None) -> dict[str, Any]:
    cat = catalog or load_video_provider_catalog()
    adapters = cat.get("payload_adapters") if isinstance(cat.get("payload_adapters"), dict) else {}
    contract = adapters.get(str(adapter_name or "").strip()) if isinstance(adapters, dict) else {}
    return dict(contract) if isinstance(contract, dict) else {}


def payload_contract_for_model(provider: str, model: str, catalog: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = provider_model_config(provider, model, catalog)
    if not cfg:
        return {}
    contract = payload_adapter_contract(str(cfg.get("payload_adapter") or ""), catalog)
    contract.update(
        {
            "provider": str(provider or "").strip().lower(),
            "model": str(model or "").strip(),
            "family": str(cfg.get("family") or contract.get("family") or ""),
            "quality": str(cfg.get("quality") or ""),
            "cost_tier": str(cfg.get("cost_tier") or cfg.get("tier") or ""),
            "supports_concat": bool(cfg.get("supports_concat")),
            "clip_seconds": int(cfg.get("clip_seconds") or 0),
            "payload_adapter": str(cfg.get("payload_adapter") or ""),
            "capabilities": list(cfg.get("capabilities") or []),
        }
    )
    return contract


def _valid_endpoint_url(value: Any) -> bool:
    text = str(value or "").strip()
    return bool(text and text.lower().startswith(_URL_PREFIXES))


def _first_endpoint(env: dict[str, str] | os._Environ[str], names: tuple[str, ...]) -> tuple[str, str]:
    for name in names:
        value = str(env.get(name) or "").strip()
        if _valid_endpoint_url(value):
            return value, name
    return "", ""


def _key4u_official_google_veo_endpoints(
    env: dict[str, str] | os._Environ[str],
) -> tuple[str, str, str, str]:
    auth_present = any(
        str(env.get(name) or "").strip()
        for name in (
            "KEY4U_VIDEO_AUTH_HEADER_VALUE",
            "VIDEO_KEY4U_AUTH_HEADER_VALUE",
            "KEY4U_API_KEY",
            "KEY4U_TOKEN",
        )
    )
    if not auth_present:
        return "", "", "", ""
    base = next(
        (
            str(env.get(name) or "").strip().rstrip("/")
            for name in ("KEY4U_BASE_URL", "KEY4U_API_BASE")
            if _valid_endpoint_url(env.get(name))
        ),
        "https://api.key4u.vn",
    )
    return (
        f"{base}/v1/video/create",
        "derived:key4u_unified_video_create",
        f"{base}/v1/video/query?id={{task_id}}",
        "derived:key4u_unified_video_query",
    )


def _normalize_key4u_official_google_veo_submit_endpoint(
    submit_url: str,
    submit_source: str,
) -> tuple[str, str]:
    parsed = urllib.parse.urlsplit(str(submit_url or "").strip())
    if (
        (parsed.hostname or "").lower() in {"api.key4u.vn", "api.key4u.shop"}
        and parsed.path.rstrip("/")
        in {"/v1/videos", "/v1/videos/generations"}
    ):
        normalized = urllib.parse.urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                "/v1/video/create",
                "",
                "",
            )
        )
        return normalized, (
            f"normalized_unified:{submit_source or 'key4u_official_videos'}"
        )
    return submit_url, submit_source


def _cost_tier_allowed(product_tier: str, model_cfg: dict[str, Any]) -> bool:
    model_cost = str(model_cfg.get("cost_tier") or model_cfg.get("tier") or "").strip().lower()
    if not model_cost:
        return True
    product_score = _TIER_COST_ORDER.get(normalize_tier(product_tier), 2)
    model_score = _TIER_COST_ORDER.get(normalize_tier(model_cost), product_score)
    return model_score <= product_score


def model_interface_contract(
    provider: str,
    model: str,
    *,
    env: dict[str, str] | os._Environ[str] | None = None,
    catalog: dict[str, Any] | None = None,
) -> dict[str, Any]:
    provider_name = str(provider or "").strip().lower()
    data = env or os.environ
    cfg = provider_model_config(provider_name, model, catalog)
    family = str(cfg.get("family") or "").strip().lower()
    base = {
        "provider": provider_name,
        "model": str(model or "").strip(),
        "selected_family": family,
        "provider_interface": provider_name or "unknown",
        "provider_endpoint_source": "general",
        "provider_submit_url_override": "",
        "provider_poll_url_override": "",
        "contract_validation_status": "ok" if cfg else CONTRACT_MISSING,
        "contract_block_reason": "" if cfg else CONTRACT_MISSING,
        "model_requires_exclusive_interface": False,
        "submit_skipped_due_to_contract": False,
    }
    if not cfg:
        return base
    if provider_name != "key4u_video":
        return base
    if family in {"kling", "keling"}:
        submit_url, submit_source = _first_endpoint(data, _KEY4U_EXCLUSIVE_ENDPOINT_ENVS.get(family, _KEY4U_EXCLUSIVE_ENDPOINT_ENVS["kling"]))
        poll_url, poll_source = _first_endpoint(data, _KEY4U_EXCLUSIVE_POLL_ENVS.get(family, ()))
        base.update(
            {
                "provider_interface": "key4u_kling_exclusive",
                "provider_endpoint_source": submit_source or "missing:key4u_kling_exclusive",
                "provider_submit_url_override": submit_url,
                "provider_poll_url_override": poll_url,
                "provider_poll_endpoint_source": poll_source,
                "model_requires_exclusive_interface": True,
            }
        )
        if not submit_url:
            base.update(
                {
                    "contract_validation_status": "blocked",
                    "contract_block_reason": KEY4U_EXCLUSIVE_ENDPOINT_MISSING,
                    "submit_skipped_due_to_contract": True,
                }
            )
        return base
    if family in {"minimax_hailuo", "google_veo"}:
        submit_url, submit_source = _first_endpoint(data, _KEY4U_EXCLUSIVE_ENDPOINT_ENVS.get(family, ()))
        poll_url, poll_source = _first_endpoint(data, _KEY4U_EXCLUSIVE_POLL_ENVS.get(family, ()))
        if family == "google_veo" and submit_url:
            submit_url, submit_source = (
                _normalize_key4u_official_google_veo_submit_endpoint(
                    submit_url,
                    submit_source,
                )
            )
        if family == "google_veo" and (not submit_url or not poll_url):
            (
                derived_submit_url,
                derived_submit_source,
                derived_poll_url,
                derived_poll_source,
            ) = _key4u_official_google_veo_endpoints(data)
            if not submit_url:
                submit_url, submit_source = (
                    derived_submit_url,
                    derived_submit_source,
                )
            if not poll_url:
                poll_url, poll_source = derived_poll_url, derived_poll_source
        base.update(
            {
                "provider_interface": f"key4u_{family}_exclusive",
                "provider_endpoint_source": submit_source or f"missing:key4u_{family}_contract",
                "provider_submit_url_override": submit_url,
                "provider_poll_url_override": poll_url,
                "provider_poll_endpoint_source": poll_source,
                "model_requires_exclusive_interface": True,
            }
        )
        if not submit_url:
            base.update(
                {
                    "contract_validation_status": "blocked",
                    "contract_block_reason": KEY4U_MODEL_CONTRACT_MISSING,
                    "submit_skipped_due_to_contract": True,
                }
            )
        return base
    submit_url, submit_source = _first_endpoint(data, _KEY4U_GENERIC_ENDPOINT_ENVS)
    poll_url, poll_source = _first_endpoint(data, _KEY4U_GENERIC_POLL_ENVS)
    base.update(
        {
            "provider_interface": "key4u_catalog_generic",
            "provider_endpoint_source": submit_source or "missing:key4u_catalog_generic",
            "provider_submit_url_override": submit_url,
            "provider_poll_url_override": poll_url,
            "provider_poll_endpoint_source": poll_source,
            "model_requires_exclusive_interface": False,
        }
    )
    if not submit_url:
        base.update(
            {
                "contract_validation_status": "blocked",
                "contract_block_reason": KEY4U_MODEL_CONTRACT_MISSING,
                "submit_skipped_due_to_contract": True,
            }
        )
    return base


def normalize_capability_values(value: Any) -> list[str]:
    if value is None:
        raw_values: list[Any] = []
    elif isinstance(value, str):
        raw_values = value.replace("|", ",").replace(";", ",").split(",")
    else:
        try:
            raw_values = list(value)
        except TypeError:
            raw_values = [value]
    aliases = {
        "text_to_video_or_scene_engine": "text_to_video_or_scene_video",
        "text_to_video_or_scene": "text_to_video_or_scene_video",
        "scene_engine": "scene_video",
        "multiscene_video": "multi_scene_video",
        "multi_scene": "multi_scene_video",
    }
    result: list[str] = []
    for item in raw_values:
        token = str(item or "").strip().lower().replace("-", "_")
        token = aliases.get(token, token)
        if token and token not in result:
            result.append(token)
    return result


def capability_options(required_capability: str) -> list[str]:
    cap = (normalize_capability_values([required_capability]) or ["text_to_video"])[0]
    mapping = {
        "text_to_video_or_scene_video": ["multi_scene_video", "scene_video", "text_to_video"],
        "text_to_video_or_scene_engine": ["multi_scene_video", "scene_video", "text_to_video"],
        "multi_scene_video": ["multi_scene_video", "scene_video", "text_to_video"],
        "scene_video": ["scene_video", "multi_scene_video", "text_to_video"],
        "first_last_frame_video": ["first_last_frame_video", "image_to_video"],
        "delegates_to_selected_product": ["multi_scene_video", "scene_video", "text_to_video", "image_to_video", "video_to_video"],
    }
    return mapping.get(cap, [cap] if cap else ["text_to_video"])


def _model_supports(cfg: dict[str, Any], required_capability: str, *, requires_concat: bool = False) -> bool:
    if not cfg:
        return False
    if requires_concat and not cfg.get("supports_concat"):
        return False
    supported = set(normalize_capability_values(cfg.get("capabilities") or []))
    return any(option in supported for option in capability_options(required_capability))


def _provider_env_model_names(provider: str, tier: str) -> list[str]:
    prefix = PROVIDER_ENV_PREFIX.get(str(provider or "").strip().lower(), "")
    if not prefix:
        return []
    tier_key = str(tier or "basic").strip().upper()
    return [
        f"{prefix}_MODEL_{tier_key}",
        f"{prefix}_MODEL_MULTICLIP",
        f"{prefix}_MODEL_DEFAULT",
    ]


def _candidate_from_entry(provider: str, model: str, source: str, catalog: dict[str, Any]) -> dict[str, Any]:
    cfg = provider_model_config(provider, model, catalog)
    return {"provider": provider, "model": model, "source": source, "config": cfg}


def _request_defaults(value: Any, fallback_duration: int = 0) -> dict[str, Any]:
    """Normalize route-owned provider defaults without inventing payload fields."""

    raw = dict(value) if isinstance(value, dict) else {}
    result = {
        str(key): item
        for key, item in raw.items()
        if str(key).strip() and item not in (None, "")
    }
    if result.get("duration") in (None, "") and int(fallback_duration or 0) > 0:
        result["duration"] = int(fallback_duration)
    if result.get("duration") not in (None, ""):
        try:
            result["duration"] = max(1, int(round(float(result["duration"]))))
        except (TypeError, ValueError):
            result.pop("duration", None)
    return result


def _routing_candidates(
    tier: str,
    provider_chain: list[str],
    catalog: dict[str, Any],
    routing: dict[str, Any],
    env: dict[str, str] | os._Environ[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    candidates: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    env_override_detected = False
    tier_cfg = (routing.get("tiers") or {}).get(tier) if isinstance(routing.get("tiers"), dict) else {}
    preferred = [dict(item) for item in (tier_cfg or {}).get("preferred", []) if isinstance(item, dict)]
    tier_duration = int((tier_cfg or {}).get("clip_seconds") or 0)
    tier_defaults = _request_defaults((tier_cfg or {}).get("request_defaults"), tier_duration)

    for provider in provider_chain:
        for env_name in _provider_env_model_names(provider, tier):
            value = str(env.get(env_name) or "").strip()
            if not value:
                continue
            env_override_detected = True
            if provider_model_config(provider, value, catalog):
                candidate = _candidate_from_entry(provider, value, f"env:{env_name}", catalog)
                candidate["request_defaults"] = dict(tier_defaults)
                candidates.append(candidate)
                break
            rejected.append({"provider": provider, "model": value, "reason": MODEL_UNKNOWN, "source": f"env:{env_name}"})

    for idx, entry in enumerate(preferred):
        provider = str(entry.get("provider") or "").strip().lower()
        model = str(entry.get("model") or "").strip()
        if provider not in provider_chain:
            continue
        candidate = _candidate_from_entry(provider, model, f"config:tier:{tier}", catalog)
        candidate["role"] = str(entry.get("role") or ("primary" if idx == 0 else "fallback"))
        candidate["cost_tier"] = str(entry.get("cost_tier") or tier)
        entry_defaults = dict(tier_defaults)
        entry_defaults.update(_request_defaults(entry.get("request_defaults"), tier_duration))
        candidate["request_defaults"] = _request_defaults(entry_defaults, tier_duration)
        candidates.append(candidate)

    # Canonical tiers own their exact fallback list. A generic catalog fallback
    # is only allowed for legacy/custom routing that has no preferred entries.
    if not preferred:
        providers = catalog.get("providers") if isinstance(catalog.get("providers"), dict) else {}
        for provider in provider_chain:
            provider_cfg = providers.get(provider) if isinstance(providers, dict) else {}
            models = provider_cfg.get("models") if isinstance(provider_cfg, dict) else {}
            for model in models.keys() if isinstance(models, dict) else []:
                candidate = _candidate_from_entry(provider, str(model), "catalog:fallback", catalog)
                candidate["role"] = "fallback"
                candidate["cost_tier"] = str((candidate.get("config") or {}).get("cost_tier") or tier)
                candidate["request_defaults"] = _request_defaults({}, tier_duration)
                candidates.append(candidate)
                break

    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in candidates:
        key = (str(item.get("provider") or ""), str(item.get("model") or ""), str(item.get("source") or ""))
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped, rejected, env_override_detected


def resolve_product_video_model(
    *,
    tier: Any = "basic",
    provider_chain: Any = None,
    scene_count: int = 1,
    required_capability: str = "text_to_video_or_scene_video",
    requires_concat: bool = True,
    env: dict[str, str] | os._Environ[str] | None = None,
    catalog: dict[str, Any] | None = None,
    routing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = env or os.environ
    cat = catalog or load_video_provider_catalog()
    route = routing or load_product_video_model_routing()
    tier_key = normalize_tier(tier, route)
    chain = split_provider_chain(provider_chain) if provider_chain not in (None, "", []) else effective_provider_chain(data, route)
    candidates, rejected, env_override_detected = _routing_candidates(tier_key, chain, cat, route, data)
    default_chain = split_provider_chain(route.get("default_provider_chain") or DEFAULT_PROVIDER_CHAIN)
    key4u_primary_override = bool(tier_key in {"low", "basic"} and chain and chain[0] == "key4u_video")
    candidate_list_compact: list[dict[str, Any]] = []
    for candidate in candidates:
        provider = str(candidate.get("provider") or "")
        model = str(candidate.get("model") or "")
        cfg = dict(candidate.get("config") or {})
        candidate_interface = model_interface_contract(provider, model, env=data, catalog=cat)
        candidate_list_compact.append(
            {
                "provider": provider,
                "model": model,
                "family": str(cfg.get("family") or ""),
                "cost_tier": str(cfg.get("cost_tier") or candidate.get("cost_tier") or ""),
                "role": str(candidate.get("role") or ""),
                "request_defaults": _request_defaults(candidate.get("request_defaults")),
                "required_capability": required_capability,
                "supports_concat": bool(cfg.get("supports_concat")),
                "contract_status": str(candidate_interface.get("contract_validation_status") or ""),
                "contract_block_reason": str(candidate_interface.get("contract_block_reason") or ""),
            }
        )
    for item in candidates:
        provider = str(item.get("provider") or "")
        model = str(item.get("model") or "")
        cfg = dict(item.get("config") or {})
        candidate_interface = model_interface_contract(provider, model, env=data, catalog=cat)
        if not cfg:
            rejected.append({"provider": provider, "model": model, "reason": MODEL_UNKNOWN, "source": item.get("source")})
            continue
        if not _cost_tier_allowed(tier_key, cfg):
            rejected.append({"provider": provider, "model": model, "reason": "model_cost_tier_exceeds_product_tier", "source": item.get("source")})
            continue
        if requires_concat and not cfg.get("supports_concat"):
            rejected.append({"provider": provider, "model": model, "reason": "model_does_not_support_concat", "source": item.get("source")})
            continue
        if not _model_supports(cfg, required_capability, requires_concat=requires_concat):
            rejected.append({"provider": provider, "model": model, "reason": "model_capability_missing", "source": item.get("source")})
            continue
        selected_defaults = _request_defaults(
            item.get("request_defaults"),
            int((route.get("tiers") or {}).get(tier_key, {}).get("clip_seconds") or cfg.get("clip_seconds") or 8),
        )
        selected_duration = int(selected_defaults.get("duration") or 0)
        max_duration = int(cfg.get("max_single_task_seconds") or cfg.get("clip_seconds") or 0)
        if selected_duration and max_duration and selected_duration > max_duration:
            rejected.append(
                {
                    "provider": provider,
                    "model": model,
                    "reason": "model_duration_exceeds_capability",
                    "requested_duration": selected_duration,
                    "max_single_task_seconds": max_duration,
                    "source": item.get("source"),
                }
            )
            continue
        contract = payload_contract_for_model(provider, model, cat)
        if not contract or not contract.get("payload_adapter"):
            rejected.append({"provider": provider, "model": model, "reason": CONTRACT_MISSING, "source": item.get("source")})
            continue
        if candidate_interface.get("contract_validation_status") == "blocked":
            rejected.append(
                {
                    "provider": provider,
                    "model": model,
                    "reason": candidate_interface.get("contract_block_reason") or CONTRACT_MISSING,
                    "source": item.get("source"),
                    "provider_interface": candidate_interface.get("provider_interface"),
                }
            )
            continue
        provider_model_map = {provider: model}
        provider_request_defaults = {provider: dict(selected_defaults)}
        for fallback in candidates:
            fallback_provider = str(fallback.get("provider") or "")
            fallback_model = str(fallback.get("model") or "")
            if not fallback_provider or fallback_provider in provider_model_map:
                continue
            fallback_cfg = provider_model_config(fallback_provider, fallback_model, cat)
            fallback_defaults = _request_defaults(
                fallback.get("request_defaults"),
                int((route.get("tiers") or {}).get(tier_key, {}).get("clip_seconds") or 8),
            )
            fallback_duration = int(fallback_defaults.get("duration") or 0)
            fallback_max_duration = int(
                fallback_cfg.get("max_single_task_seconds")
                or fallback_cfg.get("clip_seconds")
                or 0
            )
            fallback_interface = model_interface_contract(
                fallback_provider,
                fallback_model,
                env=data,
                catalog=cat,
            )
            if (
                not fallback_cfg
                or not _cost_tier_allowed(tier_key, fallback_cfg)
                or (requires_concat and not fallback_cfg.get("supports_concat"))
                or not _model_supports(
                    fallback_cfg,
                    required_capability,
                    requires_concat=requires_concat,
                )
                or (fallback_duration and fallback_max_duration and fallback_duration > fallback_max_duration)
                or fallback_interface.get("contract_validation_status") == "blocked"
                or not payload_contract_for_model(fallback_provider, fallback_model, cat).get("payload_adapter")
            ):
                continue
            provider_model_map[fallback_provider] = fallback_model
            provider_request_defaults[fallback_provider] = fallback_defaults
        capabilities = normalize_capability_values(cfg.get("capabilities") or [])
        return {
            "ok": True,
            "tier": tier_key,
            "selected_provider": provider,
            "selected_model": model,
            "selected_family": str(cfg.get("family") or ""),
            "selected_model_source": str(item.get("source") or ""),
            "selected_quality": str(cfg.get("quality") or (route.get("tiers") or {}).get(tier_key, {}).get("quality") or tier_key),
            "selected_cost_tier": str(cfg.get("cost_tier") or item.get("cost_tier") or tier_key),
            "selected_role": str(item.get("role") or ("primary" if not rejected else "fallback")),
            "selected_capabilities": capabilities,
            "selected_request_defaults": dict(selected_defaults),
            "selected_clip_seconds": int(
                selected_duration
                or (route.get("tiers") or {}).get(tier_key, {}).get("clip_seconds")
                or cfg.get("clip_seconds")
                or 8
            ),
            "selected_payload_adapter": str(cfg.get("payload_adapter") or ""),
            "payload_adapter": str(cfg.get("payload_adapter") or ""),
            "provider_catalog_model_found": True,
            "supports_concat": bool(cfg.get("supports_concat")),
            "contract_validation_status": "ok",
            **candidate_interface,
            "provider_model_map": provider_model_map,
            "provider_request_defaults": provider_request_defaults,
            "provider_chain": chain,
            "default_public_provider_chain": default_chain,
            "candidate_list_compact": candidate_list_compact,
            "rejected_models": rejected,
            "env_override_detected": env_override_detected,
            "env_override_provider_chain_detected": bool("VIDEO_PROVIDER_CHAIN" in data),
            "cost_routing_warning": KEY4U_COST_ROUTING_OVERRIDE_WARNING if key4u_primary_override else "",
            "public_low_tier_primary_provider_warning": PUBLIC_LOW_TIER_KEY4U_WARNING if key4u_primary_override else "",
            "required_capability_original": required_capability,
            "normalized_capability_candidates": capability_options(required_capability),
            "render_pipeline_mode": "historical_multi_clip_concat" if requires_concat else "single_task_legacy",
            "selected_model_config": cfg,
        }
    return {
        "ok": False,
        "tier": tier_key,
        "selected_provider": "",
        "selected_model": "",
        "selected_family": "",
        "selected_model_source": "",
        "selected_quality": "",
        "selected_capabilities": [],
        "selected_request_defaults": {},
        "selected_clip_seconds": 0,
        "selected_payload_adapter": "",
        "payload_adapter": "",
        "provider_catalog_model_found": False,
        "supports_concat": False,
        "contract_validation_status": CONTRACT_MISSING,
        "contract_block_reason": rejected[-1].get("reason") if rejected else CONTRACT_MISSING,
        "candidate_list_compact": candidate_list_compact,
        "provider_model_map": {},
        "provider_request_defaults": {},
        "provider_chain": chain,
        "default_public_provider_chain": default_chain,
        "rejected_models": rejected,
        "env_override_detected": env_override_detected,
        "env_override_provider_chain_detected": bool("VIDEO_PROVIDER_CHAIN" in data),
        "cost_routing_warning": KEY4U_COST_ROUTING_OVERRIDE_WARNING if key4u_primary_override else "",
        "public_low_tier_primary_provider_warning": PUBLIC_LOW_TIER_KEY4U_WARNING if key4u_primary_override else "",
        "required_capability_original": required_capability,
        "normalized_capability_candidates": capability_options(required_capability),
        "render_pipeline_mode": "historical_multi_clip_concat" if requires_concat else "single_task_legacy",
        "blocker": rejected[-1].get("reason") if rejected else CONTRACT_MISSING,
        "no_charge": True,
    }


def model_metadata_from_resolution(resolution: dict[str, Any]) -> dict[str, Any]:
    resolution = dict(resolution or {})
    fields = {
        "model_routing_ok": bool(resolution.get("ok")),
        "product_video_tier": resolution.get("tier") or "",
        "selected_provider": resolution.get("selected_provider") or "",
        "selected_model": resolution.get("selected_model") or "",
        "selected_family": resolution.get("selected_family") or "",
        "selected_model_source": resolution.get("selected_model_source") or "",
        "selected_quality": resolution.get("selected_quality") or "",
        "selected_cost_tier": resolution.get("selected_cost_tier") or "",
        "selected_role": resolution.get("selected_role") or "",
        "selected_capabilities": list(resolution.get("selected_capabilities") or []),
        "selected_request_defaults": dict(resolution.get("selected_request_defaults") or {}),
        "selected_clip_seconds": int(resolution.get("selected_clip_seconds") or 0),
        "selected_payload_adapter": resolution.get("selected_payload_adapter") or "",
        "provider_catalog_model_found": bool(resolution.get("provider_catalog_model_found")),
        "supports_concat": bool(resolution.get("supports_concat")),
        "contract_validation_status": resolution.get("contract_validation_status") or "",
        "contract_block_reason": resolution.get("contract_block_reason") or "",
        "provider_interface": resolution.get("provider_interface") or "",
        "provider_endpoint_source": resolution.get("provider_endpoint_source") or "",
        "provider_submit_url_override": resolution.get("provider_submit_url_override") or "",
        "provider_poll_url_override": resolution.get("provider_poll_url_override") or "",
        "model_requires_exclusive_interface": bool(resolution.get("model_requires_exclusive_interface")),
        "submit_skipped_due_to_contract": bool(resolution.get("submit_skipped_due_to_contract")),
        "provider_model_map": dict(resolution.get("provider_model_map") or {}),
        "provider_request_defaults": {
            str(key): dict(value)
            for key, value in (resolution.get("provider_request_defaults") or {}).items()
            if isinstance(value, dict)
        },
        "candidate_list_compact": list(resolution.get("candidate_list_compact") or []),
        "default_public_provider_chain": list(resolution.get("default_public_provider_chain") or []),
        "rejected_models": list(resolution.get("rejected_models") or []),
        "env_override_detected": bool(resolution.get("env_override_detected")),
        "env_override_provider_chain_detected": bool(resolution.get("env_override_provider_chain_detected")),
        "cost_routing_warning": resolution.get("cost_routing_warning") or "",
        "public_low_tier_primary_provider_warning": resolution.get("public_low_tier_primary_provider_warning") or "",
        "required_capability_original": resolution.get("required_capability_original") or "",
        "normalized_capability_candidates": list(resolution.get("normalized_capability_candidates") or []),
        "render_pipeline_mode": resolution.get("render_pipeline_mode") or "",
        "model_routing_blocker": resolution.get("blocker") or "",
    }
    return fields


def selected_model_for_provider(metadata: dict[str, Any] | None, provider: str) -> str:
    meta = dict(metadata or {})
    provider_name = str(provider or "").strip().lower()
    provider_model_map = meta.get("provider_model_map") if isinstance(meta.get("provider_model_map"), dict) else {}
    mapped = str(provider_model_map.get(provider_name) or "").strip()
    if mapped:
        return mapped
    selected_provider = str(meta.get("selected_provider") or "").strip().lower()
    selected_model = str(meta.get("selected_model") or "").strip()
    if selected_model and (not selected_provider or selected_provider == provider_name):
        return selected_model
    return ""


def enrich_metadata_with_model_contract(
    metadata: dict[str, Any] | None,
    provider: str,
    model: str,
    *,
    env: dict[str, str] | os._Environ[str] | None = None,
) -> dict[str, Any]:
    meta = dict(metadata or {})
    contract = payload_contract_for_model(provider, model)
    cfg = provider_model_config(provider, model)
    interface = model_interface_contract(provider, model, env=env)
    meta.update(
        {
            "selected_provider": str(provider or "").strip().lower(),
            "selected_model": str(model or "").strip(),
            "selected_family": str(cfg.get("family") or contract.get("family") or meta.get("selected_family") or ""),
            "selected_quality": str(cfg.get("quality") or meta.get("selected_quality") or ""),
            "selected_cost_tier": str(cfg.get("cost_tier") or meta.get("selected_cost_tier") or ""),
            "selected_capabilities": normalize_capability_values(cfg.get("capabilities") or meta.get("selected_capabilities") or []),
            "selected_clip_seconds": int(meta.get("selected_clip_seconds") or cfg.get("clip_seconds") or 0),
            "selected_request_defaults": dict(meta.get("selected_request_defaults") or {}),
            "provider_request_defaults": {
                str(key): dict(value)
                for key, value in (meta.get("provider_request_defaults") or {}).items()
                if isinstance(value, dict)
            },
            "selected_payload_adapter": str(cfg.get("payload_adapter") or contract.get("payload_adapter") or meta.get("selected_payload_adapter") or ""),
            "provider_catalog_model_found": bool(cfg),
            "supports_concat": bool(cfg.get("supports_concat") or meta.get("supports_concat")),
            "contract_validation_status": interface.get("contract_validation_status") or ("ok" if contract else CONTRACT_MISSING),
            "contract_block_reason": interface.get("contract_block_reason") or "",
            "provider_interface": interface.get("provider_interface") or "",
            "provider_endpoint_source": interface.get("provider_endpoint_source") or "",
            "provider_submit_url_override": interface.get("provider_submit_url_override") or "",
            "provider_poll_url_override": interface.get("provider_poll_url_override") or "",
            "model_requires_exclusive_interface": bool(interface.get("model_requires_exclusive_interface")),
            "submit_skipped_due_to_contract": bool(interface.get("submit_skipped_due_to_contract")),
            "model_used_in_payload": str(model or "").strip(),
            "payload_adapter": str(cfg.get("payload_adapter") or contract.get("payload_adapter") or ""),
        }
    )
    return meta


def enforce_payload_contract(
    provider: str,
    model: str,
    payload: dict[str, Any],
    *,
    env: dict[str, str] | os._Environ[str] | None = None,
) -> dict[str, Any]:
    data = dict(payload or {})
    contract = payload_contract_for_model(provider, model)
    metadata = enrich_metadata_with_model_contract(data.get("metadata") if isinstance(data.get("metadata"), dict) else {}, provider, model, env=env)
    if contract:
        allowed = set(str(item) for item in (contract.get("allowed_fields") or []) if str(item))
        model_capabilities = set(normalize_capability_values(contract.get("capabilities") or []))
        requested_options = capability_options(str(data.get("capability") or "text_to_video"))
        matched_capabilities = [item for item in requested_options if item in model_capabilities]
        fields_by_capability = contract.get("allowed_fields_by_capability")
        fields_by_capability = fields_by_capability if isinstance(fields_by_capability, dict) else {}
        allowed_media_fields: set[str] = set()
        for capability in matched_capabilities:
            allowed_media_fields.update(
                str(item)
                for item in (fields_by_capability.get(capability) or [])
                if str(item) in _MEDIA_INPUT_FIELDS
            )
        allowed.update(allowed_media_fields)
        if allowed:
            for key in list(data.keys()):
                if key not in allowed:
                    data.pop(key, None)
        if contract.get("scene_fields_allowed") is False:
            data.pop("scenes", None)
            metadata["unsupported_multiscene_fields_removed"] = True
        for field_name in _MEDIA_INPUT_FIELDS:
            if field_name not in allowed_media_fields:
                data.pop(field_name, None)
        metadata["provider_input_capability"] = matched_capabilities[0] if matched_capabilities else ""
        metadata["media_input_fields_allowed"] = sorted(allowed_media_fields)
    else:
        metadata["contract_validation_status"] = CONTRACT_MISSING
    data["metadata"] = metadata
    return data


def catalog_status_payload(env: dict[str, str] | os._Environ[str] | None = None) -> dict[str, Any]:
    data = env or os.environ
    catalog = load_video_provider_catalog()
    routing = load_product_video_model_routing()
    providers = catalog.get("providers") if isinstance(catalog.get("providers"), dict) else {}
    tiers = routing.get("tiers") if isinstance(routing.get("tiers"), dict) else {}
    env_override = False
    configured_models: dict[str, int] = {}
    for provider, provider_cfg in providers.items():
        models = provider_cfg.get("models") if isinstance(provider_cfg, dict) else {}
        configured_models[str(provider)] = len(models or {})
        for env_name in _provider_env_model_names(str(provider), "basic"):
            if str(data.get(env_name) or "").strip():
                env_override = True
    all_selected: list[str] = []
    tier_primary_models: dict[str, dict[str, str]] = {}
    cost_warnings: list[str] = []
    for tier in tiers:
        resolution = resolve_product_video_model(tier=tier, env=data, catalog=catalog, routing=routing)
        if resolution.get("selected_model"):
            all_selected.append(str(resolution.get("selected_model")))
        tier_primary_models[str(tier)] = {
            "provider": str(resolution.get("selected_provider") or ""),
            "model": str(resolution.get("selected_model") or ""),
            "family": str(resolution.get("selected_family") or ""),
            "cost_tier": str(resolution.get("selected_cost_tier") or ""),
            "role": str(resolution.get("selected_role") or ""),
        }
        for key in ("cost_routing_warning", "public_low_tier_primary_provider_warning"):
            warning = str(resolution.get(key) or "").strip()
            if warning and warning not in cost_warnings:
                cost_warnings.append(warning)
    degenerated = bool(all_selected and len(set(all_selected)) == 1 and len(all_selected) > 1)
    effective_chain = effective_provider_chain(data, routing)
    default_chain = split_provider_chain(routing.get("default_provider_chain") or DEFAULT_PROVIDER_CHAIN)
    return {
        "catalog_loaded": bool(providers),
        "routing_loaded": bool(tiers),
        "routing_enabled": bool(providers and tiers),
        "default_public_provider_chain": default_chain,
        "effective_provider_chain": effective_chain,
        "env_override_provider_chain_detected": bool(str(data.get("VIDEO_PROVIDER_CHAIN") or "").strip()),
        "low_tier_primary_model": tier_primary_models.get("low", {}),
        "basic_tier_primary_model": tier_primary_models.get("basic", {}),
        "common_tier_primary_model": tier_primary_models.get("common", {}),
        "tier_primary_models": tier_primary_models,
        "cost_routing_warnings": cost_warnings,
        "provider_count": len(providers),
        "model_count": sum(configured_models.values()),
        "providers": configured_models,
        "tier_count": len(tiers),
        "tiers": list(tiers.keys()),
        "env_override_detected": env_override,
        "degenerated_single_model": degenerated,
        "warning": "MODEL_ROUTING_DEGENERATED_SINGLE_MODEL" if degenerated else "",
    }
