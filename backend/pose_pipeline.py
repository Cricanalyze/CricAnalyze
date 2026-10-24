"""CricAnalyze pose pipeline (ca-pose-v1). See METHODOLOGY for geometry, thresholds and scoring."""
import os, math, threading, base64
from pathlib import Path
import numpy as np
import cv2
import requests

PIPELINE_VERSION = "ca-pose-v1"
SCORE_VERSION = "ca-score-v1"
KP_OK = 0.5
KP_LOW = 0.3
MODELS_DIR = Path(__file__).parent / "models"
DET_FILE, DET_URL = "yolox_m_8xb8-300e_humanart-c2c7a14a.onnx", "https://download.openmmlab.com/mmpose/v1/projects/rtmposev1/onnx_sdk/yolox_m_8xb8-300e_humanart-c2c7a14a.zip"
POSE_FILE, POSE_URL = "rtmpose-m_simcc-body7_pt-body7_420e-256x192-e48f03d0_20230504.onnx", "https://download.openmmlab.com/mmpose/v1/projects/rtmposev1/onnx_sdk/rtmpose-m_simcc-body7_pt-body7_420e-256x192-e48f03d0_20230504.zip"
KP = dict(nose=0, l_sho=5, r_sho=6, l_elb=7, r_elb=8, l_wri=9, r_wri=10, l_hip=11, r_hip=12, l_knee=13, r_knee=14, l_ank=15, r_ank=16)
EDGES = [(5, 6), (5, 7), (7, 9), (6, 8), (8, 10), (5, 11), (6, 12), (11, 12), (11, 13), (13, 15), (12, 14), (14, 16), (0, 5), (0, 6)]
MODEL_META = {
    "local_rtmpose": {"pose_model": "RTMPose-m (body7, 256x192) — COCO-17 keypoints", "detector": "YOLOX-m (HumanArt)",
                      "runtime": "ONNX Runtime, CPU, CricAnalyze server", "library": "OpenMMLab rtmlib"},
    "runpod": {"pose_model": "Hosted endpoint (COCO-17 contract)", "runtime": "Remote GPU (AI_INFERENCE_ENDPOINT)"},
}

METHODOLOGY = {
    "coordinate_system": "2D image plane, pixels; origin top-left, x right, y down. No depth, no camera calibration.",
    "angle_method": "Joint angle at vertex B of keypoints A-B-C = arccos((BA·BC)/(|BA||BC|)), degrees, 0–180. Tilt angles are measured against image vertical/horizontal.",
    "normalisation": "Distances are divided by torso length (mid-shoulder to mid-hip, same frame) so they are scale-independent ('torso lengths').",
    "assumptions": ["Camera is static and roughly level.", "2D projection: angles are apparent angles and change with camera angle.",
                    "Bat and ball are not tracked; impact and release timing are inferred from hand/wrist trajectory."],
    "thresholds": {"keypoint_measure": KP_OK, "keypoint_min": KP_LOW},
    "metric_status": {"measured": "all required joints ≥ 0.5 confidence on a detected phase",
                      "measured_estimated_phase": "joints ≥ 0.5 but the phase frame is estimated — counts at half weight",
                      "low_confidence": "a required joint between 0.3 and 0.5 — shown, excluded from score",
                      "not_measurable": "joint missing, phase not identified or camera angle unsuitable — no value shown"},
    "scoring": "Each metric scores 100 inside its reference range, falling linearly to 0 at 'tolerance' beyond it. Overall = weighted mean of included metrics. "
               "A score is shown only if ≥3 metrics are included, they cover ≥60% of total weight and ≥2 phases were detected (not estimated). "
               "Reference ranges are configurable coaching heuristics, not validated population norms. Model confidence (keypoint confidence) is reported separately and is not a technique-quality signal.",
}

