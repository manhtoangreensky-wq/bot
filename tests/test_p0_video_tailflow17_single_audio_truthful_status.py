from __future__ import annotations

import asyncio
import re
from pathlib import Path
from types import SimpleNamespace

from services import video_tail9


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    pattern = re.compile(rf"^(?:async )?def {re.escape(name)}\(", re.MULTILINE)
    match = pattern.search(BOT_SOURCE)
    assert match, f"missing function: {name}"
    next_match = re.search(r"\n(?=@|(?:async )?def [A-Za-z_])", BOT_SOURCE[match.end() :])
    end = match.end() + next_match.start() if next_match else len(BOT_SOURCE)
    return BOT_SOURCE[match.start() : end]


def _load_function(name: str, namespace: dict | None = None):
    scope = dict(namespace or {})
    exec("from __future__ import annotations\n" + _function_source(name), scope)
    return scope[name]


def _callback_rows(markup) -> list[list[str]]:
    rows = getattr(markup, "inline_keyboard", markup)
    return [
        [str(getattr(button, "callback_data", button[1])) for button in row]
        for row in rows
    ]


def test_product_video_public_renderers_do_not_emit_literal_backslash_newlines() -> None:
    planning_renderers = re.findall(
        r"^def (video_ai_real_(?:prompt_page|pilot_)[A-Za-z0-9_]*(?:payload|text))\(",
        BOT_SOURCE,
        re.MULTILINE,
    )
    tail_renderers = [
        name
        for name in re.findall(
            r"^def (video_tail9_[A-Za-z0-9_]*_text)\(",
            BOT_SOURCE,
            re.MULTILINE,
        )
        if "video_edit" not in name
    ]
    renderer_names = [
        *planning_renderers,
        *tail_renderers,
        "video_tail9_scene_script_info",
    ]
    offenders = [
        name
        for name in renderer_names
        if re.search(r"\\\\n", _function_source(name))
    ]

    assert planning_renderers
    assert tail_renderers
    assert offenders == []


def _ready_tail(source: str = "content_profiles", scene_count: int = 1) -> dict:
    state = video_tail9.new_state(
        product_type="video_ai_real",
        session_id=f"tailflow17-{source}-{scene_count}",
        scene_count=scene_count,
        ratio="9:16",
        estimated_duration=scene_count * 8,
    )
    return video_tail9.apply_content_contract(
        state,
        {
            "content_source": source,
            "canonical_content_mode": source,
            "selected_prompt_text": "Prompt video da chon.",
            "selected_prompt_revision": 2,
            "per_scene_content": [
                {"scene_index": index, "provider_prompt": f"Prompt canh {index}"}
                for index in range(1, scene_count + 1)
            ],
            "plan_status": "ready",
        },
    )


def _invoice_tail(total_xu: int = 300) -> dict:
    state = video_tail9.mark_branding_skipped(_ready_tail())
    state = video_tail9.prepare_summary(state)
    return video_tail9.select_package(
        state,
        quality_tier_id=str(total_xu),
        package_id=f"product_video_{total_xu}",
        pricing_snapshot={
            "quality_xu": total_xu,
            "price_xu": total_xu,
            "total_xu": total_xu,
            "scene_count": 1,
        },
        capability_snapshot={"ok": True, "engine_route": "video_ai_canonical"},
    )


def test_tailflow17_has_no_second_mandatory_audio_screen() -> None:
    state = _ready_tail()
    assert video_tail9.TAIL_FLOW_VERSION == 17
    assert video_tail9.next_required_screen(state) == "logo"

    state = video_tail9.mark_branding_skipped(state)
    assert state["audio_status"] == "not_configured"
    assert video_tail9.next_required_screen(state) == "summary"

    state = video_tail9.prepare_summary(state)
    assert state["summary_status"] == "ready"
    assert video_tail9.next_required_screen(state) == ""


