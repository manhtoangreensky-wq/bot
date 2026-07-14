"""Curated, provider-free idea catalog for the public Video Ideas hub.

The catalog is planning metadata only.  It never creates jobs, calls providers,
generates media, or mutates a wallet.  Public flows may use these records to
prefill an existing product planner before the user's final confirmation.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


SCENE_SECONDS = 8
DURATION_OPTIONS = (8, 16, 24, 40, 80, 160)

CATEGORIES = (
    ("sales", "🛍 Bán hàng / quảng cáo"),
    ("ugc", "📱 Review / nội dung đời thường"),
    ("education", "🎓 Hướng dẫn / kiến thức"),
    ("story", "🎬 Kể chuyện / trailer"),
    ("space", "🏠 Kiến trúc / bất động sản"),
    ("lifestyle", "👗 Thời trang / ẩm thực"),
    ("digital", "💻 Ứng dụng / website / trò chơi"),
    ("visual", "🎧 Sự kiện / nhạc hình / điểm nhấn"),
)


def _idea(
    idea_id: str,
    category: str,
    title: str,
    summary: str,
    hook: str,
    objective: str,
    product_id: str,
    profile_id: str,
    style: str,
    image_prompt: str,
    video_prompt: str,
    *,
    source_modes: tuple[str, ...] = ("text_prompt", "image_prompt", "reference_image"),
) -> dict[str, Any]:
    return {
        "idea_id": idea_id,
        "category": category,
        "title": title,
        "summary": summary,
        "hook": hook,
        "objective": objective,
        "recommended_product_id": product_id,
        "recommended_profile_id": profile_id,
        "style": style,
        "image_prompt_seed": image_prompt,
        "video_prompt_seed": video_prompt,
        "source_modes": list(source_modes),
        "duration_options": list(DURATION_OPTIONS),
        "scene_seconds": SCENE_SECONDS,
        "planning_only": True,
        "provider_called": False,
        "job_created": False,
        "outbox_created": False,
        "xu_charged": 0,
    }


IDEAS = (
    _idea(
        "sales_problem_solution", "sales", "Vấn đề → giải pháp → kết quả",
        "Mở bằng nỗi đau thật, giới thiệu giải pháp, chứng minh một lợi ích và kết bằng lời mời rõ ràng.",
        "Một khoảnh khắc bất tiện quen thuộc xảy ra ngay trong hai giây đầu.",
        "Tăng chuyển đổi nhưng vẫn giữ lời giới thiệu đáng tin.",
        "script_image_video", "product_3d_showcase", "quảng cáo sản phẩm sạch, nhịp rõ",
        "Sản phẩm trong bối cảnh sử dụng thật, bố cục sạch, vùng trống an toàn cho chữ và logo.",
        "Mỗi cảnh hoàn thành một ý: vấn đề, thao tác giải quyết, bằng chứng, kết quả và lời mời.",
    ),
    _idea(
        "sales_before_after", "sales", "Trước và sau có bằng chứng",
        "So sánh hai trạng thái bằng cùng góc máy để người xem thấy thay đổi rõ ràng.",
        "Khung hình chia đôi hé lộ sự khác biệt nhưng chưa cho thấy toàn bộ kết quả.",
        "Làm nổi bật thay đổi nhìn thấy được, không dùng tuyên bố phóng đại.",
        "video_ai_real", "product_3d_showcase", "before/after nhất quán",
        "Hai trạng thái trước và sau cùng chủ thể, cùng bố cục, ánh sáng có kiểm soát.",
        "Match cut giữa trạng thái trước và sau; giữ nguyên nhận diện, sản phẩm và hướng chuyển động.",
    ),
    _idea(
        "sales_product_reveal", "sales", "Mở hộp và hé lộ sản phẩm",
        "Dẫn dắt bằng chi tiết, mở hộp, cận cảnh tính năng rồi kết bằng khung hình sản phẩm chính.",
        "Một chi tiết vật liệu hoặc âm thanh mở hộp tạo tò mò.",
        "Tăng nhận biết sản phẩm và ghi nhớ điểm khác biệt.",
        "storyboard_prompt", "product_3d_showcase", "studio reveal cao cấp",
        "Hero product shot, vật liệu trung thực, phông nền theo màu thương hiệu, không sinh chữ ngẫu nhiên.",
        "Macro reveal, orbit ngắn, thao tác sử dụng hoàn chỉnh, kết ở hero frame ổn định.",
    ),
    _idea(
        "ugc_honest_review", "ugc", "Review thật: điểm mạnh và một lưu ý",
        "Một người dùng kể trải nghiệm ngắn, minh họa cách dùng, nêu lợi ích và một lưu ý đáng tin.",
        "Câu mở đầu như một lời thú nhận đời thường, không giống quảng cáo đọc sẵn.",
        "Tạo niềm tin và giúp người xem tự đánh giá sản phẩm.",
        "video_trend", "ugc_social_creator", "đời thường, camera điện thoại",
        "Người dùng thật trong không gian tự nhiên, ánh sáng phòng, sản phẩm rõ và tay không lỗi.",
        "Handheld nhẹ, lời nói ngắn theo từng cảnh, demo trọn thao tác, không cắt giữa câu.",
        source_modes=("text_prompt", "reference_video", "reference_image"),
    ),
    _idea(
        "ugc_day_in_life", "ugc", "Một ngày có sản phẩm đồng hành",
        "Đưa sản phẩm vào ba thời điểm tự nhiên trong ngày thay vì giới thiệu trực diện.",
        "Một tình huống buổi sáng bận rộn khiến người xem nhận ra chính mình.",
        "Cho thấy ngữ cảnh sử dụng và cảm giác gần gũi.",
        "video_ai_real", "ugc_social_creator", "day-in-the-life chân thật",
        "Cùng nhân vật, trang phục và sản phẩm xuyên suốt các thời điểm trong ngày.",
        "Chuyển thời gian bằng match cut hành động; mỗi cảnh kết thúc thao tác trước khi sang cảnh mới.",
        source_modes=("text_prompt", "reference_video", "reference_image"),
    ),
    _idea(
        "ugc_pov_demo", "ugc", "Góc nhìn người dùng tự trải nghiệm",
        "Camera ở góc nhìn người dùng, từng cảnh là một bước sử dụng và phản hồi trực quan.",
        "Bàn tay chạm vào sản phẩm ngay khi video bắt đầu.",
        "Giải thích cách dùng nhanh và giảm cảm giác quảng cáo.",
        "self_shot_scene_change", "ugc_social_creator", "POV tự quay",
        "Bàn tay, sản phẩm và mặt bàn nhất quán; bố cục dọc, vùng chữ an toàn.",
        "POV thao tác trọn bước, camera ổn định, giữ âm thanh nguồn nếu người dùng chọn.",
        source_modes=("reference_video",),
    ),
    _idea(
        "education_three_steps", "education", "Giải thích bằng ba bước dễ nhớ",
        "Đặt câu hỏi, lần lượt giải thích ba bước và chốt bằng một ví dụ hoặc checklist.",
        "Một câu hỏi cụ thể mà người xem thường trả lời sai.",
        "Giúp người xem hiểu và áp dụng ngay.",
        "script_image_video", "tutorial_explainer", "giải thích trực quan",
        "Minh họa sạch cho từng bước, màu nhất quán, vùng chữ rộng, không có chi tiết thừa.",
        "Mỗi cảnh giải quyết đúng một bước; camera và đồ họa hoàn tất trước khi chuyển cảnh.",
    ),
    _idea(
        "education_myth_fact", "education", "Hiểu lầm và sự thật",
        "Nêu một hiểu lầm phổ biến, kiểm tra bằng ví dụ, giải thích nguyên nhân và kết luận dễ nhớ.",
        "Hiển thị hai lựa chọn đối lập để người xem tự đoán.",
        "Tăng tương tác và truyền đạt kiến thức có cấu trúc.",
        "video_ai_real", "tutorial_explainer", "myth-versus-fact hiện đại",
        "Hai khung minh họa đối chiếu, biểu tượng rõ, không tạo số liệu hoặc chữ không được cung cấp.",
        "Reveal đáp án sau nhịp chờ ngắn, minh họa nguyên nhân, kết bằng khung ghi nhớ.",
    ),
    _idea(
        "education_process", "education", "Quy trình từ đầu đến kết quả",
        "Theo dõi một quy trình thật từ nguyên liệu/đầu vào đến thành phẩm cuối.",
        "Cho thấy thành phẩm trước rồi quay lại điểm bắt đầu.",
        "Làm rõ quy trình và tăng sự trân trọng đối với sản phẩm/dịch vụ.",
        "storyboard_prompt", "tutorial_explainer", "process documentary",
        "Chuỗi keyframe cùng không gian, vật liệu và dụng cụ; mỗi ảnh thể hiện một mốc hoàn chỉnh.",
        "Time-lapse có kiểm soát xen cận cảnh; không bỏ qua bước làm thay đổi kết quả.",
    ),
    _idea(
        "story_three_act", "story", "Câu chuyện ba hồi ngắn",
        "Giới thiệu mong muốn, tạo trở ngại, cho nhân vật hành động và khép lại bằng thay đổi rõ ràng.",
        "Nhân vật đứng trước một lựa chọn nhỏ nhưng có ý nghĩa.",
        "Tạo cảm xúc và ghi nhớ thương hiệu/câu chuyện.",
        "script_image_video", "character", "cinematic ba hồi",
        "Nhân vật có character bible, trang phục và ánh sáng nhất quán qua từng mốc truyện.",
        "Mỗi cảnh là một hành động hoàn chỉnh; trạng thái cuối cảnh trước mở tự nhiên sang cảnh sau.",
    ),
    _idea(
        "story_teaser", "story", "Trailer bí ẩn có cao trào",
        "Dùng hình ảnh gợi mở, chi tiết xung đột, nhịp tăng dần và kết bằng câu hỏi chưa trả lời.",
        "Một chi tiết bất thường xuất hiện trong bối cảnh rất bình thường.",
        "Tạo tò mò cho phim, sự kiện hoặc chiến dịch sắp ra mắt.",
        "video_ai_real", "cinematic_vfx", "trailer điện ảnh nguyên bản",
        "Bối cảnh nhiều lớp, ánh sáng có động cơ, motif thị giác lặp lại, không dùng nhân vật bản quyền.",
        "Establishing chậm, cận cảnh manh mối, chuyển động tăng dần, kết ở hình ảnh biểu tượng.",
    ),
    _idea(
        "story_memory", "story", "Ký ức nối quá khứ và hiện tại",
        "Một vật thể hoặc địa điểm nối hai thời điểm bằng chuyển cảnh đồng hình.",
        "Cận cảnh vật kỷ niệm mở ra một không gian khác.",
        "Kể chuyện cảm xúc, phù hợp thương hiệu, gia đình hoặc du lịch.",
        "storyboard_prompt", "character", "ký ức điện ảnh ấm",
        "Hai thời điểm có motif, nhân vật và vật thể nối cảnh rõ; màu sắc thay đổi có chủ đích.",
        "Match cut vật thể giữa quá khứ và hiện tại; hành động ở mỗi thời điểm kết thúc trọn vẹn.",
    ),
    _idea(
        "space_walkthrough", "space", "Tham quan không gian theo hành trình",
        "Đi từ lối vào tới các khu vực chính, mỗi cảnh làm rõ công năng và cảm giác không gian.",
        "Cánh cửa mở để hé lộ trục nhìn chính của công trình.",
        "Trình bày bất động sản hoặc thiết kế mà không làm sai hình học.",
        "video_ai_real", "architecture_walkthrough", "walkthrough kiến trúc chân thật",
        "Giữ tuyệt đối mặt bằng, cửa, cửa sổ, vật liệu và tỉ lệ; ánh sáng tự nhiên cân bằng.",
        "Camera tiến theo đường đi hợp lý, không xuyên tường, dừng đủ lâu ở mỗi không gian.",
        source_modes=("reference_image", "reference_video", "image_prompt"),
    ),
    _idea(
        "space_before_after", "space", "Cải tạo trước và sau",
        "Cho thấy vấn đề của không gian cũ, ý tưởng thay đổi và kết quả mới ở cùng góc nhìn.",
        "Một góc phòng thiếu công năng được giữ khung máy cố định.",
        "Làm rõ giá trị thiết kế/cải tạo.",
        "storyboard_prompt", "space_renovation", "renovation before/after",
        "Cùng cấu trúc phòng và góc máy; chỉ thay đổi vật liệu, nội thất và ánh sáng được yêu cầu.",
        "Dissolve hoặc wipe có động cơ từ hiện trạng sang phương án; không làm biến dạng kiến trúc.",
        source_modes=("reference_image", "image_prompt"),
    ),
    _idea(
        "space_property_highlights", "space", "Ba điểm đáng giá của bất động sản",
        "Mỗi cảnh trình bày một điểm mạnh: vị trí, không gian, tiện ích hoặc tầm nhìn.",
        "Mở bằng tầm nhìn hoặc mặt tiền ấn tượng nhất.",
        "Giúp khách hiểu nhanh giá trị bất động sản.",
        "script_image_video", "real_estate_property", "real-estate cinematic sạch",
        "Ảnh ngoại thất/nội thất đúng tài sản, phối cảnh thẳng, không thêm tiện ích không có thật.",
        "Aerial hoặc FPV có kiểm soát, mỗi cảnh kết ở một điểm nhìn hoàn chỉnh.",
        source_modes=("reference_image", "reference_video", "text_prompt"),
    ),
    _idea(
        "lifestyle_lookbook", "lifestyle", "Lookbook theo ba trạng thái",
        "Mỗi cảnh là một bộ trang phục hoặc thần thái, nối bằng chuyển động cơ thể đồng nhất.",
        "Một động tác xoay người biến đổi diện mạo ngay trong khung hình.",
        "Trình bày thời trang và nhận diện phong cách.",
        "video_ai_real", "fashion_lookbook", "lookbook hiện đại",
        "Giữ gương mặt, cơ thể và sản phẩm; toàn thân rõ, nền sạch, màu trang phục trung thực.",
        "Match cut theo pose, camera dolly nhẹ, mỗi pose hoàn thành trước khi đổi trang phục.",
        source_modes=("reference_image", "reference_video", "image_prompt"),
    ),
    _idea(
        "lifestyle_food_process", "lifestyle", "Ẩm thực từ nguyên liệu đến thưởng thức",
        "Cận cảnh nguyên liệu, thao tác chế biến, thành phẩm và khoảnh khắc thưởng thức.",
        "Âm thanh cắt, rót hoặc xèo tạo điểm dừng cuộn.",
        "Kích thích giác quan và giới thiệu món ăn/quán ăn.",
        "script_image_video", "product_3d_showcase", "food macro ASMR",
        "Nguyên liệu thật, màu thực phẩm tự nhiên, bề mặt chi tiết, không tạo tay hoặc dụng cụ lỗi.",
        "Macro chuyển động chậm ở thao tác chính, giữ nhịp âm thanh, kết bằng hero dish.",
    ),
    _idea(
        "lifestyle_travel_moment", "lifestyle", "Một khoảnh khắc du lịch đáng nhớ",
        "Mở bằng cảnh rộng, theo chân nhân vật khám phá, dừng ở chi tiết địa phương và kết bằng cảm xúc.",
        "Một âm thanh hoặc chuyển động địa phương kéo người xem vào địa điểm.",
        "Gợi cảm hứng du lịch, địa điểm hoặc trải nghiệm.",
        "video_ai_real", "cinematic_vfx", "travel cinematic tự nhiên",
        "Địa điểm nhất quán, con người đúng tỉ lệ, ánh sáng theo cùng thời điểm trong ngày.",
        "Wide-to-close progression, camera chuyển động có đường đi, không teleport giữa các điểm.",
    ),
    _idea(
        "digital_app_demo", "digital", "Ứng dụng giải quyết một việc trong 20 giây",
        "Đặt bài toán, thao tác ba bước trên giao diện và chốt bằng kết quả nhìn thấy được.",
        "Một tác vụ mất nhiều thời gian được rút gọn ngay trước mắt.",
        "Giới thiệu tính năng và lợi ích của ứng dụng.",
        "script_image_video", "app_game_demo", "app demo rõ giao diện",
        "Giao diện đúng sản phẩm, chữ do người dùng cung cấp, vùng chạm và màn hình dễ đọc.",
        "Zoom có kiểm soát vào thao tác, con trỏ/chạm rõ, không tự tạo tính năng không có thật.",
        source_modes=("reference_image", "reference_video", "text_prompt"),
    ),
    _idea(
        "digital_saas_workflow", "digital", "Quy trình trước và sau khi dùng phần mềm",
        "So sánh quy trình thủ công với luồng mới, mỗi cảnh chỉ minh họa một bước thay đổi.",
        "Nhiều cửa sổ và việc lặp lại tạo cảm giác quá tải.",
        "Làm rõ hiệu quả làm việc mà không đưa số liệu chưa xác minh.",
        "storyboard_prompt", "website_saas_demo", "SaaS explainer tối giản",
        "Màn hình sạch, bố cục dashboard nhất quán, không sinh dữ liệu riêng tư hoặc chữ rác.",
        "Chuyển cảnh theo luồng công việc, highlight đúng vùng, kết bằng màn tổng quan ổn định.",
        source_modes=("reference_image", "reference_video", "text_prompt"),
    ),
    _idea(
        "digital_game_teaser", "digital", "Teaser trò chơi bằng một vòng thử thách",
        "Giới thiệu thế giới, mục tiêu, một thử thách và khoảnh khắc chiến thắng ngắn.",
        "Nhân vật nhìn thấy thử thách lớn ngay ở khung đầu.",
        "Tạo tò mò và cho thấy nhịp chơi chính.",
        "video_ai_real", "app_game_demo", "gameplay teaser nguyên bản",
        "Thế giới và nhân vật nguyên bản, HUD nhất quán, không dùng tài sản hoặc nhân vật bản quyền.",
        "Camera theo hành động, mỗi thử thách có mở đầu và kết quả, không cắt giữa đòn hoặc chuyển động.",
    ),
    _idea(
        "visual_event_highlight", "visual", "Điểm nhấn sự kiện theo nhịp cảm xúc",
        "Mở bằng không khí, đi qua ba khoảnh khắc nổi bật và kết bằng phản ứng của người tham dự.",
        "Ánh sáng sân khấu bật lên đúng nhịp đầu tiên.",
        "Tóm tắt sự kiện và tạo cảm giác muốn tham gia.",
        "video_trend", "cinematic_vfx", "event highlight năng lượng",
        "Không gian, màu sự kiện và người tham dự nhất quán; giữ vùng logo an toàn.",
        "Cắt theo nhịp nhưng hoàn tất hành động; xen wide, medium và reaction close-up.",
        source_modes=("reference_video", "reference_image"),
    ),
    _idea(
        "visual_lofi_loop", "visual", "Nhạc hình lặp mượt theo một không gian",
        "Một cảnh có chuyển động môi trường tinh tế, biến đổi ánh sáng và quay về trạng thái đầu.",
        "Một chi tiết nhỏ như mưa, đèn hoặc hơi nước bắt đầu chuyển động.",
        "Tạo visualizer thư giãn, nền nhạc hoặc nội dung lặp.",
        "video_ai_real", "animation_2d_3d", "lofi loop yên tĩnh",
        "Không gian gốc ổn định, chi tiết ít nhưng giàu chiều sâu, vùng trung tâm sạch.",
        "Chuyển động tuần hoàn chậm, frame cuối khớp frame đầu, không rung hoặc đổi hình học.",
    ),
    _idea(
        "visual_transformation", "visual", "Biến đổi phong cách có chủ đích",
        "Một chủ thể đi qua ba trạng thái hình ảnh nhưng giữ nhận diện và động tác liên tục.",
        "Chủ thể chạm vào một vật thể kích hoạt lần biến đổi đầu tiên.",
        "Tạo điểm nhấn thị giác cho chiến dịch hoặc thương hiệu.",
        "storyboard_prompt", "cinematic_vfx", "visual transformation nhất quán",
        "Cùng chủ thể, pose và bố cục qua các phong cách; không sao chép nghệ sĩ hoặc thương hiệu cụ thể.",
        "Morph có điểm neo rõ, hướng chuyển động liên tục, mỗi trạng thái tồn tại đủ lâu để đọc.",
    ),
)

IDEA_BY_ID = {str(item["idea_id"]): item for item in IDEAS}
CATEGORY_LABELS = {key: label for key, label in CATEGORIES}
RELATED_CATEGORIES = {
    "sales": "ugc",
    "ugc": "sales",
    "education": "digital",
    "story": "visual",
    "space": "lifestyle",
    "lifestyle": "sales",
    "digital": "education",
    "visual": "story",
}


def list_categories() -> list[tuple[str, str]]:
    return list(CATEGORIES)


def ideas_for_category(category: str, *, offset: int = 0, limit: int = 5) -> list[dict[str, Any]]:
    selected = str(category or "")
    ordered_categories = (selected, RELATED_CATEGORIES.get(selected, ""))
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for category_key in ordered_categories:
        for item in IDEAS:
            idea_id = str(item["idea_id"])
            if item["category"] == category_key and idea_id not in seen:
                rows.append(item)
                seen.add(idea_id)
    for item in IDEAS:
        idea_id = str(item["idea_id"])
        if idea_id not in seen:
            rows.append(item)
            seen.add(idea_id)
    if not rows:
        return []
    size = max(1, min(int(limit or 5), 5))
    start = max(0, int(offset or 0)) % len(rows)
    ordered = rows[start:] + rows[:start]
    return [deepcopy(item) for item in ordered[:size]]


def idea_by_id(idea_id: str) -> dict[str, Any]:
    return deepcopy(IDEA_BY_ID.get(str(idea_id or ""), {}))


def scene_count_for_duration(duration_seconds: int) -> int:
    duration = max(SCENE_SECONDS, min(int(duration_seconds or SCENE_SECONDS), max(DURATION_OPTIONS)))
    return max(1, min(20, (duration + SCENE_SECONDS - 1) // SCENE_SECONDS))


def apply_custom_note(plan: dict[str, Any], custom_note: str = "") -> dict[str, Any]:
    result = deepcopy(dict(plan or {}))
    note = str(custom_note or "").strip()
    image_seed = str(result.get("image_prompt_seed") or "").strip()
    video_seed = str(result.get("video_prompt_seed") or "").strip()
    result["custom_note"] = note
    result["image_prompt_final"] = f"{image_seed}\nYêu cầu riêng: {note}" if note else image_seed
    result["video_prompt_final"] = f"{video_seed}\nYêu cầu riêng: {note}" if note else video_seed
    return result


def build_plan(
    idea: dict[str, Any],
    *,
    duration_seconds: int = 16,
    source_mode: str = "text_prompt",
    custom_note: str = "",
) -> dict[str, Any]:
    base = deepcopy(dict(idea or {}))
    duration = int(duration_seconds or 16)
    if duration not in DURATION_OPTIONS:
        duration = min(DURATION_OPTIONS, key=lambda value: abs(value - duration))
    scene_count = scene_count_for_duration(duration)
    base.update({
        "selected_topic": str(base.get("title") or "Ý tưởng video"),
        "product": str(base.get("title") or "Ý tưởng video"),
        "context": str(base.get("summary") or ""),
        "idea_kind": "catalog",
        "duration_seconds": duration,
        "scene_count": scene_count,
        "source_mode": str(source_mode or "text_prompt"),
        "custom_note": str(custom_note or "").strip(),
        "prompt_variant_offset": 0,
        "provider_called": False,
        "image_provider_called": False,
        "job_created": False,
        "outbox_created": False,
        "wallet_mutations": 0,
        "xu_charged": 0,
    })
    return apply_custom_note(base, custom_note)


def catalog_status() -> dict[str, Any]:
    return {
        "categories": len(CATEGORIES),
        "ideas": len(IDEAS),
        "duration_options": list(DURATION_OPTIONS),
        "provider_called": False,
        "job_created": False,
        "outbox_created": False,
        "wallet_mutations": 0,
        "xu_charged": 0,
    }
