from __future__ import annotations

import io
import re
from pathlib import Path
import zipfile

import pytest

from providers import gemini_public_chat_provider
from services import video_flow6, video_flow7, video_script_product


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    markers = (f"def {name}(", f"async def {name}(")
    positions = [BOT_SOURCE.find(marker) for marker in markers]
    start = min(position for position in positions if position >= 0)
    next_def = re.search(r"\n(?:async )?def [A-Za-z_]", BOT_SOURCE[start + 1 :])
    end = start + 1 + next_def.start() if next_def else len(BOT_SOURCE)
    return BOT_SOURCE[start:end]


def _ready_context(product_id: str) -> dict:
    return {
        "scene_count": 2,
        "aspect_ratio": "9:16",
        "primary_profile_key": "character_people",
        "content_choice": {"id": "content-1", "title": "Noi dung da chon"},
    }


def _preflight(product_id: str, context: dict) -> dict:
    return video_flow7.preflight(
        product_id,
        context,
        owner_ready=True,
        worker_ready=True,
        capability_ready=True,
        package_available=True,
        provider_healthy=True,
        storage_ready=True,
        delivery_ready=True,
    )


@pytest.mark.parametrize(
    ("product_id", "kind", "route", "job_type"),
    (
        ("video_ai_real", "ai_real", "product_video_catalog", "product_video"),
        ("video_idea", "idea_video", "preset_planner_to_product_video", "product_video"),
        ("script_image_video", "script_to_video", "parsed_scene_plan_to_product_video", "product_video"),
        ("storyboard_prompt", "storyboard", "storyboard_to_video", "storyboard_to_video"),
        ("self_shot_scene_change", "self_shot", "self_shot_scene_change", "self_shot_scene_change"),
        ("multi_scene_film", "long_series", "long_series_episode_queue", "long_series_project"),
        ("video_trend", "trend_video", "trend_preset_to_product_video", "product_video"),
    ),
)
def test_product_kinds_keep_distinct_execution_contracts(
    product_id: str,
    kind: str,
    route: str,
    job_type: str,
) -> None:
    assert video_flow7.product_kind(product_id) == kind
    execution = video_flow7.execution_route(product_id)
    assert execution["product_kind"] == kind
    assert execution["provider_or_local_route"] == route
    assert execution["job_type"] == job_type
    assert execution["preflight"] == "required_before_invoice"
    assert execution["charge_contract"] == "charge_once_after_delivery_receipt"


def test_product_sequences_are_not_one_shared_wizard() -> None:
    assert video_flow7.product_sequence("video_ai_real")[:4] == (
        "scene_count",
        "aspect_ratio",
        "ai_input_type",
        "content_source",
    )
    assert video_flow7.product_sequence("video_idea")[:4] == (
        "scene_count",
        "aspect_ratio",
        "idea_category",
        "idea_preset",
    )
    assert video_flow7.product_sequence("script_image_video")[:3] == (
        "scene_count",
        "aspect_ratio",
        "content_source",
    )
    assert "scene_count_confirm" not in video_flow7.product_sequence("script_image_video")
    assert video_flow7.product_sequence("storyboard_prompt")[:5] == (
        "panel_count",
        "aspect_ratio",
        "storyboard_source",
        "panel_images",
        "panel_mapping",
    )
    assert video_flow7.product_sequence("self_shot_scene_change")[:6] == (
        "source_video",
        "source_analysis",
        "subject_selection",
        "preserve_constraints",
        "scene_count",
        "aspect_ratio",
    )
    assert video_flow7.product_sequence("video_trend")[0] == "trend_source"
    assert video_flow7.product_sequence("multi_scene_film")[0] == "series_bible"


@pytest.mark.parametrize(
    "product_id",
    (
        "video_ai_real",
        "video_trend",
        "script_image_video",
        "storyboard_prompt",
        "self_shot_scene_change",
        "video_idea",
        "multi_scene_film",
    ),
)
def test_entry_keyboards_have_two_columns_unique_callbacks_and_bottom_navigation(
    product_id: str,
) -> None:
    rows = video_flow7.entry_rows(product_id)
    rows.append(video_flow7.bottom_navigation("menu|main_video"))
    result = video_flow7.validate_rows(rows, expected_back="menu|main_video")
    assert result["ok"] is True
    assert len(result["callbacks"]) == len(set(result["callbacks"]))


