import { useState } from "react";
import { CheckCircle2, Target, ArrowRight, Camera, ListChecks, TrendingUp, Dumbbell, Info, ShieldCheck } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend as RLegend } from "recharts";
import { media } from "@/lib/api";
import { Card, Badge } from "@/components/Common";
import { AnalysisViewer, Legend } from "@/components/AnalysisViewer";

const H = ({ icon: Icon, children, testid }) => <h3 className="font-semibold text-base flex items-center gap-2 mb-3" data-testid={testid}>{Icon && <Icon size={17} className="text-[#00B4D8]" />}{children}</h3>;
const VQ = { Good: "green", Fair: "amber", Poor: "red", "Not assessed": "slate" };
const PH = { detected: "green", estimated: "amber", unavailable: "slate" };

export const ReportHeader = ({ v }) => {
  const h = v.header;
  return (
    <Card className="border-l-4 border-l-[#10B981]" data-testid="report-header">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div><div className="eyebrow mb-1">CricAnalyze · {h.analysis_type} report</div>
          <div className="text-2xl font-display font-bold" data-testid="report-player-name">{h.player}</div>
          <div className="text-sm text-slate-400 mt-1" data-testid="report-date-ist">{h.date}{h.shot_type ? ` · ${h.shot_type}` : ""}{h.angles?.length ? ` · ${h.angles.join(", ")} camera` : ""}</div></div>
        <div className="flex flex-wrap gap-2"><Badge tone={VQ[h.video_quality]} data-testid="header-video-quality">Video quality: {h.video_quality}</Badge>
          <Badge tone={v.score.status === "complete" ? "green" : v.score.status === "provisional" ? "amber" : "slate"} data-testid="header-score-status">{h.score_status}</Badge></div>
      </div>
    </Card>);
};

export const Takeaways = ({ v }) => (
  <Card data-testid="takeaways"><H icon={Target}>Three key takeaways</H>
    <ol className="grid md:grid-cols-3 gap-3">{v.takeaways.map((t, i) => <li key={i} className="rounded-lg bg-white/[0.03] border border-white/5 p-3" data-testid={`takeaway-${i}`}>
      <div className="text-[11px] font-mono uppercase tracking-wider text-[#00B4D8] mb-1">{["Strongest aspect", "Top opportunity", "Next action"][i]}</div><p className="text-sm text-slate-200">{t}</p></li>)}</ol>
  </Card>);

export const ScorePanel = ({ sc, vq }) => (
  <div className="grid md:grid-cols-5 gap-4">
    <Card className="md:col-span-3" data-testid="score-card">
      <div className="text-[11px] font-mono uppercase tracking-wider text-slate-400">Overall technique score</div>
      {sc.value != null ? <div className="flex items-end gap-2 mt-1"><span className="text-6xl font-display font-extrabold" data-testid="overall-score">{sc.value}</span><span className="text-xl text-slate-400 mb-2">/100</span></div>
        : <div className="text-xl font-display font-bold text-amber-300 mt-2" data-testid="score-unavailable">Score unavailable — record a clearer video</div>}
      {sc.value != null && <div className={`text-sm font-semibold mt-1 ${sc.status === "complete" ? "text-[#10B981]" : "text-amber-300"}`} data-testid="score-label">{sc.label}</div>}
      <p className="text-sm text-slate-400 mt-2" data-testid="score-explanation">{sc.text}</p>
      {sc.tip && <p className="text-sm mt-2 flex gap-2" data-testid="score-tip"><Camera size={16} className="text-[#00B4D8] shrink-0 mt-0.5" />{sc.tip}</p>}
      {sc.evidence && <div className="mt-3 text-xs flex items-center gap-2" data-testid="score-evidence">Evidence <Badge tone={{ High: "green", Medium: "amber", Limited: "red" }[sc.evidence]}>{sc.evidence}</Badge></div>}
      {sc.components?.length > 0 && <div className="mt-4 space-y-2.5" data-testid="score-components">{sc.components.map((c) => <div key={c.name}>
        <div className="flex justify-between text-xs"><span>{c.name}</span><span className="font-mono text-slate-400">{c.score}/100 · {c.measured} of {c.of} measured</span></div>
        <div className="h-1.5 bg-white/10 rounded mt-1"><div className="h-full rounded bg-[#10B981]" style={{ width: `${c.score}%` }} /></div></div>)}</div>}
    </Card>
    <Card className="md:col-span-2" data-testid="video-quality-card">
      <div className="text-[11px] font-mono uppercase tracking-wider text-slate-400">Video quality</div>
      <div className="mt-2"><Badge tone={VQ[vq.rating]}>{vq.rating}</Badge></div>
      <p className="text-sm text-slate-300 mt-2">{vq.text}</p>
      <p className="text-xs text-slate-500 mt-3">This rates the footage, not the player. It affects how many measurements can be taken, not the technique score itself.</p>
    </Card>
  </div>);

