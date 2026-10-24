# CricAnalyze — Deployment & Operations Guide

## Environment variables (backend/.env) — placeholders only
```
MONGO_URL=mongodb://<host>:27017
DB_NAME=<db_name>
CORS_ORIGINS=https://cricanalyze.in
APP_SECRET=<64-char random hex>          # signs sessions, OTP hashes, media links
APP_URL=https://cricanalyze.in
ADMIN_EMAIL=cricanalyze.in@gmail.com      # verified signup with this email becomes super_admin
COOKIE_SECURE=true
DEV_EMAIL_OUTBOX=false                    # MUST be false in production
SMTP_HOST=<from Hostinger Email settings>
SMTP_PORT=465
SMTP_SECURE=ssl                           # ssl (465) or starttls (587)
SMTP_USER=noreply@cricanalyze.in
SMTP_PASS=<mailbox password>
SMTP_FROM_EMAIL=noreply@cricanalyze.in
SMTP_FROM_NAME=CricAnalyze
RAZORPAY_KEY_ID=rzp_test_xxx | rzp_live_xxx
RAZORPAY_KEY_SECRET=<secret>
RAZORPAY_WEBHOOK_SECRET=<webhook secret>
EMERGENT_LLM_KEY=<key>                    # AI vision analysis, coach, blog AI, object storage
AI_INFERENCE_PROVIDER=vision_llm
AI_MODEL=claude-sonnet-5-5
AI_INFERENCE_ENDPOINT=                    # future RunPod / pose-model endpoint (adapter placeholder)
AI_INFERENCE_API_KEY=
VIDEO_STORAGE_PROVIDER=emergent
VIDEO_STORAGE_BUCKET=cricanalyze
GA_MEASUREMENT_ID=                        # optional
GSC_VERIFICATION=                         # optional
```
Set secrets only through the platform's secure secrets panel. Never commit them.

## Razorpay webhook
Dashboard → Settings → Webhooks → URL `https://cricanalyze.in/api/billing/webhook`, events: `payment.captured`, `payment.failed`, `order.paid`, `refund.processed`. Copy the secret into `RAZORPAY_WEBHOOK_SECRET`. Until set, the webhook returns 503 and payments still activate through server-side verification on checkout.

## Admin bootstrap
No default admin exists. Sign up with the ADMIN_EMAIL address, verify the OTP, and the account becomes `super_admin`. Promote others from Admin → Users.

## Background work
The API process runs an in-process analysis worker (concurrency from Admin → Flags & limits) and a 30-second scheduler (scheduled blog publishing, subscription expiry). Jobs stuck in `processing` are re-queued on restart.

## Indexes / migrations
Created automatically at startup (`ensure_indexes` in server.py). Plans and blog categories are seeded only when empty.

## Health checks
`GET /api/health` (DB + queue depth). Admin → Integrations has live tests for SMTP, AI, storage and Razorpay.

## Backup & restore
`mongodump --uri "$MONGO_URL" --db "$DB_NAME" --out backup-$(date +%F)` / `mongorestore --uri "$MONGO_URL" backup-YYYY-MM-DD`. Run daily; keep 30 days. Videos/images live in object storage (not MongoDB).

## Domain & SEO
Point cricanalyze.in DNS to the deployment, confirm HTTPS, then submit `https://cricanalyze.in/api/sitemap.xml` in Search Console. robots.txt blocks /app, /admin, auth pages and the API.

## Rollback
Use the platform's rollback to a previous checkpoint; database is not rolled back automatically — restore from backup if a migration changed data.
