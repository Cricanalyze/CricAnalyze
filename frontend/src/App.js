import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { HelmetProvider } from "react-helmet-async";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider, Protected, isStaff, isEditor } from "@/context/AuthContext";
import { PublicLayout, AppLayout } from "@/components/Layouts";
import SharedReport from "@/pages/SharedReport";
import { Home, Features, HowItWorks, Pricing, About, Faq, Contact, Legal, NotFound } from "@/pages/Public";
import { BlogList, BlogPost, SharedPassport } from "@/pages/Blog";
import { Login, Signup, VerifyEmail, ForgotPassword, ResetPassword } from "@/pages/Auth";
import { Dashboard, Upload, Analyses, Report } from "@/pages/AppMain";
import { Coach, Training, Passport } from "@/pages/AppTools";
import { Academy, Billing, Settings } from "@/pages/AppAccount";
import Admin from "@/pages/Admin";
import AdminBlog from "@/pages/AdminBlog";

const LEGAL = ["privacy-policy", "terms-and-conditions", "refund-policy", "cookie-policy", "disclaimer"];

function App() {
  return (
    <HelmetProvider>
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            <Route path="/r/:token" element={<SharedReport />} />
            <Route element={<PublicLayout />}>
              <Route path="/" element={<Home />} />
              <Route path="/features" element={<Features />} />
              <Route path="/how-it-works" element={<HowItWorks />} />
              <Route path="/pricing" element={<Pricing />} />
              <Route path="/about" element={<About />} />
              <Route path="/faq" element={<Faq />} />
              <Route path="/contact" element={<Contact />} />
              {LEGAL.map((s) => <Route key={s} path={`/${s}`} element={<Legal slug={s} />} />)}
              <Route path="/blog" element={<BlogList />} />
              <Route path="/blog/category/:slug" element={<BlogList kind="category" />} />
              <Route path="/blog/tag/:slug" element={<BlogList kind="tag" />} />
              <Route path="/blog/author/:slug" element={<BlogList kind="author" />} />
              <Route path="/blog/:slug" element={<BlogPost />} />
              <Route path="/passport/:token" element={<SharedPassport />} />
              <Route path="*" element={<NotFound />} />
            </Route>
            <Route path="/login" element={<Login />} />
            <Route path="/signup" element={<Signup />} />
            <Route path="/verify-email" element={<VerifyEmail />} />
            <Route path="/forgot-password" element={<ForgotPassword />} />
            <Route path="/reset-password" element={<ResetPassword />} />
            <Route element={<Protected><AppLayout /></Protected>}>
              <Route path="/app" element={<Dashboard />} />
              <Route path="/app/upload" element={<Upload />} />
              <Route path="/app/analyses" element={<Analyses />} />
              <Route path="/app/analyses/:id" element={<Report />} />
              <Route path="/app/coach" element={<Coach />} />
              <Route path="/app/training" element={<Training />} />
              <Route path="/app/academy" element={<Academy />} />
              <Route path="/app/passport" element={<Passport />} />
              <Route path="/app/billing" element={<Billing />} />
              <Route path="/app/settings" element={<Settings />} />
              <Route path="/admin" element={<Protected check={isStaff}><Admin /></Protected>} />
              <Route path="/admin/blog" element={<Protected check={isEditor}><AdminBlog /></Protected>} />
            </Route>
          </Routes>
          <Toaster richColors position="top-right" />
        </AuthProvider>
      </BrowserRouter>
    </HelmetProvider>
  );
}

export default App;
