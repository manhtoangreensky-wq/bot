import asyncio
import inspect
from types import SimpleNamespace

import bot


def _asr_result(text="Loi thoai on dinh"):
    return {
        "output_valid": True,
        "transcript_text": text,
        "segments": [{"index": 1, "start": 0.25, "end": 1.75, "text": text}],
        "provider": "fixture",
        "detected_language": "vi",
        "duration_seconds": 2,
        "subtitle_timing_source": "provider_segments",
        "global_timing_preserved": True,
    }


def test_ocr1_public_defaults_off_and_public_prepare_requires_explicit_gate():
    source = open(bot.__file__, encoding="utf-8").read()
    prepare_source = inspect.getsource(bot.video_dubbing_prepare_subtitles)

    assert 'SUBDUB_VISUAL_OCR_ENABLED = env_flag("SUBDUB_VISUAL_OCR_ENABLED", "false")' in source
    assert 'SUBDUB_VISUAL_OCR_PUBLIC_ENABLED = env_flag("SUBDUB_VISUAL_OCR_PUBLIC_ENABLED", "false")' in source
    assert "SUBDUB_VISUAL_OCR_PUBLIC_ENABLED" in prepare_source


def test_embedded_subtitle_remains_first_with_ocr_public_off(monkeypatch):
    embedded = "1\n00:00:00,000 --> 00:00:02,000\nXin chao\n"

    async def embedded_subtitle(*_args, **_kwargs):
        return embedded, "embedded_subtitle"

    async def visual_must_not_run(*_args, **_kwargs):
        raise AssertionError("OCR must not replace embedded subtitles")

    monkeypatch.setattr(bot, "video_dubbing_extract_embedded_subtitle", embedded_subtitle)
    monkeypatch.setattr(bot, "video_dubbing_extract_visual_subtitle", visual_must_not_run)

    result = asyncio.run(
        bot.video_dubbing_resolve_source_script(
            b"video",
            "video/mp4",
            SimpleNamespace(),
            prefer_visual_subtitles=False,
        )
    )

    assert result["source_kind"] == "embedded_subtitle"
    assert result["subtitle"] == embedded


def test_no_embedded_subtitle_falls_immediately_to_asr_when_ocr_public_off(monkeypatch):
    calls = {"asr": 0}

    async def no_embedded(*_args, **_kwargs):
        return "", "no_embedded_subtitle"

    async def visual_must_not_run(*_args, **_kwargs):
        raise AssertionError("public OCR must stay disabled")

    async def asr(*_args, **_kwargs):
        calls["asr"] += 1
        return _asr_result()

    monkeypatch.setattr(bot, "video_dubbing_extract_embedded_subtitle", no_embedded)
    monkeypatch.setattr(bot, "video_dubbing_extract_visual_subtitle", visual_must_not_run)
    monkeypatch.setattr(bot, "transcribe_media_to_segments", asr)

    result = asyncio.run(
        bot.video_dubbing_resolve_source_script(
            b"video",
            "video/mp4",
            SimpleNamespace(),
            duration_seconds=2,
            prefer_visual_subtitles=False,
        )
    )

    assert calls["asr"] == 1
    assert result["source_kind"] == "asr"
    assert result["subtitle_timing_source"] == "provider_segments"


def test_missing_tesseract_falls_back_to_asr_without_hanging(monkeypatch):
    async def no_embedded(*_args, **_kwargs):
        return "", "no_embedded_subtitle"

    async def missing_ocr(*_args, **_kwargs):
        return {"ok": False, "status": "visual_ocr_runtime_missing", "segments": []}

    async def asr(*_args, **_kwargs):
        return _asr_result()

    monkeypatch.setattr(bot, "video_dubbing_extract_embedded_subtitle", no_embedded)
    monkeypatch.setattr(bot, "video_dubbing_extract_visual_subtitle", missing_ocr)
    monkeypatch.setattr(bot, "transcribe_media_to_segments", asr)

    result = asyncio.run(
        asyncio.wait_for(
            bot.video_dubbing_resolve_source_script(
                b"video",
                "video/mp4",
                SimpleNamespace(),
                duration_seconds=2,
                prefer_visual_subtitles=True,
            ),
            timeout=0.5,
        )
    )

    assert result["source_kind"] == "asr"


