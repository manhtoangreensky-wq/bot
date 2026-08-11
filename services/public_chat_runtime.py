"""Orchestration seams for isolated public Free/Pro chat."""

from __future__ import annotations

import asyncio
import base64
import inspect
import sqlite3
import time
from dataclasses import dataclass, replace
from typing import Any, Callable, Iterable, Mapping, Sequence

from providers.gemini_public_chat_provider import GEMINI_FREE_MODEL, generate_public_chat_text
try:
    from providers.key4u_provider import KEY4U_PUBLIC_CHAT_COMPLETIONS_URL
except ImportError:  # current main provider before its narrow adapter extension
    KEY4U_PUBLIC_CHAT_COMPLETIONS_URL = "https://api.key4u.vn/v1/chat/completions"
from services.chat_pro_pricing import (
    CLAUDE_OPUS_MODEL,
    ClaudeOpusPricing,
    OpusUsage,
    TokenUsage,
    calculate_actual_xu,
    opus_price_per_thousand_labels,
    public_chat_customer_pricing,
    reserve_xu,
)
from services.public_chat_media import (
    MediaInput,
    PublicChatAttachment,
    attachment_memory_label,
    attachment_reservation_tokens,
    capability_decision,
    validate_text_output,
)
from services.public_chat_store import (
    FREE_DAILY_LIMIT,
    PublicChatStore,
    complete_free_request,
    ensure_schema,
    load_public_context,
    load_pending_public_chat_delivery,
    purge_expired_public_turns,
    reconcile_stale_pro_reservations,
    refund_pro_request,
    release_request,
    reserve_free_request,
    reserve_pro_request,
    settle_pro_request,
)


PUBLIC_CHAT_MAX_OUTPUT_TOKENS = 1_200
PUBLIC_CHAT_MAX_TEXT_CHARS = 6_000
_LABELS = opus_price_per_thousand_labels()
CHAT_PRO_RATE_LABEL = f"{_LABELS['input']}/{_LABELS['output']} Xu/1K"


def _default_pricing() -> ClaudeOpusPricing:
    return public_chat_customer_pricing()


@dataclass(frozen=True)
class PublicChatRequest:
    account_id: str
    chat_id: str
    source_message_id: str
    mode: str = "free"
    prompt: str = ""
    role: str = "user"
    media: tuple[MediaInput, ...] = ()
    estimated_input_tokens: int = 0
    max_output_tokens: int = PUBLIC_CHAT_MAX_OUTPUT_TOKENS


async def _maybe_call(target: Any, *args: Any, **kwargs: Any) -> Any:
    if callable(target):
        result = target(*args, **kwargs)
    elif hasattr(target, "generate") and callable(target.generate):
        result = target.generate(*args, **kwargs)
    else:
        raise TypeError("provider is not callable")
    return await result if inspect.isawaitable(result) else result


async def _wallet(target: Any, method: str, *args: Any) -> Any:
    function = getattr(target, method, None)
    if not callable(function):
        raise TypeError(f"wallet.{method} is required")
    result = function(*args)
    return await result if inspect.isawaitable(result) else result


def _usage_from_result(result: Mapping[str, Any]) -> OpusUsage | None:
    raw = result.get("usage")
    usage = raw if isinstance(raw, Mapping) else {}

    def first(*keys: str, default: Any = None) -> Any:
        for source in (result, usage):
            for key in keys:
                if key in source:
                    return source[key]
        return default

    input_tokens = first("input_tokens", "prompt_tokens")
    output_tokens = first("output_tokens", "completion_tokens")
    cache = first("cache_read_tokens", "cache_read_input_tokens", default=0)
    includes_cache = first("input_tokens_include_cache", default=False)
    if input_tokens is None or output_tokens is None:
        return None
    if not isinstance(includes_cache, bool):
        return None
    try:
        normalized = OpusUsage(input_tokens, output_tokens, cache)
    except (TypeError, ValueError):
        return None
    if includes_cache and normalized.cache_read_tokens > normalized.input_tokens:
        return None
    parsed = OpusUsage(
        normalized.input_tokens - normalized.cache_read_tokens
        if includes_cache
        else normalized.input_tokens,
        normalized.output_tokens,
        normalized.cache_read_tokens,
    )
    if parsed.output_tokens <= 0 or parsed.input_tokens + parsed.cache_read_tokens <= 0:
        return None
    return parsed


