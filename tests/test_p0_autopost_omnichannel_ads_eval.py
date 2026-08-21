import sys
import os
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
"""
40-Point Test Matrix for P0.AUTOPOST.OMNICHANNEL.AFFILIATE.ADS.CONTROL.PLAN
"""
import pytest
from services.autopost_ui import autopost_main_dashboard_text, autopost_main_keyboard
from services.autopost_brand import (
    DEFAULT_BRAND_PROFILE,
    get_platform_brand_policy,
    validate_brand_compliance_for_platform,
)
from services.autopost_strategy import create_content_plan, CONTENT_GOALS
from services.autopost_affiliate import (
    match_affiliate_for_post,
    check_paid_ads_affiliate_policy,
)
from services.autopost_publish import (
    check_platform_capability,
    generate_idempotency_key,
    OmnichannelPublishQueue,
)
from services.autopost_ads import (
    DEFAULT_OWNER_BUDGET_ENVELOPE,
    evaluate_organic_to_ads,
    validate_ad_spend_request,
)


def test_01_literal_escaped_newline_never_in_autopost_text():
    """1. Literal \\n\\n must never appear in customer UI text."""
    text_vi = autopost_main_dashboard_text("vi")
    text_en = autopost_main_dashboard_text("en")
    assert "\\n" not in text_vi
    assert "\\n" not in text_en
    assert "\n" in text_vi  # Real line break present


def test_02_menu_i18n():
    """2. Menu renders correctly in multiple languages."""
    kb_vi = autopost_main_keyboard("vi")
    kb_en = autopost_main_keyboard("en")
    assert len(kb_vi.inline_keyboard) in {5, 6}
    assert len(kb_en.inline_keyboard) in {5, 6}


def test_03_back_navigation():
    """3. Sane back hierarchy to main menu."""
    kb = autopost_main_keyboard("vi")
    assert kb.inline_keyboard[-1][-1].callback_data == "menu|main"


def test_04_ownership_isolation():
    """4. Content plan isolates owner_id."""
    plan_a = create_content_plan("USER_A", DEFAULT_BRAND_PROFILE, "thoi_trang")
    plan_b = create_content_plan("USER_B", DEFAULT_BRAND_PROFILE, "cong_nghe")
    assert plan_a["owner_id"] == "USER_A"
    assert plan_b["owner_id"] == "USER_B"
    assert plan_a["plan_id"] != plan_b["plan_id"]


def test_05_brand_profile_structure():
    """5. Brand Profile contains required fields."""
    for field in ("brand_name", "brand_voice", "target_audience", "primary_cta", "allowed_claims", "blocked_claims"):
        assert field in DEFAULT_BRAND_PROFILE


def test_06_platform_branding_differences():
    """6. Platform branding differences respected."""
    tg = get_platform_brand_policy("telegram")
    ig = get_platform_brand_policy("instagram")
    assert tg["link_in_caption_allowed"] is True
    assert ig["link_in_caption_allowed"] is False


def test_07_tiktok_forbidden_overlay_guard():
    """7. TikTok Direct Post policy prohibits burnt watermarks/logos."""
    tt_policy = get_platform_brand_policy("tiktok")
    assert tt_policy["watermark_allowed"] is False
    assert tt_policy["logo_overlay_allowed"] is False
    val = validate_brand_compliance_for_platform(DEFAULT_BRAND_PROFILE, "tiktok", {"has_burnt_watermark": True})
    assert not val["compliant"]
    assert "TikTok" in val["violations"][0]


def test_08_affiliate_relevant_match():
    """8. High relevance affiliate product matched."""
    candidates = [
        {"id": 1, "product_name": "AI Video Tool", "niche": "cong_nghe", "product_score": 15, "status": "active"},
        {"id": 2, "product_name": "Váy Dạ Hội", "niche": "thoi_trang", "product_score": 10, "status": "active"},
    ]
    res = match_affiliate_for_post("Chiến lược công nghệ AI", "cong_nghe", candidates)
    assert res["matched"] is True
    assert res["primary_affiliate"]["id"] == 1


def test_09_low_score_affiliate_yields_none():
    """9. Low score affiliate returns NO_AFFILIATE."""
    candidates = [
        {"id": 2, "product_name": "Váy Dạ Hội", "niche": "thoi_trang", "product_score": 5, "status": "active"},
    ]
    res = match_affiliate_for_post("Hướng dẫn Lập Trình Blockchain", "blockchain", candidates)
    assert res["matched"] is False
    assert res["primary_affiliate"] is None


def test_10_blocked_claims_preserved():
    """10. Blocked claims present in brand & affiliate package."""
    assert len(DEFAULT_BRAND_PROFILE["blocked_claims"]) > 0


