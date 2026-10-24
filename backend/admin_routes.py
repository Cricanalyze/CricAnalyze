import os, asyncio
from datetime import timedelta
from typing import Optional
from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import BaseModel, Field, EmailStr
from core import (db, now, uid, audit, ADMIN, current_user, optional_user, ROLES, smtp_configured, send_email, get_settings,
                  DEFAULT_SETTINGS, init_storage, LLM_KEY, AI_MODEL, llm_text, sanitize_error, rate_limit, client_ip, public_user)

router = APIRouter(prefix="/api")
RANK = {r: i for i, r in enumerate(ROLES)}


@router.get("/admin/users")
async def users(q: str = "", role: Optional[str] = None, page: int = 1, a=Depends(ADMIN)):
    f = {"deleted": {"$ne": True}}
    if q:
        import re
        f["$or"] = [{"email": {"$regex": re.escape(q), "$options": "i"}}, {"full_name": {"$regex": re.escape(q), "$options": "i"}}]
    if role:
        f["role"] = role
    total = await db.users.count_documents(f)
    rows = await db.users.find(f, {"_id": 0, "password_hash": 0}).sort("created_at", -1).skip((max(page, 1) - 1) * 50).limit(50).to_list(50)
    return {"users": rows, "total": total, "roles": ROLES}


class RoleIn(BaseModel):
    role: Optional[str] = None
    status: Optional[str] = None
    confirm: bool = False


@router.patch("/admin/users/{user_id}")
async def update_user(user_id: str, body: RoleIn, request: Request, a=Depends(ADMIN)):
    if not body.confirm:
        raise HTTPException(422, "Confirmation required.")
    t = await db.users.find_one({"id": user_id, "deleted": {"$ne": True}})
    if not t:
        raise HTTPException(404, "User not found.")
    if t["id"] == a["id"]:
        raise HTTPException(409, "You can't change your own role or status.")
    if RANK.get(t["role"], 0) >= RANK[a["role"]] and a["role"] != "super_admin":
        raise HTTPException(403, "You can't modify a user with equal or higher privileges.")
    upd = {}
    if body.role:
        if body.role not in ROLES or (RANK[body.role] >= RANK["admin"] and a["role"] != "super_admin"):
            raise HTTPException(403, "Only a super administrator can grant admin roles.")
        upd["role"] = body.role
    if body.status in ("active", "suspended"):
        upd["status"] = body.status
        if body.status == "suspended":
            await db.sessions.update_many({"user_id": user_id}, {"$set": {"revoked": True}})
    await db.users.update_one({"id": user_id}, {"$set": upd})
    await audit(a["id"], "admin.user_update", user_id, upd, request)
    return {"ok": True}


@router.get("/admin/jobs")
async def jobs(status: Optional[str] = None, a=Depends(ADMIN)):
    q = {"status": status} if status else {}
    rows = await db.analysis_jobs.find(q, {"_id": 0}).sort("created_at", -1).to_list(300)
    counts = {s: await db.analysis_jobs.count_documents({"status": s}) for s in ("queued", "processing", "completed", "failed")}
    return {"jobs": rows, "counts": counts}


@router.post("/admin/jobs/{jid}/retry")
async def retry_job(jid: str, request: Request, a=Depends(ADMIN)):
    r = await db.analysis_jobs.update_one({"id": jid, "status": "failed"}, {"$set": {"status": "queued", "attempts": 0, "next_run_at": now(), "failure_reason": None}})
    if not r.modified_count:
        raise HTTPException(409, "Only failed jobs can be retried.")
    await audit(a["id"], "admin.job_retry", jid, request=request)
    return {"ok": True, "note": "Retried without charging a new credit."}


