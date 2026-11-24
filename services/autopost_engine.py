"""Autopost engine: hub keyboard/text + callback handler.

Extracted verbatim from the ``autopost_engine_code`` string that used to be
``exec``-ed into ``bot.py`` globals (latent RCE: ~300 lines of callback logic
invisible to linter/grep/AST). This is now a real module, imported normally
by ``bot.py``. Behaviour is identical: same three public names
(``autopost_hub_keyboard``, ``autopost_hub_text``,
``handle_autopost_callback``), same call sites, same helpers.
"""

import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from services.autopost_ads import DEFAULT_OWNER_BUDGET_ENVELOPE
from services.autopost_affiliate import (
    clear_user_affiliate_vault,
    count_user_affiliate_links,
    get_user_affiliate_links,
    get_user_affiliate_stats,
    seed_default_curated_vault_for_user,
)
from services.autopost_brand import get_effective_brand_profile
from services.autopost_db import (
    create_publish_job,
    get_user_publish_queue,
    get_user_social_accounts,
    set_user_publish_mode,
)
from services.autopost_publish import TelegramAdapter, execute_publish_job
from services.autopost_strategy import create_content_plan, generate_single_post_draft
from services.autopost_ui import (
    autopost_ads_center_text,
    autopost_aff_clear_confirm_text,
    autopost_aff_clear_done_text,
    autopost_aff_seed_success_text,
    autopost_affiliate_import_prompt_text,
    autopost_affiliate_keyboard,
    autopost_affiliate_list_keyboard,
    autopost_affiliate_list_text,
    autopost_affiliate_text,
    autopost_brand_edit_prompt_text,
    autopost_brand_keyboard,
    autopost_brand_preview_text,
    autopost_brand_view_text,
    autopost_calendar_text,
    autopost_channels_keyboard,
    autopost_channels_text,
    autopost_conn_oauth_prompt_text,
    autopost_conn_telegram_prompt_text,
    autopost_content_input_menu_keyboard,
    autopost_content_input_menu_text,
    autopost_content_plan_text,
    autopost_draft_approved_text,
    autopost_draft_publish_result_text,
    autopost_guide_keyboard,
    autopost_guide_plan_text,
    autopost_guide_single_text,
    autopost_guide_sub_keyboard,
    autopost_guide_telegram_text,
    autopost_guide_text,
    autopost_input_prompt_text,
    autopost_job_publish_result_text,
    autopost_kill_switch_text,
    autopost_main_dashboard_text,
    autopost_main_keyboard,
    autopost_metrics_text,
    autopost_plan_result_text,
    autopost_published_history_keyboard,
    autopost_published_history_text,
    autopost_queue_keyboard,
    autopost_queue_text,
    autopost_resume_ads_text,
    autopost_set_mode_text,
    autopost_settings_keyboard,
    autopost_settings_text,
    autopost_test_tg_conn_text,
)
from services.pricing_guide_content import public_hub_copy



def autopost_hub_text(lang: str = "vi", user_id: int = 0) -> str:
    return autopost_main_dashboard_text(lang, user_id)

def autopost_hub_keyboard(lang: str = "vi", is_admin: bool = False) -> InlineKeyboardMarkup:
    return autopost_main_keyboard(lang)

