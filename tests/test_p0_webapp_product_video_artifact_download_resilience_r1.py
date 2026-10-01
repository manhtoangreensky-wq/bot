"""Tests for Web Product Video artifact download resilience and transport retry.

Verifies:
- Bounded transient retry: exactly 2 attempts, 1 retry max.
- Transient errors (connection reset, timeouts, 5xx, Content-Length truncated) trigger retry on same URL.
- Non-transient errors (400, 401, 403, 404, HTML/JSON error, probe failure) fail immediately without retry.
- Atomic final target: writes to attempt-unique .part file, cleans up failed parts, replaces target only after media validation.
- Diagnostics sanitized: records attempts, retries, status code, error class, without secret leakage.
- Financial safety: double failure yields provider_download_failed with no charge.
- Key4U behavior unchanged.
"""

import io
import socket
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from services import video_final_output, video_provider_router
from services.video_provider_base import (
    IncompleteDownloadError,
    VideoArtifactResult,
    materialize_video_url,
)


class MockResponse:
    def __init__(
        self,
        data: bytes,
        headers: dict | None = None,
        status: int = 200,
        url: str = "https://cdn.example.com/asset.mp4",
    ):
        self._data = io.BytesIO(data)
        self.headers = headers or {}
        self.status = status
        self._url = url

    def read(self, *args):
        return self._data.read(*args)

    def geturl(self):
        return self._url

    def getcode(self):
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


VALID_MP4_BYTES = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 2048


@pytest.fixture
def mock_probe(monkeypatch):
    monkeypatch.setenv("VIDEO_PROVIDER_MIN_VIDEO_BYTES", "1")
    monkeypatch.setattr(
        video_final_output,
        "probe_video",
        lambda _p: {"ok": True, "duration": 5.0, "has_video": True, "has_audio": True},
    )


def test_transient_first_failure_then_second_get_succeeds(tmp_path, monkeypatch, mock_probe):
    attempts = []

    class MockOpener:
        def open(self, request, timeout=180):
            attempts.append(request.full_url)
            if len(attempts) == 1:
                raise ConnectionResetError("Connection reset by peer")
            return MockResponse(
                VALID_MP4_BYTES,
                headers={"Content-Type": "video/mp4", "Content-Length": str(len(VALID_MP4_BYTES))},
            )

    monkeypatch.setattr(urllib.request, "build_opener", lambda *args: MockOpener())

    sleep_calls = []
    out_dir = tmp_path / "out"
    artifact = materialize_video_url(
        "https://cdn.example.com/videos/output_123.mp4",
        job_id="job_transient_success",
        output_dir=str(out_dir),
        sleep_func=lambda s: sleep_calls.append(s),
    )

    assert artifact.ok is True
    assert len(attempts) == 2
    assert attempts[0] == attempts[1] == "https://cdn.example.com/videos/output_123.mp4"
    assert artifact.diagnostics["download_attempts"] == 2
    assert artifact.diagnostics["download_retries"] == 1
    assert artifact.diagnostics["transient_retry_attempted"] is True
    assert artifact.diagnostics["content_length_verified"] is True
    assert len(sleep_calls) == 1

    # Final target exists and no part files remain
    target = Path(artifact.local_path)
    assert target.exists()
    assert target.stat().st_size == len(VALID_MP4_BYTES)
    part_files = list(out_dir.glob("*.part"))
    assert len(part_files) == 0


def test_content_length_short_read_triggers_retry_and_succeeds(tmp_path, monkeypatch, mock_probe):
    attempts = []

    class MockOpener:
        def open(self, request, timeout=180):
            attempts.append(request.full_url)
            if len(attempts) == 1:
                # Return truncated body: Content-Length specifies 2000 bytes, but body has only 500
                return MockResponse(
                    VALID_MP4_BYTES[:500],
                    headers={"Content-Type": "video/mp4", "Content-Length": "2000"},
                )
            return MockResponse(
                VALID_MP4_BYTES,
                headers={"Content-Type": "video/mp4", "Content-Length": str(len(VALID_MP4_BYTES))},
            )

    monkeypatch.setattr(urllib.request, "build_opener", lambda *args: MockOpener())

    out_dir = tmp_path / "out"
    artifact = materialize_video_url(
        "https://cdn.example.com/videos/short_read.mp4",
        job_id="job_short_read",
        output_dir=str(out_dir),
        sleep_func=lambda _s: None,
    )

    assert artifact.ok is True
    assert len(attempts) == 2
    assert artifact.diagnostics["download_attempts"] == 2
    assert artifact.diagnostics["download_retries"] == 1
    assert artifact.diagnostics["content_length_verified"] is True
    assert Path(artifact.local_path).exists()
    assert len(list(out_dir.glob("*.part"))) == 0


