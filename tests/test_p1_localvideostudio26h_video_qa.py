import ast
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath
from unittest import SkipTest


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "video" / "local-video-video-qa"
SKILL_PATH = SKILL_ROOT / "SKILL.md"
CONTRACT_PATH = SKILL_ROOT / "video_qa_contract.json"
RIGHTS_PATH = ROOT / "skills" / "video" / "local-video-filmmaking" / "rights_requirements.json"

QA_IDS = (
    "file_exists",
    "file_size_minimum",
    "container_valid",
    "video_stream_exists",
    "duration_positive",
    "dimensions_valid",
    "frame_rate_valid",
    "audio_stream_when_promised",
    "audio_loudness_valid",
    "true_peak_valid",
    "black_frame_detection",
    "frozen_frame_detection",
    "duplicated_scene_warning",
    "subtitle_safe_area",
    "subtitle_readability",
    "aspect_ratio",
    "delivery_filename",
    "output_size",
    "render_promise_verification",
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
TOP_LEVEL_FIELDS = (
    "schema_version",
    "pack_id",
    "group_id",
    "contract_id",
    "qa_count",
    "rights_contract_ref",
    "audio_contract_refs",
    "delivery_contract_refs",
    "typography_contract_ref",
    "music_suno_policy",
    "success_policy",
    "no_fake_success",
    "checks",
    "fixture_policy",
    "ffmpeg_ffprobe_mapping",
    "existing_capability_refs",
    "planning_only",
    "runtime_registered",
    "provider_executable",
    "public_ui",
)
CHECK_FIELDS = (
    "id",
    "qualified_id",
    "display_name_vi",
    "purpose_vi",
    "evidence_required",
    "pass_rule_vi",
    "failure_rule_vi",
    "fail_closed",
    "severity",
    "outcome_policy",
    "local_method",
    "failure_modes",
    "validation_checks",
    "existing_capability_refs",
    "rights_requirement_ids",
    "inventory_status",
    "readiness",
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
INVENTORY_STATUSES = {
    "EXISTING_AND_VALID",
    "EXISTING_BUT_INCOMPLETE",
    "MISSING",
    "DUPLICATE",
    "PAID_DISABLED",
    "GPU_BLOCKED",
    "LICENSE_BLOCKED",
    "NOT_APPLICABLE",
}
READINESS = {
    "CONTRACT_ONLY",
    "LOCAL_PLANNING_READY",
    "REQUIRES_RUNTIME",
    "NOT_SUPPORTED",
}
SUPPORT_LAYERS = {
    "local_edit",
    "validation",
    "planner",
    "capability_catalog",
    "knowledge",
    "policy",
}
REFERENCE_FIELDS = ("path", "symbols", "support_layer", "relationship", "notes_vi")
APPROVED_FILENAMES = {"SKILL.md", "video_qa_contract.json"}
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
    ".mkv",
    ".png",
    ".jpg",
}
FORBIDDEN_CONTENT_PATTERNS = (
    r"(?i)https?://",
    r"(?i)\b(?:requests|httpx|urllib|wget|curl|yt[-_]?dlp)\b",
    r"(?i)\b(?:download|downloader|fetch_audio|urlopen)\b",
    r"(?i)\b(?:base64|subprocess|os\.system|Popen)\b",
    r"(?i)\b(?:api[_-]?key|client[_-]?secret|private[_-]?key|password)\b",
    r"(?i)\b(?:register[_-]?handler|callback[_-]?data|backstack|state[_-]?machine)\b",
)
FIXTURE_IDS = (
    "valid_mp4_with_audio",
    "zero_byte_file",
    "broken_mp4",
    "srt_only_output",
    "audio_only_output",
    "empty_output_path",
    "task_id_only",
    "http_200_without_artifact",
)


def _require_pack() -> None:
    if not SKILL_ROOT.is_dir() or not SKILL_PATH.is_file() or not CONTRACT_PATH.is_file():
        raise SkipTest("26H local-video QA pack is not installed")


def _read_contract() -> dict[str, object]:
    _require_pack()
    payload = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
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
    assert isinstance(path, str) and path.strip() == path and path
    assert "\\" not in path
    pure = PurePosixPath(path)
    assert not pure.is_absolute() and ".." not in pure.parts
    assert isinstance(reference["symbols"], list)
    assert all(isinstance(item, str) and item.strip() for item in reference["symbols"])
    assert reference["support_layer"] in SUPPORT_LAYERS
    assert reference["relationship"] == "metadata_only"
    assert _contains_vietnamese(reference["notes_vi"])
    resolved = (ROOT / path).resolve()
    assert resolved.is_relative_to(ROOT.resolve()) and resolved.is_file()
    if reference["symbols"] and resolved.suffix == ".py":
        assert set(reference["symbols"]) <= _python_symbols(resolved)


def _validate_locks(record: dict[str, object]) -> None:
    for key, expected in LOCKS.items():
        assert record[key] is expected


def test_exact_26h_tree_exists_without_media_or_runtime_files() -> None:
    assert SKILL_ROOT.is_dir(), "26H skill directory is absent"
    actual = {path.relative_to(SKILL_ROOT).as_posix() for path in SKILL_ROOT.rglob("*") if path.is_file()}
    assert actual == APPROVED_FILENAMES
    assert not {
        path for path in SKILL_ROOT.rglob("*")
        if path.is_file() and path.suffix.casefold() in FORBIDDEN_ASSET_EXTENSIONS
    }


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


def test_exact_19_qa_ids_order_count_and_envelope() -> None:
    payload = _read_contract()
    assert tuple(payload) == TOP_LEVEL_FIELDS
    assert payload["schema_version"] == "1.0.0"
    assert payload["pack_id"] == "local-video-video-qa"
    assert payload["group_id"] == "video_qa"
    assert payload["contract_id"] == "video_qa_no_fake_success"
    assert payload["qa_count"] == 19
    assert tuple(item["id"] for item in payload["checks"]) == QA_IDS
    assert len({item["id"] for item in payload["checks"]}) == 19
    assert payload["rights_contract_ref"] == "../local-video-filmmaking/rights_requirements.json"
    assert (SKILL_ROOT / payload["rights_contract_ref"]).resolve() == RIGHTS_PATH.resolve()
    _validate_locks(payload)


def test_each_qa_check_has_fail_closed_evidence_method_rights_and_locks() -> None:
    payload = _read_contract()
    for check in payload["checks"]:
        assert tuple(check) == CHECK_FIELDS
        assert re.fullmatch(r"[a-z0-9]+(?:_[a-z0-9]+)*", check["id"])
        assert check["qualified_id"] == f"video_qa.{check['id']}"
        for field in (
            "display_name_vi",
            "purpose_vi",
            "evidence_required",
            "pass_rule_vi",
            "failure_rule_vi",
            "local_method",
            "failure_modes",
            "validation_checks",
        ):
            _assert_nonempty(check[field])
            assert _contains_vietnamese(check[field]), field
        assert check["fail_closed"] is True
        assert check["severity"] in {"BLOCKING", "WARNING"}
        assert check["outcome_policy"] in {"FAIL_CLOSED", "WARN_AND_REVIEW"}
        assert check["inventory_status"] in INVENTORY_STATUSES
        assert check["readiness"] in READINESS
        assert check["local_method"]["execution_in_26h_allowed"] is False
        assert check["local_method"]["mode"] == "SPECIFICATION_ONLY"
        assert tuple(check["rights_requirement_ids"]) == RIGHTS_IDS
        for reference in check["existing_capability_refs"]:
            _validate_reference(reference)
        _validate_locks(check)


def test_success_policy_and_no_fake_success_cases_are_exact_and_fail_closed() -> None:
    payload = _read_contract()
    expected = (
        "http_200_alone",
        "task_id_alone",
        "empty_output_path",
        "zero_byte_file",
        "srt_only_when_mp4_promised",
        "audio_only_when_mp4_promised",
        "broken_mp4",
    )
    assert tuple(payload["no_fake_success"]) == expected
    policy = payload["success_policy"]
    assert policy["missing_evidence_action"] == "FAIL_CLOSED"
    assert policy["all_blocking_checks_required"] is True
    assert policy["warning_checks_require_review"] is True
    for key in (
        "http_200_alone_success_allowed",
        "task_id_alone_success_allowed",
        "empty_output_path_success_allowed",
        "zero_byte_success_allowed",
        "srt_only_when_mp4_promised_success_allowed",
        "audio_only_when_mp4_promised_success_allowed",
        "broken_mp4_success_allowed",
    ):
        assert policy[key] is False


def test_specialized_checks_delegate_to_their_canonical_contracts() -> None:
    payload = _read_contract()
    checks = {item["id"]: item for item in payload["checks"]}
    paths = lambda item: {reference["path"] for reference in item["existing_capability_refs"]}
    audio_path = "skills/video/local-video-sound-design/audio_qa_contract.json"
    loudness_path = "skills/video/local-video-sound-design/platform_loudness_profiles.json"
    delivery_path = "skills/video/local-video-local-capabilities/platform_delivery_profiles.json"
    typography_path = "skills/video/local-video-transition-motion/kinetic_typography.json"
    for check_id in ("audio_loudness_valid", "true_peak_valid"):
        assert {audio_path, loudness_path} <= paths(checks[check_id])
    for check_id in ("subtitle_safe_area", "subtitle_readability"):
        assert delivery_path in paths(checks[check_id])
        assert typography_path in paths(checks[check_id])
    duplicate = checks["duplicated_scene_warning"]
    assert duplicate["fail_closed"] is True
    assert duplicate["outcome_policy"] == "WARN_AND_REVIEW"
    assert "services/video_real_render_connector.py" not in paths(duplicate)


def test_audio_delivery_typography_rights_and_tool_contracts_are_linked() -> None:
    payload = _read_contract()
    assert tuple(payload["audio_contract_refs"]) == (
        "../local-video-sound-design/audio_qa_contract.json",
        "../local-video-sound-design/platform_loudness_profiles.json",
    )
    assert tuple(payload["delivery_contract_refs"]) == (
        "../local-video-local-capabilities/platform_delivery_profiles.json",
    )
    assert payload["typography_contract_ref"] == "../local-video-transition-motion/kinetic_typography.json"
    for target in (
        *payload["audio_contract_refs"],
        *payload["delivery_contract_refs"],
        payload["typography_contract_ref"],
        payload["rights_contract_ref"],
    ):
        resolved = (SKILL_ROOT / target).resolve()
        assert resolved.is_relative_to(ROOT.resolve()) and resolved.is_file()
    mapping = payload["ffmpeg_ffprobe_mapping"]
    assert set(mapping["allowed_tools"]) == {"ffmpeg", "ffprobe"}
    assert mapping["relationship"] == "metadata_only"
    assert mapping["execution_in_26h_allowed"] is False
    assert "audio_loudness_valid" in mapping["operations"]
    assert "true_peak_valid" in mapping["operations"]
    rights = payload["music_suno_policy"]
    assert rights["status"] == "LOCKED_DISABLED"
    assert rights["generation_allowed"] is False
    assert rights["asset_acquisition_allowed"] is False


def test_fixture_policy_is_ephemeral_and_covers_no_fake_success_cases() -> None:
    payload = _read_contract()
    fixture = payload["fixture_policy"]
    assert fixture["asset_policy"] == "EPHEMERAL_LOCAL_ONLY"
    assert fixture["customer_media_allowed"] is False
    assert fixture["committed_binary_assets_allowed"] is False
    assert fixture["generation_tool"] == "local_ffmpeg_lavfi"
    assert fixture["probe_tool"] == "local_ffprobe"
    assert tuple(item["id"] for item in fixture["fixtures"]) == FIXTURE_IDS
    assert len({item["id"] for item in fixture["fixtures"]}) == len(FIXTURE_IDS)
    for item in fixture["fixtures"]:
        _assert_nonempty(item)
        assert item["ephemeral_only"] is True
        assert item["commit_allowed"] is False
        assert _contains_vietnamese(item["purpose_vi"])


def test_ephemeral_local_ffmpeg_fixtures_are_probeable_and_never_bundled(tmp_path: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise SkipTest("local ffmpeg/ffprobe fixture tools are unavailable")

    valid = tmp_path / "valid.mp4"
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=160x90:rate=10:duration=0.5",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=44100:duration=0.5",
            "-c:v",
            "mpeg4",
            "-q:v",
            "5",
            "-c:a",
            "aac",
            "-shortest",
            "-y",
            str(valid),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    probed = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,width,height",
            "-of",
            "json",
            str(valid),
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        timeout=15,
    )
    evidence = json.loads(probed.stdout)
    stream_types = {stream["codec_type"] for stream in evidence["streams"]}
    assert valid.stat().st_size > 1024
    assert float(evidence["format"]["duration"]) > 0
    assert {"video", "audio"} <= stream_types

    zero_byte = tmp_path / "zero.mp4"
    zero_byte.write_bytes(b"")
    broken = tmp_path / "broken.mp4"
    broken.write_bytes(b"not-a-video-container")
    srt_only = tmp_path / "subtitle.srt"
    srt_only.write_text(
        "1\n00:00:00,000 --> 00:00:00,500\nPhụ đề kiểm thử hợp pháp.\n",
        encoding="utf-8",
    )
    audio_only = tmp_path / "audio-only.m4a"
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=44100:duration=0.25",
            "-c:a",
            "aac",
            "-y",
            str(audio_only),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    audio_probe = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "stream=codec_type", "-of", "json", str(audio_only)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        timeout=15,
    )
    audio_types = {stream["codec_type"] for stream in json.loads(audio_probe.stdout)["streams"]}
    assert zero_byte.stat().st_size == 0
    assert broken.stat().st_size > 0
    assert srt_only.suffix == ".srt"
    assert audio_types == {"audio"}
    for fixture in (valid, zero_byte, broken, srt_only, audio_only):
        assert fixture.resolve().is_relative_to(tmp_path.resolve())
        assert not fixture.resolve().is_relative_to(SKILL_ROOT.resolve())


