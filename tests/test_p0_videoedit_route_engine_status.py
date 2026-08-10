from __future__ import annotations

import asyncio
import ast
import hashlib
import html
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from services import video_edit_long_media, video_editengine1


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    start_candidates = (
        BOT_SOURCE.find(f"\ndef {name}"),
        BOT_SOURCE.find(f"\nasync def {name}"),
    )
    start_marker = max(start_candidates)
    if start_marker < 0:
        raise AssertionError(f"missing function: {name}")
    start = start_marker + 1
    next_positions = [
        position
        for position in (
            BOT_SOURCE.find("\ndef ", start + 1),
            BOT_SOURCE.find("\nasync def ", start + 1),
            BOT_SOURCE.find("\nclass ", start + 1),
        )
        if position >= 0
    ]
    broad_end = min(next_positions) if next_positions else len(BOT_SOURCE)
    candidate = BOT_SOURCE[start:broad_end]
    node = ast.parse(candidate).body[0]
    lines = candidate.splitlines(keepends=True)
    return "".join(lines[: node.end_lineno]).rstrip() + "\n"


def _compile_functions(names: list[str], namespace: dict):
    source = "from __future__ import annotations\n\n" + "\n".join(
        _function_source(name) for name in names
    )
    exec(compile(source, filename="bot.py", mode="exec"), namespace)
    return namespace


def _valid_probe(*, full_decode: bool) -> dict:
    return {
        "ok": True,
        "has_video": True,
        "video_codec": "h264",
        "duration_ms": 1_000,
        "width": 1280,
        "height": 720,
        "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
        "full_decode": full_decode,
    }


def _canonical_receipt(*, full_decode: bool, status: str = "delivered") -> dict:
    return {
        "local_worker_job_id": 71,
        "user_id": "9",
        "product_type": video_editengine1.PRODUCT_TYPE,
        "worker_job_type": video_editengine1.WORKER_JOB_TYPE,
        "engine_route": video_editengine1.ENGINE_ROUTE,
        "worker_owner": video_editengine1.OUTBOX_OWNER,
        "status": status,
        "receipt_state": "created",
        "delivery_message_id": "501",
        "delivery_file_id": "telegram-file-501",
        "output_file_id": "telegram-file-501",
        "output_path": "output.mp4",
        "output_sha256": "a" * 64,
        "output_size_bytes": 2048,
        "ffprobe": _valid_probe(full_decode=full_decode),
        "artifact_receipts": [],
        "delivery_cursor": 0,
        "tail": {},
        "price_xu": 0,
    }


def _worker_job(*, stage: str = "delivered") -> dict:
    return {
        "id": 71,
        "job_type": video_editengine1.WORKER_JOB_TYPE,
        "user_id": "9",
        "status": "completed" if stage == "delivered" else "running",
        "xu_cost": 0,
        "error_short": json.dumps(
            {"local1": True, "stage": stage, "processed": 1, "total": 1, "delivered": 1}
        ),
    }


def _artifact_receipt(index: int, *, full_decode: bool, size: int = 2048) -> dict:
    return {
        "index": index,
        "message_id": str(500 + index),
        "file_id": f"telegram-file-{500 + index}",
        "size": size,
        "sha256": format(index, "x") * 64,
        "ffprobe": _valid_probe(full_decode=full_decode),
    }


def _strict_receipt(
    artifacts: list[dict],
    *,
    cursor_state: str = "delivered",
) -> dict:
    last = artifacts[-1]
    cursor = video_edit_long_media.DeliveryCursor(
        state=cursor_state,
        output_index=(len(artifacts) if cursor_state in {"accepted", "delivered"} else len(artifacts) + 1),
        attempt_id=f"attempt-{len(artifacts)}",
        message_id=(str(last["message_id"]) if cursor_state in {"accepted", "delivered"} else ""),
        file_id=(str(last["file_id"]) if cursor_state in {"accepted", "delivered"} else ""),
    )
    receipt = _canonical_receipt(full_decode=True)
    receipt.update(
        {
            "delivery_message_id": str(last["message_id"]),
            "delivery_file_id": str(last["file_id"]),
            "output_file_id": str(last["file_id"]),
            "output_path": ",".join(f"part-{index}.mp4" for index in range(1, len(artifacts) + 1)),
            "output_size_bytes": sum(int(item["size"]) for item in artifacts),
            "artifact_receipts": artifacts,
            "delivery_cursor": len(artifacts),
            "tail": {"delivery_cursor": cursor.to_mapping()},
        }
    )
    return receipt


def test_video_edit_adapter_reads_only_exact_owned_worker_job_and_receipt() -> None:
    calls: list[tuple[str, object, object]] = []

    class ReadSnapshot:
        def __init__(self) -> None:
            self.statements: list[str] = []
            self.closed = False

        def execute(self, statement: str):
            self.statements.append(str(statement))
            return self

        def close(self) -> None:
            self.closed = True

    snapshot = ReadSnapshot()

    def get_local_worker_job_readonly(job_id, *, conn=None):
        calls.append(("worker", job_id, conn))
        return _worker_job(stage="processing_video")

    def receipt_for_worker(job_id, *, conn=None):
        calls.append(("receipt", job_id, conn))
        return _canonical_receipt(full_decode=True, status="rendering")

    ns = _compile_functions(
        ["video_edit_progress_read_status"],
        {
            "safe_int": lambda value, default=0: int(value or default),
            "db_connect_readonly": lambda: snapshot,
            "get_local_worker_job_readonly": get_local_worker_job_readonly,
            "video_editengine1_job_for_worker": receipt_for_worker,
            "video_editengine1": video_editengine1,
        },
    )

    status = ns["video_edit_progress_read_status"]("71", user_id=9)
    assert status["id"] == 71
    assert status["_video_edit_canonical"]["local_worker_job_id"] == 71
    assert snapshot.statements == ["BEGIN"]
    assert snapshot.closed is True
    assert calls == [
        ("worker", 71, snapshot),
        ("receipt", 71, snapshot),
    ]
    assert ns["video_edit_progress_read_status"]("71", user_id=10) == {}


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("engine_route", "provider_video"),
        ("worker_owner", "other_product"),
    ],
)
def test_video_edit_status_adapter_requires_the_exact_engine_route_and_worker_owner(
    field: str,
    invalid_value: str,
) -> None:
    class ReadSnapshot:
        def execute(self, _statement: str):
            return self

        def close(self) -> None:
            return None

    snapshot = ReadSnapshot()
    receipt = _canonical_receipt(full_decode=True, status="rendering")
    receipt[field] = invalid_value
    ns = _compile_functions(
        ["video_edit_progress_read_status"],
        {
            "safe_int": lambda value, default=0: int(value or default),
            "db_connect_readonly": lambda: snapshot,
            "get_local_worker_job_readonly": lambda _job_id, **_kwargs: _worker_job(
                stage="processing_video"
            ),
            "video_editengine1_job_for_worker": lambda _job_id, **_kwargs: dict(receipt),
            "video_editengine1": video_editengine1,
        },
    )

    assert ns["video_edit_progress_read_status"]("71", user_id=9) == {}


def test_video_edit_status_requires_full_decode_before_completion() -> None:
    ns = _compile_functions(
        [
            "video_local_job_progress_payload",
            "video_edit_delivery_receipt_is_complete",
            "video_editor_job_status_text",
            "video_edit_progress_snapshot",
        ],
        {
            "json": json,
            "html": html,
            "hashlib": hashlib,
            "re": __import__("re"),
            "safe_int": lambda value, default=0: int(value or default),
            "normalize_user_language": lambda value: value,
            "video_editengine1": video_editengine1,
            "video_editengine1_job_for_worker": lambda _job_id: (_ for _ in ()).throw(
                AssertionError("snapshot must use the already-read exact receipt")
            ),
        },
    )

    missing_decode = {
        **_worker_job(),
        "_video_edit_canonical": _canonical_receipt(full_decode=False),
    }
    snapshot = ns["video_edit_progress_snapshot"]("71", user_id=9, job=missing_decode, lang="vi")
    assert snapshot["product_type"] == "video_edit"
    assert snapshot["terminal_state"] == "delivery_unknown"
    assert "Hoàn tất" not in snapshot["text"]


@pytest.mark.parametrize(
    "missing_field",
    ["worker_status", "stage", "processed", "total", "delivered"],
)
def test_video_edit_status_requires_complete_worker_delivery_evidence(
    missing_field: str,
) -> None:
    ns = _compile_functions(
        [
            "video_local_job_progress_payload",
            "video_edit_delivery_receipt_is_complete",
            "video_editor_job_status_text",
            "video_edit_progress_snapshot",
        ],
        {
            "json": json,
            "html": html,
            "hashlib": hashlib,
            "re": __import__("re"),
            "safe_int": lambda value, default=0: int(value or default),
            "normalize_user_language": lambda value: value,
            "video_editengine1": video_editengine1,
            "video_editengine1_job_for_worker": lambda _job_id: {},
        },
    )
    worker = _worker_job()
    progress = json.loads(worker["error_short"])
    if missing_field == "worker_status":
        worker.pop("status")
    else:
        progress.pop(missing_field)
        worker["error_short"] = json.dumps(progress)

    snapshot = ns["video_edit_progress_snapshot"](
        "71",
        user_id=9,
        job={
            **worker,
            "_video_edit_canonical": _canonical_receipt(full_decode=True),
        },
        lang="vi",
    )

    assert snapshot["terminal_state"] == "delivery_unknown"
    assert snapshot["percent"] == 95
    assert "Hoàn tất" not in snapshot["text"]
    assert snapshot["text"].count("✅") == 5


def test_video_edit_status_rejects_noncanonical_sha_probe_and_size_fields() -> None:
    ns = _compile_functions(
        [
            "video_local_job_progress_payload",
            "video_edit_delivery_receipt_is_complete",
            "video_editor_job_status_text",
            "video_edit_progress_snapshot",
        ],
        {
            "json": json,
            "html": html,
            "hashlib": hashlib,
            "re": __import__("re"),
            "safe_int": lambda value, default=0: int(value or default),
            "normalize_user_language": lambda value: value,
            "video_editengine1": video_editengine1,
            "video_editengine1_job_for_worker": lambda _job_id: (_ for _ in ()).throw(
                AssertionError("snapshot must use the already-read exact receipt")
            ),
        },
    )

    invalid_receipts = []
    for field, value in (
        ("output_sha256", "g" * 64),
        ("output_size_bytes", True),
        ("delivery_message_id", "0501"),
        ("delivery_file_id", True),
        ("delivery_file_id", " telegram-file-501 "),
    ):
        receipt = _canonical_receipt(full_decode=True)
        receipt[field] = value
        invalid_receipts.append(receipt)
    for field, value in (
        ("ok", "true"),
        ("width", True),
        ("format_name", "notmp4"),
    ):
        receipt = _canonical_receipt(full_decode=True)
        receipt["ffprobe"][field] = value
        invalid_receipts.append(receipt)
    mismatched_file_identity = _canonical_receipt(full_decode=True)
    mismatched_file_identity["output_file_id"] = "different-telegram-file"
    invalid_receipts.append(mismatched_file_identity)

    for receipt in invalid_receipts:
        snapshot = ns["video_edit_progress_snapshot"](
            "71",
            user_id=9,
            job={**_worker_job(), "_video_edit_canonical": receipt},
            lang="vi",
        )
        assert snapshot["terminal_state"] == "delivery_unknown", receipt
        assert "Hoàn tất" not in snapshot["text"]
        assert snapshot["text"].count("✅") == 5


