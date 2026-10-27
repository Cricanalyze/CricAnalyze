"""Bowling biomechanics assessments from 2D pose: back-foot landing, action type, shin lead, trunk lean.
Measured on original video frames at their original timestamps. Not part of the technique score."""
import math
import statistics

import cv2

import pose_pipeline as pp

OK = pp.KP_OK
DOWN_PITCH = ("front_on", "behind")
METHOD = {
    "back_foot_landing": "Contact = first analysed frame where the back ankle reaches its lowest point before front-foot contact (frames checked one by one around the landing). "
                         "Placement = horizontal distance from back ankle to the middle of the hips, in torso lengths. Foot direction can't be measured by body tracking (no toe or heel points); "
                         "an AI visual note is shown only when the foot is clearly visible.",
    "action_type": "Standard coaching definitions applied at back-foot contact. Shoulder and hip lines are compared with the line of the pitch, estimated from how wide each line "
                   "appears relative to the player's own widest view in the clip (2D, approximate). Side-on < 30°, semi-side-on 30–60°, front-on > 60°; mixed when shoulders and hips "
                   "differ by 30° or more, or the shoulders turn back 30° or more between back-foot and front-foot contact.",
    "shin_lead": "Angle of the front shin (knee to ankle) from vertical at front-foot contact, side-on camera only. Direction from the bowler's run-up direction in the clip.",
    "trunk_lean": "Angle of the line from the middle of the hips to the middle of the shoulders, from vertical. Side-on shows forward/backward lean; front-on or behind shows sideways lean. "
                  "This is whole-trunk lean, not lower-back bending: body tracking has no spine points, so spinal curvature is not measured.",
}
NAMES = {"back_foot_landing": "Back-foot landing", "action_type": "Type of bowling action", "shin_lead": "Shin lead at front-foot contact",
         "trunk_lean": "Trunk lean (forward / backward / sideways)"}


def Pk(f, name):
    return pp.P(f, name, OK)


def _mid(f, a, b):
    return pp.mid(Pk(f, a), Pk(f, b))


def run_direction(seq, rel_t, ffc=None, arm=None):
    """+1 if the bowler moves to the right of the image, -1 left, None if unclear."""
    if ffc and arm:
        fr, bk = ("r", "l") if arm == "l_wri" else ("l", "r")
        fa, ba_, t = Pk(ffc, f"{fr}_ank"), Pk(ffc, f"{bk}_ank"), pp.torso(ffc)
        if fa and ba_ and t and abs(fa[0] - ba_[0]) >= 0.5 * t:
            return 1 if fa[0] > ba_[0] else -1
    pts = [(f["t"], _mid(f, "l_hip", "r_hip"), pp.torso(f)) for f in seq if f.get("kp") and f["t"] <= rel_t]
    pts = [p for p in pts if p[1] and p[2]]
    if len(pts) < 3:
        return None
    dx = pts[-1][1][0] - pts[0][1][0]
    return (1 if dx > 0 else -1) if abs(dx) >= 0.5 * statistics.median(p[2] for p in pts) else None


def _ratio(f, a, b):
    pa, pb, t = Pk(f, a), Pk(f, b), pp.torso(f)
    return math.dist(pa[:2], pb[:2]) / t if pa and pb and t else None


def _p90(xs):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(0.9 * len(xs)))] if xs else None


def _timing(seq, f, fps):
    prev = [g for g in seq if g.get("kp") and 0 < f["idx"] - g["idx"] <= max(1, round(fps / 25))]
    return "to the nearest frame" if prev else "approximate (nearest analysed frame)"


def _base(key, phase=None):
    return {"key": key, "name": NAMES[key], "status": "unavailable", "phase": phase, "summary": "", "details": [], "reason": "", "method": METHOD[key], "marks": []}


def _at(d, f):
    d.update({"t": round(f["t"], 3), "idx": f["idx"], "frame_size": [f["img"].shape[1], f["img"].shape[0]]})


def _norm(f, p):
    return [round(p[0] / f["img"].shape[1], 4), round(p[1] / f["img"].shape[0], 4)]


def _mark(f, label, lines):
    return {"t": round(f["t"], 3), "idx": f["idx"], "label": label, "lines": [{"a": _norm(f, a), "b": _norm(f, b), "color": c} for a, b, c in lines]}


