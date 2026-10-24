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

## Backlog
- P0: set RAZORPAY_WEBHOOK_SECRET; set DEV_EMAIL_OUTBOX=false for production; legal review of policy drafts
- P1: RunPod GPU pose adapter; discipline check (batting clip submitted as bowling); calibrate ideal ranges with real coach-labelled clips (score 98 on an amateur clip suggests ranges are wide); test with a real bowling clip; H.264 transcoding for non-browser codecs; recurring Razorpay Subscriptions auto-renewal; parent-to-child account linking; blog tables & video embeds; GA/GSC once IDs provided
- P2: server-side rendering/prerender for SEO, monitoring/error tracking, retention auto-cleanup job

## Next tasks
Webhook secret, real bowling clip validation, production publish on cricanalyze.in.
