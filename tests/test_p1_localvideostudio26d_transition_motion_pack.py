import ast
import copy
import json
import math
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from unittest import SkipTest


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "video" / "local-video-transition-motion"
SKILL_PATH = SKILL_ROOT / "SKILL.md"
RIGHTS_PATH = (
    ROOT
    / "skills"
    / "video"
    / "local-video-filmmaking"
    / "rights_requirements.json"
)

TRANSITION_IDS = (
    "hard_cut",
    "cross_dissolve",
    "dip_to_black",
    "dip_to_white",
    "slide",
    "push",
    "whip_pan",
    "speed_ramp",
    "match_motion",
    "match_shape",
    "match_color",
    "object_wipe",
    "foreground_occlusion",
    "zoom",
    "light_flash",
    "blur",
    "glitch",
    "mask_reveal",
    "split_screen",
    "parallax_transition",
)

MOTION_PRINCIPLE_IDS = (
    "timing_and_spacing",
    "easing",
    "anticipation",
    "follow_through",
    "overlap",
    "squash_and_stretch",
    "arcs",
    "staging",
    "secondary_action",
    "exaggeration",
    "appeal",
    "motion_hierarchy",
)

KINETIC_TYPOGRAPHY_IDS = (
    "word_emphasis",
    "line_build",
    "type_reveal",
    "mask_reveal",
    "tracking_animation",
    "scale_punch",
    "rotation_accent",
    "highlight_box",
    "subtitle_to_title_promotion",
    "beat_synced_type",
)

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

CAPABILITY_FILES = {
    "transition_grammar.json": ("transition", TRANSITION_IDS),
    "motion_design_principles.json": (
        "motion_design_principle",
        MOTION_PRINCIPLE_IDS,
    ),
    "kinetic_typography.json": (
        "kinetic_typography",
        KINETIC_TYPOGRAPHY_IDS,
    ),
}
JSON_FILENAMES = (*CAPABILITY_FILES, "local_implementation_mapping.json")
APPROVED_FILENAMES = ("SKILL.md", *JSON_FILENAMES)

CAPABILITY_ENVELOPE_FIELDS = (
    "schema_version",
    "pack_id",
    "group_id",
    "capability_count",
    "rights_contract_ref",
    "capabilities",
)
TRANSITION_FIELDS = (
    "id",
    "qualified_id",
    "display_name_vi",
    "summary_vi",
    "purpose_vi",
    "input_shot_compatibility",
    "direction_continuity",
    "duration_range_seconds",
    "easing",
    "motion_blur_requirement",
    "mask_tracking_requirement",
    "audio_accent",
    "fallback",
    "failure_conditions",
    "validation_checks",
    "existing_capability_refs",
    "inventory_status",
    "readiness",
    "rights_requirement_ids",
    "reduced_motion",
    "planning_only",
    "runtime_registered",
    "provider_executable",
    "public_ui",
)
MOTION_PRINCIPLE_FIELDS = (
    "id",
    "qualified_id",
    "display_name_vi",
    "summary_vi",
    "purpose_vi",
    "application_rules",
    "restraint_rules",
    "footage_limits",
    "timing_guidance",
    "accessibility",
    "reduced_motion",
    "fallback",
    "failure_conditions",
    "validation_checks",
    "existing_capability_refs",
    "inventory_status",
    "readiness",
    "rights_requirement_ids",
    "planning_only",
    "runtime_registered",
    "provider_executable",
    "public_ui",
)
KINETIC_TYPOGRAPHY_FIELDS = (
    "id",
    "qualified_id",
    "display_name_vi",
    "summary_vi",
    "purpose_vi",
    "required_inputs",
    "typography_behavior",
    "timing_guidance",
    "readability",
    "safe_area",
    "maximum_character_density",
    "contrast",
    "mobile_legibility",
    "no_flashing_accessibility",
    "reduced_motion",
    "audio_sync",
    "fallback",
    "failure_conditions",
    "validation_checks",
    "existing_capability_refs",
    "inventory_status",
    "readiness",
    "rights_requirement_ids",
    "planning_only",
    "runtime_registered",
    "provider_executable",
    "public_ui",
)
GROUP_FIELD_ORDERS = {
    "transition": TRANSITION_FIELDS,
    "motion_design_principle": MOTION_PRINCIPLE_FIELDS,
    "kinetic_typography": KINETIC_TYPOGRAPHY_FIELDS,
}

