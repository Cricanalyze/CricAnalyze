import os, hmac, hashlib, secrets, uuid, logging, smtplib, ssl, asyncio, time, html as htmllib
from pathlib import Path
from datetime import datetime, timezone, timedelta
from email.message import EmailMessage
from dotenv import load_dotenv
from fastapi import Request, HTTPException, Depends, Response
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ReturnDocument
from argon2 import PasswordHasher
import requests

load_dotenv(Path(__file__).parent / ".env")

client = AsyncIOMotorClient(os.environ["MONGO_URL"], tz_aware=True)
db = client[os.environ["DB_NAME"]]
logging.basicConfig(level=logging.INFO, format='{"t":"%(asctime)s","lvl":"%(levelname)s","log":"%(name)s","msg":"%(message)s"}')
log = logging.getLogger("cricanalyze")

SECRET = os.environ["APP_SECRET"]
APP_URL = os.environ["APP_URL"].rstrip("/")
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "true") == "true"
SESSION_DAYS = 14
LLM_KEY = os.environ.get("EMERGENT_LLM_KEY")
AI_MODEL = os.environ.get("AI_MODEL", "claude-sonnet-5-5")
ph = PasswordHasher()  # argon2id defaults

ROLES = ["player", "parent", "coach", "academy_admin", "content_editor", "admin", "super_admin"]
SELF_SIGNUP_ROLES = {"player", "parent", "coach", "academy_admin"}
STAFF = {"admin", "super_admin"}


def now():
    return datetime.now(timezone.utc)


def iso(dt=None):
    return (dt or now()).isoformat()


def uid():
    return uuid.uuid4().hex


def hsign(value: str) -> str:
    return hmac.new(SECRET.encode(), value.encode(), hashlib.sha256).hexdigest()


def client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "")
    return xff.split(",")[0].strip() if xff else (request.client.host if request.client else "")


def norm_email(e: str) -> str:
    return (e or "").strip().lower()


def clean(doc):
    if doc:
        doc.pop("_id", None)
    return doc


async def rate_limit(key: str, limit: int, window_s: int):
    bucket = f"{key}:{int(time.time() // window_s)}"
    doc = await db.rate_limits.find_one_and_update(
        {"_id": bucket}, {"$inc": {"n": 1}, "$setOnInsert": {"exp": now() + timedelta(seconds=window_s * 2)}},
        upsert=True, return_document=ReturnDocument.AFTER)
    if doc["n"] > limit:
        raise HTTPException(429, "Too many requests. Please wait a few minutes and try again.")


async def audit(actor_id, action, target=None, meta=None, request: Request = None):
    await db.audit_logs.insert_one({"id": uid(), "actor_id": actor_id, "action": action, "target": target,
                                    "meta": meta or {}, "ip": client_ip(request) if request else None, "created_at": now()})


DEFAULT_SETTINGS = {
    "flags": {"ai_coach": True, "ask_assistant": True, "academy": True, "challenges": True, "passport": True,
              "leaderboard": False, "otp_login": True, "blog_ai": True, "require_otp_every_login": False},
    "limits": {"max_concurrent_jobs": 2, "job_timeout_s": 240, "max_retries": 2, "frames_per_video": 6,
               "est_cost_per_analysis_inr": 6, "monthly_cost_alert_inr": 5000, "retention_days": 365},
}


async def get_settings():
    doc = await db.settings.find_one({"_id": "app"}) or {}
    out = {}
    for k, v in DEFAULT_SETTINGS.items():
        out[k] = {**v, **(doc.get(k) or {})}
    return out


