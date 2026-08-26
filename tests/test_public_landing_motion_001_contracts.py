import re
from pathlib import Path


LANDING = (Path(__file__).resolve().parents[1] / "index.html").read_text(encoding="utf-8")
HERO_SELECTORS = [
    ".hero-copy > h1",
    ".hero-copy > p:not(.hero-note)",
    ".hero-actions",
    ".hero-note",
    ".workflow-preview",
]


def test_head_prepaint_marker_is_progressive_and_has_a_fail_safe():
    head, body = LANDING.split("<body", maxsplit=1)

    assert "motion-prepaint" not in body.split(">", maxsplit=1)[0]
    assert re.search(
        r"<script>\s*\(function \(\) \{.*?"
        r"const root = document\.documentElement;.*?"
        r"root\.classList\.add\(\"motion-prepaint\"\);.*?"
        r"window\.setTimeout\(function \(\) \{\s*"
        r"root\.classList\.remove\(\"motion-prepaint\"\);\s*"
        r"\},\s*1200\);.*?</script>",
        head,
        re.DOTALL,
    )
    assert 'class="motion-pending"' not in LANDING
    assert "class='motion-pending'" not in LANDING
    assert not re.search(r"(?:html|body)\s*\{[^}]*opacity\s*:\s*0", LANDING)
    prepaint_selectors = r",\s*".join(
        re.escape("html.motion-prepaint " + selector) for selector in HERO_SELECTORS
    )
    assert re.search(
        r"@media \(min-width:\s*981px\) and "
        r"\(prefers-reduced-motion:\s*no-preference\)\s*\{\s*"
        + prepaint_selectors
        + r"\s*\{\s*opacity:\s*0;\s*transform:\s*translateY\(20px\);\s*\}",
        LANDING,
        re.DOTALL,
    )


def test_motion_css_locks_exact_timings_fill_and_transform_only():
    assert re.search(
        r"\.motion-reveal-hero\s*\{\s*animation:\s*fade-up 520ms "
        r"cubic-bezier\(\.22,\s*1,\s*\.36,\s*1\) both !important;\s*\}",
        LANDING,
    )
    assert re.search(
        r"\.motion-reveal\s*\{\s*animation:\s*fade-up 480ms "
        r"cubic-bezier\(\.22,\s*1,\s*\.36,\s*1\) both !important;\s*\}",
        LANDING,
    )
    assert re.search(
        r"@keyframes fade-up\s*\{\s*"
        r"from\s*\{\s*opacity:\s*0;\s*transform:\s*translateY\(20px\);\s*\}\s*"
        r"to\s*\{\s*opacity:\s*1;\s*transform:\s*translateY\(0\);\s*\}\s*\}",
        LANDING,
    )
    keyframes = re.search(r"@keyframes fade-up\s*\{.*?\n\s*\}", LANDING, re.DOTALL).group(0)
    assert not re.search(r"\b(?:width|height|top|left|padding|margin)\s*:", keyframes)


def test_hero_has_exact_five_non_nested_items_and_an_800ms_budget():
    selector_match = re.search(
        r"const heroSelectors = Object\.freeze\(\[(.*?)\]\);", LANDING, re.DOTALL
    )
    delay_match = re.search(
        r"const heroDelays = Object\.freeze\(\[(.*?)\]\);", LANDING, re.DOTALL
    )

    assert selector_match is not None
    assert delay_match is not None
    assert re.findall(r'"([^"]+)"', selector_match.group(1)) == HERO_SELECTORS
    delays = [int(value) for value in re.findall(r"\d+", delay_match.group(1))]
    assert delays == [0, 80, 160, 240, 240]
    assert len(delays) == len(HERO_SELECTORS) == 5
    assert max(delays) <= 280
    assert max(delays) + 520 <= 800
    assert "document.querySelector('.hero-copy')" not in LANDING
    assert 'document.querySelector(".hero-copy")' not in LANDING
    assert "index * 80" not in LANDING
    assert re.search(
        r"const heroItems = heroSelectors\.map\(\(selector\) => "
        r"document\.querySelector\(selector\)\);",
        LANDING,
    )


