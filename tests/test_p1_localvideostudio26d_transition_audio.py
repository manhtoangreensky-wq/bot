import ast
import json
import re
import sys
from pathlib import Path
from unittest import SkipTest


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "video" / "local-video-transition-motion"
AUDIO_PATH = SKILL_ROOT / "transition_audio.json"
SKILL_PATH = SKILL_ROOT / "SKILL.md"
RIGHTS_PATH = (
    ROOT
    / "skills"
    / "video"
    / "local-video-filmmaking"
    / "rights_requirements.json"
)

AUDIO_IDS = (
    "no_accent",
    "whoosh",
    "impact",
    "riser",
    "downer",
    "reverse_swell",
    "silence_cut",
    "music_duck",
)

TOP_LEVEL_FIELDS = (
    "schema_version",
    "pack_id",
    "group_id",
    "capability_count",
    "rights_contract_ref",
    "music_suno_policy",
    "capabilities",
)
ENTRY_FIELDS = (
    "id",
    "display_name_vi",
    "purpose",
    "timing_anchor",
    "gain_guidance",
    "ducking_policy",
    "rights_requirement",
    "avoid_when",
    "failure_modes",
    "validation_checks",
    "planning_only",
    "runtime_registered",
    "provider_executable",
    "public_ui",
)
LOCKS = {
    "planning_only": True,
    "runtime_registered": False,
    "provider_executable": False,
    "public_ui": False,
}
RIGHTS_IDS = (
    "source_ownership",
    "license",
    "brand_restrictions",
    "face_person_consent",
    "music_rights",
    "font_rights",
    "stock_attribution",
    "ai_generated_asset_disclosure_metadata",
)
FORBIDDEN_ASSET_EXTENSIONS = {
    ".mp3",
    ".wav",
    ".ogg",
    ".flac",
    ".aiff",
    ".m4a",
    ".mp4",
    ".mov",
    ".webm",
}
FORBIDDEN_DOWNLOAD_PATTERNS = (
    r"(?i)https?://",
    r"(?i)\b(?:requests|httpx|urllib|wget|curl|yt[-_]?dlp)\b",
    r"(?i)\b(?:download|downloader|fetch_audio|urlopen)\b",
    r"(?i)\b(?:base64|subprocess|os\.system|Popen)\b",
)
VIETNAMESE_MARKERS = tuple(
    "ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ"
)


