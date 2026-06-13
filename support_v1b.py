"""Pure helpers for TOAN AAS Operations V1B support tickets."""

from __future__ import annotations

from datetime import datetime, timedelta
import re
import unicodedata


SUPPORT_CATEGORIES = {
    "payment_topup": "💳 Nạp Xu/Thanh toán",
    "image_error": "🖼 Lỗi ảnh",
    "video_error": "🎬 Lỗi video",
    "document_pdf": "📄 Tài liệu/PDF",
    "package_combo": "🎁 Gói/Combo",
    "refund": "💰 Hoàn Xu/Refund",
    "feature_request": "💡 Góp ý tính năng",
    "lead_consulting": "🧑‍💼 Tư vấn dịch vụ",
    "general_support": "🎫 Hỗ trợ chung",
    "service_consulting": "📦 Tư vấn gói dịch vụ",
    "premium_lead": "⭐ Đăng ký Premium",
    "custom_bot_lead": "🤖 Kết nối bot riêng",
    "other": "✍️ Nội dung khác",
}

SUPPORT_STATUSES = (
    "new",
    "reviewing",
    "waiting_user",
    "waiting_provider",
    "refund_pending",
    "resolved",
    "closed",
)

SUPPORT_PRIORITIES = ("low", "normal", "high", "urgent")

STATUS_LABELS = {
    "new": "Mới",
    "reviewing": "Đang kiểm tra",
    "waiting_user": "Chờ khách bổ sung",
    "waiting_provider": "Chờ provider",
    "refund_pending": "Chờ kiểm tra hoàn Xu",
    "resolved": "Đã xử lý",
    "closed": "Đã đóng",
}

PRIORITY_LABELS = {
    "low": "Thấp",
    "normal": "Bình thường",
    "high": "Cao",
    "urgent": "Khẩn cấp",
}

AAS_SUPPORT_SYSTEM_PERSONA = """
Bạn là trợ lý CSKH của TOAN AAS - hệ thống AI Automation hỗ trợ tạo ảnh,
video, tài liệu, giọng nói, nội dung và các quy trình tự động hóa.

Trả lời chuyên nghiệp, ấm áp, rõ ràng và ngắn gọn. Mặc định xưng "mình"
hoặc "TOAN AAS", gọi khách là "bạn"; nếu khách xưng anh/chị thì đáp lại phù
hợp. Không nói như robot, không đổ lỗi cho khách và không hứa khi chưa chắc.
Chỉ hỏi 1-3 thông tin quan trọng. Không bịa giá, chính sách hay thông số.
Không khẳng định đã hoàn Xu khi hệ thống chưa ghi nhận. Với thanh toán,
refund, khách nóng, hợp đồng lớn, bảo mật hoặc kỹ thuật sâu, tạo ticket và
báo admin. Nếu lỗi thuộc hệ thống/provider, chỉ nói TOAN AAS sẽ kiểm tra và
xử lý theo chính sách không trừ/hoàn Xu sau khi đối soát.
""".strip()


def _reply_template(
    template_id: str,
    category: str,
    trigger_intent: str,
    safe_reply: str,
    *,
    needs_admin: bool = False,
    priority: str = "normal",
    allowed_auto_send: bool = True,
) -> dict:
    return {
        "id": template_id,
        "category": category,
        "trigger_intent": trigger_intent,
        "safe_reply": safe_reply,
        "needs_admin": bool(needs_admin),
        "priority": priority,
        "allowed_auto_send": bool(allowed_auto_send),
    }