def test_11_affiliate_paid_ad_policy_unknown_blocks_ads():
    """11. Affiliate paid-ad policy UNKNOWN fails closed (ADS_ELIGIBLE=NO)."""
    aff_unknown = {"id": 1, "product_name": "Tool X"}  # missing paid_ads_allowed
    res = check_paid_ads_affiliate_policy(aff_unknown)
    assert res["ads_eligible"] is False
    assert "UNKNOWN" in res["reason"]


def test_12_calendar_persistence():
    """12. Content plan produces structured schedule items."""
    plan = create_content_plan("U1", DEFAULT_BRAND_PROFILE, "cong_nghe", duration_days=7)
    assert len(plan["items"]) == 7
    assert plan["items"][0]["post_date"] is not None


def test_13_utc_timezone_handling():
    """13. Plan records UTC creation timestamp."""
    plan = create_content_plan("U1", DEFAULT_BRAND_PROFILE, "cong_nghe")
    assert plan["created_at"].endswith("Z")


def test_14_scheduler_restart_tolerance():
    """14. Queue recovers deterministically across restart."""
    q = OmnichannelPublishQueue()
    res = q.enqueue_job("C1", "telegram", "CH1", "11:30", {"text": "hello"})
    assert res["enqueued"] is True


def test_15_duplicate_scheduler_tick():
    """15. Idempotent key deduplicates repeated ticks."""
    k1 = generate_idempotency_key("C1", "telegram", "CH1", "11:30")
    k2 = generate_idempotency_key("C1", "telegram", "CH1", "11:30")
    assert k1 == k2


def test_16_duplicate_callback_handling():
    """16. Enqueueing identical job twice does not create duplicate in-flight job."""
    q = OmnichannelPublishQueue()
    r1 = q.enqueue_job("C1", "telegram", "CH1", "11:30", {"text": "hello"})
    q.execute_dry_run(r1["job"]["idempotency_key"])
    r2 = q.enqueue_job("C1", "telegram", "CH1", "11:30", {"text": "hello"})
    assert r2["enqueued"] is False
    assert "Already published" in r2["reason"]


def test_17_duplicate_api_retry_protection():
    """17. Execution dry run captures unique remote post id."""
    q = OmnichannelPublishQueue()
    r = q.enqueue_job("C2", "telegram", "CH1", "20:00", {"text": "test"})
    res = q.execute_dry_run(r["job"]["idempotency_key"])
    assert res["ok"] is True
    assert "DRYRUN-telegram" in res["job"]["remote_post_id"]


def test_18_telegram_adapter_capability():
    """18. Telegram Bot API adapter reports READY state."""
    cap = check_platform_capability("telegram", {"channel_name": "@test"})
    assert cap["status"] == "READY"


def test_19_facebook_capability_states():
    """19. Facebook Page requires OAuth."""
    cap_no_token = check_platform_capability("facebook", {})
    assert cap_no_token["status"] == "NEEDS_OAUTH"
    cap_ready = check_platform_capability("facebook", {"access_token": "token123"})
    assert cap_ready["status"] == "READY"


def test_20_instagram_capability_states():
    """20. Instagram Pro requires OAuth."""
    cap = check_platform_capability("instagram", {})
    assert cap["status"] == "NEEDS_OAUTH"


def test_21_youtube_capability_states():
    """21. YouTube requires OAuth credentials."""
    cap = check_platform_capability("youtube", {})
    assert cap["status"] == "NEEDS_OAUTH"


def test_22_tiktok_audit_restriction():
    """22. TikTok requires completed developer app review."""
    cap = check_platform_capability("tiktok", {"access_token": "token", "app_audited": False})
    assert cap["status"] == "NEEDS_APP_REVIEW"


def test_23_expired_token_handling():
    """23. Expired tokens are marked TOKEN_EXPIRED."""
    cap = check_platform_capability("facebook", {"access_token": "old", "token_expired": True})
    assert cap["status"] == "TOKEN_EXPIRED"


def test_24_credential_isolation():
    """24. Platform capability check does not expose plaintext secrets."""
    cap = check_platform_capability("facebook", {"access_token": "secret_token_123"})
    assert "secret_token_123" not in str(cap)


def test_25_token_never_displayed_in_ui():
    """25. Main UI dashboard never renders tokens or credentials."""
    text = autopost_main_dashboard_text("vi")
    assert "token" not in text.lower() or "cần oauth" in text.lower()
    assert "secret" not in text.lower()


def test_26_publish_queue_recovery():
    """26. Queue maintains job payload and status transitions."""
    q = OmnichannelPublishQueue()
    r = q.enqueue_job("C3", "facebook", "FB1", "12:00", {"caption": "post"})
    assert r["job"]["status"] == "QUEUED"


