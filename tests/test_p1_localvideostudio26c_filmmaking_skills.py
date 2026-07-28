import ast
import copy
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from unittest import SkipTest


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "video" / "local-video-filmmaking"
SKILL_PATH = SKILL_ROOT / "SKILL.md"

EDITING_IDS = (
    "standard_cut",
    "jump_cut",
    "j_cut",
    "l_cut",
    "cut_on_action",
    "cross_cut",
    "cutaway",
    "montage",
    "match_cut",
    "smash_cut",
    "insert_shot",
    "reaction_cut",
    "parallel_editing",
)

FRAMING_IDS = (
    "rule_of_thirds",
    "central_composition",
    "symmetry",
    "intentional_imbalance",
    "headroom",
    "lead_room",
    "negative_space",
    "foreground_midground_background",
    "frame_within_frame",
    "depth_layers",
    "subject_separation",
    "eyeline",
    "screen_direction",
    "180_degree_rule",
    "30_degree_rule",
    "shot_size_progression",
    "camera_height",
    "lens_perspective_awareness",
    "safe_area",
    "platform_reframing",
)

PACING_IDS = (
    "hook_first_three_seconds",
    "shot_duration_rhythm",
    "information_density",
    "beat_mapping",
    "visual_escalation",
    "pattern_interrupt",
    "setup_payoff",
    "b_roll_motivation",
    "continuity",
    "emotional_arc",
    "cta_end_card",
)

CAMERA_IDS = (
    "static",
    "pan",
    "tilt",
    "push_in",
    "pull_out",
    "dolly",
    "truck",
    "orbit",
    "crane",
    "handheld",
    "parallax",
    "rack_focus_simulation",
    "whip_motion",
    "match_motion",
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
    "editing_grammar.json": ("editing_grammar", EDITING_IDS),
    "framing_composition.json": ("framing_composition", FRAMING_IDS),
    "pacing_storytelling.json": ("pacing_storytelling", PACING_IDS),
    "camera_movement.json": ("camera_movement", CAMERA_IDS),
}
JSON_FILENAMES = (*CAPABILITY_FILES, "rights_requirements.json")
APPROVED_FILENAMES = ("SKILL.md", *JSON_FILENAMES)

CAPABILITY_TOP_LEVEL_FIELDS = (
    "schema_version",
    "pack_id",
    "group_id",
    "capability_count",
    "capabilities",
)
REQUIRED_FIELD_ORDER = (
    "id",
    "display_name_vi",
    "summary_vi",
    "category",
    "purpose",
    "use_when",
    "avoid_when",
    "required_inputs",
    "shot_requirements",
    "audio_behavior",
    "timing_guidance",
    "continuity_rules",
    "aspect_ratio_notes",
    "failure_modes",
    "fallbacks",
    "validation_checks",
    "existing_capability_refs",
    "inventory_status",
    "source_dependency",
    "readiness",
    "rights_requirement_ids",
    "planning_only",
    "runtime_registered",
    "provider_executable",
    "public_ui",
)
REQUIRED_FIELDS = frozenset(REQUIRED_FIELD_ORDER)
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
INVENTORY_STATUSES = frozenset(
    {"EXISTING_AND_VALID", "EXISTING_BUT_INCOMPLETE", "MISSING"}
)
INVENTORY_IDS = {
    "EXISTING_AND_VALID": frozenset(
        {
            "jump_cut",
            "cut_on_action",
            "cutaway",
            "match_cut",
            "reaction_cut",
            "negative_space",
            "safe_area",
            "platform_reframing",
            "hook_first_three_seconds",
            "shot_duration_rhythm",
            "visual_escalation",
            "pattern_interrupt",
            "setup_payoff",
            "b_roll_motivation",
            "continuity",
            "emotional_arc",
            "cta_end_card",
            "static",
            "pan",
            "push_in",
            "pull_out",
            "dolly",
            "orbit",
            "crane",
            "handheld",
            "parallax",
        }
    ),
    "EXISTING_BUT_INCOMPLETE": frozenset(
        {
            "standard_cut",
            "j_cut",
            "l_cut",
            "montage",
            "smash_cut",
            "insert_shot",
            "central_composition",
            "symmetry",
            "intentional_imbalance",
            "foreground_midground_background",
            "depth_layers",
            "subject_separation",
            "eyeline",
            "screen_direction",
            "shot_size_progression",
            "camera_height",
            "lens_perspective_awareness",
            "information_density",
            "beat_mapping",
            "tilt",
            "truck",
            "whip_motion",
            "match_motion",
        }
    ),
    "MISSING": frozenset(
        {
            "cross_cut",
            "parallel_editing",
            "rule_of_thirds",
            "headroom",
            "lead_room",
            "frame_within_frame",
            "180_degree_rule",
            "30_degree_rule",
            "rack_focus_simulation",
        }
    ),
}
SOURCE_DEPENDENCIES = frozenset(
    {
        "COMPATIBLE_FOOTAGE_REQUIRED",
        "PLANNED_SHOOT_RECOMMENDED",
        "PLANNED_SHOOT_REQUIRED",
        "SIMULATION_LIMITED",
    }
)
NARRATIVE_FIELDS = (
    "purpose",
    "use_when",
    "avoid_when",
    "required_inputs",
    "shot_requirements",
    "audio_behavior",
    "timing_guidance",
    "continuity_rules",
    "aspect_ratio_notes",
    "failure_modes",
    "fallbacks",
    "validation_checks",
)

