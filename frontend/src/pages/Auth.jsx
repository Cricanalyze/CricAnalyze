import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { InputOTP, InputOTPGroup, InputOTPSlot } from "@/components/ui/input-otp";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { api, errMsg } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Logo, Seo } from "@/components/Common";

const Shell = ({ title, sub, children, path }) => (
  <div className="min-h-screen grid lg:grid-cols-2">
    <Seo title={title} path={path} noindex />
    <div className="hidden lg:block relative bg-cover bg-center" style={{ backgroundImage: "url(/images/hero.jpg)" }}>
      <div className="absolute inset-0 bg-gradient-to-t from-[#070D1E] via-[#070D1E]/60 to-transparent" />
      <div className="absolute bottom-12 left-12 right-12"><div className="eyebrow mb-3">AI cricket analysis</div><p className="text-3xl font-display font-bold">Understand your technique, one video at a time.</p></div>
    </div>
    <div className="flex items-center justify-center p-6 grid-bg">
      <div className="w-full max-w-md glass rounded-2xl p-8 fade-up">
        <Logo className="mb-8" />
        <h1 className="text-2xl font-bold mb-1">{title}</h1>
        {sub && <p className="text-slate-400 text-sm mb-6">{sub}</p>}
        {children}
      </div>
    </div>
  </div>
);

const Field = ({ id, label, ...p }) => (
  <div className="space-y-1.5"><Label htmlFor={id}>{label}</Label><Input id={id} data-testid={`${id}-input`} {...p} /></div>
);

export const Otp = ({ value, onChange, testid = "otp-input" }) => (
  <InputOTP maxLength={6} value={value} onChange={onChange} data-testid={testid} inputMode="numeric">
    <InputOTPGroup>{[0, 1, 2, 3, 4, 5].map((i) => <InputOTPSlot key={i} index={i} className="w-11 h-12 text-lg" />)}</InputOTPGroup>
  </InputOTP>
);

const useNext = () => {
  const [sp] = useSearchParams();
  const n = sp.get("next");
  return n && n.startsWith("/") && !n.startsWith("//") ? n : "/app";
};

export const Login = () => {
  const [f, setF] = useState({ email: "", password: "" });
  const [mode, setMode] = useState("password");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const { refresh } = useAuth();
  const nav = useNavigate();
  const next = useNext();
  const done = async () => { await refresh(); nav(next); };
  const submit = async (e) => {
    e.preventDefault(); setBusy(true);
    try {
      if (mode === "password") {
        const { data } = await api.post("/auth/login", f);
        if (data.otp_required) { setMode("otp-verify"); toast.info("Enter the code we emailed you."); } else await done();
      } else if (mode === "otp") {
        await api.post("/auth/login/otp/request", { email: f.email }); setMode("otp-verify"); toast.success("If the account exists, a code is on its way.");
      } else {
        await api.post("/auth/login/otp/verify", { email: f.email, code }); await done();
      }
    } catch (err) {
      if (err?.response?.data?.detail === "email_unverified") { toast.info("Please verify your email first. We sent a new code."); nav(`/verify-email?email=${encodeURIComponent(f.email)}`); }
      else toast.error(errMsg(err));
    } finally { setBusy(false); }
  };
  return (
    <Shell title="Sign in" sub="Welcome back to CricAnalyze." path="/login">
      <form onSubmit={submit} className="space-y-4" data-testid="login-form">
        <Field id="login-email" label="Email" type="email" required autoComplete="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} disabled={mode === "otp-verify"} />
        {mode === "password" && <Field id="login-password" label="Password" type="password" required autoComplete="current-password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />}
        {mode === "otp-verify" && <div className="space-y-2"><Label>6-digit code</Label><Otp value={code} onChange={setCode} /></div>}
        <Button type="submit" className="w-full bg-[#10B981] hover:bg-[#059669] text-[#0B132B]" disabled={busy} data-testid="login-submit-btn">
          {busy ? "Please wait…" : mode === "password" ? "Sign in" : mode === "otp" ? "Email me a code" : "Verify & sign in"}</Button>
      </form>
      <div className="flex justify-between text-sm mt-5 text-slate-400">
        <button className="hover:text-white" onClick={() => { setMode(mode === "password" ? "otp" : "password"); setCode(""); }} data-testid="toggle-otp-login">{mode === "password" ? "Sign in with email code" : "Use password instead"}</button>
        <Link to="/forgot-password" className="hover:text-white" data-testid="forgot-link">Forgot password?</Link>
      </div>
      <p className="text-sm text-slate-400 mt-6">New here? <Link to="/signup" className="text-[#10B981]" data-testid="to-signup-link">Create an account</Link></p>
    </Shell>
  );
};

const ROLES = [["player", "Player"], ["parent", "Parent / guardian"], ["coach", "Coach"], ["academy_admin", "Academy"]];

export const Signup = () => {
  const [f, setF] = useState({ full_name: "", email: "", password: "", role: "player", accept_terms: false });
  const [busy, setBusy] = useState(false);
  const nav = useNavigate();
  const submit = async (e) => {
    e.preventDefault(); setBusy(true);
    try { const { data } = await api.post("/auth/signup", f); toast.success(data.message); nav(`/verify-email?email=${encodeURIComponent(f.email)}`); }
    catch (err) { toast.error(errMsg(err)); } finally { setBusy(false); }
  };
  return (
    <Shell title="Create your account" sub="Verify your email with a one-time code to get started." path="/signup">
      <form onSubmit={submit} className="space-y-4" data-testid="signup-form">
        <Field id="signup-name" label="Full name" required minLength={2} value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} />
        <Field id="signup-email" label="Email" type="email" required value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />
        <Field id="signup-password" label="Password (8+ characters, a letter and a number)" type="password" required minLength={8} autoComplete="new-password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
        <div className="space-y-1.5"><Label>I am a</Label><div className="grid grid-cols-2 gap-2">
          {ROLES.map(([v, l]) => <button type="button" key={v} onClick={() => setF({ ...f, role: v })} data-testid={`signup-role-${v}`}
            className={`text-sm py-2 rounded-lg border transition-colors ${f.role === v ? "border-[#10B981] bg-[#10B981]/10" : "border-white/10 hover:border-white/30"}`}>{l}</button>)}</div></div>
        <label className="flex gap-2 items-start text-sm text-slate-300"><Checkbox checked={f.accept_terms} onCheckedChange={(v) => setF({ ...f, accept_terms: !!v })} data-testid="signup-terms-checkbox" />
          <span>I agree to the <Link to="/terms-and-conditions" className="text-[#00B4D8]">Terms</Link> and <Link to="/privacy-policy" className="text-[#00B4D8]">Privacy Policy</Link>. Players under 18 need guardian consent before uploading videos.</span></label>
        <Button type="submit" className="w-full bg-[#10B981] hover:bg-[#059669] text-[#0B132B]" disabled={busy || !f.accept_terms} data-testid="signup-submit-btn">{busy ? "Sending code…" : "Create account"}</Button>
      </form>
      <p className="text-sm text-slate-400 mt-6">Already registered? <Link to="/login" className="text-[#10B981]">Sign in</Link></p>
    </Shell>
  );
};