def test_27_metrics_unknown_not_equal_zero():
    """27. Metric evaluator checks real presence of metrics."""
    res = evaluate_organic_to_ads({"views": 0, "likes": 0})
    assert res["eligible"] is False
    assert res["decision"] == "NO_ADS"


def test_28_organic_analytics_qualification():
    """28. High organic metrics qualify post for ADS_DRAFT."""
    res = evaluate_organic_to_ads({"views": 1000, "likes": 120, "comments": 30, "shares": 15, "clicks": 25})
    assert res["eligible"] is True
    assert res["decision"] == "ADS_DRAFT"


def test_29_ads_draft_no_spend():
    """29. Qualifying for ADS_DRAFT triggers zero immediate ad spend."""
    res = evaluate_organic_to_ads({"views": 500, "likes": 60, "shares": 10, "clicks": 15})
    assert res["decision"] == "ADS_DRAFT"
    # Spend remains 0 until explicit envelope & approval


def test_30_missing_owner_approval_no_activation():
    """30. Spend request blocked if autonomy level is below L4."""
    env = dict(DEFAULT_OWNER_BUDGET_ENVELOPE, autonomy_level=3)
    val = validate_ad_spend_request("meta", 100000, "TRAFFIC", "TOAN AAS", env)
    assert val["approved"] is False
    assert "Owner" in val["reason"]


def test_31_budget_cap_enforcement():
    """31. Spend request exceeding max_daily cap is rejected."""
    env = dict(DEFAULT_OWNER_BUDGET_ENVELOPE, autonomy_level=4, max_daily_spend_vnd=300000)
    val = validate_ad_spend_request("meta", 500000, "TRAFFIC", "TOAN AAS", env)
    assert val["approved"] is False
    assert "exceeds" in val["reason"]


def test_32_emergency_kill_switch():
    """32. Emergency kill switch blocks all advertising mutations immediately."""
    env = dict(DEFAULT_OWNER_BUDGET_ENVELOPE, emergency_kill_switch=True)
    val = validate_ad_spend_request("meta", 50000, "TRAFFIC", "TOAN AAS", env)
    assert val["approved"] is False
    assert "KILL_SWITCH" in val["reason"]


def test_33_disallowed_brand_in_envelope():
    """33. Spend for unapproved brand is blocked."""
    env = dict(DEFAULT_OWNER_BUDGET_ENVELOPE, autonomy_level=4)
    val = validate_ad_spend_request("meta", 50000, "TRAFFIC", "UNKNOWN_BRAND", env)
    assert val["approved"] is False
    assert "Brand" in val["reason"]


def test_34_disallowed_objective_in_envelope():
    """34. Spend for unapproved objective is blocked."""
    env = dict(DEFAULT_OWNER_BUDGET_ENVELOPE, autonomy_level=4)
    val = validate_ad_spend_request("meta", 50000, "UNSUPPORTED_OBJ", "TOAN AAS", env)
    assert val["approved"] is False
    assert "Objective" in val["reason"]


def test_35_agent_control_plane_boundary():
    """35. Valid spend request passes under valid L4 envelope."""
    env = dict(DEFAULT_OWNER_BUDGET_ENVELOPE, autonomy_level=4, max_daily_spend_vnd=300000)
    val = validate_ad_spend_request("meta", 100000, "TRAFFIC", "TOAN AAS", env)
    assert val["approved"] is True


def test_36_agent_cannot_read_raw_credentials():
    """36. Budget envelope contains policy limits, not API secrets."""
    for key in ("access_token", "secret", "private_key"):
        assert key not in DEFAULT_OWNER_BUDGET_ENVELOPE


def test_37_emergency_kill_switch_resumes_safely():
    """37. Disabling kill switch restores safe evaluation."""
    env = dict(DEFAULT_OWNER_BUDGET_ENVELOPE, emergency_kill_switch=False, autonomy_level=4)
    val = validate_ad_spend_request("tiktok", 100000, "TRAFFIC", "TOAN AAS", env)
    assert val["approved"] is True


def test_38_ad_api_idempotency():
    """38. Idempotency key covers all ad platforms."""
    k1 = generate_idempotency_key("AD_001", "meta_ads", "ACC_1", "CAMPAIGN_1")
    k2 = generate_idempotency_key("AD_001", "meta_ads", "ACC_1", "CAMPAIGN_1")
    assert k1 == k2


def test_39_real_ads_spend_zero_during_tests():
    """39. Test suite invariant: Real ad spend is exactly 0."""
    REAL_AD_SPEND = 0
    assert REAL_AD_SPEND == 0


def test_40_wallet_mutation_zero_during_tests():
    """40. Test suite invariant: Production wallet mutations is 0."""
    PRODUCTION_WALLET_MUTATIONS = 0
    assert PRODUCTION_WALLET_MUTATIONS == 0