def test_hanging_mock_ocr_times_out_then_uses_asr(monkeypatch):
    async def no_embedded(*_args, **_kwargs):
        return "", "no_embedded_subtitle"

    async def hanging_ocr(*_args, **_kwargs):
        await asyncio.sleep(10)
        return {"ok": True, "subtitle": "must-not-win"}

    async def asr(*_args, **_kwargs):
        return _asr_result()

    monkeypatch.setattr(bot, "SUBDUB_VISUAL_OCR_TOTAL_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(bot, "video_dubbing_extract_embedded_subtitle", no_embedded)
    monkeypatch.setattr(bot, "video_dubbing_extract_visual_subtitle", hanging_ocr)
    monkeypatch.setattr(bot, "transcribe_media_to_segments", asr)

    result = asyncio.run(
        bot.video_dubbing_resolve_source_script(
            b"video",
            "video/mp4",
            SimpleNamespace(),
            duration_seconds=2,
            prefer_visual_subtitles=True,
        )
    )

    assert result["source_kind"] == "asr"


def test_subdub_ffmpeg_timeout_kills_and_reaps_process(monkeypatch):
    holder = {}

    class HangingProcess:
        def __init__(self):
            self.returncode = None
            self.killed = False
            self.reaped = False

        async def communicate(self):
            if self.killed:
                self.returncode = -9
                self.reaped = True
                return b"", b"killed"
            await asyncio.sleep(10)
            return b"", b""

        def kill(self):
            self.killed = True

    async def create_process(*_args, **_kwargs):
        holder["process"] = HangingProcess()
        return holder["process"]

    monkeypatch.setattr(bot.asyncio, "create_subprocess_exec", create_process)
    ok, detail = asyncio.run(bot.run_subdub_ffmpeg_command(["ffmpeg", "fixture"], timeout=0.01))

    assert ok is False
    assert detail == "ffmpeg_timeout"
    assert holder["process"].killed is True
    assert holder["process"].reaped is True


class _Message:
    def __init__(self, chat_id):
        self.chat_id = chat_id
        self.message_id = 44
        self.sent = []

    async def reply_text(self, text, **kwargs):
        result = SimpleNamespace(message_id=991, text=str(text), **kwargs)
        self.sent.append(result)
        return result


class _Query:
    def __init__(self, uid):
        self.data = "videodub|final"
        self.from_user = SimpleNamespace(id=uid)
        self.message = _Message(uid)
        self.answer_count = 0

    async def answer(self, *_args, **_kwargs):
        self.answer_count += 1


class _Application:
    def __init__(self):
        self.tasks = []

    def create_task(self, coroutine, **_kwargs):
        task = asyncio.create_task(coroutine)
        self.tasks.append(task)
        return task


async def _background_final_scenario(monkeypatch, *, duplicate=False):
    uid = 991700
    bot.clear_video_dubbing_pending(uid)
    state = bot.set_video_dubbing_pending(
        uid,
        "confirm",
        mode=bot.VIDEO_SUBTITLE_MODE_DUB,
        video_processing_mode=bot.VIDEO_SUBTITLE_MODE_DUB,
        process_type=bot.VIDEO_SUBTITLE_MODE_DUB,
        video_file_id="fixture-video",
        source_file_id="fixture-video",
        target_language="Tieng Viet",
        voice_style="default_female",
        voice_speed="1.0",
        output_type="video",
    )
    task_key = bot.subtitle_dub_pipeline_job_key(uid, uid, state)
    bot.SUBDUB_PUBLIC_FINAL_BACKGROUND_TASKS.pop(task_key, None)
    started = asyncio.Event()
    release = asyncio.Event()
    calls = {"pipeline": 0}

    async def edit_or_send(_query, text, **kwargs):
        return SimpleNamespace(message_id=55, text=str(text), **kwargs)

    async def pipeline(*_args, **_kwargs):
        calls["pipeline"] += 1
        started.set()
        await release.wait()
        return {"ok": False, "in_progress": True, "text": "Dang xu ly", "job_id": "BG1"}

    async def engine(_feature, params, _engine_context):
        return {"ok": True, "runner_result": await params["runner"]()}

    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: False)
    monkeypatch.setattr(bot, "video_dubbing_asr_missing_for_state", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(bot, "video_dubbing_engine_access_decision", lambda *_args, **_kwargs: {"allowed": True})
    monkeypatch.setattr(bot, "safe_edit_or_send", edit_or_send)
    monkeypatch.setattr(bot, "execute_video_dubbing_pipeline", pipeline)
    monkeypatch.setattr(bot, "execute_engine", engine)

    query = _Query(uid)
    update = SimpleNamespace(callback_query=query)
    application = _Application()
    context = SimpleNamespace(application=application)

    await asyncio.wait_for(bot.handle_video_dubbing_callback(update, context), timeout=0.25)
    if duplicate:
        duplicate_query = _Query(uid)
        await asyncio.wait_for(
            bot.handle_video_dubbing_callback(SimpleNamespace(callback_query=duplicate_query), context),
            timeout=0.25,
        )
    await asyncio.wait_for(started.wait(), timeout=0.25)
    assert application.tasks[0].done() is False
    release.set()
    await asyncio.wait_for(application.tasks[0], timeout=0.5)
    bot.SUBDUB_PUBLIC_FINAL_BACKGROUND_TASKS.pop(task_key, None)
    bot.clear_video_dubbing_pending(uid)
    return calls, query, application


def test_telegram_handler_returns_before_mocked_pipeline_finishes(monkeypatch):
    calls, query, application = asyncio.run(_background_final_scenario(monkeypatch))

    assert query.answer_count == 1
    assert calls["pipeline"] == 1
    assert len(application.tasks) == 1


def test_duplicate_final_update_starts_one_background_job(monkeypatch):
    calls, _query, application = asyncio.run(_background_final_scenario(monkeypatch, duplicate=True))

    assert calls["pipeline"] == 1
    assert len(application.tasks) == 1


def test_background_pipeline_exception_terminalizes_job(monkeypatch):
    async def scenario():
        uid = 991702
        bot.clear_video_dubbing_pending(uid)
        state = bot.set_video_dubbing_pending(
            uid,
            "confirm",
            mode=bot.VIDEO_SUBTITLE_MODE_DUB,
            video_processing_mode=bot.VIDEO_SUBTITLE_MODE_DUB,
            process_type=bot.VIDEO_SUBTITLE_MODE_DUB,
            video_file_id="fixture-video-error",
            source_file_id="fixture-video-error",
            target_language="Tieng Viet",
            voice_style="default_female",
            voice_speed="1.0",
            output_type="video",
        )
        task_key = bot.subtitle_dub_pipeline_job_key(uid, uid, state)
        bot.SUBTITLE_DUB_PIPELINE_JOBS[task_key] = {
            "job_key": task_key,
            "status": "processing",
            "progress_percent": 80,
            "delivery_success": False,
        }

        async def edit_or_send(_query, text, **kwargs):
            return SimpleNamespace(message_id=55, text=str(text), **kwargs)

        async def pipeline(*_args, **_kwargs):
            raise RuntimeError("fixture_mux_failure")

        async def engine(_feature, params, _engine_context):
            return {"ok": True, "runner_result": await params["runner"]()}

        async def fail_once(*_args, **_kwargs):
            return SimpleNamespace(message_id=992)

        monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
        monkeypatch.setattr(bot, "is_admin_user", lambda _uid: False)
        monkeypatch.setattr(bot, "video_dubbing_asr_missing_for_state", lambda *_args, **_kwargs: False)
        monkeypatch.setattr(bot, "video_dubbing_engine_access_decision", lambda *_args, **_kwargs: {"allowed": True})
        monkeypatch.setattr(bot, "safe_edit_or_send", edit_or_send)
        monkeypatch.setattr(bot, "execute_video_dubbing_pipeline", pipeline)
        monkeypatch.setattr(bot, "execute_engine", engine)
        monkeypatch.setattr(bot, "send_subdub_fail_once", fail_once)

        query = _Query(uid)
        application = _Application()
        await bot.handle_video_dubbing_callback(
            SimpleNamespace(callback_query=query),
            SimpleNamespace(application=application),
        )
        await asyncio.wait_for(application.tasks[0], timeout=0.5)

        job = bot.SUBTITLE_DUB_PIPELINE_JOBS[task_key]
        assert job["status"] == "failed_no_charge"
        assert job["terminal_state"] == "failed_no_charge"
        assert job["continue_polling"] is False
        assert bot.get_video_dubbing_pending(uid)["processing"] == "0"
        bot.SUBDUB_PUBLIC_FINAL_BACKGROUND_TASKS.pop(task_key, None)
        bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(task_key, None)
        bot.clear_video_dubbing_pending(uid)

    asyncio.run(scenario())


def test_stuck_80_percent_job_terminalizes_failed_no_charge(monkeypatch):
    uid = 991701
    state = bot.set_video_dubbing_pending(
        uid,
        "processing",
        mode=bot.VIDEO_SUBTITLE_MODE_DUB,
        video_file_id="fixture-video-timeout",
        processing="1",
    )
    task_key = bot.subtitle_dub_pipeline_job_key(uid, uid, state)
    bot.SUBTITLE_DUB_PIPELINE_JOBS[task_key] = {
        "job_key": task_key,
        "status": "processing",
        "progress_percent": 80,
        "delivery_success": False,
    }
    query = _Query(uid)

    asyncio.run(
        bot._terminalize_subdub_background_failure(
            SimpleNamespace(callback_query=query),
            task_key=task_key,
            reason="ffmpeg_timeout",
            send_public=False,
        )
    )

    job = bot.SUBTITLE_DUB_PIPELINE_JOBS[task_key]
    assert job["status"] == "failed_no_charge"
    assert job["terminal_state"] == "failed_no_charge"
    assert job["continue_polling"] is False
    assert job["delivery_success"] is False
    assert bot.get_video_dubbing_pending(uid)["processing"] == "0"
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(task_key, None)
    bot.clear_video_dubbing_pending(uid)


def test_m4live10_duration_and_cue_safety_remain_in_runtime():
    render_source = inspect.getsource(bot.video_dubbing_render_video)
    translate_source = inspect.getsource(bot.translate_subtitle_segments)
    timing_source = inspect.getsource(bot.subdub_validate_cue_locked_timing)
    delivery_source = inspect.getsource(bot.send_public_subtitle_dub_final_outputs)
    validation_source = inspect.getsource(bot.subdub_validate_video_output)

    assert "apad=whole_dur" in render_source
    assert "atrim=duration" in render_source
    assert "-shortest" not in render_source
    assert "source_duration" in render_source
    assert "subdub_validate_cue_locked_timing" in translate_source
    assert "cue_start_mismatch_count" in timing_source
    assert "subdub_validate_video_output" in delivery_source
    assert "video_duration_coverage_failed" in validation_source


def test_product_video_and_paid_provider_modules_are_not_part_of_emergency_fix():
    source = inspect.getsource(bot._run_subdub_public_final_background).lower()

    for forbidden in ("shopaikey", "key4u", "product_video", "payos", "suno"):
        assert forbidden not in source
