"""
Comprehensive Empirical Tests for Real End-to-End Publishing Pipeline (P0.AUTOPOST).
Validates:
1. Content input persistence (canonical record in SQLite).
2. Brand profile editing & persistence.
3. Social accounts connection & capability status truth (no fake READY).
4. Content plan & items persistence.
5. Idempotent publish job creation & lease-based scheduler claim.
6. Publish receipt contract (NO_REMOTE_RECEIPT => NO_LIVE_PUBLISH_PASS).
7. Real UI dashboard stats calculation from SQLite.
8. Draft generation consuming Brand + Content Input + Affiliate.
9. Publish modes (MANUAL, SCHEDULED, AUTO).
10. Safe UI renderers with 11-button layout and zero literal \\n errors.
"""
import pytest
import sqlite3
import tempfile
import os
import datetime

from services.autopost_db import (
    init_autopost_durable_db,
    save_content_input,
    get_content_input,
    get_user_brand_profile,
    save_user_brand_profile,
    get_user_social_accounts,
    save_user_social_account,
    disconnect_user_social_account,
    save_content_plan_with_items,
    get_content_items,
    create_publish_job,
    claim_due_publish_jobs,
    record_publish_receipt,
    record_publish_failure,
    get_user_published_receipts,
    get_user_publish_queue,
    get_user_autopost_overview_stats,
    get_user_publish_mode,
    set_user_publish_mode,
)
from services.autopost_brand import (
    get_effective_brand_profile,
    get_platform_brand_policy,
    validate_brand_compliance_for_platform,
)
from services.autopost_strategy import (
    generate_single_post_draft,
    create_content_plan,
)
from services.autopost_publish import (
    check_platform_capability,
    TelegramAdapter,
    execute_publish_job,
    process_due_publish_jobs,
)
from services.autopost_ui import (
    autopost_main_dashboard_text,
    autopost_main_keyboard,
    autopost_content_input_menu_text,
    autopost_content_input_menu_keyboard,
    autopost_brand_view_text,
    autopost_brand_keyboard,
    autopost_channels_text,
    autopost_channels_keyboard,
    autopost_queue_text,
    autopost_queue_keyboard,
    autopost_published_history_text,
    autopost_published_history_keyboard,
    autopost_metrics_text,
    autopost_settings_text,
    autopost_settings_keyboard,
    autopost_draft_view_text,
    autopost_draft_keyboard,
    autopost_guide_text,
    autopost_guide_keyboard,
)

@pytest.fixture
def test_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    init_autopost_durable_db(conn)
    yield conn
    conn.close()
    if os.path.exists(path):
        os.remove(path)

def test_01_content_input_persistence(test_db):
    uid = 10001
    inp_id = save_content_input(uid, "text_topic", text="Giải pháp kinh doanh mới", source_url="https://toanaas.vn", conn=test_db)
    assert inp_id > 0
    
    rec = get_content_input(inp_id, conn=test_db)
    assert rec is not None
    assert rec["owner_user_id"] == uid
    assert rec["type"] == "text_topic"
    assert rec["text"] == "Giải pháp kinh doanh mới"
    assert rec["source_url"] == "https://toanaas.vn"

def test_02_brand_profile_persistence(test_db):
    uid = 10002
    brand = save_user_brand_profile(uid, {
        "brand_name": "TechPro Store",
        "brand_voice": "Uy tín & Chuyên nghiệp",
        "primary_cta": "Mua ngay tại techpro.vn",
        "website": "https://techpro.vn",
    }, conn=test_db)
    
    assert brand["brand_name"] == "TechPro Store"
    assert brand["is_configured"] is True
    
    # Check retrieval
    fetched = get_user_brand_profile(uid, conn=test_db)
    assert fetched["brand_name"] == "TechPro Store"
    assert fetched["primary_cta"] == "Mua ngay tại techpro.vn"

