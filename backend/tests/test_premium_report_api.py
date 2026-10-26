# Premium report upgrade: API-level checks (view, score, IST, PDF, history, timeline, access control, staff diagnostics)
import os, re, io
import pytest
import requests
import fitz

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    for line in open("/app/frontend/.env"):
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
FRONT = "971eb6873199472794b5a31dc81dc511"
SIDE = "91f3350e6c6e4e9287c64f656547db35"
BANNED = ["RTMPose", "YOLOX", "YOLO26", "Ultralytics", "ca-score", "ca-pose", "kinematic", "keypoint conf", "UTC", "Not specified", "Insufficient evidence"]


def login(email, pw):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pw}, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"login failed {email}: {r.status_code}")
    tok = r.json().get("token") or r.json().get("access_token")
    if tok:
        s.headers["Authorization"] = f"Bearer {tok}"
    return s


@pytest.fixture(scope="module")
def player():
    return login("qa.player+qa@cricanalyze.in", "QaPlayer#2026")


@pytest.fixture(scope="module")
def newp():
    return login("qa.newplayer+qa@cricanalyze.in", "QaPlayer#2026")


@pytest.fixture(scope="module")
def admin():
    return login("qa.admin+qa@cricanalyze.in", "QaAdmin#2026")


@pytest.fixture(scope="module")
def front(player):
    r = player.get(f"{BASE_URL}/api/analyses/{FRONT}", timeout=60)
    assert r.status_code == 200
    return r.json()


def visible_text(view):
    """customer-facing view without diagnostics"""
    return str({k: v for k, v in view.items() if k != "diagnostics"})


class TestFrontOnView:
    def test_score_provisional(self, front):
        v = front["report"]["view"]
        sc = v["score"]
        assert sc["value"] == 80 and sc["status"] == "provisional"
        assert sc["label"] == "Provisional Technique Score"
        assert "2 of 5 measurements" in sc["text"]
        assert sc["evidence"] == "Limited"

    def test_header(self, front):
        h = front["report"]["view"]["header"]
        assert h["player"] and h["date"].endswith("IST")
        assert h["video_quality"] == "Good" and h["score_status"] == "Provisional Technique Score"

    def test_layout_fields(self, front):
        v = front["report"]["view"]
        assert len(v["takeaways"]) == 3
        assert v["practice_plan"] is None and v["next_step"]
        assert v["action_plan"] and v["filming_tips"]
        assert "diagnostics" not in v
        tl = v["angles"][v["primary"]]["timeline"]
        assert len(tl) == 5
        for p in tl:
            assert p["status_label"] in ("Clear frame", "Approximate timing", "Not assessed reliably")

    def test_no_banned_words(self, front):
        t = visible_text(front["report"]["view"])
        for w in BANNED:
            assert w.lower() not in t.lower(), w
        assert not re.search(r"conf\w*\s*0\.\d", t)


class TestSideOn:
    def test_side_consistent(self, player):
        r = player.get(f"{BASE_URL}/api/analyses/{SIDE}", timeout=60)
        assert r.status_code == 200
        v = r.json()["report"]["view"]
        sc = v["score"]
        print("SIDE score", sc["value"], sc["status"], sc.get("evidence"), v["header"]["video_quality"], sc.get("tip"))
        assert sc["status"] in ("provisional", "unavailable", "complete")
        if sc["status"] == "unavailable":
            assert sc["value"] is None and sc["tip"]
        assert v["header"]["score_status"] == sc["label"]
        t = visible_text(v)
        for w in BANNED:
            assert w.lower() not in t.lower(), w


class TestListPdfTimeline:
    def test_history_list_matches(self, player, front):
        r = player.get(f"{BASE_URL}/api/analyses", timeout=60)
        assert r.status_code == 200
        row = next(j for j in r.json() if j["id"] == FRONT)
        ts = row["report"]["technique_score"]
        assert ts == {"value": 80, "status": "provisional"}

    def test_timeline(self, player):
        r = player.get(f"{BASE_URL}/api/timeline?type=batting", timeout=60)
        assert r.status_code == 200
        reps = r.json()["reports"]
        assert any(x["job_id"] == FRONT and x["technique_score"]["value"] == 80 for x in reps)

    def test_pdf(self, player, front):
        r = player.get(f"{BASE_URL}/api/analyses/{FRONT}/pdf", timeout=120)
        assert r.status_code == 200 and r.headers["content-type"].startswith("application/pdf")
        doc = fitz.open(stream=r.content, filetype="pdf")
        txt = "\n".join(p.get_text() for p in doc)
        open("/tmp/front_pdf.txt", "w").write(txt)
        assert "80" in txt and "Provisional Technique Score" in txt
        assert front["report"]["view"]["header"]["date"] in txt.replace("\n", " ")
        for w in BANNED:
            assert w.lower() not in txt.lower(), w


class TestAccess:
    def test_newplayer_404(self, newp):
        assert newp.get(f"{BASE_URL}/api/analyses/{FRONT}", timeout=30).status_code == 404
        assert newp.get(f"{BASE_URL}/api/analyses/{FRONT}/pdf", timeout=30).status_code == 404

    def test_newplayer_empty(self, newp):
        r = newp.get(f"{BASE_URL}/api/analyses", timeout=30)
        assert r.status_code == 200 and r.json() == []

    def test_anon_401(self):
        assert requests.get(f"{BASE_URL}/api/analyses/{FRONT}", timeout=30).status_code == 401
        assert requests.get(f"{BASE_URL}/api/analyses/{FRONT}/pdf", timeout=30).status_code == 401

    def test_admin_diagnostics(self, admin):
        r = admin.get(f"{BASE_URL}/api/analyses/{FRONT}", timeout=60)
        assert r.status_code == 200
        v = r.json()["report"]["view"]
        assert "diagnostics" in v
        assert v["score"]["value"] == 80
