import re, asyncio
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Request, Response, HTTPException, Depends, UploadFile, File
from pydantic import BaseModel, Field
from core import db, now, uid, audit, EDITOR, ADMIN, optional_user, put_object, get_object, BUCKET_PREFIX, APP_URL, llm_text, get_settings, STAFF

router = APIRouter(prefix="/api")
SITE = "https://cricanalyze.in"
DEFAULT_CATEGORIES = ["Batting Technique", "Bowling Technique", "Cricket Fitness", "Cricket Coaching", "AI Cricket Analysis",
                      "Cricket Training Drills", "Youth Cricket Development", "Cricket Technology", "Equipment Guides", "CricAnalyze Updates"]
PUBLIC_PATHS = ["/", "/features", "/how-it-works", "/pricing", "/about", "/contact", "/faq", "/blog", "/privacy-policy",
                "/terms-and-conditions", "/refund-policy", "/cookie-policy", "/disclaimer"]


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")[:90]


def sanitize_html(h):
    h = re.sub(r"<\s*(script|style|object|embed|form)[^>]*>.*?<\s*/\s*\1\s*>", "", h or "", flags=re.S | re.I)
    h = re.sub(r"\son\w+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", "", h, flags=re.I)
    h = re.sub(r"(href|src)\s*=\s*([\"'])\s*javascript:[^\"']*\2", r'\1="#"', h, flags=re.I)
    h = re.sub(r"<iframe(?![^>]*src=[\"']https://(www\.youtube(-nocookie)?\.com|player\.vimeo\.com)/)[^>]*>.*?</iframe>", "", h, flags=re.S | re.I)
    return h


async def seed_blog():
    if await db.blog_categories.count_documents({}) == 0:
        for i, c in enumerate(DEFAULT_CATEGORIES):
            await db.blog_categories.insert_one({"id": uid(), "name": c, "slug": slugify(c), "sort": i})
    if await db.blog_authors.count_documents({}) == 0:
        await db.blog_authors.insert_one({"id": uid(), "name": "CricAnalyze Team", "slug": "cricanalyze-team", "bio": "The team building CricAnalyze."})


def live_q():
    return {"$or": [{"status": "published"}, {"status": "scheduled", "publish_at": {"$lte": now()}}]}


PUBLIC_FIELDS = {"_id": 0, "revisions": 0, "created_by": 0}


def to_public(p):
    p.pop("autosave", None)
    if p.get("featured_image_id"):
        p["featured_image_url"] = f"/api/blog/images/{p['featured_image_id']}"
    return p


