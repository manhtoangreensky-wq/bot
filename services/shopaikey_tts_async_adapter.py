from __future__ import annotations

import asyncio
import io
import json
import os
import re
import tarfile
import tempfile
import time
from typing import Any, Callable

import httpx

from services.subdub_tts_artifact_validator import (
    validate_tts_audio_artifact,
    STATUS_VALID,
)

DEFAULT_SHOPAIKEY_TTS_BASE_URL = "https://direct.shopaikey.com"
DEFAULT_SHOPAIKEY_TTS_MODEL = "speech-02-hd"
DEFAULT_MINIMAX_TTS_ASYNC_ENDPOINT = "/tts/minimax/t2a_async_v2"
DEFAULT_MINIMAX_TTS_QUERY_ENDPOINT = "/tts/minimax/query/t2a_async_query_v2"
DEFAULT_MINIMAX_TTS_FILE_RETRIEVE_ENDPOINT = "/tts/minimax/files/retrieve"


def get_shopaikey_env(key: str, default: str = "") -> str:
    return str(os.getenv(key, default) or "").strip()


def resolve_shopaikey_async_endpoint_url(
    endpoint: str,
    base_url: str = "",
) -> str:
    ep = str(endpoint or "").strip()
    if ep.startswith(("http://", "https://")):
        return ep.rstrip("/")
    base = str(base_url or get_shopaikey_env("SHOPAIKEY_TTS_BASE_URL") or DEFAULT_SHOPAIKEY_TTS_BASE_URL).strip().rstrip("/")
    if not ep.startswith("/"):
        ep = "/" + ep
    return f"{base}{ep}"


def build_shopaikey_async_payload(
    text: str,
    voice_id: str,
    model: str = "",
    speed: float | str = 1.0,
    tts_language_boost: str = "auto",
) -> dict[str, Any]:
    selected_model = str(model or get_shopaikey_env("SHOPAIKEY_TTS_MODEL") or DEFAULT_SHOPAIKEY_TTS_MODEL).strip()
    try:
        parsed_speed = float(speed or 1.0)
    except (ValueError, TypeError):
        parsed_speed = 1.0

    return {
        "model": selected_model,
        "text": str(text or "").strip()[:10000],
        "voice_setting": {
            "voice_id": str(voice_id or "").strip(),
            "speed": parsed_speed,
            "vol": 1,
            "pitch": 0,
        },
        "audio_setting": {
            "sample_rate": 32000,
            "bitrate": 128000,
            "format": "mp3",
            "channel": 1,
        },
        "language_boost": str(tts_language_boost or "auto").strip()[:64] or "auto",
    }


def parse_shopaikey_task_id(data: Any) -> str:
    if not isinstance(data, dict):
        return ""
    candidates = [
        data.get("task_id"),
        data.get("taskId"),
        (data.get("data") or {}).get("task_id") if isinstance(data.get("data"), dict) else "",
        (data.get("data") or {}).get("taskId") if isinstance(data.get("data"), dict) else "",
    ]
    for c in candidates:
        if c and str(c).strip():
            return str(c).strip()
    return ""


def parse_shopaikey_file_id_and_url(data: Any) -> tuple[str, str]:
    if not isinstance(data, dict):
        return "", ""
    file_id = ""
    download_url = ""

    body = data.get("data") if isinstance(data.get("data"), dict) else data
    file_obj = data.get("file") if isinstance(data.get("file"), dict) else ((body or {}).get("file") if isinstance(body, dict) else {})

    candidates_file_id = [
        (body or {}).get("file_id") if isinstance(body, dict) else "",
        (body or {}).get("fileId") if isinstance(body, dict) else "",
        data.get("file_id"),
        data.get("fileId"),
    ]
    for cid in candidates_file_id:
        if cid and str(cid).strip():
            file_id = str(cid).strip()
            break

    candidates_url = [
        (file_obj or {}).get("download_url") if isinstance(file_obj, dict) else "",
        (body or {}).get("download_url") if isinstance(body, dict) else "",
        (body or {}).get("audio_url") if isinstance(body, dict) else "",
        (body or {}).get("url") if isinstance(body, dict) else "",
        data.get("download_url"),
        data.get("audio_url"),
        data.get("url"),
    ]
    for u in candidates_url:
        if u and str(u).strip().startswith(("http://", "https://")):
            download_url = str(u).strip()
            break

    return file_id, download_url


