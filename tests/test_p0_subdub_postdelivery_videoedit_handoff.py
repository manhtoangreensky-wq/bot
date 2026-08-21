from __future__ import annotations

import asyncio
import hashlib
import inspect
from copy import deepcopy
from types import SimpleNamespace

import pytest

import bot


class _DeliveredMessage:
    def __init__(self, message_id: int, file_id: str, method: str = "video") -> None:
        self.message_id = message_id
        setattr(self, method, SimpleNamespace(file_id=file_id))


class _DeliveryTarget:
    def __init__(self) -> None:
        self.videos: list[dict] = []

    async def reply_video(self, **kwargs):
        self.videos.append(kwargs)
        return _DeliveredMessage(9101, "subdub-delivered-file-9101")


class _CallbackMessage:
    def __init__(self, chat_id: int) -> None:
        self.chat_id = chat_id
        self.message_id = 9201
        self.replies: list[tuple[str, dict]] = []

    async def reply_text(self, text: str, **kwargs):
        self.replies.append((text, kwargs))
        return SimpleNamespace(message_id=self.message_id + 1)


class _CallbackQuery:
    def __init__(self, user_id: int, data: str) -> None:
        self.from_user = SimpleNamespace(id=user_id, first_name="SubDub")
        self.data = data
        self.message = _CallbackMessage(user_id)
        self.edits: list[tuple[str, dict]] = []
        self.answers: list[tuple[tuple, dict]] = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))

    async def edit_message_text(self, text: str, **kwargs):
        self.edits.append((text, kwargs))
        return SimpleNamespace(message_id=self.message.message_id)


def _button_rows(markup) -> list[list[tuple[str, str]]]:
    return [
        [(button.text, button.callback_data) for button in row]
        for row in markup.inline_keyboard
    ]


def _delivered_job(user_id: int = 81001) -> dict:
    payload = b"\x00\x00\x00\x18ftypmp42" + (b"v" * 4096)
    duration = 61.25
    return {
        "job_key": f"{user_id}|{user_id}|source-81001|create_subtitle",
        "job_id": "subdub-job-81001",
        "user_id": user_id,
        "chat_id": user_id,
        "mode": bot.VIDEO_SUBTITLE_MODE_CREATE,
        "status": "completed",
        "terminal_state": "delivered",
        "terminal_artifact_type": "video",
        "final_mp4_delivered": True,
        "final_mp4_validated": True,
        "duration_coverage_ok": True,
        "video_delivery_message_id": "9101",
        "video_delivery_file_id": "subdub-delivered-file-9101",
        "video_delivery_size_bytes": len(payload),
        "video_delivery_sha256": hashlib.sha256(payload).hexdigest(),
        "video_delivery_filename": "toan_aas_subtitle_video.mp4",
        "final_mp4_duration": duration,
        "output_validation": {
            "ok": True,
            "actual_duration": duration,
            "duration": duration,
            "duration_coverage_ok": True,
            "has_video": True,
            "has_audio": True,
            "width": 1080,
            "height": 1920,
            "display_width": 1080,
            "display_height": 1920,
            "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
            "video_codec": "h264",
        },
    }


@pytest.fixture(autouse=True)
def _isolated_state(monkeypatch):
    monkeypatch.setenv("VIDEO_EDITOR_DURABLE_STATE_DISABLED", "1")
    bot.SUBTITLE_DUB_PIPELINE_JOBS.clear()
    for user_id in (81001, 81002):
        bot.USER_PENDING.pop(bot.video_editor_pending_key(user_id), None)
        bot.clear_video_session(user_id)
    yield
    bot.SUBTITLE_DUB_PIPELINE_JOBS.clear()
    for user_id in (81001, 81002):
        bot.USER_PENDING.pop(bot.video_editor_pending_key(user_id), None)
        bot.clear_video_session(user_id)


