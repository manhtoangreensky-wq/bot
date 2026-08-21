"""
Affiliate Match Engine V2 & User-Specific Personal Affiliate Vault.
Supports personal affiliate vaults per Telegram user account, text & file import,
smart niche classification, 65+ curated seed campaigns from D: drive, and paid-ads compliance.
"""
from typing import Dict, Any, List, Optional, Tuple
import re
import os
import sqlite3
import datetime

MATCH_THRESHOLD = 60  # Minimum relevance score to include an affiliate link

# 66 Curated Seed Affiliate Campaigns (Parsed from d:\\TOANAAS\\công cụ\\link affiliate.txt)
CURATED_AFFILIATE_SEEDS: List[Tuple[str, str, str]] = [
    ("https://shorten.asia/xaE7DBsX", "Nguyễn Kim", "cong_nghe"),
    ("https://trackecom.asia/uq3Z3zhF", "JUNO", "thoi_trang"),
    ("https://attracking.asia/gzGJAWXZ", "BỀN COMPUTER", "cong_nghe"),
    ("https://attracking.asia/VU3B73xB", "ELMICH", "gia_dung"),
    ("https://shorten.asia/JxpW7rgv", "PNJ", "thoi_trang"),
    ("https://goecom.asia/8F5QMNzs", "Lug", "thoi_trang"),
    ("https://trackec.asia/UQn56Ycp", "ACFC", "thoi_trang"),
    ("https://trackfin.asia/cyrwNfdM", "Con Cưng", "gia_dung"),
    ("https://trackfin.asia/vVv8KEHu", "SAMSUNG", "cong_nghe"),
    ("https://goecom.asia/4GGZ8meW", "MediaMart", "cong_nghe"),
    ("https://trackfin.asia/7wamMsFq", "Biti's", "thoi_trang"),
    ("https://trackfin.asia/SHXY6qMT", "HDBank - Thẻ tín dụng", "tai_chinh"),
    ("https://goecom.asia/QYPZrGrU", "AppMax_Vay Nhanh+Max Card+Vay", "tai_chinh"),
    ("https://attracking.asia/AJSh3W9U", "VIB AppMax_Thẻ thanh toán", "tai_chinh"),
    ("https://goecom.asia/5pKeXgNU", "Cathay United Bank_Android", "tai_chinh"),
    ("https://goecom.asia/WWHZMPKm", "Cathay United Bank_IOS", "tai_chinh"),
    ("https://shorten.asia/gSrcTngW", "Bảo hiểm Hùng Vương", "tai_chinh"),
    ("https://attracking.asia/jRG236hs", "Liobank Thẻ + Vay", "tai_chinh"),
    ("https://trackec.asia/s6sWSVKG", "VPBank Thẻ Direct", "tai_chinh"),
    ("https://trackec.asia/TGGjCWA2", "Lotte Finance", "tai_chinh"),
    ("https://attracking.asia/CGxE1aYN", "THẺ TÍN DỤNG VPBank 3T", "tai_chinh"),
    ("https://attracking.asia/pjdNn2EA", "MỞ THẺ VPBANK SENID", "tai_chinh"),
    ("https://shorten.asia/P6SstnNY", "HOMECREDIT CASH LOAN", "tai_chinh"),
    ("https://trackfin.asia/UPbWDCPC", "VIB - THẺ TÍN DỤNG", "tai_chinh"),
    ("https://trackecom.asia/KuBZKykJ", "Tima", "tai_chinh"),
    ("https://attracking.asia/cnuDXMgD", "Bảo Minh", "tai_chinh"),
    ("https://trackfin.asia/wmqm9WMB", "EVOCARD - Thẻ tín dụng", "tai_chinh"),
    ("https://trackmobi.asia/f5vK6kWh", "Vé máy bay", "du_lich"),
    ("https://attracking.asia/mhGF3BVF", "XANH SM - TUYỂN TÀI XẾ XE MÁY", "du_lich"),
    ("https://trackfin.asia/V9G8j3Gs", "BestPrice - Đặt phòng & Tour", "du_lich"),
    ("https://attracking.asia/xaqY9Mcq", "VIETNAM AIRLINES", "du_lich"),
    ("https://attracking.asia/6PBPz15b", "VinWonders Website", "du_lich"),
    ("https://shorten.asia/7E5yK36E", "Vé Giá rẻ", "du_lich"),
    ("https://trackfin.asia/C2wmhSqG", "GOTADI – Vé máy bay giá rẻ", "du_lich"),
    ("https://trackmobi.asia/nbv6ZXPa", "ATADI _ Đặt vé máy bay", "du_lich"),
    ("https://trackfin.asia/pagx7bx2", "Klook - Vé Tham Quan, Tour, SIM", "du_lich"),
    ("https://goecom.asia/Z31Vp7Ad", "VPBank Online", "tai_chinh"),
    ("https://goeco.mobi/GJPRlrH3", "Shopee", "san_tmdt"),
    ("https://goeco.mobi/Ao8zhi5N", "Lazada", "san_tmdt"),
    ("https://goeco.mobi/UbHEhUul", "Traveloka", "du_lich"),
    ("https://trackfin.asia/J5X2hWfu", "TikTok Shop", "san_tmdt"),
    ("https://attracking.asia/TfNc2dfN", "MSB Bank", "tai_chinh"),
    ("https://trackec.asia/x6H5baXh", "Mắm Nam Ngư", "gia_dung"),
    ("https://attracking.asia/jaUg5JFT", "BIDV SmartBanking", "tai_chinh"),
    ("https://attracking.asia/eVBScXBZ", "MBBANK", "tai_chinh"),
    ("https://trackec.asia/xMdFNmSa", "VPBank Hộ kinh doanh", "tai_chinh"),
    ("https://trackmobi.asia/ss183PMu", "HongLeong Bank", "tai_chinh"),
    ("https://shorten.asia/SBPDCn5x", "Zalo Ads", "san_tmdt"),
    ("https://shorten.asia/TFbjeqe8", "ShopDunk Apple Authorized", "cong_nghe"),
    ("https://trackfin.asia/W7d7w4EX", "Giày Shondo", "thoi_trang"),
    ("https://trackec.asia/Udse3MbB", "Savani Thời trang", "thoi_trang"),
    ("https://attracking.asia/YUVK7hBs", "LAZADA REFERRAL", "san_tmdt"),
    ("https://shorten.asia/1JdwRvYt", "AEON Eshop", "san_tmdt"),
    ("https://goecom.asia/wnMFwYsF", "Hoàng Hà Mobile", "cong_nghe"),
    ("https://trackfin.asia/c413qgqe", "TIKTOK FOR BUSINESS", "san_tmdt"),
    ("https://trackfin.asia/N9sa43Xv", "CHICKITA VOUCHER", "gia_dung"),
    ("https://trackecom.asia/YbBhQ2pq", "Samsung Student Store", "cong_nghe"),
    ("https://shorten.asia/1hyutcwN", "CellphoneS", "cong_nghe"),
    ("https://shorten.asia/pPvvzj6X", "Điện Thoại Vui", "cong_nghe"),
    ("https://trackecom.asia/VYp9XMEB", "JOCKEY", "thoi_trang"),
    ("https://trackmobi.asia/fQRZdVyj", "VERA", "thoi_trang"),
    ("https://trackfin.asia/8uvHbKPp", "Vascara", "thoi_trang"),
    ("https://attracking.asia/GsQmmkz7", "Adidas Việt Nam Online", "thoi_trang"),
    ("https://trackfin.asia/9ueaXQH5", "SUPERSPORTS", "thoi_trang"),
    ("https://trackmobi.asia/pdfM4UWt", "Lazada Việt Nam VIP", "san_tmdt"),
]

