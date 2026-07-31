from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace

from services import video_smart_splitter


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    async_marker = f"async def {name}("
    sync_marker = f"def {name}("
    start = BOT_SOURCE.find(async_marker)
    if start < 0:
        start = BOT_SOURCE.index(sync_marker)
    candidates = [
        BOT_SOURCE.find("\ndef ", start + 1),
        BOT_SOURCE.find("\nasync def ", start + 1),
    ]
    ends = [position for position in candidates if position >= 0]
    return BOT_SOURCE[start:min(ends) if ends else len(BOT_SOURCE)]


def _async_function_source(name: str) -> str:
    source = _function_source(name)
    assert source.startswith("async def ")
    return source


def _compile_function(name: str, namespace: dict):
    module = ast.parse("from __future__ import annotations\n\n" + _function_source(name))
    exec(compile(module, filename="bot.py", mode="exec"), namespace)
    return namespace[name]


def test_edit4_active_editor_owns_text_and_media_before_creation_flows() -> None:
    message_handler = _async_function_source("handle_message")
    editor_text = message_handler.index("handle_video_editor_pending_text")
    for competing_handler in (
        "handle_frame_video_pending_text",
        "handle_architecture_profile_pending_text",
        "handle_video_profile_studio_pending_text",
        "handle_video_product_pending_text",
        "handle_storyboard_pending_text",
        "handle_trend_video_flow_pending_text",
        "handle_public_video_prompt_pending_text",
        "handle_developing_video_pending_text",
    ):
        assert editor_text < message_handler.index(competing_handler)

    media_handler = _async_function_source("handle_media_cache_only")
    editor_media = media_handler.index("handle_video_editor_pending_upload")
    for competing_handler in (
        "handle_video_scene3_pending_media",
        "handle_architecture_profile_pending_media",
        "handle_video_product_pending_media",
        "handle_video_reference_pending_upload",
        "handle_self_scene_pending_upload",
    ):
        assert editor_media < media_handler.index(competing_handler)


def test_edit4_entry_clears_only_competing_creation_state() -> None:
    calls: list[tuple[str, int]] = []

    def clear_developing(user_id: int) -> bool:
        calls.append(("developing", user_id))
        return True

    helper = _compile_function(
        "clear_video_editor_competing_video_states",
        {
            "VIDEO_PROFILE_STUDIO_SESSION_KEY": "video_profile_studio",
            "clear_developing_video_pending": clear_developing,
        },
    )
    context = SimpleNamespace(
        user_data={
            "video_profile_studio": {"step": "await_count_custom"},
            "unrelated": {"keep": True},
        }
    )
    result = helper(78, context)

    assert result == {"scene3_cleared": True, "developing_video_cleared": True}
    assert context.user_data == {"unrelated": {"keep": True}}
    assert calls == [("developing", 78)]
    helper_source = _function_source("clear_video_editor_competing_video_states")
    assert "clear_video_editor_pending" not in helper_source
    assert "USER_PENDING.clear" not in helper_source


def test_edit4_entering_two_means_two_parts_not_two_scenes() -> None:
    state = {
        "step": "await_split_count",
        "selected_tool": "split",
        "source_duration_ms": 12_000,
        "source_metadata": {"duration_ms": 12_000},
        "split_ranges": [],
    }
    saved: dict = {}
    replies: list[dict] = []
    cleanup_calls: list[int] = []

    class Message:
        text = "2"

        async def reply_text(self, text: str, **kwargs):
            replies.append({"text": text, **kwargs})
            return True

    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=78),
        message=Message(),
    )
    context = SimpleNamespace(user_data={"video_profile_studio": {"step": "await_count_custom"}})

    cleanup = _compile_function(
        "clear_video_editor_competing_video_states",
        {
            "VIDEO_PROFILE_STUDIO_SESSION_KEY": "video_profile_studio",
            "clear_developing_video_pending": lambda user_id: cleanup_calls.append(user_id) or True,
        },
    )

    def update_pending(_user_id: int, step: str = "", **fields) -> dict:
        saved.clear()
        saved.update(state)
        saved.update(fields)
        saved["step"] = step
        return dict(saved)

    handler = _compile_function(
        "handle_video_editor_pending_text",
        {
            "get_video_editor_pending": lambda _user_id: dict(state),
            "clear_video_editor_competing_video_states": cleanup,
            "get_user_language": lambda _user_id: "vi",
            "safe_int": lambda value, default=0: int(value or default),
            "video_smart_splitter": video_smart_splitter,
            "update_video_editor_pending": update_pending,
            "return_video_editor_workspace": lambda user_id, **fields: update_pending(
                user_id, "options", **fields
            ),
            "video_local_split_options_text": lambda current, _lang: f"Đã chia thành {current['split_part_count']} phần.",
            "video_local_split_options_keyboard": lambda _current, _lang: "split-keyboard",
        },
    )

    assert asyncio.run(handler(update, context)) is True
    assert cleanup_calls == [78]
    assert saved["step"] == "options"
    assert saved["split_mode"] == "exact_count"
    assert saved["split_part_count"] == 2
    assert len(saved["split_ranges"]) == 2
    assert replies == [{"text": "Đã chia thành 2 phần.", "parse_mode": "HTML", "reply_markup": "split-keyboard"}]
    assert "video_profile_studio" not in context.user_data


def test_edit4_editor_output_stays_edit_job_not_product_video() -> None:
    submit = _async_function_source("submit_local_video_editor_job")
    assert "video_editengine1.create_job(" in submit
    assert "video_editengine1.stable_idempotency_key(" in submit
    assert '"provider_call": False' in submit
    assert '"charge_policy": "after_valid_mp4_delivery"' in submit
    assert '"quoted_price_xu": price_xu' in submit
    assert "create_local_worker_job(" not in submit
    assert "video_profile_scene1" not in submit
    assert "video_scene3_flow" not in submit
