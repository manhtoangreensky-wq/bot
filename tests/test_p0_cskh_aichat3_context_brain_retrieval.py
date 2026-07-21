import subprocess
from pathlib import Path

from services import aas_shared_knowledge as shared
from services import ai_chatbot_copilot as aichat
from services import telegram_business_support as cskh


ROOT = Path(__file__).resolve().parents[1]


def _enabled_state(user_id="aichat3-user"):
    state = aichat.default_state()
    state, _enabled = aichat.enable_with_consent(state, user_id)
    return state


def _event(text="", *, caption="", media_type="", message_id="m1"):
    return cskh.BusinessMessageEvent(
        update_type="business_message",
        business_connection_id="bc-1",
        chat_id="chat-1",
        from_user_id="customer-1",
        from_is_bot=False,
        text=text,
        caption=caption,
        message_id=message_id,
        timestamp=1000.0,
        media_type=media_type,
    )


def _changed_files():
    result = subprocess.run(
        ["git", "diff", "--name-only", "origin/main"],
        check=False,
        text=True,
        capture_output=True,
        cwd=ROOT,
    )
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def _isolated_env(tmp_path, monkeypatch):
    monkeypatch.setenv("CSKH_BUSINESS_STATE_FILE", str(tmp_path / "cskh_state.json"))
    monkeypatch.setenv("AICHAT_COPILOT_STATE_FILE", str(tmp_path / "aichat_state.json"))


def test_context_file_loaded_with_required_version_and_sections():
    context = shared.load_context_brain()
    sections = context["sections"]

    assert context["loaded"] is True
    assert context["version"] == "P0.CSKH.AICHAT.3.2026-07-08"
    assert context["path"].endswith("knowledge\\toan_aas_cskh_aichat_context.md") or context["path"].endswith("knowledge/toan_aas_cskh_aichat_context.md")
    for section in ["brand_voice", "hard_rules", "pricing_facts", "usage_guides", "intents", "scenario_dialogues", "fallback_policy", "human_last_reply_policy", "learning_policy"]:
        assert section in sections


def test_alo_and_question_mark_never_go_silent():
    state = _enabled_state()

    state, alo = aichat.process_message(state, "aichat3-user", "alo", queue_unknown=False)
    question = cskh.classify_cskh_message("?")

    assert alo["replied"] is True
    assert "Dạ em" in alo["reply"]
    assert any(word in alo["reply"] for word in ["video", "ảnh", "SubDub", "nạp Xu", "giá"])
    assert question["intent_id"] == "vague_or_unclear"
    assert "giá" in question["reply"]
    assert "context_file" in question["source"]


def test_image_without_caption_is_actionable_media_not_suppressed():
    event = _event(media_type="photo")
    result = cskh.classify_business_event(event)
    state = cskh.default_state()
    state["enabled"] = True
    state["connections"]["bc-1"] = {"status": "active"}
    guard = cskh.evaluate_auto_reply_guard(state, event, now=1000, classification=result)

    assert result["intent_id"] == "file_without_instruction"
    assert "nhận được file" in result["reply"]
    assert "phụ đề" in result["reply"]
    assert guard["allowed"] is True
    assert guard["non_text_or_service_suppressed"] is False
    assert guard["actionable_media"] is True


def test_context_pricing_answers_are_exact():
    topup = cskh.classify_cskh_message("100k được nhiêu Xu")
    video = cskh.classify_cskh_message("tạo video bao nhiêu")
    image = cskh.classify_cskh_message("tạo ảnh bao nhiêu")
    subdub = cskh.classify_cskh_message("phụ đề + lồng tiếng 2000 ký tự bao nhiêu")

    assert "100.000đ = 1.000 Xu" in topup["reply"]
    for marker in ["200 Xu", "300 Xu", "400 Xu", "500 Xu", "600 Xu", "800 Xu", "1000 Xu", "1200 Xu", "1500 Xu"]:
        assert marker in video["reply"]
    assert "1 cảnh = 8s" in video["reply"]
    for marker in ["50 Xu", "150 Xu", "200 Xu", "300 Xu", "400 Xu", "500 Xu", "600 Xu"]:
        assert marker in image["reply"]
    assert "2.000 ký tự" in subdub["reply"]
    assert "tổng 360 Xu" in subdub["reply"]
    for result in [topup, video, image, subdub]:
        assert result["context_section_used"] == "pricing_facts"
        assert result["source_file_version"] == "P0.CSKH.AICHAT.3.2026-07-08"


