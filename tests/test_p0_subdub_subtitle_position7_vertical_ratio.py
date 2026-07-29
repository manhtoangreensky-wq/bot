import asyncio
from types import SimpleNamespace

import bot


VALID_SRT = (
    "1\n"
    "00:00:00,000 --> 00:00:02,000\n"
    "Xin chao TOAN AAS\n"
)


def _callbacks(markup):
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


class FakeMessage:
    def __init__(self, chat_id=950071):
        self.chat_id = chat_id
        self.message_id = 71
        self.sent = []

    async def reply_text(self, text, **kwargs):
        item = {"text": str(text), **kwargs}
        self.sent.append(item)
        return SimpleNamespace(**item)


class FakeQuery:
    def __init__(self, data, user_id=950071):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = FakeMessage(user_id)
        self.answers = []

    async def answer(self, text=None, show_alert=False):
        self.answers.append({"text": text, "show_alert": show_alert})


async def _press(monkeypatch, data, uid=950071):
    edits = []

    async def fake_edit(_query, text, reply_markup=None, parse_mode="HTML"):
        item = {
            "text": str(text),
            "reply_markup": reply_markup,
            "parse_mode": parse_mode,
        }
        edits.append(item)
        return SimpleNamespace(**item)

    monkeypatch.setattr(bot, "safe_edit_or_send", fake_edit)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    query = FakeQuery(data, uid)
    await bot.handle_video_dubbing_callback(
        SimpleNamespace(callback_query=query),
        SimpleNamespace(),
    )
    return edits[-1] if edits else query.message.sent[-1]


def test_position_picker_has_exactly_seven_vertical_slots():
    markup = bot.video_dubbing_subtitle_position_keyboard(
        "vi",
        {"subtitle_position_slot": 2},
    )
    callbacks = _callbacks(markup)
    labels = " | ".join(_labels(markup))

    assert bot.SUBDUB_SUBTITLE_POSITION_COUNT == 7
    assert callbacks.count("videodub|subtitle_position_set|1") == 1
    assert callbacks.count("videodub|subtitle_position_set|7") == 1
    assert len([item for item in callbacks if "subtitle_position_set" in item]) == 7
    assert "Sat duoi" not in labels
    assert "Sát dưới" in labels
    assert "Chính giữa" in labels
    assert "Sát trên" in labels
    position_rows = [
        [button.callback_data for button in row if "subtitle_position_set" in str(button.callback_data or "")]
        for row in markup.inline_keyboard
    ]
    position_rows = [row for row in position_rows if row]
    assert [len(row) for row in position_rows] == [2, 2, 2, 1]
    assert [item for row in position_rows for item in row] == [
        f"videodub|subtitle_position_set|{slot}" for slot in range(7, 0, -1)
    ]


