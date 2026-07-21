import subprocess

import bot


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]


def test_pkgcombo_home_ui_short_clean():
    text = "\n".join(bot.pricing_packages_lines("vi"))
    assert "🎁 <b>Gói / Combo TOAN AAS</b>" in text
    assert "Chọn cách mua phù hợp" in text
    assert len(bot.pricing_packages_lines("vi")) <= 10
    assert "provider" not in text.lower()
    assert "api" not in text.lower()
    assert "debug" not in text.lower()


def test_pkgcombo_home_has_two_column_layout():
    rows = bot.pricing_packages_keyboard("vi").inline_keyboard
    assert len(rows) == 6
    assert all(len(row) == 2 for row in rows)
    assert [button.text for button in rows[0]] == ["🖼 Gói Ảnh", "🎬 Gói Video"]
    assert [button.text for button in rows[2]] == ["🌐 Phụ đề / Lồng tiếng", "🧠 Prompt / Workflow"]


def test_pkgcombo_home_has_notes_button():
    labels = _labels(bot.pricing_packages_keyboard("vi"))
    callbacks = _callbacks(bot.pricing_packages_keyboard("vi"))
    assert "ℹ️ Lưu ý" in labels
    assert "pkgcombo:notes" in callbacks


def test_pkgcombo_notes_contains_long_explanation():
    text = "\n".join(bot.pricing_pkgcombo_notes_lines("vi"))
    assert "ℹ️ <b>Lưu ý Gói / Combo</b>" in text
    assert "Gói tác vụ dùng trong 30 ngày" in text
    assert "không tạo checkout giả" in text
    assert "pkgcombo:home" in _callbacks(bot.pricing_pkgcombo_notes_keyboard("vi"))


def test_pkgcombo_back_home_returns_previous_or_billing():
    callbacks = _callbacks(bot.pricing_packages_keyboard("vi"))
    assert "pricing|main" in callbacks
    assert "menu|main" in callbacks


def test_pkgcombo_group_image_back_home():
    assert "pkgcombo:home" in _callbacks(bot.pricing_task_package_group_keyboard("image", "vi"))


def test_pkgcombo_group_video_back_home():
    assert "pkgcombo:home" in _callbacks(bot.pricing_task_package_group_keyboard("video", "vi"))


def test_pkgcombo_group_music_back_home():
    assert "pkgcombo:home" in _callbacks(bot.pricing_task_package_group_keyboard("music", "vi"))


def test_pkgcombo_group_voice_back_home():
    assert "pkgcombo:home" in _callbacks(bot.pricing_task_package_group_keyboard("voice", "vi"))


def test_pkgcombo_group_subdub_back_home():
    assert "pkgcombo:home" in _callbacks(bot.pricing_task_package_group_keyboard("subtitle_dub", "vi"))


def test_pkgcombo_group_prompt_back_home():
    assert "pkgcombo:home" in _callbacks(bot.pricing_task_package_group_keyboard("prompt_workflow", "vi"))


def test_pkgcombo_group_combo_back_home():
    assert "pkgcombo:home" in _callbacks(bot.pricing_combo_keyboard("vi"))


def test_pkgcombo_detail_back_returns_correct_group():
    assert bot.package_detail_back_callback("monthly", "image_mini_monthly") == "pkgcombo:group:image"
    assert bot.package_detail_back_callback("monthly", "video_basic_monthly") == "pkgcombo:group:video"


def test_pkgcombo_combo_detail_back_returns_combo_group():
    assert bot.package_detail_back_callback("combo", "combo_ad_video_588k") == "pkgcombo:group:combo"


def test_pkgcombo_payos_back_returns_detail():
    callbacks = _callbacks(bot.package_purchase_checkout_keyboard("https://pay.example", "monthly", "image_mini_monthly"))
    assert "pkgcombo:detail:image_mini_monthly" in callbacks
    assert "pkgcombo:group:image" in callbacks


def test_pkgcombo_large_order_back_returns_origin():
    assert bot.pkgcombo_large_order_back_callback(["detail", "image_mini_monthly"]) == "pkgcombo:detail:image_mini_monthly"
    assert bot.pkgcombo_large_order_back_callback(["combo_detail", "combo_ad_video_588k"]) == "pkgcombo:combo_detail:combo_ad_video_588k"
    assert bot.pkgcombo_large_order_back_callback(["group", "subdub"]) == "pkgcombo:group:subtitle_dub"


def test_pkgcombo_my_packages_back_returns_home():
    callbacks = _callbacks(bot.my_packages_keyboard("vi"))
    assert "pkgcombo:home" in callbacks
    assert "pricing|packages" not in callbacks


def test_pkgcombo_no_public_gift_admin():
    text = "\n".join(bot.pricing_packages_lines("vi") + bot.pricing_pkgcombo_notes_lines("vi"))
    labels = _labels(bot.pricing_packages_keyboard("vi"))
    assert "Mã quà tặng" not in text
    assert "🎟 Mã quà tặng" not in labels


def test_pkgcombo_no_fake_checkout_for_admin_review():
    text = "\n".join(bot.package_purchase_detail_lines("combo", "combo_song_visual_888k"))
    callbacks = _callbacks(bot.package_purchase_manual_keyboard("combo", "combo_song_visual_888k"))
    assert "chưa mở checkout tự động" in text
    assert "Bot chưa tạo đơn" in text
    assert "pkgcombo:large_order:combo_detail:combo_song_visual_888k" in callbacks


def test_pkgcombo_public_no_debug_words():
    text = "\n".join(
        bot.pricing_packages_lines("vi")
        + bot.pricing_pkgcombo_notes_lines("vi")
        + bot.pricing_plans_lines()
        + bot.pricing_combo_lines()
    ).lower()
    for forbidden in ["provider", "api", "ledger", "traceback", "runtimeerror", "payload"]:
        assert forbidden not in text


def test_pkgcombo_no_payos_core_touched():
    changed = subprocess.check_output(["git", "diff", "--name-only", "origin/main", "--"], text=True, encoding="utf-8").splitlines()
    assert "services/payos.py" not in changed
    assert "payos.py" not in changed


def test_pkgcombo_no_wallet_ledger_touched():
    changed = subprocess.check_output(["git", "diff", "--name-only", "origin/main", "--"], text=True, encoding="utf-8").splitlines()
    assert all("wallet" not in path.lower() and "ledger" not in path.lower() for path in changed)