MAPPING_ENVELOPE_FIELDS = (
    "schema_version",
    "pack_id",
    "technology_count",
    "capability_mapping_count",
    "technologies",
    "mappings",
)
TECHNOLOGY_FIELDS = (
    "id",
    "display_name",
    "inventory_status",
    "relationship",
    "evidence_refs",
    "notes_vi",
)
MAPPING_FIELDS = (
    "qualified_id",
    "group_id",
    "capability_id",
    "primary_technology",
    "supporting_technologies",
    "realization_notes_vi",
    "limitations_vi",
    "readiness",
    "relationship",
    "production_renderer_changed",
)
TECHNOLOGY_IDS = (
    "remotion",
    "gsap",
    "hyperframes",
    "ffmpeg",
    "svg",
    "canvas",
    "css_transforms",
)
TECHNOLOGY_STATUS = {
    "remotion": "NOT_INSTALLED",
    "gsap": "NOT_INSTALLED",
    "hyperframes": "NOT_INSTALLED",
    "ffmpeg": "AVAILABLE_LOCAL",
    "svg": "SPECIFICATION_ONLY",
    "canvas": "SPECIFICATION_ONLY",
    "css_transforms": "SPECIFICATION_ONLY",
}

REFERENCE_FIELD_ORDER = (
    "path",
    "symbols",
    "support_layer",
    "relationship",
    "notes_vi",
)
SUPPORT_LAYERS = frozenset(
    {
        "prompt",
        "planner",
        "capability_catalog",
        "local_edit",
        "knowledge",
        "policy",
        "tool_inventory",
    }
)
INVENTORY_STATUSES = frozenset(
    {
        "EXISTING_AND_VALID",
        "EXISTING_BUT_INCOMPLETE",
        "MISSING",
        "DUPLICATE",
        "PAID_DISABLED",
        "GPU_BLOCKED",
        "LICENSE_BLOCKED",
        "NOT_APPLICABLE",
    }
)
READINESS = frozenset(
    {
        "CONTRACT_ONLY",
        "LOCAL_PLANNING_READY",
        "REQUIRES_RUNTIME",
        "REQUIRES_PLANNED_SHOOT",
        "NOT_SUPPORTED",
    }
)
LOCKS = {
    "planning_only": True,
    "runtime_registered": False,
    "provider_executable": False,
    "public_ui": False,
}
VIETNAMESE_MARKERS = tuple(
    "ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ"
)
FORBIDDEN_CONTENT_PATTERNS = (
    r"(?i)https?://",
    r"(?i)\b(?:api[_-]?key|client[_-]?secret|password|private[_-]?key)\b",
    r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+",
    r"(?im)^\s*(?:from|import)\s+(?:bot|services|workers?|providers?)\b",
    r"(?i)\b(?:requests|httpx)\.(?:get|post|put|patch|delete|request)\s*\(",
    r"(?i)\b(?:task[_-]?id|job[_-]?id|provider[_-]?task[_-]?id)\b",
    r"(?i)\b(?:callback[_-]?(?:data|query|handler)|conversationhandler|inlinekeyboard)\b",
    r"(?i)\b(?:context\.user_data|state[_-]?machine|back[_-]?stack|backstack)\b",
    r"(?i)\b(?:register[_-]?handler|add_handler|runtime[_-]?registry)\b",
    r"(?i)[A-Z]:\\Users\\",
)


def _approved_paths() -> tuple[Path, ...]:
    return tuple(SKILL_ROOT / filename for filename in APPROVED_FILENAMES)


