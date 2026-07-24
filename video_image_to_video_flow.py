from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def _is_vi(lang: str = "vi") -> bool:
    return str(lang or "vi").strip().lower().split("-")[0] == "vi"


def frame_video_unified_menu_text(lang: str = "vi") -> str:
    if not _is_vi(lang):
        return (
            "🖼️ <b>Image slideshow video</b>\n\n"
            "Choose where the images will come from. This product uses an image count, not a scene count. "
            "Each image becomes one ordered item on the final video timeline.\n\n"
            "You can upload images, create AI images through a separate quoted confirmation, or reuse a saved image. "
            "Video rendering has its own quote and final confirmation. No Xu has been charged on this screen."
        )
    return (
        "🖼️ <b>Ghép ảnh thành video</b>\n\n"
        "Chọn nguồn ảnh muốn dùng. Sản phẩm này tính theo <b>số ảnh</b>, không dùng số cảnh; "
        "mỗi ảnh là một phần theo đúng thứ tự trên dòng thời gian video.\n\n"
        "Anh/chị có thể gửi ảnh sẵn, tạo ảnh AI qua hóa đơn riêng hoặc dùng lại ảnh đã lưu. "
        "Dựng MP4 có báo giá và xác nhận cuối riêng. Màn này chưa tạo file và chưa trừ Xu."
    )


def frame_video_unified_menu_keyboard(lang: str = "vi") -> InlineKeyboardMarkup:
    is_vi = _is_vi(lang)
    main_label = "🏠 Menu chính" if is_vi else "🏠 Main menu"
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📎 Gửi ảnh có sẵn" if is_vi else "📎 Upload images", callback_data="framevideo|source|uploaded"),
            InlineKeyboardButton("✨ Tạo ảnh AI" if is_vi else "✨ Create AI images", callback_data="framevideo|source|ai"),
        ],
        [
            InlineKeyboardButton("🗂️ Dùng ảnh đã lưu" if is_vi else "🗂️ Use a saved image", callback_data="framevideo|source|saved"),
            InlineKeyboardButton("ℹ️ Cách hoạt động" if is_vi else "ℹ️ How it works", callback_data="framevideo|how"),
        ],
        [
            InlineKeyboardButton("⬅️ Quay lại" if is_vi else "⬅️ Back", callback_data="menu|main_video"),
            InlineKeyboardButton(main_label, callback_data="framevideo|main"),
        ],
    ])


def frame_video_how_text(lang: str = "vi") -> str:
    if not _is_vi(lang):
        return (
            "ℹ️ <b>How image-to-video works</b>\n\n"
            "Choose 2-20 images, set their order and duration, then configure ratio, transitions, motion and optional audio/text. "
            "TOAN AAS renders one MP4 locally, validates it, delivers it to Telegram, records one receipt, and only then charges Xu."
        )
    return (
        "ℹ️ <b>Cách ghép ảnh thành video</b>\n\n"
        "Chọn 2–20 ảnh, sắp xếp đúng thứ tự, đặt thời lượng rồi chọn chuyển cảnh, chuyển động và phần bổ sung nếu cần. "
        "TOAN AAS dựng một MP4, kiểm tra file, gửi qua Telegram, ghi đúng một biên nhận rồi mới trừ Xu.\n\n"
        "Tạo ảnh AI và dựng video là hai hóa đơn riêng; không có bước nào mặc định miễn phí khi bảng giá đang bật."
    )


def frame_video_how_keyboard(lang: str = "vi") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("⬅️ Quay lại" if _is_vi(lang) else "⬅️ Back", callback_data="framevideo|hub"),
        InlineKeyboardButton("🏠 Menu chính" if _is_vi(lang) else "🏠 Main menu", callback_data="framevideo|main"),
    ]])


def frame_video_image_count_text(selected: int = 0, lang: str = "vi") -> str:
    selected_line = f"\n• Đang chọn: <b>{int(selected)} ảnh</b>" if selected else ""
    if not _is_vi(lang):
        return (
            "🔢 <b>Choose image count</b>\n\n"
            "Choose exactly 2-20 images. The upload or AI-image step will require this exact count before continuing."
        )
    return (
        "🔢 <b>Chọn số ảnh</b>\n\n"
        "Chọn chính xác 2–20 ảnh. Bước gửi hoặc tạo ảnh chỉ cho tiếp tục khi đã đủ đúng số lượng này. "
        "Mỗi ảnh là một phần trên dòng thời gian, không phải một cảnh Video AI."
        f"{selected_line}\n\nMàn này chưa tạo file và chưa trừ Xu."
    )


