import { useState } from "react";
import { Footprints } from "lucide-react";
import { media } from "@/lib/api";
import { Card, Badge } from "@/components/Common";

const TONE = { measured: "green", inconclusive: "amber", unavailable: "slate" };

const Item = ({ x }) => {
  const [orig, setOrig] = useState(false);
  const img = orig ? x.frame_url : x.overlay_url || x.frame_url;
  return (
    <div className="rounded-lg border border-white/10 p-4 flex flex-col gap-3" data-testid={`assessment-${x.key}`}>
      <div className="flex justify-between gap-2 items-start"><div className="font-semibold text-sm">{x.name}</div><Badge tone={TONE[x.status]}>{x.status_label}</Badge></div>
      <p className="text-sm text-slate-300" data-testid={`assessment-${x.key}-summary`}>{x.summary || x.reason}</p>
      {x.details?.length > 0 && <dl className="text-xs space-y-1">{x.details.map((d) => <div key={d.label} className="flex gap-2"><dt className="text-slate-500 shrink-0 w-40">{d.label}</dt><dd className="text-slate-200">{d.value}</dd></div>)}</dl>}
      {x.ai_note && <p className="text-xs text-amber-200" data-testid={`assessment-${x.key}-ai-note`}><span className="font-semibold">AI visual note (foot direction):</span> {x.ai_note}</p>}
      {img && <figure><img src={media(img)} alt={`${x.name} reference frame at ${x.t}s`} className="rounded-md w-full max-h-72 object-contain bg-black" data-testid={`assessment-${x.key}-image`} />
        <figcaption className="flex justify-between text-[11px] text-slate-500 mt-1"><span>Frame {x.idx} · {x.t?.toFixed(3)} s (original timing)</span>
          {x.overlay_url && <button onClick={() => setOrig(!orig)} className="text-[#00B4D8] hover:underline" data-testid={`assessment-${x.key}-toggle`}>{orig ? "Show measurement lines" : "Show original frame"}</button>}</figcaption></figure>}
      <details className="text-[11px] text-slate-500"><summary className="cursor-pointer">How this is measured</summary><p className="mt-1">{x.method}</p></details>
    </div>);
};

export const BowlingAssessments = ({ items }) => !items?.length ? null : (
  <Card data-testid="bowling-assessments">
    <h3 className="font-semibold text-base flex items-center gap-2 mb-1"><Footprints size={17} className="text-[#00B4D8]" />Bowling biomechanics</h3>
    <p className="text-xs text-slate-400 mb-4">Measured from the original video frames at their original timestamps. Not part of the technique score. Anything that couldn't be seen clearly is marked unavailable.</p>
    <div className="grid md:grid-cols-2 gap-4">{items.map((x) => <Item key={x.key} x={x} />)}</div>
  </Card>);