def _missing_approved_paths() -> tuple[Path, ...]:
    return tuple(path for path in _approved_paths() if not path.is_file())


def _require_complete_pack() -> None:
    missing = _missing_approved_paths()
    if missing:
        relative = ", ".join(path.relative_to(ROOT).as_posix() for path in missing)
        raise SkipTest(f"transition/motion pack is not installed: {relative}")


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict), path
    return payload


def _load_capability_payloads() -> dict[str, dict[str, object]]:
    _require_complete_pack()
    return {
        filename: _read_json(SKILL_ROOT / filename)
        for filename in CAPABILITY_FILES
    }


def _load_mapping_payload() -> dict[str, object]:
    _require_complete_pack()
    return _read_json(SKILL_ROOT / "local_implementation_mapping.json")


def _all_capability_records() -> tuple[dict[str, object], ...]:
    return tuple(
        record
        for payload in _load_capability_payloads().values()
        for record in payload["capabilities"]
    )


def _qualified_ids() -> tuple[str, ...]:
    return tuple(record["qualified_id"] for record in _all_capability_records())


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


def _validate_reference(reference: object) -> None:
    assert isinstance(reference, dict)
    assert tuple(reference) == REFERENCE_FIELD_ORDER
    path = reference["path"]
    assert isinstance(path, str) and path.strip() == path and path
    assert "\\" not in path
    pure_path = PurePosixPath(path)
    assert not pure_path.is_absolute()
    assert ".." not in pure_path.parts
    assert isinstance(reference["symbols"], list)
    assert all(
        isinstance(symbol, str) and symbol.strip()
        for symbol in reference["symbols"]
    )
    assert reference["support_layer"] in SUPPORT_LAYERS
    assert reference["relationship"] == "metadata_only"
    assert _contains_vietnamese(reference["notes_vi"])


def _validate_common_record(record: dict[str, object], group_id: str) -> None:
    expected_fields = GROUP_FIELD_ORDERS[group_id]
    assert tuple(record) == expected_fields
    assert isinstance(record["id"], str)
    assert re.fullmatch(r"[a-z0-9]+(?:_[a-z0-9]+)*", record["id"])
    assert record["qualified_id"] == f"{group_id}.{record['id']}"
    for field in ("display_name_vi", "summary_vi", "purpose_vi"):
        assert isinstance(record[field], str) and record[field].strip()
        assert _contains_vietnamese(record[field]), field
    assert record["inventory_status"] in INVENTORY_STATUSES
    assert record["readiness"] in READINESS
    assert tuple(record["rights_requirement_ids"]) == RIGHTS_IDS
    references = record["existing_capability_refs"]
    assert isinstance(references, list)
    for reference in references:
        _validate_reference(reference)
    for key, expected in LOCKS.items():
        assert record[key] is expected


def _validate_transition(record: dict[str, object]) -> None:
    _validate_common_record(record, "transition")
    for field in (
        "input_shot_compatibility",
        "direction_continuity",
        "easing",
        "motion_blur_requirement",
        "mask_tracking_requirement",
        "audio_accent",
        "fallback",
        "failure_conditions",
        "validation_checks",
        "reduced_motion",
    ):
        _assert_nonempty(record[field])
        assert _contains_vietnamese(record[field]), field
    duration = record["duration_range_seconds"]
    assert tuple(duration) == ("min", "max", "decision_rule_vi")
    assert isinstance(duration["min"], (int, float)) and duration["min"] >= 0
    assert isinstance(duration["max"], (int, float))
    assert math.isfinite(float(duration["min"]))
    assert math.isfinite(float(duration["max"]))
    assert duration["max"] >= duration["min"]
    assert _contains_vietnamese(duration["decision_rule_vi"])
    easing = record["easing"]
    assert tuple(easing) == ("preset_id", "curve", "guidance_vi")
    assert isinstance(easing["preset_id"], str) and easing["preset_id"]
    assert isinstance(easing["curve"], str) and easing["curve"]
    blur = record["motion_blur_requirement"]
    assert blur["level"] in {"NONE", "OPTIONAL", "REQUIRED"}
    mask_track = record["mask_tracking_requirement"]
    assert mask_track["mask"] in {"NONE", "OPTIONAL", "REQUIRED"}
    assert mask_track["tracking"] in {"NONE", "OPTIONAL", "REQUIRED"}
    fallback = record["fallback"]
    target = fallback["qualified_id"]
    assert target is None or target in {f"transition.{item}" for item in TRANSITION_IDS}
    assert target != record["qualified_id"]


