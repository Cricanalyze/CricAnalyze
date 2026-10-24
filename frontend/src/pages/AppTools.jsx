import { useEffect, useRef, useState, useCallback } from "react";
import { toast } from "sonner";
import { Send, Plus, Sparkles, Trash2, Share2, Award, Flame, MessageSquare } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api, errMsg, fmtDate, BACKEND, csrf, SITE } from "@/lib/api";
import { PageHeader, Empty, Card, Badge, Seo } from "@/components/Common";
import { PassportView } from "@/pages/Blog";
import { useAuth } from "@/context/AuthContext";

const PROMPTS = {
  coach: ["Explain my latest report in simple words", "Which drills should I do this week?", "Build a 4-day practice structure for me", "What evidence supports my main weakness?"],
  ask: ["What should I work on next?", "What changed between my last two reports?", "Which drills were recommended?", "What progress is supported by my reports?"],
};

export const Coach = () => {
  const [mode, setMode] = useState("coach");
  const [convs, setConvs] = useState([]);
  const [cid, setCid] = useState(null);
  const [msgs, setMsgs] = useState([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef(null);
  const loadConvs = useCallback(() => api.get("/coach/conversations", { params: { mode } }).then(({ data }) => setConvs(data)).catch(() => {}), [mode]);
  useEffect(() => { loadConvs(); setCid(null); setMsgs([]); }, [loadConvs]);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs]);
  const open = async (id) => { setCid(id); setMsgs((await api.get(`/coach/conversations/${id}`)).data); };
  const send = async (q) => {
    const message = (q || text).trim();
    if (!message || busy) return;
    setText(""); setBusy(true);
    setMsgs((m) => [...m, { role: "user", content: message }, { role: "assistant", content: "" }]);
    try {
      const res = await fetch(`${BACKEND}/api/coach/chat`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf() }, body: JSON.stringify({ message, mode, conversation_id: cid }) });
      if (!res.ok) { const j = await res.json().catch(() => ({})); throw new Error(j.detail || "Request failed"); }
      const reader = res.body.getReader(); const dec = new TextDecoder(); let buf = "";
      for (;;) {
        const { done, value } = await reader.read(); if (done) break;
        buf += dec.decode(value, { stream: true });
        const parts = buf.split("\n\n"); buf = parts.pop();
        for (const p of parts) {
          const d = p.replace(/^data: /, ""); if (d === "[DONE]") continue;
          const j = JSON.parse(d);
          if (j.conversation_id) setCid(j.conversation_id);
          if (j.delta) setMsgs((m) => { const c = [...m]; c[c.length - 1] = { ...c[c.length - 1], content: c[c.length - 1].content + j.delta }; return c; });
          if (j.error) toast.error(j.error);
        }
      }
      loadConvs();
    } catch (e) { toast.error(e.message); setMsgs((m) => m.slice(0, -1)); } finally { setBusy(false); }
  };
  return (
    <div><Seo title="AI Coach" path="/app/coach" noindex />
      <PageHeader eyebrow="AI" title={mode === "coach" ? "AI Cricket Coach" : "Ask CricAnalyze"} desc={mode === "coach" ? "Explanations, drills and weekly structure grounded in your own reports." : "Questions about your reports, timeline and practice history — answered only from your data."}>
        <div className="flex rounded-lg border border-white/10 p-1">{[["coach", "AI Coach"], ["ask", "Ask CricAnalyze"]].map(([v, l]) => <button key={v} onClick={() => setMode(v)} data-testid={`mode-${v}`} className={`px-3 py-1.5 text-sm rounded-md ${mode === v ? "bg-[#00B4D8] text-[#0B132B]" : "text-slate-300"}`}>{l}</button>)}</div>
      </PageHeader>
      <div className="grid lg:grid-cols-4 gap-5">
        <Card className="lg:col-span-1 p-3 space-y-1 max-h-[560px] overflow-y-auto"><Button size="sm" variant="secondary" className="w-full mb-2" onClick={() => { setCid(null); setMsgs([]); }} data-testid="new-chat-btn"><Plus size={14} className="mr-1" />New chat</Button>
          {convs.map((c) => <button key={c.id} onClick={() => open(c.id)} className={`block w-full text-left text-sm px-2 py-2 rounded-md truncate ${cid === c.id ? "bg-white/10" : "hover:bg-white/5 text-slate-400"}`} data-testid={`conv-${c.id}`}>{c.title}</button>)}</Card>
        <Card className="lg:col-span-3 flex flex-col h-[560px] p-0">
          <div className="flex-1 overflow-y-auto p-5 space-y-4" data-testid="chat-messages">
            {!msgs.length && <div className="text-center mt-10"><MessageSquare className="mx-auto text-[#00B4D8] mb-3" /><p className="text-slate-400 text-sm mb-4">Try one of these:</p>
              <div className="flex flex-wrap justify-center gap-2">{PROMPTS[mode].map((p) => <button key={p} onClick={() => send(p)} className="text-xs border border-white/10 rounded-full px-3 py-1.5 hover:border-[#10B981]" data-testid="quick-prompt">{p}</button>)}</div></div>}
            {msgs.map((m, i) => <div key={i} className={`max-w-[85%] whitespace-pre-wrap text-sm leading-relaxed rounded-xl px-4 py-3 ${m.role === "user" ? "ml-auto bg-[#00B4D8]/15" : "bg-white/5"}`} data-testid={`msg-${m.role}`}>{m.content || (busy ? "…" : "")}</div>)}
            <div ref={end} />
          </div>
          <form onSubmit={(e) => { e.preventDefault(); send(); }} className="border-t border-white/5 p-3 flex gap-2"><Input value={text} onChange={(e) => setText(e.target.value)} placeholder="Ask about your technique…" maxLength={2000} data-testid="chat-input" aria-label="Message" />
            <Button type="submit" disabled={busy || !text.trim()} data-testid="chat-send-btn"><Send size={16} /></Button></form>
        </Card>
      </div>
      <p className="text-xs text-slate-500 mt-3">AI guidance only — not medical advice. Answers are limited to the data in your reports.</p>
    </div>
  );
};

