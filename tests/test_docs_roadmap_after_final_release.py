from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_public_guide_docs_updated_without_flow_changes():
    guide_md = (ROOT / "docs" / "public" / "TOAN_AAS_HUONG_DAN_SU_DUNG_CHO_KHACH_V2.md").read_text(encoding="utf-8")
    index_html = (ROOT / "index.html").read_text(encoding="utf-8")

    assert "23/06/2026" in guide_md
    assert "Hướng dẫn V2 cập nhật" in index_html
    assert "1 Xu = 100đ" in guide_md
    assert "1 Xu = 100đ" in index_html
    assert "Tiết kiệm: 50 Xu" in guide_md
    assert "Cao + bảo hành: 600 Xu" in guide_md
    assert "Trải nghiệm: 200 Xu" in guide_md
    assert "Premium: 1500 Xu" in guide_md
    assert "Bảng giá tạo ảnh: 50, 150, 200, 300, 400, 500 và 600 Xu." in index_html
    assert "Bảng giá video: 200, 300, 400, 500, 600, 800, 1000, 1200 và 1500 Xu." in index_html
    assert "Khuyến mãi nạp tiền chỉ áp dụng cho PayOS hoặc chuyển khoản ngân hàng Việt Nam" in guide_md
