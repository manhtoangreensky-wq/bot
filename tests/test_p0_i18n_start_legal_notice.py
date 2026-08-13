from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COPY_SOURCE = (ROOT / "services" / "pricing_guide_content.py").read_text(encoding="utf-8")
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")
LOCALES = {"vi", "en", "zh", "es", "pt", "fr", "de", "ja", "ko", "hi", "ar", "ru", "tr", "th", "fil", "it", "id"}
COMMANDS = {"/legal", "/privacy", "/dieukhoan_xu", "/refund_policy"}


def _literal_assignment(source: str, name: str):
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError(f"missing assignment: {name}")


def _source_between(source: str, start: str, end: str) -> str:
    begin = source.index(start)
    finish = source.index(end, begin)
    return source[begin:finish]


def test_start_legal_notice_is_native_and_complete_for_all_supported_locales():
    table = _literal_assignment(COPY_SOURCE, "_PUBLIC_START_LEGAL_COPY")
    assert set(table) == LOCALES
    assert len(set(table.values())) == len(LOCALES)
    for locale, notice in table.items():
        assert notice.strip()
        assert COMMANDS.issubset(set(notice.split())) or all(command in notice for command in COMMANDS), locale
        if locale != "en":
            assert notice != table["en"]
        if locale != "vi":
            assert notice != table["vi"]


def test_active_localized_start_renderer_appends_the_notice_without_route_changes():
    source = _source_between(BOT_SOURCE, "def localized_start_menu_text", "def public_back_keyboard")
    assert "copy['start_legal_notice']" in source
    assert "callback_data" not in source
