from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")
REMOTE_WORKER_SOURCE = (ROOT / "remote_worker.py").read_text(encoding="utf-8")


def _source_between(start: str, end: str) -> str:
    start_idx = BOT_SOURCE.index(start)
    end_idx = BOT_SOURCE.index(end, start_idx)
    return BOT_SOURCE[start_idx:end_idx]


def _remote_source_between(start: str, end: str) -> str:
    start_idx = REMOTE_WORKER_SOURCE.index(start)
    end_idx = REMOTE_WORKER_SOURCE.index(end, start_idx)
    return REMOTE_WORKER_SOURCE[start_idx:end_idx]


def test_predictor_contract_outputs_required_fields_and_scene_policy():
    predictor = _source_between("def product_video_duration_predictor", "def product_video_duration_predictor_text")

    for field in (
        "predicted_intent",
        "recommended_scene_count",
        "recommended_duration_seconds",
        "min_scene_count",
        "max_scene_count",
        "scene_breakdown",
        "add_on_impact",
        "price_estimate",
        "confidence",
        "next_action",
    ):
        assert field in predictor
    assert "recommended * TASK3D_SCENE_SECONDS" in predictor
    assert "video_b14_invoice_breakdown" in predictor
    assert "Gói Trải nghiệm" in predictor


def test_predictor_intent_keywords_cover_lexus_sales_and_story_cases():
    intent = _source_between("def product_video_predict_intent", "def product_video_scene_breakdown")
    breakdown = _source_between("def product_video_scene_breakdown", "def product_video_duration_predictor")

    assert "sang trọng" in intent
    assert "phố đêm" in intent
    assert "cinematic_showcase" in intent
    assert "bán hàng" in intent
    assert "mỹ phẩm" in intent
    assert "cta" in intent
    assert "product_ad" in intent
    assert "story_video" in intent
    assert "CTA/chốt cảm xúc" in breakdown
    assert "Cảnh {index + 1}" in breakdown


def test_predictor_requested_15s_30s_1min_rounds_by_8s_scene_policy():
    duration = _source_between("def product_video_requested_duration_seconds", "def product_video_predict_intent")
    predictor = _source_between("def product_video_duration_predictor", "def product_video_duration_predictor_text")

    assert r"(\d{1,3})\s*(?:giây|giay|sec|secs|second|seconds|s)\b" in duration
    assert r"(\d{1,2})\s*(?:phút|phut|minute|minutes|min|m)\b" in duration
    assert "return 60" in duration
    assert "math.ceil(requested_seconds / max(1, TASK3D_SCENE_SECONDS))" in predictor
    assert "recommended_duration_seconds" in predictor


def test_trial_package_locks_one_scene_limits_and_addon_policy():
    predictor = _source_between("def product_video_duration_predictor", "def product_video_duration_predictor_text")

    assert "video_b14_is_trial_quality" in predictor
    assert "recommended = PRODUCT_VIDEO_TRIAL_FIXED_SCENE_COUNT" in predictor
    assert '"day": PRODUCT_VIDEO_TRIAL_LIMIT_DAY' in predictor
    assert '"week": PRODUCT_VIDEO_TRIAL_LIMIT_WEEK' in predictor
    assert '"month": PRODUCT_VIDEO_TRIAL_LIMIT_MONTH' in predictor
    assert "video_b14_trial_addon_policy" in predictor
    assert "add-on có phí bị tắt trong gói Trải nghiệm" in predictor
    assert "voice/audio tự gửi không tính phí tạo mới" in predictor


def test_scene_count_text_puts_predictor_before_invoice_and_no_provider_call():
    scene_text = _source_between("def video_b14_scene_count_text", "def video_b14_scene_count_custom_text")

    assert "product_video_duration_predictor_text(session, lang=lang)" in scene_text
    assert scene_text.index("product_video_duration_predictor_text") < scene_text.index("Sau bước này")
    assert "chưa xử lý video và chưa trừ xu" in scene_text.lower()
    for forbidden in ("run_provider_generation(", "submit_video_job(", "spend_fixed_credit_info("):
        assert forbidden not in scene_text


