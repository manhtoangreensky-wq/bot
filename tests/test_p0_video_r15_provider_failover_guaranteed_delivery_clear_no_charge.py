from pathlib import Path

from services import video_provider_router


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")
ROUTER_SOURCE = (ROOT / "services" / "video_provider_router.py").read_text(encoding="utf-8")
QUEUE_SOURCE = (ROOT / "services" / "video_project_queue.py").read_text(encoding="utf-8")


def test_result_url_validation_tracks_raw_valid_and_invalid_reason():
    assert "def video_b14_result_url_validation" in BOT_SOURCE
    assert "result_url_present_raw" in BOT_SOURCE
    assert "result_url_valid" in BOT_SOURCE
    assert "result_url_invalid_reason" in BOT_SOURCE
    assert "missing_scheme_or_host" in BOT_SOURCE
    assert "provider_error_object" in BOT_SOURCE
    assert "provider_failed_result_url_invalid" in BOT_SOURCE
    assert "if normalized == \"succeeded\" and poll_debug.get(\"recovery_result_url_present_raw\")" in BOT_SOURCE


def test_queue_progress_uses_valid_result_url_not_raw_string():
    assert "def _provider_result_url_valid" in QUEUE_SOURCE
    assert "urlparse(raw)" in QUEUE_SOURCE
    assert "parsed.scheme in {\"http\", \"https\"}" in QUEUE_SOURCE
    assert "result_url_invalid_reason" in QUEUE_SOURCE
    assert "_provider_result_url_valid(payload.get(key))" in QUEUE_SOURCE


def test_public_confirmed_fallback_source_allowed_once():
    policy = video_provider_router.product_video_provider_submit_source_policy(
        {
            "submit_source": "public_confirmed_fallback_once",
            "public_user_confirmed": True,
        },
        public_submit_enabled=True,
    )
    assert policy["provider_submit_allowed"] is True
    assert policy["submit_source"] == "public_confirmed_fallback_once"

    assert video_provider_router.product_video_controlled_fallback_allowed(
        "provider_failed_result_url_invalid",
        {
            "submit_source": "public_user_final_confirm",
            "public_user_confirmed": True,
            "fallback_count": 0,
        },
    )
    assert not video_provider_router.product_video_controlled_fallback_allowed(
        "provider_failed_result_url_invalid",
        {
            "submit_source": "public_user_final_confirm",
            "public_user_confirmed": True,
            "fallback_count": 1,
        },
    )


def test_hidden_debug_recover_status_sources_never_allow_fallback_submit():
    for source in ("codex_test", "smoke", "debug", "recover", "status", "background_retry"):
        policy = video_provider_router.product_video_provider_submit_source_policy(
            {"submit_source": source, "public_user_confirmed": True},
            public_submit_enabled=True,
        )
        assert policy["provider_submit_allowed"] is False
        assert not video_provider_router.product_video_controlled_fallback_allowed(
            "provider_download_failed",
            {"submit_source": source, "public_user_confirmed": True, "fallback_count": 0},
        )


def test_router_invalid_result_url_prevents_download_and_enables_fallback_path():
    assert "result_diagnostic = _failed_result_url_diagnostic(result_url_value)" in ROUTER_SOURCE
    assert "if not result_diagnostic.get(\"result_url_valid\")" in ROUTER_SOURCE
    assert "provider_failed_result_url_invalid" in ROUTER_SOURCE
    assert "_product_video_paid_fallback_blocked(blocker, env, metadata)" in ROUTER_SOURCE
    assert "fallback_submit_source" in ROUTER_SOURCE
    assert "public_confirmed_fallback_once" in ROUTER_SOURCE


def test_recovery_and_finance_debug_remain_no_charge_until_delivered():
    assert "charge_policy\": \"after_valid_mp4_delivery\"" in BOT_SOURCE
    assert "charge_after_delivery_gate" in BOT_SOURCE
    assert "delivery_failed_no_charge" in BOT_SOURCE
    assert "wallet truth" in BOT_SOURCE
    assert "no wallet charge recorded" in BOT_SOURCE
    assert "product_video_r9_charge_allowed" in BOT_SOURCE


def test_auto_db_poll_text_and_product_mapping_are_clean():
    assert "Auto poll DB: <code>đang theo dõi provider task</code>" in BOT_SOURCE
    assert "autonomous_db_poll_enabled" in BOT_SOURCE
    assert "autonomous_db_poll_active" in BOT_SOURCE
    assert "raw_product_type = video_final_output.product_type_from_project" in BOT_SOURCE
    assert "product_type = \"multiscene_video\" if str(raw_product_type or \"\") == \"video_trend\"" in BOT_SOURCE

