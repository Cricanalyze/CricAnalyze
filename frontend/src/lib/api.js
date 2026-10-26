import axios from "axios";

export const BACKEND = process.env.REACT_APP_BACKEND_URL;
export const SITE = "https://cricanalyze.in";
export const api = axios.create({
  baseURL: `${BACKEND}/api`,
  withCredentials: true,
  xsrfCookieName: "ca_csrf",
  xsrfHeaderName: "X-CSRF-Token",
  withXSRFToken: true,
});
export const errMsg = (e) => {
  const d = e?.response?.data?.detail;
  return typeof d === "string" ? d : e?.message || "Something went wrong.";
};
export const media = (p) => (p ? `${BACKEND}${p}` : null);
export const csrf = () => (document.cookie.match(/(?:^|; )ca_csrf=([^;]+)/) || [])[1] || "";
export const fmtDate = (d) => (d ? new Date(d).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }) : "—");
export const inr = (n) => `₹${Number(n || 0).toLocaleString("en-IN")}`;
export const download = async (path, name) => {
  const r = await api.get(path, { responseType: "blob" });
  const url = URL.createObjectURL(r.data);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
};