@pytest.mark.parametrize(
    ("worker_status", "canonical_status"),
    [
        ("failed", "delivered"),
        ("succeeded", "failed_no_charge"),
    ],
)
def test_video_edit_status_never_completes_when_worker_and_canonical_terminals_conflict(
    worker_status: str,
    canonical_status: str,
) -> None:
    ns = _compile_functions(
        [
            "video_local_job_progress_payload",
            "video_edit_delivery_receipt_is_complete",
            "video_editor_job_status_text",
            "video_edit_progress_snapshot",
        ],
        {
            "json": json,
            "html": html,
            "hashlib": hashlib,
            "re": __import__("re"),
            "safe_int": lambda value, default=0: int(value or default),
            "normalize_user_language": lambda value: value,
            "video_editengine1": video_editengine1,
            "video_editengine1_job_for_worker": lambda _job_id: {},
        },
    )
    worker = _worker_job()
    worker["status"] = worker_status
    canonical = _canonical_receipt(
        full_decode=True,
        status=canonical_status,
    )
    if canonical_status == "failed_no_charge":
        canonical.update(
            {
                "receipt_state": "",
                "delivery_message_id": "",
                "delivery_file_id": "",
                "output_file_id": "",
            }
        )

    snapshot = ns["video_edit_progress_snapshot"](
        "71",
        user_id=9,
        job={**worker, "_video_edit_canonical": canonical},
        lang="vi",
    )

    assert snapshot["terminal_state"] != "delivered"
    assert snapshot["percent"] != 100
    assert "Hoàn tất" not in snapshot["text"]
    assert snapshot["text"].count("✅") < 6


@pytest.mark.parametrize("canonical_status", ["rendering", "failed_no_charge"])
def test_video_edit_terminal_worker_without_delivery_stage_is_uncertain(
    canonical_status: str,
) -> None:
    ns = _compile_functions(
        [
            "video_local_job_progress_payload",
            "video_edit_delivery_receipt_is_complete",
            "video_editor_job_status_text",
            "video_edit_progress_snapshot",
        ],
        {
            "json": json,
            "html": html,
            "hashlib": hashlib,
            "re": __import__("re"),
            "safe_int": lambda value, default=0: int(value or default),
            "normalize_user_language": lambda value: value,
            "video_editengine1": video_editengine1,
            "video_editengine1_job_for_worker": lambda _job_id: {},
        },
    )
    worker = _worker_job()
    progress = json.loads(worker["error_short"])
    progress.pop("stage")
    worker["error_short"] = json.dumps(progress)
    canonical = _canonical_receipt(
        full_decode=canonical_status != "failed_no_charge",
        status=canonical_status,
    )
    if canonical_status == "failed_no_charge":
        canonical.update(
            {
                "receipt_state": "",
                "delivery_message_id": "",
                "delivery_file_id": "",
                "output_file_id": "",
            }
        )

    snapshot = ns["video_edit_progress_snapshot"](
        "71",
        user_id=9,
        job={**worker, "_video_edit_canonical": canonical},
        lang="vi",
    )

    assert snapshot["terminal_state"] == "delivery_unknown"
    assert snapshot["percent"] == 95
    assert "Hoàn tất" not in snapshot["text"]
    assert snapshot["text"].count("✅") == 5


def test_video_edit_status_rejects_nonterminal_strict_delivery_cursor() -> None:
    ns = _compile_functions(
        [
            "video_local_job_progress_payload",
            "video_edit_delivery_receipt_is_complete",
            "video_editor_job_status_text",
            "video_edit_progress_snapshot",
        ],
        {
            "json": json,
            "html": html,
            "hashlib": hashlib,
            "re": __import__("re"),
            "safe_int": lambda value, default=0: int(value or default),
            "normalize_user_language": lambda value: value,
            "video_editengine1": video_editengine1,
            "video_editengine1_job_for_worker": lambda _job_id: {},
        },
    )
    canonical = _strict_receipt(
        [_artifact_receipt(1, full_decode=True)],
        cursor_state="sending",
    )
    snapshot = ns["video_edit_progress_snapshot"](
        "71",
        user_id=9,
        job={**_worker_job(), "_video_edit_canonical": canonical},
        lang="vi",
    )

    assert snapshot["terminal_state"] == "delivery_unknown"
    assert snapshot["percent"] == 95
    assert "Hoàn tất" not in snapshot["text"]
    assert "⚠️ Gửi kết quả" in snapshot["text"]


def test_video_edit_status_rejects_progress_count_mismatch_with_receipt_manifest() -> None:
    ns = _compile_functions(
        [
            "video_local_job_progress_payload",
            "video_edit_delivery_receipt_is_complete",
            "video_editor_job_status_text",
            "video_edit_progress_snapshot",
        ],
        {
            "json": json,
            "html": html,
            "hashlib": hashlib,
            "re": __import__("re"),
            "safe_int": lambda value, default=0: int(value or default),
            "normalize_user_language": lambda value: value,
            "video_editengine1": video_editengine1,
            "video_editengine1_job_for_worker": lambda _job_id: {},
        },
    )
    worker = _worker_job()
    worker["error_short"] = json.dumps(
        {"local1": True, "stage": "delivered", "processed": 2, "total": 2, "delivered": 1}
    )
    snapshot = ns["video_edit_progress_snapshot"](
        "71",
        user_id=9,
        job={
            **worker,
            "_video_edit_canonical": _strict_receipt(
                [_artifact_receipt(1, full_decode=True)]
            ),
        },
        lang="vi",
    )

    assert snapshot["terminal_state"] == "delivery_unknown"
    assert "Hoàn tất" not in snapshot["text"]
    assert "Đã gửi: <b>2/2</b> phần" not in snapshot["text"]
    assert "Đã có biên nhận: <b>1/2</b> phần" in snapshot["text"]


def test_video_edit_status_requires_full_decode_for_every_artifact() -> None:
    ns = _compile_functions(
        [
            "video_local_job_progress_payload",
            "video_edit_delivery_receipt_is_complete",
            "video_editor_job_status_text",
            "video_edit_progress_snapshot",
        ],
        {
            "json": json,
            "html": html,
            "hashlib": hashlib,
            "re": __import__("re"),
            "safe_int": lambda value, default=0: int(value or default),
            "normalize_user_language": lambda value: value,
            "video_editengine1": video_editengine1,
            "video_editengine1_job_for_worker": lambda _job_id: {},
        },
    )
    artifacts = [
        _artifact_receipt(1, full_decode=True, size=1024),
        _artifact_receipt(2, full_decode=False, size=1024),
    ]
    worker = _worker_job()
    worker["error_short"] = json.dumps(
        {"local1": True, "stage": "delivered", "processed": 2, "total": 2, "delivered": 2}
    )
    snapshot = ns["video_edit_progress_snapshot"](
        "71",
        user_id=9,
        job={**worker, "_video_edit_canonical": _strict_receipt(artifacts)},
        lang="vi",
    )

    assert snapshot["terminal_state"] == "delivery_unknown"
    assert "Hoàn tất" not in snapshot["text"]
    assert snapshot["text"].count("✅") == 5


def test_video_edit_snapshot_fails_closed_for_missing_or_mismatched_exact_job() -> None:
    ns = _compile_functions(
        [
            "video_local_job_progress_payload",
            "video_edit_delivery_receipt_is_complete",
            "video_editor_job_status_text",
            "video_edit_progress_snapshot",
        ],
        {
            "json": json,
            "html": html,
            "hashlib": hashlib,
            "re": __import__("re"),
            "safe_int": lambda value, default=0: int(value or default),
            "normalize_user_language": lambda value: value,
            "video_editengine1": video_editengine1,
            "video_editengine1_job_for_worker": lambda _job_id: {},
        },
    )
    invalid_jobs = [
        {},
        {**_worker_job(), "id": 72, "_video_edit_canonical": _canonical_receipt(full_decode=True)},
        {**_worker_job(), "user_id": "10", "_video_edit_canonical": _canonical_receipt(full_decode=True)},
        {
            **_worker_job(),
            "_video_edit_canonical": {
                **_canonical_receipt(full_decode=True),
                "local_worker_job_id": 72,
            },
        },
    ]

    for invalid in invalid_jobs:
        assert ns["video_edit_progress_snapshot"](
            "71",
            user_id=9,
            job=invalid,
            lang="vi",
        ) == {}


def test_delivery_uncertain_panel_preserves_an_already_recorded_charge() -> None:
    ns = _compile_functions(
        [
            "video_local_job_progress_payload",
            "video_edit_delivery_receipt_is_complete",
            "video_editor_job_status_text",
            "video_edit_progress_snapshot",
        ],
        {
            "json": json,
            "html": html,
            "hashlib": hashlib,
            "re": __import__("re"),
            "safe_int": lambda value, default=0: int(value or default),
            "normalize_user_language": lambda value: value,
            "video_editengine1": video_editengine1,
            "video_editengine1_job_for_worker": lambda _job_id: (_ for _ in ()).throw(
                AssertionError("snapshot must use the already-read exact receipt")
            ),
        },
    )
    receipt = _canonical_receipt(full_decode=False, status="charged")
    receipt.update({"price_xu": 7, "charge_state": "charged", "charged_xu": 7})

    snapshot = ns["video_edit_progress_snapshot"](
        "71",
        user_id=9,
        job={**_worker_job(), "_video_edit_canonical": receipt},
        lang="vi",
    )

    assert snapshot["terminal_state"] == "delivery_unknown"
    assert "Hoàn tất" not in snapshot["text"]
    assert "Đã ghi nhận trừ: <b>7 Xu</b>" in snapshot["text"]
    assert "không trừ Xu" not in snapshot["text"]
    assert snapshot["text"].count("✅") == 5

    delivered = {
        **_worker_job(),
        "_video_edit_canonical": _canonical_receipt(full_decode=True),
    }
    snapshot = ns["video_edit_progress_snapshot"]("71", user_id=9, job=delivered, lang="vi")
    assert snapshot["terminal_state"] == "delivered"
    assert "Hoàn tất" in snapshot["text"]
    assert snapshot["text"].count("✅") == 6

    failed = {
        **_worker_job(stage="failed_no_charge"),
        "_video_edit_canonical": _canonical_receipt(
            full_decode=False,
            status="failed_no_charge",
        ),
    }
    snapshot = ns["video_edit_progress_snapshot"]("71", user_id=9, job=failed, lang="vi")
    assert snapshot["terminal_state"] == "failed_no_charge"
    assert "Chưa xử lý được" in snapshot["text"]
    assert "Hoàn tất" not in snapshot["text"]


