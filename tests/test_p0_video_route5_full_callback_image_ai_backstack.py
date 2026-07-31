from __future__ import annotations

import ast
import asyncio
import re
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

import pytest

from services import video_flow6, video_scene3_flow


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    markers = (f"def {name}(", f"async def {name}(")
    positions = [BOT_SOURCE.find(marker) for marker in markers]
    start = min(position for position in positions if position >= 0)
    candidates = [
        position
        for marker in ("\ndef ", "\nasync def ", "\n@")
        if (position := BOT_SOURCE.find(marker, start + 1)) >= 0
    ]
    return BOT_SOURCE[start:min(candidates) if candidates else len(BOT_SOURCE)]


def _literal_assignment(name: str):
    start = BOT_SOURCE.index(f"{name} =")
    end = BOT_SOURCE.find("\n\n", start)
    module = ast.parse(BOT_SOURCE[start:end if end >= 0 else len(BOT_SOURCE)])
    for node in module.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            return ast.literal_eval(node.value)
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
            return ast.literal_eval(node.value)
    raise AssertionError(f"missing assignment: {name}")


class _Button:
    def __init__(self, text: str, *, callback_data: str):
        self.text = text
        self.callback_data = callback_data


class _Markup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard


def _callbacks(markup) -> list[str]:
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if getattr(button, "callback_data", None)
    ]


@lru_cache(maxsize=None)
def _function_code(name: str):
    source = "from __future__ import annotations\n\n" + _function_source(name)
    return compile(ast.parse(source), f"<route5:{name}>", "exec")


def _compile_functions(*names: str, namespace: dict | None = None) -> dict:
    scope = dict(namespace or {})
    for name in names:
        exec(_function_code(name), scope)
    return scope


def test_route5_root_duplicate_callback_is_removed_from_create_image_assets_screen():
    scope = _compile_functions(
        "video_scene3_keyboard",
        "video_scene3_image_assets_keyboard",
        namespace={
            "InlineKeyboardButton": _Button,
            "InlineKeyboardMarkup": _Markup,
            "video_scene3_flow": video_scene3_flow,
        },
    )
    markup = scope["video_scene3_image_assets_keyboard"]({"image_source_mode": "create"})
    callbacks = _callbacks(markup)
    assert callbacks == [
        "vprofile|image_quote",
        "vprofile|image_source|none",
        "vprofile|back",
        "menu|main",
    ]
    assert all(len(row) == 2 for row in markup.inline_keyboard)
    assert len(callbacks) == len(set(callbacks))


def test_route5_image_source_has_four_canonical_choices_and_storyboard_hides_bypass():
    scope = _compile_functions(
        "video_scene3_keyboard",
        "video_scene3_image_source_keyboard",
        namespace={
            "InlineKeyboardButton": _Button,
            "InlineKeyboardMarkup": _Markup,
            "video_scene3_flow": video_scene3_flow,
        },
    )
    regular = _callbacks(scope["video_scene3_image_source_keyboard"]({}))
    assert regular == [
        "vprofile|image_source|uploaded",
        "vprofile|image_source|create",
        "vprofile|image_source|description",
        "vprofile|image_source|none",
        "vprofile|back",
        "menu|main",
    ]
    storyboard = _callbacks(scope["video_scene3_image_source_keyboard"]({"storyboard_image_required": True}))
    assert "vprofile|image_source|description" not in storyboard
    assert "vprofile|image_source|none" not in storyboard
    assert len(regular) == len(set(regular))
    assert len(storyboard) == len(set(storyboard))


