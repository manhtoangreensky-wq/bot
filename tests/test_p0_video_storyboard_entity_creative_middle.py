from __future__ import annotations

import html
import re
import subprocess
import hashlib
import json
import uuid
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

from services import video_scene3_flow, video_storyboard2, video_uiflow3


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")
BOT_BYTES = (ROOT / "bot.py").read_bytes()
STORYBOARD_BYTES = (ROOT / "services" / "video_storyboard2.py").read_bytes()


def _function_source(source: str, name: str) -> str:
    match = re.search(rf"^(?:async )?def {re.escape(name)}\(", source, re.MULTILINE)
    assert match, f"missing function: {name}"
    next_match = re.search(
        r"\n(?=@|(?:async )?def [A-Za-z_])",
        source[match.end() :],
    )
    end = match.end() + next_match.start() if next_match else len(source)
    return source[match.start() : end]


def _function_bytes(source: bytes, name: str) -> bytes:
    match = re.search(
        rb"^(?:async )?def " + re.escape(name.encode("ascii")) + rb"\(",
        source,
        re.MULTILINE,
    )
    assert match, f"missing function bytes: {name}"
    next_match = re.search(
        rb"\r?\n(?=@|(?:async )?def [A-Za-z_])",
        source[match.end() :],
    )
    end = match.end() + next_match.start() if next_match else len(source)
    return source[match.start() : end]


def _git_canonical_bytes(value: bytes) -> bytes:
    return value.replace(b"\r\n", b"\n")


def _board() -> dict:
    board = video_storyboard2.default_state()
    board = video_storyboard2.set_scene_count(board, 3)
    board = video_storyboard2.set_ratio(board, "9:16")
    return video_storyboard2.apply_content(
        board,
        "Một nhân vật giới thiệu sản phẩm trong cùng một bối cảnh.",
        mode="manual",
    )


def _board_with_required_images() -> dict:
    board = video_storyboard2.ensure_session(_board(), "storyboard-session")
    for scene_index in range(1, int(board["scene_count"]) + 1):
        board = video_storyboard2.assign_image(
            board,
            scene_index,
            "start",
            video_storyboard2.image_record(
                scene_index=scene_index,
                slot="start",
                file_id=f"storyboard-image-{scene_index}",
                source_type="telegram_upload",
            ),
        )
    return video_storyboard2.confirm_existing_image_gate(board)


def test_storyboard_middle_contract_persists_entities_style_and_motion() -> None:
    board = video_storyboard2.apply_middle_contract(
        _board(),
        bible={
            "characters": [{"character_id": "char_01", "display_name": "Lan"}],
            "locations": [{"location_id": "loc_01", "name": "Studio"}],
            "products": [{"product_id": "prod_01", "name": "Sản phẩm A"}],
            "props": [],
            "continuity": {"identity": True, "location": True},
        },
        references=[{"asset_id": "asset_01", "file_id": "image-01"}],
        needs={"characters": "REQUIRED"},
        entity_summary="1 nhân vật · 1 bối cảnh · 1 sản phẩm",
        creative_controls={
            "visual_style": {"enabled": True, "value": "Điện ảnh chân thật"},
            "colors": {"enabled": True, "value": "Xanh lá và trắng"},
            "camera": {"enabled": True, "value": "Máy quay ngang tầm mắt"},
            "motion": {"enabled": True, "value": "Chuyển động chậm, liền mạch"},
            "negative": {"enabled": True, "value": "Không đổi khuôn mặt"},
        },
    )

    assert board["middle_complete"] is True
    assert board["entity_bible"]["characters"][0]["display_name"] == "Lan"
    assert board["entity_references"][0]["file_id"] == "image-01"
    assert board["style"]["visual"] == "Điện ảnh chân thật"
    assert board["style"]["colors"] == "Xanh lá và trắng"
    assert all("Máy quay ngang tầm mắt" in scene["camera_motion"] for scene in board["scenes"])
    assert all(scene["subject_motion"] == "Chuyển động chậm, liền mạch" for scene in board["scenes"])
    assert all(scene["negative_constraints"] == "Không đổi khuôn mặt" for scene in board["scenes"])


