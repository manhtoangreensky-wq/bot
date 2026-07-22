import ast
import asyncio
import copy
from pathlib import Path
from types import SimpleNamespace


BOT_SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")


def test_pr400_background_task_registry_exists_before_confirm_handler():
    definition = "SUBDUB_PUBLIC_FINAL_BACKGROUND_TASKS: dict[str, asyncio.Task] = {}"
    handler = "async def handle_video_dubbing_callback("

    assert BOT_SOURCE.count(definition) == 1
    assert BOT_SOURCE.index(definition) < BOT_SOURCE.index(handler)


def test_all_three_paid_subdub_confirm_buttons_use_pr400_final_callback():
    expected_buttons = (
        'InlineKeyboardButton("✅ Xác nhận dịch" if is_vi else "✅ Confirm translation", callback_data="videodub|final")',
        'InlineKeyboardButton("✅ Xác nhận lồng tiếng" if is_vi else "✅ Confirm dubbing", callback_data="videodub|final")',
        'InlineKeyboardButton("✅ Tạo video hoàn chỉnh" if is_vi else "✅ Create final video", callback_data="videodub|final")',
    )

    for button in expected_buttons:
        assert button in BOT_SOURCE


def test_pr400_final_callback_uses_registered_background_runner():
    start = BOT_SOURCE.index("async def handle_video_dubbing_callback(")
    end = BOT_SOURCE.index('    if action == "subdub_status":', start)
    final_dispatch = BOT_SOURCE[start:end]

    assert 'if action == "final" and not _subdub_background:' in final_dispatch
    assert "SUBDUB_PUBLIC_FINAL_BACKGROUND_TASKS.get(task_key)" in final_dispatch
    assert "SUBDUB_PUBLIC_FINAL_BACKGROUND_TASKS[task_key] = task" in final_dispatch
    assert (
        'CallbackQueryHandler(handle_video_dubbing_callback, pattern=r"^videodub\\|")'
        in BOT_SOURCE
    )


def _load_confirm_handler(namespace):
    start = BOT_SOURCE.index("async def handle_video_dubbing_callback(")
    end = BOT_SOURCE.index('    if action == "subdub_status":', start)
    module = ast.parse(BOT_SOURCE[start:end] + "    return None\n")
    handler = module.body[0]
    handler = copy.deepcopy(handler)
    handler.returns = None
    for arg in (*handler.args.args, *handler.args.kwonlyargs):
        arg.annotation = None
    exec(compile(ast.fix_missing_locations(ast.Module(body=[handler], type_ignores=[])), "bot.py", "exec"), namespace)
    return namespace["handle_video_dubbing_callback"]


def test_subtitle_dub_and_combo_confirm_callbacks_start_pr400_runner():
    started_modes = []
    current_state = {}

    async def fake_runner(_update, _context, _task_key):
        started_modes.append(current_state["mode"])

    async def run_mode(mode, uid):
        current_state.clear()
        current_state.update({"mode": mode, "source_file_id": f"video-{uid}"})
        task_key = f"confirm:{mode}:{uid}"

        async def answer():
            return None

        query = SimpleNamespace(
            answer=answer,
            data="videodub|final",
            from_user=SimpleNamespace(id=uid),
            message=SimpleNamespace(chat_id=uid),
        )
        context = SimpleNamespace(application=None)

        await handler(
            SimpleNamespace(callback_query=query),
            context,
        )

    namespace = {
        "get_user_language": lambda _uid: "vi",
        "get_video_dubbing_pending": lambda _uid: dict(current_state),
        "subtitle_dub_pipeline_job_key": lambda uid, _chat_id, state: f"confirm:{state['mode']}:{uid}",
        "SUBDUB_PUBLIC_FINAL_BACKGROUND_TASKS": {},
        "_run_subdub_public_final_background": fake_runner,
    }
    handler = _load_confirm_handler(namespace)

    async def scenario():
        for uid, mode in enumerate(
            (
                "translate_subtitles",
                "dub",
                "subtitle_plus_dub",
            ),
            start=22001,
        ):
            await run_mode(mode, uid)

    asyncio.run(scenario())

    assert started_modes == [
        "translate_subtitles",
        "dub",
        "subtitle_plus_dub",
    ]
