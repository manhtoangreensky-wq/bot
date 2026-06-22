import inspect
from pathlib import Path

import bot


ROOT = Path(__file__).resolve().parents[1]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def test_ui_flow_freeze_marker_doc_exists():
    doc = ROOT / "docs" / "flow_freeze_rules.md"
    text = doc.read_text(encoding="utf-8")
    assert "FREEZE_UI_FLOW_RULES_LOCKED_2026_06_23" in text
    assert "UI/flow frozen" in text
    assert "Back route rule" in text
    assert "Public copy rule" in text
    assert "No interface changes without explicit instruction" in text


def test_engine_roadmap_doc_covers_required_audit_sections():
    doc = ROOT / "docs" / "reports" / "TOAN_AAS_ENGINE_ROADMAP_VOICE_MUSIC_SUBTITLE_VIDEO.md"
    text = doc.read_text(encoding="utf-8")
    for price in ("200", "300", "400", "500", "600", "800", "1000", "1200", "1500"):
        assert f"| {price} Xu |" in text
    for section in (
        "MiniMax Voice",
        "Suno Music",
        "Subtitle, Translate, Dub",
        "Multi-Scene 120s Architecture",
        "Long Video 2h Architecture",
        "Risk, Cost, Quota, Telegram Limit",
        "Public Ready, Admin Smoke, Guarded",
    ):
        assert section in text
    assert "does not claim `public ready`" in text


def test_admin_engine_status_commands_registered_and_admin_only():
    source = Path(bot.__file__).read_text(encoding="utf-8")
    expected = {
        "voice_engine_status": bot.cmd_voice_engine_status,
        "music_engine_status": bot.cmd_music_engine_status,
        "subtitle_engine_status": bot.cmd_subtitle_engine_status,
        "video_engine_status": bot.cmd_video_engine_status,
    }
    for command, handler in expected.items():
        assert f'CommandHandler("{command}", {handler.__name__})' in source
        handler_source = inspect.getsource(handler)
        assert "is_admin_user" in handler_source
        assert "reply_html_lines" in handler_source


def test_video_flow_order_locked():
    assert bot.VIDEO_FLOW_LOCKED_AFTER_TASK3D7 is True
    assert _callbacks(bot.video_finalization_menu_keyboard("vi")) == [
        "vfinal|voice",
        "vfinal|music",
        "vfinal|addon",
        "vfinal|logo",
        "vfinal|skip",
        "vfinal|tier",
        "vfinal|back",
        "vfinal|main",
    ]
    assert [
        callback
        for callback in _callbacks(bot.video_finalization_tier_keyboard("vi"))
        if callback.startswith("vfinal|tier|")
    ] == [f"vfinal|tier|{tier}" for tier in bot.VIDEO_TIER_ORDER]
    assert _callbacks(bot.video_finalization_scene_count_keyboard({"selected_video_tier": "low"}, "vi")) == [
        "vfinal|scene_count|1",
        "vfinal|upgrade_300",
        "vfinal|back",
        "vfinal|main",
    ]
    assert _callbacks(bot.video_finalization_scene_count_keyboard({"selected_video_tier": "basic"}, "vi")) == [
        "vfinal|scene_count|1",
        "vfinal|scene_count|3",
        "vfinal|scene_count|5",
        "vfinal|scene_count|10",
        "vfinal|scene_count|20",
        "vfinal|scene_custom",
        "vfinal|back",
        "vfinal|main",
    ]


def test_image_flow_order_locked():
    assert _callbacks(bot.quick_image_prepared_prompt_keyboard("vi")) == [
        "create_media|qi_choose_ratio",
        "create_media|qi_logo_choice",
        "create_media|qi_rewrite",
        "create_media|qi_custom",
        "create_media|qi_topics",
        "create_media|qi_back_suggestions",
        "menu|main",
    ]
    assert _callbacks(bot.quick_image_logo_choice_keyboard("vi")) == [
        "create_media|qi_logo_add",
        "create_media|qi_logo_skip",
        "create_media|qi_back_prompt",
        "menu|main",
    ]
    assert _callbacks(bot.quick_image_logo_input_keyboard("vi")) == ["create_media|qi_logo_choice", "menu|main"]
    assert _callbacks(bot.quick_image_logo_confirm_keyboard("vi")) == ["create_media|qi_logo_confirm", "create_media|qi_logo_add"]
    assert "create_media|qi_ratio_4x5" in _callbacks(bot.quick_image_ratio_keyboard("vi"))
    assert "create_media|qi_tier_low" in _callbacks(bot.quick_image_tier_keyboard("vi"))


