from pathlib import Path


def _function_block(source: str, name: str) -> str:
    start = source.index(f"def {name}(")
    candidates = [
        position
        for marker in ("\ndef ", "\nasync def ")
        if (position := source.find(marker, start + 1)) >= 0
    ]
    end = min(candidates) if candidates else len(source)
    return source[start:end]


def test_video_status_panel_joins_lines_with_real_newlines():
    source = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")
    rendering_block = source[
        source.index("def video_b14_provider_rendering_block("):
        source.index("def video_b14_primary_alive_attempt(")
    ]
    status_block = source[
        source.index("def video_b14_queue_status_text("):
        source.index("def video_b14_queue_status_keyboard(")
    ]

    for block in (rendering_block, status_block):
        assert '"\\\\n".join(lines)' not in block
        assert '"\\n".join(lines)' in block


def test_frame_and_storyboard_live_renderers_use_real_newlines():
    source = (Path(__file__).resolve().parents[1] / "bot.py").read_text(
        encoding="utf-8"
    )
    renderer_names = (
        "frame_video_job_status_text",
        "frame_video_images_text",
        "frame_video_text_list_text",
        "frame_video_quality_text",
        "frame_video_review_text",
        "frame_video_planning_text",
        "storyboard_scripts_text",
        "storyboard_text",
    )

    offenders = [
        name
        for name in renderer_names
        if r"\\n" in _function_block(source, name)
    ]

    assert offenders == []


def test_shared_tail_keeps_review_invoice_confirm_status_order():
    source = (Path(__file__).resolve().parents[1] / "bot.py").read_text(
        encoding="utf-8"
    )
    invoice_keyboard = _function_block(source, "video_tail9_invoice_keyboard")
    tail_callback = _function_block(source, "handle_video_tail_callback")
    quality_start = tail_callback.index('if section == "quality":')
    confirm_start = tail_callback.index('if section == "confirm":')
    quality_block = tail_callback[quality_start:confirm_start]
    confirm_block = tail_callback[confirm_start:]
    confirm_open = confirm_block[
        confirm_block.index('if action == "open":'):
        confirm_block.index('if action == "back":')
    ]

    assert '"video_tail|confirm|open"' in invoice_keyboard
    assert '"video_tail|confirm|submit"' not in invoice_keyboard
    assert 'back_dest = "review"' in quality_block
    assert 'if product_type in {"multi_scene_film", "video_long"}:' not in (
        confirm_open
    )