SUPPORT_REPLY_TEMPLATES = {
    "onboarding": [
        _reply_template(
            "onboarding_overview",
            "onboarding",
            "bot này làm được gì / TOAN AAS là gì",
            "Dạ chào bạn, mình là trợ lý TOAN AAS nhé.\n\n"
            "Mình có thể hỗ trợ tạo ảnh AI, video AI, xử lý tài liệu/PDF, "
            "voice/TTS, prompt và kịch bản nội dung.\n\n"
            "Bạn muốn làm nội dung, tạo ảnh/video hay xử lý tài liệu trước ạ?",
            priority="low",
        ),
        _reply_template(
            "onboarding_video_affiliate",
            "onboarding",
            "video TikTok / affiliate",
            "Dạ được nhé. TOAN AAS có thể hỗ trợ từ ý tưởng, kịch bản, prompt "
            "ảnh/video đến ghép video hoàn chỉnh.\n\n"
            "Bạn gửi chủ đề hoặc sản phẩm muốn làm TikTok/affiliate nhé. "
            "Mình sẽ gợi ý 3 hướng nội dung để bạn chọn.",
            priority="low",
        ),
    ],
    "pricing": [
        _reply_template(
            "pricing_overview",
            "pricing",
            "hỏi giá / bảng giá",
            "Dạ mình gửi bạn bảng giá trong bot nhé.\n\n"
            "TOAN AAS chia theo ảnh, video, tài liệu, voice/TTS và gói/combo. "
            "Các bước lên prompt hoặc kế hoạch thường miễn phí; trước tác vụ "
            "có tính Xu, bot sẽ hiển thị phí và hỏi xác nhận.\n\n"
            "Bạn muốn xem giá ảnh, video hay gói/combo trước ạ?",
            priority="low",
        ),
        _reply_template(
            "pricing_objection",
            "pricing",
            "khách chê giá cao",
            "Dạ mình hiểu băn khoăn của bạn về chi phí.\n\n"
            "Giá được tính theo provider, tài nguyên xử lý và chính sách xử lý "
            "khi lỗi hệ thống. Bạn cho mình biết ngân sách dự kiến nhé, mình sẽ "
            "gợi ý lựa chọn tiết kiệm hơn.",
            priority="normal",
        ),
    ],
    "payment": [
        _reply_template(
            "payment_how_to_topup",
            "payment",
            "hỏi cách nạp tiền / nạp Xu",
            "💳 Cách nạp Xu TOAN AAS:\n\n"
            "1. Bấm 💰 Nạp Xu ở menu chính hoặc gửi /naptien.\n"
            "2. Chọn mệnh giá 10k, 20k, 50k, 100k, 200k hoặc 500k.\n"
            "3. Với PayOS, Xu được cộng khi giao dịch hợp lệ được xác nhận. "
            "Với nạp thủ công, bạn gửi bill/mã giao dịch để admin đối soát rồi mới cộng Xu.\n\n"
            "Nếu bạn đã thanh toán nhưng chưa nhận Xu, hãy gửi ảnh giao dịch, số tiền "
            "và thời gian chuyển khoản để TOAN AAS kiểm tra.",
            priority="low",
        ),
        _reply_template(
            "payment_insufficient_xu",
            "payment",
            "hết Xu / cần nạp",
            "Dạ tài khoản hiện chưa đủ Xu để tiếp tục tác vụ này.\n\n"
            "Bạn có thể mở Nạp Xu trong bot và thanh toán bằng QR PayOS. "
            "Hệ thống chỉ tự cộng Xu khi giao dịch hợp lệ được ghi nhận.",
            priority="low",
        ),
        _reply_template(
            "payment_missing_xu",
            "payment",
            "đã thanh toán nhưng chưa thấy Xu",
            "Dạ mình nhận được rồi nhé. Bạn gửi giúp mình 1-3 thông tin sau:\n"
            "1. Ảnh giao dịch\n2. Số tiền đã nạp\n3. Thời gian chuyển khoản gần đúng\n\n"
            "Mình sẽ tạo ticket để admin đối soát. TOAN AAS chưa thể xác nhận "
            "cộng Xu khi giao dịch chưa được kiểm tra.",
            needs_admin=True,
            priority="high",
        ),
    ],
    "technical_error": [
        _reply_template(
            "technical_image_error",
            "technical_error",
            "ảnh lỗi / kết quả ảnh chưa đúng",
            "Dạ mình xin lỗi vì ảnh chưa cho kết quả như mong muốn nhé.\n\n"
            "Bạn gửi mã job, ảnh kết quả hoặc mô tả phần chưa đúng. TOAN AAS "
            "sẽ kiểm tra tác vụ; ticket chưa tự động hoàn hay trừ thêm Xu.",
            needs_admin=True,
            priority="normal",
        ),
        _reply_template(
            "technical_video_error",
            "technical_error",
            "video không render / provider lỗi",
            "Dạ mình xin lỗi vì tác vụ chưa cho kết quả như mong muốn nhé.\n\n"
            "Bạn gửi mã job hoặc ảnh lỗi nếu có. TOAN AAS sẽ kiểm tra "
            "worker/provider; nếu đúng lỗi hệ thống hoặc nhà cung cấp thì sẽ "
            "xử lý theo chính sách không trừ hoặc hoàn Xu sau khi đối soát.",
            needs_admin=True,
            priority="high",
        ),
        _reply_template(
            "technical_deep_question",
            "technical_error",
            "API / webhook / provider / bảo mật",
            "Dạ câu hỏi này khá chuyên sâu, mình không muốn trả lời qua loa rồi "
            "làm bạn hiểu sai.\n\nBạn gửi thêm bối cảnh sử dụng hoặc mục tiêu cần "
            "đạt được nhé. Mình sẽ chuyển admin/kỹ thuật kiểm tra chính xác hơn.",
            needs_admin=True,
            priority="high",
            allowed_auto_send=True,
        ),
    ],
    "refund_complaint": [
        _reply_template(
            "refund_review",
            "refund_complaint",
            "hoàn Xu / mất Xu / bị trừ Xu",
            "Dạ mình đã ghi nhận yêu cầu kiểm tra Xu của bạn.\n\n"
            "Bạn gửi mã job hoặc ảnh lỗi giúp mình nhé. Ticket này chưa tự động "
            "cộng hay hoàn Xu; admin sẽ đối chiếu kết quả và lịch sử trước khi "
            "xử lý theo chính sách.",
            needs_admin=True,
            priority="high",
        ),
        _reply_template(
            "angry_customer",
            "refund_complaint",
            "khách nóng giận / khiếu nại",
            "Dạ mình xin lỗi bạn vì trải nghiệm này chưa tốt.\n\n"
            "Mình sẽ ghi nhận thành ticket ưu tiên để admin kiểm tra. Nếu hệ "
            "thống ghi nhận Xu bị trừ nhưng không có kết quả hợp lệ, TOAN AAS "
            "sẽ xử lý theo chính sách sau khi đối soát.\n\n"
            "Bạn gửi mã job hoặc ảnh lỗi giúp mình nhé.",
            needs_admin=True,
            priority="urgent",
        ),
    ],
    "feature_question": [
        _reply_template(
            "feature_video_affiliate",
            "feature_question",
            "hỏi tính năng ảnh/video/nội dung",
            "Dạ TOAN AAS có thể hỗ trợ phần này nhé. Bạn mô tả mục tiêu và đầu "
            "ra mong muốn, mình sẽ chỉ đúng công cụ hoặc quy trình phù hợp.",
            priority="low",
        ),
    ],
    "admin_escalation": [
        _reply_template(
            "b2b_contract",
            "admin_escalation",
            "hợp đồng lớn / B2B",
            "Dạ với nhu cầu dự án hoặc hợp đồng lớn, mình sẽ chuyển admin TOAN "
            "AAS trao đổi trực tiếp để tư vấn đúng hơn.\n\n"
            "Bạn gửi giúp mình:\n1. Nhu cầu chính\n2. Quy mô dự án\n"
            "3. Cách liên hệ thuận tiện\n\nMình sẽ lưu lại trong ticket nhé.",
            needs_admin=True,
            priority="high",
        ),
    ],
    "out_of_scope": [
        _reply_template(
            "out_of_scope_illegal",
            "out_of_scope",
            "hack / lừa đảo / giả mạo / xâm phạm riêng tư",
            "Dạ phần này nằm ngoài phạm vi hỗ trợ của TOAN AAS và mình không thể "
            "hỗ trợ hành vi hack tài khoản, lừa đảo, giả mạo giấy tờ hoặc xâm "
            "phạm quyền riêng tư.\n\nTOAN AAS tập trung vào AI automation, ảnh, "
            "video, nội dung, tài liệu và voice/TTS.",
            priority="normal",
        ),
    ],
    "closing": [
        _reply_template(
            "closing_default",
            "closing",
            "kết thúc / cảm ơn",
            "Dạ mình ghi nhận rồi nhé.\n\nNếu bạn cần làm tiếp ảnh, video, tài "
            "liệu hoặc kiểm tra giao dịch, cứ nhắn lại trong bot.",
            priority="low",
        ),
    ],
}

