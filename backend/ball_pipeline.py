"""CricAnalyze ball detection & tracking (ca-ball-v1). Independent of pose; any failure yields status 'unavailable', never a guessed ball."""
import os, math, threading
from pathlib import Path
import numpy as np
import cv2

BALL_VERSION = "ca-ball-v1"
MODELS_DIR = Path(__file__).parent / "models"
MODEL_FILE = os.environ.get("BALL_MODEL_FILE", "yolox_s.onnx")
FULL_EVERY = 4
COCO_SPORTS_BALL = 32
MAX_WINDOW_S = 15.0
MAX_FRAMES = 900
CAND_MIN = 0.15
START_MIN = 0.3
MAX_GAP = 6
MIN_TRACK_PTS = 4
NOT_DETECTED = "Ball not reliably detected in this video."
MODEL_META = {"local_yolox_coco": {"detector": f"YOLOX ({MODEL_FILE}, COCO class 'sports ball')", "runtime": "ONNX Runtime, CPU, CricAnalyze server",
                                   "note": "General-purpose detector, not cricket-specific: small, distant or blurred balls are often missed."},
              "ultralytics_yolo26": {"detector": "Ultralytics YOLO26n (COCO class 'sports ball')", "runtime": "Ultralytics Platform hosted inference",
                                     "note": "General-purpose detector, not cricket-specific: small, distant or blurred balls are often missed."}}
CLOUD_MAX_FRAMES = int(os.environ.get("ULTRALYTICS_BALL_MAX_FRAMES", "60"))
METHOD = {
    "sampling": f"Every original frame in a window of up to {MAX_WINDOW_S:.0f}s (frame stride raised only if the window exceeds {MAX_FRAMES} frames); timestamps = frame index / FPS.",
    "detection": f"Every processed frame: a native-resolution crop (detector input size) around the predicted ball position or the player. "
                 f"Full-frame pass (resized) every {FULL_EVERY}th frame and whenever no ball is being tracked. Candidates kept at detector confidence >= {CAND_MIN}.",
    "tracking": f"Greedy nearest-neighbour association with a constant-velocity prediction and a distance gate; a track ends after {MAX_GAP} missed frames. "
                f"A track is confirmed only with >= {MIN_TRACK_PTS} observed detections, mean confidence >= {START_MIN} and real movement. Unconfirmed candidates are never drawn.",
    "estimated": f"Gaps of up to {MAX_GAP} frames inside a confirmed track are linearly interpolated and labelled 'estimated'. Gaps between tracks are not bridged.",
    "events": "Ball release and bat contact are not determined: a ball near the bat or hand is not treated as contact or release. Ball speed is not measured.",
}

_sess, _lock = None, threading.Lock()


def provider():
    return os.environ.get("BALL_PROVIDER", "local_yolox_coco")


def marker_bgr():
    h = os.environ.get("BALL_MARKER_COLOR", "#FFE600").lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (b, g, r)


class BallUnavailable(Exception):
    pass


def _session():
    global _sess
    if _sess is None:
        import onnxruntime as ort
        p = MODELS_DIR / MODEL_FILE
        if not p.exists():
            raise BallUnavailable("Ball-detection model file is not installed on the server.")
        o = ort.SessionOptions()
        o.intra_op_num_threads = 4
        _sess = ort.InferenceSession(str(p), o, providers=["CPUExecutionProvider"])
    return _sess


def _size():
    return int(_session().get_inputs()[0].shape[2])


_GRID = {}


def _grids(S):
    if S not in _GRID:
        gs, ss = [], []
        for s in (8, 16, 32):
            n = S // s
            xv, yv = np.meshgrid(np.arange(n), np.arange(n))
            gs.append(np.stack((xv, yv), 2).reshape(-1, 2))
            ss.append(np.full((n * n, 1), s))
        _GRID[S] = (np.concatenate(gs).astype(np.float32), np.concatenate(ss).astype(np.float32))
    return _GRID[S]


