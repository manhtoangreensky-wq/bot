"""Curated, provider-free idea catalog for the public Video Ideas hub.

The catalog is planning metadata only.  It never creates jobs, calls providers,
generates media, or mutates a wallet.  Public flows may use these records to
prefill an existing product planner before the user's final confirmation.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from . import video_scene3_flow


SCENE_SECONDS = 8
SCENE_COUNT_OPTIONS = (1, 2, 3, 5, 10, 20)
DURATION_OPTIONS = tuple(count * SCENE_SECONDS for count in SCENE_COUNT_OPTIONS)

CATEGORIES = (
    ("sales", "🛍 Bán hàng / quảng cáo"),
    ("ugc", "📱 Mạng xã hội / UGC"),
    ("education", "🎓 Hướng dẫn / kiến thức"),
    ("story", "🎬 Kể chuyện / trailer"),
    ("space", "🏠 Kiến trúc / bất động sản"),
    ("lifestyle", "👗 Thời trang / ẩm thực"),
    ("digital", "💻 Ứng dụng / website / trò chơi"),
    ("visual", "🎧 Sự kiện / nhạc hình / điểm nhấn"),
)

CATEGORY_PLATFORMS = {
    "sales": ("TikTok", "Facebook Reels", "Instagram Reels", "YouTube Shorts"),
    "ugc": ("TikTok", "Facebook Reels", "Instagram Reels", "YouTube Shorts"),
    "education": ("YouTube", "YouTube Shorts", "TikTok", "Facebook Reels"),
    "story": ("YouTube", "TikTok", "Instagram Reels", "Facebook Reels"),
    "space": ("Facebook Reels", "Instagram Reels", "YouTube", "TikTok"),
    "lifestyle": ("TikTok", "Instagram Reels", "YouTube Shorts", "Facebook Reels"),
    "digital": ("YouTube", "TikTok", "Facebook Reels", "Instagram Reels"),
    "visual": ("TikTok", "Instagram Reels", "YouTube Shorts", "Facebook Reels"),
}

CATEGORY_VARIATION_AXES = {
    "sales": ("sản phẩm", "khách hàng", "nỗi đau", "bằng chứng", "lời mời"),
    "ugc": ("nhân vật", "tình huống thật", "cách nói", "bối cảnh", "phản ứng"),
    "education": ("câu hỏi", "mức kiến thức", "ví dụ", "minh họa", "điều cần nhớ"),
    "story": ("nhân vật", "mong muốn", "trở ngại", "bước ngoặt", "kết thúc"),
    "space": ("công trình", "công năng", "vật liệu", "ánh sáng", "lộ trình camera"),
    "lifestyle": ("nhân vật", "hoạt động", "địa điểm", "thời điểm", "cảm xúc"),
    "digital": ("người dùng", "vấn đề", "tính năng", "thao tác", "kết quả"),
    "visual": ("chủ thể", "nhịp", "màu", "chuyển động", "điểm nhấn"),
}

CATEGORY_SCENE_ARCS = {
    "sales": "hook nhu cầu -> giải pháp -> bằng chứng -> kết quả -> lời mời",
    "ugc": "khoảnh khắc thật -> trải nghiệm -> phản ứng -> điều rút ra",
    "education": "câu hỏi -> giải thích -> ví dụ -> áp dụng -> ghi nhớ",
    "story": "thiết lập -> mục tiêu -> trở ngại -> hành động -> kết quả",
    "space": "tiếp cận -> khám phá -> công năng -> chi tiết -> tổng quan",
    "lifestyle": "không gian -> hoạt động -> chi tiết -> cảm xúc -> dư âm",
    "digital": "vấn đề -> thao tác -> tính năng -> kết quả -> bước tiếp theo",
    "visual": "thiết lập nhịp -> biến đổi -> điểm nhấn -> cao trào -> kết khung",
}

# Twenty curated semantic beats per group. A shorter plan samples these beats
# across the full arc; a 20-scene plan uses every beat exactly once. This keeps
# long plans meaningful instead of multiplying one generic sentence.
CATEGORY_BEAT_IDEAS = {
    "sales": (
        "Mở bằng khoảnh khắc vấn đề xuất hiện", "Xác định đúng người đang gặp nhu cầu",
        "Cho thấy hệ quả nếu vấn đề tiếp tục", "Làm rõ kết quả người xem mong muốn",
        "Đặt sản phẩm vào bối cảnh sử dụng thật", "Minh họa cách làm cũ còn bất tiện",
        "Chỉ ra giới hạn cần được giải quyết", "Nêu tiêu chí quan trọng để lựa chọn",
        "Hé lộ giải pháp đúng thời điểm", "Trình bày tính năng chính bằng hình ảnh",
        "Thực hiện trọn một bước sử dụng", "Cho thấy lợi ích thứ hai liên quan trực tiếp",
        "Demo kết quả trong cùng điều kiện", "Đưa bằng chứng hoặc chi tiết kiểm chứng",
        "So sánh trước và sau một cách công bằng", "Ghi lại phản ứng hoặc kết quả thực tế",
        "Làm rõ ai phù hợp với giải pháp", "Tóm tắt giá trị bằng một câu dễ nhớ",
        "Đưa ra bước tiếp theo không gây áp lực", "Khép bằng khung sản phẩm và lời mời rõ",
    ),
    "ugc": (
        "Mở bằng một khoảnh khắc đời thường chân thật", "Giới thiệu người trải nghiệm và nhu cầu cá nhân",
        "Đặt câu chuyện trong bối cảnh một ngày cụ thể", "Làm rõ lý do nhân vật muốn thử",
        "Nói kỳ vọng ban đầu bằng giọng tự nhiên", "Cho thấy nhân vật tình cờ biết tới giải pháp",
        "Mở hộp hoặc chuẩn bị trước khi dùng", "Hoàn tất lần sử dụng đầu tiên",
        "Quan sát một chi tiết đáng chú ý", "Ghi lại phản ứng đầu tiên không cường điệu",
        "Nêu một vướng mắc thật khi trải nghiệm", "Điều chỉnh cách dùng để xử lý vướng mắc",
        "Tiếp tục trải nghiệm trong tình huống khác", "Cho thấy kết quả sau quá trình sử dụng",
        "Chốt điểm mạnh đáng tin nhất", "Nêu một lưu ý hoặc giới hạn cần biết",
        "Giải thích ai sẽ phù hợp", "Rút ra cảm nhận cá nhân sau trải nghiệm",
        "Đưa lời khuyên hoặc lựa chọn tiếp theo", "Khép lại tự nhiên như một nhật ký ngắn",
    ),
    "education": (
        "Đặt câu hỏi trung tâm cần giải đáp", "Cho thấy vì sao câu hỏi này quan trọng",
        "Kết nối với điều người xem đã biết", "Nêu hiểu lầm phổ biến cần loại bỏ",
        "Giải thích khái niệm cốt lõi bằng lời đơn giản", "Làm rõ nguyên tắc đứng sau vấn đề",
        "Trình bày bước đầu tiên có thể làm ngay", "Minh họa bước đầu bằng ví dụ cụ thể",
        "Trình bày bước tiếp theo theo đúng thứ tự", "Minh họa bước tiếp theo bằng tình huống thật",
        "Chỉ ra lỗi thường gặp trong quá trình", "Sửa lỗi bằng một thao tác hoặc quy tắc rõ",
        "Hoàn tất bước cuối và kiểm tra kết quả", "Áp dụng toàn bộ quy trình vào một ca mẫu",
        "So sánh cách đúng với cách dễ nhầm", "Gom các điểm chính thành checklist",
        "Cho thấy cách áp dụng trong đời sống hoặc công việc", "Tóm tắt câu trả lời cho câu hỏi ban đầu",
        "Tạo một dấu hiệu ghi nhớ ngắn", "Khép bằng kết luận và bước học tiếp theo",
    ),
    "story": (
        "Mở bằng một hình ảnh giàu ý nghĩa", "Giới thiệu nhân vật trung tâm",
        "Cho thấy trạng thái bình thường ban đầu", "Làm rõ mong muốn sâu nhất của nhân vật",
        "Đưa sự kiện kích hoạt làm thay đổi tình thế", "Để nhân vật đưa ra lựa chọn đầu tiên",
        "Xuất hiện trở ngại cụ thể", "Ghi lại phản ứng và hậu quả đầu tiên",
        "Nhân vật thử một hành động mới", "Nâng mức rủi ro hoặc cái giá phải trả",
        "Hé lộ thông tin làm thay đổi cách hiểu", "Tạo bước ngoặt buộc nhân vật đổi hướng",
        "Nhân vật thực hiện quyết định quan trọng", "Đưa xung đột tới cao trào",
        "Cho thấy hệ quả trực tiếp của cao trào", "Giải quyết vấn đề chính của câu chuyện",
        "Thể hiện sự thay đổi của nhân vật", "Rút ra ý nghĩa bằng hành động thay vì giảng giải",
        "Trở lại một hình ảnh mở đầu đã biến đổi", "Khép trọn hoặc để lại một câu hỏi có chủ đích",
    ),
    "space": (
        "Định vị công trình trong khu vực", "Tiếp cận công trình theo đường đi hợp lý",
        "Hé lộ hình khối hoặc mặt tiền chính", "Đi qua ngưỡng vào và xác lập trục nhìn",
        "Làm rõ luồng giao thông bên trong", "Trình bày công năng khu vực thứ nhất",
        "Trình bày công năng khu vực thứ hai", "Cận cảnh vật liệu và cách hoàn thiện",
        "Cho thấy ánh sáng tự nhiên đi vào không gian", "Làm rõ tỉ lệ giữa người và kiến trúc",
        "Giới thiệu nội thất hoặc lưu trữ quan trọng", "Cận cảnh một chi tiết thiết kế có lý do",
        "Mở tầm nhìn ra cảnh quan hoặc khoảng trống", "Nối hai không gian qua một ngưỡng rõ",
        "Cho thấy sự thoải mái trong sử dụng", "Minh họa khả năng linh hoạt của không gian",
        "Nêu giải pháp khí hậu hoặc tiết kiệm hợp lý", "Đặt một khoảnh khắc sống thật vào công trình",
        "Tổng hợp các khu vực bằng một đường nhìn", "Khép bằng toàn cảnh công trình đúng hình học",
    ),
    "lifestyle": (
        "Mở bằng một chi tiết giác quan", "Giới thiệu mục tiêu của nhân vật trong ngày",
        "Đặt hoạt động vào đúng không gian và thời điểm", "Chuẩn bị dụng cụ, trang phục hoặc nguyên liệu",
        "Hoàn tất hành động đầu tiên", "Cận cảnh một chi tiết tạo phong cách riêng",
        "Thiết lập nhịp hoạt động tự nhiên", "Chuyển sang hoạt động thứ hai có liên quan",
        "Xuất hiện một trở ngại đời thường", "Nhân vật thích nghi và tiếp tục",
        "Nhấn vào âm thanh, kết cấu hoặc ánh sáng", "Tạo tương tác với người hoặc môi trường",
        "Cho thấy tiến triển sau các hoạt động", "Đạt kết quả nhìn thấy được",
        "Ghi lại cảm xúc sau kết quả", "Chia sẻ một mẹo hữu ích từ trải nghiệm",
        "Khẳng định dấu ấn cá nhân", "Rút ra điều đáng giữ lại",
        "Tạo một khoảnh khắc đáng nhớ", "Khép bằng dư âm tự nhiên của ngày",
    ),
    "digital": (
        "Mở bằng vấn đề của người dùng", "Cho thấy quy trình hiện tại còn rườm rà",
        "Làm rõ thời gian hoặc công sức đang bị lãng phí", "Đặt trạng thái kết quả người dùng mong muốn",
        "Giới thiệu sản phẩm hoặc tính năng đúng lúc", "Hoàn tất thiết lập tối thiểu",
        "Đi qua điều hướng chính", "Thực hiện tính năng cốt lõi đầu tiên",
        "Cho thấy phản hồi giao diện sau thao tác", "Xác nhận kết quả đầu tiên",
        "Mở tính năng hỗ trợ thứ hai", "Minh họa chia sẻ hoặc cộng tác nếu có",
        "Cho thấy phần tự động hóa hợp lệ", "Xử lý một lỗi hoặc tình huống ngoại lệ",
        "Đưa bằng chứng bằng trạng thái giao diện cuối", "Áp dụng vào một trường hợp sử dụng cụ thể",
        "Nêu giới hạn hoặc lưu ý sử dụng", "Tóm tắt luồng thao tác ngắn nhất",
        "Chỉ bước tiếp theo cho người dùng", "Khép bằng màn hình kết quả ổn định",
    ),
    "visual": (
        "Giới thiệu motif thị giác trung tâm", "Xác lập bảng màu chủ đạo",
        "Đưa hình khối hoặc chất liệu đầu tiên", "Thiết lập hướng chuyển động xuyên suốt",
        "Thực hiện lần biến đổi đầu tiên", "Cận cảnh bề mặt và chi tiết",
        "Thay đổi ánh sáng có động cơ", "Xây nhịp bằng chuyển động lặp có kiểm soát",
        "Tạo tương phản hình ảnh rõ", "Thực hiện lần biến đổi thứ hai có liên hệ",
        "Mở rộng quy mô khung hình", "Đổi góc máy nhưng giữ điểm neo",
        "Đồng bộ chuyển động với âm thanh", "Tạo một nhịp nghỉ để người xem nhận hình",
        "Đẩy hình ảnh tới cao trào", "Giải phóng năng lượng và ổn định bố cục",
        "Nối lại motif để tạo tính liên tục", "Chừa vùng an toàn cho nhận diện nếu cần",
        "Gom các yếu tố vào một bố cục hoàn chỉnh", "Khép bằng end frame rõ hoặc vòng lặp mượt",
    ),
}


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
    platforms: tuple[str, ...] = (),
    formats: tuple[str, ...] = (),
    variation_axes: tuple[str, ...] = (),
    scene_arc: str = "",
) -> dict[str, Any]:
    platform_values = platforms or CATEGORY_PLATFORMS.get(category, ())
    variation_values = variation_axes or CATEGORY_VARIATION_AXES.get(category, ())
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
        "platform_fit": list(platform_values),
        "format_tags": list(formats),
        "variation_axes": list(variation_values),
        "scene_arc": str(scene_arc or CATEGORY_SCENE_ARCS.get(category, "")),
        "duration_options": list(DURATION_OPTIONS),
        "scene_count_options": list(SCENE_COUNT_OPTIONS),
        "scene_seconds": SCENE_SECONDS,
        "reference_only": True,
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
    _idea(
        "sales_testimonial_proof", "sales", "Khách hàng kể kết quả có bằng chứng",
        "Mở bằng kết quả thật, quay lại nhu cầu ban đầu, cho thấy cách dùng và kết bằng đánh giá cân bằng.",
        "Một câu nhận xét ngắn đi thẳng vào thay đổi người xem quan tâm.",
        "Tạo bằng chứng xã hội mà không phóng đại hoặc dựng lời chứng thực giả.",
        "video_trend", "ugc_social_creator", "testimonial chân thật, nhịp mạng xã hội",
        "Khách hàng trong bối cảnh sử dụng thật, sản phẩm rõ, vùng chữ an toàn và nhận diện nhất quán.",
        "Bắt đầu bằng kết quả, minh họa trải nghiệm theo trình tự, kết bằng một nhận xét đáng tin và CTA nhẹ.",
        formats=("testimonial", "social proof", "reaction"),
    ),
    _idea(
        "sales_comparison_list", "sales", "So sánh để chọn đúng",
        "Đặt hai phương án cạnh nhau, so từng tiêu chí quan trọng và kết luận phương án hợp từng nhu cầu.",
        "Một lựa chọn tưởng giống nhau nhưng khác ở chi tiết quyết định.",
        "Giúp khách ra quyết định bằng tiêu chí rõ thay vì công kích đối thủ.",
        "script_image_video", "product_3d_showcase", "comparison sạch, trực quan",
        "Hai phương án cùng góc nhìn, tỉ lệ và ánh sáng; chỉ hiển thị dữ kiện được cung cấp.",
        "Mỗi cảnh hoàn tất một tiêu chí, giữ bố cục đối chiếu và kết bằng hướng chọn theo nhu cầu.",
        formats=("comparison", "listicle", "buyer guide"),
    ),
    _idea(
        "sales_objection_faq", "sales", "Ba băn khoăn trước khi mua",
        "Dùng câu hỏi thật của khách, trả lời ngắn bằng demo hoặc bằng chứng rồi chốt điều kiện phù hợp.",
        "Câu hỏi khó nhất xuất hiện ngay đầu thay vì né tránh.",
        "Giảm do dự và làm rõ giới hạn sử dụng một cách minh bạch.",
        "video_ai_real", "tutorial_explainer", "FAQ nhanh, đáng tin",
        "Minh họa đúng từng câu hỏi, vùng chữ rõ, không tự sinh cam kết hoặc con số.",
        "Một cảnh cho một băn khoăn và câu trả lời hoàn chỉnh; cảnh cuối tóm tắt ai nên chọn.",
        formats=("FAQ", "objection handling", "explainer"),
    ),
    _idea(
        "ugc_grwm_routine", "ugc", "Chuẩn bị cùng tôi theo một routine",
        "Theo nhân vật qua các bước chuẩn bị tự nhiên, mỗi bước có mục đích và kết quả nhìn thấy được.",
        "Nhân vật mở đầu bằng mục tiêu cụ thể của ngày hôm đó.",
        "Đưa sản phẩm hoặc thói quen vào đời sống mà không biến thành quảng cáo đọc sẵn.",
        "video_trend", "ugc_social_creator", "GRWM gần gũi, dọc 9:16",
        "Cùng nhân vật, không gian và sản phẩm; ánh sáng điện thoại tự nhiên, vùng caption an toàn.",
        "Mỗi cảnh kết thúc một bước chuẩn bị, nối bằng động tác tay hoặc thay đổi trang phục có chủ đích.",
        formats=("GRWM", "routine", "day in life"),
    ),
    _idea(
        "ugc_first_impression", "ugc", "Ấn tượng đầu tiên và kiểm tra nhanh",
        "Ghi lại kỳ vọng, khoảnh khắc trải nghiệm đầu tiên, một kiểm tra thực tế và kết luận ban đầu.",
        "Phản ứng đầu tiên xuất hiện trước khi giải thích chi tiết.",
        "Tạo cảm giác khám phá thật và phân biệt phản ứng với kết luận dài hạn.",
        "video_ai_real", "ugc_social_creator", "first impression tự nhiên",
        "Gương mặt, sản phẩm và ánh sáng nhất quán; biểu cảm vừa phải, không cường điệu.",
        "Phản ứng mở đầu, thao tác kiểm tra trọn vẹn, cận cảnh kết quả, kết bằng nhận xét có giới hạn.",
        formats=("first impression", "reaction", "quick test"),
    ),
    _idea(
        "ugc_behind_scenes", "ugc", "Hậu trường một sản phẩm hoặc công việc",
        "Cho thấy chuẩn bị, một khó khăn thật, cách xử lý và thành phẩm cuối từ góc nhìn người làm.",
        "Mở bằng khoảnh khắc ít người thường được thấy.",
        "Tăng độ gần gũi và cho thấy giá trị của quy trình phía sau kết quả.",
        "video_trend", "ugc_social_creator", "behind-the-scenes chân thật",
        "Không gian làm việc thật, dụng cụ đúng vị trí, nhân vật và tiến độ nhất quán.",
        "Đi theo trình tự công việc; không cắt giữa thao tác quan trọng; thành phẩm là cảnh kết rõ ràng.",
        formats=("behind the scenes", "process", "creator diary"),
    ),
    _idea(
        "education_case_study", "education", "Ca thực tế: từ vấn đề đến bài học",
        "Nêu bối cảnh, mục tiêu, quyết định chính, kết quả và bài học có thể áp dụng.",
        "Kết quả xuất hiện trước rồi câu chuyện quay lại điểm xuất phát.",
        "Giải thích tư duy và quá trình, không chỉ khoe kết quả.",
        "script_image_video", "tutorial_explainer", "case study có cấu trúc",
        "Mốc trước/sau và dữ kiện do người dùng cung cấp; không tự tạo số liệu hoặc logo.",
        "Mỗi cảnh làm rõ một mốc quyết định, kết bằng bài học nối trực tiếp sang mốc kế tiếp.",
        formats=("case study", "breakdown", "before after"),
    ),
    _idea(
        "education_checklist", "education", "Checklist tránh lỗi phổ biến",
        "Mở bằng lỗi thường gặp, đi qua từng mục kiểm tra và kết bằng một quy trình ngắn dễ lưu lại.",
        "Một lỗi nhỏ gây hậu quả lớn được minh họa ngay đầu.",
        "Cho người xem một danh sách có thể áp dụng ngay.",
        "script_image_video", "tutorial_explainer", "checklist rõ, dễ lưu",
        "Minh họa riêng cho từng mục, vùng chữ rộng, biểu tượng nhất quán và không có chữ rác.",
        "Một cảnh cho một mục kiểm tra; hoàn tất ví dụ trước khi chuyển; cảnh cuối gom thành quy trình.",
        formats=("checklist", "listicle", "mistakes to avoid"),
    ),
    _idea(
        "education_question_answer", "education", "Hỏi nhanh, trả lời bằng minh họa",
        "Chọn các câu hỏi liên quan cùng một chủ đề, trả lời từng câu bằng ví dụ ngắn và kết luận chung.",
        "Câu hỏi gây tranh luận nhất được đưa lên đầu.",
        "Biến FAQ thành nội dung dễ hiểu, nhất quán và không lan sang chủ đề khác.",
        "video_ai_real", "tutorial_explainer", "Q&A trực quan",
        "Bố cục hỏi/đáp rõ, minh họa đúng chủ đề và chỉ dùng thông tin được xác nhận.",
        "Câu hỏi, câu trả lời và ví dụ nằm trọn trong một cảnh; âm thanh nối nhẹ giữa các câu.",
        formats=("Q&A", "FAQ", "expert answer"),
    ),
    _idea(
        "story_mini_documentary", "story", "Phóng sự ngắn về một con người hoặc nơi chốn",
        "Theo một chủ thể thật qua bối cảnh, động lực, công việc và khoảnh khắc có ý nghĩa.",
        "Một chi tiết đời thường hé lộ câu chuyện lớn hơn phía sau.",
        "Tạo chân dung giàu cảm xúc nhưng không bịa lời nói hoặc sự kiện.",
        "video_ai_real", "character", "mini documentary quan sát",
        "Nhân vật, địa điểm và thời gian nhất quán; hình ảnh tôn trọng chủ thể, không sân khấu hóa quá mức.",
        "Cảnh rộng đặt bối cảnh, hành động thật phát triển câu chuyện, chi tiết cá nhân và kết bằng dư âm.",
        formats=("mini documentary", "portrait", "human story"),
    ),
    _idea(
        "story_mystery_reveal", "story", "Bí ẩn được giải bằng từng manh mối",
        "Mỗi cảnh đưa một manh mối có ý nghĩa, tăng dần hiểu biết và kết bằng lời giải hợp lý.",
        "Một vật thể sai chỗ khiến nhân vật dừng lại quan sát.",
        "Tạo tò mò mà vẫn trả lời trọn vẹn, không kéo dài bằng cảnh vô nghĩa.",
        "script_image_video", "cinematic_vfx", "mystery điện ảnh nguyên bản",
        "Motif manh mối lặp lại, không gian và ánh sáng có logic, nhân vật nguyên bản.",
        "Mỗi manh mối được nhìn thấy và xử lý trọn; chuyển cảnh theo hướng nhìn; cảnh cuối giải đáp rõ.",
        formats=("mystery", "reveal", "clue trail"),
    ),
    _idea(
        "story_comedy_payoff", "story", "Tình huống hài có setup và payoff",
        "Thiết lập quy tắc bình thường, tạo hiểu lầm, đẩy tình huống và kết bằng cú đảo hợp lý.",
        "Một hành động rất nghiêm túc dẫn tới chi tiết bất ngờ.",
        "Tạo nội dung vui có nhịp rõ, không dựa vào nhân vật hoặc meme bản quyền.",
        "video_trend", "character", "hài tình huống gọn",
        "Nhân vật, đạo cụ và hướng nhìn nhất quán; biểu cảm tự nhiên, không méo mặt.",
        "Setup đủ rõ, phản ứng hoàn chỉnh, nhịp dừng trước payoff và khung kết giữ đủ lâu.",
        formats=("comedy sketch", "setup payoff", "relatable humor"),
    ),
    _idea(
        "space_exterior_arrival", "space", "Ngoại thất từ đường phố đến mặt tiền",
        "Dẫn người xem từ bối cảnh khu vực tới lối vào, hình khối, vật liệu và điểm nhấn mặt đứng.",
        "Công trình được hé lộ dần sau một lớp cảnh quan tiền cảnh.",
        "Trình bày kiến trúc ngoại thất đúng hình học và quan hệ với môi trường.",
        "video_ai_real", "architecture_exterior", "architectural exterior chân thật",
        "Giữ tuyệt đối khối tích, cửa, mái, vật liệu, cảnh quan và tỉ lệ công trình tham chiếu.",
        "Camera tiếp cận theo đường có thật, dừng ở từng mặt đứng, không xuyên vật thể hoặc đổi kết cấu.",
        source_modes=("reference_image", "reference_video", "image_prompt"),
        formats=("curb appeal", "exterior reveal", "architecture film"),
    ),
    _idea(
        "space_interior_flow", "space", "Nội thất theo luồng sử dụng",
        "Đi qua lối vào, khu sinh hoạt, điểm lưu trữ và chi tiết vật liệu theo một đường di chuyển hợp lý.",
        "Ánh sáng từ phòng chính dẫn mắt người xem qua ngưỡng cửa.",
        "Giải thích công năng và cảm giác nội thất mà không làm sai mặt bằng.",
        "video_ai_real", "architecture_interior", "interior walkthrough tinh tế",
        "Giữ mặt bằng, đồ nội thất, vật liệu, cửa và nguồn sáng; không thêm phòng hoặc thay tỉ lệ.",
        "Camera ngang tầm mắt, hoàn tất quan sát mỗi vùng, nối bằng doorway reveal và chuyển động chậm.",
        source_modes=("reference_image", "reference_video", "image_prompt"),
        formats=("interior tour", "room flow", "design detail"),
    ),
    _idea(
        "space_neighborhood_lifestyle", "space", "Bất động sản gắn với nhịp sống khu vực",
        "Kết nối đường đến, tiện ích thật, không gian bên trong và một khoảnh khắc sinh hoạt phù hợp.",
        "Mở bằng quãng đường hoặc tiện ích có ý nghĩa nhất với khách mục tiêu.",
        "Giúp người xem hình dung trải nghiệm sống thay vì chỉ xem phòng trống.",
        "script_image_video", "real_estate_property", "property lifestyle có kiểm chứng",
        "Chỉ dùng địa điểm và tiện ích được cung cấp; tài sản và nhân vật giữ nhất quán.",
        "Từ khu vực tới công trình rồi vào không gian sống; mỗi cảnh kết ở một điểm định vị rõ.",
        formats=("neighborhood guide", "property lifestyle", "location story"),
    ),
    _idea(
        "lifestyle_beauty_routine", "lifestyle", "Routine chăm sóc theo từng bước",
        "Mở bằng nhu cầu, thực hiện từng bước đúng thứ tự và kết bằng trạng thái hoàn thiện tự nhiên.",
        "Cận cảnh kết cấu hoặc thao tác đầu tiên tạo điểm dừng cuộn.",
        "Giải thích routine dễ làm theo, không đưa tuyên bố y tế chưa xác minh.",
        "video_trend", "fashion_lookbook", "beauty routine sạch",
        "Giữ gương mặt, da, sản phẩm và ánh sáng; bàn tay đúng, nhãn chỉ hiện khi có tham chiếu.",
        "Mỗi cảnh hoàn tất một bước, match cut theo tay và giữ vùng dưới an toàn cho phụ đề.",
        formats=("beauty routine", "get ready", "step by step"),
    ),
    _idea(
        "lifestyle_fitness_progress", "lifestyle", "Một buổi tập có mục tiêu rõ",
        "Đặt mục tiêu, khởi động, thực hiện động tác chính, hồi phục và kết bằng cảm nhận sau buổi tập.",
        "Mục tiêu cụ thể xuất hiện trước động tác đầu tiên.",
        "Tạo nội dung vận động có trình tự, không cổ vũ kỹ thuật nguy hiểm.",
        "video_ai_real", "ugc_social_creator", "fitness đời thường, năng lượng",
        "Cùng nhân vật, trang phục và không gian; tư thế cơ thể hợp lý, không biến dạng chi.",
        "Hoàn tất một hiệp hoặc động tác trước khi cắt; nhịp tăng dần rồi hạ ở cảnh hồi phục.",
        formats=("workout routine", "progress diary", "fitness tips"),
    ),
    _idea(
        "lifestyle_travel_itinerary", "lifestyle", "Lịch trình ngắn theo một tuyến hợp lý",
        "Đi từ điểm bắt đầu qua các trải nghiệm cùng khu vực và kết ở khoảnh khắc đáng nhớ nhất.",
        "Bản đồ hoặc dấu mốc mở ra điểm đến đầu tiên.",
        "Gợi ý hành trình có mạch, tránh ghép các địa điểm xa nhau vô lý.",
        "script_image_video", "cinematic_vfx", "travel itinerary giàu không khí",
        "Đúng địa điểm, thời tiết và thời gian trong ngày; cùng nhân vật và trang phục khi liên tục thời gian.",
        "Mỗi cảnh hoàn tất một trải nghiệm, chuyển bằng hướng đi hoặc âm thanh địa phương, kết ở điểm cuối.",
        formats=("travel itinerary", "destination guide", "day trip"),
    ),
    _idea(
        "digital_feature_launch", "digital", "Ra mắt một tính năng bằng tình huống thật",
        "Cho thấy vấn đề, mở tính năng, thao tác chính và kết quả trong một luồng người dùng hoàn chỉnh.",
        "Một thao tác cũ rườm rà được đặt cạnh nút mới đơn giản hơn.",
        "Giải thích lợi ích của tính năng mà không hứa điều sản phẩm chưa có.",
        "script_image_video", "app_game_demo", "feature launch rõ giao diện",
        "Giao diện, màu thương hiệu và dữ liệu mẫu nhất quán; chữ chỉ lấy từ nội dung được cung cấp.",
        "Camera màn hình theo đúng luồng thao tác, mỗi cảnh kết ở một trạng thái UI ổn định.",
        formats=("feature launch", "product update", "app demo"),
    ),
    _idea(
        "digital_onboarding", "digital", "Onboarding từ đăng nhập đến giá trị đầu tiên",
        "Dẫn người dùng qua thiết lập tối thiểu, hành động chính và khoảnh khắc nhận kết quả đầu tiên.",
        "Mở bằng đích đến thay vì liệt kê mọi cài đặt.",
        "Giảm cảm giác phức tạp và chỉ dẫn đúng những bước cần thiết.",
        "storyboard_prompt", "website_saas_demo", "SaaS onboarding tối giản",
        "Màn hình đúng sản phẩm, dữ liệu minh họa an toàn, bố cục và con trỏ nhất quán.",
        "Một cảnh cho một bước thiết yếu, zoom vừa đủ, hoàn tất thao tác trước khi sang màn kế tiếp.",
        formats=("onboarding", "walkthrough", "first value"),
    ),
    _idea(
        "digital_tip_hack", "digital", "Mẹo nhanh cho một tác vụ cụ thể",
        "Nêu tác vụ, cho cách thường làm, chỉ thao tác nhanh hơn và so kết quả cuối.",
        "Phím tắt hoặc thao tác ít người biết xuất hiện ngay đầu.",
        "Dạy một mẹo dùng được ngay mà không gom quá nhiều tính năng vào một video.",
        "video_trend", "tutorial_explainer", "tech tip nhanh, dễ lưu",
        "Giao diện đọc được, vùng thao tác nổi bật, không tự tạo menu hoặc chức năng.",
        "Mỗi cảnh là một bước trọn vẹn; con trỏ dừng sau thao tác; cảnh cuối nhắc lại quy trình ngắn.",
        formats=("tip", "hack", "screen tutorial"),
    ),
    _idea(
        "visual_kinetic_typography", "visual", "Chữ chuyển động theo nhịp thông điệp",
        "Chia thông điệp thành các cụm ngắn, mỗi cụm có một chuyển động và kết ở câu chính dễ nhớ.",
        "Từ khóa đầu tiên xuất hiện đồng bộ với nhịp âm thanh.",
        "Tạo video chữ có trật tự, đọc được và không biến thành chuỗi hiệu ứng ngẫu nhiên.",
        "script_image_video", "animation_2d_3d", "kinetic typography sạch",
        "Chỉ dùng nội dung chữ được cung cấp, phông dễ đọc, màu tương phản và vùng an toàn nền tảng.",
        "Mỗi cảnh hoàn tất một cụm ý, chuyển động chữ dừng trước khi nối, câu cuối giữ ổn định.",
        formats=("kinetic typography", "quote video", "text animation"),
    ),
    _idea(
        "visual_character_evolution", "visual", "Nhân vật thay đổi qua các cột mốc",
        "Giữ một nhân vật xuyên suốt, mỗi cảnh là một cột mốc có nguyên nhân và trạng thái mới rõ ràng.",
        "Một chi tiết nhận diện được giữ nguyên giữa hai trạng thái đối lập.",
        "Kể quá trình phát triển nhân vật mà không đổi gương mặt hoặc thiết kế vô cớ.",
        "storyboard_prompt", "animation_2d_3d", "character evolution liền mạch",
        "Character bible rõ, cùng gương mặt và tỉ lệ; thay đổi trang phục/bối cảnh chỉ theo mốc truyện.",
        "Mỗi biến đổi hoàn tất trong một cảnh, pose cuối làm điểm neo cho cảnh kế tiếp.",
        formats=("character evolution", "transformation", "animated story"),
    ),
    _idea(
        "visual_macro_rhythm", "visual", "Cận cảnh vật liệu theo nhịp âm thanh",
        "Dùng các chi tiết bề mặt, thao tác và ánh sáng để xây nhịp rồi kết bằng toàn cảnh chủ thể.",
        "Một âm thanh nhỏ làm chuyển động vật liệu bắt đầu.",
        "Tạo điểm nhấn cảm giác cho sản phẩm, sự kiện hoặc nhạc hình.",
        "video_ai_real", "product_3d_showcase", "macro sensory cao cấp",
        "Vật liệu trung thực, logo chỉ từ tham chiếu, ánh sáng và màu thương hiệu nhất quán.",
        "Macro theo nhịp, hoàn tất từng thao tác, tăng dần quy mô khung hình và kết bằng hero shot.",
        formats=("macro", "ASMR visual", "product visualizer"),
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

LEGACY_CINEMA_ACTIONS = frozenset({
    "cinema_refresh", "cinema_custom", "cinema_choice", "genre",
})
LEGACY_GUIDED_ACTIONS = frozenset({
    "product_type", "product_refresh", "product_custom", "product_choice",
    "back_product_type", "back_description", "back_goal", "back_context",
    "back_choices", "idea_refresh", "goal_custom", "goal", "context_custom",
    "context", "choose", "choice_custom",
})
LEGACY_RESULT_ACTIONS = frozenset({
    "catalog_source", "catalog_back_source", "catalog_edit",
    "catalog_image_prompt", "catalog_video_prompt", "routes",
    "finalization", "frame_video", "render_ai", "storyboard",
    "image_prompts", "video_prompts", "music",
})


def legacy_callback_target(
    action: str,
    value: str = "",
    state: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Map retired idea callbacks to one canonical reference-library screen."""

    action_key = str(action or "").strip()
    value_key = str(value or "").strip()
    current = dict(state or {})
    current_category = str(current.get("catalog_category") or current.get("category") or "")
    if current_category not in CATEGORY_LABELS:
        current_category = "story" if str(current.get("idea_kind") or "") == "cinema" else "sales"

    if action_key == "source_start":
        return {"screen": "categories", "category": ""}
    if action_key == "kind":
        if value_key == "ad":
            return {"screen": "options", "category": "sales"}
        if value_key == "cinema":
            return {"screen": "options", "category": "story"}
        return {"screen": "categories", "category": ""}
    if action_key in LEGACY_CINEMA_ACTIONS:
        return {"screen": "options", "category": "story"}
    if action_key in LEGACY_RESULT_ACTIONS:
        idea_id = str(current.get("catalog_idea_id") or current.get("idea_id") or "")
        screen = "result" if idea_id in IDEA_BY_ID else "options"
        return {"screen": screen, "category": current_category}
    if action_key in LEGACY_GUIDED_ACTIONS:
        return {"screen": "options", "category": current_category}
    return {}


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


