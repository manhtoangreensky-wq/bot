import asyncio
import hashlib
import inspect
import subprocess
from pathlib import Path

import bot


ROOT = Path(__file__).resolve().parents[1]
M4LIVE2_SHA = "526dfac3"
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")
M4LIVE2_SOURCE = subprocess.check_output(
    ["git", "show", f"{M4LIVE2_SHA}:bot.py"],
    cwd=ROOT,
    text=True,
    encoding="utf-8",
    errors="replace",
)


def _function_source(source: str, name: str, *, async_def: bool = False) -> str:
    marker = f"{'async ' if async_def else ''}def {name}("
    start = source.find(marker)
    assert start >= 0, name
    next_def = source.find("\ndef ", start + 1)
    next_async = source.find("\nasync def ", start + 1)
    endings = [item for item in (next_def, next_async) if item >= 0]
    end = min(endings) if endings else len(source)
    return source[start:end]


def _hash(value: str) -> str:
    return hashlib.sha1(value.strip().encode("utf-8")).hexdigest()


def test_m4live6_baseline_source_is_m4live2_526dfac3():
    assert subprocess.check_output(["git", "show", "--no-patch", "--format=%h", M4LIVE2_SHA], cwd=ROOT, text=True).strip() == "526dfac"


def test_m4live6_restores_m4live2_runtime_functions():
    names = {
        "_execute_video_dubbing_pipeline_core": True,
        "subdub_duration_gate_payload": False,
        "subdub_generate_ass_from_srt": False,
        "subdub_normalize_style": False,
        "subdub_progress_text": False,
        "subdub_voice_style_state_fields": False,
        "subdub_dub_speech_config": False,
        "video_dubbing_receipt_text": False,
    }
    for name, is_async in names.items():
        assert _hash(_function_source(BOT_SOURCE, name, async_def=is_async)) == _hash(
            _function_source(M4LIVE2_SOURCE, name, async_def=is_async)
        ), name


class _Sent:
    message_id = "msg-1"


class _Message:
    def __init__(self):
        self.documents = []
        self.audio = []

    async def reply_document(self, **kwargs):
        self.documents.append(kwargs)
        return _Sent()

    async def reply_audio(self, **kwargs):
        self.audio.append(kwargs)
        return _Sent()


async def _fake_video_delivery(*args, **kwargs):
    return {
        "sent": True,
        "delivery_method": "video",
        "telegram_message_id": "video-1",
        "file_size_mb": 1.0,
        "size_limit_used": 45.0,
    }


def test_m4live6_video_mode_mp4_delivery_does_not_auto_send_srt(monkeypatch):
    monkeypatch.setattr(bot, "send_generated_video_bytes_for_delivery", _fake_video_delivery)
    message = _Message()

    result = asyncio.run(
        bot.send_public_subtitle_dub_final_outputs(
            message,
            mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
            subtitle_items=[{"output_type": "srt", "filename": "toan_aas_subtitle_translate.srt", "bytes": b"1\n"}],
            video_bytes=b"fake mp4",
            include_subtitle_outputs=True,
        )
    )

    assert result["final_mp4_delivered"] is True
    assert result["srt_auto_send_suppressed"] is True
    assert result["documents"] == 0
    assert message.documents == []


def test_m4live6_video_mode_blocks_srt_only_mp4_replacement():
    message = _Message()

    result = asyncio.run(
        bot.send_public_subtitle_dub_final_outputs(
            message,
            mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
            subtitle_items=[{"output_type": "srt", "filename": "toan_aas_subtitle_translate.srt", "bytes": b"1\n"}],
            video_bytes=b"",
            include_subtitle_outputs=True,
        )
    )

    assert result["success_blocked_reason"] == "missing_valid_delivered_mp4"
    assert result["documents"] == 0
    assert message.documents == []


def test_m4live6_file_subtitle_flow_can_still_send_safe_srt():
    message = _Message()

    result = asyncio.run(
        bot.send_public_subtitle_dub_final_outputs(
            message,
            mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
            active_flow=bot.VIDEO_DUBBING_FLOW_SUBTITLE_FILE_TRANSLATE,
            subtitle_items=[{"output_type": "srt", "filename": "toan_aas_subtitle_translate.srt", "bytes": b"1\n"}],
            video_bytes=b"",
            include_subtitle_outputs=True,
        )
    )

    assert result["documents"] == 1
    assert len(message.documents) == 1


def test_m4live6_blocks_db_backup_artifact_delivery():
    assert bot.subdub_forbidden_delivery_artifact_reason("toan_aas_backup_20260707_1727.db") == ".db"
    assert bot.subdub_forbidden_delivery_artifact_reason("customer.sqlite3") == ".sqlite"
    assert bot.subdub_forbidden_delivery_artifact_reason("runtime.env") == ".env"
    assert bot.subdub_forbidden_delivery_artifact_reason("subdub.log") == ".log"
    assert bot.subdub_forbidden_delivery_artifact_reason("secrets.txt") == "secrets"
    assert bot.subdub_forbidden_delivery_artifact_reason("toan_aas_video.mp4") == ""
    assert bot.subdub_forbidden_delivery_artifact_reason("toan_aas_subtitle_translate.srt") == ""


def test_m4live6_forbidden_artifact_is_not_sent_even_in_file_flow():
    message = _Message()

    result = asyncio.run(
        bot.send_public_subtitle_dub_final_outputs(
            message,
            mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
            active_flow=bot.VIDEO_DUBBING_FLOW_SUBTITLE_FILE_TRANSLATE,
            subtitle_items=[{"output_type": "srt", "filename": "toan_aas_backup_20260707_1727.db", "bytes": b"secret"}],
            video_bytes=b"",
            include_subtitle_outputs=True,
        )
    )

    assert result["documents"] == 0
    assert result["forbidden_artifact_blocked"] is True
    assert message.documents == []


def test_m4live6_auto_backup_does_not_send_db_document():
    source = BOT_SOURCE
    start = source.find("async def auto_backup_loop():")
    assert start >= 0
    end = source.find("tg_auto_backup_task = asyncio.create_task(auto_backup_loop())", start)
    loop_source = source[start:end]

    assert "Auto backup Telegram document suppressed" in loop_source
    assert ".send_document(" not in loop_source


def test_m4live6_no_music_product_video_cskh_payos_runtime_files_touched():
    changed = subprocess.check_output(["git", "diff", "--name-only", "origin/main"], cwd=ROOT, text=True)
    changed_paths = {line.strip().replace("\\", "/") for line in changed.splitlines() if line.strip()}
    assert changed_paths <= {
        "bot.py",
        "tests/test_p0_19m_m4live2_subdub_final_polish_lock.py",
        "tests/test_p0_19m_m4live5_subdub_full_runtime_rollback_to_3mp4_baseline.py",
        "tests/test_p0_19m_m4live6_restore_m4live2_and_block_artifacts.py",
    }
