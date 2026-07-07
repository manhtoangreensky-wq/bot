import asyncio
import json
import subprocess
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import bot
from services import product_video_duration_decision as duration2


ROOT = Path(__file__).resolve().parents[1]


class FakeMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append({"text": str(text), **kwargs})
        return SimpleNamespace(text=str(text), **kwargs)


def _changed_files() -> set[str]:
    tracked = subprocess.run(
        ["git", "diff", "--name-only", "origin/main"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        line.strip().replace("\\", "/")
        for line in (tracked.stdout + "\n" + untracked.stdout).splitlines()
        if line.strip()
        and not line.strip().replace("\\", "/").startswith(("pytest-baseline", ".pytest_tmp"))
    }


def test_duration2_config_defaults_scene_clip_mode():
    cfg = duration2.load_duration_decision()
    assert cfg["provider"] == "shopaikey_video"
    assert cfg["model"] == "veo3.1-fast"
    assert cfg["public_mode"] == "scene_clip"
    assert cfg["short_clip_seconds"] == 8
    assert cfg["seconds_pricing_enabled"] is False
    assert cfg["smoke_policy"]["provider_submit_in_tests"] is False


def test_duration2_smoke_admin_only(monkeypatch):
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: False)
    update = SimpleNamespace(effective_user=SimpleNamespace(id=123), message=FakeMessage())
    context = SimpleNamespace(args=["8"])

    asyncio.run(bot.cmd_video_duration_smoke(update, context))

    assert update.message.replies
    assert "chỉ dành cho admin" in update.message.replies[-1]["text"]


def test_duration2_smoke_records_requested_but_blocks_paid_provider(monkeypatch):
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    update = SimpleNamespace(effective_user=SimpleNamespace(id=1), message=FakeMessage())
    context = SimpleNamespace(args=["8"])

    asyncio.run(bot.cmd_video_duration_smoke(update, context))

    text = "\n".join(item["text"] for item in update.message.replies)
    assert "Requested" in text
    assert "8s" in text
    assert duration2.REAL_PROVIDER_BLOCKED_REASON in text
    assert "Provider call: <code>NO</code>" in text
    assert "Xu deducted: <code>NO</code>" in text


def test_duration2_duration_measurement_required_for_pass():
    result = duration2.duration_smoke_dry_run(8)
    assert result["ok"] is False
    assert result["actual_seconds"] is None
    assert result["classification"] == "not_run_cost_locked"


def test_duration2_only_8s_keeps_scene_clip_mode():
    cfg = duration2.classify_duration_smokes([{"requested_seconds": 8, "actual_seconds": 8, "status": "supported_exact"}])
    assert cfg["public_mode"] == "scene_clip"
    assert cfg["short_clip_seconds"] == 8
    assert cfg["seconds_pricing_enabled"] is False


def test_duration2_4_6_8_still_not_arbitrary_seconds():
    cfg = duration2.classify_duration_smokes(
        [
            {"requested_seconds": 4, "actual_seconds": 4},
            {"requested_seconds": 6, "actual_seconds": 6},
            {"requested_seconds": 8, "actual_seconds": 8},
        ]
    )
    assert cfg["public_mode"] == "scene_clip"
    assert cfg["supported_exact_durations"] == [4, 6, 8]
    assert cfg["arbitrary_seconds_supported"] is False


def test_duration2_16s_exact_enables_seconds_mode():
    cfg = duration2.classify_duration_smokes([{"requested_seconds": 16, "actual_seconds": 16}])
    assert cfg["public_mode"] == "seconds_long_video"
    assert cfg["seconds_pricing_enabled"] is True
    assert cfg["max_single_video_seconds"] == 16


def test_duration2_ignored_20s_keeps_scene_clip():
    cfg = duration2.classify_duration_smokes([{"requested_seconds": 20, "actual_seconds": 8, "status": "ignored_to_default"}])
    assert cfg["public_mode"] == "scene_clip"
    assert cfg["seconds_pricing_enabled"] is False


def test_duration2_failed_smoke_keeps_safe_mode():
    previous = duration2.load_duration_decision()
    cfg = duration2.classify_duration_smokes([{"requested_seconds": 12, "status": "failed"}], previous=previous)
    assert cfg["public_mode"] == "scene_clip"
    assert cfg["seconds_pricing_enabled"] is False


def test_duration2_scene_mode_1_scene_8s_promo_200():
    cfg = duration2.load_duration_decision()
    price = duration2.scene_price(1, cfg, today=date(2026, 7, 7))
    assert price["list_price"] == 300
    assert price["promo_price"] == 200
    assert price["charge_price"] == 200
    assert price["public_enabled"] is True


def test_duration2_scene_mode_no_false_18s():
    text = "\n".join(duration2.public_contract_lines(duration2.load_duration_decision()))
    assert "18s" not in text
    assert "6-8s" in text


