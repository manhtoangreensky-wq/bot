"""Curated, provider-free idea catalog for the public Video Ideas hub.

The catalog is planning metadata only.  It never creates jobs, calls providers,
generates media, or mutates a wallet.  Public flows may use these records to
prefill an existing product planner before the user's final confirmation.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from . import video_profile_catalog, video_scene3_flow


SCENE_SECONDS = 8
ASPECT_RATIO_OPTIONS = ("9:16", "16:9", "1:1", "4:5")
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
    ("history", "🏺 Lịch sử / Văn hóa & Thần thoại"),
    ("sports", "🏆 Thể thao / Thể thao điện tử"),
    ("travel", "🧭 Du lịch / Trải nghiệm địa phương"),
    ("industry", "🏭 Kỹ thuật / Công nghiệp & Tự động hóa"),
    ("data_news", "📊 Tin tức / Phân tích dữ liệu"),
    ("self_help", "🌱 Động lực / Phát triển bản thân"),
    ("meme", "🎭 Giải trí / Meme / Bắt trend"),
    ("asmr", "🌧 ASMR / Thư giãn / Lofi & Chill"),
)

CATEGORY_METADATA = {
    "sales": ("🛍", "Bán hàng / quảng cáo", "Bán hàng", "Ý tưởng giới thiệu sản phẩm, chứng minh lợi ích và kêu gọi hành động đáng tin."),
    "ugc": ("📱", "Mạng xã hội / UGC", "Mạng xã hội", "Ý tưởng đời thường, góc nhìn người dùng và nội dung ngắn phù hợp mạng xã hội."),
    "education": ("🎓", "Hướng dẫn / kiến thức", "Hướng dẫn", "Giải thích kiến thức, quy trình và mẹo thực hành theo từng bước rõ ràng."),
    "story": ("🎬", "Kể chuyện / trailer", "Kể chuyện", "Ý tưởng có nhân vật, xung đột, bước ngoặt và kết thúc trọn vẹn."),
    "space": ("🏠", "Kiến trúc / bất động sản", "Kiến trúc", "Khám phá công trình, nội thất, bất động sản và trải nghiệm không gian đúng hình học."),
    "lifestyle": ("👗", "Thời trang / ẩm thực", "Đời sống", "Thời trang, ẩm thực, làm đẹp, sức khỏe và trải nghiệm đời sống giàu cảm giác."),
    "digital": ("💻", "Ứng dụng / website / trò chơi", "Sản phẩm số", "Demo ứng dụng, website, trò chơi và quy trình số bằng luồng thao tác thật dễ hiểu."),
    "visual": ("🎧", "Sự kiện / nhạc hình / điểm nhấn", "Nhạc hình", "Video nhịp điệu, sự kiện, đồ họa chuyển động và điểm nhấn thị giác."),
    "history": ("🏺", "Lịch sử / Văn hóa & Thần thoại", "Lịch sử", "Kể lịch sử, văn hóa và truyền thuyết bằng hình ảnh điện ảnh nhưng phân biệt rõ dữ kiện với giai thoại."),
    "sports": ("🏆", "Thể thao / Thể thao điện tử", "Thể thao", "Khung nội dung nhận định, chiến thuật và tin nhanh; dữ liệu hiện thời phải được xác minh riêng."),
    "travel": ("🧭", "Du lịch / Trải nghiệm địa phương", "Du lịch", "Review địa phương, hành trình, nightlife và nghỉ dưỡng theo góc nhìn chân thực."),
    "industry": ("🏭", "Kỹ thuật / Công nghiệp & Tự động hóa", "Kỹ thuật", "Showcase quy trình kỹ thuật, giải pháp B2B, công nghiệp và tự động hóa an toàn."),
    "data_news": ("📊", "Tin tức / Phân tích dữ liệu", "Dữ liệu", "Tóm tắt tin và trực quan hóa số liệu; không bịa dữ liệu, không hứa dự đoán chắc thắng."),
    "self_help": ("🌱", "Động lực / Phát triển bản thân", "Phát triển", "Podcast ngắn, định hướng và thói quen tích cực nhưng không hứa hẹn thành công chắc chắn."),
    "meme": ("🎭", "Giải trí / Meme / Bắt trend", "Meme / trend", "POV, parody và meme nguyên bản; không mạo danh hoặc sao chép giọng người thật khi chưa được phép."),
    "asmr": ("🌧", "ASMR / Thư giãn / Lofi & Chill", "ASMR / Lofi", "Không gian âm thanh, thao tác thư giãn và lofi; toàn bộ âm thanh mới chỉ là kế hoạch trước xác nhận."),
}

CATEGORY_PLATFORMS = {
    "sales": ("TikTok", "Facebook Reels", "Instagram Reels", "YouTube Shorts"),
    "ugc": ("TikTok", "Facebook Reels", "Instagram Reels", "YouTube Shorts"),
    "education": ("YouTube", "YouTube Shorts", "TikTok", "Facebook Reels"),
    "story": ("YouTube", "TikTok", "Instagram Reels", "Facebook Reels"),
    "space": ("Facebook Reels", "Instagram Reels", "YouTube", "TikTok"),
    "lifestyle": ("TikTok", "Instagram Reels", "YouTube Shorts", "Facebook Reels"),
    "digital": ("YouTube", "TikTok", "Facebook Reels", "Instagram Reels"),
    "visual": ("TikTok", "Instagram Reels", "YouTube Shorts", "Facebook Reels"),
    "history": ("YouTube", "TikTok", "Facebook Reels", "YouTube Shorts"),
    "sports": ("TikTok", "YouTube Shorts", "Facebook Reels", "YouTube"),
    "travel": ("TikTok", "Instagram Reels", "YouTube", "Facebook Reels"),
    "industry": ("LinkedIn", "YouTube", "Facebook", "TikTok"),
    "data_news": ("YouTube Shorts", "TikTok", "Facebook Reels", "LinkedIn"),
    "self_help": ("TikTok", "Instagram Reels", "YouTube Shorts", "Facebook Reels"),
    "meme": ("TikTok", "Instagram Reels", "YouTube Shorts", "Facebook Reels"),
    "asmr": ("YouTube", "TikTok", "Instagram Reels", "YouTube Shorts"),
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
    "history": ("thời kỳ", "nhân vật", "dữ kiện", "giai thoại", "hiện vật"),
    "sports": ("môn đấu", "đội/tướng", "chiến thuật", "dữ liệu", "thời điểm"),
    "travel": ("địa điểm", "trải nghiệm", "ngân sách", "thời điểm", "góc nhìn"),
    "industry": ("bài toán", "thiết bị", "quy trình", "an toàn", "lợi ích"),
    "data_news": ("nguồn", "mốc thời gian", "chỉ số", "so sánh", "kết luận"),
    "self_help": ("mục tiêu", "trở ngại", "thói quen", "tiến trình", "hành động"),
    "meme": ("tình huống", "nhân vật hư cấu", "nhịp hài", "phản ứng", "twist"),
    "asmr": ("không gian", "âm thanh", "thao tác", "nhịp", "vòng lặp"),
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
    "history": "bối cảnh -> dữ kiện -> nhân vật/hiện vật -> diễn biến -> ý nghĩa và nguồn",
    "sports": "bối cảnh trận/meta -> điểm nóng -> phân tích -> bằng chứng -> nhận định có điều kiện",
    "travel": "đặt chân -> khám phá -> trải nghiệm -> lưu ý thực tế -> dư âm địa phương",
    "industry": "bài toán -> khảo sát -> giải pháp -> triển khai an toàn -> kết quả đo được",
    "data_news": "câu hỏi -> nguồn dữ liệu -> trực quan hóa -> diễn giải -> giới hạn/kết luận",
    "self_help": "vấn đề -> nhận thức -> hành động nhỏ -> tiến trình -> lời nhắc thực tế",
    "meme": "thiết lập quen thuộc -> lệch kỳ vọng -> phản ứng -> cú bẻ -> kết ngắn",
    "asmr": "thiết lập không gian -> âm thanh đầu -> chuỗi thao tác -> nhịp ổn định -> vòng lặp êm",
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

CATEGORY_BEAT_IDEAS.update({
    "history": (
        "Mở bằng hiện vật hoặc địa danh làm điểm neo", "Xác định rõ thời kỳ và phạm vi câu chuyện",
        "Phân biệt dữ kiện được ghi nhận với giai thoại", "Giới thiệu nhân vật hoặc cộng đồng trung tâm",
        "Mô tả hoàn cảnh xã hội ảnh hưởng tới sự kiện", "Cho thấy mục tiêu hoặc thách thức lúc bấy giờ",
        "Trình bày bằng chứng hoặc nguồn tham khảo chính", "Tái hiện trang phục và đạo cụ đúng bối cảnh",
        "Diễn giải hành động đầu tiên làm thay đổi tình thế", "Làm rõ chiến thuật, kỹ thuật hoặc phong tục liên quan",
        "Nêu giới hạn của điều hiện còn biết", "Đặt hai cách lý giải cạnh nhau một cách công bằng",
        "Tái hiện bước ngoặt mà không thêm dữ kiện giả", "Cho thấy hệ quả trực tiếp với con người và địa phương",
        "Kết nối hiện vật với ý nghĩa văn hóa", "Phân biệt phần truyền thuyết trong lời kể dân gian",
        "Giải thích điều hậu thế thường hiểu nhầm", "Tóm tắt giá trị lịch sử có thể kiểm chứng",
        "Gợi mở nơi đọc hoặc kiểm tra thông tin thêm", "Khép bằng hình ảnh di sản và ghi chú nguồn rõ",
    ),
    "sports": (
        "Mở bằng tình huống thi đấu hoặc meta cần phân tích", "Nêu rõ trận đấu, phiên bản hoặc thời điểm dữ liệu",
        "Giới thiệu hai bên và điều kiện so sánh", "Chỉ ra điểm mạnh cốt lõi của bên thứ nhất",
        "Chỉ ra điểm mạnh cốt lõi của bên thứ hai", "Đặt bản đồ, đội hình hoặc vị trí chiến thuật",
        "Phân tích tình huống mở đầu có thể quyết định nhịp", "Tách một pha xử lý thành các quyết định rõ",
        "Giải thích vai trò của thông số hoặc kỹ năng chính", "Nêu một cách phản công hợp lý",
        "Chỉ ra sai lầm thường gặp trong kèo đấu", "Đưa dữ liệu đã xác minh để kiểm tra nhận định",
        "Phân tích thay đổi chiến thuật ở giữa trận", "Đánh giá rủi ro khi chọn phương án tấn công",
        "Đánh giá rủi ro khi chọn phương án phòng thủ", "Nêu yếu tố bất định không thể bỏ qua",
        "Tổng hợp điều kiện để mỗi bên có lợi thế", "Đưa nhận định có điều kiện thay vì khẳng định chắc chắn",
        "Nhắc người xem kiểm tra đội hình hoặc tin mới", "Khép bằng câu hỏi chiến thuật để thảo luận",
    ),
    "travel": (
        "Mở bằng khoảnh khắc đặc trưng của điểm đến", "Định vị địa điểm và thời điểm trải nghiệm",
        "Cho thấy cách tiếp cận hoặc đường đi thực tế", "Giới thiệu không gian đầu tiên theo góc nhìn người đi",
        "Nêu chi tiết địa phương tạo khác biệt", "Hoàn tất trải nghiệm nhỏ đầu tiên",
        "Ghi lại âm thanh và nhịp sống tại chỗ", "Thử món ăn, dịch vụ hoặc hoạt động tiêu biểu",
        "Nêu cảm nhận thật cùng một điểm cần lưu ý", "Di chuyển sang điểm kế tiếp theo tuyến hợp lý",
        "Cho thấy con người hoặc văn hóa địa phương", "Cận cảnh kiến trúc, vật liệu hoặc cảnh quan",
        "Đưa mẹo chuẩn bị dựa trên trải nghiệm", "Nói rõ thông tin giá/giờ cần được kiểm tra lại",
        "Tạo một khoảng nghỉ để cảm nhận không gian", "So sánh kỳ vọng với trải nghiệm thực tế",
        "Chọn khoảnh khắc đáng nhớ nhất", "Gợi ý ai phù hợp với hành trình này",
        "Tóm tắt tuyến đi không gây hiểu nhầm", "Khép bằng toàn cảnh và lời mời khám phá có trách nhiệm",
    ),
    "industry": (
        "Mở bằng bài toán vận hành hoặc an toàn cụ thể", "Xác định môi trường công trình và phạm vi hệ thống",
        "Khảo sát hiện trạng trước khi đề xuất giải pháp", "Chỉ ra rủi ro hoặc lãng phí đang tồn tại",
        "Nêu tiêu chuẩn hoặc yêu cầu cần tuân thủ", "Giới thiệu sơ đồ giải pháp ở mức dễ hiểu",
        "Cận cảnh thiết bị chính và chức năng", "Trình bày bước chuẩn bị và bảo hộ an toàn",
        "Hoàn tất một công đoạn lắp đặt hoặc cấu hình", "Kiểm tra tín hiệu hoặc thông số sau công đoạn",
        "Nối thiết bị vào hệ thống theo đúng quy trình", "Minh họa tự động hóa xử lý một tình huống thật",
        "Cho thấy dashboard hoặc kết quả giám sát", "Nêu trường hợp lỗi và cách cách ly an toàn",
        "So sánh trước và sau bằng chỉ số phù hợp", "Giải thích lợi ích vận hành không phóng đại",
        "Nêu kế hoạch bảo trì và trách nhiệm sử dụng", "Chỉ rõ giới hạn cần chuyên gia xác nhận",
        "Tổng hợp quy trình thành các mốc kiểm tra", "Khép bằng hệ thống hoạt động ổn định và báo cáo nghiệm thu",
    ),
    "data_news": (
        "Mở bằng câu hỏi dữ liệu cần trả lời", "Ghi rõ nguồn và thời điểm của bộ dữ liệu",
        "Giải thích chỉ số chính bằng ngôn ngữ đơn giản", "Cho thấy quy mô mẫu hoặc phạm vi thống kê",
        "Trình bày mốc cơ sở để người xem so sánh", "Vẽ xu hướng đầu tiên mà không suy diễn",
        "Chỉ ra điểm tăng hoặc giảm đáng chú ý", "So sánh hai nhóm trong cùng điều kiện",
        "Giải thích khác biệt giữa tương quan và nguyên nhân", "Nêu độ bất định hoặc sai số nếu có",
        "Kiểm tra một nhận định phổ biến bằng số liệu", "Đưa ngoại lệ làm thay đổi cách hiểu",
        "Chuyển dữ liệu thành biểu đồ dễ đọc", "Tóm tắt một phát hiện có thể kiểm chứng",
        "Nêu dữ liệu còn thiếu trước khi kết luận", "Với xác suất, nhắc rõ không có kết quả chắc thắng",
        "Với tin thời sự, đánh dấu phần cần xác minh live", "Đưa ra cách người xem tự kiểm tra nguồn",
        "Tổng hợp ba điểm quan trọng nhất", "Khép bằng giới hạn phân tích và thời điểm cập nhật",
    ),
    "self_help": (
        "Mở bằng tình huống người xem dễ đồng cảm", "Gọi tên một trở ngại cụ thể thay vì phán xét",
        "Làm rõ mục tiêu thực tế trong giai đoạn này", "Tách điều kiểm soát được khỏi điều không kiểm soát",
        "Chọn một hành động nhỏ có thể bắt đầu hôm nay", "Thiết kế môi trường giúp hành động dễ hơn",
        "Hoàn tất lần thực hành đầu tiên", "Ghi nhận khó khăn mà không tô hồng",
        "Điều chỉnh kế hoạch sau một lần vấp", "Xây một dấu hiệu nhắc thói quen",
        "Theo dõi tiến trình bằng chỉ số đơn giản", "Tạo phần thưởng nhỏ không phá mục tiêu",
        "Nêu một ranh giới để tránh kiệt sức", "Cho thấy tiến bộ qua nhiều ngày",
        "Kết nối thói quen với giá trị cá nhân", "Loại bỏ lời hứa thành công chắc chắn",
        "Chia sẻ một câu hỏi tự phản tư", "Tóm tắt lộ trình thành ba việc dễ nhớ",
        "Mời người xem chọn bước tiếp theo phù hợp", "Khép bằng lời động viên thực tế và có điều kiện",
    ),
    "meme": (
        "Mở bằng tình huống đời thường ai cũng nhận ra", "Giới thiệu nhân vật hư cấu và mong muốn đơn giản",
        "Đặt một quy tắc kỳ vọng rất rõ", "Cho chi tiết đầu tiên đi lệch kỳ vọng",
        "Ghi lại phản ứng tự nhiên thay vì xúc phạm", "Đẩy hiểu lầm lên thêm một nấc",
        "Cho nhân vật thử cách xử lý hợp lý", "Để cách xử lý tạo ra hệ quả hài mới",
        "Dùng vật thể hoặc chữ làm điểm nhấn", "Tạo khoảng dừng đúng nhịp trước câu chốt",
        "Đổi góc nhìn sang nhân vật thứ hai", "Hé lộ thông tin khiến tình huống đổi nghĩa",
        "Tránh dùng hình ảnh hoặc giọng người thật trái phép", "Đưa cú bẻ liên quan trực tiếp tới thiết lập",
        "Cho nhân vật tự nhận ra điều trớ trêu", "Kết thúc hành động thay vì kéo dài trò đùa",
        "Giữ một câu hoặc biểu cảm dễ nhớ", "Tạo biến thể nguyên bản không sao chép meme",
        "Chừa nhịp cho caption hoặc phản ứng", "Khép nhanh bằng end frame an toàn và rõ nghĩa",
    ),
    "asmr": (
        "Mở bằng toàn cảnh không gian thư giãn", "Đặt nguồn sáng và thời gian trong ngày",
        "Giới thiệu âm thanh nền đầu tiên", "Cận cảnh vật liệu tạo âm thanh",
        "Hoàn tất một thao tác chậm và rõ", "Để âm thanh tự nhiên ngân hết",
        "Thêm lớp âm thanh thứ hai nhẹ hơn", "Giữ nhịp đều không có thay đổi đột ngột",
        "Chuyển góc máy nhưng giữ cùng không gian", "Lặp một thao tác với biến thể nhỏ",
        "Tạo khoảng yên để tai nghỉ", "Đưa âm thanh môi trường trở lại làm điểm neo",
        "Cận cảnh thao tác có kết cấu dễ chịu", "Cân bằng âm lượng giữa các lớp",
        "Giảm chuyển động để chuẩn bị vòng lặp", "Nối trạng thái cuối về gần khung mở đầu",
        "Không đưa tuyên bố chữa bệnh hoặc y khoa", "Giữ hình ảnh và âm thanh không gây giật mình",
        "Hoàn tất chuỗi thao tác cuối", "Khép bằng vòng lặp mượt hoặc fade tự nhiên",
    ),
})


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
    _idea(
        "history_legendary_general", "history", "Dã sử và chân dung danh tướng",
        "Đặt nhân vật vào đúng thời kỳ, tách dữ kiện có nguồn khỏi giai thoại rồi kể một chiến lược hoặc lựa chọn trọn vẹn.",
        "Một hiện vật hoặc địa danh mở ra câu hỏi về quyết định đã làm thay đổi cục diện.",
        "Kể lịch sử hấp dẫn nhưng không xuyên tạc hoặc biến giai thoại thành sự thật.",
        "script_image_video", "character", "tài liệu lịch sử điện ảnh, tôn trọng dữ kiện",
        "Chân dung, trang phục, kiến trúc và bản đồ đúng thời kỳ; phần tái dựng được nhận diện rõ.",
        "Mỗi cảnh hoàn tất một dữ kiện hoặc hành động; lời dẫn chỉ khẳng định điều có căn cứ và ghi rõ phần còn tranh luận.",
        formats=("historical portrait", "documentary short", "battle strategy"),
    ),
    _idea(
        "history_legendary_weapon", "history", "Vũ khí huyền thoại dưới góc nhìn thực tế",
        "Phân tích nguồn gốc, vật liệu, cấu tạo, cách sử dụng và phần giai thoại của một binh khí cổ.",
        "Cận cảnh chi tiết chế tác khiến người xem đặt câu hỏi món binh khí thật sự hoạt động ra sao.",
        "Giúp người xem hiểu hiện vật mà không phóng đại sức mạnh hoặc kích thước.",
        "storyboard_prompt", "product_3d_showcase", "khảo cứu hiện vật, macro điện ảnh",
        "Tỉ lệ, vật liệu, hoa văn và cách cầm hợp lý; không tự thêm chữ khắc hoặc biểu tượng sai.",
        "Từ tổng quan tới cấu tạo, thao tác mô phỏng an toàn, đối chiếu giai thoại và kết bằng giá trị văn hóa.",
        formats=("artifact breakdown", "3D explainer", "museum story"),
    ),
    _idea(
        "history_folklore_mystery", "history", "Truyền thuyết dân gian và điều còn bí ẩn",
        "Kể một truyền thuyết theo nguồn lưu truyền, giải thích bối cảnh văn hóa và phân biệt rõ phần chưa kiểm chứng.",
        "Một âm thanh hoặc dấu tích quen thuộc xuất hiện trong không gian đêm nhưng không dùng hù dọa rẻ tiền.",
        "Bảo tồn chất kể dân gian mà không khẳng định hiện tượng siêu nhiên là sự thật.",
        "video_ai_real", "cinematic_vfx", "huyền bí tiết chế, giàu văn hóa",
        "Không gian địa phương nhất quán, ánh sáng đêm dễ nhìn, nhân vật và nghi thức không bị chế giễu.",
        "Từ lời kể, dấu tích, nhiều cách giải thích tới ý nghĩa văn hóa; kết mở có ghi chú truyền thuyết.",
        formats=("folklore", "night story", "cultural mystery"),
    ),
    _idea(
        "sports_match_analysis", "sports", "Nhận định trận đấu có dữ liệu",
        "Nêu bối cảnh, điểm nóng chiến thuật, phương án của hai bên và kết bằng nhận định có điều kiện.",
        "Một sơ đồ chiến thuật làm lộ khoảng trống có thể quyết định trận đấu.",
        "Giúp người xem hiểu trận đấu; không hardcode kết quả hoặc tin hiện thời chưa xác minh.",
        "script_image_video", "tutorial_explainer", "bình luận thể thao nhanh, đồ họa rõ",
        "Sân đấu, đội hình và biểu đồ minh họa trung tính; chỉ dùng dữ liệu người dùng cung cấp hoặc đã xác minh.",
        "Mỗi cảnh giải thích một pha hoặc nguyên tắc; cuối video nêu điều kiện có thể làm nhận định thay đổi.",
        formats=("match preview", "tactical analysis", "sports short"),
    ),
    _idea(
        "sports_esports_matchup", "sports", "Phân tích meta và kèo kỹ năng",
        "So sánh bộ kỹ năng, ngưỡng sức mạnh, cách trao đổi và điều kiện thắng của hai lựa chọn trong đúng phiên bản.",
        "Hai lối chơi đối lập xuất hiện trên cùng một bản đồ chiến thuật.",
        "Mổ xẻ meta dễ hiểu, không giả dữ liệu phiên bản hoặc dùng tài sản bản quyền trái phép.",
        "storyboard_prompt", "app_game_demo", "eSports năng lượng, infographic động",
        "Đồ họa nguyên bản, icon minh họa an toàn, trạng thái bản đồ và chỉ số nhất quán.",
        "Mỗi cảnh hoàn tất một khía cạnh: bộ kỹ năng, thời điểm mạnh, trao đổi, giao tranh và kết luận có điều kiện.",
        formats=("meta analysis", "matchup", "esports explainer"),
    ),
    _idea(
        "sports_transfer_brief", "sports", "Bản tin chuyển nhượng 60 giây",
        "Tóm tắt các diễn biến theo trạng thái xác minh, nguồn và mốc thời gian; tách tin chính thức khỏi đồn đoán.",
        "Một dòng thời gian nhanh cho thấy thương vụ đang ở giai đoạn nào.",
        "Cập nhật dễ hiểu mà không biến tin đồn thành thông báo chính thức.",
        "video_trend", "ugc_social_creator", "bản tin thể thao dứt khoát",
        "Ảnh minh họa có quyền sử dụng, thẻ trạng thái rõ 'chính thức' hoặc 'chưa xác nhận'.",
        "Mỗi cảnh là một thông tin có nguồn và thời điểm; cảnh cuối nhắc kiểm tra cập nhật mới nhất.",
        formats=("transfer news", "60s brief", "sports update"),
    ),
    _idea(
        "travel_nightlife", "travel", "Khám phá nightlife có chọn lọc",
        "Đi qua một tuyến trải nghiệm đêm, chú ý không gian, âm thanh, dịch vụ và lưu ý an toàn thực tế.",
        "Ánh đèn và âm thanh từ một lối vào kín đáo kéo người xem vào hành trình.",
        "Review chân thực, không tự khẳng định giá hoặc giờ mở cửa hiện tại.",
        "video_ai_real", "architecture_walkthrough", "nightlife POV, neon tiết chế",
        "Giữ đúng địa điểm, lộ trình camera và ánh sáng; không quay cận người lạ khi chưa có quyền.",
        "Mỗi cảnh hoàn tất một điểm dừng; chuyển bằng bước chân hoặc âm thanh địa phương, kết ở toàn cảnh đêm.",
        formats=("nightlife guide", "POV review", "local experience"),
    ),
    _idea(
        "travel_unique_local", "travel", "Một trải nghiệm địa phương độc đáo",
        "Theo chân người trải nghiệm từ chuẩn bị, lên đường, hoạt động chính tới khoảnh khắc đáng nhớ nhất.",
        "Một góc nhìn POV hé lộ địa điểm quen mà người xem chưa từng trải nghiệm theo cách này.",
        "Truyền cảm hứng khám phá có trách nhiệm và đưa lưu ý thực tế rõ.",
        "video_trend", "ugc_social_creator", "travel vlog chân thật",
        "Cùng người, trang phục và thời tiết trong một tuyến thời gian; địa điểm không bị ghép sai.",
        "Mỗi cảnh hoàn thành một chặng; lời dẫn nêu cảm nhận thật, giá/giờ cần được kiểm tra trước khi đi.",
        formats=("local experience", "POV travel", "day trip"),
    ),
    _idea(
        "travel_staycation", "travel", "Staycation từ phòng tới dịch vụ",
        "Review tuyến trải nghiệm nghỉ dưỡng: tiếp cận, phòng, tiện ích, dịch vụ, điểm mạnh và một lưu ý.",
        "Cánh cửa mở ra trục nhìn đẹp nhất của không gian nghỉ dưỡng.",
        "Giúp người xem đánh giá nơi ở thay vì chỉ xem montage quảng cáo.",
        "script_image_video", "real_estate_property", "resort walkthrough cao cấp",
        "Hình học phòng, vật liệu, cảnh quan và ánh sáng đúng; không tự thêm tiện ích không có.",
        "Camera đi theo tuyến thật, hoàn tất từng khu vực rồi mới chuyển; cuối video tóm tắt ai phù hợp.",
        formats=("staycation", "hotel review", "resort tour"),
    ),
    _idea(
        "industry_elv_installation", "industry", "Thi công ELV, camera và chiếu sáng",
        "Showcase khảo sát, thiết kế, thi công, kiểm thử và bàn giao hệ thống điện nhẹ trong môi trường thật.",
        "Một điểm mù hoặc tín hiệu gián đoạn làm lộ bài toán an toàn cần giải quyết.",
        "Giới thiệu năng lực B2B bằng quy trình và kết quả đo được, không đưa hướng dẫn nguy hiểm.",
        "script_image_video", "architecture_walkthrough", "công nghiệp sạch, kỹ thuật tin cậy",
        "Công xưởng đúng hình học, PPE đầy đủ, cáp/thiết bị hợp lý và sơ đồ không chứa bí mật hệ thống.",
        "Mỗi cảnh hoàn tất một mốc khảo sát, lắp đặt hoặc kiểm tra; chỉ chuyên gia đủ điều kiện thực hiện thao tác nguy hiểm.",
        formats=("ELV showcase", "installation process", "B2B case study"),
    ),
    _idea(
        "industry_erp_transformation", "industry", "Chuyển đổi số và tự động hóa ERP",
        "Biến một quy trình thủ công thành luồng số có dữ liệu vào, kiểm soát, tự động hóa và kết quả rõ.",
        "Một bảng tính rời rạc được đặt cạnh dashboard đồng bộ theo thời gian.",
        "Giải thích giá trị chuyển đổi số mà không hứa tiết kiệm hoặc hiệu suất chưa được đo.",
        "storyboard_prompt", "website_saas_demo", "B2B công nghệ, luồng dữ liệu sạch",
        "Giao diện mẫu không chứa dữ liệu thật, vai trò người dùng và bước phê duyệt nhất quán.",
        "Mỗi cảnh hoàn tất một bước quy trình; có ngoại lệ, kiểm soát và chỉ số trước/sau hợp lệ.",
        formats=("ERP demo", "digital transformation", "workflow automation"),
    ),
    _idea(
        "industry_device_unboxing", "industry", "Đập hộp thiết bị kỹ thuật chuyên dụng",
        "Từ niêm phong, phụ kiện, cổng kết nối, lắp thử tới kiểm tra chức năng và giới hạn sử dụng.",
        "Macro một chi tiết linh kiện cho thấy đây không phải bài mở hộp phổ thông.",
        "Review kỹ thuật có căn cứ, không tự khẳng định chuẩn hoặc hiệu năng chưa kiểm thử.",
        "video_ai_real", "product_3d_showcase", "macro kỹ thuật, chi tiết sắc nét",
        "Model, cổng, board mạch và phụ kiện đúng tham chiếu; không tự thêm chứng nhận hoặc logo.",
        "Mỗi cảnh hoàn tất một bước mở hộp hay kiểm tra; cảnh cuối nêu đối tượng phù hợp và giới hạn.",
        formats=("technical unboxing", "device review", "hardware showcase"),
    ),
    _idea(
        "data_probability_literacy", "data_news", "Xác suất và thống kê dễ hiểu",
        "Giải thích tần suất, chu kỳ, xác suất và sai lầm nhận thức bằng biểu đồ có nguồn.",
        "Một chuỗi số tưởng như có quy luật được đặt cạnh xác suất thực tế.",
        "Dạy tư duy dữ liệu; không dự đoán chắc thắng, không khuyến khích đặt cược.",
        "script_image_video", "tutorial_explainer", "infographic dữ liệu sáng rõ",
        "Biểu đồ có nhãn, mẫu và mốc thời gian; không tự tạo kết quả xổ số hoặc tỷ lệ giả.",
        "Từ câu hỏi, dữ liệu, biểu đồ, giới hạn tới disclaimer xác suất; kết bằng cách tự kiểm tra nguồn.",
        formats=("probability explainer", "statistics", "data literacy"),
    ),
    _idea(
        "data_bar_chart_story", "data_news", "Biểu đồ đua top theo thời gian",
        "Kể sự thay đổi thứ hạng qua các mốc bằng dữ liệu đã xác minh, chú thích nguồn và bối cảnh.",
        "Hai đối tượng đổi vị trí tại một mốc bất ngờ khiến người xem muốn biết nguyên nhân.",
        "Biến bảng số liệu thành câu chuyện trực quan mà không bóp méo tỉ lệ.",
        "storyboard_prompt", "animation_2d_3d", "data visualization mạch lạc",
        "Trục, đơn vị, màu và thứ hạng nhất quán; nguồn và năm hiển thị rõ, không dùng số liệu bịa.",
        "Mỗi cảnh hoàn tất một giai đoạn; camera giữ biểu đồ đọc được, kết bằng phạm vi dữ liệu và nguồn.",
        formats=("bar chart race", "ranking history", "data story"),
    ),
    _idea(
        "data_daily_brief", "data_news", "Tóm tắt tin vắn bằng dữ liệu",
        "Gom các tin cùng chủ đề, mỗi cảnh một ý có nguồn, thời điểm và điều người xem cần biết.",
        "Ba chỉ số quan trọng xuất hiện như tiêu đề của bản tin ngắn.",
        "Cập nhật nhanh nhưng không khẳng định thông tin chưa được xác minh live.",
        "video_trend", "tutorial_explainer", "bản tin sạch, nhịp nhanh vừa đủ",
        "Thẻ tin và biểu đồ nguyên bản, nguồn/mốc giờ rõ, không dùng hình vi phạm bản quyền.",
        "Mỗi cảnh một tin trọn vẹn; phân biệt dữ kiện, phân tích và phần cần theo dõi thêm.",
        formats=("news brief", "daily data", "60s update"),
    ),
    _idea(
        "selfhelp_podcast_short", "self_help", "Podcast short có một thông điệp trọn vẹn",
        "Mở bằng câu hỏi thật, triển khai một góc nhìn, ví dụ và hành động nhỏ thay vì ghép quote rời rạc.",
        "Một câu nói ngắn chạm đúng tình huống người xem đang trải qua.",
        "Tạo nội dung truyền cảm hứng thực tế, không hứa thay đổi cuộc đời tức thì.",
        "script_image_video", "ugc_social_creator", "podcast short gần gũi",
        "Nhân vật hoặc nền hình ảnh có quyền sử dụng, caption dễ đọc và vùng an toàn rõ.",
        "Lời đọc vừa 8 giây mỗi cảnh, không cắt giữa câu; nền hình nối cảm xúc và kết bằng hành động nhỏ.",
        formats=("podcast short", "quote reflection", "motivational reel"),
    ),
    _idea(
        "selfhelp_career_roadmap", "self_help", "Lộ trình nghề nghiệp có mốc kiểm tra",
        "Từ mục tiêu dài hạn, năng lực hiện tại, bước học, dự án thử nghiệm tới mốc đánh giá lại.",
        "Một bản đồ 5 năm được thu nhỏ thành bước có thể bắt đầu trong tuần này.",
        "Giúp người xem định hướng mà không hứa chắc chắn về chức danh hoặc thu nhập.",
        "storyboard_prompt", "tutorial_explainer", "roadmap trực quan, điềm tĩnh",
        "Timeline, mốc kỹ năng và checklist rõ; không dùng biểu đồ thu nhập giả.",
        "Mỗi cảnh hoàn tất một mốc; cảnh cuối nhắc điều chỉnh theo hoàn cảnh và phản hồi thực tế.",
        formats=("career roadmap", "business plan", "learning path"),
    ),
    _idea(
        "selfhelp_habit_system", "self_help", "Kỷ luật bằng hệ thống thói quen nhỏ",
        "Theo một ngày thực tế, chỉ ra tín hiệu, hành động, trở ngại, điều chỉnh và cách ghi nhận tiến bộ.",
        "Một hành động hai phút mở đầu thay cho lời hô hào kỷ luật chung chung.",
        "Khuyến khích thói quen bền vững, tránh tôn vinh kiệt sức hoặc hình mẫu phi thực tế.",
        "video_ai_real", "ugc_social_creator", "day-in-the-life chân thật",
        "Cùng nhân vật, lịch trình và không gian; tiến bộ thể hiện bằng hành động chứ không phải thành tích giả.",
        "Mỗi cảnh hoàn thành một thói quen; có vấp, điều chỉnh và kết bằng lựa chọn tiếp theo.",
        formats=("habit routine", "day in life", "discipline diary"),
    ),
    _idea(
        "meme_office_pov", "meme", "POV tình huống công sở",
        "Thiết lập một quy tắc quen thuộc, tạo hiểu lầm nhỏ, phản ứng và cú bẻ liên quan trực tiếp.",
        "Dòng chữ POV khiến người xem nhận ra ngay tình huống trớ trêu.",
        "Tạo tiếng cười nguyên bản, không nhắm vào nhóm yếu thế hoặc người thật cụ thể.",
        "video_trend", "ugc_social_creator", "hài tình huống nhanh, camera điện thoại",
        "Nhân vật hư cấu, bối cảnh an toàn, caption ngắn; không dùng khuôn mặt hoặc giọng người thật trái phép.",
        "Mỗi cảnh trọn một nhịp hài; khoảng dừng trước punchline và kết nhanh không kéo dài trò đùa.",
        formats=("POV", "office comedy", "relatable skit"),
    ),
    _idea(
        "meme_visual_parody", "meme", "Parody hình ảnh nguyên bản",
        "Lấy một mô-típ phổ biến rồi viết lại tình huống, nhân vật và cú chốt mới hoàn toàn.",
        "Một hình ảnh quen về cấu trúc nhưng khác hoàn toàn về nhân vật và bối cảnh.",
        "Bắt trend mà không sao chép nguyên tác hoặc mạo danh người thật.",
        "storyboard_prompt", "animation_2d_3d", "parody hoạt hình nguyên bản",
        "Thiết kế nhân vật riêng, không dùng logo hoặc nhân vật bản quyền; biểu cảm rõ và nhất quán.",
        "Mỗi cảnh phát triển một lớp kỳ vọng; cú bẻ cuối xuất phát từ chi tiết đã cài ở đầu.",
        formats=("parody", "animated meme", "trend remix"),
    ),
    _idea(
        "meme_voice_comedy", "meme", "Hội thoại hài với giọng được phép",
        "Viết đoạn đối đáp giữa nhân vật hư cấu, có nhịp setup–phản hồi–punchline và kế hoạch giọng hợp lệ.",
        "Hai nhân vật hiểu cùng một câu theo hai nghĩa khác nhau.",
        "Lập kế hoạch lồng tiếng hài nhưng không clone giọng người thật khi chưa có quyền.",
        "script_image_video", "character", "hội thoại nhân vật, nhịp hài rõ",
        "Nhân vật nguyên bản, khẩu hình và biểu cảm hợp câu; không dùng nhận diện người nổi tiếng.",
        "Mỗi cảnh chứa câu thoại trọn vẹn dưới giới hạn thời lượng; voice plan chỉ là metadata trước xác nhận.",
        formats=("dialogue comedy", "voice parody", "character skit"),
    ),
    _idea(
        "asmr_rain_window", "asmr", "Mưa bên cửa sổ và không gian học tập",
        "Xây một vòng lặp mưa, ánh đèn, thao tác nhẹ và khoảng yên để học hoặc làm việc.",
        "Giọt mưa trượt qua kính trong khi căn phòng dần sáng ấm.",
        "Tạo kế hoạch thư giãn không giật mình; không tuyên bố chữa mất ngủ hoặc bệnh lý.",
        "video_ai_real", "architecture_interior", "cozy rain, loop mượt",
        "Căn phòng, cửa sổ và nguồn sáng nhất quán; chuyển động mưa tự nhiên và không chớp sáng mạnh.",
        "Âm thanh mưa chỉ là kế hoạch; trạng thái cuối nối lại khung đầu để loop tự nhiên.",
        formats=("rain ambience", "study loop", "cozy room"),
    ),
    _idea(
        "asmr_cooking_process", "asmr", "ASMR nấu ăn theo thao tác trọn vẹn",
        "Từng cảnh hoàn tất một thao tác chuẩn bị, cắt, trộn, nấu hoặc trình bày với âm thanh chân thực.",
        "Âm thanh dao chạm thớt mở đầu trước khi toàn bộ nguyên liệu hiện ra.",
        "Tạo trải nghiệm cảm giác rõ mà vẫn giữ vệ sinh và an toàn thực phẩm.",
        "storyboard_prompt", "fashion_lookbook", "macro ẩm thực, âm thanh tự nhiên",
        "Tay, dụng cụ và nguyên liệu đúng hình dạng; bếp sạch, thao tác nhiệt/dao an toàn.",
        "Không cắt giữa thao tác; âm thanh từng cảnh được ghi chú riêng và cân bằng sau khi ghép.",
        formats=("cooking ASMR", "food prep", "sensory process"),
    ),
    _idea(
        "asmr_lofi_workspace", "asmr", "Lofi làm việc với nhịp hình tối giản",
        "Theo một phiên làm việc yên tĩnh, chuyển nhẹ giữa bàn, ghi chú, nghỉ mắt và quay lại tập trung.",
        "Đèn bàn bật lên cùng nhịp đầu tiên của một bản lofi chưa được tạo.",
        "Lập kế hoạch visualizer tập trung; không gọi Music/Suno ở bước tham khảo.",
        "script_image_video", "cinematic_vfx", "lofi tối giản, màu dịu",
        "Không gian và vật dụng giữ nguyên, chuyển động nhỏ, vùng hình không gây phân tâm.",
        "Mỗi cảnh có nhịp riêng nhưng cùng BPM dự kiến; music plan chỉ được thực thi sau xác nhận cuối.",
        formats=("lofi workspace", "focus loop", "study visualizer"),
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
    "history": "education",
    "sports": "data_news",
    "travel": "lifestyle",
    "industry": "digital",
    "data_news": "education",
    "self_help": "education",
    "meme": "ugc",
    "asmr": "visual",
}

CATEGORY_SYSTEM_GUIDANCE = {
    "sales": "Lập kế hoạch quảng cáo trung thực, nêu đúng lợi ích có thể chứng minh và không tạo tuyên bố quá mức.",
    "ugc": "Lập kế hoạch nội dung đời thường tự nhiên, giữ trải nghiệm đáng tin và không giả mạo lời chứng thực.",
    "education": "Giải thích theo từng bước dễ kiểm tra, dùng ví dụ rõ và không biến giả định thành dữ kiện.",
    "story": "Xây dựng mạch kể có mở đầu, phát triển, cao trào và kết thúc; mỗi cảnh hoàn tất một nhịp truyện.",
    "space": "Giữ hình học, vật liệu, kiến trúc và lộ trình camera nhất quán giữa các cảnh.",
    "lifestyle": "Ưu tiên trải nghiệm chân thực, cảm giác rõ và hành động hoàn chỉnh trong từng cảnh.",
    "digital": "Mô tả đúng luồng thao tác sản phẩm số; không bịa tính năng, số liệu hoặc giao diện chưa được cung cấp.",
    "visual": "Thiết kế nhịp hình, chuyển động và điểm nhấn nhất quán; âm thanh chỉ là kế hoạch trước xác nhận cuối.",
    "history": "Phân biệt dữ kiện có nguồn với dã sử, truyền thuyết hoặc tái hiện nghệ thuật; không bịa sự kiện lịch sử.",
    "sports": "Chỉ dùng kết quả, đội hình, meta hoặc chuyển nhượng hiện thời khi người dùng cung cấp hay đã xác minh nguồn trực tiếp.",
    "travel": "Không khẳng định giá, giờ mở cửa hoặc tình trạng dịch vụ hiện thời nếu chưa có nguồn được xác minh.",
    "industry": "Trình bày giải pháp B2B chuyên nghiệp, ưu tiên an toàn và không đưa chỉ dẫn vận hành nguy hiểm chưa được kiểm chứng.",
    "data_news": "Không bịa dữ liệu hoặc tin tức; xác suất chỉ mang tính giáo dục, không hứa dự đoán chắc thắng hay khuyến khích đánh bạc.",
    "self_help": "Đưa ra gợi ý thực tế và có điều kiện; không hứa thành công, chữa bệnh hoặc kết quả tài chính chắc chắn.",
    "meme": "Tạo nội dung nguyên bản, không quấy rối, mạo danh hoặc sao chép giọng người thật khi chưa có quyền rõ ràng.",
    "asmr": "Thiết kế trải nghiệm thư giãn nhưng không đưa tuyên bố chữa bệnh; nhạc và âm thanh chỉ được lưu dưới dạng kế hoạch.",
}

CATEGORY_MEDIA_PLANS = {
    "sales": ("nhịp hiện đại, gọn, không lấn lời", "rõ ràng, đáng tin", "sạch, sản phẩm là trọng tâm"),
    "ugc": ("nhẹ, đời thường", "tự nhiên như chia sẻ thật", "ánh sáng tự nhiên, camera gần gũi"),
    "education": ("tối giản, hỗ trợ tập trung", "mạch lạc, vừa tốc độ", "minh họa rõ, chữ có vùng an toàn"),
    "story": ("điện ảnh theo nhịp câu chuyện", "giàu cảm xúc nhưng tiết chế", "điện ảnh, continuity nhân vật rõ"),
    "space": ("ambient kiến trúc", "thuyết minh điềm tĩnh", "đúng phối cảnh, vật liệu và ánh sáng"),
    "lifestyle": ("ấm, giàu cảm giác", "thân thiện", "chi tiết chất liệu, màu tự nhiên"),
    "digital": ("tech tối giản", "chuyên nghiệp, dễ theo dõi", "giao diện rõ, thao tác có thứ tự"),
    "visual": ("nhịp hình và âm thanh đồng bộ", "tùy chọn, ưu tiên hình", "motion graphic có chủ đích"),
    "history": ("epic điện ảnh, nhạc cụ phù hợp bối cảnh", "trầm ấm, phân biệt dữ kiện và giai thoại", "điện ảnh hoài cổ, trang phục đúng bối cảnh"),
    "sports": ("năng lượng cao, tiết tấu nhanh", "bình luận rõ và có điều kiện", "hành động nhanh, đồ họa chiến thuật dễ đọc"),
    "travel": ("ambient địa phương, không lấn tiếng hiện trường", "POV chân thực", "góc nhìn trải nghiệm, màu tự nhiên"),
    "industry": ("corporate/tech gọn", "chuyên nghiệp, đáng tin", "ánh sáng sạch, cận cảnh thiết bị an toàn"),
    "data_news": ("nhịp bản tin tiết chế", "dứt khoát, đọc rõ số", "infographic có nguồn và mốc thời gian"),
    "self_help": ("ấm, nâng đỡ, không cường điệu", "bình tĩnh, thực tế", "đời thường, tiến trình nhỏ có thật"),
    "meme": ("nhịp hài nguyên bản", "không giả giọng người thật", "POV rõ, cú bẻ dễ hiểu"),
    "asmr": ("ambient/lofi hoặc âm thanh hiện trường", "không lời hoặc rất nhẹ", "chuyển động chậm, vòng lặp êm"),
}

CATEGORY_AUDIO_PLANS = {
    category_key: "Âm thanh hiện trường tùy chọn; chỉ cân chỉnh sau khi các cảnh đã ghép."
    for category_key, _label in CATEGORIES
}
CATEGORY_AUDIO_PLANS["asmr"] = (
    "Ưu tiên âm thanh môi trường chân thực, chọn loop hoặc fade tự nhiên, giữ nhịp đều và "
    "tránh thay đổi âm lượng đột ngột; chỉ là kế hoạch trước xác nhận cuối."
)

CATEGORY_DEFAULT_SCENE_COUNT = {
    "sales": 3, "ugc": 3, "education": 3, "story": 5,
    "space": 5, "lifestyle": 3, "digital": 3, "visual": 5,
    "history": 3, "sports": 4, "travel": 3, "industry": 5,
    "data_news": 3, "self_help": 3, "meme": 3, "asmr": 5,
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
        "recommended_aspect_ratio": (
            str(base.get("recommended_aspect_ratio") or base.get("aspect_ratio") or "9:16")
            if str(base.get("recommended_aspect_ratio") or base.get("aspect_ratio") or "9:16") in ASPECT_RATIO_OPTIONS
            else "9:16"
        ),
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


IDEA_PRODUCT_HANDOFFS = frozenset({
    "video_trend",
    "video_ai_real",
    "script_image_video",
    "video_reference",
    "motion_prompt",
    "storyboard_prompt",
    "self_shot_scene_change",
})


def build_scene3_handoff_state(
    plan: dict[str, Any],
    *,
    product_id_override: str = "",
) -> dict[str, Any]:
    """Turn one reference idea into exact-N editable scene prompts, provider-free."""

    source = deepcopy(dict(plan or {}))
    count = max(1, min(20, int(source.get("scene_count") or 1)))
    requested_product = str(product_id_override or "").strip()
    product_id = (
        requested_product
        if requested_product in IDEA_PRODUCT_HANDOFFS
        else recommended_handoff_product(source)
    )
    source_media_refs = [
        str(item).strip()
        for item in source.get("source_media_refs") or []
        if str(item or "").strip()
    ][:20]
    if product_id == "self_shot_scene_change" and not source_media_refs:
        raise ValueError("self_shot_source_video_required")
    profile_id = str(source.get("recommended_profile_id") or "tutorial_explainer")
    primary_profile = video_profile_catalog.canonical_profile_key(profile_id)
    category_key = str(source.get("category_key") or source.get("category") or "")
    category_profiles = tuple(video_profile_catalog.IDEA_GROUP_PROFILE_MAP.get(category_key) or ())
    if not primary_profile:
        primary_profile = str(category_profiles[0] if category_profiles else "knowledge_explainer")
    technical_profile = video_profile_catalog.technical_profile_for_profile(primary_profile)
    recommended_aspect_ratio = str(
        source.get("recommended_aspect_ratio")
        or source.get("aspect_ratio")
        or "9:16"
    ).strip()
    if recommended_aspect_ratio not in ASPECT_RATIO_OPTIONS:
        recommended_aspect_ratio = "9:16"
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
    state = video_scene3_flow.default_state(
        product_type=product_id,
        subject=title,
        aspect_ratio=recommended_aspect_ratio,
    )
    state.update({
        # A preset is already a complete planning input. Normal lanes open at
        # editable video prompts; storyboard keeps its mandatory image source
        # gate instead of reviving the retired image_strategy screen.
        "step": "image_source" if product_id == "storyboard_prompt" else "video_prompts",
        "history": ["video_idea_result"],
        "product_type": product_id,
        "source_product_id": product_id,
        "scene_count": count,
        "recommended_aspect_ratio": recommended_aspect_ratio,
        "aspect_ratio": recommended_aspect_ratio,
        "primary_profile": primary_profile,
        "linked_profiles": [],
        "profile_page": video_profile_catalog.profile_page(primary_profile),
        "profile_bundle_version": video_profile_catalog.SCHEMA_VERSION,
        "content_type": video_profile_catalog.content_type_for_profile(primary_profile),
        "technical_profile": technical_profile,
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
        "source_media_ref": source_media_refs[0] if source_media_refs else "",
        "source_media_refs": source_media_refs,
        "source_media_type": "video" if product_id == "self_shot_scene_change" else "",
        "storyboard_image_required": product_id == "storyboard_prompt",
        "storyboard_allowed_image_strategies": (
            ["uploaded_image", "ai_image"] if product_id == "storyboard_prompt" else []
        ),
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
    next_step = "image_source" if product_id == "storyboard_prompt" else "video_prompts"
    state.update({
        "step": next_step,
        "history": ["video_idea_result"],
        "origin": "video_idea_catalog",
        "idea_return_callback": "videoidea|catalog_result",
        "selected_video_idea": source,
        "recommended_aspect_ratio": recommended_aspect_ratio,
        "aspect_ratio": recommended_aspect_ratio,
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


def dynamic_category_seeds() -> list[dict[str, Any]]:
    """Return the curated category seed consumed by the SQLite catalog."""

    rows: list[dict[str, Any]] = []
    for sort_order, (category_key, _legacy_label) in enumerate(CATEGORIES, 1):
        icon, public_name, short_button_name, description = CATEGORY_METADATA[category_key]
        rows.append({
            "category_key": category_key,
            "public_name": public_name,
            "short_button_name": short_button_name,
            "description": description,
            "icon": icon,
            "sort_order": sort_order,
            "is_active": 1,
            "created_by": "system_seed",
        })
    return rows


def dynamic_preset_seeds() -> list[dict[str, Any]]:
    """Map all legacy and new curated ideas into versioned SQLite presets.

    The first 48 rows keep their existing keys and creative content. SQLite
    uses ``INSERT OR IGNORE`` so later admin edits are never overwritten by a
    restart or a new deployment.
    """

    category_positions: dict[str, int] = {}
    rows: list[dict[str, Any]] = []
    for idea in IDEAS:
        category_key = str(idea.get("category") or "story")
        category_positions[category_key] = category_positions.get(category_key, 0) + 1
        music_plan, voice_plan, visual_plan = CATEGORY_MEDIA_PLANS[category_key]
        scene_count = CATEGORY_DEFAULT_SCENE_COUNT[category_key]
        title = str(idea.get("title") or "Ý tưởng video").strip()
        rows.append({
            "preset_key": str(idea.get("idea_id") or "").strip(),
            "category_key": category_key,
            "title": title,
            "description": str(idea.get("summary") or "").strip(),
            "system_guidance": (
                f"{CATEGORY_SYSTEM_GUIDANCE[category_key]} "
                "Viết đúng số cảnh người dùng chọn; mỗi cảnh dài khoảng 8 giây, "
                "hoàn tất một ý hoặc hành động và nối mượt sang cảnh kế tiếp."
            ),
            "user_prompt_template": (
                f"Lập kế hoạch {{scene_count}} cảnh cho ý tưởng '{title}' về {{topic}}. "
                "Bám sát yêu cầu riêng: {customer_brief}. Mỗi cảnh phải có mục tiêu, "
                "chủ thể, hành động, trạng thái đầu-cuối, camera, ánh sáng, âm thanh, "
                "câu lệnh hình và câu lệnh video riêng. Không chia cơ học một đoạn dài."
            ),
            "recommended_scene_count": scene_count,
            "scene_duration_sec": SCENE_SECONDS,
            "recommended_aspect_ratio": str(idea.get("recommended_aspect_ratio") or idea.get("aspect_ratio") or "9:16"),
            "music_plan": music_plan,
            "audio_plan": CATEGORY_AUDIO_PLANS[category_key],
            "voice_plan": voice_plan,
            "visual_plan": visual_plan,
            "content_safety_note": CATEGORY_SYSTEM_GUIDANCE[category_key],
            "recommended_product_id": str(idea.get("recommended_product_id") or "video_ai_real"),
            "recommended_profile_id": str(idea.get("recommended_profile_id") or "tutorial_explainer"),
            "hook": str(idea.get("hook") or ""),
            "objective": str(idea.get("objective") or ""),
            "style": str(idea.get("style") or ""),
            "image_prompt_seed": str(idea.get("image_prompt_seed") or ""),
            "video_prompt_seed": str(idea.get("video_prompt_seed") or ""),
            "scene_arc": str(idea.get("scene_arc") or CATEGORY_SCENE_ARCS[category_key]),
            "platform_fit": list(idea.get("platform_fit") or CATEGORY_PLATFORMS[category_key]),
            "variation_axes": list(idea.get("variation_axes") or CATEGORY_VARIATION_AXES[category_key]),
            "sort_order": category_positions[category_key],
            "is_active": 1,
            "created_by": "system_seed",
        })
    return rows


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
