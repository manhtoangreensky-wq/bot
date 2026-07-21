import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import bot


class DummyMessage:
    def __init__(self):
        self.texts = []
        self.chat_id = 456

    async def reply_text(self, text, **kwargs):
        self.texts.append((text, kwargs))
        return SimpleNamespace()


class DummyQuery:
    def __init__(self, user_id=123, data="enginejob|music|MUS-STATUS"):
        self.from_user = SimpleNamespace(id=user_id)
        self.data = data
        self.message = DummyMessage()
        self.edits = []

    async def answer(self, *args, **kwargs):
        return None

    async def edit_message_text(self, text, **kwargs):
        self.edits.append((text, kwargs))
        return SimpleNamespace()


def _admin_update(user_id=123):
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        effective_chat=SimpleNamespace(id=456),
        message=DummyMessage(),
    )


def _completed_suno_job(job_id="MUS-STATUS", **overrides):
    job = {
        "feature": "music_suno",
        "internal_job_id": job_id,
        "status": "completed",
        "output_bytes": 999,
        "output_sha256": "sha-status",
        "provider": "key4u_suno",
        "provider_task_id": "raw-provider-task",
        "user_id": "123",
        "chat_id": "456",
        "send_attempt_count": 3,
    }
    job.update(overrides)
    return job


