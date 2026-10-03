"""Bounded Smart cast metadata, separate from strict attribution/geometry proof."""
from collections.abc import Mapping


def bounded_smart_terminal_evidence(state: Mapping | None) -> dict:
    from services.subdub_blackboxes.auto_smart_multivoice import is_auto_smart_multivoice_state

    if not isinstance(state, Mapping) or not is_auto_smart_multivoice_state(state):
        return {}
    result = {'auto_speaker_lane': 'auto_smart_multivoice'}
    for key in ('auto_smart_multivoice_verified', 'auto_smart_degraded_single_voice'):
        if type(state.get(key)) is bool:
            result[key] = state[key]
    for key in ('auto_smart_strategy', 'auto_smart_fallback_reason', 'auto_smart_degraded_reason'):
        value = state.get(key)
        if type(value) is str and len(value) <= 160:
            result[key] = value
    voice_map = state.get('speaker_voice_map')
    counts = [state.get(key) for key in (
        'auto_detected_speaker_count', 'auto_effective_speaker_count', 'auto_distinct_voice_count')]
    if (state.get('auto_smart_multivoice_verified') is True
            and state.get('auto_smart_degraded_single_voice') is not True
            and type(voice_map) is dict and 1 <= len(voice_map) <= 8
            and all(type(k) is str and 0 < len(k) <= 160 and type(v) is str
                    and 0 < len(v) <= 160 and v.strip() == v for k, v in voice_map.items())
            and all(type(n) is int and 1 <= n <= 8 for n in counts)
            and counts[0] == counts[1] == len(voice_map)
            and counts[2] == len(set(voice_map.values()))):
        result.update({key: state[key] for key in (
            'auto_detected_speaker_count', 'auto_effective_speaker_count', 'auto_distinct_voice_count')})
        result['speaker_voice_map'] = dict(voice_map)
    played = state.get('smart_dubbed_voice_count')
    if type(played) is int and 0 <= played <= 8:
        result['smart_dubbed_voice_count'] = played
    cue_ids, reasons, count = (state.get(key) for key in (
        'smart_source_audio_cue_ids', 'smart_source_audio_reasons', 'smart_source_audio_cue_count'))
    if (type(cue_ids) is list and len(cue_ids) <= 2048
            and all(type(cid) is str and 0 < len(cid) <= 160 for cid in cue_ids)
            and len(set(cue_ids)) == len(cue_ids) and type(count) is int and count == len(cue_ids)
            and type(reasons) is dict and set(reasons) == set(cue_ids)
            and all(type(reason) is str and reason in {'natural_audio_exceeds_window', 'translation_missing',
                               'speaker_attribution_uncertain'} for reason in reasons.values())):
        result.update(smart_source_audio_cue_ids=list(cue_ids), smart_source_audio_reasons=dict(reasons),
                      smart_source_audio_cue_count=count)
    return result