# ---------- sessions & auth deps ----------
async def create_session(response: Response, user_id: str, request: Request):
    token = secrets.token_urlsafe(32)
    await db.sessions.insert_one({"id": uid(), "token_hash": hsign(token), "user_id": user_id, "created_at": now(),
                                  "expires_at": now() + timedelta(days=SESSION_DAYS), "ip": client_ip(request),
                                  "ua": request.headers.get("user-agent", "")[:200], "revoked": False})
    opts = dict(secure=COOKIE_SECURE, samesite="lax", path="/", max_age=SESSION_DAYS * 86400)
    response.set_cookie("ca_session", token, httponly=True, **opts)
    response.set_cookie("ca_csrf", secrets.token_urlsafe(16), httponly=False, **opts)


def clear_session_cookies(response: Response):
    response.delete_cookie("ca_session", path="/")
    response.delete_cookie("ca_csrf", path="/")


async def session_from_request(request: Request):
    token = request.cookies.get("ca_session")
    if not token:
        return None
    return await db.sessions.find_one({"token_hash": hsign(token), "revoked": False, "expires_at": {"$gt": now()}})


USER_HIDDEN = {"_id": 0, "password_hash": 0, "failed_logins": 0, "locked_until": 0}


async def current_user(request: Request):
    s = await session_from_request(request)
    if not s:
        raise HTTPException(401, "Please sign in to continue.")
    u = await db.users.find_one({"id": s["user_id"], "deleted": {"$ne": True}}, USER_HIDDEN)
    if not u or u.get("status") == "suspended":
        raise HTTPException(401, "Your session is no longer valid.")
    u["_session"] = {"id": s["id"], "step_up_until": s.get("step_up_until")}
    return u


async def optional_user(request: Request):
    try:
        return await current_user(request)
    except HTTPException:
        return None


def require_roles(*roles):
    async def dep(u=Depends(current_user)):
        if u["role"] != "super_admin" and u["role"] not in roles:
            raise HTTPException(403, "You don't have permission to do this.")
        return u
    return dep


ADMIN = require_roles("admin")
EDITOR = require_roles("admin", "content_editor")


def require_step_up(u):
    su = u["_session"].get("step_up_until")
    if not su or su < now():
        raise HTTPException(403, "step_up_required")


def public_user(u):
    return {k: v for k, v in u.items() if k not in ("_session", "_id", "password_hash")}


# ---------- email ----------
EMAIL_TEMPLATES = {
    "verify_email": ("Your CricAnalyze verification code", "Verify your email",
                     "Use this code to verify your email address. It expires in 5 minutes.", True),
    "login_otp": ("Your CricAnalyze sign-in code", "Sign-in code", "Use this code to sign in. It expires in 5 minutes.", True),
    "reset_password": ("Reset your CricAnalyze password", "Password reset code",
                       "Use this code to reset your password. It expires in 5 minutes. If you didn't ask for this, ignore this email.", True),
    "step_up": ("Confirm a sensitive action", "Security confirmation", "Use this code to confirm a sensitive account action.", True),
    "change_email": ("Confirm your new email", "Confirm new email", "Use this code to confirm this new email for your CricAnalyze account.", True),
    "guardian_consent": ("Guardian consent request — CricAnalyze", "Guardian consent",
                         "{player} has asked you to approve video analysis on CricAnalyze. Share this code with them only if you consent.", True),
    "welcome": ("Welcome to CricAnalyze", "Welcome aboard", "Your email is verified. Upload a batting or bowling video to get your first report.", False),
    "password_changed": ("Your CricAnalyze password was changed", "Password changed",
                         "Your password was just changed and other sessions were signed out. If this wasn't you, reset your password immediately.", False),
    "receipt": ("Payment receipt — CricAnalyze", "Payment received", "Thank you. We received {amount} for {plan}. Payment ID: {payment_id}.", False),
    "payment_failed": ("Payment failed — CricAnalyze", "Payment failed", "Your payment for {plan} did not go through. No subscription was activated. You can try again.", False),
    "report_ready": ("Your analysis report is ready", "Report ready", "Your {kind} analysis is complete. Open CricAnalyze to view it.", False),
    "academy_invite": ("You're invited to {academy} on CricAnalyze", "Academy invitation",
                       "{academy} invited you to join as a {role}. Open this link to accept: {link}", False),
    "notice": ("Important account notice — CricAnalyze", "Account notice", "{message}", False),
    "test": ("CricAnalyze SMTP test", "SMTP test", "This is a test email from the CricAnalyze admin console.", False),
}