def test_video_edit_scheduler_retries_the_same_terminal_panel_after_a_transient_edit_failure() -> None:
    registry = {
        "video_edit:71": {
            "key": "video_edit:71",
            "product_type": "video_edit",
            "job_id": "71",
            "chat_id": 99001,
            "message_id": 7001,
            "user_id": 9,
            "lang": "vi",
            "update_count": 0,
            "max_updates": 10,
            "last_percent": 50,
            "last_render_hash": "old",
            "stop_on_terminal": True,
            "edit_only": False,
        }
    }
    events: list[str] = []

    class Bot:
        async def edit_message_text(self, **kwargs):
            events.append(f"edit:{kwargs['chat_id']}:{kwargs['message_id']}")
            assert kwargs["reply_markup"] == "videoedit|status|71"
            raise RuntimeError("telegram edit failed")

        async def send_message(self, **_kwargs):
            events.append("send")

    async def status_for_tick(_context, _record):
        return {
            **_worker_job(stage="delivery_unknown"),
            "_video_edit_canonical": _canonical_receipt(
                full_decode=False,
                status="delivery_unknown",
            ),
        }

    ns = _compile_functions(
        ["progress_auto_refresh_tick"],
        {
            "PROGRESS_AUTO_REFRESH_JOBS": registry,
            "PROGRESS_AUTO_REFRESH_MAX_UPDATES": 10,
            "PROGRESS_AUTO_REFRESH_STOP_ON_TERMINAL": True,
            "progress_auto_refresh_status_for_tick": status_for_tick,
            "progress_auto_refresh_snapshot": lambda *_args, **_kwargs: {
                "stage": "delivery_unknown",
                "percent": 95,
                "terminal_state": "delivery_unknown",
                "text": "needs verification",
                "render_hash": "new",
            },
            "progress_auto_refresh_should_edit": lambda *_args: True,
            "progress_auto_refresh_keyboard": lambda product_type, job_id, _lang: (
                f"videoedit|status|{job_id}" if product_type == "video_edit" else "generic"
            ),
            "progress_auto_refresh_key": lambda product_type, job_id: f"{product_type}:{job_id}",
            "safe_int": lambda value, default=0: int(value or default),
            "now_text": lambda: "2026-08-09 10:00:00",
            "sanitize_log_text": str,
            "video_edit_panel_not_modified": lambda _error: False,
            "re": __import__("re"),
            "hashlib": hashlib,
        },
    )

    result = asyncio.run(
        ns["progress_auto_refresh_tick"](SimpleNamespace(bot=Bot()), "video_edit:71")
    )
    assert result["status"] == "retry_pending"
    assert result["record"].get("stopped") is not True
    assert result["record"].get("stop_reason") in {None, ""}
    assert result["record"]["task_alive"] is True
    assert result["record"]["last_render_hash"] == "old"
    assert result["record"]["last_percent"] == 50
    assert events == ["edit:99001:7001"]


def test_video_edit_scheduler_treats_message_not_modified_as_terminal_panel_success() -> None:
    key = "video_edit:71"
    registry = {
        key: {
            "key": key,
            "product_type": "video_edit",
            "job_id": "71",
            "chat_id": 99001,
            "message_id": 7001,
            "user_id": 9,
            "lang": "vi",
            "update_count": 0,
            "max_updates": 10,
            "last_percent": 50,
            "last_render_hash": "old",
            "stop_on_terminal": True,
            "edit_only": True,
        }
    }
    events: list[str] = []

    class Bot:
        async def edit_message_text(self, **_kwargs):
            events.append("edit")
            raise RuntimeError("BadRequest: message is not modified")

        async def send_message(self, **_kwargs):
            events.append("send")

    async def status_for_tick(_context, _record):
        return {
            **_worker_job(stage="delivered"),
            "_video_edit_canonical": _canonical_receipt(full_decode=True),
        }

    ns = _compile_functions(
        ["progress_auto_refresh_tick"],
        {
            "PROGRESS_AUTO_REFRESH_JOBS": registry,
            "PROGRESS_AUTO_REFRESH_MAX_UPDATES": 10,
            "PROGRESS_AUTO_REFRESH_STOP_ON_TERMINAL": True,
            "progress_auto_refresh_status_for_tick": status_for_tick,
            "progress_auto_refresh_snapshot": lambda *_args, **_kwargs: {
                "stage": "delivered",
                "percent": 100,
                "terminal_state": "delivered",
                "text": "delivered",
                "render_hash": "delivered-hash",
            },
            "progress_auto_refresh_should_edit": lambda *_args: True,
            "progress_auto_refresh_keyboard": lambda *_args: "videoedit|status|71",
            "progress_auto_refresh_key": lambda product_type, job_id: f"{product_type}:{job_id}",
            "safe_int": lambda value, default=0: int(value or default),
            "now_text": lambda: "2026-08-09 10:00:00",
            "sanitize_log_text": str,
            "video_edit_panel_not_modified": lambda error: "message is not modified" in str(error).lower(),
            "re": __import__("re"),
            "hashlib": hashlib,
        },
    )

    result = asyncio.run(ns["progress_auto_refresh_tick"](SimpleNamespace(bot=Bot()), key))
    assert result["status"] == "updated"
    assert result["record"]["stopped"] is True
    assert result["record"]["stop_reason"] == "delivered"
    assert result["record"]["last_render_hash"] == "delivered-hash"
    assert result["record"]["last_percent"] == 100
    assert result["record"]["edit_success_count"] == 1
    assert result["record"].get("edit_fail_count", 0) == 0
    assert events == ["edit"]


@pytest.mark.parametrize("case", ["job_missing", "registry_key_mismatch"])
def test_video_edit_scheduler_stops_without_telegram_for_invalid_exact_binding(case: str) -> None:
    key = "video_edit:71"
    registry = {
        key: {
            "key": key,
            "product_type": "video_edit",
            "job_id": "72" if case == "registry_key_mismatch" else "71",
            "chat_id": 99001,
            "message_id": 7001,
            "user_id": 9,
            "lang": "vi",
            "update_count": 2,
            "max_updates": 10,
            "last_stage": "processing_video",
            "last_percent": 60,
            "current_stage": "processing_video",
            "percent": 60,
            "last_render_hash": "known-good",
            "stop_on_terminal": True,
            "stopped": False,
        }
    }
    events: list[str] = []

    class Bot:
        async def edit_message_text(self, **_kwargs):
            events.append("edit")

        async def send_message(self, **_kwargs):
            events.append("send")

    async def read_status(_context, _record):
        return {} if case == "job_missing" else _worker_job(stage="processing_video")

    ns = _compile_functions(
        ["progress_auto_refresh_tick"],
        {
            "PROGRESS_AUTO_REFRESH_JOBS": registry,
            "PROGRESS_AUTO_REFRESH_MAX_UPDATES": 10,
            "PROGRESS_AUTO_REFRESH_STOP_ON_TERMINAL": True,
            "progress_auto_refresh_status_for_tick": read_status,
            "progress_auto_refresh_snapshot": lambda *_args, **_kwargs: {},
            "progress_auto_refresh_should_edit": lambda *_args: True,
            "progress_auto_refresh_keyboard": lambda *_args: "keyboard",
            "progress_auto_refresh_key": lambda product_type, job_id: f"{product_type}:{job_id}",
            "now_text": lambda: "2026-08-09 10:00:00",
            "sanitize_log_text": str,
            "re": __import__("re"),
            "hashlib": hashlib,
            "safe_int": lambda value, default=0: int(value or default),
        },
    )

    result = asyncio.run(ns["progress_auto_refresh_tick"](SimpleNamespace(bot=Bot()), key))
    stopped = result["record"]
    assert result["status"] == "stopped"
    assert stopped["stop_reason"] == "job_missing_or_owner_mismatch"
    assert stopped["task_alive"] is False
    assert stopped["last_stage"] == "processing_video"
    assert stopped["last_percent"] == 60
    assert stopped["last_render_hash"] == "known-good"
    assert events == []


def test_video_edit_panel_registration_preserves_owner_and_never_normalizes_to_product_video() -> None:
    snapshots: list[tuple[str, str, int]] = []
    registry: dict[str, dict] = {}

    def snapshot(product_type, job_id, **kwargs):
        snapshots.append(
            (
                str(product_type),
                str(job_id),
                int(kwargs.get("user_id") or 0),
            )
        )
        return {
            "stage": "received",
            "percent": 10,
            "terminal_state": "",
            "render_hash": "received",
        }

    product_progress = SimpleNamespace(
        normalize_product_type=lambda value: (
            (_ for _ in ()).throw(AssertionError("video_edit must not use generic normalization"))
            if str(value) == "video_edit"
            else str(value)
        ),
        product_progress_safe_callback_value=lambda value, _limit: str(value),
    )
    ns = _compile_functions(
        ["progress_auto_refresh_key", "progress_auto_refresh_register"],
        {
            "product_progress_status": product_progress,
            "PROGRESS_AUTO_REFRESH_ENABLED": True,
            "PROGRESS_AUTO_REFRESH_JOBS": registry,
            "PROGRESS_AUTO_REFRESH_EDIT_ONLY": False,
            "PROGRESS_AUTO_REFRESH_INTERVAL_SECONDS": 5,
            "PROGRESS_AUTO_REFRESH_MAX_UPDATES": 10,
            "PROGRESS_AUTO_REFRESH_STOP_ON_TERMINAL": True,
            "PROGRESS_AUTO_REFRESH_MIN_DELTA_PERCENT": 5,
            "MUSIC_AUTO_DELIVERY_POLL_INTERVAL_SECONDS": 5,
            "MUSIC_AUTO_DELIVERY_MAX_POLLS": 10,
            "MUSIC_AUTO_DELIVERY_ENABLED": False,
            "MUSIC_AUTO_DELIVERY_STOP_ON_TERMINAL": True,
            "LOCAL_WORKER_MAX_JOB_SECONDS": 600,
            "math": __import__("math"),
            "progress_auto_refresh_snapshot": snapshot,
            "progress_product_type_is_music": lambda *_args: (_ for _ in ()).throw(
                AssertionError("video_edit must not enter generic music/product detection")
            ),
            "normalize_user_language": lambda value: value,
            "now_text": lambda: "2026-08-09 10:00:00",
        },
    )

    record = ns["progress_auto_refresh_register"](
        product_type="video_edit",
        job_id="71",
        chat_id=99001,
        message_id=7001,
        user_id=9,
        lang="vi",
        start_task=False,
    )

    assert record["key"] == "video_edit:71"
    assert record["product_type"] == "video_edit"
    assert record["edit_only"] is True
    assert snapshots == [("video_edit", "71", 9)]
    assert record["max_updates"] >= 121


