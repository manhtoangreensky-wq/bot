import ast
import json
import re
import sys
from pathlib import Path, PurePosixPath
from unittest import SkipTest


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "video" / "local-video-local-capabilities"
SKILL_PATH = SKILL_ROOT / "SKILL.md"
LOCAL_PATH = SKILL_ROOT / "local_capabilities.json"
DELIVERY_PATH = SKILL_ROOT / "platform_delivery_profiles.json"
GPU_PATH = SKILL_ROOT / "heavy_gpu_inventory.json"
RIGHTS_PATH = ROOT / "skills" / "video" / "local-video-filmmaking" / "rights_requirements.json"

G1_IDS = (
    "reference_video_analysis", "shot_list_generation", "storyboard_generation",
    "production_plan", "cost_and_resource_estimate", "delivery_promise",
    "reference_differentiation", "style_playbook_selection", "clip_ranking",
    "clip_factory", "transcript_based_editing", "silence_detection",
    "scene_detection", "frame_sampling", "documentary_montage",
    "open_archive_search", "stock_footage_corpus", "b_roll_ranking", "screen_demo",
    "synthetic_terminal_demo", "ui_demo_planning", "talking_head_cleanup",
    "subtitle_generation", "word_level_caption_planning", "reframing",
    "animated_explainer", "animated_diagram", "chart_animation",
    "logo_animation", "end_card",
)
DELIVERY_IDS = (
    "platform_delivery_profiles", "9_16_short_form", "16_9_long_form", "1_1_social",
    "4_5_feed", "thumbnail_keyframe_selection", "hook_scoring", "retention_checkpoints",
    "brand_consistency", "accessibility", "flash_flicker_safety",
)
GPU_IDS = ("WAN", "Hunyuan", "CogVideo", "LTX_local", "Stable_Diffusion", "Real_ESRGAN", "CodeFormer", "GFPGAN", "SadTalker", "Wav2Lip")
RIGHTS_IDS = (
    "source_ownership", "license", "brand_restrictions", "face_person_consent",
    "music_rights", "font_rights", "stock_attribution", "ai_generated_asset_disclosure_metadata",
)
STATUS_VALUES = {"EXISTING_AND_VALID", "EXISTING_BUT_INCOMPLETE", "MISSING", "DUPLICATE", "PAID_DISABLED", "GPU_BLOCKED", "LICENSE_BLOCKED", "NOT_APPLICABLE"}
READINESS = {"CONTRACT_ONLY", "LOCAL_PLANNING_READY", "REQUIRES_RUNTIME", "NOT_SUPPORTED"}
GPU_CLASSIFICATIONS = {"SUPPORTED", "INSUFFICIENT_HARDWARE", "DEFERRED", "LICENSE_BLOCKED"}
LOCKS = {"planning_only": True, "runtime_registered": False, "provider_executable": False, "public_ui": False}
REFERENCE_FIELDS = ("path", "symbols", "support_layer", "relationship", "notes_vi")
SUPPORT_LAYERS = {"local_edit", "validation", "planner", "knowledge", "capability_catalog", "policy"}
APPROVED = {"SKILL.md", "local_capabilities.json", "platform_delivery_profiles.json", "heavy_gpu_inventory.json"}
VIETNAMESE_MARKERS = tuple("ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ")
FORBIDDEN = (
    r"(?i)https?://", r"(?i)\b(?:requests|httpx|urllib|wget|curl|yt[-_]?dlp)\b",
    r"(?i)\b(?:download|downloader|fetch_audio|urlopen)\b",
    r"(?i)\b(?:base64|subprocess|os\.system|Popen)\b",
    r"(?i)\b(?:api[_-]?key|client[_-]?secret|private[_-]?key|password)\b",
    r"(?i)\b(?:register[_-]?handler|callback[_-]?data|backstack|state[_-]?machine)\b",
)


def _require_pack() -> None:
    if not SKILL_ROOT.is_dir() or any(not path.is_file() for path in (SKILL_PATH, LOCAL_PATH, DELIVERY_PATH, GPU_PATH)):
        raise SkipTest("26G local-capabilities pack is not installed")


