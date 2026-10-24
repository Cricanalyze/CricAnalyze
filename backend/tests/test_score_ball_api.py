# Technique score + ball tracking API regression: score-check, authz, media Range, dashboard/PDF consistency, phase ball markers
import re, io
import pytest, requests
import fitz
from conftest import API, C, login, signup_verified, mdb

JOBS = ["e6f49bd31f0f416f9561c144651fd131", "2c04878e27304c809879c8489790e42a"]
MAIN = JOBS[0]


@pytest.fixture(scope="module")
def other():
    c = signup_verified("player")
    yield c
    u = mdb.users.find_one({"email": c.email})
    if u:
        for col in ("sessions", "subscriptions", "audit_logs", "consents", "credit_ledger", "notifications"):
            try:
                mdb[col].delete_many({"user_id": u["id"]})
            except Exception:
                pass
        mdb.users.delete_one({"id": u["id"]})
    mdb.dev_outbox.delete_many({"to": c.email})


@pytest.fixture(scope="module")
def job(admin):
    r = admin.get(f"/analyses/{MAIN}")
    assert r.status_code == 200, r.text
    return r.json()


# --- score-check reproducibility + authz
@pytest.mark.parametrize("jid", JOBS)
def test_score_check_reproducible(admin, jid):
    r = admin.get(f"/analyses/{jid}/score-check")
    assert r.status_code == 200, r.text
    res = r.json()["results"]
    assert res, "no biomech results"
    for x in res:
        assert x["reproducible"] is True, x
        assert x["rubric_hash_saved"] == x["rubric_hash_current"]
        assert x["saved"] == x["recomputed"]


def test_score_check_other_user_404(other):
    assert other.get(f"/analyses/{MAIN}/score-check").status_code == 404
    assert other.get(f"/analyses/{MAIN}").status_code == 404


def test_score_check_anon_401():
    assert requests.get(f"{API}/analyses/{MAIN}/score-check", timeout=30).status_code == 401


# --- saved score structure
def test_saved_score_structure(job):
    sc = job["report"]["biomech"][0]["score"]
    assert sc["version"] == "ca-score-v2"
    for k in ("components", "coverage", "evidence", "inputs", "rubric_hash", "method", "detected_phases"):
        assert k in sc
    assert "Not a validated" in sc["method"]["status"]
    if sc["value"] is not None:
        assert 0 <= sc["value"] <= 100 and sc["status"] == "complete"
        assert abs(sum(c["contribution"] or 0 for c in sc["components"]) - sc["value"]) <= 1


# --- ball phase markers only on observed detection on exact frame
@pytest.mark.parametrize("jid", JOBS)
def test_phase_ball_markers_match_detections(admin, jid):
    rep = admin.get(f"/analyses/{jid}").json()["report"]
    for b in rep["biomech"]:
        ball = b.get("ball") or {}
        obs = {d["frame"]: d for d in ball.get("detections", []) if d["status"] == "observed"}
        for p in b.get("phases", []):
            if p.get("ball"):
                assert p["idx"] in obs, (p["key"], p["idx"])
                d = obs[p["idx"]]
                assert abs(d["cx"] - p["ball"]["cx"]) < 0.01 and abs(d["cy"] - p["ball"]["cy"]) < 0.01
                assert p.get("ball_overlay_url")
            else:
                assert p.get("idx") not in obs, f"phase {p['key']} idx {p.get('idx')} has observed det but no marker"
                assert not p.get("ball_overlay_url")


# --- media Range
def test_media_range(job):
    url = job["report"]["biomech"][0]["video_url"]
    full = url if url.startswith("http") else API.rsplit("/api", 1)[0] + url
    r = requests.get(full, headers={"Range": "bytes=0-99"}, timeout=60)
    assert r.status_code == 206, r.status_code
    assert re.match(r"bytes 0-99/\d+", r.headers.get("content-range", ""))
    assert len(r.content) == 100
    n = int(r.headers["content-range"].split("/")[1])
    r2 = requests.get(full, headers={"Range": f"bytes={n + 10}-{n + 20}"}, timeout=60)
    assert r2.status_code == 416
    assert r2.headers.get("content-range") == f"bytes */{n}"
    r3 = requests.get(full, headers={"Range": "bytes=-50"}, timeout=60)
    assert r3.status_code == 206 and len(r3.content) == 50
    tampered = re.sub(r"sig=([0-9a-fA-F])", lambda m: "sig=" + ("0" if m.group(1) != "0" else "1"), full)
    assert tampered != full
    assert requests.get(tampered, timeout=60).status_code == 403
    assert requests.get(full, timeout=60).status_code == 200


# --- PDF consistency
def test_pdf_page1_matches_score(admin, job):
    r = admin.get(f"/analyses/{MAIN}/pdf")
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    open("/tmp/main.pdf", "wb").write(r.content)
    doc = fitz.open(stream=r.content, filetype="pdf")
    t1 = doc[0].get_text()
    sc = job["report"]["biomech"][0]["score"]
    if sc["value"] is not None:
        assert str(sc["value"]) in t1
    for c in sc["components"]:
        if c["score"] is not None:
            assert c["name"] in t1 or c["name"] in "".join(p.get_text() for p in doc), c["name"]
    full = "\n".join(p.get_text() for p in doc)
    assert ("Ball" in full) or ("ball" in full)
    for ph in job["report"]["biomech"][0]["phases"]:
        assert ph["name"] in t1, ph["name"]
