from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat

import pytest

from services import video_edit_long_media as long_media
from services import video_edit_media_transport as media_transport
from services import video_local_editing


SOURCE_SHA = "a" * 64
OTHER_PRINCIPAL_PERMISSION_BITS = (
    stat.S_IRGRP,
    stat.S_IWGRP,
    stat.S_IXGRP,
    stat.S_IROTH,
    stat.S_IWOTH,
    stat.S_IXOTH,
)


def _make_private_file(path: Path) -> None:
    if os.name == "posix":
        path.chmod(0o600)


def _make_private_directory(path: Path) -> None:
    if os.name == "posix":
        path.chmod(0o700)


def _plan() -> dict:
    return {"operation": "split", "count": 2, "quality": "source"}


def _identity(*, output_index: int = 0) -> dict:
    plan = _plan()
    return {
        "source_sha256": SOURCE_SHA,
        "plan_hash": long_media.canonical_plan_hash(plan),
        "revision": 4,
        "output_index": output_index,
        "project_key": long_media.project_key(
            user_id="7",
            source_sha256=SOURCE_SHA,
            plan=plan,
            revision=4,
            output_index=output_index,
        ),
    }


def _artifact(path: Path, payload: bytes = b"video-artifact") -> long_media.ArtifactEvidence:
    path.write_bytes(payload)
    _make_private_file(path)
    return long_media.ArtifactEvidence(
        relative_path=path.name,
        sha256=hashlib.sha256(payload).hexdigest(),
        byte_count=len(payload),
        duration_ms=2_000,
        width=1920,
        height=1080,
        container="mp4",
    )


def _probe(**overrides) -> dict:
    value = {
        "duration_ms": 2_000,
        "width": 1920,
        "height": 1080,
        "container": "mp4",
    }
    value.update(overrides)
    return value


def _checkpoint(
    tmp_path: Path,
    *,
    delivery: long_media.DeliveryCursor | None = None,
    canonical: bool = True,
) -> long_media.LongMediaCheckpoint:
    identity = _identity()
    delivery_value = delivery or long_media.DeliveryCursor()
    checkpoint_stage = "canonical_ready" if canonical else "rendering"
    if delivery_value.state != "not_started":
        checkpoint_stage = "delivery_ready"
    artifact = _artifact(tmp_path / "part-0.mp4")
    part = long_media.PartCheckpoint(
        part_id=long_media.stable_part_id(index=0, start_ms=0, end_ms=2_000),
        index=0,
        start_ms=0,
        end_ms=2_000,
        artifact=artifact,
        stage="validated",
    )
    return long_media.LongMediaCheckpoint(
        project_key=identity["project_key"],
        source_sha256=identity["source_sha256"],
        plan_hash=identity["plan_hash"],
        revision=identity["revision"],
        output_index=identity["output_index"],
        execution_class="segment_safe",
        stage=checkpoint_stage,
        progress=long_media.ProgressState(
            stage=checkpoint_stage,
            completed_units=1,
            total_units=1,
            unit="parts",
        ),
        parts=(part,),
        canonical=artifact if canonical else None,
        delivery=delivery_value,
    )


def _checkpoint_with_part_stage(
    tmp_path: Path,
    *,
    checkpoint_stage: str,
    part_stage: str,
    include_canonical: bool | None = None,
) -> long_media.LongMediaCheckpoint:
    identity = _identity()
    artifact = _artifact(tmp_path / f"{checkpoint_stage}-{part_stage}.mp4")
    part = long_media.PartCheckpoint(
        part_id=long_media.stable_part_id(index=0, start_ms=0, end_ms=2_000),
        index=0,
        start_ms=0,
        end_ms=2_000,
        artifact=artifact,
        stage=part_stage,
    )
    canonical_default = checkpoint_stage in {"canonical_ready", "delivery_ready", "completed"}
    delivery = long_media.DeliveryCursor()
    if checkpoint_stage == "completed":
        delivery = long_media.DeliveryCursor(
            state="delivered",
            attempt_id="attempt-1",
            message_id="101",
            file_id="file-1",
        )
    return long_media.LongMediaCheckpoint(
        project_key=identity["project_key"],
        source_sha256=identity["source_sha256"],
        plan_hash=identity["plan_hash"],
        revision=identity["revision"],
        output_index=identity["output_index"],
        execution_class="segment_safe",
        stage=checkpoint_stage,
        progress=long_media.ProgressState(
            stage=checkpoint_stage,
            completed_units=1,
            total_units=1,
            unit="parts",
        ),
        parts=(part,),
        canonical=artifact if (canonical_default if include_canonical is None else include_canonical) else None,
        delivery=delivery,
    )


