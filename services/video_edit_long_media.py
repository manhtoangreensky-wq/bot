"""Pure long-media policy and durable checkpoint evidence for Video Edit.

This module owns no transport, FFmpeg, Telegram, or SubDub behavior.  Callers
must supply normalized FFprobe evidence and remain responsible for durable job
ownership and delivery receipts.  A checkpoint can prove reusable local work;
it can never authorize a delivery.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import hashlib
from ipaddress import IPv6Address, ip_address
import json
import math
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import secrets
import stat
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence

from services import video_edit_media_transport as media_transport


SCHEMA_VERSION = 1
PROJECT_KEY_DOMAIN = "toan-aas:video-edit:long-media:v1"
MAX_POLICY_INTEGER = 2**63 - 1
DEFAULT_WORKSPACE_RESERVE_BYTES = 512 * 1024 * 1024
MAX_CANONICAL_TREE_DEPTH = 32
MAX_CANONICAL_TREE_NODES = 10_000
MAX_CANONICAL_COLLECTION_SIZE = 10_000
MAX_CHECKPOINT_BYTES = 4 * 1024 * 1024
DESCRIPTOR_READ_BYTES = 1024 * 1024
_REPARSE_POINT = 0x400
SEGMENT_SAFE = "segment_safe"
WHOLE_TIMELINE_REQUIRED = "whole_timeline_required"

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.@-]{0,127}$")
_SAFE_TEXT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:+, -]{0,127}$")
_CONTAINER_RE = re.compile(r"^[a-z0-9][a-z0-9_.+,-]{0,63}$")
_BOT_TOKEN_RE = re.compile(r"(?<![0-9])[0-9]{5,}:[A-Za-z0-9_-]{20,}(?![A-Za-z0-9_-])")
_URL_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://")
_SCHEMELESS_URL_RE = re.compile(
    r"(?<![A-Za-z0-9_-])(?:[A-Za-z0-9._%+-]+@)?"
    r"(?:(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,62})\.)+"
    r"(?=[A-Za-z0-9-]*[A-Za-z])[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?|"
    r"(?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])"
    r"(?:\.(?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])){3})"
    r"(?::[0-9]{1,5})?(?:/[^\x00-\x20<>\"]*)?(?![A-Za-z0-9._-])"
)
_LOCALHOST_URL_RE = re.compile(
    r"(?<![A-Za-z0-9_-])localhost(?::[0-9]{1,5})?"
    r"(?:/[^\x00-\x20<>\"]*)?(?![A-Za-z0-9._-])",
    re.IGNORECASE,
)
_BRACKETED_HOST_RE = re.compile(
    r"\[[0-9A-Fa-f:.%]+\](?::[0-9]{1,5})?(?:/[^\x00-\x20<>\"]*)?"
)
_TRAILING_DOT_HOST_RE = re.compile(
    r"(?<![A-Za-z0-9_-])(?:"
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,62})\.)+"
    r"(?=[A-Za-z0-9-]*[A-Za-z])[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\."
    r"|(?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])"
    r"(?:\.(?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])){3}\.)"
    r"(?::[0-9]{1,5})?(?:/[^\x00-\x20<>\"]*)?(?![A-Za-z0-9._-])"
)
_UNBRACKETED_IPV6_HOST_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_.:%-])"
    r"(?P<host>[0-9A-Fa-f:.]+(?:%[A-Za-z0-9_.~-]+)?)/"
)
_SAFE_RELATIVE_FILE_SUFFIXES = frozenset(
    {
        ".aac",
        ".ass",
        ".avi",
        ".flac",
        ".gif",
        ".jpeg",
        ".jpg",
        ".m4a",
        ".mkv",
        ".mov",
        ".mp3",
        ".mp4",
        ".png",
        ".srt",
        ".svg",
        ".wav",
        ".webm",
        ".webp",
    }
)
_SECRET_KEY_RE = re.compile(
    r"bot[_-]?token|token|secret|password|authorization|api[_-]?key|cookie|"
    r"proxy[_-]?secret|telegram[_-]?url|worker[_-]?path",
    re.IGNORECASE,
)

_STAGES = (
    "created",
    "admitted",
    "downloading",
    "downloaded",
    "rendering",
    "validating",
    "canonical_ready",
    "delivery_ready",
    "completed",
)
_STAGE_ORDER = {name: index for index, name in enumerate(_STAGES)}
_TERMINAL_STAGES = frozenset({"completed", "failed"})
_PART_STAGES = frozenset({"planned", "rendering", "validated"})
_PART_STAGES_BY_CHECKPOINT_STAGE = {
    "created": frozenset({"planned"}),
    "admitted": frozenset({"planned"}),
    "downloading": frozenset({"planned"}),
    "downloaded": frozenset({"planned"}),
    "rendering": _PART_STAGES,
    "validating": frozenset({"rendering", "validated"}),
    "canonical_ready": frozenset({"validated"}),
    "delivery_ready": frozenset({"validated"}),
    "completed": frozenset({"validated"}),
    "failed": _PART_STAGES,
}
_DELIVERY_STATES = frozenset(
    {"not_started", "sending", "unknown", "rejected", "accepted", "delivered"}
)
_DISABLED_AUDIO_NORMALIZATION = frozenset(
    {"", "0", "disabled", "false", "keep", "none", "off"}
)

_GLOBAL_MARKERS = frozenset(
    {
        "concat",
        "concat_inputs",
        "concat_order",
        "join",
        "merge",
        "reorder",
        "ordering",
        "transition",
        "transitions",
        "crossfade",
        "xfade",
        "audio_loudnorm",
        "loudnorm",
        "audio_analysis",
        "whole_track",
        "whole_timeline",
        "timeline_global",
        "boundary_blend",
        "boundary_crossing",
        "global_analysis",
        "fade_in_ms",
        "fade_out_ms",
        "slow_zoom",
    }
)
_SAFE_OPERATIONS = frozenset(
    {
        "split",
        "split_fixed",
        "split_count",
        "split_custom",
        "cut",
        "trim",
        "trim_edges",
        "trim_range",
        "remove_middle",
        "crop",
        "crop_or_fit",
        "scale",
        "resize",
        "aspect",
        "resolution",
        "rotate",
        "rotation",
        "flip",
        "speed",
        "volume",
        "overlay",
        "text_overlay",
        "logo",
        "logo_overlay",
        "watermark",
        "subtitle",
        "subtitle_file",
        "srt",
        "color",
        "color_preset",
        "brightness",
        "brightness_percent",
        "contrast",
        "saturation",
        "sharpen",
        "denoise",
        "vignette",
        "fps",
        "transcode",
    }
)
_STRUCTURAL_KEYS = frozenset({"operation", "operations", "kind", "action", "type"})
_PARAMETER_KEYS = frozenset(
    {
        "count",
        "ranges",
        "range",
        "start",
        "end",
        "start_ms",
        "end_ms",
        "duration_ms",
        "value",
        "enabled",
        "quality",
        "codec",
        "video_codec",
        "audio_codec",
        "container",
        "format",
        "preset",
        "level",
        "mode",
        "x",
        "y",
        "width",
        "height",
        "position",
        "opacity",
        "font",
        "font_size",
        "text",
        "color_value",
        "background",
        "input_video",
        "output_format",
        "aspect_ratio",
        "quality_filters",
        "local_effects",
        "content",
        "outline",
        "path",
        "font_path",
        "source",
        "asset",
        "assets",
        "output_count",
        "outputs",
        "settings",
        "options",
        "plan",
    }
)

_WORKSPACE_PROFILES = {
    # scratch numerator/denominator, output numerator/denominator
    "manual": (1, 2, 6, 5),
    "concat": (3, 2, 6, 5),
    "split": (1, 2, 11, 10),
    "overlay": (1, 1, 5, 4),
    "transcode": (3, 2, 3, 2),
}


class CheckpointError(RuntimeError):
    """A safe, classified checkpoint validation or persistence failure."""

    def __init__(self, reason: str) -> None:
        self.reason = str(reason or "checkpoint_error")
        super().__init__(f"video edit checkpoint failed: {self.reason}")


def _contains_control(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


def _looks_absolute_path(value: str) -> bool:
    return PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute()


def _contains_unbracketed_ipv6_host_path(value: str) -> bool:
    for match in _UNBRACKETED_IPV6_HOST_PATH_RE.finditer(value):
        try:
            address = ip_address(match.group("host"))
        except ValueError:
            continue
        if isinstance(address, IPv6Address):
            return True
    return False


def _schemeless_match_is_fractional_timestamp(value: str, match: re.Match[str]) -> bool:
    return bool(
        re.search(r"(?:^|\s)[0-9]{1,2}:[0-9]{2}:$", value[: match.start()])
        and re.match(r"[0-9]{2}\.[0-9]+/", match.group(0))
    )


def _contains_schemeless_url(value: str) -> bool:
    if (
        _LOCALHOST_URL_RE.search(value)
        or _BRACKETED_HOST_RE.search(value)
        or _TRAILING_DOT_HOST_RE.search(value)
        or _contains_unbracketed_ipv6_host_path(value)
    ):
        return True
    for match in _SCHEMELESS_URL_RE.finditer(value):
        if _schemeless_match_is_fractional_timestamp(value, match):
            continue
        candidate = match.group(0)
        if any(marker in candidate for marker in ("@", ":", "/")):
            return True
        if PurePosixPath(candidate).suffix.lower() not in _SAFE_RELATIVE_FILE_SUFFIXES:
            return True
    return False


def _validate_safe_string(value: str, *, reject_absolute_path: bool) -> None:
    candidate = value.strip()
    if (
        _contains_control(value)
        or _URL_RE.search(value)
        or "//" in value
        or _contains_schemeless_url(value)
        or _BOT_TOKEN_RE.search(value)
    ):
        raise ValueError("unsafe text")
    if reject_absolute_path and _looks_absolute_path(candidate):
        raise ValueError("unsafe path")


def _validate_safe_tree(value: Any, *, reject_absolute_paths: bool) -> None:
    """Validate canonical JSON inputs without unbounded recursive traversal."""

    pending = [(value, 0)]
    node_count = 0
    while pending:
        current, depth = pending.pop()
        node_count += 1
        if node_count > MAX_CANONICAL_TREE_NODES:
            raise ValueError("canonical tree exceeds node budget")
        if depth > MAX_CANONICAL_TREE_DEPTH:
            raise ValueError("canonical tree exceeds depth budget")
        if current is None or isinstance(current, bool):
            continue
        if isinstance(current, str):
            _validate_safe_string(current, reject_absolute_path=reject_absolute_paths)
            continue
        if isinstance(current, int) and not isinstance(current, bool):
            if current < -MAX_POLICY_INTEGER or current > MAX_POLICY_INTEGER:
                raise ValueError("integer out of range")
            continue
        if isinstance(current, float):
            if not math.isfinite(current):
                raise ValueError("non-finite number")
            continue
        if isinstance(current, Mapping):
            if len(current) > MAX_CANONICAL_COLLECTION_SIZE:
                raise ValueError("canonical collection exceeds size budget")
            for key, item in current.items():
                if not isinstance(key, str) or not key or _contains_control(key):
                    raise ValueError("invalid mapping key")
                if _SECRET_KEY_RE.search(key):
                    raise ValueError("secret-like mapping key")
                pending.append((item, depth + 1))
            continue
        if isinstance(current, (list, tuple)):
            if len(current) > MAX_CANONICAL_COLLECTION_SIZE:
                raise ValueError("canonical collection exceeds size budget")
            pending.extend((item, depth + 1) for item in current)
            continue
        raise ValueError("unsupported value")


def _canonical_json_bytes(value: Mapping[str, Any], *, checkpoint: bool) -> bytes:
    if not isinstance(value, Mapping):
        raise ValueError("mapping required")
    try:
        _validate_safe_tree(value, reject_absolute_paths=checkpoint)
        encoded = json.dumps(
            dict(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError):
        raise ValueError("invalid canonical JSON") from None
    return encoded


def canonical_plan_hash(plan: Mapping[str, Any]) -> str:
    """Return SHA-256 of compact, key-sorted, UTF-8 plan JSON."""

    return hashlib.sha256(_canonical_json_bytes(plan, checkpoint=False)).hexdigest()


def _exact_string(value: Any, name: str) -> str:
    if type(value) is not str:
        raise ValueError(f"invalid {name}")
    return value


def _validate_hash(value: Any, name: str) -> str:
    normalized = _exact_string(value, name).strip().lower()
    if not _HASH_RE.fullmatch(normalized):
        raise ValueError(f"invalid {name}")
    return normalized


def _nonnegative_integer(value: Any, name: str, *, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"invalid {name}")
    if value < (1 if positive else 0) or value > MAX_POLICY_INTEGER:
        raise ValueError(f"invalid {name}")
    return value


def project_key(
    *,
    user_id: str,
    source_sha256: str,
    plan: Mapping[str, Any],
    revision: int,
    output_index: int = 0,
) -> str:
    """Bind one output revision to its exact source and canonical edit plan."""

    user = str(user_id or "").strip()
    if not _SAFE_ID_RE.fullmatch(user):
        raise ValueError("invalid user_id")
    _validate_safe_string(user, reject_absolute_path=True)
    source_hash = _validate_hash(source_sha256, "source_sha256")
    revision_value = _nonnegative_integer(revision, "revision", positive=True)
    output_value = _nonnegative_integer(output_index, "output_index")
    plan_hash = canonical_plan_hash(plan)
    material = (
        f"{PROJECT_KEY_DOMAIN}\n{user}\n{source_hash}\n{plan_hash}\n"
        f"{revision_value}\n{output_value}"
    ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _normalized_operation(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def _active(value: Any) -> bool:
    return value not in (None, False, "", (), [], {})


def _classify_node(
    value: Any, *, top_level: bool = False, strict_unknown: bool = False
) -> tuple[bool, bool]:
    """Return ``(global_or_unknown, saw_safe_operation)`` for one plan node."""

    if isinstance(value, Mapping):
        saw_safe = False
        for raw_key, item in value.items():
            key = _normalized_operation(raw_key)
            if not key:
                return True, saw_safe
            if key == "audio_normalization":
                if _normalized_operation(item) not in _DISABLED_AUDIO_NORMALIZATION:
                    return True, saw_safe
                continue
            if key in _GLOBAL_MARKERS:
                if _active(item):
                    return True, saw_safe
                continue
            if key in _SAFE_OPERATIONS and _active(item):
                saw_safe = True
            if key in _STRUCTURAL_KEYS:
                declared = item if isinstance(item, (list, tuple)) else (item,)
                for operation in declared:
                    if isinstance(operation, Mapping):
                        bad, nested_safe = _classify_node(operation, strict_unknown=True)
                        if bad:
                            return True, saw_safe or nested_safe
                        saw_safe = saw_safe or nested_safe
                        continue
                    normalized = _normalized_operation(operation)
                    if normalized in _GLOBAL_MARKERS:
                        return True, saw_safe
                    if normalized in _SAFE_OPERATIONS:
                        saw_safe = True
                    elif normalized:
                        return True, saw_safe
                continue
            if isinstance(item, (Mapping, list, tuple)):
                bad, nested_safe = _classify_node(
                    item,
                    strict_unknown=key in {"operation", "operations", "settings", "options"},
                )
                if bad:
                    return True, saw_safe or nested_safe
                saw_safe = saw_safe or nested_safe
            if key not in _SAFE_OPERATIONS and key not in _PARAMETER_KEYS:
                return True, saw_safe
        return False, saw_safe
    if isinstance(value, (list, tuple)):
        saw_safe = False
        for item in value:
            if not isinstance(item, (Mapping, list, tuple)) and not strict_unknown:
                continue
            bad, nested_safe = _classify_node(item, strict_unknown=strict_unknown)
            if bad:
                return True, saw_safe or nested_safe
            saw_safe = saw_safe or nested_safe
        return False, saw_safe
    if strict_unknown:
        if isinstance(value, str):
            normalized = _normalized_operation(value)
            if normalized in _SAFE_OPERATIONS:
                return False, True
        return True, False
    return False, False


def classify_plan_execution(plan: Mapping[str, Any]) -> str:
    """Classify only proven segment-local plans as safe to partition."""

    if not isinstance(plan, Mapping):
        return WHOLE_TIMELINE_REQUIRED
    try:
        _canonical_json_bytes(plan, checkpoint=False)
    except ValueError:
        return WHOLE_TIMELINE_REQUIRED
    unsafe, saw_safe = _classify_node(plan, top_level=True)
    return SEGMENT_SAFE if saw_safe and not unsafe else WHOLE_TIMELINE_REQUIRED


def _checked_add(*values: int) -> int:
    total = 0
    for value in values:
        if value < 0 or total > MAX_POLICY_INTEGER - value:
            raise ValueError("workspace estimate overflow")
        total += value
    return total


def _checked_ratio(value: int, numerator: int, denominator: int) -> int:
    if value and numerator > MAX_POLICY_INTEGER // value:
        raise ValueError("workspace estimate overflow")
    multiplied = value * numerator
    result = (multiplied + denominator - 1) // denominator
    if result > MAX_POLICY_INTEGER:
        raise ValueError("workspace estimate overflow")
    return result


def _asset_sizes(asset_bytes: Iterable[int] | int) -> tuple[int, ...]:
    if isinstance(asset_bytes, bool):
        raise ValueError("invalid asset_bytes")
    values: Iterable[Any]
    if isinstance(asset_bytes, int):
        values = (asset_bytes,)
    else:
        try:
            values = tuple(asset_bytes)
        except TypeError:
            raise ValueError("invalid asset_bytes") from None
    return tuple(_nonnegative_integer(item, "asset_bytes") for item in values)


@dataclass(frozen=True)
class WorkspaceEstimate:
    operation: str
    source_bytes: int
    asset_bytes: int
    output_count: int
    scratch_bytes: int
    output_bytes: int
    estimated_bytes: int
    reserve_bytes: int
    required_bytes: int


@dataclass(frozen=True)
class AdmissionDecision:
    accepted: bool
    reason: str
    evidence: Mapping[str, int | str | bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        reason = str(self.reason or "invalid_input")
        if not _SAFE_TEXT_RE.fullmatch(reason):
            raise ValueError("invalid admission reason")
        object.__setattr__(self, "reason", reason)
        object.__setattr__(self, "evidence", MappingProxyType(dict(self.evidence)))


def estimate_workspace(
    *,
    operation: str,
    source_bytes: int,
    asset_bytes: Iterable[int] | int = (),
    output_count: int = 1,
    reserve_bytes: int = DEFAULT_WORKSPACE_RESERVE_BYTES,
) -> WorkspaceEstimate:
    """Return a deterministic operation-aware disk estimate with checked math."""

    operation_value = _normalized_operation(operation)
    if operation_value not in _WORKSPACE_PROFILES:
        raise ValueError("invalid operation")
    source_value = _nonnegative_integer(source_bytes, "source_bytes")
    if source_value == 0:
        raise ValueError("invalid source_bytes")
    assets = _asset_sizes(asset_bytes)
    output_value = _nonnegative_integer(output_count, "output_count", positive=True)
    reserve_value = _nonnegative_integer(reserve_bytes, "reserve_bytes")
    asset_total = _checked_add(*assets)
    input_total = _checked_add(source_value, asset_total)
    scratch_num, scratch_den, output_num, output_den = _WORKSPACE_PROFILES[
        operation_value
    ]
    scratch = _checked_ratio(input_total, scratch_num, scratch_den)
    output_basis = input_total if operation_value == "concat" else source_value
    per_output = _checked_ratio(output_basis, output_num, output_den)
    output = (
        per_output
        if operation_value == "split"
        else _checked_ratio(per_output, output_value, 1)
    )
    per_extra_output = 1024 * 1024
    output_overhead = _checked_ratio(output_value - 1, per_extra_output, 1)
    output = _checked_add(output, output_overhead)
    estimated = _checked_add(input_total, scratch, output)
    required = _checked_add(estimated, reserve_value)
    return WorkspaceEstimate(
        operation=operation_value,
        source_bytes=source_value,
        asset_bytes=asset_total,
        output_count=output_value,
        scratch_bytes=scratch,
        output_bytes=output,
        estimated_bytes=estimated,
        reserve_bytes=reserve_value,
        required_bytes=required,
    )


def admit_workspace(
    *,
    operation: str,
    source_bytes: int | None,
    asset_bytes: Iterable[int | None] | int | None = (),
    output_count: int | None = 1,
    free_bytes: int | None,
    reserve_bytes: int = DEFAULT_WORKSPACE_RESERVE_BYTES,
    emergency_cap_bytes: int = 0,
) -> AdmissionDecision:
    """Make a pre-side-effect disk decision without a public media-size ceiling."""

    if source_bytes is None or source_bytes == 0:
        return AdmissionDecision(False, "unknown_source_size", {"size_known": False})
    if asset_bytes is None:
        return AdmissionDecision(False, "unknown_asset_size", {"size_known": False})
    try:
        raw_assets = (asset_bytes,) if isinstance(asset_bytes, int) else tuple(asset_bytes)
    except TypeError:
        return AdmissionDecision(False, "invalid_input", {"size_known": False})
    if any(item is None for item in raw_assets):
        return AdmissionDecision(False, "unknown_asset_size", {"size_known": False})
    try:
        estimate = estimate_workspace(
            operation=operation,
            source_bytes=source_bytes,
            asset_bytes=raw_assets,
            output_count=output_count,
            reserve_bytes=reserve_bytes,
        )
        free_value = _nonnegative_integer(free_bytes, "free_bytes")
        cap_value = _nonnegative_integer(emergency_cap_bytes, "emergency_cap_bytes")
    except (TypeError, ValueError, OverflowError):
        return AdmissionDecision(False, "invalid_input", {"size_known": True})
    evidence = {
        "operation": estimate.operation,
        "source_bytes": estimate.source_bytes,
        "asset_bytes": estimate.asset_bytes,
        "output_count": estimate.output_count,
        "estimated_bytes": estimate.estimated_bytes,
        "reserve_bytes": estimate.reserve_bytes,
        "required_bytes": estimate.required_bytes,
        "free_bytes": free_value,
        "emergency_cap_enabled": bool(cap_value),
    }
    declared_total = estimate.source_bytes + estimate.asset_bytes
    if cap_value and declared_total > cap_value:
        return AdmissionDecision(False, "internal_emergency_cap", evidence)
    if free_value < estimate.required_bytes:
        return AdmissionDecision(False, "insufficient_workspace", evidence)
    return AdmissionDecision(True, "accepted", evidence)


def _conservative_number(value: Any, fallback: int, *, positive: bool = False) -> int:
    try:
        if isinstance(value, bool) or value is None:
            raise ValueError
        number = int(value)
        if number < (1 if positive else 0) or number > MAX_POLICY_INTEGER:
            raise ValueError
        return number
    except (TypeError, ValueError, OverflowError):
        return fallback


def _conservative_duration(value: Any, fallback: float) -> float:
    try:
        duration = float(value)
        if not math.isfinite(duration) or duration < 0:
            raise ValueError
        return duration
    except (TypeError, ValueError, OverflowError):
        return fallback


def adaptive_deadline_seconds(
    *,
    source_bytes: int | None,
    duration_seconds: float | None,
    width: int | None,
    height: int | None,
    output_count: int | None,
    operation_class: str,
    minimum_seconds: int = 120,
    maximum_seconds: int = 6 * 60 * 60,
) -> int:
    """Return a bounded deadline monotonic in declared media work.

    Unknown or malformed media evidence receives conservative large-media
    baselines and unknown operation classes receive the global-work factor.
    """

    minimum = _nonnegative_integer(minimum_seconds, "minimum_seconds", positive=True)
    maximum = _nonnegative_integer(maximum_seconds, "maximum_seconds", positive=True)
    if maximum < minimum:
        raise ValueError("invalid deadline bounds")
    size = _conservative_number(source_bytes, 512 * 1024 * 1024, positive=True)
    duration = _conservative_duration(duration_seconds, 30 * 60.0)
    width_value = _conservative_number(width, 1920, positive=True)
    height_value = _conservative_number(height, 1080, positive=True)
    outputs = _conservative_number(output_count, 2, positive=True)
    operation = _normalized_operation(operation_class)
    global_factor = 1.5 if operation != SEGMENT_SAFE else 1.0
    pixel_ratio = (width_value * height_value) / float(1280 * 720)
    work = (
        30.0
        + size / float(4 * 1024 * 1024)
        + duration * 0.5
        + pixel_ratio * max(duration, 1.0) / 60.0
        + max(0, outputs - 1) * 40.0
    ) * global_factor
    if not math.isfinite(work) or work >= maximum:
        return maximum
    return max(minimum, min(maximum, int(math.ceil(work))))


def _safe_relative_path(value: Any) -> str:
    raw = _exact_string(value, "artifact path")
    _validate_safe_string(raw, reject_absolute_path=True)
    if not raw or "\\" in raw:
        raise ValueError("invalid artifact path")
    path = PurePosixPath(raw)
    windows_path = PureWindowsPath(raw)
    if (
        path.is_absolute()
        or windows_path.is_absolute()
        or bool(windows_path.drive)
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError("invalid artifact path")
    return path.as_posix()


@dataclass(frozen=True)
class ArtifactEvidence:
    relative_path: str
    sha256: str
    byte_count: int
    duration_ms: int
    width: int
    height: int
    container: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "relative_path", _safe_relative_path(self.relative_path))
        object.__setattr__(self, "sha256", _validate_hash(self.sha256, "artifact sha256"))
        object.__setattr__(
            self, "byte_count", _nonnegative_integer(self.byte_count, "byte_count", positive=True)
        )
        object.__setattr__(
            self, "duration_ms", _nonnegative_integer(self.duration_ms, "duration_ms", positive=True)
        )
        object.__setattr__(self, "width", _nonnegative_integer(self.width, "width", positive=True))
        object.__setattr__(
            self, "height", _nonnegative_integer(self.height, "height", positive=True)
        )
        container = _exact_string(self.container, "container").strip().lower()
        if not _CONTAINER_RE.fullmatch(container):
            raise ValueError("invalid container")
        object.__setattr__(self, "container", container)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "relative_path": self.relative_path,
            "sha256": self.sha256,
            "byte_count": self.byte_count,
            "duration_ms": self.duration_ms,
            "width": self.width,
            "height": self.height,
            "container": self.container,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ArtifactEvidence":
        _require_exact_keys(
            value,
            {"relative_path", "sha256", "byte_count", "duration_ms", "width", "height", "container"},
        )
        return cls(**dict(value))


def stable_part_id(*, index: int, start_ms: int, end_ms: int) -> str:
    index_value = _nonnegative_integer(index, "part index")
    start_value = _nonnegative_integer(start_ms, "part start_ms")
    end_value = _nonnegative_integer(end_ms, "part end_ms", positive=True)
    if end_value <= start_value:
        raise ValueError("invalid part range")
    return f"part-{index_value:06d}-{start_value:012d}-{end_value:012d}"


@dataclass(frozen=True)
class PartCheckpoint:
    part_id: str
    index: int
    start_ms: int
    end_ms: int
    artifact: ArtifactEvidence
    stage: str = "validated"

    def __post_init__(self) -> None:
        index = _nonnegative_integer(self.index, "part index")
        start = _nonnegative_integer(self.start_ms, "part start_ms")
        end = _nonnegative_integer(self.end_ms, "part end_ms", positive=True)
        expected = stable_part_id(index=index, start_ms=start, end_ms=end)
        part_id = _exact_string(self.part_id, "part_id")
        stage = _exact_string(self.stage, "part stage")
        if part_id != expected:
            raise ValueError("unstable part identity")
        if stage not in _PART_STAGES:
            raise ValueError("invalid part stage")
        if not isinstance(self.artifact, ArtifactEvidence):
            raise ValueError("invalid part artifact")

    def to_mapping(self) -> dict[str, Any]:
        return {
            "part_id": self.part_id,
            "index": self.index,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "artifact": self.artifact.to_mapping(),
            "stage": self.stage,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "PartCheckpoint":
        _require_exact_keys(value, {"part_id", "index", "start_ms", "end_ms", "artifact", "stage"})
        artifact = value.get("artifact")
        if not isinstance(artifact, Mapping):
            raise ValueError("invalid part artifact")
        return cls(
            part_id=value.get("part_id"),
            index=value.get("index"),
            start_ms=value.get("start_ms"),
            end_ms=value.get("end_ms"),
            artifact=ArtifactEvidence.from_mapping(artifact),
            stage=value.get("stage"),
        )


def _valid_stage(value: Any) -> str:
    stage = _exact_string(value, "stage").strip().lower()
    if stage not in _STAGE_ORDER and stage != "failed":
        raise ValueError("invalid stage")
    return stage


@dataclass(frozen=True)
class ProgressState:
    stage: str
    completed_units: int = 0
    total_units: int = 0
    unit: str = "items"
    detail: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "stage", _valid_stage(self.stage))
        completed = _nonnegative_integer(self.completed_units, "completed_units")
        total = _nonnegative_integer(self.total_units, "total_units")
        if (not total and completed) or (total and completed > total):
            raise ValueError("invalid progress units")
        if self.stage == "completed" and (total <= 0 or completed != total):
            raise ValueError("completed progress lacks finished evidence")
        unit = _exact_string(self.unit, "progress unit").strip().lower()
        detail = _exact_string(self.detail, "progress detail").strip()
        if not _SAFE_TEXT_RE.fullmatch(unit) or (detail and not _SAFE_TEXT_RE.fullmatch(detail)):
            raise ValueError("invalid progress text")
        _validate_safe_string(detail, reject_absolute_path=True)
        object.__setattr__(self, "completed_units", completed)
        object.__setattr__(self, "total_units", total)
        object.__setattr__(self, "unit", unit)
        object.__setattr__(self, "detail", detail)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "completed_units": self.completed_units,
            "total_units": self.total_units,
            "unit": self.unit,
            "detail": self.detail,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ProgressState":
        _require_exact_keys(value, {"stage", "completed_units", "total_units", "unit", "detail"})
        return cls(**dict(value))


@dataclass(frozen=True)
class DeliveryCursor:
    state: str = "not_started"
    output_index: int = 0
    attempt_id: str = ""
    deterministic: bool = False
    rejection_code: str = ""
    message_id: str = ""
    file_id: str = ""

    def __post_init__(self) -> None:
        if type(self.deterministic) is not bool:
            raise ValueError("invalid delivery determinism")
        state_value = _exact_string(self.state, "delivery state").strip().lower()
        if state_value not in _DELIVERY_STATES:
            raise ValueError("invalid delivery state")
        object.__setattr__(self, "state", state_value)
        object.__setattr__(
            self, "output_index", _nonnegative_integer(self.output_index, "delivery output_index")
        )
        for name in ("attempt_id", "rejection_code", "message_id", "file_id"):
            value = _exact_string(getattr(self, name), f"delivery {name}").strip()
            if value and not _SAFE_ID_RE.fullmatch(value):
                raise ValueError(f"invalid delivery {name}")
            _validate_safe_string(value, reject_absolute_path=True)
            object.__setattr__(self, name, value)
        if state_value == "not_started":
            if any((self.attempt_id, self.rejection_code, self.message_id, self.file_id)) or self.deterministic:
                raise ValueError("invalid not-started delivery cursor")
        elif state_value in {"sending", "unknown"}:
            if not self.attempt_id or any((self.rejection_code, self.message_id, self.file_id)):
                raise ValueError("invalid ambiguous delivery cursor")
        elif state_value == "rejected":
            if not self.attempt_id or not self.deterministic or not self.rejection_code:
                raise ValueError("invalid rejected delivery cursor")
            if self.message_id or self.file_id:
                raise ValueError("invalid rejected delivery receipt")
        elif state_value in {"accepted", "delivered"}:
            if not self.attempt_id or not self.message_id or not self.file_id:
                raise ValueError("invalid accepted delivery cursor")
            if self.rejection_code or self.deterministic:
                raise ValueError("invalid accepted delivery evidence")

    def to_mapping(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "output_index": self.output_index,
            "attempt_id": self.attempt_id,
            "deterministic": self.deterministic,
            "rejection_code": self.rejection_code,
            "message_id": self.message_id,
            "file_id": self.file_id,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "DeliveryCursor":
        _require_exact_keys(
            value,
            {
                "state",
                "output_index",
                "attempt_id",
                "deterministic",
                "rejection_code",
                "message_id",
                "file_id",
            },
        )
        return cls(**dict(value))


def _require_exact_keys(value: Mapping[str, Any], expected: set[str]) -> None:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError("invalid checkpoint schema")


@dataclass(frozen=True)
class LongMediaCheckpoint:
    project_key: str
    source_sha256: str
    plan_hash: str
    revision: int
    output_index: int
    execution_class: str
    stage: str
    progress: ProgressState
    parts: tuple[PartCheckpoint, ...] = ()
    canonical: ArtifactEvidence | None = None
    delivery: DeliveryCursor = field(default_factory=DeliveryCursor)
    liveness_epoch_ms: int = 0
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise ValueError("unsupported checkpoint schema")
        object.__setattr__(self, "project_key", _validate_hash(self.project_key, "project_key"))
        object.__setattr__(
            self, "source_sha256", _validate_hash(self.source_sha256, "source_sha256")
        )
        object.__setattr__(self, "plan_hash", _validate_hash(self.plan_hash, "plan_hash"))
        object.__setattr__(self, "revision", _nonnegative_integer(self.revision, "revision", positive=True))
        object.__setattr__(
            self, "output_index", _nonnegative_integer(self.output_index, "output_index")
        )
        execution_class = _exact_string(self.execution_class, "execution class")
        if execution_class not in {SEGMENT_SAFE, WHOLE_TIMELINE_REQUIRED}:
            raise ValueError("invalid execution class")
        stage_value = _valid_stage(self.stage)
        object.__setattr__(self, "stage", stage_value)
        if not isinstance(self.progress, ProgressState) or self.progress.stage != stage_value:
            raise ValueError("checkpoint progress stage mismatch")
        parts = tuple(self.parts)
        if any(not isinstance(part, PartCheckpoint) for part in parts):
            raise ValueError("invalid checkpoint parts")
        indices = [part.index for part in parts]
        ids = [part.part_id for part in parts]
        if indices != sorted(indices) or len(indices) != len(set(indices)) or len(ids) != len(set(ids)):
            raise ValueError("unstable checkpoint part order")
        for previous, current in zip(parts, parts[1:]):
            if current.start_ms < previous.end_ms:
                raise ValueError("overlapping checkpoint parts")
        allowed_part_stages = _PART_STAGES_BY_CHECKPOINT_STAGE[stage_value]
        if any(part.stage not in allowed_part_stages for part in parts):
            raise ValueError("part stage contradicts checkpoint stage")
        if self.execution_class == WHOLE_TIMELINE_REQUIRED:
            if len(parts) > 1 or (parts and parts[0].index != 0):
                raise ValueError("whole timeline requires one stable part")
            if stage_value == "rendering" and parts and parts[0].stage == "validated":
                raise ValueError("whole timeline rendering part is prematurely validated")
            if stage_value in {"canonical_ready", "delivery_ready", "completed"}:
                if len(parts) != 1:
                    raise ValueError("whole timeline final stage requires one part")
                part = parts[0]
                if (
                    part.index != 0
                    or part.start_ms != 0
                    or part.stage != "validated"
                    or part.end_ms != part.artifact.duration_ms
                ):
                    raise ValueError("whole timeline part lacks full duration evidence")
        object.__setattr__(self, "parts", parts)
        if self.canonical is not None and not isinstance(self.canonical, ArtifactEvidence):
            raise ValueError("invalid canonical artifact")
        if self.canonical is not None and any(part.stage != "validated" for part in parts):
            raise ValueError("canonical artifact requires validated parts")
        if self.canonical is not None and self.execution_class == WHOLE_TIMELINE_REQUIRED:
            if len(parts) != 1:
                raise ValueError("whole timeline canonical requires one part")
            part = parts[0]
            if (
                part.index != 0
                or part.start_ms != 0
                or part.stage != "validated"
                or part.end_ms != self.canonical.duration_ms
                or part.artifact.duration_ms != self.canonical.duration_ms
            ):
                raise ValueError("whole timeline canonical lacks full duration evidence")
        if (
            self.canonical is not None
            and self.execution_class == WHOLE_TIMELINE_REQUIRED
            and stage_value in {"canonical_ready", "delivery_ready", "completed"}
            and parts[0].end_ms != self.canonical.duration_ms
        ):
            raise ValueError("whole timeline canonical duration mismatch")
        stage_order = _STAGE_ORDER.get(stage_value, -1)
        if self.canonical is not None and stage_value != "failed" and stage_order < _STAGE_ORDER["canonical_ready"]:
            raise ValueError("canonical artifact precedes canonical stage")
        if stage_value in {"canonical_ready", "delivery_ready", "completed"} and self.canonical is None:
            raise ValueError("canonical stage lacks artifact")
        if not isinstance(self.delivery, DeliveryCursor):
            raise ValueError("invalid delivery cursor")
        if self.delivery.output_index != self.output_index:
            raise ValueError("delivery output identity mismatch")
        if self.delivery.state != "not_started" and stage_value not in {"delivery_ready", "completed", "failed"}:
            raise ValueError("delivery cursor precedes delivery stage")
        if stage_value == "completed" and self.delivery.state != "delivered":
            raise ValueError("completed checkpoint lacks delivered evidence")
        if stage_value == "completed" and (
            self.progress.total_units <= 0
            or self.progress.completed_units != self.progress.total_units
        ):
            raise ValueError("completed checkpoint lacks finished progress evidence")
        object.__setattr__(
            self,
            "liveness_epoch_ms",
            _nonnegative_integer(self.liveness_epoch_ms, "liveness_epoch_ms"),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "project_key": self.project_key,
            "source_sha256": self.source_sha256,
            "plan_hash": self.plan_hash,
            "revision": self.revision,
            "output_index": self.output_index,
            "execution_class": self.execution_class,
            "stage": self.stage,
            "progress": self.progress.to_mapping(),
            "parts": [part.to_mapping() for part in self.parts],
            "canonical": self.canonical.to_mapping() if self.canonical else None,
            "delivery": self.delivery.to_mapping(),
            "liveness_epoch_ms": self.liveness_epoch_ms,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "LongMediaCheckpoint":
        _require_exact_keys(
            value,
            {
                "schema_version",
                "project_key",
                "source_sha256",
                "plan_hash",
                "revision",
                "output_index",
                "execution_class",
                "stage",
                "progress",
                "parts",
                "canonical",
                "delivery",
                "liveness_epoch_ms",
            },
        )
        progress = value.get("progress")
        delivery = value.get("delivery")
        parts = value.get("parts")
        canonical = value.get("canonical")
        if not isinstance(progress, Mapping) or not isinstance(delivery, Mapping):
            raise ValueError("invalid checkpoint state evidence")
        if not isinstance(parts, list) or any(not isinstance(item, Mapping) for item in parts):
            raise ValueError("invalid checkpoint parts")
        if canonical is not None and not isinstance(canonical, Mapping):
            raise ValueError("invalid canonical artifact")
        return cls(
            schema_version=value.get("schema_version"),
            project_key=value.get("project_key"),
            source_sha256=value.get("source_sha256"),
            plan_hash=value.get("plan_hash"),
            revision=value.get("revision"),
            output_index=value.get("output_index"),
            execution_class=value.get("execution_class"),
            stage=value.get("stage"),
            progress=ProgressState.from_mapping(progress),
            parts=tuple(PartCheckpoint.from_mapping(item) for item in parts),
            canonical=ArtifactEvidence.from_mapping(canonical) if canonical is not None else None,
            delivery=DeliveryCursor.from_mapping(delivery),
            liveness_epoch_ms=value.get("liveness_epoch_ms"),
        )


def canonical_checkpoint_json(checkpoint: LongMediaCheckpoint | Mapping[str, Any]) -> bytes:
    """Serialize one validated checkpoint as compact canonical UTF-8 JSON."""

    try:
        if isinstance(checkpoint, LongMediaCheckpoint):
            validated = checkpoint
        elif isinstance(checkpoint, Mapping):
            _validate_safe_tree(checkpoint, reject_absolute_paths=True)
            validated = LongMediaCheckpoint.from_mapping(checkpoint)
        else:
            raise ValueError("invalid checkpoint")
        return _canonical_json_bytes(validated.to_mapping(), checkpoint=True)
    except RecursionError:
        raise ValueError("invalid checkpoint") from None


def _file_identity(result: os.stat_result) -> tuple[int, int]:
    return int(result.st_dev), int(result.st_ino)


def _is_reparse_point(result: os.stat_result) -> bool:
    return bool(getattr(result, "st_file_attributes", 0) & _REPARSE_POINT)


def _is_plain_regular_file(result: os.stat_result) -> bool:
    return stat.S_ISREG(result.st_mode) and not _is_reparse_point(result)


def _is_plain_directory(result: os.stat_result) -> bool:
    return stat.S_ISDIR(result.st_mode) and not _is_reparse_point(result)


def _is_owned_result(result: os.stat_result) -> bool:
    return not hasattr(os, "getuid") or result.st_uid == os.getuid()


def _is_private_owned_regular_file(
    result: os.stat_result,
    *,
    platform_name: str | None = None,
    effective_uid: int | None = None,
) -> bool:
    """Reject artifact files writable by another POSIX principal."""

    if not _is_plain_regular_file(result):
        return False
    platform = os.name if platform_name is None else platform_name
    if platform != "posix":
        return True
    uid = os.getuid() if effective_uid is None else effective_uid
    return (
        result.st_uid == uid
        and not stat.S_IMODE(result.st_mode) & (stat.S_IRWXG | stat.S_IRWXO)
    )


def _owned_plain_file(path: Path) -> bool:
    try:
        result = os.lstat(path)
    except OSError:
        return False
    return _is_private_owned_regular_file(result)


def _safe_checkpoint_parent(destination: Path) -> os.stat_result:
    parent = destination.parent
    try:
        result = os.lstat(parent)
        if not media_transport._is_private_owned_directory(result):
            raise OSError
        if os.path.normcase(os.path.realpath(parent)) != os.path.normcase(os.path.abspath(parent)):
            raise OSError
    except OSError:
        raise CheckpointError("unsafe_destination") from None
    if os.path.lexists(destination) and not _owned_plain_file(destination):
        raise CheckpointError("unsafe_destination")
    return result


def _revalidate_checkpoint_guard(
    guard: media_transport._DestinationGuard,
    expected_parent: os.stat_result,
) -> None:
    """Bind checkpoint publication to one private parent and owned final name."""

    try:
        guard._verify_parent()
        path_parent = _safe_checkpoint_parent(guard.final_path)
        expected_identity = _file_identity(expected_parent)
        if (
            guard.parent_identity != expected_identity
            or _file_identity(path_parent) != expected_identity
        ):
            raise OSError
        final_result = guard._stat_name(guard.final_name)
        if final_result is not None and (
            not _is_private_owned_regular_file(final_result)
        ):
            raise OSError
        guard._verify_parent()
    except CheckpointError:
        raise
    except (OSError, ValueError, media_transport.MediaTransferError):
        raise CheckpointError("unsafe_destination") from None


def write_checkpoint_atomic(
    destination: str | os.PathLike[str],
    checkpoint: LongMediaCheckpoint | Mapping[str, Any],
) -> Path:
    """Atomically replace a private checkpoint and clean only its exact temp."""

    try:
        payload = canonical_checkpoint_json(checkpoint)
        final_path = Path(os.path.abspath(os.fspath(destination)))
    except (TypeError, ValueError, OSError, RecursionError):
        raise CheckpointError("invalid_checkpoint") from None
    if len(payload) > MAX_CHECKPOINT_BYTES:
        raise CheckpointError("checkpoint_too_large")
    parent_snapshot = _safe_checkpoint_parent(final_path)
    guard: media_transport._DestinationGuard | None = None
    descriptor: int | None = None
    try:
        for _ in range(16):
            partial_name = f".{final_path.name}.{secrets.token_hex(12)}.tmp"
            try:
                guard = media_transport._DestinationGuard(
                    final_path,
                    partial_name=partial_name,
                    require_private_parent=True,
                )
                break
            except media_transport.MediaTransferError:
                continue
        if guard is None:
            raise OSError
        _revalidate_checkpoint_guard(guard, parent_snapshot)
        descriptor = guard.open_partial()
        try:
            os.fchmod(descriptor, 0o600)
        except (AttributeError, OSError):
            pass
        written = 0
        while written < len(payload):
            count = os.write(descriptor, payload[written:])
            if count <= 0:
                raise OSError
            written += count
        os.fsync(descriptor)
        guard.verify_partial(descriptor)
        os.close(descriptor)
        descriptor = None
        _revalidate_checkpoint_guard(guard, parent_snapshot)
        guard.publish()
        if guard.directory_fd is not None:
            try:
                os.fsync(guard.directory_fd)
            except OSError:
                pass
        return final_path
    except (
        OSError,
        ValueError,
        RecursionError,
        media_transport.MediaTransferError,
    ):
        raise CheckpointError("atomic_write_failed") from None
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if guard is not None:
            guard.cleanup_partial()
            guard.close()


def _expected_identity(
    checkpoint: LongMediaCheckpoint,
    *,
    project_key: str,
    source_sha256: str,
    plan_hash: str,
    revision: int,
    output_index: int,
) -> bool:
    try:
        expected = (
            _validate_hash(project_key, "project_key"),
            _validate_hash(source_sha256, "source_sha256"),
            _validate_hash(plan_hash, "plan_hash"),
            _nonnegative_integer(revision, "revision", positive=True),
            _nonnegative_integer(output_index, "output_index"),
        )
    except ValueError:
        return False
    return expected == (
        checkpoint.project_key,
        checkpoint.source_sha256,
        checkpoint.plan_hash,
        checkpoint.revision,
        checkpoint.output_index,
    )


def _descriptor_read_flags() -> int:
    flags = os.O_RDONLY
    flags |= getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)
    return flags


def _stable_file_snapshot(result: os.stat_result) -> tuple[int, ...]:
    return (
        *_file_identity(result),
        int(result.st_mode),
        int(result.st_size),
        int(getattr(result, "st_mtime_ns", int(result.st_mtime * 1_000_000_000))),
        int(getattr(result, "st_ctime_ns", int(result.st_ctime * 1_000_000_000))),
    )


def _verify_descriptor_and_name(
    descriptor: int,
    path: Path,
    opened_before: os.stat_result,
    *,
    byte_count: int,
) -> None:
    opened_after = os.fstat(descriptor)
    if (
        not _is_private_owned_regular_file(opened_after)
        or byte_count != opened_before.st_size
        or _stable_file_snapshot(opened_after) != _stable_file_snapshot(opened_before)
    ):
        raise OSError
    named = os.lstat(path)
    if (
        not _is_private_owned_regular_file(named)
        or _stable_file_snapshot(named) != _stable_file_snapshot(opened_after)
    ):
        raise OSError


def _read_checkpoint_descriptor(path: Path) -> bytes:
    descriptor: int | None = None
    try:
        descriptor = os.open(path, _descriptor_read_flags())
        opened_before = os.fstat(descriptor)
        if (
            not _is_private_owned_regular_file(opened_before)
            or opened_before.st_size > MAX_CHECKPOINT_BYTES
        ):
            raise OSError
        chunks: list[bytes] = []
        byte_count = 0
        while byte_count < opened_before.st_size:
            request_size = min(
                DESCRIPTOR_READ_BYTES,
                opened_before.st_size - byte_count,
            )
            chunk = os.read(descriptor, request_size)
            if not chunk:
                raise OSError
            chunks.append(chunk)
            byte_count += len(chunk)
        _verify_descriptor_and_name(
            descriptor,
            path,
            opened_before,
            byte_count=byte_count,
        )
        return b"".join(chunks)
    finally:
        if descriptor is not None:
            os.close(descriptor)


def load_checkpoint(
    source: str | os.PathLike[str],
    *,
    project_key: str,
    source_sha256: str,
    plan_hash: str,
    revision: int,
    output_index: int,
) -> LongMediaCheckpoint:
    """Load canonical JSON and enforce exact expected job/output identity."""

    try:
        path = Path(os.path.abspath(os.fspath(source)))
        parent_before = _safe_checkpoint_parent(path)
        raw = _read_checkpoint_descriptor(path)
        parent_after = _safe_checkpoint_parent(path)
        if _file_identity(parent_after) != _file_identity(parent_before):
            raise OSError
        decoded = raw.decode("utf-8")
        value = json.loads(decoded)
        if not isinstance(value, Mapping):
            raise ValueError
        _validate_safe_tree(value, reject_absolute_paths=True)
        checkpoint = LongMediaCheckpoint.from_mapping(value)
        if raw != canonical_checkpoint_json(checkpoint):
            raise ValueError
    except CheckpointError:
        raise
    except Exception:
        raise CheckpointError("invalid_checkpoint") from None
    if not _expected_identity(
        checkpoint,
        project_key=project_key,
        source_sha256=source_sha256,
        plan_hash=plan_hash,
        revision=revision,
        output_index=output_index,
    ):
        raise CheckpointError("identity_mismatch")
    return checkpoint


def try_load_checkpoint(
    source: str | os.PathLike[str],
    *,
    project_key: str,
    source_sha256: str,
    plan_hash: str,
    revision: int,
    output_index: int,
) -> LongMediaCheckpoint | None:
    """Ignore an unsafe, corrupt, stale, or mismatched checkpoint for reuse."""

    try:
        return load_checkpoint(
            source,
            project_key=project_key,
            source_sha256=source_sha256,
            plan_hash=plan_hash,
            revision=revision,
            output_index=output_index,
        )
    except (CheckpointError, TypeError, ValueError, OSError):
        return None


def _probe_integer(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"invalid {name}")
    return int(value)


def _probe_float(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"invalid {name}")
    return float(value)


def _normalized_probe(value: Mapping[str, Any]) -> tuple[int, int, int, str, str | None, int | None]:
    if not isinstance(value, Mapping):
        raise ValueError("invalid FFprobe evidence")
    if "format" in value or "streams" in value:
        format_value = value.get("format")
        streams = value.get("streams")
        if not isinstance(format_value, Mapping) or not isinstance(streams, Sequence):
            raise ValueError("invalid FFprobe evidence")
        video = next(
            (item for item in streams if isinstance(item, Mapping) and item.get("codec_type") == "video"),
            None,
        )
        if video is None:
            raise ValueError("missing video stream")
        duration_ms = int(
            round(_probe_float(format_value.get("duration"), "probe duration") * 1000.0)
        )
        width = _probe_integer(video.get("width"), "probe width")
        height = _probe_integer(video.get("height"), "probe height")
        container = _exact_string(
            format_value.get("format_name"), "probe container"
        ).strip().lower()
        probe_hash = value.get("sha256")
        probe_size = format_value.get("size")
    else:
        duration_ms = _probe_integer(value.get("duration_ms"), "probe duration_ms")
        width = _probe_integer(value.get("width"), "probe width")
        height = _probe_integer(value.get("height"), "probe height")
        container = _exact_string(value.get("container"), "probe container").strip().lower()
        probe_hash = value.get("sha256")
        probe_size = value.get("byte_count")
    if duration_ms <= 0 or width <= 0 or height <= 0 or not _CONTAINER_RE.fullmatch(container):
        raise ValueError("invalid FFprobe evidence")
    normalized_hash = _validate_hash(probe_hash, "probe sha256") if probe_hash is not None else None
    normalized_size = (
        _probe_integer(probe_size, "probe size") if probe_size is not None else None
    )
    if normalized_size is not None and normalized_size <= 0:
        raise ValueError("invalid probe size")
    return duration_ms, width, height, container, normalized_hash, normalized_size


def _container_matches(expected: str, actual: str) -> bool:
    return expected == actual or expected in {item.strip() for item in actual.split(",")}


def _safe_workspace_directory(result: os.stat_result) -> bool:
    return media_transport._is_private_owned_directory(result)


def _artifact_parts(relative_path: str) -> tuple[str, ...]:
    normalized = _safe_relative_path(relative_path)
    parts = PurePosixPath(normalized).parts
    if not parts:
        raise ValueError("invalid artifact path")
    return parts


def _hash_bounded_descriptor(
    descriptor: int,
    *,
    expected_bytes: int,
    opened_before: os.stat_result,
) -> tuple[str, int]:
    digest = hashlib.sha256()
    byte_count = 0
    while True:
        request_size = min(
            DESCRIPTOR_READ_BYTES,
            expected_bytes - byte_count + 1,
        )
        chunk = os.read(descriptor, request_size)
        if not chunk:
            break
        byte_count += len(chunk)
        if byte_count > expected_bytes:
            raise OSError
        digest.update(chunk)
    opened_after = os.fstat(descriptor)
    if (
        byte_count != expected_bytes
        or not _is_private_owned_regular_file(opened_after)
        or _stable_file_snapshot(opened_after) != _stable_file_snapshot(opened_before)
    ):
        raise OSError
    return digest.hexdigest(), byte_count


def _verify_posix_directory_chain(
    root: Path,
    root_descriptor: int,
    root_identity: tuple[int, int],
    chain: Sequence[tuple[int, str, int, tuple[int, int]]],
) -> None:
    root_opened = os.fstat(root_descriptor)
    root_named = os.lstat(root)
    if (
        not _safe_workspace_directory(root_opened)
        or not _safe_workspace_directory(root_named)
        or _file_identity(root_opened) != root_identity
        or _file_identity(root_named) != root_identity
        or os.path.normcase(os.path.realpath(root))
        != os.path.normcase(os.path.abspath(root))
    ):
        raise OSError
    for parent_descriptor, name, descriptor, identity in chain:
        opened = os.fstat(descriptor)
        named = os.stat(
            name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if (
            not _safe_workspace_directory(opened)
            or not _safe_workspace_directory(named)
            or _file_identity(opened) != identity
            or _file_identity(named) != identity
        ):
            raise OSError


def _hash_artifact_posix(
    root: Path,
    parts: Sequence[str],
    *,
    expected_bytes: int,
) -> tuple[str, int]:
    required = ("O_DIRECTORY", "O_NOFOLLOW")
    if not all(hasattr(os, name) for name in required):
        raise OSError
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    directory_flags |= getattr(os, "O_CLOEXEC", 0)
    root_descriptor: int | None = None
    artifact_descriptor: int | None = None
    directory_descriptors: list[int] = []
    chain: list[tuple[int, str, int, tuple[int, int]]] = []
    try:
        root_named = os.lstat(root)
        if (
            not _safe_workspace_directory(root_named)
            or os.path.normcase(os.path.realpath(root))
            != os.path.normcase(os.path.abspath(root))
        ):
            raise OSError
        root_identity = _file_identity(root_named)
        root_descriptor = os.open(root, directory_flags)
        root_opened = os.fstat(root_descriptor)
        if (
            not _safe_workspace_directory(root_opened)
            or _file_identity(root_opened) != root_identity
        ):
            raise OSError

        parent_descriptor = root_descriptor
        for name in parts[:-1]:
            named_before = os.stat(
                name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
            if not _safe_workspace_directory(named_before):
                raise OSError
            descriptor = os.open(name, directory_flags, dir_fd=parent_descriptor)
            directory_descriptors.append(descriptor)
            opened = os.fstat(descriptor)
            identity = _file_identity(opened)
            if (
                not _safe_workspace_directory(opened)
                or identity != _file_identity(named_before)
            ):
                raise OSError
            chain.append((parent_descriptor, name, descriptor, identity))
            parent_descriptor = descriptor

        artifact_name = parts[-1]
        named_before = os.stat(
            artifact_name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if (
            not _is_private_owned_regular_file(named_before)
            or named_before.st_size != expected_bytes
        ):
            raise OSError
        artifact_descriptor = os.open(
            artifact_name,
            _descriptor_read_flags(),
            dir_fd=parent_descriptor,
        )
        opened_before = os.fstat(artifact_descriptor)
        if (
            not _is_private_owned_regular_file(opened_before)
            or opened_before.st_size != expected_bytes
            or _stable_file_snapshot(opened_before)
            != _stable_file_snapshot(named_before)
        ):
            raise OSError
        result = _hash_bounded_descriptor(
            artifact_descriptor,
            expected_bytes=expected_bytes,
            opened_before=opened_before,
        )
        named_after = os.stat(
            artifact_name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if (
            not _is_private_owned_regular_file(named_after)
            or _stable_file_snapshot(named_after)
            != _stable_file_snapshot(os.fstat(artifact_descriptor))
        ):
            raise OSError
        _verify_posix_directory_chain(
            root,
            root_descriptor,
            root_identity,
            chain,
        )
        return result
    finally:
        if artifact_descriptor is not None:
            os.close(artifact_descriptor)
        for descriptor in reversed(directory_descriptors):
            os.close(descriptor)
        if root_descriptor is not None:
            os.close(root_descriptor)


def _windows_information_size(information: Any) -> int:
    return (int(information.file_size_high) << 32) | int(information.file_size_low)


def _windows_information_snapshot(information: Any) -> tuple[int, ...]:
    return (
        *media_transport._win_identity(information),
        int(information.file_attributes),
        _windows_information_size(information),
        int(information.last_write_time.dwHighDateTime),
        int(information.last_write_time.dwLowDateTime),
    )


def _windows_open_read_file(path: Path) -> tuple[int, int]:
    handle: int | None = None
    duplicate: int | None = None
    try:
        handle_value = media_transport._CreateFileW(
            str(path),
            0x80000000 | media_transport._FILE_READ_ATTRIBUTES,
            media_transport._FILE_SHARE_READ | media_transport._FILE_SHARE_WRITE,
            None,
            media_transport._OPEN_EXISTING,
            media_transport._FILE_FLAG_OPEN_REPARSE_POINT,
            None,
        )
        if handle_value == media_transport._INVALID_HANDLE_VALUE:
            raise media_transport._win_error()
        handle = int(handle_value)
        duplicate = media_transport._win_duplicate_handle(handle)
        descriptor = media_transport.msvcrt.open_osfhandle(
            duplicate,
            os.O_RDONLY | getattr(os, "O_BINARY", 0),
        )
        duplicate = None
        return handle, descriptor
    except Exception:
        if duplicate is not None:
            try:
                media_transport._win_close_handle(duplicate)
            except OSError:
                pass
        if handle is not None:
            try:
                media_transport._win_close_handle(handle)
            except OSError:
                pass
        raise


def _verify_windows_directory(
    path: Path,
    handle: int,
    identity: tuple[int, int],
) -> None:
    named = os.lstat(path)
    opened = media_transport._win_file_information(handle)
    if (
        not _safe_workspace_directory(named)
        or not media_transport._win_is_plain_directory(opened)
        or int(named.st_ino) != identity[1]
        or media_transport._win_identity(opened) != identity
        or media_transport._win_final_path(handle)
        != os.path.normcase(os.path.abspath(path))
    ):
        raise OSError


def _windows_open_directory_identity(path: Path) -> tuple[int, tuple[int, int]]:
    """Acquire one Win32 directory handle or close it before propagating."""

    handle = media_transport._win_open_directory(path)
    try:
        information = media_transport._win_file_information(handle)
        identity = media_transport._win_identity(information)
    except BaseException:
        try:
            media_transport._win_close_handle(handle)
        except OSError:
            pass
        raise
    return handle, identity


def _hash_artifact_windows(
    root: Path,
    parts: Sequence[str],
    *,
    expected_bytes: int,
) -> tuple[str, int]:
    directories: list[tuple[Path, int, tuple[int, int]]] = []
    artifact_handle: int | None = None
    artifact_descriptor: int | None = None
    try:
        current = root
        root_named = os.lstat(current)
        if (
            not _safe_workspace_directory(root_named)
            or os.path.normcase(os.path.realpath(current))
            != os.path.normcase(os.path.abspath(current))
        ):
            raise OSError
        root_handle, root_identity = _windows_open_directory_identity(current)
        directories.append((current, root_handle, root_identity))
        if int(root_named.st_ino) != root_identity[1]:
            raise OSError
        _verify_windows_directory(current, root_handle, root_identity)

        for name in parts[:-1]:
            current = current / name
            named_before = os.lstat(current)
            if not _safe_workspace_directory(named_before):
                raise OSError
            handle, identity = _windows_open_directory_identity(current)
            directories.append((current, handle, identity))
            if int(named_before.st_ino) != identity[1]:
                raise OSError
            _verify_windows_directory(current, handle, identity)

        artifact_path = current / parts[-1]
        named_before = os.lstat(artifact_path)
        if (
            not _is_private_owned_regular_file(named_before)
            or named_before.st_size != expected_bytes
        ):
            raise OSError
        artifact_handle, artifact_descriptor = _windows_open_read_file(artifact_path)
        handle_before = media_transport._win_file_information(artifact_handle)
        handle_identity = media_transport._win_identity(handle_before)
        opened_before = os.fstat(artifact_descriptor)
        if (
            not media_transport._win_is_plain_regular_file(handle_before)
            or _windows_information_size(handle_before) != expected_bytes
            or int(named_before.st_ino) != handle_identity[1]
            or int(opened_before.st_ino) != handle_identity[1]
            or not _is_private_owned_regular_file(opened_before)
            or opened_before.st_size != expected_bytes
            or media_transport._win_final_path(artifact_handle)
            != os.path.normcase(os.path.abspath(artifact_path))
        ):
            raise OSError
        result = _hash_bounded_descriptor(
            artifact_descriptor,
            expected_bytes=expected_bytes,
            opened_before=opened_before,
        )
        handle_after = media_transport._win_file_information(artifact_handle)
        named_after = os.lstat(artifact_path)
        if (
            _windows_information_snapshot(handle_after)
            != _windows_information_snapshot(handle_before)
            or not _is_private_owned_regular_file(named_after)
            or _stable_file_snapshot(named_after)
            != _stable_file_snapshot(os.fstat(artifact_descriptor))
            or media_transport._win_final_path(artifact_handle)
            != os.path.normcase(os.path.abspath(artifact_path))
        ):
            raise OSError
        for path, handle, identity in directories:
            _verify_windows_directory(path, handle, identity)
        return result
    finally:
        if artifact_descriptor is not None:
            os.close(artifact_descriptor)
        if artifact_handle is not None:
            try:
                media_transport._win_close_handle(artifact_handle)
            except OSError:
                pass
        for _path, handle, _identity in reversed(directories):
            try:
                media_transport._win_close_handle(handle)
            except OSError:
                pass


def _hash_artifact_descriptor(
    root: Path,
    relative_path: str,
    *,
    expected_bytes: int,
) -> tuple[str, int]:
    parts = _artifact_parts(relative_path)
    if os.name == "posix":
        return _hash_artifact_posix(root, parts, expected_bytes=expected_bytes)
    if os.name == "nt":
        return _hash_artifact_windows(root, parts, expected_bytes=expected_bytes)
    raise OSError


def _artifact_matches(
    artifact: ArtifactEvidence,
    *,
    workspace: str | os.PathLike[str],
    ffprobe_evidence: Mapping[str, Any],
) -> bool:
    try:
        root = Path(os.path.abspath(os.fspath(workspace)))
        root_before = os.lstat(root)
        if not _safe_workspace_directory(root_before):
            return False
        if os.path.normcase(os.path.realpath(root)) != os.path.normcase(os.path.abspath(root)):
            return False
        digest, byte_count = _hash_artifact_descriptor(
            root,
            artifact.relative_path,
            expected_bytes=artifact.byte_count,
        )
        root_after = os.lstat(root)
        if (
            not _safe_workspace_directory(root_after)
            or _stable_file_snapshot(root_after) != _stable_file_snapshot(root_before)
        ):
            return False
        if byte_count != artifact.byte_count or digest != artifact.sha256:
            return False
        duration, width, height, container, probe_hash, probe_size = _normalized_probe(
            ffprobe_evidence
        )
        if probe_hash is not None and probe_hash != artifact.sha256:
            return False
        if probe_size is not None and probe_size != artifact.byte_count:
            return False
        return (
            duration == artifact.duration_ms
            and width == artifact.width
            and height == artifact.height
            and _container_matches(artifact.container, container)
        )
    except (OSError, TypeError, ValueError, OverflowError):
        return False


def validate_reusable_part(
    checkpoint: LongMediaCheckpoint,
    *,
    part_id: str,
    workspace: str | os.PathLike[str],
    ffprobe_evidence: Mapping[str, Any],
    project_key: str,
    source_sha256: str,
    plan_hash: str,
    revision: int,
    output_index: int,
    expected_start_ms: int | None = None,
    expected_end_ms: int | None = None,
) -> PartCheckpoint | None:
    """Return a part only when identity, range, disk, hash, size, and probe match."""

    if not isinstance(checkpoint, LongMediaCheckpoint) or not _expected_identity(
        checkpoint,
        project_key=project_key,
        source_sha256=source_sha256,
        plan_hash=plan_hash,
        revision=revision,
        output_index=output_index,
    ):
        return None
    part = next((item for item in checkpoint.parts if item.part_id == part_id), None)
    if part is None or part.stage != "validated":
        return None
    if expected_start_ms is not None and part.start_ms != expected_start_ms:
        return None
    if expected_end_ms is not None and part.end_ms != expected_end_ms:
        return None
    return part if _artifact_matches(part.artifact, workspace=workspace, ffprobe_evidence=ffprobe_evidence) else None


@dataclass(frozen=True)
class RecoveryDecision:
    allowed: bool
    reason: str
    artifact: ArtifactEvidence | None = None

    def __post_init__(self) -> None:
        if not _SAFE_TEXT_RE.fullmatch(str(self.reason or "")):
            raise ValueError("invalid recovery reason")
        if self.allowed != (self.artifact is not None):
            raise ValueError("invalid recovery evidence")


def recover_canonical_output(
    checkpoint: LongMediaCheckpoint,
    *,
    workspace: str | os.PathLike[str],
    ffprobe_evidence: Mapping[str, Any],
    project_key: str,
    source_sha256: str,
    plan_hash: str,
    revision: int,
    output_index: int,
) -> RecoveryDecision:
    """Validate canonical reuse while fencing every ambiguous/accepted delivery."""

    if not isinstance(checkpoint, LongMediaCheckpoint) or not _expected_identity(
        checkpoint,
        project_key=project_key,
        source_sha256=source_sha256,
        plan_hash=plan_hash,
        revision=revision,
        output_index=output_index,
    ):
        return RecoveryDecision(False, "identity_mismatch")
    cursor = checkpoint.delivery
    if cursor.state not in {"not_started", "rejected"}:
        return RecoveryDecision(False, "delivery_fenced")
    if cursor.state == "rejected" and not cursor.deterministic:
        return RecoveryDecision(False, "delivery_fenced")
    if checkpoint.canonical is None or not _artifact_matches(
        checkpoint.canonical,
        workspace=workspace,
        ffprobe_evidence=ffprobe_evidence,
    ):
        return RecoveryDecision(False, "canonical_invalid")
    if checkpoint.execution_class == WHOLE_TIMELINE_REQUIRED:
        if len(checkpoint.parts) != 1:
            return RecoveryDecision(False, "canonical_invalid")
        part = checkpoint.parts[0]
        if (
            part.index != 0
            or part.start_ms != 0
            or part.stage != "validated"
            or part.end_ms != checkpoint.canonical.duration_ms
            or part.artifact.duration_ms != checkpoint.canonical.duration_ms
        ):
            return RecoveryDecision(False, "canonical_invalid")
    return RecoveryDecision(True, "canonical_reusable", checkpoint.canonical)


def advance_progress(
    current: ProgressState,
    *,
    stage: str,
    completed_units: int | None = None,
    total_units: int | None = None,
    unit: str | None = None,
    detail: str | None = None,
) -> ProgressState:
    """Advance a real stage/unit cursor without deriving a percentage."""

    if not isinstance(current, ProgressState):
        raise ValueError("invalid current progress")
    next_stage = _valid_stage(stage)
    next_completed = current.completed_units if completed_units is None else completed_units
    next_total = current.total_units if total_units is None else total_units
    next_unit = current.unit if unit is None else unit
    next_detail = current.detail if detail is None else detail
    candidate = ProgressState(
        stage=next_stage,
        completed_units=next_completed,
        total_units=next_total,
        unit=next_unit,
        detail=next_detail,
    )
    if current.stage in _TERMINAL_STAGES:
        if candidate == current:
            return current
        raise ValueError("terminal progress is immutable")
    if next_stage != "failed" and _STAGE_ORDER[next_stage] < _STAGE_ORDER[current.stage]:
        raise ValueError("progress stage regression")
    if candidate.unit == current.unit:
        if candidate.total_units < current.total_units:
            raise ValueError("progress total regression")
        if candidate.completed_units < current.completed_units:
            raise ValueError("progress unit regression")
    elif next_stage == current.stage:
        raise ValueError("progress unit changed within stage")
    elif (
        next_stage == "failed"
        or _STAGE_ORDER[next_stage] <= _STAGE_ORDER[current.stage]
        or unit is None
        or not str(unit).strip()
        or completed_units is None
        or total_units is None
        or candidate.total_units <= 0
    ):
        raise ValueError("progress unit changed without forward evidence")
    if next_stage == "completed" and _STAGE_ORDER[current.stage] < _STAGE_ORDER["delivery_ready"]:
        raise ValueError("premature completed progress")
    return candidate


def advance_checkpoint(
    checkpoint: LongMediaCheckpoint,
    *,
    stage: str,
    completed_units: int | None = None,
    total_units: int | None = None,
    unit: str | None = None,
    detail: str | None = None,
    liveness_epoch_ms: int | None = None,
) -> LongMediaCheckpoint:
    """Return a new checkpoint with monotonic progress and liveness evidence."""

    progress = advance_progress(
        checkpoint.progress,
        stage=stage,
        completed_units=completed_units,
        total_units=total_units,
        unit=unit,
        detail=detail,
    )
    liveness = checkpoint.liveness_epoch_ms
    if liveness_epoch_ms is not None:
        candidate_liveness = _nonnegative_integer(liveness_epoch_ms, "liveness_epoch_ms")
        if checkpoint.stage in _TERMINAL_STAGES and candidate_liveness != liveness:
            raise ValueError("terminal liveness is immutable")
        if candidate_liveness < liveness:
            raise ValueError("liveness regression")
        liveness = candidate_liveness
    return replace(checkpoint, stage=progress.stage, progress=progress, liveness_epoch_ms=liveness)


__all__ = [
    "SCHEMA_VERSION",
    "PROJECT_KEY_DOMAIN",
    "SEGMENT_SAFE",
    "WHOLE_TIMELINE_REQUIRED",
    "CheckpointError",
    "WorkspaceEstimate",
    "AdmissionDecision",
    "ArtifactEvidence",
    "PartCheckpoint",
    "ProgressState",
    "DeliveryCursor",
    "LongMediaCheckpoint",
    "RecoveryDecision",
    "canonical_plan_hash",
    "project_key",
    "classify_plan_execution",
    "estimate_workspace",
    "admit_workspace",
    "adaptive_deadline_seconds",
    "stable_part_id",
    "canonical_checkpoint_json",
    "write_checkpoint_atomic",
    "load_checkpoint",
    "try_load_checkpoint",
    "validate_reusable_part",
    "recover_canonical_output",
    "advance_progress",
    "advance_checkpoint",
]
