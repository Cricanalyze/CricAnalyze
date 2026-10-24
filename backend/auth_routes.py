import os, re, json, secrets, base64
from datetime import timedelta
from typing import Optional
from fastapi import APIRouter, Request, Response, HTTPException, Depends, UploadFile, File
from pydantic import BaseModel, EmailStr, Field
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from core import (db, ph, now, uid, hsign, norm_email, client_ip, rate_limit, audit, create_session, clear_session_cookies,
                  session_from_request, current_user, public_user, issue_otp, verify_otp, send_email, require_step_up,
                  get_settings, SELF_SIGNUP_ROLES, put_object, BUCKET_PREFIX, sign_media, is_minor, entitlements)

router = APIRouter(prefix="/api")
GENERIC = "If the details are valid, we've emailed a 6-digit code. Check your inbox (and spam folder)."
LOCK_AFTER = 5


def check_password(pw: str):
    if len(pw) < 8 or not re.search(r"[A-Za-z]", pw) or not re.search(r"\d", pw):
        raise HTTPException(422, "Password must be at least 8 characters and include a letter and a number.")


class SignupIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=80)
    email: EmailStr
    password: str = Field(max_length=128)
    role: str = "player"
    accept_terms: bool


class EmailCode(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6)


class EmailOnly(BaseModel):
    email: EmailStr
    purpose: str = "verify_email"


class LoginIn(BaseModel):
    email: EmailStr
    password: str


async def bootstrap_admin(user):
    admins = {e.strip().lower() for e in os.environ.get("ADMIN_EMAIL", "").split(",") if e.strip()}
    if user["email"] in admins and user.get("email_verified") and user["role"] != "super_admin":
        await db.users.update_one({"id": user["id"]}, {"$set": {"role": "super_admin"}})
        await audit(user["id"], "admin.bootstrap", user["id"])


async def login_response(response: Response, user_id: str, request: Request):
    await create_session(response, user_id, request)
    await db.users.update_one({"id": user_id}, {"$set": {"last_login_at": now(), "failed_logins": 0, "locked_until": None}})
    u = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    return {"user": public_user(u)}


@router.post("/auth/signup")
async def signup(body: SignupIn, request: Request):
    await rate_limit(f"signup:{client_ip(request)}", 10, 3600)
    if not body.accept_terms:
        raise HTTPException(422, "Please accept the Terms and Privacy Policy to continue.")
    if body.role not in SELF_SIGNUP_ROLES:
        raise HTTPException(422, "Invalid account type.")
    check_password(body.password)
    email = norm_email(body.email)
    existing = await db.users.find_one({"email": email})
    if existing and existing.get("email_verified"):
        return {"ok": True, "message": GENERIC}
    if not existing:
        await db.users.insert_one({"id": uid(), "email": email, "full_name": body.full_name.strip(), "role": body.role,
                                   "password_hash": ph.hash(body.password), "email_verified": False, "status": "active",
                                   "created_at": now(), "profile": {}, "privacy": {"leaderboard_opt_in": False},
                                   "terms_accepted_at": now()})
    else:
        await db.users.update_one({"id": existing["id"], "email_verified": False}, {"$set": {
            "password_hash": ph.hash(body.password), "full_name": body.full_name.strip(), "role": body.role, "terms_accepted_at": now()}})
    await issue_otp(email, "verify_email", request)
    return {"ok": True, "message": GENERIC}


@router.post("/auth/verify-email")
async def verify_email(body: EmailCode, request: Request, response: Response):
    await rate_limit(f"verify:{client_ip(request)}", 30, 900)
    email = norm_email(body.email)
    await verify_otp(email, "verify_email", body.code)
    user = await db.users.find_one({"email": email, "deleted": {"$ne": True}})
    if not user:
        raise HTTPException(400, "Invalid or already-used code. Please request a new one.")
    await db.users.update_one({"id": user["id"]}, {"$set": {"email_verified": True, "email_verified_at": now()}})
    user["email_verified"] = True
    await bootstrap_admin(user)
    await send_email(email, "welcome", {}, user["id"])
    return await login_response(response, user["id"], request)


