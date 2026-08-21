"""
Affiliate Match Engine V2 & Paid-Ads Compliance Guard.
Matches relevant products from affiliate_links and validates advertising program policy.
"""
from typing import Dict, Any, List, Optional

MATCH_THRESHOLD = 60  # Minimum relevance score to include an affiliate link

def match_affiliate_for_post(
    topic: str,
    niche: str,
    candidates: List[Dict[str, Any]],
    campaign_goal: str = "AFFILIATE_CONVERSION",
) -> Dict[str, Any]:
    """Score and select the most relevant affiliate candidate. Low score => NO_AFFILIATE."""
    if not candidates:
        return {
            "matched": False,
            "primary_affiliate": None,
            "match_score": 0,
            "match_reason": "No affiliate candidates available in database.",
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
        score += min(20, int(cand.get("product_score") or 0))
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
            "network": best_cand.get("network", "direct"),
            "disclosure": "Liên kết đối tác tiếp thị chính thức.",
            "allowed_claims": best_cand.get("allowed_claims", ""),
            "blocked_claims": best_cand.get("blocked_claims", ""),
        }
    }

def check_paid_ads_affiliate_policy(affiliate: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Check if affiliate program permits paid advertising. Fails closed (ADS_ELIGIBLE=NO) if unknown."""
    if not affiliate:
        return {"ads_eligible": False, "reason": "No affiliate attached."}

    # If the affiliate metadata explicitly prohibits paid ads
    if affiliate.get("paid_ads_allowed") is False:
        return {
            "ads_eligible": False,
            "reason": "Affiliate network program explicitly prohibits paid advertising.",
        }

    # If policy is UNKNOWN / not explicitly permitted, FAIL CLOSED
    if affiliate.get("paid_ads_allowed") is not True:
        return {
            "ads_eligible": False,
            "reason": "Affiliate program paid-advertising policy is UNKNOWN. Failing closed to prevent account ban or ad waste.",
        }

    return {
        "ads_eligible": True,
        "reason": "Affiliate program permits paid social advertising.",
    }
