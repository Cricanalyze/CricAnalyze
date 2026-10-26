import os, asyncio
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.middleware.cors import CORSMiddleware
from core import db, log, init_storage, sanitize_error
import auth_routes, analysis_routes, billing_routes, coach_routes, academy_routes, blog_routes, admin_routes

app = FastAPI(title="CricAnalyze API", version="1.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
for m in (auth_routes, analysis_routes, billing_routes, coach_routes, academy_routes, blog_routes, admin_routes):
    app.include_router(m.router)

CSRF_EXEMPT = {"/api/billing/webhook", "/api/auth/login", "/api/auth/signup", "/api/auth/verify-email", "/api/auth/login/otp/verify",
               "/api/auth/login/otp/request", "/api/auth/forgot", "/api/auth/reset/verify", "/api/auth/reset", "/api/auth/resend", "/api/contact"}


@app.middleware("http")
async def security(request: Request, call_next):
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.url.path.startswith("/api") \
            and request.url.path not in CSRF_EXEMPT and request.cookies.get("ca_session"):
        tok = request.headers.get("x-csrf-token")
        if not tok or tok != request.cookies.get("ca_csrf"):
            return JSONResponse({"detail": "Security check failed. Please refresh the page and try again."}, status_code=403)
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if request.url.path.startswith("/api") and not request.url.path.startswith(("/api/sitemap", "/api/blog/images")):
        resp.headers.setdefault("X-Robots-Tag", "noindex")
    return resp


@app.exception_handler(RequestValidationError)
async def validation_handler(request, exc):
    errs = exc.errors()
    msg = "; ".join(f"{'.'.join(str(x) for x in e['loc'][1:])}: {e['msg']}" for e in errs[:3])
    return JSONResponse({"detail": msg or "Invalid input."}, status_code=422)


@app.exception_handler(Exception)
async def unhandled(request, exc):
    log.error(f"unhandled {request.url.path} {sanitize_error(exc)}")
    return JSONResponse({"detail": "Something went wrong on our side. Please try again."}, status_code=500)


app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
                   allow_methods=["*"], allow_headers=["*"])


async def ensure_indexes():
    await db.users.create_index("email", unique=True)
    await db.users.create_index("id", unique=True)
    await db.sessions.create_index("token_hash", unique=True)
    await db.sessions.create_index("expires_at", expireAfterSeconds=0)
    await db.email_verifications.create_index([("email", 1), ("purpose", 1), ("created_at", -1)])
    await db.email_verifications.create_index("expires_at", expireAfterSeconds=86400)
    await db.password_reset_tokens.create_index("token_hash", unique=True)
    await db.password_reset_tokens.create_index("expires_at", expireAfterSeconds=86400)
    await db.rate_limits.create_index("exp", expireAfterSeconds=0)
    await db.analysis_jobs.create_index([("user_id", 1), ("idempotency_key", 1)], unique=True)
    await db.analysis_jobs.create_index([("status", 1), ("next_run_at", 1)])
    await db.analysis_reports.create_index([("user_id", 1), ("analysis_type", 1), ("created_at", -1)])
    await db.subscriptions.create_index([("user_id", 1), ("status", 1), ("expires_at", 1)])
    await db.payments.create_index("order_id", unique=True)
    await db.plans.create_index("slug", unique=True)
    await db.coupons.create_index("code", unique=True)
    await db.blog_posts.create_index("slug", unique=True)
    await db.blog_posts.create_index([("status", 1), ("published_at", -1)])
    await db.blog_redirects.create_index("from_slug", unique=True)
    await db.academy_memberships.create_index([("academy_id", 1), ("user_id", 1)], unique=True)
    await db.coach_assignments.create_index([("academy_id", 1), ("coach_id", 1), ("player_id", 1)], unique=True)
    await db.training_completions.create_index([("user_id", 1), ("plan_id", 1), ("item_id", 1)], unique=True)
    await db.passport_shares.create_index("token_hash", unique=True)
    await db.audit_logs.create_index("created_at")


async def scheduler_loop():
    while True:
        try:
            await blog_routes.publish_due()
            await billing_routes.expire_subscriptions()
        except Exception as e:
            log.error(f"scheduler error {sanitize_error(e)}")
        await asyncio.sleep(30)


@app.on_event("startup")
async def startup():
    await ensure_indexes()
    await billing_routes.seed_plans()
    await blog_routes.seed_blog()
    try:
        await asyncio.to_thread(init_storage)
    except Exception as e:
        log.error(f"storage init failed {sanitize_error(e)}")
    asyncio.create_task(analysis_routes.worker_loop())
    asyncio.create_task(scheduler_loop())