def test_storyboard_middle_contract_removes_disabled_old_creative_values() -> None:
    selected = video_storyboard2.apply_middle_contract(
        _board(),
        bible={},
        references=[],
        needs={},
        entity_summary="",
        creative_controls={
            "visual_style": {"enabled": True, "value": "Điện ảnh"},
            "camera": {"enabled": True, "value": "Máy quay thấp"},
            "motion": {"enabled": True, "value": "Chuyển động nhanh"},
            "negative": {"enabled": True, "value": "Không rung"},
        },
    )
    cleared = video_storyboard2.apply_middle_contract(
        selected,
        bible={},
        references=[],
        needs={},
        entity_summary="",
        creative_controls={
            "visual_style": {"enabled": False, "value": "Điện ảnh"},
            "camera": {"enabled": False, "value": "Máy quay thấp"},
            "motion": {"enabled": False, "value": "Chuyển động nhanh"},
            "negative": {"enabled": False, "value": "Không rung"},
        },
    )

    assert "visual" not in cleared["style"]
    assert all(scene["camera_motion"] != "Máy quay thấp" for scene in cleared["scenes"])
    assert all(scene["subject_motion"] != "Chuyển động nhanh" for scene in cleared["scenes"])
    assert all(scene["negative_constraints"] != "Không rung" for scene in cleared["scenes"])


def test_storyboard_middle_values_reach_existing_prompt_inputs() -> None:
    board = video_storyboard2.apply_middle_contract(
        _board(),
        bible={
            "characters": [{"character_id": "char_01", "display_name": "Lan"}],
            "locations": [{"location_id": "loc_01", "name": "Studio xanh"}],
            "continuity": {"identity": True, "location": True},
        },
        references=[],
        needs={},
        entity_summary="1 nhân vật · 1 bối cảnh",
        creative_controls={
            "context": {"enabled": True, "value": "Mở gần rồi hé lộ toàn cảnh"},
            "visual_style": {"enabled": True, "value": "Điện ảnh chân thật"},
            "colors": {"enabled": True, "value": "Xanh lá và trắng"},
            "camera": {"enabled": True, "value": "Máy quay ngang tầm mắt"},
            "motion": {"enabled": True, "value": "Chuyển động chậm, liền mạch"},
            "pacing": {"enabled": True, "value": "Nhịp vừa"},
            "emotion": {"enabled": True, "value": "Tin cậy"},
        },
    )

    image_prompt = video_storyboard2.image_prompt(board, 1, "start")["prompt"]
    for expected in (
        "Lan",
        "Studio xanh",
        "Máy quay ngang tầm mắt",
    ):
        assert expected in image_prompt

    for scene_index in range(1, 4):
        board = video_storyboard2.assign_image(
            board,
            scene_index,
            "start",
            video_storyboard2.image_record(
                scene_index=scene_index,
                slot="start",
                file_id=f"start-{scene_index}",
                source_type="telegram_upload",
            ),
        )
    board = video_storyboard2.compile_video_prompts(board)
    video_prompt = board["scenes"][0]["video_prompt"]
    for expected in (
        "Máy quay ngang tầm mắt",
        "Chuyển động chậm, liền mạch",
    ):
        assert expected in video_prompt


def test_all_storyboard_content_lanes_enter_existing_assets_before_entity() -> None:
    callback = _function_source(BOT_SOURCE, "_handle_storyboard2_callback_impl")
    pending_text = _function_source(BOT_SOURCE, "handle_storyboard2_pending_text")
    idea_return = _function_source(BOT_SOURCE, "video_idea_render_exact_parent")

    assert "video_storyboard_prepare_reference_bridge" not in BOT_SOURCE
    assert "video_storyboard_store_reference_source" not in BOT_SOURCE
    assert callback.count("video_storyboard_open_required_assets") >= 4
    assert "video_storyboard_open_required_assets" in pending_text
    assert "video_storyboard_prepare_entity_bridge" not in pending_text
    assert "storyboard2_screen_payload" in pending_text
    existing_lane = callback[
        callback.index('if entry_mode == "existing":'):
        callback.index('if action == "idea_source":')
    ]
    assert "video_storyboard_open_required_assets" in existing_lane
    assert "seed_uploaded=True" in existing_lane
    suggestion_lane = callback[
        callback.index('if action == "suggest_pick":'):
        callback.index('if action == "scene_screen":')
    ]
    assert "video_storyboard_open_required_assets" in suggestion_lane
    storyboard_idea = idea_return[
        idea_return.index('if product_id == "storyboard_prompt":'):
        idea_return.index('if product_id == video_selfshot2.PRODUCT_ID:')
    ]
    assert "video_storyboard_open_required_assets" in storyboard_idea
    assert "video_storyboard_prepare_entity_bridge" not in storyboard_idea
    assert "storyboard2_render" in storyboard_idea
    assert 'move(board, "scene_review"' not in idea_return[idea_return.index('if product_id == "storyboard_prompt":') : idea_return.index('if product_id == video_selfshot2.PRODUCT_ID:')]


