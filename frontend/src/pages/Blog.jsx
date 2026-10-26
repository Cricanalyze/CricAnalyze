import { useEffect, useState } from "react";
import { Link, useParams, useNavigate, useSearchParams } from "react-router-dom";
import { api, fmtDate, media, SITE } from "@/lib/api";
import { Seo, Badge, Card } from "@/components/Common";
import { Button } from "@/components/ui/button";

export const PostCard = ({ p }) => (
  <Link to={`/blog/${p.slug}`} className="group glass rounded-xl overflow-hidden block hover:border-[#00B4D8]/40 transition-colors" data-testid={`post-card-${p.slug}`}>
    {p.featured_image_url ? <img src={media(p.featured_image_url)} alt={p.featured_image_alt || ""} className="h-44 w-full object-cover" loading="lazy" /> : <div className="h-44 bg-gradient-to-br from-[#1C2541] to-[#0B132B]" />}
    <div className="p-5"><div className="text-xs text-slate-500 mb-2">{fmtDate(p.published_at || p.publish_at)}</div>
      <h3 className="font-semibold text-lg group-hover:text-[#00B4D8] transition-colors">{p.title}</h3>
      <p className="text-sm text-slate-400 mt-2 line-clamp-2">{p.excerpt}</p></div>
  </Link>
);