METRICS = {
    "batting": [
        {"key": "front_knee_angle", "name": "Front knee angle at impact", "phase": "impact", "unit": "°", "views": ["side_on"], "weight": 1.0, "ideal": [130, 170], "tol": 30},
        {"key": "hands_height_backlift", "name": "Hands height at top of backlift (above shoulders)", "phase": "backlift", "unit": "torso lengths", "views": ["side_on", "front_on"], "weight": 0.8, "ideal": [-0.2, 0.6], "tol": 0.6},
        {"key": "head_over_front_foot", "name": "Head position vs front foot at impact (horizontal offset)", "phase": "impact", "unit": "torso lengths", "views": ["side_on"], "weight": 1.0, "ideal": [0, 0.35], "tol": 0.5},
        {"key": "setup_balance", "name": "Setup balance (hips over base, horizontal offset)", "phase": "setup", "unit": "torso lengths", "views": ["side_on", "front_on"], "weight": 0.8, "ideal": [0, 0.25], "tol": 0.4},
        {"key": "shoulder_alignment", "name": "Shoulder line tilt at setup", "phase": "setup", "unit": "°", "views": ["front_on", "behind"], "weight": 0.6, "ideal": [0, 12], "tol": 20},
    ],
    "bowling": [
        {"key": "front_knee_angle", "name": "Front knee angle at release", "phase": "release", "unit": "°", "views": ["side_on"], "weight": 1.0, "ideal": [150, 185], "tol": 35},
        {"key": "trunk_tilt", "name": "Trunk tilt from vertical at release", "phase": "release", "unit": "°", "views": ["side_on", "front_on", "behind"], "weight": 0.8, "ideal": [0, 25], "tol": 25},
        {"key": "front_arm_elbow", "name": "Front (non-bowling) arm elbow angle at release", "phase": "release", "unit": "°", "views": ["side_on", "front_on"], "weight": 0.6, "ideal": [60, 140], "tol": 40},
        {"key": "release_height", "name": "Release hand height above head", "phase": "release", "unit": "torso lengths", "views": ["side_on", "front_on"], "weight": 0.8, "ideal": [0.4, 1.5], "tol": 0.6},
        {"key": "follow_through_balance", "name": "Follow-through balance (hips over base)", "phase": "follow_through", "unit": "torso lengths", "views": ["side_on", "front_on"], "weight": 0.8, "ideal": [0, 0.35], "tol": 0.5},
    ],
}
PHASES = {"batting": [("setup", "Setup"), ("backlift", "Backlift"), ("downswing", "Downswing"), ("impact", "Impact"), ("follow_through", "Follow-through")],
          "bowling": [("run_up", "Run-up"), ("gather", "Gather"), ("back_foot_contact", "Back-foot contact"), ("front_foot_contact", "Front-foot contact"), ("release", "Release & follow-through")]}


class PoseUnavailable(Exception):
    pass


_model, _lock = None, threading.Lock()


def provider():
    return os.environ.get("POSE_PROVIDER", "local_rtmpose")


def _local_model():
    global _model
    if _model is None:
        from rtmlib import Body
        det = str(MODELS_DIR / DET_FILE) if (MODELS_DIR / DET_FILE).exists() else DET_URL
        pose = str(MODELS_DIR / POSE_FILE) if (MODELS_DIR / POSE_FILE).exists() else POSE_URL
        _model = Body(det=det, det_input_size=(640, 640), pose=pose, pose_input_size=(192, 256), backend="onnxruntime", device="cpu")
    return _model


def _infer(imgs):
    """Returns per image a list of persons, each 17x[x,y,score]."""
    p = provider()
    if p == "local_rtmpose":
        with _lock:
            m = _local_model()
            out = []
            for im in imgs:
                k, s = m(im)
                out.append([[[float(k[i][j][0]), float(k[i][j][1]), float(s[i][j])] for j in range(17)] for i in range(len(k))])
            return out
    if p == "runpod":
        ep, key = os.environ.get("AI_INFERENCE_ENDPOINT"), os.environ.get("AI_INFERENCE_API_KEY")
        if not ep or not key:
            raise PoseUnavailable("GPU pose endpoint is not configured.")
        frames = [base64.b64encode(cv2.imencode(".jpg", im)[1].tobytes()).decode() for im in imgs]
        r = requests.post(ep, json={"input": {"frames": frames, "format": "coco17"}}, headers={"Authorization": f"Bearer {key}"}, timeout=180)
        r.raise_for_status()
        return [[pp["keypoints"] for pp in f.get("persons", [])] for f in r.json().get("output", {}).get("frames", [])]
    raise PoseUnavailable(f"Pose provider '{p}' is disabled.")


