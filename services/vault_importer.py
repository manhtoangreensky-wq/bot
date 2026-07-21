"""Local and Telegram-file importer for the TOAN AAS Knowledge Vault."""

from __future__ import annotations

import json
import mimetypes
import os
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from services.knowledge_vault import KnowledgeVault, get_vault, sha256_file, utc_now_text
from services.media_classifier import classify_source, media_type_for_path, supported_path
from services.prompt_extractor import extract_prompts


DEFAULT_IMPORT_ROOT = r"D:\toanaas"
DEFAULT_VIDEO_REFERENCE_DIR = r"D:\toanaas\video AI tham khảo"


@dataclass
class MediaMetadata:
    duration_sec: float = 0
    width: int = 0
    height: int = 0
    ratio: str = ""
    audio_streams: int = 0


def _safe_filename(value: str) -> str:
    name = Path(str(value or "source.bin")).name
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip(".-")
    return (stem or "source.bin")[:180]


def _ratio(width: int, height: int) -> str:
    if not width or not height:
        return ""
    from math import gcd

    divisor = gcd(int(width), int(height))
    return f"{int(width) // divisor}:{int(height) // divisor}"


def desired_keyframe_count(duration_sec: float) -> int:
    duration = float(duration_sec or 0)
    if duration < 30:
        return 4
    if duration <= 90:
        return 6
    return 10


