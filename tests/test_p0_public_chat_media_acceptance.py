from __future__ import annotations

import hashlib
import builtins
from pathlib import Path

import pytest

from services.public_chat_media import (
    PublicChatAttachment,
    attachment_memory_label,
    attachment_reservation_tokens,
    capability_decision,
    classify_attachment,
    detect_creation_intent,
    validate_attachment,
)
from services.chat_pro_pricing import estimate_reservation_usage, reserve_xu


def _write(path: Path, content: bytes) -> Path:
    path.write_bytes(content)
    return path


def test_capability_matrix_and_fail_closed_routes() -> None:
    assert capability_decision("free", ["image"])["route"] == "gemini"
    assert capability_decision("free", ["audio", "video", "pdf"])["route"] == "gemini"
    assert capability_decision("pro", ["image", "pdf"])["route"] == "opus"
    assert capability_decision("pro", ["audio"])["route"] == "unsupported"
    assert capability_decision("pro", ["video"])["route"] == "unsupported"
    assert capability_decision("free", [], requested_output="image")["route"] == "media_handoff"
    assert capability_decision("pro", [], requested_output="video")["route"] == "media_handoff"
    assert capability_decision("free", ["unknown"])["route"] == "unsupported"
    assert capability_decision("pro", [], requested_output="audio")["route"] == "unsupported"


def test_explicit_creation_intent_is_deterministic_and_multilingual() -> None:
    assert detect_creation_intent("Tạo ảnh sản phẩm màu xanh") == "image"
    assert detect_creation_intent("create an image of a cat") == "image"
    assert detect_creation_intent("生成一张图片") == "image"
    assert detect_creation_intent("tạo video quảng cáo 10 giây") == "video"
    assert detect_creation_intent("make a video for my shop") == "video"
    assert detect_creation_intent("创建一段视频") == "video"
    assert detect_creation_intent("cho tôi biết giá tạo ảnh") == "none"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Tạo danh sách khách hàng", "none"),
        ("Tạo ảnh giá bao nhiêu?", "none"),
        ("Hướng dẫn cách tạo ảnh", "none"),
        ("Tạo kịch bản video", "none"),
        ("Viết prompt cho video quảng cáo", "none"),
        ("Làm video quảng cáo", "video"),
        ("Dựng video giới thiệu sản phẩm", "video"),
        ("Tạo clip 10 giây", "video"),
        ("Làm ảnh bìa sản phẩm", "image"),
    ],
)
def test_creation_intent_uses_whole_words_and_excludes_advice_price_or_planning(
    text: str, expected: str
) -> None:
    assert detect_creation_intent(text) == expected


@pytest.mark.parametrize(
    ("mime", "name", "body"),
    [
        ("image/jpeg", "photo.jpg", b"\xff\xd8\xff" + b"jpeg"),
        ("image/png", "photo.png", b"\x89PNG\r\n\x1a\n" + b"png"),
        ("image/webp", "photo.webp", b"RIFF0000WEBP" + b"webp"),
        ("audio/mpeg", "voice.mp3", b"ID3" + b"mp3"),
        ("audio/wav", "voice.wav", b"RIFF0000WAVE" + b"wav"),
        ("audio/ogg", "voice.ogg", b"OggS" + b"ogg"),
        ("audio/mp4", "voice.m4a", b"\x00\x00\x00\x18ftypM4A "),
        ("video/mp4", "clip.mp4", b"\x00\x00\x00\x18ftypmp42"),
        ("video/quicktime", "clip.mov", b"\x00\x00\x00\x18ftypqt  "),
        ("video/webm", "clip.webm", b"\x1a\x45\xdf\xa3webm"),
    ],
)
def test_validate_supported_signatures_and_hash(tmp_path: Path, mime: str, name: str, body: bytes) -> None:
    path = _write(tmp_path / name, body)
    item = validate_attachment(
        temporary_path=path,
        mime_type=mime,
        file_name=name,
        declared_bytes=len(body),
    )
    assert item.actual_bytes == len(body)
    assert item.sha256 == hashlib.sha256(body).hexdigest()
    assert item.temporary_path == path
    assert item.kind == classify_attachment(mime, name)


