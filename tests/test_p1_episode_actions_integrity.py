import unittest
from services import video_uiflow3, video_tail9, video_script_product

class TestFilm12StepsIntegrity(unittest.TestCase):
    def test_episode_actions_and_views_coverage(self):
        """Verify all film actions and views exist in bot.py."""
        with open("bot.py", "r", encoding="utf-8") as f:
            content = f.read()

        # Check View Owners
        for v in ["episode_goal", "episode_audience", "episode_platform", "episode_duration", "episode_script"]:
            self.assertIn(f'"{v}": "episode"', content)
            self.assertIn(f'"{v}": {{"episode"}}', content)

        # Check Action Arities
        for a in ["film_goal", "film_aud", "film_plat", "film_dur", "film_ep_num"]:
            self.assertIn(f'"{a}"', content)
        for a in ["film_script_generate", "film_script_regen", "film_script_edit", "film_script_use"]:
            self.assertIn(f'"{a}"', content)

        # Check Pending Steps
        for p in ["film_goal_custom", "film_aud_custom", "film_plat_custom", "film_dur_custom", "film_script_edit"]:
            self.assertIn(f'"{p}": {{"episode"}}', content)

    def test_film_12_steps_flow(self):
        """Verify state progression through all 12 steps for multi_scene_film."""
        # Step 1: Entry
        state = video_uiflow3.new_state("multi_scene_film")
        state["navigation"]["current_step"] = "content_hub"
        state["ui_view"] = "profiles"
        state["content"]["profile_page"] = 1
        self.assertEqual(state["parent_product"], "multi_scene_film")

        # Step 2: 5 Suggestions
        profile_key = "film_drama_series"
        state["content"]["profile_id"] = profile_key
        suggestions = video_script_product.profile_content_suggestions(profile_key, revision=0)
        self.assertGreaterEqual(len(suggestions), 5)

        # Step 3: Select Suggestion -> Bible
        item = suggestions[0]
        state = video_uiflow3.set_content_candidate(
            state,
            source="content_catalog",
            profile_id=profile_key,
            original_intent=str(item.get("brief") or item.get("title") or ""),
            approved_brief={"title": str(item.get("title") or "")},
        )
        state = video_uiflow3.lock_content(state)
        state["navigation"]["current_step"] = "production_bible"
        state = video_uiflow3.set_character_count(state, 1)
        state = video_uiflow3.set_location_count(state, 1)
        char_id = state["bible"]["characters"][0]["character_id"]
        loc_id = state["bible"]["locations"][0]["location_id"]
        state = video_uiflow3.update_character(state, char_id, display_name="Diễn viên chính", description="Nam luật sư")
        state = video_uiflow3.update_location(state, loc_id, name="Tòa án", description="Trang nghiêm")
        state = video_uiflow3.mark_sections_complete(state, "production_bible")

        # Step 4: Creative Controls
        state["pilot_flow"] = {"creative_done": True}

        # Step 5: Requirements
        state["pilot_flow"]["requirements_done"] = True

        # Step 6: Goal
        state["navigation"]["current_step"] = "episode"
        state["ui_view"] = "episode_goal"
        state["episode"] = {"goal": "story", "goal_label": "Kể chuyện / Cảm xúc"}

        # Step 7: Audience
        state["ui_view"] = "episode_audience"
        state["episode"]["audience"] = "prospects"
        state["episode"]["audience_label"] = "Khách tiềm năng"

        # Step 8: Platform
        state["ui_view"] = "episode_platform"
        state["episode"]["platform"] = "tiktok_reels"
        state["episode"]["platform_label"] = "TikTok / Reels"

        # Step 9: Duration & Number
        state["ui_view"] = "episode_duration"
        state["episode"]["number"] = 1
        state["episode"]["duration"] = 60

        # Step 10: Script Generation
        state["ui_view"] = "episode_script"
        state["episode"]["script_text"] = "Timeline script"

        # Step 11: Script Use -> Direct Addon
        brief_text = str((state.get("content") or {}).get("original_intent") or "Phim dài tập").strip()
        state["series"]["goal"] = brief_text
        state = video_uiflow3.set_episode_identity(state, number=1, title="Tập 1")
        state = video_uiflow3.set_episode_content(state, original_intent=brief_text)
        state = video_uiflow3.lock_episode_content(state)

        state["format"]["scene_count"] = 5
        state["format"]["scene_count_confirmed"] = True
        state["format"]["duration_seconds"] = 60
        state = video_uiflow3.confirm_scene_count(state, 5)
        state = video_uiflow3.suggest_scene_plan(state)
        state = video_uiflow3.auto_assign_scenes(state)
        state = video_uiflow3.mark_sections_complete(
            state,
            "series_goal", "episode", "scene_count", "scene_plan", "scene_assignment", "prompts", "branding", "summary"
        )
        snapshot = video_uiflow3.approved_snapshot(state)
        self.assertIsNotNone(snapshot)

        # Step 12: Contract Execution
        contract = video_tail9.commercial_contract("multi_scene_film")
        self.assertTrue(contract.get("execution_enabled"))

if __name__ == "__main__":
    unittest.main()