export const BlogList = ({ kind }) => {
  const { slug } = useParams();
  const [sp, setSp] = useSearchParams();
  const page = Number(sp.get("page") || 1);
  const [data, setData] = useState({ posts: [], pages: 0 });
  const [meta, setMeta] = useState({ categories: [], tags: [], authors: [] });
  useEffect(() => { api.get("/blog/meta").then(({ data }) => setMeta(data)).catch(() => {}); }, []);
  useEffect(() => {
    const params = { page, limit: 9 };
    if (kind) params[kind] = slug;
    api.get("/blog/posts", { params }).then(({ data }) => setData(data)).catch(() => {});
  }, [kind, slug, page]);
  const label = kind === "category" ? meta.categories.find((c) => c.slug === slug)?.name : kind === "author" ? meta.authors.find((a) => a.slug === slug)?.name : kind === "tag" ? `#${slug}` : null;
  const path = kind ? `/blog/${kind}/${slug}` : "/blog";
  return (
    <section className="max-w-7xl mx-auto px-4 sm:px-6 py-16">
      <Seo title={label ? `${label} — Blog` : "Cricket Coaching Blog"} path={page > 1 ? `${path}?page=${page}` : path} description="Batting and bowling technique, drills, youth development and cricket technology articles." />
      <nav aria-label="Breadcrumb" className="text-xs text-slate-500 mb-4"><Link to="/">Home</Link> / <Link to="/blog">Blog</Link>{label && ` / ${label}`}</nav>
      <h1 className="text-4xl sm:text-5xl font-extrabold mb-8">{label || "The CricAnalyze Blog"}</h1>
      <div className="flex flex-wrap gap-2 mb-10">{meta.categories.map((c) => <Link key={c.slug} to={`/blog/category/${c.slug}`} data-testid={`blog-cat-${c.slug}`}
        className={`text-xs px-3 py-1.5 rounded-full border ${slug === c.slug ? "border-[#10B981] text-white" : "border-white/10 text-slate-400 hover:text-white"}`}>{c.name}</Link>)}</div>
      {data.posts.length === 0 ? <Card data-testid="blog-empty">No published articles here yet.</Card> :
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">{data.posts.map((p) => <PostCard key={p.id} p={p} />)}</div>}
      {data.pages > 1 && <div className="flex gap-2 mt-10">{Array.from({ length: data.pages }, (_, i) => <Button key={i} size="sm" variant={page === i + 1 ? "default" : "secondary"} onClick={() => setSp({ page: i + 1 })} data-testid={`blog-page-${i + 1}`}>{i + 1}</Button>)}</div>}
    </section>
  );
};

export const BlogPost = () => {
  const { slug } = useParams();
  const [sp] = useSearchParams();
  const nav = useNavigate();
  const [p, setP] = useState(null);
  const [err, setErr] = useState(false);
  useEffect(() => {
    setP(null); setErr(false);
    api.get(`/blog/posts/${slug}`, { params: sp.get("preview") ? { preview: 1 } : {} }).then(({ data }) => {
      if (data.redirect) nav(`/blog/${data.redirect}`, { replace: true }); else setP(data);
    }).catch(() => setErr(true));
  }, [slug, sp, nav]);
  if (err) return <section className="max-w-3xl mx-auto px-4 py-24 text-center"><Seo title="Article not found" path={`/blog/${slug}`} noindex /><h1 className="text-3xl font-bold">Article not found</h1><Link to="/blog" className="text-[#00B4D8] mt-4 inline-block">Back to blog</Link></section>;
  if (!p) return <div className="py-24 text-center text-slate-400">Loading…</div>;
  const url = `${SITE}/blog/${p.slug}`;
  const ld = [{ "@context": "https://schema.org", "@type": "BlogPosting", headline: p.seo_title || p.title, description: p.seo_description || p.excerpt, datePublished: p.published_at, dateModified: p.updated_at,
    author: { "@type": "Person", name: p.author?.name || "CricAnalyze Team" }, publisher: { "@type": "Organization", name: "CricAnalyze" }, mainEntityOfPage: url, image: p.featured_image_url ? media(p.featured_image_url) : undefined },
    { "@context": "https://schema.org", "@type": "BreadcrumbList", itemListElement: [{ "@type": "ListItem", position: 1, name: "Home", item: SITE }, { "@type": "ListItem", position: 2, name: "Blog", item: `${SITE}/blog` }, { "@type": "ListItem", position: 3, name: p.title, item: url }] }];
  return (
    <article className="max-w-3xl mx-auto px-4 sm:px-6 py-16" data-testid="blog-article">
      <Seo title={p.seo_title || p.title} description={p.seo_description || p.excerpt} path={`/blog/${p.slug}`} type="article" noindex={p.noindex || p.status !== "published" && !p.publish_at} image={p.featured_image_url && media(p.featured_image_url)} jsonLd={ld} />
      {sp.get("preview") && <Badge tone="amber">PREVIEW — {p.status}</Badge>}
      <nav aria-label="Breadcrumb" className="text-xs text-slate-500 my-4"><Link to="/">Home</Link> / <Link to="/blog">Blog</Link> / <span>{p.title}</span></nav>
      <h1 className="text-4xl sm:text-5xl font-extrabold leading-tight">{p.title}</h1>
      <div className="text-sm text-slate-400 mt-4 flex flex-wrap gap-3">
        {p.author && <Link to={`/blog/author/${p.author.slug}`} className="hover:text-white">{p.author.name}</Link>}<span>{fmtDate(p.published_at)}</span>
        {p.updated_at && <span>Updated {fmtDate(p.updated_at)}</span>}</div>
      {p.featured_image_url && <figure className="my-8"><img src={media(p.featured_image_url)} alt={p.featured_image_alt || ""} className="rounded-2xl w-full" />{p.featured_image_alt && <figcaption className="text-xs text-slate-500 mt-2">{p.featured_image_alt}</figcaption>}</figure>}
      <div className="prose-blog mt-8" dangerouslySetInnerHTML={{ __html: p.content_html }} />
      <div className="flex flex-wrap gap-2 mt-10">{(p.categories || []).map((c) => <Link key={c} to={`/blog/category/${c}`}><Badge tone="teal">{c}</Badge></Link>)}{(p.tags || []).map((t) => <Link key={t} to={`/blog/tag/${t}`}><Badge>#{t}</Badge></Link>)}</div>
      {p.related?.length > 0 && <div className="mt-16"><h2 className="text-xl font-bold mb-5">Related articles</h2><div className="grid sm:grid-cols-3 gap-4">{p.related.map((r) => <PostCard key={r.id} p={r} />)}</div></div>}
    </article>
  );
};

export const SharedPassport = () => {
  const { token } = useParams();
  const [p, setP] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => { api.get(`/public/passport/${token}`).then(({ data }) => setP(data)).catch((e) => setErr(e?.response?.data?.detail || "Unavailable")); }, [token]);
  return (
    <section className="max-w-3xl mx-auto px-4 py-16"><Seo title="Player Development Passport" path="/passport" noindex />
      {err ? <Card data-testid="passport-error">{err}</Card> : !p ? "Loading…" : <PassportView p={p} />}</section>
  );
};

export const PassportView = ({ p }) => (
  <div className="space-y-5" data-testid="passport-view">
    <Card><div className="eyebrow">Player development passport</div><h1 className="text-3xl font-bold mt-2">{p.name}</h1>
      <p className="text-slate-400 text-sm mt-1">{[p.playing_role, p.batting_style, p.bowling_style].filter(Boolean).join(" · ") || "Profile details not added"}</p>
      <div className="grid grid-cols-3 gap-3 mt-5 text-center">{[["Analyses", p.analysis_count], ["Batting", p.batting_count], ["Bowling", p.bowling_count]].map(([l, v]) => <div key={l} className="bg-white/5 rounded-lg p-3"><div className="text-2xl font-bold">{v}</div><div className="text-xs text-slate-400">{l}</div></div>)}</div></Card>
    <div className="grid md:grid-cols-2 gap-5">
      <Card><h3 className="font-semibold mb-2">Demonstrated strengths</h3>{p.strengths.length ? <ul className="text-sm text-slate-300 list-disc pl-5 space-y-1">{p.strengths.map((s) => <li key={s}>{s}</li>)}</ul> : <p className="text-sm text-slate-500">No reports yet.</p>}</Card>
      <Card><h3 className="font-semibold mb-2">Development priorities</h3>{p.priorities.length ? <ul className="text-sm text-slate-300 list-disc pl-5 space-y-1">{p.priorities.map((s) => <li key={s}>{s}</li>)}</ul> : <p className="text-sm text-slate-500">No reports yet.</p>}</Card>
    </div>
    <Card><h3 className="font-semibold mb-2">Milestones & completed plans</h3><div className="flex flex-wrap gap-2">{[...p.milestones, ...p.completed_plans].map((m) => <Badge key={m} tone="green">{m}</Badge>)}{!p.milestones.length && !p.completed_plans.length && <span className="text-sm text-slate-500">None yet.</span>}</div></Card>
    {p.coach_feedback?.length > 0 && <Card><h3 className="font-semibold mb-2">Coach feedback</h3>{p.coach_feedback.map((f) => <p key={f.id} className="text-sm text-slate-300 mb-2"><b>{f.coach_name}</b> · {fmtDate(f.created_at)}: {f.text}</p>)}</Card>}
    <Card><h3 className="font-semibold mb-2">Verified analysis history</h3>{p.history.map((h, i) => <div key={i} className="text-sm border-b border-white/5 py-2"><Badge tone="teal">{h.type}</Badge> <span className="text-slate-400">{h.date}</span><p className="text-slate-300 mt-1">{h.summary}</p></div>)}</Card>
    <p className="text-xs text-slate-500">{p.disclaimer}</p>
  </div>
);
