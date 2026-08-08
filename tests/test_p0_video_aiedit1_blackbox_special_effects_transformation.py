import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

import local_worker

from aiedit1_scope_guard import aiedit1_scope_files

from services import (
    video_ai_edit_prompt as prompt,
    video_ai_edit_provider as provider,
    video_ai_edit_router as router,
    video_ai_edit_status as status,
    video_ai_edit_validation as validation,
)


ROOT = Path(__file__).resolve().parents[1]


def _is_local_test_scratch(path: str) -> bool:
    """Ignore root-level basetemp/fixture directories created by local gates."""

    normalized = path.replace("\\", "/")
    first = normalized.split("/", 1)[0]
    return (
        normalized.startswith(("data/tmp/", "video_editor_sessions/"))
        or first.startswith(
            (
                ".cleanup_",
                ".postmatrix_",
                ".postrebase_",
                ".recovery_",
                ".task",
                ".videoedit_",
                ".videoedit-",
            )
        )
    )


BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")
WORKER_SOURCE = (ROOT / "local_worker.py").read_text(encoding="utf-8")
SERVICE_SOURCES = "\n".join(
    (ROOT / "services" / name).read_text(encoding="utf-8")
    for name in (
        "video_ai_edit_router.py",
        "video_ai_edit_prompt.py",
        "video_ai_edit_provider.py",
        "video_ai_edit_validation.py",
        "video_ai_edit_status.py",
    )
)


def source_between(text, start, end):
    return text[text.index(start):text.index(end, text.index(start))]


