import re
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

import bot


def _git_changed_paths_against_origin_main() -> set[str]:
    repo = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        ["git", "diff", "--name-only", "origin/main"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return set()
    return {line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()}


def pytest_collection_modifyitems(config, items):
    changed = _git_changed_paths_against_origin_main()
    if not changed:
        return
    branch_scoped_static_guards = {
        "test_p0_17c1_static_guard_no_unrelated_files_touched": "docs/reports/P0_17C1_PAYOS_SIGNATURE_IDEMPOTENCY.md",
        "test_p0_17c2_static_guard_no_unrelated_files_touched": "docs/reports/P0_17C2_PAYOS_AUTO_TOPUP_LIMITS.md",
        "test_p0_17c4_static_guard_no_unrelated_files_touched": "docs/reports/P0_17C4_WEBHOOK_DB_HTML_SECURITY_EVENTS.md",
        "test_no_engine_files_touched_for_pricing_combo_task": "tests/test_p0_21b_clean_pricing_packages_combos_back_routing.py",
        "test_music_h14m_scope_does_not_touch_forbidden_runtime_areas": "tests/test_p0_23h14m_music_delivery_lock_no_duplicate_mp3_no_late_x.py",
        "test_h14n_no_product_video_subdub_voice_payos_db_changes": "tests/test_p0_23h14n_music_female_real_output_and_one_mp3_only.py",
        "test_h14o_does_not_touch_product_video_subdub_voice_payos_db": "tests/test_p0_23h14o_music_female_suggestion_one_mp3_only.py",
        "test_cost2_no_music_changes": "tests/test_p0_cost2_provider_quota_cycle_reset_alert_baseline.py",
        "test_m4live1_no_product_video_runtime_changes": "tests/test_p0_19m_m4live1_subdub_style_renderer_only_and_dub_modes_restore.py",
        "test_m4live4_no_product_video_changes": "tests/test_p0_19m_m4live4_subdub_mode_specific_restore.py",
        "test_m4live4_subtitle_dub_does_not_touch_subtitle_only_lane": "tests/test_p0_19m_m4live4_subdub_mode_specific_restore.py",
        "test_m4live6_scope_is_subdub_and_backup_guard_only": "tests/test_p0_19m_m4live6_restore_m4live2_and_block_artifacts.py",
        "test_pr321_no_product_video_music_payos_files_touched": "tests/test_p0_19m_pr321_subdub_no_extra_srt_no_dub_fail.py",
        "test_no_music_product_video_subdub_runtime_touched": "tests/test_p0_cskh1_telegram_business_auto_support_bot.py",
        "test_product_video_runtime_untouched": "tests/test_p0_cskh2_toan_aas_training_data_playbook.py",
        "test_cskh2a_no_product_video_runtime_changes": "tests/test_p0_cskh2a_business_arm_mode_without_connection.py",
        "test_cskh3_no_product_video_runtime_changes": "tests/test_p0_cskh3_conversation_brain_natural_replies.py",
        "test_cskh4_no_product_video_runtime_changes": "tests/test_p0_cskh4_aas_product_knowledge_pricing_mixed_intents.py",
        "test_videoflow_lock_no_product_video_provider_changes": "tests/test_p0_video_uiflow_lock_current_good_flow.py",
    }
    for item in items:
        report_path = branch_scoped_static_guards.get(item.name)
        if report_path and report_path not in changed:
            item.add_marker(pytest.mark.skip(reason=f"{item.name} applies only to its scoped branch diff."))


@pytest.fixture
def tmp_path(request):
    root = Path(__file__).resolve().parents[1] / ".pytest_tmp"
    root.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", request.node.name)[:80] or "test"
    path = root / f"{safe_name}_{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(autouse=True)
def legacy_dubbing_flow_tests_keep_engine_routes_open(monkeypatch, request):
    """Keep legacy state-machine tests on their original internal routes.

    Production defaults keep the new B12.5 public router gates closed. Tests
    outside the B12.5 gate suite still exercise the voice/combo state machines,
    so they opt into those routes here without enabling public custom voice.
    """
    if request.node.path.name == "test_p0_17b12_5_live_router_gate.py":
        return
    monkeypatch.setattr(bot, "PUBLIC_VOICE_VIDEO_ENABLED", True)
    monkeypatch.setattr(bot, "PUBLIC_SUBTITLE_DUB_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_DUB_PUBLIC_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_SUBTITLE_PLUS_DUB_PUBLIC_ENABLED", True)
