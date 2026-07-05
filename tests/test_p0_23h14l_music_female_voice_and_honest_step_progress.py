import bot
from services import product_progress_status


def _song_job(**overrides):
    job = {
        "internal_job_id": "MUSH14LTRUTH",
        "feature": "music_suno",
        "product_type": "music_song",
        "music_product_type": "music_song",
        "status": "pending_submit",
        "current_stage": "received_request",
        "stage": "received_request",
        "progress_percent": 5,
        "provider_style_prompt": "Vietnamese pop, Female vocal",
        "provider_lyrics": "[Verse]\nTOAN AAS\n[Chorus]\nCung nhau vuon xa",
        "provider_submit_called": False,
        "create_song_started": False,
        "lyrics_prepared": False,
        "style_prepared": False,
        "output_bytes": 0,
    }
    job.update(overrides)
    return job


def _state(**overrides):
    return product_progress_status.product_progress_stage_from_job(
        "music_song",
        _song_job(**overrides),
    )


def test_music_progress_does_not_jump_to_35_before_provider_submit():
    state = _state()

    assert state["percent"] == 5
    assert state["current_stage"] == "received_request"
    assert state["completed_steps"] == ["received_request"]
    assert state["create_song_started"] is False


def test_music_input_text_does_not_complete_lyrics_or_style_checkpoints():
    lifecycle = product_progress_status.music_progress_lifecycle(
        "music_song",
        _song_job(),
    )

    assert lifecycle["lyrics_input_present"] is True
    assert lifecycle["style_input_present"] is True
    assert lifecycle["lyrics_prepared"] is False
    assert lifecycle["style_prepared"] is False


def test_music_submit_in_flight_stays_at_25_without_create_song_started():
    state = _state(
        status="submitting",
        current_stage="preparing_style",
        stage="preparing_style",
        progress_percent=25,
        provider_submit_called=True,
        lyrics_prepared=True,
        style_prepared=True,
    )

    assert state["percent"] == 25
    assert state["current_stage"] == "preparing_style"
    assert state["create_song_started"] is False
    assert state["public_percent_reason"] == "provider_submitting"


def test_music_progress_35_only_after_create_song_started():
    state = _state(
        status="submitted",
        current_stage="generating_song",
        stage="generating_song",
        progress_percent=35,
        provider_submit_called=True,
        provider_task_id="provider-task-h14l",
        create_song_started=True,
        lyrics_prepared=True,
        style_prepared=True,
    )

    assert state["percent"] == 35
    assert state["current_stage"] == "generating_song"
    assert state["create_song_started"] is True
    assert state["public_percent_reason"] == "provider_accepted"
    assert "generating_song" not in state["completed_steps"]


def test_music_provider_status_advances_only_on_real_status():
    submitted = _state(
        status="submitted",
        provider_task_id="provider-task-h14l",
        provider_submit_called=True,
        create_song_started=True,
        progress_percent=35,
    )
    processing = _state(
        status="processing",
        provider_task_id="provider-task-h14l",
        provider_submit_called=True,
        create_song_started=True,
        progress_percent=50,
    )
    generating = _state(
        status="generating",
        provider_task_id="provider-task-h14l",
        provider_submit_called=True,
        create_song_started=True,
        progress_percent=35,
    )

    assert submitted["percent"] == 35
    assert processing["percent"] == 50
    assert generating["percent"] == 65
    assert processing["public_percent_reason"] == "provider_processing"
    assert generating["public_percent_reason"] == "provider_generating"


def test_music_steps_match_artifact_and_delivery_checkpoints():
    artifact = _state(
        status="completed",
        provider_task_id="provider-task-h14l",
        provider_completed=True,
        create_song_started=True,
        output_url="https://provider.invalid/audio",
        progress_percent=65,
    )
    validated = _state(
        status="completed",
        provider_task_id="provider-task-h14l",
        provider_completed=True,
        create_song_started=True,
        output_bytes=4096,
        artifact_duration_seconds=180,
        audio_validated=True,
        progress_percent=85,
    )
    delivered = _state(
        status="delivered",
        provider_task_id="provider-task-h14l",
        provider_completed=True,
        create_song_started=True,
        output_bytes=4096,
        artifact_duration_seconds=180,
        audio_validated=True,
        delivery_message_id="telegram-message-h14l",
        terminal_state="delivered",
        progress_percent=95,
    )

    assert 80 <= artifact["percent"] <= 90
    assert artifact["current_stage"] == "validating_audio"
    assert validated["percent"] == 95
    assert validated["current_stage"] == "delivering"
    assert delivered["percent"] == 100
    assert delivered["current_stage"] == "delivered"


def test_music_pending_job_stores_inputs_without_fake_completed_steps(monkeypatch):
    monkeypatch.setattr(bot, "save_engine_async_job", lambda job: dict(job))

    job = bot.create_music_pending_submit_job(
        user_id=2314,
        chat_id=2314,
        result={
            "music_product_mode": "song",
            "product_kind": "song",
            "provider_style_prompt": "Vietnamese pop, Female vocal",
            "provider_lyrics": "[Verse]\nTOAN AAS",
            "song_vocal": "female",
        },
    )

    assert job["lyrics_input_present"] is True
    assert job["style_input_present"] is True
    assert job["lyrics_prepared"] is True
    assert job["style_prepared"] is True
    assert job["create_song_started"] is False
    state = product_progress_status.product_progress_stage_from_job("music_song", job)
    assert state["percent"] == 25
    assert state["current_stage"] == "preparing_style"


def test_music_submit_helpers_persist_truthful_checkpoints(monkeypatch):
    monkeypatch.setattr(bot, "save_engine_async_job", lambda job: dict(job))
    pending = _song_job()

    submitting = bot.update_music_submit_job_provider_started(pending)
    accepted = bot.update_music_submit_job_provider_accepted(
        submitting,
        {
            "provider": "key4u_suno",
            "provider_task_id": "provider-task-h14l",
            "status": "PASS_SUBMITTED",
        },
    )

    assert submitting["progress_percent"] == 25
    assert submitting["create_song_started"] is False
    assert submitting["public_percent_reason"] == "provider_payload_validated_submit_started"
    assert accepted["progress_percent"] == 35
    assert accepted["create_song_started"] is True
    assert accepted["public_percent_reason"] == "provider_job_accepted"


def test_music_public_panel_no_fake_35():
    state = _state(
        status="submitting",
        current_stage="preparing_style",
        stage="preparing_style",
        progress_percent=35,
        provider_submit_called=True,
        lyrics_prepared=True,
        style_prepared=True,
    )
    text = bot.product_progress_status_text(
        "music_song",
        "MUSH14LTRUTH",
        state["current_stage"],
        state["percent"],
        completed_steps=state["completed_steps"],
    )

    assert "Tiến độ: 25%" in text
    assert "Tiến độ: 35%" not in text
