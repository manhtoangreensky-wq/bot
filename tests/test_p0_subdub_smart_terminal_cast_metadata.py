import ast
from pathlib import Path

import pytest

from test_p0_subdub_canonical_receipt_presentation import _receipt_text


def _actual_terminal_unpacks(state, *, outer_wrapper=False):
    source = (Path(__file__).resolve().parents[1] / 'bot.py').read_text(encoding='utf-8-sig')
    marker = source.index('            **subdub_auto_multi_terminal_proof_fields(state),',
                          source.index('async def _execute_video_dubbing_pipeline_core('))
    if outer_wrapper:
        start = source.index('        update_fields = {', source.index('async def execute_video_dubbing_pipeline('))
        end = source.index('\n        }', start) + len('\n        }')
        expression = ast.parse(source[start:end].strip()).body[0].value
    else:
        start = source.rindex('job = save_engine_async_job(', 0, marker)
        end = source.index('\n        internal_job_id =', marker)
        call = ast.parse(source[start:end].strip()).body[0].value
        expression = call.args[0]
    # Execute the production metadata unpacks, not unrelated financial/media fields.
    values = [value for key, value in zip(expression.keys, expression.values)
              if key is None and isinstance(value, ast.Call)
              and isinstance(value.func, ast.Name)
              and value.func.id in {'subdub_auto_multi_terminal_proof_fields', 'subdub_smart_terminal_evidence_fields'}]
    tree = ast.Expression(ast.Dict(keys=[None]*len(values), values=values))
    ns = {'state': state, 'result_state': state, 'subdub_auto_multi_terminal_proof_fields': lambda _s: {}}
    helper_start = source.find('def subdub_smart_terminal_evidence_fields(')
    if helper_start >= 0:
        helper_end = source.index('\ndef ', helper_start+4)
        exec(compile(source[helper_start:helper_end], 'actual_smart_metadata_wrapper', 'exec'), ns)
    return eval(compile(ast.fix_missing_locations(tree), 'actual_terminal_unpacks', 'eval'), ns)


def _state():
    return {'auto_speaker_lane': 'auto_smart_multivoice', 'auto_smart_multivoice_verified': True,
            'auto_detected_speaker_count': 2, 'auto_effective_speaker_count': 2,
            'auto_distinct_voice_count': 2, 'speaker_voice_map': {'s1': 'male', 's2': 'female'},
            'smart_dubbed_voice_count': 1, 'smart_source_audio_cue_ids': ['c2'],
            'smart_source_audio_cue_count': 1, 'smart_source_audio_reasons': {'c2': 'speaker_attribution_uncertain'},
            'charge_status': 'charged', 'auto_exact_actual_total_xu': 123,
            'secret_provider_value': 'not-output'}


@pytest.mark.parametrize('outer_wrapper', [False, True])
def test_generic_cast_survives_real_final_job_and_wrapper_unpacks(outer_wrapper):
    state = _state()
    result = _actual_terminal_unpacks(state, outer_wrapper=outer_wrapper)
    assert result['auto_detected_speaker_count'] == 2
    assert result['speaker_voice_map'] == state['speaker_voice_map']
    assert result['smart_dubbed_voice_count'] == 1
    assert result['smart_source_audio_reasons'] == state['smart_source_audio_reasons']
    assert 'charge_status' not in result and 'auto_exact_actual_total_xu' not in result
    assert 'secret_provider_value' not in result
    assert 'auto_multi_attribution_verified' not in result
    assert 'auto_multi_geometry_verified' not in result
    assert 'Dubbing voices used: <b>1</b>' in _receipt_text(result, 'en')


def test_unproven_source_count_is_not_persisted_as_one_real_speaker():
    state = {**_state(), 'auto_smart_degraded_single_voice': True,
             'auto_detected_speaker_count': 1, 'smart_dubbed_voice_count': 0}
    result = _actual_terminal_unpacks(state)
    assert result['auto_smart_degraded_single_voice'] is True
    assert 'auto_detected_speaker_count' not in result
    assert result['smart_dubbed_voice_count'] == 0


@pytest.mark.parametrize('changes', [
    {'auto_speaker_lane': 'auto_speaker'}, {'auto_smart_multivoice_verified': False},
    {'speaker_voice_map': {'s1': ''}}, {'auto_detected_speaker_count': 9},
    {'auto_distinct_voice_count': 1},
])
def test_invalid_or_legacy_metadata_cannot_claim_verified_cast(changes):
    result = _actual_terminal_unpacks({**_state(), **changes})
    assert 'auto_detected_speaker_count' not in result
    assert 'speaker_voice_map' not in result
