import { useEffect, useRef, useState, useCallback } from "react";
import { Play, Pause, ChevronLeft, ChevronRight, Loader2 } from "lucide-react";
import { media } from "@/lib/api";
import { Card } from "@/components/Common";

const EDGES = [[5, 6], [5, 7], [7, 9], [6, 8], [8, 10], [5, 11], [6, 12], [11, 12], [11, 13], [13, 15], [12, 14], [14, 16], [0, 5], [0, 6]];
export const BALL_COLOR = "#FFE600";

const contentRect = (v, c) => {
  const vw = v.videoWidth || 16, vh = v.videoHeight || 9, s = Math.min(c.width / vw, c.height / vh);
  return { x: (c.width - vw * s) / 2, y: (c.height - vh * s) / 2, w: vw * s, h: vh * s };
};

const drawSkeleton = (ctx, kp, R) => {
  const P = (i) => [R.x + kp[i][0] * R.w, R.y + kp[i][1] * R.h];
  ctx.lineWidth = 3; ctx.strokeStyle = "#00B4D8";
  EDGES.forEach(([a, b]) => { if (kp[a][2] >= 0.3 && kp[b][2] >= 0.3) { ctx.beginPath(); ctx.moveTo(...P(a)); ctx.lineTo(...P(b)); ctx.stroke(); } });
  kp.forEach((k, i) => { if (k[2] < 0.3) return; ctx.fillStyle = k[2] >= 0.5 ? "#10B981" : "#FBBF24"; ctx.beginPath(); ctx.arc(...P(i), 4, 0, 7); ctx.fill(); });
};

const drawBall = (ctx, d, trail, R) => {
  const P = (p) => [R.x + p.x * R.w, R.y + p.y * R.h];
  ctx.strokeStyle = BALL_COLOR; ctx.lineWidth = 2;
  for (let i = 1; i < trail.length; i++) {
    const est = trail[i].status === "estimated" || trail[i - 1].status === "estimated";
    ctx.setLineDash(est ? [5, 5] : []); ctx.beginPath(); ctx.moveTo(...P(trail[i - 1])); ctx.lineTo(...P(trail[i])); ctx.stroke();
  }
  ctx.setLineDash([]);
  trail.slice(0, -1).forEach((p) => { ctx.beginPath(); ctx.arc(...P(p), 2.5, 0, 7); p.status === "observed" ? (ctx.fillStyle = BALL_COLOR, ctx.fill()) : ctx.stroke(); });
  const [cx, cy] = P(d), r = 11;
  ctx.lineWidth = 4; ctx.strokeStyle = "#000"; ctx.beginPath(); ctx.arc(cx, cy, r + 1, 0, 7); ctx.stroke();
  ctx.lineWidth = 2; ctx.strokeStyle = BALL_COLOR; ctx.setLineDash(d.status === "estimated" ? [4, 3] : []); ctx.beginPath(); ctx.arc(cx, cy, r, 0, 7); ctx.stroke(); ctx.setLineDash([]);
  const label = d.status === "observed" ? "BALL" : "BALL (estimated)";
  ctx.font = "bold 12px monospace"; const tw = ctx.measureText(label).width + 10;
  const right = cx + 40 + tw < R.x + R.w, lx = right ? cx + 40 : cx - 40 - tw, ly = Math.max(R.y + 18, cy - 40);
  ctx.beginPath(); ctx.moveTo(right ? lx : lx + tw, ly - 7); ctx.lineTo(cx + (right ? r : -r) * 0.7, cy - r * 0.7); ctx.stroke();
  ctx.fillStyle = BALL_COLOR; ctx.fillRect(lx, ly - 16, tw, 18); ctx.fillStyle = "#000"; ctx.fillText(label, lx + 5, ly - 3);
};