# Backward-compatible name used by bot.py and older tests.
REPLY_TEMPLATES = SUPPORT_REPLY_TEMPLATES

LEGACY_CATEGORY_TO_SCENARIO = {
    "payment_topup": "payment",
    "image_error": "technical_error",
    "video_error": "technical_error",
    "document_pdf": "technical_error",
    "package_combo": "feature_question",
    "refund": "refund_complaint",
    "feature_request": "feature_question",
    "lead_consulting": "admin_escalation",
    "general_support": "feature_question",
    "service_consulting": "admin_escalation",
    "premium_lead": "admin_escalation",
    "custom_bot_lead": "admin_escalation",
    "other": "feature_question",
}

TICKET_CATEGORY_BY_SCENARIO = {
    "payment": "payment_topup",
    "refund_complaint": "refund",
    "admin_escalation": "lead_consulting",
    "technical_error": "other",
}

PRIORITY_ORDER = {"low": 0, "normal": 1, "high": 2, "urgent": 3}


def _normalize_support_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or "").lower())
    plain = "".join(char for char in normalized if not unicodedata.combining(char))
    plain = plain.replace("đ", "d")
    return re.sub(r"\s+", " ", plain).strip()


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def get_support_reply_template(template_id: str = "", category: str = "", variant: int = 0) -> dict:
    if template_id:
        for templates in SUPPORT_REPLY_TEMPLATES.values():
            for template in templates:
                if template["id"] == template_id:
                    return dict(template)
    scenario = category if category in SUPPORT_REPLY_TEMPLATES else LEGACY_CATEGORY_TO_SCENARIO.get(category, "feature_question")
    templates = SUPPORT_REPLY_TEMPLATES.get(scenario) or SUPPORT_REPLY_TEMPLATES["feature_question"]
    return dict(templates[max(0, int(variant or 0)) % len(templates)])


