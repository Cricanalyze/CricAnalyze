import csv, io, secrets, re
from datetime import timedelta
from typing import Optional, List
from fastapi import APIRouter, Request, Response, HTTPException, Depends
from pydantic import BaseModel, Field, EmailStr
from core import db, now, uid, audit, current_user, send_email, hsign, norm_email, APP_URL, STAFF, is_minor, get_settings

router = APIRouter(prefix="/api")


async def membership(aid, user, roles=None):
    if user["role"] in STAFF:
        return {"role": "academy_admin", "academy_id": aid}
    m = await db.academy_memberships.find_one({"academy_id": aid, "user_id": user["id"], "status": "active"}, {"_id": 0})
    if not m or (roles and m["role"] not in roles):
        raise HTTPException(404, "Academy not found.")
    return m


async def flag_on():
    if not (await get_settings())["flags"]["academy"]:
        raise HTTPException(403, "Academy features are currently disabled.")


class AcademyIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    city: str = ""
    description: str = Field("", max_length=1000)
    contact_email: Optional[EmailStr] = None
    attendance_enabled: bool = True


@router.post("/academies")
async def create_academy(body: AcademyIn, request: Request, u=Depends(current_user)):
    await flag_on()
    if u["role"] not in ("coach", "academy_admin", "admin", "super_admin"):
        raise HTTPException(403, "Only coach or academy accounts can create an academy.")
    aid = uid()
    slug = re.sub(r"[^a-z0-9]+", "-", body.name.lower()).strip("-") + "-" + aid[:5]
    await db.academies.insert_one({"id": aid, "slug": slug, **body.model_dump(), "owner_id": u["id"], "created_at": now()})
    await db.academy_memberships.insert_one({"id": uid(), "academy_id": aid, "user_id": u["id"], "role": "academy_admin", "status": "active", "created_at": now()})
    await audit(u["id"], "academy.created", aid, request=request)
    return {"id": aid}


@router.get("/academies/mine")
async def my_academies(u=Depends(current_user)):
    ms = await db.academy_memberships.find({"user_id": u["id"], "status": "active"}, {"_id": 0}).to_list(50)
    acs = {a["id"]: a for a in await db.academies.find({"id": {"$in": [m["academy_id"] for m in ms]}}, {"_id": 0}).to_list(50)}
    invites = await db.academy_invites.find({"email": u["email"], "status": "pending", "expires_at": {"$gt": now()}}, {"_id": 0, "token_hash": 0}).to_list(20)
    for i in invites:
        i["academy_name"] = (await db.academies.find_one({"id": i["academy_id"]}) or {}).get("name")
    return {"memberships": [{**m, "academy": acs.get(m["academy_id"])} for m in ms], "invites": invites}


@router.get("/academies/{aid}")
async def get_academy(aid: str, u=Depends(current_user)):
    m = await membership(aid, u)
    a = await db.academies.find_one({"id": aid}, {"_id": 0})
    if not a:
        raise HTTPException(404, "Academy not found.")
    return {**a, "my_role": m["role"]}


@router.patch("/academies/{aid}")
async def update_academy(aid: str, body: AcademyIn, u=Depends(current_user)):
    await membership(aid, u, ["academy_admin"])
    await db.academies.update_one({"id": aid}, {"$set": body.model_dump()})
    return {"ok": True}


class InviteIn(BaseModel):
    email: EmailStr
    role: str


@router.post("/academies/{aid}/invites")
async def invite(aid: str, body: InviteIn, request: Request, u=Depends(current_user)):
    await membership(aid, u, ["academy_admin"])
    if body.role not in ("coach", "player"):
        raise HTTPException(422, "Role must be coach or player.")
    a = await db.academies.find_one({"id": aid})
    token = secrets.token_urlsafe(24)
    email = norm_email(body.email)
    await db.academy_invites.update_many({"academy_id": aid, "email": email, "status": "pending"}, {"$set": {"status": "superseded"}})
    await db.academy_invites.insert_one({"id": uid(), "academy_id": aid, "email": email, "role": body.role, "token_hash": hsign(token),
                                         "status": "pending", "invited_by": u["id"], "created_at": now(), "expires_at": now() + timedelta(days=14)})
    ok = await send_email(email, "academy_invite", {"academy": a["name"], "role": body.role, "link": f"{APP_URL}/app/academy?invite={token}"})
    await audit(u["id"], "academy.invite", aid, {"email": email, "role": body.role}, request)
    return {"ok": True, "email_sent": ok}


class AcceptIn(BaseModel):
    token: Optional[str] = None
    invite_id: Optional[str] = None