class PublicChatRuntime:
    """Provider/wallet dependency-injected lifecycle used by focused tests."""

    def __init__(self, *, store: PublicChatStore, free_provider: Any = None, pro_provider: Any = None, wallet: Any = None, pricing: ClaudeOpusPricing | None = None):
        self.store = store
        self.free_provider = free_provider
        self.pro_provider = pro_provider
        self.wallet = wallet
        self.pricing = pricing or _default_pricing()

    async def _free(self, request: PublicChatRequest) -> dict[str, Any]:
        decision = self.store.reserve_free_request(
            request.account_id,
            request.chat_id,
            request.source_message_id,
            is_admin=request.role in {"admin", "owner"},
        )
        if decision.duplicate:
            return decision.result or {"ok": False, "status": "DUPLICATE_IN_PROGRESS", "request_id": decision.request_id, "provider_calls": 0}
        if decision.status == "quota_exhausted":
            return {"ok": False, "status": "FREE_QUOTA_EXHAUSTED", "request_id": decision.request_id, "provider_calls": 0}
        try:
            result = await _maybe_call(self.free_provider, request, model=GEMINI_FREE_MODEL)
        except asyncio.CancelledError:
            failure = {"ok": False, "status": "CANCELLED", "request_id": decision.request_id, "provider_calls": 1}
            self.store.fail_free(decision.request_id, failure, "cancelled")
            raise
        except Exception:
            result = {"ok": False, "status": "PROVIDER_FAILURE"}
        text = result.get("text") if isinstance(result, Mapping) else ""
        valid = isinstance(result, Mapping) and bool(result.get("ok")) and str(result.get("model") or GEMINI_FREE_MODEL) == GEMINI_FREE_MODEL
        try:
            output = validate_text_output(text) if valid else ""
        except Exception:
            output = ""
        if not output:
            failure = {"ok": False, "status": "PROVIDER_FAILURE", "request_id": decision.request_id, "provider_calls": 1}
            self.store.fail_free(decision.request_id, failure, str((result or {}).get("status") if isinstance(result, Mapping) else "provider_failure"))
            return failure
        answer = {"ok": True, "status": "ok", "mode": "free", "text": output, "model": GEMINI_FREE_MODEL, "request_id": decision.request_id, "provider_calls": 1}
        self.store.finish_free(decision.request_id, prompt=request.prompt, answer=output, result=answer)
        return answer

    async def _pro(self, request: PublicChatRequest) -> dict[str, Any]:
        decision = self.store.begin_pro(request.account_id, request.chat_id, request.source_message_id, is_admin=request.role in {"admin", "owner"})
        if decision.duplicate:
            return decision.result or {"ok": False, "status": "DUPLICATE_IN_PROGRESS", "request_id": decision.request_id, "provider_calls": 0}
        is_free = request.role in {"admin", "owner"}
        estimate_usage = TokenUsage(max(0, int(request.estimated_input_tokens or len(request.prompt.encode("utf-8")))), max(0, int(request.max_output_tokens or PUBLIC_CHAT_MAX_OUTPUT_TOKENS)))
        reserve_amount = 0 if is_free else calculate_actual_xu(estimate_usage, self.pricing)
        wallet_reservation_id = ""
        if not is_free:
            if self.wallet is None:
                failure = {"ok": False, "status": "INSUFFICIENT_XU", "request_id": decision.request_id, "provider_calls": 0}
                self.store.fail_pro(decision.request_id, result=failure, reason="wallet_unavailable")
                return failure
            try:
                balance = await _wallet(self.wallet, "get_balance", request.account_id)
                if isinstance(balance, Mapping):
                    balance = balance.get("balance_xu", balance.get("credits", 0))
                if int(balance or 0) < reserve_amount:
                    failure = {"ok": False, "status": "INSUFFICIENT_XU", "request_id": decision.request_id, "provider_calls": 0}
                    self.store.fail_pro(decision.request_id, result=failure, reason="insufficient_xu")
                    return failure
                reservation = await _wallet(self.wallet, "reserve", request.account_id, reserve_amount, decision.request_id)
                if not isinstance(reservation, Mapping) or not reservation.get("ok"):
                    failure = {"ok": False, "status": "INSUFFICIENT_XU", "request_id": decision.request_id, "provider_calls": 0}
                    self.store.fail_pro(decision.request_id, result=failure, reason="reservation_failed")
                    return failure
                wallet_reservation_id = str(reservation.get("reservation_id") or decision.request_id)
                self.store.mark_pro_reserved(decision.request_id, reserve_amount, wallet_reservation_id)
            except Exception:
                failure = {"ok": False, "status": "INSUFFICIENT_XU", "request_id": decision.request_id, "provider_calls": 0}
                self.store.fail_pro(decision.request_id, result=failure, reason="reservation_failed")
                return failure
        else:
            self.store.mark_pro_reserved(decision.request_id, 0, "admin-free")
        try:
            result = await _maybe_call(self.pro_provider, request, model=CLAUDE_OPUS_MODEL)
        except asyncio.CancelledError:
            if not is_free and self.wallet is not None and wallet_reservation_id:
                try:
                    await _wallet(self.wallet, "release", request.account_id, wallet_reservation_id, decision.request_id)
                except Exception:
                    pass
            failure = {"ok": False, "status": "CANCELLED", "request_id": decision.request_id, "provider_calls": 1}
            self.store.fail_pro(decision.request_id, result=failure, reason="cancelled")
            raise
        except Exception:
            result = {"ok": False, "status": "PROVIDER_FAILURE"}
        text = result.get("text") if isinstance(result, Mapping) else ""
        usage = _usage_from_result(result) if isinstance(result, Mapping) else None
        valid = isinstance(result, Mapping) and bool(result.get("ok")) and str(result.get("model") or CLAUDE_OPUS_MODEL) == CLAUDE_OPUS_MODEL and usage is not None
        try:
            output = validate_text_output(text) if valid else ""
        except Exception:
            output = ""
        if not output:
            failure = {"ok": False, "status": "PROVIDER_FAILURE", "request_id": decision.request_id, "provider_calls": 1}
            if not is_free and self.wallet is not None and wallet_reservation_id:
                try:
                    await _wallet(self.wallet, "release", request.account_id, wallet_reservation_id, decision.request_id)
                except Exception:
                    pass
            self.store.fail_pro(decision.request_id, result=failure, reason=str((result or {}).get("status") if isinstance(result, Mapping) else "provider_failure"))
            return failure
        actual = 0 if is_free else calculate_actual_xu(usage, self.pricing)  # type: ignore[arg-type]
        if not is_free and self.wallet is not None:
            try:
                settled = await _wallet(self.wallet, "settle", request.account_id, wallet_reservation_id, actual, decision.request_id)
                if not isinstance(settled, Mapping) or not settled.get("ok"):
                    raise RuntimeError("settlement_failed")
            except Exception:
                try:
                    await _wallet(self.wallet, "release", request.account_id, wallet_reservation_id, decision.request_id)
                except Exception:
                    pass
                failure = {"ok": False, "status": "PROVIDER_FAILURE", "request_id": decision.request_id, "provider_calls": 1}
                self.store.fail_pro(decision.request_id, result=failure, reason="settlement_failed")
                return failure
        answer = {"ok": True, "status": "ok", "mode": "pro", "text": output, "model": CLAUDE_OPUS_MODEL, "request_id": decision.request_id, "provider_calls": 1, "cost_xu": actual, "provider_request_id": str(result.get("provider_request_id") or "")}
        self.store.finish_pro(decision.request_id, result=answer, usage=usage or OpusUsage(), cost_xu=actual, answer=output, prompt=request.prompt, provider_request_id=str(result.get("provider_request_id") or ""))
        return answer

    async def run(self, request: PublicChatRequest) -> dict[str, Any]:
        mode = "pro" if str(request.mode or "free").lower() == "pro" else "free"
        normalized = request if request.mode == mode else replace(request, mode=mode)
        return await (self._pro(normalized) if mode == "pro" else self._free(normalized))


