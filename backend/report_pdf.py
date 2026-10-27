import io, asyncio
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.platypus import BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table, TableStyle, KeepTogether, Image
from core import db, now, uid, get_object, put_object, BUCKET_PREFIX
import report_view

PDF_VERSION = "3.2"
LOGO = Path(__file__).parent / "assets" / "logo_sm.png"
NAVY, TEAL, EMERALD, INK, MUTED, LINE, SOFT = (colors.HexColor(c) for c in ("#0B132B", "#00A6C4", "#10B981", "#1C2541", "#5B6477", "#D6DCE5", "#F2F6FA"))
W, H = A4
M = 36
CW = W - 2 * M
ST = {k: ParagraphStyle(k, fontName=f, fontSize=s, leading=s * 1.35, textColor=c, spaceAfter=a)
      for k, f, s, c, a in [("body", "Helvetica", 9.5, INK, 4), ("small", "Helvetica", 8, MUTED, 2), ("h2", "Helvetica-Bold", 13, NAVY, 6),
                            ("h3", "Helvetica-Bold", 10.5, NAVY, 3), ("cell", "Helvetica", 8.5, INK, 0), ("cellb", "Helvetica-Bold", 8.5, NAVY, 0),
                            ("th", "Helvetica-Bold", 8.5, colors.white, 0)]}


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


def crop_blob(blob, box):
    if not blob or not box:
        return blob
    import cv2, numpy as np
    im = cv2.imdecode(np.frombuffer(blob, np.uint8), cv2.IMREAD_COLOR)
    h, w = im.shape[:2]
    x0, y0, x1, y1 = int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h)
    if x1 - x0 < 20 or y1 - y0 < 20:
        return blob
    return cv2.imencode(".jpg", im[y0:y1, x0:x1], [cv2.IMWRITE_JPEG_QUALITY, 88])[1].tobytes()


def box(flow, bg=SOFT, bar=TEAL):
    tb = Table([[flow]], colWidths=[CW])
    tb.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), bg), ("LINEBEFORE", (0, 0), (0, -1), 4, bar), ("LEFTPADDING", (0, 0), (-1, -1), 10),
                            ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    return tb


def bullets(items, st="body"):
    return [P("• " + x, st) for x in items if x]


def timeline_grid(a, blobs):
    tl = a["timeline"]
    n = max(1, len(tl))
    cw = CW / n - 4
    cells = []
    for p in tl:
        blob = blobs.get(p.get("ball_overlay_asset_id")) or blobs.get(p.get("overlay_asset_id")) or blobs.get(p.get("frame_asset_id"))
        if blob and p["status"] != "unavailable":
            img = fit_image(crop_blob(blob, p.get("crop")), cw - 4, 120)
        else:
            img = Table([[P("Not assessed reliably" if p["status"] == "unavailable" else "Frame not available", "small")]], colWidths=[cw - 6], rowHeights=[70],
                        style=[("BACKGROUND", (0, 0), (-1, -1), SOFT), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (0, 0), (-1, -1), "CENTER")])
        meta = p["status_label"] + (f" - {p['t']}s (frame {p['frame_index']})" if p.get("t") is not None else "")
        cell = [img, Paragraph(f"<b>{t(p['name'])}</b>", ST["cellb"]), P(meta, "small"), P(p["note"], "small")]
        cell += [P(m, "small") for m in p["metrics"]]
        if p.get("overlay_note"):
            cell.append(P(p["overlay_note"], "small"))
        cells.append(cell)
    tb = Table([cells], colWidths=[CW / n] * n)
    tb.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2)]))
    return tb


def metric_bar(m, w=150):
    from reportlab.graphics.shapes import Drawing, Rect, Circle
    d = Drawing(w, 12)
    d.add(Rect(0, 4, w, 4, fillColor=LINE, strokeColor=None))
    d.add(Rect(0, 4, w * m["position"], 4, fillColor=TEAL, strokeColor=None))
    d.add(Circle(w * m["position"], 6, 4, fillColor=NAVY, strokeColor=colors.white))
    return d