def _detect(img):
    """Returns [(cx, cy, w, h, conf)] in img pixel coords for COCO 'sports ball'."""
    S = _size()
    h, w = img.shape[:2]
    r = min(S / h, S / w)
    pad = np.full((S, S, 3), 114, np.uint8)
    pad[: int(h * r), : int(w * r)] = cv2.resize(img, (int(w * r), int(h * r)), interpolation=cv2.INTER_LINEAR)
    x = pad.transpose(2, 0, 1)[None].astype(np.float32)
    out = _session().run(None, {"images": x})[0][0]
    conf = out[:, 4] * out[:, 5 + COCO_SPORTS_BALL]
    keep = conf >= CAND_MIN
    if not keep.any():
        return []
    g, s = _grids(S)
    o, g, s, conf = out[keep], g[keep], s[keep], conf[keep]
    xy = (o[:, :2] + g) * s / r
    wh = np.exp(o[:, 2:4]) * s / r
    dets = sorted(zip(xy[:, 0], xy[:, 1], wh[:, 0], wh[:, 1], conf), key=lambda d: -d[4])
    res = []
    for d in dets:
        if all(math.dist(d[:2], e[:2]) > max(d[2], 6) for e in res):
            res.append(tuple(float(v) for v in d))
        if len(res) >= 5:
            break
    return res


