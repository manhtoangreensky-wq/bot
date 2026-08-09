from __future__ import annotations

import importlib
import hashlib
import json
import sqlite3
from copy import deepcopy
from datetime import datetime
from pathlib import Path

import pytest

from services import video_engine_contract
from services import video_project_queue as queue
from services import video_provider_router
from services import video_uiflow3


USER_ID = 3901


def _bridge():
    return importlib.import_module("services.video_uiflow3_routeengine")


def _ready_state(
    *,
    scene_count: int = 1,
    ratio: str = "9:16",
    target_duration_seconds: int | None = None,
) -> dict:
    state = video_uiflow3.new_state("video_ai_real", draft_id=f"bridge-{scene_count}-{ratio}")
    state = video_uiflow3.set_entry_mode(state, "prompt_video")
    state = video_uiflow3.set_format(
        state,
        ratio=ratio,
        target_duration_seconds=(
            scene_count * 8
            if target_duration_seconds is None
            else target_duration_seconds
        ),
    )
    state = video_uiflow3.set_content_candidate(
        state,
        source="manual",
        original_intent="Chai nuoc hoa xoay nhe, anh sang that va nhan hieu ro rang.",
        profile_id="product_showcase",
        approved_brief={
            "title": "Nuoc hoa anh sang that",
            "main_message": "Giu dung chai, mau sac va nhan hieu.",
            "needs_characters": False,
            "needs_locations": False,
            "needs_dialogue": False,
            "needs_voice": False,
            "needs_music": False,
        },
    )
    state = video_uiflow3.lock_content(state)
    state = video_uiflow3.set_character_count(state, 0)
    state = video_uiflow3.set_location_count(state, 0)
    state = video_uiflow3.confirm_scene_count(state, scene_count)
    state = video_uiflow3.suggest_scene_plan(state)
    state = video_uiflow3.auto_assign_scenes(state)
    for scene in list(state["scenes"]):
        state = video_uiflow3.update_scene_direction(
            state,
            str(scene["scene_id"]),
            framing="product close-up",
            movement="slow clockwise orbit",
            lighting="soft daylight",
            mood="premium and truthful",
            camera="50mm close-up, stable motion",
        )
    state["branding"] = {
        "watermark": {
            "enabled": True,
            "text": "TOAN AAS",
            "position": "top_right",
        }
    }
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
    state["navigation"]["current_step"] = "summary"
    assert video_uiflow3.readiness_errors(state) == []
    return video_uiflow3.normalize_state(state)


