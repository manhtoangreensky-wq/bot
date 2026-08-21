from __future__ import annotations

import asyncio
import hashlib
import io
import struct
import zlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

import bot
import local_worker
from services import video_edit_media_transport, video_local_editing, video_local_validation


def _image_bytes(image_format: str) -> bytes:
    payload = io.BytesIO()
    Image.new("RGB", (3, 2), (220, 40, 90)).save(payload, format=image_format)
    return payload.getvalue()


@pytest.mark.parametrize(
    ("extension", "image_format", "detected"),
    [(".png", "PNG", "png"), (".jpg", "JPEG", "jpeg"), (".webp", "WEBP", "webp")],
)
def test_static_logo_validator_uses_actual_bytes_dimensions_and_extension(
    tmp_path: Path,
    extension: str,
    image_format: str,
    detected: str,
) -> None:
    payload = _image_bytes(image_format)
    logo = tmp_path / f"logo{extension}"
    logo.write_bytes(payload)

    result = video_local_validation.validate_static_image_file(
        logo,
        expected_filename=logo.name,
    )
    assert result == {
        "ok": True,
        "reason": "",
        "format": detected,
        "width": 3,
        "height": 2,
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }

    mismatch = tmp_path / ("mismatch.jpg" if extension != ".jpg" else "mismatch.png")
    mismatch.write_bytes(payload)
    assert video_local_validation.validate_static_image_file(
        mismatch,
        expected_filename=mismatch.name,
    )["reason"] == "logo_extension_content_mismatch"

    truncated = tmp_path / f"truncated{extension}"
    truncated.write_bytes(payload[: max(1, len(payload) // 2)])
    assert video_local_validation.validate_static_image_file(
        truncated,
        expected_filename=truncated.name,
    )["ok"] is False

    if extension == ".png":
        def chunk(kind: bytes, data: bytes) -> bytes:
            return (
                struct.pack(">I", len(data))
                + kind
                + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
            )

        corrupt = tmp_path / "crc-valid-but-undecodable.png"
        corrupt.write_bytes(
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", 3, 2, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", b"not-a-zlib-stream")
            + chunk(b"IEND", b"")
        )
        assert video_local_validation.validate_static_image_file(
            corrupt,
            expected_filename=corrupt.name,
        )["reason"] == "logo_decode_invalid"


def test_bot_and_worker_reject_renamed_video_logo_before_plan_or_ffmpeg(
    tmp_path: Path,
) -> None:
    user_id = 93_301
    old_logo = {"file_id": "old-logo", "file_name": "old.png"}
    plan = video_local_editing.default_manual_edit_plan("")
    plan["logo_overlay"] = {
        "position": "bottom_left",
        "scale": 0.18,
        "opacity": 0.5,
    }
    bot.clear_video_editor_pending(user_id)
    bot.set_video_editor_pending(
        user_id,
        "await_logo",
        current_screen="logo_input",
        parent_callback="videoedit|logo_options",
        logo_parent_callback="videoedit|branding",
        pending_field="logo",
        source_file_id="source-video",
        inspection_complete=True,
        edit_session_id=f"edit-{user_id}",
        logo_source=old_logo,
        manual_edit_plan=plan,
    )

    class TelegramFile:
        def __init__(self, payload: bytes) -> None:
            self.payload = payload

        async def download_as_bytearray(self):
            return bytearray(self.payload)

    class TelegramBot:
        def __init__(self, payload: bytes) -> None:
            self.payload = payload

        async def get_file(self, _file_id):
            return TelegramFile(self.payload)

    class Message:
        photo = []
        video = None
        audio = None
        voice = None
        animation = None
        text = ""
        chat_id = user_id

        def __init__(self, file_id: str) -> None:
            self.document = SimpleNamespace(
                file_id=file_id,
                file_name="logo.png",
                mime_type="image/png",
                file_size=1_024,
            )
            self.replies: list[tuple[str, dict]] = []

        async def reply_text(self, text: str, **kwargs):
            self.replies.append((text, kwargs))
            return self

    renamed_mp4 = b"\x00\x00\x00\x18ftypmp42" + b"not-a-static-image" * 4
    invalid_message = Message("renamed-video-logo")
    invalid_context = SimpleNamespace(bot=TelegramBot(renamed_mp4), user_data={})
    try:
        assert asyncio.run(
            bot.handle_video_editor_pending_upload(
                SimpleNamespace(
                    effective_user=SimpleNamespace(id=user_id),
                    message=invalid_message,
                    callback_query=None,
                ),
                invalid_context,
            )
        ) is True
        after_invalid = dict(bot.get_video_editor_pending(user_id) or {})
        assert after_invalid["logo_source"] == old_logo
        assert after_invalid["manual_edit_plan"]["logo_overlay"] == plan["logo_overlay"]
        assert "ảnh" in invalid_message.replies[-1][0].lower()

        invalid_path = tmp_path / "logo.png"
        invalid_path.write_bytes(renamed_mp4)
        invalid_receipt = video_edit_media_transport.DownloadReceipt(
            path=str(invalid_path),
            bytes_written=len(renamed_mp4),
            sha256=hashlib.sha256(renamed_mp4).hexdigest(),
            lane="short_media",
            transport="test",
            declared_bytes=len(renamed_mp4),
        )
        with pytest.raises(local_worker.LocalVideoEditError, match="logo_format_invalid"):
            local_worker._video_edit_validate_logo_receipt(
                {"file_name": "logo.png"},
                invalid_receipt,
            )

        valid_png = _image_bytes("PNG")
        valid_message = Message("real-image-logo")
        valid_message.document.file_size = len(valid_png)
        valid_context = SimpleNamespace(bot=TelegramBot(valid_png), user_data={})
        assert asyncio.run(
            bot.handle_video_editor_pending_upload(
                SimpleNamespace(
                    effective_user=SimpleNamespace(id=user_id),
                    message=valid_message,
                    callback_query=None,
                ),
                valid_context,
            )
        ) is True
        after_valid = dict(bot.get_video_editor_pending(user_id) or {})
        assert after_valid["logo_source"]["file_id"] == "real-image-logo"
        assert after_valid["logo_source"]["detected_format"] == "png"
        assert after_valid["logo_source"]["width"] == 3
        assert after_valid["logo_source"]["height"] == 2
        assert after_valid["logo_source"]["content_sha256"] == hashlib.sha256(valid_png).hexdigest()
        assert after_valid["manual_edit_plan"]["logo_overlay"] == plan["logo_overlay"]
    finally:
        bot.clear_video_editor_pending(user_id)
