import json
import os
import subprocess
import tempfile

import pytest

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


def _allowed_p0_18o_engine_guard_path(path: str, changed: list[str]) -> bool:
    normalized = {item.replace("\\", "/") for item in changed}
    branch = subprocess.check_output(["git", "branch", "--show-current"], text=True, encoding="utf-8").strip()
    video_allowed = (
        (branch.startswith("hotfix/p0-18o-") or "tests/test_p0_18o_lock_video_flows_real_engine_all_products.py" in normalized)
        and path.replace("\\", "/") in {"services/video_project_queue.py", "services/video_final_output.py"}
    )
    video_engine_allowed = (
        (branch.startswith("hotfix/p0-18p-") or "tests/test_p0_18p_connect_real_video_engine_after_final_output_gate.py" in normalized)
        and path.replace("\\", "/") in {"services/video_final_output.py", "services/video_real_render_connector.py"}
    )
    video_final_delivery_allowed = (
        (
            branch.startswith("hotfix/p0-18r-")
            or "tests/test_p0_18r_real_video_engine_final_mp4_delivery_all_products.py" in normalized
        )
        and path.replace("\\", "/")
        in {"services/video_final_output.py", "services/video_real_render_connector.py", "services/video_project_queue.py"}
    )
    video_provider_config_allowed = (
        (
            branch.startswith("hotfix/p0-18s1-")
            or "tests/test_p0_18s1_video_provider_config_bootstrap_clean_no_provider_ux.py" in normalized
        )
        and path.replace("\\", "/")
        in {
            "providers/video_generic_http_provider.py",
            "services/video_provider_router.py",
            "services/video_real_render_connector.py",
        }
    )
    subdub_allowed = (
        (branch.startswith("hotfix/p0-19k-") or "tests/test_p0_19k_complete_subdub_flows_hardsub_cover_voice_gender_entry_fix.py" in normalized)
        and path.replace("\\", "/") == "services/subtitle_dub_product_pipeline.py"
    )
    return video_allowed or video_engine_allowed or video_final_delivery_allowed or video_provider_config_allowed or subdub_allowed