def frame_video_image_count_keyboard(lang: str = "vi") -> InlineKeyboardMarkup:
    is_vi = _is_vi(lang)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("2 ảnh", callback_data="framevideo|image_count|2"), InlineKeyboardButton("3 ảnh", callback_data="framevideo|image_count|3")],
        [InlineKeyboardButton("4 ảnh", callback_data="framevideo|image_count|4"), InlineKeyboardButton("5 ảnh", callback_data="framevideo|image_count|5")],
        [InlineKeyboardButton("8 ảnh", callback_data="framevideo|image_count|8"), InlineKeyboardButton("10 ảnh", callback_data="framevideo|image_count|10")],
        [InlineKeyboardButton("20 ảnh", callback_data="framevideo|image_count|20"), InlineKeyboardButton("✍️ Nhập số khác" if is_vi else "✍️ Custom", callback_data="framevideo|image_count_custom")],
        [
            InlineKeyboardButton("⬅️ Quay lại" if is_vi else "⬅️ Back", callback_data="framevideo|hub"),
            InlineKeyboardButton("🏠 Menu chính" if is_vi else "🏠 Main menu", callback_data="framevideo|main"),
        ],
    ])


def frame_video_ratio_first_text(selected: str = "9x16", lang: str = "vi") -> str:
    display = str(selected or "9x16").replace("x", ":")
    if not _is_vi(lang):
        return f"📐 <b>Choose video ratio</b>\n\nCurrent: <b>{display}</b>. This ratio is used for AI images and the final MP4."
    return (
        "📐 <b>Chọn tỉ lệ video</b>\n\n"
        f"• Đang chọn: <b>{display}</b>\n\n"
        "Tỉ lệ được chốt trước khi nhận ảnh để ảnh AI và MP4 cuối cùng cùng một khung hình. Ảnh tải lên không bị bóp méo."
    )


def frame_video_ratio_first_keyboard(lang: str = "vi") -> InlineKeyboardMarkup:
    is_vi = _is_vi(lang)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Dọc 9:16", callback_data="framevideo|ratio_first_set|9x16"), InlineKeyboardButton("Ngang 16:9", callback_data="framevideo|ratio_first_set|16x9")],
        [InlineKeyboardButton("Vuông 1:1", callback_data="framevideo|ratio_first_set|1x1"), InlineKeyboardButton("Dọc 4:5", callback_data="framevideo|ratio_first_set|4x5")],
        [
            InlineKeyboardButton("⬅️ Quay lại" if is_vi else "⬅️ Back", callback_data="framevideo|image_count_menu"),
            InlineKeyboardButton("🏠 Menu chính" if is_vi else "🏠 Main menu", callback_data="framevideo|main"),
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
        "Anh/chị có thể chọn một gợi ý dễ dùng hoặc tự mô tả bộ ảnh muốn tạo. "
        "TOAN AAS sẽ soạn prompt chung, tạo các ảnh liên quan cùng phong cách, rồi mới chuyển sang bước ghép video.\n\n"
        "Bước tạo ảnh tính phí riêng. Bước ghép video tính theo tổng số giây."
    )


def frame_video_ai_first_keyboard(lang: str = "vi") -> InlineKeyboardMarkup:
    is_vi = _is_vi(lang)
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💡 Chọn gợi ý" if is_vi else "💡 Choose an idea", callback_data="framevideo|ai_suggest"),
            InlineKeyboardButton("✍️ Tự nhập prompt" if is_vi else "✍️ Custom prompt", callback_data="framevideo|ai_prompt"),
        ],
        [
            InlineKeyboardButton("⬅️ Chọn tỉ lệ" if is_vi else "⬅️ Choose ratio", callback_data="framevideo|ratio_first_menu"),
            InlineKeyboardButton("🏠 Menu chính" if is_vi else "🏠 Main menu", callback_data="framevideo|main"),
        ],
    ])