def _validate_motion_principle(record: dict[str, object]) -> None:
    _validate_common_record(record, "motion_design_principle")
    for field in (
        "application_rules",
        "restraint_rules",
        "footage_limits",
        "timing_guidance",
        "accessibility",
        "reduced_motion",
        "failure_conditions",
        "validation_checks",
    ):
        _assert_nonempty(record[field])
        assert _contains_vietnamese(record[field]), field
    fallback = record["fallback"]
    assert isinstance(fallback, dict)
    assert set(fallback) >= {"principle_ref", "guidance_vi"}
    target = fallback["principle_ref"]
    assert target is None or target in MOTION_PRINCIPLE_IDS
    assert isinstance(fallback["guidance_vi"], str) and fallback["guidance_vi"].strip()
    assert _contains_vietnamese(fallback["guidance_vi"])


def _validate_kinetic_typography(record: dict[str, object]) -> None:
    _validate_common_record(record, "kinetic_typography")
    for field in (
        "required_inputs",
        "typography_behavior",
        "timing_guidance",
        "readability",
        "safe_area",
        "maximum_character_density",
        "contrast",
        "mobile_legibility",
        "no_flashing_accessibility",
        "reduced_motion",
        "audio_sync",
        "failure_conditions",
        "validation_checks",
    ):
        _assert_nonempty(record[field])
        assert _contains_vietnamese(record[field]), field
    fallback = record["fallback"]
    assert isinstance(fallback, dict)
    assert set(fallback) >= {"qualified_id", "guidance_vi"}
    target = fallback["qualified_id"]
    assert target is None or target in {
        f"kinetic_typography.{item}" for item in KINETIC_TYPOGRAPHY_IDS
    }
    assert isinstance(fallback["guidance_vi"], str) and fallback["guidance_vi"].strip()
    assert _contains_vietnamese(fallback["guidance_vi"])
    assert record["no_flashing_accessibility"]["flashing_allowed"] is False
    density = record["maximum_character_density"]
    assert isinstance(density["max_characters_per_line"], int)
    assert 1 <= density["max_characters_per_line"] <= 42
    assert isinstance(density["max_lines"], int)
    assert 1 <= density["max_lines"] <= 3


def _validate_capability(record: dict[str, object], group_id: str) -> None:
    if group_id == "transition":
        _validate_transition(record)
    elif group_id == "motion_design_principle":
        _validate_motion_principle(record)
    elif group_id == "kinetic_typography":
        _validate_kinetic_typography(record)
    else:
        raise AssertionError(group_id)


def _assert_rejected(record: dict[str, object], group_id: str) -> None:
    try:
        _validate_capability(record, group_id)
    except AssertionError:
        return
    raise AssertionError("mutated capability unexpectedly passed validation")


def _all_references() -> tuple[dict[str, object], ...]:
    references = [
        reference
        for record in _all_capability_records()
        for reference in record["existing_capability_refs"]
    ]
    for technology in _load_mapping_payload()["technologies"]:
        references.extend(technology["evidence_refs"])
    return tuple(references)


def _tracked_repository_paths() -> frozenset[str]:
    completed = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "--cached"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
    )
    return frozenset(
        line.strip().replace("\\", "/")
        for line in completed.stdout.splitlines()
        if line.strip()
    )


def _top_level_python_symbols(path: Path) -> frozenset[str]:
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
    return frozenset(symbols)


