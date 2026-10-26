import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { ArrowRight, Video, Brain, FileText, LineChart, Users, ShieldCheck, Target, Layers, CheckCircle2, Lock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { api, errMsg, inr, SITE } from "@/lib/api";
import { Seo, Card, Badge } from "@/components/Common";
import { useAuth } from "@/context/AuthContext";
import { PostCard } from "@/pages/Blog";

const ORG = { "@context": "https://schema.org", "@type": "Organization", name: "CricAnalyze", legalName: "Buddy Innovations and Technologies Pvt Ltd", url: SITE, email: "noreply@cricanalyze.in" };
const WEBSITE = { "@context": "https://schema.org", "@type": "WebSite", name: "CricAnalyze", url: SITE };
const Section = ({ children, className = "" }) => <section className={`max-w-7xl mx-auto px-4 sm:px-6 py-16 md:py-24 ${className}`}>{children}</section>;
const H2 = ({ eyebrow, title, desc, h1 }) => { const H = h1 ? "h1" : "h2"; return (<div className="mb-12 max-w-2xl"><div className="eyebrow mb-3">{eyebrow}</div><H className="text-3xl sm:text-4xl font-bold">{title}</H>{desc && <p className="text-slate-400 mt-3">{desc}</p>}</div>); };

const FEATURES = [
  [Video, "Batting analysis", "Stance, head position, trigger, footwork, weight transfer, bat path and follow-through — assessed from frames of your video."],
  [Target, "Bowling analysis", "Run-up rhythm, gather, front-arm action, alignment, release and follow-through, with up to three camera angles on eligible plans."],
  [Brain, "Honest AI observations", "Every observation is tagged observed or inferred with a confidence level. Areas the camera can't show are marked not assessable."],
  [FileText, "Structured reports & PDF", "Strengths, areas to improve, timestamped evidence frames, linked drills and a weekly practice plan."],
  [LineChart, "Progress timeline", "Compare reports of the same type over time. Missing values stay missing — never shown as zero."],
  [Users, "Academy workspace", "Invite coaches and players, assign coaches, track attendance and share reports only with player consent."],
];

export const Home = () => {
  const [posts, setPosts] = useState([]);
  useEffect(() => { api.get("/blog/posts", { params: { limit: 3 } }).then(({ data }) => setPosts(data.posts)).catch(() => {}); }, []);
  return (
    <>
      <Seo title="CricAnalyze — AI Cricket Batting & Bowling Video Analysis" path="/" description="Upload a batting or bowling video and get an AI-assisted technique report with evidence frames, drills and a practice plan." jsonLd={[ORG, WEBSITE]} />
      <section className="relative overflow-hidden grid-bg">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 pt-16 pb-20 md:pt-24 grid lg:grid-cols-12 gap-12 items-center">
          <div className="lg:col-span-6 fade-up">
            <div className="eyebrow mb-5">AI cricket video analysis</div>
            <h1 className="text-4xl sm:text-5xl lg:text-6xl font-extrabold leading-[1.05]">See your technique <span className="text-[#10B981]">frame by frame.</span></h1>
            <p className="text-slate-300 mt-6 text-base sm:text-lg max-w-xl leading-relaxed">Upload a short batting or bowling clip. CricAnalyze reviews key frames, explains what it can see, flags what it can't, and turns it into drills you can practise this week.</p>
            <div className="flex flex-wrap gap-3 mt-8">
              <Button size="lg" asChild className="bg-[#10B981] hover:bg-[#059669] text-[#0B132B] rounded-full px-7" data-testid="hero-cta-btn"><Link to="/app/upload">Analyse a video <ArrowRight className="ml-1" size={18} /></Link></Button>
              <Button size="lg" variant="outline" asChild className="rounded-full px-7 border-white/20 bg-transparent" data-testid="hero-how-btn"><Link to="/how-it-works">How it works</Link></Button>
            </div>
            <p className="text-xs text-slate-500 mt-5">For players, parents, coaches and academies. Guardian consent required for players under 18.</p>
          </div>
          <div className="lg:col-span-6 relative fade-up" style={{ animationDelay: ".15s" }}>
            <img src="/images/hero.jpg" alt="Batter playing a shot in cricket nets" className="rounded-2xl h-[460px] w-full object-cover object-top border border-white/10" />
            <ExampleReport className="absolute -bottom-8 -left-4 sm:left-6 w-[290px]" />
          </div>
        </div>
      </section>
      <Section><H2 eyebrow="What it analyses" title="Batting and bowling, explained clearly" desc="Built around what a single phone camera can reliably show." />
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">{FEATURES.map(([I, t, d]) => <Card key={t} className="hover:border-[#00B4D8]/40 transition-colors"><I className="text-[#00B4D8] mb-4" /><h3 className="font-semibold text-lg mb-2">{t}</h3><p className="text-sm text-slate-400 leading-relaxed">{d}</p></Card>)}</div>
      </Section>
      <Section className="!pt-0"><H2 eyebrow="Who it's for" title="One platform, four kinds of cricketers" />
        <div className="grid md:grid-cols-4 gap-px bg-white/5 rounded-2xl overflow-hidden">{[["Players", "Get specific, evidence-linked feedback and a plan for your next sessions."], ["Parents", "Support young players with guardian consent and privacy controls built in."], ["Coaches", "Review assigned players' shared reports and add your own feedback."], ["Academies", "Manage batches, coaches and progress in an isolated workspace."]].map(([t, d]) => <div key={t} className="bg-[#0B132B] p-7"><h3 className="font-display font-bold text-xl mb-2">{t}</h3><p className="text-sm text-slate-400">{d}</p></div>)}</div>
      </Section>
      <Section className="!pt-0"><H2 eyebrow="Pricing" title="Choose the analysis you need" desc="Prices are set by CricAnalyze and may change; the checkout shows the final amount." /><PlanGrid /></Section>
      {posts.length > 0 && <Section className="!pt-0"><div className="flex justify-between items-end"><H2 eyebrow="From the blog" title="Latest articles" /><Link to="/blog" className="text-[#00B4D8] text-sm mb-12">All articles →</Link></div>
        <div className="grid md:grid-cols-3 gap-5">{posts.map((p) => <PostCard key={p.id} p={p} />)}</div></Section>}
      <Section className="!pt-0"><H2 eyebrow="FAQ" title="Common questions" /><FaqList limit={5} /></Section>
    </>
  );
};

export const ExampleReport = ({ className = "" }) => (
  <div className={`glass rounded-xl p-4 shadow-2xl ${className}`} data-testid="example-report-preview">
    <div className="flex justify-between items-center mb-3"><Badge tone="amber">EXAMPLE REPORT</Badge><span className="font-mono text-[10px] text-slate-400">BATTING · SIDE-ON</span></div>
    {[["Head position", 4, "high"], ["Front-foot stride", 3, "medium"], ["Bat path", null, "low"]].map(([a, r, c]) => (
      <div key={a} className="mb-2"><div className="flex justify-between text-xs"><span>{a}</span><span className="text-slate-400">{r ? `${r}/5 · ${c}` : "Not assessable"}</span></div>
        <div className="h-1.5 bg-white/10 rounded mt-1"><div className="h-full rounded bg-[#10B981]" style={{ width: r ? `${r * 20}%` : 0 }} /></div></div>))}
    <p className="text-[11px] text-slate-400 mt-3">Illustrative sample only — not a real player's result.</p>
  </div>
);

export const PlanGrid = () => {
  const [plans, setPlans] = useState([]);
  const { user } = useAuth();
  useEffect(() => { api.get("/plans").then(({ data }) => setPlans(data)).catch(() => {}); }, []);
  return (
    <div className="grid md:grid-cols-3 gap-5" data-testid="plan-grid">
      {plans.map((p, i) => (
        <div key={p.id} className={`rounded-2xl p-7 border ${i === 2 ? "border-[#10B981]/50 bg-[#10B981]/5" : "border-white/10 bg-[#0B132B]"}`} data-testid={`plan-card-${p.slug}`}>
          <div className="eyebrow">{p.billing}</div>
          <h3 className="text-2xl font-bold mt-2">{p.name}</h3>
          <div className="text-4xl font-display font-extrabold mt-4">{inr(p.price_inr)}<span className="text-sm text-slate-400 font-normal"> / {p.period_days} days</span></div>
          <p className="text-sm text-slate-400 mt-2 min-h-[40px]">{p.description}</p>
          <ul className="mt-5 space-y-2 text-sm">
            {[`${p.credits} analysis credits`, `${p.analysis_types.join(" + ")} analysis`, `${p.videos_per_analysis} video(s) per analysis, up to ${p.max_duration_s}s each`, `${p.report_level} report`,
              p.multi_angle && "Multi-angle input", p.pdf_export && "PDF export", p.comparisons && "Before/after comparisons", p.ai_coach && "AI coach", p.training_planner && "Training planner"].filter(Boolean)
              .map((x) => <li key={x} className="flex gap-2"><CheckCircle2 size={16} className="text-[#10B981] shrink-0 mt-0.5" /><span className="capitalize-first">{x}</span></li>)}
          </ul>
          <Button asChild className="w-full mt-7 rounded-full" variant={i === 2 ? "default" : "secondary"} data-testid={`plan-buy-${p.slug}`}><Link to={user ? `/app/billing?plan=${p.id}` : `/signup`}>Choose {p.name}</Link></Button>
        </div>))}
    </div>
  );
};

export const Features = () => (<><Seo title="Features" path="/features" description="Batting and bowling analysis, evidence frames, drills, AI coach, training planner, academy tools and more." />
  <Section><H2 h1 eyebrow="Features" title="Everything in CricAnalyze" />
    <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">{[...FEATURES, [MessageIcon, "AI Coach & Ask CricAnalyze", "Ask questions about your own reports. Answers cite report evidence and say so when data is missing."],
      [Layers, "Multi-angle input", "Label side-on, front-on and behind angles. Each angle gets its own visibility check; no 3D reconstruction is claimed."],
      [ShieldCheck, "Privacy first", "Private video storage, expiring links, guardian consent for minors, data export and account deletion."]].map(([I, t, d]) => <Card key={t}><I className="text-[#10B981] mb-4" /><h3 className="font-semibold text-lg mb-2">{t}</h3><p className="text-sm text-slate-400">{d}</p></Card>)}</div>
  </Section></>);
