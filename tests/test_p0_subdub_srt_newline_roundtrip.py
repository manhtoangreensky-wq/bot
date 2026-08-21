import re
from pathlib import Path


TARGET_FUNCTIONS = {
    "deepgram_srt_from_response",
    "deepgram_vtt_from_srt",
    "video_dubbing_plain_script",
    "video_dubbing_segments_from_subtitle",
    "video_dubbing_srt_from_segments",
    "video_dubbing_srt_from_text",
    "video_dubbing_srt_timestamp",
    "video_dubbing_srt_to_vtt_text",
    "video_dubbing_subtitle_plain_text",
    "video_dubbing_timestamp_seconds",
}


def _load_srt_helpers() -> dict:
    bot_path = Path(__file__).resolve().parents[1] / "bot.py"
    lines = bot_path.read_text(encoding="utf-8").splitlines(keepends=True)
    blocks = []
    found = set()
    for index, line in enumerate(lines):
        match = re.match(r"^(?:async\s+)?def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", line)
        if not match or match.group(1) not in TARGET_FUNCTIONS:
            continue
        end = index + 1
        while end < len(lines) and (not lines[end].strip() or lines[end][0].isspace()):
            end += 1
        blocks.append("".join(lines[index:end]))
        found.add(match.group(1))
    assert found == TARGET_FUNCTIONS
    namespace = {"re": re}
    exec(compile("\n".join(blocks), str(bot_path), "exec"), namespace)
    return namespace


def test_subdub_srt_vtt_and_plain_text_use_real_newlines_roundtrip() -> None:
    helpers = _load_srt_helpers()
    source = " ".join(f"word{index}" for index in range(1, 25))

    srt_text = helpers["video_dubbing_srt_from_text"](source, duration_seconds=4)

    assert "\\n" not in srt_text
    assert srt_text.count("-->") == 2
    segments = helpers["video_dubbing_segments_from_subtitle"](srt_text)
    assert [item["text"] for item in segments] == [
        " ".join(f"word{index}" for index in range(1, 13)),
        " ".join(f"word{index}" for index in range(13, 25)),
    ]
    assert helpers["video_dubbing_srt_from_segments"](segments) == srt_text

    plain = helpers["video_dubbing_plain_script"](srt_text)
    assert plain == "\n".join(item["text"] for item in segments)
    assert helpers["video_dubbing_subtitle_plain_text"](srt_text) == plain + "\n"

    vtt_text = helpers["video_dubbing_srt_to_vtt_text"](srt_text)
    assert vtt_text.startswith("WEBVTT\n\n")
    assert "\\n" not in vtt_text
    assert "00:00:00.000 --> 00:00:02.000" in vtt_text


def test_deepgram_srt_and_vtt_use_real_newlines() -> None:
    helpers = _load_srt_helpers()
    helpers["deepgram_word_items"] = lambda data: data["words"]
    payload = {
        "words": [
            {"word": "one", "start": 0.0, "end": 0.4},
            {"word": "two", "start": 0.5, "end": 0.9},
            {"word": "three", "start": 1.0, "end": 1.4},
        ]
    }

    srt_text = helpers["deepgram_srt_from_response"](payload, max_words_per_block=2)

    assert "\\n" not in srt_text
    assert srt_text.count("-->") == 2
    vtt_text = helpers["deepgram_vtt_from_srt"](srt_text)
    assert vtt_text.startswith("WEBVTT\n\n")
    assert "\\n" not in vtt_text
    assert "," not in "\n".join(line for line in vtt_text.splitlines() if "-->" in line)


if __name__ == "__main__":
    test_subdub_srt_vtt_and_plain_text_use_real_newlines_roundtrip()
    test_deepgram_srt_and_vtt_use_real_newlines()
    print("SUBDUB_SRT_NEWLINE_ROUNDTRIP=2_PASS")