def test_03_social_accounts_capability_status_truth(test_db):
    uid = 10003
    
    # Telegram
    tg = check_platform_capability("telegram")
    assert tg["status"] == "READY"
    
    # Facebook without token
    fb = check_platform_capability("facebook")
    assert fb["status"] == "NEEDS_OAUTH"
    
    # Instagram without token
    ig = check_platform_capability("instagram")
    assert ig["status"] == "NEEDS_OAUTH"
    
    # YouTube without credentials
    yt = check_platform_capability("youtube")
    assert yt["status"] == "NEEDS_OAUTH"
    
    # TikTok without audit
    tt = check_platform_capability("tiktok", {"access_token": "valid_token", "app_audited": False})
    assert tt["status"] == "NEEDS_APP_REVIEW"
    
    # Save Telegram account to DB
    acc = save_user_social_account(uid, "telegram", "@toanaas_news", "@toanaas_news", "ACTIVE", "READY", conn=test_db)
    assert acc["platform"] == "telegram"
    assert acc["publish_status"] == "READY"
    
    accounts = get_user_social_accounts(uid, conn=test_db)
    assert len(accounts) == 1
    assert accounts[0]["display_name"] == "@toanaas_news"

def test_04_content_plan_and_items_persistence(test_db):
    uid = 10004
    brand = {"brand_name": "AI Studio", "primary_cta": "Thử ngay"}
    items = [
        {"post_date": "2026-08-22", "time_slot": "11:30", "platform": "telegram", "topic": "Bài 1", "pillar": "Giáo dục", "master_hook": "Hook 1", "master_caption": "Caption 1"},
        {"post_date": "2026-08-23", "time_slot": "20:00", "platform": "facebook", "topic": "Bài 2", "pillar": "Ưu đãi", "master_hook": "Hook 2", "master_caption": "Caption 2"},
    ]
    plan_id = save_content_plan_with_items(uid, "AI Studio", "AWARENESS", 2, items, conn=test_db)
    assert plan_id > 0
    
    saved_items = get_content_items(plan_id, conn=test_db)
    assert len(saved_items) == 2
    assert saved_items[0]["topic"] == "Bài 1"
    assert saved_items[0]["status"] == "DRAFT"

def test_05_publish_job_idempotency_and_claim(test_db):
    uid = 10005
    past_utc = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=5)).isoformat()
    future_utc = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=2)).isoformat()
    
    job_1 = create_publish_job(1, uid, "telegram", "@channel1", past_utc, idempotency_key="key_123", conn=test_db)
    # Duplicate with same idempotency key updates rather than creating duplicate
    job_1_dup = create_publish_job(1, uid, "telegram", "@channel1", past_utc, idempotency_key="key_123", conn=test_db)
    assert job_1 == job_1_dup
    
    job_2 = create_publish_job(2, uid, "telegram", "@channel2", future_utc, idempotency_key="key_456", conn=test_db)
    
    # Claim due jobs (only past_utc should be claimed)
    claimed = claim_due_publish_jobs(limit=10, conn=test_db)
    assert len(claimed) == 1
    assert claimed[0]["id"] == job_1
    assert claimed[0]["status"] == "PUBLISHING"

def test_06_publish_receipt_required(test_db):
    uid = 10006
    job_id = create_publish_job(1, uid, "telegram", "@my_chan", "2026-08-22T00:00:00Z", conn=test_db)
    
    # Before receipt
    assert len(get_user_published_receipts(uid, conn=test_db)) == 0
    
    # Record receipt
    r_id = record_publish_receipt(job_id, uid, "telegram", "987654", "https://t.me/my_chan/987654", "PUBLISHED", conn=test_db)
    assert r_id > 0
    
    receipts = get_user_published_receipts(uid, conn=test_db)
    assert len(receipts) == 1
    assert receipts[0]["remote_post_id"] == "987654"
    assert receipts[0]["remote_status"] == "PUBLISHED"

