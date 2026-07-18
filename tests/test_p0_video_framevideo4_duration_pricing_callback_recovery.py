from __future__ import annotations

import asyncio
import html
import math
import re
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

import pytest

from services import frame_video_commercial as commercial
from services import frame_video_flow as flow


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _source_between(start: str, end: str) -> str:
    return BOT_SOURCE[BOT_SOURCE.index(start) : BOT_SOURCE.index(end)]


@lru_cache(maxsize=1)
def _load_pricing_function():
    namespace = {"math": math, "XU_TO_VND": 100}
    function_source = _source_between(
        "def img2vid_slideshow_price_breakdown",
        "def img2vid_slideshow_price_for_state",
    )
    exec(compile(function_source, "bot.py", "exec"), namespace)
    return namespace["img2vid_slideshow_price_breakdown"]


@pytest.mark.parametrize(
    ("seconds", "expected_xu"),
    [(5, 0), (6, 20), (10, 100), (11, 115), (20, 250), (21, 260)],
)
def test_progressive_duration_price_table(seconds: int, expected_xu: int) -> None:
    price = _load_pricing_function()(1, seconds)
    assert price["duration_seconds"] == seconds
    assert price["price_xu"] == expected_xu
    assert price["total"] == expected_xu
    assert price["free_duration_entitlement"] is (seconds <= 5)
    assert price["pricing_source"] == "frame_video_duration_progressive_v1"


def test_duration_is_mandatory_and_only_explicit_short_duration_can_be_free() -> None:
    state = flow.normalize_state(
        {
            "commercial_flow_version": "framevideo3",
            "image_count": 2,
            "photos": [{"file_id": "one"}, {"file_id": "two"}],
        }
    )
    blocked = commercial.video_quote(
        state,
        {"base": 40, "addon_xu": 0, "music_xu": 0, "total": 40},
    )
    assert blocked["ok"] is False
    assert blocked["blocker"] == "duration_confirmation_missing"

    state = flow.set_global_duration(state, 2)
    free_breakdown = _load_pricing_function()(2, 2)
    allowed = commercial.video_quote(state, free_breakdown)
    assert allowed["ok"] is True
    assert allowed["total_price_xu"] == 0
    assert allowed["free_duration_entitlement"] is True

    fake_free = commercial.video_quote(
        state,
        {
            "base": 0,
            "addon_xu": 0,
            "music_xu": 0,
            "total": 0,
            "free_trial_eligible": True,
            "pricing_source": "legacy",
        },
    )
    assert fake_free["ok"] is False
    assert fake_free["blocker"] == "video_pricing_unavailable"


def test_timeline_changes_invalidate_the_confirmed_duration() -> None:
    state = flow.normalize_state(
        {
            "commercial_flow_version": "framevideo3",
            "image_count": 2,
            "photos": [{"file_id": "one"}, {"file_id": "two"}],
        }
    )
    state = flow.set_global_duration(state, 3)
    assert state["duration_confirmed"] is True

    state = flow.add_photo(state, {"file_id": "three"})
    assert state["duration_confirmed"] is False

    state = flow.set_global_duration(state, 3)
    state = flow.apply_image_action(state, "delete", state["selected_image_id"])
    assert state["duration_confirmed"] is False


def test_public_image_manager_is_compact_and_duration_is_a_priced_step() -> None:
    collect = _source_between("def frame_video_collect_keyboard", "FRAME_VIDEO_TRANSITION_LABELS")
    manager = _source_between("def frame_video_images_keyboard", "def frame_video_duration_menu_text")
    duration = _source_between("def frame_video_duration_menu_text", "def frame_video_ratio_menu_keyboard")
    quality = _source_between("def frame_video_quality_keyboard", "def frame_video_review_text")

    for removed in ("Ghi chú ảnh", "Thời lượng ảnh này", "Biên nhận ảnh", "Đổi nguồn"):
        assert removed not in collect
        assert removed not in manager
    for label in (
        "0–5 giây: 0 Xu",
        "trên 5 đến 10 giây: 20 Xu/giây",
        "trên 10 đến 20 giây: 15 Xu/giây",
        "trên 20 giây: 10 Xu/giây",
        "✅ Dùng thời lượng này",
    ):
        assert label in duration
    assert "⭐ <b>Hoàn thiện video</b>" in quality
    assert "✅ Bước tiếp theo" in quality


