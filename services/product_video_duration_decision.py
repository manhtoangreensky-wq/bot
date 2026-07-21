from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "product_video_duration_decision.json"
REAL_PROVIDER_BLOCKED_REASON = "REAL_PROVIDER_BLOCKED_BY_COST_INCIDENT"
SUPPORTED_SMOKE_SECONDS = (4, 6, 8, 10, 12, 16, 20)

DEFAULT_DECISION: dict[str, Any] = {
    "provider": "shopaikey_video",
    "model": "veo3.1-fast",
    "public_mode": "scene_clip",
    "short_clip_seconds": 8,
    "supported_exact_durations": [],
    "arbitrary_seconds_supported": False,
    "max_single_video_seconds": 8,
    "multi_scene_enabled": False,
    "concat_enabled": False,
    "seconds_pricing_enabled": False,
    "last_smoke_status": "not_run_cost_locked",
    "last_smoke_at": "",
    "scene_pricing": {
        "promo_until": "2026-12-31",
        "scenes": {
            "1": {"list_price": 300, "promo_price": 200, "public_enabled": True},
            "2": {"list_price": 600, "promo_price": 400, "public_enabled": False},
            "3": {"list_price": 900, "promo_price": 600, "public_enabled": False},
        },
    },
    "seconds_pricing": {
        "minimum_seconds": 8,
        "list_price_per_second": 40,
        "promo_price_per_second": 25,
        "promo_until": "2026-12-31",
    },
    "smoke_policy": {
        "admin_only": True,
        "requires_explicit_toan_approval": True,
        "provider_submit_in_tests": False,
        "blocked_reason": REAL_PROVIDER_BLOCKED_REASON,
    },
}


def load_duration_decision(path: Path | str | None = None) -> dict[str, Any]:
    source = Path(path or CONFIG_PATH)
    data = deepcopy(DEFAULT_DECISION)
    if source.exists():
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        if isinstance(payload, dict):
            data.update(payload)
            for key in ("scene_pricing", "seconds_pricing", "smoke_policy"):
                merged = deepcopy(DEFAULT_DECISION.get(key, {}))
                value = payload.get(key)
                if isinstance(value, dict):
                    merged.update(value)
                    if key == "scene_pricing":
                        scenes = deepcopy(DEFAULT_DECISION["scene_pricing"]["scenes"])
                        scenes.update(value.get("scenes") if isinstance(value.get("scenes"), dict) else {})
                        merged["scenes"] = scenes
                data[key] = merged
    return data