const MetricBars = ({ mets }) => !mets.length ? null : (
  <Card data-testid="metric-bars"><H>Measurements</H>
    <div className="space-y-4">{mets.map((m) => <div key={m.key} data-testid={`metric-${m.key}`}>
      <div className="flex flex-wrap justify-between gap-2 text-sm"><span className="font-medium">{m.name}</span><span className="font-mono text-[#5fd7ef]" data-testid={`metric-value-${m.key}`}>{m.display}</span></div>
      <div className="relative h-2 bg-white/10 rounded mt-1.5" aria-label={`${m.name}: ${m.display}`}><div className="absolute inset-y-0 left-0 rounded bg-[#00B4D8]/60" style={{ width: `${m.position * 100}%` }} />
        <div className="absolute -top-1 w-4 h-4 rounded-full bg-white border-2 border-[#0B132B]" style={{ left: `calc(${m.position * 100}% - 8px)` }} /></div>
      <div className="flex justify-between text-[10px] text-slate-500 font-mono mt-0.5"><span>{m.scale[0]}</span><span>{m.scale[1]}</span></div>
      <p className="text-xs text-slate-400 mt-0.5">{m.interpretation}{m.t != null ? ` (${m.t}s)` : ""}</p></div>)}</div>
    <p className="text-[11px] text-slate-500 mt-4">Target ranges aren't shown until coach-approved references are available.</p>
  </Card>);

const Crop = ({ src, crop, size, alt, zoom }) => {
  if (!zoom || !crop || !size) return <img src={src} alt={alt} className="w-full aspect-video object-contain bg-black rounded-md" />;
  const [x0, y0, x1, y1] = crop, cw = x1 - x0, ch = y1 - y0;
  return (
    <div className="relative w-full overflow-hidden rounded-md bg-black" style={{ aspectRatio: `${cw * size[0]} / ${ch * size[1]}`, maxHeight: 260 }}>
      <img src={src} alt={alt} className="absolute max-w-none" style={{ width: `${100 / cw}%`, height: `${100 / ch}%`, left: `${(-x0 / cw) * 100}%`, top: `${(-y0 / ch) * 100}%` }} /></div>);
};

const PhaseTimeline = ({ tl }) => {
  const [annot, setAnnot] = useState(true);
  const [zoom, setZoom] = useState(true);
  if (!tl.length) return null;
  const src = (p) => media(annot ? p.ball_overlay_url || p.overlay_url || p.frame_url : p.frame_url);
  return (
    <Card data-testid="phase-timeline"><div className="flex flex-wrap justify-between gap-2 mb-3"><H>Technique timeline</H>
      <div className="flex gap-4 text-xs"><label className="flex gap-1.5 items-center"><input type="checkbox" checked={annot} onChange={(e) => setAnnot(e.target.checked)} data-testid="overlay-toggle" />Body outline</label>
        <label className="flex gap-1.5 items-center"><input type="checkbox" checked={zoom} onChange={(e) => setZoom(e.target.checked)} data-testid="zoom-toggle" />Zoom on player</label></div></div>
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">{tl.map((p, i) => <div key={p.key} data-testid={`phase-${p.key}`}>
        <div className="text-[10px] font-mono text-slate-500 mb-1">{i + 1} · {p.name}</div>
        {p.frame_url && p.status !== "unavailable" ? <Crop src={src(p)} crop={p.crop} size={p.frame_size} zoom={zoom} alt={`${p.name} at ${p.t}s`} />
          : <div className="rounded-md w-full aspect-video bg-white/5 grid place-items-center text-xs text-slate-500 p-2 text-center">Not assessed reliably</div>}
        <div className="flex flex-wrap gap-1 items-center mt-1.5"><Badge tone={PH[p.status]}>{p.status_label}</Badge>{p.t != null && <span className="text-[11px] font-mono text-slate-400">{p.t}s · frame {p.frame_index}</span>}</div>
        <p className="text-[11px] text-slate-400 mt-1">{p.note}</p>
        {p.metrics.map((m) => <p key={m} className="text-[11px] text-[#5fd7ef] font-mono">{m}</p>)}
        {p.overlay_note && <p className="text-[11px] text-amber-300/80 mt-0.5">{p.overlay_note}</p>}</div>)}</div>
      <div className="mt-3"><Legend /></div></Card>);
};

