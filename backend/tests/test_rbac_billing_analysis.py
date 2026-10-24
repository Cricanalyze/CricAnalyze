# RBAC, plans/entitlements, billing (Razorpay), video validation, analysis jobs/credits/refunds, PDF, expiry
import time, uuid
from datetime import datetime, timedelta, timezone
import requests
from conftest import C, mdb, signup_verified, login, API, RUN

PLANS = {p["slug"]: p for p in requests.get(API + "/plans", timeout=30).json()}
BAT, BOWL = PLANS["batting-monthly"]["id"], PLANS["bowling-monthly"]["id"]


def up(c, path, atype="batting", angle="side_on", name="clip.mp4", ctype="video/mp4"):
    with open(path, "rb") as f:
        return c.post("/videos", files={"file": (name, f, ctype)}, data={"analysis_type": atype, "angle": angle})


def credits(sid):
    return mdb.subscriptions.find_one({"id": sid})["credits_remaining"]


class TestRBAC:
    def test_roles(self, admin):
        p = signup_verified("player")
        assert p.get("/admin/users").status_code == 403
        assert p.get("/admin/blog/posts").status_code == 403
        assert p.post("/admin/grant", json={"user_id": p.user["id"], "plan_id": BAT, "reason": "self"}).status_code == 403
        e = signup_verified("player", "TEST Editor")
        mdb.users.update_one({"id": e.user["id"]}, {"$set": {"role": "content_editor"}})
        assert e.get("/admin/blog/posts").status_code == 200
        assert e.get("/admin/users").status_code == 403
        a = signup_verified("player", "TEST Admin")
        mdb.users.update_one({"id": a.user["id"]}, {"$set": {"role": "admin"}})
        assert a.get("/admin/users").status_code == 200
        r = a.patch(f"/admin/users/{p.user['id']}", json={"role": "admin", "confirm": True})
        assert r.status_code == 403, r.text
        r = a.patch(f"/admin/users/{p.user['id']}", json={"role": "super_admin", "confirm": True})
        assert r.status_code == 403
        r = a.patch(f"/admin/users/{p.user['id']}", json={"role": "coach", "confirm": True})
        assert r.status_code == 200, r.text
        r = admin.patch(f"/admin/users/{e.user['id']}", json={"role": "admin", "confirm": True})
        assert r.status_code == 200, r.text
        assert mdb.users.find_one({"id": e.user["id"]})["role"] == "admin"
        assert C().get("/admin/users").status_code == 401


class TestBilling:
    def test_plans_public(self):
        r = requests.get(API + "/plans", timeout=30)
        assert r.status_code == 200 and len(r.json()) >= 3
        assert all("_id" not in p for p in r.json())

    def test_order_verify_webhook(self):
        p = signup_verified("player")
        r = p.post("/billing/order", json={"plan_id": BAT})
        assert r.status_code == 200, r.text
        o = r.json()
        assert o["order_id"].startswith("order_") and o["amount"] == int(PLANS["batting-monthly"]["price_inr"] * 100)
        r = p.post("/billing/verify", json={"razorpay_order_id": o["order_id"], "razorpay_payment_id": "pay_fake123", "razorpay_signature": "bad"})
        assert r.status_code == 400, r.text
        assert p.get("/billing/subscriptions").json() == [] or all(s["status"] != "active" for s in p.get("/billing/subscriptions").json())
        assert mdb.payments.find_one({"order_id": o["order_id"]})["status"] == "failed"
        r = requests.post(API + "/billing/webhook", data=b"{}", headers={"x-razorpay-signature": "x"}, timeout=30)
        assert r.status_code == 503, r.text  # RAZORPAY_WEBHOOK_SECRET not configured