def test_duration2_scene_mode_2_3_scenes_hidden_until_concat_pass():
    cfg = duration2.load_duration_decision()
    assert duration2.scene_price(2, cfg)["public_enabled"] is False
    assert duration2.scene_price(3, cfg)["public_enabled"] is False
    cfg["multi_scene_enabled"] = True
    cfg["concat_enabled"] = True
    cfg["scene_pricing"]["scenes"]["2"]["public_enabled"] = True
    assert duration2.scene_price(2, cfg)["public_enabled"] is True


def test_duration2_scene_mode_after_promo_uses_list_price():
    cfg = duration2.load_duration_decision()
    price = duration2.scene_price(1, cfg, today=date(2027, 1, 1))
    assert price["promo_active"] is False
    assert price["charge_price"] == 300


def test_duration2_seconds_mode_enabled_only_after_long_smoke():
    cfg = duration2.classify_duration_smokes([{"requested_seconds": 20, "actual_seconds": 20}])
    assert cfg["public_mode"] == "seconds_long_video"
    assert duration2.seconds_price(8, cfg, today=date(2026, 7, 7))["charge_price"] == 200
    assert duration2.seconds_price(12, cfg, today=date(2026, 7, 7))["charge_price"] == 300
    assert duration2.seconds_price(24, cfg, today=date(2026, 7, 7))["allowed"] is False


def test_duration2_seconds_mode_no_scene_wording():
    cfg = duration2.classify_duration_smokes([{"requested_seconds": 12, "actual_seconds": 12}])
    text = "\n".join(duration2.public_contract_lines(cfg)).lower()
    assert "chọn số giây" in text
    assert "1 cảnh" not in text


def test_duration2_prompt_simple_product_fits_one_scene():
    result = duration2.estimate_prompt_video_fit("chai nước hoa xoay nhẹ trên bàn")
    assert result["fit"] == "one_short_clip"
    assert result["billing_authority"] is False


def test_duration2_prompt_cooking_recommends_storyboard_or_multiscene():
    result = duration2.estimate_prompt_video_fit("video hướng dẫn nấu món phở từng bước")
    assert result["fit"] == "use_storyboard_or_multiscene"
    assert result["billing_authority"] is False


def test_duration2_prompt_static_images_recommends_img2vid():
    result = duration2.estimate_prompt_video_fit("ghép chuỗi ảnh tĩnh thành video")
    assert result["fit"] == "use_img2vid"
    assert result["billing_authority"] is False


def test_duration2_public_copy_matches_mode_scene():
    text = "\n".join(duration2.public_contract_lines(duration2.load_duration_decision()))
    assert "Video AI ngắn" in text
    assert "Giá gốc 300 Xu" in text
    assert "Ưu đãi đến hết năm 200 Xu" in text


def test_duration2_public_copy_matches_mode_seconds():
    cfg = duration2.classify_duration_smokes([{"requested_seconds": 16, "actual_seconds": 16}])
    text = "\n".join(duration2.public_contract_lines(cfg))
    assert "Video AI theo thời lượng" in text
    assert "Giá ưu đãi đến hết năm 25 Xu/giây" in text


def test_duration2_capability_command_safe(monkeypatch):
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    update = SimpleNamespace(effective_user=SimpleNamespace(id=1), message=FakeMessage())
    asyncio.run(bot.cmd_video_duration_capability(update, SimpleNamespace(args=[])))
    text = "\n".join(item["text"] for item in update.message.replies)
    assert "VIDEO DURATION CAPABILITY" in text
    assert "Provider call: <code>NO</code>" in text


def test_duration2_commands_registered_and_valid_length():
    source = Path("bot.py").read_text(encoding="utf-8")
    assert 'CommandHandler("video_duration_capability", cmd_video_duration_capability)' in source
    assert 'CommandHandler("video_duration_smoke", cmd_video_duration_smoke)' in source
    assert len("video_duration_capability") <= 32
    assert len("video_duration_smoke") <= 32


def test_duration2_config_json_valid():
    payload = json.loads((ROOT / "config" / "product_video_duration_decision.json").read_text(encoding="utf-8"))
    assert payload["public_mode"] == "scene_clip"
    assert payload["scene_pricing"]["scenes"]["1"]["promo_price"] == 200


def test_duration2_scope_locks_no_forbidden_runtime_changes():
    changed = _changed_files()
    allowed = {
        "bot.py",
        "config/product_video_duration_decision.json",
        "services/product_video_duration_decision.py",
        "tests/test_p0_video_duration2_scene_or_seconds_pricing_decision.py",
        "tests/test_p0_video_uiflow_lock_current_good_flow.py",
        "tests/test_p0_video_uiflow1_align_video_ai_flows_to_hot_trend.py",
    }
    assert changed <= allowed
    joined = " ".join(changed).lower()
    for forbidden in ("music", "suno", "subdub", "payos", "wallet", "pricing_matrix", "video_image_to_video_flow"):
        assert forbidden not in joined
