import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services import video_ai_real_pricing as canonical


def test_public_music_prices_unblock_startup_knowledge_import():
    prices = canonical.public_music_background_prices()

    assert prices == {"basic": 130, "standard": 150, "premium": 200}

    from services import aas_shared_knowledge

    assert aas_shared_knowledge.MUSIC_BACKGROUND_TIERS == [130, 150, 200]