def back_foot(seq, ph, arm, angle, fps, run_dir):
    d = _base("back_foot_landing", "back_foot_contact")
    p = ph.get("back_foot_contact")
    if not p:
        d["reason"] = "The back-foot landing wasn't identified in this clip."
        return d, None
    f, back = p["frame"], ("l" if arm == "l_wri" else "r")
    ank, hm, t = Pk(f, f"{back}_ank"), _mid(f, "l_hip", "r_hip"), pp.torso(f)
    _at(d, f)
    if not ank:
        d["reason"] = "The back ankle wasn't clearly visible at landing."
        return d, f
    d["status"] = "measured"
    d["details"].append({"label": "Landing moment", "value": f"{f['t']:.3f} s (frame {f['idx']}), {_timing(seq, f, fps)}"})
    lines = []
    if hm and t:
        off = (ank[0] - hm[0]) / t
        if angle == "side_on" and run_dir:
            along = off * run_dir
            txt = "roughly under the hips" if abs(along) < 0.1 else f"{abs(along):.2f} torso lengths {'behind' if along < 0 else 'ahead of'} the hips"
            d["details"].append({"label": "Foot placement", "value": txt})
        elif angle in DOWN_PITCH:
            txt = "roughly in line with the hips" if abs(off) < 0.1 else f"{abs(off):.2f} torso lengths to the {'right' if off > 0 else 'left'} of the hips (as seen in the video)"
            d["details"].append({"label": "Foot placement (sideways)", "value": txt})
        lines = [((hm[0], hm[1]), (hm[0], ank[1]), (216, 180, 0)), ((hm[0], ank[1]), (ank[0], ank[1]), (11, 158, 245))]
    if len(d["details"]) == 1:
        d["details"].append({"label": "Foot placement", "value": "Not available from this camera angle or run-up direction."})
    d["details"].append({"label": "Foot direction", "value": "Not measurable by body tracking (no toe or heel points)."})
    d["summary"] = f"Back foot landed at {f['t']:.2f} s (frame {f['idx']})."
    d["marks"].append(_mark(f, "Back-foot contact", [(a, b, "#F59E0B" if c == (11, 158, 245) else "#00B4D8") for a, b, c in lines]))
    d["_draw"] = (f, lines + [(ank[:2], None, (11, 158, 245))])
    return d, f


def _alpha(w, W, angle):
    r = min(1.0, w / W)
    return math.degrees(math.acos(r)) if angle == "side_on" else math.degrees(math.asin(r))


def action_type(seq, ph, angle):
    d = _base("action_type", "back_foot_contact")
    p, q = ph.get("back_foot_contact"), ph.get("front_foot_contact")
    if angle not in ("side_on",) + DOWN_PITCH:
        d.update(status="inconclusive", reason="Needs a side-on, front-on or behind camera angle.")
        return d
    if not p:
        d.update(status="inconclusive", reason="Back-foot contact wasn't identified, so the action can't be classified.")
        return d
    f = p["frame"]
    _at(d, f)
    ws, wh = _ratio(f, "l_sho", "r_sho"), _ratio(f, "l_hip", "r_hip")
    if ws is None or wh is None:
        d.update(status="inconclusive", reason="Shoulders or hips weren't clearly visible at back-foot contact.")
        return d
    Ws = _p90([r for r in (_ratio(g, "l_sho", "r_sho") for g in seq if g.get("kp")) if r])
    Wh = _p90([r for r in (_ratio(g, "l_hip", "r_hip") for g in seq if g.get("kp")) if r])
    if not Ws or not Wh or Ws < 0.55 or Wh < 0.35:
        d.update(status="inconclusive", reason="The shoulders and hips were never seen clearly enough across the clip to judge their direction.")
        return d
    a_s, a_h = _alpha(ws, Ws, angle), _alpha(wh, Wh, angle)
    cr = 0.0
    if q:
        later = [_ratio(g, "l_sho", "r_sho") for g in seq if g.get("kp") and f["t"] < g["t"] <= q["frame"]["t"]]
        later = [_alpha(r, Ws, angle) for r in later if r]
        cr = max(0.0, a_s - min(later)) if later else 0.0
    sep = abs(a_s - a_h)
    avg = (a_s + a_h) / 2
    if sep >= 30 or cr >= 30:
        cls = "Mixed action"
    else:
        cls = "Side-on action" if avg < 30 else "Semi-side-on action" if avg < 60 else "Front-on action"
    near = min(abs(avg - 30), abs(avg - 60), abs(sep - 30), abs(cr - 30))
    d.update(status="measured", summary=f"{cls} (approximate{', close to a category boundary' if near < 5 else ''}).")
    d["details"] = [{"label": "Shoulders at back-foot contact", "value": f"about {round(a_s)}° from side-on"},
                    {"label": "Hips at back-foot contact", "value": f"about {round(a_h)}° from side-on"},
                    {"label": "Hip–shoulder difference", "value": f"about {round(sep)}°"}]
    if q:
        d["details"].append({"label": "Shoulder turn-back before front-foot contact", "value": f"about {round(cr)}°"})
    ls, rs, lh, rh = Pk(f, "l_sho"), Pk(f, "r_sho"), Pk(f, "l_hip"), Pk(f, "r_hip")
    lines = [(ls[:2], rs[:2], (216, 180, 0)), (lh[:2], rh[:2], (11, 158, 245))]
    d["marks"].append(_mark(f, f"Action: {cls.replace(' action', '')}", [(a, b, "#00B4D8" if c == (216, 180, 0) else "#F59E0B") for a, b, c in lines]))
    d["_draw"] = (f, lines)
    return d


