import os, json, asyncio
from datetime import timedelta, datetime
from typing import Optional, List
from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import BaseModel, Field
from pymongo import ReturnDocument
from core import db, now, uid, log, audit, current_user, ADMIN, ledger, send_email, sanitize_error

router = APIRouter(prefix="/api")

PLAN_DEFAULTS = dict(currency="INR", period_days=30, credits=5, videos_per_analysis=1, max_duration_s=30, max_file_mb=100,
                     report_level="detailed", pdf_export=True, history_access=True, comparisons=True, timeline=True, multi_angle=False,
                     ai_coach=True, training_planner=True, academy_features=False, active=True, billing="monthly", sort=10, description="")
SEED_PLANS = [
    {"slug": "batting-monthly", "name": "Batting", "product": "batting", "price_inr": 499, "analysis_types": ["batting"], "sort": 1,
     "description": "One video of any length per batting analysis."},
    {"slug": "bowling-monthly", "name": "Bowling", "product": "bowling", "price_inr": 599, "analysis_types": ["bowling"], "sort": 2,
     "videos_per_analysis": 3, "multi_angle": True, "description": "Up to three angles of any length per bowling analysis."},
    {"slug": "combined-monthly", "name": "All-Rounder", "product": "combined", "price_inr": 899, "analysis_types": ["batting", "bowling"],
     "credits": 10, "videos_per_analysis": 3, "multi_angle": True, "report_level": "advanced", "sort": 3,
     "description": "Batting and bowling with advanced coaching reports."},
]


async def seed_plans():
    if await db.plans.count_documents({}) == 0:
        for p in SEED_PLANS:
            await db.plans.insert_one({"id": uid(), **PLAN_DEFAULTS, **p, "created_at": now(), "placeholder_price": True})


def rzp():
    import razorpay
    kid, ks = os.environ.get("RAZORPAY_KEY_ID"), os.environ.get("RAZORPAY_KEY_SECRET")
    if not kid or not ks:
        raise HTTPException(503, "Payments are not configured yet. Please try again later.")
    return razorpay.Client(auth=(kid, ks))


@router.get("/plans")
async def plans():
    return await db.plans.find({"active": True}, {"_id": 0}).sort("sort", 1).to_list(50)


class PlanIn(BaseModel):
    name: str
    slug: str
    product: str
    billing: str = "monthly"
    price_inr: float = Field(ge=0)
    currency: str = "INR"
    period_days: int = Field(ge=1, le=3660)
    credits: int = Field(ge=0)
    videos_per_analysis: int = Field(ge=1, le=3)
    max_duration_s: int = Field(ge=5, le=300)
    max_file_mb: int = Field(ge=5, le=500)
    analysis_types: List[str]
    report_level: str = "detailed"
    pdf_export: bool = True
    history_access: bool = True
    comparisons: bool = True
    timeline: bool = True
    multi_angle: bool = False
    ai_coach: bool = True
    training_planner: bool = True
    academy_features: bool = False
    active: bool = True
    sort: int = 10
    description: str = ""
    valid_until: Optional[str] = None


@router.get("/admin/plans")
async def admin_plans(a=Depends(ADMIN)):
    return await db.plans.find({}, {"_id": 0}).sort("sort", 1).to_list(100)


@router.post("/admin/plans")
async def create_plan(body: PlanIn, request: Request, a=Depends(ADMIN)):
    if await db.plans.find_one({"slug": body.slug}):
        raise HTTPException(409, "A plan with this slug already exists.")
    doc = {"id": uid(), **body.model_dump(), "created_at": now()}
    await db.plans.insert_one(doc)
    await audit(a["id"], "plan.created", doc["id"], body.model_dump(), request)
    doc.pop("_id", None)
    return doc


@router.put("/admin/plans/{pid}")
async def update_plan(pid: str, body: PlanIn, request: Request, a=Depends(ADMIN)):
    r = await db.plans.update_one({"id": pid}, {"$set": {**body.model_dump(), "updated_at": now(), "placeholder_price": False}})
    if not r.matched_count:
        raise HTTPException(404, "Plan not found.")
    await audit(a["id"], "plan.updated", pid, body.model_dump(), request)
    return {"ok": True}


# ---------- coupons ----------
class CouponIn(BaseModel):
    code: str = Field(min_length=3, max_length=30)
    kind: str = "percent"
    value: float = Field(gt=0)
    plan_ids: List[str] = []
    max_uses: int = 100
    expires_at: Optional[str] = None
    active: bool = True


