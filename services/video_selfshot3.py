"""Canonical planning contract for Video tu quay cinematic transformation.

The module is deliberately side-effect free.  It never downloads media, calls a
provider, creates a job, writes a file, or mutates a wallet.  Telegram handlers
use it to keep the public route, transformation timeline, provider capability
decision, and delivery-before-charge invariant in one place.
"""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import html
from typing import Any, Iterable, Mapping

from services import video_profile_catalog


PRODUCT_ID = "self_shot_cinematic_transform"
JOB_TYPE = "self_shot_cinematic_transform"
LEGACY_JOB_TYPE = "self_shot_scene_change"

MODE_ONE_TAKE = "one_take_cinematic"
SUPPORTED_MODES = frozenset({MODE_ONE_TAKE})

SUBJECT_TYPES = frozenset({"person", "object", "pet", "person_object", "multiple", "custom"})
LAYER_STATES = frozenset({"preserve", "transform", "not_applicable"})
MANDATORY_PRESERVE_LAYERS = frozenset({"identity", "body", "motion", "relationship", "camera"})

DEFAULT_LAYER_STATES = {
    "identity": "preserve",
    "body": "preserve",
    "hair": "preserve",
    "wardrobe": "transform",
    "accessories": "preserve",
    "motion": "preserve",
    "expression": "preserve",
    "object": "preserve",
    "brand": "preserve",
    "relationship": "preserve",
    "camera": "preserve",
    "source_audio": "preserve",
    "environment": "transform",
    "lighting": "transform",
    "weather": "not_applicable",
    "effects": "transform",
}

TRANSFORMATION_GROUPS = (
    ("continuous_one_take", "Biến đổi liên tục một cú máy", "biến đổi liền mạch theo chuyển động nguồn"),
    ("motion_new_world", "Giữ chuyển động, đổi thế giới", "giữ nhịp cơ thể và camera, thay toàn bộ không gian"),
    ("wardrobe_morph", "Biến đổi trang phục", "trang phục hình thành dần nhưng nhận diện không đổi"),
    ("character_morph", "Biến đổi nhân vật", "thay tạo hình có kiểm soát, giữ khuôn mặt và vóc dáng"),
    ("fantasy_myth", "Fantasy và thần thoại", "xây thế giới kỳ ảo có chiều sâu và ánh sáng tương tác"),
    ("scifi_cyberpunk", "Khoa học viễn tưởng", "không gian tương lai, công nghệ và ánh sáng điện ảnh"),
    ("history_ancient", "Cổ trang và lịch sử", "trang phục, kiến trúc và đạo cụ đúng cùng thời đại"),
    ("hero_action", "Siêu anh hùng và hành động", "năng lượng, hành động và hero shot rõ ràng"),
    ("magic_vfx", "Phép thuật và hiệu ứng", "hiệu ứng xuất hiện theo cử động, không che chủ thể"),
    ("fashion_runway", "Thời trang và runway", "biến đổi chất liệu, phom dáng và ánh sáng trình diễn"),
    ("music_performance", "Music video và biểu diễn", "hiệu ứng bám nhịp nhưng giữ biểu cảm và chuyển động"),
    ("product_commercial", "Quảng cáo sản phẩm", "giữ hình dáng, logo, màu và tương tác tay-vật"),
    ("travel_fantasy", "Du lịch thế giới kỳ ảo", "mở rộng địa điểm quanh hành trình nguồn"),
    ("season_time", "Mùa, thời tiết và ngày đêm", "chuyển ánh sáng và khí quyển theo thời gian"),
    ("pet_object_character", "Thú cưng và vật thể nhân vật", "giữ đặc điểm nhận diện và chuyển động tự nhiên"),
    ("cinematic_story", "Phim có cốt truyện", "dựng lại thế giới và hành động thành mạch phim nhiều nhịp"),
)

_PRESET_BEATS = (
    ("Ánh sáng thức tỉnh", "ánh sáng nhỏ xuất hiện, lan theo chuyển động rồi mở thế giới mới"),
    ("Hạt sáng kết tinh", "hạt sáng tập trung thành trang phục và không gian hoàn chỉnh"),
    ("Cánh hoa dẫn lối", "cánh hoa đi theo tay, mở rộng cảnh vật và kết ở hero shot"),
    ("Cổng không gian", "portal mở có chiều sâu, chủ thể bước qua mà không đứt chuyển động"),
    ("Sóng biến đổi", "làn sóng đi từ dưới lên, thay vật liệu và ánh sáng từng lớp"),
    ("Vòng xoay trang phục", "chuyển đổi bám vòng xoay cơ thể, giữ mặt và tỷ lệ"),
    ("Bước chân đổi thế giới", "mỗi bước chân lan cảnh vật mới ra phía trước"),
    ("Chạm tay kích hoạt", "cử động tay kích hoạt hiệu ứng rồi biến đổi môi trường"),
    ("Gương phản chiếu", "phản chiếu cho thấy trạng thái đích trước khi hai thế giới hòa vào nhau"),
    ("Mưa sang nắng", "thời tiết đổi dần, ánh sáng phản ứng đúng trên chủ thể"),
    ("Ngày sang đêm", "nhiệt độ màu, đèn và bầu trời chuyển liên tục"),
    ("Vật thể trung tâm", "vật đang cầm giữ nguyên và trở thành tâm điểm câu chuyện"),
    ("Kiến trúc trỗi dậy", "công trình xuất hiện từ xa đến gần, có foreground và bóng đổ"),
    ("Năng lượng bảo hộ", "hào quang bao quanh nhưng không che mặt, tay hoặc sản phẩm"),
    ("Chuyển chất liệu", "vải, kim loại hoặc ánh sáng đổi vật liệu theo từng vùng"),
    ("Thời đại giao nhau", "không gian hiện đại chuyển sang thời đại khác mà camera không nhảy"),
    ("Thế giới thu nhỏ", "môi trường thu nhỏ mở rộng quanh chủ thể với tỷ lệ nhất quán"),
    ("Sân khấu điện ảnh", "ánh sáng sân khấu, sương và camera hoàn thiện dần"),
    ("Hành trình anh hùng", "trạng thái bình thường tiến tới tạo hình mạnh mẽ và khung kết rõ"),
    ("Biến đổi tối giản", "ít hiệu ứng, tập trung vào ánh sáng, trang phục và continuity"),
)

WORLD_OPTIONS = (
    "thành phố tương lai", "thiên nhiên fantasy", "cung điện", "chiến trường",
    "không gian", "sa mạc", "biển", "rừng", "sân khấu", "showroom cao cấp",
    "phố cyberpunk", "cổ đại", "hậu tận thế", "thế giới hoạt hình", "thiên đường",
    "thế giới thu nhỏ",
)

EFFECT_OPTIONS = (
    "hạt sáng", "cánh hoa", "tuyết", "mưa", "sương", "tia năng lượng",
    "lửa", "khói", "bụi", "phép thuật", "portal", "vệt chuyển động",
    "lens flare", "ánh sáng thể tích", "sóng biến đổi",
)

LAYER_LABELS = {
    "identity": "Khuôn mặt/nhận diện",
    "body": "Vóc dáng/tỉ lệ",
    "hair": "Tóc",
    "wardrobe": "Trang phục",
    "accessories": "Phụ kiện",
    "motion": "Chuyển động nguồn",
    "expression": "Biểu cảm",
    "object": "Vật thể/sản phẩm",
    "brand": "Logo/màu thương hiệu",
    "relationship": "Tương tác người-vật",
    "camera": "Chuyển động camera",
    "source_audio": "Âm thanh nguồn",
    "environment": "Cảnh vật",
    "lighting": "Ánh sáng",
    "weather": "Thời tiết",
    "effects": "Hiệu ứng",
}

SUBJECT_OPTIONS = (
    ("person", "👤 Một người"),
    ("object", "📦 Một vật/sản phẩm"),
    ("pet", "🐾 Thú cưng"),
    ("person_object", "👤📦 Người + vật"),
    ("multiple", "👥 Nhiều chủ thể"),
    ("custom", "✍️ Tự mô tả"),
)

