"""Smart-only recovery on speech windows after an unstable whole-vocal view."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from services import subdub_multi_speaker_embedding_onnx as engine
from services import subdub_multi_speaker_gender_onnx as gender
from services import subdub_speaker_cast as cast
from services import subdub_two_speaker_gender_onnx as stereo


def _source_gender_consensus(evidence: dict) -> dict | None:
    try:
        full, windows = evidence["full"], evidence["windows"]
        if not windows or len(windows) + 1 > gender.MAX_CUES_PER_SPEAKER:
            return None
        rows = [full, *windows]
        for row in rows:
            scores = np.asarray([row["male_score"], row["female_score"]], dtype=np.float64)
            if (not np.isfinite(scores).all() or np.any(scores < 0)
                    or scores.sum() <= 0 or scores[0] == scores[1]):
                return None
        male, female = float(full["male_score"]), float(full["female_score"])
        if abs(male - female) / (male + female) < gender.MIN_PANN_SCORE_MARGIN:
            return None
        classification, _rows = gender._aggregate_one_gender_result("source_run", rows)
        register = "low" if male > female else "high"
        dominance = max(classification["male_votes"], classification["female_votes"]) / len(rows)
        if classification["voice_register"] != register or dominance < stereo.MIN_VOTE_DOMINANCE:
            return None
        # Preserve a strongly supported opposite voice rather than smoothing a real turn.
        for row in windows:
            male, female = float(row["male_score"]), float(row["female_score"])
            opposite = female if register == "low" else male
            if opposite / (male + female) >= gender.MULTI_GENDER_STRONG_CONFIDENCE:
                return None
        return classification
    except (KeyError, TypeError, ValueError, cast.AutoCastManualRequired):
        return None


def _apply_source_gender_evidence(authority: dict, views: dict, evidence: dict) -> dict:
    labels = np.asarray(authority["labels"], dtype=np.int64).copy()
    registers = list(authority["speaker_registers"])
    count = int(authority["speaker_count"])
    windows = views["plan"]["windows"]
    verified = {run: classification for run, item in evidence.items()
                if (classification := _source_gender_consensus(item)) is not None}
    result = dict(authority)
    register_confidences = list(authority["speaker_register_confidences"])
    # A consistently evidenced person changes register, not identity or speaker count.
    for label in range(count):
        members = [window for window in windows if labels[window["window_index"]] == label]
        votes = [verified[window["run_index"]] for window in members if window["run_index"] in verified]
        if (len(votes) < stereo.MIN_CLASSIFIED_CUES_PER_SPEAKER
                or len(votes) / len(members) < engine.SPEECH_PARTITION_MIN_AGREEMENT):
            continue
        values = [vote["voice_register"] for vote in votes]
        register = max(set(values), key=values.count)
        if values.count(register) / len(values) >= engine.SPEECH_PARTITION_MIN_AGREEMENT:
            if registers[label] != register:
                registers[label] = register
                register_confidences[label] = min(vote["confidence"] for vote in votes if vote["voice_register"] == register)
    if count > 1:
        base = np.asarray(views["base_embeddings"], dtype=np.float64)
        shifted = np.asarray(views["shifted_embeddings"], dtype=np.float64)
        aggregate = base + shifted
        centroids = np.stack([aggregate[labels == label].mean(axis=0) for label in range(count)])
        norms = np.linalg.norm(centroids, axis=1)
        if not np.isfinite(norms).all() or np.any(norms <= 0):
            return result
        centroids /= norms[:, None]
        for window in windows:
            index = int(window["window_index"])
            classification = verified.get(window["run_index"])
            if not classification or registers[labels[index]] == classification["voice_register"]:
                continue
            eligible = [label for label, register in enumerate(registers)
                        if register == classification["voice_register"]]
            if not eligible:
                continue
            base_label = eligible[int(np.argmax(base[index] @ centroids[eligible].T))]
            shift_label = eligible[int(np.argmax(shifted[index] @ centroids[eligible].T))]
            if base_label == shift_label:
                labels[index] = base_label
        try:
            engine._validate_cluster_support(labels, np.asarray(views["speech_seconds"]), count)
        except (ValueError, cast.AutoCastManualRequired):
            return result
    result.update(labels=labels.tolist(), speaker_registers=registers, speaker_register_confidences=register_confidences,
                  source_gender_verified_run_count=len(verified),
                  source_gender_corrected_window_count=int(np.count_nonzero(labels != np.asarray(authority["labels"]))),
                  source_gender_register_corrected=registers != list(authority["speaker_registers"]))
    return result


def _pann_source_run_evidence(vocal: np.ndarray, plan: dict, *, stereo_pcm_path: str,
                              deadline_monotonic, stop_requested) -> dict:
    if not stereo._CLASSIFIER_LOCK.acquire(blocking=False):
        return {}
    evidence = {}
    try:
        import onnxruntime as ort
        stereo._ensure_active(deadline_monotonic, stop_requested)
        model_paths = stereo._validated_model_paths()
        regions, bounds = {}, {}
        source_regions = {}
        for region in plan["regions"]:
            start, end = (int(round(float(region[key]) * engine.PCM_SAMPLE_RATE)) for key in ("start", "end"))
            if not 0 <= start < end <= len(vocal):
                return {}
            regions[region["index"]] = vocal[start:end]
            bounds[region["index"]] = (start, end)
            source_regions[region["index"]] = region
        source_scores, batch, batch_seconds = {}, {}, 0.0
        for run in plan["runs"]:
            run_windows = [w for w in plan["windows"] if w["run_index"] == run["run_index"]]
            if len(run_windows) + 1 > gender.MAX_CUES_PER_SPEAKER:
                continue
            items = [source_regions[index] for index in run["region_indexes"]]
            start, end = min(item["start"] for item in items), max(item["end"] for item in items)
            if end - start > stereo.MAX_JOB_EVIDENCE_SECONDS:
                continue
            if batch and batch_seconds + end - start > stereo.MAX_JOB_EVIDENCE_SECONDS:
                source_scores.update(stereo._infer_selected_cues(
                    Path(stereo_pcm_path), batch, model_paths,
                    deadline_monotonic=deadline_monotonic, stop_requested=stop_requested,
                ))
                batch, batch_seconds = {}, 0.0
            batch[str(run["run_index"])] = [{"start": start, "end": end}]
            batch_seconds += end - start
        if batch:
            source_scores.update(stereo._infer_selected_cues(
                Path(stereo_pcm_path), batch, model_paths,
                deadline_monotonic=deadline_monotonic, stop_requested=stop_requested,
            ))
        session = stereo._session(ort, model_paths[1])

        def score(samples, start):
            stereo._ensure_active(deadline_monotonic, stop_requested)
            values = samples.astype(np.float32) / 32768.0
            target = int(round(len(values) * stereo.PANN_SAMPLE_RATE / engine.PCM_SAMPLE_RATE))
            if len(values) < 2 or target < 2:
                raise ValueError("panns_signal_too_short")
            signal = np.interp(np.arange(target) * engine.PCM_SAMPLE_RATE / stereo.PANN_SAMPLE_RATE,
                               np.arange(len(values)), values).astype(np.float32)
            scores = session.run(["clipwise_output"], {"input_values": signal.reshape(1, -1)})[0][0]
            return {"start": float(start), "end": float(start) + len(values) / engine.PCM_SAMPLE_RATE,
                    "male_score": float(max(scores[stereo._MALE_SPEECH_INDEX], scores[stereo._MALE_SINGING_INDEX])),
                    "female_score": float(max(scores[stereo._FEMALE_SPEECH_INDEX], scores[stereo._FEMALE_SINGING_INDEX]))}

        for run in plan["runs"]:
            stereo._ensure_active(deadline_monotonic, stop_requested)
            samples = engine._compact_run_samples(run, region_samples=regions, region_bounds=bounds)
            run_windows = [w for w in plan["windows"] if w["run_index"] == run["run_index"]]
            # Long continuous/overlapping speech is not a single-person gender authority.
            if len(run_windows) + 1 > gender.MAX_CUES_PER_SPEAKER or str(run["run_index"]) not in source_scores:
                continue
            full = source_scores[str(run["run_index"])][0]
            rows = []
            for window in run_windows:
                start, end = (int(round(float(window[key]) * engine.PCM_SAMPLE_RATE))
                              for key in ("speech_start_seconds", "speech_end_seconds"))
                rows.append(score(samples[start:end], window["source_position"]))
            evidence[run["run_index"]] = {"full": full, "windows": rows}
    except (ImportError, MemoryError, OSError, OverflowError, IndexError, KeyError, TypeError, ValueError, RuntimeError, cast.AutoCastManualRequired):
        pass
    finally:
        stereo._CLASSIFIER_LOCK.release()
    return evidence


def _mixed_two_count_authority(base, shifted, aggregate, positions, speech, probs, reliable, partitions) -> dict:
    counts = [int(partition[0]) for partition in partitions]
    if sorted(counts) != [1, 2, 2]:
        raise ValueError("fixed_vocal_smart_speech_count_unstable")
    two_views = [partition[1] for partition in partitions if partition[0] == 2]
    for labels in two_views:
        engine._validate_cluster_support(labels, speech[reliable], 2)
    aligned = engine._align_cluster_labels_to_reference(
        two_views[0].tolist(), two_views[1].tolist(), speaker_count=2, minimum_speakers=1)
    if np.mean(two_views[0] == aligned) < engine.SPEECH_PARTITION_MIN_AGREEMENT:
        raise ValueError("fixed_vocal_smart_speech_partition_unstable")
    threshold = gender.MULTI_GENDER_STRONG_CONFIDENCE
    if any(np.count_nonzero(votes) < stereo.MIN_CLASSIFIED_CUES_PER_SPEAKER for votes in (
        probs[reliable] >= threshold, probs[reliable] <= 1 - threshold,
    )):
        raise ValueError("fixed_vocal_gender_evidence_invalid")
    authority = engine.build_gender_constrained_speech_authority(
        base[reliable], shifted[reliable], positions[reliable], speech[reliable], probs[reliable],
        speaker_count=2, minimum_speakers=1,
    )
    if (set(authority["speaker_registers"]) != {"low", "high"}
            or min(authority[k] for k in ("base_shift_agreement", "base_aggregate_agreement", "shift_aggregate_agreement"))
            < engine.SPEECH_PARTITION_MIN_AGREEMENT):
        raise ValueError("fixed_vocal_smart_speech_partition_unstable")
    trusted = np.asarray(authority["labels"])
    centroids = np.stack([aggregate[reliable][trusted == label].mean(axis=0) for label in range(2)])
    norms = np.linalg.norm(centroids, axis=1)
    if not np.isfinite(norms).all() or np.any(norms <= 0):
        raise ValueError("fixed_vocal_smart_speech_partition_unstable")
    centroids /= norms[:, None]
    projected_base = np.argmax(base[~reliable] @ centroids.T, axis=1)
    projected_shifted = np.argmax(shifted[~reliable] @ centroids.T, axis=1)
    if np.any(projected_base != projected_shifted):
        raise ValueError("fixed_vocal_smart_speech_partition_unstable")
    labels = np.empty(len(base), dtype=np.int64)
    # Keep validated acoustic/register labels; centroid projection is only for missing views.
    labels[reliable] = trusted
    labels[~reliable] = projected_base
    engine._validate_cluster_support(labels, speech, 2)
    authority.update(labels=labels.tolist(), unit_confidences=engine._cluster_unit_confidences(aggregate, labels, 2),
                     speaker_count_views=counts, supported_window_recovery=True, mixed_two_count_recovery=True,
                     unreliable_view_window_count=int((~reliable).sum()),
                     register_ambiguous_window_count=int(np.count_nonzero(
                         reliable & (probs < threshold) & (probs > 1 - threshold))))
    return authority


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
        return _mixed_two_count_authority(base, shifted, aggregate, positions, speech, probs, reliable, partitions)
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
        if (str(cause) in {"fixed_vocal_smart_speech_view_unstable", "fixed_vocal_gender_ambiguity_invalid",
                           "fixed_vocal_gender_evidence_invalid"}
                or (str(cause) == "fixed_vocal_smart_speech_count_unstable" and sorted(counts) == [1, 2, 2])):
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
    source_gender_evidence = _pann_source_run_evidence(
        vocal_pcm, views["plan"], stereo_pcm_path=stereo_pcm_path,
        deadline_monotonic=deadline_monotonic, stop_requested=stop_requested,
    )
    if source_gender_evidence:
        authority = _apply_source_gender_evidence(authority, views, source_gender_evidence)
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
            "source_gender_verified_run_count": authority.get("source_gender_verified_run_count", 0),
            "source_gender_corrected_window_count": authority.get("source_gender_corrected_window_count", 0),
            "source_gender_register_corrected": authority.get("source_gender_register_corrected", False),
            "speaker_count_views": authority["speaker_count_views"],
            "speech_view_cosine_min": authority["view_cosine_min"],
            "speech_view_agreement": min(authority[k] for k in (
                "base_shift_agreement", "base_aggregate_agreement", "shift_aggregate_agreement"))}
