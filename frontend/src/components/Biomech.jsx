import { useState } from "react";
import { media } from "@/lib/api";
import { Card, Badge } from "@/components/Common";

const ST = { measured: ["green", "Measured"], measured_estimated_phase: ["teal", "Measured · estimated phase"], low_confidence: ["amber", "Low confidence"],
  not_measurable: ["slate", "Not measurable from this video"], locked: ["slate", "Not in plan"] };
const PH = { detected: "green", estimated: "amber", unavailable: "slate" };

const Angle = ({ b }) => {
  const [overlay, setOverlay] = useState(true);
  if (b.status === "unavailable") return <Card data-testid="biomech-unavailable"><h3 className="font-semibold">Pose measurement unavailable ({b.angle?.replace("_", "-")})</h3><p className="text-sm text-slate-400 mt-1">{b.error} Only AI visual observations are shown below.</p></Card>;
  const sc = b.score || {};
  return (
    <div className="space-y-4" data-testid={`biomech-${b.angle}`}>
      <Card className="flex flex-col sm:flex-row gap-4 sm:items-center">
        {sc.value != null ? <div className="text-5xl font-display font-extrabold" data-testid="biomech-score">{sc.value}<span className="text-base text-slate-400">/100</span></div>
          : <div className="font-semibold text-amber-300 max-w-[220px]" data-testid="biomech-score-insufficient">Insufficient evidence to calculate a reliable score.</div>}
        <div className="text-xs text-slate-400 space-y-1"><div>Score method {sc.version}: {sc.requirements}. Included {sc.included?.length ?? 0} metrics, {Math.round((sc.coverage || 0) * 100)}% weight coverage, {sc.detected_phases ?? 0} phases detected.</div>
          <div>Keypoint confidence (model, not technique quality): <b>{b.quality?.keypoint_confidence}</b> · {b.model?.pose_model} · {b.pipeline_version}</div>
          {b.quality?.issues?.map((i) => <div key={i} className="text-amber-300">{i}</div>)}</div>
      </Card>
      <Card><div className="flex justify-between mb-3"><h3 className="font-semibold">Kinematic breakdown · {b.angle?.replace("_", "-")}</h3>
        <label className="text-xs flex gap-2 items-center"><input type="checkbox" checked={overlay} onChange={(e) => setOverlay(e.target.checked)} data-testid="overlay-toggle" />Pose overlay</label></div>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">{b.phases.map((p) => <div key={p.key} data-testid={`phase-${p.key}`}>
          {p.frame_url ? <img src={media(overlay && p.overlay_url ? p.overlay_url : p.frame_url)} alt={`${p.name} at ${p.t}s`} className="rounded-md w-full aspect-video object-contain bg-black" />
            : <div className="rounded-md w-full aspect-video bg-white/5 grid place-items-center text-xs text-slate-500 p-2 text-center">Not identified</div>}
          <div className="text-sm font-medium mt-1">{p.name}</div><div className="flex gap-1 items-center"><Badge tone={PH[p.status]}>{p.status}</Badge>{p.t != null && <span className="text-[11px] font-mono text-slate-400">t={p.t}s</span>}</div>
          <p className="text-[11px] text-slate-500">{p.note}</p></div>)}</div></Card>
      <Card className="overflow-x-auto"><h3 className="font-semibold mb-3">Biomechanical metrics (2D image plane)</h3>
        <table className="w-full text-sm min-w-[560px]"><thead><tr className="text-left text-slate-400"><th className="py-1">Metric</th><th>Value</th><th>Unit</th><th>Confidence</th><th>Status</th></tr></thead>
          <tbody>{b.metrics.map((m) => <tr key={m.key} className="border-t border-white/5" data-testid={`metric-${m.key}`}><td className="py-2">{m.name}{m.t != null && <span className="text-xs text-slate-500"> (t={m.t}s)</span>}</td>
            <td className="font-mono">{m.value ?? "—"}</td><td className="text-slate-400">{m.unit}</td><td>{m.confidence ?? "—"}</td>
            <td><Badge tone={(ST[m.status] || ST.not_measurable)[0]}>{(ST[m.status] || ST.not_measurable)[1]}</Badge>{m.reason && <div className="text-[11px] text-slate-500">{m.reason}</div>}</td></tr>)}</tbody></table>
        <p className="text-[11px] text-slate-500 mt-2">{b.methodology?.angle_method} {b.methodology?.coordinate_system}</p></Card>
    </div>
  );
};

export const Biomech = ({ r }) => {
  if (!r.biomech?.length) return null;
  return (
    <div className="space-y-4" data-testid="biomech-section">
      {r.assessment_type !== "measured_biomechanical" && <Card className="border-amber-500/40 text-amber-200 text-sm" data-testid="vision-only-banner">Vision-only report: pose measurements were not available, so this is not a measured biomechanical assessment.</Card>}
      {r.biomech.map((b) => <Angle key={b.video_id} b={b} />)}
      {r.coach_summary && <Card><h3 className="font-semibold mb-2">Coach summary</h3><p className="text-sm text-slate-300 leading-relaxed" data-testid="coach-summary">{r.coach_summary}</p></Card>}
    </div>
  );
};