export const VerifyEmail = () => {
  const [sp] = useSearchParams();
  const [email, setEmail] = useState(sp.get("email") || "");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const { refresh } = useAuth();
  const nav = useNavigate();
  const verify = async (e) => {
    e.preventDefault(); setBusy(true);
    try { await api.post("/auth/verify-email", { email, code }); await refresh(); toast.success("Email verified. Welcome!"); nav("/app"); }
    catch (err) { toast.error(errMsg(err)); } finally { setBusy(false); }
  };
  const resend = async () => { try { const { data } = await api.post("/auth/resend", { email, purpose: "verify_email" }); toast.success(data.message); } catch (err) { toast.error(errMsg(err)); } };
  return (
    <Shell title="Verify your email" sub="Enter the 6-digit code we sent. Codes expire after 5 minutes." path="/verify-email">
      <form onSubmit={verify} className="space-y-4" data-testid="verify-form">
        <Field id="verify-email" label="Email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        <div className="space-y-2"><Label>Verification code</Label><Otp value={code} onChange={setCode} /></div>
        <Button type="submit" className="w-full bg-[#10B981] hover:bg-[#059669] text-[#0B132B]" disabled={busy || code.length !== 6} data-testid="verify-submit-btn">Verify email</Button>
      </form>
      <button onClick={resend} className="text-sm text-[#00B4D8] mt-4" data-testid="resend-code-btn">Resend code</button>
    </Shell>
  );
};

export const ForgotPassword = () => {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const nav = useNavigate();
  const submit = async (e) => {
    e.preventDefault(); setBusy(true);
    try { const { data } = await api.post("/auth/forgot", { email }); toast.success(data.message); nav(`/reset-password?email=${encodeURIComponent(email)}`); }
    catch (err) { toast.error(errMsg(err)); } finally { setBusy(false); }
  };
  return (
    <Shell title="Forgot password" sub="We'll email you a code to reset it." path="/forgot-password">
      <form onSubmit={submit} className="space-y-4" data-testid="forgot-form">
        <Field id="forgot-email" label="Email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        <Button type="submit" className="w-full" disabled={busy} data-testid="forgot-submit-btn">Send reset code</Button>
      </form>
    </Shell>
  );
};

export const ResetPassword = () => {
  const [sp] = useSearchParams();
  const [email, setEmail] = useState(sp.get("email") || "");
  const [code, setCode] = useState("");
  const [token, setToken] = useState(null);
  const [pw, setPw] = useState("");
  const nav = useNavigate();
  const verify = async (e) => {
    e.preventDefault();
    try { const { data } = await api.post("/auth/reset/verify", { email, code }); setToken(data.reset_token); } catch (err) { toast.error(errMsg(err)); }
  };
  const reset = async (e) => {
    e.preventDefault();
    try { const { data } = await api.post("/auth/reset", { reset_token: token, new_password: pw }); toast.success(data.message); nav("/login"); } catch (err) { toast.error(errMsg(err)); }
  };
  return (
    <Shell title="Reset password" sub={token ? "Choose a new password." : "Enter the code from your email."} path="/reset-password">
      {!token ? <form onSubmit={verify} className="space-y-4" data-testid="reset-verify-form">
        <Field id="reset-email" label="Email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        <div className="space-y-2"><Label>Reset code</Label><Otp value={code} onChange={setCode} /></div>
        <Button type="submit" className="w-full" disabled={code.length !== 6} data-testid="reset-verify-btn">Continue</Button>
      </form> : <form onSubmit={reset} className="space-y-4" data-testid="reset-form">
        <Field id="reset-password" label="New password" type="password" required minLength={8} autoComplete="new-password" value={pw} onChange={(e) => setPw(e.target.value)} />
        <Button type="submit" className="w-full bg-[#10B981] text-[#0B132B]" data-testid="reset-submit-btn">Update password</Button>
      </form>}
    </Shell>
  );
};