def test_video_edit_panel_keeps_exact_binding_when_auto_refresh_is_disabled() -> None:
    registry: dict[str, dict] = {}
    product_progress = SimpleNamespace(
        normalize_product_type=lambda value: str(value),
        product_progress_safe_callback_value=lambda value, _limit: str(value),
    )
    ns = _compile_functions(
        ["progress_auto_refresh_key", "progress_auto_refresh_register"],
        {
            "product_progress_status": product_progress,
            "PROGRESS_AUTO_REFRESH_ENABLED": False,
            "PROGRESS_AUTO_REFRESH_JOBS": registry,
            "PROGRESS_AUTO_REFRESH_EDIT_ONLY": False,
            "PROGRESS_AUTO_REFRESH_INTERVAL_SECONDS": 5,
            "PROGRESS_AUTO_REFRESH_MAX_UPDATES": 10,
            "PROGRESS_AUTO_REFRESH_STOP_ON_TERMINAL": True,
            "PROGRESS_AUTO_REFRESH_MIN_DELTA_PERCENT": 5,
            "MUSIC_AUTO_DELIVERY_POLL_INTERVAL_SECONDS": 5,
            "MUSIC_AUTO_DELIVERY_MAX_POLLS": 10,
            "MUSIC_AUTO_DELIVERY_ENABLED": False,
            "MUSIC_AUTO_DELIVERY_STOP_ON_TERMINAL": True,
            "LOCAL_WORKER_MAX_JOB_SECONDS": 600,
            "math": __import__("math"),
            "progress_auto_refresh_snapshot": lambda *_args, **_kwargs: {},
            "progress_product_type_is_music": lambda *_args: False,
            "normalize_user_language": lambda value: value,
            "now_text": lambda: "2026-08-10 01:00:00",
            "progress_auto_refresh_start_task": lambda *_args: (_ for _ in ()).throw(
                AssertionError("disabled scheduler must not start")
            ),
        },
    )

    record = ns["progress_auto_refresh_register"](
        product_type="video_edit",
        job_id="71",
        chat_id=99001,
        message_id=7001,
        user_id=9,
        lang="vi",
        initial_snapshot={
            "stage": "received",
            "percent": 10,
            "terminal_state": "",
            "render_hash": "received",
        },
        start_task=True,
    )

    assert record["key"] == "video_edit:71"
    assert record["product_type"] == "video_edit"
    assert record["job_id"] == "71"
    assert record["user_id"] == 9
    assert record["chat_id"] == 99001
    assert record["message_id"] == 7001
    assert record["enabled"] is False
    assert record["scheduler_status"] == "disabled"
    assert record["task_started"] is False
    assert record["task_alive"] is False
    assert registry["video_edit:71"] == record
    assert ns["progress_auto_refresh_register"](
        product_type="frame_video",
        job_id="frame-71",
        chat_id=99001,
        message_id=7002,
        user_id=9,
        lang="vi",
        initial_snapshot={"stage": "received", "percent": 5},
        start_task=True,
    ) == {}


def test_video_edit_tick_and_loop_never_enter_generic_product_detection() -> None:
    reads: list[tuple[str, str, int]] = []
    registry = {
        "video_edit:71": {
            "product_type": "video_edit",
            "job_id": "71",
            "user_id": 9,
            "stopped": False,
        }
    }

    def read_status(product_type, job_id, user_id=0):
        reads.append((str(product_type), str(job_id), int(user_id or 0)))
        return _worker_job(stage="processing_video")

    def generic_detector(*_args):
        raise AssertionError("video_edit must not enter generic music/product detection")

    async def failed_tick(_context, _key):
        raise RuntimeError("expected scheduler failure")

    ns = _compile_functions(
        ["progress_auto_refresh_status_for_tick", "progress_auto_refresh_loop"],
        {
            "asyncio": asyncio,
            "PROGRESS_AUTO_REFRESH_JOBS": registry,
            "PROGRESS_AUTO_REFRESH_INTERVAL_SECONDS": 0,
            "progress_product_type_is_music": generic_detector,
            "progress_auto_refresh_read_status": read_status,
            "music_progress_refresh_job_status": lambda *_args, **_kwargs: None,
            "music_auto_deliver_from_progress_record": lambda *_args, **_kwargs: None,
            "progress_auto_refresh_tick": failed_tick,
            "get_engine_async_job": lambda *_args: {},
            "mark_music_confirm_submit_blocker": lambda *_args, **_kwargs: None,
            "now_text": lambda: "2026-08-09 10:00:00",
            "sanitize_provider_status_text": lambda value, *_args: str(value),
            "sanitize_log_text": str,
            "logger": SimpleNamespace(warning=lambda *_args, **_kwargs: None),
        },
    )

    status = asyncio.run(
        ns["progress_auto_refresh_status_for_tick"](
            SimpleNamespace(),
            registry["video_edit:71"],
        )
    )
    assert status["id"] == 71
    assert reads == [("video_edit", "71", 9)]

    asyncio.run(ns["progress_auto_refresh_loop"](SimpleNamespace(), "video_edit:71"))
    assert registry["video_edit:71"]["stop_reason"] == "auto_tick_exception"


def test_submitters_reuse_job_bound_status_panel_helper() -> None:
    helper = _function_source("show_video_editor_job_status_panel")
    assert "video_editor_job_status_text" in helper
    assert "video_editor_status_keyboard" in helper
    assert "progress_auto_refresh_register_message" in helper
    assert 'product_type="video_edit"' in helper

    for submitter in ("submit_video_edit_local_free_job", "submit_local_video_editor_job"):
        source = _function_source(submitter)
        committed = source[source.index("mark_video_editor_submission_committed()") :]
        assert "show_video_editor_job_status_panel(" in committed
        assert "Đã nhận tác vụ" not in committed
        assert "Đã nhận yêu cầu xử lý video" not in committed


def test_job_bound_panel_renders_all_six_stages_immediately_after_submit() -> None:
    rendered: list[dict] = []
    registered: list[dict] = []
    reads: list[tuple[int, int]] = []
    snapshots: list[dict] = []

    class Message:
        chat_id = 99001
        message_id = 7002

        async def reply_text(self, text, **kwargs):
            rendered.append({"text": text, **kwargs})
            return self

    class Query:
        message = Message()

        async def edit_message_text(self, text, **kwargs):
            rendered.append({"text": text, **kwargs})
            return self.message

    def status_text(job, _lang):
        return video_editor_status_text(job)

    def video_editor_status_text(job):
        assert job["id"] == 71
        return "\n".join(
            [
                "🎞 <b>Trạng thái chỉnh sửa video</b>",
                "✅ Nhận video",
                "⏳ Kiểm tra cấu hình",
                "⬜ Chuẩn bị file",
                "⬜ Chỉnh sửa video",
                "⬜ Kiểm tra MP4",
                "⬜ Gửi kết quả",
            ]
        )

    def register(message, context, **kwargs):
        registered.append({"message": message, "context": context, **kwargs})
        return {
            "key": f"video_edit:{kwargs['job_id']}",
            "product_type": kwargs["product_type"],
            "job_id": kwargs["job_id"],
            "user_id": kwargs["user_id"],
            "chat_id": message.chat_id,
            "message_id": message.message_id,
        }

    def snapshot(job_id, user_id=0, job=None, lang="vi"):
        assert int(job_id) == 71
        assert int(user_id) == 9
        assert job["id"] == 71
        value = {
            "product_type": "video_edit",
            "job_id": "71",
            "stage": "received",
            "percent": 10,
            "terminal_state": "",
            "text": status_text(job, lang),
            "render_hash": "same-rendered-snapshot",
        }
        snapshots.append(value)
        return value

    def read_status(job_id, user_id=0):
        reads.append((int(job_id), int(user_id)))
        return {
            "id": 71,
            "job_type": video_editengine1.WORKER_JOB_TYPE,
            "user_id": "9",
            "status": "queued",
            "_video_edit_canonical": {"local_worker_job_id": 71},
        }

    ns = _compile_functions(
        ["show_video_editor_job_status_panel"],
        {
            "safe_int": lambda value, default=0: int(value or default),
            "video_edit_progress_read_status": read_status,
            "video_edit_progress_snapshot": snapshot,
            "video_editor_job_status_text": status_text,
            "video_editor_status_keyboard": lambda job_id, _lang: f"videoedit|status|{job_id}",
            "safe_edit_or_send": lambda query, text, **kwargs: query.edit_message_text(text, **kwargs),
            "progress_auto_refresh_register_message": register,
        },
    )

    update = SimpleNamespace(
        callback_query=Query(),
        message=None,
        effective_user=SimpleNamespace(id=9),
    )
    context = SimpleNamespace()
    asyncio.run(ns["show_video_editor_job_status_panel"](update, context, 71, "vi", user_id=9))

    assert reads == [(71, 9)]
    assert len(snapshots) == 1
    assert len(rendered) == 1
    panel = rendered[0]
    assert panel["reply_markup"] == "videoedit|status|71"
    for label in (
        "Nhận video",
        "Kiểm tra cấu hình",
        "Chuẩn bị file",
        "Chỉnh sửa video",
        "Kiểm tra MP4",
        "Gửi kết quả",
    ):
        assert label in panel["text"]
    assert registered == [
        {
            "message": update.callback_query.message,
            "context": context,
            "product_type": "video_edit",
            "job_id": "71",
            "user_id": 9,
            "lang": "vi",
            "initial_snapshot": snapshots[0],
        }
    ]


@pytest.mark.parametrize(
    "registration",
    [
        {},
        {
            "key": "video_edit:71",
            "product_type": "video_edit",
            "job_id": "71",
            "user_id": 9,
            "chat_id": 99001,
            "message_id": 7999,
        },
    ],
)
def test_job_bound_panel_rejects_missing_or_mismatched_exact_registration(
    registration: dict,
) -> None:
    class Message:
        chat_id = 99001
        message_id = 7002

    class Query:
        message = Message()

    async def render(_query, _text, **_kwargs):
        return Message()

    ns = _compile_functions(
        ["show_video_editor_job_status_panel"],
        {
            "safe_int": lambda value, default=0: int(value or default),
            "video_edit_progress_read_status": lambda *_args, **_kwargs: {
                "id": 71,
                "job_type": video_editengine1.WORKER_JOB_TYPE,
                "user_id": "9",
            },
            "video_edit_progress_snapshot": lambda *_args, **_kwargs: {
                "text": "exact job status",
            },
            "video_editor_job_status_text": lambda *_args: "exact job status",
            "video_editor_status_keyboard": lambda *_args: "keyboard",
            "safe_edit_or_send": render,
            "progress_auto_refresh_register_message": lambda *_args, **_kwargs: dict(
                registration
            ),
        },
    )
    update = SimpleNamespace(
        callback_query=Query(),
        message=None,
        effective_user=SimpleNamespace(id=9),
    )

    with pytest.raises(RuntimeError, match="videoedit_progress_panel_registration_failed"):
        asyncio.run(
            ns["show_video_editor_job_status_panel"](
                update,
                SimpleNamespace(),
                71,
                "vi",
                user_id=9,
            )
        )


def test_video_edit_is_not_added_to_generic_product_progress_specs() -> None:
    source = (ROOT / "services" / "product_progress_status.py").read_text(encoding="utf-8")
    assert '"video_edit": {' not in source


class _FailingMediaQuery:
    def __init__(self, data: str, user_id: int) -> None:
        self.data = data
        self.from_user = SimpleNamespace(id=user_id, first_name="Video Edit test")
        self.message = SimpleNamespace(chat_id=user_id, message_id=9001)

    async def answer(self, *_args, **_kwargs):
        return None


class _CallbackProbe:
    def __init__(self, data: str, user_id: int) -> None:
        self.data = data
        self.from_user = SimpleNamespace(id=user_id, first_name="Video Edit test")
        self.message = SimpleNamespace(chat_id=user_id, message_id=9002)
        self.answers: list[tuple[tuple, dict]] = []
        self.edits: list[tuple[tuple, dict]] = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))

    async def edit_message_text(self, *args, **kwargs):
        self.edits.append((args, kwargs))
        return SimpleNamespace(text=args[0] if args else "")


