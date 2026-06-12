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
    "finance_accounting": ("revenue_export", "expense_receipt", "payos_statement", "provider_invoice", "profit_loss_report", "accounting_export"),
    "tax_invoice": ("tax_prep_file", "invoice", "receipt", "tax_notice", "accountant_note", "tax_report"),
    "contracts": ("b2b_contract", "service_agreement", "vendor_contract", "nda", "affiliate_agreement"),
    "hr_collaborators": ("collaborator_profile", "permission_note", "work_agreement", "work_note", "payout_record"),
    "marketing": ("campaign_plan", "content_caption", "approved_video", "posting_schedule", "kpi_report", "brand_asset"),
    "tech_codex": ("codex_task", "deployment_note", "env_note", "provider_doc", "bug_report", "architecture_doc", "backup_note"),
    "legal_policy": ("terms", "privacy", "refund_policy", "data_policy", "ip_policy", "customer_notice"),
    "provider_api": ("provider_doc", "provider_pricing", "smoke_test", "provider_status", "integration_note", "provider_error"),
    "accounts_assets": ("domain", "hosting_vps", "paid_software", "service_account", "renewal_note", "brand_asset"),
}

INTERNAL_DOC_TYPE_LABELS = {
    "general": "Hồ sơ chưa phân loại",
    "internal_document": "Hồ sơ nội bộ",
    "customer_profile": "Hồ sơ khách hàng",
    "customer_request": "Yêu cầu khách gửi",
    "refund_case": "Case hoàn Xu / refund",
    "custom_order": "Đơn custom / dịch vụ riêng",
    "b2b_lead": "Lead B2B / khách tiềm năng",
    "revenue_export": "Báo cáo doanh thu",
    "expense_receipt": "Phiếu/biên lai chi phí",
    "payos_statement": "Sao kê PayOS/ngân hàng",
    "bank_statement": "Sao kê ngân hàng",
    "provider_invoice": "Hóa đơn provider",
    "profit_loss_report": "Báo cáo lãi/lỗ",
    "accounting_export": "File xuất cho kế toán",
    "tax_prep_file": "File chuẩn bị thuế",
    "invoice": "Hóa đơn",
    "receipt": "Biên lai",
    "tax_notice": "Thông báo thuế",
    "accountant_note": "Ghi chú kế toán",
    "tax_report": "Báo cáo thuế nội bộ",
    "b2b_contract": "Hợp đồng khách hàng/B2B",
    "service_agreement": "Thỏa thuận dịch vụ",
    "vendor_contract": "Hợp đồng nhà cung cấp",
    "nda": "NDA / bảo mật",
    "affiliate_agreement": "Hợp đồng affiliate/CTV",
    "collaborator_profile": "Hồ sơ CTV",
    "permission_note": "Phân quyền tài khoản",
    "work_agreement": "Thỏa thuận làm việc",
    "work_note": "Ghi chú công việc",
    "payout_record": "Thanh toán CTV",
    "staff_profile": "Hồ sơ nhân sự",
    "collaborator_record": "Hồ sơ CTV",
    "payment_record": "Thanh toán CTV",
    "working_note": "Ghi chú công việc",
    "campaign_plan": "Kế hoạch chiến dịch",
    "content_caption": "Content/caption",
    "approved_video": "Video đã duyệt",
    "posting_schedule": "Lịch đăng bài",
    "kpi_report": "Báo cáo KPI",
    "brand_asset": "Tài nguyên thương hiệu",
    "creative_brief": "Creative brief",
    "performance_report": "Báo cáo hiệu quả",
    "codex_task": "Task Codex",
    "deployment_note": "Ghi chú deploy",
    "bug_report": "Bug report",
    "architecture_doc": "Tài liệu kiến trúc",
    "provider_doc": "Tài liệu provider",
    "backup_note": "Ghi chú backup",
    "env_note": "ENV note không chứa secret",
    "terms": "Điều khoản sử dụng",
    "privacy": "Chính sách riêng tư",
    "refund_policy": "Chính sách hoàn Xu/refund",
    "data_policy": "Chính sách dữ liệu",
    "ip_policy": "Chính sách sở hữu trí tuệ",
    "customer_notice": "Thông báo khách hàng",
    "provider_pricing": "Bảng giá provider",
    "smoke_test": "Smoke test",
    "provider_status": "Trạng thái provider",
    "integration_note": "Ghi chú tích hợp",
    "provider_error": "Lỗi provider",
    "domain": "Tên miền/domain",
    "hosting_vps": "Hosting/VPS",
    "paid_software": "Phần mềm trả phí",
    "service_account": "Tài khoản dịch vụ",
    "renewal_note": "Lịch gia hạn",
    "asset_inventory": "Danh mục tài sản",
    "account_record": "Tài khoản dịch vụ",
    "access_note": "Ghi chú truy cập",
}