def test_scene3_restores_the_single_planning_audio_route() -> None:
    handler = _function_source("handle_video_profile_studio_callback")
    requirements = handler[
        handler.index('if action == "req_none":') : handler.index('if action == "material":')
    ]

    assert 'video_profile_studio_step(context, state, "audio_plan")' in requirements
    assert "finalize_audio_planning(state, skip=True)" not in requirements
    assert 'if action == "audio_open":' in handler
    assert 'post_return_step="audio_plan"' in handler
    assert 'if action == "audio_review":' in handler
    assert 'if action in {"audio_done", "audio_skip"}:' in handler
    assert 'return_step == "summary"' in handler
    assert 'video_tail9_render(query, uid, context, "summary")' in handler


def test_summary_audio_edit_uses_planning_screen_not_duplicate_tail_screen() -> None:
    handler = _function_source("handle_video_tail_callback")
    summary = handler[
        handler.index('if section == "summary":') : handler.index('if section == "audio":')
    ]
    renderer = _function_source("video_tail9_render")

    assert "video_tail9_open_planning_audio" in summary
    assert 'video_tail9_render(query, uid, context, "audio")' not in summary
    assert "video_tail9_audio_text" not in renderer
    assert "video_tail9_audio_keyboard" not in renderer


def test_single_audio_screen_has_exact_buttons_and_no_removed_namespace() -> None:
    keyboard = _load_function(
        "video_scene3_audio_plan_keyboard",
        {
            "video_scene3_keyboard": lambda rows: rows,
            "video_scene3_nav_rows": lambda: [
                [("Quay lại", "vprofile|back"), ("Menu chính", "menu|main")]
            ],
        },
    )
    rows = _callback_rows(keyboard({"postproduction_addons": {}}))
    assert rows == [
        ["vprofile|audio_open|dubbing", "vprofile|audio_open|subtitles"],
        ["vprofile|audio_open|source_audio", "vprofile|audio_open|music"],
        ["vprofile|audio_open|sfx", "vprofile|audio_review"],
        ["vprofile|audio_done", "vprofile|audio_skip"],
        ["vprofile|back", "menu|main"],
    ]
    assert "def video_tail9_audio_text" not in BOT_SOURCE
    assert "def video_tail9_audio_keyboard" not in BOT_SOURCE
    assert "def video_tail9_volume_keyboard" not in BOT_SOURCE


def test_planning_audio_contract_preserves_32_and_idea_parent_context() -> None:
    post = {
        "dubbing": {"enabled": True, "value": {"volume": 125}},
        "subtitles": {"enabled": True, "value": {}},
        "music": {"enabled": False, "value": {"volume": 20}},
    }
    for source in ("content_profiles", "idea_catalog"):
        original = _ready_tail(source=source, scene_count=2)
        expected = {
            key: original[key]
            for key in (
                "video_product_type",
                "video_session_id",
                "content_source",
                "selected_prompt",
                "scene_count",
                "ratio",
                "scene_content",
            )
        }
        synced = video_tail9.apply_planning_audio_contract(
            original,
            post,
            planning_complete=True,
        )
        assert {key: synced[key] for key in expected} == expected
        assert synced["audio_status"] == "configured"
        assert synced["audio_config"]["dubbing"] is True
        assert synced["audio_config"]["subtitles"] is True
        assert synced["audio_config"]["volumes"]["dubbing"] == 125


def test_submit_preflight_reports_one_truthful_blocker_in_required_order() -> None:
    state = _invoice_tail(300)
    result = video_tail9.evaluate_submit_preflight(
        state,
        available_xu=200,
        provider_ready=False,
        worker_ready=False,
        admin_detail="provider_internal_blocker",
    )

    assert set(
        (
            "allowed",
            "blocker_code",
            "public_message",
            "admin_detail",
            "required_xu",
            "available_xu",
            "missing_xu",
            "provider_ready",
            "worker_ready",
            "invoice_valid",
            "existing_job_id",
        )
    ).issubset(result)
    assert result["allowed"] is False
    assert result["blocker_code"] == "insufficient_balance"
    assert result["required_xu"] == 300
    assert result["available_xu"] == 200
    assert result["missing_xu"] == 100
    assert "Còn thiếu: <b>100 Xu</b>" in result["public_message"]