def test_top_level_references_are_relative_tracked_metadata_only() -> None:
    payload = _read_contract()
    tracked = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "--cached"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
    )
    tracked_paths = {line.strip().replace("\\", "/") for line in tracked.stdout.splitlines() if line.strip()}
    for reference in payload["existing_capability_refs"]:
        _validate_reference(reference)
        assert reference["path"] in tracked_paths


def test_skill_links_contracts_and_all_relative_links_resolve() -> None:
    _require_pack()
    text = SKILL_PATH.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines[0] == "---"
    end = lines.index("---", 1)
    frontmatter = {line.split(":", 1)[0].strip(): line.split(":", 1)[1].strip() for line in lines[1:end]}
    assert set(frontmatter) == {"name", "description"}
    assert frontmatter["name"] == "local-video-video-qa"
    links = tuple(re.findall(r"\[[^\]]+\]\(([^)]+)\)", text))
    required = {
        "video_qa_contract.json",
        "../local-video-filmmaking/rights_requirements.json",
        "../local-video-sound-design/audio_qa_contract.json",
        "../local-video-sound-design/platform_loudness_profiles.json",
        "../local-video-local-capabilities/platform_delivery_profiles.json",
        "../local-video-transition-motion/kinetic_typography.json",
        "../../../docs/superpowers/specs/2026-07-29-localvideostudio26h-video-qa-design.md",
    }
    assert required <= set(links)
    for target in links:
        relative = target.split("#", 1)[0]
        assert relative and "\\" not in relative
        assert not relative.startswith(("/", "\\"))
        assert not re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", relative)
        resolved = (SKILL_ROOT / relative).resolve()
        assert resolved.is_relative_to(ROOT.resolve()) and resolved.is_file()


def test_json_is_utf8_deterministic_and_pack_has_no_network_asset_or_runtime_code() -> None:
    _require_pack()
    raw = CONTRACT_PATH.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = CONTRACT_PATH.read_text(encoding="utf-8")
    payload = json.loads(text)
    assert text == json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    combined = SKILL_PATH.read_text(encoding="utf-8") + text
    for pattern in FORBIDDEN_CONTENT_PATTERNS:
        assert re.search(pattern, combined) is None, pattern


def test_no_fake_success_and_execution_locks_cannot_be_relaxed() -> None:
    payload = _read_contract()
    for key, expected in LOCKS.items():
        mutated = dict(payload)
        mutated[key] = not expected
        try:
            _validate_locks(mutated)
        except AssertionError:
            continue
        raise AssertionError(f"changed lock passed: {key}")
    for check in payload["checks"]:
        assert check["local_method"]["execution_in_26h_allowed"] is False