def test_stale_callbacks_are_read_only_and_preflight_preserves_exact_reason() -> None:
    for action in ("image_caption", "image_receipt", "image_duration"):
        route = flow.FRAME_VIDEO_ROUTE_MATRIX[action]
        assert route["screen"] == "images"
        assert route["mutation"] == "read_only_redirect"

    handler = _source_between(
        "async def handle_frame_video_canonical_callback",
        "async def handle_frame_video_image_regeneration",
    )
    assert 'if action in {"image_caption", "image_receipt", "image_duration"}' in handler
    assert "Có lỗi khi xử lý lệnh" not in handler

    preflight = _source_between(
        "def frame_video_commercial_preflight",
        "def frame_video_runtime_guard",
    )
    assert 'str(value) != "video_package_unavailable"' in preflight
    assert 'result["message"] = frame_video_preflight_message(result)' in preflight


def test_video_delivery_and_charge_order_remains_final_only() -> None:
    confirm = _source_between(
        "async def handle_frame_video_final_confirm",
        "async def handle_frame_video_canonical_callback",
    )
    assert confirm.index("context.bot.send_video") < confirm.index(
        "frame_video_charge_after_delivery"
    )
    assert "delivery_message_id" in confirm
    assert "receipt_recorded" in confirm


def test_ai_image_prompts_lock_one_concrete_subject_across_the_batch() -> None:
    namespace = {"IMG2VID_AI_IMAGE_MAX_COUNT": 20}
    source = _source_between(
        "def img2vid_continuity_anchor",
        "def img2vid_state_debug_dict",
    )
    exec(compile("from __future__ import annotations\n" + source, "bot.py", "exec"), namespace)
    prompts = namespace["img2vid_image_prompt_variants"](
        "Ảnh sản phẩm quảng cáo studio",
        2,
    )

    assert len(prompts) == 2
    assert prompts[0] != prompts[1]
    assert all("điện thoại thông minh màu đen nhám" in prompt for prompt in prompts)
    assert all("HỢP ĐỒNG LIÊN TỤC BẮT BUỘC" in prompt for prompt in prompts)
    assert all("không thay bằng sản phẩm khác" in prompt for prompt in prompts)
    assert all("drone" not in prompt.casefold() for prompt in prompts)


def test_assets_done_has_one_owner_and_falls_back_to_one_fresh_duration_panel() -> None:
    saved = []
    sent = []

    class Logger:
        def warning(self, *_args, **_kwargs):
            return None

        def error(self, *_args, **_kwargs):
            return None

    class Bot:
        async def send_message(self, **kwargs):
            sent.append(kwargs)
            return kwargs

    async def failing_edit(*_args, **_kwargs):
        raise RuntimeError("Telegram edit variant not recognized")

    namespace = {
        "normalize_frame_video_state": lambda state: dict(state),
        "_safe_int": lambda value, default=0: int(value or default),
        "ivf": SimpleNamespace(
            frame_video_image_count_text=lambda *_args: "count",
            frame_video_image_count_keyboard=lambda *_args: "count_keyboard",
        ),
        "frame_video_collect_keyboard": lambda *_args: "collect_keyboard",
        "frame_video_duration_menu_text": lambda _state: "<b>Chọn thời lượng</b>",
        "frame_video_duration_menu_keyboard": lambda *_args: "duration_keyboard",
        "set_frame_video_state": lambda uid, state: saved.append((uid, dict(state))),
        "safe_edit_or_send": failing_edit,
        "logger": Logger(),
        "sanitize_log_text": str,
        "html": html,
        "re": re,
    }
    source = _source_between(
        "async def handle_frame_video_assets_done",
        "async def handle_frame_video_canonical_callback",
    )
    exec(compile("from __future__ import annotations\n" + source, "bot.py", "exec"), namespace)
    query = SimpleNamespace(message=SimpleNamespace(chat_id=123), bot=None)
    context = SimpleNamespace(bot=Bot())
    state = {
        "commercial_flow_version": "framevideo3",
        "image_count": 2,
        "photos": [{"file_id": "one"}, {"file_id": "two"}],
    }

    result = asyncio.run(
        namespace["handle_frame_video_assets_done"](query, context, 99, "vi", state)
    )

    assert saved[-1][1]["step"] == "duration"
    assert len(sent) == 1
    assert sent[0]["text"] == "<b>Chọn thời lượng</b>"
    assert sent[0]["reply_markup"] == "duration_keyboard"
    assert result == sent[0]
    assert flow.FRAME_VIDEO_ROUTE_MATRIX["assets_done"]["owner"] == "handle_frame_video_assets_done"
    callback = _source_between(
        "async def handle_frame_video_callback",
        "async def handle_storyboard_callback",
    )
    assert callback.count('if action == "assets_done"') == 1
