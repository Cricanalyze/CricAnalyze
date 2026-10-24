import { useEffect, useRef, useState, useCallback } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { UploadCloud, Video, FileDown, RefreshCw, Trash2, AlertTriangle, History, Sparkles, MessageSquare } from "lucide-react";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api, errMsg, fmtDate, media, download } from "@/lib/api";
import { useAuth, isStaff } from "@/context/AuthContext";
import { PageHeader, Empty, Card, Badge, statusTone, Seo } from "@/components/Common";

export const Dashboard = () => {
  const { user, ent } = useAuth();
  const [jobs, setJobs] = useState(null);
  useEffect(() => { api.get("/analyses").then(({ data }) => setJobs(data)).catch(() => setJobs([])); }, []);
  const done = (jobs || []).filter((j) => j.status === "completed");
  return (
    <div><Seo title="Dashboard" path="/app" noindex />
      <PageHeader eyebrow="Dashboard" title={`Hi ${user.full_name.split(" ")[0]}`} desc="Your analyses, credits and next steps.">
        <Button asChild className="bg-[#10B981] hover:bg-[#059669] text-[#0B132B]" data-testid="dash-new-analysis-btn"><Link to="/app/upload"><UploadCloud size={16} className="mr-1" />New analysis</Link></Button></PageHeader>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {[["Credits left", isStaff(user) ? "Staff" : ent?.credits ?? 0, "dash-credits"], ["Completed analyses", done.length, "dash-completed"], ["Batting", done.filter((j) => j.analysis_type === "batting").length, "dash-batting"], ["Bowling", done.filter((j) => j.analysis_type === "bowling").length, "dash-bowling"]]
          .map(([l, v, t]) => <Card key={l}><div className="text-xs text-slate-400">{l}</div><div className="text-3xl font-display font-bold mt-1" data-testid={t}>{v}</div></Card>)}
      </div>
      {!isStaff(user) && !ent?.subscriptions && <Card className="mb-8 border-[#10B981]/30" data-testid="dash-no-plan"><div className="flex flex-col sm:flex-row justify-between gap-3 sm:items-center"><div><h3 className="font-semibold">No active plan</h3><p className="text-sm text-slate-400">Choose a batting, bowling or all-rounder plan to start analysing videos.</p></div><Button asChild><Link to="/app/billing">View plans</Link></Button></div></Card>}
      <h2 className="text-lg font-semibold mb-4">Recent analyses</h2>
      {jobs === null ? <p className="text-slate-400">Loading…</p> : jobs.length === 0 ? <Empty icon={Video} title="No analyses yet" desc="Upload your first batting or bowling video. Your first report becomes your baseline." action={<Button asChild><Link to="/app/upload">Upload a video</Link></Button>} /> :
        <JobList jobs={jobs.slice(0, 6)} />}
    </div>
  );
};

export const JobList = ({ jobs }) => (
  <div className="glass rounded-xl divide-y divide-white/5" data-testid="job-list">
    {jobs.map((j) => <Link key={j.id} to={`/app/analyses/${j.id}`} className="flex items-center justify-between gap-3 p-4 hover:bg-white/5 transition-colors" data-testid={`job-row-${j.id}`}>
      <div className="min-w-0"><div className="flex gap-2 items-center"><Badge tone="teal">{j.analysis_type}</Badge><span className="text-sm text-slate-400">{fmtDate(j.created_at)}</span>{j.video_ids.length > 1 && <Badge>{j.video_ids.length} angles</Badge>}</div>
        <p className="text-sm text-slate-300 mt-1 truncate">{j.report?.summary || j.failure_reason || "Processing…"}</p></div>
      <Badge tone={statusTone(j.status)}>{j.status}</Badge></Link>)}
  </div>
);

const ANGLES = [["side_on", "Side-on"], ["front_on", "Front-on"], ["behind", "From behind"], ["other", "Other"]];

