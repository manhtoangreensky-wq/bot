"""Pure helpers for TOAN AAS Operations V1B support tickets."""

from __future__ import annotations

from datetime import datetime, timedelta


SUPPORT_CATEGORIES = {
    "payment_topup": "💳 Nạp Xu/Thanh toán",
    "image_error": "🖼 Lỗi ảnh",
    "video_error": "🎬 Lỗi video",
    "document_pdf": "📄 Tài liệu/PDF",
    "package_combo": "🎁 Gói/Combo",
    "refund": "💰 Hoàn Xu/Refund",
    "feature_request": "💡 Góp ý tính năng",
    "lead_consulting": "🧑‍💼 Tư vấn dịch vụ",
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

REPLY_TEMPLATES = {
    "video_error": (
        "Xin chào bạn, TOAN AAS đã nhận thông tin lỗi video. Admin sẽ kiểm tra job và provider. Nếu lỗi thuộc hệ thống, Xu sẽ được xử lý theo chính sách hiện hành.",
        "TOAN AAS đang rà soát tác vụ video của bạn. Vui lòng gửi thêm mã job hoặc ảnh chụp màn hình nếu có để admin kiểm tra nhanh hơn.",
    ),
    "image_error": (
        "Xin chào bạn, TOAN AAS đã nhận thông tin lỗi ảnh. Admin sẽ kiểm tra prompt, job và trạng thái provider trước khi phản hồi kết quả.",
        "TOAN AAS đang rà soát tác vụ ảnh. Bạn vui lòng gửi thêm mã job hoặc ảnh kết quả nếu có để admin đối chiếu.",
    ),
    "payment_topup": (
        "TOAN AAS đã nhận yêu cầu kiểm tra nạp Xu/thanh toán. Admin sẽ đối soát giao dịch; vui lòng bổ sung mã đơn và ảnh giao dịch nếu có.",
        "Admin đang kiểm tra giao dịch của bạn. TOAN AAS chỉ cập nhật Xu sau khi đối soát được khoản thanh toán thực tế.",
    ),
    "refund": (
        "TOAN AAS đã ghi nhận yêu cầu hoàn Xu/refund và đang kiểm tra điều kiện. Ticket này chưa tự động cộng hoặc trừ Xu.",
        "Yêu cầu hoàn Xu đang được admin đối chiếu với job và lịch sử giao dịch. TOAN AAS sẽ phản hồi sau khi kiểm tra xong.",
    ),
    "document_pdf": (
        "TOAN AAS đã nhận thông tin lỗi tài liệu/PDF. Vui lòng gửi file hoặc ảnh lỗi nếu có để admin kiểm tra đúng công cụ.",
    ),
    "package_combo": (
        "TOAN AAS đã nhận yêu cầu về gói/combo và sẽ kiểm tra quyền lợi trong Gói của tôi. Ticket này không tự thay đổi số lượt hoặc Xu.",
    ),
    "feature_request": (
        "Cảm ơn bạn đã góp ý. TOAN AAS đã ghi nhận đề xuất để admin đánh giá cho kế hoạch sản phẩm tiếp theo.",
    ),
    "lead_consulting": (
        "Cảm ơn bạn đã quan tâm đến dịch vụ TOAN AAS. Admin sẽ xem nhu cầu và tư vấn phương án phù hợp sớm nhất có thể.",
        "TOAN AAS đã nhận nhu cầu tư vấn. Bạn có thể bổ sung mục tiêu, ngân sách dự kiến và thời gian cần triển khai để admin chuẩn bị phương án phù hợp.",
    ),
    "other": (
        "TOAN AAS đã nhận yêu cầu hỗ trợ của bạn. Admin sẽ kiểm tra nội dung và phản hồi sớm nhất có thể.",
    ),
}


def ticket_priority(category: str, message: str = "") -> str:
    category = str(category or "").strip().lower()
    text = str(message or "").lower()
    if category in {"payment_topup", "refund"}:
        return "high"
    if category == "video_error" and any(marker in text for marker in ("mất xu", "trừ xu", "mat xu", "tru xu")):
        return "high"
    if category == "feature_request":
        return "low"
    return "normal"


def category_label(category: str) -> str:
    return SUPPORT_CATEGORIES.get(str(category or ""), SUPPORT_CATEGORIES["other"])


def status_label(status: str) -> str:
    return STATUS_LABELS.get(str(status or ""), str(status or "new"))


def priority_label(priority: str) -> str:
    return PRIORITY_LABELS.get(str(priority or ""), str(priority or "normal"))


def suggested_reply(category: str, variant: int = 0) -> str:
    values = REPLY_TEMPLATES.get(str(category or ""), REPLY_TEMPLATES["other"])
    return values[max(0, int(variant or 0)) % len(values)]


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
