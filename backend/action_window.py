"""Find the main movement in a clip of any length using local frame differencing (no hosted inference)."""
import cv2
import numpy as np

FULL_IF_UNDER_S = 12.0
BEFORE_S, AFTER_S = 5.0, 5.0
SAMPLES_PER_S = 8


def find(path):
    """Returns (t0, t1, method) in seconds. Short clips are analysed in full."""
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    dur = n / fps if n else 0
    if dur <= FULL_IF_UNDER_S:
        cap.release()
        return 0.0, round(dur, 3), "full_clip"
    step = max(1, int(round(fps / SAMPLES_PER_S)))
    prev, ts, energy, i = None, [], [], 0
    while True:
        if not cap.grab():
            break
        if i % step == 0:
            ok, f = cap.retrieve()
            if ok:
                g = cv2.GaussianBlur(cv2.cvtColor(cv2.resize(f, (160, 90)), cv2.COLOR_BGR2GRAY), (5, 5), 0)
                if prev is not None:
                    ts.append(i / fps)
                    energy.append(float(np.mean(cv2.absdiff(g, prev))))
                prev = g
        i += 1
    cap.release()
    if len(energy) < 4:
        return 0.0, round(dur, 3), "full_clip"
    e = np.array(energy)
    k = max(1, int(3 * SAMPLES_PER_S))
    smooth = np.convolve(e, np.ones(k) / k, mode="same")
    c = ts[int(np.argmax(smooth))]
    t0 = max(0.0, min(c - BEFORE_S, dur - BEFORE_S - AFTER_S))
    return round(t0, 3), round(min(dur, t0 + BEFORE_S + AFTER_S), 3), "most_movement"
