# Smoke tests after fresh environment setup: health, public APIs, signup, login errors, protected endpoints
import os, random, string
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")


@pytest.fixture
def s():
    return requests.Session()


# Health
def test_health(s):
    r = s.get(f"{BASE_URL}/api/health")
    assert r.status_code == 200, r.text
    d = r.json()
    print(d)
    assert d.get("database") is True
    assert d.get("smtp_configured") is True


# Public APIs
def test_plans(s):
    r = s.get(f"{BASE_URL}/api/plans")
    assert r.status_code == 200, r.text
    d = r.json()
    plans = d if isinstance(d, list) else d.get("plans", d.get("items", []))
    assert len(plans) > 0
    assert "_id" not in str(d)


def test_blog_posts(s):
    r = s.get(f"{BASE_URL}/api/blog/posts")
    assert r.status_code == 200, r.text
    assert "_id\"" not in r.text


def test_sitemap(s):
    r = s.get(f"{BASE_URL}/api/sitemap.xml")
    assert r.status_code == 200
    assert "<urlset" in r.text


# Signup (single throwaway example.com address)
def test_signup_example_com(s):
    rnd = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    r = s.post(f"{BASE_URL}/api/auth/signup", json={
        "full_name": "TEST Smoke", "email": f"smoketest+{rnd}@example.com",
        "password": "Smoke12345", "role": "player", "accept_terms": True})
    print(r.status_code, r.text)
    assert r.status_code == 200, r.text
    assert r.json().get("ok") is True


def test_signup_validation(s):
    r = s.post(f"{BASE_URL}/api/auth/signup", json={
        "full_name": "TEST Smoke", "email": "smoketest+weak@example.com",
        "password": "short", "role": "player", "accept_terms": True})
    assert r.status_code == 422
    r = s.post(f"{BASE_URL}/api/auth/signup", json={
        "full_name": "TEST Smoke", "email": "smoketest+weak@example.com",
        "password": "Smoke12345", "role": "super_admin", "accept_terms": True})
    assert r.status_code == 422


# Login errors
def test_login_wrong_credentials(s):
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": "nobody_smoke@example.com", "password": "Wrong12345"})
    assert r.status_code == 401
    assert r.json()["detail"] == "Incorrect email or password."


# Protected endpoints
@pytest.mark.parametrize("path", ["/api/auth/me", "/api/auth/sessions", "/api/account/status"])
def test_protected_require_auth(s, path):
    r = s.get(f"{BASE_URL}{path}")
    assert r.status_code == 401, f"{path} -> {r.status_code}"


def test_admin_endpoint_requires_auth(s):
    r = s.get(f"{BASE_URL}/api/admin/plans")
    assert r.status_code in (401, 403)