def public_chat_menu_rows(lang: str = "vi") -> list[list[str]]:
    value = str(lang or "vi").lower()
    if value == "en":
        return [["🆓 Free tools"], [f"💎 Chat Pro • {CHAT_PRO_RATE_LABEL}", "👤 Account"]]
    if value == "zh":
        return [["🆓 免费工具"], [f"💎 Pro 聊天 • {CHAT_PRO_RATE_LABEL}", "👤 我的账户"]]
    return [["🆓 Công cụ miễn phí"], [f"💎 Chat Pro • {CHAT_PRO_RATE_LABEL}", "👤 Tài khoản"]]


def toggle_public_chat_mode(current: str) -> str:
    return "pro" if str(current or "free").lower() != "pro" else "free"


def resolve_public_chat_mode_action(action: str, current: str) -> str:
    """Resolve menu callbacks to a persistent mode; explicit actions are idempotent."""
    selected = str(action or "").strip().lower()
    if selected == "chat_pro_on":
        return "pro"
    if selected == "chat_pro_off":
        return "normal"
    if selected == "chat_pro_toggle":
        return "normal" if str(current or "normal").strip().lower() in {"pro", "deep"} else "pro"
    raise ValueError("unsupported public chat mode action")


def public_chat_system_prompt(lang: str = "vi") -> str:
    language = "Vietnamese" if str(lang or "vi").lower() == "vi" else "the user's latest language"
    return f"You are TOAN AAS public chat. Return text only and reply in {language}. Never switch into another product flow."


