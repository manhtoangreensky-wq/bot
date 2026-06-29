import subprocess

import pytest

import bot


def _callbacks(markup):
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def test_pricing_back_routing_matrix():
    assert "pricing|main" in _callbacks(bot.pricing_catalog_keyboard("vi"))
    assert "pricing|main" in _callbacks(bot.pricing_packages_keyboard("vi"))
    assert "pricing|main" in _callbacks(bot.member_policy_keyboard("vi"))
    assert "pricing|catalog" in _callbacks(bot.pricing_detail_keyboard("video", "vi"))


def test_guide_back_routing_matrix():
    default_callbacks = _callbacks(bot.guide_keyboard("", "vi"))
    pricing_callbacks = _callbacks(
        bot.guide_keyboard("", "vi", back_callback="pricing|main", back_label="⬅️ Nạp Xu / Bảng giá")
    )
    assert "menu|main_guide" in default_callbacks
    assert "pricing|main" in pricing_callbacks
    assert "menu|main_guide" not in pricing_callbacks


def test_packages_back_returns_pricing_menu():
    callbacks = _callbacks(bot.pricing_plans_keyboard("vi"))
    assert "pkgcombo:home" in callbacks
    assert "pricing|packages" not in callbacks


def test_combo_back_returns_pricing_menu():
    callbacks = _callbacks(bot.pricing_combo_keyboard("vi"))
    assert "pkgcombo:home" in callbacks
    assert "pricing|packages" not in callbacks


def test_public_menu_hides_gift_code_admin_only():
    labels = _labels(bot.billing_promotions_keyboard("vi"))
    callbacks = _callbacks(bot.billing_promotions_keyboard("vi"))
    assert "🎟 Mã quà tặng" not in labels
    assert "pricing|gift_code" not in callbacks
    assert "Mã quà tặng: chỉ admin quản lý/cấp phát" in "\n".join(bot.pricing_hub_lines("vi"))


def test_admin_menu_has_gift_code_management():
    labels = _labels(bot.finance_admin_keyboard())
    callbacks = _callbacks(bot.finance_admin_keyboard())
    gift_labels = _labels(bot.admin_gift_code_keyboard())
    gift_callbacks = _callbacks(bot.admin_gift_code_keyboard())
    assert "🎟 Mã quà tặng" in labels
    assert "menu|admin_gift_codes" in callbacks
    assert "🎟 Tạo mã quà tặng" in gift_labels
    assert "📋 Danh sách mã" in gift_labels
    assert "🚫 Tắt mã" in gift_labels
    assert "📊 Lịch sử dùng mã" in gift_labels
    assert all(callback.startswith("menu|admin_gift") or callback in {"menu|finance", "menu|main"} for callback in gift_callbacks)


def test_public_voucher_entry_still_available():
    labels = _labels(bot.billing_promotions_keyboard("vi"))
    callbacks = _callbacks(bot.billing_promotions_keyboard("vi"))
    assert "🎁 Nhập mã ưu đãi" in labels
    assert "pricing|promo_apply" in callbacks
    promo_text = "\n".join(bot.billing_promo_apply_lines("vi"))
    assert "/promo FIRST30" in promo_text


def test_monthly_packages_rebuilt_current_products():
    text = "\n".join(bot.pricing_plans_lines())
    labels = _labels(bot.pricing_plans_keyboard("vi"))
    for expected in [
        "Gói Ảnh",
        "Gói Video",
        "Gói Nhạc",
        "Gói Voice",
        "Phụ đề / Lồng tiếng",
        "Prompt / Workflow",
    ]:
        assert expected in text
    assert "🖼 Gói Ảnh" in labels
    assert "🎬 Gói Video" in labels
    mixed_text = "\n".join(bot.pricing_task_package_group_lines("mixed"))
    assert "🟢 Gói Cơ bản — 98k / 30 ngày" in mixed_text
    assert "🔴 Gói Doanh nghiệp nhỏ — 888k / 30 ngày" in mixed_text


def test_combo_packages_rebuilt_by_use_case():
    text = "\n".join(bot.pricing_combo_lines())
    for expected in [
        "Combo Video Quảng Cáo Sản Phẩm Mini",
        "Combo Affiliate / Review Sản Phẩm",
        "Combo Ra Mắt Sản Phẩm",
        "Combo MV Nhạc / Ca Khúc",
        "Combo Khóa Học Mini",
        "Combo Dịch Video Đa Ngôn Ngữ",
        "Combo Nội Dung Hàng Ngày",
        "Combo Shop Bán Hàng 30 Ngày",
        "Combo Doanh Nghiệp Nhỏ",
    ]:
        assert expected in text
    assert "Combo Ưu Đãi TikTok" not in text


def test_package_combo_copy_distinguishes_xu_monthly_combo_member():
    text = "\n".join(bot.pricing_hub_lines("vi") + bot.pricing_packages_lines("vi") + bot.pricing_pkgcombo_notes_lines("vi"))
    assert "Nạp Xu: tự do" in text
    assert "Gói tác vụ" in text
    assert "Combo trọn gói" in text
    assert "Thành viên: hạng khách hàng" in text
    assert "Mã quà tặng: chỉ admin quản lý/cấp phát" in text


def test_combo_buttons_do_not_create_purchase_without_backend_product_id():
    callbacks = _callbacks(bot.pricing_combo_keyboard("vi"))
    manual_codes = {"combo_song_visual_888k", "combo_mini_course_1888k", "combo_translate_dub_888k", "combo_custom_order"}
    for code in manual_codes:
        assert f"pkgcombo:combo_detail:{code}" in callbacks
        detail = "\n".join(bot.package_purchase_detail_lines("combo", code))
        assert "chưa mở checkout tự động" in detail
        assert "Bot chưa tạo đơn" in detail


def test_no_engine_files_touched_for_pricing_combo_task():
    try:
        changed = subprocess.check_output(
            ["git", "diff", "--name-only", "origin/main", "--"],
            text=True,
            encoding="utf-8",
        ).splitlines()
    except Exception as exc:  # pragma: no cover - local git may be unavailable in some runners
        pytest.skip(f"git diff unavailable: {exc}")
    forbidden_prefixes = (
        "providers/",
        "local_worker.py",
        "migrations/",
        "web/",
    )
    forbidden_names = {
        "providers/key4u_provider.py",
        "providers/video_downloader_provider.py",
    }
    offenders = [
        path
        for path in changed
        if path in forbidden_names or path.startswith(forbidden_prefixes)
    ]
    assert offenders == []


def test_pricing_combo_ui_no_technical_words():
    text = "\n".join(
        bot.pricing_hub_lines("vi")
        + bot.pricing_packages_lines("vi")
        + bot.pricing_plans_lines()
        + bot.pricing_combo_lines()
    ).lower()
    for forbidden in ["provider", "api", "backend", "ffmpeg", "traceback", "runtimeerror", "payload"]:
        assert forbidden not in text
