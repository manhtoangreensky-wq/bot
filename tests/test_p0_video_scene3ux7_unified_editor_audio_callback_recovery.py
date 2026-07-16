from __future__ import annotations

import asyncio
import ast
from pathlib import Path
from types import SimpleNamespace

from services import video_scene3_flow


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    markers = (f"def {name}(", f"async def {name}(")
    positions = [BOT_SOURCE.find(marker) for marker in markers]
    start = min(position for position in positions if position >= 0)
    candidates = [
        position
        for marker in ("\ndef ", "\nasync def ")
        if (position := BOT_SOURCE.find(marker, start + 1)) >= 0
    ]
    return BOT_SOURCE[start:min(candidates) if candidates else len(BOT_SOURCE)]


def _literal_assignment(name: str):
    start = BOT_SOURCE.index(f"{name} =")
    end = BOT_SOURCE.find("\n\n", start)
    module = ast.parse(BOT_SOURCE[start:end if end >= 0 else len(BOT_SOURCE)])
    assignment = module.body[0]
    return ast.literal_eval(assignment.value)


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


def _compile_functions(*names: str, namespace: dict | None = None) -> dict:
    scope = dict(namespace or {})
    for name in names:
        exec(
            compile(
                "from __future__ import annotations\n\n" + _function_source(name),
                f"<scene3ux7:{name}>",
                "exec",
            ),
            scope,
        )
    return scope


def _state(*, step: str = "creative_detail") -> dict:
    state = video_scene3_flow.default_state(
        product_type="video_ai_real",
        subject="Giới thiệu sản phẩm bằng hai cảnh nối tiếp tự nhiên",
    )
    state = video_scene3_flow.invalidate_scene_outputs(state, 2)
    state.update({
        "step": step,
        "technical_profile": "product_3d_showcase",
        "content_type": "product_review",
        "history": ["requirements"] if step == "audio_plan" else ["creative_controls"],
    })
    return video_scene3_flow.normalize_state(state)


def test_all_unified_fields_bind_each_number_to_the_exact_active_field():
    groups = (
        ("creative_controls", video_scene3_flow.CREATIVE_CONTROLS),
        ("preservation_requirements", video_scene3_flow.PUBLIC_REQUIREMENT_CATEGORIES),
    )
    for group, fields in groups:
        for key, _label in fields:
            suggestions = video_scene3_flow.unified_field_suggestions(_state(), group, key)
            assert len(suggestions) == 5
            for selection in range(1, 6):
                before = _state()
                after = video_scene3_flow.select_unified_field_suggestion(
                    before,
                    group,
                    key,
                    selection,
                )
                entry = after[group][key]
                assert entry["enabled"] is True
                assert entry["value"] == suggestions[selection - 1]
                for other_key, _other_label in fields:
                    if other_key != key:
                        assert after[group][other_key] == before[group][other_key]


def test_unified_field_restore_uses_real_history_and_invalid_pick_is_read_only():
    state = _state()
    state = video_scene3_flow.select_unified_field_suggestion(
        state, "creative_controls", "colors", 1
    )
    first_value = state["creative_controls"]["colors"]["value"]
    state = video_scene3_flow.select_unified_field_suggestion(
        state, "creative_controls", "colors", 2
    )
    restored = video_scene3_flow.restore_entry(state, "creative_controls", "colors")
    assert restored["creative_controls"]["colors"]["value"] == first_value

    unchanged = video_scene3_flow.select_unified_field_suggestion(
        restored, "creative_controls", "colors", 99
    )
    unknown = video_scene3_flow.select_unified_field_suggestion(
        restored, "creative_controls", "not_a_field", 1
    )
    assert unchanged == restored
    assert unknown == restored


def test_all_unified_editor_keyboards_have_one_to_five_and_exact_navigation():
    scope = _compile_functions(
        "video_scene3_keyboard",
        "video_scene3_field_editor_keyboard",
        namespace={
            "InlineKeyboardButton": _Button,
            "InlineKeyboardMarkup": _Markup,
            "video_scene3_flow": video_scene3_flow,
        },
    )
    keyboard = scope["video_scene3_field_editor_keyboard"]
    for group, fields, pick, custom, restore, back in (
        (
            "creative_controls",
            video_scene3_flow.CREATIVE_CONTROLS,
            "creative_pick",
            "creative_custom",
            "creative_restore",
            "creative_detail_done",
        ),
        (
            "preservation_requirements",
            video_scene3_flow.PUBLIC_REQUIREMENT_CATEGORIES,
            "req_pick",
            "req_custom",
            "req_restore",
            "req_detail_done",
        ),
    ):
        for key, _label in fields:
            state = _state()
            callbacks = _callbacks(
                keyboard(
                    state,
                    group=group,
                    pick_action=pick,
                    custom_action=custom,
                    restore_action=restore,
                    back_action=back,
                    key=key,
                )
            )
            assert callbacks[:5] == [f"vprofile|{pick}|{index}" for index in range(1, 6)]
            assert f"vprofile|{custom}" in callbacks
            assert f"vprofile|{back}" in callbacks
            assert "vprofile|back" not in callbacks
            assert "menu|main" in callbacks
            assert len(callbacks) == len(set(callbacks))


