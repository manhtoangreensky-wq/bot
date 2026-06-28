"""Export public pricing and guide Markdown from the shared copy source."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.pricing_guide_content import (  # noqa: E402
    GUIDE_DOWNLOAD_FILENAME,
    PRICING_DOWNLOAD_FILENAME,
    guide_markdown,
    pricing_markdown,
)


PUBLIC_DIR = ROOT / "docs" / "public"


def guide_v2_markdown() -> str:
    return (
        "# TOAN AAS - Hướng dẫn sử dụng cho khách hàng\n\n"
        "**Phiên bản:** V2\n\n"
        "**Cập nhật nền:** 23/06/2026\n\n"
        "**Cập nhật bảng giá/hướng dẫn:** 28/06/2026\n\n"
        "**Bot Telegram:** @toanaasbot\n\n"
        "**Website:** www.toanaas.vn\n\n"
        "**Định hướng:** Công cụ AI hỗ trợ sáng tạo nội dung và công việc hằng ngày\n\n"
        "TOAN AAS giúp anh/chị tạo ảnh, video, âm thanh, phụ đề, dịch, lồng tiếng, xử lý tài liệu và xem chi phí trước khi dùng.\n\n"
        "## Bảng giá nhanh\n\n"
        "- Bảng giá tạo ảnh: 50, 150, 200, 300, 400, 500 và 600 Xu.\n"
        "- Bảng giá video: 200, 300, 400, 500, 600, 800, 1000, 1200 và 1500 Xu.\n"
        "- Tiết kiệm: 50 Xu.\n"
        "- Cao + bảo hành: 600 Xu.\n"
        "- Trải nghiệm: 200 Xu.\n"
        "- Pro Plus: 1200 Xu.\n"
        "- Premium: 1500 Xu.\n"
        "- Khuyến mãi nạp tiền chỉ áp dụng cho PayOS hoặc chuyển khoản ngân hàng Việt Nam nếu chương trình đang mở.\n\n"
        "## Hướng dẫn chi tiết\n\n"
        f"{guide_markdown()}\n"
        "## Bảng giá chi tiết\n\n"
        f"{pricing_markdown()}"
    )


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def main() -> None:
    write_text(PUBLIC_DIR / PRICING_DOWNLOAD_FILENAME, pricing_markdown())
    write_text(PUBLIC_DIR / GUIDE_DOWNLOAD_FILENAME, guide_markdown())
    write_text(PUBLIC_DIR / "TOAN_AAS_HUONG_DAN_SU_DUNG_CHO_KHACH_V2.md", guide_v2_markdown())


if __name__ == "__main__":
    main()