def test_hero_is_armed_before_marker_release_and_cleans_up_once():
    hero_block = re.search(
        r"const heroSelectors = .*?releasePrepaint\(\);", LANDING, re.DOTALL
    )

    assert hero_block is not None
    block = hero_block.group(0)
    assert block.index("classList.add('motion-reveal-hero')") < block.index(
        "releasePrepaint();"
    )
    assert re.search(
        r"element\.addEventListener\('animationend',\s*\(\) => \{\s*"
        r"clearMotionState\(element, 'motion-reveal-hero'\);\s*"
        r"\},\s*\{ once:\s*true \}\);",
        block,
    )
    assert re.search(
        r"const clearMotionState = \(element, className\) => \{\s*"
        r"element\.classList\.remove\(className\);\s*"
        r"element\.style\.animationDelay = '';\s*\};",
        LANDING,
    )


def test_sections_are_default_visible_observed_once_and_fail_open():
    assert re.search(
        r"let sectionObserver = null;\s*try \{\s*"
        r"sectionObserver = new IntersectionObserver\(",
        LANDING,
    )
    assert re.search(
        r"if \(!entry\.isIntersecting\) return;.*?"
        r"element\.classList\.remove\('motion-pending'\);.*?"
        r"element\.classList\.add\('motion-reveal'\);.*?"
        r"sectionObserver\.unobserve\(element\);",
        LANDING,
        re.DOTALL,
    )
    assert re.search(
        r"element\.addEventListener\('animationend',\s*\(\) => \{\s*"
        r"clearMotionState\(element, 'motion-reveal'\);\s*"
        r"\},\s*\{ once:\s*true \}\);",
        LANDING,
    )
    assert re.search(
        r"if \(entry\.boundingClientRect\.top > viewportBottom\) \{.*?"
        r"element\.classList\.add\('motion-pending'\);\s*return;",
        LANDING,
        re.DOTALL,
    )
    assert re.search(
        r"document\.querySelectorAll\(.*?\)\.forEach\(\(element\) => \{\s*try \{\s*"
        r"sectionObserver\.observe\(element\);\s*\} catch \(error\) \{\s*"
        r"clearMotionState\(element, 'motion-pending'\);",
        LANDING,
        re.DOTALL,
    )
    assert re.search(
        r"\} catch \(error\) \{\s*sectionObserver = null;\s*\}\s*"
        r"if \(sectionObserver\) \{",
        LANDING,
    )


def test_section_stagger_is_capped_at_six_items():
    assert re.search(
        r"const staggerIndex = Math\.min\(siblings\.indexOf\(element\), 5\);\s*"
        r"element\.style\.animationDelay = "
        r"`\$\{Math\.max\(staggerIndex, 0\) \* 70\}ms`;",
        LANDING,
    )


def test_sections_use_async_initial_entries_without_sync_geometry_reads():
    section_match = re.search(
        r"// 2\. Sections(.*?)// 3\. Parallax",
        LANDING,
        re.DOTALL,
    )

    assert section_match is not None
    section = section_match.group(1)
    assert "getBoundingClientRect" not in section
    assert "const initializedSections = new WeakSet();" in section
    assert section.count("element.classList.add('motion-pending')") == 1
    initial_match = re.search(
        r"const element = entry\.target;\s*"
        r"if \(!initializedSections\.has\(element\)\) \{\s*"
        r"initializedSections\.add\(element\);\s*"
        r"if \(entry\.isIntersecting\) \{\s*"
        r"sectionObserver\.unobserve\(element\);\s*return;\s*\}\s*"
        r"const viewportBottom = entry\.rootBounds "
        r"\? entry\.rootBounds\.bottom : window\.innerHeight;\s*"
        r"if \(entry\.boundingClientRect\.top > viewportBottom\) \{(.*?)"
        r"return;\s*\}\s*sectionObserver\.unobserve\(element\);\s*return;\s*\}",
        section,
        re.DOTALL,
    )

    assert initial_match is not None
    below_fold_branch = initial_match.group(1)
    assert "element.style.animationDelay" in below_fold_branch
    assert "element.classList.add('motion-pending')" in below_fold_branch
    assert "sectionObserver.unobserve" not in below_fold_branch
    assert re.search(
        r"if \(!entry\.isIntersecting\) return;\s*"
        r"element\.classList\.remove\('motion-pending'\);\s*"
        r"element\.classList\.add\('motion-reveal'\);\s*"
        r"sectionObserver\.unobserve\(element\);",
        section,
    )
    assert re.search(
        r"if \(sectionObserver\) \{\s*document\.querySelectorAll\("
        r"'\.section-heading, \.process-step, \.companion-card, \.capability, "
        r"\.trust-list article, \.lead-form, \.final-cta'\)"
        r"\.forEach\(\(element\) => \{\s*try \{\s*"
        r"sectionObserver\.observe\(element\);\s*\} catch \(error\) \{\s*"
        r"clearMotionState\(element, 'motion-pending'\);",
        section,
    )


