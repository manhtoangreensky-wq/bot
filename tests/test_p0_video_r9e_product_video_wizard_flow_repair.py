from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _callback_block(action: str) -> str:
    marker = f'if action == "{action}":'
    assert marker in BOT_SOURCE
    tail = BOT_SOURCE.split(marker, 1)[1]
    next_if = tail.find("\n    if action ")
    return tail if next_if == -1 else tail[:next_if]


def test_b14_quality_always_routes_to_scene_count_before_invoice():
    block = _callback_block("b14_quality")
    assert "video_b14_clear_runtime_selection_for_package(session)" in block
    assert 'task3d_session_step(uid, "b14_scene_count"' in block
    assert "video_b14_scene_count_text(session, lang)" in block
    assert "video_b14_invoice_text" not in block
    assert "video_b14_prepare_project_for_invoice" not in block


def test_scene_count_is_required_before_invoice_or_confirm():
    invoice_block = _callback_block("b14_invoice_screen")
    confirm_block = _callback_block("b14_confirm")
    assert 'if not draft.get("b14_scene_count_selected"):' in invoice_block
    assert 'if not draft.get("b14_scene_count_selected"):' in confirm_block
    assert "video_b14_scene_count_text(session, lang)" in invoice_block
    assert "video_b14_scene_count_text(session, lang)" in confirm_block


def test_scene_selection_creates_invoice_only_after_count_selected():
    block = _callback_block("b14_scene_count")
    assert 'draft["b14_scene_count"] = count' in block
    assert 'draft["b14_scene_count_selected"] = True' in block
    assert "video_b14_prepare_project_for_invoice(uid, session)" in block
    assert 'task3d_session_step(uid, "b14_invoice"' in block


def test_stale_runtime_state_and_addons_are_cleared_for_new_package():
    assert "def video_b14_clear_runtime_selection_for_package" in BOT_SOURCE
    assert '"b14_scene_count_selected"' in BOT_SOURCE
    assert '"b14_invoice"' in BOT_SOURCE
    assert '"b14_queue_job_id"' in BOT_SOURCE
    assert "def video_b14_lock_product_video_addons" in BOT_SOURCE
    assert '"voice_enabled": False' in BOT_SOURCE
    assert '"music_enabled": False' in BOT_SOURCE
    assert '"subtitle_enabled": False' in BOT_SOURCE
    assert '"logo_enabled": False' in BOT_SOURCE


def test_invoice_has_no_stale_addons_or_fake_scene_discount():
    assert "PRODUCT_VIDEO_R9E_ADDONS_LOCKED = True" in BOT_SOURCE
    assert "PRODUCT_VIDEO_R9E_ADDONS_LOCK_COPY_VI" in BOT_SOURCE
    assert "Hóa đơn này chỉ tính video chính" in BOT_SOURCE
    assert "def video_b14_scene_discount_percent" in BOT_SOURCE
    discount_block = BOT_SOURCE.split("def video_b14_scene_discount_percent", 1)[1].split("def video_b14_invoice_breakdown", 1)[0]
    assert "return 0" in discount_block


def test_confirm_blocks_when_provider_submit_switch_is_locked_before_job_submit():
    block = _callback_block("b14_confirm")
    switch_index = block.index("product_video_submit_switch_detail()")
    prepare_index = block.index("video_b14_prepare_project_for_invoice")
    confirm_index = block.index("confirm_video_project_invoice(")
    assert switch_index < prepare_index < confirm_index
    assert "PRODUCT_VIDEO_R9E_PROVIDER_LOCK_COPY_VI" in block
    assert '"b14_provider_submit_locked"' in block


def test_confirm_never_charges_wallet_before_valid_mp4_delivery():
    block = _callback_block("b14_confirm")
    assert "use_wallet=False" in block
    assert '"xu_charged": 0' in block
    assert '"charge_policy": "after_valid_mp4_delivery"' in block
    assert "TOAN AAS chỉ trừ Xu khi MP4 hợp lệ đã được gửi thành công" in BOT_SOURCE


def test_public_status_copy_has_no_provider_elapsed_or_poll_count_words():
    block = BOT_SOURCE.split("def video_b14_provider_rendering_block", 1)[1].split("def video_b14_primary_alive_attempt", 1)[0]
    assert "Đã gửi yêu cầu dựng video, đang chờ kết quả." in block
    assert "Hệ thống đang dựng video. TOAN AAS chưa trừ Xu" in BOT_SOURCE
    assert "Đang chờ provider xử lý" not in BOT_SOURCE
    assert "Đã xử lý:" not in block
    assert "Đã kiểm tra:" not in block