function MessageIcon(p) { return <Brain {...p} />; }

export const HowItWorks = () => (<><Seo title="How it works" path="/how-it-works" description="Record, upload, get an AI-assisted report and practise with linked drills." />
  <Section><H2 h1 eyebrow="How it works" title="From clip to practice plan in four steps" />
    <ol className="grid md:grid-cols-4 gap-5">{[["Record", "Film 5–30 seconds side-on or front-on, in good light, whole body in frame, 30fps or higher."], ["Upload", "Choose batting or bowling, label the camera angle and confirm consent. We check the file is a real, readable video."],
      ["Analyse", "We sample frames and an AI vision model describes what it can see, with timestamps and confidence. Usually takes 1–3 minutes."], ["Practise", "Follow the linked drills, generate a training plan, and compare your next video with this one."]]
      .map(([t, d], i) => <li key={t} className="glass rounded-xl p-6"><div className="font-mono text-[#00B4D8] text-sm">0{i + 1}</div><h3 className="text-xl font-bold mt-2 mb-2">{t}</h3><p className="text-sm text-slate-400">{d}</p></li>)}</ol>
    <Card className="mt-10"><h3 className="font-semibold mb-2">What the AI can and can't do</h3><p className="text-sm text-slate-400 leading-relaxed">The current analysis uses a hosted AI vision model on sampled frames. It does not measure bat speed, ball speed, forces or exact joint angles, and it does not run calibrated 3D biomechanics. Duration, frame rate and resolution are measured from your file; everything else is a visual assessment marked with confidence. It is not medical advice.</p></Card>
  </Section></>);