const PlanCard = ({ p, reload }) => {
  const [edit, setEdit] = useState(false);
  const [items, setItems] = useState(p.items);
  const [title, setTitle] = useState(p.title);
  const done = p.items.filter((i) => i.completed).length;
  const toggle = async (it) => { await api.post(`/training/plans/${p.id}/items/${it.id}/complete`, { done: !it.completed, notes: it.notes || "" }); reload(); };
  const save = async () => { try { await api.put(`/training/plans/${p.id}`, { title, period: p.period, items }); setEdit(false); reload(); toast.success("Plan saved."); } catch (e) { toast.error(errMsg(e)); } };
  const days = [...new Set(p.items.map((i) => i.day))];
  return (
    <Card data-testid={`plan-${p.id}`}>
      <div className="flex flex-wrap justify-between gap-2 mb-3"><div>{edit ? <Input value={title} onChange={(e) => setTitle(e.target.value)} /> : <h3 className="font-semibold">{p.title}</h3>}
        <div className="flex gap-2 mt-1"><Badge tone={p.source === "coach_approved" ? "green" : p.source === "ai_suggestion" ? "amber" : "slate"}>{p.source === "ai_suggestion" ? "AI suggestion" : p.source === "coach_approved" ? "Coach-approved" : "My plan"}</Badge><Badge>{p.period}</Badge><span className="text-xs text-slate-400">{done}/{p.items.length} done</span></div></div>
        <div className="flex gap-1"><Button size="sm" variant="ghost" onClick={() => (edit ? save() : setEdit(true))} data-testid={`plan-edit-${p.id}`}>{edit ? "Save" : "Edit"}</Button>
          <Button size="sm" variant="ghost" onClick={async () => { await api.delete(`/training/plans/${p.id}`); reload(); }} data-testid={`plan-delete-${p.id}`}><Trash2 size={14} /></Button></div></div>
      <div className="h-1.5 bg-white/10 rounded mb-4"><div className="h-full bg-[#10B981] rounded" style={{ width: `${p.items.length ? (done / p.items.length) * 100 : 0}%` }} /></div>
      {edit ? <div className="space-y-2">{items.map((it, i) => <div key={it.id || i} className="grid grid-cols-12 gap-2"><Input className="col-span-3" value={it.day} onChange={(e) => setItems(items.map((x, j) => j === i ? { ...x, day: e.target.value } : x))} aria-label="Day" />
        <Input className="col-span-5" value={it.drill} onChange={(e) => setItems(items.map((x, j) => j === i ? { ...x, drill: e.target.value } : x))} aria-label="Drill" />
        <Input className="col-span-3" value={it.notes} placeholder="Notes" onChange={(e) => setItems(items.map((x, j) => j === i ? { ...x, notes: e.target.value } : x))} aria-label="Notes" />
        <Button size="icon" variant="ghost" className="col-span-1" onClick={() => setItems(items.filter((_, j) => j !== i))}><Trash2 size={14} /></Button></div>)}
        <Button size="sm" variant="secondary" onClick={() => setItems([...items, { day: "Day 1", drill: "", how_to: "", duration_min: 20, sets_reps: "", notes: "" }])}>Add drill</Button></div> :
        days.map((d) => <div key={d} className="mb-3"><div className="eyebrow mb-1">{d}</div>{p.items.filter((i) => i.day === d).map((it) => <label key={it.id} className="flex gap-3 items-start py-1.5 cursor-pointer">
          <Checkbox checked={it.completed} onCheckedChange={() => toggle(it)} data-testid={`item-check-${it.id}`} /><div><div className={`text-sm ${it.completed ? "line-through text-slate-500" : ""}`}>{it.drill} <span className="text-xs text-slate-500">{it.sets_reps} · {it.duration_min}m</span></div>{it.how_to && <p className="text-xs text-slate-400">{it.how_to}</p>}{it.notes && <p className="text-xs text-[#00B4D8]">Note: {it.notes}</p>}</div></label>)}</div>)}
    </Card>
  );
};