@router.get("/admin/coupons")
async def list_coupons(a=Depends(ADMIN)):
    return await db.coupons.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)


@router.post("/admin/coupons")
async def save_coupon(body: CouponIn, request: Request, a=Depends(ADMIN)):
    code = body.code.strip().upper()
    if body.kind == "percent" and body.value > 100:
        raise HTTPException(422, "Percent discount can't exceed 100.")
    await db.coupons.update_one({"code": code}, {"$set": {**body.model_dump(), "code": code, "updated_at": now()},
                                                 "$setOnInsert": {"id": uid(), "uses": 0, "created_at": now()}}, upsert=True)
    await audit(a["id"], "coupon.saved", code, request=request)
    return {"ok": True}


async def apply_coupon(code, plan):
    if not code:
        return plan["price_inr"], None
    c = await db.coupons.find_one({"code": code.strip().upper(), "active": True})
    if not c or c["uses"] >= c["max_uses"] or (c.get("plan_ids") and plan["id"] not in c["plan_ids"]) or \
            (c.get("expires_at") and datetime.fromisoformat(c["expires_at"][:10] + "T23:59:59+00:00") < now()):
        raise HTTPException(422, "This coupon is invalid or has expired.")
    price = plan["price_inr"] * (1 - c["value"] / 100) if c["kind"] == "percent" else plan["price_inr"] - c["value"]
    return max(round(price, 2), 0), c["code"]


class OrderIn(BaseModel):
    plan_id: str
    coupon: Optional[str] = None


@router.post("/billing/quote")
async def quote(body: OrderIn, u=Depends(current_user)):
    plan = await db.plans.find_one({"id": body.plan_id, "active": True})
    if not plan:
        raise HTTPException(404, "Plan not found.")
    price, code = await apply_coupon(body.coupon, plan)
    return {"price_inr": price, "coupon": code, "original_inr": plan["price_inr"]}


@router.post("/billing/order")
async def create_order(body: OrderIn, u=Depends(current_user)):
    plan = await db.plans.find_one({"id": body.plan_id, "active": True}, {"_id": 0})
    if not plan:
        raise HTTPException(404, "Plan not found.")
    if plan.get("valid_until") and datetime.fromisoformat(plan["valid_until"][:10] + "T23:59:59+00:00") < now():
        raise HTTPException(422, "This offer has ended.")
    price, code = await apply_coupon(body.coupon, plan)
    if price < 1:
        raise HTTPException(422, "Order total must be at least ₹1.")
    pay_id = uid()
    try:
        order = await asyncio.to_thread(rzp().order.create, {"amount": int(round(price * 100)), "currency": plan["currency"],
                                                             "receipt": pay_id[:40], "notes": {"user_id": u["id"], "plan_id": plan["id"]}})
    except HTTPException:
        raise
    except Exception as e:
        log.warning(f"razorpay order failed {sanitize_error(e)}")
        raise HTTPException(502, "We couldn't start the payment. Please try again.")
    await db.payments.insert_one({"id": pay_id, "user_id": u["id"], "plan_id": plan["id"], "plan_name": plan["name"], "amount_inr": price,
                                  "currency": plan["currency"], "coupon": code, "provider": "razorpay", "order_id": order["id"],
                                  "status": "created", "created_at": now()})
    return {"key_id": os.environ["RAZORPAY_KEY_ID"], "order_id": order["id"], "amount": order["amount"], "currency": order["currency"],
            "name": "CricAnalyze", "description": plan["name"], "prefill": {"name": u["full_name"], "email": u["email"]}}