def test_route5_contextual_image_ai_keyboards_return_to_exact_scene3_source():
    scope = _compile_functions(
        "quick_image_entry_keyboard",
        "quick_image_prepared_prompt_keyboard",
        namespace={
            "InlineKeyboardButton": _Button,
            "InlineKeyboardMarkup": _Markup,
            "normalize_user_language": lambda lang: lang,
            "ui_text": lambda _lang, key: "Menu chính" if key == "common.main_menu" else key,
        },
    )
    entry = scope["quick_image_entry_keyboard"](
        "vi",
        back_callback="vprofile|image_ai_return",
        back_label="⬅️ Nguồn hình ảnh",
    )
    prepared = scope["quick_image_prepared_prompt_keyboard"](
        "vi",
        context_return_callback="vprofile|image_ai_return",
        context_return_label="⬅️ Nguồn hình ảnh",
    )
    for markup in (entry, prepared):
        callbacks = _callbacks(markup)
        assert "vprofile|image_ai_return" in callbacks
        assert "menu|main_image" not in callbacks
        assert len(callbacks) == len(set(callbacks))


def test_route5_context_is_persisted_into_paid_image_confirmation():
    scope = _compile_functions("quick_image_video_scene3_confirmation_fields")
    assert scope["quick_image_video_scene3_confirmation_fields"]({
        "source_flow": "video_scene3",
        "return_to": "vprofile|image_ai_return",
        "return_label": "⬅️ Nguồn hình ảnh",
    }) == {
        "origin_flow": "video_scene3",
        "return_to": "vprofile|image_ai_return",
        "return_label": "⬅️ Nguồn hình ảnh",
    }
    assert scope["quick_image_video_scene3_confirmation_fields"]({"source_flow": "image_menu"}) == {}
    handler = _function_source("handle_create_media_callback")
    assert "**quick_image_video_scene3_confirmation_fields(state)" in handler


def test_route5_delivered_quick_image_is_recorded_once_and_returns_to_image_assets():
    saved: dict = {}
    context = SimpleNamespace(user_data={"video_scene3_image_handoff_active": True})

    def current_state(_context):
        return dict(saved) if saved else {
            "step": "image_source",
            "scene_count": 2,
            "image_source_mode": "create",
            "reference_assets": {},
        }

    def step(_context, state, target, push=True):
        updated = dict(state)
        updated["step"] = target
        return updated

    def save(_context, state):
        saved.clear()
        saved.update(state)
        return dict(saved)

    scope = _compile_functions(
        "video_scene3_image_handoff_target_step",
        "video_scene3_record_generated_image",
        namespace={
            "video_profile_studio_state": current_state,
            "video_scene3_flow": video_scene3_flow,
            "video_profile_studio_step": step,
            "save_video_profile_studio_state": save,
            "safe_int": lambda value, default=0: int(value or default),
            "video_flow7_kind": lambda _state: "ai_real",
            "video_flow6": video_flow6,
        },
    )
    for _ in range(2):
        result = scope["video_scene3_record_generated_image"](
            context,
            77,
            {"origin_flow": "video_scene3"},
            job_id=901,
            output_file_id="telegram-image-901",
            image_url="https://example.test/image-901.png",
            prompt="Ảnh sản phẩm",
            delivered=True,
        )
        assert result["step"] == "image_assets"
    items = saved["reference_assets"]["items"]
    assert len(items) == 1
    assert items[0]["source_job_id"] == 901
    assert items[0]["file_id"] == "telegram-image-901"
    assert saved["image_generation_confirmed"] is True
    assert context.user_data["video_scene3_image_handoff_active"] is False


def test_route5_contextual_success_and_failure_return_to_scene3_not_image_hub():
    delivery = _function_source("handle_shopaikey_public_image_confirm_delivery_first")
    success_keyboard = _function_source("public_image_success_keyboard")
    assert "return_callback=scene3_return_callback" in delivery
    assert "video_scene3_record_generated_image(" in delivery
    assert delivery.count("video_scene3_image_handoff_panel(") >= 3
    panel = _function_source("video_scene3_image_handoff_panel")
    assert "video_scene3_asset_gate_keyboard(state)" in panel
    assert "video_scene3_image_source_keyboard(state)" in panel
    assert "video_scene3_image_assets_keyboard(state)" in panel
    assert 'callback_data="vprofile|image_source|create"' in success_keyboard
    assert 'callback_data="menu|main_image"' not in success_keyboard


