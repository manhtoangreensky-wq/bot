"""Classification, sync, backup, and online-source aggregation for the vault."""

from __future__ import annotations

import json
import os
import re
import shutil
import zipfile
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from services.knowledge_vault import KnowledgeVault, get_vault, utc_now_text
from services.media_classifier import classify_source, tags_for_text


DEFAULT_SYNC_DIR = Path("workspace") / "knowledge_vault_sync"
DEFAULT_BACKUP_DIR = Path("backups") / "knowledge_vault"


def detect_platform(url: str) -> str:
    host = urlparse(str(url or "").strip()).netloc.lower()
    if "youtube." in host or "youtu.be" in host:
        return "youtube"
    if "tiktok." in host:
        return "tiktok"
    if "instagram." in host:
        return "instagram"
    if "facebook." in host or "fb.watch" in host:
        return "facebook"
    if "pinterest." in host:
        return "pinterest"
    if host:
        return "web"
    return "unknown"


def is_http_url(value: str) -> bool:
    parsed = urlparse(str(value or "").strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _safe_filename(value: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip()).strip(".-")
    return (name or "vault")[:120]


class KnowledgeVaultOps:
    def __init__(self, vault: KnowledgeVault | None = None) -> None:
        self.vault = vault or get_vault()

    def classify_all(self) -> dict[str, Any]:
        payload = self.vault.snapshot()
        updated_sources = 0
        updated_assets = 0
        updated_prompts = 0

        for source in payload.get("knowledge_sources", []):
            path_or_name = source.get("local_path") or source.get("original_name") or source.get("source_url") or ""
            text = f"{source.get('original_name', '')} {source.get('source_url', '')}"
            classification = classify_source(path_or_name, mime_type=source.get("mime_type") or "", extracted_text=text)
            metadata = dict(source.get("metadata_json") or {})
            next_metadata = {
                **metadata,
                "classification": {
                    "asset_type": classification.get("asset_type") or "",
                    "category": classification.get("category") or "",
                    "use_case": classification.get("use_case") or "",
                    "tags": classification.get("tags") or [],
                    "needs_rights_review": bool(classification.get("needs_rights_review")),
                    "classified_at": utc_now_text(),
                },
            }
            if next_metadata != metadata:
                self.vault.update_source(
                    int(source["id"]),
                    status=source.get("status") or "needs_review",
                    metadata_json=next_metadata,
                )
                updated_sources += 1

        for asset in payload.get("media_assets", []):
            haystack = f"{asset.get('title', '')} {asset.get('description', '')} {' '.join(asset.get('tags_json') or [])}"
            tags = sorted(set(asset.get("tags_json") or []) | set(tags_for_text(haystack)))
            if tags != list(asset.get("tags_json") or []):
                self._update_asset_tags(int(asset["id"]), tags)
                updated_assets += 1

        for prompt in payload.get("prompt_library", []):
            tags = sorted(set(prompt.get("style_tags_json") or []) | set(tags_for_text(prompt.get("prompt_text") or "")))
            if tags != list(prompt.get("style_tags_json") or []):
                self.vault.update_prompt(int(prompt["id"]), updated_by="p0_22b_classify", style_tags_json=tags)
                updated_prompts += 1

        return {
            "ok": True,
            "updated_sources": updated_sources,
            "updated_assets": updated_assets,
            "updated_prompts": updated_prompts,
            "classified_at": utc_now_text(),
        }

    def _update_asset_tags(self, asset_id: int, tags: Iterable[str]) -> dict[str, Any] | None:
        def mutation(payload):
            for asset in payload.get("media_assets", []):
                if int(asset.get("id") or 0) == int(asset_id):
                    asset["tags_json"] = sorted({str(tag).strip() for tag in tags if str(tag).strip()})
                    return asset
            return None

        return self.vault._mutate(mutation)

    def sync_index(self, sync_dir: str | Path = DEFAULT_SYNC_DIR) -> dict[str, Any]:
        target = Path(sync_dir).expanduser()
        target.mkdir(parents=True, exist_ok=True)
        admin_index = self.vault.export_index(public=False)
        public_index = self.vault.export_index(public=True)
        prompts_markdown = self.vault.export_prompts("markdown", public_only=False)
        outputs = {
            "admin_index": str(target / admin_index.name),
            "public_index": str(target / public_index.name),
            "prompts_markdown": str(target / prompts_markdown.name),
        }
        shutil.copy2(admin_index, outputs["admin_index"])
        shutil.copy2(public_index, outputs["public_index"])
        shutil.copy2(prompts_markdown, outputs["prompts_markdown"])
        manifest = {
            "ok": True,
            "synced_at": utc_now_text(),
            "source_storage": str(self.vault.storage_dir),
            "outputs": outputs,
            "counts": self.vault.status(include_paths=False),
        }
        manifest_path = target / "sync-manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest["manifest_path"] = str(manifest_path)
        return manifest

    def create_backup(self, backup_dir: str | Path = DEFAULT_BACKUP_DIR, *, include_media: bool = False) -> dict[str, Any]:
        target = Path(backup_dir).expanduser()
        target.mkdir(parents=True, exist_ok=True)
        timestamp = re.sub(r"[^0-9A-Za-z]+", "", utc_now_text())[:14]
        backup_path = target / f"toan-aas-knowledge-vault-{timestamp}.zip"
        with zipfile.ZipFile(backup_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            if self.vault.index_path.exists():
                archive.write(self.vault.index_path, "index.json")
            for export_path in (
                self.vault.export_index(public=False),
                self.vault.export_index(public=True),
                self.vault.export_prompts("json", public_only=False),
            ):
                archive.write(export_path, f"exports/{export_path.name}")
            if include_media:
                for path in self.vault.media_dir.rglob("*"):
                    if path.is_file():
                        archive.write(path, f"media/{path.relative_to(self.vault.media_dir).as_posix()}")
        return {
            "ok": True,
            "backup_path": str(backup_path),
            "include_media": bool(include_media),
            "size_bytes": backup_path.stat().st_size if backup_path.exists() else 0,
            "created_at": utc_now_text(),
        }

    def add_online_source(
        self,
        url: str,
        *,
        title: str = "",
        notes: str = "",
        tags: Iterable[str] = (),
        imported_by_user_id: int | str | None = None,
        rights_status: str = "reference_only",
    ) -> dict[str, Any]:
        clean_url = str(url or "").strip()
        if not is_http_url(clean_url):
            return {"ok": False, "reason": "invalid_url", "url": clean_url}
        platform = detect_platform(clean_url)
        source, duplicate = self.vault.add_source(
            source_type="online_reference",
            original_name=title or clean_url,
            source_url=clean_url,
            source_platform=platform,
            imported_by_user_id=imported_by_user_id,
            status="needs_review",
            rights_status=rights_status,
            metadata={"tags": sorted({str(tag).strip() for tag in tags if str(tag).strip()}), "notes": notes},
        )
        if tags:
            source = self.vault.update_source(source["id"], status="needs_review") or source
        return {
            "ok": True,
            "duplicate": duplicate,
            "source": source,
            "platform": platform,
            "fetch_performed": False,
            "needs_review": True,
        }

    def import_online_sources(
        self,
        values: Iterable[str],
        *,
        imported_by_user_id: int | str | None = None,
        rights_status: str = "reference_only",
    ) -> dict[str, Any]:
        results = [
            self.add_online_source(value, imported_by_user_id=imported_by_user_id, rights_status=rights_status)
            for value in values
            if str(value or "").strip()
        ]
        return {
            "ok": True,
            "submitted": len(results),
            "imported": sum(1 for item in results if item.get("ok") and not item.get("duplicate")),
            "duplicates": sum(1 for item in results if item.get("duplicate")),
            "failed": sum(1 for item in results if not item.get("ok")),
            "fetch_performed": False,
            "results": results,
        }

    def import_online_sources_file(
        self,
        path: str | Path,
        *,
        imported_by_user_id: int | str | None = None,
        rights_status: str = "reference_only",
    ) -> dict[str, Any]:
        source = Path(path).expanduser()
        if not source.is_file():
            return {"ok": False, "reason": "local_path_unavailable", "path": str(source)}
        lines = [
            line.strip()
            for line in source.read_text(encoding="utf-8", errors="replace").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        return self.import_online_sources(lines, imported_by_user_id=imported_by_user_id, rights_status=rights_status)


def get_ops(vault: KnowledgeVault | None = None) -> KnowledgeVaultOps:
    return KnowledgeVaultOps(vault)
