import sys, json
from datetime import datetime, timezone
sys.path.insert(0, "/app/backend")
import score_engine as se
import report_view as rv


def m(k, v, st="measured", c=0.8):
    return {"key": k, "value": v, "status": st, "confidence": c}


FULL = [m("front_knee_angle", 152.5), m("head_over_front_foot", 0.1), m("setup_balance", 0.35, c=0.7),
        m("hands_height_backlift", 0.25, "measured_estimated_phase", 0.6), m("shoulder_alignment", None, "not_measurable", None)]


def test_complete_evidence_unchanged():
    r = se.compute("batting", FULL, 3)
    d = se.display(r, scaled=False)
    assert r["value"] == 85 and d["value"] == 85 and d["status"] == "complete"
    assert r["provisional_value"] is None


def test_partial_evidence_provisional_normalised():
    r = se.compute("batting", [m("front_knee_angle", 152.5), m("setup_balance", 0.35)], 3)
    d = se.display(r, scaled=False)
    assert r["value"] is None and d["status"] == "provisional"
    # weighted mean over valid metrics only: (1.0*100 + 0.8*40) / 1.8
    assert d["value"] == round((100 + 0.8 * 40) / 1.8) == r["provisional_value"]
    assert d["included"] == 2 and d["total"] == 5


def test_one_detected_phase_is_provisional_with_same_formula():
    inp = [m("front_knee_angle", 152.5), m("head_over_front_foot", 0.1), m("setup_balance", 0.1), m("hands_height_backlift", 0.25)]
    gated = se.compute("batting", inp, 1)
    full = se.compute("batting", inp, 3)
    d = se.display(gated, scaled=False)
    assert gated["value"] is None and d["status"] == "provisional" and d["value"] == full["value"]


def test_missing_metrics_not_zero():
    a = se.display(se.compute("bowling", [m("trunk_tilt", 10)], 2))
    b = se.display(se.compute("bowling", [m("trunk_tilt", 10), m("release_height", None, "not_measurable", None), m("front_arm_elbow", 5, "low_confidence", 0.4)], 2))
    assert a["value"] == b["value"] == 100 and a["status"] == "provisional"


def test_zero_valid_measurements_unavailable():
    for kind in ("batting", "bowling"):
        d = se.display(se.compute(kind, [], 0))
        assert d["value"] is None and d["status"] == "unavailable" and d["evidence"] is None


def test_display_from_stored_v2_record_without_provisional_field():
    r = se.compute("batting", [m("front_knee_angle", 152.5), m("setup_balance", 0.35)], 3)
    r.pop("provisional_value")
    assert se.display(r, scaled=False)["value"] == round((100 + 0.8 * 40) / 1.8)


def test_evidence_labels():
    assert se.display(se.compute("batting", FULL, 3))["evidence"] in ("High", "Medium", "Limited")
    assert se.display(se.compute("batting", [m("front_knee_angle", 150, c=0.5)], 0))["evidence"] == "Limited"


def _rep(metrics, detected=3, quality=None, plan=True):
    sc = se.compute("batting", metrics, detected)
    for x in metrics:
        x.update({"name": x["key"], "unit": "°" if x["key"] in ("front_knee_angle", "shoulder_alignment") else "torso lengths", "phase": "impact", "t": 1.2})
    q = quality or {"usable": True, "detection_rate": 0.95, "keypoint_confidence": 0.8, "player_height_frac": 0.6, "issues": []}
    return {"id": "r1", "analysis_type": "batting", "created_at": datetime(2026, 10, 26, 14, 0, tzinfo=timezone.utc), "model": "anthropic/claude-sonnet-5-5",
            "strengths": ["Steady head"], "improvements": ["Get the front foot closer to the ball"], "drills": [{"name": "Shadow drive", "how_to": "Do it", "sets_reps": "3x10"}, {"name": "Drop ball", "how_to": "x"}],
            "practice_plan": [{"day": "Mon", "focus": "x", "duration_min": 20}], "limitations": ["Bat not visible."],
            "biomech": [{"video_id": "v", "angle": "side_on", "status": "measured", "quality": q, "metrics": metrics, "score": sc, "pipeline_version": "ca-pose-v1",
                         "model": {"pose_model": "RTMPose-m"}, "ball": {"status": "not_detected", "version": "ca-ball-v1", "model": {"detector": "YOLOX"}},
                         "phases": [{"key": "setup", "name": "Setup", "status": "detected", "t": 0.2, "idx": 6, "keypoint_confidence": 0.42, "keypoints": [[100 + i, 100 + 10 * i, 0.9] for i in range(17)], "frame_size": [1280, 720]},
                                    {"key": "impact", "name": "Impact", "status": "estimated", "t": 1.2, "idx": 36, "keypoint_confidence": 0.8, "keypoints": [[100 + i, 100 + 10 * i, 0.9] for i in range(17)], "frame_size": [1280, 720]},
                                    {"key": "backlift", "name": "Backlift", "status": "unavailable"}]}]}


