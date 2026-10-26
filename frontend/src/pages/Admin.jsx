import { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { api, errMsg, fmtDate, inr } from "@/lib/api";
import { PageHeader, Card, Badge, statusTone, Seo } from "@/components/Common";

const useLoad = (path, params) => {
  const [d, setD] = useState(null);
  const key = JSON.stringify(params || {});
  const load = useCallback(() => api.get(path, { params: JSON.parse(key) }).then(({ data }) => setD(data)).catch((e) => toast.error(errMsg(e))), [path, key]);
  useEffect(() => { load(); }, [load]);
  return [d, load];
};
const T = ({ head, rows, testid }) => (
  <div className="overflow-x-auto glass rounded-xl" data-testid={testid}><table className="w-full text-sm min-w-[700px]"><thead><tr className="text-left text-slate-400">{head.map((h) => <th key={h} className="p-3 font-medium">{h}</th>)}</tr></thead>
    <tbody>{rows.map((r, i) => <tr key={i} className="border-t border-white/5">{r.map((c, j) => <td key={j} className="p-3 align-top">{c}</td>)}</tr>)}</tbody></table>{!rows.length && <p className="p-4 text-slate-500 text-sm">Nothing here yet.</p>}</div>
);

const Overview = () => {
  const [d] = useLoad("/admin/analytics");
  if (!d) return "Loading…";
  return (<div className="space-y-6">
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">{[["Users", d.users], ["Verified", d.verified_users], ["Active subscriptions", d.active_subscriptions], ["Revenue (paid)", inr(d.revenue_inr)],
      ["Analyses (30d)", d.analyses_30d], ["Failed (30d)", d.failed_30d], ["Est. AI cost (30d)", inr(d.est_ai_cost_30d_inr)], ["Open tickets", d.open_tickets]].map(([l, v]) => <Card key={l}><div className="text-xs text-slate-400">{l}</div><div className="text-2xl font-bold mt-1" data-testid={`stat-${l.toLowerCase().replace(/[^a-z]+/g, "-")}`}>{v}</div></Card>)}</div>
    {d.cost_alert && <Card className="border-amber-500/40 text-amber-300" data-testid="cost-alert">Estimated AI cost has reached the configured monthly alert threshold.</Card>}
    <Card><h3 className="font-semibold mb-3">Last 14 days</h3><div className="h-64"><ResponsiveContainer><BarChart data={d.daily}><CartesianGrid stroke="#1e293b" /><XAxis dataKey="date" stroke="#64748b" fontSize={11} /><YAxis stroke="#64748b" fontSize={11} allowDecimals={false} /><Tooltip contentStyle={{ background: "#1C2541", border: "none" }} /><Bar dataKey="signups" fill="#00B4D8" /><Bar dataKey="analyses" fill="#10B981" /></BarChart></ResponsiveContainer></div></Card>
  </div>);
};