NICHE_NAMES: Dict[str, str] = {
    "cong_nghe": "📱 Công nghệ & AI",
    "thoi_trang": "👗 Thời trang & Phụ kiện",
    "tai_chinh": "💳 Tài chính & Thẻ tín dụng",
    "du_lich": "✈️ Du lịch & Vé máy bay",
    "gia_dung": "🏡 Mẹ & Bé, Gia dụng",
    "san_tmdt": "🛒 Sàn TMĐT & Dịch vụ",
}

def _get_db_path() -> str:
    """Resolve database path from environment or default."""
    return os.environ.get("TOANAAS_DB_PATH") or os.environ.get("DB_FILE") or "data/toandaas_bot.db"

def _get_conn(db_path: Optional[str] = None) -> sqlite3.Connection:
    path = db_path or _get_db_path()
    if path and os.path.dirname(os.path.abspath(path)):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

def init_user_affiliate_vault_db(conn: Optional[sqlite3.Connection] = None) -> None:
    """Ensure user_affiliate_vault table exists."""
    close_after = False
    if conn is None:
        conn = _get_conn()
        close_after = True
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_affiliate_vault (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                product_name TEXT NOT NULL,
                niche TEXT NOT NULL,
                url TEXT NOT NULL,
                commission_rate TEXT DEFAULT '10%',
                paid_ads_allowed INTEGER DEFAULT 1,
                status TEXT DEFAULT 'active',
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_aff_user_niche ON user_affiliate_vault (user_id, niche)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_aff_user_status ON user_affiliate_vault (user_id, status)")
        conn.commit()
    finally:
        if close_after:
            conn.close()

def classify_product_niche(product_name: str, url: str) -> str:
    """Smartly classify campaign into a niche based on name and url keywords."""
    combined = f"{product_name} {url}".lower()
    
    if any(k in combined for k in ["máy tính", "laptop", "điện thoại", "samsung", "media", "nguyễn kim", "hoàng hà", "shopdunk", "cellphones", "điện thoại vui", "fpt", "asus", "dell", "ai", "công nghệ", "computer"]):
        return "cong_nghe"
    if any(k in combined for k in ["juno", "pnj", "lug", "bitis", "biti's", "shondo", "savani", "jockey", "vera", "vascara", "adidas", "supersports", "trang sức", "giày", "dép", "túi", "quần áo", "thời trang", "acfc"]):
        return "thoi_trang"
    if any(k in combined for k in ["bank", "ngân hàng", "hdbank", "vib", "cathay", "bảo hiểm", "liobank", "vpbank", "lotte", "homecredit", "loan", "vay", "thẻ tín dụng", "credit", "tima", "bảo minh", "evocard", "bidv", "mbbank", "senid", "appmax", "tài chính", "msb", "hongleong"]):
        return "tai_chinh"
    if any(k in combined for k in ["vé máy bay", "xanh sm", "bestprice", "vietnam airlines", "vinwonders", "vé giá rẻ", "gotadi", "atadi", "klook", "traveloka", "khách sạn", "tour", "du lịch", "flight", "hotel"]):
        return "du_lich"
    if any(k in combined for k in ["con cưng", "elmich", "mắm nam ngư", "mẹ & bé", "bỉm sữa", "gia dụng", "ăn uống", "f&b", "chickita", "food"]):
        return "gia_dung"
    if any(k in combined for k in ["shoppe", "shopee", "lazada", "tiktok", "zalo", "aeon", "sàn", "tmdt", "ecommerce"]):
        return "san_tmdt"
        
    return "cong_nghe"

def parse_affiliate_links_from_text(raw_text: str) -> List[Dict[str, Any]]:
    """
    Parse links from text with various patterns:
    - https://shorten.asia/xxx (Tên sản phẩm)
    - Tên sản phẩm - https://...
    - Tên sản phẩm: https://...
    - Pure URL
    """
    if not raw_text or not raw_text.strip():
        return []
        
    results: List[Dict[str, Any]] = []
    seen_urls = set()
    
    # Split text into lines or items delimited by newline or commas before http
    normalized = re.sub(r',\s*(https?://)', r'\n\1', raw_text)
    lines = [ln.strip() for ln in normalized.splitlines() if ln.strip()]
    
    for line in lines:
        # Check Pattern A: Name - URL or Name : URL
        m_dash = re.search(r'^([^:\-\n\r]+?)\s*[:\-]\s*(https?://[^\s,\)]+)', line)
        if m_dash:
            clean_name = m_dash.group(1).strip().lstrip("•*-1234567890. ")
            clean_url = m_dash.group(2).strip().rstrip(".,;)")
            if clean_url and clean_url not in seen_urls:
                seen_urls.add(clean_url)
                niche = classify_product_niche(clean_name, clean_url)
                results.append({
                    "product_name": clean_name or clean_url.split("/")[-1],
                    "url": clean_url,
                    "niche": niche,
                    "commission_rate": "10%",
                    "paid_ads_allowed": True,
                })
                continue
                
        # Check Pattern B: URL (Name)
        m_paren = re.search(r'(https?://[^\s,\)]+)\s*(?:\(([^)]+)\))?', line)
        if m_paren:
            clean_url = m_paren.group(1).strip().rstrip(".,;)")
            raw_name = m_paren.group(2)
            clean_name = (raw_name or "").strip()
            if not clean_name:
                clean_name = clean_url.split("/")[-1] or clean_url
            if clean_url and clean_url not in seen_urls:
                seen_urls.add(clean_url)
                niche = classify_product_niche(clean_name, clean_url)
                results.append({
                    "product_name": clean_name,
                    "url": clean_url,
                    "niche": niche,
                    "commission_rate": "10%",
                    "paid_ads_allowed": True,
                })
                continue
                
        # Check Pattern C: Generic URL in line
        m_generic = re.search(r'(https?://[^\s,\)]+)', line)
        if m_generic:
            clean_url = m_generic.group(1).strip().rstrip(".,;)")
            if clean_url and clean_url not in seen_urls:
                seen_urls.add(clean_url)
                clean_name = clean_url.split("/")[-1] or clean_url
                niche = classify_product_niche(clean_name, clean_url)
                results.append({
                    "product_name": clean_name,
                    "url": clean_url,
                    "niche": niche,
                    "commission_rate": "10%",
                    "paid_ads_allowed": True,
                })
                
    return results


def add_user_affiliate_link(
    user_id: int,
    product_name: str,
    url: str,
    niche: Optional[str] = None,
    commission_rate: str = "10%",
    paid_ads_allowed: bool = True,
    conn: Optional[sqlite3.Connection] = None,
) -> int:
    """Add a single affiliate link to a specific user's personal vault."""
    close_after = False
    if conn is None:
        conn = _get_conn()
        close_after = True
    try:
        init_user_affiliate_vault_db(conn)
        niche = niche or classify_product_niche(product_name, url)
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        # Check if URL already exists for this user
        row = conn.execute(
            "SELECT id FROM user_affiliate_vault WHERE user_id = ? AND url = ?",
            (user_id, url)
        ).fetchone()
        
        if row:
            conn.execute(
                "UPDATE user_affiliate_vault SET product_name = ?, niche = ?, commission_rate = ?, paid_ads_allowed = ?, status = 'active' WHERE id = ?",
                (product_name, niche, commission_rate, 1 if paid_ads_allowed else 0, row[0])
            )
            conn.commit()
            return row[0]
            
        cur = conn.execute(
            """INSERT INTO user_affiliate_vault 
               (user_id, product_name, niche, url, commission_rate, paid_ads_allowed, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 'active', ?)""",
            (user_id, product_name, niche, url, commission_rate, 1 if paid_ads_allowed else 0, now_str)
        )
        conn.commit()
        return cur.lastrowid
    finally:
        if close_after:
            conn.close()

def import_affiliate_links_for_user(
    user_id: int,
    raw_text_or_items: Any,
    conn: Optional[sqlite3.Connection] = None,
) -> Dict[str, Any]:
    """
    Import links from text or list into user's personal vault.
    Returns summary stats.
    """
    if isinstance(raw_text_or_items, str):
        items = parse_affiliate_links_from_text(raw_text_or_items)
    else:
        items = list(raw_text_or_items or [])
        
    close_after = False
    if conn is None:
        conn = _get_conn()
        close_after = True
    try:
        init_user_affiliate_vault_db(conn)
        added_count = 0
        by_niche: Dict[str, int] = {}
        
        for item in items:
            p_name = item.get("product_name") or "Sản phẩm Affiliate"
            p_url = item.get("url") or ""
            if not p_url:
                continue
            p_niche = item.get("niche") or classify_product_niche(p_name, p_url)
            p_comm = item.get("commission_rate") or "10%"
            p_ads = bool(item.get("paid_ads_allowed", True))
            
            add_user_affiliate_link(
                user_id=user_id,
                product_name=p_name,
                url=p_url,
                niche=p_niche,
                commission_rate=p_comm,
                paid_ads_allowed=p_ads,
                conn=conn
            )
            added_count += 1
            by_niche[p_niche] = by_niche.get(p_niche, 0) + 1
            
        total = count_user_affiliate_links(user_id=user_id, conn=conn)
        return {
            "success": True,
            "added_count": added_count,
            "total_in_vault": total,
            "by_niche": by_niche,
        }
    finally:
        if close_after:
            conn.close()

def get_user_affiliate_links(
    user_id: int,
    niche: Optional[str] = None,
    status: str = "active",
    limit: int = 100,
    offset: int = 0,
    conn: Optional[sqlite3.Connection] = None,
) -> List[Dict[str, Any]]:
    """Retrieve links from user's personal affiliate vault."""
    close_after = False
    if conn is None:
        conn = _get_conn()
        close_after = True
    try:
        init_user_affiliate_vault_db(conn)
        query = "SELECT id, user_id, product_name, niche, url, commission_rate, paid_ads_allowed, status, created_at FROM user_affiliate_vault WHERE user_id = ?"
        params: List[Any] = [user_id]
        
        if status:
            query += " AND status = ?"
            params.append(status)
        if niche and niche != "all":
            query += " AND niche = ?"
            params.append(niche)
            
        query += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        rows = conn.execute(query, params).fetchall()
        results = []
        for r in rows:
            results.append({
                "id": r["id"],
                "user_id": r["user_id"],
                "product_name": r["product_name"],
                "niche": r["niche"],
                "url": r["url"],
                "commission_rate": r["commission_rate"],
                "paid_ads_allowed": bool(r["paid_ads_allowed"]),
                "status": r["status"],
                "created_at": r["created_at"],
            })
        return results
    finally:
        if close_after:
            conn.close()

def count_user_affiliate_links(
    user_id: int,
    niche: Optional[str] = None,
    status: str = "active",
    conn: Optional[sqlite3.Connection] = None,
) -> int:
    """Count total links in user's personal vault."""
    close_after = False
    if conn is None:
        conn = _get_conn()
        close_after = True
    try:
        init_user_affiliate_vault_db(conn)
        query = "SELECT COUNT(*) FROM user_affiliate_vault WHERE user_id = ?"
        params: List[Any] = [user_id]
        if status:
            query += " AND status = ?"
            params.append(status)
        if niche and niche != "all":
            query += " AND niche = ?"
            params.append(niche)
        val = conn.execute(query, params).fetchone()[0]
        return int(val or 0)
    finally:
        if close_after:
            conn.close()

def get_user_affiliate_stats(user_id: int, conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
    """Get breakdown statistics of user's personal affiliate vault."""
    close_after = False
    if conn is None:
        conn = _get_conn()
        close_after = True
    try:
        init_user_affiliate_vault_db(conn)
        rows = conn.execute(
            "SELECT niche, COUNT(*) FROM user_affiliate_vault WHERE user_id = ? AND status = 'active' GROUP BY niche",
            (user_id,)
        ).fetchall()
        by_niche = {r[0]: r[1] for r in rows}
        total = sum(by_niche.values())
        return {
            "total": total,
            "by_niche": by_niche,
            "cong_nghe": by_niche.get("cong_nghe", 0),
            "thoi_trang": by_niche.get("thoi_trang", 0),
            "tai_chinh": by_niche.get("tai_chinh", 0),
            "du_lich": by_niche.get("du_lich", 0),
            "gia_dung": by_niche.get("gia_dung", 0),
            "san_tmdt": by_niche.get("san_tmdt", 0),
        }
    finally:
        if close_after:
            conn.close()

def seed_default_curated_vault_for_user(user_id: int, conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
    """Seed user's personal vault with curated 66 campaigns from D: drive."""
    items = []
    d_file = r"d:\TOANAAS\công cụ\link affiliate.txt"
    if os.path.exists(d_file):
        try:
            content = open(d_file, "r", encoding="utf-8").read()
            items = parse_affiliate_links_from_text(content)
        except Exception:
            items = []
            
    if not items:
        for url, name, niche in CURATED_AFFILIATE_SEEDS:
            items.append({
                "product_name": name,
                "url": url,
                "niche": niche,
                "commission_rate": "10%",
                "paid_ads_allowed": True,
            })
            
    return import_affiliate_links_for_user(user_id, items, conn=conn)

def delete_user_affiliate_link(user_id: int, link_id: int, conn: Optional[sqlite3.Connection] = None) -> bool:
    """Delete a single link from user's personal vault."""
    close_after = False
    if conn is None:
        conn = _get_conn()
        close_after = True
    try:
        init_user_affiliate_vault_db(conn)
        cur = conn.execute("DELETE FROM user_affiliate_vault WHERE user_id = ? AND id = ?", (user_id, link_id))
        conn.commit()
        return cur.rowcount > 0
    finally:
        if close_after:
            conn.close()

def clear_user_affiliate_vault(user_id: int, conn: Optional[sqlite3.Connection] = None) -> int:
    """Clear all links in user's personal vault."""
    close_after = False
    if conn is None:
        conn = _get_conn()
        close_after = True
    try:
        init_user_affiliate_vault_db(conn)
        cur = conn.execute("DELETE FROM user_affiliate_vault WHERE user_id = ?", (user_id,))
        conn.commit()
        return cur.rowcount
    finally:
        if close_after:
            conn.close()

def match_affiliate_for_post(
    topic: str,
    niche: str,
    candidates: Optional[List[Dict[str, Any]]] = None,
    user_id: Optional[int] = None,
    campaign_goal: str = "AFFILIATE_CONVERSION",
) -> Dict[str, Any]:
    """
    Score and select the most relevant affiliate candidate.
    Prioritizes user's own personal vault when user_id is provided.
    Low score => NO_AFFILIATE.
    """
    if candidates is None and user_id is not None:
        user_links = get_user_affiliate_links(user_id=user_id, niche=niche)
        if not user_links:
            user_links = get_user_affiliate_links(user_id=user_id)
        candidates = user_links

    candidates = candidates or []
    if not candidates:
        return {
            "matched": False,
            "primary_affiliate": None,
            "match_score": 0,
            "match_reason": "No affiliate candidates available in personal vault.",
        }

    scored = []
    topic_lower = topic.lower()
    niche_lower = niche.lower()

    for cand in candidates:
        score = 0
        cand_niche = str(cand.get("niche") or "").lower()
        cand_name = str(cand.get("product_name") or "").lower()
        
        # Niche relevance (+40)
        if cand_niche in niche_lower or niche_lower in cand_niche:
            score += 40
        # Topic relevance (+30)
        if any(word in topic_lower for word in cand_name.split() if len(word) > 2):
            score += 30
        # Product score bonus (+20)
        score += min(20, int(cand.get("product_score") or 15))
        # Status active (+10)
        if cand.get("status") == "active":
            score += 10

        scored.append((score, cand))

    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best_cand = scored[0]

    if best_score < MATCH_THRESHOLD:
        return {
            "matched": False,
            "primary_affiliate": None,
            "match_score": best_score,
            "match_reason": f"Match score ({best_score}) below threshold ({MATCH_THRESHOLD}). Not inserting irrelevant affiliate.",
        }

    return {
        "matched": True,
        "primary_affiliate": best_cand,
        "match_score": best_score,
        "match_reason": f"High niche/topic match score ({best_score}) for {best_cand.get('product_name')}.",
        "output_package": {
            "affiliate_link_id": best_cand.get("id"),
            "tracking_url": best_cand.get("url"),
            "network": best_cand.get("network", "personal_vault"),
            "disclosure": "Liên kết đối tác tiếp thị chính thức từ kho cá nhân.",
            "allowed_claims": best_cand.get("allowed_claims", ""),
            "blocked_claims": best_cand.get("blocked_claims", ""),
        }
    }

def check_paid_ads_affiliate_policy(affiliate: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Check if affiliate program permits paid advertising. Fails closed (ADS_ELIGIBLE=NO) if unknown."""
    if not affiliate:
        return {"ads_eligible": False, "reason": "No affiliate attached."}

    if affiliate.get("paid_ads_allowed") is False:
        return {
            "ads_eligible": False,
            "reason": "Affiliate network program explicitly prohibits paid advertising.",
        }

    if affiliate.get("paid_ads_allowed") is not True:
        return {
            "ads_eligible": False,
            "reason": "Affiliate program paid-advertising policy is UNKNOWN. Failing closed to prevent account ban or ad waste.",
        }

    return {
        "ads_eligible": True,
        "reason": "Affiliate program permits paid social advertising.",
    }