def test_canonical_plan_hash_is_stable_for_key_order_and_compact_utf8() -> None:
    first = {"volume": 80, "label": "Tiếng Việt", "speed": 1.0}
    second = {"speed": 1.0, "label": "Tiếng Việt", "volume": 80}
    expected_json = json.dumps(
        first, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")

    assert long_media.canonical_plan_hash(first) == long_media.canonical_plan_hash(second)
    assert long_media.canonical_plan_hash(first) == hashlib.sha256(expected_json).hexdigest()


@pytest.mark.parametrize(
    "label",
    ["9.5", "v1.2", "FFmpeg 7.1.1", "Bản dựng v2.10", "2026.08.03"],
)
def test_canonical_plan_hash_keeps_benign_dotted_versions(label: str) -> None:
    plan = {"operation": "trim", "label": label}
    expected_json = json.dumps(
        plan, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")

    assert long_media.canonical_plan_hash(plan) == hashlib.sha256(expected_json).hexdigest()


def test_canonical_plan_hash_rejects_tree_deeper_than_safe_limit() -> None:
    nested: object = "leaf"
    for _ in range(34):
        nested = {"options": nested}

    with pytest.raises(ValueError):
        long_media.canonical_plan_hash({"plan": nested})


def test_canonical_plan_hash_rejects_tree_over_node_budget() -> None:
    with pytest.raises(ValueError):
        long_media.canonical_plan_hash({"items": [0] * 10_000})


def test_canonical_plan_hash_rejects_collection_over_safe_limit() -> None:
    with pytest.raises(ValueError):
        long_media.canonical_plan_hash({"items": [0] * 10_001})


@pytest.mark.parametrize(
    "plan",
    [
        {"bot_token": "123:secret"},
        {"asset": "https://tg.example/private/file"},
        {"asset": "  https://tg.example/private/file  "},
        {"asset": "//tg.example/private/file"},
        {"label": "bad\x00value"},
        {"value": float("nan")},
    ],
)
def test_canonical_plan_hash_rejects_secret_url_control_and_nonfinite_values(plan) -> None:
    with pytest.raises(ValueError):
        long_media.canonical_plan_hash(plan)


@pytest.mark.parametrize(
    "value",
    [
        "Xem trước tại https://tg.example/private/file",
        "Xem trước tại //tg.example/private/file",
        "Xem trước tại tg.example/private/file",
        "Xem trước tại tg.example",
        "Xem trước tại tg.example:443",
        "Xem trước tại 127.0.0.1/private",
        "Xem trước tại user@tg.example/private",
        "Xem trước tại localhost/private",
        "Xem trước tại [2001:db8::1]/private",
        "Xem trước tại tg.example./private",
        "Xem trước tại 127.0.0.1./private",
        "Xem trước tại 2001:db8::1/private",
        "Xem trước tại 2001:db8::1:443/private",
        "Xem trước tại example.xn--p1ai/private",
        "Mã tạm 123456:abcdefghijklmnopqrstuvwxyzABCD",
    ],
)
def test_canonical_plan_hash_rejects_embedded_remote_or_token_material(value) -> None:
    with pytest.raises(ValueError):
        long_media.canonical_plan_hash({"trim": {"label": value}})


def test_safe_tree_rejects_nested_secret_like_keys() -> None:
    with pytest.raises(ValueError):
        long_media.canonical_plan_hash(
            {"trim": {"customerAuthorizationBackup": "không lưu bí mật"}}
        )


def test_safe_tree_keeps_vietnamese_labels_and_relative_media_filenames() -> None:
    plan = {
        "label": "Video tiếng Việt bản nháp",
        "asset": "clips/part-01.mp4",
        "output": "video.mov",
        "trim": {"source": "media/video.mp4", "start_ms": 0, "end_ms": 2_000},
    }

    assert len(long_media.canonical_plan_hash(plan)) == 64


def test_safe_tree_rejects_nested_trailing_dot_and_unbracketed_ipv6_hosts() -> None:
    for value in (
        "tg.example./private",
        "127.0.0.1./private",
        "::1/",
        "::1/private",
        "fe80::1/",
        "fe80::1/private",
        "fe80::1%eth0/private",
        "fe80::1%25Ethernet/private",
        "::ffff:192.0.2.1/private",
        "2001:db8::1/private",
        "2001:db8::1:443/private",
    ):
        with pytest.raises(ValueError):
            long_media.canonical_plan_hash({"trim": {"settings": [{"asset": value}]}})


@pytest.mark.parametrize(
    "value",
    [
        "Mốc 12:34:56/cảnh vẫn là ghi chú",
        "Mốc 12:34/",
        "Khung 00:00:01.250/frame-01.mp4",
        "Tỷ lệ 16:9/crop",
        "clips/part-01.mp4",
    ],
)
def test_safe_tree_does_not_treat_timestamp_text_or_relative_media_as_ipv6(value) -> None:
    assert len(long_media.canonical_plan_hash({"trim": {"text": value}})) == 64


@pytest.mark.parametrize("value", ["::1/", "fe80::1/"])
def test_checkpoint_safe_tree_rejects_unbracketed_ipv6_host_with_trailing_slash(
    tmp_path: Path, value: str
) -> None:
    checkpoint = _checkpoint(tmp_path).to_mapping()
    checkpoint["progress"]["detail"] = value

    with pytest.raises(ValueError):
        long_media.canonical_checkpoint_json(checkpoint)


def test_project_key_binds_domain_identity_revision_and_output() -> None:
    kwargs = {
        "user_id": "7",
        "source_sha256": SOURCE_SHA,
        "plan": {"speed": 1.0, "volume": 80},
        "revision": 4,
    }
    first = long_media.project_key(**kwargs, output_index=0)
    reordered = long_media.project_key(
        user_id="7",
        source_sha256=SOURCE_SHA,
        plan={"volume": 80, "speed": 1.0},
        revision=4,
        output_index=0,
    )

    assert first == reordered
    assert len(first) == 64
    assert first != long_media.project_key(**kwargs, output_index=1)
    assert first != long_media.project_key(**{**kwargs, "revision": 5}, output_index=0)


@pytest.mark.parametrize(
    "changes",
    [
        {"user_id": ""},
        {"user_id": "7\nadmin"},
        {"user_id": "https://example.invalid/user"},
        {"source_sha256": "a" * 63},
        {"source_sha256": "g" * 64},
        {"revision": 0},
        {"revision": -1},
        {"output_index": -1},
    ],
)
def test_project_key_rejects_invalid_identity(changes) -> None:
    values = {
        "user_id": "7",
        "source_sha256": SOURCE_SHA,
        "plan": _plan(),
        "revision": 4,
        "output_index": 0,
    }
    values.update(changes)
    with pytest.raises(ValueError):
        long_media.project_key(**values)


@pytest.mark.parametrize(
    "plan",
    [
        {"operation": "split", "count": 4},
        {"operation": "cut", "ranges": [[0, 1_000], [2_000, 3_000]]},
        {"operations": [{"kind": "crop"}, {"kind": "text_overlay"}]},
        {"trim": {"start_ms": 100, "end_ms": 800}, "speed": 1.1},
        {"operation": "transcode", "codec": "h264", "container": "mp4"},
    ],
)
def test_segment_local_operations_are_segment_safe(plan) -> None:
    assert long_media.classify_plan_execution(plan) == "segment_safe"


@pytest.mark.parametrize(
    "plan",
    [
        {"operation": "split", "settings": ["future_magic"]},
        {"operation": "split", "settings": (("future_magic",),)},
    ],
)
def test_unknown_scalar_nested_under_strict_operation_fields_requires_whole_timeline(plan) -> None:
    assert long_media.classify_plan_execution(plan) == "whole_timeline_required"


@pytest.mark.parametrize("unknown", [7, True, 1.25, "future_magic"])
@pytest.mark.parametrize("field", ["settings", "options"])
def test_unknown_scalar_of_any_type_in_strict_lists_requires_whole_timeline(
    field, unknown
) -> None:
    plan = {"operation": "split", field: [[unknown]]}

    assert long_media.classify_plan_execution(plan) == "whole_timeline_required"


@pytest.mark.parametrize(
    "plan",
    [
        {"operation": "split", "settings": {"count": 2, "enabled": True}},
        {
            "operation": "split",
            "options": [{"width": 720, "height": 1280}, {"codec": "h264"}],
        },
        {"operation": "split", "settings": ["trim", {"ranges": [[0, 1_000]]}]},
    ],
)
def test_recognized_strict_mapping_and_list_values_remain_segment_safe(plan) -> None:
    assert long_media.classify_plan_execution(plan) == "segment_safe"


def test_known_scalar_nested_under_strict_operation_fields_remains_segment_safe() -> None:
    assert long_media.classify_plan_execution(
        {"operation": "split", "settings": ["trim", "crop"]}
    ) == "segment_safe"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("trim", {"start_ms": 1_000, "end_ms": 8_000}),
        ("remove_middle", {"start_ms": 3_000, "end_ms": 5_000}),
        ("rotation", 90),
        ("brightness_percent", 115),
    ],
)
def test_canonical_video_edit_manual_plan_keeps_proven_local_operations_segment_safe(
    field: str,
    value: object,
) -> None:
    plan = video_local_editing.default_manual_edit_plan("source.mp4")
    plan[field] = value

    assert long_media.classify_plan_execution(plan) == "segment_safe"


def test_canonical_video_edit_manual_plan_keeps_active_global_operation_whole_timeline() -> None:
    plan = video_local_editing.default_manual_edit_plan("source.mp4")
    plan["audio_normalization"] = "ebu_r128"

    assert long_media.classify_plan_execution(plan) == "whole_timeline_required"


def test_canonical_video_edit_neutral_split_plan_is_segment_safe() -> None:
    assert long_media.classify_plan_execution(
        video_local_editing.neutral_split_manual_plan()
    ) == "segment_safe"


@pytest.mark.parametrize(
    "plan",
    [
        {"concat_inputs": ["a.mp4", "b.mp4"]},
        {"operation": "concat", "ordering": [2, 1]},
        {"audio_loudnorm": True},
        {"audio_analysis": {"whole_track": True}},
        {"transitions": [{"kind": "crossfade"}]},
        {"operation": "boundary_blend"},
        {"operation": "future_magic"},
        {"operation": "split", "settings": {"future_magic": True}},
        {"trim": {"start_ms": 100, "end_ms": 800, "future_magic": True}},
        {"crop": {"width": 720, "options": {"future_magic": True}}},
        {},
    ],
)
def test_global_or_unknown_operations_require_whole_timeline(plan) -> None:
    assert long_media.classify_plan_execution(plan) == "whole_timeline_required"


def test_workspace_estimate_is_operation_aware_and_monotonic() -> None:
    values = {
        operation: long_media.estimate_workspace(
            operation=operation,
            source_bytes=100_000_000,
            asset_bytes=[10_000_000],
            output_count=2,
            reserve_bytes=20_000_000,
        )
        for operation in ("manual", "concat", "split", "overlay", "transcode")
    }

    assert all(item.estimated_bytes >= 110_000_000 for item in values.values())
    assert all(item.required_bytes == item.estimated_bytes + 20_000_000 for item in values.values())
    assert values["concat"].estimated_bytes > values["manual"].estimated_bytes
    assert values["transcode"].estimated_bytes > values["split"].estimated_bytes
    larger = long_media.estimate_workspace(
        operation="manual",
        source_bytes=200_000_000,
        asset_bytes=[10_000_000],
        output_count=2,
        reserve_bytes=20_000_000,
    )
    assert larger.required_bytes > values["manual"].required_bytes


@pytest.mark.parametrize("operation", ["manual", "concat", "overlay", "transcode"])
def test_full_output_workspace_estimate_accounts_for_each_output(operation) -> None:
    common = {
        "operation": operation,
        "source_bytes": 120_000_000,
        "asset_bytes": [30_000_000],
        "reserve_bytes": 0,
    }
    one = long_media.estimate_workspace(**common, output_count=1)
    three = long_media.estimate_workspace(**common, output_count=3)

    assert three.output_bytes >= one.output_bytes * 3
    assert three.required_bytes > one.required_bytes


def test_multi_output_transcode_estimate_reserves_full_encoded_media_bytes() -> None:
    source_bytes = 400_000_000
    output_count = 4
    estimate = long_media.estimate_workspace(
        operation="transcode",
        source_bytes=source_bytes,
        output_count=output_count,
        reserve_bytes=0,
    )

    per_output = (source_bytes * 3 + 1) // 2
    assert estimate.output_bytes >= per_output * output_count


def test_split_workspace_estimate_keeps_per_file_overhead_monotonic() -> None:
    one = long_media.estimate_workspace(
        operation="split", source_bytes=120_000_000, output_count=1, reserve_bytes=0
    )
    four = long_media.estimate_workspace(
        operation="split", source_bytes=120_000_000, output_count=4, reserve_bytes=0
    )

    assert four.output_bytes >= one.output_bytes + 3 * 1024 * 1024


@pytest.mark.parametrize("bad", [-1, True, 2**63])
def test_workspace_estimate_rejects_unsafe_integer_inputs(bad) -> None:
    with pytest.raises(ValueError):
        long_media.estimate_workspace(
            operation="manual", source_bytes=bad, asset_bytes=[], output_count=1
        )