const AngleSection = ({ a, raw }) => (
  <div className="space-y-4" data-testid={`angle-${a.angle}`}>
    {a.angle && <div className="eyebrow">{a.angle} camera</div>}
    {a.analysed_window && <p className="text-xs text-slate-400" data-testid="analysed-window">{a.analysed_window}</p>}
    {!a.pose_available && <Card data-testid="pose-unavailable"><p className="text-sm text-slate-300">Body tracking wasn't available for this clip, so only the coach's visual notes are shown.</p></Card>}
    <MetricBars mets={a.metrics} />
    <PhaseTimeline tl={a.timeline} />
    {raw?.video_url && a.pose_available && <AnalysisViewer b={raw} />}
    {a.ball && <p className="text-xs text-slate-400 px-1" data-testid="ball-note">{a.ball.text} {a.ball.notes.join(" ")}</p>}
  </div>);

const Coaching = ({ c }) => (
  <Card data-testid="coaching"><H icon={CheckCircle2}>Coaching feedback</H>
    <div className="grid md:grid-cols-3 gap-5 text-sm">
      {c.priority && <div><div className="font-semibold text-amber-300 mb-1">Priority to improve</div><p className="text-slate-300" data-testid="coaching-priority">{c.priority}</p></div>}
      {c.why && <div><div className="font-semibold mb-1">Why it matters</div><p className="text-slate-300">{c.why}</p></div>}
      {c.how && <div><div className="font-semibold mb-1">How to practise it</div><p className="text-slate-300">{c.how}</p></div>}</div>
    {c.measured_basis?.length > 0 && <p className="text-xs text-slate-500 mt-4" data-testid="coaching-basis"><span className="text-slate-400">Measured:</span> {c.measured_basis.join(" · ")}. Coaching text is an AI interpretation of the video and these measurements.</p>}
    {c.summary && <p className="text-sm text-slate-300 mt-4 leading-relaxed border-t border-white/5 pt-3" data-testid="coach-summary">{c.summary}</p>}
  </Card>);

const Drills = ({ v }) => (
  <Card data-testid="drills"><H icon={Dumbbell}>Personalised drills</H>
    <div className="space-y-4">{v.drills.map((d) => <div key={d.name} className="border-l-2 border-[#10B981]/50 pl-3">
      <div className="flex flex-wrap gap-2 items-center"><span className="font-medium">{d.name}</span>{d.dosage && <Badge tone="teal">{d.dosage}</Badge>}</div>
      {d.objective && <p className="text-xs text-slate-400 mt-0.5">{d.objective}</p>}
      {d.instructions && <p className="text-sm text-slate-300 mt-1">{d.instructions}</p>}
      {d.mistakes && <p className="text-xs text-amber-300/90 mt-1">Avoid: {d.mistakes}</p>}</div>)}</div>
    {v.next_step && <p className="text-sm mt-4 p-3 rounded-lg bg-amber-500/10 text-amber-200" data-testid="next-step">{v.next_step}</p>}
    {v.practice_plan?.length > 0 && <div className="mt-5" data-testid="practice-plan"><div className="font-semibold text-sm mb-2">Practice plan</div>
      {v.practice_plan.map((p, i) => <div key={i} className="text-sm flex justify-between border-b border-white/5 py-1.5"><span>{p.day}: {p.focus}</span><span className="text-slate-500">{p.duration_min}m</span></div>)}</div>}
  </Card>);

