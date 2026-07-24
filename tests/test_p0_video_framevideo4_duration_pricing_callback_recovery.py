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


def test_duration_is_mandatory_and_video_package_is_never_implicitly_free() -> None:
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
    legacy_free_breakdown = _load_pricing_function()(2, 2)
    allowed = commercial.video_quote(state, legacy_free_breakdown)
    assert allowed["ok"] is True
    assert allowed["base_xu"] == 100
    assert allowed["total_price_xu"] == 100
    assert allowed["free_duration_entitlement"] is False

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
    assert fake_free["ok"] is True
    assert fake_free["total_price_xu"] == 100


@pytest.mark.parametrize(
    ("quality", "expected_xu"),
    [("fast", 50), ("balanced", 100), ("beautiful", 200)],
)
def test_video_package_price_is_fixed_by_quality_not_duration(
    quality: str,
    expected_xu: int,
) -> None:
    state = flow.normalize_state(
        {
            "commercial_flow_version": "framevideo3",
            "image_count": 20,
            "photos": [{"file_id": str(index)} for index in range(20)],
            "seconds_per_image": 8,
            "duration_confirmed": True,
            "quality": quality,
        }
    )
    quote = commercial.video_quote(
        state,
        {"base": 9999, "addon_xu": 0, "music_xu": 0, "total": 9999},
    )
    assert quote["ok"] is True
    assert quote["duration_seconds"] > 150
    assert quote["base_xu"] == expected_xu
    assert quote["total_price_xu"] == expected_xu
    assert quote["pricing_source"] == "frame_video_fixed_quality_promo_v1"


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


def test_public_image_manager_is_compact_and_duration_precedes_fixed_packages() -> None:
    collect = _source_between("def frame_video_collect_keyboard", "FRAME_VIDEO_TRANSITION_LABELS")
    manager = _source_between("def frame_video_images_keyboard", "def frame_video_duration_menu_text")
    duration = _source_between("def frame_video_duration_menu_text", "def frame_video_ratio_menu_keyboard")
    quality = _source_between("def frame_video_quality_keyboard", "def frame_video_review_text")

    for removed in ("Ghi chú ảnh", "Thời lượng ảnh này", "Biên nhận ảnh", "Đổi nguồn"):
        assert removed not in collect
        assert removed not in manager
    for label in ("50 Xu", "100 Xu", "200 Xu", "✅ Dùng thời lượng này"):
        assert label in duration
    assert "0–5 giây: 0 Xu" not in duration
    assert "20 Xu/giây" not in duration
    assert "⭐ <b>Hoàn thiện video</b>" in quality
    assert "✅ Bước tiếp theo" in quality
    for label in ("Nhanh · 50 Xu", "Cân bằng · 100 Xu", "Đẹp · 200 Xu"):
        assert label in quality


def test_stale_callbacks_are_read_only_and_preflight_preserves_exact_reason() -> None:
    for action in ("image_caption", "image_receipt", "image_duration", "ratio_first_recommend"):
        route = flow.FRAME_VIDEO_ROUTE_MATRIX[action]
        assert route["mutation"] == "read_only_redirect"

    assert flow.FRAME_VIDEO_ROUTE_MATRIX["ratio_first_recommend"]["screen"] == "ratio_first"

    handler = _source_between(
        "async def handle_frame_video_canonical_callback",
        "async def handle_frame_video_image_regeneration",
    )
    assert 'if action in {"image_caption", "image_receipt", "image_duration"}' in handler
    assert "Có lỗi khi xử lý lệnh" not in handler

    public_callback = _source_between(
        "async def handle_frame_video_callback",
        "async def handle_storyboard_callback",
    )
    stale_branch = public_callback[
        public_callback.index('if action == "ratio_first_recommend"') :
        public_callback.index('if action == "ratio_first_set"')
    ]
    assert "set_frame_video_state" not in stale_branch
    assert "không tự đổi lựa chọn" in stale_branch

    preflight = _source_between(
        "def frame_video_commercial_preflight",
        "def frame_video_runtime_guard",
    )
    assert 'str(value) != "video_package_unavailable"' in preflight
    assert 'result["message"] = frame_video_preflight_message(result)' in preflight
    assert "candidate_ffmpeg = frame_video_ffmpeg_path()" in preflight
    assert "direct_allowed = bool(candidate_ffmpeg and candidate_ffprobe)" in preflight
    assert "FRAME_VIDEO_DIRECT_RENDER_ENABLED and not FRAME_VIDEO_REQUIRE_LOCAL_WORKER" not in preflight


def test_framevideo_callback_answer_failure_cannot_surface_generic_x() -> None:
    callback = _source_between(
        "async def handle_frame_video_callback",
        "async def handle_storyboard_callback",
    )
    prologue = callback[: callback.index('    data = query.data or ""')]
    assert "try:" in prologue
    assert "await query.answer()" in prologue
    assert "except Exception as exc:" in prologue
    assert "framevideo callback answer skipped" in prologue


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