def test_workspace_admission_returns_truthful_structured_evidence() -> None:
    unknown = long_media.admit_workspace(
        operation="manual",
        source_bytes=None,
        asset_bytes=[],
        output_count=1,
        free_bytes=10**12,
    )
    estimate = long_media.estimate_workspace(
        operation="overlay",
        source_bytes=50_000_000,
        asset_bytes=[5_000_000],
        output_count=1,
        reserve_bytes=10_000_000,
    )
    insufficient = long_media.admit_workspace(
        operation="overlay",
        source_bytes=50_000_000,
        asset_bytes=[5_000_000],
        output_count=1,
        reserve_bytes=10_000_000,
        free_bytes=estimate.required_bytes - 1,
    )
    accepted = long_media.admit_workspace(
        operation="overlay",
        source_bytes=50_000_000,
        asset_bytes=[5_000_000],
        output_count=1,
        reserve_bytes=10_000_000,
        free_bytes=estimate.required_bytes,
    )

    assert unknown.accepted is False and unknown.reason == "unknown_source_size"
    assert insufficient.accepted is False and insufficient.reason == "insufficient_workspace"
    assert insufficient.evidence["required_bytes"] == estimate.required_bytes
    assert accepted.accepted is True and accepted.reason == "accepted"


def test_workspace_admission_accepts_fully_materialized_inputs_at_remaining_boundary() -> None:
    source_bytes = 50_000_000
    asset_bytes = [5_000_000]
    estimate = long_media.estimate_workspace(
        operation="overlay",
        source_bytes=source_bytes,
        asset_bytes=asset_bytes,
        output_count=1,
        reserve_bytes=10_000_000,
    )
    materialized_input_bytes = source_bytes + sum(asset_bytes)
    remaining_required_bytes = estimate.required_bytes - materialized_input_bytes

    decision = long_media.admit_workspace(
        operation="overlay",
        source_bytes=source_bytes,
        asset_bytes=asset_bytes,
        output_count=1,
        reserve_bytes=10_000_000,
        free_bytes=remaining_required_bytes,
        materialized_input_bytes=materialized_input_bytes,
    )

    assert remaining_required_bytes == (
        estimate.scratch_bytes + estimate.output_bytes + estimate.reserve_bytes
    )
    assert decision.accepted is True
    assert decision.reason == "accepted"
    assert decision.evidence["required_bytes"] == estimate.required_bytes
    assert decision.evidence["materialized_input_bytes"] == materialized_input_bytes
    assert decision.evidence["remaining_required_bytes"] == remaining_required_bytes


def test_workspace_admission_rejects_one_byte_below_fully_materialized_boundary() -> None:
    source_bytes = 50_000_000
    asset_bytes = [5_000_000]
    estimate = long_media.estimate_workspace(
        operation="overlay",
        source_bytes=source_bytes,
        asset_bytes=asset_bytes,
        output_count=1,
        reserve_bytes=10_000_000,
    )
    materialized_input_bytes = source_bytes + sum(asset_bytes)
    remaining_required_bytes = estimate.required_bytes - materialized_input_bytes

    decision = long_media.admit_workspace(
        operation="overlay",
        source_bytes=source_bytes,
        asset_bytes=asset_bytes,
        output_count=1,
        reserve_bytes=10_000_000,
        free_bytes=remaining_required_bytes - 1,
        materialized_input_bytes=materialized_input_bytes,
    )

    assert decision.accepted is False
    assert decision.reason == "insufficient_workspace"
    assert decision.evidence["remaining_required_bytes"] == remaining_required_bytes


def test_workspace_admission_counts_only_unmaterialized_input_bytes() -> None:
    source_bytes = 80_000_000
    asset_bytes = [20_000_000]
    materialized_input_bytes = 35_000_000
    estimate = long_media.estimate_workspace(
        operation="concat",
        source_bytes=source_bytes,
        asset_bytes=asset_bytes,
        output_count=1,
        reserve_bytes=5_000_000,
    )
    remaining_required_bytes = estimate.required_bytes - materialized_input_bytes

    decision = long_media.admit_workspace(
        operation="concat",
        source_bytes=source_bytes,
        asset_bytes=asset_bytes,
        output_count=1,
        reserve_bytes=5_000_000,
        free_bytes=remaining_required_bytes,
        materialized_input_bytes=materialized_input_bytes,
    )

    assert decision.accepted is True
    assert decision.evidence["required_bytes"] == estimate.required_bytes
    assert decision.evidence["materialized_input_bytes"] == materialized_input_bytes
    assert decision.evidence["remaining_required_bytes"] == remaining_required_bytes


@pytest.mark.parametrize("bad", [121, -1, True])
def test_workspace_admission_rejects_invalid_materialized_input_bytes(bad) -> None:
    decision = long_media.admit_workspace(
        operation="manual",
        source_bytes=100,
        asset_bytes=[20],
        output_count=1,
        reserve_bytes=0,
        free_bytes=10_000,
        materialized_input_bytes=bad,
    )

    assert decision.accepted is False
    assert decision.reason == "invalid_input"


def test_workspace_admission_defaults_materialized_input_to_zero() -> None:
    estimate = long_media.estimate_workspace(
        operation="manual",
        source_bytes=100,
        asset_bytes=[20],
        output_count=1,
        reserve_bytes=0,
    )

    decision = long_media.admit_workspace(
        operation="manual",
        source_bytes=100,
        asset_bytes=[20],
        output_count=1,
        reserve_bytes=0,
        free_bytes=estimate.required_bytes,
    )

    assert decision.accepted is True
    assert decision.evidence["materialized_input_bytes"] == 0
    assert decision.evidence["remaining_required_bytes"] == estimate.required_bytes


def test_workspace_internal_emergency_cap_is_optional_and_not_a_public_limit() -> None:
    common = dict(
        operation="manual",
        source_bytes=100,
        asset_bytes=[20],
        output_count=1,
        reserve_bytes=0,
        free_bytes=10_000,
    )
    assert long_media.admit_workspace(**common, emergency_cap_bytes=0).accepted is True
    capped = long_media.admit_workspace(**common, emergency_cap_bytes=119)
    assert capped.accepted is False
    assert capped.reason == "internal_emergency_cap"


def test_adaptive_deadline_is_monotonic_bounded_and_global_work_costs_more() -> None:
    small = long_media.adaptive_deadline_seconds(
        source_bytes=10_000_000,
        duration_seconds=30,
        width=1280,
        height=720,
        output_count=1,
        operation_class="segment_safe",
        minimum_seconds=30,
        maximum_seconds=10_000,
    )
    large = long_media.adaptive_deadline_seconds(
        source_bytes=1_000_000_000,
        duration_seconds=3_600,
        width=3840,
        height=2160,
        output_count=4,
        operation_class="segment_safe",
        minimum_seconds=30,
        maximum_seconds=10_000,
    )
    global_work = long_media.adaptive_deadline_seconds(
        source_bytes=1_000_000_000,
        duration_seconds=3_600,
        width=3840,
        height=2160,
        output_count=4,
        operation_class="whole_timeline_required",
        minimum_seconds=30,
        maximum_seconds=10_000,
    )
    capped = long_media.adaptive_deadline_seconds(
        source_bytes=2**63 - 1,
        duration_seconds=10**12,
        width=100_000,
        height=100_000,
        output_count=1_000,
        operation_class="whole_timeline_required",
        minimum_seconds=30,
        maximum_seconds=10_000,
    )
    unknown = long_media.adaptive_deadline_seconds(
        source_bytes=None,
        duration_seconds=None,
        width=None,
        height=None,
        output_count=None,
        operation_class="unknown",
        minimum_seconds=30,
        maximum_seconds=10_000,
    )

    assert 30 <= small < large < global_work <= 10_000
    assert capped == 10_000
    assert unknown > small


def test_checkpoint_atomic_round_trip_replaces_existing_file(tmp_path: Path) -> None:
    checkpoint_path = tmp_path / "checkpoint.json"
    checkpoint_path.write_text("old", encoding="utf-8")
    _make_private_file(checkpoint_path)
    checkpoint = _checkpoint(tmp_path)

    long_media.write_checkpoint_atomic(checkpoint_path, checkpoint)
    loaded = long_media.load_checkpoint(checkpoint_path, **_identity())

    assert loaded == checkpoint
    encoded = checkpoint_path.read_bytes()
    assert encoded == long_media.canonical_checkpoint_json(checkpoint)
    assert not list(tmp_path.glob(".checkpoint.json.*.tmp"))
    if os.name == "posix":
        assert stat.S_IMODE(checkpoint_path.stat().st_mode) == 0o600


def test_checkpoint_writer_opts_into_private_parent_guard(
    tmp_path: Path, monkeypatch
) -> None:
    real_init = media_transport._DestinationGuard.__init__
    privacy_flags: list[object] = []

    def capture_init(guard, *args, **kwargs):
        privacy_flags.append(kwargs.get("require_private_parent"))
        return real_init(guard, *args, **kwargs)

    monkeypatch.setattr(media_transport._DestinationGuard, "__init__", capture_init)

    long_media.write_checkpoint_atomic(
        tmp_path / "checkpoint.json",
        _checkpoint(tmp_path),
    )

    assert privacy_flags == [True]