@router.post("/academy-invites/accept")
async def accept(body: AcceptIn, u=Depends(current_user)):
    q = {"status": "pending", "expires_at": {"$gt": now()}, "email": u["email"]}
    if body.token:
        q["token_hash"] = hsign(body.token)
    elif body.invite_id:
        q["id"] = body.invite_id
    else:
        raise HTTPException(422, "Invite missing.")
    inv = await db.academy_invites.find_one_and_update(q, {"$set": {"status": "accepted", "accepted_at": now()}})
    if not inv:
        raise HTTPException(404, "This invitation is invalid, expired, or for a different email.")
    await db.academy_memberships.update_one({"academy_id": inv["academy_id"], "user_id": u["id"]},
                                            {"$set": {"role": inv["role"], "status": "active", "share_reports": False},
                                             "$setOnInsert": {"id": uid(), "created_at": now()}}, upsert=True)
    return {"ok": True, "academy_id": inv["academy_id"]}


@router.get("/academies/{aid}/members")
async def members(aid: str, u=Depends(current_user)):
    m = await membership(aid, u, ["academy_admin", "coach"])
    ms = await db.academy_memberships.find({"academy_id": aid, "status": "active"}, {"_id": 0}).to_list(1000)
    if m["role"] == "coach":
        assigned = {a["player_id"] for a in await db.coach_assignments.find({"academy_id": aid, "coach_id": u["id"]}).to_list(1000)}
        ms = [x for x in ms if x["role"] != "player" or x["user_id"] in assigned]
    users = {x["id"]: x for x in await db.users.find({"id": {"$in": [x["user_id"] for x in ms]}}, {"_id": 0, "id": 1, "full_name": 1, "email": 1, "profile": 1}).to_list(1000)}
    assigns = await db.coach_assignments.find({"academy_id": aid}, {"_id": 0}).to_list(5000)
    out = []
    for x in ms:
        usr = users.get(x["user_id"], {})
        row = {**x, "full_name": usr.get("full_name"), "email": usr.get("email") if m["role"] == "academy_admin" else None,
               "playing_role": (usr.get("profile") or {}).get("playing_role")}
        if x["role"] == "player":
            row["coaches"] = [a["coach_id"] for a in assigns if a["player_id"] == x["user_id"]]
            if x.get("share_reports"):
                row["analyses"] = await db.analysis_jobs.count_documents({"user_id": x["user_id"], "status": "completed"})
                last = await db.analysis_reports.find_one({"user_id": x["user_id"]}, sort=[("created_at", -1)])
                row["last_analysis"] = last["created_at"] if last else None
        out.append(row)
    invites = await db.academy_invites.find({"academy_id": aid, "status": "pending"}, {"_id": 0, "token_hash": 0}).to_list(200) if m["role"] == "academy_admin" else []
    groups = await db.academy_groups.find({"academy_id": aid}, {"_id": 0}).to_list(200)
    return {"members": out, "invites": invites, "groups": groups, "my_role": m["role"]}


@router.delete("/academies/{aid}/members/{user_id}")
async def remove_member(aid: str, user_id: str, request: Request, u=Depends(current_user)):
    await membership(aid, u, ["academy_admin"])
    if user_id == u["id"]:
        raise HTTPException(409, "You can't remove yourself.")
    await db.academy_memberships.update_one({"academy_id": aid, "user_id": user_id}, {"$set": {"status": "removed"}})
    await db.coach_assignments.delete_many({"academy_id": aid, "$or": [{"coach_id": user_id}, {"player_id": user_id}]})
    await audit(u["id"], "academy.member_removed", aid, {"user_id": user_id}, request)
    return {"ok": True}


class AssignIn(BaseModel):
    coach_id: str
    player_id: str


@router.post("/academies/{aid}/assignments")
async def assign(aid: str, body: AssignIn, u=Depends(current_user)):
    await membership(aid, u, ["academy_admin"])
    c = await db.academy_memberships.find_one({"academy_id": aid, "user_id": body.coach_id, "status": "active", "role": {"$in": ["coach", "academy_admin"]}})
    p = await db.academy_memberships.find_one({"academy_id": aid, "user_id": body.player_id, "status": "active", "role": "player"})
    if not c or not p:
        raise HTTPException(404, "Coach or player is not in this academy.")
    await db.coach_assignments.update_one({"academy_id": aid, "coach_id": body.coach_id, "player_id": body.player_id},
                                          {"$setOnInsert": {"id": uid(), "created_at": now()}}, upsert=True)
    return {"ok": True}