def test_submit_preflight_recovers_job_and_admin_bypasses_balance() -> None:
    state = _invoice_tail(300)
    recovered = video_tail9.evaluate_submit_preflight(
        state,
        available_xu=0,
        provider_ready=False,
        worker_ready=False,
        existing_job_id="451",
    )
    assert recovered["allowed"] is True
    assert recovered["existing_job_id"] == "451"
    assert recovered["blocker_code"] == ""

    internal = video_tail9.evaluate_submit_preflight(
        state,
        available_xu=0,
        provider_ready=True,
        worker_ready=True,
        is_admin_or_owner=True,
    )
    assert internal["allowed"] is True
    assert internal["required_xu"] == 0
    assert internal["missing_xu"] == 0


def test_provider_blocker_is_public_safe_and_internal_detail_is_retained() -> None:
    result = video_tail9.evaluate_submit_preflight(
        _invoice_tail(200),
        available_xu=200,
        provider_ready=False,
        worker_ready=True,
        admin_detail="provider_alpha_probation_lock",
    )
    assert result["blocker_code"] == "provider_unavailable"
    assert result["admin_detail"] == "provider_alpha_probation_lock"
    assert "TOAN AAS chưa thể bắt đầu xử lý video lúc này" in result["public_message"]
    assert "provider_alpha" not in result["public_message"]
    assert "probation" not in result["public_message"]


def test_invoice_and_worker_blockers_follow_balance_provider_precedence() -> None:
    invalid = video_tail9.evaluate_submit_preflight(
        _ready_tail(),
        available_xu=0,
        provider_ready=False,
        worker_ready=False,
    )
    assert invalid["blocker_code"] == "invoice_invalid"

    worker = video_tail9.evaluate_submit_preflight(
        _invoice_tail(200),
        available_xu=200,
        provider_ready=True,
        worker_ready=False,
        admin_detail="worker_version_mismatch",
    )
    assert worker["blocker_code"] == "worker_unavailable"
    assert worker["admin_detail"] == "worker_version_mismatch"
    assert "worker" not in worker["public_message"].lower()


def test_malformed_invoice_preflight_returns_a_blocker_instead_of_generic_x() -> None:
    state = _invoice_tail(300)
    state["pricing_snapshot"]["total_xu"] = "not-a-number"

    result = video_tail9.evaluate_submit_preflight(
        state,
        available_xu=300,
        provider_ready=True,
        worker_ready=True,
    )

    assert result["allowed"] is False
    assert result["blocker_code"] == "invoice_invalid"
    assert "Hóa đơn" in result["public_message"]


def test_submit_callback_checks_balance_before_provider_and_hands_job_to_b14_status() -> None:
    handler = _function_source("handle_video_tail_callback")
    confirm = handler[handler.index('if section == "confirm":') :]

    assert "video_tail9.evaluate_submit_preflight" in confirm
    assert confirm.index("get_user(uid)") < confirm.index("product_video_public_preflight_evaluation")
    assert "video_tail9_render_confirmed_status" in confirm
    assert "video_b14_send_or_edit_status_panel" in _function_source(
        "video_tail9_render_confirmed_status"
    )
    assert "video_b14_queue_status_text" in _function_source(
        "video_b14_send_or_edit_status_panel"
    )