@router.post("/auth/resend")
async def resend(body: EmailOnly, request: Request):
    email = norm_email(body.email)
    if body.purpose not in ("verify_email", "login_otp", "reset_password"):
        raise HTTPException(422, "Invalid request.")
    user = await db.users.find_one({"email": email, "deleted": {"$ne": True}})
    if user and (body.purpose != "verify_email" or not user.get("email_verified")):
        await issue_otp(email, body.purpose, request)
    return {"ok": True, "message": GENERIC}


@router.post("/auth/login")
async def login(body: LoginIn, request: Request, response: Response):
    email = norm_email(body.email)
    await rate_limit(f"login:{client_ip(request)}", 30, 900)
    await rate_limit(f"loginemail:{email}", 15, 900)
    user = await db.users.find_one({"email": email, "deleted": {"$ne": True}})
    bad = HTTPException(401, "Incorrect email or password.")
    if not user:
        ph.hash(body.password)
        raise bad
    if user.get("locked_until") and user["locked_until"] > now():
        raise HTTPException(429, "Too many failed attempts. Try again in 15 minutes or reset your password.")
    try:
        ph.verify(user["password_hash"], body.password)
    except (VerifyMismatchError, InvalidHashError):
        fails = user.get("failed_logins", 0) + 1
        upd = {"failed_logins": fails}
        if fails >= LOCK_AFTER:
            upd = {"failed_logins": 0, "locked_until": now() + timedelta(minutes=15)}
            await audit(user["id"], "auth.lockout", user["id"], request=request)
        await db.users.update_one({"id": user["id"]}, {"$set": upd})
        raise bad
    if user.get("status") == "suspended":
        raise HTTPException(403, "This account is suspended. Contact support.")
    if not user.get("email_verified"):
        await issue_otp(email, "verify_email", request)
        raise HTTPException(403, "email_unverified")
    settings = await get_settings()
    if settings["flags"]["require_otp_every_login"] or user.get("otp_login_required"):
        await issue_otp(email, "login_otp", request)
        return {"otp_required": True, "message": GENERIC}
    await audit(user["id"], "auth.login", request=request)
    return await login_response(response, user["id"], request)


@router.post("/auth/login/otp/request")
async def otp_login_request(body: EmailOnly, request: Request):
    if not (await get_settings())["flags"]["otp_login"]:
        raise HTTPException(403, "Email-code sign-in is disabled.")
    email = norm_email(body.email)
    user = await db.users.find_one({"email": email, "deleted": {"$ne": True}, "email_verified": True})
    if user:
        await issue_otp(email, "login_otp", request)
    return {"ok": True, "message": GENERIC}


@router.post("/auth/login/otp/verify")
async def otp_login_verify(body: EmailCode, request: Request, response: Response):
    await rate_limit(f"verify:{client_ip(request)}", 30, 900)
    email = norm_email(body.email)
    await verify_otp(email, "login_otp", body.code)
    user = await db.users.find_one({"email": email, "deleted": {"$ne": True}})
    if not user or user.get("status") == "suspended":
        raise HTTPException(401, "Unable to sign in.")
    await audit(user["id"], "auth.login_otp", request=request)
    return await login_response(response, user["id"], request)


@router.post("/auth/logout")
async def logout(request: Request, response: Response):
    s = await session_from_request(request)
    if s:
        await db.sessions.update_one({"id": s["id"]}, {"$set": {"revoked": True}})
    clear_session_cookies(response)
    return {"ok": True}


@router.get("/auth/me")
async def me(u=Depends(current_user)):
    return {"user": public_user(u), "entitlements": await entitlements(u["id"]), "flags": (await get_settings())["flags"]}


class ForgotIn(BaseModel):
    email: EmailStr