def _run_image_source_callback(data: str, initial_state: dict):
    events: list[tuple] = []
    state_store = video_scene3_flow.normalize_state(initial_state)

    class Query:
        def __init__(self):
            self.data = data
            self.from_user = SimpleNamespace(id=77)

        async def answer(self, *args, **kwargs):
            events.append(("answer", args, kwargs))

    context = SimpleNamespace(user_data={})

    def save_state(_context, state):
        nonlocal state_store
        state_store = dict(state)
        return dict(state_store)

    def step(_context, state, target, push=True, **fields):
        updated = dict(state)
        updated.update(fields)
        updated["step"] = target
        events.append(("step", target, push))
        return save_state(_context, updated)

    def set_quick(_uid, target, **fields):
        payload = {"step": target, **fields}
        events.append(("quick_image", payload))
        return payload

    async def render(_query, state, _lang):
        events.append(("render", state.get("step")))
        return state.get("step")

    async def edit(_query, text, **kwargs):
        events.append(("edit", text, kwargs.get("reply_markup")))
        return "quick_image_entry"

    scope = _compile_functions(
        "handle_video_profile_studio_callback",
        namespace={
            "video_profile_studio_state": lambda _context: dict(state_store),
            "get_user_language": lambda _uid: "vi",
            "video_scene2_action_allowed": lambda _state, _action: True,
            "video_scene2_reconcile_state": lambda _context, state: state,
            "video_scene3_flow": video_scene3_flow,
            "video_profile_studio_step": step,
            "save_video_profile_studio_state": save_state,
            "clear_quick_image_flow": lambda uid: events.append(("clear_quick", uid)),
            "set_quick_image_flow": set_quick,
            "quick_image_entry_text": lambda _lang: "quick image",
            "quick_image_context_return_callback": lambda state: state["return_to"],
            "quick_image_context_return_label": lambda state, _lang: state["return_label"],
            "quick_image_entry_keyboard": lambda _lang, **kwargs: kwargs,
            "safe_edit_or_send": edit,
            "video_profile_scene1_render": render,
        },
    )
    result = asyncio.run(
        scope["handle_video_profile_studio_callback"](
            SimpleNamespace(callback_query=Query()),
            context,
        )
    )
    return result, state_store, context, events


@pytest.mark.parametrize(
    ("mode", "target"),
    (("uploaded", "image_assets"), ("description", "creative_controls"), ("none", "creative_controls")),
)
def test_route5_non_ai_image_sources_route_once_to_their_canonical_screen(mode: str, target: str):
    result, state, _context, events = _run_image_source_callback(
        f"vprofile|image_source|{mode}",
        {"step": "image_source", "scene_count": 2},
    )
    assert result == target
    assert state["image_source_mode"] == mode
    assert [event for event in events if event[0] == "render"] == [("render", target)]
    assert not [event for event in events if event[0] == "quick_image"]
    assert video_scene3_flow.preconfirm_side_effects(state) == {
        "provider_called": False,
        "image_provider_called": False,
        "job_created": False,
        "outbox_created": False,
        "xu_charged": 0,
        "wallet_mutations": 0,
    }


def test_route5_create_image_enters_canonical_quick_image_and_preserves_scene3_session():
    result, state, context, events = _run_image_source_callback(
        "vprofile|image_source|create",
        {"step": "image_source", "scene_count": 3, "subject": "Sản phẩm mới"},
    )
    assert result == "quick_image_entry"
    assert state["step"] == "image_source"
    assert state["image_source_mode"] == "create"
    assert state["scene_count"] == 3
    assert state["subject"] == "Sản phẩm mới"
    assert context.user_data["video_scene3_image_handoff_active"] is True
    quick = [event[1] for event in events if event[0] == "quick_image"]
    assert quick == [{
        "step": "entry",
        "suggest_offset": 0,
        "source_flow": "video_scene3",
        "return_to": "vprofile|image_ai_return",
        "return_label": "⬅️ Nguồn hình ảnh",
    }]
    assert video_scene3_flow.preconfirm_side_effects(state) == {
        "provider_called": False,
        "image_provider_called": False,
        "job_created": False,
        "outbox_created": False,
        "xu_charged": 0,
        "wallet_mutations": 0,
    }


