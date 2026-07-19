import base64
import hashlib
import hmac
import json
import sqlite3
import time
import uuid
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from webapp_core_bridge import _web_link_callback_headers, build_core_bridge_router, confirm_web_link_from_telegram


def make_app(tmp_path, monkeypatch):
    db_path = tmp_path / "bridge.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE users (user_id TEXT PRIMARY KEY, username TEXT, credits INTEGER, total_spent INTEGER, is_vip INTEGER, join_date TEXT);
        INSERT INTO users VALUES ('u-1', 'User', 321, 9, 0, '2026-01-01');
        CREATE TABLE credit_events (id INTEGER PRIMARY KEY, user_id TEXT, delta INTEGER, balance_after INTEGER, event_type TEXT, ref_id TEXT, note TEXT, created_at TEXT);
        INSERT INTO credit_events VALUES (1, 'u-1', 10, 321, 'topup', 'order-1', 'ok', '2026-01-01');
        CREATE TABLE shopaikey_jobs (id INTEGER PRIMARY KEY, user_id TEXT, job_type TEXT, status TEXT, created_at TEXT, updated_at TEXT, xu_cost_planned INTEGER, xu_deducted INTEGER, result_url TEXT);
        INSERT INTO shopaikey_jobs VALUES (1, 'u-1', 'video_single', 'success', '2026-01-01', '2026-01-01', 20, 20, 'https://private.example.invalid/output.mp4');
        CREATE TABLE payos_orders (order_code TEXT PRIMARY KEY, user_id TEXT, amount INTEGER, xu INTEGER, order_type TEXT, status TEXT, created_at TEXT, paid_at TEXT);
        CREATE TABLE feedback (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, username TEXT, category TEXT, content TEXT, context TEXT, status TEXT, timestamp TEXT);
        """
    )
    conn.commit()
    conn.close()

    def db_connect():
        return sqlite3.connect(db_path)

    core = {
        "db_connect": db_connect,
        "is_admin_user": lambda user_id: str(user_id) == "admin-1",
        "engine_readiness_registry": lambda: {"video_single": {"configured": True, "public_ready": True, "reason": "ready", "missing": [], "adapter": "video"}},
        "media_workflow_pricing_payload": lambda: {
            "billing_mode": "tiered_media_pricing",
            "price_table_source": "test",
            "image_tiers": {"low": {"label": "Ảnh tiết kiệm", "cost": 50, "note": "test"}},
            "video_tiers": {"basic": {"label": "Video cơ bản", "cost": 300, "note": "test"}},
            "video_combos": [{"code": "basic_199k", "label": "Combo cơ bản", "price_vnd": 199000, "display_price": "199k", "summary": "test"}],
            "workflow_content_total_cost": 20,
        },
        "package_catalog_payload": lambda: {
            "combos": {"basic_199k": {"label": "Combo cơ bản", "items": {"video_common": 3}, "note": "test"}},
            "monthly": {"starter_monthly": {"label": "Starter", "items": {"image_standard": 10}, "default_days": 30}},
        },
        "package_purchase_price_vnd": lambda package_type, code: 199000 if package_type == "combo" else 299000,
        "free_hub_meta_prompt_pack": lambda text: {"title": f"Prompt {text}", "meta_prompts": [{"label": "Ngắn", "text": text}]},
        "free_hub_caption_pack": lambda text: {"title": f"Caption {text}", "captions": [{"hook": text, "hashtags": ["#TOANAAS"]}]},
        "free_hub_content_ideas_pack": lambda text: {"title": f"Ý tưởng {text}", "video_ideas": [text]},
        "free_hub_image_video_prompt_pack": lambda text: {"title": f"Media {text}", "image_video_prompts": {"image_9x16": text}},
        "hook_script_pack": lambda text: {"hooks": [text], "script_15s": f"15s {text}"},
        "generate_contextual_prompt": lambda text, context=None: {"title": f"Video {text}", "prompt": text, "context": context or {}},
        "storyboard_pack_build_payload": lambda state, lang="vi": {"topic": state.get("selected_topic"), "shot_count": 1, "shots": [{"shot": 1, "image_prompt": state.get("selected_topic")}]},
        "calculate_chat_cost": lambda length: max(1, int(length)),
        "workflow_script_storyboard_cost_xu": lambda: 20,
        "workflow_content_cost_xu": lambda: 35,
        "calculate_scene_video_price": lambda base, scenes: int(base) * int(scenes) * (90 if int(scenes) > 1 else 100) // 100,
        "video_scene_discount_percent": lambda scenes: 90 if int(scenes) > 1 else 100,
        "user_voice_profile_rows": lambda user_id, limit=20, offset=0, include_inactive=True: [{
            "id": "voice-1", "display_name": "Giọng thương hiệu", "status": "active", "is_default": 1,
            "consent_status": "confirmed", "provider_voice_id": "private-provider-voice-id",
            "preview_audio_ref": "private-preview-ref", "created_at": "2026-01-01", "updated_at": "2026-01-02",
        }] if str(user_id) == "u-1" else [],
        "voice_profile_can_generate_tts": lambda profile: bool(profile.get("provider_voice_id")) and profile.get("status") == "active",
        "voice_profile_can_preview": lambda profile: bool(profile.get("preview_audio_ref")),
        "voice_tts_credit_estimate": lambda text: {"chars": len(text), "billable_blocks": 1, "price_xu": 17},
        "estimate_voice_duration_seconds": lambda text, speed="normal": 6 if speed == "normal" else 8,
        "voice_profile_storage_price_xu": lambda user_id, product_context="showroom", profile_id=0: 47,
        "music_copyright_block_reason": lambda text: "giống nghệ sĩ" if "giống nghệ sĩ" in str(text).lower() else "",
        "music_prompt_mode": lambda description="", mode="": mode or "background",
        "music_prompt_suggestions": lambda description, offset=0, lang="vi", mode="": [{
            "name": "Nhạc sáng", "mood": "tươi", "tempo": "120 BPM", "instrument": "synth",
            "duration": "30s", "vocal": "no vocal", "use_case": "short video",
        }],
        "music_prompt_from_suggestion": lambda item: f"Original {item.get('name')} prompt",
        "music_result_duration_seconds": lambda result: 60 if result.get("song_length_mode") == "half" else int(result.get("guided_duration_seconds") or 30),
        "music_result_product_kind": lambda result: "song_half" if result.get("song_length_mode") == "half" else ("song_seconds" if result.get("song_product") == "seconds" else "background"),
        "music_result_price_xu": lambda result: 88 if result.get("song_length_mode") == "half" else 33,
        "calculate_music_price": lambda project: {"music_option": project.get("music_option"), "music_item_count": int(project.get("sfx_count") or 0), "music_xu": 21 if project.get("music_option") == "sfx_library" else 0, "music_notes": []},
        "normalize_video_translate_mode": lambda mode: {
            "subtitle": "subtitle_create", "subtitle_create": "subtitle_create", "translate_subtitle": "subtitle_translate", "subtitle_translate": "subtitle_translate", "dub": "dub", "subtitle_plus_dub": "subtitle_plus_dub",
        }.get(str(mode), ""),
        "video_dubbing_capability": lambda mode, state=None, public=True: {"ok": False, "reason": "public_disabled", "missing": ["public_flag"], "mux": "not_enabled_audio_output_only"},
        "calculate_video_translate_price": lambda mode, duration, translation_enabled=False: {"mode": mode, "duration_seconds": int(duration), "billable_minutes": 2, "unit_price_xu": 30, "total_price_xu": 60},
        "video_dubbing_tts_price_estimate": lambda mode, duration=0, output_text="": {"chars": 1000 if mode in {"dubbing", "subtitle_plus_dubbing"} else 0, "price_xu": 20 if mode in {"dubbing", "subtitle_plus_dubbing"} else 0, "estimated": True},
        "video_dubbing_invoice_breakdown": lambda state: {"subtitle_xu": 20, "translation_xu": 10 if state.get("target_language") else 0, "voice_xu": 0, "mix_xu": 0, "total_xu": 60},
        "doc_tools_status_payload": lambda: {"ready_basic": True, "image_to_pdf": True, "pdf_to_word": True, "pdf_to_images": True, "compress_pdf": True, "split_pdf": True, "merge_pdf": True, "ocr_local": False, "pdf_library_error": "must-not-leak"},
        "doc_cost": lambda action, pages=1: 0,
        "normalize_translate_target": lambda value: "vi" if str(value).lower().startswith("tiếng việt") else "en" if str(value).lower().startswith("english") else "",
    }
    monkeypatch.setenv("CORE_BRIDGE_TOKEN", "test-token")
    monkeypatch.setenv("CORE_BRIDGE_HMAC_SECRET", "test-secret")
    monkeypatch.setenv("WEBAPP_PROVIDER_CALLS_ENABLED", "false")
    app = FastAPI()
    app.include_router(build_core_bridge_router(core))
    return TestClient(app)


def signed_headers(method, path, body=b"", actor="u-1", request_id=None):
    request_id = request_id or str(uuid.uuid4())
    timestamp = str(int(time.time()))
    digest = hashlib.sha256(body).hexdigest()
    material = f"{timestamp}.{request_id}.{method}.{path}.{digest}".encode()
    signature = hmac.new(b"test-secret", material, hashlib.sha256).hexdigest()
    return {
        "Authorization": "Bearer test-token",
        "X-TOAN-AAS-Timestamp": timestamp,
        "X-TOAN-AAS-Request-ID": request_id,
        "X-TOAN-AAS-Signature": signature,
        "X-TOAN-AAS-Actor-ID": actor,
        "Content-Type": "application/json",
    }


def test_wallet_jobs_and_feature_draft_are_private_and_canonical(tmp_path, monkeypatch):
    with make_app(tmp_path, monkeypatch) as client:
        wallet = client.get("/internal/v1/wallet?user_id=u-1", headers=signed_headers("GET", "/internal/v1/wallet"))
        assert wallet.status_code == 200
        assert wallet.json()["data"]["balance_xu"] == 321
        jobs = client.get("/internal/v1/jobs?user_id=u-1", headers=signed_headers("GET", "/internal/v1/jobs"))
        assert jobs.json()["data"]["items"][0]["id"] == "shopaikey_jobs:1"
        delivery = client.get("/internal/v1/assets/shopaikey_jobs:1/download?user_id=u-1", headers=signed_headers("GET", "/internal/v1/assets/shopaikey_jobs:1/download"))
        assert delivery.json()["status"] == "guarded"
        assert delivery.json()["error_code"] == "SIGNED_DELIVERY_ADAPTER_REQUIRED"
        assert "private.example.invalid" not in delivery.text
        body = json.dumps({"user_id": "u-1", "input": {"prompt": "x"}}, separators=(",", ":")).encode()
        draft = client.post("/internal/v1/features/video_single/draft", content=body, headers=signed_headers("POST", "/internal/v1/features/video_single/draft", body))
        assert draft.json()["status"] == "draft"


def test_confirm_is_guarded_and_signature_rejects_tampering(tmp_path, monkeypatch):
    with make_app(tmp_path, monkeypatch) as client:
        body = json.dumps({"user_id": "u-1", "input": {}, "idempotency_key": "confirm-bridge-0001"}, separators=(",", ":")).encode()
        confirmed = client.post("/internal/v1/features/video_single/confirm", content=body, headers=signed_headers("POST", "/internal/v1/features/video_single/confirm", body))
        assert confirmed.json()["status"] == "guarded"
        denied = client.get("/internal/v1/wallet?user_id=u-1", headers={"Authorization": "Bearer test-token"})
        assert denied.status_code == 401
        assert denied.json()["ok"] is False
        assert denied.json()["error_code"] == "CORE_BRIDGE_UNAUTHORIZED"


def test_signed_request_id_is_a_one_time_nonce(tmp_path, monkeypatch):
    with make_app(tmp_path, monkeypatch) as client:
        headers = signed_headers("GET", "/internal/v1/wallet", request_id="nonce-replay-test-0001")
        first = client.get("/internal/v1/wallet?user_id=u-1", headers=headers)
        assert first.status_code == 200
        replay = client.get("/internal/v1/wallet?user_id=u-1", headers=headers)
        assert replay.status_code == 409
        assert replay.json()["ok"] is False
        assert replay.json()["error_code"] == "CORE_BRIDGE_REPLAYED_REQUEST"


def test_tickets_are_canonical_and_idempotent(tmp_path, monkeypatch):
    with make_app(tmp_path, monkeypatch) as client:
        body = json.dumps({"user_id": "u-1", "subject": "Need help", "detail": "Ticket from web", "idempotency_key": "ticket-bridge-0001"}, separators=(",", ":")).encode()
        created = client.post("/internal/v1/support/tickets", content=body, headers=signed_headers("POST", "/internal/v1/support/tickets", body))
        assert created.json()["status"] == "queued"
        repeated = client.post("/internal/v1/support/tickets", content=body, headers=signed_headers("POST", "/internal/v1/support/tickets", body))
        assert repeated.json()["data"]["id"] == created.json()["data"]["id"]
        tickets = client.get("/internal/v1/support/tickets?user_id=u-1", headers=signed_headers("GET", "/internal/v1/support/tickets"))
        assert tickets.json()["data"]["items"][0]["subject"] == "Need help"


def test_upload_staging_validates_ownership_and_feature_references(tmp_path, monkeypatch):
    with make_app(tmp_path, monkeypatch) as client:
        content = b"%PDF-1.4\nprivate-web-upload"
        upload_payload = {
            "user_id": "u-1",
            "file_name": "brief.pdf",
            "content_type": "application/pdf",
            "content_base64": base64.b64encode(content).decode("ascii"),
            "sha256": hashlib.sha256(content).hexdigest(),
            "idempotency_key": "upload-bridge-0001",
        }
        body = json.dumps(upload_payload, separators=(",", ":")).encode()
        uploaded = client.post("/internal/v1/uploads", content=body, headers=signed_headers("POST", "/internal/v1/uploads", body))
        assert uploaded.status_code == 200
        assert uploaded.json()["status"] == "completed"
        metadata = uploaded.json()["data"]
        assert metadata["file_name"] == "brief.pdf"
        assert metadata["content_size"] == len(content)
        assert "content" not in metadata
        repeated = client.post("/internal/v1/uploads", content=body, headers=signed_headers("POST", "/internal/v1/uploads", body))
        assert repeated.json()["data"]["id"] == metadata["id"]

        draft_payload = {"user_id": "u-1", "input": {"prompt": "Use attached brief", "upload_ids": [metadata["id"]]}}
        draft_body = json.dumps(draft_payload, separators=(",", ":")).encode()
        draft = client.post("/internal/v1/features/video_single/draft", content=draft_body, headers=signed_headers("POST", "/internal/v1/features/video_single/draft", draft_body))
        assert draft.json()["status"] == "draft"
        assert draft.json()["data"]["uploads"][0]["id"] == metadata["id"]

        missing_payload = {"user_id": "u-1", "input": {"upload_ids": ["missing-upload-id"]}}
        missing_body = json.dumps(missing_payload, separators=(",", ":")).encode()
        missing = client.post("/internal/v1/features/video_single/draft", content=missing_body, headers=signed_headers("POST", "/internal/v1/features/video_single/draft", missing_body))
        assert missing.json()["status"] == "failed"
        assert missing.json()["error_code"] == "UPLOAD_NOT_FOUND"


def test_pricing_and_packages_are_read_from_bot_helpers_only(tmp_path, monkeypatch):
    with make_app(tmp_path, monkeypatch) as client:
        pricing = client.get("/internal/v1/pricing?user_id=u-1", headers=signed_headers("GET", "/internal/v1/pricing"))
        assert pricing.status_code == 200
        assert pricing.json()["data"]["image_tiers"][0]["cost_xu"] == 50
        assert "provider_cost" not in pricing.text

        packages = client.get("/internal/v1/packages?user_id=u-1", headers=signed_headers("GET", "/internal/v1/packages"))
        assert packages.status_code == 200
        assert packages.json()["data"]["monthly"][0]["price_vnd"] == 299000


def test_content_image_and_storyboard_drafts_use_provider_free_bot_helpers(tmp_path, monkeypatch):
    with make_app(tmp_path, monkeypatch) as client:
        caption_payload = {"user_id": "u-1", "input": {"request": "cà phê sạch"}}
        caption_body = json.dumps(caption_payload, ensure_ascii=False, separators=(",", ":")).encode()
        caption = client.post(
            "/internal/v1/features/caption/draft",
            content=caption_body,
            headers=signed_headers("POST", "/internal/v1/features/caption/draft", caption_body),
        )
        assert caption.json()["status"] == "draft"
        assert caption.json()["data"]["draft"]["source"] == "bot.free_hub_caption_pack"
        assert caption.json()["data"]["draft"]["content"]["captions"][0]["hook"] == "cà phê sạch"
        assert caption.json()["data"]["provider_called"] is False
        assert caption.json()["data"]["charged_xu"] == 0

        storyboard_payload = {"user_id": "u-1", "input": {"request": "nước hoa nam", "format": "9:16", "duration": "15s"}}
        storyboard_body = json.dumps(storyboard_payload, ensure_ascii=False, separators=(",", ":")).encode()
        storyboard = client.post(
            "/internal/v1/features/storyboard/draft",
            content=storyboard_body,
            headers=signed_headers("POST", "/internal/v1/features/storyboard/draft", storyboard_body),
        )
        assert storyboard.json()["data"]["draft"]["content"]["shots"][0]["image_prompt"] == "nước hoa nam"

        estimate_payload = {"user_id": "u-1", "input": {"prompt": "ảnh sản phẩm", "tier": "low"}}
        estimate_body = json.dumps(estimate_payload, ensure_ascii=False, separators=(",", ":")).encode()
        estimate = client.post(
            "/internal/v1/features/image_create/estimate",
            content=estimate_body,
            headers=signed_headers("POST", "/internal/v1/features/image_create/estimate", estimate_body),
        )
        assert estimate.json()["status"] == "awaiting_confirm"
        assert estimate.json()["data"]["estimate"]["estimated_xu"] == 50
        assert estimate.json()["data"]["estimate"]["pricing_rule"] == "bot.media_workflow_pricing_payload.image_tiers"


def test_video_draft_and_multiscene_estimate_use_bot_planning_and_pricing_helpers(tmp_path, monkeypatch):
    with make_app(tmp_path, monkeypatch) as client:
        draft_payload = {"user_id": "u-1", "input": {"brief": "serum dưỡng da", "format": "9:16", "duration": "8s"}}
        draft_body = json.dumps(draft_payload, ensure_ascii=False, separators=(",", ":")).encode()
        draft = client.post(
            "/internal/v1/features/video_product/draft",
            content=draft_body,
            headers=signed_headers("POST", "/internal/v1/features/video_product/draft", draft_body),
        )
        assert draft.json()["status"] == "draft"
        assert draft.json()["data"]["draft"]["source"] == "bot.generate_contextual_prompt"
        assert draft.json()["data"]["draft"]["content"]["prompt"] == "serum dưỡng da"

        estimate_payload = {"user_id": "u-1", "input": {"brief": "serum dưỡng da", "tier": "basic", "scene_count": "3"}}
        estimate_body = json.dumps(estimate_payload, ensure_ascii=False, separators=(",", ":")).encode()
        estimate = client.post(
            "/internal/v1/features/video_multiscene/estimate",
            content=estimate_body,
            headers=signed_headers("POST", "/internal/v1/features/video_multiscene/estimate", estimate_body),
        )
        assert estimate.json()["status"] == "awaiting_confirm"
        assert estimate.json()["data"]["estimate"]["estimated_xu"] == 810
        assert estimate.json()["data"]["estimate"]["scene_discount_percent"] == 90
        assert estimate.json()["data"]["estimate"]["pricing_rule"] == "bot.calculate_scene_video_price"


def test_voice_vault_and_estimates_use_bot_helpers_without_leaking_provider_references(tmp_path, monkeypatch):
    with make_app(tmp_path, monkeypatch) as client:
        profiles = client.get("/internal/v1/voice/profiles?user_id=u-1", headers=signed_headers("GET", "/internal/v1/voice/profiles"))
        assert profiles.status_code == 200
        profile = profiles.json()["data"]["items"][0]
        assert profile["id"] == "voice-1"
        assert profile["tts_ready"] is True
        assert profile["preview_ready"] is True
        assert "provider_voice_id" not in profiles.text
        assert "private-preview-ref" not in profiles.text

        estimate_payload = {"user_id": "u-1", "input": {"script": "Xin chào TOAN AAS", "voice_profile_id": "voice-1", "speed": "normal"}}
        estimate_body = json.dumps(estimate_payload, ensure_ascii=False, separators=(",", ":")).encode()
        estimate = client.post(
            "/internal/v1/features/voice_saved_tts/estimate",
            content=estimate_body,
            headers=signed_headers("POST", "/internal/v1/features/voice_saved_tts/estimate", estimate_body),
        )
        assert estimate.json()["status"] == "awaiting_confirm"
        assert estimate.json()["data"]["estimate"]["estimated_xu"] == 17
        assert estimate.json()["data"]["estimate"]["duration_seconds"] == 6
        assert estimate.json()["data"]["estimate"]["selected_voice_profile"]["display_name"] == "Giọng thương hiệu"

        invalid_payload = {"user_id": "u-1", "input": {"script": "Xin chào", "voice_profile_id": "not-owned"}}
        invalid_body = json.dumps(invalid_payload, ensure_ascii=False, separators=(",", ":")).encode()
        invalid = client.post(
            "/internal/v1/features/voice_saved_tts/estimate",
            content=invalid_body,
            headers=signed_headers("POST", "/internal/v1/features/voice_saved_tts/estimate", invalid_body),
        )
        assert invalid.json()["status"] == "guarded"
        assert invalid.json()["data"]["estimate"]["reason"] == "voice_profile_not_found"


def test_voice_clone_requires_owned_audio_and_explicit_consent_before_estimate(tmp_path, monkeypatch):
    with make_app(tmp_path, monkeypatch) as client:
        audio = b"RIFF\x24\x00\x00\x00WAVEfmt "
        upload_payload = {
            "user_id": "u-1", "file_name": "voice-sample.wav", "content_type": "audio/wav",
            "content_base64": base64.b64encode(audio).decode("ascii"), "sha256": hashlib.sha256(audio).hexdigest(),
            "idempotency_key": "voice-clone-upload-0001",
        }
        upload_body = json.dumps(upload_payload, separators=(",", ":")).encode()
        uploaded = client.post("/internal/v1/uploads", content=upload_body, headers=signed_headers("POST", "/internal/v1/uploads", upload_body))
        upload_id = uploaded.json()["data"]["id"]

        missing_consent_payload = {"user_id": "u-1", "input": {"display_name": "Giọng demo", "upload_ids": [upload_id], "consent": False}}
        missing_consent_body = json.dumps(missing_consent_payload, separators=(",", ":")).encode()
        missing_consent = client.post(
            "/internal/v1/features/voice_clone/draft",
            content=missing_consent_body,
            headers=signed_headers("POST", "/internal/v1/features/voice_clone/draft", missing_consent_body),
        )
        assert missing_consent.json()["status"] == "draft"
        assert missing_consent.json()["data"]["draft"]["reason"] == "voice_clone_consent_required"

        valid_payload = {"user_id": "u-1", "input": {"display_name": "Giọng demo", "upload_ids": [upload_id], "consent": True}}
        valid_body = json.dumps(valid_payload, separators=(",", ":")).encode()
        draft = client.post(
            "/internal/v1/features/voice_clone/draft",
            content=valid_body,
            headers=signed_headers("POST", "/internal/v1/features/voice_clone/draft", valid_body),
        )
        assert draft.json()["data"]["draft"]["content"]["sample_staged"] is True
        estimate = client.post(
            "/internal/v1/features/voice_clone/estimate",
            content=valid_body,
            headers=signed_headers("POST", "/internal/v1/features/voice_clone/estimate", valid_body),
        )
        assert estimate.json()["status"] == "awaiting_confirm"
        assert estimate.json()["data"]["estimate"]["estimated_xu"] == 47
        assert estimate.json()["data"]["estimate"]["consent_required"] is True

        confirm_payload = {"user_id": "u-1", "input": valid_payload["input"], "idempotency_key": "voice-clone-confirm-0001"}
        confirm_body = json.dumps(confirm_payload, separators=(",", ":")).encode()
        confirm = client.post(
            "/internal/v1/features/voice_clone/confirm",
            content=confirm_body,
            headers=signed_headers("POST", "/internal/v1/features/voice_clone/confirm", confirm_body),
        )
        assert confirm.json()["status"] == "guarded"
        assert confirm.json()["error_code"] == "WEBAPP_PROVIDER_CALLS_DISABLED"


def test_music_drafts_and_quotes_reuse_bot_policy_prompt_and_price_helpers(tmp_path, monkeypatch):
    with make_app(tmp_path, monkeypatch) as client:
        draft_payload = {"user_id": "u-1", "input": {"brief": "nhạc nền giới thiệu sản phẩm", "mode": "background", "duration_seconds": "30"}}
        draft_body = json.dumps(draft_payload, ensure_ascii=False, separators=(",", ":")).encode()
        draft = client.post(
            "/internal/v1/features/music_background/draft",
            content=draft_body,
            headers=signed_headers("POST", "/internal/v1/features/music_background/draft", draft_body),
        )
        assert draft.json()["status"] == "draft"
        assert draft.json()["data"]["draft"]["source"] == "bot.music_prompt_suggestions"
        assert draft.json()["data"]["draft"]["content"]["suggestions"][0]["prompt"] == "Original Nhạc sáng prompt"
        assert draft.json()["data"]["provider_called"] is False

        estimate_payload = {"user_id": "u-1", "input": {"brief": "bài hát giới thiệu", "song_length_mode": "half"}}
        estimate_body = json.dumps(estimate_payload, ensure_ascii=False, separators=(",", ":")).encode()
        estimate = client.post(
            "/internal/v1/features/music_song/estimate",
            content=estimate_body,
            headers=signed_headers("POST", "/internal/v1/features/music_song/estimate", estimate_body),
        )
        assert estimate.json()["status"] == "awaiting_confirm"
        assert estimate.json()["data"]["estimate"]["estimated_xu"] == 88
        assert estimate.json()["data"]["estimate"]["product_kind"] == "song_half"

        sfx_payload = {"user_id": "u-1", "input": {"brief": "tiếng mở hộp", "item_count": "2"}}
        sfx_body = json.dumps(sfx_payload, ensure_ascii=False, separators=(",", ":")).encode()
        sfx = client.post(
            "/internal/v1/features/music_sfx/estimate",
            content=sfx_body,
            headers=signed_headers("POST", "/internal/v1/features/music_sfx/estimate", sfx_body),
        )
        assert sfx.json()["status"] == "awaiting_confirm"
        assert sfx.json()["data"]["estimate"]["estimated_xu"] == 21
        assert sfx.json()["data"]["estimate"]["pricing_rule"] == "bot.calculate_music_price"

        blocked_payload = {"user_id": "u-1", "input": {"brief": "làm giống nghệ sĩ nổi tiếng"}}
        blocked_body = json.dumps(blocked_payload, ensure_ascii=False, separators=(",", ":")).encode()
        blocked = client.post(
            "/internal/v1/features/music_background/draft",
            content=blocked_body,
            headers=signed_headers("POST", "/internal/v1/features/music_background/draft", blocked_body),
        )
        assert blocked.json()["data"]["draft"]["reason"] == "music_copyright_request_blocked"
        assert blocked.json()["data"]["provider_called"] is False


def test_subtitle_and_document_planning_use_canonical_contracts_without_output_claims(tmp_path, monkeypatch):
    with make_app(tmp_path, monkeypatch) as client:
        media = b"ID3\x04\x00\x00canonical-media"
        media_payload = {
            "user_id": "u-1", "file_name": "source.mp3", "content_type": "audio/mpeg",
            "content_base64": base64.b64encode(media).decode("ascii"), "sha256": hashlib.sha256(media).hexdigest(),
            "idempotency_key": "subtitle-media-upload-0001",
        }
        media_body = json.dumps(media_payload, separators=(",", ":")).encode()
        media_upload = client.post("/internal/v1/uploads", content=media_body, headers=signed_headers("POST", "/internal/v1/uploads", media_body))
        media_id = media_upload.json()["data"]["id"]

        subtitle_payload = {"user_id": "u-1", "input": {"upload_ids": [media_id], "target_language": "English", "duration_seconds": "75", "output_format": "vtt"}}
        subtitle_body = json.dumps(subtitle_payload, ensure_ascii=False, separators=(",", ":")).encode()
        subtitle = client.post(
            "/internal/v1/features/subtitle_translate/draft",
            content=subtitle_body,
            headers=signed_headers("POST", "/internal/v1/features/subtitle_translate/draft", subtitle_body),
        )
        assert subtitle.json()["status"] == "draft"
        assert subtitle.json()["data"]["draft"]["source"] == "bot.video_dubbing_capability"
        assert subtitle.json()["data"]["draft"]["content"]["capability"]["ready"] is False
        assert subtitle.json()["data"]["provider_called"] is False

        subtitle_estimate = client.post(
            "/internal/v1/features/subtitle_translate/estimate",
            content=subtitle_body,
            headers=signed_headers("POST", "/internal/v1/features/subtitle_translate/estimate", subtitle_body),
        )
        assert subtitle_estimate.json()["status"] == "awaiting_confirm"
        assert subtitle_estimate.json()["data"]["estimate"]["estimated_xu"] == 60
        assert subtitle_estimate.json()["data"]["estimate"]["pricing_rule"] == "bot.video_dubbing_invoice_breakdown"

        pdf = b"%PDF-1.4\ncanonical document"
        pdf_payload = {
            "user_id": "u-1", "file_name": "report.pdf", "content_type": "application/pdf",
            "content_base64": base64.b64encode(pdf).decode("ascii"), "sha256": hashlib.sha256(pdf).hexdigest(),
            "idempotency_key": "document-pdf-upload-0001",
        }
        pdf_body = json.dumps(pdf_payload, separators=(",", ":")).encode()
        pdf_upload = client.post("/internal/v1/uploads", content=pdf_body, headers=signed_headers("POST", "/internal/v1/uploads", pdf_body))
        pdf_id = pdf_upload.json()["data"]["id"]

        split_payload = {"user_id": "u-1", "input": {"upload_ids": [pdf_id], "page_range": "2-4", "page_count": "8"}}
        split_body = json.dumps(split_payload, separators=(",", ":")).encode()
        split = client.post(
            "/internal/v1/features/documents_split/draft",
            content=split_body,
            headers=signed_headers("POST", "/internal/v1/features/documents_split/draft", split_body),
        )
        assert split.json()["data"]["draft"]["content"]["action"] == "split_pdf"
        assert split.json()["data"]["draft"]["content"]["local_tool_status"]["split_pdf"] is True
        assert "must-not-leak" not in split.text

        split_estimate = client.post(
            "/internal/v1/features/documents_split/estimate",
            content=split_body,
            headers=signed_headers("POST", "/internal/v1/features/documents_split/estimate", split_body),
        )
        assert split_estimate.json()["status"] == "awaiting_confirm"
        assert split_estimate.json()["data"]["estimate"]["estimated_xu"] == 0
        assert split_estimate.json()["data"]["estimate"]["pricing_rule"] == "bot.doc_cost"

        invalid_split_payload = {"user_id": "u-1", "input": {"upload_ids": [pdf_id], "page_range": "2-4,8"}}
        invalid_split_body = json.dumps(invalid_split_payload, separators=(",", ":")).encode()
        invalid_split = client.post(
            "/internal/v1/features/documents_split/draft",
            content=invalid_split_body,
            headers=signed_headers("POST", "/internal/v1/features/documents_split/draft", invalid_split_body),
        )
        assert invalid_split.json()["data"]["draft"]["reason"] == "document_page_range_invalid"


def test_admin_module_adapter_is_canonical_read_only_and_role_protected(tmp_path, monkeypatch):
    with make_app(tmp_path, monkeypatch) as client:
        denied = client.get(
            "/internal/v1/admin/modules/providers?user_id=u-1",
            headers=signed_headers("GET", "/internal/v1/admin/modules/providers", actor="u-1"),
        )
        assert denied.status_code == 403

        allowed = client.get(
            "/internal/v1/admin/modules/providers?user_id=admin-1",
            headers=signed_headers("GET", "/internal/v1/admin/modules/providers", actor="admin-1"),
        )
        assert allowed.status_code == 200
        assert allowed.json()["status"] == "read_only"
        assert allowed.json()["data"]["items"][0]["feature"] == "video_single"


@pytest.mark.anyio
async def test_telegram_web_link_requires_private_callback_configuration(monkeypatch):
    monkeypatch.delenv("WEBAPP_LINK_CALLBACK_URL", raising=False)
    monkeypatch.delenv("WEBAPP_LINK_CALLBACK_TOKEN", raising=False)
    result = await confirm_web_link_from_telegram({}, "u-1", "LinkCode1234")
    assert result["status"] == "guarded"
    assert result["error_code"] == "TELEGRAM_LINK_CALLBACK_NOT_CONFIGURED"


def test_telegram_web_link_callback_signature_binds_body_and_path():
    callback_url = "https://app.example.invalid/api/v1/auth/internal/telegram-link/confirm?ignored=yes"
    body = b'{"code":"LinkCode1234","canonical_user_id":"u-1"}'
    headers = _web_link_callback_headers(
        callback_url,
        "callback-token",
        "callback-secret",
        body,
        request_id="link-callback-test-0001",
        timestamp="1777777777",
    )
    digest = hashlib.sha256(body).hexdigest()
    material = f"1777777777.link-callback-test-0001.POST./api/v1/auth/internal/telegram-link/confirm.{digest}".encode()
    expected = hmac.new(b"callback-secret", material, hashlib.sha256).hexdigest()
    assert headers["X-TOAN-AAS-BRIDGE-TOKEN"] == "callback-token"
    assert headers["X-TOAN-AAS-Signature"] == expected


def test_bot_registers_safe_telegram_link_entrypoints():
    source = (Path(__file__).parents[1] / "bot.py").read_text(encoding="utf-8")
    assert 'CommandHandler("linkweb",     cmd_linkweb)' in source
    assert 'context.args[0]).startswith("web_")' in source
