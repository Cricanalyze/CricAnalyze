import { useEffect, useState } from "react";
import { Share2, Copy, Link2Off } from "lucide-react";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

export const ShareButton = ({ jobId }) => {
  const [s, setS] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { api.get(`/analyses/${jobId}/share`).then(({ data }) => setS(data)).catch(() => setS({ enabled: false })); }, [jobId]);
  const full = s?.url ? `${window.location.origin}${s.url}` : "";
  const run = async (fn) => { setBusy(true); try { setS((await fn()).data); } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); } };
  const copy = async () => { try { await navigator.clipboard.writeText(full); toast.success("Link copied"); } catch { toast.info(full); } };
  return (
    <Popover>
      <PopoverTrigger asChild><Button variant="secondary" data-testid="report-share-btn"><Share2 size={16} className="mr-1" />{s?.enabled ? "Shared" : "Share"}</Button></PopoverTrigger>
      <PopoverContent className="w-80 bg-[#1C2541] border-white/10 text-slate-200" data-testid="share-panel">
        {!s?.enabled ? <div className="space-y-3"><p className="text-sm">Create a public link to this report. Anyone with the link can view the full report, video and PDF. No sign-in needed.</p>
          <Button className="w-full" disabled={busy} onClick={() => run(() => api.post(`/analyses/${jobId}/share`))} data-testid="share-create-btn">Create share link</Button></div>
          : <div className="space-y-3"><p className="text-xs text-slate-400">Anyone with this link can view the report. It works until you turn it off.</p>
            <div className="flex gap-2"><input readOnly value={full} className="flex-1 min-w-0 bg-black/30 rounded px-2 py-1.5 text-xs font-mono" data-testid="share-link-input" onFocus={(e) => e.target.select()} />
              <Button size="sm" onClick={copy} data-testid="share-copy-btn"><Copy size={14} /></Button></div>
            <Button variant="ghost" size="sm" className="w-full text-red-300" disabled={busy} onClick={() => run(() => api.delete(`/analyses/${jobId}/share`))} data-testid="share-disable-btn"><Link2Off size={14} className="mr-1" />Turn off link</Button></div>}
      </PopoverContent>
    </Popover>);
};