def test_assets_done_duration_screen_renders_with_two_real_images() -> None:
    namespace = {
        "normalize_frame_video_state": flow.normalize_state,
        "math": math,
    }
    numeric_helpers = _source_between("def _safe_int", "def video_v6_keyboard")
    duration_renderer = _source_between(
        "def frame_video_duration_menu_text",
        "def frame_video_duration_menu_keyboard",
    )
    exec(compile(numeric_helpers + "\n" + duration_renderer, "bot.py", "exec"), namespace)

    text = namespace["frame_video_duration_menu_text"](
        {
            "commercial_flow_version": "framevideo3",
            "image_count": 2,
            "photos": [{"file_id": "one"}, {"file_id": "two"}],
        }
    )

    assert "Chọn thời lượng mỗi ảnh" in text
    assert "Số ảnh: <b>2</b>" in text
    assert "Chưa chọn" in text
    assert "Nhanh 50 Xu" in text


def test_framevideo3_tail_requires_audio_then_branding_then_review() -> None:
    audio_keyboard = _source_between(
        "def frame_video_audio_menu_keyboard",
        "def frame_video_branding_text",
    )
    branding_keyboard = _source_between(
        "def frame_video_branding_keyboard",
        "def frame_video_branding_confirm_text",
    )
    handler = _source_between(
        "async def handle_frame_video_canonical_callback",
        "async def handle_frame_video_image_regeneration",
    )

    assert 'callback_data="framevideo|audio_done"' in audio_keyboard
    assert 'callback_data="framevideo|audio_skip"' in audio_keyboard
    assert 'callback_data="framevideo|branding|done"' in branding_keyboard
    assert 'callback_data="framevideo|branding|skip"' in branding_keyboard
    assert 'if action in {"audio_done", "addons_done"}:' in handler
    assert 'frame_video_branding_text(state)' in handler
    assert 'if action == "branding":' in handler
    assert 'return await show(frame_video_review_text(state, uid, False)' in handler

    assert flow.FRAME_VIDEO_ROUTE_MATRIX["audio_done"]["screen"] == "branding"
    assert flow.FRAME_VIDEO_ROUTE_MATRIX["audio_skip"]["screen"] == "branding"
    assert flow.FRAME_VIDEO_ROUTE_MATRIX["review"]["back"] == "branding"


def test_framevideo3_branding_is_staged_and_uses_a_position_confirmation() -> None:
    handler = _source_between(
        "async def handle_frame_video_canonical_callback",
        "async def handle_frame_video_image_regeneration",
    )
    media_handler = _source_between(
        "async def handle_frame_video_pending_media",
        "async def handle_frame_video_pending_text",
    )
    text_handler = _source_between(
        "async def handle_frame_video_pending_text",
        "async def render_video_with_audio",
    )
    position_keyboard = _source_between(
        "def frame_video_position_keyboard",
        "def frame_video_quality_keyboard",
    )
    confirm_keyboard = _source_between(
        "def frame_video_branding_confirm_keyboard",
        "def frame_video_text_list_text",
    )

    for callback in (
        "framevideo|branding|logo",
        "framevideo|branding|watermark",
        "framevideo|branding|position|logo",
        "framevideo|branding|position|watermark",
    ):
        assert callback in BOT_SOURCE
    assert 'f"framevideo|branding_confirm|{kind}"' in confirm_keyboard

    assert '"pending_brand_kind": "logo"' in media_handler
    assert '"pending_brand_kind": "watermark"' in text_handler
    assert 'f"{kind}_confirm"' in handler
    assert '"logo_enabled": True' in handler
    assert '"watermark_enabled": True' in handler
    assert "tokens = list(FRAME_VIDEO_POSITION_LABELS)" in position_keyboard
    assert "framevideo|position_set|{kind}|{token}" in position_keyboard
    assert flow.FRAME_VIDEO_ROUTE_MATRIX["branding_confirm"]["screen"] == "branding"


def test_framevideo3_removes_public_ratio_customization_and_legacy_addon_bypass() -> None:
    ratio_keyboard = _source_between(
        "def frame_video_ratio_menu_keyboard",
        "def frame_video_fit_keyboard",
    )
    canonical_handler = _source_between(
        "async def handle_frame_video_canonical_callback",
        "async def handle_frame_video_image_regeneration",
    )

    assert "Tự nhập" not in ratio_keyboard
    assert 'if action == "addons":\n        if is_frame_video3_state(state):' in canonical_handler
    assert 'return await show(frame_video_audio_menu_text(state), frame_video_audio_menu_keyboard(state), "audio")' in canonical_handler
    assert flow.FRAME_VIDEO_ROUTE_MATRIX["addons"]["mutation"] == "legacy_redirect"
