"""Provider-free architecture image prompt planning.

The architecture studio prepares a draft only.  Destination image/video
flows remain responsible for pricing, confirmation and generation.
"""

from __future__ import annotations

import re
from typing import Any


EXTERIOR_PROJECT_TYPES = (
    "Nhà phố", "Biệt thự", "Nhà cấp 4", "Căn hộ / chung cư",
    "Tòa nhà văn phòng", "Khách sạn / resort", "Quán cà phê / nhà hàng",
    "Cửa hàng / showroom", "Nhà xưởng", "Trường học",
    "Công trình công cộng", "Khu nghỉ dưỡng", "Homestay",
    "Cảnh quan sân vườn",
)

INTERIOR_SPACE_TYPES = (
    "Phòng khách", "Phòng ngủ", "Phòng bếp", "Phòng ăn",
    "Phòng làm việc", "Phòng trẻ em", "Phòng tắm", "Ban công", "Sảnh",
    "Văn phòng", "Cửa hàng", "Showroom", "Quán cà phê", "Nhà hàng",
    "Spa / salon", "Khách sạn", "Căn hộ studio", "Không gian đa chức năng",
)

RENOVATION_SCOPES = (
    "Giữ nguyên toàn bộ hình học", "Giữ tường/cửa/cửa sổ", "Giữ sàn",
    "Giữ trần", "Giữ đồ nội thất đã chọn", "Thay toàn bộ nội thất",
    "Chỉ đổi màu/vật liệu", "Chỉ cải thiện ánh sáng", "Cải tạo nhẹ",
    "Cải tạo toàn diện",
)

PRESERVATION_CONTROLS = (
    "Giữ nguyên hình học", "Giữ nguyên tường/cột", "Giữ nguyên cửa/cửa sổ",
    "Giữ nguyên trần", "Giữ nguyên sàn", "Giữ nguyên cầu thang",
    "Giữ nguyên vị trí bếp", "Giữ nguyên thiết bị vệ sinh",
    "Giữ nguyên đồ nội thất đã chọn", "Cho phép thay đổi bố cục",
    "Cho phép cải tạo toàn diện",
)

IMAGE_NEGATIVE_PROMPT = (
    "altered room dimensions", "extra doors or windows", "missing columns",
    "warped walls", "floating furniture", "oversized furniture",
    "duplicated objects", "impossible reflections", "deformed stairs",
    "fake text", "watermark", "logo corruption", "fisheye distortion",
    "extreme wide-angle distortion", "low resolution", "oversharpening",
    "excessive HDR", "inconsistent shadows", "invented dimensions",
    "invented address", "invented amenities", "misleading room scale",
)


def _style(
    forms: str,
    materials: str,
    palette: str,
    lighting: str,
    furniture: str,
    exterior: str,
    incompatible: tuple[str, ...],
    vocabulary: str,
    negative: str,
) -> dict[str, Any]:
    return {
        "key_forms": forms,
        "dominant_materials": materials,
        "palette": palette,
        "lighting": lighting,
        "furniture_characteristics": furniture,
        "exterior_characteristics": exterior,
        "unsuitable_combinations": list(incompatible),
        "prompt_vocabulary": vocabulary,
        "negative_constraints": negative,
    }