@pytest.mark.parametrize(
    "callback_data",
    ["create_media|quick_image", "create_media|image_tier_low"],
)
def test_image_handoff_commits_only_after_telegram_render(
    monkeypatch: pytest.MonkeyPatch,
    callback_data: str,
) -> None:
    user_id = 92_001 if callback_data.endswith("quick_image") else 92_002
    bot_namespace = __import__("bot")
    bot_namespace.clear_video_editor_pending(user_id)
    bot_namespace.clear_quick_image_flow(user_id)
    bot_namespace.clear_public_image_prompt_pending(user_id)
    original = bot_namespace.set_video_editor_pending(
        user_id,
        "review",
        edit_mode="manual_edit",
        current_screen="review",
        source_file_id="telegram-source",
        inspection_complete=True,
        entry_context="manual",
        entry_parent_callback="videoedit|manual",
        manual_edit_plan={"trim": {"start_ms": 0, "end_ms": 1_000}},
    )

    async def fail_render(*_args, **_kwargs):
        raise RuntimeError("videoedit_telegram_render_failed")

    monkeypatch.setattr(bot_namespace, "safe_edit_or_send", fail_render)
    query = _FailingMediaQuery(callback_data, user_id)
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=user_id),
    )
    context = SimpleNamespace(user_data={})
    try:
        with pytest.raises(RuntimeError, match="videoedit_telegram_render_failed"):
            asyncio.run(
                bot_namespace._handle_create_media_callback_impl(
                    update,
                    context,
                )
            )
        current = bot_namespace.get_video_editor_pending(user_id)
        assert bot_namespace.video_editor_state_snapshot(current) == bot_namespace.video_editor_state_snapshot(original)
        assert dict(bot_namespace.get_quick_image_flow(user_id) or {}) == {}
        assert dict(bot_namespace.get_public_image_prompt_pending(user_id) or {}) == {}
    finally:
        bot_namespace.clear_video_editor_pending(user_id)
        bot_namespace.clear_quick_image_flow(user_id)
        bot_namespace.clear_public_image_prompt_pending(user_id)


@pytest.mark.parametrize(
    "callback_data",
    ["create_media|quick_image", "create_media|image_tier_low"],
)
def test_image_handoff_never_clears_a_newer_video_editor_draft(
    monkeypatch: pytest.MonkeyPatch,
    callback_data: str,
) -> None:
    user_id = 92_011 if callback_data.endswith("quick_image") else 92_012
    bot_namespace = __import__("bot")
    bot_namespace.clear_video_editor_pending(user_id)
    bot_namespace.clear_quick_image_flow(user_id)
    bot_namespace.clear_public_image_prompt_pending(user_id)
    bot_namespace.set_video_editor_pending(
        user_id,
        "review",
        edit_mode="manual_edit",
        current_screen="review",
        source_file_id="old-source",
        inspection_complete=True,
        edit_session_id="old-edit-session",
        manual_edit_plan={"trim": {"start_ms": 0, "end_ms": 1_000}},
    )
    winner: dict[str, dict] = {}
    renders: list[str] = []

    async def render_then_publish_newer_draft(*_args, **kwargs):
        if "post_render" not in kwargs:
            renders.append("winner")
            return SimpleNamespace(chat_id=user_id, message_id=9_102)
        renders.append("handoff")
        winner["state"] = bot_namespace.set_video_editor_pending(
            user_id,
            "review",
            edit_mode="manual_edit",
            current_screen="review",
            source_file_id="newer-source",
            inspection_complete=True,
            edit_session_id="newer-edit-session",
            manual_edit_plan={"trim": {"start_ms": 500, "end_ms": 1_500}},
        )
        committed = kwargs["post_render"]()
        if asyncio.iscoroutine(committed):
            await committed
        return SimpleNamespace(chat_id=user_id, message_id=9_101)

    monkeypatch.setattr(
        bot_namespace,
        "safe_edit_or_send",
        render_then_publish_newer_draft,
    )
    query = _FailingMediaQuery(callback_data, user_id)
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=user_id),
    )
    try:
        asyncio.run(
            bot_namespace._handle_create_media_callback_impl(
                update,
                SimpleNamespace(user_data={}),
            )
        )
        current = bot_namespace.get_video_editor_pending(user_id)
        assert bot_namespace.video_editor_state_snapshot(
            current
        ) == bot_namespace.video_editor_state_snapshot(winner["state"])
        assert renders == ["handoff", "winner"]
    finally:
        bot_namespace.clear_video_editor_pending(user_id)
        bot_namespace.clear_quick_image_flow(user_id)
        bot_namespace.clear_public_image_prompt_pending(user_id)


@pytest.mark.parametrize(
    "callback_data",
    ["create_media|quick_image", "create_media|image_tier_low"],
)
def test_image_handoff_rerenders_the_hub_when_the_entry_draft_was_cleared(
    monkeypatch: pytest.MonkeyPatch,
    callback_data: str,
) -> None:
    user_id = 92_021 if callback_data.endswith("quick_image") else 92_022
    bot_namespace = __import__("bot")
    bot_namespace.clear_video_editor_pending(user_id)
    bot_namespace.clear_quick_image_flow(user_id)
    bot_namespace.clear_public_image_prompt_pending(user_id)
    bot_namespace.set_video_editor_pending(
        user_id,
        "review",
        edit_mode="manual_edit",
        current_screen="review",
        source_file_id="entry-source",
        inspection_complete=True,
        edit_session_id="entry-edit-session",
        manual_edit_plan={"trim": {"start_ms": 0, "end_ms": 1_000}},
    )
    renders: list[str] = []

    async def render_then_clear_entry_draft(*_args, **kwargs):
        if "post_render" not in kwargs:
            renders.append("winner")
            return SimpleNamespace(chat_id=user_id, message_id=9_202)
        renders.append("handoff")
        bot_namespace.clear_video_editor_pending(user_id)
        committed = kwargs["post_render"]()
        if asyncio.iscoroutine(committed):
            await committed
        return SimpleNamespace(chat_id=user_id, message_id=9_201)

    monkeypatch.setattr(
        bot_namespace,
        "safe_edit_or_send",
        render_then_clear_entry_draft,
    )
    query = _FailingMediaQuery(callback_data, user_id)
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=user_id),
    )
    try:
        asyncio.run(
            bot_namespace._handle_create_media_callback_impl(
                update,
                SimpleNamespace(user_data={}),
            )
        )
        assert bot_namespace.get_video_editor_pending(user_id) == {}
        assert dict(bot_namespace.get_quick_image_flow(user_id) or {}) == {}
        assert dict(bot_namespace.get_public_image_prompt_pending(user_id) or {}) == {}
        assert renders == ["handoff", "winner"]
    finally:
        bot_namespace.clear_video_editor_pending(user_id)
        bot_namespace.clear_quick_image_flow(user_id)
        bot_namespace.clear_public_image_prompt_pending(user_id)


@pytest.mark.parametrize(
    "callback_data",
    [
        "videoedit|status|71|extra",
        "videoedit|logo_entry|extra",
        "videoedit|watermark_entry|extra",
    ],
)
def test_malformed_videoedit_callbacks_fail_closed_before_state_or_render(
    monkeypatch: pytest.MonkeyPatch,
    callback_data: str,
) -> None:
    user_id = 92_100 + len(callback_data)
    bot_namespace = __import__("bot")
    bot_namespace.clear_video_editor_pending(user_id)
    original = bot_namespace.set_video_editor_pending(
        user_id,
        "review",
        edit_mode="manual_edit",
        current_screen="review",
        source_file_id="telegram-source",
        inspection_complete=True,
        entry_context="manual",
        entry_parent_callback="videoedit|manual",
        manual_edit_plan={"trim": {"start_ms": 0, "end_ms": 1_000}},
    )
    if callback_data.startswith("videoedit|status"):
        monkeypatch.setattr(
            bot_namespace,
            "video_edit_progress_read_status",
            lambda *_args, **_kwargs: {
                "id": 71,
                "job_type": bot_namespace.video_editengine1.WORKER_JOB_TYPE,
                "user_id": str(user_id),
            },
        )
    rendered: list[tuple[tuple, dict]] = []

    async def capture_render(*args, **kwargs):
        rendered.append((args, kwargs))
        return None

    monkeypatch.setattr(bot_namespace, "safe_edit_or_send", capture_render)
    query = _CallbackProbe(callback_data, user_id)
    try:
        asyncio.run(
            bot_namespace.handle_video_editor_callback(
                SimpleNamespace(callback_query=query),
                SimpleNamespace(user_data={}),
            )
        )
        current = bot_namespace.get_video_editor_pending(user_id)
        assert rendered == []
        assert bot_namespace.video_editor_state_snapshot(current) == bot_namespace.video_editor_state_snapshot(original)
        assert query.answers and query.answers[-1][1].get("show_alert") is True
    finally:
        bot_namespace.clear_video_editor_pending(user_id)


def test_split_reset_callback_arity_preserves_the_signed_destructive_confirmation() -> None:
    bot_namespace = __import__("bot")
    validator = bot_namespace.video_editor_callback_arity_valid

    assert validator(["videoedit", "split_reset_manual", "signed-token"]) is True
    assert validator(["videoedit", "split_reset_manual"]) is False
    assert validator(
        ["videoedit", "split_reset_manual", "signed-token", "extra"]
    ) is False


def test_every_public_video_editor_menu_callback_passes_the_arity_gate() -> None:
    bot_namespace = __import__("bot")

    callbacks = {
        button.callback_data
        for row in bot_namespace.video_editor_menu_keyboard("vi").inline_keyboard
        for button in row
        if str(button.callback_data or "").startswith("videoedit|")
    }

    assert "videoedit|crop" in callbacks
    assert callbacks
    assert {
        callback
        for callback in callbacks
        if not bot_namespace.video_editor_callback_arity_valid(callback.split("|"))
    } == set()