def test_storyboard_required_assets_use_existing_manager_and_exact_back_stack() -> None:
    asset_open = _function_source(BOT_SOURCE, "video_storyboard_open_required_assets")
    asset_back = _function_source(BOT_SOURCE, "storyboard2_asset_back_callback")
    uiflow_callback = _function_source(BOT_SOURCE, "handle_video_uiflow3_callback")
    storyboard_callback = _function_source(BOT_SOURCE, "_handle_storyboard2_callback_impl")

    assert 'move(current, "assets", push=False' in asset_open
    assert '"suggestions": "vstory|suggestions_screen"' in asset_back
    assert '"await_content": "vstory|content_manual"' in asset_back
    assert '"ratio": "vstory|ratio_screen"' in asset_back
    assert '"content_source": "vstory|content_screen"' in asset_back
    assert 'str(storyboard_marker.get("phase") or "") == "reference"' in uiflow_callback
    stale_source = uiflow_callback[
        uiflow_callback.index('storyboard_marker = video_storyboard_entity_bridge_marker(state)'):
        uiflow_callback.index('if action != "entry" and not video_uiflow3_action_allowed')
    ]
    assert 'storyboard_marker["phase"] = "assets"' in stale_source
    assert "video_storyboard_open_required_assets" in stale_source

    assert 'if action == "reference_back":' in storyboard_callback
    reference_back = storyboard_callback[
        storyboard_callback.index('if action == "reference_back":'):
        storyboard_callback.index('if action == "entity_back":')
    ]
    assert 'marker["phase"] = "assets"' in reference_back
    assert "video_storyboard_open_required_assets" in reference_back
    entity_back = storyboard_callback[
        storyboard_callback.index('if action == "entity_back":'):
        storyboard_callback.index('if action == "creative_screen":')
    ]
    assert 'marker["phase"] = "assets"' in entity_back
    assert "video_storyboard_open_required_assets" in entity_back


def test_storyboard_stale_downstream_callbacks_cannot_bypass_the_middle() -> None:
    board = _board()
    assert board["middle_complete"] is False
    assert "storyboard_middle_incomplete" in video_storyboard2.preflight(board)["blockers"]

    callback = _function_source(BOT_SOURCE, "_handle_storyboard2_callback_impl")
    assert "STORYBOARD2_MIDDLE_REQUIRED_ACTIONS" in callback
    assert 'not bool(board.get("middle_complete"))' in callback
    assert "video_storyboard_prepare_entity_bridge" in callback


def test_storyboard_reference_image_is_required_by_preflight() -> None:
    board = video_storyboard2.apply_middle_contract(
        _board(),
        bible={},
        references=[],
        needs={},
        entity_summary="",
        creative_controls={},
    )
    assert "storyboard_reference_image_missing" in video_storyboard2.preflight(board)["blockers"]

    board = video_storyboard2.set_reference_source_assets(
        board,
        [{"asset_id": "source_01", "telegram_file_id": "image-01"}],
        complete=True,
    )
    assert "storyboard_reference_image_missing" not in video_storyboard2.preflight(board)["blockers"]


def test_stale_storyboard_callbacks_never_replace_another_product_owner() -> None:
    callback = _function_source(BOT_SOURCE, "_handle_storyboard2_callback_impl")
    owner_guard = callback[: callback.index("if callback_id:")]
    assert "STORYBOARD2_FRESH_START_ACTIONS" in owner_guard
    assert "active_storyboard" in owner_guard
    assert "action not in STORYBOARD2_FRESH_START_ACTIONS" in owner_guard
    assert owner_guard.index("action not in STORYBOARD2_FRESH_START_ACTIONS") < owner_guard.index(
        "storyboard2_new_outer_state"
    )
    assert "Phiên Storyboard cũ không thay đổi sản phẩm đang mở" in owner_guard