def save_duration_decision(config: dict[str, Any], path: Path | str | None = None) -> None:
    target = Path(path or CONFIG_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def classify_duration_smokes(smokes: list[dict[str, Any]], previous: dict[str, Any] | None = None) -> dict[str, Any]:
    decision = deepcopy(previous or DEFAULT_DECISION)
    supported: list[int] = []
    ignored = False
    failed = False
    for item in smokes or []:
        requested = int(item.get("requested_seconds") or item.get("requested") or 0)
        actual = float(item.get("actual_seconds") or item.get("actual") or 0)
        status = str(item.get("status") or "").strip().lower()
        if status == "supported_exact" or (requested > 0 and actual > 0 and abs(actual - requested) <= 1.0):
            supported.append(requested)
        elif status == "ignored_to_default":
            ignored = True
        elif status in {"failed", "rejected", "provider_failed"}:
            failed = True

    supported = sorted(set(supported))
    decision["supported_exact_durations"] = supported
    decision["last_smoke_status"] = "failed" if failed and not supported else ("duration_ignored" if ignored and not any(x >= 10 for x in supported) else "classified")
    decision["last_smoke_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    if any(value >= 10 for value in supported):
        decision["public_mode"] = "seconds_long_video"
        decision["seconds_pricing_enabled"] = True
        decision["arbitrary_seconds_supported"] = False
        decision["max_single_video_seconds"] = max(supported)
    else:
        decision["public_mode"] = "scene_clip"
        decision["seconds_pricing_enabled"] = False
        decision["arbitrary_seconds_supported"] = False
        decision["max_single_video_seconds"] = max(supported or [int(decision.get("short_clip_seconds") or 8)])
        if supported:
            decision["short_clip_seconds"] = max(supported)
    return decision


def promo_active(promo_until: str = "", today: date | None = None) -> bool:
    current = today or date.today()
    try:
        end = date.fromisoformat(str(promo_until or ""))
    except ValueError:
        return False
    return current <= end


def scene_price(scene_count: int, config: dict[str, Any] | None = None, today: date | None = None) -> dict[str, Any]:
    cfg = config or load_duration_decision()
    scenes = (cfg.get("scene_pricing") or {}).get("scenes") or {}
    item = scenes.get(str(int(scene_count or 1))) or scenes.get("1") or {}
    promo_until = str((cfg.get("scene_pricing") or {}).get("promo_until") or "")
    active = promo_active(promo_until, today=today)
    list_price = int(item.get("list_price") or 0)
    promo_price = int(item.get("promo_price") or list_price)
    return {
        "scene_count": int(scene_count or 1),
        "list_price": list_price,
        "promo_price": promo_price,
        "charge_price": promo_price if active else list_price,
        "promo_until": promo_until,
        "promo_active": active,
        "public_enabled": bool(item.get("public_enabled")),
    }


def seconds_price(seconds: int, config: dict[str, Any] | None = None, today: date | None = None) -> dict[str, Any]:
    cfg = config or load_duration_decision()
    pricing = cfg.get("seconds_pricing") or {}
    sec = max(int(pricing.get("minimum_seconds") or 8), int(seconds or 0))
    promo_until = str(pricing.get("promo_until") or "")
    active = promo_active(promo_until, today=today)
    list_total = sec * int(pricing.get("list_price_per_second") or 40)
    promo_total = sec * int(pricing.get("promo_price_per_second") or 25)
    return {
        "seconds": sec,
        "list_price": list_total,
        "promo_price": promo_total,
        "charge_price": promo_total if active else list_total,
        "promo_until": promo_until,
        "promo_active": active,
        "allowed": bool(cfg.get("seconds_pricing_enabled")) and sec <= int(cfg.get("max_single_video_seconds") or 0),
    }


def public_contract_lines(config: dict[str, Any] | None = None) -> list[str]:
    cfg = config or load_duration_decision()
    mode = str(cfg.get("public_mode") or "scene_clip")
    if mode == "seconds_long_video":
        pricing = cfg.get("seconds_pricing") or {}
        return [
            "🎬 Video AI theo thời lượng",
            f"• Chọn số giây, tối đa {int(cfg.get('max_single_video_seconds') or 0)}s theo smoke đã chứng minh.",
            f"• Giá gốc {int(pricing.get('list_price_per_second') or 40)} Xu/giây.",
            f"• Giá ưu đãi đến hết năm {int(pricing.get('promo_price_per_second') or 25)} Xu/giây.",
            "• Không mở số giây vượt quá thời lượng provider đã chứng minh.",
        ]
    price = scene_price(1, cfg)
    return [
        "🎬 Video AI ngắn",
        "• 1 cảnh = 1 clip AI khoảng 8s.",
        f"• Giá gốc {price['list_price']} Xu.",
        f"• Ưu đãi đến hết năm {price['promo_price']} Xu.",
        "• Không hứa thời lượng chính xác khi provider chưa chứng minh video dài thật.",
    ]


def duration_capability_report(config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = config or load_duration_decision()
    return {
        "provider": str(cfg.get("provider") or ""),
        "model": str(cfg.get("model") or ""),
        "public_mode": str(cfg.get("public_mode") or ""),
        "short_clip_seconds": int(cfg.get("short_clip_seconds") or 0),
        "supported_exact_durations": list(cfg.get("supported_exact_durations") or []),
        "arbitrary_seconds_supported": bool(cfg.get("arbitrary_seconds_supported")),
        "max_single_video_seconds": int(cfg.get("max_single_video_seconds") or 0),
        "multi_scene_enabled": bool(cfg.get("multi_scene_enabled")),
        "concat_enabled": bool(cfg.get("concat_enabled")),
        "seconds_pricing_enabled": bool(cfg.get("seconds_pricing_enabled")),
        "last_smoke_status": str(cfg.get("last_smoke_status") or ""),
        "smoke_cost_locked": bool((cfg.get("smoke_policy") or {}).get("requires_explicit_toan_approval")),
    }


def duration_smoke_dry_run(requested_seconds: int, *, approved_by_toan: bool = False) -> dict[str, Any]:
    requested = int(requested_seconds or 0)
    if requested not in SUPPORTED_SMOKE_SECONDS:
        return {"ok": False, "requested_seconds": requested, "status": "unsupported_smoke_duration", "provider_call": False, "charge_xu": 0}
    if not approved_by_toan:
        return {
            "ok": False,
            "requested_seconds": requested,
            "status": "blocked",
            "blocker": REAL_PROVIDER_BLOCKED_REASON,
            "provider_call": False,
            "charge_xu": 0,
            "actual_seconds": None,
            "classification": "not_run_cost_locked",
        }
    return {
        "ok": False,
        "requested_seconds": requested,
        "status": "requires_manual_owner_confirmation_outside_tests",
        "blocker": REAL_PROVIDER_BLOCKED_REASON,
        "provider_call": False,
        "charge_xu": 0,
        "actual_seconds": None,
    }


def estimate_prompt_video_fit(prompt: str) -> dict[str, Any]:
    text = str(prompt or "").strip().lower()
    actions = len(re.findall(r"\b(rồi|sau đó|tiếp theo|then|and then|bước|step)\b", text))
    if any(word in text for word in ("nhiều ảnh", "chuỗi ảnh", "slideshow", "ảnh tĩnh", "hình ảnh")):
        return {"fit": "use_img2vid", "billing_authority": False, "reason": "static_image_sequence"}
    if any(word in text for word in ("nấu", "cooking", "tutorial", "hướng dẫn", "quy trình", "process")):
        return {"fit": "use_storyboard_or_multiscene", "billing_authority": False, "reason": "process_needs_steps"}
    if actions >= 2:
        return {"fit": "use_multiple_scenes", "billing_authority": False, "reason": "multiple_actions"}
    return {"fit": "one_short_clip", "billing_authority": False, "reason": "simple_action"}
