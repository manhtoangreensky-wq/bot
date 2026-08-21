from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
from types import SimpleNamespace

import pytest

try:
    import httpx  # noqa: F401
except ModuleNotFoundError:
    sys.modules["httpx"] = SimpleNamespace()

import local_worker
import remote_worker

from services import (
    multiscene_video_pipeline,
    product_video_addon_materialization,
    product_video_one_scene_engine,
    video_ai_real_pricing,
    video_profile_catalog,
    video_project_queue,
    video_real_render_connector,
    video_tail9,
    video_trace_state,
    video_uiflow3,
    video_uiflow3_routeengine,
)


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _safe_int(value, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _load_bot_functions(*names: str, extra_globals: dict | None = None) -> SimpleNamespace:
    wanted = set(names)
    blocks: list[tuple[int, str, str]] = []
    for name in wanted:
        marker = f"\ndef {name}("
        marker_at = BOT_SOURCE.find(marker)
        assert marker_at >= 0, f"missing bot function: {name}"
        start = marker_at + 1
        next_sync = BOT_SOURCE.find("\ndef ", start + len(marker))
        next_async = BOT_SOURCE.find("\nasync def ", start + len(marker))
        ends = [offset + 1 for offset in (next_sync, next_async) if offset >= 0]
        end = min(ends) if ends else len(BOT_SOURCE)
        blocks.append((start, name, BOT_SOURCE[start:end]))
    namespace = {
        "deepcopy": deepcopy,
        "re": re,
        "safe_int": _safe_int,
        "video_ai_real_pricing": video_ai_real_pricing,
        "video_profile_catalog": video_profile_catalog,
        "video_selfshot2": SimpleNamespace(PRODUCT_ID="self_shot_scene_change"),
        "video_selfshot3": SimpleNamespace(PRODUCT_ID="self_shot_cinematic_transform"),
        "video_tail9": video_tail9,
        "video_uiflow3": video_uiflow3,
        "VIDEO_TAIL9_STATE_KEY": "video_tail9",
        "VIDEO_UIFLOW3_SHARED_TAIL_PRODUCTS": frozenset(
            {
                "video_ai_real",
                "video_trend",
                "script_image_video",
                "storyboard_prompt",
                "multi_scene_film",
            }
        ),
        "VIDEO_UIFLOW3_DEFERRED_RUNTIME_PRODUCTS": frozenset(
            {
                "video_ai_real",
                "video_trend",
                "script_image_video",
                "storyboard_prompt",
                "multi_scene_film",
            }
        ),
        "normalize_translate_target": lambda value: (
            str(value or "").strip().lower()
            if str(value or "").strip().lower() in {"auto", "en", "vi", "fr"}
            else ""
        ),
        "translation_detect_language_code": lambda _text, _candidates=(): "",
    }
    namespace.update(dict(extra_globals or {}))
    for _offset, _name, block in sorted(blocks):
        exec(compile(block, str(ROOT / "bot.py"), "exec"), namespace)
    return SimpleNamespace(**{name: namespace[name] for name in wanted})


TAIL_BRIDGE = _load_bot_functions(
    "video_uiflow3_execution_adapter",
    "video_uiflow3_snapshot_revision",
    "video_uiflow3_snapshot_assets",
    "video_uiflow3_build_tail_state",
    "video_uiflow3_finalize_tail_rebuild",
)

TAIL_ADDONS = _load_bot_functions(
    "video_tail9_addon_postprocessing",
    "video_tail9_addon_value",
    "video_tail9_scene_script_info",
    "video_tail9_addon_script_info",
    "video_tail9_update_addon_audio",
    "video_tail9_set_addon_option",
    "video_tail9_set_addon_language",
    "video_tail9_set_dubbing_script_source",
)

VIDEO_TIER_ID_TO_NAME = {
    200: "low",
    300: "basic",
    400: "common",
    500: "advanced",
    600: "standard",
    700: "long",
    800: "high",
    1000: "future_1000",
    1200: "future_1200",
    1500: "future_1500",
}

BOT_PRICING = _load_bot_functions(
    "video_tier_pricing_payload",
    extra_globals={"VIDEO_TIER_ID_TO_NAME": VIDEO_TIER_ID_TO_NAME},
)


def _bot_video_tier_order() -> tuple[str, ...]:
    start = BOT_SOURCE.index("VIDEO_TIER_ID_TO_NAME = {")
    end = BOT_SOURCE.index("\ndef video_tier_pricing_payload", start)
    namespace = {"video_ai_real_pricing": video_ai_real_pricing}
    exec(compile(BOT_SOURCE[start:end], str(ROOT / "bot.py"), "exec"), namespace)
    return tuple(namespace["VIDEO_TIER_ORDER"])


def _approved_two_scene_snapshot(config_hash: str) -> dict:
    return {
        "draft_id": "product-video-real-output-draft",
        "source": {"assets": []},
        "references": [],
        "format": {"ratio": "9:16", "seconds_per_scene": 8},
        "content": {
            "source": "manual",
            "original_intent": "Cà phê thủ công",
            "approved_brief": {"prompt": "Hai cảnh giới thiệu cà phê thủ công."},
            "revision": 1,
            "profile_id": "product_review",
        },
        "scenes": [
            {
                "scene_id": "scene_01",
                "scene_index": 1,
                "duration_target": 8,
                "provider_prompt": "Cận cảnh hạt cà phê được rang thủ công.",
                "transition_out": "dissolve",
            },
            {
                "scene_id": "scene_02",
                "scene_index": 2,
                "duration_target": 8,
                "provider_prompt": "Barista rót cà phê vào ly thành phẩm.",
            },
        ],
        "audio": {
            "dubbing_mode": "none",
            "music_scope": "none",
            "music_source": "none",
            "sfx_mode": "none",
            "subtitle_mode": "none",
        },
        "branding": {},
        "config_hash": config_hash,
    }


def _uiflow3_state() -> dict:
    state = video_uiflow3.new_state(
        "video_ai_real",
        draft_id="product-video-real-output-draft",
    )
    return video_uiflow3.set_entry_mode(state, "prompt_video")


def test_same_draft_snapshot_revision_preserves_selected_addons_and_invalidates_downstream(
    monkeypatch,
) -> None:
    snapshots = [_approved_two_scene_snapshot("a" * 64)]
    monkeypatch.setattr(
        video_uiflow3,
        "approved_snapshot",
        lambda _state: deepcopy(snapshots[-1]),
    )
    state = _uiflow3_state()
    tail = TAIL_BRIDGE.video_uiflow3_build_tail_state(state)
    tail["audio_config"].update(
        {
            "dubbing": True,
            "music": True,
            "sfx": True,
            "subtitles": True,
        }
    )
    tail["audio_status"] = "configured"
    tail["addon_config"]["postprocessing"] = {
        "subtitles": {
            "enabled": True,
            "value": {
                "source": "translated",
                "translation": True,
                "target_language": "en",
            },
        },
        "dubbing": {
            "enabled": True,
            "value": {
                "dubbing_mode": "translated_ai",
                "voice_choice": "default_female",
                "script_source": "subtitles",
                "target_language": "en",
                "target_language_explicit": False,
            },
        },
        "music": {
            "enabled": True,
            "value": {
                "source": "library_only",
                "asset_id": "stock-music-coffee-01",
            },
        },
        "sfx": {
            "enabled": True,
            "value": {
                "source": "library_only",
                "asset_id": "stock-sfx-pour-01",
            },
        },
    }
    tail["logo_config"] = {
        "enabled": True,
        "asset_file_id": "telegram-logo-file",
        "file_size": 1234,
        "position": "top_left",
    }
    tail["logo_status"] = "configured"
    tail["watermark_config"] = {
        "enabled": True,
        "text": "TOAN AAS",
        "position": "bottom_right",
        "opacity_percent": 45,
    }
    tail["watermark_status"] = "configured"
    tail.update(
        {
            "review_status": "ready",
            "summary_status": "ready",
            "quality_tier_id": "400",
            "package_id": "product_video_400",
            "pricing_snapshot": {"total_xu": 180},
            "capability_snapshot": {"ready": True},
            "invoice_id": "invoice-before-revision",
            "final_confirmed": True,
            "job_id": 91,
            "submit_user_id": 77,
            "public_processing_code": "VID-BEFORE-REVISION",
            "submitted_at": "2026-08-20 10:00:00",
            "execution_state": "queued",
        }
    )
    state["video_tail9"] = tail

    snapshots.append(_approved_two_scene_snapshot("b" * 64))
    rebuilt = TAIL_BRIDGE.video_uiflow3_build_tail_state(state)

    assert rebuilt["plan_revision"] != tail["plan_revision"]
    assert rebuilt["audio_config"] == tail["audio_config"]
    assert rebuilt["addon_config"] == tail["addon_config"]
    assert rebuilt["logo_config"] == tail["logo_config"]
    assert rebuilt["logo_status"] == "configured"
    assert rebuilt["watermark_config"] == tail["watermark_config"]
    assert rebuilt["watermark_status"] == "configured"
    assert rebuilt["review_status"] == "not_ready"
    assert rebuilt["summary_status"] == "not_ready"
    assert rebuilt["quality_tier_id"] == ""
    assert rebuilt["package_id"] == ""
    assert rebuilt["pricing_snapshot"] == {}
    assert rebuilt["capability_snapshot"] == {}
    assert rebuilt["invoice_id"] == ""
    assert rebuilt["final_confirmed"] is False
    assert rebuilt["job_id"] == ""
    assert rebuilt["public_processing_code"] == ""


def test_dubbing_from_subtitles_inherits_language_until_user_overrides_it() -> None:
    tail = video_tail9.new_state(
        product_type="video_ai_real",
        execution_product_type="video_ai_prompt",
        session_id="language-inheritance",
        plan_revision=1,
        scene_count=2,
        ratio="9:16",
        estimated_duration=16,
    )
    tail = TAIL_ADDONS.video_tail9_set_addon_option(tail, "subtitles", "translated")
    tail = TAIL_ADDONS.video_tail9_set_addon_language(tail, "subtitles", "en")
    tail = TAIL_ADDONS.video_tail9_set_addon_option(tail, "dubbing", "default_female")
    tail = TAIL_ADDONS.video_tail9_set_dubbing_script_source(tail, "subtitles")

    inherited = TAIL_ADDONS.video_tail9_addon_value(tail, "dubbing")
    assert inherited["target_language"] == "en"
    assert inherited["target_language_explicit"] is False

    tail = TAIL_ADDONS.video_tail9_set_addon_language(tail, "subtitles", "vi")
    inherited_after_change = TAIL_ADDONS.video_tail9_addon_value(tail, "dubbing")
    assert inherited_after_change["target_language"] == "vi"

    tail = TAIL_ADDONS.video_tail9_set_addon_language(tail, "dubbing", "fr")
    tail = TAIL_ADDONS.video_tail9_set_addon_language(tail, "subtitles", "en")
    explicit = TAIL_ADDONS.video_tail9_addon_value(tail, "dubbing")
    assert explicit["target_language"] == "fr"
    assert explicit["target_language_explicit"] is True


def test_public_quality_catalog_uses_locked_names_icons_and_price_order() -> None:
    rows = video_ai_real_pricing.public_quality_catalog()

    assert [row["tier_id"] for row in rows] == [
        400,
        500,
        600,
        200,
        300,
        700,
        800,
        1000,
        1200,
        1500,
    ]
    assert [row["unit_xu"] for row in rows] == sorted(row["unit_xu"] for row in rows)
    by_tier = {row["tier_id"]: row for row in rows}
    assert (by_tier[400]["name"], by_tier[400]["icon"], by_tier[400]["unit_xu"]) == (
        "Nhanh gọn",
        "⚡",
        80,
    )
    assert (by_tier[200]["name"], by_tier[200]["icon"], by_tier[200]["unit_xu"]) == (
        "Cân bằng rõ nét",
        "✨",
        200,
    )


def test_bot_quality_payload_consumes_the_canonical_public_catalog() -> None:
    public_rows = video_ai_real_pricing.public_quality_catalog()
    expected_order = tuple(VIDEO_TIER_ID_TO_NAME[row["tier_id"]] for row in public_rows)
    payload = BOT_PRICING.video_tier_pricing_payload()

    assert _bot_video_tier_order() == expected_order
    assert tuple(key for key in payload if key != "premium") == expected_order
    assert payload["common"]["label"] == "Nhanh gọn"
    assert payload["low"]["label"] == "Cân bằng rõ nét"


def test_unit_economics_reports_first_route_and_conservative_fallback_costs() -> None:
    fast = video_ai_real_pricing.video_quality_unit_economics(400)
    balanced = video_ai_real_pricing.video_quality_unit_economics(200)

    assert fast["quality_name"] == "Nhanh gọn"
    assert fast["unit_xu"] == 80
    assert fast["first_route_cost_vnd_per_scene"] == 2016
    assert fast["conservative_fallback_cost_vnd_per_scene"] == 2450
    assert fast["conservative_margin_percent"] == 69.4
    assert fast["profitable_after_discount"] is True

    assert balanced["quality_name"] == "Cân bằng rõ nét"
    assert balanced["unit_xu"] == 200
    assert balanced["first_route_cost_vnd_per_scene"] == 1300
    assert balanced["conservative_fallback_cost_vnd_per_scene"] == 6457
    assert balanced["conservative_margin_percent"] == 67.7
    assert balanced["profitable_after_discount"] is True


def test_80_and_200_xu_packages_stay_profitable_at_maximum_scene_discount() -> None:
    for tier_id in (400, 200):
        report = video_ai_real_pricing.video_quality_unit_economics(
            tier_id,
            scene_count=20,
        )
        assert report["discount_percent"] == 20
        assert report["conservative_gross_profit_vnd"] > 0
        assert report["profitable_after_discount"] is True


def _product_video_project(conn: sqlite3.Connection, *, user_id: int) -> dict:
    shared = {
        "source": "product_video",
        "product_video": True,
        "render_mode": "real",
        "provider_call": True,
        "public_user": True,
        "public_user_confirmed": True,
        "invoice_confirmed": True,
        "submit_source": "public_user_final_confirm",
        "provider_submit_source": "public_user_final_confirm",
        "original_submit_source": "public_user_final_confirm",
        "product_type": "video_ai_prompt",
        "engine_adapter": "text_to_video",
        "orchestration_mode": "per_scene_8s",
        "provider_orchestration_mode": "per_scene_8s",
        "provider_chain": ["shopaikey_video"],
        "provider_order": "shopaikey_video",
        "scene_count": 2,
    }
    invoice = {
        **shared,
        "tier": "common",
        "routing_quality_tier": 400,
        "quality_tier": 400,
        "quality_xu": 80,
        "scene_duration_seconds": 8,
        "duration_seconds": 16,
        "subtotal_xu": 160,
        "discount_percent": 10,
        "discount_xu": 16,
        "total_xu": 144,
        "package_xu": 144,
        "user_visible_price_xu": 144,
        "persisted_quoted_price_xu": 144,
        "customer_charge_planned_xu": 144,
        "wallet_charge_amount_xu": 144,
        "list_price_xu": 160,
        "provider_budget_xu": 160,
    }
    project = video_project_queue.create_video_project(
        conn,
        user_id=user_id,
        profile_id="video_ai_prompt",
        topic="Cà phê thủ công",
        ratio="9:16",
        asset_pack=shared,
    )
    video_project_queue.update_video_project(
        conn,
        int(project["project_id"]),
        status="draft_invoice",
        invoice_json=invoice,
        scene_count=2,
        prompt_text="Hai cảnh giới thiệu cà phê thủ công.",
        quality_tier=400,
        total_xu_estimated=144,
    )
    return video_project_queue.get_video_project(conn, int(project["project_id"]))


def _signed_product_video_admission(project: dict, *, user_id: int) -> dict:
    checked_at = video_project_queue.now_text()
    candidate = "shopaikey_video"
    snapshot_id = "product-video-real-output-admission"
    snapshot = {
        "provider_eligibility_snapshot_id": snapshot_id,
        "admission_checked_at": checked_at,
        "admission_user_id": user_id,
        "admission_project_id": int(project["project_id"]),
        "configured_provider_keys": [candidate],
        "contract_valid_provider_chain": [candidate],
        "eligible_provider_keys": [candidate],
        "runtime_candidate_keys": [candidate],
        "final_eligible_provider_count": 1,
    }
    return video_project_queue.sign_product_video_final_admission_context({
        **snapshot,
        "ok": True,
        "provider_eligibility_snapshot": snapshot,
        "admission_snapshot_id": snapshot_id,
        "admission_candidate_keys": [candidate],
        "admission_candidate_count": 1,
        "admission_result": "PASS",
        "admission_user_id": user_id,
        "admission_project_id": int(project["project_id"]),
        "admission_quote_fingerprint": (
            video_project_queue.product_video_admission_quote_fingerprint(project, user_id)
        ),
        "admission_callback_handler_id": video_project_queue.PRODUCT_VIDEO_PUBLIC_CONFIRM_HANDLER_ID,
        "admission_callback_data": video_project_queue.PRODUCT_VIDEO_PUBLIC_CONFIRM_CALLBACK,
        "admission_provider_health_gate_pass": True,
        "admission_route_requires_provider": True,
        "route_requires_provider": True,
        "handler_id": video_project_queue.PRODUCT_VIDEO_PUBLIC_CONFIRM_HANDLER_ID,
        "admission_mode": "healthy",
        "submit_source": "public_user_final_confirm",
        "public_user_confirmed": True,
        "public_provider_freeze": False,
        "hidden_submit_freeze": False,
        "background_submit_freeze": False,
        "smoke_freeze": False,
        "public_live_provider_allowed": True,
        "freeze_blocker_code": "",
        "freeze_blocker_source": "",
    })


def test_authoritative_admission_promotes_same_preflight_job_and_one_outbox(
    tmp_path: Path,
) -> None:
    conn = sqlite3.connect(str(tmp_path / "same-job-promotion.db"))
    conn.row_factory = sqlite3.Row
    video_trace_state.ensure_video_trace_schema(conn)
    video_project_queue.ensure_video_project_queue_schema(conn)
    user_id = 880041
    chat_id = 880042
    project = _product_video_project(conn, user_id=user_id)
    started = video_trace_state.begin_video_confirm_execution(
        {"draft": {}},
        user_id=user_id,
        chat_id=chat_id,
        project_id=int(project["project_id"]),
        idempotency_key="product-video-real-output-confirm",
        payload={"scene_count": 2, "seconds_per_scene": 8, "unit_xu": 80},
        conn=conn,
    )
    ready = video_trace_state.record_video_confirm_precheck_result(
        started["session"],
        user_id=user_id,
        chat_id=chat_id,
        job_id=int(started["job_id"]),
        preflight_result="PASS",
        admission_result="PASS",
        conn=conn,
    )
    assert ready["job"]["status"] == "ready_to_submit"
    admission = _signed_product_video_admission(project, user_id=user_id)

    confirmed = video_project_queue.confirm_public_product_video_invoice(
        conn,
        project_id=int(project["project_id"]),
        user_id=user_id,
        provider_admission=admission,
    )

    assert confirmed["ok"] is True
    assert confirmed["job"]["id"] == started["job_id"]
    assert confirmed["job"]["status"] == "queued"
    assert confirmed["job_created"] is False
    assert confirmed["job_promoted"] is True
    assert conn.execute("SELECT COUNT(*) FROM video_jobs").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM video_scenes").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM video_dispatch_outbox").fetchone()[0] == 1
    outbox = video_project_queue.get_product_video_dispatch_outbox(
        conn,
        job_id=int(started["job_id"]),
    )
    assert outbox["dispatch_status"] == "pending"
    assert outbox["scene_indexes"] == [1, 2]
    payload = json.loads(str(confirmed["job"]["result_json"] or "{}"))
    assert payload["request_id"] == started["request_id"]
    assert payload["provider_task_id"] is None
    assert payload["submit_count"] == 0
    assert payload["charge_count"] == 0

    replay = video_project_queue.confirm_video_project_invoice(
        conn,
        project_id=int(project["project_id"]),
        user_id=user_id,
        provider_admission=admission,
        require_provider_admission=True,
    )
    assert replay["ok"] is True
    assert replay["job"]["id"] == started["job_id"]
    assert replay["duplicate_prevented"] is True
    assert conn.execute("SELECT COUNT(*) FROM video_jobs").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM video_dispatch_outbox").fetchone()[0] == 1
    conn.close()


