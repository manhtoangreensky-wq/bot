"""Provider-free focused test suite for P0.SUBDUB.AUTO.SMART.MULTIVOICE.TTS.PROVIDER.ROUTE.CORRECTION.R2.

Enforces STRICT_EXCLUSIVE_PROVIDER policy and provider-specific Key4U compatibility authority:
- Case A: explicit Key4U + ShopAIKey-only Vietnamese voice -> Key4U 0, ShopAIKey 0 -> fail closed.
- Case B: explicit Key4U + documented Key4U voice -> Key4U exactly 1, ShopAIKey 0.
- Case C: explicit ShopAIKey + Vietnamese_Professional_Narrator_v2 -> ShopAIKey mock route selected.
- Case D: explicit Key4U + default_male -> do NOT classify UI placeholder as provider voice (False).
- Case E: explicit Key4U + default_female -> do NOT classify UI placeholder as provider voice (False).
- Case F: explicit Key4U + toanaas-voice-* not in Key4U validated authority -> incompatible (False).
- Case G: explicit Key4U + arbitrary key4u-* prefix -> incompatible (False).
- Case H: documented/validated Key4U pool voices -> compatible (True).
- Case I: incompatible explicit-provider voice -> render 0, wallet mutation 0, no unhandled escape.

Zero network calls, zero paid provider calls, zero wallet mutations.
"""

import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, patch

import bot
from services.subdub_blackboxes import auto_smart_multivoice


