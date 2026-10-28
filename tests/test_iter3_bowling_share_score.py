# Iteration 3 regression: bowling biomechanics assessments, 70-100 display score, public share links
import os, re, json, pytest, requests

BASE = os.environ.get("REACT_APP_BACKEND_URL") or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0]
B = BASE.rstrip("/") + "/api"
SIDE = "cd2404c982a2489cb92c6b965a6903b1"
FRONT = "57da476ce23d451aa2be43a8175cd4ff"
BAT_NEW, BAT_OLD = "9b66e7320f55478f8cc0ab42588fde5d", "971eb6873199472794b5a31dc81dc511"
KEEP_TOKEN = "u04V7yzcmcP58om2K66aQDgk"
KEYS = ["back_foot_landing", "action_type", "shin_lead", "trunk_lean"]


def login(email, pw):
    s = requests.Session()
    r = s.post(f"{B}/auth/login", json={"email": email, "password": pw})
    if r.status_code != 200:
        pytest.skip(f"login failed {email}")
    s.headers["x-csrf-token"] = s.cookies.get("ca_csrf") or ""
    return s


@pytest.fixture(scope="module")
def player():
    return login("qa.player+qa@cricanalyze.in", "QaPlayer#2026")


@pytest.fixture(scope="module")
def other():
    return login("qa.newplayer+qa@cricanalyze.in", "QaPlayer#2026")


def assess(s, jid):
    d = s.get(f"{B}/analyses/{jid}").json()
    return d, [a for an in d["report"]["view"]["angles"] for a in an.get("assessments") or []]


# --- Bowling assessments ---
def test_side_on_all_four_measured(player):
    _, a = assess(player, SIDE)
    assert [x["key"] for x in a] == KEYS
    for x in a:
        assert x["status"] == "measured" and x["status_label"] == "Measured"
        assert x["frame_url"] and x["overlay_url"] and isinstance(x["idx"], int) and x["method"]
    by = {x["key"]: x for x in a}
    assert by["back_foot_landing"]["idx"] == 181 and by["shin_lead"]["idx"] == 192 and by["trunk_lean"]["idx"] == 222
    bf = " ".join(d["value"] for d in by["back_foot_landing"]["details"]).lower()
    assert "not measurable by body tracking" in bf
    tl = {d["label"]: d["value"] for d in by["trunk_lean"]["details"]}
    assert tl.get("Lower-back bending", "").startswith("Not measured")


def test_assessment_images_load(player):
    _, a = assess(player, SIDE)
    for x in a:
        for u in (x["frame_url"], x["overlay_url"]):
            r = requests.get(BASE.rstrip("/") + u)
            assert r.status_code == 200 and r.headers["content-type"].startswith("image/")


def test_front_on_nothing_guessed(player):
    _, a = assess(player, FRONT)
    st = {x["key"]: x["status"] for x in a}
    assert st == {"back_foot_landing": "unavailable", "action_type": "inconclusive", "shin_lead": "unavailable", "trunk_lean": "measured"}
    for x in a:
        if x["status"] != "measured":
            assert x["frame_url"] is None and x["reason"]


@pytest.mark.parametrize("jid", [BAT_NEW, BAT_OLD])
def test_batting_has_no_assessments(player, jid):
    d, a = assess(player, jid)
    assert d["analysis_type"] == "batting" and a == []
    assert d["report"]["view"]["score"] is not None


# --- Display score 70-100 ---
def _scores_ok(v):
    return v is None or 70 <= v <= 100


@pytest.mark.parametrize("jid", [SIDE, FRONT, BAT_NEW, BAT_OLD])
def test_report_scores_ge_70(player, jid):
    d = player.get(f"{B}/analyses/{jid}").json()
    v = d["report"]["view"]
    assert _scores_ok(v["score"]["value"])
    for an in v["angles"]:
        assert _scores_ok(an["score"]["value"])
        for c in an["score"].get("components") or []:
            assert _scores_ok(c.get("score"))
    txt = json.dumps(v).lower()
    assert "floor" not in txt and "raw score" not in txt and "raw_value" not in txt


def test_list_and_timeline_scores(player):
    jobs = player.get(f"{B}/analyses").json()
    assert len(jobs) > 0
    for j in jobs:
        ts = (j.get("report") or {}).get("technique_score")
        if ts:
            assert _scores_ok(ts["value"])
            if ts["status"] == "unavailable":
                assert ts["value"] is None
    for t in ("batting", "bowling"):
        r = player.get(f"{B}/timeline", params={"type": t})
        assert r.status_code == 200
        for rep in r.json()["reports"]:
            assert _scores_ok(rep["technique_score"]["value"])


# --- Share ---
def test_share_status_owner(player):
    r = player.get(f"{B}/analyses/{SIDE}/share").json()
    assert r == {"enabled": True, "url": f"/r/{KEEP_TOKEN}"}


def test_share_create_idempotent_keeps_token(player):
    r = player.post(f"{B}/analyses/{SIDE}/share")
    assert r.status_code == 200 and r.json()["url"] == f"/r/{KEEP_TOKEN}"


def test_share_requires_csrf(player):
    r = requests.post(f"{B}/analyses/{SIDE}/share", cookies=player.cookies)
    assert r.status_code == 403


def test_other_user_cannot_share(other):
    assert other.post(f"{B}/analyses/{SIDE}/share").status_code == 404
    assert other.delete(f"{B}/analyses/{SIDE}/share").status_code == 404
    assert other.get(f"{B}/analyses/{SIDE}/share").status_code == 404


def test_public_report_json(player):
    r = requests.get(f"{B}/public/reports/{KEEP_TOKEN}")
    assert r.status_code == 200
    d = r.json()
    raw = json.dumps(d).lower()
    assert "@" not in raw and "email" not in raw
    assert "diagnostics" not in d["report"]["view"]
    keys = [a["key"] for an in d["report"]["view"]["angles"] for a in an["assessments"]]
    assert keys == KEYS and d["videos"] and d["pdf_available"] is True


def test_public_pdf_and_media():
    d = requests.get(f"{B}/public/reports/{KEEP_TOKEN}").json()
    r = requests.get(f"{B}/public/reports/{KEEP_TOKEN}/pdf")
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    v = requests.get(BASE.rstrip("/") + d["videos"][0]["url"], headers={"Range": "bytes=0-100"})
    assert v.status_code in (200, 206)


def test_bad_token_404():
    assert requests.get(f"{B}/public/reports/notarealtoken1234567890xx").status_code == 404
    assert requests.get(f"{B}/public/reports/short").status_code == 404


def test_share_toggle_lifecycle_on_other_report(player):
    before = player.get(f"{B}/analyses/{FRONT}/share").json()
    on = player.post(f"{B}/analyses/{FRONT}/share")
    assert on.status_code == 200
    tok = on.json()["url"].split("/r/")[1]
    assert len(tok) >= 20
    assert requests.get(f"{B}/public/reports/{tok}").status_code == 200
    off = player.delete(f"{B}/analyses/{FRONT}/share")
    assert off.status_code == 200 and off.json() == {"enabled": False}
    assert requests.get(f"{B}/public/reports/{tok}").status_code == 404
    assert requests.get(f"{B}/public/reports/{tok}/pdf").status_code == 404
    assert player.get(f"{B}/analyses/{FRONT}/share").json()["enabled"] is False
    if before.get("enabled"):
        player.post(f"{B}/analyses/{FRONT}/share")
