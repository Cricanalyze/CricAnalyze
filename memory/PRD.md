# CricAnalyze — PRD

## Original problem statement
"CRICANALYZE — A–Z MASTER BUILD PROMPT: Production-Ready AI Cricket Video Analysis SaaS" owned by Buddy Innovations and Technologies Pvt Ltd (cricanalyze.in, noreply@cricanalyze.in, Hostinger SMTP, MongoDB). 31 sections: brand (navy/teal/emerald, official logo), 8 user roles with server-side RBAC, email OTP verification/reset/step-up, auth security, public website + legal pages, video upload & processing, AI batting & bowling analysis, hosted AI adapters, reports + PDF, subscriptions & credits, Razorpay billing, historical comparison, AI coach, multi-angle, training planner, academy dashboard, player passport, challenges, Ask CricAnalyze, blog CMS, SEO, admin control center, MongoDB architecture, API/integration settings, cost controls, privacy/security, testing, deployment. Never fabricate AI results, payments, email delivery or integration status.

User choices: logo to be uploaded later (text wordmark placeholder now); vision AI reads video frames; Claude Sonnet 5.5; build everything at once; SMTP + Razorpay keys supplied (webhook secret not yet).

## Architecture
FastAPI (modules: core, auth_routes, analysis_routes, billing_routes, coach_routes, academy_routes, blog_routes, admin_routes) + MongoDB + React (CRA, shadcn, TipTap, recharts, react-helmet-async). Cookie sessions (httpOnly) + CSRF double-submit; Argon2id; HMAC-hashed OTPs; Emergent object storage with HMAC-signed expiring media URLs; in-process async worker + scheduler; Claude Sonnet 5.5 vision on cv2-sampled frames; Razorpay orders + signature + API fetch verification + webhook.

## Personas
Player, parent/guardian, coach, academy admin, content editor, platform admin, super admin.

## Implemented (2026-10-24)
- Auth: signup+OTP, resend, lockout, OTP login, forgot/reset token, sessions list/revoke, step-up, email change, password change, guardian consent OTP for minors, export, deletion, admin bootstrap via ADMIN_EMAIL
- Branded email templates, SMTP test, email logs (queued/accepted/failed)
- Public site: home, features, how-it-works, pricing, about, contact, FAQ, 5 legal drafts, 404, blog (list/category/tag/author/post), SEO meta/canonical/OG/JSON-LD, robots, sitemap
- Upload (magic-byte + cv2 validation, duration/res/size limits), multi-angle, job queue, retries, refunds, idempotency, reports (observed vs inferred, confidence, frames, drills, plan, limitations), tiered reports, PDF
- Plans/credits/ledger, admin plan editor, coupons, Razorpay checkout/verify/webhook/refund, grants
- Timeline, comparisons, AI coach & Ask CricAnalyze (SSE), training planner (AI/manual/coach-approved, completion), drill library, challenges/streak/badges, opt-in leaderboard, passport + revocable share links
- Academy: create, invite, accept, groups, coach assignments, consent sharing, attendance, feedback, CSV export, tenant isolation
- Blog CMS: TipTap editor, autosave, revisions, publish/schedule/unpublish/archive/duplicate/delete, redirects, AI writing assistant, image upload
- Admin: overview analytics & cost alert, users/roles/suspend, plans, coupons, payments/ledger, jobs, integrations, flags/limits, SEO checks & page meta, academies, support, audit
- Tested: iteration_1 (backend 14/17 → 3 security findings fixed: pre-account hijack, XFF spoofing, date 500)

## Biomechanical report upgrade (2026-10-24)
User request: professional biomechanical assessment PDF inspired by the attached reference (front_foot_defense_report.pdf), CricAnalyze branding/logo, real CV measurements only, no fabricated metrics, evidence-linked phase frames, batting/bowling templates, score only via a documented method, secure entitled export. Choices: server pose now, RunPod later; official logo + reference attached.
- pose_pipeline.py: RTMPose-m + YOLOX via rtmlib/onnxruntime on CPU (MediaPipe unusable: libGLESv2 missing); phase extraction (detected/estimated/unavailable); geometry metrics with confidence gating; shoulder-width foreshortening guard; occlusion vs distance quality messages; score ca-score-v1 withheld unless >=3 metrics, >=60% weight coverage, >=2 detected phases
- report_pdf.py v2.3: official logo header, reference section order (title/meta → overall score → kinematic phase grid → coach summary → strengths/improve → metrics breakdown), evidence table, drills, plan, methodology, filming guidance, disclaimer, footer with report ID/page; tighter continuation pages; old cached PDFs marked deleted on rebuild
- Official logo in site header/sidebar/auth (frontend/public/logo.png)
- Tested: iteration_2: clear batting measured (score 98), distant/low-res/legs-occluded → score withheld, bowling template runs, PDF auth owner 200 / other 404 / anon 401, signed media URLs 403 on tamper

