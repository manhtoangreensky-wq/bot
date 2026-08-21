from __future__ import annotations

import html
import math
import re
from pathlib import Path
from types import SimpleNamespace

from services import (
    video_ai_real_pricing,
    video_selfshot2,
    video_selfshot3,
    video_selfshotflow4,
    video_tail9,
    video_uifreeze1,
)


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")
FORBIDDEN_PUBLIC_COPY = (
    "chưa tạo tác vụ",
    "chưa trừ Xu",
    "chưa xử lý video",
    "chưa tạo file",
    "chưa tạo tệp",
    "chưa gọi nguồn dựng",
)


def _function_source(name: str) -> str:
    pattern = re.compile(rf"^(?:async )?def {re.escape(name)}\(", re.MULTILINE)
    match = pattern.search(BOT_SOURCE)
    assert match, f"missing function: {name}"
    next_match = re.search(r"\n(?=@|(?:async )?def [A-Za-z_])", BOT_SOURCE[match.end() :])
    end = match.end() + next_match.start() if next_match else len(BOT_SOURCE)
    return BOT_SOURCE[match.start() : end]


def _between(start: str, end: str) -> str:
    left = BOT_SOURCE.index(start)
    right = BOT_SOURCE.index(end, left + len(start))
    return BOT_SOURCE[left:right]


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _selfshot4_state(flow: str) -> dict:
    return {
        video_selfshotflow4.FLOW_FLAGS[flow]: True,
        video_selfshotflow4.FLOW_SCREEN_KEYS[flow]: "segment",
        "session_id": f"{flow}-final-ui",
        "revision": 2,
        "source_revision": 1,
        "source_asset": {
            "file_id": f"{flow}-source",
            "duration_seconds": 30,
            "width": 1080,
            "height": 1920,
            "audio_streams": 1,
        },
        "source_video_id": f"{flow}-source",
        "source_analysis": {
            "source_hash": f"{flow}-hash",
            "duration_seconds": 30,
            "width": 1080,
            "height": 1920,
            "audio_manifest": {"stream_count": 1},
            "person_tracks": [
                {"subject_id": "person-1", "subject_type": "person", "label": "Người 1"},
                {"subject_id": "person-2", "subject_type": "person", "label": "Người 2"},
            ],
            "object_tracks": [
                {"subject_id": "object-1", "subject_type": "object", "label": "Sản phẩm"},
            ],
            "pet_tracks": [],
            "relationship_candidates": [],
        },
        "source_ratio": "9:16",
        "idea_group_id": video_selfshotflow4.idea_groups()[0]["category_id"],
    }


def _selfshot2_review_state() -> dict:
    state = video_selfshot2.initial_draft()
    state.update(
        {
            "selfshot2_screen": "review",
            "scene_count": 3,
            "aspect_ratio": "9:16",
            "subject_manifest": {
                "selection_type": "person_object",
                "subject_ids": ["person-1", "object-1"],
            },
            "selected_content": {"title": "Giới thiệu sản phẩm"},
            "direction_contract": {"label": "Đổi bối cảnh"},
            "video_prompts": [{"scene_index": 1, "prompt": "Giữ chủ thể."}],
        }
    )
    return state


def test_selfshot2_review_callbacks_are_unique_and_enters_only_shared_addon() -> None:
    state = _selfshot2_review_state()
    model = video_selfshot2.screen_model("review", state)
    callbacks = [callback for row in model["rows"] for _label, callback in row]

    assert len(callbacks) == len(set(callbacks))
    assert callbacks.count("vproduct|ss2|finish") == 1
    assert "vproduct|ss2|review_addons" not in callbacks
    assert video_selfshot2.validate_rows(
        model["rows"],
        back_callback="vproduct|ss2|show|prompts",
    )["ok"] is True

    ss2 = _between('if action == "ss2":', 'if action == "ss3":')
    ss3 = _between('if action == "ss3":', 'if product_id == video_selfshot2.PRODUCT_ID:')
    for block in (ss2, ss3):
        finish_start = block.index('if operation == "finish":')
        finish = block[finish_start : block.index('if operation == "source":', finish_start)]
        assert 'video_tail9_render(query, uid, context, "addon")' in finish
        assert 'video_tail9_render(query, uid, context, "logo")' not in finish
        assert 'video_tail9_render(query, uid, context, "summary")' not in finish
        assert 'video_tail9_render(query, uid, context, "quality")' not in finish