def test_storyboard_entity_bridge_owns_one_session_and_exact_back_callback() -> None:
    context = SimpleNamespace(user_data={})

    def save_board(_context, board):
        _context.user_data["board"] = video_storyboard2.normalize_state(board)
        return {"storyboard2": _context.user_data["board"]}

    def ui_state(_context):
        return dict(_context.user_data.get("uiflow3") or video_uiflow3.new_state("storyboard_prompt"))

    def save_ui(_context, state):
        clean = video_uiflow3.normalize_state(state)
        _context.user_data["uiflow3"] = clean
        return clean

    namespace = {
        "deepcopy": deepcopy,
        "hashlib": hashlib,
        "json": json,
        "uuid": uuid,
        "video_storyboard2": video_storyboard2,
        "video_uiflow3": video_uiflow3,
        "save_storyboard2_state": save_board,
        "video_uiflow3_state": ui_state,
        "save_video_uiflow3_state": save_ui,
        "video_uiflow3_clear_transient": lambda state, keep_return=False: state,
        "safe_int": lambda value, default=0: int(value or default),
    }
    for name in (
        "video_storyboard_entity_bridge_marker",
        "video_storyboard_entity_bridge_key",
        "video_storyboard_prepare_entity_bridge",
    ):
        exec("from __future__ import annotations\n" + _function_source(BOT_SOURCE, name), namespace)

    board = _board_with_required_images()
    state = namespace["video_storyboard_prepare_entity_bridge"](
        SimpleNamespace(chat_id=99),
        42,
        context,
        board,
        return_screen="await_content",
    )
    marker = namespace["video_storyboard_entity_bridge_marker"](state)

    assert state["parent_product"] == "storyboard_prompt"
    assert state["navigation"]["current_step"] == "production_bible"
    assert video_uiflow3.next_required_step(state) == "production_bible"
    assert marker["active"] is True
    assert marker["storyboard_session_id"] == "storyboard-session"
    assert marker["phase"] == "entity"
    assert marker["back_callback"] == f"vstory|entity_back|{marker['bridge_key']}"
    assert marker["return_screen"] == "await_content"
    assert context.user_data["board"]["entity_return_screen"] == "await_content"


def test_storyboard_existing_image_gate_reuses_scene_images_without_duplicates() -> None:
    board = _board_with_required_images()
    assets = list(board["reference_source_assets"])

    assert board["reference_gate_complete"] is True
    assert len(assets) == int(board["scene_count"])
    assert [item["owner_id"] for item in assets] == ["scene_1", "scene_2", "scene_3"]
    assert all(item["owner_type"] == "storyboard_panel" for item in assets)
    assert all(item["role"] == "start_frame" for item in assets)

    confirmed_again = video_storyboard2.confirm_existing_image_gate(board)
    assert [item["asset_id"] for item in confirmed_again["reference_source_assets"]] == [
        item["asset_id"] for item in assets
    ]

    uploaded = video_storyboard2.add_uploaded_storyboard(
        _board(),
        video_storyboard2.storyboard_upload_record(
            file_id="uploaded-storyboard-image",
            file_unique_id="uploaded-storyboard-image-unique",
            file_name="panel.png",
            mime_type="image/png",
        ),
    )
    seeded = video_storyboard2.seed_uploaded_storyboard_images(uploaded)
    seeded_again = video_storyboard2.seed_uploaded_storyboard_images(seeded)
    assert video_storyboard2.asset_summary(seeded)["ready_start"] == 1
    assert video_storyboard2.asset_summary(seeded_again)["ready_start"] == 1