def classify_support_escalation(user_message: str, context: dict | None = None, ai_classification: dict | None = None) -> dict:
    text = _normalize_support_text(user_message)
    result = {
        "matched": False,
        "needs_admin": False,
        "priority": "normal",
        "reason": "general_support",
        "category": "feature_question",
        "ticket_category": "other",
        "suggested_reply_id": "feature_video_affiliate",
        "should_create_ticket": False,
        "should_alert_admin": False,
        "allowed_auto_send": True,
        "classifier_source": "rule_fallback",
    }

    illegal = ("hack nick", "hack tai khoan", "cach lua dao", "gia mao giay to", "xam pham quyen rieng tu")
    angry = (
        "lua dao", "buc minh", "lam an kieu gi", "dang phot", "bao cong an",
        "qua te", "doi tien", "chui", "tru xu ma khong ra video",
    )
    refund = ("hoan tien", "hoan xu", "bi tru xu", "da tru xu", "mat xu", "tru xu ma", "khong ra ket qua")
    payment_help = (
        "lam sao nap", "lam sao de nap", "cach nap", "cach de nap", "huong dan nap", "nap xu nhu the nao",
        "nap tien nhu the nao", "muon nap xu", "muon nap tien",
    )
    payment = ("nap tien chua", "nap xu chua", "chuyen khoan roi", "payos loi", "qr het han", "cong thieu xu", "chua thay xu")
    b2b = ("hop dong", "bao gia doanh nghiep", "du an", "trien khai cho cong ty", "so luong lon", "doi tac", "chiet khau", "hoa hong", "agency", "shop lon")
    custom_bot = ("lam bot rieng", "bot rieng", "bot cho shop", "bot ban hang", "bot cskh", "bot noi bo", "ket noi bot", "tu dong hoa cho shop")
    premium = ("dang ky premium", "goi premium", "premium cho shop", "premium doanh nghiep", "goi cao cap")
    service_consulting = ("tu van goi", "tu van dich vu", "goi video", "goi tao anh", "goi voice", "goi tai lieu")
    admin_contact = ("gap admin", "gap nguoi that", "noi chuyen voi quan ly", "lien he admin")
    technical = (" api", "api ", "webhook", "provider", "server", "vps", "bao mat", "du lieu", "tich hop he thong", "deepgram", "khong render", "render loi", "loi video", "loi anh", "loi tai lieu", "bot dung im", "khong chay")
    pricing = ("bang gia", "gia bao nhieu", "hoi gia", "dat qua", "chi phi cao", "gia cao")
    onboarding = ("bot nay lam duoc gi", "toan aas la gi", "huong dan bat dau")
    affiliate = ("video tiktok", "lam tiktok", "affiliate")
    feature = ("co tao anh", "co tao video", "co lam video", "co xu ly pdf", "tinh nang")
    closing = ("cam on bot", "cam on nhe", "ok cam on", "xong roi")

    if _contains_any(text, illegal):
        result.update(matched=True, reason="unsafe_or_illegal_request", category="out_of_scope", suggested_reply_id="out_of_scope_illegal")
    elif _contains_any(text, angry):
        result.update(
            matched=True, needs_admin=True, priority="urgent", reason="angry_or_legal_complaint",
            category="refund_complaint", ticket_category="refund", suggested_reply_id="angry_customer",
            should_create_ticket=True, should_alert_admin=True,
        )
    elif _contains_any(text, refund):
        result.update(
            matched=True, needs_admin=True, priority="high", reason="refund_or_xu_loss",
            category="refund_complaint", ticket_category="refund", suggested_reply_id="refund_review",
            should_create_ticket=True, should_alert_admin=True,
        )
    elif _contains_any(text, payment_help):
        result.update(
            matched=True, priority="low", reason="payment_how_to_topup",
            category="payment", ticket_category="payment_topup",
            suggested_reply_id="payment_how_to_topup",
        )
    elif _contains_any(text, payment):
        result.update(
            matched=True, needs_admin=True, priority="high", reason="payment_reconciliation",
            category="payment", ticket_category="payment_topup", suggested_reply_id="payment_missing_xu",
            should_create_ticket=True, should_alert_admin=True,
        )
    elif _contains_any(text, custom_bot):
        result.update(
            matched=True, needs_admin=True, priority="high", reason="custom_bot_lead",
            category="admin_escalation", ticket_category="custom_bot_lead", suggested_reply_id="b2b_contract",
            should_create_ticket=True, should_alert_admin=True,
        )
    elif _contains_any(text, premium):
        result.update(
            matched=True, needs_admin=True, priority="high", reason="premium_lead",
            category="admin_escalation", ticket_category="premium_lead", suggested_reply_id="b2b_contract",
            should_create_ticket=True, should_alert_admin=True,
        )
    elif _contains_any(text, service_consulting):
        result.update(
            matched=True, needs_admin=True, priority="normal", reason="service_consulting",
            category="admin_escalation", ticket_category="service_consulting", suggested_reply_id="b2b_contract",
            should_create_ticket=True, should_alert_admin=False,
        )
    elif _contains_any(text, admin_contact):
        result.update(
            matched=True, needs_admin=True, priority="high", reason="admin_contact",
            category="admin_escalation", ticket_category="general_support", suggested_reply_id="b2b_contract",
            should_create_ticket=True, should_alert_admin=True,
        )
    elif _contains_any(text, b2b):
        result.update(
            matched=True, needs_admin=True, priority="high", reason="b2b_or_large_project",
            category="admin_escalation", ticket_category="lead_consulting", suggested_reply_id="b2b_contract",
            should_create_ticket=True, should_alert_admin=True,
        )
    elif _contains_any(f" {text} ", technical):
        if "video" in text or "render" in text:
            ticket_category = "video_error"
        elif "anh" in text:
            ticket_category = "image_error"
        elif "tai lieu" in text:
            ticket_category = "document_pdf"
        else:
            ticket_category = "other"
        result.update(
            matched=True, needs_admin=True, priority="high", reason="deep_technical_question",
            category="technical_error", ticket_category=ticket_category, suggested_reply_id="technical_deep_question",
            should_create_ticket=True, should_alert_admin=True,
        )
    elif _contains_any(text, pricing):
        template_id = "pricing_objection" if _contains_any(text, ("dat qua", "chi phi cao", "gia cao")) else "pricing_overview"
        result.update(matched=True, priority="low", reason="pricing_question", category="pricing", suggested_reply_id=template_id)
    elif _contains_any(text, onboarding):
        result.update(matched=True, priority="low", reason="onboarding", category="onboarding", suggested_reply_id="onboarding_overview")
    elif _contains_any(text, affiliate):
        result.update(matched=True, priority="low", reason="video_affiliate_question", category="onboarding", suggested_reply_id="onboarding_video_affiliate")
    elif _contains_any(text, feature):
        result.update(matched=True, priority="low", reason="feature_question", category="feature_question", suggested_reply_id="feature_video_affiliate")
    elif _contains_any(text, closing):
        result.update(matched=True, priority="low", reason="conversation_closing", category="closing", suggested_reply_id="closing_default")
    elif isinstance(ai_classification, dict) and ai_classification.get("matched"):
        ai_category = str(ai_classification.get("category") or "feature_question")
        if ai_category not in SUPPORT_REPLY_TEMPLATES:
            ai_category = "feature_question"
        template = get_support_reply_template(category=ai_category)
        ai_priority = str(ai_classification.get("priority") or template["priority"])
        if ai_priority not in PRIORITY_ORDER:
            ai_priority = template["priority"]
        needs_admin = bool(ai_classification.get("needs_admin") or template["needs_admin"])
        result.update(
            matched=True,
            needs_admin=needs_admin,
            priority=ai_priority,
            reason=str(ai_classification.get("reason") or "optional_ai_classifier")[:160],
            category=ai_category,
            ticket_category=TICKET_CATEGORY_BY_SCENARIO.get(ai_category, "other"),
            suggested_reply_id=template["id"],
            should_create_ticket=needs_admin,
            should_alert_admin=needs_admin,
            allowed_auto_send=bool(template["allowed_auto_send"]),
            classifier_source="optional_ai",
        )

    template = get_support_reply_template(result["suggested_reply_id"])
    result["allowed_auto_send"] = bool(template["allowed_auto_send"])
    ticket_category = str(result.get("ticket_category") or "other")
    if ticket_category == "payment_topup":
        support_category = "payment"
    elif ticket_category == "refund":
        support_category = "refund"
    elif ticket_category in {"premium_lead", "custom_bot_lead", "service_consulting"}:
        support_category = ticket_category
    elif result.get("reason") == "admin_contact":
        support_category = "admin_contact"
    elif result.get("category") == "technical_error":
        support_category = "technical_error"
    else:
        support_category = "general_support"
    result["support_category"] = support_category
    return result


