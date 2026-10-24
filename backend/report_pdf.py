import io, asyncio
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.platypus import BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table, TableStyle, KeepTogether, Image
from core import db, now, uid, get_object, put_object, BUCKET_PREFIX

PDF_VERSION = "2.6"
LOGO = Path(__file__).parent / "assets" / "logo_sm.png"
NAVY, TEAL, EMERALD, INK, MUTED, LINE, SOFT = (colors.HexColor(c) for c in ("#0B132B", "#00A6C4", "#10B981", "#1C2541", "#5B6477", "#D6DCE5", "#F2F6FA"))
W, H = A4
M = 36
CW = W - 2 * M
ST = {k: ParagraphStyle(k, fontName=f, fontSize=s, leading=s * 1.35, textColor=c, spaceAfter=a)
      for k, f, s, c, a in [("body", "Helvetica", 9.5, INK, 4), ("small", "Helvetica", 8, MUTED, 2), ("h2", "Helvetica-Bold", 13, NAVY, 6),
                            ("h3", "Helvetica-Bold", 10.5, NAVY, 3), ("cell", "Helvetica", 8.5, INK, 0), ("cellb", "Helvetica-Bold", 8.5, NAVY, 0),
                            ("th", "Helvetica-Bold", 8.5, colors.white, 0)]}
STATUS_TXT = {"measured": "Measured", "measured_estimated_phase": "Measured (estimated phase)", "low_confidence": "Low confidence - excluded",
              "not_measurable": "Not measurable from this video", "locked": "Not in plan"}


def t(s):
    return escape(str(s if s is not None else "")).replace("≥", "&gt;=").replace("≤", "&lt;=").replace("–", "-")


def P(s, st="body"):
    return Paragraph(t(s) if st != "raw" else s, ST[st if st != "raw" else "body"])


def section(title, *flow):
    return KeepTogether([Spacer(1, 8), Paragraph(t(title), ST["h2"]), *flow[:1]]), *flow[1:]


def grid_table(rows, widths, header=True):
    tb = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    style = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("GRID", (0, 0), (-1, -1), 0.4, LINE), ("TOPPADDING", (0, 0), (-1, -1), 4),
             ("BOTTOMPADDING", (0, 0), (-1, -1), 4), ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5)]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), NAVY)]
    style += [("BACKGROUND", (0, i), (-1, i), SOFT) for i in range(2 if header else 1, len(rows), 2)]
    tb.setStyle(TableStyle(style))
    return tb


def fit_image(blob, max_w, max_h):
    ir = ImageReader(io.BytesIO(blob))
    iw, ih = ir.getSize()
    s = min(max_w / iw, max_h / ih)
    return Image(io.BytesIO(blob), width=iw * s, height=ih * s)


def _page(title, rep_id, generated):
    def draw(c, doc):
        c.saveState()
        hh = 64 if doc.page == 1 else 34
        c.setFillColor(NAVY)
        c.rect(0, H - hh, W, hh, fill=1, stroke=0)
        y = H - hh / 2 - 5
        if LOGO.exists():
            ir = ImageReader(str(LOGO))
            iw, ih = ir.getSize()
            lh = hh - 10
            lw = iw * lh / ih
            c.setFillColor(colors.white)
            c.roundRect(M - 4, H - hh / 2 - lh / 2 - 1, lw + 8, lh + 2, 4, fill=1, stroke=0)
            c.drawImage(ir, M, H - hh / 2 - lh / 2, width=lw, height=lh)
        else:
            c.setFont("Helvetica-Bold", 15 if doc.page == 1 else 11)
            c.setFillColor(colors.white)
            c.drawString(M, y, "Cric")
            c.setFillColor(EMERALD)
            c.drawString(M + c.stringWidth("Cric", "Helvetica-Bold", 15 if doc.page == 1 else 11), y, "Analyze")
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 13 if doc.page == 1 else 9)
        c.drawRightString(W - M, y, title)
        c.setFillColor(TEAL)
        c.rect(0, H - hh - 3, W, 3, fill=1, stroke=0)
        c.setStrokeColor(LINE)
        c.line(M, 30, W - M, 30)
        c.setFont("Helvetica", 7.5)
        c.setFillColor(MUTED)
        c.drawString(M, 18, f"CricAnalyze - Buddy Innovations and Technologies Pvt Ltd - cricanalyze.in   |   Generated {generated}")
        c.drawRightString(W - M, 18, f"Report {rep_id[:8].upper()} - v{PDF_VERSION} - Page {doc.page}")
        c.restoreState()
    return draw