def score_panel(sc, vq):
    if sc.get("value") is not None:
        head = Paragraph(f"<font size=7.5 color='#5B6477'><b>OVERALL TECHNIQUE SCORE</b></font><br/><font size=30 color='#0B132B'><b>{sc['value']}</b></font>"
                         f"<font size=11 color='#5B6477'> / 100</font><br/><font size=9 color='{'#10B981' if sc['status'] == 'complete' else '#B45309'}'><b>{t(sc['label'])}</b></font>",
                         ParagraphStyle("score", parent=ST["body"], leading=34))
    else:
        head = Paragraph(f"<font size=7.5 color='#5B6477'><b>OVERALL TECHNIQUE SCORE</b></font><br/><font size=12 color='#B45309'><b>{t(sc['label'])}</b></font>",
                         ParagraphStyle("prov", parent=ST["body"], leading=16))
    left = [head, Spacer(1, 4), P(sc["text"], "small")]
    if sc.get("evidence"):
        left.append(P(f"Evidence: {sc['evidence']}", "small"))
    if sc.get("tip"):
        left.append(P(f"Filming tip: {sc['tip']}", "small"))
    right = [Paragraph(f"<b>Video quality: {t(vq['rating'])}</b>", ST["h3"]), P(vq["text"], "small"), P("Video quality describes the footage, not the player's technique.", "small")]
    if sc.get("components"):
        right += [Spacer(1, 4), grid_table([[Paragraph(h, ST["th"]) for h in ("Area", "Score", "Measured")]] +
                                           [[P(c["name"], "cell"), P(f"{c['score']}/100", "cell"), P(f"{c['measured']} of {c['of']}", "cell")] for c in sc["components"]], [120, 55, 60])]
    tb = Table([[left, right]], colWidths=[CW * 0.48, CW * 0.52])
    tb.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, 0), SOFT), ("LINEBEFORE", (0, 0), (0, 0), 4, TEAL), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 10), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    return tb


