import ast
import copy
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from unittest import SkipTest


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "video" / "local-video-sound-design"
SKILL_PATH = SKILL_ROOT / "SKILL.md"
RIGHTS_PATH = (
    ROOT
    / "skills"
    / "video"
    / "local-video-filmmaking"
    / "rights_requirements.json"
)

LAYER_IDS = (
    "dialogue_or_narration",
    "room_tone",
    "ambience",
    "foley",
    "impact",
    "riser",
    "whoosh",
    "transition_accent",
    "music_bed",
    "silence",
)
OPERATION_IDS = (
    "dialogue_cleanup",
    "noise_reduction",
    "high_pass_filter",
    "de_essing",
    "compression",
    "limiting",
    "normalization",
    "music_ducking",
    "crossfade",
    "fade_in_out",
    "stereo_balance",
    "mono_compatibility",
    "loudness_measurement",
    "true_peak_check",
)
TIMELINE_FIELDS = (
    "dialogue",
    "ambience",
    "foley",
    "impact",
    "riser",
    "whoosh",
    "music_cue",
    "ducking_envelope",
    "silence_window",
)
LOUDNESS_PROFILE_IDS = (
    "short_form_social",
    "long_form_video",
    "spoken_word_video",
    "podcast_stereo",
    "podcast_mono",
)
QA_IDS = (
    "audio_stream_present",
    "decodable_duration",
    "silence_ratio",
    "clipping",
    "loudness",
    "true_peak",
    "dialogue_intelligibility",
    "channel_layout",
    "mono_compatibility",
    "timeline_alignment",
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

JSON_FILENAMES = (
    "sound_layers.json",
    "audio_post_operations.json",
    "platform_loudness_profiles.json",
    "sound_timeline_contract.json",
    "audio_qa_contract.json",
)
APPROVED_FILENAMES = ("SKILL.md", *JSON_FILENAMES)

CAPABILITY_ENVELOPE_FIELDS = (
    "schema_version",
    "pack_id",
    "group_id",
    "capability_count",
    "rights_contract_ref",
    "music_suno_policy",
    "capabilities",
)
LAYER_FIELDS = (
    "id",
    "qualified_id",
    "display_name_vi",
    "purpose_vi",
    "required_inputs",
    "timing_guidance",
    "level_guidance",
    "interaction_rules",
    "rights_requirement_ids",
    "avoid_when",
    "failure_modes",
    "validation_checks",
    "existing_capability_refs",
    "inventory_status",
    "readiness",
    "planning_only",
    "runtime_registered",
    "provider_executable",
    "public_ui",
)
OPERATION_FIELDS = (
    "id",
    "qualified_id",
    "display_name_vi",
    "purpose_vi",
    "required_inputs",
    "parameter_contract",
    "order_constraints",
    "intelligibility_policy",
    "fallback",
    "failure_modes",
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
REFERENCE_FIELDS = (
    "path",
    "symbols",
    "support_layer",
    "relationship",
    "notes_vi",
)
SUPPORT_LAYERS = frozenset(
    {
        "local_audio",
        "local_edit",
        "validation",
        "planner",
        "capability_catalog",
        "knowledge",
        "policy",
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
FORBIDDEN_CONTENT_PATTERNS = (
    r"(?i)https?://",
    r"(?i)\b(?:requests|httpx|urllib|wget|curl|yt[-_]?dlp)\b",
    r"(?i)\b(?:download|downloader|fetch_audio|urlopen)\b",
    r"(?i)\b(?:base64|subprocess|os\.system|Popen)\b",
    r"(?i)\b(?:api[_-]?key|client[_-]?secret|private[_-]?key|password)\b",
    r"(?i)[A-Z]:\\Users\\",
)


def _approved_paths() -> tuple[Path, ...]:
    return tuple(SKILL_ROOT / name for name in APPROVED_FILENAMES)


def _missing_paths() -> tuple[Path, ...]:
    return tuple(path for path in _approved_paths() if not path.is_file())


def _require_pack() -> None:
    missing = _missing_paths()
    if missing:
        raise SkipTest(
            "sound-design pack is not installed: "
            + ", ".join(path.relative_to(ROOT).as_posix() for path in missing)
        )


def _read_json(filename: str) -> dict[str, object]:
    _require_pack()
    payload = json.loads((SKILL_ROOT / filename).read_text(encoding="utf-8"))
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
    assert tuple(reference) == REFERENCE_FIELDS
    path = reference["path"]
    assert isinstance(path, str) and path.strip() == path and path
    assert "\\" not in path
    pure = PurePosixPath(path)
    assert not pure.is_absolute() and ".." not in pure.parts
    assert isinstance(reference["symbols"], list)
    assert all(isinstance(item, str) and item.strip() for item in reference["symbols"])
    assert reference["support_layer"] in SUPPORT_LAYERS
    assert reference["relationship"] == "metadata_only"
    assert _contains_vietnamese(reference["notes_vi"])


def _validate_locks(record: dict[str, object]) -> None:
    for key, expected in LOCKS.items():
        assert record[key] is expected


def _validate_capability(
    record: dict[str, object],
    *,
    group_id: str,
    field_order: tuple[str, ...],
) -> None:
    assert tuple(record) == field_order
    assert re.fullmatch(r"[a-z0-9]+(?:_[a-z0-9]+)*", record["id"])
    assert record["qualified_id"] == f"{group_id}.{record['id']}"
    for field in ("display_name_vi", "purpose_vi"):
        assert isinstance(record[field], str) and record[field].strip()
        assert _contains_vietnamese(record[field])
    assert record["inventory_status"] in INVENTORY_STATUSES
    assert record["readiness"] in READINESS
    assert tuple(record["rights_requirement_ids"]) == RIGHTS_IDS
    for reference in record["existing_capability_refs"]:
        _validate_reference(reference)
    _validate_locks(record)


def _all_references() -> tuple[dict[str, object], ...]:
    layer_payload = _read_json("sound_layers.json")
    operation_payload = _read_json("audio_post_operations.json")
    qa_payload = _read_json("audio_qa_contract.json")
    return tuple(
        reference
        for record in (
            *layer_payload["capabilities"],
            *operation_payload["capabilities"],
            *qa_payload["checks"],
        )
        for reference in record["existing_capability_refs"]
    )


def _tracked_paths() -> frozenset[str]:
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


def _python_symbols(path: Path) -> frozenset[str]:
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


def test_exact_approved_sound_design_files_exist_without_runtime_or_assets() -> None:
    missing = _missing_paths()
    assert not missing, "approved 26E files are absent: " + ", ".join(
        path.relative_to(ROOT).as_posix() for path in missing
    )
    actual = {
        path.relative_to(SKILL_ROOT).as_posix()
        for path in SKILL_ROOT.rglob("*")
        if path.is_file()
    }
    assert actual == set(APPROVED_FILENAMES)
    assert not {
        path
        for path in SKILL_ROOT.rglob("*")
        if path.is_file() and path.suffix.casefold() in FORBIDDEN_ASSET_EXTENSIONS
    }


def test_contract_test_imports_only_python_standard_library() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    assert roots <= sys.stdlib_module_names
    assert roots.isdisjoint({"bot", "services", "providers", "workers", "billing"})


def test_exact_layer_ids_counts_schema_rights_music_lock_and_locks() -> None:
    payload = _read_json("sound_layers.json")
    assert tuple(payload) == CAPABILITY_ENVELOPE_FIELDS
    assert payload["schema_version"] == "1.0.0"
    assert payload["pack_id"] == "local-video-sound-design"
    assert payload["group_id"] == "sound_layer"
    assert payload["capability_count"] == 10
    assert payload["rights_contract_ref"] == "../local-video-filmmaking/rights_requirements.json"
    assert (SKILL_ROOT / payload["rights_contract_ref"]).resolve() == RIGHTS_PATH.resolve()
    assert payload["music_suno_policy"]["status"] == "LOCKED_DISABLED"
    assert payload["music_suno_policy"]["generation_allowed"] is False
    assert payload["music_suno_policy"]["asset_acquisition_allowed"] is False
    records = payload["capabilities"]
    assert tuple(record["id"] for record in records) == LAYER_IDS
    assert len({record["id"] for record in records}) == 10
    for record in records:
        _validate_capability(record, group_id="sound_layer", field_order=LAYER_FIELDS)
        for field in (
            "required_inputs",
            "timing_guidance",
            "level_guidance",
            "interaction_rules",
            "avoid_when",
            "failure_modes",
            "validation_checks",
        ):
            _assert_nonempty(record[field])
            assert _contains_vietnamese(record[field])


def test_exact_operation_ids_counts_schema_intelligibility_and_locks() -> None:
    payload = _read_json("audio_post_operations.json")
    assert tuple(payload) == CAPABILITY_ENVELOPE_FIELDS
    assert payload["schema_version"] == "1.0.0"
    assert payload["pack_id"] == "local-video-sound-design"
    assert payload["group_id"] == "audio_post_operation"
    assert payload["capability_count"] == 14
    assert payload["music_suno_policy"]["status"] == "LOCKED_DISABLED"
    records = payload["capabilities"]
    assert tuple(record["id"] for record in records) == OPERATION_IDS
    assert len({record["id"] for record in records}) == 14
    for record in records:
        _validate_capability(
            record,
            group_id="audio_post_operation",
            field_order=OPERATION_FIELDS,
        )
        for field in (
            "required_inputs",
            "parameter_contract",
            "order_constraints",
            "intelligibility_policy",
            "fallback",
            "failure_modes",
            "validation_checks",
        ):
            _assert_nonempty(record[field])
            assert _contains_vietnamese(record[field])
        assert record["intelligibility_policy"]["dialogue_priority"] is True


def test_loudness_profiles_are_platform_config_not_one_universal_target() -> None:
    payload = _read_json("platform_loudness_profiles.json")
    assert payload["schema_version"] == "1.0.0"
    assert payload["pack_id"] == "local-video-sound-design"
    assert payload["contract_id"] == "platform_loudness_profiles"
    assert payload["universal_target_allowed"] is False
    assert payload["profile_count"] == 5
    assert payload["override_policy"]["explicit_platform_override_allowed"] is True
    profiles = payload["profiles"]
    assert tuple(profile["id"] for profile in profiles) == LOUDNESS_PROFILE_IDS
    assert len({profile["target_lufs_i"] for profile in profiles}) >= 3
    for profile in profiles:
        assert profile["platform_configuration_required"] is True
        assert isinstance(profile["target_lufs_i"], (int, float))
        assert isinstance(profile["max_true_peak_dbtp"], (int, float))
        assert _contains_vietnamese(profile["display_name_vi"])
        assert _contains_vietnamese(profile["notes_vi"])
    _validate_locks(payload)


def test_sound_timeline_contract_has_exact_scene_declarations_and_rights() -> None:
    payload = _read_json("sound_timeline_contract.json")
    assert payload["schema_version"] == "1.0.0"
    assert payload["pack_id"] == "local-video-sound-design"
    assert payload["contract_id"] == "sound_design_timeline"
    assert tuple(payload["scene_declaration_fields"]) == TIMELINE_FIELDS
    assert tuple(item["id"] for item in payload["field_contracts"]) == TIMELINE_FIELDS
    for item in payload["field_contracts"]:
        assert _contains_vietnamese(item["purpose_vi"])
        _assert_nonempty(item["required_keys"])
        _assert_nonempty(item["validation_rules"])
        assert tuple(item["rights_requirement_ids"]) == RIGHTS_IDS
    assert payload["music_suno_policy"]["status"] == "LOCKED_DISABLED"
    _validate_locks(payload)


def test_audio_qa_is_fail_closed_for_silence_clipping_and_missing_evidence() -> None:
    payload = _read_json("audio_qa_contract.json")
    assert payload["schema_version"] == "1.0.0"
    assert payload["pack_id"] == "local-video-sound-design"
    assert payload["contract_id"] == "audio_qa_no_fake_success"
    assert payload["qa_count"] == 10
    policy = payload["success_policy"]
    assert policy["silent_stream_success_allowed"] is False
    assert policy["clipped_stream_success_allowed"] is False
    assert policy["missing_evidence_action"] == "FAIL_CLOSED"
    checks = payload["checks"]
    assert tuple(check["id"] for check in checks) == QA_IDS
    assert len({check["id"] for check in checks}) == 10
    for check in checks:
        assert check["fail_closed"] is True
        assert _contains_vietnamese(check["purpose_vi"])
        _assert_nonempty(check["evidence_required"])
        assert _contains_vietnamese(check["pass_rule_vi"])
        for reference in check["existing_capability_refs"]:
            _validate_reference(reference)
    assert set(payload["ffmpeg_ffprobe_mapping"]["allowed_tools"]) == {"ffmpeg", "ffprobe"}
    assert payload["ffmpeg_ffprobe_mapping"]["execution_in_26e_allowed"] is False
    _validate_locks(payload)


def test_existing_references_are_relative_tracked_metadata_only_and_symbols_resolve() -> None:
    references = _all_references()
    assert references
    tracked = _tracked_paths()
    root = ROOT.resolve()
    for reference in references:
        _validate_reference(reference)
        relative = reference["path"]
        assert relative in tracked
        resolved = (ROOT / relative).resolve()
        assert resolved.is_relative_to(root) and resolved.is_file()
        if reference["symbols"] and resolved.suffix == ".py":
            assert set(reference["symbols"]) <= _python_symbols(resolved)


def test_skill_links_all_contracts_rights_and_design_with_resolving_relative_links() -> None:
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
    assert frontmatter["name"] == "local-video-sound-design"
    links = tuple(re.findall(r"\[[^\]]+\]\(([^)]+)\)", text))
    required = {
        *JSON_FILENAMES,
        "../local-video-filmmaking/rights_requirements.json",
        "../../../docs/superpowers/specs/2026-07-29-localvideostudio26e-sound-design-design.md",
    }
    assert required <= set(links)
    root = ROOT.resolve()
    for target in links:
        relative = target.split("#", 1)[0]
        assert relative and "\\" not in relative
        assert not relative.startswith(("/", "\\"))
        assert not re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", relative)
        resolved = (SKILL_ROOT / relative).resolve()
        assert resolved.is_relative_to(root) and resolved.is_file(), target


def test_json_utf8_deterministic_and_pack_has_no_asset_download_or_secret_code() -> None:
    _require_pack()
    for filename in JSON_FILENAMES:
        path = SKILL_ROOT / filename
        raw = path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf")
        text = path.read_text(encoding="utf-8")
        payload = json.loads(text)
        assert text == json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    combined = "\n".join(path.read_text(encoding="utf-8") for path in _approved_paths())
    for pattern in FORBIDDEN_CONTENT_PATTERNS:
        assert re.search(pattern, combined) is None, pattern


def test_changed_lock_or_production_readiness_mutation_is_rejected() -> None:
    payload = _read_json("sound_layers.json")
    original = payload["capabilities"][0]
    for key, expected in LOCKS.items():
        record = copy.deepcopy(original)
        record[key] = not expected
        try:
            _validate_capability(record, group_id="sound_layer", field_order=LAYER_FIELDS)
        except AssertionError:
            continue
        raise AssertionError(f"changed lock passed: {key}")
    record = copy.deepcopy(original)
    record["readiness"] = "PRODUCTION_READY"
    try:
        _validate_capability(record, group_id="sound_layer", field_order=LAYER_FIELDS)
    except AssertionError:
        return
    raise AssertionError("production readiness unexpectedly passed")


def test_static_contract_process_call_is_only_read_only_git_inventory() -> None:
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
    assert ast.unparse(calls[0].args[0]) == "['git', '-C', str(ROOT), 'ls-files', '--cached']"