def test_aiedit1_changed_files_stay_in_exact_scope():
    changed = set()
    for command in (
        ["git", "diff", "--name-only", "origin/main"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ):
        result = subprocess.run(command, check=False, capture_output=True, text=True, cwd=ROOT)
        changed.update(
            line.strip().replace("\\", "/")
            for line in result.stdout.splitlines()
            if line.strip()
            and not _is_local_test_scratch(line.strip())
            and not line.strip().replace("\\", "/").startswith((".pytest_tmp/", "pytest-baseline-r1/"))
        )
    assert changed <= aiedit1_scope_files(changed)
    runtime_paths = {path for path in changed if not path.startswith("tests/")}
    forbidden = ("music", "suno", "subdub", "product_video", "voice", "payos", "wallet", "payment")
    assert not any(term in path.lower() for path in runtime_paths for term in forbidden)


def metadata(**overrides):
    base = {
        "ok": True,
        "has_video": True,
        "has_audio": True,
        "duration": 8.0,
        "duration_ms": 8000,
        "width": 1080,
        "height": 1920,
        "fps": 30.0,
        "bytes": 1024,
        "orientation": "portrait",
    }
    base.update(overrides)
    return base


def route(text="cinematic video", profile_id="", **kwargs):
    return router.route_ai_edit_intent(
        text,
        selected_profile=profile_id,
        source_metadata=kwargs.pop("source_metadata", metadata()),
        **kwargs,
    )


def prompt_payload(selected_route=None, **settings):
    selected = selected_route or route("product commercial, preserve logo", "product_commercial")
    return prompt.build_professional_prompt(
        selected,
        user_request="Create a premium commercial while preserving the product and logo",
        source_metadata=metadata(),
        settings={"target_aspect_ratio": "9:16", "target_duration_seconds": 8, **settings},
    )


def valid_env(**overrides):
    env = {
        "VIDEO_AI_EDIT_PUBLIC_ENABLED": "true",
        "VIDEO_AI_EDIT_LOCAL_ENABLED": "true",
        "VIDEO_AI_EDIT_GENERATIVE_ENABLED": "true",
        "VIDEO_AI_EDIT_PUBLIC_FREEZE": "false",
        "VIDEO_AI_EDIT_HIDDEN_SUBMIT_FREEZE": "true",
        "VIDEO_AI_EDIT_PRICE_XU": "300",
        "VIDEO_AI_EDIT_PROVIDER_CHAIN": "key4u_video",
        "KEY4U_VIDEO_TO_VIDEO_ENABLED": "true",
        "KEY4U_VIDEO_TO_VIDEO_SUBMIT_URL": "https://video.vendor.com/v1/edit",
        "KEY4U_VIDEO_TO_VIDEO_POLL_URL": "https://video.vendor.com/v1/edit/{task_id}",
        "KEY4U_VIDEO_TO_VIDEO_AUTH_HEADER_VALUE": "Bearer masked-credential",
        "KEY4U_VIDEO_TO_VIDEO_MODEL": "kling-3.0-turbo",
        "KEY4U_VIDEO_TO_VIDEO_INTERFACE": "video_to_video_multipart",
        "KEY4U_VIDEO_TO_VIDEO_CAPABILITIES": "video_to_video",
        "VIDEO_AI_EDIT_POLL_INTERVAL_SECONDS": "5",
        "VIDEO_AI_EDIT_MAX_WAIT_SECONDS": "60",
    }
    env.update(overrides)
    return env


def valid_config():
    return provider.provider_config_from_env("key4u_video", valid_env())


class JsonResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status = status_code

    def read(self, *_args):
        return json.dumps(self.payload).encode("utf-8")


def test_aiedit1_menu_entry_present():
    assert '"videoedit|ai"' in BOT_SOURCE
    assert "Chỉnh sửa theo mục tiêu" in BOT_SOURCE


def test_aiedit1_upload_flow():
    callback = source_between(BOT_SOURCE, "async def handle_video_editor_callback", "async def handle_video_upload_callback")
    assert '"await_ai_video"' in callback
    assert "set_video_editor_pending(" in callback
    assert 'if step == "await_ai_video"' in BOT_SOURCE
    assert "inspect_video_editor_source" in BOT_SOURCE


def test_aiedit1_exact_back_routes():
    required = {
        '"videoedit|ai"',
        '"videoedit|ai_source"',
        '"videoedit|ai_suggestions"',
        '"videoedit|ai_settings"',
        '"videoedit|ai_prompt"',
    }
    for value in required:
        assert value in BOT_SOURCE


def test_aiedit1_no_job_before_final_confirm():
    callback = source_between(BOT_SOURCE, "async def handle_video_editor_callback", "async def handle_video_upload_callback")
    assert callback.count("submit_video_edit_local_free_job(update, context, state)") == 1
    assert callback.index('action == "ai_confirm"') < callback.index('action == "confirm_local"')
    assert callback.index('action == "confirm_local"') < callback.index(
        "submit_video_edit_local_free_job(update, context, state)"
    )


def test_aiedit1_no_outbox_before_final_confirm():
    assert route()["outbox_created"] is False
    callback = source_between(BOT_SOURCE, "async def handle_video_editor_callback", "async def handle_video_upload_callback")
    assert "create_outbox" not in callback


def test_aiedit1_no_provider_before_final_confirm():
    upload = source_between(BOT_SOURCE, "async def handle_video_editor_pending_upload", "async def handle_video_editor_pending_text")
    assert "submit_video_edit(" not in upload
    assert "configured_provider_chain(" not in upload


def test_aiedit1_no_charge_before_final_confirm():
    submit = source_between(BOT_SOURCE, "async def submit_video_edit_local_free_job", "async def submit_local_video_editor_job")
    assert "spend_fixed_credit_info(" not in submit
    assert '"charge_policy": "free_local_tool"' in submit
    assert '"price_xu": 0' in submit


def test_aiedit1_router_talking_head():
    assert route("nguoi noi truoc camera chuyen nghiep")['profile_id'] == "talking_head_pro"


def test_aiedit1_router_product_video():
    assert route("quang cao san pham, giu logo")['profile_id'] == "product_commercial"


def test_aiedit1_router_fashion():
    assert route("fashion lookbook, giu outfit")['profile_id'] == "fashion_lookbook"


def test_aiedit1_router_architecture():
    assert route("kien truc noi that, giu cua va tuong")['profile_id'] == "architecture_interior"


def test_aiedit1_router_animation():
    assert route("anime cartoon animation")['profile_id'] == "animation_cartoon"


def test_aiedit1_router_cinematic_vfx():
    assert route("cinematic dien anh professional")['profile_id'] == "cinematic_professional"


def test_aiedit1_explicit_profile_wins():
    assert route("fashion", "architecture_interior")['profile_id'] == "architecture_interior"
    assert route("fashion", "architecture_interior")['confidence'] == 1.0


def test_aiedit1_low_confidence_asks_clarification():
    result = route("lam dep", source_metadata=metadata(width=1280, height=720, orientation="landscape"))
    assert result["profile_id"] == "auto_recommend"
    assert result["clarification_question"]


def test_aiedit1_preserve_constraints_retained():
    result = route("product", preserve_controls={"preserve_product_logo": True, "replace_background": True})
    assert "preserve_product_logo" in result["preserve_constraints"]
    assert "replace_background_explicit" in result["preserve_constraints"]


def test_aiedit1_all_eighteen_profiles_complete():
    assert len(router.AI_EDIT_PROFILES) == 18
    required = {"suitable_footage", "visual_objective", "effect_stack", "lighting_treatment", "color_treatment", "camera_motion_treatment", "transition_behavior", "preserve_rules", "negative_prompt", "provider_capability_required", "local_fallback_options", "clarification_questions"}
    assert all(required.issubset(item) for item in router.AI_EDIT_PROFILES)


def test_aiedit1_returns_three_to_five_suggestions():
    suggestions = router.suggestions_for_footage("talking_head", "professional")
    assert 3 <= len(suggestions) <= 5


def test_aiedit1_suggestions_match_footage_type():
    ids = [item["profile_id"] for item in router.suggestions_for_footage("room", "modern interior")]
    assert ids[0] == "architecture_interior"
    assert "fashion_lookbook" not in ids[:3]


def test_aiedit1_suggestions_show_preserve_summary():
    assert all(item.get("preserve_summary") for item in router.suggestions_for_footage("product"))


def test_aiedit1_no_provider_debug_in_public_copy():
    public = status.public_status_text({"id": 1, "status": "running", "xu_cost": 300}, {"aiedit1": 1, "stage": "ai_processing"}).lower()
    assert not any(word in public for word in status.INTERNAL_PUBLIC_TERMS)


def test_aiedit1_default_preserve_identity():
    assert route()["preserve_controls"]["preserve_identity"] is True


def test_aiedit1_preserve_product_logo():
    built = prompt_payload()
    assert "product" in built["sections"]["subject_preservation"].lower()
    assert "logo" in built["sections"]["subject_preservation"].lower()


def test_aiedit1_preserve_architecture_geometry():
    selected = route("architecture", "architecture_interior")
    built = prompt_payload(selected)
    assert "architectural geometry" in built["negative_prompt"]
    assert "architectural geometry" in built["sections"]["subject_preservation"].lower()


def test_aiedit1_intensity_changes_prompt():
    selected = route("cinematic", "cinematic_professional")
    light = prompt_payload(selected, intensity="light")["prompt"]
    creative = prompt_payload(selected, intensity="creative")["prompt"]
    assert light != creative


def test_aiedit1_replace_background_explicit_only():
    assert route()["preserve_controls"]["replace_background"] is False
    changed = route("replace background", preserve_controls={"replace_background": True})
    assert "replace_background_explicit" in changed["preserve_constraints"]


def test_aiedit1_prompt_contains_source_and_goal():
    built = prompt_payload()
    assert "Source:" in built["prompt"] and "Objective:" in built["prompt"]


def test_aiedit1_prompt_contains_preserve_rules():
    assert "Preservation:" in prompt_payload()["prompt"]


def test_aiedit1_prompt_contains_camera_and_lighting():
    text = prompt_payload()["prompt"]
    assert "Lighting:" in text and "Camera and motion:" in text


def test_aiedit1_negative_prompt_complete():
    negative = prompt_payload()["negative_prompt"]
    for item in prompt.NEGATIVE_PROMPT_ITEMS:
        assert item in negative


def test_aiedit1_architecture_prompt_preserves_geometry():
    built = prompt_payload(route("interior", "architecture_interior"))
    assert "geometry" in (built["prompt"] + built["negative_prompt"]).lower()


def test_aiedit1_product_prompt_preserves_logo():
    assert "logo" in (prompt_payload()["prompt"] + prompt_payload()["negative_prompt"]).lower()


def test_aiedit1_local_lane_no_provider():
    decision = provider.submit_source_policy(provider.PUBLIC_FINAL_CONFIRM_SOURCE, public_user_confirmed=True, lane="local", env={"VIDEO_AI_EDIT_LOCAL_ENABLED": "true"})
    assert decision == {"allowed": True, "reason": "", "provider_submit": False}


def test_aiedit1_generativelane_requires_video_to_video_capability():
    broken = valid_env(KEY4U_VIDEO_TO_VIDEO_CAPABILITIES="text_to_video")
    decision = provider.submit_source_policy(provider.PUBLIC_FINAL_CONFIRM_SOURCE, public_user_confirmed=True, lane="generative", env=broken)
    assert decision["allowed"] is False
    assert decision["reason"] == "ai_edit_video_to_video_provider_unavailable"


def test_aiedit1_public_confirm_calls_mock_provider_once(tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture-video")
    calls = []
    result = provider.submit_video_edit(valid_config(), source_video_path=str(source), prompt="edit", negative_prompt="bad", aspect_ratio="9:16", duration_seconds=8, job_id="1", submit_source=provider.PUBLIC_FINAL_CONFIRM_SOURCE, public_user_confirmed=True, opener=lambda req, timeout=0: calls.append(req) or JsonResponse({"data": {"task_id": "task-1", "status": "IN_PROGRESS"}}))
    assert len(calls) == 1 and result["accepted"] is True


@pytest.mark.parametrize("source_name", ["debug", "recover", "status", "codex_test"])
def test_aiedit1_hidden_submit_blocked(source_name):
    assert provider.submit_source_policy(source_name, public_user_confirmed=True, lane="generative", env=valid_env())["allowed"] is False


def test_aiedit1_background_submit_blocked():
    assert provider.submit_source_policy("background_retry", public_user_confirmed=True, lane="generative", env=valid_env())["allowed"] is False


def test_aiedit1_smoke_submit_blocked():
    assert provider.submit_source_policy("smoke", public_user_confirmed=True, lane="generative", env=valid_env())["allowed"] is False


def test_aiedit1_no_provider_capability_offers_local_fallback():
    selected = route("clean video", "clean_enhance")
    assert selected["safe_fallback"] == "local_enhancement"
    assert selected["local_preprocess_plan"]


def test_aiedit1_submit_source_persisted_end_to_end():
    submit = source_between(BOT_SOURCE, "async def submit_video_ai_edit_job", "async def submit_local_video_editor_job")
    assert '"submit_source": video_ai_edit_provider.PUBLIC_FINAL_CONFIRM_SOURCE' in submit
    assert 'PUBLIC_FINAL_CONFIRM_SOURCE = "public_ai_video_edit_final_confirm"' in SERVICE_SOURCES


def test_aiedit1_provider_submit_once(tmp_path):
    source = tmp_path / "input.mp4"
    source.write_bytes(b"video")
    calls = 0
    def opener(_req, timeout=0):
        nonlocal calls
        calls += 1
        return JsonResponse({"data": {"task_id": "only-once", "status": "PENDING"}})
    provider.submit_video_edit(valid_config(), source_video_path=str(source), prompt="x", negative_prompt="y", aspect_ratio="16:9", duration_seconds=8, job_id="2", submit_source=provider.PUBLIC_FINAL_CONFIRM_SOURCE, public_user_confirmed=True, opener=opener)
    assert calls == 1


def test_aiedit1_task_id_persisted():
    parsed = provider.parse_provider_payload({"data": {"task_id": "persisted-task", "status": "IN_PROGRESS"}})
    assert parsed["provider_task_id"] == "persisted-task"
    assert "provider_task_id=task_id" in WORKER_SOURCE


def test_aiedit1_poll_interval_respected():
    clock = [0.0]
    sleeps = []
    polls = iter([{"status": "running"}, {"status": "completed", "result_url_present": True, "result_url": "https://result.test/a.mp4"}])
    def sleeper(seconds):
        sleeps.append(seconds)
        clock[0] += seconds
    result = provider.wait_for_result(valid_config(), "task", poller=lambda *_: next(polls), sleeper=sleeper, now=lambda: clock[0])
    assert result["status"] == "completed"
    assert sleeps == [5, 5]


def test_aiedit1_provider_network_calls_use_the_shared_remaining_deadline(
    tmp_path,
):
    source = tmp_path / "source.mp4"
    output = tmp_path / "output.mp4"
    source.write_bytes(b"video")
    observed_timeouts = []

    provider.submit_video_edit(
        valid_config(),
        source_video_path=str(source),
        prompt="edit",
        negative_prompt="",
        aspect_ratio="9:16",
        duration_seconds=8,
        job_id="deadline-job",
        submit_source=provider.PUBLIC_FINAL_CONFIRM_SOURCE,
        public_user_confirmed=True,
        deadline_monotonic=105.0,
        monotonic=lambda: 100.0,
        opener=lambda _request, timeout=0: (
            observed_timeouts.append(float(timeout))
            or JsonResponse({"data": {"task_id": "task-1", "status": "PENDING"}})
        ),
    )
    provider.poll_video_edit(
        valid_config(),
        "task-1",
        deadline_monotonic=104.0,
        monotonic=lambda: 100.0,
        opener=lambda _request, timeout=0: (
            observed_timeouts.append(float(timeout))
            or JsonResponse({"data": {"task_id": "task-1", "status": "RUNNING"}})
        ),
    )

    class BinaryResponse:
        status = 200

        def __init__(self):
            self._chunks = iter((b"edited-video", b""))

        def read(self, _size):
            return next(self._chunks)

    provider.download_result(
        "https://result.test/output.mp4",
        str(output),
        deadline_monotonic=103.0,
        monotonic=lambda: 100.0,
        opener=lambda _request, timeout=0: (
            observed_timeouts.append(float(timeout)) or BinaryResponse()
        ),
    )

    assert observed_timeouts == [5.0, 4.0, 3.0]
    assert output.read_bytes() == b"edited-video"


def test_aiedit1_provider_wait_never_outlives_the_shared_deadline():
    clock = [100.0]
    sleeps = []
    polls = []

    def sleeper(seconds):
        sleeps.append(float(seconds))
        clock[0] += float(seconds)

    with pytest.raises(provider.AiEditProviderError, match="provider_deadline_exceeded"):
        provider.wait_for_result(
            valid_config(),
            "task-1",
            deadline_monotonic=104.0,
            poller=lambda *_args, **_kwargs: polls.append(True) or {"status": "running"},
            sleeper=sleeper,
            now=lambda: clock[0],
        )

    assert sleeps == [4.0]
    assert polls == []


def test_aiedit1_no_fallback_while_primary_alive():
    decision = provider.controlled_fallback_decision(public_confirm_provenance=True, primary_status="running", primary_task_alive=True, fallback_count=0, candidate=valid_config())
    assert decision["allowed"] is False


def test_aiedit1_controlled_fallback_max_once():
    allowed = provider.controlled_fallback_decision(public_confirm_provenance=True, primary_status="failed", primary_task_alive=False, fallback_count=0, candidate=valid_config())
    blocked = provider.controlled_fallback_decision(public_confirm_provenance=True, primary_status="failed", primary_task_alive=False, fallback_count=1, candidate=valid_config())
    assert allowed["allowed"] is True and blocked["allowed"] is False


def test_aiedit1_no_hidden_fallback_submit():
    decision = provider.controlled_fallback_decision(public_confirm_provenance=False, primary_status="failed", primary_task_alive=False, fallback_count=0, candidate=valid_config())
    assert decision["allowed"] is False


def test_aiedit1_normalizes_container():
    command = validation.build_preprocess_command("a.mov", "b.mp4", ffmpeg_path="ffmpeg", target_duration_seconds=8, preserve_audio=True, max_width=1920, max_height=1920, target_fps=30)
    assert command[-1] == "b.mp4" and "libx264" in command and "aac" in command


def test_aiedit1_caps_resolution():
    command = validation.build_preprocess_command("a.mov", "b.mp4", ffmpeg_path="ffmpeg", target_duration_seconds=8, preserve_audio=True, max_width=1280, max_height=720, target_fps=30)
    assert "min(iw,1280)" in command[command.index("-vf") + 1]
    assert "min(ih,720)" in command[command.index("-vf") + 1]


def test_aiedit1_preserves_audio_when_requested():
    command = validation.build_preprocess_command("a.mov", "b.mp4", ffmpeg_path="ffmpeg", target_duration_seconds=8, preserve_audio=True, max_width=1920, max_height=1920, target_fps=30)
    assert "-c:a" in command and "-an" not in command


def test_aiedit1_duration_limit_actionable():
    result = validation.validate_input_metadata(metadata(duration=20), file_size=1024, lane="generative", target_duration_seconds=20, env={})
    assert result["reason"] == "duration_limit_action_required"
    assert result["action"].startswith("shorten_to_")


def test_aiedit1_preprocessed_input_validated(monkeypatch, tmp_path):
    source, output = tmp_path / "source.mov", tmp_path / "output.mp4"
    source.write_bytes(b"source")
    monkeypatch.setattr(validation.video_local_validation, "probe_video_file", lambda *_a, **_k: metadata())
    monkeypatch.setattr(validation.video_local_validation, "validate_mp4_output", lambda *_a, **_k: {"ok": True, "duration_ms": 8000})
    monkeypatch.setattr(validation.video_local_validation, "enforce_workspace_limit", lambda *_a, **_k: None)
    def runner(command, **_kwargs):
        Path(command[-1]).write_bytes(b"normalized")
        return SimpleNamespace(returncode=0)
    result = validation.preprocess_source_video(str(source), str(output), workspace=tmp_path, ffmpeg_path="ffmpeg", ffprobe_path="ffprobe", target_duration_seconds=8, preserve_audio=True, runner=runner)
    assert result["ok"] is True and output.exists()


def test_aiedit1_preprocess_and_full_decode_share_one_remaining_deadline(
    monkeypatch,
    tmp_path,
):
    source, output = tmp_path / "source.mov", tmp_path / "output.mp4"
    source.write_bytes(b"source")
    observed = {"runner_timeouts": [], "validation": []}
    monkeypatch.setattr(
        validation.video_local_validation,
        "probe_video_file",
        lambda *_a, **_k: metadata(),
    )

    def validate_output(*_args, **kwargs):
        observed["validation"].append(dict(kwargs))
        return {"ok": True, "duration_ms": 8_000, "full_decode": True}

    monkeypatch.setattr(
        validation.video_local_validation,
        "validate_mp4_output",
        validate_output,
    )
    monkeypatch.setattr(
        validation.video_local_validation,
        "enforce_workspace_limit",
        lambda *_a, **_k: None,
    )

    def runner(command, **kwargs):
        observed["runner_timeouts"].append(float(kwargs["timeout"]))
        Path(command[-1]).write_bytes(b"normalized")
        return SimpleNamespace(returncode=0)

    result = validation.preprocess_source_video(
        str(source),
        str(output),
        workspace=tmp_path,
        ffmpeg_path="ffmpeg",
        ffprobe_path="ffprobe",
        target_duration_seconds=8,
        preserve_audio=True,
        timeout=600,
        deadline_monotonic=105.0,
        monotonic=lambda: 100.0,
        runner=runner,
    )

    assert result["ok"] is True
    assert observed["runner_timeouts"] == [5.0]
    assert observed["validation"][0]["deadline_monotonic"] == 105.0


def test_aiedit1_final_validation_forwards_the_shared_deadline(
    monkeypatch,
    tmp_path,
):
    source, output = tmp_path / "source.mp4", tmp_path / "output.mp4"
    source.write_bytes(b"source")
    output.write_bytes(b"different")
    observed = {}

    def validate_output(*_args, **kwargs):
        observed.update(kwargs)
        return {"ok": True, "full_decode": True}

    monkeypatch.setattr(
        validation.video_local_validation,
        "validate_mp4_output",
        validate_output,
    )

    result = validation.validate_final_edited_mp4(
        output,
        source_path=source,
        workspace=tmp_path,
        ffmpeg_path="ffmpeg",
        ffprobe_path="ffprobe",
        deadline_monotonic=205.0,
    )

    assert result["ok"] is True
    assert observed["deadline_monotonic"] == 205.0


def test_aiedit1_final_validation_uses_the_worker_resolved_ffmpeg_path(
    monkeypatch,
    tmp_path,
):
    source, output = tmp_path / "source.mp4", tmp_path / "output.mp4"
    source.write_bytes(b"source")
    output.write_bytes(b"different")
    observed = {}

    def validate_output(*_args, **kwargs):
        observed.update(kwargs)
        return {"ok": True, "full_decode": True}

    monkeypatch.setattr(
        validation.video_local_validation,
        "validate_mp4_output",
        validate_output,
    )
    monkeypatch.setattr(
        validation.video_local_validation,
        "find_ffmpeg",
        lambda *_args, **_kwargs: pytest.fail(
            "final validation must not rediscover a different FFmpeg binary"
        ),
    )

    result = validation.validate_final_edited_mp4(
        output,
        source_path=source,
        workspace=tmp_path,
        ffprobe_path="worker-resolved-ffprobe",
        ffmpeg_path="worker-resolved-ffmpeg",
    )

    assert result["ok"] is True
    assert observed["ffprobe_path"] == "worker-resolved-ffprobe"
    assert observed["ffmpeg_path"] == "worker-resolved-ffmpeg"


def test_aiedit1_workspace_cleanup():
    run = source_between(WORKER_SOURCE, "def run_video_ai_edit", "def run_social_link_import")
    assert "cleanup_job_workspace(workspace)" in run
    assert "finally:" in run


def test_aiedit1_worker_shares_one_deadline_with_render_and_full_decode():
    run = source_between(WORKER_SOURCE, "def run_video_ai_edit", "def run_social_link_import")
    deadline = run.index("deadline_monotonic =")
    local_render = run.index("execute_manual_edit(")
    preprocess = run.index("preprocess_source_video(")
    final_validation = run.index("validate_final_edited_mp4(")

    assert deadline < local_render < preprocess < final_validation
    assert "time.monotonic() + render_timeout" in run
    assert run.count("deadline_monotonic=deadline_monotonic") >= 3


def test_aiedit1_worker_forwards_the_resolved_ffmpeg_to_final_validation():
    run = source_between(WORKER_SOURCE, "def run_video_ai_edit", "def run_social_link_import")
    validation_call = run[
        run.index("validation = video_ai_edit_validation.validate_final_edited_mp4(") :
    ]
    validation_call = validation_call[: validation_call.index("\n        )")]

    assert "ffmpeg_path=ffmpeg" in validation_call


def test_aiedit1_worker_forwards_one_deadline_to_provider_download_and_delivery():
    submit_wait = source_between(
        WORKER_SOURCE,
        "def _aiedit_submit_and_wait",
        "def run_video_ai_edit",
    )
    run = source_between(WORKER_SOURCE, "def run_video_ai_edit", "def run_social_link_import")

    assert "deadline_monotonic" in submit_wait.split(") -> dict:", 1)[0]
    assert "deadline_monotonic=deadline_monotonic" in submit_wait
    assert run.count("deadline_monotonic=deadline_monotonic") >= 7
    assert "download_result(\n                result_url,\n                str(output_path),\n                deadline_monotonic=deadline_monotonic," in run
    delivery = run[run.index("receipt = telegram_send_video_receipt(") :]
    delivery_call = delivery[: delivery.index("\n        )")]
    assert "deadline_monotonic=deadline_monotonic" in delivery_call


def _ai_worker_job(**payload_overrides):
    payload = {
        "aiedit1_contract": 1,
        "execution_lane": "local",
        "public_user_confirmed": True,
        "source_file_id": "telegram-ai-source",
        "source_file_name": "source.mp4",
        "chat_id": "702",
        "max_render_seconds": 5,
        "target_duration_seconds": 4,
        "preserve_source_audio": True,
        "price_xu": 0,
    }
    payload.update(payload_overrides)
    return {
        "id": 703,
        "input_file_id": json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    }


def _patch_ai_worker_foundation(monkeypatch, tmp_path, updates):
    ffmpeg = tmp_path / "ffmpeg.exe"
    ffprobe = tmp_path / "ffprobe.exe"
    ffmpeg.write_bytes(b"ffmpeg")
    ffprobe.write_bytes(b"ffprobe")
    monkeypatch.setattr(local_worker.time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(
        local_worker.video_ai_edit_provider,
        "submit_source_policy",
        lambda *_args, **_kwargs: {"allowed": True},
    )
    monkeypatch.setattr(local_worker, "local_ffmpeg_path", lambda: str(ffmpeg))
    monkeypatch.setattr(
        local_worker,
        "find_ffprobe",
        lambda *_args, **_kwargs: str(ffprobe),
    )
    monkeypatch.setattr(local_worker, "create_job_workspace", lambda *_args: tmp_path)
    monkeypatch.setattr(local_worker, "cleanup_job_workspace", lambda *_args: {"ok": True})
    monkeypatch.setattr(local_worker, "_aiedit_progress", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        local_worker,
        "_video_edit_telegram_media_config",
        lambda: SimpleNamespace(is_local=True),
    )

    def capture_update(job_id, status_value, detail, **kwargs):
        updates.append(
            {
                "job_id": job_id,
                "status": status_value,
                "detail": json.loads(detail),
                "kwargs": kwargs,
            }
        )
        return {"ok": True}

    monkeypatch.setattr(local_worker, "update_job", capture_update)


def test_aiedit1_absolute_deadline_covers_source_download_and_probe(
    monkeypatch,
    tmp_path,
):
    updates = []
    observed = {"legacy_download": False}
    _patch_ai_worker_foundation(monkeypatch, tmp_path, updates)
    source = tmp_path / "source.mp4"

    def legacy_download(*_args, **_kwargs):
        observed["legacy_download"] = True
        source.write_bytes(b"source")
        return str(source)

    def deadline_download(*_args, **kwargs):
        observed["download_deadline"] = kwargs.get("deadline_monotonic")
        source.write_bytes(b"source")
        return SimpleNamespace(path=str(source))

    def stop_after_probe(*_args, **kwargs):
        observed["probe_deadline"] = kwargs.get("deadline_monotonic")
        raise validation.AiEditValidationError("stop_after_probe")

    monkeypatch.setattr(local_worker, "_local1_download_asset", legacy_download)
    monkeypatch.setattr(local_worker, "_video_edit_download_asset", deadline_download)
    monkeypatch.setattr(
        local_worker.video_local_validation,
        "probe_video_file",
        stop_after_probe,
    )

    local_worker.run_video_ai_edit(_ai_worker_job())

    assert observed["legacy_download"] is False
    assert observed["download_deadline"] == 105.0
    assert observed["probe_deadline"] == 105.0
    assert updates[-1]["detail"]["reason"] == "stop_after_probe"


def test_aiedit1_ambiguous_delivery_is_persisted_as_delivery_unknown(
    monkeypatch,
    tmp_path,
):
    updates = []
    _patch_ai_worker_foundation(monkeypatch, tmp_path, updates)
    source = tmp_path / "source.mp4"

    def materialize_source(*_args, **_kwargs):
        source.write_bytes(b"source")
        return SimpleNamespace(path=str(source))

    def materialize_legacy_source(*_args, **_kwargs):
        source.write_bytes(b"source")
        return str(source)

    def render_local(_plan, *, output_path, **_kwargs):
        Path(output_path).write_bytes(b"edited-video")
        return {"ok": True}

    monkeypatch.setattr(
        local_worker,
        "_video_edit_download_asset",
        materialize_source,
    )
    monkeypatch.setattr(
        local_worker,
        "_local1_download_asset",
        materialize_legacy_source,
    )
    monkeypatch.setattr(
        local_worker.video_local_validation,
        "probe_video_file",
        lambda *_args, **_kwargs: metadata(),
    )
    monkeypatch.setattr(
        local_worker.video_ai_edit_validation,
        "validate_input_metadata",
        lambda *_args, **_kwargs: {"ok": True},
    )
    monkeypatch.setattr(local_worker, "_aiedit_local_plan", lambda *_args: {})
    monkeypatch.setattr(local_worker, "execute_manual_edit", render_local)
    monkeypatch.setattr(
        local_worker.video_ai_edit_validation,
        "validate_final_edited_mp4",
        lambda *_args, **_kwargs: {"ok": True, "artifact_size": 12},
    )
    monkeypatch.setattr(
        local_worker,
        "telegram_send_video_receipt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("telegram_delivery_outcome_uncertain")
        ),
    )

    local_worker.run_video_ai_edit(_ai_worker_job())

    assert updates[-1]["status"] == "failed"
    assert updates[-1]["detail"]["stage"] == "delivery_unknown"
    assert updates[-1]["detail"]["reason"] == "telegram_delivery_outcome_uncertain"
    assert updates[-1]["detail"]["charge"] == 0


def test_aiedit1_http_200_without_result_not_success():
    parsed = provider.parse_provider_payload({"data": {"task_id": "task", "status": "IN_PROGRESS"}})
    assert parsed["status"] == "running" and parsed["result_url_present"] is False


def test_aiedit1_empty_result_url_not_success():
    parsed = provider.parse_provider_payload({"data": {"status": "SUCCESS", "result_url": ""}})
    assert parsed["result_url_present"] is False


def test_aiedit1_zero_byte_mp4_not_success(monkeypatch, tmp_path):
    source, output = tmp_path / "source.mp4", tmp_path / "toan_aas_ai_edit_1.mp4"
    source.write_bytes(b"source")
    output.write_bytes(b"")
    monkeypatch.setattr(validation.video_local_validation, "validate_mp4_output", lambda *_a, **_k: {"ok": False, "reason": "zero_bytes"})
    assert validation.validate_final_edited_mp4(
        output,
        source_path=source,
        workspace=tmp_path,
        ffmpeg_path="ffmpeg",
    )["ok"] is False


def test_aiedit1_original_input_not_accepted_as_edited_output(monkeypatch, tmp_path):
    source, output = tmp_path / "source.mp4", tmp_path / "toan_aas_ai_edit_2.mp4"
    source.write_bytes(b"same")
    output.write_bytes(b"same")
    monkeypatch.setattr(validation.video_local_validation, "validate_mp4_output", lambda *_a, **_k: {"ok": True})
    result = validation.validate_final_edited_mp4(
        output,
        source_path=source,
        workspace=tmp_path,
        ffmpeg_path="ffmpeg",
    )
    assert result["reason"] == "original_input_returned_as_edit"


def test_aiedit1_duration_validation(monkeypatch, tmp_path):
    source, output = tmp_path / "source.mp4", tmp_path / "toan_aas_ai_edit_3.mp4"
    source.write_bytes(b"source")
    output.write_bytes(b"different")
    seen = {}
    def validator(*_a, **kwargs):
        seen.update(kwargs)
        return {"ok": True}
    monkeypatch.setattr(validation.video_local_validation, "validate_mp4_output", validator)
    assert validation.validate_final_edited_mp4(
        output,
        source_path=source,
        workspace=tmp_path,
        ffmpeg_path="ffmpeg",
        requested_duration_seconds=8,
    )["ok"] is True
    assert seen["expected_duration_ms"] == 8000


def test_aiedit1_delivery_required_before_success():
    job = {"id": 5, "status": "succeeded", "xu_cost": 300, "output_file_id": ""}
    text = status.public_status_text(job, {"aiedit1": 1, "stage": "delivered", "validation": "passed", "delivery": "sent"})
    assert "Hoàn tất" not in text


def test_aiedit1_no_product_video_price_reuse():
    snap = provider.pricing_snapshot({"VIDEO_AI_EDIT_PRICE_XU": "300"})
    assert snap["reused_product_video_price"] is False


def test_aiedit1_no_subdub_price_reuse():
    assert provider.pricing_snapshot({"VIDEO_AI_EDIT_PRICE_XU": "300"})["reused_subdub_price"] is False


def test_aiedit1_unconfigured_price_blocks_before_submit():
    env = valid_env(VIDEO_AI_EDIT_PRICE_XU="0")
    decision = provider.submit_source_policy(provider.PUBLIC_FINAL_CONFIRM_SOURCE, public_user_confirmed=True, lane="generative", env=env)
    assert decision["reason"] == "ai_edit_price_unconfigured"


def test_aiedit1_no_charge_before_valid_delivery():
    handler = source_between(BOT_SOURCE, "def handle_video_ai_edit_worker_job_update", "async def submit_video_ai_edit_job")
    assert handler.index("delivered = bool(") < handler.index("spend_fixed_credit_info(")
    assert 'progress.get("validation") == "passed"' in handler
    assert 'progress.get("delivery") == "sent"' in handler


def test_aiedit1_provider_failure_no_charge():
    handler = source_between(BOT_SOURCE, "def handle_video_ai_edit_worker_job_update", "async def submit_video_ai_edit_job")
    assert 'if not delivered:' in handler
    assert 'progress["charge"] = 0' in handler


def test_aiedit1_duplicate_charge_blocked():
    handler = source_between(BOT_SOURCE, "def handle_video_ai_edit_worker_job_update", "async def submit_video_ai_edit_job")
    assert 'if previous_status in {"succeeded", "failed", "cancelled"}' in handler
    assert "charge_idempotency_key" in handler


def test_aiedit1_no_payos_changes():
    assert "payos" not in SERVICE_SOURCES.lower()
    assert "payment" not in SERVICE_SOURCES.lower()


def test_aiedit1_progress_monotonic():
    result = status.reconcile_progress({"stage": "downloading_result", "poll_count": 3}, {"stage": "ai_processing", "poll_count": 2})
    assert result["stage"] == "downloading_result" and result["poll_count"] == 3


def test_aiedit1_no_fake_provider_progress():
    result = status.reconcile_progress({}, {"stage": "ai_processing", "poll_count": 4})
    assert "provider_progress_percent" not in result
    assert result["provider_progress_source"] == "unavailable"


def test_aiedit1_single_terminal_outcome():
    terminal = status.reconcile_progress({"stage": "failed_no_charge", "reason": "x"}, {"stage": "delivered"})
    assert terminal["stage"] == "failed_no_charge"


def test_aiedit1_no_internal_provider_copy():
    text = status.public_status_text({"id": 1, "status": "running"}, {"stage": "ai_processing", "aiedit1": 1})
    assert not any(term in text.lower() for term in status.INTERNAL_PUBLIC_TERMS)


def test_aiedit1_hidden_freeze_not_shown_as_public_maintenance():
    snap = provider.feature_snapshot({"VIDEO_AI_EDIT_HIDDEN_SUBMIT_FREEZE": "true"})
    assert snap["hidden_submit_freeze"] is True
    assert snap["public_maintenance_freeze"] is False


def test_aiedit1_status_masks_secrets():
    payload = status.admin_status_payload(provider.feature_snapshot(valid_env()))
    rendered = json.dumps(payload)
    assert "fixture-secret" not in rendered
    assert "auth_header_value" not in rendered


def test_aiedit1_debug_reports_submit_source():
    job = {"id": 1, "status": "running", "provider": "x", "input_file_id": json.dumps({"submit_source": provider.PUBLIC_FINAL_CONFIRM_SOURCE}), "error_short": status.progress_json("ai_processing")}
    assert status.job_debug_payload(job)["submit_source"] == provider.PUBLIC_FINAL_CONFIRM_SOURCE


def test_aiedit1_debug_reports_validation_and_charge_truth():
    progress = status.progress_json("delivered", validation="passed", delivery="sent", charge_status="charged_after_delivery")
    debug = status.job_debug_payload({"id": 1, "status": "succeeded", "input_file_id": "{}", "error_short": progress})
    assert debug["validation"] == "passed"
    assert debug["delivery"] == "sent"
    assert debug["charge_status"] == "charged_after_delivery"


def test_aiedit1_forbidden_artifacts_blocked(tmp_path):
    path = tmp_path / "backup.mp4"
    path.write_bytes(b"x")
    assert validation.artifact_delivery_allowed(path, workspace=tmp_path) is False


def test_aiedit1_database_not_delivered(tmp_path):
    path = tmp_path / "data.sqlite"
    path.write_bytes(b"x")
    assert validation.artifact_delivery_allowed(path, workspace=tmp_path) is False


def test_aiedit1_path_traversal_blocked(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"x")
    assert validation.artifact_delivery_allowed(outside, workspace=workspace) is False


def test_aiedit1_no_shell_true():
    assert "shell=True" not in SERVICE_SOURCES
    assert "command_uses_shell\": False" in SERVICE_SOURCES


def test_aiedit1_safe_output_name():
    assert validation.safe_output_name("job/../7") == "toan_aas_ai_edit_job-7.mp4"
    assert validation.safe_output_name(123) == "toan_aas_ai_edit_123.mp4"