def test_insufficient_balance_callback_stops_before_admission_job_and_bridge() -> None:
    tail = _invoice_tail(300)
    saved: list[dict] = []
    messages: list[str] = []
    admission_calls = 0
    bridge_calls = 0

    def admission(*_args, **_kwargs):
        nonlocal admission_calls
        admission_calls += 1
        return {"ready": True}

    async def bridge(_update, _context):
        nonlocal bridge_calls
        bridge_calls += 1
        return None

    async def send(_query, text, **_kwargs):
        messages.append(str(text))
        return "insufficient"

    handler = _load_function(
        "handle_video_tail_callback",
        {
            "video_tail9_context": lambda _uid, _context: (dict(tail), "scene3", {}),
            "video_tail9": video_tail9,
            "save_video_tail9_state": lambda _uid, _context, state, _owner, _host: saved.append(dict(state)),
            "video_b14_is_admin_or_owner": lambda _uid: False,
            "get_user": lambda _uid: (200, None, None),
            "safe_int": lambda value, default=0: int(value) if str(value).isdigit() else default,
            "product_video_public_preflight_evaluation": admission,
            "product_video_worker_admission_status": lambda: {"worker_version_compatible": True},
            "handle_product_video_public_confirm_callback": bridge,
            "safe_edit_or_send": send,
            "video_tail9_submit_preflight_keyboard": lambda result: result["blocker_code"],
            "video_tail9_submit_blocker_text": lambda: "fallback",
        },
    )

    class Query:
        id = "tailflow17-insufficient"
        data = "video_tail|confirm|submit"
        from_user = SimpleNamespace(id=17001)

        async def answer(self, *_args, **_kwargs):
            return None

    result = asyncio.run(handler(SimpleNamespace(callback_query=Query()), SimpleNamespace()))

    assert result == "insufficient"
    assert admission_calls == 0
    assert bridge_calls == 0
    assert len(messages) == 1
    assert "Còn thiếu: <b>100 Xu</b>" in messages[0]
    assert saved[-1]["submit_preflight_snapshot"]["blocker_code"] == "insufficient_balance"
    assert saved[-1]["job_id"] == ""
    assert saved[-1]["final_confirmed"] is False


def test_submit_preflight_ack_timeout_preserves_truthful_blocker_and_stops_before_bridge() -> None:
    tail = _invoice_tail(300)
    saved: list[dict] = []
    rendered: list[dict] = []
    bridge_calls = 0

    async def bridge(_update, _context):
        nonlocal bridge_calls
        bridge_calls += 1
        return None

    def prepare(_uid, _context, state, _owner, _host, *, snapshot):
        prepared = dict(state)
        prepared["submit_preflight_snapshot"] = dict(snapshot)
        return prepared

    async def render(_query, _context, _uid, state, _owner, _host):
        rendered.append(dict(state))
        return state["submit_preflight_snapshot"]["blocker_code"]

    handler = _load_function(
        "handle_video_tail_callback",
        {
            "video_tail9_context": lambda _uid, _context: (dict(tail), "scene3", {}),
            "video_tail9": video_tail9,
            "VIDEO_TAIL9_TEXT_INPUT_KEY": "video_tail9_text_input",
            "VIDEO_TAIL9_DEFERRED_RUNTIME_PRODUCTS": frozenset(),
            "save_video_tail9_state": lambda _uid, _context, state, _owner, _host: saved.append(dict(state)),
            "get_user_language": lambda _uid: "vi",
            "logger": SimpleNamespace(warning=lambda *_args, **_kwargs: None),
            "video_b14_is_admin_or_owner": lambda _uid: True,
            "get_user": lambda _uid: (200, None, None),
            "safe_int": lambda value, default=0: int(value) if str(value).isdigit() else default,
            "product_video_public_preflight_evaluation": lambda *_args, **_kwargs: {
                "ready": False,
                "preflight_resolved_state": "blocked",
                "blocker_code": "provider_probation_lock",
            },
            "product_video_worker_admission_status": lambda: {
                "worker_version_compatible": False,
                "worker_admission_block_reason": "provider_probation_lock",
            },
            "video_tail9_prepare_submit_status": prepare,
            "video_tail9_render_confirmed_status": render,
            "handle_product_video_public_confirm_callback": bridge,
        },
    )

    class Query:
        id = "tailflow17-provider-blocked"
        data = "video_tail|confirm|submit"
        from_user = SimpleNamespace(id=17002)

        async def answer(self, *_args, **_kwargs):
            raise TimeoutError("Telegram callback ACK timed out")

    result = asyncio.run(handler(SimpleNamespace(callback_query=Query()), SimpleNamespace()))

    assert result == "provider_unavailable"
    assert bridge_calls == 0
    assert rendered[-1]["submit_preflight_snapshot"]["blocker_code"] == "provider_unavailable"
    assert saved[-1]["submit_preflight_snapshot"]["blocker_code"] == "provider_unavailable"
    assert saved[-1]["job_id"] == ""
    assert saved[-1]["final_confirmed"] is False