@pytest.mark.parametrize(
    "relative_path",
    ("D:outside/video.mp4", "c:artifact.mp4"),
)
def test_artifact_evidence_rejects_windows_drive_relative_paths(
    relative_path: str,
) -> None:
    with pytest.raises(ValueError):
        long_media.ArtifactEvidence(
            relative_path=relative_path,
            sha256="a" * 64,
            byte_count=1,
            duration_ms=1,
            width=1,
            height=1,
            container="mp4",
        )


def test_checkpoint_write_rejects_payload_larger_than_read_ceiling(
    tmp_path: Path, monkeypatch
) -> None:
    checkpoint = _checkpoint(tmp_path)
    monkeypatch.setattr(
        long_media,
        "canonical_checkpoint_json",
        lambda _checkpoint: b"x" * (long_media.MAX_CHECKPOINT_BYTES + 1),
    )
    checkpoint_path = tmp_path / "oversized-checkpoint.json"

    with pytest.raises(long_media.CheckpointError) as error:
        long_media.write_checkpoint_atomic(checkpoint_path, checkpoint)

    assert error.value.reason == "checkpoint_too_large"
    assert not checkpoint_path.exists()
    assert not list(tmp_path.glob(".oversized-checkpoint.json.*.tmp"))


def test_checkpoint_mapping_rejects_boolean_schema_version(tmp_path: Path) -> None:
    value = _checkpoint(tmp_path).to_mapping()
    value["schema_version"] = True

    with pytest.raises(ValueError):
        long_media.LongMediaCheckpoint.from_mapping(value)


@pytest.mark.parametrize(
    ("path", "malformed"),
    [
        (("project_key",), int("1" * 64)),
        (("source_sha256",), int("1" * 64)),
        (("plan_hash",), int("1" * 64)),
        (("execution_class",), True),
        (("stage",), 1),
        (("progress", "stage"), 1),
        (("progress", "unit"), 123),
        (("progress", "detail"), 123),
        (("parts", 0, "part_id"), 123),
        (("parts", 0, "stage"), True),
        (("parts", 0, "artifact", "relative_path"), 123),
        (("parts", 0, "artifact", "sha256"), int("1" * 64)),
        (("parts", 0, "artifact", "container"), True),
        (("canonical", "relative_path"), 123),
        (("canonical", "sha256"), int("1" * 64)),
        (("canonical", "container"), True),
        (("delivery", "state"), True),
    ],
)
def test_checkpoint_mapping_requires_exact_strings_for_string_fields(
    tmp_path: Path, path, malformed
) -> None:
    value = _checkpoint(tmp_path).to_mapping()
    target = value
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = malformed

    with pytest.raises(ValueError):
        long_media.LongMediaCheckpoint.from_mapping(value)


@pytest.mark.parametrize("field", ["attempt_id", "message_id", "file_id"])
def test_delivery_mapping_rejects_non_string_receipt_ids(field) -> None:
    value = long_media.DeliveryCursor(
        state="accepted",
        attempt_id="101",
        message_id="102",
        file_id="103",
    ).to_mapping()
    value[field] = 123

    with pytest.raises(ValueError):
        long_media.DeliveryCursor.from_mapping(value)


def test_delivery_mapping_rejects_non_string_rejection_code() -> None:
    value = long_media.DeliveryCursor(
        state="rejected",
        attempt_id="101",
        deterministic=True,
        rejection_code="404",
    ).to_mapping()
    value["rejection_code"] = 404

    with pytest.raises(ValueError):
        long_media.DeliveryCursor.from_mapping(value)


def test_checkpoint_failure_cleans_only_its_exact_unique_temporary(
    tmp_path: Path, monkeypatch
) -> None:
    checkpoint_path = tmp_path / "checkpoint.json"
    unrelated = tmp_path / ".checkpoint.json.keep.tmp"
    unrelated.write_text("keep", encoding="utf-8")
    checkpoint = _checkpoint(tmp_path)

    if os.name == "nt":
        monkeypatch.setattr(
            media_transport,
            "_win_rename_handle",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("replace failed")),
        )
    else:
        monkeypatch.setattr(
            media_transport.os,
            "replace",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("replace failed")),
        )
    with pytest.raises(long_media.CheckpointError):
        long_media.write_checkpoint_atomic(checkpoint_path, checkpoint)

    assert unrelated.read_text(encoding="utf-8") == "keep"
    assert sorted(path.name for path in tmp_path.iterdir() if path.name.endswith(".tmp")) == [
        unrelated.name
    ]