WARDROBE_OPTIONS = (
    "Giữ trang phục nguồn",
    "Kỳ ảo thanh lịch",
    "Cổ trang điện ảnh",
    "Tương lai cao cấp",
    "Siêu anh hùng tinh tế",
    "Thời trang trình diễn",
)

CONTENT_PROFILE_ROWS = tuple(
    dict(item)
    for item in video_profile_catalog.PROFILE_SEEDS
    if bool(item.get("is_active", 1))
)
CONTENT_PROFILES = tuple(str(item.get("public_name") or "") for item in CONTENT_PROFILE_ROWS)

AUDIO_LABELS = {
    "source": "Âm thanh gốc",
    "voice": "Lồng tiếng",
    "music": "Nhạc nền",
    "sfx": "Hiệu ứng âm thanh",
    "subtitle": "Phụ đề",
}

SCREEN_PARENTS = {
    "intro": "hub",
    "types": "intro",
    "project": "intro",
    "help": "intro",
    "source_ready": "intro",
    "analysis": "source_ready",
    "segment": "source_ready",
    "segment_preview": "segment",
    "subject": "segment",
    "layers": "subject",
    "groups": "layers",
    "presets": "groups",
    "content_profiles": "presets",
    "idea_library": "presets",
    "structure": "presets",
    "content": "structure",
    "timeline": "content",
    "wardrobe": "timeline",
    "world": "wardrobe",
    "effects": "world",
    "audio": "effects",
    "volume": "audio",
    "review": "effects",
    "finish": "review",
    "package": "finish",
}

CALLBACK_OPERATION_SCREENS = {
    "source": frozenset({"intro", "source_ready", "analysis"}),
    "segment": frozenset({"source_ready", "segment", "segment_preview"}),
    "subject": frozenset({"subject"}),
    "layer": frozenset({"layers"}),
    "layers_reset": frozenset({"layers"}),
    "group_preview": frozenset({"types"}),
    "group": frozenset({"groups"}),
    "preset_page": frozenset({"presets"}),
    "preset_custom": frozenset({"presets"}),
    "preset": frozenset({"presets"}),
    "content_profile_page": frozenset({"content_profiles"}),
    "content_profile": frozenset({"content_profiles"}),
    "idea_page": frozenset({"idea_library"}),
    "idea_pick": frozenset({"idea_library"}),
    "structure": frozenset({"structure"}),
    "content": frozenset({"content"}),
    "timeline": frozenset({"timeline"}),
    "wardrobe": frozenset({"wardrobe"}),
    "world": frozenset({"world"}),
    "effect": frozenset({"effects"}),
    "audio": frozenset({"audio"}),
    "volume": frozenset({"audio"}),
    "volume_set": frozenset({"volume"}),
    "prompt": frozenset({"review"}),
    "finish": frozenset({"review", "finish", "package"}),
    "quality": frozenset({"package"}),
}

STEP_SEQUENCE = (
    "intro",
    "awaiting_source_video",
    "source_ready",
    "segment",
    "subject",
    "layer_rules",
    "transformation_type",
    "structure",
    "content",
    "timeline",
    "wardrobe",
    "world",
    "effects",
    "review",
    "finish",
    "package",
    "invoice",
    "confirm",
)


def transformation_catalog() -> list[dict[str, Any]]:
    """Return 16 groups with 20 deterministic presets per group."""

    rows: list[dict[str, Any]] = []
    for group_index, (group_id, title, focus) in enumerate(TRANSFORMATION_GROUPS, 1):
        presets = []
        for preset_index, (preset_title, beat) in enumerate(_PRESET_BEATS, 1):
            presets.append({
                "preset_id": f"{group_id}:{preset_index:02d}",
                "title": preset_title,
                "summary": f"{focus}; {beat}.",
                "group_id": group_id,
                "group_title": title,
            })
        rows.append({
            "group_id": group_id,
            "group_index": group_index,
            "title": title,
            "focus": focus,
            "presets": presets,
        })
    return rows


def transformation_group_for_content_profile(profile_index: int) -> dict[str, Any]:
    index = max(1, min(len(CONTENT_PROFILE_ROWS), int(profile_index or 1)))
    profile = dict(CONTENT_PROFILE_ROWS[index - 1])
    tags = {
        str(value or "").strip().lower()
        for field in (
            "narrative_tags",
            "industry_tags",
            "visual_tags",
            "platform_tags",
            "goal_tags",
        )
        for value in profile.get(field) or []
        if str(value or "").strip()
    }
    key = str(profile.get("profile_key") or "")
    if key in {"fashion_lookbook", "beauty_skincare_wellness"} or "fashion" in tags:
        group_id = "fashion_runway"
    elif key in {"music_performance_visualizer", "event_highlight", "social_creator_trend"} or "music" in tags:
        group_id = "music_performance"
    elif key == "pets_animals" or {"pet", "animals"}.intersection(tags):
        group_id = "pet_object_character"
    elif key in {"history_culture_mythology"} or {"history", "period", "culture"}.intersection(tags):
        group_id = "history_ancient"
    elif key in {"game_trailer", "app_software_demo", "engineering_industrial"} or {"game", "technology", "industrial"}.intersection(tags):
        group_id = "scifi_cyberpunk"
    elif key in {"character_animation_vfx", "short_film_trailer"} or {"animation", "dramatic", "cinematic"}.intersection(tags):
        group_id = "magic_vfx" if key == "character_animation_vfx" else "cinematic_story"
    elif key in {"travel_local_culture", "architecture_real_estate"} or {"travel", "real_estate", "architecture"}.intersection(tags):
        group_id = "travel_fantasy"
    elif key in {"sports_esports", "automotive_transport"} or {"sport", "esports", "automotive"}.intersection(tags):
        group_id = "hero_action"
    elif key in {"sales_ads", "product_review_demo", "affiliate_ugc", "testimonial_case_study", "brand_corporate", "product_3d_showcase"} or {"commerce", "business", "product"}.intersection(tags):
        group_id = "product_commercial"
    elif key in {"asmr_relax_lofi_visualizer"} or {"ambient", "lofi"}.intersection(tags):
        group_id = "season_time"
    else:
        group_id = "cinematic_story"
    return next(
        (dict(item) for item in transformation_catalog() if item["group_id"] == group_id),
        dict(transformation_catalog()[0]),
    )


