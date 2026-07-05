import asyncio
import os
import subprocess
from pathlib import Path

import pytest

import bot
from services import product_progress_status


USER_ID = 232914
TASK_ID = "1279444349692403713"
CLIP_ID = "clipH14KPr173"
BARE_CDN = f"https://cdn1.suno.ai/{CLIP_ID}.mp3"
PROVIDER_ENDPOINT = f"https://api.key4u.shop/suno/act/wav/{CLIP_ID}"
AUDIO_BYTES = b"ID3-toan-aas-h14k-real-audio" * 360


def _current_branch_name() -> str:
    for key in ("GITHUB_HEAD_REF", "GITHUB_REF_NAME", "BRANCH_NAME"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    repo = Path(__file__).resolve().parents[1]
    return subprocess.check_output(
        ["git", "-c", f"safe.directory={repo.as_posix()}", "branch", "--show-current"],
        cwd=repo,
        text=True,
    ).strip()


def _is_music_h14k_scope() -> bool:
    branch = _current_branch_name().lower()
    return "p0-23h14k" in branch or "music-pr173-vocal" in branch


class _AudioResponse:
    status_code = 200
    content = AUDIO_BYTES
    headers = {"content-type": "audio/mpeg"}
    text = ""

    def json(self):
        raise ValueError("audio")


class _Json83Response:
    status_code = 200
    content = b'{"code":"success","message":"","data":null}'
    headers = {"content-type": "application/json"}
    text = '{"code":"success","message":"","data":null}'

    def json(self):
        return {"code": "success", "message": "", "data": None}


def _client(monkeypatch, calls, *, cdn_response, endpoint_response=None):
    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None):
            calls.append(str(url))
            if "cdn1.suno.ai" in str(url):
                return cdn_response
            return endpoint_response or _Json83Response()

    monkeypatch.setattr(bot.httpx, "AsyncClient", FakeClient)


def _song_input(vocal="female", **overrides):
    data = {
        "music_product_mode": "song",
        "music_product_tier": bot.MUSIC_PRODUCT_TIER_BASIC,
        "song_vocal": vocal,
        "vocal_mode": vocal,
        "requested_vocal_mode": vocal,
        "selected_vocal_mode": vocal,
        "theme": "Bai hat thuong hieu TOAN AAS",
        "lyrics": "[Verse]\nTOAN AAS sang ngay\n[Chorus]\nCung nhau vuon xa",
        "style_prompt": "Vietnamese upbeat pop, clear chorus",
    }
    data.update(overrides)
    return data


def _raw_endpoint_candidate():
    return {
        "source": "KEY4U_SUNO_DOWNLOAD_URL",
        "field_path": "provider_download_url",
        "role": "provider_result_metadata",
        "url": PROVIDER_ENDPOINT,
        "provider_name": "key4u_suno",
        "requires_auth": True,
        "provider_download_endpoint_candidate": True,
        "provider_download_endpoint_configured": True,
        "raw_result_url": BARE_CDN,
        "raw_result_field_path": "data.data.0.cld2AudioUrl",
        "pr173_direct_raw_audio_first": True,
        "selected_reason": "provider_download_url_candidate",
        "rank": 1400,
    }


def _job(**overrides):
    data = {
        "internal_job_id": "MUSH14KRAW",
        "job_id": "MUSH14KRAW",
        "feature": "music_suno",
        "product_type": "music_song",
        "music_product_type": "music_song",
        "provider": "key4u_suno",
        "provider_name_internal": "key4u_suno",
        "provider_task_id": TASK_ID,
        "provider_job_id": TASK_ID,
        "provider_submit_called": True,
        "provider_completed": True,
        "music_provider_completed": True,
        "provider_status": "completed",
        "status": "completed",
        "progress_percent": 85,
        "music_output_url": BARE_CDN,
        "output_url": BARE_CDN,
        "result_url": BARE_CDN,
        "provider_style_prompt": "Vietnamese pop, Female vocal",
        "provider_lyrics": "[Verse]\nTOAN AAS",
        "charged_xu": 0,
    }
    data.update(overrides)
    return data


def test_female_custom_lyrics_overrides_stale_male_state():
    result = bot.music_product_result_from_input(
        _song_input(
            "female",
            selected_vocal_mode="male",
            requested_vocal_mode="female",
            style_prompt="Vietnamese upbeat pop, Male vocal should be removed",
        )
    )

    prompt = result["provider_style_prompt"]
    assert result["song_vocal"] == "female"
    assert result["selected_vocal_mode"] == "female"
    assert "Female vocal" in prompt
    assert "Male vocal" not in prompt
    assert bot.music_product_prompt_contains_vocal_hint(prompt, "female")