def _read(cap, idx, max_side=960):
    cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
    ok, f = cap.read()
    if not ok:
        return None
    h, w = f.shape[:2]
    s = max_side / max(h, w)
    return cv2.resize(f, (int(w * s), int(h * s))) if s < 1 else f


def _main_person(persons, prev_c):
    best, best_score = None, -1
    for kp in persons:
        pts = [(x, y) for x, y, s in kp if s >= KP_LOW]
        if len(pts) < 5:
            continue
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        area = (max(xs) - min(xs)) * (max(ys) - min(ys))
        c = (sum(xs) / len(xs), sum(ys) / len(ys))
        score = area / (1 + (math.dist(c, prev_c) / 200 if prev_c else 0))
        if score > best_score:
            best, best_score = kp, score
    return best


def _track(path):
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    coarse = sorted({int(i * (n - 1) / 15) for i in range(16)})
    frames = {}

    def run(idxs):
        imgs, keep = [], []
        for i in idxs:
            if i in frames:
                continue
            im = _read(cap, i)
            if im is not None:
                imgs.append(im)
                keep.append(i)
        res = _infer(imgs) if imgs else []
        for i, im, persons in zip(keep, imgs, res):
            frames[i] = {"idx": i, "t": round(i / fps, 2), "img": im, "persons": persons}

    run(coarse)
    seq = _select(frames)
    sp = _speeds(seq)
    if sp:
        t_peak = max(sp, key=lambda x: x[1])[0]["t"]
        step = max(1, int(round(fps / 8)))
        dense = list(range(max(0, int((t_peak - 1.6) * fps)), min(n, int((t_peak + 1.0) * fps)), step))
        run(dense)
    cap.release()
    return _select(frames), fps


def _select(frames):
    seq, prev = [], None
    for i in sorted(frames):
        f = frames[i]
        kp = _main_person(f["persons"], prev)
        f["kp"] = kp
        if kp:
            pts = [(x, y) for x, y, s in kp if s >= KP_LOW]
            prev = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
        seq.append(f)
    return seq


def P(f, name, thr=KP_LOW):
    k = f.get("kp")
    if not k:
        return None
    x, y, s = k[KP[name]]
    return (x, y, s) if s >= thr else None


def mid(a, b):
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, min(a[2], b[2])) if a and b else None


def torso(f):
    sm, hm = mid(P(f, "l_sho"), P(f, "r_sho")), mid(P(f, "l_hip"), P(f, "r_hip"))
    return math.dist(sm[:2], hm[:2]) if sm and hm else None


def angle3(a, b, c):
    v1, v2 = (a[0] - b[0], a[1] - b[1]), (c[0] - b[0], c[1] - b[1])
    n = math.hypot(*v1) * math.hypot(*v2)
    return math.degrees(math.acos(max(-1, min(1, (v1[0] * v2[0] + v1[1] * v2[1]) / n)))) if n else None


def wrists(f):
    ws = [w for w in (P(f, "l_wri"), P(f, "r_wri")) if w]
    return ws


def hands_up(f, side=None):
    sm, t = mid(P(f, "l_sho"), P(f, "r_sho")), torso(f)
    ws = [P(f, side)] if side else wrists(f)
    ws = [w for w in ws if w]
    if not sm or not t or not ws:
        return None
    return (sm[1] - min(w[1] for w in ws)) / t