def split_public_chat_text(text: str, limit: int = 3900) -> list[str]:
    value = str(text or "").strip()
    bounded = max(256, min(int(limit or 3900), 4096))
    return [value[index:index + bounded] for index in range(0, len(value), bounded)] if value else []


def _provider_messages(context: Mapping[str, Any], text: str) -> list[dict[str, Any]]:
    messages = [{"role": str(turn.get("role")), "content": str(turn.get("content"))[:PUBLIC_CHAT_MAX_TEXT_CHARS]} for turn in list(context.get("turns") or []) if isinstance(turn, Mapping) and str(turn.get("role")) in {"user", "assistant"} and str(turn.get("content") or "").strip()]
    current = str(text or "").strip()[:PUBLIC_CHAT_MAX_TEXT_CHARS]
    if not current:
        raise ValueError("text is required")
    messages.append({"role": "user", "content": current})
    if messages and messages[0]["role"] != "user":
        messages = messages[1:]
    for index, item in enumerate(messages):
        if item["role"] != ("user" if index % 2 == 0 else "assistant"):
            raise ValueError("public context is not chronological")
    return messages


def _memory_user_content(text: str, attachments: Sequence[PublicChatAttachment]) -> str:
    labels = [attachment_memory_label(item) for item in attachments]
    return str(text or "").strip() + ("\n[attachments: " + ", ".join(labels) + "]" if labels else "")


def _opus_messages(messages: Sequence[dict[str, Any]], attachments: Sequence[PublicChatAttachment]) -> list[dict[str, Any]]:
    result = [dict(item) for item in messages]
    images = [item for item in attachments if item.kind == "image"]
    if not images:
        return result
    parts = [{"type": "text", "text": str(result[-1].get("content") or "")}]
    for item in images:
        raw = item.temporary_path.read_bytes()
        if len(raw) != item.actual_bytes:
            raise ValueError("attachment changed")
        parts.append({"type": "image_url", "image_url": {"url": f"data:{item.mime_type};base64,{base64.b64encode(raw).decode('ascii')}"}})
    result[-1] = {"role": "user", "content": parts}
    return result


def _credit_event(callback: Callable[..., Any] | None, conn: sqlite3.Connection, user_id: Any, delta: int, event_type: str, ref_id: str, note: str) -> None:
    if callback is not None and int(delta or 0):
        callback(conn, user_id, int(delta), event_type, ref_id, note)


