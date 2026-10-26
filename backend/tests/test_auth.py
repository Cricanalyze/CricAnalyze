# Auth: signup/OTP, login/lockout, OTP login, password reset, CSRF
import time, uuid
from datetime import datetime, timedelta, timezone
from conftest import C, mdb, latest_code, PW, RUN, login, API


def _signup(c, email, role="player"):
    return c.post("/auth/signup", json={"full_name": "TEST Auth", "email": email, "password": PW, "role": role, "accept_terms": True})


class TestSignupOtp:
    def test_signup_otp_flow(self):
        email = f"test_otp_{RUN}@example.com"
        c = C()
        r = _signup(c, email)
        assert r.status_code == 200 and r.json()["ok"]
        code = latest_code(email, "verify_email")
        # wrong code decrements attempts
        wrong = "000000" if code != "000000" else "111111"
        r = c.post("/auth/verify-email", json={"email": email, "code": wrong})
        assert r.status_code == 400 and "4 attempt" in r.json()["detail"], r.text
        rec = mdb.email_verifications.find_one({"email": email, "purpose": "verify_email"}, sort=[("created_at", -1)])
        assert rec["attempts"] == 1 and "code" not in rec  # hashed only
        # resend within 60s -> 429
        r = c.post("/auth/resend", json={"email": email, "purpose": "verify_email"})
        assert r.status_code == 429, r.text
        # unverified login -> 403 email_unverified (also cooldown may apply -> check)
        r = c.post("/auth/login", json={"email": email, "password": PW})
        assert r.status_code in (403, 429), r.text
        # correct code -> logged in
        r = c.post("/auth/verify-email", json={"email": email, "code": code})
        assert r.status_code == 200, r.text
        assert c.s.cookies.get("ca_session") and c.s.cookies.get("ca_csrf")
        assert r.json()["user"]["email"] == email
        me = c.get("/auth/me")
        assert me.status_code == 200 and me.json()["user"]["role"] == "player"
        # reuse -> rejected
        c2 = C()
        r = c2.post("/auth/verify-email", json={"email": email, "code": code})
        assert r.status_code == 400
        # CSRF: mutating request w/ cookie but no header -> 403
        r = c.s.post(f"{API}/auth/sessions/revoke-others", headers={"X-Forwarded-For": c.ip}, timeout=30)
        assert r.status_code == 403 and "Security check" in r.json()["detail"]
        r = c.post("/auth/sessions/revoke-others")
        assert r.status_code == 200

    def test_unverified_login_403(self):
        email = f"test_unv_{RUN}@example.com"
        c = C()
        assert _signup(c, email).status_code == 200
        mdb.email_verifications.update_many({"email": email}, {"$set": {"created_at": datetime.now(timezone.utc) - timedelta(seconds=120)}})
        r = c.post("/auth/login", json={"email": email, "password": PW})
        assert r.status_code == 403 and r.json()["detail"] == "email_unverified", r.text

    def test_expired_code_rejected(self):
        email = f"test_exp_{RUN}@example.com"
        c = C()
        assert _signup(c, email).status_code == 200
        code = latest_code(email, "verify_email")
        mdb.email_verifications.update_many({"email": email, "used": False}, {"$set": {"expires_at": datetime.now(timezone.utc) - timedelta(seconds=5)}})
        r = c.post("/auth/verify-email", json={"email": email, "code": code})
        assert r.status_code == 400 and "expired" in r.json()["detail"].lower(), r.text

    def test_signup_anti_enumeration_and_role(self):
        c = C()
        r = _signup(c, "e2e_admin@example.com")
        assert r.status_code == 200 and r.json()["ok"]
        r = c.post("/auth/signup", json={"full_name": "TEST X", "email": f"test_r_{RUN}@example.com", "password": PW, "role": "admin", "accept_terms": True})
        assert r.status_code == 422