def _speeds(seq):
    out, prev = [], None
    for f in seq:
        ws, t = wrists(f), torso(f)
        if not ws or not t:
            continue
        c = (sum(w[0] for w in ws) / len(ws), sum(w[1] for w in ws) / len(ws))
        if prev and f["t"] > prev[0]["t"]:
            out.append((f, math.dist(c, prev[1]) / t / (f["t"] - prev[0]["t"])))
        prev = (f, c)
    return out


def _ph(f, status, note=""):
    return {"frame": f, "status": status, "note": note}


def phases_batting(seq):
    v = [f for f in seq if wrists(f) and torso(f)]
    res = {k: None for k, _ in PHASES["batting"]}
    if not v:
        return res
    sp = _speeds(v)
    res["setup"] = _ph(v[0], "detected" if not sp or sp[0][1] < 0.6 else "estimated", "First frame with the player detected.")
    if not sp or max(s for _, s in sp) < 1.0:
        return res
    peak = max(sp, key=lambda x: x[1])[0]
    before = [f for f in v if f["t"] < peak["t"]]
    if before:
        bl = max(before, key=lambda f: hands_up(f) or -9)
        res["backlift"] = _ph(bl, "detected" if bl is not v[0] else "estimated", "Highest hand position before the fastest hand movement.")
    res["downswing"] = _ph(peak, "detected", "Fastest hand movement (wrist speed peak).")
    after = [f for f in v if peak["t"] < f["t"] <= peak["t"] + 0.5]
    if after:
        im = min(after, key=lambda f: hands_up(f) or 9)
        res["impact"] = _ph(im, "estimated", "Inferred from lowest hand point after the swing peak; bat and ball are not tracked.")
        ft = [f for f in v if f["t"] > im["t"]]
        if ft:
            fo = max(ft, key=lambda f: hands_up(f) or -9)
            res["follow_through"] = _ph(fo, "detected" if (hands_up(fo) or -9) > (hands_up(im) or 0) + 0.5 else "estimated", "Highest hand position after impact.")
    return res


def phases_bowling(seq):
    v = [f for f in seq if torso(f) and P(f, "nose")]
    res = {k: None for k, _ in PHASES["bowling"]}
    if not v:
        return res, None
    side_up = {s: max((hands_up(f, s) or -9) for f in v) for s in ("l_wri", "r_wri")}
    arm = max(side_up, key=side_up.get)
    if side_up[arm] < 0:
        return res, None
    rel = max(v, key=lambda f: hands_up(f, arm) or -9)
    above_head = P(rel, arm) and P(rel, arm)[1] < P(rel, "nose")[1]
    res["release"] = _ph(rel, "detected" if above_head else "estimated", "Bowling wrist at its highest point (ball release is not tracked).")
    front_ank, back_ank = ("r_ank", "l_ank") if arm == "l_wri" else ("l_ank", "r_ank")
    pre = [f for f in v if rel["t"] - 0.5 <= f["t"] <= rel["t"] and P(f, front_ank)]
    if pre:
        ffc = max(pre, key=lambda f: P(f, front_ank)[1])
        res["front_foot_contact"] = _ph(ffc, "estimated", "Front ankle at its lowest point before release.")
        pre2 = [f for f in v if ffc["t"] - 0.6 <= f["t"] < ffc["t"] and P(f, back_ank)]
        if pre2:
            bfc = max(pre2, key=lambda f: P(f, back_ank)[1])
            res["back_foot_contact"] = _ph(bfc, "estimated", "Back ankle at its lowest point before front-foot contact.")
            pre3 = [f for f in v if bfc["t"] - 0.8 <= f["t"] < bfc["t"] and len(wrists(f)) == 2]
            if pre3:
                sm = lambda f: mid(P(f, "l_sho"), P(f, "r_sho"))
                g = min(pre3, key=lambda f: sum(math.dist(w[:2], sm(f)[:2]) for w in wrists(f)) / torso(f) if sm(f) else 9)
                res["gather"] = _ph(g, "estimated", "Hands closest to the chest before back-foot contact.")
    first = v[0]
    if first["t"] < ((res["gather"] or res["back_foot_contact"] or res["release"])["frame"]["t"]):
        res["run_up"] = _ph(first, "estimated", "Earliest frame of the approach in this clip.")
    post = [f for f in v if f["t"] >= rel["t"] + 0.2]
    res["_follow_through"] = _ph(post[-1], "estimated", "Last frame after release.") if post else None
    return res, arm