def _compensate_pro_request(*, conn: sqlite3.Connection, owner_id: Any, request_id: str, reason: str, note: str, record_credit_event: Callable[..., Any] | None) -> dict[str, Any]:
    conn.rollback()
    refunded = refund_pro_request(conn, request_id, reason=reason)
    if refunded.get("refunded"):
        try:
            _credit_event(record_credit_event, conn, owner_id, int(refunded.get("refunded_xu") or 0), "public_chat_refund", request_id, note)
        except Exception:
            pass
    conn.commit()
    return refunded


async def _call_provider(*, mode: str, gemini_client: Any, key4u_provider: Any, system_prompt: str, messages: list[dict[str, Any]], attachments: Sequence[PublicChatAttachment]) -> dict[str, Any]:
    if mode == "free":
        return await generate_public_chat_text(gemini_client, system_prompt=system_prompt, messages=messages, attachments=attachments, max_output_tokens=PUBLIC_CHAT_MAX_OUTPUT_TOKENS)
    if key4u_provider is None:
        return {"ok": False, "status": "unavailable", "text": ""}
    opus_messages = _opus_messages(messages, attachments)
    if str(system_prompt or "").strip():
        opus_messages.insert(0, {"role": "system", "content": str(system_prompt).strip()})
    pdfs = [item for item in attachments if item.kind == "pdf"]
    if pdfs:
        if len(pdfs) != 1 or any(item.kind not in {"pdf", "image"} for item in attachments):
            return {"ok": False, "status": "unsupported", "text": ""}
        document_call = getattr(key4u_provider, "document_completion", None)
        if not callable(document_call):
            return {"ok": False, "status": "unsupported", "text": ""}
        return await document_call(messages=opus_messages, pdf_bytes=pdfs[0].temporary_path.read_bytes(), model=CLAUDE_OPUS_MODEL, max_tokens=PUBLIC_CHAT_MAX_OUTPUT_TOKENS, require_usage=True)
    public_call = getattr(key4u_provider, "public_chat_completion", None)
    if callable(public_call):
        return await public_call(messages=opus_messages, max_tokens=PUBLIC_CHAT_MAX_OUTPUT_TOKENS)
    # Compatibility seam for the injected/legacy Key4U adapter.  Supplying
    # structured messages and the exact Opus pin selects the same public route;
    # this is not a provider or model fallback.
    compatible_call = getattr(key4u_provider, "chat_completion", None)
    if callable(compatible_call):
        return await compatible_call(
            messages=opus_messages,
            model=CLAUDE_OPUS_MODEL,
            max_tokens=PUBLIC_CHAT_MAX_OUTPUT_TOKENS,
            require_usage=True,
        )
    return {"ok": False, "status": "unavailable", "text": ""}


