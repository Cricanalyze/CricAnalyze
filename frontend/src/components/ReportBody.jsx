import { useState } from "react";
import { media } from "@/lib/api";
import { Card, Badge } from "@/components/Common";
import { PremiumReport } from "@/components/PremiumReport";
import { Biomech } from "@/components/Biomech";

const FrameNotes = ({ r }) => {
  const [frame, setFrame] = useState(null);
  return (
    <Card><h3 className="font-semibold mb-1">Frame-by-frame notes</h3><p className="text-xs text-slate-500 mb-3">AI interpretation of sampled frames. Tap a time to see the frame.</p>
      <div className="grid grid-cols-3 sm:grid-cols-4 gap-2">{r.frames.map((f) => <button key={f.index} onClick={() => setFrame(f)} className={`relative rounded-md overflow-hidden border ${frame?.index === f.index ? "border-[#10B981]" : "border-transparent"}`} data-testid={`frame-${f.index}`}>
        <img src={media(f.url)} alt={`Frame at ${f.t}s`} className="aspect-video object-cover w-full" /><span className="absolute bottom-0 left-0 text-[10px] font-mono bg-black/70 px-1">{f.t}s</span></button>)}</div>
      {frame && <img src={media(frame.url)} alt="Selected frame" className="mt-3 rounded-lg w-full" />}
      <div className="space-y-3 mt-4">{(r.observations || []).map((o, i) => <div key={i} className="border-l-2 border-[#00B4D8]/40 pl-3" data-testid={`observation-${i}`}>
        <div className="flex flex-wrap gap-2 items-center text-xs"><span className="font-semibold capitalize text-sm">{o.area?.replace(/_/g, " ")}</span><Badge tone={o.evidence_type === "observed" ? "teal" : "amber"}>{o.evidence_type === "observed" ? "Seen in video" : "Coach inference"}</Badge>
          {o.timestamp_s != null && <button className="font-mono text-[#00B4D8]" onClick={() => setFrame(r.frames.find((f) => f.index === o.image_index) || null)}>{o.timestamp_s}s</button>}</div>
        <p className="text-sm text-slate-300 mt-1">{o.observation}</p></div>)}</div></Card>);
};

const VisualRatings = ({ scores }) => (
  <Card><h3 className="font-semibold mb-1">Visual ratings by area</h3><p className="text-xs text-slate-500 mb-3">AI visual impressions (1–5), separate from the measured technique score.</p>
    {Object.entries(scores || {}).filter(([, s]) => s?.rating).map(([k, s]) => <div key={k} className="mb-2.5"><div className="flex justify-between text-xs"><span className="capitalize">{k.replace(/_/g, " ")}</span><span className="text-slate-400">{s.rating}/5</span></div>
      <div className="h-1.5 bg-white/10 rounded mt-1"><div className="h-full rounded bg-[#00B4D8]" style={{ width: `${s.rating * 20}%` }} /></div>{s?.note && <p className="text-[11px] text-slate-500 mt-0.5">{s.note}</p>}</div>)}</Card>);

export const ReportBody = ({ r, videoUrl, originalUrl, showLocked = true }) => (
  <>
    <div className="mb-6">{r.view ? <PremiumReport r={r} /> : <Biomech r={r} />}</div>
    <div className="grid lg:grid-cols-5 gap-6" data-testid="report-view">
      <div className="lg:col-span-3 space-y-5">
        {videoUrl && <div><video src={videoUrl} controls className="w-full rounded-xl bg-black aspect-video" data-testid="report-video" />
          <div className="flex justify-between text-xs text-slate-500 mt-1.5"><span>Normal-speed playback. Use the analysis viewer above for slow motion.</span>{originalUrl && <a href={originalUrl} download className="text-[#00B4D8] hover:underline" data-testid="original-video-link">Original video</a>}</div></div>}
        <FrameNotes r={r} />
      </div>
      <div className="lg:col-span-2 space-y-5">
        <VisualRatings scores={r.scores} />
        {showLocked && r.locked?.length > 0 && <Card><p className="text-xs text-amber-300" data-testid="report-locked">Upgrade to unlock: {r.locked.join(", ")}</p></Card>}
      </div>
    </div>
  </>);