export const Pricing = () => (<><Seo title="Pricing" path="/pricing" description="Batting, bowling and all-rounder plans with analysis credits. Pay securely with Razorpay." />
  <Section><H2 h1 eyebrow="Pricing" title="Simple plans, clear limits" desc="Credits are reserved when an analysis starts and refunded automatically if processing fails." /><PlanGrid /></Section></>);

export const About = () => (<><Seo title="About" path="/about" description="CricAnalyze is built by Buddy Innovations and Technologies Pvt Ltd." />
  <Section><H2 h1 eyebrow="About" title="Built to make good coaching feedback more accessible" />
    <div className="grid md:grid-cols-2 gap-10 items-center"><div className="space-y-4 text-slate-300 leading-relaxed"><p>CricAnalyze is a product of Buddy Innovations and Technologies Pvt Ltd. We help cricketers understand their technique using AI-assisted video review — with honest limits, clear evidence and practical drills.</p>
      <p>We don't publish fake testimonials or invented statistics, and we never present AI output as an official selection credential.</p></div>
      <img src="/images/nets.jpg" alt="Cricket practice nets" className="rounded-2xl h-80 w-full object-cover" /></div>
  </Section></>);

const FAQS = [["What videos work best?", "5–30 second clips filmed side-on or front-on, whole body visible, steady camera, good light, 480p or higher. MP4, MOV and WEBM are supported."],
  ["Is the analysis done by a real AI model?", "Yes. Frames from your video are analysed by a hosted AI vision model. If the AI service is unavailable the job fails clearly and your credit is refunded — we never show made-up results."],
  ["Does it measure bat speed or bowling speed?", "No. Speeds, forces and exact angles need calibrated equipment. Reports show only visual observations with confidence levels."],
  ["Who can see my videos?", "Only you, unless you are in an academy and explicitly turn on report sharing. Videos are stored privately and served through short-lived links."],
  ["Can players under 18 use CricAnalyze?", "Yes, with verified guardian consent. A parent or guardian confirms by email code before any video is uploaded."],
  ["What happens if an analysis fails?", "The reserved credit is refunded automatically and you can retry."],
  ["How do payments work?", "Payments are processed by Razorpay. A plan activates only after the payment is verified on our server."],
  ["Can I delete my data?", "Yes. You can export your data or permanently delete your account from Settings."]];