const Progress = ({ p }) => {
  if (!p) return null;
  const data = p.metrics.map((m) => ({ name: m.name, Previous: m.before, Latest: m.after }));
  return (
    <Card data-testid="progress-comparison"><H icon={TrendingUp}>Progress since {p.previous_date}</H>
      <div className="overflow-x-auto"><table className="w-full text-sm min-w-[480px]"><thead><tr className="text-left text-slate-400 text-xs"><th className="py-1">Measurement</th><th>Previous</th><th>Latest</th><th>Change</th></tr></thead>
        <tbody>{p.metrics.map((m) => <tr key={m.name} className="border-t border-white/5"><td className="py-2">{m.name}</td><td className="font-mono">{m.before_display}</td><td className="font-mono">{m.after_display}</td><td className="font-mono">{m.change_display}</td></tr>)}
          <tr className="border-t border-white/5"><td className="py-2">Overall score</td><td>{p.score_before.value ?? "—"} <span className="text-xs text-slate-500">({p.score_before.status})</span></td><td>{p.score_after.value ?? "—"} <span className="text-xs text-slate-500">({p.score_after.status})</span></td><td /></tr></tbody></table></div>
      {data.length > 0 && data.every((d) => p.metrics.find((m) => m.name === d.name).unit === p.metrics[0].unit) && <div className="h-48 mt-4"><ResponsiveContainer><BarChart data={data}><XAxis dataKey="name" stroke="#64748b" fontSize={10} /><YAxis stroke="#64748b" fontSize={10} /><Tooltip contentStyle={{ background: "#1C2541", border: "none" }} /><RLegend /><Bar dataKey="Previous" fill="#475569" /><Bar dataKey="Latest" fill="#10B981" /></BarChart></ResponsiveContainer></div>}
      <p className="text-xs text-slate-500 mt-3">{p.explanation}</p></Card>);
};

const ActionPlan = ({ v }) => (
  <Card className="border-l-4 border-l-[#00B4D8]" data-testid="action-plan"><H icon={ListChecks}>Your action plan</H>
    <ol className="space-y-2">{v.action_plan.map((a, i) => <li key={i} className="flex gap-3 text-sm"><span className="w-6 h-6 shrink-0 rounded-full bg-[#10B981]/15 text-[#34d399] grid place-items-center text-xs font-bold">{i + 1}</span><span className="text-slate-200">{a}</span></li>)}</ol>
  </Card>);

const About = ({ v }) => (
  <Card data-testid="report-about"><H icon={Camera}>Filming tips for your next clip</H>
    <ul className="text-sm text-slate-300 list-disc pl-5 space-y-1" data-testid="filming-tips">{v.filming_tips.map((t) => <li key={t}>{t}</li>)}</ul>
    <div className="text-xs text-slate-500 mt-4 space-y-1.5 border-t border-white/5 pt-3"><p className="flex gap-1.5"><Info size={13} className="shrink-0 mt-0.5" />{v.score_method}</p><p>{v.video_quality.method}</p><p>{v.limitations}</p></div>
  </Card>);

const Diagnostics = ({ d }) => !d ? null : (
  <details className="glass rounded-xl p-4 text-xs" data-testid="staff-diagnostics"><summary className="cursor-pointer flex items-center gap-2 text-slate-400"><ShieldCheck size={14} />Technical diagnostics (staff only)</summary>
    <pre className="mt-3 whitespace-pre-wrap break-all text-slate-500 font-mono">{JSON.stringify(d, null, 2)}</pre></details>);

export const PremiumReport = ({ r }) => {
  const v = r.view;
  return (
    <div className="space-y-5" data-testid="premium-report">
      <ReportHeader v={v} />
      <Takeaways v={v} />
      <ScorePanel sc={v.score} vq={v.video_quality} />
      {v.whats_working.length > 0 && <Card data-testid="whats-working"><H icon={CheckCircle2}>What's working</H><ul className="text-sm text-slate-300 list-disc pl-5 space-y-1">{v.whats_working.map((w) => <li key={w}>{w}</li>)}</ul></Card>}
      {v.angles.map((a, i) => <AngleSection key={a.video_id || i} a={a} raw={r.biomech?.[i]} />)}
      <Coaching c={v.coaching} />
      {v.drills.length > 0 && <Drills v={v} />}
      <Progress p={v.progress} />
      <ActionPlan v={v} />
      <About v={v} />
      <Diagnostics d={v.diagnostics} />
      <p className="text-xs text-slate-500 flex items-center gap-1"><ArrowRight size={12} />AI-assisted coaching report — not a medical assessment or an official rating.</p>
    </div>);
};
