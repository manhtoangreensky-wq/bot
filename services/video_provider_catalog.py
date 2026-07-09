"""Product Video provider catalog and tier/model routing.

This module is deliberately provider-call free. It resolves which provider
model should be used for a confirmed Product Video job and describes the
payload contract the worker must obey before it submits anything.
"""

from __future__ import annotations

import json
import os
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
            "supports_concat": bool(cfg.get("supports_concat")),
            "clip_seconds": int(cfg.get("clip_seconds") or 0),
            "payload_adapter": str(cfg.get("payload_adapter") or ""),
        }
    )
    return contract


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

    for provider in provider_chain:
        for env_name in _provider_env_model_names(provider, tier):
            value = str(env.get(env_name) or "").strip()
            if not value:
                continue
            env_override_detected = True
            if provider_model_config(provider, value, catalog):
                candidates.append(_candidate_from_entry(provider, value, f"env:{env_name}", catalog))
                break
            rejected.append({"provider": provider, "model": value, "reason": MODEL_UNKNOWN, "source": f"env:{env_name}"})

    for entry in preferred:
        provider = str(entry.get("provider") or "").strip().lower()
        model = str(entry.get("model") or "").strip()
        if provider not in provider_chain:
            continue
        candidates.append(_candidate_from_entry(provider, model, f"config:tier:{tier}", catalog))

    # Add one catalog fallback per chained provider so Key4U is not treated as a
    # one-model generic provider if tier config misses a provider.
    providers = catalog.get("providers") if isinstance(catalog.get("providers"), dict) else {}
    for provider in provider_chain:
        provider_cfg = providers.get(provider) if isinstance(providers, dict) else {}
        models = provider_cfg.get("models") if isinstance(provider_cfg, dict) else {}
        for model in models.keys() if isinstance(models, dict) else []:
            candidates.append(_candidate_from_entry(provider, str(model), "catalog:fallback", catalog))
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
    for item in candidates:
        provider = str(item.get("provider") or "")
        model = str(item.get("model") or "")
        cfg = dict(item.get("config") or {})
        if not cfg:
            rejected.append({"provider": provider, "model": model, "reason": MODEL_UNKNOWN, "source": item.get("source")})
            continue
        if requires_concat and not cfg.get("supports_concat"):
            rejected.append({"provider": provider, "model": model, "reason": "model_does_not_support_concat", "source": item.get("source")})
            continue
        if not _model_supports(cfg, required_capability, requires_concat=requires_concat):
            rejected.append({"provider": provider, "model": model, "reason": "model_capability_missing", "source": item.get("source")})
            continue
        contract = payload_contract_for_model(provider, model, cat)
        if not contract or not contract.get("payload_adapter"):
            rejected.append({"provider": provider, "model": model, "reason": CONTRACT_MISSING, "source": item.get("source")})
            continue
        provider_model_map = {provider: model}
        for fallback in candidates:
            fallback_provider = str(fallback.get("provider") or "")
            fallback_model = str(fallback.get("model") or "")
            if fallback_provider and fallback_provider not in provider_model_map and provider_model_config(fallback_provider, fallback_model, cat):
                provider_model_map[fallback_provider] = fallback_model
        capabilities = normalize_capability_values(cfg.get("capabilities") or [])
        return {
            "ok": True,
            "tier": tier_key,
            "selected_provider": provider,
            "selected_model": model,
            "selected_family": str(cfg.get("family") or ""),
            "selected_model_source": str(item.get("source") or ""),
            "selected_quality": str(cfg.get("quality") or (route.get("tiers") or {}).get(tier_key, {}).get("quality") or tier_key),
            "selected_capabilities": capabilities,
            "selected_clip_seconds": int(cfg.get("clip_seconds") or (route.get("tiers") or {}).get(tier_key, {}).get("clip_seconds") or 8),
            "selected_payload_adapter": str(cfg.get("payload_adapter") or ""),
            "payload_adapter": str(cfg.get("payload_adapter") or ""),
            "provider_catalog_model_found": True,
            "supports_concat": bool(cfg.get("supports_concat")),
            "contract_validation_status": "ok",
            "provider_model_map": provider_model_map,
            "provider_chain": chain,
            "rejected_models": rejected,
            "env_override_detected": env_override_detected,
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
        "selected_clip_seconds": 0,
        "selected_payload_adapter": "",
        "payload_adapter": "",
        "provider_catalog_model_found": False,
        "supports_concat": False,
        "contract_validation_status": CONTRACT_MISSING,
        "provider_model_map": {},
        "provider_chain": chain,
        "rejected_models": rejected,
        "env_override_detected": env_override_detected,
        "required_capability_original": required_capability,
        "normalized_capability_candidates": capability_options(required_capability),
        "render_pipeline_mode": "historical_multi_clip_concat" if requires_concat else "single_task_legacy",
        "blocker": CONTRACT_MISSING,
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
        "selected_capabilities": list(resolution.get("selected_capabilities") or []),
        "selected_clip_seconds": int(resolution.get("selected_clip_seconds") or 0),
        "selected_payload_adapter": resolution.get("selected_payload_adapter") or "",
        "provider_catalog_model_found": bool(resolution.get("provider_catalog_model_found")),
        "supports_concat": bool(resolution.get("supports_concat")),
        "contract_validation_status": resolution.get("contract_validation_status") or "",
        "provider_model_map": dict(resolution.get("provider_model_map") or {}),
        "rejected_models": list(resolution.get("rejected_models") or []),
        "env_override_detected": bool(resolution.get("env_override_detected")),
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


def enrich_metadata_with_model_contract(metadata: dict[str, Any] | None, provider: str, model: str) -> dict[str, Any]:
    meta = dict(metadata or {})
    contract = payload_contract_for_model(provider, model)
    cfg = provider_model_config(provider, model)
    meta.update(
        {
            "selected_provider": str(provider or "").strip().lower(),
            "selected_model": str(model or "").strip(),
            "selected_family": str(cfg.get("family") or contract.get("family") or meta.get("selected_family") or ""),
            "selected_quality": str(cfg.get("quality") or meta.get("selected_quality") or ""),
            "selected_capabilities": normalize_capability_values(cfg.get("capabilities") or meta.get("selected_capabilities") or []),
            "selected_clip_seconds": int(cfg.get("clip_seconds") or meta.get("selected_clip_seconds") or 0),
            "selected_payload_adapter": str(cfg.get("payload_adapter") or contract.get("payload_adapter") or meta.get("selected_payload_adapter") or ""),
            "provider_catalog_model_found": bool(cfg),
            "supports_concat": bool(cfg.get("supports_concat") or meta.get("supports_concat")),
            "contract_validation_status": "ok" if contract else CONTRACT_MISSING,
            "model_used_in_payload": str(model or "").strip(),
            "payload_adapter": str(cfg.get("payload_adapter") or contract.get("payload_adapter") or ""),
        }
    )
    return meta


def enforce_payload_contract(provider: str, model: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = dict(payload or {})
    contract = payload_contract_for_model(provider, model)
    metadata = enrich_metadata_with_model_contract(data.get("metadata") if isinstance(data.get("metadata"), dict) else {}, provider, model)
    if contract:
        allowed = set(str(item) for item in (contract.get("allowed_fields") or []) if str(item))
        if allowed:
            for key in list(data.keys()):
                if key not in allowed:
                    data.pop(key, None)
        if contract.get("scene_fields_allowed") is False:
            data.pop("scenes", None)
            data.pop("storyboard", None)
            data.pop("image_paths", None)
            data.pop("source_video_path", None)
            metadata["unsupported_multiscene_fields_removed"] = True
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
    for tier in tiers:
        resolution = resolve_product_video_model(tier=tier, env=data, catalog=catalog, routing=routing)
        if resolution.get("selected_model"):
            all_selected.append(str(resolution.get("selected_model")))
    degenerated = bool(all_selected and len(set(all_selected)) == 1 and len(all_selected) > 1)
    return {
        "catalog_loaded": bool(providers),
        "routing_loaded": bool(tiers),
        "routing_enabled": bool(providers and tiers),
        "provider_count": len(providers),
        "model_count": sum(configured_models.values()),
        "providers": configured_models,
        "tier_count": len(tiers),
        "tiers": list(tiers.keys()),
        "env_override_detected": env_override,
        "degenerated_single_model": degenerated,
        "warning": "MODEL_ROUTING_DEGENERATED_SINGLE_MODEL" if degenerated else "",
    }
