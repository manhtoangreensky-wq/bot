from __future__ import annotations

import ast
import asyncio
import copy
import importlib
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
SERVICE_PATH = ROOT / "services" / "local_video_studio_preview.py"
INDEX_PATH = ROOT / "skills" / "video" / "local-video-codex-index" / "capability_index.json"
BOT_PATH = ROOT / "bot.py"

CALLBACK_PREFIX = "lvs27a"
STATE_KEY = "local_video_studio27a_preview"
LOCAL_RECORD_IDS = (
    "openmontage_local",
    "editing_grammar",
    "framing_composition",
    "pacing_storytelling",
    "camera_movement",
    "rights_requirements",
    "transition_motion_pack",
    "sound_design_pack",
    "viral_effects",
    "local_free_capabilities",
    "video_qa",
)
PAID_RECORD_IDS = ("mosaic_motion", "higgsfield", "suno")
RECORD_IDS = LOCAL_RECORD_IDS + PAID_RECORD_IDS
ALLOWED_VERBS = ("open", "pick", "catalog", "pack", "qa", "back", "home", "close")
SESSION_FIELDS = (
    "version",
    "screen",
    "history",
    "mode",
    "selections",
    "catalog_page",
    "pack_id",
    "pack_page",
)
CREATE_SCREENS = (
    "create_goal",
    "create_format",
    "create_style",
    "create_audio",
    "create_review",
    "create_qa",
    "complete",
)
EDIT_SCREENS = (
    "edit_goal",
    "edit_source",
    "edit_delivery",
    "edit_review",
    "edit_qa",
    "complete",
)
QA_IDS = (
    "file_exists",
    "file_size_minimum",
    "container_valid",
    "video_stream_exists",
    "duration_positive",
    "dimensions_valid",
    "frame_rate_valid",
    "audio_stream_when_promised",
    "audio_loudness_valid",
    "true_peak_valid",
    "black_frame_detection",
    "frozen_frame_detection",
    "duplicated_scene_warning",
    "subtitle_safe_area",
    "subtitle_readability",
    "aspect_ratio",
    "delivery_filename",
    "output_size",
    "render_promise_verification",
)
CREATE_CALLBACKS = (
    ("lvs27a|open|create", "create_goal"),
    ("lvs27a|pick|create_goal|ad", "create_format"),
    ("lvs27a|pick|create_format|9x16", "create_style"),
    ("lvs27a|pick|create_style|cinematic", "create_audio"),
    ("lvs27a|pick|create_audio|owner_licensed", "create_review"),
    ("lvs27a|qa|create", "create_qa"),
    ("lvs27a|pick|create_qa|complete", "complete"),
)
EDIT_CALLBACKS = (
    ("lvs27a|open|edit", "edit_goal"),
    ("lvs27a|pick|edit_goal|cut_pacing", "edit_source"),
    ("lvs27a|pick|edit_source|owner_footage", "edit_delivery"),
    ("lvs27a|pick|edit_delivery|9x16", "edit_review"),
    ("lvs27a|qa|edit", "edit_qa"),
    ("lvs27a|pick|edit_qa|complete", "complete"),
)
CROSS_PRODUCT_PREFIXES = (
    "menu|",
    "vproduct|",
    "videoedit|",
    "videodub|",
    "framevideo|",
    "motion|",
    "higgsfield|",
    "suno|",
)


def _service():
    assert SERVICE_PATH.is_file(), "27A pure preview service is missing"
    return importlib.import_module("services.local_video_studio_preview")


def _index() -> dict[str, object]:
    return json.loads(INDEX_PATH.read_text(encoding="utf-8"))


def _apply(service, session: dict[str, object], callback: str) -> dict[str, object]:
    result = service.apply_callback(session, callback)
    assert tuple(result) == ("session", "closed", "feedback")
    assert result["closed"] is False
    assert isinstance(result["feedback"], str) and result["feedback"].strip()
    return result["session"]


