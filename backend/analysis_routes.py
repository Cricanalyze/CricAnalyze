import os, io, json, re, base64, asyncio, tempfile
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Request, Response, HTTPException, Depends, UploadFile, File, Form, Query
from pydantic import BaseModel, Field
from pymongo import ReturnDocument
from core import (db, now, uid, log, audit, current_user, put_object, get_object, sign_media, verify_media_sig, BUCKET_PREFIX,
                  entitlements, ledger, is_minor, get_settings, llm_text, send_email, STAFF, LEVELS, sanitize_error, LLM_KEY, AI_MODEL)

router = APIRouter(prefix="/api")
ANGLES = ["side_on", "front_on", "behind", "other"]


def sniff_video(head: bytes):
    if head[4:8] == b"ftyp":
        return "video/quicktime" if head[8:10] == b"qt" else "video/mp4"
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return "video/webm"
    return None


def probe(path):
    import cv2
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        return None
    fps = cap.get(cv2.CAP_PROP_FPS) or 0
    n = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    ok, _ = cap.read()
    cap.release()
    if not ok or fps <= 0:
        return None
    return {"fps": round(fps, 2), "frames": int(n), "duration_s": round(n / fps, 2), "width": w, "height": h}


def extract_frames(path, count):
    import cv2
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    out = []
    for i in range(count):
        idx = int((i + 0.5) * n / count)
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = cap.read()
        if not ok:
            continue
        h, w = frame.shape[:2]
        scale = 720 / max(h, w)
        if scale < 1:
            frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ok:
            out.append({"t": round(idx / fps, 2), "jpg": buf.tobytes()})
    cap.release()
    return out


@router.get("/entitlements")
async def my_entitlements(u=Depends(current_user)):
    return await entitlements(u["id"])


def consent_gate(u):
    if is_minor(u) and not (u.get("guardian") or {}).get("consent_at"):
        raise HTTPException(403, "guardian_consent_required")


@router.post("/videos")
async def upload_video(file: UploadFile = File(...), analysis_type: str = Form(...), angle: str = Form("side_on"), u=Depends(current_user)):
    if analysis_type not in ("batting", "bowling"):
        raise HTTPException(422, "Choose batting or bowling.")
    if angle not in ANGLES:
        raise HTTPException(422, "Invalid camera angle.")
    consent_gate(u)
    ent = await entitlements(u["id"])
    if u["role"] not in STAFF and analysis_type not in ent["analysis_types"]:
        raise HTTPException(402, f"Your plan doesn't include {analysis_type} analysis. Choose a plan on the Pricing page.")
    max_mb = ent["max_file_mb"] or 100
    max_dur = ent["max_duration_s"] or 30
    data = await file.read(max_mb * 1024 * 1024 + 1)
    if len(data) > max_mb * 1024 * 1024:
        raise HTTPException(413, f"File is larger than your plan limit of {max_mb} MB.")
    ctype = sniff_video(data[:16])
    if not ctype:
        raise HTTPException(415, "This file isn't a supported video. Upload MP4, MOV or WEBM.")
    with tempfile.NamedTemporaryFile(suffix=".vid") as tmp:
        tmp.write(data)
        tmp.flush()
        meta = await asyncio.to_thread(probe, tmp.name)
    if not meta:
        raise HTTPException(415, "We couldn't read this video. Try re-exporting it as MP4 (H.264).")
    if meta["duration_s"] > max_dur + 0.5:
        raise HTTPException(422, f"Video is {meta['duration_s']}s long; your plan allows up to {max_dur}s. Trim it and try again.")
    if min(meta["width"], meta["height"]) < 240:
        raise HTTPException(422, "Video resolution is too low (minimum 240p). Record at 480p or higher.")
    vid = uid()
    res = await asyncio.to_thread(put_object, f"{BUCKET_PREFIX}/videos/{u['id']}/{vid}", data, ctype)
    doc = {"id": vid, "user_id": u["id"], "analysis_type": analysis_type, "angle": angle, "original_filename": (file.filename or "")[:120],
           "content_type": ctype, "size": len(data), "meta": meta, "storage_path": res["path"], "is_deleted": False, "created_at": now()}
    await db.video_assets.insert_one(doc)
    doc.pop("_id", None)
    doc.pop("storage_path")
    return doc