def _metric(defn, angle_label, ph, compute):
    out = {k: defn[k] for k in ("key", "name", "unit", "phase")}
    out.update({"value": None, "confidence": None, "status": "not_measurable", "reason": ""})
    if angle_label not in defn["views"]:
        out["reason"] = f"Camera angle '{angle_label.replace('_', '-')}' doesn't support this measurement (needs {', '.join(v.replace('_', '-') for v in defn['views'])})."
        return out
    if not ph:
        out["reason"] = "Required movement phase was not identified in this video."
        return out
    r = compute(ph["frame"])
    if r is None:
        out["reason"] = "Required joints were not detected confidently."
        return out
    val, conf = r
    out["value"], out["confidence"] = round(val, 1 if out["unit"] == "°" else 2), round(conf, 2)
    out["t"] = ph["frame"]["t"]
    if conf < KP_OK:
        out["status"], out["reason"] = "low_confidence", "Some required joints had low detection confidence."
    else:
        out["status"] = "measured" if ph["status"] == "detected" else "measured_estimated_phase"
        out["reason"] = "" if ph["status"] == "detected" else "Phase frame is estimated."
    return out


def _leg(f, side):
    h, k, a = P(f, f"{side}_hip"), P(f, f"{side}_knee"), P(f, f"{side}_ank")
    return (angle3(h, k, a), min(h[2], k[2], a[2])) if h and k and a else None


def metrics_batting(ph, angle_label):
    setup, imp = (ph.get("setup") or {}).get("frame"), (ph.get("impact") or {}).get("frame")
    front = None
    if setup and imp:
        d = {s: math.dist(P(setup, f"{s}_ank")[:2], P(imp, f"{s}_ank")[:2]) for s in ("l", "r") if P(setup, f"{s}_ank") and P(imp, f"{s}_ank")}
        front = max(d, key=d.get) if d else None

    def knee(f):
        return _leg(f, front) if front else None

    def hands(f):
        h, sm = hands_up(f), mid(P(f, "l_sho"), P(f, "r_sho"))
        return (h, min([sm[2]] + [w[2] for w in wrists(f)])) if h is not None else None

    def head(f):
        n, a, t = P(f, "nose"), P(f, f"{front}_ank") if front else None, torso(f)
        return (abs(n[0] - a[0]) / t, min(n[2], a[2])) if n and a and t else None

    def balance(f):
        hm, am, t = mid(P(f, "l_hip"), P(f, "r_hip")), mid(P(f, "l_ank"), P(f, "r_ank")), torso(f)
        return (abs(hm[0] - am[0]) / t, min(hm[2], am[2])) if hm and am and t else None

    def shoulders(f):
        l, r, t = P(f, "l_sho"), P(f, "r_sho"), torso(f)
        if not l or not r or not t or math.dist(l[:2], r[:2]) / t < 0.35:
            return None
        a = abs(math.degrees(math.atan2(r[1] - l[1], r[0] - l[0])))
        return (min(a, 180 - a), min(l[2], r[2]))

    fns = {"front_knee_angle": knee, "hands_height_backlift": hands, "head_over_front_foot": head, "setup_balance": balance, "shoulder_alignment": shoulders}
    return [_metric(d, angle_label, ph.get(d["phase"]), fns[d["key"]]) for d in METRICS["batting"]]


