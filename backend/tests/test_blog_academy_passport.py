# Blog CMS (draft/publish/sitemap/schedule/redirect/dup slug/RBAC), Academy tenancy & consent, Passport share
import time, uuid
from datetime import datetime, timedelta, timezone
import requests
from conftest import C, mdb, signup_verified, API, RUN


def pub(slug):
    return requests.get(f"{API}/blog/posts/{slug}", timeout=30)


def sitemap():
    return requests.get(f"{API}/sitemap.xml", timeout=30).text


class TestBlog:
    def test_blog_lifecycle(self, admin):
        ed = signup_verified("player", "TEST Editor2")
        mdb.users.update_one({"id": ed.user["id"]}, {"$set": {"role": "content_editor"}})
        slug = f"test-cric-analyze-{RUN}"
        r = ed.post("/admin/blog/posts", json={"title": "TEST Cric Analyze", "slug": slug, "excerpt": "x", "content_html": "<p>Hello<script>alert(1)</script></p>"})
        assert r.status_code == 200, r.text
        pid = r.json()["id"]
        assert r.json()["slug"] == slug
        assert "<script" not in mdb.blog_posts.find_one({"id": pid})["content_html"]
        assert pub(slug).status_code == 404
        # duplicate slug -> -2
        r = ed.post("/admin/blog/posts", json={"title": "TEST Cric Analyze", "slug": slug})
        assert r.status_code == 200 and r.json()["slug"] == f"{slug}-2", r.text
        pid2 = r.json()["id"]
        # publish
        assert ed.post(f"/admin/blog/posts/{pid}/status", json={"action": "publish"}).status_code == 200
        r = pub(slug)
        assert r.status_code == 200 and r.json().get("title") == "TEST Cric Analyze", r.text
        assert slug in sitemap()
        # slug change -> redirect
        new = f"{slug}-renamed"
        r = ed.put(f"/admin/blog/posts/{pid}", json={"title": "TEST Cric Analyze", "slug": new, "content_html": "<p>Hi</p>"})
        assert r.status_code == 200 and r.json()["slug"] == new, r.text
        r = pub(slug)
        assert r.status_code == 200 and r.json().get("redirect") == new, r.text
        assert pub(new).status_code == 200
        # unpublish -> gone from sitemap
        assert ed.post(f"/admin/blog/posts/{pid}/status", json={"action": "unpublish"}).status_code == 200
        assert new not in sitemap()
        assert pub(new).status_code == 404
        # schedule
        at = (datetime.now(timezone.utc) + timedelta(seconds=45)).isoformat()
        r = ed.post(f"/admin/blog/posts/{pid2}/status", json={"action": "schedule", "publish_at": at})
        assert r.status_code == 200, r.text
        assert pub(f"{slug}-2").status_code == 404
        r = ed.post(f"/admin/blog/posts/{pid2}/status", json={"action": "schedule", "publish_at": "2030-01-01T10:00:00"})
        assert r.status_code == 422
        r = ed.post(f"/admin/blog/posts/{pid2}/status", json={"action": "schedule", "publish_at": at})
        ok = False
        for _ in range(30):
            time.sleep(5)
            if pub(f"{slug}-2").status_code == 200:
                ok = True
                break
        assert ok, "scheduled post not published within ~150s"
        assert f"{slug}-2" in sitemap()
        # player -> 403 on admin blog
        pl = signup_verified("player")
        assert pl.get("/admin/blog/posts").status_code == 403
        assert pl.post("/admin/blog/posts", json={"title": "TEST nope"}).status_code == 403
        # cleanup
        for i in (pid, pid2):
            assert ed.delete(f"/admin/blog/posts/{i}").status_code == 200
        mdb.blog_redirects.delete_many({"from_slug": {"$regex": f"^test-cric-analyze-{RUN}"}})


class TestAcademy:
    def test_tenant_isolation_and_consent(self, admin):
        owner = signup_verified("coach", "TEST Owner")
        coach = signup_verified("coach", "TEST Coach")
        stranger = signup_verified("coach", "TEST Stranger")
        player = signup_verified("player", "TEST Player")
        r = owner.post("/academies", json={"name": f"TEST Academy {RUN}"})
        assert r.status_code == 200, r.text
        aid = r.json()["id"]
        sid = stranger.post("/academies", json={"name": f"TEST Other {RUN}"}).json()["id"]
        assert player.post("/academies", json={"name": "TEST nope"}).status_code == 403
        for who, role in ((player, "player"), (coach, "coach")):
            r = owner.post(f"/academies/{aid}/invites", json={"email": who.email, "role": role})
            assert r.status_code == 200, r.text
        for who in (player, coach):
            inv = who.get("/academies/mine").json()["invites"]
            assert len(inv) == 1, inv
            # wrong user cannot accept someone else's invite
            if who is player:
                assert stranger.post("/academy-invites/accept", json={"invite_id": inv[0]["id"]}).status_code == 404
            r = who.post("/academy-invites/accept", json={"invite_id": inv[0]["id"]})
            assert r.status_code == 200 and r.json()["academy_id"] == aid
        # stranger (owner of other academy) cannot see members
        assert stranger.get(f"/academies/{aid}/members").status_code == 404
        assert stranger.get(f"/academies/{aid}").status_code == 404
        assert owner.get(f"/academies/{sid}/members").status_code == 404
        assert player.get(f"/academies/{aid}/members").status_code == 404
        m = owner.get(f"/academies/{aid}/members").json()
        assert {x["role"] for x in m["members"]} == {"academy_admin", "coach", "player"}
        # unassigned coach can't see player reports
        rp = f"/academies/{aid}/players/{player.user['id']}/reports"
        assert coach.get(rp).status_code == 404
        assert owner.post(f"/academies/{aid}/assignments", json={"coach_id": coach.user["id"], "player_id": player.user["id"]}).status_code == 200
        # assigned but no consent
        r = coach.get(rp)
        assert r.status_code == 403, r.text
        assert coach.get(f"/analyses?player_id={player.user['id']}").status_code == 404
        assert player.patch(f"/academies/{aid}/consent", json={"share_reports": True}).status_code == 200
        r = coach.get(rp)
        assert r.status_code == 200 and isinstance(r.json(), list)
        assert coach.get(f"/analyses?player_id={player.user['id']}").status_code == 200
        assert stranger.get(f"/analyses?player_id={player.user['id']}").status_code == 404
        # coach can only see assigned players in members; email hidden for coach
        cm = coach.get(f"/academies/{aid}/members").json()
        assert all(x["email"] is None for x in cm["members"])
        # revoke consent
        assert player.patch(f"/academies/{aid}/consent", json={"share_reports": False}).status_code == 200
        assert coach.get(rp).status_code == 403


class TestPassport:
    def test_share_link(self):
        p = signup_verified("player")
        r = p.post("/passport/share", json={"days": 7})
        assert r.status_code == 200, r.text
        tok, sid = r.json()["token"], r.json()["id"]
        r = requests.get(f"{API}/public/passport/{tok}", timeout=30)
        assert r.status_code == 200, r.text
        assert "email" not in str(r.json()).lower() or p.email not in str(r.json())
        assert p.delete(f"/passport/shares/{sid}").status_code == 200
        assert requests.get(f"{API}/public/passport/{tok}", timeout=30).status_code == 404
        assert requests.get(f"{API}/public/passport/bogus", timeout=30).status_code == 404
