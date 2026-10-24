import { useEffect, useState, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Building2, Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api, errMsg, fmtDate, inr, download, media } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { PageHeader, Empty, Card, Badge, statusTone, Seo } from "@/components/Common";
import { PlanGrid } from "@/pages/Public";
import { Otp } from "@/pages/Auth";

export const Academy = () => {
  const { user } = useAuth();
  const [sp, setSp] = useSearchParams();
  const [mine, setMine] = useState(null);
  const [sel, setSel] = useState(null);
  const [form, setForm] = useState({ name: "", city: "", description: "" });
  const load = useCallback(() => api.get("/academies/mine").then(({ data }) => { setMine(data); if (!sel && data.memberships[0]) setSel(data.memberships[0].academy_id); }), [sel]);
  useEffect(() => {
    const t = sp.get("invite");
    if (t) api.post("/academy-invites/accept", { token: t }).then(() => { toast.success("Invitation accepted."); setSp({}); load(); }).catch((e) => { toast.error(errMsg(e)); setSp({}); });
    else load();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const create = async (e) => { e.preventDefault(); try { const { data } = await api.post("/academies", form); setSel(data.id); load(); toast.success("Academy created."); } catch (err) { toast.error(errMsg(err)); } };
  if (!mine) return <p className="text-slate-400">Loading…</p>;
  const canCreate = ["coach", "academy_admin", "admin", "super_admin"].includes(user.role);
  return (
    <div><Seo title="Academy" path="/app/academy" noindex />
      <PageHeader eyebrow="Academy" title="Academy workspace" desc="Each academy's data is isolated. Coaches only see assigned players who have chosen to share reports." />
      {mine.invites.map((i) => <Card key={i.id} className="mb-4 flex justify-between items-center" data-testid={`invite-${i.id}`}><span className="text-sm">Invitation to <b>{i.academy_name}</b> as {i.role}</span>
        <Button size="sm" onClick={async () => { try { await api.post("/academy-invites/accept", { invite_id: i.id }); load(); toast.success("Joined."); } catch (e) { toast.error(errMsg(e)); } }} data-testid={`accept-invite-${i.id}`}>Accept</Button></Card>)}
      {mine.memberships.length > 0 && <div className="flex flex-wrap gap-2 mb-6">{mine.memberships.map((m) => <Button key={m.academy_id} size="sm" variant={sel === m.academy_id ? "default" : "secondary"} onClick={() => setSel(m.academy_id)} data-testid={`academy-tab-${m.academy_id}`}>{m.academy?.name} · {m.role}</Button>)}</div>}
      {sel && <AcademyView aid={sel} membership={mine.memberships.find((m) => m.academy_id === sel)} reload={load} />}
      {mine.memberships.length === 0 && !canCreate && <Empty icon={Building2} title="You're not in an academy" desc="Ask your academy to invite you by email. Invitations appear here." testid="academy-empty" />}
      {canCreate && <Card className="mt-8 max-w-xl"><h3 className="font-semibold mb-3">Create an academy</h3><form onSubmit={create} className="space-y-3" data-testid="create-academy-form">
        <Input placeholder="Academy name" required minLength={2} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="academy-name-input" />
        <Input placeholder="City" value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} data-testid="academy-city-input" />
        <Textarea placeholder="Short description" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
        <Button type="submit" data-testid="create-academy-btn">Create academy</Button></form></Card>}
    </div>
  );
};

const AcademyView = ({ aid, membership, reload }) => {
  const [d, setD] = useState(null);
  const [inv, setInv] = useState({ email: "", role: "player" });
  const [asg, setAsg] = useState({ coach_id: "", player_id: "" });
  const [player, setPlayer] = useState(null);
  const [fb, setFb] = useState("");
  const [group, setGroup] = useState("");
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [att, setAtt] = useState({});
  const role = membership?.role;
  const load = useCallback(() => { if (role !== "player") api.get(`/academies/${aid}/members`).then(({ data }) => setD(data)).catch(() => setD(null)); }, [aid, role]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (role !== "player") api.get(`/academies/${aid}/attendance`, { params: { date } }).then(({ data }) => setAtt(Object.fromEntries(data.map((x) => [x.player_id, x.status])))).catch(() => {}); }, [aid, date, role]);
  if (role === "player") return <Card data-testid="player-consent-card"><h3 className="font-semibold">{membership.academy?.name}</h3><p className="text-sm text-slate-400 mt-1 mb-4">Choose whether your academy admins and assigned coaches can view your analysis reports and videos.</p>
    <label className="flex items-center gap-3"><Switch checked={!!membership.share_reports} onCheckedChange={async (v) => { try { await api.patch(`/academies/${aid}/consent`, { share_reports: v }); reload(); toast.success(v ? "Sharing enabled." : "Sharing turned off."); } catch (e) { toast.error(e?.response?.data?.detail === "guardian_consent_required" ? "Guardian consent is required first (see New analysis)." : errMsg(e)); } }} data-testid="share-reports-switch" />Share my reports with this academy</label></Card>;
  if (!d) return <p className="text-slate-400">Loading…</p>;
  const players = d.members.filter((m) => m.role === "player");
  const coaches = d.members.filter((m) => m.role !== "player");
  const admin = d.my_role === "academy_admin";
  const openPlayer = async (m) => { setPlayer({ ...m, reports: null }); if (m.share_reports) { try { const { data } = await api.get(`/academies/${aid}/players/${m.user_id}/reports`); setPlayer({ ...m, reports: data }); } catch (e) { toast.error(errMsg(e)); } } };
  return (
    <div className="space-y-6">
      <div className="flex justify-end"><Button size="sm" variant="secondary" onClick={() => download(`/academies/${aid}/export.csv`, "academy-players.csv")} data-testid="academy-export-btn"><Download size={14} className="mr-1" />Export CSV</Button></div>
      {admin && <div className="grid md:grid-cols-2 gap-5">
        <Card><h3 className="font-semibold mb-3">Invite by email</h3><div className="flex gap-2"><Input type="email" placeholder="email@example.com" value={inv.email} onChange={(e) => setInv({ ...inv, email: e.target.value })} data-testid="invite-email-input" />
          <Select value={inv.role} onValueChange={(v) => setInv({ ...inv, role: v })}><SelectTrigger className="w-28" data-testid="invite-role-select"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="player">Player</SelectItem><SelectItem value="coach">Coach</SelectItem></SelectContent></Select>
          <Button onClick={async () => { try { const { data } = await api.post(`/academies/${aid}/invites`, inv); toast[data.email_sent ? "success" : "warning"](data.email_sent ? "Invitation sent." : "Invite saved, but the email couldn't be sent."); setInv({ ...inv, email: "" }); load(); } catch (e) { toast.error(errMsg(e)); } }} data-testid="invite-send-btn">Invite</Button></div>
          {d.invites.map((i) => <p key={i.id} className="text-xs text-slate-400 mt-2">Pending: {i.email} ({i.role})</p>)}</Card>
        <Card><h3 className="font-semibold mb-3">Assign coach to player</h3><div className="flex flex-wrap gap-2">
          <Select value={asg.coach_id} onValueChange={(v) => setAsg({ ...asg, coach_id: v })}><SelectTrigger className="w-40" data-testid="assign-coach-select"><SelectValue placeholder="Coach" /></SelectTrigger><SelectContent>{coaches.map((c) => <SelectItem key={c.user_id} value={c.user_id}>{c.full_name}</SelectItem>)}</SelectContent></Select>
          <Select value={asg.player_id} onValueChange={(v) => setAsg({ ...asg, player_id: v })}><SelectTrigger className="w-40" data-testid="assign-player-select"><SelectValue placeholder="Player" /></SelectTrigger><SelectContent>{players.map((c) => <SelectItem key={c.user_id} value={c.user_id}>{c.full_name}</SelectItem>)}</SelectContent></Select>
          <Button onClick={async () => { try { await api.post(`/academies/${aid}/assignments`, asg); load(); toast.success("Assigned."); } catch (e) { toast.error(errMsg(e)); } }} disabled={!asg.coach_id || !asg.player_id} data-testid="assign-btn">Assign</Button></div>
          <div className="flex gap-2 mt-4"><Input placeholder="New batch / group name" value={group} onChange={(e) => setGroup(e.target.value)} data-testid="group-name-input" /><Button variant="secondary" onClick={async () => { await api.post(`/academies/${aid}/groups`, { name: group, player_ids: [] }); setGroup(""); load(); }} disabled={!group} data-testid="group-create-btn">Add group</Button></div>
          <div className="flex flex-wrap gap-1 mt-2">{d.groups.map((g) => <Badge key={g.id}>{g.name} ({g.player_ids.length})</Badge>)}</div></Card></div>}
      <Card className="overflow-x-auto"><div className="flex justify-between items-center mb-3"><h3 className="font-semibold">Players ({players.length})</h3><div className="flex items-center gap-2 text-xs">Attendance date <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="w-40 h-8" data-testid="attendance-date" /></div></div>
        <table className="w-full text-sm min-w-[640px]"><thead><tr className="text-left text-slate-400"><th className="py-2">Name</th><th>Role</th><th>Sharing</th><th>Analyses</th><th>Coaches</th><th>Attendance</th><th /></tr></thead>
          <tbody>{players.map((m) => <tr key={m.user_id} className="border-t border-white/5" data-testid={`player-row-${m.user_id}`}><td className="py-2">{m.full_name}</td><td>{m.playing_role || "—"}</td>
            <td><Badge tone={m.share_reports ? "green" : "slate"}>{m.share_reports ? "Shared" : "Private"}</Badge></td><td>{m.share_reports ? m.analyses : "—"}</td>
            <td className="text-xs">{(m.coaches || []).map((c) => coaches.find((x) => x.user_id === c)?.full_name).filter(Boolean).join(", ") || "—"}</td>
            <td><Select value={att[m.user_id] || ""} onValueChange={async (v) => { await api.post(`/academies/${aid}/attendance`, { player_id: m.user_id, date, status: v }); setAtt({ ...att, [m.user_id]: v }); }}><SelectTrigger className="h-8 w-28" data-testid={`attendance-${m.user_id}`}><SelectValue placeholder="—" /></SelectTrigger><SelectContent><SelectItem value="present">Present</SelectItem><SelectItem value="absent">Absent</SelectItem><SelectItem value="excused">Excused</SelectItem></SelectContent></Select></td>
            <td><Button size="sm" variant="ghost" onClick={() => openPlayer(m)} data-testid={`open-player-${m.user_id}`}>View</Button></td></tr>)}</tbody></table>
        {!players.length && <p className="text-sm text-slate-500 py-4">No players yet{admin ? " — invite some above." : " assigned to you."}</p>}</Card>
      {player && <Card data-testid="player-detail"><h3 className="font-semibold">{player.full_name}</h3>
        {!player.share_reports ? <p className="text-sm text-slate-400 mt-2">This player hasn't consented to share reports.</p> : !player.reports ? "Loading…" :
          <div className="mt-3 space-y-2">{player.reports.map((j) => <a key={j.id} href={`/app/analyses/${j.id}`} className="block text-sm hover:text-[#00B4D8]"><Badge tone="teal">{j.analysis_type}</Badge> {fmtDate(j.created_at)}</a>)}{!player.reports.length && <p className="text-sm text-slate-500">No completed analyses.</p>}</div>}
        <div className="flex gap-2 mt-4"><Input placeholder="Coach feedback for the player's passport" value={fb} onChange={(e) => setFb(e.target.value)} data-testid="feedback-input" /><Button onClick={async () => { try { await api.post(`/academies/${aid}/players/${player.user_id}/feedback`, { text: fb }); setFb(""); toast.success("Feedback saved."); } catch (e) { toast.error(errMsg(e)); } }} disabled={fb.length < 2} data-testid="feedback-save-btn">Save</Button></div></Card>}
    </div>
  );
};

