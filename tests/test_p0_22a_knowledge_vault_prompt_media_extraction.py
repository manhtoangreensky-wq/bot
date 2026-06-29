from __future__ import annotations

import sys
from pathlib import Path

from services.knowledge_vault import KnowledgeVault
from services.prompt_extractor import extract_prompt
from services.vault_importer import MediaMetadata, VaultImporter


class FakeExtractorImporter(VaultImporter):
    @property
    def ffmpeg_available(self) -> bool:
        return True

    @property
    def ffprobe_available(self) -> bool:
        return True

    def probe_media(self, path: str | Path) -> MediaMetadata:
        name = Path(path).name.lower()
        if name.endswith((".mp4", ".mov", ".mkv", ".webm")):
            return MediaMetadata(duration_sec=42, width=1080, height=1920, ratio="9:16", audio_streams=1)
        return MediaMetadata()

    def create_thumbnail(self, source: str | Path, source_id: int, duration_sec: float = 0) -> Path:
        output = self.vault.preview_dir / f"source-{source_id}-thumbnail.jpg"
        output.write_bytes(b"thumbnail")
        return output

    def create_keyframes(self, source: str | Path, source_id: int, duration_sec: float = 0) -> list[tuple[Path, float]]:
        frames: list[tuple[Path, float]] = []
        for index, timestamp in enumerate((0.0, 10.0, 20.0, 30.0), start=1):
            output = self.vault.keyframe_dir / f"source-{source_id}-frame-{index:02d}.jpg"
            output.write_bytes(f"frame-{index}".encode("utf-8"))
            frames.append((output, timestamp))
        return frames

    def extract_audio(self, source: str | Path, source_id: int) -> Path:
        output = self.vault.audio_dir / f"source-{source_id}-audio.m4a"
        output.write_bytes(b"audio")
        return output


def _vault(tmp_path: Path) -> KnowledgeVault:
    return KnowledgeVault(tmp_path / "vault")


def _sample_video(tmp_path: Path, name: str = "affiliate-demo.mp4", data: bytes = b"video-reference") -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


