"""Seed verified QA accounts directly (no email OTP). Idempotent. Run: python tests/seed_qa_users.py"""
import asyncio, sys
from datetime import timedelta
sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
from core import db, now, uid, ph

USERS = [("qa.player+qa@cricanalyze.in", "QA Player", "player", "QaPlayer#2026"), ("qa.newplayer+qa@cricanalyze.in", "QA New Player", "player", "QaPlayer#2026"),
         ("qa.admin+qa@cricanalyze.in", "QA Admin", "admin", "QaAdmin#2026")]


async def main():
    plan = await db.plans.find_one({"analysis_types": {"$all": ["batting", "bowling"]}}, {"_id": 0}) or await db.plans.find_one({}, {"_id": 0})
    for email, name, role, pw in USERS:
        u = await db.users.find_one({"email": email})
        if not u:
            u = {"id": uid(), "email": email, "full_name": name, "role": role, "password_hash": ph.hash(pw), "email_verified": True, "status": "active",
                 "created_at": now(), "profile": {"dob": "1995-01-01"}, "privacy": {"leaderboard_opt_in": False}, "terms_accepted_at": now()}
            await db.users.insert_one(u)
        else:
            await db.users.update_one({"id": u["id"]}, {"$set": {"password_hash": ph.hash(pw), "email_verified": True, "role": role, "failed_logins": 0, "locked_until": None}})
        if role == "player" and plan and not await db.subscriptions.find_one({"user_id": u["id"], "status": "active", "expires_at": {"$gt": now()}}):
            await db.subscriptions.insert_one({"id": uid(), "user_id": u["id"], "plan_id": plan["id"], "plan_name": plan["name"] + " (QA)", "plan_snapshot": plan,
                                               "payment_id": None, "credits_total": 20, "credits_remaining": 20, "starts_at": now(),
                                               "expires_at": now() + timedelta(days=60), "status": "active", "granted_by": "qa_seed", "created_at": now()})
        print("ok", email, role)


asyncio.run(main())