def test_audio_planner_toggle_is_canonical_reversible_and_has_no_duplicate_owner():
    for key, _label in video_scene3_flow.AUDIO_PLANNING_ADDONS:
        state = _state(step="audio_plan")
        enabled = video_scene3_flow.toggle_audio_planning_addon(state, key)
        assert enabled["postproduction_addons"][key]["enabled"] is True
        assert enabled["postproduction_addons"][key]["value"] == video_scene3_flow.post_addon_default(key)

        disabled = video_scene3_flow.toggle_audio_planning_addon(enabled, key)
        assert disabled["postproduction_addons"][key]["enabled"] is False
        assert set(disabled["postproduction_addons"]) == set(state["postproduction_addons"])

        enabled_again = video_scene3_flow.toggle_audio_planning_addon(disabled, key)
        assert enabled_again["postproduction_addons"][key]["enabled"] is True
        assert video_scene3_flow.preconfirm_audio_side_effects(enabled_again) == {
            "music_provider_calls": 0,
            "voice_provider_calls": 0,
            "files_generated": 0,
        }


def test_audio_keyboard_has_one_callback_per_action_and_no_duplicate_buttons():
    scope = _compile_functions(
        "video_scene3_keyboard",
        "video_scene3_nav_rows",
        "video_scene3_audio_plan_keyboard",
        namespace={
            "InlineKeyboardButton": _Button,
            "InlineKeyboardMarkup": _Markup,
            "video_scene3_flow": video_scene3_flow,
        },
    )
    callbacks = _callbacks(scope["video_scene3_audio_plan_keyboard"](_state(step="audio_plan")))
    assert callbacks == [
        "vprofile|audio_open|dubbing",
        "vprofile|audio_open|subtitles",
        "vprofile|audio_open|source_audio",
        "vprofile|audio_open|music",
        "vprofile|audio_open|sfx",
        "vprofile|audio_done",
        "vprofile|audio_skip",
        "vprofile|back",
        "menu|main",
    ]
    assert len(callbacks) == len(set(callbacks))


def test_audio_plan_and_skip_are_local_only_and_move_to_scene_plan():
    selected = _state(step="audio_plan")
    for key, _label in video_scene3_flow.AUDIO_PLANNING_ADDONS:
        selected = video_scene3_flow.toggle_audio_planning_addon(selected, key)

    planned = video_scene3_flow.finalize_audio_planning(selected, skip=False)
    assert len(planned["scene_plan"]["scenes"]) == 2
    assert video_scene3_flow.preconfirm_side_effects(planned) == {
        "provider_called": False,
        "image_provider_called": False,
        "job_created": False,
        "outbox_created": False,
        "xu_charged": 0,
        "wallet_mutations": 0,
    }

    skipped = video_scene3_flow.finalize_audio_planning(selected, skip=True)
    for key, _label in video_scene3_flow.AUDIO_PLANNING_ADDONS:
        assert skipped["postproduction_addons"][key]["enabled"] is False
    assert len(skipped["scene_plan"]["scenes"]) == 2