class TestAnalysisFlow:
    def test_full_flow(self, admin, videos):
        p = signup_verified("player")
        other = signup_verified("player")
        # no plan -> 402
        assert up(p, videos["short"]).status_code == 402
        ent = p.get("/entitlements").json()
        assert ent["credits"] == 0 and ent["analysis_types"] == []
        # grant batting
        r = admin.post("/admin/grant", json={"user_id": p.user["id"], "plan_id": BAT, "reason": "TEST grant"})
        assert r.status_code == 200, r.text
        sid = r.json()["subscription_id"]
        assert p.get("/entitlements").json()["credits"] == 5
        assert up(p, videos["short"], "bowling").status_code == 402
        # validation
        with open("/tmp/ca_fake.mp4", "w") as f:
            f.write("this is not a video" * 50)
        r = up(p, "/tmp/ca_fake.mp4")
        assert r.status_code == 415, r.text
        r = up(p, videos["long"])
        assert r.status_code == 422 and "30s" in r.json()["detail"], r.text
        r = up(p, videos["short"])
        assert r.status_code == 200, r.text
        v1 = r.json()
        assert v1["meta"]["duration_s"] <= 6 and "storage_path" not in v1
        v2 = up(p, videos["short"], angle="front_on").json()
        # >1 video on batting plan rejected
        r = p.post("/analyses", json={"analysis_type": "batting", "video_ids": [v1["id"], v2["id"]], "consent": True, "idempotency_key": uuid.uuid4().hex})
        assert r.status_code == 402, r.text
        assert credits(sid) == 5
        # consent required
        r = p.post("/analyses", json={"analysis_type": "batting", "video_ids": [v1["id"]], "consent": False, "idempotency_key": uuid.uuid4().hex})
        assert r.status_code == 422
        # create job, reserves 1 credit
        key = uuid.uuid4().hex
        r = p.post("/analyses", json={"analysis_type": "batting", "video_ids": [v1["id"]], "consent": True, "idempotency_key": key})
        assert r.status_code == 200, r.text
        job = r.json()
        assert job["credit_state"] == "reserved" and credits(sid) == 4
        assert mdb.credit_ledger.count_documents({"ref": job["id"], "delta": -1}) == 1
        r2 = p.post("/analyses", json={"analysis_type": "batting", "video_ids": [v1["id"]], "consent": True, "idempotency_key": key})
        assert r2.status_code == 200 and r2.json()["id"] == job["id"] and credits(sid) == 4
        # refund path: second job, video deleted right away
        key2 = uuid.uuid4().hex
        j2 = p.post("/analyses", json={"analysis_type": "batting", "video_ids": [v2["id"]], "consent": True, "idempotency_key": key2}).json()
        assert p.delete(f"/videos/{v2['id']}").status_code == 200
        # wait for jobs
        deadline = time.time() + 240
        st1 = st2 = None
        while time.time() < deadline:
            st1 = p.get(f"/analyses/{job['id']}").json()
            st2 = p.get(f"/analyses/{j2['id']}").json()
            if st1["status"] in ("completed", "failed") and st2["status"] in ("completed", "failed"):
                break
            time.sleep(5)
        print("job1", st1["status"], st1.get("failure_reason"), "job2", st2["status"], st2.get("failure_reason"), st2.get("credit_state"))
        assert st2["status"] == "failed" and st2["credit_state"] == "refunded", st2
        assert mdb.credit_ledger.count_documents({"ref": j2["id"], "delta": 1}) == 1
        assert st1["status"] == "completed", st1
        assert st1["report"] and st1["report"].get("summary")
        assert credits(sid) == 4
        # other user -> 404
        assert other.get(f"/analyses/{job['id']}").status_code == 404
        assert other.get(f"/analyses/{job['id']}/pdf").status_code == 404
        assert other.get(f"/videos/{v1['id']}/url").status_code == 404
        # PDF for owner
        r = p.get(f"/analyses/{job['id']}/pdf")
        print("pdf", r.status_code, r.headers.get("content-type"), r.text[:100] if r.status_code != 200 else "")
        assert r.status_code == 200
        if r.status_code == 200:
            assert r.content[:4] == b"%PDF"
        # expired subscription -> 0 credits, upload 402
        mdb.subscriptions.update_one({"id": sid}, {"$set": {"expires_at": datetime.now(timezone.utc) - timedelta(minutes=1)}})
        assert p.get("/entitlements").json()["credits"] == 0
        assert up(p, videos["short"]).status_code == 402
        # retry on failed refunded job with no credits -> 402
        assert p.post(f"/analyses/{j2['id']}/retry").status_code == 402

    def test_bowling_multi_angle(self, admin, videos):
        p = signup_verified("player")
        sid = admin.post("/admin/grant", json={"user_id": p.user["id"], "plan_id": BOWL, "reason": "TEST grant"}).json()["subscription_id"]
        assert up(p, videos["short"], "batting").status_code == 402
        ids = []
        for ang in ("side_on", "front_on", "behind"):
            r = up(p, videos["short"], "bowling", ang)
            if r.status_code == 422 and "angle" in r.text.lower():
                continue
            assert r.status_code == 200, r.text
            ids.append(r.json()["id"])
        dup = up(p, videos["short"], "bowling", "side_on").json()["id"]
        r = p.post("/analyses", json={"analysis_type": "bowling", "video_ids": [ids[0], dup], "consent": True, "idempotency_key": uuid.uuid4().hex})
        assert r.status_code == 422, r.text
        assert credits(sid) == 5
        r = p.post("/analyses", json={"analysis_type": "bowling", "video_ids": ids, "consent": True, "idempotency_key": uuid.uuid4().hex})
        assert r.status_code == 200, r.text
        assert len(r.json()["video_ids"]) == len(ids) and credits(sid) == 4
        print("bowling job", r.json()["id"], "videos", len(ids))
