import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { FileDown } from "lucide-react";
import { toast } from "sonner";
import { media } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { ReportBody } from "@/components/ReportBody";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function SharedReport() {
  const { token } = useParams();
  const [d, setD] = useState(null);
  useEffect(() => { fetch(`${API}/public/reports/${token}`).then((r) => (r.ok ? r.json() : Promise.reject())).then(setD).catch(() => setD(false)); }, [token]);
  const pdf = async () => {
    const r = await fetch(`${API}/public/reports/${token}/pdf`);
    if (!r.ok) return toast.error("PDF isn't available for this report.");
    const a = document.createElement("a"); a.href = URL.createObjectURL(await r.blob()); a.download = `cricanalyze-report.pdf`; a.click();
  };
  if (d === false) return <div className="min-h-screen grid place-items-center bg-[#0B132B] text-slate-300 p-6 text-center" data-testid="shared-not-found"><div><h1 className="text-2xl font-semibold mb-2">This link isn't active</h1><p className="text-sm text-slate-400">The player may have turned sharing off.</p><Link to="/" className="text-[#00B4D8] text-sm mt-4 inline-block">Go to CricAnalyze</Link></div></div>;
  if (!d) return <div className="min-h-screen grid place-items-center bg-[#0B132B] text-slate-400">Loading…</div>;
  const v = d.videos?.[0];
  return (
    <div className="min-h-screen bg-[#0B132B] text-slate-100" data-testid="shared-report">
      <header className="border-b border-white/10"><div className="max-w-6xl mx-auto px-4 py-3 flex justify-between items-center">
        <Link to="/" className="font-semibold tracking-tight">Cric<span className="text-[#10B981]">Analyze</span></Link>
        <div className="flex gap-2 items-center"><span className="text-xs text-slate-400 hidden sm:inline">Shared report</span>
          {d.pdf_available && <Button variant="secondary" size="sm" onClick={pdf} data-testid="shared-pdf-btn"><FileDown size={15} className="mr-1" />PDF</Button>}</div></div></header>
      <main className="max-w-6xl mx-auto px-4 py-6"><ReportBody r={d.report} videoUrl={v && media(v.url)} originalUrl={v && media(v.original_url)} showLocked={false} /></main>
    </div>);
}