def test_checkpoint_rejects_symlink_destination(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_text("safe", encoding="utf-8")
    link = tmp_path / "checkpoint.json"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("file symlinks are unavailable")

    with pytest.raises(long_media.CheckpointError):
        long_media.write_checkpoint_atomic(link, _checkpoint(tmp_path))
    assert target.read_text(encoding="utf-8") == "safe"


def test_checkpoint_revalidates_existing_final_ownership_after_guard_creation(
    tmp_path: Path, monkeypatch
) -> None:
    checkpoint_path = tmp_path / "checkpoint.json"
    checkpoint_path.write_bytes(b"foreign-owned-final")
    real_owned_plain_file = long_media._owned_plain_file
    ownership_checks = 0

    def ownership_changes_after_first_check(path: Path) -> bool:
        nonlocal ownership_checks
        if Path(path) == checkpoint_path:
            ownership_checks += 1
            return ownership_checks == 1
        return real_owned_plain_file(path)

    monkeypatch.setattr(
        long_media,
        "_owned_plain_file",
        ownership_changes_after_first_check,
    )

    with pytest.raises(long_media.CheckpointError) as error:
        long_media.write_checkpoint_atomic(checkpoint_path, _checkpoint(tmp_path))

    assert error.value.reason == "unsafe_destination"
    assert ownership_checks >= 2
    assert checkpoint_path.read_bytes() == b"foreign-owned-final"


def test_checkpoint_load_uses_private_regular_file_policy(
    tmp_path: Path, monkeypatch
) -> None:
    checkpoint_path = tmp_path / "checkpoint.json"
    long_media.write_checkpoint_atomic(checkpoint_path, _checkpoint(tmp_path))
    monkeypatch.setattr(
        long_media,
        "_is_private_owned_regular_file",
        lambda *_args, **_kwargs: False,
    )

    with pytest.raises(long_media.CheckpointError) as error:
        long_media.load_checkpoint(checkpoint_path, **_identity())

    assert error.value.reason == "unsafe_destination"


def test_checkpoint_load_uses_private_parent_directory_policy(
    tmp_path: Path, monkeypatch
) -> None:
    checkpoint_path = tmp_path / "checkpoint.json"
    long_media.write_checkpoint_atomic(checkpoint_path, _checkpoint(tmp_path))
    monkeypatch.setattr(
        media_transport,
        "_is_private_owned_directory",
        lambda *_args, **_kwargs: False,
    )

    with pytest.raises(long_media.CheckpointError) as error:
        long_media.load_checkpoint(checkpoint_path, **_identity())

    assert error.value.reason == "unsafe_destination"


def test_checkpoint_mapping_rejects_secret_url_and_absolute_path(tmp_path: Path) -> None:
    base = _checkpoint(tmp_path).to_mapping()
    for key, value in (
        ("bot_token", "123:secret"),
        ("telegram_url", "https://tg.example/bot-secret"),
        ("worker_path", str(tmp_path.resolve())),
    ):
        unsafe = dict(base)
        unsafe[key] = value
        with pytest.raises(long_media.CheckpointError):
            long_media.write_checkpoint_atomic(tmp_path / f"{key}.json", unsafe)


def test_checkpoint_serialization_rejects_embedded_remote_material(tmp_path: Path) -> None:
    value = _checkpoint(tmp_path).to_mapping()
    value["progress"]["detail"] = "Preview tg.example"

    with pytest.raises(ValueError):
        long_media.canonical_checkpoint_json(value)


def test_load_checkpoint_validates_expected_identity(tmp_path: Path) -> None:
    checkpoint_path = tmp_path / "checkpoint.json"
    checkpoint = _checkpoint(tmp_path)
    long_media.write_checkpoint_atomic(checkpoint_path, checkpoint)
    wrong = _identity()
    wrong["plan_hash"] = "b" * 64

    with pytest.raises(long_media.CheckpointError):
        long_media.load_checkpoint(checkpoint_path, **wrong)
    assert long_media.try_load_checkpoint(checkpoint_path, **wrong) is None


def test_load_checkpoint_reads_only_from_one_open_descriptor(
    tmp_path: Path, monkeypatch
) -> None:
    checkpoint_path = tmp_path / "checkpoint.json"
    checkpoint = _checkpoint(tmp_path)
    long_media.write_checkpoint_atomic(checkpoint_path, checkpoint)
    real_open = long_media.os.open
    checkpoint_opens = 0

    def count_checkpoint_open(path, flags, *args, **kwargs):
        nonlocal checkpoint_opens
        if os.path.abspath(os.fspath(path)) == str(checkpoint_path):
            checkpoint_opens += 1
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(
        Path,
        "read_bytes",
        lambda _self: (_ for _ in ()).throw(AssertionError("path read forbidden")),
    )
    monkeypatch.setattr(long_media.os, "open", count_checkpoint_open)

    assert long_media.load_checkpoint(checkpoint_path, **_identity()) == checkpoint
    assert checkpoint_opens == 1


def test_checkpoint_descriptor_never_requests_beyond_hard_read_ceiling(
    tmp_path: Path, monkeypatch
) -> None:
    checkpoint_path = tmp_path / "exact-limit.json"
    checkpoint_path.write_bytes(b"x" * long_media.MAX_CHECKPOINT_BYTES)
    _make_private_file(checkpoint_path)
    real_read = long_media.os.read
    requested_sizes: list[int] = []

    def record_read(descriptor: int, size: int) -> bytes:
        requested_sizes.append(size)
        return real_read(descriptor, size)

    monkeypatch.setattr(long_media.os, "read", record_read)

    raw = long_media._read_checkpoint_descriptor(checkpoint_path)

    assert len(raw) == long_media.MAX_CHECKPOINT_BYTES
    assert sum(requested_sizes) <= long_media.MAX_CHECKPOINT_BYTES


def test_load_checkpoint_classifies_recursion_error_from_deep_json(tmp_path: Path) -> None:
    checkpoint_path = tmp_path / "checkpoint.json"
    checkpoint_path.write_bytes(
        b'{"nested":' + (b"[" * 2_000) + b"null" + (b"]" * 2_000) + b"}"
    )
    _make_private_file(checkpoint_path)

    with pytest.raises(long_media.CheckpointError) as error:
        long_media.load_checkpoint(checkpoint_path, **_identity())

    assert error.value.reason == "invalid_checkpoint"


def test_load_checkpoint_rejects_oversized_decoded_collection(tmp_path: Path) -> None:
    checkpoint_path = tmp_path / "checkpoint.json"
    checkpoint_path.write_text(
        json.dumps({"nested": [0] * 10_001}), encoding="utf-8"
    )
    _make_private_file(checkpoint_path)

    with pytest.raises(long_media.CheckpointError) as error:
        long_media.load_checkpoint(checkpoint_path, **_identity())

    assert error.value.reason == "invalid_checkpoint"


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor race")
def test_load_checkpoint_rejects_name_swap_after_open(tmp_path: Path, monkeypatch) -> None:
    checkpoint_path = tmp_path / "checkpoint.json"
    checkpoint = _checkpoint(tmp_path)
    long_media.write_checkpoint_atomic(checkpoint_path, checkpoint)
    attacker_path = tmp_path / "attacker.json"
    attacker_path.write_bytes(long_media.canonical_checkpoint_json(checkpoint))
    displaced = tmp_path / "displaced.json"
    real_open = long_media.os.open
    raced = False

    def swap_after_open(path, flags, *args, **kwargs):
        nonlocal raced
        descriptor = real_open(path, flags, *args, **kwargs)
        if not raced and os.path.abspath(os.fspath(path)) == str(checkpoint_path):
            raced = True
            os.replace(checkpoint_path, displaced)
            os.replace(attacker_path, checkpoint_path)
        return descriptor

    monkeypatch.setattr(long_media.os, "open", swap_after_open)

    with pytest.raises(long_media.CheckpointError):
        long_media.load_checkpoint(checkpoint_path, **_identity())


@pytest.mark.skipif(os.name != "posix", reason="POSIX bounded growth race")
def test_load_checkpoint_rejects_growth_during_bounded_read(
    tmp_path: Path, monkeypatch
) -> None:
    checkpoint_path = tmp_path / "checkpoint.json"
    checkpoint = _checkpoint(tmp_path)
    long_media.write_checkpoint_atomic(checkpoint_path, checkpoint)
    append_fd = os.open(checkpoint_path, os.O_WRONLY | os.O_APPEND)
    real_read = long_media.os.read
    mutated = False

    def grow_after_first_read(descriptor: int, size: int) -> bytes:
        nonlocal mutated
        chunk = real_read(descriptor, size)
        if chunk and not mutated:
            mutated = True
            os.write(append_fd, b" ")
            os.fsync(append_fd)
        return chunk

    monkeypatch.setattr(long_media.os, "read", grow_after_first_read)
    try:
        with pytest.raises(long_media.CheckpointError):
            long_media.load_checkpoint(checkpoint_path, **_identity())
    finally:
        os.close(append_fd)


@pytest.mark.skipif(os.name != "posix", reason="POSIX relative publish contract")
def test_checkpoint_publish_uses_retained_directory_fd_and_relative_names(
    tmp_path: Path, monkeypatch
) -> None:
    checkpoint_path = tmp_path / "checkpoint.json"
    real_replace = media_transport.os.replace
    calls: list[tuple[object, object, dict]] = []

    def capture_replace(source, destination, **kwargs):
        calls.append((source, destination, kwargs))
        return real_replace(source, destination, **kwargs)

    monkeypatch.setattr(media_transport.os, "replace", capture_replace)
    long_media.write_checkpoint_atomic(checkpoint_path, _checkpoint(tmp_path))

    assert len(calls) == 1
    source, destination, kwargs = calls[0]
    assert Path(os.fspath(source)).name == os.fspath(source)
    assert destination == checkpoint_path.name
    assert kwargs["src_dir_fd"] == kwargs["dst_dir_fd"]


@pytest.mark.skipif(os.name != "posix", reason="POSIX temp-name swap race")
def test_checkpoint_temp_swap_is_rejected_without_replacing_old_final(
    tmp_path: Path, monkeypatch
) -> None:
    checkpoint_path = tmp_path / "checkpoint.json"
    checkpoint_path.write_bytes(b"old-final")
    _make_private_file(checkpoint_path)
    stolen = tmp_path / "stolen.tmp"
    original_publish = media_transport._DestinationGuard.publish

    def swap_before_publish(guard, *args, **kwargs):
        os.replace(guard.partial_path, stolen)
        guard.partial_path.write_bytes(b"attacker")
        return original_publish(guard, *args, **kwargs)

    monkeypatch.setattr(media_transport._DestinationGuard, "publish", swap_before_publish)

    with pytest.raises(long_media.CheckpointError):
        long_media.write_checkpoint_atomic(checkpoint_path, _checkpoint(tmp_path))

    assert checkpoint_path.read_bytes() == b"old-final"


def test_part_reuse_requires_actual_hash_size_and_supplied_ffprobe_evidence(
    tmp_path: Path,
) -> None:
    checkpoint = _checkpoint(tmp_path)
    part_id = checkpoint.parts[0].part_id

    assert (
        long_media.validate_reusable_part(
            checkpoint,
            part_id=part_id,
            workspace=tmp_path,
            ffprobe_evidence=_probe(),
            **_identity(),
        )
        == checkpoint.parts[0]
    )
    assert (
        long_media.validate_reusable_part(
            checkpoint,
            part_id=part_id,
            workspace=tmp_path,
            ffprobe_evidence=_probe(width=640),
            **_identity(),
        )
        is None
    )
    (tmp_path / checkpoint.parts[0].artifact.relative_path).write_bytes(b"mutated")
    assert (
        long_media.validate_reusable_part(
            checkpoint,
            part_id=part_id,
            workspace=tmp_path,
            ffprobe_evidence=_probe(),
            **_identity(),
        )
        is None
    )


def test_artifact_reuse_hashes_with_bounded_descriptor_reads(
    tmp_path: Path, monkeypatch
) -> None:
    checkpoint = _checkpoint(tmp_path)
    part = checkpoint.parts[0]
    real_read = long_media.os.read
    read_sizes: list[int] = []

    def bounded_read(descriptor: int, size: int) -> bytes:
        read_sizes.append(size)
        assert 0 < size <= 1024 * 1024
        return real_read(descriptor, size)

    monkeypatch.setattr(long_media.os, "read", bounded_read)
    monkeypatch.setattr(
        long_media,
        "open",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("path open forbidden")),
        raising=False,
    )

    assert long_media.validate_reusable_part(
        checkpoint,
        part_id=part.part_id,
        workspace=tmp_path,
        ffprobe_evidence=_probe(),
        **_identity(),
    ) == part
    assert read_sizes


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor race")
def test_artifact_reuse_rejects_name_swap_after_open(tmp_path: Path, monkeypatch) -> None:
    checkpoint = _checkpoint(tmp_path)
    part = checkpoint.parts[0]
    artifact_path = tmp_path / part.artifact.relative_path
    displaced = tmp_path / "displaced.mp4"
    attacker = tmp_path / "attacker.mp4"
    attacker.write_bytes(b"attacker")
    real_open = long_media.os.open
    raced = False

    def swap_after_open(path, flags, *args, **kwargs):
        nonlocal raced
        descriptor = real_open(path, flags, *args, **kwargs)
        absolute_open = os.path.abspath(os.fspath(path)) == str(artifact_path)
        relative_open = (
            os.fspath(path) == artifact_path.name
            and kwargs.get("dir_fd") is not None
            and not flags & getattr(os, "O_DIRECTORY", 0)
        )
        if not raced and (absolute_open or relative_open):
            raced = True
            os.replace(artifact_path, displaced)
            os.replace(attacker, artifact_path)
        return descriptor

    monkeypatch.setattr(long_media.os, "open", swap_after_open)

    assert long_media.validate_reusable_part(
        checkpoint,
        part_id=part.part_id,
        workspace=tmp_path,
        ffprobe_evidence=_probe(),
        **_identity(),
    ) is None