@router.get("/videos")
async def list_videos(u=Depends(current_user)):
    return await db.video_assets.find({"user_id": u["id"], "is_deleted": False}, {"_id": 0, "storage_path": 0}).sort("created_at", -1).to_list(200)


async def can_view_user_data(viewer, owner_id):
    if viewer["id"] == owner_id or viewer["role"] in STAFF:
        return True
    pm = await db.academy_memberships.find({"user_id": owner_id, "role": "player", "status": "active", "share_reports": True}).to_list(20)
    for m in pm:
        if await db.academy_memberships.find_one({"academy_id": m["academy_id"], "user_id": viewer["id"], "role": "academy_admin", "status": "active"}):
            return True
        if await db.coach_assignments.find_one({"academy_id": m["academy_id"], "coach_id": viewer["id"], "player_id": owner_id}):
            return True
    return False


@router.get("/videos/{vid}/url")
async def video_url(vid: str, u=Depends(current_user)):
    v = await db.video_assets.find_one({"id": vid, "is_deleted": False})
    if not v or not await can_view_user_data(u, v["user_id"]):
        raise HTTPException(404, "Video not found.")
    return {"url": sign_media(vid), "expires_in": 900}


@router.delete("/videos/{vid}")
async def delete_video(vid: str, request: Request, u=Depends(current_user)):
    r = await db.video_assets.update_one({"id": vid, "user_id": u["id"]}, {"$set": {"is_deleted": True, "deleted_at": now()}})
    if not r.matched_count:
        raise HTTPException(404, "Video not found.")
    await audit(u["id"], "video.deleted", vid, request=request)
    return {"ok": True}


@router.get("/media/{asset_id}")
async def media(asset_id: str, exp: int = 0, sig: str = ""):
    if not verify_media_sig(asset_id, exp, sig):
        raise HTTPException(403, "This link has expired.")
    a = await db.video_assets.find_one({"id": asset_id, "is_deleted": False}) or await db.media_assets.find_one({"id": asset_id, "is_deleted": False})
    if not a:
        raise HTTPException(404, "Not found.")
    data, _ = await asyncio.to_thread(get_object, a["storage_path"])
    return Response(data, media_type=a["content_type"], headers={"Cache-Control": "private, max-age=600", "X-Robots-Tag": "noindex"})


class AnalysisIn(BaseModel):
    analysis_type: str
    video_ids: List[str] = Field(min_length=1, max_length=3)
    consent: bool
    idempotency_key: str = Field(min_length=8, max_length=64)
    notes: Optional[str] = Field(None, max_length=300)


async def reserve_credit(user_id, analysis_type, ref):
    sub = await db.subscriptions.find_one_and_update(
        {"user_id": user_id, "status": "active", "expires_at": {"$gt": now()}, "credits_remaining": {"$gte": 1},
         "plan_snapshot.analysis_types": analysis_type},
        {"$inc": {"credits_remaining": -1}}, sort=[("expires_at", 1)], return_document=ReturnDocument.AFTER)
    if not sub:
        return None
    await ledger(user_id, -1, "analysis_reserved", ref, sub["id"])
    return sub


async def refund_credit(job, reason):
    if job.get("subscription_id") and job.get("credit_state") == "reserved":
        r = await db.analysis_jobs.update_one({"id": job["id"], "credit_state": "reserved"}, {"$set": {"credit_state": "refunded"}})
        if r.modified_count:
            await db.subscriptions.update_one({"id": job["subscription_id"]}, {"$inc": {"credits_remaining": 1}})
            await ledger(job["user_id"], 1, reason, job["id"], job["subscription_id"])