async def integration_status():
    rows = {x["_id"]: x for x in await db.integration_status.find().to_list(50)}
    defs = {
        "smtp": ("Hostinger SMTP email", smtp_configured(), {"sender": os.environ.get("SMTP_FROM_EMAIL"), "host": os.environ.get("SMTP_HOST")}),
        "ai": ("AI analysis provider", bool(LLM_KEY) and os.environ.get("AI_INFERENCE_PROVIDER", "vision_llm") == "vision_llm",
               {"provider": os.environ.get("AI_INFERENCE_PROVIDER", "vision_llm"), "model": AI_MODEL}),
        "gpu_inference": ("Hosted GPU pose inference (RunPod etc.)", bool(os.environ.get("AI_INFERENCE_ENDPOINT") and os.environ.get("AI_INFERENCE_API_KEY")), {}),
        "storage": ("Private object storage", bool(LLM_KEY), {"provider": os.environ.get("VIDEO_STORAGE_PROVIDER", "emergent")}),
        "razorpay": ("Razorpay payments", bool(os.environ.get("RAZORPAY_KEY_ID") and os.environ.get("RAZORPAY_KEY_SECRET")),
                     {"mode": "test" if (os.environ.get("RAZORPAY_KEY_ID") or "").startswith("rzp_test") else "live"}),
        "razorpay_webhook": ("Razorpay webhook secret", bool(os.environ.get("RAZORPAY_WEBHOOK_SECRET")), {"endpoint": "/api/billing/webhook"}),
        "google_analytics": ("Google Analytics", bool(os.environ.get("GA_MEASUREMENT_ID")), {}),
        "search_console": ("Google Search Console", bool(os.environ.get("GSC_VERIFICATION")), {}),
    }
    out = []
    for k, (name, configured, info) in defs.items():
        r = rows.get(k, {})
        out.append({"key": k, "name": name, "configured": configured, "info": info, "last_test": r.get("last_test"),
                    "last_result": r.get("last_result"), "last_message": r.get("last_message"), "last_success": r.get("last_success")})
    return out


@router.get("/admin/integrations")
async def integrations(a=Depends(ADMIN)):
    return await integration_status()


class TestIn(BaseModel):
    to: Optional[EmailStr] = None


@router.post("/admin/integrations/{key}/test")
async def test_integration(key: str, body: TestIn, request: Request, a=Depends(ADMIN)):
    ok, msg = False, ""
    try:
        if key == "smtp":
            if not smtp_configured():
                raise RuntimeError("SMTP settings are missing.")
            ok = await send_email(body.to or a["email"], "test", {}, a["id"])
            last = await db.email_logs.find_one({"template": "test"}, sort=[("created_at", -1)])
            msg = "SMTP server accepted the message (delivery to inbox not confirmed)." if ok else (last or {}).get("error", "Failed")
        elif key == "ai":
            out = await asyncio.wait_for(llm_text("Reply with OK.", "Say OK", f"health-{uid()}"), 40)
            ok, msg = "OK" in out.upper(), "Model responded." if "OK" in out.upper() else "Unexpected reply."
        elif key == "storage":
            await asyncio.to_thread(init_storage, True)
            ok, msg = True, "Storage key initialised."
        elif key == "razorpay":
            from billing_routes import rzp
            await asyncio.to_thread(rzp().order.all, {"count": 1})
            ok, msg = True, "Razorpay API credentials accepted."
        else:
            raise RuntimeError("No test available for this integration.")
    except Exception as e:
        ok, msg = False, sanitize_error(e)
    upd = {"last_test": now(), "last_result": "pass" if ok else "fail", "last_message": msg[:300]}
    if ok:
        upd["last_success"] = now()
    await db.integration_status.update_one({"_id": key}, {"$set": upd}, upsert=True)
    await audit(a["id"], "admin.integration_test", key, {"ok": ok}, request)
    return {"ok": ok, "message": msg}


@router.get("/admin/email-logs")
async def email_logs(a=Depends(ADMIN)):
    return await db.email_logs.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)


@router.get("/admin/settings")
async def settings(a=Depends(ADMIN)):
    return await get_settings()


class SettingsIn(BaseModel):
    flags: dict = {}
    limits: dict = {}
    confirm: bool = False


@router.put("/admin/settings")
async def save_settings(body: SettingsIn, request: Request, a=Depends(ADMIN)):
    if not body.confirm:
        raise HTTPException(422, "Confirmation required.")
    upd = {}
    for k, v in body.flags.items():
        if k in DEFAULT_SETTINGS["flags"]:
            upd[f"flags.{k}"] = bool(v)
    for k, v in body.limits.items():
        if k in DEFAULT_SETTINGS["limits"]:
            upd[f"limits.{k}"] = max(0, float(v)) if k.startswith("est_") or k.endswith("_inr") else max(1, int(v))
    await db.settings.update_one({"_id": "app"}, {"$set": upd}, upsert=True)
    await audit(a["id"], "admin.settings", None, upd, request)
    return await get_settings()


