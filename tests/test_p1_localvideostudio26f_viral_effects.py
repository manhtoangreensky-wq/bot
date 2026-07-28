import ast
import json
import re
import sys
from pathlib import Path, PurePosixPath
from unittest import SkipTest


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "video" / "local-video-viral-effects"
SKILL_PATH = SKILL_ROOT / "SKILL.md"
JSON_PATH = SKILL_ROOT / "viral_effects.json"
RIGHTS_PATH = ROOT / "skills" / "video" / "local-video-filmmaking" / "rights_requirements.json"

EFFECT_IDS = (
    "phone_magic",
    "colour_fill",
    "clone_throw",
    "outfit_morph",
    "clone_thief",
    "disappear",
    "text_message",
    "music_scroll",
    "product_popup",
    "phone_drop",
)
STATUS_VALUES = {
    "READY_FROM_ARBITRARY_FOOTAGE",
    "REQUIRES_PLANNED_SHOOT",
    "REQUIRES_MASK_TRACK",
    "PROTOTYPE_ONLY",
    "BLOCKED",
}
INVENTORY_VALUES = {
    "EXISTING_AND_VALID",
    "EXISTING_BUT_INCOMPLETE",
    "MISSING",
    "DUPLICATE",
    "PAID_DISABLED",
    "GPU_BLOCKED",
    "LICENSE_BLOCKED",
    "NOT_APPLICABLE",
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
CAPABILITY_ENVELOPE_FIELDS = (
    "schema_version",
    "pack_id",
    "group_id",
    "capability_count",
    "rights_contract_ref",
    "music_suno_policy",
    "ai_assist_policy",
    "capabilities",
)
RECORD_FIELDS = (
    "id",
    "qualified_id",
    "display_name_vi",
    "creative_intent_vi",
    "required_source_shot_setup",
    "camera_lock_requirement",
    "clean_plate_requirement",
    "mask_requirement",
    "tracking_requirement",
    "pose_hand_object_continuity",
    "supported_aspect_ratios",
    "duration_range_seconds",
    "beat_markers",
    "local_deterministic_method",
    "optional_ai_assisted_method",
    "fallback",
    "known_failure_conditions",
    "validation",
    "example_test_fixture_specification",
    "effect_specific_requirements",
    "existing_capability_refs",
    "inventory_status",
    "readiness",
    "status",
    "rights_requirement_ids",
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
APPROVED_FILENAMES = {"SKILL.md", "viral_effects.json"}
VIETNAMESE_MARKERS = tuple(
    "ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ"
)
ASPECT_RATIOS = {"9:16", "16:9", "1:1", "4:5"}
REFERENCE_FIELDS = ("path", "symbols", "support_layer", "relationship", "notes_vi")
SUPPORT_LAYERS = {
    "local_edit",
    "validation",
    "planner",
    "capability_catalog",
    "knowledge",
}
FORBIDDEN_PATTERNS = (
    r"(?i)https?://",
    r"(?i)\b(?:requests|httpx|urllib|wget|curl|yt[-_]?dlp)\b",
    r"(?i)\b(?:download|downloader|fetch_audio|urlopen)\b",
    r"(?i)\b(?:base64|subprocess|os\.system|Popen)\b",
    r"(?i)\b(?:api[_-]?key|client[_-]?secret|private[_-]?key|password)\b",
    r"(?i)\b(?:register[_-]?handler|callback[_-]?data|backstack|state[_-]?machine)\b",
)
EFFECT_SPECIFIC_KEYS = {
    "phone_magic": {"screen_tracking", "screen_replacement", "perspective_corner_pin", "glow_reflection", "hand_occlusion"},
    "colour_fill": {"subject_object_segmentation", "animated_fill_reveal", "edge_feathering", "spill_prevention", "color_accessibility"},
    "clone_throw": {"camera_solution", "clean_plate", "multiple_subject_passes", "throw_trajectory", "occlusion_ordering", "shadow_consistency"},
    "outfit_morph": {"matched_pose", "matched_framing", "segmentation", "transition_mask", "body_cloth_edge_continuity", "match_cut_fallback"},
    "clone_thief": {"multi_pass_compositing", "object_handoff_continuity", "clean_plate", "layer_ordering", "object_mask_tracking"},
    "disappear": {"clean_plate", "subject_mask", "optional_particles_smoke_light", "shadow_removal", "background_continuity"},
    "text_message": {"message_ui_recreation", "privacy_redaction", "typing_reveal_timing", "notification_sound_policy", "platform_neutral_brand_gate"},
    "music_scroll": {"waveform_beat_map", "scroll_direction", "cover_art_rights", "lyric_rights_gate", "unlicensed_song_extraction_block"},
    "product_popup": {"product_cutout", "shadow", "pricing_claim_validation", "callout_labels", "brand_safe_area", "cta_timing"},
    "phone_drop": {"motion_tracking", "impact_point", "screen_transition", "object_continuity", "optional_camera_shake", "hard_cut_fallback"},
}


def _require_pack() -> None:
    if not SKILL_ROOT.is_dir() or not JSON_PATH.is_file() or not SKILL_PATH.is_file():
        raise SkipTest("26F viral-effects pack is not installed")


def _read_payload() -> dict[str, object]:
    _require_pack()
    payload = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _contains_vietnamese(value: object) -> bool:
    if isinstance(value, str):
        return any(marker in value.casefold() for marker in VIETNAMESE_MARKERS)
    if isinstance(value, dict):
        return any(_contains_vietnamese(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_vietnamese(item) for item in value)
    return False


def _assert_nonempty(value: object) -> None:
    if isinstance(value, str):
        assert value.strip()
    elif isinstance(value, dict):
        assert value
        for key, nested in value.items():
            assert isinstance(key, str) and key.strip()
            _assert_nonempty(nested)
    elif isinstance(value, (list, tuple)):
        assert value
        for nested in value:
            _assert_nonempty(nested)
    else:
        assert value is not None


def _python_symbols(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    symbols: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
            for target in targets:
                if isinstance(target, ast.Name):
                    symbols.add(target.id)
    return symbols


def _validate_reference(reference: object) -> None:
    assert isinstance(reference, dict)
    assert tuple(reference) == REFERENCE_FIELDS
    path = reference["path"]
    assert isinstance(path, str) and path and "\\" not in path
    pure = PurePosixPath(path)
    assert not pure.is_absolute() and ".." not in pure.parts
    assert isinstance(reference["symbols"], list)
    assert all(isinstance(symbol, str) and symbol.strip() for symbol in reference["symbols"])
    assert reference["support_layer"] in SUPPORT_LAYERS
    assert reference["relationship"] == "metadata_only"
    assert _contains_vietnamese(reference["notes_vi"])
    resolved = (ROOT / path).resolve()
    assert resolved.is_relative_to(ROOT.resolve()) and resolved.is_file()
    if resolved.suffix == ".py":
        assert set(reference["symbols"]) <= _python_symbols(resolved)


def test_exact_viral_effect_pack_tree_and_no_runtime_files() -> None:
    assert SKILL_ROOT.is_dir(), "26F skill directory is absent"
    assert SKILL_PATH.is_file(), "26F SKILL.md is absent"
    assert JSON_PATH.is_file(), "26F viral_effects.json is absent"
    actual = {path.relative_to(SKILL_ROOT).as_posix() for path in SKILL_ROOT.rglob("*") if path.is_file()}
    assert actual == APPROVED_FILENAMES
    assert not {path for path in SKILL_ROOT.rglob("*") if path.suffix.casefold() in {".mp3", ".wav", ".mp4", ".mov", ".png", ".jpg"}}


def test_contract_test_uses_only_python_standard_library() -> None:
    roots: set[str] = set()
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    assert roots <= sys.stdlib_module_names
    assert roots.isdisjoint({"bot", "services", "providers", "workers", "billing"})


def test_exact_envelope_ids_order_count_rights_and_policies() -> None:
    payload = _read_payload()
    assert tuple(payload) == CAPABILITY_ENVELOPE_FIELDS
    assert payload["schema_version"] == "1.0.0"
    assert payload["pack_id"] == "local-video-viral-effects"
    assert payload["group_id"] == "viral_effect"
    assert payload["capability_count"] == 10
    assert payload["rights_contract_ref"] == "../local-video-filmmaking/rights_requirements.json"
    assert (SKILL_ROOT / payload["rights_contract_ref"]).resolve() == RIGHTS_PATH.resolve()
    assert payload["music_suno_policy"]["status"] == "LOCKED_DISABLED"
    assert payload["music_suno_policy"]["generation_allowed"] is False
    assert payload["music_suno_policy"]["asset_acquisition_allowed"] is False
    assert payload["ai_assist_policy"]["status"] == "LOCKED_DISABLED"
    assert payload["ai_assist_policy"]["generation_allowed"] is False
    records = payload["capabilities"]
    assert tuple(record["id"] for record in records) == EFFECT_IDS
    assert len({record["id"] for record in records}) == 10


def test_each_effect_has_complete_source_shot_contract_and_truth_status() -> None:
    payload = _read_payload()
    for record in payload["capabilities"]:
        assert tuple(record) == RECORD_FIELDS
        effect_id = record["id"]
        assert re.fullmatch(r"[a-z0-9]+(?:_[a-z0-9]+)*", effect_id)
        assert record["qualified_id"] == f"viral_effect.{effect_id}"
        for field in ("display_name_vi", "creative_intent_vi"):
            assert isinstance(record[field], str) and record[field].strip()
            assert _contains_vietnamese(record[field])
        for field in (
            "required_source_shot_setup",
            "camera_lock_requirement",
            "clean_plate_requirement",
            "mask_requirement",
            "tracking_requirement",
            "pose_hand_object_continuity",
            "local_deterministic_method",
            "optional_ai_assisted_method",
            "fallback",
            "known_failure_conditions",
            "validation",
            "example_test_fixture_specification",
            "effect_specific_requirements",
        ):
            _assert_nonempty(record[field])
            assert _contains_vietnamese(record[field]), field
        assert set(record["supported_aspect_ratios"]) <= ASPECT_RATIOS
        assert record["supported_aspect_ratios"]
        assert record["beat_markers"]
        duration = record["duration_range_seconds"]
        assert tuple(duration) == ("min", "max", "decision_rule_vi")
        assert isinstance(duration["min"], (int, float)) and duration["min"] >= 0
        assert isinstance(duration["max"], (int, float)) and duration["max"] >= duration["min"]
        assert record["inventory_status"] in INVENTORY_VALUES
        assert record["readiness"] in STATUS_VALUES
        assert record["status"] in STATUS_VALUES
        assert record["status"] != "READY_FROM_ARBITRARY_FOOTAGE"
        assert tuple(record["rights_requirement_ids"]) == RIGHTS_IDS
        for key, expected in LOCKS.items():
            assert record[key] is expected
        assert set(record["effect_specific_requirements"]) == EFFECT_SPECIFIC_KEYS[effect_id]
        for reference in record["existing_capability_refs"]:
            _validate_reference(reference)


def test_effect_minimums_and_local_method_are_explicitly_locked() -> None:
    payload = _read_payload()
    for record in payload["capabilities"]:
        camera = record["camera_lock_requirement"]
        assert set(camera) >= {"required", "guidance_vi", "evidence_vi"}
        plate = record["clean_plate_requirement"]
        assert set(plate) >= {"required", "guidance_vi", "evidence_vi"}
        mask = record["mask_requirement"]
        assert set(mask) >= {"required", "guidance_vi", "evidence_vi"}
        tracking = record["tracking_requirement"]
        assert set(tracking) >= {"required", "guidance_vi", "evidence_vi"}
        local = record["local_deterministic_method"]
        assert local["execution_in_26f_allowed"] is False
        assert local["mode"] in {"SPECIFICATION_ONLY", "LOCAL_PRIMITIVE_MAPPING"}
        assert local["technology_refs"]
        ai = record["optional_ai_assisted_method"]
        assert ai["enabled"] is False
        assert ai["status"] == "LOCKED_DISABLED"
        assert record["validation"]["fail_closed"] is True
        assert record["validation"]["checks"]
        assert record["example_test_fixture_specification"]["fixture_id"]


def test_skill_links_all_contracts_rights_and_spec_with_relative_paths() -> None:
    _require_pack()
    text = SKILL_PATH.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines[0] == "---"
    end = lines.index("---", 1)
    frontmatter = {}
    for line in lines[1:end]:
        key, value = line.split(":", 1)
        frontmatter[key.strip()] = value.strip()
    assert set(frontmatter) == {"name", "description"}
    assert frontmatter["name"] == "local-video-viral-effects"
    links = tuple(re.findall(r"\[[^\]]+\]\(([^)]+)\)", text))
    required = {
        "viral_effects.json",
        "../local-video-filmmaking/rights_requirements.json",
        "../local-video-transition-motion/transition_audio.json",
        "../../../docs/superpowers/specs/2026-07-29-localvideostudio26f-viral-effects-design.md",
    }
    assert required <= set(links)
    for target in links:
        relative = target.split("#", 1)[0]
        assert relative and "\\" not in relative
        assert not relative.startswith(("/", "\\"))
        assert not re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", relative)
        resolved = (SKILL_ROOT / relative).resolve()
        assert resolved.is_relative_to(ROOT.resolve()) and resolved.is_file()


def test_json_is_utf8_deterministic_and_pack_has_no_network_asset_or_secret_code() -> None:
    _require_pack()
    raw = JSON_PATH.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = JSON_PATH.read_text(encoding="utf-8")
    payload = json.loads(text)
    assert text == json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    combined = SKILL_PATH.read_text(encoding="utf-8") + text
    for pattern in FORBIDDEN_PATTERNS:
        assert re.search(pattern, combined) is None, pattern


def test_music_ai_and_rights_policy_never_unlocks_execution() -> None:
    payload = _read_payload()
    assert payload["music_suno_policy"]["status"] == "LOCKED_DISABLED"
    assert payload["ai_assist_policy"]["status"] == "LOCKED_DISABLED"
    for record in payload["capabilities"]:
        assert record["optional_ai_assisted_method"]["enabled"] is False
        assert record["optional_ai_assisted_method"]["status"] == "LOCKED_DISABLED"
        assert record["validation"]["rights_gate"] == "BLOCK_ON_UNKNOWN_OR_RESTRICTED"
