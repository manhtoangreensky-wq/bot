"""Bounded real-media proof for the Video Edit VPS large-media lane.

The fixture is a genuine 65-second MP4 with audio.  A valid trailing MP4
``free`` box raises its transport size above 20 MiB without making FFmpeg
encode hundreds of megabytes of synthetic pixels.  Network/provider/wallet
calls stay replaced by deterministic local transport seams, while the real
file-backed downloader, FFmpeg editor, multipart sender, receipt path, and
cleanup implementation execute unchanged.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import struct
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

import pytest

import local_worker
from services import (
    video_edit_cleanup_audit,
    video_edit_media_transport,
    video_editengine1,
    video_local_editing,
)
from services import video_local_validation as validation


MIB = 1024 * 1024
TOKEN = "123:test-token"
PROXY_SECRET_HEADER = "X-Toanaas-Proxy-Secret"
PROXY_SECRET = "test-proxy-secret"


def _require_tools() -> tuple[str, str]:
    ffmpeg = validation.find_ffmpeg()
    ffprobe = validation.find_ffprobe(ffmpeg_path=ffmpeg)
    if not ffmpeg or not ffprobe:
        pytest.skip("FFmpeg/ffprobe unavailable for Video Edit large-media proof")
    return ffmpeg, ffprobe


def _run(command: list[str], *, timeout: int = 240) -> None:
    completed = subprocess.run(
        command,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]


def _append_free_box(path: Path, target_size: int) -> None:
    current_size = path.stat().st_size
    box_size = int(target_size) - int(current_size)
    assert box_size >= 8
    with path.open("r+b") as handle:
        handle.seek(0, 2)
        handle.write(struct.pack(">I4s", box_size, b"free"))
        handle.seek(box_size - 9, 1)
        handle.write(b"\0")
    assert path.stat().st_size == target_size


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(64 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _full_decode(path: Path, ffmpeg: str) -> None:
    _run(
        [
            ffmpeg,
            "-v",
            "error",
            "-xerror",
            "-i",
            str(path),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-f",
            "null",
            "-",
        ],
        timeout=300,
    )


def test_videoedit_real_65s_21mib_localfile_edit_addons_delivery_and_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ffmpeg, ffprobe = _require_tools()
    source = tmp_path / "large-source.mp4"
    logo = tmp_path / "logo.png"
    subtitle = tmp_path / "subtitle.srt"
    delivered_copy = tmp_path / "delivered-large-media.mp4"

    _run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x203040:s=96x160:r=2:d=65",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=65",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-t",
            "65",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "35",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "24k",
            "-ac",
            "1",
            "-ar",
            "48000",
            "-movflags",
            "+faststart",
            str(source),
        ]
    )
    _append_free_box(source, 21 * MIB)
    _run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=48x24",
            "-frames:v",
            "1",
            "-update",
            "1",
            str(logo),
        ]
    )
    subtitle.write_text(
        (
            "1\n00:00:01,000 --> 00:00:04,000\nTOAN AAS VIDEO EDIT\n\n"
            "2\n00:01:01,000 --> 00:01:04,000\nLARGE MEDIA COMPLETE\n"
        ),
        encoding="utf-8",
    )

    source_probe = validation.probe_video_file(source, ffprobe_path=ffprobe)
    assert source.stat().st_size > 20 * MIB
    assert source_probe["ok"] is True
    assert source_probe["has_audio"] is True
    assert float(source_probe["duration"]) > 60.0
    assert video_edit_media_transport.select_media_lane(
        duration_seconds=float(source_probe["duration"]),
        size_bytes=source.stat().st_size,
    ) == "large_media"
    _full_decode(source, ffmpeg)

    files_by_id = {
        "source-file": source,
        "logo-file": logo,
        "subtitle-file": subtitle,
    }
    files_by_name = {path.name: path for path in files_by_id.values()}
    download_evidence: list[dict] = []
    delivery_evidence: list[dict] = []
    cleanup_evidence: list[dict] = []
    updates: list[dict] = []
    worker_root = tmp_path / "worker-root"
    expected_output_path = (
        worker_root
        / "job_9901"
        / "claim_1"
        / "toan_aas_video_edit_9901.mp4"
    )

    monkeypatch.setattr(local_worker, "TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.setenv("TELEGRAM_API_BASE_URL", "https://tg.toanaas.vn")
    monkeypatch.setenv("TELEGRAM_API_PROXY_SECRET", PROXY_SECRET)
    monkeypatch.setenv(
        "TELEGRAM_API_PROXY_SECRET_HEADER",
        PROXY_SECRET_HEADER,
    )
    monkeypatch.setenv(
        "TELEGRAM_LOCAL_API_FILE_ROOT",
        "/var/lib/telegram-bot-api",
    )
    monkeypatch.setenv("TELEGRAM_LOCAL_API_MEDIA_PATH", "/localfile")
    monkeypatch.setattr(local_worker, "local_ffmpeg_path", lambda: ffmpeg)
    monkeypatch.setattr(
        local_worker,
        "find_ffprobe",
        lambda ffmpeg_path="": ffprobe,
    )
    monkeypatch.setattr(
        local_worker,
        "create_job_workspace",
        lambda job_id: validation.create_job_workspace(job_id, root=worker_root),
    )
    monkeypatch.setattr(
        local_worker.video_local_validation,
        "VIDEO_LOCAL_WORKSPACE_ROOT",
        worker_root,
    )
    monkeypatch.setattr(
        local_worker,
        "telegram_open_no_redirect",
        lambda *_args, **_kwargs: pytest.fail(
            "large-media real fixture must never open a network socket"
        ),
    )

    def fake_get_file_json(*, url, headers, follow_redirects, json):
        assert follow_redirects is False
        assert url.startswith(f"https://tg.toanaas.vn/bot{TOKEN}/getFile")
        assert headers == {PROXY_SECRET_HEADER: PROXY_SECRET}
        file_id = str(json.get("file_id") or "")
        path = files_by_id[file_id]
        return {
            "ok": True,
            "result": {
                "file_path": (
                    f"/var/lib/telegram-bot-api/{TOKEN}/videos/{path.name}"
                ),
                "file_size": path.stat().st_size,
            },
        }

    def fake_stream_bytes(*, url, headers, follow_redirects, chunk_size):
        assert follow_redirects is False
        assert url.startswith(f"https://tg.toanaas.vn/localfile/{TOKEN}/videos/")
        assert headers == {PROXY_SECRET_HEADER: PROXY_SECRET}
        assert 1 <= chunk_size <= video_edit_media_transport.STREAM_CHUNK_BYTES
        path = files_by_name[Path(urlsplit(url).path).name]
        total = 0
        largest = 0
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(chunk_size)
                if not chunk:
                    break
                total += len(chunk)
                largest = max(largest, len(chunk))
                yield chunk
        download_evidence.append(
            {
                "name": path.name,
                "bytes": total,
                "largest_chunk": largest,
            }
        )

    def fake_multipart_request(
        *,
        method_name,
        url,
        headers,
        content_length,
        body,
        follow_redirects,
        **_kwargs,
    ):
        assert follow_redirects is False
        assert url.startswith(f"https://tg.toanaas.vn/bot{TOKEN}/{method_name}")
        assert headers[PROXY_SECRET_HEADER] == PROXY_SECRET
        assert expected_output_path.is_file()
        shutil.copyfile(expected_output_path, delivered_copy)
        streamed = 0
        largest = 0
        for chunk in body:
            streamed += len(chunk)
            largest = max(largest, len(chunk))
        assert streamed == content_length
        delivery_evidence.append(
            {
                "method": method_name,
                "content_length": content_length,
                "largest_chunk": largest,
                "artifact_bytes": expected_output_path.stat().st_size,
            }
        )
        media_field = "video" if method_name == "sendVideo" else "document"
        return {
            "ok": True,
            "result": {
                "message_id": 9901,
                media_field: {"file_id": "video-edit-large-file-9901"},
            },
        }

    def capture_update(
        job_id,
        status,
        error_short="",
        output_url="",
        output_file_id="",
        **_kwargs,
    ) -> dict:
        updates.append(
            {
                "job_id": job_id,
                "status": status,
                "detail": error_short,
                "output_url": output_url,
                "output_file_id": output_file_id,
            }
        )
        return {"ok": True, "job": {"id": job_id}}

    def reconcile_locally(intent: dict) -> dict:
        cleanup = video_edit_cleanup_audit.secure_cleanup_workspace(
            worker_root,
            intent,
        )
        cleanup_evidence.append(cleanup)
        if cleanup.get("ok") is True:
            video_edit_cleanup_audit.remove_active_intent(worker_root, intent)
        return cleanup

    monkeypatch.setattr(local_worker, "_video_edit_get_file_json", fake_get_file_json)
    monkeypatch.setattr(local_worker, "_video_edit_stream_bytes", fake_stream_bytes)
    monkeypatch.setattr(
        local_worker,
        "_video_edit_multipart_request",
        fake_multipart_request,
    )
    monkeypatch.setattr(local_worker, "update_job", capture_update)
    monkeypatch.setattr(
        local_worker,
        "reconcile_video_edit_cleanup_intent",
        reconcile_locally,
    )

    plan = video_local_editing.default_manual_edit_plan("")
    plan.update(
        {
            "trim": {"start_ms": 0, "end_ms": 65_000},
            "brightness_percent": 115,
            "volume": 0.8,
            "audio_normalization": "loudnorm",
            "logo_overlay": {
                "position": "top_right",
                "scale": 0.12,
                "opacity": 0.75,
            },
            "text_overlay": {
                "content": "TOAN AAS",
                "position": "bottom",
                "start_ms": 0,
                "end_ms": 65_000,
                "font_size": 18,
                "outline": 1,
            },
            "subtitle_file": "telegram-subtitle-placeholder.srt",
        }
    )
    source_sha256 = _sha256(source)
    payload = {
        "local1_contract": 1,
        "product_type": video_editengine1.PRODUCT_TYPE,
        "engine_route": video_editengine1.ENGINE_ROUTE,
        "worker_owner": video_editengine1.OUTBOX_OWNER,
        "worker_capability": video_editengine1.WORKER_CAPABILITY,
        "source_file_id": "source-file",
        "source_file_name": source.name,
        "source_file_size": source.stat().st_size,
        "source_sha256": source_sha256,
        "source_metadata": {
            **source_probe,
            "bytes": source.stat().st_size,
            "sha256": source_sha256,
        },
        "user_id": "701",
        "chat_id": "88",
        "media_lane": "large_media",
        "local1_mode": "manual",
        "price_xu": 0,
        "quoted_price_xu": 0,
        "quality_tier_id": "local-free",
        "charge_policy": "free_local_tool",
        "provider_call": False,
        "plan_schema_version": "video-edit-plan-v1",
        "state_revision": 3,
        "manual_edit_plan": plan,
        "logo_source": {
            "file_id": "logo-file",
            "file_name": logo.name,
            "file_size": logo.stat().st_size,
        },
        "subtitle_source": {
            "file_id": "subtitle-file",
            "file_name": subtitle.name,
            "file_size": subtitle.stat().st_size,
        },
        "rights_confirmation": {
            "confirmed": True,
            "policy": "video_edit_rights_v1",
            "user_id": "701",
            "review_revision": 3,
            "confirmed_at_unix": 1_750_000_000,
        },
        "max_render_seconds": 240,
    }

    local_worker.run_video_local_edit(
        {
            "id": 9901,
            "claim_attempt": 1,
            "job_type": video_editengine1.WORKER_JOB_TYPE,
            "user_id": "701",
            "input_file_id": json.dumps(payload),
        }
    )

    terminal = updates[-1]
    detail = json.loads(terminal["detail"])
    assert terminal["output_url"], terminal
    receipt = json.loads(terminal["output_url"])
    output_probe = validation.probe_video_file(delivered_copy, ffprobe_path=ffprobe)
    _full_decode(delivered_copy, ffmpeg)

    assert terminal["status"] == "succeeded"
    assert terminal["output_file_id"] == "video-edit-large-file-9901"
    assert detail["stage"] == "delivered"
    assert detail["media_lane"] == "large_media"
    assert detail["charge_status"] == "not_required_free"
    assert detail["charged_xu"] == 0
    assert detail["cleanup_intent"]["persisted"] is True
    assert receipt["media_lane"] == "large_media"
    assert receipt["delivery_message_id"] == "9901"
    assert receipt["delivery_file_id"] == "video-edit-large-file-9901"
    assert receipt["source_sha256"] == source_sha256
    assert receipt["output_sha256"] == _sha256(delivered_copy)
    assert output_probe["ok"] is True
    assert output_probe["has_audio"] is True
    assert output_probe["audio_stream_count"] == 1
    assert output_probe["video_codec"] == "h264"
    assert abs(float(output_probe["duration"]) - 65.0) <= 1.0
    assert [item["name"] for item in download_evidence] == [
        source.name,
        logo.name,
        subtitle.name,
    ]
    assert download_evidence[0]["bytes"] == 21 * MIB
    assert max(item["largest_chunk"] for item in download_evidence) <= (
        video_edit_media_transport.STREAM_CHUNK_BYTES
    )
    assert len(delivery_evidence) == 1
    assert delivery_evidence[0]["method"] == (
        "sendDocument"
        if delivered_copy.stat().st_size
        > video_edit_media_transport.SHORT_MEDIA_MAX_BYTES
        else "sendVideo"
    )
    assert delivery_evidence[0]["largest_chunk"] <= (
        video_edit_media_transport.STREAM_CHUNK_BYTES
    )
    assert cleanup_evidence and cleanup_evidence[-1]["ok"] is True
    assert not (worker_root / "job_9901").exists()
    print(
        "VIDEO_EDIT_LARGE_REAL_EVIDENCE="
        + json.dumps(
            {
                "source_bytes": source.stat().st_size,
                "source_duration": float(source_probe["duration"]),
                "source_sha256": source_sha256,
                "output_bytes": delivered_copy.stat().st_size,
                "output_duration": float(output_probe["duration"]),
                "output_sha256": _sha256(delivered_copy),
                "delivery_method": delivery_evidence[0]["method"],
                "max_download_chunk": max(
                    item["largest_chunk"] for item in download_evidence
                ),
                "max_upload_chunk": delivery_evidence[0]["largest_chunk"],
                "cleanup": cleanup_evidence[-1]["outcome"],
            },
            sort_keys=True,
        )
    )
