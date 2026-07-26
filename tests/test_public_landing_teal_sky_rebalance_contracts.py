"""Contracts for the public TOAN AAS teal--sky landing rebalance."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
LANDING = (ROOT / "index.html").read_text(encoding="utf-8")


def test_landing_defines_the_approved_semantic_teal_sky_roles() -> None:
    for token in (
        "--teal-action: #0f766e;",
        "--teal-brand: #14b8a6;",
        "--sky-context: #0284c7;",
        "--canvas: #f4fbfc;",
        "--ink: #083344;",
        "--muted: #486b75;",
        "--surface: #ffffff;",
        "--line: #d7ecef;",
    ):
        assert token in LANDING


def test_landing_keeps_light_sky_stage_markers_and_contextual_sky_focus() -> None:
    assert ".preview-stages div:nth-child(2) b { background: var(--sky-400); }" in LANDING
    assert ".process-step:nth-child(2) .process-step-number { background: var(--sky-400); }" in LANDING
    assert ":focus-visible { outline: 3px solid var(--sky-context); outline-offset: 3px; }" in LANDING
    assert "border-color: var(--sky-context);" in LANDING


def test_landing_rebalances_the_shared_desktop_rail_and_hero_geometry() -> None:
    assert "width: min(1240px, calc(100% - 48px));" in LANDING
    assert "grid-template-columns: minmax(0, 1.08fr) minmax(0, .92fr);" in LANDING
    assert "gap: clamp(28px, 4vw, 56px);" in LANDING
    assert "minmax(0, 420px)" not in LANDING
    assert "overflow-x: clip;" in LANDING
    assert re.search(
        r"@media \(max-width: 980px\) \{.*?\.hero-grid, \.lead-layout \{ "
        r"grid-template-columns: minmax\(0, 1fr\); \}",
        LANDING,
        flags=re.DOTALL,
    )


def test_primary_actions_keep_white_text_on_the_teal_action_role() -> None:
    primary = re.search(r"\.button--primary\s*\{(?P<rules>[^}]*)\}", LANDING, flags=re.DOTALL)
    interactive = re.search(
        r"\.button--primary:hover:not\(:disabled\),\s*"
        r"\.button--primary:focus-visible\s*\{(?P<rules>[^}]*)\}",
        LANDING,
        flags=re.DOTALL,
    )

    assert primary is not None
    assert "color: var(--surface);" in primary.group("rules")
    assert "background: var(--teal-action);" in primary.group("rules")
    assert interactive is not None
    assert "color: var(--surface);" in interactive.group("rules")
    assert "background: var(--teal-action);" in interactive.group("rules")


def test_landing_preserves_workspace_telegram_and_lead_authority() -> None:
    assert 'href="https://app.toanaas.vn/login"' in LANDING
    assert 'href="https://t.me/toanaasbot"' in LANDING

    form = re.search(r'<form\b[^>]*\bid="lead-form"[^>]*>', LANDING)
    assert form is not None
    assert re.search(r'\bmethod="post"', form.group(0))
    assert "novalidate" not in form.group(0)

    assert "fetch('/lead'" in LANDING
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


def test_landing_preserves_canonical_topics_and_three_locale_fixed_labels() -> None:
    select = re.search(r'<select id="lead-topic".*?</select>', LANDING, flags=re.DOTALL)
    assert select is not None
    assert re.findall(
        r'<option value="([^"]+)"[^>]*data-i18n="topic\.[^"]+"',
        select.group(0),
    ) == [
        "Video AI",
        "Studio âm thanh",
        "Hình ảnh AI",
        "Tài liệu / PDF",
        "Marketing automation",
        "Nạp Xu / hỗ trợ tài khoản",
    ]

    for key in ("hero.title", "hero.workspace", "workflow.title", "companion.title", "lead.submit"):
        assert LANDING.count(f'"{key}":') == 3


def test_landing_keeps_url_locale_display_and_escape_focus_restoration() -> None:
    assert 'const localeFromUrl = new URLSearchParams(window.location.search).get("lang");' in LANDING
    assert 'const locale = supportedLocales.has(localeFromUrl) ? localeFromUrl : "vi";' in LANDING
    assert 'document.documentElement.lang = locale === "zh" ? "zh-CN" : locale;' in LANDING
    assert 'document.title = copy["meta.title"];' in LANDING
    assert "localStorage" not in LANDING

    assert 'if (restoreFocus && wasOpen) menuToggle.focus();' in LANDING
    assert 'if (event.key === "Escape" && header.getAttribute("data-menu-open") === "true") {' in LANDING
    assert 'closeMenu({ restoreFocus: true });' in LANDING


def test_mobile_hash_navigation_moves_focus_to_the_visible_destination() -> None:
    """Closing the responsive menu must not leave focus on its hidden link."""

    assert "const focusHashDestination = function (link)" in LANDING
    assert "link.origin !== window.location.origin" in LANDING
    assert "link.pathname !== window.location.pathname" in LANDING
    assert "const target = document.getElementById(link.hash.slice(1));" in LANDING
    assert 'destination.setAttribute("tabindex", "-1");' in LANDING
    assert "destination.focus({ preventScroll: true });" in LANDING
    assert "link.addEventListener(\"click\", function (event) {" in LANDING
    assert "focusHashDestination(link);" in LANDING
