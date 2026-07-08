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


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def pricing_doc_path() -> Path:
    return repo_root() / "docs" / "public" / "bang-gia-toan-aas.md"


def guide_doc_path() -> Path:
    return repo_root() / "docs" / "public" / "huong-dan-su-dung-toan-aas.md"


def _read_doc(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def load_shared_docs() -> dict[str, str]:
    return {
        "pricing_doc": _read_doc(pricing_doc_path()),
        "guide_doc": _read_doc(guide_doc_path()),
    }


def docs_status() -> dict[str, Any]:
    docs = load_shared_docs()
    return {
        "pricing_doc_loaded": bool(docs["pricing_doc"]),
        "guide_doc_loaded": bool(docs["guide_doc"]),
        "pricing_doc_path": str(pricing_doc_path()),
        "guide_doc_path": str(guide_doc_path()),
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


def _base_result(intent_id: str, reply: str, *, sources: list[str], confidence: str = "high", product: str = "general", pricing_source: str = "unknown", price_text: str = "", handoff: bool = False, ticket: bool = False) -> dict:
    return {
        "matched": True,
        "intent_id": intent_id,
        "reply": reply,
        "reply_preview": reply,
        "reply_template_id": f"shared_knowledge:{intent_id}",
        "source": list(dict.fromkeys(sources)),
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
        "Bot sẽ hiện hóa đơn trước khi xử lý, chưa xác nhận thì chưa trừ Xu."
    )


def video_pricing_reply() -> str:
    tiers = "; ".join(f"{name} {price} Xu" for name, price in VIDEO_TIERS)
    return (
        f"Dạ video AI có các gói: {tiers}. "
        "Nếu làm nhiều cảnh: 1 cảnh khoảng 6 giây; 2-9 cảnh giảm 10%, 10-19 cảnh giảm 15%, 20 cảnh giảm 20% theo từng cảnh. "
        "Ví dụ gói Cơ bản 300 Xu làm 3 cảnh: 300 × 90% × 3 = 810 Xu. Bot sẽ dừng ở màn hóa đơn để mình tự xác nhận."
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
        "Dạ nếu chưa thấy video, mình kiểm tra theo thứ tự này giúp em: mở trạng thái/tác vụ gần nhất trong bot, xem có mã xử lý hoặc thông báo đang chờ không, "
        "đừng bấm tạo lại nhiều lần khi job còn chạy. Nếu đã bị trừ Xu mà chưa có file hợp lệ, gửi mã xử lý, thời gian và ảnh màn hình để admin đối soát; em không tự hứa hoàn Xu khi chưa kiểm tra."
    )


def refund_reply() -> str:
    return (
        "Dạ em ghi nhận yêu cầu kiểm tra hoàn Xu. Chính sách là admin cần đối soát mã xử lý/giao dịch và kết quả thực tế trước; "
        "em không tự hứa hoàn Xu, cộng Xu, voucher hay hoàn tiền thay admin. Mình gửi giúp mã xử lý, thời gian và ảnh lỗi nếu có ạ."
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
        "Dạ cách dùng nhanh: chọn đúng công cụ, gửi mô tả rõ sản phẩm/mục tiêu, chọn gói nếu có, kiểm tra hóa đơn, rồi tự bấm xác nhận. Chưa xác nhận thì bot chưa trừ Xu."
    )


def classify_shared_answer(text: str, *, conversation_memory: dict | None = None) -> dict:
    raw = str(text or "").strip()
    folded = fold(raw)
    if not folded:
        return {"matched": False}

    docs = docs_status()
    doc_sources = ["pricing_doc"]
    if docs["guide_doc_loaded"]:
        doc_sources.append("guide_doc")

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
        )

    if not product_pricing_context and any(term in folded for term in ("nap xu", "nap tien", "quy doi xu", "gia xu", "xu gia", "1 xu", "xu bang")):
        return _base_result(
            "pricing_topup",
            "Dạ quy đổi hiện tại là 1 Xu = 100đ. Mình nạp mệnh giá nào thì lấy số tiền chia 100 ra số Xu, ví dụ 100.000đ = 1.000 Xu. Vào /naptien hoặc mục Nạp Xu / Bảng giá để chọn mệnh giá; bot sẽ hiện hướng thanh toán trước.",
            sources=doc_sources,
            product="payment_xu",
            pricing_source="pricing_doc",
            price_text="1 Xu = 100đ",
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
        )

    if "prompt" in folded and "video" in folded:
        return _base_result(
            "prompt_video_generation",
            prompt_video_reply(raw),
            sources=["guide_doc", "cskh_knowledge"],
            product="product_video",
            pricing_source="guide_doc",
        )

    if any(term in folded for term in ("video ban hang", "lam video ban hang", "muon lam video", "muon tao video")) and "gia" not in folded:
        return _base_result(
            "product_video_consulting",
            video_sales_reply(folded),
            sources=["guide_doc", "cskh_knowledge"],
            product="product_video",
            pricing_source="guide_doc",
        )

    has_price = any(term in folded for term in ("gia", "bao nhieu", "nhieu xu", "nhieu tien", "bang gia", "phi", "tinh sao"))
    chars = _extract_first_int(raw) if any(term in folded for term in ("ky tu", "kytu", "chu")) else 0
    if any(term in folded for term in ("ghep anh", "anh thanh video", "video tu anh", "anh chay", "slideshow", "anh roi ghep video")):
        return {"matched": False}

    if "bang gia" in folded or folded in {"gia", "bao gia", "gia tong"}:
        return _base_result(
            "pricing_table_general",
            pricing_table_reply(),
            sources=doc_sources,
            pricing_source="pricing_doc",
            price_text="1 Xu = 100đ; full pricing table",
        )
    if has_price and any(term in folded for term in ("anh", "hinh", "tao anh", "chinh anh", "logo", "avatar")) and "video" not in folded:
        return _base_result(
            "image_ai_pricing",
            image_pricing_reply(),
            sources=doc_sources,
            product="image_ai",
            pricing_source="pricing_doc",
            price_text=_list_prices([price for _name, price in IMAGE_TIERS]),
        )
    if has_price and "video" in folded:
        return _base_result(
            "product_video_pricing",
            video_pricing_reply(),
            sources=doc_sources,
            product="product_video",
            pricing_source="pricing_doc",
            price_text=_list_prices([price for _name, price in VIDEO_TIERS]),
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
        )
    if has_price and any(term in folded for term in ("voice", "tts", "giong doc", "doc text")):
        return _base_result(
            "voice_pricing",
            voice_pricing_reply(),
            sources=doc_sources,
            product="voice",
            pricing_source="pricing_doc",
            price_text="custom voice first free, second 50 Xu; TTS 0.10 Xu/word min 1 Xu",
        )
    if has_price and any(term in folded for term in ("nhac", "music", "bai hat", "sfx")):
        return _base_result(
            "music_pricing",
            music_pricing_reply(),
            sources=doc_sources,
            product="music",
            pricing_source="pricing_doc",
            price_text="background 100/150/200 Xu; song 200/250/300 Xu",
        )
    if any(term in folded for term in ("huong dan", "cach dung", "su dung sao", "lam sao dung")):
        product = "subdub" if any(term in folded for term in ("phu de", "long tieng", "subdub")) else ("image_ai" if "anh" in folded else "general")
        return _base_result(
            "guide_how_to",
            guide_how_to_reply(product),
            sources=["guide_doc"],
            product=product,
            pricing_source="guide_doc",
        )
    return {"matched": False}