class TestLoginReset:
    def test_lockout_otp_login_reset(self):
        email = f"test_lock_{RUN}@example.com"
        c = C()
        assert _signup(c, email).status_code == 200
        assert c.post("/auth/verify-email", json={"email": email, "code": latest_code(email, "verify_email")}).status_code == 200
        # password login works
        l1 = login(email)
        assert l1.get("/auth/me").status_code == 200
        # 5 wrong -> lockout
        x = C()
        for i in range(5):
            r = x.post("/auth/login", json={"email": email, "password": "Wrongpass9"})
            assert r.status_code == 401, (i, r.text)
        r = x.post("/auth/login", json={"email": email, "password": PW})
        assert r.status_code == 429, r.text
        # OTP login request/verify (works while locked? document)
        o = C()
        r = o.post("/auth/login/otp/request", json={"email": email, "purpose": "login_otp"})
        assert r.status_code == 200, r.text
        code = latest_code(email, "login_otp")
        r = o.post("/auth/login/otp/verify", json={"email": email, "code": code})
        assert r.status_code == 200, r.text
        assert o.get("/auth/me").json()["user"]["email"] == email
        # forgot -> reset/verify -> reset
        f = C()
        assert f.post("/auth/forgot", json={"email": email}).status_code == 200
        code = latest_code(email, "reset_password")
        r = f.post("/auth/reset/verify", json={"email": email, "code": code})
        assert r.status_code == 200, r.text
        tok = r.json()["reset_token"]
        r = f.post("/auth/reset", json={"reset_token": tok, "new_password": "NewPassw0rd2"})
        assert r.status_code == 200, r.text
        r = f.post("/auth/reset", json={"reset_token": tok, "new_password": "NewPassw0rd3"})
        assert r.status_code == 400  # single-use
        # all sessions revoked
        assert l1.get("/auth/me").status_code == 401
        assert o.get("/auth/me").status_code == 401
        # lockout cleared + new password works
        login(email, "NewPassw0rd2")

    def test_forgot_unknown_email_generic(self):
        r = C().post("/auth/forgot", json={"email": f"nobody_{RUN}@example.com"})
        assert r.status_code == 200 and r.json()["ok"]

    def test_xff_spoof_bypasses_ip_rate_limit(self):
        # client_ip trusts first X-Forwarded-For entry -> attacker can rotate IPs (security finding)
        r = C(ip="1.2.3.4").post("/auth/login", json={"email": f"nobody_{RUN}@example.com", "password": "x"})
        ip_doc = mdb.rate_limits.find_one({"key": {"$regex": "login:1.2.3.4"}}) or mdb.rate_limits.find_one({"_id": {"$regex": "login:1.2.3.4"}})
        assert r.status_code == 401
        assert ip_doc is None, "rate limit keyed on spoofed XFF IP"


class TestSecurityEdges:
    def test_pre_account_hijack(self):
        # attacker pre-registers victim email with own password; victim signs up with a different password and verifies
        email = f"test_hijack_{RUN}@example.com"
        att = C()
        assert att.post("/auth/signup", json={"full_name": "TEST Attacker", "email": email, "password": "Attack3rPw", "role": "player", "accept_terms": True}).status_code == 200
        mdb.email_verifications.update_many({"email": email}, {"$set": {"created_at": datetime.now(timezone.utc) - timedelta(seconds=120)}})
        vic = C()
        assert vic.post("/auth/signup", json={"full_name": "TEST Victim", "email": email, "password": "Victim9Pw", "role": "player", "accept_terms": True}).status_code == 200
        assert vic.post("/auth/verify-email", json={"email": email, "code": latest_code(email, "verify_email")}).status_code == 200
        r = C().post("/auth/login", json={"email": email, "password": "Attack3rPw"})
        assert r.status_code == 401, "attacker's pre-registered password still works after victim verified (account pre-hijack)"
        r = C().post("/auth/login", json={"email": email, "password": "Victim9Pw"})
        assert r.status_code == 200, "victim's chosen password does not work"

    def test_bad_date_filter_not_500(self):
        email = f"test_date_{RUN}@example.com"
        c = C()
        c.post("/auth/signup", json={"full_name": "TEST D", "email": email, "password": PW, "role": "player", "accept_terms": True})
        assert c.post("/auth/verify-email", json={"email": email, "code": latest_code(email, "verify_email")}).status_code == 200
        r = c.get("/analyses?date_from=notadate")
        assert r.status_code in (400, 422), r.status_code
