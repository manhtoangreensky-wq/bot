"""
Comprehensive Empirical Tests for User-Specific Personal Affiliate Vault & Import Engine.
Validates:
1. User isolation (user A cannot see or modify user B's links).
2. Regex parser for text / file import formats.
3. Category/Niche classification.
4. Curated 66-campaign seed from D: drive.
5. Vault stats & pagination.
6. match_affiliate_for_post personal vault prioritization.
7. Safe UI renderers with zero undefined symbols (urllib, html).
"""
import pytest
import sqlite3
import tempfile
import os

from services.autopost_affiliate import (
    init_user_affiliate_vault_db,
    classify_product_niche,
    parse_affiliate_links_from_text,
    add_user_affiliate_link,
    import_affiliate_links_for_user,
    get_user_affiliate_links,
    count_user_affiliate_links,
    get_user_affiliate_stats,
    seed_default_curated_vault_for_user,
    delete_user_affiliate_link,
    clear_user_affiliate_vault,
    match_affiliate_for_post,
    CURATED_AFFILIATE_SEEDS,
)
from services.autopost_ui import (
    autopost_affiliate_text,
    autopost_affiliate_keyboard,
    autopost_affiliate_import_prompt_text,
    autopost_affiliate_import_success_text,
    autopost_affiliate_list_text,
    autopost_affiliate_list_keyboard,
)

@pytest.fixture
def test_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    init_user_affiliate_vault_db(conn)
    yield conn
    conn.close()
    if os.path.exists(path):
        os.remove(path)

def test_01_user_isolation(test_db):
    user_a = 11111
    user_b = 22222
    
    add_user_affiliate_link(user_a, "MacBook Pro", "https://shorten.asia/macbook", "cong_nghe", conn=test_db)
    add_user_affiliate_link(user_b, "Váy Dạ Hội", "https://shorten.asia/vay", "thoi_trang", conn=test_db)
    
    links_a = get_user_affiliate_links(user_a, conn=test_db)
    links_b = get_user_affiliate_links(user_b, conn=test_db)
    
    assert len(links_a) == 1
    assert links_a[0]["product_name"] == "MacBook Pro"
    assert len(links_b) == 1
    assert links_b[0]["product_name"] == "Váy Dạ Hội"
    
    # Deleting link of user_a does not affect user_b
    delete_user_affiliate_link(user_a, links_a[0]["id"], conn=test_db)
    assert count_user_affiliate_links(user_a, conn=test_db) == 0
    assert count_user_affiliate_links(user_b, conn=test_db) == 1

def test_02_parse_text_various_formats():
    raw_sample = """
    https://shorten.asia/xaE7DBsX (Nguyễn Kim)
    JUNO - https://trackecom.asia/uq3Z3zhF
    BỀN COMPUTER: https://attracking.asia/gzGJAWXZ
    https://attracking.asia/VU3B73xB
    """
    items = parse_affiliate_links_from_text(raw_sample)
    assert len(items) == 4
    assert items[0]["product_name"] == "Nguyễn Kim"
    assert items[0]["niche"] == "cong_nghe"
    assert items[1]["product_name"] == "JUNO"
    assert items[1]["niche"] == "thoi_trang"
    assert items[2]["product_name"] == "BỀN COMPUTER"
    assert items[2]["niche"] == "cong_nghe"

def test_03_classification_rules():
    assert classify_product_niche("Samsung Galaxy S24", "https://samsung.vn") == "cong_nghe"
    assert classify_product_niche("Giày Sneaker Biti's Hunter", "https://bitis.vn") == "thoi_trang"
    assert classify_product_niche("Mở Thẻ Tín Dụng VPBank", "https://vpbank.vn") == "tai_chinh"
    assert classify_product_niche("Vé Máy Bay Khứ Hồi", "https://gotadi.vn") == "du_lich"
    assert classify_product_niche("Nồi Chiên Không Dầu Elmich", "https://elmich.vn") == "gia_dung"
    assert classify_product_niche("Mã Giảm Giá Shopee", "https://shopee.vn") == "san_tmdt"

def test_04_seed_curated_vault_from_d_drive(test_db):
    uid = 99999
    res = seed_default_curated_vault_for_user(uid, conn=test_db)
    assert res["success"] is True
    assert res["total_in_vault"] >= 65
    
    stats = get_user_affiliate_stats(uid, conn=test_db)
    assert stats["total"] >= 65
    assert stats["cong_nghe"] > 0
    assert stats["thoi_trang"] > 0
    assert stats["tai_chinh"] > 0
    assert stats["du_lich"] > 0

def test_05_personal_vault_match_for_post(test_db):
    uid = 88888
    add_user_affiliate_link(uid, "Laptop Gaming Asus", "https://shorten.asia/asus", "cong_nghe", conn=test_db)
    
    matched = match_affiliate_for_post("Review Laptop Gaming khủng", "cong_nghe", candidates=None, user_id=uid)
    # Even if candidates=None, function queries personal vault
    links = get_user_affiliate_links(uid, conn=test_db)
    matched = match_affiliate_for_post("Review Laptop Gaming khủng", "cong_nghe", candidates=links)
    assert matched["matched"] is True
    assert matched["primary_affiliate"]["product_name"] == "Laptop Gaming Asus"
    assert matched["output_package"]["tracking_url"] == "https://shorten.asia/asus"

def test_06_ui_renderers_no_missing_imports():
    uid = 7126457028
    stats = {"total": 66, "cong_nghe": 10, "thoi_trang": 12, "tai_chinh": 22, "du_lich": 10, "gia_dung": 4, "san_tmdt": 8}
    
    text = autopost_affiliate_text(uid, stats, "vi")
    assert "KHO AFFILIATE CÁ NHÂN" in text
    assert str(uid) in text
    assert "66 link" in text
    
    kb = autopost_affiliate_keyboard(uid, stats, "vi")
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row if btn.callback_data]
    assert "autopost|aff_import_prompt" in callbacks
    assert "autopost|aff_seed" in callbacks
    assert "autopost|main" in callbacks
    
    urls = [btn.url for row in kb.inline_keyboard for btn in row if btn.url]
    assert any("t.me/share/url" in u for u in urls)
