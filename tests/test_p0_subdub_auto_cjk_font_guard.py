import tempfile
import unittest
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.subdub_blackboxes import auto_speaker


class AutoCjkFontGuardTests(unittest.TestCase):
    def _guard(self, selected: Path, supported: Path) -> dict:
        fake_shutil = SimpleNamespace(which=lambda _name: "fc-list")
        fake_subprocess = SimpleNamespace(
            run=lambda *_args, **_kwargs: SimpleNamespace(
                returncode=0,
                stdout=f"{supported.resolve()}\n",
            )
        )
        style = {
            "subtitle_font_resolution_ok": True,
            "subtitle_font_path": str(selected),
        }
        with (
            patch.object(auto_speaker, "shutil", fake_shutil, create=True),
            patch.object(auto_speaker, "subprocess", fake_subprocess, create=True),
        ):
            return auto_speaker.guard_subtitle_font(style, script="japanese")

    def test_rejects_fontconfig_latin_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            latin = root / "DejaVuSans.ttf"
            cjk = root / "NotoSansCJK-Regular.ttc"
            latin.write_bytes(b"latin")
            cjk.write_bytes(b"cjk")

            guarded = self._guard(latin, cjk)

        self.assertFalse(guarded["subtitle_font_resolution_ok"])
        self.assertEqual(
            guarded["subtitle_font_blocker"],
            "subtitle_font_missing:japanese",
        )

    def test_accepts_font_listed_for_required_script(self):
        with tempfile.TemporaryDirectory() as directory:
            cjk = Path(directory) / "NotoSansCJK-Regular.ttc"
            cjk.write_bytes(b"cjk")
            style = {
                "subtitle_font_resolution_ok": True,
                "subtitle_font_path": str(cjk),
            }

            self.assertEqual(self._guard(cjk, cjk), style)

    def test_bot_applies_guard_only_inside_auto_speaker_branch(self):
        source = (Path(__file__).parents[1] / "bot.py").read_text(encoding="utf-8")
        start = source.index("    async def _render_video_for_blackbox(")
        end = source.index("\n    voice_resolution_for_debug", start)
        renderer = source[start:end]

        branch_at = renderer.index("if auto_speaker.is_auto_speaker_state(state):")
        guard_at = renderer.index("auto_speaker.guard_subtitle_font(", branch_at)
        blocker_at = renderer.index("subtitle_font_blocker", guard_at)
        render_at = renderer.index("await video_dubbing_render_video", blocker_at)

        self.assertLess(branch_at, guard_at)
        self.assertLess(guard_at, blocker_at)
        self.assertLess(blocker_at, render_at)


if __name__ == "__main__":
    unittest.main()