def _assert_view(service, view: dict[str, object]) -> set[str]:
    assert tuple(view) == ("screen", "text", "rows")
    assert isinstance(view["screen"], str) and view["screen"]
    assert isinstance(view["text"], str) and view["text"].strip()
    assert len(view["text"]) <= 4096
    callbacks: set[str] = set()
    for row in view["rows"]:
        assert 1 <= len(row) <= 2
        for label, callback in row:
            assert isinstance(label, str) and label.strip()
            assert isinstance(callback, str) and callback.startswith(f"{CALLBACK_PREFIX}|")
            assert len(callback.encode("utf-8")) <= 64
            assert not callback.startswith(CROSS_PRODUCT_PREFIXES)
            service.parse_callback(callback)
            callbacks.add(callback)
    return callbacks


def test_service_contract_constants_and_exact_state_schema() -> None:
    service = _service()
    assert service.CALLBACK_PREFIX == CALLBACK_PREFIX
    assert service.STATE_KEY == STATE_KEY
    assert service.PREVIEW_VERSION == "27A"
    assert tuple(service.LOCAL_RECORD_IDS) == LOCAL_RECORD_IDS
    assert tuple(service.PAID_RECORD_IDS) == PAID_RECORD_IDS
    assert tuple(service.ALLOWED_VERBS) == ALLOWED_VERBS
    assert tuple(service.FLOW_STEPS["create"])[0][0] == CREATE_SCREENS[0]
    assert tuple(screen for screen, _ in service.FLOW_STEPS["create"]) == CREATE_SCREENS
    assert tuple(screen for screen, _ in service.FLOW_STEPS["edit"]) == EDIT_SCREENS
    assert service.FLOW_BACK_TARGETS["create"] == {
        "create_goal": "home",
        "create_format": "create_goal",
        "create_style": "create_format",
        "create_audio": "create_style",
        "create_review": "create_audio",
        "create_qa": "create_review",
        "complete": "create_qa",
    }
    assert service.FLOW_BACK_TARGETS["edit"] == {
        "edit_goal": "home",
        "edit_source": "edit_goal",
        "edit_delivery": "edit_source",
        "edit_review": "edit_delivery",
        "edit_qa": "edit_review",
        "complete": "edit_qa",
    }
    assert service.SCREEN_BACK_TARGETS == {
        "catalog": "home",
        "pack": "catalog",
        "safety": "home",
        "qa": "safety",
    }
    session = service.new_session()
    assert tuple(session) == SESSION_FIELDS
    assert session == {
        "version": "27A",
        "screen": "home",
        "history": [],
        "mode": "",
        "selections": {},
        "catalog_page": 0,
        "pack_id": "",
        "pack_page": 0,
    }


def test_index_validation_covers_all_local_paid_and_qa_ids_without_readiness_inference() -> None:
    service = _service()
    payload = service.validate_capability_index(_index())
    records = payload["capabilities"]
    assert tuple(record["capability_id"] for record in records) == RECORD_IDS
    coverage = service.capability_coverage(payload)
    assert tuple(coverage) == ("local", "paid", "all", "qa")
    assert len(coverage["local"]) == 248
    assert len(coverage["paid"]) == 3
    assert len(coverage["all"]) == 251
    assert len(set(coverage["all"])) == 251
    assert tuple(item.removeprefix("video_qa.") for item in coverage["qa"]) == QA_IDS
    for record in records:
        assert record["production_readiness"] is False
        assert record["planning_only"] is True
        assert record["runtime_registered"] is False
        assert record["provider_executable"] is False
        assert record["public_ui"] is False
        assert record["highest_readiness"] not in {"PRODUCTION_READY", "PUBLIC"}


def test_index_validation_fails_closed_for_public_or_provider_executable_record() -> None:
    service = _service()
    for field in ("public_ui", "provider_executable", "production_readiness"):
        payload = copy.deepcopy(_index())
        payload["capabilities"][0][field] = True
        with pytest.raises(service.PreviewDataError):
            service.validate_capability_index(payload)


