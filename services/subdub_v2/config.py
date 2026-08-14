"""Pure configuration for the disabled SubDub V2 shadow/replay path.

This module deliberately has no imports from the Telegram bot, providers,
workers or billing code.  V2 is opt-in for an explicit offline replay only.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import os
from typing import Mapping


def _flag(value: object, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enabled"}


@dataclass(frozen=True)
class V2Flags:
    enabled: bool = False
    public_allowed: bool = False
    shadow_replay: bool = False
    admin_preview: bool = False

    @classmethod
    def from_mapping(cls, values: Mapping[str, object] | None = None) -> "V2Flags":
        values = values or {}
        return cls(
            enabled=_flag(values.get("SUBDUB_PIPELINE_V2_ENABLED"), False),
            public_allowed=_flag(values.get("SUBDUB_PIPELINE_V2_PUBLIC_ALLOWED"), False),
            shadow_replay=_flag(values.get("SUBDUB_PIPELINE_V2_SHADOW_REPLAY"), False),
            admin_preview=_flag(values.get("SUBDUB_PIPELINE_V2_ADMIN_PREVIEW"), False),
        )

    @classmethod
    def from_env(cls) -> "V2Flags":
        """Read-only helper. Merely importing V2 never reads or changes ENV."""
        return cls.from_mapping(os.environ)

    @classmethod
    def shadow_defaults_for_test(cls) -> "V2Flags":
        """Explicit fixture-only opt-in; public routing stays disabled."""
        return cls(enabled=True, public_allowed=False, shadow_replay=True, admin_preview=True)

    @property
    def selects_v1(self) -> bool:
        return not self.enabled or not self.public_allowed

    @property
    def shadow_only(self) -> bool:
        return self.shadow_replay and not self.public_allowed


@dataclass(frozen=True)
class V2ResourceLimits:
    max_input_bytes: int = 500 * 1024 * 1024
    max_output_bytes: int = 500 * 1024 * 1024
    max_duration_ms: int = 3600 * 1000
    max_parts: int = 12
    part_duration_ms: int = 300 * 1000
    max_concurrent_parts: int = 1
    max_inflight_audio_bytes: int = 256 * 1024 * 1024
    max_segments: int = 6000
    max_subtitle_bytes: int = 8 * 1024 * 1024
    workspace_fixed_bytes: int = 512 * 1024 * 1024
    workspace_multiplier: int = 3
    workspace_hard_cap_bytes: int = 4 * 1024 * 1024 * 1024

    def workspace_limit(self, input_bytes: int) -> int:
        calculated = max(0, int(input_bytes or 0)) * self.workspace_multiplier + self.workspace_fixed_bytes
        return min(self.workspace_hard_cap_bytes, calculated)

    def validate(
        self,
        *,
        input_bytes: int,
        duration_ms: int,
        output_bytes: int = 0,
        part_count: int = 0,
        segment_count: int = 0,
        subtitle_bytes: int = 0,
        inflight_audio_bytes: int = 0,
        workspace_bytes: int = 0,
        concurrent_parts: int = 1,
    ) -> list[str]:
        failures: list[str] = []
        if int(input_bytes or 0) > self.max_input_bytes:
            failures.append("input_bytes")
        if int(output_bytes or 0) > self.max_output_bytes:
            failures.append("output_bytes")
        if int(duration_ms or 0) > self.max_duration_ms:
            failures.append("duration_ms")
        if int(part_count or 0) > self.max_parts:
            failures.append("part_count")
        if int(segment_count or 0) > self.max_segments:
            failures.append("segment_count")
        if int(subtitle_bytes or 0) > self.max_subtitle_bytes:
            failures.append("subtitle_bytes")
        if int(inflight_audio_bytes or 0) > self.max_inflight_audio_bytes:
            failures.append("inflight_audio_bytes")
        if int(workspace_bytes or 0) > self.workspace_limit(input_bytes):
            failures.append("workspace_bytes")
        if int(concurrent_parts or 1) > self.max_concurrent_parts:
            failures.append("concurrent_parts")
        return failures

    def plan_parts(self, duration_ms: int) -> list[dict[str, int]]:
        duration_ms = max(0, int(duration_ms or 0))
        if duration_ms > self.max_duration_ms:
            raise ValueError("RESOURCE_LIMIT_EXCEEDED:duration_ms")
        if duration_ms == 0:
            return []
        count = int(math.ceil(duration_ms / self.part_duration_ms))
        if count > self.max_parts:
            raise ValueError("RESOURCE_LIMIT_EXCEEDED:part_count")
        return [
            {
                "part_index": index + 1,
                "start_ms": index * self.part_duration_ms,
                "end_ms": min(duration_ms, (index + 1) * self.part_duration_ms),
            }
            for index in range(count)
        ]


@dataclass(frozen=True)
class V2RetentionPolicy:
    raw_media_hours: int = 24
    semantic_artifact_hours: int = 72
    admin_provider_metadata_hours: int = 30 * 24
    qc_summary_hours: int = 30 * 24
    delivery_receipt_hours: int = 90 * 24

    def hours_for(self, retention_class: str) -> int:
        mapping = {
            "subdub_raw_24h": self.raw_media_hours,
            "subdub_semantic_72h": self.semantic_artifact_hours,
            "subdub_admin_metadata_30d": self.admin_provider_metadata_hours,
            "subdub_qc_30d": self.qc_summary_hours,
            "subdub_delivery_90d": self.delivery_receipt_hours,
        }
        if retention_class not in mapping:
            raise ValueError("unknown_retention_class")
        return mapping[retention_class]


DEFAULT_RESOURCE_LIMITS = V2ResourceLimits()
DEFAULT_RETENTION_POLICY = V2RetentionPolicy()