def _rehash_snapshot(snapshot: dict) -> dict:
    clean = deepcopy(snapshot)
    clean.pop("config_hash", None)
    encoded = json.dumps(
        clean,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    clean["config_hash"] = hashlib.sha256(encoded).hexdigest()
    return clean


def _rich_planning_snapshot() -> dict:
    state = video_uiflow3.new_state("video_ai_real", draft_id="bridge-rich-plan")
    state = video_uiflow3.set_entry_mode(state, "prompt_video")
    state = video_uiflow3.set_format(state, ratio="9:16", target_duration_seconds=16)
    state = video_uiflow3.set_content_candidate(
        state,
        source="manual",
        original_intent="Lan va Minh cung gioi thieu san pham qua hai canh lien mach.",
        profile_id="product_showcase",
        approved_brief={
            "title": "Hai nhan vat gioi thieu san pham",
            "needs_characters": True,
            "needs_locations": True,
            "needs_dialogue": True,
            "needs_voice": True,
            "needs_music": False,
        },
    )
    state = video_uiflow3.lock_content(state)
    state = video_uiflow3.set_character_count(state, 2)
    state = video_uiflow3.update_character(
        state,
        "char_01",
        display_name="Lan",
        gender="female",
        description="Nguoi dan chu mac ao xanh.",
        voice_id="plan-vi-female-02",
    )
    state = video_uiflow3.update_character(
        state,
        "char_02",
        display_name="Minh",
        gender="male",
        description="Nguoi tu van mac ao trang.",
        voice_id="plan-vi-male-02",
    )
    state = video_uiflow3.set_location_count(state, 2)
    state = video_uiflow3.update_location(
        state,
        "loc_01",
        name="Ban trung bay",
        description="Ban trung bay sach, anh sang tu nhien.",
    )
    state = video_uiflow3.update_location(
        state,
        "loc_02",
        name="Ke san pham",
        description="Ke san pham cung bang mau voi canh truoc.",
    )
    state = video_uiflow3.confirm_scene_count(state, 2)
    state = video_uiflow3.suggest_scene_plan(state)
    state = video_uiflow3.auto_assign_scenes(state)
    state = video_uiflow3.set_dialogue(
        state,
        "scene_01",
        speaker_id="char_01",
        text="Day la san pham chung toi muon gioi thieu.",
    )
    state = video_uiflow3.set_dialogue(
        state,
        "scene_02",
        speaker_id="char_02",
        text="Canh sau tiep noi dung nhan dien va chot loi ich.",
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
    snapshot = video_uiflow3.approved_snapshot(state)
    assert snapshot["render_blockers"]
    return snapshot


def _quote(scene_count: int) -> dict:
    total = 300 * scene_count
    return {
        "tier": "basic",
        "package_xu": total,
        "quality_tier": 300,
        "scene_count": scene_count,
        "total_xu": total,
        "user_visible_price_xu": total,
        "persisted_quoted_price_xu": total,
        "customer_charge_planned_xu": total,
        "wallet_charge_amount_xu": total,
        "list_price_xu": total,
        "provider_budget_xu": total,
    }


def _admission(project: dict, *, snapshot_id: str = "uiflow3-bridge-admission") -> dict:
    checked_at = datetime.now()
    candidates = ["shopaikey_video"]
    quote_fingerprint = queue.product_video_admission_quote_fingerprint(
        project,
        int(project["user_id"]),
    )
    route = video_provider_router.product_video_route_contract(
        "video_ai_prompt",
        "text_to_video",
        "single_task_legacy",
    )
    snapshot = {
        "provider_eligibility_snapshot_id": snapshot_id,
        "admission_snapshot_id": snapshot_id,
        "admission_checked_at": queue.now_text(checked_at),
        "admission_user_id": int(project["user_id"]),
        "admission_project_id": int(project["project_id"]),
        "admission_quote_fingerprint": quote_fingerprint,
        "admission_callback_handler_id": queue.PRODUCT_VIDEO_PUBLIC_CONFIRM_HANDLER_ID,
        "admission_callback_data": queue.PRODUCT_VIDEO_PUBLIC_CONFIRM_CALLBACK,
        "eligible_provider_keys": candidates,
        "runtime_candidate_keys": candidates,
        "final_eligible_provider_count": 1,
    }
    admission = {
        "ok": True,
        "provider_eligibility_snapshot": snapshot,
        "provider_eligibility_snapshot_id": snapshot_id,
        "admission_snapshot_id": snapshot_id,
        "admission_checked_at": queue.now_text(checked_at),
        "admission_ttl_seconds": 60,
        "admission_candidate_keys": candidates,
        "admission_candidate_count": 1,
        "admission_result": "PASS",
        "admission_block_reason": "",
        "admission_user_id": int(project["user_id"]),
        "admission_project_id": int(project["project_id"]),
        "admission_quote_fingerprint": quote_fingerprint,
        "admission_callback_handler_id": queue.PRODUCT_VIDEO_PUBLIC_CONFIRM_HANDLER_ID,
        "admission_callback_data": queue.PRODUCT_VIDEO_PUBLIC_CONFIRM_CALLBACK,
        "admission_worker_runtime_sha": "uiflow3-runtime",
        "admission_worker_sha": "uiflow3-runtime",
        "admission_worker_version_compatible": True,
        "admission_route_requires_provider": bool(route["route_requires_provider"]),
        "admission_provider_health_gate_pass": True,
        "worker_generation_id": "uiflow3-worker-generation",
        "worker_git_sha": "uiflow3-runtime",
        "runtime_sha": "uiflow3-runtime",
        "worker_compatible": True,
        "worker_connected": True,
        "worker_heartbeat_fresh": True,
        "worker_lease_valid": True,
        "worker_sha_match": True,
        "worker_capability_match": True,
        "worker_identity_conflict": False,
        "route_requires_provider": bool(route["route_requires_provider"]),
        "handler_id": queue.PRODUCT_VIDEO_PUBLIC_CONFIRM_HANDLER_ID,
        "worker_admission_block_reason": "",
        "duplicate_confirm_handler_detected": False,
    }
    return queue.sign_product_video_final_admission_context(admission)


def _counts(conn: sqlite3.Connection) -> tuple[int, int, int, int]:
    return tuple(
        int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        for table in (
            "video_projects",
            "video_scenes",
            "video_jobs",
            "video_dispatch_outbox",
        )
    )


def _enabled_seam(monkeypatch: pytest.MonkeyPatch) -> None:
    values = {
        "PRODUCT_VIDEO_DURABLE_PUBLIC_SEAM_ENABLED": "1",
        "PRODUCT_VIDEO_ONE_SCENE_ENGINE_ENABLED": "1",
        "PRODUCT_VIDEO_ONE_SCENE_PUBLIC_ALLOWED": "1",
        "PRODUCT_VIDEO_ONE_SCENE_REAL_PROVIDER_ENABLED": "1",
        "PRODUCT_VIDEO_ONE_SCENE_AUTO_RETRY": "0",
        "PRODUCT_VIDEO_ONE_SCENE_AUTO_FALLBACK": "0",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_uiflow3_bridge_preserves_exact_snapshot_fields_and_structured_ratio() -> None:
    bridge = _bridge()
    snapshot = video_uiflow3.approved_snapshot(_ready_state(scene_count=2))

    handoff = bridge.compile_routeengine_handoff(
        snapshot,
        owner_user_id=USER_ID,
        owner_chat_id=USER_ID,
    )

    assert handoff["ok"] is True
    assert handoff["commercial_ready"] is True
    assert handoff["snapshot_config_hash"] == snapshot["config_hash"]
    assert handoff["public_product_type"] == "video_ai_prompt"
    assert handoff["route_selection"]["engine_product"] == "product_video"
    assert handoff["route_selection"]["mode"] == "multi_scene"
    assert handoff["aspect_ratio"] == "9:16"
    assert handoff["output_geometry"] == {"width": 1080, "height": 1920}
    assert [item["scene_id"] for item in handoff["scene_cards"]] == [
        "scene_01",
        "scene_02",
    ]
    assert all(item["aspect_ratio"] == "9:16" for item in handoff["scene_cards"])
    assert all(item["provider_prompt"] for item in handoff["scene_cards"])
    assert handoff["addon_plan"]["branding"]["watermark"]["text"] == "TOAN AAS"
    assert handoff["side_effects"] == {
        "provider_calls": 0,
        "jobs": 0,
        "outbox": 0,
        "wallet_mutations": 0,
        "charges": 0,
    }


def test_uiflow3_bridge_blocks_product_duration_drift_instead_of_silently_using_8s() -> None:
    bridge = _bridge()
    snapshot = video_uiflow3.approved_snapshot(
        _ready_state(scene_count=1, target_duration_seconds=6)
    )

    handoff = bridge.compile_routeengine_handoff(
        snapshot,
        owner_user_id=USER_ID,
        owner_chat_id=USER_ID,
    )

    assert handoff["ok"] is True
    assert handoff["commercial_ready"] is False
    assert handoff["commercial_blocker"] == "uiflow3_product_duration_contract_mismatch"
    assert handoff["target_duration_seconds"] == 6
    assert handoff["scene_duration_seconds"] == [8]
    assert handoff["side_effects"] == {
        "provider_calls": 0,
        "jobs": 0,
        "outbox": 0,
        "wallet_mutations": 0,
        "charges": 0,
    }


def test_uiflow3_bridge_blocks_unmaterialized_voice_instead_of_dropping_it() -> None:
    bridge = _bridge()
    snapshot = video_uiflow3.approved_snapshot(_ready_state())
    snapshot["audio"]["voice_cast"] = {
        "narrator_01": {
            "voice_id": "server-voice-01",
            "gender": "female",
            "server_renderable": True,
        }
    }
    snapshot["audio"]["dialogue_segments"] = [
        {
            "dialogue_id": "dlg_01",
            "scene_id": "scene_01",
            "speaker_id": "narrator_01",
            "text": "Day la loi thoai phai duoc materialize thanh am thanh.",
            "order": 1,
        }
    ]
    snapshot["render_blockers"] = []
    snapshot = _rehash_snapshot(snapshot)

    handoff = bridge.compile_routeengine_handoff(
        snapshot,
        owner_user_id=USER_ID,
        owner_chat_id=USER_ID,
    )

    assert handoff["ok"] is True
    assert handoff["commercial_ready"] is False
    assert handoff["commercial_blocker"] == "uiflow3_voice_materialization_missing"
    assert "uiflow3_voice_materialization_missing" in handoff["bridge_blockers"]


def test_uiflow3_bridge_blocks_unmaterialized_reference_images() -> None:
    bridge = _bridge()
    snapshot = video_uiflow3.approved_snapshot(_ready_state())
    snapshot["references"] = [
        {
            "asset_id": "asset_01",
            "asset_type": "image",
            "owner_type": "source_video",
            "owner_id": "source_01",
            "role": "identity_reference",
            "telegram_file_id": "telegram-reference-01",
            "fingerprint": "telegram:reference-01",
            "allowed_scene_ids": ["scene_01"],
        }
    ]
    snapshot = _rehash_snapshot(snapshot)

    handoff = bridge.compile_routeengine_handoff(
        snapshot,
        owner_user_id=USER_ID,
        owner_chat_id=USER_ID,
    )

    assert handoff["ok"] is True
    assert handoff["commercial_ready"] is False
    assert handoff["commercial_blocker"] == "uiflow3_reference_materialization_missing"


def test_uiflow3_bridge_keeps_character_voice_dialogue_and_scene_ownership() -> None:
    bridge = _bridge()
    snapshot = _rich_planning_snapshot()

    handoff = bridge.compile_routeengine_handoff(
        snapshot,
        owner_user_id=USER_ID,
        owner_chat_id=USER_ID,
    )

    assert handoff["ok"] is True
    assert handoff["commercial_ready"] is False
    assert handoff["render_blockers"] == snapshot["render_blockers"]
    bible = handoff["story_bible"]
    assert [item["character_id"] for item in bible["characters"]] == [
        "char_01",
        "char_02",
    ]
    assert [item["location_id"] for item in bible["locations"]] == [
        "loc_01",
        "loc_02",
    ]
    assert set(handoff["voice_policy"]["voice_cast"]) == {"char_01", "char_02"}
    assert [item["speaker_id"] for item in handoff["audio_policy"]["dialogue_segments"]] == [
        "char_01",
        "char_02",
    ]
    assert handoff["scene_cards"][0]["character_ids"] == ["char_01"]
    assert handoff["scene_cards"][1]["character_ids"] == ["char_02"]
    assert handoff["scene_cards"][0]["location_id"] == "loc_01"
    assert handoff["scene_cards"][1]["location_id"] == "loc_02"


@pytest.mark.parametrize("mutation", ("hash", "scene_count", "owner"))
def test_uiflow3_bridge_fails_closed_on_tamper_or_owner_mismatch(mutation: str) -> None:
    bridge = _bridge()
    snapshot = video_uiflow3.approved_snapshot(_ready_state())
    owner_user_id = USER_ID
    if mutation == "hash":
        snapshot["content"]["original_intent"] = "tampered after approval"
    elif mutation == "scene_count":
        snapshot["format"]["scene_count"] = 2
    else:
        owner_user_id = 0

    result = bridge.compile_routeengine_handoff(
        snapshot,
        owner_user_id=owner_user_id,
        owner_chat_id=USER_ID,
    )

    assert result["ok"] is False
    assert result["commercial_ready"] is False
    assert result["blocker"] in {
        "uiflow3_snapshot_hash_mismatch",
        "uiflow3_scene_count_mismatch",
        "uiflow3_owner_required",
    }
    assert result["side_effects"]["provider_calls"] == 0
    assert result["side_effects"]["jobs"] == 0
    assert result["side_effects"]["wallet_mutations"] == 0


def test_uiflow3_bridge_persists_one_idempotent_draft_without_submit(
    tmp_path: Path,
) -> None:
    bridge = _bridge()
    conn = sqlite3.connect(tmp_path / "uiflow3-routeengine.db")
    conn.row_factory = sqlite3.Row
    snapshot = video_uiflow3.approved_snapshot(_ready_state())
    handoff = bridge.compile_routeengine_handoff(
        snapshot,
        owner_user_id=USER_ID,
        owner_chat_id=USER_ID,
    )

    first = bridge.prepare_commercial_project(
        conn,
        handoff,
        quote=_quote(1),
    )
    second = bridge.prepare_commercial_project(
        conn,
        deepcopy(handoff),
        quote=_quote(1),
    )

    assert first["ok"] is True
    assert second["ok"] is True
    assert second["duplicate_prevented"] is True
    assert first["project"]["project_id"] == second["project"]["project_id"]
    assert _counts(conn) == (1, 1, 0, 0)
    project = first["project"]
    assert project["status"] == "draft_invoice"
    assert project["ratio"] == "9:16"
    asset_pack = json.loads(project["asset_pack_json"])
    addon_plan = json.loads(project["addon_plan_json"])
    assert asset_pack["uiflow3_snapshot_config_hash"] == snapshot["config_hash"]
    assert asset_pack["uiflow3_route_selection_sha256"] == handoff["route_selection"]["route_selection_sha256"]
    assert asset_pack["output_geometry"] == {"height": 1920, "width": 1080}
    assert asset_pack["watermark_config"] == {
        "enabled": True,
        "position": "top_right",
        "text": "TOAN AAS",
    }
    assert addon_plan["logo_enabled"] is True
    assert addon_plan["logo_source"] == "text"
    assert addon_plan["logo_text"] == "TOAN AAS"
    assert addon_plan["logo_position"] == "top_right"
    assert addon_plan["subtitle_enabled"] is False
    assert json.loads(project["scene_cards_json"])[0]["scene_id"] == "scene_01"
    selection = video_engine_contract.durable_video_product_route_selection(project)
    assert selection["selection_ok"] is True
    assert selection["engine_product"] == "product_video"
    assert selection["mode"] == "single_scene"


def test_uiflow3_bridge_explicit_confirm_is_the_first_job_and_preserves_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = _bridge()
    _enabled_seam(monkeypatch)
    conn = sqlite3.connect(tmp_path / "uiflow3-confirm.db")
    conn.row_factory = sqlite3.Row
    snapshot = video_uiflow3.approved_snapshot(_ready_state())
    handoff = bridge.compile_routeengine_handoff(
        snapshot,
        owner_user_id=USER_ID,
        owner_chat_id=USER_ID,
    )
    prepared = bridge.prepare_commercial_project(conn, handoff, quote=_quote(1))

    assert _counts(conn) == (1, 1, 0, 0)
    confirmed = queue.confirm_public_product_video_invoice(
        conn,
        project_id=int(prepared["project"]["project_id"]),
        user_id=USER_ID,
        balance_xu=300,
        provider_admission=_admission(prepared["project"]),
    )

    assert confirmed["ok"] is True
    assert _counts(conn) == (1, 1, 1, 1)
    job = queue.hydrate_video_job_payload(conn, confirmed["job"])
    asset_pack = json.loads(job["project"]["asset_pack_json"])
    persisted = json.loads(job["result_json"])
    assert asset_pack["uiflow3_snapshot_config_hash"] == snapshot["config_hash"]
    assert asset_pack["uiflow3_handoff_sha256"] == handoff["handoff_sha256"]
    assert asset_pack["uiflow3_route_selection_sha256"] == handoff["route_selection"]["route_selection_sha256"]
    assert job["project"]["ratio"] == "9:16"
    assert job["product_video_route_decision"]["engine_product"] == "product_video"
    assert job["product_video_route_decision"]["mode"] == "single_scene"
    assert persisted["charge"] == 0
    assert persisted["charged_xu"] == 0


def test_uiflow3_bridge_never_prepares_render_blocked_plan(tmp_path: Path) -> None:
    bridge = _bridge()
    conn = sqlite3.connect(tmp_path / "uiflow3-blocked.db")
    conn.row_factory = sqlite3.Row
    handoff = bridge.compile_routeengine_handoff(
        _rich_planning_snapshot(),
        owner_user_id=USER_ID,
        owner_chat_id=USER_ID,
    )

    result = bridge.prepare_commercial_project(conn, handoff, quote=_quote(2))

    assert result["ok"] is False
    assert result["blocker"] == "uiflow3_render_blockers_present"
    assert _counts(conn) == (0, 0, 0, 0)