export const Training = () => {
  const [plans, setPlans] = useState(null);
  const [drills, setDrills] = useState([]);
  const [g, setG] = useState({ period: "weekly", days_per_week: 4, minutes_per_session: 45 });
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => api.get("/training/plans").then(({ data }) => setPlans(data)), []);
  useEffect(() => { load(); api.get("/drills").then(({ data }) => setDrills(data)); }, [load]);
  const gen = async () => { setBusy(true); try { await api.post("/training/plans/generate", g); load(); toast.success("AI plan created — review and edit it."); } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); } };
  const blank = async () => { await api.post("/training/plans", { title: "My practice plan", period: "weekly", items: [{ day: "Day 1", drill: "Shadow batting in mirror", duration_min: 15, sets_reps: "3 x 10" }] }); load(); };
  return (
    <div><Seo title="Training planner" path="/app/training" noindex />
      <PageHeader eyebrow="Training" title="Training planner" desc="AI suggestions are clearly labelled; plans edited by your coach show as coach-approved." />
      <Tabs defaultValue="plans"><TabsList><TabsTrigger value="plans" data-testid="tab-plans">My plans</TabsTrigger><TabsTrigger value="library" data-testid="tab-library">Drill library</TabsTrigger></TabsList>
        <TabsContent value="plans" className="mt-6 space-y-5">
          <Card className="flex flex-wrap gap-3 items-end"><div><div className="text-xs text-slate-400 mb-1">Period</div><Select value={g.period} onValueChange={(v) => setG({ ...g, period: v })}><SelectTrigger className="w-32" data-testid="gen-period"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="weekly">Weekly</SelectItem><SelectItem value="monthly">Monthly</SelectItem></SelectContent></Select></div>
            <div><div className="text-xs text-slate-400 mb-1">Sessions / week</div><Input type="number" min={1} max={7} className="w-28" value={g.days_per_week} onChange={(e) => setG({ ...g, days_per_week: +e.target.value })} data-testid="gen-days" /></div>
            <div><div className="text-xs text-slate-400 mb-1">Minutes / session</div><Input type="number" min={15} max={180} className="w-28" value={g.minutes_per_session} onChange={(e) => setG({ ...g, minutes_per_session: +e.target.value })} data-testid="gen-minutes" /></div>
            <Button onClick={gen} disabled={busy} data-testid="gen-plan-btn"><Sparkles size={16} className="mr-1" />{busy ? "Generating…" : "Generate AI plan"}</Button><Button variant="secondary" onClick={blank} data-testid="blank-plan-btn">Blank plan</Button></Card>
          {plans === null ? "Loading…" : plans.length ? plans.map((p) => <PlanCard key={p.id} p={p} reload={load} />) : <Empty title="No plans yet" desc="Generate one from your reports or start a blank plan." testid="plans-empty" />}
        </TabsContent>
        <TabsContent value="library" className="mt-6 grid md:grid-cols-2 gap-4">{drills.map((d) => <Card key={d.id}><div className="flex gap-2 mb-1"><Badge tone="teal">{d.type}</Badge><Badge>{d.area.replace(/_/g, " ")}</Badge></div><h3 className="font-semibold">{d.name}</h3><p className="text-sm text-slate-400 mt-1">{d.how_to}</p><p className="text-xs text-slate-500 mt-1">{d.sets_reps}</p></Card>)}</TabsContent>
      </Tabs>
    </div>
  );
};