def _selected_tail_addons() -> dict:
    tail = video_tail9.new_state(
        product_type="video_ai_real",
        execution_product_type="video_ai_prompt",
        session_id="product-video-addon-contract",
        plan_revision=1,
        scene_count=2,
        ratio="9:16",
        estimated_duration=16,
    )
    tail["scene_content"] = [
        {
            "scene_index": 1,
            "subtitle_line": "Hạt cà phê được rang thủ công.",
            "transition_out": "dissolve",
        },
        {
            "scene_index": 2,
            "subtitle_line": "Barista hoàn thiện ly cà phê.",
        },
    ]
    tail["audio_config"].update(
        {"dubbing": True, "music": True, "sfx": True, "subtitles": True}
    )
    tail["addon_config"] = {
        "automatic_text": [
            {
                "text": "Cà phê thủ công",
                "position": "top_center",
                "scene_scope": "1",
                "duration_seconds": 3,
            }
        ],
        "postprocessing": {
            "subtitles": {
                "enabled": True,
                "value": {
                    "source": "translated",
                    "script_text": "Hạt cà phê thủ công.\nLy cà phê hoàn thiện.",
                    "target_language": "vi",
                },
            },
            "dubbing": {
                "enabled": True,
                "value": {
                    "script_source": "subtitles",
                    "dialogue_text": "Hạt cà phê thủ công. Ly cà phê hoàn thiện.",
                    "voice_choice": "default_female",
                    "target_language": "vi",
                },
            },
            "music": {
                "enabled": True,
                "value": {
                    "source": "library_only",
                    "asset_id": "jamendo:coffee-01",
                    "source_url": "https://fixture.invalid/music.mp3",
                },
            },
            "sfx": {
                "enabled": True,
                "value": {
                    "source": "library_only",
                    "assets": [
                        {
                            "asset_id": "freesound:pour-01",
                            "source_url": "https://fixture.invalid/pour.wav",
                        }
                    ],
                },
            },
        },
    }
    tail["logo_config"] = {
        "enabled": True,
        "asset_file_id": "telegram-logo-file",
        "file_size": 1234,
        "position": "top_left",
    }
    tail["watermark_config"] = {
        "enabled": True,
        "text": "TOAN AAS",
        "position": "bottom_right",
        "opacity_percent": 45,
    }
    return video_tail9.normalize_state(tail)