def metrics_bowling(ph, arm, angle_label):
    s = arm[0] if arm else None
    o = {"l": "r", "r": "l"}.get(s)

    def knee(f):
        return _leg(f, o) if o else None

    def trunk(f):
        sm, hm = mid(P(f, "l_sho"), P(f, "r_sho")), mid(P(f, "l_hip"), P(f, "r_hip"))
        return (abs(math.degrees(math.atan2(sm[0] - hm[0], hm[1] - sm[1]))), min(sm[2], hm[2])) if sm and hm else None

    def front_arm(f):
        if not o:
            return None
        a, b, c = P(f, f"{o}_sho"), P(f, f"{o}_elb"), P(f, f"{o}_wri")
        return (angle3(a, b, c), min(a[2], b[2], c[2])) if a and b and c else None

    def rel_h(f):
        w, n, t = P(f, f"{s}_wri") if s else None, P(f, "nose"), torso(f)
        return ((n[1] - w[1]) / t, min(w[2], n[2])) if w and n and t else None

    def ft_bal(f):
        hm, am, t = mid(P(f, "l_hip"), P(f, "r_hip")), mid(P(f, "l_ank"), P(f, "r_ank")), torso(f)
        return (abs(hm[0] - am[0]) / t, min(hm[2], am[2])) if hm and am and t else None

    fns = {"front_knee_angle": knee, "trunk_tilt": trunk, "front_arm_elbow": front_arm, "release_height": rel_h, "follow_through_balance": ft_bal}
    phmap = {**ph, "follow_through": ph.get("_follow_through")}
    return [_metric(d, angle_label, phmap.get(d["phase"]), fns[d["key"]]) for d in METRICS["bowling"]]


def score(kind, metrics, phases):
    defs = {d["key"]: d for d in METRICS[kind]}
    total = sum(d["weight"] for d in defs.values())
    inc, wsum, acc = [], 0, 0
    for m in metrics:
        if m["status"] not in ("measured", "measured_estimated_phase"):
            continue
        d = defs[m["key"]]
        w = d["weight"] * (0.5 if m["status"] == "measured_estimated_phase" else 1)
        lo, hi = d["ideal"]
        dist = 0 if lo <= m["value"] <= hi else min(abs(m["value"] - lo), abs(m["value"] - hi))
        s = max(0.0, 100 * (1 - dist / d["tol"]))
        m["metric_score"] = round(s)
        inc.append(m["key"])
        wsum += w
        acc += w * s
    detected = sum(1 for p in phases if p["status"] == "detected")
    coverage = wsum / total
    ok = len(inc) >= 3 and coverage >= 0.6 and detected >= 2
    return {"value": round(acc / wsum) if ok else None, "version": SCORE_VERSION, "included": inc, "coverage": round(coverage, 2), "detected_phases": detected,
            "reason": None if ok else "Insufficient evidence to calculate a reliable score.",
            "requirements": "≥3 included metrics, ≥60% weight coverage, ≥2 detected phases"}


def quality(seq, meta, angle_label):
    valid = [f for f in seq if f.get("kp")]
    rate = len(valid) / len(seq) if seq else 0
    hts, confs, legs = [], [], 0
    for f in valid:
        ys = [y for x, y, s in f["kp"] if s >= KP_LOW]
        hts.append((max(ys) - min(ys)) / f["img"].shape[0])
        legs += any(f["kp"][i][2] >= KP_LOW for i in (15, 16))
        confs.append(float(np.mean([f["kp"][i][2] for i in (5, 6, 11, 12, 13, 14, 15, 16)])))
    h, c = (float(np.median(hts)) if hts else 0), (float(np.median(confs)) if confs else 0)
    issues = []
    if min(meta["width"], meta["height"]) < 480:
        issues.append(f"Low resolution ({min(meta['width'], meta['height'])}p) reduces keypoint precision. Record at 720p or higher.")
    if meta["fps"] < 24:
        issues.append(f"Low frame rate ({meta['fps']} fps): fast phases may fall between frames. Record at 30–60 fps.")
    if rate < 0.6:
        issues.append(f"Player detected in only {round(rate * 100)}% of analysed frames.")
    legs_hidden = bool(valid) and legs / len(valid) < 0.5
    if legs_hidden:
        issues.append("Lower body (knees/ankles) hidden or out of frame in most frames, so leg-based metrics cannot be measured. Keep the whole body in view.")
    elif valid and h < 0.3:
        issues.append(f"Player appears distant (about {round(h * 100)}% of frame height). Move closer so the full body fills most of the frame.")
    if valid and c < KP_OK:
        issues.append(f"Body partly obstructed or unclear (median key-joint confidence {c:.2f}).")
    if angle_label == "other":
        issues.append("Camera angle is 'other' — most angle-based metrics need side-on or front-on footage.")
    return {"frames_analysed": len(seq), "detection_rate": round(rate, 2), "player_height_frac": round(h, 2), "keypoint_confidence": round(c, 2),
            "issues": issues, "usable": rate >= 0.4 and h >= 0.12}