@router.post("/analyses")
async def create_analysis(body: AnalysisIn, request: Request, u=Depends(current_user)):
    if not body.consent:
        raise HTTPException(422, "Please confirm you have the right to upload this video and consent to its analysis.")
    consent_gate(u)
    existing = await db.analysis_jobs.find_one({"user_id": u["id"], "idempotency_key": body.idempotency_key}, {"_id": 0})
    if existing:
        return existing
    vids = await db.video_assets.find({"id": {"$in": body.video_ids}, "user_id": u["id"], "is_deleted": False}).to_list(5)
    if len(vids) != len(set(body.video_ids)):
        raise HTTPException(404, "One or more videos were not found.")
    if any(v["analysis_type"] != body.analysis_type for v in vids):
        raise HTTPException(422, "All videos must match the selected analysis type.")
    staff = u["role"] in STAFF
    ent = await entitlements(u["id"])
    if not staff:
        if body.analysis_type not in ent["analysis_types"]:
            raise HTTPException(402, f"Your plan doesn't include {body.analysis_type} analysis.")
        if len(vids) > ent["videos_per_analysis"]:
            raise HTTPException(402, f"Your plan allows {ent['videos_per_analysis']} video(s) per analysis.")
        if len(vids) > 1 and not ent["multi_angle"]:
            raise HTTPException(402, "Multi-angle analysis isn't included in your plan.")
    if len({v["angle"] for v in vids}) != len(vids):
        raise HTTPException(422, "Each video in a multi-angle analysis must have a different camera angle.")
    job_id = uid()
    sub = None
    if not staff:
        sub = await reserve_credit(u["id"], body.analysis_type, job_id)
        if not sub:
            raise HTTPException(402, "You don't have analysis credits left for this type. Renew or upgrade your plan.")
    level = (sub["plan_snapshot"].get("report_level") if sub else "advanced") or "basic"
    job = {"id": job_id, "user_id": u["id"], "analysis_type": body.analysis_type, "video_ids": [v["id"] for v in vids],
           "idempotency_key": body.idempotency_key, "status": "queued", "attempts": 0, "progress": 0, "report_level": level,
           "subscription_id": sub["id"] if sub else None, "credit_state": "reserved" if sub else "none", "notes": body.notes,
           "consent_at": now(), "created_at": now(), "updated_at": now(), "next_run_at": now()}
    try:
        await db.analysis_jobs.insert_one(job)
    except Exception:
        if sub:
            await refund_credit({**job, "credit_state": "reserved"}, "duplicate_request_refund")
        return await db.analysis_jobs.find_one({"user_id": u["id"], "idempotency_key": body.idempotency_key}, {"_id": 0})
    await audit(u["id"], "analysis.created", job_id, request=request)
    job.pop("_id", None)
    return job


def filter_report(rep, level):
    if not rep:
        return rep
    lvl = LEVELS.index(level) if level in LEVELS else 0
    if lvl < 1:
        rep["observations"] = rep.get("observations", [])[:3]
        rep["drills"] = rep.get("drills", [])[:1]
        rep["locked"] = ["full observations", "all drills", "practice plan"]
    if lvl < 2:
        rep["practice_plan"] = None
        rep.setdefault("locked", []).append("practice plan")
    return rep


async def load_report_for(u, job):
    rep = await db.analysis_reports.find_one({"job_id": job["id"]}, {"_id": 0})
    if rep:
        rep = filter_report(rep, job.get("report_level", "basic"))
        for f in rep.get("frames", []):
            f["url"] = sign_media(f["asset_id"])
    return rep


@router.get("/analyses")
async def list_analyses(type: Optional[str] = None, date_from: Optional[str] = None, date_to: Optional[str] = None,
                        player_id: Optional[str] = None, u=Depends(current_user)):
    owner = player_id or u["id"]
    if not await can_view_user_data(u, owner):
        raise HTTPException(404, "Not found.")
    q = {"user_id": owner}
    if type in ("batting", "bowling"):
        q["analysis_type"] = type
    for d in (date_from, date_to):
        if d and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
            raise HTTPException(422, "Dates must be in YYYY-MM-DD format.")
    if date_from or date_to:
        q["created_at"] = {}
        if date_from:
            q["created_at"]["$gte"] = datetime.fromisoformat(date_from + "T00:00:00+00:00")
        if date_to:
            q["created_at"]["$lte"] = datetime.fromisoformat(date_to + "T23:59:59+00:00")
    jobs = await db.analysis_jobs.find(q, {"_id": 0}).sort("created_at", -1).to_list(200)
    reps = {r["job_id"]: r for r in await db.analysis_reports.find({"job_id": {"$in": [j["id"] for j in jobs]}},
                                                                    {"_id": 0, "job_id": 1, "id": 1, "summary": 1, "overall_confidence": 1, "scores": 1}).to_list(200)}
    for j in jobs:
        j["report"] = reps.get(j["id"])
    return jobs


