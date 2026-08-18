"""Unit tests for the dependency-injected public Gemini chat adapter.

These tests deliberately use no Google credentials, environment variables, or
network client.  The fake client records the complete request so the adapter's
model and capability contract remains explicit.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import threading
from types import SimpleNamespace

import pytest

import providers.gemini_public_chat_provider as gemini_module
from providers.gemini_public_chat_provider import (
    GEMINI_FREE_MODEL,
    generate_public_chat_text,
)


class FakeResponse:
    def __init__(self, text: str = "answer") -> None:
        self.text = text


class FakeModels:
    def __init__(self, response: object | None = None, error: Exception | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self.response = response if response is not None else FakeResponse()
        self.error = error

    def generate_content(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


class FakeFiles:
    def __init__(self) -> None:
        self.uploaded: list[Path] = []
        self.deleted: list[str] = []
        self.fail_delete = False
        self.fail_upload_at = 0
        self.states: list[str] = ["ACTIVE"]
        self.get_calls: list[str] = []

    def upload(self, *, file: Path) -> object:
        self.uploaded.append(Path(file))
        if self.fail_upload_at and len(self.uploaded) == self.fail_upload_at:
            raise RuntimeError("upload failed with secret-token")
        index = len(self.uploaded)
        return SimpleNamespace(
            uri=f"gemini://temporary-file-{index}",
            name=f"files/temporary-file-{index}",
            state=SimpleNamespace(name=self.states[0]),
        )

    def get(self, *, name: str) -> object:
        self.get_calls.append(name)
        state = self.states[min(len(self.get_calls), len(self.states) - 1)]
        return SimpleNamespace(
            uri="gemini://temporary-file-1",
            name=name,
            state=SimpleNamespace(name=state),
        )

    def delete(self, *, name: str) -> None:
        self.deleted.append(name)
        if self.fail_delete:
            raise RuntimeError("signed-url=secret")


class FakeClient:
    def __init__(self, *, response: object | None = None, error: Exception | None = None) -> None:
        self.models = FakeModels(response=response, error=error)
        self.files = FakeFiles()


def _attachment(tmp_path: Path, kind: str, mime_type: str, name: str, data: bytes) -> object:
    path = tmp_path / name
    path.write_bytes(data)
    return SimpleNamespace(
        kind=kind,
        mime_type=mime_type,
        file_name=name,
        actual_bytes=len(data),
        temporary_path=path,
    )


def _role(item: object) -> str:
    return str(item.get("role")) if isinstance(item, dict) else str(getattr(item, "role"))


def _parts(item: object) -> list[object]:
    return list(item.get("parts", [])) if isinstance(item, dict) else list(getattr(item, "parts"))


def test_pins_free_model_and_preserves_bounded_chronological_context() -> None:
    client = FakeClient()
    messages = [{"role": "user" if index % 2 == 0 else "assistant", "content": f"m{index}"} for index in range(31)]

    result = asyncio.run(
        generate_public_chat_text(
            client,
            system_prompt="Reply in Vietnamese.",
            messages=messages,
        )
    )

    assert result == {"ok": True, "status": "ok", "text": "answer", "model": GEMINI_FREE_MODEL}
    assert len(client.models.calls) == 1
    request = client.models.calls[0]
    assert request["model"] == "gemini-3.7-flash"
    assert "Reply in Vietnamese." in str(request["config"])
    contents = list(request["contents"])
    assert len(contents) == 23
    assert [_role(item) for item in contents] == ["user", "model"] * 11 + ["user"]
    assert "m8" in str(_parts(contents[0]))
    assert "m30" in str(_parts(contents[-1]))


def test_rejects_history_that_does_not_end_with_current_user_turn() -> None:
    client = FakeClient()

    result = asyncio.run(
        generate_public_chat_text(
            client,
            system_prompt="system",
            messages=[
                {"role": "user", "content": "question"},
                {"role": "assistant", "content": "old answer"},
            ],
        )
    )

    assert result["status"] == "invalid_input"
    assert client.models.calls == []


@pytest.mark.parametrize(
    ("kind", "mime_type", "name", "data"),
    [
        ("image", "image/png", "photo.png", b"\x89PNG\r\n\x1a\nsmall"),
        ("audio", "audio/mpeg", "voice.mp3", b"ID3small"),
        ("audio", "audio/mp4", "voice.m4a", b"\x00\x00\x00\x18ftypM4A small"),
        ("video", "video/mp4", "clip.mp4", b"\x00\x00\x00\x18ftypmp42small"),
        ("video", "video/quicktime", "clip.mov", b"\x00\x00\x00\x14ftypqt  small"),
        ("pdf", "application/pdf", "brief.pdf", b"%PDF-1.7\nsmall"),
    ],
)
def test_passes_each_supported_small_attachment_to_single_free_model(
    tmp_path: Path, kind: str, mime_type: str, name: str, data: bytes
) -> None:
    client = FakeClient()
    attachment = _attachment(tmp_path, kind, mime_type, name, data)

    result = asyncio.run(
        generate_public_chat_text(
            client,
            system_prompt="system",
            messages=[{"role": "user", "content": "analyse this"}],
            attachments=[attachment],
        )
    )

    assert result["ok"] is True
    assert result["model"] == GEMINI_FREE_MODEL
    request = client.models.calls[0]
    assert request["model"] == GEMINI_FREE_MODEL
    assert "small" in str(request["contents"])
    assert client.files.uploaded == []
    assert client.files.deleted == []


def test_large_attachment_uses_request_scoped_file_and_deletes_it(tmp_path: Path) -> None:
    client = FakeClient()
    attachment = _attachment(tmp_path, "pdf", "application/pdf", "large.pdf", b"%PDF-" + b"a" * (8 * 1024 * 1024))

    result = asyncio.run(
        generate_public_chat_text(
            client,
            system_prompt="system",
            messages=[{"role": "user", "content": "summarise"}],
            attachments=[attachment],
        )
    )

    assert result["ok"] is True
    assert client.files.uploaded == [attachment.temporary_path]
    assert client.files.deleted == ["files/temporary-file-1"]
    assert "gemini://temporary-file-1" in str(client.models.calls[0]["contents"])


def test_large_video_waits_until_files_api_is_active(tmp_path: Path) -> None:
    client = FakeClient()
    client.files.states = ["PROCESSING", "PROCESSING", "ACTIVE"]
    attachment = _attachment(
        tmp_path,
        "video",
        "video/mp4",
        "large.mp4",
        b"\x00\x00\x00\x18ftypmp42" + b"v" * (8 * 1024 * 1024),
    )

    result = asyncio.run(
        generate_public_chat_text(
            client,
            system_prompt="system",
            messages=[{"role": "user", "content": "analyse"}],
            attachments=[attachment],
        )
    )

    assert result["ok"] is True
    assert client.files.get_calls == ["files/temporary-file-1", "files/temporary-file-1"]
    assert len(client.models.calls) == 1
    assert client.files.deleted == ["files/temporary-file-1"]


def test_large_video_with_missing_upload_state_polls_until_active(tmp_path: Path) -> None:
    client = FakeClient()
    client.files.states = ["", "ACTIVE"]
    attachment = _attachment(
        tmp_path,
        "video",
        "video/mp4",
        "large-no-state.mp4",
        b"\x00\x00\x00\x18ftypmp42" + b"v" * (8 * 1024 * 1024),
    )

    result = asyncio.run(
        generate_public_chat_text(
            client,
            system_prompt="system",
            messages=[{"role": "user", "content": "analyse"}],
            attachments=[attachment],
        )
    )

    assert result["ok"] is True
    assert client.files.get_calls == ["files/temporary-file-1"]
    assert len(client.models.calls) == 1
    assert client.files.deleted == ["files/temporary-file-1"]


def test_validates_all_attachments_before_uploading_any(tmp_path: Path) -> None:
    client = FakeClient()
    large = _attachment(
        tmp_path, "pdf", "application/pdf", "large.pdf", b"%PDF-" + b"a" * (8 * 1024 * 1024)
    )
    invalid = SimpleNamespace(
        kind="image", mime_type="image/gif", actual_bytes=4, temporary_path=tmp_path / "missing.gif"
    )

    result = asyncio.run(
        generate_public_chat_text(
            client,
            system_prompt="system",
            messages=[{"role": "user", "content": "analyse"}],
            attachments=[large, invalid],
        )
    )

    assert result["status"] == "invalid_input"
    assert client.files.uploaded == []
    assert client.models.calls == []


def test_partial_upload_failure_deletes_already_uploaded_file(tmp_path: Path) -> None:
    client = FakeClient()
    client.files.fail_upload_at = 2
    attachments = [
        _attachment(tmp_path, "pdf", "application/pdf", f"large-{index}.pdf", b"%PDF-" + bytes([96 + index]) * (8 * 1024 * 1024))
        for index in (1, 2)
    ]

    result = asyncio.run(
        generate_public_chat_text(
            client,
            system_prompt="system",
            messages=[{"role": "user", "content": "analyse"}],
            attachments=attachments,
        )
    )

    assert result["status"] == "provider_error"
    assert client.files.deleted == ["files/temporary-file-1"]
    assert client.models.calls == []


def test_cancellation_still_deletes_uploaded_file(tmp_path: Path) -> None:
    client = FakeClient(error=asyncio.CancelledError())
    attachment = _attachment(
        tmp_path, "pdf", "application/pdf", "large.pdf", b"%PDF-" + b"a" * (8 * 1024 * 1024)
    )

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            generate_public_chat_text(
                client,
                system_prompt="system",
                messages=[{"role": "user", "content": "analyse"}],
                attachments=[attachment],
            )
        )

    assert client.files.deleted == ["files/temporary-file-1"]


def test_cancellation_during_sync_upload_cleans_late_provider_file(tmp_path: Path) -> None:
    class SlowUploadFiles(FakeFiles):
        def __init__(self) -> None:
            super().__init__()
            self.started = threading.Event()
            self.release = threading.Event()

        def upload(self, *, file: Path) -> object:
            self.uploaded.append(Path(file))
            self.started.set()
            if not self.release.wait(timeout=2.0):
                raise RuntimeError("test upload release timeout")
            return SimpleNamespace(
                uri="gemini://late-file",
                name="files/late-file",
                state=SimpleNamespace(name="ACTIVE"),
            )

    client = FakeClient()
    client.files = SlowUploadFiles()
    attachment = _attachment(
        tmp_path, "pdf", "application/pdf", "large.pdf", b"%PDF-" + b"a" * (8 * 1024 * 1024)
    )

    async def run() -> None:
        task = asyncio.create_task(
            generate_public_chat_text(
                client,
                system_prompt="system",
                messages=[{"role": "user", "content": "summarise"}],
                attachments=[attachment],
            )
        )
        deadline = asyncio.get_running_loop().time() + 1.0
        while not client.files.started.is_set() and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.001)
        assert client.files.started.is_set()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        client.files.release.set()
        deadline = asyncio.get_running_loop().time() + 1.0
        while not client.files.deleted and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.001)

    asyncio.run(run())

    assert client.files.deleted == ["files/late-file"]


@pytest.mark.parametrize(
    ("attachment", "expected_status"),
    [
        (SimpleNamespace(kind="image", mime_type="image/gif", actual_bytes=4, temporary_path=Path("missing.gif")), "invalid_input"),
        (SimpleNamespace(kind="unknown", mime_type="image/png", actual_bytes=4, temporary_path=Path("missing.png")), "invalid_input"),
    ],
)
def test_rejects_invalid_attachment_without_a_provider_call(attachment: object, expected_status: str) -> None:
    client = FakeClient()

    result = asyncio.run(
        generate_public_chat_text(
            client,
            system_prompt="system",
            messages=[{"role": "user", "content": "hello"}],
            attachments=[attachment],
        )
    )

    assert result == {"ok": False, "status": expected_status, "text": "", "model": GEMINI_FREE_MODEL}
    assert client.models.calls == []


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (RuntimeError("429 RESOURCE_EXHAUSTED"), "rate_limited"),
        (TimeoutError("network timeout"), "timeout"),
        (RuntimeError("Bearer secret-token signed-url=https://host/?X-Amz-Signature=secret"), "provider_error"),
    ],
)
def test_normalizes_provider_errors_without_exposing_raw_exception(error: Exception, expected_status: str) -> None:
    client = FakeClient(error=error)

    result = asyncio.run(
        generate_public_chat_text(
            client,
            system_prompt="system",
            messages=[{"role": "user", "content": "hello"}],
        )
    )

    assert result == {"ok": False, "status": expected_status, "text": "", "model": GEMINI_FREE_MODEL}
    assert "secret" not in str(result)
    assert "host" not in str(result)


def test_missing_client_empty_response_and_invalid_role_fail_closed() -> None:
    no_client = asyncio.run(
        generate_public_chat_text(None, system_prompt="system", messages=[{"role": "user", "content": "hello"}])
    )
    empty = asyncio.run(
        generate_public_chat_text(FakeClient(response=FakeResponse("  ")), system_prompt="system", messages=[{"role": "user", "content": "hello"}])
    )
    invalid_role = asyncio.run(
        generate_public_chat_text(FakeClient(), system_prompt="system", messages=[{"role": "system", "content": "hello"}])
    )

    assert no_client["status"] == "unavailable"
    assert empty["status"] == "empty_response"
    assert invalid_role["status"] == "invalid_input"


def test_adapter_has_no_paid_fallback_or_external_configuration_surface() -> None:
    public_names = set(gemini_module.__all__)
    assert public_names == {"GEMINI_FREE_MODEL", "generate_public_chat_text"}
    assert not any("fallback" in name.lower() or "key4u" in name.lower() for name in dir(gemini_module))


@pytest.mark.parametrize("payload", [{"answer": "not text"}, ["not", "text"]])
def test_non_string_provider_output_fails_closed(payload: object) -> None:
    client = FakeClient(response=SimpleNamespace(text=payload))

    result = asyncio.run(
        generate_public_chat_text(
            client,
            system_prompt="system",
            messages=[{"role": "user", "content": "hello"}],
        )
    )

    assert result == {"ok": False, "status": "empty_response", "text": "", "model": GEMINI_FREE_MODEL}


def test_sync_sdk_methods_run_outside_the_event_loop(tmp_path: Path) -> None:
    caller_thread = threading.get_ident()
    call_threads: dict[str, list[int]] = {name: [] for name in ("upload", "get", "generate", "delete")}

    class RecordingModels:
        def generate_content(self, **_kwargs: object) -> object:
            call_threads["generate"].append(threading.get_ident())
            return FakeResponse("answer")

    class RecordingFiles:
        def upload(self, *, file: Path) -> object:
            call_threads["upload"].append(threading.get_ident())
            return SimpleNamespace(uri="gemini://video", name="files/video", state=SimpleNamespace(name="PROCESSING"))

        def get(self, *, name: str) -> object:
            call_threads["get"].append(threading.get_ident())
            return SimpleNamespace(uri="gemini://video", name=name, state=SimpleNamespace(name="ACTIVE"))

        def delete(self, *, name: str) -> None:
            call_threads["delete"].append(threading.get_ident())

    client = SimpleNamespace(models=RecordingModels(), files=RecordingFiles())
    attachment = _attachment(
        tmp_path,
        "video",
        "video/mp4",
        "large.mp4",
        b"\x00\x00\x00\x18ftypmp42" + b"v" * (8 * 1024 * 1024),
    )

    result = asyncio.run(
        generate_public_chat_text(
            client,
            system_prompt="system",
            messages=[{"role": "user", "content": "analyse"}],
            attachments=[attachment],
        )
    )

    assert result["ok"] is True
    assert all(call_threads.values())
    assert all(thread_id != caller_thread for thread_ids in call_threads.values() for thread_id in thread_ids)


def test_generate_call_has_bounded_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    class HangingModels:
        async def generate_content(self, **_kwargs: object) -> object:
            await asyncio.Event().wait()

    client = SimpleNamespace(models=HangingModels(), files=FakeFiles())
    monkeypatch.setattr(gemini_module, "_GENERATE_TIMEOUT_SECONDS", 0.01, raising=False)

    async def run() -> dict[str, object]:
        return await asyncio.wait_for(
            generate_public_chat_text(
                client,
                system_prompt="system",
                messages=[{"role": "user", "content": "hello"}],
            ),
            timeout=0.25,
        )

    result = asyncio.run(run())
    assert result["status"] == "timeout"


def test_upload_call_has_bounded_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class HangingFiles(FakeFiles):
        async def upload(self, *, file: Path) -> object:
            await asyncio.Event().wait()

    client = FakeClient()
    client.files = HangingFiles()
    attachment = _attachment(
        tmp_path, "pdf", "application/pdf", "large.pdf", b"%PDF-" + b"a" * (8 * 1024 * 1024)
    )
    monkeypatch.setattr(gemini_module, "_FILE_UPLOAD_TIMEOUT_SECONDS", 0.01, raising=False)

    async def run() -> dict[str, object]:
        return await asyncio.wait_for(
            generate_public_chat_text(
                client,
                system_prompt="system",
                messages=[{"role": "user", "content": "summarise"}],
                attachments=[attachment],
            ),
            timeout=0.25,
        )

    result = asyncio.run(run())
    assert result["status"] == "timeout"
    assert client.models.calls == []


def test_get_call_has_bounded_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class HangingGetFiles(FakeFiles):
        async def get(self, *, name: str) -> object:
            await asyncio.Event().wait()

    client = FakeClient()
    client.files = HangingGetFiles()
    client.files.states = ["PROCESSING"]
    attachment = _attachment(
        tmp_path,
        "video",
        "video/mp4",
        "large.mp4",
        b"\x00\x00\x00\x18ftypmp42" + b"v" * (8 * 1024 * 1024),
    )
    monkeypatch.setattr(gemini_module, "_FILE_GET_TIMEOUT_SECONDS", 0.01, raising=False)

    async def run() -> dict[str, object]:
        return await asyncio.wait_for(
            generate_public_chat_text(
                client,
                system_prompt="system",
                messages=[{"role": "user", "content": "analyse"}],
                attachments=[attachment],
            ),
            timeout=0.25,
        )

    result = asyncio.run(run())
    assert result["status"] == "timeout"
    assert client.files.deleted == ["files/temporary-file-1"]
    assert client.models.calls == []


def test_video_processing_has_total_deadline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    client.files.states = ["PROCESSING"]
    attachment = _attachment(
        tmp_path,
        "video",
        "video/mp4",
        "large.mp4",
        b"\x00\x00\x00\x18ftypmp42" + b"v" * (8 * 1024 * 1024),
    )
    monkeypatch.setattr(gemini_module, "_VIDEO_PROCESSING_DEADLINE_SECONDS", 0.01, raising=False)

    async def run() -> dict[str, object]:
        return await asyncio.wait_for(
            generate_public_chat_text(
                client,
                system_prompt="system",
                messages=[{"role": "user", "content": "analyse"}],
                attachments=[attachment],
            ),
            timeout=0.25,
        )

    result = asyncio.run(run())
    assert result["status"] == "timeout"
    assert client.files.deleted == ["files/temporary-file-1"]
    assert client.models.calls == []


def test_delete_call_has_bounded_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class HangingDeleteFiles(FakeFiles):
        async def delete(self, *, name: str) -> None:
            self.deleted.append(name)
            await asyncio.Event().wait()

    client = FakeClient()
    client.files = HangingDeleteFiles()
    attachment = _attachment(
        tmp_path, "pdf", "application/pdf", "large.pdf", b"%PDF-" + b"a" * (8 * 1024 * 1024)
    )
    monkeypatch.setattr(gemini_module, "_FILE_DELETE_TIMEOUT_SECONDS", 0.01, raising=False)

    async def run() -> dict[str, object]:
        return await asyncio.wait_for(
            generate_public_chat_text(
                client,
                system_prompt="system",
                messages=[{"role": "user", "content": "summarise"}],
                attachments=[attachment],
            ),
            timeout=0.25,
        )

    result = asyncio.run(run())
    assert result["ok"] is True
    assert client.files.deleted == ["files/temporary-file-1"]