def format_support_reply(raw_reply: str, context: dict | None = None) -> str:
    text = str(raw_reply or "").strip()
    if not text:
        text = get_support_reply_template(category="feature_question")["safe_reply"]
    replacements = {
        "Kính gửi quý khách": "Dạ chào bạn",
        "kính gửi quý khách": "dạ chào bạn",
        "Hệ thống chúng tôi ghi nhận yêu cầu của quý khách": "TOAN AAS đã nhận yêu cầu của bạn",
        "Chúng tôi rất lấy làm tiếc": "Mình xin lỗi vì trải nghiệm này chưa tốt",
        "Đã hoàn Xu": "TOAN AAS sẽ kiểm tra điều kiện hoàn Xu",
        "đã hoàn Xu": "TOAN AAS sẽ kiểm tra điều kiện hoàn Xu",
        "Chắc chắn 100%": "TOAN AAS sẽ kiểm tra kỹ",
        "chắc chắn 100%": "TOAN AAS sẽ kiểm tra kỹ",
        "Cam kết không lỗi": "TOAN AAS sẽ cố gắng xử lý ổn định",
        "cam kết không lỗi": "TOAN AAS sẽ cố gắng xử lý ổn định",
        "ngay lập tức": "sớm nhất có thể",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:2400].strip()


