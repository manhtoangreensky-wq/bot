"""Foreign progress buttons must stop before downstream recovery/delivery or display."""
import asyncio
from copy import deepcopy
from pathlib import Path
import re
import runpy
from types import SimpleNamespace

import pytest
from services import product_progress_status


F = runpy.run_path(str(Path(__file__).with_name("test_voice_settings_input_back.py")))


def _run(product="subdub", *, owner="902", admin=False, nested=False, blank_root=False, requested="job-1", missing=False):
    job = {} if missing else {"job_id": "job-1", "internal_job_id": "job-1", "public_code": "alias-1", "user_id": owner,
                             "feature": "subtitle_dub" if product == "subdub" else product, "status": "processing"}
    if nested:
        job["debug_job"] = {"user_id": job.pop("user_id")}
        if blank_root:
            job["user_id"] = "  "
    effects = []

    def merged(value, **kwargs):
        return {**dict(value.get("debug_job") or {}), **value, **kwargs}

    async def render(_query, text, **kwargs):
        effects.append(("render", text))

    async def recover(_query, _ctx, _key, value, _lang):
        effects.append(("recover", value.get("user_id")))

    async def music(_query, _ctx, **kwargs):
        effects.append(("music", kwargs["user_id"]))
        return {"job": deepcopy(job)}

    ns = {
        "Update": object, "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "InlineKeyboardButton": F["Button"], "InlineKeyboardMarkup": F["Markup"],
        "product_progress_status": product_progress_status,
        "get_engine_async_job": lambda _id: deepcopy(job),
        "subdub_lookup_variants": lambda value: {value},
        "subdub_merge_debug_job": merged,
        "subdub_job_identifier_variants": lambda value: {value.get("job_id"), value.get("public_code")},
        "is_admin_user": lambda _uid: admin,
        "SUBTITLE_DUB_PIPELINE_JOBS": {}, "SUBDUB_TERMINAL_STATES": {"delivered"},
        "subdub_job_timestamp": lambda _value: 0,
        "list_engine_async_jobs": lambda *_args, **kwargs: [deepcopy(job)] if requested == "latest" and job else [],
        "subdub_engine_async_persisted_scan": lambda **kwargs: [],
        "resolve_progress_product_type": lambda _id, canonical, _job: canonical,
        "user_ui_lang": lambda _uid: "vi",
        "subdub_persisted_job_registry_present": lambda _job: False,
        "subdub_rehydrate_terminal_job": lambda value: ("state", value),
        "subdub_should_terminalize_interrupted_persisted_job": lambda *_args, **kwargs: False,
        "subdub_terminal_delivery_evidence": lambda _job: False,
        "subdub_recover_existing_mp4_delivery": recover,
        "maybe_deliver_music_progress_job": music,
        "music_progress_job_lookup_found": lambda *_args: bool(job),
        "frame_video_job_for_user": lambda *_args: deepcopy(job),
        "product_progress_status_from_job_text": lambda _type, value, _id, _lang: "status owner=" + str(value.get("user_id") or "none"),
        "safe_edit_or_send": render,
        "progress_auto_refresh_register_message": lambda *_args, **kwargs: effects.append(("refresh", kwargs.get("user_id"))),
    }
    for name in ("subdub_progress_job_for_user", "product_progress_status_keyboard", "handle_product_progress_callback"):
        exec(compile("from __future__ import annotations\n" + F["_source"](name), f"bot.py:{name}", "exec"), ns)
    routes = []
    ns.update(tg_app=SimpleNamespace(add_handler=routes.append),
              CallbackQueryHandler=lambda callback, pattern: (callback, re.compile(pattern)))
    registrations = re.findall(r"(?m)^\s*tg_app\.add_handler\(CallbackQueryHandler\(handle_product_progress_callback,.*$", F["SOURCE"])
    assert len(registrations) == 1
    exec(registrations[0].strip(), ns)
    callback, pattern = routes[0]
    markup = ns["product_progress_status_keyboard"](product, requested, "vi")
    data = next(b.callback_data for row in markup.inline_keyboard for b in row if str(b.callback_data).startswith("progress|status|"))
    assert pattern.search(data)
    query = F["Query"](data)
    query.from_user = SimpleNamespace(id=901)
    asyncio.run(callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    return query, effects


@pytest.mark.parametrize("product", ["subdub", "music_bg", "frame_video"])
@pytest.mark.parametrize("owner", [902, "902", " 902 "])
def test_foreign_job_cannot_reach_recovery_poll_delivery_status_or_refresh(product, owner):
    query, effects = _run(product, owner=owner)
    assert len(query.answers) == 1
    assert not any(kind in {"recover", "music", "refresh"} for kind, _value in effects)
    assert len(effects) == 1 and effects[0][0] == "render"
    assert "902" not in effects[0][1]


@pytest.mark.parametrize("product", ["subdub", "music_bg", "frame_video"])
@pytest.mark.parametrize("blank_root", [False, True])
def test_nested_debug_owner_rejection_does_not_restore_raw_job(product, blank_root):
    query, effects = _run(product, nested=True, blank_root=blank_root)
    assert len(query.answers) == 1
    assert not any(kind in {"recover", "music", "refresh"} for kind, _value in effects)
    assert all("902" not in str(value) for _kind, value in effects)


@pytest.mark.parametrize("product", ["subdub", "music_bg", "frame_video"])
@pytest.mark.parametrize("admin", [False, True])
def test_owned_or_authorized_admin_progress_keeps_existing_downstream_path(product, admin):
    query, effects = _run(product, owner="902" if admin else "901", admin=admin)
    assert len(query.answers) == 1
    assert any(kind == "refresh" for kind, _value in effects)
    assert any(kind == "render" for kind, _value in effects)
    if product == "subdub":
        assert any(kind == "recover" for kind, _value in effects)
    if product == "music_bg":
        assert any(kind == "music" for kind, _value in effects)


@pytest.mark.parametrize("requested", ["job-1", "alias-1", "latest"])
def test_owned_subdub_identifier_variants_and_latest_keep_lookup(requested):
    _query, effects = _run(owner="901", requested=requested)
    assert any(kind == "recover" for kind, _value in effects)


def test_missing_subdub_job_renders_missing_status_without_recovery():
    _query, effects = _run(missing=True)
    assert not any(kind == "recover" for kind, _value in effects)
    assert ("render", "status owner=none") in effects


def test_legacy_ownerless_subdub_policy_is_not_changed():
    _query, effects = _run(owner="")
    assert any(kind == "recover" for kind, _value in effects)


@pytest.mark.parametrize("admin", [False, True])
def test_owned_or_admin_nested_subdub_snapshot_remains_accessible(admin):
    _query, effects = _run(owner="902" if admin else "901", nested=True, admin=admin)
    assert any(kind == "recover" for kind, _value in effects)
    assert any(kind == "refresh" for kind, _value in effects)
