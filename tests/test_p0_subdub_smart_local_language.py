import asyncio
import importlib
import math
import subprocess
from types import SimpleNamespace

import pytest

from test_p0_subdub_auto_asr_timeout_boundary import _load_asr_forwarding_surface


def _module():
    return importlib.import_module("services.subdub_smart_language")


@pytest.mark.parametrize("samples,duration,expected", [
    ([('zh', .985), ('zh', .999), ('zh', .997)], 60, 'zh'),
    ([('es', .944), ('es', .932), ('es', .925)], 134, 'es'),
    ([('en', .4), ('zh', .99), ('zh', .99)], 60, 'zh'),
    ([('en', .95), ('zh', .99), ('zh', .99)], 60, 'auto'),
    ([('zh', .6), ('zh', .7), ('zh', .8)], 60, 'auto'),
    ([('xx', .99), ('xx', .99)], 60, 'auto'),
    ([('fr', .99)], 12, 'fr'),
    ([('fr', .95)], 12, 'auto'),
    ([('fr', .99)], 3, 'auto'),
    ([('zh', float('nan')), ('zh', .99)], 60, 'auto'),
    ([('zh', True), ('zh', .99)], 60, 'auto'),
    ([], 60, 'auto'),
])
def test_hint_needs_supported_consistent_confident_samples(samples, duration, expected):
    result = _module().select_language_hint(samples, duration_seconds=duration)
    assert result['language'] == expected
    assert result['status'] == ('confident' if expected != 'auto' else 'auto_fallback')


def test_missing_model_does_not_spawn_child_or_block_job(tmp_path, monkeypatch):
    module = _module()
    monkeypatch.setattr(module, 'MODEL_DIR', tmp_path / 'missing')
    monkeypatch.setattr(module.subprocess, 'run', lambda *_a, **_k: pytest.fail('must not spawn'))
    result = asyncio.run(module.detect_smart_language(b'audio', duration_seconds=60, ffmpeg_path='ffmpeg'))
    assert result['language'] == 'auto'
    assert result['reason'] == 'model_not_ready'


def test_timeout_and_bad_child_result_are_optional_failures(tmp_path, monkeypatch):
    module = _module()
    monkeypatch.setattr(module, 'model_ready', lambda *_a: True)
    monkeypatch.setattr(module, 'MODEL_DIR', tmp_path)
    def timeout(*_a, **_k):
        raise subprocess.TimeoutExpired('probe', 60)
    monkeypatch.setattr(module.subprocess, 'run', timeout)
    result = asyncio.run(module.detect_smart_language(b'audio', duration_seconds=60, ffmpeg_path='ffmpeg'))
    assert result['language'] == 'auto'
    assert result['reason'] == 'probe_timeout'
    monkeypatch.setattr(module.subprocess, 'run', lambda *_a, **_k: SimpleNamespace(stdout='not-json', returncode=0))
    result = asyncio.run(module.detect_smart_language(b'audio', duration_seconds=60, ffmpeg_path='ffmpeg'))
    assert result['language'] == 'auto'


def test_model_readiness_rejects_corruption_and_unsafe_manifest(tmp_path, monkeypatch):
    module = _module()
    monkeypatch.setattr(module, 'MODEL_FILES', {'model.bin': ('123', 3)})
    (tmp_path / 'model.bin').write_bytes(b'bad')
    assert module.model_ready(tmp_path) is False


@pytest.mark.parametrize('lane,confirmed,word_timeline,language,expected_calls', [
    ('auto_smart_multivoice', True, True, 'auto', 1),
    ('auto_speaker', True, True, 'auto', 0),
    ('auto_multi_speaker', True, True, 'auto', 0),
    ('manual', True, False, 'auto', 0),
    ('auto_smart_multivoice', False, True, 'auto', 0),
    ('auto_smart_multivoice', True, True, 'es', 0),
])
def test_only_confirmed_smart_auto_route_probes_local_language(monkeypatch, lane, confirmed, word_timeline, language, expected_calls):
    module = _module()
    calls, requests = [], []
    async def probe(*_a, **_k):
        calls.append('probe')
        return {'language': 'zh', 'status': 'confident', 'reason': 'multi_sample_agreement'}
    monkeypatch.setattr(module, 'detect_smart_language', probe)
    asr, _ = _load_asr_forwarding_surface()
    state = {'auto_speaker_lane': lane}
    ns = asr.__globals__
    ns.update(ASR_PROVIDER='deepgram', get_subdub_active_pipeline_state=lambda: state,
              auto_smart_multivoice=SimpleNamespace(is_auto_smart_multivoice_state=lambda s: s.get('auto_speaker_lane')=='auto_smart_multivoice'),
              frame_video_ffmpeg_path=lambda: 'ffmpeg')
    async def adapter(*_a, **kwargs):
        requests.append(kwargs)
        return {'ok':False, 'status':'deepgram_timeout','transcript':'','transcript_json':{}}
    ns['deepgram_asr_adapter']=adapter
    asyncio.run(asr(b'audio', language=language, allow_confirmed_product=confirmed,
                    require_auto_multi_word_timeline=word_timeline, media_duration_seconds=60))
    assert len(calls)==expected_calls
    if expected_calls:
        assert requests[0]['language']=='zh'
        assert state['subdub_smart_language_probe']['language']=='zh'


def test_optional_probe_exception_keeps_original_auto_asr(monkeypatch):
    module = _module()
    async def broken(*_a, **_k):
        raise RuntimeError('local model unavailable')
    monkeypatch.setattr(module, 'detect_smart_language', broken)
    asr, _ = _load_asr_forwarding_surface()
    state = {'auto_speaker_lane':'auto_smart_multivoice'}
    asr.__globals__.update(get_subdub_active_pipeline_state=lambda: state,
        auto_smart_multivoice=SimpleNamespace(is_auto_smart_multivoice_state=lambda s: True),
        frame_video_ffmpeg_path=lambda:'ffmpeg')
    result=asyncio.run(asr(b'audio', allow_confirmed_product=True, require_auto_multi_word_timeline=True))
    assert result['status']=='deepgram_timeout'