RIGHTS_TOP_LEVEL_FIELDS = (
    "schema_version",
    "pack_id",
    "declaration_count",
    "required_plan_key",
    "verification_values",
    "unknown_or_restricted_action",
    "declarations",
)
RIGHTS_DECLARATION_FIELDS = frozenset(
    {
        "id",
        "required",
        "purpose",
        "accepted_evidence",
        "plan_fields",
        "unknown_action",
        "existing_capability_refs",
    }
)
RIGHTS_PLAN_FIELDS = (
    "declared_value",
    "verification",
    "evidence",
    "restrictions",
    "notes",
)
RIGHTS_VERIFICATION_VALUES = (
    "VERIFIED",
    "NOT_APPLICABLE",
    "RESTRICTED",
    "UNKNOWN",
)
BLOCK_EXECUTION = "KEEP_PLANNING_ONLY_AND_BLOCK_EXECUTION"

REFERENCE_FIELD_ORDER = (
    "path",
    "symbols",
    "support_layer",
    "relationship",
    "notes",
)
SUPPORT_LAYERS = frozenset(
    {"knowledge", "prompt", "planner", "capability_catalog", "local_edit", "policy"}
)

TRUE_CAMERA_MOVE_IDS = (
    "pan",
    "tilt",
    "push_in",
    "pull_out",
    "dolly",
    "truck",
    "orbit",
    "crane",
    "handheld",
)

VIETNAMESE_MARKERS = frozenset(
    "ăâđêôơưĂÂĐÊÔƠƯ"
    "àáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩị"
    "òóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ"
    "ÀÁẢÃẠẰẮẲẴẶẦẤẨẪẬÈÉẺẼẸỀẾỂỄỆÌÍỈĨỊ"
    "ÒÓỎÕỌỒỐỔỖỘỜỚỞỠỢÙÚỦŨỤỪỨỬỮỰỲÝỶỸỴ"
)

FORBIDDEN_CONTENT_PATTERNS = (
    r"(?i)https?://",
    r"(?i)(?:^|[^A-Za-z])(?:[A-Za-z]:[\\/]|/(?:home|users|root)/|\\\\)",
    r"(?i)\b(?:api[_-]?key|client[_-]?secret|password|private[_-]?key)\b",
    r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+",
    r"(?im)^\s*(?:from|import)\s+(?:bot|services|workers?|providers?)\b",
    r"(?i)\b(?:requests|httpx)\.(?:get|post|put|patch|delete|request)\s*\(",
    r"(?i)\b(?:provider[_-]?model(?:[_-]?id)?|model[_-]?id|provider[_-]?endpoint)\b",
    r"(?i)\b(?:task[_-]?id|job[_-]?id|provider[_-]?task[_-]?id)\b",
    r"(?i)\b(?:callback[_-]?(?:data|query|handler)|conversationhandler|inlinekeyboard)\b",
    r"(?i)\b(?:context\.user_data|state[_-]?machine|back[_-]?stack|backstack)\b",
    r"(?i)\b(?:register[_-]?handler|add_handler|runtime[_-]?registry)\b",
)


def _approved_paths() -> tuple[Path, ...]:
    return tuple(SKILL_ROOT / name for name in APPROVED_FILENAMES)


def _missing_approved_paths() -> tuple[Path, ...]:
    return tuple(path for path in _approved_paths() if not path.is_file())


def _require_complete_pack() -> None:
    missing = _missing_approved_paths()
    if missing:
        relative = ", ".join(path.relative_to(ROOT).as_posix() for path in missing)
        raise SkipTest(f"filmmaking skill pack is not installed: {relative}")