def _ready_routeengine_snapshot() -> dict:
    state = video_uiflow3.new_state(
        "video_ai_real",
        draft_id="product-video-addon-handoff",
    )
    state = video_uiflow3.set_entry_mode(state, "prompt_video")
    state = video_uiflow3.set_format(
        state,
        ratio="9:16",
        target_duration_seconds=16,
    )
    state = video_uiflow3.set_content_candidate(
        state,
        source="manual",
        original_intent="Hai cảnh giới thiệu cà phê thủ công.",
        profile_id="product_showcase",
        approved_brief={
            "title": "Cà phê thủ công",
            "needs_characters": True,
            "needs_locations": True,
            "needs_dialogue": False,
            "needs_voice": False,
            "needs_music": False,
        },
    )
    state = video_uiflow3.lock_content(state)
    state = video_uiflow3.set_character_count(state, 1)
    character_id = str(state["bible"]["characters"][0]["character_id"])
    state = video_uiflow3.update_character(
        state,
        character_id,
        display_name="Mai Barista",
        role="người pha chế chính",
        gender="female",
        description="Barista mặc tạp dề xanh ngọc, thao tác tự nhiên.",
        wardrobe="tạp dề xanh ngọc",
    )
    state = video_uiflow3.set_location_count(state, 1)
    location_id = str(state["bible"]["locations"][0]["location_id"])
    state = video_uiflow3.update_location(
        state,
        location_id,
        name="Xưởng rang gạch đỏ",
        description="Không gian rang cà phê thủ công có tường gạch đỏ.",
        lighting="nắng sớm mềm",
    )
    state["creative_controls"] = {
        "visual_style": {
            "enabled": True,
            "value": "điện ảnh chân thật, màu nâu ấm",
        }
    }
    state["preservation_requirements"] = {
        "character_identity": {
            "enabled": True,
            "value": "giữ nguyên khuôn mặt, tạp dề xanh ngọc và tỷ lệ sản phẩm",
        }
    }
    state = video_uiflow3.confirm_scene_count(state, 2)
    state = video_uiflow3.suggest_scene_plan(state)
    state = video_uiflow3.auto_assign_scenes(state)
    for scene in list(state["scenes"]):
        state = video_uiflow3.update_scene_direction(
            state,
            str(scene["scene_id"]),
            framing="product close-up",
            movement="slow orbit",
            lighting="soft daylight",
            mood="premium",
            camera="50mm close-up",
        )
    state = video_uiflow3.mark_sections_complete(
        state,
        "production_bible",
        "references",
        "continuity",
        "scene_plan",
        "scene_assignment",
        "dialogue",
        "prompts",
        "branding",
        "summary",
    )
    return video_uiflow3.approved_snapshot(state)


