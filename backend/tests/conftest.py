# Shared fixtures/helpers for CricAnalyze API regression tests
import os, time, uuid, random
import pytest, requests, cv2
from pymongo import MongoClient
from dotenv import dotenv_values

_fe = dotenv_values("/app/frontend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _fe["REACT_APP_BACKEND_URL"]).rstrip("/")
API = BASE_URL + "/api"
_be = dotenv_values("/app/backend/.env")
mdb = MongoClient(_be["MONGO_URL"])[_be["DB_NAME"]]
PW = "Passw0rd1"
RUN = uuid.uuid4().hex[:6]


class C:
    """requests wrapper that adds X-CSRF-Token from ca_csrf cookie"""
    def __init__(self, ip=None):
        self.s = requests.Session()
        # distinct pseudo IP per client to keep shared-IP rate limits (signup 10/hr) from blocking the suite
        self.ip = ip or f"10.{random.randint(1,250)}.{random.randint(1,250)}.{random.randint(1,250)}"

    def _h(self, csrf=True, extra=None):
        h = {"X-Forwarded-For": self.ip}
        tok = self.s.cookies.get("ca_csrf")
        if csrf and tok:
            h["X-CSRF-Token"] = tok
        h.update(extra or {})
        return h

    def get(self, p, **kw):
        return self.s.get(API + p, headers=self._h(), timeout=60, **kw)

    def post(self, p, csrf=True, **kw):
        return self.s.post(API + p, headers=self._h(csrf), timeout=120, **kw)

    def put(self, p, **kw):
        return self.s.put(API + p, headers=self._h(), timeout=60, **kw)

    def patch(self, p, **kw):
        return self.s.patch(API + p, headers=self._h(), timeout=60, **kw)

    def delete(self, p, **kw):
        return self.s.delete(API + p, headers=self._h(), timeout=60, **kw)


def latest_code(email, purpose=None):
    for _ in range(20):
        q = {"to": email}
        if purpose:
            q["template"] = purpose
        doc = mdb.dev_outbox.find_one(q, sort=[("created_at", -1)])
        if doc and doc.get("code"):
            return doc["code"]
        time.sleep(0.5)
    raise AssertionError(f"no OTP in dev_outbox for {email}")


def signup_verified(role="player", name="TEST User"):
    email = f"test_{role}_{RUN}_{uuid.uuid4().hex[:4]}@example.com"
    c = C()
    r = c.post("/auth/signup", json={"full_name": name, "email": email, "password": PW, "role": role, "accept_terms": True})
    assert r.status_code == 200, r.text
    code = latest_code(email)
    r = c.post("/auth/verify-email", json={"email": email, "code": code})
    assert r.status_code == 200, r.text
    c.email = email
    c.user = r.json()["user"]
    return c


def login(email, pw=PW):
    c = C()
    r = c.post("/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    c.email = email
    c.user = r.json()["user"]
    return c


def make_video(path, seconds, w=480, h=720):
    img = cv2.imread("/app/frontend/public/images/hero.jpg")
    img = cv2.resize(img, (w, h))
    vw = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 25, (w, h))
    for i in range(int(seconds * 25)):
        f = img.copy()
        cv2.putText(f, str(i), (20 + i % 200, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 3)
        vw.write(f)
    vw.release()
    return path


@pytest.fixture(scope="session")
def videos():
    return {"short": make_video("/tmp/ca_short.mp4", 5), "long": make_video("/tmp/ca_long.mp4", 35)}


@pytest.fixture(scope="session")
def admin():
    return login("e2e_admin@example.com")