def render_email(template: str, ctx: dict):
    subject, title, body, has_code = EMAIL_TEMPLATES[template]
    subject = subject.format(**ctx) if "{" in subject else subject
    body = body.format(**ctx)
    code = ctx.get("code") if has_code else None
    text = f"{title}\n\n{body}\n\n" + (f"Code: {code}\n\n" if code else "") + "— CricAnalyze, Buddy Innovations and Technologies Pvt Ltd\nhttps://cricanalyze.in"
    code_html = f'<div style="font:700 32px monospace;letter-spacing:8px;color:#0B132B;background:#E6FAF4;padding:16px;text-align:center;border-radius:8px">{code}</div>' if code else ""
    html = f"""<div style="background:#f4f7fb;padding:24px;font-family:Arial,sans-serif"><div style="max-width:520px;margin:auto;background:#fff;border-radius:12px;overflow:hidden">
<div style="background:#0B132B;padding:18px 24px;color:#fff;font-weight:800;font-size:20px">Cric<span style="color:#10B981">Analyze</span></div>
<div style="padding:24px;color:#1C2541"><h2 style="margin:0 0 12px">{htmllib.escape(title)}</h2><p style="line-height:1.6">{htmllib.escape(body)}</p>{code_html}</div>
<div style="padding:16px 24px;font-size:12px;color:#64748b;border-top:1px solid #e2e8f0">Buddy Innovations and Technologies Pvt Ltd · cricanalyze.in<br>Never share this code. CricAnalyze will never ask for your password.</div></div></div>"""
    return subject, html, text


