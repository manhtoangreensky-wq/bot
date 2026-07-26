"""Static contracts for the public TOAN AAS teal--sky landing."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
LANDING = (ROOT / "index.html").read_text(encoding="utf-8")


def test_public_landing_uses_the_shared_teal_sky_system_and_real_entry_points() -> None:
    for token in (
        "--teal-950: #062a36;",
        "--teal-500: #14b8a6;",
        "--sky-400: #38bdf8;",
        "--canvas: #f4fbfc;",
    ):
        assert token in LANDING

    assert 'href="https://app.toanaas.vn/login"' in LANDING
    assert 'href="https://t.me/toanaasbot"' in LANDING
    assert 'action="/lead"' not in LANDING  # JS keeps the existing JSON contract.
    assert "fetch('/lead'" in LANDING
    assert 'source: "landing-clean-clear-v2"' in LANDING
    assert "--success: #0f766e;" in LANDING


def test_public_landing_has_complete_vietnamese_english_chinese_display_copy() -> None:
    assert "const PUBLIC_COPY = Object.freeze({" in LANDING
    for locale in ('vi: Object.freeze({', 'en: Object.freeze({', 'zh: Object.freeze({'):
        assert locale in LANDING

    for key in (
        "nav.workspace",
        "hero.title",
        "workflow.title",
        "companion.title",
        "lead.submit",
        "lead.error",
    ):
        assert f'"{key}"' in LANDING

    assert "new URLSearchParams(window.location.search)" in LANDING
    assert "localStorage" not in LANDING


def test_public_landing_keeps_accessibility_and_mobile_boundaries_visible() -> None:
    for marker in (
        'class="skip-link"',
        'aria-label="Điều hướng chính"',
        'aria-controls="site-menu"',
        'aria-expanded="false"',
        'role="status" aria-live="polite"',
        "min-height: 44px;",
        "@media (prefers-reduced-motion: reduce)",
    ):
        assert marker in LANDING

    assert "grid-template-columns: minmax(0, 1fr);" in LANDING
    assert "overflow-x: clip;" in LANDING


def test_public_landing_does_not_reintroduce_fake_metrics_or_structural_emoji() -> None:
    assert "1 Xu =" not in LANDING
    assert "Video có 9 gói" not in LANDING
    assert re.search(r"[\U0001F300-\U0001FAFF]", LANDING) is None


def test_public_landing_preserves_the_existing_lead_payload_authority() -> None:
    payload = re.search(
        r"body: JSON\.stringify\(\{(?P<body>.*?)\}\)",
        LANDING,
        flags=re.DOTALL,
    )

    assert payload is not None
    fields = re.findall(r"^\s*(name|phone|services|note|source):", payload.group("body"), re.MULTILINE)
    assert fields == ["name", "phone", "services", "note", "source"]
    assert 'services: [String(data.get("topic") || "").trim()]' in payload.group("body")
    assert 'source: "landing-clean-clear-v2"' in payload.group("body")
    assert 'source: "public-teal-sky-landing"' not in payload.group("body")


def test_public_landing_lead_fallback_uses_post_and_native_validation() -> None:
    form = re.search(r'<form\b[^>]*\bid="lead-form"[^>]*>', LANDING)

    assert form is not None
    opening_tag = form.group(0)
    assert re.search(r'\bmethod="post"', opening_tag)
    assert "novalidate" not in opening_tag


def test_public_landing_keeps_canonical_lead_service_values_across_locales() -> None:
    expected_values = [
        "Video AI",
        "Studio âm thanh",
        "Hình ảnh AI",
        "Tài liệu / PDF",
        "Marketing automation",
        "Nạp Xu / hỗ trợ tài khoản",
    ]
    select = re.search(r'<select id="lead-topic".*?</select>', LANDING, flags=re.DOTALL)

    assert select is not None
    actual_values = re.findall(
        r'<option value="([^"]+)"[^>]*data-i18n="topic\.[^"]+"',
        select.group(0),
    )
    assert actual_values == expected_values
    for key in (
        "topic.videoAi",
        "topic.audioStudio",
        "topic.imageAi",
        "topic.documents",
        "topic.marketingAutomation",
        "topic.walletSupport",
    ):
        assert LANDING.count(f'"{key}":') == 3
    assert 'element.textContent = copy[key]' in LANDING
    assert 'setAttribute("value", copy[key])' not in LANDING


def test_public_landing_mobile_menu_uses_localized_open_close_copy_and_restores_focus() -> None:
    for copy in (
        '"nav.menuOpen": "Mở menu"',
        '"nav.menuClose": "Đóng menu"',
        '"nav.menuOpen": "Open menu"',
        '"nav.menuClose": "Close menu"',
        '"nav.menuOpen": "打开菜单"',
        '"nav.menuClose": "关闭菜单"',
    ):
        assert copy in LANDING

    assert 'data-i18n-aria="nav.menuOpen"' in LANDING
    assert 'const setMenuLabel = function (open)' in LANDING
    assert 'menuToggle.setAttribute("aria-label", copy[open ? "nav.menuClose" : "nav.menuOpen"]);' in LANDING
    assert 'if (restoreFocus && wasOpen) menuToggle.focus();' in LANDING
    assert 'if (event.key === "Escape" && header.getAttribute("data-menu-open") === "true") {' in LANDING
    assert 'closeMenu({ restoreFocus: true });' in LANDING


def test_public_landing_keeps_download_and_legal_resources_localized_in_footer() -> None:
    expected_resources = {
        "/download/bang-gia-toan-aas.md": "footer.downloadPricing",
        "/download/huong-dan-su-dung-toan-aas.md": "footer.downloadGuide",
        "/download/huong-dan-toan-aas.docx": "footer.downloadGuideDocx",
        "/download/dieu-khoan-su-dung-toan-aas.pdf": "footer.terms",
    }

    assert 'data-i18n="footer.resources"' in LANDING
    for href, key in expected_resources.items():
        assert f'href="{href}"' in LANDING
        assert f'"{key}":' in LANDING
        assert LANDING.count(f'"{key}":') == 3
