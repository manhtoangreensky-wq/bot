"""
Omnichannel Publish Adapters & Capability Matrix.
Supports Telegram, Facebook Pages, Instagram Professional, YouTube, TikTok with idempotent execution.
"""
from typing import Dict, Any, List, Optional
import datetime
import hashlib

PLATFORM_CAPABILITY_STATES = [
    "READY",
    "NEEDS_OAUTH",
    "NEEDS_PERMISSION",
    "NEEDS_APP_REVIEW",
    "TOKEN_EXPIRED",
    "MANUAL_ONLY",
    "UNSUPPORTED",
    "BLOCKED",
]

def check_platform_capability(platform: str, channel_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Return runtime capability state for a given platform connection."""
    platform = platform.lower()
    channel_config = channel_config or {}

    if platform == "telegram":
        # Telegram Bot API: Ready if bot is admin in channel/group
        if channel_config.get("chat_id") or channel_config.get("channel_name"):
            return {"status": "READY", "message": "Bot API publishing ready to authorized channel/group."}
        return {"status": "READY", "message": "Telegram Bot API available. Add bot as admin to publish."}

    if platform == "facebook":
        if not channel_config.get("access_token"):
            return {"status": "NEEDS_OAUTH", "message": "Facebook Page requires OAuth authorization."}
        if channel_config.get("token_expired"):
            return {"status": "TOKEN_EXPIRED", "message": "Facebook Page access token has expired."}
        return {"status": "READY", "message": "Facebook Pages API ready for organic publishing."}

    if platform == "instagram":
        if not channel_config.get("access_token"):
            return {"status": "NEEDS_OAUTH", "message": "Instagram Professional requires Meta Business OAuth."}
        return {"status": "READY", "message": "Instagram Professional Content Publishing API ready."}

    if platform == "youtube":
        if not channel_config.get("oauth_credentials"):
            return {"status": "NEEDS_OAUTH", "message": "YouTube Data API requires Google OAuth channel authorization."}
        return {"status": "READY", "message": "YouTube Data API upload ready."}

    if platform == "tiktok":
        # Direct Post requires App Review and registered audit status
        if not channel_config.get("access_token"):
            return {"status": "NEEDS_OAUTH", "message": "TikTok requires creator OAuth login."}
        if not channel_config.get("app_audited"):
            return {"status": "NEEDS_APP_REVIEW", "message": "TikTok Direct Post requires completed TikTok developer app audit."}
        return {"status": "READY", "message": "TikTok Content Posting API ready."}

    return {"status": "UNSUPPORTED", "message": f"Platform {platform} is not currently supported."}

def generate_idempotency_key(content_id: str, platform: str, channel_id: str, schedule_slot: str) -> str:
    """Deterministic idempotency key preventing duplicate posts on retries/restarts."""
    raw = f"{content_id}:{platform}:{channel_id}:{schedule_slot}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

class OmnichannelPublishQueue:
    """Idempotent in-memory / persistent publish queue manager."""
    def __init__(self):
        self._jobs: Dict[str, Dict[str, Any]] = {}

    def enqueue_job(self, content_id: str, platform: str, channel_id: str, schedule_slot: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        idempotency_key = generate_idempotency_key(content_id, platform, channel_id, schedule_slot)
        
        # Deduplication check
        if idempotency_key in self._jobs:
            existing = self._jobs[idempotency_key]
            if existing["status"] in {"PUBLISHED", "PUBLISHING"}:
                return {"enqueued": False, "reason": "Already published or in-flight", "job": existing}

        job = {
            "publish_job_id": f"PUB-{datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{idempotency_key[:6]}",
            "idempotency_key": idempotency_key,
            "content_id": content_id,
            "platform": platform,
            "channel_id": channel_id,
            "schedule_slot": schedule_slot,
            "payload": payload,
            "status": "QUEUED",
            "attempt_count": 0,
            "created_at": datetime.datetime.utcnow().isoformat() + "Z",
        }
        self._jobs[idempotency_key] = job
        return {"enqueued": True, "job": job}

    def execute_dry_run(self, idempotency_key: str) -> Dict[str, Any]:
        job = self._jobs.get(idempotency_key)
        if not job:
            return {"ok": False, "error": "Job not found"}
        
        job["status"] = "PUBLISHED"
        job["published_at"] = datetime.datetime.utcnow().isoformat() + "Z"
        job["remote_post_id"] = f"DRYRUN-{job['platform']}-{idempotency_key[:8]}"
        job["remote_url"] = f"https://mock.{job['platform']}.com/post/{job['remote_post_id']}"
        return {"ok": True, "dry_run": True, "job": job}
