from __future__ import annotations

import ast
import asyncio
import html
import io
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services import video_edit_state_machine, video_local_editing


BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def function_source(name: str) -> str:
    markers = (f"async def {name}(", f"def {name}(")
    starts = [BOT_SOURCE.find(marker) for marker in markers]
    start = next(position for position in starts if position >= 0)
    candidates = (
        BOT_SOURCE.find("\ndef ", start + 1),
        BOT_SOURCE.find("\nasync def ", start + 1),
    )
    ends = [position for position in candidates if position >= 0]
    return BOT_SOURCE[start : min(ends) if ends else len(BOT_SOURCE)]


def compile_function(name: str, namespace: dict):
    source = "from __future__ import annotations\n\n" + function_source(name)
    module = ast.parse(source, filename=f"<{name}>")
    exec(compile(module, filename=f"<{name}>", mode="exec"), namespace)
    return namespace[name]


class Logger:
    def __init__(self):
        self.warnings: list[str] = []

    def warning(self, message: str, *args) -> None:
        self.warnings.append(message % args if args else message)


class Message:
    chat_id = 7001
    message_id = 901

    def __init__(self):
        self.replies: list[dict] = []

    async def reply_text(self, text: str, **kwargs):
        self.replies.append({"text": text, **kwargs})
        return SimpleNamespace(message_id=len(self.replies))


class ImageBot:
    def __init__(self, *, photo_timeout: bool = False):
        self.photo_timeout = photo_timeout
        self.photos: list[dict] = []
        self.documents: list[dict] = []
        self.messages: list[dict] = []

    async def send_photo(self, **kwargs):
        self.photos.append(kwargs)
        if self.photo_timeout:
            raise TimeoutError("Timed out")
        return SimpleNamespace(photo=[SimpleNamespace(file_id="edited-photo")], document=None)

    async def send_document(self, **kwargs):
        self.documents.append(kwargs)
        return SimpleNamespace(photo=None, document=SimpleNamespace(file_id="edited-document"))

    async def send_message(self, **kwargs):
        self.messages.append(kwargs)
        return SimpleNamespace(message_id=len(self.messages))


def image_payload() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (64, 64), (120, 130, 140)).save(output, format="PNG")
    return output.getvalue()


def image_namespace(bot: ImageBot, saved: list[dict], logger: Logger) -> dict:
    prepare = compile_function(
        "prepare_telegram_image_delivery",
        {"Image": Image, "ImageOps": ImageOps, "io": io},
    )
    return {
        "asyncio": asyncio,
        "html": html,
        "io": io,
        "json": json,
        "time": time,
        "logger": logger,
        "sanitize_log_text": str,
        "get_user_language": lambda _uid: "vi",
        "normalize_image_editor_overlay_position": lambda value, default: value or default,
        "acquire_image_action_lock": lambda *_args: True,
        "release_image_action_lock": lambda *_args, **_kwargs: None,
        "safe_edit_query_message": lambda *_args, **_kwargs: None,
        "image_action_waiting_text": lambda _lang: "Dang xu ly",
        "telegram_photo_file_bytes": lambda _context, _file_id: asyncio.sleep(0, result=image_payload()),
        "process_image_local_editor_bytes": lambda *args, **kwargs: (
            True,
            image_payload(),
            "64x64",
            "brightness_only",
        ),
        "prepare_telegram_image_delivery": prepare,
        "image_editor_preset_label": lambda preset, _lang: preset,
        "image_editor_result_keyboard": lambda _lang: "result-keyboard",
        "image_editor_start_keyboard": lambda _lang: "start-keyboard",
        "image_action_locked_text": lambda _lang: "locked",
        "save_image_tool_result": lambda _uid, _kind, payload: saved.append(dict(payload)),
        "set_image_menu_pending": lambda *_args, **_kwargs: None,
    }


async def verify_image_delivery(photo_timeout: bool) -> None:
    bot = ImageBot(photo_timeout=photo_timeout)
    message = Message()
    saved: list[dict] = []
    logger = Logger()
    handler = compile_function("send_local_edited_image", image_namespace(bot, saved, logger))
    update = SimpleNamespace(
        message=message,
        callback_query=None,
        effective_user=SimpleNamespace(id=42),
    )
    context = SimpleNamespace(bot=bot)

    result = await handler(
        update,
        context,
        {"file_id": "source-photo"},
        preset="brightness_only",
        settings={"brightness": 2.0},
    )

    assert result is True
    assert len(bot.photos) == 1
    assert bot.photos[0]["read_timeout"] == 60
    assert bot.photos[0]["write_timeout"] == 60
    assert bot.photos[0]["connect_timeout"] == 30
    assert bot.photos[0]["pool_timeout"] == 30
    assert len(bot.documents) == (1 if photo_timeout else 0)
    assert len(saved) == 1
    assert saved[0]["brightness_percent"] == 200
    all_text = "\n".join(item["text"] for item in message.replies + bot.messages)
    assert "chua xu ly duoc anh" not in all_text.lower()


class VideoMessage(Message):
    video = SimpleNamespace(file_id="video-file", file_size=2048, duration=4, file_name="clip.mp4")
    document = None