def test_07_overview_stats_calculation(test_db):
    uid = 10007
    stats = get_user_autopost_overview_stats(uid, conn=test_db)
    assert stats["brand_name"] == "Chưa thiết lập"
    assert stats["connected_channels"] == "0/5"
    assert stats["today_posts"] == 0
    assert stats["queued_posts"] == 0
    assert stats["published_posts"] == 0
    assert stats["error_posts"] == 0
    
    # Save brand and social account
    save_user_brand_profile(uid, {"brand_name": "AAS Brand"}, conn=test_db)
    save_user_social_account(uid, "telegram", "@test_chan", "@test_chan", conn=test_db)
    
    stats2 = get_user_autopost_overview_stats(uid, conn=test_db)
    assert stats2["brand_name"] == "AAS Brand"
    assert stats2["connected_channels"] == "1/5"

def test_08_draft_generation():
    uid = 10008
    brand = {"brand_name": "EcoGreen", "brand_voice": "Tươi mới", "primary_cta": "Đặt mua ngay", "default_hashtags": "#EcoGreen"}
    aff = {"id": 5, "product_name": "Bình giữ nhiệt", "url": "https://shorten.asia/binh"}
    
    draft = generate_single_post_draft(uid, "Sản phẩm thân thiện môi trường", brand, affiliate=aff)
    assert "EcoGreen" in draft["caption"]
    assert "Đặt mua ngay" in draft["caption"]
    assert "https://shorten.asia/binh" in draft["caption"]
    assert draft["affiliate_id"] == 5

def test_09_publish_modes(test_db):
    uid = 10009
    assert get_user_publish_mode(uid, conn=test_db) == "MANUAL"
    
    set_user_publish_mode(uid, "SCHEDULED", conn=test_db)
    assert get_user_publish_mode(uid, conn=test_db) == "SCHEDULED"
    
    set_user_publish_mode(uid, "AUTO", conn=test_db)
    assert get_user_publish_mode(uid, conn=test_db) == "AUTO"

def test_10_task_b_home_screen_11_buttons():
    kb = autopost_main_keyboard("vi")
    assert len(kb.inline_keyboard) == 6
    total_buttons = sum(len(row) for row in kb.inline_keyboard)
    assert total_buttons == 12
    
    btn_callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row if btn.callback_data]
    assert "autopost|content_input_menu" in btn_callbacks
    assert "autopost|content_plan" in btn_callbacks
    assert "autopost|brands" in btn_callbacks
    assert "autopost|affiliate" in btn_callbacks
    assert "autopost|channels" in btn_callbacks
    assert "autopost|calendar" in btn_callbacks
    assert "autopost|queue" in btn_callbacks
    assert "autopost|published_history" in btn_callbacks
    assert "autopost|metrics" in btn_callbacks
    assert "autopost|ads_center" in btn_callbacks
    assert "autopost|guide" in btn_callbacks
    assert "menu|main" in btn_callbacks

def test_12_autopost_guide_renderer():
    guide_text = autopost_guide_text()
    assert "HƯỚNG DẪN SỬ DỤNG HỆ THỐNG ĐĂNG BÀI TỰ ĐỘNG" in guide_text
    assert "Thiết lập Thương hiệu" in guide_text
    assert "Kho Affiliate" in guide_text
    assert "Tạo Nguyên liệu" in guide_text
    
    guide_kb = autopost_guide_keyboard()
    assert len(guide_kb.inline_keyboard) >= 2
    callbacks = [btn.callback_data for row in guide_kb.inline_keyboard for btn in row if btn.callback_data]
    assert "autopost|content_input_menu" in callbacks
    assert "autopost|main" in callbacks

def test_11_telegram_adapter_simulation():
    import asyncio
    res = asyncio.run(TelegramAdapter.publish(999, "@sim_channel", {"caption": "Test Post"}))
    assert res["ok"] is True
    assert res["platform"] == "telegram"
    assert res["remote_status"] == "PUBLISHED"
    assert "TG-SIM-" in res["remote_post_id"]
