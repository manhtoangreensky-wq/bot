import unittest
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.subdub_blackboxes import auto_speaker


class AutoCjkFontAnchorTests(unittest.TestCase):
    def test_anchor_auto_speaker_has_no_runtime_fontconfig_dependency(self):
        source = Path(auto_speaker.__file__).read_text(encoding="utf-8")

        self.assertNotIn("guard_subtitle_font", source)
        self.assertNotIn("fc-list", source)
        self.assertNotIn("subprocess.run", source)

    def test_bot_uses_shared_subtitle_style_resolution_for_all_lanes(self):
        source = (Path(__file__).parents[1] / "bot.py").read_text(encoding="utf-8")
        start = source.index("    async def _render_video_for_blackbox(")
        end = source.index("\n    voice_resolution_for_debug", start)
        renderer = source[start:end]

        normalize_at = renderer.index("render_style = subdub_normalize_style(render_state)")
        render_at = renderer.index("await video_dubbing_render_video", normalize_at)

        self.assertLess(normalize_at, render_at)
        self.assertNotIn("auto_speaker.guard_subtitle_font(", renderer)

    def test_shared_renderer_keeps_font_resolution_fail_closed(self):
        source = (Path(__file__).parents[1] / "bot.py").read_text(encoding="utf-8")
        start = source.index("async def video_dubbing_render_video(")
        end = source.index("\ndef ", start)
        renderer = source[start:end]

        self.assertIn('if not style.get("subtitle_font_resolution_ok"):', renderer)
        self.assertIn('subtitle_font_blocker', renderer)


if __name__ == "__main__":
    unittest.main()
