const BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";
let token = localStorage.getItem("token");
export const setToken = (t) => { token = t; t ? localStorage.setItem("token", t) : localStorage.removeItem("token"); };
export const hasToken = () => !!token;

export async function api(path, { method = "GET", body, form } = {}) {
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body) headers["Content-Type"] = "application/json";
  const res = await fetch(BASE + path, { method, headers, body: form || (body ? JSON.stringify(body) : undefined) });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const d = data.detail;
    throw new Error(Array.isArray(d) ? d.map((x) => x.msg).join("; ") : d || res.statusText);
  }
  return data;
}
export const rs = (n) => "Rs " + Number(n ?? 0).toLocaleString("en-IN", { maximumFractionDigits: 0 });
