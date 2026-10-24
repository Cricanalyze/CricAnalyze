import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { api } from "@/lib/api";

const Ctx = createContext(null);
export const useAuth = () => useContext(Ctx);

export const AuthProvider = ({ children }) => {
  const [state, setState] = useState({ user: null, ent: null, flags: {}, loading: true });
  const refresh = useCallback(async () => {
    try {
      const { data } = await api.get("/auth/me");
      setState({ user: data.user, ent: data.entitlements, flags: data.flags, loading: false });
      return data.user;
    } catch {
      setState({ user: null, ent: null, flags: {}, loading: false });
      return null;
    }
  }, []);
  useEffect(() => { refresh(); }, [refresh]);
  const logout = async () => {
    await api.post("/auth/logout").catch(() => {});
    setState({ user: null, ent: null, flags: {}, loading: false });
  };
  return <Ctx.Provider value={{ ...state, refresh, logout }}>{children}</Ctx.Provider>;
};

const STAFF = ["admin", "super_admin"];
export const isStaff = (u) => u && STAFF.includes(u.role);
export const isEditor = (u) => u && (isStaff(u) || u.role === "content_editor");

export const Protected = ({ children, check }) => {
  const { user, loading } = useAuth();
  const loc = useLocation();
  if (loading) return <div className="min-h-screen grid place-items-center text-slate-400" data-testid="auth-loading">Loading…</div>;
  if (!user) return <Navigate to={`/login?next=${encodeURIComponent(loc.pathname + loc.search)}`} replace />;
  if (check && !check(user)) return <Navigate to="/app" replace />;
  return children;
};
