# Ball pipeline failure tolerance: disabled/unknown provider raise BallUnavailable; process_job converts any exception to status 'unavailable'
import os, sys, inspect
sys.path.insert(0, "/app/backend")
import pytest
import ball_pipeline as bp


def test_disabled_provider(monkeypatch):
    monkeypatch.setenv("BALL_PROVIDER", "disabled")
    with pytest.raises(bp.BallUnavailable, match="disabled"):
        bp.analyse("/root/testvids/bat.mp4", {})


def test_unknown_provider(monkeypatch):
    monkeypatch.setenv("BALL_PROVIDER", "foo")
    with pytest.raises(bp.BallUnavailable, match="not configured"):
        bp.analyse("/root/testvids/bat.mp4", {})


def test_missing_model(monkeypatch):
    monkeypatch.setattr(bp, "_sess", None)
    monkeypatch.setattr(bp, "MODEL_FILE", "nope.onnx")
    with pytest.raises(bp.BallUnavailable):
        bp._session()
    bp._sess = None


def test_process_job_catches_ball_errors():
    import analysis_routes as ar
    src = inspect.getsource(ar.process_job)
    i = src.index("ball_pipeline.analyse")
    blk = src[i - 200:i + 700]
    assert "except Exception" in blk and '"status": "unavailable"' in blk and "NOT_DETECTED" in blk


def test_phase_marker_no_guess():
    ball = {"status": "tracked", "detections": [{"frame": 10, "status": "observed", "track_id": 0, "cx": 1, "cy": 1},
                                                 {"frame": 11, "status": "estimated", "track_id": 0, "cx": 2, "cy": 2}]}
    assert bp.phase_marker(ball, 10)[0]["frame"] == 10
    assert bp.phase_marker(ball, 11) == (None, [])
    assert bp.phase_marker(ball, 12) == (None, [])
    assert bp.phase_marker({"status": "not_detected", "detections": []}, 10) == (None, [])
    assert bp.phase_marker({"status": "unavailable"}, 10) == (None, [])
