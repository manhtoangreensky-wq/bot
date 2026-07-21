from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")
ROUTER_SOURCE = (ROOT / "services" / "video_provider_router.py").read_text(encoding="utf-8")


def test_source_locks_scene_based_contract_8s_and_promo_price():
    assert "TASK3D_SCENE_SECONDS = 8" in BOT_SOURCE
    assert "TASK3D_SCENE_COUNT_OPTIONS = (1, 2, 3)" in BOT_SOURCE
    assert "PRODUCT_VIDEO_R9_LIST_PRICE_PER_SCENE_XU = 300" in BOT_SOURCE
    assert "PRODUCT_VIDEO_R9_PROMO_PRICE_PER_SCENE_XU = 200" in BOT_SOURCE
    assert '"estimated_duration_seconds": duration' in BOT_SOURCE
    assert '"duration_note": f"{count} cảnh, khoảng {duration} giây"' in BOT_SOURCE


def test_source_locks_dynamic_scene_menu_and_custom_scene_entry():
    assert 'callback_data="vfinal|scene_count|1"' in BOT_SOURCE
    assert 'callback_data="vfinal|scene_count|2"' in BOT_SOURCE
    assert 'callback_data="vfinal|scene_count|3"' in BOT_SOURCE
    assert 'callback_data="vfinal|scene_custom"' in BOT_SOURCE
    assert 'callback_data="vfinal|upgrade_300"' not in BOT_SOURCE
    assert "1 cảnh khoảng <b>{TASK3D_SCENE_SECONDS} giây</b>" in BOT_SOURCE
    assert "TOAN AAS chỉ trừ Xu khi có MP4 hợp lệ" in BOT_SOURCE


def test_source_sanitizes_addons_from_product_video_quote_and_invoice():
    assert "def product_video_r9_sanitized_addon_state" in BOT_SOURCE
    assert '"product_video_addons_public_locked"' in BOT_SOURCE
    assert '"addons_public_locked": True' in BOT_SOURCE
    assert '"paid_items": []' in BOT_SOURCE
    assert '"addon_fee_xu": 0' in BOT_SOURCE
    assert "Add-on: <b>chưa bán trong hóa đơn Product Video phiên bản này</b>" in BOT_SOURCE
    assert "logo_line_vi" in BOT_SOURCE  # legacy invoice remains, but R9 branch returns before this block.


def test_source_locks_charge_after_valid_mp4_not_after_provider_accept():
    assert "deducted_after_first_provider_accept" not in BOT_SOURCE
    assert "pending_until_valid_mp4" in BOT_SOURCE
    assert "deducted_after_valid_mp4_delivery" in BOT_SOURCE
    assert "def product_video_r9_charge_allowed" in BOT_SOURCE
    assert "valid_mp4_required_before_charge" in BOT_SOURCE
    assert "provider_in_progress_no_charge" in BOT_SOURCE


def test_source_registers_read_only_video_job_finance_debug():
    assert "def video_job_finance_debug_text" in BOT_SOURCE
    assert "async def cmd_video_job_finance_debug" in BOT_SOURCE
    assert 'CommandHandler("video_job_finance_debug", cmd_video_job_finance_debug)' in BOT_SOURCE
    assert "artifact valid for charge" in BOT_SOURCE
    assert "refund/manual review if charged without valid MP4" in BOT_SOURCE


def test_source_has_safe_provider_in_progress_public_copy():
    assert "def product_video_provider_pending_public_copy" in BOT_SOURCE
    assert "Hệ thống đang dựng video. TOAN AAS chưa trừ Xu và chỉ trừ Xu khi có MP4 hợp lệ." in BOT_SOURCE
    assert "product_video_provider_pending_public_copy" in BOT_SOURCE


def test_router_source_locks_pending_task_poll_only_no_new_submit():
    assert '"no_new_submit": bool(pending_task_id or pending_video_id)' in ROUTER_SOURCE
    assert '"poll_existing_task": bool(pending_task_id or pending_video_id)' in ROUTER_SOURCE
    assert '"no_new_submit": bool(poll_existing_task)' in ROUTER_SOURCE
    assert '"poll_existing_task": bool(poll_existing_task)' in ROUTER_SOURCE
    assert "submit_called_flag = not poll_existing_task" in ROUTER_SOURCE
    assert '"provider_submit_called": submit_called_flag' in ROUTER_SOURCE
    assert '"external_provider_spend_prevented": bool(poll_existing_task)' in ROUTER_SOURCE
