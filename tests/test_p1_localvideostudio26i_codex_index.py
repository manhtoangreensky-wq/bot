import ast
import json
import re
import subprocess
import sys
from pathlib import Path
from unittest import SkipTest


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "video" / "local-video-codex-index"
SKILL_PATH = SKILL_ROOT / "SKILL.md"
INDEX_PATH = SKILL_ROOT / "capability_index.json"

READINESS_STATES = (
    "NOT_INSTALLED",
    "INSTALLED",
    "CONTRACT_PASS",
    "LOCAL_DEMO_PASS",
    "PAID_SMOKE_REQUIRED",
    "PRODUCTION_READY",
    "PUBLIC",
)
RECORD_IDS = (
    "openmontage_local",
    "editing_grammar",
    "framing_composition",
    "pacing_storytelling",
    "camera_movement",
    "rights_requirements",
    "transition_motion_pack",
    "sound_design_pack",
    "viral_effects",
    "local_free_capabilities",
    "video_qa",
    "mosaic_motion",
    "higgsfield",
    "suno",
)
READINESS_CEILINGS = {
    "openmontage_local": "LOCAL_DEMO_PASS",
    "editing_grammar": "CONTRACT_PASS",
    "framing_composition": "CONTRACT_PASS",
    "pacing_storytelling": "CONTRACT_PASS",
    "camera_movement": "CONTRACT_PASS",
    "rights_requirements": "CONTRACT_PASS",
    "transition_motion_pack": "CONTRACT_PASS",
    "sound_design_pack": "CONTRACT_PASS",
    "viral_effects": "CONTRACT_PASS",
    "local_free_capabilities": "CONTRACT_PASS",
    "video_qa": "LOCAL_DEMO_PASS",
    "mosaic_motion": "PAID_SMOKE_REQUIRED",
    "higgsfield": "PAID_SMOKE_REQUIRED",
    "suno": "NOT_INSTALLED",
}
COUNTER_KEYS = (
    "provider_calls",
    "paid_provider_calls",
    "paid_generations",
    "motion_calls",
    "higgsfield_generation_calls",
    "wallet_mutations",
    "telegram_deliveries",
    "production_deploys",
    "vps_updates",
)
TOP_LEVEL_FIELDS = (
    "schema_version",
    "pack_id",
    "contract_id",
    "baseline_main_sha",
    "readiness_states",
    "readiness_definitions",
    "index_policy",
    "execution_counters",
    "capability_count",
    "capabilities",
    "planning_only",
    "runtime_registered",
    "provider_executable",
    "public_ui",
)
RECORD_FIELDS = (
    "capability_id",
    "display_name_vi",
    "location",
    "location_kind",
    "source_files",
    "status",
    "local_cloud",
    "free_paid",
    "required_tools",
    "requires_planned_shoot",
    "requires_explicit_confirmation",
    "test_command",
    "highest_readiness",
    "production_readiness",
    "version_or_sha",
    "official_source",
    "capability_count",
    "capability_ids",
    "evidence",
    "notes_vi",
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
STATUSES = {
    "VERIFIED_LOCAL",
    "VERIFIED_REPOSITORY",
    "VERIFIED_COMMAND",
    "OWNER_REPORTED",
    "LOCKED_DISABLED",
}
LOCAL_CLOUD = {"LOCAL", "LOCAL_METADATA_ONLY", "EXTERNAL_CLOUD"}
FREE_PAID = {
    "FREE_OPEN_SOURCE",
    "FREE_LOCAL",
    "FREE_LOCAL_WITH_DEFERRED_MODELS",
    "PAID_DISABLED",
}
SHOOT_VALUES = {"NO", "OPTIONAL", "REQUIRED", "VARIES_BY_CAPABILITY"}
APPROVED_FILENAMES = {"SKILL.md", "capability_index.json"}
VIETNAMESE_MARKERS = tuple(
    "ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ"
)
OPENMONTAGE_PATH = "C:/Users/toann/Documents/Codex/tools/OpenMontage"
OPENMONTAGE_SHA = "c36e41223e819441748817105635ac4036d41b10"
OPENMONTAGE_REMOTE = "https://github.com/calesthio/OpenMontage.git"
BASELINE_SHA = "599470bd55acdecd22f196004f60e0c3b3182b23"

SOURCE_GROUPS = {
    "editing_grammar": (("skills/video/local-video-filmmaking/editing_grammar.json", "editing_grammar", "capabilities"),),
    "framing_composition": (("skills/video/local-video-filmmaking/framing_composition.json", "framing_composition", "capabilities"),),
    "pacing_storytelling": (("skills/video/local-video-filmmaking/pacing_storytelling.json", "pacing_storytelling", "capabilities"),),
    "camera_movement": (("skills/video/local-video-filmmaking/camera_movement.json", "camera_movement", "capabilities"),),
    "rights_requirements": (("skills/video/local-video-filmmaking/rights_requirements.json", "rights", "declarations"),),
    "transition_motion_pack": (
        ("skills/video/local-video-transition-motion/transition_grammar.json", "transition", "capabilities"),
        ("skills/video/local-video-transition-motion/transition_audio.json", "transition_audio", "capabilities"),
        ("skills/video/local-video-transition-motion/motion_design_principles.json", "motion_design_principle", "capabilities"),
        ("skills/video/local-video-transition-motion/kinetic_typography.json", "kinetic_typography", "capabilities"),
    ),
    "sound_design_pack": (
        ("skills/video/local-video-sound-design/sound_layers.json", "sound_layer", "capabilities"),
        ("skills/video/local-video-sound-design/audio_post_operations.json", "audio_post_operation", "capabilities"),
        ("skills/video/local-video-sound-design/platform_loudness_profiles.json", "loudness_profile", "profiles"),
        ("skills/video/local-video-sound-design/sound_timeline_contract.json", "sound_timeline", "field_contracts"),
        ("skills/video/local-video-sound-design/audio_qa_contract.json", "audio_qa", "checks"),
    ),
    "viral_effects": (("skills/video/local-video-viral-effects/viral_effects.json", "viral_effect", "capabilities"),),
    "local_free_capabilities": (
        ("skills/video/local-video-local-capabilities/local_capabilities.json", "local_capability", "capabilities"),
        ("skills/video/local-video-local-capabilities/platform_delivery_profiles.json", "delivery_profile", "profiles"),
        ("skills/video/local-video-local-capabilities/heavy_gpu_inventory.json", "heavy_model", "models"),
    ),
    "video_qa": (("skills/video/local-video-video-qa/video_qa_contract.json", "video_qa", "checks"),),
}


def _require_pack() -> None:
    if not SKILL_ROOT.is_dir() or not SKILL_PATH.is_file() or not INDEX_PATH.is_file():
        raise SkipTest("26I capability index is not installed")


def _read_index() -> dict[str, object]:
    _require_pack()
    payload = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
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


def _nonempty(value: object) -> None:
    if isinstance(value, str):
        assert value.strip()
    elif isinstance(value, dict):
        assert value
        for key, nested in value.items():
            assert isinstance(key, str) and key.strip()
            _nonempty(nested)
    elif isinstance(value, (list, tuple)):
        assert value
        for nested in value:
            _nonempty(nested)
    else:
        assert value is not None


def _expected_ids(record_id: str) -> tuple[str, ...]:
    result: list[str] = []
    for path, namespace, list_key in SOURCE_GROUPS[record_id]:
        payload = json.loads((ROOT / path).read_text(encoding="utf-8"))
        result.extend(f"{namespace}.{item['id']}" for item in payload[list_key])
    return tuple(result)


def _validate_locks(record: dict[str, object]) -> None:
    for key, expected in LOCKS.items():
        assert record[key] is expected


def test_exact_26i_tree_exists_without_runtime_or_assets() -> None:
    assert SKILL_ROOT.is_dir(), "26I skill directory is absent"
    actual = {path.relative_to(SKILL_ROOT).as_posix() for path in SKILL_ROOT.rglob("*") if path.is_file()}
    assert actual == APPROVED_FILENAMES
    assert not {path for path in SKILL_ROOT.rglob("*") if path.suffix.casefold() in {".py", ".mp3", ".wav", ".mp4", ".mov", ".onnx", ".safetensors"}}


def test_contract_test_uses_only_python_standard_library() -> None:
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    assert roots <= sys.stdlib_module_names
    assert roots.isdisjoint({"bot", "services", "providers", "workers", "billing"})


def test_exact_index_envelope_readiness_and_global_locks() -> None:
    payload = _read_index()
    assert tuple(payload) == TOP_LEVEL_FIELDS
    assert payload["schema_version"] == "1.0.0"
    assert payload["pack_id"] == "local-video-codex-index"
    assert payload["contract_id"] == "codex_capability_index"
    assert payload["baseline_main_sha"] == BASELINE_SHA
    assert tuple(payload["readiness_states"]) == READINESS_STATES
    assert tuple(payload["readiness_definitions"]) == READINESS_STATES
    policy = payload["index_policy"]
    assert policy["installed_means_production_ready"] is False
    assert policy["implementation_copy_allowed"] is False
    assert policy["paid_auto_enable_allowed"] is False
    assert policy["automatic_fallback_allowed"] is False
    assert policy["missing_evidence_action"] == "DOWNGRADE_READINESS"
    assert policy["exact_state_evidence_required"] is True
    counters = payload["execution_counters"]
    assert tuple(counters) == COUNTER_KEYS
    for key in COUNTER_KEYS:
        assert counters[key] == 0
    _validate_locks(payload)


def test_exact_14_records_fields_status_and_no_production_inference() -> None:
    payload = _read_index()
    assert payload["capability_count"] == 14
    records = payload["capabilities"]
    assert tuple(record["capability_id"] for record in records) == RECORD_IDS
    assert len({record["capability_id"] for record in records}) == 14
    for record in records:
        assert tuple(record) == RECORD_FIELDS
        assert re.fullmatch(r"[a-z0-9]+(?:_[a-z0-9]+)*", record["capability_id"])
        assert _contains_vietnamese(record["display_name_vi"])
        assert _contains_vietnamese(record["notes_vi"])
        assert record["status"] in STATUSES
        assert record["local_cloud"] in LOCAL_CLOUD
        assert record["free_paid"] in FREE_PAID
        assert record["requires_planned_shoot"] in SHOOT_VALUES
        assert isinstance(record["requires_explicit_confirmation"], bool)
        assert record["highest_readiness"] == READINESS_CEILINGS[record["capability_id"]]
        assert record["production_readiness"] is False
        assert record["highest_readiness"] not in {"PRODUCTION_READY", "PUBLIC"}
        assert record["capability_count"] == len(record["capability_ids"])
        assert len(set(record["capability_ids"])) == record["capability_count"]
        _nonempty(record["required_tools"])
        _nonempty(record["test_command"])
        _nonempty(record["evidence"])
        _validate_locks(record)


def test_repository_groups_cover_every_current_source_id_without_duplication() -> None:
    records = {record["capability_id"]: record for record in _read_index()["capabilities"]}
    flattened: list[str] = []
    for record_id, groups in SOURCE_GROUPS.items():
        record = records[record_id]
        assert record["location_kind"] == "REPOSITORY_RELATIVE"
        expected_files = tuple(path for path, _, _ in groups)
        assert tuple(record["source_files"]) == expected_files
        assert tuple(record["capability_ids"]) == _expected_ids(record_id)
        for path in record["source_files"]:
            resolved = (ROOT / path).resolve()
            assert resolved.is_relative_to(ROOT.resolve()) and resolved.is_file()
        flattened.extend(record["capability_ids"])
    assert len(flattened) == len(set(flattened))
    assert len(flattened) == 244


def test_openmontage_path_remote_pin_evidence_and_readiness_are_exact() -> None:
    records = {record["capability_id"]: record for record in _read_index()["capabilities"]}
    record = records["openmontage_local"]
    assert record["location"] == OPENMONTAGE_PATH
    assert record["location_kind"] == "WORKSTATION_ABSOLUTE"
    assert record["version_or_sha"] == OPENMONTAGE_SHA
    assert record["official_source"] == OPENMONTAGE_REMOTE
    assert record["status"] == "VERIFIED_LOCAL"
    assert record["highest_readiness"] == "LOCAL_DEMO_PASS"
    assert record["free_paid"] == "FREE_OPEN_SOURCE"
    assert tuple(record["source_files"]) == ("CODEX.md", "AGENT_GUIDE.md", "PROJECT_CONTEXT.md", "LOCAL_INSTALLATION.md")
    evidence = record["evidence"]
    assert evidence["checkout_head"] == OPENMONTAGE_SHA
    assert evidence["license"] == "GNU AGPL-3.0"
    assert evidence["contract_tests"] == "620 passed, 7 skipped"
    assert evidence["local_demo"] == "projects/demos/renders/focusflow-pitch.mp4"
    assert evidence["demo_decode"] == "PASS"
    assert evidence["cloud_keys_configured"] == 0
    local = Path(OPENMONTAGE_PATH)
    if local.is_dir():
        assert (local / evidence["local_demo"]).is_file()
        head = subprocess.run(["git", "-C", str(local), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
        remote = subprocess.run(["git", "-C", str(local), "remote", "get-url", "origin"], check=True, capture_output=True, text=True).stdout.strip()
        assert head == OPENMONTAGE_SHA
        assert remote == OPENMONTAGE_REMOTE


def test_motion_higgsfield_and_suno_are_explicitly_paid_disabled_or_locked() -> None:
    records = {record["capability_id"]: record for record in _read_index()["capabilities"]}
    motion = records["mosaic_motion"]
    assert motion["status"] == "OWNER_REPORTED"
    assert motion["free_paid"] == "PAID_DISABLED"
    assert motion["test_command"] == "SKIP_PAID_SMOKE"
    assert motion["highest_readiness"] == "PAID_SMOKE_REQUIRED"
    assert motion["evidence"]["audit_action"] == "SKIPPED"
    assert motion["evidence"]["paid_calls"] == 0
    higgsfield = records["higgsfield"]
    assert higgsfield["status"] == "VERIFIED_COMMAND"
    assert higgsfield["location"] == "PATH:higgsfield"
    assert higgsfield["free_paid"] == "PAID_DISABLED"
    assert higgsfield["test_command"] == "SKIP_PAID_SMOKE"
    assert higgsfield["highest_readiness"] == "PAID_SMOKE_REQUIRED"
    assert higgsfield["evidence"]["audit_action"] == "SKIPPED"
    assert higgsfield["evidence"]["generation_calls"] == 0
    suno = records["suno"]
    assert suno["status"] == "LOCKED_DISABLED"
    assert suno["free_paid"] == "PAID_DISABLED"
    assert suno["test_command"] == "SKIP_PAID_SMOKE"
    assert suno["highest_readiness"] == "NOT_INSTALLED"
    assert suno["evidence"]["generation_allowed"] is False
    assert suno["evidence"]["asset_acquisition_allowed"] is False
    assert suno["evidence"]["paid_calls"] == 0
    for path in suno["source_files"]:
        resolved = (ROOT / path).resolve()
        assert resolved.is_relative_to(ROOT.resolve()) and resolved.is_file()
    for record in (motion, higgsfield, suno):
        assert record["requires_explicit_confirmation"] is True
        assert record["provider_executable"] is False
        assert record["production_readiness"] is False


def test_capability_ids_are_globally_unique_and_test_commands_are_safe() -> None:
    payload = _read_index()
    ids = [capability_id for record in payload["capabilities"] for capability_id in record["capability_ids"]]
    assert len(ids) == len(set(ids))
    assert len(ids) == 251
    for record in payload["capabilities"]:
        command = record["test_command"]
        assert ".pytest_cache/lastfailed" not in command.replace("\\", "/")
        assert not re.search(r"(?i)\b(?:generate|submit|poll|deploy|charge|wallet)\b", command)


def test_skill_links_every_repository_pack_and_all_relative_links_resolve() -> None:
    _require_pack()
    text = SKILL_PATH.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines[0] == "---"
    end = lines.index("---", 1)
    frontmatter = {line.split(":", 1)[0].strip(): line.split(":", 1)[1].strip() for line in lines[1:end]}
    assert set(frontmatter) == {"name", "description"}
    assert frontmatter["name"] == "local-video-codex-index"
    links = tuple(re.findall(r"\[[^\]]+\]\(([^)]+)\)", text))
    required = {
        "capability_index.json",
        "../local-video-filmmaking/SKILL.md",
        "../local-video-transition-motion/SKILL.md",
        "../local-video-sound-design/SKILL.md",
        "../local-video-viral-effects/SKILL.md",
        "../local-video-local-capabilities/SKILL.md",
        "../local-video-video-qa/SKILL.md",
        "../../../docs/superpowers/specs/2026-07-29-localvideostudio26i-codex-index-design.md",
    }
    assert required <= set(links)
    for target in links:
        relative = target.split("#", 1)[0]
        assert relative and "\\" not in relative
        assert not relative.startswith(("/", "\\"))
        assert not re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", relative)
        resolved = (SKILL_ROOT / relative).resolve()
        assert resolved.is_relative_to(ROOT.resolve()) and resolved.is_file()


def test_json_is_utf8_deterministic_and_contains_only_the_official_url() -> None:
    _require_pack()
    raw = INDEX_PATH.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = INDEX_PATH.read_text(encoding="utf-8")
    payload = json.loads(text)
    assert text == json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    urls = re.findall(r"https?://[^\s\"']+", text)
    assert urls == [OPENMONTAGE_REMOTE]
    combined = SKILL_PATH.read_text(encoding="utf-8") + text.replace(OPENMONTAGE_REMOTE, "")
    for pattern in (
        r"(?i)\b(?:requests|httpx|urllib|wget|curl|yt[-_]?dlp)\b",
        r"(?i)\b(?:download|downloader|urlopen)\b",
        r"(?i)\b(?:base64|os\.system|Popen)\b",
        r"(?i)\b(?:api[_-]?key|client[_-]?secret|private[_-]?key|password)\b",
        r"(?i)\b(?:register[_-]?handler|callback[_-]?data|backstack|state[_-]?machine)\b",
    ):
        assert re.search(pattern, combined) is None, pattern