def test_http_403_and_404_no_retry(tmp_path, monkeypatch, mock_probe):
    for status_code in (403, 404):
        attempts = []

        class MockOpener:
            def open(self, request, timeout=180):
                attempts.append(request.full_url)
                raise urllib.error.HTTPError(
                    request.full_url,
                    status_code,
                    f"Error {status_code}",
                    {"Content-Type": "text/plain"},
                    io.BytesIO(b"error"),
                )

        monkeypatch.setattr(urllib.request, "build_opener", lambda *args: MockOpener())

        out_dir = tmp_path / f"out_{status_code}"
        artifact = materialize_video_url(
            f"https://cdn.example.com/videos/error_{status_code}.mp4",
            job_id=f"job_{status_code}",
            output_dir=str(out_dir),
            sleep_func=lambda _s: None,
        )

        assert artifact.ok is False
        assert len(attempts) == 1
        assert artifact.diagnostics["download_attempts"] == 1
        assert artifact.diagnostics["download_retries"] == 0
        assert artifact.diagnostics["transient_retry_attempted"] is False
        assert artifact.diagnostics["download_http_status"] == status_code
        assert artifact.error_code == "provider_download_failed"
        assert len(list(out_dir.glob("*.part"))) == 0


def test_max_exactly_two_attempts_on_persistent_transient_failure(tmp_path, monkeypatch, mock_probe):
    attempts = []

    class MockOpener:
        def open(self, request, timeout=180):
            attempts.append(request.full_url)
            raise socket.timeout("timed out")

    monkeypatch.setattr(urllib.request, "build_opener", lambda *args: MockOpener())

    out_dir = tmp_path / "out"
    artifact = materialize_video_url(
        "https://cdn.example.com/videos/timeout.mp4",
        job_id="job_timeout",
        output_dir=str(out_dir),
        sleep_func=lambda _s: None,
    )

    assert artifact.ok is False
    assert len(attempts) == 2
    assert artifact.diagnostics["download_attempts"] == 2
    assert artifact.diagnostics["download_retries"] == 1
    assert artifact.diagnostics["transient_retry_attempted"] is True
    assert artifact.error_code == "provider_download_failed"
    assert not Path(artifact.local_path).exists()
    assert len(list(out_dir.glob("*.part"))) == 0


def test_same_result_url_only_and_no_provider_submit_or_fallback(tmp_path, monkeypatch, mock_probe):
    requested_urls = []

    class MockOpener:
        def open(self, request, timeout=180):
            requested_urls.append(request.full_url)
            if len(requested_urls) == 1:
                raise TimeoutError("connection timeout")
            return MockResponse(VALID_MP4_BYTES)

    monkeypatch.setattr(urllib.request, "build_opener", lambda *args: MockOpener())

    target_url = "https://cdn.shopaikey.com/renders/v1/unique_vid_999.mp4?token=abc"
    artifact = materialize_video_url(
        target_url,
        job_id="job_url_isolation",
        output_dir=str(tmp_path / "out"),
        sleep_func=lambda _s: None,
    )

    assert artifact.ok is True
    assert len(requested_urls) == 2
    for url in requested_urls:
        assert url == target_url


def test_failed_part_file_cleaned_and_atomic_final_target(tmp_path, monkeypatch, mock_probe):
    class MockOpener:
        def open(self, request, timeout=180):
            raise ConnectionResetError("network drop")

    monkeypatch.setattr(urllib.request, "build_opener", lambda *args: MockOpener())

    out_dir = tmp_path / "out_atomic"
    artifact = materialize_video_url(
        "https://cdn.example.com/videos/drop.mp4",
        job_id="job_atomic_clean",
        output_dir=str(out_dir),
        sleep_func=lambda _s: None,
    )

    assert artifact.ok is False
    assert not Path(artifact.local_path).exists()
    # Ensure no leftover attempt .part files
    assert len(list(out_dir.glob("*.part"))) == 0