const ConsentGate = ({ status, reload }) => {
  const { refresh } = useAuth();
  const [dob, setDob] = useState("");
  const [g, setG] = useState({ guardian_name: "", guardian_email: "" });
  const [sent, setSent] = useState(false);
  const [code, setCode] = useState("");
  if (status.needs_dob) return <Card className="mb-6" data-testid="dob-gate"><h3 className="font-semibold">Your date of birth</h3><p className="text-sm text-slate-400 mb-3">We ask this only to apply guardian consent for players under 18.</p>
    <div className="flex gap-2"><Input type="date" value={dob} onChange={(e) => setDob(e.target.value)} className="max-w-xs" data-testid="dob-input" /><Button onClick={async () => { await api.patch("/account/profile", { profile: { dob } }); await refresh(); reload(); }} disabled={!dob} data-testid="dob-save-btn">Save</Button></div></Card>;
  if (status.is_minor && !status.guardian_consent) return <Card className="mb-6 border-amber-500/30" data-testid="guardian-gate"><h3 className="font-semibold">Guardian consent needed</h3>
    <p className="text-sm text-slate-400 mb-3">Players under 18 need a parent or guardian to approve video analysis. We'll email them a code.</p>
    {!sent ? <div className="grid sm:grid-cols-3 gap-2"><Input placeholder="Guardian name" value={g.guardian_name} onChange={(e) => setG({ ...g, guardian_name: e.target.value })} data-testid="guardian-name-input" />
      <Input type="email" placeholder="Guardian email" value={g.guardian_email} onChange={(e) => setG({ ...g, guardian_email: e.target.value })} data-testid="guardian-email-input" />
      <Button onClick={async () => { try { await api.post("/account/guardian/request", g); setSent(true); toast.success("Code sent to guardian."); } catch (e) { toast.error(errMsg(e)); } }} data-testid="guardian-send-btn">Send code</Button></div> :
      <div className="flex gap-2"><Input placeholder="6-digit code from guardian" value={code} onChange={(e) => setCode(e.target.value)} maxLength={6} className="max-w-xs" data-testid="guardian-code-input" />
        <Button onClick={async () => { try { await api.post("/account/guardian/confirm", { code }); toast.success("Guardian consent recorded."); reload(); } catch (e) { toast.error(errMsg(e)); } }} data-testid="guardian-confirm-btn">Confirm</Button></div>}</Card>;
  return null;
};

