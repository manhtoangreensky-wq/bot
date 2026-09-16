import pytest
import bot
from services.subdub_blackboxes import auto_multi_speaker_v2, auto_multi_speaker, auto_speaker


@pytest.fixture(autouse=True)
def _stub_capacity(monkeypatch):
    monkeypatch.setattr(bot, "SUBDUB_AUTO_SPEAKER_ACTIVATION_ENABLED", True)
    monkeypatch.setattr(bot, "subdub_auto_provider_capacity_ready", lambda *a, **kw: True)


def _base_multi_state(**overrides):
    state = {
        "job_id": "789abcdef01234567890",
        "voice_kind": "auto_speaker_gender",
        "voice_selection_mode": "auto_speaker",
        "auto_speaker_lane": "multi",
    }
    state.update(overrides)
    return state


def test_routing_a_historic_prefix_c11830a5():
    state = _base_multi_state(job_id="c11830a5a8a6c054514f")
    assert bot.subdub_auto_multi_v2_route_enabled(state) is True
    assert bot.subdub_auto_blackbox_runner(state) == auto_multi_speaker_v2.run_auto_multi_speaker_v2_blackbox
    assert state.get("subdub_engine_selected") == "auto_multi_speaker_v2"


def test_routing_b_historic_prefix_b653b52f():
    state = _base_multi_state(job_id="b653b52fe9dfc8381b14")
    assert bot.subdub_auto_multi_v2_route_enabled(state) is True
    assert bot.subdub_auto_blackbox_runner(state) == auto_multi_speaker_v2.run_auto_multi_speaker_v2_blackbox
    assert state.get("subdub_engine_selected") == "auto_multi_speaker_v2"


def test_routing_c_new_job_with_input_save_original_filename():
    state = _base_multi_state(
        job_id="e9d6a006985596692928",
        source="/tmp/toan_aas_pipeline/e9d6a006985596692928/test_m_i_multi.mp4",
        input_save={"original_filename": "test mới multi.mp4"},
    )
    assert bot.subdub_auto_multi_v2_route_enabled(state) is True
    assert bot.subdub_auto_blackbox_runner(state) == auto_multi_speaker_v2.run_auto_multi_speaker_v2_blackbox
    assert state.get("subdub_engine_selected") == "auto_multi_speaker_v2"
    assert "authorized_fixture_identity" in state.get("auto_multi_routing_reason", "")


def test_routing_d_new_job_with_source_file_name():
    state = _base_multi_state(
        job_id="ffff9999000011112222",
        source_file_name="test mới multi.mp4",
    )
    assert bot.subdub_auto_multi_v2_route_enabled(state) is True
    assert bot.subdub_auto_blackbox_runner(state) == auto_multi_speaker_v2.run_auto_multi_speaker_v2_blackbox


def test_routing_e_new_job_with_file_name():
    state = _base_multi_state(
        job_id="ffff9999000011112222",
        file_name="test mới multi.mp4",
    )
    assert bot.subdub_auto_multi_v2_route_enabled(state) is True
    assert bot.subdub_auto_blackbox_runner(state) == auto_multi_speaker_v2.run_auto_multi_speaker_v2_blackbox


def test_routing_f_new_job_source_path_sanitized_basename_fallback():
    state = _base_multi_state(
        job_id="ffff9999000011112222",
        source="/tmp/some_dir/test_m_i_multi.mp4",
    )
    assert bot.subdub_auto_multi_v2_route_enabled(state) is True
    assert bot.subdub_auto_blackbox_runner(state) == auto_multi_speaker_v2.run_auto_multi_speaker_v2_blackbox


def test_routing_g_unrelated_ordinary_video():
    state = _base_multi_state(
        job_id="ffff9999000011112222",
        source="/tmp/some_dir/regular_daily_vlog.mp4",
        input_save={"original_filename": "daily_vlog_ep1.mp4"},
    )
    assert bot.subdub_auto_multi_v2_route_enabled(state) is False
    assert bot.subdub_auto_blackbox_runner(state) == auto_multi_speaker.run_auto_multi_speaker_blackbox
    assert state.get("subdub_engine_selected") == "auto_multi_speaker"


def test_routing_h_missing_input_save_no_exception():
    state = _base_multi_state(job_id="ffff9999000011112222")
    assert bot.resolve_subdub_original_filename(state) == ""
    assert bot.subdub_auto_multi_v2_route_enabled(state) is False
    assert bot.subdub_auto_blackbox_runner(state) == auto_multi_speaker.run_auto_multi_speaker_blackbox


