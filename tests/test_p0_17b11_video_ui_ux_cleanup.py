import asyncio
import inspect
from types import SimpleNamespace

import bot


GENERIC_RED_ERROR = "Có lỗi khi xử lý lệnh"


def _rows(markup):
    return [[button.text for button in row] for row in markup.inline_keyboard]


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


class _FakeMessage:
    chat_id = 1701100

    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))
        return None


class _FakeQuery:
    def __init__(self, user_id: int, data: str):
        self.from_user = SimpleNamespace(id=user_id, first_name="Video UI")
        self.data = data
        self.message = _FakeMessage()
        self.answers = []
        self.edits = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))

    async def edit_message_text(self, text, **kwargs):
        self.edits.append((text, kwargs))
        return None


def _last_text(query: _FakeQuery) -> str:
    if query.edits:
        return str(query.edits[-1][0])
    if query.message.replies:
        return str(query.message.replies[-1][0])
    return ""


def _last_markup(query: _FakeQuery):
    if query.edits:
        return query.edits[-1][1].get("reply_markup")
    if query.message.replies:
        return query.message.replies[-1][1].get("reply_markup")
    return None


def _press_video_product(user_id: int, callback: str) -> _FakeQuery:
    query = _FakeQuery(user_id, callback)
    asyncio.run(bot.handle_video_product_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    return query


def _press_videoedit(user_id: int, callback: str) -> _FakeQuery:
    query = _FakeQuery(user_id, callback)
    asyncio.run(bot.handle_video_editor_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    return query


def test_video_main_menu_two_columns():
    assert _rows(bot.main_video_keyboard("vi")) == [
        ["🎥 Tạo video AI", "🖼 Ảnh thành video"],
        ["🎭 Tự quay / đổi cảnh AI", "🧩 Prompt video"],
        ["🌐 Dịch phụ đề / Video", "📂 Kho video"],
        ["🏠 Menu chính"],
    ]


def test_video_main_menu_no_duplicate_image_to_video():
    labels = _labels(bot.main_video_keyboard("vi"))
    callbacks = _callbacks(bot.main_video_keyboard("vi"))
    assert "🖼 Ảnh → Video" not in labels
    assert "vproduct|open|image_to_video" in callbacks


def test_video_main_menu_no_music_voice_sfx():
    assert "🎵 Nhạc / Voice / SFX" not in _labels(bot.main_video_keyboard("vi"))


def test_video_main_menu_no_video_sample_channel():
    assert "📥 Video mẫu / Kênh mẫu" not in _labels(bot.main_video_keyboard("vi"))
    assert "vproduct|open|video_reference" not in _callbacks(bot.main_video_keyboard("vi"))


def test_video_main_menu_no_prompt_motion():
    assert "🎥 Prompt / Chuyển động" not in _labels(bot.main_video_keyboard("vi"))
    assert "vproduct|open|motion_prompt" not in _callbacks(bot.main_video_keyboard("vi"))


def test_video_main_menu_has_image_to_video_product():
    labels = _labels(bot.main_video_keyboard("vi"))
    callbacks = _callbacks(bot.main_video_keyboard("vi"))
    assert "🖼 Ảnh thành video" in labels
    assert "vproduct|open|image_to_video" in callbacks
    assert "vproduct|open|frame_video_local" not in callbacks


def test_video_main_menu_has_video_vault_not_downloader():
    labels = _labels(bot.main_video_keyboard("vi"))
    callbacks = _callbacks(bot.main_video_keyboard("vi"))
    assert "📂 Kho video" in labels
    assert "menu|video_vault" in callbacks
    assert "📥 Tải video từ link" not in labels
    assert "vdownload|start" not in callbacks


def test_video_main_menu_hides_local_edit_public_entry():
    labels = _labels(bot.main_video_keyboard("vi"))
    callbacks = _callbacks(bot.main_video_keyboard("vi"))
    assert "🛠 Chỉnh sửa video local" not in labels
    assert "vproduct|open|video_local_edit" not in callbacks


def test_video_numeric_buttons_1_to_5_single_row():
    markup = bot.video_numbered_choice_keyboard([(str(i), f"x|{i}") for i in range(1, 6)], "vi", main=False)
    assert _rows(markup) == [["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]]
    idea_markup = bot.task3d_idea_suggestions_keyboard({"product_id": "video_idea", "draft": {}}, "vi")
    assert _rows(idea_markup)[0] == ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]


def test_video_numeric_buttons_6_three_by_three():
    markup = bot.video_numbered_choice_keyboard([(str(i), f"x|{i}") for i in range(1, 7)], "vi", main=False)
    assert _rows(markup) == [["1️⃣", "2️⃣", "3️⃣"], ["4️⃣", "5️⃣", "6️⃣"]]


def test_video_numeric_buttons_8_four_by_four():
    markup = bot.video_numbered_choice_keyboard([(str(i), f"x|{i}") for i in range(1, 9)], "vi", main=False)
    assert _rows(markup) == [["1️⃣", "2️⃣", "3️⃣", "4️⃣"], ["5️⃣", "6️⃣", "7️⃣", "8️⃣"]]
    assert [len(row) for row in bot.task3d_prompt_number_rows(8, "prompt_image_select")] == [4, 4]


def test_video_local_edit_buttons_have_handlers():
    markup = bot.task3d_product_intro_keyboard("video_local_edit", "vi")
    callbacks = _callbacks(markup)
    assert "videoedit|upload" in callbacks
    assert "videoedit|cut" in callbacks
    assert "videoedit|resize" in callbacks
    assert "videoedit|compress" in callbacks
    source = inspect.getsource(bot.handle_video_editor_callback)
    assert "compress" in source and "upload" in source and "video_editor_normalize_action" in source


def test_video_local_edit_cut_requires_upload_not_red_error():
    user_id = 1701111
    bot.clear_video_editor_pending(user_id)
    query = _press_videoedit(user_id, "videoedit|cut")
    text = _last_text(query)
    assert "gửi video" in text.lower()
    assert "chưa trừ Xu" in text
    assert GENERIC_RED_ERROR not in text


def test_video_local_edit_resize_requires_upload_not_red_error():
    user_id = 1701112
    bot.clear_video_editor_pending(user_id)
    query = _press_videoedit(user_id, "videoedit|resize")
    text = _last_text(query)
    assert "gửi video" in text.lower()
    assert "chưa trừ Xu" in text
    assert GENERIC_RED_ERROR not in text


def test_video_local_edit_compress_requires_upload_not_red_error():
    user_id = 1701113
    bot.clear_video_editor_pending(user_id)
    query = _press_videoedit(user_id, "videoedit|compress")
    text = _last_text(query)
    assert "gửi video" in text.lower()
    assert "chưa trừ Xu" in text
    assert GENERIC_RED_ERROR not in text

    bot.set_video_editor_pending(
        user_id,
        "menu",
        source_file_id="telegram-file-id",
        source_file_name="demo.mp4",
        source_mime_type="video/mp4",
        requested_action="compress",
    )
    query = _press_videoedit(user_id, "videoedit|compress")
    text = _last_text(query)
    assert "Chỉnh sửa video local đang được chuẩn bị" in text
    assert "chưa trừ Xu" in text
    assert GENERIC_RED_ERROR not in text
    assert _callbacks(_last_markup(query)) == ["menu|main_video", "menu|main"]


def test_video_visible_buttons_do_not_throw_generic_red_error():
    callbacks = _callbacks(bot.main_video_keyboard("vi"))
    for index, callback in enumerate(callbacks):
        user_id = 1701200 + index
        if callback.startswith("vproduct|"):
            query = _press_video_product(user_id, callback)
            assert GENERIC_RED_ERROR not in _last_text(query)
        elif callback.startswith("vpromptlib|"):
            query = _FakeQuery(user_id, callback)
            asyncio.run(bot.handle_video_prompt_library_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
            assert GENERIC_RED_ERROR not in _last_text(query)
        elif callback.startswith("vdownload|"):
            query = _FakeQuery(user_id, callback)
            asyncio.run(bot.handle_video_downloader_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
            assert GENERIC_RED_ERROR not in _last_text(query)
        elif callback.startswith("videodub|"):
            assert callback == "videodub|start|video"
        elif callback == "menu|video_vault":
            text, _markup = bot.localized_menu_content("video_vault", False, "vi", user_id=user_id)
            assert GENERIC_RED_ERROR not in text
        else:
            assert callback == "menu|main"


def test_video_visible_buttons_no_xu_before_confirm():
    source = "\n".join(
        [
            inspect.getsource(bot.main_video_keyboard),
            inspect.getsource(bot.task3d_product_intro_keyboard),
            inspect.getsource(bot.handle_video_product_callback),
            inspect.getsource(bot.handle_video_prompt_library_callback),
            inspect.getsource(bot.handle_video_downloader_callback),
            inspect.getsource(bot.handle_video_editor_callback),
        ]
    )
    for forbidden in ("spend_fixed_credit_info(", "deduct_dynamic_credit(", "charge_user(", "refund_charged_credit("):
        assert forbidden not in source


def test_video_back_returns_to_video_menu():
    for callback in _callbacks(bot.main_video_keyboard("vi")):
        if callback == "menu|main":
            continue
        if callback.startswith("vproduct|"):
            query = _press_video_product(1701300, callback)
            markup = _last_markup(query)
        elif callback.startswith("vpromptlib|"):
            markup = bot.video_prompt_library_keyboard("vi")
        elif callback.startswith("vdownload|"):
            markup = bot.video_downloader_start_keyboard("vi")
        elif callback.startswith("videodub|"):
            markup = bot.video_dubbing_menu_keyboard("vi", "video")
        elif callback == "menu|video_vault":
            _text, markup = bot.localized_menu_content("video_vault", False, "vi", user_id=1701300)
        else:
            continue
        assert "menu|main_video" in _callbacks(markup)


def test_video_ui_task_does_not_touch_voice():
    source = "\n".join([inspect.getsource(bot.main_video_keyboard), inspect.getsource(bot.video_editor_menu_text)])
    assert "voice_hub" not in source
    assert "custom voice" not in source.lower()


def test_video_ui_task_does_not_touch_asr_subtitle():
    labels = _labels(bot.video_dubbing_menu_keyboard("vi", "translation"))
    assert "🎬 Tạo phụ đề tự động" in labels
    assert "📄 Dịch file phụ đề" not in labels
    assert "🧾 Bóc lời thoại" not in labels
    assert "📥 Tải video từ link" not in labels


def test_video_ui_task_does_not_touch_payos():
    source = "\n".join([inspect.getsource(bot.main_video_keyboard), inspect.getsource(bot.handle_video_editor_callback)])
    for forbidden in ("payos", "wallet", "payment", "naptien"):
        assert forbidden not in source.lower()


def test_video_ui_task_does_not_touch_music():
    source = inspect.getsource(bot.main_video_keyboard)
    assert "main_music" not in source
    assert "🎵 Nhạc / Voice / SFX" not in _labels(bot.main_video_keyboard("vi"))


def test_video_ui_task_does_not_touch_image_menu():
    labels = _labels(bot.main_image_keyboard("vi"))
    callbacks = _callbacks(bot.main_image_keyboard("vi"))
    assert "🖼 Tạo ảnh nhanh" in labels
    assert "create_media|quick_image" in callbacks
    assert "vproduct|open|frame_video_local" not in callbacks
