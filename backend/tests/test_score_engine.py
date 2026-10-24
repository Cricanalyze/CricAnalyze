import sys
sys.path.insert(0, "/app/backend")
import score_engine as se


def m(k, v, st="measured", c=0.8):
    return {"key": k, "value": v, "status": st, "confidence": c}


def test_metric_score_formula():
    assert se.metric_score(152.5, 140, 165, 30) == 100
    assert se.metric_score(140, 140, 165, 30) == 80
    assert se.metric_score(125, 140, 165, 30) == 40
    assert se.metric_score(100, 140, 165, 30) == 0
    assert se.metric_score(0.35, 0.0, 0.15, 0.4) == 40


def test_batting_complete_and_contributions():
    inp = [m("front_knee_angle", 152.5), m("head_over_front_foot", 0.1), m("setup_balance", 0.35, c=0.7),
           m("hands_height_backlift", 0.25, "measured_estimated_phase", 0.6), m("shoulder_alignment", None, "not_measurable", None)]
    r = se.compute("batting", inp, 3)
    assert r["status"] == "complete" and r["value"] == 85
    assert abs(sum(c["contribution"] or 0 for c in r["components"]) - 85) < 0.5
    assert se.recompute("batting", r)["value"] == 85


def test_missing_not_counted_as_zero_or_perfect():
    a = se.compute("batting", [m("front_knee_angle", 152.5), m("head_over_front_foot", 0.1), m("setup_balance", 0.35)], 3)
    b = se.compute("batting", [m("front_knee_angle", 152.5), m("head_over_front_foot", 0.1), m("setup_balance", 0.35),
                               m("hands_height_backlift", 9, "low_confidence", 0.4)], 3)
    assert a["value"] == b["value"] and b["coverage"] == a["coverage"]


def test_provisional_without_overall():
    r = se.compute("batting", [m("front_knee_angle", 152.5), m("head_over_front_foot", 0.1)], 3)
    assert r["value"] is None and r["status"] == "provisional"
    assert [c["score"] for c in r["components"] if c["score"] is not None] == [100.0, 100.0]


def test_phase_gate():
    inp = [m("front_knee_angle", 152.5), m("head_over_front_foot", 0.1), m("setup_balance", 0.1), m("hands_height_backlift", 0.25)]
    assert se.compute("batting", inp, 1)["value"] is None
    assert se.compute("batting", inp, 2)["value"] is not None


def test_bowling_rubric_separate():
    inp = [m("front_knee_angle", 172.5), m("trunk_tilt", 10), m("front_arm_elbow", 100), m("release_height", 0.95), m("follow_through_balance", 0.125)]
    r = se.compute("bowling", inp, 3)
    assert r["value"] == 100 and {c["key"] for c in r["components"]} == {"balance", "alignment", "joint_angles", "release"}
    assert se.rubric_hash("bowling") != se.rubric_hash("batting")


def test_bounds():
    r = se.compute("batting", [m("front_knee_angle", 10), m("head_over_front_foot", 5), m("setup_balance", 5), m("hands_height_backlift", -5)], 3)
    assert r["value"] == 0