ARCHITECTURAL_STYLES: dict[str, dict[str, Any]] = {
    "Hiện đại": _style("clean orthogonal volumes", "glass, timber, stone, metal", "neutral with one restrained accent", "layered daylight", "simple functional pieces", "clear massing and shaded glazing", ("Cổ điển",), "modern, rational, refined", "no ornamental overload"),
    "Tối giản": _style("quiet planes and negative space", "plaster, pale timber, stone", "white, warm grey, muted natural", "soft indirect light", "few precise pieces", "simple monolithic facade", ("Art Deco", "Cổ điển"), "minimal, calm, uncluttered", "no visual clutter"),
    "Scandinavian": _style("light practical forms", "light oak, wool, linen", "white, pale wood, soft grey", "bright diffuse daylight", "comfortable practical furniture", "simple pitched or clean facade", ("Luxury",), "Nordic warmth, functional simplicity", "no dark heavy ornament"),
    "Japandi": _style("low calm proportions", "light oak, linen, clay, stone", "warm off-white, taupe, muted earth", "soft natural daylight", "low handcrafted pieces", "restrained openings and natural textures", ("Art Deco",), "Japandi, warm minimal, tactile", "no glossy excess"),
    "Wabi-sabi": _style("asymmetric quiet forms", "aged timber, lime plaster, raw stone", "earth, charcoal, warm beige", "gentle directional light", "handmade imperfect pieces", "weathered natural expression", ("Futuristic",), "patina, imperfect beauty, quiet", "no polished synthetic finish"),
    "Indochine": _style("colonial proportions with local motifs", "dark timber, rattan, patterned tile", "cream, deep green, dark wood", "warm filtered daylight", "carved timber and woven details", "shutters, arches, shaded verandas", ("Futuristic",), "Indochine, tropical colonial elegance", "no unrelated European excess"),
    "Đông Dương hiện đại": _style("clean forms with Indochine accents", "timber, rattan, terrazzo, brass", "warm ivory, green, wood", "layered warm daylight", "modern pieces with woven accents", "modern facade with shaded tropical details", ("Brutalist",), "modern Indochine, restrained heritage", "no motif overload"),
    "Tân cổ điển": _style("balanced symmetry and restrained mouldings", "stone, timber, brass, plaster", "ivory, warm grey, muted gold", "soft layered chandelier light", "elegant proportional furniture", "symmetrical facade and measured detailing", ("Industrial",), "neoclassical, refined symmetry", "no excessive gilding"),
    "Cổ điển": _style("formal symmetry and layered ornament", "marble, carved timber, plaster", "cream, burgundy, antique gold", "warm dramatic lighting", "ornate traditional pieces", "columns, cornices and formal composition", ("Tối giản", "Industrial"), "classical grandeur, formal order", "no modern casual clutter"),
    "Luxury": _style("generous polished composition", "marble, veneer, brass, glass", "warm neutral with rich accents", "layered premium lighting", "tailored statement furniture", "premium material rhythm", ("Rustic",), "luxury, bespoke, sophisticated", "no cheap glossy surfaces"),
    "Contemporary": _style("current fluid geometry", "glass, timber, microcement", "soft neutral and curated accents", "dynamic natural and ambient light", "sculptural current furniture", "expressive but buildable facade", (), "contemporary, curated, current", "no trend clutter"),
    "Industrial": _style("open structure and honest grids", "exposed brick, steel, concrete", "charcoal, rust, warm timber", "track lighting and large windows", "robust metal and leather pieces", "exposed structure and large bays", ("Cổ điển",), "industrial loft, raw honest materials", "no ornate classical trim"),
    "Tropical": _style("open shaded forms", "timber, stone, rattan, greenery", "lush green, sand, warm wood", "filtered daylight", "breathable natural furniture", "deep eaves and cross ventilation", ("Futuristic",), "tropical, shaded, bioclimatic", "no sealed sterile atmosphere"),
    "Mediterranean": _style("arches and thick textured planes", "lime plaster, terracotta, stone", "white, sand, terracotta, sea blue", "sunlit warm contrast", "relaxed crafted furniture", "courtyards, arches, tiled roofs", ("Brutalist",), "Mediterranean, sun-washed, tactile", "no cold metallic dominance"),
    "Rustic": _style("solid familiar forms", "reclaimed timber, stone, linen", "earth, brown, cream", "warm fireplace-like light", "substantial handcrafted pieces", "natural stone and timber expression", ("Futuristic", "Luxury"), "rustic, authentic, handcrafted", "no glossy futuristic finish"),
    "Farmhouse": _style("simple domestic proportions", "painted timber, oak, stone", "white, sage, warm wood", "bright homely daylight", "comfortable traditional utility pieces", "porches and simple gables", ("Parametric",), "farmhouse, welcoming, practical", "no urban high-gloss styling"),
    "Art Deco": _style("bold symmetry and stepped geometry", "brass, velvet, lacquer, marble", "black, emerald, cream, gold", "dramatic layered glow", "geometric statement pieces", "stepped lines and decorative symmetry", ("Tối giản", "Wabi-sabi"), "Art Deco, geometric glamour", "no random mixed motifs"),
    "Mid-century modern": _style("low horizontal clean forms", "teak, walnut, glass, brick", "mustard, olive, walnut, cream", "warm daylight", "tapered legs and iconic silhouettes", "horizontal glazing and indoor-outdoor flow", ("Cổ điển",), "mid-century modern, optimistic, functional", "no ornate revival details"),
    "Organic modern": _style("soft curves and balanced voids", "oak, travertine, plaster, linen", "warm stone, cream, wood", "soft sculpting daylight", "rounded tactile furniture", "calm curved massing", ("Industrial",), "organic modern, soft, tactile", "no harsh mechanical clutter"),
    "Biophilic": _style("forms organized around nature", "timber, stone, planting, water", "natural greens and earth", "daylight-led lighting", "natural tactile pieces", "green layers and climate response", (), "biophilic, nature-integrated, restorative", "no token plastic greenery"),
    "Zen": _style("balanced low quiet composition", "timber, stone, paper, gravel", "warm neutral, charcoal, moss", "calm diffused light", "minimal low furniture", "courtyard and framed nature", ("Art Deco",), "Zen, contemplative, balanced", "no decorative noise"),
    "Futuristic": _style("fluid advanced geometry", "glass, composite, brushed metal", "white, graphite, controlled neon", "integrated luminous surfaces", "seamless adaptive furniture", "aerodynamic buildable envelope", ("Wabi-sabi", "Rustic"), "futuristic, seamless, advanced", "no impossible unsupported structure"),
    "Parametric": _style("rule-based repeated geometry", "engineered timber, metal, concrete", "material-led neutral", "light emphasizing pattern", "custom integrated elements", "rational computational skin", ("Farmhouse",), "parametric, patterned, computational", "no arbitrary unbuildable curves"),
    "Brutalist": _style("bold monolithic masses", "board-formed concrete, steel, glass", "concrete grey, charcoal, warm accent", "strong directional light", "solid minimal furniture", "expressed mass and deep openings", ("Indochine", "Mediterranean"), "Brutalist, monumental, honest", "no delicate ornamental trim"),
    "Minimal luxury": _style("precise calm proportions", "travertine, oak, bronze, plaster", "warm ivory, taupe, bronze", "concealed layered light", "few bespoke premium pieces", "quiet premium material composition", ("Rustic",), "minimal luxury, restrained premium", "no ostentatious decoration"),
    "Modern Vietnamese": _style("contemporary tropical proportions", "local timber, terrazzo, brick, stone", "warm neutral, terracotta, green", "shaded tropical daylight", "modern local craft pieces", "screens, courtyards, deep shading", (), "modern Vietnamese, climate-responsive", "no copied heritage ornament"),
    "Resort style": _style("open relaxing indoor-outdoor forms", "stone, timber, linen, planting", "sand, cream, aqua, green", "golden soft daylight", "relaxed premium furniture", "pavilions, water and landscape integration", ("Industrial",), "resort, serene, immersive", "no cramped urban clutter"),
}