def test_storyboard_entity_and_creative_callbacks_have_exact_parent_returns() -> None:
    marker = _function_source(BOT_SOURCE, "video_storyboard_entity_bridge_marker")
    pilot_owner = _function_source(BOT_SOURCE, "video_uiflow3_uses_entity_pilot")
    entity_finish = _function_source(BOT_SOURCE, "video_storyboard_finish_entity_bridge")
    creative_finish = _function_source(BOT_SOURCE, "video_storyboard_finish_creative_details")
    uiflow_callback = _function_source(BOT_SOURCE, "handle_video_uiflow3_callback")
    storyboard_callback = _function_source(BOT_SOURCE, "_handle_storyboard2_callback_impl")
    scene_keyboard = _function_source(BOT_SOURCE, "storyboard2_scene_review_keyboard")
    prompt_keyboard = _function_source(BOT_SOURCE, "storyboard2_video_prompt_keyboard")
    creative_open = _function_source(BOT_SOURCE, "video_storyboard_open_creative_details")

    assert 'parent_product") or "") != "storyboard_prompt"' in marker
    assert "storyboard_entity_bridge" in marker
    assert "video_storyboard_entity_bridge_marker(raw_state)" in pilot_owner
    assert "video_storyboard_entity_bridge_marker(state)" in uiflow_callback
    assert "video_storyboard_finish_entity_bridge" in uiflow_callback
    assert "video_storyboard_open_creative_details" in entity_finish
    assert 'marker.get("phase") or "") != "entity"' in entity_finish
    assert 'marker["phase"] = "creative"' in entity_finish
    assert 'marker["phase"] = "requirements"' in uiflow_callback
    assert "video_storyboard_finish_creative_details" in uiflow_callback
    assert 'marker["phase"] = "scene_review"' in creative_finish
    assert 'marker["phase"] = "entity"' in uiflow_callback
    assert 'str(marker.get("bridge_key") or "") != value' in storyboard_callback
    assert 'str(marker.get("storyboard_session_id") or "") != str(board.get("storyboard_session_id") or "")' in storyboard_callback
    assert 'str((bridge_state.get("navigation") or {}).get("current_step") or "") != "production_bible"' in storyboard_callback
    assert 'str(bridge_state.get("ui_view") or "")' in storyboard_callback
    assert 'str(board.get("screen") or "") != "scene_review"' in storyboard_callback
    assert "return await render_storyboard_current_owner()" in storyboard_callback
    assert 'move(board, "scene_review"' in creative_finish
    assert 'f"vstory|entity_back|{bridge_key}"' in BOT_SOURCE
    assert '"vstory|creative_screen"' in scene_keyboard
    assert 'return_to_requirements = marker_phase == "scene_review"' in creative_open
    assert '"pilot_requirements" if return_to_requirements' in creative_open
    assert '*storyboard2_nav("vstory|scene_screen")' in prompt_keyboard


def test_storyboard_uses_realistic_character_hub_without_duplicate_context() -> None:
    class _UiFlow:
        VIDEO_AI_REAL_PRODUCT_FIRST_MODES = frozenset({"prompt_video", "image_video"})

    namespace = {
        "video_uiflow3": _UiFlow,
        "video_uiflow3_uses_entity_pilot": lambda _state: True,
        "video_storyboard_entity_bridge_marker": lambda _state: {
            "active": True,
            "back_callback": "vstory|entity_back|bridge-key",
        },
        "video_entity_bridge_marker": lambda _state: {},
        "video_ai_real_pilot_input_payload": lambda _state: None,
        "video_ai_real_pilot_bible_view_payload": lambda _state, view: None,
        "video_ai_real_pilot_scene_view_payload": lambda _state, view: None,
        "video_ai_real_pilot_prompt_view_payload": lambda _state, view: None,
        "video_ai_real_pilot_nav_rows": lambda back: [[("⬅️ Quay lại", back), ("🎬 Menu Video", "menu|main_video")]],
        "video_uiflow3_keyboard": lambda rows: rows,
    }
    exec(
        "from __future__ import annotations\n"
        + _function_source(BOT_SOURCE, "video_ai_real_pilot_screen_payload"),
        namespace,
    )
    state = {
        "entry_mode": "storyboard_entities",
        "bible": {
            "characters": [],
            "locations": [],
            "products": [],
            "props": [],
        },
        "references": [],
    }

    payload = namespace["video_ai_real_pilot_screen_payload"](
        state,
        step="production_bible",
        view="",
        prefix="",
    )

    assert payload is not None
    text, rows = payload
    labels = [label for row in rows for label, _callback in row]
    assert "👥 Nhân vật và tham chiếu" in text
    assert "Bối cảnh" not in text
    assert not any("Bối cảnh" in label for label in labels)
    assert {
        "👥 Số nhân vật",
        "👤 Danh sách nhân vật",
        "🖼 Ảnh tham chiếu",
        "🛠 Tùy chỉnh chi tiết",
        "⚡ Tạo nhanh",
        "✨ Tự động gợi ý",
        "✅ Hoàn tất thiết lập nhân vật",
    }.issubset(set(labels))
    assert [(label, callback) for label, callback in rows[2]] == [
        ("⚡ Tạo nhanh", "vid3|quick_build"),
        ("✨ Tự động gợi ý", "vid3|bible_auto"),
    ]
    assert rows[3] == [("✅ Hoàn tất thiết lập nhân vật", "vid3|bible_done")]
    assert labels[-2:] == ["⬅️ Quay lại", "🎬 Menu Video"]


