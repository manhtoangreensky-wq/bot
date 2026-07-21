import inspect

import bot
from services import workflow_graph_contract as graph_contract


def _graph():
    return graph_contract.build_p0_infra1_workflow_graph()


def _handlers():
    return bot.workflow_graph_registered_handlers()


def test_subdub_modes_have_graph_contract():
    graph = _graph()
    modes = graph.modes()
    assert {"subtitle_translate_video", "dub_video", "subtitle_dub_video", "auto_subtitle_video", "auto_subtitle_then_dub"}.issubset(modes)
    assert any(edge.handler_name == "handle_video_dubbing_callback" for edge in graph.edges)


def test_music_modes_have_graph_contract():
    graph = _graph()
    assert {"music_song", "music_instrumental", "confirm", "status_panel", "delivery_recover"}.issubset(graph.modes())
    assert any(edge.callback_pattern.startswith("progress|status|music_song|") for edge in graph.edges)


def test_video_status_has_graph_contract():
    graph = _graph()
    assert {"status_panel", "manual_refresh", "auto_refresh", "final_delivery"}.issubset(graph.modes())
    assert any(edge.handler_name == "handle_product_progress_callback" for edge in graph.edges)
    source = inspect.getsource(graph_contract).lower()
    assert "import n8n" not in source
    assert "n8n-nodes" not in source


def test_visible_buttons_have_handlers():
    assert graph_contract.assert_callback_visible_has_handler(_graph(), registered_handlers=_handlers()) == []


def test_handlers_have_graph_edges():
    assert graph_contract.assert_handler_has_graph_edge(_graph(), _handlers()) == []


def test_back_targets_exist():
    assert graph_contract.assert_back_target_valid(_graph()) == []


def test_manual_refresh_edges_are_read_only():
    graph = _graph()
    assert graph_contract.assert_manual_refresh_read_only(graph) == []
    for edge in graph.edges:
        if edge.action_type == graph_contract.WorkflowActionType.TERMINAL_REFRESH.value:
            assert edge.provider_allowed is False
            assert edge.wallet_allowed is False
            assert edge.reprocess_allowed is False


def test_provider_submit_only_after_final_confirm():
    assert graph_contract.assert_no_provider_before_final_confirm(_graph()) == []


def test_wallet_charge_only_after_valid_artifact():
    assert graph_contract.assert_no_wallet_before_valid_artifact(_graph()) == []


def test_terminal_delivered_blocks_failed_transition():
    graph = _graph()
    assert graph_contract.assert_terminal_lock_respected(graph) == []
    assert graph_contract.assert_no_fail_after_delivered(graph) == []
    assert graph_contract.assert_no_audio_fallback_after_video_delivered(graph) == []


def test_old_confirm_does_not_resubmit():
    assert graph_contract.assert_old_confirm_does_not_resubmit(_graph()) == []


def test_workflow_graph_audit_passes():
    payload = graph_contract.audit_workflow_graph(_graph(), registered_handlers=_handlers())
    assert payload["ok"] is True
    assert payload["node_count"] >= 20
    assert payload["edge_count"] >= 15
    assert "internal_contract_only_no_n8n" in bot.workflow_graph_audit_text("graph")


def test_workflow_route_audit_passes():
    payload = graph_contract.workflow_route_audit(_graph(), registered_handlers=_handlers())
    assert payload["ok"] is True
    assert payload["missing_handler"] == []
    assert payload["handler_without_graph_edge"] == []


def test_workflow_terminal_audit_passes():
    payload = graph_contract.workflow_terminal_audit(_graph(), registered_handlers=_handlers())
    assert payload["ok"] is True
    assert payload["invalid_terminal_transition"] == []
    assert payload["old_confirm_resubmit_risk"] == []


def test_workflow_callback_audit_passes():
    payload = graph_contract.workflow_callback_audit(_graph(), registered_handlers=_handlers())
    assert payload["ok"] is True
    assert payload["missing_handler"] == []


def test_workflow_audit_commands_registered_and_under_32_chars():
    source = inspect.getsource(bot.lifespan)
    for command in (
        "workflow_graph_audit",
        "workflow_route_audit",
        "workflow_terminal_audit",
        "workflow_callback_audit",
    ):
        assert len(command) <= 32
        assert f'CommandHandler("{command}"' in source