def test_owner_admin_charge_guard_runs_before_wallet_charge_runner() -> None:
    source = _function_source("product_video_charge_after_final_delivery")
    guard = source.index("video_b14_is_admin_or_owner(user_id)")
    runner = source.index("charge_runner = charge_func or spend_fixed_credit_info")
    assert guard < runner
    assert '"charged_xu": 0' in source[guard:runner]
    assert "admin_owner_free" in source[guard:runner]


def test_owner_admin_delivery_path_never_calls_wallet_charge_runner() -> None:
    updates: list[dict] = []
    charge_calls = 0
    queue = SimpleNamespace(
        get_video_render_job=lambda _conn, _jid: {"id": 71, "project_id": 9, "user_id": 17002, "result_json": "{}"},
        get_video_project=lambda _conn, _pid: {"project_id": 9, "user_id": 17002},
        product_video_delivery_charge_decision=lambda _project, _job, _result: {
            "ok": True,
            "amount_xu": 300,
            "charge_idempotency_key": "delivery:71:300",
        },
    )

    def charge(*_args, **_kwargs):
        nonlocal charge_calls
        charge_calls += 1
        raise AssertionError("owner/admin wallet charge must not run")

    function = _load_function(
        "product_video_charge_after_final_delivery",
        {
            "safe_int": lambda value, default=0: int(value) if str(value).isdigit() else default,
            "db_connect": lambda: None,
            "video_project_queue": queue,
            "_video_debug_json": lambda _value, default: dict(default),
            "product_video_charge_amount_after_delivery": lambda *_args: {"amount_xu": 300},
            "video_b14_is_admin_or_owner": lambda _uid: True,
            "_video_provider_update_job_result": lambda _conn, _jid, payload: updates.append(dict(payload)),
            "spend_fixed_credit_info": charge,
        },
    )
    result = function(71, conn=object(), charge_func=charge)

    assert result["ok"] is True
    assert result["charged_xu"] == 0
    assert result["charge_skip_reason"] == "admin_owner_free"
    assert charge_calls == 0
    assert updates[-1]["wallet_charge_recorded"] is False


def test_status_panel_is_the_pr460_canonical_panel() -> None:
    status = _function_source("video_b14_queue_status_text")
    keyboard = _function_source("video_b14_queue_status_keyboard")

    assert "TOAN AAS đang xử lý video" in status
    assert "Mã xử lý" in status
    assert "Gói" in status
    assert "Số cảnh" in status
    assert "Cập nhật trạng thái" in keyboard
    assert "b14_job_status" in keyboard
    assert "b14_invoice_screen" in keyboard
    assert 'draft.get("public_processing_code")' in status


def test_shared_b14_insufficient_balance_copy_and_navigation_match_tail() -> None:
    text_source = _function_source("video_b14_insufficient_balance_text")
    keyboard_source = _function_source("video_b14_insufficient_balance_keyboard")

    for phrase in (
        "Chưa đủ Xu để bắt đầu tạo video",
        "Tổng thanh toán",
        "Số dư hiện tại",
        "Còn thiếu",
        "chưa gọi nguồn dựng",
    ):
        assert phrase in text_source
    for callback in (
        "menu|main_topup",
        "vproduct|b14_quality_screen",
        "vproduct|b14_invoice_screen",
        "menu|main",
    ):
        assert callback in keyboard_source