def frame_video_ai_suggestions_text(suggestions: list[str] | None = None, lang: str = "vi") -> str:
    items = list(suggestions or [])[:5]
    if not _is_vi(lang):
        lines = [
            "💡 <b>Image set ideas</b>",
            "",
            "The image count was selected at the start. Choose one idea and TOAN AAS will prepare a coherent image-set prompt.",
            "",
        ]
    else:
        lines = [
            "💡 <b>Gợi ý bộ ảnh để ghép video</b>",
            "",
            "Số ảnh đã được chốt ở bước đầu. Chọn một ý tưởng để TOAN AAS soạn prompt bộ ảnh đồng nhất.",
            "",
        ]
    lines.extend(f"{index}. {item}" for index, item in enumerate(items, start=1))
    lines.extend([
        "",
        "Màn này chỉ chọn ý tưởng, chưa tạo ảnh và chưa trừ Xu."
        if _is_vi(lang)
        else "This screen only selects an idea. No image has been generated and no Xu was charged.",
    ])
    return "\n".join(lines)


def frame_video_ai_suggestions_keyboard(lang: str = "vi") -> InlineKeyboardMarkup:
    is_vi = _is_vi(lang)
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(str(index), callback_data=f"framevideo|ai_pick|{index}")
            for index in range(1, 6)
        ],
        [
            InlineKeyboardButton("🔄 Đổi gợi ý" if is_vi else "🔄 More ideas", callback_data="framevideo|ai_refresh"),
            InlineKeyboardButton("✍️ Tự nhập prompt" if is_vi else "✍️ Custom prompt", callback_data="framevideo|ai_prompt"),
        ],
        [
            InlineKeyboardButton("⬅️ Quay lại" if is_vi else "⬅️ Back", callback_data="framevideo|ai_first"),
            InlineKeyboardButton("🏠 Menu chính" if is_vi else "🏠 Main menu", callback_data="framevideo|main"),
        ],
    ])


def frame_video_ai_prompt_text(prompt: str = "", lang: str = "vi") -> str:
    clean = " ".join(str(prompt or "").split())[:1200]
    if not _is_vi(lang):
        return (
            "✨ <b>Image-set prompt</b>\n\n"
            f"{clean}\n\n"
            "TOAN AAS will vary composition and camera angle while preserving the same subject and visual style. "
            "The image count was selected at the start. Review the prompt before choosing image quality."
        )
    return (
        "✨ <b>Prompt bộ ảnh</b>\n\n"
        f"{clean}\n\n"
        "TOAN AAS sẽ đổi bố cục và góc nhìn giữa các ảnh nhưng giữ cùng chủ thể, màu sắc và phong cách. "
        "Số ảnh đã được chọn ở đầu flow. Anh/chị hãy kiểm tra prompt trước khi chọn chất lượng ảnh."
    )


def frame_video_ai_prompt_keyboard(lang: str = "vi", *, suggestion_source: bool = False) -> InlineKeyboardMarkup:
    is_vi = _is_vi(lang)
    back_callback = "framevideo|ai_suggest" if suggestion_source else "framevideo|ai_first"
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔢 Chọn số ảnh" if is_vi else "🔢 Choose image count", callback_data="framevideo|ai_count_menu"),
            InlineKeyboardButton("✍️ Sửa prompt" if is_vi else "✍️ Edit prompt", callback_data="framevideo|ai_prompt"),
        ],
        [
            InlineKeyboardButton("⬅️ Quay lại" if is_vi else "⬅️ Back", callback_data=back_callback),
            InlineKeyboardButton("🏠 Menu chính" if is_vi else "🏠 Main menu", callback_data="framevideo|main"),
        ],
    ])


def frame_video_ai_custom_prompt_keyboard(lang: str = "vi") -> InlineKeyboardMarkup:
    is_vi = _is_vi(lang)
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("⬅️ Quay lại" if is_vi else "⬅️ Back", callback_data="framevideo|ai_first"),
        InlineKeyboardButton("🏠 Menu chính" if is_vi else "🏠 Main menu", callback_data="framevideo|main"),
    ]])


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