INTERNAL = ("RTMPose", "YOLOX", "ca-score", "ca-pose", "ca-ball", "YOLO26", "Ultralytics", "claude", "keypoint", "kinematic")


def test_view_hides_internal_names_and_uses_ist():
    v = rv.build(_rep([m("front_knee_angle", 152.5), m("head_over_front_foot", 0.1), m("setup_balance", 0.1)]), "Asha")
    dump = json.dumps(v, default=str)
    for w in INTERNAL:
        assert w.lower() not in dump.lower(), w
    assert v["header"]["date"].endswith("IST") and "7:30 PM" in v["header"]["date"]
    assert v["header"]["shot_type"] is None and len(v["takeaways"]) == 3
    assert "diagnostics" in rv.build(_rep([m("front_knee_angle", 150)]), "A", staff=True)


def test_view_unreliable_overlay_omitted_and_timestamps_kept():
    v = rv.build(_rep([m("front_knee_angle", 152.5)]), "A")
    tl = {p["key"]: p for p in v["angles"][0]["timeline"]}
    assert tl["setup"]["show_overlay"] is False and tl["setup"]["overlay_note"]
    assert tl["impact"]["status_label"] == "Approximate timing" and tl["impact"]["t"] == 1.2 and tl["impact"]["frame_index"] == 36
    assert tl["backlift"]["status_label"] == "Not assessed reliably"


def test_poor_evidence_hides_plan_and_shows_tip():
    bad = {"usable": False, "detection_rate": 0.3, "keypoint_confidence": 0.3, "player_height_frac": 0.1, "issues": ["Player appears distant (about 10% of frame height). Move closer."]}
    v = rv.build(_rep([], 0, bad), "A")
    assert v["score"]["status"] == "unavailable" and v["score"]["value"] is None and v["score"]["tip"]
    assert v["practice_plan"] is None and v["next_step"] and len(v["drills"]) == 1
    assert v["video_quality"]["rating"] == "Poor"


def test_good_evidence_keeps_plan():
    v = rv.build(_rep(FULL[:4] + [m("shoulder_alignment", 5)]), "A")
    assert v["score"]["status"] == "complete" and v["practice_plan"] and v["video_quality"]["rating"] == "Good"


def test_history_comparable_only_same_angle():
    cur, old = _rep([m("front_knee_angle", 150)]), _rep([m("front_knee_angle", 140)])
    old["created_at"] = datetime(2026, 10, 1, tzinfo=timezone.utc)
    h = rv.comparable_history(cur, [old])
    assert h and h["metrics"][0]["change"] == 10 and h["metrics"][0]["change_display"].startswith("+10")
    old["biomech"][0]["angle"] = "front_on"
    assert rv.comparable_history(cur, [old]) is None
    assert rv.comparable_history(cur, []) is None


def test_display_scale_70_to_100_keeps_order_and_unavailable():
    assert [se.to_display(v) for v in (0, 40, 85, 100)] == [70, 82, 96, 100]
    r = se.compute("batting", FULL, 3)
    d = se.display(r)
    assert d["raw_value"] == 85 and d["value"] == 96 and r["value"] == 85
    assert se.display(se.compute("batting", [], 0))["value"] is None
