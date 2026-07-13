from pathlib import Path

from services import pricing_guide_content, product_video_duration_decision


ROOT = Path(__file__).resolve().parents[1]
GUIDE_SURFACES = (
    ROOT / "bot.py",
    ROOT / "services" / "pricing_guide_content.py",
    ROOT / "docs" / "public" / "TOAN_AAS_HUONG_DAN_SU_DUNG_CHO_KHACH_V2.md",
    ROOT / "docs" / "public" / "huong-dan-su-dung-toan-aas.md",
)


def _guide_section(path: Path) -> str:
    source = path.read_text(encoding="utf-8")
    start = source.index("Quy trình tạo video:")
    end = source.index("Bảng giá video theo gói:", start)
    return source[start:end]


def test_public_product_video_guides_use_eight_seconds_up_to_160_seconds():
    expected = (
        "1 cảnh khoảng 8 giây",
        "3 cảnh khoảng 24 giây",
        "5 cảnh khoảng 40 giây",
        "10 cảnh khoảng 80 giây",
        "20 cảnh khoảng 160 giây",
    )
    forbidden = (
        "1 cảnh khoảng 6 giây",
        "3 cảnh khoảng 18 giây",
        "5 cảnh khoảng 30 giây",
        "10 cảnh khoảng 60 giây",
        "20 cảnh khoảng 120 giây",
    )

    for path in GUIDE_SURFACES:
        source = path.read_text(encoding="utf-8")
        for line in expected:
            assert line in source, f"{path.name} is missing: {line}"
        for line in forbidden:
            assert line not in source, f"{path.name} still exposes stale Product Video copy: {line}"


def test_public_product_video_guide_keeps_scene_first_sequence():
    expected_steps = (
        "Chọn chủ đề hoặc nguồn video",
        "Chọn số cảnh trước",
        "Chọn profile và ngữ cảnh",
        "Kiểm tra kế hoạch và prompt riêng",
        "Chọn gói chất lượng video",
        "Xem tổng chi phí",
    )

    for path in GUIDE_SURFACES:
        section = _guide_section(path)
        positions = [section.index(step) for step in expected_steps]
        assert positions == sorted(positions), f"{path.name} does not preserve the SCENE1 order"


def test_product_video_duration_contract_has_no_public_six_to_eight_range():
    duration_source = (ROOT / "services" / "product_video_duration_decision.py").read_text(encoding="utf-8")
    bot_source = (ROOT / "bot.py").read_text(encoding="utf-8")

    assert 'TASK3D_SCENE_SECONDS = 8' in bot_source
    assert "1 cảnh = 1 clip AI khoảng 8s" in duration_source
    assert "1 cảnh = 1 clip AI khoảng 6-8s" not in duration_source


def test_shared_guide_and_duration_services_render_the_same_contract():
    video_guide = next(
        content
        for key, _title, content in pricing_guide_content.customer_guide_sections()
        if key == "video_ai"
    )
    duration_copy = "\n".join(product_video_duration_decision.public_contract_lines())

    assert "Chọn số cảnh trước" in video_guide
    assert "20 cảnh khoảng 160 giây" in video_guide
    assert "1 cảnh = 1 clip AI khoảng 8s" in duration_copy