def test_routing_i_input_save_none_no_exception():
    state = _base_multi_state(job_id="ffff9999000011112222", input_save=None)
    assert bot.resolve_subdub_original_filename(state) == ""
    assert bot.subdub_auto_multi_v2_route_enabled(state) is False
    assert bot.subdub_auto_blackbox_runner(state) == auto_multi_speaker.run_auto_multi_speaker_blackbox


def test_routing_j_source_none_no_exception():
    state = _base_multi_state(job_id="ffff9999000011112222", source=None, input_save={"original_filename": None})
    assert bot.resolve_subdub_original_filename(state) == ""
    assert bot.subdub_auto_multi_v2_route_enabled(state) is False
    assert bot.subdub_auto_blackbox_runner(state) == auto_multi_speaker.run_auto_multi_speaker_blackbox


def test_routing_k_two_speaker_protected_auto2_unchanged():
    state = {
        "job_id": "e9d6a006985596692928",
        "voice_kind": "auto_speaker_gender",
        "voice_selection_mode": "auto_speaker",
        "source": "/tmp/toan_aas_pipeline/e9d6a006985596692928/test_m_i_multi.mp4",
        "input_save": {"original_filename": "test mới multi.mp4"},
    }
    assert bot.subdub_auto_multi_v2_route_enabled(state) is False
    assert bot.subdub_auto_blackbox_runner(state) == auto_speaker.run_auto_speaker_blackbox
    assert state.get("subdub_engine_selected") == "auto_speaker"


def test_routing_l_historical_job_50bff_reconstructed_state():
    state = _base_multi_state(
        job_id="50bff8620870539176fa",
        source="/tmp/toan_aas_pipeline/50bff8620870539176fa/test_m_i_multi.mp4",
        input_save={"original_filename": "test mới multi.mp4"},
        mode="subtitle_plus_dub",
        target_language=None,
    )
    assert bot.subdub_auto_multi_v2_route_enabled(state) is True
    engine_name, reason = bot.subdub_auto_routing_decision(state)
    assert engine_name == "auto_multi_speaker_v2"
    assert reason == "authorized_fixture_identity"
    assert bot.subdub_auto_blackbox_runner(state) == auto_multi_speaker_v2.run_auto_multi_speaker_v2_blackbox
    assert state.get("subdub_engine_selected") == "auto_multi_speaker_v2"


def test_routing_m_target_language_separation_none_vs_vi():
    state_none = _base_multi_state(
        job_id="50bff8620870539176fa",
        input_save={"original_filename": "test mới multi.mp4"},
        target_language=None,
    )
    state_vi = _base_multi_state(
        job_id="50bff8620870539176fa",
        input_save={"original_filename": "test mới multi.mp4"},
        target_language="vi",
    )
    assert bot.subdub_auto_multi_v2_route_enabled(state_none) is True
    assert bot.subdub_auto_multi_v2_route_enabled(state_vi) is True
    assert bot.subdub_auto_routing_decision(state_none)[0] == "auto_multi_speaker_v2"
    assert bot.subdub_auto_routing_decision(state_vi)[0] == "auto_multi_speaker_v2"


def test_routing_n_malformed_input_save_type():
    state = _base_multi_state(job_id="ffff9999000011112222", input_save="not_a_dict")
    assert bot.resolve_subdub_original_filename(state) == ""
    assert bot.subdub_auto_multi_v2_route_enabled(state) is False
    engine_name, reason = bot.subdub_auto_routing_decision(state)
    assert engine_name == "auto_multi_speaker"
    assert bot.subdub_auto_blackbox_runner(state) == auto_multi_speaker.run_auto_multi_speaker_blackbox


def test_routing_o_unrelated_unicode_filename_no_cutover():
    state = _base_multi_state(
        job_id="ffff9999000011112222",
        input_save={"original_filename": "hội_thảo_khoa_học_2026.mp4"},
    )
    assert bot.subdub_auto_multi_v2_route_enabled(state) is False
    engine_name, reason = bot.subdub_auto_routing_decision(state)
    assert engine_name == "auto_multi_speaker"
    assert bot.subdub_auto_blackbox_runner(state) == auto_multi_speaker.run_auto_multi_speaker_blackbox

