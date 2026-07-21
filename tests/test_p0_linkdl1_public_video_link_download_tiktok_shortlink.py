import asyncio
from pathlib import Path
from types import SimpleNamespace

import bot
from services import public_video_link_downloader as linkdl


GENERIC_ERROR = "Có lỗi khi xử lý lệnh. Bot chưa trừ Xu"


class FakeYoutubeDL:
    calls = []
    info = {
        "id": "7390000000000000001",
        "title": "TikTok demo",
        "uploader": "toanaas",
        "duration": 12,
        "filesize_approx": 2_000_000,
        "thumbnail": "https://p16-sign.tiktokcdn.com/cover.jpg",
        "ext": "mp4",
    }

    def __init__(self, opts):
        self.opts = dict(opts)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def extract_info(self, url, download=False):
        FakeYoutubeDL.calls.append({"url": url, "download": download, "opts": self.opts})
        if download:
            ext = "m4a" if "bestaudio" in str(self.opts.get("format") or "") else "mp4"
            path = Path(str(self.opts["outtmpl"]).replace("%(id)s", self.info["id"]).replace("%(ext)s", ext))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((b"\x00\x00\x00\x18ftypmp42" if ext == "mp4" else b"audio-data") + b"x" * 128)
        return dict(FakeYoutubeDL.info)


class FakeYtDlpModule:
    YoutubeDL = FakeYoutubeDL


def _service(tmp_path, monkeypatch):
    FakeYoutubeDL.calls = []
    monkeypatch.setattr(linkdl, "_lazy_import_yt_dlp", lambda: FakeYtDlpModule)
    return linkdl.PublicVideoLinkDownloader(data_dir=tmp_path / "link_downloads")


