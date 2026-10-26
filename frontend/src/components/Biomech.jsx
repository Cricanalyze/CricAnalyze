import { useState } from "react";
import { media } from "@/lib/api";
import { Card, Badge } from "@/components/Common";
import { AnalysisViewer, Legend } from "@/components/AnalysisViewer";

const ST = { measured: ["green", "Measured"], measured_estimated_phase: ["teal", "Measured · estimated phase"], low_confidence: ["amber", "Low confidence"],
  not_measurable: ["slate", "Not measurable from this video"], locked: ["slate", "Not in plan"] };
const PH = { detected: "green", estimated: "amber", unavailable: "slate" };
const EV = { high: "green", medium: "amber", low: "red" };

const ScoreCard = ({ b }) => {
  const sc = b.score || {};
  const name = (k) => b.metrics?.find((m) => m.key === k)?.name || k;
  if (!sc.components) return (
    <Card data-testid="biomech-score-legacy"><div className="font-semibold">{sc.value != null ? <span data-testid="biomech-score">{sc.value}/100</span> : "Insufficient evidence to calculate a reliable score."}</div>
      <p className="text-xs text-slate-400 mt-1">Saved with scoring method {sc.version}. Re-run the analysis for the component breakdown.</p></Card>);
  return (
    <Card data-testid="score-card">
      <div className="flex flex-col md:flex-row gap-6">
        <div className="md:w-60 shrink-0">
          {sc.value != null ? <div data-testid="biomech-score"><span className="text-6xl font-display font-extrabold">{sc.value}</span><span className="text-lg text-slate-400">/100</span>
            <div className="text-sm font-semibold text-[#10B981] mt-1">Technique Score</div></div>
            : <div data-testid="biomech-score-provisional"><Badge tone="amber">Provisional</Badge><p className="font-semibold text-amber-300 mt-2">No overall score: not enough reliable measurements.</p><p className="text-xs text-slate-400 mt-1">Component results below use only what could be measured.</p></div>}
          <div className="mt-4 text-xs space-y-1" data-testid="score-evidence"><div className="flex items-center gap-2">Evidence <Badge tone={EV[sc.evidence?.level]}>{sc.evidence?.level}</Badge></div>
            <div className="text-slate-400">Coverage {Math.round((sc.coverage || 0) * 100)}% of rubric weight · {sc.detected_phases} detected phases · mean confidence of scored metrics {sc.evidence?.mean_keypoint_confidence}</div></div>
        </div>
        <div className="flex-1 space-y-3" data-testid="score-components">
          {sc.components.map((c) => <div key={c.key} data-testid={`component-${c.key}`}>
            <div className="flex justify-between text-sm"><span>{c.name}</span><span className="font-mono text-slate-300">{c.score != null ? `${Math.round(c.score)}/100` : "not measured"}{c.contribution != null && sc.value != null && <span className="text-slate-500"> · +{c.contribution} pts</span>}</span></div>
            <div className="h-1.5 bg-white/10 rounded mt-1"><div className="h-full rounded bg-[#10B981]" style={{ width: `${c.score || 0}%` }} /></div>
            <div className="text-[11px] text-slate-500">{c.metrics.length} of {c.metrics.length + c.missing.length} metrics measured · {Math.round(c.coverage * 100)}% weight</div></div>)}
          {sc.not_assessed?.map((n) => <div key={n.key} className="text-[11px] text-slate-500">{n.name}: not assessed. {n.reason}</div>)}
          <div className="grid sm:grid-cols-2 gap-3 pt-1 text-xs">
            <div><div className="font-semibold text-[#10B981] mb-1">Strongest factors</div>{sc.strongest?.length ? sc.strongest.map((k) => <div key={k}>{name(k)}</div>) : <div className="text-slate-500">None stood out.</div>}</div>
            <div><div className="font-semibold text-amber-300 mb-1">Main opportunities</div>{sc.opportunities?.length ? sc.opportunities.map((k) => <div key={k}>{name(k)}</div>) : <div className="text-slate-500">No measured metric fell well outside its target.</div>}</div></div>
        </div>
      </div>
      <p className="text-[11px] text-slate-500 mt-4">Method {sc.version} (rubric {sc.rubric_hash}). {sc.method?.status} {b.quality?.issues?.join(" ")}</p>
    </Card>);
};

const BallSummary = ({ ball }) => {
  if (!ball) return null;
  const ok = ball.status === "tracked";
  return (
    <Card data-testid="ball-summary"><h3 className="font-semibold mb-2">Ball tracking</h3>
      {!ok && <p className="text-amber-300 text-sm" data-testid="ball-not-detected">{ball.message || "Ball not reliably detected in this video."}</p>}
      {ok && <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
        <div><div className="text-xs text-slate-400">Frames detected</div><div className="font-mono" data-testid="ball-frames-detected">{ball.frames_detected} / {ball.frames_processed}</div></div>
        <div><div className="text-xs text-slate-400">Detection coverage</div><div className="font-mono" data-testid="ball-coverage">{(ball.coverage * 100).toFixed(1)}%</div></div>
        <div><div className="text-xs text-slate-400">Highest confidence</div><div className="font-mono" data-testid="ball-best">{ball.best.conf} at {ball.best.t}s</div></div>
        <div><div className="text-xs text-slate-400">Mean confidence</div><div className="font-mono">{ball.mean_conf}</div></div></div>}
      <ul className="text-xs text-slate-400 list-disc pl-5 mt-3 space-y-0.5">
        {(ball.gaps || []).map((g, i) => <li key={i}>Tracking interrupted at {g.t_from}s{g.t_to ? `–${g.t_to}s` : ""}: {g.reason}</li>)}
        {(ball.limitations || []).filter((l) => l !== ball.message).map((l) => <li key={l}>{l}</li>)}
        {ball.error && <li>{ball.error}</li>}
        <li>{ball.events?.note || "Ball release and bat contact are not determined. Ball speed is not measured."}</li></ul>
      <p className="text-[11px] text-slate-500 mt-2">{ball.model?.detector} · {ball.model?.note} · {ball.version}</p>
    </Card>);
};

