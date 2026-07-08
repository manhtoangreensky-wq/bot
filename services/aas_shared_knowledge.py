from __future__ import annotations

import math
import re
import unicodedata
from pathlib import Path
from typing import Any


VIDEO_TIERS = [
    ("Trải nghiệm", 200),
    ("Cơ bản", 300),
    ("Phổ thông", 400),
    ("Nâng cao", 500),
    ("Bán hàng", 600),
    ("Cao cấp", 800),
    ("Chuyên nghiệp", 1000),
    ("Pro Plus", 1200),
    ("Premium", 1500),
]

IMAGE_TIERS = [
    ("Tiết kiệm", 50),
    ("Chuẩn", 150),
    ("Chuẩn + bảo hành", 200),
    ("Phổ thông", 300),
    ("Phổ thông + bảo hành", 400),
    ("Cao", 500),
    ("Cao + bảo hành", 600),
]

MUSIC_BACKGROUND_TIERS = [100, 150, 200]
MUSIC_SONG_TIERS = [200, 250, 300]
XU_TO_VND = 100
CONTEXT_FILE_VERSION_FALLBACK = "P0.CSKH.AICHAT.3.2026-07-08"
CONTEXT_FILE_RELATIVE_PATH = "knowledge/toan_aas_cskh_aichat_context.md"

VAGUE_REPLY = (
    "Dạ em đây ạ. Anh/chị muốn hỏi về giá, tạo video, tạo ảnh, phụ đề/lồng tiếng "
    "hay nạp Xu để em hỗ trợ đúng hơn nha?"
)
MEANINGLESS_REPLY = (
    "Dạ em chưa hiểu chính xác ý anh/chị ạ. Mình nhắn giúp em rõ hơn một chút, "
    "ví dụ: muốn xem giá, tạo video, tạo ảnh, dịch/lồng tiếng hay kiểm tra Xu ạ?"
)
FILE_WITHOUT_INSTRUCTION_REPLY = (
    "Dạ em nhận được file rồi ạ. Anh/chị muốn em hỗ trợ tạo phụ đề, dịch/lồng tiếng, "
    "dùng làm tư liệu tạo video hay kiểm tra file này ạ?"
)
PRICE_UNKNOWN_SAFE_REPLY = (
    "Dạ phần này em cần kiểm tra theo hóa đơn trong bot để nói chính xác, vì giá cuối còn tùy gói/số lượng/nội dung. "
    "Anh/chị chọn tới màn hóa đơn, hệ thống sẽ hiện tổng Xu trước khi xác nhận ạ."
)
COMPLAINT_REPLY = (
    "Dạ em xin lỗi anh/chị vì trải nghiệm này chưa tốt ạ. Anh/chị gửi giúp em mã xử lý hoặc ID Telegram, "
    "em kiểm tra trạng thái và phần Xu cho mình ngay nha."
)
CHARGED_NO_RESULT_REPLY = (
    "Dạ nếu hệ thống đã trừ Xu nhưng không có kết quả hợp lệ, bên em sẽ kiểm tra và xử lý theo chính sách hoàn/no-charge. "
    "Anh/chị gửi giúp em mã xử lý để em kiểm tra chính xác ạ."
)
LAST_REPLY_TEMPLATE = "Anh/chị gửi thêm giúp em [thông tin cần thiết], em sẽ hỗ trợ tiếp cho mình nha."
ACTIONABLE_MEDIA_TYPES = {"photo", "image", "video", "document", "audio", "voice", "animation"}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def pricing_doc_path() -> Path:
    return repo_root() / "docs" / "public" / "bang-gia-toan-aas.md"


def guide_doc_path() -> Path:
    return repo_root() / "docs" / "public" / "huong-dan-su-dung-toan-aas.md"


def context_doc_path() -> Path:
    return repo_root() / CONTEXT_FILE_RELATIVE_PATH