def support_reply_for_classification(classification: dict) -> str:
    template = get_support_reply_template(str((classification or {}).get("suggested_reply_id") or ""))
    return format_support_reply(template["safe_reply"], classification)


def ticket_priority(category: str, message: str = "") -> str:
    category = str(category or "").strip().lower()
    classification = classify_support_escalation(message)
    detected_priority = classification.get("priority") if classification.get("matched") else ""
    if category in {"payment_topup", "refund"}:
        base_priority = "high"
    elif category == "video_error" and classification.get("reason") == "refund_or_xu_loss":
        base_priority = "high"
    elif category in {"premium_lead", "custom_bot_lead"}:
        base_priority = "high"
    elif category == "service_consulting":
        base_priority = "normal"
    elif category == "feature_request":
        base_priority = "low"
    else:
        base_priority = "normal"
    if detected_priority and PRIORITY_ORDER.get(str(detected_priority), 1) > PRIORITY_ORDER.get(base_priority, 1):
        return str(detected_priority)
    return base_priority


def category_label(category: str) -> str:
    return SUPPORT_CATEGORIES.get(str(category or ""), SUPPORT_CATEGORIES["other"])


def status_label(status: str) -> str:
    return STATUS_LABELS.get(str(status or ""), str(status or "new"))


def priority_label(priority: str) -> str:
    return PRIORITY_LABELS.get(str(priority or ""), str(priority or "normal"))


def suggested_reply(category: str, variant: int = 0, message: str = "") -> str:
    classification = classify_support_escalation(message) if message else {}
    if classification.get("matched"):
        template = get_support_reply_template(classification.get("suggested_reply_id"))
    else:
        template = get_support_reply_template(category=str(category or ""), variant=variant)
    return format_support_reply(template["safe_reply"], classification)


def parse_ticket_time(value: str) -> datetime | None:
    raw = str(value or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(raw[:19], fmt)
        except ValueError:
            continue
    return None


def overdue_reason(status: str, created_at: str, now: datetime | None = None) -> str:
    created = parse_ticket_time(created_at)
    if not created:
        return ""
    current = now or datetime.now()
    status = str(status or "")
    threshold = timedelta(hours=72 if status == "waiting_provider" else 24)
    if status not in {"new", "reviewing", "refund_pending", "waiting_provider"}:
        return ""
    if current - created <= threshold:
        return ""
    if status == "waiting_provider":
        return "Chờ provider quá 72 giờ"
    if status == "refund_pending":
        return "Refund pending quá 24 giờ"
    return "Chưa xử lý quá 24 giờ"