STYLE_ALIASES = {
    "hien dai": "Hiện đại", "modern": "Hiện đại", "toi gian": "Tối giản",
    "minimal": "Tối giản", "dong duong": "Indochine", "tan co dien": "Tân cổ điển",
    "co dien": "Cổ điển", "sang trong": "Luxury", "contemporary": "Contemporary",
    "cong nghiep": "Industrial", "nhiet doi": "Tropical", "wabi sabi": "Wabi-sabi",
    "modern vietnamese": "Modern Vietnamese", "resort": "Resort style",
}


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _text_list(value: Any) -> list[str]:
    if value is None:
        return []
    values = value if isinstance(value, (list, tuple, set)) else [value]
    return [_clean(item) for item in values if _clean(item)]


def normalize_style_names(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        values = list(value)
    else:
        values = re.split(r"\s*(?:,|\+|/| và )\s*", _clean(value)) if _clean(value) else []
    normalized: list[str] = []
    for raw in values:
        item = _clean(raw)
        if item in ARCHITECTURAL_STYLES:
            canonical = item
        else:
            key = item.lower()
            canonical = STYLE_ALIASES.get(key, item)
        if canonical in ARCHITECTURAL_STYLES and canonical not in normalized:
            normalized.append(canonical)
    return normalized


def conflicting_styles(styles: Any, *, explicit_fusion: bool = False) -> list[tuple[str, str]]:
    if explicit_fusion:
        return []
    selected = normalize_style_names(styles)
    conflicts: list[tuple[str, str]] = []
    for left in selected:
        incompatible = set(ARCHITECTURAL_STYLES[left]["unsuitable_combinations"])
        for right in selected:
            if left != right and (right in incompatible or left in set(ARCHITECTURAL_STYLES[right]["unsuitable_combinations"])):
                pair = tuple(sorted((left, right)))
                if pair not in conflicts:
                    conflicts.append(pair)
    return conflicts


def default_preservation(profile_id: str, has_reference: bool = False) -> list[str]:
    profile = _clean(profile_id)
    if profile == "floorplan_visualization":
        return ["Giữ nguyên kích thước và bố trí mặt bằng", "Không tự thêm phòng", "Không tự bỏ tường kết cấu"]
    if profile == "real_estate_property":
        return ["Giữ đúng hình học và quy mô thật", "Giữ số phòng và vị trí cửa", "Không bịa góc nhìn hoặc tiện ích"]
    if profile == "space_renovation" or has_reference:
        return ["Giữ nguyên hình học", "Giữ nguyên cửa/cửa sổ", "Giữ nguyên góc máy", "Giữ nguyên kết cấu"]
    return ["Giữ đúng ràng buộc khách hàng đã nêu"]


def build_architecture_image_prompt(payload: dict[str, Any]) -> dict[str, Any]:
    profile_id = _clean(payload.get("profile_id") or "interior_design")
    project = _clean(payload.get("project_type") or payload.get("space_type") or "dự án kiến trúc")
    existing = _clean(payload.get("existing_condition") or "the supplied existing condition")
    objective = _clean(payload.get("user_text") or payload.get("design_objective") or "prepare a coherent architectural concept")
    styles = normalize_style_names(payload.get("style")) or ["Hiện đại"]
    conflicts = conflicting_styles(styles, explicit_fusion=bool(payload.get("explicit_style_fusion")))
    if conflicts:
        names = " và ".join(conflicts[0])
        return {
            "ok": False,
            "clarification_question": f"Hai phong cách {names} có nhiều điểm đối lập. Anh/chị muốn chọn một phong cách hay chủ động phối hợp cả hai?",
            "prompt": "",
            "negative_prompt": ", ".join(IMAGE_NEGATIVE_PROMPT),
            "sections": {},
        }
    style_details = [ARCHITECTURAL_STYLES[name] for name in styles]
    preservation = _text_list(payload.get("preserve_requirements"))
    if not preservation:
        preservation = default_preservation(profile_id, bool(payload.get("reference_assets")))
    materials = _text_list(payload.get("materials"))
    if not materials:
        materials = [style_details[0]["dominant_materials"]]
    palettes = _text_list(payload.get("color_palette") or payload.get("palette"))
    if not palettes:
        palettes = [style_details[0]["palette"]]
    lighting = _clean(payload.get("lighting") or style_details[0]["lighting"])
    aspect_ratio = _clean(payload.get("aspect_ratio") or "16:9")
    camera = _clean(payload.get("camera") or "balanced architectural wide-angle lens without distortion")
    furniture = _clean(payload.get("furniture_fixtures") or style_details[0]["furniture_characteristics"])
    sections = {
        "project_space": project,
        "existing_condition": existing,
        "design_objective": objective,
        "architectural_style": ", ".join(styles),
        "geometry_preservation": "; ".join(preservation),
        "layout": _clean(payload.get("layout") or "clear circulation and plausible functional zoning"),
        "materials": "; ".join(materials),
        "color_palette": "; ".join(palettes),
        "furniture_fixtures": furniture,
        "lighting": lighting,
        "camera_lens": camera,
        "composition": _clean(payload.get("composition") or "balanced professional architectural composition"),
        "realism": "physically plausible structure, proportions and material response",
        "render_quality": "photorealistic architectural visualization with natural detail",
        "aspect_ratio": aspect_ratio,
        "negative_prompt": ", ".join(IMAGE_NEGATIVE_PROMPT),
    }
    prompt = (
        f"Architectural project: {project}. Existing condition: {existing}. Design objective: {objective}. "
        f"Style: {sections['architectural_style']} ({'; '.join(item['prompt_vocabulary'] for item in style_details)}). "
        f"Preserve exactly: {sections['geometry_preservation']}. Layout: {sections['layout']}. "
        f"Materials: {sections['materials']}. Palette: {sections['color_palette']}. "
        f"Furniture and fixtures: {furniture}. Lighting: {lighting}. Camera: {camera}. "
        f"Composition: {sections['composition']}. {sections['realism']}. {sections['render_quality']}. "
        f"Aspect ratio {aspect_ratio}. Do not invent dimensions, addresses, regulations, ownership, legal status, views or amenities."
    )
    return {
        "ok": True,
        "clarification_question": "",
        "prompt": _clean(prompt),
        "negative_prompt": sections["negative_prompt"],
        "sections": sections,
        "styles": styles,
        "preserve_constraints": preservation,
        "provider_called": False,
        "xu_charged": 0,
    }