@pytest.mark.skipif(os.name != "posix", reason="POSIX retained-directory race")
def test_artifact_reuse_rejects_nested_directory_swap_after_identity_check(
    tmp_path: Path, monkeypatch
) -> None:
    checkpoint = _checkpoint(tmp_path)
    part = checkpoint.parts[0]
    outer_directory = tmp_path / "outer"
    trusted_directory = outer_directory / "trusted"
    displaced_directory = outer_directory / "trusted-displaced"
    attacker_directory = outer_directory / "attacker"
    trusted_directory.mkdir(parents=True)
    attacker_directory.mkdir()
    _make_private_directory(outer_directory)
    _make_private_directory(trusted_directory)
    _make_private_directory(attacker_directory)
    original_artifact = tmp_path / part.artifact.relative_path
    trusted_artifact = trusted_directory / original_artifact.name
    original_artifact.replace(trusted_artifact)
    payload = trusted_artifact.read_bytes()
    (attacker_directory / trusted_artifact.name).write_bytes(payload)
    object.__setattr__(
        part.artifact,
        "relative_path",
        f"{outer_directory.name}/{trusted_directory.name}/{trusted_artifact.name}",
    )
    real_open = long_media.os.open
    raced = False

    def swap_after_directory_open(path, flags, *args, **kwargs):
        nonlocal raced
        descriptor = real_open(path, flags, *args, **kwargs)
        if (
            not raced
            and os.fspath(path) == trusted_directory.name
            and flags & os.O_DIRECTORY
            and kwargs.get("dir_fd") is not None
        ):
            trusted_directory.rename(displaced_directory)
            attacker_directory.rename(trusted_directory)
            raced = True
        return descriptor

    monkeypatch.setattr(long_media.os, "open", swap_after_directory_open)

    reusable = long_media.validate_reusable_part(
        checkpoint,
        part_id=part.part_id,
        workspace=tmp_path,
        ffprobe_evidence=_probe(),
        **_identity(),
    )

    assert reusable is None, "nested directory pathname swap must invalidate reuse"
    assert raced is True
    assert (displaced_directory / trusted_artifact.name).read_bytes() == payload


@pytest.mark.skipif(os.name != "nt", reason="requires Win32 handle sharing")
def test_artifact_reuse_windows_handles_never_share_delete(
    tmp_path: Path, monkeypatch
) -> None:
    checkpoint = _checkpoint(tmp_path)
    part = checkpoint.parts[0]
    real_create_file = media_transport._CreateFileW
    share_modes: list[int] = []

    def capture_share_mode(*args):
        share_modes.append(int(args[2]))
        return real_create_file(*args)

    monkeypatch.setattr(media_transport, "_CreateFileW", capture_share_mode)

    assert long_media.validate_reusable_part(
        checkpoint,
        part_id=part.part_id,
        workspace=tmp_path,
        ffprobe_evidence=_probe(),
        **_identity(),
    ) == part
    assert len(share_modes) >= 2
    assert all(not share_mode & 0x00000004 for share_mode in share_modes)


@pytest.mark.skipif(os.name != "nt", reason="requires Win32 handle lifecycle")
@pytest.mark.parametrize("failure_stage", ["root", "nested"])
@pytest.mark.parametrize("failure_point", ["information", "identity"])
def test_artifact_reuse_windows_closes_directory_handle_when_metadata_read_fails(
    tmp_path: Path,
    monkeypatch,
    failure_stage: str,
    failure_point: str,
) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    handles_by_path = {
        os.path.normcase(os.path.abspath(tmp_path)): 101,
        os.path.normcase(os.path.abspath(nested)): 202,
    }
    identities_by_handle = {
        101: (1, int(os.lstat(tmp_path).st_ino)),
        202: (1, int(os.lstat(nested).st_ino)),
    }
    opened: list[int] = []
    closed: list[int] = []

    def open_directory(path: Path) -> int:
        handle = handles_by_path[os.path.normcase(os.path.abspath(path))]
        opened.append(handle)
        return handle

    def file_information(handle: int):
        failing_handle = 101 if failure_stage == "root" else 202
        if failure_point == "information" and handle == failing_handle:
            raise OSError("metadata unavailable")
        return type(
            "DirectoryInformation",
            (),
            {"handle": handle, "identity": identities_by_handle[handle]},
        )()

    def file_identity(information):
        failing_handle = 101 if failure_stage == "root" else 202
        if failure_point == "identity" and information.handle == failing_handle:
            raise OSError("metadata unavailable")
        return information.identity

    monkeypatch.setattr(media_transport, "_win_open_directory", open_directory)
    monkeypatch.setattr(media_transport, "_win_file_information", file_information)
    monkeypatch.setattr(media_transport, "_win_identity", file_identity)
    monkeypatch.setattr(media_transport, "_win_close_handle", closed.append)
    monkeypatch.setattr(long_media, "_verify_windows_directory", lambda *_args: None)

    with pytest.raises(OSError, match="metadata unavailable"):
        long_media._hash_artifact_windows(
            tmp_path,
            ("nested", "artifact.mp4") if failure_stage == "nested" else ("artifact.mp4",),
            expected_bytes=1,
        )

    expected_handles = [101] if failure_stage == "root" else [101, 202]
    assert opened == expected_handles
    assert sorted(closed) == expected_handles
    assert len(closed) == len(set(closed))


@pytest.mark.skipif(os.name != "posix", reason="POSIX ownership/mode contract")
@pytest.mark.parametrize("unsafe_permission_bit", OTHER_PRINCIPAL_PERMISSION_BITS)
def test_artifact_reuse_rejects_workspace_access_by_other_principals(
    tmp_path: Path, unsafe_permission_bit: int
) -> None:
    checkpoint = _checkpoint(tmp_path)
    part = checkpoint.parts[0]
    original_mode = stat.S_IMODE(tmp_path.stat().st_mode)
    tmp_path.chmod(0o700 | unsafe_permission_bit)
    try:
        assert long_media.validate_reusable_part(
            checkpoint,
            part_id=part.part_id,
            workspace=tmp_path,
            ffprobe_evidence=_probe(),
            **_identity(),
        ) is None
    finally:
        tmp_path.chmod(original_mode)


@pytest.mark.skipif(os.name != "posix", reason="POSIX ownership/mode contract")
@pytest.mark.parametrize("unsafe_permission_bit", OTHER_PRINCIPAL_PERMISSION_BITS)
def test_artifact_reuse_rejects_artifact_access_by_other_principals(
    tmp_path: Path, unsafe_permission_bit: int
) -> None:
    checkpoint = _checkpoint(tmp_path)
    part = checkpoint.parts[0]
    artifact_path = tmp_path / part.artifact.relative_path
    original_mode = stat.S_IMODE(artifact_path.stat().st_mode)
    artifact_path.chmod(0o600 | unsafe_permission_bit)
    try:
        assert long_media.validate_reusable_part(
            checkpoint,
            part_id=part.part_id,
            workspace=tmp_path,
            ffprobe_evidence=_probe(),
            **_identity(),
        ) is None
    finally:
        artifact_path.chmod(original_mode)


@pytest.mark.parametrize(
    "unsafe_permission_bit",
    OTHER_PRINCIPAL_PERMISSION_BITS,
)
def test_artifact_file_policy_rejects_posix_access_by_other_principals(
    unsafe_permission_bit: int,
) -> None:
    unsafe_result = type(
        "UnsafeArtifactResult",
        (),
        {
            "st_mode": stat.S_IFREG | 0o600 | unsafe_permission_bit,
            "st_uid": 1000,
        },
    )()
    safe_result = type(
        "SafeArtifactResult",
        (),
        {"st_mode": stat.S_IFREG | 0o600, "st_uid": 1000},
    )()

    assert long_media._is_private_owned_regular_file(
        unsafe_result,
        platform_name="posix",
        effective_uid=1000,
    ) is False
    assert long_media._is_private_owned_regular_file(
        safe_result,
        platform_name="posix",
        effective_uid=1000,
    ) is True


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO unavailable")
def test_artifact_reuse_rejects_fifo_without_opening_it(tmp_path: Path) -> None:
    checkpoint = _checkpoint(tmp_path)
    part = checkpoint.parts[0]
    artifact_path = tmp_path / part.artifact.relative_path
    artifact_path.unlink()
    os.mkfifo(artifact_path)

    assert long_media.validate_reusable_part(
        checkpoint,
        part_id=part.part_id,
        workspace=tmp_path,
        ffprobe_evidence=_probe(),
        **_identity(),
    ) is None