def _player_box(pose_track, t, W, H):
    if not pose_track:
        return None
    p = min(pose_track, key=lambda f: abs(f["t"] - t))
    pts = [(x * W, y * H) for x, y, s in p["kp"] if s >= 0.3]
    if len(pts) < 5:
        return None
    xs, ys = [a for a, _ in pts], [b for _, b in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def _merge(a, b):
    out = list(a)
    for d in b:
        hit = next((i for i, e in enumerate(out) if math.dist(d[:2], e[:2]) < max(d[2], e[2], 6)), None)
        if hit is None:
            out.append(d)
        elif d[4] > out[hit][4]:
            out[hit] = d
    return out


def _plausible(d, W, H, pbox):
    cx, cy, w, h, c = d
    if max(w, h) > 0.08 * H or min(w, h) < 2 or not (0.4 <= w / max(h, 1e-6) <= 2.5):
        return False
    return True


def _track(cands, diag):
    tracks = []
    for fi in sorted(cands):
        live = [t for t in tracks if fi - t["pts"][-1][0] <= MAX_GAP]
        used = set()
        for t in sorted(live, key=lambda t: -len(t["pts"])):
            lf, lx, ly = t["pts"][-1][:3]
            vx, vy = t["v"]
            gap = fi - lf
            px, py = lx + vx * gap, ly + vy * gap
            gate = max(0.03 * diag, 2.5 * math.hypot(vx, vy)) * (1 + 0.4 * (gap - 1))
            best = None
            for j, d in enumerate(cands[fi]):
                if j in used:
                    continue
                dist = math.dist((px, py), d[:2])
                if dist <= gate and (best is None or dist < best[0]):
                    best = (dist, j)
            if best:
                j = best[1]
                used.add(j)
                d = cands[fi][j]
                t["v"] = ((d[0] - lx) / gap, (d[1] - ly) / gap)
                t["pts"].append((fi, d[0], d[1], d[4], d[2], d[3]))
        for j, d in enumerate(cands[fi]):
            if j not in used and d[4] >= START_MIN:
                tracks.append({"pts": [(fi, d[0], d[1], d[4], d[2], d[3])], "v": (0.0, 0.0)})
    return tracks


def _confirmed(t, diag):
    p = t["pts"]
    if len(p) < MIN_TRACK_PTS or np.mean([x[3] for x in p]) < START_MIN:
        return False
    span = max(math.dist(a[1:3], b[1:3]) for a in p for b in (p[0], p[-1]))
    return span >= 0.02 * diag


def _gap_reason(pt, W, H, pbox, speed):
    _, x, y, _, w, h = pt
    m = 0.05
    if x < W * m or x > W * (1 - m) or y < H * m or y > H * (1 - m):
        return "Likely left the frame."
    if pbox:
        x0, y0, x1, y1 = pbox
        ex = 0.25 * (x1 - x0)
        if x0 - ex <= x <= x1 + ex and y0 - ex <= y <= y1 + ex:
            return "Likely occluded by the player or bat."
    if max(w, h) < 7:
        return "Ball too small in the frame to detect reliably."
    if speed > 0.02 * math.hypot(W, H):
        return "Likely motion blur at high ball speed."
    return "Not detected (blur, lighting or background)."


def analyse(path, meta, pose_track=None, t_center=None):
    p = provider()
    if p == "disabled":
        raise BallUnavailable("Ball detection is disabled on this server.")
    if p not in MODEL_META:
        raise BallUnavailable(f"Ball provider '{p}' is not configured.")
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    W, H = int(cap.get(3)), int(cap.get(4))
    diag = math.hypot(W, H)
    dur = n / fps
    if dur > MAX_WINDOW_S:
        c = t_center if t_center is not None else dur / 2
        t0 = max(0.0, min(dur - MAX_WINDOW_S, c - MAX_WINDOW_S / 2))
    else:
        t0 = 0.0
    f0, f1 = int(t0 * fps), min(n, int((t0 + MAX_WINDOW_S) * fps))
    stride = max(1, math.ceil((f1 - f0) / MAX_FRAMES))
    method = METHOD
    if p == "ultralytics_yolo26":
        c = t_center if t_center is not None else dur / 2
        f0 = max(0, min(n - CLOUD_MAX_FRAMES, int(c * fps) - CLOUD_MAX_FRAMES // 2))
        f1, stride = min(n, f0 + CLOUD_MAX_FRAMES), 1
        method = {**METHOD, "sampling": f"Up to {CLOUD_MAX_FRAMES} consecutive original frames centred on the fastest hand movement (hosted inference is rate-limited); timestamps = frame index / FPS.",
                  "detection": f"Every processed frame: full frame sent to Ultralytics YOLO26n at 1280 px. Candidates kept at detector confidence >= {CAND_MIN}."}
        cands, processed = _gather_cloud(cap, f0, f1, W, H, pose_track, fps)
    else:
        cands, processed = _gather_local(cap, f0, f1, stride, W, H, pose_track, fps)
    cap.release()
    return _finalize(cands, processed, f0, f1, stride, fps, W, H, diag, pose_track, p, method)


def _gather_cloud(cap, f0, f1, W, H, pose_track, fps):
    from ultralytics_client import balls, UltralyticsError
    cap.set(cv2.CAP_PROP_POS_FRAMES, f0)
    cands, processed = {}, 0
    for fi in range(f0, f1):
        ok, img = cap.read()
        if not ok:
            break
        processed += 1
        try:
            d = balls(img, CAND_MIN, 1280)
        except UltralyticsError as e:
            raise BallUnavailable(str(e))
        d = [x for x in d if _plausible(x, W, H, _player_box(pose_track, fi / fps, W, H))]
        if d:
            cands[fi] = d
    return cands, processed


def _gather_local(cap, f0, f1, stride, W, H, pose_track, fps):
    cap.set(cv2.CAP_PROP_POS_FRAMES, f0)
    cands, processed, fi, pred, last_hit = {}, 0, f0, None, -99
    with _lock:
        S = _size()
        nx, ny = math.ceil(W / S), math.ceil(H / S)
        tiles = [(S / 2 + i * (W - S) / max(1, nx - 1), S / 2 + j * (H - S) / max(1, ny - 1)) for j in range(ny) for i in range(nx)] if nx * ny > 1 else []
        while fi < f1:
            ok, img = cap.read()
            if not ok:
                break
            if (fi - f0) % stride == 0:
                processed += 1
                t = fi / fps
                pbox = _player_box(pose_track, t, W, H)
                tracking = fi - last_hit <= 3
                small = W <= S * 1.2 and H <= S * 1.2
                d = _detect(img) if small or processed % FULL_EVERY == 1 or (not tracking and processed % 2 == 1) else []
                if pred and tracking:
                    cx, cy = pred
                elif tiles and processed % 2 == 0:
                    cx, cy = tiles[(processed // 2) % len(tiles)]
                else:
                    cx, cy = ((pbox[0] + pbox[2]) / 2, (pbox[1] + pbox[3]) / 2) if pbox else (W / 2, H / 2)
                if not small:
                    x0, y0 = int(min(max(0, cx - S / 2), max(0, W - S))), int(min(max(0, cy - S / 2), max(0, H - S)))
                    crop = img[y0:y0 + S, x0:x0 + S]
                    d = _merge(d, [(a + x0, b + y0, w, h, c) for a, b, w, h, c in _detect(crop)])
                d = [x for x in d if _plausible(x, W, H, pbox)]
                if d:
                    cands[fi] = d
                    best = max(d, key=lambda x: x[4])
                    if best[4] >= START_MIN:
                        pred, last_hit = (best[0], best[1]), fi
            fi += 1
    return cands, processed


def _finalize(cands, processed, f0, f1, stride, fps, W, H, diag, pose_track, p, method):
    tracks = [t for t in _track(cands, diag) if _confirmed(t, diag)]
    tracks.sort(key=lambda t: t["pts"][0][0])
    dets, gaps = [], []
    for ti, t in enumerate(tracks):
        pts = t["pts"]
        for a, b in zip(pts, pts[1:]):
            dets.append(_det(a, fps, W, H, ti, "observed"))
            for k in range(1, b[0] - a[0]):
                if (a[0] + k - f0) % stride:
                    continue
                r = k / (b[0] - a[0])
                dets.append({"frame": a[0] + k, "t": round((a[0] + k) / fps, 3), "cx": round(a[1] + (b[1] - a[1]) * r, 1), "cy": round(a[2] + (b[2] - a[2]) * r, 1),
                             "x": round((a[1] + (b[1] - a[1]) * r) / W, 4), "y": round((a[2] + (b[2] - a[2]) * r) / H, 4), "w": None, "h": None, "conf": None,
                             "track_id": ti, "status": "estimated"})
        dets.append(_det(pts[-1], fps, W, H, ti, "observed"))
        last = pts[-1]
        speed = math.hypot(*t["v"])
        nxt = tracks[ti + 1]["pts"][0][0] if ti + 1 < len(tracks) else f1
        if nxt - last[0] > MAX_GAP:
            gaps.append({"t_from": round(last[0] / fps, 2), "t_to": round(nxt / fps, 2) if ti + 1 < len(tracks) else None,
                         "reason": _gap_reason(last, W, H, _player_box(pose_track, last[0] / fps, W, H), speed)})
    obs = [d for d in dets if d["status"] == "observed"]
    raw_cands = sum(len(v) for v in cands.values())
    lim = []
    if not obs:
        lim.append(NOT_DETECTED)
        if raw_cands:
            lim.append(f"{raw_cands} weak or isolated candidate detections were rejected as unreliable and are not shown.")
    if min(W, H) < 720:
        lim.append("Resolution below 720p makes the ball only a few pixels wide.")
    if fps < 50:
        lim.append(f"At {round(fps)} fps a fast ball moves far between frames and is often motion-blurred.")
    best = max(obs, key=lambda d: d["conf"]) if obs else None
    return {"status": "tracked" if obs else "not_detected", "version": BALL_VERSION, "provider": p, "model": MODEL_META[p], "method": method,
            "message": None if obs else NOT_DETECTED, "fps": round(fps, 3), "frame_size": [W, H], "window": [round(f0 / fps, 2), round(f1 / fps, 2)], "stride": stride,
            "frames_processed": processed, "frames_detected": len(obs), "coverage": round(len(obs) / processed, 3) if processed else 0,
            "tracks": len(tracks), "rejected_candidates": raw_cands - len(obs) if raw_cands >= len(obs) else 0,
            "best": {"t": best["t"], "conf": best["conf"], "frame": best["frame"]} if best else None,
            "mean_conf": round(float(np.mean([d["conf"] for d in obs])), 2) if obs else None,
            "detections": sorted(dets, key=lambda d: d["frame"]), "gaps": gaps, "limitations": lim,
            "events": {"release": None, "contact": None, "note": METHOD["events"]}}


def _det(p, fps, W, H, ti, status):
    fi, x, y, c, w, h = p
    return {"frame": fi, "t": round(fi / fps, 3), "cx": round(x, 1), "cy": round(y, 1), "x": round(x / W, 4), "y": round(y / H, 4),
            "w": round(w, 1), "h": round(h, 1), "conf": round(c, 2), "track_id": ti, "status": status}


def draw_marker(img, det, scale=1.0, trail=()):
    """Draw ring + 'BALL' pointer at the detection's real coordinates (det in original px; img may be resized by `scale`)."""
    out = img.copy()
    col = marker_bgr()
    H, W = out.shape[:2]
    for a, b in zip(trail, trail[1:]):
        p1, p2 = (int(a["cx"] * scale), int(a["cy"] * scale)), (int(b["cx"] * scale), int(b["cy"] * scale))
        if a["status"] == "estimated" or b["status"] == "estimated":
            n = max(1, int(math.dist(p1, p2) // 8))
            for k in range(0, n, 2):
                q1 = (int(p1[0] + (p2[0] - p1[0]) * k / n), int(p1[1] + (p2[1] - p1[1]) * k / n))
                q2 = (int(p1[0] + (p2[0] - p1[0]) * (k + 1) / n), int(p1[1] + (p2[1] - p1[1]) * (k + 1) / n))
                cv2.line(out, q1, q2, col, 2, cv2.LINE_AA)
        else:
            cv2.line(out, p1, p2, col, 2, cv2.LINE_AA)
    cx, cy = int(det["cx"] * scale), int(det["cy"] * scale)
    r = max(10, int(max(det.get("w") or 8, det.get("h") or 8) * scale * 0.9))
    cv2.circle(out, (cx, cy), r + 2, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.circle(out, (cx, cy), r, col, 2, cv2.LINE_AA)
    label = f"BALL {det['conf']:.2f}" if det.get("conf") is not None else "BALL (est.)"
    fs = max(0.45, H / 1100)
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, fs, 2)
    lx = cx + 4 * r if cx + 4 * r + tw + 10 < W else cx - 4 * r - tw - 10
    ly = cy - 4 * r if cy - 4 * r - th - 8 > 0 else cy + 4 * r + th
    lx, ly = max(2, lx), max(th + 8, min(H - 4, ly))
    ax = lx if lx > cx else lx + tw + 10
    cv2.line(out, (ax, ly - th // 2 - 4), (int(cx + (ax - cx) * r / max(1, math.dist((ax, ly), (cx, cy)))), int(cy + (ly - th // 2 - 4 - cy) * r / max(1, math.dist((ax, ly), (cx, cy))))), col, 2, cv2.LINE_AA)
    cv2.rectangle(out, (lx, ly - th - 8), (lx + tw + 10, ly), col, -1)
    cv2.putText(out, label, (lx + 5, ly - 5), cv2.FONT_HERSHEY_SIMPLEX, fs, (0, 0, 0), 2, cv2.LINE_AA)
    return out


def phase_marker(ball, frame_idx, fps_pose=None):
    """Observed detection exactly on this frame (no guessing from neighbours)."""
    if not ball or ball.get("status") != "tracked":
        return None, []
    d = next((x for x in ball["detections"] if x["frame"] == frame_idx and x["status"] == "observed"), None)
    if not d:
        return None, []
    trail = [x for x in ball["detections"] if x["track_id"] == d["track_id"] and frame_idx - 8 <= x["frame"] <= frame_idx]
    return d, trail