async def _blob(asset_id):
    a = await db.media_assets.find_one({"id": asset_id}) if asset_id else None
    if not a:
        return None
    data, _ = await asyncio.to_thread(get_object, a["storage_path"])
    return data


def phase_grid(b, blobs):
    n = max(1, len(b.get("phases", [])))
    cells, cw = [], CW / n - 2
    for p in b.get("phases", []):
        blob = blobs.get(p.get("ball_overlay_asset_id")) or blobs.get(p.get("overlay_asset_id")) or blobs.get(p.get("frame_asset_id"))
        img = fit_image(blob, cw - 6, 70) if blob else Table([[P("Not identified in this video", "small")]], colWidths=[cw - 10], rowHeights=[60],
                                                                 style=[("BACKGROUND", (0, 0), (-1, -1), SOFT), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (0, 0), (-1, -1), "CENTER")])
        st = {"detected": "Detected", "estimated": "Estimated", "unavailable": "Unavailable"}[p["status"]]
        meta = f"{st}" + (f" - t={p['t']}s - keypoint conf {p.get('keypoint_confidence')}" if p.get("t") is not None else "")
        if p.get("t") is not None:
            meta += f" - ball conf {p['ball']['conf']}" if p.get("ball") else " - ball not detected in this frame"
        cells.append([img, Paragraph(f"<b>{t(p['name'])}</b>", ST["cellb"]), P(meta, "small"), P(p.get("note", ""), "small")])
    rows = [[cells[j] for j in range(len(cells))]] if cells else [[""]]
    tb = Table(rows, colWidths=[CW / n] * n)
    tb.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                            ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2)]))
    return tb


def score_block(sc, b):
    if not sc.get("components"):
        txt = f"<b>{sc['value']} / 100</b>" if sc.get("value") is not None else "<b>Insufficient evidence to calculate a reliable score.</b>"
        return [Paragraph(txt, ST["h3"]), P(f"Saved with scoring method {sc.get('version', 'n/a')}.", "small")]
    names = {m["key"]: m["name"] for m in b.get("metrics", [])}
    if sc.get("value") is not None:
        head = Paragraph(f"<font size=7.5 color='#5B6477'><b>OVERALL SCORE</b></font><br/><font size=30 color='#0B132B'><b>{sc['value']}</b></font><font size=11 color='#5B6477'> / 100</font>"
                         f"<br/><font size=9 color='#10B981'><b>Technique Score</b></font>", ParagraphStyle("score", parent=ST["body"], leading=34))
    else:
        head = Paragraph("<font size=7.5 color='#5B6477'><b>OVERALL SCORE</b></font><br/><font size=12 color='#B45309'><b>Provisional - no overall score</b></font><br/>"
                         "<font size=8 color='#5B6477'>Not enough reliable measurements. Components use only what could be measured.</font>", ParagraphStyle("prov", parent=ST["body"], leading=14))
    ev = sc.get("evidence") or {}
    side = Paragraph(f"Evidence: <b>{t(ev.get('level', 'n/a'))}</b> - coverage {round(sc.get('coverage', 0) * 100)}%, {sc.get('detected_phases')} detected phases, "
                     f"keypoint conf {ev.get('mean_keypoint_confidence')}. Separate from technique quality. {sc['version']} / {sc.get('rubric_hash')}", ST["small"])
    rows = [[Paragraph(h, ST["th"]) for h in ("Component", "Score", "Contribution", "Measured")]]
    for c in sc["components"]:
        rows.append([P(c["name"], "cell"), P(f"{round(c['score'])}/100" if c["score"] is not None else "Not measured", "cell"),
                     P(f"+{c['contribution']} pts" if c.get("contribution") is not None and sc.get("value") is not None else "-", "cell"),
                     P(f"{len(c['metrics'])} of {len(c['metrics']) + len(c['missing'])}", "cell")])
    for n in sc.get("not_assessed") or []:
        rows.append([P(n["name"], "cell"), P("Not assessed", "cell"), P("-", "cell"), P("needs repeats", "cell")])
    comp = grid_table(rows, [120, 60, 65, CW - 165 - 245])
    bt = Table([[[head, Spacer(1, 6), side], comp]], colWidths=[165, CW - 165])
    bt.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, 0), SOFT), ("LINEBEFORE", (0, 0), (0, 0), 4, TEAL), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6), ("LEFTPADDING", (0, 0), (0, 0), 10), ("LEFTPADDING", (1, 0), (1, 0), 8)]))
    strong = ", ".join(names.get(k, k) for k in sc.get("strongest") or []) or "none stood out"
    opp = ", ".join(names.get(k, k) for k in sc.get("opportunities") or []) or "no measured metric fell well outside its target"
    return [bt, P(f"Strongest factors: {strong}. Main opportunities: {opp}. " + (sc.get("method") or {}).get("status", ""), "small")]