async def get_job_authorized(u, job_id):
    job = await db.analysis_jobs.find_one({"id": job_id}, {"_id": 0})
    if not job or not await can_view_user_data(u, job["user_id"]):
        raise HTTPException(404, "Analysis not found.")
    return job


@router.get("/analyses/{job_id}")
async def get_analysis(job_id: str, u=Depends(current_user)):
    job = await get_job_authorized(u, job_id)
    job["report"] = await load_report_for(u, job)
    job["videos"] = await db.video_assets.find({"id": {"$in": job["video_ids"]}}, {"_id": 0, "storage_path": 0}).to_list(5)
    if job["report"] and u["id"] == job["user_id"] and not job.get("reviewed_at"):
        await db.analysis_jobs.update_one({"id": job_id}, {"$set": {"reviewed_at": now()}})
    return job


@router.post("/analyses/{job_id}/retry")
async def retry_analysis(job_id: str, u=Depends(current_user)):
    job = await db.analysis_jobs.find_one({"id": job_id, "user_id": u["id"]})
    if not job or job["status"] != "failed":
        raise HTTPException(409, "Only failed analyses can be retried.")
    upd = {"status": "queued", "attempts": 0, "failure_reason": None, "next_run_at": now(), "updated_at": now()}
    if job.get("credit_state") == "refunded":
        sub = await reserve_credit(u["id"], job["analysis_type"], job_id)
        if not sub:
            raise HTTPException(402, "You don't have credits left to retry this analysis.")
        upd.update({"subscription_id": sub["id"], "credit_state": "reserved"})
    await db.analysis_jobs.update_one({"id": job_id}, {"$set": upd})
    return {"ok": True}


@router.get("/analyses/{job_id}/pdf")
async def report_pdf(job_id: str, u=Depends(current_user)):
    job = await get_job_authorized(u, job_id)
    if u["role"] not in STAFF and not (await entitlements(job["user_id"]))["pdf_export"]:
        raise HTTPException(402, "PDF export isn't included in this plan.")
    rep = await load_report_for(u, job)
    if not rep:
        raise HTTPException(409, "The report isn't ready yet.")
    owner = await db.users.find_one({"id": job["user_id"]})
    pdf = await asyncio.to_thread(build_pdf, rep, job, owner)
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=cricanalyze-{job_id[:8]}.pdf"})


def build_pdf(rep, job, owner):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from xml.sax.saxutils import escape as e
    buf = io.BytesIO()
    ss = getSampleStyleSheet()
    doc = SimpleDocTemplate(buf, pagesize=A4, title="CricAnalyze Report")
    s = [Paragraph("<font color='#0B132B'>Cric</font><font color='#10B981'>Analyze</font> — Technique Report", ss["Title"]),
         Paragraph(f"Player: {e(owner.get('full_name', ''))} · {job['analysis_type'].title()} · {job['created_at'].strftime('%d %b %Y')}", ss["Normal"]),
         Paragraph(f"Model: {e(rep.get('model', ''))} · Report level: {job.get('report_level')} · Overall confidence: {e(str(rep.get('overall_confidence', 'n/a')))}", ss["Normal"]),
         Spacer(1, 10), Paragraph("Summary", ss["Heading2"]), Paragraph(e(rep.get("summary", "")), ss["Normal"])]
    for title, key in (("Strengths", "strengths"), ("Areas to improve", "improvements")):
        s.append(Paragraph(title, ss["Heading2"]))
        for x in rep.get(key, []):
            s.append(Paragraph("• " + e(str(x)), ss["Normal"]))
    s.append(Paragraph("Observations", ss["Heading2"]))
    rows = [["Area", "Observation", "Time", "Type", "Conf."]]
    for o in rep.get("observations", []):
        rows.append([Paragraph(e(o.get("area", "")), ss["Normal"]), Paragraph(e(o.get("observation", "")), ss["Normal"]),
                     f"{o.get('timestamp_s', '-')}s", o.get("evidence_type", ""), o.get("confidence", "")])
    t = Table(rows, colWidths=[70, 250, 45, 70, 45])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B132B")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                           ("GRID", (0, 0), (-1, -1), 0.3, colors.grey), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    s.append(t)
    s.append(Paragraph("Recommended drills", ss["Heading2"]))
    for d in rep.get("drills", []):
        s.append(Paragraph(f"<b>{e(d.get('name', ''))}</b> — {e(d.get('how_to', ''))} ({e(d.get('sets_reps', ''))})", ss["Normal"]))
    if rep.get("practice_plan"):
        s.append(Paragraph("Practice plan", ss["Heading2"]))
        for p in rep["practice_plan"]:
            s.append(Paragraph(f"<b>{e(p.get('day', ''))}</b>: {e(p.get('focus', ''))}", ss["Normal"]))
    s.append(Spacer(1, 12))
    s.append(Paragraph("Limitations: " + e("; ".join(rep.get("limitations", []))), ss["Italic"]))
    s.append(Paragraph("AI-assisted coaching observations from sampled video frames. Not a medical assessment or official selection credential.", ss["Italic"]))
    doc.build(s)
    return buf.getvalue()