@pytest.mark.parametrize(
    ("duration_ms", "ffprobe_evidence"),
    [
        (
            1,
            {
                "duration_ms": True,
                "width": True,
                "height": True,
                "container": "mp4",
                "byte_count": True,
            },
        ),
        (
            1_000,
            {
                "format": {"duration": True, "format_name": "mp4", "size": True},
                "streams": [{"codec_type": "video", "width": True, "height": True}],
            },
        ),
    ],
)
def test_ffprobe_boolean_numbers_cannot_validate_non_media_bytes(
    tmp_path: Path, duration_ms, ffprobe_evidence
) -> None:
    identity = _identity()
    payload = b"x"
    artifact = _artifact(tmp_path / f"tiny-{duration_ms}.mp4", payload)
    artifact = long_media.ArtifactEvidence(
        relative_path=artifact.relative_path,
        sha256=artifact.sha256,
        byte_count=artifact.byte_count,
        duration_ms=duration_ms,
        width=1,
        height=1,
        container="mp4",
    )
    part = long_media.PartCheckpoint(
        part_id=long_media.stable_part_id(index=0, start_ms=0, end_ms=duration_ms),
        index=0,
        start_ms=0,
        end_ms=duration_ms,
        artifact=artifact,
        stage="validated",
    )
    checkpoint = long_media.LongMediaCheckpoint(
        **identity,
        execution_class="segment_safe",
        stage="rendering",
        progress=long_media.ProgressState(
            stage="rendering", completed_units=1, total_units=1, unit="parts"
        ),
        parts=(part,),
    )

    assert long_media.validate_reusable_part(
        checkpoint,
        part_id=part.part_id,
        workspace=tmp_path,
        ffprobe_evidence=ffprobe_evidence,
        **identity,
    ) is None


def test_raw_ffprobe_duration_and_size_strings_remain_valid_evidence(tmp_path: Path) -> None:
    checkpoint = _checkpoint(tmp_path)
    part = checkpoint.parts[0]
    evidence = {
        "format": {
            "duration": "2.000",
            "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
            "size": str(part.artifact.byte_count),
        },
        "streams": [{"codec_type": "video", "width": "1920", "height": "1080"}],
        "sha256": part.artifact.sha256,
    }

    assert long_media.validate_reusable_part(
        checkpoint,
        part_id=part.part_id,
        workspace=tmp_path,
        ffprobe_evidence=evidence,
        **_identity(),
    ) == part


@pytest.mark.parametrize(
    ("checkpoint_stage", "allowed_part_stages"),
    [
        ("created", {"planned"}),
        ("admitted", {"planned"}),
        ("downloading", {"planned"}),
        ("downloaded", {"planned"}),
        ("rendering", {"planned", "rendering", "validated"}),
        ("validating", {"rendering", "validated"}),
        ("canonical_ready", {"validated"}),
        ("delivery_ready", {"validated"}),
        ("completed", {"validated"}),
        ("failed", {"planned", "rendering", "validated"}),
    ],
)
def test_checkpoint_stage_has_explicit_part_stage_relation(
    tmp_path: Path, checkpoint_stage: str, allowed_part_stages: set[str]
) -> None:
    for part_stage in ("planned", "rendering", "validated"):
        if part_stage in allowed_part_stages:
            checkpoint = _checkpoint_with_part_stage(
                tmp_path,
                checkpoint_stage=checkpoint_stage,
                part_stage=part_stage,
            )
            assert checkpoint.parts[0].stage == part_stage
        else:
            with pytest.raises(ValueError):
                _checkpoint_with_part_stage(
                    tmp_path,
                    checkpoint_stage=checkpoint_stage,
                    part_stage=part_stage,
                )


@pytest.mark.parametrize(
    ("completed_units", "total_units"),
    [(1, 4), (0, 0)],
)
def test_completed_checkpoint_requires_truthfully_finished_real_progress(
    tmp_path: Path,
    completed_units: int,
    total_units: int,
) -> None:
    value = _checkpoint_with_part_stage(
        tmp_path,
        checkpoint_stage="completed",
        part_stage="validated",
    ).to_mapping()
    value["progress"]["completed_units"] = completed_units
    value["progress"]["total_units"] = total_units

    with pytest.raises(ValueError):
        long_media.LongMediaCheckpoint.from_mapping(value)