def test_predictor_and_invoice_are_no_provider_no_charge_planning_only():
    source = "\n".join(
        [
            _source_between("def product_video_duration_predictor", "def video_b14_build_storyboard_for_session"),
            _source_between("def video_b14_scene_count_text", "def video_b14_scene_count_custom_text"),
            _source_between("def video_b14_invoice_text", "def video_b14_invoice_keyboard"),
        ]
    )

    for forbidden in (
        "run_provider_generation(",
        "submit_video_job(",
        "video_provider_recover_existing_task(",
        "spend_fixed_credit_info(",
        "charge_user",
    ):
        assert forbidden not in source


def test_download_button_appears_only_when_delivered_artifact_available():
    keyboard = _source_between("def video_b14_queue_status_keyboard", "def video_b14_auto_refresh_json_field")

    assert "video_b14_delivered_video_artifact(jid)" in keyboard
    assert "📥 Tải video" in keyboard
    assert "b14_download_video" in keyboard
    assert "if jid and video_b14_delivered_video_artifact(jid).get(\"ok\")" in keyboard


def test_delivered_artifact_can_use_existing_result_url_when_file_path_is_missing():
    artifact = _source_between("def video_b14_delivered_video_artifact", "async def video_b14_resend_delivered_video")

    assert "result_url_present" in artifact
    assert "payload.get(\"result_url\")" in artifact
    assert "payload.get(\"canonical_result_url\")" in artifact
    assert "payload.get(\"download_url\")" in artifact
    assert "or result_url_present" in artifact
    assert "current_project.get(\"video_delivered_at\")" in artifact


def test_download_callback_recovers_existing_result_url_without_new_submit_or_charge():
    resend = _source_between("async def video_b14_resend_delivered_video", "def video_b14_auto_refresh_session_from_status")
    callback = _source_between("if action == \"b14_download_video\":", "if action == \"b14_invoice_screen\":")

    assert "video_provider_recover_existing_task(safe_int(job_id, 0), download=True)" in resend
    assert "recovered_from_result_url" in resend
    assert "Không trừ thêm Xu" in resend
    assert "submit_video_job(" not in resend
    assert "run_provider_generation(" not in resend
    assert "đang tải lại file từ kết quả cũ" in callback


def test_auto_refresh_registry_missing_is_warning_not_blocker_for_existing_job():
    status_text = _source_between("def video_b14_auto_refresh_status_text", "async def cmd_video_progress_auto_refresh_status")

    assert "recovered_from_db_read_only" in status_text
    assert "status_can_read_db_and_provider_task" in status_text
    recovered_block = status_text.split("recovered_from_db_read_only", 1)[1].split("return", 1)[0]
    assert "no_registry_after_restart" not in recovered_block


def test_product_status_mapping_is_product_video_not_video_trend():
    session = _source_between("def video_b14_auto_refresh_session_from_status", "def video_b14_auto_refresh_status_bundle")

    assert '"product_id": "multiscene_video"' in session
    assert '"video_flow": "product_video"' in session
    assert '"b14_invoice": invoice' in session
    assert "profile_id" not in session.split("return", 1)[1].split("\"current_step\"", 1)[0]


def test_public_status_payload_and_copy_show_worker_runtime_sync_guard():
    payload = _source_between("def video_remote_worker_runtime_status", "VIDEO_GATE_FEATURES")

    for expected in (
        "runtime_sha",
        "worker_sha",
        "worker_parser_version",
        "worker_code_matches_runtime",
        "worker cần sync latest main",
        "\"remote_worker\": remote_worker",
        "Product Video Worker",
        "worker code matches runtime",
        "runtime SHA",
        "worker SHA",
    ):
        assert expected in payload


def test_remote_worker_ping_and_heartbeat_send_git_sha_parser_version():
    ping = _remote_source_between("def ping_server", "def send_heartbeat")
    heartbeat = _remote_source_between("def send_heartbeat", "def complete_job")

    assert '"worker_git_sha": worker_git_sha()' in ping
    assert '"worker_parser_version": WORKER_PARSER_VERSION' in ping
    assert '"worker_git_sha": worker_git_sha()' in heartbeat
    assert '"worker_parser_version": WORKER_PARSER_VERSION' in heartbeat


def test_status_debug_persists_worker_sha_from_ping_and_heartbeat():
    ping = _source_between("async def api_worker_ping", "async def api_worker_claim")
    heartbeat = _source_between("async def api_worker_heartbeat", "async def maybe_send_remote_worker_final_video")

    for source in (ping, heartbeat):
        assert "remote_worker:worker_git_sha" in source
        assert "remote_worker:worker_parser_version" in source
        assert "set_system_setting" in source