def _read_audio() -> dict[str, object]:
    if not AUDIO_PATH.is_file():
        raise SkipTest("transition-audio contract is not installed")
    payload = json.loads(AUDIO_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _contains_vietnamese(value: object) -> bool:
    if isinstance(value, str):
        return any(marker in value.casefold() for marker in VIETNAMESE_MARKERS)
    if isinstance(value, dict):
        return any(_contains_vietnamese(nested) for nested in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_vietnamese(nested) for nested in value)
    return False


def _assert_nonempty(value: object) -> None:
    if isinstance(value, str):
        assert value.strip()
        return
    if isinstance(value, dict):
        assert value
        for key, nested in value.items():
            assert isinstance(key, str) and key.strip()
            _assert_nonempty(nested)
        return
    if isinstance(value, (list, tuple)):
        assert value
        for nested in value:
            _assert_nonempty(nested)
        return
    assert value is not None


def _tracked_asset_files() -> tuple[Path, ...]:
    return tuple(
        path
        for path in SKILL_ROOT.rglob("*")
        if path.is_file() and path.suffix.casefold() in FORBIDDEN_ASSET_EXTENSIONS
    )


def test_transition_audio_path_exists() -> None:
    assert AUDIO_PATH.is_file(), AUDIO_PATH


def test_transition_audio_file_exists_with_exact_eight_ids_and_envelope() -> None:
    payload = _read_audio()
    assert tuple(payload) == TOP_LEVEL_FIELDS
    assert payload["schema_version"] == "1.0.0"
    assert payload["pack_id"] == "local-video-transition-motion"
    assert payload["group_id"] == "transition_audio"
    assert payload["capability_count"] == 8
    assert payload["rights_contract_ref"] == (
        "../local-video-filmmaking/rights_requirements.json"
    )
    assert (SKILL_ROOT / payload["rights_contract_ref"]).resolve() == RIGHTS_PATH.resolve()
    assert payload["music_suno_policy"]["status"] == "LOCKED_DISABLED"
    assert payload["music_suno_policy"]["generation_allowed"] is False
    capabilities = payload["capabilities"]
    assert isinstance(capabilities, list)
    assert tuple(entry["id"] for entry in capabilities) == AUDIO_IDS
    assert len({entry["id"] for entry in capabilities}) == 8


def test_each_transition_audio_entry_has_required_contract_fields_and_locks() -> None:
    payload = _read_audio()
    for entry in payload["capabilities"]:
        assert tuple(entry) == ENTRY_FIELDS
        assert re.fullmatch(r"[a-z0-9]+(?:_[a-z0-9]+)*", entry["id"])
        assert isinstance(entry["display_name_vi"], str)
        assert _contains_vietnamese(entry["display_name_vi"])
        for field in (
            "purpose",
            "timing_anchor",
            "gain_guidance",
            "ducking_policy",
            "rights_requirement",
            "avoid_when",
            "failure_modes",
            "validation_checks",
        ):
            _assert_nonempty(entry[field])
            assert _contains_vietnamese(entry[field]), field
        rights = entry["rights_requirement"]
        assert rights["contract_ref"] == (
            "../local-video-filmmaking/rights_requirements.json"
        )
        assert (SKILL_ROOT / rights["contract_ref"]).resolve() == RIGHTS_PATH.resolve()
        assert tuple(rights["required_ids"]) == RIGHTS_IDS
        assert rights["music_rights_id"] == "music_rights"
        assert rights["sound_effect_rights_id"] in {"license", "stock_attribution"}
        for key, expected in LOCKS.items():
            assert entry[key] is expected


def test_music_and_sound_effect_rights_are_explicitly_linked() -> None:
    payload = _read_audio()
    for entry in payload["capabilities"]:
        rights = entry["rights_requirement"]
        assert "music_rights" in rights["required_ids"]
        assert any(
            item in rights["required_ids"]
            for item in ("license", "stock_attribution")
        )
    assert "Music/Suno" in payload["music_suno_policy"]["guidance_vi"]


def test_audio_contract_has_no_binary_asset_url_downloader_or_runtime_code() -> None:
    assert not _tracked_asset_files()
    _read_audio()
    combined = AUDIO_PATH.read_text(encoding="utf-8")
    for pattern in FORBIDDEN_DOWNLOAD_PATTERNS:
        assert re.search(pattern, combined) is None, pattern
    source = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".", 1)[0])
    assert imported_roots <= sys.stdlib_module_names
    assert "subprocess" not in imported_roots


def test_skill_links_audio_contract_and_all_relative_links_resolve() -> None:
    _read_audio()
    text = SKILL_PATH.read_text(encoding="utf-8")
    links = tuple(re.findall(r"\[[^\]]+\]\(([^)]+)\)", text))
    assert "transition_audio.json" in links
    root = ROOT.resolve()
    for target in links:
        relative_target = target.split("#", 1)[0]
        assert relative_target and "\\" not in relative_target
        assert not relative_target.startswith(("/", "\\"))
        assert not re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", relative_target)
        resolved = (SKILL_ROOT / relative_target).resolve()
        assert resolved.is_relative_to(root)
        assert resolved.is_file(), target


def test_audio_json_is_utf8_without_bom_and_deterministic() -> None:
    _read_audio()
    raw = AUDIO_PATH.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = AUDIO_PATH.read_text(encoding="utf-8")
    payload = json.loads(text)
    assert text == json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
