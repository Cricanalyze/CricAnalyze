import { Link } from "react-router-dom";
import { Helmet } from "react-helmet-async";
import { useEffect, useState } from "react";
import { api, SITE } from "@/lib/api";

export const Logo = ({ className = "" }) => (
  <Link to="/" className={`inline-flex items-center rounded-lg bg-white px-2 py-1 w-fit ${className}`} data-testid="brand-logo" aria-label="CricAnalyze home">
    <img src="/logo.png" alt="CricAnalyze - Analyze, Improve, Play Better" className="h-10 w-auto" />
  </Link>
);

let metaCache = null;
const usePageMeta = (path) => {
  const [m, setM] = useState(metaCache?.[path]);
  useEffect(() => {
    if (metaCache) { setM(metaCache[path]); return; }
    api.get("/seo/pages").then(({ data }) => {
      metaCache = Object.fromEntries(data.map((x) => [x.path, x]));
      setM(metaCache[path]);
    }).catch(() => {});
  }, [path]);
  return m;
};

export const Seo = ({ title, description, path = "/", noindex, image, jsonLd, type = "website" }) => {
  const o = usePageMeta(path);
  const t = (o?.title || title) + (title?.includes("CricAnalyze") ? "" : " | CricAnalyze");
  const d = o?.description || description;
  const url = `${SITE}${path}`;
  const ld = Array.isArray(jsonLd) ? jsonLd : jsonLd ? [jsonLd] : [];
  return (
    <Helmet>
      <title>{t}</title>
      {d && <meta name="description" content={d} />}
      {(noindex || o?.noindex) && <meta name="robots" content="noindex,nofollow" />}
      <link rel="canonical" href={url} />
      <meta property="og:title" content={t} />
      {d && <meta property="og:description" content={d} />}
      <meta property="og:url" content={url} />
      <meta property="og:type" content={type} />
      <meta property="og:image" content={image || `${SITE}/images/hero.jpg`} />
      <meta name="twitter:card" content="summary_large_image" />
      {ld.map((j, i) => <script key={i} type="application/ld+json">{JSON.stringify(j)}</script>)}
    </Helmet>
  );
};

export const PageHeader = ({ eyebrow, title, desc, children }) => (
  <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 mb-8">
    <div>
      {eyebrow && <div className="eyebrow mb-2">{eyebrow}</div>}
      <h1 className="text-2xl sm:text-3xl font-bold" data-testid="page-title">{title}</h1>
      {desc && <p className="text-slate-400 mt-2 max-w-2xl text-sm sm:text-base">{desc}</p>}
    </div>
    {children && <div className="flex gap-2 flex-wrap">{children}</div>}
  </div>
);

export const Empty = ({ icon: Icon, title, desc, action, testid = "empty-state" }) => (
  <div className="glass rounded-xl p-10 text-center" data-testid={testid}>
    {Icon && <Icon className="mx-auto mb-3 text-[#00B4D8]" size={32} />}
    <h3 className="font-semibold text-lg">{title}</h3>
    {desc && <p className="text-slate-400 text-sm mt-1 max-w-md mx-auto">{desc}</p>}
    {action && <div className="mt-5">{action}</div>}
  </div>
);

export const Card = ({ className = "", children, ...p }) => <div className={`glass rounded-xl p-5 ${className}`} {...p}>{children}</div>;

export const Badge = ({ tone = "slate", children, ...p }) => {
  const tones = { slate: "bg-slate-700/50 text-slate-200", teal: "bg-[#00B4D8]/15 text-[#5fd7ef]", green: "bg-[#10B981]/15 text-[#34d399]",
    amber: "bg-amber-500/15 text-amber-300", red: "bg-red-500/15 text-red-300" };
  return <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium ${tones[tone]}`} {...p}>{children}</span>;
};

export const statusTone = (s) => ({ completed: "green", paid: "green", active: "green", published: "green", processing: "teal", queued: "amber",
  scheduled: "amber", created: "amber", failed: "red", refunded: "red", expired: "slate", archived: "slate", draft: "slate" }[s] || "slate");