def smtp_configured():
    return all(os.environ.get(k) for k in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS", "SMTP_FROM_EMAIL"))


def _smtp_send(to, subject, html, text):
    host, port = os.environ["SMTP_HOST"], int(os.environ["SMTP_PORT"])
    secure = os.environ.get("SMTP_SECURE", "ssl").strip().lower()
    msg = EmailMessage()
    msg["From"] = f'{os.environ.get("SMTP_FROM_NAME") or "CricAnalyze"} <{os.environ["SMTP_FROM_EMAIL"]}>'
    msg["To"], msg["Subject"] = to, subject
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    ctx = ssl.create_default_context()
    if secure in ("ssl", "true", "1", "yes", "tls") or port == 465:
        server = smtplib.SMTP_SSL(host, port, context=ctx, timeout=20)
    else:
        server = smtplib.SMTP(host, port, timeout=20)
        server.starttls(context=ctx)
    with server:
        server.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
        server.send_message(msg)


def sanitize_error(e: Exception) -> str:
    msg = str(e)
    for k in ("SMTP_PASS", "SMTP_USER", "RAZORPAY_KEY_SECRET", "EMERGENT_LLM_KEY"):
        v = os.environ.get(k)
        if v:
            msg = msg.replace(v, "***")
    return f"{type(e).__name__}: {msg[:180]}"


async def send_email(to: str, template: str, ctx: dict, user_id=None) -> bool:
    subject, html, text = render_email(template, ctx)
    log_id = uid()
    await db.email_logs.insert_one({"id": log_id, "to": to, "template": template, "user_id": user_id,
                                    "status": "queued", "created_at": now()})
    if os.environ.get("DEV_EMAIL_OUTBOX") == "true" and to.endswith("@example.com"):
        await db.dev_outbox.insert_one({"to": to, "template": template, "code": ctx.get("code"), "created_at": now()})
        await db.email_logs.update_one({"id": log_id}, {"$set": {"status": "captured_dev_outbox"}})
        return True
    if not smtp_configured():
        await db.email_logs.update_one({"id": log_id}, {"$set": {"status": "failed", "error": "SMTP not configured"}})
        return False
    try:
        await asyncio.to_thread(_smtp_send, to, subject, html, text)
        await db.email_logs.update_one({"id": log_id}, {"$set": {"status": "accepted", "accepted_at": now()}})
        return True
    except Exception as e:
        err = sanitize_error(e)
        log.warning(f"email send failed template={template} err={type(e).__name__}")
        await db.email_logs.update_one({"id": log_id}, {"$set": {"status": "failed", "error": err}})
        return False


# ---------- OTP ----------
OTP_TTL = 300
OTP_MAX_ATTEMPTS = 5
OTP_COOLDOWN = 60


def _otp_hash(email, purpose, code):
    return hsign(f"otp:{purpose}:{email}:{code}")


async def issue_otp(email: str, purpose: str, request: Request, ctx=None, send_to=None, extra=None):
    await rate_limit(f"otp:{purpose}:{email}", 6, 3600)
    await rate_limit(f"otpip:{client_ip(request)}", 30, 3600)
    last = await db.email_verifications.find_one({"email": email, "purpose": purpose}, sort=[("created_at", -1)])
    if last and (now() - last["created_at"]).total_seconds() < OTP_COOLDOWN:
        raise HTTPException(429, f"Please wait {OTP_COOLDOWN} seconds before requesting another code.")
    code = f"{secrets.randbelow(10 ** 6):06d}"
    await db.email_verifications.update_many({"email": email, "purpose": purpose, "used": False},
                                             {"$set": {"used": True, "invalidated": True}})
    await db.email_verifications.insert_one({"id": uid(), "email": email, "purpose": purpose,
                                             "code_hash": _otp_hash(email, purpose, code), "attempts": 0, "used": False,
                                             "created_at": now(), "expires_at": now() + timedelta(seconds=OTP_TTL),
                                             "extra": extra or {}})
    ok = await send_email(send_to or email, purpose, {"code": code, **(ctx or {})})
    if not ok:
        raise HTTPException(502, "We couldn't send the email right now. Please try again in a moment.")


async def verify_otp(email: str, purpose: str, code: str):
    rec = await db.email_verifications.find_one({"email": email, "purpose": purpose, "used": False}, sort=[("created_at", -1)])
    if not rec:
        raise HTTPException(400, "Invalid or already-used code. Please request a new one.")
    if rec["expires_at"] < now():
        raise HTTPException(400, "This code has expired. Please request a new one.")
    if rec["attempts"] >= OTP_MAX_ATTEMPTS:
        await db.email_verifications.update_one({"id": rec["id"]}, {"$set": {"used": True}})
        raise HTTPException(429, "Too many incorrect attempts. Please request a new code.")
    if not hmac.compare_digest(rec["code_hash"], _otp_hash(email, purpose, (code or "").strip())):
        await db.email_verifications.update_one({"id": rec["id"]}, {"$inc": {"attempts": 1}})
        left = OTP_MAX_ATTEMPTS - rec["attempts"] - 1
        raise HTTPException(400, f"Incorrect code. {left} attempt(s) left." if left > 0 else "Too many incorrect attempts. Please request a new code.")
    claimed = await db.email_verifications.find_one_and_update({"id": rec["id"], "used": False},
                                                               {"$set": {"used": True, "used_at": now()}})
    if not claimed:
        raise HTTPException(400, "This code was already used.")
    return rec


# ---------- object storage ----------
STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"
BUCKET_PREFIX = os.environ.get("VIDEO_STORAGE_BUCKET", "cricanalyze")
_storage_key = None


def init_storage(force=False):
    global _storage_key
    if _storage_key and not force:
        return _storage_key
    r = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": LLM_KEY}, timeout=30)
    r.raise_for_status()
    _storage_key = r.json()["storage_key"]
    return _storage_key


def put_object(path, data: bytes, content_type: str):
    for attempt in range(2):
        r = requests.put(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": init_storage(attempt > 0), "Content-Type": content_type},
                         data=data, timeout=180)
        if r.status_code == 404 and attempt == 0:
            continue
        r.raise_for_status()
        return r.json()


def get_object(path):
    for attempt in range(2):
        r = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": init_storage(attempt > 0)}, timeout=120)
        if r.status_code == 404 and attempt == 0:
            continue
        r.raise_for_status()
        return r.content, r.headers.get("Content-Type", "application/octet-stream")


def sign_media(asset_id: str, ttl=900):
    exp = int(time.time()) + ttl
    return f"/api/media/{asset_id}?exp={exp}&sig={hsign(f'media:{asset_id}:{exp}')}"


def verify_media_sig(asset_id, exp, sig):
    return exp > time.time() and hmac.compare_digest(sig or "", hsign(f"media:{asset_id}:{exp}"))


# ---------- entitlements ----------
async def active_subscriptions(user_id):
    return await db.subscriptions.find({"user_id": user_id, "status": "active", "expires_at": {"$gt": now()}}, {"_id": 0}).to_list(50)


ENT_BOOL = ["pdf_export", "history_access", "comparisons", "timeline", "multi_angle", "ai_coach", "training_planner", "academy_features"]
LEVELS = ["basic", "detailed", "advanced"]


async def entitlements(user_id):
    subs = await active_subscriptions(user_id)
    ent = {k: False for k in ENT_BOOL}
    ent.update({"analysis_types": [], "report_level": None, "credits": 0, "max_duration_s": 0, "max_file_mb": 0,
                "videos_per_analysis": 0, "subscriptions": len(subs)})
    for s in subs:
        p = s["plan_snapshot"]
        for k in ENT_BOOL:
            ent[k] = ent[k] or bool(p.get(k))
        ent["analysis_types"] = sorted(set(ent["analysis_types"]) | set(p.get("analysis_types", [])))
        ent["credits"] += s.get("credits_remaining", 0)
        ent["max_duration_s"] = max(ent["max_duration_s"], p.get("max_duration_s", 0))
        ent["max_file_mb"] = max(ent["max_file_mb"], p.get("max_file_mb", 0))
        ent["videos_per_analysis"] = max(ent["videos_per_analysis"], p.get("videos_per_analysis", 0))
        lvl = p.get("report_level", "basic")
        if ent["report_level"] is None or LEVELS.index(lvl) > LEVELS.index(ent["report_level"]):
            ent["report_level"] = lvl
    return ent


async def require_ent(user, key):
    if user["role"] in STAFF:
        return
    if not (await entitlements(user["id"])).get(key):
        raise HTTPException(402, f"Your current plan doesn't include this feature ({key.replace('_', ' ')}). Upgrade on the Billing page.")


async def ledger(user_id, delta, reason, ref=None, subscription_id=None, actor_id=None):
    await db.credit_ledger.insert_one({"id": uid(), "user_id": user_id, "delta": delta, "reason": reason, "ref": ref,
                                       "subscription_id": subscription_id, "actor_id": actor_id, "created_at": now()})


def age_of(dob: str):
    try:
        d = datetime.strptime(dob, "%Y-%m-%d").date()
        t = now().date()
        return t.year - d.year - ((t.month, t.day) < (d.month, d.day))
    except Exception:
        return None


def is_minor(u):
    a = age_of(u.get("dob") or "")
    return a is not None and a < 18


async def llm_text(system: str, prompt: str, session: str, images=None) -> str:
    from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
    chat = LlmChat(api_key=LLM_KEY, session_id=session, system_message=system).with_model("anthropic", AI_MODEL)
    msg = UserMessage(text=prompt, file_contents=[ImageContent(image_base64=b) for b in (images or [])] or None)
    return await chat.send_message(msg)