def test_tiktok_vt_shortlink_resolves_final_url(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    monkeypatch.setattr(
        service,
        "_follow_redirects",
        lambda url: ("https://www.tiktok.com/@toanaas/video/7390000000000000001?utm_source=share", 2, 200),
    )

    resolved = service.resolve_url("https://vt.tiktok.com/ZSCupGHK7/")

    assert resolved["ok"] is True
    assert resolved["platform"] == "TikTok"
    assert resolved["final_url"] == "https://www.tiktok.com/@toanaas/video/7390000000000000001"
    assert resolved["video_id"] == "7390000000000000001"
    assert resolved["redirect_count"] == 2


def test_tiktok_vm_shortlink_resolves_final_url(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    monkeypatch.setattr(service, "_follow_redirects", lambda url: ("https://www.tiktok.com/t/ZT1234567/", 1, 302))

    resolved = service.resolve_url("https://vm.tiktok.com/ZMabcdef/")

    assert resolved["ok"] is True
    assert resolved["platform"] == "TikTok"
    assert resolved["resolver_status"] == "resolved"
    assert resolved["final_url"] == "https://www.tiktok.com/t/ZT1234567/"


def test_tiktok_normal_url_supported(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    detected = service.detect_link("https://www.tiktok.com/@abc/video/123456789")
    resolved = service.resolve_url("https://www.tiktok.com/@abc/video/123456789?utm_medium=x")

    assert detected["ok"] is True
    assert detected["platform"] == "TikTok"
    assert resolved["final_url"] == "https://www.tiktok.com/@abc/video/123456789"


def test_unsupported_url_clean_blocker(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)

    result = service.prepare(linkdl.LinkDownloadRequest(url="https://example.com/article/1"))

    assert result.ok is False
    assert result.blocker in {"unsupported_platform", "unsupported_url"}
    assert "chưa hỗ trợ" in result.public_message
    assert "chưa trừ Xu" in result.public_message


def test_private_or_login_required_clean_blocker(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    detected = service.detect_link("https://www.tiktok.com/@abc/video/private-login")

    assert detected["ok"] is False
    assert detected["reason"] == "private_or_invalid"
    assert "riêng tư" in bot.video_downloader_guard_text("private_or_login_required", "vi", {"platform": "TikTok"})


def test_downloader_lazy_import_no_startup_crash(tmp_path, monkeypatch):
    service = linkdl.PublicVideoLinkDownloader(data_dir=tmp_path / "link_downloads")

    assert service.detect_link("https://www.tiktok.com/@abc/video/123")["ok"] is True


def test_downloader_unavailable_clean_copy(tmp_path, monkeypatch):
    service = linkdl.PublicVideoLinkDownloader(data_dir=tmp_path / "link_downloads")
    monkeypatch.setattr(linkdl, "_lazy_import_yt_dlp", lambda: None)

    result = service.prepare(linkdl.LinkDownloadRequest(url="https://www.tiktok.com/@abc/video/123"))

    assert result.ok is False
    assert result.blocker == "downloader_unavailable"
    assert "Bộ tải link đang tạm thời chưa sẵn sàng" in result.public_message


def test_linkdl_audit_reports_tiktok_support(tmp_path, monkeypatch):
    monkeypatch.setattr(bot, "video_downloader_provider", lambda: _service(tmp_path, monkeypatch))

    text = bot.linkdl_audit_text()

    assert "tiktok_shortlink_supported" in text
    assert "direct_mp4_supported" in text
    assert "no_private_bypass" in text


def test_tiktok_metadata_extracts_title_duration_thumbnail(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)

    metadata = service.metadata("https://www.tiktok.com/@abc/video/123")

    assert metadata["ok"] is True
    assert metadata["title"] == "TikTok demo"
    assert metadata["duration_seconds"] == 12
    assert metadata["thumbnail_url"].endswith("cover.jpg")


def test_duration_over_300_rejected_cleanly(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    FakeYoutubeDL.info = {**FakeYoutubeDL.info, "duration": 301}

    metadata = service.metadata(linkdl.LinkDownloadRequest(url="https://www.tiktok.com/@abc/video/123", max_duration_seconds=300))

    assert metadata["ok"] is False
    assert metadata["blocker"] == "duration_too_long"
    assert "chưa trừ Xu" in metadata["public_message"]
    FakeYoutubeDL.info = {**FakeYoutubeDL.info, "duration": 12}


def test_size_over_limit_rejected_cleanly(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    FakeYoutubeDL.info = {**FakeYoutubeDL.info, "filesize_approx": 101 * 1024 * 1024}

    metadata = service.metadata(linkdl.LinkDownloadRequest(url="https://www.tiktok.com/@abc/video/123", max_input_mb=100))

    assert metadata["ok"] is False
    assert metadata["blocker"] == "file_too_large"
    assert "File vượt giới hạn" in metadata["public_message"]
    FakeYoutubeDL.info = {**FakeYoutubeDL.info, "filesize_approx": 2_000_000}


def test_download_video_saves_valid_mp4(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)

    result = service.download(linkdl.LinkDownloadRequest(url="https://www.tiktok.com/@abc/video/123", requested_asset="video"))

    assert result["ok"] is True
    assert Path(result["video_path"]).read_bytes().startswith(b"\x00\x00\x00\x18ftyp")


def test_download_audio_saves_valid_audio(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)

    result = service.download(linkdl.LinkDownloadRequest(url="https://www.tiktok.com/@abc/video/123", requested_asset="audio"))

    assert result["ok"] is True
    assert Path(result["audio_path"]).read_bytes().startswith(b"audio-data")


def test_download_cover_saves_valid_image(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)

    def fake_download(url, output_path, limit_bytes):
        Path(output_path).write_bytes(b"\xff\xd8\xffcover")
        return Path(output_path).stat().st_size

    monkeypatch.setattr(service, "_download_url_to_file", fake_download)
    result = service.download(linkdl.LinkDownloadRequest(url="https://www.tiktok.com/@abc/video/123", requested_asset="cover"))

    assert result["ok"] is True
    assert Path(result["cover_path"]).read_bytes().startswith(b"\xff\xd8")


def test_tap_audio_after_video_does_not_resend_video(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    req = linkdl.LinkDownloadRequest(url="https://www.tiktok.com/@abc/video/123", requested_asset="video")
    first = service.download(req)
    second = service.download(linkdl.LinkDownloadRequest(url=req.url, requested_asset="audio", job_id=first["job_id"]))

    assert first["video_path"]
    assert second["audio_path"]
    assert second["video_path"] == first["video_path"]
    assert second["file_path"] == second["audio_path"]


def test_cached_asset_reused_when_valid(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    req = linkdl.LinkDownloadRequest(url="https://www.tiktok.com/@abc/video/123", requested_asset="video")
    first = service.download(req)
    before_calls = len([call for call in FakeYoutubeDL.calls if call["download"]])
    second = service.download(linkdl.LinkDownloadRequest(url=req.url, requested_asset="video", job_id=first["job_id"]))

    assert second["file_path"] == first["file_path"]
    assert second["debug"]["cache_reused"] is True
    assert len([call for call in FakeYoutubeDL.calls if call["download"]]) == before_calls


class FakeTelegramMessage:
    def __init__(self, fail_video=False):
        self.fail_video = fail_video
        self.calls = []
        self.chat_id = 123

    async def reply_video(self, **kwargs):
        self.calls.append(("video", kwargs))
        if self.fail_video:
            raise RuntimeError("telegram video fallback")
        return SimpleNamespace(message_id=11)

    async def reply_document(self, **kwargs):
        self.calls.append(("document", kwargs))
        return SimpleNamespace(message_id=12)

    async def reply_audio(self, **kwargs):
        self.calls.append(("audio", kwargs))
        return SimpleNamespace(message_id=13)

    async def reply_photo(self, **kwargs):
        self.calls.append(("photo", kwargs))
        return SimpleNamespace(message_id=14)


def test_send_video_when_under_limit(tmp_path):
    path = tmp_path / "video.mp4"
    path.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    query = SimpleNamespace(message=FakeTelegramMessage())

    delivery = asyncio.run(bot.send_video_downloader_file(query, {"file_path": str(path), "kind": "video", "platform": "TikTok"}, "vi"))

    assert delivery == {"method": "video", "message_id": 11}
    assert query.message.calls[0][0] == "video"


def test_send_document_fallback_when_needed(tmp_path):
    path = tmp_path / "video.mp4"
    path.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    query = SimpleNamespace(message=FakeTelegramMessage(fail_video=True))

    delivery = asyncio.run(bot.send_video_downloader_file(query, {"file_path": str(path), "kind": "video", "platform": "TikTok"}, "vi"))

    assert delivery == {"method": "document", "message_id": 12}
    assert [call[0] for call in query.message.calls] == ["video", "document"]


def test_output_over_limit_no_charge(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)

    def too_big(url, asset, output_dir, limit_bytes=None):
        path = Path(output_dir) / "too-big.mp4"
        path.write_bytes(b"x" * ((limit_bytes or 1024 * 1024) + 1))
        return path, ""

    monkeypatch.setattr(service, "_download_with_ytdlp", too_big)
    result = service.download(linkdl.LinkDownloadRequest(url="https://www.tiktok.com/@abc/video/123", requested_asset="video", max_output_mb=1))

    assert result["ok"] is False
    assert result["reason"] in {"file_too_large", "too_large"}
    assert "chưa trừ Xu" in result["public_message"]


def test_delivery_message_id_saved(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    result = service.download(linkdl.LinkDownloadRequest(url="https://www.tiktok.com/@abc/video/123", requested_asset="video"))
    service.mark_delivered(result["job_id"], message_id=777, method="video", asset="video")

    status = service.status(result["job_id"])

    assert status["delivery_message_id"] == 777


def test_no_generic_error_for_known_linkdl_blockers():
    for blocker in ("unsupported_url", "private_or_login_required", "file_too_large", "downloader_unavailable", "metadata_failed"):
        text = bot.video_downloader_guard_text(blocker, "vi", {"platform": "TikTok"})
        assert GENERIC_ERROR not in text
        assert "chưa trừ Xu" in text


def test_public_copy_no_traceback_no_cookie_no_provider_leak():
    text = "\n".join(
        [
            bot.video_downloader_start_text("vi"),
            bot.video_downloader_guard_text("downloader_unavailable", "vi", {"platform": "TikTok"}),
            bot.video_downloader_preview_text({"platform": "TikTok", "url": "https://www.tiktok.com/@abc/video/123"}, {"ok": True, "title": "demo"}, "vi"),
        ]
    ).lower()
    for forbidden in ("traceback", "provider", "api", "cookie", "session", "payload", "runtimeerror"):
        assert forbidden not in text


def test_rights_warning_present():
    assert "Vui lòng chỉ tải nội dung anh/chị có quyền sử dụng hoặc được phép lưu lại" in bot.video_downloader_start_text("vi")


def test_video_studio_menu_still_opens_link_downloader():
    callbacks = [button.callback_data for row in bot.main_video_keyboard("vi").inline_keyboard for button in row]

    assert "vdownload|start" in callbacks