def test_male_custom_lyrics_keeps_male_voice_keyword():
    result = bot.music_product_result_from_input(_song_input("male"))

    assert result["song_vocal"] == "male"
    assert result["selected_vocal_mode"] == "male"
    assert "Male vocal" in result["provider_style_prompt"]
    assert "Female vocal" not in result["provider_style_prompt"]


def test_female_suggestion_flow_overrides_stale_male_state():
    state = bot.music_product_prepare_suggestions_result(
        _song_input("female", selected_vocal_mode="male"),
        idea="Bai hat quang cao thuong hieu TOAN AAS vui tuoi",
        offset=0,
        lang="vi",
    )
    selected = bot.music_product_result_from_suggestion(state, state["music_suggestions"][0])

    assert state["selected_vocal_mode"] == "female"
    assert all(item["selected_vocal_mode"] == "female" for item in state["music_suggestions"])
    assert selected["selected_vocal_mode"] == "female"
    assert "Female vocal" in selected["provider_style_prompt"]
    assert "Male vocal" not in selected["provider_style_prompt"]


def test_male_suggestion_flow_keeps_male_voice_keyword():
    state = bot.music_product_prepare_suggestions_result(
        _song_input("male"),
        idea="Bai hat quang cao thuong hieu TOAN AAS manh me",
        offset=0,
        lang="vi",
    )
    selected = bot.music_product_result_from_suggestion(state, state["music_suggestions"][0])

    assert selected["selected_vocal_mode"] == "male"
    assert "Male vocal" in selected["provider_style_prompt"]
    assert "Female vocal" not in selected["provider_style_prompt"]


def test_duet_custom_lyrics_uses_male_and_female_duet_keyword():
    result = bot.music_product_result_from_input(_song_input("duet"))

    assert result["selected_vocal_mode"] == "duet"
    assert "Male and female duet vocal" in result["provider_style_prompt"]
    assert "[Male Verse]" in result["provider_lyrics"]
    assert "[Female Verse]" in result["provider_lyrics"]


def test_manual_lyrics_screen_shows_style_prompt_before_lyrics():
    text = bot.music_product_details_input_text("song", bot.MUSIC_PRODUCT_TIER_BASIC, "female", "vi")

    assert "Style nhạc:" in text
    assert "Female vocal" in text
    assert text.index("Style nhạc:") < text.index("Lời hát:")


def test_manual_style_prompt_and_lyrics_are_parsed_separately():
    parsed = bot.music_product_parse_details(
        "\n".join([
            "Tiêu đề: Đón Nắng Mai",
            "Style nhạc: Upbeat Tropical Pop, female vocal, bright acoustic guitar, marimba, deep bouncy bass, healing vibes, 120 BPM, clean studio production",
            "Ngôn ngữ: Tiếng Việt",
            "Lời hát:",
            "[Intro]",
            "[Ocean wave sfx]",
            "(Ooh... aah...)",
            "[Verse 1]",
            "Tạm gác lại những bề bộn ngược xuôi",
            "[Chorus]",
            "Hát lên nào, đón năng lượng mới!",
        ]),
        "song",
        bot.MUSIC_PRODUCT_TIER_BASIC,
        "female",
    )
    result = bot.music_product_result_from_input(parsed)

    assert parsed["style_prompt"].startswith("Upbeat Tropical Pop")
    assert parsed["lyrics"].startswith("[Intro]")
    assert "Female vocal" in result["provider_style_prompt"]
    assert "[Ocean wave sfx]" in result["provider_lyrics"]
    assert "Style nhạc" not in result["provider_lyrics"]


def test_provider_download_endpoint_with_raw_audio_gets_raw_url_first(monkeypatch):
    calls = []
    _client(monkeypatch, calls, cdn_response=_AudioResponse(), endpoint_response=_Json83Response())

    result = asyncio.run(bot.music_download_artifact_candidate(_raw_endpoint_candidate(), _job()))

    assert result["ok"] is True
    assert result["download_strategy_used"] == "direct_raw_url"
    assert result["pr173_artifact_engine_restored"] is True
    assert result["direct_audio_url_get_attempted"] is True
    assert result["provider_download_endpoint_attempted"] is False
    assert result["provider_download_endpoint_bypassed_for_raw_audio"] is True
    assert calls == [BARE_CDN]