def test_parallax_uses_exact_media_clamp_and_one_pending_frame():
    assert (
        "window.matchMedia('(min-width: 981px) and (pointer: fine) and "
        "(prefers-reduced-motion: no-preference)')" in LANDING
    )
    pointer_block = re.search(
        r"const onPointerMove = \(event\) => \{(.*?)\n\s*\};\s*"
        r"const setParallaxActive",
        LANDING,
        re.DOTALL,
    )

    assert pointer_block is not None
    block = pointer_block.group(1)
    assert "if (parallaxFrame) return;" in block
    assert block.count("window.requestAnimationFrame") == 1
    assert block.index("window.requestAnimationFrame") < block.index(
        "preview.style.transform"
    )
    assert len(re.findall(r"Math\.max\(-10, Math\.min\(10,", block)) == 2
    assert "window.addEventListener('pointermove', onPointerMove" in LANDING
    assert "window.removeEventListener('pointermove', onPointerMove)" in LANDING
    assert "window.cancelAnimationFrame(parallaxFrame)" in LANDING
    assert "preview.style.transform = 'translate(0px, 0px)'" in LANDING


def test_mobile_and_reduced_motion_neutralize_marker_and_motion():
    neutral_rule = (
        r"html\.motion-prepaint .*?\.motion-pending,\s*\.motion-reveal,\s*"
        r"\.motion-reveal-hero\s*\{\s*animation:\s*none !important;\s*"
        r"opacity:\s*1 !important;\s*transform:\s*none !important;\s*\}"
    )
    assert re.search(
        r"@media \(max-width:\s*980px\)\s*\{\s*" + neutral_rule, LANDING
    )
    assert re.search(
        r"@media \(prefers-reduced-motion:\s*reduce\)\s*\{\s*" + neutral_rule,
        LANDING,
    )
    assert re.search(
        r"if \(presentationDisabled\.matches\) \{\s*"
        r"releasePrepaint\(\);\s*return;\s*\}",
        LANDING,
    )


def test_banned_motion_patterns_are_absent():
    assert not re.search(r"transition\s*:\s*all\b", LANDING)
    assert "preloader" not in LANDING.lower()
    assert not re.search(r"animation(?:-iteration-count)?\s*:\s*infinite", LANDING)


def test_workspace_telegram_and_lead_authority_remain_exact():
    assert (
        '<a class="button button--primary" href="https://app.toanaas.vn/login" '
        'data-i18n="hero.workspace">' in LANDING
    )
    assert (
        '<a class="button" href="https://t.me/toanaasbot" target="_blank" '
        'rel="noopener" data-i18n="hero.telegram">' in LANDING
    )
    assert '<form id="lead-form" class="lead-form" method="post">' in LANDING
    assert re.search(
        r"fetch\('/lead',\s*\{\s*method:\s*\"POST\",\s*"
        r"headers:\s*\{\s*\"Content-Type\":\s*\"application/json\"\s*\},\s*"
        r"body:\s*JSON\.stringify\(\{.*?"
        r"source:\s*\"landing-clean-clear-v2\"\s*\}\)\s*\}\);",
        LANDING,
        re.DOTALL,
    )
