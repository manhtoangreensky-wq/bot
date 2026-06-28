"""Shared public pricing and guide copy for TOAN AAS.

This module is intentionally copy-only. It does not calculate charges, call
product engines, or change wallet/payment behavior.
"""

from __future__ import annotations

import html
import re
from typing import Iterable


PRICING_DOWNLOAD_FILENAME = "bang-gia-toan-aas.md"
GUIDE_DOWNLOAD_FILENAME = "huong-dan-su-dung-toan-aas.md"

CONFIRM_GATE_COPY = (
    "TOAN AAS sẽ hiển thị hóa đơn trước khi xử lý. Hệ thống chỉ trừ Xu sau khi "
    "anh/chị xác nhận và tác vụ tạo ra kết quả hợp lệ."
)
MAINTENANCE_NOTICE = "Hệ thống đang bảo trì/nâng cấp. TOAN AAS chưa xử lý và chưa trừ Xu. Vui lòng thử lại sau."

TECHNICAL_WORDS = (
    "provider",
    "api",
    "asr",
    "tts",
    "mux",
    "ffmpeg",
    "adapter",
    "debug",
    "route",
    "payload",
    "traceback",
    "runtimeerror",
    "model id",
    "database",
    "worker",
)


def _clean_lines(lines: Iterable[str]) -> list[str]:
    return [str(line) for line in lines]


def strip_html_tags(text: str) -> str:
    return re.sub(r"</?(?:b|code|i|u|strong|em)>", "", str(text or ""))


def technical_words_found(text: str) -> list[str]:
    lowered = strip_html_tags(text).lower()
    found = []
    for word in TECHNICAL_WORDS:
        if re.search(rf"(?<![a-z0-9_]){re.escape(word)}(?![a-z0-9_])", lowered):
            found.append(word)
    return found


def html_lines_to_markdown(lines: Iterable[str]) -> str:
    converted = []
    for line in _clean_lines(lines):
        clean = strip_html_tags(line)
        clean = clean.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
        converted.append(clean)
    return "\n".join(converted).strip() + "\n"


