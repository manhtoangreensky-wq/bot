"""Pure constants and helpers for TOAN AAS Operations V1A."""

from __future__ import annotations

import csv
import io
from typing import Iterable, Sequence


TAX_PREP_DISCLAIMER = (
    "Báo cáo quản trị nội bộ / dữ liệu chuẩn bị cho kế toán. "
    "Không phải tờ khai thuế chính thức. Cần đối chiếu chứng từ và xác nhận "
    "với kế toán trước khi nộp."
)

REVENUE_CATEGORIES = (
    "payos_topup_xu",
    "manual_topup_xu",
    "combo_package_sale",
    "storage_addon",
    "custom_service",
    "image_service",
    "video_service",
    "document_service",
    "voice_tts_service",
    "other_income",
    "refund_reversal",
)

EXPENSE_CATEGORIES = (
    "provider_ai_api",
    "shopaikey",
    "wokushop",
    "key4u",
    "railway",
    "vps",
    "domain",
    "software_tools",
    "marketing",
    "office",
    "bank_fee",
    "refund_cash",
    "accounting_service",
    "legal_service",
    "other_expense",
)

INTERNAL_DOC_DEPARTMENTS = {
    "customers": "👥 Khách hàng",
    "finance_accounting": "💰 Tài chính/Kế toán",
    "tax_invoice": "🧾 Hóa đơn/Thuế",
    "contracts": "📑 Hợp đồng",
    "hr_collaborators": "👤 Nhân sự/CTV",
    "marketing": "📣 Marketing",
    "tech_codex": "💻 Kỹ thuật/Codex",
    "legal_policy": "⚖️ Pháp lý/Chính sách",
    "provider_api": "🤖 Provider/API",
    "accounts_assets": "🔐 Tài khoản/Tài sản",
}

INTERNAL_DOC_TYPES = {
    "customers": ("customer_profile", "customer_request", "refund_case", "custom_order", "b2b_lead"),
    "finance_accounting": ("revenue_export", "expense_receipt", "payos_statement", "bank_statement", "provider_invoice", "profit_loss_report"),
    "tax_invoice": ("tax_report", "tax_prep_file", "invoice", "receipt", "tax_notice", "accountant_note"),
    "contracts": ("b2b_contract", "nda", "service_agreement", "vendor_contract", "affiliate_agreement"),
    "hr_collaborators": ("staff_profile", "collaborator_record", "payment_record", "working_note"),
    "marketing": ("campaign_plan", "creative_brief", "performance_report", "brand_asset"),
    "tech_codex": ("codex_task", "deployment_note", "env_note", "provider_doc", "bug_report", "architecture_doc", "backup_note"),
    "legal_policy": ("terms", "privacy", "refund_policy", "ip_policy", "data_policy", "customer_notice"),
    "provider_api": ("provider_doc", "provider_invoice", "provider_status", "integration_note"),
    "accounts_assets": ("asset_inventory", "account_record", "access_note", "renewal_note"),
}

RETENTION_LABELS = ("1_year", "3_years", "5_years", "10_years", "permanent", "manual_review")


def revenue_category_for_source(source_type: str) -> str:
    value = str(source_type or "").strip().lower()
    if "payos" in value or value in {"topup", "paid_topup"}:
        return "payos_topup_xu"
    if "manual" in value and "topup" in value:
        return "manual_topup_xu"
    if "combo" in value or "package" in value or "plan" in value:
        return "combo_package_sale"
    if "storage" in value:
        return "storage_addon"
    if "image" in value:
        return "image_service"
    if "video" in value:
        return "video_service"
    if "document" in value or "pdf" in value:
        return "document_service"
    if "voice" in value or "tts" in value:
        return "voice_tts_service"
    if "refund" in value:
        return "refund_reversal"
    if "service" in value:
        return "custom_service"
    return "other_income"


def default_document_type(department: str) -> str:
    values = INTERNAL_DOC_TYPES.get(str(department or ""), ())
    return values[0] if values else "internal_document"


def default_retention(department: str) -> str:
    department = str(department or "")
    if department in {"finance_accounting", "tax_invoice", "contracts"}:
        return "10_years"
    if department == "legal_policy":
        return "permanent"
    if department in {"tech_codex", "provider_api", "accounts_assets"}:
        return "5_years"
    return "3_years"


def calculate_tax_estimate(taxable_revenue: int, config: dict) -> dict:
    revenue = max(0, int(taxable_revenue or 0))
    vat_rate = max(0.0, float(config.get("vat_rate_percent") or 0))
    pit_rate = max(0.0, float(config.get("pit_rate_percent") or 0))
    license_fee = max(0, int(config.get("license_fee_amount_vnd") or 0)) if bool(config.get("license_fee_enabled")) else 0
    vat = int(round(revenue * vat_rate / 100))
    pit = int(round(revenue * pit_rate / 100))
    return {
        "taxable_revenue": revenue,
        "vat_rate_percent": vat_rate,
        "pit_rate_percent": pit_rate,
        "vat_estimate": vat,
        "pit_estimate": pit,
        "license_fee_estimate": license_fee,
        "total_tax_estimate": vat + pit + license_fee,
    }


def csv_with_no_data(headers: Sequence[str], rows: Iterable[Sequence[object]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(list(headers))
    row_list = list(rows)
    if row_list:
        writer.writerows(row_list)
    else:
        writer.writerow(["No data"] + [""] * max(0, len(headers) - 1))
    return buffer.getvalue()
