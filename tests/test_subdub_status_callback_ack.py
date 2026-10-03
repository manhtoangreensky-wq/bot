"""Exercise emitted SubDub status/download callbacks through their real route."""
import asyncio
import re
from pathlib import Path
from types import SimpleNamespace


SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")


class _Button:
    def __init__(self, text, callback_data=None, **kwargs):
        self.text = text
        self.callback_data = callback_data


class _Markup:
    def __init__(self, rows):
        self.inline_keyboard = rows


class _Query:
    def __init__(self, data: str, user_id: int = 81001) -> None:
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.answers = []
        self.screens = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


def _registered_handler(namespace):
    match = re.search(
        r"(?m)^\s*tg_app\.add_handler\(CallbackQueryHandler\(handle_video_dubbing_callback,.*$",
        SOURCE,
    )
    assert match, "SubDub callback handler registration is missing"
    routes = []
    runtime = dict(
        namespace,
        tg_app=SimpleNamespace(add_handler=routes.append),
        CallbackQueryHandler=lambda callback, pattern: (callback, re.compile(pattern)),
    )
    exec(compile(match.group(0).strip(), "bot.py:SubDub registration", "exec"), runtime)
    assert len(routes) == 1
    return routes[0]


def _emitted_callback(function_name, *args):
    match = re.search(
        rf"(?ms)^def {re.escape(function_name)}\(.*?(?=^(?:async\s+)?def\s|^class\s|\Z)",
        SOURCE,
    )
    assert match, f"SubDub button builder {function_name} is missing"
    namespace = {
        "InlineKeyboardButton": _Button,
        "InlineKeyboardMarkup": _Markup,
        "normalize_user_language": lambda lang: lang,
        "_safe_int": lambda value, default=0: int(value) if str(value).isdigit() else default,
        "subdub_missing_origin_back_callback": lambda _state: "videodub|back_type",
        "ui_text": lambda _lang, _key: "Home",
    }
    exec(compile(match.group(0), f"bot.py:{function_name}", "exec"), namespace)
    markup = namespace[function_name](*args)
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def _load_handler(*, job=None, admin=False):
    match = re.search(
        r"(?ms)^async def handle_video_dubbing_callback\(.*?(?=^(?:async\s+)?def\s|^class\s|\Z)",
        SOURCE,
    )
    assert match, "SubDub callback handler is missing"
    events = []
    screens = []

    async def render(_query, text, **kwargs):
        screens.append((text, kwargs))

    namespace = {
        "Update": object,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "get_user_language": lambda _uid: "vi",
        "logger": SimpleNamespace(warning=lambda *args, **kwargs: None),
        "_safe_int": lambda value, default=0: int(value) if str(value).isdigit() else default,
        "normalize_video_translate_mode": lambda value: value or "",
        "VIDEO_SUBTITLE_MODE_DUB": "dub",
        "VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB": "subtitle_plus_dub",
        "VIDEO_DUBBING_FLOW_SUBTITLE_PLUS_DUB": "subtitle_plus_dub",
        "get_video_dubbing_pending": lambda _uid: {},
        "current_product_context": lambda _uid: "showroom",
        "PRODUCT_CONTEXT_SHOWROOM": "showroom",
        "PRODUCT_CONTEXT_VIDEO_ADDON": "video_addon",
        "enter_product_context": lambda *args, **kwargs: None,
        "video_dubbing_video_addon_session_ready": lambda _uid: True,
        "get_local_worker_job": lambda job_id: events.append(("read_job", job_id)) or (job or {}),
        "is_admin_user": lambda _uid: admin,
        "safe_edit_or_send": render,
        "video_dubbing_job_status_text": lambda value, _lang: f"status:{value['status']}",
        "video_dubbing_job_result_keyboard": lambda _lang: "result-keyboard",
        "video_dubbing_guard_keyboard": lambda _lang, admin=False: "guard-keyboard",
        "video_dubbing_job_progress_keyboard": lambda job_id, _lang: f"progress-keyboard:{job_id}",
        "video_dubbing_menu_keyboard": lambda _lang, _origin="video": "subdub-menu-keyboard",
        "open_subdub_postdelivery_video_edit": lambda *args, **kwargs: None,
    }
    exec(compile(match.group(0), "bot.py:handle_video_dubbing_callback", "exec"), namespace)
    handler, pattern = _registered_handler(namespace)
    assert pattern.search("videodub|job_status|912")
    return handler, events, screens


def _dispatch(data, *, job=None, admin=False, user_id=81001):
    handler, events, screens = _load_handler(job=job, admin=admin)
    query = _Query(data, user_id=user_id)
    asyncio.run(handler(SimpleNamespace(callback_query=query), SimpleNamespace()))
    return query, events, screens


def test_missing_job_status_has_one_ack_and_recoverable_subdub_screen():
    status_callback = _emitted_callback("video_dubbing_job_progress_keyboard", 912, "vi")[0]
    query, events, screens = _dispatch(status_callback)

    assert query.answers == [((), {})]
    assert events == [("read_job", 912)]
    assert screens == [
        ("Không tìm thấy job xử lý.", {"reply_markup": "subdub-menu-keyboard"})
    ]


def test_unauthorized_job_status_does_not_expose_job_and_has_one_ack():
    status_callback = _emitted_callback("video_dubbing_job_progress_keyboard", 912, "vi")[0]
    query, events, screens = _dispatch(
        status_callback,
        job={"user_id": "other-user", "status": "processing"},
    )

    assert query.answers == [((), {})]
    assert events == [("read_job", 912)]
    assert "status:processing" not in str(screens)
    assert screens and screens[0][0] == "Không tìm thấy job xử lý."


def test_valid_job_status_reads_once_and_renders_without_provider_or_charge():
    status_callback = _emitted_callback("video_dubbing_job_progress_keyboard", 912, "vi")[0]
    query, events, screens = _dispatch(
        status_callback,
        job={"user_id": "81001", "status": "processing"},
    )

    assert query.answers == [((), {})]
    assert events == [("read_job", 912)]
    assert screens == [
        ("status:processing", {"reply_markup": "progress-keyboard:912"})
    ]


def test_job_download_uses_one_alert_ack():
    download_callback = _emitted_callback("video_dubbing_job_result_keyboard", "vi")[0]
    query, events, screens = _dispatch(download_callback)

    assert query.answers == [
        (("File kết quả sẽ được gửi trong chat khi worker hoàn tất.",), {"show_alert": True})
    ]
    assert events == []
    assert screens == []