const Users = () => {
  const [q, setQ] = useState("");
  const [d, load] = useLoad("/admin/users", { q });
  const [plans] = useLoad("/admin/plans");
  const [grant, setGrant] = useState(null);
  const upd = async (id, body) => { if (!window.confirm("Confirm this change?")) return; try { await api.patch(`/admin/users/${id}`, { ...body, confirm: true }); toast.success("Updated."); load(); } catch (e) { toast.error(errMsg(e)); } };
  return (<div>
    <Input placeholder="Search name or email" value={q} onChange={(e) => setQ(e.target.value)} className="max-w-sm mb-4" data-testid="admin-user-search" />
    {d && <T testid="admin-users-table" head={["Name", "Email", "Role", "Status", "Joined", ""]} rows={d.users.map((u) => [u.full_name, <span className="text-xs">{u.email}{!u.email_verified && <Badge tone="amber">unverified</Badge>}</span>,
      <Select value={u.role} onValueChange={(v) => upd(u.id, { role: v })}><SelectTrigger className="h-8 w-40" data-testid={`role-select-${u.id}`}><SelectValue /></SelectTrigger><SelectContent>{d.roles.map((r) => <SelectItem key={r} value={r}>{r}</SelectItem>)}</SelectContent></Select>,
      <Badge tone={u.status === "suspended" ? "red" : "green"}>{u.status}</Badge>, fmtDate(u.created_at),
      <div className="flex gap-1"><Button size="sm" variant="ghost" onClick={() => upd(u.id, { status: u.status === "suspended" ? "active" : "suspended" })} data-testid={`suspend-${u.id}`}>{u.status === "suspended" ? "Reactivate" : "Suspend"}</Button>
        <Button size="sm" variant="ghost" onClick={() => setGrant({ user_id: u.id, name: u.full_name, plan_id: "", reason: "" })} data-testid={`grant-${u.id}`}>Grant credits</Button></div>])} />}
    <Dialog open={!!grant} onOpenChange={() => setGrant(null)}><DialogContent><DialogHeader><DialogTitle>Grant plan to {grant?.name}</DialogTitle></DialogHeader>
      {grant && <div className="space-y-3"><Select value={grant.plan_id} onValueChange={(v) => setGrant({ ...grant, plan_id: v })}><SelectTrigger data-testid="grant-plan-select"><SelectValue placeholder="Plan" /></SelectTrigger><SelectContent>{(plans || []).map((p) => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}</SelectContent></Select>
        <Input type="number" placeholder="Credits (default: plan credits)" onChange={(e) => setGrant({ ...grant, credits: e.target.value ? +e.target.value : null })} data-testid="grant-credits" />
        <Input placeholder="Reason (audited)" value={grant.reason} onChange={(e) => setGrant({ ...grant, reason: e.target.value })} data-testid="grant-reason" />
        <Button onClick={async () => { try { await api.post("/admin/grant", grant); toast.success("Granted."); setGrant(null); } catch (e) { toast.error(errMsg(e)); } }} disabled={!grant.plan_id || grant.reason.length < 3} data-testid="grant-submit">Grant</Button></div>}</DialogContent></Dialog>
  </div>);
};

const PLAN_BLANK = { name: "", slug: "", product: "batting", billing: "monthly", price_inr: 499, currency: "INR", period_days: 30, credits: 5, videos_per_analysis: 1, max_duration_s: 30, max_file_mb: 100, analysis_types: ["batting"],
  report_level: "detailed", pdf_export: true, history_access: true, comparisons: true, timeline: true, multi_angle: false, ai_coach: true, training_planner: true, academy_features: false, active: true, sort: 10, description: "", valid_until: null };
const Plans = () => {
  const [d, load] = useLoad("/admin/plans");
  const [ed, setEd] = useState(null);
  const save = async () => { try { const { id, created_at, updated_at, placeholder_price, ...body } = ed; if (id) await api.put(`/admin/plans/${id}`, body); else await api.post("/admin/plans", body); toast.success("Plan saved."); setEd(null); load(); } catch (e) { toast.error(errMsg(e)); } };
  const num = ["price_inr", "period_days", "credits", "videos_per_analysis", "max_duration_s", "max_file_mb", "sort"];
  const bools = ["pdf_export", "history_access", "comparisons", "timeline", "multi_angle", "ai_coach", "training_planner", "academy_features", "active"];
  return (<div><Button className="mb-4" onClick={() => setEd({ ...PLAN_BLANK })} data-testid="new-plan-btn">New plan</Button>
    {d && <T testid="admin-plans-table" head={["Plan", "Price", "Credits", "Limits", "Types", "Status", ""]} rows={d.map((p) => [<span>{p.name}{p.placeholder_price && <Badge tone="amber">placeholder price</Badge>}</span>, `${inr(p.price_inr)} / ${p.period_days}d`, p.credits,
      `${p.videos_per_analysis} vid · ${p.max_duration_s}s · ${p.max_file_mb}MB`, p.analysis_types.join(", "), <Badge tone={p.active ? "green" : "slate"}>{p.active ? "active" : "hidden"}</Badge>, <Button size="sm" variant="ghost" onClick={() => setEd({ ...p })} data-testid={`edit-plan-${p.slug}`}>Edit</Button>])} />}
    <Dialog open={!!ed} onOpenChange={() => setEd(null)}><DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto"><DialogHeader><DialogTitle>{ed?.id ? "Edit plan" : "New plan"}</DialogTitle></DialogHeader>
      {ed && <div className="grid sm:grid-cols-2 gap-3 text-sm">
        {["name", "slug", "description"].map((k) => <label key={k} className="space-y-1"><span className="text-slate-400">{k}</span><Input value={ed[k]} onChange={(e) => setEd({ ...ed, [k]: e.target.value })} data-testid={`plan-${k}`} /></label>)}
        <label className="space-y-1"><span className="text-slate-400">billing</span><Select value={ed.billing} onValueChange={(v) => setEd({ ...ed, billing: v })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{["monthly", "quarterly", "annual", "one_time", "promo"].map((x) => <SelectItem key={x} value={x}>{x}</SelectItem>)}</SelectContent></Select></label>
        <label className="space-y-1"><span className="text-slate-400">product</span><Select value={ed.product} onValueChange={(v) => setEd({ ...ed, product: v, analysis_types: v === "combined" ? ["batting", "bowling"] : [v] })}><SelectTrigger data-testid="plan-product"><SelectValue /></SelectTrigger><SelectContent>{["batting", "bowling", "combined"].map((x) => <SelectItem key={x} value={x}>{x}</SelectItem>)}</SelectContent></Select></label>
        <label className="space-y-1"><span className="text-slate-400">report_level</span><Select value={ed.report_level} onValueChange={(v) => setEd({ ...ed, report_level: v })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{["basic", "detailed", "advanced"].map((x) => <SelectItem key={x} value={x}>{x}</SelectItem>)}</SelectContent></Select></label>
        {num.map((k) => <label key={k} className="space-y-1"><span className="text-slate-400">{k}</span><Input type="number" value={ed[k]} onChange={(e) => setEd({ ...ed, [k]: +e.target.value })} data-testid={`plan-${k}`} /></label>)}
        <label className="space-y-1"><span className="text-slate-400">promo valid until</span><Input type="date" value={ed.valid_until || ""} onChange={(e) => setEd({ ...ed, valid_until: e.target.value || null })} /></label>
        <div className="sm:col-span-2 grid grid-cols-2 gap-2">{bools.map((k) => <label key={k} className="flex justify-between items-center bg-white/5 rounded-md px-3 py-2">{k}<Switch checked={!!ed[k]} onCheckedChange={(v) => setEd({ ...ed, [k]: v })} data-testid={`plan-${k}`} /></label>)}</div>
        <Button className="sm:col-span-2" onClick={save} data-testid="plan-save-btn">Save plan</Button></div>}</DialogContent></Dialog>
  </div>);
};

const Coupons = () => {
  const [d, load] = useLoad("/admin/coupons");
  const [f, setF] = useState({ code: "", kind: "percent", value: 10, max_uses: 100, expires_at: "" });
  return (<div><Card className="flex flex-wrap gap-2 items-end mb-4"><Input placeholder="CODE" className="w-36" value={f.code} onChange={(e) => setF({ ...f, code: e.target.value.toUpperCase() })} data-testid="coupon-code" />
    <Select value={f.kind} onValueChange={(v) => setF({ ...f, kind: v })}><SelectTrigger className="w-32"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="percent">% off</SelectItem><SelectItem value="flat">₹ off</SelectItem></SelectContent></Select>
    <Input type="number" className="w-24" value={f.value} onChange={(e) => setF({ ...f, value: +e.target.value })} data-testid="coupon-value" /><Input type="number" className="w-28" value={f.max_uses} onChange={(e) => setF({ ...f, max_uses: +e.target.value })} aria-label="Max uses" />
    <Input type="date" className="w-40" value={f.expires_at} onChange={(e) => setF({ ...f, expires_at: e.target.value })} aria-label="Expiry" />
    <Button onClick={async () => { try { await api.post("/admin/coupons", { ...f, expires_at: f.expires_at || null }); load(); toast.success("Coupon saved."); } catch (e) { toast.error(errMsg(e)); } }} data-testid="coupon-save-btn">Save coupon</Button></Card>
    {d && <T head={["Code", "Discount", "Uses", "Expires", "Active"]} rows={d.map((c) => [c.code, c.kind === "percent" ? `${c.value}%` : inr(c.value), `${c.uses}/${c.max_uses}`, c.expires_at || "—", c.active ? "yes" : "no"])} />}</div>);
};

const Payments = () => {
  const [d, load] = useLoad("/admin/payments");
  const [l] = useLoad("/admin/ledger");
  return (<div className="space-y-6">{d && <T testid="admin-payments-table" head={["User", "Plan", "Amount", "Status", "Razorpay ID", "Date", ""]} rows={d.map((p) => [p.user_id.slice(0, 8), p.plan_name, inr(p.amount_inr), <Badge tone={statusTone(p.status)}>{p.status}</Badge>, <span className="font-mono text-xs">{p.payment_id || p.order_id}</span>, fmtDate(p.created_at),
    p.status === "paid" && <Button size="sm" variant="ghost" onClick={async () => { if (!window.confirm("Refund this payment in full via Razorpay? Credits will be revoked.")) return; try { await api.post(`/admin/payments/${p.id}/refund`, { confirm: true }); toast.success("Refund requested."); load(); } catch (e) { toast.error(errMsg(e)); } }} data-testid={`refund-${p.id}`}>Refund</Button>])} />}
    <h3 className="font-semibold">Credit ledger</h3>{l && <T head={["Date", "User", "Change", "Reason", "Ref"]} rows={l.slice(0, 100).map((x) => [fmtDate(x.created_at), x.user_id.slice(0, 8), x.delta, x.reason, <span className="font-mono text-xs">{(x.ref || "").slice(0, 10)}</span>])} />}</div>);
};

const Jobs = () => {
  const [d, load] = useLoad("/admin/jobs");
  return d ? (<div><div className="flex gap-2 mb-4">{Object.entries(d.counts).map(([k, v]) => <Badge key={k} tone={statusTone(k)}>{k}: {v}</Badge>)}<Button size="sm" variant="ghost" onClick={load}>Refresh</Button></div>
    <T testid="admin-jobs-table" head={["Job", "Type", "Status", "Attempts", "Created", "Reason", ""]} rows={d.jobs.map((j) => [<a className="font-mono text-xs text-[#00B4D8]" href={`/app/analyses/${j.id}`}>{j.id.slice(0, 8)}</a>, j.analysis_type, <Badge tone={statusTone(j.status)}>{j.status}</Badge>, j.attempts, fmtDate(j.created_at),
      <span className="text-xs text-slate-400">{j.failure_reason || j.last_error || ""}</span>, j.status === "failed" && <Button size="sm" variant="ghost" onClick={async () => { await api.post(`/admin/jobs/${j.id}/retry`); load(); }} data-testid={`admin-retry-${j.id}`}>Retry</Button>])} /></div>) : "Loading…";
};

const Integrations = () => {
  const [d, load] = useLoad("/admin/integrations");
  const [logs, loadLogs] = useLoad("/admin/email-logs");
  const [to, setTo] = useState("");
  const [busy, setBusy] = useState(null);
  const test = async (k) => { setBusy(k); try { const { data } = await api.post(`/admin/integrations/${k}/test`, k === "smtp" && to ? { to } : {}); toast[data.ok ? "success" : "error"](data.message); load(); loadLogs(); } catch (e) { toast.error(errMsg(e)); } finally { setBusy(null); } };
  return (<div className="space-y-6"><div className="grid md:grid-cols-2 gap-4">{(d || []).map((i) => <Card key={i.key} data-testid={`integration-${i.key}`}>
    <div className="flex justify-between"><h3 className="font-semibold">{i.name}</h3><Badge tone={i.configured ? "green" : "red"}>{i.configured ? "configured" : "missing"}</Badge></div>
    <div className="text-xs text-slate-400 mt-2 space-y-0.5">{Object.entries(i.info).filter(([, v]) => v).map(([k, v]) => <div key={k}>{k}: {String(v)}</div>)}
      {i.last_test && <div>Last test {fmtDate(i.last_test)}: <span className={i.last_result === "pass" ? "text-[#10B981]" : "text-red-300"}>{i.last_result}</span> — {i.last_message}</div>}{i.last_success && <div>Last success: {fmtDate(i.last_success)}</div>}</div>
    {["smtp", "ai", "storage", "razorpay"].includes(i.key) && <div className="flex gap-2 mt-3">{i.key === "smtp" && <Input placeholder="Send test to (default: you)" value={to} onChange={(e) => setTo(e.target.value)} className="h-8 text-xs" data-testid="smtp-test-to" />}
      <Button size="sm" variant="secondary" onClick={() => test(i.key)} disabled={busy === i.key} data-testid={`test-${i.key}-btn`}>{busy === i.key ? "Testing…" : i.key === "smtp" ? "Send test email" : "Test connection"}</Button></div>}</Card>)}</div>
    <p className="text-xs text-slate-500">Secret values are never shown. Update keys via the platform's secure secrets panel. "Accepted" means the SMTP server took the message; inbox delivery isn't confirmed by SMTP.</p>
    <h3 className="font-semibold">Email delivery log</h3>{logs && <T testid="email-logs-table" head={["Time", "To", "Template", "Status", "Error"]} rows={logs.map((l) => [fmtDate(l.created_at), l.to, l.template, <Badge tone={l.status === "accepted" ? "green" : l.status === "failed" ? "red" : "amber"}>{l.status}</Badge>, <span className="text-xs text-slate-400">{l.error || ""}</span>])} />}</div>);
};

const SettingsTab = () => {
  const [d, setD] = useLoad("/admin/settings");
  const [s, setS] = useState(null);
  useEffect(() => { if (d) setS(d); }, [d]);
  if (!s) return "Loading…";
  const save = async () => { if (!window.confirm("Apply these platform settings?")) return; try { await api.put("/admin/settings", { ...s, confirm: true }); toast.success("Settings saved."); setD(); } catch (e) { toast.error(errMsg(e)); } };
  return (<div className="grid lg:grid-cols-2 gap-6"><Card><h3 className="font-semibold mb-3">Feature flags</h3>{Object.entries(s.flags).map(([k, v]) => <label key={k} className="flex justify-between py-2 text-sm">{k.replace(/_/g, " ")}<Switch checked={v} onCheckedChange={(x) => setS({ ...s, flags: { ...s.flags, [k]: x } })} data-testid={`flag-${k}`} /></label>)}</Card>
    <Card><h3 className="font-semibold mb-3">Limits & cost controls</h3>{Object.entries(s.limits).map(([k, v]) => <label key={k} className="flex justify-between items-center py-1.5 text-sm gap-3">{k.replace(/_/g, " ")}<Input type="number" className="w-28 h-8" value={v} onChange={(e) => setS({ ...s, limits: { ...s.limits, [k]: +e.target.value } })} data-testid={`limit-${k}`} /></label>)}</Card>
    <Button onClick={save} className="lg:col-span-2 justify-self-start" data-testid="settings-apply-btn">Save settings</Button></div>);
};

const SeoTab = () => {
  const [d, load] = useLoad("/admin/seo/checks");
  const [ed, setEd] = useState(null);
  if (!d) return "Loading…";
  return (<div className="space-y-6"><div className="grid grid-cols-3 gap-4"><Card><div className="text-xs text-slate-400">Published posts</div><div className="text-2xl font-bold">{d.published_posts}</div></Card><Card><div className="text-xs text-slate-400">Drafts (not indexed)</div><div className="text-2xl font-bold">{d.drafts}</div></Card>
    <Card><div className="text-xs text-slate-400">Sitemap</div><a href={d.sitemap_url} target="_blank" rel="noreferrer" className="text-sm text-[#00B4D8] break-all" data-testid="sitemap-link">sitemap.xml</a></Card></div>
    <h3 className="font-semibold">Issues</h3><T testid="seo-issues" head={["Post", "Issue", "Severity"]} rows={d.issues.map((i) => [i.post, i.issue, <Badge tone={{ high: "red", medium: "amber" }[i.severity] || "slate"}>{i.severity}</Badge>])} />
    <h3 className="font-semibold">Public page metadata</h3><T testid="seo-pages" head={["Path", "Title", "Description", "Noindex", ""]} rows={d.pages.map((p) => [p.path, p.title || <span className="text-slate-500">default</span>, <span className="text-xs">{p.description || "default"}</span>, p.noindex ? "yes" : "no",
      <Button size="sm" variant="ghost" onClick={() => setEd({ path: p.path, title: p.title || "", description: p.description || "", noindex: !!p.noindex })} data-testid={`seo-edit-${p.path}`}>Edit</Button>])} />
    <Card><h3 className="font-semibold mb-2">Guidance</h3><ul className="text-sm text-slate-400 list-disc pl-5">{d.guidance.map((g) => <li key={g}>{g}</li>)}</ul></Card>
    <Dialog open={!!ed} onOpenChange={() => setEd(null)}><DialogContent><DialogHeader><DialogTitle>Metadata for {ed?.path}</DialogTitle></DialogHeader>{ed && <div className="space-y-3">
      <Input placeholder="Title (≤70)" maxLength={70} value={ed.title} onChange={(e) => setEd({ ...ed, title: e.target.value })} data-testid="seo-title-input" /><Input placeholder="Description (≤170)" maxLength={170} value={ed.description} onChange={(e) => setEd({ ...ed, description: e.target.value })} data-testid="seo-desc-input" />
      <label className="flex justify-between text-sm">Noindex<Switch checked={ed.noindex} onCheckedChange={(v) => setEd({ ...ed, noindex: v })} /></label>
      <Button onClick={async () => { try { await api.put("/admin/seo/pages", ed); setEd(null); load(); toast.success("Saved."); } catch (e) { toast.error(errMsg(e)); } }} data-testid="seo-save-btn">Save</Button></div>}</DialogContent></Dialog></div>);
};

const Support = () => {
  const [d, load] = useLoad("/admin/support");
  return d ? <T testid="support-table" head={["Date", "From", "Subject", "Message", "Status"]} rows={d.map((t) => [fmtDate(t.created_at), <span className="text-xs">{t.name}<br />{t.email}</span>, t.subject, <span className="text-xs text-slate-400">{t.message}</span>,
    <Select value={t.status} onValueChange={async (v) => { await api.patch(`/admin/support/${t.id}`, { status: v }); load(); }}><SelectTrigger className="h-8 w-28"><SelectValue /></SelectTrigger><SelectContent>{["open", "pending", "closed"].map((x) => <SelectItem key={x} value={x}>{x}</SelectItem>)}</SelectContent></Select>])} /> : "Loading…";
};
const Audit = () => { const [d] = useLoad("/admin/audit"); return d ? <T testid="audit-table" head={["Time", "Actor", "Action", "Target", "IP"]} rows={d.map((a) => [new Date(a.created_at).toLocaleString("en-IN"), (a.actor_id || "").slice(0, 8), a.action, (a.target || "").slice(0, 12), a.ip || ""])} /> : "Loading…"; };
const Academies = () => { const [d] = useLoad("/admin/academies"); return d ? <T head={["Name", "City", "Members", "Created"]} rows={d.map((a) => [a.name, a.city, a.members, fmtDate(a.created_at)])} /> : "Loading…"; };

const TABS = [["overview", "Overview", Overview], ["users", "Users & roles", Users], ["plans", "Plans", Plans], ["coupons", "Coupons", Coupons], ["payments", "Payments & credits", Payments], ["jobs", "Analysis jobs", Jobs],
  ["integrations", "Integrations & email", Integrations], ["settings", "Flags & limits", SettingsTab], ["seo", "SEO", SeoTab], ["academies", "Academies", Academies], ["support", "Support", Support], ["audit", "Audit log", Audit]];

export default function Admin() {
  return (<div><Seo title="Admin" path="/admin" noindex /><PageHeader eyebrow="Admin control center" title="Platform administration" desc="Sensitive changes require confirmation and are written to the audit log." />
    <Tabs defaultValue="overview"><TabsList className="flex-wrap h-auto">{TABS.map(([v, l]) => <TabsTrigger key={v} value={v} data-testid={`admin-tab-${v}`}>{l}</TabsTrigger>)}</TabsList>
      {TABS.map(([v, , C]) => <TabsContent key={v} value={v} className="mt-6"><C /></TabsContent>)}</Tabs></div>);
}