def test_review_keyboard_has_exact_rows_and_finish_label() -> None:
    assert video_flow7.review_rows() == [
        [("👁️ Xem cảnh", "vprofile|scene_view|1"), ("✍️ Sửa cảnh", "vprofile|edit_scene")],
        [("🎬 Prompt video", "vprofile|review_video_prompts"), ("🔗 Chuyển cảnh", "vprofile|review_transitions")],
        [("📝 Chữ", "vprofile|review_text"), ("🎚️ Âm thanh", "vprofile|review_audio")],
        [("🖼️ Logo/Watermark", "vprofile|review_post"), ("⭐ Hoàn thiện video", "vprofile|review_continue")],
    ]
    rows = video_flow7.review_rows()
    rows.append(video_flow7.bottom_navigation("vprofile|back"))
    assert video_flow7.validate_rows(rows, expected_back="vprofile|back")["ok"] is True
    keyboard_source = _function_source("video_scene3_full_review_keyboard")
    for label in (
        "Xem cảnh",
        "Sửa cảnh",
        "Prompt video",
        "Chuyển cảnh",
        "Chữ",
        "Âm thanh",
        "Logo/Watermark",
        "Hoàn thiện video",
    ):
        assert label in keyboard_source


def test_suggestion_catalog_has_twenty_contextual_single_select_items() -> None:
    items = video_flow7.suggestion_catalog(
        "video_ai_real",
        profile_label="Nhan vat",
        scene_count=20,
        aspect_ratio="16:9",
    )
    assert len(items) == 20
    assert len({item["id"] for item in items}) == 20
    assert all("20 cảnh 16:9" in item["content"] for item in items)
    assert [item["id"] for item in video_flow7.suggestion_page(items, 4)] == [
        item["id"] for item in items[15:20]
    ]
    selected = video_flow7.select_single(items, items[7]["id"])
    assert [item["id"] for item in selected if item["selected"]] == [items[7]["id"]]


def test_script_parser_preserves_source_and_requires_explicit_count_confirmation() -> None:
    proposal = video_flow7.parse_script_proposal("Mo dau tron y\nHanh dong tron y\nKet thuc tron y")
    assert proposal["coverage"]["no_truncation"] is True
    assert proposal["coverage"]["exact_match"] is True
    assert proposal["coverage"]["coverage_percent"] == 100
    assert proposal["proposed_scene_count"] == 3
    assert proposal["scene_count_confirmed"] is False
    context = _ready_context("script_image_video")
    context.update({
        "scene_count": 3,
        "script_text": proposal["source_text"],
        "manual_script_raw": proposal["source_text"],
        "parsed_script_scenes": proposal["proposed_scenes"],
        "parsed_script_ranges": proposal["scene_ranges"],
        "script_coverage": proposal["coverage"],
        "scene_count_confirmed": False,
    })
    blocked = _preflight("script_image_video", context)
    assert "script_scene_count_not_confirmed" in blocked["blockers"]
    context["scene_count_confirmed"] = True
    assert _preflight("script_image_video", context)["ok"] is True
    context["parsed_script_scenes"][1] += " sai"
    assert "script_coverage_incomplete" in _preflight("script_image_video", context)["blockers"]

    restored = video_script_product.parse_script(proposal["source_text"])
    context["parsed_script_scenes"] = list(restored["proposed_scenes"])
    contract = video_script_product.state_contract(context)
    assert contract["script_text"] == proposal["source_text"]
    assert contract["manual_script_raw"] == proposal["source_text"]
    assert contract["parsed_script_ranges"] == proposal["scene_ranges"]
    assert contract["script_coverage"]["coverage_percent"] == 100
    assert contract["scene_count_confirmed"] is True
    assert not any(key.startswith("script_execution_") for key in contract)


def test_script_ai_adapter_requests_one_complete_script_not_a_lite_prompt_pack() -> None:
    source = _function_source("generate_video_script_pack")
    caller_source = _function_source("video_script_generate_ai")
    assert gemini_public_chat_provider.GEMINI_FREE_MODEL == "gemini-3.6-flash"
    assert "GeminiPublicChatProvider" in source
    assert "AgentGemini.chat" not in source
    assert "await generate_video_script_pack" in caller_source
    assert "to_thread(generate_video_script_pack" not in caller_source
    assert "biên kịch Video AI chuyên sâu" in source
    assert "MỘT KỊCH BẢN HOÀN CHỈNH" in source
    assert "Script Lite" not in source


def test_script_parser_merges_more_than_twenty_headings_without_losing_text() -> None:
    source = "\n".join(f"Cảnh {index}: Nội dung nguyên văn {index}." for index in range(1, 26))
    proposal = video_script_product.parse_script(source)
    assert proposal.get("error") in (None, "")
    assert proposal["proposed_scene_count"] == video_script_product.MAX_SCENES
    assert "".join(proposal["proposed_scenes"]) == source
    assert proposal["coverage"]["exact_match"] is True
    assert proposal["coverage"]["coverage_percent"] == 100