def test_every_core_video_edit_keyboard_emits_callbacks_accepted_by_the_arity_gate() -> None:
    bot_namespace = __import__("bot")
    state = {
        "source_file_id": "telegram-source",
        "source_metadata": {
            "duration": 10,
            "duration_ms": 10_000,
            "has_audio": True,
            "width": 1920,
            "height": 1080,
        },
        "source_duration_ms": 10_000,
        "edit_mode": "manual_edit",
        "entry_parent_callback": "videoedit|manual",
        "parent_callback": "videoedit|cut",
        "return_to": "workspace",
        "current_screen": "workspace",
        "review_revision": 1,
        "edit_session_id": "keyboard-contract-session",
        "selected_effect": "enhance_basic_sharpen",
        "preserve_controls": {},
        "ai_suggestions": [{"title": "Làm sáng"}],
        "split_ranges": [{"start_ms": 0, "end_ms": 5_000}],
    }
    keyboards = [
        bot_namespace.video_edit_hub_keyboard("vi"),
        bot_namespace.video_edit_info_keyboard("vi"),
        bot_namespace.video_edit_guide_keyboard("vi"),
        bot_namespace.video_edit_lane_upload_keyboard("manual_edit", "vi"),
        bot_namespace.video_edit_legacy_redirect_keyboard("aspect", "vi"),
        bot_namespace.video_edit_audio_keyboard(state, "vi"),
        bot_namespace.video_edit_audio_component_keyboard("vi"),
        bot_namespace.video_edit_audio_master_keyboard("vi"),
        bot_namespace.video_edit_effects_keyboard("vi", state=state, runtime={}),
        bot_namespace.video_edit_restore_keyboard("vi"),
        bot_namespace.video_quality_enhance_source_keyboard("vi", state, runtime={}),
        bot_namespace.video_edit_plan_keyboard(state, "vi"),
        bot_namespace.video_ai_edit_intro_keyboard("vi"),
        bot_namespace.video_ai_edit_upload_keyboard("vi"),
        bot_namespace.video_ai_edit_source_summary_keyboard("vi", state),
        bot_namespace.video_ai_edit_intent_keyboard("vi", state),
        bot_namespace.video_ai_edit_suggestions_keyboard(state, "vi"),
        bot_namespace.video_ai_edit_settings_keyboard("vi", state),
        bot_namespace.video_ai_edit_intensity_keyboard("vi"),
        bot_namespace.video_ai_edit_preserve_keyboard(state, "vi"),
        bot_namespace.video_ai_edit_aspect_keyboard("vi"),
        bot_namespace.video_ai_edit_aspect_method_keyboard("vi"),
        bot_namespace.video_ai_edit_effect_timing_keyboard("vi"),
        bot_namespace.video_ai_edit_duration_keyboard(state, "vi"),
        bot_namespace.video_ai_edit_text_keyboard("vi"),
        bot_namespace.video_ai_edit_motion_keyboard("vi"),
        bot_namespace.video_ai_edit_prompt_keyboard("vi"),
        bot_namespace.video_ai_edit_invoice_keyboard({"ready": True}, "vi"),
        bot_namespace.video_ai_edit_invoice_keyboard({"ready": False}, "vi"),
        bot_namespace.video_ai_edit_status_keyboard(71, "vi"),
        bot_namespace.video_local_tool_keyboard("manual", "vi"),
        bot_namespace.video_local_upload_keyboard("manual", "vi"),
        bot_namespace.video_local_source_summary_keyboard("manual", "vi", state),
        bot_namespace.video_local_manual_options_keyboard("vi", state),
        bot_namespace.video_local_frame_keyboard("vi"),
        bot_namespace.video_local_transform_keyboard("vi"),
        bot_namespace.video_local_color_keyboard("vi"),
        bot_namespace.video_local_overlay_keyboard("vi"),
        bot_namespace.video_local_brightness_keyboard("vi"),
        bot_namespace.video_local_cut_options_keyboard("vi"),
        bot_namespace.video_local_join_options_keyboard("vi"),
        bot_namespace.video_local_rotate_flip_keyboard("vi"),
        bot_namespace.video_local_split_options_keyboard(state, "vi"),
        *[
            bot_namespace.video_local_choice_keyboard(kind, "vi")
            for kind in (
                "aspect",
                "resolution",
                "rotation",
                "flip",
                "speed",
                "volume",
                "color_preset",
            )
        ],
        bot_namespace.video_local_input_keyboard("manual", "vi"),
        bot_namespace.video_local_custom_input_keyboard(False, "vi"),
        bot_namespace.video_local_concat_keyboard("vi"),
        bot_namespace.video_local_logo_keyboard("vi"),
        bot_namespace.video_local_branding_keyboard("vi"),
        bot_namespace.video_local_watermark_keyboard("vi"),
        bot_namespace.video_local_review_keyboard("manual", "vi", state),
        bot_namespace.video_local_confirmation_keyboard("manual", "vi", state),
        bot_namespace.video_editor_guard_keyboard("vi"),
        bot_namespace.video_editor_menu_keyboard("vi"),
        bot_namespace.video_editor_preset_keyboard("vi"),
        bot_namespace.video_editor_ratio_keyboard("vi"),
        bot_namespace.video_editor_ratio_method_keyboard("vi"),
        bot_namespace.video_editor_status_keyboard(71, "vi"),
        bot_namespace.video_editor_latest_status_fallback_keyboard("vi"),
    ]
    callbacks = {
        str(button.callback_data or "")
        for keyboard in keyboards
        for row in keyboard.inline_keyboard
        for button in row
        if str(button.callback_data or "").startswith("videoedit|")
    }

    invalid = {
        callback
        for callback in callbacks
        if not bot_namespace.video_editor_callback_arity_valid(callback.split("|"))
    }

    assert callbacks
    assert invalid == set()


def test_video_edit_status_without_an_exact_registry_binding_fails_closed_after_restart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot_namespace = __import__("bot")
    user_id = 92_151
    job_id = 71
    key = bot_namespace.progress_auto_refresh_key("video_edit", str(job_id))
    bot_namespace.PROGRESS_AUTO_REFRESH_JOBS.pop(key, None)
    monkeypatch.setattr(
        bot_namespace,
        "video_edit_progress_read_status",
        lambda *_args, **_kwargs: {
            "id": job_id,
            "job_type": bot_namespace.video_editengine1.WORKER_JOB_TYPE,
            "user_id": str(user_id),
        },
    )
    monkeypatch.setattr(
        bot_namespace,
        "video_editor_job_status_text",
        lambda *_args: "forwarded status must not render",
    )
    query = _CallbackProbe(f"videoedit|status|{job_id}", user_id)
    query.message.chat_id = user_id + 99
    query.message.message_id = 8_888

    asyncio.run(
        bot_namespace.handle_video_editor_callback(
            SimpleNamespace(callback_query=query),
            SimpleNamespace(user_data={}),
        )
    )

    assert query.edits == []
    assert query.answers and query.answers[-1][1].get("show_alert") is True
    assert key not in bot_namespace.PROGRESS_AUTO_REFRESH_JOBS


def test_submit_panel_reuses_the_exact_registered_job_panel_without_creating_a_duplicate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot_namespace = __import__("bot")
    user_id = 92_181
    job_id = 71
    key = bot_namespace.progress_auto_refresh_key("video_edit", str(job_id))
    original_record = {
        "key": key,
        "product_type": "video_edit",
        "job_id": str(job_id),
        "user_id": user_id,
        "chat_id": user_id,
        "message_id": 7_001,
    }
    bot_namespace.PROGRESS_AUTO_REFRESH_JOBS[key] = dict(original_record)
    monkeypatch.setattr(
        bot_namespace,
        "video_edit_progress_read_status",
        lambda *_args, **_kwargs: {
            "id": job_id,
            "job_type": bot_namespace.video_editengine1.WORKER_JOB_TYPE,
            "user_id": str(user_id),
        },
    )
    monkeypatch.setattr(
        bot_namespace,
        "video_edit_progress_snapshot",
        lambda *_args, **_kwargs: {"text": "existing status panel"},
    )
    monkeypatch.setattr(
        bot_namespace,
        "video_editor_job_status_text",
        lambda *_args: "existing status panel",
    )
    rendered: list[tuple[tuple, dict]] = []
    registered: list[tuple[tuple, dict]] = []

    async def capture_render(*args, **kwargs):
        rendered.append((args, kwargs))
        return SimpleNamespace(chat_id=user_id, message_id=8_001)

    def capture_register(*args, **kwargs):
        registered.append((args, kwargs))
        return {}

    monkeypatch.setattr(bot_namespace, "safe_edit_or_send", capture_render)
    monkeypatch.setattr(
        bot_namespace,
        "progress_auto_refresh_register_message",
        capture_register,
    )
    query = _CallbackProbe("videoedit|confirm_local|signed-token", user_id)
    update = SimpleNamespace(
        callback_query=query,
        message=None,
        effective_user=SimpleNamespace(id=user_id),
    )
    try:
        assert asyncio.run(
            bot_namespace.show_video_editor_job_status_panel(
                update,
                SimpleNamespace(user_data={}),
                job_id,
                "vi",
                user_id=user_id,
            )
        ) is None
        assert rendered == []
        assert registered == []
        assert query.answers and query.answers[-1][1].get("show_alert") is True
        assert bot_namespace.PROGRESS_AUTO_REFRESH_JOBS[key] == original_record
    finally:
        bot_namespace.PROGRESS_AUTO_REFRESH_JOBS.pop(key, None)


@pytest.mark.parametrize("action", ["status_hub", "status_menu"])
def test_job_panel_navigation_clears_the_committed_editor_draft(
    monkeypatch: pytest.MonkeyPatch,
    action: str,
) -> None:
    bot_namespace = __import__("bot")
    user_id = 92_401 + (1 if action == "status_menu" else 0)
    job_id = 71
    key = bot_namespace.progress_auto_refresh_key("video_edit", str(job_id))
    bot_namespace.PROGRESS_AUTO_REFRESH_JOBS[key] = {
        "key": key,
        "product_type": "video_edit",
        "job_id": str(job_id),
        "user_id": user_id,
        "chat_id": user_id,
        "message_id": 7_001,
    }
    bot_namespace.set_video_editor_pending(
        user_id,
        "job_status",
        current_screen="job_status",
        source_file_id="old-source",
        inspection_complete=True,
        job_id=job_id,
    )
    monkeypatch.setattr(
        bot_namespace,
        "video_edit_progress_read_status",
        lambda *_args, **_kwargs: {
            "id": job_id,
            "job_type": bot_namespace.video_editengine1.WORKER_JOB_TYPE,
            "user_id": str(user_id),
        },
    )
    monkeypatch.setattr(bot_namespace, "localized_start_menu_text", lambda *_args: "main menu")
    monkeypatch.setattr(bot_namespace, "localized_main_menu_keyboard", lambda *_args: "main keyboard")

    class PanelMessage:
        chat_id = user_id
        message_id = 7_001

        async def reply_text(self, *_args, **_kwargs):
            return SimpleNamespace(chat_id=self.chat_id, message_id=8_001)

    query = _CallbackProbe(f"videoedit|{action}|{job_id}", user_id)
    query.message = PanelMessage()
    try:
        asyncio.run(
            bot_namespace.handle_video_editor_callback(
                SimpleNamespace(callback_query=query),
                SimpleNamespace(user_data={}),
            )
        )
        assert bot_namespace.get_video_editor_pending(user_id) == {}
    finally:
        bot_namespace.PROGRESS_AUTO_REFRESH_JOBS.pop(key, None)
        bot_namespace.clear_video_editor_pending(user_id)


@pytest.mark.parametrize("action", ["status_hub", "status_menu"])
def test_old_job_panel_navigation_never_clears_a_newer_editor_draft(
    monkeypatch: pytest.MonkeyPatch,
    action: str,
) -> None:
    bot_namespace = __import__("bot")
    user_id = 92_421 + (1 if action == "status_menu" else 0)
    old_job_id = 71
    key = bot_namespace.progress_auto_refresh_key(
        "video_edit",
        str(old_job_id),
    )
    bot_namespace.PROGRESS_AUTO_REFRESH_JOBS[key] = {
        "key": key,
        "product_type": "video_edit",
        "job_id": str(old_job_id),
        "user_id": user_id,
        "chat_id": user_id,
        "message_id": 7_101,
    }
    newer = bot_namespace.set_video_editor_pending(
        user_id,
        "review",
        current_screen="review",
        source_file_id="newer-source",
        inspection_complete=True,
        edit_session_id="newer-edit-session",
        job_id=72,
        manual_edit_plan={"trim": {"start_ms": 500, "end_ms": 1_500}},
    )
    monkeypatch.setattr(
        bot_namespace,
        "video_edit_progress_read_status",
        lambda *_args, **_kwargs: {
            "id": old_job_id,
            "job_type": bot_namespace.video_editengine1.WORKER_JOB_TYPE,
            "user_id": str(user_id),
        },
    )
    monkeypatch.setattr(
        bot_namespace,
        "localized_start_menu_text",
        lambda *_args: "main menu",
    )
    monkeypatch.setattr(
        bot_namespace,
        "localized_main_menu_keyboard",
        lambda *_args: "main keyboard",
    )
    rendered: list[tuple[tuple, dict]] = []

    class PanelMessage:
        chat_id = user_id
        message_id = 7_101

        async def reply_text(self, *args, **kwargs):
            rendered.append((args, kwargs))
            return SimpleNamespace(chat_id=self.chat_id, message_id=8_101)

    query = _CallbackProbe(
        f"videoedit|{action}|{old_job_id}",
        user_id,
    )
    query.message = PanelMessage()
    try:
        asyncio.run(
            bot_namespace.handle_video_editor_callback(
                SimpleNamespace(callback_query=query),
                SimpleNamespace(user_data={}),
            )
        )
        current = bot_namespace.get_video_editor_pending(user_id)
        assert bot_namespace.video_editor_state_snapshot(
            current
        ) == bot_namespace.video_editor_state_snapshot(newer)
        assert rendered == []
        assert query.answers and query.answers[-1][1].get("show_alert") is True
    finally:
        bot_namespace.PROGRESS_AUTO_REFRESH_JOBS.pop(key, None)
        bot_namespace.clear_video_editor_pending(user_id)