def _patch_music_job_store(monkeypatch, job):
    jobs = {str(job["internal_job_id"]): dict(job)}
    vault = {}
    monkeypatch.setattr(bot, "is_admin_user", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(bot, "get_engine_async_job", lambda job_id: dict(jobs.get(str(job_id), {})))
    monkeypatch.setattr(bot, "_music_vault_index", lambda: list(vault))
    monkeypatch.setattr(bot, "get_music_vault_entry", lambda vault_id: dict(vault.get(str(vault_id), {})))

    def save_vault(entry, updated_by=""):
        vault[str(entry["vault_id"])] = dict(entry)
        return dict(entry)

    def save_job(updated):
        jobs[str(updated["internal_job_id"])] = dict(updated)
        return dict(updated)

    monkeypatch.setattr(bot, "save_music_vault_entry", save_vault)
    monkeypatch.setattr(bot, "save_engine_async_job", save_job)

    async def no_provider_poll(*_args, **_kwargs):
        raise AssertionError("music_suno_job must not poll provider")

    monkeypatch.setattr(bot, "poll_music_suno_async_job", no_provider_poll)
    return jobs, vault


def _patch_preview_store(monkeypatch, tier="silver"):
    store = {}
    monkeypatch.setattr(bot, "is_admin_user", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(bot, "get_member_profile", lambda *_args, **_kwargs: {"tier": tier})
    monkeypatch.setattr(bot, "get_system_setting", lambda key, default="": store.get(key, default))
    monkeypatch.setattr(bot, "set_system_setting", lambda key, value, note="", updated_by="": store.__setitem__(key, value))
    return store


def test_vip_music_quota_title_claim_quota(monkeypatch):
    monkeypatch.setattr(bot, "is_admin_user", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(bot, "vip_music_vault_allowed", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(bot, "vip_music_quota_counts", lambda *_args, **_kwargs: {"day": 0, "daily_limit": 1, "month": 0, "monthly_limit": 10})
    update = _admin_update()

    asyncio.run(bot.cmd_vip_music_quota(update, SimpleNamespace(args=[])))
    text = update.message.texts[-1][0]

    assert "LƯỢT NHẬN NHẠC VIP TỪ KHO" in text
    assert "0/1</code> lượt" in text
    assert "0/10</code> lượt" in text


def test_vip_music_quota_mentions_not_storage_duration(monkeypatch):
    monkeypatch.setattr(bot, "is_admin_user", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(bot, "vip_music_vault_allowed", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(bot, "vip_music_quota_counts", lambda *_args, **_kwargs: {"day": 0, "daily_limit": 1, "month": 0, "monthly_limit": 10})
    update = _admin_update()

    asyncio.run(bot.cmd_vip_music_quota(update, SimpleNamespace(args=[])))
    text = update.message.texts[-1][0]

    assert "không phải thời hạn lưu nhạc" in text
    assert "kho nhạc AI có sẵn, không gọi provider" in text


def test_completed_music_job_upserts_vault_record(monkeypatch):
    saved = {}
    jobs = {}
    job = {
        "feature": "music_suno",
        "internal_job_id": "MUS-DONE",
        "status": "completed",
        "output_bytes": 1234,
        "output_sha256": "abc123",
        "provider": "key4u_suno",
        "provider_task_id": "raw-provider-task",
        "user_id": "42",
        "chat_id": "99",
    }

    monkeypatch.setattr(bot, "_music_vault_index", lambda: list(saved))
    monkeypatch.setattr(bot, "get_music_vault_entry", lambda vault_id: saved.get(vault_id, {}))
    monkeypatch.setattr(bot, "save_music_vault_entry", lambda entry, updated_by="": saved.setdefault(entry["vault_id"], dict(entry)))
    monkeypatch.setattr(bot, "save_engine_async_job", lambda updated: jobs.setdefault(updated["internal_job_id"], dict(updated)))

    entry = bot.upsert_music_vault_from_completed_job(job, updated_by="test")

    assert entry["vault_id"].startswith("MV-")
    assert entry["output_bytes"] == 1234
    assert entry["provider_task_id_present"] is True
    assert entry["source"] == "backfill"
    assert jobs["MUS-DONE"]["vault_id"] == entry["vault_id"]


def test_music_vault_backfill_idempotent_no_duplicates(monkeypatch):
    saved = {}
    job = {
        "feature": "music_suno",
        "internal_job_id": "MUS-IDEMP",
        "status": "completed",
        "output_bytes": 777,
        "provider": "key4u_suno",
        "provider_task_id": "raw-provider-task",
    }

    monkeypatch.setattr(bot, "list_engine_async_jobs", lambda *_args, **_kwargs: [job])
    monkeypatch.setattr(bot, "_music_vault_index", lambda: list(saved))
    monkeypatch.setattr(bot, "get_music_vault_entry", lambda vault_id: saved.get(vault_id, {}))

    def save(entry, updated_by=""):
        saved[entry["vault_id"]] = dict(entry)
        return dict(entry)

    monkeypatch.setattr(bot, "save_music_vault_entry", save)
    monkeypatch.setattr(bot, "save_engine_async_job", lambda updated: updated)

    bot.backfill_completed_music_vault_entries(updated_by="test")
    bot.backfill_completed_music_vault_entries(updated_by="test")

    assert len(saved) == 1


def test_music_suno_job_status_does_not_auto_send_audio(monkeypatch):
    monkeypatch.setattr(bot, "is_admin_user", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(bot, "get_engine_async_job", lambda *_args, **_kwargs: {
        "feature": "music_suno",
        "internal_job_id": "MUS-STATUS",
        "status": "completed",
        "output_bytes": 999,
        "provider": "key4u_suno",
    })
    monkeypatch.setattr(bot, "upsert_music_vault_from_completed_job", lambda *_args, **_kwargs: {"vault_id": "MV-STATUS"})
    monkeypatch.setattr(bot, "find_music_vault_entry_for_job", lambda *_args, **_kwargs: {"vault_id": "MV-STATUS"})
    update = _admin_update()
    context = SimpleNamespace(args=["MUS-STATUS"], bot=SimpleNamespace(send_audio=lambda *a, **k: (_ for _ in ()).throw(AssertionError("no send"))))

    asyncio.run(bot.cmd_music_suno_job(update, context))
    text = update.message.texts[-1][0]

    assert "Đã gửi bản nhạc phía trên" not in text
    assert "/music_suno_send" in text


def test_music_suno_job_completed_does_not_auto_send_audio(monkeypatch):
    job = _completed_suno_job()
    _patch_music_job_store(monkeypatch, job)

    class NoSendBot:
        async def send_audio(self, *args, **kwargs):
            raise AssertionError("music_suno_job must not send audio")

    update = _admin_update()
    asyncio.run(bot.cmd_music_suno_job(update, SimpleNamespace(args=["MUS-STATUS"], bot=NoSendBot())))

    assert "Job nhạc đã hoàn tất" in update.message.texts[-1][0]


def test_music_suno_job_no_sent_above_text(monkeypatch):
    job = _completed_suno_job()
    _patch_music_job_store(monkeypatch, job)
    update = _admin_update()

    asyncio.run(bot.cmd_music_suno_job(update, SimpleNamespace(args=["MUS-STATUS"], bot=SimpleNamespace())))

    assert "Đã gửi bản nhạc phía trên" not in update.message.texts[-1][0]


def test_music_suno_job_completed_shows_vault_id(monkeypatch):
    job = _completed_suno_job()
    _patch_music_job_store(monkeypatch, job)
    update = _admin_update()

    asyncio.run(bot.cmd_music_suno_job(update, SimpleNamespace(args=["MUS-STATUS"], bot=SimpleNamespace())))
    text = update.message.texts[-1][0]

    assert "• Vault: <code>MV-" in text
    assert "/music_vault_detail" in text


def test_music_suno_job_suggests_music_suno_send(monkeypatch):
    job = _completed_suno_job()
    _patch_music_job_store(monkeypatch, job)
    update = _admin_update()

    asyncio.run(bot.cmd_music_suno_job(update, SimpleNamespace(args=["MUS-STATUS"], bot=SimpleNamespace())))

    assert "/music_suno_send" in update.message.texts[-1][0]


def test_music_suno_job_does_not_increment_send_attempt_count(monkeypatch):
    job = _completed_suno_job(send_attempt_count=7)
    jobs, _vault = _patch_music_job_store(monkeypatch, job)
    update = _admin_update()

    asyncio.run(bot.cmd_music_suno_job(update, SimpleNamespace(args=["MUS-STATUS"], bot=SimpleNamespace())))

    assert jobs["MUS-STATUS"]["send_attempt_count"] == 7
    assert not jobs["MUS-STATUS"].get("sent_full_at")


def test_music_suno_send_still_explicit_admin_resend(monkeypatch):
    job = _completed_suno_job(output_file_id="tg-old-file", send_attempt_count=0)
    jobs, _vault = _patch_music_job_store(monkeypatch, job)
    sent = []

    class SendBot:
        async def send_audio(self, **kwargs):
            sent.append(kwargs)
            return SimpleNamespace(audio=SimpleNamespace(file_id="tg-new-file"))

    update = _admin_update()
    asyncio.run(bot.cmd_music_suno_send(update, SimpleNamespace(args=["MUS-STATUS"], bot=SendBot())))

    assert sent and sent[0]["audio"] == "tg-old-file"
    assert jobs["MUS-STATUS"]["send_attempt_count"] == 1
    assert jobs["MUS-STATUS"]["sent_full_at"]
    assert "Đã gửi lại file nhạc" in update.message.texts[-1][0]


def test_music_engine_status_callback_completed_metadata_only_no_send(monkeypatch):
    job = _completed_suno_job("MUS-CALLBACK")
    jobs, _vault = _patch_music_job_store(monkeypatch, job)
    async def fake_poll(*_args, **_kwargs):
        return {"ok": True, "audio_bytes": b"real-audio", "job": dict(job)}

    monkeypatch.setattr(bot, "poll_music_suno_async_job", fake_poll)
    monkeypatch.setattr(bot, "upsert_music_vault_from_output", lambda **_kwargs: {"vault_id": "MV-CALLBACK"})
    monkeypatch.setattr(bot, "find_music_vault_entry_for_job", lambda *_args, **_kwargs: {"vault_id": "MV-CALLBACK"})

    class NoSendBot:
        async def send_audio(self, *args, **kwargs):
            raise AssertionError("engine music status must not auto-send full audio")

    query = DummyQuery(data="enginejob|music|MUS-CALLBACK")
    asyncio.run(bot.handle_engine_async_job_callback(SimpleNamespace(callback_query=query), SimpleNamespace(bot=NoSendBot())))
    text = query.edits[-1][0]

    assert "Đã gửi bản nhạc phía trên" not in text
    assert "Job nhạc đã hoàn tất" in text
    assert "/music_suno_send" in text
    assert jobs["MUS-CALLBACK"]["vault_id"] == "MV-CALLBACK"
    assert jobs["MUS-CALLBACK"]["send_attempt_count"] == 3


def test_music_suno_poll_completed_does_not_auto_send_audio(monkeypatch):
    monkeypatch.setattr(bot, "is_admin_user", lambda *_args, **_kwargs: True)

    async def fake_poll(*_args, **_kwargs):
        return {"ok": True, "audio_bytes": b"real-audio", "job": {"feature": "music_suno", "internal_job_id": "MUS-POLL", "status": "completed", "output_bytes": 10}}

    monkeypatch.setattr(bot, "poll_music_suno_async_job", fake_poll)
    monkeypatch.setattr(bot, "upsert_music_vault_from_output", lambda **_kwargs: {"vault_id": "MV-POLL"})
    monkeypatch.setattr(bot, "save_engine_async_job", lambda job: job)
    monkeypatch.setattr(bot, "find_music_vault_entry_for_job", lambda *_args, **_kwargs: {"vault_id": "MV-POLL"})
    update = _admin_update()

    class NoSendBot:
        async def send_audio(self, *args, **kwargs):
            raise AssertionError("status poll must not send audio")

    asyncio.run(bot.cmd_music_suno_poll(update, SimpleNamespace(args=["MUS-POLL"], bot=NoSendBot())))
    assert "Đã gửi bản nhạc phía trên" not in update.message.texts[-1][0]


def test_music_suno_send_explicit_admin_only(monkeypatch):
    monkeypatch.setattr(bot, "is_admin_user", lambda *_args, **_kwargs: False)
    update = _admin_update()

    asyncio.run(bot.cmd_music_suno_send(update, SimpleNamespace(args=["MUS-X"])))

    assert "không có quyền" in update.message.texts[-1][0]


def test_preview_quota_15_days_per_product_type(monkeypatch):
    store = _patch_preview_store(monkeypatch)
    now = datetime(2026, 6, 1, 10, 0, 0)

    decision = bot.preview_quota_check_and_consume("u1", "music_ai", now=now)

    assert decision["allowed"] is True
    assert decision["consumed"] is True
    assert store
    snap = bot.preview_quota_snapshot("u1", "music_ai", now + timedelta(days=1))
    assert snap["used_in_window"] is True
    assert snap["window_days"] == 15


def test_preview_quota_not_one_per_day(monkeypatch):
    _patch_preview_store(monkeypatch)
    now = datetime(2026, 6, 1, 10, 0, 0)
    bot.preview_quota_check_and_consume("u1", "music_ai", now=now)

    second_day = bot.preview_quota_guard("u1", "music_ai", now + timedelta(days=1))

    assert second_day["allowed"] is False
    assert second_day["reason"] == "quota"


def test_preview_quota_blocks_second_preview_before_15_days(monkeypatch):
    _patch_preview_store(monkeypatch)
    now = datetime(2026, 6, 1, 10, 0, 0)
    bot.preview_quota_check_and_consume("u1", "video_ai", now=now)

    blocked = bot.preview_quota_guard("u1", "video_ai", now + timedelta(days=14, hours=23))

    assert blocked["allowed"] is False
    assert blocked["reason"] == "quota"


def test_preview_quota_allows_after_15_days(monkeypatch):
    _patch_preview_store(monkeypatch)
    now = datetime(2026, 6, 1, 10, 0, 0)
    bot.preview_quota_check_and_consume("u1", "voice_ai", now=now)

    allowed = bot.preview_quota_guard("u1", "voice_ai", now + timedelta(days=15, seconds=1))

    assert allowed["allowed"] is True


def test_preview_quota_monthly_text_says_about_two_times_not_daily():
    text = bot.preview_quota_policy_text("vi")
    block = bot.preview_quota_block_text({"reason": "quota", "quota": {}, "product_type": "music_ai"}, "music_ai", "vi")

    assert "1 lần trong 15 ngày" in text
    assert "Tương đương tối đa khoảng 2 lần/tháng" in text
    assert "1 lần/ngày" not in text
    assert "1 lần/ngày" not in block


def test_preview_music_separate_from_voice(monkeypatch):
    _patch_preview_store(monkeypatch)
    now = datetime(2026, 6, 1, 10, 0, 0)
    bot.preview_quota_check_and_consume("u1", "music_ai", now=now)

    assert bot.preview_quota_guard("u1", "music_ai", now + timedelta(days=1))["allowed"] is False
    assert bot.preview_quota_guard("u1", "voice_ai", now + timedelta(days=1))["allowed"] is True


def test_preview_quota_not_consumed_when_tier_fails(monkeypatch):
    store = _patch_preview_store(monkeypatch, tier="newbie")

    decision = bot.preview_quota_check_and_consume("u1", "music_ai", now=datetime(2026, 6, 1, 10, 0, 0))

    assert decision["allowed"] is False
    assert decision["reason"] == "tier"
    assert decision["consumed"] is False
    assert store == {}


def test_preview_requires_silver(monkeypatch):
    _patch_preview_store(monkeypatch, tier="newbie")

    decision = bot.preview_quota_guard("u1", "voice_ai")

    assert decision["allowed"] is False
    assert decision["reason"] == "tier"


def test_preview_notice_mentions_silver_and_15_days():
    text = bot.preview_quota_notice_text("music_ai", "vi")

    assert "Silver" in text
    assert "1 lần trong 15 ngày" in text
    assert "Bản nghe thử nhạc dài 12 giây" in text
    assert "1 lần/ngày" not in text


def test_subtitle_dub_preview_duration_6s():
    assert bot.subtitle_dub_preview_seconds() == 6
    assert bot.preview_duration_seconds("subtitle_dub_ai") == 6


def test_video_preview_blocks_3_scenes_or_less(monkeypatch):
    _patch_preview_store(monkeypatch, tier="platinum")

    missing = bot.video_preview_gate_decision("u1", {"base_cost": 400})
    one_scene = bot.video_preview_gate_decision("u1", {"scene_count": 1, "base_cost": 400})
    three_scenes = bot.video_preview_gate_decision("u1", {"scene_count": 3, "base_cost": 400})

    assert missing["allowed"] is False
    assert one_scene["allowed"] is False
    assert three_scenes["allowed"] is False
    assert three_scenes["reason"] == "scene_count"
    assert not bot.video_paid_preview_required({"job_type": "video", "base_cost": 400, "preview_required": True})
    assert not bot.video_paid_preview_required({"job_type": "video", "base_cost": 400, "preview_required": True, "scene_count": 3})


def test_video_preview_allows_more_than_3_scenes(monkeypatch):
    _patch_preview_store(monkeypatch, tier="platinum")

    decision = bot.video_preview_gate_decision("u1", {"scene_count": 4, "base_cost": 400})

    assert decision["allowed"] is True
    assert decision["scene_count"] == 4
    assert bot.video_paid_preview_required({"job_type": "video", "base_cost": 400, "preview_required": True, "scene_count": 4})


def test_video_preview_5_scenes_requires_gold(monkeypatch):
    _patch_preview_store(monkeypatch, tier="silver")

    decision = bot.video_preview_gate_decision("u1", {"scene_count": 5, "base_cost": 500})

    assert decision["allowed"] is False
    assert decision["required_tier"] == "gold"


def test_video_preview_over_500_requires_gold(monkeypatch):
    _patch_preview_store(monkeypatch, tier="silver")

    decision = bot.video_preview_gate_decision("u1", {"scene_count": 4, "base_cost": 501})

    assert decision["allowed"] is False
    assert decision["required_tier"] == "gold"


def test_video_preview_1000_1200_1500_or_10_scenes_requires_platinum(monkeypatch):
    _patch_preview_store(monkeypatch, tier="gold")

    by_price = bot.video_preview_gate_decision("u1", {"scene_count": 4, "base_cost": 1000})
    by_scene = bot.video_preview_gate_decision("u1", {"scene_count": 10, "base_cost": 500})

    assert by_price["allowed"] is False
    assert by_price["required_tier"] == "platinum"
    assert by_scene["allowed"] is False
    assert by_scene["required_tier"] == "platinum"


def test_video_package_200_pricing_not_touched():
    source = Path(bot.__file__).read_text(encoding="utf-8")
    assert "package 200" not in source.lower()[source.lower().find("def video_paid_preview_required"):source.lower().find("PAID_PREVIEW_REQUIRED_TASKS")]


def test_preview_quota_policy_command_registered():
    source = Path(bot.__file__).read_text(encoding="utf-8")
    assert 'CommandHandler("preview_quota_policy", cmd_preview_quota_policy)' in source
    assert 'CommandHandler("preview_quota_status", cmd_preview_quota_status)' in source
    assert 'CommandHandler("preview_quota_reset", cmd_preview_quota_reset)' in source
    assert 'CommandHandler("music_suno_send", cmd_music_suno_send)' in source
