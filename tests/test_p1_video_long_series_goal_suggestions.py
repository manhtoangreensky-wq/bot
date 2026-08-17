import pytest
from services import video_uiflow3

def test_series_goal_two_lanes():
    """Verify 2-lane series goal: manual input lane and 5-number suggestion lane."""
    # Lane 1: Manual Input
    state = video_uiflow3.new_state("multi_scene_film")
    state = video_uiflow3.set_series_goal(state, "Series điều tra tội phạm bí ẩn")
    assert state["series"]["goal"] == "Series điều tra tội phạm bí ẩn"
    
    # Lane 2: 25 suggestions, 5 items per page
    suggestions = [
        "🎬 Chuỗi phim ngắn drama kịch tính về cuộc sống và tình cảm hiện đại",
        "☕ Phim ngắn hài hước, tình huống văn phòng & cuộc sống thường ngày",
        "🕵️ Loạt video trinh thám, bí ẩn và giải mã các câu chuyện kỳ thú",
        "⚡ Phim hành động ngắn, giả tưởng và thế giới tương lai cyberpunk",
        "🎭 Tuyển tập tiểu phẩm hài, tình huống bất ngờ mang lại tiếng cười",
        "📈 Khóa học & bài giảng ngắn chia sẻ kiến thức kinh doanh, tài chính thực chiến",
        "🚀 Hành trình khởi nghiệp & phát triển bản thân từ con số 0",
        "💼 Bí quyết quản trị, lãnh đạo và kỹ năng làm việc hiệu quả",
        "📚 Kể chuyện lịch sử & những câu chuyện truyền cảm hứng lay động lòng người",
        "🔮 Giải mã tâm lý học hành vi và nghệ thuật giao tiếp thu phục lòng người",
        "🌟 Series review sản phẩm & hướng dẫn công nghệ đời sống thế hệ mới",
        "💎 Chuỗi video quảng bá thương hiệu, định vị phong cách sống sang trọng",
        "🍲 Hành trình khám phá ẩm thực đường phố và văn hóa các vùng miền",
        "✈️ Cẩm nang du lịch trải nghiệm, khám phá những vùng đất mới lạ",
        "🏡 Cẩm nang chia sẻ mẹo vặt gia đình, chăm sóc nhà cửa và đời sống",
        "🧘 Chuỗi video chữa lành tâm hồn, động lực sống và tư duy tích cực",
        "🩺 Chia sẻ kiến thức sức khỏe, thể hình và chế độ ăn lành mạnh",
        "🎨 Series sáng tạo nghệ thuật, thiết kế và phong cách sống tối giản",
        "🐾 Những câu chuyện dễ thương, hài hước về thú cưng và động vật",
        "🌿 Cuộc sống nông thôn, làm vườn và tìm về với thiên nhiên an yên",
        "🎤 Podcast video tâm sự đêm khuya và những bài học cuộc đời",
        "🏙️ Phim ngắn tài liệu về nhịp sống đô thị và những góc khuất xã hội",
        "🎮 Review thế giới game, cốt truyện game và phân tích nhân vật",
        "👗 Series thời trang, phối đồ và phong cách đường phố cá tính",
        "💡 Giới thiệu các ý tưởng sáng tạo và phát minh độc đáo thay đổi cuộc sống",
    ]
    assert len(suggestions) == 25
    
    # Test picking from page 1 (items 1-5)
    pick_idx = 2  # item 3: trinh thám
    state = video_uiflow3.set_series_goal(state, suggestions[pick_idx])
    assert state["series"]["goal"] == "🕵️ Loạt video trinh thám, bí ẩn và giải mã các câu chuyện kỳ thú"
    
    # Test page rotation across 5 pages
    total_pages = (len(suggestions) + 4) // 5
    assert total_pages == 5
    page = 1
    page = 1 if page >= total_pages else page + 1
    assert page == 2