def _current_branch_name():
    for key in ("GITHUB_HEAD_REF", "GITHUB_REF_NAME", "BRANCH_NAME"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return subprocess.check_output(["git", "branch", "--show-current"], text=True, encoding="utf-8").strip()


def _is_finance_pricing_guard_scope(changed: list[str]) -> bool:
    branch = _current_branch_name().lower()
    branch_tokens = (
        "p0-21d",
        "p0-21e",
        "finance",
        "pricing",
        "tax",
        "accounting",
        "dashboard",
        "packages",
        "combos",
    )
    if any(token in branch for token in branch_tokens):
        return True
    normalized = {path.replace("\\", "/").lower() for path in changed}
    task_files = {
        "tests/test_p0_21d_expand_product_packages_combos_many_products.py",
        "tests/test_p0_21e_tax_payment_accounting_business_dashboard.py",
        "tests/test_p0_21e2_admin_finance_routing_editable_vat_cit.py",
    }
    return bool(normalized & task_files)


def _fresh_db(monkeypatch):
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(bot, "DB_FILE", db_path)
    bot.init_db()
    return db_path


def _public_monthly():
    return {
        code: entry
        for code, entry in bot.package_catalog_payload()["monthly"].items()
        if entry.get("public") is not False
    }


def _group_entries(group):
    return {
        code: entry
        for code, entry in _public_monthly().items()
        if entry.get("group") == group
    }


def _public_combos():
    return {
        code: entry
        for code, entry in bot.package_catalog_payload()["combos"].items()
        if entry.get("public") is not False
    }


def test_p0_21d_package_menu_has_product_groups():
    labels = _labels(bot.pricing_packages_keyboard("vi")) + _labels(bot.pricing_plans_keyboard("vi"))
    callbacks = set(_callbacks(bot.pricing_packages_keyboard("vi")) + _callbacks(bot.pricing_plans_keyboard("vi")))
    for expected in ["🖼 Gói Ảnh", "🎬 Gói Video", "🎵 Gói Nhạc", "🎙 Gói Voice", "🌐 Phụ đề / Lồng tiếng", "🧠 Prompt / Workflow"]:
        assert expected in labels
    for group in ["image", "video", "music", "voice", "subtitle_dub", "prompt_workflow"]:
        assert bot.pkgcombo_group_callback(group) in callbacks


def test_p0_21d_image_packages_have_multiple_tiers():
    entries = _group_entries("image")
    assert len(entries) == 5
    text = "\n".join(bot.pricing_task_package_group_lines("image"))
    for expected in ["Ảnh Mini", "Ảnh Cơ bản", "Ảnh Bán hàng", "Ảnh Chuyên nghiệp", "Ảnh Doanh nghiệp"]:
        assert expected in text


def test_p0_21d_video_packages_have_multiple_tiers():
    entries = _group_entries("video")
    assert len(entries) == 5
    assert entries["video_pro_monthly"]["manual"] is True
    assert entries["video_studio_monthly"]["manual"] is True
    text = "\n".join(bot.pricing_task_package_group_lines("video"))
    for expected in ["Video Mini", "Video Cơ bản", "Video Bán hàng", "Video Chuyên nghiệp", "Video Studio"]:
        assert expected in text


def test_p0_21d_music_packages_have_multiple_tiers():
    entries = _group_entries("music")
    assert len(entries) == 5
    assert all(entry["manual"] is True for entry in entries.values())
    text = "\n".join(bot.pricing_task_package_group_lines("music"))
    for expected in ["Nhạc nền Mini", "Nhạc nền Creator", "Bài hát Có Lời", "Nhạc Shop/Quảng cáo", "Nhạc Studio"]:
        assert expected in text


def test_p0_21d_voice_packages_have_multiple_tiers():
    entries = _group_entries("voice")
    assert len(entries) == 5
    assert all(entry["manual"] is True for entry in entries.values())
    text = "\n".join(bot.pricing_task_package_group_lines("voice"))
    for expected in ["TTS Mini", "TTS Nội dung", "Voice Shop", "Voice Creator", "Voice Pro"]:
        assert expected in text


def test_p0_21d_subtitle_dub_packages_have_multiple_tiers():
    entries = _group_entries("subtitle_dub")
    assert len(entries) == 5
    assert all(entry["manual"] is True for entry in entries.values())
    text = "\n".join(bot.pricing_task_package_group_lines("subtitle_dub"))
    for expected in ["Phụ đề Mini", "Dịch phụ đề", "Lồng tiếng Cơ bản", "Lồng tiếng Đa ngôn ngữ", "Studio Dịch Video"]:
        assert expected in text


def test_p0_21d_prompt_workflow_packages_have_multiple_tiers():
    entries = _group_entries("prompt_workflow")
    assert len(entries) == 4
    text = "\n".join(bot.pricing_task_package_group_lines("prompt_workflow"))
    for expected in ["Prompt Mini", "Storyboard Creator", "Workflow Shop", "Workflow Pro"]:
        assert expected in text


def test_p0_21d_combo_menu_has_use_case_groups():
    combos = _public_combos()
    assert len(combos) == 12
    text = "\n".join(bot.pricing_combo_lines())
    for expected in [
        "Combo video quảng cáo",
        "Combo shop bán hàng",
        "Combo MV nhạc",
        "Combo dịch/lồng tiếng",
        "Combo khóa học",
        "Combo TikTok/Reels",
        "Combo ra mắt sản phẩm",
        "Combo doanh nghiệp nhỏ",
        "Order riêng admin",
    ]:
        assert expected in text


def test_p0_21d_combo_video_ads_has_full_components():
    text = "\n".join(bot.package_purchase_detail_lines("combo", "combo_ad_video_588k"))
    for expected in ["1 video 3-5 cảnh", "3-5 ảnh", "voice", "nhạc nền", "phụ đề"]:
        assert expected in text


def test_p0_21d_combo_music_mv_has_music_voice_visual_subtitle():
    text = "\n".join(bot.package_purchase_detail_lines("combo", "combo_song_visual_888k"))
    for expected in ["nhạc có lời", "ảnh/video visual", "lyric/subtitle", "voice hát", "video lyric/MV"]:
        assert expected in text


def test_p0_21d_combo_course_has_video_voice_subtitle_assets():
    text = "\n".join(bot.package_purchase_detail_lines("combo", "combo_mini_course_1888k"))
    for expected in ["video bài học", "voice/TTS", "phụ đề", "slide/ảnh", "nhạc nền"]:
        assert expected in text


def test_p0_21d_combo_translation_dub_has_video_subtitle_dub():
    text = "\n".join(bot.package_purchase_detail_lines("combo", "combo_translate_dub_888k"))
    for expected in ["video dịch phụ đề", "video lồng tiếng", "phụ đề đa ngôn ngữ", "voice"]:
        assert expected in text


def test_p0_21d_each_package_once_per_month_preserved(monkeypatch):
    db_path = _fresh_db(monkeypatch)
    try:
        user_id = "p0_21d_package_once"
        result = bot.grant_user_package(user_id, "image_mini_monthly", "monthly", "admin", 30, "pytest")
        assert result["ok"] is True
        assert bot.user_bought_package_this_month(user_id, "image_mini_monthly", "monthly") is True
        assert "1 lần/tháng" in bot.package_same_month_guard_text()
    finally:
        os.remove(db_path)


def test_p0_21d_each_combo_once_per_month_preserved(monkeypatch):
    db_path = _fresh_db(monkeypatch)
    try:
        user_id = "p0_21d_combo_once"
        result = bot.grant_user_package(user_id, "combo_ad_video_588k", "combo", "admin", 0, "pytest")
        assert result["ok"] is True
        assert bot.user_bought_package_this_month(user_id, "combo_ad_video_588k", "combo") is True
    finally:
        os.remove(db_path)


def test_p0_21d_large_package_routes_admin_review():
    entry = bot.package_catalog_entry("video_studio_monthly", "monthly")
    assert entry["manual"] is True
    assert bot.package_entry_auto_checkout_enabled(entry) is False
    text = "\n".join(bot.package_purchase_detail_lines("monthly", "video_studio_monthly"))
    assert "cần admin xác nhận" in text
    assert "Bot chưa tạo đơn" in text


def test_p0_21d_abnormal_order_routes_admin_review(monkeypatch):
    db_path = _fresh_db(monkeypatch)
    try:
        user_id = "p0_21d_abnormal"
        code = "combo_product_review_888k"
        amount = bot.package_purchase_price_vnd("combo", code)
        order_code = "210400001"
        metadata = {
            "type": "package_purchase",
            "payment_type": "combo_purchase",
            "package_type": "combo",
            "package_code": code,
        }
        bot.create_order(
            order_code,
            user_id,
            amount,
            0,
            order_type="package_purchase",
            plan_id=code,
            plan_name="Combo Review",
            metadata_json=json.dumps(metadata, ensure_ascii=False),
        )
        processed, desc, info = bot.process_payos_paid_order(order_code, amount - 1000, webhook_currency="VND")
        assert processed is False
        assert desc == "package_order_flagged"
        assert info["flagged"] is True
    finally:
        os.remove(db_path)


def test_p0_21d_no_fake_checkout_for_manual_combo():
    entry = bot.package_catalog_entry("combo_song_visual_888k", "combo")
    assert entry["manual"] is True
    assert bot.package_entry_auto_checkout_enabled(entry) is False
    text = "\n".join(bot.package_purchase_detail_lines("combo", "combo_song_visual_888k"))
    assert "chưa mở checkout tự động" in text
    assert "Bot chưa tạo đơn" in text
    callbacks = _callbacks(bot.package_purchase_manual_keyboard("combo", "combo_song_visual_888k"))
    assert "pkgcombo:large_order:combo_detail:combo_song_visual_888k" in callbacks
    assert "menu|support" in callbacks


def test_p0_21d_gift_code_admin_only_preserved():
    labels = _labels(bot.billing_promotions_keyboard("vi"))
    callbacks = _callbacks(bot.billing_promotions_keyboard("vi"))
    assert "🎟 Mã quà tặng" not in labels
    assert "pricing|gift_code" not in callbacks
    assert "🎟 Mã quà tặng" in _labels(bot.finance_admin_keyboard())


def test_p0_21d_public_discount_code_preserved():
    labels = _labels(bot.billing_promotions_keyboard("vi"))
    callbacks = _callbacks(bot.billing_promotions_keyboard("vi"))
    assert "🎁 Nhập mã ưu đãi" in labels
    assert "pricing|promo_apply" in callbacks
    assert "/promo FIRST30" in "\n".join(bot.billing_promo_apply_lines("vi"))


def test_p0_21d_menu_not_one_huge_message():
    assert len("\n".join(bot.pricing_plans_lines())) < 3200
    for group in ["image", "video", "music", "voice", "subtitle_dub", "prompt_workflow"]:
        assert len("\n".join(bot.pricing_task_package_group_lines(group))) < 3600
    assert len(bot.chunk_pricing_lines(bot.pricing_combo_lines(), limit=3600)) >= 1


def test_p0_21d_prices_end_with_8_when_cash_price():
    entries = list(_public_monthly().values()) + list(_public_combos().values())
    for entry in entries:
        price = int(entry.get("price_vnd") or 0)
        if price <= 0:
            assert entry.get("manual") is True
            continue
        assert price % 10000 == 8000


def test_p0_21d_unit_prices_read_from_config(monkeypatch):
    original = bot.package_catalog_entry("image_mini_monthly", "monthly")
    monkeypatch.setattr(bot, "XU_TO_VND", int(bot.XU_TO_VND or 100) * 2)
    changed = bot.package_catalog_entry("image_mini_monthly", "monthly")
    assert changed["retail_vnd"] == original["retail_vnd"] * 2
    assert changed["price_vnd"] != original["price_vnd"]


def test_p0_21d_discount_range():
    for code, entry in _public_monthly().items():
        if entry.get("legacy"):
            continue
        assert 10 <= int(entry["discount_percent"]) <= 30, code
    for code, entry in _public_combos().items():
        if int(entry.get("price_vnd") or 0) <= 0:
            continue
        assert 20 <= int(entry["discount_percent"]) <= 30, code


def test_p0_21d_does_not_touch_engines():
    try:
        changed = subprocess.check_output(
            ["git", "diff", "--name-only", "origin/main", "--"],
            text=True,
            encoding="utf-8",
        ).splitlines()
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"git diff unavailable: {exc}")
    if not _is_finance_pricing_guard_scope(changed):
        pytest.skip("Finance/Pricing engine guard is not active for this branch")
    forbidden_prefixes = (
        "providers/",
        "services/subtitle",
        "services/video",
        "video_multiscene_engine.py",
        "local_worker.py",
        "migrations/",
        "web/",
    )
    offenders = [path for path in changed if path.startswith(forbidden_prefixes) and not _allowed_p0_18o_engine_guard_path(path, changed)]
    assert offenders == []