def build(rep, job, owner, blobs):
    v = rep["view"]
    buf = io.BytesIO()
    title = f"{v['header']['analysis_type']} Technique Report"
    generated = report_view.ist(now())
    doc = BaseDocTemplate(buf, pagesize=A4, leftMargin=M, rightMargin=M, topMargin=84, bottomMargin=44, title=title, author="CricAnalyze")
    draw = _page(title, rep["id"], generated)
    doc.addPageTemplates([PageTemplate(id="first", frames=[Frame(M, 44, CW, H - 84 - 44, id="f1")], onPage=draw, autoNextPageTemplate="later"),
                          PageTemplate(id="later", frames=[Frame(M, 44, CW, H - 50 - 44, id="f2")], onPage=draw)])
    h = v["header"]
    info = [["Player", h["player"] or "", "Report date", h["date"]], ["Analysis", h["analysis_type"] + (f" - {h['shot_type']}" if h.get("shot_type") else ""), "Camera", ", ".join(h["angles"]) or "-"],
            ["Video quality", h["video_quality"], "Score status", h["score_status"]]]
    s = [Paragraph(t(h["player"] or "Player"), ParagraphStyle("ttl", fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=NAVY, spaceAfter=4)),
         grid_table([[Paragraph(t(a), ST["cellb"]), P(b, "cell"), Paragraph(t(c), ST["cellb"]), P(d, "cell")] for a, b, c, d in info], [75, 190, 75, CW - 340], header=False), Spacer(1, 8)]
    s.append(box([Paragraph("<b>Three key takeaways</b>", ST["h3"]),
                  *[P(f"{i + 1}. {x}") for i, x in enumerate(v["takeaways"])]], bar=EMERALD))
    s += [Spacer(1, 8), score_panel(v["score"], v["video_quality"])]
    if v["whats_working"]:
        s += section("What's working", *bullets(v["whats_working"]))
    for a in v["angles"]:
        if a["metrics"]:
            rows = [[Paragraph(x, ST["th"]) for x in ("Measurement", "Value", "Scale", "What it means")]]
            rows += [[P(m["name"] + (f" ({m['t']}s)" if m.get("t") is not None else ""), "cell"), P(m["display"], "cell"), metric_bar(m, 110), P(m["interpretation"], "cell")] for m in a["metrics"]]
            s += section(f"Measurements - {a['angle']} camera", grid_table(rows, [130, 60, 120, CW - 310]),
                         P("Values are measured from the video. Target ranges are not shown until coach-approved references are available.", "small"))
        if a["timeline"]:
            if a.get("analysed_window"):
                s.append(P(a["analysed_window"], "small"))
            s += section(f"Technique timeline - {a['angle']} camera", timeline_grid(a, blobs),
                         P("Frames are cropped around the player from the original video at the times shown. 'Approximate timing' frames are best estimates, not exact events.", "small"))
        if a.get("ball"):
            s.append(P("Ball: " + a["ball"]["text"] + " " + " ".join(a["ball"]["notes"]), "small"))
        if a.get("assessments"):
            rows = [[Paragraph(x, ST["th"]) for x in ("Assessment", "Result", "Details", "Reference frame")]]
            for x in a["assessments"]:
                det = "<br/>".join(f"{d['label']}: {d['value']}" for d in x["details"]) + (f"<br/>AI visual note (foot direction): {x['ai_note']}" if x.get("ai_note") else "")
                img = fit_image(blobs[x["overlay_asset_id"]], 110, 80) if blobs.get(x.get("overlay_asset_id")) else P("—" if x["status"] != "measured" else "", "cell")
                rows.append([P(f"<b>{x['name']}</b><br/>{x['status_label']}", "cell"), P(x["summary"] or x["reason"], "cell"), P(det or "", "cell"), img])
            s += section(f"Bowling biomechanics - {a['angle']} camera", grid_table(rows, [95, 120, CW - 335, 120]),
                         P("Measured from the original video frames at their original timestamps (2D body tracking). These assessments are not part of the technique score. "
                           "Trunk lean is whole-trunk lean; lower-back bending and spinal curvature are not measured.", "small"))
        if not a["pose_available"]:
            s += section(f"{a['angle'].title()} camera", P("Body tracking wasn't available for this clip, so only the coach's visual notes are shown."))
    c = v["coaching"]
    flow = []
    if c.get("priority"):
        flow += [Paragraph("<b>Priority to improve</b>", ST["h3"]), P(c["priority"])]
    if c.get("why"):
        flow += [Paragraph("<b>Why it matters</b>", ST["h3"]), P(c["why"])]
    if c.get("how"):
        flow += [Paragraph("<b>How to practise it</b>", ST["h3"]), P(c["how"])]
    if c.get("measured_basis"):
        flow.append(P("Based on measurements: " + "; ".join(c["measured_basis"]) + ". Coaching text is an AI interpretation of the video and these measurements.", "small"))
    if flow:
        s += section("Coaching feedback", box(flow))
    if v["drills"]:
        rows = [[Paragraph(x, ST["th"]) for x in ("Drill", "Objective and instructions", "Dose", "Avoid")]]
        rows += [[P(d["name"], "cell"), [P(d.get("objective") or "", "cell"), P(d.get("instructions") or "", "cell")], P(d.get("dosage") or "", "cell"), P(d.get("mistakes") or "", "cell")] for d in v["drills"]]
        s += section("Personalised drills", grid_table(rows, [100, CW - 280, 80, 100]))
    if v.get("practice_plan"):
        prow = [[Paragraph(x, ST["th"]) for x in ("Day", "Focus", "Minutes")]] + [[P(p.get("day"), "cell"), P(p.get("focus"), "cell"), P(p.get("duration_min"), "cell")] for p in v["practice_plan"]]
        s += section("Practice plan", grid_table(prow, [80, CW - 140, 60]))
    pr = v.get("progress")
    if pr:
        rows = [[Paragraph(x, ST["th"]) for x in ("Measurement", f"Previous ({pr['previous_date']})", "Latest", "Change")]]
        rows += [[P(m["name"], "cell"), P(m["before_display"], "cell"), P(m["after_display"], "cell"), P(m["change_display"], "cell")] for m in pr["metrics"]]
        sb, sa = pr["score_before"], pr["score_after"]
        rows.append([P("Overall score", "cell"), P(f"{sb['value'] if sb['value'] is not None else '-'} ({sb['status']})", "cell"),
                     P(f"{sa['value'] if sa['value'] is not None else '-'} ({sa['status']})", "cell"), P("", "cell")])
        s += section("Progress comparison", grid_table(rows, [150, 130, 130, CW - 410]), P(pr["explanation"], "small"))
    s += section("Your action plan", box([P(f"{i + 1}. {x}") for i, x in enumerate(v["action_plan"])], bar=EMERALD))
    s += section("Filming tips for your next clip", *bullets(v["filming_tips"]))
    s += section("About this report", P(v["score_method"], "small"), P(v["video_quality"]["method"], "small"), P(v["limitations"], "small"),
                 P("AI-assisted coaching report. Not a medical assessment, does not guarantee injury prevention or performance, and is not an official selection credential.", "small"))
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
    for a in rep["view"]["angles"]:
        for p in a["timeline"] + (a.get("assessments") or []):
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
