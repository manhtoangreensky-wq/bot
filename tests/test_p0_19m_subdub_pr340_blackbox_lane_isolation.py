from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def test_pr340_rollback_removes_shared_tts_target_text_gate():
    assert "video_dubbing_target_language_requires_translation_for_tts" not in BOT_SOURCE
    assert "test_p0_19m_dub_tts_target_text_only" not in BOT_SOURCE


def test_subdub_modes_have_isolated_blackbox_prepare_wrappers():
    assert "async def _prepare_subtitle_only_blackbox" in BOT_SOURCE
    assert "async def _prepare_dub_only_blackbox" in BOT_SOURCE
    assert "async def _prepare_combo_blackbox" in BOT_SOURCE
    assert "selected_prepare_subtitles = {" in BOT_SOURCE
    assert "VIDEO_SUBTITLE_MODE_TRANSLATE: _prepare_subtitle_only_blackbox" in BOT_SOURCE
    assert "VIDEO_SUBTITLE_MODE_DUB: _prepare_dub_only_blackbox" in BOT_SOURCE
    assert "VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB: _prepare_combo_blackbox" in BOT_SOURCE


def test_run_subdub_pipeline_uses_selected_mode_blackbox():
    assert "prepare_subtitles=selected_prepare_subtitles" in BOT_SOURCE
    assert "subdub_blackbox_lane" in BOT_SOURCE
    assert "_subdub_blackbox_isolated" in BOT_SOURCE