def test_tail_addons_compile_into_complete_worker_material_contract() -> None:
    contract = video_uiflow3_routeengine.product_video_addon_worker_contract(
        _selected_tail_addons()
    )

    assert contract["requested_addons"] == [
        "subtitle",
        "dubbing",
        "music",
        "sfx",
        "logo",
        "watermark",
        "text",
        "transitions",
    ]
    assert contract["subtitle"]["script_text"].startswith("Hạt cà phê")
    assert contract["dubbing"]["voice_choice"] == "default_female"
    assert contract["music"]["asset_id"] == "jamendo:coffee-01"
    assert contract["sfx"]["assets"][0]["asset_id"] == "freesound:pour-01"
    assert contract["logo"]["telegram_file_id"] == "telegram-logo-file"
    assert contract["watermark"]["text"] == "TOAN AAS"
    assert contract["text_overlays"][0]["text"] == "Cà phê thủ công"
    assert contract["transition_plan"] == ["dissolve"]
    assert [item["name"] for item in contract["materialization_requirements"]] == contract[
        "requested_addons"
    ]
    assert contract["silent_drop_allowed"] is False


def test_routeengine_handoff_embeds_tail_materials_without_legacy_audio_blockers() -> None:
    handoff = video_uiflow3_routeengine.compile_routeengine_handoff(
        _ready_routeengine_snapshot(),
        owner_user_id=880051,
        owner_chat_id=880051,
        tail_state=_selected_tail_addons(),
    )

    assert handoff["ok"] is True
    assert handoff["commercial_ready"] is True
    assert handoff["bridge_blockers"] == []
    assert handoff["addon_plan"]["requested_addons"] == [
        "subtitle",
        "dubbing",
        "music",
        "sfx",
        "logo",
        "watermark",
        "text",
        "transitions",
    ]
    assert handoff["addon_plan"]["silent_drop_allowed"] is False
    assert handoff["branding_worker_contract"]["asset_pack"]["logo_material"][
        "logo_file_id"
    ] == "telegram-logo-file"
    assert handoff["branding_worker_contract"]["asset_pack"]["watermark_config"][
        "text"
    ] == "TOAN AAS"