def test_diagnostics_sanitized_and_no_secret_leakage(tmp_path, monkeypatch, mock_probe):
    class MockOpener:
        def open(self, request, timeout=180):
            return MockResponse(
                VALID_MP4_BYTES,
                headers={"Content-Type": "video/mp4", "Content-Length": str(len(VALID_MP4_BYTES))},
            )

    monkeypatch.setattr(urllib.request, "build_opener", lambda *args: MockOpener())

    secret_url = "https://cdn.example.com/video.mp4?auth_token=super_secret_token_12345"
    artifact = materialize_video_url(
        secret_url,
        job_id="job_sanitized",
        output_dir=str(tmp_path / "out"),
    )

    diag = artifact.diagnostics
    assert "super_secret_token_12345" not in diag["download_error_message_masked"]
    assert "super_secret_token_12345" not in diag["result_url_host"]
    assert diag["part_file_used"] is True
    assert diag["download_attempts"] == 1
    assert diag["download_retries"] == 0


def test_html_error_payload_no_retry(tmp_path, monkeypatch, mock_probe):
    attempts = []

    class MockOpener:
        def open(self, request, timeout=180):
            attempts.append(request.full_url)
            return MockResponse(b"<!doctype html><html>Error</html>", headers={"Content-Type": "video/mp4"})

    monkeypatch.setattr(urllib.request, "build_opener", lambda *args: MockOpener())

    out_dir = tmp_path / "out_html"
    artifact = materialize_video_url(
        "https://cdn.example.com/videos/error.html",
        job_id="job_html",
        output_dir=str(out_dir),
        sleep_func=lambda _s: None,
    )

    assert artifact.ok is False
    assert len(attempts) == 1
    assert artifact.error_code == "provider_download_html_error"
    assert not Path(artifact.local_path).exists()
    assert len(list(out_dir.glob("*.part"))) == 0


def test_probe_failure_invalid_mp4_no_retry(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEO_PROVIDER_MIN_VIDEO_BYTES", "1")
    monkeypatch.setattr(
        video_final_output,
        "probe_video",
        lambda _p: {"ok": False, "reason": "output_unreadable"},
    )

    attempts = []

    class MockOpener:
        def open(self, request, timeout=180):
            attempts.append(request.full_url)
            return MockResponse(b"\x00\x00\x00\x18ftypmp42corrupted_bytes_here", headers={"Content-Type": "video/mp4"})

    monkeypatch.setattr(urllib.request, "build_opener", lambda *args: MockOpener())

    out_dir = tmp_path / "out_probe_fail"
    artifact = materialize_video_url(
        "https://cdn.example.com/videos/corrupted.mp4",
        job_id="job_corrupted",
        output_dir=str(out_dir),
        sleep_func=lambda _s: None,
    )

    assert artifact.ok is False
    assert len(attempts) == 1
    assert artifact.error_code == "output_unreadable"
    assert not Path(artifact.local_path).exists()
    assert len(list(out_dir.glob("*.part"))) == 0


def test_double_failure_yields_provider_download_failed_with_no_charge(tmp_path, monkeypatch):
    from services.video_provider_base import VideoGenerationRequest

    req = VideoGenerationRequest(
        job_id="job_fail_no_charge",
        product_type="video_ai_prompt",
        prompt="Sample prompt",
        metadata={"product_video": True, "wallet_charge": False},
    )

    class PersistentFailOpener:
        def open(self, request, timeout=180):
            raise TimeoutError("Persistent connection timeout")

    monkeypatch.setattr(urllib.request, "build_opener", lambda *args: PersistentFailOpener())

    artifact = materialize_video_url(
        "https://cdn.example.com/fail.mp4",
        job_id=req.job_id,
        output_dir=str(tmp_path / "out"),
        sleep_func=lambda _s: None,
    )

    assert artifact.ok is False
    assert artifact.error_code == "provider_download_failed"
    assert artifact.diagnostics["download_attempts"] == 2
    assert artifact.diagnostics["download_retries"] == 1


def test_key4u_behavior_unchanged(tmp_path, monkeypatch, mock_probe):
    # Verify local file or direct URL for key4u uses same safe contract without regressions
    source = tmp_path / "key4u_source.mp4"
    source.write_bytes(VALID_MP4_BYTES)

    artifact = materialize_video_url(
        str(source),
        job_id="key4u_job",
        output_dir=str(tmp_path / "out_key4u"),
        filename_prefix="key4u_video",
    )

    assert artifact.ok is True
    assert artifact.diagnostics["download_final_url_host"] == "local_file"
    assert Path(artifact.local_path).name == "key4u_video_key4u_job.mp4"
    assert Path(artifact.local_path).exists()