def test_every_canonical_selfshot_screen_has_unique_callbacks() -> None:
    for flow in ("ss2", "ss3"):
        state = _selfshot4_state(flow)
        for screen in sorted(video_selfshotflow4.FLOW_SCREENS[flow]):
            state[video_selfshotflow4.FLOW_SCREEN_KEYS[flow]] = screen
            model = video_selfshotflow4.screen_model(flow, screen, state)
            callbacks = [callback for row in model["rows"] for _label, callback in row]
            assert len(callbacks) == len(set(callbacks)), (flow, screen, callbacks)
            assert video_selfshotflow4.validate_rows(
                model["rows"],
                back_callback=video_selfshotflow4.back_callback(flow, screen, state),
            )["ok"] is True


def test_selfshot_idea_buttons_have_icons_without_changing_callback_ids() -> None:
    for flow in ("ss2", "ss3"):
        state = _selfshot4_state(flow)
        state[video_selfshotflow4.FLOW_SCREEN_KEYS[flow]] = "ideas"
        model = video_selfshotflow4.screen_model(flow, "ideas", state)
        idea_buttons = [
            (label, callback)
            for row in model["rows"]
            for label, callback in row
            if f"vproduct|{flow}|c4idea|" in callback
        ]
        assert idea_buttons
        assert all(label.startswith(("💡 ", "✅ 💡 ")) for label, _callback in idea_buttons)


def test_selfshot_public_screens_do_not_expose_internal_side_effect_copy() -> None:
    canonical = _selfshot4_state("ss2")
    public_texts = [
        video_selfshotflow4.screen_model("ss2", "segment", canonical)["text"],
        video_selfshotflow4.screen_model("ss2", "content_view", canonical)["text"],
    ]

    ss2 = _selfshot2_review_state()
    public_texts.extend(
        video_selfshot2.screen_model(screen, ss2)["text"]
        for screen in ("intro", "direction", "addons", "review")
    )

    ss3 = video_selfshot3.initial_draft()
    ss3.update(
        {
            "source_segment": {"start_ms": 0, "end_ms": 30000, "duration_ms": 30000},
            "source_analysis": {"duration_seconds": 30, "width": 1080, "height": 1920},
            "selected_preset": {"title": "Biến đổi điện ảnh"},
            "transformation_stages": [{"title": "Giai đoạn 1"}],
            "subject_manifest": {"selection_type": "person"},
        }
    )
    public_texts.extend(
        video_selfshot3.screen_model(screen, ss3)["text"]
        for screen in ("intro", "analysis", "segment_preview", "review", "finish")
    )
    public_texts.append(_function_source("video_selfshot_product_hub_text"))
    public_texts.append(_function_source("video_selfshotflow4_request_source"))
    public_texts.append(_function_source("video_selfshot3_render_prompt_review"))

    for public_text in public_texts:
        for fragment in FORBIDDEN_PUBLIC_COPY:
            assert fragment not in public_text


def test_selfshot_hub_has_one_exact_return_to_video_menu() -> None:
    source = _function_source("video_selfshot_product_hub_keyboard")
    assert source.count('"menu|main_video"') == 1
    assert '("🏠 Menu chính", "menu|main")' not in source


def test_selfshot2_has_scene_and_ratio_but_selfshot3_defers_billable_scenes() -> None:
    assert video_selfshot2.SCREEN_PARENTS["scene_count"] == "preserve"
    assert video_selfshot2.SCREEN_PARENTS["ratio"] == "scene_count"
    assert video_selfshot2.SCREEN_PARENTS["content_source"] == "ratio"
    assert "scene_count" not in video_selfshot3.SCREEN_PARENTS
    assert "ratio" not in video_selfshot3.SCREEN_PARENTS

    state = _selfshot4_state("ss3")
    selected = video_selfshotflow4.apply_action("ss3", state, "c4segment", "whole")["state"]
    assert "scene_count" not in selected
    assert selected["scene_count_deferred_to_quality"] is True

    selected["subject_manifest"] = {
        "selection_type": "person",
        "subjects": [{"subject_id": "person-1", "subject_type": "person", "label": "Người 1"}],
        "selected_ids": ["person-1"],
        "description": "Người 1",
    }
    selected["selected_content"] = {
        "id": "cinematic",
        "title": "Biến đổi điện ảnh",
        "summary": "Giữ chủ thể và biến đổi môi trường.",
    }
    compiled = video_selfshotflow4.compile_selfshot3_content(selected)
    assert len(compiled["scene_plan"]) == 1
    assert "scene_count" not in compiled
    assert compiled["scene_count_deferred_to_quality"] is True