def contextual_preset_page(state: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """Return five profile-specific directions without changing transform semantics."""

    current = dict(state or {})
    group_id = str(current.get("selected_group_id") or TRANSFORMATION_GROUPS[0][0])
    page = max(1, min(4, int(current.get("preset_page") or 1)))
    group = next(
        (item for item in transformation_catalog() if item["group_id"] == group_id),
        transformation_catalog()[0],
    )
    start = (page - 1) * 5
    options = [dict(item) for item in group["presets"][start:start + 5]]
    if str(current.get("preset_source") or "") != "content_profile":
        return options
    profile_key = str(current.get("content_profile_key") or "")
    profile = next(
        (dict(item) for item in CONTENT_PROFILE_ROWS if str(item.get("profile_key") or "") == profile_key),
        {},
    )
    if not profile:
        return options
    pattern = [str(item or "").strip() for item in profile.get("default_scene_pattern") or [] if str(item or "").strip()]
    if not pattern:
        pattern = ["Mở đầu", "Diễn biến", "Điểm nhấn", "Kết"]
    description = str(profile.get("description") or profile.get("public_name") or "").strip()
    result = []
    for index, item in enumerate(options):
        offset = (index + start) % len(pattern)
        ordered = pattern[offset:] + pattern[:offset]
        result.append({
            **item,
            "preset_id": f"{item['preset_id']}:{profile_key}",
            "title": f"{ordered[0]} · {item['title']}",
            "summary": (
                f"{description}. Mạch riêng: {' → '.join(ordered)}. {item['summary']}"
            ).strip(),
            "content_profile_key": profile_key,
        })
    return result


def initial_draft() -> dict[str, Any]:
    return {
        "product_id": PRODUCT_ID,
        "selfshot_mode": MODE_ONE_TAKE,
        "selfshot3_screen": "intro",
        "layer_rules": default_layer_rules(),
        "selected_effects": [],
        "content_profile_page": 1,
        "idea_library_page": 1,
        "audio_plan": {
            "source": {"enabled": True, "volume": 100},
            "voice": {"enabled": False, "volume": 100},
            "music": {"enabled": False, "volume": 40},
            "sfx": {"enabled": False, "volume": 40},
            "subtitle": {"enabled": False, "volume": 0},
            "ducking": True,
            "clipping_guard": True,
        },
        "provider_called": False,
        "job_created": False,
        "outbox_created": False,
        "generated_files": 0,
        "wallet_mutations": 0,
        "xu_charged": 0,
    }


def screen_parent(
    screen: str,
    state: Mapping[str, Any] | None = None,
) -> str:
    name = str(screen or "intro")
    override = str(
        (dict(state or {}).get("screen_return_overrides") or {}).get(name) or ""
    )
    if override in set(SCREEN_PARENTS) | {"hub"}:
        return override
    return SCREEN_PARENTS.get(name, "intro")


def callback_operation_allowed(screen: str, operation: str) -> bool:
    """Allow state-changing callbacks only from their canonical owner screen."""

    owner_screens = CALLBACK_OPERATION_SCREENS.get(str(operation or ""))
    return bool(owner_screens and str(screen or "intro") in owner_screens)


def callback_allowed(
    screen: str,
    callback_data: str,
    state: Mapping[str, Any] | None = None,
) -> bool:
    """Accept a button only when it belongs to the currently rendered screen."""

    model = screen_model(screen, state)
    allowed = {
        str(callback)
        for row in model.get("rows") or []
        for _label, callback in row
    }
    return str(callback_data or "") in allowed


def _safe(value: Any) -> str:
    return html.escape(str(value or ""), quote=False)


def _nav(back_screen: str) -> list[tuple[str, str]]:
    callback = "vproduct|selfshot_hub" if back_screen == "hub" else f"vproduct|ss3|show|{back_screen}"
    return [("⬅️ Quay lại", callback), ("🎬 Menu Video", "menu|main_video")]


def _status_label(enabled: bool) -> str:
    return "✅" if enabled else "□"


def screen_model(screen: str, state: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Build one deterministic public screen with an exact parent callback."""

    current = dict(state or {})
    name = str(screen or "intro")
    rows: list[list[tuple[str, str]]] = []
    title = "🎥 Tự quay & biến đổi điện ảnh"
    body = ""

    if name == "intro":
        body = (
            "Gửi video mộc để giữ đúng khuôn mặt, vóc dáng, chuyển động và tương tác nguồn trong cùng một cú máy. "
            "TOAN AAS chỉ biến đổi những lớp anh/chị cho phép như trang phục, cảnh vật, ánh sáng và hiệu ứng."
        )
        rows = [
            [("📎 Gửi video nguồn", "vproduct|ss3|source"), ("✨ Xem kiểu biến đổi", "vproduct|ss3|show|types")],
            [("📁 Dự án đang làm", "vproduct|ss3|show|project"), ("ℹ️ Cách hoạt động", "vproduct|ss3|show|help")],
        ]
    elif name == "types":
        title = "✨ Các kiểu biến đổi một cú máy"
        body = "Có 16 nhóm, mỗi nhóm 20 hướng. Tất cả đều giữ chuyển động nguồn và không cắt sang clip không liên quan."
        groups = transformation_catalog()
        rows = [[(f"{item['group_index']}. {item['title']}", f"vproduct|ss3|group_preview|{item['group_id']}") for item in groups[index:index + 2]] for index in range(0, len(groups), 2)]
    elif name == "project":
        title = "📁 Dự án biến đổi đang làm"
        body = (
            f"Video nguồn: {'Đã nhận' if current.get('source_video') or current.get('source_asset') else 'Chưa có'}\n"
            f"Chủ thể: {_safe((current.get('subject_manifest') or {}).get('selection_type') or 'Chưa chọn')}\n"
            f"Kiểu biến đổi: {_safe((current.get('selected_preset') or {}).get('title') or 'Chưa chọn')}\n"
            f"Mạch biến đổi: {len(list(current.get('transformation_stages') or []))} giai đoạn"
        )
        resume = str(current.get("selfshot3_resume_screen") or "")
        resume_callback = f"vproduct|ss3|show|{resume}" if resume and resume != "intro" else "vproduct|ss3|source"
        rows = [[("▶️ Tiếp tục dự án", resume_callback), ("🗑️ Xóa phiên", "vproduct|ss3|reset")]]
    elif name == "help":
        title = "ℹ️ Cách hoạt động"
        body = (
            "1. Gửi video nguồn và chọn đoạn cần dùng.\n"
            "2. Chọn người, vật hoặc thú cưng cần giữ.\n"
            "3. Khóa những lớp phải giữ nguyên.\n"
            "4. Chọn kiểu biến đổi và chia 2–5 giai đoạn liên tục.\n"
            "5. Xem mạch biến đổi, âm thanh và toàn bộ câu lệnh trước hóa đơn.\n"
            "6. Chỉ sau xác nhận cuối hệ thống mới tạo video; chỉ trừ Xu sau khi video hợp lệ đã giao thành công."
        )
    elif name == "source_ready":
        analysis = dict(current.get("source_analysis") or {})
        title = "✅ Đã nhận video nguồn"
        body = (
            f"Thời lượng: {float(analysis.get('duration_seconds') or 0):.1f} giây\n"
            f"Kích thước: {int(analysis.get('width') or 0)}×{int(analysis.get('height') or 0)}\n"
            f"Tốc độ khung hình: {float(analysis.get('fps') or 0):.2f} hình/giây\n\n"
            "Chọn toàn bộ video hoặc đúng một đoạn trước khi khóa chủ thể."
        )
        rows = [
            [("✅ Dùng toàn bộ video", "vproduct|ss3|segment|whole"), ("✂️ Chọn một đoạn", "vproduct|ss3|segment|custom")],
            [("🔎 Xem phân tích", "vproduct|ss3|show|analysis"), ("📎 Gửi video khác", "vproduct|ss3|source")],
        ]
    elif name == "analysis":
        report = dict(current.get("source_analysis") or {})
        title = "🔎 Phân tích video nguồn"
        body = (
            f"Cú máy: {len(list(report.get('shot_manifest') or [])) or 1}\n"
            f"Chuyển động camera: {_safe(report.get('camera_motion') or 'chưa phân loại')}\n"
            f"Người: {len(list(report.get('person_tracks') or []))} · Vật: {len(list(report.get('object_tracks') or []))} · Thú cưng: {len(list(report.get('pet_tracks') or []))}\n"
            f"Tương tác đã nhận diện: {len(list(report.get('interaction_graph') or []))}\n\n"
            "Kết quả này dùng để khóa đúng chủ thể, quan hệ và chuyển động nguồn."
        )
        rows = [[("➡️ Chọn đoạn video", "vproduct|ss3|show|segment"), ("📎 Gửi video khác", "vproduct|ss3|source")]]
    elif name == "segment":
        title = "✂️ Chọn đoạn video nguồn"
        body = "Dùng toàn bộ video hoặc nhập mốc bắt đầu–kết thúc. Đoạn chọn phải giữ nguyên nhịp chuyển động và camera nguồn."
        rows = [
            [("🎬 Dùng toàn bộ", "vproduct|ss3|segment|whole"), ("✂️ Chọn một đoạn", "vproduct|ss3|segment|custom")],
            [("▶️ Xem đoạn đã chọn", "vproduct|ss3|segment|preview"), ("🔄 Chọn lại", "vproduct|ss3|segment|reset")],
        ]
    elif name == "segment_preview":
        segment = dict(current.get("source_segment") or {})
        title = "▶️ Đoạn video đã chọn"
        if segment:
            body = (
                f"Bắt đầu: {int(segment.get('start_ms') or 0) / 1000:.1f} giây\n"
                f"Kết thúc: {int(segment.get('end_ms') or 0) / 1000:.1f} giây\n"
                f"Thời lượng: {int(segment.get('duration_ms') or 0) / 1000:.1f} giây\n\n"
                "Đoạn này giữ nguyên chuyển động và camera nguồn."
            )
        else:
            body = "Chưa chọn đoạn video. Hãy dùng toàn bộ hoặc nhập mốc bắt đầu–kết thúc."
        rows = [[("✅ Dùng đoạn này", "vproduct|ss3|segment|accept"), ("🎬 Dùng toàn bộ", "vproduct|ss3|segment|whole")]]
    elif name == "subject":
        title = "🎯 Chọn chủ thể cần giữ"
        analysis = dict(current.get("source_analysis") or {})
        counts = analysis_track_counts(analysis)
        available = {
            "person": counts["person"] > 0 and counts["face"] > 0,
            "object": counts["object"] + counts["product"] > 0,
            "pet": counts["pet"] > 0,
            "person_object": counts["person"] > 0 and counts["object"] + counts["product"] > 0,
            "multiple": counts["person"] + counts["object"] + counts["product"] + counts["pet"] >= 2,
            "custom": True,
        }
        options = [(key, label) for key, label in SUBJECT_OPTIONS if available.get(key)]
        blocker_text = str(current.get("selfshot3_subject_blocker") or "").strip()
        if blocker_text:
            body = blocker_text
        elif len(options) == 1 and options[0][0] == "custom":
            body = (
                "Chưa xác định được người, vật hoặc thú cưng riêng biệt từ phân tích cục bộ. "
                "Hãy tự mô tả chủ thể để tạo neo nguồn; hệ thống không tự đoán nhận diện."
            )
        else:
            body = (
                f"Đã nhận diện: người {counts['person']} · khuôn mặt {counts['face']} · "
                f"vật/sản phẩm {counts['object'] + counts['product']} · thú cưng {counts['pet']}.\n"
                "Chọn đúng chủ thể cần giữ xuyên suốt; không tự thay chủ thể khác."
            )
        rows = [[(label, f"vproduct|ss3|subject|{key}") for key, label in options[index:index + 2]] for index in range(0, len(options), 2)]
        if rows and len(rows[-1]) == 1:
            rows[-1].append(("🔎 Xem phân tích", "vproduct|ss3|show|analysis"))
    elif name == "layers":
        title = "🔒 Lớp giữ nguyên và lớp được biến đổi"
        body = (
            "Bấm từng mục để chuyển giữa Giữ nguyên → Biến đổi → Không áp dụng. "
            "Khuôn mặt, vóc dáng, chuyển động, tương tác và camera nguồn luôn được khóa giữ nguyên."
        )
        rules = dict(current.get("layer_rules") or DEFAULT_LAYER_STATES)
        buttons = []
        icons = {"preserve": "🔒", "transform": "✨", "not_applicable": "—"}
        for key, label in LAYER_LABELS.items():
            value = str(rules.get(key) or DEFAULT_LAYER_STATES[key])
            buttons.append((f"{icons.get(value, '—')} {label}", f"vproduct|ss3|layer|{key}"))
        rows = [buttons[index:index + 2] for index in range(0, len(buttons), 2)]
        rows.append([("✅ Xong phần giữ/đổi", "vproduct|ss3|show|groups"), ("↩️ Khôi phục mặc định", "vproduct|ss3|layers_reset")])
    elif name == "groups":
        title = "🎬 Chọn nhóm biến đổi"
        body = "Chọn một nhóm rồi xem 20 hướng cụ thể. Mỗi hướng là biến đổi liên tục trong cùng cú máy."
        groups = transformation_catalog()
        rows = [[(f"{item['group_index']}. {item['title']}", f"vproduct|ss3|group|{item['group_id']}") for item in groups[index:index + 2]] for index in range(0, len(groups), 2)]
    elif name == "presets":
        group_id = str(current.get("selected_group_id") or TRANSFORMATION_GROUPS[0][0])
        page = max(1, min(4, int(current.get("preset_page") or 1)))
        options = contextual_preset_page(current)
        group = next((item for item in transformation_catalog() if item["group_id"] == group_id), transformation_catalog()[0])
        title = f"✨ {group['title']}"
        context_label = str(current.get("content_profile") or "").strip()
        context_line = f"\nBối cảnh nội dung: {_safe(context_label)}" if context_label else ""
        body = "\n".join(
            f"{index}. {_safe(item['title'])}: {_safe(item['summary'])}"
            for index, item in enumerate(options, 1)
        ) + context_line
        rows = [[(str(index), f"vproduct|ss3|preset|{index}") for index in range(1, 6)]]
        rows.append([("🔄 Đổi 5 gợi ý", "vproduct|ss3|preset_page"), ("✍️ Tự nhập", "vproduct|ss3|preset_custom")])
        rows.append([("🎯 32 loại nội dung", "vproduct|ss3|show|content_profiles"), ("🗂️ Kho Ý tưởng video", "vproduct|ss3|show|idea_library")])
    elif name == "content_profiles":
        page = max(1, min(4, int(current.get("content_profile_page") or 1)))
        start = (page - 1) * 8
        options = CONTENT_PROFILE_ROWS[start:start + 8]
        title = "🎯 Chọn loại nội dung"
        body = (
            f"Trang {page}/4. Chọn đúng một loại nội dung; hệ thống sẽ quay lại 5 hướng biến đổi bám sát loại đã chọn. "
            "Lựa chọn này không tự ghi đè video nguồn hoặc các lớp đã khóa."
        )
        rows = [
            [
                (
                    f"{item.get('icon') or '🎯'} {item.get('short_name') or item.get('public_name') or ''}",
                    f"vproduct|ss3|content_profile|{start + index + 1}",
                )
                for index, item in enumerate(options[offset:offset + 2], offset)
            ]
            for offset in range(0, len(options), 2)
        ]
        rows.append([("➡️ Nhóm tiếp theo", "vproduct|ss3|content_profile_page"), ("🎬 Đổi nhóm biến đổi", "vproduct|ss3|show|groups")])
    elif name == "idea_library":
        page = max(1, min(2, int(current.get("idea_library_page") or 1)))
        groups = transformation_catalog()
        start = (page - 1) * 8
        options = groups[start:start + 8]
        title = "🗂️ Kho Ý tưởng video"
        body = (
            f"Trang {page}/2. Mỗi ý tưởng đã có cấu trúc biến đổi, nhịp, máy quay và mạch liên tục cho video tự quay. "
            "Chọn một ý tưởng rồi vẫn được xem và sửa mạch biến đổi trước khi hoàn thiện."
        )
        rows = [
            [(item["title"], f"vproduct|ss3|idea_pick|{start + index + 1}") for index, item in enumerate(options[offset:offset + 2], offset)]
            for offset in range(0, len(options), 2)
        ]
        rows.append([("➡️ 8 ý tưởng tiếp", "vproduct|ss3|idea_page"), ("🎬 Đổi nhóm biến đổi", "vproduct|ss3|show|groups")])
    elif name == "structure":
        title = "🎞 Chia giai đoạn biến đổi"
        body = "Chọn 2–5 giai đoạn. Mỗi giai đoạn tiếp nhận đúng trạng thái cuối của giai đoạn trước, không cắt cảnh đột ngột."
        rows = [[("2 giai đoạn", "vproduct|ss3|structure|2"), ("3 giai đoạn", "vproduct|ss3|structure|3")], [("4 giai đoạn", "vproduct|ss3|structure|4"), ("5 giai đoạn", "vproduct|ss3|structure|5")]]
    elif name == "content":
        preset = dict(current.get("selected_preset") or {})
        title = "📝 Nội dung biến đổi"
        body = f"Hướng đã chọn: {_safe(preset.get('title') or 'Tự nhập')}\n\nDùng nội dung gợi ý hoặc viết mục tiêu/câu chuyện riêng cho một cú máy."
        rows = [[("✅ Dùng nội dung gợi ý", "vproduct|ss3|content|preset"), ("✍️ Tự nhập nội dung", "vproduct|ss3|content|custom")]]
    elif name == "timeline":
        stages = list(current.get("transformation_stages") or [])
        title = "🧭 Mạch biến đổi"
        body = "\n".join(
            f"Giai đoạn {index}: {int(item.get('start_ms') or 0) / 1000:.1f}s–{int(item.get('end_ms') or 0) / 1000:.1f}s · {_safe(item.get('target_state'))}"
            for index, item in enumerate(stages, 1)
        ) or "Chưa có mạch biến đổi."
        rows = [[("🔄 Lập lại mạch", "vproduct|ss3|timeline|rebuild"), ("✍️ Sửa mạch", "vproduct|ss3|timeline|custom")], [("✅ Dùng mạch này", "vproduct|ss3|show|wardrobe"), ("🎬 Xem kiểu đã chọn", "vproduct|ss3|show|presets")]]
    elif name == "wardrobe":
        title = "👗 Trang phục"
        body = f"Đang chọn: {_safe(current.get('wardrobe') or 'Chưa chọn')}\nChỉ biến đổi trang phục nếu mục Trang phục đang ở trạng thái Biến đổi."
        rows = [[(label, f"vproduct|ss3|wardrobe|{index}") for index, label in list(enumerate(WARDROBE_OPTIONS, 1))[offset:offset + 2]] for offset in range(0, len(WARDROBE_OPTIONS), 2)]
        rows.append([("✍️ Tự nhập trang phục", "vproduct|ss3|wardrobe|custom"), ("✅ Xong trang phục", "vproduct|ss3|show|world")])
    elif name == "world":
        title = "🌍 Thế giới và cảnh vật"
        body = f"Đang chọn: {_safe(current.get('world') or 'Chưa chọn')}\nChọn một thế giới thống nhất với chuyển động, ánh sáng và tỷ lệ của video nguồn."
        rows = [[(label, f"vproduct|ss3|world|{index + 1}") for index, label in list(enumerate(WORLD_OPTIONS))[offset:offset + 2]] for offset in range(0, len(WORLD_OPTIONS), 2)]
        rows.append([("✍️ Tự nhập cảnh vật", "vproduct|ss3|world|custom"), ("✅ Xong cảnh vật", "vproduct|ss3|show|effects")])
    elif name == "effects":
        selected = set(current.get("selected_effects") or [])
        title = "✨ Hiệu ứng điện ảnh"
        body = "Chỉ chọn hiệu ứng có động cơ trong cảnh; hiệu ứng không được che mặt, tay, vật hoặc sản phẩm."
        buttons = [(f"{_status_label(label in selected)} {label}", f"vproduct|ss3|effect|{index + 1}") for index, label in enumerate(EFFECT_OPTIONS)]
        buttons.append(("🚫 Không thêm hiệu ứng", "vproduct|ss3|effect|none"))
        rows = [buttons[index:index + 2] for index in range(0, len(buttons), 2)]
        rows.append([("✅ Xong hiệu ứng", "vproduct|ss3|show|review"), ("↩️ Tắt toàn bộ", "vproduct|ss3|effect|clear")])
    elif name == "audio":
        plan = dict(current.get("audio_plan") or initial_draft()["audio_plan"])
        title = "🎙️ Âm thanh và phụ đề"
        body = "Âm lượng chỉnh từ 0–200%. Có chống vỡ tiếng và tự hạ nhạc khi có lời. Nếu video nguồn chỉ có một luồng âm thanh đã trộn, hệ thống sẽ giữ đúng giới hạn đó."
        items = []
        for key in ("source", "voice", "music", "sfx", "subtitle"):
            item = dict(plan.get(key) or {})
            suffix = f" {int(item.get('volume') or 0)}%" if key != "subtitle" else ""
            items.append((f"{_status_label(bool(item.get('enabled')))} {AUDIO_LABELS[key]}{suffix}", f"vproduct|ss3|audio|{key}"))
        items.append(("🎚️ Chỉnh âm lượng", "vproduct|ss3|volume|source"))
        rows = [items[index:index + 2] for index in range(0, len(items), 2)]
        rows.append([("✅ Xong âm thanh", "vproduct|ss3|show|review"), ("🚫 Bỏ qua âm thanh", "vproduct|ss3|audio|skip")])
    elif name == "volume":
        target = str(current.get("audio_volume_target") or "source")
        title = f"🎚️ Âm lượng {AUDIO_LABELS.get(target, target)}"
        body = "Chọn mức 0–200%. Hệ thống chống vỡ tiếng và tự hạ nhạc khi có lời."
        values = (0, 20, 40, 60, 80, 100, 120, 150, 180, 200)
        buttons = [(f"{value}%", f"vproduct|ss3|volume_set|{value}") for value in values]
        rows = [buttons[index:index + 2] for index in range(0, len(buttons), 2)]
    elif name == "review":
        preset = dict(current.get("selected_preset") or {})
        stages = list(current.get("transformation_stages") or [])
        title = "👁️ <b>Xem lại kế hoạch biến đổi</b>"
        body = (
            f"• <b>Đoạn nguồn:</b> {int((current.get('source_segment') or {}).get('duration_ms') or 0) / 1000:.1f} giây\n"
            f"• <b>Chủ thể:</b> {_safe((current.get('subject_manifest') or {}).get('selection_type'))}\n"
            f"• <b>Kiểu:</b> {_safe(preset.get('title'))}\n"
            f"• <b>Mạch biến đổi:</b> {len(stages)} giai đoạn\n"
            f"• <b>Trang phục:</b> {_safe(current.get('wardrobe'))}\n"
            f"• <b>Thế giới:</b> {_safe(current.get('world'))}\n"
            f"• <b>Hiệu ứng:</b> {_safe(', '.join(current.get('selected_effects') or []) or 'Không thêm')}\n\n"
            "Kiểm tra kế hoạch rồi bấm <b>Tiếp tục sang Add-on</b> để hoàn thiện âm thanh và tạo video."
        )
        rows = [
            [("🧭 Mạch biến đổi", "vproduct|ss3|show|timeline"), ("📝 Câu lệnh", "vproduct|ss3|prompt")],
            [("🔒 Lớp giữ/đổi", "vproduct|ss3|show|layers"), ("👗 Trang phục", "vproduct|ss3|show|wardrobe")],
            [("✍️ Sửa nội dung", "vproduct|ss3|show|content"), ("✨ Hiệu ứng", "vproduct|ss3|show|effects")],
            [("➡️ Tiếp tục sang Add-on", "vproduct|ss3|finish"), ("🎚️ Âm thanh & phụ đề", "vproduct|ss3|show|audio")],
        ]
    elif name == "finish":
        title = "✅ Kiểm tra kế hoạch trước hóa đơn"
        body = (
            "Tiếp tục theo đuôi chung: Add-on → Rà soát → Chất lượng → Hóa đơn → Xác nhận → Trạng thái."
        )
        rows = [[("✅ Hoàn thiện video", "vproduct|ss3|finish"), ("👁️ Xem lại", "vproduct|ss3|finish_review")]]
    elif name == "package":
        title = "⭐ Chất lượng video"
        body = "Bảng Chất lượng dùng chung hiển thị gói phù hợp với thời lượng video nguồn."
        rows = [[("✅ Hoàn thiện video", "vproduct|ss3|finish"), ("👁️ Xem lại kế hoạch", "vproduct|ss3|show|review")]]
    else:
        raise ValueError("unknown_selfshot3_screen")

    rows.append(_nav(screen_parent(name, current)))
    return {"screen": name, "title": title, "text": f"{title}\n\n{body}", "rows": rows}


def catalog_page(group_id: str, page: int = 1) -> list[dict[str, Any]]:
    group = next((item for item in transformation_catalog() if item["group_id"] == str(group_id)), None)
    if not group:
        return []
    page_number = max(1, min(4, int(page or 1)))
    start = (page_number - 1) * 5
    return deepcopy(group["presets"][start:start + 5])


def source_fingerprint(source: Mapping[str, Any] | None) -> str:
    item = dict(source or {})
    token = "|".join(str(item.get(key) or "") for key in (
        "file_unique_id", "file_id", "file_name", "file_size", "duration_seconds", "width", "height"
    ))
    return sha256(token.encode("utf-8")).hexdigest()[:24] if token.strip("|") else ""


def analyze_source(
    source: Mapping[str, Any] | None,
    *,
    detected_people: Iterable[Mapping[str, Any]] = (),
    detected_faces: Iterable[Mapping[str, Any]] = (),
    detected_objects: Iterable[Mapping[str, Any]] = (),
    detected_products: Iterable[Mapping[str, Any]] = (),
    detected_pets: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Normalize no-cost metadata and supplied local detector results."""

    item = dict(source or {})
    duration = max(0.0, float(item.get("duration_seconds") or item.get("duration") or 0))
    width = max(0, int(item.get("width") or 0))
    height = max(0, int(item.get("height") or 0))
    ratio = f"{width}:{height}" if width and height else "unknown"

    def candidates(kind: str, values: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
        result = []
        for index, value in enumerate(values, 1):
            row = dict(value)
            row["subject_id"] = str(row.get("subject_id") or f"{kind}-{index}")
            row["subject_type"] = kind
            row["label"] = str(row.get("label") or f"{kind} {index}")
            result.append(row)
        return result

    people = candidates("person", detected_people)
    faces = candidates("face", detected_faces)
    objects = candidates("object", detected_objects)
    products = candidates("product", detected_products)
    pets = candidates("pet", detected_pets)
    detector_results_supplied = bool(people or faces or objects or products or pets)
    tracking_ready = bool(people or faces or objects or products or pets)
    return {
        "analysis_version": "selfshot3-local-v1",
        "source_hash": source_fingerprint(item),
        "duration_seconds": duration,
        "width": width,
        "height": height,
        "fps": max(0.0, float(item.get("fps") or 0)),
        "aspect_ratio": ratio,
        "format": str(item.get("format") or item.get("mime_type") or ""),
        "audio_streams": max(0, int(item.get("audio_streams") or 0)),
        "shot_manifest": deepcopy(item.get("shot_manifest") or []),
        "camera_motion": str(item.get("camera_motion") or "chưa phân loại"),
        "main_actions": deepcopy(item.get("main_actions") or []),
        "person_tracks": people,
        "face_tracks": faces,
        "object_tracks": objects,
        "product_tracks": products,
        "pet_tracks": pets,
        "interaction_graph": deepcopy(item.get("interaction_graph") or []),
        "logo_text_candidates": deepcopy(item.get("logo_text_candidates") or []),
        "audio_manifest": deepcopy(item.get("audio_manifest") or {}),
        "detector_results_supplied": detector_results_supplied,
        "tracking_source": "supplied_local_detector" if detector_results_supplied else "metadata_only",
        "tracking_ready": tracking_ready,
        "planning_only": True,
        "provider_calls": 0,
    }


def source_gate(source: Mapping[str, Any] | None, analysis: Mapping[str, Any] | None) -> dict[str, Any]:
    item = dict(source or {})
    report = dict(analysis or {})
    has_source = bool(item.get("file_id") or item.get("path"))
    duration_ok = float(report.get("duration_seconds") or 0) > 0
    dimensions_ok = int(report.get("width") or 0) > 0 and int(report.get("height") or 0) > 0
    blocker = "" if has_source and duration_ok and dimensions_ok else (
        "source_video_missing" if not has_source else "source_video_probe_incomplete"
    )
    return {"ok": not blocker, "blocker": blocker, "source_received": has_source, "probe_complete": duration_ok and dimensions_ok}


def default_layer_rules() -> dict[str, str]:
    return dict(DEFAULT_LAYER_STATES)


def update_layer_rule(rules: Mapping[str, str] | None, layer: str, state: str) -> dict[str, str]:
    key = str(layer or "")
    value = str(state or "")
    if key not in DEFAULT_LAYER_STATES:
        raise ValueError("unknown_transformation_layer")
    if value not in LAYER_STATES:
        raise ValueError("invalid_layer_state")
    updated = default_layer_rules()
    updated.update({str(k): str(v) for k, v in dict(rules or {}).items() if k in DEFAULT_LAYER_STATES and v in LAYER_STATES})
    updated[key] = "preserve" if key in MANDATORY_PRESERVE_LAYERS else value
    return updated


def select_subjects(
    analysis: Mapping[str, Any] | None,
    selection_type: str,
    selected_ids: Iterable[str] = (),
    description: str = "",
) -> dict[str, Any]:
    subject_type = str(selection_type or "")
    if subject_type not in SUBJECT_TYPES:
        raise ValueError("invalid_subject_selection")
    report = dict(analysis or {})
    people = list(report.get("person_tracks") or [])
    objects = [*list(report.get("object_tracks") or []), *list(report.get("product_tracks") or [])]
    pets = list(report.get("pet_tracks") or [])
    by_type = {
        "person": people,
        "object": objects,
        "pet": pets,
        "person_object": [*people, *objects],
        "multiple": [*people, *objects, *pets],
        "custom": [],
    }
    all_subjects = list(by_type[subject_type])
    selected = {str(value) for value in selected_ids if str(value)}
    if selected:
        all_subjects = [row for row in all_subjects if str(row.get("subject_id") or "") in selected]
    return {
        "selection_type": subject_type,
        "subjects": deepcopy(all_subjects),
        "selected_ids": [str(row.get("subject_id")) for row in all_subjects],
        "stable_ids": bool(all_subjects) and all(bool(row.get("subject_id")) for row in all_subjects),
        "description": str(description or "").strip()[:1200],
        "source_bound": bool(report.get("source_hash")) and bool(report.get("duration_seconds")),
    }


def analysis_track_counts(analysis: Mapping[str, Any] | None) -> dict[str, int]:
    """Return detector counts without inferring a subject from raw metadata."""

    report = dict(analysis or {})
    return {
        "person": len(list(report.get("person_tracks") or [])),
        "face": len(list(report.get("face_tracks") or [])),
        "object": len(list(report.get("object_tracks") or [])),
        "product": len(list(report.get("product_tracks") or [])),
        "pet": len(list(report.get("pet_tracks") or [])),
        "interaction": len(list(report.get("interaction_graph") or [])),
    }


def subject_tracking_gate(
    analysis: Mapping[str, Any] | None,
    subject_manifest: Mapping[str, Any] | None,
    relationship_locks: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Require a real source-bound track before a non-custom transform route.

    Telegram file metadata alone is not an identity detector.  The gate keeps
    the UI usable for a user-supplied description while preventing an empty
    manifest from being presented as a valid person/object lock.
    """

    report = dict(analysis or {})
    manifest = dict(subject_manifest or {})
    selection_type = str(manifest.get("selection_type") or "")
    counts = analysis_track_counts(report)
    subjects = list(manifest.get("subjects") or [])
    selected_ids = [str(value) for value in (manifest.get("selected_ids") or []) if str(value)]
    blockers: list[str] = []

    if not selection_type or selection_type not in SUBJECT_TYPES:
        blockers.append("subject_selection_missing")
    elif selection_type == "custom":
        if not str(manifest.get("description") or "").strip():
            blockers.append("subject_description_missing")
        if not manifest.get("source_bound") or not report.get("source_hash"):
            blockers.append("custom_subject_source_anchor_missing")
    else:
        if not subjects or not selected_ids or not manifest.get("stable_ids"):
            blockers.append("subject_track_missing")
        if selection_type == "person" and (counts["person"] < 1 or counts["face"] < 1):
            blockers.append("face_identity_track_missing")
        elif selection_type == "object" and counts["object"] + counts["product"] < 1:
            blockers.append("object_track_missing")
        elif selection_type == "pet" and counts["pet"] < 1:
            blockers.append("pet_track_missing")
        elif selection_type == "person_object" and (counts["person"] < 1 or counts["object"] + counts["product"] < 1):
            blockers.append("person_object_tracks_missing")
        elif selection_type == "multiple" and len(subjects) < 2:
            blockers.append("multiple_subject_tracks_missing")

    if selection_type == "person_object" and not list(relationship_locks or []):
        blockers.append("interaction_lock_missing")

    return {
        "ok": not blockers,
        "blockers": list(dict.fromkeys(blockers)),
        "blocker": blockers[0] if blockers else "",
        "selection_type": selection_type,
        "counts": counts,
        "selected_subject_count": len(subjects),
        "source_hash_present": bool(report.get("source_hash")),
    }


def subject_blocker_text(result: Mapping[str, Any] | None) -> str:
    """Turn an internal subject gate result into one actionable public message."""

    blocker = str((result or {}).get("blocker") or "").strip()
    messages = {
        "subject_selection_missing": "⚠️ Hãy chọn một chủ thể cần giữ trước khi tiếp tục.",
        "subject_description_missing": "⚠️ Hãy mô tả người, vật hoặc thú cưng cần giữ.",
        "custom_subject_source_anchor_missing": "⚠️ Chưa có video nguồn hợp lệ để neo mô tả chủ thể. Hãy gửi lại video nguồn.",
        "subject_track_missing": "⚠️ Chưa có track chủ thể hợp lệ từ video nguồn. Hãy chọn Tự mô tả hoặc gửi video có thông tin rõ hơn.",
        "face_identity_track_missing": "⚠️ Chưa có track khuôn mặt đủ tin cậy để khóa người này.",
        "object_track_missing": "⚠️ Chưa có track vật/sản phẩm đủ tin cậy để khóa chủ thể.",
        "pet_track_missing": "⚠️ Chưa có track thú cưng đủ tin cậy để khóa chủ thể.",
        "person_object_tracks_missing": "⚠️ Chưa đủ track người và vật để giữ đúng tương tác nguồn.",
        "multiple_subject_tracks_missing": "⚠️ Chưa đủ hai track chủ thể để chọn nhiều chủ thể.",
        "interaction_lock_missing": "⚠️ Chưa khóa được tương tác người-vật từ video nguồn.",
    }
    return messages.get(blocker, "⚠️ Chưa đủ dữ liệu nhận diện chủ thể từ video nguồn. Hệ thống chưa chuyển bước.")


def layer_lock_gate(
    layer_rules: Mapping[str, str] | None,
    subject_manifest: Mapping[str, Any] | None,
    relationship_locks: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    rules = dict(layer_rules or {})
    missing = [key for key in MANDATORY_PRESERVE_LAYERS if str(rules.get(key) or "") != "preserve"]
    blockers = ["mandatory_layer_lock_missing"] if missing else []
    if str((subject_manifest or {}).get("selection_type") or "") == "person_object" and not list(relationship_locks or []):
        blockers.append("interaction_lock_missing")
    return {"ok": not blockers, "blockers": list(dict.fromkeys(blockers)), "missing_layers": sorted(missing)}


def build_interaction_lock(subject_manifest: Mapping[str, Any] | None, analysis: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    selected = set((subject_manifest or {}).get("selected_ids") or [])
    relationships = []
    for row in list((analysis or {}).get("interaction_graph") or []):
        item = dict(row)
        person_id = str(item.get("person_id") or "")
        object_id = str(item.get("object_id") or "")
        if selected and person_id not in selected and object_id not in selected:
            continue
        relationships.append({
            "person_id": person_id,
            "object_id": object_id,
            "relationship_type": str(item.get("relationship_type") or "interaction"),
            "contact_points": deepcopy(item.get("contact_points") or []),
            "relative_position": str(item.get("relative_position") or "preserve"),
            "interaction_lock": True,
        })
    return relationships


def segment_selection(analysis: Mapping[str, Any] | None, start_ms: int = 0, end_ms: int | None = None) -> dict[str, Any]:
    duration_ms = max(0, int(float((analysis or {}).get("duration_seconds") or 0) * 1000))
    start = max(0, min(int(start_ms or 0), duration_ms))
    end = duration_ms if end_ms is None else max(start, min(int(end_ms), duration_ms))
    if duration_ms <= 0 or end <= start:
        raise ValueError("valid_source_segment_required")
    return {"start_ms": start, "end_ms": end, "duration_ms": end - start, "whole_source": start == 0 and end == duration_ms}


def build_timeline(
    *,
    segment: Mapping[str, Any],
    stage_count: int,
    preset: Mapping[str, Any] | None = None,
    wardrobe: str = "",
    world: str = "",
    effects: Iterable[str] = (),
) -> list[dict[str, Any]]:
    count = max(2, min(5, int(stage_count or 4)))
    start = int(segment.get("start_ms") or 0)
    end = int(segment.get("end_ms") or 0)
    if end <= start:
        raise ValueError("valid_source_segment_required")
    total = end - start
    preset_row = dict(preset or {})
    effect_list = [str(value) for value in effects if str(value)]
    stages = []
    for index in range(count):
        stage_start = start + (total * index // count)
        stage_end = start + (total * (index + 1) // count)
        progress = index / max(1, count - 1)
        stages.append({
            "stage_id": f"stage-{index + 1}",
            "start_ms": stage_start,
            "end_ms": stage_end,
            "source_state": "video nguồn" if index == 0 else f"trạng thái sau giai đoạn {index}",
            "target_state": "trạng thái điện ảnh hoàn chỉnh" if index == count - 1 else f"biến đổi {round(progress * 100)}%",
            "outfit_change": wardrobe if index > 0 else "chưa đổi",
            "environment_change": world if index > 0 else "giữ cảnh nguồn",
            "lighting_change": "tăng dần ánh sáng tương tác" if index > 0 else "ánh sáng nguồn",
            "effect_layers": effect_list[: max(0, index + 1)],
            "camera_policy": "preserve_source_camera",
            "audio_policy": "preserve_timeline_sync",
            "continuity_constraints": ["identity", "body", "motion", "interaction"],
            "negative_constraints": ["no_abrupt_cut", "no_identity_drift", "no_duplicate_subject"],
            "transition_method": str(preset_row.get("title") or "biến đổi liên tục") if index > 0 else "giữ trạng thái đầu",
        })
    return stages


def compile_prompt(
    *,
    mode: str,
    subject_manifest: Mapping[str, Any],
    relationship_locks: Iterable[Mapping[str, Any]],
    layer_rules: Mapping[str, str],
    segment: Mapping[str, Any],
    stages: Iterable[Mapping[str, Any]],
    wardrobe: str,
    world: str,
    effects: Iterable[str],
    content: str,
) -> dict[str, Any]:
    if mode not in SUPPORTED_MODES:
        raise ValueError("selfshot_mode_required")
    stage_rows = [dict(row) for row in stages]
    if not stage_rows:
        raise ValueError("transformation_timeline_required")
    selected_ids = list(subject_manifest.get("selected_ids") or [])
    negative = (
        "no face replacement, no identity drift, no duplicate person, no extra limbs, "
        "no hand deformation, no body proportion drift, no object disappearance, "
        "no logo distortion, no product color drift, no broken hand-object contact, "
        "no abrupt background cut, no unrelated subject insertion, no temporal flicker"
    )
    stage_prompts = []
    for row in stage_rows:
        stage_prompts.append({
            "stage_id": row["stage_id"],
            "prompt": (
                f"Source segment {segment.get('start_ms')}ms-{segment.get('end_ms')}ms. "
                f"Identity lock: {', '.join(selected_ids) or 'confirmed subject description'}. "
                f"Motion lock: preserve source body, object and camera timing. "
                f"Relationship lock: {list(relationship_locks) or 'preserve all source contact points'}. "
                f"Story: {content or 'cinematic transformation around the selected subject'}. "
                f"Wardrobe: {wardrobe or 'preserve unless approved'}. World: {world or 'cinematic world selected by user'}. "
                f"Effects: {', '.join(str(value) for value in effects) or 'subtle motivated light'}. "
                f"Stage target: {row.get('target_state')}. Camera: {row.get('camera_policy')}. "
                f"Layer rules: {dict(layer_rules)}. Negative: {negative}."
            ),
            "negative_prompt": negative,
        })
    return {
        "compiler_version": "selfshot3-v1",
        "mode": mode,
        "identity_lock": selected_ids,
        "motion_lock": "preserve_source_motion",
        "relationship_locks": [dict(row) for row in relationship_locks],
        "layer_rules": dict(layer_rules),
        "stage_prompts": stage_prompts,
        "negative_prompt": negative,
    }


def capability_route(
    capabilities: Iterable[str],
    *,
    mode: str,
    layer_rules: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    available = {str(value).strip() for value in capabilities if str(value).strip()}
    if "video_to_video" in available:
        available.add("direct_video_to_video")
    if "reference_video" in available:
        available.add("person_identity_reference")
    if "first_last_frame_video" in available:
        available.add("first_last_frame")
    rules = dict(layer_rules or DEFAULT_LAYER_STATES)
    wardrobe_only = rules.get("wardrobe") == "transform" and rules.get("identity") == "preserve"
    routes = (
        ("direct_video_to_video", "direct_video_to_video", "Biến đổi trực tiếp từ video nguồn"),
        ("performance_capture", "performance_capture", "Dùng chuyển động và biểu cảm từ video nguồn"),
        ("regional_mask_transform", "masked_regional_transform", "Biến đổi vùng chọn, giữ chủ thể"),
        ("person_identity_reference", "reference_assisted_video", "Dùng tham chiếu nhận diện cùng chuyển động nguồn"),
        ("first_last_frame", "keyframe_image_to_video", "Chế độ dự phòng sử dụng keyframe, không phải biến đổi video trực tiếp"),
    )
    for capability, route, public_label in routes:
        if capability not in available:
            continue
        if route == "keyframe_image_to_video":
            return {
                "ok": True,
                "route": route,
                "capability": capability,
                "truthful_fallback": True,
                "public_label": public_label,
                "limitations": ["continuity_validation_required", "not_direct_video_to_video"],
            }
        if wardrobe_only and route not in {
            "direct_video_to_video",
            "performance_capture",
            "masked_regional_transform",
            "reference_assisted_video",
        }:
            continue
        return {
            "ok": True,
            "route": route,
            "capability": capability,
            "truthful_fallback": False,
            "public_label": public_label,
            "limitations": [],
        }
    blocker = "regional_identity_capability_missing" if wardrobe_only else "cinematic_transform_capability_missing"
    return {
        "ok": False,
        "route": "",
        "capability": "",
        "truthful_fallback": False,
        "public_label": "",
        "blocker": blocker,
        "fallback": "full_frame_cinematic_transform" if wardrobe_only else "none",
    }


def preflight(
    state: Mapping[str, Any] | None,
    *,
    capabilities: Iterable[str],
    owner_ready: bool,
    package_available: bool,
    delivery_ready: bool,
) -> dict[str, Any]:
    current = dict(state or {})
    draft = dict(current.get("draft") or current)
    blockers: list[str] = []
    gate = source_gate(draft.get("source_video") or draft.get("source_asset"), draft.get("source_analysis"))
    if not gate["ok"]:
        blockers.append(gate["blocker"])
    mode = str(draft.get("selfshot_mode") or MODE_ONE_TAKE)
    if mode not in SUPPORTED_MODES:
        blockers.append("selfshot_mode_missing")
    subject_manifest = dict(draft.get("subject_manifest") or {})
    relationship_locks = list(draft.get("relationship_locks") or [])
    subject_gate = subject_tracking_gate(draft.get("source_analysis"), subject_manifest, relationship_locks)
    blockers.extend(subject_gate.get("blockers") or [])
    lock_gate = layer_lock_gate(draft.get("layer_rules"), subject_manifest, relationship_locks)
    blockers.extend(lock_gate.get("blockers") or [])
    if not draft.get("source_segment"):
        blockers.append("source_segment_missing")
    if not list(draft.get("transformation_stages") or []):
        blockers.append("transformation_timeline_missing")
    route = capability_route(capabilities, mode=mode, layer_rules=draft.get("layer_rules")) if mode in SUPPORTED_MODES else {"ok": False, "blocker": "selfshot_mode_missing"}
    if not route.get("ok"):
        blockers.append(str(route.get("blocker") or "cinematic_transform_capability_missing"))
    if not owner_ready:
        blockers.append("execution_owner_unavailable")
    if not package_available:
        blockers.append("package_unavailable")
    if not delivery_ready:
        blockers.append("delivery_route_unavailable")
    blockers = list(dict.fromkeys(blockers))
    return {
        "ok": not blockers,
        "blocker": blockers[0] if blockers else "",
        "blockers": blockers,
        "engine_route": route,
        "subject_tracking": subject_gate,
        "layer_lock": lock_gate,
        "job_type": JOB_TYPE,
        "product_id": PRODUCT_ID,
        "legacy_product_route": LEGACY_JOB_TYPE,
        "side_effects": {
            "job": 0,
            "outbox": 0,
            "invoice": 0,
            "provider_calls": 0,
            "rendered_files": 0,
            "wallet_mutations": 0,
            "xu_charged": 0,
        },
    }


def continuity_validation(metrics: Mapping[str, Any] | None) -> dict[str, Any]:
    values = dict(metrics or {})
    required = ("identity", "body", "motion", "object", "interaction", "temporal")
    failures = [key for key in required if float(values.get(key, 0)) < 0.8]
    return {
        "ok": not failures,
        "failures": failures,
        "scores": {key: float(values.get(key, 0)) for key in required},
    }


def record_delivery(
    state: Mapping[str, Any] | None,
    *,
    final_mp4_valid: bool,
    message_id: int,
    receipt_key: str,
    continuity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if not final_mp4_valid:
        raise ValueError("valid_final_mp4_required")
    if int(message_id or 0) <= 0 or not str(receipt_key or "").strip():
        raise ValueError("valid_telegram_delivery_required")
    if continuity is not None and not continuity_validation(continuity).get("ok"):
        raise ValueError("continuity_validation_required")
    current = deepcopy(dict(state or {}))
    existing = dict(current.get("delivery") or {})
    expected = {"delivered": True, "message_id": int(message_id), "receipt_key": str(receipt_key)}
    if existing and existing != expected:
        raise ValueError("delivery_receipt_conflict")
    current["delivery"] = expected
    return current


def charge_allowed(state: Mapping[str, Any] | None) -> bool:
    delivery = dict((state or {}).get("delivery") or {})
    return bool(delivery.get("delivered") and int(delivery.get("message_id") or 0) > 0 and delivery.get("receipt_key"))


def back_target(step: str) -> str:
    current = str(step or "intro")
    try:
        index = STEP_SEQUENCE.index(current)
    except ValueError:
        return "intro"
    return "video_menu" if index == 0 else STEP_SEQUENCE[index - 1]


def route_matrix() -> dict[str, dict[str, str]]:
    return {
        "selfshot3_segment": {"owner": "vproduct", "next": "segment", "back": "source_ready"},
        "selfshot3_segment_preview": {"owner": "vproduct", "next": "segment_preview", "back": "segment"},
        "selfshot3_subject": {"owner": "vproduct", "next": "subject", "back": "segment"},
        "selfshot3_layers": {"owner": "vproduct", "next": "layer_rules", "back": "subject"},
        "selfshot3_type": {"owner": "vproduct", "next": "transformation_type", "back": "layer_rules"},
        "selfshot3_structure": {"owner": "vproduct", "next": "structure", "back": "transformation_type"},
        "selfshot3_content": {"owner": "vproduct", "next": "content", "back": "structure"},
        "selfshot3_content_profiles": {"owner": "vproduct", "next": "content_profiles", "back": "presets"},
        "selfshot3_idea_library": {"owner": "vproduct", "next": "idea_library", "back": "presets"},
        "selfshot3_timeline": {"owner": "vproduct", "next": "timeline", "back": "content"},
        "selfshot3_wardrobe": {"owner": "vproduct", "next": "wardrobe", "back": "timeline"},
        "selfshot3_world": {"owner": "vproduct", "next": "world", "back": "wardrobe"},
        "selfshot3_effect": {"owner": "vproduct", "next": "effects", "back": "world"},
        "selfshot3_audio": {"owner": "vproduct", "next": "audio", "back": "effects"},
        "selfshot3_review": {"owner": "vproduct", "next": "review", "back": "effects"},
    }


def validate_rows(rows: Iterable[Iterable[tuple[str, str]]], *, back_callback: str) -> dict[str, Any]:
    normalized = [[tuple(button) for button in row] for row in rows]
    errors = []
    callbacks = []
    for index, row in enumerate(normalized):
        if len(row) not in {2, 5}:
            errors.append(f"row_{index + 1}_invalid_width")
        if len(row) == 5 and [str(item[0]).strip("✅ ") for item in row] != ["1", "2", "3", "4", "5"]:
            errors.append(f"row_{index + 1}_invalid_suggestions")
        callbacks.extend(str(item[1]) for item in row)
    if len(callbacks) != len(set(callbacks)):
        errors.append("duplicate_callback")
    expected_tail = [str(back_callback), "menu|main_video"]
    if not normalized or [str(item[1]) for item in normalized[-1]] != expected_tail:
        errors.append("bottom_navigation_invalid")
    return {"ok": not errors, "errors": errors, "callbacks": callbacks}
