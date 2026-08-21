import asyncio
import re
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).parents[1]
BOT_PATH = ROOT / "bot.py"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.subdub_blackboxes import auto_speaker


def _load_bot_pool_contract():
    source = BOT_PATH.read_text(encoding="utf-8")
    start = source.index("SUBDUB_AUTO_DOCUMENTED_LOW_VOICE_IDS = (")
    end = source.index("SUBDUB_AUTO_EXACT_RECEIPT_VERSION", start)
    namespace = {
        "minimax_voice_adapter": SimpleNamespace(
            validate_provider_voice_id=lambda value: bool(
                re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}", str(value or ""))
            )
        )
    }
    exec(compile(source[start:end], str(BOT_PATH), "exec"), namespace)
    return namespace


def _load_route_contract(provider: str):
    source = BOT_PATH.read_text(encoding="utf-8")
    namespace = _load_bot_pool_contract()
    namespace.update(
        {
            "SUBDUB_AUTO_SPEAKER_ACTIVATION_ENABLED": True,
            "subdub_speaker_cast": SimpleNamespace(MAX_AUTO_SPEAKER_LABELS=16),
            "subdub_tts_provider_name": lambda: provider,
            "auto_speaker": SimpleNamespace(
                is_auto_speaker_state=lambda state: bool(
                    isinstance(state, dict)
                    and state.get("voice_kind") == "auto_speaker_gender"
                    and state.get("voice_selection_mode") == "auto_speaker"
                )
            ),
        }
    )
    start = source.index("def subdub_auto_speaker_route_enabled(")
    end = source.index("SUBDUB_MANUAL_VOICE_FIELDS", start)
    exec(compile(source[start:end], str(BOT_PATH), "exec"), namespace)
    return namespace


class AutoProviderVoicePoolContractTests(unittest.TestCase):
    def test_official_minimax_pools_are_only_enabled_for_proven_routes(self):
        contract = _load_bot_pool_contract()
        resolve = contract["subdub_auto_validated_voice_pools"]
        expected = {
            "low": list(contract["SUBDUB_AUTO_DOCUMENTED_LOW_VOICE_IDS"]),
            "high": list(contract["SUBDUB_AUTO_DOCUMENTED_HIGH_VOICE_IDS"]),
        }

        self.assertEqual(resolve("key4u_minimax"), expected)
        self.assertEqual(resolve("direct_minimax"), expected)
        self.assertEqual(len(set(expected["low"])), 16)
        self.assertEqual(len(set(expected["high"])), 16)

        empty = {"low": [], "high": []}
        for provider in ("shopaikey_minimax", "auto", "", None, "unknown"):
            with self.subTest(provider=provider):
                self.assertEqual(resolve(provider), empty)

    def test_bot_passes_the_explicit_selected_provider_to_auto_pool_resolution(self):
        source = BOT_PATH.read_text(encoding="utf-8")
        marker = "validated_pools=subdub_auto_validated_voice_pools(subdub_tts_provider_name())"
        self.assertTrue(
            marker in source,
            "Auto blackbox must resolve its static pool from the explicit selected provider",
        )
        self.assertIn(
            "required_pool_capacity=subdub_speaker_cast.MAX_AUTO_SPEAKER_LABELS",
            source,
        )
        self.assertNotIn("load_shopaikey_minimax_voice_catalog(", source[source.index("def subdub_auto_validated_voice_pools"):source.index("SUBDUB_AUTO_EXACT_RECEIPT_VERSION")])

    def test_route_and_customer_voice_ui_require_a_full_proven_provider_pool(self):
        auto_state = {
            "voice_kind": "auto_speaker_gender",
            "voice_selection_mode": "auto_speaker",
        }
        for provider in ("shopaikey_minimax", "auto", "", "unknown"):
            with self.subTest(provider=provider):
                contract = _load_route_contract(provider)
                self.assertFalse(contract["subdub_auto_provider_capacity_ready"]())
                self.assertFalse(contract["subdub_auto_speaker_route_enabled"](auto_state))

        for provider in ("key4u_minimax", "direct_minimax"):
            with self.subTest(provider=provider):
                contract = _load_route_contract(provider)
                self.assertTrue(contract["subdub_auto_provider_capacity_ready"]())
                self.assertTrue(contract["subdub_auto_speaker_route_enabled"](auto_state))

        source = BOT_PATH.read_text(encoding="utf-8")
        self.assertEqual(
            source.count("if include_auto and subdub_auto_provider_capacity_ready():"),
            4,
        )
        self.assertIn(
            "subdub_auto_provider_capacity_ready()\n"
            "        if activation_enabled is None",
            source,
        )

    def test_unverified_pool_fails_before_prepare_or_tts(self):
        invalid_pools = (
            {"low": [], "high": []},
            {
                "low": [f"low-{index}" for index in range(15)],
                "high": [f"high-{index}" for index in range(16)],
            },
            {
                "low": [f"voice-{index}" for index in range(16)],
                "high": ["voice-0", *[f"high-{index}" for index in range(15)]],
            },
        )
        for validated_pools in invalid_pools:
            with self.subTest(validated_pools=validated_pools):
                calls = {"prepare": 0, "tts": 0, "lane": 0}

                async def prepare(*_args, **_kwargs):
                    calls["prepare"] += 1
                    raise AssertionError("unverified provider must fail before subtitle preparation")

                async def synthesize(*_args, **_kwargs):
                    calls["tts"] += 1
                    raise AssertionError("unverified provider must fail before TTS")

                async def lane(*_args, **_kwargs):
                    calls["lane"] += 1
                    raise AssertionError("unverified provider must not enter the protected lane")

                result = asyncio.run(
                    auto_speaker.run_auto_speaker_blackbox(
                        lane_mode="dub",
                        run_lane_blackbox=lane,
                        runner=lambda *_args, **_kwargs: None,
                        prepare_subtitles=prepare,
                        resolve_voice_id=lambda *_args, **_kwargs: "",
                        synthesize_segments=synthesize,
                        post_prepare_gate=lambda *_args, **_kwargs: True,
                        extract_pcm=lambda *_args, **_kwargs: None,
                        validated_pools=validated_pools,
                        required_pool_capacity=16,
                        state={
                            "mode": "dub",
                            "voice_kind": "auto_speaker_gender",
                            "voice_selection_mode": "auto_speaker",
                        },
                    )
                )

                self.assertFalse(result["ok"])
                self.assertEqual(result["status"], "AUTO_CAST_MANUAL_REQUIRED")
                self.assertEqual(calls, {"prepare": 0, "tts": 0, "lane": 0})


if __name__ == "__main__":
    unittest.main()
