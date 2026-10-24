# PDF report endpoint security + measured biomechanical E2E (player owner) for /api/analyses/{id}/pdf
import time, uuid, os
import pytest, requests
from conftest import C, API, signup_verified, mdb

BAT = "f400e7bc0f75406a9abe36ebf2c3b62b"
CLIP = "/root/testvids/bat.mp4"
STATE = {}


def _cleanup():
    for c in STATE.get("users", []):
        uid_ = c.user["id"]
        mdb.users.delete_many({"id": uid_})
        for col in ("sessions", "subscriptions", "video_assets", "analysis_jobs", "analysis_reports", "media_assets"):
            mdb[col].delete_many({"user_id": uid_})


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    STATE["users"] = []
    yield
    _cleanup()


def _latest_admin_measured_job():
    rep = mdb.analysis_reports.find_one({"assessment_type": "measured_biomechanical", "user_id": mdb.users.find_one({"email": "e2e_admin@example.com"})["id"]},
                                        sort=[("created_at", -1)])
    assert rep, "no measured report owned by e2e_admin"
    return rep["job_id"]


class TestPdfSecurity:
    def test_unauthenticated_401(self):
        job = _latest_admin_measured_job()
        r = requests.get(f"{API}/analyses/{job}/pdf", timeout=60)
        assert r.status_code == 401, r.status_code

    def test_admin_owner_200(self, admin):
        job = _latest_admin_measured_job()
        r = admin.get(f"/analyses/{job}/pdf")
        assert r.status_code == 200, r.text[:300]
        assert r.headers["content-type"].startswith("application/pdf")
        assert r.content[:5] == b"%PDF-"
        assert "attachment" in r.headers.get("content-disposition", "")

    def test_other_player_forbidden(self):
        other = signup_verified("player", "TEST Other")
        STATE["users"].append(other)
        job = _latest_admin_measured_job()
        r = other.get(f"/analyses/{job}/pdf")
        assert r.status_code in (403, 404), r.status_code
        assert other.get(f"/analyses/{job}").status_code in (403, 404)

    def test_bogus_job_404(self, admin):
        assert admin.get(f"/analyses/{uuid.uuid4().hex}/pdf").status_code == 404


class TestPlayerOwnerE2E:
    def test_player_full_job_and_pdf(self, admin):
        p = signup_verified("player", "TEST Owner")
        other = signup_verified("player", "TEST Intruder")
        STATE["users"] += [p, other]
        r = admin.post("/admin/grant", json={"user_id": p.user["id"], "plan_id": BAT, "reason": "TEST grant"})
        assert r.status_code == 200, r.text
        with open(CLIP, "rb") as f:
            r = p.post("/videos", files={"file": ("bat.mp4", f, "video/mp4")}, data={"analysis_type": "batting", "angle": "side_on"})
        assert r.status_code == 200, r.text
        vid = r.json()["id"]
        r = p.post("/analyses", json={"analysis_type": "batting", "video_ids": [vid], "consent": True, "idempotency_key": uuid.uuid4().hex, "shot_type": "Front-foot drive"})
        assert r.status_code == 200, r.text
        job = r.json()["id"]
        d = None
        for _ in range(60):
            time.sleep(8)
            d = p.get(f"/analyses/{job}").json()
            if d["status"] in ("completed", "failed"):
                break
        print("JOB", job, d["status"], d.get("failure_reason"))
        assert d["status"] == "completed", d.get("failure_reason")
        rep = d["report"]
        assert rep["assessment_type"] == "measured_biomechanical"
        b = rep["biomech"][0]
        print("SCORE", b["score"], [(m["key"], m["value"], m["status"]) for m in b["metrics"]])
        for m in b["metrics"]:
            if m["status"] == "not_measurable":
                assert m["value"] is None
        # owner PDF
        r = p.get(f"/analyses/{job}/pdf")
        assert r.status_code == 200, r.text[:300]
        assert r.content[:5] == b"%PDF-"
        open("/tmp/player_report.pdf", "wb").write(r.content)
        # intruder & anonymous
        assert other.get(f"/analyses/{job}/pdf").status_code in (403, 404)
        assert requests.get(f"{API}/analyses/{job}/pdf", timeout=60).status_code == 401
        # frame / overlay media must also be private
        ph = next((x for x in b["phases"] if x.get("overlay_url")), None)
        if ph:
            url = ph["overlay_url"]
            full = url if url.startswith("http") else (API.rsplit("/api", 1)[0] + url)
            print("MEDIA", url)
            # media uses short-lived (900s) HMAC-signed URLs: valid sig works, tampered sig must be rejected
            assert p.s.get(full, timeout=60).status_code == 200
            bad = full[:-4] + ("0000" if not full.endswith("0000") else "1111")
            assert requests.get(bad, timeout=60).status_code in (401, 403, 404)