def test_validate_rejects_mime_signature_and_size_failures(tmp_path: Path) -> None:
    path = _write(tmp_path / "photo.png", b"not a png")
    with pytest.raises(ValueError, match="signature"):
        validate_attachment(temporary_path=path, mime_type="image/png", file_name="photo.png")
    with pytest.raises(ValueError, match="unsupported"):
        validate_attachment(temporary_path=path, mime_type="application/octet-stream", file_name="photo.png")
    huge = _write(tmp_path / "huge.jpg", b"\xff\xd8\xff" + b"x" * (10 * 1024 * 1024))
    with pytest.raises(ValueError, match="size"):
        validate_attachment(
            temporary_path=huge,
            mime_type="image/jpeg",
            file_name="huge.jpg",
            declared_bytes=10 * 1024 * 1024 + 1,
        )


def test_validate_pdf_page_count_and_memory_label(tmp_path: Path) -> None:
    from pypdf import PdfWriter

    path = tmp_path / "brief.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with path.open("wb") as stream:
        writer.write(stream)
    item = validate_attachment(
        temporary_path=path,
        mime_type="application/pdf",
        file_name="brief.pdf",
        declared_bytes=path.stat().st_size,
    )
    assert item.page_count == 1
    assert "pages=1" in attachment_memory_label(item)


def test_validate_pdf_fails_closed_when_parser_is_unavailable(tmp_path: Path, monkeypatch) -> None:
    path = _write(tmp_path / "brief.pdf", b"%PDF-1.7\nminimal")
    original_import = builtins.__import__

    def blocked_import(name, *args, **kwargs):
        if name == "pypdf":
            raise ImportError("missing")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)
    with pytest.raises(ValueError, match="parser unavailable"):
        validate_attachment(
            temporary_path=path,
            mime_type="application/pdf",
            file_name="brief.pdf",
            declared_bytes=len(path.read_bytes()),
        )


def test_validate_duration_and_safe_memory_label(tmp_path: Path) -> None:
    path = _write(tmp_path / "voice.mp3", b"ID3" + b"voice")
    item = validate_attachment(
        temporary_path=path,
        mime_type="audio/mpeg",
        file_name=r"..\private\customer.mp3",
        duration_seconds=60,
    )
    assert "private" not in attachment_memory_label(item)
    assert str(path) not in attachment_memory_label(item)
    assert "bytes" not in attachment_memory_label(item)
    assert "customer.mp3" in attachment_memory_label(item)
    with pytest.raises(ValueError, match="duration"):
        validate_attachment(
            temporary_path=path,
            mime_type="audio/mpeg",
            file_name="voice.mp3",
            duration_seconds=30 * 60 + 1,
        )


def test_attachment_reservation_tokens_are_bounded() -> None:
    image = PublicChatAttachment("image", "image/png", "a.png", 1, 1, "a" * 64, Path("x"))
    pdf = PublicChatAttachment("pdf", "application/pdf", "a.pdf", 1, 1, "b" * 64, Path("x"), page_count=80)
    assert attachment_reservation_tokens([image]) == 8_192
    assert attachment_reservation_tokens([pdf]) == 640_000
    assert attachment_reservation_tokens([image, pdf]) == 648_192
    assert attachment_reservation_tokens([image, image, image, image]) == 32_768
    with pytest.raises(ValueError, match="attachment count"):
        attachment_reservation_tokens([image] * 5)
    with pytest.raises(ValueError, match="PDF count"):
        attachment_reservation_tokens([pdf, pdf])


def test_extra_input_tokens_increase_reservation_once_and_validate() -> None:
    messages = [{"role": "user", "content": "hello"}]
    base = estimate_reservation_usage(messages, 100)
    multimodal = estimate_reservation_usage(messages, 100, extra_input_tokens=8_192)
    assert multimodal.input_tokens == base.input_tokens + 8_192
    assert reserve_xu(messages, 100, extra_input_tokens=8_192) > reserve_xu(messages, 100)
    with pytest.raises(ValueError):
        estimate_reservation_usage(messages, 100, extra_input_tokens=-1)
    with pytest.raises(ValueError):
        estimate_reservation_usage(messages, 100, extra_input_tokens=1.5)
