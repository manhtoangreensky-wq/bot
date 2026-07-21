from __future__ import annotations

import json
import zipfile
from pathlib import Path

from services.knowledge_vault import KnowledgeVault
from services.knowledge_vault_sync import KnowledgeVaultOps, detect_platform


def _vault(tmp_path: Path) -> KnowledgeVault:
    return KnowledgeVault(tmp_path / "vault")


def test_classify_all_enriches_prompt_tags(tmp_path: Path):
    vault = _vault(tmp_path)
    source, _ = vault.add_source(source_type="manual", original_name="prompt.txt", rights_status="own")
    prompt, _ = vault.add_prompt(
        source_id=source["id"],
        prompt_text="Video prompt: create a TikTok reels product ad with cinematic camera movement",
        prompt_type="video",
    )

    result = KnowledgeVaultOps(vault).classify_all()
    updated = vault.get_prompt(prompt["id"])

    assert result["ok"] is True
    assert result["updated_prompts"] == 1
    assert "tiktok_reels" in updated["style_tags_json"]
    assert "product_ads" in updated["style_tags_json"]


def test_classify_all_enriches_asset_tags(tmp_path: Path):
    vault = _vault(tmp_path)
    source, _ = vault.add_source(source_type="manual", original_name="video.mp4", rights_status="own")
    asset = vault.add_asset(
        source_id=source["id"],
        asset_type="video",
        title="Cinematic affiliate product ad reference",
        rights_status="own",
    )

    result = KnowledgeVaultOps(vault).classify_all()
    updated = next(item for item in vault.snapshot()["media_assets"] if item["id"] == asset["id"])

    assert result["updated_assets"] == 1
    assert "affiliate" in updated["tags_json"]
    assert "product_ads" in updated["tags_json"]


def test_classify_all_stores_source_classification_metadata(tmp_path: Path):
    vault = _vault(tmp_path)
    source, _ = vault.add_source(source_type="manual", original_name="tiktok-product-reference.mp4", rights_status="own")

    result = KnowledgeVaultOps(vault).classify_all()
    updated = vault.get_source(source["id"])

    assert result["updated_sources"] == 1
    assert updated["metadata_json"]["classification"]["asset_type"] == "video"
    assert "tiktok_reels" in updated["metadata_json"]["classification"]["tags"]


def test_sync_index_writes_manifest_and_exports(tmp_path: Path):
    vault = _vault(tmp_path)
    sync_dir = tmp_path / "sync"
    source, _ = vault.add_source(source_type="manual", original_name="prompt.txt", rights_status="own")
    vault.add_prompt(source_id=source["id"], prompt_text="Image prompt: create an image for a tech poster", prompt_type="image")

    result = KnowledgeVaultOps(vault).sync_index(sync_dir)

    assert result["ok"] is True
    assert Path(result["manifest_path"]).is_file()
    assert Path(result["outputs"]["admin_index"]).is_file()
    assert Path(result["outputs"]["public_index"]).is_file()
    assert Path(result["outputs"]["prompts_markdown"]).is_file()


def test_sync_manifest_has_counts(tmp_path: Path):
    vault = _vault(tmp_path)
    source, _ = vault.add_source(source_type="manual", original_name="prompt.txt", rights_status="own")
    vault.add_prompt(source_id=source["id"], prompt_text="Music prompt: compose a short brand jingle", prompt_type="music")

    result = KnowledgeVaultOps(vault).sync_index(tmp_path / "sync")
    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))

    assert manifest["counts"]["sources"] == 1
    assert manifest["counts"]["prompts"] == 1


def test_backup_creates_zip_with_index_and_exports(tmp_path: Path):
    vault = _vault(tmp_path)
    source, _ = vault.add_source(source_type="manual", original_name="prompt.txt", rights_status="own")
    vault.add_prompt(source_id=source["id"], prompt_text="Workflow: Step 1 collect refs, Step 2 create storyboard", prompt_type="workflow")

    result = KnowledgeVaultOps(vault).create_backup(tmp_path / "backups")

    assert result["ok"] is True
    with zipfile.ZipFile(result["backup_path"]) as archive:
        names = set(archive.namelist())
    assert "index.json" in names
    assert "exports/toan-aas-vault-index.json" in names
    assert "exports/toan-aas-prompts.json" in names


def test_online_source_platform_detection():
    assert detect_platform("https://www.youtube.com/watch?v=abc") == "youtube"
    assert detect_platform("https://www.tiktok.com/@toan/video/1") == "tiktok"
    assert detect_platform("https://example.com/ref") == "web"


def test_add_online_source_stores_reference_only_and_needs_review(tmp_path: Path):
    vault = _vault(tmp_path)

    result = KnowledgeVaultOps(vault).add_online_source("https://www.youtube.com/watch?v=abc", title="YouTube ref")

    assert result["ok"] is True
    assert result["fetch_performed"] is False
    assert result["source"]["source_type"] == "online_reference"
    assert result["source"]["source_platform"] == "youtube"
    assert result["source"]["rights_status"] == "reference_only"
    assert result["source"]["status"] == "needs_review"


def test_add_online_source_dedupes_by_url(tmp_path: Path):
    ops = KnowledgeVaultOps(_vault(tmp_path))
    first = ops.add_online_source("https://example.com/ref")
    second = ops.add_online_source("https://example.com/ref")

    assert first["duplicate"] is False
    assert second["duplicate"] is True


def test_import_online_sources_batch_does_not_fetch_network(tmp_path: Path):
    result = KnowledgeVaultOps(_vault(tmp_path)).import_online_sources(
        ["https://example.com/a", "https://example.com/b", "not-a-url"]
    )

    assert result["submitted"] == 3
    assert result["imported"] == 2
    assert result["failed"] == 1
    assert result["fetch_performed"] is False


def test_import_online_sources_file(tmp_path: Path):
    source_file = tmp_path / "urls.txt"
    source_file.write_text("# refs\nhttps://example.com/a\nhttps://www.instagram.com/reel/1\n", encoding="utf-8")

    result = KnowledgeVaultOps(_vault(tmp_path)).import_online_sources_file(source_file)

    assert result["imported"] == 2
    assert result["failed"] == 0


def test_public_index_hides_admin_source_url(tmp_path: Path):
    vault = _vault(tmp_path)
    ops = KnowledgeVaultOps(vault)
    ops.add_online_source("https://example.com/private-ref")

    public_index = vault.export_index(public=True)
    payload = json.loads(public_index.read_text(encoding="utf-8"))

    assert payload["knowledge_sources"] == []
    assert "private-ref" not in public_index.read_text(encoding="utf-8")


def test_bot_registers_p0_22b_vault_commands():
    source = Path("bot.py").read_text(encoding="utf-8")

    for command in (
        "vault_classify_all",
        "vault_sync_index",
        "vault_backup",
        "vault_add_online_source",
        "vault_import_online_sources",
    ):
        assert f'CommandHandler("{command}"' in source


def test_no_forbidden_runtime_touched_by_p0_22b():
    service_source = Path("services/knowledge_vault_sync.py").read_text(encoding="utf-8").lower()

    assert "payos" not in service_source
    assert "wallet" not in service_source
    assert "video_product_system" not in service_source
    assert "subtitle_dub" not in service_source
    assert "suno" not in service_source
