"""Smart-only recovery on speech windows after an unstable whole-vocal view."""
from __future__ import annotations

import numpy as np

from services import subdub_multi_speaker_embedding_onnx as engine
from services import subdub_multi_speaker_gender_onnx as gender
from services import subdub_speaker_cast as cast
from services import subdub_two_speaker_gender_onnx as stereo


def _supported_speech_authority(views: dict, probabilities: list) -> dict:
    base = np.array(views["base_embeddings"], dtype=np.float64, copy=True)
    shifted = np.array(views["shifted_embeddings"], dtype=np.float64, copy=True)
    positions = np.asarray(views["source_positions"], dtype=np.float64)
    speech = np.asarray(views["speech_seconds"], dtype=np.float64)
    probs = np.asarray(probabilities, dtype=np.float64)
    if (base.ndim != 2 or shifted.shape != base.shape or base.shape[1] != engine.EMBEDDING_DIM
            or not engine.MIN_UNITS <= len(base) <= engine.MAX_CLUSTER_UNITS
            or any(a.shape != (len(base),) for a in (positions, speech, probs))
            or not all(np.isfinite(a).all() for a in (base, shifted, positions, speech, probs))
            or np.any(speech <= 0) or np.any((probs < 0) | (probs > 1))):
        raise ValueError("fixed_vocal_smart_speech_view_invalid")
    norms, shifted_norms = np.linalg.norm(base, axis=1), np.linalg.norm(shifted, axis=1)
    if np.any(norms <= 0) or np.any(shifted_norms <= 0):
        raise ValueError("fixed_vocal_smart_speech_view_invalid")
    base /= norms[:, None]
    shifted /= shifted_norms[:, None]
    cosines = np.sum(base * shifted, axis=1)
    reliable = cosines >= engine.MIN_FIXED_VOCAL_VIEW_COSINE
    if reliable.mean() < engine.SPEECH_PARTITION_MIN_AGREEMENT or reliable.sum() < engine.MIN_UNITS:
        raise ValueError("fixed_vocal_smart_speech_view_unstable")
    aggregate = base + shifted
    aggregate_norms = np.linalg.norm(aggregate, axis=1)
    if np.any(aggregate_norms <= 0):
        raise ValueError("fixed_vocal_smart_speech_view_invalid")
    aggregate /= aggregate_norms[:, None]
    # Count all reliable identities before selecting register evidence, never recount a subset.
    partitions = [engine._stable_cluster_view(matrix[reliable], positions[reliable], minimum_speakers=1)
                  for matrix in (base, shifted, aggregate)]
    counts = [int(partition[0]) for partition in partitions]
    if len(set(counts)) != 1:
        raise ValueError("fixed_vocal_smart_speech_count_unstable")
    count = counts[0]
    for _count, labels, _eigenvalues in partitions:
        engine._validate_cluster_support(labels, speech[reliable], count)
        aligned = engine._align_cluster_labels_to_reference(
            partitions[0][1].tolist(), labels.tolist(), speaker_count=count, minimum_speakers=1)
        if np.mean(partitions[0][1] == aligned) < engine.SPEECH_PARTITION_MIN_AGREEMENT:
            raise ValueError("fixed_vocal_smart_speech_partition_unstable")
    threshold = gender.MULTI_GENDER_STRONG_CONFIDENCE
    for label in range(count):
        votes = probs[reliable][partitions[0][1] == label]
        high, low = np.count_nonzero(votes >= threshold), np.count_nonzero(votes <= 1 - threshold)
        if high + low < engine.MIN_CLUSTER_UNITS:
            raise ValueError("fixed_vocal_gender_evidence_invalid")
    supported = reliable & ((probs >= threshold) | (probs <= 1 - threshold))
    authority = engine.build_gender_constrained_speech_authority(
        base[supported], shifted[supported], positions[supported], speech[supported], probs[supported],
        speaker_count=count, minimum_speakers=1,
    )
    if min(authority[k] for k in ("base_shift_agreement", "base_aggregate_agreement", "shift_aggregate_agreement")) < engine.SPEECH_PARTITION_MIN_AGREEMENT:
        raise ValueError("fixed_vocal_smart_speech_partition_unstable")
    centroids = np.stack([aggregate[supported][np.asarray(authority["labels"]) == label].mean(axis=0)
                          for label in range(count)])
    centroids /= np.linalg.norm(centroids, axis=1)[:, None]
    if np.mean(np.argmax(aggregate[supported] @ centroids.T, axis=1) == authority["labels"]) < engine.SPEECH_PARTITION_MIN_AGREEMENT:
        raise ValueError("fixed_vocal_smart_speech_partition_unstable")
    labels = np.argmax(aggregate @ centroids.T, axis=1)
    base_labels, shifted_labels = (np.argmax(matrix @ centroids.T, axis=1) for matrix in (base, shifted))
    if np.mean(base_labels[reliable] == shifted_labels[reliable]) < engine.SPEECH_PARTITION_MIN_AGREEMENT:
        raise ValueError("fixed_vocal_smart_speech_partition_unstable")
    labels[supported] = authority["labels"]
    engine._validate_cluster_support(labels, speech, count)
    authority.update(labels=labels.tolist(), unit_confidences=engine._cluster_unit_confidences(aggregate, labels, count),
                     speaker_count_views=counts, supported_window_recovery=True,
                     unreliable_view_window_count=int((~reliable).sum()),
                     register_ambiguous_window_count=int((reliable & ~supported).sum()))
    return authority