def overlay(img, kp):
    out = img.copy()
    t = max(2, out.shape[0] // 300)
    for a, b in EDGES:
        if kp[a][2] >= KP_LOW and kp[b][2] >= KP_LOW:
            cv2.line(out, (int(kp[a][0]), int(kp[a][1])), (int(kp[b][0]), int(kp[b][1])), (216, 180, 0), t, cv2.LINE_AA)
    for x, y, s in kp:
        if s >= KP_LOW:
            cv2.circle(out, (int(x), int(y)), t + 2, (129, 185, 16) if s >= KP_OK else (36, 191, 251), -1, cv2.LINE_AA)
    return out


def analyse_video(path, kind, angle_label, meta):
    """Returns (result_dict, phase_images) — phase_images: list of (phase_key, raw_jpg, overlay_jpg or None)."""
    seq, fps = _track(path)
    q = quality(seq, meta, angle_label)
    base = {"provider": provider(), "model": MODEL_META.get(provider(), {}), "pipeline_version": PIPELINE_VERSION, "methodology": METHODOLOGY, "quality": q}
    if not q["usable"]:
        return {**base, "status": "insufficient", "phases": [{"key": k, "name": n, "status": "unavailable", "note": "Player not reliably detected."} for k, n in PHASES[kind]],
                "metrics": [{**{k: d[k] for k in ("key", "name", "unit", "phase")}, "value": None, "status": "not_measurable", "reason": "Player not reliably detected in this video."} for d in METRICS[kind]],
                "score": {"value": None, "version": SCORE_VERSION, "reason": "Insufficient evidence to calculate a reliable score."}}, []
    arm = None
    if kind == "batting":
        ph = phases_batting(seq)
        mets = metrics_batting(ph, angle_label)
    else:
        ph, arm = phases_bowling(seq)
        mets = metrics_bowling(ph, arm, angle_label)
    phases, imgs = [], []
    for k, n in PHASES[kind]:
        p = ph.get(k)
        if not p:
            phases.append({"key": k, "name": n, "status": "unavailable", "note": "Not identified in this video."})
            continue
        f = p["frame"]
        kconf = round(float(np.mean([s for _, _, s in f["kp"]])), 2)
        phases.append({"key": k, "name": n, "status": p["status"], "note": p["note"], "t": f["t"], "keypoint_confidence": kconf,
                       "keypoints": [[round(x, 1), round(y, 1), round(s, 3)] for x, y, s in f["kp"]], "frame_size": [f["img"].shape[1], f["img"].shape[0]]})
        raw = cv2.imencode(".jpg", f["img"], [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tobytes()
        ov = cv2.imencode(".jpg", overlay(f["img"], f["kp"]), [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tobytes()
        imgs.append((k, raw, ov))
    sc = score(kind, mets, phases)
    status = "measured" if any(m["status"].startswith("measured") for m in mets) else "insufficient"
    return {**base, "status": status, "bowling_arm": {"l_wri": "left", "r_wri": "right"}.get(arm), "phases": phases, "metrics": mets, "score": sc}, imgs
