"""Provider-free prompt selection for embedded Video idea-catalog flows."""

from __future__ import annotations

from copy import deepcopy


SUPPORTED_PARENT_PRODUCTS = frozenset({
    "video_ai_real",
    "video_trend",
    "script_image_video",
    "storyboard_prompt",
    "self_shot_scene_change",
    "self_shot_cinematic_transform",
    "multi_scene_film",
    "video_reference",
    "motion_prompt",
})

MANDATORY_PROMPT_PRODUCTS = frozenset({"storyboard_prompt"})
SKIPPABLE_PROMPT_PRODUCTS = SUPPORTED_PARENT_PRODUCTS - MANDATORY_PROMPT_PRODUCTS

_VARIATIONS = (
    ("Mạch kể rõ và liền cảnh", "camera chuyển động có động cơ, nhịp kể tự nhiên, kết cảnh trọn ý"),
    ("Điện ảnh giàu cảm xúc", "bố cục điện ảnh, ánh sáng có chủ đích, chuyển tiếp mềm giữa trạng thái"),
    ("Chân thật và gần gũi", "chuyển động đời thường, vật liệu chân thật, camera ổn định và dễ tin"),
    ("Nhịp mạng xã hội", "hook rõ, tiết tấu gọn, điểm nhấn thị giác nhưng không cắt cụt hành động"),
    ("Cao cấp và tối giản", "khung hình sạch, chuyển động tiết chế, chủ thể nổi bật và kết thúc tinh tế"),
    ("Kể chuyện theo hành động", "mỗi cảnh hoàn tất một hành động rồi truyền trạng thái sang cảnh sau"),
    ("Tập trung sản phẩm", "chi tiết sản phẩm chính xác, lợi ích dễ thấy, không thêm chữ hoặc logo giả"),
    ("Tập trung nhân vật", "giữ khuôn mặt, vóc dáng, trang phục và hướng chuyển động nhất quán"),
    ("Không gian có chiều sâu", "bối cảnh nhiều lớp, camera có tiền cảnh và hậu cảnh, ánh sáng đồng nhất"),
    ("Chuyển tiếp theo chuyển động", "nối hướng nhìn và hướng chuyển động, tránh đổi vị trí vô lý"),
    ("Tài liệu hiện đại", "hình ảnh rõ, thông tin chính xác, nhịp giải thích dễ theo dõi"),
    ("Quảng cáo có bằng chứng", "mở bằng vấn đề, thể hiện giải pháp, kết bằng kết quả nhìn thấy được"),
    ("Trước và sau", "giữ cùng chủ thể và góc nhận diện để thay đổi trước-sau có sức thuyết phục"),
    ("Một cú máy mềm", "camera tiếp nối tự nhiên, biến đổi có giai đoạn, không nhảy sang clip không liên quan"),
    ("Nhịp chậm có chủ đích", "cho hành động đủ thời gian bắt đầu, phát triển và kết thúc tự nhiên"),
    ("Năng động có kiểm soát", "camera linh hoạt nhưng chủ thể vẫn rõ, không rung giật hoặc chuyển cảnh vô cớ"),
    ("Ánh sáng dẫn chuyện", "thay đổi ánh sáng theo diễn biến nhưng giữ màu nhận diện nhất quán"),
    ("Chi tiết giàu cảm giác", "cận cảnh vật liệu và thao tác, âm thanh hình dung rõ, không nhồi nhiều ý"),
    ("Mở mạnh, kết đáng nhớ", "hook trực tiếp, mạch giữa có nguyên nhân-kết quả, khung cuối khép ý"),
    ("Cân bằng toàn bộ", "chủ thể, bối cảnh, camera, ánh sáng và nhịp phối hợp trong cùng một mạch"),
)