def _read_json(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    payload = json.loads(text)
    assert isinstance(payload, dict), path
    return payload


def _load_capability_payloads() -> dict[str, dict[str, object]]:
    _require_complete_pack()
    return {
        filename: _read_json(SKILL_ROOT / filename)
        for filename in CAPABILITY_FILES
    }


def _load_rights_payload() -> dict[str, object]:
    _require_complete_pack()
    return _read_json(SKILL_ROOT / "rights_requirements.json")


def _records_by_id(payload: dict[str, object]) -> dict[str, dict[str, object]]:
    capabilities = payload["capabilities"]
    assert isinstance(capabilities, list)
    return {record["id"]: record for record in capabilities}


def _text_values(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, dict):
        return tuple(
            text
            for nested in value.values()
            for text in _text_values(nested)
        )
    if isinstance(value, (list, tuple)):
        return tuple(text for nested in value for text in _text_values(nested))
    return ()


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


def _contains_vietnamese(value: object) -> bool:
    return any(
        marker in text
        for text in _text_values(value)
        for marker in VIETNAMESE_MARKERS
    )


def _nested_values_for_key(value: object, expected_key: str) -> tuple[object, ...]:
    if isinstance(value, dict):
        matches = tuple(
            nested for key, nested in value.items() if key == expected_key
        )
        descendants = tuple(
            match
            for nested in value.values()
            for match in _nested_values_for_key(nested, expected_key)
        )
        return matches + descendants
    if isinstance(value, (list, tuple)):
        return tuple(
            match
            for nested in value
            for match in _nested_values_for_key(nested, expected_key)
        )
    return ()


def _validate_reference(reference: object) -> None:
    assert isinstance(reference, dict)
    assert tuple(reference) == REFERENCE_FIELD_ORDER
    path = reference["path"]
    symbols = reference["symbols"]
    assert isinstance(path, str) and path.strip() == path and path
    assert "\\" not in path
    pure_path = PurePosixPath(path)
    assert not pure_path.is_absolute()
    assert ".." not in pure_path.parts
    assert reference["support_layer"] in SUPPORT_LAYERS
    assert reference["relationship"] == "metadata_only"
    assert isinstance(symbols, list)
    assert all(isinstance(symbol, str) and symbol.strip() for symbol in symbols)
    assert isinstance(reference["notes"], str) and reference["notes"].strip()
    assert _contains_vietnamese(reference["notes"])


def _validate_capability(record: dict[str, object]) -> None:
    assert tuple(record) == REQUIRED_FIELD_ORDER
    assert set(record) == REQUIRED_FIELDS
    assert isinstance(record["id"], str)
    assert re.fullmatch(r"[a-z0-9]+(?:_[a-z0-9]+)*", record["id"])
    assert isinstance(record["display_name_vi"], str)
    assert isinstance(record["summary_vi"], str)
    assert record["display_name_vi"].strip()
    assert record["summary_vi"].strip()
    assert _contains_vietnamese(record["display_name_vi"])
    assert _contains_vietnamese(record["summary_vi"])
    assert isinstance(record["category"], str) and record["category"].strip()
    for field in NARRATIVE_FIELDS:
        _assert_nonempty(record[field])
        assert _contains_vietnamese(record[field]), field
    references = record["existing_capability_refs"]
    assert isinstance(references, list)
    for reference in references:
        _validate_reference(reference)
    assert record["inventory_status"] in INVENTORY_STATUSES
    assert record["source_dependency"] in SOURCE_DEPENDENCIES
    assert record["readiness"] in READINESS
    assert tuple(record["rights_requirement_ids"]) == RIGHTS_IDS
    for key, expected in LOCKS.items():
        assert record[key] is expected


def _assert_rejected(record: dict[str, object]) -> None:
    try:
        _validate_capability(record)
    except AssertionError:
        return
    raise AssertionError("mutated capability unexpectedly passed validation")


def _all_references() -> tuple[dict[str, object], ...]:
    payloads = _load_capability_payloads()
    references: list[dict[str, object]] = []
    for payload in payloads.values():
        for record in payload["capabilities"]:
            references.extend(record["existing_capability_refs"])
    for declaration in _load_rights_payload()["declarations"]:
        references.extend(declaration["existing_capability_refs"])
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
    assert not missing, "approved filmmaking files are absent: " + ", ".join(
        path.relative_to(ROOT).as_posix() for path in missing
    )
    actual = {
        path.relative_to(SKILL_ROOT).as_posix()
        for path in SKILL_ROOT.rglob("*")
        if path.is_file()
    }
    assert actual == set(APPROVED_FILENAMES)


def test_contract_test_imports_only_the_python_standard_library() -> None:
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


def test_capability_envelopes_exact_ids_fields_counts_and_global_uniqueness() -> None:
    payloads = _load_capability_payloads()
    all_ids: list[str] = []
    for filename, (group_id, expected_ids) in CAPABILITY_FILES.items():
        payload = payloads[filename]
        assert tuple(payload) == CAPABILITY_TOP_LEVEL_FIELDS
        assert payload["schema_version"] == "1.0.0"
        assert payload["pack_id"] == "local-video-filmmaking"
        assert payload["group_id"] == group_id
        assert payload["capability_count"] == len(expected_ids)
        capabilities = payload["capabilities"]
        assert isinstance(capabilities, list)
        assert tuple(record["id"] for record in capabilities) == expected_ids
        for record in capabilities:
            _validate_capability(record)
        all_ids.extend(record["id"] for record in capabilities)
    assert len(all_ids) == 58
    assert len(set(all_ids)) == 58
    assert len(set((*all_ids, *RIGHTS_IDS))) == 66


def test_inventory_classification_is_exact_for_all_58_capabilities() -> None:
    actual = {status: set() for status in INVENTORY_IDS}
    for payload in _load_capability_payloads().values():
        for record in payload["capabilities"]:
            actual[record["inventory_status"]].add(record["id"])
    assert {status: frozenset(ids) for status, ids in actual.items()} == INVENTORY_IDS
    assert {status: len(ids) for status, ids in actual.items()} == {
        "EXISTING_AND_VALID": 26,
        "EXISTING_BUT_INCOMPLETE": 23,
        "MISSING": 9,
    }


def test_rights_contract_has_all_eight_required_declarations_once() -> None:
    payload = _load_rights_payload()
    assert tuple(payload) == RIGHTS_TOP_LEVEL_FIELDS
    assert payload["schema_version"] == "1.0.0"
    assert payload["pack_id"] == "local-video-filmmaking"
    assert payload["declaration_count"] == len(RIGHTS_IDS)
    assert payload["required_plan_key"] == "rights"
    assert tuple(payload["verification_values"]) == RIGHTS_VERIFICATION_VALUES
    assert payload["unknown_or_restricted_action"] == BLOCK_EXECUTION
    declarations = payload["declarations"]
    assert isinstance(declarations, list)
    assert tuple(declaration["id"] for declaration in declarations) == RIGHTS_IDS
    assert len({declaration["id"] for declaration in declarations}) == len(RIGHTS_IDS)
    for declaration in declarations:
        assert set(declaration) == RIGHTS_DECLARATION_FIELDS
        assert declaration["required"] is True
        assert declaration["unknown_action"] == BLOCK_EXECUTION
        assert tuple(declaration["plan_fields"]) == RIGHTS_PLAN_FIELDS
        _assert_nonempty(declaration["purpose"])
        _assert_nonempty(declaration["accepted_evidence"])
        assert _contains_vietnamese(declaration["purpose"])
        assert _contains_vietnamese(declaration["accepted_evidence"])
        references = declaration["existing_capability_refs"]
        assert isinstance(references, list)
        for reference in references:
            _validate_reference(reference)


def test_missing_required_field_mutation_is_rejected() -> None:
    record = copy.deepcopy(
        _load_capability_payloads()["editing_grammar.json"]["capabilities"][0]
    )
    del record["failure_modes"]
    _assert_rejected(record)


def test_unknown_readiness_mutation_is_rejected() -> None:
    record = copy.deepcopy(
        _load_capability_payloads()["editing_grammar.json"]["capabilities"][0]
    )
    record["readiness"] = "PRODUCTION_READY"
    _assert_rejected(record)


def test_empty_vietnamese_text_mutation_is_rejected() -> None:
    record = copy.deepcopy(
        _load_capability_payloads()["editing_grammar.json"]["capabilities"][0]
    )
    record["summary_vi"] = ""
    _assert_rejected(record)


def test_each_changed_planning_lock_mutation_is_rejected() -> None:
    original = _load_capability_payloads()["editing_grammar.json"]["capabilities"][0]
    for key, expected in LOCKS.items():
        record = copy.deepcopy(original)
        record[key] = not expected
        _assert_rejected(record)


def test_j_cut_and_l_cut_have_opposite_audio_picture_boundaries() -> None:
    editing = _records_by_id(_load_capability_payloads()["editing_grammar.json"])
    j_cut = editing["j_cut"]
    l_cut = editing["l_cut"]
    assert j_cut["audio_behavior"]["starts_before_picture_cut"] is True
    assert j_cut["audio_behavior"]["continues_after_picture_cut"] is False
    assert l_cut["audio_behavior"]["starts_before_picture_cut"] is False
    assert l_cut["audio_behavior"]["continues_after_picture_cut"] is True


def test_composition_semantics_preserve_axis_optional_guidance_and_crop_limits() -> None:
    framing = _records_by_id(
        _load_capability_payloads()["framing_composition.json"]
    )
    assert "180_degree_rule" in _text_values(
        framing["screen_direction"]["continuity_rules"]
    )
    thirds = framing["rule_of_thirds"]
    assert False in _nested_values_for_key(thirds, "mandatory")
    assert True in _nested_values_for_key(thirds, "guidance_only")
    reframing = framing["platform_reframing"]
    assert False in _nested_values_for_key(reframing, "universal_safe_crop")


def test_true_camera_moves_require_planned_capture_and_rack_focus_is_simulation() -> None:
    camera = _records_by_id(_load_capability_payloads()["camera_movement.json"])
    for capability_id in TRUE_CAMERA_MOVE_IDS:
        record = camera[capability_id]
        assert record["readiness"] == "REQUIRES_PLANNED_SHOOT"
        assert record["source_dependency"] == "PLANNED_SHOOT_REQUIRED"
    rack_focus = camera["rack_focus_simulation"]
    assert True in _nested_values_for_key(rack_focus, "simulation_only")
    assert False in _nested_values_for_key(rack_focus, "physical_optical_focus")
    rack_focus_text = " ".join(_text_values(rack_focus)).casefold()
    assert "mô phỏng" in rack_focus_text
    assert "quang học" in rack_focus_text


def test_existing_capability_references_are_relative_tracked_metadata_only() -> None:
    references = _all_references()
    assert references
    tracked_paths = _tracked_repository_paths()
    root = ROOT.resolve()
    for reference in references:
        _validate_reference(reference)
        relative_path = reference["path"]
        assert relative_path in tracked_paths
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


def test_json_is_utf8_without_bom_and_has_deterministic_two_space_format() -> None:
    _require_complete_pack()
    for filename in JSON_FILENAMES:
        path = SKILL_ROOT / filename
        raw = path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), filename
        text = path.read_text(encoding="utf-8")
        payload = json.loads(text)
        expected = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        assert text == expected, filename