def test_index_validation_rejects_every_malformed_field_used_by_the_preview() -> None:
    service = _service()
    malformed_payloads: list[dict[str, object]] = []

    for field, unsafe in (
        ("planning_only", False),
        ("runtime_registered", True),
        ("provider_executable", True),
        ("public_ui", True),
    ):
        payload = copy.deepcopy(_index())
        payload[field] = unsafe
        malformed_payloads.append(payload)

    missing_counter = copy.deepcopy(_index())
    missing_counter["execution_counters"].pop("provider_calls")
    malformed_payloads.append(missing_counter)

    boolean_counter = copy.deepcopy(_index())
    boolean_counter["execution_counters"]["provider_calls"] = False
    malformed_payloads.append(boolean_counter)

    missing_name = copy.deepcopy(_index())
    missing_name["capabilities"][0].pop("display_name_vi")
    malformed_payloads.append(missing_name)

    for unsafe_readiness in (None, [], "UNKNOWN"):
        payload = copy.deepcopy(_index())
        payload["capabilities"][0]["highest_readiness"] = unsafe_readiness
        malformed_payloads.append(payload)

    wrong_qa = copy.deepcopy(_index())
    qa_record = next(
        record for record in wrong_qa["capabilities"] if record["capability_id"] == "video_qa"
    )
    qa_record["capability_ids"][0] = "video_qa.not_an_approved_check"
    malformed_payloads.append(wrong_qa)

    for payload in malformed_payloads:
        with pytest.raises(service.PreviewDataError):
            service.validate_capability_index(payload)


@pytest.mark.parametrize("callbacks", (CREATE_CALLBACKS, EDIT_CALLBACKS))
def test_each_forward_step_and_back_returns_to_the_exact_parent(callbacks) -> None:
    service = _service()
    session = service.new_session()
    previous = "home"
    for callback, expected in callbacks:
        session = _apply(service, session, callback)
        assert session["screen"] == expected
        assert session["history"][-1] == previous
        back = _apply(service, session, "lvs27a|back")
        assert back["screen"] == previous
        session = _apply(service, back, callback)
        previous = expected


def test_required_steps_cannot_be_skipped_and_home_close_are_isolated() -> None:
    service = _service()
    session = service.new_session()
    with pytest.raises(service.PreviewActionError):
        service.apply_callback(session, "lvs27a|pick|create_format|9x16")
    session = _apply(service, session, "lvs27a|open|create")
    with pytest.raises(service.PreviewActionError):
        service.apply_callback(session, "lvs27a|qa|create")
    home = _apply(service, session, "lvs27a|home")
    assert home == service.new_session()
    closed = service.apply_callback(home, "lvs27a|close")
    assert tuple(closed) == ("session", "closed", "feedback")
    assert closed["closed"] is True
    assert closed["session"] == service.new_session()


def test_invalid_callbacks_fail_closed_without_mutating_input() -> None:
    service = _service()
    with pytest.raises(service.PreviewActionError):
        service.callback_data("open", "bad|target")
    with pytest.raises(service.PreviewActionError):
        service.callback_data("pack", "x" * 60, 0)
    original = service.new_session()
    snapshot = copy.deepcopy(original)
    for callback in (
        "menu|main",
        "lvs27a",
        "lvs27a|unknown",
        "lvs27a|catalog|not_a_page",
        "lvs27a|pack|mosaic_motion|0",
        "lvs27a|pick|create_goal|not_allowed",
    ):
        with pytest.raises(service.PreviewActionError):
            service.apply_callback(original, callback)
        assert original == snapshot


@pytest.mark.parametrize(
    "screen,mode",
    (
        ("create_goal", "edit"),
        ("create_review", ""),
        ("edit_source", "create"),
        ("edit_qa", "catalog"),
        ("catalog", "safety"),
        ("pack", "create"),
        ("safety", "catalog"),
        ("qa", "edit"),
        ("complete", "catalog"),
        ("home", "create"),
    ),
)
def test_stale_screen_mode_pairs_fail_closed_to_a_new_home_session(screen, mode) -> None:
    service = _service()
    stale = service.new_session()
    stale.update({"screen": screen, "mode": mode})
    if screen == "pack":
        stale["pack_id"] = "editing_grammar"
    assert service.normalize_session(stale) == service.new_session()