def test_any_canonical_artifact_requires_all_parts_validated(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        _checkpoint_with_part_stage(
            tmp_path,
            checkpoint_stage="failed",
            part_stage="rendering",
            include_canonical=True,
        )


def test_whole_timeline_checkpoint_allows_only_one_stable_part(tmp_path: Path) -> None:
    checkpoint = _checkpoint(tmp_path, canonical=False)
    part = checkpoint.parts[0]
    with pytest.raises(ValueError):
        long_media.LongMediaCheckpoint(
            project_key=checkpoint.project_key,
            source_sha256=checkpoint.source_sha256,
            plan_hash=checkpoint.plan_hash,
            revision=checkpoint.revision,
            output_index=checkpoint.output_index,
            execution_class="whole_timeline_required",
            stage="rendering",
            progress=checkpoint.progress,
            parts=(part, part),
            delivery=long_media.DeliveryCursor(),
        )


@pytest.mark.parametrize("checkpoint_stage", ["canonical_ready", "delivery_ready", "completed"])
def test_whole_timeline_final_stages_require_one_full_validated_part(
    tmp_path: Path, checkpoint_stage: str
) -> None:
    value = _checkpoint_with_part_stage(
        tmp_path,
        checkpoint_stage=checkpoint_stage,
        part_stage="validated",
    ).to_mapping()
    value["execution_class"] = "whole_timeline_required"

    valid = long_media.LongMediaCheckpoint.from_mapping(value)
    assert valid.parts[0].index == 0
    assert valid.parts[0].start_ms == 0
    assert valid.parts[0].end_ms == valid.parts[0].artifact.duration_ms

    partial = {**value, "parts": [dict(value["parts"][0])]}
    partial["parts"][0]["end_ms"] = 1_000
    partial["parts"][0]["part_id"] = long_media.stable_part_id(
        index=0, start_ms=0, end_ms=1_000
    )
    with pytest.raises(ValueError):
        long_media.LongMediaCheckpoint.from_mapping(partial)

    no_parts = {**value, "parts": []}
    with pytest.raises(ValueError):
        long_media.LongMediaCheckpoint.from_mapping(no_parts)


@pytest.mark.parametrize("part_stage", ["planned", "rendering"])
def test_whole_timeline_rendering_allows_one_unfinished_part(
    tmp_path: Path, part_stage: str
) -> None:
    value = _checkpoint_with_part_stage(
        tmp_path,
        checkpoint_stage="rendering",
        part_stage=part_stage,
    ).to_mapping()
    value["execution_class"] = "whole_timeline_required"

    checkpoint = long_media.LongMediaCheckpoint.from_mapping(value)
    assert checkpoint.parts[0].stage == part_stage


def test_whole_timeline_rendering_rejects_future_validated_part(tmp_path: Path) -> None:
    value = _checkpoint_with_part_stage(
        tmp_path,
        checkpoint_stage="rendering",
        part_stage="validated",
    ).to_mapping()
    value["execution_class"] = "whole_timeline_required"

    with pytest.raises(ValueError):
        long_media.LongMediaCheckpoint.from_mapping(value)


@pytest.mark.parametrize("parts", [[], None])
def test_failed_whole_timeline_canonical_requires_exact_validated_full_range_part(
    tmp_path: Path, parts
) -> None:
    value = _checkpoint(tmp_path).to_mapping()
    value["execution_class"] = "whole_timeline_required"
    value["stage"] = "failed"
    value["progress"]["stage"] = "failed"
    if parts is None:
        partial = dict(value["parts"][0])
        partial["end_ms"] = 1_000
        partial["part_id"] = long_media.stable_part_id(index=0, start_ms=0, end_ms=1_000)
        value["parts"] = [partial]
    else:
        value["parts"] = parts

    with pytest.raises(ValueError):
        long_media.LongMediaCheckpoint.from_mapping(value)


def test_recovery_refuses_failed_whole_timeline_canonical_without_full_range_part(
    tmp_path: Path,
) -> None:
    checkpoint = _checkpoint(tmp_path)
    object.__setattr__(checkpoint, "execution_class", "whole_timeline_required")
    object.__setattr__(checkpoint, "stage", "failed")
    object.__setattr__(
        checkpoint,
        "progress",
        long_media.ProgressState(stage="failed", completed_units=1, total_units=1, unit="parts"),
    )
    object.__setattr__(checkpoint, "parts", ())

    decision = long_media.recover_canonical_output(
        checkpoint, workspace=tmp_path, ffprobe_evidence=_probe(), **_identity()
    )

    assert decision.allowed is False
    assert decision.reason == "canonical_invalid"


@pytest.mark.parametrize("deterministic", ["false", 1])
def test_delivery_cursor_mapping_requires_exact_boolean_determinism(deterministic) -> None:
    value = long_media.DeliveryCursor(
        state="rejected",
        attempt_id="attempt-1",
        deterministic=True,
        rejection_code="video_not_supported",
    ).to_mapping()
    value["deterministic"] = deterministic

    with pytest.raises(ValueError):
        long_media.DeliveryCursor.from_mapping(value)


def test_delivery_cursor_advances_only_through_exact_delivery_edges() -> None:
    not_started = long_media.DeliveryCursor(output_index=2)
    sending = long_media.DeliveryCursor(
        state="sending", output_index=2, attempt_id="attempt-2"
    )
    accepted = long_media.DeliveryCursor(
        state="accepted",
        output_index=2,
        attempt_id="attempt-2",
        message_id="102",
        file_id="file-2",
    )
    delivered = long_media.DeliveryCursor(
        state="delivered",
        output_index=2,
        attempt_id="attempt-2",
        message_id="102",
        file_id="file-2",
    )

    assert long_media.advance_delivery_cursor(not_started, sending) is sending
    assert long_media.advance_delivery_cursor(sending, accepted) is accepted
    assert long_media.advance_delivery_cursor(accepted, delivered) is delivered
    assert long_media.advance_delivery_cursor(delivered, delivered) is delivered


@pytest.mark.parametrize(
    ("current", "proposed"),
    [
        (
            long_media.DeliveryCursor(state="sending", attempt_id="attempt-1"),
            long_media.DeliveryCursor(),
        ),
        (
            long_media.DeliveryCursor(state="sending", attempt_id="attempt-1"),
            long_media.DeliveryCursor(
                state="accepted",
                attempt_id="attempt-2",
                message_id="101",
                file_id="file-1",
            ),
        ),
        (
            long_media.DeliveryCursor(state="sending", output_index=1, attempt_id="attempt-1"),
            long_media.DeliveryCursor(
                state="unknown", output_index=2, attempt_id="attempt-1"
            ),
        ),
        (
            long_media.DeliveryCursor(
                state="rejected",
                attempt_id="attempt-1",
                deterministic=True,
                rejection_code="unsupported",
            ),
            long_media.DeliveryCursor(state="sending", attempt_id="attempt-1"),
        ),
        (
            long_media.DeliveryCursor(state="unknown", attempt_id="attempt-1"),
            long_media.DeliveryCursor(state="unknown", attempt_id="attempt-2"),
        ),
    ],
)
def test_delivery_cursor_rejects_regression_identity_drift_and_terminal_mutation(
    current: long_media.DeliveryCursor,
    proposed: long_media.DeliveryCursor,
) -> None:
    with pytest.raises(ValueError, match="delivery cursor transition rejected"):
        long_media.advance_delivery_cursor(current, proposed)


@pytest.mark.parametrize(
    ("delivery", "allowed"),
    [
        (long_media.DeliveryCursor(), True),
        (
            long_media.DeliveryCursor(
                state="rejected",
                attempt_id="attempt-1",
                deterministic=True,
                rejection_code="video_not_supported",
            ),
            True,
        ),
        (long_media.DeliveryCursor(state="sending", attempt_id="attempt-1"), False),
        (long_media.DeliveryCursor(state="unknown", attempt_id="attempt-1"), False),
        (
            long_media.DeliveryCursor(
                state="accepted",
                attempt_id="attempt-1",
                message_id="101",
                file_id="file-1",
            ),
            False,
        ),
        (
            long_media.DeliveryCursor(
                state="delivered",
                attempt_id="attempt-1",
                message_id="101",
                file_id="file-1",
            ),
            False,
        ),
    ],
)
def test_canonical_recovery_validates_artifact_and_fences_delivery(
    tmp_path: Path, delivery: long_media.DeliveryCursor, allowed: bool
) -> None:
    checkpoint = _checkpoint(tmp_path, delivery=delivery)

    decision = long_media.recover_canonical_output(
        checkpoint,
        workspace=tmp_path,
        ffprobe_evidence=_probe(),
        **_identity(),
    )

    assert decision.allowed is allowed
    if allowed:
        assert decision.artifact == checkpoint.canonical
    else:
        assert decision.reason == "delivery_fenced"


def test_canonical_recovery_rejects_mismatched_actual_artifact(tmp_path: Path) -> None:
    checkpoint = _checkpoint(tmp_path)
    (tmp_path / checkpoint.canonical.relative_path).write_bytes(b"wrong")

    decision = long_media.recover_canonical_output(
        checkpoint,
        workspace=tmp_path,
        ffprobe_evidence=_probe(),
        **_identity(),
    )

    assert decision.allowed is False
    assert decision.reason == "canonical_invalid"


def test_progress_advances_real_units_without_regression_or_terminal_overwrite() -> None:
    current = long_media.ProgressState(
        stage="rendering", completed_units=1, total_units=4, unit="parts"
    )
    advanced = long_media.advance_progress(current, stage="rendering", completed_units=2)
    terminal = long_media.advance_progress(
        advanced, stage="failed", detail="render_failed"
    )

    assert advanced.completed_units == 2
    assert not hasattr(advanced, "percentage")
    with pytest.raises(ValueError):
        long_media.advance_progress(advanced, stage="downloaded")
    with pytest.raises(ValueError):
        long_media.advance_progress(advanced, stage="rendering", completed_units=1)
    with pytest.raises(ValueError):
        long_media.advance_progress(terminal, stage="failed", detail="different")


@pytest.mark.parametrize(
    ("completed_units", "total_units"),
    [(1, 4), (0, 0)],
)
def test_public_progress_state_rejects_unfinished_completed_evidence(
    completed_units: int,
    total_units: int,
) -> None:
    with pytest.raises(ValueError):
        long_media.ProgressState(
            stage="completed",
            completed_units=completed_units,
            total_units=total_units,
            unit="parts",
        )


@pytest.mark.parametrize(
    ("completed_units", "total_units"),
    [(1, 4), (0, 0)],
)
def test_public_progress_helper_rejects_unfinished_completed_evidence(
    completed_units: int,
    total_units: int,
) -> None:
    current = long_media.ProgressState(
        stage="delivery_ready",
        completed_units=completed_units,
        total_units=total_units,
        unit="parts",
    )

    with pytest.raises(ValueError):
        long_media.advance_progress(current, stage="completed")


@pytest.mark.parametrize("terminal_stage", ["completed", "failed"])
def test_terminal_checkpoint_rejects_liveness_mutation(
    tmp_path: Path,
    terminal_stage: str,
) -> None:
    if terminal_stage == "completed":
        checkpoint = _checkpoint_with_part_stage(
            tmp_path,
            checkpoint_stage="completed",
            part_stage="validated",
        )
    else:
        value = _checkpoint(tmp_path, canonical=False).to_mapping()
        value["stage"] = "failed"
        value["progress"]["stage"] = "failed"
        checkpoint = long_media.LongMediaCheckpoint.from_mapping(value)

    with pytest.raises(ValueError):
        long_media.advance_checkpoint(
            checkpoint,
            stage=terminal_stage,
            liveness_epoch_ms=checkpoint.liveness_epoch_ms + 1,
        )


def test_same_stage_progress_rejects_unit_change() -> None:
    current = long_media.ProgressState(
        stage="rendering", completed_units=2, total_units=4, unit="parts"
    )

    with pytest.raises(ValueError):
        long_media.advance_progress(current, stage="rendering", unit="frames")


def test_same_stage_progress_rejects_total_unit_regression() -> None:
    current = long_media.ProgressState(
        stage="rendering", completed_units=2, total_units=4, unit="parts"
    )

    with pytest.raises(ValueError):
        long_media.advance_progress(current, stage="rendering", total_units=3)


def test_same_stage_progress_allows_truthful_total_discovery_and_growth() -> None:
    unknown = long_media.ProgressState(
        stage="rendering", completed_units=0, total_units=0, unit="parts"
    )
    known = long_media.advance_progress(unknown, stage="rendering", total_units=4)
    grown = long_media.advance_progress(
        known, stage="rendering", completed_units=1, total_units=5
    )

    assert known.total_units == 4
    assert grown.completed_units == 1
    assert grown.total_units == 5
    assert grown.unit == "parts"


@pytest.mark.parametrize("stage", ["validating", "failed"])
def test_progress_rejects_resetting_real_evidence_during_stage_transition(stage: str) -> None:
    current = long_media.ProgressState(
        stage="rendering", completed_units=3, total_units=4, unit="parts"
    )

    with pytest.raises(ValueError):
        long_media.advance_progress(
            current, stage=stage, completed_units=0, total_units=0
        )


def test_progress_rejects_same_unit_regression_during_forward_stage_transition() -> None:
    current = long_media.ProgressState(
        stage="rendering", completed_units=3, total_units=4, unit="parts"
    )

    with pytest.raises(ValueError):
        long_media.advance_progress(
            current, stage="validating", completed_units=2, total_units=3
        )


def test_progress_allows_truthful_new_unit_only_during_real_forward_stage_transition() -> None:
    current = long_media.ProgressState(
        stage="rendering", completed_units=3, total_units=4, unit="parts"
    )

    advanced = long_media.advance_progress(
        current, stage="validating", completed_units=0, total_units=120, unit="frames"
    )

    assert advanced.stage == "validating"
    assert (advanced.completed_units, advanced.total_units, advanced.unit) == (0, 120, "frames")


def test_progress_new_unit_transition_requires_explicit_completed_units() -> None:
    current = long_media.ProgressState(
        stage="rendering", completed_units=3, total_units=4, unit="parts"
    )

    with pytest.raises(ValueError):
        long_media.advance_progress(
            current, stage="validating", total_units=120, unit="frames"
        )
