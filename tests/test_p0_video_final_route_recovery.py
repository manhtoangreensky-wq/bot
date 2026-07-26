from __future__ import annotations

import ast
import re
from pathlib import Path

from services import video_idea_catalog, video_idea_script_intake, video_local_validation, video_scene3_flow


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    pattern = re.compile(rf"^(?:async )?def {re.escape(name)}\(", re.MULTILINE)
    match = pattern.search(BOT_SOURCE)
    assert match, f"missing function: {name}"
    next_match = re.search(r"\n(?:async )?def [A-Za-z_]", BOT_SOURCE[match.end() :])
    end = match.end() + next_match.start() if next_match else len(BOT_SOURCE)
    return BOT_SOURCE[match.start() : end]


def _compile_function(name: str, namespace: dict):
    module = ast.parse("from __future__ import annotations\n\n" + _function_source(name))
    exec(compile(module, filename="bot.py", mode="exec"), namespace)
    return namespace[name]


def _safe_int(value, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def test_embedded_idea_builds_semantic_drafts_before_scene3_quality_gate() -> None:
    build = _compile_function(
        "video_idea_dynamic_scene3_state",
        {
            "safe_int": _safe_int,
            "video_idea_catalog": video_idea_catalog,
            "video_idea_script_intake": video_idea_script_intake,
            "video_scene3_flow": video_scene3_flow,
        },
    )
    preset = {
        "preset_key": "proof-before-after",
        "title": "Trước và sau có bằng chứng",
        "description": "Mở vấn đề, thực hiện giải pháp và khép bằng kết quả.",
        "category": "sales",
        "recommended_profile_id": "cinematic_product",
        "recommended_aspect_ratio": "16:9",
        "video_prompt_seed": "Giữ cùng chủ thể và nối hành động tự nhiên.",
    }
    state = {
        "idea_preset": preset,
        "idea_preset_content": preset,
        "idea_preset_id": 496,
        "idea_id": preset["preset_key"],
        "idea_title": preset["title"],
        "subject": preset["title"],
        "scene_count": 2,
        "recommended_aspect_ratio": "16:9",
        "idea_selected_prompt": "Mạch kể rõ, cảnh cuối phải khép bằng kết quả nhìn thấy được.",
        # This is the legacy content-only shape that caused the live quality gate failure.
        "scene_drafts": [
            {"scene_index": 1, "content": "Mở vấn đề"},
            {"scene_index": 2, "content": "Khép bằng kết quả"},
        ],
    }

    result = build(state, origin_product="video_ai_real")

    drafts = result["scene_drafts"]
    assert len(drafts) == 2
    assert all(item.get("goal") and item.get("start_state") and item.get("end_state") for item in drafts)
    assert drafts[0]["goal"] != drafts[1]["goal"]
    assert "khép lại" in drafts[-1]["end_state"].lower()
    assert result["scene_count"] == 2
    assert result["job_created"] is False
    assert result["provider_called"] is False
    assert result["xu_charged"] == 0


def test_storyboard_finish_enters_canonical_branding_not_legacy_scene3() -> None:
    handler = _function_source("_handle_storyboard2_callback_impl")
    finish = handler[handler.index('if action == "finish":') : handler.index("if action in deferred_answer_actions")]
    assert "storyboard2_scene3_handoff(context, board)" in finish
    assert 'video_tail9_render(query, uid, context, "logo")' in finish
    assert "video_profile_scene1_render" not in finish


def test_long_video_public_entry_has_one_direct_owner() -> None:
    handler = _function_source("handle_long_video_callback")
    branch_start = handler.index('if action == "public_guard":')
    first_answer = handler.index("await query.answer()", branch_start)
    second_answer = handler.index("await query.answer()", first_answer + 1)
    public_entry = handler[branch_start:second_answer]
    assert "start_public_video_scene2_step" in public_entry
    assert '"multi_scene_film"' in public_entry
    assert "handle_video_product_callback" not in public_entry
    assert "query.data =" not in public_entry


def test_video_edit_uses_telegram_video_metadata_only_for_probe_infrastructure_failure() -> None:
    fallback = _compile_function(
        "video_editor_telegram_probe_fallback",
        {"safe_int": _safe_int, "video_local_validation": video_local_validation},
    )
    source = {
        "source_origin": "telegram_video",
        "source_file_size": 2_000_000,
        "source_duration": 18,
        "source_width": 852,
        "source_height": 480,
    }

    result = fallback(source, "ffprobe_failed")
    assert result["ok"] is True
    assert result["duration_ms"] == 18_000
    assert result["width"] == 852
    assert result["probe_fallback"] == "telegram_video_metadata"
    assert fallback({**source, "source_origin": "telegram_document"}, "ffprobe_failed") == {}
    assert fallback(source, "input_zero_bytes") == {}


def test_video_edit_intake_preserves_telegram_envelope_and_runs_fallback_before_error() -> None:
    extractor = _function_source("video_editor_source_from_update")
    handler = _function_source("handle_video_editor_pending_upload")
    assert '"source_origin": "telegram_video" if telegram_video else "telegram_document"' in extractor
    assert '"source_width"' in extractor
    assert '"source_height"' in extractor
    fallback_at = handler.index("video_editor_telegram_probe_fallback")
    invalid_at = handler.index('reason = str(metadata.get("reason") or "invalid_video")')
    assert fallback_at < invalid_at