def _read_doc(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _parse_context_metadata(raw: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    if not raw.strip().startswith("---"):
        return metadata
    parts = raw.split("---", 2)
    if len(parts) < 3:
        return metadata
    for line in parts[1].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip()
    return metadata


def _parse_markdown_sections(raw: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current = "root"
    for line in raw.splitlines():
        if line.startswith("## "):
            current = fold(line.lstrip("#").strip()).replace(" ", "_")
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)
    return {key: "\n".join(value).strip() for key, value in sections.items() if key}


def load_context_brain() -> dict[str, Any]:
    path = context_doc_path()
    raw = _read_doc(path)
    metadata = _parse_context_metadata(raw)
    version = metadata.get("version") or CONTEXT_FILE_VERSION_FALLBACK
    return {
        "loaded": bool(raw),
        "path": str(path),
        "relative_path": CONTEXT_FILE_RELATIVE_PATH,
        "version": version,
        "updated_at": metadata.get("updated_at") or "",
        "owner": metadata.get("owner") or "TOAN_AAS",
        "applies_to": metadata.get("applies_to") or "ai_chatbot, cskh_business_support",
        "sections": _parse_markdown_sections(raw),
        "raw": raw,
    }


def context_status() -> dict[str, Any]:
    context = load_context_brain()
    return {
        "context_file_loaded": bool(context.get("loaded")),
        "context_file_path": str(context.get("path") or context_doc_path()),
        "context_file_version": str(context.get("version") or CONTEXT_FILE_VERSION_FALLBACK),
        "source_file_version": str(context.get("version") or CONTEXT_FILE_VERSION_FALLBACK),
    }


def load_shared_docs() -> dict[str, str]:
    return {
        "pricing_doc": _read_doc(pricing_doc_path()),
        "guide_doc": _read_doc(guide_doc_path()),
        "context_file": _read_doc(context_doc_path()),
    }


def docs_status() -> dict[str, Any]:
    docs = load_shared_docs()
    context = context_status()
    return {
        "pricing_doc_loaded": bool(docs["pricing_doc"]),
        "guide_doc_loaded": bool(docs["guide_doc"]),
        "context_file_loaded": bool(docs["context_file"]),
        "pricing_doc_path": str(pricing_doc_path()),
        "guide_doc_path": str(guide_doc_path()),
        "context_file_path": context["context_file_path"],
        "context_file_version": context["context_file_version"],
        "source_file_version": context["source_file_version"],
    }


def fold(value: str) -> str:
    text = unicodedata.normalize("NFD", str(value or "").lower())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return " ".join(text.replace("đ", "d").split())


def _format_int(value: float | int) -> str:
    integer = int(round(float(value)))
    return f"{integer:,}".replace(",", ".")


def format_xu(value: float | int) -> str:
    return f"{_format_int(value)} Xu"


def format_vnd(value: float | int) -> str:
    return f"{_format_int(value)}đ"


def _list_prices(values: list[int]) -> str:
    return " / ".join(str(item) for item in values) + " Xu"


def _extract_first_int(text: str) -> int:
    match = re.search(r"(\d{1,7})", str(text or "").replace(".", "").replace(",", ""))
    return int(match.group(1)) if match else 0


def _extract_vnd_amount(text: str) -> int:
    raw = str(text or "")
    folded = fold(raw)
    money_match = re.search(
        r"(\d+(?:[.,]\d+)?)\s*(k|nghin|nghìn|ngan|ngàn|tr|trieu|triệu|vnd|đ|dong|đồng)?",
        raw,
        flags=re.IGNORECASE,
    )
    if not money_match:
        return 0
    number = float(money_match.group(1).replace(",", "."))
    unit = fold(money_match.group(2) or "")
    if unit in {"k", "nghin", "ngan"}:
        return int(number * 1000)
    if unit in {"tr", "trieu"}:
        return int(number * 1_000_000)
    if unit in {"vnd", "d", "dong"}:
        return int(number)
    if "nap" in folded or "chuyen khoan" in folded or "duoc nhieu xu" in folded or "duoc nhieu" in folded:
        if number <= 999:
            return int(number * 1000)
    return 0


def vnd_to_xu(vnd: int) -> int:
    return max(0, int(vnd // XU_TO_VND))


def _char_discount(chars: int) -> float:
    if chars > 10_000:
        return 0.8
    if chars > 1_000:
        return 0.9
    return 1.0


def _charge_for_chars(chars: int, rate: float) -> int:
    return int(math.ceil(chars * rate * _char_discount(chars)))


def calculate_subdub(chars: int, *, private_voice: bool = False) -> dict[str, int | float]:
    safe_chars = max(0, int(chars or 0))
    subtitle = _charge_for_chars(safe_chars, 0.1)
    dub_rate = 0.2 if private_voice else 0.1
    dub = _charge_for_chars(safe_chars, dub_rate)
    return {
        "chars": safe_chars,
        "discount_percent": int(round((1 - _char_discount(safe_chars)) * 100)),
        "subtitle_translate_xu": subtitle,
        "dub_xu": dub,
        "total_xu": subtitle + dub,
        "dub_rate": dub_rate,
    }


def _memory_values(memory: dict | None) -> tuple[str, str, str]:
    data = memory or {}
    return (
        fold(str(data.get("last_intent") or "")),
        fold(str(data.get("last_product") or "")),
        fold(str(data.get("conversation_stage") or "")),
    )


def _in_topup_context(folded: str, memory: dict | None) -> bool:
    last_intent, last_product, last_stage = _memory_values(memory)
    return (
        "xu" in folded
        or "nap" in folded
        or "duoc nhieu" in folded
        or last_product == "payment_xu"
        or last_intent in {"pricing_topup", "pricing_general"}
        or last_stage == "pricing"
    )


def _section_for_intent(intent_id: str) -> str:
    intent = str(intent_id or "")
    if intent.startswith("pricing") or "pricing" in intent or intent in {
        "ask_xu_conversion",
        "image_ai_pricing",
        "product_video_pricing",
        "subdub_pricing",
        "dub_pricing",
        "subtitle_pricing",
        "voice_pricing",
        "music_pricing",
    }:
        return "pricing_facts"
    if intent in {"greeting", "vague_message", "meaningless_message", "file_without_instruction", "out_of_scope_context_fallback"}:
        return "fallback_policy"
    if intent.startswith("complaint") or intent in {"refund_request", "angry_customer", "public_negative_comment", "escalation_manager", "product_video_failed_no_file"}:
        return "scenario_dialogues"
    if intent.startswith("prompt") or intent in {"prompt_video_generation", "prompt_create_request", "image_create_request", "video_create_request", "content_asset_suggestion"}:
        return "usage_guides"
    if intent in {"farewell", "customer_silent_followup"}:
        return "human_last_reply_policy"
    return "intents"


def retrieve_context_sections(text: str, *, intent_id: str = "", media_type: str = "") -> list[str]:
    folded = fold(text)
    sections: list[str] = []
    if media_type:
        sections.extend(["usage_guides", "fallback_policy"])
    if any(term in folded for term in ("gia", "bao nhieu", "xu", "tien", "bang gia", "phi", "100k", "nap")):
        sections.append("pricing_facts")
    if any(term in folded for term in ("cach dung", "huong dan", "lam sao", "dung sao", "flow")):
        sections.append("usage_guides")
    if any(term in folded for term in ("loi", "ket", "khong ra", "chua thay", "lua dao", "hoan xu", "tru xu", "quan ly")):
        sections.extend(["scenario_dialogues", "hard_rules"])
    if any(term in folded for term in ("prompt", "caption", "y tuong", "kich ban")):
        sections.append("usage_guides")
    section = _section_for_intent(intent_id)
    if section:
        sections.append(section)
    return list(dict.fromkeys(section for section in sections if section))


def _is_actionable_media(media_type: str) -> bool:
    return fold(media_type) in ACTIONABLE_MEDIA_TYPES


def _is_noise_message(raw: str, folded: str) -> bool:
    if folded in {"?", "??", "???", "sao", "ua", "u", "ok roi sao", "ok sao", "alo?", "alo"}:
        return True
    if raw and not re.search(r"[0-9A-Za-zÀ-ỹ]", raw):
        return True
    return False


def _is_meaningless_message(raw: str, folded: str) -> bool:
    if folded in {"?", "??", "???", "sao", "ua", "u", "ok roi sao", "ok sao"}:
        return True
    if raw and not re.search(r"[0-9A-Za-zÀ-ỹ]", raw):
        return True
    return False


def _looks_farewell(folded: str) -> bool:
    return any(term in folded for term in ("cam on xong roi", "xong roi", "ok de toi lam", "ok de anh lam", "dung nhan"))


def _looks_silent_followup(folded: str) -> bool:
    return any(term in folded for term in ("de suy nghi", "lat tinh", "de anh xem", "de chi xem"))


def _is_charged_no_result(folded: str) -> bool:
    charged = any(term in folded for term in ("tru xu", "mat xu", "tru tien", "bi tru", "mat tien"))
    no_result = any(term in folded for term in ("khong ra", "chua ra", "khong co ket qua", "khong co file", "chua co file", "khong thay"))
    return charged and no_result


def _is_payment_issue(folded: str) -> bool:
    payment = any(term in folded for term in ("nap", "chuyen khoan", "thanh toan", "momo", "payos", "giao dich"))
    issue = any(term in folded for term in ("chua thay", "khong nhan", "chua nhan", "chua vao", "khong vao", "loi", "bonus"))
    return payment and issue


def _is_subdub_runtime_issue(folded: str) -> bool:
    subdub = any(term in folded for term in ("phu de", "subtitle", "long tieng", "dub", "voice over"))
    issue = any(term in folded for term in ("khong ra", "chua ra", "loi", "sai", "lech", "khong dung", "mat tieng"))
    return subdub and issue


def _is_render_stuck_issue(folded: str) -> bool:
    return "video" in folded and any(term in folded for term in ("bi ket", "ket", "20%", "render lau", "qua lau"))


def _is_video_runtime_error(folded: str) -> bool:
    return "video" in folded and any(term in folded for term in ("bi loi", "loi", "khong chay", "fail", "hong"))


def _is_angry_customer(folded: str) -> bool:
    return any(term in folded for term in ("lua dao", "boc phot", "lam an chan", "bot gi ky", "app lua", "mat tien oan"))


def _is_file_capability_question(folded: str) -> bool:
    return any(term in folded for term in ("gui clip nay", "gui file nay", "clip nay lam gi", "file nay lam gi", "anh nay lam gi", "video nay lam gi"))


def _memory_topic(memory: dict | None) -> str:
    data = memory or {}
    topic = fold(str(data.get("previous_topic") or data.get("last_product_type") or data.get("last_product") or ""))
    intent = fold(str(data.get("previous_intent") or data.get("last_intent") or ""))
    if topic in {"image", "image_ai", "anh", "hinh"} or intent == "image_create_request":
        return "image"
    if topic in {"video", "product_video"} or intent == "video_create_request":
        return "video"
    if "pricing" in intent or topic in {"payment_xu", "xu"}:
        return "pricing"
    return topic


def _memory_subject(memory: dict | None) -> str:
    data = memory or {}
    return str(data.get("last_subject") or data.get("last_requested_asset") or "").strip()


def _has_image_keyword(raw: str, folded: str) -> bool:
    raw_lower = str(raw or "").lower()
    return (
        "ảnh" in raw_lower
        or "hình" in raw_lower
        or any(term in folded for term in ("hinh", "image", "photo", "picture", "avatar", "logo"))
    )


def _has_video_keyword(folded: str) -> bool:
    return any(term in folded for term in ("video", "clip", "reel", "short", "tiktok", "dung video", "lam phim"))


def _has_create_action(folded: str) -> bool:
    return any(term in folded for term in ("tao", "lam", "ve", "dung", "bien", "thiet ke", "viet", "soan"))


def _has_prompt_keyword(folded: str) -> bool:
    return any(term in folded for term in ("prompt", "caption", "hashtag", "y tuong", "kich ban"))


def _is_short_image_followup(raw: str, folded: str, memory: dict | None) -> bool:
    if str(raw or "").strip().lower() == "ảnh":
        return True
    return folded in {"anh", "hinh", "lam anh di", "tao anh di", "tiep", "tiep di", "lam di", "duoc", "ok", "duoc khong"} and _memory_topic(memory) == "image"


def _is_short_video_followup(folded: str, memory: dict | None) -> bool:
    return folded in {"video", "clip", "lam video di", "tao video di", "tiep", "tiep di", "lam di", "duoc", "ok", "duoc khong"} and _memory_topic(memory) == "video"


def _is_short_price_followup(folded: str, memory: dict | None) -> bool:
    return folded in {"gia", "bao gia", "bao nhieu", "nhieu xu", "xu", "phi"} and _memory_topic(memory) in {"image", "video", "pricing"}


def _subject_from_match(raw: str, pattern: str) -> str:
    match = re.search(pattern, str(raw or ""), flags=re.IGNORECASE)
    return match.group(1).strip(" .,!?:;\"'") if match else ""


def _clean_subject(subject: str) -> str:
    clean = re.sub(r"\s+", " ", str(subject or "").strip(" .,!?:;\"'"))
    clean = re.sub(r"^(về|ve|cho|của|cua|theo)\s+", "", clean, flags=re.IGNORECASE).strip()
    clean = re.sub(r"\s+(được không|duoc khong|nhé|nha|đi|di)$", "", clean, flags=re.IGNORECASE).strip()
    if not clean:
        return ""
    clean = re.sub(r"\blexus\b", "Lexus", clean, flags=re.IGNORECASE)
    return clean[:120]


def _extract_image_subject(raw: str) -> str:
    patterns = (
        r"(?:bức\s+ảnh|ảnh|hình)\s+(?:về|ve|cho|của|cua)?\s*(.+)$",
        r"(?:tạo|tao|làm|lam|vẽ|ve|thiết kế|thiet ke)\s+(?:dùm|dum|giúp|giup)?\s*(?:tôi|toi|em|anh|chị|chi)?\s*(?:một|1)?\s*(?:bức\s+)?(?:ảnh|hình)\s*(?:về|ve|cho)?\s*(.+)$",
        r"(?:biến|bien)\s+(.+?)\s+thành\s+(?:ảnh|hình)",
    )
    for pattern in patterns:
        subject = _clean_subject(_subject_from_match(raw, pattern))
        if subject and fold(subject) not in {"duoc khong", "di", "nha", "nhe"}:
            return subject
    return ""


def _extract_video_subject(raw: str, folded: str) -> str:
    if "my pham" in folded:
        return "mỹ phẩm"
    if "nuoc hoa" in folded:
        return "nước hoa"
    subject = _clean_subject(_subject_from_match(raw, r"(?:video|clip)\s+(?:bán hàng|ban hang|quảng cáo|quang cao)?\s*(.+)$"))
    return subject


def _extract_prompt_subject(raw: str) -> str:
    return _clean_subject(
        _subject_from_match(
            raw,
            r"(?:tạo|tao|viết|viet|cho tôi|cho toi)?\s*prompt\s+(?:tạo\s+ảnh|tao anh|ảnh|anh|video)?\s*(.+)$",
        )
    )


def _is_image_create_request(raw: str, folded: str, memory: dict | None) -> bool:
    if _is_short_image_followup(raw, folded, memory):
        return True
    if _has_image_keyword(raw, folded) and _has_create_action(folded):
        return True
    if _has_image_keyword(raw, folded) and any(term in folded for term in ("duoc khong", "duoc ko", "lam duoc khong", "tao duoc khong")):
        return True
    if _memory_topic(memory) == "image" and folded in {"duoc khong", "lam di", "tiep", "ok", "duoc"}:
        return True
    return False


def _is_video_create_request(raw: str, folded: str, memory: dict | None) -> bool:
    if _is_short_video_followup(folded, memory):
        return True
    return _has_video_keyword(folded) and any(term in folded for term in ("tao", "lam", "dung", "quang cao", "ban hang"))


def image_create_reply(raw: str, *, memory: dict | None = None, subject: str = "") -> str:
    remembered = _memory_subject(memory)
    topic = subject or remembered
    if topic:
        if "lexus" in fold(topic):
            prompt = (
                "Ảnh quảng cáo xe Lexus màu đen chạy trên đường phố ban đêm, ánh đèn phản chiếu trên thân xe, "
                "phong cách luxury automotive commercial, cinematic lighting, ultra realistic, sharp details, 9:16."
            )
        else:
            prompt = (
                f"Ảnh quảng cáo {topic}, bố cục rõ chủ thể, ánh sáng đẹp, phong cách thương mại cao cấp, "
                "màu sắc sạch, chi tiết sắc nét, tỉ lệ 9:16, không chữ rối, không phóng đại."
            )
        if not subject and remembered and str(raw or "").strip().lower() in {"ảnh", "anh"}:
            return (
                f"Dạ mình đang muốn tiếp tục tạo ảnh {remembered} đúng không ạ? Em có thể giúp anh/chị theo 2 cách: "
                f"tạo prompt ảnh {remembered} trước, hoặc hướng mình vào luồng Tạo ảnh để tạo ảnh thật trong bot."
            )
        return (
            f"Dạ được ạ. Em soạn sẵn prompt ảnh {topic} cho anh/chị trước nha. Nếu anh/chị muốn tạo ảnh thật trong bot, "
            "mình vào Tạo ảnh, chọn gói và xác nhận hóa đơn rồi hệ thống mới xử lý.\n\n"
            f"Prompt đề xuất:\n<code>{prompt}</code>\n\n"
            "Anh/chị muốn em hướng theo phong cách sang trọng, thể thao hay showroom cao cấp ạ?"
        )
    if _memory_topic(memory) == "image":
        return (
            "Dạ được ạ. Em có thể hỗ trợ anh/chị chuẩn bị prompt ảnh và hướng vào luồng Tạo ảnh. "
            "Phần tạo ảnh thật sẽ có hóa đơn trước khi xử lý, anh/chị xác nhận rồi hệ thống mới trừ Xu nếu ảnh tạo hợp lệ. "
            "Mình muốn tạo ảnh về nội dung gì ạ?"
        )
    return (
        "Dạ anh/chị muốn tạo ảnh mới, xem giá tạo ảnh hay chỉnh ảnh có sẵn ạ? "
        "Nếu muốn tạo ảnh thật, bot sẽ hiện hóa đơn trước khi xử lý; nếu chỉ cần prompt thì em viết miễn phí trước cho mình."
    )


def video_create_reply(raw: str, folded: str) -> str:
    subject = _extract_video_subject(raw, folded) or "sản phẩm"
    return (
        f"Dạ làm video {subject} được ạ. Em có thể giúp anh/chị chuẩn bị kịch bản/prompt video trước, rồi hướng vào luồng Tạo video trong bot. "
        "Khi tạo video thật, hệ thống sẽ hiện hóa đơn trước; anh/chị xác nhận rồi mới xử lý. "
        "Mình gửi thêm sản phẩm cụ thể, tỉ lệ khung hình và muốn video khoảng mấy cảnh để em gợi ý sát hơn nha."
    )


def prompt_create_reply(raw: str, folded: str) -> str:
    if "video" in folded:
        return prompt_video_reply(raw)
    subject = _extract_prompt_subject(raw) or _extract_image_subject(raw) or "sản phẩm"
    return (
        "Dạ được ạ. Đây là prompt miễn phí cho ảnh để mình dùng làm nháp:\n\n"
        f"<code>Ảnh quảng cáo {subject}, chủ thể nổi bật, ánh sáng studio mềm, bố cục sạch, phong cách thương mại cao cấp, "
        "màu sắc hài hòa, chi tiết sắc nét, tỉ lệ 9:16, không chữ rối, không phóng đại công dụng.</code>\n\n"
        "Nếu muốn tạo ảnh thật trong bot, mình vào Tạo ảnh, xem gói và xác nhận hóa đơn trước khi xử lý ạ."
    )


def _base_result(
    intent_id: str,
    reply: str,
    *,
    sources: list[str],
    confidence: str = "high",
    product: str = "general",
    pricing_source: str = "unknown",
    price_text: str = "",
    handoff: bool = False,
    ticket: bool = False,
    context_section: str = "",
    learning_queue: bool = False,
    human_last_reply_required: bool = True,
    topic: str = "",
    last_subject: str = "",
    last_requested_asset: str = "",
    last_flow_suggestion: str = "",
) -> dict:
    context = load_context_brain()
    context_version = str(context.get("version") or CONTEXT_FILE_VERSION_FALLBACK)
    section = context_section or _section_for_intent(intent_id)
    result_sources = list(dict.fromkeys([*sources, "context_file"]))
    return {
        "matched": True,
        "intent_id": intent_id,
        "reply": reply,
        "reply_preview": reply,
        "reply_template_id": f"shared_knowledge:{intent_id}",
        "source": result_sources,
        "confidence": confidence,
        "primary_product": product,
        "product": product,
        "pricing_source": pricing_source,
        "price_text": price_text,
        "knowledge_entry_id": product if product != "general" else "",
        "handoff": handoff,
        "handoff_required": handoff,
        "ticket": ticket,
        "ticket_required": ticket,
        "context_file_path": str(context.get("path") or context_doc_path()),
        "context_file_version": context_version,
        "context_file_used": bool(context.get("loaded")),
        "context_version": context_version,
        "source_file_version": context_version,
        "context_section_used": section,
        "context_sections": [section] if section else [],
        "retrieval": {
            "intent_id": intent_id,
            "context_section_used": section,
            "source_file_version": context_version,
            "source": result_sources,
        },
        "learning_queue": bool(learning_queue),
        "would_queue_learning": bool(learning_queue),
        "human_last_reply_required": bool(human_last_reply_required),
        "previous_topic": topic,
        "last_product_type": topic or product,
        "last_requested_asset": last_requested_asset,
        "last_subject": last_subject,
        "last_flow_suggestion": last_flow_suggestion,
        "shared_docs": docs_status(),
    }


def pricing_table_reply() -> str:
    return (
        "Dạ bảng giá chính của TOAN AAS đây ạ:\n"
        "• Quy đổi: 1 Xu = 100đ.\n"
        "• ảnh AI: 50 / 150 / 200 / 300 / 400 / 500 / 600 Xu.\n"
        "• Video AI: 200 / 300 / 400 / 500 / 600 / 800 / 1000 / 1200 / 1500 Xu theo gói.\n"
        "• Voice riêng: lần đầu miễn phí, từ voice thứ 2 là 50 Xu; audio từ voice 0.10 Xu/từ, tối thiểu 1 Xu.\n"
        "• Nhạc nền AI: 100 / 150 / 200 Xu; bài hát có lời: 200 / 250 / 300 Xu.\n"
        "• SubDub: phụ đề gốc tự động miễn phí; dịch phụ đề 0.1 Xu/ký tự; lồng tiếng mặc định 0.10 Xu/ký tự; voice riêng 0.20 Xu/ký tự.\n"
        "• bot riêng/Premium: cần admin tư vấn theo nhu cầu, không báo một giá cố định khi chưa khảo sát.\n"
        "Bot luôn hiện hóa đơn trước, chỉ trừ Xu sau khi mình xác nhận."
    )


def image_pricing_reply() -> str:
    tiers = "; ".join(f"{name} {price} Xu" for name, price in IMAGE_TIERS)
    return (
        f"Dạ tạo/chỉnh ảnh AI đang theo các mức: {tiers}. "
        "Mức 50 Xu phù hợp tác vụ nhẹ; 150-200 Xu cho ảnh tiêu chuẩn; 300-400 Xu cho ảnh nhiều chi tiết; 500-600 Xu cho gói cao hơn. "
        "Nếu anh/chị chưa có prompt, em có thể viết prompt miễn phí trước. Bot sẽ hiện hóa đơn trước khi xử lý, chưa xác nhận thì chưa trừ Xu."
    )


def video_pricing_reply() -> str:
    tiers = "; ".join(f"{name} {price} Xu" for name, price in VIDEO_TIERS)
    return (
        f"Dạ video AI có các gói: {tiers}. "
        "Product Video hiện tính 1 cảnh = 8s; video khoảng 30s thường cần 4 cảnh. "
        "Nếu làm nhiều cảnh: 2-9 cảnh giảm 10%, 10-19 cảnh giảm 15%, 20 cảnh giảm 20% theo từng cảnh. "
        "Ví dụ gói Cơ bản 300 Xu làm 4 cảnh: 300 × 90% × 4 = 1.080 Xu nếu đủ điều kiện giảm. "
        "Bot sẽ dừng ở màn hóa đơn để mình tự xác nhận. Anh/chị muốn làm video về sản phẩm gì để em gợi ý gói phù hợp?"
    )


def voice_pricing_reply() -> str:
    return (
        "Dạ voice/TTS tính như sau: voice riêng đầu tiên miễn phí; từ voice riêng thứ 2 là 50 Xu nếu tạo thành công. "
        "Tạo audio từ voice là 0.10 Xu/từ, tối thiểu 1 Xu. Ví dụ 100 từ = 10 Xu, theo hướng dẫn hiện tại có giảm số lượng 10% còn 9 Xu."
    )


def music_pricing_reply() -> str:
    return (
        f"Dạ nhạc nền AI có 3 mức {_list_prices(MUSIC_BACKGROUND_TIERS)}. "
        f"Bài hát có lời có 3 mức {_list_prices(MUSIC_SONG_TIERS)}. "
        "Đổi gợi ý không trừ Xu; chỉ tạo file thật khi mình xem hóa đơn và xác nhận."
    )


def subdub_pricing_reply(chars: int = 0, *, private_voice: bool = False) -> str:
    if chars > 0:
        calc = calculate_subdub(chars, private_voice=private_voice)
        voice_label = "voice riêng" if private_voice else "giọng mặc định"
        discount = f", đã giảm {calc['discount_percent']}%" if calc["discount_percent"] else ""
        return (
            f"Dạ {format_xu(0)} cho tạo phụ đề gốc tự động. Nếu phụ đề + lồng tiếng {_format_int(chars)} ký tự với {voice_label}: "
            f"dịch phụ đề {format_xu(calc['subtitle_translate_xu'])}, lồng tiếng {format_xu(calc['dub_xu'])}{discount}, "
            f"tổng {format_xu(calc['total_xu'])}. Bot vẫn hiện hóa đơn trước khi mình xác nhận."
        )
    return (
        "Dạ SubDub tính theo ký tự: tạo phụ đề gốc tự động miễn phí; dịch phụ đề 0.1 Xu/ký tự; "
        "lồng tiếng giọng mặc định 0.10 Xu/ký tự; lồng tiếng voice riêng 0.20 Xu/ký tự. "
        "Trên 1.000 ký tự giảm 10%, trên 10.000 ký tự giảm 20%."
    )


def topup_reply(vnd: int, *, include_examples: bool = False) -> str:
    xu = vnd_to_xu(vnd)
    base = f"Dạ {format_vnd(vnd)} = {format_xu(xu)} vì 1 Xu = 100đ."
    if include_examples:
        base += (
            f" Với {format_xu(xu)}, mình có thể test nhiều gói ảnh, làm video gói 200-600 Xu, "
            "hoặc dùng cho SubDub/voice theo số ký tự/từ. Bot vẫn báo hóa đơn từng tác vụ trước khi trừ Xu."
        )
    return base


def status_video_reply() -> str:
    return (
        "Dạ em xin lỗi vì mình chưa thấy video ạ. Anh/chị kiểm tra trạng thái/tác vụ gần nhất trong bot, xem có mã xử lý hoặc thông báo đang chờ không, "
        "và đừng bấm tạo lại nhiều lần khi tác vụ còn chạy. Nếu đã bị trừ Xu mà chưa có file hợp lệ, anh/chị gửi mã xử lý, thời gian và ảnh màn hình để admin đối soát; em không tự hứa hoàn Xu khi chưa kiểm tra."
    )


def refund_reply() -> str:
    return (
        "Dạ em ghi nhận yêu cầu kiểm tra hoàn Xu. Chính sách là admin cần đối soát mã xử lý/giao dịch và kết quả thực tế trước; "
        "em không tự hứa hoàn Xu, cộng Xu, voucher hay hoàn tiền thay admin. Mình gửi giúp mã xử lý, thời gian và ảnh lỗi nếu có ạ."
    )


def charged_no_result_reply() -> str:
    return CHARGED_NO_RESULT_REPLY


def angry_customer_reply() -> str:
    return COMPLAINT_REPLY


def media_capability_reply() -> str:
    return (
        "Dạ clip/file này mình có thể dùng để tạo phụ đề, dịch phụ đề, lồng tiếng, lấy tư liệu dựng video, "
        "hoặc kiểm tra nội dung trước khi chọn flow ạ. Anh/chị muốn em hỗ trợ theo hướng nào trước nha?"
    )


def video_sales_reply(folded: str) -> str:
    topic = "sản phẩm"
    if "my pham" in folded:
        topic = "mỹ phẩm"
    elif "nuoc hoa" in folded:
        topic = "nước hoa"
    return (
        f"Dạ làm video bán hàng {topic} được ạ. Để đi đúng flow, mình chuẩn bị giúp em 4 ý: sản phẩm cụ thể/tệp khách, nền tảng đăng (TikTok/Reels/Facebook), tỉ lệ khung hình, và muốn video khoảng mấy cảnh. "
        "Nếu chưa có ảnh sản phẩm thì tạo ảnh trước; nếu có ảnh rồi thì đi thẳng Tạo video/Video từ ảnh. Tới bước có phí, bot sẽ hiện gói Xu và dừng ở màn xác nhận."
    )


def prompt_video_reply(text: str) -> str:
    raw = str(text or "").strip()
    folded = fold(raw)
    topic = raw
    match = re.search(r"(?:prompt\s+video|video\s+prompt|tạo\s+prompt\s+video|tao\s+prompt\s+video)\s+(.+)", raw, re.IGNORECASE)
    if match:
        topic = match.group(1).strip()
    elif "nuoc hoa" in folded:
        topic = "nước hoa nam"
    topic = topic or "sản phẩm"
    return (
        "Dạ đây là prompt video dùng miễn phí:\n\n"
        f"<code>Video quảng cáo ngắn cho {topic}, phong cách cao cấp và tự nhiên. "
        "Cảnh mở đầu cận sản phẩm với ánh sáng mềm, nền sạch, chuyển động máy quay chậm. "
        "Cảnh giữa thể hiện lợi ích chính, cảm giác sử dụng và chi tiết chất liệu. "
        "Cảnh cuối có CTA rõ: khám phá ngay hôm nay. Tỉ lệ 9:16, nhịp dựng nhanh, màu sắc sang, không chữ rối, không phóng đại công dụng.</code>"
    )


def guide_how_to_reply(product: str) -> str:
    if product == "image_ai":
        return (
            "Dạ để tạo ảnh: vào Tạo ảnh, nhập mô tả sản phẩm/phong cách/tỉ lệ, chọn gói ảnh, xem hóa đơn rồi xác nhận. "
            "Nếu chỉ cần prompt/caption thì em tạo text miễn phí cho mình trước."
        )
    if product == "subdub":
        return (
            "Dạ để làm phụ đề/lồng tiếng: mở Phụ đề / Dịch / Lồng tiếng, gửi video/audio, chọn tạo phụ đề gốc, dịch phụ đề hoặc lồng tiếng, xem số ký tự và hóa đơn rồi xác nhận."
        )
    return (
        "Dạ cách dùng nhanh: chọn đúng công cụ video, ảnh, phụ đề/lồng tiếng, voice/nhạc hoặc nạp Xu; gửi mô tả rõ sản phẩm/mục tiêu, chọn gói nếu có, kiểm tra hóa đơn, rồi tự bấm xác nhận. Chưa xác nhận thì bot chưa trừ Xu."
    )


def classify_shared_answer(text: str, *, conversation_memory: dict | None = None, media_type: str = "") -> dict:
    raw = str(text or "").strip()
    folded = fold(raw)
    media = fold(media_type)
    if not folded and _is_actionable_media(media):
        return _base_result(
            "file_without_instruction",
            FILE_WITHOUT_INSTRUCTION_REPLY,
            sources=["guide_doc"],
            confidence="high",
            product="general",
            pricing_source="guide_doc",
            context_section="fallback_policy",
        )
    if not folded:
        return {"matched": False}

    docs = docs_status()
    doc_sources = ["pricing_doc"]
    if docs["guide_doc_loaded"]:
        doc_sources.append("guide_doc")

    if folded in {"alo", "alo alo", "em oi", "shop oi", "co ai khong", "co ho tro khong"}:
        return _base_result(
            "greeting_ping",
            VAGUE_REPLY,
            sources=["cskh_knowledge"],
            confidence="high",
            context_section="fallback_policy",
        )

    if _looks_farewell(folded):
        return _base_result(
            "farewell",
            "Dạ vâng ạ. Khi nào anh/chị cần thêm về giá, video, ảnh, SubDub hay nạp Xu thì nhắn em hỗ trợ tiếp nha.",
            sources=["context_file"],
            confidence="high",
            context_section="human_last_reply_policy",
            human_last_reply_required=False,
        )

    if _looks_silent_followup(folded):
        return _base_result(
            "customer_silent_followup",
            "Dạ anh/chị cứ suy nghĩ thêm nha. Nếu cần em tính thử giá hoặc gợi ý flow phù hợp thì nhắn em, em hỗ trợ tiếp cho mình ạ.",
            sources=["context_file"],
            confidence="high",
            context_section="human_last_reply_policy",
        )

    if _is_meaningless_message(raw, folded):
        return _base_result(
            "vague_or_unclear",
            MEANINGLESS_REPLY,
            sources=["fallback"],
            confidence="medium",
            context_section="fallback_policy",
            learning_queue=True,
        )

    if _is_file_capability_question(folded):
        return _base_result(
            "content_asset_suggestion",
            media_capability_reply(),
            sources=["guide_doc", "cskh_knowledge"],
            confidence="high",
            product="general",
            pricing_source="guide_doc",
            context_section="usage_guides",
        )

    if _is_charged_no_result(folded):
        return _base_result(
            "complaint_charged_no_result",
            charged_no_result_reply(),
            sources=["guide_doc", "playbook"],
            confidence="high",
            product="general",
            pricing_source="guide_doc",
            handoff=True,
            ticket=True,
            context_section="scenario_dialogues",
        )

    if _is_angry_customer(folded):
        return _base_result(
            "angry_customer",
            angry_customer_reply(),
            sources=["playbook", "cskh_knowledge"],
            confidence="high",
            product="general",
            pricing_source="guide_doc",
            handoff=True,
            ticket=True,
            context_section="scenario_dialogues",
        )

    if any(term in folded for term in ("bot nay lam duoc gi", "ben em co gi", "toan aas lam gi", "bot lam gi")):
        return _base_result(
            "ask_capabilities",
            (
                "Dạ TOAN AAS hỗ trợ tạo video/ảnh AI, phụ đề-dịch-lồng tiếng, voice/audio, nhạc AI, "
                "prompt/caption/ý tưởng content và một số công cụ tài liệu. Bot luôn hiện hóa đơn trước khi xử lý. "
                "Anh/chị muốn bắt đầu với video, ảnh hay phụ đề/lồng tiếng trước ạ?"
            ),
            sources=["guide_doc", "cskh_knowledge"],
            confidence="high",
            pricing_source="guide_doc",
            context_section="usage_guides",
        )

    if _is_subdub_runtime_issue(folded):
        intent_id = "subdub_dubbing_error" if any(term in folded for term in ("long tieng", "dub", "voice over")) else "subdub_subtitle_error"
        reply = (
            "Dạ em xin lỗi vì phần phụ đề/lồng tiếng chưa ra đúng ạ. Anh/chị gửi giúp em mã xử lý và file kết quả nếu có, "
            "em chuyển kiểm tra lại trạng thái xử lý cho mình nha."
        )
        return _base_result(
            intent_id,
            reply,
            sources=["cskh_knowledge", "playbook"],
            confidence="high",
            product="subdub",
            pricing_source="guide_doc",
            handoff=True,
            ticket=True,
            context_section="scenario_dialogues",
        )

    if _is_payment_issue(folded) or _is_render_stuck_issue(folded) or _is_video_runtime_error(folded):
        return {"matched": False}

    if any(term in folded for term in ("bot rieng", "he thong rieng", "tra loi khach cho shop", "lam he thong rieng")):
        if any(term in folded for term in ("gia", "bao nhieu", "phi", "bao gia")):
            return {"matched": False}
        return _base_result(
            "premium_private_bot",
            (
                "Dạ phần bot riêng/hệ thống trả lời khách cho shop bên em có thể tư vấn theo nhu cầu ạ. "
                "Anh/chị gửi giúp em ngành hàng, kênh dùng chính và lượng khách dự kiến, em chuyển admin tư vấn cấu hình phù hợp cho mình."
            ),
            sources=["cskh_knowledge", "playbook"],
            confidence="high",
            product="premium_private_bot",
            pricing_source="guide_doc",
            handoff=True,
            ticket=True,
            context_section="scenario_dialogues",
        )

    product_pricing_context = any(
        term in folded
        for term in (
            "anh",
            "hinh",
            "video",
            "phu de",
            "subtitle",
            "sub",
            "long tieng",
            "dub",
            "voice",
            "tts",
            "nhac",
            "music",
            "bai hat",
        )
    )
    amount = _extract_vnd_amount(raw)
    if amount and _in_topup_context(folded, conversation_memory) and not product_pricing_context:
        include_examples = any(term in folded for term in ("duoc gi", "lam duoc gi", "xai duoc gi", "dung duoc gi"))
        return _base_result(
            "pricing_topup",
            topup_reply(amount, include_examples=include_examples),
            sources=doc_sources,
            product="payment_xu",
            pricing_source="pricing_doc",
            price_text=f"1 Xu = 100đ; {format_vnd(amount)} = {format_xu(vnd_to_xu(amount))}",
            context_section="pricing_facts",
        )

    if not product_pricing_context and any(term in folded for term in ("nap xu", "nap tien", "quy doi xu", "gia xu", "xu gia", "1 xu", "xu bang")):
        return _base_result(
            "pricing_topup",
            "Dạ quy đổi hiện tại là 1 Xu = 100đ. Mình nạp mệnh giá nào thì lấy số tiền chia 100 ra số Xu, ví dụ 100.000đ = 1.000 Xu. Vào /naptien hoặc mục Nạp Xu / Bảng giá để chọn mệnh giá; bot sẽ hiện hướng thanh toán trước.",
            sources=doc_sources,
            product="payment_xu",
            pricing_source="pricing_doc",
            price_text="1 Xu = 100đ",
            context_section="pricing_facts",
        )

    if any(term in folded for term in ("hoan xu", "hoan tien", "refund", "cong xu cho toi", "tra xu")):
        return _base_result(
            "refund_request",
            refund_reply(),
            sources=["guide_doc", "cskh_knowledge"],
            product="payment_xu",
            pricing_source="guide_doc",
            handoff=True,
            ticket=True,
            context_section="scenario_dialogues",
        )

    if "video" in folded and any(term in folded for term in ("chua thay", "khong thay", "chua co file", "khong ra file", "chua ra file", "bi ket", "ket")):
        return _base_result(
            "product_video_failed_no_file",
            status_video_reply(),
            sources=["guide_doc", "cskh_knowledge", "playbook"],
            product="product_video",
            pricing_source="guide_doc",
            handoff=True,
            ticket=True,
            context_section="scenario_dialogues",
        )

    has_price = any(term in folded for term in ("gia", "bao nhieu", "nhieu xu", "nhieu tien", "bang gia", "phi", "tinh sao"))
    chars = _extract_first_int(raw) if any(term in folded for term in ("ky tu", "kytu", "chu")) else 0

    if not has_price and any(term in folded for term in ("nap tien", "nap xu", "chuyen khoan", "thanh toan")) and any(term in folded for term in ("video", "anh", "hinh")):
        return {"matched": False}

    if _has_prompt_keyword(folded) and not has_price:
        prompt_topic = _extract_prompt_subject(raw) or _extract_image_subject(raw) or _extract_video_subject(raw, folded)
        prompt_is_video = "video" in folded or _memory_topic(conversation_memory) == "video"
        prompt_is_image = _has_image_keyword(raw, folded) or _memory_topic(conversation_memory) == "image"
        return _base_result(
            "prompt_create_request",
            prompt_create_reply(raw, folded),
            sources=["guide_doc", "cskh_knowledge"],
            product="product_video" if prompt_is_video else ("image_ai" if prompt_is_image else "general"),
            pricing_source="guide_doc",
            context_section="usage_guides",
            topic="video" if prompt_is_video else ("image" if prompt_is_image else "content"),
            last_subject=prompt_topic,
            last_requested_asset=prompt_topic,
            last_flow_suggestion="free_text_only",
        )

    if _is_short_price_followup(folded, conversation_memory):
        topic = _memory_topic(conversation_memory)
        if topic == "image":
            return _base_result(
                "image_ai_pricing",
                image_pricing_reply(),
                sources=doc_sources,
                product="image_ai",
                pricing_source="pricing_doc",
                price_text=_list_prices([price for _name, price in IMAGE_TIERS]),
                context_section="pricing_facts",
                topic="image",
            )
        if topic == "video":
            return _base_result(
                "product_video_pricing",
                video_pricing_reply(),
                sources=doc_sources,
                product="product_video",
                pricing_source="pricing_doc",
                price_text=_list_prices([price for _name, price in VIDEO_TIERS]),
                context_section="pricing_facts",
                topic="video",
            )

    if _is_image_create_request(raw, folded, conversation_memory) and not has_price:
        explicit_subject = _extract_image_subject(raw)
        subject = explicit_subject or _memory_subject(conversation_memory)
        return _base_result(
            "image_create_request",
            image_create_reply(raw, memory=conversation_memory, subject=explicit_subject),
            sources=["guide_doc", "cskh_knowledge"],
            confidence="high" if subject else "medium",
            product="image_ai",
            pricing_source="guide_doc",
            context_section="usage_guides",
            topic="image",
            last_subject=subject,
            last_requested_asset=subject or "image",
            last_flow_suggestion="menu|main_image",
        )

    if _is_video_create_request(raw, folded, conversation_memory) and not has_price:
        subject = _extract_video_subject(raw, folded)
        return _base_result(
            "video_create_request",
            video_create_reply(raw, folded),
            sources=["guide_doc", "cskh_knowledge"],
            confidence="high",
            product="product_video",
            pricing_source="guide_doc",
            context_section="usage_guides",
            topic="video",
            last_subject=subject,
            last_requested_asset=subject or "video",
            last_flow_suggestion="menu|main_video",
        )

    if any(term in folded for term in ("video ban hang", "lam video ban hang", "muon lam video", "muon tao video")) and "gia" not in folded:
        return _base_result(
            "product_video_consulting",
            video_sales_reply(folded),
            sources=["guide_doc", "cskh_knowledge"],
            product="product_video",
            pricing_source="guide_doc",
            context_section="usage_guides",
            topic="video",
        )

    if any(term in folded for term in ("ghep anh", "anh thanh video", "video tu anh", "anh chay", "slideshow", "anh roi ghep video")):
        return {"matched": False}

    if "bang gia" in folded and "video" in folded:
        return _base_result(
            "product_video_pricing",
            video_pricing_reply(),
            sources=doc_sources,
            product="product_video",
            pricing_source="pricing_doc",
            price_text=_list_prices([price for _name, price in VIDEO_TIERS]),
            context_section="pricing_facts",
        )
    if "bang gia" in folded or folded in {"gia", "bao gia", "gia tong"}:
        return _base_result(
            "pricing_table_general",
            pricing_table_reply(),
            sources=doc_sources,
            pricing_source="pricing_doc",
            price_text="1 Xu = 100đ; full pricing table",
            context_section="pricing_facts",
        )
    if has_price and any(term in folded for term in ("anh", "hinh", "tao anh", "chinh anh", "logo", "avatar")) and "video" not in folded:
        return _base_result(
            "image_ai_pricing",
            image_pricing_reply(),
            sources=doc_sources,
            product="image_ai",
            pricing_source="pricing_doc",
            price_text=_list_prices([price for _name, price in IMAGE_TIERS]),
            context_section="pricing_facts",
        )
    if has_price and "video" in folded:
        return _base_result(
            "product_video_pricing",
            video_pricing_reply(),
            sources=doc_sources,
            product="product_video",
            pricing_source="pricing_doc",
            price_text=_list_prices([price for _name, price in VIDEO_TIERS]),
            context_section="pricing_facts",
        )
    if has_price and any(term in folded for term in ("phu de", "subtitle", "sub", "long tieng", "dub", "voice over")):
        private_voice = any(term in folded for term in ("voice rieng", "giong rieng"))
        return _base_result(
            "subdub_pricing" if ("phu de" in folded and ("long tieng" in folded or "dub" in folded)) else ("dub_pricing" if ("long tieng" in folded or "dub" in folded) else "subtitle_pricing"),
            subdub_pricing_reply(chars, private_voice=private_voice),
            sources=doc_sources,
            product="subdub",
            pricing_source="pricing_doc",
            price_text="subtitle free; translation 0.1 Xu/char; default dub 0.10 Xu/char; custom voice 0.20 Xu/char",
            context_section="pricing_facts",
        )
    if has_price and any(term in folded for term in ("voice", "tts", "giong doc", "doc text")):
        return _base_result(
            "voice_pricing",
            voice_pricing_reply(),
            sources=doc_sources,
            product="voice",
            pricing_source="pricing_doc",
            price_text="custom voice first free, second 50 Xu; TTS 0.10 Xu/word min 1 Xu",
            context_section="pricing_facts",
        )
    if has_price and any(term in folded for term in ("nhac", "music", "bai hat", "sfx")):
        return _base_result(
            "music_pricing",
            music_pricing_reply(),
            sources=doc_sources,
            product="music",
            pricing_source="pricing_doc",
            price_text="background 100/150/200 Xu; song 200/250/300 Xu",
            context_section="pricing_facts",
        )
    if any(term in folded for term in ("huong dan", "cach dung", "su dung sao", "lam sao dung")):
        image_guide = any(term in folded for term in ("tao anh", "chinh anh", "anh ai", "anh san pham", "hinh", "image"))
        product = "subdub" if any(term in folded for term in ("phu de", "long tieng", "subdub")) else ("image_ai" if image_guide else "general")
        return _base_result(
            "guide_how_to",
            guide_how_to_reply(product),
            sources=["guide_doc"],
            product=product,
            pricing_source="guide_doc",
            context_section="usage_guides",
        )
    if re.search(r"\bloi\b", folded) and "tra loi" not in folded:
        return _base_result(
            "vague_or_unclear",
            "Dạ em chưa rõ mình đang lỗi ở phần nào ạ. Anh/chị đang lỗi ở video, ảnh, phụ đề/lồng tiếng, voice/nhạc hay nạp Xu/hóa đơn để em hướng dẫn đúng hơn nha?",
            sources=["fallback"],
            confidence="medium",
            context_section="fallback_policy",
            learning_queue=True,
        )
    return _base_result(
        "out_of_scope",
        MEANINGLESS_REPLY,
        sources=["fallback"],
        confidence="low",
        pricing_source="unknown",
        context_section="fallback_policy",
        learning_queue=True,
    )
