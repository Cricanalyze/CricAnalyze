import sys
import numpy as np
sys.path.insert(0, "/app/backend")
import bowling_assess as ba

IMG = np.zeros((600, 800, 3), np.uint8)


def frame(idx, pts, fps=30):
    kp = [[0.0, 0.0, 0.0] for _ in range(17)]
    for i, (x, y) in pts.items():
        kp[i] = [float(x), float(y), 0.9]
    return {"idx": idx, "t": round(idx / fps, 3), "img": IMG, "kp": kp}


def body(dx=0, sho_w=80, hip_w=50, lean=0, knee=(0, 0), ank_back=None, ank_front=None):
    """Right-arm bowler facing +x. Shoulders/hips centred at x=400+dx."""
    c = 400 + dx
    return {0: (c + lean, 120), 5: (c - sho_w / 2 + lean, 160), 6: (c + sho_w / 2 + lean, 160), 7: (c - 50, 200), 8: (c + 50, 120), 9: (c - 60, 240), 10: (c + 60, 60),
            11: (c - hip_w / 2, 260), 12: (c + hip_w / 2, 260), 13: (c + 40 + knee[0], 340), 14: (c - 30 + knee[1], 340),
            15: ank_front or (c + 50, 420), 16: ank_back or (c - 40, 420)}


def phases(fr_bfc, fr_ffc, fr_rel):
    return {"back_foot_contact": {"frame": fr_bfc, "status": "estimated"}, "front_foot_contact": {"frame": fr_ffc, "status": "estimated"},
            "release": {"frame": fr_rel, "status": "detected"}}


def seq_run():
    run = [frame(i, body(dx=-200 + i * 10)) for i in range(0, 20)]
    bfc = frame(20, body(dx=0, sho_w=100, hip_w=60))
    ffc = frame(24, body(dx=30, sho_w=95, hip_w=58, knee=(-20, 0), ank_front=(400 + 30 + 60, 420)))
    rel = frame(27, body(dx=50, lean=30))
    return run + [frame(19, body(dx=-10)), bfc, ffc, rel], bfc, ffc, rel


def test_all_four_measured_side_on():
    seq, bfc, ffc, rel = seq_run()
    out, imgs = ba.assess(seq, phases(bfc, ffc, rel), "r_wri", "side_on", 30)
    st = {d["key"]: d for d in out}
    assert [d["key"] for d in out] == ["back_foot_landing", "action_type", "shin_lead", "trunk_lean"]
    assert st["back_foot_landing"]["status"] == "measured" and st["back_foot_landing"]["idx"] == 20
    assert "to the nearest frame" in st["back_foot_landing"]["details"][0]["value"]
    assert any("Foot direction" == d["label"] and "Not measurable" in d["value"] for d in st["back_foot_landing"]["details"])
    assert st["shin_lead"]["status"] == "measured" and st["shin_lead"]["idx"] == 24
    assert "ankle ahead of the knee" in st["shin_lead"]["summary"]
    tl = st["trunk_lean"]
    assert tl["status"] == "measured" and any("forward" in d["value"] for d in tl["details"] if d["label"] == "Release")
    assert any(d["label"] == "Lower-back bending" for d in tl["details"])
    assert st["action_type"]["status"] == "measured" and "Side-on" in st["action_type"]["summary"]
    assert {k for k, _, _ in imgs} == {f"assess:{k}" for k in st}
    assert all(m["idx"] in (20, 24, 27) for d in out for m in d["marks"])


def test_shin_needs_side_on_and_action_inconclusive_for_other():
    seq, bfc, ffc, rel = seq_run()
    out, _ = ba.assess(seq, phases(bfc, ffc, rel), "r_wri", "other", 30)
    st = {d["key"]: d for d in out}
    assert st["shin_lead"]["status"] == "unavailable" and "side-on" in st["shin_lead"]["reason"]
    assert st["action_type"]["status"] == "inconclusive"
    assert st["trunk_lean"]["status"] == "unavailable"


def test_hidden_back_ankle_marks_unavailable():
    seq, bfc, ffc, rel = seq_run()
    bfc["kp"][16] = [0, 0, 0.2]
    out, _ = ba.assess(seq, phases(bfc, ffc, rel), "r_wri", "side_on", 30)
    assert out[0]["status"] == "unavailable" and "ankle" in out[0]["reason"]


def test_missing_phases_never_guess():
    seq, *_ = seq_run()
    out, imgs = ba.assess(seq, {}, None, "side_on", 30)
    assert [d["status"] for d in out] == ["unavailable", "inconclusive", "unavailable", "unavailable"] and imgs == []


def test_mixed_action_when_hips_and_shoulders_disagree():
    seq, bfc, ffc, rel = seq_run()
    bfc["kp"][5], bfc["kp"][6] = [395, 160, 0.9], [405, 160, 0.9]
    out, _ = ba.assess(seq, phases(bfc, ffc, rel), "r_wri", "side_on", 30)
    assert out[1]["summary"].startswith("Mixed action")


def test_report_view_exposes_assessments_without_internals():
    import report_view
    seq, bfc, ffc, rel = seq_run()
    out, _ = ba.assess(seq, phases(bfc, ffc, rel), "r_wri", "side_on", 30)
    out[0]["ai_note"] = {"text": "Back foot roughly parallel to the crease", "image_index": 3}
    rows = report_view.assessments_view({"bowling_assessments": out})
    assert [r["status_label"] for r in rows][:2] == ["Measured", "Measured"]
    assert rows[0]["ai_note"].startswith("Back foot") and "marks" not in rows[0]
    assert report_view.assessments_view({}) == []


def test_direction_from_stride_when_runup_unclear():
    seq, bfc, ffc, rel = seq_run()
    still = [frame(i, body(dx=0)) for i in range(0, 20)] + [bfc, ffc, rel]
    out, _ = ba.assess(still, phases(bfc, ffc, rel), "r_wri", "side_on", 30)
    assert "unclear" not in out[2]["summary"] and "ankle ahead of the knee" in out[2]["summary"]