def test_storyboard_style_has_auto_suggestions_without_quick_build() -> None:
    class _SceneFlow:
        CREATIVE_CONTROLS = video_scene3_flow.CREATIVE_CONTROLS

    namespace = {
        "video_scene3_flow": _SceneFlow,
        "video_ai_real_pilot_scene3_field_state": lambda state: state,
        "video_storyboard_entity_bridge_marker": lambda _state: {"active": True},
        "video_scene3_summary": lambda _entries, _catalog: "Chưa thêm",
        "video_uiflow3_keyboard": lambda rows: rows,
        "video_ai_real_pilot_nav_rows": lambda back: [[("⬅️ Quay lại", back), ("🎬 Menu Video", "menu|main_video")]],
    }
    exec(
        "from __future__ import annotations\n"
        + _function_source(BOT_SOURCE, "video_ai_real_pilot_creative_payload"),
        namespace,
    )

    text, rows = namespace["video_ai_real_pilot_creative_payload"](
        {"creative_controls": {}}
    )
    labels = [label for row in rows for label, _callback in row]
    assert "🎨 Tùy chỉnh phong cách" in text
    assert all(len(row) == 2 for row in rows[:4])
    assert rows[4] == [("✨ Tự động gợi ý", "vid3|pilot_creative_auto")]
    assert "⚡ Tạo nhanh" not in labels
    assert "✅ Xong phong cách" in labels
    assert "⏭ Bỏ qua" in labels


def test_standard_requirements_keep_environment_once_and_offer_automatic_suggestions() -> None:
    category_start = BOT_SOURCE.index("VIDEO_AI_REAL_PILOT_REQUIREMENT_CATEGORIES =")
    category_end = BOT_SOURCE.index("\ndef video_ai_real_pilot_scene3_field_state", category_start)
    category_contract = BOT_SOURCE[category_start:category_end]
    assert "PUBLIC_REQUIREMENT_CATEGORIES" in category_contract
    assert 'item[0] != "environment"' not in category_contract

    class _SceneFlow:
        CREATIVE_CONTROLS = ()

    categories = video_scene3_flow.PUBLIC_REQUIREMENT_CATEGORIES
    namespace = {
        "html": html,
        "VIDEO_AI_REAL_PILOT_REQUIREMENT_CATEGORIES": categories,
        "video_scene3_flow": _SceneFlow,
        "video_ai_real_pilot_scene3_field_state": lambda state: state,
        "video_ai_real_uses_inline_requirements": lambda _state: True,
        "video_scene3_entry_label": lambda entry: str(entry.get("value") or "Chưa thêm"),
        "video_scene3_summary": lambda _entries, _catalog: "Chưa thêm",
        "video_uiflow3_keyboard": lambda rows: rows,
        "video_ai_real_pilot_nav_rows": lambda back: [[("⬅️ Quay lại", back), ("🎬 Menu Video", "menu|main_video")]],
    }
    exec(
        "from __future__ import annotations\n"
        + _function_source(BOT_SOURCE, "video_ai_real_pilot_requirements_payload"),
        namespace,
    )

    text, rows = namespace["video_ai_real_pilot_requirements_payload"](
        {
            "preservation_requirements": {
                "identity": {"enabled": True, "value": "Khuôn mặt nhất quán"},
            }
        }
    )
    labels = [label for row in rows for label, _callback in row]
    callbacks = [callback for row in rows for _label, callback in row]
    assert len(categories) == 7
    assert all(len(row) == 2 for row in rows[:4])
    assert "➕ Bối cảnh/kiến trúc" in labels
    assert "✨ Tự động gợi ý" in labels
    assert "👁 Xem mục đã chọn" not in labels
    assert "vid3|pilot_requirement_auto" in callbacks
    assert "vid3|pilot_requirement_view" not in callbacks
    assert "• 🧍 Nhân vật/nhận diện: Khuôn mặt nhất quán" in text
    assert "không hỏi lại ở màn Nhân vật" in text