async def activate(payment, provider_payment_id, source):
    p = await db.payments.find_one_and_update({"id": payment["id"], "status": {"$in": ["created", "failed"]}},
                                              {"$set": {"status": "paid", "payment_id": provider_payment_id, "paid_at": now(), "verified_by": source}},
                                              return_document=ReturnDocument.AFTER)
    if not p:
        return False
    plan = await db.plans.find_one({"id": p["plan_id"]}, {"_id": 0})
    current = await db.subscriptions.find_one({"user_id": p["user_id"], "plan_id": plan["id"], "status": "active", "expires_at": {"$gt": now()}})
    start = current["expires_at"] if current else now()
    sub = {"id": uid(), "user_id": p["user_id"], "plan_id": plan["id"], "plan_name": plan["name"], "plan_snapshot": plan, "payment_id": p["id"],
           "credits_total": plan["credits"], "credits_remaining": plan["credits"], "starts_at": start,
           "expires_at": start + timedelta(days=plan["period_days"]), "status": "active", "auto_renew": False, "created_at": now()}
    await db.subscriptions.insert_one(sub)
    await ledger(p["user_id"], plan["credits"], "subscription_purchase", p["id"], sub["id"])
    if p.get("coupon"):
        await db.coupons.update_one({"code": p["coupon"]}, {"$inc": {"uses": 1}})
    user = await db.users.find_one({"id": p["user_id"]})
    await send_email(user["email"], "receipt", {"amount": f"₹{p['amount_inr']}", "plan": plan["name"], "payment_id": provider_payment_id}, user["id"])
    await audit(p["user_id"], "subscription.activated", sub["id"], {"source": source})
    return True