async def verify_video_upload_routes_once() -> None:
    state = video_edit_state_machine.start_lane("manual_edit")
    saved: dict = dict(state)
    replies: list[dict] = []

    def save(_uid: int, value: dict) -> dict:
        saved.clear()
        saved.update(value)
        return dict(saved)

    def keyboard_builder(rows):
        assert all(len(row) == 2 for row in rows)
        return rows

    manual_keyboard = compile_function(
        "video_local_manual_options_keyboard",
        {
            "video_scene3_keyboard": keyboard_builder,
            "ui_text": lambda _lang, key: "Quay lai" if key.endswith("back") else "Menu chinh",
        },
    )
    metadata = {
        "ok": True,
        "duration": 4.0,
        "duration_ms": 4000,
        "width": 720,
        "height": 1280,
        "fps": 30.0,
        "has_audio": True,
        "bytes": 2048,
    }
    logger = Logger()
    namespace = {
        "video_edit_state_machine": video_edit_state_machine,
        "video_local_editing": video_local_editing,
        "get_video_editor_pending": lambda _uid: dict(saved),
        "save_video_edit_canonical_state": save,
        "clear_video_editor_competing_video_states": lambda *_args: None,
        "get_user_language": lambda _uid: "vi",
        "safe_int": lambda value, default=0: int(value or default),
        "video_editor_source_from_update": lambda _update: {
            "source_file_id": "video-file",
            "source_file_name": "clip.mp4",
            "source_file_size": 2048,
        },
        "inspect_video_editor_source": lambda *_args: asyncio.sleep(0, result=dict(metadata)),
        "video_local_validation": SimpleNamespace(
            LocalVideoValidationError=RuntimeError,
            safe_display_filename=lambda name: name,
        ),
        "logger": logger,
        "sanitize_log_text": str,
        "cache_recent_media_state": lambda _update: None,
        "video_local_manual_options_text": lambda _state, _lang: "Chon thao tac chinh sua",
        "video_local_manual_options_keyboard": manual_keyboard,
    }
    handler = compile_function("handle_video_editor_pending_upload", namespace)

    class RuntimeMessage(VideoMessage):
        async def reply_text(self, text: str, **kwargs):
            replies.append({"text": text, **kwargs})
            return SimpleNamespace(message_id=len(replies))

    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=42),
        message=RuntimeMessage(),
    )
    result = await handler(update, SimpleNamespace(user_data={}))

    assert result is True
    assert saved["edit_mode"] == "manual_edit"
    assert saved["awaiting_media"] is False
    assert saved["source_file_id"] == "video-file"
    assert len(replies) == 1
    assert replies[0]["text"] == "Chon thao tac chinh sua"
    assert all(len(row) == 2 for row in replies[0]["reply_markup"])


class ImageResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self) -> dict:
        return dict(self._payload)


class ImageClient:
    responses: list[ImageResponse] = []
    payloads: list[dict] = []

    def __init__(self, **_kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def post(self, _url: str, **kwargs):
        self.payloads.append(dict(kwargs["json"]))
        return self.responses.pop(0)


async def verify_image_model_fallback() -> None:
    ImageClient.responses = [
        ImageResponse(503, {"error": {"message": "no available channel"}}),
        ImageResponse(200, {"data": [{"url": "https://example.test/storyboard.jpg"}]}),
    ]
    ImageClient.payloads = []
    fallback_namespace: dict = {}
    compile_function("shopaikey_image_model_invalid_error", fallback_namespace)
    compile_function("shopaikey_classify_error", fallback_namespace)
    allows_fallback = compile_function("shopaikey_image_allows_model_fallback", fallback_namespace)
    assert allows_fallback(503, "no available channel") is True
    assert allows_fallback(401, "invalid api key") is False

    namespace = {
        "time": time,
        "httpx": SimpleNamespace(AsyncClient=ImageClient),
        "SHOPAIKEY_API_KEY": "test-key",
        "SHOPAIKEY_IMAGE_MODEL_PRIMARY": "nano-banana",
        "SHOPAIKEY_IMAGE_MODEL": "nano-banana",
        "SHOPAIKEY_IMAGE_MODEL_FALLBACKS": "nano-banana-2,nano-banana-pro",
        "SHOPAIKEY_IMAGE_URL": "https://example.test/images",
        "SHOPAIKEY_GOOGLE_IMAGE_PAYLOAD_MODE": "size",
        "IMAGE_RATIO_UNSUPPORTED_MESSAGE": "unsupported",
        "shopaikey_image_model_sequence": lambda _primary, _fallbacks: ["nano-banana", "nano-banana-2"],
        "infer_image_aspect_ratio_from_prompt": lambda _prompt, default: default,
        "normalize_image_aspect_ratio": lambda ratio: ratio,
        "get_image_size_for_ratio": lambda ratio, _tier, _provider: {
            "provider_supported": True,
            "size_string": "1024x1024",
            "ratio": ratio,
        },
        "build_shopaikey_google_image_payload": lambda prompt, model, ratio: {
            "prompt": prompt,
            "model": model,
            "size": ratio,
        },
        "shopaikey_image_output_from_payload": lambda payload: {
            "image_url": payload.get("data", [{}])[0].get("url", ""),
            "b64_json": "",
            "size": "",
        },
        "shopaikey_provider_error_from_payload": lambda payload: (
            "",
            str(payload.get("error", {}).get("message", "")),
        ),
        "shopaikey_sanitize_error": str,
        "shopaikey_classify_error": fallback_namespace["shopaikey_classify_error"],
        "shopaikey_image_allows_model_fallback": allows_fallback,
    }
    generate = compile_function("shopaikey_image_generate", namespace)
    result = await generate("storyboard prompt", aspect_ratio="1:1")

    assert result["status"] == "PASS"
    assert result["final_model"] == "nano-banana-2"
    assert result["models_tried"] == ["nano-banana", "nano-banana-2"]
    assert result["fallback_used"] is True
    assert [payload["model"] for payload in ImageClient.payloads] == ["nano-banana", "nano-banana-2"]


async def main() -> None:
    await verify_image_delivery(photo_timeout=False)
    await verify_image_delivery(photo_timeout=True)
    await verify_video_upload_routes_once()
    await verify_image_model_fallback()
    print("media_edit_live_recovery: PASS (4 checks)")


if __name__ == "__main__":
    asyncio.run(main())