def _load_selfshot3_catalog_report():
    helper_namespace = {
        "math": math,
        "safe_int": _safe_int,
        "video_selfshot3": SimpleNamespace(PRODUCT_ID=video_selfshot3.PRODUCT_ID),
        "video_public_quality_product": lambda tier_id: {
            "seconds": 5 if int(tier_id) == 200 else 8,
        },
    }
    exec(
        "from __future__ import annotations\n"
        + _function_source("video_selfshot3_scene_count_for_quality"),
        helper_namespace,
    )
    namespace = {
        "safe_int": _safe_int,
        "video_editengine1": SimpleNamespace(
            PRODUCT_TYPE="video_local_edit",
            WORKER_JOB_TYPE="video_local_edit",
        ),
        "video_selfshot3": SimpleNamespace(PRODUCT_ID=video_selfshot3.PRODUCT_ID),
        "video_selfshot3_scene_count_for_quality": helper_namespace[
            "video_selfshot3_scene_count_for_quality"
        ],
        "video_tail9": video_tail9,
        "video_uifreeze1": video_uifreeze1,
    }
    exec(
        "from __future__ import annotations\n" + _function_source("video_tail9_catalog_report"),
        namespace,
    )
    return namespace["video_tail9_catalog_report"]


def test_selfshot3_quality_catalog_uses_effective_scene_count_per_tier() -> None:
    catalog_report = _load_selfshot3_catalog_report()
    report = catalog_report(
        {
            "video_product_type": video_selfshot3.PRODUCT_ID,
            "scene_count": 1,
            "source_duration_seconds": 30,
            "estimated_duration": 30,
            "ratio": "9:16",
        }
    )

    assert report["ok"] is True
    assert 200 not in report["tier_ids"]
    assert all(int(item["effective_scene_count"]) > 1 for item in report["offers"])


def test_selfshot3_quality_copy_never_claims_one_scene_before_tier_selection() -> None:
    namespace = {
        "html": html,
        "safe_int": _safe_int,
        "VIDEO_TAIL9_PRODUCT_LABELS": {
            video_selfshot3.PRODUCT_ID: "Tự quay & biến đổi điện ảnh",
        },
        "video_tail9_catalog_report": lambda *_args, **_kwargs: {},
        "video_tail9_duration_label": lambda _tail: "30 giây",
        "video_public_quality_product": lambda _tier: {
            "seconds": 8,
            "icon": "⭐",
            "name": "Cơ bản",
            "unit_xu": 300,
            "public_level": "Tốt",
            "resolution": "HD",
            "public_detail": "Video rõ nét",
            "use_case": "Mạng xã hội",
        },
        "video_selfshot3": SimpleNamespace(PRODUCT_ID=video_selfshot3.PRODUCT_ID),
        "video_selfshot3_scene_count_for_quality": lambda _tail, _tier: 4,
        "video_ai_real_pricing": video_ai_real_pricing,
    }
    exec(
        "from __future__ import annotations\n" + _function_source("video_tail9_quality_text"),
        namespace,
    )
    text = namespace["video_tail9_quality_text"](
        {
            "video_product_type": video_selfshot3.PRODUCT_ID,
            "scene_count": 1,
            "ratio": "9:16",
        },
        {"ok": True},
        {"ok": True, "offers": [{"tier_id": 300}]},
    )

    assert "Số cảnh: <b>Tính theo gói và thời lượng nguồn</b>" in text
    assert "Số cảnh: <b>1</b>" not in text
    assert "Tạm tính 4 cảnh" in text


def test_selfshot_golden_contract_ends_in_exact_shared_six_step_tail() -> None:
    expected_tail = ("addon", "review", "quality", "invoice", "confirm", "status")
    assert video_selfshotflow4.SELF_SHOT_2_GOLDEN_FLOW[-6:] == expected_tail
    assert video_selfshotflow4.SELF_SHOT_3_GOLDEN_FLOW[-6:] == expected_tail
