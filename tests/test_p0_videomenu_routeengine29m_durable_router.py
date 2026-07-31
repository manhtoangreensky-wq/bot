from __future__ import annotations

import copy
import json

import pytest

from services import video_engine_contract


def _project(
    *,
    product_type: str = "video_ai_prompt",
    scene_count: int = 1,
    primary_profile: str = "sales_ads",
    technical_profile: str = "product_showcase",
    linked_profiles: tuple[str, ...] = (),
) -> dict:
    cards = [
        {
            "scene_index": index,
            "provider_prompt": f"scene {index}: keep the approved product exact",
        }
        for index in range(1, scene_count + 1)
    ]
    return {
        "project_id": 29,
        "scene_count": scene_count,
        "asset_pack_json": json.dumps(
            {
                "source": "product_video",
                "product_type": product_type,
                "scene_count": scene_count,
            }
        ),
        "invoice_json": json.dumps(
            {"product_type": product_type, "scene_count": scene_count}
        ),
        "story_bible_json": json.dumps(
            {
                "primary_profile": primary_profile,
                "technical_profile": technical_profile,
                "linked_profiles": list(linked_profiles),
            }
        ),
        "scene_cards_json": json.dumps(cards),
    }


def _replace_json(project: dict, field: str, **values) -> dict:
    updated = copy.deepcopy(project)
    current = json.loads(updated[field])
    current.update(values)
    updated[field] = json.dumps(current)
    return updated


def test_29m_product_single_scene_uses_durable_product_and_count() -> None:
    result = video_engine_contract.durable_video_product_route_selection(_project())

    assert result["selection_ok"] is True
    assert result["engine_product"] == "product_video"
    assert result["mode"] == "single_scene"
    assert result["scene_count"] == 1
    assert result["public_product_type"] == "video_ai_prompt"
    assert result["selection_source"] == "locked_public_product"
    assert len(result["route_selection_sha256"]) == 64
    assert result["blocker"] == ""
    assert "dispatch_allowed" not in result


@pytest.mark.parametrize(
    ("product_type", "expected_product"),
    (
        ("video_ai_prompt", "product_video"),
        ("video_ai_image", "product_video"),
        ("video_ai_video_reference", "product_video"),
        ("video_trend", "product_video"),
        ("script_to_video", "product_video"),
        ("storyboard_prompt", "product_video"),
        ("video_idea_to_product", "product_video"),
        ("image_to_video", "frame_video"),
        ("frame_video_local", "frame_video"),
        ("self_shot_scene_change", "human_ai_video"),
        ("self_shot_cinematic_transform", "human_ai_video"),
        ("human_ai_video", "human_ai_video"),
        ("animated_video", "animated_video"),
        ("summary_video", "summary_video"),
        ("podcast_video", "podcast_video"),
    ),
)
def test_29m_known_products_map_to_one_engine(
    product_type: str,
    expected_product: str,
) -> None:
    result = video_engine_contract.durable_video_product_route_selection(
        _project(product_type=product_type)
    )

    assert result["selection_ok"] is True
    assert result["engine_product"] == expected_product


@pytest.mark.parametrize(
    ("scene_count", "expected_mode"),
    ((1, "single_scene"), (2, "multi_scene"), (3, "multi_scene")),
)
def test_29m_scene_count_selects_exact_mode(
    scene_count: int,
    expected_mode: str,
) -> None:
    result = video_engine_contract.durable_video_product_route_selection(
        _project(scene_count=scene_count)
    )

    assert result["selection_ok"] is True
    assert result["scene_count"] == scene_count
    assert result["mode"] == expected_mode


def test_29m_exact_primary_animation_profile_selects_animated_engine() -> None:
    result = video_engine_contract.durable_video_product_route_selection(
        _project(
            primary_profile="character_animation_vfx",
            technical_profile="animation_2d_3d",
        )
    )

    assert result["selection_ok"] is True
    assert result["engine_product"] == "animated_video"
    assert result["selection_source"] == "primary_profile"


def test_29m_legacy_animation_technical_profile_requires_empty_primary() -> None:
    result = video_engine_contract.durable_video_product_route_selection(
        _project(primary_profile="", technical_profile="animation_2d_3d")
    )

    assert result["selection_ok"] is True
    assert result["engine_product"] == "animated_video"
    assert result["selection_source"] == "legacy_technical_profile"