def test_routeengine_provider_prompt_preserves_character_style_and_requirements() -> None:
    snapshot = _ready_routeengine_snapshot()
    handoff = video_uiflow3_routeengine.compile_routeengine_handoff(
        snapshot,
        owner_user_id=880052,
        owner_chat_id=880052,
        tail_state=_selected_tail_addons(),
    )

    assert snapshot["creative_controls"]["visual_style"]["value"] == (
        "điện ảnh chân thật, màu nâu ấm"
    )
    assert snapshot["preservation_requirements"]["character_identity"]["value"].startswith(
        "giữ nguyên khuôn mặt"
    )
    assert handoff["ok"] is True
    prompt_blob = "\n".join(str(item["provider_prompt"]) for item in handoff["scene_cards"])
    assert "Mai Barista" in prompt_blob
    assert "Xưởng rang gạch đỏ" in prompt_blob
    assert "điện ảnh chân thật, màu nâu ấm" in prompt_blob
    assert "giữ nguyên khuôn mặt, tạp dề xanh ngọc" in prompt_blob
    assert handoff["story_bible"]["uiflow3_creative_controls"] == snapshot[
        "creative_controls"
    ]
    assert handoff["story_bible"]["uiflow3_preservation_requirements"] == snapshot[
        "preservation_requirements"
    ]
    provider_plan = video_real_render_connector.real_video_scene_plan(
        {
            "source": "product_video",
            "product_video": True,
            "product_type": "video_ai_prompt",
            "scene_count": 2,
            "aspect_ratio": "9:16",
            "expected_duration_seconds": 16,
            "scene_cards": handoff["scene_cards"],
            "asset_pack": {
                "original_user_prompt": handoff["prompt_text"],
                "product_type": "video_ai_prompt",
                "orchestration_mode": "per_scene_8s",
            },
        }
    )
    submitted_prompt = str(provider_plan["scenes"][0]["video_prompt"])
    assert len(submitted_prompt) <= 1200
    assert "Mai Barista" in submitted_prompt
    assert "Xưởng rang gạch đỏ" in submitted_prompt
    assert "điện ảnh chân thật, màu nâu ấm" in submitted_prompt
    assert "giữ nguyên khuôn mặt, tạp dề xanh ngọc" in submitted_prompt


def test_remote_logo_download_accepts_strict_addon_plan_without_asset_pack(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class _Response:
        def __init__(self, payload: bytes):
            self.payload = payload
            self.offset = 0

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, size: int) -> bytes:
            chunk = self.payload[self.offset : self.offset + size]
            self.offset += len(chunk)
            return chunk

    observed: list[str] = []

    def fake_urlopen(request, timeout):
        observed.append(request.full_url)
        return _Response(b"strict-logo-image")

    monkeypatch.setattr(remote_worker, "endpoint", lambda path: f"https://worker.invalid{path}")
    monkeypatch.setattr(remote_worker.urllib.request, "urlopen", fake_urlopen)
    job = {
        "job_id": "strict-logo-job",
        "addon_plan": {
            "contract_version": "product-video-addons-v1",
            "requested_addons": ["logo"],
            "logo": {
                "enabled": True,
                "telegram_file_id": "telegram-strict-logo",
                "position": "center_left",
            },
        },
    }

    path = remote_worker.download_product_video_logo(job, str(tmp_path))

    assert Path(path).read_bytes() == b"strict-logo-image"
    assert job["asset_pack"]["logo_material"] == {
        "logo_enabled": True,
        "logo_file_id": "telegram-strict-logo",
        "logo_position": "center_left",
        "logo_path": path,
    }
    assert observed == [
        "https://worker.invalid/api/v1/worker/jobs/strict-logo-job/logo-material"
    ]
    endpoint_start = BOT_SOURCE.index("async def api_worker_product_video_logo_material")
    endpoint_end = BOT_SOURCE.index(
        '@fastapi_app.get("/api/v1/worker/jobs/{job_id}/source-video")',
        endpoint_start,
    )
    assert "addon_plan_json" in BOT_SOURCE[endpoint_start:endpoint_end]


def test_b14_session_recompiles_routeengine_handoff_after_tail_selection() -> None:
    start = BOT_SOURCE.index("def video_uiflow3_prepare_b14_session(")
    end = BOT_SOURCE.index("\n\ndef video_uiflow3_real_invoice_keyboard(", start)
    block = BOT_SOURCE[start:end]

    assert "video_uiflow3_compile_routeengine_handoff(" in block
    assert "tail_state=tail" in block
    assert block.index("tail = video_tail9.normalize_state") < block.index(
        "video_uiflow3_compile_routeengine_handoff("
    )


