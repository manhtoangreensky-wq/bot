import subprocess
from pathlib import Path

from services import aas_shared_knowledge as shared
from services import ai_chatbot_copilot as aichat
from services import telegram_business_support as cskh


ROOT = Path(__file__).resolve().parents[1]


def _enabled_state(user_id="aichat2-user"):
    state = aichat.default_state()
    state, _enabled = aichat.enable_with_consent(state, user_id)
    return state


def _ask(state, text, user_id="aichat2-user", *, queue_unknown=False):
    return aichat.process_message(state, user_id, text, queue_unknown=queue_unknown)


def _changed_files():
    result = subprocess.run(
        ["git", "diff", "--name-only", "origin/main"],
        check=False,
        text=True,
        capture_output=True,
        cwd=ROOT,
    )
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def test_pricing_docs_are_integrated():
    status = shared.docs_status()

    assert status["pricing_doc_loaded"] is True
    assert status["guide_doc_loaded"] is True


def test_aichat_100k_to_xu_is_exact():
    state = _enabled_state()

    state, result = _ask(state, "100k được nhiêu Xu")

    assert result["intent_id"] == "pricing_topup"
    assert "100.000đ = 1.000 Xu" in result["reply"]
    assert "pricing_doc" in result["source"]
    assert result["provider_call_allowed"] is False


def test_aichat_image_pricing_uses_doc_numbers():
    state = _enabled_state()

    state, result = _ask(state, "Tạo ảnh bao nhiêu")

    assert result["intent_id"] == "image_ai_pricing"
    for marker in ["50 Xu", "150 Xu", "200 Xu", "300 Xu", "400 Xu", "500 Xu", "600 Xu"]:
        assert marker in result["reply"]
    assert "pricing_doc" in result["source"]


def test_aichat_video_pricing_uses_doc_tiers_and_scene_hint():
    state = _enabled_state()

    state, result = _ask(state, "Tạo video giá sao")

    assert result["intent_id"] == "product_video_pricing"
    for marker in ["200 Xu", "300 Xu", "400 Xu", "500 Xu", "600 Xu", "800 Xu", "1000 Xu", "1200 Xu", "1500 Xu"]:
        assert marker in result["reply"]
    assert "1 cảnh khoảng 6 giây" in result["reply"]
    assert "pricing_doc" in result["source"]


def test_aichat_subtitle_dub_2000_chars_calculates_total():
    state = _enabled_state()

    state, result = _ask(state, "Phụ đề + lồng tiếng 2000 ký tự bao nhiêu")

    assert result["intent_id"] == "subdub_pricing"
    assert "2.000 ký tự" in result["reply"]
    assert "dịch phụ đề 180 Xu" in result["reply"]
    assert "lồng tiếng 180 Xu" in result["reply"]
    assert "tổng 360 Xu" in result["reply"]


def test_aichat_prompt_video_returns_concrete_free_prompt():
    state = _enabled_state()

    state, result = _ask(state, "Tạo prompt video nước hoa nam")

    assert result["action_guard"] == "free_text_only"
    assert "nước hoa nam" in result["reply"]
    assert "9:16" in result["reply"]
    assert "provider" not in cskh._fold(result["reply"])
    assert result["provider_call_allowed"] is False


def test_aichat_video_sales_request_guides_flow_without_confirming():
    state = _enabled_state()

    state, result = _ask(state, "Tôi muốn làm video bán hàng mỹ phẩm")

    assert result["intent_id"] == "product_video_consulting"
    assert "mỹ phẩm" in result["reply"]
    assert "tỉ lệ khung hình" in result["reply"]
    assert "màn xác nhận" in result["reply"]
    assert result["xu_charge_allowed"] is False


def test_aichat_video_missing_file_safe_status_guidance():
    state = _enabled_state()

    state, result = _ask(state, "Chưa thấy video")
    folded = cskh._fold(result["reply"])

    assert result["intent_id"] == "product_video_failed_no_file"
    assert "mã xử lý" in result["reply"]
    assert "da hoan xu" not in folded
    assert "tu hua hoan xu" in folded


def test_aichat_refund_request_does_not_promise_credit():
    state = _enabled_state()

    state, result = _ask(state, "Hoàn Xu cho tôi")
    folded = cskh._fold(result["reply"])

    assert result["action_guard"] == "admin_review_required"
    assert "da hoan xu" not in folded
    assert "da cong xu" not in folded
    assert "admin kiểm tra" in result["reply"]


def test_aichat_short_context_resolves_100k_as_topup():
    state = _enabled_state()

    state, first = _ask(state, "nạp xu giá sao")
    state, followup = _ask(state, "100k được nhiêu")

    assert first["intent_id"] == "pricing_topup"
    assert followup["intent_id"] == "pricing_topup"
    assert "100.000đ = 1.000 Xu" in followup["reply"]
    assert aichat.status_payload(state, "aichat2-user")["conversation_memory"]["last_product"] == "payment_xu"


def test_cskh_uses_same_pricing_and_guide_sources():
    video = cskh.classify_cskh_message("Tạo video giá sao")
    subdub = cskh.classify_cskh_message("Phụ đề + lồng tiếng 2000 ký tự bao nhiêu")

    assert video["intent_id"] == "product_video_pricing"
    assert "pricing_doc" in video["source"]
    assert "1500 Xu" in video["reply"]
    assert subdub["intent_id"] == "subdub_pricing"
    assert "tổng 360 Xu" in subdub["reply"]
    assert "guide_doc" in subdub["source"]


def test_trace_has_intent_source_confidence_and_learning_flag(tmp_path, monkeypatch):
    monkeypatch.setenv("CSKH_BUSINESS_STATE_FILE", str(tmp_path / "cskh_state.json"))
    monkeypatch.setenv("AICHAT_COPILOT_STATE_FILE", str(tmp_path / "aichat_state.json"))
    state = _enabled_state()

    state, _result = _ask(state, "Tạo ảnh bao nhiêu")
    trace = aichat.status_payload(state, "aichat2-user")["last_trace"]

    assert trace["intent_id"] == "image_ai_pricing"
    assert "pricing_doc" in trace["source"]
    assert trace["confidence"] == "high"
    assert trace["learning_queue"] is False


def test_no_real_provider_calls_or_forbidden_runtime_scope():
    changed = _changed_files()
    forbidden_prefixes = ("providers/",)
    forbidden_terms = ("music", "suno", "voice_provider", "video_provider", "product_video_provider", "payos", "wallet")

    assert not any(path.startswith(forbidden_prefixes) for path in changed)
    assert not any(any(term in path.lower() for term in forbidden_terms) and not path.startswith("tests/") for path in changed)
