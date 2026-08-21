"""
Durable SQLite Persistence Layer for TOAN AAS Omnichannel Marketing Automation.
Manages content_inputs, user_brand_profiles, user_social_accounts, content_plans,
content_items, publish_jobs, publish_receipts, post_metrics, and user_autopost_settings.
"""
from typing import Dict, Any, List, Optional
import os
import sqlite3
import datetime
import hashlib

def _get_db_path() -> str:
    return os.environ.get("TOANAAS_DB_PATH") or os.environ.get("DB_FILE") or "data/toandaas_bot.db"

def _get_conn(db_path: Optional[str] = None) -> sqlite3.Connection:
    path = db_path or _get_db_path()
    if path and os.path.dirname(os.path.abspath(path)):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

def init_autopost_durable_db(conn: Optional[sqlite3.Connection] = None) -> None:
    """Ensure all required tables and indexes exist."""
    close_after = False
    if conn is None:
        conn = _get_conn()
        close_after = True
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS content_inputs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_user_id INTEGER NOT NULL,
                type TEXT NOT NULL,
                text TEXT,
                source_url TEXT,
                media_id TEXT,
                affiliate_id INTEGER,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ci_user ON content_inputs (owner_user_id)")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_brand_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_user_id INTEGER NOT NULL UNIQUE,
                brand_name TEXT NOT NULL,
                description TEXT,
                products_services TEXT,
                target_audience TEXT,
                brand_voice TEXT,
                primary_cta TEXT,
                website TEXT,
                logo_file_id TEXT,
                brand_colors TEXT,
                default_hashtags TEXT,
                language TEXT DEFAULT 'vi',
                allowed_claims TEXT,
                blocked_claims TEXT,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ubp_user ON user_brand_profiles (owner_user_id)")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_social_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_user_id INTEGER NOT NULL,
                platform TEXT NOT NULL,
                account_id TEXT NOT NULL,
                display_name TEXT NOT NULL,
                connected INTEGER DEFAULT 1,
                authorized INTEGER DEFAULT 1,
                token_status TEXT DEFAULT 'ACTIVE',
                publish_status TEXT DEFAULT 'READY',
                encrypted_credential_ref TEXT,
                last_checked TEXT NOT NULL,
                UNIQUE(owner_user_id, platform, account_id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_usa_user_platform ON user_social_accounts (owner_user_id, platform)")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS content_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_user_id INTEGER NOT NULL,
                brand_name TEXT NOT NULL,
                goal TEXT NOT NULL,
                duration_days INTEGER NOT NULL,
                total_posts INTEGER NOT NULL,
                status TEXT DEFAULT 'DRAFT',
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cp_user ON content_plans (owner_user_id)")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS content_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id INTEGER,
                owner_user_id INTEGER NOT NULL,
                scheduled_date TEXT NOT NULL,
                scheduled_time TEXT NOT NULL,
                timezone TEXT DEFAULT 'Asia/Ho_Chi_Minh',
                platform TEXT NOT NULL,
                topic TEXT NOT NULL,
                pillar TEXT,
                hook TEXT,
                caption TEXT,
                cta TEXT,
                hashtags TEXT,
                content_input_id INTEGER,
                affiliate_id INTEGER,
                status TEXT DEFAULT 'DRAFT',
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_citem_plan ON content_items (plan_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_citem_user ON content_items (owner_user_id)")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS publish_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content_item_id INTEGER,
                owner_user_id INTEGER NOT NULL,
                platform TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                scheduled_at_utc TEXT NOT NULL,
                status TEXT DEFAULT 'SCHEDULED',
                attempt_count INTEGER DEFAULT 0,
                idempotency_key TEXT NOT NULL UNIQUE,
                last_attempt_at TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pj_status_sched ON publish_jobs (status, scheduled_at_utc)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pj_user ON publish_jobs (owner_user_id)")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS publish_receipts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                publish_job_id INTEGER NOT NULL UNIQUE,
                owner_user_id INTEGER NOT NULL,
                platform TEXT NOT NULL,
                remote_post_id TEXT NOT NULL,
                remote_url TEXT,
                remote_status TEXT NOT NULL,
                api_accepted_at TEXT NOT NULL,
                verified_at TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pr_user ON publish_receipts (owner_user_id)")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS post_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                receipt_id INTEGER NOT NULL,
                owner_user_id INTEGER NOT NULL,
                platform TEXT NOT NULL,
                views INTEGER,
                likes INTEGER,
                shares INTEGER,
                comments INTEGER,
                clicks INTEGER,
                revenue_vnd INTEGER,
                metrics_source TEXT NOT NULL,
                last_polled_at TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pm_receipt ON post_metrics (receipt_id)")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_autopost_settings (
                owner_user_id INTEGER PRIMARY KEY,
                publish_mode TEXT DEFAULT 'MANUAL',
                updated_at TEXT NOT NULL
            )
        """)
        conn.commit()
    finally:
        if close_after:
            conn.close()

# ----------------- Content Inputs -----------------
def save_content_input(
    owner_user_id: int,
    input_type: str,
    text: Optional[str] = None,
    source_url: Optional[str] = None,
    media_id: Optional[str] = None,
    affiliate_id: Optional[int] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> int:
    close_after = False
    if conn is None:
        conn = _get_conn()
        close_after = True
    try:
        init_autopost_durable_db(conn)
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        cur = conn.execute(
            """INSERT INTO content_inputs (owner_user_id, type, text, source_url, media_id, affiliate_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (owner_user_id, input_type, text, source_url, media_id, affiliate_id, now_str)
        )
        conn.commit()
        return cur.lastrowid
    finally:
        if close_after:
            conn.close()

def get_content_input(input_id: int, conn: Optional[sqlite3.Connection] = None) -> Optional[Dict[str, Any]]:
    close_after = False
    if conn is None:
        conn = _get_conn()
        close_after = True
    try:
        init_autopost_durable_db(conn)
        row = conn.execute("SELECT * FROM content_inputs WHERE id = ?", (input_id,)).fetchone()
        if not row:
            return None
        return dict(row)
    finally:
        if close_after:
            conn.close()

# ----------------- Brand Profiles -----------------
def get_user_brand_profile(owner_user_id: int, conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
    close_after = False
    if conn is None:
        conn = _get_conn()
        close_after = True
    try:
        init_autopost_durable_db(conn)
        row = conn.execute("SELECT * FROM user_brand_profiles WHERE owner_user_id = ?", (owner_user_id,)).fetchone()
        if not row:
            return {
                "brand_name": "Chưa thiết lập",
                "description": "",
                "products_services": "",
                "target_audience": "",
                "brand_voice": "Chuyên nghiệp & Hiện đại",
                "primary_cta": "Trải nghiệm ngay trên Telegram @toanaasbot",
                "website": "https://toanaas.vn",
                "logo_file_id": "",
                "brand_colors": "#1E88E5",
                "default_hashtags": "#TOANAAS #AI",
                "language": "vi",
                "allowed_claims": "",
                "blocked_claims": "",
                "is_configured": False,
            }
        d = dict(row)
        d["is_configured"] = bool(d.get("brand_name") and d["brand_name"] != "Chưa thiết lập")
        return d
    finally:
        if close_after:
            conn.close()

def save_user_brand_profile(
    owner_user_id: int,
    brand_data: Dict[str, Any],
    conn: Optional[sqlite3.Connection] = None,
) -> Dict[str, Any]:
    close_after = False
    if conn is None:
        conn = _get_conn()
        close_after = True
    try:
        init_autopost_durable_db(conn)
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        brand_name = brand_data.get("brand_name") or "TOAN AAS"
        desc = brand_data.get("description", "")
        products = brand_data.get("products_services", "")
        audience = brand_data.get("target_audience", "")
        voice = brand_data.get("brand_voice", "Chuyên nghiệp & Hiện đại")
        cta = brand_data.get("primary_cta", "Trải nghiệm ngay trên Telegram @toanaasbot")
        website = brand_data.get("website", "https://toanaas.vn")
        logo = brand_data.get("logo_file_id", "")
        colors = brand_data.get("brand_colors", "#1E88E5")
        hashtags = brand_data.get("default_hashtags", "#TOANAAS")
        lang = brand_data.get("language", "vi")
        allowed = brand_data.get("allowed_claims", "")
        blocked = brand_data.get("blocked_claims", "")

        conn.execute(
            """INSERT INTO user_brand_profiles (
                owner_user_id, brand_name, description, products_services, target_audience,
                brand_voice, primary_cta, website, logo_file_id, brand_colors,
                default_hashtags, language, allowed_claims, blocked_claims, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(owner_user_id) DO UPDATE SET
                brand_name = excluded.brand_name,
                description = excluded.description,
                products_services = excluded.products_services,
                target_audience = excluded.target_audience,
                brand_voice = excluded.brand_voice,
                primary_cta = excluded.primary_cta,
                website = excluded.website,
                logo_file_id = excluded.logo_file_id,
                brand_colors = excluded.brand_colors,
                default_hashtags = excluded.default_hashtags,
                language = excluded.language,
                allowed_claims = excluded.allowed_claims,
                blocked_claims = excluded.blocked_claims,
                updated_at = excluded.updated_at
            """,
            (owner_user_id, brand_name, desc, products, audience, voice, cta, website, logo, colors, hashtags, lang, allowed, blocked, now_str)
        )
        conn.commit()
        return get_user_brand_profile(owner_user_id, conn=conn)
    finally:
        if close_after:
            conn.close()

# ----------------- Social Accounts -----------------
def get_user_social_accounts(owner_user_id: int, conn: Optional[sqlite3.Connection] = None) -> List[Dict[str, Any]]:
    close_after = False
    if conn is None:
        conn = _get_conn()
        close_after = True
    try:
        init_autopost_durable_db(conn)
        rows = conn.execute("SELECT * FROM user_social_accounts WHERE owner_user_id = ?", (owner_user_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        if close_after:
            conn.close()

def save_user_social_account(
    owner_user_id: int,
    platform: str,
    account_id: str,
    display_name: str,
    token_status: str = "ACTIVE",
    publish_status: str = "READY",
    encrypted_credential_ref: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> Dict[str, Any]:
    close_after = False
    if conn is None:
        conn = _get_conn()
        close_after = True
    try:
        init_autopost_durable_db(conn)
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        conn.execute(
            """INSERT INTO user_social_accounts (
                owner_user_id, platform, account_id, display_name, connected, authorized,
                token_status, publish_status, encrypted_credential_ref, last_checked
            ) VALUES (?, ?, ?, ?, 1, 1, ?, ?, ?, ?)
            ON CONFLICT(owner_user_id, platform, account_id) DO UPDATE SET
                display_name = excluded.display_name,
                connected = 1,
                authorized = 1,
                token_status = excluded.token_status,
                publish_status = excluded.publish_status,
                encrypted_credential_ref = excluded.encrypted_credential_ref,
                last_checked = excluded.last_checked
            """,
            (owner_user_id, platform.lower(), account_id, display_name, token_status, publish_status, encrypted_credential_ref, now_str)
        )
        conn.commit()
        row = conn.execute("SELECT * FROM user_social_accounts WHERE owner_user_id = ? AND platform = ? AND account_id = ?", (owner_user_id, platform.lower(), account_id)).fetchone()
        return dict(row)
    finally:
        if close_after:
            conn.close()

def disconnect_user_social_account(owner_user_id: int, platform: str, account_id: str, conn: Optional[sqlite3.Connection] = None) -> bool:
    close_after = False
    if conn is None:
        conn = _get_conn()
        close_after = True
    try:
        init_autopost_durable_db(conn)
        cur = conn.execute("DELETE FROM user_social_accounts WHERE owner_user_id = ? AND platform = ? AND account_id = ?", (owner_user_id, platform.lower(), account_id))
        conn.commit()
        return cur.rowcount > 0
    finally:
        if close_after:
            conn.close()

# ----------------- Content Plans & Items -----------------
def save_content_plan_with_items(
    owner_user_id: int,
    brand_name: str,
    goal: str,
    duration_days: int,
    items: List[Dict[str, Any]],
    conn: Optional[sqlite3.Connection] = None,
) -> int:
    close_after = False
    if conn is None:
        conn = _get_conn()
        close_after = True
    try:
        init_autopost_durable_db(conn)
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        cur = conn.execute(
            """INSERT INTO content_plans (owner_user_id, brand_name, goal, duration_days, total_posts, status, created_at)
               VALUES (?, ?, ?, ?, ?, 'DRAFT', ?)""",
            (owner_user_id, brand_name, goal, duration_days, len(items), now_str)
        )
        plan_id = cur.lastrowid

        for it in items:
            conn.execute(
                """INSERT INTO content_items (
                    plan_id, owner_user_id, scheduled_date, scheduled_time, timezone,
                    platform, topic, pillar, hook, caption, cta, hashtags,
                    content_input_id, affiliate_id, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'DRAFT', ?)""",
                (
                    plan_id, owner_user_id, it.get("post_date", ""), it.get("time_slot", "11:30"),
                    it.get("timezone", "Asia/Ho_Chi_Minh"), it.get("platform", "telegram"),
                    it.get("topic", ""), it.get("pillar", ""), it.get("master_hook", ""),
                    it.get("master_caption", ""), it.get("cta", ""),
                    " ".join(it.get("hashtags", [])) if isinstance(it.get("hashtags"), list) else it.get("hashtags", ""),
                    it.get("content_input_id"), it.get("affiliate_id"), now_str
                )
            )
        conn.commit()
        return plan_id
    finally:
        if close_after:
            conn.close()

def get_content_items(plan_id: int, status: Optional[str] = None, conn: Optional[sqlite3.Connection] = None) -> List[Dict[str, Any]]:
    close_after = False
    if conn is None:
        conn = _get_conn()
        close_after = True
    try:
        init_autopost_durable_db(conn)
        q = "SELECT * FROM content_items WHERE plan_id = ?"
        params: List[Any] = [plan_id]
        if status:
            q += " AND status = ?"
            params.append(status)
        rows = conn.execute(q, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        if close_after:
            conn.close()

# ----------------- Publish Jobs & Receipts -----------------
def create_publish_job(
    content_item_id: Optional[int],
    owner_user_id: int,
    platform: str,
    channel_id: str,
    scheduled_at_utc: str,
    idempotency_key: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> int:
    close_after = False
    if conn is None:
        conn = _get_conn()
        close_after = True
    try:
        init_autopost_durable_db(conn)
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        if not idempotency_key:
            raw = f"{owner_user_id}:{content_item_id}:{platform}:{channel_id}:{scheduled_at_utc}"
            idempotency_key = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

        cur = conn.execute(
            """INSERT INTO publish_jobs (
                content_item_id, owner_user_id, platform, channel_id, scheduled_at_utc,
                status, attempt_count, idempotency_key, created_at
            ) VALUES (?, ?, ?, ?, ?, 'SCHEDULED', 0, ?, ?)
            ON CONFLICT(idempotency_key) DO UPDATE SET
                status = 'SCHEDULED',
                scheduled_at_utc = excluded.scheduled_at_utc
            """,
            (content_item_id, owner_user_id, platform.lower(), channel_id, scheduled_at_utc, idempotency_key, now_str)
        )
        conn.commit()
        return cur.lastrowid
    finally:
        if close_after:
            conn.close()

def claim_due_publish_jobs(limit: int = 10, conn: Optional[sqlite3.Connection] = None) -> List[Dict[str, Any]]:
    close_after = False
    if conn is None:
        conn = _get_conn()
        close_after = True
    try:
        init_autopost_durable_db(conn)
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        # Find due jobs
        rows = conn.execute(
            """SELECT * FROM publish_jobs 
               WHERE status = 'SCHEDULED' AND scheduled_at_utc <= ? 
               ORDER BY scheduled_at_utc ASC LIMIT ?""",
            (now_str, limit)
        ).fetchall()
        
        claimed = []
        for r in rows:
            job_id = r["id"]
            # Lease claim
            conn.execute(
                "UPDATE publish_jobs SET status = 'PUBLISHING', attempt_count = attempt_count + 1, last_attempt_at = ? WHERE id = ? AND status = 'SCHEDULED'",
                (now_str, job_id)
            )
            d = dict(r)
            d["status"] = "PUBLISHING"
            d["attempt_count"] = r["attempt_count"] + 1
            claimed.append(d)
            
        conn.commit()
        return claimed
    finally:
        if close_after:
            conn.close()

def record_publish_receipt(
    publish_job_id: int,
    owner_user_id: int,
    platform: str,
    remote_post_id: str,
    remote_url: str,
    remote_status: str = "PUBLISHED",
    conn: Optional[sqlite3.Connection] = None,
) -> int:
    close_after = False
    if conn is None:
        conn = _get_conn()
        close_after = True
    try:
        init_autopost_durable_db(conn)
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        cur = conn.execute(
            """INSERT INTO publish_receipts (
                publish_job_id, owner_user_id, platform, remote_post_id, remote_url, remote_status, api_accepted_at, verified_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(publish_job_id) DO UPDATE SET
                remote_post_id = excluded.remote_post_id,
                remote_url = excluded.remote_url,
                remote_status = excluded.remote_status,
                verified_at = excluded.verified_at
            """,
            (publish_job_id, owner_user_id, platform.lower(), remote_post_id, remote_url, remote_status, now_str, now_str)
        )
        conn.execute("UPDATE publish_jobs SET status = 'PUBLISHED' WHERE id = ?", (publish_job_id,))
        conn.commit()
        return cur.lastrowid
    finally:
        if close_after:
            conn.close()

def record_publish_failure(
    publish_job_id: int,
    error_message: str,
    status: str = "FAILED_FINAL",
    conn: Optional[sqlite3.Connection] = None,
) -> None:
    close_after = False
    if conn is None:
        conn = _get_conn()
        close_after = True
    try:
        init_autopost_durable_db(conn)
        conn.execute(
            "UPDATE publish_jobs SET status = ?, error_message = ? WHERE id = ?",
            (status, error_message, publish_job_id)
        )
        conn.commit()
    finally:
        if close_after:
            conn.close()

def get_user_published_receipts(owner_user_id: int, limit: int = 20, conn: Optional[sqlite3.Connection] = None) -> List[Dict[str, Any]]:
    close_after = False
    if conn is None:
        conn = _get_conn()
        close_after = True
    try:
        init_autopost_durable_db(conn)
        rows = conn.execute(
            "SELECT * FROM publish_receipts WHERE owner_user_id = ? ORDER BY id DESC LIMIT ?",
            (owner_user_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        if close_after:
            conn.close()

def get_user_publish_queue(owner_user_id: int, limit: int = 20, conn: Optional[sqlite3.Connection] = None) -> List[Dict[str, Any]]:
    close_after = False
    if conn is None:
        conn = _get_conn()
        close_after = True
    try:
        init_autopost_durable_db(conn)
        rows = conn.execute(
            "SELECT * FROM publish_jobs WHERE owner_user_id = ? AND status IN ('SCHEDULED', 'DUE', 'PUBLISHING', 'RETRY_WAIT', 'PAUSED') ORDER BY scheduled_at_utc ASC LIMIT ?",
            (owner_user_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        if close_after:
            conn.close()

def get_user_autopost_overview_stats(owner_user_id: int, conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
    """Calculate real runtime metrics for user's AutoPost hub."""
    close_after = False
    if conn is None:
        conn = _get_conn()
        close_after = True
    try:
        init_autopost_durable_db(conn)
        today_date = datetime.datetime.now().strftime("%Y-%m-%d")
        
        today_items = conn.execute(
            "SELECT COUNT(*) FROM content_items WHERE owner_user_id = ? AND scheduled_date = ?",
            (owner_user_id, today_date)
        ).fetchone()[0]

        queued = conn.execute(
            "SELECT COUNT(*) FROM publish_jobs WHERE owner_user_id = ? AND status IN ('SCHEDULED', 'DUE', 'PUBLISHING', 'RETRY_WAIT')",
            (owner_user_id,)
        ).fetchone()[0]

        published = conn.execute(
            "SELECT COUNT(*) FROM publish_receipts WHERE owner_user_id = ?",
            (owner_user_id,)
        ).fetchone()[0]

        errors = conn.execute(
            "SELECT COUNT(*) FROM publish_jobs WHERE owner_user_id = ? AND status IN ('FAILED_FINAL', 'POLICY_BLOCKED', 'NEEDS_AUTH')",
            (owner_user_id,)
        ).fetchone()[0]

        connected_accounts = conn.execute(
            "SELECT COUNT(DISTINCT platform) FROM user_social_accounts WHERE owner_user_id = ? AND connected = 1",
            (owner_user_id,)
        ).fetchone()[0]

        brand = get_user_brand_profile(owner_user_id, conn=conn)

        return {
            "brand_name": brand["brand_name"] if brand["is_configured"] else "Chưa thiết lập",
            "connected_channels": f"{connected_accounts}/5",
            "today_posts": today_items,
            "queued_posts": queued,
            "published_posts": published,
            "error_posts": errors,
        }
    finally:
        if close_after:
            conn.close()

# ----------------- Settings -----------------
def get_user_publish_mode(owner_user_id: int, conn: Optional[sqlite3.Connection] = None) -> str:
    close_after = False
    if conn is None:
        conn = _get_conn()
        close_after = True
    try:
        init_autopost_durable_db(conn)
        row = conn.execute("SELECT publish_mode FROM user_autopost_settings WHERE owner_user_id = ?", (owner_user_id,)).fetchone()
        if not row:
            return "MANUAL"
        return row[0]
    finally:
        if close_after:
            conn.close()

def set_user_publish_mode(owner_user_id: int, mode: str, conn: Optional[sqlite3.Connection] = None) -> None:
    close_after = False
    if conn is None:
        conn = _get_conn()
        close_after = True
    try:
        init_autopost_durable_db(conn)
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        conn.execute(
            """INSERT INTO user_autopost_settings (owner_user_id, publish_mode, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(owner_user_id) DO UPDATE SET
                   publish_mode = excluded.publish_mode,
                   updated_at = excluded.updated_at
            """,
            (owner_user_id, mode, now_str)
        )
        conn.commit()
    finally:
        if close_after:
            conn.close()