# ---------- timeline & comparison ----------
CONF = {"low": 1, "medium": 2, "high": 3}


@router.get("/timeline")
async def timeline(type: str = "batting", player_id: Optional[str] = None, u=Depends(current_user)):
    owner = player_id or u["id"]
    if not await can_view_user_data(u, owner):
        raise HTTPException(404, "Not found.")
    if u["role"] not in STAFF and not (await entitlements(owner))["timeline"] and owner == u["id"]:
        raise HTTPException(402, "The player timeline isn't included in your plan.")
    reps = await db.analysis_reports.find({"user_id": owner, "analysis_type": type}, {"_id": 0, "job_id": 1, "created_at": 1, "scores": 1,
                                                                                     "summary": 1, "overall_confidence": 1}).sort("created_at", 1).to_list(200)
    return {"reports": reps, "baseline": len(reps) <= 1}


@router.get("/compare")
async def compare(a: str, b: str, u=Depends(current_user)):
    ja, jb = await get_job_authorized(u, a), await get_job_authorized(u, b)
    if u["role"] not in STAFF and not (await entitlements(ja["user_id"]))["comparisons"]:
        raise HTTPException(402, "Before-and-after comparisons aren't included in your plan.")
    if ja["user_id"] != jb["user_id"] or ja["analysis_type"] != jb["analysis_type"]:
        raise HTTPException(422, "Only reports of the same player and analysis type can be compared.")
    ra, rb = await load_report_for(u, ja), await load_report_for(u, jb)
    if not ra or not rb:
        raise HTTPException(409, "Both analyses must be completed.")
    if ra["created_at"] > rb["created_at"]:
        ra, rb, ja, jb = rb, ra, jb, ja
    areas = sorted(set((ra.get("scores") or {}).keys()) | set((rb.get("scores") or {}).keys()))
    rows = []
    for ar in areas:
        x, y = (ra.get("scores") or {}).get(ar), (rb.get("scores") or {}).get(ar)
        rows.append({"area": ar, "before": x, "after": y, "change": (y["rating"] - x["rating"]) if x and y and x.get("rating") and y.get("rating") else None})
    if u["id"] == ja["user_id"]:
        await db.challenge_events.update_one({"user_id": u["id"], "type": "comparison", "ref": f"{a}:{b}"},
                                             {"$setOnInsert": {"created_at": now()}}, upsert=True)
    return {"before": {"job": ja, "report": ra}, "after": {"job": jb, "report": rb}, "areas": rows,
            "note": "Ratings are AI visual assessments (1–5) of sampled frames, not measured biomechanics. Missing values mean the area wasn't assessable."}


# ---------- worker ----------
BAT_AREAS = ["stance", "balance", "head_position", "trigger_movement", "footwork", "weight_transfer", "bat_path", "body_alignment", "contact_position", "follow_through"]
BOWL_AREAS = ["run_up", "rhythm", "gather", "back_foot_contact", "front_foot_contact", "bowling_arm", "front_arm", "trunk_alignment", "hip_shoulder_rotation", "release", "follow_through", "balance"]