export const FaqList = ({ limit }) => (
  <Accordion type="single" collapsible className="max-w-3xl" data-testid="faq-list">
    {FAQS.slice(0, limit || FAQS.length).map(([q, a], i) => <AccordionItem key={q} value={`f${i}`}><AccordionTrigger className="text-left">{q}</AccordionTrigger><AccordionContent className="text-slate-400">{a}</AccordionContent></AccordionItem>)}
  </Accordion>
);
export const Faq = () => (<><Seo title="FAQ" path="/faq" description="Answers about video requirements, AI analysis, privacy, minors and payments." jsonLd={{ "@context": "https://schema.org", "@type": "FAQPage", mainEntity: FAQS.map(([q, a]) => ({ "@type": "Question", name: q, acceptedAnswer: { "@type": "Answer", text: a } })) }} />
  <Section><H2 h1 eyebrow="FAQ" title="Frequently asked questions" /><FaqList /></Section></>);

export const Contact = () => {
  const [f, setF] = useState({ name: "", email: "", subject: "", message: "", website: "" });
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault(); setBusy(true);
    try { const { data } = await api.post("/contact", f); toast.success(data.message); setF({ name: "", email: "", subject: "", message: "", website: "" }); } catch (err) { toast.error(errMsg(err)); } finally { setBusy(false); }
  };
  return (<><Seo title="Contact" path="/contact" description="Contact the CricAnalyze team." />
    <Section><H2 h1 eyebrow="Contact" title="Talk to us" desc="Questions about plans, academies or your account? Send a message and we'll reply by email." />
      <form onSubmit={submit} className="glass rounded-2xl p-6 max-w-2xl grid gap-4" data-testid="contact-form">
        <div className="grid sm:grid-cols-2 gap-4"><Input placeholder="Your name" required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} data-testid="contact-name" aria-label="Name" />
          <Input type="email" placeholder="Email" required value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} data-testid="contact-email" aria-label="Email" /></div>
        <Input placeholder="Subject" required value={f.subject} onChange={(e) => setF({ ...f, subject: e.target.value })} data-testid="contact-subject" aria-label="Subject" />
        <Textarea placeholder="Message (at least 10 characters)" required minLength={10} rows={6} value={f.message} onChange={(e) => setF({ ...f, message: e.target.value })} data-testid="contact-message" aria-label="Message" />
        <input className="hidden" tabIndex={-1} autoComplete="off" value={f.website} onChange={(e) => setF({ ...f, website: e.target.value })} aria-hidden="true" />
        <Button type="submit" disabled={busy} className="justify-self-start" data-testid="contact-submit-btn">Send message</Button>
      </form></Section></>);
};

