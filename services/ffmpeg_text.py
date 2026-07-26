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
    punctuation is kept: `:` `,` `%` `(` `)` are literal inside quotes and must
    survive so captions still read naturally.
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
    return text


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
    if re.match(r"^[A-Za-z]:", cleaned):
        cleaned = cleaned[0] + "\\:" + cleaned[2:]
    return cleaned


def quote_filter_path(path: str, *, resolve: bool = True) -> str:
    return "'" + escape_filter_path(path, resolve=resolve) + "'"


def drawtext_is_safe(fragment: str) -> bool:
    """True when a built drawtext fragment cannot escape its own quoting.

    Used by tests as an independent check on whatever the builders produced:
    every quote in the fragment must open or close a value, never appear
    inside one.
    """
    return fragment.count("'") % 2 == 0 and "\\'" not in fragment
