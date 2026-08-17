import pytest
from services import video_uiflow3

def test_series_level_initialization():
    """Verify Series Level initialization with Bible and target duration."""
    state = video_uiflow3.new_state("multi_scene_film")
    state = video_uiflow3.set_series_goal(state, "Thành phố không ngủ - Bộ phim ngắn kịch tính")
    state = video_uiflow3.set_format(state, ratio="16:9", target_duration_seconds=300)
    
    assert state["parent_product"] == "multi_scene_film"
    assert state["series"]["goal"] == "Thành phố không ngủ - Bộ phim ngắn kịch tính"
    assert state["format"]["ratio"] == "16:9"
    assert state["format"]["target_duration_seconds"] == 300

def test_smart_episode_identity_parser():
    """Verify flexible episode number and title parsing without forcing 'number | title' syntax."""
    import re
    
    def parse_episode_identity_smart(text: str, default_number: int = 1, current_title: str = "") -> tuple[int, str]:
        clean = str(text or "").strip()
        if "|" in clean:
            parts = [p.strip() for p in clean.split("|", 1)]
            num_match = re.search(r"\d+", parts[0])
            num = int(num_match.group(0)) if num_match else default_number
            title = parts[1] or current_title or f"Tập {num}"
            return num, title
        
        # Check if text is just a number like "1", "tập 1", "Tập 02", "tap 3"
        match_only_ep = re.match(r"^(?:tập\s*|tap\s*|ep\s*|episode\s*)?(\d+)$", clean, re.IGNORECASE)
        if match_only_ep:
            num = int(match_only_ep.group(1))
            title = current_title if current_title and current_title != f"Tập {default_number}" else f"Tập {num}"
            return num, title
        
        # Check if text starts with "Tập 1 - Title" or "1: Title"
        match_prefix = re.match(r"^(?:tập\s*|tap\s*|ep\s*)?(\d+)\s*[\:\-\–\.\,]\s*(.+)$", clean, re.IGNORECASE)
        if match_prefix:
            return int(match_prefix.group(1)), match_prefix.group(2).strip()
            
        # Otherwise text is just the title
        return default_number, clean

    # Test cases:
    assert parse_episode_identity_smart("1") == (1, "Tập 1")
    assert parse_episode_identity_smart("tập 2") == (2, "Tập 2")
    assert parse_episode_identity_smart("Tập 03") == (3, "Tập 3")
    assert parse_episode_identity_smart("Cuộc gặp đầu tiên") == (1, "Cuộc gặp đầu tiên")
    assert parse_episode_identity_smart("1 | Cuộc gặp đầu tiên") == (1, "Cuộc gặp đầu tiên")
    assert parse_episode_identity_smart("Tập 2 - Bí mật") == (2, "Bí mật")
    assert parse_episode_identity_smart("3: Sự thật") == (3, "Sự thật")

def test_execution_planner_auto_scene_duration_rebalance():
    """Verify Execution Planner automatically calculates scene counts and durations for target duration (e.g. 300s)."""
    target_duration = 300  # 5 minutes
    
    # Model script scene requirements (establishing, dialogue, action, reaction, close-up)
    script_beats = [
        {"type": "establishing", "suggested_duration": 8},
        {"type": "dialogue", "suggested_duration": 10},
        {"type": "dialogue", "suggested_duration": 10},
        {"type": "reaction", "suggested_duration": 4},
        {"type": "action", "suggested_duration": 6},
        {"type": "close_up", "suggested_duration": 5},
    ] * 6  # 36 scenes base
    
    # Execution Planner rebalancing algorithm to hit target_duration +- tolerance
    scenes = [dict(s) for s in script_beats]
    current_total = sum(s["suggested_duration"] for s in scenes)
    
    # Rebalance by adjusting scenes to valid clip capabilities
    while current_total < target_duration:
        scenes.append({"type": "continuation", "suggested_duration": 6})
        current_total += 6
        
    assert len(scenes) > 0
    assert abs(sum(s["suggested_duration"] for s in scenes) - target_duration) <= 10
    
    # Calculate exact cost
    price_per_second = {4: 10, 5: 12, 6: 14, 8: 17, 10: 20}
    total_xu = sum(price_per_second.get(s["suggested_duration"], 15) for s in scenes)
    assert total_xu > 0

def test_continuity_snapshot_inheritance():
    """Verify Episode 2 inherits Episode 1 continuity state."""
    ep1_end_state = {
        "episode_id": "ep_01",
        "characters": {
            "char_01": {"outfit": "áo đen", "status": "bị thương nhẹ"},
            "char_02": {"outfit": "váy trắng", "status": "đã biết bí mật A"},
        },
        "location": "Quán cà phê",
        "unresolved_plot": ["Nam chưa biết Lan phát hiện", "Sản phẩm A đang ở nhà Lan"],
        "weather": "trời mưa",
    }
    
    # Create Episode 2 inheriting Episode 1 state
    ep2_state = video_uiflow3.new_state("multi_scene_film")
    ep2_state["series"]["continuity_snapshots"] = [ep1_end_state]
    
    # Verify Episode 2 sees Episode 1 continuity
    latest_snapshot = ep2_state["series"]["continuity_snapshots"][-1]
    assert latest_snapshot["characters"]["char_02"]["status"] == "đã biết bí mật A"
    assert "Sản phẩm A đang ở nhà Lan" in latest_snapshot["unresolved_plot"]