@router.get("/blog/posts")
async def public_posts(category: Optional[str] = None, tag: Optional[str] = None, author: Optional[str] = None, page: int = 1, limit: int = 9):
    q = live_q()
    if category:
        q["categories"] = category
    if tag:
        q["tags"] = tag
    if author:
        q["author_slug"] = author
    limit = min(max(limit, 1), 30)
    total = await db.blog_posts.count_documents(q)
    rows = await db.blog_posts.find(q, {**PUBLIC_FIELDS, "content_html": 0}).sort("published_at", -1).skip((max(page, 1) - 1) * limit).limit(limit).to_list(limit)
    return {"posts": [to_public(r) for r in rows], "total": total, "page": page, "pages": (total + limit - 1) // limit}


@router.get("/blog/meta")
async def blog_meta():
    return {"categories": await db.blog_categories.find({}, {"_id": 0}).sort("sort", 1).to_list(100),
            "authors": await db.blog_authors.find({}, {"_id": 0}).to_list(100),
            "tags": await db.blog_tags.find({}, {"_id": 0}).to_list(500)}


@router.get("/blog/posts/{slug}")
async def public_post(slug: str, preview: Optional[str] = None, request: Request = None):
    u = await optional_user(request)
    if preview and u and u["role"] in STAFF | {"content_editor"}:
        p = await db.blog_posts.find_one({"slug": slug}, PUBLIC_FIELDS)
    else:
        p = await db.blog_posts.find_one({"slug": slug, **live_q()}, PUBLIC_FIELDS)
    if not p:
        r = await db.blog_redirects.find_one({"from_slug": slug})
        if r:
            return {"redirect": r["to_slug"]}
        raise HTTPException(404, "Article not found.")
    related = await db.blog_posts.find({**live_q(), "slug": {"$ne": slug}, "categories": {"$in": p.get("categories", [])}},
                                       {**PUBLIC_FIELDS, "content_html": 0}).sort("published_at", -1).limit(3).to_list(3)
    p["related"] = [to_public(r) for r in related]
    p["author"] = await db.blog_authors.find_one({"slug": p.get("author_slug")}, {"_id": 0})
    return to_public(p)


@router.get("/blog/images/{iid}")
async def blog_image(iid: str):
    a = await db.media_assets.find_one({"id": iid, "kind": "blog_image", "is_deleted": False})
    if not a:
        raise HTTPException(404, "Not found.")
    data, _ = await asyncio.to_thread(get_object, a["storage_path"])
    return Response(data, media_type=a["content_type"], headers={"Cache-Control": "public, max-age=86400"})


# ---------- admin CMS ----------
class PostIn(BaseModel):
    title: str = Field(min_length=3, max_length=160)
    slug: Optional[str] = None
    excerpt: str = Field("", max_length=400)
    content_html: str = ""
    featured_image_id: Optional[str] = None
    featured_image_alt: str = ""
    categories: List[str] = []
    tags: List[str] = []
    author_slug: str = "cricanalyze-team"
    seo_title: str = Field("", max_length=70)
    seo_description: str = Field("", max_length=170)
    canonical_url: str = ""
    og_image_id: Optional[str] = None
    noindex: bool = False
    faqs: List[dict] = []
    ai_generated: bool = False


async def unique_slug(slug, exclude_id=None):
    base, n = slug, 2
    while await db.blog_posts.find_one({"slug": slug, **({"id": {"$ne": exclude_id}} if exclude_id else {})}):
        slug = f"{base}-{n}"
        n += 1
    return slug


async def upsert_tags(tags):
    out = []
    for t in tags:
        s = slugify(t)
        if s:
            await db.blog_tags.update_one({"slug": s}, {"$setOnInsert": {"id": uid(), "name": t.strip(), "slug": s}}, upsert=True)
            out.append(s)
    return out


@router.get("/admin/blog/posts")
async def admin_posts(status: Optional[str] = None, e=Depends(EDITOR)):
    q = {"status": status} if status else {}
    return await db.blog_posts.find(q, {"_id": 0, "content_html": 0, "autosave": 0}).sort("updated_at", -1).to_list(500)


@router.get("/admin/blog/posts/{pid}")
async def admin_post(pid: str, e=Depends(EDITOR)):
    p = await db.blog_posts.find_one({"id": pid}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Post not found.")
    p["revisions"] = await db.blog_revisions.find({"post_id": pid}, {"_id": 0, "content_html": 0}).sort("created_at", -1).to_list(20)
    return p


@router.post("/admin/blog/posts")
async def create_post(body: PostIn, request: Request, e=Depends(EDITOR)):
    d = body.model_dump()
    d["slug"] = await unique_slug(slugify(body.slug or body.title))
    d["content_html"] = sanitize_html(d["content_html"])
    d["tags"] = await upsert_tags(body.tags)
    doc = {"id": uid(), **d, "status": "draft", "created_by": e["id"], "created_at": now(), "updated_at": now(), "published_at": None}
    await db.blog_posts.insert_one(doc)
    await audit(e["id"], "blog.created", doc["id"], request=request)
    return {"id": doc["id"], "slug": doc["slug"]}


@router.put("/admin/blog/posts/{pid}")
async def update_post(pid: str, body: PostIn, request: Request, e=Depends(EDITOR)):
    p = await db.blog_posts.find_one({"id": pid})
    if not p:
        raise HTTPException(404, "Post not found.")
    d = body.model_dump()
    new_slug = slugify(body.slug or p["slug"])
    if new_slug != p["slug"]:
        new_slug = await unique_slug(new_slug, pid)
        if p.get("published_at"):
            await db.blog_redirects.update_one({"from_slug": p["slug"]}, {"$set": {"to_slug": new_slug, "created_at": now()}}, upsert=True)
        await db.blog_redirects.delete_many({"from_slug": new_slug})
    d["slug"] = new_slug
    d["content_html"] = sanitize_html(d["content_html"])
    d["tags"] = await upsert_tags(body.tags)
    await db.blog_revisions.insert_one({"id": uid(), "post_id": pid, "title": p["title"], "content_html": p.get("content_html", ""),
                                        "by": e["id"], "created_at": now()})
    await db.blog_posts.update_one({"id": pid}, {"$set": {**d, "updated_at": now()}, "$unset": {"autosave": ""}})
    await audit(e["id"], "blog.updated", pid, request=request)
    return {"ok": True, "slug": new_slug}


class AutosaveIn(BaseModel):
    title: str = ""
    content_html: str = ""


@router.post("/admin/blog/posts/{pid}/autosave")
async def autosave(pid: str, body: AutosaveIn, e=Depends(EDITOR)):
    await db.blog_posts.update_one({"id": pid}, {"$set": {"autosave": {"title": body.title, "content_html": sanitize_html(body.content_html), "at": now()}}})
    return {"ok": True, "at": now()}


class StatusIn(BaseModel):
    action: str
    publish_at: Optional[str] = None


@router.post("/admin/blog/posts/{pid}/status")
async def post_status(pid: str, body: StatusIn, request: Request, e=Depends(EDITOR)):
    p = await db.blog_posts.find_one({"id": pid})
    if not p:
        raise HTTPException(404, "Post not found.")
    upd = {"updated_at": now()}
    if body.action == "publish":
        upd.update({"status": "published", "published_at": p.get("published_at") or now(), "ai_generated": False, "approved_by": e["id"]})
    elif body.action == "schedule":
        if not body.publish_at:
            raise HTTPException(422, "Choose a publish date and time.")
        at = datetime.fromisoformat(body.publish_at.replace("Z", "+00:00"))
        if at.tzinfo is None:
            raise HTTPException(422, "Publish time must include a timezone.")
        upd.update({"status": "scheduled", "publish_at": at, "approved_by": e["id"]})
    elif body.action in ("unpublish", "draft"):
        upd.update({"status": "draft"})
    elif body.action == "archive":
        upd.update({"status": "archived"})
    else:
        raise HTTPException(422, "Unknown action.")
    await db.blog_posts.update_one({"id": pid}, {"$set": upd})
    await audit(e["id"], f"blog.{body.action}", pid, request=request)
    return {"ok": True}


@router.post("/admin/blog/posts/{pid}/duplicate")
async def duplicate(pid: str, e=Depends(EDITOR)):
    p = await db.blog_posts.find_one({"id": pid}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Post not found.")
    p.update({"id": uid(), "title": p["title"] + " (copy)", "slug": await unique_slug(p["slug"] + "-copy"), "status": "draft",
              "published_at": None, "publish_at": None, "created_at": now(), "updated_at": now(), "created_by": e["id"]})
    await db.blog_posts.insert_one(p)
    return {"id": p["id"]}


@router.delete("/admin/blog/posts/{pid}")
async def delete_post(pid: str, request: Request, e=Depends(EDITOR)):
    await db.blog_posts.delete_one({"id": pid})
    await audit(e["id"], "blog.deleted", pid, request=request)
    return {"ok": True}


@router.post("/admin/blog/images")
async def upload_blog_image(file: UploadFile = File(...), e=Depends(EDITOR)):
    data = await file.read(5 * 1024 * 1024 + 1)
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(413, "Image must be under 5 MB.")
    kind = "image/png" if data[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg" if data[:3] == b"\xff\xd8\xff" else "image/webp" if data[8:12] == b"WEBP" else None
    if not kind:
        raise HTTPException(415, "Upload a JPG, PNG or WEBP image.")
    iid = uid()
    res = await asyncio.to_thread(put_object, f"{BUCKET_PREFIX}/blog/{iid}", data, kind)
    await db.media_assets.insert_one({"id": iid, "kind": "blog_image", "storage_path": res["path"], "content_type": kind, "is_deleted": False,
                                      "user_id": e["id"], "created_at": now()})
    return {"id": iid, "url": f"/api/blog/images/{iid}"}


class TaxIn(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    bio: str = ""


@router.post("/admin/blog/taxonomy/{kind}")
async def add_tax(kind: str, body: TaxIn, e=Depends(EDITOR)):
    coll = {"categories": db.blog_categories, "authors": db.blog_authors}.get(kind)
    if coll is None:
        raise HTTPException(404, "Unknown type.")
    s = slugify(body.name)
    if await coll.find_one({"slug": s}):
        raise HTTPException(409, "Already exists.")
    await coll.insert_one({"id": uid(), "name": body.name, "slug": s, "bio": body.bio, "sort": 99})
    return {"slug": s}


@router.get("/admin/blog/redirects")
async def redirects(e=Depends(EDITOR)):
    return await db.blog_redirects.find({}, {"_id": 0}).to_list(500)


class RedirectIn(BaseModel):
    from_slug: str
    to_slug: str


@router.post("/admin/blog/redirects")
async def add_redirect(body: RedirectIn, e=Depends(EDITOR)):
    await db.blog_redirects.update_one({"from_slug": slugify(body.from_slug)}, {"$set": {"to_slug": slugify(body.to_slug), "created_at": now()}}, upsert=True)
    return {"ok": True}


@router.delete("/admin/blog/redirects/{from_slug}")
async def del_redirect(from_slug: str, e=Depends(EDITOR)):
    await db.blog_redirects.delete_one({"from_slug": from_slug})
    return {"ok": True}


class AIIn(BaseModel):
    action: str
    topic: str = Field("", max_length=300)
    content: str = Field("", max_length=20000)


AI_TASKS = {
    "outline": "Write a clear H2/H3 outline (HTML <h2>,<h3>,<ul>) for a cricket blog article on: {topic}",
    "draft": "Write a helpful, accurate ~700-word cricket blog article draft in clean HTML (<h2>,<p>,<ul>) on: {topic}. No fabricated statistics, studies or quotes.",
    "grammar": "Fix grammar and clarity in this HTML, keep structure and meaning. Return HTML only:\n{content}",
    "seo": "Write an SEO title (<=60 chars) and meta description (<=155 chars) for this article. Return as 'TITLE: ...\\nDESCRIPTION: ...'\n{content}",
    "faq": "Write 4 FAQ Q&As based only on this article, as HTML <h3>question</h3><p>answer</p>:\n{content}",
    "social": "Write 3 short social media captions (no fake claims) for this article:\n{content}",
}


@router.post("/admin/blog/ai")
async def blog_ai(body: AIIn, e=Depends(EDITOR)):
    if not (await get_settings())["flags"]["blog_ai"]:
        raise HTTPException(403, "AI writing assistant is disabled.")
    if body.action not in AI_TASKS:
        raise HTTPException(422, "Unknown action.")
    try:
        out = await llm_text("You are a careful cricket content editor. Output only what is asked, no preamble.",
                             AI_TASKS[body.action].format(topic=body.topic, content=body.content[:15000]), f"blog-{uid()}")
    except Exception:
        raise HTTPException(502, "The AI assistant is unavailable right now.")
    return {"result": re.sub(r"^```(html)?|```$", "", out.strip()).strip(), "note": "AI-generated — saved only as draft until an editor publishes."}


async def publish_due():
    await db.blog_posts.update_many({"status": "scheduled", "publish_at": {"$lte": now()}},
                                    [{"$set": {"status": "published", "published_at": {"$ifNull": ["$published_at", "$publish_at"]}}}])


# ---------- SEO ----------
class PageMetaIn(BaseModel):
    path: str
    title: str = Field("", max_length=70)
    description: str = Field("", max_length=170)
    noindex: bool = False


@router.get("/seo/pages")
async def page_meta():
    return await db.seo_pages.find({}, {"_id": 0}).to_list(100)


@router.put("/admin/seo/pages")
async def save_page_meta(body: PageMetaIn, request: Request, a=Depends(ADMIN)):
    if body.path not in PUBLIC_PATHS:
        raise HTTPException(422, "Only public pages can have editable metadata.")
    await db.seo_pages.update_one({"path": body.path}, {"$set": body.model_dump()}, upsert=True)
    await audit(a["id"], "seo.page_meta", body.path, request=request)
    return {"ok": True}


@router.get("/sitemap.xml")
async def sitemap():
    urls = [(p, None) for p in PUBLIC_PATHS if not await db.seo_pages.find_one({"path": p, "noindex": True})]
    posts = await db.blog_posts.find({**live_q(), "noindex": {"$ne": True}}, {"slug": 1, "updated_at": 1}).to_list(5000)
    urls += [(f"/blog/{p['slug']}", p["updated_at"]) for p in posts]
    used = await db.blog_posts.distinct("categories", live_q())
    urls += [(f"/blog/category/{c}", None) for c in used]
    body = "".join(f"<url><loc>{SITE}{u}</loc>{f'<lastmod>{d.date().isoformat()}</lastmod>' if d else ''}</url>" for u, d in urls)
    return Response(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>', media_type="application/xml")


@router.get("/admin/seo/checks")
async def seo_checks(a=Depends(EDITOR)):
    posts = await db.blog_posts.find({}, {"_id": 0, "id": 1, "title": 1, "slug": 1, "status": 1, "seo_title": 1, "seo_description": 1, "excerpt": 1,
                                         "content_html": 1, "featured_image_id": 1, "featured_image_alt": 1, "noindex": 1, "canonical_url": 1}).to_list(5000)
    live_slugs = {p["slug"] for p in posts if p["status"] == "published"}
    redirect_from = {r["from_slug"] for r in await db.blog_redirects.find().to_list(1000)}
    issues = []
    for p in posts:
        if p["status"] != "published":
            continue
        if not p.get("seo_title"):
            issues.append({"post": p["title"], "issue": "Missing SEO title (falls back to post title)", "severity": "low"})
        if not (p.get("seo_description") or p.get("excerpt")):
            issues.append({"post": p["title"], "issue": "Missing meta description and excerpt", "severity": "high"})
        if p.get("featured_image_id") and not p.get("featured_image_alt"):
            issues.append({"post": p["title"], "issue": "Featured image has no alt text", "severity": "medium"})
        if p.get("noindex"):
            issues.append({"post": p["title"], "issue": "Published but set to noindex", "severity": "info"})
        if p.get("canonical_url") and not p["canonical_url"].startswith(SITE):
            issues.append({"post": p["title"], "issue": "Canonical points to another domain", "severity": "medium"})
        for link in re.findall(r'href="(?:https://cricanalyze\.in)?/blog/([a-z0-9-]+)"', p.get("content_html", "")):
            if link not in live_slugs and link not in redirect_from and link not in ("category", "tag", "author"):
                issues.append({"post": p["title"], "issue": f"Broken internal link to /blog/{link}", "severity": "high"})
    pages = {x["path"]: x for x in await db.seo_pages.find({}, {"_id": 0}).to_list(100)}
    return {"issues": issues, "published_posts": len(live_slugs), "drafts": sum(p["status"] == "draft" for p in posts),
            "sitemap_url": f"{APP_URL}/api/sitemap.xml", "pages": [{"path": p, **pages.get(p, {})} for p in PUBLIC_PATHS],
            "guidance": ["Validate structured data with Google's Rich Results Test after deployment.",
                         "Submit https://cricanalyze.in/sitemap.xml in Google Search Console once the domain is verified.",
                         "Use PageSpeed Insights for Core Web Vitals on the live domain."]}