@router.delete("/academies/{aid}/assignments")
async def unassign(aid: str, coach_id: str, player_id: str, u=Depends(current_user)):
    await membership(aid, u, ["academy_admin"])
    await db.coach_assignments.delete_one({"academy_id": aid, "coach_id": coach_id, "player_id": player_id})
    return {"ok": True}


class GroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    player_ids: List[str] = []


@router.post("/academies/{aid}/groups")
async def save_group(aid: str, body: GroupIn, gid: Optional[str] = None, u=Depends(current_user)):
    await membership(aid, u, ["academy_admin"])
    valid = {m["user_id"] for m in await db.academy_memberships.find({"academy_id": aid, "role": "player", "status": "active"}).to_list(2000)}
    ids = [p for p in body.player_ids if p in valid]
    gid = gid or uid()
    await db.academy_groups.update_one({"id": gid, "academy_id": aid}, {"$set": {"name": body.name, "player_ids": ids},
                                                                        "$setOnInsert": {"created_at": now()}}, upsert=True)
    return {"id": gid}


class ConsentIn(BaseModel):
    share_reports: bool


@router.patch("/academies/{aid}/consent")
async def consent(aid: str, body: ConsentIn, request: Request, u=Depends(current_user)):
    m = await db.academy_memberships.find_one({"academy_id": aid, "user_id": u["id"], "role": "player", "status": "active"})
    if not m:
        raise HTTPException(404, "Membership not found.")
    if body.share_reports and is_minor(u) and not (u.get("guardian") or {}).get("consent_at"):
        raise HTTPException(403, "guardian_consent_required")
    await db.academy_memberships.update_one({"id": m["id"]}, {"$set": {"share_reports": body.share_reports, "consent_updated_at": now()}})
    await audit(u["id"], "consent.academy_share", aid, {"share": body.share_reports}, request)
    return {"ok": True}


async def coach_can_see(aid, u, pid):
    m = await membership(aid, u, ["academy_admin", "coach"])
    pm = await db.academy_memberships.find_one({"academy_id": aid, "user_id": pid, "role": "player", "status": "active"})
    if not pm:
        raise HTTPException(404, "Player not found.")
    if m["role"] == "coach" and not await db.coach_assignments.find_one({"academy_id": aid, "coach_id": u["id"], "player_id": pid}):
        raise HTTPException(404, "Player not found.")
    return pm


@router.get("/academies/{aid}/players/{pid}/reports")
async def player_reports(aid: str, pid: str, u=Depends(current_user)):
    pm = await coach_can_see(aid, u, pid)
    if not pm.get("share_reports"):
        raise HTTPException(403, "This player hasn't consented to share reports with the academy.")
    return await db.analysis_jobs.find({"user_id": pid, "status": "completed"}, {"_id": 0}).sort("created_at", -1).to_list(100)


class FeedbackIn(BaseModel):
    text: str = Field(min_length=2, max_length=1500)


@router.post("/academies/{aid}/players/{pid}/feedback")
async def feedback(aid: str, pid: str, body: FeedbackIn, u=Depends(current_user)):
    await coach_can_see(aid, u, pid)
    await db.coach_feedback.insert_one({"id": uid(), "academy_id": aid, "player_id": pid, "coach_id": u["id"], "coach_name": u["full_name"],
                                        "text": body.text, "created_at": now()})
    return {"ok": True}


class AttendIn(BaseModel):
    player_id: str
    date: str
    status: str = "present"


@router.post("/academies/{aid}/attendance")
async def attendance(aid: str, body: AttendIn, u=Depends(current_user)):
    await coach_can_see(aid, u, body.player_id)
    if body.status not in ("present", "absent", "excused"):
        raise HTTPException(422, "Invalid status.")
    await db.attendance.update_one({"academy_id": aid, "player_id": body.player_id, "date": body.date[:10]},
                                   {"$set": {"status": body.status, "by": u["id"], "updated_at": now()}}, upsert=True)
    return {"ok": True}


@router.get("/academies/{aid}/attendance")
async def get_attendance(aid: str, date: str, u=Depends(current_user)):
    await membership(aid, u, ["academy_admin", "coach"])
    return await db.attendance.find({"academy_id": aid, "date": date[:10]}, {"_id": 0}).to_list(2000)


@router.get("/academies/{aid}/export.csv")
async def export_csv(aid: str, u=Depends(current_user)):
    data = await members(aid, u)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["name", "role", "playing_role", "reports_shared", "completed_analyses", "last_analysis"])
    for m in data["members"]:
        w.writerow([m.get("full_name"), m["role"], m.get("playing_role") or "", bool(m.get("share_reports")), m.get("analyses", ""), m.get("last_analysis") or ""])
    return Response(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=academy-players.csv"})