@router.get("/admin/audit")
async def audit_logs(a=Depends(ADMIN)):
    return await db.audit_logs.find({}, {"_id": 0}).sort("created_at", -1).to_list(300)


@router.get("/admin/analytics")
async def analytics(a=Depends(ADMIN)):
    s = await get_settings()
    month = now() - timedelta(days=30)
    analyses_30 = await db.analysis_jobs.count_documents({"status": "completed", "completed_at": {"$gte": month}})
    revenue = await db.payments.aggregate([{"$match": {"status": "paid"}}, {"$group": {"_id": None, "t": {"$sum": "$amount_inr"}}}]).to_list(1)
    est = analyses_30 * s["limits"]["est_cost_per_analysis_inr"]
    days = []
    for i in range(13, -1, -1):
        d0 = (now() - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        days.append({"date": d0.strftime("%d %b"), "signups": await db.users.count_documents({"created_at": {"$gte": d0, "$lt": d0 + timedelta(days=1)}}),
                     "analyses": await db.analysis_jobs.count_documents({"created_at": {"$gte": d0, "$lt": d0 + timedelta(days=1)}})})
    return {"users": await db.users.count_documents({"deleted": {"$ne": True}}),
            "verified_users": await db.users.count_documents({"email_verified": True, "deleted": {"$ne": True}}),
            "active_subscriptions": await db.subscriptions.count_documents({"status": "active", "expires_at": {"$gt": now()}}),
            "analyses_30d": analyses_30, "failed_30d": await db.analysis_jobs.count_documents({"status": "failed", "created_at": {"$gte": month}}),
            "revenue_inr": revenue[0]["t"] if revenue else 0, "est_ai_cost_30d_inr": est,
            "cost_alert": est >= s["limits"]["monthly_cost_alert_inr"], "published_posts": await db.blog_posts.count_documents({"status": "published"}),
            "open_tickets": await db.support_tickets.count_documents({"status": "open"}), "daily": days}


@router.get("/admin/academies")
async def admin_academies(a=Depends(ADMIN)):
    rows = await db.academies.find({}, {"_id": 0}).to_list(500)
    for r in rows:
        r["members"] = await db.academy_memberships.count_documents({"academy_id": r["id"], "status": "active"})
    return rows


# ---------- support ----------
class ContactIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: EmailStr
    subject: str = Field(min_length=2, max_length=120)
    message: str = Field(min_length=10, max_length=3000)
    website: str = ""


@router.post("/contact")
async def contact(body: ContactIn, request: Request):
    await rate_limit(f"contact:{client_ip(request)}", 5, 3600)
    if body.website:
        return {"ok": True}
    u = await optional_user(request)
    await db.support_tickets.insert_one({"id": uid(), **body.model_dump(exclude={"website"}), "user_id": u["id"] if u else None,
                                         "status": "open", "created_at": now()})
    return {"ok": True, "message": "Thanks — your message has been received. We'll reply by email."}


@router.get("/admin/support")
async def tickets(a=Depends(ADMIN)):
    return await db.support_tickets.find({}, {"_id": 0}).sort("created_at", -1).to_list(300)


class TicketIn(BaseModel):
    status: str


@router.patch("/admin/support/{tid}")
async def ticket_update(tid: str, body: TicketIn, a=Depends(ADMIN)):
    await db.support_tickets.update_one({"id": tid}, {"$set": {"status": body.status, "updated_at": now(), "handled_by": a["id"]}})
    return {"ok": True}


@router.get("/public/config")
async def public_config():
    s = await get_settings()
    return {"flags": s["flags"], "ga_id": os.environ.get("GA_MEASUREMENT_ID"), "gsc": os.environ.get("GSC_VERIFICATION"),
            "payments_enabled": bool(os.environ.get("RAZORPAY_KEY_ID"))}


@router.get("/health")
async def health():
    try:
        await db.command("ping")
        dbok = True
    except Exception:
        dbok = False
    q = await db.analysis_jobs.count_documents({"status": "queued"})
    return {"status": "ok" if dbok else "degraded", "database": dbok, "queue_depth": q, "smtp_configured": smtp_configured(), "time": now()}