def test_route5_image_ai_return_clears_handoff_and_opens_exact_parent_screen():
    result, state, context, events = _run_image_source_callback(
        "vprofile|image_ai_return",
        {"step": "image_source", "scene_count": 2, "image_source_mode": "create"},
    )
    assert result == "image_source"
    assert state["step"] == "image_source"
    assert context.user_data["video_scene3_image_handoff_active"] is False
    assert [event for event in events if event[0] == "render"] == [("render", "image_source")]


def test_route5_storyboard_rejects_description_without_mutating_image_source():
    result, state, _context, events = _run_image_source_callback(
        "vprofile|image_source|description",
        {"step": "image_source", "scene_count": 2, "storyboard_image_required": True},
    )
    assert result is None
    assert state.get("image_source_mode") in {None, ""}
    visible_alerts = [event for event in events if event[0] == "answer" and event[2].get("show_alert")]
    assert len(visible_alerts) == 1
    assert not [event for event in events if event[0] in {"render", "edit", "quick_image"}]


def test_route5_duplicate_callback_query_is_stopped_before_second_owner_response():
    class HandlerStop(Exception):
        pass

    answers: list[str] = []

    class Query:
        id = "callback-100"
        data = "vprofile|image_source|create"

        async def answer(self, text="", **_kwargs):
            answers.append(text)

    scope = _compile_functions(
        "_claim_video_public_event",
        "_is_video_public_callback",
        "video_public_callback_dedupe_guard",
        namespace={
            "time": SimpleNamespace(time=lambda: 1_000.0),
            "VIDEO_PUBLIC_CALLBACK_DEDUPE_TTL_SECONDS": 600,
            "VIDEO_PUBLIC_CALLBACK_PREFIXES": ("vprofile|",),
            "_VIDEO_PUBLIC_CALLBACK_CLAIMS": {},
            "ApplicationHandlerStop": HandlerStop,
        },
    )
    update = SimpleNamespace(callback_query=Query())
    context = SimpleNamespace(user_data={})
    assert asyncio.run(scope["video_public_callback_dedupe_guard"](update, context)) is None
    with pytest.raises(HandlerStop):
        asyncio.run(scope["video_public_callback_dedupe_guard"](update, context))
    assert answers == ["TOAN AAS đã nhận thao tác này."]


def test_route5_same_scene3_media_message_is_consumed_once():
    state = {
        "step": "await_material_upload",
        "input_target": "character_person",
        "processed_media_message_ids": [],
    }
    replies: list[str] = []

    class Message:
        message_id = 701
        photo = None
        voice = None
        audio = None
        document = None

        async def reply_text(self, text, **_kwargs):
            replies.append(text)

    def save(_context, updated):
        state.clear()
        state.update(updated)
        return dict(state)

    scope = _compile_functions(
        "handle_video_scene3_pending_media",
        namespace={
            "video_profile_studio_state": lambda _context: dict(state),
            "safe_int": lambda value, default=0: int(value or default),
            "save_video_profile_studio_state": save,
            "video_scene3_flow": video_scene3_flow,
            "video_scene3_keyboard": lambda rows: rows,
            "video_scene3_nav_rows": lambda: [[("Quay lại", "vprofile|back")]],
        },
    )
    update = SimpleNamespace(message=Message(), effective_user=SimpleNamespace(id=88))
    context = SimpleNamespace(user_data={})
    assert asyncio.run(scope["handle_video_scene3_pending_media"](update, context)) is True
    assert asyncio.run(scope["handle_video_scene3_pending_media"](update, context)) is True
    assert len(replies) == 1
    assert state["processed_media_message_ids"] == [701]