async def handle_autopost_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Lazy imports: these three helpers are defined in bot.py (the monolith).
    # A top-level `from bot import ...` here would be a circular import, so
    # they are resolved at call time, exactly as the old exec-in-globals()
    # code resolved them from bot.py's globals.
    from bot import get_user_language, is_admin_user, safe_edit_query_message

    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    lang = get_user_language(uid) or "vi"
    copy = public_hub_copy(lang)
    parts = str(query.data or "").split("|")
    action = parts[1] if len(parts) > 1 else "main"
    value = parts[2] if len(parts) > 2 else ""

    if action in {"main", "hub", "dashboard"}:
        return await safe_edit_query_message(
            query,
            autopost_main_dashboard_text(lang, uid),
            parse_mode="HTML",
            reply_markup=autopost_main_keyboard(lang),
        )

    if action == "content_input_menu":
        return await safe_edit_query_message(
            query,
            autopost_content_input_menu_text(),
            parse_mode="HTML",
            reply_markup=autopost_content_input_menu_keyboard(),
        )

    if action == "input":
        input_type = value or "topic"
        context.user_data["awaiting_content_input_type"] = input_type
        msg = autopost_input_prompt_text(input_type)
        reply_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Quay lại", callback_data="autopost|content_input_menu"), InlineKeyboardButton(f"🏠 {copy['main_menu']}", callback_data="menu|main")],
        ])
        return await safe_edit_query_message(query, msg, parse_mode="HTML", reply_markup=reply_kb)

    if action == "content_plan":
        reply_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("👗 Thời trang", callback_data="autopost|gen_plan|thoi_trang"), InlineKeyboardButton("💄 Mỹ phẩm", callback_data="autopost|gen_plan|my_pham")],
            [InlineKeyboardButton("📱 Công nghệ & AI", callback_data="autopost|gen_plan|cong_nghe"), InlineKeyboardButton("🎓 Khóa học", callback_data="autopost|gen_plan|khoa_hoc")],
            [InlineKeyboardButton("🏡 Bất động sản", callback_data="autopost|gen_plan|bat_dong_san"), InlineKeyboardButton("☕ F&B Ăn uống", callback_data="autopost|gen_plan|an_uong")],
            [InlineKeyboardButton("⬅️ Quay lại", callback_data="autopost|main"), InlineKeyboardButton(f"🏠 {copy['main_menu']}", callback_data="menu|main")],
        ])
        return await safe_edit_query_message(query, autopost_content_plan_text(), parse_mode="HTML", reply_markup=reply_kb)

    if action == "gen_plan":
        niche = value or "cong_nghe"
        brand = get_effective_brand_profile(uid)
        plan = create_content_plan(str(uid), brand, niche, duration_days=7, persist_db=True)
        context.user_data["active_content_plan"] = plan
        msg = autopost_plan_result_text(niche, plan["total_posts"], plan["items"][0])
        reply_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📅 Xem lịch đăng", callback_data="autopost|calendar"), InlineKeyboardButton("🚀 Xem hàng đợi", callback_data="autopost|queue")],
            [InlineKeyboardButton("⬅️ Đổi ngành", callback_data="autopost|content_plan"), InlineKeyboardButton("🏠 Menu chính", callback_data="menu|main")],
        ])
        return await safe_edit_query_message(query, msg, parse_mode="HTML", reply_markup=reply_kb)

    if action == "brands":
        brand = get_effective_brand_profile(uid)
        msg = autopost_brand_view_text(brand)
        reply_kb = autopost_brand_keyboard()
        return await safe_edit_query_message(query, msg, parse_mode="HTML", reply_markup=reply_kb)

    if action == "brand_edit_prompt":
        context.user_data["awaiting_brand_edit"] = True
        msg = autopost_brand_edit_prompt_text()
        reply_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Quay lại", callback_data="autopost|brands")],
        ])
        return await safe_edit_query_message(query, msg, parse_mode="HTML", reply_markup=reply_kb)

    if action == "brand_preview":
        brand = get_effective_brand_profile(uid)
        draft = generate_single_post_draft(uid, "Bí quyết kinh doanh bứt phá doanh số", brand)
        msg = autopost_brand_preview_text(draft)
        reply_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Quay lại Thương hiệu", callback_data="autopost|brands")],
        ])
        return await safe_edit_query_message(query, msg, parse_mode="HTML", reply_markup=reply_kb)

    if action == "affiliate":
        stats = get_user_affiliate_stats(uid)
        if stats.get("total", 0) == 0 and is_admin_user(uid):
            seed_default_curated_vault_for_user(uid)
            stats = get_user_affiliate_stats(uid)
        msg = autopost_affiliate_text(uid, stats, lang)
        reply_kb = autopost_affiliate_keyboard(uid, stats, lang)
        return await safe_edit_query_message(query, msg, parse_mode="HTML", reply_markup=reply_kb)

    if action == "aff_import_prompt":
        context.user_data["awaiting_affiliate_import"] = True
        msg = autopost_affiliate_import_prompt_text(lang)
        reply_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Quay lại Kho Affiliate", callback_data="autopost|affiliate"), InlineKeyboardButton(f"🏠 {copy['main_menu']}", callback_data="menu|main")],
        ])
        return await safe_edit_query_message(query, msg, parse_mode="HTML", reply_markup=reply_kb)

    if action == "aff_seed":
        seed_default_curated_vault_for_user(uid)
        stats = get_user_affiliate_stats(uid)
        msg = autopost_aff_seed_success_text(uid, stats, lang)
        reply_kb = autopost_affiliate_keyboard(uid, stats, lang)
        return await safe_edit_query_message(query, msg, parse_mode="HTML", reply_markup=reply_kb)

    if action == "aff_clear_confirm":
        msg = autopost_aff_clear_confirm_text()
        reply_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🗑️ Xác nhận xóa sạch", callback_data="autopost|aff_clear_done")],
            [InlineKeyboardButton("❌ Hủy bỏ", callback_data="autopost|affiliate")],
        ])
        return await safe_edit_query_message(query, msg, parse_mode="HTML", reply_markup=reply_kb)

    if action == "aff_clear_done":
        clear_user_affiliate_vault(uid)
        stats = get_user_affiliate_stats(uid)
        msg = autopost_aff_clear_done_text(uid, stats, lang)
        reply_kb = autopost_affiliate_keyboard(uid, stats, lang)
        return await safe_edit_query_message(query, msg, parse_mode="HTML", reply_markup=reply_kb)

    if action == "aff_view":
        niche = value or "all"
        page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0
        total = count_user_affiliate_links(uid, niche=niche)
        items = get_user_affiliate_links(uid, niche=niche, limit=5, offset=page * 5)
        msg = autopost_affiliate_list_text(uid, items, total, niche, page, 5, lang)
        reply_kb = autopost_affiliate_list_keyboard(uid, items, total, niche, page, 5, lang)
        return await safe_edit_query_message(query, msg, parse_mode="HTML", reply_markup=reply_kb)

    if action == "aff_noop":
        return

    if action == "channels":
        msg = autopost_channels_text(uid)
        reply_kb = autopost_channels_keyboard()
        return await safe_edit_query_message(query, msg, parse_mode="HTML", reply_markup=reply_kb)

    if action == "conn":
        platform = value or "telegram"
        if platform == "telegram":
            context.user_data["awaiting_telegram_channel_id"] = True
            msg = autopost_conn_telegram_prompt_text()
            return await safe_edit_query_message(query, msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Quay lại", callback_data="autopost|channels")]]))
        else:
            msg = autopost_conn_oauth_prompt_text(platform)
            return await safe_edit_query_message(query, msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Quay lại", callback_data="autopost|channels")]]))

    if action == "test_tg_conn":
        accounts = get_user_social_accounts(uid)
        tg_acc = next((a for a in accounts if a["platform"] == "telegram"), None)
        v = await TelegramAdapter.validate(tg_acc["account_id"] if tg_acc else "", bot_instance=context.bot) if tg_acc else {"valid": False}
        msg = autopost_test_tg_conn_text(tg_acc, v)
        return await safe_edit_query_message(query, msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Quay lại Channels", callback_data="autopost|channels")]]))

    if action == "calendar":
        msg = autopost_calendar_text(uid)
        reply_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🧠 Lập kế hoạch mới", callback_data="autopost|content_plan")],
            [InlineKeyboardButton("⬅️ Quay lại", callback_data="autopost|main"), InlineKeyboardButton(f"🏠 {copy['main_menu']}", callback_data="menu|main")],
        ])
        return await safe_edit_query_message(query, msg, parse_mode="HTML", reply_markup=reply_kb)

    if action == "queue":
        msg = autopost_queue_text(uid)
        reply_kb = autopost_queue_keyboard(uid)
        return await safe_edit_query_message(query, msg, parse_mode="HTML", reply_markup=reply_kb)

    if action == "job_publish_now":
        job_id = int(value) if value.isdigit() else 0
        queue = get_user_publish_queue(uid)
        job = next((q for q in queue if q["id"] == job_id), None)
        if not job:
            msg = "⚠️ Không tìm thấy bài đăng trong hàng đợi."
        else:
            res = await execute_publish_job(job, bot_instance=context.bot)
            msg = autopost_job_publish_result_text(res, job)
        reply_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Xem lịch sử đã đăng", callback_data="autopost|published_history"), InlineKeyboardButton("🚀 Hàng đợi", callback_data="autopost|queue")],
            [InlineKeyboardButton("⬅️ Quay lại Hub", callback_data="autopost|main")],
        ])
        return await safe_edit_query_message(query, msg, parse_mode="HTML", reply_markup=reply_kb)

    if action == "published_history":
        msg = autopost_published_history_text(uid)
        reply_kb = autopost_published_history_keyboard()
        return await safe_edit_query_message(query, msg, parse_mode="HTML", reply_markup=reply_kb)

    if action == "metrics":
        msg = autopost_metrics_text(uid)
        reply_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📣 Quản trị quảng cáo", callback_data="autopost|ads_center")],
            [InlineKeyboardButton("⬅️ Quay lại", callback_data="autopost|main"), InlineKeyboardButton(f"🏠 {copy['main_menu']}", callback_data="menu|main")],
        ])
        return await safe_edit_query_message(query, msg, parse_mode="HTML", reply_markup=reply_kb)

    if action == "ads_center":
        env = DEFAULT_OWNER_BUDGET_ENVELOPE
        msg = autopost_ads_center_text(env)
        reply_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🛑 Dừng toàn bộ quảng cáo (Kill Switch)", callback_data="autopost|kill_switch")],
            [InlineKeyboardButton("⬅️ Quay lại", callback_data="autopost|main"), InlineKeyboardButton(f"🏠 {copy['main_menu']}", callback_data="menu|main")],
        ])
        return await safe_edit_query_message(query, msg, parse_mode="HTML", reply_markup=reply_kb)

    if action == "kill_switch":
        DEFAULT_OWNER_BUDGET_ENVELOPE["emergency_kill_switch"] = True
        reply_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🟢 Bật lại", callback_data="autopost|resume_ads")],
            [InlineKeyboardButton("⬅️ Quay lại", callback_data="autopost|ads_center"), InlineKeyboardButton("🏠 Menu chính", callback_data="menu|main")],
        ])
        return await safe_edit_query_message(query, autopost_kill_switch_text(), parse_mode="HTML", reply_markup=reply_kb)

    if action == "resume_ads":
        DEFAULT_OWNER_BUDGET_ENVELOPE["emergency_kill_switch"] = False
        return await safe_edit_query_message(query, autopost_resume_ads_text(), parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Quay lại Ads", callback_data="autopost|ads_center")]]))

    if action == "settings":
        msg = autopost_settings_text(uid)
        reply_kb = autopost_settings_keyboard(uid)
        return await safe_edit_query_message(query, msg, parse_mode="HTML", reply_markup=reply_kb)

    if action == "set_mode":
        set_user_publish_mode(uid, value or "MANUAL")
        msg = autopost_set_mode_text(value, uid)
        reply_kb = autopost_settings_keyboard(uid)
        return await safe_edit_query_message(query, msg, parse_mode="HTML", reply_markup=reply_kb)

    if action == "draft_publish_now":
        draft = context.user_data.get("current_draft")
        if not draft:
            msg = "⚠️ Không tìm thấy bản nháp để phát hành."
        else:
            accounts = get_user_social_accounts(uid)
            tg_acc = next((a for a in accounts if a["platform"] == "telegram"), None)
            target_chat = tg_acc["account_id"] if tg_acc else f"@{query.from_user.username}" if query.from_user.username else str(uid)
            now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
            
            job_id = create_publish_job(None, uid, "telegram", target_chat, now_str)
            res = await execute_publish_job({
                "id": job_id, "owner_user_id": uid, "platform": "telegram",
                "channel_id": target_chat, "payload": {"caption": draft["caption"]}
            }, bot_instance=context.bot)
            msg = autopost_draft_publish_result_text(res)
                
        reply_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Xem lịch sử đã đăng", callback_data="autopost|published_history"), InlineKeyboardButton("🚀 Hàng đợi", callback_data="autopost|queue")],
            [InlineKeyboardButton("⬅️ Quay lại Hub", callback_data="autopost|main")],
        ])
        return await safe_edit_query_message(query, msg, parse_mode="HTML", reply_markup=reply_kb)

    if action == "draft_approve":
        draft = context.user_data.get("current_draft")
        if not draft:
            msg = "⚠️ Không tìm thấy bản nháp để lên lịch."
        else:
            accounts = get_user_social_accounts(uid)
            tg_acc = next((a for a in accounts if a["platform"] == "telegram"), None)
            target_chat = tg_acc["account_id"] if tg_acc else str(uid)
            sched_time = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=5)).isoformat()
            job_id = create_publish_job(None, uid, "telegram", target_chat, sched_time)
            msg = autopost_draft_approved_text(job_id, sched_time, target_chat)
        reply_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Xem hàng đợi", callback_data="autopost|queue"), InlineKeyboardButton("⬅️ Quay lại Hub", callback_data="autopost|main")],
        ])
        return await safe_edit_query_message(query, msg, parse_mode="HTML", reply_markup=reply_kb)

    if action == "guide":
        msg = autopost_guide_text()
        reply_kb = autopost_guide_keyboard()
        return await safe_edit_query_message(query, msg, parse_mode="HTML", reply_markup=reply_kb)

    if action == "guide_single":
        msg = autopost_guide_single_text()
        reply_kb = autopost_guide_sub_keyboard()
        return await safe_edit_query_message(query, msg, parse_mode="HTML", reply_markup=reply_kb)

    if action == "guide_plan":
        msg = autopost_guide_plan_text()
        reply_kb = autopost_guide_sub_keyboard()
        return await safe_edit_query_message(query, msg, parse_mode="HTML", reply_markup=reply_kb)

    if action == "guide_telegram":
        msg = autopost_guide_telegram_text()
        reply_kb = autopost_guide_sub_keyboard()
        return await safe_edit_query_message(query, msg, parse_mode="HTML", reply_markup=reply_kb)

    if action == "guide":
        msg = autopost_guide_text()
        reply_kb = autopost_guide_keyboard()
        return await safe_edit_query_message(query, msg, parse_mode="HTML", reply_markup=reply_kb)

    if action == "guide_single":
        msg = autopost_guide_single_text()
        reply_kb = autopost_guide_sub_keyboard()
        return await safe_edit_query_message(query, msg, parse_mode="HTML", reply_markup=reply_kb)

    if action == "guide_plan":
        msg = autopost_guide_plan_text()
        reply_kb = autopost_guide_sub_keyboard()
        return await safe_edit_query_message(query, msg, parse_mode="HTML", reply_markup=reply_kb)

    if action == "guide_telegram":
        msg = autopost_guide_telegram_text()
        reply_kb = autopost_guide_sub_keyboard()
        return await safe_edit_query_message(query, msg, parse_mode="HTML", reply_markup=reply_kb)

    return await safe_edit_query_message(query, autopost_main_dashboard_text(lang, uid), parse_mode="HTML", reply_markup=autopost_main_keyboard(lang))