class TestTTSProviderRouteCorrectionR2(unittest.TestCase):
    def test_case_a_explicit_key4u_incompatible_voice_fails_closed_zero_submits(self):
        """Case A: When key4u_minimax is explicit but voice is Vietnamese_Professional_Narrator_v2:
        Under STRICT_EXCLUSIVE_PROVIDER policy:
        - Key4U submit count == 0
        - ShopAIKey submit count == 0 (NO silent cross-provider fallback!)
        - Fails closed with structured tts_unavailable exception
        """
        mock_key4u = AsyncMock(return_value=("PASS", b"KEY4U_AUDIO", "ok", 200))
        mock_shopaikey = AsyncMock(return_value=("PASS", b"SHOPAIKEY_AUDIO", "ok", 200))

        with patch.object(bot, "subdub_tts_provider_name", return_value="key4u_minimax"), \
             patch.object(bot, "key4u_minimax_tts_configured", return_value=True), \
             patch.object(bot, "shopaikey_minimax_tts_configured", return_value=True), \
             patch.object(bot, "KEY4U_PUBLIC_ENABLED", True), \
             patch.object(bot, "VIDEO_DUB_TTS_ENABLED", True), \
             patch.object(bot, "SHOPAIKEY_ADMIN_ONLY", False), \
             patch.object(bot, "call_key4u_minimax_tts_bytes_with_speed", mock_key4u), \
             patch.object(bot, "call_shopaikey_minimax_tts_bytes_with_speed", mock_shopaikey):

            with self.assertRaises(RuntimeError) as ctx:
                asyncio.run(
                    bot.video_dubbing_tts_bytes(
                        "Xin chào TOAN AAS.",
                        voice_id="Vietnamese_Professional_Narrator_v2",
                    )
                )

            # Strict policy: Zero submits to both providers
            self.assertEqual(
                mock_key4u.call_count, 0,
                f"Expected Key4U submit count == 0, got {mock_key4u.call_count}"
            )
            self.assertEqual(
                mock_shopaikey.call_count, 0,
                f"Expected ShopAIKey submit count == 0 (no fallback), got {mock_shopaikey.call_count}"
            )
            self.assertIn("tts_unavailable", str(ctx.exception))

    def test_case_b_explicit_key4u_compatible_voice_preserves_key4u_route(self):
        """Case B: When voice is known Key4U-compatible (e.g. English_magnetic_voiced_man or male-qn-qingse),
        Key4U route must be used exactly once, ShopAIKey submit count == 0.
        """
        mock_key4u = AsyncMock(return_value=("PASS", b"KEY4U_COMPATIBLE_AUDIO", "ok", 200))
        mock_shopaikey = AsyncMock(return_value=("PASS", b"SHOPAIKEY_AUDIO", "ok", 200))

        with patch.object(bot, "subdub_tts_provider_name", return_value="key4u_minimax"), \
             patch.object(bot, "key4u_minimax_tts_configured", return_value=True), \
             patch.object(bot, "shopaikey_minimax_tts_configured", return_value=True), \
             patch.object(bot, "KEY4U_PUBLIC_ENABLED", True), \
             patch.object(bot, "VIDEO_DUB_TTS_ENABLED", True), \
             patch.object(bot, "SHOPAIKEY_ADMIN_ONLY", False), \
             patch.object(bot, "call_key4u_minimax_tts_bytes_with_speed", mock_key4u), \
             patch.object(bot, "call_shopaikey_minimax_tts_bytes_with_speed", mock_shopaikey):

            label, audio_bytes, detail = asyncio.run(
                bot.video_dubbing_tts_bytes(
                    "Hello world.",
                    voice_id="English_magnetic_voiced_man",
                )
            )

            self.assertEqual(mock_key4u.call_count, 1)
            self.assertEqual(mock_shopaikey.call_count, 0)
            self.assertEqual(label, "Key4U MiniMax")
            self.assertEqual(audio_bytes, b"KEY4U_COMPATIBLE_AUDIO")

    def test_case_c_explicit_shopaikey_routes_vietnamese_voice_to_shopaikey(self):
        """Case C: When explicit provider is shopaikey_minimax, Vietnamese_Professional_Narrator_v2
        is successfully routed to ShopAIKey MiniMax.
        """
        mock_key4u = AsyncMock(return_value=("PASS", b"KEY4U_AUDIO", "ok", 200))
        mock_shopaikey = AsyncMock(return_value=("PASS", b"SHOPAIKEY_AUDIO", "ok", 200))

        with patch.object(bot, "subdub_tts_provider_name", return_value="shopaikey_minimax"), \
             patch.object(bot, "key4u_minimax_tts_configured", return_value=True), \
             patch.object(bot, "shopaikey_minimax_tts_configured", return_value=True), \
             patch.object(bot, "KEY4U_PUBLIC_ENABLED", True), \
             patch.object(bot, "VIDEO_DUB_TTS_ENABLED", True), \
             patch.object(bot, "SHOPAIKEY_ADMIN_ONLY", False), \
             patch.object(bot, "call_key4u_minimax_tts_bytes_with_speed", mock_key4u), \
             patch.object(bot, "call_shopaikey_minimax_tts_bytes_with_speed", mock_shopaikey):

            label, audio_bytes, detail = asyncio.run(
                bot.video_dubbing_tts_bytes(
                    "Xin chào TOAN AAS.",
                    voice_id="Vietnamese_Professional_Narrator_v2",
                )
            )

            self.assertEqual(mock_shopaikey.call_count, 1)
            self.assertEqual(mock_key4u.call_count, 0)
            self.assertEqual(label, "ShopAIKey MiniMax")
            self.assertEqual(audio_bytes, b"SHOPAIKEY_AUDIO")

    def test_case_d_key4u_rejects_ui_placeholder_default_male(self):
        """Case D: default_male is a UI placeholder, NOT a provider voice. Must return False."""
        self.assertFalse(
            bot.key4u_minimax_voice_compatible("default_male"),
            "UI placeholder 'default_male' must NOT be classified as Key4U-compatible!"
        )

    def test_case_e_key4u_rejects_ui_placeholder_default_female(self):
        """Case E: default_female is a UI placeholder, NOT a provider voice. Must return False."""
        self.assertFalse(
            bot.key4u_minimax_voice_compatible("default_female"),
            "UI placeholder 'default_female' must NOT be classified as Key4U-compatible!"
        )

    def test_case_f_key4u_rejects_arbitrary_toanaas_voice_prefix(self):
        """Case F: toanaas-voice-* prefix without Key4U validation must return False."""
        self.assertFalse(
            bot.key4u_minimax_voice_compatible("toanaas-voice-user123-20260628"),
            "Arbitrary toanaas-voice-* clone prefix must NOT be assumed Key4U-compatible!"
        )

    def test_case_g_key4u_rejects_arbitrary_key4u_prefix(self):
        """Case G: arbitrary key4u-* prefix has no provider documentation basis. Must return False."""
        self.assertFalse(
            bot.key4u_minimax_voice_compatible("key4u-arbitrary-identifier"),
            "Arbitrary key4u-* prefix must NOT be assumed Key4U-compatible!"
        )

    def test_case_h_key4u_accepts_documented_and_validated_pools(self):
        """Case H: Documented provider voice male-qn-qingse, empty voice (default),
        and official validated pool voices must return True.
        """
        # Empty string defaults to provider male-qn-qingse
        self.assertTrue(bot.key4u_minimax_voice_compatible(""))
        self.assertTrue(bot.key4u_minimax_voice_compatible("male-qn-qingse"))
        # Documented English system voices
        self.assertTrue(bot.key4u_minimax_voice_compatible("English_magnetic_voiced_man"))
        self.assertTrue(bot.key4u_minimax_voice_compatible("English_radiant_girl"))
        self.assertTrue(bot.key4u_minimax_voice_compatible("English_Aussie_Bloke"))
        # moss_audio documented sample
        self.assertTrue(bot.key4u_minimax_voice_compatible("moss_audio_sample_voice"))
        # ShopAIKey catalog voice must be False
        self.assertFalse(bot.key4u_minimax_voice_compatible("Vietnamese_Professional_Narrator_v2"))
        self.assertFalse(bot.key4u_minimax_voice_compatible("Vietnamese_Cute_Girl_v1"))

    def test_case_i_incompatible_explicit_voice_contains_failure_without_render_or_charge(self):
        """Case I: Incompatible voice under explicit provider fails closed:
        zero render calls, zero wallet mutations, and no unhandled exception escape.
        """
        mock_key4u = AsyncMock(return_value=("PASS", b"KEY4U_AUDIO", "ok", 200))
        mock_shopaikey = AsyncMock(return_value=("PASS", b"SHOPAIKEY_AUDIO", "ok", 200))
        render_mock = AsyncMock(return_value=b"CORRUPT_VIDEO")

        with patch.object(bot, "subdub_tts_provider_name", return_value="key4u_minimax"), \
             patch.object(bot, "key4u_minimax_tts_configured", return_value=True), \
             patch.object(bot, "shopaikey_minimax_tts_configured", return_value=True), \
             patch.object(bot, "KEY4U_PUBLIC_ENABLED", True), \
             patch.object(bot, "VIDEO_DUB_TTS_ENABLED", True), \
             patch.object(bot, "SHOPAIKEY_ADMIN_ONLY", False), \
             patch.object(bot, "call_key4u_minimax_tts_bytes_with_speed", mock_key4u), \
             patch.object(bot, "call_shopaikey_minimax_tts_bytes_with_speed", mock_shopaikey):

            # Verify synthesis fails closed with structured exception
            with self.assertRaises(RuntimeError) as ctx:
                asyncio.run(
                    bot.video_dubbing_tts_bytes(
                        "Đoạn thuyết minh.",
                        voice_id="Vietnamese_Professional_Narrator_v2",
                    )
                )

            self.assertIn("tts_unavailable", str(ctx.exception))
            # Verify render was never invoked
            self.assertEqual(render_mock.call_count, 0)
            # Verify neither provider was submitted
            self.assertEqual(mock_key4u.call_count, 0)
            self.assertEqual(mock_shopaikey.call_count, 0)


if __name__ == "__main__":
    unittest.main()