INTERNAL_DOC_DEPARTMENT_DESCRIPTIONS = {
    "customers": "Dùng để lưu thông tin khách hàng, yêu cầu dịch vụ, ticket, hoàn Xu, đơn custom và lead B2B.",
    "finance_accounting": "Dùng để lưu sao kê, doanh thu, chi phí, báo cáo lãi/lỗ, file xuất kế toán và chứng từ nội bộ.",
    "tax_invoice": "Dùng để lưu hóa đơn, biên lai, file chuẩn bị thuế và ghi chú làm việc với kế toán.",
    "contracts": "Dùng để lưu hợp đồng khách hàng, nhà cung cấp, NDA và các thỏa thuận dịch vụ/CTV.",
    "hr_collaborators": "Dùng để lưu hồ sơ nhân sự/CTV, phân quyền, thỏa thuận làm việc và thanh toán.",
    "marketing": "Dùng để lưu kế hoạch chiến dịch, nội dung đã duyệt, lịch đăng, KPI và tài nguyên thương hiệu.",
    "tech_codex": "Dùng để lưu task Codex, ghi chú deploy, bug, kiến trúc, backup và ENV note không chứa secret.",
    "legal_policy": "Dùng để lưu điều khoản, chính sách dữ liệu, hoàn Xu, sở hữu trí tuệ và thông báo khách hàng.",
    "provider_api": "Dùng để lưu tài liệu nhà cung cấp, bảng giá, smoke test, trạng thái provider và ghi chú tích hợp.",
    "accounts_assets": "Dùng để lưu tên miền, hosting/VPS, phần mềm trả phí, tài khoản dịch vụ và lịch gia hạn.",
}

INTERNAL_DOC_DEPARTMENT_HELP = {
    "customers": {
        "name": "KH_TenKhach_NoiDung_YYYYMMDD",
        "examples": ("KH_NguyenVanA_refund_video_20260612", "KH_CongTyABC_bao_gia_video_20260612"),
        "tags": "khach-hang, refund, video, bao-gia, lead-b2b",
        "retention": "Lead/tư vấn: 1–3 năm; refund/thanh toán: 5–10 năm; hợp đồng/B2B: 10 năm hoặc vĩnh viễn.",
    },
    "finance_accounting": {
        "name": "TC_LoaiChungTu_KyBaoCao_YYYYMMDD",
        "examples": ("TC_PayOS_2026_06_20260630", "TC_ProviderInvoice_ShopAIKey_20260612"),
        "tags": "doanh-thu, chi-phi, payos, provider, lai-lo",
        "retention": "Chứng từ/sao kê/báo cáo: 5–10 năm theo nhu cầu kế toán.",
    },
    "tax_invoice": {
        "name": "HD_LoaiChungTu_Ky_YYYYMMDD",
        "examples": ("HD_HoaDonProvider_20260612", "HD_GhiChuKeToan_Q2_2026"),
        "tags": "hoa-don, bien-lai, ke-toan, thue, doi-soat",
        "retention": "Hóa đơn và hồ sơ đối soát: 10 năm hoặc theo tư vấn kế toán.",
    },
    "contracts": {
        "name": "HD_TenDoiTac_LoaiHopDong_YYYYMMDD",
        "examples": ("HD_CongTyABC_DichVu_20260612", "HD_Provider_NDA_20260612"),
        "tags": "hop-dong, nda, b2b, provider, ctv",
        "retention": "Hợp đồng/NDA: 10 năm hoặc vĩnh viễn.",
    },
    "hr_collaborators": {
        "name": "NS_TenNhanSu_LoaiHoSo_YYYYMMDD",
        "examples": ("NS_NguyenVanA_CTV_20260612", "NS_CTV_Payout_2026_06"),
        "tags": "nhan-su, ctv, phan-quyen, thanh-toan",
        "retention": "Hồ sơ làm việc/thanh toán: 3–10 năm tùy loại.",
    },
    "marketing": {
        "name": "MKT_ChienDich_TaiSan_YYYYMMDD",
        "examples": ("MKT_TikTokLaunch_Plan_20260612", "MKT_Brand_VideoApproved_20260612"),
        "tags": "marketing, campaign, content, kpi, brand",
        "retention": "Chiến dịch/KPI: 3–5 năm; brand asset: vĩnh viễn.",
    },
    "tech_codex": {
        "name": "TECH_HeThong_LoaiTaiLieu_YYYYMMDD",
        "examples": ("TECH_Bot_Deploy_20260612", "TECH_Codex_Task_V9_20260612"),
        "tags": "codex, deploy, bug, architecture, backup",
        "retention": "Kiến trúc/backup quan trọng: 5 năm hoặc vĩnh viễn.",
    },
    "legal_policy": {
        "name": "LEGAL_ChinhSach_PhienBan_YYYYMMDD",
        "examples": ("LEGAL_Privacy_v2_20260612", "LEGAL_RefundPolicy_v3_20260612"),
        "tags": "legal, policy, privacy, refund, data",
        "retention": "Chính sách và phiên bản đã công bố: vĩnh viễn.",
    },
    "provider_api": {
        "name": "PROVIDER_Ten_LoaiTaiLieu_YYYYMMDD",
        "examples": ("PROVIDER_ShopAIKey_Status_20260612", "PROVIDER_Kling_Pricing_20260612"),
        "tags": "provider, pricing, smoke-test, integration, error",
        "retention": "Tài liệu tích hợp/trạng thái: 3–5 năm. Tuyệt đối không lưu secret.",
    },
    "accounts_assets": {
        "name": "ASSET_TenTaiSan_Loai_YYYYMMDD",
        "examples": ("ASSET_toanaas.vn_domain_20260612", "ASSET_Railway_Renewal_20260612"),
        "tags": "domain, hosting, software, account, renewal",
        "retention": "Tài sản/gia hạn: giữ khi còn sử dụng và tối thiểu 3–5 năm sau đó.",
    },
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


def document_type_label(document_type: str) -> str:
    value = str(document_type or "").strip()
    return INTERNAL_DOC_TYPE_LABELS.get(value, "Hồ sơ khác")


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
