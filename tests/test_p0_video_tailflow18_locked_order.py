from pathlib import Path

from services import video_tail9


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")

SHARED_TAIL_PRODUCTS = (
    "video_ai_real",
    "script_image_video",
    "video_trend",
    "storyboard_prompt",
    "multi_scene_film",
    "self_shot_scene_change",
    "self_shot_cinematic_transform",
)


def _ready_content(product_type: str) -> dict:
    state = video_tail9.new_state(
        product_type=product_type,
        session_id=f"tail18-{product_type}",
        scene_count=5 if product_type == "script_image_video" else 2,
        ratio="9:16",
    )
    return video_tail9.apply_content_contract(
        state,
        {
            "content_source": "manual",
            "selected_prompt": f"Full prompt for {product_type}",
            "plan_approved": True,
        },
    )


def _function_source(name: str) -> str:
    markers = (f"def {name}(", f"async def {name}(")
    starts = [BOT_SOURCE.find(marker) for marker in markers]
    start = min(position for position in starts if position >= 0)
    candidates = [
        position
        for marker in ("\ndef ", "\nasync def ")
        if (position := BOT_SOURCE.find(marker, start + 1)) >= 0
    ]
    end = min(candidates) if candidates else len(BOT_SOURCE)
    return BOT_SOURCE[start:end]


def test_tail18_locks_one_six_screen_order_for_every_shared_product() -> None:
    for product_type in SHARED_TAIL_PRODUCTS:
        state = _ready_content(product_type)
        assert video_tail9.next_required_screen(state) == "addon"

        state = video_tail9.mark_addon_complete(state)
        assert state["audio_status"] in {"configured", "skipped"}
        assert state["logo_status"] in {"configured", "skipped"}
        assert state["watermark_status"] in {"configured", "skipped"}
        assert video_tail9.next_required_screen(state) == "review"

        opened = video_tail9.prepare_review(state)
        assert opened["review_status"] == "not_ready"
        assert video_tail9.next_required_screen(opened) == "review"

        completed = video_tail9.mark_review_complete(opened)
        assert completed["review_status"] == "ready"
        assert video_tail9.next_required_screen(completed) == ""


def test_tail18_bot_exposes_real_addon_and_review_screens_without_summary_alias() -> None:
    assert "def video_tail9_addon_text(" in BOT_SOURCE
    assert "def video_tail9_addon_keyboard(" in BOT_SOURCE
    assert 'if screen == "addon":' in BOT_SOURCE
    assert 'if section == "addon":' in BOT_SOURCE
    assert '("✅ Hoàn tất Add-on", "video_tail|addon|complete")' in BOT_SOURCE
    assert '("✅ Hoàn tất rà soát", "video_tail|review|complete")' in BOT_SOURCE
    assert '("⬅️ Quay lại Add-on", "video_tail|review|back")' in BOT_SOURCE
    assert 'return video_tail9_summary_text(tail)' not in BOT_SOURCE
    assert 'return video_tail9_summary_keyboard(tail)' not in BOT_SOURCE


def test_tail18_bridges_enter_addon_before_quality_or_invoice() -> None:
    uiflow3 = _function_source("handle_video_uiflow3_callback")
    script = _function_source("video_profile_scene1_open_selected_tail_invoice")
    selfshot = _function_source("video_selfshotflow4_handle_result")

    product_tail = uiflow3[uiflow3.index('if route["kind"] == "product_tail"') :]
    assert '"review" if tail_return_screen == "review" else "addon"' in product_tail
    assert product_tail.index('else "addon"') < product_tail.index('elif creation_flow')

    assert 'return await video_tail9_render(query, user_id, context, "addon")' in script
    assert 'video_tail9_render(query, user_id, context, "invoice")' not in script

    assert '"addon" if return_to_addon else "review"' in selfshot