class VerifyIn(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


@router.post("/billing/verify")
async def verify(body: VerifyIn, u=Depends(current_user)):
    p = await db.payments.find_one({"order_id": body.razorpay_order_id, "user_id": u["id"]})
    if not p:
        raise HTTPException(404, "Order not found.")
    if p["status"] == "paid":
        return {"ok": True, "status": "paid"}
    client = rzp()
    try:
        client.utility.verify_payment_signature(body.model_dump())
    except Exception:
        await db.payments.update_one({"id": p["id"]}, {"$set": {"status": "failed", "failure": "signature_mismatch"}})
        raise HTTPException(400, "Payment verification failed. You have not been charged for a subscription.")
    try:
        rp = await asyncio.to_thread(client.payment.fetch, body.razorpay_payment_id)
    except Exception:
        raise HTTPException(502, "We couldn't confirm the payment with Razorpay yet. It will activate automatically once confirmed.")
    if rp.get("order_id") != p["order_id"] or rp.get("status") not in ("captured", "authorized") or int(rp.get("amount", 0)) != int(round(p["amount_inr"] * 100)):
        raise HTTPException(400, "Payment is not confirmed yet.")
    await activate(p, body.razorpay_payment_id, "client_verify+api_fetch")
    return {"ok": True, "status": "paid"}


@router.post("/billing/webhook")
async def webhook(request: Request):
    secret = os.environ.get("RAZORPAY_WEBHOOK_SECRET")
    if not secret:
        raise HTTPException(503, "Webhook secret not configured.")
    raw = (await request.body()).decode()
    sig = request.headers.get("x-razorpay-signature", "")
    import hmac, hashlib
    if not hmac.compare_digest(hmac.new(secret.encode(), raw.encode(), hashlib.sha256).hexdigest(), sig):
        raise HTTPException(400, "Invalid signature.")
    evt = json.loads(raw)
    eid = request.headers.get("x-razorpay-event-id") or f"{evt.get('event')}:{evt.get('created_at')}:{hashlib.sha256(raw.encode()).hexdigest()[:16]}"
    try:
        await db.webhook_events.insert_one({"_id": eid, "event": evt.get("event"), "received_at": now()})
    except Exception:
        return {"ok": True, "duplicate": True}
    ent = (evt.get("payload", {}).get("payment") or {}).get("entity") or {}
    name = evt.get("event")
    if name in ("payment.captured", "order.paid") and ent.get("order_id"):
        p = await db.payments.find_one({"order_id": ent["order_id"]})
        if p and int(ent.get("amount", 0)) == int(round(p["amount_inr"] * 100)):
            await activate(p, ent["id"], "webhook")
    elif name == "payment.failed" and ent.get("order_id"):
        p = await db.payments.find_one_and_update({"order_id": ent["order_id"], "status": "created"},
                                                  {"$set": {"status": "failed", "failure": (ent.get("error_description") or "")[:200]}})
        if p:
            user = await db.users.find_one({"id": p["user_id"]})
            await send_email(user["email"], "payment_failed", {"plan": p["plan_name"]}, user["id"])
    elif name in ("refund.processed", "refund.created"):
        rf = (evt.get("payload", {}).get("refund") or {}).get("entity") or {}
        await mark_refunded(rf.get("payment_id"), rf.get("id"), rf.get("amount"))
    return {"ok": True}


async def mark_refunded(provider_payment_id, refund_id, amount_paise):
    p = await db.payments.find_one_and_update({"payment_id": provider_payment_id, "status": {"$ne": "refunded"}},
                                              {"$set": {"status": "refunded", "refund_id": refund_id, "refunded_inr": (amount_paise or 0) / 100, "refunded_at": now()}})
    if p:
        sub = await db.subscriptions.find_one_and_update({"payment_id": p["id"], "status": "active"}, {"$set": {"status": "refunded", "credits_remaining": 0}})
        if sub:
            await ledger(p["user_id"], -sub["credits_remaining"], "refund_revoked", p["id"], sub["id"])


@router.get("/billing/payments")
async def my_payments(u=Depends(current_user)):
    return await db.payments.find({"user_id": u["id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)


@router.get("/billing/subscriptions")
async def my_subs(u=Depends(current_user)):
    return await db.subscriptions.find({"user_id": u["id"]}, {"_id": 0, "plan_snapshot": 0}).sort("created_at", -1).to_list(100)


@router.get("/billing/ledger")
async def my_ledger(u=Depends(current_user)):
    return await db.credit_ledger.find({"user_id": u["id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)


@router.post("/billing/subscriptions/{sid}/cancel")
async def cancel_sub(sid: str, request: Request, u=Depends(current_user)):
    r = await db.subscriptions.update_one({"id": sid, "user_id": u["id"], "status": "active"}, {"$set": {"auto_renew": False, "cancel_requested_at": now()}})
    if not r.matched_count:
        raise HTTPException(404, "Subscription not found.")
    await audit(u["id"], "subscription.cancel", sid, request=request)
    return {"ok": True, "message": "Your plan stays active until its expiry date and won't renew."}


# ---------- admin billing ----------
@router.get("/admin/payments")
async def admin_payments(status: Optional[str] = None, a=Depends(ADMIN)):
    q = {"status": status} if status else {}
    return await db.payments.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)


class RefundIn(BaseModel):
    confirm: bool
    amount_inr: Optional[float] = None


@router.post("/admin/payments/{pid}/refund")
async def admin_refund(pid: str, body: RefundIn, request: Request, a=Depends(ADMIN)):
    if not body.confirm:
        raise HTTPException(422, "Confirmation required.")
    p = await db.payments.find_one({"id": pid, "status": "paid"})
    if not p:
        raise HTTPException(404, "Paid payment not found.")
    amt = int(round((body.amount_inr or p["amount_inr"]) * 100))
    try:
        rf = await asyncio.to_thread(rzp().payment.refund, p["payment_id"], {"amount": amt})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"Refund failed: {sanitize_error(e)}")
    await mark_refunded(p["payment_id"], rf.get("id"), amt)
    await audit(a["id"], "payment.refund", pid, {"amount_paise": amt}, request)
    return {"ok": True}


class GrantIn(BaseModel):
    user_id: str
    plan_id: str
    credits: Optional[int] = None
    days: Optional[int] = None
    reason: str = Field(min_length=3)


@router.post("/admin/grant")
async def admin_grant(body: GrantIn, request: Request, a=Depends(ADMIN)):
    plan = await db.plans.find_one({"id": body.plan_id}, {"_id": 0})
    if not plan or not await db.users.find_one({"id": body.user_id}):
        raise HTTPException(404, "User or plan not found.")
    cr = body.credits if body.credits is not None else plan["credits"]
    sub = {"id": uid(), "user_id": body.user_id, "plan_id": plan["id"], "plan_name": plan["name"] + " (granted)", "plan_snapshot": plan,
           "payment_id": None, "credits_total": cr, "credits_remaining": cr, "starts_at": now(),
           "expires_at": now() + timedelta(days=body.days or plan["period_days"]), "status": "active", "granted_by": a["id"], "created_at": now()}
    await db.subscriptions.insert_one(sub)
    await ledger(body.user_id, cr, f"admin_grant: {body.reason}", None, sub["id"], a["id"])
    await audit(a["id"], "subscription.granted", body.user_id, {"plan": plan["slug"], "credits": cr}, request)
    return {"ok": True, "subscription_id": sub["id"]}


@router.get("/admin/ledger")
async def admin_ledger(user_id: Optional[str] = None, a=Depends(ADMIN)):
    return await db.credit_ledger.find({"user_id": user_id} if user_id else {}, {"_id": 0}).sort("created_at", -1).to_list(500)


async def expire_subscriptions():
    await db.subscriptions.update_many({"status": "active", "expires_at": {"$lte": now()}}, {"$set": {"status": "expired"}})