def test_stale_or_cross_flow_history_fails_closed_instead_of_routing_to_wrong_parent() -> None:
    service = _service()
    create = _apply(service, service.new_session(), "lvs27a|open|create")
    create = _apply(service, create, "lvs27a|pick|create_goal|ad")
    assert create["history"] == ["home", "create_goal"]
    for history in ([], ["home", "safety"], ["home", "edit_goal"]):
        stale = copy.deepcopy(create)
        stale["history"] = history
        assert service.normalize_session(stale) == service.new_session()

    pack = _apply(service, service.new_session(), "lvs27a|open|catalog")
    pack = _apply(service, pack, "lvs27a|pack|editing_grammar|0")
    assert pack["history"] == ["home", "catalog"]
    pack["history"] = ["home", "safety"]
    assert service.normalize_session(pack) == service.new_session()


def test_stale_flow_sessions_require_a_valid_selection_prefix_and_cannot_skip_steps() -> None:
    service = _service()
    valid = service.new_session()
    for callback, _ in CREATE_CALLBACKS[:-1]:
        valid = _apply(service, valid, callback)
    assert valid["screen"] == "create_qa"
    assert set(valid["selections"]) == {"goal", "format", "style", "audio"}

    missing = copy.deepcopy(valid)
    missing["selections"] = {}
    assert service.normalize_session(missing) == service.new_session()

    invalid_value = copy.deepcopy(valid)
    invalid_value["selections"]["goal"] = "not_a_goal"
    assert service.normalize_session(invalid_value) == service.new_session()

    early = _apply(service, service.new_session(), "lvs27a|open|create")
    early = _apply(service, early, "lvs27a|pick|create_goal|ad")
    early["selections"]["style"] = "cinematic"
    assert service.normalize_session(early) == service.new_session()

    returned = _apply(service, valid, "lvs27a|back")
    returned = _apply(service, returned, "lvs27a|back")
    assert returned["screen"] == "create_audio"
    assert service.normalize_session(returned) == returned
    for expected_screen, expected_fields in (
        ("create_style", {"goal", "format", "style"}),
        ("create_format", {"goal", "format"}),
        ("create_goal", {"goal"}),
        ("home", set()),
    ):
        returned = _apply(service, returned, "lvs27a|back")
        assert returned["screen"] == expected_screen
        assert set(returned["selections"]) == expected_fields
        assert service.normalize_session(returned) == returned

    edit = service.new_session()
    for callback, _ in EDIT_CALLBACKS[:-1]:
        edit = _apply(service, edit, callback)
    for expected_screen, expected_fields in (
        ("edit_review", {"goal", "source", "delivery"}),
        ("edit_delivery", {"goal", "source", "delivery"}),
        ("edit_source", {"goal", "source"}),
        ("edit_goal", {"goal"}),
        ("home", set()),
    ):
        edit = _apply(service, edit, "lvs27a|back")
        assert edit["screen"] == expected_screen
        assert set(edit["selections"]) == expected_fields
        assert service.normalize_session(edit) == edit


def test_all_flow_views_render_with_single_namespace_and_truthful_completion() -> None:
    service = _service()
    payload = service.load_capability_index()
    for callbacks in (CREATE_CALLBACKS, EDIT_CALLBACKS):
        session = service.new_session()
        _assert_view(service, service.render_view(session, payload))
        for callback, _ in callbacks:
            session = _apply(service, session, callback)
            view = service.render_view(session, payload)
            _assert_view(service, view)
        text = view["text"]
        assert "PREVIEW_COMPLETE" in text
        assert "không tạo MP4" in text
        assert "Provider calls: 0" in text
        assert "Xu: 0" in text


