"""Session-only caption editing. No publishing, provider or database operations."""
import hashlib
import html
import json
import secrets

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from services.autopost_ui import autopost_draft_keyboard, autopost_draft_view_text

EDIT_KEY = 'autopost_caption_edit'


def clear_pending(context):
    """Release only AutoPost input ownership; preserve draft and all other jobs."""
    state = getattr(context, 'user_data', None)
    if isinstance(state, dict):
        for key in (EDIT_KEY, 'awaiting_content_input_type',
                    'awaiting_brand_edit', 'awaiting_telegram_channel_id'):
            state.pop(key, None)


def _fingerprint(draft):
    return hashlib.sha256(json.dumps(draft, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _controls(token):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton('✅ Lưu', callback_data='autopost|draft_edit_save|' + token),
        InlineKeyboardButton('❌ Hủy', callback_data='autopost|draft_edit_cancel|' + token),
    ]])


async def handle_callback(update, context):
    query = update.callback_query
    parts = str(query.data or '').split('|')
    action = parts[1] if len(parts) > 1 else ''
    if action not in {'draft_edit', 'draft_edit_save', 'draft_edit_cancel'}:
        return False
    state = context.user_data
    draft = state.get('current_draft')
    owner = query.from_user.id
    chat_id = getattr(getattr(query, 'message', None), 'chat_id', None)
    if not isinstance(draft, dict) or draft.get('owner_user_id') != owner:
        await query.answer('Bản nháp không còn khả dụng. Hãy mở lại bản nháp.', show_alert=True)
        return True
    if action == 'draft_edit':
        if (chat_id is None or state.get('autopost_draft_chat_id') != chat_id
                or state.get('autopost_draft_message_id') != query.message.message_id):
            await query.answer('Nút này đã cũ. Hãy dùng bản nháp mới nhất.', show_alert=True)
            return True
        token = secrets.token_hex(8)
        for key in ('awaiting_content_input_type', 'awaiting_brand_edit', 'awaiting_telegram_channel_id'):
            state.pop(key, None)
        state[EDIT_KEY] = {'token': token, 'owner': owner, 'chat_id': chat_id, 'original': _fingerprint(draft)}
        await query.answer()
        await query.message.reply_text('Gửi nội dung mới. Bản nháp chỉ thay đổi khi bạn bấm Lưu.',
                                       reply_markup=_controls(token))
        return True
    editing = state.get(EDIT_KEY, {})
    token = parts[2] if len(parts) > 2 else ''
    if (not token or editing.get('token') != token or editing.get('owner') != owner
            or chat_id is None or editing.get('chat_id') != chat_id):
        await query.answer('Phiên sửa đã hết hạn.', show_alert=True)
        return True
    if editing.get('original') != _fingerprint(draft):
        state.pop(EDIT_KEY, None)
        await query.answer('Bản nháp đã thay đổi. Hãy mở lại để sửa.', show_alert=True)
        return True
    if action == 'draft_edit_save':
        if 'candidate' not in editing:
            await query.answer('Hãy gửi nội dung mới trước khi lưu.', show_alert=True)
            return True
        state['current_draft'] = {**draft, 'caption': html.escape(editing['candidate'])}
    state.pop(EDIT_KEY, None)
    await query.answer('Đã lưu.' if action == 'draft_edit_save' else 'Đã hủy sửa.')
    message = await query.message.reply_text(autopost_draft_view_text(state['current_draft']),
                      parse_mode='HTML', reply_markup=autopost_draft_keyboard(0))
    state['autopost_draft_message_id'] = message.message_id
    state['autopost_draft_chat_id'] = message.chat_id
    return True


async def handle_text(update, context):
    state = context.user_data
    editing = state.get(EDIT_KEY)
    if not editing:
        return False
    if (editing.get('owner') != update.effective_user.id
            or editing.get('chat_id') != getattr(update.message, 'chat_id', None)):
        return False
    text = update.message.text or ''
    if text.startswith('/'):
        state.pop(EDIT_KEY, None)
        return False
    draft = state.get('current_draft')
    if not isinstance(draft, dict) or _fingerprint(draft) != editing.get('original'):
        state.pop(EDIT_KEY, None)
        await update.message.reply_text('Bản nháp đã thay đổi. Hãy mở lại để sửa.')
        return True
    # Leave room for the draft heading in Telegram's 4096-character message.
    if not text.strip() or len(text.encode('utf-16-le')) // 2 > 3500:
        await update.message.reply_text('Nhập nội dung từ 1 đến 3500 ký tự.')
        return True
    editing['candidate'] = text
    editing['token'] = secrets.token_hex(8)
    await update.message.reply_text('Xem trước:\n\n' + text, parse_mode=None,
                                   reply_markup=_controls(editing['token']))
    return True
