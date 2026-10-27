import sys, json, time
sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv; load_dotenv("/app/backend/.env")
import cv2, pose_pipeline, action_window
path, angle = sys.argv[1], sys.argv[2]
c = cv2.VideoCapture(path); meta = {"width": int(c.get(3)), "height": int(c.get(4)), "fps": c.get(5), "duration_s": c.get(7) / c.get(5)}
win = action_window.find(path); t = time.time()
r, imgs = pose_pipeline.analyse_video(path, "bowling", angle, meta, win[:2])
print("TIME", round(time.time() - t), "s window", win, "arm", r.get("bowling_arm"), "frames", len(r.get("pose_track", [])))
print("PHASES", [(p["key"], p.get("t"), p.get("idx"), p["status"]) for p in r["phases"]])
for a in r.get("bowling_assessments", []):
    print("ASSESS", a["key"], a["status"], a.get("t"), a.get("idx"), "|", a["summary"] or a["reason"])
    for d in a["details"]: print("    ", d["label"], ":", d["value"])
out = sys.argv[3]
for k, raw, ov in imgs:
    if k.startswith("assess:"): open(f"{out}_{k[7:]}.jpg", "wb").write(ov)