def test_skill_markdown_uses_only_resolving_relative_links() -> None:
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
    assert frontmatter["name"] == "local-video-filmmaking"
    assert frontmatter["description"]

    links = tuple(re.findall(r"\[[^\]]+\]\(([^)]+)\)", text))
    required_links = {
        *JSON_FILENAMES,
        "../../../docs/superpowers/specs/2026-07-28-localvideostudio26c-filmmaking-skills-design.md",
    }
    assert required_links <= set(links)
    root = ROOT.resolve()
    for target in links:
        relative_target = target.split("#", 1)[0]
        assert relative_target
        assert not re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", relative_target)
        assert not relative_target.startswith(("/", "\\"))
        assert "\\" not in relative_target
        resolved = (SKILL_ROOT / relative_target).resolve()
        assert resolved.is_relative_to(root)
        assert resolved.is_file(), target


def test_skill_requires_notes_reason_when_rights_are_not_applicable() -> None:
    text = SKILL_PATH.read_text(encoding="utf-8")
    assert re.search(r"`NOT_APPLICABLE`[^\n.]*`notes`", text)


def test_static_contract_loader_makes_zero_provider_or_renderer_calls() -> None:
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
        "provider" in name or "renderer" in name or name.startswith("render")
        for name in called_names
    )


def test_contract_test_process_execution_is_only_read_only_git_inventory() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    process_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "subprocess"
    ]
    assert len(process_calls) == 1
    call = process_calls[0]
    assert call.func.attr == "run"
    assert len(call.args) == 1 and isinstance(call.args[0], ast.List)
    command = call.args[0].elts
    assert [item.value for item in command[:2] if isinstance(item, ast.Constant)] == [
        "git",
        "-C",
    ]
    assert ast.unparse(command[2]) == "str(ROOT)"
    assert [item.value for item in command[3:] if isinstance(item, ast.Constant)] == [
        "ls-files",
        "--cached",
    ]
    keywords = {keyword.arg: keyword.value for keyword in call.keywords}
    assert "shell" not in keywords
    for name in ("check", "capture_output", "text"):
        assert isinstance(keywords.get(name), ast.Constant)
        assert keywords[name].value is True


def test_pack_contains_no_secrets_provider_tasks_or_runtime_ui_wiring() -> None:
    _require_complete_pack()
    combined = "\n".join(
        path.read_text(encoding="utf-8") for path in _approved_paths()
    )
    for pattern in FORBIDDEN_CONTENT_PATTERNS:
        assert re.search(pattern, combined) is None, pattern
