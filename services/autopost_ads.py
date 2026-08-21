"""
Ads Control Plane & Autonomy Levels (L0..L5).
Supports Meta Ads, TikTok Ads, Google Ads within strict Owner Budget Envelopes and Emergency Kill Switch.
"""
from typing import Dict, Any, List, Optional
import datetime

DEFAULT_OWNER_BUDGET_ENVELOPE = {
    "enabled": True,
    "max_daily_spend_vnd": 300000,       # 300,000 VNĐ / day
    "max_campaign_spend_vnd": 1500000,   # 1,500,000 VNĐ / campaign
    "max_total_open_budget_vnd": 3000000, # 3,000,000 VNĐ total active
    "allowed_platforms": ["meta", "tiktok", "google"],
    "allowed_objectives": ["TRAFFIC", "CONVERSIONS", "LEADS"],
    "allowed_brands": ["TOAN AAS"],
    "paid_ads_allowed_only": True,
    "max_cpa_threshold_vnd": 50000,      # Max 50,000 VNĐ per conversion before auto-pause
    "emergency_kill_switch": False,       # True => stops all active campaigns immediately
    "autonomy_level": 3,                 # L0..L5 (Default L3: Draft / Paused external creation only)
}

def evaluate_organic_to_ads(post_metrics: Dict[str, Any], threshold_score: int = 70) -> Dict[str, Any]:
    """Explainable decision engine for converting organic posts into paid ad drafts."""
    views = int(post_metrics.get("views") or 0)
    likes = int(post_metrics.get("likes") or 0)
    comments = int(post_metrics.get("comments") or 0)
    shares = int(post_metrics.get("shares") or 0)
    clicks = int(post_metrics.get("clicks") or 0)

    # Engagement rate score (0..100)
    score = 0
    if views > 0:
        engagement_rate = ((likes + comments * 2 + shares * 3) / views) * 100
        score += min(50, int(engagement_rate * 10))
    if clicks > 5:
        score += min(30, clicks * 3)
    if shares > 3:
        score += 20

    reasons = [
        f"Views: {views}, Likes: {likes}, Comments: {comments}, Shares: {shares}, Clicks: {clicks}.",
        f"Calculated Engagement/Conversion Score: {score}/100.",
    ]

    if score < threshold_score:
        return {
            "eligible": False,
            "ads_score": score,
            "decision": "NO_ADS",
            "reasons": reasons + [f"Score ({score}) below qualification threshold ({threshold_score})."],
        }

    return {
        "eligible": True,
        "ads_score": score,
        "decision": "ADS_DRAFT",
        "reasons": reasons + [f"High organic performance qualified post for paid amplification draft."],
        "recommended_objective": "TRAFFIC" if clicks > 10 else "ENGAGEMENT",
        "recommended_daily_budget_vnd": 100000,
    }

def validate_ad_spend_request(
    platform: str,
    budget_vnd: int,
    objective: str,
    brand_name: str,
    envelope: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Enforce Owner Budget Envelope. Never spend without policy pass."""
    env = envelope or DEFAULT_OWNER_BUDGET_ENVELOPE

    # Emergency kill switch check
    if env.get("emergency_kill_switch"):
        return {"approved": False, "reason": "EMERGENCY_KILL_SWITCH_ACTIVE: All advertising mutations are blocked."}

    # Platform check
    if platform.lower() not in [p.lower() for p in env.get("allowed_platforms", [])]:
        return {"approved": False, "reason": f"Platform {platform} not in allowed_platforms envelope."}

    # Brand check
    if brand_name not in env.get("allowed_brands", []):
        return {"approved": False, "reason": f"Brand {brand_name} not in allowed_brands envelope."}

    # Objective check
    if objective not in env.get("allowed_objectives", []):
        return {"approved": False, "reason": f"Objective {objective} not in allowed_objectives envelope."}

    # Daily budget cap check
    max_daily = int(env.get("max_daily_spend_vnd") or 0)
    if budget_vnd > max_daily:
        return {
            "approved": False,
            "reason": f"Requested daily budget ({budget_vnd:,}đ) exceeds Owner max_daily cap ({max_daily:,}đ). OWNER_APPROVAL_REQUIRED.",
        }

    # Autonomy level check (L4/L5 required for active spend)
    autonomy = int(env.get("autonomy_level") or 0)
    if autonomy < 4:
        return {
            "approved": False,
            "reason": f"Current autonomy level L{autonomy} requires explicit Owner activation approval (L4/L5 needed for spend).",
        }

    return {"approved": True, "reason": "Spend request is fully compliant with Owner Budget Envelope."}
