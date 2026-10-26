# Score engine edge cases (ca-score-v2): empty, all low-confidence, bowling with unavailable phase, determinism
import sys
sys.path.insert(0, "/app/backend")
import score_engine as se


def test_empty_inputs():
    for kind in ("batting", "bowling"):
        r = se.compute(kind, [], 0)
        assert r["value"] is None and r["status"] == "provisional"
        assert r["coverage"] == 0 and r["evidence"]["level"] == "low"
        assert all(c["score"] is None and c["contribution"] is None for c in r["components"])
        assert r["strongest"] == [] and r["opportunities"] == []


def test_all_low_confidence():
    inp = [{"key": k, "value": 150, "status": "low_confidence", "confidence": 0.3} for k in se.RUBRICS["batting"]["ranges"]]
    r = se.compute("batting", inp, 4)
    assert r["value"] is None and r["included"] == [] and r["coverage"] == 0
    assert len(r["inputs"]) == len(inp)


def test_bowling_unavailable_phase():
    inp = [{"key": "front_knee_angle", "value": 170, "status": "measured", "confidence": 0.8},
           {"key": "trunk_tilt", "value": 10, "status": "measured", "confidence": 0.8},
           {"key": "front_arm_elbow", "value": 100, "status": "measured_estimated_phase", "confidence": 0.7},
           {"key": "release_height", "value": None, "status": "not_measurable", "confidence": None},
           {"key": "follow_through_balance", "value": 0.1, "status": "measured", "confidence": 0.8}]
    r = se.compute("bowling", inp, 1)  # only one detected phase -> gate fails
    assert r["value"] is None and r["status"] == "provisional"
    assert any(c["score"] is not None for c in r["components"])
    rel = next(c for c in r["components"] if c["key"] == "release")
    assert rel["score"] is None and rel["missing"][0]["status"] == "not_measurable"
    r2 = se.compute("bowling", inp, 3)
    assert r2["value"] is not None
    # contributions sum ~ overall
    assert abs(sum(c["contribution"] or 0 for c in r2["components"]) - r2["value"]) <= 1
    # estimated phase metric weight halved
    m = next(m for m in r2["metric_scores"] if m["key"] == "front_arm_elbow")
    assert m["effective_weight"] == 0.6 * se.EST_PHASE_FACTOR


def test_recompute_deterministic():
    inp = [{"key": k, "value": v, "status": "measured", "confidence": 0.8} for k, v in
           [("front_knee_angle", 150), ("hands_height_backlift", 0.3), ("head_over_front_foot", 0.1), ("setup_balance", 0.05)]]
    a = se.compute("batting", inp, 3)
    b = se.recompute("batting", a)
    assert a["value"] == b["value"] and a["rubric_hash"] == b["rubric_hash"]


def test_none_confidence_and_missing_status():
    inp = [{"key": "front_knee_angle", "value": 150, "status": "measured", "confidence": None}, {"key": "setup_balance", "value": 0.1}]
    r = se.compute("batting", inp, 2)
    assert r["included"] == ["front_knee_angle"]
