import pytest

import bot


@pytest.fixture(autouse=True)
def legacy_dubbing_flow_tests_keep_engine_routes_open(monkeypatch, request):
    """Keep legacy state-machine tests on their original internal routes.

    Production defaults keep the new B12.5 public router gates closed. Tests
    outside the B12.5 gate suite still exercise the voice/combo state machines,
    so they opt into those routes here without enabling public custom voice.
    """
    if request.node.path.name == "test_p0_17b12_5_live_router_gate.py":
        return
    monkeypatch.setattr(bot, "PUBLIC_VOICE_VIDEO_ENABLED", True)
    monkeypatch.setattr(bot, "PUBLIC_SUBTITLE_DUB_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_DUB_PUBLIC_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_SUBTITLE_PLUS_DUB_PUBLIC_ENABLED", True)