def test_public_invoice_and_guard_copy_have_no_technical_terms():
    public_texts = [
        bot.PUBLIC_PRODUCT_MAINTENANCE_VI,
        bot.PUBLIC_PRODUCT_MAINTENANCE_EN,
        bot.VIDEO_MULTISCENE_PUBLIC_GUARD_TEXT,
        *bot.VIDEO_COMPLETED_ADDON_GUARD_TEXTS.values(),
        bot.public_product_maintenance_text("vi", "Video"),
        bot.music_ai_public_guard_text("vi"),
        bot.voice_clone_provider_not_ready_public_text("vi"),
        bot.video_addon_guard_text("vi"),
        bot.video_dubbing_guard_text(bot.VIDEO_SUBTITLE_MODE_CREATE, {}, "vi", admin=False),
        bot.ui_text("vi", "video.queue_submitted", task_id="task_123", auto_poll="ON"),
    ]
    for tier in bot.VIDEO_TIER_ORDER:
        scene_count = 1 if tier == "low" else 3
        state = {
            "video_tier": tier,
            "selected_video_tier": tier,
            "selected_scene_count": scene_count,
            "selected_video_aspect_ratio": "9:16",
            "pending_payload": {
                "job_type": "video",
                "video_tier": tier,
                "base_cost": bot.video_tier_cost_xu(tier),
                "selected_scene_count": scene_count,
            },
        }
        public_texts.append(bot.video_quote_invoice_text(bot.calculate_video_quote(state), state, "vi"))

    forbidden = ("đang kiểm thử", "provider", "task", "job", "api", "shopaikey", "key4u", "token", "secret")
    for text in public_texts:
        lowered = text.lower()
        for term in forbidden:
            assert term not in lowered


def test_all_video_tiers_route_to_invoice_export_or_clean_guard():
    expected_costs = {
        "low": 200,
        "basic": 300,
        "common": 400,
        "advanced": 500,
        "standard": 600,
        "high": 800,
        "future_1000": 1000,
        "future_1200": 1200,
        "future_1500": 1500,
    }
    assert [bot.video_tier_cost_xu(tier) for tier in bot.VIDEO_TIER_ORDER] == [
        expected_costs[tier] for tier in bot.VIDEO_TIER_ORDER
    ]

    engine_rows = {row["tier"]: row for row in bot.video_engine_tier_status_rows()}
    status_text = "\n".join(bot.video_engine_status_lines())
    for tier in bot.VIDEO_TIER_ORDER:
        scene_count = 1 if tier == "low" else 3
        state = {
            "video_tier": tier,
            "selected_video_tier": tier,
            "selected_scene_count": scene_count,
            "selected_video_aspect_ratio": "9:16",
            "pending_payload": {
                "job_type": "video",
                "video_tier": tier,
                "base_cost": bot.video_tier_cost_xu(tier),
                "selected_scene_count": scene_count,
            },
        }
        quote = bot.calculate_video_quote(state)
        invoice = bot.video_quote_invoice_text(quote, state, "vi")
        callbacks = _callbacks(bot.video_addon_confirm_keyboard("route-token", tier, "vi", state))
        assert "Hóa đơn xác nhận video" in invoice
        assert "Xuất video" in invoice
        assert callbacks[0] == "videoaddon|export|route-token"
        assert "videoaddon|back" in callbacks
        assert tier in engine_rows
        assert engine_rows[tier]["stage"] in {"PUBLIC_READY", "CONFIGURED_SMOKE_REQUIRED_GUARDED", "GUARDED"}
        if engine_rows[tier]["public_ready"]:
            assert engine_rows[tier]["smoke_pass"] is True
        assert f"{expected_costs[tier]} Xu:" in status_text
    assert "invoice/export or guard <code>YES</code>" in status_text


def test_maintenance_copy_has_no_forbidden_terms():
    maintenance_texts = [
        bot.PUBLIC_PRODUCT_MAINTENANCE_VI,
        bot.PUBLIC_PRODUCT_MAINTENANCE_EN,
        bot.VIDEO_MULTISCENE_PUBLIC_GUARD_TEXT,
        *bot.VIDEO_COMPLETED_ADDON_GUARD_TEXTS.values(),
    ]
    forbidden = ("đang kiểm thử", "provider", "task", "job", "api", "shopaikey")
    for text in maintenance_texts:
        lowered = text.lower()
        for term in forbidden:
            assert term not in lowered