def test_docx_extractor_keeps_table_header_footer_and_textbox_text() -> None:
    document_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        <w:p><w:r><w:t>Đoạn chính</w:t></w:r></w:p>
        <w:tbl><w:tr>
          <w:tc><w:p><w:r><w:t>Ô bảng A</w:t></w:r></w:p></w:tc>
          <w:tc><w:p><w:r><w:t>Ô bảng B</w:t></w:r></w:p></w:tc>
        </w:tr></w:tbl>
        <w:p><w:r><w:pict><w:txbxContent><w:p><w:r><w:t>Chữ trong hộp</w:t></w:r></w:p></w:txbxContent></w:pict></w:r></w:p>
      </w:body>
    </w:document>"""
    header_xml = """<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p><w:r><w:t>Đầu trang</w:t></w:r></w:p></w:hdr>"""
    footer_xml = """<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p><w:r><w:t>Chân trang</w:t></w:r></w:p></w:ftr>"""
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("word/document.xml", document_xml)
        archive.writestr("word/header1.xml", header_xml)
        archive.writestr("word/footer1.xml", footer_xml)

    extracted = video_script_product.extract_docx_text(payload.getvalue())
    for expected in ("Đoạn chính", "Ô bảng A", "Ô bảng B", "Chữ trong hộp", "Đầu trang", "Chân trang"):
        assert expected in extracted


def test_storyboard_requires_one_mapped_image_per_panel_and_n_minus_one_transitions() -> None:
    partial = video_flow7.storyboard_asset_gate(
        3,
        [
            {"file_id": "panel-1", "scene_index": 1},
            {"file_id": "panel-3", "scene_index": 3},
        ],
    )
    assert partial["ok"] is False
    assert partial["missing_panels"] == [2]
    assert partial["blocker"] == "storyboard_panel_images_missing"

    context = _ready_context("storyboard_prompt")
    context["asset_items"] = [
        {"file_id": "panel-1", "scene_index": 1},
        {"file_id": "panel-2", "scene_index": 2},
    ]
    context["transitions"] = [{"from": 1, "to": 2, "type": "action_cut"}]
    assert _preflight("storyboard_prompt", context)["ok"] is True
    context["transitions"] = []
    assert "storyboard_transition_count_invalid" in _preflight("storyboard_prompt", context)["blockers"]


def test_self_shot_requires_real_source_video_and_complete_local_probe() -> None:
    missing_probe = video_flow7.self_shot_asset_gate({"file_id": "video-1"}, {})
    assert missing_probe == {
        "ok": False,
        "source_received": True,
        "probe_complete": False,
        "blocker": "source_video_probe_missing",
    }
    context = _ready_context("self_shot_scene_change")
    context.update(
        {
            "source_video": {"file_id": "video-1"},
            "source_probe": {
                "duration_seconds": 18,
                "width": 1080,
                "height": 1920,
                "format": "video/mp4",
            },
        }
    )
    assert _preflight("self_shot_scene_change", context)["ok"] is True


def test_trend_requires_observed_source_or_explicit_sample() -> None:
    context = _ready_context("video_trend")
    blocked = _preflight("video_trend", context)
    assert blocked["blocker"] == "trend_source_or_sample_missing"
    context["trend_source"] = {
        "source_url": "https://example.test/trend",
        "observed_at": "2026-07-18T00:00:00Z",
    }
    assert _preflight("video_trend", context)["ok"] is True
    context["trend_source"] = {"sample_preset": "sample-1"}
    assert _preflight("video_trend", context)["ok"] is True


def test_flow6_keeps_trend_source_from_persisted_source_fields() -> None:
    context = video_flow6.context_from_scene_state(
        {
            "source_product_id": "video_trend",
            "scene_count": 2,
            "aspect_ratio": "9:16",
            "source_fields": {
                "selected_trend_source": {
                    "source_url": "https://example.test/trend",
                    "observed_at": "2026-07-18",
                }
            },
        }
    )
    assert context["trend_source"]["source_url"] == "https://example.test/trend"
    assert context["source_fields"]["selected_trend_source"]["observed_at"] == "2026-07-18"


def test_long_series_stays_development_only_and_cannot_enter_short_video_preflight() -> None:
    context = {
        "aspect_ratio": "16:9",
        "series_bible": "Series bible",
    }
    blocked = _preflight("multi_scene_film", context)
    assert "long_series_public_not_ready" in blocked["blockers"]
    entry_callbacks = [
        callback
        for row in video_flow7.entry_rows("multi_scene_film")
        for _label, callback in row
    ]
    assert "longvideo|public_guard" in entry_callbacks


@pytest.mark.parametrize(
    ("product_id", "context"),
    (
        ("video_ai_real", _ready_context("video_ai_real")),
        (
            "video_idea",
            {
                **_ready_context("video_idea"),
                "idea_preset_id": "idea-1",
            },
        ),
        (
            "script_image_video",
            {
                **_ready_context("script_image_video"),
                "script_text": "Canh 1\nCanh 2",
                "scene_count_confirmed": True,
            },
        ),
    ),
)
def test_ready_short_video_flows_pass_without_side_effects(
    product_id: str,
    context: dict,
) -> None:
    result = _preflight(product_id, context)
    assert result["ok"] is True
    assert set(result["side_effects"].values()) == {0}


def test_blocked_preflight_always_reports_zero_side_effects() -> None:
    result = video_flow7.preflight(
        "video_ai_real",
        {},
        owner_ready=False,
        worker_ready=False,
        capability_ready=False,
        package_available=False,
        provider_healthy=False,
        storage_ready=False,
        delivery_ready=False,
    )
    assert result["ok"] is False
    assert set(result["side_effects"].values()) == {0}
    assert result["side_effects"]["provider_calls"] == 0
    assert result["side_effects"]["wallet_mutations"] == 0
    assert result["side_effects"]["xu_charged"] == 0


def test_delivery_receipt_is_required_idempotent_and_precedes_charge() -> None:
    with pytest.raises(ValueError, match="valid_delivery_receipt_required"):
        video_flow7.record_delivery({}, message_id=0, receipt_key="")
    delivered = video_flow7.record_delivery({}, message_id=991, receipt_key="job:991")
    assert video_flow7.charge_allowed(delivered) is True
    assert video_flow7.record_delivery(delivered, message_id=991, receipt_key="job:991") == delivered
    with pytest.raises(ValueError, match="delivery_receipt_conflict"):
        video_flow7.record_delivery(delivered, message_id=992, receipt_key="job:992")


def test_back_matrix_is_exact_for_every_product_sequence() -> None:
    for product_id in video_flow7.PRODUCT_KIND_BY_ID:
        sequence = video_flow7.product_sequence(product_id)
        matrix = video_flow7.back_matrix(product_id)
        assert matrix[sequence[0]] == "product_intro"
        for index in range(1, len(sequence)):
            assert matrix[sequence[index]] == sequence[index - 1]


def test_bot_routes_storyboard_self_shot_and_trend_without_generic_profile_fallthrough() -> None:
    after_ratio = _function_source("video_flow7_after_ratio")
    assert 'flow_kind in {"script_to_video", "trend_video"}' in after_ratio
    assert 'return updated, "content_source"' in after_ratio
    assert 'return updated, "ai_input_type"' in after_ratio
    assert 'video_scene3_flow.build_planning_package' not in after_ratio
    assert "video_flow6.next_after_ratio" in after_ratio

    character_route = _function_source("video_flow7_after_character_step")
    assert 'video_flow7_kind(state) == "self_shot"' in character_route
    assert 'return "requirements"' in character_route

    handler = _function_source("handle_video_profile_studio_callback")
    asset_done = handler.split('if action == "asset_done":', 1)[1].split(
        'if action in {"ctype"', 1
    )[0]
    assert 'if flow_kind == "storyboard":' in asset_done
    assert 'elif flow_kind == "self_shot":' in asset_done
    assert 'state = video_profile_studio_step(context, state, "technical_profile")' in asset_done
    assert 'target = "transitions" if video_flow7_kind(state) == "storyboard" else "full_review"' in handler


def test_storyboard_image_ai_handoff_returns_to_asset_gate_and_normal_failure_to_source() -> None:
    target = _function_source("video_scene3_image_handoff_target_step")
    panel = _function_source("video_scene3_image_handoff_panel")
    record = _function_source("video_scene3_record_generated_image")
    assert 'return_to == "vprofile|asset_ai_return"' in target
    assert 'return "asset_gate"' in target
    assert 'if step == "image_source":' in panel
    assert "video_scene3_image_source_keyboard(state)" in panel
    assert '"scene_index"' in record
    assert '"storyboard_frames"' in record


def test_frame_video_keeps_local_ffmpeg_route_outside_flow7_product_wizard() -> None:
    route = video_flow6.execution_route_for(
        video_flow6.new_context(product_id="frame_video_local")
    )
    assert route["job_type"] == "frame_video_local"
    assert route["mapped_job_type"] == "frame_video_render"
    assert route["execution_owner"] == "local_worker"
    assert route["local_renderer"] == "ffmpeg"
    assert "frame_video_local" not in video_flow7.PRODUCT_KIND_BY_ID


def test_flow7_service_is_provider_free() -> None:
    source = (ROOT / "services" / "video_flow7.py").read_text(encoding="utf-8")
    for forbidden in (
        "requests.",
        "httpx.",
        "urllib.request",
        "shopaikey",
        "key4u",
        "subprocess",
    ):
        assert forbidden not in source.lower()