def parse_shopaikey_task_status(data: Any, http_status: int) -> str:
    if http_status >= 400:
        return "FAIL"
    if not isinstance(data, dict):
        return "PROCESSING"

    body = data.get("data") if isinstance(data.get("data"), dict) else data
    status_raw = str(
        (body or {}).get("status")
        or (body or {}).get("task_status")
        or (body or {}).get("state")
        or data.get("status")
        or data.get("task_status")
        or data.get("state")
        or ""
    ).strip().lower()

    if status_raw in {"success", "succeeded", "completed", "finish", "done"}:
        return "SUCCESS"
    if status_raw in {"failed", "fail", "error", "cancelled", "canceled"}:
        return "FAIL"
    return "PROCESSING"


async def shopaikey_minimax_tts_async_submit(
    text: str,
    voice_id: str = "",
    model: str = "",
    speed: float | str = 1.0,
    tts_language_boost: str = "auto",
    client: httpx.AsyncClient | None = None,
    base_url: str = "",
    api_key: str = "",
    endpoint: str = "",
    timeout_seconds: float = 60.0,
) -> tuple[str, str, str, int]:
    key = str(api_key or get_shopaikey_env("SHOPAIKEY_API_KEY")).strip()
    if not key:
        return "MISSING", "", "SHOPAIKEY_API_KEY missing", 0

    text_clean = str(text or "").strip()
    if not text_clean:
        return "FAIL_BAD_REQUEST", "", "empty_text", 0

    selected_voice = str(voice_id or "").strip()
    if not selected_voice:
        return "FAIL_BAD_REQUEST", "", "missing_voice_id", 0

    target_endpoint = endpoint or get_shopaikey_env("MINIMAX_TTS_ASYNC_ENDPOINT") or DEFAULT_MINIMAX_TTS_ASYNC_ENDPOINT
    target_url = resolve_shopaikey_async_endpoint_url(target_endpoint, base_url)
    payload = build_shopaikey_async_payload(
        text=text_clean,
        voice_id=selected_voice,
        model=model,
        speed=speed,
        tts_language_boost=tts_language_boost,
    )
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    try:
        should_close = False
        if client is None:
            client = httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True)
            should_close = True

        try:
            res = await client.post(target_url, headers=headers, json=payload)
        finally:
            if should_close:
                await client.aclose()

        http_status = int(res.status_code)
        try:
            data = res.json()
        except Exception:
            data = {}

        if http_status < 400:
            task_id = parse_shopaikey_task_id(data)
            if task_id:
                return "PASS", task_id, f"http={http_status}; task_id={task_id}; url={target_url}", http_status
            return "FAIL_NO_TASK_ID", "", f"http={http_status}; no_task_id_in_response; url={target_url}", http_status

        error_detail = str(res.text[:300] if getattr(res, "text", "") else f"HTTP {http_status}")
        return "FAIL_HTTP_STATUS", "", f"http={http_status}; detail={error_detail}; url={target_url}", http_status

    except httpx.TimeoutException as exc:
        return "FAIL_TIMEOUT", "", f"timeout: {exc}", 0
    except Exception as exc:
        return "FAIL_PROVIDER_ERROR", "", f"{type(exc).__name__}: {exc}", 0