## Score + ball tracking (2026-10-24)
User request: prominent overall technique score /100 (separate batting/bowling rubrics, components + contributions, coverage indicator, stored version/inputs, reproducible, provisional when insufficient, no 'official' claims) and real cricket ball detection/tracking with yellow marker + 'BALL' pointer, trail, estimated segments, gap reasons, toggles, legend, viewer with frame stepping/scrubber; PDF keeps 5 phases on page 1 + ball summary. Choices: general sports-ball detector on server; every frame up to 15 s; component scores only (no overall) when insufficient; user will upload own real clips.
- score_engine.py ca-score-v2: rubrics per type, documented normalisation, est-phase x0.5, missing excluded, gate (>=3 metrics, >=60% coverage, >=2 detected phases, >=2 components), evidence level, strongest/opportunities, inputs + rubric hash stored; GET /api/analyses/{id}/score-check; tests/test_score_engine.py (7 pass)
- ball_pipeline.py ca-ball-v1: YOLOX-s COCO 'sports ball' ONNX (models/yolox_s.onnx, BALL_PROVIDER, BALL_MODEL_FILE, BALL_MARKER_COLOR env), native crop + tiled acquisition + periodic full-frame, constant-velocity tracking, confirmed tracks only, interpolation <=6 frames labelled estimated, gap reasons; failures -> 'unavailable', job continues
- Phase frames get ball overlay only when an observed detection exists on that exact frame; AnalysisViewer.jsx (canvas skeleton + ball, toggles, frame step, scrubber, readout, legend, guidance); /media supports HTTP Range
- PDF v2.7: score + component table, 5-phase row, ball summary on page 1
- Tested iteration_3: synthetic real-ball-photo clips (fast/blur, occlusion, exit) max error ~1px, no false positives; 10px ball and no-ball clips -> 'not reliably detected'. NOT yet tested on real cricket footage (awaiting user clips)

## Backlog
- P0: set RAZORPAY_WEBHOOK_SECRET; validate ball tracking on the user's real clips (general COCO detector scored only 0.23 on a close-up cricket ball photo; a cricket-trained model may be needed); set DEV_EMAIL_OUTBOX=false for production; legal review of policy drafts
- P1: RunPod GPU pose adapter; H.264/HEVC transcoding on upload (iPhone HEVC won't play in Chrome viewer); stream Range responses instead of loading whole object; discipline check (batting clip submitted as bowling); calibrate ideal ranges with real coach-labelled clips (score 98 on an amateur clip suggests ranges are wide); test with a real bowling clip; H.264 transcoding for non-browser codecs; recurring Razorpay Subscriptions auto-renewal; parent-to-child account linking; blog tables & video embeds; GA/GSC once IDs provided
- P2: server-side rendering/prerender for SEO, monitoring/error tracking, retention auto-cleanup job

## Next tasks
Webhook secret, real bowling clip validation, production publish on cricanalyze.in.

## Environment setup (2026-10-26)
- Imported repo into this workspace; installed backend/frontend deps; .env configured (real Hostinger SMTP, DEV_EMAIL_OUTBOX=false, Emergent LLM key, Razorpay test keys, new APP_SECRET, APP_URL = preview URL)
- Verified: SMTP login OK, Razorpay test order OK, health OK, public pages + auth guards pass smoke test
- Fix: OTP send failure now returns 503 (502 was masked by Cloudflare) and deletes the unsent OTP so retry works

## Own keys: Claude + Ultralytics YOLO26n (2026-10-26)
- All LLM features (reports, coach/ask, planner, blog AI) use ANTHROPIC_API_KEY (core.AI_KEY); EMERGENT_LLM_KEY kept only for object storage
- ultralytics_client.py: Ultralytics Platform hosted yolo26n (ball) + yolo26n-pose (player+17 keypoints); POSE_PROVIDER/BALL_PROVIDER=ultralytics_yolo26; rate limiter ULTRALYTICS_RPM=20; ULTRALYTICS_DETECT_URL/POSE_URL override for dedicated deployments; ball = up to ULTRALYTICS_BALL_MAX_FRAMES (60) consecutive frames around swing peak at 1280px
- Admin Integrations: Ultralytics row + test button
- Verified: Claude reply OK; pose 5 persons on test image; full pipeline on 3s clip: pose 24 frames/70s, ball 60 frames/180s
- Backlog: dedicated Ultralytics deployment to lift 20 req/min (two simultaneous analyses share the limit and may hit the 5-min timeout); test on real cricket clips