@pytest.mark.parametrize("action", ["status_hub", "status_menu"])
def test_job_panel_navigation_rejects_a_state_winner_before_render(
    monkeypatch: pytest.MonkeyPatch,
    action: str,
) -> None:
    bot_namespace = __import__("bot")
    user_id = 92_431 + (1 if action == "status_menu" else 0)
    old_job_id = 71
    key = bot_namespace.progress_auto_refresh_key(
        "video_edit",
        str(old_job_id),
    )
    bot_namespace.PROGRESS_AUTO_REFRESH_JOBS[key] = {
        "key": key,
        "product_type": "video_edit",
        "job_id": str(old_job_id),
        "user_id": user_id,
        "chat_id": user_id,
        "message_id": 7_111,
    }
    bot_namespace.set_video_editor_pending(
        user_id,
        "job_status",
        current_screen="job_status",
        source_file_id="old-source",
        inspection_complete=True,
        job_id=old_job_id,
    )
    winner: dict[str, dict] = {}

    def read_status_and_publish_winner(*_args, **_kwargs):
        winner["state"] = bot_namespace.set_video_editor_pending(
            user_id,
            "review",
            current_screen="review",
            source_file_id="newer-source",
            inspection_complete=True,
            edit_session_id="newer-edit-session",
            job_id=72,
            manual_edit_plan={"trim": {"start_ms": 500, "end_ms": 1_500}},
        )
        return {
            "id": old_job_id,
            "job_type": bot_namespace.video_editengine1.WORKER_JOB_TYPE,
            "user_id": str(user_id),
        }

    monkeypatch.setattr(
        bot_namespace,
        "video_edit_progress_read_status",
        read_status_and_publish_winner,
    )
    monkeypatch.setattr(
        bot_namespace,
        "localized_start_menu_text",
        lambda *_args: "main menu",
    )
    monkeypatch.setattr(
        bot_namespace,
        "localized_main_menu_keyboard",
        lambda *_args: "main keyboard",
    )
    rendered: list[tuple[tuple, dict]] = []

    class PanelMessage:
        chat_id = user_id
        message_id = 7_111

        async def reply_text(self, *args, **kwargs):
            rendered.append((args, kwargs))
            return SimpleNamespace(chat_id=self.chat_id, message_id=8_111)

    query = _CallbackProbe(
        f"videoedit|{action}|{old_job_id}",
        user_id,
    )
    query.message = PanelMessage()
    try:
        asyncio.run(
            bot_namespace.handle_video_editor_callback(
                SimpleNamespace(callback_query=query),
                SimpleNamespace(user_data={}),
            )
        )
        current = bot_namespace.get_video_editor_pending(user_id)
        assert bot_namespace.video_editor_state_snapshot(
            current
        ) == bot_namespace.video_editor_state_snapshot(winner["state"])
        assert rendered == []
        assert query.edits == []
        assert query.answers and query.answers[-1][1].get("show_alert") is True
    finally:
        bot_namespace.PROGRESS_AUTO_REFRESH_JOBS.pop(key, None)
        bot_namespace.clear_video_editor_pending(user_id)


@pytest.mark.parametrize("action", ["status_hub", "status_menu"])
def test_job_panel_navigation_restores_state_when_new_message_render_fails(
    monkeypatch: pytest.MonkeyPatch,
    action: str,
) -> None:
    bot_namespace = __import__("bot")
    user_id = 92_441 + (1 if action == "status_menu" else 0)
    job_id = 71
    key = bot_namespace.progress_auto_refresh_key("video_edit", str(job_id))
    bot_namespace.PROGRESS_AUTO_REFRESH_JOBS[key] = {
        "key": key,
        "product_type": "video_edit",
        "job_id": str(job_id),
        "user_id": user_id,
        "chat_id": user_id,
        "message_id": 7_121,
    }
    original = bot_namespace.set_video_editor_pending(
        user_id,
        "job_status",
        current_screen="job_status",
        source_file_id="source-for-rollback",
        inspection_complete=True,
        job_id=job_id,
    )
    monkeypatch.setattr(
        bot_namespace,
        "video_edit_progress_read_status",
        lambda *_args, **_kwargs: {
            "id": job_id,
            "job_type": bot_namespace.video_editengine1.WORKER_JOB_TYPE,
            "user_id": str(user_id),
        },
    )
    monkeypatch.setattr(
        bot_namespace,
        "localized_start_menu_text",
        lambda *_args: "main menu",
    )
    monkeypatch.setattr(
        bot_namespace,
        "localized_main_menu_keyboard",
        lambda *_args: "main keyboard",
    )

    class PanelMessage:
        chat_id = user_id
        message_id = 7_121

        async def reply_text(self, *_args, **_kwargs):
            raise RuntimeError("telegram new-message render failed")

    query = _CallbackProbe(f"videoedit|{action}|{job_id}", user_id)
    query.message = PanelMessage()
    try:
        asyncio.run(
            bot_namespace.handle_video_editor_callback(
                SimpleNamespace(callback_query=query),
                SimpleNamespace(user_data={}),
            )
        )
        current = bot_namespace.get_video_editor_pending(user_id)
        assert bot_namespace.video_editor_state_snapshot(
            current
        ) == bot_namespace.video_editor_state_snapshot(original)
        assert query.answers and query.answers[-1][1].get("show_alert") is True
    finally:
        bot_namespace.PROGRESS_AUTO_REFRESH_JOBS.pop(key, None)
        bot_namespace.clear_video_editor_pending(user_id)


def test_video_editor_guide_rejects_an_unknown_caller_without_rendering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot_namespace = __import__("bot")
    user_id = 92_451
    rendered: list[tuple[tuple, dict]] = []

    async def capture_render(*args, **kwargs):
        rendered.append((args, kwargs))
        return None

    monkeypatch.setattr(bot_namespace, "safe_edit_or_send", capture_render)
    query = _CallbackProbe("videoedit|guide|forged", user_id)
    asyncio.run(
        bot_namespace.handle_video_editor_callback(
            SimpleNamespace(callback_query=query),
            SimpleNamespace(user_data={}),
        )
    )

    assert rendered == []
    assert query.answers and query.answers[-1][1].get("show_alert") is True


def test_video_edit_status_callback_requires_exact_registered_chat_and_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot_namespace = __import__("bot")
    user_id = 92_201
    key = bot_namespace.progress_auto_refresh_key("video_edit", "71")
    bot_namespace.PROGRESS_AUTO_REFRESH_JOBS[key] = {
        "key": key,
        "product_type": "video_edit",
        "job_id": "71",
        "user_id": user_id,
        "chat_id": user_id,
        "message_id": 7001,
    }
    monkeypatch.setattr(
        bot_namespace,
        "video_edit_progress_read_status",
        lambda *_args, **_kwargs: {
            "id": 71,
            "job_type": bot_namespace.video_editengine1.WORKER_JOB_TYPE,
            "user_id": str(user_id),
        },
    )
    monkeypatch.setattr(bot_namespace, "video_editor_job_status_text", lambda *_args: "status")
    rendered: list[tuple[tuple, dict]] = []

    async def capture_render(*args, **kwargs):
        rendered.append((args, kwargs))
        return None

    monkeypatch.setattr(bot_namespace, "safe_edit_or_send", capture_render)
    query = _CallbackProbe("videoedit|status|71", user_id)
    query.message.message_id = 7002
    try:
        asyncio.run(
            bot_namespace.handle_video_editor_callback(
                SimpleNamespace(callback_query=query),
                SimpleNamespace(user_data={}),
            )
        )
        assert rendered == []
        assert query.edits == []
        assert query.answers and query.answers[-1][1].get("show_alert") is True
    finally:
        bot_namespace.PROGRESS_AUTO_REFRESH_JOBS.pop(key, None)


def test_video_edit_exact_status_edit_failure_never_fallback_sends_a_second_panel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot_namespace = __import__("bot")
    user_id = 92_251
    key = bot_namespace.progress_auto_refresh_key("video_edit", "71")
    original_record = {
        "key": key,
        "product_type": "video_edit",
        "job_id": "71",
        "user_id": user_id,
        "chat_id": user_id,
        "message_id": 7001,
        "last_stage": "processing_video",
        "last_percent": 60,
        "last_render_hash": "known-good",
    }
    bot_namespace.PROGRESS_AUTO_REFRESH_JOBS[key] = dict(original_record)
    monkeypatch.setattr(
        bot_namespace,
        "video_edit_progress_read_status",
        lambda *_args, **_kwargs: {
            "id": 71,
            "job_type": bot_namespace.video_editengine1.WORKER_JOB_TYPE,
            "user_id": str(user_id),
        },
    )
    monkeypatch.setattr(
        bot_namespace,
        "video_editor_job_status_text",
        lambda *_args: "bound status panel",
    )
    fallback_calls: list[tuple[tuple, dict]] = []

    async def forbidden_fallback(*args, **kwargs):
        fallback_calls.append((args, kwargs))
        return None

    monkeypatch.setattr(bot_namespace, "safe_edit_or_send", forbidden_fallback)
    query = _CallbackProbe("videoedit|status|71", user_id)
    query.message.message_id = 7001

    async def fail_exact_edit(*_args, **_kwargs):
        raise RuntimeError("telegram exact edit failed")

    query.edit_message_text = fail_exact_edit
    try:
        assert asyncio.run(
            bot_namespace.handle_video_editor_callback(
                SimpleNamespace(callback_query=query),
                SimpleNamespace(user_data={}),
            )
        ) is True
        assert fallback_calls == []
        assert query.edits == []
        assert query.answers and query.answers[-1][1].get("show_alert") is True
        assert "không tạo bảng mới" in query.answers[-1][0][0]
        assert bot_namespace.PROGRESS_AUTO_REFRESH_JOBS[key] == original_record
    finally:
        bot_namespace.PROGRESS_AUTO_REFRESH_JOBS.pop(key, None)


