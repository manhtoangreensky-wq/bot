"""Internal workflow graph contract for high-risk TOAN AAS product flows.

This module is a read-only contract/audit layer. It borrows the node/edge
idea from workflow tools, but it does not import or run n8n or any external
workflow runtime.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable


class WorkflowMode(str, Enum):
    SUBDUB = "subdub"
    MUSIC = "music"
    VIDEO = "video"


class WorkflowTerminalState(str, Enum):
    NONE = ""
    DELIVERED = "delivered"
    FAILED_NO_CHARGE = "failed_no_charge"
    FAILED_REFUNDED = "failed_refunded"
    NEEDS_ADMIN_REVIEW = "needs_admin_review"


class WorkflowActionType(str, Enum):
    RENDER_ONLY = "render_only"
    STATE_UPDATE = "state_update"
    SUBMIT_PROVIDER = "submit_provider"
    POLL_STATUS = "poll_status"
    DELIVER_ARTIFACT = "deliver_artifact"
    TERMINAL_REFRESH = "terminal_refresh"


@dataclass(frozen=True)
class WorkflowEdge:
    callback_pattern: str
    source_node: str
    target_node: str
    handler_name: str
    action_type: str
    provider_allowed: bool = False
    wallet_allowed: bool = False
    reprocess_allowed: bool = False
    required_state_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkflowNode:
    node_id: str
    product_area: str
    mode: str
    public_title: str
    allowed_buttons: tuple[str, ...] = ()
    required_state_keys: tuple[str, ...] = ()
    next_edges: tuple[str, ...] = ()
    back_target: str = ""
    terminal_policy: str = WorkflowTerminalState.NONE.value


@dataclass
class WorkflowGraph:
    nodes: dict[str, WorkflowNode] = field(default_factory=dict)
    edges: list[WorkflowEdge] = field(default_factory=list)

    def add_node(self, node: WorkflowNode) -> None:
        self.nodes[node.node_id] = node

    def add_edge(self, edge: WorkflowEdge) -> None:
        self.edges.append(edge)

    def node_count(self) -> int:
        return len(self.nodes)

    def edge_count(self) -> int:
        return len(self.edges)

    def modes(self) -> set[str]:
        return {node.mode for node in self.nodes.values() if node.mode}

    def product_areas(self) -> set[str]:
        return {node.product_area for node in self.nodes.values() if node.product_area}

    def callback_patterns(self) -> set[str]:
        return {edge.callback_pattern for edge in self.edges}

    def handler_names(self) -> set[str]:
        return {edge.handler_name for edge in self.edges if edge.handler_name}

    def edges_for_handler(self, handler_name: str) -> list[WorkflowEdge]:
        return [edge for edge in self.edges if edge.handler_name == handler_name]

    def matching_edges(self, callback_data: str) -> list[WorkflowEdge]:
        value = str(callback_data or "")
        return [edge for edge in self.edges if callback_matches(edge.callback_pattern, value)]


def callback_matches(pattern: str, callback_data: str) -> bool:
    pattern = str(pattern or "")
    callback_data = str(callback_data or "")
    if not pattern:
        return False
    if pattern == callback_data:
        return True
    if "*" in pattern:
        return fnmatch.fnmatchcase(callback_data, pattern)
    return callback_data.startswith(pattern)


def _node(
    node_id: str,
    product_area: str,
    mode: str,
    title: str,
    *,
    buttons: Iterable[str] = (),
    required: Iterable[str] = (),
    back: str = "",
    terminal: str = "",
) -> WorkflowNode:
    return WorkflowNode(
        node_id=node_id,
        product_area=product_area,
        mode=mode,
        public_title=title,
        allowed_buttons=tuple(buttons),
        required_state_keys=tuple(required),
        back_target=back,
        terminal_policy=terminal,
    )


def _edge(
    callback_pattern: str,
    source: str,
    target: str,
    handler: str,
    action: WorkflowActionType | str,
    *,
    provider: bool = False,
    wallet: bool = False,
    reprocess: bool = False,
    required: Iterable[str] = (),
) -> WorkflowEdge:
    return WorkflowEdge(
        callback_pattern=callback_pattern,
        source_node=source,
        target_node=target,
        handler_name=handler,
        action_type=str(action.value if isinstance(action, WorkflowActionType) else action),
        provider_allowed=bool(provider),
        wallet_allowed=bool(wallet),
        reprocess_allowed=bool(reprocess),
        required_state_keys=tuple(required),
    )


def build_p0_infra1_workflow_graph() -> WorkflowGraph:
    graph = WorkflowGraph()

    for node in (
        _node("subdub_start", "subdub", "subdub", "SubDub start", buttons=("videodub|type|*",), back="menu_video"),
        _node("subdub_auto_subtitle_video", "subdub", "auto_subtitle_video", "Tao phu de video", back="subdub_start"),
        _node("subdub_translate_video", "subdub", "subtitle_translate_video", "Dich phu de video", back="subdub_start"),
        _node("subdub_dub_video", "subdub", "dub_video", "Long tieng video", back="subdub_start"),
        _node("subdub_subtitle_dub_video", "subdub", "subtitle_dub_video", "Phu de va long tieng", back="subdub_start"),
        _node("subdub_auto_subtitle_then_dub", "subdub", "auto_subtitle_then_dub", "Phu de roi long tieng", back="subdub_start"),
        _node("subdub_confirm", "subdub", "confirm", "Xac nhan SubDub", required=("media_ready", "final_confirmed"), back="subdub_start"),
        _node("subdub_status", "subdub", "status_panel", "Trang thai SubDub", back="subdub_start"),
        _node("subdub_delivered", "subdub", "terminal", "SubDub delivered", terminal=WorkflowTerminalState.DELIVERED.value),
        _node("subdub_failed", "subdub", "terminal", "SubDub failed no charge", terminal=WorkflowTerminalState.FAILED_NO_CHARGE.value),
        _node("music_hub", "music", "music", "Music hub", buttons=("music_quick|showroom|*",), back="menu_main"),
        _node("music_song", "music", "music_song", "Tao bai hat", back="music_hub"),
        _node("music_instrumental", "music", "music_instrumental", "Tao nhac nen", back="music_hub"),
        _node("music_confirm", "music", "confirm", "Xac nhan tao nhac", required=("final_confirmed", "idempotency_key"), back="music_hub"),
        _node("music_status", "music", "status_panel", "Trang thai nhac", back="music_hub"),
        _node("music_delivery_recover", "music", "delivery_recover", "Khoi phuc giao file nhac", back="music_status"),
        _node("music_delivered", "music", "terminal", "Music delivered", terminal=WorkflowTerminalState.DELIVERED.value),
        _node("music_failed", "music", "terminal", "Music failed no charge", terminal=WorkflowTerminalState.FAILED_NO_CHARGE.value),
        _node("video_status", "video", "status_panel", "Trang thai video", back="menu_video"),
        _node("video_manual_refresh", "video", "manual_refresh", "Cap nhat trang thai video", back="video_status"),
        _node("video_auto_refresh", "video", "auto_refresh", "Tu dong cap nhat video", back="video_status"),
        _node("video_final_confirm", "video", "final_confirm", "Xac nhan tao video", required=("final_confirmed", "idempotency_key"), back="video_status"),
        _node("video_final_delivery", "video", "final_delivery", "Giao video", required=("valid_artifact",), back="video_status"),
        _node("video_delivered", "video", "terminal", "Video delivered", terminal=WorkflowTerminalState.DELIVERED.value),
        _node("video_failed", "video", "terminal", "Video failed no charge", terminal=WorkflowTerminalState.FAILED_NO_CHARGE.value),
        _node("menu_video", "video", "menu", "Video menu", back="menu_main"),
        _node("menu_main", "system", "menu", "Main menu"),
    ):
        graph.add_node(node)

    for edge in (
        _edge("videodub|type|subtitle_create", "subdub_start", "subdub_auto_subtitle_video", "handle_video_dubbing_callback", WorkflowActionType.STATE_UPDATE),
        _edge("videodub|type|subtitle_translate", "subdub_start", "subdub_translate_video", "handle_video_dubbing_callback", WorkflowActionType.STATE_UPDATE),
        _edge("videodub|type|dub", "subdub_start", "subdub_dub_video", "handle_video_dubbing_callback", WorkflowActionType.STATE_UPDATE),
        _edge("videodub|type|subtitle_plus_dub", "subdub_start", "subdub_subtitle_dub_video", "handle_video_dubbing_callback", WorkflowActionType.STATE_UPDATE),
        _edge("videodub|status_back_type", "subdub_status", "subdub_start", "handle_video_dubbing_callback", WorkflowActionType.RENDER_ONLY),
        _edge("videodub|confirm*", "subdub_confirm", "subdub_status", "handle_video_dubbing_callback", WorkflowActionType.SUBMIT_PROVIDER, provider=True, required=("final_confirmed", "idempotency_key")),
        _edge("videodub|subdub_status|*", "subdub_status", "subdub_status", "handle_video_dubbing_callback", WorkflowActionType.TERMINAL_REFRESH),
        _edge("videodub|delivered|*", "subdub_status", "subdub_delivered", "handle_video_dubbing_callback", WorkflowActionType.DELIVER_ARTIFACT, required=("valid_artifact",)),
        _edge("music_quick|showroom|ai_music", "music_hub", "music_song", "handle_music_quick_callback", WorkflowActionType.RENDER_ONLY),
        _edge("music_quick|song|*", "music_song", "music_confirm", "handle_music_quick_callback", WorkflowActionType.STATE_UPDATE),
        _edge("music_quick|instrumental|*", "music_instrumental", "music_confirm", "handle_music_quick_callback", WorkflowActionType.STATE_UPDATE),
        _edge("music_quick|confirm|*", "music_confirm", "music_status", "handle_music_quick_callback", WorkflowActionType.SUBMIT_PROVIDER, provider=True, required=("final_confirmed", "idempotency_key")),
        _edge("progress|status|music_song|*", "music_status", "music_status", "handle_product_progress_callback", WorkflowActionType.TERMINAL_REFRESH),
        _edge("progress|status|music_bg|*", "music_status", "music_status", "handle_product_progress_callback", WorkflowActionType.TERMINAL_REFRESH),
        _edge("music_quick|delivery_recover|*", "music_status", "music_delivery_recover", "handle_music_quick_callback", WorkflowActionType.DELIVER_ARTIFACT, required=("valid_artifact",)),
        _edge("progress|status|frame_video|*", "video_status", "video_manual_refresh", "handle_product_progress_callback", WorkflowActionType.TERMINAL_REFRESH),
        _edge("progress|status|multiscene_video|*", "video_status", "video_manual_refresh", "handle_product_progress_callback", WorkflowActionType.TERMINAL_REFRESH),
        _edge("video|status|*", "video_status", "video_manual_refresh", "handle_public_video_status_callback", WorkflowActionType.TERMINAL_REFRESH),
        _edge("vproduct|storyboard_confirm", "video_final_confirm", "video_status", "handle_video_product_callback", WorkflowActionType.SUBMIT_PROVIDER, provider=True, required=("final_confirmed", "idempotency_key")),
        _edge("vproduct|b14_quality|*", "video_final_confirm", "video_status", "handle_video_product_callback", WorkflowActionType.STATE_UPDATE),
        _edge("vproduct|deliver|*", "video_final_delivery", "video_delivered", "handle_video_product_callback", WorkflowActionType.DELIVER_ARTIFACT, required=("valid_artifact",)),
    ):
        graph.add_edge(edge)

    return graph


def default_high_risk_handlers() -> set[str]:
    return {
        "handle_video_dubbing_callback",
        "handle_music_quick_callback",
        "handle_product_progress_callback",
        "handle_video_product_callback",
        "handle_public_video_status_callback",
    }


def assert_callback_visible_has_handler(
    graph: WorkflowGraph,
    visible_callbacks: Iterable[str] | None = None,
    registered_handlers: Iterable[str] | None = None,
) -> list[str]:
    callbacks = list(visible_callbacks or graph.callback_patterns())
    handlers = set(registered_handlers or default_high_risk_handlers())
    missing: list[str] = []
    for callback in callbacks:
        matched = graph.matching_edges(callback.replace("*", "sample"))
        if not matched:
            missing.append(callback)
            continue
        if not any(edge.handler_name in handlers for edge in matched):
            missing.append(callback)
    return missing


def assert_handler_has_graph_edge(graph: WorkflowGraph, handler_names: Iterable[str] | None = None) -> list[str]:
    handlers = set(handler_names or default_high_risk_handlers())
    graph_handlers = graph.handler_names()
    return sorted(handler for handler in handlers if handler not in graph_handlers)


def assert_back_target_valid(graph: WorkflowGraph) -> list[str]:
    return sorted(node.node_id for node in graph.nodes.values() if node.back_target and node.back_target not in graph.nodes)


def assert_manual_refresh_read_only(graph: WorkflowGraph) -> list[str]:
    risks: list[str] = []
    for edge in graph.edges:
        if edge.action_type != WorkflowActionType.TERMINAL_REFRESH.value:
            continue
        if edge.provider_allowed or edge.wallet_allowed or edge.reprocess_allowed:
            risks.append(edge.callback_pattern)
    return risks


def assert_terminal_lock_respected(graph: WorkflowGraph) -> list[str]:
    terminal_nodes = {
        node.node_id: node.terminal_policy
        for node in graph.nodes.values()
        if node.terminal_policy in {WorkflowTerminalState.DELIVERED.value, WorkflowTerminalState.FAILED_NO_CHARGE.value, WorkflowTerminalState.FAILED_REFUNDED.value}
    }
    risks: list[str] = []
    for edge in graph.edges:
        source_terminal = terminal_nodes.get(edge.source_node)
        target_terminal = terminal_nodes.get(edge.target_node)
        if source_terminal and target_terminal and source_terminal != target_terminal:
            risks.append(edge.callback_pattern)
        if source_terminal == WorkflowTerminalState.DELIVERED.value and edge.action_type == WorkflowActionType.SUBMIT_PROVIDER.value:
            risks.append(edge.callback_pattern)
    return sorted(set(risks))


def assert_no_provider_before_final_confirm(graph: WorkflowGraph) -> list[str]:
    risks: list[str] = []
    for edge in graph.edges:
        if edge.provider_allowed or edge.action_type == WorkflowActionType.SUBMIT_PROVIDER.value:
            if "final_confirmed" not in set(edge.required_state_keys):
                risks.append(edge.callback_pattern)
    return risks


def assert_no_wallet_before_valid_artifact(graph: WorkflowGraph) -> list[str]:
    risks: list[str] = []
    for edge in graph.edges:
        if edge.wallet_allowed and "valid_artifact" not in set(edge.required_state_keys):
            risks.append(edge.callback_pattern)
    return risks


def assert_no_fail_after_delivered(graph: WorkflowGraph) -> list[str]:
    risks: list[str] = []
    for edge in graph.edges:
        source = graph.nodes.get(edge.source_node)
        target = graph.nodes.get(edge.target_node)
        if (
            source
            and target
            and source.terminal_policy == WorkflowTerminalState.DELIVERED.value
            and target.terminal_policy in {WorkflowTerminalState.FAILED_NO_CHARGE.value, WorkflowTerminalState.FAILED_REFUNDED.value}
        ):
            risks.append(edge.callback_pattern)
    return risks


def assert_no_audio_fallback_after_video_delivered(graph: WorkflowGraph) -> list[str]:
    risks: list[str] = []
    for edge in graph.edges:
        source = graph.nodes.get(edge.source_node)
        if source and source.product_area == "video" and source.terminal_policy == WorkflowTerminalState.DELIVERED.value:
            if "audio" in edge.target_node or "audio" in edge.callback_pattern:
                risks.append(edge.callback_pattern)
    return risks


def assert_mode_copy_matches_graph(graph: WorkflowGraph) -> list[str]:
    mismatches: list[str] = []
    forbidden_by_area = {
        "music": ("subdub", "phu de", "long tieng", "video delivered"),
        "subdub": ("bai hat", "nhac nen", "music delivered"),
        "video": ("bai hat", "subdub delivered"),
    }
    for node in graph.nodes.values():
        title = node.public_title.lower()
        for forbidden in forbidden_by_area.get(node.product_area, ()):
            if forbidden in title:
                mismatches.append(node.node_id)
                break
    return mismatches


def assert_old_confirm_does_not_resubmit(graph: WorkflowGraph) -> list[str]:
    risks: list[str] = []
    for edge in graph.edges:
        if "confirm" not in edge.callback_pattern:
            continue
        if edge.reprocess_allowed or "idempotency_key" not in set(edge.required_state_keys):
            risks.append(edge.callback_pattern)
    return risks


def audit_workflow_graph(
    graph: WorkflowGraph | None = None,
    *,
    visible_callbacks: Iterable[str] | None = None,
    registered_handlers: Iterable[str] | None = None,
) -> dict[str, Any]:
    graph = graph or build_p0_infra1_workflow_graph()
    handlers = set(registered_handlers or default_high_risk_handlers())
    payload = {
        "product_area": ",".join(sorted(graph.product_areas())),
        "mode": ",".join(sorted(graph.modes())),
        "node_count": graph.node_count(),
        "edge_count": graph.edge_count(),
        "missing_handler": assert_callback_visible_has_handler(graph, visible_callbacks, handlers),
        "handler_without_graph_edge": assert_handler_has_graph_edge(graph, handlers),
        "missing_back_target": assert_back_target_valid(graph),
        "invalid_terminal_transition": assert_terminal_lock_respected(graph) + assert_no_fail_after_delivered(graph),
        "refresh_reprocess_risk": assert_manual_refresh_read_only(graph),
        "provider_before_confirm_risk": assert_no_provider_before_final_confirm(graph),
        "wallet_before_artifact_risk": assert_no_wallet_before_valid_artifact(graph),
        "audio_fallback_after_video_delivered_risk": assert_no_audio_fallback_after_video_delivered(graph),
        "mode_copy_mismatch": assert_mode_copy_matches_graph(graph),
        "old_confirm_resubmit_risk": assert_old_confirm_does_not_resubmit(graph),
    }
    payload["ok"] = not any(
        payload[key]
        for key in (
            "missing_handler",
            "handler_without_graph_edge",
            "missing_back_target",
            "invalid_terminal_transition",
            "refresh_reprocess_risk",
            "provider_before_confirm_risk",
            "wallet_before_artifact_risk",
            "audio_fallback_after_video_delivered_risk",
            "mode_copy_mismatch",
            "old_confirm_resubmit_risk",
        )
    )
    return payload


def workflow_route_audit(graph: WorkflowGraph | None = None, **kwargs: Any) -> dict[str, Any]:
    payload = audit_workflow_graph(graph, **kwargs)
    return {
        "ok": bool(payload["ok"] and not payload["missing_handler"] and not payload["handler_without_graph_edge"]),
        **payload,
    }


def workflow_terminal_audit(graph: WorkflowGraph | None = None, **kwargs: Any) -> dict[str, Any]:
    payload = audit_workflow_graph(graph, **kwargs)
    return {
        "ok": bool(payload["ok"] and not payload["invalid_terminal_transition"] and not payload["old_confirm_resubmit_risk"]),
        **payload,
    }


def workflow_callback_audit(graph: WorkflowGraph | None = None, **kwargs: Any) -> dict[str, Any]:
    payload = audit_workflow_graph(graph, **kwargs)
    return {
        "ok": bool(payload["ok"] and not payload["missing_handler"]),
        **payload,
    }
