from pathlib import Path

import bot


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _disable_short(monkeypatch):
    monkeypatch.setattr(bot, "MUSIC_SHORT_MODE_VERIFIED", False)
    monkeypatch.setattr(
        bot,
        "get_system_setting",
        lambda key, default="": "" if key == "music_short_mode_verified" else default,
    )


def test_music_preview_duration_12s():
    assert bot.music_preview_seconds() == 12
    text = bot.music_ai_preview_text({"selected_prompt": "nhạc nền", "guided_duration_seconds": 60}, "vi")
    assert "Preview: <b>12 giây đầu</b>" in text


def test_voice_preview_duration_6s():
    assert bot.voice_preview_seconds() == 6
    labels = _labels(bot.voice_clone_preview_entry_keyboard(1, "vi"))
    assert "▶️ Nghe thử 6 giây" in labels


def test_video_preview_duration_6s():
    assert bot.video_preview_seconds() == 6
    labels = _labels(bot.video_paid_preview_entry_keyboard("tok", "vi"))
    assert "▶️ Xem thử 6 giây" in labels


def test_preview_labels_match_product_type():
    music_labels = _labels(bot.music_ai_preview_keyboard("vi", result={"selected_prompt": "x"}))
    voice_labels = _labels(bot.voice_clone_preview_entry_keyboard(1, "vi"))
    video_labels = _labels(bot.video_paid_preview_entry_keyboard("tok", "vi"))

    assert "▶️ Nghe thử 12 giây" in music_labels
    assert "✅ Dùng bản đầy đủ" in music_labels
    assert "🗂 Lưu vào kho nhạc" in music_labels
    assert "▶️ Nghe thử 6 giây" in voice_labels
    assert "▶️ Xem thử 6 giây" in video_labels


def test_full_output_not_delivered_before_confirm():
    source = Path(bot.__file__).read_text(encoding="utf-8")
    start = source.index('if action in {"music_ai_guard", "music_ai_preview"}:')
    end = source.index('if action == "music_ai_confirm":', start)
    preview_block = source[start:end]

    assert "toan_aas_music_preview.mp3" in preview_block
    assert "toan_aas_music.mp3" not in preview_block
    assert "cap_voice_preview_audio_bytes" in preview_block
    assert "Bản đầy đủ đã được lưu trong kho" in bot.music_ai_preview_text({"song_product": "full", "selected_prompt": "bài hát"}, "vi")


def test_music_half_option_removed_if_not_verified(monkeypatch):
    _disable_short(monkeypatch)
    labels = _labels(bot.music_song_product_keyboard("vi"))

    assert "🎤 Bài hát có lời AI" in labels
    assert not any("Nửa bài" in label for label in labels)
    assert bot.music_result_product_kind({"song_product": "half"}) == "song_full"


def test_music_short_option_only_if_provider_verified(monkeypatch):
    monkeypatch.setattr(bot, "MUSIC_SHORT_MODE_VERIFIED", True)
    labels = _labels(bot.music_song_product_keyboard("vi"))

    assert "1️⃣ Nửa bài thật" in labels
    assert bot.music_result_product_kind({"song_product": "half"}) == "song_half"


def test_music_does_not_sell_fake_half_song(monkeypatch):
    _disable_short(monkeypatch)
    text = bot.music_song_product_text("vi")
    preview = bot.music_ai_preview_text({"song_product": "half", "selected_prompt": "bài hát"}, "vi")

    assert "Không bán nửa bài" in text
    assert "Đã chọn: Nửa bài." not in preview
    assert bot.music_ai_output_price_xu(60, "song_half") == bot.MUSIC_VOCAL_FULL_PRICE_XU


def test_music_duration_does_not_promise_exact_short_if_provider_not_verified(monkeypatch):
    _disable_short(monkeypatch)
    prompt = bot.music_provider_prompt_for_result({"song_product": "half", "selected_prompt": "bài hát"}, preview=True)

    assert "verified short song" not in prompt
    assert "Target output duration: 120 seconds" in prompt


def test_music_vault_stores_real_output_file(monkeypatch, tmp_path):
    store = {}
    monkeypatch.setattr(bot, "OPERATOR_UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(bot, "get_system_setting", lambda key, default="": store.get(key, default))
    monkeypatch.setattr(bot, "set_system_setting", lambda key, value, note="", updated_by="": store.__setitem__(key, value))
    bot.MUSIC_VAULT_MEMORY.clear()
    bot.MUSIC_VAULT_MEMORY_INDEX.clear()

    entry = bot.upsert_music_vault_from_output(
        audio_bytes=b"real-audio-bytes",
        result={"song_product": "full", "selected_prompt": "bài hát"},
        job={"internal_job_id": "MUS-16A2", "provider": "key4u_suno", "provider_task_id": "secret-task"},
        status="preview_sent",
        updated_by="test",
    )

    assert entry["status"] == "preview_sent"
    assert entry["category"] == "vocal_ai"
    assert entry["output_bytes"] == len(b"real-audio-bytes")
    assert entry["storage_ref"]
    assert Path(entry["storage_ref"]).exists()
    assert entry["provider_task_id_present"] is True