@router.post("/auth/forgot")
async def forgot(body: ForgotIn, request: Request):
    email = norm_email(body.email)
    await rate_limit(f"forgot:{client_ip(request)}", 10, 3600)
    user = await db.users.find_one({"email": email, "deleted": {"$ne": True}})
    if user:
        await issue_otp(email, "reset_password", request)
    return {"ok": True, "message": GENERIC}


@router.post("/auth/reset/verify")
async def reset_verify(body: EmailCode, request: Request):
    await rate_limit(f"verify:{client_ip(request)}", 30, 900)
    email = norm_email(body.email)
    await verify_otp(email, "reset_password", body.code)
    user = await db.users.find_one({"email": email, "deleted": {"$ne": True}})
    if not user:
        raise HTTPException(400, "Invalid or already-used code. Please request a new one.")
    token = secrets.token_urlsafe(32)
    await db.password_reset_tokens.update_many({"user_id": user["id"], "used": False}, {"$set": {"used": True}})
    await db.password_reset_tokens.insert_one({"id": uid(), "user_id": user["id"], "token_hash": hsign(token), "used": False,
                                               "created_at": now(), "expires_at": now() + timedelta(minutes=15)})
    return {"reset_token": token}


class ResetIn(BaseModel):
    reset_token: str
    new_password: str = Field(max_length=128)


@router.post("/auth/reset")
async def reset(body: ResetIn, request: Request):
    check_password(body.new_password)
    rec = await db.password_reset_tokens.find_one_and_update(
        {"token_hash": hsign(body.reset_token), "used": False, "expires_at": {"$gt": now()}}, {"$set": {"used": True, "used_at": now()}})
    if not rec:
        raise HTTPException(400, "This reset link has expired or was already used. Please start again.")
    user = await db.users.find_one({"id": rec["user_id"]})
    await db.users.update_one({"id": user["id"]}, {"$set": {"password_hash": ph.hash(body.new_password), "failed_logins": 0,
                                                            "locked_until": None, "email_verified": True}})
    await db.sessions.update_many({"user_id": user["id"]}, {"$set": {"revoked": True}})
    await audit(user["id"], "auth.password_reset", request=request)
    await send_email(user["email"], "password_changed", {}, user["id"])
    return {"ok": True, "message": "Password updated. Please sign in with your new password."}


# ---------- sessions & step-up ----------
@router.get("/auth/sessions")
async def sessions(u=Depends(current_user)):
    rows = await db.sessions.find({"user_id": u["id"], "revoked": False, "expires_at": {"$gt": now()}},
                                  {"_id": 0, "token_hash": 0}).sort("created_at", -1).to_list(50)
    for r in rows:
        r["current"] = r["id"] == u["_session"]["id"]
    return rows


@router.delete("/auth/sessions/{sid}")
async def revoke_session(sid: str, u=Depends(current_user)):
    await db.sessions.update_one({"id": sid, "user_id": u["id"]}, {"$set": {"revoked": True}})
    return {"ok": True}


@router.post("/auth/sessions/revoke-others")
async def revoke_others(u=Depends(current_user)):
    await db.sessions.update_many({"user_id": u["id"], "id": {"$ne": u["_session"]["id"]}}, {"$set": {"revoked": True}})
    return {"ok": True}


@router.post("/auth/step-up/request")
async def step_up_request(request: Request, u=Depends(current_user)):
    await issue_otp(u["email"], "step_up", request)
    return {"ok": True, "message": "We've emailed you a confirmation code."}


class CodeOnly(BaseModel):
    code: str = Field(min_length=6, max_length=6)


@router.post("/auth/step-up/verify")
async def step_up_verify(body: CodeOnly, u=Depends(current_user)):
    await verify_otp(u["email"], "step_up", body.code)
    await db.sessions.update_one({"id": u["_session"]["id"]}, {"$set": {"step_up_until": now() + timedelta(minutes=10)}})
    return {"ok": True}


