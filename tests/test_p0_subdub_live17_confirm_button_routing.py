import asyncio
from types import SimpleNamespace

import pytest

import bot


class _CaptureQuery:
    def __init__(self, user_id: int):
        self.data = "videodub|final"
        self.from_user = SimpleNamespace(id=user_id)
        self.message = SimpleNamespace(chat_id=user_id)
        self.answer_count = 0

    async def answer(self, *args, **kwargs):
        self.answer_count += 1


class _CaptureApplication:
    def __init__(self):
        self.tasks = []

    def create_task(self, coroutine, **kwargs):
        task = asyncio.create_task(coroutine)
        self.tasks.append(task)
        return task


@pytest.mark.parametrize(
    "mode",
    [
        bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        bot.VIDEO_SUBTITLE_MODE_DUB,
        bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
    ],
)
def test_confirm_button_reaches_background_runner_for_all_three_modes(monkeypatch, mode):
    async def scenario():
        user_id = 917001
        task_key = f"{user_id}|{mode}"
        query = _CaptureQuery(user_id)
        application = _CaptureApplication()
        calls = []

        monkeypatch.setattr(bot, "get_video_dubbing_pending", lambda _uid: {"mode": mode})
        monkeypatch.setattr(bot, "subtitle_dub_pipeline_job_key", lambda *_args: task_key)

        async def fake_background(_update, _context, received_task_key):
            calls.append(received_task_key)

        monkeypatch.setattr(bot, "_run_subdub_public_final_background", fake_background)
        bot.SUBDUB_PUBLIC_FINAL_BACKGROUND_TASKS.clear()

        await bot.handle_video_dubbing_callback(
            SimpleNamespace(callback_query=query),
            SimpleNamespace(application=application),
        )
        await asyncio.gather(*application.tasks)

        assert query.answer_count == 1
        assert calls == [task_key]
        bot.SUBDUB_PUBLIC_FINAL_BACKGROUND_TASKS.clear()

    asyncio.run(scenario())


def test_repeated_confirm_does_not_start_a_second_active_job(monkeypatch):
    async def scenario():
        user_id = 917002
        mode = bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB
        task_key = f"{user_id}|{mode}"
        query = _CaptureQuery(user_id)
        application = _CaptureApplication()
        release = asyncio.Event()
        calls = []

        monkeypatch.setattr(bot, "get_video_dubbing_pending", lambda _uid: {"mode": mode})
        monkeypatch.setattr(bot, "subtitle_dub_pipeline_job_key", lambda *_args: task_key)

        async def fake_background(_update, _context, received_task_key):
            calls.append(received_task_key)
            await release.wait()

        monkeypatch.setattr(bot, "_run_subdub_public_final_background", fake_background)
        bot.SUBDUB_PUBLIC_FINAL_BACKGROUND_TASKS.clear()
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(application=application)

        await bot.handle_video_dubbing_callback(update, context)
        await asyncio.sleep(0)
        await bot.handle_video_dubbing_callback(update, context)

        assert len(application.tasks) == 1
        assert calls == [task_key]

        release.set()
        await asyncio.gather(*application.tasks)
        bot.SUBDUB_PUBLIC_FINAL_BACKGROUND_TASKS.clear()

    asyncio.run(scenario())