def test_catalog_pages_render_all_248_local_ids_and_back_to_catalog() -> None:
    service = _service()
    payload = service.load_capability_index()
    records = {record["capability_id"]: record for record in payload["capabilities"]}
    catalog = _apply(service, service.new_session(), "lvs27a|open|catalog")
    assert catalog["screen"] == "catalog"
    clamped = _apply(service, catalog, "lvs27a|catalog|-1")
    assert clamped["catalog_page"] == 0
    catalog_view = service.render_view(catalog, payload)
    pack_rows = [
        row
        for row in catalog_view["rows"]
        if any(callback.startswith("lvs27a|pack|") for _, callback in row)
    ]
    assert pack_rows and all(len(row) == 1 for row in pack_rows)
    assert _apply(service, catalog, "lvs27a|back")["screen"] == "home"
    rendered_ids: set[str] = set()
    for record_id in LOCAL_RECORD_IDS:
        pack = _apply(service, catalog, f"lvs27a|pack|{record_id}|0")
        assert pack["screen"] == "pack"
        assert pack["pack_id"] == record_id
        expected_ids = tuple(records[record_id]["capability_ids"])
        page_count = max(1, (len(expected_ids) + service.PACK_PAGE_SIZE - 1) // service.PACK_PAGE_SIZE)
        for page in range(page_count):
            if page:
                pack = _apply(service, pack, f"lvs27a|pack|{record_id}|{page}")
            view = service.render_view(pack, payload)
            _assert_view(service, view)
            rendered_ids.update(capability_id for capability_id in expected_ids if capability_id in view["text"])
        back = _apply(service, pack, "lvs27a|back")
        assert back["screen"] == "catalog"
    coverage = service.capability_coverage(payload)
    assert rendered_ids == set(coverage["local"])


def test_out_of_range_pages_are_clamped_in_state_before_render() -> None:
    service = _service()
    payload = service.load_capability_index()
    records = {record["capability_id"]: record for record in payload["capabilities"]}

    catalog = _apply(service, service.new_session(), "lvs27a|open|catalog")
    catalog = _apply(service, catalog, "lvs27a|catalog|999")
    catalog_total = max(1, (len(LOCAL_RECORD_IDS) + service.CATALOG_PAGE_SIZE - 1) // service.CATALOG_PAGE_SIZE)
    assert catalog["catalog_page"] == catalog_total - 1

    pack = _apply(service, service.new_session(), "lvs27a|open|catalog")
    pack_id = LOCAL_RECORD_IDS[0]
    pack = _apply(service, pack, f"lvs27a|pack|{pack_id}|999")
    pack_total = max(
        1,
        (len(records[pack_id]["capability_ids"]) + service.PACK_PAGE_SIZE - 1) // service.PACK_PAGE_SIZE,
    )
    assert pack["pack_page"] == pack_total - 1

    safety = _apply(service, service.new_session(), "lvs27a|open|safety")
    qa = _apply(service, safety, "lvs27a|qa|999")
    qa_total = max(
        1,
        (len(records["video_qa"]["capability_ids"]) + service.PACK_PAGE_SIZE - 1) // service.PACK_PAGE_SIZE,
    )
    assert qa["pack_page"] == qa_total - 1


def test_safety_and_qa_pages_render_paid_locks_and_all_19_qa_ids() -> None:
    service = _service()
    payload = service.load_capability_index()
    records = {record["capability_id"]: record for record in payload["capabilities"]}
    safety = _apply(service, service.new_session(), "lvs27a|open|safety")
    safety_view = service.render_view(safety, payload)
    _assert_view(service, safety_view)
    assert _apply(service, safety, "lvs27a|back")["screen"] == "home"
    for counter, value in payload["execution_counters"].items():
        assert f"<code>{counter}</code>" in safety_view["text"]
        assert value == 0
    for record_id in PAID_RECORD_IDS:
        record = records[record_id]
        assert record_id in safety_view["text"]
        assert record["capability_ids"][0] in safety_view["text"]
        assert "DISABLED" in safety_view["text"]
        assert record["highest_readiness"] in safety_view["text"]
    qa_ids = tuple(records["video_qa"]["capability_ids"])
    rendered: set[str] = set()
    page_count = max(1, (len(qa_ids) + service.PACK_PAGE_SIZE - 1) // service.PACK_PAGE_SIZE)
    qa_session = safety
    for page in range(page_count):
        qa_session = _apply(service, qa_session, f"lvs27a|qa|{page}")
        view = service.render_view(qa_session, payload)
        _assert_view(service, view)
        assert records["video_qa"]["highest_readiness"] in view["text"]
        rendered.update(capability_id for capability_id in qa_ids if capability_id in view["text"])
    assert rendered == set(qa_ids)
    assert _apply(service, qa_session, "lvs27a|back")["screen"] == "safety"


def test_service_is_stdlib_read_only_and_has_no_cross_product_or_paid_route() -> None:
    service = _service()
    source = SERVICE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    assert roots <= sys.stdlib_module_names
    assert roots.isdisjoint({"bot", "services", "providers", "workers", "billing", "telegram"})
    for token in (
        "subprocess",
        "requests",
        "httpx",
        "urlopen",
        "write_text",
        "write_bytes",
        "os.system",
        "Popen",
        "create_task",
        "enqueue",
        "charge_wallet",
    ):
        assert token not in source
    for prefix in CROSS_PRODUCT_PREFIXES:
        assert prefix not in source
    assert service.load_capability_index()["execution_counters"] == {
        "provider_calls": 0,
        "paid_provider_calls": 0,
        "paid_generations": 0,
        "motion_calls": 0,
        "higgsfield_generation_calls": 0,
        "wallet_mutations": 0,
        "telegram_deliveries": 0,
        "production_deploys": 0,
        "vps_updates": 0,
    }


def test_failure_view_is_local_truthful_and_offers_only_close() -> None:
    service = _service()
    view = service.render_failure_view()
    callbacks = _assert_view(service, view)
    assert view["screen"] == "error"
    assert "dừng an toàn" in view["text"]
    assert "không có tác vụ nào được chạy" in view["text"]
    assert callbacks == {"lvs27a|close"}


def test_bot_adapter_is_hidden_admin_only_and_registration_is_exact() -> None:
    _service()
    source = BOT_PATH.read_text(encoding="utf-8")
    assert "from services import local_video_studio_preview" in source
    start_marker = "# --- LOCAL VIDEO STUDIO 27A PREVIEW ---"
    end_marker = "# --- END LOCAL VIDEO STUDIO 27A PREVIEW ---"
    assert start_marker in source and end_marker in source
    adapter = source.split(start_marker, 1)[1].split(end_marker, 1)[0]
    assert "def local_video_studio_preview_keyboard" in adapter
    assert "async def cmd_local_video_studio_preview" in adapter
    assert "async def handle_local_video_studio_preview_callback" in adapter
    assert adapter.count("is_admin_user(") >= 2
    assert "context.user_data" in adapter
    assert "STATE_KEY" in adapter
    assert "render_failure_view" in adapter
    for forbidden in (
        "create_order(",
        "charge",
        "wallet",
        "provider_router",
        "remote_worker",
        "local_worker",
        "render_product_video(",
        "render_video(",
        "enqueue_video",
        "send_video(",
        "menu|",
        "vproduct|",
        "videodub|",
        "videoedit|",
    ):
        assert forbidden not in adapter
    assert re.search(
        r'CommandHandler\(\s*"local_video_studio_preview"\s*,\s*admin_internal_command\(cmd_local_video_studio_preview\)\s*\)',
        source,
    )
    assert re.search(
        r'CallbackQueryHandler\(\s*handle_local_video_studio_preview_callback\s*,\s*pattern=r"\^lvs27a\\\|"\s*\)',
        source,
    )
    assert "local_video_studio_preview" not in source_between(source, "def admin_center_text", "async def cmd_admin_center")


def test_bot_adapter_executes_authorized_command_callback_and_back_without_cross_state(monkeypatch) -> None:
    service = _service()
    source = BOT_PATH.read_text(encoding="utf-8")
    adapter = source.split("# --- LOCAL VIDEO STUDIO 27A PREVIEW ---", 1)[1].split(
        "# --- END LOCAL VIDEO STUDIO 27A PREVIEW ---", 1
    )[0]

    class FakeButton:
        def __init__(self, text, callback_data):
            self.text = text
            self.callback_data = callback_data

    class FakeMarkup:
        def __init__(self, rows):
            self.inline_keyboard = rows

    class FakeMessage:
        def __init__(self, *, fail_reply=False):
            self.fail_reply = fail_reply
            self.replies = []
            self.events = []

        async def reply_text(self, text, **kwargs):
            self.events.append("reply")
            if self.fail_reply:
                raise RuntimeError("telegram_reply_failed")
            item = {"text": str(text), **kwargs}
            self.replies.append(item)
            return item

    class FakeQuery:
        def __init__(self, data, *, fail_edit=False):
            self.data = data
            self.fail_edit = fail_edit
            self.answers = []
            self.edits = []
            self.events = []

        async def answer(self, text=None, **kwargs):
            self.events.append("answer")
            self.answers.append({"text": text, **kwargs})

        async def edit_message_text(self, text, **kwargs):
            self.events.append("edit")
            if self.fail_edit:
                raise RuntimeError("telegram_edit_failed")
            item = {"text": str(text), **kwargs}
            self.edits.append(item)
            return item

    namespace = {
        "InlineKeyboardButton": FakeButton,
        "InlineKeyboardMarkup": FakeMarkup,
        "Update": object,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "is_admin_user": lambda user_id: int(user_id) == 1,
        "local_video_studio_preview": service,
    }
    exec(adapter, namespace)
    command = namespace["cmd_local_video_studio_preview"]
    callback = namespace["handle_local_video_studio_preview_callback"]

    context = SimpleNamespace(user_data={})
    message = FakeMessage()
    command_update = SimpleNamespace(
        effective_user=SimpleNamespace(id=1),
        effective_message=message,
    )
    asyncio.run(command(command_update, context))
    assert context.user_data[STATE_KEY]["screen"] == "home"
    assert len(message.replies) == 1
    assert isinstance(message.replies[0]["reply_markup"], FakeMarkup)

    open_query = FakeQuery("lvs27a|open|create")
    open_update = SimpleNamespace(
        effective_user=SimpleNamespace(id=1),
        callback_query=open_query,
    )
    asyncio.run(callback(open_update, context))
    assert context.user_data[STATE_KEY]["screen"] == "create_goal"
    assert len(open_query.answers) == 1
    assert len(open_query.edits) == 1
    assert open_query.events == ["edit", "answer"]

    back_query = FakeQuery("lvs27a|back")
    back_update = SimpleNamespace(
        effective_user=SimpleNamespace(id=1),
        callback_query=back_query,
    )
    asyncio.run(callback(back_update, context))
    assert context.user_data[STATE_KEY] == service.new_session()
    assert len(back_query.answers) == 1
    assert len(back_query.edits) == 1
    assert back_query.events == ["edit", "answer"]

    broken_session = service.apply_callback(service.new_session(), "lvs27a|open|catalog")["session"]
    broken_context = SimpleNamespace(user_data={STATE_KEY: broken_session})

    def broken_index():
        raise service.PreviewDataError("capability_index_missing")

    monkeypatch.setattr(service, "load_capability_index", broken_index)
    broken_query = FakeQuery("lvs27a|pack|openmontage_local|0")
    broken_update = SimpleNamespace(
        effective_user=SimpleNamespace(id=1),
        callback_query=broken_query,
    )
    asyncio.run(callback(broken_update, broken_context))
    assert STATE_KEY not in broken_context.user_data
    assert broken_query.events == ["edit", "answer"]
    assert broken_query.answers == [
        {"text": "Capability index local không hợp lệ.", "show_alert": True}
    ]
    assert "Không tải được capability index local" in broken_query.edits[0]["text"]

    broken_edit_context = SimpleNamespace(user_data={STATE_KEY: broken_session})
    broken_edit_query = FakeQuery("lvs27a|pack|openmontage_local|0", fail_edit=True)
    broken_edit_update = SimpleNamespace(
        effective_user=SimpleNamespace(id=1),
        callback_query=broken_edit_query,
    )
    with pytest.raises(RuntimeError, match="telegram_edit_failed"):
        asyncio.run(callback(broken_edit_update, broken_edit_context))
    assert broken_edit_context.user_data[STATE_KEY] == broken_session
    assert broken_edit_query.answers == []
    assert broken_edit_query.events == ["edit"]

    stale_command_state = service.new_session()
    broken_command_context = SimpleNamespace(user_data={STATE_KEY: stale_command_state})
    broken_message = FakeMessage()
    broken_command_update = SimpleNamespace(
        effective_user=SimpleNamespace(id=1),
        effective_message=broken_message,
    )
    asyncio.run(command(broken_command_update, broken_command_context))
    assert STATE_KEY not in broken_command_context.user_data
    assert broken_message.events == ["reply"]
    assert "Không tải được capability index local" in broken_message.replies[0]["text"]

    failed_command_context = SimpleNamespace(user_data={STATE_KEY: stale_command_state})
    failed_message = FakeMessage(fail_reply=True)
    failed_command_update = SimpleNamespace(
        effective_user=SimpleNamespace(id=1),
        effective_message=failed_message,
    )
    with pytest.raises(RuntimeError, match="telegram_reply_failed"):
        asyncio.run(command(failed_command_update, failed_command_context))
    assert failed_command_context.user_data[STATE_KEY] == stale_command_state
    assert failed_message.events == ["reply"]

    failure_context = SimpleNamespace(user_data={STATE_KEY: service.new_session()})
    failure_query = FakeQuery("lvs27a|open|edit", fail_edit=True)
    failure_update = SimpleNamespace(
        effective_user=SimpleNamespace(id=1),
        callback_query=failure_query,
    )
    with pytest.raises(RuntimeError, match="telegram_edit_failed"):
        asyncio.run(callback(failure_update, failure_context))
    assert failure_context.user_data[STATE_KEY] == service.new_session()
    assert failure_query.answers == []
    assert failure_query.events == ["edit"]

    before_invalid = copy.deepcopy(context.user_data)
    invalid_query = FakeQuery("lvs27a|unknown")
    invalid_update = SimpleNamespace(
        effective_user=SimpleNamespace(id=1),
        callback_query=invalid_query,
    )
    asyncio.run(callback(invalid_update, context))
    assert context.user_data == before_invalid
    assert invalid_query.answers == [
        {"text": "Thao tác preview không hợp lệ hoặc đã cũ.", "show_alert": True}
    ]
    assert invalid_query.edits == []

    close_query = FakeQuery("lvs27a|close")
    close_update = SimpleNamespace(
        effective_user=SimpleNamespace(id=1),
        callback_query=close_query,
    )
    asyncio.run(callback(close_update, context))
    assert STATE_KEY not in context.user_data
    assert len(close_query.answers) == 1
    assert len(close_query.edits) == 1

    protected_state = copy.deepcopy(context.user_data)
    denied_query = FakeQuery("lvs27a|open|edit")
    denied_update = SimpleNamespace(
        effective_user=SimpleNamespace(id=999),
        callback_query=denied_query,
    )
    asyncio.run(callback(denied_update, context))
    assert context.user_data == protected_state
    assert denied_query.answers == [
        {"text": "Preview này chỉ dành cho owner/admin.", "show_alert": True}
    ]
    assert denied_query.edits == []

    denied_message = FakeMessage()
    denied_command_update = SimpleNamespace(
        effective_user=SimpleNamespace(id=999),
        effective_message=denied_message,
    )
    asyncio.run(command(denied_command_update, SimpleNamespace(user_data={})))
    assert denied_message.replies == [
        {"text": "⛔ Preview này chỉ dành cho owner/admin."}
    ]


def source_between(source: str, start: str, end: str) -> str:
    return source.split(start, 1)[1].split(end, 1)[0]