def test_position_button_appears_only_for_outputs_with_visible_subtitles():
    create = _callbacks(
        bot.video_dubbing_confirm_keyboard(
            "vi",
            {"mode": bot.VIDEO_SUBTITLE_MODE_CREATE, "output_type": "burn"},
        )
    )
    translate = _callbacks(
        bot.video_dubbing_confirm_keyboard(
            "vi",
            {"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE, "output_type": "burn"},
        )
    )
    dub = _callbacks(
        bot.video_dubbing_confirm_keyboard(
            "vi",
            {"mode": bot.VIDEO_SUBTITLE_MODE_DUB, "output_type": "video"},
        )
    )
    combo = _callbacks(
        bot.subtitle_plus_dub_confirm_keyboard(
            "vi",
            {
                "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
                "output_type": "video_subtitle",
            },
        )
    )
    original = _callbacks(
        bot.video_dubbing_original_subtitle_confirm_keyboard(
            "vi",
            {"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE},
        )
    )

    assert "videodub|subtitle_position" in create
    assert "videodub|subtitle_position" in translate
    assert "videodub|subtitle_position" not in dub
    assert "videodub|subtitle_position" in combo
    assert "videodub|subtitle_position" in original


def test_new_subdub_lane_starts_with_position_two_of_seven(monkeypatch):
    monkeypatch.setattr(
        bot,
        "get_subdub_lane_readiness",
        lambda *_args, **_kwargs: {"effective_ready": True},
    )
    monkeypatch.setattr(bot, "current_product_context", lambda _uid: "")
    monkeypatch.setattr(bot, "enter_product_context", lambda *_args, **_kwargs: {})

    for index, mode in enumerate(
        (
            bot.VIDEO_SUBTITLE_MODE_CREATE,
            bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
            bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        ),
        start=1,
    ):
        uid = 950080 + index
        bot.clear_video_dubbing_pending(uid)
        result = asyncio.run(_press(monkeypatch, f"videodub|type|{mode}", uid))
        state = bot.get_video_dubbing_pending(uid)

        assert state["step"] == "source"
        assert bot.subdub_subtitle_position_slot(state) == 2
        assert state["subtitle_position"] == "slot_2"
        callbacks = _callbacks(result["reply_markup"])
        if mode == bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB:
            assert "videodub|path|has_subtitle" in callbacks
            assert "videodub|path|no_subtitle" in callbacks
        else:
            assert "videodub|source_upload" in callbacks


def test_seven_ass_positions_are_centered_safe_and_evenly_spaced(monkeypatch):
    monkeypatch.setattr(
        bot,
        "resolve_subdub_subtitle_font",
        lambda _style: {
            "ok": True,
            "family": "Arial",
            "path": "fixture.ttf",
            "blocker": "",
        },
    )
    points = []
    for slot in range(1, 8):
        style = bot.subdub_normalize_style(
            {
                "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
                "output_type": "burn",
                "video_width": 1080,
                "video_height": 1920,
                "subtitle_position_slot": slot,
            }
        )
        points.append(bot.subdub_subtitle_position_point(style))

    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    gaps = [ys[index] - ys[index + 1] for index in range(6)]

    assert xs == [540] * 7
    assert ys == sorted(ys, reverse=True)
    assert ys[0] < 1920
    assert ys[-1] > 0
    assert max(gaps) - min(gaps) <= 1

    ass = bot.subdub_generate_ass_from_srt(
        VALID_SRT,
        {
            "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
            "output_type": "burn",
            "video_width": 1080,
            "video_height": 1920,
            "subtitle_position_slot": 4,
        },
    )
    assert r"\an2\pos(540," in ass
    assert "; subtitle_position_slot: 4" in ass


def test_vertical_subtitle_font_is_exactly_two_points_larger(monkeypatch):
    monkeypatch.setattr(
        bot,
        "resolve_subdub_subtitle_font",
        lambda _style: {
            "ok": True,
            "family": "Arial",
            "path": "fixture.ttf",
            "blocker": "",
        },
    )
    style = bot.subdub_normalize_style(
        {
            "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
            "output_type": "burn",
            "video_width": 1080,
            "video_height": 1920,
        }
    )

    assert style["render_size"] == 46
    assert style["subtitle_vertical_font_increment"] == 2


def test_vertical_video_fit_preserves_source_aspect_ratio():
    filters = ",".join(
        bot.subdub_video_fit_filters(
            {"video_width": 1080, "video_height": 1920}
        )
    )

    assert bot.subdub_aspect_ratio_close(1080, 1920, 1080, 1920)
    assert "crop=" not in filters
    assert "pad=" not in filters
    assert "setsar=1" in filters
    if "scale=" in filters:
        assert "force_original_aspect_ratio=decrease" in filters


def test_position_callbacks_return_to_same_create_confirm_without_execution(monkeypatch):
    uid = 950072
    bot.clear_video_dubbing_pending(uid)
    bot.set_video_dubbing_pending(
        uid,
        "confirm",
        mode=bot.VIDEO_SUBTITLE_MODE_CREATE,
        process_type=bot.VIDEO_SUBTITLE_MODE_CREATE,
        video_processing_mode=bot.VIDEO_SUBTITLE_MODE_CREATE,
        output_type="burn",
        origin="translation",
        subtitle_position_slot=2,
    )

    async def forbidden_pipeline(*_args, **_kwargs):
        raise AssertionError("position callback must not execute the pipeline")

    monkeypatch.setattr(bot, "execute_video_dubbing_pipeline", forbidden_pipeline)

    picker = asyncio.run(_press(monkeypatch, "videodub|subtitle_position", uid))
    state = bot.get_video_dubbing_pending(uid)
    assert state["step"] == "subtitle_position"
    assert state["subtitle_position_return_step"] == "confirm"
    assert "Vị trí phụ đề" in picker["text"]

    returned = asyncio.run(
        _press(monkeypatch, "videodub|subtitle_position_set|5", uid)
    )
    state = bot.get_video_dubbing_pending(uid)
    assert state["step"] == "confirm"
    assert bot.subdub_subtitle_position_slot(state) == 5
    assert state["subtitle_position"] == "slot_5"
    assert "videodub|final" in _callbacks(returned["reply_markup"])
    assert "videodub|subtitle_position" in _callbacks(returned["reply_markup"])


def test_position_callback_returns_to_original_subtitle_confirm(monkeypatch):
    uid = 950073
    bot.clear_video_dubbing_pending(uid)
    bot.set_video_dubbing_pending(
        uid,
        "original_subtitle_confirm",
        mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        process_type=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        video_processing_mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        output_type="burn",
        origin="translation",
        subtitle_position_slot=2,
    )

    asyncio.run(_press(monkeypatch, "videodub|subtitle_position", uid))
    returned = asyncio.run(
        _press(monkeypatch, "videodub|subtitle_position_set|6", uid)
    )
    state = bot.get_video_dubbing_pending(uid)

    assert state["step"] == "original_subtitle_confirm"
    assert bot.subdub_subtitle_position_slot(state) == 6
    assert "videodub|confirm_original_subtitle" in _callbacks(
        returned["reply_markup"]
    )
