from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_public_guide_docs_and_landing_links_match_current_public_scope():
    guide_md = (ROOT / "docs" / "public" / "TOAN_AAS_HUONG_DAN_SU_DUNG_CHO_KHACH_V2.md").read_text(encoding="utf-8")
    index_html = (ROOT / "index.html").read_text(encoding="utf-8")

    assert "23/06/2026" in guide_md
    assert "1 Xu = 100đ" in guide_md
    assert "Tiết kiệm: 50 Xu" in guide_md
    assert "Cao + bảo hành: 600 Xu" in guide_md
    assert "Trải nghiệm: 200 Xu" in guide_md
    assert "Premium: 1500 Xu" in guide_md
    assert "Khuyến mãi nạp tiền chỉ áp dụng cho PayOS hoặc chuyển khoản ngân hàng Việt Nam" in guide_md
    for public_link in (
        "https://app.toanaas.vn/login",
        "https://t.me/toanaasbot",
        "/guide",
        "/pricing",
        "/download/bang-gia-toan-aas.md",
        "/download/huong-dan-su-dung-toan-aas.md",
        "/download/huong-dan-toan-aas.docx",
        "/download/dieu-khoan-su-dung-toan-aas.pdf",
    ):
        assert public_link in index_html
    assert "Hướng dẫn V2 cập nhật" not in index_html
    assert "1 Xu = 100đ" not in index_html
    assert "Bảng giá tạo ảnh: 50, 150, 200, 300, 400, 500 và 600 Xu." not in index_html
    assert "Bảng giá video: 200, 300, 400, 500, 600, 800, 1000, 1200 và 1500 Xu." not in index_html