def test_exact_approved_skill_files_exist_and_no_runtime_files() -> None:
    missing = _missing_approved_paths()
    assert not missing, "approved 26D files are absent: " + ", ".join(
        path.relative_to(ROOT).as_posix() for path in missing
    )
    actual = {
        path.relative_to(SKILL_ROOT).as_posix()
        for path in SKILL_ROOT.rglob("*")
        if path.is_file()
    }
    assert actual == set(APPROVED_FILENAMES)


def test_contract_test_imports_only_python_standard_library() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".", 1)[0])
    assert imported_roots <= sys.stdlib_module_names
    assert imported_roots.isdisjoint(
        {"bot", "services", "workers", "providers", "database", "billing"}
    )


def test_exact_envelopes_ids_counts_order_and_group_qualified_uniqueness() -> None:
    payloads = _load_capability_payloads()
    qualified_ids: list[str] = []
    base_ids: list[str] = []
    for filename, (group_id, expected_ids) in CAPABILITY_FILES.items():
        payload = payloads[filename]
        assert tuple(payload) == CAPABILITY_ENVELOPE_FIELDS
        assert payload["schema_version"] == "1.0.0"
        assert payload["pack_id"] == "local-video-transition-motion"
        assert payload["group_id"] == group_id
        assert payload["capability_count"] == len(expected_ids)
        assert payload["rights_contract_ref"] == (
            "../local-video-filmmaking/rights_requirements.json"
        )
        rights_ref = (SKILL_ROOT / payload["rights_contract_ref"]).resolve()
        assert rights_ref == RIGHTS_PATH.resolve()
        assert rights_ref.is_file()
        records = payload["capabilities"]
        assert tuple(record["id"] for record in records) == expected_ids
        for record in records:
            _validate_capability(record, group_id)
        base_ids.extend(record["id"] for record in records)
        qualified_ids.extend(record["qualified_id"] for record in records)
    assert len(qualified_ids) == 42
    assert len(set(qualified_ids)) == 42
    collisions = {item for item in base_ids if base_ids.count(item) > 1}
    assert collisions == {"mask_reveal"}


def test_rights_contract_resolves_and_all_records_link_exact_eight_ids() -> None:
    assert RIGHTS_PATH.is_file()
    rights_payload = _read_json(RIGHTS_PATH)
    assert tuple(item["id"] for item in rights_payload["declarations"]) == RIGHTS_IDS
    for record in _all_capability_records():
        assert tuple(record["rights_requirement_ids"]) == RIGHTS_IDS


def test_transition_semantics_are_complete_and_hard_cut_has_zero_duration() -> None:
    records = {
        record["id"]: record
        for record in _load_capability_payloads()["transition_grammar.json"][
            "capabilities"
        ]
    }
    assert records["hard_cut"]["duration_range_seconds"]["min"] == 0
    assert records["hard_cut"]["duration_range_seconds"]["max"] == 0
    assert records["hard_cut"]["motion_blur_requirement"]["level"] == "NONE"
    for capability_id, record in records.items():
        _validate_transition(record)
        if capability_id != "hard_cut":
            assert record["duration_range_seconds"]["max"] > 0


def test_transition_tracking_and_direction_requirements_are_truthful() -> None:
    records = {
        record["id"]: record
        for record in _load_capability_payloads()["transition_grammar.json"][
            "capabilities"
        ]
    }
    for capability_id in ("object_wipe", "foreground_occlusion", "mask_reveal"):
        assert records[capability_id]["mask_tracking_requirement"]["mask"] == (
            "REQUIRED"
        )
    for capability_id in ("whip_pan", "match_motion", "parallax_transition"):
        assert records[capability_id]["direction_continuity"]["mode"] == (
            "MATCH_VECTOR"
        )


def test_motion_principles_all_include_restraint_and_footage_limits() -> None:
    records = _load_capability_payloads()["motion_design_principles.json"][
        "capabilities"
    ]
    for record in records:
        _validate_motion_principle(record)
        combined = " ".join(record["restraint_rules"] + record["footage_limits"])
        assert re.search(r"(?i)không|tránh|chỉ", combined)