def _read(path: Path) -> dict[str, object]:
    _require_pack()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _vi(value: object) -> bool:
    if isinstance(value, str):
        return any(marker in value.casefold() for marker in VIETNAMESE_MARKERS)
    if isinstance(value, dict):
        return any(_vi(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_vi(item) for item in value)
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


def _symbols(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
            for target in targets:
                if isinstance(target, ast.Name):
                    out.add(target.id)
    return out


def _reference(value: object) -> None:
    assert isinstance(value, dict)
    assert tuple(value) == REFERENCE_FIELDS
    path = value["path"]
    assert isinstance(path, str) and path and "\\" not in path
    pure = PurePosixPath(path)
    assert not pure.is_absolute() and ".." not in pure.parts
    assert isinstance(value["symbols"], list)
    assert value["support_layer"] in SUPPORT_LAYERS
    assert value["relationship"] == "metadata_only"
    assert _vi(value["notes_vi"])
    resolved = (ROOT / path).resolve()
    assert resolved.is_relative_to(ROOT.resolve()) and resolved.is_file()
    if resolved.suffix == ".py":
        assert set(value["symbols"]) <= _symbols(resolved)


def test_exact_26g_tree_exists_without_runtime_or_assets() -> None:
    assert SKILL_ROOT.is_dir(), "26G skill directory is absent"
    actual = {path.relative_to(SKILL_ROOT).as_posix() for path in SKILL_ROOT.rglob("*") if path.is_file()}
    assert actual == APPROVED
    assert not {path for path in SKILL_ROOT.rglob("*") if path.suffix.casefold() in {".mp3", ".wav", ".mp4", ".mov", ".onnx", ".safetensors"}}


def test_contract_test_uses_stdlib_only() -> None:
    roots: set[str] = set()
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    assert roots <= sys.stdlib_module_names
    assert roots.isdisjoint({"bot", "services", "providers", "workers", "billing"})


def test_local_capability_ids_count_order_rights_and_locks() -> None:
    payload = _read(LOCAL_PATH)
    assert payload["schema_version"] == "1.0.0"
    assert payload["pack_id"] == "local-video-local-capabilities"
    assert payload["group_id"] == "local_capability"
    assert payload["capability_count"] == 30
    assert tuple(item["id"] for item in payload["capabilities"]) == G1_IDS
    assert len({item["id"] for item in payload["capabilities"]}) == 30
    assert payload["rights_contract_ref"] == "../local-video-filmmaking/rights_requirements.json"
    assert (SKILL_ROOT / payload["rights_contract_ref"]).resolve() == RIGHTS_PATH.resolve()
    for record in payload["capabilities"]:
        assert record["qualified_id"] == f"local_capability.{record['id']}"
        assert tuple(record["rights_requirement_ids"]) == RIGHTS_IDS
        assert record["inventory_status"] in STATUS_VALUES
        assert record["readiness"] in READINESS
        for key, expected in LOCKS.items():
            assert record[key] is expected
        for field in ("display_name_vi", "purpose_vi", "required_inputs", "local_method", "failure_modes", "validation_checks"):
            _nonempty(record[field])
            assert _vi(record[field])
        for reference in record["existing_capability_refs"]:
            _reference(reference)
    assert payload["inventory_snapshot"]["reframing"]["status"] == "EXISTING_BUT_INCOMPLETE"
    assert payload["inventory_snapshot"]["kinetic_typography"]["duplicate_action"] == "KEEP_EXISTING"
    assert payload["local_tool_policy"]["ffmpeg"]["status"] == "AVAILABLE_LOCAL"
    assert payload["local_tool_policy"]["remotion"]["status"] != "AVAILABLE_LOCAL"


def test_delivery_profiles_and_accessibility_are_fail_closed() -> None:
    payload = _read(DELIVERY_PATH)
    assert payload["contract_id"] == "platform_delivery_profiles"
    assert payload["profile_count"] == 11
    assert tuple(item["id"] for item in payload["profiles"]) == DELIVERY_IDS
    for item in payload["profiles"]:
        assert item["inventory_status"] in STATUS_VALUES
        assert item["readiness"] in READINESS
        for field in ("display_name_vi", "purpose_vi", "delivery_rules", "accessibility", "reduced_motion", "fallback", "validation"):
            _nonempty(item[field])
            assert _vi(item[field])
        assert item["validation"]["fail_closed"] is True
        assert item["rights_requirement_ids"] == list(RIGHTS_IDS)
        for key, expected in LOCKS.items():
            assert item[key] is expected
    snapshot = payload["inventory_snapshot"]
    assert snapshot["subtitle_safe_area"]["duplicate_action"] == "KEEP_EXISTING"
    assert snapshot["mobile_legibility"]["duplicate_action"] == "KEEP_EXISTING"


def test_heavy_model_inventory_has_hardware_evidence_and_no_install() -> None:
    payload = _read(GPU_PATH)
    assert payload["contract_id"] == "heavy_local_model_inventory"
    assert payload["model_count"] == 10
    assert tuple(item["id"] for item in payload["models"]) == GPU_IDS
    assert payload["hardware_snapshot"]["gpu_model"] == "NVIDIA Quadro P1000"
    assert payload["hardware_snapshot"]["vram_mib"] == 4096
    assert payload["hardware_snapshot"]["ram_gib"] > 30
    for model in payload["models"]:
        assert model["classification"] in GPU_CLASSIFICATIONS
        assert model["install_allowed_in_26g"] is False
        _nonempty(model["license"])
        _nonempty(model["estimated_runtime_minutes"])
        _nonempty(model["limitations_vi"])
        for key, expected in LOCKS.items():
            assert model[key] is expected


def test_skill_links_contracts_rights_and_spec_with_relative_paths() -> None:
    _require_pack()
    text = SKILL_PATH.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines[0] == "---"
    end = lines.index("---", 1)
    frontmatter = {line.split(":", 1)[0].strip(): line.split(":", 1)[1].strip() for line in lines[1:end]}
    assert set(frontmatter) == {"name", "description"}
    assert frontmatter["name"] == "local-video-local-capabilities"
    links = tuple(re.findall(r"\[[^\]]+\]\(([^)]+)\)", text))
    required = {"local_capabilities.json", "platform_delivery_profiles.json", "heavy_gpu_inventory.json", "../local-video-filmmaking/rights_requirements.json", "../../../docs/superpowers/specs/2026-07-29-localvideostudio26g-local-capabilities-design.md"}
    assert required <= set(links)
    for target in links:
        relative = target.split("#", 1)[0]
        assert not relative.startswith(("/", "\\")) and "\\" not in relative
        assert not re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", relative)
        resolved = (SKILL_ROOT / relative).resolve()
        assert resolved.is_relative_to(ROOT.resolve()) and resolved.is_file()


def test_json_is_deterministic_and_pack_has_no_network_or_secret_code() -> None:
    _require_pack()
    for path in (LOCAL_PATH, DELIVERY_PATH, GPU_PATH):
        raw = path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf")
        text = path.read_text(encoding="utf-8")
        payload = json.loads(text)
        assert text == json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    combined = "\n".join(path.read_text(encoding="utf-8") for path in SKILL_ROOT.iterdir() if path.is_file())
    for pattern in FORBIDDEN:
        assert re.search(pattern, combined) is None, pattern