def test_29m_auto_derived_animation_technical_profile_does_not_override_primary() -> None:
    result = video_engine_contract.durable_video_product_route_selection(
        _project(
            primary_profile="meme_parody_comedy",
            technical_profile="animation_2d_3d",
        )
    )

    assert result["selection_ok"] is True
    assert result["engine_product"] == "product_video"
    assert result["selection_source"] == "locked_public_product"


def test_29m_linked_animation_profile_does_not_change_product() -> None:
    result = video_engine_contract.durable_video_product_route_selection(
        _project(linked_profiles=("character_animation_vfx",))
    )

    assert result["selection_ok"] is True
    assert result["engine_product"] == "product_video"


@pytest.mark.parametrize(
    "keyword",
    ("podcast", "summary", "news", "interview"),
)
def test_29m_prompt_keywords_never_infer_an_engine_product(keyword: str) -> None:
    project = _project()
    project = _replace_json(
        project,
        "asset_pack_json",
        original_user_prompt=f"Make a {keyword} style product launch",
    )

    result = video_engine_contract.durable_video_product_route_selection(project)

    assert result["selection_ok"] is True
    assert result["engine_product"] == "product_video"


def test_29m_conflicting_durable_product_fields_fail_closed() -> None:
    project = _replace_json(
        _project(),
        "invoice_json",
        product_type="self_shot_scene_change",
    )

    result = video_engine_contract.durable_video_product_route_selection(project)

    assert result["selection_ok"] is False
    assert result["blocker"] == "durable_engine_product_mismatch"
    assert result["route_selection_sha256"] == ""


def test_29m_conflicting_scene_counts_fail_closed() -> None:
    project = _replace_json(_project(), "invoice_json", scene_count=3)

    result = video_engine_contract.durable_video_product_route_selection(project)

    assert result["selection_ok"] is False
    assert result["blocker"] == "durable_scene_count_mismatch"


@pytest.mark.parametrize(
    "field",
    ("asset_pack_json", "invoice_json", "story_bible_json", "scene_cards_json"),
)
def test_29m_malformed_nonempty_snapshot_json_fails_closed(field: str) -> None:
    project = _project()
    project[field] = "{not-json"

    result = video_engine_contract.durable_video_product_route_selection(project)

    assert result["selection_ok"] is False
    assert result["blocker"] == "durable_video_project_snapshot_invalid"


def test_29m_unknown_product_never_defaults_to_product_video() -> None:
    result = video_engine_contract.durable_video_product_route_selection(
        _project(product_type="unknown_video_product")
    )

    assert result["selection_ok"] is False
    assert result["blocker"] == "durable_public_product_unsupported"


def test_29m_missing_scene_count_fails_closed() -> None:
    project = _project()
    project["scene_count"] = 0
    project = _replace_json(project, "asset_pack_json", scene_count=0)
    project = _replace_json(project, "invoice_json", scene_count=0)
    project["scene_cards_json"] = "[]"

    result = video_engine_contract.durable_video_product_route_selection(project)

    assert result["selection_ok"] is False
    assert result["blocker"] == "durable_scene_count_missing"


@pytest.mark.parametrize("product_type", ("video_local_edit", "video_editing"))
def test_29m_video_edit_scope_remains_released(product_type: str) -> None:
    result = video_engine_contract.durable_video_product_route_selection(
        _project(product_type=product_type)
    )

    assert result["selection_ok"] is False
    assert result["blocker"] == "video_editing_scope_released"


def test_29m_route_fingerprint_is_stable_across_json_key_order() -> None:
    first = _project()
    second = copy.deepcopy(first)
    for field in (
        "asset_pack_json",
        "invoice_json",
        "story_bible_json",
        "scene_cards_json",
    ):
        parsed = json.loads(second[field])
        if isinstance(parsed, dict):
            parsed = dict(reversed(list(parsed.items())))
        second[field] = json.dumps(parsed, indent=2)

    first_result = video_engine_contract.durable_video_product_route_selection(first)
    second_result = video_engine_contract.durable_video_product_route_selection(second)

    assert first_result["selection_ok"] is True
    assert second_result["selection_ok"] is True
    assert first_result["route_selection_sha256"] == second_result["route_selection_sha256"]


def test_29m_resolution_does_not_mutate_the_durable_project() -> None:
    project = _project(scene_count=3)
    before = copy.deepcopy(project)

    video_engine_contract.durable_video_product_route_selection(project)

    assert project == before
