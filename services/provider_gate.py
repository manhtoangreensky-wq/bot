from __future__ import annotations

from dataclasses import dataclass


SLASH_SMOKE = "SLASH_SMOKE"
INTERACTIVE_UI = "INTERACTIVE_UI"
PREVIEW_CONFIRMED = "PREVIEW_CONFIRMED"
WORKER_CONFIRMED_JOB = "WORKER_CONFIRMED_JOB"
ADMIN_TEST = "ADMIN_TEST"

PUBLIC_SAFE_BLOCK_MESSAGE = (
    "TOAN AAS chưa xử lý file và chưa trừ Xu. "
    "Anh/chị xác nhận bước cuối rồi hệ thống mới tạo file."
)
PUBLIC_SAFE_NOT_READY_MESSAGE = (
    "Tính năng này đang được hoàn thiện. TOAN AAS chưa xử lý file và chưa trừ Xu."
)
PUBLIC_SAFE_PREVIEW_MESSAGE = (
    "Bản nghe thử chỉ được tạo khi anh/chị xác nhận rõ. TOAN AAS không trừ Xu âm thầm."
)

PUBLIC_TECHNICAL_TERMS = (
    "provider",
    "api",
    "endpoint",
    "minimax",
    "ffmpeg",
    "mux",
    "adapter",
    "worker lease",
    "traceback",
    "token",
)


@dataclass(frozen=True)
class ProviderGateDecision:
    allowed: bool
    context: str
    reason: str
    public_message: str
    admin_message: str = ""
    no_charge: bool = True
    may_charge: bool = False

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "context": self.context,
            "reason": self.reason,
            "public_message": self.public_message,
            "admin_message": self.admin_message,
            "no_charge": self.no_charge,
            "may_charge": self.may_charge,
        }


def public_copy_has_technical_terms(text: str) -> bool:
    lower = str(text or "").lower()
    return any(term in lower for term in PUBLIC_TECHNICAL_TERMS)


def safe_public_error(message: str = "") -> str:
    text = str(message or "").strip() or PUBLIC_SAFE_NOT_READY_MESSAGE
    if public_copy_has_technical_terms(text):
        return PUBLIC_SAFE_NOT_READY_MESSAGE
    return text


def evaluate_provider_gate(
    *,
    context: str,
    is_admin: bool = False,
    is_owner: bool = False,
    configured: bool = True,
    public_ready: bool = True,
    final_confirmed: bool = False,
    preview_confirmed: bool = False,
    preview_no_charge: bool = False,
    fake_mode: bool = False,
    provider_name: str = "",
) -> ProviderGateDecision:
    """Decide whether a real provider call is allowed for voice/subtitle/dub work."""
    del provider_name
    normalized = str(context or "").strip().upper()
    privileged = bool(is_admin or is_owner)

    if normalized == ADMIN_TEST:
        if not privileged:
            return ProviderGateDecision(
                allowed=False,
                context=normalized,
                reason="admin_only",
                public_message="Khu vực này chỉ dành cho Admin. TOAN AAS chưa xử lý file và chưa trừ Xu.",
            )
        if not configured and not fake_mode:
            return ProviderGateDecision(
                allowed=False,
                context=normalized,
                reason="not_configured",
                public_message=PUBLIC_SAFE_NOT_READY_MESSAGE,
                admin_message="OWNER/ADMIN TEST MODE - no provider configuration for real call",
            )
        return ProviderGateDecision(
            allowed=True,
            context=normalized,
            reason="admin_test_no_charge",
            public_message="OWNER/ADMIN TEST MODE - không trừ Xu",
            admin_message="OWNER/ADMIN TEST MODE - không trừ Xu",
            no_charge=True,
            may_charge=False,
        )

    if normalized == SLASH_SMOKE:
        if not privileged:
            return ProviderGateDecision(
                allowed=False,
                context=normalized,
                reason="admin_only",
                public_message="Khu vực này chỉ dành cho Admin. TOAN AAS chưa xử lý file và chưa trừ Xu.",
            )
        if not configured and not fake_mode:
            return ProviderGateDecision(
                allowed=False,
                context=normalized,
                reason="not_configured",
                public_message=PUBLIC_SAFE_NOT_READY_MESSAGE,
            )
        return ProviderGateDecision(
            allowed=True,
            context=normalized,
            reason="slash_smoke_no_charge",
            public_message="OWNER/ADMIN TEST MODE - không trừ Xu",
            admin_message="OWNER/ADMIN TEST MODE - không trừ Xu",
            no_charge=True,
            may_charge=False,
        )

    if normalized == INTERACTIVE_UI:
        return ProviderGateDecision(
            allowed=False,
            context=normalized,
            reason="interactive_plan_only",
            public_message=PUBLIC_SAFE_BLOCK_MESSAGE,
        )

    if normalized == PREVIEW_CONFIRMED:
        if not configured or (not privileged and not public_ready):
            return ProviderGateDecision(
                allowed=False,
                context=normalized,
                reason="preview_not_ready",
                public_message=PUBLIC_SAFE_NOT_READY_MESSAGE,
            )
        if not privileged and not (preview_confirmed and preview_no_charge):
            return ProviderGateDecision(
                allowed=False,
                context=normalized,
                reason="preview_requires_explicit_no_charge_confirm",
                public_message=PUBLIC_SAFE_PREVIEW_MESSAGE,
            )
        return ProviderGateDecision(
            allowed=True,
            context=normalized,
            reason="preview_confirmed_no_charge" if preview_no_charge else "admin_preview_no_charge",
            public_message="TOAN AAS sẽ tạo bản nghe thử ngắn và không trừ Xu.",
            admin_message="OWNER/ADMIN TEST MODE - không trừ Xu" if privileged else "",
            no_charge=True,
            may_charge=False,
        )

    if normalized == WORKER_CONFIRMED_JOB:
        if not configured:
            return ProviderGateDecision(
                allowed=False,
                context=normalized,
                reason="not_configured",
                public_message=PUBLIC_SAFE_NOT_READY_MESSAGE,
            )
        if final_confirmed or privileged:
            return ProviderGateDecision(
                allowed=True,
                context=normalized,
                reason="worker_confirmed_job",
                public_message="TOAN AAS đang xử lý video sau khi anh/chị xác nhận.",
                no_charge=privileged,
                may_charge=not privileged,
            )
        return ProviderGateDecision(
            allowed=False,
            context=normalized,
            reason="missing_final_confirm",
            public_message=PUBLIC_SAFE_BLOCK_MESSAGE,
        )

    return ProviderGateDecision(
        allowed=False,
        context=normalized or "UNKNOWN",
        reason="unknown_context",
        public_message=PUBLIC_SAFE_NOT_READY_MESSAGE,
    )


def provider_gate_allows(**kwargs) -> bool:
    return evaluate_provider_gate(**kwargs).allowed