class ChangePw(BaseModel):
    current_password: str
    new_password: str = Field(max_length=128)


@router.post("/auth/change-password")
async def change_password(body: ChangePw, request: Request, u=Depends(current_user)):
    full = await db.users.find_one({"id": u["id"]})
    try:
        ph.verify(full["password_hash"], body.current_password)
    except (VerifyMismatchError, InvalidHashError):
        raise HTTPException(400, "Current password is incorrect.")
    check_password(body.new_password)
    await db.users.update_one({"id": u["id"]}, {"$set": {"password_hash": ph.hash(body.new_password)}})
    await db.sessions.update_many({"user_id": u["id"], "id": {"$ne": u["_session"]["id"]}}, {"$set": {"revoked": True}})
    await audit(u["id"], "auth.password_change", request=request)
    await send_email(u["email"], "password_changed", {}, u["id"])
    return {"ok": True}


class NewEmail(BaseModel):
    new_email: EmailStr


@router.post("/auth/change-email/request")
async def change_email_request(body: NewEmail, request: Request, u=Depends(current_user)):
    require_step_up(u)
    new = norm_email(body.new_email)
    if await db.users.find_one({"email": new}):
        raise HTTPException(409, "That email can't be used. Try a different address.")
    await db.users.update_one({"id": u["id"]}, {"$set": {"pending_email": new}})
    await issue_otp(new, "change_email", request)
    return {"ok": True, "message": f"We've sent a code to {new}."}


@router.post("/auth/change-email/confirm")
async def change_email_confirm(body: CodeOnly, request: Request, u=Depends(current_user)):
    new = u.get("pending_email")
    if not new:
        raise HTTPException(400, "No email change is pending.")
    await verify_otp(new, "change_email", body.code)
    await db.users.update_one({"id": u["id"]}, {"$set": {"email": new, "email_verified": True}, "$unset": {"pending_email": ""}})
    await send_email(u["email"], "notice", {"message": f"Your CricAnalyze login email was changed to {new}."}, u["id"])
    await audit(u["id"], "account.email_change", meta={"old": u["email"], "new": new}, request=request)
    return {"ok": True}


# ---------- account / profile ----------
PROFILE_FIELDS = {"phone", "dob", "playing_role", "batting_style", "bowling_style", "experience_level", "preferred_format",
                  "coaching_goals", "practice_minutes_per_week"}


class ProfileIn(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=80)
    profile: dict = {}
    privacy: dict = {}
    otp_login_required: Optional[bool] = None


@router.patch("/account/profile")
async def update_profile(body: ProfileIn, u=Depends(current_user)):
    upd = {}
    if body.full_name:
        upd["full_name"] = body.full_name.strip()
    for k, v in body.profile.items():
        if k in PROFILE_FIELDS:
            if k == "dob":
                upd["dob"] = str(v)[:10] or None
            else:
                upd[f"profile.{k}"] = str(v)[:500] if v is not None else None
    for k in ("leaderboard_opt_in", "share_passport", "product_emails"):
        if k in body.privacy:
            upd[f"privacy.{k}"] = bool(body.privacy[k])
    if body.otp_login_required is not None:
        upd["otp_login_required"] = body.otp_login_required
    if upd:
        await db.users.update_one({"id": u["id"]}, {"$set": upd})
    return {"user": public_user(await db.users.find_one({"id": u["id"]}, {"_id": 0, "password_hash": 0}))}