async def shopaikey_minimax_tts_async_query(
    task_id: str,
    client: httpx.AsyncClient | None = None,
    base_url: str = "",
    api_key: str = "",
    endpoint: str = "",
    timeout_seconds: float = 30.0,
) -> tuple[str, str, str, int]:
    key = str(api_key or get_shopaikey_env("SHOPAIKEY_API_KEY")).strip()
    clean_task_id = str(task_id or "").strip()
    if not clean_task_id:
        return "FAIL_BAD_REQUEST", "", "missing_task_id", 0

    target_endpoint = endpoint or get_shopaikey_env("MINIMAX_TTS_QUERY_ENDPOINT") or DEFAULT_MINIMAX_TTS_QUERY_ENDPOINT
    target_url = resolve_shopaikey_async_endpoint_url(target_endpoint, base_url)
    headers = {"Authorization": f"Bearer {key}"} if key else {}

    try:
        should_close = False
        if client is None:
            client = httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True)
            should_close = True

        try:
            res = await client.get(target_url, headers=headers, params={"task_id": clean_task_id})
        finally:
            if should_close:
                await client.aclose()

        http_status = int(res.status_code)
        try:
            data = res.json()
        except Exception:
            data = {}

        if http_status < 400:
            status = parse_shopaikey_task_status(data, http_status)
            file_id, download_url = parse_shopaikey_file_id_and_url(data)
            identifier = download_url or file_id
            return status, identifier, f"http={http_status}; status={status}; file_id={file_id}; url={'yes' if download_url else 'no'}", http_status

        error_detail = str(res.text[:300] if getattr(res, "text", "") else f"HTTP {http_status}")
        return "FAIL", "", f"http={http_status}; detail={error_detail}", http_status

    except httpx.TimeoutException as exc:
        return "FAIL_TIMEOUT", "", f"timeout: {exc}", 0
    except Exception as exc:
        return "FAIL_PROVIDER_ERROR", "", f"{type(exc).__name__}: {exc}", 0


async def shopaikey_minimax_tts_async_retrieve(
    file_id: str,
    client: httpx.AsyncClient | None = None,
    base_url: str = "",
    api_key: str = "",
    endpoint: str = "",
    timeout_seconds: float = 30.0,
) -> tuple[str, str, str, int]:
    key = str(api_key or get_shopaikey_env("SHOPAIKEY_API_KEY")).strip()
    clean_file_id = str(file_id or "").strip()
    if not clean_file_id:
        return "FAIL_BAD_REQUEST", "", "missing_file_id", 0

    target_endpoint = endpoint or get_shopaikey_env("MINIMAX_TTS_FILE_RETRIEVE_ENDPOINT") or DEFAULT_MINIMAX_TTS_FILE_RETRIEVE_ENDPOINT
    target_url = resolve_shopaikey_async_endpoint_url(target_endpoint, base_url)
    headers = {"Authorization": f"Bearer {key}"} if key else {}

    try:
        should_close = False
        if client is None:
            client = httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True)
            should_close = True

        try:
            res = await client.get(target_url, headers=headers, params={"file_id": clean_file_id})
        finally:
            if should_close:
                await client.aclose()

        http_status = int(res.status_code)
        try:
            data = res.json()
        except Exception:
            data = {}

        if http_status < 400:
            _file_id, download_url = parse_shopaikey_file_id_and_url(data)
            if download_url:
                return "PASS", download_url, f"http={http_status}; download_url=ok", http_status
            content_type = str(res.headers.get("content-type") or "")
            if res.content and content_type.startswith("audio/"):
                return "PASS_BINARY", clean_file_id, f"http={http_status}; binary_audio_bytes={len(res.content)}", http_status
            return "FAIL_NO_URL", "", f"http={http_status}; no_download_url", http_status

        error_detail = str(res.text[:300] if getattr(res, "text", "") else f"HTTP {http_status}")
        return "FAIL", "", f"http={http_status}; detail={error_detail}", http_status

    except httpx.TimeoutException as exc:
        return "FAIL_TIMEOUT", "", f"timeout: {exc}", 0
    except Exception as exc:
        return "FAIL_PROVIDER_ERROR", "", f"{type(exc).__name__}: {exc}", 0


MAX_SHOPAIKEY_AUDIO_ARCHIVE_BYTES = 50 * 1024 * 1024  # 50 MB
MAX_SHOPAIKEY_TAR_MEMBERS = 32
MAX_SHOPAIKEY_EXTRACTED_AUDIO_BYTES = 50 * 1024 * 1024  # 50 MB


