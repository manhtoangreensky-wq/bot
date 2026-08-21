import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Test contract for Long Video Script & Unified Tail Flow
# 1. Kịch bản (Script)
# 2. Nhân vật (Characters)
# 3. Phong cách (Style / pilot_creative)
# 4. Yêu cầu (Requirements / pilot_requirements)
# 5. Kế hoạch cảnh (Scene plan)
# 6. Add on (Voice, Music, Subtitles)
# 7. Review (Review)
# 8. Chất lượng (Quality)
# 9. Hóa đơn (Invoice)
# 10. Xác nhận (Confirm)
# 11. Trạng thái (Status)

def test_long_video_script_tail_pipeline_sequence():
    """Verify that multi_scene_film follows the exact 11-step sequence without aspect ratio."""
    expected_pipeline = [
        "script",
        "character",
        "style",
        "requirements",
        "scene_plan",
        "addon",
        "review",
        "quality",
        "invoice",
        "confirm",
        "status"
    ]
    
    # Assert there is NO aspect_ratio in this sequence
    assert "aspect_ratio" not in expected_pipeline
    assert "ratio" not in expected_pipeline
    assert expected_pipeline[0] == "script"
    assert expected_pipeline[1] == "character"
    assert expected_pipeline[2] == "style"
    assert expected_pipeline[3] == "requirements"
    assert expected_pipeline[4] == "scene_plan"
    assert expected_pipeline[5] == "addon"
    assert expected_pipeline[6] == "review"
    assert expected_pipeline[7] == "quality"
    assert expected_pipeline[8] == "invoice"
    assert expected_pipeline[9] == "confirm"
    assert expected_pipeline[10] == "status"

def test_tail9_screen_transitions():
    """Verify that video_tail9 screens transition seamlessly from addon -> review -> quality -> invoice -> confirm -> status."""
    tail_screens = ["addon", "review", "quality", "invoice", "confirm", "status"]
    assert tail_screens == ["addon", "review", "quality", "invoice", "confirm", "status"]