def test_delivery_persists_the_exact_telegram_mp4_identity(monkeypatch) -> None:
    key = "81001|81001|source-81001|create_subtitle"
    acquired, _job = bot.acquire_subtitle_dub_pipeline_job(
        key,
        user_id=81001,
        chat_id=81001,
        mode=bot.VIDEO_SUBTITLE_MODE_CREATE,
    )
    assert acquired is True
    payload = b"\x00\x00\x00\x18ftypmp42" + (b"p" * 4096)

    async def valid_output(_payload, **_kwargs):
        return {
            "ok": True,
            "detail": "ok",
            "actual_duration": 61.25,
            "duration": 61.25,
            "duration_coverage_ok": True,
            "duration_coverage_ratio": 1.0,
            "has_video": True,
            "has_audio": True,
            "width": 1080,
            "height": 1920,
        }

    monkeypatch.setattr(bot, "subdub_validate_video_output", valid_output)
    sent = asyncio.run(
        bot.send_public_subtitle_dub_final_outputs(
            _DeliveryTarget(),
            mode=bot.VIDEO_SUBTITLE_MODE_CREATE,
            video_bytes=payload,
            strict_validation=True,
            expected_duration_seconds=61.25,
            include_subtitle_outputs=False,
            job_key=key,
        )
    )

    stored = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]
    expected_sha = hashlib.sha256(payload).hexdigest()
    assert sent["video_delivery_file_id"] == "subdub-delivered-file-9101"
    assert sent["video_delivery_size_bytes"] == len(payload)
    assert sent["video_delivery_sha256"] == expected_sha
    assert stored["video_delivery_file_id"] == "subdub-delivered-file-9101"
    assert stored["video_delivery_size_bytes"] == len(payload)
    assert stored["video_delivery_sha256"] == expected_sha


@pytest.mark.parametrize(
    "mode",
    [
        bot.VIDEO_SUBTITLE_MODE_CREATE,
        bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        bot.VIDEO_SUBTITLE_MODE_DUB,
        bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
    ],
)
def test_receipt_shows_two_balanced_handoff_buttons_only_with_complete_artifact(
    mode: str,
) -> None:
    job = _delivered_job()
    job["mode"] = mode
    rows = _button_rows(bot.video_dubbing_receipt_keyboard("vi", "translation", job))
    handoff_rows = [row for row in rows if any("Chỉnh sửa video" in label for label, _ in row)]

    assert len(handoff_rows) == 1
    assert [label for label, _callback in handoff_rows[0]] == [
        "🛠 Chỉnh sửa video",
        "🏷 Logo / Watermark",
    ]
    assert all(len(row) <= 2 for row in rows)

    incomplete = deepcopy(job)
    incomplete.pop("video_delivery_file_id")
    incomplete_labels = {
        label
        for row in _button_rows(
            bot.video_dubbing_receipt_keyboard("vi", "translation", incomplete)
        )
        for label, _callback in row
    }
    assert "🛠 Chỉnh sửa video" not in incomplete_labels
    assert "🏷 Logo / Watermark" not in incomplete_labels


def test_dub_receipt_uses_exact_three_row_postdelivery_actions() -> None:
    job = _delivered_job()
    job.update({
        "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "final_video_available": "1",
        "final_audio_available": "1",
    })
    token = bot.subdub_postdelivery_video_edit_artifact(
        job,
        user_id=job["user_id"],
    )["token"]

    rows = _button_rows(
        bot.video_dubbing_receipt_keyboard("vi", "video_addon", job)
    )

    assert rows == [
        [
            ("📹 Tải video lồng tiếng", "videodub|download_final_video"),
        ],
        [
            ("🛠 Chỉnh sửa video", f"videodub|edit|{token}"),
            ("🏷 Logo / Watermark", f"videodub|branding|{token}"),
        ],
        [
            ("🎞 Phụ đề / Lồng tiếng", "videodub|status_back_type"),
            ("🏠 Menu chính", "menu|main"),
        ],
    ]
    assert "videodub|redub_voice" not in {
        callback for row in rows for _label, callback in row
    }