def ball_block(ball):
    if not ball:
        return []
    if ball.get("status") != "tracked":
        body = [P(ball.get("message") or "Ball not reliably detected in this video."), P(" ".join(x for x in [ball.get("error")] + (ball.get("limitations") or [])[1:] if x), "small")]
    else:
        rows = [[Paragraph(h, ST["th"]) for h in ("Frames detected", "Detection coverage", "Highest-confidence detection", "Mean confidence")],
                [P(f"{ball['frames_detected']} of {ball['frames_processed']}", "cell"), P(f"{ball['coverage'] * 100:.1f}%", "cell"),
                 P(f"{ball['best']['conf']} at t={ball['best']['t']}s", "cell"), P(ball.get("mean_conf"), "cell")]]
        lim = [f"Interrupted at {g['t_from']}s: {g['reason']}" for g in ball.get("gaps") or []] + list(ball.get("limitations") or [])
        body = [grid_table(rows, [CW / 4] * 4), P("Tracking limitations: " + (" ".join(lim) or "none noted."), "small")]
    body.append(P(f"{(ball.get('events') or {}).get('note', '')} Detector: {(ball.get('model') or {}).get('detector', 'n/a')} ({ball.get('version')}).", "small"))
    return section("Ball tracking summary", *body)


def build(rep, job, owner, blobs):
    buf = io.BytesIO()
    measured = rep.get("assessment_type") == "measured_biomechanical"
    title = "Biomechanical Assessment Report" if measured else "Technique Assessment Report (vision-only)"
    generated = now().strftime("%d %b %Y %H:%M UTC")
    doc = BaseDocTemplate(buf, pagesize=A4, leftMargin=M, rightMargin=M, topMargin=84, bottomMargin=44, title=title, author="CricAnalyze")
    draw = _page(title, rep["id"], generated)
    doc.addPageTemplates([PageTemplate(id="first", frames=[Frame(M, 44, CW, H - 84 - 44, id="f1")], onPage=draw, autoNextPageTemplate="later"),
                          PageTemplate(id="later", frames=[Frame(M, 44, CW, H - 50 - 44, id="f2")], onPage=draw)])
    bios = rep.get("biomech") or []
    primary = next((b for b in bios if b.get("status") == "measured"), bios[0] if bios else {})
    model = primary.get("model") or {}
    s = [Paragraph(t(rep.get("shot_type") or rep["analysis_type"].title()), ParagraphStyle("ttl", fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=NAVY, spaceAfter=2)),
         P(f"Type: {rep['analysis_type'].title()}  |  Status: Completed", "small"), Spacer(1, 6)]
    metric_secs = []
    info = [["Player", owner.get("full_name", ""), "Analysis date", rep["created_at"].strftime("%d %b %Y")],
            ["Analysis type", rep["analysis_type"].title(), "Shot / delivery", rep.get("shot_type") or "Not specified"],
            ["Report status", "Measured biomechanical assessment" if measured else "Vision-only - not a measured assessment", "Report level", job.get("report_level", "").title()],
            ["Pose pipeline", f"{primary.get('pipeline_version', 'n/a')} - {model.get('pose_model', 'unavailable')}", "Vision model", rep.get("model", "")],
            ["Keypoint confidence", str((primary.get("quality") or {}).get("keypoint_confidence", "n/a")), "AI observation confidence", str(rep.get("overall_confidence") or "n/a")]]
    s.append(grid_table([[Paragraph(t(a), ST["cellb"]), P(b, "cell"), Paragraph(t(c), ST["cellb"]), P(d, "cell")] for a, b, c, d in info], [80, 180, 95, CW - 355], header=False))
    sc = primary.get("score") or {}
    s += [Spacer(1, 10), *score_block(sc, primary)]
    if not measured:
        s.append(P("This report contains AI visual observations only. Joint angles and phase timings were not measured, so no biomechanical metrics or score are shown.", "small"))
    for b in bios:
        q = b.get("quality") or {}
        label = b.get("angle", "").replace("_", "-")
        if b.get("status") == "unavailable":
            s += section(f"Kinematic breakdown - {label}", P(f"Pose estimation unavailable: {b.get('error', '')}"))
            continue
        blobs_ok = phase_grid(b, blobs)
        s += section(f"Kinematic breakdown - {label} camera", P("Frames extracted from the uploaded video at the timestamps shown. Skeleton overlays are drawn from detected pose keypoints (teal lines; green = confidence >= 0.5, amber = 0.3-0.5). "
                                                                "Yellow ring with a 'BALL' pointer = ball detected by the ball model in that exact frame; dashed yellow = estimated between detections.", "small"), blobs_ok)
        s += ball_block(b.get("ball"))
        if q.get("issues"):
            s.append(KeepTogether([P("Video quality notes: " + " ".join(q["issues"]), "small")]))
        rows = [[Paragraph(h, ST["th"]) for h in ("Metric", "Value", "Unit", "Confidence", "Status")]]
        for m in b.get("metrics", []):
            ok = m.get("value") is not None and m["status"] != "locked"
            rows.append([P(m["name"] + (f" (t={m['t']}s)" if m.get("t") is not None else ""), "cell"), P(m["value"] if ok else "-", "cell"), P(m["unit"], "cell"),
                         P(m.get("confidence") if m.get("confidence") is not None else "-", "cell"),
                         P(STATUS_TXT.get(m["status"], m["status"]) + (f" - {m['reason']}" if m.get("reason") else ""), "cell")])
        metric_secs += section(f"Biomechanical metrics breakdown - {label}", grid_table(rows, [175, 50, 70, 60, CW - 355]))
    s += section("Coach summary", P(rep.get("coach_summary") or rep.get("summary") or ""))
    sw = [[Paragraph("Key strengths", ST["th"]), Paragraph("Areas to improve", ST["th"])],
          [[P("- " + x, "cell") for x in rep.get("strengths") or ["-"]], [P("- " + x, "cell") for x in rep.get("improvements") or ["-"]]]]
    s += section("Key strengths and areas to improve", grid_table(sw, [CW / 2, CW / 2]))
    s += metric_secs
    orows = [[Paragraph(h, ST["th"]) for h in ("Area", "Observation", "Time", "Evidence", "Conf.")]]
    for o in rep.get("observations") or []:
        orows.append([P((o.get("area") or "").replace("_", " "), "cell"), P(o.get("observation"), "cell"), P(f"{o.get('timestamp_s', '-')}s", "cell"),
                      P(o.get("evidence_type"), "cell"), P(o.get("confidence"), "cell")])
    s += section("Evidence-linked observations (AI visual assessment)", grid_table(orows, [80, CW - 230, 40, 60, 50]))
    drows = [[Paragraph(h, ST["th"]) for h in ("Drill", "How to do it", "Sets / reps", "Targets")]]
    for d in rep.get("drills") or []:
        drows.append([P(d.get("name"), "cell"), P(d.get("how_to"), "cell"), P(d.get("sets_reps"), "cell"), P((d.get("linked_area") or "").replace("_", " "), "cell")])
    s += section("Personalised drills", grid_table(drows, [110, CW - 260, 75, 75]))
    if rep.get("practice_plan"):
        prow = [[Paragraph(h, ST["th"]) for h in ("Day", "Focus", "Minutes")]] + [[P(p.get("day"), "cell"), P(p.get("focus"), "cell"), P(p.get("duration_min"), "cell")] for p in rep["practice_plan"]]
        s += section("Practice plan", grid_table(prow, [80, CW - 140, 60]))
    meth = (primary.get("methodology") or {})
    lim = list(rep.get("limitations") or []) + [rep.get("measured", {}).get("note", "")]
    s += section("Limitations and methodology", P(" ".join(x if x.rstrip().endswith((".", "!", "?")) else x + "." for x in lim if x)),
                 *[P(f"{k.replace('_', ' ').title()}: {v if isinstance(v, str) else '; '.join(v) if isinstance(v, list) else ', '.join(f'{a}={b}' for a, b in v.items())}", "small") for k, v in meth.items()])
    s += section("Filming guidance", P("Use a steady phone at hip height, 8-12 m away, whole body in frame and filling most of its height. Side-on for knee angles and head position; front-on for alignment and trunk tilt. Record 720p or higher at 30-60 fps in good light, with no one standing in front of the player."))
    s += section("Disclaimer", P("AI-assisted coaching report. Measurements are 2D estimates from a pose-estimation model on the uploaded video and can be affected by camera angle, occlusion, resolution and frame rate. "
                                 "Bat speed, ball speed and impact force are not measured. This is not a medical assessment, does not guarantee injury prevention or performance, and is not an official selection credential.", "small"))
    doc.build(s)
    return buf.getvalue()


