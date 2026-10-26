"""Ultralytics Platform hosted inference (YOLO26n detect + YOLO26n-pose). Key stays server-side."""
import os, time, threading
import cv2
import requests

BASE = "https://platform.ultralytics.com/api/models/ultralytics/yolo26"
_lock = threading.Lock()
_last = [0.0]


class UltralyticsError(Exception):
    pass


def configured():
    return bool(os.environ.get("ULTRALYTICS_API_KEY"))


def _url(task):
    if task == "pose":
        return os.environ.get("ULTRALYTICS_POSE_URL") or f"{BASE}/yolo26n-pose/predict"
    return os.environ.get("ULTRALYTICS_DETECT_URL") or f"{BASE}/yolo26n/predict"


def _interval():
    return 60.0 / max(1.0, float(os.environ.get("ULTRALYTICS_RPM", "20")))


def predict(img, task="detect", conf=0.25, imgsz=640):
    """img: BGR ndarray. Returns list of results (name, confidence, box, keypoints?) in img pixel coords."""
    key = os.environ.get("ULTRALYTICS_API_KEY")
    if not key:
        raise UltralyticsError("Ultralytics API key is not configured.")
    jpg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])[1].tobytes()
    data = {"conf": str(conf), "iou": "0.7", "imgsz": str(imgsz), "normalize": "false"}
    for attempt in range(4):
        with _lock:
            wait = _last[0] + _interval() - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            _last[0] = time.monotonic()
        r = requests.post(_url(task), headers={"Authorization": f"Bearer {key}"}, data=data,
                          files={"file": ("frame.jpg", jpg, "image/jpeg")}, timeout=60)
        if r.status_code == 429:
            time.sleep(min(float(r.headers.get("Retry-After") or 5), 30))
            continue
        if r.status_code in (401, 403):
            raise UltralyticsError("Ultralytics rejected the API key.")
        if r.status_code >= 400:
            raise UltralyticsError(f"Ultralytics inference failed (HTTP {r.status_code}).")
        imgs = r.json().get("images") or [{}]
        return imgs[0].get("results") or []
    raise UltralyticsError("Ultralytics rate limit reached; try again later.")


def pose_persons(img):
    """Persons as 17x[x, y, score] (COCO order), matching the local pose contract."""
    out = []
    for p in predict(img, "pose", conf=0.25, imgsz=640):
        k = p.get("keypoints") or {}
        xs, ys, vs = k.get("x") or [], k.get("y") or [], k.get("visible") or []
        if p.get("name", "person") == "person" and len(xs) == 17:
            out.append([[float(xs[j]), float(ys[j]), float(vs[j] if j < len(vs) else 0)] for j in range(17)])
    return out


def balls(img, conf=0.15, imgsz=1280):
    """Sports-ball detections as (cx, cy, w, h, conf) in img pixels."""
    res = []
    for d in predict(img, "detect", conf=conf, imgsz=imgsz):
        if d.get("name") != "sports ball":
            continue
        b = d["box"]
        res.append(((b["x1"] + b["x2"]) / 2, (b["y1"] + b["y2"]) / 2, b["x2"] - b["x1"], b["y2"] - b["y1"], float(d["confidence"])))
    return res