export const Upload = () => {
  const { user, ent } = useAuth();
  const nav = useNavigate();
  const [status, setStatus] = useState(null);
  const [type, setType] = useState("batting");
  const [items, setItems] = useState([]);
  const [consent, setConsent] = useState(false);
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [drag, setDrag] = useState(false);
  const key = useRef(crypto.randomUUID());
  const loadStatus = useCallback(() => api.get("/account/status").then(({ data }) => setStatus(data)), []);
  useEffect(() => { loadStatus(); }, [loadStatus]);
  const staff = isStaff(user);
  const maxVideos = staff ? 3 : ent?.videos_per_analysis || 1;
  const allowed = staff ? ["batting", "bowling"] : ent?.analysis_types || [];
  const add = (files) => {
    const f = [...files].filter((x) => x.type.startsWith("video/") || /\.(mp4|mov|webm)$/i.test(x.name));
    if (!f.length) return toast.error("Please choose an MP4, MOV or WEBM video.");
    const next = [...items, ...f.map((file, i) => ({ file, url: URL.createObjectURL(file), angle: ANGLES[(items.length + i) % 3][0], progress: 0 }))].slice(0, maxVideos);
    if (items.length + f.length > maxVideos) toast.info(`Your plan allows ${maxVideos} video(s) per analysis.`);
    setItems(next);
  };
  const start = async () => {
    setBusy(true);
    try {
      const ids = [];
      for (let i = 0; i < items.length; i++) {
        const fd = new FormData();
        fd.append("file", items[i].file); fd.append("analysis_type", type); fd.append("angle", items[i].angle);
        const { data } = await api.post("/videos", fd, { onUploadProgress: (e) => setItems((s) => s.map((x, j) => j === i ? { ...x, progress: Math.round((e.loaded / (e.total || 1)) * 100) } : x)) });
        ids.push(data.id);
      }
      const { data: job } = await api.post("/analyses", { analysis_type: type, video_ids: ids, consent, idempotency_key: key.current, notes: notes || null });
      toast.success("Upload complete. Analysis queued.");
      nav(`/app/analyses/${job.id}`);
    } catch (e) {
      const d = e?.response?.data?.detail;
      if (d === "guardian_consent_required") { toast.error("Guardian consent is required first."); loadStatus(); } else toast.error(errMsg(e));
      key.current = crypto.randomUUID();
    } finally { setBusy(false); }
  };
  if (!status) return <p className="text-slate-400">Loading…</p>;
  return (
    <div><Seo title="New analysis" path="/app/upload" noindex />
      <PageHeader eyebrow="New analysis" title="Upload a cricket video" desc={`Up to ${staff ? 3 : maxVideos} video(s), ${ent?.max_duration_s || 30}s each, ${ent?.max_file_mb || 100} MB max. MP4, MOV or WEBM.`} />
      <ConsentGate status={status} reload={loadStatus} />
      {!staff && allowed.length === 0 ? <Empty title="No active plan" desc="Choose a plan to start analysing videos." action={<Button asChild><Link to="/app/billing">View plans</Link></Button>} testid="upload-no-plan" /> :
      <div className="grid lg:grid-cols-5 gap-6">
        <div className="lg:col-span-3 space-y-4">
          <div className="flex gap-2">{["batting", "bowling"].map((t) => <button key={t} disabled={!allowed.includes(t)} onClick={() => setType(t)} data-testid={`type-${t}-btn`}
            className={`flex-1 py-3 rounded-lg border capitalize transition-colors disabled:opacity-40 ${type === t ? "border-[#10B981] bg-[#10B981]/10" : "border-white/10 hover:border-white/30"}`}>{t}</button>)}</div>
          <label onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)} onDrop={(e) => { e.preventDefault(); setDrag(false); add(e.dataTransfer.files); }}
            className={`block border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-colors ${drag ? "border-[#10B981] bg-[#10B981]/5" : "border-white/15 hover:border-[#00B4D8]/50"}`} data-testid="dropzone">
            <UploadCloud className="mx-auto text-[#00B4D8] mb-3" size={36} /><p className="font-medium">Drag & drop video{maxVideos > 1 ? "s" : ""} here or click to browse</p>
            <p className="text-xs text-slate-500 mt-1">{items.length}/{maxVideos} selected</p>
            <input type="file" accept="video/mp4,video/quicktime,video/webm" multiple={maxVideos > 1} className="hidden" onChange={(e) => { add(e.target.files); e.target.value = ""; }} data-testid="video-file-input" disabled={items.length >= maxVideos} />
          </label>
          {items.map((it, i) => <Card key={it.url} className="flex flex-col sm:flex-row gap-4" data-testid={`video-item-${i}`}>
            <video src={it.url} controls className="sm:w-56 rounded-lg bg-black aspect-video" />
            <div className="flex-1 space-y-3"><p className="text-sm truncate">{it.file.name} · {(it.file.size / 1048576).toFixed(1)} MB</p>
              <Select value={it.angle} onValueChange={(v) => setItems(items.map((x, j) => j === i ? { ...x, angle: v } : x))}><SelectTrigger data-testid={`angle-select-${i}`}><SelectValue /></SelectTrigger>
                <SelectContent>{ANGLES.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}</SelectContent></Select>
              {busy && <Progress value={it.progress} />}
              <Button size="sm" variant="ghost" onClick={() => setItems(items.filter((_, j) => j !== i))} disabled={busy} data-testid={`remove-video-${i}`}><Trash2 size={14} className="mr-1" />Remove</Button></div></Card>)}
        </div>
        <div className="lg:col-span-2 space-y-4">
          <Card><h3 className="font-semibold mb-2">Camera placement tips</h3><ul className="text-sm text-slate-400 space-y-1.5 list-disc pl-5">
            <li>Side-on: camera level with the hips, 8–12 m away, full body in frame.</li><li>Front-on: behind the bowler's arm / straight down the pitch.</li>
            <li>Steady phone, good light, 30fps or higher, 480p+.</li><li>For multi-angle bowling, record the same delivery or similar deliveries per angle.</li></ul></Card>
          <Textarea placeholder="Optional note for the analyst (e.g. 'working on my cover drive')" maxLength={300} value={notes} onChange={(e) => setNotes(e.target.value)} data-testid="analysis-notes" />
          <label className="flex gap-2 items-start text-sm"><Checkbox checked={consent} onCheckedChange={(v) => setConsent(!!v)} data-testid="consent-checkbox" />
            <span>I own this video or have permission from everyone in it, and I consent to it being processed by a hosted AI provider to create my report.</span></label>
          <Button className="w-full bg-[#10B981] hover:bg-[#059669] text-[#0B132B]" disabled={!items.length || !consent || busy} onClick={start} data-testid="start-analysis-btn">
            {busy ? "Uploading…" : staff ? "Start analysis (staff, no credit)" : "Start analysis · uses 1 credit"}</Button>
          <p className="text-xs text-slate-500">Credits are refunded automatically if the analysis fails.</p>
        </div>
      </div>}
    </div>
  );
};

