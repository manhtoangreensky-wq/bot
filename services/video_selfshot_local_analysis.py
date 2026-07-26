"""Provider-free local source analysis for the two SelfShot products."""

from __future__ import annotations

from copy import deepcopy
from math import hypot
from pathlib import Path
from statistics import fmean, pstdev
from typing import Any, Iterable, Mapping


SUPPORTED_KINDS = frozenset({"person", "object", "pet"})
KIND_LABELS = {
    "person": "Người",
    "object": "Vật thể",
    "pet": "Thú cưng",
}


class LocalSelfShotAnalysisError(RuntimeError):
    pass


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _bbox(value: Any) -> tuple[float, float, float, float]:
    items = list(value or [])
    if len(items) != 4:
        return (0.0, 0.0, 0.0, 0.0)
    x, y, width, height = (_number(item) for item in items)
    return (max(0.0, x), max(0.0, y), max(0.0, width), max(0.0, height))


def _iou(first: tuple[float, float, float, float], second: tuple[float, float, float, float]) -> float:
    ax, ay, aw, ah = first
    bx, by, bw, bh = second
    left = max(ax, bx)
    top = max(ay, by)
    right = min(ax + aw, bx + bw)
    bottom = min(ay + ah, by + bh)
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    union = aw * ah + bw * bh - intersection
    return intersection / union if union > 0 else 0.0


def _center_distance(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
    diagonal: float,
) -> float:
    ax, ay, aw, ah = first
    bx, by, bw, bh = second
    distance = hypot((ax + aw / 2) - (bx + bw / 2), (ay + ah / 2) - (by + bh / 2))
    return distance / max(1.0, diagonal)