def _sample_text(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_vault_import_video_creates_source_record(tmp_path: Path):
    vault = _vault(tmp_path)
    result = FakeExtractorImporter(vault).import_file(_sample_video(tmp_path), imported_by_user_id=11)

    assert result["ok"] is True
    assert result["source"]["source_type"] == "admin_import"
    assert result["source"]["original_name"] == "affiliate-demo.mp4"
    assert vault.status()["sources"] == 1


def test_vault_import_video_extracts_metadata(tmp_path: Path):
    result = FakeExtractorImporter(_vault(tmp_path)).import_file(_sample_video(tmp_path))

    source = result["source"]
    assert source["duration_sec"] == 42
    assert source["width"] == 1080
    assert source["height"] == 1920
    assert source["ratio"] == "9:16"
    assert source["audio_streams"] == 1


def test_vault_import_video_creates_thumbnail(tmp_path: Path):
    result = FakeExtractorImporter(_vault(tmp_path)).import_file(_sample_video(tmp_path))

    thumbnails = [asset for asset in result["assets"] if asset["asset_type"] == "thumbnail"]
    assert len(thumbnails) == 1
    assert Path(thumbnails[0]["local_path"]).is_file()


def test_vault_import_video_creates_keyframes(tmp_path: Path):
    result = FakeExtractorImporter(_vault(tmp_path)).import_file(_sample_video(tmp_path))

    keyframes = [asset for asset in result["assets"] if asset["asset_type"] == "keyframe"]
    assert len(keyframes) == 4
    assert all(Path(asset["local_path"]).is_file() for asset in keyframes)


def test_vault_import_video_extracts_audio_track_when_present(tmp_path: Path):
    result = FakeExtractorImporter(_vault(tmp_path)).import_file(_sample_video(tmp_path))

    audio_assets = [asset for asset in result["assets"] if asset["asset_type"] == "audio"]
    assert len(audio_assets) == 1
    assert Path(audio_assets[0]["local_path"]).is_file()


def test_vault_import_folder_skips_duplicates_by_checksum(tmp_path: Path):
    folder = tmp_path / "refs"
    folder.mkdir()
    (folder / "one.mp4").write_bytes(b"same")
    (folder / "two.mp4").write_bytes(b"same")

    summary = FakeExtractorImporter(_vault(tmp_path)).import_folder(folder)

    assert summary["imported"] == 1
    assert summary["duplicates"] == 1


def test_vault_import_folder_respects_file_limit(tmp_path: Path):
    folder = tmp_path / "refs"
    folder.mkdir()
    for index in range(3):
        (folder / f"ref-{index}.mp4").write_bytes(f"video-{index}".encode("utf-8"))

    summary = FakeExtractorImporter(_vault(tmp_path)).import_folder(folder, max_files=2)

    assert summary["scanned"] == 2
    assert summary["imported"] == 2


def test_vault_local_d_drive_missing_does_not_crash(tmp_path: Path):
    missing = tmp_path / "does-not-exist"
    summary = FakeExtractorImporter(_vault(tmp_path)).scan_folder(missing)

    assert summary["ok"] is False
    assert summary["reason"] == "local_path_unavailable"


def test_prompt_parser_classifies_video_prompt():
    candidate = extract_prompt("Video prompt: create a 9:16 product demo with camera movement for 12s")

    assert candidate
    assert candidate.prompt_type == "video"
    assert candidate.ratio_hint == "9:16"
    assert candidate.duration_hint == "12s"


def test_prompt_parser_classifies_image_prompt():
    candidate = extract_prompt("Image prompt: create an image of a premium skincare bottle, cinematic light")

    assert candidate
    assert candidate.prompt_type == "image"


def test_prompt_parser_classifies_music_prompt():
    candidate = extract_prompt("Music prompt: compose a song, upbeat instrumental, 120 bpm for product launch")

    assert candidate
    assert candidate.prompt_type == "music"


def test_prompt_parser_classifies_storyboard_prompt():
    candidate = extract_prompt("Storyboard: Scene 1 close-up product, Scene 2 customer reaction")

    assert candidate
    assert candidate.prompt_type == "storyboard"
    assert candidate.scene_count == 2


def test_prompt_saved_to_prompt_library_as_draft(tmp_path: Path):
    vault = _vault(tmp_path)
    source = _sample_text(
        tmp_path,
        "prompt.txt",
        "Video prompt: create a 9:16 affiliate short video with product close-up and CTA",
    )

    result = FakeExtractorImporter(vault).import_file(source)

    assert result["prompts_draft"] == 1
    prompt = vault.snapshot()["prompt_library"][0]
    assert prompt["status"] == "draft"
    assert prompt["prompt_type"] == "video"


def test_media_saved_to_correct_asset_library(tmp_path: Path):
    result = FakeExtractorImporter(_vault(tmp_path)).import_file(_sample_video(tmp_path))

    assert result["assets"][0]["asset_type"] == "video"


def test_music_audio_saved_to_music_or_audio_vault(tmp_path: Path):
    audio = tmp_path / "launch-music.mp3"
    audio.write_bytes(b"audio")

    result = FakeExtractorImporter(_vault(tmp_path)).import_file(audio)

    assert result["assets"][0]["asset_type"] in {"music", "sfx", "voice"}


def test_keyframes_saved_to_image_vault(tmp_path: Path):
    result = FakeExtractorImporter(_vault(tmp_path)).import_file(_sample_video(tmp_path))

    assert any(asset["asset_type"] == "keyframe" for asset in result["assets"])


def test_admin_review_approves_prompt_to_public_library(tmp_path: Path):
    vault = _vault(tmp_path)
    source = _sample_text(tmp_path, "prompt.txt", "Image prompt: create an image of a bold tech poster")
    FakeExtractorImporter(vault).import_file(source)

    approved = vault.approve_prompt(1, approved_by=99)

    assert approved["status"] == "approved"
    assert vault.search_prompt("tech", public_only=True)[0]["id"] == 1


def test_unreviewed_reference_not_public(tmp_path: Path):
    vault = _vault(tmp_path)
    source = _sample_text(tmp_path, "prompt.txt", "Image prompt: create an image of a bold tech poster")
    FakeExtractorImporter(vault).import_file(source, rights_status="reference_only")

    assert vault.search_prompt("tech", public_only=True) == []


def test_rights_status_defaults_reference_only_for_imported_reference(tmp_path: Path):
    result = FakeExtractorImporter(_vault(tmp_path)).import_file(_sample_video(tmp_path))

    assert result["source"]["rights_status"] == "reference_only"
    assert result["needs_review"] is True


def test_search_prompt_by_tag(tmp_path: Path):
    vault = _vault(tmp_path)
    source = _sample_text(tmp_path, "prompt.txt", "Video prompt: create a TikTok reels product ad with cinematic light")
    FakeExtractorImporter(vault).import_file(source)
    vault.approve_prompt(1, approved_by=99)

    matches = vault.search_prompt(tags=["tiktok_reels"], public_only=True)

    assert len(matches) == 1
    assert matches[0]["id"] == 1


def test_use_prompt_button_returns_clean_prompt(tmp_path: Path):
    vault = _vault(tmp_path)
    source = _sample_text(tmp_path, "prompt.txt", "Prompt: create a video ad with hand product demo, 9:16")
    FakeExtractorImporter(vault).import_file(source)
    vault.approve_prompt(1, approved_by=99)

    prompt = vault.get_prompt(1, public=True)

    assert prompt["prompt_text"] == "create a video ad with hand product demo, 9:16"
    assert "source_original_text" not in prompt
    assert "normalized_prompt_text" not in prompt


def test_use_prompt_button_exists_in_bot_keyboard():
    bot_module = sys.modules["bot"]
    labels = [button.text for row in bot_module.vault_prompt_keyboard(1).inline_keyboard for button in row]

    assert "Dùng prompt này" in labels


def test_vault_admin_menu_has_expected_libraries():
    bot_module = sys.modules["bot"]
    labels = [button.text for row in bot_module.vault_admin_keyboard().inline_keyboard for button in row]

    assert "🧠 Kho học liệu" in labels
    assert "📥 Import học liệu" in labels
    assert "📚 Kho Prompt" in labels
    assert "🎬 Kho Video" in labels
    assert "🖼 Kho Ảnh" in labels
    assert "🎵 Kho Nhạc/SFX" in labels
    assert "🧾 Nháp cần duyệt" in labels
    assert "🔎 Tìm kiếm kho" in labels


def test_bot_registers_p0_22a_vault_commands_and_callback():
    source = Path("bot.py").read_text(encoding="utf-8")

    for command in (
        "vault_status",
        "vault_import_folder",
        "vault_scan_folder",
        "vault_import_video_refs",
        "vault_import_file",
        "vault_job_debug",
        "vault_source_debug",
        "vault_prompt_debug",
        "vault_export_prompts",
        "vault_export_index",
        "vault_review",
        "kho_prompt",
    ):
        assert f'CommandHandler("{command}"' in source
    assert "CallbackQueryHandler(handle_knowledge_vault_callback" in source
    assert 'pattern=r"^vault\\|"' in source


def test_export_prompts_markdown_json_txt(tmp_path: Path):
    vault = _vault(tmp_path)
    source = _sample_text(tmp_path, "prompt.txt", "Video prompt: create a product ads short with CTA")
    FakeExtractorImporter(vault).import_file(source)

    markdown = vault.export_prompts("markdown", public_only=False)
    json_path = vault.export_prompts("json", public_only=False)
    txt_path = vault.export_prompts("txt", public_only=False)

    assert markdown.suffix == ".md" and markdown.is_file()
    assert json_path.suffix == ".json" and json_path.is_file()
    assert txt_path.suffix == ".txt" and txt_path.is_file()


def test_public_ui_hides_local_paths(tmp_path: Path):
    vault = _vault(tmp_path)
    result = FakeExtractorImporter(vault).import_file(_sample_video(tmp_path), rights_status="own")
    vault.approve_asset(result["assets"][0]["id"], approved_by=99)

    public_assets = vault.list_assets(asset_type="video", public_only=True)

    assert len(public_assets) == 1
    assert "local_path" not in public_assets[0]
    assert "preview_path" not in public_assets[0]


def test_admin_debug_shows_import_status(tmp_path: Path):
    vault = _vault(tmp_path)
    importer = FakeExtractorImporter(vault)
    importer.import_file(_sample_video(tmp_path))

    status = importer.debug_status()

    assert status["sources"] == 1
    assert "storage_path" in status
    assert status["ffmpeg_available"] is True
    assert status["ffprobe_available"] is True


def test_no_engine_touched():
    service_files = [
        Path("services/knowledge_vault.py"),
        Path("services/prompt_extractor.py"),
        Path("services/media_classifier.py"),
        Path("services/vault_importer.py"),
    ]
    source = "\n".join(path.read_text(encoding="utf-8").lower() for path in service_files)

    assert "payos" not in source
    assert "wallet" not in source
    assert "/naptien" not in source
    assert "video_product_system" not in source
    assert "subtitle_dub" not in source