SYSTEM = """You are an experienced cricket technique analyst. You are shown frames sampled from a player's video with timestamps.
Rules: describe ONLY what is visible in the frames. Never state speeds, forces, exact joint angles or any number you cannot measure.
If an area cannot be assessed (occlusion, camera angle, resolution, frame rate, too few frames), set its rating to null and say why.
Separate 'observed' (directly visible) from 'inferred' (coaching interpretation). No medical diagnosis, no injury guarantees.
Return ONLY valid JSON, no markdown."""


def build_prompt(kind, frames_by_video, notes):
    areas = BAT_AREAS if kind == "batting" else BOWL_AREAS
    lines = []
    i = 0
    for v, frames in frames_by_video:
        for f in frames:
            lines.append(f"Image {i}: angle={v['angle']}, t={f['t']}s")
            i += 1
    return f"""Analyse this {kind} technique. {'Player note: ' + notes if notes else ''}
Images in order:\n""" + "\n".join(lines) + f"""
Return JSON with keys:
"is_cricket_{kind}": bool (false if the video does not show cricket {kind}),
"summary": string (3-4 sentences, simple language),
"scores": object whose keys are from {areas} -> {{"rating": 1-5 or null, "confidence": "low"|"medium"|"high", "note": short string}},
"observations": list of {{"area", "observation", "timestamp_s", "image_index", "evidence_type": "observed"|"inferred", "confidence"}},
"strengths": list of strings, "improvements": list of strings,
"drills": list of {{"name","purpose","how_to","sets_reps","linked_area"}} (3-5),
"practice_plan": list of {{"day","focus","duration_min"}} for one week,
"per_angle": list of {{"angle","visibility":"good"|"partial"|"poor","note"}},
"limitations": list of strings about what could not be reliably assessed,
"overall_confidence": "low"|"medium"|"high" """


def parse_json(text):
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("AI response did not contain JSON")
    return json.loads(m.group(0))


class PermanentError(Exception):
    pass


async def run_provider(job, vids, frames_by_video):
    provider = os.environ.get("AI_INFERENCE_PROVIDER", "vision_llm")
    if provider != "vision_llm":
        raise PermanentError(f"AI provider '{provider}' is not configured on this server.")
    if not LLM_KEY:
        raise PermanentError("AI analysis provider is not configured. An administrator must add the AI key.")
    imgs = [base64.b64encode(f["jpg"]).decode() for _, fr in frames_by_video for f in fr]
    text = await llm_text(SYSTEM, build_prompt(job["analysis_type"], frames_by_video, job.get("notes")), f"job-{job['id']}-{job['attempts']}", imgs)
    return parse_json(text)