def test_actual_callback_owner_handles_field_picks_audio_toggles_plan_and_skip_once():
    expected_steps = _literal_assignment("VIDEO_SCENE2_ACTION_EXPECTED_STEPS")
    assert expected_steps["creative_pick"] == {"creative_detail", "creative_suggestions"}
    assert expected_steps["req_pick"] == {"requirement_detail"}
    assert expected_steps["audio_open"] == {"audio_plan"}

    response_count = 0

    def save_state(context, state):
        clean = video_scene3_flow.normalize_state(state)
        context.user_data["video_profile_studio"] = clean
        return clean

    def read_state(context):
        return video_scene3_flow.normalize_state(
            context.user_data.get("video_profile_studio") or {}
        )

    def step_state(context, state, step, *, push=True, **fields):
        history = list(state.get("history") or [])
        current = str(state.get("step") or "menu")
        if push and current != step:
            history.append(current)
        return save_state(
            context,
            {**state, **fields, "step": step, "history": history[-40:]},
        )

    def return_parent(context, state, parent, **fields):
        history = list(state.get("history") or [])
        if history and history[-1] == parent:
            history.pop()
        return save_state(
            context,
            {**state, **fields, "step": parent, "history": history},
        )

    async def render(_query, state, _lang):
        nonlocal response_count
        response_count += 1
        return save_state(context, state)

    async def safe_edit(_query, _text, **_kwargs):
        nonlocal response_count
        response_count += 1
        return None

    namespace = {
        "Update": object,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "get_user_language": lambda _uid: "vi",
        "video_profile_studio_state": read_state,
        "save_video_profile_studio_state": save_state,
        "video_profile_studio_step": step_state,
        "video_scene3_return_to_parent": return_parent,
        "video_scene2_action_allowed": lambda state, action: (
            action not in expected_steps
            or str(state.get("step") or "") in expected_steps[action]
        ),
        "video_scene2_reconcile_state": lambda _context, state: state,
        "video_profile_scene1_render": render,
        "video_scene3_flow": video_scene3_flow,
        "video_scene3_audio_plan_text": lambda _state: "Cấu hình lời thoại và âm thanh",
        "video_scene3_audio_plan_keyboard": lambda _state: None,
        "safe_edit_or_send": safe_edit,
        "safe_int": lambda value, default=0: int(value) if str(value or "").isdigit() else default,
        "VIDEO_PRODUCT_REGISTRY": {},
        "logger": SimpleNamespace(warning=lambda *_args, **_kwargs: None),
    }
    exec(
        compile(
            "from __future__ import annotations\n\n"
            + _function_source("handle_video_profile_studio_callback"),
            "<scene3ux7-handler>",
            "exec",
        ),
        namespace,
    )
    handler = namespace["handle_video_profile_studio_callback"]

    class Query:
        def __init__(self):
            self.data = ""
            self.from_user = SimpleNamespace(id=123)
            self.answer_count = 0

        async def answer(self, *_args, **_kwargs):
            self.answer_count += 1

    query = Query()
    context = SimpleNamespace(user_data={})
    update = SimpleNamespace(callback_query=query)

    async def run(callback: str):
        nonlocal response_count
        response_count = 0
        query.answer_count = 0
        query.data = callback
        await handler(update, context)
        assert query.answer_count == 1
        assert response_count == 1
        return read_state(context)

    async def scenario():
        for key, _label in video_scene3_flow.CREATIVE_CONTROLS:
            save_state(context, {**_state(), "active_creative": key})
            state = await run("vprofile|creative_pick|5")
            assert state["step"] == "creative_detail"
            assert state["creative_controls"][key]["value"] == video_scene3_flow.creative_suggestions(state, key)[4]

        for key, _label in video_scene3_flow.PUBLIC_REQUIREMENT_CATEGORIES:
            save_state(
                context,
                {
                    **_state(step="requirement_detail"),
                    "active_requirement": key,
                },
            )
            state = await run("vprofile|req_pick|3")
            assert state["step"] == "requirement_detail"
            assert state["preservation_requirements"][key]["value"] == video_scene3_flow.requirement_suggestions(state, key)[2]

        save_state(context, _state(step="audio_plan"))
        for key, _label in video_scene3_flow.AUDIO_PLANNING_ADDONS:
            state = await run(f"vprofile|audio_open|{key}")
            assert state["step"] == "post_detail"
            assert state["active_post_addon"] == key
            assert state["post_return_step"] == "audio_plan"
            state = save_state(context, {**state, "step": "audio_plan"})

        state = await run("vprofile|audio_done")
        assert state["step"] == "scene_plan"

        save_state(context, _state(step="audio_plan"))
        state = await run("vprofile|audio_skip")
        assert state["step"] == "scene_plan"

        original_finalize = video_scene3_flow.finalize_audio_planning
        try:
            def fail_planning(_state, *, skip=False):
                raise ValueError("fixture_missing_plan_data")

            video_scene3_flow.finalize_audio_planning = fail_planning
            save_state(context, _state(step="audio_plan"))
            state = await run("vprofile|audio_done")
            assert state["step"] == "audio_plan"
        finally:
            video_scene3_flow.finalize_audio_planning = original_finalize

    asyncio.run(scenario())


def test_registration_and_back_stack_have_one_owner_and_no_cross_module_route():
    assert BOT_SOURCE.count(
        'CallbackQueryHandler(handle_video_profile_studio_callback, pattern=r"^vprofile\\|")'
    ) == 1
    assert BOT_SOURCE.index("video_public_callback_dedupe_guard") < BOT_SOURCE.index(
        'CallbackQueryHandler(handle_video_profile_studio_callback, pattern=r"^vprofile\\|")'
    )
    assert video_scene3_flow.BACK_STEP["creative_detail"] == "creative_controls"
    assert video_scene3_flow.BACK_STEP["requirement_detail"] == "requirements"
    assert video_scene3_flow.BACK_STEP["audio_plan"] == "requirements"
    handler = _function_source("handle_video_profile_studio_callback")
    audio_block = handler[handler.index('if action == "audio_open"'):handler.index('if action == "content"')]
    assert '"post_detail"' in audio_block
    assert 'post_return_step="audio_plan"' in audio_block
    assert "toggle_audio_planning_addon" not in audio_block
    assert "Có lỗi khi xử lý lệnh" not in audio_block