def test_complaints_ask_for_case_id_without_fake_generosity():
    charged = cskh.classify_cskh_message("bot trừ Xu mà không ra video")
    angry = cskh.classify_cskh_message("lừa đảo à")
    joined = cskh._fold(charged["reply"] + " " + angry["reply"])

    assert charged["intent_id"] == "complaint_charged_no_result"
    assert "mã xử lý" in charged["reply"]
    assert angry["intent_id"] == "angry_customer"
    assert "xin lỗi" in angry["reply"]
    assert "mã xử lý" in angry["reply"]
    assert "da hoan xu" not in joined
    assert "da cong xu" not in joined
    assert charged["handoff_required"] is True
    assert angry["ticket_required"] is True


def test_prompt_and_uploaded_clip_question_get_concrete_human_reply():
    prompt = cskh.classify_cskh_message("tạo prompt video nước hoa nam")
    clip = cskh.classify_cskh_message("chị gửi clip này làm gì được")

    assert prompt["intent_id"] == "prompt_create_request"
    assert "nước hoa nam" in prompt["reply"]
    assert "9:16" in prompt["reply"]
    assert "provider" not in cskh._fold(prompt["reply"])
    assert clip["intent_id"] == "content_asset_suggestion"
    for marker in ["phụ đề", "dịch phụ đề", "lồng tiếng", "dựng video"]:
        assert marker in clip["reply"]


def test_aichat_and_cskh_use_same_context_file_and_trace_version(tmp_path, monkeypatch):
    _isolated_env(tmp_path, monkeypatch)
    user_id = "aichat3-user"
    state = _enabled_state(user_id)

    state, ai_result = aichat.process_message(state, user_id, "tạo ảnh bao nhiêu", queue_unknown=False)
    cskh_result = cskh.classify_cskh_message("tạo ảnh bao nhiêu")
    trace = aichat.status_payload(state, user_id)["last_trace"]

    assert ai_result["context_file_path"] == cskh_result["context_file_path"]
    assert ai_result["source_file_version"] == "P0.CSKH.AICHAT.3.2026-07-08"
    assert cskh_result["source_file_version"] == "P0.CSKH.AICHAT.3.2026-07-08"
    assert trace["source_file_version"] == "P0.CSKH.AICHAT.3.2026-07-08"
    assert trace["context_section_used"] == "pricing_facts"
    assert "context_file" in ai_result["source"]
    assert "context_file" in cskh_result["source"]


def test_unknown_intent_goes_to_learning_queue_without_auto_promote(tmp_path, monkeypatch):
    _isolated_env(tmp_path, monkeypatch)
    user_id = "aichat3-user"
    state = _enabled_state(user_id)

    state, result = aichat.process_message(state, user_id, "toi muon blorb zorx qqq")
    shared_state = cskh.load_state()
    candidates = cskh.list_learning_candidates(shared_state, limit=5)

    assert result["intent_id"] == "out_of_scope"
    assert result["learning_queue"] is True
    assert result["learning_candidate_id"]
    assert candidates
    assert candidates[0]["status"] == "open"
    assert "intents" not in shared_state


def test_no_real_provider_calls_or_wallet_payment_runtime_scope():
    changed = _changed_files()
    forbidden_prefixes = ("providers/",)
    forbidden_terms = (
        "music",
        "suno",
        "voice_provider",
        "product_video_provider",
        "payos",
        "wallet",
        "payment",
    )

    assert not any(path.startswith(forbidden_prefixes) for path in changed)
    assert not any(any(term in path.lower() for term in forbidden_terms) and not path.startswith("tests/") for path in changed)