async def process_job(job):
    settings = await get_settings()
    lim = settings["limits"]
    vids = await db.video_assets.find({"id": {"$in": job["video_ids"]}, "is_deleted": False}).to_list(5)
    if len(vids) != len(job["video_ids"]):
        raise PermanentError("A video for this analysis was deleted before processing.")
    per = max(3, lim["frames_per_video"] if len(vids) == 1 else lim["frames_per_video"] // 2 + 1)
    frames_by_video = []
    for v in vids:
        data, _ = await asyncio.to_thread(get_object, v["storage_path"])
        with tempfile.NamedTemporaryFile(suffix=".vid") as tmp:
            tmp.write(data)
            tmp.flush()
            fr = await asyncio.to_thread(extract_frames, tmp.name, per)
        if not fr:
            raise PermanentError("We couldn't extract frames from the video.")
        frames_by_video.append((v, fr))
    await db.analysis_jobs.update_one({"id": job["id"]}, {"$set": {"progress": 40, "stage": "ai_analysis"}})
    result = await run_provider(job, vids, frames_by_video)
    if result.get(f"is_cricket_{job['analysis_type']}") is False:
        raise PermanentError(f"The video doesn't appear to show cricket {job['analysis_type']}. Your credit has been refunded.")
    frames = []
    idx = 0
    for v, fr in frames_by_video:
        for f in fr:
            aid = uid()
            res = await asyncio.to_thread(put_object, f"{BUCKET_PREFIX}/frames/{job['user_id']}/{aid}.jpg", f["jpg"], "image/jpeg")
            await db.media_assets.insert_one({"id": aid, "user_id": job["user_id"], "kind": "frame", "storage_path": res["path"],
                                              "content_type": "image/jpeg", "is_deleted": False, "created_at": now()})
            frames.append({"index": idx, "asset_id": aid, "t": f["t"], "angle": v["angle"], "video_id": v["id"]})
            idx += 1
    rep = {"id": uid(), "job_id": job["id"], "user_id": job["user_id"], "analysis_type": job["analysis_type"], "created_at": now(),
           "model": f"anthropic/{AI_MODEL} (vision, sampled frames)", "provider": "vision_llm", "frames": frames,
           "video_meta": [{"video_id": v["id"], "angle": v["angle"], **v["meta"]} for v in vids],
           "measured": {"note": "Duration, FPS and resolution are measured from the file. Pose keypoints, joint angles and speeds are not measured by the current provider."},
           **{k: result.get(k) for k in ("summary", "scores", "observations", "strengths", "improvements", "drills", "practice_plan",
                                         "per_angle", "limitations", "overall_confidence")}}
    await db.analysis_reports.insert_one(rep)
    await db.analysis_jobs.update_one({"id": job["id"]}, {"$set": {"status": "completed", "progress": 100, "stage": "done", "completed_at": now(),
                                                                   "credit_state": "consumed" if job.get("credit_state") == "reserved" else job.get("credit_state")}})
    if job.get("credit_state") == "reserved":
        await ledger(job["user_id"], 0, "analysis_consumed", job["id"], job.get("subscription_id"))
    await db.performance_timelines.update_one({"user_id": job["user_id"], "analysis_type": job["analysis_type"]},
                                              {"$push": {"entries": {"job_id": job["id"], "at": now(), "scores": rep["scores"]}}}, upsert=True)
    user = await db.users.find_one({"id": job["user_id"]})
    if user:
        await send_email(user["email"], "report_ready", {"kind": job["analysis_type"]}, user["id"])


async def handle_job(job):
    lim = (await get_settings())["limits"]
    try:
        await asyncio.wait_for(process_job(job), timeout=lim["job_timeout_s"])
    except Exception as e:
        permanent = isinstance(e, (PermanentError, json.JSONDecodeError, ValueError)) and not isinstance(e, asyncio.TimeoutError)
        reason = str(e) if isinstance(e, PermanentError) else ("The analysis timed out." if isinstance(e, asyncio.TimeoutError) else "The AI provider was unavailable or returned an unusable result.")
        log.warning(f"job {job['id']} failed attempt={job['attempts']} err={sanitize_error(e)}")
        if not permanent and job["attempts"] <= lim["max_retries"]:
            from datetime import timedelta
            await db.analysis_jobs.update_one({"id": job["id"]}, {"$set": {"status": "queued", "stage": "retry_wait", "last_error": reason,
                                                                           "next_run_at": now() + timedelta(seconds=20 * job["attempts"])}})
            return
        await db.analysis_jobs.update_one({"id": job["id"]}, {"$set": {"status": "failed", "failure_reason": reason, "failed_at": now(),
                                                                       "error_detail": sanitize_error(e)}})
        await refund_credit(job, "analysis_failed_refund")


_running = set()


async def worker_loop():
    await db.analysis_jobs.update_many({"status": "processing"}, {"$set": {"status": "queued", "next_run_at": now()}})
    while True:
        try:
            lim = (await get_settings())["limits"]
            while len(_running) < lim["max_concurrent_jobs"]:
                job = await db.analysis_jobs.find_one_and_update(
                    {"status": "queued", "next_run_at": {"$lte": now()}},
                    {"$set": {"status": "processing", "stage": "extracting_frames", "progress": 10, "started_at": now()}, "$inc": {"attempts": 1}},
                    sort=[("created_at", 1)], return_document=ReturnDocument.AFTER)
                if not job:
                    break
                t = asyncio.create_task(handle_job(job))
                _running.add(t)
                t.add_done_callback(_running.discard)
        except Exception as e:
            log.error(f"worker loop error {sanitize_error(e)}")
        await asyncio.sleep(3)