const loadRzp = () => new Promise((res) => { if (window.Razorpay) return res(true); const s = document.createElement("script"); s.src = "https://checkout.razorpay.com/v1/checkout.js"; s.onload = () => res(true); s.onerror = () => res(false); document.body.appendChild(s); });

export const Billing = () => {
  const { refresh } = useAuth();
  const [sp] = useSearchParams();
  const [plans, setPlans] = useState([]);
  const [planId, setPlanId] = useState(sp.get("plan") || "");
  const [coupon, setCoupon] = useState("");
  const [quote, setQuote] = useState(null);
  const [subs, setSubs] = useState([]);
  const [pays, setPays] = useState([]);
  const [ledger, setLedger] = useState([]);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => { api.get("/billing/subscriptions").then(({ data }) => setSubs(data)); api.get("/billing/payments").then(({ data }) => setPays(data)); api.get("/billing/ledger").then(({ data }) => setLedger(data)); }, []);
  useEffect(() => { api.get("/plans").then(({ data }) => setPlans(data)); load(); }, [load]);
  useEffect(() => { setQuote(null); }, [planId, coupon]);
  const checkCoupon = async () => { try { setQuote((await api.post("/billing/quote", { plan_id: planId, coupon })).data); } catch (e) { toast.error(errMsg(e)); } };
  const pay = async () => {
    setBusy(true);
    try {
      const { data: o } = await api.post("/billing/order", { plan_id: planId, coupon: coupon || null });
      if (!(await loadRzp())) throw new Error("Couldn't load Razorpay checkout.");
      const rz = new window.Razorpay({ key: o.key_id, order_id: o.order_id, amount: o.amount, currency: o.currency, name: o.name, description: o.description, prefill: o.prefill, theme: { color: "#10B981" },
        handler: async (r) => { try { await api.post("/billing/verify", r); toast.success("Payment verified. Plan activated!"); await refresh(); load(); } catch (e) { toast.error(errMsg(e)); load(); } finally { setBusy(false); } },
        modal: { ondismiss: () => setBusy(false) } });
      rz.on("payment.failed", () => toast.error("Payment failed. No plan was activated."));
      rz.open();
    } catch (e) { toast.error(errMsg(e)); setBusy(false); }
  };
  const plan = plans.find((p) => p.id === planId);
  return (
    <div><Seo title="Billing" path="/app/billing" noindex />
      <PageHeader eyebrow="Billing" title="Plans & billing" desc="Plans activate only after Razorpay confirms the payment on our server." />
      {plan ? <Card className="mb-8 max-w-xl border-[#10B981]/30" data-testid="checkout-card"><h3 className="font-semibold">{plan.name} — {inr(quote?.price_inr ?? plan.price_inr)}{quote?.coupon && <span className="text-sm text-slate-400 line-through ml-2">{inr(plan.price_inr)}</span>}</h3>
        <p className="text-sm text-slate-400">{plan.credits} credits · {plan.period_days} days</p>
        <div className="flex gap-2 mt-4"><Input placeholder="Coupon code" value={coupon} onChange={(e) => setCoupon(e.target.value.toUpperCase())} data-testid="coupon-input" /><Button variant="secondary" onClick={checkCoupon} disabled={!coupon} data-testid="coupon-apply-btn">Apply</Button></div>
        <div className="flex gap-2 mt-4"><Button onClick={pay} disabled={busy} className="bg-[#10B981] hover:bg-[#059669] text-[#0B132B]" data-testid="pay-btn">{busy ? "Processing…" : "Pay with Razorpay"}</Button><Button variant="ghost" onClick={() => setPlanId("")}>Change plan</Button></div></Card> :
        <div className="mb-10"><div className="grid md:grid-cols-3 gap-3 mb-4">{plans.map((p) => <Button key={p.id} variant="secondary" onClick={() => setPlanId(p.id)} data-testid={`select-plan-${p.slug}`}>Select {p.name} · {inr(p.price_inr)}</Button>)}</div><PlanGrid /></div>}
      <div className="grid lg:grid-cols-2 gap-6">
        <Card><h3 className="font-semibold mb-3">Subscriptions</h3>{subs.length ? subs.map((s) => <div key={s.id} className="flex justify-between items-center text-sm border-b border-white/5 py-2" data-testid={`sub-${s.id}`}><div><b>{s.plan_name}</b> <Badge tone={statusTone(s.status)}>{s.status}</Badge><div className="text-xs text-slate-400">{s.credits_remaining}/{s.credits_total} credits · until {fmtDate(s.expires_at)}{s.cancel_requested_at ? " · won't renew" : ""}</div></div>
          {s.status === "active" && !s.cancel_requested_at && <Button size="sm" variant="ghost" onClick={async () => { const { data } = await api.post(`/billing/subscriptions/${s.id}/cancel`); toast.success(data.message); load(); }} data-testid={`cancel-sub-${s.id}`}>Cancel renewal</Button>}</div>) : <p className="text-sm text-slate-500">No subscriptions yet.</p>}</Card>
        <Card><h3 className="font-semibold mb-3">Payments</h3>{pays.length ? pays.map((p) => <div key={p.id} className="flex justify-between text-sm border-b border-white/5 py-2"><span>{p.plan_name} · {fmtDate(p.created_at)}{p.payment_id && <span className="block text-xs font-mono text-slate-500">{p.payment_id}</span>}</span><span>{inr(p.amount_inr)} <Badge tone={statusTone(p.status)}>{p.status}</Badge></span></div>) : <p className="text-sm text-slate-500">No payments yet.</p>}</Card>
        <Card className="lg:col-span-2"><h3 className="font-semibold mb-3">Credit ledger</h3><div className="max-h-64 overflow-y-auto">{ledger.map((l) => <div key={l.id} className="flex justify-between text-xs border-b border-white/5 py-1.5"><span>{fmtDate(l.created_at)} · {l.reason}</span><span className={l.delta > 0 ? "text-[#10B981]" : l.delta < 0 ? "text-red-300" : ""}>{l.delta > 0 ? "+" : ""}{l.delta}</span></div>)}{!ledger.length && <p className="text-sm text-slate-500">No credit activity.</p>}</div></Card>
      </div>
    </div>
  );
};