export const Legend = () => (
  <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-400" data-testid="overlay-legend">
    <span className="flex items-center gap-1"><span className="w-4 h-0.5 bg-[#00B4D8]" />Body outline</span>
    <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-[#10B981]" />Clearly seen joint</span>
    <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-[#FBBF24]" />Less certain joint</span>
    <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-full border-2" style={{ borderColor: BALL_COLOR }} />Ball seen (solid trail)</span>
    <span className="flex items-center gap-1"><span className="w-4 border-t-2 border-dashed" style={{ borderColor: BALL_COLOR }} />Estimated between detections</span>
  </div>
);

const useFrameState = (b) => {
  const fps = b.ball?.fps || b.fps || 30;
  const byFrame = useRef(null);
  if (!byFrame.current) { byFrame.current = new Map(); (b.ball?.detections || []).forEach((d) => byFrame.current.set(d.frame, d)); }
  return { fps, byFrame: byFrame.current };
};

export const AnalysisViewer = ({ b }) => {
  const vRef = useRef(null), cRef = useRef(null);
  const [showPose, setShowPose] = useState(true);
  const [showBall, setShowBall] = useState(true);
  const [t, setT] = useState(0);
  const [dur, setDur] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [rate, setRate] = useState(0.25);
  const { fps, byFrame } = useFrameState(b);
  const frame = Math.floor(t * fps + 0.1);
  const det = byFrame.get(frame);
  const pose = (b.pose_track || []).reduce((best, p) => (Math.abs(p.t - t) < Math.abs((best?.t ?? 1e9) - t) ? p : best), null);
  const poseOn = pose && Math.abs(pose.t - t) <= 0.6 / fps + 0.02;

  const draw = useCallback(() => {
    const v = vRef.current, c = cRef.current;
    if (!v || !c) return;
    c.width = c.clientWidth; c.height = c.clientHeight;
    const ctx = c.getContext("2d"), R = contentRect(v, c);
    ctx.clearRect(0, 0, c.width, c.height);
    if (showPose && poseOn && !loading && !failed) drawSkeleton(ctx, pose.kp, R);
    if (showBall && det && !loading && !failed) {
      const trail = [];
      for (let f = frame - 8; f <= frame; f++) { const d = byFrame.get(f); if (d && d.track_id === det.track_id) trail.push(d); }
      drawBall(ctx, det, trail, R);
    }
  }, [showPose, showBall, poseOn, pose, det, frame, byFrame, loading, failed]);
  useEffect(() => { draw(); }, [draw]);
  useEffect(() => {
    const v = vRef.current;
    if (!v) return;
    let id, stop = false;
    const tick = (_, meta) => { if (stop) return; setT(meta?.mediaTime ?? v.currentTime); id = v.requestVideoFrameCallback ? v.requestVideoFrameCallback(tick) : requestAnimationFrame(() => tick()); };
    id = v.requestVideoFrameCallback ? v.requestVideoFrameCallback(tick) : requestAnimationFrame(() => tick());
    const onResize = () => draw();
    window.addEventListener("resize", onResize);
    return () => { stop = true; window.removeEventListener("resize", onResize); if (v.cancelVideoFrameCallback) v.cancelVideoFrameCallback(id); else cancelAnimationFrame(id); };
  }, [draw]);

  const seek = (s) => { const v = vRef.current; v.pause(); v.currentTime = Math.max(0, Math.min(dur, s)); setT(v.currentTime); };
  const step = (n) => { const cur = Math.floor((vRef.current?.currentTime || 0) * fps + 0.1); seek((cur + n) / fps + 0.5 / fps); };
  const toggle = () => { const v = vRef.current; v.paused ? v.play() : v.pause(); };
  const setSpeed = (r) => { setRate(r); if (vRef.current) vRef.current.playbackRate = r; };

  return (
    <Card data-testid="analysis-viewer">
      <div className="flex flex-wrap justify-between gap-2 mb-3"><h3 className="font-semibold">Analysis viewer · {b.angle?.replace("_", "-")}</h3>
        <div className="flex gap-4 text-xs">
          <label className="flex gap-1.5 items-center"><input type="checkbox" checked={showPose} onChange={(e) => setShowPose(e.target.checked)} data-testid="viewer-skeleton-toggle" />Skeleton</label>
          <label className="flex gap-1.5 items-center"><input type="checkbox" checked={showBall} onChange={(e) => setShowBall(e.target.checked)} data-testid="viewer-ball-toggle" />Ball tracking</label>
          <div className="flex rounded-md overflow-hidden border border-white/10" role="group" aria-label="Playback speed">{[0.1, 0.25, 0.5, 1].map((r) => <button key={r} onClick={() => setSpeed(r)} className={`px-2 py-0.5 ${rate === r ? "bg-[#10B981] text-[#0B132B]" : "hover:bg-white/10"}`} data-testid={`viewer-speed-${r * 100}`}>{r === 1 ? "Normal" : `${r}×`}</button>)}</div></div></div>
      <div className="relative rounded-lg overflow-hidden bg-black aspect-video">
        {b.video_url && <video ref={vRef} src={media(b.video_url)} className="absolute inset-0 w-full h-full object-contain" playsInline preload="auto"
          onLoadedData={() => { const v = vRef.current; setLoading(false); setDur(v.duration || 0); v.playbackRate = rate; const t0 = b.pose_track?.[0]?.t; if (t0 > 1 && v.currentTime < 0.1) { v.currentTime = t0; setT(t0); } draw(); }} onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onSeeked={draw} onError={() => { setLoading(false); setFailed(true); }} data-testid="viewer-video" />}
        {failed && <div className="absolute inset-0 grid place-items-center text-center text-sm text-amber-300 p-6 bg-black/80" data-testid="viewer-video-error">This browser can't play this video. The analysis results are unaffected; try Chrome, Safari or Edge.</div>}
        <canvas ref={cRef} className="absolute inset-0 w-full h-full pointer-events-none" data-testid="viewer-canvas" />
        {loading && <div className="absolute inset-0 grid place-items-center text-slate-400 text-sm" data-testid="viewer-loading"><Loader2 className="animate-spin" /></div>}
      </div>
      <div className="flex items-center gap-2 mt-3">
        <button onClick={() => step(-1)} className="p-1.5 rounded bg-white/5 hover:bg-white/10" aria-label="Previous frame" data-testid="viewer-prev-frame"><ChevronLeft size={16} /></button>
        <button onClick={toggle} className="p-1.5 rounded bg-[#10B981] text-[#0B132B]" aria-label={playing ? "Pause" : "Play"} data-testid="viewer-play">{playing ? <Pause size={16} /> : <Play size={16} />}</button>
        <button onClick={() => step(1)} className="p-1.5 rounded bg-white/5 hover:bg-white/10" aria-label="Next frame" data-testid="viewer-next-frame"><ChevronRight size={16} /></button>
        <input type="range" min={0} max={dur || 0} step={1 / fps} value={t} onChange={(e) => seek(+e.target.value)} className="flex-1 accent-[#10B981]" data-testid="viewer-scrubber" aria-label="Timeline" />
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs font-mono text-slate-400 mt-2" data-testid="viewer-readout">
        <span>t={t.toFixed(3)}s</span><span>frame {frame}</span>
        <span data-testid="viewer-ball-readout">{det ? (det.status === "observed" ? "ball seen in this frame" : "ball: estimated position") : "ball: not detected in this frame"}</span>
        <span>{poseOn ? `body outline from frame at ${pose.t}s` : "body outline: not checked on this frame"}</span>
      </div>
      <div className="mt-3"><Legend /></div>
    </Card>
  );
};
