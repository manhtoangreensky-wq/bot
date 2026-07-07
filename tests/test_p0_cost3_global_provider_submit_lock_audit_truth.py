from pathlib import Path

from services import video_provider_router


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _source_between(start: str, end: str) -> str:
    start_idx = BOT_SOURCE.index(start)
    end_idx = BOT_SOURCE.index(end, start_idx)
    return BOT_SOURCE[start_idx:end_idx]


def test_product_video_provider_submit_default_locked(monkeypatch):
    monkeypatch.delenv("PRODUCT_VIDEO_PROVIDER_SUBMIT_ENABLED", raising=False)

    detail = video_provider_router.product_video_submit_switch_detail({})

    assert detail["resolved"] is False
    assert detail["source"] == "default"
    assert video_provider_router.product_video_submit_enabled({}) is False


def test_product_video_provider_submit_explicit_public_flag_allows_submit(monkeypatch):
    monkeypatch.delenv("PRODUCT_VIDEO_PROVIDER_SUBMIT_ENABLED", raising=False)

    detail = video_provider_router.product_video_submit_switch_detail(
        {"PRODUCT_VIDEO_PROVIDER_SUBMIT_ENABLED": "true"}
    )

    assert detail["resolved"] is True
    assert video_provider_router.product_video_submit_enabled({"PRODUCT_VIDEO_PROVIDER_SUBMIT_ENABLED": "1"}) is True


def test_product_video_confirm_blocks_before_provider_call_when_locked():
    block = _source_between(
        'if action == "b14_confirm":',
        'if action == "b14_job_status":',
    )

    switch_idx = block.index("product_video_submit_switch_detail()")
    prepare_idx = block.index("video_b14_prepare_project_for_invoice")
    confirm_idx = block.index("confirm_video_project_invoice")
    assert switch_idx < prepare_idx < confirm_idx
    assert "provider_submit_locked" in block
    assert "provider_called" in block
    assert "xu_charged" in block


def test_video_public_status_mentions_product_video_submit_lock_state():
    payload_source = _source_between("def video_public_status_payload", "def video_public_status_text")
    text_source = _source_between("def video_public_status_text", "VIDEO_GATE_FEATURES")

    assert "product_video_submit_switch_detail" in payload_source
    assert '"PRODUCT_VIDEO_PROVIDER_SUBMIT_ENABLED"' in payload_source
    assert '"state": "ENABLED" if product_video_submit_enabled else "LOCKED"' in payload_source
    assert "Product Video provider submit" in text_source


def test_provider_spend_audit_detects_job87_style_video_submit_fixture():
    payload_fixture = {
        "source": "product_video",
        "product_type": "product_video",
        "video_flow_type": "video_ai_prompt",
        "selected_provider": "shopaikey_video",
        "provider_submit_called": True,
        "submit_accepted": True,
        "provider_task_id": "shop-task-job87",
        "charge": 0,
        "charged_xu": 0,
    }
    helper_source = _source_between(
        "def provider_spend_audit_payload_submit_markers",
        "def provider_spend_audit_records",
    )
    audit_source = _source_between("def provider_spend_audit_records", "def latest_api_debug_event")

    for key in payload_fixture:
        if key.startswith("charged"):
            continue
        assert key in helper_source + audit_source
    assert "video_jobs" in audit_source
    assert "result_json" in audit_source
    assert "provider_spend_audit_payload_submit_markers" in audit_source
    assert "provider_spend_audit_payload_provider" in audit_source
    assert "provider_spend_audit_payload_task_id" in audit_source
    assert "table=\"video_jobs\"" in audit_source


def test_debug_recover_status_and_audit_are_read_only_no_provider_submit():
    readonly_sections = "\n".join(
        [
            _source_between("def video_public_status_payload", "VIDEO_GATE_FEATURES"),
            _source_between("def provider_spend_audit_records", "def latest_api_debug_event"),
            _source_between("async def cmd_provider_spend_audit", "async def cmd_tool_test_shopaikey"),
        ]
    )
    forbidden = [
        "run_provider_generation(",
        "submit_video(",
        "shopaikey_video_create_smoke_test(",
        "shopaikey_workflow_image_to_video_create(",
        "shopaikey_image_generate(",
        "shopaikey_tts_smoke_test(",
        ".suno_create(",
    ]
    for term in forbidden:
        assert term not in readonly_sections