def test_pipeline_result_and_registry_keep_exact_delivery_identity() -> None:
    core_source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)
    wrapper_source = inspect.getsource(bot.execute_video_dubbing_pipeline)
    expected_fields = {
        "video_delivery_file_id": "str(delivery.get",
        "video_delivery_size_bytes": "int(delivery.get",
        "video_delivery_sha256": "str(delivery.get",
        "video_delivery_filename": "str(delivery.get",
        "video_delivery_mime_type": "str(delivery.get",
        "video_delivery_duration_seconds": "float(delivery.get",
    }

    for field, core_value in expected_fields.items():
        assert f'"{field}": {core_value}' in core_source
        assert f'"{field}": ' in wrapper_source
        assert f'result.get("{field}")' in wrapper_source


def test_handoff_state_uses_exact_delivered_file_without_upload_or_latest_fallback() -> None:
    job = _delivered_job()
    artifact = bot.subdub_postdelivery_video_edit_artifact(job, user_id=81001)
    workspace = bot.subdub_postdelivery_video_edit_state(artifact, target="edit")
    branding = bot.subdub_postdelivery_video_edit_state(artifact, target="branding")

    for state in (workspace, branding):
        assert state["source_file_id"] == "subdub-delivered-file-9101"
        assert state["source_video_hash"] == job["video_delivery_sha256"]
        assert state["source_file_size"] == job["video_delivery_size_bytes"]
        assert state["inspection_complete"] is True
        assert state["awaiting_media"] is False
        assert state["price_xu"] == 0
        assert state["provider_call"] is False
        assert bot.video_edit_submit_inspection_evidence(state)["ok"] is True
    assert workspace["current_screen"] == "workspace"
    assert branding["current_screen"] == "branding"


def test_stale_token_and_wrong_owner_fail_closed_without_another_artifact() -> None:
    job = _delivered_job()
    bot.SUBTITLE_DUB_PIPELINE_JOBS[job["job_key"]] = deepcopy(job)
    artifact = bot.subdub_postdelivery_video_edit_artifact(job, user_id=81001)

    assert bot.subdub_resolve_postdelivery_video_edit_artifact(
        artifact["token"], user_id=81002
    ) == {}

    bot.SUBTITLE_DUB_PIPELINE_JOBS[job["job_key"]][
        "video_delivery_file_id"
    ] = "different-delivered-file"
    assert bot.subdub_resolve_postdelivery_video_edit_artifact(
        artifact["token"], user_id=81001
    ) == {}


def test_receipt_callbacks_open_canonical_workspace_or_branding_with_source_attached() -> None:
    user_id = 81001
    job = _delivered_job(user_id)
    bot.SUBTITLE_DUB_PIPELINE_JOBS[job["job_key"]] = deepcopy(job)
    artifact = bot.subdub_postdelivery_video_edit_artifact(job, user_id=user_id)
    context = SimpleNamespace(user_data={})

    branding_query = _CallbackQuery(
        user_id,
        f"videodub|branding|{artifact['token']}",
    )
    asyncio.run(
        bot.handle_video_dubbing_callback(
            SimpleNamespace(callback_query=branding_query),
            context,
        )
    )
    branding_state = bot.get_video_editor_pending(user_id)
    session_id = branding_state["edit_session_id"]
    assert branding_state["current_screen"] == "branding"
    assert branding_state["source_file_id"] == job["video_delivery_file_id"]
    assert "Logo ảnh và Watermark chữ" in branding_query.edits[-1][0]

    edit_query = _CallbackQuery(user_id, f"videodub|edit|{artifact['token']}")
    asyncio.run(
        bot.handle_video_dubbing_callback(
            SimpleNamespace(callback_query=edit_query),
            context,
        )
    )
    edit_state = bot.get_video_editor_pending(user_id)
    assert edit_state["current_screen"] == "workspace"
    assert edit_state["edit_session_id"] == session_id
    assert edit_state["source_file_id"] == job["video_delivery_file_id"]
    assert "Không gian chỉnh sửa video" in edit_query.edits[-1][0]
    assert len(bot.SUBTITLE_DUB_PIPELINE_JOBS) == 1
    assert bot.SUBTITLE_DUB_PIPELINE_JOBS[job["job_key"]] == job