def is_valid_mp3_payload(data: bytes) -> bool:
    """Cheap magic-byte prefilter to check potential MP3 container (ID3 or frame sync)."""
    if not data or len(data) < 32:
        return False
    if data.startswith(b"ID3"):
        return True
    if data[0] == 0xFF and (data[1] & 0xE0) == 0xE0:
        return True
    return False


def validate_mp3_audio_bytes(
    data: bytes,
    *,
    expected_container: str = "mp3",
    expected_codec: str = "mp3",
    min_duration: float = 0.01,
) -> tuple[bool, str]:
    """Validate in-memory audio bytes using the canonical validator.

    Guarantees:
    - TEMP_FILE_CLEANUP=ALWAYS via finally block
    - Canonical ffprobe container=mp3, codec=mp3/mp3float, duration>0, full ffmpeg decode PASS
    - PRODUCTION_ARTIFACT_WRITE=NO
    - CHECKPOINT_WRITE_BEFORE_VALIDATION=NO
    """
    if not data or len(data) < 32:
        return False, "audio_bytes_too_short_or_empty"

    temp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            temp_path = tmp.name
            tmp.write(data)
            tmp.flush()

        res = validate_tts_audio_artifact(
            temp_path,
            expected_container=expected_container,
            expected_codec=expected_codec,
            min_duration=min_duration,
        )
        if not res.ok:
            return False, f"status={res.status}; detail={res.detail}"
        if res.duration <= 0.0:
            return False, f"status=ZERO_OR_INVALID_DURATION; duration={res.duration}"
        return True, f"status={STATUS_VALID}; duration={res.duration:.4f}s; codec={res.codec}"
    except Exception as exc:
        return False, f"exception={type(exc).__name__}: {exc}"
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass


