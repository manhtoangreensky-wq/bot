"""JSON-backed TOAN AAS Knowledge Vault.

The repository is intentionally isolated from billing and production-job tables.
It can later be replaced by a database adapter without changing callers.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from services.media_classifier import normalize_text


INDEX_VERSION = 1
PUBLIC_RIGHTS = {"own", "licensed"}
RIGHTS_STATUSES = {"own", "licensed", "reference_only", "unknown", "do_not_use_public"}
PROMPT_STATUSES = {"draft", "reviewed", "approved", "archived"}
SOURCE_STATUSES = {"pending", "processing", "extracted", "needs_review", "reviewed", "failed"}
ASSET_TYPES = {"video", "image", "audio", "music", "sfx", "voice", "thumbnail", "keyframe", "document"}


def utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def default_storage_dir() -> Path:
    configured = os.getenv("TOAN_AAS_VAULT_STORAGE_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path(__file__).resolve().parents[1] / "workspace" / "knowledge_vault"


def _empty_index() -> dict[str, Any]:
    return {
        "version": INDEX_VERSION,
        "sequences": {
            "source": 0,
            "asset": 0,
            "prompt": 0,
            "workflow": 0,
            "collection": 0,
            "job": 0,
        },
        "knowledge_sources": [],
        "media_assets": [],
        "prompt_library": [],
        "workflow_templates": [],
        "knowledge_collections": [],
        "extraction_jobs": [],
        "last_import": {},
    }


def sha256_file(path: str | Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


class KnowledgeVault:
    def __init__(self, storage_dir: str | Path | None = None) -> None:
        self.storage_dir = Path(storage_dir or default_storage_dir()).expanduser().resolve()
        self.index_path = self.storage_dir / "index.json"
        self.media_dir = self.storage_dir / "media"
        self.preview_dir = self.storage_dir / "previews"
        self.keyframe_dir = self.storage_dir / "keyframes"
        self.audio_dir = self.storage_dir / "audio"
        self.export_dir = self.storage_dir / "exports"
        self._lock = threading.RLock()
        for path in (
            self.storage_dir,
            self.media_dir,
            self.preview_dir,
            self.keyframe_dir,
            self.audio_dir,
            self.export_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)
        if not self.index_path.exists():
            self._write(_empty_index())

    def _read(self) -> dict[str, Any]:
        with self._lock:
            try:
                payload = json.loads(self.index_path.read_text(encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError):
                payload = _empty_index()
            baseline = _empty_index()
            for key, value in baseline.items():
                payload.setdefault(key, deepcopy(value))
            for key, value in baseline["sequences"].items():
                payload["sequences"].setdefault(key, value)
            return payload

    def _write(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(
                prefix="vault-index-",
                suffix=".json",
                dir=str(self.storage_dir),
            )
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle, ensure_ascii=False, indent=2, default=str)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary_name, self.index_path)
            finally:
                if os.path.exists(temporary_name):
                    os.unlink(temporary_name)

    def _mutate(self, callback):
        with self._lock:
            payload = self._read()
            result = callback(payload)
            self._write(payload)
            return deepcopy(result)

    @staticmethod
    def _next_id(payload: dict[str, Any], kind: str) -> int:
        payload["sequences"][kind] = int(payload["sequences"].get(kind) or 0) + 1
        return payload["sequences"][kind]

    @staticmethod
    def _record(records: list[dict[str, Any]], record_id: int) -> dict[str, Any] | None:
        return next((item for item in records if int(item.get("id") or 0) == int(record_id)), None)

    def snapshot(self) -> dict[str, Any]:
        return deepcopy(self._read())

    def add_collection(
        self,
        name: str,
        *,
        description: str = "",
        category: str = "",
        folder_path: str = "",
        tags: Iterable[str] = (),
        created_by: int | str | None = None,
    ) -> dict[str, Any]:
        def mutation(payload):
            record = {
                "id": self._next_id(payload, "collection"),
                "name": str(name or "Untitled collection").strip()[:240],
                "description": str(description or "").strip()[:2000],
                "category": str(category or "").strip()[:80],
                "folder_path": str(folder_path or "").strip()[:1200],
                "tags_json": sorted({str(tag).strip() for tag in tags if str(tag).strip()}),
                "created_by": str(created_by or ""),
                "created_at": utc_now_text(),
            }
            payload["knowledge_collections"].append(record)
            return record

        return self._mutate(mutation)

    def add_source(
        self,
        *,
        source_type: str,
        original_name: str,
        local_path: str = "",
        source_url: str = "",
        source_platform: str = "",
        file_id: str = "",
        mime_type: str = "",
        size_bytes: int = 0,
        checksum_sha256: str = "",
        source_collection_id: int | None = None,
        imported_by_user_id: int | str | None = None,
        status: str = "pending",
        rights_status: str = "reference_only",
        metadata: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], bool]:
        checksum = str(checksum_sha256 or "").lower().strip()
        if rights_status not in RIGHTS_STATUSES:
            rights_status = "reference_only"
        if status not in SOURCE_STATUSES:
            status = "pending"

        def mutation(payload):
            duplicate = next(
                (
                    item
                    for item in payload["knowledge_sources"]
                    if (checksum and item.get("checksum_sha256") == checksum)
                    or (source_url and item.get("source_url") == source_url)
                ),
                None,
            )
            if duplicate:
                return duplicate, True
            source_id = self._next_id(payload, "source")
            values = dict(metadata or {})
            record = {
                "id": source_id,
                "source_type": str(source_type or "admin_import")[:40],
                "original_name": str(original_name or f"source-{source_id}")[:500],
                "local_path": str(local_path or "")[:2000],
                "source_url": str(source_url or "")[:2000],
                "source_platform": str(source_platform or "")[:80],
                "file_id": str(file_id or "")[:500],
                "mime_type": str(mime_type or "")[:160],
                "size_bytes": max(0, int(size_bytes or 0)),
                "duration_sec": float(values.get("duration_sec") or 0),
                "width": int(values.get("width") or 0),
                "height": int(values.get("height") or 0),
                "ratio": str(values.get("ratio") or ""),
                "audio_streams": int(values.get("audio_streams") or 0),
                "checksum_sha256": checksum,
                "source_collection_id": source_collection_id,
                "imported_by_user_id": str(imported_by_user_id or ""),
                "imported_at": utc_now_text(),
                "status": status,
                "rights_status": rights_status,
                "error_code": "",
                "error_message_admin": "",
                "metadata_json": dict(values),
            }
            payload["knowledge_sources"].append(record)
            return record, False

        return self._mutate(mutation)

    def update_source(self, source_id: int, **changes: Any) -> dict[str, Any] | None:
        allowed = {
            "local_path",
            "source_url",
            "source_platform",
            "duration_sec",
            "width",
            "height",
            "ratio",
            "audio_streams",
            "status",
            "error_code",
            "error_message_admin",
            "source_collection_id",
            "metadata_json",
        }

        def mutation(payload):
            record = self._record(payload["knowledge_sources"], source_id)
            if not record:
                return None
            for key, value in changes.items():
                if key in allowed:
                    record[key] = value
            return record

        return self._mutate(mutation)

    def get_source(self, source_id: int, *, public: bool = False) -> dict[str, Any] | None:
        record = self._record(self._read()["knowledge_sources"], source_id)
        if not record:
            return None
        result = deepcopy(record)
        if public:
            for key in ("local_path", "source_url", "file_id", "error_code", "error_message_admin", "checksum_sha256", "metadata_json"):
                result.pop(key, None)
        return result

    def add_asset(
        self,
        *,
        source_id: int,
        asset_type: str,
        title: str,
        local_path: str = "",
        preview_path: str = "",
        description: str = "",
        duration_sec: float = 0,
        width: int = 0,
        height: int = 0,
        ratio: str = "",
        tags: Iterable[str] = (),
        category: str = "",
        mood: str = "",
        style: str = "",
        use_case: str = "",
        rights_status: str = "reference_only",
        visibility: str = "admin_only",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if asset_type not in ASSET_TYPES:
            asset_type = "document"
        if rights_status not in RIGHTS_STATUSES:
            rights_status = "reference_only"
        if visibility not in {"admin_only", "public_library", "private"}:
            visibility = "admin_only"
        if visibility == "public_library" and rights_status not in PUBLIC_RIGHTS:
            visibility = "admin_only"

        def mutation(payload):
            asset_id = self._next_id(payload, "asset")
            record = {
                "id": asset_id,
                "source_id": int(source_id),
                "asset_type": asset_type,
                "title": str(title or f"{asset_type}-{asset_id}")[:500],
                "description": str(description or "")[:4000],
                "local_path": str(local_path or "")[:2000],
                "preview_path": str(preview_path or "")[:2000],
                "duration_sec": float(duration_sec or 0),
                "width": int(width or 0),
                "height": int(height or 0),
                "ratio": str(ratio or ""),
                "tags_json": sorted({str(tag).strip() for tag in tags if str(tag).strip()}),
                "category": str(category or "")[:120],
                "mood": str(mood or "")[:120],
                "style": str(style or "")[:240],
                "use_case": str(use_case or "")[:120],
                "rights_status": rights_status,
                "visibility": visibility,
                "approved_by": "",
                "approved_at": "",
                "created_at": utc_now_text(),
                "metadata_json": dict(metadata or {}),
            }
            payload["media_assets"].append(record)
            return record

        return self._mutate(mutation)

    def approve_asset(self, asset_id: int, approved_by: int | str) -> dict[str, Any] | None:
        def mutation(payload):
            record = self._record(payload["media_assets"], asset_id)
            if not record:
                return None
            record["approved_by"] = str(approved_by or "")
            record["approved_at"] = utc_now_text()
            record["visibility"] = (
                "public_library" if record.get("rights_status") in PUBLIC_RIGHTS else "admin_only"
            )
            return record

        return self._mutate(mutation)

    def add_prompt(
        self,
        *,
        source_id: int,
        prompt_text: str,
        prompt_type: str,
        asset_id: int | None = None,
        title: str = "",
        negative_prompt: str = "",
        language: str = "",
        model_hint: str = "generic",
        ratio_hint: str = "",
        duration_hint: str = "",
        style_tags: Iterable[str] = (),
        scene_count: int = 0,
        category: str = "",
        use_case: str = "",
        quality_score: float = 0,
        source_confidence: float = 0,
        created_by: int | str | None = None,
        source_original_text: str = "",
        cleaned_prompt_text: str = "",
    ) -> tuple[dict[str, Any], bool]:
        clean = re.sub(r"\s+", " ", str(cleaned_prompt_text or prompt_text or "")).strip()
        normalized = normalize_text(clean)
        if not normalized:
            raise ValueError("empty_prompt")

        def mutation(payload):
            duplicate = next(
                (
                    item
                    for item in payload["prompt_library"]
                    if item.get("normalized_prompt_text") == normalized
                ),
                None,
            )
            if duplicate:
                return duplicate, True
            prompt_id = self._next_id(payload, "prompt")
            record = {
                "id": prompt_id,
                "source_id": int(source_id),
                "asset_id": asset_id,
                "prompt_type": str(prompt_type or "caption")[:40],
                "title": str(title or clean[:80] or f"Prompt {prompt_id}")[:500],
                "prompt_text": clean[:12000],
                "negative_prompt": str(negative_prompt or "")[:4000],
                "language": str(language or "")[:20],
                "model_hint": str(model_hint or "generic")[:80],
                "ratio_hint": str(ratio_hint or "")[:20],
                "duration_hint": str(duration_hint or "")[:40],
                "style_tags_json": sorted({str(tag).strip() for tag in style_tags if str(tag).strip()}),
                "scene_count": max(0, int(scene_count or 0)),
                "category": str(category or "")[:120],
                "use_case": str(use_case or "")[:120],
                "quality_score": float(quality_score or 0),
                "source_confidence": float(source_confidence or 0),
                "status": "draft",
                "version": 1,
                "version_history": [],
                "source_original_text": str(source_original_text or prompt_text or "")[:20000],
                "cleaned_prompt_text": clean[:12000],
                "normalized_prompt_text": normalized,
                "created_by": str(created_by or ""),
                "approved_by": "",
                "created_at": utc_now_text(),
                "updated_at": utc_now_text(),
            }
            payload["prompt_library"].append(record)
            return record, False

        return self._mutate(mutation)

    def update_prompt(self, prompt_id: int, *, updated_by: int | str = "", **changes: Any) -> dict[str, Any] | None:
        allowed = {
            "title",
            "prompt_text",
            "negative_prompt",
            "language",
            "model_hint",
            "ratio_hint",
            "duration_hint",
            "style_tags_json",
            "scene_count",
            "category",
            "use_case",
            "status",
        }

        def mutation(payload):
            record = self._record(payload["prompt_library"], prompt_id)
            if not record:
                return None
            record["version_history"].append(
                {
                    "version": record.get("version", 1),
                    "prompt_text": record.get("prompt_text", ""),
                    "updated_at": record.get("updated_at", ""),
                    "updated_by": str(updated_by or ""),
                }
            )
            for key, value in changes.items():
                if key in allowed:
                    record[key] = value
            record["prompt_text"] = re.sub(r"\s+", " ", str(record.get("prompt_text") or "")).strip()[:12000]
            record["cleaned_prompt_text"] = record["prompt_text"]
            record["normalized_prompt_text"] = normalize_text(record["prompt_text"])
            record["version"] = int(record.get("version") or 1) + 1
            record["updated_at"] = utc_now_text()
            return record

        return self._mutate(mutation)

    def approve_prompt(self, prompt_id: int, approved_by: int | str) -> dict[str, Any] | None:
        def mutation(payload):
            record = self._record(payload["prompt_library"], prompt_id)
            if not record:
                return None
            record["status"] = "approved"
            record["approved_by"] = str(approved_by or "")
            record["approved_at"] = utc_now_text()
            record["updated_at"] = utc_now_text()
            return record

        return self._mutate(mutation)

    def get_prompt(self, prompt_id: int, *, public: bool = False) -> dict[str, Any] | None:
        record = self._record(self._read()["prompt_library"], prompt_id)
        if not record or (public and record.get("status") != "approved"):
            return None
        result = deepcopy(record)
        if public:
            for key in (
                "source_original_text",
                "normalized_prompt_text",
                "version_history",
                "created_by",
                "approved_by",
                "source_confidence",
            ):
                result.pop(key, None)
        return result

    def search_prompt(
        self,
        query: str = "",
        category: str = "",
        tags: Iterable[str] = (),
        *,
        public_only: bool = True,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        wanted = normalize_text(query)
        category = normalize_text(category)
        wanted_tags = {normalize_text(tag) for tag in tags if normalize_text(tag)}
        results = []
        for prompt in reversed(self._read()["prompt_library"]):
            if public_only and prompt.get("status") != "approved":
                continue
            if category and normalize_text(prompt.get("category", "")) != category:
                continue
            prompt_tags = {normalize_text(tag) for tag in prompt.get("style_tags_json") or []}
            if wanted_tags and not wanted_tags.issubset(prompt_tags):
                continue
            haystack = normalize_text(
                f"{prompt.get('title', '')} {prompt.get('prompt_text', '')} "
                f"{prompt.get('category', '')} {' '.join(prompt.get('style_tags_json') or [])}"
            )
            if wanted and wanted not in haystack:
                continue
            results.append(self.get_prompt(prompt["id"], public=public_only) or deepcopy(prompt))
            if len(results) >= max(1, min(int(limit or 20), 100)):
                break
        return results

    def list_assets(
        self,
        *,
        asset_type: str = "",
        public_only: bool = False,
        use_case: str = "",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        results = []
        for asset in reversed(self._read()["media_assets"]):
            if asset_type and asset.get("asset_type") != asset_type:
                continue
            if use_case and asset.get("use_case") != use_case:
                continue
            if public_only and not (
                asset.get("visibility") == "public_library"
                and asset.get("rights_status") in PUBLIC_RIGHTS
                and asset.get("approved_at")
            ):
                continue
            result = deepcopy(asset)
            if public_only:
                for key in ("local_path", "preview_path", "metadata_json", "approved_by"):
                    result.pop(key, None)
            results.append(result)
            if len(results) >= max(1, min(int(limit or 50), 200)):
                break
        return results

    def add_extraction_job(self, source_id: int, job_type: str, *, status: str = "queued") -> dict[str, Any]:
        def mutation(payload):
            job_id = self._next_id(payload, "job")
            record = {
                "id": job_id,
                "source_id": int(source_id),
                "job_type": str(job_type or "classify")[:80],
                "status": str(status or "queued")[:40],
                "progress": 0,
                "stage": "queued",
                "started_at": "",
                "finished_at": "",
                "result_json": {},
                "error_admin": "",
                "public_safe_error": "",
            }
            payload["extraction_jobs"].append(record)
            return record

        return self._mutate(mutation)

    def update_extraction_job(self, job_id: int, **changes: Any) -> dict[str, Any] | None:
        allowed = {
            "status",
            "progress",
            "stage",
            "started_at",
            "finished_at",
            "result_json",
            "error_admin",
            "public_safe_error",
        }

        def mutation(payload):
            record = self._record(payload["extraction_jobs"], job_id)
            if not record:
                return None
            for key, value in changes.items():
                if key in allowed:
                    record[key] = value
            return record

        return self._mutate(mutation)

    def set_last_import(self, summary: dict[str, Any]) -> dict[str, Any]:
        def mutation(payload):
            payload["last_import"] = {**dict(summary or {}), "updated_at": utc_now_text()}
            return payload["last_import"]

        return self._mutate(mutation)

    def status(self, *, include_paths: bool = False) -> dict[str, Any]:
        payload = self._read()
        result = {
            "sources": len(payload["knowledge_sources"]),
            "assets": len(payload["media_assets"]),
            "prompts": len(payload["prompt_library"]),
            "approved_prompts": sum(1 for item in payload["prompt_library"] if item.get("status") == "approved"),
            "draft_prompts": sum(1 for item in payload["prompt_library"] if item.get("status") == "draft"),
            "collections": len(payload["knowledge_collections"]),
            "jobs": len(payload["extraction_jobs"]),
            "queue_pending": sum(
                1 for item in payload["extraction_jobs"] if item.get("status") in {"queued", "processing"}
            ),
            "last_import": deepcopy(payload.get("last_import") or {}),
        }
        if include_paths:
            result["storage_path"] = str(self.storage_dir)
        return result

    def export_prompts(self, export_format: str = "markdown", *, public_only: bool = False) -> Path:
        export_format = str(export_format or "markdown").lower().strip()
        extension = {"markdown": "md", "md": "md", "json": "json", "txt": "txt"}.get(export_format)
        if not extension:
            raise ValueError("unsupported_export_format")
        prompts = self.search_prompt(public_only=public_only, limit=10000)
        output_path = self.export_dir / f"toan-aas-prompts.{extension}"
        if extension == "json":
            content = json.dumps(prompts, ensure_ascii=False, indent=2)
        elif extension == "txt":
            content = "\n\n".join(item.get("prompt_text", "") for item in prompts).strip() + "\n"
        else:
            blocks = ["# TOAN AAS Prompt Vault", ""]
            for prompt in prompts:
                blocks.extend(
                    [
                        f"## {prompt.get('title') or 'Untitled prompt'}",
                        "",
                        f"- Type: {prompt.get('prompt_type') or 'caption'}",
                        f"- Category: {prompt.get('category') or 'reference'}",
                        f"- Tags: {', '.join(prompt.get('style_tags_json') or []) or '-'}",
                        "",
                        str(prompt.get("prompt_text") or ""),
                        "",
                    ]
                )
            content = "\n".join(blocks).rstrip() + "\n"
        output_path.write_text(content, encoding="utf-8")
        return output_path

    def export_index(self, *, public: bool = False) -> Path:
        payload = self._read()
        if public:
            payload["knowledge_sources"] = [
                self.get_source(item["id"], public=True)
                for item in payload["knowledge_sources"]
                if item.get("status") == "reviewed"
            ]
            payload["media_assets"] = self.list_assets(public_only=True, limit=10000)
            payload["prompt_library"] = self.search_prompt(public_only=True, limit=10000)
            payload["extraction_jobs"] = []
            payload["last_import"] = {}
        output_path = self.export_dir / ("toan-aas-vault-public.json" if public else "toan-aas-vault-index.json")
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return output_path

    def recommend_prompts_for_video_goal(self, goal: str, *, limit: int = 5) -> list[dict[str, Any]]:
        tags = [tag for tag in ("product_ads", "affiliate", "course", "tutorial") if tag in normalize_text(goal)]
        return self.search_prompt(goal, tags=tags, public_only=True, limit=limit)

    def recommend_assets_for_use_case(self, use_case: str, *, limit: int = 10) -> list[dict[str, Any]]:
        return self.list_assets(public_only=True, use_case=use_case, limit=limit)

    def get_reference_bundle(self, collection_id: int) -> dict[str, Any]:
        payload = self._read()
        collection = self._record(payload["knowledge_collections"], collection_id)
        source_ids = {
            int(item["id"])
            for item in payload["knowledge_sources"]
            if int(item.get("source_collection_id") or 0) == int(collection_id)
        }
        assets = [
            item
            for item in self.list_assets(public_only=True, limit=10000)
            if int(item.get("source_id") or 0) in source_ids
        ]
        prompts = [
            item
            for item in self.search_prompt(public_only=True, limit=10000)
            if int(item.get("source_id") or 0) in source_ids
        ]
        return {"collection": deepcopy(collection), "assets": assets, "prompts": prompts}

    def create_prompt_pack_from_sources(self, source_ids: Iterable[int]) -> list[dict[str, Any]]:
        wanted = {int(item) for item in source_ids}
        return [
            item
            for item in self.search_prompt(public_only=False, limit=10000)
            if int(item.get("source_id") or 0) in wanted
        ]


_DEFAULT_VAULT: KnowledgeVault | None = None
_DEFAULT_VAULT_LOCK = threading.Lock()


def get_vault(storage_dir: str | Path | None = None) -> KnowledgeVault:
    global _DEFAULT_VAULT
    if storage_dir is not None:
        return KnowledgeVault(storage_dir)
    with _DEFAULT_VAULT_LOCK:
        configured = default_storage_dir().resolve()
        if _DEFAULT_VAULT is None or _DEFAULT_VAULT.storage_dir != configured:
            _DEFAULT_VAULT = KnowledgeVault(configured)
        return _DEFAULT_VAULT


def search_prompt(query: str = "", category: str = "", tags: Iterable[str] = ()) -> list[dict[str, Any]]:
    return get_vault().search_prompt(query, category, tags)


def recommend_prompts_for_video_goal(goal: str) -> list[dict[str, Any]]:
    return get_vault().recommend_prompts_for_video_goal(goal)


def recommend_assets_for_use_case(use_case: str) -> list[dict[str, Any]]:
    return get_vault().recommend_assets_for_use_case(use_case)


def get_reference_bundle(collection_id: int) -> dict[str, Any]:
    return get_vault().get_reference_bundle(collection_id)


def create_prompt_pack_from_sources(source_ids: Iterable[int]) -> list[dict[str, Any]]:
    return get_vault().create_prompt_pack_from_sources(source_ids)