def test_inline_requirements_are_scoped_to_video_ai_and_storyboard_only() -> None:
    namespace: dict[str, object] = {}
    exec(
        "from __future__ import annotations\n"
        + _function_source(BOT_SOURCE, "video_ai_real_uses_inline_requirements"),
        namespace,
    )
    uses_inline = namespace["video_ai_real_uses_inline_requirements"]

    assert uses_inline({"parent_product": "video_ai_real"}) is True
    assert uses_inline({"parent_product": "storyboard_prompt"}) is True
    for protected_product in ("script_image_video", "video_trend", "multi_scene_film"):
        assert uses_inline({"parent_product": protected_product}) is False

    payload_source = _function_source(BOT_SOURCE, "video_ai_real_pilot_requirements_payload")
    legacy_start = payload_source.index("else:", payload_source.index("if inline_summary:"))
    legacy_rows = payload_source.index("rows.extend([", legacy_start)
    legacy_branch = payload_source[
        legacy_start:
        payload_source.index("rows.extend([", legacy_rows + 1)
    ]
    assert "✨ Tự động gợi ý" in legacy_branch
    assert "👁 Xem mục đã chọn" in legacy_branch


def test_all_middle_suggestion_catalogs_have_five_distinct_pages() -> None:
    state = video_scene3_flow.default_state(
        product_type="storyboard_prompt",
        subject="Một câu chuyện nhiều cảnh",
        aspect_ratio="9:16",
    )
    groups = (
        ("creative_controls", video_scene3_flow.CREATIVE_CONTROLS),
        ("preservation_requirements", video_scene3_flow.PUBLIC_REQUIREMENT_CATEGORIES),
    )
    for group, categories in groups:
        for key, _label in categories:
            catalog = video_scene3_flow.unified_field_suggestion_catalog(state, group, key)
            assert len(catalog) >= 25, (group, key, len(catalog))
            assert len(catalog) == len(set(catalog)), (group, key)

            page_state = state
            pages: list[tuple[str, ...]] = []
            for _page in range(5):
                visible = tuple(video_scene3_flow.unified_field_suggestions(page_state, group, key))
                assert len(visible) == 5
                pages.append(visible)
                page_state = video_scene3_flow.rotate_unified_field_suggestions(
                    page_state,
                    group,
                    key,
                )
            assert len(set().union(*(set(page) for page in pages))) == 25
            assert tuple(video_scene3_flow.unified_field_suggestions(page_state, group, key)) == pages[0]


def test_environment_catalog_covers_all_required_location_families() -> None:
    state = video_scene3_flow.default_state(
        product_type="storyboard_prompt",
        subject="Một câu chuyện nhiều cảnh",
        aspect_ratio="9:16",
    )
    catalog = video_scene3_flow.unified_field_suggestion_catalog(
        state,
        "preservation_requirements",
        "environment",
    )
    joined = " ".join(catalog).lower()

    assert len(catalog) >= 25
    for expected in ("thành thị", "thiên nhiên", "đời sống", "bảo tàng", "văn phòng"):
        assert expected in joined