const PhaseGrid = ({ b }) => {
  const [overlay, setOverlay] = useState(true);
  const [ballOn, setBallOn] = useState(true);
  const src = (p) => media(overlay ? (ballOn && p.ball_overlay_url) || p.overlay_url || p.frame_url : p.frame_url);
  return (
    <Card><div className="flex flex-wrap gap-2 justify-between mb-3"><h3 className="font-semibold">Kinematic breakdown · {b.angle?.replace("_", "-")}</h3>
      <div className="flex gap-4 text-xs"><label className="flex gap-1.5 items-center"><input type="checkbox" checked={overlay} onChange={(e) => setOverlay(e.target.checked)} data-testid="overlay-toggle" />Pose overlay</label>
        <label className="flex gap-1.5 items-center"><input type="checkbox" checked={ballOn} onChange={(e) => setBallOn(e.target.checked)} data-testid="phase-ball-toggle" />Ball marker</label></div></div>
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">{b.phases.map((p) => <div key={p.key} data-testid={`phase-${p.key}`}>
        {p.frame_url ? <img src={src(p)} alt={`${p.name} at ${p.t}s`} className="rounded-md w-full aspect-video object-contain bg-black" />
          : <div className="rounded-md w-full aspect-video bg-white/5 grid place-items-center text-xs text-slate-500 p-2 text-center">Not identified</div>}
        <div className="text-sm font-medium mt-1">{p.name}</div><div className="flex flex-wrap gap-1 items-center"><Badge tone={PH[p.status]}>{p.status}</Badge>{p.t != null && <span className="text-[11px] font-mono text-slate-400">t={p.t}s</span>}</div>
        {p.ball ? <div className="text-[11px] font-mono text-yellow-300" data-testid={`phase-ball-${p.key}`}>ball conf {p.ball.conf}</div> : p.frame_url && <div className="text-[11px] text-slate-500">ball not detected in this frame</div>}
        <p className="text-[11px] text-slate-500">{p.note}</p></div>)}</div>
      <div className="mt-3"><Legend /></div></Card>);
};

const Metrics = ({ b }) => (
  <Card className="overflow-x-auto"><h3 className="font-semibold mb-3">Biomechanical metrics (2D image plane)</h3>
    <table className="w-full text-sm min-w-[620px]"><thead><tr className="text-left text-slate-400"><th className="py-1">Metric</th><th>Value</th><th>Unit</th><th>Confidence</th><th>Metric score</th><th>Status</th></tr></thead>
      <tbody>{b.metrics.map((m) => <tr key={m.key} className="border-t border-white/5" data-testid={`metric-${m.key}`}><td className="py-2">{m.name}{m.t != null && <span className="text-xs text-slate-500"> (t={m.t}s)</span>}</td>
        <td className="font-mono">{m.value ?? "—"}</td><td className="text-slate-400">{m.unit}</td><td>{m.confidence ?? "—"}</td><td className="font-mono">{m.metric_score ?? "—"}</td>
        <td><Badge tone={(ST[m.status] || ST.not_measurable)[0]}>{(ST[m.status] || ST.not_measurable)[1]}</Badge>{m.reason && <div className="text-[11px] text-slate-500">{m.reason}</div>}</td></tr>)}</tbody></table>
    <p className="text-[11px] text-slate-500 mt-2">{b.methodology?.angle_method} {b.methodology?.coordinate_system} {b.score?.method?.normalisation}</p></Card>);

const Angle = ({ b }) => {
  if (b.status === "unavailable") return <Card data-testid="biomech-unavailable"><h3 className="font-semibold">Pose measurement unavailable ({b.angle?.replace("_", "-")})</h3><p className="text-sm text-slate-400 mt-1">{b.error} Only AI visual observations are shown below.</p><div className="mt-4"><BallSummary ball={b.ball} /></div></Card>;
  return (
    <div className="space-y-4" data-testid={`biomech-${b.angle}`}>
      <ScoreCard b={b} />
      {b.video_url && <AnalysisViewer b={b} />}
      <PhaseGrid b={b} />
      <BallSummary ball={b.ball} />
      <Metrics b={b} />
    </div>);
};

export const Biomech = ({ r }) => {
  if (!r.biomech?.length) return null;
  return (
    <div className="space-y-4" data-testid="biomech-section">
      {r.assessment_type !== "measured_biomechanical" && <Card className="border-amber-500/40 text-amber-200 text-sm" data-testid="vision-only-banner">Vision-only report: pose measurements were not available, so this is not a measured biomechanical assessment.</Card>}
      {r.biomech.map((b) => <Angle key={b.video_id} b={b} />)}
      {r.coach_summary && <Card><h3 className="font-semibold mb-2">Coach summary</h3><p className="text-sm text-slate-300 leading-relaxed" data-testid="coach-summary">{r.coach_summary}</p></Card>}
    </div>);
};