async def get_or_build(rep, job, owner):
    cached = await db.analysis_reports.find_one({"id": rep["id"]}, {"pdf": 1})
    pc = (cached or {}).get("pdf") or {}
    if pc.get("version") == PDF_VERSION and pc.get("level") == job.get("report_level"):
        a = await db.media_assets.find_one({"id": pc["asset_id"]})
        if a:
            return (await asyncio.to_thread(get_object, a["storage_path"]))[0]
    blobs = {}
    for b in rep.get("biomech") or []:
        for p in b.get("phases", []):
            for k in ("overlay_asset_id", "frame_asset_id", "ball_overlay_asset_id"):
                if p.get(k):
                    blobs[p[k]] = await _blob(p[k])
    pdf = await asyncio.to_thread(build, rep, job, owner, blobs)
    if pc.get("asset_id"):
        await db.media_assets.update_one({"id": pc["asset_id"]}, {"$set": {"is_deleted": True}})
    aid = uid()
    res = await asyncio.to_thread(put_object, f"{BUCKET_PREFIX}/reports/{rep['user_id']}/{aid}.pdf", pdf, "application/pdf")
    await db.media_assets.insert_one({"id": aid, "user_id": rep["user_id"], "kind": "report_pdf", "storage_path": res["path"], "content_type": "application/pdf",
                                      "is_deleted": False, "created_at": now()})
    await db.analysis_reports.update_one({"id": rep["id"]}, {"$set": {"pdf": {"asset_id": aid, "version": PDF_VERSION, "level": job.get("report_level"), "at": now()}}})
    return pdf