export const Passport = () => {
  const { flags } = useAuth();
  const [p, setP] = useState(null);
  const [ch, setCh] = useState(null);
  const [shares, setShares] = useState([]);
  const [newLink, setNewLink] = useState(null);
  const [lb, setLb] = useState(null);
  const loadShares = () => api.get("/passport/shares").then(({ data }) => setShares(data));
  useEffect(() => { api.get("/passport").then(({ data }) => setP(data)); api.get("/challenges").then(({ data }) => setCh(data)); loadShares(); if (flags?.leaderboard) api.get("/leaderboard").then(({ data }) => setLb(data)).catch(() => {}); }, [flags]);
  const share = async () => { const { data } = await api.post("/passport/share", { days: 7 }); setNewLink(`${SITE.includes("cricanalyze") ? window.location.origin : ""}/passport/${data.token}`); loadShares(); };
  return (
    <div><Seo title="Passport" path="/app/passport" noindex />
      <PageHeader eyebrow="Development" title="Passport & challenges" desc="A player-controlled summary of verified analyses, plans and milestones." />
      <div className="grid lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">{p ? <PassportView p={p} /> : "Loading…"}</div>
        <div className="space-y-5">
          <Card><h3 className="font-semibold mb-2 flex items-center gap-2"><Share2 size={16} />Share passport</h3><p className="text-xs text-slate-400 mb-3">Creates a revocable link that expires in 7 days. Shows first name only; coach feedback stays private.</p>
            <Button size="sm" onClick={share} data-testid="share-passport-btn">Create link</Button>
            {newLink && <Input readOnly value={newLink} className="mt-3 text-xs" onFocus={(e) => e.target.select()} data-testid="share-link-output" />}
            {shares.map((s) => <div key={s.id} className="flex justify-between text-xs mt-2"><span>Expires {fmtDate(s.expires_at)}</span><button className="text-red-300" onClick={async () => { await api.delete(`/passport/shares/${s.id}`); loadShares(); }} data-testid={`revoke-share-${s.id}`}>Revoke</button></div>)}</Card>
          <Card data-testid="challenges-card"><div className="flex justify-between mb-3"><h3 className="font-semibold flex items-center gap-2"><Award size={16} />Challenges</h3>{ch && <span className="text-sm flex items-center gap-1 text-amber-300" data-testid="streak"><Flame size={14} />{ch.streak_days}-day streak</span>}</div>
            {ch?.challenges.map((c) => <div key={c.id} className="mb-3"><div className="flex justify-between text-sm"><span className={c.completed ? "text-[#10B981]" : ""}>{c.title}</span><span className="text-xs text-slate-400">{Math.min(c.value, c.target)}/{c.target}</span></div><p className="text-xs text-slate-500">{c.desc}</p>
              <div className="h-1 bg-white/10 rounded mt-1"><div className="h-full bg-[#10B981] rounded" style={{ width: `${Math.min(100, (c.value / c.target) * 100)}%` }} /></div></div>)}
            <p className="text-[11px] text-slate-500">Progress counts only verified actions (completed analyses, reviewed reports, checked-off drills).</p></Card>
          {lb && <Card><h3 className="font-semibold mb-2">Leaderboard (opt-in)</h3>{lb.map((r, i) => <div key={i} className="text-sm flex justify-between"><span>{i + 1}. {r.name}</span><span className="text-slate-400">{r.badges} badges</span></div>)}</Card>}
        </div>
      </div>
    </div>
  );
};