def test_route5_every_public_prefix_has_one_registered_owner_and_no_overlap():
    owners = _literal_assignment("VIDEO_PUBLIC_CALLBACK_OWNER_PREFIXES")
    prefixes = [prefix for prefix, _owner in owners]
    assert len(prefixes) == len(set(prefixes))
    assert BOT_SOURCE.count(
        'CallbackQueryHandler(handle_product_video_public_confirm_callback, pattern=r"^vproduct\\|b14_confirm$")'
    ) == 1
    assert BOT_SOURCE.count(
        'CallbackQueryHandler(handle_video_product_callback, pattern=r"^vproduct\\|(?!b14_confirm(?:\\||$))")'
    ) == 1
    for prefix, owner in owners:
        if prefix.startswith("vproduct|"):
            continue
        pattern = "^" + prefix.replace("|", "\\|")
        registration = f'CallbackQueryHandler({owner}, pattern=r"{pattern}"'
        assert BOT_SOURCE.count(registration) == 1, (prefix, owner, registration)


def test_route5_public_keyboard_callback_literals_all_have_canonical_owners():
    owner_prefixes = _literal_assignment("VIDEO_PUBLIC_CALLBACK_OWNER_PREFIXES")
    keyboard_names = (
        "main_video_keyboard",
        "task3d_product_intro_keyboard",
        "video_scene3_image_source_keyboard",
        "video_scene3_image_assets_keyboard",
        "video_scene3_profile_keyboard",
        "video_scene3_scene_plan_keyboard",
        "video_scene3_prompt_keyboard",
        "video_scene3_full_review_keyboard",
        "video_scene3_audio_plan_keyboard",
        "video_scene3_post_keyboard",
        "video_edit_hub_keyboard",
        "video_local_manual_options_keyboard",
        "video_ai_edit_source_summary_keyboard",
        "video_quality_enhance_source_keyboard",
        "quick_image_entry_keyboard",
        "quick_image_prepared_prompt_keyboard",
    )
    literal_callbacks: set[str] = set()
    for name in keyboard_names:
        source = _function_source(name)
        literal_callbacks.update(
            value
            for value in re.findall(r'["\']([a-zA-Z_]+\|[^"\']+)["\']', source)
            if "{" not in value
        )
    unmapped = sorted(
        callback
        for callback in literal_callbacks
        if not any(callback.startswith(prefix) for prefix, _owner in owner_prefixes)
    )
    assert not unmapped, f"unmapped={unmapped!r}"


def test_route5_all_public_video_keyboard_callback_prefixes_have_one_owner():
    owner_prefixes = _literal_assignment("VIDEO_PUBLIC_CALLBACK_OWNER_PREFIXES")
    keyboard_names = re.findall(r"^def ([A-Za-z0-9_]+keyboard)\(", BOT_SOURCE, flags=re.MULTILINE)
    public_name_prefixes = (
        "main_video",
        "task3d_",
        "video_",
        "quick_image_",
        "trend_",
        "storyboard_",
        "frame_video_",
        "image_to_video_",
        "public_video_",
    )
    callback_prefixes: set[str] = set()
    for name in keyboard_names:
        if not name.startswith(public_name_prefixes):
            continue
        source = _function_source(name)
        callback_prefixes.update(
            match
            for match in re.findall(r'callback_data=(?:f)?["\']([a-zA-Z_]+\|)', source)
        )
        callback_prefixes.update(
            match
            for match in re.findall(r'["\']([a-zA-Z_]+\|[^"\']*)["\']', source)
            if "{" not in match
        )
    unmapped = sorted(
        callback
        for callback in callback_prefixes
        if not any(callback.startswith(prefix) for prefix, _owner in owner_prefixes)
    )
    assert not unmapped, f"unmapped={unmapped!r}"


def test_route5_scope_has_no_provider_payment_or_worker_changes():
    expected_changed = {
        "bot.py",
        "tests/test_p0_video_route5_full_callback_image_ai_backstack.py",
        "tests/test_p0_video_flow4_callback_route_recovery.py",
        "tests/test_p0_image_live1_public_image_generation.py",
    }
    assert not expected_changed & {
        "remote_worker.py",
        "local_worker.py",
        "services/video_provider_router.py",
        "services/video_real_render_connector.py",
        "services/payment.py",
        "services/wallet.py",
        "services/storage.py",
    }