class VaultImporter:
    def __init__(
        self,
        vault: KnowledgeVault | None = None,
        *,
        ffmpeg_path: str = "",
        ffprobe_path: str = "",
        ocr_adapter: Callable[[Path], str] | None = None,
        asr_adapter: Callable[[Path], str] | None = None,
    ) -> None:
        self.vault = vault or get_vault()
        self.ffmpeg_path = (
            ffmpeg_path
            or os.getenv("FFMPEG_PATH", "").strip()
            or os.getenv("FFMPEG_BINARY", "").strip()
            or shutil.which("ffmpeg")
            or ""
        )
        self.ffprobe_path = (
            ffprobe_path
            or os.getenv("FFPROBE_PATH", "").strip()
            or shutil.which("ffprobe")
            or ""
        )
        self.ocr_adapter = ocr_adapter
        self.asr_adapter = asr_adapter

    @property
    def ffmpeg_available(self) -> bool:
        return bool(self.ffmpeg_path and (Path(self.ffmpeg_path).exists() or shutil.which(self.ffmpeg_path)))

    @property
    def ffprobe_available(self) -> bool:
        return bool(self.ffprobe_path and (Path(self.ffprobe_path).exists() or shutil.which(self.ffprobe_path)))

    def probe_media(self, path: str | Path) -> MediaMetadata:
        if not self.ffprobe_available:
            return MediaMetadata()
        command = [
            self.ffprobe_path,
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,width,height",
            "-of",
            "json",
            str(path),
        ]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if result.returncode != 0:
                return MediaMetadata()
            payload = json.loads(result.stdout or "{}")
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
            return MediaMetadata()
        streams = list(payload.get("streams") or [])
        video = next((item for item in streams if item.get("codec_type") == "video"), {})
        width = int(video.get("width") or 0)
        height = int(video.get("height") or 0)
        return MediaMetadata(
            duration_sec=float((payload.get("format") or {}).get("duration") or 0),
            width=width,
            height=height,
            ratio=_ratio(width, height),
            audio_streams=sum(1 for item in streams if item.get("codec_type") == "audio"),
        )

    def _run_ffmpeg(self, arguments: list[str], *, timeout: int = 60) -> bool:
        if not self.ffmpeg_available:
            return False
        try:
            result = subprocess.run(
                [self.ffmpeg_path, "-hide_banner", "-loglevel", "error", "-y", *arguments],
                capture_output=True,
                timeout=timeout,
                check=False,
            )
            output = Path(arguments[-1])
            return result.returncode == 0 and output.exists() and output.stat().st_size > 0
        except (OSError, subprocess.TimeoutExpired):
            return False

    def create_thumbnail(self, source: Path, source_id: int, duration_sec: float) -> Path | None:
        output = self.vault.preview_dir / f"source-{source_id}-thumbnail.jpg"
        timestamp = max(0.0, min(float(duration_sec or 0) * 0.1, 3.0))
        ok = self._run_ffmpeg(["-ss", f"{timestamp:.3f}", "-i", str(source), "-frames:v", "1", str(output)])
        return output if ok else None

    def create_keyframes(self, source: Path, source_id: int, duration_sec: float) -> list[tuple[Path, float]]:
        count = desired_keyframe_count(duration_sec)
        duration = max(float(duration_sec or 0), float(count))
        frames: list[tuple[Path, float]] = []
        for index in range(count):
            timestamp = duration * (index + 1) / (count + 1)
            output = self.vault.keyframe_dir / f"source-{source_id}-frame-{index + 1:02d}.jpg"
            if self._run_ffmpeg(
                ["-ss", f"{timestamp:.3f}", "-i", str(source), "-frames:v", "1", str(output)]
            ):
                frames.append((output, timestamp))
        return frames

    def extract_audio(self, source: Path, source_id: int) -> Path | None:
        output = self.vault.audio_dir / f"source-{source_id}-audio.m4a"
        ok = self._run_ffmpeg(["-i", str(source), "-vn", "-c:a", "aac", "-b:a", "160k", str(output)])
        return output if ok else None

    def _save_prompt_candidates(
        self,
        source_id: int,
        texts: Iterable[str],
        *,
        source_kind: str,
        created_by: int | str | None,
        asset_id: int | None = None,
    ) -> int:
        count = 0
        for candidate in extract_prompts(texts, source_kind=source_kind):
            record, duplicate = self.vault.add_prompt(
                source_id=source_id,
                asset_id=asset_id,
                title=str(candidate["cleaned_prompt_text"])[:80],
                prompt_text=candidate["prompt_text"],
                prompt_type=candidate["prompt_type"],
                negative_prompt=candidate["negative_prompt"],
                language=candidate["language"],
                model_hint=candidate["model_hint"],
                ratio_hint=candidate["ratio_hint"],
                duration_hint=candidate["duration_hint"],
                style_tags=candidate["style_tags"],
                scene_count=candidate["scene_count"],
                category=candidate["category"],
                use_case=candidate["use_case"],
                source_confidence=candidate["source_confidence"],
                created_by=created_by,
                source_original_text=candidate["source_original_text"],
                cleaned_prompt_text=candidate["cleaned_prompt_text"],
            )
            if record and not duplicate:
                count += 1
        return count

    def import_file(
        self,
        path: str | Path,
        *,
        source_type: str = "admin_import",
        imported_by_user_id: int | str | None = None,
        collection_id: int | None = None,
        rights_status: str = "reference_only",
        file_id: str = "",
        original_name: str = "",
    ) -> dict[str, Any]:
        source_path = Path(path).expanduser()
        if not source_path.is_file():
            return {"ok": False, "reason": "local_path_unavailable", "path": str(source_path)}
        if not supported_path(source_path):
            return {"ok": False, "reason": "unsupported_file_type", "path": str(source_path)}
        checksum = sha256_file(source_path)
        mime_type = mimetypes.guess_type(source_path.name)[0] or "application/octet-stream"
        source, duplicate = self.vault.add_source(
            source_type=source_type,
            original_name=original_name or source_path.name,
            local_path=str(source_path),
            file_id=file_id,
            mime_type=mime_type,
            size_bytes=source_path.stat().st_size,
            checksum_sha256=checksum,
            source_collection_id=collection_id,
            imported_by_user_id=imported_by_user_id,
            status="pending",
            rights_status=rights_status,
        )
        if duplicate:
            return {"ok": True, "duplicate": True, "source": source, "assets": [], "prompts_draft": 0}

        source_id = int(source["id"])
        job = self.vault.add_extraction_job(source_id, "video_analyze" if media_type_for_path(source_path) == "video" else "classify")
        self.vault.update_extraction_job(job["id"], status="processing", stage="copy", started_at=utc_now_text(), progress=5)
        stored_path = self.vault.media_dir / f"source-{source_id}-{_safe_filename(source_path.name)}"
        try:
            shutil.copy2(source_path, stored_path)
        except OSError as exc:
            self.vault.update_source(
                source_id,
                status="failed",
                error_code="source_copy_failed",
                error_message_admin=f"{type(exc).__name__}:{str(exc)[:240]}",
            )
            self.vault.update_extraction_job(
                job["id"],
                status="failed",
                stage="copy",
                finished_at=utc_now_text(),
                error_admin="source_copy_failed",
                public_safe_error="import_failed",
            )
            return {"ok": False, "reason": "source_copy_failed", "source": source}

        self.vault.update_source(source_id, local_path=str(stored_path), status="processing")
        classification = classify_source(stored_path, mime_type=mime_type)
        metadata = self.probe_media(stored_path)
        self.vault.update_source(source_id, **asdict(metadata))
        media_type = classification["asset_type"]
        asset_type = media_type if media_type in {"video", "image", "music", "sfx", "voice"} else "document"
        main_asset = self.vault.add_asset(
            source_id=source_id,
            asset_type=asset_type,
            title=source.get("original_name") or stored_path.name,
            local_path=str(stored_path),
            duration_sec=metadata.duration_sec,
            width=metadata.width,
            height=metadata.height,
            ratio=metadata.ratio,
            tags=classification["tags"],
            category=classification["category"],
            use_case=classification["use_case"],
            rights_status=rights_status,
            visibility="admin_only",
            metadata={"needs_rights_review": classification["needs_rights_review"]},
        )
        assets = [main_asset]
        prompts_draft = 0
        extraction_notes: list[str] = []
        self.vault.update_extraction_job(job["id"], stage="extract", progress=30)

        if media_type == "video":
            thumbnail = self.create_thumbnail(stored_path, source_id, metadata.duration_sec)
            if thumbnail:
                assets.append(
                    self.vault.add_asset(
                        source_id=source_id,
                        asset_type="thumbnail",
                        title=f"{source['original_name']} thumbnail",
                        local_path=str(thumbnail),
                        preview_path=str(thumbnail),
                        width=metadata.width,
                        height=metadata.height,
                        ratio=metadata.ratio,
                        tags=classification["tags"],
                        category=classification["category"],
                        rights_status=rights_status,
                        visibility="admin_only",
                    )
                )
            frames = self.create_keyframes(stored_path, source_id, metadata.duration_sec)
            for frame_index, (frame_path, timestamp) in enumerate(frames, start=1):
                frame_asset = self.vault.add_asset(
                    source_id=source_id,
                    asset_type="keyframe",
                    title=f"{source['original_name']} frame {frame_index}",
                    local_path=str(frame_path),
                    preview_path=str(frame_path),
                    width=metadata.width,
                    height=metadata.height,
                    ratio=metadata.ratio,
                    tags=classification["tags"],
                    category=classification["category"],
                    rights_status=rights_status,
                    visibility="admin_only",
                    metadata={"frame_timestamp_sec": round(timestamp, 3)},
                )
                assets.append(frame_asset)
                if self.ocr_adapter:
                    try:
                        ocr_text = str(self.ocr_adapter(frame_path) or "").strip()
                    except Exception:
                        ocr_text = ""
                        extraction_notes.append("ocr_adapter_failed")
                    if ocr_text:
                        prompts_draft += self._save_prompt_candidates(
                            source_id,
                            [ocr_text],
                            source_kind="ocr",
                            created_by=imported_by_user_id,
                            asset_id=frame_asset["id"],
                        )
            if metadata.audio_streams:
                audio_path = self.extract_audio(stored_path, source_id)
                if audio_path:
                    audio_asset = self.vault.add_asset(
                        source_id=source_id,
                        asset_type="audio",
                        title=f"{source['original_name']} extracted audio",
                        local_path=str(audio_path),
                        duration_sec=metadata.duration_sec,
                        tags=["needs_review"],
                        category=classification["category"],
                        rights_status=rights_status,
                        visibility="admin_only",
                    )
                    assets.append(audio_asset)
                    if self.asr_adapter:
                        try:
                            transcript = str(self.asr_adapter(audio_path) or "").strip()
                        except Exception:
                            transcript = ""
                            extraction_notes.append("asr_adapter_failed")
                        if transcript:
                            prompts_draft += self._save_prompt_candidates(
                                source_id,
                                [transcript],
                                source_kind="asr",
                                created_by=imported_by_user_id,
                                asset_id=audio_asset["id"],
                            )
            if not self.ocr_adapter:
                extraction_notes.append("ocr_unavailable")
            if metadata.audio_streams and not self.asr_adapter:
                extraction_notes.append("asr_unavailable")
        elif media_type == "image" and self.ocr_adapter:
            try:
                ocr_text = str(self.ocr_adapter(stored_path) or "").strip()
            except Exception:
                ocr_text = ""
                extraction_notes.append("ocr_adapter_failed")
            if ocr_text:
                prompts_draft += self._save_prompt_candidates(
                    source_id,
                    [ocr_text],
                    source_kind="ocr",
                    created_by=imported_by_user_id,
                    asset_id=main_asset["id"],
                )
        elif media_type == "document":
            try:
                text = stored_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                text = ""
            prompts_draft += self._save_prompt_candidates(
                source_id,
                [text],
                source_kind="caption_file",
                created_by=imported_by_user_id,
                asset_id=main_asset["id"],
            )

        needs_review = bool(
            extraction_notes
            or classification["needs_rights_review"]
            or rights_status not in {"own", "licensed"}
        )
        final_status = "needs_review" if needs_review else "extracted"
        self.vault.update_source(source_id, status=final_status)
        result = {
            "ok": True,
            "duplicate": False,
            "source": self.vault.get_source(source_id),
            "assets": assets,
            "prompts_draft": prompts_draft,
            "needs_review": needs_review,
            "notes": sorted(set(extraction_notes)),
        }
        self.vault.update_extraction_job(
            job["id"],
            status="completed",
            stage="review",
            progress=100,
            finished_at=utc_now_text(),
            result_json={
                "asset_count": len(assets),
                "prompts_draft": prompts_draft,
                "needs_review": needs_review,
                "notes": result["notes"],
            },
        )
        return result

    def import_bytes(
        self,
        data: bytes,
        *,
        original_name: str,
        source_type: str = "telegram_upload",
        imported_by_user_id: int | str | None = None,
        collection_id: int | None = None,
        rights_status: str = "unknown",
        file_id: str = "",
    ) -> dict[str, Any]:
        safe_name = _safe_filename(original_name)
        upload_dir = self.vault.storage_dir / "incoming"
        upload_dir.mkdir(parents=True, exist_ok=True)
        temporary_path = upload_dir / safe_name
        suffix = 1
        while temporary_path.exists():
            temporary_path = upload_dir / f"{Path(safe_name).stem}-{suffix}{Path(safe_name).suffix}"
            suffix += 1
        temporary_path.write_bytes(bytes(data or b""))
        try:
            return self.import_file(
                temporary_path,
                source_type=source_type,
                imported_by_user_id=imported_by_user_id,
                collection_id=collection_id,
                rights_status=rights_status,
                file_id=file_id,
                original_name=original_name,
            )
        finally:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass

    def scan_folder(
        self,
        folder: str | Path,
        *,
        max_files: int = 50,
        max_depth: int = 2,
        max_file_size_bytes: int = 500 * 1024 * 1024,
    ) -> dict[str, Any]:
        root = Path(folder).expanduser()
        if not root.is_dir():
            return {
                "ok": False,
                "reason": "local_path_unavailable",
                "root": str(root),
                "files": [],
                "file_count": 0,
            }
        max_files = max(1, min(int(max_files or 50), 1000))
        max_depth = max(0, min(int(max_depth or 2), 10))
        files: list[Path] = []
        for path in root.rglob("*"):
            if not path.is_file() or not supported_path(path):
                continue
            try:
                relative_depth = len(path.relative_to(root).parts) - 1
                size = path.stat().st_size
            except OSError:
                continue
            if relative_depth > max_depth or size > max_file_size_bytes:
                continue
            files.append(path)
            if len(files) >= max_files:
                break
        return {
            "ok": True,
            "reason": "ok",
            "root": str(root),
            "files": [str(path) for path in files],
            "file_count": len(files),
            "limit_reached": len(files) >= max_files,
        }

    def import_folder(
        self,
        folder: str | Path,
        *,
        imported_by_user_id: int | str | None = None,
        collection_id: int | None = None,
        max_files: int = 50,
        max_depth: int = 2,
        max_file_size_bytes: int = 500 * 1024 * 1024,
        rights_status: str = "reference_only",
    ) -> dict[str, Any]:
        scan = self.scan_folder(
            folder,
            max_files=max_files,
            max_depth=max_depth,
            max_file_size_bytes=max_file_size_bytes,
        )
        if not scan["ok"]:
            self.vault.set_last_import(scan)
            return scan
        results = [
            self.import_file(
                path,
                source_type="local_folder",
                imported_by_user_id=imported_by_user_id,
                collection_id=collection_id,
                rights_status=rights_status,
            )
            for path in scan["files"]
        ]
        summary = {
            "ok": True,
            "root": scan["root"],
            "file_count": scan["file_count"],
            "scanned": scan["file_count"],
            "processed": sum(1 for item in results if item.get("ok") and not item.get("duplicate")),
            "imported": sum(1 for item in results if item.get("ok") and not item.get("duplicate")),
            "duplicates": sum(1 for item in results if item.get("duplicate")),
            "failed": sum(1 for item in results if not item.get("ok")),
            "assets": sum(len(item.get("assets") or []) for item in results),
            "prompts_draft": sum(int(item.get("prompts_draft") or 0) for item in results),
            "needs_review": sum(1 for item in results if item.get("needs_review")),
            "limit_reached": scan["limit_reached"],
            "results": results,
        }
        self.vault.set_last_import({key: value for key, value in summary.items() if key != "results"})
        return summary

    def debug_status(self) -> dict[str, Any]:
        import_root = os.getenv("TOAN_AAS_VAULT_IMPORT_ROOT", DEFAULT_IMPORT_ROOT)
        video_ref_dir = os.getenv("TOAN_AAS_VAULT_VIDEO_REF_DIR", DEFAULT_VIDEO_REFERENCE_DIR)
        return {
            **self.vault.status(include_paths=True),
            "import_root": import_root,
            "import_root_available": Path(import_root).is_dir(),
            "video_ref_dir": video_ref_dir,
            "video_ref_dir_available": Path(video_ref_dir).is_dir(),
            "ocr_available": self.ocr_adapter is not None,
            "asr_available": self.asr_adapter is not None,
            "ffmpeg_available": self.ffmpeg_available,
            "ffprobe_available": self.ffprobe_available,
        }