def build_speech_identity_authority(views: dict, probabilities: list) -> dict:
    try:
        base = np.array(views["base_embeddings"], dtype=np.float64, copy=True)
        shifted = np.array(views["shifted_embeddings"], dtype=np.float64, copy=True)
        positions = np.asarray(views["source_positions"], dtype=np.float64)
        speech = np.asarray(views["speech_seconds"], dtype=np.float64)
        if (
            base.ndim != 2 or base.shape != shifted.shape
            or base.shape[1] != engine.EMBEDDING_DIM
            or not engine.MIN_UNITS <= len(base) <= engine.MAX_CLUSTER_UNITS
            or positions.shape != (len(base),) or speech.shape != (len(base),)
            or not all(np.isfinite(a).all() for a in (base, shifted, positions, speech))
            or np.any(speech <= 0)
        ):
            raise ValueError("fixed_vocal_smart_speech_view_invalid")
        norms, shifted_norms = np.linalg.norm(base, axis=1), np.linalg.norm(shifted, axis=1)
        if np.any(norms <= 0) or np.any(shifted_norms <= 0):
            raise ValueError("fixed_vocal_smart_speech_view_invalid")
        base /= norms[:, None]
        shifted /= shifted_norms[:, None]
        if float(np.min(np.sum(base * shifted, axis=1))) < engine.MIN_FIXED_VOCAL_VIEW_COSINE:
            raise ValueError("fixed_vocal_smart_speech_view_unstable")
        aggregate = base + shifted
        aggregate /= np.linalg.norm(aggregate, axis=1)[:, None]
        partitions = [engine._stable_cluster_view(matrix, positions, minimum_speakers=1)
                      for matrix in (base, shifted, aggregate)]
        counts = [int(partition[0]) for partition in partitions]
        if len(set(counts)) != 1 or not 1 <= counts[0] <= engine.MAX_SPEAKERS:
            raise ValueError("fixed_vocal_smart_speech_count_unstable")
        probs = np.asarray(probabilities, dtype=np.float64)
        if probs.shape != (len(base),) or not np.isfinite(probs).all() or np.any((probs < 0) | (probs > 1)):
            raise ValueError("fixed_vocal_smart_speech_view_invalid")
        for label in range(counts[0]):
            selected = probs[np.asarray(partitions[0][1]) == label]
            high = np.count_nonzero(selected >= gender.MULTI_GENDER_STRONG_CONFIDENCE)
            low = np.count_nonzero(selected <= 1 - gender.MULTI_GENDER_STRONG_CONFIDENCE)
            if max(high, low) < engine.MIN_CLUSTER_UNITS or max(high, low) / (high + low) < gender.MIN_VOTE_DOMINANCE:
                raise ValueError("fixed_vocal_gender_evidence_invalid")
        authority = engine.build_gender_constrained_speech_authority(
            base, shifted, positions, speech, probabilities,
            speaker_count=counts[0], minimum_speakers=1, enforce_gender_consistency=False,
        )
        if min(float(authority[key]) for key in (
            "base_shift_agreement", "base_aggregate_agreement", "shift_aggregate_agreement",
        )) < engine.SPEECH_PARTITION_MIN_AGREEMENT:
            raise ValueError("fixed_vocal_smart_speech_partition_unstable")
        # Repair isolated register outliers, not supported opposite-register speech.
        labels = np.asarray(authority["labels"])
        supported_opposite_register = False
        for label, register in enumerate(authority["speaker_registers"]):
            selected = probs[labels == label]
            votes = np.count_nonzero(selected >= gender.MULTI_GENDER_STRONG_CONFIDENCE
                                     if register == "high" else selected <= 1 - gender.MULTI_GENDER_STRONG_CONFIDENCE)
            strong_votes = np.count_nonzero((selected >= gender.MULTI_GENDER_STRONG_CONFIDENCE)
                                           | (selected <= 1 - gender.MULTI_GENDER_STRONG_CONFIDENCE))
            if votes < engine.MIN_CLUSTER_UNITS or votes / strong_votes < gender.MIN_VOTE_DOMINANCE:
                raise ValueError("fixed_vocal_gender_evidence_invalid")
            supported_opposite_register |= strong_votes - votes >= engine.MIN_CLUSTER_UNITS
        if supported_opposite_register:
            authority = engine.build_gender_constrained_speech_authority(
                base, shifted, positions, speech, probabilities,
                speaker_count=counts[0], minimum_speakers=1,
            )
            if min(float(authority[key]) for key in (
                "base_shift_agreement", "base_aggregate_agreement", "shift_aggregate_agreement",
            )) < engine.SPEECH_PARTITION_MIN_AGREEMENT:
                raise ValueError("fixed_vocal_smart_speech_partition_unstable")
        authority["speaker_count_views"] = counts
        return authority
    except Exception as error:
        cause = error
        while cause.__cause__ is not None:
            cause = cause.__cause__
        if str(cause) in {"fixed_vocal_smart_speech_view_unstable", "fixed_vocal_gender_ambiguity_invalid",
                          "fixed_vocal_gender_evidence_invalid"}:
            try:
                return _supported_speech_authority(views, probabilities)
            except Exception as recovery_error:
                recovery_cause = recovery_error
                while recovery_cause.__cause__ is not None:
                    recovery_cause = recovery_cause.__cause__
                if str(recovery_cause) in {"acoustic_cluster_unsupported", "acoustic_cluster_count_out_of_range",
                                          "fixed_vocal_gender_cluster_unsupported"}:
                    raise cast.AutoCastManualRequired() from ValueError("fixed_vocal_smart_speech_partition_unstable")
                raise cast.AutoCastManualRequired() from recovery_error
        if isinstance(error, cast.AutoCastManualRequired):
            raise
        raise cast.AutoCastManualRequired() from error