const StepUp = ({ onDone }) => {
  const [sent, setSent] = useState(false);
  const [code, setCode] = useState("");
  return (<div className="mt-3 p-3 rounded-lg bg-white/5" data-testid="step-up-box"><p className="text-xs text-slate-400 mb-2">For your security, confirm with a code sent to your email.</p>
    {!sent ? <Button size="sm" onClick={async () => { try { await api.post("/auth/step-up/request"); setSent(true); } catch (e) { toast.error(errMsg(e)); } }} data-testid="step-up-send-btn">Send code</Button> :
      <div className="flex gap-2 items-center"><Otp value={code} onChange={setCode} testid="step-up-otp" /><Button size="sm" disabled={code.length !== 6} onClick={async () => { try { await api.post("/auth/step-up/verify", { code }); onDone(); } catch (e) { toast.error(errMsg(e)); } }} data-testid="step-up-verify-btn">Confirm</Button></div>}</div>);
};

export const Settings = () => {
  const { user, refresh, logout } = useAuth();
  const [f, setF] = useState({ full_name: user.full_name, ...(user.profile || {}), dob: user.dob || "" });
  const [privacy, setPrivacy] = useState(user.privacy || {});
  const [pw, setPw] = useState({ current_password: "", new_password: "" });
  const [sessions, setSessions] = useState([]);
  const [stepFor, setStepFor] = useState(null);
  const [newEmail, setNewEmail] = useState("");
  const [emailCode, setEmailCode] = useState("");
  const [emailSent, setEmailSent] = useState(false);
  const [avatar, setAvatar] = useState(null);
  const loadS = () => api.get("/auth/sessions").then(({ data }) => setSessions(data));
  useEffect(() => { loadS(); api.get("/account/status").then(({ data }) => setAvatar(data.avatar_url)); }, []);
  const save = async () => { const { full_name, ...profile } = f; try { await api.patch("/account/profile", { full_name, profile, privacy }); await refresh(); toast.success("Saved."); } catch (e) { toast.error(errMsg(e)); } };
  const fields = [["playing_role", "Playing role", ["Batter", "Bowler", "All-rounder", "Wicket-keeper"]], ["batting_style", "Batting style", ["Right-handed", "Left-handed"]],
    ["bowling_style", "Bowling style", ["Right-arm fast", "Right-arm medium", "Right-arm off-spin", "Right-arm leg-spin", "Left-arm fast", "Left-arm medium", "Left-arm orthodox", "Left-arm wrist-spin", "Doesn't bowl"]],
    ["experience_level", "Experience", ["Beginner", "Club", "School / academy", "District", "State+"]], ["preferred_format", "Preferred format", ["T20", "One-day", "Multi-day", "Indoor"]]];
  const doDelete = async () => { try { await api.delete("/account"); await logout(); window.location.href = "/"; } catch (e) { if (e?.response?.data?.detail === "step_up_required") setStepFor("delete"); else toast.error(errMsg(e)); } };
  const reqEmail = async () => { try { await api.post("/auth/change-email/request", { new_email: newEmail }); setEmailSent(true); toast.success("Code sent to the new email."); } catch (e) { if (e?.response?.data?.detail === "step_up_required") setStepFor("email"); else toast.error(errMsg(e)); } };
  return (
    <div><Seo title="Settings" path="/app/settings" noindex />
      <PageHeader eyebrow="Account" title="Settings" />
      <div className="grid lg:grid-cols-2 gap-6">
        <Card><h3 className="font-semibold mb-4">Profile</h3><div className="flex items-center gap-4 mb-4">{avatar ? <img src={media(avatar)} alt="Profile" className="w-14 h-14 rounded-full object-cover" /> : <div className="w-14 h-14 rounded-full bg-white/10" />}
          <label className="text-sm text-[#00B4D8] cursor-pointer">Upload photo<input type="file" accept="image/png,image/jpeg,image/webp" className="hidden" data-testid="avatar-input" onChange={async (e) => { const fd = new FormData(); fd.append("file", e.target.files[0]); try { await api.post("/account/avatar", fd); const { data } = await api.get("/account/status"); setAvatar(data.avatar_url); } catch (er) { toast.error(errMsg(er)); } }} /></label></div>
          <div className="grid sm:grid-cols-2 gap-3">
            <div className="sm:col-span-2"><Label>Full name</Label><Input value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} data-testid="settings-name" /></div>
            <div><Label>Phone (optional)</Label><Input value={f.phone || ""} onChange={(e) => setF({ ...f, phone: e.target.value })} data-testid="settings-phone" /></div>
            <div><Label>Date of birth</Label><Input type="date" value={f.dob || ""} onChange={(e) => setF({ ...f, dob: e.target.value })} data-testid="settings-dob" /></div>
            {fields.map(([k, l, opts]) => <div key={k}><Label>{l}</Label><Select value={f[k] || ""} onValueChange={(v) => setF({ ...f, [k]: v })}><SelectTrigger data-testid={`settings-${k}`}><SelectValue placeholder="Select" /></SelectTrigger><SelectContent>{opts.map((o) => <SelectItem key={o} value={o}>{o}</SelectItem>)}</SelectContent></Select></div>)}
            <div className="sm:col-span-2"><Label>Coaching goals</Label><Textarea value={f.coaching_goals || ""} onChange={(e) => setF({ ...f, coaching_goals: e.target.value })} data-testid="settings-goals" /></div></div>
          <Button className="mt-4" onClick={save} data-testid="settings-save-btn">Save profile</Button></Card>
        <div className="space-y-6">
          <Card><h3 className="font-semibold mb-3">Privacy & sign-in</h3>
            {[["leaderboard_opt_in", "Show me on the opt-in leaderboard (first name only)"], ["product_emails", "Receive product update emails"]].map(([k, l]) => <label key={k} className="flex justify-between items-center py-2 text-sm">{l}<Switch checked={!!privacy[k]} onCheckedChange={(v) => setPrivacy({ ...privacy, [k]: v })} data-testid={`privacy-${k}`} /></label>)}
            <label className="flex justify-between items-center py-2 text-sm">Require an email code every time I sign in<Switch checked={!!user.otp_login_required} onCheckedChange={async (v) => { await api.patch("/account/profile", { otp_login_required: v }); refresh(); }} data-testid="otp-required-switch" /></label>
            <Button size="sm" variant="secondary" onClick={save} className="mt-2">Save privacy</Button>
            {user.guardian && <p className="text-xs text-slate-400 mt-3">Guardian: {user.guardian.name} ({user.guardian.email}) · {user.guardian.consent_at ? `consented ${fmtDate(user.guardian.consent_at)}` : "pending"}</p>}</Card>
          <Card><h3 className="font-semibold mb-3">Password</h3><div className="space-y-2"><Input type="password" placeholder="Current password" value={pw.current_password} onChange={(e) => setPw({ ...pw, current_password: e.target.value })} data-testid="current-password" />
            <Input type="password" placeholder="New password" value={pw.new_password} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} data-testid="new-password" />
            <Button size="sm" onClick={async () => { try { await api.post("/auth/change-password", pw); toast.success("Password changed. Other sessions signed out."); setPw({ current_password: "", new_password: "" }); loadS(); } catch (e) { toast.error(errMsg(e)); } }} data-testid="change-password-btn">Change password</Button></div></Card>
          <Card><h3 className="font-semibold mb-3">Email address</h3><p className="text-sm text-slate-400 mb-2">Current: {user.email}</p>
            {!emailSent ? <div className="flex gap-2"><Input type="email" placeholder="New email" value={newEmail} onChange={(e) => setNewEmail(e.target.value)} data-testid="new-email-input" /><Button size="sm" onClick={reqEmail} disabled={!newEmail} data-testid="change-email-btn">Change</Button></div> :
              <div className="flex gap-2 items-center"><Otp value={emailCode} onChange={setEmailCode} testid="email-change-otp" /><Button size="sm" onClick={async () => { try { await api.post("/auth/change-email/confirm", { code: emailCode }); toast.success("Email updated."); setEmailSent(false); refresh(); } catch (e) { toast.error(errMsg(e)); } }} data-testid="confirm-email-btn">Confirm</Button></div>}
            {stepFor === "email" && <StepUp onDone={() => { setStepFor(null); reqEmail(); }} />}</Card>
          <Card><div className="flex justify-between mb-3"><h3 className="font-semibold">Active sessions</h3><Button size="sm" variant="ghost" onClick={async () => { await api.post("/auth/sessions/revoke-others"); loadS(); }} data-testid="revoke-others-btn">Sign out others</Button></div>
            {sessions.map((s) => <div key={s.id} className="flex justify-between text-xs py-1.5 border-b border-white/5"><span className="truncate max-w-[70%]">{s.ua || "Unknown device"} · {fmtDate(s.created_at)}{s.current && <Badge tone="green">this device</Badge>}</span>{!s.current && <button className="text-red-300" onClick={async () => { await api.delete(`/auth/sessions/${s.id}`); loadS(); }}>Revoke</button>}</div>)}</Card>
          <Card className="border-red-500/20"><h3 className="font-semibold mb-2">Your data</h3><div className="flex flex-wrap gap-2"><Button size="sm" variant="secondary" onClick={() => download("/account/export", "cricanalyze-export.json")} data-testid="export-data-btn">Export my data</Button>
            <Button size="sm" variant="destructive" onClick={() => { if (window.confirm("Permanently delete your account and videos? This can't be undone.")) doDelete(); }} data-testid="delete-account-btn">Delete account</Button></div>
            {stepFor === "delete" && <StepUp onDone={() => { setStepFor(null); doDelete(); }} />}</Card>
        </div>
      </div>
    </div>
  );
};
