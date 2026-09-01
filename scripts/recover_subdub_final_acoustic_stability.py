"""One-shot same-attempt runner for the Owner-confirmed SubDub acoustic repair."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from telegram import Bot

import bot as app


JOB_ID = "b4cb6d5fe8a7bdfce507"
OWNER_ID = 7_126_457_028
SOURCE_SHA256 = "83de97b744b931e544b569e6e750f8415545f226461bd2e36cfb49225898ad3e"


def claim_same_attempt() -> dict:
    key = app._engine_async_job_key(JOB_ID)
    conn = app.db_connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT value FROM system_settings WHERE key=? LIMIT 1", (key,)
        ).fetchone()
        if not row:
            conn.rollback()
            return {"ok": False, "claimed": False, "reason": "job_not_found"}
        old_value = str(row[0] or "")
        current = json.loads(old_value)
        recovery = current.get("auto_multi_recovery")
        false_fields = (
            "output_sent", "delivery_attempted", "artifact_started",
            "final_mp4_exists", "output_validated",
        )
        path_fields = (
            "final_mp4_path", "final_output_path", "output_path",
            "output_video_path", "final_video_path", "dub_video_path",
        )
        allowed = bool(
            type(current) is dict
            and type(recovery) is dict
            and str(current.get("internal_job_id") or current.get("job_id") or "") == JOB_ID
            and current.get("public_code") == "B4CB6D5FE8"
            and str(current.get("user_id") or "") == str(OWNER_ID)
            and str(current.get("chat_id") or current.get("user_id") or "") == str(OWNER_ID)
            and str(current.get("job_key") or "").endswith("|subtitle_plus_dub|auto_multi_speaker")
            and current.get("status") == "failed_no_charge"
            and current.get("terminal_state") == "failed_no_charge"
            and current.get("auto_multi_recovery_attempt_count") == 4
            and current.get("auto_multi_recovery_correction_attempt_count") == 3
            and current.get("auto_multi_acoustic_recovery_used") is True
            and current.get("auto_multi_acoustic_stability_repair_used") is not True
            and current.get("last_error_stage") == "AUTO_CAST_MANUAL_REQUIRED"
            and current.get("charged_xu") == 0
            and current.get("charge_status") == "not_charged"
            and all(field in current and current.get(field) is False for field in false_fields)
            and not any(str(current.get(field) or "").strip() for field in path_fields)
            and recovery.get("owner_confirmed_paid") is True
            and str(recovery.get("source_sha256") or "").lower() == SOURCE_SHA256
            and recovery.get("target_language") == "English"
            and recovery.get("original_volume_percent") == 40
            and recovery.get("dub_volume_percent") == 150
        )
        if not allowed:
            conn.rollback()
            return {"ok": False, "claimed": False, "reason": "stability_repair_not_allowed"}
        current.update({
            "status": app.SUBDUB_FAILED_AUTO_MULTI_RECOVERY_STATUS,
            "terminal_state": "",
            "lifecycle_state": app.SUBDUB_FAILED_AUTO_MULTI_RECOVERY_STATUS,
            "current_stage": app.SUBDUB_FAILED_AUTO_MULTI_RECOVERY_STATUS,
            "progress_stage": app.SUBDUB_FAILED_AUTO_MULTI_RECOVERY_STATUS,
            "progress_percent": 5,
            "last_error_stage": "",
            "last_error_safe": "",
            "auto_multi_acoustic_stability_repair_used": True,
            "auto_multi_acoustic_stability_repair_authority": "owner_confirmed_same_attempt",
            "updated_at": app.time.time(),
        })
        new_value = json.dumps(current, ensure_ascii=False, separators=(",", ":"))
        cursor = conn.execute(
            "UPDATE system_settings SET value=?,note=?,updated_at=?,updated_by=? WHERE key=? AND value=?",
            (new_value, "SubDub same-attempt acoustic stability repair", app.now_text(), str(OWNER_ID), key, old_value),
        )
        if int(cursor.rowcount or 0) != 1:
            conn.rollback()
            return {"ok": False, "claimed": False, "reason": "stability_repair_cas_lost"}
        conn.commit()
        app.ENGINE_ASYNC_MEMORY_JOBS[JOB_ID] = dict(current)
        app.SUBTITLE_DUB_PIPELINE_JOBS[str(current.get("job_key") or "")] = dict(current)
        return {"ok": True, "claimed": True, "job": dict(current)}
    finally:
        conn.close()


async def run() -> None:
    claim = claim_same_attempt()
    if not claim.get("claimed"):
        raise RuntimeError(str(claim.get("reason") or "stability_repair_failed"))
    async with Bot(token=app.TELEGRAM_TOKEN) as telegram_bot:
        async def reply_text(text, **kwargs):
            return await telegram_bot.send_message(chat_id=OWNER_ID, text=text, **kwargs)

        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=OWNER_ID),
            message=SimpleNamespace(chat_id=OWNER_ID, reply_text=reply_text),
        )
        context = SimpleNamespace(
            args=[JOB_ID, SOURCE_SHA256, "English", "40", "150", "--confirm-paid", "--confirm-local-acoustic"],
            bot=telegram_bot,
        )
        original_claim = app.claim_subdub_failed_auto_multi_recovery
        app.claim_subdub_failed_auto_multi_recovery = lambda *_a, **_k: claim
        try:
            await app.cmd_subdub_recover_failed_auto_multi(update, context)
        finally:
            app.claim_subdub_failed_auto_multi_recovery = original_claim


if __name__ == "__main__":
    asyncio.run(run())