@router.post("/account/avatar")
async def upload_avatar(file: UploadFile = File(...), u=Depends(current_user)):
    data = await file.read(3 * 1024 * 1024 + 1)
    if len(data) > 3 * 1024 * 1024:
        raise HTTPException(413, "Image must be under 3 MB.")
    kind = "image/png" if data[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg" if data[:3] == b"\xff\xd8\xff" else "image/webp" if data[8:12] == b"WEBP" else None
    if not kind:
        raise HTTPException(415, "Please upload a JPG, PNG or WEBP image.")
    aid = uid()
    res = put_object(f"{BUCKET_PREFIX}/avatars/{u['id']}/{aid}", data, kind)
    await db.media_assets.insert_one({"id": aid, "user_id": u["id"], "kind": "avatar", "storage_path": res["path"],
                                      "content_type": kind, "size": len(data), "public": True, "is_deleted": False, "created_at": now()})
    await db.users.update_one({"id": u["id"]}, {"$set": {"avatar_id": aid}})
    return {"avatar_id": aid}


class GuardianIn(BaseModel):
    guardian_name: str = Field(min_length=2, max_length=80)
    guardian_email: EmailStr


@router.post("/account/guardian/request")
async def guardian_request(body: GuardianIn, request: Request, u=Depends(current_user)):
    ge = norm_email(body.guardian_email)
    if ge == u["email"]:
        raise HTTPException(422, "The guardian email must be different from your own.")
    await db.users.update_one({"id": u["id"]}, {"$set": {"guardian": {"name": body.guardian_name, "email": ge, "consent_at": None}}})
    await issue_otp(f"guardian:{u['id']}", "guardian_consent", request, ctx={"player": u["full_name"]}, send_to=ge)
    return {"ok": True, "message": f"We emailed a consent code to {ge}."}


@router.post("/account/guardian/confirm")
async def guardian_confirm(body: CodeOnly, request: Request, u=Depends(current_user)):
    await verify_otp(f"guardian:{u['id']}", "guardian_consent", body.code)
    await db.users.update_one({"id": u["id"]}, {"$set": {"guardian.consent_at": now()}})
    await audit(u["id"], "consent.guardian_granted", request=request)
    return {"ok": True}


@router.get("/account/export")
async def export_data(u=Depends(current_user)):
    q = {"user_id": u["id"]}
    out = {"user": public_user(u)}
    for c in ("subscriptions", "payments", "credit_ledger", "analysis_jobs", "analysis_reports", "training_plans",
              "training_completions", "coach_messages", "academy_memberships"):
        out[c] = await db[c].find(q, {"_id": 0}).to_list(5000)
    out["video_assets"] = await db.video_assets.find(q, {"_id": 0, "storage_path": 0}).to_list(5000)
    return Response(json.dumps(out, default=str, indent=1), media_type="application/json",
                    headers={"Content-Disposition": "attachment; filename=cricanalyze-export.json"})


@router.delete("/account")
async def delete_account(request: Request, response: Response, u=Depends(current_user)):
    require_step_up(u)
    if u["role"] == "super_admin" and await db.users.count_documents({"role": "super_admin", "deleted": {"$ne": True}}) <= 1:
        raise HTTPException(409, "Assign another super administrator before deleting this account.")
    await db.users.update_one({"id": u["id"]}, {"$set": {"deleted": True, "deleted_at": now(), "email": f"deleted-{u['id']}@deleted.invalid",
                                                          "full_name": "Deleted user", "profile": {}, "dob": None, "guardian": None}})
    await db.video_assets.update_many({"user_id": u["id"]}, {"$set": {"is_deleted": True}})
    await db.media_assets.update_many({"user_id": u["id"]}, {"$set": {"is_deleted": True}})
    await db.sessions.update_many({"user_id": u["id"]}, {"$set": {"revoked": True}})
    await db.academy_memberships.update_many({"user_id": u["id"]}, {"$set": {"status": "removed"}})
    await audit(u["id"], "account.deleted", request=request)
    clear_session_cookies(response)
    return {"ok": True}


@router.get("/account/status")
async def account_status(u=Depends(current_user)):
    minor = is_minor(u)
    return {"is_minor": minor, "guardian_consent": bool((u.get("guardian") or {}).get("consent_at")), "needs_dob": not u.get("dob"),
            "avatar_url": sign_media(u["avatar_id"]) if u.get("avatar_id") else None}