export const Analyses = () => {
  const [type, setType] = useState("all");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [jobs, setJobs] = useState(null);
  useEffect(() => {
    const params = {}; if (type !== "all") params.type = type; if (from) params.date_from = from; if (to) params.date_to = to;
    api.get("/analyses", { params }).then(({ data }) => setJobs(data)).catch(() => setJobs([]));
  }, [type, from, to]);
  return (
    <div><Seo title="Analyses" path="/app/analyses" noindex />
      <PageHeader eyebrow="History" title="Analyses & progress" />
      <Tabs defaultValue="history">
        <TabsList><TabsTrigger value="history" data-testid="tab-history">History</TabsTrigger><TabsTrigger value="timeline" data-testid="tab-timeline">Timeline</TabsTrigger><TabsTrigger value="compare" data-testid="tab-compare">Compare</TabsTrigger></TabsList>
        <TabsContent value="history" className="mt-6">
          <div className="flex flex-wrap gap-2 mb-4"><Select value={type} onValueChange={setType}><SelectTrigger className="w-40" data-testid="history-type-filter"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">All types</SelectItem><SelectItem value="batting">Batting</SelectItem><SelectItem value="bowling">Bowling</SelectItem></SelectContent></Select>
            <Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="w-44" aria-label="From date" data-testid="history-from" /><Input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="w-44" aria-label="To date" data-testid="history-to" /></div>
          {jobs === null ? "Loading…" : jobs.length ? <JobList jobs={jobs} /> : <Empty icon={History} title="No analyses match" />}
        </TabsContent>
        <TabsContent value="timeline" className="mt-6"><Timeline /></TabsContent>
        <TabsContent value="compare" className="mt-6"><Compare /></TabsContent>
      </Tabs>
    </div>
  );
};

