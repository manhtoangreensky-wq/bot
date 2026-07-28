import json
from pathlib import Path

from services import video_real_render_connector as connector


def _project(scene_count: int) -> dict:
    return {
        "scene_count": scene_count,
        "invoice_json": json.dumps(
            {
                "scene_count": scene_count,
                "scene_seconds": 8,
                "duration_seconds": scene_count * 8,
            }
        ),
    }


def test_short_recovered_single_scene_is_normalized_to_sold_duration(monkeypatch, tmp_path):
    assert hasattr(connector, "finalize_recovered_product_video_artifact")
    raw = tmp_path / "raw-provider.mp4"
    raw.write_bytes(b"raw-provider-video")
    normalized_paths = []

    def fake_probe(path: str, **_kwargs):
        duration = 8.0 if str(path).endswith("finalized.mp4") else 6.016
        return {
            "ok": True,
            "path": str(path),
            "bytes": Path(path).stat().st_size,
            "duration": duration,
            "has_video": True,
            "has_audio": False,
        }

    def fake_normalize(source: str, output: str, target: float):
        assert source == str(raw)
        assert target == 8.0
        Path(output).write_bytes(b"normalized-provider-video")
        normalized_paths.append(output)
        return output

    monkeypatch.setattr(connector.video_final_output, "probe_video", fake_probe)
    monkeypatch.setattr(connector, "normalize_scene_duration", fake_normalize)

    result = connector.finalize_recovered_product_video_artifact(
        {
            "source": "product_video",
            "product_type": "video_ai_prompt",
            "scene_count": 1,
        },
        _project(1),
        str(raw),
        workspace=str(tmp_path),
    )

    assert result["ok"] is True
    assert result["recovery_duration_normalized"] is True
    assert result["raw_duration_seconds"] == 6.016
    assert result["final_duration_seconds"] == 8.0
    assert result["expected_duration_seconds"] == 8
    assert result["final_duration_contract"]["ok"] is True
    assert result["final_video_path"] == normalized_paths[0]


def test_matching_recovered_single_scene_is_reused_without_transcode(monkeypatch, tmp_path):
    assert hasattr(connector, "finalize_recovered_product_video_artifact")
    raw = tmp_path / "already-eight-seconds.mp4"
    raw.write_bytes(b"valid-provider-video")
    monkeypatch.setattr(
        connector.video_final_output,
        "probe_video",
        lambda path, **_kwargs: {
            "ok": True,
            "path": str(path),
            "bytes": Path(path).stat().st_size,
            "duration": 8.0,
            "has_video": True,
            "has_audio": False,
        },
    )
    monkeypatch.setattr(
        connector,
        "normalize_scene_duration",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not transcode matching output")),
    )

    result = connector.finalize_recovered_product_video_artifact(
        {"source": "product_video", "product_type": "video_ai_prompt", "scene_count": 1},
        _project(1),
        str(raw),
        workspace=str(tmp_path),
    )

    assert result["ok"] is True
    assert result["recovery_duration_normalized"] is False
    assert result["final_video_path"] == str(raw)


def test_multiscene_recovery_never_promotes_one_raw_clip_to_final(monkeypatch, tmp_path):
    assert hasattr(connector, "finalize_recovered_product_video_artifact")
    raw = tmp_path / "scene-one-only.mp4"
    raw.write_bytes(b"one-scene-only")
    monkeypatch.setattr(
        connector.video_final_output,
        "probe_video",
        lambda path, **_kwargs: {
            "ok": True,
            "path": str(path),
            "bytes": Path(path).stat().st_size,
            "duration": 8.0,
            "has_video": True,
            "has_audio": False,
        },
    )
    monkeypatch.setattr(
        connector,
        "normalize_scene_duration",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must use scene orchestrator")),
    )

    result = connector.finalize_recovered_product_video_artifact(
        {"source": "product_video", "product_type": "script_to_video", "scene_count": 2},
        _project(2),
        str(raw),
        workspace=str(tmp_path),
    )

    assert result["ok"] is False
    assert result["reason"] == "multiscene_recovery_requires_scene_orchestrator"
    assert result["delivery_allowed"] is False