def test_requirement_values_are_inline_and_legacy_review_returns_to_hub() -> None:
    payload_source = _function_source(BOT_SOURCE, "video_ai_real_pilot_requirements_payload")
    screen = _function_source(BOT_SOURCE, "video_ai_real_pilot_screen_payload")
    callback = _function_source(BOT_SOURCE, "handle_video_uiflow3_callback")

    assert "preservation_requirements" in payload_source
    inline_branch = payload_source[
        payload_source.index("if inline_summary:"):
        payload_source.index("else:", payload_source.index("if inline_summary:"))
    ]
    assert "✨ Tự động gợi ý" in inline_branch
    assert "👁 Xem mục đã chọn" not in inline_branch
    assert 'selection_copy = "Đã chọn:\\n" + selected_copy' in payload_source
    assert 'view == "pilot_requirement_review"' in screen
    assert "video_ai_real_uses_inline_requirements(state)" in screen
    stale_view = callback[
        callback.index('elif action == "pilot_requirement_view":'):
        callback.index('elif action == "pilot_requirement_back":')
    ]
    assert "video_ai_real_uses_inline_requirements(state)" in stale_view
    assert 'else "pilot_requirement_review"' in stale_view
    assert 'video_uiflow3_open_view(state, "pilot_requirements")' in stale_view


def test_storyboard_middle_uses_pilot_creative_then_requirements_before_scene_plan() -> None:
    entity_finish = _function_source(BOT_SOURCE, "video_storyboard_finish_entity_bridge")
    creative_open = _function_source(BOT_SOURCE, "video_storyboard_open_creative_details")
    middle_finish = _function_source(BOT_SOURCE, "video_storyboard_finish_creative_details")
    callback = _function_source(BOT_SOURCE, "handle_video_uiflow3_callback")
    profile_callback = _function_source(BOT_SOURCE, "handle_video_profile_studio_callback")

    assert '"pilot_creative_controls"' in creative_open
    assert '"pilot_requirements"' in creative_open
    assert "video_profile_scene1_render" not in creative_open
    assert "video_storyboard_open_creative_details" in entity_finish
    assert 'action == "pilot_creative_auto"' in callback
    creative_auto = callback[
        callback.index('elif action == "pilot_creative_auto":'):
        callback.index('elif action == "pilot_creative_back":')
    ]
    assert "video_storyboard_entity_bridge_marker(state)" in creative_auto
    assert 'raise ValueError("video_uiflow3_action_not_relevant")' in creative_auto
    assert 'action == "pilot_requirement_auto"' in callback
    assert 'marker["phase"] = "requirements"' in callback
    assert "video_storyboard_finish_creative_details" in callback
    assert "video_storyboard_entity_bridge_marker(state)" in callback
    quick_branch = callback[
        callback.index('elif action == "quick_build":'):
        callback.index('elif action == "bible_done":')
    ]
    assert "video_storyboard_quick_middle" not in quick_branch
    assert "video_storyboard_finish_entity_bridge" in quick_branch
    assert "video_storyboard_finish_creative_details" not in quick_branch
    assert 'move(board, "scene_review"' in middle_finish
    assert "preservation_requirements" in middle_finish
    assert "storyboard_creative_setup" not in profile_callback


def test_storyboard_protected_tail_remains_byte_identical_to_origin_main() -> None:
    result = subprocess.run(
        ["git", "show", "origin/main:bot.py"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    base = result.stdout

    for name in ("storyboard2_addon_keyboard", "storyboard2_scene3_handoff"):
        assert hashlib.sha256(_git_canonical_bytes(_function_bytes(BOT_BYTES, name))).digest() == hashlib.sha256(
            _git_canonical_bytes(_function_bytes(base, name))
        ).digest()

    marker = b'    if action in {"transition_natural", "transition_done"}:'
    current_callback = _function_bytes(BOT_BYTES, "_handle_storyboard2_callback_impl")
    base_callback = _function_bytes(base, "_handle_storyboard2_callback_impl")
    assert hashlib.sha256(_git_canonical_bytes(current_callback[current_callback.index(marker) :])).digest() == hashlib.sha256(
        _git_canonical_bytes(base_callback[base_callback.index(marker) :])
    ).digest()


def test_storyboard_existing_prompt_generators_remain_byte_identical_to_origin_main() -> None:
    result = subprocess.run(
        ["git", "show", "origin/main:services/video_storyboard2.py"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")

    for name in ("image_prompt", "compile_video_prompts"):
        assert hashlib.sha256(
            _git_canonical_bytes(_function_bytes(STORYBOARD_BYTES, name))
        ).digest() == hashlib.sha256(
            _git_canonical_bytes(_function_bytes(result.stdout, name))
        ).digest()
