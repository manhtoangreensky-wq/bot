"""One place that decides how user text and paths enter an FFmpeg filtergraph.

Why this module exists
----------------------
A filtergraph is its own small language, parsed in three layers: `,` and `;`
separate filters, `:` separates a filter's options, and `'` quotes an option
value. Values were being wrapped in single quotes and "escaped" with
backslashes — `\\'`, `\\:`, `\\,`. Inside a single-quoted FFmpeg string a
backslash is **not** an escape character, so `\\'` reads as a literal backslash
followed by a quote that *closes the string*. Everything after it is parsed as
filtergraph syntax again, which is enough to append options or chain a whole
new filter such as `movie=` or `drawtext=textfile=`.

So escaping a quote is not possible here. The quote has to be gone before the
value is ever quoted. That is what `escape_filter_text` does, and it is why
`sanitize_overlay_text` runs at the point the text is captured as well: two
independent layers, either of which is sufficient on its own.

There is one more parser boundary: `:` separates filter options, and FFmpeg's
CLI accepts `/text=<path>` as "load this option value from a file".  Quoting
alone does not protect that boundary.  Every colon inside an option value must
therefore be escaped after user-provided backslashes have been removed.

`%` and `{}` are handled differently again: drawtext expands them at render
time, so callers pass `expansion=none` (see `DRAWTEXT_NO_EXPANSION`) rather
than trying to escape them.
"""

from __future__ import annotations

import os
import re

# Characters that can break out of a single-quoted filtergraph value, or that
# the parser treats specially before quoting is even considered.
_FILTER_BREAKOUT = "'\"\\"

# Control characters, including newline: a newline ends the value outright.
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")

# Typographic apostrophe. Vietnamese and English overlay text uses apostrophes;
# substituting keeps the text readable instead of silently deleting characters.
_SAFE_APOSTROPHE = "’"

DRAWTEXT_NO_EXPANSION = "expansion=none"

OVERLAY_TEXT_MAX_CHARS = 300


def sanitize_overlay_text(value: str, limit: int = OVERLAY_TEXT_MAX_CHARS) -> str:
    """Clean user text at the moment it is captured.

    Collapses whitespace, drops control characters, and replaces the quote and
    backslash forms that could later break out of a quoted filter value. Normal
    punctuation is kept at capture time so captions remain readable. The
    filter builder later escapes `:` for FFmpeg's option parser.
    """
    text = _CONTROL.sub(" ", str(value or ""))
    text = text.replace("'", _SAFE_APOSTROPHE).replace('"', "")
    text = text.replace("\\", "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[: max(1, int(limit or OVERLAY_TEXT_MAX_CHARS))]


def escape_filter_text(value: str) -> str:
    """Make text safe to place inside single quotes in a filtergraph.

    The quote and backslash are removed rather than escaped, because neither
    can be represented inside a single-quoted FFmpeg value.
    """
    text = _CONTROL.sub(" ", str(value or ""))
    text = text.replace("'", _SAFE_APOSTROPHE)
    for char in _FILTER_BREAKOUT:
        text = text.replace(char, "")
    # A bare colon ends the current filter option before the CLI's slash-option
    # loader is interpreted.  Escape it only after deleting attacker-supplied
    # backslashes, so every emitted escape is owned by this helper.
    return text.replace(":", r"\:")


def quote_filter_value(value: str) -> str:
    """Return an escaped value already wrapped in the quotes FFmpeg expects."""
    return "'" + escape_filter_text(value) + "'"


def escape_filter_path(path: str, *, resolve: bool = True) -> str:
    """Make a filesystem path safe for `subtitles=`, `fontfile=` and friends.

    Paths reach the same parser as text, so the same breakout characters have
    to go. A Windows drive letter still needs its colon escaped because the
    option parser splits on `:` before quoting is considered.
    """
    raw = str(path or "")
    if resolve and raw:
        try:
            raw = os.path.abspath(raw)
        except Exception:
            pass
    cleaned = _CONTROL.sub("", raw).replace("\\", "/")
    cleaned = cleaned.replace("'", "").replace('"', "")
    # Escape every colon, not only a Windows drive separator. A later colon in
    # an otherwise valid path can also start another filter option.
    return cleaned.replace(":", r"\:")


def quote_filter_path(path: str, *, resolve: bool = True) -> str:
    return "'" + escape_filter_path(path, resolve=resolve) + "'"


def drawtext_is_safe(fragment: str) -> bool:
    """True when a built drawtext fragment cannot escape its own quoting.

    Used by tests as an independent check on whatever the builders produced:
    every quote in the fragment must open or close a value, never appear
    inside one.
    """
    if fragment.count("'") % 2 != 0 or "\\'" in fragment:
        return False

    # Colons outside quotes are the builder's legitimate option separators.
    # Inside a quoted value, an unescaped colon is a parser escape and can make
    # `/text=<path>` become FFmpeg's file-value loader.
    in_quote = False
    preceding_backslashes = 0
    for char in fragment:
        if char == "'":
            in_quote = not in_quote
            preceding_backslashes = 0
            continue
        if not in_quote:
            preceding_backslashes = 0
            continue
        if char == "\\":
            preceding_backslashes += 1
            continue
        if char == ":" and preceding_backslashes % 2 == 0:
            return False
        preceding_backslashes = 0
    return True