def duration_for_scene_count(scene_count: int) -> int:
    return max(1, min(20, int(scene_count or 1))) * SCENE_SECONDS


def semantic_beats_for_idea(idea: dict[str, Any], scene_count: int) -> list[dict[str, Any]]:
    count = max(1, min(20, int(scene_count or 1)))
    category = str((idea or {}).get("category") or "story")
    library = CATEGORY_BEAT_IDEAS.get(category) or CATEGORY_BEAT_IDEAS["story"]
    title = str((idea or {}).get("title") or "ý tưởng video").strip()
    if count == 1:
        positions = [0]
        selected = [f"Trình bày trọn vẹn {title}: mở rõ, phát triển một hành động chính và khép bằng kết quả"]
    else:
        positions = [round(index * (len(library) - 1) / (count - 1)) for index in range(count)]
        selected = [library[position] for position in positions]
    beats: list[dict[str, Any]] = []
    for index, (position, main_idea) in enumerate(zip(positions, selected), 1):
        is_last = index == count
        beats.append({
            "role": f"{category}_conclusion" if is_last else f"{category}_beat_{position + 1:02d}",
            "main_idea": main_idea,
            "action": (
                f"Thể hiện trọn vẹn {main_idea.lower()} bằng một hành động hoặc diễn biến cụ thể liên quan trực tiếp tới {title}."
            ),
            "development": (
                "Bắt đầu bằng trạng thái dễ hiểu, phát triển đúng một ý, hoàn tất hành động và giữ trạng thái cuối đủ rõ để nối cảnh."
            ),
            "completion": (
                f"Toàn bộ ý tưởng {title} đã khép lại bằng một kết quả rõ ràng."
                if is_last else
                f"{main_idea} đã hoàn tất; trạng thái cuối mở tự nhiên sang ý kế tiếp."
            ),
        })
    return beats


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
    scene_count: int | None = None,
    source_mode: str = "text_prompt",
    custom_note: str = "",
) -> dict[str, Any]:
    base = deepcopy(dict(idea or {}))
    if scene_count is None:
        duration = int(duration_seconds or 16)
        if duration not in DURATION_OPTIONS:
            duration = min(DURATION_OPTIONS, key=lambda value: abs(value - duration))
        selected_scene_count = scene_count_for_duration(duration)
    else:
        selected_scene_count = max(1, min(20, int(scene_count or 1)))
        duration = duration_for_scene_count(selected_scene_count)
    base.update({
        "selected_topic": str(base.get("title") or "Ý tưởng video"),
        "product": str(base.get("title") or "Ý tưởng video"),
        "context": str(base.get("summary") or ""),
        "idea_kind": "catalog",
        "duration_seconds": duration,
        "scene_count": selected_scene_count,
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


def recommended_handoff_product(plan: dict[str, Any]) -> str:
    """Choose one text/scene-capable public route for the reference idea."""

    recommended = str((plan or {}).get("recommended_product_id") or "video_ai_real")
    aliases = {
        "storyboard_prompt": "script_image_video",
        "self_shot_scene_change": "video_ai_real",
        "multi_scene_film": "video_ai_real",
    }
    return aliases.get(recommended, recommended if recommended in {"video_trend", "video_ai_real", "script_image_video"} else "video_ai_real")


def build_scene3_handoff_state(plan: dict[str, Any]) -> dict[str, Any]:
    """Turn one reference idea into exact-N editable scene prompts, provider-free."""

    source = deepcopy(dict(plan or {}))
    count = max(1, min(20, int(source.get("scene_count") or 1)))
    product_id = recommended_handoff_product(source)
    profile_id = str(source.get("recommended_profile_id") or "tutorial_explainer")
    valid_profiles = {key for key, _label in video_scene3_flow.TECHNICAL_PROFILES}
    if profile_id not in valid_profiles:
        profile_id = "tutorial_explainer"
    title = str(source.get("title") or source.get("selected_topic") or "Ý tưởng video").strip()
    context_parts = [
        str(source.get("summary") or "").strip(),
        f"Hướng mở đầu: {str(source.get('hook') or '').strip()}",
        f"Mục tiêu: {str(source.get('objective') or '').strip()}",
    ]
    custom_note = str(source.get("custom_note") or "").strip()
    if custom_note:
        context_parts.append(f"Điều chỉnh riêng: {custom_note}")
    context = " ".join(part for part in context_parts if part and not part.endswith(": "))
    state = video_scene3_flow.default_state(product_type=product_id, subject=title, aspect_ratio="9:16")
    state.update({
        "step": "video_prompts",
        "history": ["video_idea_result"],
        "product_type": product_id,
        "source_product_id": product_id,
        "scene_count": count,
        "content_type": video_scene3_flow.content_type_for_profile(profile_id, state),
        "technical_profile": profile_id,
        "context": context,
        "profile_context": context,
        "selected_suggestion": {
            "title": title,
            "detail": str(source.get("summary") or ""),
            "hook": str(source.get("hook") or ""),
            "objective": str(source.get("objective") or ""),
        },
        "origin": "video_idea_catalog",
        "idea_return_callback": "videoidea|catalog_result",
        "catalog_idea_id": str(source.get("catalog_idea_id") or source.get("idea_id") or ""),
        "selected_video_idea": source,
        "idea_scene_beats": semantic_beats_for_idea(source, count),
        "idea_planning_brief": {
            "scene_arc": str(source.get("scene_arc") or ""),
            "image_direction": str(source.get("image_prompt_final") or source.get("image_prompt_seed") or ""),
            "motion_direction": str(source.get("video_prompt_final") or source.get("video_prompt_seed") or ""),
            "platform_fit": list(source.get("platform_fit") or []),
            "variation_axes": list(source.get("variation_axes") or []),
        },
        "provider_called": False,
        "image_provider_called": False,
        "music_provider_calls": 0,
        "voice_provider_calls": 0,
        "files_generated": 0,
        "job_created": False,
        "outbox_created": False,
        "wallet_mutations": 0,
        "xu_charged": 0,
    })
    creative = dict(state.get("creative_controls") or {})
    for key, value in {
        "context": context,
        "visual_style": str(source.get("style") or ""),
        "pacing": "Mỗi cảnh hoàn tất một ý hoặc hành động trước khi chuyển; toàn bộ cảnh cùng phục vụ một chủ đề.",
    }.items():
        entry = dict(creative.get(key) or {})
        entry.update({"enabled": bool(value), "value": value})
        creative[key] = entry
    state["creative_controls"] = creative
    state = video_scene3_flow.build_planning_package(state)
    state.update({
        "step": "video_prompts",
        "history": ["video_idea_result"],
        "origin": "video_idea_catalog",
        "idea_return_callback": "videoidea|catalog_result",
        "selected_video_idea": source,
        "final_confirmed": False,
        "provider_called": False,
        "image_provider_called": False,
        "music_provider_calls": 0,
        "voice_provider_calls": 0,
        "files_generated": 0,
        "job_created": False,
        "outbox_created": False,
        "wallet_mutations": 0,
        "xu_charged": 0,
    })
    return video_scene3_flow.normalize_state(state)


def catalog_status() -> dict[str, Any]:
    return {
        "categories": len(CATEGORIES),
        "ideas": len(IDEAS),
        "scene_count_options": list(SCENE_COUNT_OPTIONS),
        "duration_options": list(DURATION_OPTIONS),
        "reference_only": True,
        "provider_called": False,
        "job_created": False,
        "outbox_created": False,
        "wallet_mutations": 0,
        "xu_charged": 0,
    }
