# Render report PDFs to PNG for visual inspection + text checks (pymupdf)
import sys, asyncio, fitz
sys.path.insert(0, '/app/backend')
from dotenv import load_dotenv
load_dotenv('/app/backend/.env')


async def build_latest():
    import report_pdf
    from core import db
    rep = await db.analysis_reports.find_one({"assessment_type": "measured_biomechanical"}, {"_id": 0}, sort=[("created_at", -1)])
    job = await db.analysis_jobs.find_one({"id": rep["job_id"]}, {"_id": 0})
    owner = await db.users.find_one({"id": job["user_id"]})
    await db.analysis_reports.update_one({"id": rep["id"]}, {"$unset": {"pdf": ""}})  # force rebuild
    pdf = await report_pdf.get_or_build(rep, job, owner)
    open('/tmp/latest_report.pdf', 'wb').write(pdf)
    print("REPORT", rep["id"], "JOB", rep["job_id"])

asyncio.run(build_latest())
for name in ['/tmp/latest_report.pdf', '/tmp/player_report.pdf']:
    d = fitz.open(name)
    print(name, "pages", len(d))
    for i, pg in enumerate(d):
        txt = pg.get_text()
        imgs = pg.get_images(full=True)
        print(f" p{i+1} imgs={len(imgs)} OVERALL SCORE={'OVERALL SCORE' in txt} footer_page={'Page %d' % (i+1) in txt} report_id={'Report ' in txt}")
        for info in pg.get_image_info():
            print("   img bbox", [round(v) for v in info['bbox']], "src", info['width'], info['height'],
                  "aspect_src", round(info['width'] / info['height'], 3), "aspect_draw", round((info['bbox'][2]-info['bbox'][0]) / (info['bbox'][3]-info['bbox'][1]), 3))
        pg.get_pixmap(dpi=70).save(f"{name[:-4]}_p{i+1}.png")