def shin_lead(ph, arm, angle, run_dir):
    d = _base("shin_lead", "front_foot_contact")
    p = ph.get("front_foot_contact")
    if angle != "side_on":
        d["reason"] = "Shin angle needs a side-on camera."
        return d
    if not p or not arm:
        d["reason"] = "Front-foot contact wasn't identified in this clip."
        return d
    f, fr = p["frame"], ("r" if arm == "l_wri" else "l")
    _at(d, f)
    k, a = Pk(f, f"{fr}_knee"), Pk(f, f"{fr}_ank")
    if not k or not a or a[1] <= k[1]:
        d["reason"] = "The front knee or ankle wasn't clearly visible at front-foot contact."
        return d
    ang = math.degrees(math.atan2(abs(k[0] - a[0]), a[1] - k[1]))
    d["status"] = "measured"
    if ang < 3:
        direction = "close to vertical"
    elif run_dir is None:
        direction = "direction unclear (run-up direction not visible)"
    else:
        direction = ("knee ahead of the ankle — shin leaning towards the batter" if (k[0] - a[0]) * run_dir > 0
                     else "ankle ahead of the knee — shin angled back (braced front leg)")
    d["summary"] = f"Front shin about {round(ang)}° from vertical at front-foot contact, {direction}."
    d["details"] = [{"label": "Shin angle from vertical", "value": f"{round(ang)}°"}, {"label": "Direction", "value": direction},
                    {"label": "Measured at", "value": f"front-foot contact, {f['t']:.3f} s (frame {f['idx']})"}]
    lines = [(k[:2], a[:2], (11, 158, 245)), ((a[0], a[1]), (a[0], k[1]), (220, 220, 220))]
    d["marks"].append(_mark(f, f"Shin {round(ang)}°", [(k[:2], a[:2], "#F59E0B"), ((a[0], a[1]), (a[0], k[1]), "#E2E8F0")]))
    d["_draw"] = (f, lines)
    return d