def test_uiflow3_tail_session_keeps_strict_addon_plan_for_job_persistence() -> None:
    tail = _selected_tail_addons()
    strict_plan = video_uiflow3_routeengine.product_video_addon_worker_contract(tail)
    stored: dict = {}
    prepared_session = {
        "draft": {
            "b14_profile_id": "product_showcase",
            "uiflow3_routeengine_handoff": {
                "handoff_sha256": "a" * 64,
                "addon_plan": deepcopy(strict_plan),
            },
        },
        "product_id": "video_ai_real",
    }

    def save_session(_user_id: int, session: dict) -> dict:
        stored.clear()
        stored.update(deepcopy(session))
        return deepcopy(stored)

    runtime = _load_bot_functions(
        "video_tail9_apply_to_session",
        extra_globals={
            "video_uiflow3_prepare_b14_session": lambda *_args, **_kwargs: (
                {"owner_chat_id": 99},
                deepcopy(prepared_session),
            ),
            "save_video_uiflow3_state": lambda _context, state: state,
            "video_uiflow3_handoff_from_session": lambda session: deepcopy(
                (session.get("draft") or {}).get("uiflow3_routeengine_handoff") or {}
            ),
            "video_tail9_addon_script_info": lambda *_args, **_kwargs: {
                "text": "Nội dung đã duyệt"
            },
            "video_tail9_language_label": lambda value: str(value or ""),
            "video_b14_default_addon_plan": lambda _profile: {},
            "video_tail9_addon_quote": lambda _tail: {"items": [], "total_xu": 0},
            "product_video_logo_material_config": lambda **kwargs: dict(kwargs),
            "save_video_session": save_session,
            "get_video_session": lambda _user_id: deepcopy(stored),
        },
    )

    result = runtime.video_tail9_apply_to_session(
        880061,
        SimpleNamespace(user_data={}),
        tail,
        "uiflow3",
        {"owner_chat_id": 99},
    )

    persisted_plan = result["draft"]["b14_addon_plan"]
    assert persisted_plan == strict_plan
    assert persisted_plan["requested_addons"] == [
        "subtitle",
        "dubbing",
        "music",
        "sfx",
        "logo",
        "watermark",
        "text",
        "transitions",
    ]


def test_one_scene_contract_supports_every_selected_product_video_addon() -> None:
    values = {
        name: {
            "requested": True,
            "approved": True,
            "supported": True,
            "required": True,
            "materialized": True,
            "handoff_status": "materialized",
            "artifact_path": f"fixture://{name}",
            "artifact_kind": "inline" if name in {"watermark", "text", "transitions"} else "file",
        }
        for name in (
            "subtitle",
            "dubbing",
            "music",
            "sfx",
            "logo",
            "watermark",
            "text",
            "transitions",
        )
    }

    addons = product_video_one_scene_engine.normalize_product_video_addons(values)
    validation = product_video_one_scene_engine.validate_product_video_addons(addons)

    assert set(product_video_one_scene_engine.SUPPORTED_ADDONS) >= set(values)
    assert validation["ok"] is True
    assert validation["blocker"] == ""


def test_requested_addon_without_material_blocks_before_provider_submit() -> None:
    addons = product_video_one_scene_engine.normalize_product_video_addons(
        {
            "music": {
                "requested": True,
                "approved": True,
                "supported": True,
                "required": True,
                "materialized": False,
                "handoff_status": "selected",
                "artifact_path": "",
                "artifact_kind": "audio",
            }
        }
    )

    validation = product_video_one_scene_engine.validate_product_video_addons(addons)

    assert validation["ok"] is False
    assert validation["blocker"] == "addon_material_missing:music"


def _worker_job_with_addons(addon_plan: dict) -> dict:
    return {
        "id": 880061,
        "job_id": 880061,
        "job_type": "video_render",
        "source": "product_video",
        "product_video": True,
        "render_mode": "real",
        "provider_call": True,
        "scene_count": 2,
        "addon_plan": deepcopy(addon_plan),
        "project": {
            "user_id": 880061,
            "scene_count": 2,
            "ratio": "9:16",
            "addon_plan_json": json.dumps(addon_plan, ensure_ascii=False),
        },
    }


def _render_audio_fixture(path: Path, frequency: int, duration: float = 2.0) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg, "ffmpeg is required for Product Video fixture tests"
    completed = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={frequency}:sample_rate=48000:duration={duration:.3f}",
            "-c:a",
            "pcm_s16le" if path.suffix.lower() == ".wav" else "aac",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    return path


def _render_logo_fixture(path: Path) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg, "ffmpeg is required for Product Video fixture tests"
    completed = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=yellow:s=48x48:d=0.1",
            "-frames:v",
            "1",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    return path


def _render_scene_fixture(path: Path, color: str, duration: float = 2.0) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg, "ffmpeg is required for Product Video fixture tests"
    completed = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s=180x320:r=12:d={duration:.3f}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    return path