def _bounded_int(value, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _clean(value, limit: int = 4000) -> str:
    return " ".join(str(value or "").split()).strip()[:limit]


def _scene_content(state: dict) -> list[dict]:
    rows = []
    for fallback_index, item in enumerate(state.get("scene_drafts") or [], 1):
        if not isinstance(item, dict):
            continue
        content = _clean(
            item.get("content")
            or item.get("main_action")
            or item.get("goal")
            or item.get("idea"),
            1600,
        )
        if not content:
            continue
        rows.append({
            "scene_index": _bounded_int(item.get("scene_index"), fallback_index, 1, 20),
            "content": content,
        })
    return rows[:20]


def hydrate_parent_state(state: dict, handoff: dict) -> dict:
    """Persist the complete return contract without sharing sessions across products."""

    updated = deepcopy(dict(state or {}))
    parent = deepcopy(dict(handoff or {}))
    product = _clean(
        updated.get("idea_parent_product")
        or parent.get("idea_parent_product")
        or parent.get("origin_product"),
        80,
    )
    if product not in SUPPORTED_PARENT_PRODUCTS:
        raise ValueError("unsupported_idea_parent_product")

    session_id = _clean(
        updated.get("idea_parent_session_id")
        or parent.get("idea_parent_session_id")
        or parent.get("session_id"),
        160,
    )
    revision = _bounded_int(
        updated.get("idea_parent_revision")
        or parent.get("idea_parent_revision")
        or parent.get("revision"),
        1,
        1,
        1_000_000,
    )
    parent_flow = _clean(
        updated.get("idea_parent_flow")
        or parent.get("idea_parent_flow")
        or parent.get("idea_source_flow")
        or parent.get("source_flow")
        or product,
        160,
    )
    return_step = _clean(
        updated.get("idea_return_step")
        or parent.get("idea_return_step")
        or parent.get("return_step"),
        160,
    )
    scene_count = _bounded_int(
        updated.get("scene_count") or parent.get("scene_count"),
        1,
        1,
        20,
    )
    ratio = _clean(
        updated.get("ratio")
        or updated.get("recommended_aspect_ratio")
        or parent.get("ratio")
        or parent.get("aspect_ratio")
        or "9:16",
        20,
    )
    trend_source = deepcopy(dict(updated.get("trend_source") or parent.get("trend_source") or {}))
    trend_id = _clean(
        updated.get("trend_id")
        or parent.get("trend_id")
        or trend_source.get("trend_id")
        or trend_source.get("id")
        or trend_source.get("title"),
        200,
    )
    source_video_id = _clean(
        updated.get("source_video_id")
        or parent.get("source_video_id"),
        500,
    )
    storyboard_session_id = _clean(
        updated.get("storyboard_session_id")
        or parent.get("storyboard_session_id"),
        160,
    )
    scene_content = _scene_content(updated)

    updated.update({
        "idea_parent_product": product,
        "idea_parent_flow": parent_flow,
        "idea_parent_session_id": session_id,
        "idea_parent_revision": revision,
        "idea_return_step": return_step,
        "idea_preset_id": _bounded_int(updated.get("idea_preset_id"), 0, 0, 2_147_483_647),
        "idea_content": _clean(
            updated.get("idea_content")
            or (updated.get("idea_preset") or {}).get("description")
            or updated.get("subject"),
            8000,
        ),
        "idea_scene_content": scene_content,
        "scene_count": scene_count,
        "ratio": ratio,
        "recommended_aspect_ratio": ratio,
        "trend_source": trend_source,
        "trend_id": trend_id,
        "source_video_id": source_video_id,
        "storyboard_session_id": storyboard_session_id,
        "idea_session_key": f"{product}:{session_id or 'missing'}:{revision}",
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
    return updated


def _continuity_text(state: dict) -> str:
    product = state.get("idea_parent_product")
    if product == "self_shot_scene_change":
        return "Giữ đúng người/vật và video nguồn; cảnh mới chỉ thay đổi không gian quanh chủ thể."
    if product == "self_shot_cinematic_transform":
        return "Giữ khuôn mặt, vóc dáng và chuyển động nguồn; biến đổi trang phục, thế giới và hiệu ứng theo từng giai đoạn trong cùng cú máy."
    if product == "storyboard_prompt":
        return "Mỗi cảnh có ảnh đầu bắt buộc; chuyển động phải xuất phát từ ảnh Storyboard và kết cảnh tự nhiên."
    if product == "multi_scene_film":
        return "Giữ nhân vật, thế giới và tuyến truyện xuyên suốt các chương dài; mỗi chương khép một nhịp rõ."
    return "Giữ nhân vật, sản phẩm, bối cảnh, màu sắc và trạng thái cuối-cảnh đầu-cảnh nhất quán."


def build_prompt_candidates(state: dict, *, offset: int = 0) -> list[dict]:
    """Build five of twenty deterministic prompt options without any provider call."""

    source = deepcopy(dict(state or {}))
    product = _clean(source.get("idea_parent_product"), 80)
    if product not in SUPPORTED_PARENT_PRODUCTS:
        raise ValueError("unsupported_idea_parent_product")
    scenes = list(source.get("idea_scene_content") or _scene_content(source))
    scene_count = _bounded_int(source.get("scene_count"), len(scenes) or 1, 1, 20)
    ratio = _clean(source.get("ratio") or source.get("recommended_aspect_ratio") or "9:16", 20)
    preset = dict(source.get("idea_preset") or {})
    subject = _clean(source.get("subject") or preset.get("title") or source.get("idea_content") or "Ý tưởng video", 500)
    profile = _clean(
        preset.get("recommended_profile_id")
        or preset.get("profile")
        or preset.get("visual_plan")
        or source.get("primary_profile")
        or "phù hợp nội dung",
        500,
    )
    trend = _clean(
        (source.get("trend_source") or {}).get("title")
        or (source.get("trend_source") or {}).get("summary")
        or source.get("trend_id"),
        500,
    )
    continuity = _continuity_text(source)
    start = _bounded_int(offset, 0, 0, len(_VARIATIONS) - 1)
    candidates = []
    for button_index in range(5):
        variation_index = (start + button_index) % len(_VARIATIONS)
        title, direction = _VARIATIONS[variation_index]
        scene_prompts = []
        for scene_index in range(1, scene_count + 1):
            row = scenes[scene_index - 1] if scene_index <= len(scenes) else {}
            content = _clean(row.get("content") or f"Nhịp nội dung {scene_index} của {subject}", 1600)
            previous_state = "Mở từ trạng thái đầu rõ ràng" if scene_index == 1 else "Tiếp nhận đúng trạng thái kết cảnh trước"
            next_state = "Khép toàn bộ video" if scene_index == scene_count else "Kết hành động tự nhiên và để lại trạng thái nối cảnh sau"
            scene_prompts.append(
                f"Cảnh {scene_index}/{scene_count}: {content}. {previous_state}; phát triển đúng một ý hoặc hành động trọn vẹn; "
                f"{next_state}. Hướng thể hiện: {direction}. Tỉ lệ {ratio}. {continuity}"
            )
        context_parts = [
            f"Sản phẩm: {product}",
            f"Ý tưởng: {subject}",
            f"Profile/phong cách: {profile}",
            f"Số cảnh: {scene_count}",
            f"Tỉ lệ: {ratio}",
        ]
        if trend:
            context_parts.append(f"Ngữ cảnh trend phải giữ: {trend}")
        if source.get("source_video_id"):
            context_parts.append("Dùng đúng video nguồn đã gắn trong phiên; không thay bằng video khác")
        full_prompt = ". ".join(context_parts) + ". " + continuity + "\n\n" + "\n".join(scene_prompts)
        candidates.append({
            "button_index": button_index + 1,
            "variant_index": variation_index + 1,
            "title": title,
            "summary": direction,
            "prompt": full_prompt,
            "scene_prompts": scene_prompts,
            "negative_prompt": (
                "Không đổi nhận diện, không đổi sản phẩm hoặc trang phục vô lý, không cắt giữa câu nói hay hành động, "
                "không thêm logo/chữ giả, không nhồi nhiều ý trong một cảnh, không làm mất continuity."
            ),
        })
    return candidates


def prepare_prompt_selection(state: dict, handoff: dict) -> dict:
    updated = hydrate_parent_state(state, handoff)
    updated["idea_prompt_offset"] = 0
    updated["idea_prompt_candidates"] = build_prompt_candidates(updated, offset=0)
    updated["idea_selected_prompt"] = ""
    updated["idea_selected_prompt_record"] = {}
    updated["idea_prompt_skipped"] = False
    return updated


def refresh_prompt_candidates(state: dict) -> dict:
    updated = deepcopy(dict(state or {}))
    offset = (_bounded_int(updated.get("idea_prompt_offset"), 0, 0, 19) + 5) % 20
    updated["idea_prompt_offset"] = offset
    updated["idea_prompt_candidates"] = build_prompt_candidates(updated, offset=offset)
    return updated


def select_prompt(state: dict, button_index: int) -> dict:
    updated = deepcopy(dict(state or {}))
    candidates = [dict(item) for item in updated.get("idea_prompt_candidates") or [] if isinstance(item, dict)]
    index = _bounded_int(button_index, 0, 0, 5)
    if index < 1 or index > len(candidates):
        raise ValueError("idea_prompt_candidate_not_found")
    selected = candidates[index - 1]
    updated["idea_selected_prompt"] = _clean(selected.get("prompt"), 20000)
    updated["idea_selected_prompt_record"] = selected
    updated["idea_prompt_skipped"] = False
    return updated


def set_custom_prompt(state: dict, prompt: str) -> dict:
    value = str(prompt or "").strip()[:20000]
    if not value:
        raise ValueError("idea_prompt_empty")
    updated = deepcopy(dict(state or {}))
    updated["idea_selected_prompt"] = value
    updated["idea_selected_prompt_record"] = {
        "button_index": 0,
        "variant_index": 0,
        "title": "Prompt đã sửa",
        "summary": "Nội dung do khách hàng chỉnh trong phiên hiện tại.",
        "prompt": value,
        "scene_prompts": [],
        "negative_prompt": "",
    }
    updated["idea_prompt_skipped"] = False
    return updated


def skip_prompt(state: dict) -> dict:
    product = _clean((state or {}).get("idea_parent_product"), 80)
    if product in MANDATORY_PROMPT_PRODUCTS:
        raise ValueError("storyboard_prompt_required")
    if product not in SKIPPABLE_PROMPT_PRODUCTS:
        raise ValueError("idea_prompt_skip_not_supported")
    updated = deepcopy(dict(state or {}))
    candidates = [dict(item) for item in updated.get("idea_prompt_candidates") or [] if isinstance(item, dict)]
    if not candidates:
        candidates = build_prompt_candidates(updated, offset=0)
        updated["idea_prompt_candidates"] = candidates
    selected = candidates[0]
    updated["idea_selected_prompt"] = _clean(selected.get("prompt"), 20000)
    updated["idea_selected_prompt_record"] = selected
    updated["idea_prompt_skipped"] = True
    return updated


def validate_return_state(state: dict) -> dict:
    source = dict(state or {})
    required = {
        "idea_parent_product": _clean(source.get("idea_parent_product"), 80),
        "idea_parent_flow": _clean(source.get("idea_parent_flow"), 160),
        "idea_parent_session_id": _clean(source.get("idea_parent_session_id"), 160),
        "idea_return_step": _clean(source.get("idea_return_step"), 160),
        "idea_preset_id": _bounded_int(source.get("idea_preset_id"), 0, 0, 2_147_483_647),
        "idea_content": _clean(source.get("idea_content"), 8000),
        "idea_scene_content": list(source.get("idea_scene_content") or []),
        "idea_selected_prompt": str(source.get("idea_selected_prompt") or "").strip(),
        "scene_count": _bounded_int(source.get("scene_count"), 0, 0, 20),
        "ratio": _clean(source.get("ratio"), 20),
    }
    missing = [key for key, value in required.items() if not value]
    return {"ok": not missing, "missing": missing, "required": required}


def safety_report(state: dict) -> dict:
    source = dict(state or {})
    return {
        "job": int(bool(source.get("job_created"))),
        "outbox": int(bool(source.get("outbox_created"))),
        "provider_calls": int(bool(source.get("provider_called"))),
        "image_provider_calls": int(bool(source.get("image_provider_called"))),
        "generated_files": int(source.get("files_generated") or 0),
        "wallet_mutations": int(source.get("wallet_mutations") or 0),
        "xu_charged": int(source.get("xu_charged") or 0),
    }