def _track_observations(observations: Iterable[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    tracks: list[dict[str, Any]] = []
    assignments: list[dict[str, Any]] = []
    counters = {kind: 0 for kind in SUPPORTED_KINDS}
    ordered = sorted((deepcopy(dict(item)) for item in observations), key=lambda item: _number(item.get("timestamp_seconds")))
    for observation in ordered:
        timestamp = max(0.0, _number(observation.get("timestamp_seconds")))
        width = max(1.0, _number(observation.get("width"), 1))
        height = max(1.0, _number(observation.get("height"), 1))
        diagonal = hypot(width, height)
        frame_rows = []
        for raw in list(observation.get("detections") or []):
            detection = dict(raw or {})
            kind = str(detection.get("kind") or "").strip().lower()
            box = _bbox(detection.get("bbox"))
            if kind not in SUPPORTED_KINDS or box[2] <= 1 or box[3] <= 1:
                continue
            best: dict[str, Any] | None = None
            best_score = -1.0
            for candidate in tracks:
                if candidate["subject_type"] != kind:
                    continue
                overlap = _iou(tuple(candidate["last_bbox"]), box)
                distance = _center_distance(tuple(candidate["last_bbox"]), box, diagonal)
                if overlap < 0.12 and distance > 0.18:
                    continue
                score = overlap + max(0.0, 0.25 - distance)
                if score > best_score:
                    best = candidate
                    best_score = score
            if best is None:
                counters[kind] += 1
                subject_id = f"{kind}-{counters[kind]}"
                best = {
                    "subject_id": subject_id,
                    "subject_type": kind,
                    "label": f"{KIND_LABELS[kind]} {counters[kind]}",
                    "description": f"{KIND_LABELS[kind]} {counters[kind]}",
                    "first_seen_seconds": timestamp,
                    "last_seen_seconds": timestamp,
                    "last_bbox": list(box),
                    "samples": [],
                    "confidences": [],
                    "face_detected": False,
                }
                tracks.append(best)
            confidence = max(0.0, min(1.0, _number(detection.get("confidence"), 0.5)))
            best["last_seen_seconds"] = timestamp
            best["last_bbox"] = list(box)
            best["confidences"].append(confidence)
            best["face_detected"] = bool(best.get("face_detected") or detection.get("face_detected"))
            best["samples"].append({
                "timestamp_seconds": round(timestamp, 3),
                "bbox": [round(value, 2) for value in box],
                "confidence": round(confidence, 4),
            })
            frame_rows.append({"subject_id": best["subject_id"], "subject_type": kind, "bbox": box})
        assignments.append({"timestamp_seconds": timestamp, "width": width, "height": height, "tracks": frame_rows})

    normalized = []
    for item in tracks:
        samples = list(item.get("samples") or [])
        centers_x = [sample["bbox"][0] + sample["bbox"][2] / 2 for sample in samples]
        centers_y = [sample["bbox"][1] + sample["bbox"][3] / 2 for sample in samples]
        spread = (pstdev(centers_x) if len(centers_x) > 1 else 0.0) + (pstdev(centers_y) if len(centers_y) > 1 else 0.0)
        mean_size = fmean(sample["bbox"][2] + sample["bbox"][3] for sample in samples) if samples else 1.0
        confidence = fmean(item.get("confidences") or [0.0])
        normalized.append({
            "subject_id": item["subject_id"],
            "track_id": item["subject_id"],
            "subject_type": item["subject_type"],
            "label": item["label"],
            "description": item["description"],
            "appearance_start_seconds": round(_number(item.get("first_seen_seconds")), 3),
            "appearance_end_seconds": round(_number(item.get("last_seen_seconds")), 3),
            "confidence": round(confidence, 4),
            "stability": round(max(0.0, min(1.0, 1.0 - spread / max(1.0, mean_size))), 4),
            "face_detected": bool(item.get("face_detected")),
            "regions": samples,
            "provenance": "local_detector",
        })
    kind_order = {"person": 0, "pet": 1, "object": 2}
    normalized.sort(key=lambda item: (kind_order.get(item["subject_type"], 9), item["appearance_start_seconds"], item["subject_id"]))
    return normalized, assignments


def _relationships(assignments: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    found: dict[tuple[str, str], dict[str, Any]] = {}
    for frame in assignments:
        width = max(1.0, _number(frame.get("width"), 1))
        height = max(1.0, _number(frame.get("height"), 1))
        diagonal = hypot(width, height)
        people = [dict(item) for item in frame.get("tracks") or [] if item.get("subject_type") == "person"]
        targets = [dict(item) for item in frame.get("tracks") or [] if item.get("subject_type") in {"object", "pet"}]
        for person in people:
            for target in targets:
                distance = _center_distance(_bbox(person.get("bbox")), _bbox(target.get("bbox")), diagonal)
                overlap = _iou(_bbox(person.get("bbox")), _bbox(target.get("bbox")))
                if distance > 0.32 and overlap <= 0:
                    continue
                key = (str(person.get("subject_id")), str(target.get("subject_id")))
                current = found.setdefault(key, {
                    "person_id": key[0],
                    "object_id": key[1],
                    "target_type": str(target.get("subject_type")),
                    "relationship_type": "accompanying" if target.get("subject_type") == "pet" else "holding_or_close",
                    "relative_position": "preserve",
                    "contact_points": [],
                    "confidence_samples": [],
                })
                current["confidence_samples"].append(max(overlap, 1.0 - distance))
    rows = []
    for item in found.values():
        samples = list(item.pop("confidence_samples") or [0.0])
        item["confidence"] = round(max(0.0, min(1.0, fmean(samples))), 4)
        rows.append(item)
    return rows


def analyze_observations(
    observations: Iterable[Mapping[str, Any]],
    *,
    duration_seconds: float,
    source_hash: str,
    analysis_revision: int = 1,
    source_has_audio: bool = False,
) -> dict[str, Any]:
    rows = [deepcopy(dict(item)) for item in observations]
    tracks, assignments = _track_observations(rows)
    people = [item for item in tracks if item["subject_type"] == "person"]
    objects = [item for item in tracks if item["subject_type"] == "object"]
    pets = [item for item in tracks if item["subject_type"] == "pet"]
    relationships = _relationships(assignments)
    motion_scores = [max(0.0, _number(item.get("motion_score"))) for item in rows]
    shifts = [
        hypot(*([_number(value) for value in list(item.get("camera_shift") or [0, 0])[:2]] + [0, 0])[:2])
        for item in rows
    ]
    average_motion = fmean(motion_scores) if motion_scores else 0.0
    average_shift = fmean(shifts) if shifts else 0.0
    motion_summary = (
        "Chuyển động mạnh, cần giữ đúng hướng và nhịp nguồn"
        if average_motion >= 0.18
        else "Chuyển động vừa, có thể chuyển cảnh theo hành động nguồn"
        if average_motion >= 0.07
        else "Chuyển động nhẹ hoặc chủ thể tương đối ổn định"
    )
    camera_summary = (
        "Camera di chuyển rõ"
        if average_shift >= 3.0
        else "Camera chuyển nhẹ"
        if average_shift >= 0.8
        else "Camera tương đối ổn định"
    )
    references = [
        {
            "timestamp_seconds": round(max(0.0, _number(item.get("timestamp_seconds"))), 3),
            "source_timestamp_seconds": round(max(0.0, _number(item.get("source_timestamp_seconds") or item.get("timestamp_seconds"))), 3),
            "frame_index": int(_number(item.get("frame_index"))),
            "width": int(_number(item.get("width"))),
            "height": int(_number(item.get("height"))),
        }
        for item in rows[:5]
    ]
    confidence = fmean([_number(item.get("confidence")) for item in tracks]) if tracks else 0.0
    stability = fmean([_number(item.get("stability")) for item in tracks]) if tracks else 0.0
    status = "ready" if tracks else "ready_no_tracks"
    return {
        "analysis_status": status,
        "analysis_revision": max(1, int(analysis_revision or 1)),
        "analysis_version": "selfshot-local-cv-v1",
        "analysis_engine": "opencv_cpu",
        "source_hash": str(source_hash or ""),
        "duration_seconds": max(0.0, _number(duration_seconds)),
        "person_tracks": people,
        "face_tracks": [item for item in people if item.get("face_detected")],
        "object_tracks": objects,
        "product_tracks": [],
        "pet_tracks": pets,
        "subject_candidates": deepcopy(tracks),
        "relationship_candidates": relationships,
        "interaction_graph": deepcopy(relationships),
        "motion_summary": motion_summary,
        "camera_summary": camera_summary,
        "track_confidence": round(confidence, 4),
        "track_stability": round(stability, 4),
        "source_reference_frames": references,
        "source_has_audio": bool(source_has_audio),
        "sample_count": len(rows),
        "tracking_source": "local_opencv" if rows else "local_opencv_no_observations",
        "tracking_ready": bool(tracks),
        "provider_calls": 0,
        "provider_called": False,
        "job_created": False,
        "outbox_created": False,
        "wallet_mutations": 0,
        "xu_charged": 0,
    }


def _overlaps(box: tuple[float, float, float, float], detections: Iterable[Mapping[str, Any]]) -> bool:
    return any(_iou(box, _bbox(item.get("bbox"))) >= 0.2 for item in detections)


def analyze_video_file(
    path: str,
    *,
    start_seconds: float = 0.0,
    end_seconds: float | None = None,
    source_hash: str = "",
    analysis_revision: int = 1,
    source_has_audio: bool = False,
    sample_limit: int = 12,
) -> dict[str, Any]:
    """Analyze sampled source frames locally with OpenCV CPU detectors."""

    source = Path(path)
    if not source.is_file() or source.stat().st_size <= 0:
        raise LocalSelfShotAnalysisError("source_video_missing")
    try:
        import cv2  # type: ignore
        import numpy as np
    except ImportError as exc:
        raise LocalSelfShotAnalysisError("opencv_unavailable") from exc

    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise LocalSelfShotAnalysisError("source_video_open_failed")
    try:
        fps = max(1.0, float(capture.get(cv2.CAP_PROP_FPS) or 0))
        frame_count = max(1, int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0))
        width = max(1, int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0))
        height = max(1, int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0))
        source_duration = frame_count / fps
        start = max(0.0, min(_number(start_seconds), source_duration))
        end = source_duration if end_seconds is None else max(start, min(_number(end_seconds), source_duration))
        if end <= start:
            raise LocalSelfShotAnalysisError("source_segment_invalid")

        count = max(4, min(max(4, int(sample_limit or 12)), int((end - start) / 1.5) + 2))
        timestamps = np.linspace(start, max(start, end - 1 / fps), num=count)
        hog = cv2.HOGDescriptor()
        hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        face = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"))
        cat_path = Path(cv2.data.haarcascades) / "haarcascade_frontalcatface.xml"
        cat = cv2.CascadeClassifier(str(cat_path)) if cat_path.is_file() else None
        observations = []
        previous_gray = None

        for timestamp in timestamps:
            capture.set(cv2.CAP_PROP_POS_MSEC, float(timestamp) * 1000)
            ok, frame = capture.read()
            if not ok or frame is None:
                continue
            original_height, original_width = frame.shape[:2]
            scale = min(1.0, 720.0 / max(1, original_width))
            working = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else frame
            gray = cv2.cvtColor(working, cv2.COLOR_BGR2GRAY)
            gray = cv2.equalizeHist(gray)
            detections: list[dict[str, Any]] = []

            rectangles, weights = hog.detectMultiScale(working, winStride=(8, 8), padding=(8, 8), scale=1.05)
            for rect, weight in zip(rectangles, weights):
                x, y, box_width, box_height = [float(value) / scale for value in rect]
                detections.append({
                    "kind": "person",
                    "bbox": [x, y, box_width, box_height],
                    "confidence": max(0.55, min(0.99, 0.55 + _number(weight) / 4)),
                    "face_detected": False,
                })

            faces = face.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(24, 24)) if not face.empty() else []
            for x, y, face_width, face_height in faces:
                original_face = (x / scale, y / scale, face_width / scale, face_height / scale)
                matched = False
                for detection in detections:
                    if _iou(original_face, _bbox(detection.get("bbox"))) > 0.02:
                        detection["face_detected"] = True
                        detection["confidence"] = max(_number(detection.get("confidence")), 0.78)
                        matched = True
                        break
                if not matched:
                    px = max(0.0, (x - face_width * 1.3) / scale)
                    py = max(0.0, (y - face_height * 0.8) / scale)
                    pw = min(original_width - px, face_width * 3.6 / scale)
                    ph = min(original_height - py, face_height * 5.2 / scale)
                    detections.append({"kind": "person", "bbox": [px, py, pw, ph], "confidence": 0.74, "face_detected": True})

            if cat is not None and not cat.empty():
                for x, y, box_width, box_height in cat.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(24, 24)):
                    px = max(0.0, (x - box_width * 0.7) / scale)
                    py = max(0.0, (y - box_height * 0.4) / scale)
                    pw = min(original_width - px, box_width * 2.4 / scale)
                    ph = min(original_height - py, box_height * 2.8 / scale)
                    detections.append({"kind": "pet", "bbox": [px, py, pw, ph], "confidence": 0.72})

            camera_shift = (0.0, 0.0)
            motion_score = 0.0
            if previous_gray is not None and previous_gray.shape == gray.shape:
                shift, _response = cv2.phaseCorrelate(previous_gray.astype(np.float32), gray.astype(np.float32))
                camera_shift = (float(shift[0]), float(shift[1]))
                difference = cv2.absdiff(previous_gray, gray)
                motion_score = float(np.mean(difference) / 255.0)
                _threshold, mask = cv2.threshold(difference, 28, 255, cv2.THRESH_BINARY)
                mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
                mask = cv2.dilate(mask, None, iterations=2)
                contours, _hierarchy = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                frame_area = float(gray.shape[0] * gray.shape[1])
                moving = []
                for contour in contours:
                    area = float(cv2.contourArea(contour))
                    if area < frame_area * 0.006 or area > frame_area * 0.35:
                        continue
                    x, y, box_width, box_height = cv2.boundingRect(contour)
                    box = (x / scale, y / scale, box_width / scale, box_height / scale)
                    if _overlaps(box, detections):
                        continue
                    moving.append({
                        "kind": "object",
                        "bbox": list(box),
                        "confidence": max(0.5, min(0.78, 0.5 + area / frame_area)),
                    })
                detections.extend(sorted(moving, key=lambda item: item["bbox"][2] * item["bbox"][3], reverse=True)[:4])
            previous_gray = gray
            observations.append({
                "timestamp_seconds": float(timestamp - start),
                "source_timestamp_seconds": float(timestamp),
                "frame_index": int(round(float(timestamp) * fps)),
                "width": original_width,
                "height": original_height,
                "detections": detections,
                "camera_shift": list(camera_shift),
                "motion_score": motion_score,
            })
    finally:
        capture.release()

    report = analyze_observations(
        observations,
        duration_seconds=end - start,
        source_hash=source_hash,
        analysis_revision=analysis_revision,
        source_has_audio=source_has_audio,
    )
    report.update({
        "width": width,
        "height": height,
        "fps": round(fps, 4),
        "segment_start_seconds": round(start, 3),
        "segment_end_seconds": round(end, 3),
        "source_duration_seconds": round(source_duration, 3),
    })
    return report
