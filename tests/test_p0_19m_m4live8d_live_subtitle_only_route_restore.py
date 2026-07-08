from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    markers = (f"def {name}(", f"async def {name}(")
    starts = [BOT_SOURCE.find(marker) for marker in markers]
    starts = [start for start in starts if start >= 0]
    assert starts, f"{name} not found"
    start = min(starts)
    next_def = BOT_SOURCE.find("\ndef ", start + 1)
    next_async = BOT_SOURCE.find("\nasync def ", start + 1)
    candidates = [item for item in (next_def, next_async) if item >= 0]
    end = min(candidates) if candidates else len(BOT_SOURCE)
    return BOT_SOURCE[start:end]


def test_m4live8d_pr299_is_present_and_subtitle_ass_is_m4live7_chunked():
    source = _function_source("subdub_generate_ass_from_srt")

    assert "subdub_ass_text_chunks" in source
    assert "total_weight" in source
    assert "chunk_start = block_start + ((block_end - block_start)" in source
    assert "subtitle_timing_preserved: yes" not in source
    assert "subtitle_text_length_duration_split: no" not in source


def test_m4live8d_video_subtitle_upload_route_uses_video_path_not_file_path():
    source = _function_source("handle_video_dubbing_pending_upload")
    video_only_branch = source[
        source.index("if video_dubbing_is_video_only_mode(mode)")
        : source.index("if mode in {VIDEO_SUBTITLE_MODE_TRANSLATE, VIDEO_SUBTITLE_MODE_DUB}")
    ]

    assert 'active = VIDEO_DUBBING_FLOW_SUBTITLE_PLUS_DUB if mode == VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB else ("dub_audio" if mode == VIDEO_SUBTITLE_MODE_DUB else "subtitle_translate")' in video_only_branch
    assert 'output_type="video" if mode in {VIDEO_SUBTITLE_MODE_DUB, VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB} else "burn"' in video_only_branch
    assert 'active_flow=active' in video_only_branch
    assert 'VIDEO_DUBBING_FLOW_SUBTITLE_FILE_TRANSLATE' not in video_only_branch.split("active =", 1)[-1]


def test_m4live8d_subtitle_failure_copy_uses_m4live7_runtime_contract():
    core = _function_source("_execute_video_dubbing_pipeline_core")
    debug_payload = _function_source("subtitle_dub_debug_job_payload")

    for field in ("subtitle_translate_fail_reason", "public_failure_copy_source"):
        assert field not in core
        assert field not in debug_payload
    assert "video_dubbing_flow_failure_text(mode, lang)" in core
    assert "subdub_should_suppress_generic_fail_for_active_job" not in BOT_SOURCE


def test_m4live8d_subtitle_only_success_contract_still_has_mp4_receipt_buttons():
    receipt = _function_source("video_dubbing_receipt_text")
    keyboard = _function_source("video_dubbing_receipt_keyboard")
    labels = _function_source("video_dubbing_final_video_label")

    assert "Đã tạo video phụ đề thành công" in receipt
    assert "Đã gửi video" in receipt
    assert "video_button = video_dubbing_final_video_label(mode, lang)" in keyboard
    assert "Tải video phụ đề dịch" in labels
    assert "Tải SRT dịch" in keyboard


def test_m4live8d_dub_modes_are_back_on_m4live7_runtime_contract():
    diff_sensitive = "\n".join(
        [
            _function_source("resolve_video_dub_tts_voice"),
            _function_source("video_dubbing_voice_payload"),
        ]
    )

    assert "subdub_default_tts_voice_for_gender" not in BOT_SOURCE
    assert "subtitle_translate_fail_reason" not in diff_sensitive
    assert "m4live7_subtitle_only_route_active" not in diff_sensitive