def test_provider_download_json_83_does_not_override_raw_audio(monkeypatch):
    calls = []
    _client(monkeypatch, calls, cdn_response=_AudioResponse(), endpoint_response=_Json83Response())

    result = asyncio.run(bot.music_download_artifact_candidate(_raw_endpoint_candidate(), _job()))

    assert result["ok"] is True
    assert result["provider_download_json_83_bytes_ignored"] is True
    assert result["wav_json_no_data_ignored_when_raw_url_present"] is True
    assert not any("api.key4u.shop" in url for url in calls)


def test_direct_raw_url_failure_is_visible_not_hidden_by_wav_json(monkeypatch):
    calls = []
    _client(monkeypatch, calls, cdn_response=_Json83Response(), endpoint_response=_Json83Response())

    result = asyncio.run(bot.music_download_artifact_candidate(_raw_endpoint_candidate(), _job()))

    assert result["ok"] is False
    assert result["direct_audio_url_get_attempted"] is True
    assert result["provider_download_endpoint_attempted"] is True
    assert result["direct_audio_url_content_type"].startswith("application/json")
    assert calls[0] == BARE_CDN
    assert any("api.key4u.shop" in url for url in calls)


def test_artifact_terminal_panel_does_not_render_5_percent():
    job = _job(
        status="failed",
        terminal_state="failed_no_charge",
        current_stage="received_request",
        stage="received_request",
        primary_blocker="artifact_download_failed",
        terminal_after_wait_exhausted=True,
        progress_percent=85,
    )

    state = product_progress_status.product_progress_stage_from_job("music_song", job)
    text = bot.product_progress_status_from_job_text("music_song", job, "MUSH14KRAW", "vi")

    assert state["current_stage"] == "validating_audio"
    assert state["percent"] >= 85
    assert "Tiến độ: 5%" not in text
    assert "Kiểm tra file nhạc" in text


def test_completed_generation_steps_do_not_render_received_request_5_percent():
    completed = ["preparing_lyrics", "preparing_style", "generating_song"]

    text = bot.product_progress_status_text(
        "music_song",
        "MUS714F7AC5",
        "received_request",
        5,
        "failed_no_charge",
        lang="vi",
        completed_steps=completed,
    )

    assert "Tiến độ: 5%" not in text
    assert "⚠️ Nhận yêu cầu" not in text
    assert "✅ Tạo bài hát" in text
    assert "⚠️ Kiểm tra file nhạc" in text


def test_completed_generation_steps_in_job_override_stale_received_stage():
    job = _job(
        status="failed",
        provider_status="processing",
        provider_completed=False,
        music_provider_completed=False,
        provider_task_id="",
        provider_job_id="",
        terminal_state="failed_no_charge",
        current_stage="received_request",
        stage="received_request",
        progress_percent=5,
        completed_steps=["preparing_lyrics", "preparing_style", "generating_song"],
        primary_blocker="artifact_download_failed",
        terminal_after_wait_exhausted=True,
    )

    state = product_progress_status.product_progress_stage_from_job("music_song", job)

    assert state["current_stage"] == "validating_audio"
    assert state["percent"] >= 85
    assert state["generation_checkpoint_done"] is True
    assert state["artifact_check_stage_allowed"] is True


def test_provider_generating_does_not_fake_jump_to_85():
    state = product_progress_status.product_progress_stage_from_job(
        "music_song",
        _job(
            status="running",
            provider_completed=False,
            music_provider_completed=False,
            progress_percent=85,
            current_stage="generating_song",
        ),
    )

    assert state["current_stage"] == "generating_song"
    assert 50 <= state["percent"] <= 75
    assert state["progress_source"] == "provider_generating"


def test_no_product_video_subdub_voice_payos_pricing_db_changes():
    if not _is_music_h14k_scope():
        pytest.skip("Music H14K diff guard is scoped to Music H14K branches only.")
    repo = Path(__file__).resolve().parents[1]
    changed = subprocess.check_output(
        ["git", "-c", f"safe.directory={repo.as_posix()}", "diff", "--name-only", "origin/main"],
        cwd=repo,
        text=True,
    ).splitlines()
    forbidden_prefixes = (
        "providers/video",
        "services/video",
        "services/subdub",
        "services/payos",
        "services/wallet",
        "services/pricing",
        "migrations/",
        "web/",
    )
    forbidden_exact = {
        "local_worker.py",
        "remote_worker.py",
        "providers/key4u_provider.py",
    }
    assert not [
        path
        for path in changed
        if path in forbidden_exact or any(path.startswith(prefix) for prefix in forbidden_prefixes)
    ]
