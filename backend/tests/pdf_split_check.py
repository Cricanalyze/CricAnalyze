# Synthetic stress: long tables must split across pages with repeated header; no-biomech vision-only variant
import sys, asyncio, fitz, copy
sys.path.insert(0, '/app/backend')
from dotenv import load_dotenv
load_dotenv('/app/backend/.env')
import report_pdf
from core import db


async def main():
    rep = await db.analysis_reports.find_one({"assessment_type": "measured_biomechanical"}, {"_id": 0}, sort=[("created_at", -1)])
    job = await db.analysis_jobs.find_one({"id": rep["job_id"]}, {"_id": 0})
    owner = await db.users.find_one({"id": job["user_id"]})
    r2 = copy.deepcopy(rep)
    r2["observations"] = [{"area": "stance", "observation": f"TEST long observation row {i} " + "lorem ipsum " * 12, "timestamp_s": i, "evidence_type": "observed", "confidence": "low"} for i in range(45)]
    pdf = report_pdf.build(r2, job, owner, {})
    open('/tmp/long.pdf', 'wb').write(pdf)
    r3 = copy.deepcopy(rep); r3["biomech"] = []; r3["assessment_type"] = "vision_only"
    open('/tmp/vision.pdf', 'wb').write(report_pdf.build(r3, job, owner, {}))

asyncio.run(main())
d = fitz.open('/tmp/long.pdf')
print("long pages", len(d))
for i, pg in enumerate(d):
    t = pg.get_text()
    print(i + 1, "obs-header-repeat" if "Observation" in t and "Evidence" in t else "", "rows:", t.count("TEST long observation row"))
    pg.get_pixmap(dpi=60).save(f'/tmp/long_p{i+1}.png')
v = fitz.open('/tmp/vision.pdf')
print("vision pages", len(v), "insufficient" if "Insufficient evidence" in v[0].get_text() else "NO-INSUFF", "No pose" if "No pose measurements" in v[0].get_text() else "")
v[0].get_pixmap(dpi=60).save('/tmp/vision_p1.png')
