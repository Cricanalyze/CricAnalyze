import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { useState } from "react";
import { Menu, X, LayoutDashboard, Upload, History, MessageSquare, CalendarCheck, Building2, IdCard, CreditCard, Settings, Shield, LogOut, Newspaper } from "lucide-react";
import { Logo } from "@/components/Common";
import { useAuth, isStaff, isEditor } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";

const NAV = [["Features", "/features"], ["How it works", "/how-it-works"], ["Pricing", "/pricing"], ["Blog", "/blog"], ["About", "/about"]];

export const PublicLayout = () => {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  return (
    <div className="min-h-screen flex flex-col">
      <header className="sticky top-0 z-40 backdrop-blur-xl bg-[#070D1E]/80 border-b border-white/5">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
          <Logo />
          <nav className="hidden md:flex gap-7 text-sm text-slate-300" aria-label="Main">
            {NAV.map(([l, h]) => <NavLink key={h} to={h} className={({ isActive }) => `hover:text-white transition-colors ${isActive ? "text-white" : ""}`} data-testid={`nav-${l.toLowerCase().replace(/ /g, "-")}`}>{l}</NavLink>)}
          </nav>
          <div className="hidden md:flex gap-2">
            {user ? <Button asChild data-testid="nav-dashboard-btn"><Link to="/app">Dashboard</Link></Button> : <>
              <Button variant="ghost" asChild data-testid="nav-login-btn"><Link to="/login">Sign in</Link></Button>
              <Button asChild className="bg-[#10B981] hover:bg-[#059669] text-[#0B132B]" data-testid="nav-signup-btn"><Link to="/signup">Start free account</Link></Button></>}
          </div>
          <button className="md:hidden p-2" onClick={() => setOpen(!open)} aria-label="Toggle menu" data-testid="mobile-menu-btn">{open ? <X /> : <Menu />}</button>
        </div>
        {open && <div className="md:hidden px-4 pb-4 flex flex-col gap-3 text-slate-200" onClick={() => setOpen(false)}>
          {NAV.map(([l, h]) => <Link key={h} to={h}>{l}</Link>)}
          <Link to={user ? "/app" : "/login"} className="text-[#10B981] font-semibold">{user ? "Dashboard" : "Sign in / Sign up"}</Link>
        </div>}
      </header>
      <main className="flex-1"><Outlet /></main>
      <Footer />
    </div>
  );
};

const Footer = () => (
  <footer className="border-t border-white/5 bg-[#0B132B] mt-20" data-testid="site-footer">
    <div className="max-w-7xl mx-auto px-4 sm:px-6 py-12 grid gap-10 sm:grid-cols-2 lg:grid-cols-4 text-sm">
      <div><Logo /><p className="text-slate-400 mt-3 leading-relaxed">AI-assisted cricket technique analysis for players, parents, coaches and academies.</p></div>
      <div><h3 className="font-semibold mb-3">Product</h3><ul className="space-y-2 text-slate-400">
        {[["Features", "/features"], ["How it works", "/how-it-works"], ["Pricing", "/pricing"], ["FAQ", "/faq"], ["Blog", "/blog"]].map(([l, h]) => <li key={h}><Link className="hover:text-white" to={h}>{l}</Link></li>)}</ul></div>
      <div><h3 className="font-semibold mb-3">Legal</h3><ul className="space-y-2 text-slate-400">
        {[["Privacy Policy", "/privacy-policy"], ["Terms & Conditions", "/terms-and-conditions"], ["Refund Policy", "/refund-policy"], ["Cookie Policy", "/cookie-policy"], ["Disclaimer", "/disclaimer"]].map(([l, h]) => <li key={h}><Link className="hover:text-white" to={h}>{l}</Link></li>)}</ul></div>
      <div><h3 className="font-semibold mb-3">Company</h3><ul className="space-y-2 text-slate-400">
        <li><Link className="hover:text-white" to="/about">About</Link></li><li><Link className="hover:text-white" to="/contact">Contact</Link></li>
        <li>Buddy Innovations and Technologies Pvt Ltd</li><li>cricanalyze.in</li></ul></div>
    </div>
    <div className="text-center text-xs text-slate-500 pb-8">© {new Date().getFullYear()} Buddy Innovations and Technologies Pvt Ltd. All rights reserved.</div>
  </footer>
);

const APP_NAV = [["Dashboard", "/app", LayoutDashboard], ["New analysis", "/app/upload", Upload], ["Analyses", "/app/analyses", History],
  ["AI Coach", "/app/coach", MessageSquare], ["Training", "/app/training", CalendarCheck], ["Academy", "/app/academy", Building2],
  ["Passport & badges", "/app/passport", IdCard], ["Billing", "/app/billing", CreditCard], ["Settings", "/app/settings", Settings]];

export const AppLayout = () => {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const links = [...APP_NAV];
  if (isEditor(user)) links.push(["Blog CMS", "/admin/blog", Newspaper]);
  if (isStaff(user)) links.push(["Admin", "/admin", Shield]);
  const side = (
    <nav className="flex flex-col gap-1" aria-label="App">
      {links.map(([l, h, I]) => <NavLink key={h} to={h} end={h === "/app" || h === "/admin"} onClick={() => setOpen(false)} data-testid={`side-${l.toLowerCase().replace(/[^a-z]+/g, "-")}`}
        className={({ isActive }) => `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${isActive ? "bg-[#00B4D8]/15 text-white" : "text-slate-400 hover:text-white hover:bg-white/5"}`}><I size={17} />{l}</NavLink>)}
      <button onClick={async () => { await logout(); nav("/"); }} className="flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-slate-400 hover:text-white mt-4" data-testid="logout-btn"><LogOut size={17} />Sign out</button>
    </nav>
  );
  return (
    <div className="min-h-screen flex">
      <aside className="hidden lg:flex flex-col w-64 shrink-0 border-r border-white/5 bg-[#0B132B] p-5 gap-8 sticky top-0 h-screen overflow-y-auto"><Logo />{side}</aside>
      <div className="flex-1 min-w-0">
        <header className="lg:hidden flex items-center justify-between px-4 h-14 border-b border-white/5 bg-[#0B132B]">
          <Logo /><button onClick={() => setOpen(!open)} aria-label="Toggle navigation" data-testid="app-menu-btn">{open ? <X /> : <Menu />}</button>
        </header>
        {open && <div className="lg:hidden p-4 bg-[#0B132B] border-b border-white/5">{side}</div>}
        <div className="px-4 sm:px-8 py-8 max-w-7xl"><div className="text-xs text-slate-500 mb-4" data-testid="signed-in-as">Signed in as {user?.full_name} · <span className="font-mono">{user?.role}</span></div><Outlet /></div>
      </div>
    </div>
  );
};