const LEGAL = {
  "privacy-policy": ["Privacy Policy", ["What we collect: name, verified email, optional phone, optional profile details, date of birth only when needed for age-appropriate handling, guardian contact for minors, uploaded videos, generated reports, payment references (never card details), and basic technical logs.",
    "Why: to provide analysis, reports, billing, security and support. Videos are processed by a hosted AI provider solely to generate your report.",
    "Minors: players under 18 must have verified guardian consent before uploading or sharing videos. Leaderboards are opt-in and never show minors' personal details.",
    "Sharing: we don't sell personal data. Reports are shared with an academy or coach only after you turn sharing on. Service providers (hosting, storage, email, payments, AI) process data on our behalf.",
    "Retention & rights: you can export your data or delete your account at any time from Settings. Contact us via the Contact page for other requests."]],
  "terms-and-conditions": ["Terms & Conditions", ["CricAnalyze is operated by Buddy Innovations and Technologies Pvt Ltd. By creating an account you agree to these terms.",
    "You must only upload videos you have the right to upload, and obtain consent from anyone identifiable in them.", "Analysis results are AI-assisted coaching observations, not professional, medical or selection assessments.",
    "Credits and plan limits apply as shown at purchase. Misuse, abuse or attempts to bypass limits may lead to suspension.", "We may update these terms; material changes will be notified by email."]],
  "refund-policy": ["Refund Policy", ["Credits reserved for an analysis that fails are refunded to your plan automatically.", "Payment refund requests can be sent via the Contact page; eligibility is reviewed case by case by the CricAnalyze team.",
    "Approved refunds are processed through Razorpay to the original payment method; timelines depend on your bank."]],
  "cookie-policy": ["Cookie Policy", ["We use essential cookies only: a secure, HTTP-only session cookie to keep you signed in and a security token cookie to protect forms.",
    "Analytics cookies (Google Analytics) will be used only once configured, and this policy will be updated accordingly."]],
  disclaimer: ["Disclaimer", ["CricAnalyze provides AI-assisted technique observations from sampled video frames. Accuracy depends on camera angle, lighting, resolution and occlusion.",
    "It does not diagnose injuries, guarantee performance improvement or injury prevention, or provide official selection credentials. Consult a qualified coach or medical professional where appropriate."]],
};
export const Legal = ({ slug }) => {
  const params = useParams();
  const [title, paras] = LEGAL[slug || params.slug] || LEGAL.disclaimer;
  return (<><Seo title={title} path={`/${slug}`} description={`${title} for CricAnalyze.`} />
    <Section className="max-w-3xl"><div className="eyebrow mb-3">Legal</div><h1 className="text-4xl font-bold mb-4">{title}</h1>
      <div className="flex gap-2 items-start text-xs text-amber-300 bg-amber-500/10 rounded-lg p-3 mb-8"><Lock size={14} className="mt-0.5" />Draft prepared for owner review. Not yet reviewed by a qualified legal professional.</div>
      <div className="space-y-4 text-slate-300 leading-relaxed">{paras.map((p) => <p key={p}>{p}</p>)}</div>
      <p className="text-sm text-slate-500 mt-10">Buddy Innovations and Technologies Pvt Ltd · cricanalyze.in</p></Section></>);
};

export const NotFound = () => (<><Seo title="Page not found" path="/404" noindex /><Section className="text-center"><div className="font-mono text-[#00B4D8]">404</div><h1 className="text-4xl font-bold mt-2">This page isn't here</h1>
  <p className="text-slate-400 mt-3">The link may be broken or the page may have moved.</p><Button asChild className="mt-6" data-testid="notfound-home-btn"><Link to="/">Go home</Link></Button></Section></>);