def normalize_shopaikey_tts_audio_payload(
    content: bytes,
    content_type: str = "",
) -> tuple[str, bytes, str]:
    """
    Safely classify, validate, and normalize ShopAIKey TTS audio responses.

    Returns:
        tuple[status, clean_audio_bytes, detail]
        - Direct MP3 => validated and returned directly
        - POSIX TAR => safely extracted regular *.mp3 member in memory (ignoring sidecars)
        - Multiple MP3s / 0 MP3s / symlinks / hardlinks / path traversal / absolute paths / invalid audio => fail closed
    """
    if not content:
        return "FAIL_EMPTY", b"", "empty_audio_content"

    if len(content) > MAX_SHOPAIKEY_AUDIO_ARCHIVE_BYTES:
        return "FAIL_PAYLOAD_TOO_LARGE", b"", f"payload_exceeds_limit: {len(content)} > {MAX_SHOPAIKEY_AUDIO_ARCHIVE_BYTES}"

    # 1. In-memory TAR archive inspection if recognized as tar
    is_tar = False
    if len(content) >= 512:
        if len(content) >= 262 and content[257:262] == b"ustar":
            is_tar = True
        else:
            try:
                is_tar = tarfile.is_tarfile(io.BytesIO(content))
            except Exception:
                is_tar = False

    if is_tar:
        try:
            with tarfile.open(fileobj=io.BytesIO(content), mode="r:*") as tf:
                members = tf.getmembers()
                if len(members) > MAX_SHOPAIKEY_TAR_MEMBERS:
                    return "FAIL_UNSAFE_TAR", b"", f"tar_too_many_members: {len(members)} > {MAX_SHOPAIKEY_TAR_MEMBERS}"

                mp3_members: list[tarfile.TarInfo] = []

                for m in members:
                    # Reject symlinks and hardlinks
                    if m.issym() or m.islnk():
                        return "FAIL_UNSAFE_TAR", b"", f"tar_unsafe_link: name={m.name}; link={m.linkname}"

                    # Reject path traversal / absolute paths
                    norm_name = m.name.replace("\\", "/")
                    parts = [p for p in norm_name.split("/") if p]
                    if (
                        any(p == ".." for p in parts)
                        or norm_name.startswith("/")
                        or os.path.isabs(m.name)
                        or os.path.isabs(norm_name)
                        or bool(re.match(r"^[a-zA-Z]:", norm_name))
                    ):
                        return "FAIL_UNSAFE_TAR", b"", f"tar_path_traversal: name={m.name}"

                    # Collect regular .mp3 files (sidecars like .titles and .extra are ignored)
                    if m.isreg() and m.name.lower().endswith(".mp3"):
                        mp3_members.append(m)

                if len(mp3_members) == 0:
                    return "FAIL_NO_MP3", b"", f"tar_archive_contains_no_mp3: no mp3 found in archive (members={len(members)})"

                if len(mp3_members) > 1:
                    names = [m.name for m in mp3_members]
                    return "FAIL_MULTIPLE_MP3", b"", f"tar_archive_contains_multiple_mp3: {names}"

                target_member = mp3_members[0]
                if target_member.size > MAX_SHOPAIKEY_EXTRACTED_AUDIO_BYTES:
                    return "FAIL_AUDIO_TOO_LARGE", b"", f"extracted_mp3_too_large: {target_member.size}"

                extracted_file = tf.extractfile(target_member)
                if extracted_file is None:
                    return "FAIL_TAR_EXTRACT", b"", f"tar_extractfile_none: name={target_member.name}"

                extracted_bytes = extracted_file.read(MAX_SHOPAIKEY_EXTRACTED_AUDIO_BYTES + 1)
                if len(extracted_bytes) > MAX_SHOPAIKEY_EXTRACTED_AUDIO_BYTES:
                    return "FAIL_AUDIO_TOO_LARGE", b"", f"extracted_mp3_read_overflow: {len(extracted_bytes)}"

                val_ok, val_detail = validate_mp3_audio_bytes(extracted_bytes)
                if not val_ok:
                    return "FAIL_INVALID_AUDIO", b"", f"extracted_member_invalid_audio: name={target_member.name}; {val_detail}"

                return "PASS", extracted_bytes, f"tar_extracted; member={target_member.name}; bytes={len(extracted_bytes)}; {val_detail}"

        except (tarfile.TarError, Exception) as exc:
            return "FAIL_CORRUPT_TAR", b"", f"tar_processing_error: {type(exc).__name__}: {exc}"

    # 2. Direct MP3 check (magic-byte prefilter + canonical validator)
    if is_valid_mp3_payload(content):
        val_ok, val_detail = validate_mp3_audio_bytes(content)
        if val_ok:
            return "PASS", content, f"direct_mp3; bytes={len(content)}; {val_detail}"
        return "FAIL_INVALID_AUDIO", b"", f"direct_mp3_invalid_audio: {val_detail}"

    # 3. Unknown or unsupported binary payload => fail closed
    return "FAIL_UNKNOWN_PAYLOAD", b"", f"unknown_payload_rejected: bytes={len(content)}; content_type={content_type}"


async def download_audio_from_url(
    url: str,
    timeout_seconds: float = 60.0,
    client: httpx.AsyncClient | None = None,
) -> tuple[bytes, str, int]:
    target = str(url or "").strip()
    if not target.startswith(("http://", "https://")):
        return b"", "invalid_audio_url", 0

    should_close = False
    if client is None:
        client = httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True)
        should_close = True

    try:
        last_exc_detail = ""
        for attempt in range(3):
            try:
                res = await client.get(target)
                http_status = int(res.status_code)
                content = bytes(res.content or b"")
                content_type = str(res.headers.get("content-type") or "")
                if http_status < 400 and content:
                    norm_status, clean_bytes, norm_detail = normalize_shopaikey_tts_audio_payload(content, content_type=content_type)
                    if norm_status == "PASS" and clean_bytes:
                        return clean_bytes, f"http={http_status}; bytes={len(clean_bytes)}; {norm_detail}", http_status
                    return b"", f"http={http_status}; normalization_failed={norm_status}; {norm_detail}", http_status
                if attempt < 2 and http_status >= 500:
                    await asyncio.sleep(1.0)
                    continue
                return b"", f"http={http_status}; bytes={len(content)}; content_type={content_type}", http_status
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_exc_detail = f"{type(exc).__name__}: {exc}"
                if attempt < 2:
                    await asyncio.sleep(1.0)
                    continue
                return b"", f"network_error: {last_exc_detail}", 0
        return b"", f"download_exhausted: {last_exc_detail}", 0
    finally:
        if should_close:
            await client.aclose()