def _probe_mp4_fixture(path: Path) -> dict:
    ffprobe = shutil.which("ffprobe")
    assert ffprobe, "ffprobe is required for Product Video fixture tests"
    completed = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,codec_name,width,height",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def _assert_mp4_decodes(path: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg, "ffmpeg is required for Product Video fixture tests"
    completed = subprocess.run(
        [ffmpeg, "-v", "error", "-i", str(path), "-f", "null", "-"],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert completed.returncode == 0, completed.stderr


def _write_subtitle_fixture(path: Path, scene_count: int) -> Path:
    blocks = []
    for index in range(scene_count):
        start = index * 2
        end = start + 2
        blocks.append(
            f"{index + 1}\n00:00:{start:02d},000 --> 00:00:{end:02d},000\nCảnh {index + 1}\n"
        )
    path.write_text("\n".join(blocks), encoding="utf-8")
    return path


def test_worker_blocks_missing_requested_material_before_provider_renderer(
    tmp_path: Path,
    monkeypatch,
) -> None:
    addon_plan = {
        "contract_version": "product-video-addons-v1",
        "requested_addons": ["music"],
        "music": {
            "enabled": True,
            "asset_id": "jamendo:missing-material",
            "source_url": "",
            "artifact_path": "",
        },
        "materialization_requirements": [
            {
                "name": "music",
                "required": True,
                "material_identity": "jamendo:missing-material",
                "material_kind": "stock_audio",
            }
        ],
        "silent_drop_allowed": False,
    }
    calls = {"renderer": 0, "pipeline": 0, "delivery": 0}
    updates: list[tuple[tuple, dict]] = []
    monkeypatch.setattr(local_worker, "TELEGRAM_BOT_TOKEN", "fixture-token")
    monkeypatch.setattr(
        local_worker,
        "prepare_product_video_public_seam_job",
        lambda job, **_kwargs: dict(job),
    )
    monkeypatch.setattr(
        local_worker,
        "create_multiscene_workspace",
        lambda *_args: str(tmp_path),
    )
    monkeypatch.setattr(
        local_worker,
        "video_project_real_scene_renderer",
        lambda *_args, **_kwargs: calls.__setitem__("renderer", calls["renderer"] + 1),
    )
    monkeypatch.setattr(
        local_worker,
        "process_multiscene_video_pipeline",
        lambda **_kwargs: calls.__setitem__("pipeline", calls["pipeline"] + 1)
        or {"ok": False, "error": "unexpected_pipeline"},
    )
    monkeypatch.setattr(
        local_worker,
        "telegram_send_video_receipt",
        lambda *_args, **_kwargs: calls.__setitem__("delivery", calls["delivery"] + 1),
    )
    monkeypatch.setattr(
        local_worker,
        "update_video_render_job",
        lambda *args, **kwargs: updates.append((args, kwargs)),
    )

    local_worker.run_video_render_job(_worker_job_with_addons(addon_plan))

    assert calls == {"renderer": 0, "pipeline": 0, "delivery": 0}
    assert updates
    assert "addon_material_missing:music" in str(updates[-1])


def test_remote_connector_blocks_missing_addon_before_provider_readiness(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = {"readiness": 0}

    def forbidden_readiness(*_args, **_kwargs):
        calls["readiness"] += 1
        raise AssertionError("provider readiness must not run before strict Add-on materialization")

    monkeypatch.setattr(
        video_real_render_connector,
        "real_video_provider_readiness",
        forbidden_readiness,
    )
    job = _worker_job_with_addons(
        {
            "contract_version": "product-video-addons-v1",
            "requested_addons": ["music"],
            "music": {
                "enabled": True,
                "asset_id": "jamendo:missing-remote-material",
                "source_url": "",
                "artifact_path": "",
            },
            "silent_drop_allowed": False,
        }
    )

    with pytest.raises(
        video_real_render_connector.RealVideoRenderError,
        match="addon_material_missing:music",
    ):
        video_real_render_connector.render_real_video_job(job, str(tmp_path))

    assert calls["readiness"] == 0


def test_remote_connector_forwards_strict_materials_to_local_compositor(
    tmp_path: Path,
    monkeypatch,
) -> None:
    captured: dict = {}
    monkeypatch.setattr(
        video_real_render_connector,
        "process_multiscene_video_pipeline",
        lambda **kwargs: captured.update(kwargs) or {"ok": True},
    )
    materials = {
        "strict": True,
        "requested_addons": ["subtitle", "dubbing", "music", "sfx", "logo", "watermark", "text", "transitions"],
        "subtitle_path": str(tmp_path / "captions.srt"),
        "voice_audio_path": str(tmp_path / "voice.m4a"),
        "voice_volume_percent": 90,
        "bgm_audio_path": str(tmp_path / "music.m4a"),
        "music_volume_percent": 20,
        "sfx_audio_paths": [str(tmp_path / "sfx.wav")],
        "sfx_assets": [{"start_seconds": 0.5}],
        "sfx_volume_percent": 35,
        "logo_path": str(tmp_path / "logo.png"),
        "logo_position": "top_left",
        "watermark_text": "TOAN AAS",
        "watermark_position": "bottom_right",
        "watermark_opacity_percent": 45,
        "text_overlays": [{"text": "Cà phê thủ công", "scene_scope": "1"}],
        "transition_plan": ["dissolve"],
    }

    video_real_render_connector._run_multiscene_render(
        {
            "job_id": "strict-forward",
            "user_id": "880061",
            "source": "product_video",
            "product_video": True,
            "scene_count": 2,
            "project": {"addon_plan_json": "{}"},
        },
        str(tmp_path / "workspace"),
        render_video_func=lambda *_args, **_kwargs: {},
        addon_materials=materials,
    )

    assert captured["requested_addons"] == materials["requested_addons"]
    assert captured["voice_audio_path"] == materials["voice_audio_path"]
    assert captured["sfx_audio_paths"] == materials["sfx_audio_paths"]
    assert captured["watermark_text"] == "TOAN AAS"
    assert captured["text_overlays"] == materials["text_overlays"]


def test_worker_passes_every_materialized_addon_to_product_compositor(
    tmp_path: Path,
    monkeypatch,
) -> None:
    voice = _render_audio_fixture(tmp_path / "voice.m4a", 440)
    music = _render_audio_fixture(tmp_path / "music.m4a", 660)
    sfx = _render_audio_fixture(tmp_path / "pour.wav", 880)
    logo = _render_logo_fixture(tmp_path / "logo.png")
    addon_plan = {
        "contract_version": "product-video-addons-v1",
        "requested_addons": [
            "subtitle",
            "dubbing",
            "music",
            "sfx",
            "logo",
            "watermark",
            "text",
            "transitions",
        ],
        "subtitle": {
            "enabled": True,
            "script_text": "Cảnh một.\nCảnh hai.",
        },
        "dubbing": {
            "enabled": True,
            "script_text": "Cảnh một. Cảnh hai.",
            "voice_choice": "default_female",
            "artifact_path": str(voice),
            "volume_percent": 90,
        },
        "music": {
            "enabled": True,
            "asset_id": "jamendo:coffee-fixture",
            "artifact_path": str(music),
            "volume_percent": 20,
        },
        "sfx": {
            "enabled": True,
            "assets": [
                {
                    "asset_id": "freesound:pour-fixture",
                    "artifact_path": str(sfx),
                    "start_seconds": 0.5,
                }
            ],
            "volume_percent": 35,
        },
        "logo": {
            "enabled": True,
            "artifact_path": str(logo),
            "position": "top_left",
        },
        "watermark": {
            "enabled": True,
            "text": "TOAN AAS",
            "position": "bottom_right",
            "opacity_percent": 45,
        },
        "text_overlays": [
            {
                "text": "Cà phê thủ công",
                "position": "top_center",
                "scene_scope": "1",
                "duration_seconds": 1,
            }
        ],
        "transition_plan": ["dissolve"],
        "silent_drop_allowed": False,
    }
    captured: dict = {}
    updates: list[tuple[tuple, dict]] = []
    final_path = tmp_path / "final.mp4"
    final_path.write_bytes(b"fixture-final")
    monkeypatch.setattr(local_worker, "TELEGRAM_BOT_TOKEN", "fixture-token")
    monkeypatch.setattr(
        local_worker,
        "prepare_product_video_public_seam_job",
        lambda job, **_kwargs: dict(job),
    )
    monkeypatch.setattr(
        local_worker,
        "create_multiscene_workspace",
        lambda *_args: str(tmp_path),
    )
    monkeypatch.setattr(local_worker, "video_project_real_scene_renderer", lambda *_args: object())
    monkeypatch.setattr(local_worker, "product_video_logo_material", lambda *_args: {})
    monkeypatch.setattr(local_worker, "real_video_llm_func_from_job", lambda *_args: None)

    def capture_pipeline(**kwargs):
        captured.update(kwargs)
        return {"ok": True, "final_video_path": str(final_path)}

    monkeypatch.setattr(local_worker, "process_multiscene_video_pipeline", capture_pipeline)
    monkeypatch.setattr(
        local_worker,
        "telegram_send_video_receipt",
        lambda *_args, **_kwargs: {
            "sent": True,
            "message_id": "fixture-message",
            "file_id": "fixture-file",
        },
    )
    monkeypatch.setattr(
        local_worker,
        "update_video_render_job",
        lambda *args, **kwargs: updates.append((args, kwargs)),
    )

    local_worker.run_video_render_job(_worker_job_with_addons(addon_plan))

    assert captured["voice_audio_path"] == str(voice)
    assert captured["bgm_audio_path"] == str(music)
    assert captured["sfx_audio_paths"] == [str(sfx)]
    subtitle_render = Path(captured["subtitle_path"])
    subtitle_ass = subtitle_render.read_text(encoding="utf-8")
    assert subtitle_render.suffix == ".ass"
    assert subtitle_ass.count("Dialogue: 0,") == 2
    assert "canonical_subdub_profile: vi_telegram_general_v1" in subtitle_ass
    assert captured["logo_path"] == str(logo)
    assert captured["logo_position"] == "top_left"
    assert captured["watermark_text"] == "TOAN AAS"
    assert captured["watermark_position"] == "bottom_right"
    assert captured["text_overlays"][0]["text"] == "Cà phê thủ công"
    assert captured["transition_plan"] == ["dissolve"]
    assert captured["voice_volume_percent"] == 90
    assert captured["music_volume_percent"] == 20
    assert captured["sfx_volume_percent"] == 35
    assert captured["requested_addons"] == addon_plan["requested_addons"]
    assert updates[-1][0][1] == "completed"


def _frame_mean_rgb(path: Path, at_seconds: float) -> tuple[float, float, float]:
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg, "ffmpeg is required for Product Video fixture tests"
    completed = subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-ss",
            f"{at_seconds:.3f}",
            "-i",
            str(path),
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-",
        ],
        capture_output=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr.decode(errors="ignore")
    payload = completed.stdout
    assert payload and len(payload) % 3 == 0
    pixels = len(payload) // 3
    return tuple(sum(payload[offset::3]) / pixels for offset in range(3))


def _finalize_all_addon_fixture(tmp_path: Path, scene_count: int) -> dict:
    colors = ["red", "blue"]
    scenes = [
        multiscene_video_pipeline.SceneSpec(
            scene_id=index,
            title=f"Cảnh {index}",
            visual_prompt=f"Sản phẩm cảnh {index}",
            video_prompt=f"Sản phẩm cảnh {index}",
            narration_text=f"Lời đọc cảnh {index}",
            target_duration_sec=2.0,
            aspect_ratio="9:16",
            transition="cut",
        )
        for index in range(1, scene_count + 1)
    ]
    clips = {
        index: str(_render_scene_fixture(tmp_path / f"scene-{index}.mp4", colors[index - 1]))
        for index in range(1, scene_count + 1)
    }
    total_duration = float(scene_count * 2)
    voice = _render_audio_fixture(tmp_path / "fixture-voice.m4a", 440, total_duration)
    music = _render_audio_fixture(tmp_path / "fixture-music.m4a", 660, total_duration)
    sfx = _render_audio_fixture(tmp_path / "fixture-sfx.wav", 880, 0.75)
    logo = _render_logo_fixture(tmp_path / "fixture-logo.png")
    subtitle_materials = product_video_addon_materialization.materialize_product_video_addons(
        {
            "output_width": 180,
            "output_height": 320,
            "addon_plan": {
                "contract_version": "product-video-addons-v1",
                "requested_addons": ["subtitle"],
                "subtitle": {
                    "enabled": True,
                    "target_language": "vi",
                    "script_text": "\n".join(
                        f"Lời phụ đề SubDub cho cảnh {index}."
                        for index in range(1, scene_count + 1)
                    ),
                },
            },
        },
        workspace=str(tmp_path),
        scene_count=scene_count,
        scene_duration=2.0,
    )
    assert subtitle_materials["ok"] is True
    subtitle = Path(subtitle_materials["subtitle_path"])
    transitions = ["dissolve"] if scene_count == 2 else []
    requested = [
        "subtitle",
        "dubbing",
        "music",
        "sfx",
        "logo",
        "watermark",
        "text",
    ] + (["transitions"] if transitions else [])
    return multiscene_video_pipeline.finalize_multiscene_scene_clips(
        user_id="880061",
        job_id=f"fixture-{scene_count}-scene",
        workspace_dir=str(tmp_path / "workspace"),
        scenes=scenes,
        scene_clip_paths=clips,
        voice_audio_path=str(voice),
        bgm_audio_path=str(music),
        sfx_audio_paths=[str(sfx)],
        sfx_assets=[{"start_seconds": 0.5, "asset_id": "freesound:fixture"}],
        subtitle_path=str(subtitle),
        logo_path=str(logo),
        enable_voice=True,
        enable_subtitle=True,
        enable_logo=True,
        logo_position="top_left",
        watermark_text="TOAN AAS",
        watermark_position="bottom_right",
        watermark_opacity_percent=45,
        text_overlays=[
            {
                "text": "Cà phê thủ công",
                "position": "top_center",
                "scene_scope": "1",
                "duration_seconds": 1,
            },
            {
                "text": "Hoàn thiện",
                "position": "center",
                "scene_scope": str(scene_count),
                "duration_seconds": 1,
            },
        ],
        transition_plan=transitions,
        requested_addons=requested,
        voice_volume_percent=90,
        music_volume_percent=20,
        sfx_volume_percent=35,
        output_width=180,
        output_height=320,
        output_fps=12,
        transition_duration_sec=0.25,
        final_duration_tolerance_sec=0.8,
    )


def test_one_scene_local_fixture_produces_decodable_mp4_with_all_addons(
    tmp_path: Path,
) -> None:
    result = _finalize_all_addon_fixture(tmp_path, 1)

    assert result["ok"] is True
    final_path = Path(result["final_video_path"])
    probe = _probe_mp4_fixture(final_path)
    assert {stream["codec_type"] for stream in probe["streams"]} >= {"video", "audio"}
    assert result["scene_order"] == [1]
    assert result["addon_application"]["missing"] == []
    assert set(result["addon_application"]["applied"]) == set(result["addon_application"]["requested"])
    _assert_mp4_decodes(final_path)


def test_two_scene_local_fixture_keeps_order_transition_and_all_addons(
    tmp_path: Path,
) -> None:
    result = _finalize_all_addon_fixture(tmp_path, 2)

    assert result["ok"] is True
    final_path = Path(result["final_video_path"])
    probe = _probe_mp4_fixture(final_path)
    assert {stream["codec_type"] for stream in probe["streams"]} >= {"video", "audio"}
    assert result["scene_order"] == [1, 2]
    assert result["transition_plan"] == ["dissolve"]
    assert result["addon_application"]["missing"] == []
    assert set(result["addon_application"]["applied"]) == set(result["addon_application"]["requested"])
    early = _frame_mean_rgb(final_path, 0.5)
    late = _frame_mean_rgb(final_path, 3.0)
    assert early[0] > early[2]
    assert late[2] > late[0]
    _assert_mp4_decodes(final_path)