def trunk_lean(ph, arm, angle, run_dir):
    d = _base("trunk_lean", "release")
    if angle not in ("side_on",) + DOWN_PITCH:
        d["reason"] = "Trunk lean needs a side-on, front-on or behind camera."
        return d
    rows, best = [], None
    for key, label in (("back_foot_contact", "Back-foot contact"), ("front_foot_contact", "Front-foot contact"), ("release", "Release")):
        p = ph.get(key)
        if not p:
            rows.append({"label": label, "value": "Not available (moment not identified)"})
            continue
        f = p["frame"]
        sm, hm = _mid(f, "l_sho", "r_sho"), _mid(f, "l_hip", "r_hip")
        if not sm or not hm or hm[1] <= sm[1]:
            rows.append({"label": label, "value": "Not available (shoulders or hips unclear)"})
            continue
        dx, dy = sm[0] - hm[0], hm[1] - sm[1]
        mag = round(math.degrees(math.atan2(abs(dx), dy)))
        if mag < 3:
            txt = "upright (under 3°)"
        elif angle == "side_on":
            txt = f"{mag}° " + ("direction unclear" if run_dir is None else "forward (towards the batter)" if dx * run_dir > 0 else "backward (away from the batter)")
        else:
            txt = f"{mag}° sideways, towards the {'right' if dx > 0 else 'left'} of the picture"
        rows.append({"label": label, "value": f"{txt} · {f['t']:.3f} s (frame {f['idx']})"})
        cand = (key == "release", f, sm, hm, mag, label)
        if best is None or cand[0]:
            best = cand
    d["details"] = rows
    if not best:
        d["reason"] = "Shoulders and hips weren't clearly visible at the key moments."
        return d
    _, f, sm, hm, mag, label = best
    _at(d, f)
    d["phase"] = label
    d["status"] = "measured"
    d["summary"] = f"Whole-trunk lean measured at {sum(1 for r in rows if not r['value'].startswith('Not available'))} of 3 key moments."
    d["details"].append({"label": "Lower-back bending", "value": "Not measured — ordinary video has no spine points, so only whole-trunk lean is shown."})
    for r_key in ("back_foot_contact", "front_foot_contact", "release"):
        p = ph.get(r_key)
        if p:
            g = p["frame"]
            gs, gh = _mid(g, "l_sho", "r_sho"), _mid(g, "l_hip", "r_hip")
            if gs and gh and gh[1] > gs[1]:
                d["marks"].append(_mark(g, f"Trunk {round(math.degrees(math.atan2(abs(gs[0] - gh[0]), gh[1] - gs[1])))}°",
                                        [(gh[:2], gs[:2], "#F59E0B"), (gh[:2], (gh[0], gs[1]), "#E2E8F0")]))
    d["_draw"] = (f, [(hm[:2], sm[:2], (11, 158, 245)), (hm[:2], (hm[0], sm[1]), (220, 220, 220))])
    return d


def _dashed(img, a, b, color, t):
    n = max(1, int(math.dist(a, b) // 14))
    for i in range(0, n, 2):
        p = (int(a[0] + (b[0] - a[0]) * i / n), int(a[1] + (b[1] - a[1]) * i / n))
        q = (int(a[0] + (b[0] - a[0]) * (i + 1) / n), int(a[1] + (b[1] - a[1]) * (i + 1) / n))
        cv2.line(img, p, q, color, t, cv2.LINE_AA)


def render(f, lines, label):
    img = pp.overlay(f["img"], f["kp"])
    t = max(4, img.shape[0] // 120)
    for a, b, c in lines:
        if b is None:
            cv2.circle(img, (int(a[0]), int(a[1])), t * 3, c, t, cv2.LINE_AA)
        elif c == (220, 220, 220):
            _dashed(img, a, b, c, max(2, t // 2))
        else:
            cv2.line(img, (int(a[0]), int(a[1])), (int(b[0]), int(b[1])), c, t, cv2.LINE_AA)
    txt = f"{label}  {f['t']:.3f}s  frame {f['idx']}"
    sc = img.shape[0] / 700
    (tw, th), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, sc, 2)
    cv2.rectangle(img, (8, 8), (20 + tw, 22 + th), (43, 19, 11), -1)
    cv2.putText(img, txt, (14, 14 + th), cv2.FONT_HERSHEY_SIMPLEX, sc, (255, 255, 255), 2, cv2.LINE_AA)
    return img


def assess(seq, ph, arm, angle, fps):
    """Returns (assessments, images) where images = [(key, raw_jpg, annotated_jpg)]."""
    rel = ph.get("release")
    ffc = (ph.get("front_foot_contact") or {}).get("frame")
    run_dir = run_direction(seq, rel["frame"]["t"], ffc if angle == "side_on" else None, arm) if rel else None
    bf, _ = back_foot(seq, ph, arm, angle, fps, run_dir)
    out = [bf, action_type(seq, ph, angle), shin_lead(ph, arm, angle, run_dir), trunk_lean(ph, arm, angle, run_dir)]
    imgs = []
    for d in out:
        dr = d.pop("_draw", None)
        if dr and d["status"] == "measured":
            f, lines = dr
            raw = cv2.imencode(".jpg", f["img"], [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tobytes()
            ann = cv2.imencode(".jpg", render(f, lines, d["name"]), [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tobytes()
            imgs.append((f"assess:{d['key']}", raw, ann))
    return out, imgs
