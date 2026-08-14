from __future__ import annotations

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


def test_all_storyboard_content_lanes_enter_required_reference_before_entity() -> None:
    callback = _function_source(BOT_SOURCE, "_handle_storyboard2_callback_impl")
    pending_text = _function_source(BOT_SOURCE, "handle_storyboard2_pending_text")
    idea_return = _function_source(BOT_SOURCE, "video_idea_render_exact_parent")

    assert "video_storyboard_prepare_reference_bridge" in callback
    assert callback.count("video_storyboard_prepare_reference_bridge") >= 2
    assert "video_storyboard_prepare_reference_bridge" in pending_text
    assert "video_storyboard_prepare_entity_bridge" not in pending_text
    assert "video_uiflow3_screen_payload" in pending_text
    storyboard_idea = idea_return[
        idea_return.index('if product_id == "storyboard_prompt":'):
        idea_return.index('if product_id == video_selfshot2.PRODUCT_ID:')
    ]
    assert "video_storyboard_prepare_reference_bridge" in storyboard_idea
    assert "video_storyboard_prepare_entity_bridge" not in storyboard_idea
    assert 'move(board, "scene_review"' not in idea_return[idea_return.index('if product_id == "storyboard_prompt":') : idea_return.index('if product_id == video_selfshot2.PRODUCT_ID:')]


def test_storyboard_reference_gate_uses_existing_source_screen_and_exact_back_stack() -> None:
    reference_bridge = _function_source(BOT_SOURCE, "video_storyboard_prepare_reference_bridge")
    pilot_screen = _function_source(BOT_SOURCE, "video_ai_real_pilot_screen_payload")
    uiflow_callback = _function_source(BOT_SOURCE, "handle_video_uiflow3_callback")
    storyboard_callback = _function_source(BOT_SOURCE, "_handle_storyboard2_callback_impl")

    assert 'marker["phase"] = "reference"' in reference_bridge
    assert 'state["source"]["kind"] = "raw_images"' in reference_bridge
    assert 'state["source"]["required"] = True' in reference_bridge
    assert '"current_step": "source"' in reference_bridge
    assert 'f"vstory|reference_back|{bridge_key}"' in reference_bridge
    assert 'storyboard_bridge.get("phase") or ""' in pilot_screen
    assert 'storyboard_bridge.get("back_callback")' in pilot_screen

    source_done = uiflow_callback[
        uiflow_callback.index('elif action == "source_done":'):
        uiflow_callback.index('elif action == "ratio" and values:')
    ]
    assert 'str(storyboard_marker.get("phase") or "") == "reference"' in source_done
    assert 'storyboard_marker["phase"] = "entity"' in source_done
    assert '"production_bible"' in source_done
    assert "video_storyboard_store_reference_source" in source_done

    assert 'if action == "reference_back":' in storyboard_callback
    entity_back = storyboard_callback[
        storyboard_callback.index('if action == "entity_back":'):
        storyboard_callback.index('if action == "creative_screen":')
    ]
    assert 'marker["phase"] = "reference"' in entity_back
    assert '"current_step": "source"' in entity_back


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

    board = video_storyboard2.ensure_session(_board(), "storyboard-session")
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


def test_storyboard_reference_bridge_requires_and_persists_source_image() -> None:
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
        "storyboard2_state": lambda _context: video_storyboard2.normalize_state(_context.user_data["board"]),
        "video_uiflow3_state": ui_state,
        "save_video_uiflow3_state": save_ui,
        "video_uiflow3_clear_transient": lambda state, keep_return=False: state,
        "safe_int": lambda value, default=0: int(value or default),
    }
    for name in (
        "video_storyboard_entity_bridge_marker",
        "video_storyboard_entity_bridge_key",
        "video_storyboard_prepare_entity_bridge",
        "video_storyboard_store_reference_source",
        "video_storyboard_prepare_reference_bridge",
    ):
        exec("from __future__ import annotations\n" + _function_source(BOT_SOURCE, name), namespace)

    board = video_storyboard2.ensure_session(_board(), "storyboard-reference-session")
    state = namespace["video_storyboard_prepare_reference_bridge"](
        SimpleNamespace(chat_id=99),
        42,
        context,
        board,
        return_screen="await_content",
    )
    marker = namespace["video_storyboard_entity_bridge_marker"](state)
    assert state["navigation"]["current_step"] == "source"
    assert state["source"]["kind"] == "raw_images"
    assert state["source"]["required"] is True
    assert state["source"]["complete"] is False
    assert marker["phase"] == "reference"
    assert marker["back_callback"].startswith("vstory|reference_back|")

    state = video_uiflow3.add_source_asset(
        state,
        asset_type="image",
        telegram_file_id="storyboard-reference-image",
        fingerprint="telegram:storyboard-reference-image",
    )
    stored = namespace["video_storyboard_store_reference_source"](
        context,
        state,
        complete=True,
    )
    assert stored["reference_gate_complete"] is True
    assert stored["reference_source_assets"][0]["telegram_file_id"] == "storyboard-reference-image"