def test_kinetic_typography_has_all_accessibility_guards() -> None:
    records = _load_capability_payloads()["kinetic_typography.json"][
        "capabilities"
    ]
    for record in records:
        _validate_kinetic_typography(record)
        assert record["readability"]["required"] is True
        assert record["safe_area"]["target_profile_required"] is True
        assert record["contrast"]["frame_sampling_required"] is True
        assert record["mobile_legibility"]["mobile_preview_required"] is True
        assert record["reduced_motion"]["variant_required"] is True


def test_mask_reveal_scopes_are_distinct_not_duplicate_behavior() -> None:
    payloads = _load_capability_payloads()
    transition = next(
        item
        for item in payloads["transition_grammar.json"]["capabilities"]
        if item["id"] == "mask_reveal"
    )
    typography = next(
        item
        for item in payloads["kinetic_typography.json"]["capabilities"]
        if item["id"] == "mask_reveal"
    )
    assert transition["qualified_id"] == "transition.mask_reveal"
    assert typography["qualified_id"] == "kinetic_typography.mask_reveal"
    assert "hai shot" in transition["summary_vi"].casefold()
    assert "chữ" in typography["summary_vi"].casefold()


def test_missing_field_unknown_readiness_empty_text_and_changed_locks_rejected() -> None:
    original = copy.deepcopy(
        _load_capability_payloads()["transition_grammar.json"]["capabilities"][0]
    )
    missing = copy.deepcopy(original)
    del missing["failure_conditions"]
    _assert_rejected(missing, "transition")
    readiness = copy.deepcopy(original)
    readiness["readiness"] = "PRODUCTION_READY"
    _assert_rejected(readiness, "transition")
    empty = copy.deepcopy(original)
    empty["summary_vi"] = ""
    _assert_rejected(empty, "transition")
    for key, expected in LOCKS.items():
        changed = copy.deepcopy(original)
        changed[key] = not expected
        _assert_rejected(changed, "transition")


def test_local_mapping_has_exact_technologies_and_all_42_scoped_capabilities() -> None:
    payload = _load_mapping_payload()
    assert tuple(payload) == MAPPING_ENVELOPE_FIELDS
    assert payload["schema_version"] == "1.0.0"
    assert payload["pack_id"] == "local-video-transition-motion"
    assert payload["technology_count"] == 7
    assert payload["capability_mapping_count"] == 42
    technologies = payload["technologies"]
    assert tuple(item["id"] for item in technologies) == TECHNOLOGY_IDS
    for technology in technologies:
        assert tuple(technology) == TECHNOLOGY_FIELDS
        assert technology["inventory_status"] == TECHNOLOGY_STATUS[technology["id"]]
        assert technology["relationship"] == "metadata_only"
        assert _contains_vietnamese(technology["notes_vi"])
        for reference in technology["evidence_refs"]:
            _validate_reference(reference)
    mappings = payload["mappings"]
    assert tuple(item["qualified_id"] for item in mappings) == _qualified_ids()
    assert len({item["qualified_id"] for item in mappings}) == 42
    for mapping in mappings:
        assert tuple(mapping) == MAPPING_FIELDS
        assert mapping["group_id"] in GROUP_FIELD_ORDERS
        assert mapping["qualified_id"] == (
            f"{mapping['group_id']}.{mapping['capability_id']}"
        )
        assert mapping["primary_technology"] in TECHNOLOGY_IDS
        assert isinstance(mapping["supporting_technologies"], list)
        assert set(mapping["supporting_technologies"]) <= set(TECHNOLOGY_IDS)
        assert mapping["primary_technology"] not in mapping["supporting_technologies"]
        assert _contains_vietnamese(mapping["realization_notes_vi"])
        assert _contains_vietnamese(mapping["limitations_vi"])
        assert mapping["readiness"] in READINESS
        assert mapping["relationship"] == "metadata_only"
        assert mapping["production_renderer_changed"] is False


