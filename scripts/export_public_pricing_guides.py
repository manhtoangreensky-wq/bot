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
    public_product_video_catalog,
    video_multiscene_discount_lines,
)
from services import video_ai_real_pricing  # noqa: E402


PUBLIC_DIR = ROOT / "docs" / "public"


def _image_price_values() -> str:
    values = sorted({int(entry["unit_xu"]) for entry in video_ai_real_pricing.public_image_quality_catalog()})
    return " / ".join(str(value) for value in values)


def guide_v2_markdown() -> str:
    video_prices = "".join(
        (
            f"- {row['name']} — {int(row['seconds'])} giây/cảnh: "
            f"{int(row['unit_xu']):,} Xu/cảnh.\n"
        ).replace(",", ".")
        for row in public_product_video_catalog()
    )
    video_discounts = "".join(
        f"- {line.removeprefix('• ')}\n" for line in video_multiscene_discount_lines()
    )
    return (
        "# TOAN AAS - Hướng dẫn sử dụng cho khách hàng\n\n"
        "**Phiên bản:** V2\n\n"
        "**Cập nhật nền:** 23/06/2026\n\n"
        "**Cập nhật bảng giá/hướng dẫn:** 21/08/2026\n\n"
        "**Bot Telegram:** @toanaasbot\n\n"
        "**Website:** www.toanaas.vn\n\n"
        "**Định hướng:** Công cụ AI hỗ trợ sáng tạo nội dung và công việc hằng ngày\n\n"
        "TOAN AAS giúp anh/chị tạo ảnh, video, âm thanh, phụ đề, dịch, lồng tiếng, xử lý tài liệu và xem chi phí trước khi dùng.\n\n"
        "## Bảng giá nhanh\n\n"
        f"- Bảng giá tạo ảnh: {_image_price_values()} Xu/ảnh.\n"
        "### Video AI theo cảnh\n\n"
        f"{video_prices}\n"
        "Khuyến mãi chỉ áp dụng cho đơn Video nhiều cảnh từ 2 cảnh; add-on tính riêng.\n\n"
        f"{video_discounts}\n"
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