def lines_to_html_page(title: str, lines: Iterable[str]) -> str:
    body_lines = []
    for line in _clean_lines(lines):
        if not line:
            body_lines.append("")
        elif line.startswith(("• ", "1. ", "2. ", "3. ", "4. ", "5. ", "6. ", "7. ", "8. ")):
            body_lines.append(line)
        else:
            body_lines.append(line)
    body = "<br>\n".join(body_lines)
    return f"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 0; background: #f7fbf9; color: #10241d; line-height: 1.6; }}
    main {{ max-width: 920px; margin: 0 auto; padding: 32px 18px 48px; }}
    .card {{ background: #fff; border: 1px solid #d8ece4; border-radius: 14px; padding: 24px; box-shadow: 0 12px 32px rgba(20, 80, 60, .08); }}
    a {{ color: #087f5b; font-weight: 700; }}
  </style>
</head>
<body>
  <main>
    <p><a href="/">← Trang chủ</a></p>
    <div class="card">{body}</div>
  </main>
</body>
</html>
"""


def pricing_menu_labels() -> list[tuple[str, str]]:
    return [
        ("pricing|total", "💰 Bảng giá tổng"),
        ("pricing|voice", "🎙 Bảng giá Giọng nói"),
        ("pricing|music", "🎵 Bảng giá Nhạc AI"),
        ("pricing|video", "🎬 Bảng giá Video"),
        ("pricing|subtitle", "🌐 Bảng giá Phụ đề / Lồng tiếng"),
        ("pricing|image", "🖼 Bảng giá Hình ảnh"),
        ("pricing|free", "🎁 Miễn phí / Không tính Xu"),
        ("pricing|member", "🎁 Khuyến mãi / Thành viên"),
        ("pricing|guide", "📘 Hướng dẫn sử dụng"),
        ("pricing|download_pricing", "📥 Tải bảng giá"),
        ("pricing|download_guide", "📘 Tải hướng dẫn sử dụng"),
    ]


def default_context() -> dict:
    return {
        "image_price_lines": [
            "• Ảnh 50 Xu: tác vụ ảnh nhẹ / cơ bản.",
            "• Ảnh 150-200 Xu: tạo hoặc chỉnh ảnh tiêu chuẩn.",
            "• Ảnh 300-400 Xu: ảnh chất lượng cao, nhiều chi tiết hơn.",
            "• Ảnh 500-600 Xu: ảnh cao cấp, nhiều ảnh hoặc tác vụ nặng nếu hệ thống có.",
        ],
        "video_price_lines": [
            "• Video 200 Xu: gói trải nghiệm.",
            "• Video 300 Xu: gói cơ bản.",
            "• Video 400 Xu: gói phổ thông.",
            "• Video 500 Xu: gói nâng cao.",
            "• Video 600 Xu: gói bán hàng.",
            "• Video 800 Xu: gói cao cấp.",
            "• Video 1000 Xu: gói chuyên nghiệp.",
            "• Video 1200 Xu: gói Pro Plus.",
            "• Video 1500 Xu: gói Premium.",
        ],
        "document_price_lines": [
            "• Ảnh sang PDF: <b>0 Xu</b>.",
            "• PDF sang ảnh: <b>0 Xu</b>.",
            "• PDF sang Word text: <b>0 Xu</b> nếu công cụ đang mở.",
            "• Nén PDF: <b>0 Xu</b>.",
            "• Tách PDF: <b>0 Xu</b>.",
            "• Gộp PDF: <b>0 Xu</b>.",
            "• Các công cụ tài liệu đang thử nghiệm vẫn hiển thị rõ giá trước khi xử lý.",
        ],
        "member_discount_lines": ["• Chiết khấu thành viên: chưa kích hoạt."],
    }


def _context_value(context: dict | None, key: str) -> list[str]:
    data = dict(default_context())
    data.update(context or {})
    return list(data.get(key) or [])


def pricing_total_lines(context: dict | None = None) -> list[str]:
    return [
        "💰 <b>Bảng giá tổng TOAN AAS</b>",
        "",
        CONFIRM_GATE_COPY,
        "",
        "• Giọng nói: từ 0.05 Xu / từ.",
        "• Tạo voice riêng: lần đầu miễn phí, từ lần 2: 50 Xu / voice thành công.",
        "• Nhạc nền AI: 100 / 150 / 200 Xu.",
        "• Bài hát có lời: 200 / 250 / 300 Xu.",
        "• Video AI: theo gói video đang chọn.",
        "• Tạo phụ đề tự động: miễn phí.",
        "• Dịch phụ đề: 0.1 Xu / ký tự.",
        "• Lồng tiếng giọng mặc định: 0.05 Xu / ký tự.",
        "• Lồng tiếng voice riêng: 0.1 Xu / ký tự.",
        "• Hình ảnh: 50 / 150 / 200 / 300 / 400 / 500 / 600 Xu.",
        "• Tài nguyên tự có của anh/chị: miễn phí nếu hệ thống không cần tạo mới.",
        "",
        "<b>Nhóm giá chính</b>",
        "1. Giọng nói.",
        "2. Nhạc AI.",
        "3. Video.",
        "4. Phụ đề / Lồng tiếng.",
        "5. Hình ảnh.",
        "6. Tài liệu / file nếu công cụ đang mở.",
        "7. Miễn phí / không tính Xu.",
        "8. Chiết khấu / thành viên.",
        "",
        "TOAN AAS sẽ báo giá chi tiết trước khi xử lý.",
    ]


def pricing_voice_lines() -> list[str]:
    return [
        "🎙 <b>Bảng giá Giọng nói</b>",
        "",
        CONFIRM_GATE_COPY,
        "",
        "<b>A. Tạo voice riêng</b>",
        "• Voice riêng đầu tiên tạo thành công: miễn phí.",
        "• Từ voice riêng thứ 2 trở đi: 50 Xu / voice tạo thành công.",
        "• Chỉ tính Xu khi tạo voice thành công.",
        "• Nếu mẫu lỗi, quá ngắn hoặc không tạo được voice hợp lệ: không trừ Xu.",
        "• Nếu tài khoản vận hành được miễn phí nội bộ, phần hiển thị cho khách vẫn giữ cùng cách báo giá.",
        "",
        "<b>B. Tạo audio từ voice</b>",
        "• 0.05 Xu / từ.",
        "• Nội dung tối thiểu: 20 từ.",
        "• Tối thiểu thanh toán: 1 Xu.",
        "• Không giới hạn từ nếu hệ thống cho phép.",
        "• Có chỉnh tốc độ 0.1x-2.0x.",
        "• Có chỉnh âm lượng 0%-200%.",
        "• 100% là mức âm lượng đã chốt hiện tại.",
        "• 0% cần xác nhận riêng nếu tạo audio im lặng.",
        "",
        "<b>Ví dụ</b>",
        "• Anh/chị tạo audio 100 từ: 100 × 0.05 = 5 Xu.",
        "• Anh/chị nhập 20 từ: 20 × 0.05 = 1 Xu. Tổng thanh toán tối thiểu: 1 Xu.",
        "• Anh/chị tạo voice riêng lần đầu: 0 Xu.",
        "• Anh/chị tạo voice riêng lần thứ 2: 50 Xu nếu tạo thành công.",
    ]


def pricing_music_lines() -> list[str]:
    return [
        "🎵 <b>Bảng giá Nhạc AI</b>",
        "",
        CONFIRM_GATE_COPY,
        "",
        "<b>A. Nhạc nền / không lời</b>",
        "• Cơ bản: 100 Xu.",
        "• Tiêu chuẩn: 150 Xu.",
        "• Cao cấp: 200 Xu.",
        "",
        "<b>B. Bài hát có lời</b>",
        "• Cơ bản: 200 Xu.",
        "• Tiêu chuẩn: 250 Xu.",
        "• Cao cấp: 300 Xu.",
        "",
        "Nhạc nền dùng cho video quảng cáo, intro, nền TikTok/Facebook hoặc nội dung giới thiệu sản phẩm. Mặc định không có giọng hát.",
        "Bài hát có lời dùng để tạo bài hát có giọng hát, có thể chọn giọng nam, giọng nữ, song ca hoặc tự động. TOAN AAS sẽ tạo 3 gợi ý để anh/chị chọn trước khi tạo nhạc.",
        "",
        "<b>Cách tính</b>",
        "• Tính theo mỗi lần tạo file nhạc thành công.",
        "• Không trừ Xu trước khi xác nhận.",
        "• Không trừ Xu nếu hệ thống không tạo được file nhạc hợp lệ.",
        "• Nếu tài khoản vận hành được miễn phí nội bộ, phần hiển thị cho khách vẫn giữ cùng cách báo giá.",
        "",
        "<b>Ví dụ</b>",
        "• Nhạc nền Tiêu chuẩn: tổng thanh toán 150 Xu.",
        "• Bài hát có lời Cao cấp, giọng nữ: tổng thanh toán 300 Xu.",
        "• Bấm Đổi gợi ý: không trừ Xu, chỉ tạo gợi ý mới.",
    ]


def pricing_video_lines(context: dict | None = None) -> list[str]:
    return [
        "🎬 <b>Bảng giá Video</b>",
        "",
        "Bảng này giữ nguyên các gói video hiện có trong hệ thống.",
        CONFIRM_GATE_COPY,
        "",
        *_context_value(context, "video_price_lines"),
        "",
        "<b>Miễn phí trong video khi dùng tài nguyên có sẵn</b>",
        "• Watermark/logo chữ có sẵn nếu không tạo mới: miễn phí.",
        "• Dùng ảnh của khách: miễn phí phần tài nguyên ảnh.",
        "• Dùng nhạc của khách: miễn phí phần tài nguyên nhạc.",
        "• Dùng voice/audio có sẵn của khách: miễn phí phần tài nguyên có sẵn.",
        "• Tạo phụ đề gốc tự động từ voice/lời đọc có sẵn trong quy trình video: miễn phí nếu chỉ tạo phụ đề gốc.",
        "• Logo tự tạo bằng công cụ ảnh riêng: tính theo bảng giá Hình ảnh, không tính trong video nếu khách tự đưa tài nguyên.",
        "",
        "<b>Ví dụ</b>",
        "• Anh/chị chọn gói video 300 Xu, bật voice mặc định và nhạc mặc định miễn phí theo gói. Tổng thanh toán vẫn là 300 Xu nếu không chọn thêm tác vụ tạo mới tính phí.",
        "• Nếu anh/chị chọn tạo ảnh/logo AI riêng bên ngoài, phần ảnh sẽ tính theo bảng giá Hình ảnh.",
    ]


def pricing_subtitle_lines() -> list[str]:
    return [
        "🌐 <b>Bảng giá Phụ đề / Lồng tiếng</b>",
        "",
        CONFIRM_GATE_COPY,
        "",
        "<b>A. Tạo phụ đề tự động</b>",
        "• Miễn phí.",
        "• Chỉ tạo phụ đề gốc từ video/audio/lời đọc.",
        "• Không dịch, không lồng tiếng nếu chưa chọn thêm tác vụ.",
        "",
        "<b>B. Dịch phụ đề</b>",
        "• 0.1 Xu / ký tự.",
        "• Trên 1.000 ký tự: giảm 10%.",
        "• Trên 10.000 ký tự: giảm 20%.",
        "• Hệ thống hiển thị rõ số ký tự tính phí trước khi xử lý.",
        "",
        "<b>C. Lồng tiếng giọng mặc định</b>",
        "• 0.05 Xu / ký tự.",
        "• Trên 1.000 ký tự: giảm 10%.",
        "• Trên 10.000 ký tự: giảm 20%.",
        "",
        "<b>D. Lồng tiếng voice riêng</b>",
        "• 0.1 Xu / ký tự.",
        "• Trên 1.000 ký tự: giảm 10%.",
        "• Trên 10.000 ký tự: giảm 20%.",
        "",
        "<b>E. Phụ đề + Lồng tiếng</b>",
        "Tổng = giá dịch phụ đề + giá lồng tiếng.",
        "",
        "<b>Ví dụ</b>",
        "• Dịch phụ đề 2.000 ký tự: giá gốc 200 Xu, giảm 10%, tổng còn 180 Xu.",
        "• Lồng tiếng giọng mặc định 2.000 ký tự: giá gốc 100 Xu, giảm 10%, tổng còn 90 Xu.",
        "• Lồng tiếng voice riêng 2.000 ký tự: giá gốc 200 Xu, giảm 10%, tổng còn 180 Xu.",
        "• Phụ đề + lồng tiếng: 180 Xu + 90 Xu = 270 Xu.",
    ]


def pricing_image_lines(context: dict | None = None) -> list[str]:
    return [
        "🖼 <b>Bảng giá Hình ảnh</b>",
        "",
        CONFIRM_GATE_COPY,
        "",
        *_context_value(context, "image_price_lines"),
        "",
        "<b>Gợi ý chọn gói</b>",
        "• 50 Xu: tác vụ ảnh nhẹ / cơ bản nếu hệ thống đang hỗ trợ.",
        "• 150-200 Xu: tạo/chỉnh ảnh tiêu chuẩn.",
        "• 300-400 Xu: ảnh chất lượng cao / nhiều chi tiết.",
        "• 500-600 Xu: ảnh cao cấp / nhiều ảnh / tác vụ nặng nếu hệ thống có.",
        "",
        "<b>Ví dụ</b>",
        "Anh/chị chọn gói ảnh 200 Xu để tạo ảnh sản phẩm. TOAN AAS hiển thị hóa đơn 200 Xu trước khi xử lý. Nếu ảnh không tạo được hợp lệ, hệ thống không trừ Xu.",
    ]


def pricing_docs_lines(context: dict | None = None) -> list[str]:
    return [
        "📄 <b>Bảng giá Tài liệu / File</b>",
        "",
        *_context_value(context, "document_price_lines"),
        "",
        "TOAN AAS vẫn hiển thị rõ trước khi xử lý nếu một công cụ tài liệu có phí trong tương lai.",
    ]


def pricing_free_lines() -> list[str]:
    return [
        "🎁 <b>Những phần miễn phí</b>",
        "",
        "• Xem demo voice: miễn phí.",
        "• Đổi gợi ý nhạc: miễn phí.",
        "• Tạo gợi ý bài hát/nhạc: miễn phí.",
        "• Tạo phụ đề gốc tự động: miễn phí.",
        "• Dùng ảnh do anh/chị gửi lên: không tính phí tạo ảnh.",
        "• Dùng nhạc do anh/chị gửi lên: không tính phí tạo nhạc.",
        "• Dùng voice/audio có sẵn của anh/chị: không tính phí tạo voice mới.",
        "• Watermark/logo chữ có sẵn trong video: miễn phí nếu không tạo ảnh/logo mới.",
        "• Xem hóa đơn/tính thử giá: miễn phí.",
        "• Hủy trước xác nhận: không trừ Xu.",
        "",
        "Nếu anh/chị yêu cầu TOAN AAS tạo mới ảnh, voice, nhạc, phụ đề dịch, lồng tiếng hoặc video thì phần tạo mới sẽ tính theo bảng giá tương ứng.",
    ]


def pricing_member_lines(context: dict | None = None) -> list[str]:
    return [
        "🎁 <b>Khuyến mãi & Thành viên</b>",
        "",
        "<b>Chiết khấu thành viên hiện tại</b>",
        *_context_value(context, "member_discount_lines"),
        "",
        "<b>Cách cộng dồn</b>",
        "1. Tính giá gốc theo sản phẩm.",
        "2. Áp dụng chiết khấu theo số lượng/ký tự nếu có.",
        "3. Áp dụng chiết khấu thành viên trên số còn lại.",
        "4. Áp dụng voucher/khuyến mãi nếu hệ thống có, theo chính sách hiện có.",
        "5. Làm tròn theo đơn vị Xu hiện tại của ví.",
        "6. Hiển thị tổng cuối trước xác nhận.",
        "",
        "<b>Ví dụ có thành viên giảm 10%</b>",
        "Dịch phụ đề 2.000 ký tự: giá gốc 200 Xu, giảm số lượng 10% còn 180 Xu, thành viên giảm thêm 10% còn 162 Xu. Tổng thanh toán: 162 Xu.",
        "",
        "<b>Ví dụ không có thành viên</b>",
        "Dịch phụ đề 2.000 ký tự: tổng thanh toán sau giảm số lượng là 180 Xu.",
        "",
        "Khuyến mãi nạp tiền chỉ áp dụng cho PayOS hoặc chuyển khoản ngân hàng Việt Nam theo điều kiện từng chương trình.",
    ]


def pricing_lines(section: str = "total", context: dict | None = None) -> list[str]:
    key = (section or "total").strip().lower()
    mapping = {
        "catalog": pricing_total_lines,
        "main": pricing_total_lines,
        "total": pricing_total_lines,
        "voice": lambda _context=None: pricing_voice_lines(),
        "music": lambda _context=None: pricing_music_lines(),
        "video": pricing_video_lines,
        "subtitle": lambda _context=None: pricing_subtitle_lines(),
        "subtitle_dub": lambda _context=None: pricing_subtitle_lines(),
        "image": pricing_image_lines,
        "docs": pricing_docs_lines,
        "free": lambda _context=None: pricing_free_lines(),
        "member": pricing_member_lines,
    }
    renderer = mapping.get(key, pricing_total_lines)
    return renderer(context)


def all_pricing_lines(context: dict | None = None) -> list[str]:
    lines: list[str] = []
    for key in ("total", "voice", "music", "video", "subtitle", "image", "docs", "free", "member"):
        if lines:
            lines.extend(["", "-----", ""])
        lines.extend(pricing_lines(key, context))
    return lines


def customer_guide_sections() -> list[tuple[str, str, str]]:
    return [
        (
            "quick_start",
            "Bắt đầu nhanh",
            "\n".join([
                "🚀 <b>BẮT ĐẦU NHANH</b>",
                "",
                "1. Chọn tính năng muốn dùng: Tạo ảnh, Tạo video, Studio âm thanh, Phụ đề / Dịch / Lồng tiếng hoặc Tài liệu.",
                "2. Gửi mô tả rõ mục tiêu, sản phẩm, phong cách, nền tảng đăng và yêu cầu riêng.",
                "3. Chọn gói phù hợp nếu tính năng có nhiều mức giá.",
                "4. Kiểm tra bản xem trước, bảng giá và thông tin xác nhận.",
                "5. Chỉ khi anh/chị xác nhận, hệ thống mới xử lý và mới trừ Xu nếu bước đó có phí.",
                "6. Nhận kết quả trong bot, tải về hoặc tiếp tục bước kế tiếp.",
                "",
                CONFIRM_GATE_COPY,
                "",
                "Ví dụ: muốn tạo video bán hàng, anh/chị có thể tạo ảnh sản phẩm trước, sau đó dùng ảnh đó để tạo video.",
            ]),
        ),
        (
            "voice_custom",
            "Tạo voice riêng",
            "\n".join([
                "🎙 <b>HƯỚNG DẪN TẠO VOICE RIÊNG</b>",
                "",
                "Dùng khi: anh/chị muốn có giọng riêng đã lưu để dùng cho nội dung sau này.",
                "",
                "Cách làm:",
                "1. Vào Studio âm thanh.",
                "2. Chọn tạo voice riêng.",
                "3. Gửi mẫu giọng rõ, đủ dài và ít tạp âm.",
                "4. Xem điều kiện và hóa đơn nếu đây không phải voice đầu tiên.",
                "5. Xác nhận tạo voice.",
                "",
                "Cách tính: voice riêng đầu tiên tạo thành công miễn phí; từ voice thứ 2 là 50 Xu / voice thành công.",
                "Ví dụ: tạo voice riêng lần đầu = 0 Xu; tạo voice riêng lần thứ 2 = 50 Xu nếu tạo thành công.",
            ]),
        ),
        (
            "voice_audio",
            "Tạo audio từ voice",
            "\n".join([
                "📘 <b>TẠO AUDIO TỪ VOICE</b>",
                "",
                "Dùng khi: anh/chị muốn biến văn bản thành file giọng đọc.",
                "",
                "Cách làm:",
                "1. Vào Studio âm thanh.",
                "2. Chọn Kho voice hoặc giọng mặc định.",
                "3. Bấm Tạo audio.",
                "4. Nhập nội dung từ 20 từ trở lên.",
                "5. Chỉnh tốc độ/âm lượng nếu cần.",
                "6. Xem hóa đơn.",
                "7. Xác nhận tạo audio.",
                "",
                "Cách tính: 0.05 Xu / từ, tối thiểu 1 Xu.",
                "Ví dụ: 100 từ = 5 Xu; 20 từ = 1 Xu.",
            ]),
        ),
        (
            "music_background",
            "Tạo nhạc nền AI",
            "\n".join([
                "🎵 <b>HƯỚNG DẪN TẠO NHẠC NỀN AI</b>",
                "",
                "Dùng khi: anh/chị cần nhạc không lời cho video, intro, quảng cáo hoặc nội dung sản phẩm.",
                "",
                "Cách làm:",
                "1. Vào Studio âm thanh.",
                "2. Chọn Nhạc nền AI.",
                "3. Mô tả phong cách, cảm xúc và mục đích sử dụng.",
                "4. Chọn Cơ bản, Tiêu chuẩn hoặc Cao cấp.",
                "5. Xem hóa đơn và xác nhận.",
                "",
                "Cách tính: Cơ bản 100 Xu, Tiêu chuẩn 150 Xu, Cao cấp 200 Xu.",
                "Ví dụ: chọn Nhạc nền Tiêu chuẩn = 150 Xu.",
            ]),
        ),
        (
            "music_song",
            "Tạo bài hát có lời",
            "\n".join([
                "🎤 <b>HƯỚNG DẪN TẠO BÀI HÁT CÓ LỜI</b>",
                "",
                "Dùng khi: anh/chị muốn bài hát ngắn cho thương hiệu, sản phẩm hoặc chiến dịch.",
                "",
                "Cách làm:",
                "1. Vào Studio âm thanh.",
                "2. Chọn Bài hát có lời.",
                "3. Nhập chủ đề, phong cách, cảm xúc và chọn giọng hát.",
                "4. Xem 3 gợi ý.",
                "5. Chọn gợi ý phù hợp, xem hóa đơn và xác nhận.",
                "",
                "Cách tính: Cơ bản 200 Xu, Tiêu chuẩn 250 Xu, Cao cấp 300 Xu.",
                "Ví dụ: bài hát có lời Cao cấp, giọng nữ = 300 Xu.",
                "Đổi gợi ý: không trừ Xu.",
            ]),
        ),
        (
            "audio",
            "Âm thanh",
            "\n".join([
                "🎧 <b>HƯỚNG DẪN ÂM THANH</b>",
                "",
                "Âm thanh giúp video dễ nghe, dễ bán hàng và chuyên nghiệp hơn.",
                "",
                "Bạn có thể dùng:",
                "• Tạo giọng đọc từ nội dung đã viết.",
                "• Tạo voice riêng.",
                "• Tạo nhạc nền theo phong cách mong muốn.",
                "• Tạo bài hát ngắn cho thương hiệu, sản phẩm hoặc chiến dịch.",
                "",
                "Giá cần nhớ:",
                "• Audio từ voice: 0.05 Xu / từ, tối thiểu 1 Xu.",
                "• Voice riêng đầu tiên: 0 Xu; từ voice thứ 2: 50 Xu nếu tạo thành công.",
                "• Nhạc nền AI: 100 / 150 / 200 Xu.",
                "• Bài hát có lời: 200 / 250 / 300 Xu.",
                "",
                "Ví dụ: audio 100 từ = 5 Xu; nhạc nền Tiêu chuẩn = 150 Xu.",
                MAINTENANCE_NOTICE,
            ]),
        ),
        (
            "video_ai",
            "Tạo video",
            "\n".join([
                "🎬 <b>HƯỚNG DẪN TẠO VIDEO AI</b>",
                "",
                "Dùng khi: anh/chị muốn tạo video từ mô tả, ảnh có sẵn hoặc concept bán hàng.",
                "",
                "Quy trình tạo video:",
                "1. Mở mục <b>Tạo video</b>.",
                "2. Chọn tạo video từ mô tả hoặc tạo video từ ảnh đã có.",
                "3. Gửi mô tả video: chủ thể, chuyển động, bối cảnh, ánh sáng, tỉ lệ, thời lượng và cảm xúc.",
                "4. Chọn gói video.",
                "5. Chọn số cảnh nếu muốn làm video dài hơn.",
                "6. Xem tổng chi phí, kiểm tra nội dung và xác nhận.",
                "7. Hệ thống xử lý và gửi video về bot khi hoàn tất.",
                "8. Sau khi có video, anh/chị có thể dùng thêm Âm thanh hoặc Phụ đề / Dịch / Lồng tiếng nếu cần.",
                "",
                "Bảng giá video theo gói:",
                "• Trải nghiệm — 200 Xu.",
                "• Cơ bản — 300 Xu.",
                "• Phổ thông — 400 Xu.",
                "• Nâng cao — 500 Xu.",
                "• Bán hàng — 600 Xu.",
                "• Cao cấp — 800 Xu.",
                "• Chuyên nghiệp — 1000 Xu.",
                "• Pro Plus — 1200 Xu.",
                "• Premium — 1500 Xu.",
                "",
                "Gói Trải nghiệm 200 Xu phù hợp để test ý tưởng nhanh, xem hướng chuyển động, kiểm tra concept hoặc tạo bản nháp ngắn trước khi dùng gói cao hơn.",
                "",
                "Cách tính theo cảnh:",
                "• 1 cảnh khoảng 6 giây.",
                "• 3 cảnh khoảng 18 giây.",
                "• 5 cảnh khoảng 30 giây.",
                "• 10 cảnh khoảng 60 giây.",
                "• 20 cảnh khoảng 120 giây.",
                "",
                "Ưu đãi theo số cảnh:",
                "• 1 cảnh: giá gốc.",
                "• 2-9 cảnh: giảm 10%.",
                "• 10-19 cảnh: giảm 15%.",
                "• 20 cảnh: giảm 20%.",
                "",
                "Ví dụ: gói Cơ bản 300 Xu, làm 3 cảnh: 300 × 90% = 270 Xu/cảnh, tổng 270 × 3 = 810 Xu.",
            ]),
        ),
        (
            "auto_subtitle",
            "Tạo phụ đề tự động",
            "\n".join([
                "📝 <b>HƯỚNG DẪN TẠO PHỤ ĐỀ TỰ ĐỘNG</b>",
                "",
                "Dùng khi: anh/chị cần phụ đề gốc từ video/audio/lời đọc.",
                "Cách làm: mở Phụ đề / Dịch / Lồng tiếng, gửi video hoặc audio, chọn tạo phụ đề gốc, nhận kết quả để kiểm tra.",
                "Cách tính: miễn phí nếu chỉ tạo phụ đề gốc.",
                "Ví dụ: tạo phụ đề gốc cho video rõ tiếng = 0 Xu.",
            ]),
        ),
        (
            "translate_subtitle",
            "Dịch phụ đề",
            "\n".join([
                "🌐 <b>HƯỚNG DẪN DỊCH PHỤ ĐỀ</b>",
                "",
                "Dùng khi: anh/chị muốn chuyển phụ đề sang ngôn ngữ khác.",
                "Cách làm: gửi video/audio hoặc phụ đề, chọn ngôn ngữ đích, xem số ký tự tính phí, xem hóa đơn và xác nhận.",
                "Cách tính: 0.1 Xu / ký tự; trên 1.000 ký tự giảm 10%; trên 10.000 ký tự giảm 20%.",
                "Ví dụ: 2.000 ký tự = 200 Xu, giảm 10%, tổng còn 180 Xu.",
            ]),
        ),
        (
            "dub",
            "Lồng tiếng",
            "\n".join([
                "🎙 <b>HƯỚNG DẪN LỒNG TIẾNG</b>",
                "",
                "Dùng khi: anh/chị muốn tạo bản giọng đọc mới cho nội dung.",
                "Cách làm: gửi nội dung hoặc video, chọn giọng mặc định hoặc voice riêng, xem hóa đơn và xác nhận.",
                "Cách tính: giọng mặc định 0.05 Xu / ký tự; voice riêng 0.1 Xu / ký tự. Trên 1.000 ký tự giảm 10%, trên 10.000 ký tự giảm 20%.",
                "Ví dụ: lồng tiếng giọng mặc định 2.000 ký tự = 100 Xu, giảm 10%, tổng còn 90 Xu.",
            ]),
        ),
        (
            "subtitle_dub",
            "Phụ đề / Dịch / Lồng tiếng",
            "\n".join([
                "📝 <b>HƯỚNG DẪN PHỤ ĐỀ / DỊCH / LỒNG TIẾNG</b>",
                "",
                "Bạn có thể dùng:",
                "• Tạo phụ đề từ video hoặc audio.",
                "• Dịch nội dung sang ngôn ngữ khác.",
                "• Lồng tiếng lại video bằng giọng phù hợp.",
                "• Tạo phụ đề + lồng tiếng trong cùng quy trình.",
                "",
                "Giá cần nhớ:",
                "• Tạo phụ đề gốc tự động: miễn phí.",
                "• Dịch phụ đề: 0.1 Xu / ký tự.",
                "• Lồng tiếng giọng mặc định: 0.05 Xu / ký tự.",
                "• Lồng tiếng voice riêng: 0.1 Xu / ký tự.",
                "",
                "Ví dụ phụ đề + lồng tiếng: dịch phụ đề 2.000 ký tự = 180 Xu; lồng tiếng giọng mặc định 2.000 ký tự = 90 Xu; tổng 270 Xu.",
                MAINTENANCE_NOTICE,
            ]),
        ),
        (
            "image_ai",
            "Tạo/chỉnh ảnh",
            "\n".join([
                "🖼 <b>HƯỚNG DẪN TẠO/CHỈNH ẢNH</b>",
                "",
                "Dùng khi: anh/chị cần ảnh sản phẩm, ảnh quảng cáo, ảnh minh họa, ảnh dùng làm khung cho video.",
                "",
                "Cách làm:",
                "1. Mở mục Tạo ảnh.",
                "2. Gửi mô tả ảnh: sản phẩm, bối cảnh, ánh sáng, màu sắc, bố cục, tỉ lệ và phong cách.",
                "3. Chọn gói ảnh theo nhu cầu.",
                "4. Xem hóa đơn và xác nhận.",
                "5. Nhận ảnh trong bot, tải về hoặc dùng tiếp để tạo video.",
                "",
                "Bảng giá tạo ảnh:",
                "• Tiết kiệm — 50 Xu.",
                "• Chuẩn — 150 Xu.",
                "• Chuẩn + bảo hành — 200 Xu.",
                "• Phổ thông — 300 Xu.",
                "• Phổ thông + bảo hành — 400 Xu.",
                "• Cao — 500 Xu.",
                "• Cao + bảo hành — 600 Xu.",
                "",
                "Ví dụ: chọn gói ảnh 200 Xu để tạo ảnh sản phẩm. Nếu ảnh không tạo được hợp lệ, hệ thống không trừ Xu.",
            ]),
        ),
        (
            "own_resources",
            "Dùng tài nguyên tự có",
            "\n".join([
                "🎁 <b>HƯỚNG DẪN DÙNG TÀI NGUYÊN TỰ CÓ</b>",
                "",
                "Dùng khi: anh/chị đã có ảnh, nhạc, voice/audio, logo hoặc nội dung riêng.",
                "",
                "Cách làm:",
                "1. Gửi tài nguyên vào đúng bước hệ thống yêu cầu.",
                "2. Chọn dùng tài nguyên đã gửi.",
                "3. Xem hóa đơn nếu có phần xử lý mới.",
                "4. Xác nhận trước khi xử lý.",
                "",
                "Cách tính: tài nguyên tự có không tính phí tạo mới. Nếu yêu cầu TOAN AAS tạo mới ảnh, nhạc, voice, phụ đề dịch, lồng tiếng hoặc video thì phần tạo mới tính theo bảng giá tương ứng.",
                "Ví dụ: dùng ảnh do anh/chị gửi lên trong video không tính phí tạo ảnh.",
            ]),
        ),
        (
            "credits",
            "Nạp Xu và xem hóa đơn",
            "\n".join([
                "💰 <b>HƯỚNG DẪN XU, HÓA ĐƠN VÀ BẢNG GIÁ</b>",
                "",
                "Quy đổi: 1 Xu = 100đ. Ví dụ 1.000 Xu tương đương 100.000đ giá trị sử dụng nội bộ trong TOAN AAS.",
                "",
                "Cách nạp Xu:",
                "1. Gõ /naptien.",
                "2. Chọn mệnh giá.",
                "3. Thanh toán theo hướng dẫn trong bot.",
                "4. Gõ /profile để kiểm tra số dư.",
                "",
                "Cách xem hóa đơn:",
                "1. Chọn công cụ cần dùng.",
                "2. Nhập nội dung hoặc chọn gói.",
                "3. Xem tổng Xu, chiết khấu nếu có và nút xác nhận.",
                "4. Chỉ xác nhận khi nội dung và giá đã đúng.",
                "",
                "Khuyến mãi nạp tiền chỉ áp dụng cho PayOS hoặc chuyển khoản ngân hàng Việt Nam nếu chương trình đang mở.",
                "Không áp dụng cho Zalo/MoMo hoặc kênh nạp quốc tế.",
            ]),
        ),
        (
            "faq",
            "FAQ / Hoàn Xu",
            "\n".join([
                "❓ <b>FAQ / HOÀN XU</b>",
                "",
                "1. Mở menu có bị trừ Xu không? Không.",
                "2. Khi nào TOAN AAS trừ Xu? Sau khi anh/chị xem hóa đơn và xác nhận bước có phí.",
                "3. Khi nào được hoàn Xu? Nếu đã trừ Xu nhưng lỗi trước khi có kết quả hợp lệ theo chính sách.",
                "4. Thiếu Xu thì sao? Bot sẽ báo thiếu Xu và hướng dẫn nạp thêm.",
                "5. Có nên bấm tạo nhiều lần khi đang chờ không? Không nên; hãy chờ kết quả hoặc liên hệ hỗ trợ.",
                "6. Cần hỗ trợ thì gửi gì? Gửi ID Telegram, ảnh chụp màn hình, thời gian giao dịch hoặc nội dung yêu cầu gần nhất.",
            ]),
        ),
    ]


def guide_index_lines() -> list[str]:
    lines = [
        "📚 <b>HƯỚNG DẪN TOAN AAS</b>",
        "",
        "Chọn mục bạn muốn xem:",
        "",
    ]
    for idx, (_key, title, _body) in enumerate(customer_guide_sections(), start=1):
        lines.append(f"{idx}. {html.escape(title)} — /huongdan {idx}")
    lines.extend([
        "",
        "Người mới nên bắt đầu với /huongdan 1.",
        CONFIRM_GATE_COPY,
    ])
    return lines


def guide_lines(section: str = "") -> list[str]:
    raw = (section or "").strip().lower()
    sections = customer_guide_sections()
    aliases = {
        "guided_video": "video_ai",
        "trend": "video_ai",
        "music_add": "audio",
        "music": "audio",
        "voice": "audio",
        "amthanh": "audio",
        "phude": "subtitle_dub",
        "subtitle": "subtitle_dub",
        "translate": "subtitle_dub",
        "dub": "subtitle_dub",
        "dubbing": "subtitle_dub",
        "banggia": "credits",
        "pricing": "credits",
        "topup": "credits",
        "xu": "credits",
        "refund": "faq",
    }
    raw = aliases.get(raw, raw)
    if raw.isdigit():
        idx = int(raw)
        if 1 <= idx <= len(sections):
            key, title, body = sections[idx - 1]
            return [f"📘 <b>Hướng dẫn {idx}: {html.escape(title)}</b>", "", body, "", "Mục lục: /huongdan"]
    for idx, (key, title, body) in enumerate(sections, start=1):
        if key == raw:
            return [f"📘 <b>Hướng dẫn {idx}: {html.escape(title)}</b>", "", body, "", "Mục lục: /huongdan"]
    return guide_index_lines()


def all_guide_lines() -> list[str]:
    lines = guide_index_lines()
    for idx, (key, _title, _body) in enumerate(customer_guide_sections(), start=1):
        lines.extend(["", "-----", ""])
        lines.extend(guide_lines(str(idx)))
    return lines


def pricing_markdown(context: dict | None = None) -> str:
    return html_lines_to_markdown(all_pricing_lines(context))


def guide_markdown() -> str:
    return html_lines_to_markdown(all_guide_lines())