def test_absent_javascript_runtimes_never_claim_local_execution() -> None:
    payload = _load_mapping_payload()
    status = {item["id"]: item["inventory_status"] for item in payload["technologies"]}
    assert status["remotion"] == "NOT_INSTALLED"
    assert status["gsap"] == "NOT_INSTALLED"
    assert status["hyperframes"] == "NOT_INSTALLED"
    for mapping in payload["mappings"]:
        if mapping["primary_technology"] in {"remotion", "gsap", "hyperframes"}:
            assert mapping["readiness"] in {"CONTRACT_ONLY", "REQUIRES_RUNTIME"}


def test_existing_references_are_relative_tracked_metadata_only() -> None:
    references = _all_references()
    assert references
    tracked = _tracked_repository_paths()
    root = ROOT.resolve()
    for reference in references:
        _validate_reference(reference)
        relative_path = reference["path"]
        assert relative_path in tracked
        resolved = (ROOT / relative_path).resolve()
        assert resolved.is_relative_to(root)
        assert resolved.is_file()


def test_declared_python_reference_symbols_resolve_at_module_top_level() -> None:
    for reference in _all_references():
        symbols = reference["symbols"]
        path = ROOT / reference["path"]
        if not symbols or path.suffix != ".py":
            continue
        available = _top_level_python_symbols(path)
        assert set(symbols) <= available, (
            reference["path"],
            sorted(set(symbols) - available),
        )


def test_json_is_utf8_without_bom_and_deterministic_two_space_format() -> None:
    _require_complete_pack()
    for filename in JSON_FILENAMES:
        path = SKILL_ROOT / filename
        raw = path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), filename
        text = path.read_text(encoding="utf-8")
        payload = json.loads(text)
        assert text == json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def test_skill_markdown_frontmatter_and_relative_links_are_exact() -> None:
    _require_complete_pack()
    text = SKILL_PATH.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines and lines[0] == "---"
    frontmatter_end = lines.index("---", 1)
    frontmatter = {}
    for line in lines[1:frontmatter_end]:
        key, value = line.split(":", 1)
        frontmatter[key.strip()] = value.strip()
    assert set(frontmatter) == {"name", "description"}
    assert frontmatter["name"] == "local-video-transition-motion"
    assert frontmatter["description"]
    links = tuple(re.findall(r"\[[^\]]+\]\(([^)]+)\)", text))
    required_links = {
        *JSON_FILENAMES,
        "../local-video-filmmaking/rights_requirements.json",
        "../../../docs/superpowers/specs/2026-07-29-localvideostudio26d-transition-motion-pack-design.md",
    }
    assert required_links <= set(links)
    root = ROOT.resolve()
    for target in links:
        relative_target = target.split("#", 1)[0]
        assert relative_target and "\\" not in relative_target
        assert not re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", relative_target)
        assert not relative_target.startswith(("/", "\\"))
        resolved = (SKILL_ROOT / relative_target).resolve()
        assert resolved.is_relative_to(root)
        assert resolved.is_file(), target


def test_pack_contains_no_secrets_network_provider_tasks_or_ui_runtime_wiring() -> None:
    _require_complete_pack()
    combined = "\n".join(path.read_text(encoding="utf-8") for path in _approved_paths())
    for pattern in FORBIDDEN_CONTENT_PATTERNS:
        assert re.search(pattern, combined) is None, pattern


def test_static_contract_test_process_is_only_read_only_git_inventory() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "subprocess"
    ]
    assert len(calls) == 1
    call = calls[0]
    assert call.func.attr == "run"
    assert ast.unparse(call.args[0]) == (
        "['git', '-C', str(ROOT), 'ls-files', '--cached']"
    )


def test_26d_test_does_not_call_provider_renderer_or_generation() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    called_names: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            called_names.append(node.func.id.casefold())
        elif isinstance(node.func, ast.Attribute):
            called_names.append(node.func.attr.casefold())
    assert not any(
        "provider" in name
        or "renderer" in name
        or "generation" in name
        or name.startswith("render")
        for name in called_names
    )