def test_video_edit_message_not_modified_refresh_restores_the_exact_scheduler_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot_namespace = __import__("bot")
    user_id = 92_271
    key = bot_namespace.progress_auto_refresh_key("video_edit", "71")
    bot_namespace.PROGRESS_AUTO_REFRESH_JOBS.pop(key, None)
    job = {
        "id": 71,
        "job_type": bot_namespace.video_editengine1.WORKER_JOB_TYPE,
        "user_id": str(user_id),
    }
    snapshot = {
        "stage": "processing_video",
        "percent": 60,
        "terminal_state": "",
        "text": "same status panel",
        "render_hash": "same-status-hash",
    }
    registrations: list[tuple[object, object, dict]] = []

    monkeypatch.setattr(
        bot_namespace,
        "video_edit_progress_read_status",
        lambda *_args, **_kwargs: dict(job),
    )
    monkeypatch.setattr(
        bot_namespace,
        "video_editor_job_status_text",
        lambda *_args: "same status panel",
    )
    monkeypatch.setattr(
        bot_namespace,
        "video_edit_progress_snapshot",
        lambda *_args, **_kwargs: dict(snapshot),
    )

    def capture_registration(message, context, **kwargs):
        registrations.append((message, context, kwargs))
        return {"key": key, **kwargs}

    monkeypatch.setattr(
        bot_namespace,
        "progress_auto_refresh_register_message",
        capture_registration,
    )
    query = _CallbackProbe("videoedit|status|71", user_id)

    async def unchanged_edit(*_args, **_kwargs):
        raise RuntimeError("BadRequest: message is not modified")

    query.edit_message_text = unchanged_edit
    context = SimpleNamespace(user_data={})
    try:
        assert asyncio.run(
            bot_namespace.handle_video_editor_callback(
                SimpleNamespace(callback_query=query),
                context,
            )
        ) is True
        assert len(registrations) == 1
        message, registered_context, kwargs = registrations[0]
        assert message is query.message
        assert registered_context is context
        assert kwargs["product_type"] == "video_edit"
        assert kwargs["job_id"] == "71"
        assert kwargs["user_id"] == user_id
        assert kwargs["initial_snapshot"] == snapshot
        assert query.answers == [((), {})]
    finally:
        bot_namespace.PROGRESS_AUTO_REFRESH_JOBS.pop(key, None)


@pytest.mark.parametrize(
    ("terminal_state", "expected_registrations"),
    [("", 1), ("delivered", 0)],
)
def test_video_edit_status_restart_recovery_only_rebinds_a_nonterminal_exact_job(
    monkeypatch: pytest.MonkeyPatch,
    terminal_state: str,
    expected_registrations: int,
) -> None:
    bot_namespace = __import__("bot")
    user_id = 92_281 + (1 if terminal_state else 0)
    key = bot_namespace.progress_auto_refresh_key("video_edit", "71")
    bot_namespace.PROGRESS_AUTO_REFRESH_JOBS[key] = {
        "key": key,
        "product_type": "video_edit",
        "job_id": "71",
        "chat_id": user_id,
        "message_id": 9002,
        "user_id": user_id,
        "lang": "vi",
        "stopped": True,
        "task_alive": False,
        "stop_reason": "auto_tick_exception",
    }
    job = {
        "id": 71,
        "job_type": bot_namespace.video_editengine1.WORKER_JOB_TYPE,
        "user_id": str(user_id),
    }
    snapshot = {
        "stage": terminal_state or "processing_video",
        "percent": 100 if terminal_state else 60,
        "terminal_state": terminal_state,
        "text": terminal_state or "processing",
        "render_hash": terminal_state or "processing-hash",
    }
    registrations: list[tuple[object, object, dict]] = []
    monkeypatch.setattr(
        bot_namespace,
        "video_edit_progress_read_status",
        lambda *_args, **_kwargs: dict(job),
    )
    monkeypatch.setattr(
        bot_namespace,
        "video_editor_job_status_text",
        lambda *_args: str(snapshot["text"]),
    )
    monkeypatch.setattr(
        bot_namespace,
        "video_edit_progress_snapshot",
        lambda *_args, **_kwargs: dict(snapshot),
    )

    def capture_registration(message, context, **kwargs):
        registrations.append((message, context, kwargs))
        return {"key": key, **kwargs}

    monkeypatch.setattr(
        bot_namespace,
        "progress_auto_refresh_register_message",
        capture_registration,
    )
    query = _CallbackProbe("videoedit|status|71", user_id)
    context = SimpleNamespace(user_data={})
    try:
        assert asyncio.run(
            bot_namespace.handle_video_editor_callback(
                SimpleNamespace(callback_query=query),
                context,
            )
        ) is True
        assert len(registrations) == expected_registrations
        if registrations:
            message, registered_context, kwargs = registrations[0]
            assert message is query.message
            assert registered_context is context
            assert kwargs["job_id"] == "71"
            assert kwargs["user_id"] == user_id
            assert kwargs["initial_snapshot"] == snapshot
    finally:
        bot_namespace.PROGRESS_AUTO_REFRESH_JOBS.pop(key, None)


@pytest.mark.parametrize("action", ["status", "ai_status"])
def test_video_edit_public_status_never_grants_admin_cross_owner_bypass(
    monkeypatch: pytest.MonkeyPatch,
    action: str,
) -> None:
    bot_namespace = __import__("bot")
    admin_id = 92_301
    owner_id = 92_302
    calls: list[tuple[int, int]] = []
    rendered: list[tuple[tuple, dict]] = []

    def read_status(job_id, user_id=0):
        calls.append((int(job_id), int(user_id or 0)))
        if int(user_id or 0) != owner_id:
            return {}
        return {
            "id": 71,
            "job_type": bot_namespace.video_editengine1.WORKER_JOB_TYPE,
            "user_id": str(owner_id),
        }

    async def capture_render(*args, **kwargs):
        rendered.append((args, kwargs))
        return None

    monkeypatch.setattr(bot_namespace, "is_admin_user", lambda _user_id: True)
    monkeypatch.setattr(bot_namespace, "video_edit_progress_read_status", read_status)
    monkeypatch.setattr(bot_namespace, "safe_edit_or_send", capture_render)
    query = _CallbackProbe(f"videoedit|{action}|71", admin_id)
    asyncio.run(
        bot_namespace.handle_video_editor_callback(
            SimpleNamespace(callback_query=query),
            SimpleNamespace(user_data={}),
        )
    )

    assert calls == [(71, admin_id)]
    assert rendered == []
    assert query.edits == []
    assert query.answers and query.answers[-1][1].get("show_alert") is True


@pytest.mark.parametrize("action", ["status_hub", "status_menu"])
def test_video_edit_status_navigation_opens_new_message_and_preserves_live_panel(
    monkeypatch: pytest.MonkeyPatch,
    action: str,
) -> None:
    bot_namespace = __import__("bot")
    user_id = 92_401
    key = bot_namespace.progress_auto_refresh_key("video_edit", "71")
    original_record = {
        "key": key,
        "product_type": "video_edit",
        "job_id": "71",
        "user_id": user_id,
        "chat_id": user_id,
        "message_id": 7001,
        "last_stage": "processing_video",
        "last_percent": 60,
        "last_render_hash": "known-good",
    }
    bot_namespace.PROGRESS_AUTO_REFRESH_JOBS[key] = dict(original_record)
    monkeypatch.setattr(
        bot_namespace,
        "video_edit_progress_read_status",
        lambda *_args, **_kwargs: {
            "id": 71,
            "job_type": bot_namespace.video_editengine1.WORKER_JOB_TYPE,
            "user_id": str(user_id),
        },
    )
    monkeypatch.setattr(bot_namespace, "localized_start_menu_text", lambda *_args: "main menu")
    monkeypatch.setattr(bot_namespace, "localized_main_menu_keyboard", lambda *_args: "main keyboard")

    class PanelMessage:
        chat_id = user_id
        message_id = 7001

        def __init__(self) -> None:
            self.replies: list[tuple[str, dict]] = []

        async def reply_text(self, text, **kwargs):
            self.replies.append((str(text), kwargs))
            return SimpleNamespace(chat_id=self.chat_id, message_id=8001)

    query = _CallbackProbe(f"videoedit|{action}|71", user_id)
    query.message = PanelMessage()
    try:
        asyncio.run(
            bot_namespace.handle_video_editor_callback(
                SimpleNamespace(callback_query=query),
                SimpleNamespace(user_data={}),
            )
        )
        assert query.edits == []
        assert len(query.message.replies) == 1
        assert bot_namespace.PROGRESS_AUTO_REFRESH_JOBS[key] == original_record
    finally:
        bot_namespace.PROGRESS_AUTO_REFRESH_JOBS.pop(key, None)

    callbacks = {
        button.callback_data
        for row in bot_namespace.video_editor_status_keyboard(71, "vi").inline_keyboard
        for button in row
    }
    assert "videoedit|status_hub|71" in callbacks
    assert "videoedit|status_menu|71" in callbacks
    assert "videoedit|hub" not in callbacks
    assert "menu|main" not in callbacks


@pytest.mark.parametrize("action", ["status_hub", "status_menu"])
def test_video_edit_status_navigation_ack_failure_never_rolls_back_a_rendered_destination(
    monkeypatch: pytest.MonkeyPatch,
    action: str,
) -> None:
    bot_namespace = __import__("bot")
    user_id = 92_411 + (1 if action == "status_menu" else 0)
    job_id = 71
    key = bot_namespace.progress_auto_refresh_key("video_edit", str(job_id))
    original_record = {
        "key": key,
        "product_type": "video_edit",
        "job_id": str(job_id),
        "user_id": user_id,
        "chat_id": user_id,
        "message_id": 7_001,
        "last_stage": "processing_video",
        "last_percent": 60,
        "last_render_hash": "known-good",
    }
    bot_namespace.PROGRESS_AUTO_REFRESH_JOBS[key] = dict(original_record)
    bot_namespace.set_video_editor_pending(
        user_id,
        "job_status",
        current_screen="job_status",
        source_file_id="source-for-navigation",
        inspection_complete=True,
        job_id=job_id,
    )
    monkeypatch.setattr(
        bot_namespace,
        "video_edit_progress_read_status",
        lambda *_args, **_kwargs: {
            "id": job_id,
            "job_type": bot_namespace.video_editengine1.WORKER_JOB_TYPE,
            "user_id": str(user_id),
        },
    )
    monkeypatch.setattr(
        bot_namespace,
        "localized_start_menu_text",
        lambda *_args: "main menu",
    )
    monkeypatch.setattr(
        bot_namespace,
        "localized_main_menu_keyboard",
        lambda *_args: "main keyboard",
    )

    class PanelMessage:
        chat_id = user_id
        message_id = 7_001

        def __init__(self) -> None:
            self.replies: list[tuple[str, dict]] = []

        async def reply_text(self, text, **kwargs):
            self.replies.append((str(text), kwargs))
            return SimpleNamespace(chat_id=self.chat_id, message_id=8_001)

    query = _CallbackProbe(f"videoedit|{action}|{job_id}", user_id)
    query.message = PanelMessage()

    async def fail_acknowledgement(*_args, **_kwargs):
        raise RuntimeError("telegram callback acknowledgement failed")

    query.answer = fail_acknowledgement
    try:
        assert asyncio.run(
            bot_namespace.handle_video_editor_callback(
                SimpleNamespace(callback_query=query),
                SimpleNamespace(user_data={}),
            )
        ) is True
        assert len(query.message.replies) == 1
        assert bot_namespace.get_video_editor_pending(user_id) == {}
        assert bot_namespace.PROGRESS_AUTO_REFRESH_JOBS[key] == original_record
    finally:
        bot_namespace.PROGRESS_AUTO_REFRESH_JOBS.pop(key, None)
        bot_namespace.clear_video_editor_pending(user_id)