def test_storyboard_entity_and_creative_callbacks_have_exact_parent_returns() -> None:
    marker = _function_source(BOT_SOURCE, "video_storyboard_entity_bridge_marker")
    pilot_owner = _function_source(BOT_SOURCE, "video_uiflow3_uses_entity_pilot")
    entity_finish = _function_source(BOT_SOURCE, "video_storyboard_finish_entity_bridge")
    creative_finish = _function_source(BOT_SOURCE, "video_storyboard_finish_creative_details")
    uiflow_callback = _function_source(BOT_SOURCE, "handle_video_uiflow3_callback")
    storyboard_callback = _function_source(BOT_SOURCE, "_handle_storyboard2_callback_impl")
    scene_keyboard = _function_source(BOT_SOURCE, "storyboard2_scene_review_keyboard")

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
        "✨ Tự động gợi ý",
        "✅ Hoàn tất thiết lập nhân vật",
    }.issubset(set(labels))
    assert "⚡ Tạo nhanh" not in labels
    assert labels[-2:] == ["⬅️ Quay lại", "🎬 Menu Video"]


def test_standard_requirements_keep_environment_once_and_offer_automatic_suggestions() -> None:
    category_start = BOT_SOURCE.index("VIDEO_AI_REAL_PILOT_REQUIREMENT_CATEGORIES =")
    category_end = BOT_SOURCE.index("\ndef video_ai_real_pilot_scene3_field_state", category_start)
    category_contract = BOT_SOURCE[category_start:category_end]
    assert "PUBLIC_REQUIREMENT_CATEGORIES" in category_contract
    assert 'item[0] != "environment"' not in category_contract

    class _SceneFlow:
        CREATIVE_CONTROLS = ()

    categories = (
        ("identity", "🔒 Nhân vật/nhận diện"),
        ("environment", "🏞 Bối cảnh/kiến trúc"),
    )
    namespace = {
        "VIDEO_AI_REAL_PILOT_REQUIREMENT_CATEGORIES": categories,
        "video_scene3_flow": _SceneFlow,
        "video_ai_real_pilot_scene3_field_state": lambda state: state,
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
        {"preservation_requirements": {}}
    )
    labels = [label for row in rows for label, _callback in row]
    callbacks = [callback for row in rows for _label, callback in row]
    assert "➕ Bối cảnh/kiến trúc" in labels
    assert "✨ Tự động gợi ý" in labels
    assert "👁 Xem mục đã chọn" in labels
    assert "vid3|pilot_requirement_auto" in callbacks
    assert "vid3|pilot_requirement_view" in callbacks
    assert "không hỏi lại ở màn Nhân vật" in text


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


def test_requirement_review_shows_selected_values_and_has_one_parent_back() -> None:
    payload_source = _function_source(BOT_SOURCE, "video_ai_real_pilot_requirement_review_payload")
    screen = _function_source(BOT_SOURCE, "video_ai_real_pilot_screen_payload")
    callback = _function_source(BOT_SOURCE, "handle_video_uiflow3_callback")

    assert "preservation_requirements" in payload_source
    assert '"⬅️ Về Yêu cầu"' in payload_source
    assert '"vid3|pilot_requirement_review_back"' in payload_source
    assert '"menu|main_video"' not in payload_source
    assert 'view == "pilot_requirement_review"' in screen
    assert 'action == "pilot_requirement_view"' in callback
    assert 'action == "pilot_requirement_review_back"' in callback


def test_storyboard_middle_uses_pilot_creative_then_requirements_before_scene_plan() -> None:
    entity_finish = _function_source(BOT_SOURCE, "video_storyboard_finish_entity_bridge")
    creative_open = _function_source(BOT_SOURCE, "video_storyboard_open_creative_details")
    middle_finish = _function_source(BOT_SOURCE, "video_storyboard_finish_creative_details")
    callback = _function_source(BOT_SOURCE, "handle_video_uiflow3_callback")
    profile_callback = _function_source(BOT_SOURCE, "handle_video_profile_studio_callback")

    assert 'video_uiflow3_open_view(bridge_state, "pilot_creative_controls")' in creative_open
    assert "video_profile_scene1_render" not in creative_open
    assert "video_storyboard_open_creative_details" in entity_finish
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