const Timeline = () => {
  const [type, setType] = useState("batting");
  const [d, setD] = useState(null);
  const [err, setErr] = useState(null);
  const [area, setArea] = useState("avg");
  useEffect(() => { setErr(null); api.get("/timeline", { params: { type } }).then(({ data }) => setD(data)).catch((e) => setErr(errMsg(e))); }, [type]);
  const areas = d ? [...new Set(d.reports.flatMap((r) => Object.keys(r.scores || {})))] : [];
  const rows = (d?.reports || []).map((r) => {
    const vals = Object.values(r.scores || {}).map((s) => s?.rating).filter((x) => typeof x === "number");
    return { date: fmtDate(r.created_at), value: area === "avg" ? (vals.length ? +(vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(2) : null) : r.scores?.[area]?.rating ?? null };
  });
  return (<div>
    <div className="flex gap-2 mb-4"><Select value={type} onValueChange={setType}><SelectTrigger className="w-40" data-testid="timeline-type"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="batting">Batting</SelectItem><SelectItem value="bowling">Bowling</SelectItem></SelectContent></Select>
      <Select value={area} onValueChange={setArea}><SelectTrigger className="w-56" data-testid="timeline-area"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="avg">Average of assessable areas</SelectItem>{areas.map((a) => <SelectItem key={a} value={a}>{a.replace(/_/g, " ")}</SelectItem>)}</SelectContent></Select></div>
    {err ? <Empty title="Timeline unavailable" desc={err} testid="timeline-locked" /> : !d ? "Loading…" : d.reports.length === 0 ? <Empty title="No reports yet" desc="Your first completed analysis will become your baseline." testid="timeline-empty" /> :
      <Card><p className="text-xs text-slate-400 mb-3">{d.baseline ? "Baseline only — add another analysis to see change over time." : "AI visual ratings (1–5). Gaps mean the area wasn't assessable."}</p>
        <div className="h-72" data-testid="timeline-chart"><ResponsiveContainer><LineChart data={rows}><CartesianGrid stroke="#1e293b" /><XAxis dataKey="date" stroke="#64748b" fontSize={12} /><YAxis domain={[0, 5]} stroke="#64748b" fontSize={12} /><Tooltip contentStyle={{ background: "#1C2541", border: "none" }} /><Line dataKey="value" stroke="#10B981" strokeWidth={2} connectNulls={false} dot /></LineChart></ResponsiveContainer></div></Card>}
  </div>);
};

const Compare = () => {
  const [sp] = useSearchParams();
  const [jobs, setJobs] = useState([]);
  const [a, setA] = useState(sp.get("a") || "");
  const [b, setB] = useState("");
  const [res, setRes] = useState(null);
  useEffect(() => { api.get("/analyses").then(({ data }) => setJobs(data.filter((j) => j.status === "completed"))).catch(() => {}); }, []);
  const run = async () => { try { setRes((await api.get("/compare", { params: { a, b } })).data); } catch (e) { toast.error(errMsg(e)); } };
  const typeA = jobs.find((j) => j.id === a)?.analysis_type;
  const opt = (list) => list.map((j) => <SelectItem key={j.id} value={j.id}>{j.analysis_type} · {fmtDate(j.created_at)}</SelectItem>);
  if (jobs.length < 2) return <Empty title="Need two completed reports" desc="Compare becomes available once you have two analyses of the same type." testid="compare-empty" />;
  return (<div>
    <div className="flex flex-wrap gap-2 mb-6"><Select value={a} onValueChange={(v) => { setA(v); setB(""); }}><SelectTrigger className="w-64" data-testid="compare-a"><SelectValue placeholder="Before report" /></SelectTrigger><SelectContent>{opt(jobs)}</SelectContent></Select>
      <Select value={b} onValueChange={setB}><SelectTrigger className="w-64" data-testid="compare-b"><SelectValue placeholder="After report" /></SelectTrigger><SelectContent>{opt(jobs.filter((j) => j.id !== a && j.analysis_type === typeA))}</SelectContent></Select>
      <Button onClick={run} disabled={!a || !b} data-testid="compare-run-btn">Compare</Button></div>
    {res && <Card data-testid="compare-result"><p className="text-xs text-slate-400 mb-4">{res.note}</p>
      <div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr className="text-left text-slate-400"><th className="py-2">Area</th><th>Before ({fmtDate(res.before.report.created_at)})</th><th>After ({fmtDate(res.after.report.created_at)})</th><th>Change</th></tr></thead>
        <tbody>{res.areas.map((r) => <tr key={r.area} className="border-t border-white/5"><td className="py-2 capitalize">{r.area.replace(/_/g, " ")}</td>
          <td>{r.before?.rating ?? <span className="text-slate-500">Unavailable</span>}</td><td>{r.after?.rating ?? <span className="text-slate-500">Unavailable</span>}</td>
          <td>{r.change === null ? <span className="text-slate-500">—</span> : <span className={r.change > 0 ? "text-[#10B981]" : r.change < 0 ? "text-red-400" : ""}>{r.change > 0 ? "+" : ""}{r.change}</span>}</td></tr>)}</tbody></table></div>
      <div className="grid md:grid-cols-2 gap-4 mt-6"><div><h4 className="font-semibold text-sm mb-1">Before summary</h4><p className="text-sm text-slate-400">{res.before.report.summary}</p></div><div><h4 className="font-semibold text-sm mb-1">After summary</h4><p className="text-sm text-slate-400">{res.after.report.summary}</p></div></div></Card>}
  </div>);
};

export const Report = () => {
  const { id } = useParams();
  const nav = useNavigate();
  const [job, setJob] = useState(null);
  const [videoUrl, setVideoUrl] = useState(null);
  const [frame, setFrame] = useState(null);
  const load = useCallback(() => api.get(`/analyses/${id}`).then(({ data }) => setJob(data)).catch(() => setJob(false)), [id]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!job || ["completed", "failed"].includes(job.status)) return;
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, [job, load]);
  useEffect(() => { if (job?.video_ids?.[0]) api.get(`/videos/${job.video_ids[0]}/url`).then(({ data }) => setVideoUrl(media(data.url))).catch(() => {}); }, [job?.video_ids]);
  if (job === false) return <Empty title="Analysis not found" testid="report-not-found" />;
  if (!job) return <p className="text-slate-400">Loading…</p>;
  const r = job.report;
  const retry = async () => { try { await api.post(`/analyses/${id}/retry`); toast.success("Retry queued."); load(); } catch (e) { toast.error(errMsg(e)); } };
  const genPlan = async () => { try { toast.info("Creating plan…"); await api.post("/training/plans/generate", { report_id: r.id }); nav("/app/training"); } catch (e) { toast.error(errMsg(e)); } };
  return (
    <div><Seo title="Report" path={`/app/analyses/${id}`} noindex />
      <PageHeader eyebrow={`${job.analysis_type} analysis · ${fmtDate(job.created_at)}`} title={r ? "Technique report" : "Analysis in progress"}>
        {r && <><Button variant="secondary" onClick={() => download(`/analyses/${id}/pdf`, `cricanalyze-${id.slice(0, 8)}.pdf`).catch((e) => toast.error(e?.response?.status === 402 ? "PDF export isn't included in your plan." : "PDF failed"))} data-testid="report-pdf-btn"><FileDown size={16} className="mr-1" />PDF</Button>
          <Button variant="secondary" onClick={genPlan} data-testid="report-plan-btn"><Sparkles size={16} className="mr-1" />Training plan</Button>
          <Button variant="secondary" asChild data-testid="report-coach-btn"><Link to="/app/coach"><MessageSquare size={16} className="mr-1" />Ask coach</Link></Button></>}
      </PageHeader>
      {!r && <Card className="mb-6" data-testid="job-status-card"><div className="flex items-center gap-3 mb-3"><Badge tone={statusTone(job.status)}>{job.status}</Badge><span className="text-sm text-slate-400">{job.stage?.replace(/_/g, " ")}</span></div>
        {job.status === "failed" ? <div><p className="text-red-300 flex gap-2 items-start"><AlertTriangle size={18} />{job.failure_reason}</p><p className="text-xs text-slate-500 mt-1">{job.credit_state === "refunded" ? "Your credit was refunded." : ""}</p><Button className="mt-4" onClick={retry} data-testid="retry-btn"><RefreshCw size={16} className="mr-1" />Retry</Button></div>
          : <><Progress value={job.progress} /><p className="text-xs text-slate-500 mt-2">Usually 1–3 minutes. You can leave this page — we'll email you when it's ready.{job.last_error ? ` Retrying after: ${job.last_error}` : ""}</p></>}</Card>}
      {r && <div className="grid lg:grid-cols-5 gap-6" data-testid="report-view">
        <div className="lg:col-span-3 space-y-5">
          {videoUrl && <video src={videoUrl} controls className="w-full rounded-xl bg-black aspect-video" data-testid="report-video" />}
          <Card><div className="flex justify-between mb-2"><h3 className="font-semibold">Summary</h3><Badge tone={{ high: "green", medium: "amber", low: "red" }[r.overall_confidence]}>confidence: {r.overall_confidence || "n/a"}</Badge></div><p className="text-slate-300 leading-relaxed" data-testid="report-summary">{r.summary}</p></Card>
          <Card><h3 className="font-semibold mb-3">Evidence frames</h3><div className="grid grid-cols-3 sm:grid-cols-4 gap-2">{r.frames.map((f) => <button key={f.index} onClick={() => setFrame(f)} className={`relative rounded-md overflow-hidden border ${frame?.index === f.index ? "border-[#10B981]" : "border-transparent"}`} data-testid={`frame-${f.index}`}>
            <img src={media(f.url)} alt={`Frame at ${f.t}s, ${f.angle}`} className="aspect-video object-cover w-full" /><span className="absolute bottom-0 left-0 text-[10px] font-mono bg-black/70 px-1">#{f.index} · {f.t}s</span></button>)}</div>
            {frame && <img src={media(frame.url)} alt="Selected frame" className="mt-3 rounded-lg w-full" />}
            <p className="text-xs text-slate-500 mt-2">Pose keypoints: not available with the current analysis provider.</p></Card>
          <Card><h3 className="font-semibold mb-3">Observations</h3><div className="space-y-3">{(r.observations || []).map((o, i) => <div key={i} className="border-l-2 border-[#00B4D8]/40 pl-3" data-testid={`observation-${i}`}>
            <div className="flex flex-wrap gap-2 items-center text-xs"><span className="font-semibold capitalize text-sm">{o.area?.replace(/_/g, " ")}</span><Badge tone={o.evidence_type === "observed" ? "teal" : "amber"}>{o.evidence_type}</Badge><Badge>{o.confidence}</Badge>
              {o.timestamp_s != null && <button className="font-mono text-[#00B4D8]" onClick={() => setFrame(r.frames.find((f) => f.index === o.image_index) || null)}>t={o.timestamp_s}s</button>}</div>
            <p className="text-sm text-slate-300 mt-1">{o.observation}</p></div>)}</div></Card>
        </div>
        <div className="lg:col-span-2 space-y-5">
          <Card><h3 className="font-semibold mb-3">Area ratings (AI visual, 1–5)</h3>{Object.entries(r.scores || {}).map(([k, s]) => <div key={k} className="mb-2.5"><div className="flex justify-between text-xs"><span className="capitalize">{k.replace(/_/g, " ")}</span><span className="text-slate-400">{s?.rating ? `${s.rating}/5 · ${s.confidence}` : "Not assessable"}</span></div>
            <div className="h-1.5 bg-white/10 rounded mt-1"><div className="h-full rounded bg-[#10B981]" style={{ width: s?.rating ? `${s.rating * 20}%` : 0 }} /></div>{s?.note && <p className="text-[11px] text-slate-500 mt-0.5">{s.note}</p>}</div>)}</Card>
          <Card><h3 className="font-semibold mb-2 text-[#10B981]">Strengths</h3><ul className="text-sm text-slate-300 list-disc pl-5 space-y-1">{(r.strengths || []).map((s) => <li key={s}>{s}</li>)}</ul>
            <h3 className="font-semibold mt-4 mb-2 text-amber-300">Areas to improve</h3><ul className="text-sm text-slate-300 list-disc pl-5 space-y-1">{(r.improvements || []).map((s) => <li key={s}>{s}</li>)}</ul></Card>
          <Card><h3 className="font-semibold mb-3">Recommended drills</h3>{(r.drills || []).map((d) => <div key={d.name} className="mb-3"><div className="font-medium text-sm">{d.name} <span className="text-xs text-slate-500">· {d.sets_reps}</span></div><p className="text-xs text-slate-400">{d.how_to}</p>{d.linked_area && <Badge tone="teal">for {d.linked_area.replace(/_/g, " ")}</Badge>}</div>)}</Card>
          {r.practice_plan && <Card><h3 className="font-semibold mb-3">Practice plan</h3>{r.practice_plan.map((p, i) => <div key={i} className="text-sm flex justify-between border-b border-white/5 py-1.5"><span>{p.day}: {p.focus}</span><span className="text-slate-500">{p.duration_min}m</span></div>)}</Card>}
          {r.per_angle?.length > 0 && <Card><h3 className="font-semibold mb-2">Per-angle visibility</h3>{r.per_angle.map((a, i) => <p key={i} className="text-sm"><Badge tone={{ good: "green", partial: "amber", poor: "red" }[a.visibility]}>{a.angle}: {a.visibility}</Badge> <span className="text-slate-400">{a.note}</span></p>)}</Card>}
          <Card><h3 className="font-semibold mb-2">Limitations & processing</h3><ul className="text-xs text-slate-400 list-disc pl-5 space-y-1">{(r.limitations || []).map((l) => <li key={l}>{l}</li>)}<li>{r.measured?.note}</li></ul>
            <div className="text-xs text-slate-500 mt-3 font-mono">{r.model}<br />{r.video_meta.map((v) => `${v.angle}: ${v.duration_s}s · ${v.fps}fps · ${v.width}×${v.height}`).join(" | ")}</div>
            {r.locked?.length > 0 && <p className="text-xs text-amber-300 mt-2" data-testid="report-locked">Upgrade to unlock: {r.locked.join(", ")}</p>}</Card>
        </div>
      </div>}
    </div>
  );
};
