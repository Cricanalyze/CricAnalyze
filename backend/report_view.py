"""Customer-facing report view shared by the web report and the PDF. Pure function of saved report data; no invented values."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import score_engine

IST = ZoneInfo("Asia/Kolkata")
SCORABLE = score_engine.SCORABLE
OVERLAY_MIN_CONF = 0.5

METRIC_TEXT = {
    "batting": {
        "front_knee_angle": ("Front knee bend at impact", "How bent the front knee is as the bat comes through (180° is a straight leg)."),
        "hands_height_backlift": ("Hands height at top of backlift", "How far the hands rise above the shoulders, measured in torso lengths."),
        "head_over_front_foot": ("Head over front foot at impact", "Sideways gap between the head and the front foot; smaller means the head is more over the front foot."),
        "setup_balance": ("Balance at setup", "Sideways gap between the hips and the feet at setup; smaller means more centred."),
        "shoulder_alignment": ("Shoulder line at setup", "How much the shoulder line tilts at setup."),
    },
    "bowling": {
        "front_knee_angle": ("Front knee at release", "How straight the front leg is at release (180° is a straight leg)."),
        "trunk_tilt": ("Upper-body lean at release", "How far the upper body leans away from vertical at release."),
        "front_arm_elbow": ("Front arm bend at release", "How bent the non-bowling arm is at release."),
        "release_height": ("Release hand height", "How high the bowling hand is above the head at release, in torso lengths."),
        "follow_through_balance": ("Balance in follow-through", "Sideways gap between the hips and the feet after release; smaller means more balanced."),
    },
}
TILT_KEYS = {"shoulder_alignment", "trunk_tilt"}
UNIT = {"°": "°", "torso lengths": " × torso length"}
PHASE_TEXT = {
    "setup": "Stance before the movement starts.", "backlift": "Highest hand position before the swing.", "downswing": "Fastest hand movement in the swing.",
    "impact": "Approximate moment of impact, judged from the hands' lowest point. Bat-ball contact itself isn't detected.",
    "follow_through": "Highest hand position after the swing.", "run_up": "Earliest part of the approach in this clip.",
    "gather": "Hands closest to the chest before the jump.", "back_foot_contact": "Back foot landing, judged from the back ankle's lowest point.",
    "front_foot_contact": "Front foot landing, judged from the front ankle's lowest point.", "release": "Bowling hand at its highest point. Ball release itself isn't detected.",
}
PHASE_STATUS = {"detected": "Clear frame", "estimated": "Approximate timing", "unavailable": "Not assessed reliably"}
ISSUE_TEXT = [("Low resolution", "Record at 720p or higher so joints are sharper."), ("Low frame rate", "Record at 30–60 fps so fast movements aren't missed."),
              ("Player detected in only", "Keep the player in frame for the whole clip."),
              ("Lower body", "Keep the knees and feet in view — leg measurements need them."),
              ("Player appears distant", "Move closer so the player fills most of the frame height."),
              ("Body partly obstructed", "Make sure nothing blocks the player and the light is good."),
              ("Camera angle is 'other'", "Film side-on or front-on for the most measurements.")]
DEFAULT_TIP = {"batting": "Film side-on at hip height, 8–12 m away, with the whole body, feet and bat in frame.",
               "bowling": "Film side-on at hip height from 10–15 m, keeping the whole run-up, delivery stride and follow-through in frame."}
ANGLE_TIP = {"front_on": "Add a front-on clip as well — shoulder line and some balance measurements need a front-on view.", "batting": "Add a side-on clip as well — knee bend and head position can only be measured side-on.",
             "bowling": "Add a side-on clip as well — front-knee angle can only be measured side-on."}
QUALITY_TEXT = {"Good": "Clear footage — measurements are as reliable as a single camera allows.",
                "Fair": "Usable footage with some issues — a few measurements may be missing or less certain.",
                "Poor": "Hard-to-read footage — most measurements could not be taken reliably.",
                "Not assessed": "Body tracking wasn't available for this clip."}
VQ_METHOD = "Video quality is rated from the footage only: Poor if the player was found in under 60% of frames, the player was too small, or joints were mostly unclear; Fair if any other filming issue was found; otherwise Good. It is not part of the technique score."


def ist(dt, with_time=True):
    if not dt:
        return None
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    d = dt.astimezone(IST)
    return d.strftime("%d %b %Y, %I:%M %p IST").lstrip("0") if with_time else d.strftime("%d %b %Y").lstrip("0")


def fmt_val(v, unit):
    return f"{round(v) if unit == '°' else f'{v:.2f}'}{UNIT.get(unit, ' ' + (unit or ''))}"


def video_quality(b):
    q = b.get("quality")
    if b.get("status") == "unavailable" or not q:
        return {"rating": "Not assessed", "text": QUALITY_TEXT["Not assessed"]}
    poor = not q.get("usable") or q.get("detection_rate", 1) < 0.6 or q.get("keypoint_confidence", 1) < 0.5 or q.get("player_height_frac", 1) < 0.3
    r = "Poor" if poor else "Fair" if q.get("issues") else "Good"
    return {"rating": r, "text": QUALITY_TEXT[r]}


def filming_tips(bios, kind):
    tips = []
    for b in bios:
        for issue in (b.get("quality") or {}).get("issues") or []:
            tip = next((t for k, t in ISSUE_TEXT if issue.startswith(k)), None)
            if tip and tip not in tips:
                tips.append(tip)
        if any((m.get("reason") or "").startswith("Camera angle") for m in b.get("metrics") or []):
            tip = ANGLE_TIP["front_on" if b.get("angle") == "side_on" else kind]
            if tip not in tips:
                tips.append(tip)
    return tips[:3] or [DEFAULT_TIP[kind]]


def score_view(b, kind, tips):
    d = score_engine.display(b.get("score"))
    out = {**d, "label": {"complete": "Technique Score", "provisional": "Provisional Technique Score", "unavailable": "Score unavailable — record a clearer video"}[d["status"]]}
    if d["status"] == "complete":
        out["text"] = f"Fully assessed from {d['included']} measurements covering {round((d['coverage'] or 0) * 100)}% of the scoring weight."
    elif d["status"] == "provisional":
        out["text"] = (f"Provisional: uses only the {d['included']} of {d['total']} measurements available in this clip ({round((d['coverage'] or 0) * 100)}% of the scoring weight). "
                       "Missing measurements are left out, not counted as zero, so the score may change with a clearer clip.")
    else:
        out["text"] = "No technique measurement could be taken reliably from this clip, so a score can't be calculated."
        out["tip"] = tips[0]
    comps = (b.get("score") or {}).get("components") or []
    out["components"] = [{"name": c["name"], "score": round(c["score"]), "measured": len(c["metrics"]), "of": len(c["metrics"]) + len(c["missing"])} for c in comps if c.get("score") is not None]
    return out


def metric_rows(b, kind):
    out = []
    for m in b.get("metrics") or []:
        if m.get("status") not in SCORABLE or m.get("value") is None:
            continue
        name, desc = METRIC_TEXT[kind].get(m["key"], (m["name"], ""))
        v = m["value"]
        lo, hi = ((0, max(60, v * 1.2)) if m["key"] in TILT_KEYS else (0, 180)) if m["unit"] == "°" else (min(0, v * 1.2), max(1.5, v * 1.2))
        out.append({"key": m["key"], "name": name, "value": v, "unit": m["unit"], "display": fmt_val(v, m["unit"]), "phase": m["phase"], "t": m.get("t"),
                    "scale": [round(lo, 2), round(hi, 2)], "position": round((v - lo) / (hi - lo), 3) if hi > lo else 0,
                    "certainty": "Clear" if m["status"] == "measured" else "Approximate timing",
                    "interpretation": desc + (" Measured on an approximately timed frame, so treat it as a guide." if m["status"] != "measured" else "")})
    return out


def crop_box(p):
    kp, fs = p.get("keypoints"), p.get("frame_size")
    pts = [(x, y) for x, y, s in (kp or []) if s >= 0.3]
    if len(pts) < 5 or not fs:
        return None
    W, H = fs
    xs, ys = [a for a, _ in pts], [c for _, c in pts]
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    side = max(w, h) * 1.35
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    x0, y0 = max(0, cx - side * 0.75 / 2), max(0, cy - side / 2)
    x1, y1 = min(W, cx + side * 0.75 / 2), min(H, cy + side / 2)
    if (x1 - x0) * (y1 - y0) > 0.8 * W * H:
        return None
    return [round(x0 / W, 4), round(y0 / H, 4), round(x1 / W, 4), round(y1 / H, 4)]


def timeline(b, kind, mets):
    out = []
    by_phase = {}
    for m in mets:
        ph = "release" if kind == "bowling" and m["phase"] == "follow_through" else m["phase"]
        by_phase.setdefault(ph, []).append(f"{m['name']}: {m['display']}")
    for p in b.get("phases") or []:
        st = p.get("status", "unavailable")
        reliable = st != "unavailable" and (p.get("keypoint_confidence") or 0) >= OVERLAY_MIN_CONF
        row = {"key": p["key"], "name": p["name"], "status": st, "status_label": PHASE_STATUS.get(st, st), "t": p.get("t"), "frame_index": p.get("idx"),
               "note": PHASE_TEXT.get(p["key"], "") if st != "unavailable" else "This phase couldn't be identified reliably in the clip.",
               "metrics": by_phase.get(p["key"], []) if st != "unavailable" else [], "show_overlay": reliable, "crop": crop_box(p) if st != "unavailable" else None, "frame_size": p.get("frame_size"),
               "ball_in_frame": bool(p.get("ball")), "frame_asset_id": p.get("frame_asset_id"), "overlay_asset_id": p.get("overlay_asset_id") if reliable else None,
               "ball_overlay_asset_id": p.get("ball_overlay_asset_id") if reliable else None}
        if st != "unavailable" and not reliable:
            row["overlay_note"] = "Skeleton hidden: the joints weren't clear enough to draw accurately."
        for k in ("frame_url", "overlay_url", "ball_overlay_url"):
            if p.get(k) and (k == "frame_url" or reliable):
                row[k] = p[k]
        out.append(row)
    return out


def ball_view(ball):
    if not ball:
        return None
    if ball.get("status") == "tracked":
        gaps = list(dict.fromkeys(g["reason"] for g in ball.get("gaps") or []))[:2]
        return {"tracked": True, "text": f"Ball tracked in {ball['frames_detected']} of {ball['frames_processed']} frames checked. Where it's visible, a yellow ring marks it on the frames.",
                "notes": gaps + ["Ball speed, release and bat contact aren't measured."]}
    return {"tracked": False, "text": "The ball couldn't be tracked reliably in this clip, so no ball path is shown.", "notes": []}


def angle_view(b, kind, tips):
    mets = metric_rows(b, kind) if b.get("status") != "unavailable" else []
    w = b.get("analysed_window") or {}
    mmss = lambda s: f"{int(s // 60)}:{int(s % 60):02d}"
    window = f"Analysed {mmss(w['t0'])}–{mmss(w['t1'])} of the clip, the part with the most movement." if w.get("method") == "most_movement" else None
    return {"video_id": b.get("video_id"), "angle": (b.get("angle") or "").replace("_", "-"), "pose_available": b.get("status") != "unavailable", "analysed_window": window,
            "video_quality": video_quality(b), "score": score_view(b, kind, tips), "metrics": mets, "timeline": timeline(b, kind, mets) if b.get("status") != "unavailable" else [],
            "ball": ball_view(b.get("ball"))}


def _primary(angles):
    rank = {"complete": 2, "provisional": 1, "unavailable": 0}
    return max(range(len(angles)), key=lambda i: (rank[angles[i]["score"]["status"]], angles[i]["score"]["coverage"] or 0)) if angles else None


def build(rep, owner_name=None, history=None, staff=False):
    kind = rep["analysis_type"]
    bios = rep.get("biomech") or []
    tips = filming_tips(bios, kind)
    angles = [angle_view(b, kind, tips) for b in bios]
    pi = _primary(angles)
    prim = angles[pi] if pi is not None else {"score": {"status": "unavailable", "label": "Score unavailable — record a clearer video", "value": None,
                                                         "text": "Body tracking wasn't available, so a score can't be calculated.", "tip": tips[0], "components": []},
                                              "video_quality": {"rating": "Not assessed", "text": QUALITY_TEXT["Not assessed"]}, "metrics": []}
    sc, vq = prim["score"], prim["video_quality"]
    poor = sc["status"] == "unavailable" or vq["rating"] == "Poor" or sc.get("evidence") == "Limited"
    raw = (bios[pi].get("score") or {}) if pi is not None else {}
    mets = {m["key"]: m for m in prim["metrics"]}
    strengths, improvements = list(rep.get("strengths") or []), list(rep.get("improvements") or [])
    drills = [{"name": d.get("name"), "objective": d.get("purpose") or d.get("objective"), "instructions": d.get("how_to"), "dosage": d.get("sets_reps"),
               "mistakes": d.get("common_mistakes"), "area": (d.get("linked_area") or "").replace("_", " ") or None} for d in rep.get("drills") or [] if d.get("name")]
    strong = next((mets[k] for k in raw.get("strongest") or [] if k in mets), None)
    opp = next((mets[k] for k in raw.get("opportunities") or [] if k in mets), None)
    t1 = (f"{strong['name']} ({strong['display']}) was your strongest measured area." if strong else
          strengths[0] if strengths else "No area stood out clearly enough in this clip to call a strength.")
    t2 = (f"{opp['name']} ({opp['display']}) is the measurement with the most room to improve." if opp else
          improvements[0] if improvements else "Not enough clear evidence to pick a priority yet.")
    t3 = ("Record a clearer clip using the filming tips below." if poor or not drills else f"Practise “{drills[0]['name']}”" + (f" — {drills[0]['dosage']}." if drills[0].get("dosage") else "."))
    working = [s for s in strengths if s != t1][:4]
    co = rep.get("coaching") or {}
    coaching = {"working": working, "priority": co.get("priority") or (improvements[0] if improvements else None),
                "why": co.get("why_it_matters") or (drills[0]["objective"] if drills else None),
                "how": co.get("how_to_practice") or (drills[0]["instructions"] if drills else None),
                "measured_basis": [f"{m['name']}: {m['display']}" for m in prim["metrics"]][:3],
                "summary": rep.get("coach_summary") or rep.get("summary")}
    plan = None if poor else rep.get("practice_plan")
    actions = []
    if poor:
        actions.append("Record a new clip using the filming tips below.")
    if drills:
        actions.append(f"Practise “{drills[0]['name']}”" + (f" ({drills[0]['dosage']})" if drills[0].get("dosage") else "") + (f" to work on {drills[0]['area']}." if drills[0].get("area") else "."))
    if not poor and len(drills) > 1:
        actions.append(f"Add “{drills[1]['name']}” once the first drill feels comfortable.")
    actions.append("Upload a new clip from the same camera angle in 1–2 weeks to track progress.")
    lim = (rep.get("limitations") or [])[:1]
    view = {
        "header": {"player": owner_name, "analysis_type": kind.title(), "shot_type": rep.get("shot_type") or None, "date": ist(rep.get("created_at")),
                   "video_quality": vq["rating"], "score_status": sc["label"], "angles": [a["angle"] for a in angles]},
        "score": sc, "video_quality": {**vq, "method": VQ_METHOD}, "takeaways": [t1, t2, t3], "whats_working": working, "angles": angles, "primary": pi,
        "coaching": coaching, "drills": drills[:1] if poor else drills, "practice_plan": plan, "next_step": tips[0] if poor else None,
        "progress": history, "action_plan": actions, "filming_tips": tips, "evidence_poor": poor,
        "limitations": " ".join([x.rstrip(".") + "." for x in lim] + ["Measurements are 2D estimates from one camera; bat speed, ball speed and forces aren't measured."]),
        "score_method": "Each measurement is compared with a coaching reference and the results are combined using fixed weights. Missing measurements are left out rather than counted as zero. The score describes technique in this clip only; it isn't an official rating.",
    }
    if staff:
        view["diagnostics"] = {"vision_model": rep.get("model"), "angles": [{"angle": b.get("angle"), "pose": b.get("model"), "pipeline": b.get("pipeline_version"),
                               "score_version": (b.get("score") or {}).get("version"), "rubric": (b.get("score") or {}).get("rubric_hash"), "quality": b.get("quality"),
                               "ball": {k: (b.get("ball") or {}).get(k) for k in ("version", "model", "status", "mean_conf", "coverage", "error")}} for b in bios]}
    return view


def comparable_history(rep, prev_reps):
    """Most recent earlier report with the same type and camera angle; equivalent measured metrics only."""
    cur = {b.get("angle"): b for b in rep.get("biomech") or [] if b.get("status") != "unavailable"}
    for old in prev_reps:
        for ob in old.get("biomech") or []:
            nb = cur.get(ob.get("angle"))
            if not nb or ob.get("status") == "unavailable":
                continue
            kind = rep["analysis_type"]
            om = {m["key"]: m for m in ob.get("metrics") or [] if m.get("status") in SCORABLE and m.get("value") is not None}
            rows = []
            for m in nb.get("metrics") or []:
                o = om.get(m["key"])
                if o and m.get("status") in SCORABLE and m.get("value") is not None:
                    name = METRIC_TEXT[kind].get(m["key"], (m["name"],))[0]
                    ch = m["value"] - o["value"]
                    rows.append({"name": name, "unit": m["unit"], "before": o["value"], "after": m["value"], "change": round(ch, 1 if m["unit"] == "°" else 2),
                                 "before_display": fmt_val(o["value"], m["unit"]), "after_display": fmt_val(m["value"], m["unit"]),
                                 "change_display": ("+" if ch > 0 else "") + fmt_val(ch, m["unit"])})
            if not rows:
                continue
            sb, sa = score_engine.display(ob.get("score")), score_engine.display(nb.get("score"))
            lbl = {"complete": "Technique Score", "provisional": "Provisional", "unavailable": "Unavailable"}
            return {"previous_date": ist(old.get("created_at")), "angle": (ob.get("angle") or "").replace("_", "-"), "metrics": rows,
                    "score_before": {"value": sb["value"], "status": lbl[sb["status"]]}, "score_after": {"value": sa["value"], "status": lbl[sa["status"]]},
                    "explanation": f"Compared with your {ist(old.get('created_at'), False)} {kind} clip from the same {(ob.get('angle') or '').replace('_', '-')} camera angle. "
                                   "Only measurements taken in both clips are compared; differences in filming can also change the numbers."
                                   + (" At least one of these scores is provisional, so compare them with care." if "provisional" in (sb["status"], sa["status"]) else "")}
    return None


def list_summary(rep):
    bios = rep.get("biomech") or []
    best = None
    for b in bios:
        d = score_engine.display(b.get("score"))
        if d["value"] is not None and (best is None or d["status"] == "complete"):
            best = d
    return {"value": best["value"], "status": best["status"]} if best else {"value": None, "status": "unavailable"}
