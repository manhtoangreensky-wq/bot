from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def _is_vi(lang: str = "vi") -> bool:
    return str(lang or "vi").strip().lower().split("-")[0] == "vi"


def frame_video_unified_menu_text(lang: str = "vi") -> str:
    if not _is_vi(lang):
        return (
            "🎞 <b>Image slideshow video</b>\n\n"
            "How would you like to make a video from images?\n\n"
            "1. You already have images:\n"
            "Send multiple images and TOAN AAS will merge them into an MP4 with simple transitions. "
            "This path uses TOAN AAS video processing and does not call AI video generation.\n\n"
            "2. You do not have images yet:\n"
            "TOAN AAS can help prepare AI images first, then use those images for the MP4 slideshow.\n\n"
            "The bot only processes after the final confirmation and has not charged Xu on this screen."
        )
    return (
        "🎞 <b>Ghép ảnh thành video</b>\n\n"
        "Bạn muốn làm video từ ảnh theo cách nào?\n\n"
        "1. Đã có ảnh sẵn:\n"
        "Gửi nhiều ảnh để TOAN AAS ghép thành video MP4 bằng hiệu ứng chuyển cảnh đơn giản. "
        "Luồng này dùng công cụ ghép video của TOAN AAS, không gọi AI video.\n\n"
        "2. Chưa có ảnh:\n"
        "TOAN AAS sẽ hỗ trợ tạo ảnh AI trước, sau đó dùng các ảnh đã tạo để ghép thành video MP4.\n\n"
        "Bot chỉ xử lý thật sau bước xác nhận cuối và chưa trừ Xu ở bước này."
    )


def frame_video_unified_menu_keyboard(lang: str = "vi") -> InlineKeyboardMarkup:
    is_vi = _is_vi(lang)
    main_label = "🏠 Menu chính" if is_vi else "🏠 Main menu"
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📤 Dùng ảnh có sẵn" if is_vi else "📤 Use existing images", callback_data="framevideo|start"),
            InlineKeyboardButton("✨ Tạo ảnh AI nhanh rồi ghép" if is_vi else "✨ Quick AI images then stitch", callback_data="framevideo|ai_first"),
        ],
        [
            InlineKeyboardButton("⬅️ Menu video" if is_vi else "⬅️ Video menu", callback_data="menu|main_video"),
            InlineKeyboardButton(main_label, callback_data="framevideo|main"),
        ],
    ])


def frame_video_ai_first_guard_text(lang: str = "vi") -> str:
    if not _is_vi(lang):
        return (
            "✨ <b>Quick AI images then stitch</b>\n\n"
            "Enter a prompt and image count. TOAN AAS will create related still images first, then you can stitch those images into a simple MP4 slideshow.\n\n"
            "Image generation is priced separately. Video stitching is priced by total seconds."
        )
    return (
        "✨ <b>Tạo ảnh AI nhanh rồi ghép</b>\n\n"
        "Nhập prompt và số ảnh. TOAN AAS tạo nhiều ảnh cùng chủ đề, sau đó anh/chị có thể ghép các ảnh đó thành video.\n\n"
        "Bước tạo ảnh tính phí riêng. Bước ghép video tính theo tổng số giây."
    )


def frame_video_ai_first_keyboard(lang: str = "vi") -> InlineKeyboardMarkup:
    is_vi = _is_vi(lang)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✍️ Nhập prompt ảnh" if is_vi else "✍️ Enter image prompt", callback_data="framevideo|ai_prompt")],
        [
            InlineKeyboardButton("📤 Dùng ảnh có sẵn" if is_vi else "📤 Use existing images", callback_data="framevideo|start"),
            InlineKeyboardButton("⬅️ Ghép ảnh thành video" if is_vi else "⬅️ Image slideshow video", callback_data="framevideo|hub"),
        ],
        [
            InlineKeyboardButton("🏠 Menu chính" if is_vi else "🏠 Main menu", callback_data="framevideo|main"),
        ],
    ])


def frame_video_layout_helper_text(lang: str = "vi") -> str:
    if not _is_vi(lang):
        return (
            "📚 <b>Image layout ideas</b>\n\n"
            "Use 2-20 images in the order they should appear. For a clean short video, prepare: "
            "1 cover image, 3-5 detail/process images, and 1 ending image with product, CTA or result.\n\n"
            "This screen is planning help only. TOAN AAS has not processed media and has not charged Xu."
        )
    return (
        "📚 <b>Gợi ý bố cục ảnh</b>\n\n"
        "Chuẩn bị 2-20 ảnh theo đúng thứ tự muốn xuất hiện trong video. Bố cục dễ dùng:\n"
        "1. Ảnh mở đầu/cover.\n"
        "2. 3-5 ảnh chi tiết, quy trình hoặc lợi ích chính.\n"
        "3. Ảnh kết thúc có sản phẩm, CTA hoặc kết quả.\n\n"
        "Màn này chỉ hỗ trợ lên bố cục, chưa xử lý media và chưa trừ Xu."
    )


def frame_video_layout_helper_keyboard(lang: str = "vi") -> InlineKeyboardMarkup:
    is_vi = _is_vi(lang)
    main_label = "🏠 Menu chính" if is_vi else "🏠 Main menu"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📷 Tôi có ảnh sẵn" if is_vi else "📷 I have images", callback_data="framevideo|start")],
        [
            InlineKeyboardButton("⬅️ Ghép ảnh thành video" if is_vi else "⬅️ Image slideshow video", callback_data="framevideo|hub"),
            InlineKeyboardButton(main_label, callback_data="framevideo|main"),
        ],
    ])


def frame_video_apply_effect_defaults(state: dict | None, effect_token: str = "default") -> dict:
    clean = dict(state or {})
    choice = str(effect_token or "default").strip().lower()
    effect = "fade" if choice in {"", "default", "auto"} else choice
    if effect not in {"none", "fade", "zoom", "slide"}:
        effect = "fade"
    clean.setdefault("ratio", "9x16")
    clean.setdefault("duration", "standard")
    clean["effect"] = effect
    clean["effect_choice"] = choice or "default"
    clean["music_choice"] = "skip"
    clean["music_merge_enabled"] = False
    clean["voice_choice"] = "skip"
    clean["voice_merge_enabled"] = False
    clean["step"] = "confirm"
    return clean


def frame_video_handoff_images_state(photos: list | None, source: str = "ai_image_first", max_images: int = 20) -> dict:
    return {
        "step": "effect",
        "photos": list(photos or [])[:max_images],
        "source": str(source or "ai_image_first")[:80],
        "ratio": "9x16",
        "duration": "standard",
    }
