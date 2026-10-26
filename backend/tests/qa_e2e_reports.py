"""QA e2e: log in, upload clips, run analyses sequentially, fetch reports + PDFs. Run in background."""
import os, sys, time, uuid, json, requests
BASE = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0] + "/api"
D = "/app/backend/tests/media"
CLIPS = [("bat2.mp4", "batting", "front_on"), ("bat1.mp4", "batting", "side_on"), ("bat2.mp4", "batting", "front_on"), ("bowl1.mp4", "bowling", "front_on")]


def session(email, pw):
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json={"email": email, "password": pw})
    r.raise_for_status()
    s.headers["X-CSRF-Token"] = s.cookies.get("ca_csrf")
    return s


def run():
    s = session("qa.player+qa@cricanalyze.in", "QaPlayer#2026")
    out = []
    while any(x["status"] in ("queued", "processing") for x in s.get(f"{BASE}/analyses").json()):
        time.sleep(15)
    for f, kind, angle in CLIPS[int(sys.argv[1]) if len(sys.argv) > 1 else 0:]:
        with open(f"{D}/{f}", "rb") as fh:
            v = s.post(f"{BASE}/videos", files={"file": (f, fh, "video/mp4")}, data={"analysis_type": kind, "angle": angle})
        print("upload", f, v.status_code, v.text[:200], flush=True)
        v.raise_for_status()
        j = s.post(f"{BASE}/analyses", json={"analysis_type": kind, "video_ids": [v.json()["id"]], "consent": True, "idempotency_key": str(uuid.uuid4())}).json()
        t0 = time.time()
        while True:
            time.sleep(15)
            try:
                job = s.get(f"{BASE}/analyses/{j['id']}", timeout=60).json()
            except Exception:
                continue
            if job["status"] in ("completed", "failed"):
                break
        v = (job.get("report") or {}).get("view") or {}
        print("JOB", j["id"], f, kind, angle, job["status"], job.get("failure_reason"), round(time.time() - t0), "s",
              json.dumps({"score": v.get("score", {}).get("value"), "status": v.get("score", {}).get("status"), "vq": v.get("video_quality", {}).get("rating"),
                          "progress": bool(v.get("progress"))}), flush=True)
        if job["status"] == "completed":
            p = s.get(f"{BASE}/analyses/{j['id']}/pdf")
            open(f"{D}/{j['id'][:8]}.pdf", "wb").write(p.content)
            print("pdf", p.status_code, len(p.content), flush=True)
        out.append(j["id"])
    print("DONE", out, flush=True)


run()