def recover_speech_identity(
    vocal_pcm: np.ndarray, stereo_pcm_path: str, words: list[dict], *,
    duration_seconds: float, deadline_monotonic: float, stop_requested,
    session_factory=None,
) -> dict:
    engine._embedding_boundary_check(deadline_monotonic=deadline_monotonic, stop_requested=stop_requested)
    source = np.fromfile(stereo_pcm_path, dtype="<i2").reshape(-1, stereo.PCM_CHANNELS)
    mono = source.astype(np.float32).mean(axis=1)
    positions = np.arange(len(vocal_pcm), dtype=np.float64) * stereo.PCM_SAMPLE_RATE / engine.PCM_SAMPLE_RATE
    original = np.clip(np.interp(positions, np.arange(len(mono), dtype=np.float64), mono),
                       -32768, 32767).astype(np.int16)
    views = engine._fixed_vocal_speech_window_views(
        vocal_pcm, words, duration_seconds=duration_seconds,
        deadline_monotonic=deadline_monotonic, stop_requested=stop_requested,
        session_factory=session_factory, gender_pcm16=original,
    )
    probabilities = gender.classify_vocal_window_gender_probabilities(
        views["window_samples"], deadline_monotonic=deadline_monotonic, stop_requested=stop_requested,
    )
    authority = build_speech_identity_authority(views, probabilities)
    count = int(authority["speaker_count"])
    mapped = engine.map_subsegment_clusters_to_regions(views["plan"], authority, minimum_speakers=1)
    units = [{"unit_index": index, "word_indexes": [index], "start": float(word["start"]),
              "end": float(word["end"]), "original_speech_seconds": float(word["end"]) - float(word["start"])}
             for index, word in enumerate(words)]
    segments = engine.build_clustered_segments(words, units, mapped)
    classes = {cast.normalized_speaker_key(0, label): {
        "speaker_id": cast.normalized_speaker_key(0, label),
        "voice_register": authority["speaker_registers"][label],
        "confidence": authority["speaker_register_confidences"][label],
        "reason": "smart_speech_view_recovery",
    } for label in range(count)}
    for segment in segments:
        segment["voice_register"] = classes[segment["speaker_id"]]["voice_register"]
    if len({c["speaker_id"] for c in segments}) != count or len(mapped["labels"]) != len(words):
        raise cast.AutoCastManualRequired() from ValueError("smart_speech_word_coverage_invalid")
    return {"ok": True, "status": "PASS", "provider": engine.FIXED_VOCAL_PROVIDER,
            "segments": segments, "detected_speaker_count": count, "word_count": len(words),
            "word_coverage_count": len(words), "model_sha256": engine.MODEL_SHA256,
            "algorithm_version": engine.FIXED_VOCAL_ALGORITHM_VERSION,
            "smart_acoustic_generic": True, "smart_acoustic_classifications": classes,
            "smart_speech_identity_recovered": True,
            "speaker_count_views": authority["speaker_count_views"],
            "speech_view_cosine_min": authority["view_cosine_min"],
            "speech_view_agreement": min(authority[k] for k in (
                "base_shift_agreement", "base_aggregate_agreement", "shift_aggregate_agreement"))}