async def run_public_chat_request(*, conn: sqlite3.Connection, owner_id: Any, chat_id: Any, source_message_id: Any, text: str, mode: str = "free", system_prompt: str | None = None, lang: str = "vi", gemini_client: Any = None, key4u_provider: Any = None, attachments: Iterable[PublicChatAttachment] = (), is_admin: bool = False, record_credit_event: Callable[..., Any] | None = None, now: Any = None) -> dict[str, Any]:
    selected = "pro" if str(mode or "free").lower() == "pro" else "free"
    items = tuple(attachments or ())
    decision = capability_decision(selected, [item.kind for item in items])
    if decision.get("route") not in {"gemini", "opus"}:
        return {"ok": False, "status": "unsupported", "mode": selected, "provider_calls": 0}
    try:
        messages = _provider_messages(load_public_context(conn, owner_id, chat_id, now=now), text)
    except ValueError:
        return {"ok": False, "status": "invalid_input", "mode": selected, "provider_calls": 0}
    purge_expired_public_turns(conn, now=now)
    conn.commit()
    stale_refunds = reconcile_stale_pro_reservations(conn, owner_id, now=now)
    for stale_refund in stale_refunds:
        try:
            _credit_event(record_credit_event, conn, owner_id, int(stale_refund.get("refunded_xu") or 0), "public_chat_refund", str(stale_refund.get("request_id") or ""), "stale Pro reservation")
        except Exception:
            pass
    conn.commit()
    if selected == "free":
        request = reserve_free_request(conn, owner_id=owner_id, chat_id=chat_id, source_message_id=source_message_id, now=now, is_admin=is_admin)
        conn.commit()
        if request.get("duplicate"):
            pending = load_pending_public_chat_delivery(
                conn,
                owner_id=owner_id,
                chat_id=chat_id,
                request_id=request.get("request_id"),
                now=now,
            )
            if pending is not None:
                return {**pending, "replay": True, "provider_calls": 0}
            return {"ok": False, "status": "duplicate", "mode": selected, "request_id": request.get("request_id"), "provider_calls": 0}
        if not request.get("accepted"):
            return {"ok": False, "status": "free_quota_exhausted", "mode": selected, "request_id": request.get("request_id"), "provider_calls": 0}
    else:
        try:
            reserve = reserve_xu(messages, PUBLIC_CHAT_MAX_OUTPUT_TOKENS, extra_input_tokens=attachment_reservation_tokens(items))
        except (TypeError, ValueError):
            return {"ok": False, "status": "invalid_input", "mode": selected, "provider_calls": 0}
        try:
            request = reserve_pro_request(conn, owner_id=owner_id, chat_id=chat_id, source_message_id=source_message_id, reserved_xu=reserve, now=now, is_admin=is_admin)
            if request.get("accepted") and not request.get("duplicate"):
                _credit_event(record_credit_event, conn, owner_id, -int(request.get("reserved_xu") or 0), "public_chat_reserve", request["request_id"], f"model={CLAUDE_OPUS_MODEL}")
            conn.commit()
        except Exception:
            conn.rollback()
            return {"ok": False, "status": "provider_failure", "mode": selected, "provider_calls": 0}
        if request.get("duplicate"):
            pending = load_pending_public_chat_delivery(
                conn,
                owner_id=owner_id,
                chat_id=chat_id,
                request_id=request.get("request_id"),
                now=now,
            )
            if pending is not None:
                return {**pending, "replay": True, "provider_calls": 0}
            return {"ok": False, "status": "duplicate", "mode": selected, "request_id": request.get("request_id"), "provider_calls": 0}
        if not request.get("accepted"):
            return {"ok": False, "status": "insufficient_balance", "mode": selected, "request_id": request.get("request_id"), "provider_calls": 0}
    try:
        provider_result = await _call_provider(mode=selected, gemini_client=gemini_client, key4u_provider=key4u_provider, system_prompt=system_prompt or public_chat_system_prompt(lang), messages=messages, attachments=items)
    except asyncio.CancelledError:
        if selected == "free":
            release_request(conn, request["request_id"], reason="cancelled")
            conn.commit()
        else:
            _compensate_pro_request(conn=conn, owner_id=owner_id, request_id=request["request_id"], reason="cancelled", note="provider cancellation", record_credit_event=record_credit_event)
        raise
    except Exception:
        provider_result = {"ok": False, "status": "provider_error", "text": ""}
    raw_output = provider_result.get("text") if isinstance(provider_result, Mapping) else None
    output = raw_output.strip() if isinstance(raw_output, str) else ""
    if not isinstance(provider_result, Mapping) or not provider_result.get("ok") or not output:
        if selected == "free":
            release_request(conn, request["request_id"], reason=str(provider_result.get("status") if isinstance(provider_result, Mapping) else "provider_failure"))
        else:
            _compensate_pro_request(conn=conn, owner_id=owner_id, request_id=request["request_id"], reason=str(provider_result.get("status") if isinstance(provider_result, Mapping) else "provider_failure"), note="provider failure", record_credit_event=record_credit_event)
        if selected == "free":
            conn.commit()
        return {"ok": False, "status": "provider_failure", "mode": selected, "request_id": request["request_id"], "provider_calls": 1}
    if selected == "free":
        try:
            completed = complete_free_request(conn, request["request_id"], user_content=_memory_user_content(text, items), assistant_content=output, now=time.time())
            conn.commit()
        except Exception:
            conn.rollback()
            release_request(conn, request["request_id"], reason="persistence_failed")
            conn.commit()
            return {"ok": False, "status": "provider_failure", "mode": selected, "request_id": request["request_id"], "provider_calls": 1}
        if not completed.get("consumed"):
            return {"ok": False, "status": "duplicate", "mode": selected, "request_id": request["request_id"], "provider_calls": 1}
        delivery = completed.get("delivery")
        if not isinstance(delivery, Mapping):
            delivery = load_pending_public_chat_delivery(
                conn,
                owner_id=owner_id,
                chat_id=chat_id,
                request_id=request["request_id"],
            )
        if not isinstance(delivery, Mapping):
            return {"ok": False, "status": "provider_failure", "mode": selected, "request_id": request["request_id"], "provider_calls": 1}
        return {**delivery, "provider_calls": 1, "provider_messages": str(messages)}
    usage = _usage_from_result(provider_result)
    provider_request_id = str(provider_result.get("provider_request_id") or "").strip()
    if usage is None or not provider_request_id:
        _compensate_pro_request(conn=conn, owner_id=owner_id, request_id=request["request_id"], reason="usage_or_request_id_missing", note="usage/request id missing", record_credit_event=record_credit_event)
        return {"ok": False, "status": "provider_failure", "mode": selected, "request_id": request["request_id"], "provider_calls": 1}
    try:
        settled = settle_pro_request(conn, request["request_id"], usage=usage, user_content=_memory_user_content(text, items), assistant_content=output, provider_request_id=provider_request_id, now=time.time())
        if not settled.get("settled"):
            raise RuntimeError("settlement_failed")
        delta = int(settled.get("refunded_xu") or 0) - max(0, int(settled.get("charged_xu") or 0) - int(request.get("reserved_xu") or 0))
        event_type = "public_chat_refund" if delta > 0 else "public_chat_settlement"
        _credit_event(record_credit_event, conn, owner_id, delta, event_type, request["request_id"], f"model={CLAUDE_OPUS_MODEL}; provider_request_id={provider_request_id}")
        conn.commit()
    except Exception:
        _compensate_pro_request(conn=conn, owner_id=owner_id, request_id=request["request_id"], reason="settlement_failed", note="settlement failure", record_credit_event=record_credit_event)
        return {"ok": False, "status": "provider_failure", "mode": selected, "request_id": request["request_id"], "provider_calls": 1}
    if settled.get("status") == "under_reserved_refunded":
        return {
            "ok": False,
            "status": "insufficient_balance_after_usage",
            "mode": selected,
            "request_id": request["request_id"],
            "provider_request_id": provider_request_id,
            "actual_xu": int(settled.get("actual_xu") or 0),
            "charged_xu": 0,
            "refunded_xu": int(settled.get("refunded_xu") or 0),
            "uncollected_xu": int(settled.get("uncollected_xu") or 0),
            "provider_calls": 1,
        }
    delivery = settled.get("delivery")
    if not isinstance(delivery, Mapping):
        delivery = load_pending_public_chat_delivery(
            conn,
            owner_id=owner_id,
            chat_id=chat_id,
            request_id=request["request_id"],
        )
    if not isinstance(delivery, Mapping):
        return {"ok": False, "status": "provider_failure", "mode": selected, "request_id": request["request_id"], "provider_calls": 1}
    return {
        **delivery,
        "provider_calls": 1,
        "provider_messages": str(messages),
        "endpoint": KEY4U_PUBLIC_CHAT_COMPLETIONS_URL,
    }


__all__ = ["CHAT_PRO_RATE_LABEL", "PUBLIC_CHAT_MAX_OUTPUT_TOKENS", "PublicChatRequest", "PublicChatRuntime", "public_chat_menu_rows", "public_chat_system_prompt", "resolve_public_chat_mode_action", "run_public_chat_request", "split_public_chat_text", "toggle_public_chat_mode"]