async def shopaikey_minimax_tts_async_bytes(
    text: str,
    voice_id: str = "",
    model: str = "",
    speed: float | str = 1.0,
    tts_language_boost: str = "auto",
    poll_interval_seconds: float = 2.0,
    max_poll_seconds: float = 60.0,
    existing_task_id: str = "",
    client: httpx.AsyncClient | None = None,
    api_key: str = "",
    base_url: str = "",
    on_submit_hook: Callable[[str], None] | None = None,
    audio_downloader: Callable[[str], Any] | None = None,
) -> tuple[str, bytes, str, int, str]:
    task_id = str(existing_task_id or "").strip()

    # Phase 1: Submit if not already submitted
    if not task_id:
        submit_status, new_task_id, submit_detail, http_status = await shopaikey_minimax_tts_async_submit(
            text=text,
            voice_id=voice_id,
            model=model,
            speed=speed,
            tts_language_boost=tts_language_boost,
            client=client,
            api_key=api_key,
            base_url=base_url,
        )
        if submit_status != "PASS" or not new_task_id:
            return submit_status, b"", submit_detail, http_status, ""
        task_id = new_task_id
        if on_submit_hook:
            try:
                on_submit_hook(task_id)
            except Exception:
                pass

    # Phase 2: Polling Query loop
    start_time = time.monotonic()
    last_query_status = "PROCESSING"
    last_detail = ""
    last_http = 200
    target_identifier = ""

    while (time.monotonic() - start_time) < max_poll_seconds:
        q_status, identifier, q_detail, q_http = await shopaikey_minimax_tts_async_query(
            task_id=task_id,
            client=client,
            api_key=api_key,
            base_url=base_url,
        )
        last_query_status = q_status
        last_detail = q_detail
        last_http = q_http

        if q_status == "SUCCESS":
            target_identifier = identifier
            break
        if q_status == "FAIL":
            return "FAIL_PROVIDER_TASK", b"", f"task_failed: {q_detail}", q_http, task_id

        await asyncio.sleep(poll_interval_seconds)

    if last_query_status != "SUCCESS" or not target_identifier:
        return "FAIL_TIMEOUT", b"", f"poll_timeout_after_{int(max_poll_seconds)}s: {last_detail}", last_http, task_id

    # Phase 3: Retrieve download URL if target_identifier is a file_id
    download_url = target_identifier
    if not download_url.startswith(("http://", "https://")):
        r_status, r_url, r_detail, r_http = await shopaikey_minimax_tts_async_retrieve(
            file_id=target_identifier,
            client=client,
            api_key=api_key,
            base_url=base_url,
        )
        if r_status != "PASS" or not r_url:
            return "FAIL_RETRIEVE", b"", f"retrieve_failed: {r_detail}", r_http, task_id
        download_url = r_url

    # Phase 4: Download binary audio bytes
    if audio_downloader is not None:
        audio_bytes, dl_detail, dl_http = await audio_downloader(download_url)
    else:
        audio_bytes, dl_detail, dl_http = await download_audio_from_url(download_url, client=client)
    if not audio_bytes or len(audio_bytes) < 32:
        return "FAIL_AUDIO_EMPTY", b"", f"empty_audio: {dl_detail}", dl_http, task_id

    norm_status, clean_bytes, norm_detail = normalize_shopaikey_tts_audio_payload(audio_bytes)
    if norm_status != "PASS" or not clean_bytes:
        return "FAIL_AUDIO_NORMALIZATION", b"", f"normalization_failed: {norm_status}; {norm_detail}", dl_http, task_id

    return "PASS", clean_bytes, f"http={last_http}; bytes={len(clean_bytes)}; task_id={task_id}", last_http, task_id
